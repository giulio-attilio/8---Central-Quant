"""Lightweight runtime contract for automatic daily summaries.

This module intentionally performs no file, Redis, broker, dataframe, network,
or Telegram access.  It is safe to import from the Central and bot processes.
"""

from __future__ import annotations

import os


_TRUE_VALUES = frozenset({"true", "1", "yes", "sim", "on"})

CENTRAL_STANDARD_DAILY_MODES = frozenset(
    {
        "completo",
        "full",
        "audit",
        "auditoria",
        "daily",
        "diario",
        "diário",
        "legacy",
        "dashboard",
        "painel",
    }
)

CENTRAL_CEO_DAILY_MODES = frozenset(
    {
        "executivo",
        "executive",
        "ceo",
        "ceo_daily",
        "ceodaily",
        "light",
        "leve",
    }
)


def _env_enabled(name: str) -> bool:
    return os.environ.get(name, "false").strip().lower() in _TRUE_VALUES


CENTRAL_AUTO_DAILY_SUMMARIES_ENABLED = _env_enabled(
    "CENTRAL_AUTO_DAILY_SUMMARIES_ENABLED"
)
CENTRAL_AUTO_CEO_DAILY_ENABLED = _env_enabled("CENTRAL_AUTO_CEO_DAILY_ENABLED")


def central_daily_report_automatic_enabled(
    mode: str | None,
    legacy_daily_enabled: bool = True,
) -> bool:
    """Return whether the configured Central daily mode may run automatically."""
    if not legacy_daily_enabled:
        return False
    if mode is None:
        return False
    normalized_mode = str(mode).strip().lower()
    if not normalized_mode:
        return False
    if normalized_mode in CENTRAL_STANDARD_DAILY_MODES:
        return CENTRAL_AUTO_DAILY_SUMMARIES_ENABLED
    if normalized_mode in CENTRAL_CEO_DAILY_MODES:
        return CENTRAL_AUTO_CEO_DAILY_ENABLED
    return False


def central_daily_report_policy_reason(
    mode: str | None,
    legacy_daily_enabled: bool = True,
) -> str:
    """Explain the lightweight policy decision without building a report."""
    if not legacy_daily_enabled:
        return "DISABLED_LEGACY_DAILY_REPORT"
    normalized_mode = str(mode or "").strip().lower()
    if normalized_mode in CENTRAL_STANDARD_DAILY_MODES:
        return (
            "STANDARD_DAILY_POLICY"
            if CENTRAL_AUTO_DAILY_SUMMARIES_ENABLED
            else "DISABLED_GLOBAL_DAILY_POLICY"
        )
    if normalized_mode in CENTRAL_CEO_DAILY_MODES:
        return (
            "CENTRAL_CEO_DAILY_POLICY"
            if CENTRAL_AUTO_CEO_DAILY_ENABLED
            else "DISABLED_CEO_DAILY_POLICY"
        )
    return "DISABLED_UNKNOWN_DAILY_MODE"


def automatic_daily_summaries_health() -> dict:
    """Return static, allocation-light health data without generating reports."""
    # Phase A exposes policy only. Real skip tracking is not implemented yet;
    # do not fabricate timestamps or bot names until an actual skip is observed.
    return {
        "auto_daily_summaries_enabled": CENTRAL_AUTO_DAILY_SUMMARIES_ENABLED,
        "auto_ceo_daily_enabled": CENTRAL_AUTO_CEO_DAILY_ENABLED,
        "daily_summary_manual_commands_available": True,
        "auto_daily_summaries_last_skipped_at": None,
        "auto_daily_summaries_skipped_bots": [],
    }


__all__ = [
    "CENTRAL_AUTO_CEO_DAILY_ENABLED",
    "CENTRAL_AUTO_DAILY_SUMMARIES_ENABLED",
    "automatic_daily_summaries_health",
    "central_daily_report_automatic_enabled",
    "central_daily_report_policy_reason",
]
