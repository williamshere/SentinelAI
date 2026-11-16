from types import SimpleNamespace
from unittest.mock import Mock

from ui.dashboard import SentinelDashboard


def harness():
    window = SimpleNamespace(
        _chat_busy=True, chat_worker=None, _chat_workers=set(),
        _chat_history_generation=0, chat_engine=SimpleNamespace(history=[]),
        btn_chat_send=Mock(), chat_input=Mock(), _append_chat_bubble=Mock(),
        chat_watchdog=Mock(), sender=Mock(),
    )
    return window


def test_timeout_restores_input_and_late_signals_cannot_disrupt_new_request():
    window = harness()
    old, new = Mock(), Mock()
    window.chat_worker = old
    window._chat_workers.add(old)
    SentinelDashboard._on_chat_timeout(window)
    assert not window._chat_busy
    assert window.chat_worker is None
    assert old in window._chat_workers
    window.btn_chat_send.setEnabled.assert_called_with(True)
    window.chat_input.setEnabled.assert_called_with(True)

    window._chat_busy = True
    window.chat_worker = new
    window._chat_workers.add(new)
    window.sender.return_value = old
    window._append_chat_bubble.reset_mock()
    SentinelDashboard._on_chat_response_ready(window, {'content': 'late'})
    window._append_chat_bubble.assert_not_called()
    SentinelDashboard._on_chat_finished(window)
    assert window._chat_busy
    assert window.chat_worker is new
    assert old not in window._chat_workers
    assert new in window._chat_workers
    old.deleteLater.assert_called_once()
    window.chat_watchdog.stop.assert_not_called()


def test_active_result_updates_history_and_clear_generation_prevents_resurrection():
    window = harness()
    worker = Mock()
    worker.history_generation = 0
    worker.chat_engine.history = [{'role': 'user', 'content': 'question'}]
    window.chat_worker = worker
    window._chat_workers.add(worker)
    window.sender.return_value = worker
    SentinelDashboard._on_chat_response_ready(window, {'content': 'answer'})
    assert window.chat_engine.history == worker.chat_engine.history
    assert window.chat_engine.history is not worker.chat_engine.history
    window._chat_history_generation += 1
    window.chat_engine.history = []
    SentinelDashboard._on_chat_response_ready(window, {'content': 'answer'})
    assert window.chat_engine.history == []
    SentinelDashboard._on_chat_finished(window)
    assert not window._chat_busy
    assert window.chat_worker is None
    assert not window._chat_workers
    worker.deleteLater.assert_called_once()


def test_qt_queued_late_response_is_ignored():
    import threading
    import time
    from PySide6.QtCore import QObject, QThread, Signal
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    class Worker(QThread):
        response_ready = Signal(dict)
        def __init__(self):
            super().__init__()
            self.release = threading.Event()
            self.history_generation = 0
            self.chat_engine = SimpleNamespace(history=[])
        def run(self):
            self.release.wait(3)
            self.response_ready.emit({'content': 'finished'})
    class Window(QObject):
        _on_chat_timeout = SentinelDashboard._on_chat_timeout
        _on_chat_finished = SentinelDashboard._on_chat_finished
        _on_chat_response_ready = SentinelDashboard._on_chat_response_ready
        def __init__(self):
            super().__init__()
            self._chat_busy = True
            self.chat_worker = None
            self._chat_workers = set()
            self._chat_history_generation = 0
            self.chat_engine = SimpleNamespace(history=[])
            self.btn_chat_send = Mock()
            self.chat_input = Mock()
            self._append_chat_bubble = Mock()
            self.chat_watchdog = Mock()
    window = Window()
    old, new = Worker(), Worker()
    try:
        for worker in (old, new):
            worker.response_ready.connect(window._on_chat_response_ready)
            worker.finished.connect(window._on_chat_finished)
        window.chat_worker = old
        window._chat_workers.add(old)
        old.start()
        window._on_chat_timeout()
        window.chat_worker = new
        window._chat_busy = True
        window._chat_workers.add(new)
        new.start()
        window._append_chat_bubble.reset_mock()
        old.release.set()
        deadline = time.monotonic() + 2
        while old in window._chat_workers and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(.005)
        assert old not in window._chat_workers
        assert window.chat_worker is new and window._chat_busy
        window._append_chat_bubble.assert_not_called()
        new.release.set()
        deadline = time.monotonic() + 2
        while new in window._chat_workers and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(.005)
        assert new not in window._chat_workers
        assert not window._chat_busy
        window._append_chat_bubble.assert_called_once()
    finally:
        for worker in (old, new):
            worker.release.set()
            # A finished worker may already have been deleted by Qt.
            if worker in window._chat_workers:
                worker.wait(3000)
        app.processEvents()
