# ==============================================================================
# CENTRAL QUANT - TRADE JOURNAL MANAGER
# Versão: 2026-07-02-TRADE-JOURNAL-V2-LIFECYCLE
#
# Objetivo:
# - Criar um diário persistente de trades encerrados da Central Quant.
# - Registrar contexto operacional do trade no fechamento.
# - Ler eventos do Super History sem quebrar Analytics/History atual.
# - Expor estatísticas por bot, setup, ativo, horário, dia da semana, regime e qualidade.
# - Funcionar em Render Free usando JSONL local/ephemeral.
# ==============================================================================

import json
import os
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import defaultdict, Counter

TIMEZONE_BR = timezone(timedelta(hours=-3))
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data"))).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)

JOURNAL_FILE = DATA_DIR / "trade_journal.jsonl"
JOURNAL_SEEN_FILE = DATA_DIR / "trade_journal_seen.json"
JOURNAL_EXPORT_FILE = DATA_DIR / "trade_journal_export.json"
JOURNAL_MAX_READ = int(os.environ.get("JOURNAL_MAX_READ", "5000"))
LIFECYCLE_FILE = DATA_DIR / "trade_lifecycle.jsonl"
LIFECYCLE_EXPORT_FILE = DATA_DIR / "trade_lifecycle_export.json"
LIFECYCLE_MAX_READ = int(os.environ.get("LIFECYCLE_MAX_READ", "10000"))
JOURNAL_SEEN_MAX = int(os.environ.get("JOURNAL_SEEN_MAX", "10000"))


def ensure_journal_files():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not JOURNAL_FILE.exists():
        JOURNAL_FILE.touch()
    if not JOURNAL_SEEN_FILE.exists():
        JOURNAL_SEEN_FILE.write_text("{}", encoding="utf-8")
    if not JOURNAL_EXPORT_FILE.exists():
        JOURNAL_EXPORT_FILE.write_text("{}", encoding="utf-8")
    if not LIFECYCLE_FILE.exists():
        LIFECYCLE_FILE.touch()
    if not LIFECYCLE_EXPORT_FILE.exists():
        LIFECYCLE_EXPORT_FILE.write_text("{}", encoding="utf-8")


ensure_journal_files()


def agora_sp():
    return datetime.now(TIMEZONE_BR)


def data_hora_sp_str():
    return agora_sp().strftime("%d/%m/%Y %H:%M")


def _json_default(value):
    try:
        return str(value)
    except Exception:
        return None


def _read_json(path, default):
    try:
        if not path.exists():
            return default
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _write_json(path, payload):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, default=_json_default)
        return True
    except Exception:
        return False


def _append_jsonl(path, item):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(item, ensure_ascii=False, default=_json_default) + "\n")
        return True
    except Exception as exc:
        print(f"ERRO JOURNAL append_jsonl {path}: {exc}")
        return False


def _read_jsonl_tail(path, limit=None):
    try:
        limit = int(limit or JOURNAL_MAX_READ)
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8") as f:
            lines = f.readlines()[-limit:]
        rows = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                rows.append({"raw": line})
        return rows
    except Exception as exc:
        print(f"ERRO JOURNAL read_jsonl {path}: {exc}")
        return []


def _safe_float(value, default=None):
    try:
        if value is None:
            return default
        if isinstance(value, str):
            value = value.replace("%", "").replace(",", ".").strip()
            if not value or value.lower() in {"none", "null", "nan", "n/a", "na"}:
                return default
        return float(value)
    except Exception:
        return default


def _safe_int(value, default=None):
    try:
        if value is None:
            return default
        return int(float(value))
    except Exception:
        return default


def _first(mapping, keys, default=None):
    if not isinstance(mapping, dict):
        return default
    for key in keys:
        if mapping.get(key) is not None and mapping.get(key) != "":
            return mapping.get(key)
    return default


def _nested_first(event, keys, default=None):
    if not isinstance(event, dict):
        return default
    value = _first(event, keys, None)
    if value is not None and value != "":
        return value
    for child_key in ["raw", "details", "payload", "context", "state", "event"]:
        child = event.get(child_key)
        if isinstance(child, dict):
            value = _nested_first(child, keys, None)
            if value is not None and value != "":
                return value
    return default


def normalize_symbol(symbol):
    s = str(symbol or "").upper().strip()
    if not s:
        return ""
    return s.replace("/USDT:USDT", "USDT").replace("/USDT", "USDT").replace("-", "")


def normalize_side(side):
    s = str(side or "").upper().strip()
    if s in {"BUY", "LONG"}:
        return "LONG"
    if s in {"SELL", "SHORT"}:
        return "SHORT"
    return s


def _parse_ts(value):
    if not value:
        return None
    text = str(value).strip()
    for fmt in ["%d/%m/%Y %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"]:
        try:
            return datetime.strptime(text.replace("Z", ""), fmt)
        except Exception:
            pass
    try:
        epoch = float(text)
        if epoch > 0:
            return datetime.fromtimestamp(epoch, TIMEZONE_BR).replace(tzinfo=None)
    except Exception:
        pass
    return None


def _minutes_between(start_value, end_value):
    start = _parse_ts(start_value)
    end = _parse_ts(end_value)
    if not start or not end:
        return None
    try:
        return round((end - start).total_seconds() / 60, 2)
    except Exception:
        return None


def _journal_uid(event):
    raw = event.get("raw") if isinstance(event.get("raw"), dict) else {}
    for key in ["journal_id", "close_id", "event_id", "uid"]:
        value = event.get(key) or raw.get(key)
        if value:
            return str(value)
    trade_id = event.get("trade_id") or raw.get("trade_id") or raw.get("position_id")
    closed_at = _nested_first(event, ["closed_at", "close_time", "ts", "timestamp", "created_at"], "")
    symbol = normalize_symbol(_nested_first(event, ["symbol", "ativo", "pair"], ""))
    side = normalize_side(_nested_first(event, ["side", "direction", "signal"], ""))
    return "|".join([str(trade_id or ""), symbol, side, str(closed_at or "")])


def _dedup_seen(uid):
    try:
        seen = _read_json(JOURNAL_SEEN_FILE, {})
        if not isinstance(seen, dict):
            seen = {}
        if uid in seen:
            return True
        seen[uid] = time.time()
        if len(seen) > JOURNAL_SEEN_MAX:
            seen = dict(sorted(seen.items(), key=lambda x: x[1])[-JOURNAL_SEEN_MAX:])
        _write_json(JOURNAL_SEEN_FILE, seen)
        return False
    except Exception:
        return False


def _result_label(pnl_pct, result_value=None):
    result_text = str(result_value or "").upper().strip()
    if result_text in {"WIN", "LOSS", "BE", "BREAKEVEN"}:
        return "BREAKEVEN" if result_text in {"BE", "BREAKEVEN"} else result_text
    if pnl_pct is None:
        return "UNKNOWN"
    if pnl_pct > 0:
        return "WIN"
    if pnl_pct < 0:
        return "LOSS"
    return "BREAKEVEN"


def build_journal_trade(event):
    """Converte um evento TRADE_CLOSED do history em uma linha rica do Trade Journal."""
    if not isinstance(event, dict):
        return None

    event_type = str(event.get("event") or event.get("event_type") or event.get("type") or "").upper()
    if event_type and event_type != "TRADE_CLOSED":
        return None

    raw = event.get("raw") if isinstance(event.get("raw"), dict) else {}
    uid = _journal_uid(event)

    opened_at = _nested_first(event, ["opened_at", "open_time", "entry_time", "created_at_entry"], None)
    closed_at = _nested_first(event, ["closed_at", "close_time", "exit_time", "timestamp", "created_at", "ts"], None) or event.get("ts")
    closed_dt = _parse_ts(closed_at) or _parse_ts(event.get("ts")) or agora_sp().replace(tzinfo=None)

    entry = _safe_float(_nested_first(event, ["entry", "entrada", "entry_price"], None), None)
    exit_price = _safe_float(_nested_first(event, ["exit_price", "close_price", "price", "exit", "saida"], None), None)
    stop = _safe_float(_nested_first(event, ["stop", "sl", "initial_sl", "stop_atual"], None), None)
    tp50 = _safe_float(_nested_first(event, ["tp50", "tp_50", "take_profit_50"], None), None)

    pnl_pct = _safe_float(_nested_first(event, ["pnl_pct", "result_pct", "pnl", "resultado_pct", "current_pct", "open_pct"], None), None)
    result_r = _safe_float(_nested_first(event, ["result_r", "pnl_r", "r_result", "current_r", "open_r"], None), None)
    mfe_pct = _safe_float(_nested_first(event, ["mfe_pct", "max_favorable_excursion_pct", "max_pnl_pct"], None), None)
    mae_pct = _safe_float(_nested_first(event, ["mae_pct", "max_adverse_excursion_pct", "min_pnl_pct"], None), None)
    giveback_pct = _safe_float(_nested_first(event, ["giveback_pct", "devolucao_pct", "giveback"], None), None)
    if giveback_pct is None and mfe_pct is not None and pnl_pct is not None:
        giveback_pct = round(mfe_pct - pnl_pct, 6)

    duration_minutes = _safe_float(_nested_first(event, ["duration_minutes", "minutes_in_trade", "tempo_minutos"], None), None)
    if duration_minutes is None:
        duration_minutes = _minutes_between(opened_at, closed_at)

    result_value = _nested_first(event, ["result", "result_type", "status", "resultado"], None)

    return {
        "journal_id": uid,
        "created_at": data_hora_sp_str(),
        "closed_at": str(closed_at or event.get("ts") or data_hora_sp_str()),
        "opened_at": opened_at,
        "epoch": _safe_float(event.get("epoch"), time.time()),
        "hour": int(closed_dt.hour),
        "weekday": closed_dt.strftime("%A"),
        "weekday_num": int(closed_dt.weekday()),
        "trade_id": str(_nested_first(event, ["trade_id", "position_id", "client_trade_id"], "")),
        "bot": str(_nested_first(event, ["bot", "bot_name", "source", "strategy"], "") or "").upper(),
        "setup": str(_nested_first(event, ["setup", "signal_type", "setup_label", "strategy"], "") or "").upper(),
        "symbol": normalize_symbol(_nested_first(event, ["symbol", "ativo", "pair", "ticker"], "")),
        "side": normalize_side(_nested_first(event, ["side", "direction", "signal"], "")),
        "entry": entry,
        "exit_price": exit_price,
        "stop": stop,
        "tp50": tp50,
        "risk_pct": _safe_float(_nested_first(event, ["risk_pct", "risco_pct", "risk"], None), None),
        "pnl_pct": pnl_pct,
        "result_r": result_r,
        "result": _result_label(pnl_pct, result_value),
        "mfe_pct": mfe_pct,
        "mae_pct": mae_pct,
        "giveback_pct": giveback_pct,
        "duration_minutes": duration_minutes,
        "exit_reason": _nested_first(event, ["exit_reason", "reason", "motivo"], None),
        "score": _safe_float(_nested_first(event, ["score", "signal_score", "meme_score", "qualidade_pontos"], None), None),
        "quality": _nested_first(event, ["quality", "qualidade", "classification"], None),
        "adx": _safe_float(_nested_first(event, ["adx", "adx_h4", "adx_h1"], None), None),
        "atr": _safe_float(_nested_first(event, ["atr", "atr_pct", "atr_h1", "atr_h4"], None), None),
        "rsi": _safe_float(_nested_first(event, ["rsi", "rsi_h1", "rsi_h4"], None), None),
        "volume_status": _nested_first(event, ["volume_status", "volume", "volume_label"], None),
        "market_regime": _nested_first(event, ["market_regime", "regime", "trend_regime"], None),
        "btc_alignment": _nested_first(event, ["btc_alignment", "btc_aligned", "btc_context"], None),
        "timeframe": _nested_first(event, ["timeframe", "tf"], None),
        "entry_reason": _nested_first(event, ["entry_reason", "signal_reason", "motivo_entrada"], None),
        "raw_event": raw or event,
    }


def append_journal_trade(event):
    trade = build_journal_trade(event)
    if not trade:
        return {"ok": False, "error": "evento não é TRADE_CLOSED válido"}
    uid = trade.get("journal_id")
    if uid and _dedup_seen(uid):
        return {"ok": True, "dedup": True, "journal_id": uid}
    ok = _append_jsonl(JOURNAL_FILE, trade)
    return {"ok": ok, "dedup": False, "journal_id": uid, "trade": trade}


def load_journal_trades(limit=None):
    rows = _read_jsonl_tail(JOURNAL_FILE, limit=limit or JOURNAL_MAX_READ)
    return [row for row in rows if isinstance(row, dict)]


def _match_filters(row, filters):
    filters = filters or {}
    for key in ["bot", "setup", "symbol", "side", "result", "quality", "market_regime"]:
        wanted = str(filters.get(key) or "").strip().upper()
        if wanted and str(row.get(key) or "").strip().upper() != wanted:
            return False
    hour = filters.get("hour")
    if hour is not None and str(hour) != "":
        try:
            if int(row.get("hour")) != int(hour):
                return False
        except Exception:
            return False
    days = filters.get("days")
    if days:
        try:
            cutoff = agora_sp().replace(tzinfo=None) - timedelta(days=int(days))
            row_dt = _parse_ts(row.get("closed_at"))
            if row_dt and row_dt < cutoff:
                return False
        except Exception:
            pass
    return True


def query_journal(bot=None, setup=None, symbol=None, side=None, result=None, quality=None, market_regime=None, hour=None, days=None, limit=None):
    filters = {
        "bot": bot,
        "setup": setup,
        "symbol": normalize_symbol(symbol) if symbol else None,
        "side": normalize_side(side) if side else None,
        "result": result,
        "quality": quality,
        "market_regime": market_regime,
        "hour": hour,
        "days": days,
    }
    rows = [row for row in load_journal_trades(limit=limit or JOURNAL_MAX_READ) if _match_filters(row, filters)]
    return {
        "ok": True,
        "generated_at": data_hora_sp_str(),
        "filters": {k: v for k, v in filters.items() if v not in {None, ""}},
        "stats": calculate_journal_stats(rows),
        "trades": rows[-int(limit):] if limit else rows,
    }


def calculate_journal_stats(rows=None):
    rows = list(rows or [])
    trades = len(rows)
    pnl_values = [_safe_float(row.get("pnl_pct"), None) for row in rows]
    pnl_values = [x for x in pnl_values if x is not None]
    r_values = [_safe_float(row.get("result_r"), None) for row in rows]
    r_values = [x for x in r_values if x is not None]
    mfe_values = [_safe_float(row.get("mfe_pct"), None) for row in rows]
    mfe_values = [x for x in mfe_values if x is not None]
    mae_values = [_safe_float(row.get("mae_pct"), None) for row in rows]
    mae_values = [x for x in mae_values if x is not None]
    giveback_values = [_safe_float(row.get("giveback_pct"), None) for row in rows]
    giveback_values = [x for x in giveback_values if x is not None]
    duration_values = [_safe_float(row.get("duration_minutes"), None) for row in rows]
    duration_values = [x for x in duration_values if x is not None]

    wins = sum(1 for x in pnl_values if x > 0)
    losses = sum(1 for x in pnl_values if x < 0)
    breakeven = sum(1 for x in pnl_values if x == 0)
    gross_win = sum(x for x in pnl_values if x > 0)
    gross_loss = abs(sum(x for x in pnl_values if x < 0))
    avg_win = gross_win / wins if wins else 0.0
    avg_loss = gross_loss / losses if losses else 0.0

    return {
        "trades": trades,
        "wins": wins,
        "losses": losses,
        "breakeven": breakeven,
        "win_rate_pct": round((wins / len(pnl_values)) * 100, 2) if pnl_values else 0.0,
        "pnl_total_pct": round(sum(pnl_values), 4),
        "pnl_avg_pct": round(sum(pnl_values) / len(pnl_values), 4) if pnl_values else 0.0,
        "r_total": round(sum(r_values), 4),
        "r_avg": round(sum(r_values) / len(r_values), 4) if r_values else 0.0,
        "avg_win_pct": round(avg_win, 4),
        "avg_loss_pct": round(avg_loss, 4),
        "profit_factor_pct": round(gross_win / gross_loss, 4) if gross_loss else (999 if gross_win else 0),
        "expectancy_pct": round(((wins / len(pnl_values)) * avg_win) - ((losses / len(pnl_values)) * avg_loss), 4) if pnl_values else 0.0,
        "mfe_avg_pct": round(sum(mfe_values) / len(mfe_values), 4) if mfe_values else 0.0,
        "mae_avg_pct": round(sum(mae_values) / len(mae_values), 4) if mae_values else 0.0,
        "giveback_avg_pct": round(sum(giveback_values) / len(giveback_values), 4) if giveback_values else 0.0,
        "duration_avg_minutes": round(sum(duration_values) / len(duration_values), 2) if duration_values else 0.0,
    }


def group_journal_stats(group_by="bot", rows=None):
    allowed = {"bot", "setup", "symbol", "side", "hour", "weekday", "quality", "market_regime", "btc_alignment"}
    if group_by not in allowed:
        raise ValueError(f"group_by deve ser um destes: {sorted(allowed)}")
    rows = list(rows if rows is not None else load_journal_trades())
    buckets = defaultdict(list)
    for row in rows:
        key = row.get(group_by)
        if key is None or key == "":
            key = "N/A"
        buckets[str(key)].append(row)
    return {key: calculate_journal_stats(items) for key, items in sorted(buckets.items())}


def build_journal_payload(group_by="bot", days=None, limit=None):
    query = query_journal(days=days, limit=limit)
    rows = query.get("trades", [])
    return {
        "ok": True,
        "generated_at": data_hora_sp_str(),
        "files": {
            "journal": str(JOURNAL_FILE),
            "seen": str(JOURNAL_SEEN_FILE),
            "export": str(JOURNAL_EXPORT_FILE),
        },
        "filters": {"days": days or None, "limit": limit or None, "group_by": group_by},
        "stats": calculate_journal_stats(rows),
        "groups": group_journal_stats(group_by=group_by, rows=rows),
        "recent_trades": rows[-20:],
    }


def build_journal_report(group_by="bot", days=None, limit=None):
    payload = build_journal_payload(group_by=group_by, days=days, limit=limit)
    stats = payload.get("stats", {})
    groups = payload.get("groups", {})

    title_map = {
        "bot": "por bot",
        "setup": "por setup",
        "symbol": "por ativo",
        "side": "por lado",
        "hour": "por horário",
        "weekday": "por dia da semana",
        "quality": "por qualidade",
        "market_regime": "por regime",
        "btc_alignment": "por alinhamento BTC",
    }

    lines = [
        "📓 TRADE JOURNAL — CENTRAL QUANT",
        f"Data/hora: {data_hora_sp_str()}",
        f"Agrupamento: {title_map.get(group_by, group_by)}",
        "",
        "Resumo geral:",
        f"Trades: {stats.get('trades', 0)}",
        f"Wins: {stats.get('wins', 0)} | Losses: {stats.get('losses', 0)} | BE: {stats.get('breakeven', 0)}",
        f"Win rate: {stats.get('win_rate_pct', 0)}%",
        f"PnL total: {stats.get('pnl_total_pct', 0)}%",
        f"Expectancy: {stats.get('expectancy_pct', 0)}%",
        f"Profit Factor: {stats.get('profit_factor_pct', 0)}",
        f"MFE médio: {stats.get('mfe_avg_pct', 0)}%",
        f"MAE médio: {stats.get('mae_avg_pct', 0)}%",
        f"Giveback médio: {stats.get('giveback_avg_pct', 0)}%",
        f"Duração média: {stats.get('duration_avg_minutes', 0)} min",
        "",
        "Detalhe:",
    ]

    ordered = sorted(
        groups.items(),
        key=lambda item: (
            -item[1].get("pnl_total_pct", 0),
            -item[1].get("trades", 0),
            str(item[0]),
        ),
    )
    if not ordered:
        lines.append("Nenhum trade encerrado registrado no Journal ainda.")
    for name, item in ordered:
        lines += [
            "",
            f"{name}",
            f"Trades: {item.get('trades', 0)} | WR: {item.get('win_rate_pct', 0)}% | PnL: {item.get('pnl_total_pct', 0)}%",
            f"Exp: {item.get('expectancy_pct', 0)}% | PF: {item.get('profit_factor_pct', 0)} | MFE: {item.get('mfe_avg_pct', 0)}% | MAE: {item.get('mae_avg_pct', 0)}% | Giveback: {item.get('giveback_avg_pct', 0)}%",
        ]

    return "\n".join(lines)


def export_journal(limit=None):
    rows = load_journal_trades(limit=limit or JOURNAL_MAX_READ)
    payload = {
        "ok": True,
        "generated_at": data_hora_sp_str(),
        "stats": calculate_journal_stats(rows),
        "trades": rows,
    }
    _write_json(JOURNAL_EXPORT_FILE, payload)
    return payload



# ==============================================================================
# TRADE LIFECYCLE JOURNAL V2
# ============================================================================
LIFECYCLE_EVENTS = {
    "SIGNAL_CREATED",
    "TRADE_OPENED",
    "TP50_HIT",
    "BREAKEVEN",
    "TRAILING_UPDATED",
    "TRADE_CLOSED",
    "TRADE_BLOCKED",
}


def _event_lifecycle_uid(event):
    if not isinstance(event, dict):
        return f"raw-{time.time()}"
    raw_uid = _first(event, ["uid", "event_id", "id"], None)
    event_name = str(_first(event, ["event", "event_type", "type"], "EVENT") or "EVENT").upper()
    trade_id = _first(event, ["trade_id", "position_id", "client_trade_id"], "")
    symbol = normalize_symbol(_nested_first(event, ["symbol", "ativo", "pair", "ticker"], ""))
    side = normalize_side(_nested_first(event, ["side", "direction", "signal"], ""))
    ts = _first(event, ["ts", "timestamp", "created_at", "closed_at", "event_ts", "epoch"], "")
    if raw_uid:
        return f"lifecycle|{event_name}|{raw_uid}"
    return f"lifecycle|{event_name}|{trade_id}|{symbol}|{side}|{ts}"


def normalize_lifecycle_event(event):
    """Converte qualquer evento operacional do History em uma linha de ciclo do trade."""
    if not isinstance(event, dict):
        return None
    event_name = str(_first(event, ["event", "event_type", "type"], "EVENT") or "EVENT").upper().strip()
    if event_name not in LIFECYCLE_EVENTS:
        return None

    raw = event.get("raw") if isinstance(event.get("raw"), dict) else event
    trade_id = _first(event, ["trade_id", "position_id", "client_trade_id"], None) or _nested_first(raw, ["trade_id", "position_id", "client_trade_id"], None)
    bot = str(_nested_first(event, ["bot", "bot_name", "strategy", "source"], "") or "").upper().strip()
    source = str(_first(event, ["source"], bot or "central") or "central").lower()
    symbol = normalize_symbol(_nested_first(event, ["symbol", "ativo", "pair", "ticker"], ""))
    side = normalize_side(_nested_first(event, ["side", "direction", "signal"], ""))
    setup = str(_nested_first(event, ["setup", "signal_type", "setup_label", "strategy"], "") or "").upper().strip()
    ts = _first(event, ["ts", "created_at", "timestamp", "closed_at"], None) or data_hora_sp_str()
    epoch = _safe_float(_first(event, ["epoch"], None), time.time())

    if not trade_id:
        # fallback estável o bastante para sinais/entradas sem id explícito
        trade_id = f"{bot or source}|{symbol}|{side}|{setup}|{ts}"

    return {
        "uid": _event_lifecycle_uid(event),
        "ts": ts,
        "epoch": epoch,
        "event": event_name,
        "source": source,
        "trade_id": str(trade_id),
        "bot": bot or source.upper(),
        "setup": setup,
        "symbol": symbol,
        "side": side,
        "score": _safe_float(_nested_first(event, ["score", "signal_score", "meme_score", "qualidade_pontos"], None), None),
        "quality": _nested_first(event, ["quality", "qualidade", "classification"], None),
        "entry": _safe_float(_nested_first(event, ["entry", "entrada", "entry_price"], None), None),
        "stop": _safe_float(_nested_first(event, ["stop", "sl", "initial_sl", "stop_atual"], None), None),
        "tp50": _safe_float(_nested_first(event, ["tp50", "tp_50"], None), None),
        "exit_price": _safe_float(_nested_first(event, ["exit_price", "close_price", "price", "exit"], None), None),
        "result_pct": _safe_float(_nested_first(event, ["result_pct", "pnl_pct", "current_pct", "open_pct", "pnl"], None), None),
        "result_r": _safe_float(_nested_first(event, ["result_r", "pnl_r", "current_r", "open_r"], None), None),
        "mfe_pct": _safe_float(_nested_first(event, ["mfe_pct", "max_favorable_excursion_pct", "max_profit_pct"], None), None),
        "mae_pct": _safe_float(_nested_first(event, ["mae_pct", "max_adverse_excursion_pct", "max_drawdown_pct"], None), None),
        "reason": _nested_first(event, ["reason", "motivo", "exit_reason", "block_reason"], None),
        "raw": event,
    }


def append_lifecycle_event(event):
    item = normalize_lifecycle_event(event)
    if not item:
        return {"ok": False, "skipped": True, "error": "evento não é lifecycle válido"}
    uid = item.get("uid")
    if uid and _dedup_seen(uid):
        return {"ok": True, "dedup": True, "uid": uid}
    ok = _append_jsonl(LIFECYCLE_FILE, item)
    return {"ok": ok, "dedup": False, "event": item}


def load_lifecycle_events(limit=None):
    rows = _read_jsonl_tail(LIFECYCLE_FILE, limit=limit or LIFECYCLE_MAX_READ)
    # Compatibilidade: trades fechados da V1 também aparecem como ciclo fechado.
    if not rows:
        for trade in load_journal_trades(limit=JOURNAL_MAX_READ):
            rows.append({
                "uid": f"compat|closed|{trade.get('trade_id') or trade.get('uid')}",
                "ts": trade.get("closed_at") or trade.get("ts") or data_hora_sp_str(),
                "epoch": trade.get("epoch") or time.time(),
                "event": "TRADE_CLOSED",
                "source": trade.get("source") or str(trade.get("bot") or "central").lower(),
                "trade_id": str(trade.get("trade_id") or trade.get("uid") or ""),
                "bot": trade.get("bot"),
                "setup": trade.get("setup"),
                "symbol": trade.get("symbol"),
                "side": trade.get("side"),
                "entry": trade.get("entry"),
                "stop": trade.get("stop"),
                "tp50": trade.get("tp50"),
                "exit_price": trade.get("exit_price"),
                "result_pct": trade.get("result_pct"),
                "result_r": trade.get("result_r"),
                "mfe_pct": trade.get("mfe_pct"),
                "mae_pct": trade.get("mae_pct"),
                "quality": trade.get("quality"),
                "score": trade.get("score"),
                "reason": trade.get("exit_reason") or trade.get("reason"),
                "raw": trade,
            })
    rows.sort(key=lambda x: _safe_float(x.get("epoch"), 0) or 0)
    return rows[-int(limit or LIFECYCLE_MAX_READ):]


def query_lifecycle(days=None, limit=None, event=None, bot=None, symbol=None, setup=None, status=None, side=None, quality=None, market_regime=None, hour=None, **kwargs):
    rows = load_lifecycle_events(limit=limit or LIFECYCLE_MAX_READ)
    cutoff = None
    if days:
        try:
            cutoff = time.time() - (float(days) * 86400)
        except Exception:
            cutoff = None
    result = []
    for row in rows:
        if cutoff and (_safe_float(row.get("epoch"), 0) or 0) < cutoff:
            continue
        if event and str(row.get("event") or "").upper() != str(event).upper():
            continue
        if bot and str(row.get("bot") or "").upper() != str(bot).upper():
            continue
        if symbol and normalize_symbol(row.get("symbol")) != normalize_symbol(symbol):
            continue
        if setup and str(row.get("setup") or "").upper() != str(setup).upper():
            continue
        if side and str(row.get("side") or "").upper() != str(side).upper():
            continue
        if quality and str(row.get("quality") or "").upper() != str(quality).upper():
            continue
        if market_regime and str(row.get("market_regime") or row.get("regime") or "").upper() != str(market_regime).upper():
            continue
        if hour not in (None, ""):
            try:
                target_hour = int(hour)
                row_hour = row.get("hour")
                if row_hour is None:
                    dt = _parse_ts(row.get("ts"))
                    row_hour = dt.hour if dt else None
                if row_hour is None or int(row_hour) != target_hour:
                    continue
            except Exception:
                pass
        result.append(row)
    lifecycles = build_trade_lifecycles(result)
    if status:
        status = str(status).lower()
        lifecycles = [x for x in lifecycles if str(x.get("status") or "").lower() == status]
    return {
        "ok": True,
        "generated_at": data_hora_sp_str(),
        "filters": {"days": days, "limit": limit, "event": event, "bot": bot, "symbol": symbol, "setup": setup, "status": status, "side": side, "quality": quality, "market_regime": market_regime, "hour": hour},
        "events": result[-int(limit or LIFECYCLE_MAX_READ):],
        "lifecycles": lifecycles,
        "summary": summarize_lifecycles(lifecycles),
    }


def build_trade_lifecycles(rows=None):
    rows = list(rows if rows is not None else load_lifecycle_events())
    buckets = defaultdict(list)
    for row in rows:
        tid = row.get("trade_id") or row.get("uid") or "SEM_ID"
        buckets[str(tid)].append(row)

    lifecycles = []
    closed_events = {"TRADE_CLOSED"}
    blocked_events = {"TRADE_BLOCKED"}
    for trade_id, events in buckets.items():
        events.sort(key=lambda x: _safe_float(x.get("epoch"), 0) or 0)
        first = events[0] if events else {}
        last = events[-1] if events else {}
        names = [str(e.get("event") or "") for e in events]
        status = "OPEN"
        if any(x in closed_events for x in names):
            status = "CLOSED"
        elif any(x in blocked_events for x in names):
            status = "BLOCKED"
        elif "SIGNAL_CREATED" in names and "TRADE_OPENED" not in names:
            status = "SIGNAL_ONLY"
        started_at = first.get("ts")
        updated_at = last.get("ts")
        duration = _minutes_between(started_at, updated_at)
        lifecycles.append({
            "trade_id": trade_id,
            "status": status,
            "bot": last.get("bot") or first.get("bot"),
            "setup": last.get("setup") or first.get("setup"),
            "symbol": last.get("symbol") or first.get("symbol"),
            "side": last.get("side") or first.get("side"),
            "started_at": started_at,
            "updated_at": updated_at,
            "duration_minutes": duration,
            "event_count": len(events),
            "events": names,
            "last_event": last.get("event"),
            "entry": last.get("entry") or first.get("entry"),
            "stop": last.get("stop") or first.get("stop"),
            "tp50": last.get("tp50") or first.get("tp50"),
            "exit_price": last.get("exit_price"),
            "result_pct": last.get("result_pct"),
            "result_r": last.get("result_r"),
            "mfe_pct": last.get("mfe_pct"),
            "mae_pct": last.get("mae_pct"),
            "quality": last.get("quality") or first.get("quality"),
            "score": last.get("score") or first.get("score"),
            "reason": last.get("reason"),
            "timeline": events,
        })
    lifecycles.sort(key=lambda x: _parse_ts(x.get("updated_at")) or datetime.min, reverse=True)
    return lifecycles


def summarize_lifecycles(lifecycles):
    total = len(lifecycles or [])
    by_status = Counter([x.get("status") or "N/A" for x in lifecycles or []])
    by_bot = Counter([x.get("bot") or "N/A" for x in lifecycles or []])
    by_event = Counter()
    for item in lifecycles or []:
        for event in item.get("events") or []:
            by_event[event] += 1
    return {
        "trades": total,
        "open": by_status.get("OPEN", 0),
        "closed": by_status.get("CLOSED", 0),
        "blocked": by_status.get("BLOCKED", 0),
        "signal_only": by_status.get("SIGNAL_ONLY", 0),
        "by_status": dict(by_status),
        "by_bot": dict(by_bot),
        "by_event": dict(by_event),
    }


def build_lifecycle_report(days=None, limit=None, status=None, event=None, bot=None, symbol=None, setup=None, side=None, quality=None, market_regime=None, hour=None, **kwargs):
    payload = query_lifecycle(days=days, limit=limit, status=status, event=event, bot=bot, symbol=symbol, setup=setup, side=side, quality=quality, market_regime=market_regime, hour=hour)
    summary = payload.get("summary", {})
    lifecycles = payload.get("lifecycles", [])
    lines = [
        "📓 TRADE LIFECYCLE JOURNAL — CENTRAL QUANT",
        f"Data/hora: {data_hora_sp_str()}",
        "",
        "Resumo:",
        f"Ciclos: {summary.get('trades', 0)}",
        f"Abertos: {summary.get('open', 0)} | Fechados: {summary.get('closed', 0)} | Bloqueados: {summary.get('blocked', 0)} | Só sinal: {summary.get('signal_only', 0)}",
        "",
        "Eventos:",
    ]
    by_event = summary.get("by_event", {}) or {}
    if by_event:
        for name, count in sorted(by_event.items(), key=lambda x: (-x[1], x[0])):
            lines.append(f"{name}: {count}")
    else:
        lines.append("Nenhum evento de lifecycle registrado ainda.")

    lines += ["", "Últimos ciclos:"]
    if not lifecycles:
        lines.append("Nenhum ciclo registrado ainda.")
    for item in lifecycles[:20]:
        result = item.get("result_pct")
        result_txt = f" | PnL: {result}%" if result is not None else ""
        lines.append(
            f"{item.get('status')} | {item.get('bot')} {item.get('symbol')} {item.get('side')} {item.get('setup')} | "
            f"Eventos: {item.get('event_count')} | Último: {item.get('last_event')}{result_txt}"
        )
    return "\n".join(lines)


def export_lifecycle(limit=None):
    rows = load_lifecycle_events(limit=limit or LIFECYCLE_MAX_READ)
    lifecycles = build_trade_lifecycles(rows)
    payload = {
        "ok": True,
        "generated_at": data_hora_sp_str(),
        "files": {"lifecycle": str(LIFECYCLE_FILE), "export": str(LIFECYCLE_EXPORT_FILE)},
        "summary": summarize_lifecycles(lifecycles),
        "events": rows,
        "lifecycles": lifecycles,
    }
    _write_json(LIFECYCLE_EXPORT_FILE, payload)
    return payload

def get_status():
    return {
        "ok": True,
        "module": "journal_manager",
        "version": "2026-07-02-TRADE-JOURNAL-V2-LIFECYCLE",
        "data_dir": str(DATA_DIR),
        "journal_file": str(JOURNAL_FILE),
        "lifecycle_file": str(LIFECYCLE_FILE),
        "seen_file": str(JOURNAL_SEEN_FILE),
        "export_file": str(JOURNAL_EXPORT_FILE),
        "lifecycle_export_file": str(LIFECYCLE_EXPORT_FILE),
        "max_read": JOURNAL_MAX_READ,
        "lifecycle_max_read": LIFECYCLE_MAX_READ,
        "trades_loaded": len(load_journal_trades(limit=JOURNAL_MAX_READ)),
        "lifecycle_events_loaded": len(load_lifecycle_events(limit=LIFECYCLE_MAX_READ)),
    }
