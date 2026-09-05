"""Read-only source loader for the C3 runtime static preflight."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_static_preflight_v1 as preflight


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_STATIC_PREFLIGHT_HARNESS_V1_VERSION = (
    "2026-09-04-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-STATIC-PREFLIGHT-HARNESS-V1"
)

_MAX_SOURCE_BYTES = 8 * 1024 * 1024
_MAX_TOTAL_SOURCE_BYTES = 16 * 1024 * 1024


class RuntimeStaticPreflightSourceBlocked(RuntimeError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def load_closed_repair_runtime_sources_read_only_v1(
    repository_root: str | Path,
) -> dict[str, str]:
    """Read only the exact allowlisted Python sources below a supplied root."""

    root = Path(repository_root).resolve(strict=True)
    if not root.is_dir():
        raise RuntimeStaticPreflightSourceBlocked("REPOSITORY_ROOT_NOT_DIRECTORY")
    sources: dict[str, str] = {}
    total = 0
    for relative in preflight.REQUIRED_SOURCE_KEYS_V1:
        path = (root / relative).resolve(strict=True)
        if not path.is_relative_to(root) or not path.is_file():
            raise RuntimeStaticPreflightSourceBlocked("SOURCE_PATH_OUTSIDE_ROOT")
        size = path.stat().st_size
        if size > _MAX_SOURCE_BYTES:
            raise RuntimeStaticPreflightSourceBlocked("SOURCE_SIZE_LIMIT_EXCEEDED")
        total += size
        if total > _MAX_TOTAL_SOURCE_BYTES:
            raise RuntimeStaticPreflightSourceBlocked(
                "TOTAL_SOURCE_SIZE_LIMIT_EXCEEDED"
            )
        try:
            source = path.read_text(encoding="utf-8")
        except UnicodeError as exc:
            raise RuntimeStaticPreflightSourceBlocked(
                "SOURCE_UTF8_DECODE_FAILED"
            ) from exc
        if "\x00" in source:
            raise RuntimeStaticPreflightSourceBlocked("SOURCE_TEXT_INVALID")
        sources[relative] = source
    return sources


def run_closed_repair_runtime_static_preflight_harness_v1(
    repository_root: str | Path,
) -> dict[str, Any]:
    sources = load_closed_repair_runtime_sources_read_only_v1(repository_root)
    before = copy.deepcopy(sources)
    result = preflight.evaluate_closed_repair_runtime_static_preflight_v1(sources)
    observed = set(result.get("blockers") or ())
    inventory_valid = bool(
        result.get("writer_summary", {}).get("discovered_count") == 19
        and result.get("writer_summary", {}).get("signature_mismatch_count") == 0
        and result.get("writer_summary", {}).get("anchor_mismatch_count") == 0
    )
    harness_ok = bool(
        result.get("evaluation_complete") is True
        and result.get("static_readiness") is True
        and result.get("production_ready") is False
        and result.get("live_allowed") is False
        and inventory_valid
        and not observed
        and sources == before
    )
    return {
        "ok": harness_ok,
        "status": (
            "C3_RUNTIME_STATIC_PREFLIGHT_HARNESS_V1_PASSED_DORMANT_SEAMS_CONFIRMED"
            if harness_ok
            else "C3_RUNTIME_STATIC_PREFLIGHT_HARNESS_V1_FAILED_CLOSED"
        ),
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_STATIC_PREFLIGHT_HARNESS_V1_VERSION,
        "read_only": True,
        "offline_only": True,
        "ast_only": True,
        "input_preserved": sources == before,
        "runtime_imported": False,
        "runtime_executed": False,
        "write_executed": False,
        "registry_write": False,
        "network_accessed": False,
        "broker_called": False,
        "no_order_sent": True,
        "static_readiness": result.get("static_readiness") is True,
        "production_ready": False,
        "live_allowed": False,
        "expected_current_blockers_confirmed": [],
        "preflight_result": result,
    }


__all__ = [
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_STATIC_PREFLIGHT_HARNESS_V1_VERSION",
    "RuntimeStaticPreflightSourceBlocked",
    "load_closed_repair_runtime_sources_read_only_v1",
    "run_closed_repair_runtime_static_preflight_harness_v1",
]
