import json
import os
import stat
from pathlib import Path
from types import SimpleNamespace

import adaptive_weights
import execution_engine
import execution_orchestrator
import execution_pipeline_status
import paper_executor_integrated
import outcome_evaluator
import paper_lifecycle
import paper_state_storage


def test_executor_lifecycle_and_outcome_share_the_resolved_storage_path():
    assert paper_executor_integrated.DATA_DIR == paper_lifecycle.DATA_DIR
    assert paper_executor_integrated.DATA_DIR == outcome_evaluator.DATA_DIR
    assert paper_executor_integrated.DATA_DIR == execution_pipeline_status.DATA_DIR
    assert paper_executor_integrated.DATA_DIR == adaptive_weights.DATA_DIR
    assert paper_executor_integrated.DATA_DIR == execution_engine.DATA_DIR
    assert paper_executor_integrated.DATA_DIR == execution_orchestrator.DATA_DIR


def test_central_data_dir_takes_precedence_over_data_dir(monkeypatch, tmp_path):
    central = tmp_path / "central"
    generic = tmp_path / "generic"
    monkeypatch.setenv("CENTRAL_DATA_DIR", str(central))
    monkeypatch.setenv("DATA_DIR", str(generic))

    assert paper_executor_integrated._resolve_data_dir() == central
    assert execution_pipeline_status._resolve_data_dir() == central
    assert adaptive_weights._resolve_data_dir() == central
    assert execution_engine._resolve_data_dir() == central
    assert execution_orchestrator._resolve_data_dir() == central


def test_data_dir_is_used_when_central_data_dir_is_unset(monkeypatch, tmp_path):
    configured = tmp_path / "render-persistent-data"
    monkeypatch.delenv("CENTRAL_DATA_DIR", raising=False)
    monkeypatch.setenv("DATA_DIR", str(configured))

    assert paper_executor_integrated._resolve_data_dir() == configured
    assert execution_pipeline_status._resolve_data_dir() == configured
    assert adaptive_weights._resolve_data_dir() == configured
    assert execution_engine._resolve_data_dir() == configured
    assert execution_orchestrator._resolve_data_dir() == configured


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
    assert execution_pipeline_status._resolve_data_dir() == Path("/data")
    assert adaptive_weights._resolve_data_dir() == Path("/data")
    assert execution_engine._resolve_data_dir() == Path("/data")
    assert execution_orchestrator._resolve_data_dir() == Path("/data")


def test_local_fallback_is_module_relative_when_render_mount_is_absent(monkeypatch):
    monkeypatch.delenv("CENTRAL_DATA_DIR", raising=False)
    monkeypatch.delenv("DATA_DIR", raising=False)
    monkeypatch.setattr(paper_executor_integrated.os.path, "isdir", lambda _path: False)

    assert paper_executor_integrated._resolve_data_dir() == (
        Path(paper_executor_integrated.__file__).resolve().parent / "data"
    )
    assert execution_pipeline_status._resolve_data_dir() == (
        Path(execution_pipeline_status.__file__).resolve().parent / "data"
    )
    assert adaptive_weights._resolve_data_dir() == (
        Path(adaptive_weights.__file__).resolve().parent / "data"
    )
    assert execution_engine._resolve_data_dir() == (
        Path(execution_engine.__file__).resolve().parent / "data"
    )
    assert execution_orchestrator._resolve_data_dir() == (
        Path(execution_orchestrator.__file__).resolve().parent / "data"
    )


def test_paper_executor_persistence_guard_rejects_unmounted_render_data(monkeypatch):
    monkeypatch.setattr(paper_executor_integrated, "DATA_DIR", Path("/data"))
    monkeypatch.setattr(paper_executor_integrated, "_paper_data_mount_verified", lambda: False)
    monkeypatch.setattr(
        paper_executor_integrated.shutil,
        "disk_usage",
        lambda _path: (_ for _ in ()).throw(AssertionError("must not trust ephemeral disk")),
    )

    result = paper_executor_integrated._paper_persistence_guard()

    assert result["allowed"] is False
    assert result["status"] == "PAPER_DATA_MOUNT_NOT_VERIFIED"
    assert result["free_bytes"] is None


def test_paper_health_does_not_trust_state_files_without_render_mount(monkeypatch, tmp_path):
    positions = tmp_path / "paper_integrated_positions.json"
    seen = tmp_path / "paper_integrated_seen.json"
    positions.write_text("[]", encoding="utf-8")
    seen.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(paper_executor_integrated, "DATA_DIR", Path("/data"))
    monkeypatch.setattr(paper_executor_integrated, "PAPER_POSITIONS_FILE", positions)
    monkeypatch.setattr(paper_executor_integrated, "PAPER_SEEN_FILE", seen)
    monkeypatch.setattr(paper_executor_integrated, "PAPER_EXECUTION_ENABLED", True)
    monkeypatch.setattr(paper_executor_integrated, "_paper_data_mount_verified", lambda: False)

    health = paper_executor_integrated.paper_integrated_health()

    assert health["ok"] is False
    assert health["state_files_present"] is True
    assert health["state_files_valid"] is False
    assert health["state_files_status"] == "PAPER_DATA_MOUNT_NOT_VERIFIED"
    assert health["data_mount_verified"] is False
    assert health["open_positions"] is None


def test_render_persistent_mount_check_rejects_missing_mount_on_posix(monkeypatch):
    monkeypatch.setattr(paper_executor_integrated, "DATA_DIR", Path("/data"))
    monkeypatch.setattr(paper_executor_integrated.os.path, "ismount", lambda _path: False)

    assert paper_executor_integrated._paper_data_mount_verified(platform_name="posix") is False


def test_mount_guard_rejects_resolved_path_escape_from_persistent_data(monkeypatch, tmp_path):
    data_root = tmp_path / "persistent"
    outside = tmp_path / "ephemeral"
    data_root.mkdir()
    outside.mkdir()
    target = data_root / "paper" / "nested" / "trade_registry.json"
    original_resolve = paper_state_storage.Path.resolve

    def resolve_with_symlink_escape(path, *args, **kwargs):
        if path == target:
            return outside / "trade_registry.json"
        if path == data_root:
            return data_root
        return original_resolve(path, *args, **kwargs)

    monkeypatch.setattr(paper_state_storage.Path, "resolve", resolve_with_symlink_escape)
    monkeypatch.setattr(paper_state_storage.os.path, "ismount", lambda _path: True)

    verified = paper_state_storage.paper_data_mount_verified(
        target,
        platform_name="posix",
        data_root=data_root,
    )

    assert verified is False


def test_mount_guard_rejects_data_root_symlink(monkeypatch, tmp_path):
    data_root = tmp_path / "persistent-link"
    target = data_root / "paper" / "positions.json"
    original_is_symlink = Path.is_symlink
    monkeypatch.setattr(
        paper_state_storage.Path,
        "is_symlink",
        lambda path: True if path == data_root else original_is_symlink(path),
    )
    monkeypatch.setattr(paper_state_storage.os.path, "ismount", lambda _path: True)

    verified = paper_state_storage.paper_data_mount_verified(
        target,
        platform_name="posix",
        data_root=data_root,
    )

    assert verified is False


def test_mount_guard_rejects_nested_mount_on_different_device(monkeypatch, tmp_path):
    data_root = tmp_path / "persistent"
    nested_mount = data_root / "paper"
    nested_mount.mkdir(parents=True)
    target = nested_mount / "positions.json"
    original_lstat = Path.lstat
    root_device = data_root.stat().st_dev

    def lstat_with_nested_device(path):
        if path == nested_mount:
            return SimpleNamespace(st_mode=stat.S_IFDIR | 0o755, st_dev=root_device + 1)
        return original_lstat(path)

    monkeypatch.setattr(paper_state_storage.Path, "lstat", lstat_with_nested_device)
    monkeypatch.setattr(paper_state_storage.os.path, "ismount", lambda _path: True)

    verified = paper_state_storage.paper_data_mount_verified(
        target,
        platform_name="posix",
        data_root=data_root,
    )

    assert verified is False


def test_import_directory_initializer_does_not_create_unmounted_data_path(monkeypatch, tmp_path):
    target = tmp_path / "would-be-ephemeral-data"
    monkeypatch.setattr(paper_executor_integrated, "DATA_DIR", target)
    monkeypatch.setattr(paper_executor_integrated, "_paper_data_mount_verified", lambda: False)
    monkeypatch.setattr(paper_executor_integrated, "ensure_paper_data_dir", lambda _path: False)

    assert paper_executor_integrated._ensure_paper_data_dir() is False
    assert not target.exists()


def test_shared_directory_initializer_does_not_create_when_mount_missing(monkeypatch, tmp_path):
    target = tmp_path / "would-be-ephemeral-data"
    monkeypatch.setattr(
        paper_state_storage,
        "paper_data_mount_verified",
        lambda _path, **_kwargs: False,
    )

    assert paper_state_storage.ensure_paper_data_dir(target) is False
    assert not target.exists()


def test_blocked_or_invalid_paper_request_does_not_create_ephemeral_log(monkeypatch, tmp_path):
    log_path = tmp_path / "paper_integrated_executor_log.jsonl"
    monkeypatch.setattr(paper_executor_integrated, "DATA_DIR", Path("/data"))
    monkeypatch.setattr(paper_executor_integrated, "PAPER_LOG_FILE", log_path)
    monkeypatch.setattr(paper_executor_integrated, "_paper_data_mount_verified", lambda: False)

    monkeypatch.setattr(paper_executor_integrated, "PAPER_EXECUTION_ENABLED", False)
    blocked = paper_executor_integrated.execute_paper_from_engine({})
    assert blocked["payload"]["status"] == "PAPER_BLOCKED"
    assert not log_path.exists()

    monkeypatch.setattr(paper_executor_integrated, "PAPER_EXECUTION_ENABLED", True)
    invalid = paper_executor_integrated.execute_paper_from_engine({})
    assert invalid["payload"]["status"] == "PAPER_INVALID_PLAN"
    assert not log_path.exists()


def test_shared_paper_state_io_fails_closed_when_mount_is_unverified(monkeypatch, tmp_path):
    positions = tmp_path / "paper_integrated_positions.json"
    original = '[{"status":"OPEN"}]'
    positions.write_text(original, encoding="utf-8")
    monkeypatch.setattr(
        paper_state_storage,
        "paper_data_mount_verified",
        lambda _path, **_kwargs: False,
    )

    state, status = paper_state_storage.read_paper_positions_state(positions)
    written = paper_state_storage.write_json_atomically(positions, [])

    assert state is None
    assert status == "PAPER_DATA_MOUNT_NOT_VERIFIED"
    assert written is False
    assert positions.read_text(encoding="utf-8") == original


def test_lifecycle_and_outcome_fail_closed_without_mount(monkeypatch, tmp_path):
    positions = tmp_path / "paper_integrated_positions.json"
    original = json.dumps([{
        "trade_id": "paper-test-trade",
        "idempotency_key": "paper-test-idem",
        "status": "OPEN",
        "entry": 100.0,
        "sl_initial": 95.0,
        "sl_current": 95.0,
    }])
    positions.write_text(original, encoding="utf-8")
    monkeypatch.setattr(paper_lifecycle, "DATA_DIR", Path("/data"))
    monkeypatch.setattr(paper_lifecycle, "PAPER_POSITIONS_FILE", positions)
    monkeypatch.setattr(paper_lifecycle, "PAPER_LIFECYCLE_ENABLED", True)
    monkeypatch.setattr(outcome_evaluator, "DATA_DIR", Path("/data"))
    monkeypatch.setattr(outcome_evaluator, "PAPER_POSITIONS_FILE", positions)
    monkeypatch.setattr(outcome_evaluator, "OUTCOME_EVALUATOR_ENABLED", True)
    monkeypatch.setattr(
        paper_state_storage,
        "paper_data_mount_verified",
        lambda _path, **_kwargs: False,
    )
    monkeypatch.setattr(paper_lifecycle, "paper_data_mount_verified", lambda *_a, **_k: False)
    monkeypatch.setattr(outcome_evaluator, "paper_data_mount_verified", lambda *_a, **_k: False)

    lifecycle_health = paper_lifecycle.paper_lifecycle_health()
    outcome_health = outcome_evaluator.outcome_evaluator_health()
    lifecycle_update = paper_lifecycle.update_paper_position_price(
        trade_id="paper-test-trade", price=101.0
    )
    outcome_update = outcome_evaluator.evaluate_closed_paper_trades()
    outcome_stats = outcome_evaluator.get_outcome_stats()

    assert lifecycle_health["ok"] is False
    assert lifecycle_health["state_files_status"] == "PAPER_DATA_MOUNT_NOT_VERIFIED"
    assert outcome_health["ok"] is False
    assert outcome_health["state_files_status"] == "PAPER_DATA_MOUNT_NOT_VERIFIED"
    assert lifecycle_update["error"] == "PAPER_DATA_MOUNT_NOT_VERIFIED"
    assert outcome_update["status"] == "PAPER_DATA_MOUNT_NOT_VERIFIED"
    assert outcome_stats["status"] == "PAPER_DATA_MOUNT_NOT_VERIFIED"
    assert positions.read_text(encoding="utf-8") == original


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


def test_outcome_evaluation_does_not_recreate_positions_if_ledger_disappears_after_check(
    monkeypatch, tmp_path
):
    positions = tmp_path / "paper_integrated_positions.json"
    positions.write_text("[]", encoding="utf-8")
    stats = tmp_path / "outcome_stats.json"
    log = tmp_path / "outcome.jsonl"
    monkeypatch.setattr(outcome_evaluator, "PAPER_POSITIONS_FILE", positions)
    monkeypatch.setattr(outcome_evaluator, "OUTCOME_STATS_FILE", stats)
    monkeypatch.setattr(outcome_evaluator, "OUTCOME_LOG_FILE", log)
    monkeypatch.setattr(outcome_evaluator, "OUTCOME_EVALUATOR_ENABLED", True)
    original_read = outcome_evaluator._read_state_json

    def remove_required_ledger_before_open(path, default, *, required=False):
        if Path(path) == positions and required:
            positions.unlink(missing_ok=True)
        return original_read(path, default, required=required)

    monkeypatch.setattr(
        outcome_evaluator, "_read_state_json", remove_required_ledger_before_open
    )

    result = outcome_evaluator.evaluate_closed_paper_trades()

    assert result["ok"] is False
    assert result["status"] == "OUTCOME_STATE_INVALID"
    assert not positions.exists()
    assert not stats.exists()
    assert not log.exists()


def test_execution_engine_logs_delegate_to_guarded_storage(monkeypatch, tmp_path):
    engine_log = tmp_path / "execution_engine_log.jsonl"
    audit_log = tmp_path / "execution_audit_log.jsonl"
    appended = []
    monkeypatch.setattr(execution_engine, "EXECUTION_ENGINE_LOG_FILE", engine_log)
    monkeypatch.setattr(execution_engine, "EXECUTION_AUDIT_LOG_FILE", audit_log)
    monkeypatch.setattr(
        execution_engine,
        "append_paper_text",
        lambda path, content, **kwargs: appended.append((path, content, kwargs)),
    )

    execution_engine._append_jsonl(engine_log, {"event": "TEST_ONLY"})

    assert appended == [
        (engine_log, '{"event": "TEST_ONLY"}\n', {"encoding": "utf-8"})
    ]

    monkeypatch.setattr(execution_engine, "paper_file_exists", lambda _path: True)
    monkeypatch.setattr(
        execution_engine,
        "read_paper_text",
        lambda path, **_kwargs: '{"event": "TEST_ONLY"}\n',
    )
    assert execution_engine.read_execution_engine_log()["items"] == [
        {"event": "TEST_ONLY"}
    ]
    assert execution_engine.read_execution_audit_log()["items"] == [
        {"event": "TEST_ONLY"}
    ]


def test_execution_engine_log_read_errors_fail_closed_for_duplicate_check(
    monkeypatch,
):
    def unavailable(_path):
        raise OSError("synthetic storage failure")

    monkeypatch.setattr(execution_engine, "paper_file_exists", unavailable)
    result = execution_engine._recent_duplicate_execution(
        symbol="BTCUSDT", side="LONG", bot="FALCON"
    )
    assert result["ok"] is False
    assert result["status"] == "EXECUTION_LOGS_READ_FAILED"
    assert result["duplicate"] is False


def test_execution_engine_malformed_log_fails_closed_for_duplicate_check(
    monkeypatch,
):
    private_marker = "synthetic-malformed-log-value"
    monkeypatch.setattr(execution_engine, "paper_file_exists", lambda _path: True)
    monkeypatch.setattr(
        execution_engine,
        "read_paper_text",
        lambda _path, **_kwargs: private_marker,
    )

    result = execution_engine._recent_duplicate_execution(
        symbol="BTCUSDT", side="LONG", bot="FALCON"
    )

    assert result["ok"] is False
    assert result["status"] == "EXECUTION_LOGS_INVALID"
    assert result["duplicate"] is False
    assert private_marker not in repr(result)


def test_confirmation_guard_blocks_when_duplicate_log_read_is_unavailable(
    monkeypatch,
):
    monkeypatch.setattr(
        execution_engine,
        "_recent_duplicate_execution",
        lambda **_kwargs: {"ok": False, "status": "EXECUTION_LOGS_READ_FAILED"},
    )
    result = execution_engine.execution_confirmation_guard(
        payload={},
        mode="LIVE",
        dry_run=False,
        real_guard={"ok": True},
        execution_auth_token="synthetic-test-token",
    )

    assert result["allowed"] is False
    assert "verificação de duplicidade indisponível; execução bloqueada" in result[
        "reasons"
    ]
