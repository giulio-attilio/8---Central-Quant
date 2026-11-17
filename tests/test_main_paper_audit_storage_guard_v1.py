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
    assert "_paper_data_mount_verified" in _called_names(verifier)
    assert "_write_guarded_paper_json" in _called_names(json_writer)
    assert "_append_guarded_paper_text" in _called_names(event_writer)

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
