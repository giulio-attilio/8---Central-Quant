"""Compatibility facade for Falcon account-wide ``clientOrderID`` values.

Falcon historically exposed a small role-aware generator with ``revision``
and ``attempt`` arguments.  BingX, however, applies client-order identity to
the whole account for its complete lifetime.  The account authority in
``account_client_order_id`` is therefore the sole generator used here.

This module intentionally retains the Falcon public API so existing callers
can migrate without creating a second identity domain.  It performs no I/O and
does not import Falcon, Broker, Redis, or another operational component.
"""

from __future__ import annotations

import hashlib
from typing import Any

from account_client_order_id import (
    ACCOUNT_CLIENT_ORDER_ID_GENERATOR_VERSION,
    ACCOUNT_CLIENT_ORDER_ID_HASH_HEX_LENGTH,
    ACCOUNT_CLIENT_ORDER_ID_MAX_LENGTH,
    ACCOUNT_CLIENT_ORDER_ID_NAMESPACE,
    ACCOUNT_CLIENT_ORDER_ID_ROLE_NAMESPACES,
    ROLE_BREAK_EVEN_STOP,
    ROLE_EMERGENCY_TERMINAL_STOP_CLOSE,
    ROLE_ENTRY,
    ROLE_INITIAL_DISASTER_STOP,
    ROLE_MANAGED_CLOSE,
    ROLE_REPLACEMENT_STOP,
    ROLE_ROLLBACK_STOP,
    ROLE_TP50_CLOSE,
    ROLE_TRAILING_STOP,
    build_canonical_operation_id,
    canonical_account_order_attempt_identity,
    canonical_account_order_attempt_identity_hash,
    canonical_account_order_attempt_identity_json,
    generate_account_client_order_id,
    is_valid_account_client_order_id,
)


# Backwards-compatible Falcon names now point at the account-wide contract.
FALCON_CLIENT_ORDER_ID_GENERATOR_VERSION = (
    ACCOUNT_CLIENT_ORDER_ID_GENERATOR_VERSION
)
FALCON_CLIENT_ORDER_ID_MAX_LENGTH = ACCOUNT_CLIENT_ORDER_ID_MAX_LENGTH
FALCON_CLIENT_ORDER_ID_HASH_HEX_LENGTH = (
    ACCOUNT_CLIENT_ORDER_ID_HASH_HEX_LENGTH
)
FALCON_CLIENT_ORDER_ID_ACCOUNT_NAMESPACE = ACCOUNT_CLIENT_ORDER_ID_NAMESPACE
FALCON_CLIENT_ORDER_ID_ROLE_NAMESPACES = (
    ACCOUNT_CLIENT_ORDER_ID_ROLE_NAMESPACES
)

_DERIVED_ORDER_ROLES = frozenset(
    role
    for role in FALCON_CLIENT_ORDER_ID_ROLE_NAMESPACES
    if role != ROLE_ENTRY
)
_STOP_ORDER_ROLES = frozenset(
    {
        ROLE_INITIAL_DISASTER_STOP,
        ROLE_REPLACEMENT_STOP,
        ROLE_ROLLBACK_STOP,
        ROLE_BREAK_EVEN_STOP,
        ROLE_TRAILING_STOP,
    }
)


def _sequence(name: str, value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a non-negative integer")
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a non-negative integer") from exc
    if normalized < 0 or str(value).strip() not in {
        str(normalized),
        f"+{normalized}",
    }:
        raise ValueError(f"{name} must be a non-negative integer")
    return normalized


def _falcon_order_type(role: str, explicit: Any = None) -> str:
    if explicit not in (None, ""):
        return str(explicit).strip().upper()
    return "STOP_MARKET" if role in _STOP_ORDER_ROLES else "MARKET"


def _falcon_attempt_id(
    canonical_operation_id: str, *, revision: int, attempt: int
) -> str:
    """Derive the legacy numeric attempt as an immutable account attempt ID."""

    material = (
        f"{ACCOUNT_CLIENT_ORDER_ID_NAMESPACE}|{canonical_operation_id}|"
        f"REVISION={revision}|ATTEMPT={attempt}"
    )
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest().upper()
    return f"ATT1-{digest[:ACCOUNT_CLIENT_ORDER_ID_HASH_HEX_LENGTH]}"


def _account_identity_from_falcon(
    *,
    bot: Any,
    lifecycle_id: Any,
    entry_client_order_id: Any,
    entry_order_id: Any,
    symbol: Any,
    side: Any,
    operation: Any = None,
    revision: Any = 0,
    attempt: Any = 0,
    role: Any = None,
    stop_revision: Any = None,
    order_type: Any = None,
    account_namespace: Any = ACCOUNT_CLIENT_ORDER_ID_NAMESPACE,
    canonical_operation_id: Any = None,
    attempt_id: Any = None,
    attempt_sequence: Any = None,
) -> dict[str, Any]:
    """Translate and validate the legacy Falcon identity without ambiguity."""

    normalized_role = str(
        operation if operation not in (None, "") else role or ""
    ).strip().upper()
    if not normalized_role:
        raise ValueError("operation is required")
    if role not in (None, "") and str(role).strip().upper() != normalized_role:
        raise ValueError("role and operation must identify the same order role")
    if normalized_role not in FALCON_CLIENT_ORDER_ID_ROLE_NAMESPACES:
        raise ValueError("unsupported Falcon order operation")

    normalized_revision = _sequence("revision", revision)
    if stop_revision is not None and _sequence(
        "stop_revision", stop_revision
    ) != normalized_revision:
        raise ValueError("stop_revision and revision must match")
    normalized_attempt = _sequence("attempt", attempt)
    if attempt_sequence is not None and _sequence(
        "attempt_sequence", attempt_sequence
    ) != normalized_attempt:
        raise ValueError("attempt_sequence and attempt must match")

    normalized_bot = str(bot or "").strip().upper()
    if normalized_bot != "FALCON":
        raise ValueError("bot must be FALCON")
    entry_client_text = str(entry_client_order_id or "").strip()
    entry_order_text = str(entry_order_id or "").strip()
    if normalized_role in _DERIVED_ORDER_ROLES:
        if not entry_client_text:
            raise ValueError(
                "entry_client_order_id is required for derived orders"
            )
        if not entry_order_text:
            raise ValueError("entry_order_id is required for derived orders")

    namespace = str(account_namespace or "").strip().upper()
    if namespace != ACCOUNT_CLIENT_ORDER_ID_NAMESPACE:
        raise ValueError("Falcon must use the account-wide client-order namespace")
    normalized_order_type = _falcon_order_type(
        normalized_role, explicit=order_type
    )
    derived_operation_id = build_canonical_operation_id(
        account_namespace=ACCOUNT_CLIENT_ORDER_ID_NAMESPACE,
        bot="FALCON",
        role=normalized_role,
        lifecycle_id=lifecycle_id,
        symbol=symbol,
        side=side,
        entry_client_order_id=entry_client_text,
        entry_order_id=entry_order_text,
        stop_revision=normalized_revision,
        order_type=normalized_order_type,
    )
    if canonical_operation_id not in (None, "") and (
        str(canonical_operation_id).strip().upper() != derived_operation_id
    ):
        raise ValueError("canonical_operation_id does not match Falcon identity")
    derived_attempt_id = _falcon_attempt_id(
        derived_operation_id,
        revision=normalized_revision,
        attempt=normalized_attempt,
    )
    if attempt_id not in (None, "") and (
        str(attempt_id).strip().upper() != derived_attempt_id
    ):
        raise ValueError("attempt_id does not match Falcon revision/attempt")

    return canonical_account_order_attempt_identity(
        account_namespace=ACCOUNT_CLIENT_ORDER_ID_NAMESPACE,
        bot="FALCON",
        role=normalized_role,
        lifecycle_id=lifecycle_id,
        symbol=symbol,
        side=side,
        entry_client_order_id=entry_client_text,
        entry_order_id=entry_order_text,
        stop_revision=normalized_revision,
        order_type=normalized_order_type,
        canonical_operation_id=derived_operation_id,
        attempt_id=derived_attempt_id,
        attempt_sequence=normalized_attempt,
    )


def canonical_falcon_order_identity(**identity: Any) -> dict[str, Any]:
    """Return a Falcon-compatible view of the canonical account attempt."""

    canonical = _account_identity_from_falcon(**identity)
    return {
        **canonical,
        # Compatibility fields retained for Falcon's existing reservation
        # projection.  They are aliases of the authoritative account fields.
        "operation": canonical["role"],
        "revision": canonical["stop_revision"],
        "attempt": canonical["attempt_sequence"],
    }


def _account_identity_from_canonical_falcon(
    identity: dict[str, Any]
) -> dict[str, Any]:
    canonical = canonical_falcon_order_identity(**identity)
    return {
        key: canonical[key]
        for key in (
            "account_namespace",
            "bot",
            "role",
            "lifecycle_id",
            "symbol",
            "side",
            "attempt_id",
            "attempt_sequence",
            "canonical_operation_id",
            "entry_client_order_id",
            "entry_order_id",
            "stop_revision",
            "order_type",
        )
    }


def canonical_falcon_order_identity_json(**identity: Any) -> str:
    """Serialize the authoritative account attempt behind the facade."""

    return canonical_account_order_attempt_identity_json(
        **_account_identity_from_canonical_falcon(identity)
    )


def canonical_falcon_order_identity_hash(**identity: Any) -> str:
    """Return the account-wide attempt identity SHA-256 digest."""

    return canonical_account_order_attempt_identity_hash(
        **_account_identity_from_canonical_falcon(identity)
    )


def is_valid_falcon_client_order_id(value: Any) -> bool:
    """Validate using the case-insensitive account boundary contract."""

    return is_valid_account_client_order_id(value)


def generate_falcon_client_order_id(**identity: Any) -> str:
    """Generate through the sole account-wide client-order ID generator."""

    return generate_account_client_order_id(
        **_account_identity_from_canonical_falcon(identity)
    )


__all__ = [
    "ACCOUNT_CLIENT_ORDER_ID_GENERATOR_VERSION",
    "ACCOUNT_CLIENT_ORDER_ID_HASH_HEX_LENGTH",
    "ACCOUNT_CLIENT_ORDER_ID_MAX_LENGTH",
    "ACCOUNT_CLIENT_ORDER_ID_NAMESPACE",
    "ACCOUNT_CLIENT_ORDER_ID_ROLE_NAMESPACES",
    "FALCON_CLIENT_ORDER_ID_ACCOUNT_NAMESPACE",
    "FALCON_CLIENT_ORDER_ID_GENERATOR_VERSION",
    "FALCON_CLIENT_ORDER_ID_HASH_HEX_LENGTH",
    "FALCON_CLIENT_ORDER_ID_MAX_LENGTH",
    "FALCON_CLIENT_ORDER_ID_ROLE_NAMESPACES",
    "ROLE_BREAK_EVEN_STOP",
    "ROLE_EMERGENCY_TERMINAL_STOP_CLOSE",
    "ROLE_ENTRY",
    "ROLE_INITIAL_DISASTER_STOP",
    "ROLE_MANAGED_CLOSE",
    "ROLE_REPLACEMENT_STOP",
    "ROLE_ROLLBACK_STOP",
    "ROLE_TP50_CLOSE",
    "ROLE_TRAILING_STOP",
    "canonical_falcon_order_identity",
    "canonical_falcon_order_identity_hash",
    "canonical_falcon_order_identity_json",
    "generate_falcon_client_order_id",
    "is_valid_falcon_client_order_id",
]
