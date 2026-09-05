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
    _controlled_activation_state.update(
        {
            field: True for field in required_true if field != "activation_requested"
        }
    )
    _controlled_activation_state["kill_switch"] = kill_switch
    status = c3_closed_repair_writer_coordination_status_v1()
    if status.get("coordination_ready") is not True:
        _coordinator = previous
        _controlled_activation_state.clear()
        _controlled_activation_state.update(previous_state)
        raise coordinator_module.WriterRuntimeCoordinationBlocked(
            "C3_CONTROLLED_ACTIVATION_POST_INSTALL_ATTESTATION_FAILED"
        )
    return status


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
        }
        ready = bool(
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
        return {
            "ok": ready,
            "status": (
                "C3_WRITER_COORDINATION_READY"
                if ready
                else "C3_WRITER_COORDINATION_BLOCKED"
            ),
            "installed": True,
            **fields,
            "coordination_ready": ready,
            "runtime_activation_allowed": ready,
            "kill_switch_engaged": not kill_switch_ready,
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
    "_c3_closed_repair_writer_mutation_v1",
    "c3_closed_repair_writer_coordination_status_v1",
    "controlled_activation_evidence_sha256_v1",
    "install_controlled_c3_closed_repair_writer_coordinator_v1",
    "install_dormant_c3_closed_repair_writer_coordinator_v1",
]
