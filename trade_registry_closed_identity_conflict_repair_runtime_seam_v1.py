"""Dormant runtime seam for C3 Trade Registry writer coordination.

This module deliberately installs only the default-off coordinator.  It does
not inspect environment variables, touch the Registry, start workers or make
network calls.  A future activation requires a separate, explicit patch.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import re
from contextlib import ContextDecorator
from collections.abc import Callable, Mapping
from typing import Any

import trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1 as coordinator_module


C3_CONTROLLED_RUNTIME_ACTIVATION_SCOPE_ATTESTATION_V1 = (
    "C3_CONTROLLED_RUNTIME_ACTIVATION_EXPLICIT_OFFLINE_REVIEW_V1"
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_CONTROLLED_ACTIVATION_SOURCE_FILES = frozenset(
    {
        "trade_registry.py",
        "main.py",
        "bots/meme.py",
        "bots/predator.py",
        "bots/turtle.py",
        "trade_registry_closed_identity_conflict_repair_raw_transaction_store_production_v1.py",
        "trade_registry_closed_identity_conflict_repair_writer_invocation_adapter_v1.py",
        "trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1.py",
        "trade_registry_closed_identity_conflict_repair_production_provider_v1.py",
    }
)


_coordinator = coordinator_module.build_closed_repair_writer_runtime_coordinator_v1()
_controlled_activation_state: dict[str, Any] = {
    "activation_receipt_verified": False,
    "source_hashes_verified": False,
    "shared_lock_backend_ready": False,
    "maintenance_lease_store_ready": False,
    "registry_interlock_ready": False,
    "rollback_ready": False,
    "kill_switch_ready": False,
    "kill_switch": None,
    "startup_recovery_verified": False,
    "startup_recovery_attestation_sha256": None,
    "startup_recovery_summary": None,
}


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def controlled_activation_evidence_sha256_v1(
    evidence: Mapping[str, Any],
) -> str:
    """Hash a sanitized activation envelope without performing any I/O."""

    if not isinstance(evidence, Mapping):
        raise TypeError("evidence must be a mapping")
    payload = {
        key: value
        for key, value in evidence.items()
        if key != "activation_evidence_sha256"
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _reset_controlled_activation_state_v1() -> None:
    _controlled_activation_state.update(
        {
            "activation_receipt_verified": False,
            "source_hashes_verified": False,
            "shared_lock_backend_ready": False,
            "maintenance_lease_store_ready": False,
            "registry_interlock_ready": False,
            "rollback_ready": False,
            "kill_switch_ready": False,
            "kill_switch": None,
            "startup_recovery_verified": False,
            "startup_recovery_attestation_sha256": None,
            "startup_recovery_summary": None,
        }
    )


def _kill_switch_clear_v1() -> bool:
    callback = _controlled_activation_state.get("kill_switch")
    if not callable(callback):
        return False
    try:
        return callback() is False
    except Exception:
        return False


def install_dormant_c3_closed_repair_writer_coordinator_v1(
    coordinator: coordinator_module.ClosedRepairWriterRuntimeCoordinatorV1,
) -> dict[str, Any]:
    """Install one disabled coordinator; enabled bindings fail closed."""

    global _coordinator
    if type(coordinator) is not coordinator_module.ClosedRepairWriterRuntimeCoordinatorV1:
        raise coordinator_module.WriterRuntimeCoordinationBlocked(
            "C3_RUNTIME_COORDINATOR_TYPE_INVALID"
        )
    if coordinator.enabled:
        raise coordinator_module.WriterRuntimeCoordinationBlocked(
            "C3_RUNTIME_ACTIVATION_FORBIDDEN_BY_DORMANT_SEAM"
        )
    _coordinator = coordinator
    _reset_controlled_activation_state_v1()
    return c3_closed_repair_writer_coordination_status_v1()


def install_controlled_c3_closed_repair_writer_coordinator_v1(
    coordinator: coordinator_module.ClosedRepairWriterRuntimeCoordinatorV1,
    *,
    enabled: bool = False,
    scope_attestation: str | None = None,
    activation_evidence: Mapping[str, Any] | None = None,
    kill_switch: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Install an enabled coordinator only from complete, hash-bound evidence.

    This callable is deliberately not wired into ``main.py``.  Its defaults
    deny activation and it consumes only caller-supplied sanitized evidence.
    """

    global _coordinator
    if enabled is not True:
        raise coordinator_module.WriterRuntimeCoordinationBlocked(
            "C3_CONTROLLED_ACTIVATION_DEFAULT_OFF"
        )
    if (
        scope_attestation
        != C3_CONTROLLED_RUNTIME_ACTIVATION_SCOPE_ATTESTATION_V1
    ):
        raise coordinator_module.WriterRuntimeCoordinationBlocked(
            "C3_CONTROLLED_ACTIVATION_SCOPE_ATTESTATION_REQUIRED"
        )
    if type(coordinator) is not coordinator_module.ClosedRepairWriterRuntimeCoordinatorV1:
        raise coordinator_module.WriterRuntimeCoordinationBlocked(
            "C3_RUNTIME_COORDINATOR_TYPE_INVALID"
        )
    if coordinator.enabled is not True:
        raise coordinator_module.WriterRuntimeCoordinationBlocked(
            "C3_CONTROLLED_ACTIVATION_ENABLED_COORDINATOR_REQUIRED"
        )
    if not isinstance(activation_evidence, Mapping):
        raise coordinator_module.WriterRuntimeCoordinationBlocked(
            "C3_CONTROLLED_ACTIVATION_EVIDENCE_REQUIRED"
        )
    try:
        supplied_sha = str(
            activation_evidence.get("activation_evidence_sha256") or ""
        ).lower().strip()
        expected_sha = controlled_activation_evidence_sha256_v1(
            activation_evidence
        )
    except (TypeError, ValueError, OverflowError):
        raise coordinator_module.WriterRuntimeCoordinationBlocked(
            "C3_CONTROLLED_ACTIVATION_EVIDENCE_INVALID"
        ) from None
    if len(supplied_sha) != 64 or not hmac.compare_digest(
        supplied_sha, expected_sha
    ):
        raise coordinator_module.WriterRuntimeCoordinationBlocked(
            "C3_CONTROLLED_ACTIVATION_EVIDENCE_HASH_MISMATCH"
        )

    required_true = (
        "activation_requested",
        "activation_receipt_verified",
        "source_hashes_verified",
        "shared_lock_backend_ready",
        "maintenance_lease_store_ready",
        "registry_interlock_ready",
        "rollback_ready",
        "kill_switch_ready",
    )
    controls = activation_evidence.get("trading_controls")
    registry_interlock = activation_evidence.get("registry_interlock")
    source_hashes = activation_evidence.get("source_hashes")
    activation_window = activation_evidence.get("activation_window")
    duration = (
        activation_window.get("max_duration_seconds")
        if isinstance(activation_window, Mapping)
        else None
    )
    rollback_deadline = (
        activation_window.get("rollback_deadline_seconds")
        if isinstance(activation_window, Mapping)
        else None
    )
    window_numeric = bool(
        not isinstance(duration, bool)
        and not isinstance(rollback_deadline, bool)
        and isinstance(duration, (int, float))
        and isinstance(rollback_deadline, (int, float))
        and math.isfinite(float(duration))
        and math.isfinite(float(rollback_deadline))
    )
    evidence_safe = bool(
        all(activation_evidence.get(field) is True for field in required_true)
        and _SHA256_RE.fullmatch(
            str(activation_evidence.get("activation_receipt_sha256") or "")
        )
        and isinstance(source_hashes, Mapping)
        and set(source_hashes) == _CONTROLLED_ACTIVATION_SOURCE_FILES
        and all(
            _SHA256_RE.fullmatch(str(value or ""))
            for value in source_hashes.values()
        )
        and isinstance(registry_interlock, Mapping)
        and registry_interlock.get("migration_done") is True
        and registry_interlock.get("restart_readiness_attested") is True
        and registry_interlock.get("last_load_ok") is True
        and registry_interlock.get("last_write_ok") is True
        and registry_interlock.get("write_allowed") is True
        and registry_interlock.get("temporary_read_only") is False
        and window_numeric
        and 1.0 <= float(duration) <= 300.0
        and 1.0 <= float(rollback_deadline) <= float(duration)
        and activation_window.get("max_inflight_mutations_before_activation")
        == 0
        and activation_window.get("fail_closed") is True
        and activation_window.get("auto_rollback_on_failure") is True
        and isinstance(controls, Mapping)
        and controls.get("enable_real_trading") is False
        and controls.get("broker_dry_run") is True
        and controls.get("falcon_mode") == "VERIFY"
        and controls.get("central_real_execution_enabled") is False
        and controls.get("central_real_pilot_enabled") is False
        and controls.get("live_trading_enabled") is False
        and controls.get("order_submission_authorized") is False
    )
    if not evidence_safe:
        raise coordinator_module.WriterRuntimeCoordinationBlocked(
            "C3_CONTROLLED_ACTIVATION_EVIDENCE_UNSAFE"
        )
    if not callable(kill_switch):
        raise coordinator_module.WriterRuntimeCoordinationBlocked(
            "C3_CONTROLLED_ACTIVATION_KILL_SWITCH_REQUIRED"
        )
    try:
        kill_switch_engaged = kill_switch() is not False
    except Exception:
        kill_switch_engaged = True
    if kill_switch_engaged:
        raise coordinator_module.WriterRuntimeCoordinationBlocked(
            "C3_CONTROLLED_ACTIVATION_KILL_SWITCH_ENGAGED"
        )

    snapshot = coordinator.snapshot()
    if not (
        snapshot.get("enabled") is True
        and snapshot.get("registered_writer_count") == 19
        and snapshot.get("all_writers_registered") is True
        and snapshot.get("inflight_mutations") == 0
        and snapshot.get("maintenance_lease_state") in (None, "RELEASED")
    ):
        raise coordinator_module.WriterRuntimeCoordinationBlocked(
            "C3_CONTROLLED_ACTIVATION_COORDINATOR_NOT_QUIESCENT"
        )

    previous = _coordinator
    previous_state = dict(_controlled_activation_state)
    _coordinator = coordinator
    _reset_controlled_activation_state_v1()
    _controlled_activation_state.update(
        {
            field: True for field in required_true if field != "activation_requested"
        }
    )
    _controlled_activation_state["kill_switch"] = kill_switch
    status = c3_closed_repair_writer_coordination_status_v1()
    if not _c3_closed_repair_base_coordination_safe_v1(status):
        _coordinator = previous
        _controlled_activation_state.clear()
        _controlled_activation_state.update(previous_state)
        raise coordinator_module.WriterRuntimeCoordinationBlocked(
            "C3_CONTROLLED_ACTIVATION_POST_INSTALL_ATTESTATION_FAILED"
        )
    return status


def startup_recovery_attestation_sha256_v1(
    attestation: Mapping[str, Any],
) -> str:
    """Hash a sanitized recovery result without trusting its supplied digest."""

    if not isinstance(attestation, Mapping):
        raise TypeError("attestation must be a mapping")
    payload = {
        key: value
        for key, value in attestation.items()
        if key != "startup_recovery_attestation_sha256"
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _c3_closed_repair_base_coordination_safe_v1(
    status: Mapping[str, Any],
) -> bool:
    return bool(
        isinstance(status, Mapping)
        and status.get("enabled") is True
        and status.get("registered_writer_count") == 19
        and status.get("all_writers_registered") is True
        and status.get("inflight_mutations") == 0
        and status.get("shared_lock_backend_ready") is True
        and status.get("maintenance_lease_store_ready") is True
        and status.get("registry_interlock_ready") is True
        and status.get("activation_receipt_verified") is True
        and status.get("source_hashes_verified") is True
        and status.get("rollback_ready") is True
        and status.get("kill_switch_ready") is True
        and status.get("kill_switch_engaged") is False
    )


class C3ClosedRepairRuntimeInterlockBindingV1:
    """Bind status, maintenance and recovery to one exact coordinator object."""

    __slots__ = ("_bound_coordinator", "_bound_startup_recovery")

    def __init__(
        self,
        coordinator: coordinator_module.ClosedRepairWriterRuntimeCoordinatorV1,
        *,
        startup_recovery: Callable[[Mapping[str, Any]], Mapping[str, Any]],
    ) -> None:
        if not callable(startup_recovery):
            raise coordinator_module.WriterRuntimeCoordinationBlocked(
                "C3_STARTUP_RECOVERY_DEPENDENCY_REQUIRED"
            )
        self._bound_coordinator = coordinator
        self._bound_startup_recovery = startup_recovery

    def __repr__(self) -> str:
        return "<C3ClosedRepairRuntimeInterlockBindingV1 protected>"

    def _require_current_coordinator(self) -> None:
        if self._bound_coordinator is not _coordinator:
            raise coordinator_module.WriterRuntimeCoordinationBlocked(
                "C3_RUNTIME_INTERLOCK_BINDING_STALE"
            )

    def coordination_status(self) -> dict[str, Any]:
        self._require_current_coordinator()
        return c3_closed_repair_writer_coordination_status_v1()

    def maintenance_lease(self):
        self._require_current_coordinator()
        status = self.coordination_status()
        if not _c3_closed_repair_base_coordination_safe_v1(status):
            raise coordinator_module.WriterRuntimeCoordinationBlocked(
                "C3_RUNTIME_INTERLOCKS_NOT_READY"
            )
        return self._bound_coordinator.maintenance_lease()

    def run_startup_recovery_v1(self) -> dict[str, Any]:
        """Recover under the same maintenance lease, then unlock readiness."""

        self._require_current_coordinator()
        with self.maintenance_lease() as permit:
            permit_evidence = {
                "maintenance_epoch": permit.maintenance_epoch,
                "state": permit.state,
                "lock_namespace_sha256": permit.lock_namespace_sha256,
                "registered_writer_count": permit.registered_writer_count,
                "inflight_mutations": permit.inflight_mutations,
                "shared_lock_acquired": permit.shared_lock_acquired,
            }
            try:
                recovered = self._bound_startup_recovery(dict(permit_evidence))
                if not isinstance(recovered, Mapping):
                    raise TypeError("recovery result must be a mapping")
                attestation = json.loads(_canonical_json(dict(recovered)))
                supplied_sha = str(
                    attestation.get("startup_recovery_attestation_sha256")
                    or ""
                ).lower().strip()
                expected_sha = startup_recovery_attestation_sha256_v1(
                    attestation
                )
            except Exception as exc:
                raise coordinator_module.WriterRuntimeCoordinationBlocked(
                    "C3_STARTUP_RECOVERY_FAILED_CLOSED"
                ) from exc
            counts = (
                attestation.get("prepared_transactions_before"),
                attestation.get("resolved_transactions_before"),
                attestation.get("prepared_transactions_after"),
                attestation.get("resolved_transactions_after"),
                attestation.get("unresolved_transactions_after"),
            )
            valid = bool(
                all(type(value) is int and value >= 0 for value in counts)
                and counts[2:] == (0, 0, 0)
                and attestation.get("ok") is True
                and attestation.get("wal_inspected") is True
                and attestation.get("transaction_log_inspected") is True
                and attestation.get("prepared_transactions_inspected") is True
                and attestation.get("resolved_transactions_inspected") is True
                and attestation.get("recovery_completed") is True
                and attestation.get("reconciliation_completed") is True
                and attestation.get("maintenance_epoch")
                == permit.maintenance_epoch
                and attestation.get("lock_namespace_sha256")
                == permit.lock_namespace_sha256
                and type(attestation.get("real_registry_accessed")) is bool
                and attestation.get("filesystem_accessed") is True
                and type(attestation.get("write_executed")) is bool
                and type(attestation.get("registry_write")) is bool
                and (
                    attestation.get("registry_write") is False
                    or attestation.get("write_executed") is True
                )
                and attestation.get("network_accessed") is False
                and attestation.get("broker_called") is False
                and attestation.get("no_order_sent") is True
                and attestation.get("synthetic_only") is False
                and attestation.get("temporary_storage_only") is False
                and attestation.get("production_authority") is True
                and attestation.get("production_ready") is True
                and attestation.get("runtime_integrated") is True
                and _SHA256_RE.fullmatch(supplied_sha)
                and hmac.compare_digest(supplied_sha, expected_sha)
            )
            if not valid:
                raise coordinator_module.WriterRuntimeCoordinationBlocked(
                    "C3_STARTUP_RECOVERY_ATTESTATION_INVALID"
                )

        self._require_current_coordinator()
        _controlled_activation_state["startup_recovery_verified"] = True
        _controlled_activation_state[
            "startup_recovery_attestation_sha256"
        ] = supplied_sha
        _controlled_activation_state["startup_recovery_summary"] = {
            "prepared_transactions_before": counts[0],
            "resolved_transactions_before": counts[1],
            "prepared_transactions_after": counts[2],
            "resolved_transactions_after": counts[3],
            "unresolved_transactions_after": counts[4],
            "real_registry_accessed": attestation[
                "real_registry_accessed"
            ],
            "write_executed": attestation["write_executed"],
            "registry_write": attestation["registry_write"],
            "network_accessed": False,
            "broker_called": False,
            "no_order_sent": True,
        }
        status = self.coordination_status()
        if status.get("coordination_ready") is not True:
            _controlled_activation_state["startup_recovery_verified"] = False
            _controlled_activation_state[
                "startup_recovery_attestation_sha256"
            ] = None
            _controlled_activation_state["startup_recovery_summary"] = None
            raise coordinator_module.WriterRuntimeCoordinationBlocked(
                "C3_STARTUP_RECOVERY_POSTCONDITION_FAILED"
            )
        return status


def bind_c3_closed_repair_runtime_interlocks_v1(
    coordinator: coordinator_module.ClosedRepairWriterRuntimeCoordinatorV1,
    *,
    startup_recovery: Callable[[Mapping[str, Any]], Mapping[str, Any]],
) -> C3ClosedRepairRuntimeInterlockBindingV1:
    """Capture the exact installed coordinator for all runtime interlocks."""

    if (
        type(coordinator)
        is not coordinator_module.ClosedRepairWriterRuntimeCoordinatorV1
        or coordinator is not _coordinator
    ):
        raise coordinator_module.WriterRuntimeCoordinationBlocked(
            "C3_RUNTIME_INTERLOCK_COORDINATOR_IDENTITY_MISMATCH"
        )
    return C3ClosedRepairRuntimeInterlockBindingV1(
        coordinator,
        startup_recovery=startup_recovery,
    )


class _DormantWriterMutationContextV1(ContextDecorator):
    def __init__(self, writer_id: str) -> None:
        self._writer_id = str(writer_id)
        self._context = None

    def _recreate_cm(self):
        return type(self)(self._writer_id)

    def __enter__(self):
        if _coordinator.enabled and not _kill_switch_clear_v1():
            raise coordinator_module.WriterRuntimeCoordinationBlocked(
                "C3_RUNTIME_KILL_SWITCH_ENGAGED"
            )
        if _coordinator.enabled and _controlled_activation_state.get(
            "startup_recovery_verified"
        ) is not True:
            raise coordinator_module.WriterRuntimeCoordinationBlocked(
                "C3_RUNTIME_STARTUP_RECOVERY_REQUIRED"
            )
        self._context = _coordinator.mutation(self._writer_id)
        return self._context.__enter__()

    def __exit__(self, exc_type, exc, traceback):
        if self._context is None:
            raise coordinator_module.WriterRuntimeCoordinationBlocked(
                "C3_RUNTIME_MUTATION_CONTEXT_NOT_ENTERED"
            )
        try:
            return self._context.__exit__(exc_type, exc, traceback)
        finally:
            self._context = None


def _c3_closed_repair_writer_mutation_v1(writer_id: str):
    """Return a reusable dynamic context/decorator for one writer."""

    return _DormantWriterMutationContextV1(writer_id)


def c3_closed_repair_writer_coordination_status_v1() -> dict[str, Any]:
    snapshot = _coordinator.snapshot()
    if snapshot.get("enabled") is True:
        kill_switch_ready = bool(
            _controlled_activation_state.get("kill_switch_ready")
            and _kill_switch_clear_v1()
        )
        fields = {
            "enabled": True,
            "registered_writer_count": snapshot.get(
                "registered_writer_count", 0
            ),
            "all_writers_registered": snapshot.get(
                "all_writers_registered", False
            ),
            "inflight_mutations": snapshot.get("inflight_mutations", 0),
            "shared_lock_backend_ready": bool(
                _controlled_activation_state.get("shared_lock_backend_ready")
            ),
            "maintenance_lease_store_ready": bool(
                _controlled_activation_state.get(
                    "maintenance_lease_store_ready"
                )
            ),
            "registry_interlock_ready": bool(
                _controlled_activation_state.get("registry_interlock_ready")
            ),
            "activation_receipt_verified": bool(
                _controlled_activation_state.get(
                    "activation_receipt_verified"
                )
            ),
            "source_hashes_verified": bool(
                _controlled_activation_state.get("source_hashes_verified")
            ),
            "rollback_ready": bool(
                _controlled_activation_state.get("rollback_ready")
            ),
            "kill_switch_ready": kill_switch_ready,
            "startup_recovery_verified": bool(
                _controlled_activation_state.get(
                    "startup_recovery_verified"
                )
            ),
        }
        base_ready = bool(
            fields["registered_writer_count"] == 19
            and fields["all_writers_registered"] is True
            and fields["inflight_mutations"] == 0
            and all(
                fields[key] is True
                for key in (
                    "shared_lock_backend_ready",
                    "maintenance_lease_store_ready",
                    "registry_interlock_ready",
                    "activation_receipt_verified",
                    "source_hashes_verified",
                    "rollback_ready",
                    "kill_switch_ready",
                )
            )
        )
        ready = bool(
            base_ready and fields["startup_recovery_verified"] is True
        )
        return {
            "ok": ready,
            "status": (
                "C3_WRITER_COORDINATION_READY"
                if ready
                else (
                    "C3_WRITER_COORDINATION_STARTUP_RECOVERY_REQUIRED"
                    if base_ready
                    else "C3_WRITER_COORDINATION_BLOCKED"
                )
            ),
            "installed": True,
            **fields,
            "coordination_ready": ready,
            "runtime_activation_allowed": ready,
            "kill_switch_engaged": not kill_switch_ready,
            "startup_recovery_attestation_sha256": (
                _controlled_activation_state.get(
                    "startup_recovery_attestation_sha256"
                )
            ),
            "startup_recovery_summary": _controlled_activation_state.get(
                "startup_recovery_summary"
            ),
            "real_registry_accessed": False,
            "network_accessed": False,
            "broker_called": False,
            "no_order_sent": True,
        }
    return {
        "ok": True,
        "status": "C3_WRITER_COORDINATION_DORMANT_DEFAULT_OFF",
        "installed": True,
        "enabled": False,
        "coordination_ready": False,
        "runtime_activation_allowed": False,
        "registered_writer_count": snapshot.get("registered_writer_count", 0),
        "real_registry_accessed": False,
        "network_accessed": False,
        "broker_called": False,
        "no_order_sent": True,
    }


__all__ = [
    "C3_CONTROLLED_RUNTIME_ACTIVATION_SCOPE_ATTESTATION_V1",
    "C3ClosedRepairRuntimeInterlockBindingV1",
    "_c3_closed_repair_writer_mutation_v1",
    "bind_c3_closed_repair_runtime_interlocks_v1",
    "c3_closed_repair_writer_coordination_status_v1",
    "controlled_activation_evidence_sha256_v1",
    "install_controlled_c3_closed_repair_writer_coordinator_v1",
    "install_dormant_c3_closed_repair_writer_coordinator_v1",
    "startup_recovery_attestation_sha256_v1",
]
