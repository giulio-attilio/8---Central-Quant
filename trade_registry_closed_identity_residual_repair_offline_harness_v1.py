"""Synthetic in-memory harness for the residual CLOSED repair contract."""

from __future__ import annotations

import copy
import datetime as dt
from typing import Any

import trade_registry_closed_identity_residual_repair_offline_contract_v1 as contract


TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_OFFLINE_HARNESS_V1_VERSION = (
    "2026-09-06-TRADE-REGISTRY-CLOSED-IDENTITY-RESIDUAL-REPAIR-OFFLINE-HARNESS-V1"
)


def _record(
    number: int,
    *,
    bot: str,
    source: str,
    opened_at: Any,
    created_at: Any,
    legacy_status: str | None = None,
    marker: str | None = None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {"created_at": created_at, "keep": {"number": number}}
    if legacy_status is not None:
        metadata["status"] = legacy_status
    if marker is not None:
        metadata["synced_from"] = marker
    return {
        "trade_id": f"SYNTHETIC:{bot}:{number:02d}",
        "status": "CLOSED",
        "bot": bot,
        "setup": f"{bot}_SYNTHETIC",
        "symbol": f"SYN{number:02d}USDT",
        "side": "LONG" if number % 2 else "SHORT",
        "source": source,
        "opened_at": opened_at,
        "closed_at": "2026-07-12T00:00:00+00:00",
        "entry": 100.0 + number,
        "metadata": metadata,
    }


def build_synthetic_residual_matrix_v1() -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    base = dt.datetime(2026, 7, 9, 15, 0, tzinfo=dt.timezone.utc)

    for number, seconds in enumerate((4.121, 12.261, 40.287, 47.562, 52.004), 1):
        moment = base + dt.timedelta(minutes=number)
        rows.append(
            _record(
                number,
                bot="PREDATOR",
                source="predator_paper_registry_sync_fix_v1",
                opened_at=(moment - dt.timedelta(hours=3)).strftime(
                    "%d/%m/%Y %H:%M"
                ),
                created_at=moment.timestamp() + seconds,
                marker="predator_module_open_positions",
            )
        )

    for number, seconds in enumerate((60.0, 61.0, 61.5, 62.0), 6):
        moment = base + dt.timedelta(hours=1, minutes=number)
        rows.append(
            _record(
                number,
                bot="FALCON",
                source="falcon",
                opened_at=(moment + dt.timedelta(seconds=seconds)).isoformat(),
                created_at=moment.isoformat(timespec="minutes"),
            )
        )

    rows.append(
        _record(
            10,
            bot="TURTLE",
            source="main_traderegistry_sync",
            opened_at=(base + dt.timedelta(hours=2, seconds=62)).isoformat(),
            created_at=(base + dt.timedelta(hours=2)).isoformat(timespec="minutes"),
            legacy_status="OPEN",
            marker="central_open_positions",
        )
    )

    for offset in range(14):
        number = 11 + offset
        moment = base + dt.timedelta(days=1, minutes=number)
        rows.append(
            _record(
                number,
                bot="TURTLE",
                source="main_traderegistry_sync",
                opened_at=moment.isoformat(),
                created_at=(moment - dt.timedelta(minutes=360 + offset * 30)).isoformat(),
                legacy_status="OPEN",
                marker="central_open_positions",
            )
        )

    for number in (25, 26):
        moment = base + dt.timedelta(days=1, minutes=number)
        rows.append(
            _record(
                number,
                bot="FALCON",
                source="falcon",
                opened_at=moment.isoformat(),
                created_at=(moment - dt.timedelta(minutes=180)).isoformat(),
            )
        )

    moment = base + dt.timedelta(days=1, minutes=27)
    rows.append(
        _record(
            27,
            bot="FALCON",
            source="main_traderegistry_sync",
            opened_at=moment.isoformat(),
            created_at=(moment - dt.timedelta(minutes=435)).isoformat(),
            legacy_status="OPEN",
            marker="central_open_positions",
        )
    )

    for offset in range(12):
        number = 28 + offset
        moment = base + dt.timedelta(days=3, minutes=number)
        rows.append(
            _record(
                number,
                bot="TURTLE",
                source="main_traderegistry_sync",
                opened_at=moment.isoformat(),
                created_at=(moment - dt.timedelta(hours=25 + offset)).isoformat(),
                legacy_status="OPEN",
                marker="central_open_positions",
            )
        )

    predator_moment = base + dt.timedelta(days=2)
    rows.append(
        _record(
            40,
            bot="PREDATOR",
            source="main_traderegistry_sync",
            opened_at=predator_moment.isoformat(),
            created_at=(predator_moment - dt.timedelta(hours=3, minutes=10)).timestamp(),
            legacy_status="ABERTO",
            marker="central_open_positions",
        )
    )
    for number, phrase in (
        (41, "DONKEY TP50 / TRAILING50+EMA20"),
        (42, "DONKEY TP50 / TRAILING50+EMA20"),
    ):
        moment = base + dt.timedelta(days=18, seconds=number)
        rows.append(
            _record(
                number,
                bot="DONKEY",
                source="main_traderegistry_sync",
                opened_at=moment.isoformat(),
                created_at=(moment - dt.timedelta(days=17)).timestamp(),
                legacy_status=phrase,
                marker="central_open_positions",
            )
        )
    return {
        "version": "synthetic-residual-42-v1",
        "open_trades": {"keep": {"unchanged": True}},
        "closed_trades": rows,
        "extension": {"must_remain_exact": True},
    }


def run_residual_repair_offline_harness_v1() -> dict[str, Any]:
    snapshot = build_synthetic_residual_matrix_v1()
    original = copy.deepcopy(snapshot)
    result = contract.build_residual_closed_identity_repair_plan_v1(
        snapshot,
        expected_snapshot_sha256=contract.stable_sha256_v1(snapshot),
    )
    summary = result.get("summary") or {}
    candidate = result.get("candidate_registry") or {}
    quarantined_indexes = {
        item.get("registry_index") for item in result.get("quarantine") or []
    }
    checks = {
        "input_unchanged": snapshot == original,
        "record_count_exact": len(snapshot["closed_trades"]) == 42,
        "residual_count_exact": summary.get("residual_record_count") == 42,
        "timestamp_equivalence_exact": summary.get("timestamp_aliases_archived") == 10,
        "status_archive_exact": summary.get("status_aliases_archived") == 31,
        "historical_quarantine_exact": summary.get("quarantined_record_count") == 32,
        "modified_record_count_exact": summary.get("modified_record_count") == 40,
        "all_records_preserved": len(candidate.get("closed_trades") or []) == 42,
        "unrelated_root_preserved": candidate.get("extension") == original["extension"],
        "two_unmodified_divergent_falcon_rows": {24, 25}.issubset(quarantined_indexes),
        "never_applicable": result.get("apply_allowed") is False,
        "no_runtime": result.get("runtime_activation_allowed") is False,
        "no_write": result.get("write_executed") is False,
        "no_broker": result.get("broker_called") is False,
    }
    return {
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_OFFLINE_HARNESS_V1_VERSION,
        "ok": bool(result.get("ok") and all(checks.values())),
        "checks": checks,
        "plan": result,
    }


TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_OFFLINE_HARNESS_V1_SHA256 = (
    contract.stable_sha256_v1(
        {
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_OFFLINE_HARNESS_V1_VERSION,
            "matrix": "42_SYNTHETIC_RESIDUAL_RECORDS",
            "expected_timestamp_equivalences": 10,
            "expected_status_archives": 31,
            "expected_quarantined_records": 32,
        }
    )
)


__all__ = [
    "TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_OFFLINE_HARNESS_V1_SHA256",
    "TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_OFFLINE_HARNESS_V1_VERSION",
    "build_synthetic_residual_matrix_v1",
    "run_residual_repair_offline_harness_v1",
]
