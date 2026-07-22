from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest

from account_client_order_id import (
    ACCOUNT_CLIENT_ORDER_ID_GENERATOR_VERSION,
    ACCOUNT_CLIENT_ORDER_ID_NAMESPACE,
    generate_account_client_order_id,
)
from falcon_client_order_id import (
    FALCON_CLIENT_ORDER_ID_ACCOUNT_NAMESPACE,
    FALCON_CLIENT_ORDER_ID_GENERATOR_VERSION,
    FALCON_CLIENT_ORDER_ID_ROLE_NAMESPACES,
    ROLE_BREAK_EVEN_STOP,
    ROLE_EMERGENCY_TERMINAL_STOP_CLOSE,
    ROLE_ENTRY,
    ROLE_INITIAL_DISASTER_STOP,
    ROLE_MANAGED_CLOSE,
    ROLE_REPLACEMENT_STOP,
    ROLE_ROLLBACK_STOP,
    ROLE_TP50_CLOSE,
    ROLE_TRAILING_STOP,
    canonical_falcon_order_identity,
    canonical_falcon_order_identity_hash,
    canonical_falcon_order_identity_json,
    generate_falcon_client_order_id,
    is_valid_falcon_client_order_id,
)


ROOT = Path(__file__).resolve().parents[1]
FACTUAL_ENTRY_CLIENT_IDS = (
    "FALCON-LIVE-FALCON15-1784037618",
    "FALCON-LIVE-FALCON15-1784124020",
    "FALCON-LIVE-FALCON15-1784470538",
)
LEGACY_COLLIDING_STOP_ID = "FALCON-LIVE-FALCON15-178-DS"


def identity(**updates):
    values = {
        "bot": "FALCON",
        "lifecycle_id": "CENTRAL-FALCON-LIFECYCLE:FALCON-LIVE-FALCON15-1784470538",
        "entry_client_order_id": FACTUAL_ENTRY_CLIENT_IDS[-1],
        "entry_order_id": "2078840000000000000",
        "symbol": "SOLUSDT",
        "side": "LONG",
        "operation": ROLE_INITIAL_DISASTER_STOP,
        "revision": 0,
        "attempt": 0,
    }
    values.update(updates)
    return values


def test_three_factual_entries_generate_distinct_disaster_stop_ids():
    generated = {
        generate_falcon_client_order_id(
            **identity(
                lifecycle_id=f"CENTRAL-FALCON-LIFECYCLE:{entry_id}",
                entry_client_order_id=entry_id,
                entry_order_id=str(2078800000000000000 + index),
            )
        )
        for index, entry_id in enumerate(FACTUAL_ENTRY_CLIENT_IDS)
    }

    assert len(generated) == 3
    assert LEGACY_COLLIDING_STOP_ID not in generated
    assert all(value.startswith("FDS1-") for value in generated)


def test_ids_are_deterministic_bounded_and_use_exchange_safe_characters():
    first = generate_falcon_client_order_id(**identity())
    second = generate_falcon_client_order_id(**identity())

    assert first == second
    assert len(first) == 29
    assert len(first) <= 32
    assert re.fullmatch(r"[A-Z0-9-]+", first)
    assert is_valid_falcon_client_order_id(first) is True
    # BingX compares this account-wide identity case-insensitively.  The
    # account authority normalizes before reservation/collision checks.
    assert is_valid_falcon_client_order_id(first.lower()) is True
    assert is_valid_falcon_client_order_id("A" * 33) is False


@pytest.mark.parametrize(
    "field,replacement",
    [
        ("lifecycle_id", "LC-DIFFERENT"),
        ("entry_client_order_id", FACTUAL_ENTRY_CLIENT_IDS[0]),
        ("entry_order_id", "2078840000000000099"),
        ("symbol", "XRPUSDT"),
        ("side", "SHORT"),
        ("revision", 2),
        ("attempt", 1),
    ],
)
def test_each_immutable_identity_dimension_changes_the_id(field, replacement):
    baseline = generate_falcon_client_order_id(**identity())
    changed = generate_falcon_client_order_id(
        **identity(**{field: replacement})
    )
    assert changed != baseline


def test_initial_and_replacement_stop_have_distinct_role_namespaces():
    initial = generate_falcon_client_order_id(**identity())
    replacement = generate_falcon_client_order_id(
        **identity(operation=ROLE_REPLACEMENT_STOP)
    )

    assert initial.startswith("FDS1-")
    assert replacement.startswith("FRP1-")
    assert initial != replacement


def test_stop_one_and_stop_two_differ_by_revision_but_retry_is_idempotent():
    stop_one = generate_falcon_client_order_id(**identity(revision=1, attempt=0))
    stop_one_retry = generate_falcon_client_order_id(
        **identity(revision=1, attempt=0)
    )
    stop_two = generate_falcon_client_order_id(**identity(revision=2, attempt=0))

    assert stop_one_retry == stop_one
    assert stop_two != stop_one


def test_exchange_symbol_and_side_aliases_canonicalize_to_same_identity():
    canonical = generate_falcon_client_order_id(**identity())
    exchange_aliases = generate_falcon_client_order_id(
        **identity(symbol="SOL/USDT:USDT", side="BUY")
    )
    assert exchange_aliases == canonical


@pytest.mark.parametrize(
    "role,namespace",
    [
        (ROLE_ENTRY, "ENT1"),
        (ROLE_INITIAL_DISASTER_STOP, "FDS1"),
        (ROLE_REPLACEMENT_STOP, "FRP1"),
        (ROLE_ROLLBACK_STOP, "FRB1"),
        (ROLE_BREAK_EVEN_STOP, "FBE1"),
        (ROLE_TRAILING_STOP, "FTR1"),
        (ROLE_TP50_CLOSE, "FTP1"),
        (ROLE_EMERGENCY_TERMINAL_STOP_CLOSE, "FEC1"),
        (ROLE_MANAGED_CLOSE, "MCL1"),
    ],
)
def test_derived_order_roles_have_separate_namespaces(role, namespace):
    generated = generate_falcon_client_order_id(**identity(operation=role))
    assert generated.startswith(f"{namespace}-")
    assert len(generated) <= 32


def test_canonical_helpers_include_complete_identity_and_full_sha256():
    canonical = canonical_falcon_order_identity(**identity())
    serialized = canonical_falcon_order_identity_json(**identity())
    digest = canonical_falcon_order_identity_hash(**identity())

    assert canonical["schema"] == ACCOUNT_CLIENT_ORDER_ID_GENERATOR_VERSION
    assert canonical["schema"] == FALCON_CLIENT_ORDER_ID_GENERATOR_VERSION
    assert canonical["account_namespace"] == ACCOUNT_CLIENT_ORDER_ID_NAMESPACE
    assert canonical["account_namespace"] == (
        FALCON_CLIENT_ORDER_ID_ACCOUNT_NAMESPACE
    )
    assert canonical["bot"] == "FALCON"
    assert canonical["lifecycle_id"] == identity()["lifecycle_id"]
    assert canonical["entry_client_order_id"] == FACTUAL_ENTRY_CLIENT_IDS[-1]
    assert canonical["entry_order_id"] == "2078840000000000000"
    assert canonical["symbol"] == "SOLUSDT"
    assert canonical["side"] == "LONG"
    assert canonical["role"] == ROLE_INITIAL_DISASTER_STOP
    assert canonical["operation"] == ROLE_INITIAL_DISASTER_STOP
    assert canonical["stop_revision"] == canonical["revision"] == 0
    assert canonical["attempt_sequence"] == canonical["attempt"] == 0
    assert canonical["order_type"] == "STOP_MARKET"
    assert canonical["canonical_operation_id"].startswith("OP1-")
    assert canonical["attempt_id"].startswith("ATT1-")
    account_projection = json.loads(serialized)
    assert "operation" not in account_projection
    assert "revision" not in account_projection
    assert "attempt" not in account_projection
    assert account_projection["role"] == canonical["role"]
    assert account_projection["stop_revision"] == canonical["stop_revision"]
    assert account_projection["attempt_id"] == canonical["attempt_id"]
    assert re.fullmatch(r"[0-9a-f]{64}", digest)
    assert generate_falcon_client_order_id(**identity()).split("-", 1)[1] == (
        digest[:24].upper()
    )


def test_facade_delegates_to_account_wide_generator_exactly():
    canonical = canonical_falcon_order_identity(**identity())
    account_identity = {
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
    assert generate_falcon_client_order_id(**identity()) == (
        generate_account_client_order_id(**account_identity)
    )


def test_operation_and_attempt_ids_are_deterministic_from_revision_attempt():
    baseline = canonical_falcon_order_identity(**identity(revision=1, attempt=0))
    same = canonical_falcon_order_identity(**identity(revision=1, attempt=0))
    new_revision = canonical_falcon_order_identity(
        **identity(revision=2, attempt=0)
    )
    new_attempt = canonical_falcon_order_identity(
        **identity(revision=1, attempt=1)
    )

    assert baseline["canonical_operation_id"] == same["canonical_operation_id"]
    assert baseline["attempt_id"] == same["attempt_id"]
    assert baseline["canonical_operation_id"] != (
        new_revision["canonical_operation_id"]
    )
    assert baseline["attempt_id"] != new_revision["attempt_id"]
    assert baseline["canonical_operation_id"] == (
        new_attempt["canonical_operation_id"]
    )
    assert baseline["attempt_id"] != new_attempt["attempt_id"]


def test_large_identity_set_has_no_observed_collision():
    generated = {
        generate_falcon_client_order_id(
            **identity(
                lifecycle_id=f"LC-{number}",
                entry_client_order_id=f"FALCON-LIVE-{number}",
                entry_order_id=f"ORDER-{number}",
                revision=number % 11,
            )
        )
        for number in range(5000)
    }
    assert len(generated) == 5000


@pytest.mark.parametrize(
    "updates",
    [
        {"bot": "OTHER"},
        {"lifecycle_id": ""},
        {"entry_client_order_id": ""},
        {"entry_order_id": ""},
        {"symbol": ""},
        {"side": "BOTH"},
        {"operation": "UNKNOWN"},
        {"revision": -1},
        {"attempt": "1.5"},
    ],
)
def test_invalid_or_incomplete_derived_identity_fails_closed(updates):
    with pytest.raises(ValueError):
        generate_falcon_client_order_id(**identity(**updates))


def test_role_namespace_map_is_immutable():
    with pytest.raises(TypeError):
        FALCON_CLIENT_ORDER_ID_ROLE_NAMESPACES["NEW"] = "BAD1"


def test_module_is_pure_and_has_no_operational_imports_or_calls():
    tree = ast.parse(
        (ROOT / "falcon_client_order_id.py").read_text(encoding="utf-8")
    )
    imported = set()
    called = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                called.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                called.add(node.func.attr)

    assert imported <= {
        "__future__",
        "account_client_order_id",
        "hashlib",
        "typing",
    }
    assert imported.isdisjoint(
        {
            "broker",
            "bots",
            "redis",
            "requests",
            "socket",
            "threading",
            "trade_registry",
        }
    )
    assert called.isdisjoint(
        {
            "create_order",
            "fetch_order",
            "fetch_open_orders",
            "get_exchange",
            "set",
            "eval",
            "Thread",
        }
    )
