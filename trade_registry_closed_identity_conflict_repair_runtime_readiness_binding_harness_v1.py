"""Read-only source harness for the dormant C3 readiness-binding policy."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_controlled_activation_contract_v1 as activation_contract
import trade_registry_closed_identity_conflict_repair_runtime_controlled_activation_harness_v1 as activation_harness
import trade_registry_closed_identity_conflict_repair_runtime_readiness_binding_contract_v1 as binding


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_READINESS_BINDING_HARNESS_V1_VERSION = (
    "2026-09-05-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-READINESS-BINDING-HARNESS-V1"
)


def _attest_pinned_sources_read_only_v1(repository_root: str | Path) -> list[dict[str, Any]]:
    root = Path(repository_root).resolve()
    attestations: list[dict[str, Any]] = []
    for pin in binding.canonical_c3_readiness_source_attestation_pins_v1():
        source_path = (root / pin["path"]).resolve()
        if root not in source_path.parents:
            raise AssertionError("pinned source escaped repository root")
        source_text = source_path.read_text(encoding="utf-8")
        sha256, size_bytes = binding.source_text_sha256_v1(source_text)
        attestation = {
            "role": pin["role"],
            "path": pin["path"],
            "sha256": sha256,
            "normalized_size_bytes": size_bytes,
        }
        if attestation != pin:
            raise AssertionError(f"pinned source drifted: {pin['role']}")
        attestations.append(attestation)
    return attestations


def build_synthetic_c3_runtime_readiness_binding_inputs_v1(
    repository_root: str | Path,
) -> dict[str, Any]:
    activation_inputs = activation_harness.build_synthetic_c3_controlled_activation_inputs_v1(
        repository_root
    )
    activation_result = activation_contract.evaluate_c3_controlled_runtime_activation_proposal_offline_v1(
        **activation_inputs
    )
    if activation_result.get("ok") is not True:
        raise AssertionError("controlled activation contract failed closed")

    source_attestations = _attest_pinned_sources_read_only_v1(repository_root)
    readiness_vector = binding.canonical_c3_runtime_readiness_vector_v1()
    predicates = binding.canonical_c3_live_preflight_predicates_v1()
    spec = {
        "spec_version": "C3_RUNTIME_READINESS_BINDING_POLICY_OFFLINE_V1",
        "upstream_proposal_receipt_sha256": activation_result["proposal_receipt"][
            "proposal_receipt_sha256"
        ],
        "source_attestations": source_attestations,
        "source_attestations_sha256": binding._stable_sha256(source_attestations),
        "required_runtime_readiness_vector": readiness_vector,
        "required_runtime_readiness_vector_sha256": binding._stable_sha256(
            readiness_vector
        ),
        "live_preflight_predicates": predicates,
        "live_preflight_predicates_sha256": binding._stable_sha256(predicates),
        "consumer_policy": {
            "require_all_predicates": True,
            "missing_field_blocks": True,
            "unknown_field_blocks": True,
            "generic_ok_is_insufficient": True,
            "exact_boolean_identity_required": True,
            "activation_receipt_sha256_required": True,
            "source_attestation_sha256_required": True,
            "static_preflight_must_prove_predicate_semantics": True,
            "runtime_status_must_be_sampled_at_decision_time": True,
            "cached_readiness_forbidden": True,
        },
        "safety_envelope": {
            "scope_attestation": "C3_RUNTIME_READINESS_BINDING_REVIEW_OFFLINE_ONLY_V1",
            "policy_contract_only": True,
            "source_read_only": True,
            "runtime_imported": False,
            "runtime_integrated": False,
            "real_registry_accessed": False,
            "network_accessed": False,
            "broker_called": False,
            "write_executed": False,
            "runtime_patch_authorized": False,
            "production_activation_authorized": False,
            "live_authorized": False,
            "order_submission_authorized": False,
            "no_order_sent": True,
        },
        "dormant": True,
        "default_off": True,
        "offline_only": True,
        "policy_only": True,
        "runtime_binding_satisfied": False,
        "production_ready": False,
        "activation_allowed": False,
        "live_allowed": False,
    }
    spec["spec_sha256"] = binding.readiness_binding_spec_sha256_v1(spec)
    return {
        "controlled_activation_result": activation_result,
        "readiness_binding_spec": spec,
    }


def run_synthetic_c3_runtime_readiness_binding_harness_v1(
    repository_root: str | Path,
) -> dict[str, Any]:
    inputs = build_synthetic_c3_runtime_readiness_binding_inputs_v1(repository_root)
    before = copy.deepcopy(inputs)
    before_sha = binding._stable_sha256(before)
    first = binding.evaluate_c3_runtime_readiness_binding_policy_offline_v1(**inputs)
    second = binding.evaluate_c3_runtime_readiness_binding_policy_offline_v1(
        **copy.deepcopy(inputs)
    )
    after_sha = binding._stable_sha256(inputs)
    receipt = first.get("binding_receipt")
    ok = bool(
        first.get("ok") is True
        and first.get("binding_contract_verified") is True
        and first.get("upstream_activation_contract_verified") is True
        and first.get("source_hashes_verified") is True
        and first.get("runtime_readiness_policy_verified") is True
        and first.get("live_preflight_policy_verified") is True
        and first.get("runtime_binding_satisfied") is False
        and first.get("production_ready") is False
        and first.get("apply_allowed") is False
        and first.get("runtime_patch_allowed") is False
        and first.get("runtime_install_allowed") is False
        and first.get("runtime_start_allowed") is False
        and first.get("activation_allowed") is False
        and first.get("live_allowed") is False
        and first.get("runtime_imported") is False
        and first.get("runtime_integrated") is False
        and first.get("real_registry_accessed") is False
        and first.get("network_accessed") is False
        and first.get("broker_called") is False
        and first.get("write_executed") is False
        and first.get("no_order_sent") is True
        and isinstance(receipt, dict)
        and receipt.get("source_attestation_count") == 4
        and receipt.get("required_predicate_count") == 13
        and receipt.get("writer_count") == 19
        and receipt.get("runtime_binding_satisfied") is False
        and receipt.get("activation_allowed") is False
        and receipt.get("production_blockers")
        and inputs == before
        and before_sha == after_sha
        and first == second
    )
    return {
        "ok": ok,
        "status": (
            "C3_RUNTIME_READINESS_BINDING_V1_HARNESS_PASSED_OFFLINE_NON_APPLICABLE"
            if ok
            else "C3_RUNTIME_READINESS_BINDING_V1_HARNESS_FAILED_CLOSED"
        ),
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_READINESS_BINDING_HARNESS_V1_VERSION,
        "dormant": True,
        "default_off": True,
        "offline_only": True,
        "policy_only": True,
        "runtime_binding_satisfied": False,
        "production_ready": False,
        "apply_allowed": False,
        "runtime_patch_allowed": False,
        "runtime_install_allowed": False,
        "runtime_start_allowed": False,
        "activation_allowed": False,
        "live_allowed": False,
        "runtime_imported": False,
        "runtime_integrated": False,
        "real_registry_accessed": False,
        "network_accessed": False,
        "broker_called": False,
        "write_executed": False,
        "no_order_sent": True,
        "input_preserved": inputs == before and before_sha == after_sha,
        "deterministic": first == second,
        "binding_result": first,
    }


__all__ = [
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_READINESS_BINDING_HARNESS_V1_VERSION",
    "build_synthetic_c3_runtime_readiness_binding_inputs_v1",
    "run_synthetic_c3_runtime_readiness_binding_harness_v1",
]
