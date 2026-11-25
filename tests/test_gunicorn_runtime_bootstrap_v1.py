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
