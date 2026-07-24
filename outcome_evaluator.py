# outcome_evaluator.py
# CENTRAL QUANT — OUTCOME EVALUATOR V1
# Versão: 2026-07-04-OUTCOME-EVALUATOR-V1
#
# Objetivo:
# - Avaliar trades PAPER fechados pelo Paper Lifecycle.
# - Gerar resultado estatístico por bot/setup/símbolo/lado.
# - Marcar posição como outcome_evaluated=true.
# - Registrar eventos em JSONL.
#
# Arquivo:
#   /opt/render/project/src/outcome_evaluator.py

import os
import json
import time
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, Optional

try:
    from trade_registry import (
        closed_trade_identity_state as _registry_closed_trade_identity_state,
        merge_closed_trade_records as _registry_merge_closed_trade_records,
    )
    CLOSED_IDENTITY_HELPERS_AVAILABLE = True
except Exception as _closed_identity_import_exc:
    _registry_closed_trade_identity_state = None
    _registry_merge_closed_trade_records = None
    CLOSED_IDENTITY_HELPERS_AVAILABLE = False
    CLOSED_IDENTITY_IMPORT_ERROR = type(_closed_identity_import_exc).__name__


VERSION = "2026-07-04-OUTCOME-EVALUATOR-V1"
CLOSED_EXECUTION_MARKER_VERSION = (
    "2026-07-23-OUTCOME-EVALUATOR-CLOSED-EXECUTION-IDENTITY-V1"
)

DATA_DIR = Path(os.getenv("CENTRAL_DATA_DIR", "/opt/render/project/src/data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

PAPER_POSITIONS_FILE = DATA_DIR / "paper_integrated_positions.json"
OUTCOME_LOG_FILE = DATA_DIR / "outcome_evaluator_log.jsonl"
OUTCOME_STATS_FILE = DATA_DIR / "outcome_stats.json"

OUTCOME_EVALUATOR_ENABLED = os.getenv("CENTRAL_OUTCOME_EVALUATOR_ENABLED", "true").lower() == "true"


def _now_br() -> str:
    return datetime.now().strftime("%d/%m/%Y %H:%M:%S")


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _append_jsonl(path: Path, payload: Dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _key(value: Any) -> str:
    return str(value or "UNKNOWN").upper().strip()


def _closed_execution_identity_projection(
    trade: Dict[str, Any]
) -> Dict[str, Any]:
    """Remove evaluator-owned fields before deriving immutable identity."""
    projected = dict(trade) if isinstance(trade, dict) else {}
    for field in (
        "outcome_evaluated",
        "outcome_evaluated_at",
        "outcome_version",
        "outcome_execution_key",
        "outcome_execution_identity_kind",
    ):
        projected.pop(field, None)
    return projected


def _closed_execution_identity(trade: Dict[str, Any]) -> Dict[str, Any]:
    if not CLOSED_IDENTITY_HELPERS_AVAILABLE or not callable(
        _registry_closed_trade_identity_state
    ):
        return {
            "ok": False,
            "reason": "CLOSED_IDENTITY_HELPER_UNAVAILABLE",
            "error_type": globals().get(
                "CLOSED_IDENTITY_IMPORT_ERROR", "HELPER_UNAVAILABLE"
            ),
        }
    try:
        state = _registry_closed_trade_identity_state(
            _closed_execution_identity_projection(trade)
        )
    except Exception as exc:
        return {
            "ok": False,
            "reason": "CLOSED_IDENTITY_HELPER_ERROR",
            "error_type": type(exc).__name__,
        }
    if not isinstance(state, dict) or not str(
        state.get("canonical_key") or ""
    ).strip():
        return {
            "ok": False,
            "reason": "CLOSED_IDENTITY_UNAVAILABLE",
        }
    return {
        "ok": True,
        "state": state,
        "canonical_key": str(state.get("canonical_key") or "").strip(),
        "identity_kind": str(state.get("identity_kind") or "UNKNOWN"),
        "has_alias_conflict": bool(state.get("has_alias_conflict")),
        "alias_conflicts": list(state.get("alias_conflicts") or []),
    }


def _closed_execution_marker_record(
    trade: Dict[str, Any], identity: Dict[str, Any]
) -> Dict[str, Any]:
    """Persist only the identity fields required to prove a future retry."""
    state = identity.get("state") if isinstance(identity, dict) else {}
    state = state if isinstance(state, dict) else {}
    legacy = state.get("legacy_fallback")
    legacy = legacy if isinstance(legacy, dict) else {}
    marker_record = {"status": "CLOSED"}
    for field in (
        "trade_id",
        "registry_mode",
        "execution_mode",
        "opened_at",
        "closed_at",
        "entry",
        "qty",
        "bot",
        "setup",
        "symbol",
        "side",
    ):
        value = legacy.get(field)
        if value not in (None, "", "UNKNOWN"):
            marker_record[field] = value

    strong = state.get("strong_identity")
    strong = strong if isinstance(strong, dict) else {}
    for field in ("lifecycle_id", "client_order_id", "order_id"):
        value = strong.get(field)
        if value not in (None, ""):
            marker_record[field] = value

    for specific in state.get("specific_identity_states") or []:
        if not isinstance(specific, dict) or specific.get("conflict"):
            continue
        field = str(specific.get("field") or "").strip()
        value = specific.get("value")
        if field and value not in (None, ""):
            marker_record[field] = value

    # A source may expose a useful identity field that is not needed by the
    # canonical helper today. Preserve no metadata or arbitrary payload here.
    if not marker_record.get("trade_id"):
        marker_record["trade_id"] = str(trade.get("trade_id") or "").strip()
    return marker_record


def _closed_execution_marker(
    trade: Dict[str, Any], identity: Dict[str, Any]
) -> Dict[str, Any]:
    return {
        "version": CLOSED_EXECUTION_MARKER_VERSION,
        "canonical_key": identity.get("canonical_key"),
        "identity_kind": identity.get("identity_kind"),
        "trade_id": str(trade.get("trade_id") or "").strip(),
        "identity_record": _closed_execution_marker_record(trade, identity),
    }


def _closed_execution_relation(
    candidate: Dict[str, Any], marker_record: Dict[str, Any]
) -> Dict[str, Any]:
    if not callable(_registry_merge_closed_trade_records):
        return {
            "relation": "ERROR",
            "reason": "CLOSED_IDENTITY_HELPER_UNAVAILABLE",
        }
    try:
        merged = _registry_merge_closed_trade_records(
            [
                _closed_execution_identity_projection(candidate),
                _closed_execution_identity_projection(marker_record),
            ],
            sources=["outcome_candidate", "outcome_marker"],
        )
    except Exception as exc:
        return {
            "relation": "ERROR",
            "reason": "CLOSED_IDENTITY_MERGE_ERROR",
            "error_type": type(exc).__name__,
        }
    records = (
        merged.get("records")
        if isinstance(merged, dict) and isinstance(merged.get("records"), list)
        else []
    )
    diagnostics = (
        merged.get("diagnostics")
        if isinstance(merged, dict)
        and isinstance(merged.get("diagnostics"), dict)
        else {}
    )
    if diagnostics.get("safe_to_commit") is True and len(records) == 1:
        return {"relation": "EQUIVALENT", "reason": "SAME_CLOSED_EXECUTION"}

    candidate_identity = _closed_execution_identity(candidate)
    marker_identity = _closed_execution_identity(marker_record)
    if not candidate_identity.get("ok") or not marker_identity.get("ok"):
        return {
            "relation": "ERROR",
            "reason": "CLOSED_IDENTITY_RELATION_UNAVAILABLE",
        }
    candidate_state = candidate_identity.get("state") or {}
    marker_state = marker_identity.get("state") or {}
    shared_tokens = set(candidate_state.get("merge_tokens") or []) & set(
        marker_state.get("merge_tokens") or []
    )
    same_key = bool(
        candidate_identity.get("canonical_key")
        and candidate_identity.get("canonical_key")
        == marker_identity.get("canonical_key")
    )
    if same_key or shared_tokens:
        return {
            "relation": "CONFLICT",
            "reason": "CLOSED_EXECUTION_IDENTITY_CONFLICT",
        }
    return {"relation": "DISTINCT", "reason": "DISTINCT_CLOSED_EXECUTION"}


def _closed_execution_evaluation_state(
    trade: Dict[str, Any],
    stats: Dict[str, Any],
    legacy_ambiguous_trade_ids: Optional[set] = None,
) -> Dict[str, Any]:
    identity = _closed_execution_identity(trade)
    if not identity.get("ok"):
        return {
            "status": "BLOCKED",
            "reason": identity.get("reason"),
            "identity": identity,
        }
    if identity.get("has_alias_conflict"):
        return {
            "status": "BLOCKED",
            "reason": "CLOSED_EXECUTION_IDENTITY_ALIAS_CONFLICT",
            "identity": identity,
        }

    markers = stats.get("evaluated_closed_executions") or []
    for marker_index, marker in enumerate(markers):
        if not isinstance(marker, dict):
            continue
        if (
            str(marker.get("canonical_key") or "")
            == identity.get("canonical_key")
            and str(marker.get("identity_kind") or "")
            == identity.get("identity_kind")
            and identity.get("identity_kind")
            in {
                "LEGACY_FALLBACK",
                "LEGACY_INCOMPLETE_EXACT_ONLY",
                "PARTIAL_STRONG_IDENTITY",
            }
        ):
            return {
                "status": "ALREADY_EVALUATED",
                "reason": "CLOSED_EXECUTION_ALREADY_EVALUATED",
                "identity": identity,
                "marker_index": marker_index,
            }
        marker_record = marker.get("identity_record")
        if not isinstance(marker_record, dict):
            continue
        relation = _closed_execution_relation(trade, marker_record)
        if relation.get("relation") == "EQUIVALENT":
            return {
                "status": "ALREADY_EVALUATED",
                "reason": "CLOSED_EXECUTION_ALREADY_EVALUATED",
                "identity": identity,
                "marker_index": marker_index,
            }
        if relation.get("relation") in {"CONFLICT", "ERROR"}:
            return {
                "status": "BLOCKED",
                "reason": (
                    "CLOSED_EXECUTION_MARKER_CONFLICT"
                    if relation.get("relation") == "CONFLICT"
                    else relation.get("reason")
                ),
                "identity": identity,
                "marker_index": marker_index,
                "relation": relation,
            }

    # V1 compatibility: a bare trade_id marker remains authoritative only for
    # records that themselves lack strong/specific execution identity. It must
    # never hide a later lifecycle/order-owned execution with the same trade_id.
    legacy_identity_kinds = {
        "LEGACY_FALLBACK",
        "LEGACY_INCOMPLETE_EXACT_ONLY",
    }
    trade_id = str(trade.get("trade_id") or "")
    legacy_ids = {
        str(item)
        for item in (stats.get("evaluated_trade_ids") or [])
        if item is not None
    }
    scoped_marker_exists = any(
        isinstance(marker, dict)
        and str(marker.get("trade_id") or "") == trade_id
        for marker in markers
    )
    if trade_id in set(legacy_ambiguous_trade_ids or set()):
        return {
            "status": "BLOCKED",
            "reason": "LEGACY_TRADE_ID_MARKER_AMBIGUOUS",
            "identity": identity,
            "legacy_marker": True,
        }
    if (
        identity.get("identity_kind") in legacy_identity_kinds
        and trade_id in legacy_ids
        and not scoped_marker_exists
    ):
        return {
            "status": "ALREADY_EVALUATED",
            "reason": "LEGACY_TRADE_ID_MARKER_MATCH",
            "identity": identity,
            "legacy_marker": True,
        }
    return {
        "status": "PENDING",
        "reason": "CLOSED_EXECUTION_NOT_EVALUATED",
        "identity": identity,
    }


def _legacy_marker_ambiguous_trade_ids(
    positions: Any, stats: Dict[str, Any]
) -> set:
    legacy_ids = {
        str(item)
        for item in (stats.get("evaluated_trade_ids") or [])
        if item is not None
    }
    scoped_ids = {
        str(marker.get("trade_id") or "")
        for marker in (stats.get("evaluated_closed_executions") or [])
        if isinstance(marker, dict)
    }
    identities_by_trade_id: Dict[str, set] = {}
    for trade in positions if isinstance(positions, list) else []:
        if not isinstance(trade, dict) or trade.get("status") != "CLOSED":
            continue
        trade_id = str(trade.get("trade_id") or "")
        if not trade_id or trade_id not in legacy_ids or trade_id in scoped_ids:
            continue
        identity = _closed_execution_identity(trade)
        if (
            identity.get("ok")
            and identity.get("identity_kind")
            in {"LEGACY_FALLBACK", "LEGACY_INCOMPLETE_EXACT_ONLY"}
        ):
            identities_by_trade_id.setdefault(trade_id, set()).add(
                str(identity.get("canonical_key") or "")
            )
    return {
        trade_id
        for trade_id, identities in identities_by_trade_id.items()
        if len(identities) > 1
    }


def _empty_bucket() -> Dict[str, Any]:
    return {
        "trades": 0,
        "wins": 0,
        "losses": 0,
        "breakeven": 0,
        "tp50_hits": 0,
        "pnl_total_pct": 0.0,
        "pnl_avg_pct": 0.0,
        "r_total": 0.0,
        "r_avg": 0.0,
        "win_rate_pct": 0.0,
        "tp50_hit_rate_pct": 0.0,
        "best_trade_pct": None,
        "worst_trade_pct": None,
        "last_trade_at": None,
    }


def _update_bucket(bucket: Dict[str, Any], trade: Dict[str, Any]) -> Dict[str, Any]:
    pnl = _safe_float(trade.get("pnl_pct"))
    r = _safe_float(trade.get("r_result"))

    bucket["trades"] = int(bucket.get("trades", 0)) + 1

    if pnl > 0:
        bucket["wins"] = int(bucket.get("wins", 0)) + 1
    elif pnl < 0:
        bucket["losses"] = int(bucket.get("losses", 0)) + 1
    else:
        bucket["breakeven"] = int(bucket.get("breakeven", 0)) + 1

    if trade.get("tp50_hit"):
        bucket["tp50_hits"] = int(bucket.get("tp50_hits", 0)) + 1

    bucket["pnl_total_pct"] = round(_safe_float(bucket.get("pnl_total_pct")) + pnl, 4)
    bucket["r_total"] = round(_safe_float(bucket.get("r_total")) + r, 4)

    trades = max(1, int(bucket.get("trades", 1)))
    bucket["pnl_avg_pct"] = round(bucket["pnl_total_pct"] / trades, 4)
    bucket["r_avg"] = round(bucket["r_total"] / trades, 4)
    bucket["win_rate_pct"] = round((int(bucket.get("wins", 0)) / trades) * 100, 2)
    bucket["tp50_hit_rate_pct"] = round((int(bucket.get("tp50_hits", 0)) / trades) * 100, 2)

    if bucket.get("best_trade_pct") is None or pnl > _safe_float(bucket.get("best_trade_pct")):
        bucket["best_trade_pct"] = pnl
    if bucket.get("worst_trade_pct") is None or pnl < _safe_float(bucket.get("worst_trade_pct")):
        bucket["worst_trade_pct"] = pnl

    bucket["last_trade_at"] = trade.get("closed_at") or _now_br()
    return bucket


def outcome_evaluator_health() -> Dict[str, Any]:
    positions = _read_json(PAPER_POSITIONS_FILE, [])
    closed = [p for p in positions if isinstance(p, dict) and p.get("status") == "CLOSED"]
    stats = _read_json(
        OUTCOME_STATS_FILE,
        {
            "evaluated_trade_ids": [],
            "evaluated_closed_execution_keys": [],
            "evaluated_closed_executions": [],
        },
    )
    stats = stats if isinstance(stats, dict) else {}
    legacy_ambiguous_trade_ids = _legacy_marker_ambiguous_trade_ids(
        positions, stats
    )
    pending = []
    identity_blocked = []
    for trade in closed:
        evaluation_state = _closed_execution_evaluation_state(
            trade, stats, legacy_ambiguous_trade_ids
        )
        if evaluation_state.get("status") == "BLOCKED":
            identity_blocked.append(trade)
        elif (
            not trade.get("outcome_evaluated")
            and evaluation_state.get("status") == "PENDING"
        ):
            pending.append(trade)

    return {
        "ok": True,
        "module": "outcome_evaluator",
        "loaded": True,
        "version": VERSION,
        "generated_at": _now_br(),
        "enabled": OUTCOME_EVALUATOR_ENABLED,
        "closed_positions": len(closed),
        "pending_evaluation": len(pending),
        "identity_blocked": len(identity_blocked),
        "closed_identity_helpers_available": CLOSED_IDENTITY_HELPERS_AVAILABLE,
        "files": {
            "paper_positions": str(PAPER_POSITIONS_FILE),
            "outcome_log": str(OUTCOME_LOG_FILE),
            "outcome_stats": str(OUTCOME_STATS_FILE),
        },
        "notes": [
            "Outcome Evaluator V1 avalia trades PAPER fechados.",
            "Gera estatística por bot, setup, símbolo e lado.",
            "Próxima fase: alimentar Adaptive Weights.",
        ],
    }


def evaluate_closed_paper_trades(force: bool = False) -> Dict[str, Any]:
    if not OUTCOME_EVALUATOR_ENABLED:
        return {
            "ok": False,
            "status": "OUTCOME_EVALUATOR_DISABLED",
            "generated_at": _now_br(),
            "version": VERSION,
        }

    positions = _read_json(PAPER_POSITIONS_FILE, [])
    stats = _read_json(OUTCOME_STATS_FILE, {
        "version": VERSION,
        "updated_at": None,
        "global": _empty_bucket(),
        "by_bot": {},
        "by_setup": {},
        "by_symbol": {},
        "by_side": {},
        "evaluated_trade_ids": [],
        "evaluated_closed_execution_keys": [],
        "evaluated_closed_executions": [],
    })
    if not isinstance(stats, dict):
        stats = {
            "version": VERSION,
            "updated_at": None,
            "global": _empty_bucket(),
            "by_bot": {},
            "by_setup": {},
            "by_symbol": {},
            "by_side": {},
            "evaluated_trade_ids": [],
            "evaluated_closed_execution_keys": [],
            "evaluated_closed_executions": [],
        }

    evaluated_ids = set(str(x) for x in stats.get("evaluated_trade_ids", []))
    evaluated_execution_keys = set(
        str(x)
        for x in stats.get("evaluated_closed_execution_keys", [])
        if x is not None
    )
    evaluated_now = []
    skipped = []
    legacy_ambiguous_trade_ids = _legacy_marker_ambiguous_trade_ids(
        positions, stats
    )

    for pos in positions:
        if not isinstance(pos, dict):
            continue
        if pos.get("status") != "CLOSED":
            continue

        trade_id = str(pos.get("trade_id") or "")
        if not trade_id:
            skipped.append({"reason": "missing_trade_id", "trade": pos})
            continue

        evaluation_state = _closed_execution_evaluation_state(
            pos, stats, legacy_ambiguous_trade_ids
        )
        identity = evaluation_state.get("identity") or {}
        if evaluation_state.get("status") == "BLOCKED":
            skipped.append(
                {
                    "trade_id": trade_id,
                    "reason": evaluation_state.get("reason"),
                    "closed_execution_key": identity.get("canonical_key"),
                    "closed_execution_identity_kind": identity.get(
                        "identity_kind"
                    ),
                    "identity_conflicts": identity.get("alias_conflicts") or [],
                }
            )
            continue

        already_evaluated = bool(pos.get("outcome_evaluated")) or (
            evaluation_state.get("status") == "ALREADY_EVALUATED"
        )
        if already_evaluated and not force:
            skipped.append(
                {
                    "trade_id": trade_id,
                    "reason": "already_evaluated",
                    "identity_reason": evaluation_state.get("reason"),
                    "closed_execution_key": identity.get("canonical_key"),
                }
            )
            continue

        outcome = {
            "trade_id": trade_id,
            "closed_execution_key": identity.get("canonical_key"),
            "closed_execution_identity_kind": identity.get("identity_kind"),
            "bot": _key(pos.get("bot")),
            "setup": _key(pos.get("setup")),
            "symbol": _key(pos.get("symbol")),
            "side": _key(pos.get("side")),
            "entry": pos.get("entry"),
            "exit_price": pos.get("exit_price"),
            "pnl_pct": _safe_float(pos.get("pnl_pct")),
            "r_result": _safe_float(pos.get("r_result")),
            "tp50_hit": bool(pos.get("tp50_hit")),
            "breakeven": bool(pos.get("breakeven")),
            "close_reason": pos.get("close_reason"),
            "opened_at": pos.get("opened_at"),
            "closed_at": pos.get("closed_at"),
            "source": "PAPER",
            "evaluated_at": _now_br(),
        }

        stats["global"] = _update_bucket(stats.get("global") or _empty_bucket(), outcome)

        for group_name, key_name in [
            ("by_bot", outcome["bot"]),
            ("by_setup", outcome["setup"]),
            ("by_symbol", outcome["symbol"]),
            ("by_side", outcome["side"]),
        ]:
            group = stats.setdefault(group_name, {})
            group.setdefault(key_name, _empty_bucket())
            group[key_name] = _update_bucket(group[key_name], outcome)

        if trade_id not in evaluated_ids:
            stats.setdefault("evaluated_trade_ids", []).append(trade_id)
            evaluated_ids.add(trade_id)

        execution_key = str(identity.get("canonical_key") or "").strip()
        if execution_key and execution_key not in evaluated_execution_keys:
            stats.setdefault("evaluated_closed_execution_keys", []).append(
                execution_key
            )
            evaluated_execution_keys.add(execution_key)
        if evaluation_state.get("status") != "ALREADY_EVALUATED":
            stats.setdefault("evaluated_closed_executions", []).append(
                _closed_execution_marker(pos, identity)
            )

        pos["outcome_evaluated"] = True
        pos["outcome_evaluated_at"] = _now_br()
        pos["outcome_version"] = VERSION
        pos["outcome_execution_key"] = execution_key
        pos["outcome_execution_identity_kind"] = identity.get(
            "identity_kind"
        )

        event = {
            "event": "PAPER_OUTCOME_EVALUATED",
            "version": VERSION,
            "generated_at": _now_br(),
            "epoch": time.time(),
            "outcome": outcome,
        }
        _append_jsonl(OUTCOME_LOG_FILE, event)
        evaluated_now.append(outcome)

    stats["updated_at"] = _now_br()
    _write_json(PAPER_POSITIONS_FILE, positions)
    _write_json(OUTCOME_STATS_FILE, stats)

    return {
        "ok": True,
        "status": "OUTCOME_EVALUATION_DONE",
        "version": VERSION,
        "generated_at": _now_br(),
        "evaluated_count": len(evaluated_now),
        "skipped_count": len(skipped),
        "evaluated": evaluated_now,
        "skipped": skipped[:50],
        "stats": stats,
    }


def get_outcome_stats() -> Dict[str, Any]:
    stats = _read_json(OUTCOME_STATS_FILE, {
        "version": VERSION,
        "updated_at": None,
        "global": _empty_bucket(),
        "by_bot": {},
        "by_setup": {},
        "by_symbol": {},
        "by_side": {},
        "evaluated_trade_ids": [],
        "evaluated_closed_execution_keys": [],
        "evaluated_closed_executions": [],
    })
    return {
        "ok": True,
        "generated_at": _now_br(),
        "stats": stats,
    }


def read_outcome_log(limit: int = 20) -> Dict[str, Any]:
    if not OUTCOME_LOG_FILE.exists():
        return {
            "ok": True,
            "generated_at": _now_br(),
            "count": 0,
            "items": [],
        }

    lines = OUTCOME_LOG_FILE.read_text(encoding="utf-8").splitlines()
    selected = lines[-max(1, int(limit)):]

    items = []
    for line in selected:
        try:
            items.append(json.loads(line))
        except Exception:
            continue

    return {
        "ok": True,
        "generated_at": _now_br(),
        "count": len(items),
        "items": items,
    }
