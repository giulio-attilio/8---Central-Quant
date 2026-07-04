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


VERSION = "2026-07-04-OUTCOME-EVALUATOR-V1"

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
    pending = [p for p in closed if not p.get("outcome_evaluated")]

    return {
        "ok": True,
        "module": "outcome_evaluator",
        "loaded": True,
        "version": VERSION,
        "generated_at": _now_br(),
        "enabled": OUTCOME_EVALUATOR_ENABLED,
        "closed_positions": len(closed),
        "pending_evaluation": len(pending),
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
    })

    evaluated_ids = set(str(x) for x in stats.get("evaluated_trade_ids", []))
    evaluated_now = []
    skipped = []

    for pos in positions:
        if not isinstance(pos, dict):
            continue
        if pos.get("status") != "CLOSED":
            continue

        trade_id = str(pos.get("trade_id") or "")
        if not trade_id:
            skipped.append({"reason": "missing_trade_id", "trade": pos})
            continue

        already_evaluated = bool(pos.get("outcome_evaluated")) or trade_id in evaluated_ids
        if already_evaluated and not force:
            skipped.append({"trade_id": trade_id, "reason": "already_evaluated"})
            continue

        outcome = {
            "trade_id": trade_id,
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

        pos["outcome_evaluated"] = True
        pos["outcome_evaluated_at"] = _now_br()
        pos["outcome_version"] = VERSION

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
