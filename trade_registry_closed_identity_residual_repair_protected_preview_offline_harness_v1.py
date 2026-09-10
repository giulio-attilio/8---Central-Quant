"""Synthetic harness for the protected residual repair preview contract."""

from __future__ import annotations

import copy
import json
from typing import Any

import trade_registry_closed_identity_residual_repair_offline_contract_v1 as residual
import trade_registry_closed_identity_residual_repair_offline_harness_v1 as residual_harness
import trade_registry_closed_identity_residual_repair_protected_preview_offline_contract_v1 as preview


TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_PROTECTED_PREVIEW_OFFLINE_HARNESS_V1_VERSION = (
    "2026-09-10-TRADE-REGISTRY-CLOSED-IDENTITY-RESIDUAL-REPAIR-PROTECTED-PREVIEW-OFFLINE-HARNESS-V1"
)
DEFAULT_SYNTHETIC_NOW_EPOCH_V1 = 10_000
_SYNTHETIC_AUTHORITY_KEY_V1 = b"C3 synthetic residual preview authority key v1"


def build_synthetic_protected_preview_fixture_v1() -> dict[str, Any]:
    snapshot = residual_harness.build_synthetic_residual_matrix_v1()
    caps = residual.ResidualClosedIdentityRepairCapsV1()
    authority = preview.ProtectedSyntheticResidualPreviewAuthorityV1(
        _SYNTHETIC_AUTHORITY_KEY_V1
    )
    controller = preview.DormantProtectedResidualPreviewV1(
        preview.DormantProtectedResidualPreviewConfigV1(
            enabled=True,
            scope_attestation=preview.OFFLINE_PROTECTED_RESIDUAL_PREVIEW_SCOPE_ATTESTATION_V1,
            expected_planner_contract_sha256=residual.TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_OFFLINE_CONTRACT_V1_SHA256,
            receipt_ttl_seconds=60,
            maximum_deadline_seconds=120,
        ),
        authority=authority,
    )
    request = preview.ProtectedResidualPreviewRequestV1(
        registry_snapshot=snapshot,
        expected_snapshot_sha256=residual.stable_sha256_v1(snapshot),
        request_nonce_sha256=residual.stable_sha256_v1(
            "synthetic-protected-residual-preview-request-v1"
        ),
        requested_at_epoch=DEFAULT_SYNTHETIC_NOW_EPOCH_V1,
        deadline_epoch=DEFAULT_SYNTHETIC_NOW_EPOCH_V1 + 90,
        caps=caps,
    )
    return {
        "snapshot": snapshot,
        "caps": caps,
        "authority": authority,
        "controller": controller,
        "request": request,
    }


def run_protected_residual_preview_offline_harness_v1() -> dict[str, Any]:
    fixture = build_synthetic_protected_preview_fixture_v1()
    snapshot_before = copy.deepcopy(fixture["snapshot"])
    result = fixture["controller"].preview_offline(
        fixture["request"],
        now_epoch=DEFAULT_SYNTHETIC_NOW_EPOCH_V1,
    )
    receipt = result.get("preview_receipt") or {}
    serialized = json.dumps(result, sort_keys=True, separators=(",", ":"))
    tampered = copy.deepcopy(receipt)
    tampered["plan_sha256"] = "f" * 64
    disabled = preview.DormantProtectedResidualPreviewV1(
        authority=fixture["authority"]
    ).preview_offline(
        fixture["request"],
        now_epoch=DEFAULT_SYNTHETIC_NOW_EPOCH_V1,
    )
    checks = {
        "protected_request_repr": repr(fixture["request"])
        == "ProtectedResidualPreviewRequestV1(<protected>)",
        "protected_authority_repr": repr(fixture["authority"])
        == "ProtectedSyntheticResidualPreviewAuthorityV1(<protected>)",
        "input_snapshot_unchanged": fixture["snapshot"] == snapshot_before,
        "known_residual_count_exact": result.get("summary", {}).get(
            "residual_record_count"
        )
        == 43,
        "known_quarantine_count_exact": result.get("summary", {}).get(
            "quarantined_record_count"
        )
        == 32,
        "partial_quarantine_not_ready": result.get("repair_ready") is False
        and result.get("preview_candidate_complete") is False,
        "receipt_valid_now": preview.protected_residual_preview_receipt_valid_v1(
            receipt,
            fixture["authority"],
            now_epoch=DEFAULT_SYNTHETIC_NOW_EPOCH_V1,
        ),
        "receipt_valid_at_boundary": preview.protected_residual_preview_receipt_valid_v1(
            receipt,
            fixture["authority"],
            now_epoch=DEFAULT_SYNTHETIC_NOW_EPOCH_V1 + 60,
        ),
        "receipt_expired_after_boundary": not preview.protected_residual_preview_receipt_valid_v1(
            receipt,
            fixture["authority"],
            now_epoch=DEFAULT_SYNTHETIC_NOW_EPOCH_V1 + 61,
        ),
        "tampered_receipt_rejected": not preview.protected_residual_preview_receipt_valid_v1(
            tampered,
            fixture["authority"],
            now_epoch=DEFAULT_SYNTHETIC_NOW_EPOCH_V1,
        ),
        "raw_snapshot_not_public": "candidate_registry" not in serialized
        and "registry_snapshot" not in serialized,
        "raw_trade_identity_not_public": "SYNTHETIC:PREDATOR:01" not in serialized,
        "default_off_fails_closed": disabled.get("ok") is False
        and disabled.get("reasons") == ["PREVIEW_DEFAULT_OFF"],
        "no_apply_surface": not hasattr(fixture["controller"], "apply"),
        "no_filesystem": result.get("filesystem_accessed") is False,
        "no_real_registry": result.get("real_registry_accessed") is False,
        "no_network": result.get("network_accessed") is False,
        "no_write": result.get("write_executed") is False,
        "no_broker": result.get("broker_called") is False,
        "no_order": result.get("order_sent") is False,
    }
    return {
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_PROTECTED_PREVIEW_OFFLINE_HARNESS_V1_VERSION,
        "ok": bool(result.get("ok") and all(checks.values())),
        "checks": checks,
        "preview": result,
    }


TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_PROTECTED_PREVIEW_OFFLINE_HARNESS_V1_SHA256 = (
    residual.stable_sha256_v1(
        {
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_PROTECTED_PREVIEW_OFFLINE_HARNESS_V1_VERSION,
            "matrix": "43_SYNTHETIC_RESIDUAL_RECORDS",
            "receipt": "EXPIRING_HMAC_SHA256_SYNTHETIC_AUTHORITY",
            "public_payload": "SANITIZED_COUNTS_PATHS_AND_HASHES_ONLY",
            "apply_surface": False,
        }
    )
)


__all__ = [
    "DEFAULT_SYNTHETIC_NOW_EPOCH_V1",
    "TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_PROTECTED_PREVIEW_OFFLINE_HARNESS_V1_SHA256",
    "TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_PROTECTED_PREVIEW_OFFLINE_HARNESS_V1_VERSION",
    "build_synthetic_protected_preview_fixture_v1",
    "run_protected_residual_preview_offline_harness_v1",
]
