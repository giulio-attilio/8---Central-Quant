"""Temporary-filesystem harness for the authenticated authority boundary."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as hash_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_persistent_authority_boundary_v2 as boundary_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_source_ports_contract_v2 as identity_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_resolved_authority_bridge_harness_v2 as bridge_harness_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_resolved_authority_bridge_v2 as bridge_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_resolved_authority_physical_store_reference_harness_v2 as store_harness_v2
import trade_registry_closed_identity_conflict_repair_runtime_seam_v1 as runtime_seam_v1


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_AUTHENTICATED_PERSISTENT_AUTHORITY_BOUNDARY_HARNESS_V2_VERSION = (
    "2026-09-09-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-"
    "PRODUCTION-STARTUP-RECOVERY-AUTHENTICATED-PERSISTENT-AUTHORITY-BOUNDARY-HARNESS-V2"
)


def _atomic_write_json(path: Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    payload = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


class TemporaryPersistentRootAuthorityProviderV2:
    def __init__(self, path: Path, attestation: dict[str, Any]) -> None:
        self._path = path
        self.call_count = 0
        _atomic_write_json(
            path,
            {"generation": 1, "root_authority_attestation": attestation},
        )

    def read_current_root_authority_v2(self, *, now_epoch: int) -> dict[str, Any]:
        self.call_count += 1
        value = json.loads(self._path.read_text(encoding="utf-8"))
        attestation = value["root_authority_attestation"]
        receipt = {
            "ok": True,
            "receipt_version": boundary_v2.PERSISTENT_ROOT_AUTHORITY_READ_RECEIPT_VERSION_V2,
            "storage_binding_sha256": attestation["storage_binding_sha256"],
            "root_authority_attestation_sha256": attestation[
                "attestation_sha256"
            ],
            "root_authority_attestation": attestation,
            "generation": value["generation"],
            "observed_at_epoch": now_epoch,
            "durable_read_verified": True,
            "atomic_replace_on_write": True,
            "fsync_on_write": True,
            "filesystem_accessed": True,
            "temporary_storage_only": True,
            "synthetic_only": True,
            "real_registry_accessed": False,
            "network_accessed": False,
            "broker_called": False,
            "no_order_sent": True,
        }
        receipt["receipt_sha256"] = (
            boundary_v2.persistent_root_authority_read_receipt_sha256_v2(receipt)
        )
        return receipt


class TemporaryPersistentRootRevocationSourceV2:
    def __init__(self, path: Path, revoked_key_ids: set[str] | None = None) -> None:
        self._path = path
        self.call_count = 0
        _atomic_write_json(
            path,
            {"generation": 1, "revoked_key_ids": sorted(revoked_key_ids or set())},
        )

    def root_authority_key_revoked_v2(
        self, *, key_id_sha256: str, key_epoch: int, now_epoch: int
    ) -> bool:
        self.call_count += 1
        value = json.loads(self._path.read_text(encoding="utf-8"))
        if value.get("generation") != 1 or key_epoch < 1 or now_epoch < 0:
            raise ValueError("PERSISTENT_REVOCATION_STATE_INVALID")
        return key_id_sha256 in value.get("revoked_key_ids", [])


class TemporarySyntheticMultistoreRecoveryV2:
    def __init__(self, root: Path, storage_binding_sha256: str) -> None:
        self._transaction_path = root / "transaction_store.json"
        self._resolved_path = root / "resolved_authority_store.json"
        self._storage_binding_sha256 = storage_binding_sha256
        self.call_count = 0
        _atomic_write_json(
            self._transaction_path,
            {"state": "CLEAN", "prepared_transactions_remaining": 0},
        )
        _atomic_write_json(
            self._resolved_path,
            {"state": "CLEAN", "resolved_transactions_remaining": 0},
        )

    def recover_multistore_v2(
        self,
        *,
        maintenance_permit: dict[str, Any],
        root_authority_attestation: dict[str, Any],
        now_epoch: int,
    ) -> dict[str, Any]:
        self.call_count += 1
        transaction = json.loads(self._transaction_path.read_text(encoding="utf-8"))
        resolved = json.loads(self._resolved_path.read_text(encoding="utf-8"))
        if transaction.get("state") != "CLEAN" or resolved.get("state") != "CLEAN":
            raise ValueError("SYNTHETIC_MULTISTORE_NOT_CLEAN")
        receipt = {
            "ok": True,
            "receipt_version": boundary_v2.MULTISTORE_RECOVERY_RECEIPT_VERSION_V2,
            "maintenance_epoch": maintenance_permit["maintenance_epoch"],
            "lock_namespace_sha256": maintenance_permit[
                "lock_namespace_sha256"
            ],
            "root_authority_attestation_sha256": root_authority_attestation[
                "attestation_sha256"
            ],
            "storage_binding_sha256": self._storage_binding_sha256,
            "transaction_store_recovered": True,
            "resolved_authority_store_recovered": True,
            "lock_order_verified": True,
            "reverse_release_verified": True,
            "all_locks_released": True,
            "prepared_transactions_remaining": transaction[
                "prepared_transactions_remaining"
            ],
            "resolved_transactions_remaining": resolved[
                "resolved_transactions_remaining"
            ],
            "recovered_at_epoch": now_epoch,
            "filesystem_accessed": True,
            "temporary_storage_only": True,
            "synthetic_only": True,
            "real_registry_accessed": False,
            "network_accessed": False,
            "broker_called": False,
            "no_order_sent": True,
        }
        receipt["receipt_sha256"] = (
            boundary_v2.multistore_recovery_receipt_sha256_v2(receipt)
        )
        return receipt


def build_authenticated_persistent_authority_boundary_context_v2(
    root: str | Path, *, revoked: bool = False
) -> dict[str, Any]:
    root_path = Path(root).resolve(strict=False)
    resolved_root = root_path / "resolved_authority"
    resolved_root.mkdir(parents=True, exist_ok=False)
    values = store_harness_v2.build_resolved_authority_physical_store_reference_context_v2(
        resolved_root
    )
    store = values["reference"]
    attestation = dict(vars(values["ledger"])["_root_authority_attestation"])
    verifier = values["root_authority_verifier"]
    prepared = bridge_harness_v2._SyntheticPreparedRecovery()
    bridge = bridge_v2.ResolvedAuthorityStartupRecoveryBridgeV2(
        bridge_v2.ResolvedAuthorityStartupRecoveryBridgeConfigV2(
            enabled=True,
            scope_attestation=bridge_v2.OFFLINE_RESOLVED_AUTHORITY_STARTUP_BRIDGE_SCOPE_ATTESTATION_V2,
            expected_prepared_recovery_object_identity_sha256=_object_identity(prepared),
            expected_physical_store_object_identity_sha256=_object_identity(store),
        ),
        prepared_recovery=prepared,
        physical_store=store,
        clock=lambda: store_harness_v2.SYNTHETIC_NOW_V2,
    )
    root_provider = TemporaryPersistentRootAuthorityProviderV2(
        root_path / "root_authority.json", attestation
    )
    revoked_keys = {attestation["key_id_sha256"]} if revoked else set()
    revocation = TemporaryPersistentRootRevocationSourceV2(
        root_path / "root_revocations.json", revoked_keys
    )
    multistore = TemporarySyntheticMultistoreRecoveryV2(
        root_path, attestation["storage_binding_sha256"]
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
                revocation
            ),
            expected_multistore_recovery_object_identity_sha256=_object_identity(
                multistore
            ),
            expected_startup_bridge_object_identity_sha256=_object_identity(bridge),
            expected_storage_binding_sha256=attestation[
                "storage_binding_sha256"
            ],
            expected_root_authority_attestation_sha256=attestation[
                "attestation_sha256"
            ],
        ),
        root_state_provider=root_provider,
        root_authority_verifier=verifier,
        root_revocation_source=revocation,
        multistore_recovery=multistore,
        startup_bridge=bridge,
        clock=lambda: store_harness_v2.SYNTHETIC_NOW_V2,
    )
    return {
        "boundary": boundary,
        "bridge": bridge,
        "root_provider": root_provider,
        "revocation": revocation,
        "multistore": multistore,
        "attestation": attestation,
        "prepared": prepared,
    }


def _object_identity(value: Any) -> str:
    return identity_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
        value
    )


def run_authenticated_persistent_authority_boundary_harness_v2() -> dict[str, Any]:
    root_path: Path | None = None
    with tempfile.TemporaryDirectory(prefix="c3_authenticated_boundary_v2_") as root:
        root_path = Path(root)
        values = build_authenticated_persistent_authority_boundary_context_v2(
            root_path
        )
        permit = {
            "maintenance_epoch": hash_v2.stable_sha256_v2(
                {"maintenance_epoch": "authenticated-boundary"}
            ),
            "state": "QUIESCED",
            "lock_namespace_sha256": hash_v2.stable_sha256_v2(
                {"lock_namespace": "authenticated-boundary"}
            ),
            "registered_writer_count": 19,
            "inflight_mutations": 0,
            "shared_lock_acquired": True,
        }
        before = values["boundary"].snapshot()
        result = values["boundary"](permit)
        ok = bool(
            before["temporary_offline_ready"] is True
            and result.get("ok") is True
            and result.get("persistent_root_read") is True
            and result.get("root_signature_verified") is True
            and result.get("root_revocation_checked") is True
            and result.get("root_revoked") is False
            and result.get("multistore_recovery_verified") is True
            and result.get("startup_bridge_verified") is True
            and result.get("prepared_transactions_after") == 0
            and result.get("resolved_transactions_after") == 0
            and result.get("unresolved_transactions_after") == 0
            and result.get("real_registry_accessed") is False
            and result.get("network_accessed") is False
            and result.get("broker_called") is False
            and result.get("no_order_sent") is True
            and result.get("production_ready") is False
            and result.get("runtime_integrated") is False
            and result.get("live_allowed") is False
            and values["root_provider"].call_count == 1
            and values["revocation"].call_count == 1
            and values["multistore"].call_count == 1
            and values["prepared"].call_count == 1
            and result["startup_recovery_attestation_sha256"]
            == runtime_seam_v1.startup_recovery_attestation_sha256_v1(result)
        )
    temporary_storage_removed = bool(root_path and not root_path.exists())
    ok = bool(ok and temporary_storage_removed)
    return {
        "ok": ok,
        "status": (
            "AUTHENTICATED_PERSISTENT_AUTHORITY_BOUNDARY_HARNESS_V2_PASSED"
            if ok
            else "AUTHENTICATED_PERSISTENT_AUTHORITY_BOUNDARY_HARNESS_V2_FAILED"
        ),
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_AUTHENTICATED_PERSISTENT_AUTHORITY_BOUNDARY_HARNESS_V2_VERSION,
        "temporary_storage_removed": temporary_storage_removed,
        "persistent_root_read": True,
        "persistent_revocation_checked": True,
        "multistore_recovery_verified": True,
        "temporary_storage_only": True,
        "synthetic_only": True,
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
    "TemporaryPersistentRootAuthorityProviderV2",
    "TemporaryPersistentRootRevocationSourceV2",
    "TemporarySyntheticMultistoreRecoveryV2",
    "build_authenticated_persistent_authority_boundary_context_v2",
    "run_authenticated_persistent_authority_boundary_harness_v2",
]
