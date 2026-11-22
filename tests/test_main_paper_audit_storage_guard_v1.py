import ast
from pathlib import Path

import pytest


def _called_names(node):
    names = set()
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        func = child.func
        if isinstance(func, ast.Name):
            names.add(func.id)
        elif isinstance(func, ast.Attribute):
            names.add(func.attr)
    return names


def test_predator_paper_audit_writers_use_guarded_storage_only():
    source = (Path(__file__).resolve().parents[1] / "main.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    functions = {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    verifier = functions["_verify_central_paper_audit_path"]
    json_writer = functions["_write_central_paper_audit_json"]
    event_writer = functions["_append_central_paper_audit_event"]
    json_reader = functions["_pppa_v1_read_json_records"]
    assert "_paper_data_mount_verified" in _called_names(verifier)
    assert "_write_guarded_paper_json" in _called_names(json_writer)
    assert "_append_guarded_paper_text" in _called_names(event_writer)
    assert "_paper_file_exists" in _called_names(json_reader)
    assert "_read_guarded_paper_text" in _called_names(json_reader)
    assert not {"exists", "read_text"}.intersection(_called_names(json_reader))

    callers = (
        "predator_pnl_paper_audit_v1_status",
        "predator_paper_lifecycle_audit_v1_status",
        "predator_paper_registry_sync_fix_v1_status",
        "predator_registry_orphan_open_fix_v1_status",
    )
    direct_io = {"mkdir", "write_text", "write_bytes", "open", "replace"}
    for name in callers:
        called = _called_names(functions[name])
        assert "_write_central_paper_audit_json" in called
        assert "_append_central_paper_audit_event" in called
        assert not direct_io.intersection(called), name


def test_trade_close_outcome_state_io_uses_guarded_storage_only():
    source = (Path(__file__).resolve().parents[1] / "main.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    functions = {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    guarded_readers = (
        "_rp_v13_closed_pairs_from_outcome_files_with_status",
        "trade_close_outcome_v1_health_route",
        "trade_close_outcome_v1_log_route",
    )
    for name in guarded_readers:
        called = _called_names(functions[name])
        assert "_paper_file_exists" in called, name
        assert "_read_guarded_paper_text" in called, name
        assert not {"exists", "read_text"}.intersection(called), name

    json_writer = _called_names(functions["_tco_v1_atomic_write_json"])
    assert "_write_central_paper_audit_json" in json_writer
    assert not {"mkdir", "write_text", "write_bytes", "open", "replace"}.intersection(
        json_writer
    )

    event_writer = _called_names(functions["_tco_v1_append_event"])
    assert "_append_central_paper_audit_event" in event_writer
    assert not {"mkdir", "open"}.intersection(event_writer)

    mode_json_writer = _called_names(functions["_rms_v1_atomic_write_json"])
    assert "_write_central_paper_audit_json" in mode_json_writer
    assert not {"mkdir", "write_text", "write_bytes", "open", "replace"}.intersection(
        mode_json_writer
    )

    mode_event_writer = _called_names(functions["_rms_v1_append_event"])
    assert "_append_central_paper_audit_event" in mode_event_writer
    assert not {"mkdir", "open"}.intersection(mode_event_writer)


def test_outcome_evaluator_and_adaptive_weight_state_use_guarded_storage_only():
    source = (Path(__file__).resolve().parents[1] / "main.py").read_text(
        encoding="utf-8"
    )
    assert "CENTRAL_DATA_DIR.mkdir" not in source
    assert "_ensure_guarded_paper_data_dir(CENTRAL_DATA_DIR)" in source
    tree = ast.parse(source)
    functions = {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    append_writer = _called_names(functions["_oe_append_jsonl"])
    assert "_append_central_paper_audit_event" in append_writer
    assert not {"mkdir", "open"}.intersection(append_writer)

    outcome_reader = _called_names(functions["_oe_read_records"])
    assert "_paper_file_exists" in outcome_reader
    assert "_read_guarded_paper_tail_lines" in outcome_reader
    assert not {"exists", "open", "read_text"}.intersection(outcome_reader)

    evaluation_reader = _called_names(functions["_awe_v2_read_evaluations"])
    assert "_oe_read_records" in evaluation_reader
    assert not {"exists", "open", "read_text"}.intersection(evaluation_reader)

    adaptive_reader = _called_names(functions["_awe_v2_load_state"])
    assert "_paper_file_exists" in adaptive_reader
    assert "_read_guarded_paper_text" in adaptive_reader
    assert not {"exists", "open", "read_text"}.intersection(adaptive_reader)

    adaptive_writer = _called_names(functions["_awe_v2_save_state"])
    assert "_write_central_paper_audit_json" in adaptive_writer
    assert not {"mkdir", "open", "write_text", "write_bytes"}.intersection(
        adaptive_writer
    )

    adaptive_v1_reader = _called_names(functions["_awe_load_state"])
    assert "_paper_file_exists" in adaptive_v1_reader
    assert "_read_guarded_paper_text" in adaptive_v1_reader
    assert not {"exists", "open", "read_text"}.intersection(adaptive_v1_reader)

    adaptive_v1_writer = _called_names(functions["_awe_save_state"])
    assert "_write_central_paper_audit_json" in adaptive_v1_writer
    assert not {"mkdir", "open", "write_text", "write_bytes"}.intersection(
        adaptive_v1_writer
    )

    adaptive_v1_outcome_reader = _called_names(
        functions["_awe_extract_outcome_records"]
    )
    assert "_paper_file_exists" in adaptive_v1_outcome_reader
    assert "_read_guarded_paper_tail_lines" in adaptive_v1_outcome_reader
    assert "_read_physical_tail_lines_v1" not in adaptive_v1_outcome_reader
    assert not {"exists", "open", "read_text"}.intersection(
        adaptive_v1_outcome_reader
    )

    learning_writer = _called_names(functions["_le_append_jsonl"])
    assert "_append_central_paper_audit_event" in learning_writer
    assert not {"mkdir", "open"}.intersection(learning_writer)

    learning_reader = _called_names(functions["_le_read_records"])
    assert "_paper_file_exists" in learning_reader
    assert "_read_guarded_paper_tail_lines" in learning_reader
    assert not {"exists", "open", "read_text"}.intersection(learning_reader)

    for name in ("_append_jsonl", "_read_jsonl_tail", "_read_json_file", "_write_json_file", "_read_jsonl_tail_v3"):
        assert "_is_central_data_path" in _called_names(functions[name]), name
    assert "_append_central_paper_audit_event" in _called_names(
        functions["_append_jsonl"]
    )
    assert "_read_guarded_paper_tail_lines" in _called_names(
        functions["_read_jsonl_tail"]
    )
    assert "_read_guarded_paper_tail_lines" in _called_names(
        functions["_read_jsonl_tail_v3"]
    )
    assert "_read_guarded_paper_text" in _called_names(functions["_read_json_file"])
    assert "_write_central_paper_audit_json" in _called_names(
        functions["_write_json_file"]
    )

    runtime_append = _called_names(functions["_runtime_stability_v1_append_event"])
    assert "_append_central_paper_audit_event" in runtime_append
    assert not {"mkdir", "open"}.intersection(runtime_append)
    runtime_state_write = _called_names(
        functions["_runtime_stability_v1_write_state"]
    )
    assert "_write_central_paper_audit_json" in runtime_state_write
    assert not {"mkdir", "write_text", "open"}.intersection(runtime_state_write)
    runtime_reader = _called_names(functions["_runtime_stability_v1_read_events"])
    assert "_paper_file_exists" in runtime_reader
    assert "_read_guarded_paper_tail_lines" in runtime_reader
    assert not {"exists", "read_text", "open"}.intersection(runtime_reader)

    strategy_writer = _called_names(functions["_see_append_jsonl"])
    assert "_append_central_paper_audit_event" in strategy_writer
    assert not {"mkdir", "open"}.intersection(strategy_writer)

    lifecycle_writer = _called_names(functions["_tlm_append_jsonl"])
    assert "_append_central_paper_audit_event" in lifecycle_writer
    assert not {"mkdir", "open"}.intersection(lifecycle_writer)
    lifecycle_reader = _called_names(functions["_tlm_read_records"])
    assert "_paper_file_exists" in lifecycle_reader
    assert "_read_guarded_paper_tail_lines" in lifecycle_reader
    assert not {"exists", "open", "read_text"}.intersection(lifecycle_reader)

    route_tree = functions["execution_console_route"]
    nested_functions = {
        node.name: node
        for node in ast.walk(route_tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    console_reader = _called_names(nested_functions["_console_read_store"])
    assert "_paper_file_exists" in console_reader
    assert "_read_guarded_paper_text" in console_reader
    assert not {"exists", "open", "read_text"}.intersection(console_reader)
    console_writer = _called_names(nested_functions["_console_write_store"])
    assert "_write_central_paper_audit_json" in console_writer
    assert not {"mkdir", "open", "write_text"}.intersection(console_writer)

    disaster_reader = _called_names(functions["_dsf_v1_read_json"])
    assert "_paper_file_exists" in disaster_reader
    assert "_read_guarded_paper_text" in disaster_reader
    assert not {"exists", "open", "read_text"}.intersection(disaster_reader)
    disaster_writer = _called_names(functions["_dsf_v1_atomic_write_json"])
    assert "_write_central_paper_audit_json" in disaster_writer
    assert not {"mkdir", "open", "replace"}.intersection(disaster_writer)
    disaster_event_writer = _called_names(functions["_dsf_v1_append_event"])
    assert "_append_central_paper_audit_event" in disaster_event_writer
    assert not {"mkdir", "open"}.intersection(disaster_event_writer)

    registry_snapshot_reader = _called_names(
        functions["_rp_v1_read_latest_snapshot"]
    )
    assert "_paper_file_exists" in registry_snapshot_reader
    assert "_read_guarded_paper_text" in registry_snapshot_reader
    assert not {"exists", "read_text", "open"}.intersection(
        registry_snapshot_reader
    )
    registry_snapshot_writer = _called_names(functions["_rp_v1_atomic_write_json"])
    assert "_write_central_paper_audit_json" in registry_snapshot_writer
    assert not {"mkdir", "write_text", "replace"}.intersection(
        registry_snapshot_writer
    )
    registry_event_writer = _called_names(functions["_rp_v1_append_event"])
    assert "_append_central_paper_audit_event" in registry_event_writer
    assert not {"mkdir", "open"}.intersection(registry_event_writer)


def test_runtime_audit_sidecars_use_guarded_storage_only():
    source = (Path(__file__).resolve().parents[1] / "main.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    functions = {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    direct_io = {"exists", "read_text", "write_text", "write_bytes", "mkdir", "open", "replace"}
    groups = {
        "auto_real_execution_bridge": (
            ("_arb_v1_load_state", "_paper_file_exists", "_read_guarded_paper_text"),
            ("_arb_v1_save_state", "_write_central_paper_audit_json", None),
            ("_arb_v1_append_event", "_append_central_paper_audit_event", None),
        ),
        "real_position_watchdog": (
            ("_rpw_v1_load_json", "_paper_file_exists", "_read_guarded_paper_text"),
            ("_rpw_v1_write_json", "_write_central_paper_audit_json", None),
            ("_rpw_v1_append_event", "_append_central_paper_audit_event", None),
            ("_rpw_v1_read_events", "_read_guarded_paper_tail_lines", "_paper_file_exists"),
        ),
        "pilot_cooldown": (
            ("_pcd_v1_load_json", "_paper_file_exists", "_read_guarded_paper_text"),
            ("_pcd_v1_write_json", "_write_central_paper_audit_json", None),
            ("_pcd_v1_append_event", "_append_central_paper_audit_event", None),
            ("_pcd_v1_read_events", "_read_guarded_paper_tail_lines", "_paper_file_exists"),
        ),
        "real_close_auto_evaluator": (
            ("_rcae_v1_load_json", "_paper_file_exists", "_read_guarded_paper_text"),
            ("_rcae_v1_write_json", "_write_central_paper_audit_json", None),
            ("_rcae_v1_append_event", "_append_central_paper_audit_event", None),
            ("_rcae_v1_read_events", "_read_guarded_paper_tail_lines", "_paper_file_exists"),
        ),
        "real_pilot_dashboard": (
            ("_rpd_v1_load_json", "_paper_file_exists", "_read_guarded_paper_text"),
            ("_rpd_v1_write_json", "_write_central_paper_audit_json", None),
            ("_rpd_v1_append_event", "_append_central_paper_audit_event", None),
            ("_rpd_v1_read_events", "_read_guarded_paper_tail_lines", "_paper_file_exists"),
        ),
    }
    for group_name, checks in groups.items():
        for function_name, required_call, also_required in checks:
            called = _called_names(functions[function_name])
            assert required_call in called, (group_name, function_name)
            if also_required:
                assert also_required in called, (group_name, function_name)
            assert not direct_io.intersection(called), (group_name, function_name)


def test_remaining_central_audit_sidecars_use_guarded_storage_only():
    source = (Path(__file__).resolve().parents[1] / "main.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    functions = {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    direct_io = {"mkdir", "open", "write_text", "write_bytes"}
    checks = {
        "_trendpro_daily_summary_v1_append_event": "_append_central_paper_audit_event",
        "trendpro_daily_summary_v1_load_state": "_read_guarded_paper_text",
        "trendpro_daily_summary_v1_save_state": "_write_central_paper_audit_json",
        "_retg_v1_append_event": "_append_central_paper_audit_event",
        "_eaa_v1_write_json": "_write_central_paper_audit_json",
        "_eaa_v1_append": "_append_central_paper_audit_event",
        "_eaa_v1_read_jsonl": "_read_guarded_paper_tail_lines",
        "_bdsp_v1_write_json_atomic": "_write_central_paper_audit_json",
        "_bdsp_v1_append_event": "_append_central_paper_audit_event",
        "_frpp_v1_write_json_atomic": "_write_central_paper_audit_json",
        "_frpp_v1_append_event": "_append_central_paper_audit_event",
        "_frpp_v1_read_jsonl": "_read_guarded_paper_tail_lines",
        "_frpp_v1_load_json": "_read_guarded_paper_text",
        "_fleag_v1_load_state": "_read_guarded_paper_text",
        "_fleag_v1_save_state": "_write_central_paper_audit_json",
        "_fleag_v1_append_event": "_append_central_paper_audit_event",
        "_fleag_v1_read_events": "_read_guarded_paper_tail_lines",
        "_flad_v1_write_snapshot": "_write_central_paper_audit_json",
        "_flad_v1_append_event": "_append_central_paper_audit_event",
        "_fcor_v1_atomic_write": "_write_central_paper_audit_json",
        "_fcor_v1_append": "_append_central_paper_audit_event",
        "_read_executive_alert_log_rows": "_read_guarded_paper_tail_lines",
        "_fmcd_v1_read_liveorder_detail_snapshot": "_read_guarded_paper_text",
        "_fdsff_v1_read_snapshot_records": "_read_guarded_paper_text",
        "_pacs_v1_atomic_write_json": "_write_central_paper_audit_json",
        "_pacs_v1_write_audit": "_append_central_paper_audit_event",
        "_rcrm_v1_write": "_write_central_paper_audit_json",
        "_rcrm_v1_append": "_append_central_paper_audit_event",
        "_trpsf_v1_atomic_write_json": "_write_central_paper_audit_json",
        "_trpsf_v1_bootstrap_registry": "_append_central_paper_audit_event",
    }
    for name, guarded_call in checks.items():
        called = _called_names(functions[name])
        assert guarded_call in called, name
        assert not direct_io.intersection(called), name

    falcon_file_reader = _called_names(functions["_fleag_v1_read_jsonl_file"])
    assert "_is_central_data_path" in falcon_file_reader
    assert "_read_guarded_paper_tail_lines" in falcon_file_reader
    assert "RENDER" in {
        node.value for node in ast.walk(functions["_fleag_v1_read_jsonl_file"])
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert "_paper_file_exists" in falcon_file_reader

    memory_read_json = _called_names(functions["_md_v1_read_json"])
    assert "_is_central_data_path" in memory_read_json
    assert "_read_guarded_paper_text" in memory_read_json
    memory_audit = _called_names(functions["_md_v1_latest_execution_audit"])
    assert "_is_central_data_path" in memory_audit
    assert "_read_guarded_paper_tail_lines" in memory_audit

    latest_live_audit = _called_names(
        functions["falcon_live_execution_audit_guard_v1_status"]
    )
    assert "_paper_file_exists" in latest_live_audit
    assert "_read_guarded_paper_text" in latest_live_audit

    bridge_tail_reader = _called_names(functions["_arb_v1_read_events_page"])
    assert "_is_central_data_path" in bridge_tail_reader
    assert "_open_guarded_paper_binary" in bridge_tail_reader
    assert "_paper_file_stat" in bridge_tail_reader
    assert "RENDER" in {
        node.value for node in ast.walk(functions["_arb_v1_read_events_page"])
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }

    registry_read = _called_names(functions["_trpsf_v1_read_json"])
    assert "_is_central_data_path" in registry_read
    assert "_paper_file_exists" in registry_read
    assert "_read_guarded_paper_text" in registry_read
    assert "RENDER" in {
        node.value for node in ast.walk(functions["_trpsf_v1_read_json"])
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }

    for name in (
        "_trpsf_v1_falcon_live_entry_storage_readiness",
        "_trpsf_v1_patched_load_registry",
        "_trpsf_v1_patched_save_registry",
        "_trpsf_v1_preview_bootstrap_registry",
        "_trpsf_v1_legacy_candidate_paths",
        "_trpsf_v1_temporary_registry_source",
    ):
        called = _called_names(functions[name])
        if name != "_trpsf_v1_legacy_candidate_paths":
            assert "_paper_file_exists" in called, name
        assert "exists" not in called, name


def test_render_daily_history_uses_persistent_guarded_storage():
    source = (Path(__file__).resolve().parents[1] / "main.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    functions = {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    save_calls = _called_names(functions["save_daily_snapshot"])
    report_calls = _called_names(functions["build_history_report"])
    assert "_is_central_data_path" in save_calls
    assert "_write_central_paper_audit_json" in save_calls
    assert "_is_central_data_path" in report_calls
    assert "_list_guarded_paper_files" in report_calls
    assert "_read_guarded_paper_text" in report_calls
    assert 'DAILY_HISTORY_DIR = CENTRAL_DATA_DIR / "daily_history"' in source
    save_source = ast.get_source_segment(source, functions["save_daily_snapshot"])
    report_source = ast.get_source_segment(source, functions["build_history_report"])
    assert 'os.environ.get("RENDER", "").strip().lower() == "true"' in save_source
    assert 'os.environ.get("RENDER", "").strip().lower() == "true"' in report_source


def test_daily_history_blocks_ephemeral_render_fallback(tmp_path, monkeypatch):
    import main as central_main

    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setattr(central_main, "DAILY_HISTORY_DIR", tmp_path)
    monkeypatch.setattr(central_main, "_is_central_data_path", lambda _path: False)
    monkeypatch.setattr(
        central_main,
        "daily_snapshot_payload",
        lambda: {"date": "2026-11-21"},
    )

    with pytest.raises(OSError, match="DAILY_HISTORY_PERSISTENT_PATH_REQUIRED"):
        central_main.save_daily_snapshot()

    assert central_main.build_history_report() == (
        "Histórico indisponível: armazenamento persistente não verificado."
    )
    assert list(tmp_path.iterdir()) == []


def test_data_status_lock_inventory_uses_guarded_listing():
    source = (Path(__file__).resolve().parents[1] / "main.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    functions = {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    calls = _called_names(functions["_central_runtime_lock_files"])
    assert "_list_guarded_paper_files" in calls
    assert not {"glob", "rglob", "iterdir", "listdir"}.intersection(calls)

    route_calls = _called_names(functions["data_status_route"])
    assert "_central_runtime_lock_files" in route_calls


def test_registry_forensics_and_diagnostics_use_guarded_file_access():
    source = (Path(__file__).resolve().parents[1] / "main.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    functions = {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    requirements = {
        "system_debug_route": ("_paper_file_exists", "_open_guarded_paper_text"),
        "_trg_v1_load_history_events": ("_paper_file_exists",),
        "_trpsf_v1_stop_evidence_scan_file": (
            "_paper_file_exists",
            "_paper_file_stat",
            "_open_guarded_paper_binary",
            "_open_guarded_paper_text",
        ),
        "_trpsf_v1_closed_trade_stop_evidence_v1": (
            "_paper_file_exists",
            "_paper_file_stat",
        ),
    }
    for name, required in requirements.items():
        called = _called_names(functions[name])
        assert set(required).issubset(called), name
