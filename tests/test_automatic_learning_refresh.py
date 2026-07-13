from __future__ import annotations

import ast
import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _fresh_policy(monkeypatch, value=None):
    monkeypatch.delenv("CENTRAL_AUTO_LEARNING_REFRESH_ENABLED", raising=False)
    if value is not None:
        monkeypatch.setenv("CENTRAL_AUTO_LEARNING_REFRESH_ENABLED", value)
    sys.modules.pop("automatic_learning_policy", None)
    return importlib.import_module("automatic_learning_policy")


def _function_node(name: str) -> ast.FunctionDef:
    tree = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))
    return next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    )


def _compile_function(node: ast.FunctionDef, namespace: dict):
    node.decorator_list = []
    module = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, "<isolated-main-function>", "exec"), namespace)
    return namespace[node.name]


def _startup_learning_gate() -> ast.If:
    startup = _function_node("start_central_runtime_once")
    return next(
        node
        for node in ast.walk(startup)
        if isinstance(node, ast.If)
        and ast.unparse(node.test) == "LEARNING_AUTO_REFRESH_ENABLED"
    )


def _run_startup_learning_gate(enabled: bool, lock_result=True):
    gate = _startup_learning_gate()
    wrapper = ast.FunctionDef(
        name="run_learning_startup_gate",
        args=ast.arguments(
            posonlyargs=[], args=[], kwonlyargs=[], kw_defaults=[], defaults=[]
        ),
        body=[ast.Global(names=["LEARNING_AUTO_REFRESH_THREAD_STARTED"]), gate],
        decorator_list=[],
    )
    calls = {"lock": 0, "thread": 0, "start": 0, "logs": []}

    class FakeThread:
        def start(self):
            calls["start"] += 1

    def acquire_lock(name):
        calls["lock"] += 1
        assert name == "learning_auto_refresh"
        return lock_result

    def make_thread(*, target, daemon):
        calls["thread"] += 1
        assert target is namespace["learning_auto_refresh_loop"]
        assert daemon is True
        return FakeThread()

    namespace = {
        "LEARNING_AUTO_REFRESH_ENABLED": enabled,
        "LEARNING_AUTO_REFRESH_THREAD_STARTED": False,
        "learning_auto_refresh_loop": lambda: None,
        "acquire_runtime_file_lock": acquire_lock,
        "threading": SimpleNamespace(Thread=make_thread),
        "print": lambda message: calls["logs"].append(message),
    }
    _compile_function(wrapper, namespace)()
    calls["thread_started"] = namespace["LEARNING_AUTO_REFRESH_THREAD_STARTED"]
    return calls


def test_flag_absent_is_false(monkeypatch):
    policy = _fresh_policy(monkeypatch)
    assert policy.CENTRAL_AUTO_LEARNING_REFRESH_ENABLED is False
    assert policy.automatic_learning_refresh_enabled() is False


@pytest.mark.parametrize("value", ["false", "0", "no", "off", "", "enabled", "y"])
def test_false_and_invalid_values_remain_false(monkeypatch, value):
    policy = _fresh_policy(monkeypatch, value)
    assert policy.CENTRAL_AUTO_LEARNING_REFRESH_ENABLED is False


@pytest.mark.parametrize("value", ["1", "true", "yes", "sim", "on", " TRUE "])
def test_explicit_true_values_enable_policy(monkeypatch, value):
    policy = _fresh_policy(monkeypatch, value)
    assert policy.CENTRAL_AUTO_LEARNING_REFRESH_ENABLED is True
    assert policy.automatic_learning_refresh_enabled() is True


def test_legacy_disable_remains_respected(monkeypatch):
    policy = _fresh_policy(monkeypatch, "true")
    assert policy.automatic_learning_refresh_enabled(legacy_enabled=False) is False


def test_disabled_health_is_lightweight_and_truthful(monkeypatch):
    policy = _fresh_policy(monkeypatch)
    assert policy.automatic_learning_refresh_health(interval_seconds=900) == {
        "auto_learning_refresh_enabled": False,
        "auto_learning_refresh_thread_started": False,
        "auto_learning_refresh_manual_available": True,
        "auto_learning_refresh_interval_seconds": 900,
        "auto_learning_refresh_disabled_reason": "DISABLED_BY_POLICY",
    }


def test_policy_module_is_pure_and_imports_only_os():
    source = (ROOT / "automatic_learning_policy.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = {
        alias.name
        for node in tree.body
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imports_from = {
        node.module
        for node in tree.body
        if isinstance(node, ast.ImportFrom) and node.module != "__future__"
    }
    assert imports == {"os"}
    assert imports_from == set()
    for forbidden in (
        "learning_engine",
        "trade_registry",
        "broker",
        "redis",
        "requests",
        "threading",
    ):
        assert forbidden not in source.lower()


def test_disabled_startup_does_not_acquire_lock_or_create_thread():
    calls = _run_startup_learning_gate(enabled=False)
    assert calls == {
        "lock": 0,
        "thread": 0,
        "start": 0,
        "logs": ["LEARNING AUTO REFRESH DESABILITADO — policy default false"],
        "thread_started": False,
    }


def test_enabled_startup_preserves_existing_thread_creation():
    calls = _run_startup_learning_gate(enabled=True)
    assert calls["lock"] == 1
    assert calls["thread"] == 1
    assert calls["start"] == 1
    assert calls["thread_started"] is True
    assert calls["logs"] == []


def test_disabled_loop_returns_before_learning_import_readers_writes_or_sleep():
    node = _function_node("learning_auto_refresh_loop")

    def forbidden(*args, **kwargs):
        raise AssertionError("disabled automatic learning touched heavy work")

    namespace = {
        "LEARNING_AUTO_REFRESH_ENABLED": False,
        "LEARNING_AUTO_REFRESH_SECONDS": 900,
        "LEARNING_AUTO_REFRESH_MIN_SECONDS": 300,
        "time": SimpleNamespace(sleep=forbidden),
        "__builtins__": {"__import__": forbidden},
    }
    result = _compile_function(node, namespace)()
    assert result is None


def test_enabled_loop_keeps_current_interval_and_refresh_call():
    node = _function_node("learning_auto_refresh_loop")
    source = ast.unparse(node)
    assert "max(LEARNING_AUTO_REFRESH_SECONDS, LEARNING_AUTO_REFRESH_MIN_SECONDS)" in source
    assert "time.sleep(interval)" in source
    refresh_calls = [
        child
        for child in ast.walk(node)
        if isinstance(child, ast.Call)
        and isinstance(child.func, ast.Attribute)
        and child.func.attr == "refresh_state"
    ]
    assert len(refresh_calls) == 1
    assert any(
        keyword.arg == "reason"
        and isinstance(keyword.value, ast.Constant)
        and keyword.value.value == "auto_loop"
        for keyword in refresh_calls[0].keywords
    )


def test_manual_refresh_endpoint_still_calls_learning_explicitly(monkeypatch):
    calls = []
    fake_learning = SimpleNamespace(
        refresh_state=lambda reason: calls.append(reason)
        or {"ok": True, "summary": {"trades": 1}, "readiness": {"level": "TEST"}}
    )
    monkeypatch.setitem(sys.modules, "learning_engine", fake_learning)
    state = {"ts": None, "ok": None, "error": None, "summary": None, "readiness": None}
    namespace = {
        "LEARNING_AUTO_REFRESH_LAST": state,
        "data_hora_sp_str": lambda: "13/07/2026 12:00",
    }
    result = _compile_function(_function_node("learning_refresh_route"), namespace)()
    assert calls == ["manual_route"]
    assert result["ok"] is True
    assert state["ok"] is True


def test_manual_learning_and_policy_surfaces_remain_present():
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    for marker in (
        '@app.route("/learning")',
        '@app.route("/learning/refresh")',
        '@app.route("/learning/status")',
        '@app.route("/learning/readiness")',
        '@app.route("/policylearning", methods=["GET"])',
        '@app.route("/policyeffect", methods=["GET"])',
        '@app.route("/policyeffectrebuild", methods=["GET"])',
        '@app.route("/policylearningseed", methods=["GET"])',
    ):
        assert marker in source


def test_main_health_only_merges_lightweight_learning_contract():
    expected = {
        "auto_learning_refresh_enabled": False,
        "auto_learning_refresh_thread_started": False,
        "auto_learning_refresh_manual_available": True,
        "auto_learning_refresh_interval_seconds": 900,
        "auto_learning_refresh_disabled_reason": "DISABLED_BY_POLICY",
    }
    calls = []
    forbidden_calls = []

    def forbidden(name):
        return lambda *args, **kwargs: forbidden_calls.append(name) or pytest.fail(
            f"health attempted forbidden operation: {name}"
        )

    disk = {
        "disk_forensics_available": False,
        "disk_forensics_usage_pct": None,
        "disk_forensics_free_mb": None,
        "disk_forensics_partial": None,
        "disk_forensics_largest_file": None,
        "disk_forensics_largest_file_mb": None,
    }
    timeline = {
        "timeline_emergency_recovery_enabled": False,
        "timeline_emergency_recovery_status": "DISABLED",
    }
    namespace = {
        "central_watchdog_status": lambda: {"ok": True},
        "central_trade_registry_snapshot": lambda include_trades=False: {"ok": True},
        "automatic_daily_summaries_health": lambda: {},
        "automatic_learning_refresh_health": lambda **kwargs: calls.append(kwargs)
        or expected.copy(),
        "LEARNING_AUTO_REFRESH_SECONDS": 900,
        "LEARNING_AUTO_REFRESH_MIN_SECONDS": 300,
        "LEARNING_AUTO_REFRESH_THREAD_STARTED": False,
        "LEARNING_AUTO_REFRESH_LEGACY_ENABLED": True,
        "build_disk_forensics_health": lambda cached: disk.copy(),
        "STARTUP_DISK_FORENSICS_RESULT": {"ok": False},
        "build_timeline_emergency_recovery_health": lambda cached: timeline.copy(),
        "TIMELINE_EMERGENCY_RECOVERY_RESULT": {"enabled": False},
        "load_events": forbidden("history_events"),
        "iter_jsonl_tail": forbidden("iter_jsonl_tail"),
        "open": forbidden("filesystem"),
        "redis": forbidden("redis"),
        "socket": forbidden("network"),
    }
    result = _compile_function(_function_node("health"), namespace)()
    assert calls == [
        {"interval_seconds": 900, "thread_started": False, "legacy_enabled": True}
    ]
    for key, value in expected.items():
        assert result[key] == value
    for key, value in {**disk, **timeline}.items():
        assert result[key] == value
    assert forbidden_calls == []


def test_auto_status_is_lightweight_and_does_not_run_learning():
    namespace = {
        "LEARNING_AUTO_REFRESH_ENABLED": False,
        "LEARNING_AUTO_REFRESH_SECONDS": 900,
        "LEARNING_AUTO_REFRESH_MIN_SECONDS": 300,
        "LEARNING_AUTO_REFRESH_LAST": {"ts": None},
        "LEARNING_AUTO_REFRESH_THREAD_STARTED": False,
        "LEARNING_AUTO_REFRESH_LEGACY_ENABLED": True,
        "automatic_learning_refresh_health": lambda **kwargs: {
            "auto_learning_refresh_enabled": False,
            "auto_learning_refresh_thread_started": False,
            "auto_learning_refresh_manual_available": True,
            "auto_learning_refresh_interval_seconds": kwargs["interval_seconds"],
            "auto_learning_refresh_disabled_reason": "DISABLED_BY_POLICY",
        },
    }
    result = _compile_function(_function_node("learning_auto_status_route"), namespace)()
    assert result["auto_learning_refresh_enabled"] is False
    assert result["auto_learning_refresh_thread_started"] is False
    assert result["auto_learning_refresh_manual_available"] is True
    assert result["auto_learning_refresh_interval_seconds"] == 900


def test_no_independent_heavy_learning_threads_exist():
    for relative_path in (
        "learning_engine.py",
        "executive_policy_learning.py",
        "adaptive_weights.py",
        "outcome_evaluator.py",
    ):
        source = (ROOT / relative_path).read_text(encoding="utf-8")
        assert "threading.Thread" not in source
        assert "Thread(" not in source


def test_gate_precedes_learning_lock_and_thread_in_main():
    gate_node = _startup_learning_gate()
    gate = ast.unparse(gate_node)
    assert gate.startswith("if LEARNING_AUTO_REFRESH_ENABLED:")
    calls = [node for node in ast.walk(gate_node) if isinstance(node, ast.Call)]
    lock_call = next(
        call
        for call in calls
        if isinstance(call.func, ast.Name)
        and call.func.id == "acquire_runtime_file_lock"
    )
    thread_call = next(
        call
        for call in calls
        if isinstance(call.func, ast.Attribute)
        and call.func.attr == "Thread"
    )
    assert lock_call.lineno < thread_call.lineno


def test_operational_and_live_modules_are_not_gated_by_learning_policy():
    main_source = (ROOT / "main.py").read_text(encoding="utf-8")
    policy_name = "CENTRAL_AUTO_LEARNING_REFRESH_ENABLED"
    assert policy_name not in main_source
    for relative_path in (
        "trade_registry.py",
        "trade_lifecycle_manager.py",
        "trade_lifecycle_shadow_runtime_adapter.py",
        "execution_engine.py",
        "execution_orchestrator.py",
    ):
        assert policy_name not in (ROOT / relative_path).read_text(encoding="utf-8")
