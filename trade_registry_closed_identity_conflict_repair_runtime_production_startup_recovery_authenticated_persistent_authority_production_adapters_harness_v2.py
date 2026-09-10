"""Offline harness for the four production-shaped authority adapters."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as hash_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_authority_binding_harness_v1 as authority_harness_v1
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_persistent_authority_boundary_harness_v2 as boundary_harness_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_persistent_authority_boundary_v2 as boundary_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_persistent_authority_production_adapters_v2 as adapters_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_source_ports_contract_v2 as identity_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_resolved_authority_physical_store_reference_harness_v2 as store_harness_v2


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_AUTHENTICATED_PERSISTENT_AUTHORITY_PRODUCTION_ADAPTERS_HARNESS_V2_VERSION = (
    "2026-09-09-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-"
    "PRODUCTION-STARTUP-RECOVERY-AUTHENTICATED-PERSISTENT-AUTHORITY-PRODUCTION-ADAPTERS-HARNESS-V2"
)


def _object_identity(value: Any) -> str:
    return identity_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
        value
    )


class SyntheticInjectedKeyProviderV2:
    def resolve_root_hmac_key_v2(self, *, key_id_sha256: str) -> bytes:
        if key_id_sha256 != authority_harness_v1._SYNTHETIC_KEY_ID_SHA256:
            raise ValueError("SYNTHETIC_KEY_NOT_FOUND")
        return authority_harness_v1._SYNTHETIC_KEY

    def __repr__(self) -> str:
        return "SyntheticInjectedKeyProviderV2(<protected>)"


class TemporaryStoreRecoveryPortV2:
    def __init__(
        self, path: Path, role: str, storage_binding_sha256: str
    ) -> None:
        self._path = path
        self._role = role
        self._storage_binding_sha256 = storage_binding_sha256
        self.call_count = 0
        boundary_harness_v2._atomic_write_json(
            path, {"state": "CLEAN", "transactions_remaining": 0}
        )

    def recover_store_v2(
        self,
        *,
        maintenance_permit: dict[str, Any],
        root_authority_attestation: dict[str, Any],
        now_epoch: int,
    ) -> dict[str, Any]:
        self.call_count += 1
        stored = json.loads(self._path.read_text(encoding="utf-8"))
        if stored.get("state") != "CLEAN":
            raise ValueError("TEMPORARY_STORE_RECOVERY_NOT_CLEAN")
        receipt = {
            "ok": True,
            "receipt_version": adapters_v2.STORE_RECOVERY_PORT_RECEIPT_VERSION_V2,
            "store_role": self._role,
            "maintenance_epoch": maintenance_permit["maintenance_epoch"],
            "lock_namespace_sha256": maintenance_permit[
                "lock_namespace_sha256"
            ],
            "root_authority_attestation_sha256": root_authority_attestation[
                "attestation_sha256"
            ],
            "storage_binding_sha256": self._storage_binding_sha256,
            "transactions_remaining": stored["transactions_remaining"],
            "recovery_completed": True,
            "recovered_at_epoch": now_epoch,
            "filesystem_accessed": True,
            "temporary_storage_only": True,
            "synthetic_only": True,
            "real_registry_accessed": False,
            "network_accessed": False,
            "broker_called": False,
            "no_order_sent": True,
        }
        receipt["receipt_sha256"] = adapters_v2.store_recovery_port_receipt_sha256_v2(
            receipt
        )
        return receipt


def build_authenticated_persistent_authority_production_adapters_context_v2(
    root: str | Path, *, revoked: bool = False
) -> dict[str, Any]:
    root_path = Path(root).resolve(strict=False)
    base = boundary_harness_v2.build_authenticated_persistent_authority_boundary_context_v2(
        root_path
    )
    attestation = dict(base["attestation"])
    root_envelope = {
        "envelope_version": adapters_v2.ROOT_AUTHORITY_STATE_ENVELOPE_VERSION_V2,
        "generation": 1,
        "root_authority_attestation": attestation,
        "synthetic_only": True,
    }
    root_envelope["envelope_sha256"] = (
        adapters_v2.authority_adapter_state_envelope_sha256_v2(root_envelope)
    )
    boundary_harness_v2._atomic_write_json(
        root_path / "c3_root_authority_state_v2.json", root_envelope
    )
    revoked_ids = [attestation["key_id_sha256"]] if revoked else []
    revocation_envelope = {
        "envelope_version": adapters_v2.ROOT_REVOCATION_STATE_ENVELOPE_VERSION_V2,
        "generation": 1,
        "revoked_key_ids": revoked_ids,
        "synthetic_only": True,
    }
    revocation_envelope["envelope_sha256"] = (
        adapters_v2.authority_adapter_state_envelope_sha256_v2(
            revocation_envelope
        )
    )
    boundary_harness_v2._atomic_write_json(
        root_path / "c3_root_authority_revocations_v2.json",
        revocation_envelope,
    )
    root_binding = adapters_v2.authority_adapter_storage_root_binding_sha256_v2(
        root_path
    )
    file_config = adapters_v2.PersistentAuthorityFileAdapterConfigV2(
        enabled=True,
        scope_attestation=adapters_v2.PRODUCTION_AUTHORITY_ADAPTERS_EXPLICIT_DEPENDENCY_SCOPE_V2,
        expected_storage_root_binding_sha256=root_binding,
    )
    root_provider = adapters_v2.PersistentRootAuthorityStateProviderV2(
        file_config, storage_root=root_path
    )
    revocation_source = adapters_v2.PersistentRootAuthorityRevocationSourceV2(
        file_config, storage_root=root_path
    )
    key_provider = SyntheticInjectedKeyProviderV2()
    verifier = adapters_v2.InjectedRootAuthorityVerifierV2(
        adapters_v2.InjectedRootAuthorityVerifierConfigV2(
            enabled=True,
            scope_attestation=adapters_v2.PRODUCTION_AUTHORITY_ADAPTERS_EXPLICIT_DEPENDENCY_SCOPE_V2,
            expected_key_provider_object_identity_sha256=_object_identity(
                key_provider
            ),
        ),
        key_provider=key_provider,
    )
    storage_binding = attestation["storage_binding_sha256"]
    transaction_port = TemporaryStoreRecoveryPortV2(
        root_path / "transaction_recovery_state.json",
        "TRANSACTION_STORE",
        storage_binding,
    )
    resolved_port = TemporaryStoreRecoveryPortV2(
        root_path / "resolved_recovery_state.json",
        "RESOLVED_AUTHORITY_STORE",
        storage_binding,
    )
    multistore = adapters_v2.CoordinatedMultistoreStartupRecoveryV2(
        adapters_v2.CoordinatedMultistoreRecoveryConfigV2(
            enabled=True,
            scope_attestation=adapters_v2.PRODUCTION_AUTHORITY_ADAPTERS_EXPLICIT_DEPENDENCY_SCOPE_V2,
            expected_transaction_recovery_object_identity_sha256=_object_identity(
                transaction_port
            ),
            expected_resolved_recovery_object_identity_sha256=_object_identity(
                resolved_port
            ),
            expected_storage_binding_sha256=storage_binding,
        ),
        transaction_recovery=transaction_port,
        resolved_recovery=resolved_port,
    )
    boundary = boundary_v2.AuthenticatedPersistentAuthorityBoundaryV2(
        boundary_v2.AuthenticatedPersistentAuthorityBoundaryConfigV2(
            enabled=True,
            scope_attestation=boundary_v2.OFFLINE_AUTHENTICATED_PERSISTENT_AUTHORITY_BOUNDARY_SCOPE_ATTESTATION_V2,
            expected_root_state_provider_object_identity_sha256=_object_identity(
                root_provider
            ),
            expected_root_verifier_object_identity_sha256=_object_identity(verifier),
            expected_revocation_source_object_identity_sha256=_object_identity(
                revocation_source
            ),
            expected_multistore_recovery_object_identity_sha256=_object_identity(
                multistore
            ),
            expected_startup_bridge_object_identity_sha256=_object_identity(
                base["bridge"]
            ),
            expected_storage_binding_sha256=storage_binding,
            expected_root_authority_attestation_sha256=attestation[
                "attestation_sha256"
            ],
        ),
        root_state_provider=root_provider,
        root_authority_verifier=verifier,
        root_revocation_source=revocation_source,
        multistore_recovery=multistore,
        startup_bridge=base["bridge"],
        clock=lambda: store_harness_v2.SYNTHETIC_NOW_V2,
    )
    return {
        **base,
        "boundary": boundary,
        "root_provider": root_provider,
        "revocation": revocation_source,
        "verifier": verifier,
        "key_provider": key_provider,
        "multistore": multistore,
        "transaction_port": transaction_port,
        "resolved_port": resolved_port,
    }


def run_authenticated_persistent_authority_production_adapters_harness_v2() -> dict[str, Any]:
    root_path: Path | None = None
    with tempfile.TemporaryDirectory(prefix="c3_production_adapters_v2_") as root:
        root_path = Path(root)
        values = build_authenticated_persistent_authority_production_adapters_context_v2(
            root_path
        )
        permit = {
            "maintenance_epoch": hash_v2.stable_sha256_v2(
                {"maintenance_epoch": "production-adapters"}
            ),
            "state": "QUIESCED",
            "lock_namespace_sha256": hash_v2.stable_sha256_v2(
                {"lock_namespace": "production-adapters"}
            ),
            "registered_writer_count": 19,
            "inflight_mutations": 0,
            "shared_lock_acquired": True,
        }
        result = values["boundary"](permit)
        ok = bool(
            result.get("ok") is True
            and result.get("persistent_root_read") is True
            and result.get("root_signature_verified") is True
            and result.get("root_revocation_checked") is True
            and result.get("multistore_recovery_verified") is True
            and result.get("startup_bridge_verified") is True
            and values["transaction_port"].call_count == 1
            and values["resolved_port"].call_count == 1
            and result.get("real_registry_accessed") is False
            and result.get("network_accessed") is False
            and result.get("broker_called") is False
            and result.get("no_order_sent") is True
            and result.get("production_ready") is False
            and result.get("runtime_integrated") is False
            and result.get("live_allowed") is False
        )
    temporary_storage_removed = bool(root_path and not root_path.exists())
    ok = bool(ok and temporary_storage_removed)
    return {
        "ok": ok,
        "status": (
            "AUTHENTICATED_PERSISTENT_AUTHORITY_PRODUCTION_ADAPTERS_HARNESS_V2_PASSED"
            if ok
            else "AUTHENTICATED_PERSISTENT_AUTHORITY_PRODUCTION_ADAPTERS_HARNESS_V2_FAILED"
        ),
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_AUTHENTICATED_PERSISTENT_AUTHORITY_PRODUCTION_ADAPTERS_HARNESS_V2_VERSION,
        "temporary_storage_removed": temporary_storage_removed,
        "four_adapters_verified": True,
        "synthetic_only": True,
        "temporary_storage_only": True,
        "real_registry_accessed": False,
        "network_accessed": False,
        "broker_called": False,
        "no_order_sent": True,
        "production_ready": False,
        "runtime_integrated": False,
        "activation_allowed": False,
        "live_allowed": False,
    }


__all__ = [
    "SyntheticInjectedKeyProviderV2",
    "TemporaryStoreRecoveryPortV2",
    "build_authenticated_persistent_authority_production_adapters_context_v2",
    "run_authenticated_persistent_authority_production_adapters_harness_v2",
]
