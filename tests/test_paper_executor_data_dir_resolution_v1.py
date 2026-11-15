import os
from pathlib import Path

import paper_executor_integrated
import outcome_evaluator
import paper_lifecycle


def test_executor_lifecycle_and_outcome_share_the_resolved_storage_path():
    assert paper_executor_integrated.DATA_DIR == paper_lifecycle.DATA_DIR
    assert paper_executor_integrated.DATA_DIR == outcome_evaluator.DATA_DIR


def test_central_data_dir_takes_precedence_over_data_dir(monkeypatch, tmp_path):
    central = tmp_path / "central"
    generic = tmp_path / "generic"
    monkeypatch.setenv("CENTRAL_DATA_DIR", str(central))
    monkeypatch.setenv("DATA_DIR", str(generic))

    assert paper_executor_integrated._resolve_data_dir() == central


def test_data_dir_is_used_when_central_data_dir_is_unset(monkeypatch, tmp_path):
    configured = tmp_path / "render-persistent-data"
    monkeypatch.delenv("CENTRAL_DATA_DIR", raising=False)
    monkeypatch.setenv("DATA_DIR", str(configured))

    assert paper_executor_integrated._resolve_data_dir() == configured


def test_render_mount_is_used_when_no_environment_path_is_configured(monkeypatch):
    monkeypatch.delenv("CENTRAL_DATA_DIR", raising=False)
    monkeypatch.delenv("DATA_DIR", raising=False)
    original_isdir = os.path.isdir
    monkeypatch.setattr(
        paper_executor_integrated.os.path,
        "isdir",
        lambda path: True if path == "/data" else original_isdir(path),
    )

    assert paper_executor_integrated._resolve_data_dir() == Path("/data")


def test_local_fallback_is_module_relative_when_render_mount_is_absent(monkeypatch):
    monkeypatch.delenv("CENTRAL_DATA_DIR", raising=False)
    monkeypatch.delenv("DATA_DIR", raising=False)
    monkeypatch.setattr(paper_executor_integrated.os.path, "isdir", lambda _path: False)

    assert paper_executor_integrated._resolve_data_dir() == (
        Path(paper_executor_integrated.__file__).resolve().parent / "data"
    )


def test_lifecycle_and_outcome_health_do_not_report_missing_state_as_zero(
    monkeypatch, tmp_path
):
    positions = tmp_path / "paper_integrated_positions.json"
    monkeypatch.setattr(paper_lifecycle, "PAPER_POSITIONS_FILE", positions)
    monkeypatch.setattr(paper_lifecycle, "PAPER_LIFECYCLE_ENABLED", True)
    monkeypatch.setattr(outcome_evaluator, "PAPER_POSITIONS_FILE", positions)
    monkeypatch.setattr(outcome_evaluator, "OUTCOME_EVALUATOR_ENABLED", True)

    lifecycle = paper_lifecycle.paper_lifecycle_health()
    outcome = outcome_evaluator.outcome_evaluator_health()
    assert lifecycle["ok"] is False
    assert lifecycle["state_files_status"] == "PAPER_STATE_FILES_MISSING"
    assert lifecycle["state_files_present"] is False
    assert lifecycle["open_positions"] is None
    assert outcome["ok"] is False
    assert outcome["state_files_status"] == "PAPER_STATE_FILES_MISSING"
    assert outcome["state_files_present"] is False
    assert outcome["closed_positions"] is None

    positions.write_text("[]", encoding="utf-8")
    lifecycle = paper_lifecycle.paper_lifecycle_health()
    outcome = outcome_evaluator.outcome_evaluator_health()
    assert lifecycle["ok"] is True
    assert lifecycle["open_positions"] == 0
    assert outcome["ok"] is True
    assert outcome["closed_positions"] == 0

    positions.write_text("not-json", encoding="utf-8")
    lifecycle = paper_lifecycle.paper_lifecycle_health()
    outcome = outcome_evaluator.outcome_evaluator_health()
    assert lifecycle["state_files_status"] == "PAPER_STATE_FILES_INVALID"
    assert lifecycle["state_files_present"] is True
    assert lifecycle["open_positions"] is None
    assert outcome["state_files_status"] == "PAPER_STATE_FILES_INVALID"
    assert outcome["state_files_present"] is True
    assert outcome["closed_positions"] is None


def test_lifecycle_positions_endpoint_fails_closed_for_missing_or_invalid_state(
    monkeypatch, tmp_path
):
    positions = tmp_path / "paper_integrated_positions.json"
    monkeypatch.setattr(paper_lifecycle, "PAPER_POSITIONS_FILE", positions)

    missing = paper_lifecycle.get_paper_lifecycle_positions()
    assert missing["ok"] is False
    assert missing["status"] == "PAPER_STATE_FILES_MISSING"
    assert missing["count"] is None
    assert missing["positions"] is None
    assert not positions.exists()

    positions.write_text("not-json", encoding="utf-8")
    invalid = paper_lifecycle.get_paper_lifecycle_positions()
    assert invalid["ok"] is False
    assert invalid["status"] == "PAPER_STATE_FILES_INVALID"
    assert invalid["count"] is None
    assert invalid["positions"] is None

    positions.write_text("[]", encoding="utf-8")
    empty = paper_lifecycle.get_paper_lifecycle_positions()
    assert empty["ok"] is True
    assert empty["status"] == "PAPER_STATE_FILES_PRESENT"
    assert empty["count"] == 0
    assert empty["positions"] == []


def test_lifecycle_update_and_outcome_eval_fail_closed_when_positions_missing(
    monkeypatch, tmp_path
):
    positions = tmp_path / "paper_integrated_positions.json"
    lifecycle_log = tmp_path / "paper_lifecycle.jsonl"
    stats = tmp_path / "stats.json"
    monkeypatch.setattr(paper_lifecycle, "PAPER_POSITIONS_FILE", positions)
    monkeypatch.setattr(paper_lifecycle, "PAPER_LIFECYCLE_ENABLED", True)
    monkeypatch.setattr(paper_lifecycle, "PAPER_LIFECYCLE_LOG_FILE", lifecycle_log)
    monkeypatch.setattr(outcome_evaluator, "PAPER_POSITIONS_FILE", positions)
    monkeypatch.setattr(outcome_evaluator, "OUTCOME_EVALUATOR_ENABLED", True)
    monkeypatch.setattr(outcome_evaluator, "OUTCOME_STATS_FILE", stats)

    update = paper_lifecycle.update_paper_position_price(price=100.0)
    evaluate = outcome_evaluator.evaluate_closed_paper_trades()
    assert update["ok"] is False
    assert update["error"] == "PAPER_STATE_FILES_MISSING"
    assert evaluate["ok"] is False
    assert evaluate["status"] == "PAPER_STATE_FILES_MISSING"
    assert not positions.exists()
    assert not lifecycle_log.exists()
    assert not stats.exists()
