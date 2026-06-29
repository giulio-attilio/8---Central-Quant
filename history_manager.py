# ==========================================================
# SUPER CENTRAL QUANT - HISTORY MANAGER
# Versao: 2026-06-28-HISTORY-V1
#
# Objetivo:
# - Criar um historico persistente simples e profissional para a Central Quant.
# - Salvar eventos em JSONL dentro da pasta data/.
# - Consolidar decision_log, timeline e snapshots ja existentes.
# - Expor relatorios: /history, /riskstats e /exporthistory.
#
# Importante:
# - Nao executa trades.
# - Nao altera estrategia dos robos.
# - Funciona mesmo se nenhum bot estiver carregado.
# - Usa arquivos locais do Render. Em plano free, dados podem ser perdidos em redeploy/rebuild.
#   Futuramente, o ideal e migrar para Postgres/Supabase/Neon.
# ==========================================================

import os
import json
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import Counter, defaultdict

TIMEZONE_BR = timezone(timedelta(hours=-3))
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

HISTORY_EVENTS_FILE = DATA_DIR / "history_events.jsonl"
HISTORY_EXPORT_FILE = DATA_DIR / "history_export.json"
DECISION_LOG_FILE = DATA_DIR / "decision_log.jsonl"
TIMELINE_LOG_FILE = DATA_DIR / "timeline.jsonl"
EXECUTION_STATS_FILE = DATA_DIR / "execution_stats.json"
SHADOW_POSITIONS_FILE = DATA_DIR / "shadow_positions.json"
STATUS_SNAPSHOTS_FILE = DATA_DIR / "status_snapshots.jsonl"

DEFAULT_LIMIT = int(os.environ.get("HISTORY_DEFAULT_LIMIT", "5000"))
MAX_EXPORT_LIMIT = int(os.environ.get("HISTORY_MAX_EXPORT_LIMIT", "20000"))


def agora_sp():
    return datetime.now(TIMEZONE_BR)


def data_hora_sp_str():
    return agora_sp().strftime("%d/%m/%Y %H:%M")


def iso_sp_str():
    return agora_sp().isoformat()


def _json_default(obj):
    try:
        if isinstance(obj, Path):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
    except Exception:
        pass
    return str(obj)


def _safe_float(value, default=None):
    try:
        if value is None:
            return default
        if isinstance(value, str):
            value = value.replace("%", "").replace("R", "").replace("+", "").replace(",", ".").strip()
            if value == "":
                return default
        return float(value)
    except Exception:
        return default


def _safe_upper(value):
    return str(value or "").strip().upper()


def _normalize_symbol(value):
    txt = _safe_upper(value)
    return txt.replace("/", "").replace(":USDT", "").replace("-", "")


def _append_jsonl(path, item):
    try:
        path.parent.mkdir(exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(item, ensure_ascii=False, default=_json_default) + "\n")
        return True
    except Exception as exc:
        print(f"ERRO HISTORY append_jsonl {path}: {exc}")
        return False


def _read_jsonl(path, limit=DEFAULT_LIMIT):
    if not Path(path).exists():
        return []
    rows = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
        if limit and len(rows) > int(limit):
            rows = rows[-int(limit):]
        return rows
    except Exception as exc:
        print(f"ERRO HISTORY read_jsonl {path}: {exc}")
        return []


def _read_json(path, default=None):
    try:
        p = Path(path)
        if not p.exists():
            return default
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path, payload):
    try:
        path = Path(path)
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")
        return True
    except Exception as exc:
        print(f"ERRO HISTORY write_json {path}: {exc}")
        return False


def log_event(event_type, data=None, source="central", trade_id=None):
    """
    Registro universal do History.

    Exemplos:
    log_event("trade_opened", {"bot":"TURTLE", "symbol":"ETHUSDT"})
    log_event("trade_closed", {"bot":"FALCON", "symbol":"BTCUSDT", "pnl_pct": 1.2, "result":"WIN"})
    log_event("trade_blocked", {"bot":"PREDATOR", "reason":"risco alto"})
    """
    data = data if isinstance(data, dict) else {"value": data}
    bot = data.get("bot") or data.get("robot") or data.get("strategy")
    symbol = data.get("symbol") or data.get("ativo") or data.get("pair")
    side = data.get("side") or data.get("direction") or data.get("lado")
    setup = data.get("setup") or data.get("setup_label")
    result = data.get("result") or data.get("resultado") or data.get("status")

    item = {
        "ts": data_hora_sp_str(),
        "ts_iso": iso_sp_str(),
        "epoch": time.time(),
        "event_type": _safe_upper(event_type or "EVENT"),
        "source": str(source or "central"),
        "trade_id": str(trade_id or data.get("trade_id") or data.get("id") or ""),
        "bot": _safe_upper(bot),
        "symbol": _normalize_symbol(symbol),
        "side": _safe_upper(side),
        "setup": str(setup or ""),
        "result": _safe_upper(result),
        "pnl_pct": _safe_float(data.get("pnl_pct") or data.get("pnl") or data.get("result_pct"), None),
        "pnl_r": _safe_float(data.get("pnl_r") or data.get("result_r"), None),
        "risk_pct": _safe_float(data.get("risk_pct") or data.get("risk") or data.get("risco"), None),
        "score": _safe_float(data.get("score"), None),
        "raw": data,
    }
    _append_jsonl(HISTORY_EVENTS_FILE, item)
    return item


def import_decision_log(limit=MAX_EXPORT_LIMIT):
    rows = _read_jsonl(DECISION_LOG_FILE, limit=limit)
    converted = []
    for r in rows:
        converted.append({
            "ts": r.get("ts"),
            "epoch": r.get("epoch"),
            "event_type": "TRADE_ALLOWED" if r.get("allowed") else "TRADE_BLOCKED",
            "source": "decision_log",
            "trade_id": r.get("trade_id"),
            "bot": _safe_upper(r.get("bot")),
            "symbol": _normalize_symbol(r.get("symbol")),
            "side": _safe_upper(r.get("side")),
            "setup": r.get("setup") or "",
            "result": "ALLOW" if r.get("allowed") else "DENY",
            "pnl_pct": None,
            "pnl_r": None,
            "risk_pct": _safe_float(r.get("risk_pct"), None),
            "score": _safe_float(r.get("score"), None),
            "raw": r,
        })
    return converted


def import_timeline(limit=MAX_EXPORT_LIMIT):
    rows = _read_jsonl(TIMELINE_LOG_FILE, limit=limit)
    converted = []
    for r in rows:
        converted.append({
            "ts": r.get("ts"),
            "epoch": r.get("epoch"),
            "event_type": _safe_upper(r.get("event") or r.get("state") or "TIMELINE"),
            "source": "timeline",
            "trade_id": r.get("trade_id"),
            "bot": _safe_upper(r.get("bot")),
            "symbol": _normalize_symbol(r.get("symbol")),
            "side": _safe_upper(r.get("side")),
            "setup": (r.get("details") or {}).get("setup", "") if isinstance(r.get("details"), dict) else "",
            "result": _safe_upper(r.get("state")),
            "pnl_pct": None,
            "pnl_r": None,
            "risk_pct": None,
            "score": None,
            "raw": r,
        })
    return converted


def all_history_events(limit=DEFAULT_LIMIT, include_imports=True):
    events = _read_jsonl(HISTORY_EVENTS_FILE, limit=limit)
    if include_imports:
        events = events + import_decision_log(limit=limit) + import_timeline(limit=limit)
    events = [e for e in events if isinstance(e, dict)]
    events.sort(key=lambda x: float(x.get("epoch") or 0))
    if limit and len(events) > int(limit):
        events = events[-int(limit):]
    return events


def _filter_events(events, bot=None, symbol=None, event_type=None):
    bot = _safe_upper(bot) if bot else None
    symbol = _normalize_symbol(symbol) if symbol else None
    event_type = _safe_upper(event_type) if event_type else None
    out = []
    for e in events:
        if bot and _safe_upper(e.get("bot")) != bot:
            continue
        if symbol and _normalize_symbol(e.get("symbol")) != symbol:
            continue
        if event_type and _safe_upper(e.get("event_type")) != event_type:
            continue
        out.append(e)
    return out


def build_history_payload(limit=1000, bot=None, symbol=None, event_type=None):
    events = all_history_events(limit=limit, include_imports=True)
    events = _filter_events(events, bot=bot, symbol=symbol, event_type=event_type)
    return {
        "ok": True,
        "generated_at": data_hora_sp_str(),
        "total_events": len(events),
        "filters": {"bot": bot, "symbol": symbol, "event_type": event_type},
        "events": events,
        "files": {
            "history_events": str(HISTORY_EVENTS_FILE),
            "decision_log": str(DECISION_LOG_FILE),
            "timeline": str(TIMELINE_LOG_FILE),
        },
    }


def build_riskstats_payload(limit=MAX_EXPORT_LIMIT):
    events = all_history_events(limit=limit, include_imports=True)
    by_bot = defaultdict(lambda: {"events": 0, "allow": 0, "deny": 0, "closed": 0, "wins": 0, "loss": 0, "be": 0, "pnl_pct": 0.0, "pnl_r": 0.0})
    by_symbol = defaultdict(lambda: {"events": 0, "allow": 0, "deny": 0, "closed": 0, "wins": 0, "loss": 0, "be": 0, "pnl_pct": 0.0, "pnl_r": 0.0})
    by_setup = defaultdict(lambda: {"events": 0, "allow": 0, "deny": 0, "closed": 0, "wins": 0, "loss": 0, "be": 0, "pnl_pct": 0.0, "pnl_r": 0.0})
    event_counts = Counter()
    block_reasons = Counter()

    total_pnl_pct = 0.0
    total_pnl_r = 0.0
    closed = wins = loss = be = allow = deny = 0

    def touch(bucket, key, e):
        if not key:
            key = "N/A"
        st = bucket[key]
        st["events"] += 1
        et = _safe_upper(e.get("event_type"))
        res = _safe_upper(e.get("result"))
        if et in {"TRADE_ALLOWED", "RISK_ALLOW"} or res == "ALLOW":
            st["allow"] += 1
        if et in {"TRADE_BLOCKED", "RISK_DENY"} or res == "DENY":
            st["deny"] += 1
        if et in {"TRADE_CLOSED", "CLOSED", "STOP_HIT", "TP_HIT"} or res in {"WIN", "LOSS", "BE", "BREAKEVEN"}:
            st["closed"] += 1
            if res == "WIN":
                st["wins"] += 1
            elif res == "LOSS":
                st["loss"] += 1
            elif res in {"BE", "BREAKEVEN"}:
                st["be"] += 1
        if e.get("pnl_pct") is not None:
            st["pnl_pct"] += _safe_float(e.get("pnl_pct"), 0.0) or 0.0
        if e.get("pnl_r") is not None:
            st["pnl_r"] += _safe_float(e.get("pnl_r"), 0.0) or 0.0

    for e in events:
        et = _safe_upper(e.get("event_type"))
        res = _safe_upper(e.get("result"))
        event_counts[et or "EVENT"] += 1
        if et in {"TRADE_ALLOWED", "RISK_ALLOW"} or res == "ALLOW":
            allow += 1
        if et in {"TRADE_BLOCKED", "RISK_DENY"} or res == "DENY":
            deny += 1
            raw = e.get("raw") or {}
            reasons = raw.get("reasons") or raw.get("reason") or raw.get("motivo") or []
            if isinstance(reasons, str):
                reasons = [reasons]
            if isinstance(reasons, list):
                for reason in reasons[:5]:
                    block_reasons[str(reason)[:120]] += 1
        if et in {"TRADE_CLOSED", "CLOSED", "STOP_HIT", "TP_HIT"} or res in {"WIN", "LOSS", "BE", "BREAKEVEN"}:
            closed += 1
            if res == "WIN":
                wins += 1
            elif res == "LOSS":
                loss += 1
            elif res in {"BE", "BREAKEVEN"}:
                be += 1
        if e.get("pnl_pct") is not None:
            total_pnl_pct += _safe_float(e.get("pnl_pct"), 0.0) or 0.0
        if e.get("pnl_r") is not None:
            total_pnl_r += _safe_float(e.get("pnl_r"), 0.0) or 0.0

        touch(by_bot, e.get("bot") or "N/A", e)
        touch(by_symbol, e.get("symbol") or "N/A", e)
        touch(by_setup, e.get("setup") or "N/A", e)

    win_rate = round((wins / max(1, wins + loss)) * 100, 2) if (wins + loss) else None
    win_rate_com_be = round((wins / max(1, closed)) * 100, 2) if closed else None

    return {
        "ok": True,
        "generated_at": data_hora_sp_str(),
        "total_events": len(events),
        "allow": allow,
        "deny": deny,
        "closed": closed,
        "wins": wins,
        "loss": loss,
        "breakeven": be,
        "win_rate_sem_be": win_rate,
        "win_rate_com_be": win_rate_com_be,
        "pnl_pct_total": round(total_pnl_pct, 4),
        "pnl_r_total": round(total_pnl_r, 4),
        "event_counts": dict(event_counts.most_common()),
        "block_reasons": dict(block_reasons.most_common(20)),
        "by_bot": dict(by_bot),
        "by_symbol": dict(by_symbol),
        "by_setup": dict(by_setup),
    }


def _fmt_pct(value):
    if value is None:
        return "N/A"
    try:
        sign = "+" if float(value) > 0 else ""
        return f"{sign}{float(value):.2f}%".replace(".", ",")
    except Exception:
        return "N/A"


def build_history_report(limit=80, bot=None, symbol=None, event_type=None):
    payload = build_history_payload(limit=limit, bot=bot, symbol=symbol, event_type=event_type)
    events = payload.get("events", [])
    stats = build_riskstats_payload(limit=MAX_EXPORT_LIMIT)
    lines = [
        "📚 SUPER HISTORY — CENTRAL QUANT",
        f"Data/hora: {data_hora_sp_str()}",
        "",
        f"Eventos exibidos: {len(events)}",
        f"Eventos totais analisados: {stats.get('total_events')}",
        f"ALLOW: {stats.get('allow')} | DENY: {stats.get('deny')}",
        f"Trades encerrados: {stats.get('closed')}",
        f"Wins: {stats.get('wins')} | Loss: {stats.get('loss')} | BE: {stats.get('breakeven')}",
        f"Win rate sem BE: {_fmt_pct(stats.get('win_rate_sem_be'))}",
        f"PnL % total registrado: {_fmt_pct(stats.get('pnl_pct_total'))}",
        "",
        "Por robô:",
    ]
    by_bot = stats.get("by_bot") or {}
    if not by_bot:
        lines.append("- Ainda sem eventos por robô.")
    else:
        for bot_key, st in sorted(by_bot.items()):
            lines.append(
                f"- {bot_key}: eventos={st.get('events')} | allow={st.get('allow')} | deny={st.get('deny')} | "
                f"fechados={st.get('closed')} | W/L/BE={st.get('wins')}/{st.get('loss')}/{st.get('be')} | "
                f"PnL={_fmt_pct(st.get('pnl_pct'))}"
            )
    lines += ["", "Últimos eventos:"]
    if not events:
        lines.append("- Nenhum evento ainda.")
    else:
        for e in events[-30:]:
            lines.append(
                f"- {e.get('ts')} | {e.get('source')} | {e.get('event_type')} | "
                f"{e.get('bot') or 'N/A'} {e.get('symbol') or ''} {e.get('side') or ''} | "
                f"result={e.get('result') or 'N/A'} | pnl={_fmt_pct(e.get('pnl_pct'))}"
            )
    lines += [
        "",
        "Rotas disponíveis:",
        "/history — resumo do histórico",
        "/riskstats — estatísticas de risco/performance",
        "/exporthistory — exportação em JSON para colar no ChatGPT",
    ]
    return "\n".join(lines)


def build_riskstats_report(limit=MAX_EXPORT_LIMIT):
    stats = build_riskstats_payload(limit=limit)
    lines = [
        "📊 RISKSTATS — SUPER CENTRAL QUANT",
        f"Data/hora: {data_hora_sp_str()}",
        "",
        f"Eventos analisados: {stats.get('total_events')}",
        f"ALLOW: {stats.get('allow')} | DENY: {stats.get('deny')}",
        f"Trades encerrados: {stats.get('closed')}",
        f"Wins: {stats.get('wins')} | Loss: {stats.get('loss')} | Breakeven: {stats.get('breakeven')}",
        f"Win rate sem BE: {_fmt_pct(stats.get('win_rate_sem_be'))}",
        f"Win rate com BE: {_fmt_pct(stats.get('win_rate_com_be'))}",
        f"PnL % total: {_fmt_pct(stats.get('pnl_pct_total'))}",
        f"PnL R total: {stats.get('pnl_r_total')}",
        "",
        "Eventos por tipo:",
    ]
    for k, v in (stats.get("event_counts") or {}).items():
        lines.append(f"- {k}: {v}")
    lines += ["", "Bloqueios mais comuns:"]
    reasons = stats.get("block_reasons") or {}
    if not reasons:
        lines.append("- Ainda sem motivos de bloqueio registrados.")
    else:
        for k, v in reasons.items():
            lines.append(f"- {v}x | {k}")
    lines += ["", "Por robô:"]
    for bot_key, st in sorted((stats.get("by_bot") or {}).items()):
        lines.append(f"- {bot_key}: eventos={st.get('events')} | allow={st.get('allow')} | deny={st.get('deny')} | fechados={st.get('closed')} | W/L/BE={st.get('wins')}/{st.get('loss')}/{st.get('be')} | PnL={_fmt_pct(st.get('pnl_pct'))}")
    return "\n".join(lines)


def build_export_payload(limit=MAX_EXPORT_LIMIT):
    payload = {
        "ok": True,
        "generated_at": data_hora_sp_str(),
        "history": build_history_payload(limit=limit),
        "riskstats": build_riskstats_payload(limit=limit),
        "shadow_positions": _read_json(SHADOW_POSITIONS_FILE, {}),
        "execution_stats": _read_json(EXECUTION_STATS_FILE, {}),
    }
    _write_json(HISTORY_EXPORT_FILE, payload)
    return payload


def build_export_report(limit=MAX_EXPORT_LIMIT):
    return json.dumps(build_export_payload(limit=limit), ensure_ascii=False, indent=2, default=_json_default)


def wrap_central_functions(globals_dict):
    """
    Conecta o History nas funcoes ja existentes da Central, sem quebrar o main.py.
    Deve ser chamado no final do main.py, depois que append_timeline_event e
    append_decision_log ja existem.
    """
    try:
        original_timeline = globals_dict.get("append_timeline_event")
        if callable(original_timeline) and not getattr(original_timeline, "_history_wrapped", False):
            def append_timeline_event_wrapped(event_type, bot=None, symbol=None, side=None, trade_id=None, state=None, details=None):
                result = original_timeline(event_type, bot=bot, symbol=symbol, side=side, trade_id=trade_id, state=state, details=details)
                try:
                    log_event(event_type, {
                        "bot": bot,
                        "symbol": symbol,
                        "side": side,
                        "trade_id": trade_id,
                        "status": state,
                        "details": details,
                    }, source="timeline_hook", trade_id=trade_id)
                except Exception as exc:
                    print("ERRO HISTORY timeline hook:", exc)
                return result
            append_timeline_event_wrapped._history_wrapped = True
            globals_dict["append_timeline_event"] = append_timeline_event_wrapped

        original_decision = globals_dict.get("append_decision_log")
        if callable(original_decision) and not getattr(original_decision, "_history_wrapped", False):
            def append_decision_log_wrapped(payload, decision_result):
                result = original_decision(payload, decision_result)
                try:
                    data = dict(result or {})
                    log_event("TRADE_ALLOWED" if data.get("allowed") else "TRADE_BLOCKED", data, source="decision_hook", trade_id=data.get("trade_id"))
                except Exception as exc:
                    print("ERRO HISTORY decision hook:", exc)
                return result
            append_decision_log_wrapped._history_wrapped = True
            globals_dict["append_decision_log"] = append_decision_log_wrapped

        # Sobrescreve o relatorio antigo da Central. A rota /history existente chama esse nome em tempo de execucao.
        globals_dict["build_history_report"] = build_history_report
        return True
    except Exception as exc:
        print("ERRO HISTORY wrap_central_functions:", exc)
        return False
