"""In-memory harness for the dormant handoff-to-raw-request adapter."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import trade_registry_closed_identity_conflict_repair_raw_transaction_store_v1 as raw_store
import trade_registry_closed_identity_conflict_repair_runtime_durable_handoff_v1 as handoff
import trade_registry_closed_identity_conflict_repair_runtime_handoff_raw_transaction_request_adapter_v1 as adapter


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_RAW_TRANSACTION_REQUEST_ADAPTER_HARNESS_V1_VERSION = (
    "2026-09-06-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-HANDOFF-RAW-TRANSACTION-REQUEST-ADAPTER-HARNESS-V1"
)

_NOW = 2_000_000_000


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _build_protected_command_v1(
    *,
    source_registry_sha256: str,
    candidate_registry_sha256: str,
    changed_paths_sha256: str,
    expires_at_epoch: int,
) -> handoff.ProtectedDurableHandoffCommandV1:
    binding = {
        "gateway_receipt_sha256": _sha256_text("synthetic-raw-adapter-gateway"),
        "authorization_receipt_sha256": _sha256_text(
            "synthetic-raw-adapter-authorization"
        ),
        "handoff_intent_sha256": _sha256_text("synthetic-raw-adapter-intent"),
        "preview_receipt_sha256": _sha256_text("synthetic-raw-adapter-preview"),
        "controller_instance_sha256": _sha256_text(
            "synthetic-raw-adapter-controller"
        ),
        "source_registry_sha256": source_registry_sha256,
        "candidate_registry_sha256": candidate_registry_sha256,
        "changed_paths_sha256": changed_paths_sha256,
        "expires_at_epoch": expires_at_epoch,
    }
    transaction_id = handoff.deterministic_handoff_transaction_id_v1(binding)
    values = {
        "command_version": handoff.HANDOFF_COMMAND_VERSION_V1,
        "transaction_id": transaction_id,
        "idempotency_key": transaction_id,
        "handoff_binding_sha256": adapter._stable_sha256(binding),
        **binding,
        "wal_prepared_record_sha256": _sha256_text(
            "synthetic-raw-adapter-handoff-wal-prepared"
        ),
    }
    unsigned = handoff.ProtectedDurableHandoffCommandV1(
        **values,
        command_sha256="0" * 64,
    )
    return handoff.ProtectedDurableHandoffCommandV1(
        **values,
        command_sha256=handoff.protected_handoff_command_sha256_v1(unsigned),
    )


def build_synthetic_handoff_raw_request_adapter_inputs_v1() -> dict[str, Any]:
    source_payload = {
        "schema_version": 3,
        "closed_trades": [
            {
                "trade_id": "synthetic-c3-trade-001",
                "close_reason": "BROKER_RECONCILED_CLOSE",
                "pnl_r": -1.26907189,
                "r_multiple": -1.08850668,
            }
        ],
        "open_trades": [],
    }
    source_raw = (
        json.dumps(source_payload, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    ).encode("utf-8")
    source_raw_sha = hashlib.sha256(source_raw).hexdigest()
    generation_token = adapter._stable_sha256(
        {
            "raw_document_sha256": source_raw_sha,
            "size_bytes": len(source_raw),
            "modified_ns": 123_456_789,
        }
    )
    source_snapshot = raw_store.ExactRawRegistrySnapshotV1(
        raw_document_sha256=source_raw_sha,
        generation_token=generation_token,
        size_bytes=len(source_raw),
        payload=json.loads(adapter._canonical_json(source_payload)),
        raw_bytes=source_raw,
    )
    candidate = json.loads(adapter._canonical_json(source_payload))
    candidate["closed_trades"][0]["close_reason"] = "STOP"
    candidate["closed_trades"][0]["gross_r_multiple"] = -1.08850668
    changed_paths = [
        "closed_trades[0].close_reason",
        "closed_trades[0].gross_r_multiple",
    ]
    source_logical_sha = adapter._stable_sha256(source_payload)
    candidate_logical_sha = adapter._stable_sha256(candidate)
    candidate_raw_sha = hashlib.sha256(
        adapter._canonical_json(candidate).encode("utf-8")
    ).hexdigest()
    changed_paths_sha = adapter._stable_sha256(changed_paths)
    command = _build_protected_command_v1(
        source_registry_sha256=source_logical_sha,
        candidate_registry_sha256=candidate_logical_sha,
        changed_paths_sha256=changed_paths_sha,
        expires_at_epoch=_NOW + 120,
    )

    maintenance_epoch = _sha256_text("synthetic-raw-adapter-maintenance-epoch")
    maintenance_attestation = {
        "attestation_version": adapter.MAINTENANCE_ATTESTATION_VERSION_V1,
        "state": "QUIESCED",
        "maintenance_epoch": maintenance_epoch,
        "lock_namespace_sha256": _sha256_text(
            "synthetic-raw-adapter-lock-namespace"
        ),
        "registered_writer_count": 19,
        "inflight_mutations": 0,
        "shared_lock_acquired": True,
        "issued_at_epoch": _NOW - 1,
        "expires_at_epoch": _NOW + 90,
        "synthetic_only": True,
        "production_evidence": False,
    }
    maintenance_attestation["attestation_sha256"] = (
        adapter.maintenance_attestation_sha256_v1(maintenance_attestation)
    )
    proof = {
        "proof_version": adapter.CANONICAL_RAW_PROOF_VERSION_V1,
        "handoff_transaction_id": command.transaction_id,
        "handoff_command_sha256": command.command_sha256,
        "source_registry_sha256": source_logical_sha,
        "source_raw_document_sha256": source_raw_sha,
        "source_generation_token": generation_token,
        "candidate_registry_sha256": candidate_logical_sha,
        "candidate_raw_document_sha256": candidate_raw_sha,
        "changed_paths_sha256": changed_paths_sha,
        "maintenance_attestation_sha256": maintenance_attestation[
            "attestation_sha256"
        ],
        "maintenance_epoch": maintenance_epoch,
        "issued_at_epoch": _NOW - 1,
        "expires_at_epoch": _NOW + 60,
        "synthetic_only": True,
        "real_registry_accessed": False,
    }
    proof["proof_sha256"] = adapter.canonical_raw_proof_sha256_v1(proof)
    return {
        "command": command,
        "source_snapshot": source_snapshot,
        "candidate_registry": candidate,
        "changed_paths": changed_paths,
        "canonical_raw_proof": proof,
        "maintenance_attestation": maintenance_attestation,
    }


def build_synthetic_handoff_raw_request_adapter_v1(
    *,
    clock=None,
) -> adapter.DormantHandoffRawTransactionRequestAdapterV1:
    return adapter.DormantHandoffRawTransactionRequestAdapterV1(
        config=adapter.DormantHandoffRawRequestAdapterConfigV1(
            enabled=True,
            scope_attestation=adapter.OFFLINE_HANDOFF_RAW_REQUEST_ADAPTER_SCOPE_ATTESTATION_V1,
        ),
        clock=clock if clock is not None else lambda: _NOW,
    )


def run_synthetic_handoff_raw_request_adapter_harness_v1() -> dict[str, Any]:
    inputs = build_synthetic_handoff_raw_request_adapter_inputs_v1()
    result = build_synthetic_handoff_raw_request_adapter_v1().project_offline(
        **inputs
    )
    protected = result.get("protected_request")
    protected_surface_safe = bool(
        type(protected) is adapter.ProtectedHandoffRawTransactionRequestV1
        and repr(protected)
        == "ProtectedHandoffRawTransactionRequestV1(<protected>)"
        and not hasattr(protected, "serialize")
        and not hasattr(protected, "apply")
        and not hasattr(protected, "invoke")
        and not hasattr(protected, "commit")
    )
    source_hash_domains_distinct = bool(
        inputs["command"].source_registry_sha256
        != inputs["source_snapshot"].raw_document_sha256
    )
    identities_distinct = bool(
        protected_surface_safe
        and protected.handoff_transaction_id
        != protected.raw_transaction_sha256
    )
    ok = bool(
        result.get("ok") is True
        and result.get("handoff_verified") is True
        and result.get("source_snapshot_verified") is True
        and result.get("canonical_raw_proof_verified") is True
        and result.get("changed_paths_verified") is True
        and result.get("maintenance_attestation_verified_synthetic") is True
        and result.get("deadline_verified") is True
        and result.get("request_projected") is True
        and result.get("raw_transaction_store_called") is False
        and result.get("transaction_persistence_allowed") is False
        and result.get("write_executed") is False
        and result.get("registry_write") is False
        and source_hash_domains_distinct
        and identities_distinct
        and protected_surface_safe
    )
    return {
        "ok": ok,
        "status": (
            "C3_HANDOFF_RAW_REQUEST_ADAPTER_HARNESS_PASSED_OFFLINE"
            if ok
            else "C3_HANDOFF_RAW_REQUEST_ADAPTER_HARNESS_FAILED_CLOSED"
        ),
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_RAW_TRANSACTION_REQUEST_ADAPTER_HARNESS_V1_VERSION,
        "protected_surface_safe": protected_surface_safe,
        "source_hash_domains_distinct": source_hash_domains_distinct,
        "handoff_and_raw_transaction_identities_distinct": identities_distinct,
        "canonical_raw_proof_verified": result.get(
            "canonical_raw_proof_verified"
        )
        is True,
        "generation_token_bound": bool(
            protected_surface_safe
            and protected.request.get("expected_generation_token")
            == inputs["source_snapshot"].generation_token
        ),
        "maintenance_epoch_bound": bool(
            protected_surface_safe
            and protected.request.get("maintenance_epoch")
            == inputs["maintenance_attestation"]["maintenance_epoch"]
        ),
        "request_projected": result.get("request_projected") is True,
        "request_material_exposed": False,
        "raw_transaction_store_called": False,
        "transaction_persistence_allowed": False,
        "runtime_integrated": False,
        "production_ready": False,
        "apply_allowed": False,
        "activation_allowed": False,
        "live_allowed": False,
        "real_registry_accessed": False,
        "network_accessed": False,
        "broker_called": False,
        "write_executed": False,
        "registry_write": False,
        "no_order_sent": True,
    }


__all__ = [
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_RAW_TRANSACTION_REQUEST_ADAPTER_HARNESS_V1_VERSION",
    "build_synthetic_handoff_raw_request_adapter_inputs_v1",
    "build_synthetic_handoff_raw_request_adapter_v1",
    "run_synthetic_handoff_raw_request_adapter_harness_v1",
]
