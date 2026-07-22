"""Account-wide lifetime authority for BingX ``clientOrderID`` values.

BingX treats client-order identifiers as case-insensitive and permanently
unique for the whole account.  This module owns that contract independently
from any bot.  Importing it is side-effect free: Redis is resolved lazily only
when a caller explicitly asks to reserve or verify an attempt.

The lifetime ledger is append-only.  It never expires, deletes, prunes, or
releases an identifier after a terminal outcome.  A create-order timeout never
authorizes either reuse of the old identifier or creation of a new attempt.
Only explicit factual reconciliation proving ``NOT_CREATED`` may authorize a
new attempt, which receives a distinct ``attempt_id`` and client-order ID.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Callable, Mapping, Optional


ACCOUNT_CLIENT_ORDER_ID_GENERATOR_VERSION = "ACCOUNT_CLIENT_ORDER_ID_V1"
ACCOUNT_CLIENT_ORDER_ID_AUTHORITY_VERSION = "ACCOUNT_CLIENT_ORDER_ID_AUTHORITY_V1"
ACCOUNT_CLIENT_ORDER_ID_MAX_LENGTH = 32
ACCOUNT_CLIENT_ORDER_ID_HASH_HEX_LENGTH = 24
ACCOUNT_CLIENT_ORDER_ID_NAMESPACE = "CENTRAL_QUANT_BINGX_ACCOUNT_V1"

ACCOUNT_CLIENT_ORDER_ID_LEDGER_PREFIX = "central:bingx:client_order_id:lifetime:v1"
ACCOUNT_CLIENT_ORDER_ATTEMPT_PREFIX = "central:bingx:client_order_attempt:lifetime:v1"
ACCOUNT_CLIENT_ORDER_OPERATION_PREFIX = "central:bingx:client_order_operation:lifetime:v1"
ACCOUNT_CLIENT_ORDER_AUTHORIZATION_PREFIX = "central:bingx:client_order_authorization:lifetime:v1"
ACCOUNT_CLIENT_ORDER_OUTCOME_PREFIX = "central:bingx:client_order_outcome:lifetime:v1"
ACCOUNT_CLIENT_ORDER_SEND_CLAIM_PREFIX = "central:bingx:client_order_send_claim:lifetime:v1"
ACCOUNT_CLIENT_ORDER_SEQUENCE_PREFIX = "central:bingx:client_order_sequence:lifetime:v1"
ACCOUNT_CLIENT_ORDER_DISPOSITION_PREFIX = "central:bingx:client_order_disposition:lifetime:v1"

ATTEMPT_DISPOSITION_PRE_SEND_CONSUMED = "PRE_SEND_CONSUMED"
ATTEMPT_DISPOSITION_SEND_CLAIMED = "SEND_CLAIMED"

ROLE_ENTRY = "ENTRY"
ROLE_INITIAL_DISASTER_STOP = "INITIAL_DISASTER_STOP"
ROLE_REPLACEMENT_STOP = "REPLACEMENT_STOP"
ROLE_ROLLBACK_STOP = "ROLLBACK_STOP"
ROLE_BREAK_EVEN_STOP = "BREAK_EVEN_STOP"
ROLE_TRAILING_STOP = "TRAILING_STOP"
ROLE_TP50_CLOSE = "TP50_CLOSE"
ROLE_EMERGENCY_TERMINAL_STOP_CLOSE = "EMERGENCY_TERMINAL_STOP_CLOSE"
ROLE_MANAGED_CLOSE = "MANAGED_CLOSE"

ACCOUNT_CLIENT_ORDER_ID_ROLE_NAMESPACES: Mapping[str, str] = MappingProxyType(
    {
        ROLE_ENTRY: "ENT1",
        ROLE_INITIAL_DISASTER_STOP: "FDS1",
        ROLE_REPLACEMENT_STOP: "FRP1",
        ROLE_ROLLBACK_STOP: "FRB1",
        ROLE_BREAK_EVEN_STOP: "FBE1",
        ROLE_TRAILING_STOP: "FTR1",
        ROLE_TP50_CLOSE: "FTP1",
        ROLE_EMERGENCY_TERMINAL_STOP_CLOSE: "FEC1",
        ROLE_MANAGED_CLOSE: "MCL1",
    }
)

_CLIENT_ORDER_ID_PATTERN = re.compile(r"^[A-Z0-9_-]{1,32}$")
_SAFE_IDENTITY_TEXT_PATTERN = re.compile(r"^[A-Z0-9_.:/-]+$")
_SIDES = frozenset({"LONG", "SHORT"})
_OUTCOME_STATES = frozenset(
    {
        "PRE_SEND_FAILED_ATTEMPT_CONSUMED",
        "CREATE_ORDER_OUTCOME_UNKNOWN",
        "ACKNOWLEDGED",
        "REJECTED",
        "FAILED",
        "CANCELED",
        "FILLED",
        "TERMINAL",
    }
)

_DEFAULT_REDIS_CLIENT: Any = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _required_text(name: str, value: Any, *, uppercase: bool = True) -> str:
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        raise ValueError(f"{name} must be textual")
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{name} is required")
    if len(normalized) > 512:
        raise ValueError(f"{name} is too long")
    normalized = normalized.upper() if uppercase else normalized
    if not _SAFE_IDENTITY_TEXT_PATTERN.fullmatch(normalized):
        raise ValueError(f"{name} contains unsupported characters")
    return normalized


def _optional_text(name: str, value: Any, *, uppercase: bool = True) -> str:
    if value in (None, ""):
        return ""
    return _required_text(name, value, uppercase=uppercase)


def _safe_evidence_code(name: str, value: Any) -> str:
    """Normalize a bounded diagnostic code without retaining free-form text."""

    if not isinstance(value, str):
        raise ValueError(f"{name} must be textual")
    normalized = value.strip().upper()
    if not normalized:
        raise ValueError(f"{name} is required")
    if len(normalized) > 128:
        raise ValueError(f"{name} is too long")
    if not _SAFE_IDENTITY_TEXT_PATTERN.fullmatch(normalized):
        raise ValueError(f"{name} contains unsupported characters")
    return normalized


def _sequence(name: str, value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a non-negative integer")
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a non-negative integer") from exc
    if normalized < 0 or str(value).strip() not in {str(normalized), f"+{normalized}"}:
        raise ValueError(f"{name} must be a non-negative integer")
    return normalized


def _canonical_symbol(value: Any) -> str:
    symbol = _required_text("symbol", value)
    symbol = symbol.replace("/", "").replace("-", "")
    if symbol.endswith(":USDT"):
        symbol = symbol[:-5]
    if not symbol or not re.fullmatch(r"[A-Z0-9]+", symbol):
        raise ValueError("symbol must use the Central canonical format")
    return symbol


def _canonical_side(value: Any) -> str:
    side = _required_text("side", value)
    side = {"BUY": "LONG", "SELL": "SHORT"}.get(side, side)
    if side not in _SIDES:
        raise ValueError("side must be LONG or SHORT")
    return side


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(
        dict(value), ensure_ascii=True, sort_keys=True, separators=(",", ":")
    )


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_canonical_operation_id(
    *,
    account_namespace: Any = ACCOUNT_CLIENT_ORDER_ID_NAMESPACE,
    bot: Any,
    role: Any,
    lifecycle_id: Any,
    symbol: Any,
    side: Any,
    entry_client_order_id: Any = "",
    entry_order_id: Any = "",
    stop_revision: Any = 0,
    order_type: Any = "MARKET",
) -> str:
    """Build the stable identity of one logical order, excluding attempts."""

    normalized_role = _required_text("role", role)
    if normalized_role not in ACCOUNT_CLIENT_ORDER_ID_ROLE_NAMESPACES:
        raise ValueError("unsupported account client-order role")
    payload = {
        "schema": ACCOUNT_CLIENT_ORDER_ID_GENERATOR_VERSION,
        "account_namespace": _required_text("account_namespace", account_namespace),
        "bot": _required_text("bot", bot),
        "role": normalized_role,
        "lifecycle_id": _required_text("lifecycle_id", lifecycle_id),
        "symbol": _canonical_symbol(symbol),
        "side": _canonical_side(side),
        "entry_client_order_id": _optional_text(
            "entry_client_order_id", entry_client_order_id
        ),
        "entry_order_id": _optional_text("entry_order_id", entry_order_id),
        "stop_revision": _sequence("stop_revision", stop_revision),
        "order_type": _required_text("order_type", order_type),
    }
    return f"OP1-{_sha256_hex(_canonical_json(payload)).upper()}"


def canonical_account_order_attempt_identity(
    *,
    bot: Any,
    role: Any,
    lifecycle_id: Any,
    symbol: Any,
    side: Any,
    attempt_id: Any,
    attempt_sequence: Any = 0,
    canonical_operation_id: Any = None,
    entry_client_order_id: Any = "",
    entry_order_id: Any = "",
    stop_revision: Any = 0,
    order_type: Any = "MARKET",
    account_namespace: Any = ACCOUNT_CLIENT_ORDER_ID_NAMESPACE,
) -> dict[str, Any]:
    """Return the immutable account-wide identity of one factual attempt."""

    normalized_role = _required_text("role", role)
    if normalized_role not in ACCOUNT_CLIENT_ORDER_ID_ROLE_NAMESPACES:
        raise ValueError("unsupported account client-order role")
    derived_operation_id = build_canonical_operation_id(
        account_namespace=account_namespace,
        bot=bot,
        role=normalized_role,
        lifecycle_id=lifecycle_id,
        symbol=symbol,
        side=side,
        entry_client_order_id=entry_client_order_id,
        entry_order_id=entry_order_id,
        stop_revision=stop_revision,
        order_type=order_type,
    )
    if canonical_operation_id not in (None, "") and _required_text(
        "canonical_operation_id", canonical_operation_id
    ) != derived_operation_id:
        raise ValueError("canonical_operation_id does not match immutable identity")
    operation_id = derived_operation_id
    return {
        "schema": ACCOUNT_CLIENT_ORDER_ID_GENERATOR_VERSION,
        "account_namespace": _required_text("account_namespace", account_namespace),
        "bot": _required_text("bot", bot),
        "role": normalized_role,
        "lifecycle_id": _required_text("lifecycle_id", lifecycle_id),
        "symbol": _canonical_symbol(symbol),
        "side": _canonical_side(side),
        "entry_client_order_id": _optional_text(
            "entry_client_order_id", entry_client_order_id
        ),
        "entry_order_id": _optional_text("entry_order_id", entry_order_id),
        "stop_revision": _sequence("stop_revision", stop_revision),
        "order_type": _required_text("order_type", order_type),
        "canonical_operation_id": _required_text(
            "canonical_operation_id", operation_id
        ),
        "attempt_id": _required_text("attempt_id", attempt_id),
        "attempt_sequence": _sequence("attempt_sequence", attempt_sequence),
    }


def canonical_account_order_attempt_identity_json(**identity: Any) -> str:
    return _canonical_json(canonical_account_order_attempt_identity(**identity))


def canonical_account_order_attempt_identity_hash(**identity: Any) -> str:
    return _sha256_hex(canonical_account_order_attempt_identity_json(**identity))


def normalize_account_client_order_id(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("clientOrderID must be textual")
    normalized = value.strip().upper()
    if not normalized:
        raise ValueError("clientOrderID is required")
    if len(normalized) > ACCOUNT_CLIENT_ORDER_ID_MAX_LENGTH:
        raise ValueError("CLIENT_ORDER_ID_INVALID_LENGTH")
    if not _CLIENT_ORDER_ID_PATTERN.fullmatch(normalized):
        raise ValueError("CLIENT_ORDER_ID_INVALID_CHARACTERS")
    return normalized


def is_valid_account_client_order_id(value: Any) -> bool:
    try:
        normalize_account_client_order_id(value)
        return True
    except Exception:
        return False


def generate_account_client_order_id(**identity: Any) -> str:
    canonical = canonical_account_order_attempt_identity(**identity)
    digest = _sha256_hex(_canonical_json(canonical)).upper()
    namespace = ACCOUNT_CLIENT_ORDER_ID_ROLE_NAMESPACES[canonical["role"]]
    result = f"{namespace}-{digest[:ACCOUNT_CLIENT_ORDER_ID_HASH_HEX_LENGTH]}"
    return normalize_account_client_order_id(result)


def account_client_order_id_ledger_key(
    client_order_id: Any,
    *,
    account_namespace: Any = ACCOUNT_CLIENT_ORDER_ID_NAMESPACE,
) -> str:
    normalized = normalize_account_client_order_id(client_order_id)
    namespace = _required_text("account_namespace", account_namespace)
    return f"{ACCOUNT_CLIENT_ORDER_ID_LEDGER_PREFIX}:{_sha256_hex(namespace + ':' + normalized)}"


def _identity_key(prefix: str, canonical_operation_id: str, attempt_id: str = "") -> str:
    material = f"{canonical_operation_id}:{attempt_id}" if attempt_id else canonical_operation_id
    return f"{prefix}:{_sha256_hex(material)}"


def account_client_order_sequence_key(
    canonical_operation_id: Any,
    attempt_sequence: Any,
) -> str:
    """Return the permanent slot for one operation attempt sequence."""

    operation_id = _required_text(
        "canonical_operation_id", canonical_operation_id
    )
    sequence = _sequence("attempt_sequence", attempt_sequence)
    return _identity_key(
        ACCOUNT_CLIENT_ORDER_SEQUENCE_PREFIX,
        operation_id,
        f"SEQUENCE:{sequence}",
    )


def account_client_order_disposition_key(
    canonical_operation_id: Any,
    attempt_id: Any,
) -> str:
    """Return the single immutable PRE_SEND-vs-SEND disposition slot."""

    return _identity_key(
        ACCOUNT_CLIENT_ORDER_DISPOSITION_PREFIX,
        _required_text("canonical_operation_id", canonical_operation_id),
        _required_text("attempt_id", attempt_id),
    )


def _authorization_sequence_key(
    canonical_operation_id: Any,
    attempt_sequence: Any,
) -> str:
    return _identity_key(
        ACCOUNT_CLIENT_ORDER_AUTHORIZATION_PREFIX,
        _required_text("canonical_operation_id", canonical_operation_id),
        f"SEQUENCE:{_sequence('attempt_sequence', attempt_sequence)}",
    )


def _record_has_fields(
    record: Optional[Mapping[str, Any]],
    expected: Mapping[str, Any],
) -> bool:
    return bool(
        record
        and all(record.get(field) == value for field, value in expected.items())
    )


def _decode_record(raw: Any) -> Optional[dict[str, Any]]:
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    if isinstance(raw, str):
        raw = json.loads(raw)
    return dict(raw) if isinstance(raw, dict) else None


def _default_redis_client() -> Any:
    global _DEFAULT_REDIS_CLIENT
    if _DEFAULT_REDIS_CLIENT is not None:
        return _DEFAULT_REDIS_CLIENT
    url = os.environ.get("UPSTASH_REDIS_REST_URL")
    token = os.environ.get("UPSTASH_REDIS_REST_TOKEN")
    if not url or not token:
        return None
    from upstash_redis import Redis

    _DEFAULT_REDIS_CLIENT = Redis(url=url, token=token)
    return _DEFAULT_REDIS_CLIENT


def _set_if_absent(
    redis_client: Any,
    key: str,
    value: str,
    callback: Optional[Callable[..., Any]],
) -> Any:
    if callback is not None:
        return callback(redis_client, key, value, caller=__name__)
    from redis_bandwidth import redis_set_if_absent

    return redis_set_if_absent(
        redis_client, key, value, caller=__name__
    )


def _authoritative_get(
    redis_client: Any,
    key: str,
    callback: Optional[Callable[..., Any]],
) -> Any:
    if callback is not None:
        return callback(redis_client, key, caller=__name__)
    from redis_bandwidth import redis_get_authoritative

    return redis_get_authoritative(redis_client, key, caller=__name__)


def _reservation_error(
    status: str,
    *,
    client_order_id: Any = None,
    identity: Optional[Mapping[str, Any]] = None,
    error: Optional[BaseException] = None,
) -> dict[str, Any]:
    identity = dict(identity or {})
    return {
        "ok": False,
        "send_allowed": False,
        "status": status,
        "client_order_id": str(client_order_id or "").upper() or None,
        "client_order_id_reserved": False,
        "client_order_id_unique": False,
        "reservation_status": status,
        "reservation_state": None,
        "persistent": False,
        "canonical_operation_id": identity.get("canonical_operation_id"),
        "attempt_id": identity.get("attempt_id"),
        "attempt_sequence": identity.get("attempt_sequence"),
        "account_namespace": identity.get("account_namespace"),
        "bot": identity.get("bot"),
        "role": identity.get("role"),
        "lifecycle_id": identity.get("lifecycle_id"),
        "symbol": identity.get("symbol"),
        "side": identity.get("side"),
        "entry_client_order_id": identity.get("entry_client_order_id"),
        "entry_order_id": identity.get("entry_order_id"),
        "stop_revision": identity.get("stop_revision"),
        "order_type": identity.get("order_type"),
        "reconciliation_required": True,
        "error_type": type(error).__name__ if error is not None else None,
    }


def reserve_account_client_order_attempt(
    identity: Mapping[str, Any],
    *,
    client_order_id: Any = None,
    redis_client: Any = None,
    set_if_absent: Optional[Callable[..., Any]] = None,
    get_authoritative: Optional[Callable[..., Any]] = None,
    now: Optional[Callable[[], str]] = None,
) -> dict[str, Any]:
    """Permanently reserve one factual attempt before ``create_order``.

    Only a freshly-created lifetime ledger record returns ``send_allowed``.
    Seeing the same attempt again is idempotent evidence but never permission
    to send a second order.
    """

    canonical: dict[str, Any] = {}
    generated_id: Optional[str] = None
    normalized_id: Optional[str] = None
    reservation_write_started = False
    reservation_readback_after_error: Optional[Callable[[], dict[str, Any]]] = None
    try:
        canonical = canonical_account_order_attempt_identity(**dict(identity or {}))
        generated_id = generate_account_client_order_id(**dict(identity or {}))
        normalized_id = normalize_account_client_order_id(
            generated_id if client_order_id is None else client_order_id
        )
        client = redis_client if redis_client is not None else _default_redis_client()
        if normalized_id != generated_id:
            existing = None
            if client is not None:
                existing = _decode_record(
                    _authoritative_get(
                        client,
                        account_client_order_id_ledger_key(
                            normalized_id,
                            account_namespace=canonical["account_namespace"],
                        ),
                        get_authoritative,
                    )
                )
            if existing:
                return {
                    **_reservation_error(
                        "CLIENT_ORDER_ID_COLLISION_DETECTED",
                        client_order_id=normalized_id,
                        identity=canonical,
                    ),
                    "persistent": True,
                    "client_order_id_reserved": True,
                    "collision_detected": True,
                    "same_attempt": False,
                }
            return _reservation_error(
                "CLIENT_ORDER_ID_DOES_NOT_MATCH_CANONICAL_ATTEMPT",
                client_order_id=normalized_id,
                identity=canonical,
            )
        if client is None:
            return _reservation_error(
                "CLIENT_ORDER_ID_AUTHORITY_UNAVAILABLE",
                client_order_id=normalized_id,
                identity=canonical,
            )

        operation_id = canonical["canonical_operation_id"]
        attempt_id = canonical["attempt_id"]
        attempt_sequence = canonical["attempt_sequence"]
        identity_hash = _sha256_hex(_canonical_json(canonical))
        created_at = (now or _now_iso)()
        id_key = account_client_order_id_ledger_key(
            normalized_id, account_namespace=canonical["account_namespace"]
        )
        attempt_key = _identity_key(
            ACCOUNT_CLIENT_ORDER_ATTEMPT_PREFIX, operation_id, attempt_id
        )
        operation_key = _identity_key(
            ACCOUNT_CLIENT_ORDER_OPERATION_PREFIX, operation_id
        )
        sequence_key = account_client_order_sequence_key(
            operation_id, attempt_sequence
        )
        authorization = None
        authorization_key = None

        if attempt_sequence > 0:
            authorization_key = _authorization_sequence_key(
                operation_id, attempt_sequence
            )
            authorization = _decode_record(
                _authoritative_get(client, authorization_key, get_authoritative)
            )
            prior_attempt_id = (
                str((authorization or {}).get("prior_attempt_id") or "")
                .upper()
                .strip()
            )
            prior_attempt_key = _identity_key(
                ACCOUNT_CLIENT_ORDER_ATTEMPT_PREFIX,
                operation_id,
                prior_attempt_id,
            )
            prior_attempt = (
                _decode_record(
                    _authoritative_get(
                        client, prior_attempt_key, get_authoritative
                    )
                )
                if prior_attempt_id
                else None
            )
            if not authorization or not (
                authorization.get("status") == "RECONCILED_NEW_ATTEMPT_AUTHORIZED"
                and authorization.get("account_namespace")
                == canonical["account_namespace"]
                and authorization.get("canonical_operation_id") == operation_id
                and authorization.get("attempt_id") == attempt_id
                and int(authorization.get("attempt_sequence", -1)) == attempt_sequence
                and int(authorization.get("prior_attempt_sequence", -2))
                == attempt_sequence - 1
                and prior_attempt_id
                and authorization.get("prior_attempt_identity_hash")
                and authorization.get("prior_client_order_id")
                and authorization.get("proof_mode")
                in {
                    "AUTHORITATIVE_PRE_SEND_NO_SEND_CLAIM",
                    "FACTUAL_BROKER_CLIENT_ORDER_ID_LOOKUP",
                }
                and re.fullmatch(
                    r"[0-9a-f]{64}", str(authorization.get("evidence_hash") or "")
                )
                and authorization.get("query_complete") is True
                and authorization.get("order_found") is False
                and authorization.get("fills_found") is False
                and authorization.get("ambiguous") is False
                and authorization.get("lifetime") is True
                and prior_attempt
                and prior_attempt.get("canonical_operation_id") == operation_id
                and prior_attempt.get("attempt_id") == prior_attempt_id
                and prior_attempt.get("attempt_sequence") == attempt_sequence - 1
                and prior_attempt.get("attempt_identity_hash")
                == authorization.get("prior_attempt_identity_hash")
                and str(prior_attempt.get("client_order_id") or "").upper()
                == str(authorization.get("prior_client_order_id") or "").upper()
            ):
                return _reservation_error(
                    "CLIENT_ORDER_ATTEMPT_NOT_AUTHORIZED_BY_RECONCILIATION",
                    client_order_id=normalized_id,
                    identity=canonical,
                )

        id_record = {
            "authority_version": ACCOUNT_CLIENT_ORDER_ID_AUTHORITY_VERSION,
            "generator_version": ACCOUNT_CLIENT_ORDER_ID_GENERATOR_VERSION,
            "account_namespace": canonical["account_namespace"],
            "client_order_id": normalized_id,
            "role": canonical["role"],
            "bot": canonical["bot"],
            "lifecycle_id": canonical["lifecycle_id"],
            "symbol": canonical["symbol"],
            "side": canonical["side"],
            "entry_client_order_id": canonical["entry_client_order_id"],
            "entry_order_id": canonical["entry_order_id"],
            "stop_revision": canonical["stop_revision"],
            "order_type": canonical["order_type"],
            "canonical_operation_id": operation_id,
            "attempt_id": attempt_id,
            "attempt_sequence": attempt_sequence,
            "attempt_identity_hash": identity_hash,
            "state": "RESERVED_PRE_SEND",
            "created_at": created_at,
            "lifetime": True,
            "case_sensitive": False,
        }
        attempt_record = {
            "account_namespace": canonical["account_namespace"],
            "client_order_id": normalized_id,
            "canonical_operation_id": operation_id,
            "attempt_id": attempt_id,
            "attempt_sequence": attempt_sequence,
            "attempt_identity_hash": identity_hash,
            "bot": canonical["bot"],
            "role": canonical["role"],
            "lifecycle_id": canonical["lifecycle_id"],
            "symbol": canonical["symbol"],
            "side": canonical["side"],
            "entry_client_order_id": canonical["entry_client_order_id"],
            "entry_order_id": canonical["entry_order_id"],
            "stop_revision": canonical["stop_revision"],
            "order_type": canonical["order_type"],
            "state": "RESERVED_PRE_SEND",
            "created_at": created_at,
            "lifetime": True,
        }
        operation_record = {
            "account_namespace": canonical["account_namespace"],
            "canonical_operation_id": operation_id,
            "bot": canonical["bot"],
            "role": canonical["role"],
            "lifecycle_id": canonical["lifecycle_id"],
            "symbol": canonical["symbol"],
            "side": canonical["side"],
            "first_attempt_id": attempt_id,
            "created_at": created_at,
            "lifetime": True,
        }
        sequence_record = {
            "authority_version": ACCOUNT_CLIENT_ORDER_ID_AUTHORITY_VERSION,
            "account_namespace": canonical["account_namespace"],
            "canonical_operation_id": operation_id,
            "attempt_sequence": attempt_sequence,
            "attempt_id": attempt_id,
            "attempt_identity_hash": identity_hash,
            "client_order_id": normalized_id,
            "created_at": created_at,
            "lifetime": True,
        }

        id_expected = {key: value for key, value in id_record.items() if key != "created_at"}
        attempt_expected = {
            key: value for key, value in attempt_record.items() if key != "created_at"
        }
        sequence_expected = {
            key: value for key, value in sequence_record.items() if key != "created_at"
        }
        operation_expected = {
            key: value
            for key, value in operation_record.items()
            if key != "created_at"
            and not (attempt_sequence > 0 and key == "first_attempt_id")
        }

        def readback() -> dict[str, Any]:
            actual = {
                "client_order_id": _decode_record(
                    _authoritative_get(client, id_key, get_authoritative)
                ),
                "attempt": _decode_record(
                    _authoritative_get(client, attempt_key, get_authoritative)
                ),
                "operation": _decode_record(
                    _authoritative_get(client, operation_key, get_authoritative)
                ),
                "sequence": _decode_record(
                    _authoritative_get(client, sequence_key, get_authoritative)
                ),
            }
            expected = {
                "client_order_id": id_expected,
                "attempt": attempt_expected,
                "operation": operation_expected,
                "sequence": sequence_expected,
            }
            if attempt_sequence > 0:
                actual["authorization"] = _decode_record(
                    _authoritative_get(
                        client, authorization_key, get_authoritative
                    )
                )
                expected["authorization"] = dict(authorization or {})
            present = {name: value is not None for name, value in actual.items()}
            matches = {
                name: _record_has_fields(actual[name], expected[name])
                for name in actual
            }
            return {
                "integral": all(matches.values()),
                "present": present,
                "matches": matches,
                "missing": sorted(name for name, value in present.items() if not value),
                "mismatched": sorted(
                    name
                    for name, value in matches.items()
                    if present[name] and not value
                ),
            }

        def blocked_from_readback(
            status: str,
            projection: Mapping[str, Any],
            *,
            same_attempt: bool = False,
            collision: bool = False,
        ) -> dict[str, Any]:
            return {
                **_reservation_error(
                    status,
                    client_order_id=normalized_id,
                    identity=canonical,
                ),
                "persistent": any(projection.get("present", {}).values()),
                "client_order_id_reserved": bool(
                    projection.get("present", {}).get("client_order_id")
                ),
                "client_order_id_unique": bool(
                    same_attempt
                    and projection.get("matches", {}).get("client_order_id")
                ),
                "collision_detected": collision,
                "same_attempt": same_attempt,
                "attempt_identity_hash": identity_hash,
                "sequence_slot_key": sequence_key,
                "reservation_readback": dict(projection),
            }

        reservation_readback_after_error = readback

        # The sequence slot is reserved first.  Two attempt IDs can therefore
        # never both consume the same operation+sequence, even when their
        # generated clientOrderIDs differ.
        reservation_write_started = True
        sequence_acquired = _set_if_absent(
            client, sequence_key, _canonical_json(sequence_record), set_if_absent
        )
        sequence_existing = _decode_record(
            _authoritative_get(client, sequence_key, get_authoritative)
        )
        sequence_matches = _record_has_fields(sequence_existing, sequence_expected)
        if not sequence_matches:
            projection = readback()
            return blocked_from_readback(
                "CLIENT_ORDER_ATTEMPT_SEQUENCE_SLOT_COLLISION"
                if sequence_existing
                else "PARTIAL_RESERVATION_REQUIRES_RECONCILIATION",
                projection,
                collision=bool(sequence_existing),
            )
        if sequence_acquired in (None, False):
            projection = readback()
            if not projection["integral"]:
                return blocked_from_readback(
                    "PARTIAL_RESERVATION_REQUIRES_RECONCILIATION",
                    projection,
                    same_attempt=True,
                )
            return {
                **blocked_from_readback(
                    "CLIENT_ORDER_ID_ALREADY_RESERVED_RECONCILIATION_REQUIRED",
                    projection,
                    same_attempt=True,
                ),
                "ok": True,
                "client_order_id_unique": True,
            }

        id_acquired = _set_if_absent(
            client, id_key, _canonical_json(id_record), set_if_absent
        )
        if id_acquired in (None, False):
            projection = readback()
            same_attempt = bool(projection["matches"].get("client_order_id"))
            return blocked_from_readback(
                "CLIENT_ORDER_ID_ALREADY_RESERVED_RECONCILIATION_REQUIRED"
                if same_attempt and projection["integral"]
                else "PARTIAL_RESERVATION_REQUIRES_RECONCILIATION"
                if same_attempt
                else "CLIENT_ORDER_ID_COLLISION_DETECTED",
                projection,
                same_attempt=same_attempt,
                collision=not same_attempt,
            )

        attempt_acquired = _set_if_absent(
            client, attempt_key, _canonical_json(attempt_record), set_if_absent
        )
        if attempt_acquired in (None, False):
            projection = readback()
            return blocked_from_readback(
                "CLIENT_ORDER_ATTEMPT_ALREADY_EXISTS"
                if projection["present"].get("attempt")
                else "PARTIAL_RESERVATION_REQUIRES_RECONCILIATION",
                projection,
                collision=bool(
                    projection["present"].get("attempt")
                    and not projection["matches"].get("attempt")
                ),
            )

        if attempt_sequence == 0:
            operation_acquired = _set_if_absent(
                client,
                operation_key,
                _canonical_json(operation_record),
                set_if_absent,
            )
            if operation_acquired in (None, False):
                projection = readback()
                return blocked_from_readback(
                    "CLIENT_ORDER_OPERATION_ALREADY_HAS_INITIAL_ATTEMPT",
                    projection,
                    collision=True,
                )
        else:
            existing_operation = _decode_record(
                _authoritative_get(client, operation_key, get_authoritative)
            )
            if not _record_has_fields(existing_operation, operation_expected):
                projection = readback()
                return blocked_from_readback(
                    "CLIENT_ORDER_OPERATION_HISTORY_MISSING",
                    projection,
                )

        projection = readback()
        if not projection["integral"]:
            return blocked_from_readback(
                "PARTIAL_RESERVATION_REQUIRES_RECONCILIATION",
                projection,
            )

        return {
            "ok": True,
            "send_allowed": True,
            "status": "RESERVED_UNIQUE",
            "reservation_status": "RESERVED_UNIQUE",
            "reservation_state": "RESERVED_PRE_SEND",
            "persistent": True,
            "client_order_id": normalized_id,
            "client_order_id_reserved": True,
            "client_order_id_unique": True,
            "collision_detected": False,
            "same_attempt": True,
            "reconciliation_required": False,
            "canonical_operation_id": operation_id,
            "attempt_id": attempt_id,
            "attempt_sequence": attempt_sequence,
            "attempt_identity_hash": identity_hash,
            "account_namespace": canonical["account_namespace"],
            "role": canonical["role"],
            "bot": canonical["bot"],
            "lifecycle_id": canonical["lifecycle_id"],
            "symbol": canonical["symbol"],
            "side": canonical["side"],
            "entry_client_order_id": canonical["entry_client_order_id"],
            "entry_order_id": canonical["entry_order_id"],
            "stop_revision": canonical["stop_revision"],
            "order_type": canonical["order_type"],
            "authority_key": id_key,
            "sequence_slot_key": sequence_key,
            "sequence_slot_unique": True,
            "reservation_readback": projection,
        }
    except ValueError as exc:
        status = (
            str(exc)
            if str(exc).startswith("CLIENT_ORDER_ID_")
            else "CLIENT_ORDER_IDENTITY_INVALID"
        )
        return _reservation_error(
            status,
            client_order_id=(
                client_order_id if client_order_id is not None else generated_id
            ),
            identity=canonical,
            error=exc,
        )
    except Exception as exc:
        if reservation_write_started and reservation_readback_after_error is not None:
            try:
                projection = reservation_readback_after_error()
            except Exception:
                projection = None
            if projection and any(projection.get("present", {}).values()):
                return {
                    **_reservation_error(
                        "PARTIAL_RESERVATION_REQUIRES_RECONCILIATION",
                        client_order_id=(
                            normalized_id
                            or client_order_id
                            or generated_id
                        ),
                        identity=canonical,
                        error=exc,
                    ),
                    "persistent": True,
                    "reservation_readback": projection,
                }
        return _reservation_error(
            "CLIENT_ORDER_ID_AUTHORITY_ERROR",
            client_order_id=(
                client_order_id if client_order_id is not None else generated_id
            ),
            identity=canonical,
            error=exc,
        )


def verify_account_client_order_id_reservation(
    reservation: Mapping[str, Any],
    *,
    expected_client_order_id: Any,
    redis_client: Any = None,
    get_authoritative: Optional[Callable[..., Any]] = None,
) -> dict[str, Any]:
    """Authoritatively verify a reservation immediately before a send."""

    try:
        receipt = dict(reservation or {})
        normalized_id = normalize_account_client_order_id(expected_client_order_id)
        account_namespace = _required_text(
            "account_namespace",
            receipt.get("account_namespace") or ACCOUNT_CLIENT_ORDER_ID_NAMESPACE,
        )
        if not (
            receipt.get("status") == "RESERVED_UNIQUE"
            and receipt.get("reservation_status") == "RESERVED_UNIQUE"
            and receipt.get("reservation_state") == "RESERVED_PRE_SEND"
            and receipt.get("persistent") is True
            and receipt.get("client_order_id_reserved") is True
            and receipt.get("client_order_id_unique") is True
            and str(receipt.get("client_order_id") or "").upper() == normalized_id
            and receipt.get("canonical_operation_id")
            and receipt.get("attempt_id")
            and receipt.get("attempt_sequence") is not None
            and receipt.get("attempt_identity_hash")
            and receipt.get("bot")
            and receipt.get("role")
            and receipt.get("lifecycle_id")
            and receipt.get("symbol")
            and receipt.get("side")
            and receipt.get("order_type")
            and receipt.get("stop_revision") is not None
        ):
            return {
                "ok": False,
                "send_allowed": False,
                "status": "CLIENT_ORDER_ID_RESERVATION_RECEIPT_INVALID",
                "client_order_id": normalized_id,
                "persistent": False,
            }
        client = redis_client if redis_client is not None else _default_redis_client()
        if client is None:
            raise RuntimeError("account client-order authority unavailable")
        operation_id = _required_text(
            "canonical_operation_id", receipt.get("canonical_operation_id")
        )
        attempt_id = _required_text("attempt_id", receipt.get("attempt_id"))
        attempt_sequence = _sequence(
            "attempt_sequence", receipt.get("attempt_sequence")
        )
        key = account_client_order_id_ledger_key(
            normalized_id, account_namespace=account_namespace
        )
        existing = _decode_record(
            _authoritative_get(client, key, get_authoritative)
        )
        attempt_key = _identity_key(
            ACCOUNT_CLIENT_ORDER_ATTEMPT_PREFIX, operation_id, attempt_id
        )
        existing_attempt = _decode_record(
            _authoritative_get(client, attempt_key, get_authoritative)
        )
        operation_key = _identity_key(
            ACCOUNT_CLIENT_ORDER_OPERATION_PREFIX, operation_id
        )
        existing_operation = _decode_record(
            _authoritative_get(client, operation_key, get_authoritative)
        )
        sequence_key = account_client_order_sequence_key(
            operation_id, attempt_sequence
        )
        existing_sequence = _decode_record(
            _authoritative_get(client, sequence_key, get_authoritative)
        )
        authorization_key = None
        existing_authorization = None
        authorization_matches = attempt_sequence == 0
        if attempt_sequence > 0:
            authorization_key = _authorization_sequence_key(
                operation_id, attempt_sequence
            )
            existing_authorization = _decode_record(
                _authoritative_get(
                    client, authorization_key, get_authoritative
                )
            )
            prior_id = str(
                (existing_authorization or {}).get("prior_attempt_id") or ""
            ).upper()
            prior_sequence = (existing_authorization or {}).get(
                "prior_attempt_sequence"
            )
            prior_attempt = None
            prior_sequence_record = None
            if prior_id and prior_sequence is not None:
                prior_attempt = _decode_record(
                    _authoritative_get(
                        client,
                        _identity_key(
                            ACCOUNT_CLIENT_ORDER_ATTEMPT_PREFIX,
                            operation_id,
                            prior_id,
                        ),
                        get_authoritative,
                    )
                )
                prior_sequence_record = _decode_record(
                    _authoritative_get(
                        client,
                        account_client_order_sequence_key(
                            operation_id, prior_sequence
                        ),
                        get_authoritative,
                    )
                )
            authorization_matches = bool(
                existing_authorization
                and existing_authorization.get("status")
                == "RECONCILED_NEW_ATTEMPT_AUTHORIZED"
                and existing_authorization.get("account_namespace")
                == account_namespace
                and existing_authorization.get("canonical_operation_id")
                == operation_id
                and existing_authorization.get("attempt_id") == attempt_id
                and existing_authorization.get("attempt_sequence")
                == attempt_sequence
                and prior_sequence == attempt_sequence - 1
                and existing_authorization.get("prior_attempt_identity_hash")
                and existing_authorization.get("prior_client_order_id")
                and existing_authorization.get("proof_mode")
                in {
                    "AUTHORITATIVE_PRE_SEND_NO_SEND_CLAIM",
                    "FACTUAL_BROKER_CLIENT_ORDER_ID_LOOKUP",
                }
                and re.fullmatch(
                    r"[0-9a-f]{64}",
                    str(existing_authorization.get("evidence_hash") or ""),
                )
                and existing_authorization.get("query_complete") is True
                and existing_authorization.get("order_found") is False
                and existing_authorization.get("fills_found") is False
                and existing_authorization.get("ambiguous") is False
                and existing_authorization.get("lifetime") is True
                and _record_has_fields(
                    prior_attempt,
                    {
                        "canonical_operation_id": operation_id,
                        "attempt_id": prior_id,
                        "attempt_sequence": prior_sequence,
                        "attempt_identity_hash": existing_authorization.get(
                            "prior_attempt_identity_hash"
                        ),
                        "client_order_id": existing_authorization.get(
                            "prior_client_order_id"
                        ),
                        "lifetime": True,
                    },
                )
                and _record_has_fields(
                    prior_sequence_record,
                    {
                        "canonical_operation_id": operation_id,
                        "attempt_sequence": prior_sequence,
                        "attempt_id": prior_id,
                        "attempt_identity_hash": existing_authorization.get(
                            "prior_attempt_identity_hash"
                        ),
                        "client_order_id": existing_authorization.get(
                            "prior_client_order_id"
                        ),
                        "lifetime": True,
                    },
                )
            )
        claim_key = _identity_key(
            ACCOUNT_CLIENT_ORDER_SEND_CLAIM_PREFIX,
            operation_id,
            attempt_id,
        )
        existing_claim = _decode_record(
            _authoritative_get(client, claim_key, get_authoritative)
        )
        disposition_key = account_client_order_disposition_key(
            operation_id, attempt_id
        )
        existing_disposition = _decode_record(
            _authoritative_get(client, disposition_key, get_authoritative)
        )
        existing_outcomes = {}
        for outcome_state in sorted(_OUTCOME_STATES):
            outcome = _decode_record(
                _authoritative_get(
                    client,
                    _identity_key(
                        ACCOUNT_CLIENT_ORDER_OUTCOME_PREFIX,
                        operation_id,
                        f"{attempt_id}:{outcome_state}",
                    ),
                    get_authoritative,
                )
            )
            if outcome:
                existing_outcomes[outcome_state] = outcome
        stable_context = {
            "account_namespace": account_namespace,
            "client_order_id": normalized_id,
            "canonical_operation_id": operation_id,
            "attempt_id": attempt_id,
            "attempt_sequence": attempt_sequence,
            "attempt_identity_hash": receipt.get("attempt_identity_hash"),
            "bot": receipt.get("bot"),
            "role": receipt.get("role"),
            "lifecycle_id": receipt.get("lifecycle_id"),
            "symbol": receipt.get("symbol"),
            "side": receipt.get("side"),
            "entry_client_order_id": receipt.get("entry_client_order_id"),
            "entry_order_id": receipt.get("entry_order_id"),
            "stop_revision": receipt.get("stop_revision"),
            "order_type": receipt.get("order_type"),
        }
        id_matches = bool(
            existing
            and str(existing.get("client_order_id") or "").upper() == normalized_id
            and all(
                existing.get(field) == value
                for field, value in stable_context.items()
                if field != "client_order_id"
            )
            and existing.get("state") == "RESERVED_PRE_SEND"
            and existing.get("lifetime") is True
        )
        attempt_matches = _record_has_fields(existing_attempt, stable_context)
        sequence_matches = _record_has_fields(
            existing_sequence,
            {
                "account_namespace": account_namespace,
                "client_order_id": normalized_id,
                "canonical_operation_id": operation_id,
                "attempt_id": attempt_id,
                "attempt_sequence": attempt_sequence,
                "attempt_identity_hash": receipt.get("attempt_identity_hash"),
                "lifetime": True,
            },
        )
        operation_matches = _record_has_fields(
            existing_operation,
            {
                "account_namespace": account_namespace,
                "canonical_operation_id": operation_id,
                "bot": receipt.get("bot"),
                "role": receipt.get("role"),
                "lifecycle_id": receipt.get("lifecycle_id"),
                "symbol": receipt.get("symbol"),
                "side": receipt.get("side"),
                "lifetime": True,
            },
        ) and (
            attempt_sequence > 0
            or existing_operation.get("first_attempt_id") == attempt_id
        )
        reservation_readback = {
            "integral": bool(
                id_matches
                and attempt_matches
                and operation_matches
                and sequence_matches
                and authorization_matches
            ),
            "matches": {
                "client_order_id": id_matches,
                "attempt": attempt_matches,
                "operation": operation_matches,
                "sequence": sequence_matches,
                "authorization": authorization_matches,
            },
            "present": {
                "client_order_id": bool(existing),
                "attempt": bool(existing_attempt),
                "operation": bool(existing_operation),
                "sequence": bool(existing_sequence),
                "authorization": bool(existing_authorization)
                if attempt_sequence > 0
                else True,
            },
        }
        disposition = str(
            (existing_disposition or {}).get("disposition")
            or (existing_disposition or {}).get("status")
            or ""
        ).upper()
        disposition_matches = bool(
            not existing_disposition
            or (
                disposition
                in {
                    ATTEMPT_DISPOSITION_PRE_SEND_CONSUMED,
                    ATTEMPT_DISPOSITION_SEND_CLAIMED,
                }
                and _record_has_fields(
                    existing_disposition,
                    {
                        "status": disposition,
                        "disposition": disposition,
                        "canonical_operation_id": operation_id,
                        "attempt_id": attempt_id,
                        "attempt_identity_hash": receipt.get(
                            "attempt_identity_hash"
                        ),
                        "client_order_id": normalized_id,
                        "lifetime": True,
                        "id_released": False,
                    },
                )
            )
        )
        send_already_claimed = bool(
            disposition == ATTEMPT_DISPOSITION_SEND_CLAIMED or existing_claim
        )
        pre_send_consumed = disposition == ATTEMPT_DISPOSITION_PRE_SEND_CONSUMED
        disposition_conflict = bool(
            not disposition_matches
            or (existing_claim and pre_send_consumed)
        )
        outcome_record_mismatches = sorted(
            state
            for state, outcome in existing_outcomes.items()
            if not _record_has_fields(
                outcome,
                {
                    "status": state,
                    "canonical_operation_id": operation_id,
                    "attempt_id": attempt_id,
                    "attempt_identity_hash": receipt.get(
                        "attempt_identity_hash"
                    ),
                    "client_order_id": normalized_id,
                    "attempt_disposition": (
                        ATTEMPT_DISPOSITION_PRE_SEND_CONSUMED
                        if state == "PRE_SEND_FAILED_ATTEMPT_CONSUMED"
                        else ATTEMPT_DISPOSITION_SEND_CLAIMED
                    ),
                    "lifetime": True,
                    "id_released": False,
                },
            )
        )
        outcome_conflicts = list(outcome_record_mismatches)
        if existing_outcomes:
            if not existing_disposition:
                outcome_conflicts = sorted(existing_outcomes)
            elif disposition == ATTEMPT_DISPOSITION_PRE_SEND_CONSUMED:
                outcome_conflicts = sorted(
                    set(outcome_conflicts)
                    | {
                    state
                    for state in existing_outcomes
                    if state != "PRE_SEND_FAILED_ATTEMPT_CONSUMED"
                    }
                )
            elif disposition == ATTEMPT_DISPOSITION_SEND_CLAIMED:
                if "PRE_SEND_FAILED_ATTEMPT_CONSUMED" in existing_outcomes:
                    outcome_conflicts = sorted(
                        set(outcome_conflicts)
                        | {"PRE_SEND_FAILED_ATTEMPT_CONSUMED"}
                    )
            else:
                outcome_conflicts = sorted(existing_outcomes)
        verified = bool(
            reservation_readback["integral"]
            and not disposition_conflict
            and not send_already_claimed
            and not pre_send_consumed
            and not existing_disposition
            and not outcome_conflicts
        )
        status = (
            "CLIENT_ORDER_ATTEMPT_OUTCOME_DISPOSITION_CONFLICT"
            if outcome_conflicts
            else "CLIENT_ORDER_ATTEMPT_DISPOSITION_MISMATCH"
            if disposition_conflict
            else
            "CLIENT_ORDER_ATTEMPT_PRE_SEND_CONSUMED"
            if pre_send_consumed
            else
            "CLIENT_ORDER_ATTEMPT_SEND_ALREADY_CLAIMED"
            if send_already_claimed
            else "RESERVED_UNIQUE"
            if verified
            else "PARTIAL_RESERVATION_REQUIRES_RECONCILIATION"
            if not all(reservation_readback["present"].values())
            else "CLIENT_ORDER_ID_LEDGER_MISMATCH"
        )
        return {
            "ok": verified,
            "send_allowed": verified,
            "status": status,
            "send_claimed": send_already_claimed,
            "attempt_disposition": disposition or None,
            "attempt_disposition_matches": disposition_matches,
            "outcomes_found": sorted(existing_outcomes),
            "outcome_record_mismatches": outcome_record_mismatches,
            "outcome_conflicts": outcome_conflicts,
            "client_order_id": normalized_id,
            "client_order_id_reserved": verified,
            "client_order_id_unique": verified,
            "persistent": bool(existing),
            "canonical_operation_id": receipt.get("canonical_operation_id"),
            "attempt_id": receipt.get("attempt_id"),
            "attempt_identity_hash": receipt.get("attempt_identity_hash"),
            "account_namespace": account_namespace,
            "bot": receipt.get("bot"),
            "role": receipt.get("role"),
            "lifecycle_id": receipt.get("lifecycle_id"),
            "symbol": receipt.get("symbol"),
            "side": receipt.get("side"),
            "entry_client_order_id": receipt.get("entry_client_order_id"),
            "entry_order_id": receipt.get("entry_order_id"),
            "stop_revision": receipt.get("stop_revision"),
            "order_type": receipt.get("order_type"),
            "attempt_sequence": attempt_sequence,
            "reservation_readback": reservation_readback,
            "reconciliation_required": not verified,
        }
    except ValueError as exc:
        return _reservation_error(str(exc), client_order_id=expected_client_order_id, error=exc)
    except Exception as exc:
        return _reservation_error(
            "CLIENT_ORDER_ID_AUTHORITY_ERROR",
            client_order_id=expected_client_order_id,
            error=exc,
        )


def claim_account_client_order_send_authorization(
    reservation: Mapping[str, Any],
    *,
    expected_client_order_id: Any,
    redis_client: Any = None,
    set_if_absent: Optional[Callable[..., Any]] = None,
    get_authoritative: Optional[Callable[..., Any]] = None,
    now: Optional[Callable[[], str]] = None,
) -> dict[str, Any]:
    """Atomically consume the one permitted send for a reserved attempt.

    Reservation and send authorization are deliberately separate.  A caller
    may pass a reservation through several fail-closed validation layers, but
    only the raw ``create_order`` boundary may claim it.  The claim is a
    permanent SET-NX fact: a crash after the claim is outcome-unknown and must
    be reconciled; the same receipt can never authorize a second send.
    """

    try:
        receipt = dict(reservation or {})
        client = redis_client if redis_client is not None else _default_redis_client()
        if client is None:
            raise RuntimeError("account client-order authority unavailable")
        verified = verify_account_client_order_id_reservation(
            receipt,
            expected_client_order_id=expected_client_order_id,
            redis_client=client,
            get_authoritative=get_authoritative,
        )
        if verified.get("send_allowed") is not True:
            return {
                **verified,
                "send_allowed": False,
                "send_claimed": False,
            }

        operation_id = _required_text(
            "canonical_operation_id", receipt.get("canonical_operation_id")
        )
        attempt_id = _required_text("attempt_id", receipt.get("attempt_id"))
        attempt_hash = _required_text(
            "attempt_identity_hash", receipt.get("attempt_identity_hash")
        ).lower()
        normalized_id = normalize_account_client_order_id(expected_client_order_id)
        disposition_key = account_client_order_disposition_key(
            operation_id, attempt_id
        )
        claimed_at = (now or _now_iso)()
        disposition_record = {
            "authority_version": ACCOUNT_CLIENT_ORDER_ID_AUTHORITY_VERSION,
            "status": ATTEMPT_DISPOSITION_SEND_CLAIMED,
            "disposition": ATTEMPT_DISPOSITION_SEND_CLAIMED,
            "account_namespace": receipt.get("account_namespace")
            or ACCOUNT_CLIENT_ORDER_ID_NAMESPACE,
            "canonical_operation_id": operation_id,
            "attempt_id": attempt_id,
            "attempt_identity_hash": attempt_hash,
            "client_order_id": normalized_id,
            "lifecycle_id": receipt.get("lifecycle_id"),
            "recorded_at": claimed_at,
            "lifetime": True,
            "id_released": False,
        }
        disposition_acquired = _set_if_absent(
            client,
            disposition_key,
            _canonical_json(disposition_record),
            set_if_absent,
        )
        persisted_disposition = _decode_record(
            _authoritative_get(client, disposition_key, get_authoritative)
        )
        disposition_matches = _record_has_fields(
            persisted_disposition,
            {
                key: value
                for key, value in disposition_record.items()
                if key != "recorded_at"
            },
        )
        if disposition_acquired in (None, False) or not disposition_matches:
            disposition = str(
                (persisted_disposition or {}).get("disposition")
                or (persisted_disposition or {}).get("status")
                or ""
            ).upper()
            return {
                "ok": False,
                "send_allowed": False,
                "send_claimed": disposition == ATTEMPT_DISPOSITION_SEND_CLAIMED,
                "status": "CLIENT_ORDER_ATTEMPT_PRE_SEND_CONSUMED"
                if disposition == ATTEMPT_DISPOSITION_PRE_SEND_CONSUMED
                else "CLIENT_ORDER_ATTEMPT_SEND_ALREADY_CLAIMED"
                if disposition == ATTEMPT_DISPOSITION_SEND_CLAIMED
                else "CLIENT_ORDER_ATTEMPT_DISPOSITION_PERSISTENCE_UNKNOWN",
                "client_order_id": normalized_id,
                "canonical_operation_id": operation_id,
                "attempt_id": attempt_id,
                "attempt_disposition": disposition or None,
                "persistent": bool(persisted_disposition),
                "reconciliation_required": True,
            }
        return {
            **verified,
            "ok": True,
            "send_allowed": True,
            "send_claimed": True,
            "status": "SEND_CLAIMED",
            # Compatibility field: the single disposition slot replaced the
            # former mirrored send-claim record and is now the sole authority.
            "send_claim_key": disposition_key,
            "attempt_disposition": ATTEMPT_DISPOSITION_SEND_CLAIMED,
            "attempt_disposition_key": disposition_key,
            "persistent": True,
            "reconciliation_required": False,
        }
    except ValueError as exc:
        return _reservation_error(
            str(exc), client_order_id=expected_client_order_id, error=exc
        )
    except Exception as exc:
        return _reservation_error(
            "CLIENT_ORDER_SEND_CLAIM_AUTHORITY_ERROR",
            client_order_id=expected_client_order_id,
            error=exc,
        )


def authorize_account_client_order_next_attempt(
    *,
    canonical_operation_id: Any,
    prior_attempt_id: Any,
    next_attempt_id: Any,
    next_attempt_sequence: Any,
    reconciliation_status: Any,
    evidence_source: Any,
    reconciled_at: Any,
    redis_client: Any = None,
    set_if_absent: Optional[Callable[..., Any]] = None,
    get_authoritative: Optional[Callable[..., Any]] = None,
    factual_reconciler: Optional[Callable[[Mapping[str, Any]], Mapping[str, Any]]] = None,
) -> dict[str, Any]:
    """Append factual authorization for a *new* attempt after reconciliation.

    No runtime writer calls this automatically.  A pre-send failure may be
    proven entirely by this authority's immutable ledgers.  Once the send claim
    exists (or the create outcome is unknown), ``NOT_CREATED`` must come from an
    injected read-only factual reconciler and is validated against the exact
    prior attempt and reserved clientOrderID before a new attempt is authorized.
    """

    try:
        operation_id = _required_text(
            "canonical_operation_id", canonical_operation_id
        )
        previous = _required_text("prior_attempt_id", prior_attempt_id)
        next_id = _required_text("next_attempt_id", next_attempt_id)
        sequence = _sequence("next_attempt_sequence", next_attempt_sequence)
        if sequence <= 0 or previous == next_id:
            raise ValueError("next attempt must be distinct and have sequence > 0")
        if _required_text("reconciliation_status", reconciliation_status) != "NOT_CREATED":
            raise ValueError("only factual NOT_CREATED reconciliation may authorize retry")
        source = _required_text("evidence_source", evidence_source)
        reconciled = _required_text("reconciled_at", reconciled_at)
        client = redis_client if redis_client is not None else _default_redis_client()
        if client is None:
            raise RuntimeError("account client-order authority unavailable")

        def deny(
            status: str,
            *,
            error: Optional[BaseException] = None,
            persistent: bool = False,
        ) -> dict[str, Any]:
            return {
                "ok": False,
                "status": status,
                "send_allowed": False,
                "persistent": persistent,
                "canonical_operation_id": operation_id,
                "attempt_id": next_id,
                "attempt_sequence": sequence,
                "reconciliation_required": True,
                "error_type": type(error).__name__ if error is not None else None,
            }

        prior_attempt_key = _identity_key(
            ACCOUNT_CLIENT_ORDER_ATTEMPT_PREFIX, operation_id, previous
        )
        prior_attempt = _decode_record(
            _authoritative_get(client, prior_attempt_key, get_authoritative)
        )
        if not prior_attempt or not (
            prior_attempt.get("canonical_operation_id") == operation_id
            and prior_attempt.get("attempt_id") == previous
            and prior_attempt.get("attempt_identity_hash")
            and prior_attempt.get("client_order_id")
            and prior_attempt.get("lifetime") is True
        ):
            return deny("PRIOR_ATTEMPT_AUTHORITY_RECORD_INVALID")
        try:
            prior_sequence = _sequence(
                "prior_attempt_sequence", prior_attempt.get("attempt_sequence")
            )
        except Exception as exc:
            return deny("PRIOR_ATTEMPT_SEQUENCE_INVALID", error=exc)
        if sequence != prior_sequence + 1:
            return deny("NEXT_ATTEMPT_SEQUENCE_NOT_CONTIGUOUS")

        account_namespace = _required_text(
            "account_namespace",
            prior_attempt.get("account_namespace")
            or ACCOUNT_CLIENT_ORDER_ID_NAMESPACE,
        )
        prior_client_order_id = normalize_account_client_order_id(
            prior_attempt.get("client_order_id")
        )
        prior_attempt_hash = _required_text(
            "prior_attempt_identity_hash",
            prior_attempt.get("attempt_identity_hash"),
        ).lower()
        prior_sequence_key = account_client_order_sequence_key(
            operation_id, prior_sequence
        )
        prior_sequence_record = _decode_record(
            _authoritative_get(client, prior_sequence_key, get_authoritative)
        )
        if not _record_has_fields(
            prior_sequence_record,
            {
                "canonical_operation_id": operation_id,
                "attempt_sequence": prior_sequence,
                "attempt_id": previous,
                "attempt_identity_hash": prior_attempt_hash,
                "client_order_id": prior_client_order_id,
                "lifetime": True,
            },
        ):
            return deny("PRIOR_ATTEMPT_SEQUENCE_SLOT_MISMATCH")
        operation_key = _identity_key(
            ACCOUNT_CLIENT_ORDER_OPERATION_PREFIX, operation_id
        )
        operation = _decode_record(
            _authoritative_get(client, operation_key, get_authoritative)
        )
        if not operation or not (
            operation.get("canonical_operation_id") == operation_id
            and operation.get("lifetime") is True
            and (
                not operation.get("account_namespace")
                or operation.get("account_namespace") == account_namespace
            )
        ):
            return deny("CLIENT_ORDER_OPERATION_HISTORY_MISSING")

        lifetime_key = account_client_order_id_ledger_key(
            prior_client_order_id, account_namespace=account_namespace
        )
        lifetime_record = _decode_record(
            _authoritative_get(client, lifetime_key, get_authoritative)
        )
        if not lifetime_record or not (
            str(lifetime_record.get("client_order_id") or "").upper()
            == prior_client_order_id
            and lifetime_record.get("canonical_operation_id") == operation_id
            and lifetime_record.get("attempt_id") == previous
            and lifetime_record.get("attempt_identity_hash") == prior_attempt_hash
            and lifetime_record.get("lifetime") is True
        ):
            return deny("PRIOR_CLIENT_ORDER_ID_LEDGER_MISMATCH")

        send_claim_key = _identity_key(
            ACCOUNT_CLIENT_ORDER_SEND_CLAIM_PREFIX, operation_id, previous
        )
        send_claim = _decode_record(
            _authoritative_get(client, send_claim_key, get_authoritative)
        )
        disposition_key = account_client_order_disposition_key(
            operation_id, previous
        )
        disposition_record = _decode_record(
            _authoritative_get(client, disposition_key, get_authoritative)
        )
        disposition = str(
            (disposition_record or {}).get("disposition")
            or (disposition_record or {}).get("status")
            or ""
        ).upper()
        disposition_matches = bool(
            not disposition_record
            or (
                disposition
                in {
                    ATTEMPT_DISPOSITION_PRE_SEND_CONSUMED,
                    ATTEMPT_DISPOSITION_SEND_CLAIMED,
                }
                and _record_has_fields(
                    disposition_record,
                    {
                        "status": disposition,
                        "disposition": disposition,
                        "canonical_operation_id": operation_id,
                        "attempt_id": previous,
                        "attempt_identity_hash": prior_attempt_hash,
                        "client_order_id": prior_client_order_id,
                        "lifetime": True,
                        "id_released": False,
                    },
                )
            )
        )
        outcomes = {}
        for outcome_state in sorted(_OUTCOME_STATES):
            outcome_key = _identity_key(
                ACCOUNT_CLIENT_ORDER_OUTCOME_PREFIX,
                operation_id,
                f"{previous}:{outcome_state}",
            )
            outcome = _decode_record(
                _authoritative_get(client, outcome_key, get_authoritative)
            )
            if outcome:
                outcomes[outcome_state] = outcome
        terminal_or_acknowledged = set(outcomes) - {
            "PRE_SEND_FAILED_ATTEMPT_CONSUMED",
            "CREATE_ORDER_OUTCOME_UNKNOWN",
        }
        if terminal_or_acknowledged:
            return deny("PRIOR_ATTEMPT_HAS_STRONGER_FACTUAL_OUTCOME")

        pre_send_outcome = outcomes.get("PRE_SEND_FAILED_ATTEMPT_CONSUMED")
        unknown_outcome = outcomes.get("CREATE_ORDER_OUTCOME_UNKNOWN")
        outcomes_match_disposition = all(
            _record_has_fields(
                outcome,
                {
                    "status": state,
                    "canonical_operation_id": operation_id,
                    "attempt_id": previous,
                    "attempt_identity_hash": prior_attempt_hash,
                    "client_order_id": prior_client_order_id,
                    "attempt_disposition": (
                        ATTEMPT_DISPOSITION_PRE_SEND_CONSUMED
                        if state == "PRE_SEND_FAILED_ATTEMPT_CONSUMED"
                        else ATTEMPT_DISPOSITION_SEND_CLAIMED
                    ),
                    "lifetime": True,
                    "id_released": False,
                },
            )
            for state, outcome in outcomes.items()
        )
        pre_send_consumed = bool(
            disposition == ATTEMPT_DISPOSITION_PRE_SEND_CONSUMED
        )
        send_claimed = bool(
            disposition == ATTEMPT_DISPOSITION_SEND_CLAIMED or send_claim
        )
        if (
            not disposition_matches
            or (outcomes and not disposition_record)
            or not outcomes_match_disposition
            or (pre_send_consumed and send_claimed)
            or (pre_send_consumed and unknown_outcome)
            or (
                disposition == ATTEMPT_DISPOSITION_SEND_CLAIMED
                and pre_send_outcome
            )
        ):
            return deny("PRIOR_ATTEMPT_DISPOSITION_CONFLICT")
        if pre_send_consumed:
            proof_mode = "AUTHORITATIVE_PRE_SEND_NO_SEND_CLAIM"
            evidence_projection = {
                "proof_mode": proof_mode,
                "read_only": True,
                "query_complete": True,
                "reconciliation_status": "NOT_CREATED",
                "canonical_operation_id": operation_id,
                "prior_attempt_id": previous,
                "prior_client_order_id": prior_client_order_id,
                "send_claim_present": False,
                "outcome_state": "PRE_SEND_FAILED_ATTEMPT_CONSUMED",
                "evidence_source": "ACCOUNT_CLIENT_ORDER_AUTHORITY_LEDGER",
                "reconciled_at": str(
                    (disposition_record or {}).get("recorded_at")
                    or (pre_send_outcome or {}).get("recorded_at")
                    or reconciled
                ),
            }
        else:
            if not (send_claimed or unknown_outcome):
                return deny("PRIOR_ATTEMPT_RECONCILIATION_BASIS_MISSING")
            if not callable(factual_reconciler):
                return deny("FACTUAL_READ_ONLY_RECONCILER_REQUIRED")
            lookup_request = MappingProxyType(
                {
                    "read_only": True,
                    "canonical_operation_id": operation_id,
                    "prior_attempt_id": previous,
                    "prior_attempt_sequence": prior_sequence,
                    "prior_client_order_id": prior_client_order_id,
                    "attempt_identity_hash": prior_attempt_hash,
                }
            )
            try:
                factual = dict(factual_reconciler(lookup_request) or {})
            except Exception as exc:
                return deny("FACTUAL_READ_ONLY_RECONCILIATION_ERROR", error=exc)
            try:
                factual_client_order_id = normalize_account_client_order_id(
                    factual.get("queried_client_order_id")
                )
            except Exception as exc:
                return deny("FACTUAL_RECONCILIATION_CLIENT_ORDER_ID_INVALID", error=exc)
            factual_valid = bool(
                factual.get("read_only") is True
                and factual.get("query_complete") is True
                and factual.get("order_found") is False
                and factual.get("fills_found") is False
                and factual.get("ambiguous") is False
                and factual.get("reconciliation_status") == "NOT_CREATED"
                and factual.get("canonical_operation_id") == operation_id
                and factual.get("prior_attempt_id") == previous
                and factual_client_order_id == prior_client_order_id
                and _required_text(
                    "factual_evidence_source", factual.get("evidence_source")
                ) == source
                and _required_text(
                    "factual_reconciled_at", factual.get("reconciled_at")
                ) == reconciled
            )
            if not factual_valid:
                return deny("FACTUAL_NOT_CREATED_RECONCILIATION_INVALID")
            proof_mode = "FACTUAL_BROKER_CLIENT_ORDER_ID_LOOKUP"
            evidence_projection = {
                "proof_mode": proof_mode,
                "read_only": True,
                "query_complete": True,
                "reconciliation_status": "NOT_CREATED",
                "canonical_operation_id": operation_id,
                "prior_attempt_id": previous,
                "prior_client_order_id": prior_client_order_id,
                "order_found": False,
                "fills_found": False,
                "ambiguous": False,
                "evidence_source": source,
                "reconciled_at": reconciled,
            }

        evidence_hash = _sha256_hex(_canonical_json(evidence_projection))
        key = _authorization_sequence_key(operation_id, sequence)
        record = {
            "authority_version": ACCOUNT_CLIENT_ORDER_ID_AUTHORITY_VERSION,
            "status": "RECONCILED_NEW_ATTEMPT_AUTHORIZED",
            "account_namespace": account_namespace,
            "canonical_operation_id": operation_id,
            "prior_attempt_id": previous,
            "prior_attempt_sequence": prior_sequence,
            "prior_attempt_identity_hash": prior_attempt_hash,
            "prior_client_order_id": prior_client_order_id,
            "attempt_id": next_id,
            "attempt_sequence": sequence,
            "reconciliation_status": "NOT_CREATED",
            "evidence_source": evidence_projection["evidence_source"],
            "reconciled_at": evidence_projection["reconciled_at"],
            "proof_mode": proof_mode,
            "evidence_hash": evidence_hash,
            "query_complete": True,
            "order_found": False,
            "fills_found": False,
            "ambiguous": False,
            "lifetime": True,
        }
        encoded_record = _canonical_json(record)
        acquired = _set_if_absent(
            client, key, encoded_record, set_if_absent
        )
        existing = _decode_record(
            _authoritative_get(client, key, get_authoritative)
        )
        if existing != record:
            return deny(
                "NEXT_ATTEMPT_SEQUENCE_ALREADY_AUTHORIZED"
                if existing
                else "ATTEMPT_AUTHORIZATION_PERSISTENCE_ERROR",
                persistent=bool(existing),
            )
        idempotent = acquired in (None, False)
        return {
            "ok": True,
            "status": (
                "ATTEMPT_AUTHORIZATION_ALREADY_EXISTS"
                if idempotent
                else "RECONCILED_NEW_ATTEMPT_AUTHORIZED"
            ),
            "account_namespace": account_namespace,
            "canonical_operation_id": operation_id,
            "attempt_id": next_id,
            "attempt_sequence": sequence,
            "prior_attempt_id": previous,
            "prior_attempt_sequence": prior_sequence,
            "prior_attempt_identity_hash": prior_attempt_hash,
            "prior_client_order_id": prior_client_order_id,
            "proof_mode": proof_mode,
            "evidence_hash": evidence_hash,
            "idempotent": idempotent,
            "persistent": True,
            "send_allowed": False,
            "reconciliation_required": False,
        }
    except Exception as exc:
        return {
            "ok": False,
            "status": "ATTEMPT_AUTHORIZATION_ERROR",
            "send_allowed": False,
            "persistent": False,
            "error_type": type(exc).__name__,
        }


def consume_account_client_order_attempt_pre_send(
    reservation: Mapping[str, Any],
    *,
    reason: Any,
    failure_phase: Any,
    redis_client: Any = None,
    set_if_absent: Optional[Callable[..., Any]] = None,
    get_authoritative: Optional[Callable[..., Any]] = None,
    now: Optional[Callable[[], str]] = None,
) -> dict[str, Any]:
    """Permanently consume an intact attempt before any exchange send.

    This and :func:`claim_account_client_order_send_authorization` compete for
    the same SET-NX disposition key.  Consequently an attempt can become
    exactly one of ``PRE_SEND_CONSUMED`` or ``SEND_CLAIMED``, never both.
    ``reason`` and ``failure_phase`` are restricted identity-safe codes; raw
    exception messages and other free-form values are intentionally rejected.
    """

    try:
        receipt = dict(reservation or {})
        reason_code = _safe_evidence_code("reason", reason)
        phase_code = _safe_evidence_code("failure_phase", failure_phase)
        operation_id = _required_text(
            "canonical_operation_id", receipt.get("canonical_operation_id")
        )
        attempt_id = _required_text("attempt_id", receipt.get("attempt_id"))
        attempt_hash = _required_text(
            "attempt_identity_hash", receipt.get("attempt_identity_hash")
        ).lower()
        client_order_id = normalize_account_client_order_id(
            receipt.get("client_order_id")
        )
        client = redis_client if redis_client is not None else _default_redis_client()
        if client is None:
            raise RuntimeError("account client-order authority unavailable")

        integrity = verify_account_client_order_id_reservation(
            receipt,
            expected_client_order_id=client_order_id,
            redis_client=client,
            get_authoritative=get_authoritative,
        )
        readback = integrity.get("reservation_readback") or {}
        if readback.get("integral") is not True:
            return {
                "ok": False,
                "status": "PARTIAL_RESERVATION_REQUIRES_RECONCILIATION",
                "send_allowed": False,
                "client_order_id": client_order_id,
                "id_released": False,
                "persistent": bool(integrity.get("persistent")),
                "reservation_readback": readback,
                "reconciliation_required": True,
            }
        if integrity.get("outcome_conflicts"):
            return {
                "ok": False,
                "status": "CLIENT_ORDER_ATTEMPT_OUTCOME_DISPOSITION_CONFLICT",
                "send_allowed": False,
                "client_order_id": client_order_id,
                "id_released": False,
                "persistent": True,
                "outcome_conflicts": list(integrity["outcome_conflicts"]),
                "reconciliation_required": True,
            }
        if integrity.get("send_claimed") is True:
            return {
                "ok": False,
                "status": "ATTEMPT_DISPOSITION_CONFLICT",
                "send_allowed": False,
                "client_order_id": client_order_id,
                "attempt_disposition": ATTEMPT_DISPOSITION_SEND_CLAIMED,
                "id_released": False,
                "persistent": True,
                "reconciliation_required": True,
            }

        disposition_key = account_client_order_disposition_key(
            operation_id, attempt_id
        )
        record = {
            "authority_version": ACCOUNT_CLIENT_ORDER_ID_AUTHORITY_VERSION,
            "status": ATTEMPT_DISPOSITION_PRE_SEND_CONSUMED,
            "disposition": ATTEMPT_DISPOSITION_PRE_SEND_CONSUMED,
            "account_namespace": receipt.get("account_namespace")
            or ACCOUNT_CLIENT_ORDER_ID_NAMESPACE,
            "canonical_operation_id": operation_id,
            "attempt_id": attempt_id,
            "attempt_identity_hash": attempt_hash,
            "client_order_id": client_order_id,
            "lifecycle_id": receipt.get("lifecycle_id"),
            "reason": reason_code,
            "failure_phase": phase_code,
            "recorded_at": (now or _now_iso)(),
            "lifetime": True,
            "id_released": False,
        }
        acquired = _set_if_absent(
            client, disposition_key, _canonical_json(record), set_if_absent
        )
        existing = _decode_record(
            _authoritative_get(client, disposition_key, get_authoritative)
        )
        stable_record = {
            key: value for key, value in record.items() if key != "recorded_at"
        }
        exact_match = _record_has_fields(existing, stable_record)
        existing_disposition = str(
            (existing or {}).get("disposition")
            or (existing or {}).get("status")
            or ""
        ).upper()
        if not exact_match:
            return {
                "ok": False,
                "status": "ATTEMPT_DISPOSITION_CONFLICT"
                if existing_disposition == ATTEMPT_DISPOSITION_SEND_CLAIMED
                else "ATTEMPT_PRE_SEND_EVIDENCE_MISMATCH"
                if existing_disposition == ATTEMPT_DISPOSITION_PRE_SEND_CONSUMED
                else "ATTEMPT_DISPOSITION_PERSISTENCE_ERROR",
                "send_allowed": False,
                "client_order_id": client_order_id,
                "attempt_disposition": existing_disposition or None,
                "id_released": False,
                "persistent": bool(existing),
                "reconciliation_required": True,
            }
        idempotent = acquired in (None, False)
        return {
            "ok": True,
            "status": "PRE_SEND_CONSUMPTION_ALREADY_RECORDED"
            if idempotent
            else "PRE_SEND_FAILED_ATTEMPT_CONSUMED",
            "send_allowed": False,
            "client_order_id": client_order_id,
            "canonical_operation_id": operation_id,
            "attempt_id": attempt_id,
            "attempt_disposition": ATTEMPT_DISPOSITION_PRE_SEND_CONSUMED,
            "attempt_disposition_key": disposition_key,
            "reason": reason_code,
            "failure_phase": phase_code,
            "id_released": False,
            "persistent": True,
            "idempotent": idempotent,
            "reconciliation_required": False,
        }
    except Exception as exc:
        return {
            "ok": False,
            "status": "ATTEMPT_PRE_SEND_CONSUMPTION_ERROR",
            "send_allowed": False,
            "id_released": False,
            "persistent": False,
            "reconciliation_required": True,
            "error_type": type(exc).__name__,
        }


def record_account_client_order_attempt_outcome(
    reservation: Mapping[str, Any],
    *,
    outcome_state: Any,
    reason: Any = None,
    failure_phase: Any = None,
    redis_client: Any = None,
    set_if_absent: Optional[Callable[..., Any]] = None,
    get_authoritative: Optional[Callable[..., Any]] = None,
    now: Optional[Callable[[], str]] = None,
) -> dict[str, Any]:
    """Append an immutable outcome fact; it never releases the reserved ID."""

    try:
        receipt = dict(reservation or {})
        state = _required_text("outcome_state", outcome_state)
        if state not in _OUTCOME_STATES:
            raise ValueError("unsupported attempt outcome state")
        operation_id = _required_text(
            "canonical_operation_id", receipt.get("canonical_operation_id")
        )
        attempt_id = _required_text("attempt_id", receipt.get("attempt_id"))
        attempt_hash = _required_text(
            "attempt_identity_hash", receipt.get("attempt_identity_hash")
        ).lower()
        client_order_id = normalize_account_client_order_id(
            receipt.get("client_order_id")
        )
        client = redis_client if redis_client is not None else _default_redis_client()
        if client is None:
            raise RuntimeError("account client-order authority unavailable")
        disposition_key = account_client_order_disposition_key(
            operation_id, attempt_id
        )
        if state == "PRE_SEND_FAILED_ATTEMPT_CONSUMED":
            expected_disposition = ATTEMPT_DISPOSITION_PRE_SEND_CONSUMED
            consumption = consume_account_client_order_attempt_pre_send(
                receipt,
                reason=reason or "PRE_SEND_FAILED_ATTEMPT_CONSUMED",
                failure_phase=failure_phase or "PRE_SEND",
                redis_client=client,
                set_if_absent=set_if_absent,
                get_authoritative=get_authoritative,
                now=now,
            )
            if consumption.get("ok") is not True:
                return consumption
            disposition_idempotent = bool(consumption.get("idempotent"))
            reason = consumption.get("reason")
            failure_phase = consumption.get("failure_phase")
        else:
            expected_disposition = ATTEMPT_DISPOSITION_SEND_CLAIMED
            persisted_disposition = _decode_record(
                _authoritative_get(client, disposition_key, get_authoritative)
            )
            disposition_matches = _record_has_fields(
                persisted_disposition,
                {
                    "status": expected_disposition,
                    "disposition": expected_disposition,
                    "account_namespace": receipt.get("account_namespace")
                    or ACCOUNT_CLIENT_ORDER_ID_NAMESPACE,
                    "canonical_operation_id": operation_id,
                    "attempt_id": attempt_id,
                    "attempt_identity_hash": attempt_hash,
                    "client_order_id": client_order_id,
                    "lifecycle_id": receipt.get("lifecycle_id"),
                    "lifetime": True,
                    "id_released": False,
                },
            )
            if not disposition_matches:
                disposition = str(
                    (persisted_disposition or {}).get("disposition")
                    or (persisted_disposition or {}).get("status")
                    or ""
                ).upper()
                return {
                    "ok": False,
                    "status": "ATTEMPT_DISPOSITION_CONFLICT"
                    if disposition == ATTEMPT_DISPOSITION_PRE_SEND_CONSUMED
                    else "ATTEMPT_SEND_NOT_CLAIMED",
                    "send_allowed": False,
                    "client_order_id": client_order_id,
                    "attempt_disposition": disposition or None,
                    "id_released": False,
                    "persistent": bool(persisted_disposition),
                    "reconciliation_required": True,
                }
            disposition_idempotent = True
        key = _identity_key(
            ACCOUNT_CLIENT_ORDER_OUTCOME_PREFIX,
            operation_id,
            f"{attempt_id}:{state}",
        )
        record = {
            "status": state,
            "account_namespace": receipt.get("account_namespace")
            or ACCOUNT_CLIENT_ORDER_ID_NAMESPACE,
            "canonical_operation_id": operation_id,
            "attempt_id": attempt_id,
            "attempt_identity_hash": attempt_hash,
            "client_order_id": client_order_id,
            "lifecycle_id": receipt.get("lifecycle_id"),
            "attempt_disposition": expected_disposition,
            "lifecycle_blocked": state == "CREATE_ORDER_OUTCOME_UNKNOWN",
            "reconciliation_required": state == "CREATE_ORDER_OUTCOME_UNKNOWN",
            "recorded_at": (now or _now_iso)(),
            "lifetime": True,
            "id_released": False,
        }
        if state == "PRE_SEND_FAILED_ATTEMPT_CONSUMED":
            record.update(
                {
                    "reason": reason,
                    "failure_phase": failure_phase,
                }
            )
        encoded_record = _canonical_json(record)
        acquired = _set_if_absent(
            client, key, encoded_record, set_if_absent
        )
        # A positive SET-NX acknowledgement is not durable evidence by itself.
        # Always prove the immutable outcome through authoritative read-back.
        existing = _decode_record(
            _authoritative_get(client, key, get_authoritative)
        )
        outcome_matches = bool(
            existing
            and all(
                existing.get(field) == record.get(field)
                for field in (
                    "status",
                    "account_namespace",
                    "canonical_operation_id",
                    "attempt_id",
                    "attempt_identity_hash",
                    "client_order_id",
                    "lifecycle_id",
                    "attempt_disposition",
                    "lifecycle_blocked",
                    "reconciliation_required",
                    "lifetime",
                    "id_released",
                    "reason",
                    "failure_phase",
                )
            )
        )
        idempotent = bool(acquired in (None, False) and outcome_matches)
        return {
            "ok": outcome_matches,
            "status": state if acquired not in (None, False) and outcome_matches else (
                "OUTCOME_ALREADY_RECORDED"
                if idempotent
                else "ATTEMPT_OUTCOME_COLLISION"
                if existing
                else "ATTEMPT_OUTCOME_PERSISTENCE_ERROR"
            ),
            "client_order_id": client_order_id,
            "id_released": False,
            "persistent": bool(existing),
            "idempotent": idempotent,
            "disposition_idempotent": disposition_idempotent,
            "attempt_disposition": expected_disposition,
            "attempt_disposition_key": disposition_key,
            "lifecycle_id": receipt.get("lifecycle_id"),
            "lifecycle_blocked": state == "CREATE_ORDER_OUTCOME_UNKNOWN",
            "reconciliation_required": bool(
                state == "CREATE_ORDER_OUTCOME_UNKNOWN" or not outcome_matches
            ),
        }
    except Exception as exc:
        return {
            "ok": False,
            "status": "ATTEMPT_OUTCOME_PERSISTENCE_ERROR",
            "id_released": False,
            "persistent": False,
            "error_type": type(exc).__name__,
        }


__all__ = [
    "ACCOUNT_CLIENT_ORDER_ATTEMPT_PREFIX",
    "ACCOUNT_CLIENT_ORDER_AUTHORIZATION_PREFIX",
    "ACCOUNT_CLIENT_ORDER_DISPOSITION_PREFIX",
    "ACCOUNT_CLIENT_ORDER_ID_AUTHORITY_VERSION",
    "ACCOUNT_CLIENT_ORDER_ID_GENERATOR_VERSION",
    "ACCOUNT_CLIENT_ORDER_ID_HASH_HEX_LENGTH",
    "ACCOUNT_CLIENT_ORDER_ID_LEDGER_PREFIX",
    "ACCOUNT_CLIENT_ORDER_ID_MAX_LENGTH",
    "ACCOUNT_CLIENT_ORDER_ID_NAMESPACE",
    "ACCOUNT_CLIENT_ORDER_ID_ROLE_NAMESPACES",
    "ACCOUNT_CLIENT_ORDER_OPERATION_PREFIX",
    "ACCOUNT_CLIENT_ORDER_OUTCOME_PREFIX",
    "ACCOUNT_CLIENT_ORDER_SEQUENCE_PREFIX",
    "ACCOUNT_CLIENT_ORDER_SEND_CLAIM_PREFIX",
    "ATTEMPT_DISPOSITION_PRE_SEND_CONSUMED",
    "ATTEMPT_DISPOSITION_SEND_CLAIMED",
    "ROLE_BREAK_EVEN_STOP",
    "ROLE_EMERGENCY_TERMINAL_STOP_CLOSE",
    "ROLE_ENTRY",
    "ROLE_INITIAL_DISASTER_STOP",
    "ROLE_MANAGED_CLOSE",
    "ROLE_REPLACEMENT_STOP",
    "ROLE_ROLLBACK_STOP",
    "ROLE_TP50_CLOSE",
    "ROLE_TRAILING_STOP",
    "account_client_order_id_ledger_key",
    "account_client_order_disposition_key",
    "account_client_order_sequence_key",
    "authorize_account_client_order_next_attempt",
    "build_canonical_operation_id",
    "canonical_account_order_attempt_identity",
    "canonical_account_order_attempt_identity_hash",
    "canonical_account_order_attempt_identity_json",
    "claim_account_client_order_send_authorization",
    "consume_account_client_order_attempt_pre_send",
    "generate_account_client_order_id",
    "is_valid_account_client_order_id",
    "normalize_account_client_order_id",
    "record_account_client_order_attempt_outcome",
    "reserve_account_client_order_attempt",
    "verify_account_client_order_id_reservation",
]
