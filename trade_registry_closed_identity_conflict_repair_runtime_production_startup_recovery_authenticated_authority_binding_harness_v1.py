"""In-memory harness for the dormant authenticated-authority binding."""

from __future__ import annotations

import hashlib
import hmac
from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_authority_contract_v2 as authority_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_authority_binding_contract_v1 as contract
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_schema_harness_v1 as schema_harness_v1


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_AUTHENTICATED_AUTHORITY_BINDING_HARNESS_V1_VERSION = (
    "2026-09-09-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-"
    "PRODUCTION-STARTUP-RECOVERY-AUTHENTICATED-AUTHORITY-BINDING-HARNESS-V1"
)

_SYNTHETIC_KEY = b"synthetic-c3-startup-recovery-authority-key-v1"
_SYNTHETIC_KEY_ID_SHA256 = hashlib.sha256(
    b"synthetic-c3-startup-recovery-authority-key-id-v1"
).hexdigest()


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class SyntheticOfflineRootAuthorityVerifierV1:
    offline_only = True
    filesystem_access_allowed = False
    network_access_allowed = False

    def __init__(self) -> None:
        self.call_count = 0

    def verify_root_authority_signature_v2(
        self,
        *,
        key_id_sha256: str,
        payload_sha256: str,
        signature_sha256: str,
    ) -> bool:
        self.call_count += 1
        if key_id_sha256 != _SYNTHETIC_KEY_ID_SHA256:
            return False
        expected = hmac.new(
            _SYNTHETIC_KEY,
            payload_sha256.encode("ascii"),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature_sha256)

    def __repr__(self) -> str:
        return "SyntheticOfflineRootAuthorityVerifierV1(<protected>)"


def _root_authority_attestation(
    *,
    root_identity_sha256: str,
    storage_binding_sha256: str,
) -> dict[str, Any]:
    value = {
        "attestation_version": authority_v2.AUTHENTICATED_ROOT_AUTHORITY_ATTESTATION_VERSION_V2,
        "root_identity_sha256": root_identity_sha256,
        "storage_binding_sha256": storage_binding_sha256,
        "key_id_sha256": _SYNTHETIC_KEY_ID_SHA256,
        "key_epoch": 2,
        "previous_attestation_sha256": _sha("synthetic-previous-root-v1"),
        "issued_at_epoch": 1_000,
        "expires_at_epoch": 2_000,
        "signature_algorithm": authority_v2.ROOT_AUTHORITY_SIGNATURE_ALGORITHM_V2,
        "signature_sha256": "",
    }
    payload_sha256 = authority_v2.root_authority_signature_payload_sha256_v2(
        value
    )
    value["signature_sha256"] = hmac.new(
        _SYNTHETIC_KEY,
        payload_sha256.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()
    value["attestation_sha256"] = (
        authority_v2.authenticated_root_authority_attestation_sha256_v2(value)
    )
    return value


def _durable_authority_receipt(
    *,
    root_identity_sha256: str,
    storage_binding_sha256: str,
    root_authority_attestation_sha256: str,
) -> authority_v2.ProtectedDurableReconciliationAuthorityReceiptV2:
    record = {
        "record_version": authority_v2.DURABLE_AUTHORITY_RECORD_VERSION_V2,
        "root_identity_sha256": root_identity_sha256,
        "obligation_sha256": _sha("synthetic-startup-obligation-v1"),
        "obligation_id_sha256": _sha("synthetic-startup-obligation-id-v1"),
        "transaction_sha256": _sha("synthetic-startup-transaction-v1"),
        "subject_binding_sha256": _sha("synthetic-startup-subject-v1"),
        "grant_sha256": _sha("synthetic-startup-grant-v1"),
        "issued_at_epoch": 1_100,
        "expires_at_epoch": 1_900,
        "state": "ISSUED",
        "issuance_count": 1,
        "consumption_count": 0,
        "consumed_at_epoch": None,
        "terminal_evidence_sha256": None,
        "synthetic_only": True,
        "production_authority": False,
        "pre_resolution_record_sha256": None,
        "admission_sha256": None,
        "preparation_sha256": None,
        "terminal_state": None,
        "resolved_at_epoch": None,
        "resolution_source_evidence_sha256": None,
        "resolution_adapter_plan_sha256": None,
        "resolution_request_binding_sha256": None,
        "resolution_request_sha256": None,
        "resolution_binding_sha256": None,
    }
    record["record_sha256"] = authority_v2.durable_authority_record_sha256_v2(
        record
    )
    receipt = {
        "receipt_version": authority_v2.DURABLE_AUTHORITY_RECEIPT_VERSION_V2,
        "root_identity_sha256": root_identity_sha256,
        "storage_binding_sha256": storage_binding_sha256,
        "root_authority_attestation_sha256": root_authority_attestation_sha256,
        "record_sha256": record["record_sha256"],
        "obligation_sha256": record["obligation_sha256"],
        "transaction_sha256": record["transaction_sha256"],
        "grant_sha256": record["grant_sha256"],
        "state": record["state"],
        "issuance_count": record["issuance_count"],
        "consumption_count": record["consumption_count"],
        "generation": 1,
        "restart_persistent_reference": True,
        "synthetic_only": True,
        "production_authority": False,
        "production_durable": False,
    }
    receipt["receipt_sha256"] = authority_v2.durable_authority_receipt_sha256_v2(
        receipt
    )
    return authority_v2.ProtectedDurableReconciliationAuthorityReceiptV2(
        record=record,
        receipt=receipt,
        receipt_sha256=receipt["receipt_sha256"],
    )


def make_synthetic_startup_recovery_authority_identity_v1(
    *,
    backend_instance_sha256: str,
    registry_path_binding_sha256: str,
    lock_namespace_sha256: str,
    authority_storage_binding_sha256: str,
) -> dict[str, Any]:
    identity = {
        "identity_version": contract.SYNTHETIC_STARTUP_RECOVERY_AUTHORITY_IDENTITY_VERSION_V1,
        "authority_storage_binding_sha256": authority_storage_binding_sha256,
        "backend_instance_sha256": backend_instance_sha256,
        "registry_path_binding_sha256": registry_path_binding_sha256,
        "wal_storage_binding_sha256": _sha("synthetic-production-wal-v1"),
        "resolved_ledger_storage_binding_sha256": _sha(
            "synthetic-production-resolved-ledger-v1"
        ),
        "lock_namespace_sha256": lock_namespace_sha256,
        "maintenance_epoch": _sha("synthetic-maintenance-epoch-v1"),
        "maintenance_lease_receipt_sha256": _sha(
            "synthetic-maintenance-lease-receipt-v1"
        ),
        "synthetic_only": True,
        "production_evidence": False,
    }
    identity["identity_sha256"] = (
        contract.startup_recovery_authority_identity_sha256_v1(identity)
    )
    return identity


def make_synthetic_authenticated_authority_binding_contract_v1(
    *,
    schema_sha256: str,
    root_authority_attestation_sha256: str,
    durable_authority_receipt_sha256: str,
    recovery_identity_sha256: str,
) -> contract.DormantStartupRecoveryAuthenticatedAuthorityBindingContractV1:
    return contract.DormantStartupRecoveryAuthenticatedAuthorityBindingContractV1(
        config=contract.DormantStartupRecoveryAuthenticatedAuthorityBindingConfigV1(
            enabled=True,
            scope_attestation=(
                contract.OFFLINE_PRODUCTION_STARTUP_RECOVERY_AUTHENTICATED_AUTHORITY_BINDING_SCOPE_ATTESTATION_V1
            ),
            expected_schema_sha256=schema_sha256,
            expected_root_authority_attestation_sha256=(
                root_authority_attestation_sha256
            ),
            expected_durable_authority_receipt_sha256=(
                durable_authority_receipt_sha256
            ),
            expected_recovery_identity_sha256=recovery_identity_sha256,
        )
    )


def build_synthetic_startup_recovery_authenticated_authority_binding_context_v1() -> dict[
    str, Any
]:
    schema_values = (
        schema_harness_v1.build_synthetic_production_startup_recovery_evidence_schema_context_v1()
    )
    schema_result = schema_values["schema_contract"].define_offline(
        protected_provider_binding=schema_values["protected_identity_binding"]
    )
    protected_schema = schema_result.get("protected_schema")
    schema = protected_schema.schema if protected_schema is not None else {}
    authority_storage_binding_sha256 = _sha(
        "synthetic-authority-storage-binding-v1"
    )
    root_identity_sha256 = _sha("synthetic-root-identity-v1")
    root_attestation = _root_authority_attestation(
        root_identity_sha256=root_identity_sha256,
        storage_binding_sha256=authority_storage_binding_sha256,
    )
    durable_receipt = _durable_authority_receipt(
        root_identity_sha256=root_identity_sha256,
        storage_binding_sha256=authority_storage_binding_sha256,
        root_authority_attestation_sha256=root_attestation[
            "attestation_sha256"
        ],
    )
    recovery_identity = make_synthetic_startup_recovery_authority_identity_v1(
        backend_instance_sha256=schema.get("source_backend_instance_sha256", ""),
        registry_path_binding_sha256=schema.get(
            "source_registry_path_binding_sha256", ""
        ),
        lock_namespace_sha256=schema.get("source_lock_namespace_sha256", ""),
        authority_storage_binding_sha256=authority_storage_binding_sha256,
    )
    verifier = SyntheticOfflineRootAuthorityVerifierV1()
    binding_contract = make_synthetic_authenticated_authority_binding_contract_v1(
        schema_sha256=(protected_schema.schema_sha256 if protected_schema else ""),
        root_authority_attestation_sha256=root_attestation[
            "attestation_sha256"
        ],
        durable_authority_receipt_sha256=durable_receipt.receipt_sha256,
        recovery_identity_sha256=recovery_identity["identity_sha256"],
    )
    return {
        **schema_values,
        "schema_result": schema_result,
        "protected_schema": protected_schema,
        "root_authority_attestation": root_attestation,
        "durable_authority_receipt": durable_receipt,
        "recovery_identity": recovery_identity,
        "root_authority_verifier": verifier,
        "binding_contract": binding_contract,
        "now_epoch": 1_500,
    }


def run_synthetic_startup_recovery_authenticated_authority_binding_harness_v1() -> dict[
    str, Any
]:
    values = (
        build_synthetic_startup_recovery_authenticated_authority_binding_context_v1()
    )
    result = values["binding_contract"].bind_offline(
        protected_evidence_schema=values["protected_schema"],
        recovery_identity=values["recovery_identity"],
        root_authority_attestation=values["root_authority_attestation"],
        root_authority_verifier=values["root_authority_verifier"],
        durable_authority_receipt=values["durable_authority_receipt"],
        now_epoch=values["now_epoch"],
    )
    protected = result.get("protected_binding")
    binding = protected.binding if protected is not None else {}
    counters = values["store_double"].counters()
    safe = bool(
        values["schema_result"].get("ok") is True
        and result.get("ok") is True
        and result.get("schema_verified") is True
        and result.get("identity_vector_verified") is True
        and result.get("root_signature_verifier_reused") is True
        and result.get("root_signature_verified") is True
        and result.get("durable_authority_receipt_verified") is True
        and result.get("binding_created") is True
        and contract.protected_startup_recovery_authenticated_authority_binding_valid_v1(
            protected
        )
        and binding.get("cryptographic_contract_compatible") is True
        and binding.get("startup_session_authority_scope_verified") is False
        and binding.get("evidence_population_allowed") is False
        and binding.get("production_authority") is False
        and binding.get("production_ready") is False
        and binding.get("runtime_integrated") is False
        and binding.get("live_allowed") is False
        and values["root_authority_verifier"].call_count == 1
        and counters == {"apply_call_count": 0, "recovery_call_count": 0}
        and result.get("evidence_created") is False
        and result.get("filesystem_accessed") is False
        and result.get("real_registry_accessed") is False
        and result.get("network_accessed") is False
        and result.get("broker_called") is False
        and result.get("write_executed") is False
        and result.get("registry_write") is False
        and result.get("no_order_sent") is True
    )
    return {
        "ok": safe,
        "status": (
            "C3_STARTUP_RECOVERY_AUTHENTICATED_AUTHORITY_BINDING_HARNESS_PASSED_OFFLINE"
            if safe
            else "C3_STARTUP_RECOVERY_AUTHENTICATED_AUTHORITY_BINDING_HARNESS_FAILED_CLOSED"
        ),
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_AUTHENTICATED_AUTHORITY_BINDING_HARNESS_V1_VERSION,
        "root_signature_verifier_reused": result.get(
            "root_signature_verifier_reused"
        )
        is True,
        "root_signature_verified": result.get("root_signature_verified") is True,
        "identity_vector_verified": result.get("identity_vector_verified") is True,
        "cryptographic_contract_compatible": binding.get(
            "cryptographic_contract_compatible"
        )
        is True,
        "startup_session_authority_scope_verified": False,
        "evidence_created": False,
        "production_authority": False,
        "production_ready": False,
        "runtime_integrated": False,
        "recovery_execution_allowed": False,
        "activation_allowed": False,
        "live_allowed": False,
        "filesystem_accessed": False,
        "real_registry_accessed": False,
        "network_accessed": False,
        "broker_called": False,
        "write_executed": False,
        "registry_write": False,
        "no_order_sent": True,
    }


__all__ = [
    "SyntheticOfflineRootAuthorityVerifierV1",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_AUTHENTICATED_AUTHORITY_BINDING_HARNESS_V1_VERSION",
    "build_synthetic_startup_recovery_authenticated_authority_binding_context_v1",
    "make_synthetic_authenticated_authority_binding_contract_v1",
    "make_synthetic_startup_recovery_authority_identity_v1",
    "run_synthetic_startup_recovery_authenticated_authority_binding_harness_v1",
]
