from __future__ import annotations

import ast
import base64
import copy
import hmac
import importlib.util
import json
import os
import re
import socket
import sys
import threading
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest
from flask import Flask, request as flask_request


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "main.py"
_TREE = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))


def test_execution_preview_and_paper_update_docs_match_post_only_routes():
    source = SOURCE.read_text(encoding="utf-8")

    assert 'href="/executionverify?bot=' not in source
    assert "POST JSON para <code>/executionverify</code>" in source
    assert 'methods=["POST"]' in source[
        source.index('@app.route("/executionverify", methods=["POST"])'):
        source.index("def execution_engine_verify_route")
    ]
    assert '"update": ["POST /paperlifecycleupdate (symbol, price, close)", "POST /paperupdate"]' in source
    assert "/paperlifecycleupdate?symbol=ETHUSDT" not in source


@pytest.mark.parametrize(
    ("function_name", "expected_routes"),
    [
        (
            "real_execution_telegram_notifier_v1_health_route",
            {
                "/realexecutiontelegram/health": {"GET"},
                "/realexecutiontelegram": {"GET", "POST"},
                "/real/executiontelegram/health": {"GET"},
            },
        ),
        (
            "pilot_cooldown_v1_release_route",
            {
                "/pilotcooldown/release": {"POST"},
                "/pilot/cooldown/release": {"POST"},
            },
        ),
    ],
)
def test_external_notification_and_cooldown_release_routes_use_safe_methods(
    function_name, expected_routes
):
    route = next(
        node
        for node in _TREE.body
        if isinstance(node, ast.FunctionDef) and node.name == function_name
    )
    registered = {}
    for decorator in route.decorator_list:
        if not (
            isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and decorator.func.attr == "route"
            and decorator.args
            and isinstance(decorator.args[0], ast.Constant)
        ):
            continue
        methods = next((kw.value for kw in decorator.keywords if kw.arg == "methods"), None)
        registered[decorator.args[0].value] = {
            item.value for item in methods.elts if isinstance(item, ast.Constant)
        }

    assert registered == expected_routes

    if function_name == "real_execution_telegram_notifier_v1_health_route":
        calls = [
            node.lineno
            for node in ast.walk(route)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "real_execution_telegram_notifier_v1_notify"
        ]
        guards = [
            node.lineno
            for node in ast.walk(route)
            if isinstance(node, ast.Compare)
            and isinstance(node.left, ast.Attribute)
            and node.left.attr == "method"
        ]
        assert calls and guards and min(guards) < min(calls)

        isolated_app = Flask("telegram_get_mutation_regression")
        notifications = []
        namespace = {
            "app": isolated_app,
            "request": flask_request,
            "_retg_v1_config": lambda: {"enabled": True},
            "_retg_v1_bool": lambda value, default=False: (
                str(value).strip().lower() in {"1", "true", "yes", "on", "sim"}
                if value is not None
                else default
            ),
            "_retg_v1_now": lambda: "synthetic-time",
            "REAL_EXECUTION_TELEGRAM_NOTIFIER_V1_VERSION": "test-version",
            "REAL_EXECUTION_TELEGRAM_NOTIFIER_V1_EVENTS_FILE": None,
            "REAL_EXECUTION_TELEGRAM_NOTIFIER_V1_LATEST_FILE": None,
            "_ORIGINAL_RUN_EXECUTION_ENGINE_FOR_REAL_EXECUTION_TELEGRAM_NOTIFIER_V1": None,
            "real_execution_telegram_notifier_v1_notify": lambda **kwargs: notifications.append(kwargs),
        }
        isolated_module = ast.Module(body=[route], type_ignores=[])
        exec(
            compile(ast.fix_missing_locations(isolated_module), str(SOURCE), "exec"),
            namespace,
        )
        response = isolated_app.test_client().get(
            "/realexecutiontelegram?send_test=true&ack=REAL_EXECUTION_TELEGRAM_TEST"
        )
        assert response.status_code == 405
        assert response.get_json()["status"] == "TEST_MESSAGE_REQUIRES_POST"
        assert notifications == []
    else:
        isolated_app = Flask("cooldown_get_mutation_regression")
        releases = []
        namespace = {
            "app": isolated_app,
            "request": flask_request,
            "PILOT_COOLDOWN_V1_VERSION": "test-version",
            "pilot_cooldown_v1_release": lambda **kwargs: releases.append(kwargs)
            or {"ok": True, "status": "RELEASED"},
        }
        isolated_module = ast.Module(body=[route], type_ignores=[])
        exec(
            compile(ast.fix_missing_locations(isolated_module), str(SOURCE), "exec"),
            namespace,
        )
        client = isolated_app.test_client()
        blocked = client.get(
            "/pilotcooldown/release?ack=PILOT_COOLDOWN_RELEASE"
        )
        assert blocked.status_code == 405
        assert releases == []
        posted = client.post(
            "/pilotcooldown/release",
            json={"ack": "PILOT_COOLDOWN_RELEASE", "reason": "synthetic-test"},
        )
        assert posted.status_code == 200
        assert releases == [
            {
                "reason": "synthetic-test",
                "payload": {
                    "ack": "PILOT_COOLDOWN_RELEASE",
                    "reason": "synthetic-test",
                },
            }
        ]


def test_memory_stabilizer_aliases_register_get_and_post():
    route = next(
        node
        for node in _TREE.body
        if isinstance(node, ast.FunctionDef) and node.name == "memory_stabilizer_route"
    )
    registered = {}
    for decorator in route.decorator_list:
        if not (
            isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and decorator.func.attr == "route"
            and decorator.args
            and isinstance(decorator.args[0], ast.Constant)
        ):
            continue
        methods = next((kw.value for kw in decorator.keywords if kw.arg == "methods"), None)
        registered[decorator.args[0].value] = {
            item.value for item in methods.elts if isinstance(item, ast.Constant)
        }

    assert registered == {
        "/memory/stabilizer": {"GET", "POST"},
        "/memorystabilizer": {"GET", "POST"},
    }


class _Response:
    def __init__(self, *, response, status, mimetype):
        self.data = response
        self.status_code = status
        self.mimetype = mimetype
        self.headers = {}


class _App:
    response_class = _Response

    def before_request(self, function):
        self.before_request_function = function
        return function


def _load_auth_gate():
    wanted = {
        "_central_personal_http_auth_decision",
        "central_personal_http_auth_before_request",
    }
    nodes = [
        node
        for node in _TREE.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in wanted
    ]
    assert {
        node.name
        for node in nodes
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    } == wanted
    app = _App()
    namespace = {
        "hmac": hmac,
        "urlsplit": urlsplit,
        "os": os,
        "json": json,
        "app": app,
        "request": None,
    }
    module = ast.Module(body=nodes, type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), str(SOURCE), "exec"), namespace)
    return namespace, app


def _load_real_flask_auth_app(*, draining=False, runtime_ready=True):
    """Register the exact source hook on Flask's real request dispatcher."""
    if "personal_http_auth" not in sys.modules:
        auth_helper = ROOT / "personal_http_auth.py"
        spec = importlib.util.spec_from_file_location("personal_http_auth", auth_helper)
        module = importlib.util.module_from_spec(spec)
        sys.modules["personal_http_auth"] = module
        spec.loader.exec_module(module)
    wanted = {
        "_central_personal_http_auth_decision",
        "central_personal_http_auth_before_request",
        "central_personal_http_mutation_method_before_request",
        "central_personal_http_runtime_readiness_before_request",
        "render_healthz_v1",
    }
    nodes = [
        node
        for node in _TREE.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in wanted
    ]
    app = Flask("personal_http_auth_integration_test")
    namespace = {
        "hmac": hmac,
        "urlsplit": urlsplit,
        "os": os,
        "json": json,
        "app": app,
        "request": flask_request,
        "RUNTIME_DRAIN": SimpleNamespace(is_draining=lambda: draining),
        "CENTRAL_RUNTIME_LOCK": threading.RLock(),
        "CENTRAL_RUNTIME_READY": runtime_ready,
    }
    module = ast.Module(body=nodes, type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), str(SOURCE), "exec"), namespace)
    app.add_url_rule(
        "/livestatus",
        "synthetic_livestatus",
        lambda: {"ok": True, "data": "synthetic-only"},
    )
    mutations = []

    def synthetic_mutation():
        mutations.append(flask_request.method)
        return {"ok": True, "write_executed": True}

    app.add_url_rule(
        "/registrymode",
        "synthetic_registrymode",
        synthetic_mutation,
        methods=["GET", "POST"],
    )
    app.add_url_rule(
        "/history/rotation/commit/text",
        "synthetic_history_commit",
        synthetic_mutation,
        methods=["GET", "POST"],
    )
    app.add_url_rule(
        "/learning/refresh",
        "synthetic_learning_refresh",
        synthetic_mutation,
        methods=["GET", "POST"],
    )
    app.add_url_rule(
        "/memory/stabilizer",
        "synthetic_memory_stabilizer",
        synthetic_mutation,
        methods=["GET", "POST"],
    )
    app.add_url_rule(
        "/falcon/centralonly/reconcile",
        "synthetic_falcon_centralonly_reconcile",
        synthetic_mutation,
        methods=["GET", "POST"],
    )
    app.add_url_rule(
        "/memorystabilizer",
        "synthetic_memory_stabilizer_legacy",
        synthetic_mutation,
        methods=["GET", "POST"],
    )
    for path in (
        "/realpnlr",
        "/realpnlr/text",
        "/adaptive/build",
        "/adaptive_weights/build",
        "/executive/alerts/check",
        "/executive_alerts/check",
        "/policyexpiration",
        "/executive/policy/expiration",
        "/policytimeline",
        "/executive/policy/timeline",
        "/policylearning",
        "/executive/policy/learning",
        "/policylearningseed",
        "/executive/policy/learning/seed",
        "/policyeffect",
        "/executive/policy/learning/effect",
        "/policyeffectseed",
        "/executive/policy/learning/effect/seed",
        "/policyeffectrebuild",
        "/executive/policy/learning/effect/rebuild",
        "/policyautorelease",
        "/executive/policy/auto_release",
        "/policypriority",
        "/executive/policy/priority",
        "/outcome/evaluate",
        "/outcome_evaluator/evaluate",
        "/outcome/evaluator/v1",
        "/outcome/evaluate/v1",
        "/learning/evaluate/v1",
        "/learning/outcome/v1",
        "/learning/result/v1",
        "/learn/outcome/v1",
        "/traderegistry/sync/confirm",
        "/trade_registry/sync/confirm",
        "/trades/sync/confirm",
        "/traderegistry/sync",
        "/trade_registry/sync",
        "/trades/sync",
        "/disasterstopfallback",
        "/disasterstop",
        "/paper_lifecycle/update",
        "/paper/lifecycle/update",
        "/paperlifecycleupdate",
        "/paperupdate",
        "/paper_lifecycle/test_tp50",
        "/paper/lifecycle/test_tp50",
        "/paperlifecycletesttp50",
        "/papertesttp50",
        "/paper_lifecycle/test_close",
        "/paper/lifecycle/test_close",
        "/paperlifecycletestclose",
        "/papertestclose",
        "/executionenginerun",
        "/executionrun",
        "/execution_engine/run",
        "/execution/engine/run",
        "/executionverify",
        "/executionengineverify",
        "/execution/verify",
        "/execution/engine/verify",
        "/memory/stabilizer",
        "/memorystabilizer",
    ):
        app.add_url_rule(
            path,
            "synthetic_mutation_" + str(len(app.url_map._rules)),
            synthetic_mutation,
            methods=["GET", "POST"],
        )
    app.test_mutations = mutations
    app._central_runtime_namespace = namespace
    return app


def _request(
    *,
    endpoint="execution_route",
    username=None,
    password=None,
    fetch_site=None,
    origin=None,
    referer=None,
):
    authorization = None
    if username is not None or password is not None:
        authorization = SimpleNamespace(
            type="basic",
            username=username,
            password=password,
        )
    return SimpleNamespace(
        authorization=authorization,
        method="GET",
        path="/synthetic",
        args={},
        headers={
            key: value
            for key, value in {
                "Sec-Fetch-Site": fetch_site,
                "Origin": origin,
                "Referer": referer,
            }.items()
            if value is not None
        },
        endpoint=endpoint,
        host="central.example.test",
    )


def _runtime_auth_pair():
    from personal_http_auth import central_personal_http_auth_expected_passwords

    username, passwords = central_personal_http_auth_expected_passwords()
    assert passwords
    return username, passwords[0]


def _runtime_basic_header():
    username, password = _runtime_auth_pair()
    encoded = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    return "Basic " + encoded


@pytest.fixture(autouse=True)
def block_network(monkeypatch):
    monkeypatch.delenv("CENTRAL_PERSONAL_HTTP_USER", raising=False)
    monkeypatch.delenv("CENTRAL_PERSONAL_HTTP_PASSWORD", raising=False)

    def blocked(*_args, **_kwargs):
        raise AssertionError("network access is forbidden in these tests")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)


def test_auth_decision_fails_closed_when_credentials_are_missing():
    namespace, _ = _load_auth_gate()

    decision = namespace["_central_personal_http_auth_decision"](
        configured_username="",
        configured_password="",
    )

    assert decision == {
        "allowed": False,
        "status": "PRIVATE_HTTP_AUTH_NOT_CONFIGURED",
        "http_status": 503,
    }


def test_auth_decision_requires_basic_credentials_and_compares_them():
    namespace, _ = _load_auth_gate()
    decide = namespace["_central_personal_http_auth_decision"]
    base = {"configured_username": "operator", "configured_password": "synthetic-pass"}

    missing = decide(**base)
    wrong = decide(**base, auth_type="basic", presented_username="operator", presented_password="wrong")
    correct = decide(**base, auth_type="basic", presented_username="operator", presented_password="synthetic-pass")

    assert missing["http_status"] == 401
    assert wrong["http_status"] == 401
    assert correct["allowed"] is True
    assert "synthetic-pass" not in repr((missing, wrong, correct))


def test_auth_decision_supports_unicode_credentials_without_leaking_them():
    namespace, _ = _load_auth_gate()

    decision = namespace["_central_personal_http_auth_decision"](
        configured_username="operador-ç",
        configured_password="senha-de-teste-á",
        auth_type="basic",
        presented_username="operador-ç",
        presented_password="senha-de-teste-á",
    )

    assert decision["allowed"] is True
    assert "senha-de-teste-á" not in repr(decision)


def test_auth_decision_rejects_cross_site_and_malformed_origins():
    namespace, _ = _load_auth_gate()
    decide = namespace["_central_personal_http_auth_decision"]
    base = {
        "configured_username": "operator",
        "configured_password": "synthetic-pass",
        "auth_type": "basic",
        "presented_username": "operator",
        "presented_password": "synthetic-pass",
        "request_host": "central.example.test",
    }

    cross_site = decide(**base, fetch_site="cross-site")
    wrong_origin = decide(**base, origin="https://attacker.example")
    malformed_origin = decide(**base, origin="null")
    same_origin = decide(**base, origin="https://central.example.test")

    assert cross_site["http_status"] == 403
    assert wrong_origin["http_status"] == 403
    assert malformed_origin["http_status"] == 403
    assert same_origin["allowed"] is True


def test_runtime_http_passwords_rotate_without_persisting(monkeypatch):
    import personal_http_auth

    monkeypatch.delenv("CENTRAL_PERSONAL_HTTP_USER", raising=False)
    monkeypatch.delenv("CENTRAL_PERSONAL_HTTP_PASSWORD", raising=False)
    monkeypatch.setattr(personal_http_auth, "_RUNTIME_AUTH_KEY", b"k" * 32)
    username, first_bucket = personal_http_auth.central_personal_http_auth_expected_passwords(
        now=119.0
    )
    next_username, second_bucket = personal_http_auth.central_personal_http_auth_expected_passwords(
        now=120.0
    )

    assert username == next_username == "cq-runtime"
    assert len(first_bucket[0]) == len(second_bucket[0]) == 64
    assert first_bucket[0] != second_bucket[0]
    assert "CENTRAL_PERSONAL_HTTP_PASSWORD" not in personal_http_auth.__dict__


def test_http_gate_accepts_boundary_grace_then_rejects_expired_password(monkeypatch):
    import personal_http_auth

    monkeypatch.delenv("CENTRAL_PERSONAL_HTTP_USER", raising=False)
    monkeypatch.delenv("CENTRAL_PERSONAL_HTTP_PASSWORD", raising=False)
    clock = [119.0]
    monkeypatch.setattr(personal_http_auth.time, "time", lambda: clock[0])
    app = _load_real_flask_auth_app()
    client = app.test_client()
    old_bucket_header = _runtime_basic_header()

    clock[0] = 120.0
    boundary = client.get("/livestatus", headers={"Authorization": old_bucket_header})
    clock[0] = 240.0
    expired = client.get("/livestatus", headers={"Authorization": old_bucket_header})

    assert boundary.status_code == 200
    assert expired.status_code == 401


def test_request_hook_returns_503_if_runtime_auth_initialization_fails(monkeypatch):
    import personal_http_auth

    monkeypatch.setattr(
        personal_http_auth,
        "central_personal_http_auth_expected_passwords",
        lambda: (None, ()),
    )
    namespace, app = _load_auth_gate()
    namespace["request"] = _request()

    response = app.before_request_function()

    assert response.status_code == 503
    assert response.mimetype == "application/json"
    assert json.loads(response.data)["status"] == "PRIVATE_HTTP_AUTH_NOT_CONFIGURED"


def test_request_hook_challenges_missing_or_invalid_credentials(monkeypatch):
    username, _password = _runtime_auth_pair()
    namespace, app = _load_auth_gate()
    namespace["request"] = _request(username=username, password="wrong")

    response = app.before_request_function()

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"].startswith("Basic ")
    assert "synthetic-pass" not in response.data


def test_request_hook_allows_matching_same_origin_credentials(monkeypatch):
    username, password = _runtime_auth_pair()
    namespace, app = _load_auth_gate()
    namespace["request"] = _request(
        username=username,
        password=password,
        fetch_site="same-origin",
        origin="https://central.example.test",
    )

    assert app.before_request_function() is None


def test_request_hook_blocks_cross_site_even_with_valid_basic_credentials(monkeypatch):
    username, password = _runtime_auth_pair()
    namespace, app = _load_auth_gate()
    namespace["request"] = _request(
        username=username,
        password=password,
        fetch_site="cross-site",
    )

    response = app.before_request_function()

    assert response.status_code == 403
    assert json.loads(response.data)["status"] == "CROSS_SITE_REQUEST_BLOCKED"


@pytest.mark.parametrize("endpoint", ["can_open_trade_route", "health", "execution_route", None])
def test_request_hook_fails_closed_for_every_endpoint_when_credentials_are_missing(monkeypatch, endpoint):
    import personal_http_auth

    monkeypatch.setattr(
        personal_http_auth,
        "central_personal_http_auth_expected_passwords",
        lambda: (None, ()),
    )
    namespace, app = _load_auth_gate()
    namespace["request"] = _request(endpoint=endpoint)

    response = app.before_request_function()

    assert response.status_code == 503
    assert json.loads(response.data)["status"] == "PRIVATE_HTTP_AUTH_NOT_CONFIGURED"


def test_global_auth_hook_precedes_routes_with_only_narrow_healthz_exemption():
    hook_index = next(
        index
        for index, node in enumerate(_TREE.body)
        if isinstance(node, ast.FunctionDef)
        and node.name == "central_personal_http_auth_before_request"
    )
    routes = [
        (index, node)
        for index, node in enumerate(_TREE.body)
        if isinstance(node, ast.FunctionDef)
        and any(
            isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and decorator.func.attr == "route"
            for decorator in node.decorator_list
        )
    ]
    mutation_hook_index = next(
        index
        for index, node in enumerate(_TREE.body)
        if isinstance(node, ast.FunctionDef)
        and node.name == "central_personal_http_mutation_method_before_request"
    )
    readiness_hook_index = next(
        index
        for index, node in enumerate(_TREE.body)
        if isinstance(node, ast.FunctionDef)
        and node.name == "central_personal_http_runtime_readiness_before_request"
    )
    assert routes
    assert all(index > hook_index for index, _node in routes)
    assert all(index > mutation_hook_index for index, _node in routes)
    assert all(index > readiness_hook_index for index, _node in routes)
    hook = _TREE.body[hook_index]
    hook_source = ast.unparse(hook)
    assert "request.method ==" in hook_source and "GET" in hook_source
    assert "request.path ==" in hook_source and "/healthz" in hook_source
    assert "not request.args" in hook_source
    assert "PRIVATE_HTTP_AUTH_NOT_CONFIGURED" in hook_source
    assert "PRIVATE_HTTP_AUTH_REQUIRED" in hook_source


def test_authenticated_get_cannot_commit_registry_query_mutation(monkeypatch):
    monkeypatch.setenv("CENTRAL_PERSONAL_HTTP_USER", "local-operator")
    monkeypatch.setenv("CENTRAL_PERSONAL_HTTP_PASSWORD", "synthetic-only-password")
    app = _load_real_flask_auth_app()
    client = app.test_client()
    valid = _runtime_basic_header()

    blocked = client.get("/registrymode?commit=true", headers={"Authorization": valid})
    preview = client.get("/registrymode?commit=false", headers={"Authorization": valid})
    posted = client.post("/registrymode?commit=true", headers={"Authorization": valid})

    assert blocked.status_code == 405
    assert blocked.get_json() == {
        "ok": False,
        "status": "GET_MUTATION_REQUIRES_POST",
        "write_executed": False,
        "order_attempted": False,
        "no_order_sent": True,
    }
    assert app.test_mutations == ["GET", "POST"]
    assert preview.status_code == 200
    assert posted.status_code == 200


def test_authenticated_get_cannot_confirm_registry_sync_or_disaster_stop(monkeypatch):
    monkeypatch.setenv("CENTRAL_PERSONAL_HTTP_USER", "local-operator")
    monkeypatch.setenv("CENTRAL_PERSONAL_HTTP_PASSWORD", "synthetic-only-password")
    app = _load_real_flask_auth_app()
    client = app.test_client()
    valid = _runtime_basic_header()

    paths = (
        "/traderegistry/sync?confirm=1",
        "/trade_registry/sync?confirm=true",
        "/trades/sync?confirm=sim",
        "/disasterstopfallback?commit=true&ack=DISASTER_STOP_FALLBACK",
        "/disasterstop?commit=1&ack=DISASTER_STOP_FALLBACK",
    )
    responses = [client.get(path, headers={"Authorization": valid}) for path in paths]

    assert [response.status_code for response in responses] == [405] * len(paths)
    assert all(
        response.get_json()["status"] == "GET_MUTATION_REQUIRES_POST"
        for response in responses
    )
    assert app.test_mutations == []


def test_authenticated_get_blocks_discovered_registry_and_action_intents(monkeypatch):
    monkeypatch.setenv("CENTRAL_PERSONAL_HTTP_USER", "local-operator")
    monkeypatch.setenv("CENTRAL_PERSONAL_HTTP_PASSWORD", "synthetic-only-password")
    app = _load_real_flask_auth_app()
    client = app.test_client()
    valid = _runtime_basic_header()

    paths = (
        "/registryclosedrecovery?commit=true&ack=RESTORE_CLOSED_TRADE_MANUAL",
        "/registrypersistence?restore=true&commit=false",
        "/trade_registry/storage?force=true",
        "/realcloseidentitybackfill?commit=true&ack=REAL_CLOSE_STRONG_IDENTITY_BACKFILL_V1",
        "/realclosereconciliation?commit=true&ack=REAL_CLOSE_RECONCILE",
        "/falcon/centralonly/reconcile?commit=true&ack=FALCON_CENTRAL_ONLY_RECONCILE",
        "/falcon/centralonly/reconcile/text?commit=true&ack=FALCON_CENTRAL_ONLY_RECONCILE",
        "/realexecutiontelegram?send_test=true&ack=REAL_EXECUTION_TELEGRAM_TEST",
        "/pilotcooldown/release",
        "/executionconsole?action=sync_existing",
        "/risk/registry/check?commit=true",
        "/realtradelifecycle?commit=true",
        "/trade/lifecycle/v1?record_decision=true",
        "/trade/lifecycle/v1?evaluate_closed=true",
        "/trade/lifecycle/v1?evaluate=true",
    )
    responses = [client.get(path, headers={"Authorization": valid}) for path in paths]

    assert [response.status_code for response in responses] == [405] * len(paths)
    assert all(
        response.get_json()["status"] == "GET_MUTATION_REQUIRES_POST"
        for response in responses
    )
    assert app.test_mutations == []


def test_authenticated_get_keeps_centralonly_preview_but_blocks_commit_intent(monkeypatch):
    monkeypatch.setenv("CENTRAL_PERSONAL_HTTP_USER", "local-operator")
    monkeypatch.setenv("CENTRAL_PERSONAL_HTTP_PASSWORD", "synthetic-only-password")
    app = _load_real_flask_auth_app()
    client = app.test_client()
    valid = _runtime_basic_header()

    preview = client.get(
        "/falcon/centralonly/reconcile?commit=false",
        headers={"Authorization": valid},
    )
    assert preview.status_code == 200
    assert app.test_mutations == ["GET"]

    app.test_mutations.clear()
    blocked = client.get(
        "/falcon/centralonly/reconcile?commit=true",
        headers={"Authorization": valid},
    )
    assert blocked.status_code == 405
    assert blocked.get_json()["status"] == "GET_MUTATION_REQUIRES_POST"
    assert app.test_mutations == []


def test_real_close_reconciliation_route_rejects_get_commit_and_keeps_post(monkeypatch):
    route = copy.deepcopy(
        next(
            node
            for node in _TREE.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "real_close_reconciliation_v1_route"
        )
    )
    route.decorator_list = []
    calls = []
    namespace = {
        "request": SimpleNamespace(
            method="GET",
            args={"commit": "true", "ack": "REAL_CLOSE_RECONCILE"},
            path="/realclosereconciliation",
            get_json=lambda silent=True: None,
        ),
        "_rcrm_v1_bool": lambda value, default=False: (
            default if value is None else str(value).strip().lower() in {"1", "true", "yes", "sim", "on"}
        ),
        "REAL_CLOSE_RECONCILIATION_MAIN_V1_VERSION": "synthetic-version",
        "real_close_reconciliation_v1_run": lambda **kwargs: calls.append(kwargs)
        or {"ok": True, "status": "SYNTHETIC_PREVIEW"},
    }
    isolated_module = ast.Module(body=[route], type_ignores=[])
    exec(
        compile(ast.fix_missing_locations(isolated_module), str(SOURCE), "exec"),
        namespace,
    )

    response, status = namespace["real_close_reconciliation_v1_route"]()
    assert status == 405
    assert response["status"] == "POST_REQUIRED_FOR_RECONCILIATION"
    assert response["write_executed"] is False
    assert calls == []

    namespace["request"] = SimpleNamespace(
        method="POST",
        args={},
        path="/realclosereconciliation",
        get_json=lambda silent=True: {
            "commit": True,
            "ack": "REAL_CLOSE_RECONCILE",
        },
    )
    posted, posted_status = namespace["real_close_reconciliation_v1_route"]()
    assert posted_status == 200
    assert posted["status"] == "SYNTHETIC_PREVIEW"
    assert calls[0]["commit"] is True


def test_trade_close_outcome_route_makes_get_preview_only_and_allows_post_commit():
    route = copy.deepcopy(
        next(
            node
            for node in _TREE.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "trade_close_outcome_v1_route"
        )
    )
    registered = {}
    for decorator in route.decorator_list:
        if (
            isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and decorator.func.attr == "route"
            and decorator.args
            and isinstance(decorator.args[0], ast.Constant)
        ):
            methods = next(kw.value for kw in decorator.keywords if kw.arg == "methods")
            registered[decorator.args[0].value] = {
                item.value for item in methods.elts if isinstance(item, ast.Constant)
            }
    assert registered == {
        "/tradecloseoutcome": {"GET", "POST"},
        "/tradecloseoutcomev1": {"GET", "POST"},
        "/trade/close/outcome": {"GET", "POST"},
    }

    route.decorator_list = []
    calls = []
    namespace = {
        "request": SimpleNamespace(
            method="GET",
            args={"symbol": "XRPUSDT", "commit": "true"},
            get_json=lambda silent=True: None,
        ),
        "_tco_v1_bool": lambda value, default=False: (
            default if value is None else str(value).strip().lower() == "true"
        ),
        "trade_close_outcome_v1_build": lambda **kwargs: calls.append(kwargs)
        or {"ok": True, "status": "SYNTHETIC_PREVIEW"},
    }
    isolated_module = ast.Module(body=[route], type_ignores=[])
    exec(
        compile(ast.fix_missing_locations(isolated_module), str(SOURCE), "exec"),
        namespace,
    )
    namespace["trade_close_outcome_v1_route"]()
    assert calls[-1]["commit"] is False
    assert calls[-1]["symbol"] == "XRPUSDT"

    namespace["request"] = SimpleNamespace(
        method="POST",
        args={},
        get_json=lambda silent=True: {"symbol": "XRPUSDT", "commit": True},
    )
    namespace["trade_close_outcome_v1_route"]()
    assert calls[-1]["commit"] is True
    assert calls[-1]["symbol"] == "XRPUSDT"


def test_registry_mode_route_requires_post_for_classification_write():
    route = copy.deepcopy(
        next(
            node
            for node in _TREE.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "registry_mode_segregation_v1_route"
        )
    )
    registered = {}
    for decorator in route.decorator_list:
        if (
            isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and decorator.func.attr == "route"
            and decorator.args
            and isinstance(decorator.args[0], ast.Constant)
        ):
            methods = next(kw.value for kw in decorator.keywords if kw.arg == "methods")
            registered[decorator.args[0].value] = {
                item.value for item in methods.elts if isinstance(item, ast.Constant)
            }
    assert registered == {
        "/registrymodesegregation": {"GET", "POST"},
        "/registrymode": {"GET", "POST"},
    }

    route.decorator_list = []
    calls = []
    namespace = {
        "request": SimpleNamespace(
            method="GET",
            args={"commit": "true"},
            get_json=lambda silent=True: None,
        ),
        "registry_mode_segregation_v1_analyze": lambda **kwargs: calls.append(kwargs)
        or {"ok": True, "status": "SYNTHETIC_PREVIEW"},
    }
    isolated_module = ast.Module(body=[route], type_ignores=[])
    exec(
        compile(ast.fix_missing_locations(isolated_module), str(SOURCE), "exec"),
        namespace,
    )
    blocked = namespace["registry_mode_segregation_v1_route"]()
    assert blocked[1] == 405
    assert blocked[0]["status"] == "POST_REQUIRED_FOR_REGISTRY_MODE_COMMIT"
    assert calls == []

    namespace["request"] = SimpleNamespace(
        method="POST",
        args={},
        get_json=lambda silent=True: {"commit": True},
    )
    posted = namespace["registry_mode_segregation_v1_route"]()
    assert posted["status"] == "SYNTHETIC_PREVIEW"
    assert calls == [{"commit": True, "include_trades": True, "source": "route"}]


@pytest.mark.parametrize(
    ("function_name", "expected_routes"),
    [
        (
            "real_pnl_r_dashboard_route",
            {"/realpnlr": {"GET", "POST"}},
        ),
        (
            "real_pnl_r_text_route",
            {"/realpnlr/text": {"GET", "POST"}},
        ),
        (
            "adaptive_weights_build_route",
            {"/adaptive/build": {"GET", "POST"}, "/adaptive_weights/build": {"GET", "POST"}},
        ),
    ],
)
def test_snapshot_build_routes_reject_get_commit_and_dispatch_post(
    function_name, expected_routes
):
    route = copy.deepcopy(
        next(
            node
            for node in _TREE.body
            if isinstance(node, ast.FunctionDef) and node.name == function_name
        )
    )
    registered = {}
    for decorator in route.decorator_list:
        if (
            isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and decorator.func.attr == "route"
            and decorator.args
            and isinstance(decorator.args[0], ast.Constant)
        ):
            methods = next(kw.value for kw in decorator.keywords if kw.arg == "methods")
            registered[decorator.args[0].value] = {
                item.value for item in methods.elts if isinstance(item, ast.Constant)
            }
    assert registered == expected_routes

    route.decorator_list = []
    builds = []
    namespace = {
        "request": SimpleNamespace(
            method="GET",
            args={"commit": "true"},
            get_json=lambda silent=True: None,
        ),
        "REAL_PNL_R_MAPPER_AVAILABLE": True,
        "REAL_PNL_R_DEFAULT_LIMIT": 5,
        "REAL_PNL_R_MAX_LIMIT": 10,
        "_request_limit": lambda **kwargs: 5,
        "real_pnl_r_mapper": SimpleNamespace(
            build_real_pnl_r_map=lambda **kwargs: builds.append(kwargs)
            or {"ok": True, "status": "SYNTHETIC"},
            build_real_pnl_r_text=lambda payload: "synthetic text",
        ),
        "_compact_real_pnl_payload": lambda payload: payload,
        "_adaptive_weights_bool": lambda value, default=False: default if value is None else str(value).lower() == "true",
        "build_adaptive_weights": lambda **kwargs: builds.append(kwargs)
        or {"ok": True, "status": "SYNTHETIC"},
    }
    isolated_module = ast.Module(body=[route], type_ignores=[])
    exec(
        compile(ast.fix_missing_locations(isolated_module), str(SOURCE), "exec"),
        namespace,
    )
    response = namespace[function_name]()
    assert response[1] == 405
    assert response[0]["write_executed"] is False
    assert builds == []

    namespace["request"] = SimpleNamespace(
        method="POST",
        args={},
        get_json=lambda silent=True: {"commit": True},
    )
    namespace[function_name]()
    assert builds and builds[-1]["commit"] is True


def test_outcome_evaluation_route_is_post_only_and_reads_json_force():
    route = copy.deepcopy(
        next(
            node
            for node in _TREE.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "outcome_evaluator_evaluate_route"
        )
    )
    methods = {
        item.value
        for decorator in route.decorator_list
        if isinstance(decorator, ast.Call)
        and isinstance(decorator.func, ast.Attribute)
        and decorator.func.attr == "route"
        for kw in decorator.keywords
        if kw.arg == "methods"
        for item in kw.value.elts
        if isinstance(item, ast.Constant)
    }
    assert methods == {"POST"}
    route.decorator_list = []
    calls = []
    namespace = {
        "request": SimpleNamespace(get_json=lambda silent=True: {"force": True}),
        "evaluate_closed_paper_trades": lambda **kwargs: calls.append(kwargs)
        or {"ok": True},
    }
    isolated_module = ast.Module(body=[route], type_ignores=[])
    exec(
        compile(ast.fix_missing_locations(isolated_module), str(SOURCE), "exec"),
        namespace,
    )
    assert namespace["outcome_evaluator_evaluate_route"]() == {"ok": True}
    assert calls == [{"force": True}]


@pytest.mark.parametrize("path", ["/memory/emergency", "/memoryemergency"])
def test_memory_emergency_get_is_read_only_and_post_performs_cleanup(path):
    route = copy.deepcopy(
        next(
            node
            for node in _TREE.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "memory_emergency_guard_v1_route"
        )
    )
    registered = {}
    for decorator in route.decorator_list:
        if (
            isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and decorator.func.attr == "route"
        ):
            methods = next(kw.value for kw in decorator.keywords if kw.arg == "methods")
            registered[decorator.args[0].value] = {
                item.value for item in methods.elts if isinstance(item, ast.Constant)
            }
    assert registered == {
        "/memory/emergency": {"GET", "POST"},
        "/memoryemergency": {"GET", "POST"},
    }

    route.decorator_list = []
    cleanup_calls = []
    namespace = {
        "request": SimpleNamespace(method="GET"),
        "_meg_v1_memory_snapshot": lambda: {"rss_mb": 1},
        "_meg_v1_cleanup": lambda **kwargs: cleanup_calls.append(kwargs) or {"ok": True},
        "MEMORY_EMERGENCY_GUARD_V1_VERSION": "synthetic",
        "MEMORY_EMERGENCY_GUARD_ENABLED": True,
        "_eaa_v1_now": lambda: "synthetic-time",
    }
    isolated = ast.Module(body=[route], type_ignores=[])
    exec(compile(ast.fix_missing_locations(isolated), str(SOURCE), "exec"), namespace)

    response, status = namespace["memory_emergency_guard_v1_route"]()
    assert status == 200
    assert response["cleanup"] == {
        "ok": True,
        "status": "READ_ONLY_PREVIEW",
        "cleanup_performed": False,
    }
    assert cleanup_calls == []

    namespace["request"] = SimpleNamespace(method="POST")
    namespace["memory_emergency_guard_v1_route"]()
    assert cleanup_calls == [{"reason": "/memory/emergency", "force": True}]


def test_authenticated_get_cannot_invoke_path_encoded_mutation(monkeypatch):
    monkeypatch.setenv("CENTRAL_PERSONAL_HTTP_USER", "local-operator")
    monkeypatch.setenv("CENTRAL_PERSONAL_HTTP_PASSWORD", "synthetic-only-password")
    app = _load_real_flask_auth_app()
    client = app.test_client()
    valid = _runtime_basic_header()

    blocked = client.get(
        "/history/rotation/commit/text?ack=ROTATE_HISTORY",
        headers={"Authorization": valid},
    )
    posted = client.post(
        "/history/rotation/commit/text?ack=ROTATE_HISTORY",
        headers={"Authorization": valid},
    )

    assert blocked.status_code == 405
    assert blocked.get_json()["status"] == "GET_MUTATION_REQUIRES_POST"
    assert app.test_mutations == ["POST"]


def test_authenticated_get_cannot_trigger_learning_refresh(monkeypatch):
    monkeypatch.setenv("CENTRAL_PERSONAL_HTTP_USER", "local-operator")
    monkeypatch.setenv("CENTRAL_PERSONAL_HTTP_PASSWORD", "synthetic-only-password")
    app = _load_real_flask_auth_app()
    client = app.test_client()
    valid = _runtime_basic_header()

    blocked = client.get("/learning/refresh", headers={"Authorization": valid})
    posted = client.post("/learning/refresh", headers={"Authorization": valid})

    assert blocked.status_code == 405
    assert blocked.get_json()["status"] == "GET_MUTATION_REQUIRES_POST"
    assert posted.status_code == 200
    assert app.test_mutations == ["POST"]


@pytest.mark.parametrize("path", ["/memory/stabilizer", "/memorystabilizer"])
def test_authenticated_memory_gc_route_requires_post(monkeypatch, path):
    monkeypatch.setenv("CENTRAL_PERSONAL_HTTP_USER", "local-operator")
    monkeypatch.setenv("CENTRAL_PERSONAL_HTTP_PASSWORD", "synthetic-only-password")
    app = _load_real_flask_auth_app()
    client = app.test_client()
    valid = _runtime_basic_header()

    blocked = client.get(path, headers={"Authorization": valid})
    posted = client.post(path, headers={"Authorization": valid})

    assert blocked.status_code == 405
    assert blocked.get_json()["status"] == "GET_MUTATION_REQUIRES_POST"
    assert posted.status_code == 200
    assert app.test_mutations == ["POST"]


@pytest.mark.parametrize(
    "path",
    [
        "/realpnlr",
        "/realpnlr/text",
        "/adaptive/build",
        "/adaptive_weights/build",
        "/executive/alerts/check",
        "/executive_alerts/check",
        "/policyexpiration",
        "/executive/policy/expiration",
        "/policytimeline",
        "/executive/policy/timeline",
        "/policylearning",
        "/executive/policy/learning",
        "/policylearningseed",
        "/executive/policy/learning/seed",
        "/policyeffect",
        "/executive/policy/learning/effect",
        "/policyeffectseed",
        "/executive/policy/learning/effect/seed",
        "/policyeffectrebuild",
        "/executive/policy/learning/effect/rebuild",
        "/policyautorelease",
        "/executive/policy/auto_release",
        "/policypriority",
        "/executive/policy/priority",
        "/outcome/evaluate",
        "/outcome_evaluator/evaluate",
        "/learning/outcome/v1",
        "/learning/result/v1",
        "/learn/outcome/v1",
        "/traderegistry/sync/confirm",
        "/trade_registry/sync/confirm",
        "/trades/sync/confirm",
    ],
)
def test_authenticated_get_blocks_legacy_mutation_routes_by_default(monkeypatch, path):
    monkeypatch.setenv("CENTRAL_PERSONAL_HTTP_USER", "local-operator")
    monkeypatch.setenv("CENTRAL_PERSONAL_HTTP_PASSWORD", "synthetic-only-password")
    app = _load_real_flask_auth_app()
    client = app.test_client()
    valid = _runtime_basic_header()

    response = client.get(path, headers={"Authorization": valid})

    assert response.status_code == 405
    assert response.get_json()["status"] == "GET_MUTATION_REQUIRES_POST"
    assert app.test_mutations == []


def test_trade_registry_sync_confirmation_aliases_are_post_only():
    route = next(
        node
        for node in _TREE.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "trade_registry_sync_route"
    )
    registered = {}
    for decorator in route.decorator_list:
        if not (
            isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and decorator.func.attr == "route"
            and decorator.args
            and isinstance(decorator.args[0], ast.Constant)
        ):
            continue
        methods = next(
            (kw.value for kw in decorator.keywords if kw.arg == "methods"), None
        )
        registered[decorator.args[0].value] = {
            item.value for item in methods.elts if isinstance(item, ast.Constant)
        }
    assert registered == {
        "/traderegistry/sync": {"GET", "POST"},
        "/trade_registry/sync": {"GET", "POST"},
        "/trades/sync": {"GET", "POST"},
        "/traderegistry/sync/confirm": {"POST"},
        "/trade_registry/sync/confirm": {"POST"},
        "/trades/sync/confirm": {"POST"},
    }


def test_registry_sync_get_is_preview_even_with_json_or_query_confirmation():
    route = next(
        node
        for node in _TREE.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "trade_registry_sync_route"
    )
    app = Flask("trade_registry_sync_method_test")
    commits = []

    def sync_trade_registry_from_open_positions(*, commit=False):
        commits.append(bool(commit))
        return {"ok": True, "commit": bool(commit)}

    namespace = {
        "app": app,
        "request": flask_request,
        "sync_trade_registry_from_open_positions": sync_trade_registry_from_open_positions,
    }
    module = ast.Module(body=[route], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), str(SOURCE), "exec"), namespace)

    client = app.test_client()
    get_json = client.get("/traderegistry/sync", json={"confirm": True})
    get_query = client.get("/traderegistry/sync?confirm=1")
    post_json = client.post("/traderegistry/sync", json={"confirm": True})
    post_alias = client.post("/traderegistry/sync/confirm")

    assert get_json.status_code == 200
    assert get_query.status_code == 200
    assert post_json.status_code == 200
    assert post_alias.status_code == 200
    assert commits == [False, False, True, True]


def test_predator_registry_mutation_routes_ignore_get_json_confirmation():
    wanted = {
        "predator_paper_registry_sync_fix_v1_route",
        "predator_paper_registry_sync_fix_v1_text_route",
        "predator_registry_orphan_open_fix_v1_route",
        "predator_registry_orphan_open_fix_v1_text_route",
        "predator_auto_closed_sync_v1_route",
        "predator_auto_closed_sync_v1_text_route",
    }
    routes = [
        node
        for node in _TREE.body
        if isinstance(node, ast.FunctionDef) and node.name in wanted
    ]
    assert {node.name for node in routes} == wanted

    app = Flask("predator_get_body_mutation_test")
    calls = []

    def status(name):
        def run(*args, **kwargs):
            calls.append((name, bool(kwargs.get("commit"))))
            return {"ok": True, "commit": bool(kwargs.get("commit"))}
        return run

    def text(name):
        def build(*args, **kwargs):
            calls.append((name, bool(kwargs.get("commit"))))
            return f"{name}:{bool(kwargs.get('commit'))}"
        return build

    namespace = {
        "app": app,
        "request": flask_request,
        "_pprsf_v1_bool": lambda value, default=False: (
            str(value).strip().lower() in {"1", "true", "yes", "sim", "on"}
            if value is not None else default
        ),
        "predator_paper_registry_sync_fix_v1_status": status("paper_sync"),
        "build_predator_paper_registry_sync_fix_v1_text": text("paper_sync_text"),
        "predator_registry_orphan_open_fix_v1_status": status("orphan_fix"),
        "build_predator_registry_orphan_open_fix_v1_text": text("orphan_fix_text"),
        "predator_auto_closed_sync_v1_status": status("auto_closed_sync"),
        "build_predator_auto_closed_sync_v1_text": text("auto_closed_sync_text"),
    }
    module = ast.Module(body=routes, type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), str(SOURCE), "exec"), namespace)

    registered_paths = []
    for route in routes:
        for decorator in route.decorator_list:
            if (
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Attribute)
                and decorator.func.attr == "route"
                and decorator.args
                and isinstance(decorator.args[0], ast.Constant)
            ):
                registered_paths.append(decorator.args[0].value)

    client = app.test_client()
    for path in registered_paths:
        get_result = client.get(
            f"{path}?commit=true&ack=LOCAL_TEST_ACK",
            json={"commit": True, "ack": "LOCAL_TEST_ACK"},
        )
        assert get_result.status_code == 200
        assert calls[-1][1] is False

        post_result = client.post(
            path,
            json={"commit": True, "ack": "LOCAL_TEST_ACK"},
        )
        assert post_result.status_code == 200
        assert calls[-1][1] is True

    assert len(calls) == len(registered_paths) * 2


def test_learning_and_adaptive_routes_do_not_persist_on_get_body_or_query():
    route_names = {
        "adaptive_weight_engine_v1_route",
        "adaptive_weight_engine_v2_route",
        "learning_engine_v1_route",
        "outcome_evaluator_v1_route",
        "meta_strategy_engine_v11_route",
        "market_regime_detector_v1_route",
        "strategy_evolution_engine_v1_route",
        "trade_lifecycle_manager_v1_route",
    }
    routes = [
        node
        for node in _TREE.body
        if isinstance(node, ast.FunctionDef) and node.name in route_names
    ]
    assert {node.name for node in routes} == route_names

    app = Flask("learning_get_body_mutation_test")
    calls = {}

    def capture(name, *, pair=False):
        def run(**kwargs):
            calls[name] = dict(kwargs)
            return ("synthetic text", {"ok": True}) if pair else {"ok": True}
        return run

    namespace = {
        "app": app,
        "request": flask_request,
        "_dse_request_payload_from_args": lambda body: {**dict(flask_request.args), **(body or {})},
        "_awe_safe_float": lambda value, default=0.0: default,
        "_le_safe_float": lambda value, default=None: default,
        "_mse_safe_float": lambda value, default=0.0: default,
        "_mrd_safe_float": lambda value, default=0.0: default,
        "_see_safe_float": lambda value, default=0.0: default,
        "_tlm_safe_float": lambda value, default=None: default,
        "build_adaptive_weight_engine_v1_text": capture("adaptive_v1", pair=True),
        "build_adaptive_weight_engine_v2_text": capture("adaptive_v2", pair=True),
        "build_learning_engine_v1": capture("learning"),
        "build_learning_engine_v1_text": lambda payload: "synthetic text",
        "build_outcome_evaluator_v1": capture("outcome"),
        "build_outcome_evaluator_v1_text": lambda payload: "synthetic text",
        "build_meta_strategy_engine_v1_1_text": capture("meta_strategy", pair=True),
        "build_market_regime_detector_v1_text": capture("market_regime", pair=True),
        "build_strategy_evolution_engine_v1_text": capture("strategy_evolution", pair=True),
        "build_trade_lifecycle_manager_v1_text": capture("trade_lifecycle", pair=True),
    }
    module = ast.Module(body=routes, type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), str(SOURCE), "exec"), namespace)

    paths = {
        "adaptive_v1": "/adaptive/weights/v1",
        "adaptive_v2": "/adaptive/weights/v2",
        "learning": "/learning/engine/v1",
        "outcome": "/outcome/evaluator/v1?save=false",
        "meta_strategy": "/meta/strategy/v1",
        "market_regime": "/market/regime/v1",
        "strategy_evolution": "/strategy/evolution/v1",
        "trade_lifecycle": "/trade/lifecycle/v1",
    }
    mutation_flags = {
        "persist": True,
        "record": True,
        "save": True,
        "record_decision": True,
        "evaluate": True,
        "evaluate_closed": True,
    }
    client = app.test_client()
    for name, path in paths.items():
        get_result = client.get(path + "&" if "?" in path else path + "?" + "&".join(f"{key}={str(value).lower()}" for key, value in mutation_flags.items()), json=mutation_flags)
        assert get_result.status_code == 200
        get_kwargs = calls[name]
        for key in ("persist", "record", "save", "record_decision", "evaluate_closed"):
            if key in get_kwargs:
                assert get_kwargs[key] is False

        post_result = client.post(path.split("?", 1)[0], json=mutation_flags)
        assert post_result.status_code == 200
        post_kwargs = calls[name]
        for key in ("persist", "record", "save", "record_decision", "evaluate_closed"):
            if key in post_kwargs:
                assert post_kwargs[key] is True


def test_auto_real_bridge_test_route_is_post_only_and_forces_dry_run():
    route = copy.deepcopy(
        next(
            node
            for node in _TREE.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "auto_real_execution_bridge_v1_test_route"
        )
    )
    app = Flask("auto_real_bridge_test_post_only")
    calls = []

    def process(**kwargs):
        calls.append(kwargs)
        return {"ok": True, "status": "SYNTHETIC_TEST"}

    namespace = {
        "app": app,
        "request": flask_request,
        "time": SimpleNamespace(time=lambda: 1),
        "_arb_v1_normalize_payload": lambda payload, manual_defaults: dict(payload),
        "auto_real_execution_bridge_v1_process": process,
        "_arb_v1_sanitize_public": lambda value: value,
    }
    module = ast.Module(body=[route], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), str(SOURCE), "exec"), namespace)

    client = app.test_client()
    get_result = client.get("/autorealbridge/test?mode=LIVE&execute=true")
    assert get_result.status_code == 405
    assert calls == []

    post_result = client.post("/autorealbridge/test", json={"mode": "VERIFY"})
    assert post_result.status_code == 200
    assert calls == [
        {
            "payload": {
                "mode": "VERIFY",
                "signal_id": "AUTO-REAL-BRIDGE-TEST-1",
            },
            "risk_result": {
                "allowed": True,
                "decision": "ALLOW",
                "mode": "VERIFY",
            },
            "source": "test_route",
            "execute": False,
            "dry_run": True,
        }
    ]


def test_can_open_trade_http_route_is_post_only_before_decision_chain():
    route = copy.deepcopy(
        next(
            node
            for node in _TREE.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "can_open_trade_route"
        )
    )
    app = Flask("can_open_trade_post_only")
    decisions = []
    namespace = {
        "app": app,
        "request": flask_request,
        "can_open_trade_decision": lambda payload: decisions.append(payload)
        or {"ok": True, "decision": "DENY"},
    }
    module = ast.Module(body=[route], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), str(SOURCE), "exec"), namespace)

    client = app.test_client()
    get_result = client.get(
        "/can_open_trade?mode=LIVE&decision=ALLOW&symbol=BTCUSDT&side=LONG"
    )
    assert get_result.status_code == 405
    assert decisions == []

    post_result = client.post("/can_open_trade", json={"mode": "PAPER"})
    assert post_result.status_code == 200
    assert decisions == [{"mode": "PAPER"}]


def test_execution_live_route_get_never_calls_execution_engine():
    route = copy.deepcopy(
        next(
            node
            for node in _TREE.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "execution_engine_live_route"
        )
    )
    app = Flask("execution_live_get_no_engine")
    engine_calls = []
    configured_phrase = "SENTINEL_PRIVATE_CONFIRMATION_PHRASE"
    namespace = {
        "app": app,
        "request": flask_request,
        "os": SimpleNamespace(
            environ={"EXECUTION_LIVE_CONFIRMATION_PHRASE": configured_phrase}
        ),
        "run_execution_engine": lambda **kwargs: engine_calls.append(kwargs)
        or {"ok": True, "sent": True},
    }
    module = ast.Module(body=[route], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), str(SOURCE), "exec"), namespace)

    client = app.test_client()
    aliases = (
        "/executionlive",
        "/execution/live",
        "/executionengine/live",
        "/execution/engine/live",
    )
    responses = [
        client.get(
            f"{path}?mode=LIVE&confirm=EXECUTE_REAL_TRADE&symbol=BTCUSDT&side=LONG"
        )
        for path in aliases
    ]

    assert [response.status_code for response in responses] == [405] * len(aliases)
    assert all(response.get_json()["status"] == "POST_REQUIRED" for response in responses)
    assert all(response.get_json()["sent"] is False for response in responses)
    assert all(
        configured_phrase not in response.get_data(as_text=True)
        and "required_confirmation_value" not in response.get_json()
        for response in responses
    )

    invalid_post = client.post(
        "/executionlive", json={"confirm": "WRONG_PRIVATE_VALUE"}
    )
    assert invalid_post.status_code == 400
    assert configured_phrase not in invalid_post.get_data(as_text=True)
    assert "required_confirmation_value" not in invalid_post.get_json()
    assert invalid_post.get_json()["confirmation_received"] is True
    assert engine_calls == []


def test_real_execution_final_gate_never_returns_confirmation_value():
    route = next(
        node
        for node in _TREE.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "execution_console_route"
    )
    helper = next(
        node
        for node in ast.walk(route)
        if isinstance(node, ast.FunctionDef)
        and node.name == "_build_real_execution_final_gate"
    )
    namespace = {
        "_gate_env_token_present": lambda: (False, None),
        "registry_persistence_v1_gate_check": lambda _payload: {"ok": False},
        "trade_close_outcome_v1_gate_check": lambda: {"ok": False},
        "registry_mode_segregation_v1_gate_check": lambda _payload: {"ok": False},
        "disaster_stop_fallback_v1_gate_check": lambda: {"ok": False},
        "_normalize_console_symbol": lambda value: str(value or "").upper(),
        "_normalize_console_side": lambda value: str(value or "").upper(),
        "_gate_float": lambda value, default=None: (
            float(value) if value is not None else default
        ),
        "re": re,
    }
    module = ast.Module(body=[copy.deepcopy(helper)], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), str(SOURCE), "exec"), namespace)

    configured_phrase = "SENTINEL_PRIVATE_CONFIRMATION_PHRASE"
    gate = namespace[helper.name](
        {},
        {},
        {},
        confirm_value=configured_phrase,
        required_phrase=configured_phrase,
        action_context="execute",
    )

    assert configured_phrase not in json.dumps(gate)
    confirmation_check = next(
        item for item in gate["checks"] if item["code"] == "CONFIRMATION_PHRASE"
    )
    assert confirmation_check["detail"] == {
        "required_for_execute": True,
        "received_ok": True,
        "mode": "execute",
        "confirmation_value_exposed": False,
    }


def test_watchdog_notification_cannot_be_triggered_by_get():
    route = copy.deepcopy(
        next(
            node
            for node in _TREE.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "real_position_watchdog_v1_route"
        )
    )
    app = Flask("watchdog_notification_post_only")
    assessments = []

    def assess(**kwargs):
        assessments.append(kwargs)
        return {"ok": True, "notification": {"sent": bool(kwargs.get("notify"))}}

    namespace = {
        "app": app,
        "request": flask_request,
        "_rpw_v1_bool": lambda value, default=False: (
            str(value or "").strip().lower() in {"1", "true", "yes", "on", "sim"}
            if value is not None
            else default
        ),
        "REAL_POSITION_WATCHDOG_V1_VERSION": "synthetic-test",
        "real_position_watchdog_v1_assess": assess,
    }
    module = ast.Module(body=[route], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), str(SOURCE), "exec"), namespace)

    client = app.test_client()
    get_result = client.get(
        "/realpositionwatchdog?notify=true&ack=REAL_POSITION_WATCHDOG_NOTIFY"
    )
    assert get_result.status_code == 405
    assert get_result.get_json()["status"] == "POST_REQUIRED_FOR_NOTIFICATION"
    assert get_result.get_json()["notification_sent"] is False
    assert assessments == []

    post_result = client.post(
        "/realpositionwatchdog",
        json={"notify": True, "ack": "REAL_POSITION_WATCHDOG_NOTIFY"},
    )
    assert post_result.status_code == 200
    assert len(assessments) == 1
    assert assessments[0]["notify"] is True


def test_falcon_live_audit_ack_is_post_json_only():
    route = copy.deepcopy(
        next(
            node
            for node in _TREE.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "falcon_live_audit_guard_v1_ack_route"
        )
    )
    app = Flask("falcon_live_audit_ack_post_only")
    state = {"acked_bad_event_keys": []}
    saves = []
    events = []
    namespace = {
        "app": app,
        "request": flask_request,
        "_fleag_v1_bool": lambda value, default=False: (
            str(value or "").strip().lower() in {"1", "true", "yes", "on", "sim"}
            if value is not None
            else default
        ),
        "FALCON_LIVE_EXECUTION_AUDIT_GUARD_V1_VERSION": "synthetic-v1",
        "_fleag_v1_load_state": lambda: state,
        "_fleag_v1_read_bad_execution_events": lambda limit: [
            {"event": "SYNTHETIC_BAD_EVENT", "id": "bad-1"}
        ],
        "_fleag_v1_bad_event_key_candidates_v1_2": lambda event: ["key-1"],
        "_fleag_v1_bad_event_canonical_key_v1_3": lambda event: None,
        "_fleag_v1_event_key": lambda event: event.get("id"),
        "_fleag_v1_now": lambda: "synthetic-time",
        "_fleag_v1_save_state": lambda value: saves.append(copy.deepcopy(value)),
        "_fleag_v1_append_event": lambda value: events.append(copy.deepcopy(value)),
        "_fleag_v1_public": lambda value: dict(value),
    }
    module = ast.Module(body=[route], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), str(SOURCE), "exec"), namespace)

    client = app.test_client()
    get_result = client.get(
        "/falcon/liveaudit/ack?ack=FALCON_LIVE_AUDIT_ACK&clear_block=true"
    )
    assert get_result.status_code == 405
    assert saves == []
    assert events == []

    post_result = client.post(
        "/falcon/liveaudit/ack",
        json={"ack": "FALCON_LIVE_AUDIT_ACK", "clear_block": True},
    )
    assert post_result.status_code == 200
    assert post_result.get_json()["status"] == "ACK_SAVED_RECHECK_REQUIRED"
    assert len(saves) == 1
    assert len(events) == 1
    assert state["live_audit_status"] == "ACKED_RECHECK_REQUIRED"


@pytest.mark.parametrize(
    ("route_name", "path", "runner_name", "report_name", "runner_kwargs"),
    [
        (
            "policy_auto_release_route",
            "/policyautorelease",
            "run_executive_policy_auto_release",
            "build_executive_policy_auto_release_report",
            {"context": {}},
        ),
        (
            "policy_priority_route",
            "/policypriority",
            "resolve_executive_policy_priority",
            "build_executive_policy_priority_report",
            {"trade_payload": None, "commit": True},
        ),
    ],
)
def test_executive_policy_mutation_routes_are_post_only(
    route_name, path, runner_name, report_name, runner_kwargs
):
    route = copy.deepcopy(
        next(
            node
            for node in _TREE.body
            if isinstance(node, ast.FunctionDef) and node.name == route_name
        )
    )
    app = Flask("executive_policy_post_only_" + route_name)
    calls = []

    def run(**kwargs):
        calls.append(kwargs)
        return {"ok": True, "synthetic": True}

    namespace = {
        "app": app,
        runner_name: run,
        report_name: lambda result: "synthetic policy report",
    }
    module = ast.Module(body=[route], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), str(SOURCE), "exec"), namespace)

    client = app.test_client()
    get_result = client.get(path)
    assert get_result.status_code == 405
    assert calls == []

    post_result = client.post(path)
    assert post_result.status_code == 200
    assert calls == [runner_kwargs]


def test_history_trades_rebuild_is_inert_and_post_only():
    route = next(
        node
        for node in ast.walk(_TREE)
        if isinstance(node, ast.FunctionDef)
        and node.name == "history_trades_rebuild"
    )
    registered = {}
    for decorator in route.decorator_list:
        if not (
            isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and decorator.func.attr == "route"
            and decorator.args
            and isinstance(decorator.args[0], ast.Constant)
        ):
            continue
        methods = next(
            (kw.value for kw in decorator.keywords if kw.arg == "methods"), None
        )
        registered[decorator.args[0].value] = {
            item.value for item in methods.elts if isinstance(item, ast.Constant)
        }
    assert registered == {"/history/trades/rebuild": {"POST"}}

    executable = ast.FunctionDef(
        name=route.name,
        args=route.args,
        body=route.body,
        decorator_list=[],
        returns=route.returns,
        type_comment=route.type_comment,
    )
    namespace = {}
    module = ast.Module(body=[executable], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), str(SOURCE), "exec"), namespace)
    result, status = namespace[route.name]()

    assert status == 409
    assert result == {
        "ok": False,
        "status": "DESTRUCTIVE_HISTORY_REBUILD_DISABLED",
        "write_executed": False,
        "history_unchanged": True,
    }


def test_learning_outcome_route_aliases_are_post_only():
    route = next(
        node
        for node in _TREE.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "learning_outcome_v1_route"
    )
    registered = {}
    for decorator in route.decorator_list:
        if not (
            isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and decorator.func.attr == "route"
            and decorator.args
            and isinstance(decorator.args[0], ast.Constant)
        ):
            continue
        methods = next(
            (kw.value for kw in decorator.keywords if kw.arg == "methods"), None
        )
        registered[decorator.args[0].value] = {
            item.value for item in methods.elts if isinstance(item, ast.Constant)
        }
    assert registered == {
        "/learning/outcome/v1": {"POST"},
        "/learning/result/v1": {"POST"},
        "/learn/outcome/v1": {"POST"},
    }


@pytest.mark.parametrize(
    "path",
    [
        "/realpnlr?commit=false",
        "/realpnlr/text?commit=0",
        "/adaptive/build?commit=false",
        "/adaptive_weights/build?commit=0",
        "/outcome/evaluator/v1?save=false",
        "/outcome/evaluate/v1?save=0",
        "/learning/evaluate/v1?save=false",
        "/executive/alerts/check?check_only=true",
        "/executive_alerts/check?check_only=true",
        "/policyexpiration?check_only=true",
        "/executive/policy/expiration?check_only=1",
        "/policytimeline?check_only=true",
        "/executive/policy/timeline?check_only=1",
        "/policylearning?check_only=true",
        "/executive/policy/learning?check_only=1",
        "/policylearningseed?check_only=true",
        "/executive/policy/learning/seed?check_only=1",
        "/policyeffect?check_only=true",
        "/executive/policy/learning/effect?check_only=1",
        "/policyeffectseed?check_only=true",
        "/executive/policy/learning/effect/seed?check_only=1",
        "/policyeffectrebuild?check_only=true",
        "/executive/policy/learning/effect/rebuild?check_only=1",
    ],
)
def test_authenticated_get_allows_only_explicit_read_only_route_modes(monkeypatch, path):
    monkeypatch.setenv("CENTRAL_PERSONAL_HTTP_USER", "local-operator")
    monkeypatch.setenv("CENTRAL_PERSONAL_HTTP_PASSWORD", "synthetic-only-password")
    app = _load_real_flask_auth_app()
    client = app.test_client()
    valid = _runtime_basic_header()

    response = client.get(path, headers={"Authorization": valid})

    assert response.status_code == 200
    assert app.test_mutations == ["GET"]


def test_risk_registry_check_only_syncs_registry_on_post():
    node = copy.deepcopy(
        next(
            item
            for item in _TREE.body
            if isinstance(item, ast.FunctionDef)
            and item.name == "risk_registry_check_route"
        )
    )
    node.decorator_list = []
    sync_calls = []
    namespace = {
        "request": SimpleNamespace(method="GET"),
        "autosync_trade_registry": lambda **kwargs: sync_calls.append(kwargs),
        "central_exposure_snapshot": lambda: {
            "source": "trade_registry",
            "total_positions_open": 0,
            "long_positions_open": 0,
            "short_positions_open": 0,
        },
        "central_trade_registry_snapshot": lambda **kwargs: {
            "loaded": True,
            "ok": True,
            "open_count": 0,
            "updated_at": None,
            "trade_registry_file": "synthetic-only",
        },
    }
    module = ast.Module(body=[node], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), str(SOURCE), "exec"), namespace)

    get_result = namespace["risk_registry_check_route"]()
    assert get_result["status"] == "OK"
    assert get_result["registry_sync"] == {"attempted": False, "error": None}
    assert sync_calls == []

    namespace["request"].method = "POST"
    post_result = namespace["risk_registry_check_route"]()
    assert post_result["status"] == "OK"
    assert post_result["registry_sync"] == {"attempted": True, "error": None}
    assert sync_calls == [{"reason": "risk_registry_check"}]


def test_risk_registry_only_syncs_registry_on_post():
    node = copy.deepcopy(
        next(
            item
            for item in _TREE.body
            if isinstance(item, ast.FunctionDef)
            and item.name == "risk_registry_route"
        )
    )
    node.decorator_list = []
    sync_calls = []
    namespace = {
        "request": SimpleNamespace(method="GET"),
        "autosync_trade_registry": lambda **kwargs: sync_calls.append(kwargs),
        "central_trade_registry": object(),
        "central_exposure_snapshot": lambda: {
            "source": "trade_registry",
            "total_positions_open": 0,
            "long_positions_open": 0,
            "short_positions_open": 0,
            "by_bot": {},
        },
    }
    module = ast.Module(body=[node], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), str(SOURCE), "exec"), namespace)

    get_result = namespace["risk_registry_route"]()
    assert get_result["registry_sync"] == {"attempted": False, "error": None}
    assert sync_calls == []

    namespace["request"].method = "POST"
    post_result = namespace["risk_registry_route"]()
    assert post_result["registry_sync"] == {"attempted": True, "error": None}
    assert sync_calls == [{"reason": "risk_registry"}]


@pytest.mark.parametrize(
    ("route_name", "expected_path"),
    [
        ("policy_auto_release_report_route", "policy_auto_release_health"),
        ("policy_priority_report_route", "policy_priority_preview"),
    ],
)
def test_policy_report_get_routes_are_read_only(route_name, expected_path):
    node = copy.deepcopy(
        next(
            item
            for item in _TREE.body
            if isinstance(item, ast.FunctionDef) and item.name == route_name
        )
    )
    node.decorator_list = []
    calls = []

    def get_health():
        calls.append("policy_auto_release_health")
        return {
            "ok": True,
            "active_policy_count": 1,
            "last_run_at": "synthetic",
            "last_released_codes": [],
        }

    def resolve(*, trade_payload, commit):
        calls.append("policy_priority_commit" if commit else "policy_priority_preview")
        return {"ok": True, "decision": "ALLOW"}

    namespace = {
        "get_executive_policy_auto_release_health": get_health,
        "resolve_executive_policy_priority": resolve,
        "build_executive_policy_priority_report": lambda result: "synthetic report",
    }
    module = ast.Module(body=[node], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), str(SOURCE), "exec"), namespace)

    result = namespace[route_name]()

    assert expected_path in calls
    assert "policy_priority_commit" not in calls
    assert "policy_auto_release_execution" not in calls
    if route_name == "policy_auto_release_report_route":
        assert "não executa liberação" in result["text"]
    else:
        assert result["text"] == "synthetic report"


@pytest.mark.parametrize(
    "query",
    [
        "update_registry=true",
        "close_registry=true",
        "mark_closed=true",
        "ack=CONFIRM",
        "confirmation=CONFIRM",
        "send=true",
        "action=execute",
    ],
)
def test_authenticated_get_blocks_additional_action_intent_fields(monkeypatch, query):
    monkeypatch.setenv("CENTRAL_PERSONAL_HTTP_USER", "local-operator")
    monkeypatch.setenv("CENTRAL_PERSONAL_HTTP_PASSWORD", "synthetic-only-password")
    app = _load_real_flask_auth_app()
    client = app.test_client()
    valid = _runtime_basic_header()

    response = client.get(f"/registrymode?{query}", headers={"Authorization": valid})

    assert response.status_code == 405
    assert app.test_mutations == []


def _personal_http_action_fields():
    helper_path = ROOT / "personal_http_auth.py"
    helper_tree = ast.parse(helper_path.read_text(encoding="utf-8"), filename=str(helper_path))
    function = next(
        node
        for node in helper_tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "central_personal_http_get_mutation_block"
    )
    for node in ast.walk(function):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Set):
            continue
        if any(isinstance(target, ast.Name) and target.id == "action_fields" for target in node.targets):
            return {
                element.value
                for element in node.value.elts
                if isinstance(element, ast.Constant) and isinstance(element.value, str)
            }
    raise AssertionError("GET mutation guard has no action_fields set")


@pytest.mark.parametrize("field", sorted(_personal_http_action_fields()))
def test_every_configured_action_field_blocks_affirmative_get(field):
    from personal_http_auth import central_personal_http_get_mutation_block

    args = SimpleNamespace(
        getlist=lambda name: ["true"] if name == field else [],
        get=lambda name: "true" if name == field else None,
    )
    result = central_personal_http_get_mutation_block("GET", "/synthetic-read-route", args)

    assert result == {
        "ok": False,
        "status": "GET_MUTATION_REQUIRES_POST",
        "write_executed": False,
        "order_attempted": False,
        "no_order_sent": True,
    }


def test_real_flask_dispatch_authenticates_sensitive_and_unknown_paths(monkeypatch):
    monkeypatch.setenv("CENTRAL_PERSONAL_HTTP_USER", "local-operator")
    monkeypatch.setenv("CENTRAL_PERSONAL_HTTP_PASSWORD", "synthetic-only-password")
    app = _load_real_flask_auth_app()
    client = app.test_client()
    valid = _runtime_basic_header()

    missing = client.get("/livestatus")
    wrong = client.get(
        "/livestatus",
        headers={"Authorization": "Basic " + base64.b64encode(b"other:wrong").decode("ascii")},
    )
    allowed = client.get("/livestatus", headers={"Authorization": valid})
    unknown = client.get("/not-a-route")
    cross_site = client.get(
        "/livestatus",
        headers={"Authorization": valid, "Sec-Fetch-Site": "cross-site"},
    )

    assert missing.status_code == 401
    assert wrong.status_code == 401
    assert allowed.status_code == 200
    assert allowed.get_json() == {"ok": True, "data": "synthetic-only"}
    assert unknown.status_code == 401
    assert cross_site.status_code == 403
    assert b"cq-runtime" not in allowed.data


def test_render_healthz_is_minimal_public_liveness_only(monkeypatch):
    monkeypatch.setenv("CENTRAL_PERSONAL_HTTP_USER", "local-operator")
    monkeypatch.setenv("CENTRAL_PERSONAL_HTTP_PASSWORD", "synthetic-only-password")
    app = _load_real_flask_auth_app()
    client = app.test_client()

    live = client.get("/healthz")
    with_query = client.get("/healthz?detail=true")
    post = client.post("/healthz")
    cross_site = client.get("/healthz", headers={"Sec-Fetch-Site": "cross-site"})
    draining_app = _load_real_flask_auth_app(draining=True)
    draining = draining_app.test_client().get("/healthz")

    assert live.status_code == 200
    assert live.get_json() == {"ok": True, "status": "HTTP_LIVE"}
    assert with_query.status_code == 401
    assert post.status_code == 401
    assert cross_site.status_code == 403
    assert draining.status_code == 503
    assert draining.get_json() == {"ok": False, "status": "HTTP_DRAINING"}
    assert b"trading" not in live.data.lower()
    assert b"secret" not in live.data.lower()

    import personal_http_auth

    monkeypatch.setattr(
        personal_http_auth,
        "central_personal_http_auth_expected_passwords",
        lambda: (None, ()),
    )
    unconfigured = _load_real_flask_auth_app().test_client().get("/healthz")
    assert unconfigured.status_code == 200
    assert unconfigured.get_json() == {"ok": True, "status": "HTTP_LIVE"}


def test_runtime_routes_fail_closed_until_boot_completes(monkeypatch):
    monkeypatch.setenv("CENTRAL_PERSONAL_HTTP_USER", "local-operator")
    monkeypatch.setenv("CENTRAL_PERSONAL_HTTP_PASSWORD", "synthetic-only-password")
    app = _load_real_flask_auth_app(runtime_ready=False)
    client = app.test_client()
    valid = _runtime_basic_header()

    unauthorized = client.get("/livestatus")
    blocked = client.get("/livestatus", headers={"Authorization": valid})
    blocked_post = client.post("/registrymode", headers={"Authorization": valid})
    not_ready_probe = client.get("/healthz")

    assert unauthorized.status_code == 401
    assert blocked.status_code == 503
    assert blocked.get_json() == {"ok": False, "status": "CENTRAL_RUNTIME_NOT_READY"}
    assert blocked_post.status_code == 503
    assert blocked_post.get_json() == {"ok": False, "status": "CENTRAL_RUNTIME_NOT_READY"}
    assert app.test_mutations == []
    assert not_ready_probe.status_code == 503
    assert not_ready_probe.get_json() == {
        "ok": False,
        "status": "CENTRAL_RUNTIME_NOT_READY",
    }

    app._central_runtime_namespace["CENTRAL_RUNTIME_READY"] = True
    ready = client.get("/livestatus", headers={"Authorization": valid})
    ready_probe = client.get("/healthz")
    assert ready.status_code == 200
    assert ready_probe.status_code == 200
    assert ready_probe.get_json() == {"ok": True, "status": "HTTP_LIVE"}


def test_internal_bot_risk_requests_use_the_same_runtime_auth():
    expected_files = {
        "cobra.py",
        "donkey.py",
        "falcon.py",
        "meme.py",
        "predator.py",
        "trendpro.py",
        "turtle.py",
    }
    bots_dir = ROOT / "bots"
    authenticated_calls = {}
    for path in bots_dir.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if not isinstance(node.func.value, ast.Name) or node.func.value.id != "requests":
                continue
            if node.func.attr != "post":
                continue
            auth_kw = next((kw for kw in node.keywords if kw.arg == "auth"), None)
            if (
                auth_kw
                and isinstance(auth_kw.value, ast.Call)
                and isinstance(auth_kw.value.func, ast.Name)
                and auth_kw.value.func.id == "central_personal_http_auth"
            ):
                assert node.args
                assert auth_kw.value.args
                assert ast.dump(node.args[0], include_attributes=False) == ast.dump(
                    auth_kw.value.args[0], include_attributes=False
                ), f"{path.name}:{node.lineno} auth helper must guard the request target"
                authenticated_calls[path.name] = authenticated_calls.get(path.name, 0) + 1
    assert authenticated_calls == {name: 1 for name in expected_files}


def test_configured_http_credentials_are_used_without_disclosing_values(monkeypatch):
    import personal_http_auth

    monkeypatch.setenv("CENTRAL_PERSONAL_HTTP_USER", "synthetic-operator")
    monkeypatch.setenv("CENTRAL_PERSONAL_HTTP_PASSWORD", "synthetic-only-password")

    username, passwords = personal_http_auth.central_personal_http_auth_expected_passwords()

    assert username == "synthetic-operator"
    assert passwords == ("synthetic-only-password",)

    app = _load_real_flask_auth_app()
    client = app.test_client()
    unauthorized = client.get("/livestatus")
    encoded = base64.b64encode(
        b"synthetic-operator:synthetic-only-password"
    ).decode("ascii")
    authorized = client.get(
        "/livestatus", headers={"Authorization": "Basic " + encoded}
    )
    assert unauthorized.status_code == 401
    assert authorized.status_code == 200
    assert b"synthetic-operator" not in authorized.data
    assert b"synthetic-only-password" not in authorized.data


def test_runtime_auth_source_uses_only_configured_or_process_local_credentials():
    source = SOURCE.read_text(encoding="utf-8")
    helper_source = (ROOT / "personal_http_auth.py").read_text(encoding="utf-8")

    assert "CENTRAL_PERSONAL_HTTP_USER" not in source
    assert "CENTRAL_PERSONAL_HTTP_PASSWORD" not in source
    assert 'os.environ.get("CENTRAL_PERSONAL_HTTP_USER")' in helper_source
    assert 'os.environ.get("CENTRAL_PERSONAL_HTTP_PASSWORD")' in helper_source
    assert "print(configured_password)" not in helper_source


def test_bot_auth_helper_returns_short_lived_tuple_only_for_own_origin(monkeypatch):
    from personal_http_auth import central_personal_http_auth

    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://central.example.test")
    monkeypatch.setenv("PORT", "10000")
    credentials = central_personal_http_auth("https://central.example.test/can_open_trade")
    assert credentials is not None
    assert credentials[0] == "cq-runtime"
    assert len(credentials[1]) == 64
    assert central_personal_http_auth("https://attacker.example/can_open_trade") is None


def test_bot_auth_helper_never_sends_credentials_to_untrusted_or_plain_http_hosts(monkeypatch):
    from personal_http_auth import central_personal_http_auth

    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://central.example.test")
    monkeypatch.setenv("PORT", "10000")

    assert central_personal_http_auth("https://attacker.example/can_open_trade") is None
    assert central_personal_http_auth("http://central.example.test/can_open_trade") is None
    assert central_personal_http_auth("http://localhost:9999/can_open_trade") is None
    credentials = central_personal_http_auth("http://127.0.0.1:10000/can_open_trade")
    assert credentials is not None
    assert credentials[0] == "cq-runtime"
    assert len(credentials[1]) == 64


@pytest.mark.parametrize("port", ["invalid", "", "-1"])
def test_bot_auth_helper_fails_closed_for_invalid_local_port(monkeypatch, port):
    from personal_http_auth import central_personal_http_auth

    monkeypatch.delenv("RENDER_EXTERNAL_URL", raising=False)
    monkeypatch.setenv("PORT", port)

    assert central_personal_http_auth("http://127.0.0.1:10000/can_open_trade") is None
