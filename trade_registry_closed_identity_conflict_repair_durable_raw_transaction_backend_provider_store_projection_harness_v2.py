"""Offline harness for the dormant provider/store projection V2."""

from __future__ import annotations

from typing import Any

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_physical_reference_harness_v2 as physical_harness
import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_provider_store_projection_contract_v2 as contract


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_DURABLE_RAW_TRANSACTION_BACKEND_PROVIDER_STORE_PROJECTION_HARNESS_V2_VERSION = (
    "2026-09-08-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-DURABLE-RAW-TRANSACTION-BACKEND-PROVIDER-STORE-PROJECTION-HARNESS-V2"
)


def build_provider_store_projection_fixture_v2() -> dict[str, Any]:
    physical = physical_harness.run_temporary_physical_reference_harness_v2()
    if physical.get("ok") is not True:
        raise AssertionError("temporary physical reference harness failed")
    snapshot = physical["backend_snapshot"]
    evidence = physical["capability_evidence"]
    catalog = physical["prepared_catalog"]
    manifest = contract.build_immutable_capability_manifest_offline_v2(
        snapshot, evidence
    )
    projector = contract.DormantProviderStoreProjectionV2(
        contract.ProviderStoreProjectionConfigV2(
            enabled=True,
            scope_attestation=contract.OFFLINE_PROVIDER_STORE_PROJECTION_SCOPE_ATTESTATION_V2,
            expected_backend_snapshot_sha256=snapshot["snapshot_sha256"],
            expected_prepared_catalog_sha256=catalog["catalog_sha256"],
            expected_capability_manifest_sha256=manifest["manifest_sha256"],
        )
    )
    projection = projector.project_offline(
        snapshot=snapshot,
        capability_evidence=evidence,
        prepared_catalog=catalog,
    )
    return {
        "physical": physical,
        "snapshot": snapshot,
        "evidence": evidence,
        "catalog": catalog,
        "manifest": manifest,
        "projector": projector,
        "projection": projection,
    }


def run_provider_store_projection_harness_v2() -> dict[str, Any]:
    values = build_provider_store_projection_fixture_v2()
    projection = values["projection"]
    protected = projection.get("protected_bundle")
    bundle = protected.bundle if protected is not None else {}
    store = bundle.get("store_projection", {})
    provider = bundle.get("provider_projection", {})
    binding = bundle.get("provider_store_binding", {})
    no_call_surface = bool(
        protected is not None
        and all(
            not hasattr(protected, name)
            for name in (
                "apply", "apply_attested_transaction", "reconcile",
                "reconcile_attested_transaction", "load_exact_raw_registry",
                "install", "activate", "start",
            )
        )
    )
    ok = bool(
        projection.get("ok") is True
        and contract.immutable_capability_manifest_valid_v2(values["manifest"])
        and contract.protected_provider_store_projection_bundle_valid_v2(protected)
        and repr(protected)
        == "ProtectedProviderStoreProjectionBundleV2(<protected>)"
        and store.get("store_instance_sha256") == protected.store_instance_sha256
        and provider.get("store_projection_sha256") == store.get("projection_sha256")
        and binding.get("provider_projection_sha256") == provider.get("projection_sha256")
        and binding.get("capability_manifest_sha256")
        == values["manifest"]["manifest_sha256"]
        and no_call_surface
    )
    return {
        "ok": ok,
        "status": (
            "PROVIDER_STORE_PROJECTION_V2_HARNESS_PASSED_OFFLINE"
            if ok else "PROVIDER_STORE_PROJECTION_V2_HARNESS_FAILED_CLOSED"
        ),
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_DURABLE_RAW_TRANSACTION_BACKEND_PROVIDER_STORE_PROJECTION_HARNESS_V2_VERSION,
        "bundle_sha256": projection.get("bundle_sha256"),
        "capability_manifest_sha256": projection.get("capability_manifest_sha256"),
        "store_instance_sha256": projection.get("store_instance_sha256"),
        "capability_count": values["manifest"]["capability_count"],
        "immutable_manifest_verified": True,
        "cross_binding_verified": ok,
        "no_call_surface": no_call_surface,
        "writer_coordination_bound": False,
        "invocation_adapter_bound": False,
        "temporary_storage_only": True,
        "synthetic_only": True,
        "durability_verified": False,
        "production_authority": False,
        "provider_called": False,
        "store_called": False,
        "backend_called_by_projection": False,
        "runtime_integrated": False,
        "activation_allowed": False,
        "live_allowed": False,
        "real_registry_accessed": False,
        "network_accessed": False,
        "broker_called": False,
        "no_order_sent": True,
    }


__all__ = [
    "build_provider_store_projection_fixture_v2",
    "run_provider_store_projection_harness_v2",
]
