from __future__ import annotations

import ast
import hashlib
import json
import uuid
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
MAIN_FILE = ROOT / "main.py"


_MAIN_FUNCTIONS = {
    "_closed_trade_identity_state_v1",
    "_merge_closed_trade_records_v1",
    "_closed_trade_record_relation_v1",
    "_pppa_v1_public",
    "_pppa_v1_deep_find",
    "_pppa_v1_float",
    "_pppa_v1_norm_symbol",
    "_pppa_v1_norm_side",
    "_pppa_v1_event_key",
    "_pppa_v1_closed_trade_id_from_event",
    "_pppa_v1_norm_text",
    "_pppa_v1_round_key_num",
    "_pppa_v1_closed_at_key",
    "_pppa_v1_source_event_key_from_closed",
    "_pppa_v1_closed_semantic_fingerprint",
    "_pppa_v1_closed_registry_record",
    "_pppa_v1_closed_registry_identity",
    "_pppa_v1_closed_canonical_key",
    "_pppa_v1_duplicate_reason_for_group",
    "_pppa_v1_pnl_fields_from_event",
    "_pppa_v1_closed_source_rank",
    "_pppa_v1_registry_closed_as_events",
    "_pppa_v1_build_pnl_stats",
}

_ALIASES = {
    "lifecycle_id": ("lifecycle_id", "trade_lifecycle_id"),
    "client_order_id": (
        "client_order_id",
        "clientOrderId",
        "clientOrderID",
        "client_tag",
    ),
    "order_id": (
        "open_order_id",
        "broker_order_id",
        "order_id",
        "orderId",
        "live_order_id",
        "entry_order_id",
    ),
}


class _AuditStage:
    def __enter__(self):
        return self

    def finish(self, *_args, **_kwargs):
        return None

    def __exit__(self, *_args):
        return False


def _values(record, field):
    values = []
    containers = [record]
    for key in ("metadata", "outcome"):
        nested = record.get(key)
        if isinstance(nested, dict):
            containers.append(nested)
    for container in containers:
        for alias in _ALIASES[field]:
            value = container.get(alias)
            if value is None or not str(value).strip():
                continue
            normalized = str(value).strip()
            if field == "client_order_id":
                normalized = normalized.upper()
            if normalized not in values:
                values.append(normalized)
    return values


def _identity_state(record):
    lifecycle = _values(record, "lifecycle_id")
    client = _values(record, "client_order_id")
    order = _values(record, "order_id")
    conflicts = [
        field
        for field, values in (
            ("lifecycle_id", lifecycle),
            ("client_order_id", client),
            ("order_id", order),
        )
        if len(values) > 1
    ]
    fingerprint = hashlib.sha256(
        json.dumps(record, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    if conflicts:
        key = f"conflict|{fingerprint}"
        kind = "CONFLICT_QUARANTINED"
    elif lifecycle:
        key = f"lifecycle|{lifecycle[0]}"
        kind = "LIFECYCLE_ID"
    elif client and order:
        key = f"client_order|{client[0]}|{order[0]}"
        kind = "CLIENT_AND_ORDER_ID"
    else:
        key = "legacy|" + "|".join(
            str(record.get(field) or "").strip().upper()
            for field in (
                "trade_id",
                "registry_mode",
                "execution_mode",
                "opened_at",
                "closed_at",
                "entry",
                "qty",
            )
        )
        kind = "LEGACY_COMPOUND"
    tokens = []
    if len(lifecycle) == 1:
        tokens.append(f"lifecycle|{lifecycle[0]}")
    if len(client) == 1 and len(order) == 1:
        tokens.append(f"client_order|{client[0]}|{order[0]}")
    return {
        "canonical_key": key,
        "identity_kind": kind,
        "merge_tokens": tokens,
        "fingerprint": fingerprint,
        "trade_id": str(record.get("trade_id") or ""),
        "has_alias_conflict": bool(conflicts),
        "alias_conflicts": conflicts,
    }


def _pair_relation(left, right):
    left_lifecycle = _values(left, "lifecycle_id")
    right_lifecycle = _values(right, "lifecycle_id")
    left_client = _values(left, "client_order_id")
    right_client = _values(right, "client_order_id")
    left_order = _values(left, "order_id")
    right_order = _values(right, "order_id")

    if _identity_state(left)["has_alias_conflict"] or _identity_state(right)[
        "has_alias_conflict"
    ]:
        return "CONFLICT"

    if left_lifecycle and right_lifecycle:
        if left_lifecycle[0] != right_lifecycle[0]:
            return "DISTINCT"
        if left_client and right_client and left_client[0] != right_client[0]:
            return "CONFLICT"
        if left_order and right_order and left_order[0] != right_order[0]:
            return "CONFLICT"
        return "EQUIVALENT"

    if left_client and left_order and right_client and right_order:
        if (
            left_client[0] == right_client[0]
            and left_order[0] == right_order[0]
        ):
            return "EQUIVALENT"
        return "DISTINCT"

    return "DISTINCT"


def _merge_closed_trade_records(records, sources=None):
    del sources
    clean = [dict(record) for record in records if isinstance(record, dict)]
    if len(clean) != 2:
        return {
            "records": clean,
            "diagnostics": {"safe_to_commit": True},
        }
    relation = _pair_relation(clean[0], clean[1])
    if relation == "EQUIVALENT":
        preferred = max(
            clean,
            key=lambda record: sum(
                len(_values(record, field)) for field in _ALIASES
            ),
        )
        return {
            "records": [preferred],
            "diagnostics": {"safe_to_commit": True},
        }
    return {
        "records": clean,
        "diagnostics": {"safe_to_commit": relation == "DISTINCT"},
    }


def _compile_subject():
    tree = ast.parse(MAIN_FILE.read_text(encoding="utf-8"))
    selected = []
    found = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name in _MAIN_FUNCTIONS:
                node.decorator_list = []
                selected.append(node)
                found.add(node.name)
    assert found == _MAIN_FUNCTIONS, sorted(_MAIN_FUNCTIONS - found)
    module = ast.Module(body=selected, type_ignores=[])
    ast.fix_missing_locations(module)
    registry = SimpleNamespace(
        closed_trade_identity_state=_identity_state,
        merge_closed_trade_records=_merge_closed_trade_records,
    )
    namespace = {
        "central_trade_registry": registry,
        "hashlib": hashlib,
        "json": json,
        "uuid": uuid,
        "predator_audit_stage": lambda *_args, **_kwargs: _AuditStage(),
    }
    exec(compile(module, str(MAIN_FILE), "exec"), namespace)
    return namespace["_pppa_v1_build_pnl_stats"]


def _closed_event(
    *,
    lifecycle_id=None,
    client_order_id=None,
    order_id=None,
    source,
    closed_at,
    pnl_pct,
):
    raw = {
        "trade_id": "PREDATOR:SMART_PREDATOR:XRPUSDT:LONG",
        "bot": "PREDATOR",
        "setup": "SMART_PREDATOR",
        "symbol": "XRPUSDT",
        "side": "LONG",
        "entry": 1.0,
        "exit_price": 1.0 + (pnl_pct / 100),
        "pnl_pct": pnl_pct,
        "closed_at": closed_at,
        "status": "CLOSED",
    }
    if lifecycle_id is not None:
        raw["lifecycle_id"] = lifecycle_id
    if client_order_id is not None:
        raw["client_order_id"] = client_order_id
    if order_id is not None:
        raw["broker_order_id"] = order_id
    return {
        "source": source,
        "kind": "PAPER_CLOSED",
        "key": f"{source}|{lifecycle_id or client_order_id}|{closed_at}",
        "ts": closed_at,
        "symbol": "XRPUSDT",
        "side": "LONG",
        "setup": "SMART_PREDATOR",
        "status": "CLOSED",
        "sent": False,
        "raw_public": raw,
    }


def test_same_trade_id_distinct_strong_executions_remain_two():
    build = _compile_subject()
    events = [
        _closed_event(
            lifecycle_id="LC-ONE",
            client_order_id="CLIENT-ONE",
            order_id="ORDER-ONE",
            source="history_events",
            closed_at="2026-07-20T10:00:00Z",
            pnl_pct=1.0,
        ),
        _closed_event(
            lifecycle_id="LC-TWO",
            client_order_id="CLIENT-TWO",
            order_id="ORDER-TWO",
            source="history_events",
            closed_at="2026-07-21T10:00:00Z",
            pnl_pct=2.0,
        ),
    ]

    result = build(events, {"closed_trades": []})

    assert result["raw_paper_closed_count"] == 2
    assert result["unique_paper_closed_count"] == 2
    assert result["duplicate_closed_count"] == 0
    assert result["closed_identity_conflict_count"] == 0
    assert result["pnl_total_pct"] == 3.0


def test_complete_and_client_order_projection_of_same_execution_deduplicate():
    build = _compile_subject()
    events = [
        _closed_event(
            lifecycle_id="LC-SAME",
            client_order_id="CLIENT-SAME",
            order_id="ORDER-SAME",
            source="history_events",
            closed_at="2026-07-20T10:00:00Z",
            pnl_pct=1.25,
        ),
        _closed_event(
            client_order_id="client-same",
            order_id="ORDER-SAME",
            source="trade_registry_closed",
            closed_at="2026-07-20T10:00:00Z",
            pnl_pct=1.25,
        ),
    ]

    result = build(events, {"closed_trades": []})

    assert result["raw_paper_closed_count"] == 2
    assert result["unique_paper_closed_count"] == 1
    assert result["duplicate_closed_count"] == 1
    assert result["duplicate_closed_trade_count"] == 1
    assert result["closed_identity_conflict_count"] == 0
    assert result["sources_per_trade"][0]["source_count"] == 2


def test_same_lifecycle_with_divergent_client_order_is_preserved_and_reported():
    build = _compile_subject()
    events = [
        _closed_event(
            lifecycle_id="LC-CONFLICT",
            client_order_id="CLIENT-A",
            order_id="ORDER-A",
            source="history_events",
            closed_at="2026-07-20T10:00:00Z",
            pnl_pct=1.0,
        ),
        _closed_event(
            lifecycle_id="LC-CONFLICT",
            client_order_id="CLIENT-B",
            order_id="ORDER-B",
            source="trade_registry_closed",
            closed_at="2026-07-20T10:01:00Z",
            pnl_pct=-0.5,
        ),
    ]

    result = build(events, {"closed_trades": []})

    assert result["raw_paper_closed_count"] == 2
    assert result["unique_paper_closed_count"] == 2
    assert result["duplicate_closed_count"] == 0
    assert result["closed_identity_conflict_count"] == 1
    assert result["closed_identity_conflicts"][0]["reason"] == (
        "CLOSED_EXECUTION_IDENTITY_CONFLICT"
    )
    assert result["pnl_total_pct"] == 0.5
