# -*- coding: utf-8 -*-
"""
REAL PNL/R MAPPER — CENTRAL QUANT V2.5
Versão: 2026-07-07-REAL-PNL-R-MAPPER-V2.5

Objetivo:
- Mapear PnL real e R real a partir de trades encerrados.
- Enriquecer trades fechados incompletos usando History, Trade Registry,
  History Export e Decision Log.
- Separar trades sem dados suficientes em diagnóstico, em vez de zerar
  silenciosamente PnL/R.
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

import copy
import hashlib
import json
import math
import os
from collections import OrderedDict, defaultdict
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

from history_memory_guard import AUTOMATIC_MAX_BYTES, AUTOMATIC_MAX_RECORDS, iter_jsonl_tail
from trade_registry import (
    STRONG_IDENTITY_ALIASES,
    closed_trade_identity_state,
    merge_closed_trade_records,
)

VERSION = "2026-07-07-REAL-PNL-R-MAPPER-V2.5"
MODULE = "real_pnl_r_mapper"
MODE = "OBSERVATION_ONLY"
_JSONL_READ_METADATA = OrderedDict()

def _resolve_data_dir():
    configured = os.environ.get("CENTRAL_DATA_DIR") or os.environ.get("DATA_DIR")
    if configured:
        return configured
    try:
        if os.path.isdir("/data"):
            return "/data"
    except Exception:
        pass
    return "/opt/render/project/src/data"

DATA_DIR = _resolve_data_dir()
TRADE_REGISTRY_FILE = os.path.join(DATA_DIR, "trade_registry.jsonl")
HISTORY_EVENTS_FILE = os.path.join(DATA_DIR, "history_events.jsonl")
HISTORY_EXPORT_FILE = os.path.join(DATA_DIR, "history_export.json")
DECISION_LOG_FILE = os.path.join(DATA_DIR, "decision_log.jsonl")

# Fontes potencialmente reais/auditáveis. Nem todas precisam existir.
# O mapper V2.5 filtra os registros e só conta como Real PnL/R quando
# houver marcador explícito de LIVE/REAL/BROKER/BINGX e não for dry_run/VERIFY/PAPER.
EXECUTION_ENGINE_LOG_FILE = os.path.join(DATA_DIR, "execution_engine_log.jsonl")
EXECUTION_LOG_FILE = os.path.join(DATA_DIR, "execution_log.jsonl")
REAL_CLOSE_AUTO_EVALUATOR_EVENTS_FILE = os.path.join(DATA_DIR, "real_close_auto_evaluator_v1_events.jsonl")
AUTO_REAL_EXECUTION_BRIDGE_EVENTS_FILE = os.path.join(DATA_DIR, "auto_real_execution_bridge_v1_events.jsonl")
REAL_POSITION_WATCHDOG_EVENTS_FILE = os.path.join(DATA_DIR, "real_position_watchdog_v1_events.jsonl")

OUTPUT_MAP_FILE = os.path.join(DATA_DIR, "real_pnl_r_map.json")
OUTPUT_EVENTS_FILE = os.path.join(DATA_DIR, "real_pnl_r_events.jsonl")

STRICT_REAL_SOURCES = os.environ.get("REAL_PNL_R_STRICT_REAL_SOURCES", "true").strip().lower() in {
    "1", "true", "yes", "sim", "on"
}
ALLOW_LEGACY_HISTORY_SOURCES = os.environ.get("REAL_PNL_R_ALLOW_LEGACY_HISTORY_SOURCES", "false").strip().lower() in {
    "1", "true", "yes", "sim", "on"
}

LEGACY_STATISTICAL_SOURCES = {"history_events", "history_export", "decision_log"}

EMPTY_VALUES = {None, "", "null", "None", "NONE", "N/A", "nan", "NaN"}


# ==========================================================
# BÁSICO / IO
# ==========================================================

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


def _is_empty(value: Any) -> bool:
    """Verificação type-safe de vazio.

    A V2.6 podia receber listas/dicts vindos do Registry/BingX e tentava
    consultá-los diretamente em EMPTY_VALUES (set), causando:
    TypeError: cannot use 'list' as a set element.
    """
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() in EMPTY_VALUES
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) == 0
    try:
        return value in EMPTY_VALUES
    except TypeError:
        return False


def _read_jsonl(path: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    try:
        result = iter_jsonl_tail(
            path,
            max_records=limit if limit is not None else AUTOMATIC_MAX_RECORDS,
            max_bytes=AUTOMATIC_MAX_BYTES,
            operation=f"real_pnl_r_mapper:{os.path.basename(path)}",
        )
        _JSONL_READ_METADATA[os.path.basename(path)] = {
            key: result[key] for key in (
                "partial", "coverage_complete", "records_examined", "bytes_read",
                "max_records", "max_bytes", "source_size_bytes",
            )
        }
        while len(_JSONL_READ_METADATA) > 32:
            _JSONL_READ_METADATA.popitem(last=False)
        return result["records"]
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


def _flatten_payload(row: Dict[str, Any]) -> Dict[str, Any]:
    """Une row + payload + trade + position + result sem sobrescrever campo bom."""
    merged = dict(row or {})
    for nested_key in ["payload", "trade", "position", "data", "result", "order", "decision", "context"]:
        nested = row.get(nested_key) if isinstance(row, dict) else None
        if isinstance(nested, dict):
            for k, v in nested.items():
                if _is_empty(merged.get(k)) and not _is_empty(v):
                    merged[k] = v
    return merged


def _pick(d: Dict[str, Any], keys: Iterable[str], default: Any = None) -> Any:
    for k in keys:
        if k in d and not _is_empty(d.get(k)):
            return d.get(k)
    return default


_CANONICAL_MERGE_PASSTHROUGH_FIELDS = (
    "outcome",
    "outcome_status",
    "outcome_source",
    "outcome_id",
    "outcome_hash",
    "data_quality",
    "outcome_data_quality",
    "exit_price",
    "exit_avg_price",
    "average_exit_price",
    "closed_quantity",
    "closed_qty",
    "close_qty",
    "remaining_qty",
    "close_timestamp",
    "close_reason",
    "exit_reason",
    "pnl",
    "pnl_r",
    "result",
    "result_pct",
    "result_r",
    "r_multiple",
    "gross_pnl",
    "gross_pnl_usdt",
    "net_pnl",
    "net_pnl_usdt",
    "realized_pnl",
    "realized_pnl_usdt",
    "profit_usdt",
    "profit_loss",
    "fee",
    "fees",
    "fees_usdt",
    "opening_fee",
    "closing_fee",
    "funding",
    "funding_fee",
    "broker_close_order_id",
    "close_order_id",
    "exit_order_id",
    "tp50_hit",
    "financial_reconciliation_pending",
    "learning_eligible",
)


def _project_closed_identity_fields(
    item: Dict[str, Any], merged: Dict[str, Any]
) -> Dict[str, Any]:
    """Keep evidence required by the shared canonical CLOSED identity merge."""
    projected = dict(item or {})
    merged = merged if isinstance(merged, dict) else {}
    source_metadata = (
        merged.get("metadata")
        if isinstance(merged.get("metadata"), dict)
        else {}
    )
    projected_metadata: Dict[str, Any] = {}

    identity_state = closed_trade_identity_state(merged)
    identity_states: List[Dict[str, Any]] = []
    identity_states.extend(
        state
        for state in (
            identity_state.get("strong_identity_states") or {}
        ).values()
        if isinstance(state, dict)
    )
    identity_states.extend(
        state
        for state in identity_state.get("specific_identity_states") or []
        if isinstance(state, dict)
    )
    identity_states.extend(
        state
        for state in (
            identity_state.get("legacy_identity_states") or {}
        ).values()
        if isinstance(state, dict)
    )

    for state in identity_states:
        for alias_path in state.get("aliases_present") or []:
            source_name, separator, alias = str(alias_path).partition(".")
            if not separator or not alias:
                continue
            source = merged if source_name == "trade" else source_metadata
            value = source.get(alias)
            if _is_empty(value):
                continue
            if source_name == "metadata":
                projected_metadata[alias] = copy.deepcopy(value)
            elif alias not in projected or _is_empty(projected.get(alias)):
                # Canonical mapper fields stay normalized; alternate aliases
                # remain available for exact identity/conflict checks.
                projected[alias] = copy.deepcopy(value)

    for field in _CANONICAL_MERGE_PASSTHROUGH_FIELDS:
        value = merged.get(field)
        if not _is_empty(value) and (
            field not in projected or _is_empty(projected.get(field))
        ):
            projected[field] = copy.deepcopy(value)
        metadata_value = source_metadata.get(field)
        if not _is_empty(metadata_value):
            projected_metadata[field] = copy.deepcopy(metadata_value)

    # Some operational event sources call execution_mode simply ``mode``.
    if _is_empty(projected.get("execution_mode")):
        execution_mode = _pick(merged, ["execution_mode", "mode"], None)
        if not _is_empty(execution_mode):
            projected["execution_mode"] = copy.deepcopy(execution_mode)
    if _is_empty(projected.get("registry_mode")):
        registry_mode = _pick(merged, ["registry_mode", "trade_mode"], None)
        if not _is_empty(registry_mode):
            projected["registry_mode"] = copy.deepcopy(registry_mode)

    # Preserve every strong alias, including conflicting metadata aliases, so
    # trade_registry can quarantine corruption instead of silently fusing it.
    for aliases in STRONG_IDENTITY_ALIASES.values():
        for alias in aliases:
            value = merged.get(alias)
            if not _is_empty(value):
                projected[alias] = copy.deepcopy(value)
            metadata_value = source_metadata.get(alias)
            if not _is_empty(metadata_value):
                projected_metadata[alias] = copy.deepcopy(metadata_value)

    if projected_metadata:
        projected["metadata"] = projected_metadata
    return projected


# ==========================================================
# NORMALIZAÇÃO
# ==========================================================

def _normalize_side(side: Any) -> str:
    s = _safe_str(side).upper()
    if s in {"BUY", "LONG", "COMPRA"}:
        return "LONG"
    if s in {"SELL", "SHORT", "VENDA"}:
        return "SHORT"
    return s or "UNKNOWN"


def _normalize_symbol(symbol: Any) -> str:
    s = _safe_str(symbol).upper()
    s = s.replace("/", "").replace(":USDT", "")
    s = s.replace("-", "").replace("_", "")
    return s or "UNKNOWN"


def _normalize_bot(bot: Any) -> str:
    b = _safe_str(bot, "UNKNOWN").upper()
    aliases = {
        "SMARTPREDATOR": "PREDATOR",
        "SMART_PREDATOR": "PREDATOR",
        "TREND_PRO": "TRENDPRO",
        "TREND PRO": "TRENDPRO",
        "FALCON15": "FALCON",
    }
    return aliases.get(b, b or "UNKNOWN")


def _normalize_setup(setup: Any) -> str:
    s = _safe_str(setup, "UNKNOWN").upper()
    return s or "UNKNOWN"


def _extract_price(row: Dict[str, Any], names: List[str]) -> Optional[float]:
    return _safe_float(_pick(row, names))


def _infer_closed(row: Dict[str, Any]) -> bool:
    status = _safe_str(_pick(row, ["status", "state"])).upper()
    event = _safe_str(_pick(row, ["event", "event_raw", "type", "kind"])).upper()
    if status in {"CLOSED", "CLOSE", "DONE", "FINISHED", "EXITED", "ENCERRADO", "FECHADO"}:
        return True
    if event in {"TRADE_CLOSED", "CLOSE", "CLOSED", "POSITION_CLOSED", "EXIT", "TP", "STOP", "SL", "TAKE_PROFIT"}:
        return True
    if _extract_price(row, ["exit", "exit_price", "close", "close_price", "avg_exit_price", "closed_price"]):
        return True
    if _safe_float(_pick(row, ["pnl_pct", "pnl_percent", "profit_pct", "real_pnl_pct", "pnl_usdt", "realized_pnl", "realizedPnl"])) is not None:
        return True
    return False


def _primary_identity(row: Dict[str, Any]) -> Dict[str, Any]:
    merged = _flatten_payload(row)
    return {
        "bot": _normalize_bot(_pick(merged, ["bot", "robot", "strategy", "bot_name", "source_bot"])),
        "setup": _normalize_setup(_pick(merged, ["setup", "setup_name", "strategy_setup", "signal_type", "setup_label"])),
        "symbol": _normalize_symbol(_pick(merged, ["symbol", "symbol_clean", "ativo", "pair", "market", "ticker"])),
        "side": _normalize_side(_pick(merged, ["side", "direction", "position_side", "signal_side"])),
    }


def _candidate_trade_id(row: Dict[str, Any]) -> str:
    merged = _flatten_payload(row)
    explicit = _pick(merged, [
        "trade_id", "id", "decision_id", "position_id", "signal_id", "client_order_id",
        "order_id", "orderId", "uid", "uuid",
    ])
    if explicit:
        explicit_s = _safe_str(explicit)
        # Evita IDs ruins demais como "C" agruparem tudo indevidamente.
        if len(explicit_s) >= 6:
            return explicit_s

    ident = _primary_identity(merged)
    ts = _safe_str(_pick(merged, ["entry_time", "opened_at", "created_at", "timestamp", "epoch", "closed_at", "generated_at"]), "NO_TIME")
    entry = _safe_str(_pick(merged, ["entry", "entry_price", "avg_entry_price", "open_price"]), "NO_ENTRY")
    return f"{ident['bot']}:{ident['setup']}:{ident['symbol']}:{ident['side']}:{entry}:{ts}"


def _match_key(row: Dict[str, Any]) -> str:
    ident = _primary_identity(row)
    return f"{ident['bot']}|{ident['symbol']}|{ident['side']}"


def _loose_match_key(row: Dict[str, Any]) -> str:
    ident = _primary_identity(row)
    return f"{ident['symbol']}|{ident['side']}"


def _source_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(x) for x in value]
    if value:
        return [str(value)]
    return []


def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    try:
        s = str(value).strip().lower()
    except Exception:
        return default
    if s in {"1", "true", "yes", "sim", "on", "live", "sent", "ok"}:
        return True
    if s in {"0", "false", "no", "nao", "não", "off", "dry_run", "paper", "verify"}:
        return False
    return default


def _upper_values(row: Dict[str, Any], keys: Iterable[str]) -> List[str]:
    merged = _flatten_payload(row)
    values: List[str] = []
    for key in keys:
        value = merged.get(key)
        if isinstance(value, (list, tuple, set)):
            for item in value:
                if not _is_empty(item):
                    values.append(str(item).upper().strip())
        elif not _is_empty(value):
            values.append(str(value).upper().strip())
    return values


def _is_real_trade_candidate(item: Dict[str, Any], raw_row: Dict[str, Any], source: str) -> bool:
    """
    Decide se um registro pode entrar no Real PnL/R auditável.

    V2.5 é propositalmente conservador: histórico estatístico, decision_log,
    PAPER, VERIFY, SHADOW e dry_run não entram como resultado financeiro real.
    Para entrar, o registro precisa carregar marcador explícito de LIVE/REAL/BROKER/BINGX
    ou evidência de envio real ao broker.
    """
    merged = _flatten_payload(raw_row if isinstance(raw_row, dict) else {})
    source_name = str(source or "").lower().strip()

    # Fontes legadas são estatísticas por padrão. Podem ser liberadas por env
    # apenas se o registro também trouxer marcador real explícito.
    legacy_source = source_name in LEGACY_STATISTICAL_SOURCES

    mode_values = _upper_values(merged, [
        "mode", "execution_mode", "order_mode", "run_mode", "environment",
        "source_mode", "trade_mode", "payload_mode", "status_mode",
    ])
    source_values = _upper_values(merged, [
        "source", "source_type", "origin", "executor", "executor_route",
        "broker", "exchange", "venue", "execution_source", "registry_source",
    ])
    status_values = _upper_values(merged, [
        "status", "event", "event_raw", "type", "kind", "route", "decision",
    ])

    combined = " ".join(mode_values + source_values + status_values)

    dry_run = any(_safe_bool(merged.get(k), False) for k in [
        "dry_run", "broker_dry_run", "preview", "preview_only", "test_mode", "paper", "shadow"
    ])
    if dry_run:
        return False

    # Exclui marcadores não reais quando não há LIVE explícito.
    has_live_marker = any(x in combined for x in ["LIVE", "REAL", "BROKER", "BINGX", "EXCHANGE"])
    has_non_real_marker = any(x in combined for x in ["PAPER", "VERIFY", "SHADOW", "OBSERVATION_ONLY", "DRY_RUN", "PREVIEW"])
    if has_non_real_marker and not has_live_marker:
        return False

    sent_real = any(_safe_bool(merged.get(k), False) for k in [
        "sent", "live_sent", "order_sent", "broker_sent", "real_sent", "executed", "filled"
    ])
    broker_ids = [
        merged.get("live_order_id"), merged.get("bingx_order_id"), merged.get("broker_order_id"),
        merged.get("exchange_order_id"), merged.get("orderId"), merged.get("order_id"),
        merged.get("client_order_id"), merged.get("position_id"),
    ]
    has_broker_id = any(not _is_empty(x) and len(str(x)) >= 4 for x in broker_ids)

    explicit_real_source = any(x in combined for x in [
        "LIVE", "REAL", "BROKER", "BINGX", "EXCHANGE", "REAL_CLOSE", "LIVE_SENT"
    ])

    if legacy_source and not ALLOW_LEGACY_HISTORY_SOURCES:
        # Mesmo com PnL%, history_events/decision_log não são prova financeira real.
        return bool(explicit_real_source and (sent_real or has_broker_id))

    return bool(explicit_real_source or sent_real or has_broker_id or item.get("source") in {
        "execution_engine_log", "execution_log", "real_close_auto_evaluator",
        "auto_real_execution_bridge", "real_position_watchdog",
    })


def _filter_real_rows(normalized: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Mantém apenas fechamentos reais auditáveis e completos o suficiente para estatística."""
    out: List[Dict[str, Any]] = []
    for row in normalized:
        if not row.get("real_audit_candidate"):
            continue
        out.append(row)
    return out


# ==========================================================
# CÁLCULOS
# ==========================================================

def _compute_pnl_pct(side: str, entry: Optional[float], exit_price: Optional[float]) -> Optional[float]:
    if not entry or not exit_price or entry <= 0:
        return None
    if side == "SHORT":
        return ((entry - exit_price) / entry) * 100.0
    return ((exit_price - entry) / entry) * 100.0


def _compute_r(side: str, entry: Optional[float], stop: Optional[float], exit_price: Optional[float]) -> Optional[float]:
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


def _recompute_metrics(t: Dict[str, Any]) -> Dict[str, Any]:
    side = _normalize_side(t.get("side"))
    entry = _safe_float(t.get("entry"))
    stop = _safe_float(t.get("stop"))
    exit_price = _safe_float(t.get("exit"))

    pnl_pct = _safe_float(t.get("pnl_pct"))
    if pnl_pct is None:
        pnl_pct = _compute_pnl_pct(side, entry, exit_price)

    r_value = _safe_float(t.get("r"))
    if r_value is None:
        r_value = _compute_r(side, entry, stop, exit_price)

    t["side"] = side or "UNKNOWN"
    t["entry"] = entry
    t["stop"] = stop
    t["exit"] = exit_price
    t["pnl_pct"] = round(pnl_pct, 6) if pnl_pct is not None else None
    t["r"] = round(r_value, 6) if r_value is not None else None
    return t


# ==========================================================
# NORMALIZAÇÃO / ENRIQUECIMENTO
# ==========================================================

def _normalize_trade(row: Dict[str, Any], source: str) -> Optional[Dict[str, Any]]:
    if not isinstance(row, dict):
        return None

    merged = _flatten_payload(row)
    ident = _primary_identity(merged)

    entry = _extract_price(merged, [
        "entry", "entry_price", "avg_entry_price", "open_price", "entrada", "price_entry", "fill_entry",
    ])
    stop = _extract_price(merged, [
        "sl", "stop", "stop_loss", "initial_sl", "initial_stop", "stop_price", "stop_atual",
    ])
    exit_price = _extract_price(merged, [
        "exit", "exit_price", "close", "close_price", "avg_exit_price", "closed_price", "saida", "price_exit",
    ])

    pnl_pct = _safe_float(_pick(merged, ["pnl_pct", "pnl_percent", "profit_pct", "real_pnl_pct", "result_pct"]))
    r_value = _safe_float(_pick(merged, ["r", "r_result", "real_r", "r_multiple", "result_r"]))
    # Para fechamento REAL reconciliado, a verdade financeira é net_pnl.
    # realized_pnl permanece disponível separadamente, mas não substitui fees/funding.
    pnl_usdt = _safe_float(_pick(merged, ["net_pnl", "net_pnl_usdt", "pnl_usdt", "realized_pnl", "realizedPnl", "profit_usdt", "pnl"] ))
    qty = _safe_float(_pick(merged, ["qty", "quantity", "size", "amount", "contracts", "position_size"] ))

    closed = _infer_closed(merged)
    has_useful_data = closed or any(x is not None for x in [entry, stop, exit_price, pnl_pct, r_value, pnl_usdt, qty])
    if not has_useful_data:
        return None

    item: Dict[str, Any] = {
        "trade_id": _candidate_trade_id(merged),
        "match_key": _match_key(merged),
        "loose_match_key": _loose_match_key(merged),
        "sources": [source],
        "source": source,
        "bot": ident["bot"],
        "setup": ident["setup"],
        "symbol": ident["symbol"],
        "side": ident["side"],
        "entry": entry,
        "stop": stop,
        "exit": exit_price,
        "qty": qty,
        "pnl_pct": round(pnl_pct, 6) if pnl_pct is not None else None,
        "pnl_usdt": round(pnl_usdt, 6) if pnl_usdt is not None else None,
        "r": round(r_value, 6) if r_value is not None else None,
        "status": "CLOSED" if closed else "MAPPED",
        "closed": bool(closed),
        "raw_event": _safe_str(_pick(merged, ["event", "event_raw", "type", "status", "kind"]), ""),
        "timestamp": _pick(merged, ["timestamp", "epoch", "created_at", "entry_time", "opened_at", "closed_at", "generated_at"]),
    }
    item = _project_closed_identity_fields(item, merged)
    return _recompute_metrics(item)


def _mapper_stable_record_key(record: Dict[str, Any]) -> Tuple[str, str]:
    try:
        identity = closed_trade_identity_state(record)
        canonical_key = str(identity.get("canonical_key") or "")
    except Exception:
        canonical_key = ""
    return (
        canonical_key,
        json.dumps(
            record,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ),
    )


def _mapper_observation_id(record: Dict[str, Any]) -> str:
    """Return a deterministic, internal-only identifier for one observation."""
    payload = json.dumps(
        record,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _merge_trades_with_diagnostics(
    trades: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Merge execution observations through the Registry identity contract.

    ``trade_id`` and symbol/side match keys are never sufficient evidence.
    A non-CLOSED observation may enrich a CLOSED record only when both expose a
    shared typed canonical token.  Uncertain, financially conflicting, or
    alias-conflicting records remain separate and make persistence fail-closed
    through ``safe_to_commit``.
    """
    closed_marker = "__real_pnl_mapper_closed_observation_ids__"
    open_marker = "__real_pnl_mapper_open_observation_ids__"
    closed_records: List[Dict[str, Any]] = []
    non_closed_records: List[Dict[str, Any]] = []
    for trade in trades or []:
        if not isinstance(trade, dict):
            continue
        item = copy.deepcopy(trade)
        if item.get("closed") or str(item.get("status") or "").upper() == "CLOSED":
            item["closed"] = True
            item["status"] = "CLOSED"
            item[closed_marker] = [_mapper_observation_id(item)]
            closed_records.append(item)
        else:
            non_closed_records.append(item)

    closed_tokens = {
        str(token)
        for item in closed_records
        for token in (
            closed_trade_identity_state(item).get("merge_tokens") or []
        )
    }
    canonical_candidates: List[Dict[str, Any]] = []
    candidate_open_ids = set()
    for item in non_closed_records:
        projected = copy.deepcopy(item)
        projected["closed"] = True
        projected["status"] = "CLOSED"
        state = closed_trade_identity_state(projected)
        tokens = {str(token) for token in state.get("merge_tokens") or []}
        # No coarse fallback is allowed here.  The shared token can only be a
        # lifecycle, client+order, specific execution ID, or complete canonical
        # legacy fallback emitted by trade_registry.
        if not (tokens & closed_tokens):
            continue
        observation_id = _mapper_observation_id(item)
        projected[open_marker] = [observation_id]
        canonical_candidates.append(projected)
        candidate_open_ids.add(observation_id)

    canonical_result = merge_closed_trade_records(
        closed_records + canonical_candidates
    )
    diagnostics = copy.deepcopy(canonical_result.get("diagnostics") or {})

    merged_closed: List[Dict[str, Any]] = []
    consumed_open_ids = set()
    for record in canonical_result.get("records") or []:
        if not isinstance(record, dict):
            continue
        item = copy.deepcopy(record)
        closed_observation_ids = {
            str(value)
            for value in item.pop(closed_marker, []) or []
            if value
        }
        open_observation_ids = {
            str(value)
            for value in item.pop(open_marker, []) or []
            if value
        }
        # A projected OPEN-only row is never exposed as a fabricated CLOSED.
        # It is retained below in its original non-CLOSED form unless the
        # canonical Registry merge actually joined it to a CLOSED observation.
        if not closed_observation_ids:
            continue
        if open_observation_ids:
            consumed_open_ids.update(open_observation_ids)
        item["closed"] = True
        item["status"] = "CLOSED"
        if _is_empty(item.get("r")) and not _is_empty(item.get("pnl_r")):
            item["r"] = _safe_float(item.get("pnl_r"))
        merged_closed.append(_diagnose_trade(_recompute_metrics(item)))

    merged_closed.sort(key=_mapper_stable_record_key)
    normalized_open = [
        _diagnose_trade(_recompute_metrics(copy.deepcopy(item)))
        for item in non_closed_records
        if _mapper_observation_id(item) not in consumed_open_ids
    ]
    normalized_open.sort(key=_mapper_stable_record_key)
    diagnostics.update(
        {
            "mapper_identity_contract": "TRADE_REGISTRY_CLOSED_CANONICAL_IDENTITY",
            "closed_input_count": len(closed_records),
            "non_closed_input_count": len(non_closed_records),
            "open_enrichment_candidate_count": len(canonical_candidates),
            "open_enrichment_consumed_count": len(consumed_open_ids),
            "open_enrichment_preserved_count": len(
                candidate_open_ids - consumed_open_ids
            ),
            "trade_id_only_merge": False,
            "symbol_side_merge": False,
        }
    )
    return {
        "records": merged_closed + normalized_open,
        "diagnostics": diagnostics,
    }


def _merge_trades(trades: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Compatibility projection returning canonical merge records only."""
    return list(_merge_trades_with_diagnostics(trades).get("records") or [])


# ==========================================================
# DIAGNÓSTICO
# ==========================================================

def _diagnose_trade(t: Dict[str, Any]) -> Dict[str, Any]:
    issues: List[str] = []
    if t.get("closed"):
        if t.get("entry") is None:
            issues.append("MISSING_ENTRY_PRICE")
        if t.get("exit") is None:
            issues.append("MISSING_EXIT_PRICE")
        if t.get("stop") is None:
            issues.append("MISSING_STOP_PRICE")
        if t.get("pnl_pct") is None:
            issues.append("MISSING_PNL_PCT")
        if t.get("r") is None:
            issues.append("MISSING_R")
        if t.get("symbol") in {None, "", "UNKNOWN"}:
            issues.append("MISSING_SYMBOL")
        if t.get("side") in {None, "", "UNKNOWN"}:
            issues.append("MISSING_SIDE")
    t["quality"] = "COMPLETE" if not issues and t.get("closed") else ("INCOMPLETE" if issues else "MAPPED")
    t["issues"] = issues
    return t


def _diagnostics(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    closed = [r for r in rows if r.get("closed") or r.get("status") == "CLOSED"]
    incomplete = [r for r in closed if r.get("issues")]
    by_issue: Dict[str, int] = defaultdict(int)
    for r in incomplete:
        for issue in r.get("issues") or []:
            by_issue[issue] += 1
    return {
        "closed_complete": len([r for r in closed if not r.get("issues")]),
        "closed_incomplete": len(incomplete),
        "by_issue": dict(sorted(by_issue.items())),
        "incomplete_recent": incomplete[-25:],
    }


# ==========================================================
# LOADERS
# ==========================================================

def _load_history_export_rows() -> List[Dict[str, Any]]:
    data = _read_json(HISTORY_EXPORT_FILE)
    if data is None:
        return []
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for key in ["trades", "events", "closed_trades", "history", "rows", "items", "data"]:
            value = data.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
        return [data]
    return []


# ==========================================================
# ESTATÍSTICAS
# ==========================================================

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


# ==========================================================
# API PÚBLICA DO MÓDULO
# ==========================================================

def get_real_pnl_r_health() -> Dict[str, Any]:
    return {
        "ok": True,
        "available": True,
        "module": MODULE,
        "version": VERSION,
        "mode": MODE,
        "import_error": None,
        "files": {
            "trade_registry_exists": os.path.exists(TRADE_REGISTRY_FILE),
            "history_events_exists": os.path.exists(HISTORY_EVENTS_FILE),
            "history_export_exists": os.path.exists(HISTORY_EXPORT_FILE),
            "decision_log_exists": os.path.exists(DECISION_LOG_FILE),
            "execution_engine_log_exists": os.path.exists(EXECUTION_ENGINE_LOG_FILE),
            "execution_log_exists": os.path.exists(EXECUTION_LOG_FILE),
            "real_close_auto_evaluator_events_exists": os.path.exists(REAL_CLOSE_AUTO_EVALUATOR_EVENTS_FILE),
            "auto_real_execution_bridge_events_exists": os.path.exists(AUTO_REAL_EXECUTION_BRIDGE_EVENTS_FILE),
            "real_position_watchdog_events_exists": os.path.exists(REAL_POSITION_WATCHDOG_EVENTS_FILE),
            "output_map_exists": os.path.exists(OUTPUT_MAP_FILE),
            "output_events_exists": os.path.exists(OUTPUT_EVENTS_FILE),
        },
        "notes": [
            "V2.5 mapeia PnL/R real apenas quando há marcador auditável LIVE/REAL/BROKER/BINGX.",
            "Por padrão, history_events, history_export e decision_log não entram como PnL real financeiro.",
            "Não executa ordens, não altera lotes e não muda risco real.",
        ],
    }


def build_real_pnl_r_map(limit: Optional[int] = None, commit: bool = True) -> Dict[str, Any]:
    _JSONL_READ_METADATA.clear()
    raw_sources: List[Tuple[str, List[Dict[str, Any]]]] = [
        ("trade_registry", _read_jsonl(TRADE_REGISTRY_FILE, limit=limit)),
        ("execution_engine_log", _read_jsonl(EXECUTION_ENGINE_LOG_FILE, limit=limit)),
        ("execution_log", _read_jsonl(EXECUTION_LOG_FILE, limit=limit)),
        ("real_close_auto_evaluator", _read_jsonl(REAL_CLOSE_AUTO_EVALUATOR_EVENTS_FILE, limit=limit)),
        ("auto_real_execution_bridge", _read_jsonl(AUTO_REAL_EXECUTION_BRIDGE_EVENTS_FILE, limit=limit)),
        ("real_position_watchdog", _read_jsonl(REAL_POSITION_WATCHDOG_EVENTS_FILE, limit=limit)),
        # Fontes legadas continuam lidas para diagnóstico, mas V2.5 não as conta como Real PnL/R
        # sem marcador explícito de broker/live.
        ("history_events", _read_jsonl(HISTORY_EVENTS_FILE, limit=limit)),
        ("history_export", _load_history_export_rows()),
        ("decision_log", _read_jsonl(DECISION_LOG_FILE, limit=limit)),
    ]

    normalized: List[Dict[str, Any]] = []
    source_counts: Dict[str, int] = {}
    skipped_non_real_count = 0
    skipped_non_real_by_source: Dict[str, int] = defaultdict(int)
    for source, rows in raw_sources:
        source_counts[source] = len(rows)
        for row in rows:
            item = _normalize_trade(row, source)
            if not item:
                continue
            item["real_audit_candidate"] = _is_real_trade_candidate(item, row, source)
            if STRICT_REAL_SOURCES and not item.get("real_audit_candidate"):
                skipped_non_real_count += 1
                skipped_non_real_by_source[source] += 1
                continue
            normalized.append(item)

    merge_result = _merge_trades_with_diagnostics(normalized)
    merged = list(merge_result.get("records") or [])
    closed_identity_merge = dict(merge_result.get("diagnostics") or {})
    closed = [r for r in merged if r.get("closed") or r.get("status") == "CLOSED"]
    diagnostics = _diagnostics(merged)

    payload: Dict[str, Any] = {
        "ok": True,
        "version": VERSION,
        "module": MODULE,
        "generated_at": _now_br(),
        "mode": MODE,
        "notes": [
            "Real PnL/R Mapper V2.5 apenas observa e calcula métricas.",
            "Só conta como resultado real financeiro registros auditáveis LIVE/REAL/BROKER/BINGX.",
            "history_events/history_export/decision_log são fontes estatísticas e ficam fora por padrão.",
            "PnL% é calculado quando há entry/exit; R é calculado quando há entry/stop/exit.",
            "Trades incompletos aparecem em diagnostics.by_issue, não como perda/zero silencioso.",
        ],
        "files": {
            "trade_registry": TRADE_REGISTRY_FILE,
            "execution_engine_log": EXECUTION_ENGINE_LOG_FILE,
            "execution_log": EXECUTION_LOG_FILE,
            "real_close_auto_evaluator_events": REAL_CLOSE_AUTO_EVALUATOR_EVENTS_FILE,
            "auto_real_execution_bridge_events": AUTO_REAL_EXECUTION_BRIDGE_EVENTS_FILE,
            "real_position_watchdog_events": REAL_POSITION_WATCHDOG_EVENTS_FILE,
            "history_events": HISTORY_EVENTS_FILE,
            "history_export": HISTORY_EXPORT_FILE,
            "decision_log": DECISION_LOG_FILE,
            "output_map": OUTPUT_MAP_FILE,
            "output_events": OUTPUT_EVENTS_FILE,
        },
        "source_counts": source_counts,
        "source_coverage": dict(_JSONL_READ_METADATA),
        "partial": any(item.get("partial") for item in _JSONL_READ_METADATA.values()),
        "coverage_complete": all(item.get("coverage_complete") for item in _JSONL_READ_METADATA.values()),
        "records_examined": sum(item.get("records_examined", 0) for item in _JSONL_READ_METADATA.values()),
        "bytes_read": sum(item.get("bytes_read", 0) for item in _JSONL_READ_METADATA.values()),
        "max_records": limit if limit is not None else AUTOMATIC_MAX_RECORDS,
        "max_bytes": AUTOMATIC_MAX_BYTES,
        "source_size_bytes": sum(item.get("source_size_bytes", 0) for item in _JSONL_READ_METADATA.values()),
        "strict_real_sources": STRICT_REAL_SOURCES,
        "allow_legacy_history_sources": ALLOW_LEGACY_HISTORY_SOURCES,
        "skipped_non_real_count": skipped_non_real_count,
        "skipped_non_real_by_source": dict(sorted(skipped_non_real_by_source.items())),
        "normalized_count": len(normalized),
        "mapped_count": len(merged),
        "closed_count": len(closed),
        "closed_identity_merge": closed_identity_merge,
        "summary": _stats_for(merged),
        "diagnostics": diagnostics,
        "by_bot": _group_stats(closed, "bot"),
        "by_setup": _group_stats(closed, "setup"),
        "by_symbol": _group_stats(closed, "symbol"),
        "by_side": _group_stats(closed, "side"),
        "recent_closed": closed[-25:],
    }

    if commit and not closed_identity_merge.get("safe_to_commit", True):
        payload["ok"] = False
        payload["status"] = "CLOSED_IDENTITY_REVIEW_REQUIRED"
        payload["commit_blocked"] = True
        payload["commit_block_reason"] = "CLOSED_IDENTITY_MERGE_UNSAFE"
        payload["committed"] = False
    elif commit:
        _write_json(OUTPUT_MAP_FILE, payload)
        _append_jsonl(OUTPUT_EVENTS_FILE, {
            "event": "REAL_PNL_R_MAP_REBUILT",
            "version": VERSION,
            "generated_at": payload["generated_at"],
            "mapped_count": payload["mapped_count"],
            "closed_count": payload["closed_count"],
            "summary": payload["summary"],
            "diagnostics": payload["diagnostics"],
        })
        payload["committed"] = True
    else:
        payload["committed"] = False

    return payload


def build_real_pnl_r_text(payload: Optional[Dict[str, Any]] = None) -> str:
    if payload is None:
        payload = build_real_pnl_r_map(commit=False)

    summary = payload.get("summary", {}) or {}
    diagnostics = payload.get("diagnostics", {}) or {}
    by_issue = diagnostics.get("by_issue", {}) or {}

    lines = []
    lines.append("💰 REAL PNL/R MAPPER — CENTRAL QUANT V2.5")
    lines.append(f"Data/hora: {payload.get('generated_at')}")
    lines.append(f"Status: {'✅' if payload.get('ok') else '❌'}")
    lines.append(f"Modo: {payload.get('mode', MODE)}")
    lines.append("")
    lines.append("Resumo geral:")
    if int(summary.get('trades', 0) or 0) <= 0:
        lines.append("- Nenhum trade real fechado auditável encontrado.")
        lines.append("- Histórico estatístico/PAPER/VERIFY não é contado como Real PnL/R financeiro na V2.5.")
    lines.append(f"- Trades fechados: {summary.get('trades', 0)}")
    lines.append(f"- Wins: {summary.get('wins', 0)} | Losses: {summary.get('losses', 0)} | BE: {summary.get('breakeven', 0)}")
    lines.append(f"- Win rate: {summary.get('win_rate_pct', 0)}%")
    lines.append(f"- PnL total: {summary.get('pnl_total_pct', 0)}%")
    lines.append(f"- PnL médio: {summary.get('pnl_avg_pct', 0)}%")
    lines.append(f"- R total: {summary.get('r_total', 0)}R")
    lines.append(f"- R médio: {summary.get('r_avg', 0)}R")
    lines.append(f"- Profit factor: {summary.get('profit_factor_pct', 0)}")
    lines.append(f"- Com PnL%: {summary.get('with_pnl_pct', 0)} | Com R: {summary.get('with_r', 0)}")
    lines.append("")
    lines.append("Diagnóstico:")
    lines.append(f"- Fechados completos: {diagnostics.get('closed_complete', 0)}")
    lines.append(f"- Fechados incompletos: {diagnostics.get('closed_incomplete', 0)}")
    if by_issue:
        for issue, count in by_issue.items():
            lines.append(f"- {issue}: {count}")
    else:
        lines.append("- Sem pendências de dados nos fechamentos mapeados.")
    lines.append("")
    lines.append("Por bot:")
    by_bot = payload.get("by_bot") or {}
    if not by_bot:
        lines.append("- Sem trades fechados mapeados por bot.")
    else:
        for bot, st in by_bot.items():
            lines.append(
                f"- {bot}: trades={st.get('trades', 0)} | win={st.get('win_rate_pct', 0)}% | "
                f"PnL={st.get('pnl_total_pct', 0)}% | R={st.get('r_total', 0)}R | "
                f"with_pnl={st.get('with_pnl_pct', 0)} | with_r={st.get('with_r', 0)}"
            )
    lines.append("")
    lines.append("Observação:")
    lines.append("- V2.5 não mistura history_events/decision_log com resultado real financeiro.")
    lines.append("- Continua observacional: não muda lote, risco, execução ou policies ativas.")
    return "\n".join(lines)


if __name__ == "__main__":
    result = build_real_pnl_r_map(commit=True)
    print(build_real_pnl_r_text(result))


# ==============================================================================
# PATCH 2026-07-11 — REAL PNL/R MAPPER V2.6 — REGISTRY JSON + BINGX RECON
# ==============================================================================
# Corrige o principal gap visto no piloto real: o Trade Registry persistente é JSON
# (/data/trade_registry.json), enquanto a V2.5 lia apenas trade_registry.jsonl.
# Continua observacional: não envia ordens, não altera risco e não rearma LIVE.

VERSION = "2026-07-23-REAL-PNL-R-MAPPER-V2.6.4-CLOSED-CANONICAL-IDENTITY"
TRADE_REGISTRY_JSON_FILE = os.path.join(DATA_DIR, "trade_registry.json")
BROKER_EXECUTIONS_LOG_FILE = os.path.join(DATA_DIR, "broker_executions_log.jsonl")
BROKER_EXECUTION_AUDIT_LOG_FILE = os.path.join(DATA_DIR, "broker_execution_audit_log.jsonl")


def _read_trade_registry_json_rows(limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Lê formatos conhecidos do Registry persistente sem assumir um único schema.

    Compatível com containers list/dict em closed_trades, open_trades, trades,
    positions, items e registry. Preserva o trade_id quando o container é dict.
    """
    data = _read_json(TRADE_REGISTRY_JSON_FILE)
    if data is None:
        return []

    rows: List[Dict[str, Any]] = []
    seen: set = set()

    def add_row(item: Any, default_status: Optional[str] = None, container_key: Optional[str] = None) -> None:
        if not isinstance(item, dict):
            return
        row = dict(item)
        if container_key and _is_empty(row.get("trade_id")):
            row["trade_id"] = str(container_key)
        if default_status:
            row.setdefault("status", default_status)
            row.setdefault("event", "TRADE_CLOSED" if default_status == "CLOSED" else "TRADE_OPEN")
        row.setdefault("registry_file", TRADE_REGISTRY_JSON_FILE)
        # Reader-level dedup is exact-document-only.  Semantic identity belongs
        # to merge_closed_trade_records; a coarse tuple omitting lifecycle or
        # order aliases can erase an independent execution before that merge.
        fingerprint = json.dumps(
            row,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        if fingerprint in seen:
            return
        seen.add(fingerprint)
        rows.append(row)

    def consume(container: Any, default_status: Optional[str] = None) -> None:
        if isinstance(container, list):
            for item in container:
                add_row(item, default_status=default_status)
        elif isinstance(container, dict):
            # Um dict pode ser um trade único ou um mapa trade_id -> trade.
            trade_markers = {"symbol", "side", "status", "state", "entry", "entry_price", "order_id", "trade_id"}
            if trade_markers.intersection(container.keys()):
                add_row(container, default_status=default_status)
            else:
                for key, item in container.items():
                    add_row(item, default_status=default_status, container_key=str(key))

    if isinstance(data, list):
        consume(data)
    elif isinstance(data, dict):
        known = [
            ("closed_trades", "CLOSED"),
            ("closed", "CLOSED"),
            ("open_trades", "OPEN"),
            ("open", "OPEN"),
            ("trades", None),
            ("positions", None),
            ("items", None),
            ("registry", None),
            ("data", None),
        ]
        consumed_any = False
        for key, default_status in known:
            if key in data:
                consume(data.get(key), default_status=default_status)
                consumed_any = True
        if not consumed_any:
            consume(data)

    if limit and len(rows) > int(limit):
        return rows[-int(limit):]
    return rows


def _authoritative_reconciled_real_close(row: Dict[str, Any]) -> bool:
    """Reconhece um CLOSED REAL já reconciliado, mesmo que o metadata preserve
    decisões históricas PRECHECK/NOT_ELIGIBLE anteriores ao envio manual/controlado.

    A exceção é deliberadamente estreita: exige fechamento, modo REAL/LIVE, ID forte
    de broker, preço de saída e evidência financeira reconciliada.
    """
    if not isinstance(row, dict):
        return False

    merged = _flatten_payload(row)
    meta = merged.get("metadata") if isinstance(merged.get("metadata"), dict) else {}

    status = _safe_str(_pick(merged, ["status", "state"], "")).upper()
    event = _safe_str(_pick(merged, ["event", "event_raw", "type", "kind"], "")).upper()
    closed = status in {"CLOSED", "CLOSE", "DONE", "FINISHED", "EXITED", "ENCERRADO", "FECHADO"} or event in {
        "TRADE_CLOSED", "CLOSED", "POSITION_CLOSED", "REAL_CLOSE"
    }
    if not closed:
        return False

    registry_mode = _safe_str(_pick(merged, ["registry_mode", "trade_mode"], "")).upper()
    execution_mode = _safe_str(_pick(merged, ["execution_mode", "mode"], "")).upper()
    reconciled = _safe_bool(merged.get("real_close_reconciled"), False) or _safe_bool(meta.get("real_close_reconciled"), False)
    data_quality = _safe_str(
        _pick(merged, ["broker_data_quality", "data_quality"], None)
        or _pick(meta, ["broker_data_quality", "data_quality"], "")
    ).upper()

    mode_ok = registry_mode == "REAL" or execution_mode in {"LIVE", "REAL"}
    reconciliation_ok = reconciled or data_quality.startswith("HIGH_BROKER_RECONCILED") or data_quality == "HIGH_REAL"
    if not (mode_ok and reconciliation_ok):
        return False

    strong_order_id = _strong_broker_order_id(merged, meta)
    exit_price = _safe_float(_pick(merged, ["exit_price", "exit", "close_price", "avg_exit_price"]))
    net_pnl = _safe_float(_pick(merged, ["net_pnl", "net_pnl_usdt", "pnl_usdt", "realized_pnl"]))
    r_net = _safe_float(_pick(merged, ["pnl_r", "r_multiple", "r_net", "result_r"]))
    financial_ok = net_pnl is not None or r_net is not None

    return bool(strong_order_id and exit_price is not None and financial_ok)


def _row_has_explicit_non_execution(row: Dict[str, Any]) -> bool:
    """True quando o registro descreve bloqueio/preview e não uma ordem real."""
    merged = _flatten_payload(row if isinstance(row, dict) else {})
    meta = merged.get("metadata") if isinstance(merged.get("metadata"), dict) else {}
    combined = dict(merged)
    combined.update({f"metadata_{k}": v for k, v in meta.items()})
    txt = json.dumps(combined, ensure_ascii=False, default=str).upper()

    negative_markers = [
        "NOT_ELIGIBLE_FOR_AUTO_REAL_EXECUTION",
        "NOT_ELIGIBLE",
        "ELIGIBILITY_DENIED",
        "PRECHECK_DENY",
        "PRECHECK_BLOCK",
        "EXECUTION_BLOCKED",
        "ORDER_BLOCKED",
        "NOT_SENT",
        "NO_ORDER_SENT",
        "WOULD_NOT_SEND",
        "WOULD_SEND_ORDER\": FALSE",
        "DRY_RUN",
        "SAFE_DRY_RUN",
        "BROKER_DRY_RUN",
        "\"MODE\": \"VERIFY\"",
        "\"EXECUTION_MODE\": \"VERIFY\"",
        "\"MODE\": \"PAPER\"",
        "\"EXECUTION_MODE\": \"PAPER\"",
        "\"MODE\": \"SHADOW\"",
        "OBSERVATION_ONLY",
        "PREVIEW_ONLY",
        "\"PREVIEW\": TRUE",
        "\"SENT\": FALSE",
        "\"ORDER_SENT\": FALSE",
        "\"LIVE_SENT\": FALSE",
        "\"BROKER_SENT\": FALSE",
        "\"REAL_SENT\": FALSE",
    ]
    return any(marker in txt for marker in negative_markers)


def _strong_broker_order_id(merged: Dict[str, Any], meta: Dict[str, Any]) -> Optional[str]:
    """Retorna ID de ordem/posição da exchange; client_order_id isolado não é prova."""
    keys = [
        "bingx_order_id", "broker_order_id", "exchange_order_id", "live_order_id",
        "order_id", "orderId", "position_id", "close_order_id", "exit_order_id",
        "stop_order_id", "disaster_stop_order_id",
    ]
    for mapping in (merged, meta):
        if not isinstance(mapping, dict):
            continue
        for key in keys:
            value = mapping.get(key)
            if _is_empty(value):
                continue
            value_s = _safe_str(value)
            if len(value_s) >= 6:
                return value_s
    return None


def _row_has_real_broker_evidence(row: Dict[str, Any]) -> bool:
    """Exige evidência positiva de execução real e rejeita previews/bloqueios.

    A palavra REAL dentro de NOT_ELIGIBLE_FOR_AUTO_REAL_EXECUTION não é prova.
    client_order_id também não basta sozinho, pois pode nascer antes do envio.
    Um CLOSED REAL reconciliado e financeiramente completo tem precedência sobre
    decisões históricas negativas preservadas apenas para auditoria no metadata.
    """
    merged = _flatten_payload(row if isinstance(row, dict) else {})
    meta = merged.get("metadata") if isinstance(merged.get("metadata"), dict) else {}

    if _authoritative_reconciled_real_close(row):
        return True

    if _row_has_explicit_non_execution(row):
        return False

    strong_order_id = _strong_broker_order_id(merged, meta)

    sent_flags = [
        "sent", "live_sent", "order_sent", "broker_sent", "real_sent",
        "executed", "filled", "broker_filled", "exchange_filled",
    ]
    sent_real = any(
        _safe_bool(mapping.get(key), False)
        for mapping in (merged, meta)
        if isinstance(mapping, dict)
        for key in sent_flags
    )

    event_values = _upper_values(merged, [
        "event", "event_raw", "status", "type", "kind", "route", "result",
        "execution_status", "broker_status", "order_status",
    ])
    mode_values = _upper_values(merged, [
        "mode", "execution_mode", "order_mode", "trade_mode", "environment",
    ])
    source_values = _upper_values(merged, [
        "source", "source_type", "origin", "executor", "executor_route",
        "broker", "exchange", "venue", "execution_source", "registry_source",
    ])
    combined = " ".join(event_values + mode_values + source_values)

    positive_events = [
        "LIVE_SENT", "ORDER_SENT", "ORDER_FILLED", "FILLED", "PARTIALLY_FILLED",
        "POSITION_OPENED", "POSITION_CLOSED", "REAL_CLOSE", "BROKER_FILL",
        "BINGX_FILL", "DISASTER_STOP_CREATED", "DISASTER_STOP_EXECUTED",
        "STOP_EXECUTED", "TP50_REAL_EXECUTED", "REAL_ORDER_SENT_BY_CENTRAL",
        "EXECUTION_ENGINE_REAL_TRADE_SYNC", "LIVE_ORDER_REGISTERED",
    ]
    explicit_positive_event = any(marker in combined for marker in positive_events)
    explicit_live_mode = any(v in {"LIVE", "REAL"} for v in mode_values)
    explicit_broker_source = any(
        marker in combined for marker in ["BINGX", "BROKER", "EXCHANGE"]
    )

    if strong_order_id and (sent_real or explicit_positive_event or explicit_live_mode or explicit_broker_source):
        return True
    if sent_real and (explicit_positive_event or explicit_live_mode or explicit_broker_source):
        return True
    if explicit_positive_event and explicit_broker_source:
        return True
    return False


_ORIGINAL_IS_REAL_TRADE_CANDIDATE_V25 = _is_real_trade_candidate

def _is_real_trade_candidate(item: Dict[str, Any], raw_row: Dict[str, Any], source: str) -> bool:  # type: ignore[override]
    source_name = str(source or "").lower().strip()

    # Fontes operacionais podem conter muitos PRECHECK/BLOCKED/NOT_ELIGIBLE.
    # O nome da fonte nunca basta; sempre exigimos evidência positiva no registro.
    operational_sources = {
        "trade_registry_json", "trade_registry_jsonl",
        "broker_executions_log", "broker_execution_audit_log",
        "execution_engine_log", "execution_log",
        "real_close_auto_evaluator", "auto_real_execution_bridge",
        "real_position_watchdog",
    }
    if source_name in operational_sources:
        return _row_has_real_broker_evidence(raw_row)

    # Fontes estatísticas/legadas seguem conservadoras e ainda precisam
    # satisfazer a evidência broker forte da V2.6.2.
    try:
        legacy_candidate = bool(_ORIGINAL_IS_REAL_TRADE_CANDIDATE_V25(item, raw_row, source))
    except Exception:
        legacy_candidate = False
    return bool(legacy_candidate and _row_has_real_broker_evidence(raw_row))


def _normalize_trade_v26(row: Dict[str, Any], source: str) -> Optional[Dict[str, Any]]:
    item = _normalize_trade(row, source)
    if not item:
        return None
    merged = _flatten_payload(row if isinstance(row, dict) else {})
    meta = merged.get("metadata") if isinstance(merged.get("metadata"), dict) else {}
    # Enriquece campos financeiros reais quando existirem no registry/metadata/BingX.
    for dst, keys in {
        "net_pnl_usdt": ["net_pnl", "net_pnl_usdt", "pnl_usdt"],
        "realized_pnl_usdt": ["realized_pnl_usdt", "realizedPnl", "realized_pnl", "closed_pnl_usdt", "income"],
        "r_net": ["pnl_r", "r_net", "r_multiple", "result_r"],
        "r_price": ["r_price"],
        "fees_usdt": ["fees_usdt", "fee_usdt", "commission", "fee", "fees"],
        "entry_order_id": ["entry_order_id", "order_id", "bingx_order_id", "live_order_id"],
        "exit_order_id": ["exit_order_id", "close_order_id", "stop_order_id"],
        "client_order_id": ["client_order_id", "clientOrderId", "client_tag"],
    }.items():
        val = _pick(merged, keys, None)
        if _is_empty(val) and isinstance(meta, dict):
            val = _pick(meta, keys, None)
        if not _is_empty(val):
            item[dst] = val
    # Em fechamento reconciliado, force as métricas líquidas de topo como verdade estatística.
    if _authoritative_reconciled_real_close(row):
        net_pnl = _safe_float(_pick(merged, ["net_pnl", "net_pnl_usdt", "pnl_usdt"]))
        r_net = _safe_float(_pick(merged, ["pnl_r", "r_net", "r_multiple", "result_r"]))
        if net_pnl is not None:
            item["pnl_usdt"] = round(net_pnl, 8)
        if r_net is not None:
            item["r"] = round(r_net, 8)
        item["financial_truth"] = "NET_PNL_AND_R_NET"

    # Se o registry usa result_pct/result_r, copie para pnl_pct/pnl_r.
    if _is_empty(item.get("pnl_pct")):
        val = _pick(merged, ["result_pct", "pnl_pct", "pnl_percent"], None)
        if not _is_empty(val):
            item["pnl_pct"] = _safe_float(val)
    if _is_empty(item.get("pnl_r")):
        val = _pick(merged, ["result_r", "pnl_r", "r"], None)
        if not _is_empty(val):
            item["pnl_r"] = _safe_float(val)
    item["real_audit_candidate"] = _is_real_trade_candidate(item, row, source)
    return item


def get_real_pnl_r_health() -> Dict[str, Any]:  # type: ignore[override]
    return {
        "ok": True,
        "available": True,
        "module": MODULE,
        "version": VERSION,
        "mode": MODE,
        "import_error": None,
        "files": {
            "trade_registry_json_exists": os.path.exists(TRADE_REGISTRY_JSON_FILE),
            "trade_registry_jsonl_exists": os.path.exists(TRADE_REGISTRY_FILE),
            "broker_executions_log_exists": os.path.exists(BROKER_EXECUTIONS_LOG_FILE),
            "broker_execution_audit_log_exists": os.path.exists(BROKER_EXECUTION_AUDIT_LOG_FILE),
            "history_events_exists": os.path.exists(HISTORY_EVENTS_FILE),
            "history_export_exists": os.path.exists(HISTORY_EXPORT_FILE),
            "decision_log_exists": os.path.exists(DECISION_LOG_FILE),
            "output_map_exists": os.path.exists(OUTPUT_MAP_FILE),
            "output_events_exists": os.path.exists(OUTPUT_EVENTS_FILE),
        },
        "notes": [
            "V2.6.3 reconhece CLOSED REAL reconciliado no Registry sem confundir metadata histórico PRECHECK/NOT_ELIGIBLE.",
            "Conta como Real PnL/R apenas registros com evidência LIVE/REAL/BROKER/BINGX/order_id.",
            "Se a exchange fechou a posição mas não houver fill/PnL salvo, o trade aparece como incompleto em diagnostics.",
        ],
    }


def build_real_pnl_r_map(limit: Optional[int] = None, commit: bool = True) -> Dict[str, Any]:  # type: ignore[override]
    _JSONL_READ_METADATA.clear()
    raw_sources: List[Tuple[str, List[Dict[str, Any]]]] = [
        ("trade_registry_json", _read_trade_registry_json_rows(limit=limit)),
        ("trade_registry_jsonl", _read_jsonl(TRADE_REGISTRY_FILE, limit=limit)),
        ("broker_executions_log", _read_jsonl(BROKER_EXECUTIONS_LOG_FILE, limit=limit)),
        ("broker_execution_audit_log", _read_jsonl(BROKER_EXECUTION_AUDIT_LOG_FILE, limit=limit)),
        ("execution_engine_log", _read_jsonl(EXECUTION_ENGINE_LOG_FILE, limit=limit)),
        ("execution_log", _read_jsonl(EXECUTION_LOG_FILE, limit=limit)),
        ("real_close_auto_evaluator", _read_jsonl(REAL_CLOSE_AUTO_EVALUATOR_EVENTS_FILE, limit=limit)),
        ("auto_real_execution_bridge", _read_jsonl(AUTO_REAL_EXECUTION_BRIDGE_EVENTS_FILE, limit=limit)),
        ("real_position_watchdog", _read_jsonl(REAL_POSITION_WATCHDOG_EVENTS_FILE, limit=limit)),
        ("history_events", _read_jsonl(HISTORY_EVENTS_FILE, limit=limit)),
        ("history_export", _load_history_export_rows()),
        ("decision_log", _read_jsonl(DECISION_LOG_FILE, limit=limit)),
    ]

    normalized: List[Dict[str, Any]] = []
    source_counts: Dict[str, int] = {}
    skipped_non_real_count = 0
    skipped_non_real_by_source: Dict[str, int] = defaultdict(int)
    for source, rows in raw_sources:
        source_counts[source] = len(rows)
        for row in rows:
            item = _normalize_trade_v26(row, source)
            if not item:
                continue
            if STRICT_REAL_SOURCES and not item.get("real_audit_candidate"):
                skipped_non_real_count += 1
                skipped_non_real_by_source[source] += 1
                continue
            normalized.append(item)

    merge_result = _merge_trades_with_diagnostics(normalized)
    merged = list(merge_result.get("records") or [])
    closed_identity_merge = dict(merge_result.get("diagnostics") or {})
    closed = [r for r in merged if r.get("closed") or r.get("status") == "CLOSED"]
    diagnostics = _diagnostics(merged)
    open_real_candidates = [r for r in merged if not (r.get("closed") or r.get("status") == "CLOSED")]
    diagnostics["real_candidates_not_closed"] = len(open_real_candidates)
    diagnostics["real_candidates_not_closed_recent"] = open_real_candidates[-25:]
    payload: Dict[str, Any] = {
        "ok": True,
        "version": VERSION,
        "module": MODULE,
        "generated_at": _now_br(),
        "mode": MODE,
        "notes": [
            "Real PnL/R Mapper V2.6.3 lê Registry JSON e prioriza fechamentos REAL reconciliados e financeiramente completos.",
            "Não mistura PAPER/VERIFY sem evidência broker.",
            "Trades fechados sem PnL/exit/order fill aparecem no diagnóstico para reconciliação.",
        ],
        "files": {
            "trade_registry_json": TRADE_REGISTRY_JSON_FILE,
            "trade_registry_jsonl": TRADE_REGISTRY_FILE,
            "broker_executions_log": BROKER_EXECUTIONS_LOG_FILE,
            "broker_execution_audit_log": BROKER_EXECUTION_AUDIT_LOG_FILE,
            "execution_engine_log": EXECUTION_ENGINE_LOG_FILE,
            "execution_log": EXECUTION_LOG_FILE,
            "history_events": HISTORY_EVENTS_FILE,
            "history_export": HISTORY_EXPORT_FILE,
            "decision_log": DECISION_LOG_FILE,
            "output_map": OUTPUT_MAP_FILE,
            "output_events": OUTPUT_EVENTS_FILE,
        },
        "source_counts": source_counts,
        "source_coverage": dict(_JSONL_READ_METADATA),
        "partial": any(item.get("partial") for item in _JSONL_READ_METADATA.values()),
        "coverage_complete": all(item.get("coverage_complete") for item in _JSONL_READ_METADATA.values()),
        "records_examined": sum(item.get("records_examined", 0) for item in _JSONL_READ_METADATA.values()),
        "bytes_read": sum(item.get("bytes_read", 0) for item in _JSONL_READ_METADATA.values()),
        "max_records": limit if limit is not None else AUTOMATIC_MAX_RECORDS,
        "max_bytes": AUTOMATIC_MAX_BYTES,
        "source_size_bytes": sum(item.get("source_size_bytes", 0) for item in _JSONL_READ_METADATA.values()),
        "strict_real_sources": STRICT_REAL_SOURCES,
        "skipped_non_real_count": skipped_non_real_count,
        "skipped_non_real_by_source": dict(sorted(skipped_non_real_by_source.items())),
        "normalized_count": len(normalized),
        "mapped_count": len(merged),
        "closed_count": len(closed),
        "closed_identity_merge": closed_identity_merge,
        "summary": _stats_for(closed),
        "diagnostics": diagnostics,
        "by_bot": _group_stats(closed, "bot"),
        "by_setup": _group_stats(closed, "setup"),
        "by_symbol": _group_stats(closed, "symbol"),
        "by_side": _group_stats(closed, "side"),
        "recent_closed": closed[-25:],
    }
    if commit and not closed_identity_merge.get("safe_to_commit", True):
        payload["ok"] = False
        payload["status"] = "CLOSED_IDENTITY_REVIEW_REQUIRED"
        payload["commit_blocked"] = True
        payload["commit_block_reason"] = "CLOSED_IDENTITY_MERGE_UNSAFE"
        payload["committed"] = False
    elif commit:
        _write_json(OUTPUT_MAP_FILE, payload)
        _append_jsonl(OUTPUT_EVENTS_FILE, {
            "event": "REAL_PNL_R_MAP_REBUILT",
            "version": VERSION,
            "generated_at": payload["generated_at"],
            "mapped_count": payload["mapped_count"],
            "closed_count": payload["closed_count"],
            "summary": payload["summary"],
            "diagnostics": payload["diagnostics"],
        })
        payload["committed"] = True
    else:
        payload["committed"] = False
    return payload


def build_real_pnl_r_text(payload: Optional[Dict[str, Any]] = None) -> str:  # type: ignore[override]
    if payload is None:
        payload = build_real_pnl_r_map(commit=False)
    summary = payload.get("summary", {}) or {}
    diagnostics = payload.get("diagnostics", {}) or {}
    by_issue = diagnostics.get("by_issue", {}) or {}
    lines = [
        "💰 REAL PNL/R MAPPER — CENTRAL QUANT V2.6.2",
        f"Data/hora: {payload.get('generated_at')}",
        f"Status: {'✅' if payload.get('ok') else '❌'}",
        f"Modo: {payload.get('mode', MODE)}",
        "",
        "Resumo geral:",
    ]
    if int(summary.get("trades", 0) or 0) <= 0:
        lines.append("- Nenhum trade real fechado auditável completo encontrado.")
        lines.append("- Se a BingX já fechou, falta fill/PnL financeiro salvo em fonte auditável ou o trade não carregou marcador broker/order_id.")
    lines += [
        f"- Trades fechados: {summary.get('trades', 0)}",
        f"- Wins: {summary.get('wins', 0)} | Losses: {summary.get('losses', 0)} | BE: {summary.get('breakeven', 0)}",
        f"- Win rate: {summary.get('win_rate_pct', 0)}%",
        f"- PnL total: {summary.get('pnl_total_pct', 0)}%",
        f"- PnL médio: {summary.get('pnl_avg_pct', 0)}%",
        f"- R total: {summary.get('r_total', 0)}R",
        f"- R médio: {summary.get('r_avg', 0)}R",
        f"- Profit factor: {summary.get('profit_factor_pct', 0)}",
        f"- Com PnL%: {summary.get('with_pnl_pct', 0)} | Com R: {summary.get('with_r', 0)}",
        "",
        "Fontes lidas:",
    ]
    for k, v in (payload.get("source_counts") or {}).items():
        lines.append(f"- {k}: {v}")
    lines += ["", "Diagnóstico:"]
    lines.append(f"- Fechados completos: {diagnostics.get('closed_complete', 0)}")
    lines.append(f"- Fechados incompletos: {diagnostics.get('closed_incomplete', 0)}")
    lines.append(f"- Candidatos reais ainda sem fechamento financeiro reconciliado: {diagnostics.get('real_candidates_not_closed', 0)}")
    if by_issue:
        for issue, count in by_issue.items():
            lines.append(f"- {issue}: {count}")
    else:
        lines.append("- Sem pendências de dados nos fechamentos mapeados.")
    lines.append("")
    lines.append("Por bot:")
    by_bot = payload.get("by_bot") or {}
    if not by_bot:
        lines.append("- Sem trades fechados mapeados por bot.")
    else:
        for bot, st in by_bot.items():
            lines.append(f"- {bot}: trades={st.get('trades', 0)} | win={st.get('win_rate_pct', 0)}% | PnL={st.get('pnl_total_pct', 0)}% | R={st.get('r_total', 0)}R")
    lines += [
        "",
        "Observação:",
        "- V2.6.3 exclui PRECHECK/NOT_ELIGIBLE/VERIFY, mas aceita CLOSED REAL reconciliado com order_id, exit e net_pnl/R líquido.",
        "- Continua observacional: não muda lote, risco, execução ou policies ativas.",
    ]
    return "\n".join(lines)
