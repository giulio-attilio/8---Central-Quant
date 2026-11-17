from __future__ import annotations

import json

import execution_orchestrator as orchestrator


def test_missing_seen_ledger_blocks_falcon_pending_preflight(monkeypatch, tmp_path):
    ledger = tmp_path / "execution_seen.json"
    monkeypatch.setattr(orchestrator, "EXECUTION_SEEN_FILE", ledger)
    monkeypatch.setattr(orchestrator, "paper_data_mount_verified", lambda _path: True)

    result = orchestrator.find_falcon_pending_broker_states()

    assert result["ok"] is False
    assert result["status"] == "FALCON_ENGINE_BROKER_LEDGER_MISSING"
    assert result["pending"] == []
    assert result["pending_count"] is None


def test_corrupt_seen_ledger_blocks_falcon_pending_preflight(monkeypatch, tmp_path):
    ledger = tmp_path / "execution_seen.json"
    ledger.write_text("{corrupt", encoding="utf-8")
    monkeypatch.setattr(orchestrator, "EXECUTION_SEEN_FILE", ledger)
    monkeypatch.setattr(orchestrator, "paper_data_mount_verified", lambda _path: True)

    result = orchestrator.find_falcon_pending_broker_states()

    assert result["ok"] is False
    assert result["status"] == "FALCON_ENGINE_BROKER_LEDGER_READ_ERROR"
    assert result["pending_count"] is None
    assert ledger.read_text(encoding="utf-8") == "{corrupt"


def test_unverified_seen_path_blocks_without_reading(monkeypatch, tmp_path):
    ledger = tmp_path / "execution_seen.json"
    ledger.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(orchestrator, "EXECUTION_SEEN_FILE", ledger)
    monkeypatch.setattr(orchestrator, "paper_data_mount_verified", lambda _path: False)

    def forbidden_read(*_args, **_kwargs):
        raise AssertionError("unverified execution ledger must not be read")

    monkeypatch.setattr(type(ledger), "read_text", forbidden_read)

    result = orchestrator.find_falcon_pending_broker_states()

    assert result["ok"] is False
    assert result["status"] == "FALCON_ENGINE_BROKER_LEDGER_MOUNT_NOT_VERIFIED"
    assert result["pending_count"] is None


def test_seen_reader_rejects_non_mapping_and_does_not_fabricate_empty_state(
    monkeypatch, tmp_path
):
    ledger = tmp_path / "execution_seen.json"
    ledger.write_text(json.dumps([]), encoding="utf-8")
    monkeypatch.setattr(orchestrator, "EXECUTION_SEEN_FILE", ledger)
    monkeypatch.setattr(orchestrator, "paper_data_mount_verified", lambda _path: True)

    try:
        orchestrator._load_seen()
    except ValueError as exc:
        assert str(exc) == "EXECUTION_SEEN_STATE_INVALID"
    else:
        raise AssertionError("non-mapping execution ledger was accepted")


def test_orchestration_and_health_report_missing_seen_state_as_unavailable(
    monkeypatch, tmp_path
):
    ledger = tmp_path / "execution_seen.json"
    monkeypatch.setattr(orchestrator, "EXECUTION_SEEN_FILE", ledger)
    monkeypatch.setattr(orchestrator, "paper_data_mount_verified", lambda _path: True)

    result = orchestrator.orchestrate_execution(payload={}, mode="PAPER")
    health = orchestrator.execution_health()

    assert result["ok"] is False
    assert result["payload"]["status"] == "EXECUTION_SEEN_STATE_UNAVAILABLE"
    assert health["ok"] is False
    assert health["status"] == "EXECUTION_SEEN_STATE_UNAVAILABLE"
    assert health["seen_count"] is None
    assert not ledger.exists()


def test_corrupt_seen_state_blocks_orchestration_without_replacing_file(
    monkeypatch, tmp_path
):
    ledger = tmp_path / "execution_seen.json"
    original = "{corrupt-ledger"
    ledger.write_text(original, encoding="utf-8")
    monkeypatch.setattr(orchestrator, "EXECUTION_SEEN_FILE", ledger)
    monkeypatch.setattr(orchestrator, "paper_data_mount_verified", lambda _path: True)

    result = orchestrator.orchestrate_execution(payload={}, mode="PAPER")

    assert result["ok"] is False
    assert result["payload"]["status"] == "EXECUTION_SEEN_STATE_UNAVAILABLE"
    assert ledger.read_text(encoding="utf-8") == original


def test_seen_writer_uses_shared_guarded_atomic_json_writer(monkeypatch, tmp_path):
    ledger = tmp_path / "execution_seen.json"
    calls = []

    def write_atomically(path, payload):
        calls.append((path, payload))
        return True

    monkeypatch.setattr(orchestrator, "EXECUTION_SEEN_FILE", ledger)
    monkeypatch.setattr(orchestrator, "write_json_atomically", write_atomically)

    orchestrator._save_seen({"key": {"mode": "PAPER"}})

    assert calls == [(ledger, {"key": {"mode": "PAPER"}})]
