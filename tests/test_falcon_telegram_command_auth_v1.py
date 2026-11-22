from __future__ import annotations

import ast
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest


SOURCE = Path(__file__).resolve().parents[1] / "bots" / "falcon.py"


def _load_command_functions(*, chat_id, monkeypatch):
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    wanted = {"_falcon_telegram_command_authorized", "commands_loop"}
    nodes = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in wanted
    ]
    assert {node.name for node in nodes} == wanted
    module = ast.Module(body=nodes, type_ignores=[])
    ast.fix_missing_locations(module)

    monkeypatch.delenv("FALCON_TELEGRAM_OWNER_USER_ID", raising=False)
    monkeypatch.delenv("CENTRAL_TELEGRAM_OWNER_USER_ID", raising=False)
    from telegram_command_auth_v1 import telegram_command_authorized

    namespace = {
        "os": os,
        "json": json,
        "CHAT_ID": chat_id,
        "telegram_command_authorized": telegram_command_authorized,
    }
    exec(compile(module, str(SOURCE), "exec"), namespace)
    return namespace


def _update(*, chat_id, sender_id, text="/reset_falcon_all", is_bot=False):
    return {
        "update_id": 1,
        "message": {
            "chat": {
                "id": chat_id,
                "type": "private" if int(chat_id) > 0 else "group",
            },
            "from": {"id": sender_id, "is_bot": is_bot},
            "text": text,
        },
    }


@pytest.mark.parametrize(
    "message,chat_id,configured_chat,owner_env,authorized",
    [
        ({"chat": {"id": 123, "type": "private"}, "from": {"id": 123}}, 123, "123", None, True),
        ({"chat": {"id": -1001, "type": "group"}, "from": {"id": 456}}, -1001, "-1001", "456", True),
        ({"chat": {"id": -1001, "type": "group"}, "from": {"id": 456}}, -1001, "-1001", None, False),
        ({"chat": {"id": 123, "type": "private"}, "from": {"id": 999}}, 123, "123", None, False),
        ({"chat": {"id": 123, "type": "private"}, "from": {"id": 123, "is_bot": True}}, 123, "123", None, False),
        ({"chat": {"id": 123, "type": "private"}, "from": {"id": 123}}, 123, "", None, False),
    ],
)
def test_telegram_command_authorization_is_private_owner_or_explicit_group_owner(
    message, chat_id, configured_chat, owner_env, authorized, monkeypatch
):
    namespace = _load_command_functions(
        chat_id=configured_chat, monkeypatch=monkeypatch
    )
    if owner_env is not None:
        monkeypatch.setenv("FALCON_TELEGRAM_OWNER_USER_ID", owner_env)

    assert namespace["_falcon_telegram_command_authorized"](
        message, chat_id
    ) is authorized


class _StopLoop(Exception):
    pass


@pytest.mark.parametrize("authorized", [False, True])
def test_reset_all_command_never_clears_persisted_positions_or_history(
    authorized, monkeypatch
):
    configured_chat = 123
    sender_id = configured_chat if authorized else 456
    namespace = _load_command_functions(
        chat_id=configured_chat, monkeypatch=monkeypatch
    )
    updates = [_update(chat_id=configured_chat, sender_id=sender_id)]
    writes = []
    replies = []

    def stop_after_one_batch(_seconds):
        raise _StopLoop

    namespace.update(
        {
            "HEALTH": {},
            "telegram_get_updates": lambda _offset=None: updates,
            "telegram_reply": lambda *args: replies.append(args),
            "redis_set_json": lambda *args: writes.append(args),
            "health_payload": lambda: {},
            "positions_text": lambda: "positions",
            "build_summary": lambda *_args: "summary",
            "trades_today": lambda: [],
            "funnel_text": lambda: "funnel",
            "events_text": lambda: "events",
            "load_watchlist": lambda: [],
            "data_hora_sp_str": lambda: "synthetic-time",
            "time": SimpleNamespace(sleep=stop_after_one_batch),
            "FUNNEL_KEY": "funnel",
            "LAST_CANDLES_KEY": "candles",
            "POSITIONS_KEY": "positions",
            "SIGNALS_KEY": "signals",
            "TRADES_KEY": "trades",
            "EVENTS_KEY": "events",
            "COMMAND_SLEEP_SECONDS": 1,
        }
    )

    with pytest.raises(_StopLoop):
        namespace["commands_loop"]()

    assert writes == []
    if authorized:
        assert len(replies) == 1
        assert "desativado" in replies[0][1]
    else:
        assert replies == []


@pytest.mark.parametrize("authorized", [False, True])
def test_operational_reset_never_clears_positions_or_trade_history(
    authorized, monkeypatch
):
    configured_chat = 123
    sender_id = configured_chat if authorized else 456
    namespace = _load_command_functions(
        chat_id=configured_chat, monkeypatch=monkeypatch
    )
    updates = [
        _update(chat_id=configured_chat, sender_id=sender_id, text="/reset")
    ]
    writes = []
    replies = []

    def stop_after_one_batch(_seconds):
        raise _StopLoop

    namespace.update(
        {
            "HEALTH": {},
            "telegram_get_updates": lambda _offset=None: updates,
            "telegram_reply": lambda *args: replies.append(args),
            "redis_set_json": lambda *args: writes.append(args),
            "health_payload": lambda: {},
            "positions_text": lambda: "positions",
            "build_summary": lambda *_args: "summary",
            "trades_today": lambda: [],
            "funnel_text": lambda: "funnel",
            "events_text": lambda: "events",
            "load_watchlist": lambda: [],
            "data_hora_sp_str": lambda: "synthetic-time",
            "time": SimpleNamespace(sleep=stop_after_one_batch),
            "COMMAND_SLEEP_SECONDS": 1,
            "FUNNEL_KEY": "funnel",
            "LAST_CANDLES_KEY": "candles",
        }
    )

    with pytest.raises(_StopLoop):
        namespace["commands_loop"]()

    if authorized:
        assert [key for key, _value in writes] == ["funnel", "candles"]
        assert len(replies) == 1
        assert "NÃO foram apagados" in replies[0][1]
    else:
        assert writes == []
        assert replies == []
