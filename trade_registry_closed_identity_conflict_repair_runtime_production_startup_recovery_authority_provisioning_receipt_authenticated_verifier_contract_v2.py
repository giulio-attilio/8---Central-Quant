"""Dormant authenticated verifier for a C3 provisioning receipt candidate.

All dependencies and evidence are caller-injected.  The offline contract binds
an exact synthetic provisioning receipt to an authenticated root, checks the
same verifier and revocation-source instances, and fails closed without I/O.
"""

from __future__ import annotations

import copy
import hmac
import re
from dataclasses import dataclass, field
from typing import Any, Mapping

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as hash_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_authority_contract_v2 as authority_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authority_provisioning_receipt_contract_v2 as receipt_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_source_ports_contract_v2 as identity_v2


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_AUTHORITY_PROVISIONING_RECEIPT_AUTHENTICATED_VERIFIER_CONTRACT_V2_VERSION = (
    "2026-09-09-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-"
    "PRODUCTION-STARTUP-RECOVERY-AUTHORITY-PROVISIONING-RECEIPT-"
    "AUTHENTICATED-VERIFIER-CONTRACT-V2"
)
OFFLINE_AUTHORITY_PROVISIONING_RECEIPT_AUTHENTICATED_VERIFIER_SCOPE_V2 = (
    "C3_AUTHORITY_PROVISIONING_RECEIPT_AUTHENTICATED_VERIFIER_OFFLINE_ONLY_V2"
)
AUTHORITY_PROVISIONING_RECEIPT_CANDIDATE_VERSION_V2 = (
    "C3_AUTHORITY_PROVISIONING_RECEIPT_AUTHENTICATED_CANDIDATE_V2"
)
AUTHORITY_PROVISIONING_RECEIPT_VERIFICATION_VERSION_V2 = (
    "C3_AUTHORITY_PROVISIONING_RECEIPT_AUTHENTICATED_VERIFICATION_V2"
)

_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_CANDIDATE_KEYS = {
    "candidate_version",
    "scope_attestation",
    "base_receipt_sha256",
    "manifest_sha256",
    "root_authority_attestation_sha256",
    "root_identity_sha256",
    "storage_binding_sha256",
    "key_id_sha256",
    "key_epoch",
    "reference_binding_set_sha256",
    "authority_state_generation",
    "revocation_state_generation",
    "issued_at_epoch",
    "expires_at_epoch",
    "signature_algorithm",
    "signature_sha256",
    "synthetic_only",
    "persistent_evidence_observed",
    "production_receipt",
    "candidate_sha256",
}
_PRODUCTION_BLOCKERS = (
    "AUTHENTICATED_VERIFICATION_USED_SYNTHETIC_EVIDENCE_ONLY",
    "ROOT_VERIFIER_IS_NOT_A_PROVISIONED_PRODUCTION_KEY_PROVIDER",
    "REVOCATION_SOURCE_IS_NOT_PERSISTENT_PRODUCTION_STATE",
    "PERSISTENT_DURABILITY_EVIDENCE_WAS_NOT_OBSERVED",
    "PRODUCTION_PROVISIONING_RECEIPT_WAS_NOT_SUPPLIED",
    "PRODUCTION_REFERENCE_BINDINGS_WERE_NOT_RESOLVED",
    "RUNTIME_CONFIGURATION_NOT_APPLIED",
    "STARTUP_RECOVERY_NOT_EXECUTED",
    "SEPARATE_PRODUCTION_ATTESTATION_REQUIRED",
    "LIVE_REMAINS_FORBIDDEN",
)


def _valid_sha(value: Any) -> bool:
    return bool(_SHA_RE.fullmatch(str(value or "").lower().strip()))


def authority_provisioning_receipt_candidate_signature_payload_sha256_v2(
    value: Mapping[str, Any],
) -> str:
    return hash_v2.stable_sha256_v2(
        {
            key: item
            for key, item in value.items()
            if key not in {"signature_sha256", "candidate_sha256"}
        }
    )


def authority_provisioning_receipt_candidate_sha256_v2(
    value: Mapping[str, Any],
) -> str:
    return hash_v2.stable_sha256_v2(
        {key: item for key, item in value.items() if key != "candidate_sha256"}
    )


def authority_provisioning_receipt_verification_sha256_v2(
    value: Mapping[str, Any],
) -> str:
    return hash_v2.stable_sha256_v2(
        {key: item for key, item in value.items() if key != "verification_sha256"}
    )


@dataclass(frozen=True)
class DormantAuthenticatedProvisioningReceiptVerifierConfigV2:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    expected_protected_receipt_object_identity_sha256: str | None = field(
        default=None, repr=False
    )
    expected_signature_verifier_object_identity_sha256: str | None = field(
        default=None, repr=False
    )
    expected_revocation_source_object_identity_sha256: str | None = field(
        default=None, repr=False
    )
    expected_root_authority_attestation_sha256: str | None = field(
        default=None, repr=False
    )
    expected_storage_binding_sha256: str | None = field(
        default=None, repr=False
    )


@dataclass(frozen=True, repr=False)
class ProtectedAuthenticatedProvisioningReceiptVerificationV2:
    protected_receipt_object_identity_sha256: str = field(repr=False)
    root_authority_attestation_sha256: str = field(repr=False)
    candidate_sha256: str = field(repr=False)
    verification: Mapping[str, Any] = field(repr=False)
    verification_sha256: str = field(repr=False)

    def __repr__(self) -> str:
        return "ProtectedAuthenticatedProvisioningReceiptVerificationV2(<protected>)"


def protected_authenticated_provisioning_receipt_verification_valid_v2(
    value: Any,
) -> bool:
    if not isinstance(
        value, ProtectedAuthenticatedProvisioningReceiptVerificationV2
    ):
        return False
    verification = value.verification
    if not isinstance(verification, Mapping):
        return False
    try:
        return bool(
            set(verification)
            == {
                "verification_version",
                "scope_attestation",
                "protected_receipt_object_identity_sha256",
                "base_receipt_sha256",
                "manifest_sha256",
                "candidate_sha256",
                "root_authority_attestation_sha256",
                "root_identity_sha256",
                "storage_binding_sha256",
                "key_id_sha256",
                "key_epoch",
                "authority_state_generation",
                "revocation_state_generation",
                "receipt_signature_verified",
                "root_authority_verified",
                "revocation_checked",
                "root_key_revoked",
                "storage_binding_verified",
                "rotation_chain_shape_verified",
                "same_verifier_instance_required",
                "same_revocation_source_instance_required",
                "synthetic_only",
                "persistent_evidence_observed",
                "production_receipt",
                "real_registry_accessed",
                "filesystem_accessed",
                "environment_read",
                "network_accessed",
                "render_accessed",
                "broker_called",
                "no_order_sent",
                "runtime_wiring_allowed",
                "startup_recovery_allowed",
                "production_ready",
                "activation_allowed",
                "live_allowed",
                "production_blockers",
                "verification_sha256",
            }
            and verification["verification_version"]
            == AUTHORITY_PROVISIONING_RECEIPT_VERIFICATION_VERSION_V2
            and verification["scope_attestation"]
            == OFFLINE_AUTHORITY_PROVISIONING_RECEIPT_AUTHENTICATED_VERIFIER_SCOPE_V2
            and all(
                _valid_sha(verification[field_name])
                for field_name in (
                    "protected_receipt_object_identity_sha256",
                    "base_receipt_sha256",
                    "manifest_sha256",
                    "candidate_sha256",
                    "root_authority_attestation_sha256",
                    "root_identity_sha256",
                    "storage_binding_sha256",
                    "key_id_sha256",
                )
            )
            and verification["protected_receipt_object_identity_sha256"]
            == value.protected_receipt_object_identity_sha256
            and verification["root_authority_attestation_sha256"]
            == value.root_authority_attestation_sha256
            and verification["candidate_sha256"] == value.candidate_sha256
            and type(verification["key_epoch"]) is int
            and verification["key_epoch"] >= 1
            and type(verification["authority_state_generation"]) is int
            and verification["authority_state_generation"] >= 1
            and type(verification["revocation_state_generation"]) is int
            and verification["revocation_state_generation"] >= 1
            and all(
                verification[field_name] is True
                for field_name in (
                    "receipt_signature_verified",
                    "root_authority_verified",
                    "revocation_checked",
                    "storage_binding_verified",
                    "rotation_chain_shape_verified",
                    "same_verifier_instance_required",
                    "same_revocation_source_instance_required",
                    "synthetic_only",
                    "no_order_sent",
                )
            )
            and all(
                verification[field_name] is False
                for field_name in (
                    "root_key_revoked",
                    "persistent_evidence_observed",
                    "production_receipt",
                    "real_registry_accessed",
                    "filesystem_accessed",
                    "environment_read",
                    "network_accessed",
                    "render_accessed",
                    "broker_called",
                    "runtime_wiring_allowed",
                    "startup_recovery_allowed",
                    "production_ready",
                    "activation_allowed",
                    "live_allowed",
                )
            )
            and verification["production_blockers"] == list(_PRODUCTION_BLOCKERS)
            and _valid_sha(verification["verification_sha256"])
            and verification["verification_sha256"]
            == value.verification_sha256
            and hmac.compare_digest(
                value.verification_sha256,
                authority_provisioning_receipt_verification_sha256_v2(
                    verification
                ),
            )
        )
    except Exception:
        return False


class DormantAuthenticatedProvisioningReceiptVerifierV2:
    def __init__(
        self,
        config: DormantAuthenticatedProvisioningReceiptVerifierConfigV2 | None = None,
        *,
        signature_verifier: Any = None,
        revocation_source: Any = None,
        clock: Any = None,
    ) -> None:
        self._config = config or DormantAuthenticatedProvisioningReceiptVerifierConfigV2()
        self._signature_verifier = signature_verifier
        self._revocation_source = revocation_source
        self._clock = clock

    def __repr__(self) -> str:
        return "DormantAuthenticatedProvisioningReceiptVerifierV2(<protected>)"

    @staticmethod
    def _base(reason: str) -> dict[str, Any]:
        return {
            "ok": False,
            "status": "C3_AUTHORITY_PROVISIONING_RECEIPT_AUTHENTICATED_VERIFICATION_BLOCKED",
            "reason": reason,
            "verification_created": False,
            "protected_verification": None,
            "authenticated": False,
            "revocation_checked": False,
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
            "production_blockers": list(_PRODUCTION_BLOCKERS),
        }

    def verify_offline(
        self,
        *,
        protected_receipt: Any,
        candidate_receipt: Mapping[str, Any],
        root_authority_attestation: Mapping[str, Any],
    ) -> dict[str, Any]:
        config = self._config
        if config.enabled is not True:
            return self._base("AUTHENTICATED_PROVISIONING_RECEIPT_VERIFIER_DEFAULT_OFF")
        if (
            config.scope_attestation
            != OFFLINE_AUTHORITY_PROVISIONING_RECEIPT_AUTHENTICATED_VERIFIER_SCOPE_V2
        ):
            return self._base("AUTHENTICATED_PROVISIONING_RECEIPT_SCOPE_INVALID")
        if not receipt_v2.protected_authority_provisioning_receipt_valid_v2(
            protected_receipt
        ):
            return self._base("PROTECTED_PROVISIONING_RECEIPT_INVALID")

        receipt_identity = (
            identity_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
                protected_receipt
            )
        )
        verifier_identity = (
            identity_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
                self._signature_verifier
            )
        )
        revocation_identity = (
            identity_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
                self._revocation_source
            )
        )
        expected_identities = (
            config.expected_protected_receipt_object_identity_sha256,
            config.expected_signature_verifier_object_identity_sha256,
            config.expected_revocation_source_object_identity_sha256,
        )
        actual_identities = (receipt_identity, verifier_identity, revocation_identity)
        if not all(_valid_sha(item) for item in expected_identities) or any(
            not hmac.compare_digest(str(expected), actual)
            for expected, actual in zip(expected_identities, actual_identities)
        ):
            return self._base("AUTHENTICATED_PROVISIONING_DEPENDENCY_INSTANCE_INVALID")
        if not callable(self._clock):
            return self._base("AUTHENTICATED_PROVISIONING_CLOCK_REQUIRED")
        try:
            now_epoch = self._clock()
        except Exception:
            return self._base("AUTHENTICATED_PROVISIONING_CLOCK_FAILED")
        if type(now_epoch) is not int:
            return self._base("AUTHENTICATED_PROVISIONING_CLOCK_INVALID")

        if not authority_v2.authenticated_root_authority_attestation_verified_v2(
            root_authority_attestation, self._signature_verifier
        ):
            return self._base("ROOT_AUTHORITY_ATTESTATION_INVALID")
        root_attestation_sha = root_authority_attestation["attestation_sha256"]
        if not (
            _valid_sha(config.expected_root_authority_attestation_sha256)
            and hmac.compare_digest(
                root_attestation_sha,
                str(config.expected_root_authority_attestation_sha256),
            )
            and _valid_sha(config.expected_storage_binding_sha256)
            and hmac.compare_digest(
                root_authority_attestation["storage_binding_sha256"],
                str(config.expected_storage_binding_sha256),
            )
            and root_authority_attestation["issued_at_epoch"]
            <= now_epoch
            < root_authority_attestation["expires_at_epoch"]
        ):
            return self._base("ROOT_AUTHORITY_BINDING_OR_TIME_INVALID")
        revoke = getattr(
            self._revocation_source, "root_authority_key_revoked_v2", None
        )
        if not callable(revoke):
            return self._base("ROOT_REVOCATION_SOURCE_INVALID")
        try:
            revoked = revoke(
                key_id_sha256=root_authority_attestation["key_id_sha256"],
                key_epoch=root_authority_attestation["key_epoch"],
                now_epoch=now_epoch,
            )
        except Exception:
            return self._base("ROOT_REVOCATION_CHECK_FAILED")
        if type(revoked) is not bool:
            return self._base("ROOT_REVOCATION_RESULT_INVALID")
        if revoked:
            return self._base("ROOT_AUTHORITY_KEY_REVOKED")

        if type(candidate_receipt) is not dict or set(candidate_receipt) != _CANDIDATE_KEYS:
            return self._base("PROVISIONING_RECEIPT_CANDIDATE_SHAPE_INVALID")
        try:
            candidate_valid = bool(
                candidate_receipt["candidate_version"]
                == AUTHORITY_PROVISIONING_RECEIPT_CANDIDATE_VERSION_V2
                and candidate_receipt["scope_attestation"]
                == OFFLINE_AUTHORITY_PROVISIONING_RECEIPT_AUTHENTICATED_VERIFIER_SCOPE_V2
                and candidate_receipt["base_receipt_sha256"]
                == protected_receipt.receipt_sha256
                and candidate_receipt["manifest_sha256"]
                == protected_receipt.receipt["manifest_sha256"]
                and candidate_receipt["root_authority_attestation_sha256"]
                == root_attestation_sha
                and candidate_receipt["root_identity_sha256"]
                == root_authority_attestation["root_identity_sha256"]
                and candidate_receipt["storage_binding_sha256"]
                == root_authority_attestation["storage_binding_sha256"]
                and candidate_receipt["key_id_sha256"]
                == root_authority_attestation["key_id_sha256"]
                and candidate_receipt["key_epoch"]
                == root_authority_attestation["key_epoch"]
                and candidate_receipt["reference_binding_set_sha256"]
                == hash_v2.stable_sha256_v2(
                    protected_receipt.receipt[
                        "reference_object_identity_sha256_by_name"
                    ]
                )
                and type(candidate_receipt["authority_state_generation"]) is int
                and candidate_receipt["authority_state_generation"] >= 1
                and type(candidate_receipt["revocation_state_generation"]) is int
                and candidate_receipt["revocation_state_generation"] >= 1
                and type(candidate_receipt["issued_at_epoch"]) is int
                and type(candidate_receipt["expires_at_epoch"]) is int
                and candidate_receipt["issued_at_epoch"]
                <= now_epoch
                < candidate_receipt["expires_at_epoch"]
                and candidate_receipt["signature_algorithm"]
                == authority_v2.ROOT_AUTHORITY_SIGNATURE_ALGORITHM_V2
                and candidate_receipt["synthetic_only"] is True
                and candidate_receipt["persistent_evidence_observed"] is False
                and candidate_receipt["production_receipt"] is False
                and _valid_sha(candidate_receipt["signature_sha256"])
                and _valid_sha(candidate_receipt["candidate_sha256"])
                and hmac.compare_digest(
                    candidate_receipt["candidate_sha256"],
                    authority_provisioning_receipt_candidate_sha256_v2(
                        candidate_receipt
                    ),
                )
            )
        except Exception:
            candidate_valid = False
        if not candidate_valid:
            return self._base("PROVISIONING_RECEIPT_CANDIDATE_INVALID")

        verify = getattr(
            self._signature_verifier, "verify_root_authority_signature_v2", None
        )
        try:
            signature_verified = bool(
                callable(verify)
                and verify(
                    key_id_sha256=candidate_receipt["key_id_sha256"],
                    payload_sha256=authority_provisioning_receipt_candidate_signature_payload_sha256_v2(
                        candidate_receipt
                    ),
                    signature_sha256=candidate_receipt["signature_sha256"],
                )
                is True
            )
        except Exception:
            signature_verified = False
        if not signature_verified:
            return self._base("PROVISIONING_RECEIPT_SIGNATURE_INVALID")

        verification = {
            "verification_version": AUTHORITY_PROVISIONING_RECEIPT_VERIFICATION_VERSION_V2,
            "scope_attestation": OFFLINE_AUTHORITY_PROVISIONING_RECEIPT_AUTHENTICATED_VERIFIER_SCOPE_V2,
            "protected_receipt_object_identity_sha256": receipt_identity,
            "base_receipt_sha256": protected_receipt.receipt_sha256,
            "manifest_sha256": protected_receipt.receipt["manifest_sha256"],
            "candidate_sha256": candidate_receipt["candidate_sha256"],
            "root_authority_attestation_sha256": root_attestation_sha,
            "root_identity_sha256": root_authority_attestation["root_identity_sha256"],
            "storage_binding_sha256": root_authority_attestation["storage_binding_sha256"],
            "key_id_sha256": root_authority_attestation["key_id_sha256"],
            "key_epoch": root_authority_attestation["key_epoch"],
            "authority_state_generation": candidate_receipt["authority_state_generation"],
            "revocation_state_generation": candidate_receipt["revocation_state_generation"],
            "receipt_signature_verified": True,
            "root_authority_verified": True,
            "revocation_checked": True,
            "root_key_revoked": False,
            "storage_binding_verified": True,
            "rotation_chain_shape_verified": True,
            "same_verifier_instance_required": True,
            "same_revocation_source_instance_required": True,
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
            "production_blockers": list(_PRODUCTION_BLOCKERS),
        }
        verification["verification_sha256"] = (
            authority_provisioning_receipt_verification_sha256_v2(verification)
        )
        protected_verification = (
            ProtectedAuthenticatedProvisioningReceiptVerificationV2(
                protected_receipt_object_identity_sha256=receipt_identity,
                root_authority_attestation_sha256=root_attestation_sha,
                candidate_sha256=candidate_receipt["candidate_sha256"],
                verification=copy.deepcopy(verification),
                verification_sha256=verification["verification_sha256"],
            )
        )
        if not protected_authenticated_provisioning_receipt_verification_valid_v2(
            protected_verification
        ):
            return self._base("AUTHENTICATED_PROVISIONING_SELF_VALIDATION_FAILED")
        result = self._base("")
        result.update(
            {
                "ok": True,
                "status": "C3_AUTHORITY_PROVISIONING_RECEIPT_AUTHENTICATED_OFFLINE",
                "reason": None,
                "verification_created": True,
                "protected_verification": protected_verification,
                "authenticated": True,
                "revocation_checked": True,
            }
        )
        return result


def build_dormant_authenticated_provisioning_receipt_verifier_v2(
) -> DormantAuthenticatedProvisioningReceiptVerifierV2:
    return DormantAuthenticatedProvisioningReceiptVerifierV2()


__all__ = [
    "AUTHORITY_PROVISIONING_RECEIPT_CANDIDATE_VERSION_V2",
    "AUTHORITY_PROVISIONING_RECEIPT_VERIFICATION_VERSION_V2",
    "DormantAuthenticatedProvisioningReceiptVerifierConfigV2",
    "DormantAuthenticatedProvisioningReceiptVerifierV2",
    "OFFLINE_AUTHORITY_PROVISIONING_RECEIPT_AUTHENTICATED_VERIFIER_SCOPE_V2",
    "ProtectedAuthenticatedProvisioningReceiptVerificationV2",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_AUTHORITY_PROVISIONING_RECEIPT_AUTHENTICATED_VERIFIER_CONTRACT_V2_VERSION",
    "authority_provisioning_receipt_candidate_sha256_v2",
    "authority_provisioning_receipt_candidate_signature_payload_sha256_v2",
    "authority_provisioning_receipt_verification_sha256_v2",
    "build_dormant_authenticated_provisioning_receipt_verifier_v2",
    "protected_authenticated_provisioning_receipt_verification_valid_v2",
]
