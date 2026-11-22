"""Fail-closed authorization for personal Telegram command handlers."""

import os


def telegram_command_authorized(message, configured_chat_id, owner_env_names=()):
    """Allow only the configured chat and its explicitly authorized owner.

    Without an owner setting, only a private chat whose positive chat ID
    equals the sender ID is accepted. Group commands require an owner ID.
    """
    if not isinstance(message, dict) or message.get("sender_chat"):
        return False
    chat = message.get("chat")
    sender = message.get("from")
    if not isinstance(chat, dict) or not isinstance(sender, dict):
        return False
    if sender.get("is_bot") is True:
        return False

    try:
        expected_chat_id = int(str(configured_chat_id or "").strip())
        incoming_chat_id = int(str(chat.get("id") or "").strip())
        sender_id = int(str(sender.get("id") or "").strip())
    except (TypeError, ValueError):
        return False
    if expected_chat_id == 0:
        return False
    if incoming_chat_id != expected_chat_id or sender_id <= 0:
        return False

    owner_value = ""
    for name in owner_env_names:
        owner_value = str(os.environ.get(name) or "").strip()
        if owner_value:
            break
    if owner_value:
        try:
            owner_id = int(owner_value)
        except ValueError:
            return False
        return owner_id > 0 and sender_id == owner_id

    return (
        chat.get("type") == "private"
        and expected_chat_id > 0
        and sender_id == expected_chat_id
    )
