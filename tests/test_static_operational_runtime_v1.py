from __future__ import annotations

import ast
import importlib
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _fresh_policy(monkeypatch, value=None):
    monkeypatch.delenv("CENTRAL_STATIC_OPERATIONAL_RUNTIME_ENABLED", raising=False)
    if value is not None:
        monkeypatch.setenv("CENTRAL_STATIC_OPERATIONAL_RUNTIME_ENABLED", value)
    sys.modules.pop("static_operational_runtime", None)
    return importlib.import_module("static_operational_runtime")


def _function_nodes(relative_path: str, *names: str):
    tree = ast.parse((ROOT / relative_path).read_text(encoding="utf-8"))
    selected = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    assert {node.name for node in selected} == set(names)
    return selected


def _load_functions(relative_path: str, names: set[str], namespace: dict):
    nodes = _function_nodes(relative_path, *names)
    for node in nodes:
        node.decorator_list = []
    module = ast.Module(body=nodes, type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, relative_path, "exec"), namespace)
    return namespace


def test_default_is_current_runtime_and_static_health_is_config_only(monkeypatch):
    policy = _fresh_policy(monkeypatch)
    assert policy.static_operational_runtime_enabled() is False
    assert policy.historical_background_tasks_allowed() is True
    assert policy.heavy_predator_watchdog_audit_allowed() is True
    assert policy.auto_learning_runtime_allowed() is True
    assert policy.large_redis_snapshot_allowed() is True
    assert policy.static_operational_runtime_health() == {
        "static_operational_runtime_enabled": False,
        "operational_runtime_profile": "DEFAULT",
        "historical_background_tasks_enabled": True,
        "predator_heavy_watchdog_audit_enabled": True,
        "auto_learning_runtime_enabled": True,
        "smartpredator_large_redis_snapshot_enabled": True,
        "manual_heavy_audits_available": True,
    }


@pytest.mark.parametrize("value", ["1", "true", "yes", "sim", "on", " TRUE "])
def test_accepted_values_enable_static_mode(monkeypatch, value):
    policy = _fresh_policy(monkeypatch, value)
    assert policy.static_operational_runtime_enabled() is True
    assert policy.historical_background_tasks_allowed() is False
    assert policy.heavy_predator_watchdog_audit_allowed() is False
    assert policy.auto_learning_runtime_allowed() is False
    assert policy.large_redis_snapshot_allowed() is False
    assert policy.static_operational_runtime_health() == {
        "static_operational_runtime_enabled": True,
        "operational_runtime_profile": "STATIC_OPERATIONAL",
        "historical_background_tasks_enabled": False,
        "predator_heavy_watchdog_audit_enabled": False,
        "auto_learning_runtime_enabled": False,
        "smartpredator_large_redis_snapshot_enabled": False,
        "manual_heavy_audits_available": True,
    }


@pytest.mark.parametrize("value", ["", "0", "false", "no", "off", "enabled", "invalid"])
def test_invalid_values_fail_safe_to_current_runtime(monkeypatch, value):
    policy = _fresh_policy(monkeypatch, value)
    assert policy.static_operational_runtime_enabled() is False


def test_environment_evaluation_error_fails_safe_to_current_runtime(monkeypatch):
    policy = _fresh_policy(monkeypatch)

    class BrokenEnvironment:
        def get(self, *_args, **_kwargs):
            raise RuntimeError("environment unavailable")

    assert policy._environment_enabled(
        "CENTRAL_STATIC_OPERATIONAL_RUNTIME_ENABLED",
        environment=BrokenEnvironment(),
    ) is False


def test_blocked_logs_are_rate_limited_per_task(monkeypatch):
    policy = _fresh_policy(monkeypatch, "true")
    policy.reset_static_operational_runtime_log_state()
    assert policy.static_operational_runtime_should_log_blocked("predator_heavy", now=10) is True
    assert policy.static_operational_runtime_should_log_blocked("predator_heavy", now=11) is False
    assert policy.static_operational_runtime_should_log_blocked("redis_snapshot", now=11) is True
    assert policy.static_operational_runtime_should_log_blocked("predator_heavy", now=3610) is True
    assert policy.static_operational_runtime_blocked_log("predator_heavy", "watchdog") == (
        "STATIC_OPERATIONAL_RUNTIME_BLOCKED task=predator_heavy "
        "origin=watchdog reason=STATIC_OPERATIONAL_RUNTIME"
    )


def _run_watchdog_once(heavy_allowed: bool):
    calls = {"tick": 0, "blocked": []}
    namespace = {
        "heavy_predator_watchdog_audit_allowed": lambda: heavy_allowed,
        "_emit_static_operational_runtime_blocked": lambda task, origin: calls[
            "blocked"
        ].append((task, origin)),
        "predator_auto_closed_sync_v1_tick": lambda: calls.__setitem__(
            "tick", calls["tick"] + 1
        ),
    }
    watchdog = _function_nodes("main.py", "central_watchdog_loop")[0]
    watchdog_try = watchdog.body[0].body[0]
    gate_index = next(
        index
        for index, statement in enumerate(watchdog_try.body)
        if isinstance(statement, ast.If)
        and ast.unparse(statement.test) == "not heavy_audit_allowed"
    )
    wrapper = ast.FunctionDef(
        name="run_watchdog_heavy_audit_gate",
        args=ast.arguments(
            posonlyargs=[], args=[], kwonlyargs=[], kw_defaults=[], defaults=[]
        ),
        body=watchdog_try.body[gate_index - 2 : gate_index + 1],
        decorator_list=[],
    )
    module = ast.Module(body=[wrapper], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, "main.py", "exec"), namespace)
    namespace["run_watchdog_heavy_audit_gate"]()
    return calls


def test_watchdog_keeps_current_automatic_tick_when_static_mode_is_off():
    calls = _run_watchdog_once(heavy_allowed=True)
    assert calls == {"tick": 1, "blocked": []}


def test_watchdog_does_not_enter_predator_historical_audit_when_static_mode_is_on():
    calls = _run_watchdog_once(heavy_allowed=False)
    assert calls == {
        "tick": 0,
        "blocked": [("predator_heavy_watchdog_audit", "central_watchdog_loop")],
    }


def test_auto_closed_tick_has_its_own_static_guard_before_any_audit_reader():
    blocked = []
    namespace = {
        "heavy_predator_watchdog_audit_allowed": lambda: False,
        "_emit_static_operational_runtime_blocked": lambda task, origin: blocked.append(
            (task, origin)
        ),
        "PREDATOR_AUTO_CLOSED_SYNC_V1_ENABLED": True,
        "predator_auto_closed_sync_v1_status": lambda **_kwargs: pytest.fail(
            "historical audit was entered"
        ),
    }
    _load_functions("main.py", {"predator_auto_closed_sync_v1_tick"}, namespace)
    result = namespace["predator_auto_closed_sync_v1_tick"]()
    assert result["status"] == "STATIC_OPERATIONAL_RUNTIME_BLOCKED"
    assert blocked == [
        ("predator_heavy_watchdog_audit", "predator_auto_closed_sync_v1_tick")
    ]


def test_health_merges_static_policy_without_files_redis_or_broker_calls():
    forbidden_calls = []

    def forbidden(name):
        return lambda *_args, **_kwargs: forbidden_calls.append(name) or pytest.fail(name)

    namespace = {
        "central_trade_registry_snapshot": lambda **_kwargs: {"ok": True},
        "automatic_daily_summaries_health": lambda: {},
        "telegram_notification_policy_health": lambda: {},
        "automatic_learning_refresh_health": lambda **_kwargs: {},
        "static_operational_runtime_health": lambda: {
            "static_operational_runtime_enabled": True,
            "operational_runtime_profile": "STATIC_OPERATIONAL",
            "historical_background_tasks_enabled": False,
            "predator_heavy_watchdog_audit_enabled": False,
            "auto_learning_runtime_enabled": False,
            "smartpredator_large_redis_snapshot_enabled": False,
            "manual_heavy_audits_available": True,
        },
        "LEARNING_AUTO_REFRESH_SECONDS": 900,
        "LEARNING_AUTO_REFRESH_MIN_SECONDS": 300,
        "LEARNING_AUTO_REFRESH_THREAD_STARTED": False,
        "LEARNING_AUTO_REFRESH_LEGACY_ENABLED": False,
        "build_disk_forensics_health": None,
        "STARTUP_DISK_FORENSICS_RESULT": {},
        "TIMELINE_EMERGENCY_RECOVERY_RESULT": {},
        "load_events": forbidden("history"),
        "open": forbidden("file"),
        "redis": forbidden("redis"),
        "broker": forbidden("broker"),
    }
    _load_functions("main.py", {"health"}, namespace)
    result = namespace["health"]()
    assert result["health_profile"] == "LIGHT"
    assert result["history_files_read"] is False
    assert result["redis_called"] is False
    assert result["broker_called"] is False
    assert result["write_executed"] is False
    assert result["operational_runtime_profile"] == "STATIC_OPERATIONAL"
    assert result["manual_heavy_audits_available"] is True
    assert forbidden_calls == []


def test_static_runtime_preserves_minimal_event_journal_but_skips_redis_trade_snapshot():
    calls = {"journal": [], "redis_get": 0, "redis_set": []}
    namespace = {
        "append_predator_event": lambda event: calls["journal"].append(event) or {"ok": True},
        "HEALTH": {},
        "large_redis_snapshot_allowed": lambda: False,
        "static_operational_runtime_should_log_blocked": lambda _task: True,
        "static_operational_runtime_blocked_log": lambda task, origin: f"{task}:{origin}",
        "print": lambda *_args: None,
        "carregar_trades": lambda: calls.__setitem__("redis_get", calls["redis_get"] + 1),
        "redis_set_json": lambda key, value: calls["redis_set"].append((key, value)),
        "TRADES_KEY": "smartpredator:trades",
    }
    _load_functions(
        "bots/predator.py",
        {
            "salvar_trades",
            "_predator_static_operational_runtime_blocked",
            "registrar_evento_trade",
        },
        namespace,
    )
    namespace["registrar_evento_trade"]({"event": "TP50"})
    assert calls == {"journal": [{"event": "TP50"}], "redis_get": 0, "redis_set": []}
    assert namespace["salvar_trades"]([], automatic=True) is False
    assert namespace["salvar_trades"]([], automatic=False) is True
    assert calls["redis_set"] == [("smartpredator:trades", [])]


def _predator_salvar_trades_callers():
    tree = ast.parse((ROOT / "bots/predator.py").read_text(encoding="utf-8"))
    callers = {}
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        calls = [
            call
            for call in ast.walk(node)
            if isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id == "salvar_trades"
        ]
        if calls:
            callers[node.name] = calls
    return callers


def test_all_predator_salvar_trades_callers_are_explicitly_classified():
    callers = _predator_salvar_trades_callers()
    assert set(callers) == {"registrar_evento_trade", "resetar_estado_operacional"}

    automatic_call = callers["registrar_evento_trade"]
    assert len(automatic_call) == 1
    automatic_keyword = next(
        (keyword for keyword in automatic_call[0].keywords if keyword.arg == "automatic"),
        None,
    )
    assert automatic_keyword is not None
    assert isinstance(automatic_keyword.value, ast.Constant)
    assert automatic_keyword.value.value is True

    manual_call = callers["resetar_estado_operacional"]
    assert len(manual_call) == 1
    assert all(keyword.arg != "automatic" for keyword in manual_call[0].keywords)


def test_manual_audit_json_and_text_routes_remain_available_and_identified():
    expected_routes = {
        "predator_pnl_paper_audit_v1": (
            "predator_pnl_paper_audit_v1_route",
            "/predator/pnlaudit",
            "predator_pnl_paper_audit_v1_text_route",
            "/predator/pnlaudit/text",
            "build_predator_pnl_paper_audit_v1_text",
        ),
        "predator_paper_lifecycle_audit_v1": (
            "predator_paper_lifecycle_audit_v1_route",
            "/predator/lifecycleaudit",
            "predator_paper_lifecycle_audit_v1_text_route",
            "/predator/lifecycleaudit/text",
            "build_predator_paper_lifecycle_audit_v1_text",
        ),
        "predator_auto_closed_sync_v1": (
            "predator_auto_closed_sync_v1_route",
            "/predator/autoclosedsync",
            "predator_auto_closed_sync_v1_text_route",
            "/predator/autoclosedsync/text",
            "build_predator_auto_closed_sync_v1_text",
        ),
    }
    tree = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))
    functions = {
        node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)
    }

    for (
        _name,
        (json_route, json_path, text_route, text_path, text_builder),
    ) in expected_routes.items():
        json_source = ast.unparse(functions[json_route])
        text_route_source = ast.unparse(functions[text_route])
        text_builder_source = ast.unparse(functions[text_builder])
        assert json_path in json_source
        assert "MANUAL_HEAVY_AUDIT" in json_source
        assert "manual_heavy_audit" in json_source
        assert text_path in text_route_source
        assert "text/plain" in text_route_source
        assert "MANUAL_HEAVY_AUDIT" in text_builder_source


def test_static_runtime_blocks_only_automatic_historical_summary_loops():
    cases = {
        "central_daily_report_loop": "central_daily_historical_report",
        "trendpro_daily_summary_v1_loop": "trendpro_daily_historical_summary",
    }
    for function_name, task in cases.items():
        blocked = []
        namespace = {
            "historical_background_tasks_allowed": lambda: False,
            "_emit_static_operational_runtime_blocked": lambda event, origin: blocked.append(
                (event, origin)
            ),
        }
        _load_functions("main.py", {function_name}, namespace)
        assert namespace[function_name]() is None
        assert blocked == [(task, function_name)]


def test_historical_scheduler_startup_is_gated_but_manual_summary_routes_are_not():
    startup = ast.unparse(_function_nodes("main.py", "start_central_runtime_once")[0])
    assert "historical_background_allowed = historical_background_tasks_allowed()" in startup
    assert "central_daily_historical_report" in startup
    assert "trendpro_daily_historical_summary" in startup

    for route in (
        "learning_refresh_route",
        "trendpro_daily_summary_v1_route",
        "trendpro_daily_summary_v1_text_route",
    ):
        assert "historical_background_tasks_allowed" not in ast.unparse(
            _function_nodes("main.py", route)[0]
        )


def test_manual_predator_audits_remain_explicit_and_operational_management_is_ungated():
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    for route in (
        "predator_pnl_paper_audit_v1_route",
        "predator_paper_lifecycle_audit_v1_route",
        "predator_auto_closed_sync_v1_route",
    ):
        node = _function_nodes("main.py", route)[0]
        body = ast.unparse(node)
        assert "MANUAL_HEAVY_AUDIT" in body
        assert "manual_heavy_audit" in body
    predator_tree = ast.parse((ROOT / "bots/predator.py").read_text(encoding="utf-8"))
    management = next(
        node
        for node in predator_tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "gerenciar_posicoes"
    )
    close_position = next(
        node
        for node in predator_tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "encerrar_posicao"
    )
    management_source = ast.unparse(management)
    assert "large_redis_snapshot_allowed" not in management_source
    assert "static_operational_runtime" not in management_source
    assert "encerrar_posicao" in management_source
    assert "registrar_trade_registry_close_predator" in ast.unparse(close_position)


def test_policy_module_is_pure_and_has_no_external_runtime_dependencies():
    source = (ROOT / "static_operational_runtime.py").read_text(encoding="utf-8")
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
    assert imports == {"os", "time"}
    assert imports_from == set()
    lower_source = source.lower()
    assert all(
        forbidden not in lower_source
        for forbidden in (
            "import broker",
            "from broker",
            "import redis",
            "from redis",
            "import telegram",
            "from telegram",
            "import requests",
            "from requests",
        )
    )
