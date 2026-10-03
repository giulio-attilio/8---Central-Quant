"""Explicit, default-off production activation for C3 writer coordination.

The module discovers no environment variables, secrets or runtime paths.  Its
caller must inject every capability and nothing is activated at import time.
"""

from __future__ import annotations

import copy
import hmac
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_seam_v1 as runtime_seam
import trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1 as coordinator_module
import trade_registry_closed_identity_conflict_repair_writer_runtime_storage_adapters_v1 as storage_module


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_WRITER_COORDINATION_ACTIVATION_V1_VERSION = (
    "2026-10-01-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-"
    "RUNTIME-PRODUCTION-WRITER-COORDINATION-ACTIVATION-V1"
)
PRODUCTION_WRITER_COORDINATION_ACTIVATION_SCOPE_ATTESTATION_V1 = (
    "C3_PRODUCTION_WRITER_COORDINATION_EXPLICIT_PRE_RUNTIME_ACTIVATION_V1"
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_RUNTIME_STATE_KEYS = frozenset(
    {"runtime_started", "workers_started", "server_accepting_requests"}
)


class ProductionWriterCoordinationActivationBlocked(RuntimeError):
    def __init__(self, reason: str) -> None:
        self.reason = str(reason or "C3_PRODUCTION_WRITER_COORDINATION_BLOCKED")
        super().__init__(self.reason)


@dataclass(frozen=True)
class ProductionWriterCoordinationActivationConfigV1:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    expected_storage_root_binding_sha256: str | None = field(
        default=None, repr=False
    )


@dataclass(frozen=True)
class ProductionWriterCoordinationActivationResultV1:
    interlocks: runtime_seam.C3ClosedRepairRuntimeInterlockBindingV1 = field(
        repr=False
    )
    runtime_operation: Any = field(repr=False)
    receipt: Mapping[str, Any] = field(repr=False)

    def __repr__(self) -> str:
        return "<ProductionWriterCoordinationActivationResultV1 protected>"

    def snapshot(self) -> dict[str, Any]:
        return copy.deepcopy(dict(self.receipt))


def _require_pre_runtime_state(
    runtime_state: Callable[[], Mapping[str, Any]],
) -> None:
    if not callable(runtime_state):
        raise ProductionWriterCoordinationActivationBlocked(
            "C3_PRODUCTION_WRITER_COORDINATION_RUNTIME_STATE_REQUIRED"
        )
    try:
        state = runtime_state()
    except Exception as exc:
        raise ProductionWriterCoordinationActivationBlocked(
            "C3_PRODUCTION_WRITER_COORDINATION_RUNTIME_STATE_FAILED"
        ) from exc
    if not (
        isinstance(state, Mapping)
        and set(state) == _RUNTIME_STATE_KEYS
        and all(state[key] is False for key in _RUNTIME_STATE_KEYS)
    ):
        raise ProductionWriterCoordinationActivationBlocked(
            "C3_PRODUCTION_WRITER_COORDINATION_PRE_RUNTIME_REQUIRED"
        )


def _require_config(
    config: ProductionWriterCoordinationActivationConfigV1,
    storage_root: str | Path,
) -> str:
    if config.enabled is not True:
        raise ProductionWriterCoordinationActivationBlocked(
            "C3_PRODUCTION_WRITER_COORDINATION_DEFAULT_OFF"
        )
    if (
        config.scope_attestation
        != PRODUCTION_WRITER_COORDINATION_ACTIVATION_SCOPE_ATTESTATION_V1
    ):
        raise ProductionWriterCoordinationActivationBlocked(
            "C3_PRODUCTION_WRITER_COORDINATION_SCOPE_REQUIRED"
        )
    supplied = str(config.expected_storage_root_binding_sha256 or "").lower().strip()
    if not _SHA256_RE.fullmatch(supplied):
        raise ProductionWriterCoordinationActivationBlocked(
            "C3_PRODUCTION_WRITER_COORDINATION_STORAGE_BINDING_REQUIRED"
        )
    expected = (
        coordinator_module.production_coordinator_storage_root_binding_sha256_v1(
            storage_root
        )
    )
    if not hmac.compare_digest(supplied, expected):
        raise ProductionWriterCoordinationActivationBlocked(
            "C3_PRODUCTION_WRITER_COORDINATION_STORAGE_BINDING_MISMATCH"
        )
    return supplied


def activate_production_writer_coordination_v1(
    *,
    storage_root: str | Path,
    activation_evidence: Mapping[str, Any],
    kill_switch: Callable[[], bool],
    activation_authority: Any,
    activation_interlock: Any,
    startup_recovery: Callable[[Mapping[str, Any]], Mapping[str, Any]],
    runtime_operation_factory: Callable[..., Any],
    runtime_state: Callable[[], Mapping[str, Any]],
    clock: Callable[[], float],
    nonce_source: Callable[[], str],
    config: ProductionWriterCoordinationActivationConfigV1 | None = None,
) -> ProductionWriterCoordinationActivationResultV1:
    """Activate before runtime, or restore a dormant coordinator on failure."""

    selected = config or ProductionWriterCoordinationActivationConfigV1()
    storage_binding = _require_config(selected, storage_root)
    _require_pre_runtime_state(runtime_state)
    if not isinstance(activation_evidence, Mapping):
        raise ProductionWriterCoordinationActivationBlocked(
            "C3_PRODUCTION_WRITER_COORDINATION_EVIDENCE_REQUIRED"
        )
    if activation_evidence.get("storage_root_binding_sha256") != storage_binding:
        raise ProductionWriterCoordinationActivationBlocked(
            "C3_PRODUCTION_WRITER_COORDINATION_EVIDENCE_STORAGE_MISMATCH"
        )
    if not all(
        callable(value)
        for value in (
            kill_switch,
            startup_recovery,
            runtime_operation_factory,
            clock,
            nonce_source,
        )
    ):
        raise ProductionWriterCoordinationActivationBlocked(
            "C3_PRODUCTION_WRITER_COORDINATION_DEPENDENCY_REQUIRED"
        )

    runtime_seam.bind_controlled_c3_runtime_activation_capabilities_v1(
        enabled=True,
        scope_attestation=(
            runtime_seam.C3_CONTROLLED_RUNTIME_CAPABILITY_BINDING_SCOPE_ATTESTATION_V1
        ),
        activation_authority=activation_authority,
        activation_interlock=activation_interlock,
    )

    try:
        lock_backend = storage_module.CrossPlatformInterprocessFileLockBackendV1(
            storage_root,
            enabled=True,
        )
        lease_store = storage_module.DurableJsonMaintenanceLeaseStoreV1(
            storage_root,
            enabled=True,
        )
        coordinator = (
            coordinator_module.build_production_closed_repair_writer_runtime_coordinator_v1(
                config=coordinator_module.ProductionWriterRuntimeCoordinatorBindingConfigV1(
                    enabled=True,
                    scope_attestation=(
                        coordinator_module.PRODUCTION_COORDINATOR_EXPLICIT_DEPENDENCY_BINDING_ATTESTATION_V1
                    ),
                    storage_root_binding_sha256=storage_binding,
                ),
                lock_backend=lock_backend,
                lease_store=lease_store,
                clock=clock,
                nonce_source=nonce_source,
            )
        )
        runtime_seam.install_controlled_c3_closed_repair_writer_coordinator_v1(
            coordinator,
            enabled=True,
            scope_attestation=(
                runtime_seam.C3_CONTROLLED_RUNTIME_ACTIVATION_SCOPE_ATTESTATION_V1
            ),
            activation_evidence=activation_evidence,
            kill_switch=kill_switch,
            activation_authority=activation_authority,
            activation_interlock=activation_interlock,
        )
        interlocks = runtime_seam.bind_c3_closed_repair_runtime_interlocks_v1(
            coordinator,
            startup_recovery=startup_recovery,
        )
        ready = interlocks.run_startup_recovery_v1()
        if not (
            ready.get("ok") is True
            and ready.get("coordination_ready") is True
            and ready.get("runtime_activation_allowed") is True
            and ready.get("registered_writer_count") == 19
            and ready.get("all_writers_registered") is True
            and ready.get("inflight_mutations") == 0
        ):
            raise ProductionWriterCoordinationActivationBlocked(
                "C3_PRODUCTION_WRITER_COORDINATION_POSTCONDITION_FAILED"
            )
        runtime_operation = runtime_operation_factory(interlocks=interlocks)
        if runtime_operation is None:
            raise ProductionWriterCoordinationActivationBlocked(
                "C3_PRODUCTION_WRITER_COORDINATION_RUNTIME_BINDING_REQUIRED"
            )
    except Exception as exc:
        try:
            dormant = (
                coordinator_module.build_production_closed_repair_writer_runtime_coordinator_v1()
            )
            runtime_seam.install_dormant_c3_closed_repair_writer_coordinator_v1(
                dormant
            )
            runtime_seam.bind_c3_closed_repair_runtime_interlocks_v1(
                dormant,
                startup_recovery=startup_recovery,
            )
        except Exception as rollback_exc:
            raise ProductionWriterCoordinationActivationBlocked(
                "C3_PRODUCTION_WRITER_COORDINATION_ROLLBACK_FAILED"
            ) from rollback_exc
        raise ProductionWriterCoordinationActivationBlocked(
            getattr(
                exc,
                "reason",
                "C3_PRODUCTION_WRITER_COORDINATION_ACTIVATION_FAILED",
            )
        ) from exc

    summary = ready.get("startup_recovery_summary") or {}
    receipt = {
        "ok": True,
        "status": "C3_PRODUCTION_WRITER_COORDINATION_READY",
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_WRITER_COORDINATION_ACTIVATION_V1_VERSION,
        "enabled": True,
        "coordination_ready": True,
        "runtime_activation_allowed": True,
        "registered_writer_count": 19,
        "all_writers_registered": True,
        "inflight_mutations": 0,
        "shared_lock_backend_ready": True,
        "maintenance_lease_store_ready": True,
        "registry_interlock_ready": True,
        "startup_recovery_verified": True,
        "storage_root_binding_sha256": storage_binding,
        "startup_recovery_attestation_sha256": ready.get(
            "startup_recovery_attestation_sha256"
        ),
        "real_registry_accessed": bool(summary.get("real_registry_accessed")),
        "write_executed": bool(summary.get("write_executed")),
        "registry_write": bool(summary.get("registry_write")),
        "network_accessed": False,
        "broker_called": False,
        "no_order_sent": True,
        "live_allowed": False,
        "order_submission_authorized": False,
    }
    return ProductionWriterCoordinationActivationResultV1(
        interlocks=interlocks,
        runtime_operation=runtime_operation,
        receipt=receipt,
    )


__all__ = [
    "PRODUCTION_WRITER_COORDINATION_ACTIVATION_SCOPE_ATTESTATION_V1",
    "ProductionWriterCoordinationActivationBlocked",
    "ProductionWriterCoordinationActivationConfigV1",
    "ProductionWriterCoordinationActivationResultV1",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_WRITER_COORDINATION_ACTIVATION_V1_VERSION",
    "activate_production_writer_coordination_v1",
]
