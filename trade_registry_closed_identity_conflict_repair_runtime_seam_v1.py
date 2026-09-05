"""Dormant runtime seam for C3 Trade Registry writer coordination.

This module deliberately installs only the default-off coordinator.  It does
not inspect environment variables, touch the Registry, start workers or make
network calls.  A future activation requires a separate, explicit patch.
"""

from __future__ import annotations

from contextlib import ContextDecorator
from typing import Any

import trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1 as coordinator_module


_coordinator = coordinator_module.build_closed_repair_writer_runtime_coordinator_v1()


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
    return c3_closed_repair_writer_coordination_status_v1()


class _DormantWriterMutationContextV1(ContextDecorator):
    def __init__(self, writer_id: str) -> None:
        self._writer_id = str(writer_id)
        self._context = None

    def _recreate_cm(self):
        return type(self)(self._writer_id)

    def __enter__(self):
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
    "_c3_closed_repair_writer_mutation_v1",
    "c3_closed_repair_writer_coordination_status_v1",
    "install_dormant_c3_closed_repair_writer_coordinator_v1",
]
