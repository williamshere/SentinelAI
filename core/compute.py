"""Bounded compute workers. No Qt imports; failures are explicit JSON messages."""
import hashlib
import json
import os
import sys
import time


def emit(**data):
    output = os.environ.get("SENTINEL_COMPUTE_OUTPUT")
    if output:
        # Windowed PyInstaller executables have no sys.stdout on Windows.
        with open(output, "a", encoding="utf-8") as stream:
            stream.write(json.dumps(data) + "\n")
    else:
        print(json.dumps(data), flush=True)


def cpu_step():
    # Real SHA-256 throughput with a known-answer integrity check on each batch.
    block = b"a" * 1_000_000
    expected = "cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0"
    def step():
        if hashlib.sha256(block).hexdigest() != expected:
            raise RuntimeError("CPU SHA-256 integrity check failed")
        return len(block) / 1e6
    return step, "SHA-256", "MB/s"


def gpu_step():
    try:
        import numpy as np
        import pyopencl as cl
    except ImportError as exc:
        raise RuntimeError("GPU compute needs the optional gpu extra (pip install '.[gpu]') and an OpenCL GPU driver") from exc
    devices = [d for p in cl.get_platforms() for d in p.get_devices(device_type=cl.device_type.GPU)]
    if not devices:
        raise RuntimeError("No OpenCL GPU found; CPU OpenCL devices are not used as a GPU fallback")
    monitored_name = os.environ.get("SENTINEL_GPU_NAME", "")
    if monitored_name:
        def normalized(name):
            return str(name).lower().replace("nvidia", "").replace(" ", "").strip()
        devices = [d for d in devices if normalized(d.name) == normalized(monitored_name)]
        if len(devices) != 1:
            raise RuntimeError("Cannot uniquely match the OpenCL device to the monitored GPU; test was not started")
    device = devices[0]
    context = cl.Context([device])
    queue = cl.CommandQueue(context)
    # 8 MiB of bounded GPU buffers; deterministic uint arithmetic is checked in full.
    source = np.arange(1 << 20, dtype=np.uint32)
    result = np.empty_like(source)
    expected = source.copy()
    for _ in range(128):
        expected = expected * np.uint32(1664525) + np.uint32(1013904223)
    flags = cl.mem_flags
    src = cl.Buffer(context, flags.READ_ONLY | flags.COPY_HOST_PTR, hostbuf=source)
    dst = cl.Buffer(context, flags.WRITE_ONLY, result.nbytes)
    program = cl.Program(context, """
        __kernel void verify(__global const uint *src, __global uint *dst) {
            size_t i = get_global_id(0);
            uint x = src[i];
            for (int j = 0; j < 128; ++j) x = x * 1664525u + 1013904223u;
            dst[i] = x;
        }
    """).build()
    kernel = cl.Kernel(program, "verify")
    def step():
        kernel(queue, source.shape, None, src, dst)
        cl.enqueue_copy(queue, result, dst).wait()
        if not np.array_equal(result, expected):
            raise RuntimeError("GPU integer compute integrity check failed")
        return source.size * 128 / 1e6
    return step, str(device.name).strip(), "M iterations/s"


def run_worker(kind, seconds, load):
    try:
        if kind not in ("cpu", "gpu") or not 1 <= seconds <= 300 or not 10 <= load <= 100:
            raise ValueError("Invalid workload parameters")
        step, device, unit = cpu_step() if kind == "cpu" else gpu_step()
        emit(event="ready", device=device, unit=unit)
        start = last = time.monotonic()
        work = 0.0
        while time.monotonic() - start < seconds:
            cycle = time.monotonic()
            while time.monotonic() - cycle < 0.05 * load / 100:
                work += step()
            time.sleep(max(0, 0.05 - (time.monotonic() - cycle)))
            now = time.monotonic()
            if now - last >= 0.5:
                emit(event="progress", rate=round(work / (now - start), 2), unit=unit)
                last = now
        emit(event="complete", rate=round(work / max(time.monotonic() - start, 0.001), 2), unit=unit)
        return 0
    except Exception as exc:
        emit(event="error", message=str(exc))
        return 1


if __name__ == "__main__":
    sys.exit(run_worker(sys.argv[1], int(sys.argv[2]), int(sys.argv[3])))
