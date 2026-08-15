from __future__ import annotations

import ast
import builtins
import copy
import json
import socket
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
MAIN_FILE = ROOT / "main.py"
MAIN_TREE = ast.parse(MAIN_FILE.read_text(encoding="utf-8"))
MODULE_NAME = "trade_evidence_identity_offset_shadow_compare_v1"
ROUTE = "/tradeevidenceindex/shadow/status"
SOURCES = ("history_manager", "timeline")


@pytest.fixture(autouse=True)
def _block_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("network access attempted during shadow telemetry HTTP test")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)


def _route_node():
    return next(
        copy.deepcopy(item)
        for item in MAIN_TREE.body
        if isinstance(item, ast.FunctionDef)
        and item.name == "trade_evidence_index_shadow_status_v1_route"
    )


def _compile_route():
    node = _route_node()
    node.decorator_list = []
    tree = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(tree)
    namespace = {}
    exec(compile(tree, "<isolated-shadow-telemetry-route>", "exec"), namespace)
    return namespace["trade_evidence_index_shadow_status_v1_route"]


def _empty_source(**overrides):
    source = {
        "shadow_requests": 0,
        "shadow_eligible": 0,
        "shadow_matches": 0,
        "shadow_mismatches": 0,
        "shadow_not_comparable": 0,
        "shadow_index_unavailable": 0,
        "shadow_last_status": "SHADOW_DISABLED",
        "shadow_last_index_status": "SHADOW_DISABLED",
        "shadow_last_at": None,
        "shadow_last_trade_id_masked": None,
        "shadow_last_source": None,
        "shadow_last_mismatch_category": None,
        "shadow_last_legacy_count": 0,
        "shadow_last_index_count": 0,
        "shadow_last_index_lookup_ms": 0.0,
        "shadow_last_legacy_duration_ms": 0.0,
        "shadow_last_duration_ms": 0.0,
        "shadow_last_duration_overhead_percent": None,
        "shadow_last_legacy_bytes_scanned": 0,
        "shadow_last_factual_journal_bytes": 0,
        "shadow_last_tail_journal_bytes": 0,
        "shadow_last_journal_bytes_read": 0,
        "shadow_total_index_journal_bytes_read": 0,
    }
    source.update(overrides)
    return source


def _snapshot(**source_overrides):
    return {
        "version": "test-version",
        "shadow_enabled": True,
        "shadow_compare_enabled": True,
        "sources": {
            name: _empty_source(shadow_last_source=name, **source_overrides)
            for name in SOURCES
        },
    }


def _install_snapshot(monkeypatch, snapshot):
    calls = []

    def getter():
        calls.append(True)
        return copy.deepcopy(snapshot)

    monkeypatch.setitem(
        sys.modules,
        MODULE_NAME,
        SimpleNamespace(get_shadow_telemetry_snapshot=getter),
    )
    return calls


def test_endpoint_is_registered_as_get_only():
    decorators = [ast.unparse(item) for item in _route_node().decorator_list]
    assert decorators == ["app.route('/tradeevidenceindex/shadow/status', methods=['GET'])"]


def test_initial_empty_process_snapshot_is_exposed_without_resetting(monkeypatch):
    import trade_evidence_identity_offset_shadow_compare_v1 as shadow_v1

    shadow_v1.reset_shadow_telemetry()
    before = shadow_v1.get_shadow_telemetry_snapshot()
    monkeypatch.setitem(sys.modules, MODULE_NAME, shadow_v1)

    payload, status = _compile_route()()

    assert status == 200
    assert payload == {
        "ok": True,
        "module": MODULE_NAME,
        "version": before["version"],
        "shadow_enabled": False,
        "shadow_compare_enabled": False,
        "sources": before["sources"],
    }
    assert shadow_v1.get_shadow_telemetry_snapshot() == before


@pytest.mark.parametrize(
    ("last_status", "counter"),
    (
        ("MATCH", "shadow_matches"),
        ("NOT_COMPARABLE", "shadow_not_comparable"),
        ("MISMATCH", "shadow_mismatches"),
        ("INDEX_UNAVAILABLE", "shadow_index_unavailable"),
    ),
)
def test_status_and_corresponding_counter_are_reflected(
    monkeypatch,
    last_status,
    counter,
):
    snapshot = _snapshot(
        shadow_requests=9,
        shadow_last_status=last_status,
        **{counter: 4},
    )
    calls = _install_snapshot(monkeypatch, snapshot)

    payload, status = _compile_route()()

    assert status == 200
    assert calls == [True]
    for source_name in SOURCES:
        assert payload["sources"][source_name]["shadow_last_status"] == last_status
        assert payload["sources"][source_name][counter] == 4
        assert payload["sources"][source_name]["shadow_requests"] == 9


def test_read_preserves_all_counters_and_returns_a_defensive_projection(monkeypatch):
    snapshot = _snapshot(
        shadow_requests=17,
        shadow_eligible=13,
        shadow_matches=11,
        shadow_mismatches=2,
        shadow_not_comparable=3,
        shadow_index_unavailable=1,
        shadow_total_index_journal_bytes_read=9876,
    )
    original = copy.deepcopy(snapshot)
    _install_snapshot(monkeypatch, snapshot)
    route = _compile_route()

    first, first_status = route()
    first["sources"]["history_manager"]["shadow_requests"] = -1
    second, second_status = route()

    assert first_status == second_status == 200
    assert second["sources"]["history_manager"]["shadow_requests"] == 17
    assert second["sources"]["timeline"]["shadow_total_index_journal_bytes_read"] == 9876
    assert snapshot == original


def test_security_projection_keeps_only_masked_trade_id_and_drops_sensitive_fields(
    monkeypatch,
):
    secret = "SECRET_TOKEN_SHOULD_NOT_LEAK"
    raw_trade_id = "RAW-TRADE-ID-SHOULD-NOT-LEAK"
    filesystem_path = "C:/private/history_events.jsonl"
    snapshot = _snapshot(shadow_last_trade_id_masked="a1b2c3d4e5f6")
    snapshot.update({"secret": secret, "token": secret, "path": filesystem_path})
    for source in snapshot["sources"].values():
        source.update({
            "trade_id": raw_trade_id,
            "journal_path": filesystem_path,
            "event_payload": {"token": secret},
            "rows": [{"trade_id": raw_trade_id}],
        })
    monkeypatch.setenv("TRADE_EVIDENCE_TEST_SECRET", secret)
    _install_snapshot(monkeypatch, snapshot)

    payload, status = _compile_route()()
    encoded = json.dumps(payload, sort_keys=True)

    assert status == 200
    assert secret not in encoded
    assert raw_trade_id not in encoded
    assert filesystem_path not in encoded
    assert "TRADE_EVIDENCE_TEST_SECRET" not in encoded
    assert payload["sources"]["history_manager"]["shadow_last_trade_id_masked"] == "a1b2c3d4e5f6"


def test_non_hash_trade_identifier_is_removed_by_route_sanitizer(monkeypatch):
    _install_snapshot(
        monkeypatch,
        _snapshot(shadow_last_trade_id_masked="raw-trade-id"),
    )

    payload, status = _compile_route()()

    assert status == 200
    assert all(
        source["shadow_last_trade_id_masked"] is None
        for source in payload["sources"].values()
    )


def test_import_failure_is_isolated_and_sanitized(monkeypatch):
    real_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == MODULE_NAME:
            raise ImportError("C:/private/path token=secret")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    payload, status = _compile_route()()

    assert status == 503
    assert payload == {
        "ok": False,
        "module": MODULE_NAME,
        "status": "UNAVAILABLE",
        "error_type": "ImportError",
    }
    assert "private" not in json.dumps(payload).lower()
    assert "secret" not in json.dumps(payload).lower()


def test_snapshot_failure_is_isolated_without_public_stack_or_message(monkeypatch):
    def fail():
        raise RuntimeError("C:/private/journal.jsonl secret=abc")

    monkeypatch.setitem(
        sys.modules,
        MODULE_NAME,
        SimpleNamespace(get_shadow_telemetry_snapshot=fail),
    )

    payload, status = _compile_route()()

    assert status == 503
    assert payload["status"] == "UNAVAILABLE"
    assert payload["error_type"] == "RuntimeError"
    assert set(payload) == {"ok", "module", "status", "error_type"}


def test_route_does_not_observe_read_sqlite_journals_write_or_change_counters(
    monkeypatch,
    tmp_path,
):
    import trade_evidence_identity_offset_shadow_compare_v1 as shadow_v1

    shadow_v1.reset_shadow_telemetry()
    before = shadow_v1.get_shadow_telemetry_snapshot()
    monkeypatch.setitem(sys.modules, MODULE_NAME, shadow_v1)

    def forbidden(*args, **kwargs):
        raise AssertionError("route attempted an out-of-scope side effect")

    monkeypatch.setattr(shadow_v1, "observe_evidence_bundle", forbidden)
    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(Path, "open", forbidden)
    monkeypatch.setattr(sqlite3, "connect", forbidden)
    files_before = list(tmp_path.iterdir())

    payload, status = _compile_route()()

    assert status == 200 and payload["ok"] is True
    assert list(tmp_path.iterdir()) == files_before == []
    assert shadow_v1.get_shadow_telemetry_snapshot() == before


def test_route_source_contains_only_snapshot_read_and_no_mutating_integrations():
    node = _route_node()
    source = ast.unparse(node)
    assert "get_shadow_telemetry_snapshot()" in source
    called_names = set()
    for item in ast.walk(node):
        if not isinstance(item, ast.Call):
            continue
        if isinstance(item.func, ast.Name):
            called_names.add(item.func.id)
        elif isinstance(item.func, ast.Attribute):
            called_names.add(item.func.attr)
    for forbidden in (
        "reset_shadow_telemetry",
        "observe_evidence_bundle",
        "compare_source_semantics",
        "connect",
        "open",
        "write_text",
        "write_bytes",
        "mkdir",
        "replace",
        "unlink",
        "remove",
        "rmtree",
        "request",
        "urlopen",
        "start",
    ):
        assert forbidden not in called_names
    for forbidden_text in (
        "sqlite3.",
        "Path(",
        "write",
        "registry",
        "broker",
        "socket.",
        "Thread(",
    ):
        assert forbidden_text not in source
