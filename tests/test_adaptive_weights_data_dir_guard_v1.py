import adaptive_weights
import outcome_evaluator
import paper_executor_integrated
import paper_lifecycle
from pathlib import Path


def test_adaptive_weights_fails_closed_without_verified_paper_data_mount(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(adaptive_weights, "DATA_DIR", tmp_path)
    monkeypatch.setattr(adaptive_weights, "OUTCOME_STATS_FILE", tmp_path / "outcome.json")
    monkeypatch.setattr(adaptive_weights, "ADAPTIVE_WEIGHTS_FILE", tmp_path / "weights.json")
    monkeypatch.setattr(
        adaptive_weights,
        "ADAPTIVE_WEIGHTS_LOG_FILE",
        tmp_path / "weights.jsonl",
    )
    monkeypatch.setattr(adaptive_weights, "ADAPTIVE_WEIGHTS_ENABLED", True)
    monkeypatch.setattr(adaptive_weights, "paper_data_mount_verified", lambda _path: False)

    health = adaptive_weights.adaptive_weights_health()
    built = adaptive_weights.build_adaptive_weights(commit=True)
    current = adaptive_weights.get_adaptive_weights()
    log = adaptive_weights.read_adaptive_weights_log()

    assert health["ok"] is False
    assert health["status"] == "PAPER_DATA_MOUNT_NOT_VERIFIED"
    assert built["ok"] is False
    assert built["status"] == "PAPER_DATA_MOUNT_NOT_VERIFIED"
    assert current["ok"] is False
    assert current["weights"] is None
    assert log["ok"] is False
    assert log["items"] is None
    assert list(tmp_path.iterdir()) == []


def test_paper_and_outcome_log_readers_do_not_report_empty_without_mount(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(paper_executor_integrated, "PAPER_LOG_FILE", tmp_path / "paper.jsonl")
    monkeypatch.setattr(
        paper_executor_integrated,
        "_paper_data_mount_verified",
        lambda: False,
    )
    monkeypatch.setattr(
        outcome_evaluator,
        "OUTCOME_LOG_FILE",
        tmp_path / "outcome.jsonl",
    )
    monkeypatch.setattr(outcome_evaluator, "paper_data_mount_verified", lambda _path: False)

    paper_log = paper_executor_integrated.read_paper_integrated_log()
    outcome_log = outcome_evaluator.read_outcome_log()
    outcome_stats = outcome_evaluator.get_outcome_stats()

    assert paper_log["ok"] is False
    assert paper_log["status"] == "PAPER_DATA_MOUNT_NOT_VERIFIED"
    assert paper_log["items"] is None
    assert outcome_log["ok"] is False
    assert outcome_log["status"] == "PAPER_DATA_MOUNT_NOT_VERIFIED"
    assert outcome_log["items"] is None
    assert outcome_stats["ok"] is False
    assert outcome_stats["status"] == "PAPER_DATA_MOUNT_NOT_VERIFIED"
    assert list(tmp_path.iterdir()) == []


def test_outcome_stats_reader_validates_exact_path_before_reading(
    monkeypatch, tmp_path
):
    stats_file = tmp_path / "outcome_stats.json"
    stats_file.write_text('{"global":{"trades":7}}', encoding="utf-8")
    monkeypatch.setattr(outcome_evaluator, "DATA_DIR", tmp_path)
    monkeypatch.setattr(outcome_evaluator, "OUTCOME_STATS_FILE", stats_file)
    checked_paths = []

    def guard(path):
        candidate = Path(path)
        checked_paths.append(candidate)
        return candidate == tmp_path

    monkeypatch.setattr(outcome_evaluator, "paper_data_mount_verified", guard)

    result = outcome_evaluator.get_outcome_stats()

    assert checked_paths == [tmp_path, stats_file]
    assert result["ok"] is False
    assert result["status"] == "PAPER_DATA_MOUNT_NOT_VERIFIED"
    assert result["stats"] is None


def test_all_paper_jsonl_callers_validate_the_exact_log_path(monkeypatch, tmp_path):
    cases = (
        (paper_executor_integrated, "PAPER_LOG_FILE", "_append_jsonl", "read_paper_integrated_log"),
        (paper_lifecycle, "PAPER_LIFECYCLE_LOG_FILE", "_append_jsonl", "read_paper_lifecycle_log"),
        (outcome_evaluator, "OUTCOME_LOG_FILE", "_append_jsonl", "read_outcome_log"),
        (adaptive_weights, "ADAPTIVE_WEIGHTS_LOG_FILE", "_append_jsonl", "read_adaptive_weights_log"),
    )
    for index, (module, path_attr, append_name, read_name) in enumerate(cases):
        log_path = tmp_path / f"paper-{index}.jsonl"
        monkeypatch.setattr(module, "DATA_DIR", tmp_path, raising=False)
        monkeypatch.setattr(module, path_attr, log_path)
        monkeypatch.setattr(
            module,
            "paper_data_mount_verified",
            lambda path, expected=log_path: Path(path) != expected,
            raising=False,
        )
        if module is paper_executor_integrated:
            monkeypatch.setattr(module, "_paper_data_mount_verified", lambda: True)

        append = getattr(module, append_name)
        if module is outcome_evaluator:
            import pytest
            with pytest.raises(OSError, match="PAPER_DATA_MOUNT_NOT_VERIFIED"):
                append(log_path, {"event": "test"})
        else:
            assert append(log_path, {"event": "test"}) is False

        read = getattr(module, read_name)()
        assert read["ok"] is False
        assert read["status"] == "PAPER_DATA_MOUNT_NOT_VERIFIED"
        assert not log_path.exists()


def test_lifecycle_and_adaptive_log_writers_delegate_parent_creation_to_guarded_storage(
    monkeypatch, tmp_path
):
    import pytest

    cases = (
        (paper_lifecycle, "PAPER_LIFECYCLE_LOG_FILE"),
        (adaptive_weights, "ADAPTIVE_WEIGHTS_LOG_FILE"),
    )

    def forbidden_mkdir(*_args, **_kwargs):
        raise AssertionError("caller must not create a PAPER log parent by path")

    monkeypatch.setattr(Path, "mkdir", forbidden_mkdir)
    for index, (module, path_attr) in enumerate(cases):
        path = tmp_path / f"nested-{index}" / "paper.jsonl"
        monkeypatch.setattr(module, path_attr, path)
        monkeypatch.setattr(
            module,
            "paper_data_mount_verified",
            lambda _path: True,
        )
        monkeypatch.setattr(module, "append_paper_text", lambda *_args, **_kwargs: None)

        assert module._append_jsonl(path, {"event": "test"}) is True
