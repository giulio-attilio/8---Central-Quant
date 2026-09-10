"""Synthetic end-to-end harness for the dormant invocation gateway."""

from __future__ import annotations

import hashlib
from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_apply_schema_static_conformance_harness_v1 as conformance_harness
import trade_registry_closed_identity_conflict_repair_runtime_apply_schema_static_conformance_v1 as conformance_module
import trade_registry_closed_identity_conflict_repair_runtime_controlled_authorization_validator_v1 as authorization_module
import trade_registry_closed_identity_conflict_repair_runtime_package_apply_request_adapter_v1 as adapter_module
import trade_registry_closed_identity_conflict_repair_runtime_dormant_invocation_gateway_v1 as gateway_module


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_DORMANT_INVOCATION_GATEWAY_HARNESS_V1_VERSION = (
    "2026-09-06-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-DORMANT-INVOCATION-GATEWAY-HARNESS-V1"
)

_NOW = 2_000_000_000


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_synthetic_dormant_invocation_gateway_inputs_v1(
    repository_root: object | None = None,
) -> dict[str, Any]:
    del repository_root
    preview_sha = _sha256_text("synthetic-gateway-preview-v1")
    package_sha = _sha256_text("synthetic-gateway-package-v1")
    controller_instance_sha = _sha256_text("synthetic-dormant-gateway-instance-v1")
    expires_at = _NOW + 120

    authorization_receipt = {
        "upstream_controller_binding_receipt_sha256": _sha256_text(
            "synthetic-gateway-controller-binding-v1"
        ),
        "authorization_envelope_sha256": _sha256_text(
            "synthetic-gateway-authorization-envelope-v1"
        ),
        "signature_sha256": _sha256_text("synthetic-gateway-signature-v1"),
        "key_id_sha256": _sha256_text("synthetic-gateway-key-id-v1"),
        "nonce_sha256": _sha256_text("synthetic-gateway-nonce-v1"),
        "preview_receipt_sha256": preview_sha,
        "source_registry_sha256": _sha256_text("synthetic-gateway-source-v1"),
        "candidate_registry_sha256": _sha256_text(
            "synthetic-gateway-candidate-v1"
        ),
        "changed_paths_sha256": _sha256_text(
            "synthetic-gateway-changed-paths-v1"
        ),
        "authorized_action": authorization_module.AUTHORIZATION_ACTION_V1,
        "max_apply_count": 1,
        "issued_at_epoch": _NOW - 10,
        "expires_at_epoch": expires_at,
        "ttl_seconds": 130,
        "synthetic_authorization_verified": True,
        "production_authorization_valid": False,
        "runtime_binding_satisfied": False,
        "production_ready": False,
        "apply_allowed": False,
        "activation_allowed": False,
        "live_allowed": False,
        "production_blockers": ["SYNTHETIC_AUTHORIZATION_ONLY"],
    }
    authorization_receipt["authorization_receipt_sha256"] = (
        gateway_module._stable_sha256(authorization_receipt)
    )
    authorization_result = {
        "ok": True,
        "version": authorization_module.TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_CONTROLLED_AUTHORIZATION_VALIDATOR_V1_VERSION,
        "authorization_contract_verified": True,
        "upstream_controller_binding_verified": True,
        "signature_verified": True,
        "freshness_verified": True,
        "replay_guard_verified": True,
        "synthetic_authorization_verified": True,
        "apply_allowed": False,
        "activation_allowed": False,
        "live_allowed": False,
        "authorization_receipt": authorization_receipt,
    }

    reservation_sha = _sha256_text("synthetic-gateway-adapter-reservation-v1")
    protected = adapter_module.ProtectedDormantApplyRequestV1(
        ack="TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_APPLY_V1",
        preview_receipt_sha256=preview_sha,
        package_receipt_sha256=package_sha,
        authorization_receipt_sha256=authorization_receipt[
            "authorization_receipt_sha256"
        ],
        controller_instance_sha256=controller_instance_sha,
        reservation_token_sha256=reservation_sha,
        expires_at_epoch=expires_at,
    )
    adapter_receipt = {
        "package_receipt_sha256": package_sha,
        "preview_instance_attestation_sha256": _sha256_text(
            "synthetic-gateway-preview-instance-attestation-v1"
        ),
        "apply_request_intent_sha256": _sha256_text(
            "synthetic-gateway-adapter-intent-v1"
        ),
        "controller_instance_sha256": controller_instance_sha,
        "reservation_token_sha256": reservation_sha,
        "expires_at_epoch": expires_at,
        "request_payload_field_count": 2,
        "request_projected": True,
        "request_material_exposed": False,
        "same_instance_preview_verified_synthetic": True,
        "same_runtime_instance_verified": False,
        "apply_invocation_allowed": False,
        "runtime_binding_satisfied": False,
        "production_ready": False,
        "apply_allowed": False,
        "activation_allowed": False,
        "live_allowed": False,
        "production_blockers": ["SYNTHETIC_ADAPTER_ONLY"],
    }
    adapter_receipt["adapter_receipt_sha256"] = gateway_module._stable_sha256(
        adapter_receipt
    )
    adapter_result = {
        "ok": True,
        "version": adapter_module.TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PACKAGE_APPLY_REQUEST_ADAPTER_V1_VERSION,
        "adapter_contract_verified": True,
        "request_projected": True,
        "request_serialization_allowed": False,
        "apply_invocation_allowed": False,
        "runtime_binding_satisfied": False,
        "production_ready": False,
        "apply_allowed": False,
        "activation_allowed": False,
        "live_allowed": False,
        "protected_request": protected,
        "adapter_receipt": adapter_receipt,
    }

    static_conformance_result = (
        conformance_module.evaluate_c3_apply_schema_static_conformance_offline_v1(
            **conformance_harness.build_synthetic_apply_schema_sources_v1(),
            config=conformance_harness.build_enabled_static_conformance_config_v1(),
        )
    )
    if static_conformance_result.get("ok") is not True:
        raise AssertionError("synthetic static conformance failed closed")

    instance = gateway_module.SyntheticDormantControllerInstanceV1(
        controller_instance_sha256=protected.controller_instance_sha256,
        pending_preview_receipt_sha256=protected.preview_receipt_sha256,
        expires_at_epoch=protected.expires_at_epoch,
    )
    intent = {
        "intent_version": gateway_module.INVOCATION_INTENT_VERSION_V1,
        "conformance_receipt_sha256": static_conformance_result[
            "conformance_receipt"
        ]["conformance_receipt_sha256"],
        "adapter_receipt_sha256": adapter_result["adapter_receipt"][
            "adapter_receipt_sha256"
        ],
        "authorization_receipt_sha256": authorization_receipt[
            "authorization_receipt_sha256"
        ],
        "controller_instance_sha256": protected.controller_instance_sha256,
        "reservation_token_sha256": protected.reservation_token_sha256,
        "operation": "apply",
        "envelope_fields": ["operation", "ack", "preview_receipt_sha256"],
        "max_invocation_count": 1,
        "serialization_requested": False,
        "controller_call_requested": False,
        "runtime_binding_requested": False,
    }
    intent["intent_sha256"] = gateway_module.dormant_invocation_intent_sha256_v1(
        intent
    )
    return {
        "static_conformance_result": static_conformance_result,
        "adapter_result": adapter_result,
        "authorization_result": authorization_result,
        "preview_owner_instance": instance,
        "invocation_target_instance": instance,
        "invocation_intent": intent,
    }


def build_synthetic_dormant_invocation_gateway_v1(
    *,
    lease_store: gateway_module.InMemoryDormantInvocationLeaseStoreV1 | None = None,
    clock=None,
) -> gateway_module.DormantInvocationGatewayV1:
    return gateway_module.DormantInvocationGatewayV1(
        config=gateway_module.DormantInvocationGatewayConfigV1(
            enabled=True,
            scope_attestation=gateway_module.OFFLINE_INVOCATION_GATEWAY_SCOPE_ATTESTATION_V1,
        ),
        clock=clock if clock is not None else lambda: _NOW,
        lease_store=(
            lease_store
            if lease_store is not None
            else gateway_module.InMemoryDormantInvocationLeaseStoreV1()
        ),
    )


def run_synthetic_dormant_invocation_gateway_harness_v1(
    repository_root: object | None = None,
) -> dict[str, Any]:
    inputs = build_synthetic_dormant_invocation_gateway_inputs_v1(repository_root)
    store = gateway_module.InMemoryDormantInvocationLeaseStoreV1()
    gateway = build_synthetic_dormant_invocation_gateway_v1(lease_store=store)
    first = gateway.prepare(**inputs)
    duplicate = gateway.prepare(**inputs)
    envelope = first.get("protected_envelope")
    lease = first.get("invocation_lease")
    aborted = store.abort_without_invocation(lease)
    after_abort = gateway.prepare(**inputs)
    protected_surface_safe = bool(
        type(envelope) is gateway_module.ProtectedDormantInvocationEnvelopeV1
        and repr(envelope) == "ProtectedDormantInvocationEnvelopeV1(<protected>)"
        and not hasattr(envelope, "serialize")
        and not hasattr(envelope, "to_payload")
        and not hasattr(envelope, "send")
        and not hasattr(envelope, "apply")
        and not hasattr(envelope, "invoke")
    )
    ok = bool(
        first.get("ok") is True
        and first.get("gateway_contract_verified") is True
        and first.get("same_instance_preview_verified_synthetic") is True
        and first.get("same_runtime_instance_verified") is False
        and first.get("strict_deadline_verified") is True
        and first.get("http_envelope_projected") is True
        and first.get("controller_invocation_allowed") is False
        and first.get("runtime_binding_satisfied") is False
        and first.get("apply_allowed") is False
        and duplicate.get("ok") is False
        and "GATEWAY_REPLAY_OR_DUPLICATE_DETECTED" in duplicate.get("reasons", [])
        and aborted is True
        and after_abort.get("ok") is False
        and "GATEWAY_REPLAY_OR_DUPLICATE_DETECTED" in after_abort.get("reasons", [])
        and protected_surface_safe
    )
    return {
        "ok": ok,
        "status": (
            "C3_DORMANT_INVOCATION_GATEWAY_HARNESS_PASSED_OFFLINE"
            if ok
            else "C3_DORMANT_INVOCATION_GATEWAY_HARNESS_FAILED_CLOSED"
        ),
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_DORMANT_INVOCATION_GATEWAY_HARNESS_V1_VERSION,
        "protected_surface_safe": protected_surface_safe,
        "same_instance_preview_verified_synthetic": first.get(
            "same_instance_preview_verified_synthetic"
        ),
        "same_runtime_instance_verified": False,
        "strict_deadline_verified": first.get("strict_deadline_verified"),
        "http_envelope_projected": first.get("http_envelope_projected"),
        "duplicate_denied": duplicate.get("ok") is False,
        "abort_terminal": aborted and after_abort.get("ok") is False,
        "serialization_allowed": False,
        "controller_invocation_allowed": False,
        "runtime_binding_satisfied": False,
        "production_ready": False,
        "apply_allowed": False,
        "activation_allowed": False,
        "live_allowed": False,
        "real_registry_accessed": False,
        "network_accessed": False,
        "broker_called": False,
        "write_executed": False,
        "no_order_sent": True,
        "lease_store_snapshot": store.snapshot(),
    }


__all__ = [
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_DORMANT_INVOCATION_GATEWAY_HARNESS_V1_VERSION",
    "build_synthetic_dormant_invocation_gateway_inputs_v1",
    "build_synthetic_dormant_invocation_gateway_v1",
    "run_synthetic_dormant_invocation_gateway_harness_v1",
]
