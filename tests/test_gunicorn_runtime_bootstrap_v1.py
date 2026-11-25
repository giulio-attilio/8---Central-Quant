import importlib.util
import os
import signal
import sys
import threading
from pathlib import Path
from types import ModuleType, SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]


def _load_config():
    spec = importlib.util.spec_from_file_location(
        "central_gunicorn_config_test", ROOT / "gunicorn.conf.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_wsgi_entry_disables_inline_autostart_before_importing_main():
    source = (ROOT / "central_wsgi.py").read_text(encoding="utf-8")
    assert source.index('os.environ["CENTRAL_AUTO_START_RUNTIME"] = "false"') < source.index(
        "import main as central_main"
    )
    assert "app = central_main.app" in source


def test_wsgi_entry_sets_gate_and_exports_app_without_loading_runtime(monkeypatch):
    fake_app = object()
    fake_main = ModuleType("main")
    fake_main.app = fake_app
    monkeypatch.setitem(sys.modules, "main", fake_main)
    monkeypatch.delenv("CENTRAL_AUTO_START_RUNTIME", raising=False)

    spec = importlib.util.spec_from_file_location(
        "central_wsgi_entry_test", ROOT / "central_wsgi.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert os.environ["CENTRAL_AUTO_START_RUNTIME"] == "false"
    assert module.app is fake_app


def test_gunicorn_uses_one_bounded_worker_and_render_port():
    config = _load_config()
    assert config.bind == "0.0.0.0:10000"
    assert config.workers == 1
    assert config.worker_class == "gthread"
    assert config.threads == 16
    assert config.preload_app is False
    assert 0 < config.graceful_timeout < 30
    assert config._DRAIN_WINDOW_SECONDS < 30
    assert config.accesslog is None


def test_startup_hook_rejects_multiple_workers_or_preload():
    config = _load_config()
    for workers, preload in ((2, False), (1, True)):
        server = SimpleNamespace(
            cfg=SimpleNamespace(workers=workers, preload_app=preload)
        )
        try:
            config.on_starting(server)
        except RuntimeError as exc:
            assert str(exc) == "CENTRAL_GUNICORN_SINGLE_WORKER_REQUIRED"
        else:
            raise AssertionError("unsafe Gunicorn process topology accepted")


def test_startup_hook_starts_runtime_in_background_and_disables_no_more_gates(monkeypatch):
    config = _load_config()
    started = threading.Event()

    class FakeDrain:
        def begin_draining(self):
            pass

        def wait_for_shutdown_work(self, timeout):
            return True

    central_main = SimpleNamespace(
        start_central_runtime_once=started.set,
        RUNTIME_DRAIN=FakeDrain(),
    )
    central_wsgi = ModuleType("central_wsgi")
    central_wsgi.central_main = central_main
    monkeypatch.setitem(sys.modules, "central_wsgi", central_wsgi)
    monkeypatch.setenv("CENTRAL_AUTO_START_RUNTIME", "false")

    originals = {}

    def fake_getsignal(sig):
        def original(signum, frame):
            originals.setdefault("called", []).append(signum)

        return original

    installed = {}
    monkeypatch.setattr(config, "signal", SimpleNamespace(
        SIGTERM=signal.SIGTERM,
        SIGINT=signal.SIGINT,
        getsignal=fake_getsignal,
        signal=lambda sig, handler: installed.__setitem__(sig, handler),
    ))

    config.post_worker_init(SimpleNamespace())
    assert started.wait(2)
    installed[signal.SIGTERM](signal.SIGTERM, None)
    assert originals.get("called") == [signal.SIGTERM]
    assert central_main.RUNTIME_DRAIN.wait_for_shutdown_work(0.1)


def test_shutdown_signal_requests_one_drain_monitor(monkeypatch):
    config = _load_config()

    class FakeDrain:
        def __init__(self):
            self.begin_calls = 0

        def begin_draining(self):
            self.begin_calls += 1

        def wait_for_shutdown_work(self, timeout):
            return True

    state = FakeDrain()
    monkeypatch.setattr(config, "_CENTRAL_MAIN", SimpleNamespace(RUNTIME_DRAIN=state))
    monkeypatch.setattr(config, "_RUNTIME_START_THREAD", None)
    monkeypatch.setattr(config, "_SHUTDOWN_REQUESTED_AT", None)
    monkeypatch.setattr(config, "_DRAIN_MONITOR_THREAD", None)
    monkeypatch.setattr(config, "_DRAIN_COMPLETE", threading.Event())

    config._request_drain(config._CENTRAL_MAIN)
    monitor = config._DRAIN_MONITOR_THREAD
    config._request_drain(config._CENTRAL_MAIN)
    monitor.join(1)

    assert not monitor.is_alive()
    assert state.begin_calls == 1
    assert config._DRAIN_COMPLETE.is_set()


def test_worker_exit_wait_is_capped_by_remaining_shared_deadline(monkeypatch):
    config = _load_config()
    now = [126.95]
    requested_at = 100.0
    waits = []

    class FakeEvent:
        def is_set(self):
            return False

        def wait(self, timeout):
            waits.append(timeout)
            now[0] += timeout
            return False

    monkeypatch.setattr(config, "_CENTRAL_MAIN", object())
    monkeypatch.setattr(config, "_SHUTDOWN_REQUESTED_AT", requested_at)
    monkeypatch.setattr(config, "_DRAIN_COMPLETE", FakeEvent())
    monkeypatch.setattr(config, "_DRAIN_WINDOW_SECONDS", 27.0)
    monkeypatch.setattr(
        config, "time", SimpleNamespace(monotonic=lambda: now[0])
    )

    config.worker_exit(None, None)

    deadline = requested_at + config._DRAIN_WINDOW_SECONDS
    assert waits
    assert max(waits) <= 0.1
    assert now[0] == deadline


def test_startup_gate_mismatch_fails_closed(monkeypatch):
    config = _load_config()
    central_wsgi = ModuleType("central_wsgi")
    central_wsgi.central_main = SimpleNamespace(
        start_central_runtime_once=lambda: None,
        RUNTIME_DRAIN=SimpleNamespace(),
    )
    monkeypatch.setitem(sys.modules, "central_wsgi", central_wsgi)
    monkeypatch.setenv("CENTRAL_AUTO_START_RUNTIME", "true")
    try:
        config.post_worker_init(SimpleNamespace())
    except RuntimeError as exc:
        assert str(exc) == "CENTRAL_GUNICORN_RUNTIME_AUTOSTART_NOT_DISABLED"
    else:
        raise AssertionError("unexpectedly accepted duplicate runtime startup")
