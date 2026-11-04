"""Fixed, synthetic-only child process for the C3 lock hierarchy test.

The parent test passes a temporary directory and a whitelisted role.  This
helper refuses paths outside the dedicated temporary fixture root, imports
only the local lock/coordinator modules, and never opens sockets or touches the
Central runtime or production registry.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile


def _emit(payload: dict[str, object], exit_code: int = 0) -> None:
    sys.stdout.write(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    sys.stdout.write("\n")
    sys.stdout.flush()
    if exit_code:
        os._exit(exit_code)


def main(argv: list[str]) -> int:
    if len(argv) not in (4, 5):
        _emit({"ok": False, "reason": "ARGUMENT_COUNT_INVALID"})
        return 64

    root = Path(argv[1]).resolve(strict=True)
    role = argv[2]
    namespace = argv[3]
    writer_index = int(argv[4]) if len(argv) == 5 else None
    temp_root = Path(tempfile.gettempdir()).resolve(strict=True)
    if root.parent != temp_root or not root.name.startswith("c3_durable_backend_v2_"):
        _emit({"ok": False, "reason": "SYNTHETIC_ROOT_INVALID"})
        return 65

    allowed_roles = {
        "outer-writer-locks",
        "locks",
        "resolved-authority",
        "writer-admission",
        "maintenance-crash",
        "maintenance-crash-attested",
    }
    if role not in allowed_roles or (role == "writer-admission") != (writer_index is not None):
        _emit({"ok": False, "reason": "ROLE_INVALID"})
        return 66

    # `-I` deliberately excludes the working directory; resolve imports from
    # this checked-in helper's repository, not from caller-controlled input.
    repository_root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repository_root))
    import trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1 as coordinator_v1
    import trade_registry_closed_identity_conflict_repair_writer_runtime_storage_adapters_v1 as storage_v1

    if role in {"outer-writer-locks", "locks", "resolved-authority"}:
        backend = storage_v1.CrossPlatformInterprocessFileLockBackendV1(
            root / role, enabled=True,
        )
        handle = backend.acquire(namespace, 0.05)
        acquired = handle is not None
        if handle is not None:
            handle.release()
        _emit({"synthetic_only": True, "role": role, "acquired": acquired})
        return 0

    lock_backend = storage_v1.CrossPlatformInterprocessFileLockBackendV1(
        root / "outer-writer-locks", enabled=True,
    )
    lease_store = storage_v1.DurableJsonMaintenanceLeaseStoreV1(
        lock_backend.storage_root, enabled=True,
    )
    inventory = coordinator_v1.canonical_runtime_writer_inventory_v1()
    if role == "writer-admission":
        if writer_index is None or not 0 <= writer_index < len(inventory):
            _emit({"ok": False, "reason": "WRITER_INDEX_INVALID"})
            return 67
        writer_id = inventory[writer_index]["writer_id"]
        coordinator = coordinator_v1.ClosedRepairWriterRuntimeCoordinatorV1(
            config=coordinator_v1.WriterRuntimeCoordinatorConfigV1(
                enabled=True,
                lock_timeout_seconds=0.05,
            ),
            lock_backend=lock_backend,
            lease_store=lease_store,
            clock=lambda: 50.0,
            nonce_source=lambda: f"synthetic-child-{os.getpid()}",
            lock_namespace=namespace,
        )
        coordinator.register_all_declared_writers()
        try:
            with coordinator.mutation(writer_id) as permit:
                _emit({
                    "synthetic_only": True,
                    "role": role,
                    "writer_id": writer_id,
                    "admitted": permit.admitted,
                    "reason": None,
                })
        except coordinator_v1.WriterRuntimeCoordinationBlocked as exc:
            _emit({
                "synthetic_only": True,
                "role": role,
                "writer_id": writer_id,
                "admitted": False,
                "reason": exc.reason,
            })
        return 0

    synthetic_owner = (
        f"synthetic-maintenance-child-{os.getpid()}"
        if role == "maintenance-crash-attested"
        else None
    )
    coordinator = coordinator_v1.ClosedRepairWriterRuntimeCoordinatorV1(
        config=coordinator_v1.WriterRuntimeCoordinatorConfigV1(
            enabled=True,
            lock_timeout_seconds=0.05,
            synthetic_recovery_owner_identity=synthetic_owner,
        ),
        lock_backend=lock_backend,
        lease_store=lease_store,
        # Parent recovery uses a synthetic clock of 100.0; this puts the
        # crashed lease safely in the past without consulting wall-clock time.
        clock=lambda: 50.0,
        nonce_source=lambda: f"synthetic-crash-child-{os.getpid()}",
        lock_namespace=namespace,
    )
    coordinator.register_all_declared_writers()
    with coordinator.maintenance_lease() as permit:
        _emit({
            "synthetic_only": True,
            "role": role,
            "state": permit.state,
            "process_id": os.getpid(),
        }, exit_code=75)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
