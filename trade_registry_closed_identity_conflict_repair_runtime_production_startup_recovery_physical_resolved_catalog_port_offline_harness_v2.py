"""Temporary synthetic harness for the physical RESOLVED catalog port V2."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as hash_v2
import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_physical_reference_v2 as physical_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_authority_contract_v2 as durable_authority_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_authority_harness_v2 as durable_authority_harness_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_resolution_commit_harness_v2 as durable_commit_harness_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_obligation_harness_v2 as obligation_harness_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_source_ports_contract_v2 as source_ports_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_physical_resolved_catalog_port_offline_v2 as port_v2


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_PHYSICAL_RESOLVED_CATALOG_PORT_OFFLINE_HARNESS_V2_VERSION = (
    "2026-09-09-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-"
    "PRODUCTION-STARTUP-RECOVERY-PHYSICAL-RESOLVED-CATALOG-PORT-"
    "OFFLINE-HARNESS-V2"
)
SYNTHETIC_NOW_V2 = 1_788_710_000


def _sha(label: str) -> str:
    return hash_v2.stable_sha256_v2({"physical_resolved_catalog": label})


def make_physical_resolved_catalog_port_v2(
    *, backend: Any, ledger: Any
) -> port_v2.TemporaryPhysicalResolvedCatalogPortV2:
    storage = vars(ledger)["_storage"]
    return port_v2.TemporaryPhysicalResolvedCatalogPortV2(
        port_v2.TemporaryPhysicalResolvedCatalogPortConfigV2(
            enabled=True,
            scope_attestation=(
                port_v2.OFFLINE_PHYSICAL_RESOLVED_CATALOG_SCOPE_ATTESTATION_V2
            ),
            expected_backend_object_identity_sha256=(
                source_ports_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
                    backend
                )
            ),
            expected_ledger_object_identity_sha256=(
                source_ports_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
                    ledger
                )
            ),
            expected_storage_binding_sha256=(
                durable_authority_v2.durable_authority_storage_binding_sha256_v2(
                    storage
                )
            ),
        ),
        backend=backend,
        durable_authority_ledger=ledger,
    )


def run_physical_resolved_catalog_port_offline_harness_v2() -> dict[str, Any]:
    root_path: Path | None = None
    catalog: dict[str, Any] | None = None
    restarted_catalog: dict[str, Any] | None = None
    with tempfile.TemporaryDirectory(prefix="c3_durable_backend_v2_") as root:
        root_path = Path(root)
        backend = physical_v2.TemporaryPhysicalDurableRawTransactionBackendV2(
            root_path,
            enabled=True,
            scope_attestation=(
                physical_v2.TEMPORARY_PHYSICAL_REFERENCE_SCOPE_ATTESTATION_V2
            ),
            clock=lambda: SYNTHETIC_NOW_V2,
        )
        backend.initialize_synthetic_registry_offline(
            {"closed_trades": [], "fixture": "resolved-catalog", "generation": 0}
        )
        upstream = obligation_harness_v2.run_protected_reconciliation_obligation_harness_v2()
        obligation = upstream.get("terminal_ambiguity_obligation")
        if upstream.get("ok") is not True or obligation is None:
            raise RuntimeError("SYNTHETIC_RESOLUTION_OBLIGATION_UNAVAILABLE")
        ledger_root = root_path / "resolved-authority"
        scenario = durable_commit_harness_v2._scenario(
            ledger_root, obligation, "physical-resolved-catalog", None
        )
        ledger = scenario["active_ledger"]
        port = make_physical_resolved_catalog_port_v2(
            backend=backend, ledger=ledger
        )
        snapshot = backend.snapshot_offline()
        catalog = dict(
            port.read_resolved_catalog_offline(
                backend=backend, backend_snapshot=snapshot
            )
        )

        storage = vars(ledger)["_storage"]
        ledger_config = vars(ledger)["_config"]
        restarted_ledger = durable_authority_harness_v2._ledger(
            ledger_root,
            storage,
            ledger_config.expected_root_identity_sha256,
            root_attestation=vars(ledger)["_root_authority_attestation"],
        )
        recovery = restarted_ledger.recover_offline()
        restarted_port = make_physical_resolved_catalog_port_v2(
            backend=backend, ledger=restarted_ledger
        )
        restarted_catalog = dict(
            restarted_port.read_resolved_catalog_offline(
                backend=backend, backend_snapshot=snapshot
            )
        )
        expected_record = catalog["records"][0]
        ok = bool(
            scenario["first"].get("ok") is True
            and recovery.get("ok") is True
            and port_v2.physical_resolved_catalog_valid_v2(catalog, snapshot)
            and port_v2.physical_resolved_catalog_valid_v2(
                restarted_catalog, snapshot
            )
            and catalog == restarted_catalog
            and catalog["resolved_count"] == 1
            and expected_record["state"] == "RESOLVED"
            and expected_record["projection_committed"] is False
            and catalog["complete_scan_verified"] is True
            and catalog["wal_integrity_verified"] is True
            and catalog["durable"] is False
            and catalog["production_evidence"] is False
        )
    temporary_storage_removed = bool(root_path is not None and not root_path.exists())
    ok = bool(ok and temporary_storage_removed)
    return {
        "ok": ok,
        "status": (
            "PHYSICAL_RESOLVED_CATALOG_PORT_OFFLINE_V2_HARNESS_PASSED"
            if ok
            else "PHYSICAL_RESOLVED_CATALOG_PORT_OFFLINE_V2_HARNESS_FAILED"
        ),
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_PHYSICAL_RESOLVED_CATALOG_PORT_OFFLINE_HARNESS_V2_VERSION,
        "catalog_sha256": catalog["catalog_sha256"] if catalog else None,
        "resolved_count": catalog["resolved_count"] if catalog else None,
        "restart_catalog_identical": catalog == restarted_catalog,
        "temporary_storage_removed": temporary_storage_removed,
        "temporary_storage_only": True,
        "synthetic_only": True,
        "filesystem_accessed": True,
        "temporary_write_executed": True,
        "real_registry_accessed": False,
        "network_accessed": False,
        "broker_called": False,
        "no_order_sent": True,
        "production_authority": False,
        "production_ready": False,
        "runtime_integrated": False,
        "activation_allowed": False,
        "live_allowed": False,
    }


__all__ = [
    "SYNTHETIC_NOW_V2",
    "make_physical_resolved_catalog_port_v2",
    "run_physical_resolved_catalog_port_offline_harness_v2",
]
