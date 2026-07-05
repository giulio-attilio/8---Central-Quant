# -*- coding: utf-8 -*-
"""
REAL PNL/R MAPPER — CENTRAL QUANT V2.4
Versão: 2026-07-05-REAL-PNL-R-MAPPER-V2.4

Objetivo:
- Mapear PnL real e R real a partir de trades encerrados.
- Unificar leitura de History, Trade Registry, Decision Log e possíveis eventos de fechamento.
- Gerar métricas por bot, setup, símbolo e lado.
- Rodar em modo observacional, sem executar ordens e sem alterar risco/lote.

Arquivos lidos, quando existirem:
- /opt/render/project/src/data/trade_registry.jsonl
- /opt/render/project/src/data/history_events.jsonl
- /opt/render/project/src/data/history_export.json
- /opt/render/project/src/data/decision_log.jsonl

Arquivos gerados:
- /opt/render/project/src/data/real_pnl_r_map.json
- /opt/render/project/src/data/real_pnl_r_events.jsonl
"""

from __future__ import annotations

import json
import math
import os
import time
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

VERSION = "2026-07-05-REAL-PNL-R-MAPPER-V2.4"

DATA_DIR = os.environ.get("CENTRAL_DATA_DIR", "/opt/render/project/src/data")
TRADE_REGISTRY_FILE = os.path.join(DATA_DIR, "trade_registry.jsonl")
HISTORY_EVENTS_FILE = os.path.join(DATA_DIR, "history_events.jsonl")
HISTORY_EXPORT_FILE = os.path.join(DATA_DIR, "history_export.json")
DECISION_LOG_FILE = os.path.join(DATA_DIR, "decision_log.jsonl")
OUTPUT_MAP_FILE = os.path.join(DATA_DIR, "real_pnl_r_map.json")
OUTPUT_EVENTS_FILE = os.path.join(DATA_DIR, "real_pnl_r_events.jsonl")


def _now_br() -> str:
    return datetime.now().strftime("%d/%m/%Y %H:%M:%S")


def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None:
            return default
        if isinstance(value, str):
            value = value.strip().replace("%", "").replace(",", ".")
            if value == "":
                return default
        f = float(value)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except Exception:
        return default


def _safe_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def _read_jsonl(path: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    if not os.path.exists(path):
        return []
    rows: List[Dict[str, Any]] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                    if isinstance(item, dict):
                        rows.append(item)
                except Exception:
                    continue
        if limit and len(rows) > limit:
            return rows[-limit:]
        return rows
    except Exception:
        return []


def _read_json(path: str) -> Any:
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _write_json(path: str, payload: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)
    os.replace(tmp, path)


def _append_jsonl(path: str, payload: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def _normalize_side(side: Any) -> str:
    s = _safe_str(side).upper()
    if s in {"BUY", "LONG"}:
        return "LONG"
    if s in {"SELL", "SHORT"}:
        return "SHORT"
    return s or "UNKNOWN"


def _normalize_symbol(symbol: Any) -> str:
    s = _safe_str(symbol).upper()
    return s.replace("/", "").replace(":USDT", "")


def _pick(d: Dict[str, Any], keys: Iterable[str], default: Any = None) -> Any:
    for k in keys:
        if k in d and d.get(k) is not None:
            return d.get(k)
    return default


def _candidate_trade_id(row: Dict[str, Any]) -> str:
    explicit = _pick(row, ["trade_id", "id", "decision_id", "position_id", "signal_id"])
    if explicit:
        return _safe_str(explicit)

    bot = _safe_str(_pick(row, ["bot", "robot", "strategy"]), "UNKNOWN")
    setup = _safe_str(_pick(row, ["setup", "setup_name"]), "UNKNOWN")
    symbol = _normalize_symbol(_pick(row, ["symbol", "pair", "market"]))
    side = _normalize_side(_pick(row, ["side", "direction"])).upper()
    entry_time = _safe_str(_pick(row, ["entry_time", "opened_at", "created_at", "timestamp", "epoch"]), "NO_TIME")
    return f"{bot}:{setup}:{symbol}:{side}:{entry_time}"


def _extract_price(row: Dict[str, Any], names: List[str]) -> Optional[float]:
    return _safe_float(_pick(row, names))


def _infer_closed(row: Dict[str, Any]) -> bool:
    status = _safe_str(_pick(row, ["status", "state"])).upper()
    event = _safe_str(_pick(row, ["event", "event_raw", "type"])).upper()
    if status in {"CLOSED", "CLOSE", "DONE", "FINISHED", "EXITED"}:
        return True
    if event in {"TRADE_CLOSED", "CLOSE", "CLOSED", "POSITION_CLOSED", "EXIT"}:
        return True
    if _extract_price(row, ["exit", "exit_price", "close", "close_price", "avg_exit_price"]):
        return True
    return False


def _compute_pnl_pct(side: str, entry: Optional[float], exit_price: Optional[float]) -> Optional[float]:
    if not entry or not exit_price or entry <= 0:
        return None
    if side == "SHORT":
        return ((entry - exit_price) / entry) * 100.0
    return ((exit_price - entry) / entry) * 100.0


def _compute_r(side: str, entry: Optional[float], stop: Optional[float], exit_price: Optional[float], pnl_pct: Optional[float]) -> Optional[float]:
    if not entry or not stop or not exit_price or entry <= 0:
        return None
    if side == "SHORT":
        risk_per_unit = stop - entry
        reward_per_unit = entry - exit_price
    else:
        risk_per_unit = entry - stop
        reward_per_unit = exit_price - entry
    if risk_per_unit <= 0:
        return None
    return reward_per_unit / risk_per_unit


def _normalize_trade(row: Dict[str, Any], source: str) -> Optional[Dict[str, Any]]:
    if not isinstance(row, dict):
        return None

    event_payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    merged = dict(row)
    merged.update({k: v for k, v in event_payload.items() if k not in merged or merged.get(k) is None})

    side = _normalize_side(_pick(merged, ["side", "direction", "position_side"]))
    symbol = _normalize_symbol(_pick(merged, ["symbol", "pair", "market"]))
    bot = _safe_str(_pick(merged, ["bot", "robot", "strategy", "bot_name"]), "UNKNOWN")
    setup = _safe_str(_pick(merged, ["setup", "setup_name", "strategy_setup"]), "UNKNOWN")

    entry = _extract_price(merged, ["entry", "entry_price", "avg_entry_price", "open_price"])
    stop = _extract_price(merged, ["sl", "stop", "stop_loss", "initial_sl", "initial_stop"])
    exit_price = _extract_price(merged, ["exit", "exit_price", "close", "close_price", "avg_exit_price"])

    pnl_pct = _safe_float(_pick(merged, ["pnl_pct", "pnl_percent", "profit_pct", "real_pnl_pct"]))
    if pnl_pct is None:
        pnl_pct = _compute_pnl_pct(side, entry, exit_price)

    r_value = _safe_float(_pick(merged, ["r", "r_result", "real_r", "r_multiple"]))
    if r_value is None:
        r_value = _compute_r(side, entry, stop, exit_price, pnl_pct)

    pnl_usdt = _safe_float(_pick(merged, ["pnl_usdt", "realized_pnl", "realizedPnl", "profit_usdt", "net_pnl_usdt"]))
    qty = _safe_float(_pick(merged, ["qty", "quantity", "size", "amount", "contracts"]))

    closed = _infer_closed(merged)
    if not closed and pnl_pct is None and r_value is None and pnl_usdt is None:
        return None

    trade_id = _candidate_trade_id(merged)
    return {
        "trade_id": trade_id,
        "source": source,
        "bot": bot,
        "setup": setup,
        "symbol": symbol or "UNKNOWN",
        "side": side or "UNKNOWN",
        "entry": entry,
        "stop": stop,
        "exit": exit_price,
        "qty": qty,
        "pnl_pct": round(pnl_pct, 6) if pnl_pct is not None else None,
        "pnl_usdt": round(pnl_usdt, 6) if pnl_usdt is not None else None,
        "r": round(r_value, 6) if r_value is not None else None,
        "status": "CLOSED" if closed else "MAPPED",
        "closed": bool(closed),
        "raw_event": _safe_str(_pick(merged, ["event", "event_raw", "type", "status"]), ""),
        "timestamp": _pick(merged, ["timestamp", "epoch", "created_at", "entry_time", "closed_at", "generated_at"]),
    }


def _load_history_export_rows() -> List[Dict[str, Any]]:
    data = _read_json(HISTORY_EXPORT_FILE)
    if data is None:
        return []
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for key in ["trades", "events", "closed_trades", "history", "rows"]:
            value = data.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
        return [data]
    return []


def _merge_trades(trades: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_id: Dict[str, Dict[str, Any]] = {}
    source_rank = {"history_events": 4, "history_export": 3, "trade_registry": 2, "decision_log": 1}

    for t in trades:
        tid = t.get("trade_id") or _candidate_trade_id(t)
        if tid not in by_id:
            by_id[tid] = t
            continue

        current = by_id[tid]
        # Mantém o registro mais completo, sem perder campos já preenchidos.
        if source_rank.get(t.get("source"), 0) >= source_rank.get(current.get("source"), 0):
            merged = dict(current)
            for k, v in t.items():
                if v is not None and v != "":
                    merged[k] = v
            by_id[tid] = merged
        else:
            for k, v in t.items():
                if current.get(k) in [None, ""] and v not in [None, ""]:
                    current[k] = v

    return list(by_id.values())


def _stats_for(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    closed = [r for r in rows if r.get("closed") or r.get("status") == "CLOSED"]
    pnl_rows = [r for r in closed if r.get("pnl_pct") is not None]
    r_rows = [r for r in closed if r.get("r") is not None]
    wins = [r for r in pnl_rows if (r.get("pnl_pct") or 0) > 0]
    losses = [r for r in pnl_rows if (r.get("pnl_pct") or 0) < 0]
    breakeven = [r for r in pnl_rows if (r.get("pnl_pct") or 0) == 0]

    pnl_total = sum(float(r.get("pnl_pct") or 0) for r in pnl_rows)
    pnl_avg = pnl_total / len(pnl_rows) if pnl_rows else 0.0
    r_total = sum(float(r.get("r") or 0) for r in r_rows)
    r_avg = r_total / len(r_rows) if r_rows else 0.0

    gross_win = sum(float(r.get("pnl_pct") or 0) for r in wins)
    gross_loss = abs(sum(float(r.get("pnl_pct") or 0) for r in losses))
    profit_factor = 999.0 if gross_loss == 0 and gross_win > 0 else (gross_win / gross_loss if gross_loss > 0 else 0.0)

    return {
        "trades": len(closed),
        "mapped_rows": len(rows),
        "wins": len(wins),
        "losses": len(losses),
        "breakeven": len(breakeven),
        "win_rate_pct": round((len(wins) / len(pnl_rows)) * 100.0, 2) if pnl_rows else 0.0,
        "pnl_total_pct": round(pnl_total, 6),
        "pnl_avg_pct": round(pnl_avg, 6),
        "r_total": round(r_total, 6),
        "r_avg": round(r_avg, 6),
        "profit_factor_pct": round(profit_factor, 6),
        "with_pnl_pct": len(pnl_rows),
        "with_r": len(r_rows),
    }


def _group_stats(rows: List[Dict[str, Any]], key: str) -> Dict[str, Dict[str, Any]]:
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        groups[_safe_str(r.get(key), "UNKNOWN") or "UNKNOWN"].append(r)
    return {k: _stats_for(v) for k, v in sorted(groups.items(), key=lambda kv: kv[0])}


def build_real_pnl_r_map(limit: Optional[int] = None, commit: bool = True) -> Dict[str, Any]:
    raw_sources: List[Tuple[str, List[Dict[str, Any]]]] = [
        ("trade_registry", _read_jsonl(TRADE_REGISTRY_FILE, limit=limit)),
        ("history_events", _read_jsonl(HISTORY_EVENTS_FILE, limit=limit)),
        ("history_export", _load_history_export_rows()),
        ("decision_log", _read_jsonl(DECISION_LOG_FILE, limit=limit)),
    ]

    normalized: List[Dict[str, Any]] = []
    source_counts: Dict[str, int] = {}
    for source, rows in raw_sources:
        source_counts[source] = len(rows)
        for row in rows:
            item = _normalize_trade(row, source)
            if item:
                normalized.append(item)

    merged = _merge_trades(normalized)
    closed = [r for r in merged if r.get("closed") or r.get("status") == "CLOSED"]

    payload: Dict[str, Any] = {
        "ok": True,
        "version": VERSION,
        "generated_at": _now_br(),
        "mode": "OBSERVATION_ONLY",
        "notes": [
            "Real PnL/R Mapper V2.4 apenas observa e calcula métricas.",
            "Não executa trades, não altera lotes e não altera policies ativas.",
            "PnL% é calculado quando há entry/exit; R é calculado quando há entry/stop/exit.",
        ],
        "files": {
            "trade_registry": TRADE_REGISTRY_FILE,
            "history_events": HISTORY_EVENTS_FILE,
            "history_export": HISTORY_EXPORT_FILE,
            "decision_log": DECISION_LOG_FILE,
            "output_map": OUTPUT_MAP_FILE,
            "output_events": OUTPUT_EVENTS_FILE,
        },
        "source_counts": source_counts,
        "mapped_count": len(merged),
        "closed_count": len(closed),
        "summary": _stats_for(merged),
        "by_bot": _group_stats(closed, "bot"),
        "by_setup": _group_stats(closed, "setup"),
        "by_symbol": _group_stats(closed, "symbol"),
        "by_side": _group_stats(closed, "side"),
        "recent_closed": closed[-25:],
    }

    if commit:
        _write_json(OUTPUT_MAP_FILE, payload)
        _append_jsonl(OUTPUT_EVENTS_FILE, {
            "event": "REAL_PNL_R_MAP_REBUILT",
            "version": VERSION,
            "generated_at": payload["generated_at"],
            "mapped_count": payload["mapped_count"],
            "closed_count": payload["closed_count"],
            "summary": payload["summary"],
        })
        payload["committed"] = True
    else:
        payload["committed"] = False

    return payload


def build_real_pnl_r_text(payload: Optional[Dict[str, Any]] = None) -> str:
    if payload is None:
        payload = build_real_pnl_r_map(commit=False)

    summary = payload.get("summary", {})
    lines = []
    lines.append("💰 REAL PNL/R MAPPER — CENTRAL QUANT V2.4")
    lines.append(f"Data/hora: {payload.get('generated_at')}")
    lines.append(f"Status: {'✅' if payload.get('ok') else '❌'}")
    lines.append(f"Modo: {payload.get('mode', 'OBSERVATION_ONLY')}")
    lines.append("")
    lines.append("Resumo geral:")
    lines.append(f"- Trades fechados: {summary.get('trades', 0)}")
    lines.append(f"- Wins: {summary.get('wins', 0)} | Losses: {summary.get('losses', 0)} | BE: {summary.get('breakeven', 0)}")
    lines.append(f"- Win rate: {summary.get('win_rate_pct', 0)}%")
    lines.append(f"- PnL total: {summary.get('pnl_total_pct', 0)}%")
    lines.append(f"- PnL médio: {summary.get('pnl_avg_pct', 0)}%")
    lines.append(f"- R total: {summary.get('r_total', 0)}R")
    lines.append(f"- R médio: {summary.get('r_avg', 0)}R")
    lines.append(f"- Profit factor: {summary.get('profit_factor_pct', 0)}")
    lines.append("")
    lines.append("Por bot:")
    by_bot = payload.get("by_bot") or {}
    if not by_bot:
        lines.append("- Sem trades fechados mapeados por bot.")
    else:
        for bot, st in by_bot.items():
            lines.append(
                f"- {bot}: trades={st.get('trades', 0)} | win={st.get('win_rate_pct', 0)}% | "
                f"PnL={st.get('pnl_total_pct', 0)}% | R={st.get('r_total', 0)}R"
            )
    lines.append("")
    lines.append("Observação:")
    lines.append("- V2.4 ainda não muda lote, risco ou execução. Ela cria a ponte estatística entre resultado real e aprendizagem da Central.")
    return "\n".join(lines)


if __name__ == "__main__":
    result = build_real_pnl_r_map(commit=True)
    print(build_real_pnl_r_text(result))
