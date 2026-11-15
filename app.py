"""
app.py - Main entry point for Sentinel AI Security & Hardware Telemetry Suite.
"""
import sys
from pathlib import Path

# Ensure project root is always first in sys.path regardless of launch cwd
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if __name__ == "__main__":
    if len(sys.argv) == 5 and sys.argv[1] == "--compute-worker":
        from core.compute import run_worker
        sys.exit(run_worker(sys.argv[2], int(sys.argv[3]), int(sys.argv[4])))
    from ui.dashboard import main
    main()
