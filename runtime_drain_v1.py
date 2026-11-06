"""Small process-local drain gate for graceful service shutdown.

This module has no I/O or startup side effects. It only coordinates entry
flows inside the current process; it is not a distributed lock or readiness
signal.
"""

from __future__ import annotations

from functools import wraps
import signal
import threading
import time


class RuntimeDrainState:
    """Atomically stop admission of new live entries and track in-flight ones."""

    def __init__(self):
        self._condition = threading.Condition()
        self._draining = False
        self._active_entries = 0
        self._active_management_cycles = 0
        self._management_local = threading.local()

    def try_enter_live_entry(self) -> bool:
        with self._condition:
            if self._draining:
                return False
            self._active_entries += 1
            return True

    def leave_live_entry(self) -> None:
        with self._condition:
            if self._active_entries <= 0:
                raise RuntimeError("runtime drain entry count underflow")
            self._active_entries -= 1
            if self._active_entries == 0:
                self._condition.notify_all()

    def begin_draining(self) -> bool:
        """Enter drain mode; return True only for the first caller."""
        with self._condition:
            first = not self._draining
            self._draining = True
            self._condition.notify_all()
            return first

    def is_draining(self) -> bool:
        with self._condition:
            return self._draining

    def active_live_entries(self) -> int:
        with self._condition:
            return self._active_entries

    def try_enter_management_cycle(self) -> bool:
        """Admit one position-management pass unless shutdown has begun."""
        with self._condition:
            if self._draining:
                return False
            self._active_management_cycles += 1
            return True

    def leave_management_cycle(self) -> None:
        with self._condition:
            if self._active_management_cycles <= 0:
                raise RuntimeError("runtime drain management count underflow")
            self._active_management_cycles -= 1
            if self._active_management_cycles == 0:
                self._condition.notify_all()

    def active_management_cycles(self) -> int:
        with self._condition:
            return self._active_management_cycles

    def wait_for_live_entries(self, timeout_seconds: float) -> bool:
        deadline = time.monotonic() + max(0.0, float(timeout_seconds))
        with self._condition:
            while self._active_entries:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._condition.wait(remaining)
            return True

    def wait_for_shutdown_work(self, timeout_seconds: float) -> bool:
        """Wait for admitted live entries and existing management passes."""
        deadline = time.monotonic() + max(0.0, float(timeout_seconds))
        with self._condition:
            while self._active_entries or self._active_management_cycles:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._condition.wait(remaining)
            return True


RUNTIME_DRAIN = RuntimeDrainState()


def guard_management_cycle(state):
    """Count a position-management call so shutdown waits for it to finish."""

    def decorate(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            depth = getattr(state._management_local, "depth", 0)
            if depth:
                state._management_local.depth = depth + 1
                try:
                    return function(*args, **kwargs)
                finally:
                    state._management_local.depth = depth
            if not state.try_enter_management_cycle():
                return None
            state._management_local.depth = 1
            try:
                return function(*args, **kwargs)
            finally:
                state._management_local.depth = 0
                state.leave_management_cycle()

        return wrapped

    return decorate


def guard_new_live_entries(state, live_send_enabled):
    """Decorate a broker entry boundary while leaving reduce-only calls alone."""

    def decorate(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            reduce_only = kwargs.get("reduce_only", args[3] if len(args) > 3 else False)
            reduce_only = (
                reduce_only is True
                or str(reduce_only).strip().lower() in {"1", "true", "yes", "sim", "on"}
            )
            try:
                live_enabled = bool(live_send_enabled())
            except Exception:
                # If mode inspection itself fails, conservatively treat a
                # non-reduce-only call as live-capable at the final boundary.
                live_enabled = True

            if not live_enabled or reduce_only:
                return function(*args, **kwargs)
            if not state.try_enter_live_entry():
                return {
                    "ok": False,
                    "status": "ENTRY_BLOCKED_RUNTIME_DRAIN",
                    "sent": False,
                    "reason": "RUNTIME_DRAINING",
                    "live_send_enabled": True,
                    "preview_isolation": True,
                }
            try:
                return function(*args, **kwargs)
            finally:
                state.leave_live_entry()

        return wrapped

    return decorate


def guard_live_flow(state, live_flow_enabled, blocked_result):
    """Track a complete live-entry orchestration flow, including its caller-side persistence.

    ``blocked_result`` receives the original positional and keyword arguments
    and must return the wrapped function's normal result shape. If mode
    inspection fails, conservatively treat the flow as live-capable so drain
    cannot silently admit an unclassified entry.
    """

    def decorate(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            try:
                live_enabled = bool(live_flow_enabled(*args, **kwargs))
            except Exception:
                live_enabled = True
            if not live_enabled:
                return function(*args, **kwargs)
            if not state.try_enter_live_entry():
                return blocked_result(args, kwargs)
            try:
                return function(*args, **kwargs)
            finally:
                state.leave_live_entry()

        return wrapped

    return decorate


def runtime_drain_blocked_result(*, message="Runtime is draining"):
    return {
        "ok": False,
        "status": "ENTRY_BLOCKED_RUNTIME_DRAIN",
        "sent": False,
        "send_attempted": False,
        "reason": "RUNTIME_DRAINING",
        "message": message,
        "reconciliation_required": False,
    }


def install_shutdown_signal_handlers(server, state=RUNTIME_DRAIN, signal_module=None):
    """Install SIGTERM/SIGINT handlers that initiate drain and stop HTTP serving."""
    signal_module = signal_module or signal
    previous = {}

    def request_shutdown(_signum, _frame):
        if state.begin_draining():
            # BaseServer.shutdown must run outside the serving thread.
            threading.Thread(target=server.shutdown, name="central-http-shutdown", daemon=True).start()

    for signal_name in ("SIGTERM", "SIGINT"):
        signal_value = getattr(signal_module, signal_name, None)
        if signal_value is None:
            continue
        previous[signal_value] = signal_module.getsignal(signal_value)
        signal_module.signal(signal_value, request_shutdown)

    def restore():
        for signal_value, handler in previous.items():
            signal_module.signal(signal_value, handler)

    return restore


def close_after_drain(server, state=RUNTIME_DRAIN, grace_seconds: float = 27.0) -> bool:
    """Wait within Render's default SIGTERM window, then close the HTTP socket."""
    state.begin_draining()
    drained = state.wait_for_shutdown_work(grace_seconds)
    server.server_close()
    return drained
