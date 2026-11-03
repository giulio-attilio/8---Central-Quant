from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

from auto_real_execution_bridge_route_v1 import (
    dispatch_auto_real_execution_bridge_route_v1,
)


ROOT = Path(__file__).resolve().parents[1]


class _Request:
    def __init__(self, method="GET", args=None, body=None):
        self.method = method
        self.args = dict(args or {})
        self._body = body

    def get_json(self, silent=False):
        return self._body


def _run(request, *, auth=None):
    calls = []

    def processor(**kwargs):
        calls.append(kwargs)
        return {"ok": True, "synthetic": True, "execute": kwargs["execute"]}

    def auth_guard():
        return auth if auth is not None else {"ok": False, "status": "EXECUTION_AUTH_REQUIRED"}

    result = dispatch_auto_real_execution_bridge_route_v1(
        request,
        processor,
        lambda value, manual_defaults: dict(value),
        lambda value, default=False: str(value).lower() in {"1", "true", "yes"} if value is not None else default,
        lambda value: value,
        auth_guard,
    )
    return result, calls


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch):
    import socket
    import urllib.request

    def blocked(*_args, **_kwargs):
        raise AssertionError("network access is forbidden in this route test")

    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(urllib.request, "urlopen", blocked)


def test_get_with_live_action_fields_is_rejected_without_processor_call():
    result, calls = _run(
        _Request(
            "GET",
            {
                "execute": "true",
                "commit": "true",
                "ack": "AUTO_REAL_EXECUTE",
            },
        )
    )

    assert result[1] == 405
    assert result[0]["status"] == "LIVE_ACTION_REQUIRES_AUTHENTICATED_POST"
    assert result[0]["no_order_sent"] is True
    assert calls == []


def test_get_without_action_fields_is_preview_only():
    result, calls = _run(_Request("GET", {"symbol": "BTCUSDT", "side": "LONG"}))

    assert result[1] == 200
    assert len(calls) == 1
    assert calls[0]["execute"] is False
    assert calls[0]["dry_run"] is True
    assert calls[0]["source"] == "manual_route_preview"


def test_post_live_action_requires_execution_authentication():
    result, calls = _run(
        _Request(
            "POST",
            body={"execute": True, "commit": True, "ack": "AUTO_REAL_EXECUTE"},
        )
    )

    assert result[1] == 403
    assert result[0]["status"] == "EXECUTION_AUTH_REQUIRED"
    assert calls == []


@pytest.mark.parametrize(
    "body",
    [
        {"execute": True, "commit": False, "ack": "AUTO_REAL_EXECUTE"},
        {"execute": True, "commit": True, "ack": "WRONG"},
        {"execute": False, "commit": True, "ack": "AUTO_REAL_EXECUTE"},
    ],
)
def test_post_rejects_incomplete_or_wrong_live_confirmation(body):
    result, calls = _run(_Request("POST", body=body), auth={"ok": True})

    assert result[1] == 400
    assert result[0]["status"] == "LIVE_ACTION_CONFIRMATION_INVALID"
    assert calls == []


def test_post_rejects_query_parameters_even_when_authenticated():
    result, calls = _run(
        _Request(
            "POST",
            args={"execute": "true"},
            body={"execute": True, "commit": True, "ack": "AUTO_REAL_EXECUTE"},
        ),
        auth={"ok": True},
    )

    assert result[1] == 400
    assert result[0]["status"] == "POST_QUERY_PARAMETERS_NOT_ALLOWED"
    assert calls == []


def test_authenticated_post_with_exact_live_confirmation_is_still_refused():
    result, calls = _run(
        _Request(
            "POST",
            body={"execute": True, "commit": True, "ack": "AUTO_REAL_EXECUTE"},
        ),
        auth={"ok": True},
    )

    assert result[1] == 403
    assert result[0]["status"] == "LIVE_EXECUTION_DISABLED_BY_SAFETY_POLICY"
    assert result[0]["order_attempted"] is False
    assert result[0]["no_order_sent"] is True
    assert calls == []


def test_flask_route_delegates_live_action_to_authenticated_dispatcher():
    tree = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))
    route = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "auto_real_execution_bridge_v1_route"
    )
    decorators = [ast.unparse(node) for node in route.decorator_list]
    source = ast.unparse(route)

    assert any("methods=['GET', 'POST']" in item for item in decorators)
    assert "dispatch_auto_real_execution_bridge_route_v1" in source
    assert "_rtlm_v15_admin_auth" in source
