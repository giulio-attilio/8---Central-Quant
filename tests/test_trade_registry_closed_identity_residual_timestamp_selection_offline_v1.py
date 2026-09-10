from __future__ import annotations

import ast
import copy
from pathlib import Path

import trade_registry_closed_identity_residual_repair_offline_contract_v1 as residual
import trade_registry_closed_identity_residual_timestamp_selection_offline_contract_v1 as selection
import trade_registry_closed_identity_residual_timestamp_selection_offline_harness_v1 as harness


ROOT = Path(__file__).resolve().parents[1]


def _inputs():
    prior = harness.build_prior_residual_plan_v1()
    evidence = harness.build_synthetic_factual_evidence_bundle_v1(prior)
    return prior, evidence


def _select(prior, evidence):
    return selection.build_residual_timestamp_selection_plan_v1(
        prior,
        evidence,
        expected_evidence_bundle_sha256=residual.stable_sha256_v1(evidence),
    )


def test_harness_resolves_all_32_only_with_synthetic_attestations():
    result = harness.run_residual_timestamp_selection_offline_harness_v1()

    assert result["ok"] is True
    assert all(result["checks"].values())
    assert result["selection_plan"]["status"] == "OFFLINE_TIMESTAMP_SELECTION_COMPLETE"


def test_selection_is_deterministic_and_does_not_mutate_inputs():
    prior, evidence = _inputs()
    prior_copy = copy.deepcopy(prior)
    evidence_copy = copy.deepcopy(evidence)

    first = _select(prior, evidence)
    second = _select(prior, evidence)

    assert prior == prior_copy
    assert evidence == evidence_copy
    assert first == second
    assert first["selection_plan_sha256"] == second["selection_plan_sha256"]


def test_attested_selection_preserves_both_raw_aliases_and_unrelated_fields():
    prior, evidence = _inputs()
    result = _select(prior, evidence)
    before_rows = prior["candidate_registry"]["closed_trades"]
    after_rows = result["candidate_registry"]["closed_trades"]

    assert len(result["actions"]) == 32
    assert len(after_rows) == len(before_rows) == 43
    for action in result["actions"]:
        index = action["registry_index"]
        before = before_rows[index]
        after = after_rows[index]
        archive = after["metadata"]["c3_residual_timestamp_selection_v1"]
        assert archive["original_opened_at"] == before["opened_at"]
        assert archive["original_metadata_created_at"] == before["metadata"]["created_at"]
        assert "created_at" not in after["metadata"]
        assert after["opened_at"] == residual.normalize_residual_timestamp_v1(
            before["metadata"]["created_at"]
        )
        assert after["status"] == before["status"] == "CLOSED"
        assert after["entry"] == before["entry"]


def test_missing_evidence_stays_unchanged_and_quarantined():
    prior, evidence = _inputs()
    missing = evidence[:-1]
    result = _select(prior, missing)
    missing_index = evidence[-1]["registry_index"]

    assert result["ok"] is True
    assert result["status"] == "OFFLINE_TIMESTAMP_SELECTION_PARTIAL_QUARANTINE"
    assert result["summary"]["selected_record_count"] == 31
    assert result["summary"]["remaining_quarantined_record_count"] == 1
    assert result["quarantine"] == [
        {
            "registry_index": missing_index,
            "record_sha256": residual.stable_sha256_v1(
                prior["candidate_registry"]["closed_trades"][missing_index]
            ),
            "field": "opened_at",
            "reason": "FACTUAL_TIMESTAMP_EVIDENCE_MISSING",
        }
    ]
    assert result["candidate_registry"]["closed_trades"][missing_index] == prior[
        "candidate_registry"
    ]["closed_trades"][missing_index]


def test_tampered_evidence_is_quarantined_without_changing_its_record():
    prior, evidence = _inputs()
    tampered = copy.deepcopy(evidence)
    tampered[0]["selected_source_value"] = "2026-01-01T00:00:00+00:00"
    tampered[0]["selection_attestation_sha256"] = (
        selection.residual_timestamp_selection_attestation_sha256_v1(
            tampered[0]
        )
    )
    result = _select(prior, tampered)
    index = tampered[0]["registry_index"]

    assert result["ok"] is True
    assert result["quarantine"][0]["reason"] == "EVIDENCE_SOURCE_VALUE_MISMATCH"
    assert result["candidate_registry"]["closed_trades"][index] == prior[
        "candidate_registry"
    ]["closed_trades"][index]


def test_global_digest_prior_plan_and_duplicate_event_tampering_fail_closed():
    prior, evidence = _inputs()
    digest_mismatch = selection.build_residual_timestamp_selection_plan_v1(
        prior,
        evidence,
        expected_evidence_bundle_sha256="0" * 64,
    )
    assert digest_mismatch["reasons"] == ["EVIDENCE_BUNDLE_SHA256_MISMATCH"]

    tampered_prior = copy.deepcopy(prior)
    tampered_prior["quarantine"][0]["reason"] = "tampered"
    prior_result = _select(tampered_prior, evidence)
    assert prior_result["reasons"] == ["PRIOR_PLAN_SHA256_MISMATCH"]

    duplicate = copy.deepcopy(evidence)
    duplicate[1]["independent_event_id"] = duplicate[0]["independent_event_id"]
    duplicate[1]["selection_attestation_sha256"] = (
        selection.residual_timestamp_selection_attestation_sha256_v1(
            duplicate[1]
        )
    )
    duplicate_result = _select(prior, duplicate)
    assert duplicate_result["reasons"] == ["DUPLICATE_INDEPENDENT_EVENT_ID"]

    for result in (digest_mismatch, prior_result, duplicate_result):
        assert result["ok"] is False
        assert result["candidate_registry"] is None
        assert result["apply_allowed"] is False
        assert result["runtime_activation_allowed"] is False
        assert result["write_executed"] is False
        assert result["broker_called"] is False


def test_selection_contract_has_no_runtime_network_or_filesystem_access():
    path = ROOT / "trade_registry_closed_identity_residual_timestamp_selection_offline_contract_v1.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported = set()
    calls = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                calls.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                calls.add(node.func.attr)

    assert imported.isdisjoint(
        {"os", "pathlib", "requests", "httpx", "urllib", "socket", "trade_registry", "main"}
    )
    assert calls.isdisjoint(
        {"open", "write_text", "write_bytes", "remove", "unlink", "urlopen", "request"}
    )
