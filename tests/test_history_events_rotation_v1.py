from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

import history_manager


def _write_rows(path: Path, rows) -> bytes:
    raw = b"".join(
        json.dumps(row, ensure_ascii=False).encode("utf-8") + b"\n"
        for row in rows
    )
    path.write_bytes(raw)
    return raw


def _read_rows(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _sample_rows():
    return [
        {"event": "DEBUG_SNAPSHOT", "execution_mode": "PAPER", "id": "drop-debug"},
        {"event": "SIGNAL_CREATED", "execution_mode": "PAPER", "id": "drop-paper"},
        {"event": "LIVE_SENT", "execution_mode": "LIVE", "sent": True, "id": "keep-live"},
        {"event": "TRADE_BLOCKED", "bot": "FALCON", "execution_mode": "PAPER", "id": "keep-falcon"},
        {"event": "CUSTOM_LEGACY_FACT", "id": "keep-uncertain"},
        {"event": "DEBUG_RECENT", "execution_mode": "PAPER", "id": "recent-1"},
        {"event": "SIGNAL_RECENT", "execution_mode": "PAPER", "id": "recent-2"},
        {"event": "HEARTBEAT_RECENT", "execution_mode": "PAPER", "id": "recent-3"},
    ]


def test_preview_is_read_only_and_reports_exact_plan(tmp_path):
    path = tmp_path / "history_events.jsonl"
    before = _write_rows(path, _sample_rows())

    result = history_manager.preview_history_events_rotation(keep_recent=3, path=path)

    assert result["ok"] is True
    assert result["status"] == "READY"
    assert result["dry_run"] is True
    assert result["safe_to_commit"] is True
    assert result["events_read"] == 8
    assert result["events_keep_recent"] == 3
    assert result["events_keep_critical"] == 2
    assert result["events_keep_uncertain"] == 1
    assert result["events_drop_or_archive"] == 2
    assert path.read_bytes() == before


@pytest.mark.parametrize("ack", [None, "", "WRONG_ACK", "history_rotation_v1"])
def test_commit_requires_exact_ack_and_never_changes_file(tmp_path, ack):
    path = tmp_path / "history_events.jsonl"
    before = _write_rows(path, _sample_rows())

    result = history_manager.commit_history_events_rotation(ack, keep_recent=3, path=path)

    assert result["committed"] is False
    assert result["status"] == "ACK_REQUIRED"
    assert path.read_bytes() == before


def test_commit_compacts_old_noncritical_rows_and_is_atomic(tmp_path):
    path = tmp_path / "history_events.jsonl"
    _write_rows(path, _sample_rows())

    result = history_manager.commit_history_events_rotation(
        history_manager.HISTORY_ROTATION_V1_ACK,
        keep_recent=3,
        path=path,
    )

    rows = _read_rows(path)
    ids = [row["id"] for row in rows]
    assert result["status"] == "COMMITTED"
    assert result["committed"] is True
    assert result["backup_created"] is False
    assert result["events_before"] == 8
    assert result["events_after"] == 6
    assert result["events_removed"] == 2
    assert ids == ["keep-live", "keep-falcon", "keep-uncertain", "recent-1", "recent-2", "recent-3"]
    assert not list(tmp_path.glob(".*.rotation-v1-*.tmp"))


@pytest.mark.parametrize(
    "event_type",
    sorted(history_manager.HISTORY_ROTATION_V1_CRITICAL_EVENT_TYPES),
)
def test_every_declared_critical_event_type_is_preserved_when_old(tmp_path, event_type):
    path = tmp_path / "history_events.jsonl"
    _write_rows(path, [
        {"event": event_type, "id": "critical-old"},
        {"event": "DEBUG_OLD", "execution_mode": "PAPER", "id": "drop"},
        {"event": "DEBUG_RECENT", "execution_mode": "PAPER", "id": "recent"},
    ])

    result = history_manager.commit_history_events_rotation(
        history_manager.HISTORY_ROTATION_V1_ACK,
        keep_recent=1,
        path=path,
    )

    assert result["committed"] is True
    assert [row["id"] for row in _read_rows(path)] == ["critical-old", "recent"]


def test_live_mode_or_sent_true_is_preserved_without_known_event_name(tmp_path):
    path = tmp_path / "history_events.jsonl"
    _write_rows(path, [
        {"event": "UNKNOWN_FACT", "execution_mode": "LIVE", "id": "live-mode"},
        {"event": "UNKNOWN_FACT", "sent": True, "id": "sent-true"},
        {"event": "DEBUG_OLD", "execution_mode": "PAPER", "id": "drop"},
        {"event": "DEBUG_RECENT", "execution_mode": "PAPER", "id": "recent"},
    ])

    result = history_manager.commit_history_events_rotation(
        history_manager.HISTORY_ROTATION_V1_ACK,
        keep_recent=1,
        path=path,
    )

    assert result["committed"] is True
    assert [row["id"] for row in _read_rows(path)] == ["live-mode", "sent-true", "recent"]


def test_malformed_jsonl_blocks_preview_and_commit_without_rewrite(tmp_path):
    path = tmp_path / "history_events.jsonl"
    before = b'{"event":"DEBUG_OLD","execution_mode":"PAPER"}\nnot-json\n'
    path.write_bytes(before)

    preview = history_manager.preview_history_events_rotation(keep_recent=1, path=path)
    committed = history_manager.commit_history_events_rotation(
        history_manager.HISTORY_ROTATION_V1_ACK,
        keep_recent=1,
        path=path,
    )

    assert preview["safe_to_commit"] is False
    assert preview["reason"] == "MALFORMED_JSONL"
    assert committed["committed"] is False
    assert path.read_bytes() == before


def test_missing_file_fails_safely(tmp_path):
    path = tmp_path / "missing.jsonl"

    preview = history_manager.preview_history_events_rotation(path=path)
    committed = history_manager.commit_history_events_rotation(
        history_manager.HISTORY_ROTATION_V1_ACK,
        path=path,
    )

    assert preview["reason"] == "HISTORY_EVENTS_FILE_NOT_FOUND"
    assert committed["committed"] is False
    assert not path.exists()


def test_insufficient_temp_space_blocks_without_rewrite(tmp_path, monkeypatch):
    path = tmp_path / "history_events.jsonl"
    before = _write_rows(path, _sample_rows())
    monkeypatch.setattr(history_manager.shutil, "disk_usage", lambda _path: type("Usage", (), {"free": 0})())

    result = history_manager.commit_history_events_rotation(
        history_manager.HISTORY_ROTATION_V1_ACK,
        keep_recent=3,
        path=path,
    )

    assert result["committed"] is False
    assert result["reason"] == "INSUFFICIENT_TEMP_SPACE"
    assert path.read_bytes() == before


def test_event_appended_during_compaction_is_preserved(tmp_path, monkeypatch):
    path = tmp_path / "history_events.jsonl"
    _write_rows(path, _sample_rows())
    original = history_manager._history_rotation_v1_should_keep
    appended = False

    def append_once(event, is_recent):
        nonlocal appended
        if not appended:
            appended = True
            assert history_manager._append_jsonl(path, {
                "event": "LIVE_SENT",
                "execution_mode": "LIVE",
                "sent": True,
                "id": "appended-during-compaction",
            })
        return original(event, is_recent)

    monkeypatch.setattr(history_manager, "_history_rotation_v1_should_keep", append_once)
    result = history_manager.commit_history_events_rotation(
        history_manager.HISTORY_ROTATION_V1_ACK,
        keep_recent=3,
        path=path,
    )

    assert result["committed"] is True
    assert result["events_appended_during_compaction"] == 1
    assert _read_rows(path)[-1]["id"] == "appended-during-compaction"


def test_rotation_has_no_network_or_operational_imports(tmp_path, monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("network attempted")

    monkeypatch.setattr(socket, "socket", forbidden)
    path = tmp_path / "history_events.jsonl"
    _write_rows(path, _sample_rows())

    result = history_manager.commit_history_events_rotation(
        history_manager.HISTORY_ROTATION_V1_ACK,
        keep_recent=3,
        path=path,
    )

    assert result["committed"] is True


def test_main_declares_read_only_preview_and_ack_commit_routes():
    source = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")
    assert '@app.route("/history/rotation/preview/text", methods=["GET"])' in source
    assert '@app.route("/history/rotation/commit/text", methods=["GET"])' in source
    assert '@app.route("/history/rotation/emergency/preview/text", methods=["GET"])' in source
    assert '@app.route("/history/rotation/emergency/commit/text", methods=["GET"])' in source
    assert "commit_history_events_rotation" in source
    assert "HISTORY_ROTATION_V1" in history_manager.HISTORY_ROTATION_V1_ACK


def _write_emergency_sample(path: Path) -> bytes:
    rows = [
        {"event": "DEBUG_OLD", "execution_mode": "PAPER", "id": "drop-debug"},
        {"event": "CUSTOM_UNCERTAIN_OLD", "id": "drop-uncertain"},
        {"event": "LIVE_SENT", "execution_mode": "LIVE", "sent": True, "id": "keep-live"},
        {"event": "TRADE_BLOCKED", "bot": "FALCON", "execution_mode": "PAPER", "id": "keep-falcon"},
        {"event": "SIGNAL_OLD", "execution_mode": "PAPER", "id": "drop-signal"},
        {"event": "DEBUG_RECENT_1", "execution_mode": "PAPER", "id": "recent-1"},
        {"event": "DEBUG_RECENT_2", "execution_mode": "PAPER", "id": "recent-2"},
    ]
    raw = b"".join(json.dumps(row).encode("utf-8") + b"\n" for row in rows)
    raw += b"{malformed-emergency-line\n"
    path.write_bytes(raw)
    return raw


def test_emergency_preview_is_read_only_and_accepts_malformed_for_quarantine(tmp_path):
    path = tmp_path / "history_events.jsonl"
    before = _write_emergency_sample(path)

    result = history_manager.preview_history_events_emergency_rotation(
        keep_recent=2,
        max_output_mb=1,
        path=path,
        central_live_positions_count=0,
    )

    assert result["status"] == "READY"
    assert result["safe_to_commit"] is True
    assert result["dry_run"] is True
    assert result["malformed_lines_count"] == 1
    assert result["malformed_line_numbers"] == [8]
    assert result["quarantine_would_be_created"] is True
    assert result["critical_preserved"] == 2
    assert result["recent_preserved"] == 2
    assert result["events_after"] == 4
    assert path.read_bytes() == before


@pytest.mark.parametrize("ack", [None, "", "HISTORY_ROTATION_V1", "WRONG"])
def test_emergency_commit_requires_strong_exact_ack(tmp_path, ack):
    path = tmp_path / "history_events.jsonl"
    before = _write_emergency_sample(path)

    result = history_manager.commit_history_events_emergency_rotation(
        ack,
        keep_recent=2,
        max_output_mb=1,
        path=path,
        central_live_positions_count=0,
    )

    assert result["status"] == "ACK_REQUIRED"
    assert result["committed"] is False
    assert path.read_bytes() == before
    assert list(tmp_path.iterdir()) == [path]


def test_emergency_commit_preserves_recent_and_critical_and_writes_evidence(tmp_path):
    path = tmp_path / "history_events.jsonl"
    _write_emergency_sample(path)

    result = history_manager.commit_history_events_emergency_rotation(
        history_manager.HISTORY_ROTATION_EMERGENCY_V1_ACK,
        keep_recent=2,
        max_output_mb=1,
        path=path,
        central_live_positions_count=0,
    )

    rows = _read_rows(path)
    assert result["status"] == "COMMITTED"
    assert result["committed"] is True
    assert result["backup_created"] is False
    assert [row["id"] for row in rows] == ["keep-live", "keep-falcon", "recent-1", "recent-2"]
    assert result["manifest_created"] is True
    assert result["malformed_quarantine_created"] is True
    manifest_path = Path(result["manifest_file"])
    quarantine_path = Path(result["malformed_quarantine_file"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "COMMITTED"
    assert manifest["malformed_lines_count"] == 1
    assert manifest["malformed_line_numbers"] == [8]
    assert manifest["policy"]["large_backup_created"] is False
    assert manifest["emergency_ack_required"] == "HISTORY_ROTATION_EMERGENCY_V1"
    assert quarantine_path.read_bytes() == b"{malformed-emergency-line\n"
    assert not list(tmp_path.glob("*.bak"))


def test_emergency_respects_max_output_by_reducing_noncritical_recent(tmp_path):
    path = tmp_path / "history_events.jsonl"
    rows = [{"event": "LIVE_SENT", "sent": True, "id": "critical"}]
    rows.extend(
        {"event": "DEBUG_RECENT", "execution_mode": "PAPER", "id": number, "padding": "x" * 1800}
        for number in range(20)
    )
    _write_rows(path, rows)

    result = history_manager.commit_history_events_emergency_rotation(
        history_manager.HISTORY_ROTATION_EMERGENCY_V1_ACK,
        keep_recent=20,
        max_output_mb=0.01,
        path=path,
        central_live_positions_count=0,
    )

    assert result["committed"] is True
    assert path.stat().st_size <= int(0.01 * 1024 * 1024)
    kept = _read_rows(path)
    assert kept[0]["id"] == "critical"
    assert len(kept) < len(rows)
    assert "RECENT_NONCRITICAL_REDUCED_TO_FIT_OUTPUT_TARGET" in result["warnings"]


def test_emergency_aborts_when_critical_evidence_exceeds_target(tmp_path):
    path = tmp_path / "history_events.jsonl"
    before = _write_rows(path, [
        {"event": "LIVE_SENT", "sent": True, "padding": "x" * 5000},
        {"event": "DEBUG_RECENT", "execution_mode": "PAPER"},
    ])

    result = history_manager.commit_history_events_emergency_rotation(
        history_manager.HISTORY_ROTATION_EMERGENCY_V1_ACK,
        keep_recent=1,
        max_output_mb=0.001,
        path=path,
        central_live_positions_count=0,
    )

    assert result["committed"] is False
    assert result["reason"] == "CRITICAL_EVENTS_EXCEED_OUTPUT_TARGET"
    assert path.read_bytes() == before


def test_emergency_aborts_when_temp_cannot_fit(tmp_path, monkeypatch):
    path = tmp_path / "history_events.jsonl"
    before = _write_emergency_sample(path)
    monkeypatch.setattr(history_manager.shutil, "disk_usage", lambda _path: type("Usage", (), {"free": 0})())

    result = history_manager.commit_history_events_emergency_rotation(
        history_manager.HISTORY_ROTATION_EMERGENCY_V1_ACK,
        keep_recent=2,
        max_output_mb=1,
        path=path,
        central_live_positions_count=0,
    )

    assert result["committed"] is False
    assert result["reason"] == "INSUFFICIENT_TEMP_SPACE"
    assert path.read_bytes() == before


def test_emergency_blocks_when_central_live_position_is_open(tmp_path):
    path = tmp_path / "history_events.jsonl"
    before = _write_emergency_sample(path)

    result = history_manager.commit_history_events_emergency_rotation(
        history_manager.HISTORY_ROTATION_EMERGENCY_V1_ACK,
        keep_recent=2,
        max_output_mb=1,
        path=path,
        central_live_positions_count=1,
    )

    assert result["committed"] is False
    assert result["reason"] == "CENTRAL_LIVE_POSITIONS_OPEN"
    assert path.read_bytes() == before


def test_emergency_uses_os_replace_for_history_file(tmp_path, monkeypatch):
    path = tmp_path / "history_events.jsonl"
    _write_emergency_sample(path)
    original_replace = history_manager.os.replace
    destinations = []

    def tracked_replace(source, destination):
        destinations.append(Path(destination))
        return original_replace(source, destination)

    monkeypatch.setattr(history_manager.os, "replace", tracked_replace)
    result = history_manager.commit_history_events_emergency_rotation(
        history_manager.HISTORY_ROTATION_EMERGENCY_V1_ACK,
        keep_recent=2,
        max_output_mb=1,
        path=path,
        central_live_positions_count=0,
    )

    assert result["committed"] is True
    assert path in destinations


def test_emergency_can_continue_with_hash_manifest_when_quarantine_does_not_fit(tmp_path, monkeypatch):
    path = tmp_path / "history_events.jsonl"
    malformed = b"{" + (b"x" * 400_000) + b"\n"
    valid = b'{"event":"LIVE_SENT","sent":true}\n' + b'{"event":"DEBUG_RECENT","execution_mode":"PAPER"}\n'
    path.write_bytes(valid + malformed)
    free_bytes = (
        history_manager.HISTORY_ROTATION_V1_MIN_FREE_RESERVE_BYTES
        + history_manager.HISTORY_ROTATION_EMERGENCY_V1_MANIFEST_RESERVE_BYTES
        + 100_000
    )
    monkeypatch.setattr(
        history_manager.shutil,
        "disk_usage",
        lambda _path: type("Usage", (), {"free": free_bytes})(),
    )

    result = history_manager.commit_history_events_emergency_rotation(
        history_manager.HISTORY_ROTATION_EMERGENCY_V1_ACK,
        keep_recent=1,
        max_output_mb=0.1,
        path=path,
        central_live_positions_count=0,
    )

    assert result["committed"] is True
    assert result["malformed_quarantine_created"] is False
    manifest = json.loads(Path(result["manifest_file"]).read_text(encoding="utf-8"))
    assert manifest["malformed_line_numbers"] == [3]
    assert len(manifest["malformed_line_hashes"]) == 1
    assert "MALFORMED_CONTENT_HASH_ONLY_NO_QUARANTINE_SPACE" in result["warnings"]


def test_emergency_without_live_provider_never_calls_network(tmp_path, monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("network attempted")

    monkeypatch.setattr(socket, "socket", forbidden)
    path = tmp_path / "history_events.jsonl"
    _write_emergency_sample(path)

    result = history_manager.commit_history_events_emergency_rotation(
        history_manager.HISTORY_ROTATION_EMERGENCY_V1_ACK,
        keep_recent=2,
        max_output_mb=1,
        path=path,
        central_live_positions_count=None,
    )

    assert result["committed"] is True
    assert "CENTRAL_LIVE_POSITIONS_NOT_VERIFIED_NO_BROKER_CALL_PERFORMED" in result["warnings"]
