"""Synthetic harness for the offline apply-schema conformance contract."""

from __future__ import annotations

from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_apply_schema_static_conformance_v1 as contract


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_APPLY_SCHEMA_STATIC_CONFORMANCE_HARNESS_V1_VERSION = (
    "2026-09-06-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-APPLY-SCHEMA-STATIC-CONFORMANCE-HARNESS-V1"
)


def build_synthetic_apply_schema_sources_v1() -> dict[str, str]:
    operation_source = '''
from dataclasses import dataclass

APPLY_ACK_V1 = "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_APPLY_V1"

@dataclass
class ClosedIdentityRepairRuntimeConfigV1:
    apply_enabled: bool = False

class ClosedIdentityRepairRuntimeOperationV1:
    def apply(self, request_payload):
        if request_payload.get("ack") != APPLY_ACK_V1:
            return {}
        receipt_sha = request_payload.get("preview_receipt_sha256")
        pending = self._pending.get(receipt_sha)
        receipt = pending["receipt"]
        if receipt.get("apply_allowed") is not True:
            return {}
        if int(self._clock()) > int(receipt["expires_at_epoch"]):
            return {}
        return {}
'''.strip()
    route_source = '''
import trade_registry_closed_identity_conflict_repair_runtime_operation_v1 as operation

def _c3_closed_identity_repair_request_v1():
    body = request.get_json(silent=True)
    operation_name = str(body.get("operation") or "").lower().strip()
    if operation_name not in {"preview", "apply"}:
        return {"ok": False}
    return {"ok": True, "operation": operation_name, "payload": body}

def trade_registry_closed_identity_repair_runtime_operation_v1_route():
    decision = _c3_closed_identity_repair_request_v1()
    controller = C3_CLOSED_IDENTITY_REPAIR_RUNTIME_OPERATION_V1
    if decision.get("operation") == "preview":
        result = controller.preview(decision["payload"])
    else:
        result = controller.apply(decision["payload"])
    return result
'''.strip()
    adapter_source = '''
from dataclasses import dataclass

_APPLY_ACK_V1 = "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_APPLY_V1"

@dataclass(frozen=True, repr=False)
class ProtectedDormantApplyRequestV1:
    ack: str
    preview_receipt_sha256: str
    package_receipt_sha256: str
    authorization_receipt_sha256: str
    controller_instance_sha256: str
    reservation_token_sha256: str
    expires_at_epoch: int

class DormantApplyRequestAdapterV1:
    def _check_intent(self, value):
        return value.get("request_payload_fields") == ["ack", "preview_receipt_sha256"]

    def prepare(self, package_receipt, expiry):
        now = self._clock()
        assembled = package_receipt.get("assembled_at_epoch")
        if assembled <= now < expiry:
            return ProtectedDormantApplyRequestV1
        return None
'''.strip()
    return {
        "operation_source": operation_source,
        "route_source": route_source,
        "adapter_source": adapter_source,
    }


def build_enabled_static_conformance_config_v1(
) -> contract.StaticApplySchemaConformanceConfigV1:
    return contract.StaticApplySchemaConformanceConfigV1(
        enabled=True,
        scope_attestation=contract.OFFLINE_STATIC_CONFORMANCE_SCOPE_ATTESTATION_V1,
    )


def run_synthetic_apply_schema_static_conformance_harness_v1() -> dict[str, Any]:
    result = contract.evaluate_c3_apply_schema_static_conformance_offline_v1(
        **build_synthetic_apply_schema_sources_v1(),
        config=build_enabled_static_conformance_config_v1(),
    )
    return {
        "ok": result.get("ok") is True,
        "status": result.get("status"),
        "static_conformance_verified": result.get("static_conformance_verified"),
        "drift_detected": result.get("drift_detected"),
        "direct_controller_schema_compatible": result.get(
            "direct_controller_schema_compatible"
        ),
        "http_route_payload_compatible": result.get("http_route_payload_compatible"),
        "deadline_semantics_aligned": result.get("deadline_semantics_aligned"),
        "authorization_gateway_bound": result.get("authorization_gateway_bound"),
        "runtime_binding_satisfied": result.get("runtime_binding_satisfied"),
        "production_ready": result.get("production_ready"),
        "apply_allowed": result.get("apply_allowed"),
        "real_registry_accessed": result.get("real_registry_accessed"),
        "network_accessed": result.get("network_accessed"),
        "write_executed": result.get("write_executed"),
        "no_order_sent": result.get("no_order_sent"),
        "known_blockers": result.get("known_blockers"),
        "conformance_receipt": result.get("conformance_receipt"),
    }


__all__ = [
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_APPLY_SCHEMA_STATIC_CONFORMANCE_HARNESS_V1_VERSION",
    "build_synthetic_apply_schema_sources_v1",
    "build_enabled_static_conformance_config_v1",
    "run_synthetic_apply_schema_static_conformance_harness_v1",
]
