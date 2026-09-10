"""Temporary physical reference for the dormant RESOLVED-authority store.

The reference binds the protected production-shaped store contract to the
existing WAL-backed authority ledger.  It is disabled by default, accepts only
temporary synthetic storage, re-verifies the authenticated root for every
operation and fails closed when the root is revoked.  It is not a production
store and exposes no runtime, activation, Live or broker surface.
"""

from __future__ import annotations

import copy
import hmac
import re
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as hash_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_authority_contract_v2 as authority_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_source_ports_contract_v2 as identity_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_production_resolved_authority_store_contract_offline_v2 as store_contract_v2


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_RESOLVED_AUTHORITY_PHYSICAL_STORE_REFERENCE_V2_VERSION = (
    "2026-09-09-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-"
    "PRODUCTION-STARTUP-RECOVERY-RESOLVED-AUTHORITY-PHYSICAL-STORE-REFERENCE-V2"
)
OFFLINE_RESOLVED_AUTHORITY_PHYSICAL_STORE_REFERENCE_SCOPE_ATTESTATION_V2 = (
    "C3_RESOLVED_AUTHORITY_PHYSICAL_STORE_TEMPORARY_SYNTHETIC_ONLY_V2"
)
RESOLVED_AUTHORITY_PHYSICAL_STORE_REFERENCE_RECEIPT_VERSION_V2 = (
    "C3_RESOLVED_AUTHORITY_PHYSICAL_STORE_REFERENCE_RECEIPT_V2"
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ResolvedAuthorityPhysicalStoreReferenceBlockedV2(RuntimeError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _valid_sha(value: Any) -> bool:
    return bool(_SHA256_RE.fullmatch(str(value or "").lower().strip()))


def _object_identity(value: Any) -> str:
    return identity_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
        value
    )


def resolved_authority_physical_store_reference_receipt_sha256_v2(
    value: Mapping[str, Any],
) -> str:
    return hash_v2.stable_sha256_v2(
        {key: item for key, item in value.items() if key != "receipt_sha256"}
    )


class InMemorySyntheticRootRevocationSourceV2:
    """Injected test-only revocation source; never reads files or the network."""

    offline_only = True
    filesystem_access_allowed = False
    network_access_allowed = False

    def __init__(self, revoked_key_ids: frozenset[str] | None = None) -> None:
        self._revoked = frozenset(revoked_key_ids or ())
        self.call_count = 0

    def root_authority_key_revoked_v2(
        self, *, key_id_sha256: str, key_epoch: int, now_epoch: int
    ) -> bool:
        self.call_count += 1
        return bool(
            _valid_sha(key_id_sha256)
            and type(key_epoch) is int
            and key_epoch >= 1
            and type(now_epoch) is int
            and key_id_sha256 in self._revoked
        )

    def __repr__(self) -> str:
        return "InMemorySyntheticRootRevocationSourceV2(<protected>)"


@dataclass(frozen=True)
class ResolvedAuthorityPhysicalStoreReferenceConfigV2:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    expected_store_binding_sha256: str | None = field(default=None, repr=False)
    expected_ledger_object_identity_sha256: str | None = field(
        default=None, repr=False
    )
    expected_root_verifier_object_identity_sha256: str | None = field(
        default=None, repr=False
    )
    expected_revocation_source_object_identity_sha256: str | None = field(
        default=None, repr=False
    )
    expected_storage_binding_sha256: str | None = field(
        default=None, repr=False
    )
    expected_temporary_root_sha256: str | None = field(default=None, repr=False)


class ResolvedAuthorityPhysicalStoreReferenceV2:
    """Fail-closed adapter over one exact temporary physical ledger instance."""

    def __init__(
        self,
        config: ResolvedAuthorityPhysicalStoreReferenceConfigV2 | None = None,
        *,
        protected_store_binding: Any = None,
        durable_authority_ledger: Any = None,
        root_authority_verifier: Any = None,
        root_revocation_source: Any = None,
        temporary_root: str | Path | None = None,
    ) -> None:
        self._config = config or ResolvedAuthorityPhysicalStoreReferenceConfigV2()
        self._binding = protected_store_binding
        self._ledger = durable_authority_ledger
        self._root_verifier = root_authority_verifier
        self._revocation_source = root_revocation_source
        self._temporary_root = (
            Path(temporary_root).resolve(strict=False)
            if temporary_root is not None
            else None
        )

    def __repr__(self) -> str:
        return "ResolvedAuthorityPhysicalStoreReferenceV2(<protected>)"

    @staticmethod
    def _base(reason: str) -> dict[str, Any]:
        return {
            "ok": False,
            "status": "RESOLVED_AUTHORITY_PHYSICAL_STORE_REFERENCE_V2_BLOCKED",
            "reason": reason,
            "operation": None,
            "record_count": 0,
            "complete_scan_verified": False,
            "wal_integrity_verified": False,
            "root_signature_reverified": False,
            "root_revocation_checked": False,
            "root_revoked": None,
            "physical_store_implementation_bound": False,
            "filesystem_accessed": False,
            "temporary_write_executed": False,
            "write_executed": False,
            "registry_write": False,
            "real_registry_accessed": False,
            "network_accessed": False,
            "broker_called": False,
            "no_order_sent": True,
            "temporary_storage_only": True,
            "synthetic_only": True,
            "production_signature_verified": False,
            "production_authority": False,
            "production_durable": False,
            "production_ready": False,
            "runtime_integrated": False,
            "activation_allowed": False,
            "live_allowed": False,
            "receipt_sha256": None,
        }

    def _reason(self) -> str | None:
        config = self._config
        if config.enabled is not True:
            return "RESOLVED_AUTHORITY_PHYSICAL_STORE_REFERENCE_DEFAULT_OFF"
        if (
            config.scope_attestation
            != OFFLINE_RESOLVED_AUTHORITY_PHYSICAL_STORE_REFERENCE_SCOPE_ATTESTATION_V2
        ):
            return "RESOLVED_AUTHORITY_PHYSICAL_STORE_REFERENCE_SCOPE_INVALID"
        pins = (
            config.expected_store_binding_sha256,
            config.expected_ledger_object_identity_sha256,
            config.expected_root_verifier_object_identity_sha256,
            config.expected_revocation_source_object_identity_sha256,
            config.expected_storage_binding_sha256,
            config.expected_temporary_root_sha256,
        )
        if any(not _valid_sha(item) for item in pins):
            return "RESOLVED_AUTHORITY_PHYSICAL_STORE_REFERENCE_PINS_INVALID"
        if not store_contract_v2.protected_production_resolved_authority_store_binding_valid_v2(
            self._binding
        ):
            return "RESOLVED_AUTHORITY_PHYSICAL_STORE_CONTRACT_BINDING_INVALID"
        if type(self._ledger) is not authority_v2.DormantDurableReconciliationAuthorityLedgerV2:
            return "RESOLVED_AUTHORITY_PHYSICAL_LEDGER_INVALID"
        if self._temporary_root is None:
            return "RESOLVED_AUTHORITY_TEMPORARY_ROOT_REQUIRED"
        if not (
            self._binding.binding_sha256 == config.expected_store_binding_sha256
            and _object_identity(self._ledger)
            == config.expected_ledger_object_identity_sha256
            and _object_identity(self._root_verifier)
            == config.expected_root_verifier_object_identity_sha256
            and _object_identity(self._revocation_source)
            == config.expected_revocation_source_object_identity_sha256
        ):
            return "RESOLVED_AUTHORITY_PHYSICAL_STORE_INSTANCE_MISMATCH"
        storage = vars(self._ledger).get("_storage")
        attestation = vars(self._ledger).get("_root_authority_attestation")
        if storage is None or not isinstance(attestation, Mapping):
            return "RESOLVED_AUTHORITY_PHYSICAL_LEDGER_BINDING_MISSING"
        storage_binding = authority_v2.durable_authority_storage_binding_sha256_v2(
            storage
        )
        binding = dict(self._binding.binding)
        if not (
            hmac.compare_digest(
                storage_binding, str(config.expected_storage_binding_sha256)
            )
            and storage_binding == binding["storage_binding_sha256"]
            and attestation.get("root_identity_sha256")
            == binding["root_identity_sha256"]
            and attestation.get("attestation_sha256")
            == binding["root_authority_attestation_sha256"]
            and attestation.get("key_id_sha256")
            == binding["root_authority_key_id_sha256"]
            and attestation.get("key_epoch")
            == binding["root_authority_key_epoch"]
            and vars(self._ledger).get("_root_authority_verifier")
            is self._root_verifier
        ):
            return "RESOLVED_AUTHORITY_PHYSICAL_STORE_CROSS_BINDING_INVALID"
        expected_root_sha = hash_v2.stable_sha256_v2(
            {"temporary_root": str(self._temporary_root)}
        )
        if not hmac.compare_digest(
            expected_root_sha, str(config.expected_temporary_root_sha256)
        ):
            return "RESOLVED_AUTHORITY_TEMPORARY_ROOT_BINDING_MISMATCH"
        system_temp = Path(tempfile.gettempdir()).resolve(strict=False)
        try:
            if not self._temporary_root.is_relative_to(system_temp):
                return "RESOLVED_AUTHORITY_STORAGE_OUTSIDE_SYSTEM_TEMP"
            storage_paths = (
                Path(storage.snapshot_path),
                Path(storage.journal_path),
                Path(storage.lock_path),
                Path(storage.backup_dir),
            )
            if any(
                not path.resolve(strict=False).is_relative_to(self._temporary_root)
                for path in storage_paths
            ):
                return "RESOLVED_AUTHORITY_STORAGE_OUTSIDE_TEMPORARY_ROOT"
        except Exception:
            return "RESOLVED_AUTHORITY_TEMPORARY_PATH_VALIDATION_FAILED"
        verifier = getattr(
            self._root_verifier, "verify_root_authority_signature_v2", None
        )
        revoked = getattr(
            self._revocation_source, "root_authority_key_revoked_v2", None
        )
        if not (
            callable(verifier)
            and callable(revoked)
            and getattr(self._revocation_source, "offline_only", None) is True
            and getattr(
                self._revocation_source, "filesystem_access_allowed", None
            )
            is False
            and getattr(self._revocation_source, "network_access_allowed", None)
            is False
        ):
            return "RESOLVED_AUTHORITY_ROOT_SECURITY_DEPENDENCY_INVALID"
        return None

    def snapshot(self) -> dict[str, Any]:
        reason = self._reason()
        attestation = (
            vars(self._ledger).get("_root_authority_attestation")
            if self._ledger is not None
            else None
        )
        return {
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_RESOLVED_AUTHORITY_PHYSICAL_STORE_REFERENCE_V2_VERSION,
            "enabled": self._config.enabled is True,
            "default_off": self._config.enabled is not True,
            "ready_for_temporary_offline_use": reason is None,
            "reason": reason,
            "physical_store_implementation_bound": reason is None,
            "store_binding_sha256": (
                getattr(self._binding, "binding_sha256", None)
                if reason is None
                else None
            ),
            "storage_binding_sha256": (
                self._config.expected_storage_binding_sha256
                if reason is None
                else None
            ),
            "root_authority_attestation_sha256": (
                attestation.get("attestation_sha256")
                if reason is None and isinstance(attestation, Mapping)
                else None
            ),
            "production_root_verifier_bound": False,
            "production_revocation_source_bound": False,
            "filesystem_accessed": False,
            "network_accessed": False,
            "real_registry_accessed": False,
            "broker_called": False,
            "no_order_sent": True,
            "synthetic_only": True,
            "production_ready": False,
            "runtime_integrated": False,
            "activation_allowed": False,
            "live_allowed": False,
        }

    def _authorize(self, now_epoch: int) -> str | None:
        reason = self._reason()
        if reason is not None:
            return reason
        attestation = vars(self._ledger)["_root_authority_attestation"]
        if not (
            type(now_epoch) is int
            and attestation["issued_at_epoch"] <= now_epoch
            < attestation["expires_at_epoch"]
            and authority_v2.authenticated_root_authority_attestation_verified_v2(
                attestation, self._root_verifier
            )
        ):
            return "RESOLVED_AUTHORITY_ROOT_SIGNATURE_REVERIFICATION_FAILED"
        try:
            revoked = self._revocation_source.root_authority_key_revoked_v2(
                key_id_sha256=attestation["key_id_sha256"],
                key_epoch=attestation["key_epoch"],
                now_epoch=now_epoch,
            )
        except Exception:
            return "RESOLVED_AUTHORITY_ROOT_REVOCATION_CHECK_FAILED"
        if type(revoked) is not bool:
            return "RESOLVED_AUTHORITY_ROOT_REVOCATION_RESULT_INVALID"
        if revoked:
            return "RESOLVED_AUTHORITY_ROOT_REVOKED"
        return None

    def _run(self, operation: str, now_epoch: int) -> dict[str, Any]:
        result = self._base("")
        reason = self._authorize(now_epoch)
        if reason is not None:
            result["reason"] = reason
            result["root_revocation_checked"] = reason == "RESOLVED_AUTHORITY_ROOT_REVOKED"
            result["root_revoked"] = True if result["root_revocation_checked"] else None
            return result
        try:
            if operation == "OPEN":
                observed = self._ledger.open_offline()
            elif operation == "RECOVER":
                observed = self._ledger.recover_offline()
            elif operation == "SCAN_RESOLVED":
                observed = self._ledger.list_resolved_records_offline()
            else:
                raise ValueError("RESOLVED_AUTHORITY_PHYSICAL_OPERATION_INVALID")
        except Exception as exc:
            result["reason"] = getattr(exc, "reason", type(exc).__name__)
            return result
        if not isinstance(observed, Mapping) or observed.get("ok") is not True:
            result["reason"] = "RESOLVED_AUTHORITY_PHYSICAL_OPERATION_FAILED_CLOSED"
            return result
        record_count = observed.get("record_count", 0)
        if type(record_count) is not int or record_count < 0:
            result["reason"] = "RESOLVED_AUTHORITY_PHYSICAL_RECORD_COUNT_INVALID"
            return result
        receipt = {
            "receipt_version": RESOLVED_AUTHORITY_PHYSICAL_STORE_REFERENCE_RECEIPT_VERSION_V2,
            "operation": operation,
            "store_binding_sha256": self._binding.binding_sha256,
            "storage_binding_sha256": self._config.expected_storage_binding_sha256,
            "ledger_object_identity_sha256": self._config.expected_ledger_object_identity_sha256,
            "record_count": record_count,
            "ledger_generation": observed.get("generation"),
            "wal_state": observed.get("wal_state"),
            "complete_scan_verified": bool(
                operation != "SCAN_RESOLVED"
                or observed.get("complete_scan_verified") is True
            ),
            "wal_integrity_verified": bool(
                operation != "SCAN_RESOLVED"
                or observed.get("wal_integrity_verified") is True
            ),
            "root_signature_reverified": True,
            "root_revocation_checked": True,
            "root_revoked": False,
            "physical_store_implementation_bound": True,
            "filesystem_accessed": True,
            "temporary_write_executed": bool(observed.get("write_executed")),
            "write_executed": False,
            "registry_write": False,
            "real_registry_accessed": False,
            "network_accessed": False,
            "broker_called": False,
            "no_order_sent": True,
            "temporary_storage_only": True,
            "synthetic_only": True,
            "production_signature_verified": False,
            "production_authority": False,
            "production_durable": False,
            "production_ready": False,
            "runtime_integrated": False,
            "activation_allowed": False,
            "live_allowed": False,
        }
        receipt["receipt_sha256"] = (
            resolved_authority_physical_store_reference_receipt_sha256_v2(
                receipt
            )
        )
        result.update(copy.deepcopy(receipt))
        result.update(
            {
                "ok": True,
                "status": "RESOLVED_AUTHORITY_PHYSICAL_STORE_REFERENCE_V2_COMPLETED_OFFLINE",
                "reason": None,
                "observed": copy.deepcopy(dict(observed)),
            }
        )
        return result

    def open_offline(self, *, now_epoch: int) -> dict[str, Any]:
        return self._run("OPEN", now_epoch)

    def recover_offline(self, *, now_epoch: int) -> dict[str, Any]:
        return self._run("RECOVER", now_epoch)

    def read_resolved_records_offline(self, *, now_epoch: int) -> dict[str, Any]:
        return self._run("SCAN_RESOLVED", now_epoch)


def build_dormant_resolved_authority_physical_store_reference_v2(
) -> ResolvedAuthorityPhysicalStoreReferenceV2:
    """Build the no-I/O, default-off runtime placeholder."""

    return ResolvedAuthorityPhysicalStoreReferenceV2()


__all__ = [
    "InMemorySyntheticRootRevocationSourceV2",
    "OFFLINE_RESOLVED_AUTHORITY_PHYSICAL_STORE_REFERENCE_SCOPE_ATTESTATION_V2",
    "RESOLVED_AUTHORITY_PHYSICAL_STORE_REFERENCE_RECEIPT_VERSION_V2",
    "ResolvedAuthorityPhysicalStoreReferenceBlockedV2",
    "ResolvedAuthorityPhysicalStoreReferenceConfigV2",
    "ResolvedAuthorityPhysicalStoreReferenceV2",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_RESOLVED_AUTHORITY_PHYSICAL_STORE_REFERENCE_V2_VERSION",
    "build_dormant_resolved_authority_physical_store_reference_v2",
    "resolved_authority_physical_store_reference_receipt_sha256_v2",
]
