# ==============================================================================
# CENTRAL QUANT - LEARNING ENGINE
# Versao: 2026-07-02-LEARNING-ENGINE-V1-OBSERVE
#
# Objetivo:
# - Ler Journal + Lifecycle + Context.
# - Medir maturidade estatistica da base.
# - Gerar observacoes preliminares sem alterar operacao.
# - Preparar recomendações futuras para Policy Engine.
#
# Segurança:
# - Esta V1 roda apenas em modo OBSERVE.
# - Não altera score, risco, políticas, bots nem corretora.
# ============================================================================

import json
import os
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import Counter, defaultdict

TIMEZONE_BR = timezone(timedelta(hours=-3))
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data"))).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)

LEARNING_STATE_FILE = DATA_DIR / "learning_state.json"
LEARNING_AUDIT_FILE = DATA_DIR / "learning_audit.jsonl"
LEARNING_EXPORT_FILE = DATA_DIR / "learning_export.json"
LEARNING_MAX_READ = int(os.environ.get("LEARNING_MAX_READ", "10000"))

VERSION = "2026-07-02-LEARNING-ENGINE-V1-4-BRIEF"
MODE = os.environ.get("LEARNING_ENGINE_MODE", "OBSERVE").strip().upper()

MIN_CYCLES_OBSERVATION = int(os.environ.get("LEARNING_MIN_CYCLES_OBSERVATION", "20"))
MIN_CYCLES_HINTS = int(os.environ.get("LEARNING_MIN_CYCLES_HINTS", "50"))
MIN_CLOSED_MODERATE = int(os.environ.get("LEARNING_MIN_CLOSED_MODERATE", "200"))
MIN_CLOSED_HIGH = int(os.environ.get("LEARNING_MIN_CLOSED_HIGH", "500"))

CORE_FIELDS = [
    "trade_id", "bot", "setup", "symbol", "side", "status", "events",
    "score", "quality", "mfe_pct", "mae_pct", "entry", "started_at",
]
CONTEXT_FIELDS = [
    "hour", "weekday", "session_br", "market_regime", "btc_alignment",
    "volatility", "volume_status", "adx", "atr", "rsi", "paper_positions",
    "memory_usage_pct", "execution_mode", "score_bucket", "risk_bucket",
]


def agora_sp():
    return datetime.now(TIMEZONE_BR)


def data_hora_sp_str():
    return agora_sp().strftime("%d/%m/%Y %H:%M")


def _json_default(value):
    try:
        return str(value)
    except Exception:
        return None


def _safe_float(value, default=None):
    try:
        if value is None:
            return default
        if isinstance(value, str):
            value = value.replace("%", "").replace(",", ".").strip()
        return float(value)
    except Exception:
        return default


def _safe_int(value, default=0):
    try:
        if value is None:
            return default
        return int(float(value))
    except Exception:
        return default


def _round(value, ndigits=2, default=0.0):
    try:
        if value is None:
            return default
        return round(float(value), ndigits)
    except Exception:
        return default


def _write_json(path: Path, payload):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, default=_json_default)
        return True
    except Exception:
        return False


def _read_json(path: Path, default):
    try:
        if not path.exists():
            return default
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _append_jsonl(path: Path, item: dict):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(item, ensure_ascii=False, default=_json_default) + "\n")
        return True
    except Exception:
        return False


def _load_journal_data(limit=None):
    trades = []
    events = []
    lifecycles = []
    errors = []

    try:
        import journal_manager
        if hasattr(journal_manager, "load_journal_trades"):
            trades = journal_manager.load_journal_trades(limit=limit or LEARNING_MAX_READ) or []
        if hasattr(journal_manager, "load_lifecycle_events"):
            events = journal_manager.load_lifecycle_events(limit=limit or LEARNING_MAX_READ) or []
        if hasattr(journal_manager, "build_trade_lifecycles"):
            lifecycles = journal_manager.build_trade_lifecycles(events) or []
    except Exception as exc:
        errors.append(f"journal_manager: {exc}")

    if isinstance(lifecycles, dict):
        lifecycles = list(lifecycles.values())
    if not isinstance(lifecycles, list):
        lifecycles = []
    if not isinstance(events, list):
        events = []
    if not isinstance(trades, list):
        trades = []

    return {"trades": trades, "events": events, "lifecycles": lifecycles, "errors": errors}


def _non_empty(value):
    return value is not None and value != "" and value != [] and value != {}


def _coverage(rows, fields):
    total = len(rows)
    result = {}
    if total <= 0:
        for field in fields:
            result[field] = {"present": 0, "total": 0, "pct": 0.0}
        return result
    for field in fields:
        present = 0
        for row in rows:
            if isinstance(row, dict) and _non_empty(row.get(field)):
                present += 1
        result[field] = {"present": present, "total": total, "pct": round((present / total) * 100, 2)}
    return result




def _deep_get(mapping, path, default=None):
    """Busca segura em dicts aninhados."""
    cur = mapping
    for key in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
    return cur if cur is not None else default


def _merge_dicts(*items):
    merged = {}
    for item in items:
        if isinstance(item, dict):
            for k, v in item.items():
                if _non_empty(v):
                    merged[k] = v
    return merged


def _extract_context_from_row(row):
    """
    Extrai contexto de eventos/ciclos mesmo quando ele veio aninhado.

    Possíveis origens observadas:
    - row["context"]
    - row["raw"]["context"]
    - row["raw"]["raw"]["context"]
    - row["timeline"][-1]["context"]
    - row["timeline"][-1]["raw"]["context"]
    - row["timeline"][-1]["raw"]["raw"]["context"]
    """
    if not isinstance(row, dict):
        return {}

    contexts = []
    contexts.append(row.get("context"))
    contexts.append(_deep_get(row, ["raw", "context"]))
    contexts.append(_deep_get(row, ["raw", "raw", "context"]))

    timeline = row.get("timeline")
    if isinstance(timeline, list) and timeline:
        for ev in timeline:
            if not isinstance(ev, dict):
                continue
            contexts.append(ev.get("context"))
            contexts.append(_deep_get(ev, ["raw", "context"]))
            contexts.append(_deep_get(ev, ["raw", "raw", "context"]))

    ctx = _merge_dicts(*contexts)

    # Fallback: alguns campos de contexto podem estar no próprio evento ou dentro de execution_decision.
    for field in CONTEXT_FIELDS:
        if not _non_empty(ctx.get(field)) and _non_empty(row.get(field)):
            ctx[field] = row.get(field)

    execution_mode = (
        _deep_get(row, ["raw", "execution_decision", "mode"])
        or _deep_get(row, ["raw", "raw", "execution_decision", "mode"])
        or _deep_get(row, ["execution_decision", "mode"])
    )
    if _non_empty(execution_mode) and not _non_empty(ctx.get("execution_mode")):
        ctx["execution_mode"] = execution_mode

    paper_positions = (
        _deep_get(row, ["raw", "execution_decision", "exposure", "paper_total"])
        or _deep_get(row, ["raw", "raw", "execution_decision", "exposure", "paper_total"])
        or _deep_get(row, ["execution_decision", "exposure", "paper_total"])
    )
    if _non_empty(paper_positions) and not _non_empty(ctx.get("paper_positions")):
        ctx["paper_positions"] = paper_positions

    memory_usage_pct = (
        _deep_get(row, ["raw", "execution_decision", "memory", "usage_pct"])
        or _deep_get(row, ["raw", "raw", "execution_decision", "memory", "usage_pct"])
        or _deep_get(row, ["execution_decision", "memory", "usage_pct"])
    )
    if _non_empty(memory_usage_pct) and not _non_empty(ctx.get("memory_usage_pct")):
        ctx["memory_usage_pct"] = memory_usage_pct

    return ctx


def _flatten_context(row):
    """Copia campos de contexto para o topo para cobertura, agrupamentos e relatórios."""
    if not isinstance(row, dict):
        return row
    item = dict(row)
    ctx = _extract_context_from_row(item)
    if ctx:
        existing = item.get("context") if isinstance(item.get("context"), dict) else {}
        item["context"] = _merge_dicts(existing, ctx)
        for field in CONTEXT_FIELDS:
            if not _non_empty(item.get(field)) and _non_empty(ctx.get(field)):
                item[field] = ctx.get(field)

    # Fallback temporal a partir de ts/started_at, para não deixar hour/weekday zerado.
    dt_text = item.get("ts") or item.get("started_at") or item.get("updated_at")
    try:
        dt = datetime.strptime(str(dt_text), "%d/%m/%Y %H:%M") if dt_text else None
    except Exception:
        dt = None
    if dt is not None:
        if not _non_empty(item.get("hour")):
            item["hour"] = dt.hour
        if not _non_empty(item.get("weekday")):
            item["weekday"] = dt.strftime("%A")
        if not _non_empty(item.get("session_br")):
            h = dt.hour
            if 0 <= h < 6:
                item["session_br"] = "MADRUGADA"
            elif 6 <= h < 12:
                item["session_br"] = "MANHA"
            elif 12 <= h < 18:
                item["session_br"] = "TARDE"
            else:
                item["session_br"] = "NOITE"
    return item


def _flatten_rows(rows):
    return [_flatten_context(x) for x in (rows or []) if isinstance(x, dict)]


def _avg(values):
    nums = [_safe_float(v, None) for v in values]
    nums = [v for v in nums if v is not None]
    if not nums:
        return 0.0
    return round(sum(nums) / len(nums), 4)


def _pnl(row):
    if not isinstance(row, dict):
        return None
    for key in ["result_pct", "pnl_pct", "result_r", "pnl_r"]:
        val = _safe_float(row.get(key), None)
        if val is not None:
            return val
    return None


def _status(row):
    return str((row or {}).get("status") or "").upper().strip()


def _is_closed(row):
    status = _status(row)
    if status in {"CLOSED", "FECHADO", "ENCERRADO"}:
        return True
    events = row.get("events") if isinstance(row, dict) else []
    return isinstance(events, list) and "TRADE_CLOSED" in [str(e).upper() for e in events]


def _readiness_level(cycles_count, closed_count):
    if closed_count >= MIN_CLOSED_HIGH:
        return {"level": "ALTA_CONFIANCA", "confidence": 80, "action": "Pode gerar recomendações robustas por bot/setup/ativo/horário."}
    if closed_count >= MIN_CLOSED_MODERATE:
        return {"level": "CONFIANCA_MODERADA", "confidence": 55, "action": "Pode gerar recomendações com cautela."}
    if cycles_count >= MIN_CYCLES_HINTS:
        return {"level": "INDICIOS", "confidence": 25, "action": "Pode apontar tendências preliminares sem alterar políticas."}
    if cycles_count >= MIN_CYCLES_OBSERVATION:
        return {"level": "OBSERVACAO", "confidence": 10, "action": "Apenas estatísticas descritivas."}
    return {"level": "AMOSTRA_INSUFICIENTE", "confidence": 0, "action": "Aguardar mais ciclos/eventos."}


def _group_summary(rows, key, limit=8):
    buckets = defaultdict(list)
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = row.get(key)
        if not _non_empty(name):
            name = "UNKNOWN"
        buckets[str(name).upper()].append(row)

    items = []
    for name, group in buckets.items():
        count = len(group)
        closed = [r for r in group if _is_closed(r)]
        open_ = [r for r in group if _status(r) == "OPEN"]
        mfe = _avg([r.get("mfe_pct") for r in group])
        mae = _avg([r.get("mae_pct") for r in group])
        pnls = [_pnl(r) for r in closed]
        pnls = [p for p in pnls if p is not None]
        wins = sum(1 for p in pnls if p > 0)
        losses = sum(1 for p in pnls if p < 0)
        wr = round((wins / len(pnls)) * 100, 2) if pnls else 0.0
        expectancy = round(sum(pnls) / len(pnls), 4) if pnls else 0.0
        items.append({
            "name": name,
            "cycles": count,
            "open": len(open_),
            "closed": len(closed),
            "wins": wins,
            "losses": losses,
            "win_rate_pct": wr,
            "expectancy": expectancy,
            "mfe_avg_pct": mfe,
            "mae_avg_pct": mae,
        })
    items.sort(key=lambda x: (x.get("cycles", 0), x.get("expectancy", 0)), reverse=True)
    return items[:limit]


def _sample_label(cycles, closed):
    if closed >= MIN_CLOSED_HIGH:
        return "ALTA_CONFIANCA"
    if closed >= MIN_CLOSED_MODERATE:
        return "CONFIANCA_MODERADA"
    if cycles >= MIN_CYCLES_HINTS:
        return "INDICIOS"
    if cycles >= MIN_CYCLES_OBSERVATION:
        return "OBSERVACAO"
    return "AMOSTRA_INSUFICIENTE"


def _build_observations(payload):
    """Gera observações conservadoras sem alterar Policy Engine."""
    groups = payload.get("groups") or {}
    summary = payload.get("summary") or {}
    observations = []

    observations.append({
        "type": "readiness",
        "level": payload.get("readiness", {}).get("level"),
        "confidence": payload.get("readiness", {}).get("confidence", 0),
        "message": "Learning em modo OBSERVE. Nenhuma política operacional foi alterada.",
    })

    for group_name, items in groups.items():
        for item in (items or [])[:8]:
            cycles = _safe_int(item.get("cycles"), 0)
            closed = _safe_int(item.get("closed"), 0)
            expectancy = _safe_float(item.get("expectancy"), 0.0)
            wr = _safe_float(item.get("win_rate_pct"), 0.0)
            sample = _sample_label(cycles, closed)
            if cycles <= 0:
                continue
            observations.append({
                "type": "group",
                "group": group_name,
                "name": item.get("name"),
                "cycles": cycles,
                "closed": closed,
                "sample_status": sample,
                "expectancy": expectancy,
                "win_rate_pct": wr,
                "message": (
                    f"{group_name.replace('by_', '').upper()} {item.get('name')}: "
                    f"{cycles} ciclos, {closed} fechados, expectancy {expectancy}. "
                    f"Status: {sample}."
                ),
            })

    # Diagnóstico de qualidade de dados para orientar próxima instrumentação.
    coverage = payload.get("coverage") or {}
    ctx = coverage.get("context") or {}
    weak_fields = []
    for field in ["score_bucket", "risk_bucket", "execution_mode", "paper_positions", "memory_usage_pct", "adx", "atr", "rsi", "btc_alignment", "volatility"]:
        pct = _safe_float((ctx.get(field) or {}).get("pct"), 0.0)
        if pct < 70:
            weak_fields.append({"field": field, "pct": pct})
    if weak_fields:
        observations.append({
            "type": "data_quality",
            "level": "ATENCAO",
            "fields": weak_fields,
            "message": "Alguns campos de contexto ainda têm baixa cobertura; recomendações devem permanecer bloqueadas.",
        })

    return observations[:40]


def _build_policy_suggestions(payload, observations):
    """Nesta V1.2, apenas prepara sugestões bloqueadas por amostra/confiança."""
    readiness = payload.get("readiness") or {}
    confidence = _safe_int(readiness.get("confidence"), 0)
    suggestions = []

    if confidence < 25:
        suggestions.append({
            "bot": "GLOBAL",
            "action": "NO_CHANGE",
            "status": "BLOCKED_SAMPLE",
            "confidence": confidence,
            "reason": "Amostra insuficiente para alterar Policy Engine.",
            "apply": False,
        })
        return suggestions

    # Guardrail: mesmo em INDICIOS, não aplica nada automaticamente.
    for obs in observations:
        if obs.get("type") == "group" and obs.get("closed", 0) >= 20:
            suggestions.append({
                "bot": obs.get("name"),
                "action": "OBSERVE_ONLY",
                "status": "CANDIDATE",
                "confidence": min(confidence, 40),
                "reason": obs.get("message"),
                "apply": False,
            })
    return suggestions[:10]


def build_learning_payload(limit=None):
    data = _load_journal_data(limit=limit)
    lifecycles = _flatten_rows(data.get("lifecycles") or [])
    events = _flatten_rows(data.get("events") or [])
    trades = _flatten_rows(data.get("trades") or [])

    closed_lifecycles = [x for x in lifecycles if _is_closed(x)]
    open_lifecycles = [x for x in lifecycles if _status(x) == "OPEN"]
    blocked_lifecycles = [x for x in lifecycles if _status(x) == "BLOCKED"]

    readiness = _readiness_level(len(lifecycles), len(closed_lifecycles) or len(trades))
    core_coverage = _coverage(lifecycles, CORE_FIELDS)
    context_coverage = _coverage(events, CONTEXT_FIELDS)

    event_counter = Counter()
    for event in events:
        if isinstance(event, dict):
            event_counter[str(event.get("event") or "UNKNOWN").upper()] += 1

    by_bot = _group_summary(lifecycles, "bot")
    by_setup = _group_summary(lifecycles, "setup")
    by_symbol = _group_summary(lifecycles, "symbol")
    by_hour = _group_summary(events, "hour")
    by_session = _group_summary(events, "session_br")
    by_score_bucket = _group_summary(events, "score_bucket")
    by_risk_bucket = _group_summary(events, "risk_bucket")

    payload = {
        "ok": True,
        "module": "learning_engine",
        "version": VERSION,
        "mode": MODE,
        "generated_at": data_hora_sp_str(),
        "data_dir": str(DATA_DIR),
        "state_file": str(LEARNING_STATE_FILE),
        "audit_file": str(LEARNING_AUDIT_FILE),
        "export_file": str(LEARNING_EXPORT_FILE),
        "summary": {
            "cycles": len(lifecycles),
            "events": len(events),
            "journal_trades": len(trades),
            "open": len(open_lifecycles),
            "closed": len(closed_lifecycles),
            "blocked": len(blocked_lifecycles),
        },
        "readiness": readiness,
        "coverage": {
            "core": core_coverage,
            "context": context_coverage,
        },
        "events_by_type": dict(event_counter.most_common(20)),
        "groups": {
            "by_bot": by_bot,
            "by_setup": by_setup,
            "by_symbol": by_symbol,
            "by_hour": by_hour,
            "by_session": by_session,
            "by_score_bucket": by_score_bucket,
            "by_risk_bucket": by_risk_bucket,
        },
        "errors": data.get("errors") or [],
        "notes": [
            "V1 em modo OBSERVE: não altera políticas, scores, risco, bots ou corretora.",
            "Com poucos ciclos, usar apenas como telemetria e diagnóstico de maturidade.",
        ],
    }
    observations = _build_observations(payload)
    policy_suggestions = _build_policy_suggestions(payload, observations)
    payload["observations"] = observations
    payload["policy_suggestions"] = policy_suggestions

    _write_json(LEARNING_EXPORT_FILE, payload)
    _write_json(LEARNING_STATE_FILE, {
        "version": VERSION,
        "mode": MODE,
        "updated_at": data_hora_sp_str(),
        "readiness": readiness,
        "summary": payload["summary"],
        "recommendations": observations,
        "policy_suggestions": policy_suggestions,
        "can_influence_policy": False,
    })
    _append_jsonl(LEARNING_AUDIT_FILE, {
        "ts": data_hora_sp_str(),
        "event": "LEARNING_ANALYSIS_BUILT",
        "summary": payload["summary"],
        "readiness": readiness,
    })
    return payload


def _fmt_pct(value):
    try:
        return f"{float(value):.1f}%"
    except Exception:
        return "0.0%"


def build_learning_report(limit=None):
    payload = build_learning_payload(limit=limit)
    s = payload.get("summary") or {}
    r = payload.get("readiness") or {}
    events_by_type = payload.get("events_by_type") or {}
    groups = payload.get("groups") or {}

    lines = [
        "🧠 LEARNING ENGINE — CENTRAL QUANT",
        f"Data/hora: {payload.get('generated_at')}",
        f"Modo: {payload.get('mode')}",
        "",
        "Status:",
        f"Nível: {r.get('level')}",
        f"Confiança: {r.get('confidence')}/100",
        f"Ação: {r.get('action')}",
        "",
        "Base analisada:",
        f"Ciclos: {s.get('cycles', 0)}",
        f"Eventos: {s.get('events', 0)}",
        f"Trades fechados no Journal: {s.get('journal_trades', 0)}",
        f"Abertos: {s.get('open', 0)} | Fechados: {s.get('closed', 0)} | Bloqueados: {s.get('blocked', 0)}",
        "",
        "Eventos por tipo:",
    ]
    if events_by_type:
        for name, count in list(events_by_type.items())[:8]:
            lines.append(f"{name}: {count}")
    else:
        lines.append("Nenhum evento lifecycle encontrado.")

    lines += ["", "Principais bots:"]
    for item in (groups.get("by_bot") or [])[:5]:
        lines.append(
            f"{item.get('name')}: ciclos {item.get('cycles')} | open {item.get('open')} | "
            f"closed {item.get('closed')} | MFE {_fmt_pct(item.get('mfe_avg_pct'))} | MAE {_fmt_pct(item.get('mae_avg_pct'))}"
        )
    if not (groups.get("by_bot") or []):
        lines.append("Sem dados por bot ainda.")

    lines += ["", "Principais setups:"]
    for item in (groups.get("by_setup") or [])[:5]:
        lines.append(
            f"{item.get('name')}: ciclos {item.get('cycles')} | open {item.get('open')} | "
            f"closed {item.get('closed')} | MFE {_fmt_pct(item.get('mfe_avg_pct'))} | MAE {_fmt_pct(item.get('mae_avg_pct'))}"
        )
    if not (groups.get("by_setup") or []):
        lines.append("Sem dados por setup ainda.")

    observations = payload.get("observations") or []
    lines += ["", "Observações automáticas:"]
    shown = 0
    for obs in observations:
        if obs.get("type") in {"group", "data_quality"}:
            lines.append(f"- {obs.get('message')}")
            shown += 1
        if shown >= 6:
            break
    if shown == 0:
        lines.append("Nenhuma observação relevante ainda.")

    lines += [
        "",
        "Interpretação:",
        "Esta V1 apenas observa. Nenhuma política operacional foi alterada.",
    ]
    if r.get("level") == "AMOSTRA_INSUFICIENTE":
        lines.append("Ainda não há amostra suficiente para recomendações; a Central está acumulando telemetria.")
    elif r.get("level") == "OBSERVACAO":
        lines.append("Já é possível acompanhar estatísticas descritivas, mas sem recomendação operacional.")
    elif r.get("level") == "INDICIOS":
        lines.append("Já é possível apontar indícios preliminares, ainda sem alterar Policy Engine.")
    else:
        lines.append("A base começa a permitir recomendações com controle de confiança.")
    return "\n".join(lines), payload




def _fmt_signed(value, ndigits=4):
    try:
        v = float(value)
        sign = "+" if v > 0 else ""
        return f"{sign}{v:.{ndigits}f}"
    except Exception:
        return "0"


def _top_items(items, max_items=3, min_cycles=1):
    rows = []
    for item in items or []:
        try:
            cycles = int(item.get("cycles") or 0)
        except Exception:
            cycles = 0
        if cycles >= min_cycles:
            rows.append(item)
    return rows[:max_items]


def build_learning_brief(limit=None):
    """Resumo executivo curto para uso diário/consultoria.

    Mantém o Learning em modo OBSERVE: não altera Policy, scores, risco,
    bots nem corretora. O objetivo é reduzir JSON grande para um briefing.
    """
    payload = build_learning_payload(limit=limit or LEARNING_MAX_READ)
    s = payload.get("summary") or {}
    r = payload.get("readiness") or {}
    groups = payload.get("groups") or {}
    observations = payload.get("observations") or []
    policy_suggestions = payload.get("policy_suggestions") or []
    cov = payload.get("coverage") or {}
    ctx = cov.get("context") or {}
    core = cov.get("core") or {}

    lines = [
        "🧠 LEARNING BRIEF — CENTRAL QUANT",
        f"Data/hora: {payload.get('generated_at')}",
        f"Modo: {payload.get('mode')} | Nível: {r.get('level')} | Confiança: {r.get('confidence')}/100",
        "",
        "Base:",
        f"Ciclos: {s.get('cycles', 0)} | Eventos: {s.get('events', 0)} | Fechados: {s.get('closed', 0)} | Abertos: {s.get('open', 0)} | Bloqueados: {s.get('blocked', 0)}",
        "",
        "Leitura rápida:",
    ]

    if r.get("level") == "AMOSTRA_INSUFICIENTE":
        lines.append("- Base ainda insuficiente para recomendação operacional.")
    elif r.get("level") == "OBSERVACAO":
        lines.append("- Base já permite estatística descritiva, sem recomendação operacional.")
    elif r.get("level") == "INDICIOS":
        lines.append("- Já existem indícios preliminares, mas Policy continua bloqueado.")
    else:
        lines.append("- Base evoluindo para recomendações, ainda com guardrails ativos.")

    if policy_suggestions:
        applied = [x for x in policy_suggestions if x.get("apply")]
        if applied:
            lines.append("- ALERTA: há sugestão marcada para aplicação. Revisar Policy antes de qualquer uso.")
        else:
            lines.append("- Nenhuma alteração operacional autorizada pelo Learning.")
    else:
        lines.append("- Nenhuma sugestão de Policy ativa.")

    lines += ["", "Indícios por bot:"]
    shown = 0
    for item in _top_items(groups.get("by_bot"), max_items=5):
        lines.append(
            f"- {item.get('name')}: ciclos {item.get('cycles')} | fechados {item.get('closed')} | "
            f"WR {_fmt_pct(item.get('win_rate_pct'))} | Exp {_fmt_signed(item.get('expectancy'))} | "
            f"status {item.get('sample_status') or 'N/A'}"
        )
        shown += 1
    if not shown:
        lines.append("- Sem dados suficientes por bot.")

    lines += ["", "Indícios por setup:"]
    shown = 0
    for item in _top_items(groups.get("by_setup"), max_items=5):
        lines.append(
            f"- {item.get('name')}: ciclos {item.get('cycles')} | fechados {item.get('closed')} | "
            f"WR {_fmt_pct(item.get('win_rate_pct'))} | Exp {_fmt_signed(item.get('expectancy'))} | "
            f"status {item.get('sample_status') or 'N/A'}"
        )
        shown += 1
    if not shown:
        lines.append("- Sem dados suficientes por setup.")

    # Alertas de qualidade de dados: só mostra o essencial.
    weak = []
    for field in ["score", "mfe_pct", "mae_pct"]:
        item = core.get(field) or {}
        pct = _safe_float(item.get("pct"), 0.0)
        if pct < 70:
            weak.append(f"{field} {pct}%")
    for field in ["score_bucket", "risk_bucket", "execution_mode", "paper_positions", "memory_usage_pct", "adx", "atr", "rsi", "btc_alignment", "volatility"]:
        item = ctx.get(field) or {}
        pct = _safe_float(item.get("pct"), 0.0)
        if pct < 70:
            weak.append(f"{field} {pct}%")

    lines += ["", "Qualidade dos dados:"]
    if weak:
        lines.append("- Campos com baixa cobertura: " + "; ".join(weak[:8]) + ("..." if len(weak) > 8 else ""))
        lines.append("- Recomendação: manter Learning em OBSERVE e bloquear alterações automáticas.")
    else:
        lines.append("- Cobertura mínima aceitável para leitura preliminar.")

    # Observações automáticas resumidas.
    important_obs = []
    for obs in observations:
        if obs.get("type") in {"data_quality", "readiness"}:
            important_obs.append(obs.get("message"))
        elif obs.get("type") == "group" and obs.get("sample_status") not in {"AMOSTRA_INSUFICIENTE", None}:
            important_obs.append(obs.get("message"))
    lines += ["", "Observações:"]
    if important_obs:
        for msg in important_obs[:5]:
            lines.append(f"- {msg}")
    else:
        lines.append("- Nenhuma observação relevante além de amostra insuficiente.")

    lines += [
        "",
        "Decisão operacional:",
        "- NÃO alterar bots, scores, risco, Policy ou corretora com esta amostra.",
        "- Usar este brief apenas para acompanhamento consultivo.",
    ]
    return "\n".join(lines), payload


def refresh_state(reason="auto_refresh", limit=None):
    """Recalcula o estado do Learning Engine e grava state/export/audit.

    Esta funcao nao altera Policy, scores, risco, bots ou corretora.
    Ela apenas mantém learning_state.json atualizado para a Central consultar
    sem depender de comando manual no Telegram.
    """
    payload = build_learning_payload(limit=limit or LEARNING_MAX_READ)
    _append_jsonl(LEARNING_AUDIT_FILE, {
        "ts": data_hora_sp_str(),
        "event": "LEARNING_STATE_REFRESH",
        "reason": str(reason or "auto_refresh"),
        "summary": payload.get("summary"),
        "readiness": payload.get("readiness"),
        "policy_suggestions": payload.get("policy_suggestions") or [],
    })
    return {
        "ok": True,
        "module": "learning_engine",
        "version": VERSION,
        "mode": MODE,
        "reason": str(reason or "auto_refresh"),
        "generated_at": payload.get("generated_at"),
        "summary": payload.get("summary"),
        "readiness": payload.get("readiness"),
        "policy_suggestions": payload.get("policy_suggestions") or [],
    }


def get_status():
    payload = build_learning_payload(limit=LEARNING_MAX_READ)
    return {
        "ok": True,
        "module": "learning_engine",
        "version": VERSION,
        "mode": MODE,
        "data_dir": str(DATA_DIR),
        "state_file": str(LEARNING_STATE_FILE),
        "audit_file": str(LEARNING_AUDIT_FILE),
        "export_file": str(LEARNING_EXPORT_FILE),
        "summary": payload.get("summary"),
        "readiness": payload.get("readiness"),
    }


def get_state():
    return {
        "ok": True,
        "generated_at": data_hora_sp_str(),
        "state": _read_json(LEARNING_STATE_FILE, {}),
        "status": get_status(),
    }


def build_readiness_report():
    payload = build_learning_payload(limit=LEARNING_MAX_READ)
    cov = payload.get("coverage") or {}
    core = cov.get("core") or {}
    context = cov.get("context") or {}
    readiness = payload.get("readiness") or {}
    summary = payload.get("summary") or {}

    def line_for(field, data):
        item = data.get(field) or {}
        pct = item.get("pct", 0)
        mark = "✅" if pct >= 95 else "⚠️" if pct >= 70 else "🔴"
        return f"{field}: {item.get('present',0)}/{item.get('total',0)} ({pct}%) {mark}"

    lines = [
        "🧠 LEARNING READINESS — CENTRAL QUANT",
        f"Data/hora: {payload.get('generated_at')}",
        "",
        f"Nível: {readiness.get('level')}",
        f"Confiança: {readiness.get('confidence')}/100",
        f"Ciclos: {summary.get('cycles',0)} | Eventos: {summary.get('events',0)} | Fechados: {summary.get('closed',0)}",
        "",
        "Campos principais:",
    ]
    for field in ["trade_id", "bot", "setup", "symbol", "side", "score", "mfe_pct", "mae_pct"]:
        lines.append(line_for(field, core))
    lines += ["", "Contexto:"]
    for field in ["hour", "session_br", "score_bucket", "risk_bucket", "execution_mode", "paper_positions", "memory_usage_pct"]:
        lines.append(line_for(field, context))
    lines += ["", "Observação: readiness não autoriza mudanças automáticas. Ele apenas mede se a base já está madura."]
    return "\n".join(lines), payload
