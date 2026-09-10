"""Dormant offline rehearsal for the CLOSED-repair pre-bootstrap bridge.

The bridge composes only injected dependencies and has no filesystem, runtime,
network or broker capability of its own.  Even a successful rehearsal remains
non-applicable to production and cannot authorize C3, Live or trading.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from typing import Any


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_PREBOOTSTRAP_MAINTENANCE_BRIDGE_V1_VERSION = (
    "2026-09-10-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-PREBOOTSTRAP-MAINTENANCE-BRIDGE-V1"
)
PREBOOTSTRAP_MAINTENANCE_REHEARSAL_ACK_V1 = (
    "C3_CLOSED_REPAIR_PREBOOTSTRAP_MAINTENANCE_REHEARSAL_V1"
)
PREBOOTSTRAP_MAINTENANCE_REHEARSAL_SCOPE_ATTESTATION_V1 = (
    "C3_CLOSED_REPAIR_EXPLICIT_OFFLINE_PREBOOTSTRAP_REHEARSAL_V1"
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_CHANGED_PATH_RE = re.compile(r"^closed_trades\[(\d+)\]\.(.+)$")
_EXPECTED_CHANGED_SUFFIXES = frozenset(
    {
        "close_reason",
        "gross_r_multiple",
        "metadata.outcome.close_reason",
        "metadata.outcome.gross_r_multiple",
        "metadata.outcome.r_multiple",
        "r_multiple",
    }
)
_EXPECTED_SELECTED_SOURCES = {
    "close_reason": "trade.metadata.exit_reason",
    "pnl_r": "trade.pnl_r",
}
_SAFE_CONTROL_VECTOR = {
    "enable_real_trading": False,
    "broker_dry_run": True,
    "falcon_mode": "VERIFY",
    "central_real_execution_enabled": False,
    "central_real_pilot_enabled": False,
    "live_trading_enabled": False,
    "order_submission_authorized": False,
}
_REQUEST_KEYS = frozenset(
    {"ack", "scope_attestation", "evidence", "request_sha256"}
)
_PRODUCTION_BLOCKERS = (
    "BRIDGE_IS_OFFLINE_REHEARSAL_ONLY",
    "PRODUCTION_RUNTIME_BINDING_ABSENT",
    "PRODUCTION_AUTHORITY_NOT_VERIFIED",
    "PRODUCTION_MAINTENANCE_ENTRYPOINT_ABSENT",
    "PRODUCTION_REPAIR_APPLY_REMAINS_DEFAULT_OFF",
    "LIVE_AUTHORIZATION_ABSENT",
)


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _stable_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _canonical_copy(value: Any) -> Any:
    return json.loads(_canonical_json(value))


def _valid_sha256(value: Any) -> str:
    normalized = str(value or "").lower().strip()
    return normalized if _SHA256_RE.fullmatch(normalized) else ""


def prebootstrap_maintenance_request_sha256_v1(
    request: Mapping[str, Any],
) -> str:
    if not isinstance(request, Mapping):
        raise TypeError("request must be a mapping")
    return _stable_sha256(
        {key: value for key, value in request.items() if key != "request_sha256"}
    )


def _safe_no_side_effect_result(value: Any) -> bool:
    return bool(
        isinstance(value, Mapping)
        and value.get("synthetic_only") is True
        and value.get("real_registry_accessed") is False
        and value.get("write_executed") is False
        and value.get("registry_write") is False
        and value.get("network_accessed") is False
        and value.get("broker_called") is False
        and value.get("no_order_sent") is True
    )


def _permit_value(permit: Any, name: str) -> Any:
    if isinstance(permit, Mapping):
        return permit.get(name)
    return getattr(permit, name, None)


def _maintenance_permit_safe(permit: Any) -> bool:
    return bool(
        _permit_value(permit, "state") == "QUIESCED"
        and _permit_value(permit, "registered_writer_count") == 19
        and _permit_value(permit, "inflight_mutations") == 0
        and _permit_value(permit, "shared_lock_acquired") is True
        and _permit_value(permit, "maintenance_only") is True
        and _permit_value(permit, "writer_mutations_allowed") is False
        and _permit_value(permit, "runtime_activation_allowed") is False
        and _valid_sha256(_permit_value(permit, "maintenance_epoch"))
        and _valid_sha256(_permit_value(permit, "lock_namespace_sha256"))
    )


def _changed_paths_valid(paths: Any) -> bool:
    if not isinstance(paths, list) or paths != sorted(set(paths)):
        return False
    indexes: set[str] = set()
    suffixes: set[str] = set()
    for path in paths:
        match = _CHANGED_PATH_RE.fullmatch(str(path or ""))
        if match is None:
            return False
        indexes.add(match.group(1))
        suffixes.add(match.group(2))
    return len(indexes) == 1 and suffixes == _EXPECTED_CHANGED_SUFFIXES


@dataclass(frozen=True)
class PrebootstrapMaintenanceBridgeConfigV1:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)


class PrebootstrapMaintenanceBridgeV1:
    """Run one fail-closed synthetic rehearsal using one maintenance permit."""

    def __init__(
        self,
        *,
        observe: Callable[[], Mapping[str, Any]],
        maintenance_lease: Callable[[], AbstractContextManager[Any]],
        repair: Callable[[Mapping[str, Any], Any], Mapping[str, Any]],
        bootstrap: Callable[[Mapping[str, Any], Any], Mapping[str, Any]],
        startup_recovery: Callable[[Mapping[str, Any], Any], Mapping[str, Any]],
        postflight: Callable[[Mapping[str, Any], Any], Mapping[str, Any]],
        rollback: Callable[[Mapping[str, Any], Any], Mapping[str, Any]],
        config: PrebootstrapMaintenanceBridgeConfigV1 | None = None,
    ) -> None:
        self._observe = observe
        self._maintenance_lease = maintenance_lease
        self._repair = repair
        self._bootstrap = bootstrap
        self._startup_recovery = startup_recovery
        self._postflight = postflight
        self._rollback = rollback
        self._config = config or PrebootstrapMaintenanceBridgeConfigV1()
        self._consumed: set[str] = set()

    @staticmethod
    def _base() -> dict[str, Any]:
        return {
            "ok": False,
            "status": "C3_PREBOOTSTRAP_MAINTENANCE_REHEARSAL_BLOCKED",
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_PREBOOTSTRAP_MAINTENANCE_BRIDGE_V1_VERSION,
            "phase": "NOT_STARTED",
            "default_off": True,
            "offline_only": True,
            "synthetic_only": True,
            "runtime_integrated": False,
            "production_ready": False,
            "apply_allowed": False,
            "activation_allowed": False,
            "live_allowed": False,
            "real_registry_accessed": False,
            "write_executed": False,
            "registry_write": False,
            "network_accessed": False,
            "broker_called": False,
            "no_order_sent": True,
            "rollback_attempted": False,
            "rollback_verified": False,
            "production_blockers": list(_PRODUCTION_BLOCKERS),
        }

    @staticmethod
    def _evidence_valid(evidence: Mapping[str, Any]) -> bool:
        controls = evidence.get("trading_controls")
        storage = evidence.get("registry_status")
        conflict = evidence.get("conflict_audit")
        coordinator = evidence.get("maintenance_coordinator")
        preview = evidence.get("preview_receipt")
        if not all(
            isinstance(value, Mapping)
            for value in (controls, storage, conflict, coordinator, preview)
        ):
            return False
        preview_payload = dict(preview)
        supplied_preview_sha = _valid_sha256(
            preview_payload.pop("preview_receipt_sha256", None)
        )
        changed_paths = preview.get("changed_paths")
        issued = preview.get("issued_at_epoch")
        expires = preview.get("expires_at_epoch")
        observed = evidence.get("observed_at_epoch")
        return bool(
            dict(controls) == _SAFE_CONTROL_VECTOR
            and storage.get("status") == "PATCH_INSTALLED_MIGRATION_PENDING"
            and storage.get("active_file_exists") is True
            and storage.get("migration_pending") is True
            and storage.get("migration_done") is False
            and storage.get("restart_readiness_attested") is False
            and storage.get("temporary_read_only") is False
            and storage.get("write_allowed") is False
            and conflict.get("ok") is True
            and conflict.get("read_only") is True
            and conflict.get("write_executed") is False
            and conflict.get("registry_write") is False
            and conflict.get("conflict_count") == 1
            and conflict.get("financial_conflict_count") == 2
            and frozenset(conflict.get("financial_conflict_fields") or ())
            == frozenset({"close_reason", "pnl_r"})
            and conflict.get("conflict_binding_sha256")
            == preview.get("conflict_binding_sha256")
            and conflict.get("safe_to_commit") is False
            and conflict.get("migration_compatible") is False
            and coordinator.get("enabled") is True
            and coordinator.get("maintenance_only") is True
            and coordinator.get("registered_writer_count") == 19
            and coordinator.get("all_writers_registered") is True
            and coordinator.get("inflight_mutations") == 0
            and coordinator.get("shared_lock_backend_ready") is True
            and coordinator.get("maintenance_lease_store_ready") is True
            and coordinator.get("writer_mutations_allowed") is False
            and coordinator.get("runtime_activation_allowed") is False
            and coordinator.get("startup_recovery_verified") is False
            and preview.get("receipt_version")
            == "C3_CLOSED_IDENTITY_REPAIR_PREVIEW_RECEIPT_V1"
            and preview.get("selected_source_paths") == _EXPECTED_SELECTED_SOURCES
            and preview.get("gross_r_source_path") == "trade.r_multiple"
            and _valid_sha256(preview.get("source_registry_sha256"))
            and _valid_sha256(preview.get("candidate_registry_sha256"))
            and preview.get("source_registry_sha256")
            != preview.get("candidate_registry_sha256")
            and _valid_sha256(preview.get("conflict_binding_sha256"))
            and _valid_sha256(preview.get("gross_r_preservation_sha256"))
            and supplied_preview_sha
            and hmac.compare_digest(
                supplied_preview_sha, _stable_sha256(preview_payload)
            )
            and preview.get("apply_allowed") is False
            and _changed_paths_valid(changed_paths)
            and type(issued) is int
            and type(expires) is int
            and type(observed) is int
            and issued <= observed < expires
            and 1 <= expires - issued <= 300
            and evidence.get("synthetic_only") is True
            and evidence.get("production_authorization_valid") is False
            and evidence.get("runtime_binding_satisfied") is False
        )

    def _validate_request(
        self, request: Any
    ) -> tuple[str, Mapping[str, Any] | None]:
        if not isinstance(request, Mapping) or set(request) != _REQUEST_KEYS:
            return "PREBOOTSTRAP_REQUEST_INVALID", None
        if request.get("ack") != PREBOOTSTRAP_MAINTENANCE_REHEARSAL_ACK_V1:
            return "PREBOOTSTRAP_ACK_REQUIRED", None
        if (
            request.get("scope_attestation")
            != PREBOOTSTRAP_MAINTENANCE_REHEARSAL_SCOPE_ATTESTATION_V1
        ):
            return "PREBOOTSTRAP_REQUEST_SCOPE_INVALID", None
        supplied = _valid_sha256(request.get("request_sha256"))
        expected = prebootstrap_maintenance_request_sha256_v1(request)
        if not supplied or not hmac.compare_digest(supplied, expected):
            return "PREBOOTSTRAP_REQUEST_HASH_MISMATCH", None
        evidence = request.get("evidence")
        if not isinstance(evidence, Mapping) or not self._evidence_valid(evidence):
            return "PREBOOTSTRAP_EVIDENCE_UNSAFE", None
        return supplied, evidence

    @staticmethod
    def _repair_valid(
        value: Any, preview: Mapping[str, Any]
    ) -> bool:
        return bool(
            _safe_no_side_effect_result(value)
            and value.get("ok") is True
            and value.get("status") == "SYNTHETIC_CLOSED_REPAIR_APPLIED"
            and value.get("simulated_registry_write") is True
            and value.get("preservation_verified") is True
            and value.get("gross_r_preservation_verified") is True
            and value.get("open_trades_preserved_exactly") is True
            and value.get("same_maintenance_permit") is True
            and value.get("conflict_count_after") == 0
            and value.get("source_registry_sha256")
            == preview.get("source_registry_sha256")
            and value.get("candidate_registry_sha256")
            == preview.get("candidate_registry_sha256")
            and value.get("changed_paths") == preview.get("changed_paths")
        )

    @staticmethod
    def _bootstrap_valid(value: Any, repair: Mapping[str, Any]) -> bool:
        return bool(
            _safe_no_side_effect_result(value)
            and value.get("ok") is True
            and value.get("status") == "SYNTHETIC_BOOTSTRAP_COMPLETED"
            and value.get("source_registry_sha256")
            == repair.get("candidate_registry_sha256")
            and value.get("conflict_count_after") == 0
            and value.get("migration_done") is True
            and value.get("restart_readiness_attested") is True
            and value.get("last_load_ok") is True
            and value.get("last_write_ok") is True
            and value.get("write_allowed") is True
            and value.get("same_maintenance_permit") is True
        )

    @staticmethod
    def _recovery_valid(value: Any, permit: Any) -> bool:
        return bool(
            _safe_no_side_effect_result(value)
            and value.get("ok") is True
            and value.get("status") == "SYNTHETIC_STARTUP_RECOVERY_COMPLETED"
            and value.get("startup_recovery_verified") is True
            and value.get("prepared_transactions_after") == 0
            and value.get("resolved_transactions_after") == 0
            and value.get("unresolved_transactions_after") == 0
            and value.get("maintenance_epoch")
            == _permit_value(permit, "maintenance_epoch")
            and value.get("lock_namespace_sha256")
            == _permit_value(permit, "lock_namespace_sha256")
        )

    @staticmethod
    def _postflight_valid(value: Any) -> bool:
        return bool(
            _safe_no_side_effect_result(value)
            and value.get("ok") is True
            and value.get("status") == "SYNTHETIC_READINESS_PROJECTED"
            and value.get("registry_storage_ready") is True
            and value.get("coordination_ready") is True
            and value.get("registered_writer_count") == 19
            and value.get("startup_recovery_verified") is True
            and value.get("runtime_integrated") is False
            and value.get("production_ready") is False
            and value.get("live_allowed") is False
            and value.get("same_maintenance_permit") is True
        )

    @staticmethod
    def _rollback_valid(value: Any) -> bool:
        return bool(
            _safe_no_side_effect_result(value)
            and value.get("ok") is True
            and value.get("status") == "SYNTHETIC_PREBOOTSTRAP_ROLLBACK_VERIFIED"
            and value.get("source_restored") is True
            and value.get("open_trades_preserved_exactly") is True
            and value.get("same_maintenance_permit") is True
        )

    def run_offline(self, request: Any) -> dict[str, Any]:
        result = self._base()
        if self._config.enabled is not True:
            result["status"] = "C3_PREBOOTSTRAP_MAINTENANCE_BRIDGE_DEFAULT_OFF"
            return result
        if (
            self._config.scope_attestation
            != PREBOOTSTRAP_MAINTENANCE_REHEARSAL_SCOPE_ATTESTATION_V1
        ):
            result["status"] = "C3_PREBOOTSTRAP_MAINTENANCE_SCOPE_REQUIRED"
            return result
        request_sha, evidence = self._validate_request(request)
        if evidence is None:
            result["status"] = request_sha
            return result
        if request_sha in self._consumed:
            result["status"] = "PREBOOTSTRAP_REQUEST_REPLAY_BLOCKED"
            return result
        try:
            observed = self._observe()
        except Exception:
            result.update(status="PREBOOTSTRAP_OBSERVATION_FAILED", phase="OBSERVE")
            return result
        try:
            observation_matches = bool(
                isinstance(observed, Mapping)
                and hmac.compare_digest(
                    _stable_sha256(observed), _stable_sha256(evidence)
                )
            )
        except (TypeError, ValueError, OverflowError):
            observation_matches = False
        if not observation_matches:
            result.update(status="PREBOOTSTRAP_OBSERVATION_DRIFT", phase="OBSERVE")
            return result

        repair_result: Mapping[str, Any] | None = None
        permit: Any = None
        workflow_complete = False
        try:
            maintenance = self._maintenance_lease()
            if maintenance is None:
                raise RuntimeError("MAINTENANCE_LEASE_UNAVAILABLE")
            with maintenance as permit:
                result["phase"] = "MAINTENANCE"
                if not _maintenance_permit_safe(permit):
                    result["status"] = "PREBOOTSTRAP_MAINTENANCE_PERMIT_INVALID"
                    return result
                preview = evidence["preview_receipt"]
                try:
                    result["phase"] = "REPAIR"
                    repair_result = self._repair(
                        _canonical_copy(preview), permit
                    )
                    if not self._repair_valid(repair_result, preview):
                        result["status"] = "PREBOOTSTRAP_REPAIR_FAILED_CLOSED"
                        if not (
                            isinstance(repair_result, Mapping)
                            and repair_result.get("simulated_registry_write") is True
                        ):
                            return result
                        raise RuntimeError("ROLLBACK_REQUIRED")
                    result["phase"] = "BOOTSTRAP"
                    bootstrap_result = self._bootstrap(repair_result, permit)
                    if not self._bootstrap_valid(bootstrap_result, repair_result):
                        result["status"] = "PREBOOTSTRAP_BOOTSTRAP_FAILED_CLOSED"
                        raise RuntimeError("ROLLBACK_REQUIRED")
                    result["phase"] = "STARTUP_RECOVERY"
                    recovery_result = self._startup_recovery(
                        bootstrap_result, permit
                    )
                    if not self._recovery_valid(recovery_result, permit):
                        result["status"] = "PREBOOTSTRAP_RECOVERY_FAILED_CLOSED"
                        raise RuntimeError("ROLLBACK_REQUIRED")
                    result["phase"] = "POSTFLIGHT"
                    postflight_result = self._postflight(
                        recovery_result, permit
                    )
                    if not self._postflight_valid(postflight_result):
                        result["status"] = "PREBOOTSTRAP_POSTFLIGHT_FAILED_CLOSED"
                        raise RuntimeError("ROLLBACK_REQUIRED")
                    workflow_complete = True
                except Exception as exc:
                    if (
                        result["status"]
                        == "C3_PREBOOTSTRAP_MAINTENANCE_REHEARSAL_BLOCKED"
                    ):
                        result["status"] = (
                            f"PREBOOTSTRAP_{result['phase']}_FAILED_CLOSED"
                        )
                    if (
                        isinstance(repair_result, Mapping)
                        and repair_result.get("simulated_registry_write") is True
                    ):
                        result["rollback_attempted"] = True
                        try:
                            rollback_result = self._rollback(
                                repair_result, permit
                            )
                            result["rollback_verified"] = (
                                self._rollback_valid(rollback_result)
                            )
                        except Exception:
                            result["rollback_verified"] = False
                        if not result["rollback_verified"]:
                            result["status"] = (
                                "PREBOOTSTRAP_ROLLBACK_FAILED_CLOSED"
                            )
                    result["reason"] = type(exc).__name__
                    return result
        except Exception as exc:
            result["status"] = "PREBOOTSTRAP_MAINTENANCE_FAILED_CLOSED"
            result["reason"] = type(exc).__name__
            return result

        if not workflow_complete:
            result["status"] = "PREBOOTSTRAP_WORKFLOW_INCOMPLETE"
            return result

        self._consumed.add(request_sha)
        receipt = {
            "request_sha256": request_sha,
            "source_registry_sha256": evidence["preview_receipt"][
                "source_registry_sha256"
            ],
            "candidate_registry_sha256": evidence["preview_receipt"][
                "candidate_registry_sha256"
            ],
            "changed_paths_sha256": _stable_sha256(
                evidence["preview_receipt"]["changed_paths"]
            ),
            "maintenance_epoch": _permit_value(permit, "maintenance_epoch"),
            "lock_namespace_sha256": _permit_value(
                permit, "lock_namespace_sha256"
            ),
            "rehearsal_completed": True,
            "production_ready": False,
            "runtime_integrated": False,
            "live_allowed": False,
            "production_blockers": list(_PRODUCTION_BLOCKERS),
        }
        receipt["receipt_sha256"] = _stable_sha256(receipt)
        result.update(
            {
                "ok": True,
                "status": "C3_PREBOOTSTRAP_MAINTENANCE_REHEARSAL_VERIFIED",
                "phase": "COMPLETE",
                "rehearsal_completed": True,
                "same_maintenance_permit_used": True,
                "open_trades_preserved_exactly": True,
                "conflict_count_after": 0,
                "rollback_attempted": False,
                "rollback_verified": False,
                "receipt": receipt,
            }
        )
        return result


__all__ = [
    "PREBOOTSTRAP_MAINTENANCE_REHEARSAL_ACK_V1",
    "PREBOOTSTRAP_MAINTENANCE_REHEARSAL_SCOPE_ATTESTATION_V1",
    "PrebootstrapMaintenanceBridgeConfigV1",
    "PrebootstrapMaintenanceBridgeV1",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_PREBOOTSTRAP_MAINTENANCE_BRIDGE_V1_VERSION",
    "prebootstrap_maintenance_request_sha256_v1",
]
