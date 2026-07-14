"""Política central e leve para notificações automáticas do Telegram.

Este módulo não conhece transportes, tokens, chats ou conteúdo de mensagens.
Ele decide apenas a elegibilidade a partir de contexto estruturado e mantém
contadores efêmeros de observabilidade no processo.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone


_TRUE_VALUES = {"1", "true", "yes", "sim", "on"}
_VERIFY_MODES = {"VERIFY", "DRY_RUN", "SHADOW", "OBSERVATION_ONLY"}
LIVE_OPERATIONAL_EVENT_TYPES = frozenset(
    {
        "SIGNAL_LIVE_AUTHORIZED",
        "LIVE_ORDER_SENT",
        "LIVE_ORDER_CONFIRMED",
        "LIVE_ORDER_BLOCKED",
        "LIVE_ORDER_FAILED",
        "REAL_EXECUTION_SENT",
        "REAL_EXECUTION_SENT_ATTENTION",
        "REAL_EXECUTION_BLOCKED",
        "REAL_EXECUTION_FAILED_BEFORE_SEND",
        "REAL_EXECUTION_RESULT",
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
        "LIVE_POSITION_DIVERGENCE",
        "LIVE_MANAGEMENT_ERROR",
        "OWNERSHIP_ERROR",
        "BROKER_CRITICAL",
        "FALCON_LIVE_PRE_ORDER_TELEGRAM",
        "FALCON_LIVE_POST_ORDER_AUDIT",
        "FALCON_LIVE_ORDER_BLOCKED_BY_AUDIT_STATUS",
        "REAL_POSITION_WATCHDOG",
    }
)

LIVE_INFORMATIONAL_EVENT_TYPES = frozenset(
    {
        "FALCON_NOTIFICATION",
        "FALCON_STARTUP",
        "BOT_STARTUP",
        "STARTUP",
        "READY",
        "READINESS",
        "CONFIGURATION",
        "HEARTBEAT",
        "SCANNER_STARTED",
        "WATCHDOG_STARTED",
        "STATUS",
        "FALCON_LIVE_AUDIT",
    }
)

CRITICAL_EVENT_TYPES = frozenset(
    {
        "RUNTIME_CRITICAL",
        "OOM",
        "FILESYSTEM_CRITICAL",
        "BROKER_CRITICAL",
        "DISASTER_STOP_FAILED",
        "LIVE_MANAGEMENT_ERROR",
        "LIVE_POSITION_DIVERGENCE",
        "OWNERSHIP_ERROR",
    }
)

_METRICS = {
    "telegram_auto_allowed_live": 0,
    "telegram_auto_allowed_live_operational": 0,
    "telegram_auto_allowed_critical": 0,
    "telegram_auto_allowed_manual": 0,
    "telegram_auto_blocked_paper": 0,
    "telegram_auto_blocked_verify": 0,
    "telegram_auto_blocked_unknown": 0,
    "telegram_auto_blocked_live_informational": 0,
    "telegram_auto_blocked_unknown_event": 0,
    "telegram_auto_last_blocked_at": None,
    "telegram_auto_last_blocked_bot": None,
    "telegram_auto_last_blocked_event": None,
    "telegram_auto_last_blocked_reason": None,
}


def telegram_live_only_enabled(environ=None):
    source = os.environ if environ is None else environ
    value = source.get("CENTRAL_TELEGRAM_LIVE_ONLY_ENABLED")
    if value is None:
        return True
    return str(value).strip().lower() in _TRUE_VALUES


def _clean(value, default="UNKNOWN"):
    text = str(value or "").strip().upper()
    return text or default


def should_send_automatic_telegram(
    *,
    bot,
    event_type,
    mode,
    severity=None,
    operational_critical=False,
    manual_command=False,
    metadata=None,
    environ=None,
):
    """Retorna uma decisão pura, fail-closed e que nunca propaga exceção."""

    try:
        # Argumentos canônicos têm prioridade; metadata é apenas contexto futuro.
        _ = dict(metadata) if isinstance(metadata, dict) else {}
        normalized_mode = _clean(mode)
        normalized_event = _clean(event_type)
        normalized_bot = _clean(bot)
        normalized_severity = _clean(severity, default="")
        enabled = telegram_live_only_enabled(environ)

        if manual_command is True:
            allowed, reason = True, "MANUAL_COMMAND"
        elif operational_critical is True:
            allowed, reason = True, "CRITICAL_OVERRIDE"
        elif not enabled:
            allowed, reason = True, "LEGACY_POLICY_DISABLED"
        elif normalized_mode != "LIVE":
            allowed, reason = False, "LIVE_ONLY_POLICY"
        elif normalized_event not in LIVE_OPERATIONAL_EVENT_TYPES:
            allowed, reason = False, "LIVE_EVENT_NOT_ALLOWLISTED"
        else:
            allowed, reason = True, "LIVE_OPERATIONAL_EVENT"

        return {
            "allowed": allowed,
            "reason": reason,
            "mode": normalized_mode,
            "event_type": normalized_event,
            "bot": normalized_bot,
            "severity": normalized_severity,
            "critical_override": operational_critical is True,
            "manual_override": manual_command is True,
            "live_only_enabled": enabled,
            "known_live_event": normalized_event in LIVE_OPERATIONAL_EVENT_TYPES,
            "live_operational_event": normalized_event in LIVE_OPERATIONAL_EVENT_TYPES,
            "live_informational_event": normalized_event in LIVE_INFORMATIONAL_EVENT_TYPES,
        }
    except Exception:
        # Manual/crítico explicitamente marcado continua permitido; o restante fecha.
        allowed = manual_command is True or operational_critical is True
        return {
            "allowed": allowed,
            "reason": "POLICY_ERROR_OVERRIDE" if allowed else "POLICY_ERROR_FAIL_CLOSED",
            "mode": "UNKNOWN",
            "event_type": "UNKNOWN",
            "bot": "UNKNOWN",
            "severity": "",
            "critical_override": operational_critical is True,
            "manual_override": manual_command is True,
            "live_only_enabled": True,
            "known_live_event": False,
            "live_operational_event": False,
            "live_informational_event": False,
        }


def _record_decision(decision):
    try:
        if decision.get("manual_override"):
            _METRICS["telegram_auto_allowed_manual"] += 1
        elif decision.get("critical_override"):
            _METRICS["telegram_auto_allowed_critical"] += 1
        elif decision.get("allowed") and decision.get("mode") == "LIVE":
            _METRICS["telegram_auto_allowed_live"] += 1
            _METRICS["telegram_auto_allowed_live_operational"] += 1
        elif not decision.get("allowed"):
            mode = decision.get("mode")
            if mode == "LIVE" and decision.get("live_informational_event"):
                key = "telegram_auto_blocked_live_informational"
            elif mode == "LIVE":
                key = "telegram_auto_blocked_unknown_event"
            elif mode == "PAPER":
                key = "telegram_auto_blocked_paper"
            elif mode in _VERIFY_MODES:
                key = "telegram_auto_blocked_verify"
            else:
                key = "telegram_auto_blocked_unknown"
            _METRICS[key] += 1
            _METRICS["telegram_auto_last_blocked_at"] = datetime.now(timezone.utc).isoformat()
            _METRICS["telegram_auto_last_blocked_bot"] = decision.get("bot")
            _METRICS["telegram_auto_last_blocked_event"] = decision.get("event_type")
            _METRICS["telegram_auto_last_blocked_reason"] = decision.get("reason")
    except Exception:
        pass


def _log_decision(decision):
    try:
        if decision.get("allowed"):
            if decision.get("manual_override"):
                reason = "MANUAL_COMMAND"
            elif decision.get("critical_override"):
                reason = "CRITICAL_OVERRIDE"
            elif decision.get("mode") == "LIVE":
                reason = "LIVE_OPERATIONAL_EVENT"
            else:
                return
            print(
                "TELEGRAM_NOTIFICATION_ALLOWED "
                f"bot={decision.get('bot')} event_type={decision.get('event_type')} "
                f"mode={decision.get('mode')} reason={reason}"
            )
        else:
            print(
                "TELEGRAM_NOTIFICATION_BLOCKED "
                f"bot={decision.get('bot')} event_type={decision.get('event_type')} "
                f"mode={decision.get('mode')} reason={decision.get('reason')}"
            )
    except Exception:
        pass


def send_automatic_telegram(
    sender,
    message,
    *,
    bot,
    event_type,
    mode,
    severity=None,
    operational_critical=False,
    manual_command=False,
    metadata=None,
    environ=None,
):
    """Aplica a policy imediatamente antes de chamar um transporte existente."""

    decision = should_send_automatic_telegram(
        bot=bot,
        event_type=event_type,
        mode=mode,
        severity=severity,
        operational_critical=operational_critical,
        manual_command=manual_command,
        metadata=metadata,
        environ=environ,
    )
    _record_decision(decision)
    _log_decision(decision)
    if not decision.get("allowed"):
        return {**decision, "sent": False}
    try:
        result = sender(message)
        return {**decision, "sent": bool(result), "transport_result": result}
    except Exception as exc:
        # A falha de Telegram jamais interfere no pipeline operacional.
        print(
            "TELEGRAM_NOTIFICATION_TRANSPORT_ERROR "
            f"bot={decision.get('bot')} event_type={decision.get('event_type')} "
            f"error_type={type(exc).__name__}"
        )
        return {**decision, "sent": False, "transport_error": type(exc).__name__}


def telegram_notification_policy_health(environ=None):
    enabled = telegram_live_only_enabled(environ)
    return {
        "telegram_live_only_enabled": enabled,
        "telegram_manual_commands_available": True,
        "telegram_paper_auto_notifications_enabled": not enabled,
        "telegram_live_auto_notifications_enabled": True,
        "telegram_critical_notifications_enabled": True,
        **dict(_METRICS),
    }


__all__ = [
    "CRITICAL_EVENT_TYPES",
    "LIVE_INFORMATIONAL_EVENT_TYPES",
    "LIVE_OPERATIONAL_EVENT_TYPES",
    "send_automatic_telegram",
    "should_send_automatic_telegram",
    "telegram_live_only_enabled",
    "telegram_notification_policy_health",
]
