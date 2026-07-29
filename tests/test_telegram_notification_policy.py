from __future__ import annotations

import ast
import builtins
import copy
from pathlib import Path
from types import SimpleNamespace

import pytest

import telegram_notification_policy as policy


ROOT = Path(__file__).resolve().parents[1]


def decide(**updates):
    payload = {
        "bot": "PREDATOR",
        "event_type": "SIGNAL",
        "mode": "PAPER",
        "environ": {},
    }
    payload.update(updates)
    return policy.should_send_automatic_telegram(**payload)


def test_flag_absent_defaults_to_live_only():
    assert policy.telegram_live_only_enabled({}) is True


@pytest.mark.parametrize("value", ["1", "true", "yes", "sim", "on", " TRUE "])
def test_true_values_enable_live_only(value):
    assert policy.telegram_live_only_enabled({"CENTRAL_TELEGRAM_LIVE_ONLY_ENABLED": value}) is True


def test_false_preserves_legacy_behavior():
    result = decide(environ={"CENTRAL_TELEGRAM_LIVE_ONLY_ENABLED": "false"})
    assert result["allowed"] is True
    assert result["reason"] == "LEGACY_POLICY_DISABLED"


def test_live_automatic_is_allowed():
    result = decide(mode="LIVE", event_type="LIVE_ORDER_SENT")
    assert result["allowed"] is True
    assert result["reason"] == "LIVE_OPERATIONAL_EVENT"


@pytest.mark.parametrize(
    "event_type",
    ["FALCON_STARTUP", "BOT_STARTUP", "FALCON_NOTIFICATION", "UNRECOGNIZED_LIVE_EVENT", None],
)
def test_live_informational_unknown_or_missing_event_is_blocked(event_type):
    result = decide(bot="FALCON", mode="LIVE", event_type=event_type)
    assert result["allowed"] is False
    assert result["reason"] == "LIVE_EVENT_NOT_ALLOWLISTED"


@pytest.mark.parametrize(
    "event_type",
    [
        "REAL_EXECUTION_SENT",
        "REAL_EXECUTION_BLOCKED",
        "DISASTER_STOP_FAILED",
        "TP50_LIVE",
        "BREAK_EVEN_LIVE",
        "TRAILING_UPDATED_LIVE",
        "LIVE_TRADE_CLOSED",
    ],
)
def test_recognized_live_operational_events_are_allowed(event_type):
    result = decide(bot="FALCON", mode="LIVE", event_type=event_type)
    assert result["allowed"] is True
    assert result["reason"] == "LIVE_OPERATIONAL_EVENT"


def test_operational_allowlist_covers_real_trade_lifecycle_contract():
    required = {
        "SIGNAL_LIVE_AUTHORIZED",
        "REAL_EXECUTION_SENT",
        "REAL_EXECUTION_SENT_ATTENTION",
        "REAL_EXECUTION_BLOCKED",
        "REAL_EXECUTION_FAILED_BEFORE_SEND",
        "FALCON_LIVE_PRE_ORDER_TELEGRAM",
        "FALCON_LIVE_POST_ORDER_AUDIT",
        "DISASTER_STOP_REQUESTED",
        "DISASTER_STOP_CREATED",
        "DISASTER_STOP_CONFIRMED",
        "DISASTER_STOP_FAILED",
        "TP50_LIVE",
        "PARTIAL_EXIT_LIVE",
        "BREAK_EVEN_LIVE",
        "TRAILING_STARTED_LIVE",
        "TRAILING_UPDATED_LIVE",
        "STOP_UPDATED_LIVE",
        "STOP_EXECUTED_LIVE",
        "LIVE_TRADE_CLOSED",
        "LIVE_MANAGEMENT_ERROR",
        "LIVE_POSITION_DIVERGENCE",
        "OWNERSHIP_ERROR",
        "BROKER_CRITICAL",
    }
    assert required <= policy.LIVE_OPERATIONAL_EVENT_TYPES
    assert {"FALCON_STARTUP", "BOT_STARTUP", "FALCON_NOTIFICATION"}.isdisjoint(
        policy.LIVE_OPERATIONAL_EVENT_TYPES
    )


@pytest.mark.parametrize("mode", ["PAPER", "VERIFY", "DRY_RUN", "SHADOW", "OBSERVATION_ONLY", None, "UNKNOWN"])
def test_non_live_automatic_is_blocked(mode):
    result = decide(mode=mode)
    assert result["allowed"] is False
    assert result["reason"] == "LIVE_ONLY_POLICY"


def test_central_ceo_daily_is_the_only_paper_summary_policy_exception():
    result = decide(
        bot="CENTRAL",
        event_type="CENTRAL_CEO_DAILY_SUMMARY",
        mode="PAPER",
    )
    assert result["allowed"] is True
    assert result["reason"] == "CENTRAL_CEO_DAILY_POLICY"
    assert result["central_ceo_daily_event"] is True

    calls = []
    sent = policy.send_automatic_telegram(
        lambda message: calls.append(message) or True,
        "ceo daily",
        bot="CENTRAL",
        event_type="CENTRAL_CEO_DAILY_SUMMARY",
        mode="PAPER",
        environ={},
    )
    assert sent["sent"] is True
    assert calls == ["ceo daily"]


@pytest.mark.parametrize("bot", ["FALCON", "PREDATOR", "TURTLE", "DONKEY", "COBRA", "MEME", "TRENDPRO"])
def test_bot_paper_daily_summaries_remain_blocked(bot):
    result = decide(bot=bot, event_type="AUTOMATIC_DAILY_SUMMARY", mode="PAPER")
    assert result["allowed"] is False
    assert result["reason"] == "LIVE_ONLY_POLICY"


def test_central_ceo_event_name_does_not_allow_another_bot():
    result = decide(
        bot="FALCON",
        event_type="CENTRAL_CEO_DAILY_SUMMARY",
        mode="PAPER",
    )
    assert result["allowed"] is False
    assert result["reason"] == "LIVE_ONLY_POLICY"


def test_manual_paper_is_allowed():
    result = decide(manual_command=True)
    assert result["allowed"] is True
    assert result["manual_override"] is True


@pytest.mark.parametrize("mode", ["PAPER", None])
def test_explicit_operational_critical_is_allowed(mode):
    result = decide(mode=mode, severity="CRITICAL", operational_critical=True)
    assert result["allowed"] is True
    assert result["critical_override"] is True


def test_severity_alone_does_not_override_policy():
    assert decide(severity="P0", operational_critical=False)["allowed"] is False


def test_operational_event_requires_live_mode_and_is_bot_agnostic():
    assert decide(bot="FALCON", mode="PAPER", event_type="REAL_EXECUTION_SENT")["allowed"] is False
    assert decide(bot="FALCON", mode="VERIFY", event_type="REAL_EXECUTION_SENT")["allowed"] is False
    assert decide(bot="PREDATOR", mode="LIVE", event_type="SIGNAL_LIVE_AUTHORIZED")["allowed"] is True


def test_flag_false_restores_legacy_falcon_startup():
    result = decide(
        bot="FALCON",
        mode="LIVE",
        event_type="FALCON_STARTUP",
        environ={"CENTRAL_TELEGRAM_LIVE_ONLY_ENABLED": "false"},
    )
    assert result["allowed"] is True
    assert result["reason"] == "LEGACY_POLICY_DISABLED"


def test_canonical_arguments_win_over_metadata_and_input_is_immutable():
    metadata = {"mode": "LIVE", "manual_command": True, "nested": [1]}
    original = copy.deepcopy(metadata)
    result = decide(mode="PAPER", manual_command=False, metadata=metadata)
    assert result["allowed"] is False
    assert result["mode"] == "PAPER"
    assert metadata == original


def test_send_helper_blocks_without_calling_transport():
    calls = []
    result = policy.send_automatic_telegram(
        lambda message: calls.append(message) or True,
        "secret message body",
        bot="TURTLE",
        event_type="SIGNAL_PAPER",
        mode="PAPER",
        environ={},
    )
    assert result["sent"] is False
    assert calls == []


def test_policy_logs_never_include_message_body(capsys):
    secret_body = "message-body-must-not-be-logged"
    policy.send_automatic_telegram(
        lambda _message: True,
        secret_body,
        bot="PREDATOR",
        event_type="SIGNAL_PAPER",
        mode="PAPER",
        environ={},
    )
    output = capsys.readouterr().out
    assert "TELEGRAM_NOTIFICATION_BLOCKED" in output
    assert secret_body not in output


def test_strict_live_logs_and_counters(capsys):
    before = policy.telegram_notification_policy_health({})
    sender = lambda _message: True
    policy.send_automatic_telegram(
        sender,
        "startup body",
        bot="FALCON",
        event_type="FALCON_STARTUP",
        mode="LIVE",
        environ={},
    )
    policy.send_automatic_telegram(
        sender,
        "unknown body",
        bot="FALCON",
        event_type="UNKNOWN_LIVE_EVENT",
        mode="LIVE",
        environ={},
    )
    policy.send_automatic_telegram(
        sender,
        "real body",
        bot="FALCON",
        event_type="REAL_EXECUTION_SENT",
        mode="LIVE",
        environ={},
    )
    after = policy.telegram_notification_policy_health({})
    assert after["telegram_auto_blocked_live_informational"] == before["telegram_auto_blocked_live_informational"] + 1
    assert after["telegram_auto_blocked_unknown_event"] == before["telegram_auto_blocked_unknown_event"] + 1
    assert after["telegram_auto_allowed_live_operational"] == before["telegram_auto_allowed_live_operational"] + 1
    output = capsys.readouterr().out
    assert "event_type=FALCON_STARTUP mode=LIVE reason=LIVE_EVENT_NOT_ALLOWLISTED" in output
    assert "event_type=REAL_EXECUTION_SENT mode=LIVE reason=LIVE_OPERATIONAL_EVENT" in output
    assert "startup body" not in output


def test_send_helper_allows_live_manual_and_critical():
    calls = []
    sender = lambda message: calls.append(message) or True
    cases = [
        {"mode": "LIVE", "event_type": "LIVE_ORDER_CONFIRMED"},
        {"mode": "PAPER", "event_type": "MANUAL_HEALTH", "manual_command": True},
        {"mode": None, "event_type": "OOM", "operational_critical": True},
    ]
    for item in cases:
        result = policy.send_automatic_telegram(
            sender,
            "body",
            bot="CENTRAL",
            environ={},
            **item,
        )
        assert result["sent"] is True
    assert calls == ["body", "body", "body"]


def test_transport_failure_is_fail_open_for_operational_pipeline():
    def broken(_message):
        raise RuntimeError("network-like failure")

    result = policy.send_automatic_telegram(
        broken,
        "body",
        bot="FALCON",
        event_type="LIVE_ORDER_SENT",
        mode="LIVE",
        environ={},
    )
    assert result["allowed"] is True
    assert result["sent"] is False
    assert result["transport_error"] == "RuntimeError"


def test_health_is_lightweight_and_in_memory():
    health = policy.telegram_notification_policy_health({})
    expected = {
        "telegram_live_only_enabled",
        "telegram_manual_commands_enabled",
        "telegram_reports_only_enabled",
        "telegram_daily_reports_enabled",
        "telegram_monthly_reports_enabled",
        "telegram_critical_alerts_enabled",
        "telegram_live_operational_alerts_enabled",
        "telegram_manual_commands_available",
        "telegram_paper_auto_notifications_enabled",
        "telegram_live_auto_notifications_enabled",
        "telegram_critical_notifications_enabled",
        "telegram_central_ceo_daily_enabled",
        "telegram_auto_allowed_live",
        "telegram_auto_allowed_live_operational",
        "telegram_auto_allowed_critical",
        "telegram_auto_allowed_manual",
        "telegram_auto_allowed_central_ceo_daily",
        "telegram_auto_blocked_paper",
        "telegram_auto_blocked_verify",
        "telegram_auto_blocked_unknown",
        "telegram_auto_blocked_live_informational",
        "telegram_auto_blocked_unknown_event",
    }
    assert expected <= set(health)
    assert health["telegram_manual_commands_enabled"] is False
    assert health["telegram_reports_only_enabled"] is True
    assert health["telegram_daily_reports_enabled"] is False
    assert health["telegram_monthly_reports_enabled"] is True
    assert health["telegram_critical_alerts_enabled"] is True
    assert health["telegram_live_operational_alerts_enabled"] is True
    assert health["telegram_paper_auto_notifications_enabled"] is False
    assert health["telegram_central_ceo_daily_enabled"] is True


def test_policy_module_has_no_network_threads_or_persistence():
    source = (ROOT / "telegram_notification_policy.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = set()
    called_attributes = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.module != "__future__":
            imported.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            called_attributes.add(node.func.attr)
    assert imported <= {"os", "datetime"}
    assert imported.isdisjoint({"requests", "socket", "redis", "threading", "flask"})
    assert called_attributes.isdisjoint({"write", "write_text", "write_bytes", "open", "post"})
    assert "TOKEN" not in source
    assert "CHAT_ID" not in source


@pytest.mark.parametrize(
    "relative,marker",
    [
        ("bots/predator.py", "send_automatic_telegram"),
        ("bots/turtle.py", "send_automatic_telegram"),
        ("bots/cobra.py", "send_cobra_automatic"),
        ("bots/donkey.py", "_safe_send_telegram_transport"),
        ("bots/meme.py", "_safe_send_telegram_transport"),
        ("bots/trendpro.py", "_safe_send_telegram_transport"),
        ("bots/falcon.py", "_safe_send_telegram_transport"),
        ("main.py", "central_send_automatic_telegram"),
    ],
)
def test_all_automatic_emitter_families_are_integrated(relative, marker):
    source = (ROOT / relative).read_text(encoding="utf-8")
    assert "telegram_notification_policy" in source
    assert marker in source


def test_paper_pipelines_keep_persistence_before_notification_gate():
    predator = (ROOT / "bots/predator.py").read_text(encoding="utf-8")
    turtle = (ROOT / "bots/turtle.py").read_text(encoding="utf-8")
    assert predator.index("registrar_trade_registry_close_predator(") < predator.index(
        "mensagem_saida(p, preco_saida, motivo, resultado)"
    )
    assert turtle.index("redis_list_append(TRADES_KEY, trade)") < turtle.index(
        'event_type="PAPER_TRADE_CLOSED"'
    )


def test_falcon_real_and_verify_contexts_are_explicit():
    source = (ROOT / "bots/falcon.py").read_text(encoding="utf-8")
    for event in (
        "TP50_LIVE",
        "BREAK_EVEN_LIVE",
        "TRAILING_UPDATED_LIVE",
        "LIVE_TRADE_CLOSED",
        "LIVE_MANAGEMENT_ERROR",
        "VERIFY_PREVIEW",
    ):
        assert event in source


def _compile_falcon_function(name, namespace):
    source = (ROOT / "bots/falcon.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    node = next(item for item in tree.body if isinstance(item, ast.FunctionDef) and item.name == name)
    node.decorator_list = []
    isolated = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(isolated)
    exec(compile(isolated, "<isolated-falcon-telegram>", "exec"), namespace)
    return namespace[name]


def _falcon_startup_harness(monkeypatch, live_only):
    monkeypatch.setenv("CENTRAL_TELEGRAM_LIVE_ONLY_ENABLED", "true" if live_only else "false")
    transports = []
    policy_namespace = {
        "send_automatic_telegram": policy.send_automatic_telegram,
        "_safe_send_telegram_transport": lambda message: transports.append(message) or True,
        "FALCON_MODE": "LIVE",
    }
    safe_send = _compile_falcon_function("safe_send_telegram", policy_namespace)

    started = []

    class FakeThread:
        def __init__(self, *, target, args, daemon):
            started.append({"target": target, "args": args, "daemon": daemon, "started": False})

        def start(self):
            started[-1]["started"] = True

    namespace = {
        "HEALTH": {},
        "data_hora_sp_str": lambda: "2026-07-13 12:00:00",
        "safe_send_telegram": safe_send,
        "SETUPS": {"FALCON15": {}, "FALCON30": {}},
        "TIMEFRAME": "15m",
        "ORB_START_HOUR": 9,
        "ORB_START_MINUTE": 30,
        "ORB_TRADE_END_HOUR": 12,
        "ORB_TRADE_END_MINUTE": 0,
        "ALIGNMENT_MODE": "off",
        "FALCON_MODE": "LIVE",
        "threading": SimpleNamespace(Thread=FakeThread),
        "run_thread_guarded": lambda *args: None,
        "scanner_loop": lambda: None,
        "management_loop": lambda: None,
        "summary_loop": lambda: None,
        "watchdog_loop": lambda: None,
    }
    startup = _compile_falcon_function("start_threads", namespace)
    startup()
    return transports, started, namespace["HEALTH"]


def _compile_loop_once(function_name: str, namespace: dict):
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    node = next(
        item
        for item in tree.body
        if isinstance(item, ast.FunctionDef) and item.name == function_name
    )
    node.decorator_list = []
    for item in ast.walk(node):
        if isinstance(item, ast.While):
            item.body = list(item.body) + [ast.Break()]
            break

    isolated = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(isolated)
    exec(compile(isolated, f"<isolated-main-loop-{function_name}>", "exec"), namespace)
    return namespace[function_name]


def _compile_main_function(function_name: str, namespace: dict):
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    node = next(
        item
        for item in tree.body
        if isinstance(item, ast.FunctionDef) and item.name == function_name
    )
    node.decorator_list = []
    isolated = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(isolated)
    exec(compile(isolated, f"<isolated-main-{function_name}>", "exec"), namespace)
    return namespace[function_name]


def _main_function_node(function_name: str):
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    return next(
        item
        for item in tree.body
        if isinstance(item, ast.FunctionDef) and item.name == function_name
    )


def test_reports_only_mode_returns_static_message_from_central_telegram_loop(monkeypatch):
    message = "Comandos manuais do Telegram estão desativados. Use as rotas HTTP da Central."
    sent = []
    calls = []

    def forbidden(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("reports-only mode should not execute blocked command handlers")

    class _Lock:
        def __enter__(self):
            return self

        def __exit__(self, _exc_type, _exc, _tb):
            return None

    namespace = {
        "TELEGRAM_MANUAL_COMMANDS_ENABLED": False,
        "TELEGRAM_REPORTS_ONLY_BLOCK_MESSAGE": message,
        "TELEGRAM_REPORTS_ONLY_ENABLED": True,
        "CENTRAL_TELEGRAM_POLLING_ENABLED": True,
        "CENTRAL_TELEGRAM_BOT_TOKEN": "token",
        "CENTRAL_TELEGRAM_CHAT_ID": "chat-99",
        "CENTRAL_TELEGRAM_OFFSET": 0,
        "CENTRAL_TELEGRAM_PROCESSED_UPDATES": set(),
        "CENTRAL_TELEGRAM_ROUTER_STARTED": False,
        "CENTRAL_TELEGRAM_ROUTER_LOCK": _Lock(),
        "CENTRAL_TELEGRAM_DROP_PENDING_ON_START": False,
        "telegram_send_with_token": lambda token, chat_id, text: sent.append(
            (token, chat_id, text)
        ),
        "telegram_get_updates_for_token": lambda _token, _offset: (
            [
                {
                    "update_id": 1,
                    "message": {"text": "/health", "chat": {"id": "chat-99"}},
                }
            ],
            None,
        ),
        "is_benign_telegram_conflict": lambda *args, **kwargs: False,
        "time": SimpleNamespace(sleep=lambda *_args, **_kwargs: None),
        "print": lambda *_args, **_kwargs: None,
        "_is_duplicate_recent_central_command": lambda *_args, **_kwargs: False,
        "_central_command_title": forbidden,
        "build_central_command_reply": forbidden,
        "bot_health": forbidden,
        "load_events": forbidden,
        "iter_jsonl_tail": forbidden,
    }

    original_import = builtins.__import__

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "history_manager":
            raise AssertionError("history_manager should not be imported in reports-only path")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    try:
        loop = _compile_loop_once("central_telegram_command_loop", namespace)
        loop()
    finally:
        monkeypatch.setattr(builtins, "__import__", original_import)

    assert sent == [("token", "chat-99", message)]
    assert calls == []


def test_reports_only_mode_returns_static_message_from_bot_router_loop(monkeypatch):
    message = "Comandos manuais do Telegram estão desativados. Use as rotas HTTP da Central."
    sent = []
    calls = []

    def forbidden(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("reports-only mode should not execute blocked bot command handlers")

    namespace = {
        "TELEGRAM_MANUAL_COMMANDS_ENABLED": False,
        "TELEGRAM_REPORTS_ONLY_BLOCK_MESSAGE": message,
        "TELEGRAM_REPORTS_ONLY_ENABLED": True,
        "os": SimpleNamespace(environ={"BOT_TOKEN": "bot-token", "BOT_CHAT": "bot-chat"}),
        "CENTRAL_COMMAND_OFFSETS": {"TURTLE": 0},
        "telegram_send_with_token": lambda token, chat_id, text: sent.append(
            (token, chat_id, text)
        ),
        "telegram_get_updates_for_token": lambda _token, _offset: (
            [
                {
                    "update_id": 1,
                    "message": {"text": "/health", "chat": {"id": "bot-chat"}},
                }
            ],
            None,
        ),
        "is_benign_telegram_conflict": lambda *args, **kwargs: False,
        "time": SimpleNamespace(sleep=lambda *_args, **_kwargs: None),
        "print": lambda *_args, **_kwargs: None,
        "_is_duplicate_recent_bot_command": lambda *_args, **_kwargs: False,
        "get_bot_module": forbidden,
        "build_command_reply_for_module": forbidden,
        "load_events": forbidden,
        "iter_jsonl_tail": forbidden,
    }

    original_import = builtins.__import__

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "history_manager":
            raise AssertionError("history_manager should not be imported in reports-only path")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    try:
        loop = _compile_loop_once("central_command_router_loop", namespace)
        loop("TURTLE", {"token_env": "BOT_TOKEN", "chat_env": "BOT_CHAT", "name": "TURTLE"})
    finally:
        monkeypatch.setattr(builtins, "__import__", original_import)

    assert sent == [("bot-token", "bot-chat", message)]
    assert calls == []


def test_falcon_startup_is_blocked_but_initialization_is_preserved(monkeypatch):
    transports, started, health = _falcon_startup_harness(monkeypatch, live_only=True)
    assert transports == []
    assert len(started) == 4
    assert all(item["started"] and item["daemon"] for item in started)
    assert health["started_at"] == "2026-07-13 12:00:00"


def test_falcon_startup_returns_to_legacy_transport_when_flag_is_false(monkeypatch):
    transports, started, _health = _falcon_startup_harness(monkeypatch, live_only=False)
    assert len(transports) == 1
    assert "Falcon Strike iniciado" in transports[0]
    assert len(started) == 4


def test_falcon_startup_has_explicit_informational_context_and_no_new_cooldown():
    source = (ROOT / "bots/falcon.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    node = next(item for item in tree.body if isinstance(item, ast.FunctionDef) and item.name == "start_threads")
    function_source = ast.get_source_segment(source, node)
    assert 'event_type="FALCON_STARTUP"' in function_source
    assert "operational_critical=False" in function_source
    assert "manual_command=False" in function_source
    assert "cooldown" not in function_source.lower()


def test_central_manual_command_transport_remains_direct():
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    node = next(
        item
        for item in tree.body
        if isinstance(item, ast.FunctionDef)
        and item.name == "central_telegram_command_loop"
    )
    command_loop = ast.get_source_segment(source, node)
    assert "telegram_send_with_token" in command_loop
    assert "central_send_automatic_telegram" not in command_loop
    for command in ("/live", "/sync", "/bots", "/health", "/resumo"):
        assert command in source


def test_http_read_routes_remain_registered_with_telegram_reports_only_mode():
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    assert '@app.route("/health")' in source
    assert '@app.route("/trade_snapshot", methods=["GET"])' in source
    assert '"/falcon/liveaudit/text"' in source
    for command in ("/health", "/posicoes", "/resumo"):
        assert command in source


def test_health_function_is_light_projection_without_watchdog_status():
    health_node = _main_function_node("health")
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    function_source = ast.get_source_segment(source, health_node)
    names = {
        node.id
        for node in ast.walk(health_node)
        if isinstance(node, ast.Name)
    }
    assert "build_central_health_light_payload" in function_source
    assert "central_watchdog_status" not in names


def test_build_central_health_light_payload_prefers_watchdog_last_status():
    forbidden_calls = []

    def forbidden(name):
        return lambda *args, **kwargs: (
            forbidden_calls.append(name) or pytest.fail(
                f"forbidden heavy path was executed: {name}"
            )
        )

    namespace = {
        "BOT_CONFIGS": {
            "PREDATOR": {
                "enabled_env": "PREDATOR_ENABLED",
                "name": "Predator",
            },
            "FALCON": {
                "enabled_env": "FALCON_ENABLED",
                "name": "Falcon",
            },
        },
        "LOAD_ERRORS": {"FALCON": "module import error"},
        "WATCHDOG_THRESHOLD_MINUTES": 30,
        "is_benign_bingx_quote_error": lambda *_args, **_kwargs: False,
        "central_health_dummy": True,
        "CENTRAL_HEALTH": {
            "started_at": "2026-07-27 12:00:00",
            "started_epoch": 1000.0,
            "watchdog_last_status": "RECENT_OK",
            "watchdog_status": "LEGACY",
        },
        "time": SimpleNamespace(time=lambda: 1120.0),
        "light_bot_health": lambda key, cfg: (
            {
                "name": cfg["name"],
                "enabled": True,
                "loaded": False,
                "load_error": "module import error",
            }
            if key == "FALCON"
            else {
                "name": cfg["name"],
                "enabled": True,
                "loaded": True,
                "health": {"last_error": "ERR", "watchdog_last_status": "ALERT"},
                "minutes_since_scanner": 45,
                "minutes_since_management": 20,
            }
        ),
        "bot_health": forbidden("bot_health"),
        "predator_pnl_paper_audit": forbidden("predator_pnl_paper_audit"),
        "predator_source_collection": forbidden("predator_source_collection"),
        "load_events": forbidden("load_events"),
        "iter_jsonl_tail": forbidden("iter_jsonl_tail"),
        "open": forbidden("open"),
        "redis": forbidden("redis"),
    }

    light_health = _compile_main_function("build_central_health_light_payload", namespace)
    payload = light_health()

    assert payload["ok"] is False
    assert payload["status"] == "ALERTA"
    assert payload["watchdog_status"] == "RECENT_OK"
    assert payload["watchdog_last_status"] == "RECENT_OK"
    assert payload["central_started_at"] == "2026-07-27 12:00:00"
    assert payload["uptime_seconds"] == 120.0
    assert payload["uptime_minutes"] == 2.0
    assert payload["uptime_hours"] == pytest.approx(0.03)
    assert payload["threshold_minutes"] == 30
    assert isinstance(payload["reasons"], list)
    reasons = "\n".join(payload["reasons"])
    assert len(payload["reasons"]) == 3
    assert any("RECENT_OK" in reason for reason in payload["reasons"]) is False
    assert any("FALCON" in item and "carregado" in item for item in payload["reasons"])
    assert "PREDATOR: last_error=ERR" in reasons
    assert "PREDATOR" in reasons and "45 min" in reasons
    assert forbidden_calls == []


def test_health_route_uses_light_projection_and_is_forbidden_from_heavy_paths():
    forbidden_calls = []

    def forbidden(name):
        return lambda *args, **kwargs: (
            forbidden_calls.append(name) or pytest.fail(
                f"forbidden heavy path was executed: {name}"
            )
        )

    namespace = {
        "watchlist_route": True,
        "BOT_CONFIGS": {},
        "WATCHDOG_THRESHOLD_MINUTES": 30,
        "CENTRAL_HEALTH": {
            "started_at": "2026-07-27 12:00:00",
            "started_epoch": 1000.0,
            "watchdog_status": "OK",
            "watchdog_last_status": "UPDATED_OK",
        },
        "time": SimpleNamespace(time=lambda: 1030.0),
        "central_trade_registry_snapshot": lambda include_trades=False, **kwargs: {
            "ok": True,
            "include_trades": include_trades,
            "health_light": kwargs.get("health_light"),
        },
        "automatic_daily_summaries_health": lambda: {
            "auto_daily_summaries_enabled": False,
        },
        "central_daily_scheduler_health": lambda: {"daily_summary_scheduler_enabled": False},
        "telegram_notification_policy_health": lambda: {
            "telegram_manual_commands_enabled": False,
            "telegram_reports_only_enabled": True,
            "telegram_daily_reports_enabled": False,
            "telegram_monthly_reports_enabled": True,
            "telegram_critical_alerts_enabled": True,
            "telegram_live_operational_alerts_enabled": True,
            "telegram_live_only_enabled": True,
            "telegram_manual_commands_available": False,
            "telegram_paper_auto_notifications_enabled": False,
            "telegram_live_auto_notifications_enabled": True,
            "telegram_critical_notifications_enabled": True,
            "telegram_central_ceo_daily_enabled": True,
        },
        "automatic_learning_refresh_health": lambda **kwargs: {
            "auto_learning_refresh_enabled": False,
            "auto_learning_refresh_thread_started": False,
            "auto_learning_refresh_manual_available": True,
            "auto_learning_refresh_interval_seconds": 900,
            "auto_learning_refresh_disabled_reason": "DISABLED_BY_POLICY",
        },
        "LEARNING_AUTO_REFRESH_SECONDS": 900,
        "LEARNING_AUTO_REFRESH_MIN_SECONDS": 300,
        "LEARNING_AUTO_REFRESH_THREAD_STARTED": False,
        "LEARNING_AUTO_REFRESH_LEGACY_ENABLED": True,
        "build_disk_forensics_health": lambda cached: {
            "disk_forensics_available": True,
            "disk_forensics_usage_pct": 50.0,
            "disk_forensics_free_mb": 1024.0,
            "disk_forensics_partial": False,
            "disk_forensics_largest_file": None,
            "disk_forensics_largest_file_mb": None,
        },
        "STARTUP_DISK_FORENSICS_RESULT": {"ok": True},
        "build_timeline_emergency_recovery_health": lambda cached: {
            "timeline_emergency_recovery_enabled": False,
            "timeline_emergency_recovery_status": "DISABLED",
        },
        "TIMELINE_EMERGENCY_RECOVERY_RESULT": {"enabled": False},
        "central_watchdog_status": forbidden("central_watchdog_status"),
        "bot_health": forbidden("bot_health"),
        "load_registry": forbidden("load_registry"),
        "predator_pnl_paper_audit": forbidden("predator_pnl_paper_audit"),
        "predator_source_collection": forbidden("predator_source_collection"),
        "load_events": forbidden("load_events"),
        "iter_jsonl_tail": forbidden("iter_jsonl_tail"),
        "open": forbidden("open"),
        "redis": forbidden("redis"),
        "socket": forbidden("socket"),
        "requests": forbidden("requests"),
        "current_rss_mb": lambda: 64.0,
        "EXECUTION_MODE": "PAPER",
        "ENABLE_REAL_TRADING": "false",
        "CENTRAL_TELEGRAM_BOT_TOKEN": "token",
        "CENTRAL_TELEGRAM_CHAT_ID": "chat",
        "CENTRAL_TELEGRAM_POLLING_ENABLED": True,
        "CENTRAL_TELEGRAM_ROUTER_STARTED": True,
        "broker": forbidden("broker"),
    }

    namespace["build_central_health_light_payload"] = _compile_main_function(
        "build_central_health_light_payload",
        namespace,
    )
    health = _compile_main_function("health", namespace)
    namespace["health"] = health
    result = health()

    assert result["ok"] is True
    assert result["health_profile"] == "LIGHT"
    assert result["heavy_audits_executed"] is False
    assert result["history_files_read"] is False
    assert result["redis_called"] is False
    assert result["broker_called"] is False
    assert result["registry_reloaded"] is False
    assert result["write_executed"] is False
    assert result["telegram_reports_only_enabled"] is True
    assert result["telegram_daily_reports_enabled"] is False
    assert result["telegram_monthly_reports_enabled"] is True
    assert result["telegram_live_operational_alerts_enabled"] is True
    assert result["trade_registry"]["include_trades"] is False
    assert result["trade_registry"]["health_light"] is True
    assert result["uptime_seconds"] == 30.0
    assert result["telegram_paper_auto_notifications_enabled"] is False
    assert forbidden_calls == []
