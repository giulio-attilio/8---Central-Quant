from __future__ import annotations

import ast
from pathlib import Path

from telegram_command_auth_v1 import telegram_command_authorized


ROOT = Path(__file__).resolve().parents[1]


def _message(chat_id, chat_type, sender_id, **sender_fields):
    return {
        "chat": {"id": chat_id, "type": chat_type},
        "from": {"id": sender_id, **sender_fields},
    }


def test_private_chat_only_allows_configured_owner_without_extra_env(monkeypatch):
    monkeypatch.delenv("CENTRAL_TELEGRAM_OWNER_USER_ID", raising=False)
    assert telegram_command_authorized(
        _message(123, "private", 123), "123", ("CENTRAL_TELEGRAM_OWNER_USER_ID",)
    )
    assert not telegram_command_authorized(
        _message(123, "private", 456), "123", ("CENTRAL_TELEGRAM_OWNER_USER_ID",)
    )


def test_group_requires_explicit_positive_owner_id(monkeypatch):
    message = _message(-1001, "group", 456)
    monkeypatch.delenv("CENTRAL_TELEGRAM_OWNER_USER_ID", raising=False)
    assert not telegram_command_authorized(
        message, "-1001", ("CENTRAL_TELEGRAM_OWNER_USER_ID",)
    )
    monkeypatch.setenv("CENTRAL_TELEGRAM_OWNER_USER_ID", "456")
    assert telegram_command_authorized(
        message, "-1001", ("CENTRAL_TELEGRAM_OWNER_USER_ID",)
    )
    monkeypatch.setenv("CENTRAL_TELEGRAM_OWNER_USER_ID", "bad")
    assert not telegram_command_authorized(
        message, "-1001", ("CENTRAL_TELEGRAM_OWNER_USER_ID",)
    )


def test_rejects_wrong_chat_bot_sender_and_anonymous_admin(monkeypatch):
    monkeypatch.setenv("CENTRAL_TELEGRAM_OWNER_USER_ID", "456")
    assert not telegram_command_authorized(
        _message(-1002, "group", 456), "-1001", ("CENTRAL_TELEGRAM_OWNER_USER_ID",)
    )
    assert not telegram_command_authorized(
        _message(-1001, "group", 456, is_bot=True),
        "-1001",
        ("CENTRAL_TELEGRAM_OWNER_USER_ID",),
    )
    anonymous = _message(-1001, "group", 456)
    anonymous["sender_chat"] = {"id": -1001}
    assert not telegram_command_authorized(
        anonymous, "-1001", ("CENTRAL_TELEGRAM_OWNER_USER_ID",)
    )


def test_missing_identity_or_unconfigured_chat_fails_closed():
    assert not telegram_command_authorized({}, "123")
    assert not telegram_command_authorized(_message(123, "private", 123), "")
    assert not telegram_command_authorized(_message(0, "private", 1), "0")


def test_each_loaded_bot_command_listener_checks_owner_before_dispatch():
    listeners = {
        "cobra.py": ("listen_commands",),
        "donkey.py": ("listen_commands", "listen_donkey_commands"),
        "meme.py": ("listen_commands",),
        "predator.py": ("listen_commands",),
        "trendpro.py": ("listen_commands", "listen_donkey_commands"),
    }
    for filename, function_names in listeners.items():
        tree = ast.parse((ROOT / "bots" / filename).read_text(encoding="utf-8"))
        functions = {
            node.name: node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        for function_name in function_names:
            function = functions[function_name]
            calls = [
                node
                for node in ast.walk(function)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "telegram_command_authorized"
            ]
            assert len(calls) == 1, f"{filename}:{function_name} missing unique guard"
            dispatch_lines = [
                node.lineno
                for node in ast.walk(function)
                if isinstance(node, ast.If)
                and any(
                    isinstance(child, ast.Constant)
                    and isinstance(child.value, str)
                    and child.value.startswith("/")
                    for child in ast.walk(node.test)
                )
            ]
            if dispatch_lines:
                assert calls[0].lineno < min(dispatch_lines)
