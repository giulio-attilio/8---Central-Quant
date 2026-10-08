"""Offline-only cross-binding of C3 recovery and an independent root head.

This candidate never installs a runtime component or grants startup/trading.
Process-local object pins and synthetic recovery are not workload identity,
physical restart evidence, or production authority.
"""

from __future__ import annotations

import hmac
import re
from dataclasses import dataclass, field
from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_authority_contract_v2 as authority_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_persistent_authority_boundary_v2 as boundary_v2
import trade_registry_closed_identity_conflict_repair_runtime_seam_v1 as seam_v1
from trade_registry_c3_independent_root_head_read_offline_v1 import (
    IndependentRootHeadReaderV1,
)
from trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_source_ports_contract_v2 import (
    startup_recovery_evidence_source_object_identity_sha256_v2,
)


OFFLINE_ROOT_HEAD_RECOVERY_SCOPE_V1 = "C3_ROOT_HEAD_RECOVERY_COMPOSITION_OFFLINE_V1"
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")


def _sha(value: Any) -> bool:
    return type(value) is str and _SHA_RE.fullmatch(value) is not None


@dataclass(frozen=True)
class OfflineRootHeadRecoveryConfigV1:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    expected_boundary_object_identity_sha256: str | None = field(
        default=None, repr=False
    )
    expected_head_reader_object_identity_sha256: str | None = field(
        default=None, repr=False
    )


class OfflineRootHeadRecoveryCompositionV1:
    """Evaluate synthetic recovery, then the independent head; never admit."""

    def __init__(
        self,
        config: OfflineRootHeadRecoveryConfigV1 | None = None,
        *,
        boundary: Any = None,
        head_reader: Any = None,
    ) -> None:
        self._config = config or OfflineRootHeadRecoveryConfigV1()
        self._boundary = boundary
        self._head_reader = head_reader

    def __repr__(self) -> str:
        return "OfflineRootHeadRecoveryCompositionV1(<protected>)"

    @staticmethod
    def _result(
        reason: str, *, recovery_checked: bool = False,
        head_read_attempted: bool = False, consistent: bool = False,
    ) -> dict[str, Any]:
        return {
            "reason": reason,
            "offline_evidence_consistent": consistent,
            "synthetic_recovery_checked": recovery_checked,
            "head_external_read_attempted": head_read_attempted,
            "synthetic_only": True,
            "production_authority": False,
            "production_ready": False,
            "runtime_integrated": False,
            "admission_allowed": False,
            "live_allowed": False,
            "order_submission_authorized": False,
        }

    def check(
        self, *, maintenance_permit: dict[str, Any],
        root_authority_attestation: dict[str, Any],
    ) -> dict[str, Any]:
        config = self._config
        if config.enabled is not True:
            return self._result("ROOT_HEAD_RECOVERY_DEFAULT_OFF")
        if not (
            config.scope_attestation == OFFLINE_ROOT_HEAD_RECOVERY_SCOPE_V1
            and _sha(config.expected_boundary_object_identity_sha256)
            and _sha(config.expected_head_reader_object_identity_sha256)
            and type(self._boundary) is boundary_v2.AuthenticatedPersistentAuthorityBoundaryV2
            and type(self._head_reader) is IndependentRootHeadReaderV1
            and type(maintenance_permit) is dict
            and authority_v2.authenticated_root_authority_attestation_valid_v2(
                root_authority_attestation
            )
        ):
            return self._result("ROOT_HEAD_RECOVERY_INPUT_INVALID")
        try:
            boundary_identity = startup_recovery_evidence_source_object_identity_sha256_v2(
                self._boundary
            )
            reader_identity = startup_recovery_evidence_source_object_identity_sha256_v2(
                self._head_reader
            )
            attestation = root_authority_attestation
            boundary_config = self._boundary._config
            reader_config = self._head_reader._config
            bound = (
                hmac.compare_digest(
                    boundary_identity, config.expected_boundary_object_identity_sha256
                )
                and hmac.compare_digest(
                    reader_identity, config.expected_head_reader_object_identity_sha256
                )
                and boundary_config.enabled is True
                and reader_config.enabled is True
                and boundary_config.expected_root_authority_attestation_sha256
                == attestation["attestation_sha256"]
                and boundary_config.expected_storage_binding_sha256
                == attestation["storage_binding_sha256"]
                and reader_config.root_identity_sha256
                == attestation["root_identity_sha256"]
            )
        except Exception:
            return self._result("ROOT_HEAD_RECOVERY_BINDING_INVALID")
        if not bound:
            return self._result("ROOT_HEAD_RECOVERY_BINDING_INVALID")
        try:
            recovery = self._boundary(dict(maintenance_permit))
        except Exception:
            return self._result("ROOT_HEAD_RECOVERY_FAILED")
        try:
            recovery_valid = (
                type(recovery) is dict
                and recovery.get("ok") is True
                and recovery.get("persistent_root_read") is True
                and recovery.get("root_signature_verified") is True
                and recovery.get("root_revocation_checked") is True
                and recovery.get("root_revoked") is False
                and recovery.get("multistore_recovery_verified") is True
                and recovery.get("startup_bridge_verified") is True
                and recovery.get("maintenance_epoch")
                == maintenance_permit.get("maintenance_epoch")
                and recovery.get("lock_namespace_sha256")
                == maintenance_permit.get("lock_namespace_sha256")
                and recovery.get("storage_binding_sha256")
                == attestation["storage_binding_sha256"]
                and recovery.get("root_authority_attestation_sha256")
                == attestation["attestation_sha256"]
                and recovery.get("prepared_transactions_after") == 0
                and recovery.get("resolved_transactions_after") == 0
                and recovery.get("unresolved_transactions_after") == 0
                and recovery.get("synthetic_only") is True
                and recovery.get("temporary_storage_only") is True
                and recovery.get("real_registry_accessed") is False
                and recovery.get("network_accessed") is False
                and recovery.get("broker_called") is False
                and recovery.get("no_order_sent") is True
                and recovery.get("production_authority") is False
                and recovery.get("production_ready") is False
                and recovery.get("runtime_integrated") is False
                and recovery.get("live_allowed") is False
                and _sha(recovery.get("startup_recovery_attestation_sha256"))
                and hmac.compare_digest(
                    recovery["startup_recovery_attestation_sha256"],
                    seam_v1.startup_recovery_attestation_sha256_v1(recovery),
                )
            )
        except Exception:
            recovery_valid = False
        if not recovery_valid:
            return self._result("ROOT_HEAD_RECOVERY_RECEIPT_INVALID", recovery_checked=True)
        try:
            head = self._head_reader.check_head(
                storage_binding_sha256=attestation["storage_binding_sha256"],
                key_id_sha256=attestation["key_id_sha256"],
                key_epoch=attestation["key_epoch"],
                attestation_sha256=attestation["attestation_sha256"],
            )
        except Exception:
            return self._result("ROOT_HEAD_RECOVERY_HEAD_FAILED", recovery_checked=True)
        attempted = type(head) is dict and head.get("external_read_attempted") is True
        matched = (
            type(head) is dict
            and head.get("head_matches") is True
            and attempted
            and head.get("production_ready") is False
            and head.get("runtime_integrated") is False
            and head.get("admission_allowed") is False
            and head.get("live_allowed") is False
        )
        if not matched:
            return self._result(
                "ROOT_HEAD_RECOVERY_HEAD_MISMATCH",
                recovery_checked=True, head_read_attempted=attempted,
            )
        return self._result(
            "ROOT_HEAD_RECOVERY_CONSISTENT_OFFLINE",
            recovery_checked=True, head_read_attempted=True, consistent=True,
        )


__all__ = [
    "OFFLINE_ROOT_HEAD_RECOVERY_SCOPE_V1",
    "OfflineRootHeadRecoveryConfigV1",
    "OfflineRootHeadRecoveryCompositionV1",
]
