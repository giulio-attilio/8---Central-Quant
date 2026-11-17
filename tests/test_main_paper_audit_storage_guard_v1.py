import ast
from pathlib import Path


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
