"""Synthetic end-to-end harness for the non-applicable repair package."""

from __future__ import annotations

import copy
import hashlib
import hmac
from pathlib import Path
from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_controlled_authorization_harness_v1 as authorization_harness
import trade_registry_closed_identity_conflict_repair_runtime_controlled_authorization_validator_v1 as authorization_validator
import trade_registry_closed_identity_conflict_repair_runtime_controlled_repair_package_v1 as package_module


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_CONTROLLED_REPAIR_PACKAGE_HARNESS_V1_VERSION = (
    "2026-09-06-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-CONTROLLED-REPAIR-PACKAGE-HARNESS-V1"
)

_NOW = authorization_harness._SYNTHETIC_NOW
_CHANGED_PATHS = [
    "closed_trades[0].close_reason",
    "closed_trades[0].gross_r_multiple",
    "closed_trades[0].metadata.outcome.close_reason",
    "closed_trades[0].metadata.outcome.gross_r_multiple",
    "closed_trades[0].metadata.outcome.r_multiple",
    "closed_trades[0].r_multiple",
]


def _synthetic_sha256(label: str) -> str:
    return hashlib.sha256(f"synthetic-package:{label}".encode("utf-8")).hexdigest()


def _build_synthetic_preview_result_v1() -> dict[str, Any]:
    receipt = {
        "receipt_version": "C3_CLOSED_IDENTITY_REPAIR_PREVIEW_RECEIPT_V1",
        "source_registry_sha256": _synthetic_sha256("source-registry"),
        "candidate_registry_sha256": _synthetic_sha256("candidate-registry"),
        "conflict_binding_sha256": _synthetic_sha256("conflict-binding"),
        "selected_source_paths": {
            "close_reason": "trade.metadata.exit_reason",
            "pnl_r": "trade.pnl_r",
        },
        "gross_r_source_path": "trade.r_multiple",
        "gross_r_preservation_sha256": _synthetic_sha256(
            "gross-r-preservation"
        ),
        "changed_paths": list(_CHANGED_PATHS),
        "issued_at_epoch": _NOW - 10,
        "expires_at_epoch": _NOW + 120,
        "apply_allowed": False,
    }
    receipt["preview_receipt_sha256"] = package_module._stable_sha256(receipt)
    return {
        "ok": True,
        "status": "REPAIR_PREVIEW_CANDIDATE_VERIFIED",
        "synthetic_only": True,
        "preservation_verified": True,
        "gross_r_preservation_verified": True,
        "real_registry_accessed": False,
        "network_accessed": False,
        "broker_called": False,
        "write_executed": False,
        "no_order_sent": True,
        "preview_receipt": receipt,
    }


def build_synthetic_c3_controlled_repair_package_inputs_v1(
    repository_root: str | Path,
) -> dict[str, Any]:
    preview_result = _build_synthetic_preview_result_v1()
    preview_receipt = preview_result["preview_receipt"]
    authorization_inputs = (
        authorization_harness.build_synthetic_c3_controlled_authorization_inputs_v1(
            repository_root
        )
    )
    envelope = authorization_inputs["authorization_envelope"]
    envelope["preview_receipt_sha256"] = preview_receipt[
        "preview_receipt_sha256"
    ]
    envelope["source_registry_sha256"] = preview_receipt[
        "source_registry_sha256"
    ]
    envelope["candidate_registry_sha256"] = preview_receipt[
        "candidate_registry_sha256"
    ]
    envelope["changed_paths_sha256"] = package_module._stable_sha256(
        preview_receipt["changed_paths"]
    )
    envelope["signature"] = hmac.new(
        authorization_harness._SYNTHETIC_KEY,
        authorization_validator.authorization_signing_payload_v1(envelope),
        hashlib.sha256,
    ).hexdigest()
    validator = (
        authorization_harness.build_synthetic_c3_controlled_authorization_validator_v1()
    )
    authorization_result = validator.verify(**authorization_inputs)
    if authorization_result.get("ok") is not True:
        raise AssertionError("synthetic authorization validation failed closed")

    controller_result = authorization_inputs["controller_binding_result"]
    controller_sha = controller_result["binding_receipt"]["binding_receipt_sha256"]
    authorization_receipt = authorization_result["authorization_receipt"]
    authorization_sha = authorization_receipt["authorization_receipt_sha256"]
    effective_expiry = min(
        authorization_receipt["expires_at_epoch"],
        preview_receipt["expires_at_epoch"],
    )
    manifest = {
        "package_version": package_module.CONTROLLED_REPAIR_PACKAGE_VERSION_V1,
        "controller_binding_receipt_sha256": controller_sha,
        "authorization_receipt_sha256": authorization_sha,
        "preview_receipt_sha256": preview_receipt["preview_receipt_sha256"],
        "source_registry_sha256": preview_receipt["source_registry_sha256"],
        "candidate_registry_sha256": preview_receipt["candidate_registry_sha256"],
        "changed_paths_sha256": package_module._stable_sha256(
            preview_receipt["changed_paths"]
        ),
        "assembled_at_epoch": _NOW,
        "expires_at_epoch": effective_expiry,
        "max_apply_count": 1,
        "dormant": True,
        "default_off": True,
        "offline_only": True,
        "synthetic_only": True,
        "production_authorization_valid": False,
        "runtime_binding_satisfied": False,
        "apply_allowed": False,
        "activation_allowed": False,
        "live_allowed": False,
    }
    manifest["package_sha256"] = (
        package_module.controlled_repair_package_sha256_v1(manifest)
    )
    return {
        "controller_binding_result": controller_result,
        "authorization_result": authorization_result,
        "preview_result": preview_result,
        "package_manifest": manifest,
    }


def build_synthetic_c3_controlled_repair_package_assembler_v1(
    *, replay_guard: package_module.InMemoryRepairPackageReplayGuardV1 | None = None
) -> package_module.ControlledRepairPackageAssemblerV1:
    return package_module.ControlledRepairPackageAssemblerV1(
        config=package_module.ControlledRepairPackageConfigV1(
            enabled=True,
            scope_attestation=package_module.OFFLINE_PACKAGE_SCOPE_ATTESTATION_V1,
        ),
        clock=lambda: _NOW,
        replay_guard=(
            replay_guard
            if replay_guard is not None
            else package_module.InMemoryRepairPackageReplayGuardV1()
        ),
    )


def run_synthetic_c3_controlled_repair_package_harness_v1(
    repository_root: str | Path,
) -> dict[str, Any]:
    inputs = build_synthetic_c3_controlled_repair_package_inputs_v1(repository_root)
    before = copy.deepcopy(inputs)
    guard = package_module.InMemoryRepairPackageReplayGuardV1()
    assembler = build_synthetic_c3_controlled_repair_package_assembler_v1(
        replay_guard=guard
    )
    first = assembler.assemble(**inputs)
    replay = assembler.assemble(**copy.deepcopy(inputs))
    receipt = first.get("package_receipt")
    guard_snapshot = guard.snapshot()
    ok = bool(
        first.get("ok") is True
        and first.get("package_contract_verified") is True
        and first.get("controller_binding_verified") is True
        and first.get("authorization_verified") is True
        and first.get("preview_verified") is True
        and first.get("cross_binding_verified") is True
        and first.get("freshness_verified") is True
        and first.get("replay_guard_verified") is True
        and first.get("package_assembled_offline") is True
        and first.get("production_authorization_valid") is False
        and first.get("runtime_binding_satisfied") is False
        and first.get("apply_allowed") is False
        and first.get("activation_allowed") is False
        and first.get("live_allowed") is False
        and isinstance(receipt, dict)
        and receipt.get("max_apply_count") == 1
        and receipt.get("apply_allowed") is False
        and replay.get("ok") is False
        and "PACKAGE_AUTHORIZATION_REPLAY_DETECTED" in replay.get("reasons", [])
        and replay.get("package_receipt") is None
        and guard_snapshot.get("stored_authorization_digest_count") == 1
        and guard_snapshot.get("raw_authorization_receipt_stored") is False
        and inputs == before
    )
    return {
        "ok": ok,
        "status": (
            "C3_CONTROLLED_REPAIR_PACKAGE_HARNESS_PASSED_OFFLINE_NON_APPLICABLE"
            if ok
            else "C3_CONTROLLED_REPAIR_PACKAGE_HARNESS_FAILED_CLOSED"
        ),
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_CONTROLLED_REPAIR_PACKAGE_HARNESS_V1_VERSION,
        "dormant": True,
        "default_off": True,
        "offline_only": True,
        "synthetic_only": True,
        "package_assembled_offline": first.get("package_assembled_offline", False),
        "production_authorization_valid": False,
        "runtime_binding_satisfied": False,
        "production_ready": False,
        "apply_allowed": False,
        "activation_allowed": False,
        "live_allowed": False,
        "runtime_integrated": False,
        "real_registry_accessed": False,
        "network_accessed": False,
        "broker_called": False,
        "write_executed": False,
        "no_order_sent": True,
        "input_preserved": inputs == before,
        "replay_denied": replay.get("ok") is False,
        "replay_guard_snapshot": guard_snapshot,
        "package_result": first,
        "replay_result": replay,
    }


__all__ = [
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_CONTROLLED_REPAIR_PACKAGE_HARNESS_V1_VERSION",
    "build_synthetic_c3_controlled_repair_package_assembler_v1",
    "build_synthetic_c3_controlled_repair_package_inputs_v1",
    "run_synthetic_c3_controlled_repair_package_harness_v1",
]
