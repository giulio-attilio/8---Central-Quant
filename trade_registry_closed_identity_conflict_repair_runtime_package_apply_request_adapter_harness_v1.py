"""Synthetic harness for the dormant package-to-request adapter."""

from __future__ import annotations

import copy
import hashlib
from pathlib import Path
from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_controlled_repair_package_harness_v1 as package_harness
import trade_registry_closed_identity_conflict_repair_runtime_package_apply_request_adapter_v1 as adapter_module


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PACKAGE_APPLY_REQUEST_ADAPTER_HARNESS_V1_VERSION = (
    "2026-09-06-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-PACKAGE-APPLY-REQUEST-ADAPTER-HARNESS-V1"
)

_NOW = package_harness._NOW


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_synthetic_c3_package_apply_request_adapter_inputs_v1(
    repository_root: str | Path,
) -> dict[str, Any]:
    package_inputs = package_harness.build_synthetic_c3_controlled_repair_package_inputs_v1(
        repository_root
    )
    package_assembler = (
        package_harness.build_synthetic_c3_controlled_repair_package_assembler_v1()
    )
    package_result = package_assembler.assemble(**package_inputs)
    if package_result.get("ok") is not True:
        raise AssertionError("controlled repair package assembly failed closed")
    package_receipt = package_result["package_receipt"]
    package_sha = package_receipt["package_receipt_sha256"]
    controller_instance_sha = _sha256_text(
        "synthetic-dormant-controller-instance-v1"
    )
    instance = {
        "attestation_version": adapter_module.PREVIEW_INSTANCE_ATTESTATION_VERSION_V1,
        "controller_instance_sha256": controller_instance_sha,
        "preview_receipt_sha256": package_receipt["preview_receipt_sha256"],
        "package_receipt_sha256": package_sha,
        "pending_preview_present": True,
        "pending_preview_same_instance": True,
        "controller_apply_enabled": False,
        "apply_scope_attested": False,
        "expires_at_epoch": package_receipt["expires_at_epoch"],
        "synthetic_only": True,
        "real_controller_referenced": False,
    }
    instance["attestation_sha256"] = (
        adapter_module.preview_instance_attestation_sha256_v1(instance)
    )
    intent = {
        "intent_version": adapter_module.APPLY_REQUEST_INTENT_VERSION_V1,
        "package_receipt_sha256": package_sha,
        "preview_instance_attestation_sha256": instance["attestation_sha256"],
        "operation": "PROJECT_DORMANT_APPLY_REQUEST",
        "request_payload_fields": ["ack", "preview_receipt_sha256"],
        "apply_ack_sha256": _sha256_text(
            "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_APPLY_V1"
        ),
        "max_apply_count": 1,
        "apply_invocation_requested": False,
        "serialization_allowed": False,
        "runtime_adapter_bound": False,
    }
    intent["intent_sha256"] = adapter_module.apply_request_intent_sha256_v1(
        intent
    )
    return {
        "controlled_package_result": package_result,
        "preview_instance_attestation": instance,
        "apply_request_intent": intent,
    }


def build_synthetic_c3_package_apply_request_adapter_v1(
    *,
    reservation_store: adapter_module.InMemoryProjectedApplyReservationStoreV1
    | None = None,
) -> adapter_module.DormantPackageApplyRequestAdapterV1:
    return adapter_module.DormantPackageApplyRequestAdapterV1(
        config=adapter_module.DormantApplyRequestAdapterConfigV1(
            enabled=True,
            scope_attestation=adapter_module.OFFLINE_ADAPTER_SCOPE_ATTESTATION_V1,
        ),
        clock=lambda: _NOW,
        reservation_store=(
            reservation_store
            if reservation_store is not None
            else adapter_module.InMemoryProjectedApplyReservationStoreV1()
        ),
    )


def run_synthetic_c3_package_apply_request_adapter_harness_v1(
    repository_root: str | Path,
) -> dict[str, Any]:
    inputs = build_synthetic_c3_package_apply_request_adapter_inputs_v1(
        repository_root
    )
    before = copy.deepcopy(inputs)
    store = adapter_module.InMemoryProjectedApplyReservationStoreV1()
    adapter = build_synthetic_c3_package_apply_request_adapter_v1(
        reservation_store=store
    )
    first = adapter.prepare(**inputs)
    duplicate = adapter.prepare(**copy.deepcopy(inputs))
    protected = first.get("protected_request")
    reservation = first.get("reservation")
    aborted = store.abort_without_invocation(reservation)
    after_abort_duplicate = adapter.prepare(**copy.deepcopy(inputs))
    store_snapshot = store.snapshot()
    protected_surface_safe = bool(
        type(protected) is adapter_module.ProtectedDormantApplyRequestV1
        and repr(protected) == "ProtectedDormantApplyRequestV1(<protected>)"
        and not hasattr(protected, "to_payload")
        and not hasattr(protected, "serialize")
        and not hasattr(protected, "send")
        and not hasattr(protected, "apply")
    )
    ok = bool(
        first.get("ok") is True
        and first.get("adapter_contract_verified") is True
        and first.get("package_verified") is True
        and first.get("same_instance_preview_verified_synthetic") is True
        and first.get("same_runtime_instance_verified") is False
        and first.get("deadline_verified") is True
        and first.get("reservation_verified") is True
        and first.get("request_projected") is True
        and first.get("request_serialization_allowed") is False
        and first.get("apply_invocation_allowed") is False
        and first.get("runtime_binding_satisfied") is False
        and first.get("apply_allowed") is False
        and first.get("activation_allowed") is False
        and first.get("live_allowed") is False
        and protected_surface_safe
        and type(reservation) is adapter_module.ProjectedApplyReservationV1
        and repr(reservation) == "ProjectedApplyReservationV1(<protected>)"
        and duplicate.get("ok") is False
        and "APPLY_ADAPTER_PACKAGE_ALREADY_RESERVED"
        in duplicate.get("reasons", [])
        and aborted is True
        and after_abort_duplicate.get("ok") is False
        and "APPLY_ADAPTER_PACKAGE_ALREADY_RESERVED"
        in after_abort_duplicate.get("reasons", [])
        and store_snapshot.get("reservation_count") == 1
        and store_snapshot.get("states")
        == {"ABORTED_WITHOUT_INVOCATION": 1}
        and store_snapshot.get("raw_package_receipt_stored") is False
        and inputs == before
    )
    return {
        "ok": ok,
        "status": (
            "C3_PACKAGE_APPLY_REQUEST_ADAPTER_HARNESS_PASSED_OFFLINE_DORMANT"
            if ok
            else "C3_PACKAGE_APPLY_REQUEST_ADAPTER_HARNESS_FAILED_CLOSED"
        ),
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PACKAGE_APPLY_REQUEST_ADAPTER_HARNESS_V1_VERSION,
        "dormant": True,
        "default_off": True,
        "offline_only": True,
        "synthetic_only": True,
        "request_projected": first.get("request_projected", False),
        "protected_surface_safe": protected_surface_safe,
        "reservation_aborted_without_invocation": aborted,
        "duplicate_denied_before_abort": duplicate.get("ok") is False,
        "duplicate_denied_after_abort": after_abort_duplicate.get("ok") is False,
        "same_runtime_instance_verified": False,
        "request_serialization_allowed": False,
        "apply_invocation_allowed": False,
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
        "reservation_store_snapshot": store_snapshot,
        "adapter_result": first,
    }


__all__ = [
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PACKAGE_APPLY_REQUEST_ADAPTER_HARNESS_V1_VERSION",
    "build_synthetic_c3_package_apply_request_adapter_inputs_v1",
    "build_synthetic_c3_package_apply_request_adapter_v1",
    "run_synthetic_c3_package_apply_request_adapter_harness_v1",
]
