"""Offline conformance validator for synthetic production-evidence fixtures.

Conformance here means only that a synthetic bundle satisfies the dormant
schema and its cross-bindings.  The validator deliberately rejects durable,
authenticated, real-Registry, runtime-admissible, or production-evidence
claims and therefore cannot authorize recovery or readiness.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_schema_contract_v1 as schema_contract


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_CONFORMANCE_CONTRACT_V1_VERSION = (
    "2026-09-09-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-PRODUCTION-STARTUP-RECOVERY-EVIDENCE-CONFORMANCE-CONTRACT-V1"
)
OFFLINE_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_CONFORMANCE_SCOPE_ATTESTATION_V1 = (
    "C3_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_CONFORMANCE_SYNTHETIC_ONLY_V1"
)
SYNTHETIC_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_BUNDLE_VERSION_V1 = (
    "C3_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_BUNDLE_SYNTHETIC_FIXTURE_V1"
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_STATES = ("PREPARED", "RESOLVED", "COMMITTED", "ABORTED", "ROLLED_BACK")
_BUNDLE_KEYS = frozenset(
    {
        "bundle_version",
        "schema_sha256",
        "initial_backend_snapshot",
        "initial_transaction_log_audit",
        "initial_prepared_catalog",
        "initial_resolved_catalog",
        "final_backend_snapshot",
        "final_transaction_log_audit",
        "final_prepared_catalog",
        "final_resolved_catalog",
        "terminal_receipts",
        "completion_attestation",
        "synthetic_fixture_only",
        "durable",
        "production_evidence",
        "production_authority",
        "runtime_admissible",
        "bundle_sha256",
    }
)


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _canonical_copy(value: Any) -> Any:
    return json.loads(_canonical_json(value))


def _stable_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _valid_sha256(value: Any) -> str:
    normalized = str(value or "").lower().strip()
    return normalized if _SHA256_RE.fullmatch(normalized) else ""


def synthetic_evidence_artifact_sha256_v1(
    value: Mapping[str, Any], hash_field: str
) -> str:
    if not isinstance(value, Mapping) or not isinstance(hash_field, str):
        raise TypeError("artifact mapping and hash field required")
    return _stable_sha256(
        {key: item for key, item in value.items() if key != hash_field}
    )


def synthetic_evidence_bundle_sha256_v1(value: Mapping[str, Any]) -> str:
    if not isinstance(value, Mapping):
        raise TypeError("bundle must be a mapping")
    return synthetic_evidence_artifact_sha256_v1(value, "bundle_sha256")


def synthetic_completion_attestation_sha256_v1(
    value: Mapping[str, Any],
) -> str:
    if not isinstance(value, Mapping):
        raise TypeError("completion attestation must be a mapping")
    return synthetic_evidence_artifact_sha256_v1(
        value, "startup_recovery_attestation_sha256"
    )


def synthetic_transaction_log_audit_sha256_v1(
    value: Mapping[str, Any],
) -> str:
    if not isinstance(value, Mapping):
        raise TypeError("transaction log audit must be a mapping")
    return synthetic_evidence_artifact_sha256_v1(value, "audit_sha256")


def synthetic_terminal_receipt_set_sha256_v1(
    receipts: list[Mapping[str, Any]],
) -> str:
    if not isinstance(receipts, list) or any(
        not isinstance(receipt, Mapping) for receipt in receipts
    ):
        raise TypeError("terminal receipts must be a list of mappings")
    return _stable_sha256(
        [receipt.get("receipt_sha256") for receipt in receipts]
    )


def synthetic_terminal_receipt_sha256_v1(
    value: Mapping[str, Any],
) -> str:
    if not isinstance(value, Mapping):
        raise TypeError("terminal receipt must be a mapping")
    return synthetic_evidence_artifact_sha256_v1(value, "receipt_sha256")


def _sealed_mapping_valid(
    value: Any,
    expected_fields: Any,
    hash_field: str,
) -> bool:
    if not isinstance(value, Mapping) or set(value) != set(expected_fields):
        return False
    supplied_sha = _valid_sha256(value.get(hash_field))
    try:
        return bool(
            supplied_sha
            and hmac.compare_digest(
                supplied_sha,
                synthetic_evidence_artifact_sha256_v1(value, hash_field),
            )
        )
    except Exception:
        return False


def _snapshot_valid(
    value: Any,
    schema: Mapping[str, Any],
) -> bool:
    if not _sealed_mapping_valid(
        value, schema["backend_snapshot_fields"], "snapshot_sha256"
    ):
        return False
    try:
        return bool(
            value.get("schema_sha256") == schema["schema_sha256"]
            and value.get("provider_binding_sha256")
            == schema["provider_binding_sha256"]
            and value.get("backend_instance_sha256")
            == schema["source_backend_instance_sha256"]
            and value.get("registry_path_binding_sha256")
            == schema["source_registry_path_binding_sha256"]
            and value.get("lock_namespace_sha256")
            == schema["source_lock_namespace_sha256"]
            and value.get("backend_capability_attestation_sha256")
            == schema["source_backend_capability_declaration_sha256"]
            and all(
                _valid_sha256(value.get(field_name))
                for field_name in (
                    "backend_module_source_sha256",
                    "wal_storage_binding_sha256",
                    "resolved_ledger_storage_binding_sha256",
                    "backend_capability_probe_receipt_sha256",
                    "authenticated_authority_receipt_sha256",
                )
            )
            and type(value.get("generation")) is int
            and value.get("generation") >= 0
            and type(value.get("observed_at_epoch")) is int
            and value.get("observed_at_epoch") >= 0
            and value.get("durable") is False
            and value.get("production_evidence") is False
        )
    except Exception:
        return False


def _prepared_record_valid(value: Any, schema: Mapping[str, Any]) -> bool:
    if not _sealed_mapping_valid(
        value, schema["prepared_record_fields"], "record_sha256"
    ):
        return False
    try:
        return bool(
            all(
                _valid_sha256(value.get(field_name))
                for field_name in (
                    "transaction_sha256",
                    "request_sha256",
                    "prepared_record_sha256",
                    "source_raw_document_sha256",
                    "candidate_raw_document_sha256",
                    "previous_maintenance_epoch",
                )
            )
            and type(value.get("prepared_at_epoch")) is int
            and type(value.get("deadline_epoch")) is int
            and value.get("prepared_at_epoch") < value.get("deadline_epoch")
            and value.get("state") == "PREPARED"
        )
    except Exception:
        return False


def _resolved_record_valid(value: Any, schema: Mapping[str, Any]) -> bool:
    if not _sealed_mapping_valid(
        value, schema["resolved_record_fields"], "record_sha256"
    ):
        return False
    try:
        return bool(
            all(
                _valid_sha256(value.get(field_name))
                for field_name in (
                    "obligation_sha256",
                    "transaction_sha256",
                    "resolution_receipt_sha256",
                    "terminal_result_sha256",
                )
            )
            and type(value.get("resolved_at_epoch")) is int
            and value.get("resolved_at_epoch") >= 0
            and value.get("projection_committed") is False
            and value.get("state") == "RESOLVED"
        )
    except Exception:
        return False


def _terminal_receipt_valid(
    value: Any,
    schema: Mapping[str, Any],
    maintenance_epoch: str,
) -> bool:
    if not _sealed_mapping_valid(
        value, schema["terminal_receipt_fields"], "receipt_sha256"
    ):
        return False
    try:
        return bool(
            value.get("schema_sha256") == schema["schema_sha256"]
            and value.get("provider_binding_sha256")
            == schema["provider_binding_sha256"]
            and value.get("backend_instance_sha256")
            == schema["source_backend_instance_sha256"]
            and _valid_sha256(value.get("transaction_sha256"))
            and value.get("source_state") in {"PREPARED", "RESOLVED"}
            and value.get("terminal_state")
            in {"COMMITTED", "ABORTED", "ROLLED_BACK"}
            and value.get("maintenance_epoch") == maintenance_epoch
            and _valid_sha256(value.get("previous_maintenance_epoch"))
            and value.get("previous_maintenance_epoch")
            != value.get("maintenance_epoch")
            and _valid_sha256(value.get("backend_result_sha256"))
            and value.get("write_state_known") is True
            and type(value.get("write_executed")) is bool
            and type(value.get("registry_write")) is bool
            and (
                value.get("registry_write") is False
                or value.get("write_executed") is True
            )
            and type(value.get("completed_at_epoch")) is int
            and value.get("completed_at_epoch") >= 0
            and value.get("durable") is False
            and value.get("production_evidence") is False
            and _valid_sha256(
                value.get("authenticated_authority_receipt_sha256")
            )
        )
    except Exception:
        return False


def _catalog_valid(
    value: Any,
    snapshot: Mapping[str, Any],
    schema: Mapping[str, Any],
    *,
    resolved: bool,
) -> bool:
    fields_key = "resolved_catalog_fields" if resolved else "prepared_catalog_fields"
    count_key = "resolved_count" if resolved else "prepared_count"
    storage_key = (
        "resolved_ledger_storage_binding_sha256"
        if resolved
        else "wal_storage_binding_sha256"
    )
    record_validator = _resolved_record_valid if resolved else _prepared_record_valid
    if not _sealed_mapping_valid(
        value, schema[fields_key], "catalog_sha256"
    ):
        return False
    records = value.get("records")
    if not isinstance(records, list) or any(
        not record_validator(record, schema) for record in records
    ):
        return False
    record_hashes = [record["record_sha256"] for record in records]
    try:
        return bool(
            value.get("schema_sha256") == schema["schema_sha256"]
            and value.get("backend_instance_sha256")
            == snapshot["backend_instance_sha256"]
            and value.get("backend_snapshot_sha256")
            == snapshot["snapshot_sha256"]
            and value.get("lock_namespace_sha256")
            == snapshot["lock_namespace_sha256"]
            and value.get(storage_key) == snapshot[storage_key]
            and (
                resolved
                or value.get("registry_path_binding_sha256")
                == snapshot["registry_path_binding_sha256"]
            )
            and value.get("generation") == snapshot["generation"]
            and value.get("record_count") == len(records)
            and value.get(count_key) == len(records)
            and record_hashes == sorted(record_hashes)
            and len(record_hashes) == len(set(record_hashes))
            and value.get("complete_scan_verified") is True
            and value.get("durable") is False
            and value.get("production_evidence") is False
            and _valid_sha256(
                value.get("authenticated_authority_receipt_sha256")
            )
        )
    except Exception:
        return False


def _audit_valid(
    value: Any,
    snapshot: Mapping[str, Any],
    schema: Mapping[str, Any],
) -> bool:
    if not _sealed_mapping_valid(
        value, schema["transaction_log_audit_fields"], "audit_sha256"
    ):
        return False
    state_counts = value.get("state_counts")
    latest_counts = value.get("latest_state_counts")
    if not (
        isinstance(state_counts, Mapping)
        and set(state_counts) == set(_STATES)
        and isinstance(latest_counts, Mapping)
        and set(latest_counts) == set(_STATES)
        and all(type(state_counts[state]) is int for state in _STATES)
        and all(type(latest_counts[state]) is int for state in _STATES)
        and all(state_counts[state] >= 0 for state in _STATES)
        and all(latest_counts[state] >= 0 for state in _STATES)
    ):
        return False
    try:
        return bool(
            value.get("schema_sha256") == schema["schema_sha256"]
            and value.get("backend_instance_sha256")
            == snapshot["backend_instance_sha256"]
            and value.get("backend_snapshot_sha256")
            == snapshot["snapshot_sha256"]
            and value.get("wal_storage_binding_sha256")
            == snapshot["wal_storage_binding_sha256"]
            and value.get("resolved_ledger_storage_binding_sha256")
            == snapshot["resolved_ledger_storage_binding_sha256"]
            and value.get("lock_namespace_sha256")
            == snapshot["lock_namespace_sha256"]
            and value.get("wal_record_count") == sum(state_counts.values())
            and value.get("transaction_count") == sum(latest_counts.values())
            and value.get("unresolved_prepared_count")
            == latest_counts["PREPARED"]
            and value.get("unresolved_resolved_count")
            == latest_counts["RESOLVED"]
            and _valid_sha256(value.get("hash_chain_head_sha256"))
            and value.get("wal_integrity_verified") is True
            and value.get("catalog_crosscheck_verified") is True
            and value.get("fsync_capability_verified") is False
            and value.get("durable") is False
            and value.get("production_evidence") is False
            and _valid_sha256(
                value.get("authenticated_authority_receipt_sha256")
            )
        )
    except Exception:
        return False


def _completion_valid(
    completion: Any,
    schema: Mapping[str, Any],
    initial_snapshot: Mapping[str, Any],
    initial_audit: Mapping[str, Any],
    initial_prepared: Mapping[str, Any],
    initial_resolved: Mapping[str, Any],
    final_snapshot: Mapping[str, Any],
    final_audit: Mapping[str, Any],
    final_prepared: Mapping[str, Any],
    final_resolved: Mapping[str, Any],
    terminal_receipts: list[Mapping[str, Any]],
) -> bool:
    if not _sealed_mapping_valid(
        completion,
        schema["completion_attestation_fields"],
        "startup_recovery_attestation_sha256",
    ):
        return False
    expected_links = {
        "initial_backend_snapshot_sha256": initial_snapshot["snapshot_sha256"],
        "initial_transaction_log_audit_sha256": initial_audit["audit_sha256"],
        "initial_prepared_catalog_sha256": initial_prepared["catalog_sha256"],
        "initial_resolved_catalog_sha256": initial_resolved["catalog_sha256"],
        "final_backend_snapshot_sha256": final_snapshot["snapshot_sha256"],
        "final_transaction_log_audit_sha256": final_audit["audit_sha256"],
        "final_prepared_catalog_sha256": final_prepared["catalog_sha256"],
        "final_resolved_catalog_sha256": final_resolved["catalog_sha256"],
    }
    try:
        return bool(
            completion.get("evidence_version")
            == schema_contract.FUTURE_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_VERSION_V1
            and completion.get("schema_sha256") == schema["schema_sha256"]
            and completion.get("provider_binding_sha256")
            == schema["provider_binding_sha256"]
            and completion.get("backend_instance_sha256")
            == schema["source_backend_instance_sha256"]
            and completion.get("registry_path_binding_sha256")
            == schema["source_registry_path_binding_sha256"]
            and completion.get("lock_namespace_sha256")
            == schema["source_lock_namespace_sha256"]
            and completion.get("wal_storage_binding_sha256")
            == initial_snapshot["wal_storage_binding_sha256"]
            == final_snapshot["wal_storage_binding_sha256"]
            and completion.get("resolved_ledger_storage_binding_sha256")
            == initial_snapshot["resolved_ledger_storage_binding_sha256"]
            == final_snapshot["resolved_ledger_storage_binding_sha256"]
            and all(
                completion.get(key) == expected
                for key, expected in expected_links.items()
            )
            and all(
                _valid_sha256(completion.get(field_name))
                for field_name in ("maintenance_epoch", "maintenance_lease_receipt_sha256")
            )
            and completion.get("terminal_receipt_set_sha256")
            == synthetic_terminal_receipt_set_sha256_v1(terminal_receipts)
            and completion.get("prepared_transactions_before")
            == initial_prepared["prepared_count"]
            == initial_audit["unresolved_prepared_count"]
            and completion.get("resolved_transactions_before")
            == initial_resolved["resolved_count"]
            == initial_audit["unresolved_resolved_count"]
            and completion.get("prepared_transactions_after")
            == final_prepared["prepared_count"]
            == final_audit["unresolved_prepared_count"]
            == 0
            and completion.get("resolved_transactions_after")
            == final_resolved["resolved_count"]
            == final_audit["unresolved_resolved_count"]
            == 0
            and completion.get("unresolved_transactions_after") == 0
            and completion.get("writers_blocked_entire_window") is True
            and completion.get("same_maintenance_epoch_used") is True
            and completion.get("fresh_maintenance_epoch_verified") is True
            and completion.get("all_catalogs_drained") is True
            and completion.get("wal_integrity_verified") is True
            and completion.get("durability_verified") is False
            and completion.get("authenticated_authority_verified") is False
            and completion.get("write_state_known") is True
            and type(completion.get("write_executed")) is bool
            and type(completion.get("registry_write")) is bool
            and (
                completion.get("registry_write") is False
                or completion.get("write_executed") is True
            )
            and completion.get("real_registry_accessed") is False
            and completion.get("network_accessed") is False
            and completion.get("broker_called") is False
            and completion.get("no_order_sent") is True
            and completion.get("production_evidence") is False
            and completion.get("runtime_admissible") is False
        )
    except Exception:
        return False


@dataclass(frozen=True)
class OfflineProductionStartupRecoveryEvidenceConformanceConfigV1:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    expected_schema_sha256: str | None = field(default=None, repr=False)


class OfflineProductionStartupRecoveryEvidenceConformanceV1:
    def __init__(
        self,
        *,
        config: OfflineProductionStartupRecoveryEvidenceConformanceConfigV1
        | None = None,
    ) -> None:
        self._config = (
            config or OfflineProductionStartupRecoveryEvidenceConformanceConfigV1()
        )

    def __repr__(self) -> str:
        return "OfflineProductionStartupRecoveryEvidenceConformanceV1(<protected>)"

    @staticmethod
    def _base() -> dict[str, Any]:
        return {
            "ok": False,
            "status": "C3_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_CONFORMANCE_FAILED_CLOSED",
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_CONFORMANCE_CONTRACT_V1_VERSION,
            "offline_only": True,
            "synthetic_fixture_only": True,
            "schema_verified": False,
            "bundle_hash_verified": False,
            "initial_evidence_verified": False,
            "final_evidence_verified": False,
            "cross_binding_verified": False,
            "safety_vector_verified": False,
            "schema_conforms": False,
            "production_admissible": False,
            "production_authority": False,
            "production_ready": False,
            "runtime_integrated": False,
            "recovery_execution_allowed": False,
            "activation_allowed": False,
            "live_allowed": False,
            "provider_called": False,
            "store_called": False,
            "backend_called": False,
            "filesystem_accessed": False,
            "real_registry_accessed": False,
            "network_accessed": False,
            "broker_called": False,
            "write_executed": False,
            "registry_write": False,
            "no_order_sent": True,
            "reasons": [],
        }

    def audit_offline(
        self,
        *,
        protected_schema: schema_contract.ProtectedProductionStartupRecoveryEvidenceSchemaV1,
        fixture_bundle: Mapping[str, Any],
    ) -> dict[str, Any]:
        result = self._base()
        if self._config.enabled is not True:
            result["reasons"].append(
                "PRODUCTION_RECOVERY_EVIDENCE_CONFORMANCE_DEFAULT_OFF"
            )
            return result
        if (
            self._config.scope_attestation
            != OFFLINE_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_CONFORMANCE_SCOPE_ATTESTATION_V1
        ):
            result["reasons"].append(
                "PRODUCTION_RECOVERY_EVIDENCE_CONFORMANCE_SCOPE_INVALID"
            )
            return result
        expected_schema_sha = _valid_sha256(
            self._config.expected_schema_sha256
        )
        if not (
            expected_schema_sha
            and schema_contract.protected_production_startup_recovery_evidence_schema_valid_v1(
                protected_schema
            )
            and hmac.compare_digest(
                protected_schema.schema_sha256, expected_schema_sha
            )
        ):
            result["reasons"].append("PROTECTED_RECOVERY_EVIDENCE_SCHEMA_INVALID")
            return result
        result["schema_verified"] = True
        try:
            bundle = _canonical_copy(dict(fixture_bundle))
        except Exception:
            result["reasons"].append("SYNTHETIC_EVIDENCE_BUNDLE_INVALID")
            return result
        if not (
            set(bundle) == _BUNDLE_KEYS
            and bundle.get("bundle_version")
            == SYNTHETIC_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_BUNDLE_VERSION_V1
            and bundle.get("schema_sha256") == expected_schema_sha
            and _valid_sha256(bundle.get("bundle_sha256"))
            and hmac.compare_digest(
                bundle["bundle_sha256"],
                synthetic_evidence_bundle_sha256_v1(bundle),
            )
        ):
            result["reasons"].append("SYNTHETIC_EVIDENCE_BUNDLE_HASH_INVALID")
            return result
        result["bundle_hash_verified"] = True
        schema = protected_schema.schema
        initial_snapshot = bundle["initial_backend_snapshot"]
        initial_audit = bundle["initial_transaction_log_audit"]
        initial_prepared = bundle["initial_prepared_catalog"]
        initial_resolved = bundle["initial_resolved_catalog"]
        final_snapshot = bundle["final_backend_snapshot"]
        final_audit = bundle["final_transaction_log_audit"]
        final_prepared = bundle["final_prepared_catalog"]
        final_resolved = bundle["final_resolved_catalog"]
        terminal_receipts = bundle["terminal_receipts"]
        if not (
            _snapshot_valid(initial_snapshot, schema)
            and _audit_valid(initial_audit, initial_snapshot, schema)
            and _catalog_valid(
                initial_prepared, initial_snapshot, schema, resolved=False
            )
            and _catalog_valid(
                initial_resolved, initial_snapshot, schema, resolved=True
            )
        ):
            result["reasons"].append("INITIAL_SYNTHETIC_EVIDENCE_INVALID")
            return result
        result["initial_evidence_verified"] = True
        if not (
            _snapshot_valid(final_snapshot, schema)
            and _audit_valid(final_audit, final_snapshot, schema)
            and _catalog_valid(
                final_prepared, final_snapshot, schema, resolved=False
            )
            and _catalog_valid(
                final_resolved, final_snapshot, schema, resolved=True
            )
        ):
            result["reasons"].append("FINAL_SYNTHETIC_EVIDENCE_INVALID")
            return result
        result["final_evidence_verified"] = True
        completion = bundle["completion_attestation"]
        maintenance_epoch = completion.get("maintenance_epoch")
        expected_sources = {
            record["transaction_sha256"]: "PREPARED"
            for record in initial_prepared["records"]
        }
        expected_sources.update(
            {
                record["transaction_sha256"]: "RESOLVED"
                for record in initial_resolved["records"]
            }
        )
        if not (
            isinstance(terminal_receipts, list)
            and len(terminal_receipts) == len(expected_sources)
            and all(
                _terminal_receipt_valid(receipt, schema, maintenance_epoch)
                for receipt in terminal_receipts
            )
            and [receipt["receipt_sha256"] for receipt in terminal_receipts]
            == sorted(receipt["receipt_sha256"] for receipt in terminal_receipts)
            and len(
                {receipt["transaction_sha256"] for receipt in terminal_receipts}
            )
            == len(terminal_receipts)
            and {
                receipt["transaction_sha256"]: receipt["source_state"]
                for receipt in terminal_receipts
            }
            == expected_sources
            and all(
                maintenance_epoch != record["previous_maintenance_epoch"]
                for record in initial_prepared["records"]
            )
        ):
            result["reasons"].append("TERMINAL_RECEIPT_SET_INVALID")
            return result
        if not (
            final_snapshot["generation"] >= initial_snapshot["generation"]
            and final_snapshot["backend_module_source_sha256"]
            == initial_snapshot["backend_module_source_sha256"]
            and final_snapshot["backend_capability_attestation_sha256"]
            == initial_snapshot["backend_capability_attestation_sha256"]
            and final_snapshot["backend_capability_probe_receipt_sha256"]
            == initial_snapshot["backend_capability_probe_receipt_sha256"]
            and final_snapshot["authenticated_authority_receipt_sha256"]
            == initial_snapshot["authenticated_authority_receipt_sha256"]
            and _completion_valid(
                completion,
                schema,
                initial_snapshot,
                initial_audit,
                initial_prepared,
                initial_resolved,
                final_snapshot,
                final_audit,
                final_prepared,
                final_resolved,
                terminal_receipts,
            )
        ):
            result["reasons"].append("SYNTHETIC_EVIDENCE_CROSS_BINDING_INVALID")
            return result
        result["cross_binding_verified"] = True
        if not (
            bundle.get("synthetic_fixture_only") is True
            and bundle.get("durable") is False
            and bundle.get("production_evidence") is False
            and bundle.get("production_authority") is False
            and bundle.get("runtime_admissible") is False
        ):
            result["reasons"].append("SYNTHETIC_FIXTURE_SAFETY_VECTOR_INVALID")
            return result
        result.update(
            ok=True,
            status="C3_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_SCHEMA_CONFORMS_SYNTHETIC_ONLY",
            safety_vector_verified=True,
            schema_conforms=True,
            write_executed=completion["write_executed"],
            registry_write=completion["registry_write"],
        )
        return result


__all__ = [
    "OFFLINE_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_CONFORMANCE_SCOPE_ATTESTATION_V1",
    "OfflineProductionStartupRecoveryEvidenceConformanceConfigV1",
    "OfflineProductionStartupRecoveryEvidenceConformanceV1",
    "SYNTHETIC_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_BUNDLE_VERSION_V1",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_CONFORMANCE_CONTRACT_V1_VERSION",
    "synthetic_completion_attestation_sha256_v1",
    "synthetic_evidence_artifact_sha256_v1",
    "synthetic_evidence_bundle_sha256_v1",
    "synthetic_terminal_receipt_sha256_v1",
    "synthetic_terminal_receipt_set_sha256_v1",
    "synthetic_transaction_log_audit_sha256_v1",
]
