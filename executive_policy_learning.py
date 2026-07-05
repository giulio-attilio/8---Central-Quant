# -*- coding: utf-8 -*-
"""
Executive Policy Learning V1 — Central Quant
Versão: 2026-07-05-EXECUTIVE-POLICY-LEARNING-V1

Objetivo:
- Aprender, de forma leve e incremental, como as policies executivas se comportam.
- Não executa trades.
- Não altera policies.
- Não carrega histórico inteiro em memória.
- Lê apenas eventos novos do Executive Policy Timeline via offset persistente.
- Gera estatísticas por policy code.

Arquivos:
- data/executive_policy_timeline.jsonl
- data/executive_policy_learning_state.json
- data/executive_policy_learning_stats.json
- data/executive_policy_learning_log.jsonl
"""

import os
import json
import time
from datetime import datetime
from pathlib import Path

VERSION = "2026-07-05-EXECUTIVE-POLICY-LEARNING-V1"

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("CENTRAL_DATA_DIR", str(BASE_DIR / "data")))
DATA_DIR.mkdir(exist_ok=True)

TIMELINE_FILE = Path(os.environ.get("EXECUTIVE_POLICY_TIMELINE_FILE", str(DATA_DIR / "executive_policy_timeline.jsonl")))
STATE_FILE = Path(os.environ.get("EXECUTIVE_POLICY_LEARNING_STATE_FILE", str(DATA_DIR / "executive_policy_learning_state.json")))
STATS_FILE = Path(os.environ.get("EXECUTIVE_POLICY_LEARNING_STATS_FILE", str(DATA_DIR / "executive_policy_learning_stats.json")))
LOG_FILE = Path(os.environ.get("EXECUTIVE_POLICY_LEARNING_LOG_FILE", str(DATA_DIR / "executive_policy_learning_log.jsonl")))

MAX_EVENTS_PER_RUN = int(os.environ.get("EXECUTIVE_POLICY_LEARNING_MAX_EVENTS_PER_RUN", "500"))
MIN_SAMPLE_FOR_CONFIDENCE = int(os.environ.get("EXECUTIVE_POLICY_LEARNING_MIN_SAMPLE", "10"))


def _now():
    return datetime.now().strftime("%d/%m/%Y %H:%M:%S")


def _safe_float(value, default=0.0):
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _safe_int(value, default=0):
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def _read_json(path, default):
    try:
        if not Path(path).exists():
            return default
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _write_json(path, payload):
    tmp = str(path) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)
    os.replace(tmp, path)


def _append_log(event):
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
    except Exception:
        pass


def _load_state():
    state = _read_json(STATE_FILE, {})
    if not isinstance(state, dict):
        state = {}
    state.setdefault("version", VERSION)
    state.setdefault("timeline_offset", 0)
    state.setdefault("events_processed", 0)
    state.setdefault("last_run_at", None)
    state.setdefault("last_error", None)
    return state


def _save_state(state):
    state["version"] = VERSION
    state["updated_at"] = _now()
    _write_json(STATE_FILE, state)


def _empty_stats():
    return {
        "ok": True,
        "version": VERSION,
        "generated_at": _now(),
        "policies": {},
        "summary": {
            "policy_count": 0,
            "events_seen": 0,
            "events_processed": 0,
            "confident_policies": 0,
            "observation_policies": 0,
            "weak_policies": 0,
            "average_score": 0.0,
        },
    }


def _load_stats():
    stats = _read_json(STATS_FILE, _empty_stats())
    if not isinstance(stats, dict):
        stats = _empty_stats()
    stats.setdefault("ok", True)
    stats.setdefault("version", VERSION)
    stats.setdefault("policies", {})
    stats.setdefault("summary", {})
    return stats


def _save_stats(stats):
    stats["version"] = VERSION
    stats["generated_at"] = _now()
    _recompute_summary(stats)
    _write_json(STATS_FILE, stats)


def _policy_template(code):
    return {
        "code": code,
        "first_seen_at": None,
        "last_seen_at": None,
        "events": 0,
        "created": 0,
        "activated": 0,
        "updated": 0,
        "released": 0,
        "expired": 0,
        "kept": 0,
        "blocked_trades_est": 0,
        "allowed_trades_est": 0,
        "risk_events": 0,
        "release_events": 0,
        "auto_release_events": 0,
        "priority_events": 0,
        "timeline_events": 0,
        "score": 50.0,
        "confidence_pct": 0.0,
        "recommendation": "OBSERVAR",
        "notes": [],
        "last_event_type": None,
        "last_reason": None,
    }


def _extract_code(event):
    if not isinstance(event, dict):
        return None

    for key in ["code", "policy_code", "policy", "policy_code_normalized"]:
        value = event.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().upper()

    payload = event.get("payload")
    if isinstance(payload, dict):
        for key in ["code", "policy_code", "policy"]:
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip().upper()

    return None


def _extract_event_type(event):
    for key in ["event", "event_type", "type", "action"]:
        value = event.get(key) if isinstance(event, dict) else None
        if isinstance(value, str) and value.strip():
            return value.strip().upper()
    return "UNKNOWN"


def _event_text(event):
    try:
        return json.dumps(event, ensure_ascii=False).lower()
    except Exception:
        return str(event).lower()


def _apply_event_to_policy(policy, event):
    event_type = _extract_event_type(event)
    text = _event_text(event)
    now = event.get("generated_at") or event.get("created_at") or event.get("ts") or _now()

    if not policy.get("first_seen_at"):
        policy["first_seen_at"] = now
    policy["last_seen_at"] = now
    policy["last_event_type"] = event_type

    reason = event.get("reason") or event.get("rationale") or event.get("message")
    if reason:
        policy["last_reason"] = str(reason)[:300]

    policy["events"] = _safe_int(policy.get("events")) + 1
    policy["timeline_events"] = _safe_int(policy.get("timeline_events")) + 1

    if "CREATE" in event_type or "CREATED" in event_type or "NOVA" in text or "created" in text:
        policy["created"] = _safe_int(policy.get("created")) + 1

    if "ACTIVE" in event_type or "ACTIVATE" in event_type or "INGEST" in event_type:
        policy["activated"] = _safe_int(policy.get("activated")) + 1

    if "UPDATE" in event_type or "SYNC" in event_type:
        policy["updated"] = _safe_int(policy.get("updated")) + 1

    if "RELEASE" in event_type or "released" in text or "liber" in text:
        policy["released"] = _safe_int(policy.get("released")) + 1
        policy["release_events"] = _safe_int(policy.get("release_events")) + 1
        if "AUTO" in event_type or "auto_release" in text:
            policy["auto_release_events"] = _safe_int(policy.get("auto_release_events")) + 1

    if "EXPIRE" in event_type or "expired" in text or "expir" in text:
        policy["expired"] = _safe_int(policy.get("expired")) + 1

    if "KEEP" in event_type or "kept" in text or "mantid" in text:
        policy["kept"] = _safe_int(policy.get("kept")) + 1

    if "DENY" in text or "BLOCK" in text or "bloque" in text or "no_new" in text or "limit_new" in text:
        policy["risk_events"] = _safe_int(policy.get("risk_events")) + 1
        policy["blocked_trades_est"] = _safe_int(policy.get("blocked_trades_est")) + 1

    if "ALLOW" in text or "normal" in text or "permit" in text:
        policy["allowed_trades_est"] = _safe_int(policy.get("allowed_trades_est")) + 1

    if "PRIORITY" in event_type or "priority" in text:
        policy["priority_events"] = _safe_int(policy.get("priority_events")) + 1

    _score_policy(policy)


def _score_policy(policy):
    """
    Score V1 consultivo.
    Não tenta provar PnL ainda; mede utilidade operacional da policy.
    V2 poderá cruzar com outcome/decision_log para medir PnL evitado/perdido.
    """
    events = max(0, _safe_int(policy.get("events")))
    risk = _safe_int(policy.get("risk_events"))
    releases = _safe_int(policy.get("release_events"))
    kept = _safe_int(policy.get("kept"))
    expired = _safe_int(policy.get("expired"))
    blocked = _safe_int(policy.get("blocked_trades_est"))

    sample_score = min(30.0, events * 3.0)
    risk_score = min(25.0, risk * 4.0)
    release_score = min(20.0, releases * 5.0)
    lifecycle_score = min(15.0, (kept + expired + releases) * 2.5)
    balance_score = 10.0

    # Penaliza policies que aparecem muitas vezes e nunca têm release/expiração.
    if events >= MIN_SAMPLE_FOR_CONFIDENCE and releases == 0 and expired == 0:
        balance_score = 3.0

    score = sample_score + risk_score + release_score + lifecycle_score + balance_score
    score = max(0.0, min(100.0, score))

    confidence = min(100.0, (events / max(1, MIN_SAMPLE_FOR_CONFIDENCE)) * 100.0)

    if confidence < 40:
        recommendation = "AGUARDAR_AMOSTRA"
    elif score >= 75:
        recommendation = "MANTER"
    elif score >= 55:
        recommendation = "OBSERVAR"
    elif score >= 40:
        recommendation = "REVISAR"
    else:
        recommendation = "ENFRAQUECER_OU_APOSENTAR"

    notes = []
    if events < MIN_SAMPLE_FOR_CONFIDENCE:
        notes.append("Amostra ainda insuficiente para conclusão robusta.")
    if blocked > 0:
        notes.append("Policy associada a bloqueios/restrições operacionais.")
    if releases > 0:
        notes.append("Policy possui eventos de liberação/release registrados.")
    if events >= MIN_SAMPLE_FOR_CONFIDENCE and releases == 0 and expired == 0:
        notes.append("Policy acumula eventos sem ciclo claro de release/expiração.")

    policy["score"] = round(score, 2)
    policy["confidence_pct"] = round(confidence, 2)
    policy["recommendation"] = recommendation
    policy["notes"] = notes[-5:]


def _recompute_summary(stats):
    policies = stats.get("policies") or {}
    values = [p for p in policies.values() if isinstance(p, dict)]
    count = len(values)

    avg = 0.0
    if values:
        avg = sum(_safe_float(p.get("score")) for p in values) / len(values)

    confident = sum(1 for p in values if _safe_float(p.get("confidence_pct")) >= 70)
    weak = sum(1 for p in values if str(p.get("recommendation")) in {"REVISAR", "ENFRAQUECER_OU_APOSENTAR"})
    observation = max(0, count - confident - weak)

    stats["summary"] = {
        "policy_count": count,
        "events_seen": sum(_safe_int(p.get("events")) for p in values),
        "events_processed": sum(_safe_int(p.get("timeline_events")) for p in values),
        "confident_policies": confident,
        "observation_policies": observation,
        "weak_policies": weak,
        "average_score": round(avg, 2),
        "updated_at": _now(),
    }


def _iter_new_timeline_events(offset, max_events):
    """
    Lê eventos novos por offset.
    Retorna: events, new_offset, reached_eof
    """
    events = []
    if not TIMELINE_FILE.exists():
        return events, offset, True

    new_offset = offset
    try:
        with open(TIMELINE_FILE, "rb") as f:
            try:
                f.seek(max(0, int(offset)))
            except Exception:
                f.seek(0)

            for _ in range(max_events):
                line = f.readline()
                if not line:
                    new_offset = f.tell()
                    return events, new_offset, True

                new_offset = f.tell()
                try:
                    decoded = line.decode("utf-8").strip()
                    if not decoded:
                        continue
                    event = json.loads(decoded)
                    if isinstance(event, dict):
                        events.append(event)
                except Exception:
                    continue

        return events, new_offset, False
    except Exception:
        return events, offset, True


def run_executive_policy_learning(context=None, commit=True, max_events=None):
    """
    Roda uma atualização incremental.
    """
    started = time.time()
    state = _load_state()
    stats = _load_stats()

    offset = _safe_int(state.get("timeline_offset"), 0)
    max_events = int(max_events or MAX_EVENTS_PER_RUN)

    events, new_offset, reached_eof = _iter_new_timeline_events(offset, max_events)

    processed = 0
    skipped_without_code = 0

    policies = stats.setdefault("policies", {})

    for event in events:
        code = _extract_code(event)
        if not code:
            skipped_without_code += 1
            continue

        policy = policies.get(code)
        if not isinstance(policy, dict):
            policy = _policy_template(code)
            policies[code] = policy

        _apply_event_to_policy(policy, event)
        processed += 1

    state["timeline_offset"] = new_offset
    state["last_run_at"] = _now()
    state["last_error"] = None
    state["events_processed"] = _safe_int(state.get("events_processed")) + processed
    state["last_batch"] = {
        "events_read": len(events),
        "events_processed": processed,
        "skipped_without_code": skipped_without_code,
        "reached_eof": reached_eof,
        "old_offset": offset,
        "new_offset": new_offset,
    }

    if commit:
        _save_stats(stats)
        _save_state(state)

    result = {
        "ok": True,
        "module": "executive_policy_learning",
        "version": VERSION,
        "generated_at": _now(),
        "commit": commit,
        "timeline_file": str(TIMELINE_FILE),
        "state_file": str(STATE_FILE),
        "stats_file": str(STATS_FILE),
        "events_read": len(events),
        "events_processed": processed,
        "skipped_without_code": skipped_without_code,
        "old_offset": offset,
        "new_offset": new_offset,
        "reached_eof": reached_eof,
        "duration_ms": round((time.time() - started) * 1000, 2),
        "summary": stats.get("summary") or {},
    }

    _append_log(result)
    return result


def get_executive_policy_learning_stats():
    stats = _load_stats()
    _recompute_summary(stats)
    return stats


def get_executive_policy_learning_health():
    state = _load_state()
    stats = _load_stats()
    summary = stats.get("summary") or {}

    status = "OK"
    if not TIMELINE_FILE.exists():
        status = "NO_TIMELINE"
    elif _safe_int(summary.get("policy_count")) == 0:
        status = "WAITING_DATA"

    return {
        "ok": True,
        "module": "executive_policy_learning",
        "loaded": True,
        "version": VERSION,
        "status": status,
        "timeline_file": str(TIMELINE_FILE),
        "timeline_exists": TIMELINE_FILE.exists(),
        "state_file": str(STATE_FILE),
        "stats_file": str(STATS_FILE),
        "timeline_offset": state.get("timeline_offset"),
        "last_run_at": state.get("last_run_at"),
        "last_error": state.get("last_error"),
        "summary": summary,
    }


def build_executive_policy_learning_report(result=None, limit=12):
    if result is None:
        result = run_executive_policy_learning(context={}, commit=True)

    stats = get_executive_policy_learning_stats()
    summary = stats.get("summary") or {}
    policies = stats.get("policies") or {}

    ranking = sorted(
        [p for p in policies.values() if isinstance(p, dict)],
        key=lambda p: (_safe_float(p.get("score")), _safe_float(p.get("confidence_pct")), _safe_int(p.get("events"))),
        reverse=True,
    )

    lines = [
        "🧠 EXECUTIVE POLICY LEARNING — CENTRAL QUANT V1",
        f"Data/hora: {_now()}",
        "",
        f"Status: {'✅' if result.get('ok') else '❌'}",
        f"Eventos lidos agora: {result.get('events_read', 0)}",
        f"Eventos processados agora: {result.get('events_processed', 0)}",
        f"Timeline EOF: {result.get('reached_eof')}",
        "",
        "Resumo:",
        f"- Policies avaliadas: {summary.get('policy_count', 0)}",
        f"- Eventos acumulados: {summary.get('events_seen', 0)}",
        f"- Policies confiáveis: {summary.get('confident_policies', 0)}",
        f"- Em observação: {summary.get('observation_policies', 0)}",
        f"- Fracas/revisar: {summary.get('weak_policies', 0)}",
        f"- Score médio: {summary.get('average_score', 0)}",
        "",
    ]

    if not ranking:
        lines += [
            "Ainda não há policies suficientes no Learning.",
            "",
            "Leitura:",
            "O módulo está carregado, mas precisa de eventos no Executive Policy Timeline para aprender.",
        ]
        return "\n".join(lines)

    lines.append("Ranking:")
    for idx, p in enumerate(ranking[:limit], start=1):
        lines += [
            f"{idx}. {p.get('code')}",
            f"- Score: {p.get('score')} | Confiança: {p.get('confidence_pct')}%",
            f"- Eventos: {p.get('events')} | Risk: {p.get('risk_events')} | Releases: {p.get('release_events')}",
            f"- Recomendação: {p.get('recommendation')}",
        ]
        notes = p.get("notes") or []
        if notes:
            lines.append(f"- Nota: {notes[0]}")
        lines.append("")

    lines += [
        "Observação:",
        "V1 mede utilidade operacional por eventos de policy/timeline.",
        "V2 poderá cruzar com Decision Log e Outcome para estimar PnL salvo/perdido.",
    ]
    return "\n".join(lines)


def build_policy_history_report(code, limit=1):
    code = str(code or "").strip().upper()
    stats = get_executive_policy_learning_stats()
    policy = (stats.get("policies") or {}).get(code)

    lines = [
        f"🧠 POLICY HISTORY — {code}",
        f"Data/hora: {_now()}",
        "",
    ]

    if not policy:
        lines += [
            "Policy ainda não encontrada no Executive Policy Learning.",
            "",
            "Sugestão:",
            "Rode /policylearning após o Executive Policy Timeline acumular eventos.",
        ]
        return "\n".join(lines)

    lines += [
        f"Score: {policy.get('score')}",
        f"Confiança: {policy.get('confidence_pct')}%",
        f"Recomendação: {policy.get('recommendation')}",
        "",
        f"Eventos: {policy.get('events')}",
        f"Criada/ativada: {policy.get('created')} / {policy.get('activated')}",
        f"Atualizações: {policy.get('updated')}",
        f"Risk events: {policy.get('risk_events')}",
        f"Bloqueios estimados: {policy.get('blocked_trades_est')}",
        f"Allows estimados: {policy.get('allowed_trades_est')}",
        f"Releases: {policy.get('released')}",
        f"Expirações: {policy.get('expired')}",
        f"Auto releases: {policy.get('auto_release_events')}",
        "",
        f"Primeira aparição: {policy.get('first_seen_at')}",
        f"Última aparição: {policy.get('last_seen_at')}",
        f"Último evento: {policy.get('last_event_type')}",
    ]

    if policy.get("last_reason"):
        lines.append(f"Último motivo: {policy.get('last_reason')}")

    notes = policy.get("notes") or []
    if notes:
        lines.append("")
        lines.append("Notas:")
        for note in notes:
            lines.append(f"- {note}")

    return "\n".join(lines)


def read_executive_policy_learning_log(limit=20):
    if not LOG_FILE.exists():
        return {"ok": True, "items": [], "log_file": str(LOG_FILE)}

    try:
        with open(LOG_FILE, "rb") as f:
            f.seek(0, os.SEEK_END)
            end = f.tell()
            block = 4096
            data = b""
            pos = end
            while pos > 0 and data.count(b"\n") <= limit:
                read_size = min(block, pos)
                pos -= read_size
                f.seek(pos)
                data = f.read(read_size) + data

        items = []
        for line in data.splitlines()[-limit:]:
            try:
                items.append(json.loads(line.decode("utf-8")))
            except Exception:
                pass
        return {"ok": True, "items": items, "log_file": str(LOG_FILE)}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "items": [], "log_file": str(LOG_FILE)}


if __name__ == "__main__":
    print(build_executive_policy_learning_report())
