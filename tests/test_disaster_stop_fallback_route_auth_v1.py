from __future__ import annotations

import ast
import socket
from pathlib import Path

from flask import Flask, request as flask_request
import pytest

from disaster_stop_fallback_route_v1 import (
    dispatch_disaster_stop_fallback_route_v1,
    persist_disaster_stop_fallback_result_v1,
)


ROOT = Path(__file__).resolve().parents[1]
MAIN_SOURCE = ROOT / "main.py"


def _deny_network(*_args, **_kwargs):
    raise AssertionError("network access is forbidden in this offline route test")


@pytest.fixture(autouse=True)
def _block_network(monkeypatch):
    monkeypatch.setattr(socket, "create_connection", _deny_network)
    monkeypatch.setattr(socket, "getaddrinfo", _deny_network)
    monkeypatch.setattr(socket.socket, "connect", _deny_network)
    monkeypatch.setattr(socket.socket, "connect_ex", _deny_network)


def _load_route(*, auth_result=None):
    calls = []
    builder = lambda **kwargs: calls.append(kwargs) or {
        "ok": True,
        "status": "TEST_BUILDER_CALLED",
    }
    auth_guard = lambda: auth_result if auth_result is not None else {
        "ok": True,
        "status": "EXECUTION_AUTH_OK",
    }
    return (
        lambda: dispatch_disaster_stop_fallback_route_v1(
            flask_request,
            builder,
            auth_guard,
        ),
        calls,
    )


def _call(route, path, *, method="GET", json=None, headers=None):
    app = Flask(__name__)
    with app.test_request_context(path, method=method, json=json, headers=headers):
        return route()


def test_route_decorators_restrict_fallback_to_get_and_post():
    tree = ast.parse(MAIN_SOURCE.read_text(encoding="utf-8"))
    route = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "disaster_stop_fallback_v1_route"
    )
    route_rules = [
        decorator
        for decorator in route.decorator_list
        if isinstance(decorator, ast.Call)
        and isinstance(decorator.func, ast.Attribute)
        and decorator.func.attr == "route"
    ]
    assert len(route_rules) == 2
    assert all(
        ast.literal_eval(next(kw.value for kw in dec.keywords if kw.arg == "methods"))
        == ["GET", "POST"]
        for dec in route_rules
    )
    assert "dispatch_disaster_stop_fallback_route_v1" in ast.unparse(route)


def test_builder_only_uses_query_commit_and_ack_when_arguments_are_omitted():
    tree = ast.parse(MAIN_SOURCE.read_text(encoding="utf-8"))
    builder = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "build_disaster_stop_fallback_v1"
    )
    source = ast.unparse(builder)
    assert "if commit is None:" in source
    assert "if ack is None:" in source


def test_get_with_commit_query_is_rejected_without_builder_call():
    route, calls = _load_route()
    response, status = _call(
        route,
        "/disasterstopfallback?commit=true&ack=DISASTER_STOP_FALLBACK",
    )
    assert status == 405
    assert response["status"] == "COMMIT_REQUIRES_AUTHENTICATED_POST"
    assert response["commit_attempted"] is False
    assert calls == []


def test_get_preview_ignores_ack_and_never_requests_commit():
    route, calls = _load_route()
    response = _call(
        route,
        "/disasterstopfallback?symbol=BTCUSDT&ack=DISASTER_STOP_FALLBACK",
    )
    assert response["status"] == "TEST_BUILDER_CALLED"
    assert len(calls) == 1
    assert calls[0]["symbol"] == "BTCUSDT"
    assert calls[0]["commit"] is False
    assert calls[0]["ack"] == ""


def test_preview_does_not_persist_state_or_append_event(tmp_path):
    latest = tmp_path / "latest.json"
    events = tmp_path / "events.jsonl"

    def write_json(path, payload):
        Path(path).write_text(str(payload), encoding="utf-8")

    def append_event(event):
        with events.open("a", encoding="utf-8") as stream:
            stream.write(str(event) + "\n")

    persisted = persist_disaster_stop_fallback_result_v1(
        {"status": "DISASTER_STOP_FALLBACK_PREVIEW_READY"},
        commit=False,
        latest_file=latest,
        atomic_write_json=write_json,
        append_event=append_event,
    )

    assert persisted is False
    assert not latest.exists()
    assert not events.exists()


def test_committed_fallback_persists_latest_and_event_in_temp_storage(tmp_path):
    latest = tmp_path / "latest.json"
    events = tmp_path / "events.jsonl"

    def write_json(path, payload):
        Path(path).write_text(str(payload), encoding="utf-8")

    def append_event(event):
        with events.open("a", encoding="utf-8") as stream:
            stream.write(str(event) + "\n")

    payload = {"status": "MANUAL_ATTENTION_REQUIRED_STOP_NOT_CONFIRMED"}
    persisted = persist_disaster_stop_fallback_result_v1(
        payload,
        commit=True,
        latest_file=latest,
        atomic_write_json=write_json,
        append_event=append_event,
    )

    assert persisted is True
    assert latest.read_text(encoding="utf-8") == str(payload)
    assert events.read_text(encoding="utf-8") == (
        "{'event': 'DISASTER_STOP_FALLBACK', 'status': "
        "'MANUAL_ATTENTION_REQUIRED_STOP_NOT_CONFIRMED'}\n"
    )


def test_main_builder_uses_commit_gated_persistence_helper():
    tree = ast.parse(MAIN_SOURCE.read_text(encoding="utf-8"))
    builder = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "build_disaster_stop_fallback_v1"
    )
    calls = {
        node.func.id
        for node in ast.walk(builder)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "persist_disaster_stop_fallback_result_v1" in calls
    assert "_dsf_v1_atomic_write_json" not in calls
    assert "_dsf_v1_append_event" not in calls


def test_post_without_auth_is_rejected_before_builder_call():
    route, calls = _load_route(auth_result={"ok": False, "status": "EXECUTION_AUTH_REQUIRED"})
    response, status = _call(
        route,
        "/disasterstopfallback",
        method="POST",
        json={"commit": True, "ack": "DISASTER_STOP_FALLBACK"},
    )
    assert status == 403
    assert response["status"] == "EXECUTION_AUTH_REQUIRED"
    assert response["commit_attempted"] is False
    assert calls == []


def test_post_rejects_query_parameters_even_with_auth():
    route, calls = _load_route()
    response, status = _call(
        route,
        "/disasterstopfallback?symbol=BTCUSDT",
        method="POST",
        json={"commit": True, "ack": "DISASTER_STOP_FALLBACK"},
    )
    assert status == 400
    assert response["status"] == "POST_QUERY_PARAMETERS_NOT_ALLOWED"
    assert calls == []


def test_post_requires_explicit_commit_and_exact_ack():
    route, calls = _load_route()
    missing_commit, missing_commit_status = _call(
        route,
        "/disasterstopfallback",
        method="POST",
        json={"ack": "DISASTER_STOP_FALLBACK"},
    )
    wrong_ack, wrong_ack_status = _call(
        route,
        "/disasterstopfallback",
        method="POST",
        json={"commit": True, "ack": "AUTO_POST_EXECUTION_STOP_FALLBACK"},
    )
    assert missing_commit_status == 400
    assert missing_commit["status"] == "EXPLICIT_COMMIT_REQUIRED"
    assert wrong_ack_status == 400
    assert wrong_ack["status"] == "ACK_REQUIRED"
    assert calls == []


def test_authenticated_post_passes_only_body_values_to_builder():
    route, calls = _load_route()
    response = _call(
        route,
        "/disasterstopfallback",
        method="POST",
        json={
            "commit": True,
            "ack": "DISASTER_STOP_FALLBACK",
            "symbol": "BTCUSDT",
            "side": "SHORT",
            "sl": 66750.9,
        },
    )
    assert response["status"] == "TEST_BUILDER_CALLED"
    assert len(calls) == 1
    assert calls[0]["commit"] is True
    assert calls[0]["ack"] == "DISASTER_STOP_FALLBACK"
    assert calls[0]["symbol"] == "BTCUSDT"
    assert calls[0]["side"] == "SHORT"
    assert calls[0]["sl"] == 66750.9


def _synthetic_auth_material_present(value):
    if not hasattr(value, "keys"):
        return False
    return any(
        any(marker in str(key or "").lower() for marker in ("token", "authorization", "secret", "password"))
        for key in value.keys()
    )


def _load_real_admin_auth_guard(resolved):
    tree = ast.parse(MAIN_SOURCE.read_text(encoding="utf-8"))
    guard = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_rtlm_v15_admin_auth"
    )

    def resolver(**kwargs):
        assert kwargs == {"allow_env_fallback": False}
        return dict(resolved)

    namespace = {
        "request": flask_request,
        "_rtlm_v15_contains_auth_material": _synthetic_auth_material_present,
        "_ee_auth_resolver_v1_get_from_mapping": lambda mapping, key: mapping.get(key),
        "_ee_auth_resolver_v1_resolve": resolver,
        "app": Flask(__name__),
    }
    module = ast.Module(body=[guard], type_ignores=[])
    exec(compile(module, str(MAIN_SOURCE), "exec"), namespace)
    return namespace["_rtlm_v15_admin_auth"]


def test_route_passes_real_exact_header_guard_to_dispatcher():
    tree = ast.parse(MAIN_SOURCE.read_text(encoding="utf-8"))
    route = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "disaster_stop_fallback_v1_route"
    )
    route_source = ast.unparse(route)
    assert "dispatch_disaster_stop_fallback_route_v1" in route_source
    guard_lookup = [
        node
        for node in ast.walk(route)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "get"
        and isinstance(node.func.value, ast.Call)
        and ast.unparse(node.func.value) == "globals()"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value == "_rtlm_v15_admin_auth"
    ]
    assert len(guard_lookup) == 1


def test_real_admin_guard_accepts_only_a_resolver_verified_exact_header():
    guard = _load_real_admin_auth_guard(
        {
            "ok": True,
            "matched_source": "request.headers.X-Execution-Auth-Token",
        }
    )
    result = _call(
        guard,
        "/disasterstopfallback",
        method="POST",
        headers={"X-Execution-Auth-Token": "synthetic-test-only"},
    )
    assert result == {"ok": True, "status": "EXECUTION_AUTH_OK", "http_status": 200}


@pytest.mark.parametrize(
    ("path", "headers", "resolved", "expected"),
    [
        (
            "/disasterstopfallback",
            {},
            {"ok": True, "matched_source": "request.headers.X-Execution-Auth-Token"},
            "EXECUTION_AUTH_REQUIRED",
        ),
        (
            "/disasterstopfallback",
            {"X-Execution-Auth": "synthetic-test-only"},
            {"ok": True, "matched_source": "request.headers.X-Execution-Auth-Token"},
            "EXECUTION_AUTH_HEADER_REQUIRED",
        ),
        (
            "/disasterstopfallback?token=synthetic-test-only",
            {"X-Execution-Auth-Token": "synthetic-test-only"},
            {"ok": True, "matched_source": "request.headers.X-Execution-Auth-Token"},
            "EXECUTION_AUTH_HEADER_REQUIRED",
        ),
        (
            "/disasterstopfallback",
            {"X-Execution-Auth-Token": "synthetic-test-only"},
            {"ok": True, "matched_source": "request.args.token"},
            "EXECUTION_AUTH_INVALID",
        ),
    ],
)
def test_real_admin_guard_fails_closed_for_invalid_auth_sources(path, headers, resolved, expected):
    guard = _load_real_admin_auth_guard(resolved)
    result = _call(guard, path, method="POST", headers=headers)
    assert result["ok"] is False
    assert result["status"] == expected
    assert result["http_status"] == 403
