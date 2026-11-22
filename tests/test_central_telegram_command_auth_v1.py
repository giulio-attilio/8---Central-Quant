from __future__ import annotations

import ast
from pathlib import Path

from telegram_command_auth_v1 import telegram_command_authorized


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


def _load_authorization_helper(monkeypatch):
    tree = ast.parse(MAIN.read_text(encoding="utf-8"))
    node = next(
        item
        for item in tree.body
        if isinstance(item, ast.FunctionDef)
        and item.name == "_central_telegram_command_authorized"
    )
    module = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {
        "telegram_command_authorized": telegram_command_authorized,
    }
    exec(compile(module, str(MAIN), "exec"), namespace)
    monkeypatch.delenv("CENTRAL_TELEGRAM_OWNER_USER_ID", raising=False)
    monkeypatch.delenv("FALCON_TELEGRAM_OWNER_USER_ID", raising=False)
    return namespace["_central_telegram_command_authorized"]


def test_central_private_commands_require_matching_configured_chat_and_sender(monkeypatch):
    authorize = _load_authorization_helper(monkeypatch)
    message = {
        "chat": {"id": 1234, "type": "private"},
        "from": {"id": 1234, "is_bot": False},
        "text": "/status",
    }
    assert authorize(message, "1234")
    assert not authorize(message, "5678")
    message["from"]["id"] = 9999
    assert not authorize(message, "1234")


def test_bot_group_commands_require_explicit_bot_owner_or_central_owner(monkeypatch):
    authorize = _load_authorization_helper(monkeypatch)
    message = {
        "chat": {"id": -1001, "type": "group"},
        "from": {"id": 456, "is_bot": False},
        "text": "/status",
    }
    assert not authorize(message, "-1001", "FALCON")
    monkeypatch.setenv("FALCON_TELEGRAM_OWNER_USER_ID", "456")
    assert authorize(message, "-1001", "FALCON")
    monkeypatch.setenv("FALCON_TELEGRAM_OWNER_USER_ID", "bad")
    assert not authorize(message, "-1001", "FALCON")


def test_both_central_routers_authorize_before_command_dispatch():
    tree = ast.parse(MAIN.read_text(encoding="utf-8"))
    functions = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
    }
    expected = {
        "central_telegram_command_loop": "build_central_command_reply",
        "central_command_router_loop": "build_command_reply_for_module",
    }
    for name, dispatch_name in expected.items():
        function = functions[name]
        auth_calls = [
            node
            for node in ast.walk(function)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_central_telegram_command_authorized"
        ]
        dispatch_calls = [
            node
            for node in ast.walk(function)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == dispatch_name
        ]
        assert len(auth_calls) == 1, name
        assert dispatch_calls, name
        assert auth_calls[0].lineno < min(node.lineno for node in dispatch_calls), name


def test_auth_helper_is_imported_by_production_entrypoint():
    tree = ast.parse(MAIN.read_text(encoding="utf-8"))
    assert any(
        isinstance(node, ast.ImportFrom)
        and node.module == "telegram_command_auth_v1"
        and any(alias.name == "telegram_command_authorized" for alias in node.names)
        for node in tree.body
    )
