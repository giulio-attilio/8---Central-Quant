from __future__ import annotations

import ast
import copy
import hashlib
import json
from pathlib import Path

import trade_registry_closed_identity_residual_repair_offline_contract_v1 as residual
import trade_registry_closed_identity_residual_timestamp_evidence_extractor_offline_contract_v1 as extractor
import trade_registry_closed_identity_residual_timestamp_evidence_extractor_offline_harness_v1 as harness
import trade_registry_closed_identity_residual_timestamp_selection_offline_contract_v1 as selection
import trade_registry_closed_identity_residual_timestamp_selection_offline_harness_v1 as selection_harness


ROOT = Path(__file__).resolve().parents[1]


def _inputs():
    prior = selection_harness.build_prior_residual_plan_v1()
    source, indexes = harness.build_synthetic_history_jsonl_v1(prior)
    return prior, source, indexes


def _extract(prior, source):
    return extractor.extract_residual_timestamp_evidence_v1(
        prior,
        source,
        expected_source_sha256=hashlib.sha256(source.encode("utf-8")).hexdigest(),
    )


def test_harness_extracts_ten_and_keeps_twenty_two_quarantined():
    result = harness.run_residual_timestamp_evidence_extractor_offline_harness_v1()

    assert result["ok"] is True
    assert all(result["checks"].values())
    assert result["extraction"]["status"] == "OFFLINE_TIMESTAMP_EVIDENCE_PARTIAL"


def test_extraction_is_deterministic_and_does_not_mutate_prior_plan():
    prior, source, _indexes = _inputs()
    original = copy.deepcopy(prior)

    first = _extract(prior, source)
    second = _extract(prior, source)

    assert prior == original
    assert first == second
    assert first["extractor_receipt_sha256"] == second["extractor_receipt_sha256"]


def test_every_attestation_has_distinct_open_close_hashes_and_selection_accepts_it():
    prior, source, indexes = _inputs()
    result = _extract(prior, source)

    assert len(result["evidence"]) == 10
    assert [item["registry_index"] for item in result["evidence"]] == indexes
    for evidence in result["evidence"]:
        assert evidence["independent_source"] == "history_events.jsonl"
        assert evidence["independent_source_record_sha256"] != evidence[
            "corroborating_close_record_sha256"
        ]
        assert evidence["source_event_record_count"] == 2
        assert evidence["selected_source_path"] == "trade.metadata.created_at"
        assert evidence["selection_attestation_sha256"] == (
            selection.residual_timestamp_selection_attestation_sha256_v1(
                evidence
            )
        )

    selected = selection.build_residual_timestamp_selection_plan_v1(
        prior,
        result["evidence"],
        expected_evidence_bundle_sha256=result["evidence_bundle_sha256"],
    )
    assert selected["summary"]["selected_record_count"] == 10
    assert selected["summary"]["remaining_quarantined_record_count"] == 22


def test_open_event_without_distinct_close_event_does_not_attest():
    prior, source, indexes = _inputs()
    lines = source.splitlines()
    target_trade_id = prior["candidate_registry"]["closed_trades"][indexes[0]][
        "trade_id"
    ]
    reduced = "\n".join(
        line
        for line in lines
        if not (
            json.loads(line).get("event") == "TRADE_CLOSED"
            and json.loads(line).get("trade_id") == target_trade_id
        )
    )
    result = _extract(prior, reduced)

    assert result["summary"]["attested_record_count"] == 9
    unresolved = {
        item["registry_index"]: item for item in result["unresolved"]
    }
    assert unresolved[indexes[0]]["reason"] == "DISTINCT_OPEN_CLOSE_EVENT_CHAIN_NOT_PROVEN"
    assert unresolved[indexes[0]]["matching_open_event_count"] == 1
    assert unresolved[indexes[0]]["matching_close_event_count"] == 0


def test_wrong_trade_id_or_timestamp_cannot_attest():
    prior, source, indexes = _inputs()
    lines = [json.loads(line) for line in source.splitlines()]
    target = prior["candidate_registry"]["closed_trades"][indexes[0]]
    for event in lines:
        if event.get("trade_id") == target["trade_id"]:
            event["trade_id"] = "TURTLE:WRONG:TRADE"
            event["raw"]["trade_id"] = "TURTLE:WRONG:TRADE"
    changed = "\n".join(
        json.dumps(line, sort_keys=True, separators=(",", ":")) for line in lines
    )
    wrong_id = _extract(prior, changed)
    assert wrong_id["summary"]["attested_record_count"] == 9

    lines = [json.loads(line) for line in source.splitlines()]
    for event in lines:
        if event.get("trade_id") == target["trade_id"]:
            event["ts"] = "2020-01-01T00:00:00+00:00"
            event["raw"]["created_at"] = "2020-01-01T00:00:00+00:00"
    changed = "\n".join(
        json.dumps(line, sort_keys=True, separators=(",", ":")) for line in lines
    )
    wrong_timestamp = _extract(prior, changed)
    assert wrong_timestamp["summary"]["attested_record_count"] == 9


def test_source_digest_malformed_line_and_caps_fail_closed():
    prior, source, _indexes = _inputs()
    mismatch = extractor.extract_residual_timestamp_evidence_v1(
        prior,
        source,
        expected_source_sha256="0" * 64,
    )
    assert mismatch["reasons"] == ["SOURCE_SHA256_MISMATCH"]

    malformed = source + "\n{invalid"
    malformed_result = _extract(prior, malformed)
    assert malformed_result["reasons"] == ["SOURCE_JSONL_MALFORMED_LINE"]

    capped = extractor.extract_residual_timestamp_evidence_v1(
        prior,
        source,
        expected_source_sha256=hashlib.sha256(source.encode("utf-8")).hexdigest(),
        caps=extractor.ResidualTimestampEvidenceExtractorCapsV1(
            max_lines=1
        ),
    )
    assert capped["reasons"] == ["SOURCE_LINE_CAP_EXCEEDED"]

    for result in (mismatch, malformed_result, capped):
        assert result["ok"] is False
        assert result["evidence"] == []
        assert result["apply_allowed"] is False
        assert result["runtime_activation_allowed"] is False
        assert result["write_executed"] is False
        assert result["broker_called"] is False


def test_extractor_has_no_runtime_network_or_filesystem_access():
    path = ROOT / "trade_registry_closed_identity_residual_timestamp_evidence_extractor_offline_contract_v1.py"
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
