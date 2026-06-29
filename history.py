# ============================================================
# HISTORY - SUPER CENTRAL QUANT
# Arquivo pronto para registrar histórico persistente em JSONL
# Versão inicial simples: salva eventos no arquivo history.jsonl
# ============================================================

import json
import os
from datetime import datetime, timezone
from collections import defaultdict, Counter


HISTORY_FILE = os.getenv("HISTORY_FILE", "history.jsonl")
MAX_EXPORT_EVENTS_DEFAULT = 1000


def _now_iso():
    """Data/hora atual em formato ISO."""
    return datetime.now(timezone.utc).isoformat()


def _safe_float(value, default=0.0):
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def log_event(event_type, data=None):
    """
    Registra qualquer evento importante da Central Quant.

    Exemplos:
        log_event("trade_opened", {"bot": "Turtle", "symbol": "ETHUSDT"})
        log_event("trade_closed", {"bot": "Falcon", "symbol": "BTCUSDT", "pnl_pct": 1.25, "result": "WIN"})
        log_event("trade_blocked", {"bot": "Predator", "symbol": "SOLUSDT", "reason": "risco alto"})
    """
    if data is None:
        data = {}

    event = {
        "timestamp": _now_iso(),
        "type": event_type,
        **data,
    }

    try:
        with open(HISTORY_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
        return {"ok": True, "event": event}
    except Exception as e:
        return {"ok": False, "error": str(e), "event": event}


def read_history(limit=200):
    """
    Lê os últimos eventos do histórico.
    """
    if not os.path.exists(HISTORY_FILE):
        return []

    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()

        if limit:
            lines = lines[-int(limit):]

        events = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except Exception:
                continue
        return events
    except Exception:
        return []


def export_history(limit=MAX_EXPORT_EVENTS_DEFAULT):
    """
    Exporta o histórico em formato JSON.
    Ideal para copiar e colar no ChatGPT.
    """
    return {
        "ok": True,
        "history_file": HISTORY_FILE,
        "count": len(read_history(limit=limit)),
        "events": read_history(limit=limit),
    }


def get_history_summary(limit=500):
    """
    Gera um resumo simples dos eventos recentes.
    """
    events = read_history(limit=limit)

    if not events:
        return {
            "ok": True,
            "message": "Nenhum evento registrado ainda.",
            "events_count": 0,
        }

    by_type = Counter(e.get("type", "unknown") for e in events)
    by_bot = Counter(e.get("bot", "sem_bot") for e in events if e.get("bot"))
    by_symbol = Counter(e.get("symbol", "sem_ativo") for e in events if e.get("symbol"))

    last_events = events[-20:]

    return {
        "ok": True,
        "events_count": len(events),
        "by_type": dict(by_type),
        "by_bot": dict(by_bot),
        "by_symbol": dict(by_symbol),
        "last_events": last_events,
    }


def get_riskstats(limit=2000):
    """
    Calcula estatísticas básicas usando eventos do History.
    Procura principalmente eventos do tipo trade_closed e trade_blocked.
    """
    events = read_history(limit=limit)

    closed = [e for e in events if e.get("type") == "trade_closed"]
    blocked = [e for e in events if e.get("type") == "trade_blocked"]

    wins = 0
    losses = 0
    breakevens = 0
    pnl_total = 0.0

    pnl_by_bot = defaultdict(float)
    pnl_by_symbol = defaultdict(float)
    trades_by_bot = Counter()
    trades_by_symbol = Counter()
    result_by_bot = defaultdict(Counter)
    blocked_reasons = Counter()

    for e in closed:
        bot = e.get("bot", "sem_bot")
        symbol = e.get("symbol", "sem_ativo")
        result = str(e.get("result", "")).upper()
        pnl = _safe_float(e.get("pnl_pct", e.get("pnl", 0.0)))

        pnl_total += pnl
        pnl_by_bot[bot] += pnl
        pnl_by_symbol[symbol] += pnl
        trades_by_bot[bot] += 1
        trades_by_symbol[symbol] += 1

        if result in ["WIN", "GAIN", "LUCRO"] or pnl > 0:
            wins += 1
            result_by_bot[bot]["wins"] += 1
        elif result in ["LOSS", "STOP", "PREJUIZO", "PREJUÍZO"] or pnl < 0:
            losses += 1
            result_by_bot[bot]["losses"] += 1
        else:
            breakevens += 1
            result_by_bot[bot]["breakevens"] += 1

    for e in blocked:
        reason = e.get("reason", e.get("motivo", "sem_motivo"))
        blocked_reasons[reason] += 1

    total_closed = len(closed)
    win_rate = round((wins / total_closed) * 100, 2) if total_closed else 0.0
    win_rate_sem_be = round((wins / (wins + losses)) * 100, 2) if (wins + losses) else 0.0

    return {
        "ok": True,
        "events_analyzed": len(events),
        "trades_closed": total_closed,
        "wins": wins,
        "losses": losses,
        "breakevens": breakevens,
        "win_rate": win_rate,
        "win_rate_sem_be": win_rate_sem_be,
        "pnl_total_pct": round(pnl_total, 4),
        "pnl_by_bot": {k: round(v, 4) for k, v in sorted(pnl_by_bot.items(), key=lambda x: x[1], reverse=True)},
        "pnl_by_symbol": {k: round(v, 4) for k, v in sorted(pnl_by_symbol.items(), key=lambda x: x[1], reverse=True)},
        "trades_by_bot": dict(trades_by_bot),
        "trades_by_symbol": dict(trades_by_symbol),
        "result_by_bot": {bot: dict(counter) for bot, counter in result_by_bot.items()},
        "blocked_trades": len(blocked),
        "blocked_reasons": dict(blocked_reasons),
    }


def format_history_text(limit=100):
    """
    Retorna um texto simples para rota /history.
    """
    summary = get_history_summary(limit=limit)

    if not summary.get("events_count"):
        return "📚 HISTORY CENTRAL QUANT\n\nNenhum evento registrado ainda."

    lines = []
    lines.append("📚 HISTORY CENTRAL QUANT")
    lines.append("")
    lines.append(f"Eventos analisados: {summary['events_count']}")
    lines.append("")
    lines.append("Por tipo:")
    for k, v in summary.get("by_type", {}).items():
        lines.append(f"- {k}: {v}")

    lines.append("")
    lines.append("Últimos eventos:")
    for e in summary.get("last_events", [])[-10:]:
        t = e.get("timestamp", "")
        event_type = e.get("type", "")
        bot = e.get("bot", "")
        symbol = e.get("symbol", "")
        pnl = e.get("pnl_pct", e.get("pnl", ""))
        reason = e.get("reason", e.get("motivo", ""))

        text = f"- {t} | {event_type}"
        if bot:
            text += f" | {bot}"
        if symbol:
            text += f" | {symbol}"
        if pnl != "":
            text += f" | PnL: {pnl}%"
        if reason:
            text += f" | Motivo: {reason}"
        lines.append(text)

    return "\n".join(lines)


def format_riskstats_text(limit=2000):
    """
    Retorna um texto simples para rota /riskstats.
    """
    s = get_riskstats(limit=limit)

    lines = []
    lines.append("📊 RISKSTATS - SUPER CENTRAL QUANT")
    lines.append("")
    lines.append(f"Eventos analisados: {s['events_analyzed']}")
    lines.append(f"Trades encerrados: {s['trades_closed']}")
    lines.append(f"Wins: {s['wins']}")
    lines.append(f"Losses: {s['losses']}")
    lines.append(f"Breakevens: {s['breakevens']}")
    lines.append(f"Win rate: {s['win_rate']}%")
    lines.append(f"Win rate sem BE: {s['win_rate_sem_be']}%")
    lines.append(f"PnL total: {s['pnl_total_pct']}%")
    lines.append("")

    lines.append("PnL por bot:")
    if s["pnl_by_bot"]:
        for bot, pnl in s["pnl_by_bot"].items():
            lines.append(f"- {bot}: {pnl}%")
    else:
        lines.append("- Sem dados ainda")

    lines.append("")
    lines.append("PnL por ativo:")
    if s["pnl_by_symbol"]:
        for symbol, pnl in list(s["pnl_by_symbol"].items())[:20]:
            lines.append(f"- {symbol}: {pnl}%")
    else:
        lines.append("- Sem dados ainda")

    lines.append("")
    lines.append(f"Trades bloqueados: {s['blocked_trades']}")
    lines.append("Motivos de bloqueio:")
    if s["blocked_reasons"]:
        for reason, count in s["blocked_reasons"].items():
            lines.append(f"- {reason}: {count}")
    else:
        lines.append("- Sem bloqueios registrados")

    return "\n".join(lines)
