from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
TREE = ast.parse(MAIN.read_text(encoding="utf-8"), filename=str(MAIN))
_ROUTE = next(
    node
    for node in TREE.body
    if isinstance(node, ast.FunctionDef)
    and node.name == "execution_engine_run_route"
)
_ROUTE.decorator_list = []
_NAMESPACE = {"request": None}
exec(
    compile(ast.Module(body=[_ROUTE], type_ignores=[]), str(MAIN), "exec"),
    _NAMESPACE,
)
_ROUTE_FUNCTION = _NAMESPACE["execution_engine_run_route"]


class _Args(dict):
    def get(self, key, default=None):
        return super().get(key, default)


def _call_route(*, method, payload=None, args=None):
    _NAMESPACE["request"] = SimpleNamespace(
        method=method,
        get_json=lambda silent=True: payload,
        args=_Args(args or {}),
    )
    return _ROUTE_FUNCTION()


@pytest.mark.parametrize(
    ("method", "payload", "args"),
    [
        ("POST", None, {}),
        ("POST", {}, {}),
        ("POST", [], {}),
        ("POST", [{"symbol": "BTCUSDT"}], {}),
        ("GET", None, {}),
    ],
)
def test_empty_or_non_object_execution_payload_is_rejected_without_execution(
    method, payload, args
):
    response, status = _call_route(method=method, payload=payload, args=args)

    assert status == 400
    assert response == {
        "ok": False,
        "mode": "OBSERVATION_ONLY",
        "dry_run": True,
        "decision": "DENY",
        "allowed": False,
        "status": "EXECUTION_PAYLOAD_REQUIRED",
        "sent": False,
        "send_attempted": False,
        "paper_executor_called": False,
        "no_order_sent": True,
    }
