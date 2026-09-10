"""In-memory harness for authenticated C3 provisioning receipt verification."""

from __future__ import annotations

import hashlib
import hmac
from typing import Any

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as hash_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_authority_contract_v2 as authority_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authority_provisioning_receipt_authenticated_verifier_contract_v2 as verifier_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authority_provisioning_receipt_harness_v2 as receipt_harness_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_source_ports_contract_v2 as identity_v2


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_AUTHORITY_PROVISIONING_RECEIPT_AUTHENTICATED_VERIFIER_HARNESS_V2_VERSION = (
    "2026-09-09-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-"
    "PRODUCTION-STARTUP-RECOVERY-AUTHORITY-PROVISIONING-RECEIPT-"
    "AUTHENTICATED-VERIFIER-HARNESS-V2"
)
SYNTHETIC_NOW_EPOCH_V2 = 1_788_700_000


class SyntheticInMemoryRootSignatureVerifierV2:
    def __init__(self, *, key_id_sha256: str, key: bytes) -> None:
        self._key_id_sha256 = key_id_sha256
        self._key = key

    def __repr__(self) -> str:
        return "SyntheticInMemoryRootSignatureVerifierV2(<protected>)"

    def verify_root_authority_signature_v2(
        self,
        *,
        key_id_sha256: str,
        payload_sha256: str,
        signature_sha256: str,
    ) -> bool:
        if key_id_sha256 != self._key_id_sha256:
            return False
        expected = hmac.new(
            self._key, payload_sha256.encode("ascii"), hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature_sha256)


class SyntheticInMemoryRootRevocationSourceV2:
    def __init__(self, revoked_key_ids: set[str] | None = None) -> None:
        self._revoked_key_ids = frozenset(revoked_key_ids or set())

    def __repr__(self) -> str:
        return "SyntheticInMemoryRootRevocationSourceV2(<protected>)"

    def root_authority_key_revoked_v2(
        self, *, key_id_sha256: str, key_epoch: int, now_epoch: int
    ) -> bool:
        if key_epoch < 1 or now_epoch < 0:
            raise ValueError("SYNTHETIC_REVOCATION_QUERY_INVALID")
        return key_id_sha256 in self._revoked_key_ids


def _object_identity(value: Any) -> str:
    return identity_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
        value
    )


def _build_root_attestation(
    *, key_id_sha256: str, key: bytes, storage_binding_sha256: str
) -> dict[str, Any]:
    attestation = {
        "attestation_version": authority_v2.AUTHENTICATED_ROOT_AUTHORITY_ATTESTATION_VERSION_V2,
        "root_identity_sha256": hash_v2.stable_sha256_v2(
            {"synthetic_root_identity": "provisioning-receipt-verifier-v2"}
        ),
        "storage_binding_sha256": storage_binding_sha256,
        "key_id_sha256": key_id_sha256,
        "key_epoch": 1,
        "previous_attestation_sha256": None,
        "issued_at_epoch": SYNTHETIC_NOW_EPOCH_V2 - 60,
        "expires_at_epoch": SYNTHETIC_NOW_EPOCH_V2 + 600,
        "signature_algorithm": authority_v2.ROOT_AUTHORITY_SIGNATURE_ALGORITHM_V2,
        "signature_sha256": "0" * 64,
        "attestation_sha256": "0" * 64,
    }
    payload_sha256 = authority_v2.root_authority_signature_payload_sha256_v2(
        attestation
    )
    attestation["signature_sha256"] = hmac.new(
        key, payload_sha256.encode("ascii"), hashlib.sha256
    ).hexdigest()
    attestation["attestation_sha256"] = (
        authority_v2.authenticated_root_authority_attestation_sha256_v2(
            attestation
        )
    )
    return attestation


def _build_candidate(
    *,
    protected_receipt: Any,
    root_attestation: dict[str, Any],
    key: bytes,
) -> dict[str, Any]:
    candidate = {
        "candidate_version": verifier_v2.AUTHORITY_PROVISIONING_RECEIPT_CANDIDATE_VERSION_V2,
        "scope_attestation": verifier_v2.OFFLINE_AUTHORITY_PROVISIONING_RECEIPT_AUTHENTICATED_VERIFIER_SCOPE_V2,
        "base_receipt_sha256": protected_receipt.receipt_sha256,
        "manifest_sha256": protected_receipt.receipt["manifest_sha256"],
        "root_authority_attestation_sha256": root_attestation[
            "attestation_sha256"
        ],
        "root_identity_sha256": root_attestation["root_identity_sha256"],
        "storage_binding_sha256": root_attestation["storage_binding_sha256"],
        "key_id_sha256": root_attestation["key_id_sha256"],
        "key_epoch": root_attestation["key_epoch"],
        "reference_binding_set_sha256": hash_v2.stable_sha256_v2(
            protected_receipt.receipt[
                "reference_object_identity_sha256_by_name"
            ]
        ),
        "authority_state_generation": 1,
        "revocation_state_generation": 1,
        "issued_at_epoch": SYNTHETIC_NOW_EPOCH_V2 - 30,
        "expires_at_epoch": SYNTHETIC_NOW_EPOCH_V2 + 300,
        "signature_algorithm": authority_v2.ROOT_AUTHORITY_SIGNATURE_ALGORITHM_V2,
        "signature_sha256": "0" * 64,
        "synthetic_only": True,
        "persistent_evidence_observed": False,
        "production_receipt": False,
        "candidate_sha256": "0" * 64,
    }
    payload_sha256 = (
        verifier_v2.authority_provisioning_receipt_candidate_signature_payload_sha256_v2(
            candidate
        )
    )
    candidate["signature_sha256"] = hmac.new(
        key, payload_sha256.encode("ascii"), hashlib.sha256
    ).hexdigest()
    candidate["candidate_sha256"] = (
        verifier_v2.authority_provisioning_receipt_candidate_sha256_v2(
            candidate
        )
    )
    return candidate


def build_authenticated_provisioning_receipt_verifier_context_v2(
    *, revoked: bool = False
) -> dict[str, Any]:
    receipt_context = (
        receipt_harness_v2.build_authority_provisioning_receipt_context_v2()
    )
    protected_receipt = receipt_context["result"]["protected_receipt"]
    key = b"c3-synthetic-provisioning-verifier-key-v2-0000000000000000"
    key_id_sha256 = hash_v2.stable_sha256_v2(
        {"synthetic_key_id": "provisioning-verifier-v2"}
    )
    storage_binding_sha256 = hash_v2.stable_sha256_v2(
        {
            "synthetic_storage_binding": "central-data-dir/c3/authority",
            "manifest_sha256": protected_receipt.receipt["manifest_sha256"],
        }
    )
    root_attestation = _build_root_attestation(
        key_id_sha256=key_id_sha256,
        key=key,
        storage_binding_sha256=storage_binding_sha256,
    )
    signature_verifier = SyntheticInMemoryRootSignatureVerifierV2(
        key_id_sha256=key_id_sha256, key=key
    )
    revoked_ids = {key_id_sha256} if revoked else set()
    revocation_source = SyntheticInMemoryRootRevocationSourceV2(revoked_ids)
    candidate = _build_candidate(
        protected_receipt=protected_receipt,
        root_attestation=root_attestation,
        key=key,
    )
    contract = verifier_v2.DormantAuthenticatedProvisioningReceiptVerifierV2(
        verifier_v2.DormantAuthenticatedProvisioningReceiptVerifierConfigV2(
            enabled=True,
            scope_attestation=verifier_v2.OFFLINE_AUTHORITY_PROVISIONING_RECEIPT_AUTHENTICATED_VERIFIER_SCOPE_V2,
            expected_protected_receipt_object_identity_sha256=_object_identity(
                protected_receipt
            ),
            expected_signature_verifier_object_identity_sha256=_object_identity(
                signature_verifier
            ),
            expected_revocation_source_object_identity_sha256=_object_identity(
                revocation_source
            ),
            expected_root_authority_attestation_sha256=root_attestation[
                "attestation_sha256"
            ],
            expected_storage_binding_sha256=storage_binding_sha256,
        ),
        signature_verifier=signature_verifier,
        revocation_source=revocation_source,
        clock=lambda: SYNTHETIC_NOW_EPOCH_V2,
    )
    result = contract.verify_offline(
        protected_receipt=protected_receipt,
        candidate_receipt=candidate,
        root_authority_attestation=root_attestation,
    )
    return {
        "receipt_context": receipt_context,
        "protected_receipt": protected_receipt,
        "root_attestation": root_attestation,
        "candidate": candidate,
        "signature_verifier": signature_verifier,
        "revocation_source": revocation_source,
        "contract": contract,
        "result": result,
    }


def run_authenticated_provisioning_receipt_verifier_harness_v2() -> dict[str, Any]:
    values = build_authenticated_provisioning_receipt_verifier_context_v2()
    result = values["result"]
    protected = result.get("protected_verification")
    verification = dict(protected.verification) if protected is not None else {}
    ok = bool(
        result.get("ok") is True
        and verifier_v2.protected_authenticated_provisioning_receipt_verification_valid_v2(
            protected
        )
        and verification.get("receipt_signature_verified") is True
        and verification.get("root_authority_verified") is True
        and verification.get("revocation_checked") is True
        and verification.get("root_key_revoked") is False
        and verification.get("storage_binding_verified") is True
        and verification.get("synthetic_only") is True
        and verification.get("persistent_evidence_observed") is False
        and verification.get("production_receipt") is False
        and verification.get("filesystem_accessed") is False
        and verification.get("network_accessed") is False
        and verification.get("render_accessed") is False
        and verification.get("production_ready") is False
        and verification.get("live_allowed") is False
        and repr(protected)
        == "ProtectedAuthenticatedProvisioningReceiptVerificationV2(<protected>)"
    )
    return {
        "ok": ok,
        "status": (
            "AUTHENTICATED_PROVISIONING_RECEIPT_VERIFIER_HARNESS_V2_PASSED"
            if ok
            else "AUTHENTICATED_PROVISIONING_RECEIPT_VERIFIER_HARNESS_V2_FAILED"
        ),
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_AUTHORITY_PROVISIONING_RECEIPT_AUTHENTICATED_VERIFIER_HARNESS_V2_VERSION,
        "authenticated": result.get("authenticated") is True,
        "revocation_checked": result.get("revocation_checked") is True,
        "synthetic_only": True,
        "persistent_evidence_observed": False,
        "production_receipt": False,
        "real_registry_accessed": False,
        "filesystem_accessed": False,
        "environment_read": False,
        "network_accessed": False,
        "render_accessed": False,
        "broker_called": False,
        "no_order_sent": True,
        "runtime_wiring_allowed": False,
        "startup_recovery_allowed": False,
        "production_ready": False,
        "activation_allowed": False,
        "live_allowed": False,
    }


__all__ = [
    "SYNTHETIC_NOW_EPOCH_V2",
    "SyntheticInMemoryRootRevocationSourceV2",
    "SyntheticInMemoryRootSignatureVerifierV2",
    "build_authenticated_provisioning_receipt_verifier_context_v2",
    "run_authenticated_provisioning_receipt_verifier_harness_v2",
]
