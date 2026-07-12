import json
import os
import socket
from pathlib import Path
from unittest import mock

import requests


def _network_forbidden(*args, **kwargs):
    raise AssertionError("network access attempted during Shadow HTTP tests")


# Install the firewall before importing main.py and keep it active for the suite.
_request_patch = mock.patch.object(requests.sessions.Session, "request", _network_forbidden)
_connection_patch = mock.patch.object(socket, "create_connection", _network_forbidden)
_request_patch.start()
_connection_patch.start()

import main as central_main  # noqa: E402


AUTHORITIES = (
    "operational_authority", "broker_access", "registry_write_access",
    "lifecycle_write_access", "execution_control", "automatic_repair",
)
ROUTES = (
    "/shadowhealth", "/shadowmetrics", "/shadowevents",
    "/shadowdivergences", "/shadowreconciliation",
)


def payload(status="OK", **extra):
    return {
        "schema_version": "1.0", "ok": status != "UNAVAILABLE", "status": status,
        "module": "trade_lifecycle_shadow_observability", "mode": "SHADOW",
        **{key: False for key in AUTHORITIES}, **extra,
    }


def get(client, route):
    response = client.get(route)
    return response, response.get_json()


@mock.patch.object(central_main, "shadow_observability_get_health")
def test_shadowhealth_status_mapping(provider):
    with central_main.app.test_client() as client:
        for status, expected in (("OK", 200), ("DEGRADED", 200), ("DISABLED", 200), ("UNAVAILABLE", 503)):
            provider.return_value = payload(status, enabled=status != "DISABLED")
            response, body = get(client, "/shadowhealth")
            assert response.status_code == expected and body["status"] == status


@mock.patch.object(central_main, "shadow_observability_get_metrics")
def test_shadowmetrics_status_mapping(provider):
    with central_main.app.test_client() as client:
        for status, expected in (("OK", 200), ("PARTIAL", 200), ("DISABLED", 200), ("UNAVAILABLE", 503)):
            provider.return_value = payload(status)
            response, body = get(client, "/shadowmetrics")
            assert response.status_code == expected and body["status"] == status


@mock.patch.object(central_main, "shadow_observability_list_events")
def test_shadowevents_without_filters_and_valid_limit(provider):
    provider.return_value = payload("OK", items=[])
    with central_main.app.test_client() as client:
        assert client.get("/shadowevents").status_code == 200
        provider.assert_called_with(filters={}, limit=50, cursor=None)
        assert client.get("/shadowevents?limit=17").status_code == 200
        provider.assert_called_with(filters={}, limit=17, cursor=None)


@mock.patch.object(central_main, "shadow_observability_list_events")
def test_shadowevents_forwards_all_allowed_filters_and_opaque_cursor(provider):
    provider.return_value = payload("PARTIAL", items=[])
    query = {
        "lifecycle_id": "LC", "trade_id": "TR", "event_id": "EV", "bot": "FALCON",
        "setup": "ORB", "symbol": "BTCUSDT", "side": "LONG", "event_type": "ENTRY_CONFIRMED",
        "status": "APPLIED", "date_from": "2026-01-01T00:00:00+00:00",
        "date_to": "2026-01-02T00:00:00+00:00", "limit": "25", "cursor": "opaque-value",
    }
    with central_main.app.test_client() as client:
        response = client.get("/shadowevents", query_string=query)
    assert response.status_code == 200
    provider.assert_called_once_with(
        filters={key: value for key, value in query.items() if key not in {"limit", "cursor"}},
        limit=25, cursor="opaque-value",
    )


@mock.patch.object(central_main, "shadow_observability_list_events")
def test_shadowevents_module_error_mapping(provider):
    with central_main.app.test_client() as client:
        for status, expected in (("INVALID_FILTER", 400), ("INVALID_LIMIT", 400), ("INVALID_CURSOR", 400), ("CURSOR_STALE", 409), ("UNAVAILABLE", 503), ("PAYLOAD_TOO_LARGE", 413)):
            provider.return_value = payload(status)
            assert client.get("/shadowevents").status_code == expected


@mock.patch.object(central_main, "shadow_observability_list_events")
def test_shadowevents_rejects_invalid_limit_and_unknown_or_dangerous_parameters(provider):
    with central_main.app.test_client() as client:
        assert client.get("/shadowevents?limit=nope").status_code == 400
        for key in ("unknown", "path", "file", "filename", "offset", "persist", "repair", "replay", "reconcile", "refresh", "commit"):
            response = client.get("/shadowevents", query_string={key: "x"})
            assert response.status_code == 400
            assert response.get_json()["status"] == "INVALID_FILTER"
    provider.assert_not_called()


@mock.patch.object(central_main, "shadow_observability_list_events")
def test_shadowevents_does_not_read_or_execute_json_body(provider):
    provider.return_value = payload("OK", items=[])
    with central_main.app.test_client() as client:
        response = client.get("/shadowevents", json={"repair": True, "path": "C:/secret"})
    assert response.status_code == 200
    provider.assert_called_once_with(filters={}, limit=50, cursor=None)


@mock.patch.object(central_main, "shadow_observability_list_divergences")
def test_shadowdivergences_filters_resolved_and_cursor(provider):
    provider.return_value = payload("PARTIAL", items=[])
    query = {
        "lifecycle_id": "LC", "trade_id": "TR", "field": "state", "severity": "HIGH",
        "resolved": "null", "category": "FIELD_MISMATCH",
        "date_from": "2026-01-01T00:00:00+00:00", "date_to": "2026-01-02T00:00:00+00:00",
        "limit": "30", "cursor": "opaque",
    }
    with central_main.app.test_client() as client:
        assert client.get("/shadowdivergences").status_code == 200
        response = client.get("/shadowdivergences", query_string=query)
        assert response.status_code == 200
        for resolved in ("true", "false", "null"):
            assert client.get("/shadowdivergences", query_string={"resolved": resolved}).status_code == 200
    assert provider.call_args_list[1].kwargs == {
        "filters": {key: value for key, value in query.items() if key not in {"limit", "cursor"}},
        "limit": 30, "cursor": "opaque",
    }


@mock.patch.object(central_main, "shadow_observability_list_divergences")
def test_shadowdivergences_rejects_unknown_filter(provider):
    with central_main.app.test_client() as client:
        response = client.get("/shadowdivergences?path=x")
    assert response.status_code == 400
    assert response.get_json()["status"] == "INVALID_FILTER"
    provider.assert_not_called()


def test_parameterless_endpoints_reject_query_parameters():
    with central_main.app.test_client() as client:
        for route in ("/shadowhealth", "/shadowmetrics", "/shadowreconciliation"):
            response = client.get(route + "?path=x")
            assert response.status_code == 400
            assert response.get_json()["status"] == "INVALID_FILTER"


@mock.patch.object(central_main, "shadow_observability_get_reconciliation_summary")
def test_shadowreconciliation_status_mapping(provider):
    with central_main.app.test_client() as client:
        for status, expected in (("NO_EVIDENCE", 200), ("DIVERGENCE", 200), ("PARTIAL", 200), ("UNKNOWN", 200), ("DISABLED", 200), ("UNAVAILABLE", 503)):
            provider.return_value = payload(status)
            response, body = get(client, "/shadowreconciliation")
            assert response.status_code == expected and body["status"] == status


def test_non_get_methods_are_automatically_rejected():
    with central_main.app.test_client() as client:
        for route in ROUTES:
            for method in (client.post, client.put, client.patch, client.delete):
                assert method(route, json={"command": "repair"}).status_code == 405


@mock.patch.object(central_main, "shadow_observability_get_health", side_effect=RuntimeError("C:/secret/path token=abc"))
def test_exception_is_structured_sanitized_and_does_not_break_other_routes(provider):
    with central_main.app.test_client() as client:
        response, body = get(client, "/shadowhealth")
        assert response.status_code == 500
        assert body["status"] == "INTEGRATION_ERROR"
        assert "secret" not in json.dumps(body).lower()
        assert client.get("/").status_code == 200
    provider.assert_called_once_with()


@mock.patch.object(central_main, "shadow_observability_get_health", return_value="malformed")
def test_malformed_contract_is_structured(provider):
    with central_main.app.test_client() as client:
        response, body = get(client, "/shadowhealth")
    assert response.status_code == 500
    assert body["schema_version"] == "1.0"
    assert all(body[key] is False for key in AUTHORITIES)


@mock.patch.object(central_main, "shadow_observability_list_events")
def test_authorities_schema_and_external_position_are_preserved(provider):
    provider.return_value = payload("OK", items=[{"external_position": True, "bot": None, "setup": None}])
    with central_main.app.test_client() as client:
        response, body = get(client, "/shadowevents")
    assert response.status_code == 200 and body["schema_version"] == "1.0"
    assert all(body[key] is False for key in AUTHORITIES)
    assert body["items"][0]["bot"] is None


def test_import_guard_unavailable_is_fail_open(monkeypatch):
    monkeypatch.setattr(central_main, "SHADOW_OBSERVABILITY_HTTP_IMPORT_OK", False)
    with central_main.app.test_client() as client:
        response, body = get(client, "/shadowhealth")
    assert response.status_code == 503 and body["status"] == "UNAVAILABLE"


def test_endpoints_do_not_change_trading_environment(monkeypatch):
    monkeypatch.setenv("ENABLE_REAL_TRADING", "sentinel-real")
    monkeypatch.setenv("BROKER_DRY_RUN", "sentinel-dry")
    with mock.patch.object(central_main, "shadow_observability_get_health", return_value=payload("OK")):
        with central_main.app.test_client() as client:
            assert client.get("/shadowhealth").status_code == 200
    assert os.environ["ENABLE_REAL_TRADING"] == "sentinel-real"
    assert os.environ["BROKER_DRY_RUN"] == "sentinel-dry"


def test_shadow_http_source_has_no_mutable_or_operational_calls():
    source = Path(central_main.__file__).read_text(encoding="utf-8")
    section = source.split("TRADE LIFECYCLE SHADOW OBSERVABILITY V1 — HTTP READ-ONLY", 1)[1].split("MEMORY STABILIZER HELPERS", 1)[0]
    for forbidden in (
        "reconcile_all", "reconcile_trade", "compare_with_registry", "central_broker",
        "trade_registry", "request.get_json", "request.data", "request.body",
        "requests.", "socket.", "open(", "write_text", "write_bytes", "mkdir", "os.replace",
    ):
        assert forbidden not in section
    assert "cursor=" not in section or "shadow_observability_list" in section


def test_shadow_endpoints_create_or_modify_no_files(tmp_path):
    before = list(tmp_path.iterdir())
    fakes = {
        "shadow_observability_get_health": lambda: payload("OK"),
        "shadow_observability_get_metrics": lambda: payload("OK"),
        "shadow_observability_list_events": lambda **kwargs: payload("OK", items=[]),
        "shadow_observability_list_divergences": lambda **kwargs: payload("OK", items=[]),
        "shadow_observability_get_reconciliation_summary": lambda: payload("NO_EVIDENCE"),
    }
    with mock.patch.multiple(central_main, **fakes):
        with central_main.app.test_client() as client:
            for route in ROUTES:
                assert client.get(route).status_code == 200
    assert list(tmp_path.iterdir()) == before == []


def test_routes_are_registered_and_existing_home_still_works():
    rules = {rule.rule: rule.methods for rule in central_main.app.url_map.iter_rules()}
    for route in ROUTES:
        assert route in rules and "GET" in rules[route] and "POST" not in rules[route]
    with central_main.app.test_client() as client:
        assert client.get("/").status_code == 200
