"""Offline harness for the C3 V2 writer-coordination compatibility contract.

The upstream provider/store projection is injected as protected data.  This
harness creates only synthetic writer wrappers and projections; its callback
is a trap and must never be invoked.
"""

from __future__ import annotations

from typing import Any

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as backend_contract
import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_provider_store_projection_contract_v2 as provider_contract
import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_writer_coordination_compatibility_contract_v2 as contract
import trade_registry_closed_identity_conflict_repair_writer_coordination_contract_v1 as coordination
import trade_registry_closed_identity_conflict_repair_writer_invocation_adapter_v1 as invocation
import trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1 as runtime_coordinator
import trade_registry_closed_identity_conflict_repair_writer_seam_binding_contract_v1 as seam_contract


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_DURABLE_RAW_TRANSACTION_BACKEND_WRITER_COORDINATION_COMPATIBILITY_HARNESS_V2_VERSION = (
    "2026-09-08-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-DURABLE-RAW-TRANSACTION-BACKEND-WRITER-COORDINATION-COMPATIBILITY-HARNESS-V2"
)


def _sha(value: Any) -> str:
    return backend_contract.stable_sha256_v2(value)


def _seal(value: dict[str, Any], key: str) -> dict[str, Any]:
    value[key] = backend_contract.stable_sha256_v2(
        {name: item for name, item in value.items() if name != key}
    )
    return value


def _blocked(reason: str) -> dict[str, Any]:
    return {
        "ok": False,
        "status": "WRITER_COORDINATION_COMPATIBILITY_V2_HARNESS_FAILED_CLOSED",
        "reason": reason,
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_DURABLE_RAW_TRANSACTION_BACKEND_WRITER_COORDINATION_COMPATIBILITY_HARNESS_V2_VERSION,
        "protected_bundle": None,
        "writer_count": 0,
        "writer_callback_invocations": 0,
        "provider_called": False,
        "store_called": False,
        "backend_called": False,
        "writer_called": False,
        "invocation_adapter_called": False,
        "coordinator_called": False,
        "lock_acquired": False,
        "filesystem_accessed": False,
        "real_registry_accessed": False,
        "network_accessed": False,
        "broker_called": False,
        "write_executed": False,
        "production_authority": False,
        "runtime_integrated": False,
        "activation_allowed": False,
        "live_allowed": False,
        "no_order_sent": True,
    }


def build_writer_coordination_compatibility_fixture_v2(
    provider_store_bundle: provider_contract.ProtectedProviderStoreProjectionBundleV2,
    *,
    now_epoch: int = 1_000,
) -> dict[str, Any]:
    """Build deterministic projections without invoking any operational surface."""

    if not provider_contract.protected_provider_store_projection_bundle_valid_v2(
        provider_store_bundle
    ):
        raise ValueError("VALID_PROTECTED_PROVIDER_STORE_BUNDLE_REQUIRED")
    if type(now_epoch) is not int:
        raise ValueError("INTEGER_NOW_EPOCH_REQUIRED")
    inventory = coordination.canonical_closed_repair_writer_inventory_v1()
    participation_sha = _sha(
        {
            "kind": "C3_OFFLINE_WRITER_PARTICIPATION_V2",
            "provider_store_bundle_sha256": provider_store_bundle.bundle_sha256,
        }
    )
    seams = seam_contract.canonical_writer_seam_bindings_v1(
        {"participation_receipt_sha256": participation_sha}
    )
    callback_counter = {"count": 0}

    def forbidden_writer_callback(payload: Any, context: Any) -> dict[str, Any]:
        callback_counter["count"] += 1
        raise AssertionError("WRITER_CALLBACK_MUST_NOT_BE_INVOKED")

    wrappers = [
        invocation.build_production_writer_callable_v1(
            item["writer_id"],
            forbidden_writer_callback,
            label=f"OFFLINE_{index:02d}_{item['writer_id']}",
            source_signature_sha256=binding["source_signature_sha256"],
            binding_scope="TEMPORARY_TEST",
            scope_attestation=invocation.PRODUCTION_WRITER_CALLABLE_EXPLICIT_BINDING_ATTESTATION_V1,
        )
        for index, (item, binding) in enumerate(
            zip(inventory, seams, strict=True), start=1
        )
    ]
    callable_manifest_sha = invocation.production_writer_callable_manifest_sha256_v1(
        wrappers
    )
    adapter_instance_sha = _sha(
        {
            "kind": "C3_SYNTHETIC_INVOCATION_ADAPTER_PROJECTION_V2",
            "callable_manifest_sha256": callable_manifest_sha,
            "provider_store_bundle_sha256": provider_store_bundle.bundle_sha256,
        }
    )
    callable_projection = contract.build_callable_manifest_projection_offline_v2(
        inventory,
        seams,
        adapter_instance_sha256=adapter_instance_sha,
        callable_manifest_sha256=callable_manifest_sha,
    )
    namespace = runtime_coordinator.canonical_runtime_lock_namespace_v1()
    inventory_sha = _sha(inventory)
    coordinator_instance_sha = _sha(
        {
            "kind": "C3_SYNTHETIC_COORDINATOR_PROJECTION_V2",
            "writer_inventory_sha256": inventory_sha,
            "lock_namespace_sha256": namespace,
            "provider_store_bundle_sha256": provider_store_bundle.bundle_sha256,
        }
    )
    coordinator_projection = _seal(
        {
            "projection_version": contract.COORDINATOR_PROJECTION_VERSION_V2,
            "coordinator_contract_version": runtime_coordinator.TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_WRITER_RUNTIME_COORDINATOR_V1_VERSION,
            "coordinator_instance_sha256": coordinator_instance_sha,
            "writer_inventory_sha256": inventory_sha,
            "lock_namespace_sha256": namespace,
            "registered_writer_count": 19,
            "all_writers_registered": True,
            "inflight_mutations": 0,
            "synthetic_rehearsal": True,
            "runtime_enabled": False,
            "runtime_integrated": False,
            "production_authority": False,
        },
        "projection_sha256",
    )
    maintenance_epoch = _sha(
        {
            "kind": "C3_SYNTHETIC_MAINTENANCE_EPOCH_V2",
            "coordinator_instance_sha256": coordinator_instance_sha,
            "provider_store_bundle_sha256": provider_store_bundle.bundle_sha256,
        }
    )
    permit_binding = {
        "coordinator_instance_sha256": coordinator_instance_sha,
        "maintenance_epoch": maintenance_epoch,
        "state": "QUIESCED",
        "lock_namespace_sha256": namespace,
        "registered_writer_count": 19,
        "inflight_mutations": 0,
        "shared_lock_acquired": True,
    }
    permit_instance_sha = _sha(
        {"kind": "C3_SYNTHETIC_MAINTENANCE_PERMIT_V2", **permit_binding}
    )
    permit_projection = _seal(
        {
            "projection_version": contract.MAINTENANCE_PERMIT_PROJECTION_VERSION_V2,
            "permit_instance_sha256": permit_instance_sha,
            "permit_binding_sha256": _sha(permit_binding),
            **permit_binding,
            "synthetic_only": True,
            "production_authority": False,
        },
        "projection_sha256",
    )
    lease_projection = _seal(
        {
            "projection_version": contract.LIVE_LEASE_PROJECTION_VERSION_V2,
            "lease_token_sha256": _sha(
                {
                    "kind": "C3_SYNTHETIC_LIVE_LEASE_TOKEN_V2",
                    "permit_instance_sha256": permit_instance_sha,
                    "issued_at_epoch": now_epoch,
                    "expires_at_epoch": now_epoch + 120,
                }
            ),
            "permit_instance_sha256": permit_instance_sha,
            "permit_binding_sha256": permit_projection["permit_binding_sha256"],
            "coordinator_instance_sha256": coordinator_instance_sha,
            "maintenance_epoch": maintenance_epoch,
            "lock_namespace_sha256": namespace,
            "issued_at_epoch": now_epoch,
            "expires_at_epoch": now_epoch + 120,
            "same_permit_instance": True,
            "active_synthetic": True,
            "single_use": True,
            "synthetic_only": True,
            "production_authority": False,
        },
        "projection_sha256",
    )
    lock_policy = contract.build_single_owner_lock_policy_offline_v2(namespace)
    binder = contract.DormantWriterCoordinationCompatibilityV2(
        contract.WriterCoordinationCompatibilityConfigV2(
            enabled=True,
            scope_attestation=contract.OFFLINE_WRITER_COORDINATION_COMPATIBILITY_SCOPE_ATTESTATION_V2,
            expected_provider_store_bundle_sha256=provider_store_bundle.bundle_sha256,
            max_lease_seconds=120,
        )
    )
    return {
        "provider_store_bundle": provider_store_bundle,
        "writer_inventory": inventory,
        "seam_bindings": seams,
        "callable_wrappers": wrappers,
        "callable_manifest_projection": callable_projection,
        "coordinator_projection": coordinator_projection,
        "maintenance_permit_projection": permit_projection,
        "live_lease_projection": lease_projection,
        "lock_ownership_policy": lock_policy,
        "binder": binder,
        "callback_counter": callback_counter,
        "now_epoch": now_epoch,
    }


def run_writer_coordination_compatibility_harness_v2(
    provider_store_bundle: provider_contract.ProtectedProviderStoreProjectionBundleV2,
    *,
    now_epoch: int = 1_000,
) -> dict[str, Any]:
    result = _blocked("")
    try:
        fixture = build_writer_coordination_compatibility_fixture_v2(
            provider_store_bundle, now_epoch=now_epoch
        )
    except Exception:
        return _blocked("WRITER_COORDINATION_COMPATIBILITY_V2_FIXTURE_INVALID")
    binding_result = fixture["binder"].bind_offline(
        provider_store_bundle=fixture["provider_store_bundle"],
        writer_inventory=fixture["writer_inventory"],
        seam_bindings=fixture["seam_bindings"],
        callable_manifest_projection=fixture["callable_manifest_projection"],
        coordinator_projection=fixture["coordinator_projection"],
        maintenance_permit_projection=fixture["maintenance_permit_projection"],
        live_lease_projection=fixture["live_lease_projection"],
        lock_ownership_policy=fixture["lock_ownership_policy"],
        now_epoch=fixture["now_epoch"],
    )
    protected = binding_result.get("protected_bundle")
    no_call_surface = bool(
        protected is not None
        and all(
            not hasattr(protected, name)
            for name in (
                "invoke", "apply", "apply_attested_transaction", "reconcile",
                "reconcile_attested_transaction", "load_exact_raw_registry",
                "acquire", "install", "activate", "start",
            )
        )
    )
    ok = bool(
        binding_result.get("ok") is True
        and contract.protected_writer_coordination_compatibility_bundle_valid_v2(
            protected
        )
        and len(fixture["callable_wrappers"]) == 19
        and fixture["callback_counter"]["count"] == 0
        and no_call_surface
    )
    if not ok:
        return _blocked("WRITER_COORDINATION_COMPATIBILITY_V2_COMPOSITION_INVALID")
    result.update(
        {
            "ok": True,
            "status": "WRITER_COORDINATION_COMPATIBILITY_V2_HARNESS_PASSED_OFFLINE",
            "reason": None,
            "protected_bundle": protected,
            "bundle_sha256": protected.bundle_sha256,
            "provider_store_bundle_sha256": provider_store_bundle.bundle_sha256,
            "writer_count": 19,
            "writer_callback_invocations": 0,
            "exact_writer_inventory_verified": True,
            "source_signatures_verified": True,
            "v1_callable_manifest_verified": True,
            "same_permit_instance_verified_synthetic": True,
            "lease_live_verified_synthetic": True,
            "single_lock_owner_verified": True,
            "no_call_surface": True,
        }
    )
    return result


__all__ = [
    "build_writer_coordination_compatibility_fixture_v2",
    "run_writer_coordination_compatibility_harness_v2",
]
