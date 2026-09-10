"""Temporary-filesystem harness for the dormant durable-authority reference."""

from __future__ import annotations

import copy
import hashlib
import hmac
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import registry_v2_wal as wal_v2
import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as hash_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_authority_contract_v2 as authority_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_obligation_harness_v2 as obligation_harness_v2
import trade_registry_closed_identity_conflict_repair_writer_runtime_storage_adapters_v1 as storage_v1


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_V1_BACKEND_V2_PROTECTED_RECONCILIATION_DURABLE_AUTHORITY_HARNESS_V2_VERSION = (
    "2026-09-08-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-HANDOFF-V1-BACKEND-V2-PROTECTED-RECONCILIATION-DURABLE-AUTHORITY-HARNESS-V2"
)
DURABLE_AUTHORITY_HARNESS_EVIDENCE_VERSION_V2 = (
    "C3_DURABLE_AUTHORITY_TEMP_STORAGE_HARNESS_EVIDENCE_V2"
)
_CHECK_NAMES = (
    "TEMPORARY_LEDGER_OPENED_WITH_STABLE_ROOT",
    "ROOT_AUTHORITY_SIGNATURE_VERIFIED",
    "ROOT_AUTHORITY_ROTATION_WAL_COMMITTED",
    "ROTATED_ROOT_RECOVERED_AFTER_RESTART",
    "FORGED_ROOT_SIGNATURE_REJECTED",
    "AUTHORITY_ISSUED_ONCE",
    "RESTART_REOPENS_SAME_LEDGER",
    "SAME_ISSUE_IS_IDEMPOTENT_AFTER_RESTART",
    "SAME_ISSUE_DOES_NOT_APPEND_WAL",
    "DIVERGENT_REMINT_REJECTED",
    "AUTHORITY_CONSUMED_EXACTLY_ONCE",
    "SECOND_CONSUMPTION_REJECTED_AFTER_RESTART",
    "CRASH_AFTER_PREPARE_FAILS_CLOSED",
    "PREPARED_ISSUE_RECOVERED_AFTER_RESTART",
    "RECOVERED_ISSUE_REMAINS_IDEMPOTENT",
    "CONCURRENT_LOCK_CONTENTION_FAILS_CLOSED",
    "ROOT_SUBSTITUTION_REJECTED",
    "JOURNAL_CORRUPTION_FAILS_CLOSED",
    "PROTECTED_RECEIPTS_HIDE_RECORDS",
    "NO_REAL_REGISTRY_RUNTIME_NETWORK_OR_BROKER_ACCESS",
)
_CHECK_KEYS = frozenset({"name", "passed"})
_EVIDENCE_KEYS = frozenset(
    {
        "evidence_version", "root_identity_sha256", "storage_binding_sha256",
        "root_authority_attestation_sha256", "root_authority_key_epoch",
        "issued_receipt_sha256", "consumed_receipt_sha256",
        "recovered_receipt_sha256", "final_generation_before_corruption",
        "checks", "check_count", "passed_count", "temporary_filesystem_accessed",
        "temporary_write_executed", "temporary_storage_removed",
        "interprocess_lock_acquired", "restart_persistent_reference",
        "production_durable", "real_registry_accessed", "network_accessed",
        "broker_called", "production_authority", "runtime_integrated",
        "activation_allowed", "live_allowed", "no_order_sent",
        "synthetic_only", "evidence_sha256",
    }
)

_SYNTHETIC_ROOT_KEY_ID_ONE = hashlib.sha256(b"c3-root-key-v2-one").hexdigest()
_SYNTHETIC_ROOT_KEY_ID_TWO = hashlib.sha256(b"c3-root-key-v2-two").hexdigest()
_SYNTHETIC_ROOT_KEYS = {
    _SYNTHETIC_ROOT_KEY_ID_ONE: b"synthetic-c3-root-key-v2-one",
    _SYNTHETIC_ROOT_KEY_ID_TWO: b"synthetic-c3-root-key-v2-two",
}


class _SyntheticRootAuthorityVerifierV2:
    def verify_root_authority_signature_v2(
        self,
        *,
        key_id_sha256: str,
        payload_sha256: str,
        signature_sha256: str,
    ) -> bool:
        key = _SYNTHETIC_ROOT_KEYS.get(key_id_sha256)
        if key is None:
            return False
        expected = hmac.new(
            key,
            payload_sha256.encode("ascii"),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature_sha256)


def _root_attestation(
    root_identity_sha256: str,
    storage_binding_sha256: str,
    *,
    key_epoch: int = 1,
    previous_attestation_sha256: str | None = None,
) -> dict[str, Any]:
    key_id = tuple(_SYNTHETIC_ROOT_KEYS)[key_epoch - 1]
    value = {
        "attestation_version": authority_v2.AUTHENTICATED_ROOT_AUTHORITY_ATTESTATION_VERSION_V2,
        "root_identity_sha256": root_identity_sha256,
        "storage_binding_sha256": storage_binding_sha256,
        "key_id_sha256": key_id,
        "key_epoch": key_epoch,
        "previous_attestation_sha256": previous_attestation_sha256,
        "issued_at_epoch": 0,
        "expires_at_epoch": 4_102_444_800,
        "signature_algorithm": authority_v2.ROOT_AUTHORITY_SIGNATURE_ALGORITHM_V2,
        "signature_sha256": "",
    }
    payload_sha = authority_v2.root_authority_signature_payload_sha256_v2(value)
    value["signature_sha256"] = hmac.new(
        _SYNTHETIC_ROOT_KEYS[key_id],
        payload_sha.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()
    value["attestation_sha256"] = (
        authority_v2.authenticated_root_authority_attestation_sha256_v2(value)
    )
    return value


def _sha(value: Any) -> str:
    return hash_v2.stable_sha256_v2(value)


def _storage(root: Path) -> wal_v2.RegistryV2WalStorage:
    return wal_v2.RegistryV2WalStorage(
        snapshot_path=root / "authority.snapshot.json",
        journal_path=root / "authority.journal.jsonl",
        lock_path=root / "authority.wal.lock",
        backup_dir=root / "backups",
    )


def _ledger(
    root: Path,
    storage: wal_v2.RegistryV2WalStorage,
    root_identity_sha256: str,
    *,
    lock_timeout_seconds: float = 1.0,
    root_attestation: Mapping[str, Any] | None = None,
) -> authority_v2.DormantDurableReconciliationAuthorityLedgerV2:
    binding = authority_v2.durable_authority_storage_binding_sha256_v2(storage)
    authenticated_root = dict(
        root_attestation or _root_attestation(root_identity_sha256, binding)
    )
    lock_backend = storage_v1.CrossPlatformInterprocessFileLockBackendV1(
        root, enabled=True
    )
    return authority_v2.DormantDurableReconciliationAuthorityLedgerV2(
        authority_v2.DormantDurableReconciliationAuthorityConfigV2(
            enabled=True,
            scope_attestation=authority_v2.OFFLINE_PROTECTED_RECONCILIATION_DURABLE_AUTHORITY_SCOPE_ATTESTATION_V2,
            expected_root_identity_sha256=root_identity_sha256,
            expected_storage_binding_sha256=binding,
            lock_timeout_seconds=lock_timeout_seconds,
        ),
        storage=storage,
        lock_backend=lock_backend,
        root_authority_attestation=authenticated_root,
        root_authority_verifier=_SyntheticRootAuthorityVerifierV2(),
    )


def durable_authority_harness_evidence_sha256_v2(value: Mapping[str, Any]) -> str:
    return _sha({key: item for key, item in value.items() if key != "evidence_sha256"})


@dataclass(frozen=True, repr=False)
class ProtectedDurableAuthorityHarnessEvidenceV2:
    issued_receipt: authority_v2.ProtectedDurableReconciliationAuthorityReceiptV2 = field(repr=False)
    consumed_receipt: authority_v2.ProtectedDurableReconciliationAuthorityReceiptV2 = field(repr=False)
    recovered_receipt: authority_v2.ProtectedDurableReconciliationAuthorityReceiptV2 = field(repr=False)
    evidence: Mapping[str, Any] = field(repr=False)
    evidence_sha256: str = field(repr=False)

    def __repr__(self) -> str:
        return "ProtectedDurableAuthorityHarnessEvidenceV2(<protected>)"


def protected_durable_authority_harness_evidence_valid_v2(value: Any) -> bool:
    if type(value) is not ProtectedDurableAuthorityHarnessEvidenceV2:
        return False
    evidence = value.evidence
    checks = evidence.get("checks") if type(evidence) is dict else None
    try:
        return bool(
            type(evidence) is dict
            and set(evidence) == _EVIDENCE_KEYS
            and authority_v2.protected_durable_reconciliation_authority_receipt_valid_v2(value.issued_receipt)
            and authority_v2.protected_durable_reconciliation_authority_receipt_valid_v2(value.consumed_receipt)
            and authority_v2.protected_durable_reconciliation_authority_receipt_valid_v2(value.recovered_receipt)
            and evidence["evidence_version"] == DURABLE_AUTHORITY_HARNESS_EVIDENCE_VERSION_V2
            and evidence["issued_receipt_sha256"] == value.issued_receipt.receipt_sha256
            and evidence["consumed_receipt_sha256"] == value.consumed_receipt.receipt_sha256
            and evidence["recovered_receipt_sha256"] == value.recovered_receipt.receipt_sha256
            and isinstance(checks, list)
            and [item["name"] for item in checks] == list(_CHECK_NAMES)
            and all(type(item) is dict and set(item) == _CHECK_KEYS and item["passed"] is True for item in checks)
            and evidence["check_count"] == len(_CHECK_NAMES)
            and evidence["passed_count"] == len(_CHECK_NAMES)
            and evidence["temporary_filesystem_accessed"] is True
            and evidence["temporary_write_executed"] is True
            and evidence["temporary_storage_removed"] is True
            and value.issued_receipt.receipt[
                "root_authority_attestation_sha256"
            ] == evidence["root_authority_attestation_sha256"]
            and evidence["root_authority_key_epoch"] == 2
            and evidence["interprocess_lock_acquired"] is True
            and evidence["restart_persistent_reference"] is True
            and evidence["production_durable"] is False
            and all(
                evidence[key] is False
                for key in (
                    "real_registry_accessed", "network_accessed", "broker_called",
                    "production_authority", "runtime_integrated",
                    "activation_allowed", "live_allowed",
                )
            )
            and evidence["no_order_sent"] is True
            and evidence["synthetic_only"] is True
            and value.evidence_sha256 == evidence["evidence_sha256"]
            and hmac.compare_digest(
                evidence["evidence_sha256"],
                durable_authority_harness_evidence_sha256_v2(evidence),
            )
        )
    except Exception:
        return False


def run_durable_authority_harness_v2() -> dict[str, Any]:
    base = {
        "ok": False,
        "status": "DURABLE_AUTHORITY_HARNESS_V2_FAILED_CLOSED",
        "reason": None,
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_V1_BACKEND_V2_PROTECTED_RECONCILIATION_DURABLE_AUTHORITY_HARNESS_V2_VERSION,
        "protected_evidence": None,
        "check_count": 0,
        "passed_count": 0,
        "temporary_filesystem_accessed": False,
        "temporary_write_executed": False,
        "temporary_storage_removed": False,
        "interprocess_lock_acquired": False,
        "real_registry_accessed": False,
        "network_accessed": False,
        "broker_called": False,
        "production_authority": False,
        "runtime_integrated": False,
        "activation_allowed": False,
        "live_allowed": False,
        "no_order_sent": True,
    }
    try:
        default_off = authority_v2.DormantDurableReconciliationAuthorityLedgerV2().open_offline()
        upstream = obligation_harness_v2.run_protected_reconciliation_obligation_harness_v2()
        obligation = upstream.get("terminal_ambiguity_obligation")
        if upstream.get("ok") is not True or obligation is None:
            base["reason"] = "UPSTREAM_OPEN_OBLIGATION_INVALID"
            return base
        root_identity = _sha({"durable-authority-root": obligation.obligation_sha256})
        grant = _sha({"durable-authority-grant": obligation.obligation_sha256})
        now_epoch = obligation.obligation["created_at_epoch"] + 1
        issue_args = {
            "obligation_sha256": obligation.obligation_sha256,
            "obligation_id_sha256": obligation.obligation["obligation_id_sha256"],
            "transaction_sha256": obligation.obligation["transaction_sha256"],
            "subject_binding_sha256": obligation.obligation_sha256,
            "grant_sha256": grant,
            "issued_at_epoch": now_epoch,
            "expires_at_epoch": now_epoch + 300,
        }
        second_obligation = _sha({"second-obligation": obligation.obligation_sha256})
        second_args = {
            **issue_args,
            "obligation_sha256": second_obligation,
            "obligation_id_sha256": _sha({"second-id": second_obligation}),
            "transaction_sha256": _sha({"second-transaction": second_obligation}),
            "subject_binding_sha256": second_obligation,
            "grant_sha256": _sha({"second-grant": second_obligation}),
        }
        temp_path: Path | None = None
        with tempfile.TemporaryDirectory(prefix="c3-durable-authority-v2-") as directory:
            temp_path = Path(directory)
            storage = _storage(temp_path)
            binding = authority_v2.durable_authority_storage_binding_sha256_v2(storage)
            initial_root = _root_attestation(root_identity, binding)
            rotated_root = _root_attestation(
                root_identity,
                binding,
                key_epoch=2,
                previous_attestation_sha256=initial_root["attestation_sha256"],
            )
            first = _ledger(
                temp_path, storage, root_identity, root_attestation=initial_root
            )
            opened = first.open_offline()
            rotation = first.rotate_root_authority_offline(
                rotated_root, rotated_at_epoch=now_epoch
            )
            restarted = _ledger(
                temp_path, storage, root_identity, root_attestation=rotated_root
            )
            reopened_after_rotation = restarted.open_offline()
            issued = restarted.issue_once_offline(**issue_args)
            issued_receipt = issued.get("protected_receipt")
            journal_count_after_issue = len(wal_v2.read_journal(storage))

            restarted_again = _ledger(
                temp_path, storage, root_identity, root_attestation=rotated_root
            )
            reopened = restarted_again.open_offline()
            idempotent = restarted_again.issue_once_offline(**issue_args)
            journal_count_after_idempotent = len(wal_v2.read_journal(storage))
            divergent = restarted_again.issue_once_offline(
                **{**issue_args, "grant_sha256": _sha("divergent-remint")}
            )
            terminal_sha = _sha({"terminal": obligation.obligation_sha256})
            consumed = restarted_again.consume_once_offline(
                issued_receipt,
                terminal_evidence_sha256=terminal_sha,
                consumed_at_epoch=now_epoch + 1,
            )
            consumed_receipt = consumed.get("protected_receipt")

            after_consumption = _ledger(
                temp_path, storage, root_identity, root_attestation=rotated_root
            )
            reopened_again = after_consumption.open_offline()
            second_consumption = after_consumption.consume_once_offline(
                issued_receipt,
                terminal_evidence_sha256=terminal_sha,
                consumed_at_epoch=now_epoch + 2,
            )

            def crash_after_prepare(stage: str) -> None:
                if stage == wal_v2.AFTER_PREPARED:
                    raise RuntimeError("synthetic-crash-after-prepare")

            interrupted = after_consumption.issue_once_offline(
                **second_args, fault_hook=crash_after_prepare
            )
            pending_before_recovery = wal_v2.inspect_wal_recovery_state(storage)
            recovery_instance = _ledger(
                temp_path, storage, root_identity, root_attestation=rotated_root
            )
            recovered = recovery_instance.recover_offline()
            recovered_issue = recovery_instance.issue_once_offline(**second_args)
            recovered_receipt = recovered_issue.get("protected_receipt")

            guard_backend = storage_v1.CrossPlatformInterprocessFileLockBackendV1(
                temp_path, enabled=True
            )
            guard = guard_backend.acquire(binding, 1.0)
            if guard is None:
                base["reason"] = "SYNTHETIC_CONTENTION_GUARD_NOT_ACQUIRED"
                return base
            try:
                contended = _ledger(
                    temp_path,
                    storage,
                    root_identity,
                    lock_timeout_seconds=0.05,
                    root_attestation=rotated_root,
                ).open_offline()
            finally:
                guard.release()

            substituted_root = _sha("substituted-durable-root")
            substituted_attestation = _root_attestation(
                substituted_root, binding
            )
            substituted = _ledger(
                temp_path,
                storage,
                substituted_root,
                root_attestation=substituted_attestation,
            ).open_offline()
            forged_root = copy.deepcopy(rotated_root)
            forged_root["signature_sha256"] = _sha("forged-root-signature")
            forged_root["attestation_sha256"] = (
                authority_v2.authenticated_root_authority_attestation_sha256_v2(
                    forged_root
                )
            )
            forged = _ledger(
                temp_path,
                storage,
                root_identity,
                root_attestation=forged_root,
            ).open_offline()
            generation_before_corruption = recovered_issue.get("generation")
            with Path(storage.journal_path).open("ab") as handle:
                handle.write(b"{corrupt-journal-record}\n")
                handle.flush()
            corrupt = _ledger(
                temp_path, storage, root_identity, root_attestation=rotated_root
            ).recover_offline()

            if any(item is None for item in (issued_receipt, consumed_receipt, recovered_receipt)):
                base["reason"] = "DURABLE_AUTHORITY_RECEIPT_MISSING"
                return base
            checks_by_name = {
                "TEMPORARY_LEDGER_OPENED_WITH_STABLE_ROOT": opened["ok"] is True and opened["generation"] == 0 and binding == authority_v2.durable_authority_storage_binding_sha256_v2(storage),
                "ROOT_AUTHORITY_SIGNATURE_VERIFIED": authority_v2.authenticated_root_authority_attestation_verified_v2(initial_root, _SyntheticRootAuthorityVerifierV2()),
                "ROOT_AUTHORITY_ROTATION_WAL_COMMITTED": rotation["ok"] is True and rotation["status"] == "ROOT_AUTHORITY_ROTATED_OFFLINE" and rotation["root_authority_attestation_sha256"] == rotated_root["attestation_sha256"],
                "ROTATED_ROOT_RECOVERED_AFTER_RESTART": reopened_after_rotation["ok"] is True and reopened_after_rotation["generation"] == rotation["generation"],
                "FORGED_ROOT_SIGNATURE_REJECTED": forged["ok"] is False and forged["reason"] == "AUTHENTICATED_ROOT_AUTHORITY_REQUIRED",
                "AUTHORITY_ISSUED_ONCE": issued["ok"] is True and issued["status"] == "DURABLE_AUTHORITY_ISSUED_OFFLINE" and issued_receipt.record["issuance_count"] == 1,
                "RESTART_REOPENS_SAME_LEDGER": reopened["ok"] is True and reopened["generation"] == issued["generation"],
                "SAME_ISSUE_IS_IDEMPOTENT_AFTER_RESTART": idempotent["ok"] is True and idempotent["status"] == "DURABLE_AUTHORITY_ALREADY_ISSUED_IDEMPOTENT" and idempotent["protected_receipt"].receipt_sha256 == issued_receipt.receipt_sha256,
                "SAME_ISSUE_DOES_NOT_APPEND_WAL": journal_count_after_issue == journal_count_after_idempotent,
                "DIVERGENT_REMINT_REJECTED": divergent["ok"] is False and divergent["reason"] == "DURABLE_AUTHORITY_REISSUE_CONFLICT",
                "AUTHORITY_CONSUMED_EXACTLY_ONCE": consumed["ok"] is True and consumed_receipt.record["state"] == "CONSUMED" and consumed_receipt.record["consumption_count"] == 1,
                "SECOND_CONSUMPTION_REJECTED_AFTER_RESTART": reopened_again["ok"] is True and second_consumption["ok"] is False and second_consumption["reason"] == "DURABLE_AUTHORITY_ALREADY_CONSUMED",
                "CRASH_AFTER_PREPARE_FAILS_CLOSED": interrupted["ok"] is False and interrupted["reason"] == "DURABLE_AUTHORITY_ISSUE_INTERRUPTED" and interrupted["write_executed"] is True and pending_before_recovery.status == wal_v2.PREPARED_PENDING,
                "PREPARED_ISSUE_RECOVERED_AFTER_RESTART": recovered["ok"] is True and recovered["wal_state"] == wal_v2.CLEAN and recovered_issue["ok"] is True,
                "RECOVERED_ISSUE_REMAINS_IDEMPOTENT": recovered_issue["status"] == "DURABLE_AUTHORITY_ALREADY_ISSUED_IDEMPOTENT" and recovered_receipt.record["issuance_count"] == 1,
                "CONCURRENT_LOCK_CONTENTION_FAILS_CLOSED": contended["ok"] is False and contended["reason"] == "INTERPROCESS_LOCK_TIMEOUT" and contended["write_executed"] is False,
                "ROOT_SUBSTITUTION_REJECTED": substituted["ok"] is False and substituted["reason"] == "DURABLE_AUTHORITY_SNAPSHOT_INVALID",
                "JOURNAL_CORRUPTION_FAILS_CLOSED": corrupt["ok"] is False and corrupt["reason"] == "DURABLE_AUTHORITY_WAL_RECOVERY_FAILED",
                "PROTECTED_RECEIPTS_HIDE_RECORDS": repr(issued_receipt) == "ProtectedDurableReconciliationAuthorityReceiptV2(<protected>)" and repr(consumed_receipt) == "ProtectedDurableReconciliationAuthorityReceiptV2(<protected>)",
                "NO_REAL_REGISTRY_RUNTIME_NETWORK_OR_BROKER_ACCESS": all(result[key] is False for result in (opened, rotation, reopened_after_rotation, forged, issued, reopened, idempotent, divergent, consumed, reopened_again, second_consumption, interrupted, recovered, recovered_issue, contended, substituted, corrupt) for key in ("real_registry_accessed", "network_accessed", "broker_called", "production_authority", "runtime_integrated", "activation_allowed", "live_allowed")) and default_off["filesystem_accessed"] is False,
            }
            checks = [{"name": name, "passed": checks_by_name[name] is True} for name in _CHECK_NAMES]
            if not all(item["passed"] for item in checks):
                base["reason"] = "DURABLE_AUTHORITY_HARNESS_ORACLE_FAILED"
                base["failed_checks"] = [item["name"] for item in checks if not item["passed"]]
                return base
            evidence_seed = {
                "evidence_version": DURABLE_AUTHORITY_HARNESS_EVIDENCE_VERSION_V2,
                "root_identity_sha256": root_identity,
                "storage_binding_sha256": binding,
                "root_authority_attestation_sha256": rotated_root[
                    "attestation_sha256"
                ],
                "root_authority_key_epoch": rotated_root["key_epoch"],
                "issued_receipt_sha256": issued_receipt.receipt_sha256,
                "consumed_receipt_sha256": consumed_receipt.receipt_sha256,
                "recovered_receipt_sha256": recovered_receipt.receipt_sha256,
                "final_generation_before_corruption": generation_before_corruption,
                "checks": checks,
                "check_count": len(checks),
                "passed_count": sum(item["passed"] for item in checks),
                "temporary_filesystem_accessed": True,
                "temporary_write_executed": True,
                "temporary_storage_removed": True,
                "interprocess_lock_acquired": True,
                "restart_persistent_reference": True,
                "production_durable": False,
                "real_registry_accessed": False,
                "network_accessed": False,
                "broker_called": False,
                "production_authority": False,
                "runtime_integrated": False,
                "activation_allowed": False,
                "live_allowed": False,
                "no_order_sent": True,
                "synthetic_only": True,
            }
        temporary_removed = temp_path is not None and not temp_path.exists()
        evidence_seed["temporary_storage_removed"] = temporary_removed
        evidence_seed["evidence_sha256"] = durable_authority_harness_evidence_sha256_v2(evidence_seed)
        protected_evidence = ProtectedDurableAuthorityHarnessEvidenceV2(
            issued_receipt=issued_receipt,
            consumed_receipt=consumed_receipt,
            recovered_receipt=recovered_receipt,
            evidence=copy.deepcopy(evidence_seed),
            evidence_sha256=evidence_seed["evidence_sha256"],
        )
        if not protected_durable_authority_harness_evidence_valid_v2(protected_evidence):
            base["reason"] = "DURABLE_AUTHORITY_HARNESS_EVIDENCE_INTERNAL_INVALID"
            return base
    except Exception as exc:
        base["reason"] = "DURABLE_AUTHORITY_HARNESS_EXCEPTION"
        base["diagnostic"] = type(exc).__name__
        return base
    base.update(
        {
            "ok": True,
            "status": "DURABLE_AUTHORITY_HARNESS_PASSED_TEMP_STORAGE_ONLY",
            "protected_evidence": protected_evidence,
            "evidence_sha256": protected_evidence.evidence_sha256,
            "check_count": len(_CHECK_NAMES),
            "passed_count": len(_CHECK_NAMES),
            "temporary_filesystem_accessed": True,
            "temporary_write_executed": True,
            "temporary_storage_removed": temporary_removed,
            "interprocess_lock_acquired": True,
        }
    )
    return base


__all__ = [
    "DURABLE_AUTHORITY_HARNESS_EVIDENCE_VERSION_V2",
    "ProtectedDurableAuthorityHarnessEvidenceV2",
    "durable_authority_harness_evidence_sha256_v2",
    "protected_durable_authority_harness_evidence_valid_v2",
    "run_durable_authority_harness_v2",
]
