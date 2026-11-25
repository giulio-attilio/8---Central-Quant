"""Bounded, single-worker Gunicorn configuration for Render's web service.

Render sends SIGTERM and, for services with a persistent disk, enforces its
default 30-second shutdown delay. Runtime drain and active HTTP request grace
therefore share one bounded window instead of being performed sequentially.
"""

import os
import signal
import threading
import time


bind = f"0.0.0.0:{int(os.environ.get('PORT', '10000'))}"
workers = 1
worker_class = "gthread"
threads = 16
preload_app = False
timeout = 120
graceful_timeout = 29
keepalive = 2
# Avoid logging full request targets, which may contain sensitive query values.
accesslog = None
errorlog = "-"

_DRAIN_WINDOW_SECONDS = 27.0
_SHUTDOWN_REQUESTED_AT = None
_CENTRAL_MAIN = None
_RUNTIME_START_THREAD = None
_DRAIN_MONITOR_THREAD = None
_DRAIN_COMPLETE = threading.Event()


def _start_central_runtime(central_main):
    try:
        central_main.start_central_runtime_once()
    except Exception as exc:
        # Do not log exception text: it may contain paths or operational data.
        print(
            "CENTRAL_RUNTIME_STARTUP_FAILED "
            f"error_type={type(exc).__name__}",
            flush=True,
        )


def _wait_for_runtime_drain(central_main, startup_thread, deadline):
    state = central_main.RUNTIME_DRAIN
    state.begin_draining()
    while time.monotonic() < deadline:
        if startup_thread is not None and startup_thread.is_alive():
            time.sleep(0.05)
            continue
        remaining = max(0.0, deadline - time.monotonic())
        if state.wait_for_shutdown_work(min(0.25, remaining)):
            _DRAIN_COMPLETE.set()
            print("CENTRAL_RUNTIME_DRAIN_COMPLETE", flush=True)
            return
    _DRAIN_COMPLETE.set()
    print("CENTRAL_RUNTIME_DRAIN_TIMEOUT", flush=True)


def _request_drain(central_main):
    global _SHUTDOWN_REQUESTED_AT, _DRAIN_MONITOR_THREAD
    if _SHUTDOWN_REQUESTED_AT is not None:
        return

    # The signal handler only assigns this timestamp and delegates to
    # Gunicorn's original handler. A monitor thread performs lock-taking work.
    _SHUTDOWN_REQUESTED_AT = time.monotonic()
    deadline = _SHUTDOWN_REQUESTED_AT + _DRAIN_WINDOW_SECONDS
    _DRAIN_MONITOR_THREAD = threading.Thread(
        target=_wait_for_runtime_drain,
        args=(central_main, _RUNTIME_START_THREAD, deadline),
        name="central-runtime-drain",
        daemon=True,
    )
    _DRAIN_MONITOR_THREAD.start()


def on_starting(server):
    """Reject worker/process settings that would duplicate bot runtimes."""
    config = server.cfg
    if config.workers != 1 or config.preload_app:
        raise RuntimeError("CENTRAL_GUNICORN_SINGLE_WORKER_REQUIRED")


def post_worker_init(worker):
    """Start bot runtime off-thread after the WSGI app has loaded."""
    global _CENTRAL_MAIN, _RUNTIME_START_THREAD
    import central_wsgi

    _CENTRAL_MAIN = central_wsgi.central_main
    if os.environ.get("CENTRAL_AUTO_START_RUNTIME", "").strip().lower() != "false":
        raise RuntimeError("CENTRAL_GUNICORN_RUNTIME_AUTOSTART_NOT_DISABLED")

    for signal_name in ("SIGTERM", "SIGINT"):
        signal_number = getattr(signal, signal_name, None)
        if signal_number is None:
            continue
        original_handler = signal.getsignal(signal_number)
        if not callable(original_handler):
            raise RuntimeError("CENTRAL_GUNICORN_SIGNAL_HANDLER_UNAVAILABLE")

        def _handle_shutdown(signum, frame, _original=original_handler):
            _request_drain(_CENTRAL_MAIN)
            _original(signum, frame)

        signal.signal(signal_number, _handle_shutdown)

    _RUNTIME_START_THREAD = threading.Thread(
        target=_start_central_runtime,
        args=(_CENTRAL_MAIN,),
        name="central-runtime-startup",
        daemon=True,
    )
    _RUNTIME_START_THREAD.start()


def worker_exit(server, worker):
    """Wait only for the remaining portion of the shared Render drain window."""
    global _SHUTDOWN_REQUESTED_AT
    central_main = _CENTRAL_MAIN
    if central_main is None:
        return
    if _SHUTDOWN_REQUESTED_AT is None:
        _request_drain(central_main)

    deadline = _SHUTDOWN_REQUESTED_AT + _DRAIN_WINDOW_SECONDS
    while not _DRAIN_COMPLETE.is_set():
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        _DRAIN_COMPLETE.wait(min(0.1, remaining))
