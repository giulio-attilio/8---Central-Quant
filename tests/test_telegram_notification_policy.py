from __future__ import annotations

import ast
import copy
from pathlib import Path

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
    assert result["reason"] == "LIVE_EVENT"


@pytest.mark.parametrize("mode", ["PAPER", "VERIFY", "DRY_RUN", "SHADOW", "OBSERVATION_ONLY", None, "UNKNOWN"])
def test_non_live_automatic_is_blocked(mode):
    result = decide(mode=mode)
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


def test_falcon_paper_is_blocked_and_predator_live_is_allowed():
    assert decide(bot="FALCON", mode="PAPER")["allowed"] is False
    assert decide(bot="PREDATOR", mode="LIVE")["allowed"] is True


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
        "telegram_manual_commands_available",
        "telegram_paper_auto_notifications_enabled",
        "telegram_live_auto_notifications_enabled",
        "telegram_critical_notifications_enabled",
        "telegram_auto_allowed_live",
        "telegram_auto_allowed_critical",
        "telegram_auto_allowed_manual",
        "telegram_auto_blocked_paper",
        "telegram_auto_blocked_verify",
        "telegram_auto_blocked_unknown",
    }
    assert expected <= set(health)
    assert health["telegram_paper_auto_notifications_enabled"] is False


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


def test_central_manual_command_transport_remains_direct():
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    start = source.index("def central_telegram_command_loop")
    end = source.index("def central_daily_report_loop", start)
    command_loop = source[start:end]
    assert "telegram_send_with_token" in command_loop
    assert "central_send_automatic_telegram" not in command_loop
