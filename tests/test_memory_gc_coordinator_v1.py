from __future__ import annotations

import ast
import io
import threading
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import memory_gc_coordinator as coordinator_module
import memory_profiler_v1 as memory_profiler
from memory_gc_coordinator import (
    MemoryGCCoordinator,
    emit_memory_gc_skipped,
)
from memory_source_observability import emit_memory_source_observation


ROOT = Path(__file__).resolve().parents[1]
MAIN_SOURCE = (ROOT / "main.py").read_text(encoding="utf-8")
MAIN_TREE = ast.parse(MAIN_SOURCE)
PROFILER_SOURCE = (ROOT / "memory_profiler_v1.py").read_text(encoding="utf-8")
PROFILER_TREE = ast.parse(PROFILER_SOURCE)


class _TrackingLock:
    """Expose when the second test caller has started waiting on the lock."""

    def __init__(self, lock, second_entered):
        self._lock = lock
        self._second_entered = second_entered
        self._guard = threading.Lock()
        self._enters = 0

    def __enter__(self):
        with self._guard:
            self._enters += 1
            if self._enters == 2:
                self._second_entered.set()
        self._lock.acquire()
        return self

    def __exit__(self, exc_type, exc, traceback):
        self._lock.release()
        return False


def _overlapping_attempts(*, force):
    coordinator = MemoryGCCoordinator()
    collect_started = threading.Event()
    release_collect = threading.Event()
    second_entered = threading.Event()
    coordinator._lock = _TrackingLock(coordinator._lock, second_entered)
    rss = {"value": 950.0}
    calls = {"collect": 0, "trim": 0}
    results = []
    errors = []

    def collect_fn():
        calls["collect"] += 1
        collect_started.set()
        if not release_collect.wait(timeout=2):
            raise AssertionError("test did not release collect")
        return 11

    def trim_fn():
        calls["trim"] += 1
        rss["value"] = 700.0

    def caller(reason):
        try:
            results.append(coordinator.coordinate(
                reason=reason,
                force=force,
                threshold_mb=900.0,
                rss_before_mb=950.0,
                current_rss_fn=lambda: rss["value"],
                collect_fn=collect_fn,
                trim_fn=trim_fn,
            ))
        except Exception as exc:  # pragma: no cover - assertion aid
            errors.append(exc)

    first = threading.Thread(target=caller, args=("first",))
    second = threading.Thread(target=caller, args=("second",))
    first.start()
    assert collect_started.wait(timeout=2)
    second.start()
    assert second_entered.wait(timeout=2)
    release_collect.set()
    first.join(timeout=2)
    second.join(timeout=2)

    assert not first.is_alive()
    assert not second.is_alive()
    assert errors == []
    return calls, results


def _coordinate_once(coordinator, *, force, rss, collect_fn, trim_fn):
    return coordinator.coordinate(
        reason="test",
        force=force,
        threshold_mb=900.0,
        rss_before_mb=rss,
        current_rss_fn=lambda: rss,
        collect_fn=collect_fn,
        trim_fn=trim_fn,
    )


def _function_node(tree, name):
    return next(
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == name
    )


def _called_names(function):
    names = set()
    for call in (node for node in ast.walk(function) if isinstance(node, ast.Call)):
        if isinstance(call.func, ast.Name):
            names.add(call.func.id)
        elif isinstance(call.func, ast.Attribute):
            names.add(call.func.attr)
    return names


def test_two_simultaneous_threshold_callers_run_one_collect_and_one_trim():
    calls, results = _overlapping_attempts(force=False)

    assert calls == {"collect": 1, "trim": 1}
    assert sum(bool(result["executed"]) for result in results) == 1
    skipped = next(result for result in results if result["skipped"])
    assert skipped["skip_reason"] == "gc_completed_while_waiting"
    assert skipped["rss_recheck_mb"] == 700.0
    assert skipped["current_generation"] > skipped["entry_generation"]


def test_two_simultaneous_force_callers_share_one_attempt():
    calls, results = _overlapping_attempts(force=True)

    assert calls == {"collect": 1, "trim": 1}
    assert sum(bool(result["executed"]) for result in results) == 1
    skipped = next(result for result in results if result["skipped"])
    assert skipped["skip_reason"] == "gc_completed_while_waiting"


def test_new_force_after_completed_attempt_can_run_again():
    coordinator = MemoryGCCoordinator()
    calls = {"collect": 0, "trim": 0}

    def collect_fn():
        calls["collect"] += 1
        return calls["collect"]

    def trim_fn():
        calls["trim"] += 1

    first = _coordinate_once(
        coordinator,
        force=True,
        rss=100.0,
        collect_fn=collect_fn,
        trim_fn=trim_fn,
    )
    second = _coordinate_once(
        coordinator,
        force=True,
        rss=100.0,
        collect_fn=collect_fn,
        trim_fn=trim_fn,
    )

    assert first["executed"] is True
    assert second["executed"] is True
    assert calls == {"collect": 2, "trim": 2}


def test_new_threshold_caller_runs_if_rss_remains_high():
    coordinator = MemoryGCCoordinator()
    calls = {"collect": 0, "trim": 0}

    def collect_fn():
        calls["collect"] += 1
        return 1

    def trim_fn():
        calls["trim"] += 1

    first = _coordinate_once(
        coordinator,
        force=False,
        rss=950.0,
        collect_fn=collect_fn,
        trim_fn=trim_fn,
    )
    second = _coordinate_once(
        coordinator,
        force=False,
        rss=950.0,
        collect_fn=collect_fn,
        trim_fn=trim_fn,
    )

    assert first["executed"] is True
    assert second["executed"] is True
    assert first["current_generation"] == 1
    assert second["entry_generation"] == 1
    assert second["current_generation"] == 2
    assert calls == {"collect": 2, "trim": 2}


def test_collect_exception_releases_lock_and_preserves_exception_policy():
    coordinator = MemoryGCCoordinator()

    def failing_collect():
        raise RuntimeError("collect failed")

    try:
        _coordinate_once(
            coordinator,
            force=True,
            rss=950.0,
            collect_fn=failing_collect,
            trim_fn=lambda: None,
        )
    except RuntimeError as exc:
        assert str(exc) == "collect failed"
    else:  # pragma: no cover - assertion aid
        raise AssertionError("collect exception was unexpectedly swallowed")

    result = _coordinate_once(
        coordinator,
        force=True,
        rss=950.0,
        collect_fn=lambda: 7,
        trim_fn=lambda: None,
    )
    assert result["executed"] is True
    assert result["collected"] == 7
    assert result["current_generation"] == 1


def test_trim_exception_is_nonfatal_and_does_not_leave_lock_held():
    coordinator = MemoryGCCoordinator()
    trim_calls = {"count": 0}

    def trim_fn():
        trim_calls["count"] += 1
        if trim_calls["count"] == 1:
            raise RuntimeError("trim unavailable")

    first = _coordinate_once(
        coordinator,
        force=True,
        rss=950.0,
        collect_fn=lambda: 3,
        trim_fn=trim_fn,
    )
    second = _coordinate_once(
        coordinator,
        force=True,
        rss=950.0,
        collect_fn=lambda: 4,
        trim_fn=trim_fn,
    )

    assert first["executed"] is True
    assert first["trim_succeeded"] is False
    assert first["trim_error"] == "RuntimeError"
    assert second["executed"] is True
    assert second["current_generation"] == 2


def test_rss_recheck_below_threshold_skips_without_cleanup():
    coordinator = MemoryGCCoordinator()
    result = coordinator.coordinate(
        reason="memory_loop",
        force=False,
        threshold_mb=900.0,
        rss_before_mb=925.0,
        current_rss_fn=lambda: 800.0,
        collect_fn=lambda: (_ for _ in ()).throw(AssertionError("collect called")),
        trim_fn=lambda: (_ for _ in ()).throw(AssertionError("trim called")),
    )

    assert result["executed"] is False
    assert result["skipped"] is True
    assert result["skip_reason"] == "rss_below_threshold_after_lock"


def test_automatic_main_callers_and_profiler_import_the_same_coordinator():
    force_gc = _function_node(MAIN_TREE, "force_gc_if_needed")
    memory_loop = _function_node(MAIN_TREE, "memory_monitor_loop")
    watchdog_loop = _function_node(MAIN_TREE, "central_watchdog_loop")
    cleanup = _function_node(MAIN_TREE, "_memory_cleanup")
    profiler_gc = _function_node(PROFILER_TREE, "_run_gc_if_needed")

    assert "coordinate_memory_gc" in _called_names(force_gc)
    assert "coordinate_memory_gc" in _called_names(cleanup)
    assert "force_gc_if_needed" in _called_names(memory_loop)
    assert "force_gc_if_needed" in _called_names(watchdog_loop)
    assert "coordinate_memory_gc" in _called_names(profiler_gc)
    assert memory_profiler.coordinate_memory_gc is coordinator_module.coordinate_memory_gc

    for tree in (MAIN_TREE, PROFILER_TREE):
        imports = [
            node
            for node in tree.body
            if isinstance(node, ast.ImportFrom)
            and node.module == "memory_gc_coordinator"
        ]
        assert len(imports) == 1
        assert "coordinate_memory_gc" in {
            alias.name for alias in imports[0].names
        }


def test_profiler_preserves_snapshot_action_shape_when_coordination_skips():
    coordination = {
        "reason": "memory_profiler:scheduled",
        "qualified": True,
        "executed": False,
        "skipped": True,
        "skip_reason": "gc_completed_while_waiting",
        "collected": None,
    }
    with (
        patch.object(memory_profiler, "coordinate_memory_gc", return_value=coordination) as coordinate,
        patch.object(memory_profiler, "emit_memory_gc_skipped", return_value=True) as emit,
    ):
        result = memory_profiler._run_gc_if_needed(
            {"rss_mb": 950.0},
            force=False,
            reason="scheduled",
        )

    assert result == {
        "executed": False,
        "collected": None,
        "threshold_mb": memory_profiler.GC_THRESHOLD_MB,
        "skip_reason": "gc_completed_while_waiting",
    }
    assert coordinate.call_args.kwargs["reason"] == "memory_profiler:scheduled"
    emit.assert_called_once()


def test_memory_gc_skipped_log_is_scalar_only_and_has_runtime_identity():
    coordinator = MemoryGCCoordinator()
    result = coordinator.coordinate(
        reason="memory_loop",
        force=False,
        threshold_mb=900.0,
        rss_before_mb=925.0,
        current_rss_fn=lambda: 800.0,
        collect_fn=lambda: None,
        trim_fn=lambda: None,
    )

    output = io.StringIO()
    with redirect_stdout(output):
        emitted = emit_memory_gc_skipped(
            result,
            emit_fn=emit_memory_source_observation,
        )

    rendered = output.getvalue()
    assert emitted is True
    assert rendered.startswith("MEMORY GC SKIPPED | sampled_at=")
    for field in (
        "reason=memory_loop",
        "skip_reason=rss_below_threshold_after_lock",
        "rss_before_mb=925.0",
        "rss_recheck_mb=800.0",
        "waited_ms=",
        "entry_generation=0",
        "current_generation=0",
        "pid=",
        "ppid=",
        "thread=",
        "boot_id=",
    ):
        assert field in rendered
    assert "{" not in rendered
    assert "[" not in rendered


def test_skipped_observability_is_fail_open_and_unqualified_callers_are_silent():
    def failing_emitter(*_args, **_kwargs):
        raise RuntimeError("logger failed")

    assert emit_memory_gc_skipped(
        {"qualified": True, "skipped": True},
        emit_fn=failing_emitter,
    ) is False
    assert emit_memory_gc_skipped(
        {"qualified": False, "skipped": False},
        emit_fn=failing_emitter,
    ) is False


def test_coordinator_adds_no_cooldown_or_sleep():
    source = (ROOT / "memory_gc_coordinator.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    sleep_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "sleep"
    ]

    assert sleep_calls == []
    assert "cooldown" not in source.lower()
