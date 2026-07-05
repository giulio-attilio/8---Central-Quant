# -*- coding: utf-8 -*-
"""
Executive Policy Learning V2.1.8 — Central Quant
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
import re
from datetime import datetime
from pathlib import Path

VERSION = "2026-07-05-EXECUTIVE-POLICY-LEARNING-V2.1.8"

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("CENTRAL_DATA_DIR", str(BASE_DIR / "data")))
DATA_DIR.mkdir(exist_ok=True)

TIMELINE_FILE = Path(os.environ.get("EXECUTIVE_POLICY_TIMELINE_FILE", str(DATA_DIR / "executive_policy_timeline.jsonl")))
STATE_FILE = Path(os.environ.get("EXECUTIVE_POLICY_LEARNING_STATE_FILE", str(DATA_DIR / "executive_policy_learning_state.json")))
STATS_FILE = Path(os.environ.get("EXECUTIVE_POLICY_LEARNING_STATS_FILE", str(DATA_DIR / "executive_policy_learning_stats.json")))
LOG_FILE = Path(os.environ.get("EXECUTIVE_POLICY_LEARNING_LOG_FILE", str(DATA_DIR / "executive_policy_learning_log.jsonl")))

MAX_EVENTS_PER_RUN = int(os.environ.get("EXECUTIVE_POLICY_LEARNING_MAX_EVENTS_PER_RUN", "500"))
MIN_SAMPLE_FOR_CONFIDENCE = int(os.environ.get("EXECUTIVE_POLICY_LEARNING_MIN_SAMPLE", "10"))

# V2.1.8 — correlação entre Policy Timeline e Decision Log.
DECISION_LOG_FILE = Path(os.environ.get("CENTRAL_DECISION_LOG_FILE", str(DATA_DIR / "decision_log.jsonl")))
V2_STATE_FILE = Path(os.environ.get("EXECUTIVE_POLICY_LEARNING_V2_STATE_FILE", str(DATA_DIR / "executive_policy_learning_v2_state.json")))
V2_EFFECT_FILE = Path(os.environ.get("EXECUTIVE_POLICY_LEARNING_EFFECT_FILE", str(DATA_DIR / "executive_policy_learning_effect.json")))
V2_LOG_FILE = Path(os.environ.get("EXECUTIVE_POLICY_LEARNING_V2_LOG_FILE", str(DATA_DIR / "executive_policy_learning_v2_log.jsonl")))
MAX_DECISIONS_PER_RUN = int(os.environ.get("EXECUTIVE_POLICY_LEARNING_MAX_DECISIONS_PER_RUN", "700"))
POLICY_DECISION_WINDOW_MINUTES = int(os.environ.get("EXECUTIVE_POLICY_DECISION_WINDOW_MINUTES", "1440"))



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
        "🧠 EXECUTIVE POLICY LEARNING — CENTRAL QUANT V2.1.8",
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


def seed_executive_policy_learning_events(commit=True):
    """
    Cria eventos controlados de teste na timeline para validar o fluxo:
    Timeline -> Policy Learning -> Stats/Ranking.

    Importante:
    - Os eventos possuem test_seed=True.
    - Não representam decisão real.
    - Não executam trades.
    - Não alteram policies ativas.
    """
    DATA_DIR.mkdir(exist_ok=True)

    now = _now()
    seed_id = datetime.now().strftime("%Y%m%d%H%M%S")

    events = [
        {
            "event_type": "POLICY_CREATED",
            "code": "WAIT_SAMPLE",
            "generated_at": now,
            "reason": "Seed técnico para validar Executive Policy Learning.",
            "source": "executive_policy_learning_seed",
            "test_seed": True,
            "seed_id": seed_id,
        },
        {
            "event_type": "POLICY_KEPT",
            "code": "WAIT_SAMPLE",
            "generated_at": now,
            "reason": "Seed: policy mantida por amostra insuficiente.",
            "source": "executive_policy_learning_seed",
            "test_seed": True,
            "seed_id": seed_id,
        },
        {
            "event_type": "POLICY_CREATED",
            "code": "LIMIT_NEW_LONG",
            "generated_at": now,
            "reason": "Seed: concentração direcional elevada exige restrição.",
            "source": "executive_policy_learning_seed",
            "test_seed": True,
            "seed_id": seed_id,
            "payload": {
                "dominant_side": "LONG",
                "dominant_pct": 76.0,
                "blocks_expansion": True,
            },
        },
        {
            "event_type": "POLICY_PRIORITY_DENY",
            "code": "LIMIT_NEW_LONG",
            "generated_at": now,
            "reason": "Seed: bloqueio estimado de nova expansão LONG.",
            "source": "executive_policy_learning_seed",
            "test_seed": True,
            "seed_id": seed_id,
        },
        {
            "event_type": "POLICY_AUTO_RELEASE",
            "code": "LIMIT_NEW_LONG",
            "generated_at": now,
            "reason": "Seed: liberação após queda de concentração.",
            "source": "executive_policy_learning_seed",
            "test_seed": True,
            "seed_id": seed_id,
            "payload": {
                "release_condition": "LONG abaixo de 75%",
            },
        },
        {
            "event_type": "POLICY_CREATED",
            "code": "NORMAL_WITH_MONITORING",
            "generated_at": now,
            "reason": "Seed: operação normal com monitoramento assistido.",
            "source": "executive_policy_learning_seed",
            "test_seed": True,
            "seed_id": seed_id,
        },
        {
            "event_type": "POLICY_ALLOW",
            "code": "NORMAL_WITH_MONITORING",
            "generated_at": now,
            "reason": "Seed: operação permitida sem expansão estrutural.",
            "source": "executive_policy_learning_seed",
            "test_seed": True,
            "seed_id": seed_id,
        },
    ]

    if commit:
        with open(TIMELINE_FILE, "a", encoding="utf-8") as f:
            for event in events:
                f.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")

    result = {
        "ok": True,
        "module": "executive_policy_learning",
        "version": VERSION,
        "generated_at": now,
        "commit": commit,
        "seed_id": seed_id,
        "events_created": len(events),
        "timeline_file": str(TIMELINE_FILE),
        "notes": [
            "Eventos seed são técnicos e possuem test_seed=True.",
            "Eles servem apenas para validar o fluxo do Policy Learning.",
            "Não representam decisão real e não executam trades.",
        ],
    }

    _append_log({
        "event": "POLICY_LEARNING_SEED",
        **result,
    })

    return result


def build_executive_policy_learning_seed_report(result=None):
    if result is None:
        result = seed_executive_policy_learning_events(commit=True)

    lines = [
        "🌱 EXECUTIVE POLICY LEARNING SEED — CENTRAL QUANT",
        f"Data/hora: {_now()}",
        "",
        f"Status: {'✅' if result.get('ok') else '❌'}",
        f"Commit: {result.get('commit')}",
        f"Seed ID: {result.get('seed_id')}",
        f"Eventos criados: {result.get('events_created', 0)}",
        f"Timeline: {result.get('timeline_file')}",
        "",
        "Eventos seed:",
        "- WAIT_SAMPLE criada/mantida",
        "- LIMIT_NEW_LONG criada/bloqueio/release",
        "- NORMAL_WITH_MONITORING criada/allow",
        "",
        "Importante:",
        "- Estes eventos são técnicos e possuem test_seed=True.",
        "- Eles validam o pipeline; não representam decisão real.",
        "- Não executam trades e não alteram policies ativas.",
        "",
        "Próximo comando:",
        "/policylearning",
    ]

    return "\n".join(lines)


# ==========================================================
# EXECUTIVE POLICY LEARNING V2.1.8
# Correlação Timeline + Decision Log
# ==========================================================

def _parse_dt_any(value):
    if not value:
        return None
    txt = str(value).strip()
    formats = [
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(txt[:19], fmt)
        except Exception:
            pass
    try:
        # ISO com frações/timezone simples
        cleaned = txt.replace("Z", "").split("+")[0].split(".")[0]
        return datetime.fromisoformat(cleaned)
    except Exception:
        return None


def _event_time(event):
    if not isinstance(event, dict):
        return None
    for key in ["generated_at", "created_at", "updated_at", "ts", "timestamp", "datetime", "date"]:
        dt = _parse_dt_any(event.get(key))
        if dt:
            return dt
    return None


def _decision_time(decision):
    if not isinstance(decision, dict):
        return None
    for key in ["generated_at", "created_at", "updated_at", "ts", "timestamp", "datetime", "date"]:
        dt = _parse_dt_any(decision.get(key))
        if dt:
            return dt
    return None


def _extract_decision(decision):
    if not isinstance(decision, dict):
        return "UNKNOWN"
    for key in ["decision", "status", "result", "action"]:
        value = decision.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().upper()
    payload = decision.get("payload")
    if isinstance(payload, dict):
        for key in ["decision", "status", "result", "action"]:
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip().upper()
    return "UNKNOWN"


def _extract_trade_fields(decision):
    if not isinstance(decision, dict):
        return {}

    payload = decision.get("payload") if isinstance(decision.get("payload"), dict) else {}
    trade = decision.get("trade") if isinstance(decision.get("trade"), dict) else {}

    def pick(*keys):
        for source in [decision, trade, payload]:
            if not isinstance(source, dict):
                continue
            for key in keys:
                value = source.get(key)
                if value not in (None, ""):
                    return value
        return None

    return {
        "bot": str(pick("bot", "robot") or "UNKNOWN").upper(),
        "setup": str(pick("setup", "strategy", "signal_type") or "UNKNOWN").upper(),
        "symbol": str(pick("symbol", "symbol_clean", "ativo", "pair") or "UNKNOWN").upper(),
        "side": str(pick("side", "direction") or "UNKNOWN").upper(),
        "risk_pct": _safe_float(pick("risk_pct", "risk", "risco"), 0.0),
        "score": _safe_float(pick("score", "quality_score"), 0.0),
    }


def _read_new_jsonl(path, offset, max_items):
    items = []
    if not Path(path).exists():
        return items, offset, True

    new_offset = offset
    try:
        with open(path, "rb") as f:
            try:
                f.seek(max(0, int(offset)))
            except Exception:
                f.seek(0)

            for _ in range(max_items):
                line = f.readline()
                if not line:
                    new_offset = f.tell()
                    return items, new_offset, True

                new_offset = f.tell()
                try:
                    decoded = line.decode("utf-8").strip()
                    if not decoded:
                        continue
                    item = json.loads(decoded)
                    if isinstance(item, dict):
                        items.append(item)
                except Exception:
                    continue

        return items, new_offset, False
    except Exception:
        return items, offset, True


def _read_all_policy_events_light(limit=5000):
    """
    Lê eventos da timeline de forma limitada para correlacionar com decisões.
    Não é usado em loop pesado; V2.1.8 trabalha com limite.
    """
    if not TIMELINE_FILE.exists():
        return []

    events = []
    try:
        with open(TIMELINE_FILE, "rb") as f:
            # Se arquivo for muito grande, lê apenas o final.
            try:
                f.seek(0, os.SEEK_END)
                size = f.tell()
                max_bytes = 1024 * 1024
                if size > max_bytes:
                    f.seek(size - max_bytes)
                    f.readline()
                else:
                    f.seek(0)
            except Exception:
                f.seek(0)

            for line in f:
                if len(events) >= limit:
                    break
                try:
                    item = json.loads(line.decode("utf-8").strip())
                    if isinstance(item, dict):
                        code = _extract_code(item)
                        dt = _event_time(item)
                        if code and dt:
                            events.append({
                                "code": code,
                                "dt": dt,
                                "event_type": _extract_event_type(item),
                                "test_seed": bool(item.get("test_seed")),
                                "reason": item.get("reason") or item.get("rationale") or "",
                            })
                except Exception:
                    continue
    except Exception:
        return []

    events.sort(key=lambda x: x.get("dt"))
    return events



def _decision_policy_codes(decision):
    """
    V2.1.8 — Raw-Aware Policy Link Reader.

    Lê vínculo explícito salvo pelo Policy Decision Linker em todos os formatos
    que hoje aparecem no pipeline real:
    - decision_log.policy_codes / applied_policies / policy_context;
    - raw.policy_codes / raw.applied_policies / raw.policy_linker.policy_codes;
    - executive_policy.policy_codes;
    - raw.executive_policy.policy_codes;
    - payload/trade/context aninhados;
    - chaves em lower_case ou UPPER_CASE.

    Retorna lista normalizada, sem duplicidade.
    """
    codes = []

    direct_keys = [
        "policy_codes", "applied_policies", "applied_policy_codes",
        "policy_context", "matched_policy_codes", "blocked_policy_codes",
        "dominant_policy_code", "dominant_code", "active_policy_codes",
    ]

    scalar_keys = [
        "code", "policy_code", "policy_code_normalized", "dominant_code",
        "dominant_policy_code", "id", "name",
    ]

    nested_keys = [
        "policy_linker", "executive_policy", "priority", "payload", "trade",
        "raw", "context", "details", "decision_result", "result",
    ]

    def get_any(d, key):
        if not isinstance(d, dict):
            return None
        if key in d:
            return d.get(key)
        upper = key.upper()
        if upper in d:
            return d.get(upper)
        lower = key.lower()
        if lower in d:
            return d.get(lower)
        # fallback case-insensitive para objetos vindos do history/context manager
        for k, v in d.items():
            try:
                if str(k).strip().lower() == lower:
                    return v
            except Exception:
                continue
        return None

    def add(value, depth=0):
        if value is None or depth > 8:
            return

        if isinstance(value, (list, tuple, set)):
            for item in value:
                add(item, depth + 1)
            return

        if isinstance(value, dict):
            for key in scalar_keys:
                add(get_any(value, key), depth + 1)
            for key in direct_keys:
                add(get_any(value, key), depth + 1)
            for key in nested_keys:
                child = get_any(value, key)
                if isinstance(child, (dict, list, tuple, set)):
                    add(child, depth + 1)
            return

        text = str(value or "").strip()
        if not text:
            return

        # Strings enormes como dumps de dict não devem virar policy code.
        # Porém, se vierem como texto contendo policy_codes, tentamos extrair de forma segura.
        if len(text) > 120:
            upper_text = text.upper()
            known = [
                "WAIT_SAMPLE",
                "NORMAL_WITH_MONITORING",
                "LIMIT_NEW_LONG",
                "NO_NEW_LONG",
                "LIMIT_NEW_SHORT",
                "NO_NEW_SHORT",
                "REDUCE_SIZE",
                "NO_RISK_INCREASE",
            ]
            for code in known:
                if code in upper_text:
                    add(code, depth + 1)
            return

        if "," in text:
            for part in text.split(","):
                add(part, depth + 1)
            return

        clean = text.strip().strip("[]{}()'\"").upper()
        if not clean or len(clean) > 120:
            return

        # Evita aceitar status/decisões genéricas como se fossem policy code.
        blacklist = {
            "ALLOW", "DENY", "BLOCK", "TRUE", "FALSE", "NONE", "NULL",
            "VERIFY", "PAPER", "LIVE", "LONG", "SHORT", "BUY", "SELL",
            "FALCON", "PREDATOR", "TRENDPRO", "DONKEY", "COBRA", "MEME", "TURTLE",
        }
        if clean in blacklist:
            return

        if clean not in codes:
            codes.append(clean)

    if not isinstance(decision, dict):
        return []

    # O add(dict) já percorre campos diretos e raw.* recursivamente.
    add(decision)

    return codes

def _active_policy_codes_for_decision(decision_dt, policy_events, window_minutes=POLICY_DECISION_WINDOW_MINUTES):
    """
    V2.1.8: associação simples.
    Uma decisão é associada a policies cujos eventos ocorreram até a decisão
    dentro da janela configurada. Events de release/expire fecham a policy.
    """
    if not decision_dt:
        return []

    active = {}
    window_seconds = max(60, int(window_minutes) * 60)

    for event in policy_events:
        code = event.get("code")
        dt = event.get("dt")
        if not code or not dt:
            continue
        if dt > decision_dt:
            break

        age = (decision_dt - dt).total_seconds()
        if age < 0 or age > window_seconds:
            continue

        event_type = str(event.get("event_type") or "").upper()
        if "RELEASE" in event_type or "EXPIRE" in event_type or "REMOVED" in event_type:
            active.pop(code, None)
        else:
            active[code] = event

    return sorted(active.keys())


def _empty_effect():
    return {
        "ok": True,
        "version": VERSION,
        "generated_at": _now(),
        "source": "timeline_plus_decision_log",
        "decision_log_file": str(DECISION_LOG_FILE),
        "timeline_file": str(TIMELINE_FILE),
        "policies": {},
        "summary": {
            "policy_count": 0,
            "decisions_processed": 0,
            "decisions_matched": 0,
            "decisions_unmatched": 0,
            "average_effect_score": 0.0,
        },
    }


def _load_v2_state():
    state = _read_json(V2_STATE_FILE, {})
    if not isinstance(state, dict):
        state = {}
    state.setdefault("version", VERSION)
    state.setdefault("decision_log_offset", 0)
    state.setdefault("decisions_processed", 0)
    state.setdefault("last_run_at", None)
    state.setdefault("last_error", None)
    return state


def _save_v2_state(state):
    state["version"] = VERSION
    state["updated_at"] = _now()
    _write_json(V2_STATE_FILE, state)


def _load_effect():
    effect = _read_json(V2_EFFECT_FILE, _empty_effect())
    if not isinstance(effect, dict):
        effect = _empty_effect()
    effect.setdefault("policies", {})
    effect.setdefault("summary", {})
    return effect


def _save_effect(effect):
    effect["version"] = VERSION
    effect["generated_at"] = _now()
    _recompute_effect_summary(effect)
    _write_json(V2_EFFECT_FILE, effect)


def _effect_policy_template(code):
    return {
        "code": code,
        "first_seen_at": None,
        "last_seen_at": None,
        "decisions": 0,
        "allow": 0,
        "deny": 0,
        "block": 0,
        "reduce_size": 0,
        "no_expansion": 0,
        "unknown": 0,
        "by_bot": {},
        "by_side": {},
        "by_symbol": {},
        "risk_pct_total": 0.0,
        "score_total": 0.0,
        "avg_risk_pct": 0.0,
        "avg_trade_score": 0.0,
        "effect_score": 50.0,
        "confidence_pct": 0.0,
        "recommendation": "OBSERVAR",
        "notes": [],
    }


def _update_counter_map(target, key):
    key = str(key or "UNKNOWN").upper()
    target[key] = _safe_int(target.get(key)) + 1


def _apply_decision_to_effect(policy, decision):
    dt = _decision_time(decision)
    dt_txt = dt.strftime("%d/%m/%Y %H:%M:%S") if dt else _now()
    if not policy.get("first_seen_at"):
        policy["first_seen_at"] = dt_txt
    policy["last_seen_at"] = dt_txt

    decision_name = _extract_decision(decision)
    fields = _extract_trade_fields(decision)

    policy["decisions"] = _safe_int(policy.get("decisions")) + 1

    d = decision_name
    if "ALLOW" in d:
        policy["allow"] = _safe_int(policy.get("allow")) + 1
    elif "DENY" in d:
        policy["deny"] = _safe_int(policy.get("deny")) + 1
    elif "BLOCK" in d:
        policy["block"] = _safe_int(policy.get("block")) + 1
    elif "REDUCE" in d:
        policy["reduce_size"] = _safe_int(policy.get("reduce_size")) + 1
    elif "NO_EXPANSION" in d or "NO EXPANSION" in d:
        policy["no_expansion"] = _safe_int(policy.get("no_expansion")) + 1
    else:
        policy["unknown"] = _safe_int(policy.get("unknown")) + 1

    _update_counter_map(policy.setdefault("by_bot", {}), fields.get("bot"))
    _update_counter_map(policy.setdefault("by_side", {}), fields.get("side"))
    _update_counter_map(policy.setdefault("by_symbol", {}), fields.get("symbol"))

    policy["risk_pct_total"] = round(_safe_float(policy.get("risk_pct_total")) + _safe_float(fields.get("risk_pct")), 6)
    policy["score_total"] = round(_safe_float(policy.get("score_total")) + _safe_float(fields.get("score")), 6)

    decisions = max(1, _safe_int(policy.get("decisions")))
    policy["avg_risk_pct"] = round(_safe_float(policy.get("risk_pct_total")) / decisions, 4)
    policy["avg_trade_score"] = round(_safe_float(policy.get("score_total")) / decisions, 4)

    _score_effect_policy(policy)


def _score_effect_policy(policy):
    decisions = _safe_int(policy.get("decisions"))
    allow = _safe_int(policy.get("allow"))
    deny = _safe_int(policy.get("deny"))
    block = _safe_int(policy.get("block"))
    reduce_size = _safe_int(policy.get("reduce_size"))
    no_expansion = _safe_int(policy.get("no_expansion"))

    sample_score = min(30.0, decisions * 2.0)
    protection_score = min(30.0, (deny + block + reduce_size + no_expansion) * 4.0)
    operation_score = min(20.0, allow * 2.0)
    balance_score = 10.0

    # Penaliza política que só permite tudo sem restrição em contexto executivo.
    if decisions >= 10 and allow >= decisions * 0.9 and (deny + block + reduce_size + no_expansion) == 0:
        balance_score = 4.0

    # Penaliza política que só bloqueia, porque pode indicar excesso conservador.
    if decisions >= 10 and allow == 0 and (deny + block) >= decisions * 0.9:
        balance_score = 5.0

    score = max(0.0, min(100.0, sample_score + protection_score + operation_score + balance_score))
    confidence = min(100.0, (decisions / 20.0) * 100.0)

    if confidence < 35:
        recommendation = "AGUARDAR_AMOSTRA"
    elif score >= 80:
        recommendation = "MANTER"
    elif score >= 60:
        recommendation = "OBSERVAR"
    elif score >= 45:
        recommendation = "REVISAR"
    else:
        recommendation = "ENFRAQUECER_OU_APOSENTAR"

    notes = []
    if decisions < 20:
        notes.append("Amostra de decisões ainda insuficiente para conclusão robusta.")
    if deny + block + reduce_size + no_expansion > 0:
        notes.append("Policy influenciou restrição/controle de risco em decisões.")
    if allow > 0:
        notes.append("Policy também conviveu com decisões permitidas.")
    if decisions >= 10 and allow == 0:
        notes.append("Policy altamente restritiva; revisar impacto financeiro na V2.1.")
    if decisions >= 10 and allow >= decisions * 0.9:
        notes.append("Policy pouco restritiva; revisar se agrega proteção real.")

    policy["effect_score"] = round(score, 2)
    policy["confidence_pct"] = round(confidence, 2)
    policy["recommendation"] = recommendation
    policy["notes"] = notes[-5:]


def _recompute_effect_summary(effect):
    policies = effect.get("policies") or {}
    values = [p for p in policies.values() if isinstance(p, dict)]

    total_decisions = sum(_safe_int(p.get("decisions")) for p in values)
    avg = 0.0
    if values:
        avg = sum(_safe_float(p.get("effect_score")) for p in values) / len(values)

    effect["summary"] = {
        "policy_count": len(values),
        "decisions_processed": total_decisions,
        "decisions_matched": total_decisions,
        "average_effect_score": round(avg, 2),
        "updated_at": _now(),
    }


def run_executive_policy_learning_v2(context=None, commit=True, max_decisions=None):
    """
    V2.1.8:
    Lê decisões novas do decision_log e associa às policies ativas recentes da timeline.
    Não calcula PnL ainda.
    """
    started = time.time()
    state = _load_v2_state()
    effect = _load_effect()

    offset = _safe_int(state.get("decision_log_offset"), 0)
    max_decisions = int(max_decisions or MAX_DECISIONS_PER_RUN)

    decisions, new_offset, reached_eof = _read_new_jsonl(DECISION_LOG_FILE, offset, max_decisions)
    policy_events = _read_all_policy_events_light()

    processed = 0
    matched = 0
    unmatched = 0

    policies = effect.setdefault("policies", {})

    for decision in decisions:
        explicit_codes = _decision_policy_codes(decision)
        dt = _decision_time(decision)
        codes = explicit_codes or _active_policy_codes_for_decision(dt, policy_events)

        if not codes:
            unmatched += 1
            continue

        for code in codes:
            policy = policies.get(code)
            if not isinstance(policy, dict):
                policy = _effect_policy_template(code)
                policies[code] = policy
            _apply_decision_to_effect(policy, decision)
            matched += 1

        processed += 1

    state["decision_log_offset"] = new_offset
    state["last_run_at"] = _now()
    state["last_error"] = None
    state["decisions_processed"] = _safe_int(state.get("decisions_processed")) + processed
    state["last_batch"] = {
        "decisions_read": len(decisions),
        "decisions_processed": processed,
        "decisions_matched": matched,
        "decisions_unmatched": unmatched,
        "policy_events_loaded": len(policy_events),
        "old_offset": offset,
        "new_offset": new_offset,
        "reached_eof": reached_eof,
    }

    if commit:
        _save_effect(effect)
        _save_v2_state(state)

    result = {
        "ok": True,
        "module": "executive_policy_learning_v2",
        "version": VERSION,
        "generated_at": _now(),
        "commit": commit,
        "decision_log_file": str(DECISION_LOG_FILE),
        "timeline_file": str(TIMELINE_FILE),
        "effect_file": str(V2_EFFECT_FILE),
        "decisions_read": len(decisions),
        "decisions_processed": processed,
        "decisions_matched": matched,
        "decisions_unmatched": unmatched,
        "policy_events_loaded": len(policy_events),
        "old_offset": offset,
        "new_offset": new_offset,
        "reached_eof": reached_eof,
        "duration_ms": round((time.time() - started) * 1000, 2),
        "summary": effect.get("summary") or {},
    }

    try:
        with open(V2_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(result, ensure_ascii=False, sort_keys=True) + "\n")
    except Exception:
        pass

    return result


def get_executive_policy_effect_stats():
    effect = _load_effect()
    _recompute_effect_summary(effect)
    return effect


def get_executive_policy_learning_v2_health():
    state = _load_v2_state()
    effect = _load_effect()
    summary = effect.get("summary") or {}

    status = "OK"
    if not DECISION_LOG_FILE.exists():
        status = "NO_DECISION_LOG"
    elif not TIMELINE_FILE.exists():
        status = "NO_TIMELINE"
    elif _safe_int(summary.get("policy_count")) == 0:
        status = "WAITING_MATCHES"

    return {
        "ok": True,
        "module": "executive_policy_learning_v2",
        "loaded": True,
        "version": VERSION,
        "status": status,
        "decision_log_file": str(DECISION_LOG_FILE),
        "decision_log_exists": DECISION_LOG_FILE.exists(),
        "timeline_file": str(TIMELINE_FILE),
        "timeline_exists": TIMELINE_FILE.exists(),
        "state_file": str(V2_STATE_FILE),
        "effect_file": str(V2_EFFECT_FILE),
        "decision_log_offset": state.get("decision_log_offset"),
        "last_run_at": state.get("last_run_at"),
        "last_error": state.get("last_error"),
        "summary": summary,
    }


def build_executive_policy_effect_report(result=None, limit=12):
    if result is None:
        result = run_executive_policy_learning_v2(context={}, commit=True)

    effect = get_executive_policy_effect_stats()
    summary = effect.get("summary") or {}
    policies = effect.get("policies") or {}

    ranking = sorted(
        [p for p in policies.values() if isinstance(p, dict)],
        key=lambda p: (_safe_float(p.get("effect_score")), _safe_float(p.get("confidence_pct")), _safe_int(p.get("decisions"))),
        reverse=True,
    )

    lines = [
        "🧠 EXECUTIVE POLICY LEARNING V2.1.8 — POLICY EFFECT",
        f"Data/hora: {_now()}",
        "",
        f"Status: {'✅' if result.get('ok') else '❌'}",
        f"Decisões lidas agora: {result.get('decisions_read', 0)}",
        f"Decisões processadas agora: {result.get('decisions_processed', 0)}",
        f"Matches policy↔decision: {result.get('decisions_matched', 0)}",
        f"Links explícitos no decision_log: {result.get('explicit_policy_links', 0)}",
        f"Fallback via timeline: {result.get('timeline_fallback_links', 0)}",
        f"Sem policy associada: {result.get('decisions_unmatched', 0)}",
        f"Policy events carregados: {result.get('policy_events_loaded', 0)}",
        "",
        "Resumo acumulado:",
        f"- Policies com efeito medido: {summary.get('policy_count', 0)}",
        f"- Decisões correlacionadas: {summary.get('decisions_processed', 0)}",
        f"- Effect score médio: {summary.get('average_effect_score', 0)}",
        "",
    ]

    if not ranking:
        lines += [
            "Ainda não há correlação policy↔decision suficiente.",
            "",
            "Leitura:",
            "A V2.1.8 precisa de eventos no Timeline e decisões no Decision Log dentro da janela configurada.",
        ]
        return "\n".join(lines)

    lines.append("Ranking de efeito:")
    for idx, p in enumerate(ranking[:limit], start=1):
        lines += [
            f"{idx}. {p.get('code')}",
            f"- Effect Score: {p.get('effect_score')} | Confiança: {p.get('confidence_pct')}%",
            f"- Decisões: {p.get('decisions')} | ALLOW: {p.get('allow')} | DENY: {p.get('deny')} | BLOCK: {p.get('block')} | REDUCE: {p.get('reduce_size')}",
            f"- Avg risk: {p.get('avg_risk_pct')} | Avg trade score: {p.get('avg_trade_score')}",
            f"- Recomendação: {p.get('recommendation')}",
        ]
        notes = p.get("notes") or []
        if notes:
            lines.append(f"- Nota: {notes[0]}")
        lines.append("")

    lines += [
        "Observação:",
        "V2.1.8 correlaciona Timeline + Decision Log.",
        "V2.1 deve cruzar com Lifecycle/Outcome para PnL, Profit Factor e Drawdown.",
    ]
    return "\n".join(lines)


def rebuild_executive_policy_effect(commit=True, max_decisions=None):
    """
    Rebuild controlado da V2.
    Zera o offset do Decision Log e reconstrói o effect stats desde o início.

    Uso:
    - /policyeffectrebuild
    - útil depois de criar seed ou depois de corrigir timeline/decision log.
    """
    old_state = _load_v2_state()
    old_effect = _load_effect()

    if commit:
        reset_state = {
            "version": VERSION,
            "decision_log_offset": 0,
            "decisions_processed": 0,
            "last_run_at": None,
            "last_error": None,
            "rebuild_requested_at": _now(),
            "previous_offset": old_state.get("decision_log_offset"),
        }
        reset_effect = _empty_effect()
        _save_v2_state(reset_state)
        _write_json(V2_EFFECT_FILE, reset_effect)

    result = run_executive_policy_learning_v2(
        context={"rebuild": True},
        commit=commit,
        max_decisions=max_decisions or MAX_DECISIONS_PER_RUN,
    )

    result["rebuild"] = True
    result["previous_state"] = {
        "decision_log_offset": old_state.get("decision_log_offset"),
        "decisions_processed": old_state.get("decisions_processed"),
        "last_run_at": old_state.get("last_run_at"),
    }
    result["previous_summary"] = old_effect.get("summary") or {}

    return result


def build_executive_policy_effect_rebuild_report(result=None):
    if result is None:
        result = rebuild_executive_policy_effect(commit=True)

    lines = [
        "♻️ EXECUTIVE POLICY EFFECT REBUILD — CENTRAL QUANT V2.1.8",
        f"Data/hora: {_now()}",
        "",
        f"Status: {'✅' if result.get('ok') else '❌'}",
        f"Commit: {result.get('commit')}",
        f"Rebuild: {result.get('rebuild')}",
        "",
        "Antes:",
        f"- Offset anterior: {(result.get('previous_state') or {}).get('decision_log_offset')}",
        f"- Decisões processadas antes: {(result.get('previous_state') or {}).get('decisions_processed')}",
        "",
        "Reprocessamento:",
        f"- Decisões lidas: {result.get('decisions_read', 0)}",
        f"- Decisões processadas: {result.get('decisions_processed', 0)}",
        f"- Matches policy↔decision: {result.get('decisions_matched', 0)}",
        f"- Sem policy associada: {result.get('decisions_unmatched', 0)}",
        f"- Policy events carregados: {result.get('policy_events_loaded', 0)}",
        f"- Novo offset: {result.get('new_offset')}",
        "",
    ]

    summary = result.get("summary") or {}
    lines += [
        "Resumo V2:",
        f"- Policies com efeito medido: {summary.get('policy_count', 0)}",
        f"- Decisões correlacionadas: {summary.get('decisions_processed', 0)}",
        f"- Effect score médio: {summary.get('average_effect_score', 0)}",
        "",
        "Próximos comandos:",
        "/policyeffect",
        "/policycompare",
        "/policyinsights",
    ]

    return "\n".join(lines)


def build_policy_compare_report(limit=10):
    effect = get_executive_policy_effect_stats()
    policies = effect.get("policies") or {}
    ranking = sorted(
        [p for p in policies.values() if isinstance(p, dict)],
        key=lambda p: (_safe_float(p.get("effect_score")), _safe_int(p.get("decisions"))),
        reverse=True,
    )

    lines = [
        "⚖️ POLICY COMPARE — CENTRAL QUANT V2.1.8",
        f"Data/hora: {_now()}",
        "",
    ]

    if not ranking:
        lines += [
            "Sem policies suficientes para comparar.",
            "Rode /policyeffect após acumular decisões e eventos na Timeline.",
        ]
        return "\n".join(lines)

    for idx, p in enumerate(ranking[:limit], start=1):
        lines.append(
            f"{idx}. {p.get('code')} | effect={p.get('effect_score')} | conf={p.get('confidence_pct')}% | "
            f"dec={p.get('decisions')} | allow={p.get('allow')} | restrições={_safe_int(p.get('deny')) + _safe_int(p.get('block')) + _safe_int(p.get('reduce_size')) + _safe_int(p.get('no_expansion'))}"
        )

    return "\n".join(lines)


def build_policy_insights_report():
    effect = get_executive_policy_effect_stats()
    policies = effect.get("policies") or {}
    values = [p for p in policies.values() if isinstance(p, dict)]

    lines = [
        "💡 POLICY INSIGHTS — CENTRAL QUANT V2.1.8",
        f"Data/hora: {_now()}",
        "",
    ]

    if not values:
        lines += [
            "Ainda não há dados suficientes para insights.",
            "Rode /policyeffect após acumular Decision Log e Timeline.",
        ]
        return "\n".join(lines)

    best = max(values, key=lambda p: _safe_float(p.get("effect_score")))
    worst = min(values, key=lambda p: _safe_float(p.get("effect_score")))

    restrictive = sorted(
        values,
        key=lambda p: _safe_int(p.get("deny")) + _safe_int(p.get("block")) + _safe_int(p.get("reduce_size")) + _safe_int(p.get("no_expansion")),
        reverse=True,
    )

    lines += [
        f"Melhor effect score: {best.get('code')} — {best.get('effect_score')}",
        f"Menor effect score: {worst.get('code')} — {worst.get('effect_score')}",
        "",
        "Mais restritivas:",
    ]

    for p in restrictive[:5]:
        restrictions = _safe_int(p.get("deny")) + _safe_int(p.get("block")) + _safe_int(p.get("reduce_size")) + _safe_int(p.get("no_expansion"))
        lines.append(f"- {p.get('code')}: restrições={restrictions}, decisões={p.get('decisions')}, score={p.get('effect_score')}")

    lines += [
        "",
        "Leitura:",
        "Esta versão ainda não julga PnL. Ela mede influência operacional das policies nas decisões.",
    ]
    return "\n".join(lines)



# ==========================================================
# EXECUTIVE POLICY LEARNING V2.1.8 — REBUILD SAFE PATCH
# ==========================================================

def rebuild_executive_policy_effect(commit=True, max_decisions=None):
    """
    Rebuild completo da V2:
    - zera offset do decision_log da V2
    - limpa effect stats
    - reprocessa o Decision Log desde o início

    Não executa trades.
    Não altera policies.
    """
    old_state = _load_v2_state()
    old_effect = _load_effect()

    reset_state = {
        "version": VERSION,
        "decision_log_offset": 0,
        "decisions_processed": 0,
        "last_run_at": None,
        "last_error": None,
        "rebuild_requested_at": _now(),
        "previous_state": {
            "decision_log_offset": old_state.get("decision_log_offset"),
            "decisions_processed": old_state.get("decisions_processed"),
            "last_run_at": old_state.get("last_run_at"),
        },
    }

    reset_effect = _empty_effect()
    reset_effect["previous_summary"] = old_effect.get("summary") or {}

    if commit:
        _write_json(V2_STATE_FILE, reset_state)
        _write_json(V2_EFFECT_FILE, reset_effect)

    result = run_executive_policy_learning_v2(
        context={"source": "rebuild"},
        commit=commit,
        max_decisions=max_decisions or MAX_DECISIONS_PER_RUN,
    )

    result["rebuild"] = True
    result["previous_decision_log_offset"] = old_state.get("decision_log_offset")
    result["previous_summary"] = old_effect.get("summary") or {}

    try:
        with open(V2_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "event": "POLICY_EFFECT_REBUILD",
                **result,
            }, ensure_ascii=False, sort_keys=True) + "\n")
    except Exception:
        pass

    return result


def build_policy_effect_rebuild_report(result=None):
    if result is None:
        result = rebuild_executive_policy_effect(commit=True)

    lines = [
        "♻️ POLICY EFFECT REBUILD — CENTRAL QUANT V2.1.8",
        f"Data/hora: {_now()}",
        "",
        f"Status: {'✅' if result.get('ok') else '❌'}",
        f"Rebuild: {result.get('rebuild')}",
        f"Offset anterior: {result.get('previous_decision_log_offset')}",
        f"Decisões lidas: {result.get('decisions_read', 0)}",
        f"Decisões processadas: {result.get('decisions_processed', 0)}",
        f"Matches policy↔decision: {result.get('decisions_matched', 0)}",
        f"Links explícitos no decision_log: {result.get('explicit_policy_links', 0)}",
        f"Fallback via timeline: {result.get('timeline_fallback_links', 0)}",
        f"Sem policy associada: {result.get('decisions_unmatched', 0)}",
        f"Policy events carregados: {result.get('policy_events_loaded', 0)}",
        f"Novo offset: {result.get('new_offset')}",
        "",
    ]

    summary = result.get("summary") or {}
    if summary:
        lines += [
            "Resumo atual:",
            f"- Policies com efeito medido: {summary.get('policy_count', 0)}",
            f"- Decisões correlacionadas: {summary.get('decisions_processed', 0)}",
            f"- Effect score médio: {summary.get('average_effect_score', 0)}",
            "",
        ]

    lines += [
        "Leitura:",
        "O rebuild reprocessa o Decision Log desde o início para tentar associar decisões às policies da Timeline.",
        "",
        "Próximos comandos:",
        "/policyeffect",
        "/policycompare",
        "/policyinsights",
    ]

    return "\n".join(lines)


# ==========================================================
# EXECUTIVE POLICY LEARNING V2.1.8 — DECISION SEED
# ==========================================================

def seed_policy_effect_decision(commit=True):
    """
    Cria uma decisão técnica de teste no decision_log para validar:
    Timeline seed -> Decision seed -> Policy Effect match.

    Importante:
    - Possui test_seed=True.
    - Não executa trades.
    - Não altera policies reais.
    - Não cria posição.
    """
    DATA_DIR.mkdir(exist_ok=True)

    now = _now()
    seed_id = datetime.now().strftime("%Y%m%d%H%M%S")

    decision = {
        "generated_at": now,
        "created_at": now,
        "decision": "DENY",
        "action": "POLICY_EFFECT_SEED_DECISION",
        "bot": "FALCON",
        "setup": "FALCON15",
        "symbol": "BTCUSDT",
        "side": "LONG",
        "risk_pct": 1.0,
        "score": 72,
        "reason": "Seed técnico para validar correlação Policy Timeline + Decision Log.",
        "source": "executive_policy_learning_effect_seed",
        "test_seed": True,
        "seed_id": seed_id,
        "payload": {
            "decision": "DENY",
            "policy_context": ["LIMIT_NEW_LONG", "WAIT_SAMPLE"],
            "dominant_side": "LONG",
            "dominant_pct": 76.0,
        },
    }

    if commit:
        with open(DECISION_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(decision, ensure_ascii=False, sort_keys=True) + "\n")

    result = {
        "ok": True,
        "module": "executive_policy_learning_v2",
        "version": VERSION,
        "generated_at": now,
        "commit": commit,
        "seed_id": seed_id,
        "events_created": 1,
        "decision_log_file": str(DECISION_LOG_FILE),
        "decision": decision,
        "notes": [
            "Decisão seed é técnica e possui test_seed=True.",
            "Ela serve apenas para validar o match Policy Timeline ↔ Decision Log.",
            "Não executa trades e não altera policies reais.",
        ],
    }

    try:
        with open(V2_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "event": "POLICY_EFFECT_DECISION_SEED",
                **result,
            }, ensure_ascii=False, sort_keys=True) + "\n")
    except Exception:
        pass

    return result


def build_policy_effect_seed_report(result=None):
    if result is None:
        result = seed_policy_effect_decision(commit=True)

    lines = [
        "🌱 POLICY EFFECT DECISION SEED — CENTRAL QUANT V2.1.8",
        f"Data/hora: {_now()}",
        "",
        f"Status: {'✅' if result.get('ok') else '❌'}",
        f"Commit: {result.get('commit')}",
        f"Seed ID: {result.get('seed_id')}",
        f"Decisões criadas: {result.get('events_created', 0)}",
        f"Decision Log: {result.get('decision_log_file')}",
        "",
        "Decisão seed:",
        "- Decision: DENY",
        "- Bot: FALCON",
        "- Setup: FALCON15",
        "- Symbol: BTCUSDT LONG",
        "- Policy context: LIMIT_NEW_LONG + WAIT_SAMPLE",
        "",
        "Importante:",
        "- Esta decisão é técnica e possui test_seed=True.",
        "- Ela valida o pipeline; não representa decisão real.",
        "- Não executa trades e não cria posição.",
        "",
        "Próximo comando:",
        "/policyeffectrebuild",
    ]

    return "\n".join(lines)


# ==========================================================
# EXECUTIVE POLICY LEARNING V2.1.8 — READYNESS SAFE PATCH
# ==========================================================
# Esta seção sobrescreve funções da V2 sem quebrar imports/rotas existentes.
# Objetivo:
# - manter /policylearning, /policyeffect, /policycompare e /policyinsights;
# - ignorar seeds técnicos em métricas reais;
# - adicionar readiness_label / ready_to_learn por policy;
# - continuar 100% observacional, sem execução real e sem alterar policies.

VERSION = "2026-07-05-EXECUTIVE-POLICY-LEARNING-V2.1.8"
MIN_REAL_DECISIONS_FOR_LEARNING = int(os.environ.get("EXECUTIVE_POLICY_LEARNING_MIN_REAL_DECISIONS", "10"))
MIN_READY_DECISIONS_FOR_POLICY = int(os.environ.get("EXECUTIVE_POLICY_LEARNING_MIN_READY_DECISIONS", "20"))


def _is_test_seed_event(item):
    if not isinstance(item, dict):
        return False

    candidates = [
        item.get("test_seed"),
        item.get("is_seed"),
        item.get("seed"),
    ]

    payload = item.get("payload")
    if isinstance(payload, dict):
        candidates.extend([
            payload.get("test_seed"),
            payload.get("is_seed"),
            payload.get("seed"),
        ])

    meta = item.get("meta")
    if isinstance(meta, dict):
        candidates.extend([
            meta.get("test_seed"),
            meta.get("is_seed"),
            meta.get("seed"),
        ])

    return any(v is True or str(v).strip().lower() == "true" for v in candidates)


def _extract_decision_outcome(decision):
    if not isinstance(decision, dict):
        return None

    payload = decision.get("payload") if isinstance(decision.get("payload"), dict) else {}
    trade = decision.get("trade") if isinstance(decision.get("trade"), dict) else {}

    for source in [decision, trade, payload]:
        if not isinstance(source, dict):
            continue
        for key in ["outcome", "result_outcome", "trade_outcome", "closed_result", "pnl_result", "lifecycle_outcome"]:
            value = source.get(key)
            if value not in (None, ""):
                return str(value).strip().upper()
    return None


def _read_all_policy_events_light(limit=5000):
    """
    V2.1.8: lê eventos reais da timeline para correlação com Decision Log.
    Seeds técnicos são ignorados para não contaminar readiness real.
    """
    if not TIMELINE_FILE.exists():
        return []

    events = []
    skipped_test_seeds = 0
    try:
        with open(TIMELINE_FILE, "rb") as f:
            try:
                f.seek(0, os.SEEK_END)
                size = f.tell()
                max_bytes = 1024 * 1024
                if size > max_bytes:
                    f.seek(size - max_bytes)
                    f.readline()
                else:
                    f.seek(0)
            except Exception:
                f.seek(0)

            for line in f:
                if len(events) >= limit:
                    break
                try:
                    item = json.loads(line.decode("utf-8").strip())
                    if not isinstance(item, dict):
                        continue
                    if _is_test_seed_event(item):
                        skipped_test_seeds += 1
                        continue
                    code = _extract_code(item)
                    dt = _event_time(item)
                    if code and dt:
                        events.append({
                            "code": code,
                            "dt": dt,
                            "event_type": _extract_event_type(item),
                            "test_seed": False,
                            "reason": item.get("reason") or item.get("rationale") or "",
                        })
                except Exception:
                    continue
    except Exception:
        return []

    events.sort(key=lambda x: x.get("dt"))
    # A lista continua sendo lista simples para compatibilidade.
    # O contador de seeds puladas aparece no result do run_v2.
    try:
        _read_all_policy_events_light.last_skipped_test_seeds = skipped_test_seeds
    except Exception:
        pass
    return events


def _effect_policy_template(code):
    return {
        "code": code,
        "first_seen_at": None,
        "last_seen_at": None,
        "decisions": 0,
        "real_decisions": 0,
        "test_decisions": 0,
        "outcomes_detected": 0,
        "allow": 0,
        "deny": 0,
        "block": 0,
        "reduce_size": 0,
        "no_expansion": 0,
        "unknown": 0,
        "by_bot": {},
        "by_side": {},
        "by_symbol": {},
        "risk_pct_total": 0.0,
        "score_total": 0.0,
        "avg_risk_pct": 0.0,
        "avg_trade_score": 0.0,
        "effect_score": 50.0,
        "confidence_pct": 0.0,
        "readiness_score": 0.0,
        "readiness_label": "WAIT_SAMPLE",
        "ready_to_learn": False,
        "recommendation": "OBSERVAR",
        "notes": [],
    }


def _apply_decision_to_effect(policy, decision):
    dt = _decision_time(decision)
    dt_txt = dt.strftime("%d/%m/%Y %H:%M:%S") if dt else _now()
    if not policy.get("first_seen_at"):
        policy["first_seen_at"] = dt_txt
    policy["last_seen_at"] = dt_txt

    decision_name = _extract_decision(decision)
    fields = _extract_trade_fields(decision)
    outcome = _extract_decision_outcome(decision)

    policy["decisions"] = _safe_int(policy.get("decisions")) + 1
    policy["real_decisions"] = _safe_int(policy.get("real_decisions")) + 1
    if outcome:
        policy["outcomes_detected"] = _safe_int(policy.get("outcomes_detected")) + 1

    d = decision_name
    if "ALLOW" in d:
        policy["allow"] = _safe_int(policy.get("allow")) + 1
    elif "DENY" in d:
        policy["deny"] = _safe_int(policy.get("deny")) + 1
    elif "BLOCK" in d:
        policy["block"] = _safe_int(policy.get("block")) + 1
    elif "REDUCE" in d:
        policy["reduce_size"] = _safe_int(policy.get("reduce_size")) + 1
    elif "NO_EXPANSION" in d or "NO EXPANSION" in d:
        policy["no_expansion"] = _safe_int(policy.get("no_expansion")) + 1
    else:
        policy["unknown"] = _safe_int(policy.get("unknown")) + 1

    _update_counter_map(policy.setdefault("by_bot", {}), fields.get("bot"))
    _update_counter_map(policy.setdefault("by_side", {}), fields.get("side"))
    _update_counter_map(policy.setdefault("by_symbol", {}), fields.get("symbol"))

    policy["risk_pct_total"] = round(_safe_float(policy.get("risk_pct_total")) + _safe_float(fields.get("risk_pct")), 6)
    policy["score_total"] = round(_safe_float(policy.get("score_total")) + _safe_float(fields.get("score")), 6)

    decisions = max(1, _safe_int(policy.get("decisions")))
    policy["avg_risk_pct"] = round(_safe_float(policy.get("risk_pct_total")) / decisions, 4)
    policy["avg_trade_score"] = round(_safe_float(policy.get("score_total")) / decisions, 4)

    _score_effect_policy(policy)




# ==========================================================
# EXECUTIVE POLICY LEARNING V2.2.2.1 — READINESS HOTFIX
# ==========================================================
# Corrige dependência auxiliar usada pela V2.2.
# Mantém a mesma semântica da V2.1.8: readiness é observacional
# e não altera execução, risco, lote ou policies ativas.

def _compute_policy_readiness(policy):
    """Calcula readiness por policy com base em decisões reais e outcomes detectados."""
    if not isinstance(policy, dict):
        return policy

    decisions = _safe_int(policy.get("decisions"))
    real_decisions = _safe_int(policy.get("real_decisions"), decisions)
    outcomes = _safe_int(policy.get("outcomes_detected", policy.get("outcomes", 0)))

    readiness_score = min(
        100.0,
        (real_decisions / max(1, MIN_REAL_DECISIONS_FOR_LEARNING)) * 70.0
        + min(30.0, outcomes * 6.0),
    )

    if real_decisions < MIN_REAL_DECISIONS_FOR_LEARNING:
        readiness_label = "WAIT_SAMPLE"
        ready_to_learn = False
        readiness_note = f"Amostra real insuficiente: {real_decisions}/{MIN_REAL_DECISIONS_FOR_LEARNING} decisões reais."
    elif real_decisions < MIN_READY_DECISIONS_FOR_POLICY:
        readiness_label = "LEARN_WITH_CAUTION"
        ready_to_learn = True
        readiness_note = f"Policy pode aprender com cautela: {real_decisions}/{MIN_READY_DECISIONS_FOR_POLICY} decisões reais."
    else:
        readiness_label = "READY_TO_LEARN"
        ready_to_learn = True
        readiness_note = "Policy atingiu amostra mínima para aprendizado executivo controlado."

    policy["readiness_score"] = round(readiness_score, 2)
    policy["readiness_label"] = readiness_label
    policy["ready_to_learn"] = ready_to_learn

    notes = policy.get("notes") if isinstance(policy.get("notes"), list) else []
    if readiness_note not in notes:
        notes.insert(0, readiness_note)
    policy["notes"] = notes[-8:]
    return policy

def _score_effect_policy(policy):
    decisions = _safe_int(policy.get("decisions"))
    real_decisions = _safe_int(policy.get("real_decisions"), decisions)
    outcomes = _safe_int(policy.get("outcomes_detected"))
    allow = _safe_int(policy.get("allow"))
    deny = _safe_int(policy.get("deny"))
    block = _safe_int(policy.get("block"))
    reduce_size = _safe_int(policy.get("reduce_size"))
    no_expansion = _safe_int(policy.get("no_expansion"))

    restrictions = deny + block + reduce_size + no_expansion

    sample_score = min(30.0, real_decisions * 2.0)
    protection_score = min(30.0, restrictions * 4.0)
    operation_score = min(20.0, allow * 2.0)
    outcome_score = min(10.0, outcomes * 2.0)
    balance_score = 10.0

    if real_decisions >= 10 and allow >= real_decisions * 0.9 and restrictions == 0:
        balance_score = 4.0

    if real_decisions >= 10 and allow == 0 and (deny + block) >= real_decisions * 0.9:
        balance_score = 5.0

    score = max(0.0, min(100.0, sample_score + protection_score + operation_score + outcome_score + balance_score))
    confidence = min(100.0, (real_decisions / max(1, MIN_READY_DECISIONS_FOR_POLICY)) * 100.0)

    readiness_score = min(100.0, (real_decisions / max(1, MIN_REAL_DECISIONS_FOR_LEARNING)) * 70.0 + min(30.0, outcomes * 6.0))

    if real_decisions < MIN_REAL_DECISIONS_FOR_LEARNING:
        readiness_label = "WAIT_SAMPLE"
        ready_to_learn = False
        recommendation = "AGUARDAR_AMOSTRA"
    elif real_decisions < MIN_READY_DECISIONS_FOR_POLICY:
        readiness_label = "LEARN_WITH_CAUTION"
        ready_to_learn = True
        recommendation = "OBSERVAR"
    else:
        readiness_label = "READY_TO_LEARN"
        ready_to_learn = True
        if score >= 80:
            recommendation = "MANTER"
        elif score >= 60:
            recommendation = "OBSERVAR"
        elif score >= 45:
            recommendation = "REVISAR"
        else:
            recommendation = "ENFRAQUECER_OU_APOSENTAR"

    notes = []
    if real_decisions < MIN_REAL_DECISIONS_FOR_LEARNING:
        notes.append(f"Amostra real insuficiente: {real_decisions}/{MIN_REAL_DECISIONS_FOR_LEARNING} decisões reais.")
    elif real_decisions < MIN_READY_DECISIONS_FOR_POLICY:
        notes.append(f"Policy pode aprender com cautela: {real_decisions}/{MIN_READY_DECISIONS_FOR_POLICY} decisões reais.")
    else:
        notes.append("Policy atingiu amostra mínima para aprendizado executivo controlado.")
    if outcomes == 0:
        notes.append("Ainda sem outcome/lifecycle confirmado; não usar para PnL real.")
    if restrictions > 0:
        notes.append("Policy influenciou restrição/controle de risco em decisões reais.")
    if allow > 0:
        notes.append("Policy também conviveu com decisões permitidas.")
    if real_decisions >= 10 and allow == 0:
        notes.append("Policy altamente restritiva; revisar impacto financeiro antes de automatizar.")
    if real_decisions >= 10 and allow >= real_decisions * 0.9:
        notes.append("Policy pouco restritiva; revisar se agrega proteção real.")

    policy["effect_score"] = round(score, 2)
    policy["confidence_pct"] = round(confidence, 2)
    policy["readiness_score"] = round(readiness_score, 2)
    policy["readiness_label"] = readiness_label
    policy["ready_to_learn"] = ready_to_learn
    policy["recommendation"] = recommendation
    policy["notes"] = notes[-6:]


def _recompute_effect_summary(effect):
    policies = effect.get("policies") or {}
    values = [p for p in policies.values() if isinstance(p, dict)]

    total_decisions = sum(_safe_int(p.get("decisions")) for p in values)
    total_real_decisions = sum(_safe_int(p.get("real_decisions"), _safe_int(p.get("decisions"))) for p in values)
    total_outcomes = sum(_safe_int(p.get("outcomes_detected")) for p in values)
    avg = 0.0
    if values:
        avg = sum(_safe_float(p.get("effect_score")) for p in values) / len(values)

    effect["summary"] = {
        "policy_count": len(values),
        "decisions_processed": total_decisions,
        "real_decisions_processed": total_real_decisions,
        "decisions_matched": total_decisions,
        "decisions_unmatched": effect.get("summary", {}).get("decisions_unmatched", 0),
        "outcomes_detected": total_outcomes,
        "ready_to_learn_count": sum(1 for p in values if p.get("readiness_label") == "READY_TO_LEARN"),
        "learn_with_caution_count": sum(1 for p in values if p.get("readiness_label") == "LEARN_WITH_CAUTION"),
        "wait_sample_count": sum(1 for p in values if p.get("readiness_label") == "WAIT_SAMPLE"),
        "average_effect_score": round(avg, 2),
        "updated_at": _now(),
    }


def run_executive_policy_learning_v2(context=None, commit=True, max_decisions=None):
    """
    V2.1.8:
    Lê decisões novas do decision_log e associa às policies ativas reais da timeline.
    Ignora seeds técnicos para readiness real.
    Não calcula PnL ainda e não altera policies/execução.
    """
    started = time.time()
    state = _load_v2_state()
    effect = _load_effect()

    offset = _safe_int(state.get("decision_log_offset"), 0)
    max_decisions = int(max_decisions or MAX_DECISIONS_PER_RUN)

    decisions, new_offset, reached_eof = _read_new_jsonl(DECISION_LOG_FILE, offset, max_decisions)
    policy_events = _read_all_policy_events_light()
    timeline_seeds_skipped = getattr(_read_all_policy_events_light, "last_skipped_test_seeds", 0)

    processed = 0
    matched = 0
    unmatched = 0
    test_decisions_skipped = 0
    explicit_policy_links = 0
    timeline_fallback_links = 0

    policies = effect.setdefault("policies", {})

    for decision in decisions:
        if _is_test_seed_event(decision):
            test_decisions_skipped += 1
            continue

        explicit_codes = _decision_policy_codes(decision)
        dt = _decision_time(decision)
        codes = explicit_codes or _active_policy_codes_for_decision(dt, policy_events)

        if not codes:
            unmatched += 1
            processed += 1
            continue

        if explicit_codes:
            explicit_policy_links += 1
        else:
            timeline_fallback_links += 1

        for code in codes:
            policy = policies.get(code)
            if not isinstance(policy, dict):
                policy = _effect_policy_template(code)
                policies[code] = policy
            _apply_decision_to_effect(policy, decision)
            matched += 1

        processed += 1

    # Mantém informação de unmatched no summary sem depender de reprocessamento completo.
    prior_summary = effect.get("summary") if isinstance(effect.get("summary"), dict) else {}
    prior_unmatched = _safe_int(prior_summary.get("decisions_unmatched"))
    effect.setdefault("summary", {})["decisions_unmatched"] = prior_unmatched + unmatched

    state["decision_log_offset"] = new_offset
    state["last_run_at"] = _now()
    state["last_error"] = None
    state["decisions_processed"] = _safe_int(state.get("decisions_processed")) + processed
    state["last_batch"] = {
        "decisions_read": len(decisions),
        "decisions_processed": processed,
        "decisions_matched": matched,
        "decisions_unmatched": unmatched,
        "test_decisions_skipped": test_decisions_skipped,
        "explicit_policy_links": explicit_policy_links,
        "timeline_fallback_links": timeline_fallback_links,
        "timeline_test_seeds_skipped": timeline_seeds_skipped,
        "policy_events_loaded": len(policy_events),
        "old_offset": offset,
        "new_offset": new_offset,
        "reached_eof": reached_eof,
    }

    if commit:
        _save_effect(effect)
        _save_v2_state(state)
    else:
        _recompute_effect_summary(effect)

    result = {
        "ok": True,
        "module": "executive_policy_learning_v2",
        "version": VERSION,
        "generated_at": _now(),
        "commit": commit,
        "decision_log_file": str(DECISION_LOG_FILE),
        "timeline_file": str(TIMELINE_FILE),
        "effect_file": str(V2_EFFECT_FILE),
        "decisions_read": len(decisions),
        "decisions_processed": processed,
        "decisions_matched": matched,
        "decisions_unmatched": unmatched,
        "test_decisions_skipped": test_decisions_skipped,
        "explicit_policy_links": explicit_policy_links,
        "timeline_fallback_links": timeline_fallback_links,
        "timeline_test_seeds_skipped": timeline_seeds_skipped,
        "policy_events_loaded": len(policy_events),
        "old_offset": offset,
        "new_offset": new_offset,
        "reached_eof": reached_eof,
        "duration_ms": round((time.time() - started) * 1000, 2),
        "summary": effect.get("summary") or {},
        "notes": [
            "V2.1.8 usa policy_codes explícitos do decision_log quando disponíveis.",
            "Seeds técnicos são ignorados nas métricas reais.",
            "READY_TO_LEARN é consultivo e não libera execução automática.",
            "PnL real ainda depende de Lifecycle/Outcome em etapa futura.",
        ],
    }

    try:
        with open(V2_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(result, ensure_ascii=False, sort_keys=True) + "\n")
    except Exception:
        pass

    return result


def get_executive_policy_effect_stats():
    effect = _load_effect()
    effect["version"] = VERSION
    _recompute_effect_summary(effect)
    return effect


def get_executive_policy_learning_v2_health():
    state = _load_v2_state()
    effect = _load_effect()
    _recompute_effect_summary(effect)
    summary = effect.get("summary") or {}

    status = "OK"
    if not DECISION_LOG_FILE.exists():
        status = "NO_DECISION_LOG"
    elif not TIMELINE_FILE.exists():
        status = "NO_TIMELINE"
    elif _safe_int(summary.get("policy_count")) == 0:
        status = "WAITING_MATCHES"
    elif _safe_int(summary.get("wait_sample_count")) > 0 and _safe_int(summary.get("ready_to_learn_count")) == 0:
        status = "WAIT_SAMPLE"

    return {
        "ok": True,
        "module": "executive_policy_learning_v2",
        "loaded": True,
        "version": VERSION,
        "status": status,
        "decision_log_file": str(DECISION_LOG_FILE),
        "decision_log_exists": DECISION_LOG_FILE.exists(),
        "timeline_file": str(TIMELINE_FILE),
        "timeline_exists": TIMELINE_FILE.exists(),
        "state_file": str(V2_STATE_FILE),
        "effect_file": str(V2_EFFECT_FILE),
        "decision_log_offset": state.get("decision_log_offset"),
        "last_run_at": state.get("last_run_at"),
        "last_error": state.get("last_error"),
        "summary": summary,
        "notes": [
            "Health V2.1.8 separa amostra real de seeds técnicos.",
            "WAIT_SAMPLE não é erro; indica que a Central ainda precisa de decisões reais.",
        ],
    }


def build_executive_policy_effect_report(result=None, limit=12):
    if result is None:
        result = run_executive_policy_learning_v2(context={}, commit=True)

    effect = get_executive_policy_effect_stats()
    summary = effect.get("summary") or {}
    policies = effect.get("policies") or {}

    ranking = sorted(
        [p for p in policies.values() if isinstance(p, dict)],
        key=lambda p: (_safe_float(p.get("readiness_score")), _safe_float(p.get("effect_score")), _safe_float(p.get("confidence_pct")), _safe_int(p.get("decisions"))),
        reverse=True,
    )

    lines = [
        "🧠 EXECUTIVE POLICY LEARNING V2.1.8 — POLICY EFFECT",
        f"Data/hora: {_now()}",
        "",
        f"Status: {'✅' if result.get('ok') else '❌'}",
        f"Decisões lidas agora: {result.get('decisions_read', 0)}",
        f"Decisões reais processadas agora: {result.get('decisions_processed', 0)}",
        f"Matches policy↔decision: {result.get('decisions_matched', 0)}",
        f"Links explícitos no decision_log: {result.get('explicit_policy_links', 0)}",
        f"Fallback via timeline: {result.get('timeline_fallback_links', 0)}",
        f"Sem policy associada: {result.get('decisions_unmatched', 0)}",
        f"Seeds decision ignorados: {result.get('test_decisions_skipped', 0)}",
        f"Seeds timeline ignorados: {result.get('timeline_test_seeds_skipped', 0)}",
        f"Policy events reais carregados: {result.get('policy_events_loaded', 0)}",
        "",
        "Resumo acumulado:",
        f"- Policies com efeito medido: {summary.get('policy_count', 0)}",
        f"- Decisões reais correlacionadas: {summary.get('real_decisions_processed', summary.get('decisions_processed', 0))}",
        f"- Outcomes detectados: {summary.get('outcomes_detected', 0)}",
        f"- READY_TO_LEARN: {summary.get('ready_to_learn_count', 0)}",
        f"- LEARN_WITH_CAUTION: {summary.get('learn_with_caution_count', 0)}",
        f"- WAIT_SAMPLE: {summary.get('wait_sample_count', 0)}",
        f"- Effect score médio: {summary.get('average_effect_score', 0)}",
        "",
    ]

    if not ranking:
        lines += [
            "Ainda não há correlação real policy↔decision suficiente.",
            "",
            "Leitura:",
            "A V2.1.8 precisa de eventos reais no Timeline e decisões reais no Decision Log dentro da janela configurada.",
            "Seeds técnicos são ignorados para não contaminar o aprendizado real.",
        ]
        return "\n".join(lines)

    lines.append("Ranking de readiness/efeito:")
    for idx, p in enumerate(ranking[:limit], start=1):
        lines += [
            f"{idx}. {p.get('code')}",
            f"- Readiness: {p.get('readiness_label')} | score={p.get('readiness_score')} | ready={p.get('ready_to_learn')}",
            f"- Effect Score: {p.get('effect_score')} | Confiança: {p.get('confidence_pct')}%",
            f"- Decisões reais: {p.get('real_decisions', p.get('decisions'))} | ALLOW: {p.get('allow')} | DENY: {p.get('deny')} | BLOCK: {p.get('block')} | REDUCE: {p.get('reduce_size')}",
            f"- Avg risk: {p.get('avg_risk_pct')} | Avg trade score: {p.get('avg_trade_score')}",
            f"- Recomendação: {p.get('recommendation')}",
        ]
        notes = p.get("notes") or []
        if notes:
            lines.append(f"- Nota: {notes[0]}")
        lines.append("")

    lines += [
        "Observação:",
        "V2.1.8 é observacional, ignora seeds técnicos e separa readiness real de validação de pipeline.",
        "READY_TO_LEARN não altera execução real; apenas indica que a policy já tem amostra mínima para aprendizado controlado.",
        "A próxima etapa deve cruzar com Lifecycle/Outcome para PnL, Profit Factor e Drawdown.",
    ]
    return "\n".join(lines)


def build_policy_compare_report(limit=10):
    effect = get_executive_policy_effect_stats()
    policies = effect.get("policies") or {}
    ranking = sorted(
        [p for p in policies.values() if isinstance(p, dict)],
        key=lambda p: (_safe_float(p.get("readiness_score")), _safe_float(p.get("effect_score")), _safe_int(p.get("real_decisions", p.get("decisions")))),
        reverse=True,
    )

    lines = [
        "⚖️ POLICY COMPARE — CENTRAL QUANT V2.1.8",
        f"Data/hora: {_now()}",
        "",
    ]

    if not ranking:
        lines += [
            "Sem policies reais suficientes para comparar.",
            "Rode /policyeffect após acumular decisões reais e eventos reais na Timeline.",
        ]
        return "\n".join(lines)

    for idx, p in enumerate(ranking[:limit], start=1):
        restrictions = _safe_int(p.get("deny")) + _safe_int(p.get("block")) + _safe_int(p.get("reduce_size")) + _safe_int(p.get("no_expansion"))
        lines.append(
            f"{idx}. {p.get('code')} | readiness={p.get('readiness_label')}({p.get('readiness_score')}) | "
            f"effect={p.get('effect_score')} | conf={p.get('confidence_pct')}% | "
            f"dec_reais={p.get('real_decisions', p.get('decisions'))} | allow={p.get('allow')} | restrições={restrictions}"
        )

    return "\n".join(lines)


def build_policy_insights_report():
    effect = get_executive_policy_effect_stats()
    policies = effect.get("policies") or {}
    values = [p for p in policies.values() if isinstance(p, dict)]

    lines = [
        "💡 POLICY INSIGHTS — CENTRAL QUANT V2.1.8",
        f"Data/hora: {_now()}",
        "",
    ]

    if not values:
        lines += [
            "Ainda não há dados reais suficientes para insights.",
            "Rode /policyeffect após acumular Decision Log real e Timeline real.",
        ]
        return "\n".join(lines)

    best = max(values, key=lambda p: _safe_float(p.get("effect_score")))
    worst = min(values, key=lambda p: _safe_float(p.get("effect_score")))
    ready = [p for p in values if p.get("readiness_label") == "READY_TO_LEARN"]
    caution = [p for p in values if p.get("readiness_label") == "LEARN_WITH_CAUTION"]
    wait = [p for p in values if p.get("readiness_label") == "WAIT_SAMPLE"]

    restrictive = sorted(
        values,
        key=lambda p: _safe_int(p.get("deny")) + _safe_int(p.get("block")) + _safe_int(p.get("reduce_size")) + _safe_int(p.get("no_expansion")),
        reverse=True,
    )

    lines += [
        f"READY_TO_LEARN: {len(ready)}",
        f"LEARN_WITH_CAUTION: {len(caution)}",
        f"WAIT_SAMPLE: {len(wait)}",
        "",
        f"Melhor effect score: {best.get('code')} — {best.get('effect_score')}",
        f"Menor effect score: {worst.get('code')} — {worst.get('effect_score')}",
        "",
        "Mais restritivas:",
    ]

    for p in restrictive[:5]:
        restrictions = _safe_int(p.get("deny")) + _safe_int(p.get("block")) + _safe_int(p.get("reduce_size")) + _safe_int(p.get("no_expansion"))
        lines.append(f"- {p.get('code')}: restrições={restrictions}, decisões reais={p.get('real_decisions', p.get('decisions'))}, readiness={p.get('readiness_label')}, score={p.get('effect_score')}")

    lines += [
        "",
        "Leitura:",
        "Esta versão ainda não julga PnL. Ela mede influência operacional real das policies nas decisões e separa seeds técnicos.",
    ]
    return "\n".join(lines)



# ==========================================================
# EXECUTIVE POLICY LEARNING V2.1.8 — POLICY LINK RECOGNITION PATCH
# ==========================================================
# Correções principais:
# - aceita policy_context como vínculo explícito;
# - aceita policy_context dentro de payload/trade/policy_linker/executive_policy;
# - mantém contadores explicit_policy_links e timeline_fallback_links no result;
# - preserva compatibilidade com /policylearning, /policyeffect,
#   /policyeffectrebuild, /policycompare e /policyinsights;
# - continua 100% observacional: não executa trades e não altera policies.


if __name__ == "__main__":
    print(build_executive_policy_learning_report())



# ==========================================================
# EXECUTIVE POLICY LEARNING V2.1.8 — DECISION LOG SOURCE RESOLVER
# ==========================================================
# Correção incremental da V2.1.8:
# - Detecta automaticamente o maior/mais completo decision_log disponível.
# - Evita o bug onde /policyeffect lia apenas 1 decisão enquanto /decisionlog mostrava várias.
# - Mantém compatibilidade com CENTRAL_DECISION_LOG_FILE.
# - Continua 100% observacional.

VERSION = "2026-07-05-EXECUTIVE-POLICY-LEARNING-V2.1.8"


def _jsonl_line_count(path):
    try:
        path = Path(path)
        if not path.exists():
            return 0
        with open(path, "r", encoding="utf-8") as f:
            return sum(1 for line in f if line.strip())
    except Exception:
        return 0


def _decision_log_candidate_paths():
    candidates = []

    def add(value):
        try:
            if value is None:
                return
            p = Path(str(value))
            if p not in candidates:
                candidates.append(p)
        except Exception:
            pass

    # Fonte padrão do módulo.
    add(DECISION_LOG_FILE)

    # Variáveis de ambiente possíveis.
    for env_name in [
        "CENTRAL_DECISION_LOG_FILE",
        "HISTORY_DECISION_LOG_FILE",
        "DECISION_LOG_FILE",
        "CENTRAL_DATA_DIR",
    ]:
        value = os.environ.get(env_name)
        if not value:
            continue
        if env_name.endswith("DATA_DIR"):
            add(Path(value) / "decision_log.jsonl")
        else:
            add(value)

    # Caminhos prováveis dentro do projeto.
    add(DATA_DIR / "decision_log.jsonl")
    add(BASE_DIR / "data" / "decision_log.jsonl")
    add(Path("/opt/render/project/src/data/decision_log.jsonl"))

    # History Manager pode manter um decision log próprio.
    try:
        import history_manager as super_history_manager
        add(getattr(super_history_manager, "DECISION_LOG_FILE", None))
        add(getattr(super_history_manager, "CENTRAL_DECISION_LOG_FILE", None))
        add(getattr(super_history_manager, "HISTORY_DECISION_LOG_FILE", None))
        history_data_dir = getattr(super_history_manager, "DATA_DIR", None)
        if history_data_dir:
            add(Path(history_data_dir) / "decision_log.jsonl")
    except Exception:
        pass

    # Remove duplicados e inexistentes depois.
    out = []
    seen = set()
    for p in candidates:
        key = str(p)
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def _resolve_decision_log_file():
    """
    Escolhe o decision_log mais completo.
    Prioridade prática: maior quantidade de linhas JSONL válidas/registradas.
    Isso evita ler um arquivo pequeno de teste enquanto /decisionlog mostra outro log maior.
    """
    candidates = _decision_log_candidate_paths()
    scored = []
    for path in candidates:
        count = _jsonl_line_count(path)
        exists = Path(path).exists()
        scored.append({
            "path": str(path),
            "exists": bool(exists),
            "line_count": int(count),
        })

    valid = [item for item in scored if item.get("exists") and item.get("line_count", 0) > 0]
    if not valid:
        chosen = str(DECISION_LOG_FILE)
    else:
        valid.sort(key=lambda x: (x.get("line_count", 0), x.get("path") == str(DECISION_LOG_FILE)), reverse=True)
        chosen = valid[0]["path"]

    try:
        _resolve_decision_log_file.last_candidates = scored
        _resolve_decision_log_file.last_chosen = chosen
    except Exception:
        pass

    return Path(chosen)


def run_executive_policy_learning_v2(context=None, commit=True, max_decisions=None):
    """
    V2.1.8:
    Lê decisões novas do decision_log resolvido automaticamente.
    Associa por links explícitos quando existirem e por timeline como fallback.
    Ignora seeds técnicos para readiness real.
    """
    started = time.time()
    state = _load_v2_state()
    effect = _load_effect()

    decision_log_path = _resolve_decision_log_file()
    decision_log_candidates = getattr(_resolve_decision_log_file, "last_candidates", [])

    previous_path = state.get("decision_log_file")
    if previous_path and str(previous_path) != str(decision_log_path):
        # Se a fonte mudou, não reutiliza offset de outro arquivo.
        offset = 0
    else:
        offset = _safe_int(state.get("decision_log_offset"), 0)

    max_decisions = int(max_decisions or MAX_DECISIONS_PER_RUN)

    decisions, new_offset, reached_eof = _read_new_jsonl(decision_log_path, offset, max_decisions)
    policy_events = _read_all_policy_events_light()
    timeline_seeds_skipped = getattr(_read_all_policy_events_light, "last_skipped_test_seeds", 0)

    processed = 0
    matched = 0
    unmatched = 0
    test_decisions_skipped = 0
    explicit_policy_links = 0
    timeline_fallback_links = 0

    policies = effect.setdefault("policies", {})

    for decision in decisions:
        if _is_test_seed_event(decision):
            test_decisions_skipped += 1
            continue

        explicit_codes = _decision_policy_codes(decision)
        dt = _decision_time(decision)
        codes = explicit_codes or _active_policy_codes_for_decision(dt, policy_events)

        if not codes:
            unmatched += 1
            processed += 1
            continue

        if explicit_codes:
            explicit_policy_links += 1
        else:
            timeline_fallback_links += 1

        for code in codes:
            policy = policies.get(code)
            if not isinstance(policy, dict):
                policy = _effect_policy_template(code)
                policies[code] = policy
            _apply_decision_to_effect(policy, decision)
            matched += 1

        processed += 1

    prior_summary = effect.get("summary") if isinstance(effect.get("summary"), dict) else {}
    prior_unmatched = _safe_int(prior_summary.get("decisions_unmatched"))
    effect.setdefault("summary", {})["decisions_unmatched"] = prior_unmatched + unmatched

    state["decision_log_file"] = str(decision_log_path)
    state["decision_log_candidates"] = decision_log_candidates
    state["decision_log_offset"] = new_offset
    state["last_run_at"] = _now()
    state["last_error"] = None
    state["decisions_processed"] = _safe_int(state.get("decisions_processed")) + processed
    state["last_batch"] = {
        "decisions_read": len(decisions),
        "decisions_processed": processed,
        "decisions_matched": matched,
        "decisions_unmatched": unmatched,
        "test_decisions_skipped": test_decisions_skipped,
        "explicit_policy_links": explicit_policy_links,
        "timeline_fallback_links": timeline_fallback_links,
        "timeline_test_seeds_skipped": timeline_seeds_skipped,
        "policy_events_loaded": len(policy_events),
        "decision_log_file": str(decision_log_path),
        "decision_log_candidates": decision_log_candidates,
        "old_offset": offset,
        "new_offset": new_offset,
        "reached_eof": reached_eof,
    }

    if commit:
        _save_effect(effect)
        _save_v2_state(state)
    else:
        _recompute_effect_summary(effect)

    result = {
        "ok": True,
        "module": "executive_policy_learning_v2",
        "version": VERSION,
        "generated_at": _now(),
        "commit": commit,
        "decision_log_file": str(decision_log_path),
        "decision_log_candidates": decision_log_candidates,
        "timeline_file": str(TIMELINE_FILE),
        "effect_file": str(V2_EFFECT_FILE),
        "decisions_read": len(decisions),
        "decisions_processed": processed,
        "decisions_matched": matched,
        "decisions_unmatched": unmatched,
        "test_decisions_skipped": test_decisions_skipped,
        "explicit_policy_links": explicit_policy_links,
        "timeline_fallback_links": timeline_fallback_links,
        "timeline_test_seeds_skipped": timeline_seeds_skipped,
        "policy_events_loaded": len(policy_events),
        "old_offset": offset,
        "new_offset": new_offset,
        "reached_eof": reached_eof,
        "duration_ms": round((time.time() - started) * 1000, 2),
        "summary": effect.get("summary") or {},
        "notes": [
            "V2.1.8 escolhe automaticamente o decision_log mais completo.",
            "Se a fonte do log mudar, o offset é reiniciado com segurança.",
            "Seeds técnicos são ignorados nas métricas reais.",
            "PnL real ainda depende de Lifecycle/Outcome em etapa futura.",
        ],
    }

    try:
        with open(V2_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(result, ensure_ascii=False, sort_keys=True) + "\n")
    except Exception:
        pass

    return result


def get_executive_policy_learning_v2_health():
    state = _load_v2_state()
    effect = _load_effect()
    _recompute_effect_summary(effect)
    summary = effect.get("summary") or {}
    decision_log_path = _resolve_decision_log_file()

    status = "OK"
    if not decision_log_path.exists():
        status = "NO_DECISION_LOG"
    elif not TIMELINE_FILE.exists():
        status = "NO_TIMELINE"
    elif _safe_int(summary.get("policy_count")) == 0:
        status = "WAITING_MATCHES"
    elif _safe_int(summary.get("wait_sample_count")) > 0 and _safe_int(summary.get("ready_to_learn_count")) == 0:
        status = "WAIT_SAMPLE"

    return {
        "ok": True,
        "module": "executive_policy_learning_v2",
        "loaded": True,
        "version": VERSION,
        "status": status,
        "decision_log_file": str(decision_log_path),
        "decision_log_candidates": getattr(_resolve_decision_log_file, "last_candidates", []),
        "decision_log_exists": decision_log_path.exists(),
        "timeline_file": str(TIMELINE_FILE),
        "timeline_exists": TIMELINE_FILE.exists(),
        "state_file": str(V2_STATE_FILE),
        "effect_file": str(V2_EFFECT_FILE),
        "decision_log_offset": state.get("decision_log_offset"),
        "last_run_at": state.get("last_run_at"),
        "last_error": state.get("last_error"),
        "summary": summary,
    }


def rebuild_executive_policy_effect(commit=True, max_decisions=None):
    """
    V2.1.8 rebuild:
    Zera offset e effect stats, resolve o decision_log mais completo e reprocessa desde o início.
    """
    old_state = _load_v2_state()
    old_effect = _load_effect()

    decision_log_path = _resolve_decision_log_file()
    decision_log_candidates = getattr(_resolve_decision_log_file, "last_candidates", [])

    reset_state = {
        "version": VERSION,
        "decision_log_file": str(decision_log_path),
        "decision_log_candidates": decision_log_candidates,
        "decision_log_offset": 0,
        "decisions_processed": 0,
        "last_run_at": None,
        "last_error": None,
        "rebuild_requested_at": _now(),
        "previous_state": {
            "decision_log_file": old_state.get("decision_log_file"),
            "decision_log_offset": old_state.get("decision_log_offset"),
            "decisions_processed": old_state.get("decisions_processed"),
            "last_run_at": old_state.get("last_run_at"),
        },
    }

    reset_effect = _empty_effect()
    reset_effect["version"] = VERSION
    reset_effect["decision_log_file"] = str(decision_log_path)
    reset_effect["previous_summary"] = old_effect.get("summary") or {}

    if commit:
        _write_json(V2_STATE_FILE, reset_state)
        _write_json(V2_EFFECT_FILE, reset_effect)

    result = run_executive_policy_learning_v2(
        context={"source": "rebuild", "version": VERSION},
        commit=commit,
        max_decisions=max_decisions or MAX_DECISIONS_PER_RUN,
    )

    result["rebuild"] = True
    result["previous_decision_log_file"] = old_state.get("decision_log_file")
    result["previous_decision_log_offset"] = old_state.get("decision_log_offset")
    result["previous_summary"] = old_effect.get("summary") or {}

    try:
        with open(V2_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "event": "POLICY_EFFECT_REBUILD",
                **result,
            }, ensure_ascii=False, sort_keys=True) + "\n")
    except Exception:
        pass

    return result


def build_policy_effect_rebuild_report(result=None):
    if result is None:
        result = rebuild_executive_policy_effect(commit=True)

    lines = [
        "♻️ POLICY EFFECT REBUILD — CENTRAL QUANT V2.1.8",
        f"Data/hora: {_now()}",
        "",
        f"Status: {'✅' if result.get('ok') else '❌'}",
        f"Rebuild: {result.get('rebuild')}",
        f"Decision Log usado: {result.get('decision_log_file')}",
        f"Offset anterior: {result.get('previous_decision_log_offset')}",
        f"Decisões lidas: {result.get('decisions_read', 0)}",
        f"Decisões reais processadas: {result.get('decisions_processed', 0)}",
        f"Matches policy↔decision: {result.get('decisions_matched', 0)}",
        f"Links explícitos no decision_log: {result.get('explicit_policy_links', 0)}",
        f"Fallback via timeline: {result.get('timeline_fallback_links', 0)}",
        f"Sem policy associada: {result.get('decisions_unmatched', 0)}",
        f"Seeds decision ignorados: {result.get('test_decisions_skipped', 0)}",
        f"Seeds timeline ignorados: {result.get('timeline_test_seeds_skipped', 0)}",
        f"Policy events reais carregados: {result.get('policy_events_loaded', 0)}",
        f"Novo offset: {result.get('new_offset')}",
        "",
    ]

    candidates = result.get("decision_log_candidates") or []
    if candidates:
        lines.append("Decision logs candidatos:")
        for item in candidates[:8]:
            lines.append(f"- {item.get('path')} | exists={item.get('exists')} | linhas={item.get('line_count')}")
        lines.append("")

    summary = result.get("summary") or {}
    if summary:
        lines += [
            "Resumo atual:",
            f"- Policies com efeito medido: {summary.get('policy_count', 0)}",
            f"- Decisões correlacionadas: {summary.get('decisions_processed', 0)}",
            f"- Effect score médio: {summary.get('average_effect_score', 0)}",
            "",
        ]

    lines += [
        "Leitura:",
        "A V2.1.8 resolve automaticamente qual decision_log tem mais dados antes do rebuild.",
        "",
        "Próximos comandos:",
        "/policyeffect",
        "/policycompare",
        "/policyinsights",
    ]

    return "\n".join(lines)


# ==========================================================
# EXECUTIVE POLICY LEARNING V2.2.2 — POLICY OUTCOME LINKER
# ==========================================================
# Objetivo:
# - Manter a V2.1.8 funcionando como Policy Effect.
# - Adicionar cruzamento observacional entre policy↔decision e outcomes/lifecycle.
# - Não executa trades.
# - Não altera policies.
# - Não altera risco, lote, prioridade ou execução real.
#
# Fontes tentadas:
# - decision_log.jsonl resolvido pela V2.1.8
# - history_events.jsonl
# - outcome_log.jsonl
# - paper_lifecycle_log.jsonl
# - paper_integrated_log.jsonl
# - trade_registry.json
# - history_export.json
#
# Observação:
# - Quando não houver outcome fechado, mantém outcome_status=WAITING_OUTCOME.
# - Para decisões DENY/BLOCK, não inventa PnL evitado; marca como no_executed_trade_outcome.
# - PnL por policy só é confiável quando os eventos de ciclo/trade fechado tiverem
#   trade_id/signal_id ou chaves suficientes para correlação.

VERSION = "2026-07-05-EXECUTIVE-POLICY-LEARNING-V2.2.1"
POLICY_OUTCOME_WINDOW_DAYS = int(os.environ.get("EXECUTIVE_POLICY_OUTCOME_WINDOW_DAYS", "21"))
POLICY_OUTCOME_MAX_EVENTS = int(os.environ.get("EXECUTIVE_POLICY_OUTCOME_MAX_EVENTS", "12000"))

# Referências para compatibilidade com a V2.1.8.
_V218_effect_policy_template = _effect_policy_template
_V218_apply_decision_to_effect = _apply_decision_to_effect
_V218_recompute_effect_summary = _recompute_effect_summary

_CURRENT_OUTCOME_INDEX = None
_CURRENT_OUTCOME_SOURCES = []


def _ci_get(d, key, default=None):
    if not isinstance(d, dict):
        return default
    if key in d:
        return d.get(key)
    key_l = str(key).lower()
    for k, v in d.items():
        try:
            if str(k).lower() == key_l:
                return v
        except Exception:
            continue
    return default


def _deep_get_any(obj, keys, depth=0):
    if depth > 6 or obj is None:
        return None
    if isinstance(obj, dict):
        for key in keys:
            value = _ci_get(obj, key)
            if value not in (None, ""):
                return value
        for nested_key in ["raw", "payload", "trade", "position", "data", "details", "context", "result", "decision_result", "execution"]:
            child = _ci_get(obj, nested_key)
            if isinstance(child, (dict, list)):
                found = _deep_get_any(child, keys, depth + 1)
                if found not in (None, ""):
                    return found
    elif isinstance(obj, list):
        for item in obj[:20]:
            found = _deep_get_any(item, keys, depth + 1)
            if found not in (None, ""):
                return found
    return None


def _deep_values_for_keys(obj, keys, depth=0, out=None):
    if out is None:
        out = []
    if depth > 6 or obj is None:
        return out
    if isinstance(obj, dict):
        for key in keys:
            value = _ci_get(obj, key)
            if value not in (None, ""):
                out.append(value)
        for value in obj.values():
            if isinstance(value, (dict, list)):
                _deep_values_for_keys(value, keys, depth + 1, out)
    elif isinstance(obj, list):
        for item in obj[:30]:
            if isinstance(item, (dict, list)):
                _deep_values_for_keys(item, keys, depth + 1, out)
    return out


def _normalize_key_value(value):
    if value is None:
        return None
    txt = str(value).strip()
    if not txt or txt.lower() in {"none", "null", "nan"}:
        return None
    return txt.upper()


def _decision_identity(decision):
    """Identidade robusta para correlacionar decisão com outcome."""
    ids = []
    for value in _deep_values_for_keys(decision, [
        "trade_id", "signal_id", "decision_id", "id", "uid", "position_id", "order_id", "client_order_id"
    ]):
        norm = _normalize_key_value(value)
        if norm and len(norm) <= 180 and norm not in ids:
            ids.append(norm)

    fields = _extract_trade_fields(decision)
    bot = _normalize_key_value(fields.get("bot")) or "UNKNOWN"
    symbol = _normalize_key_value(fields.get("symbol")) or "UNKNOWN"
    side = _normalize_key_value(fields.get("side")) or "UNKNOWN"
    setup = _normalize_key_value(fields.get("setup")) or "UNKNOWN"

    # Evita chaves claramente quebradas vindas de wrappers antigos.
    if symbol in {"", "UNKNOWN", "NONE"}:
        sym2 = _normalize_key_value(_deep_get_any(decision, ["symbol", "symbol_clean", "ativo", "pair"]))
        if sym2:
            symbol = sym2
    if side in {"", "UNKNOWN", "NONE"}:
        side2 = _normalize_key_value(_deep_get_any(decision, ["side", "direction"]))
        if side2:
            side = side2

    composite = f"{bot}|{symbol}|{side}|{setup}"
    return {
        "ids": ids,
        "bot": bot,
        "symbol": symbol,
        "side": side,
        "setup": setup,
        "composite": composite,
        "dt": _decision_time(decision),
    }


def _outcome_identity(event):
    ids = []
    for value in _deep_values_for_keys(event, [
        "trade_id", "signal_id", "decision_id", "id", "uid", "position_id", "order_id", "client_order_id"
    ]):
        norm = _normalize_key_value(value)
        if norm and len(norm) <= 180 and norm not in ids:
            ids.append(norm)

    bot = _normalize_key_value(_deep_get_any(event, ["bot", "robot", "source_bot"])) or "UNKNOWN"
    symbol = _normalize_key_value(_deep_get_any(event, ["symbol", "symbol_clean", "ativo", "pair"])) or "UNKNOWN"
    side = _normalize_key_value(_deep_get_any(event, ["side", "direction"])) or "UNKNOWN"
    setup = _normalize_key_value(_deep_get_any(event, ["setup", "strategy", "signal_type", "setup_label"])) or "UNKNOWN"
    dt = _event_time(event) or _parse_dt_any(_deep_get_any(event, ["closed_at", "exit_at", "updated_at", "ts", "timestamp"]))
    return {
        "ids": ids,
        "bot": bot,
        "symbol": symbol,
        "side": side,
        "setup": setup,
        "composite": f"{bot}|{symbol}|{side}|{setup}",
        "dt": dt,
    }


def _extract_numeric_any(event, keys, default=None):
    value = _deep_get_any(event, keys)
    if value in (None, ""):
        return default
    try:
        return float(str(value).replace("%", "").replace(",", "."))
    except Exception:
        return default


def _extract_outcome_payload(event):
    """Extrai resultado fechado de um evento/decisão, sem inventar dados."""
    if not isinstance(event, dict):
        return None

    outcome_text = _deep_get_any(event, [
        "outcome", "result_outcome", "trade_outcome", "closed_result", "pnl_result", "lifecycle_outcome", "result", "status"
    ])
    pnl_pct = _extract_numeric_any(event, [
        "pnl_pct", "result_pct", "profit_pct", "pnl_percent", "return_pct", "pnl_total_pct"
    ])
    result_r = _extract_numeric_any(event, [
        "result_r", "pnl_r", "r", "r_result", "r_multiple", "profit_r"
    ])
    pnl_usdt = _extract_numeric_any(event, [
        "pnl_usdt", "pnl", "profit_usdt", "realized_pnl", "net_pnl", "pnl_total_usdt"
    ])

    text_blob = ""
    try:
        text_blob = json.dumps(event, ensure_ascii=False).upper()
    except Exception:
        text_blob = str(event).upper()

    event_type = str(_deep_get_any(event, ["event", "event_type", "type", "action"]) or "").upper()

    has_close_signal = any(token in text_blob for token in [
        "TRADE_CLOSED", "CLOSED", "FECHADO", "ENCERRADO", "STOP", "TP50", "TAKE_PROFIT", "TAKE PROFIT", "LOSS", "WIN"
    ]) or any(token in event_type for token in ["CLOSE", "CLOSED", "TRADE_CLOSED", "ENCERRADO"])

    has_numeric = pnl_pct is not None or result_r is not None or pnl_usdt is not None
    if not has_close_signal and not has_numeric and not outcome_text:
        return None

    label = str(outcome_text or "").upper()
    if not label or label in {"ALLOW", "DENY", "BLOCK", "VERIFY", "OPEN", "NONE", "NULL"}:
        if result_r is not None:
            label = "WIN" if result_r > 0 else "LOSS" if result_r < 0 else "BREAKEVEN"
        elif pnl_pct is not None:
            label = "WIN" if pnl_pct > 0 else "LOSS" if pnl_pct < 0 else "BREAKEVEN"
        elif pnl_usdt is not None:
            label = "WIN" if pnl_usdt > 0 else "LOSS" if pnl_usdt < 0 else "BREAKEVEN"
        elif "LOSS" in text_blob or "STOP" in text_blob:
            label = "LOSS"
        elif "WIN" in text_blob or "TAKE" in text_blob or "TP" in text_blob:
            label = "WIN"
        else:
            label = "UNKNOWN"

    return {
        "label": label,
        "pnl_pct": pnl_pct,
        "result_r": result_r,
        "pnl_usdt": pnl_usdt,
        "event_type": event_type,
        "dt": _outcome_identity(event).get("dt"),
        "source_event": str(_deep_get_any(event, ["source", "event", "event_type"]) or "unknown")[:80],
    }


def _read_jsonl_tail_items(path, max_items=POLICY_OUTCOME_MAX_EVENTS, max_bytes=6 * 1024 * 1024):
    items = []
    try:
        path = Path(path)
        if not path.exists():
            return []
        with open(path, "rb") as f:
            try:
                f.seek(0, os.SEEK_END)
                size = f.tell()
                if size > max_bytes:
                    f.seek(size - max_bytes)
                    f.readline()
                else:
                    f.seek(0)
            except Exception:
                f.seek(0)
            for line in f:
                if len(items) >= max_items:
                    break
                try:
                    obj = json.loads(line.decode("utf-8").strip())
                    if isinstance(obj, dict):
                        items.append(obj)
                except Exception:
                    continue
    except Exception:
        return []
    return items


def _policy_outcome_candidate_paths():
    paths = []

    def add(value):
        try:
            if not value:
                return
            p = Path(str(value))
            if p not in paths:
                paths.append(p)
        except Exception:
            pass

    data_dirs = [DATA_DIR, BASE_DIR / "data", Path("/data"), Path("/opt/render/project/src/data")]
    for env_name in ["CENTRAL_DATA_DIR", "DATA_DIR"]:
        if os.environ.get(env_name):
            data_dirs.append(Path(os.environ.get(env_name)))

    names = [
        "history_events.jsonl",
        "outcome_log.jsonl",
        "paper_lifecycle_log.jsonl",
        "paper_integrated_log.jsonl",
        "paper_executor_integrated_log.jsonl",
        "execution_engine_log.jsonl",
        "trade_lifecycle_log.jsonl",
        "decision_log.jsonl",
    ]
    for d in data_dirs:
        for name in names:
            add(Path(d) / name)

    # Arquivos JSON agregados.
    for d in data_dirs:
        for name in ["trade_registry.json", "history_export.json", "execution_stats.json"]:
            add(Path(d) / name)

    # Tenta descobrir caminhos exportados por módulos existentes.
    for module_name in ["history_manager", "paper_lifecycle", "outcome_evaluator", "paper_executor_integrated", "trade_registry"]:
        try:
            mod = __import__(module_name)
            for attr in [
                "HISTORY_EVENTS_FILE", "OUTCOME_LOG_FILE", "PAPER_LIFECYCLE_LOG_FILE", "PAPER_INTEGRATED_LOG_FILE",
                "TRADE_REGISTRY_FILE", "HISTORY_EXPORT_FILE", "LOG_FILE", "EVENTS_FILE"
            ]:
                add(getattr(mod, attr, None))
        except Exception:
            continue

    out = []
    seen = set()
    for p in paths:
        key = str(p)
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def _flatten_json_container(obj):
    """Extrai eventos de JSONs agregados como trade_registry/history_export."""
    out = []
    if isinstance(obj, dict):
        # Estruturas comuns.
        for key in ["events", "history", "items", "closed_trades", "trades", "outcomes", "data"]:
            child = obj.get(key)
            if isinstance(child, list):
                out.extend([x for x in child if isinstance(x, dict)])
            elif isinstance(child, dict):
                out.extend(_flatten_json_container(child))
        # trade_registry: open_trades dict / closed_trades list/dict.
        for key in ["closed_trades", "closed", "positions", "registry"]:
            child = obj.get(key)
            if isinstance(child, dict):
                out.extend([v for v in child.values() if isinstance(v, dict)])
        # Se ele próprio parece evento, inclui.
        if _extract_outcome_payload(obj):
            out.append(obj)
    elif isinstance(obj, list):
        out.extend([x for x in obj if isinstance(x, dict)])
    return out


def _load_policy_outcome_index():
    """Carrega outcomes/lifecycle em índices por id e por composite."""
    by_id = {}
    by_composite = {}
    sources = []
    total_events = 0
    total_outcomes = 0

    for path in _policy_outcome_candidate_paths():
        exists = Path(path).exists()
        source_info = {"path": str(path), "exists": bool(exists), "events": 0, "outcomes": 0}
        if not exists:
            sources.append(source_info)
            continue

        events = []
        try:
            if str(path).endswith(".jsonl"):
                events = _read_jsonl_tail_items(path, max_items=POLICY_OUTCOME_MAX_EVENTS)
            elif str(path).endswith(".json"):
                raw = _read_json(path, {})
                events = _flatten_json_container(raw)
        except Exception:
            events = []

        source_info["events"] = len(events)
        total_events += len(events)

        for event in events:
            outcome = _extract_outcome_payload(event)
            if not outcome:
                continue
            ident = _outcome_identity(event)
            payload = {
                "event": event,
                "outcome": outcome,
                "identity": ident,
                "source_file": str(path),
            }
            for idv in ident.get("ids") or []:
                by_id.setdefault(idv, []).append(payload)
            comp = ident.get("composite")
            if comp:
                by_composite.setdefault(comp, []).append(payload)
            total_outcomes += 1

        source_info["outcomes"] = total_outcomes - sum(x.get("outcomes", 0) for x in sources if isinstance(x, dict))
        sources.append(source_info)

    # Ordena candidatos por data para match por tempo.
    for bucket in list(by_id.values()) + list(by_composite.values()):
        try:
            bucket.sort(key=lambda x: x.get("identity", {}).get("dt") or datetime.max)
        except Exception:
            pass

    index = {
        "by_id": by_id,
        "by_composite": by_composite,
        "sources": sources,
        "total_events_loaded": total_events,
        "total_outcomes_loaded": total_outcomes,
        "loaded_at": _now(),
    }
    return index


def _choose_best_outcome(decision, candidates):
    if not candidates:
        return None
    ident = _decision_identity(decision)
    decision_dt = ident.get("dt")
    if not decision_dt:
        return candidates[0]

    max_seconds = max(1, POLICY_OUTCOME_WINDOW_DAYS) * 86400
    best = None
    best_score = None
    for item in candidates:
        odt = (item.get("identity") or {}).get("dt") or (item.get("outcome") or {}).get("dt")
        if odt:
            delta = (odt - decision_dt).total_seconds()
            # Outcome normalmente ocorre depois da decisão. Aceita pequena inversão por timezone/log.
            if delta < -6 * 3600 or delta > max_seconds:
                continue
            score = abs(delta)
        else:
            score = max_seconds + 1
        if best is None or score < best_score:
            best = item
            best_score = score
    return best or candidates[0]


def _find_outcome_for_decision(decision, outcome_index=None):
    outcome_index = outcome_index or _CURRENT_OUTCOME_INDEX
    if not outcome_index:
        return None

    # Resultado já embutido na própria decisão.
    direct = _extract_outcome_payload(decision)
    if direct and (direct.get("pnl_pct") is not None or direct.get("result_r") is not None or direct.get("pnl_usdt") is not None):
        return {"outcome": direct, "identity": _decision_identity(decision), "source_file": "decision_log_embedded", "event": decision}

    ident = _decision_identity(decision)
    candidates = []
    for idv in ident.get("ids") or []:
        candidates.extend((outcome_index.get("by_id") or {}).get(idv, []))
    if candidates:
        return _choose_best_outcome(decision, candidates)

    comp = ident.get("composite")
    if comp:
        candidates = (outcome_index.get("by_composite") or {}).get(comp, [])
        if candidates:
            return _choose_best_outcome(decision, candidates)

    # Fallback sem setup quando setup veio quebrado/ausente.
    comp2 = f"{ident.get('bot')}|{ident.get('symbol')}|{ident.get('side')}|UNKNOWN"
    candidates = (outcome_index.get("by_composite") or {}).get(comp2, [])
    if candidates:
        return _choose_best_outcome(decision, candidates)

    return None


def _ensure_outcome_fields(policy):
    policy.setdefault("outcomes", 0)
    policy.setdefault("wins", 0)
    policy.setdefault("losses", 0)
    policy.setdefault("breakeven", 0)
    policy.setdefault("outcome_unknown", 0)
    policy.setdefault("waiting_outcome", 0)
    policy.setdefault("no_executed_trade_outcome", 0)
    policy.setdefault("pnl_total_pct", 0.0)
    policy.setdefault("pnl_avg_pct", 0.0)
    policy.setdefault("pnl_total_usdt", 0.0)
    policy.setdefault("pnl_avg_usdt", 0.0)
    policy.setdefault("result_r_total", 0.0)
    policy.setdefault("result_r_avg", 0.0)
    policy.setdefault("gross_profit_pct", 0.0)
    policy.setdefault("gross_loss_pct", 0.0)
    policy.setdefault("profit_factor_pct", None)
    policy.setdefault("win_rate_pct", 0.0)
    policy.setdefault("max_drawdown_pct", 0.0)
    policy.setdefault("pnl_curve_pct", [])
    policy.setdefault("last_outcome_at", None)
    policy.setdefault("last_outcome_source", None)
    policy.setdefault("outcome_status", "WAITING_OUTCOME")


def _recompute_policy_outcome_metrics(policy):
    _ensure_outcome_fields(policy)
    outcomes = max(0, _safe_int(policy.get("outcomes")))
    wins = _safe_int(policy.get("wins"))
    losses = _safe_int(policy.get("losses"))

    if outcomes > 0:
        policy["pnl_avg_pct"] = round(_safe_float(policy.get("pnl_total_pct")) / outcomes, 4)
        policy["pnl_avg_usdt"] = round(_safe_float(policy.get("pnl_total_usdt")) / outcomes, 4)
        policy["result_r_avg"] = round(_safe_float(policy.get("result_r_total")) / outcomes, 4)
        policy["win_rate_pct"] = round((wins / outcomes) * 100.0, 2)
    else:
        policy["pnl_avg_pct"] = 0.0
        policy["pnl_avg_usdt"] = 0.0
        policy["result_r_avg"] = 0.0
        policy["win_rate_pct"] = 0.0

    gp = _safe_float(policy.get("gross_profit_pct"), 0.0)
    gl = abs(_safe_float(policy.get("gross_loss_pct"), 0.0))
    if gl > 0:
        policy["profit_factor_pct"] = round(gp / gl, 4)
    elif gp > 0:
        policy["profit_factor_pct"] = 999.0
    else:
        policy["profit_factor_pct"] = None

    curve = policy.get("pnl_curve_pct") or []
    peak = 0.0
    max_dd = 0.0
    for v in curve:
        try:
            x = float(v)
        except Exception:
            continue
        if x > peak:
            peak = x
        dd = peak - x
        if dd > max_dd:
            max_dd = dd
    policy["max_drawdown_pct"] = round(max_dd, 4)

    if outcomes > 0:
        policy["outcome_status"] = "OUTCOME_LINKED"
    elif _safe_int(policy.get("no_executed_trade_outcome")) > 0:
        policy["outcome_status"] = "NO_EXECUTED_TRADE_OUTCOME"
    else:
        policy["outcome_status"] = "WAITING_OUTCOME"


def _apply_outcome_to_policy(policy, decision, outcome_match):
    _ensure_outcome_fields(policy)
    decision_name = _extract_decision(decision)

    # Se a policy bloqueou/negou, não houve trade executado para ter PnL real.
    if "DENY" in decision_name or "BLOCK" in decision_name:
        policy["no_executed_trade_outcome"] = _safe_int(policy.get("no_executed_trade_outcome")) + 1
        _recompute_policy_outcome_metrics(policy)
        return False

    if not outcome_match:
        policy["waiting_outcome"] = _safe_int(policy.get("waiting_outcome")) + 1
        _recompute_policy_outcome_metrics(policy)
        return False

    outcome = outcome_match.get("outcome") or {}
    label = str(outcome.get("label") or "UNKNOWN").upper()
    pnl_pct = outcome.get("pnl_pct")
    result_r = outcome.get("result_r")
    pnl_usdt = outcome.get("pnl_usdt")

    policy["outcomes"] = _safe_int(policy.get("outcomes")) + 1

    # Classificação por label ou números.
    is_win = False
    is_loss = False
    is_be = False
    if any(x in label for x in ["WIN", "TP", "PROFIT", "GAIN"]):
        is_win = True
    elif any(x in label for x in ["LOSS", "STOP", "SL"]):
        is_loss = True
    elif any(x in label for x in ["BE", "BREAKEVEN", "ZERO"]):
        is_be = True
    elif result_r is not None:
        is_win = float(result_r) > 0
        is_loss = float(result_r) < 0
        is_be = float(result_r) == 0
    elif pnl_pct is not None:
        is_win = float(pnl_pct) > 0
        is_loss = float(pnl_pct) < 0
        is_be = float(pnl_pct) == 0
    elif pnl_usdt is not None:
        is_win = float(pnl_usdt) > 0
        is_loss = float(pnl_usdt) < 0
        is_be = float(pnl_usdt) == 0
    else:
        policy["outcome_unknown"] = _safe_int(policy.get("outcome_unknown")) + 1

    if is_win:
        policy["wins"] = _safe_int(policy.get("wins")) + 1
    elif is_loss:
        policy["losses"] = _safe_int(policy.get("losses")) + 1
    elif is_be:
        policy["breakeven"] = _safe_int(policy.get("breakeven")) + 1

    if pnl_pct is not None:
        pnl_pct = float(pnl_pct)
        policy["pnl_total_pct"] = round(_safe_float(policy.get("pnl_total_pct")) + pnl_pct, 6)
        if pnl_pct > 0:
            policy["gross_profit_pct"] = round(_safe_float(policy.get("gross_profit_pct")) + pnl_pct, 6)
        elif pnl_pct < 0:
            policy["gross_loss_pct"] = round(_safe_float(policy.get("gross_loss_pct")) + pnl_pct, 6)
        curve = policy.setdefault("pnl_curve_pct", [])
        last = float(curve[-1]) if curve else 0.0
        curve.append(round(last + pnl_pct, 6))
        if len(curve) > 500:
            del curve[:-500]

    if result_r is not None:
        policy["result_r_total"] = round(_safe_float(policy.get("result_r_total")) + float(result_r), 6)

    if pnl_usdt is not None:
        policy["pnl_total_usdt"] = round(_safe_float(policy.get("pnl_total_usdt")) + float(pnl_usdt), 6)

    odt = outcome.get("dt")
    if odt:
        try:
            policy["last_outcome_at"] = odt.strftime("%d/%m/%Y %H:%M:%S")
        except Exception:
            policy["last_outcome_at"] = str(odt)
    policy["last_outcome_source"] = outcome_match.get("source_file")

    _recompute_policy_outcome_metrics(policy)
    return True


def _effect_policy_template(code):
    policy = _V218_effect_policy_template(code)
    _ensure_outcome_fields(policy)
    return policy


def _apply_decision_to_effect(policy, decision):
    # Primeiro preserva toda a lógica V2.1.8: decisões, allow/deny, readiness.
    _V218_apply_decision_to_effect(policy, decision)
    # Depois adiciona outcome, se existir.
    outcome_match = _find_outcome_for_decision(decision, _CURRENT_OUTCOME_INDEX)
    _apply_outcome_to_policy(policy, decision, outcome_match)
    _score_effect_policy(policy)


def _score_effect_policy(policy):
    """V2.2: mantém score operacional e adiciona influência de outcomes quando houver."""
    decisions = _safe_int(policy.get("real_decisions", policy.get("decisions")))
    allow = _safe_int(policy.get("allow"))
    deny = _safe_int(policy.get("deny"))
    block = _safe_int(policy.get("block"))
    reduce_size = _safe_int(policy.get("reduce_size"))
    no_expansion = _safe_int(policy.get("no_expansion"))
    outcomes = _safe_int(policy.get("outcomes"))
    pnl_avg = _safe_float(policy.get("pnl_avg_pct"), 0.0)
    pf = policy.get("profit_factor_pct")
    dd = _safe_float(policy.get("max_drawdown_pct"), 0.0)

    sample_score = min(25.0, decisions * 2.0)
    protection_score = min(25.0, (deny + block + reduce_size + no_expansion) * 3.0)
    operation_score = min(15.0, allow * 1.5)
    outcome_score = 0.0

    if outcomes > 0:
        outcome_score += min(15.0, outcomes * 2.0)
        if pnl_avg > 0:
            outcome_score += min(10.0, pnl_avg * 2.0)
        elif pnl_avg < 0:
            outcome_score -= min(10.0, abs(pnl_avg) * 2.0)
        try:
            if pf is not None and float(pf) >= 1.2:
                outcome_score += 5.0
            elif pf is not None and float(pf) < 1.0:
                outcome_score -= 5.0
        except Exception:
            pass
        if dd > 5:
            outcome_score -= min(8.0, dd / 2.0)

    balance_score = 10.0
    if decisions >= 10 and allow >= decisions * 0.9 and (deny + block + reduce_size + no_expansion) == 0:
        balance_score = 4.0
    if decisions >= 10 and allow == 0 and (deny + block) >= decisions * 0.9:
        balance_score = 5.0

    score = max(0.0, min(100.0, sample_score + protection_score + operation_score + balance_score + outcome_score))
    confidence = min(100.0, (decisions / 20.0) * 100.0)

    if confidence < 35:
        recommendation = "AGUARDAR_AMOSTRA"
    elif outcomes >= 10 and pnl_avg < 0:
        recommendation = "REVISAR_OUTCOME"
    elif score >= 80:
        recommendation = "MANTER"
    elif score >= 60:
        recommendation = "OBSERVAR"
    elif score >= 45:
        recommendation = "REVISAR"
    else:
        recommendation = "ENFRAQUECER_OU_APOSENTAR"

    notes = []
    if decisions < 20:
        notes.append("Amostra de decisões ainda insuficiente para conclusão robusta.")
    if deny + block + reduce_size + no_expansion > 0:
        notes.append("Policy influenciou restrição/controle de risco em decisões.")
    if allow > 0:
        notes.append("Policy também conviveu com decisões permitidas.")
    if outcomes > 0:
        notes.append("Policy já possui outcomes/lifecycle correlacionados.")
    else:
        notes.append("Ainda sem outcomes fechados correlacionados; PnL não conclusivo.")
    if decisions >= 10 and allow == 0:
        notes.append("Policy altamente restritiva; PnL evitado exige análise hipotética futura.")

    policy["effect_score"] = round(score, 2)
    policy["confidence_pct"] = round(confidence, 2)
    policy["recommendation"] = recommendation
    policy["notes"] = notes[-6:]
    _compute_policy_readiness(policy)


def _recompute_effect_summary(effect):
    policies = effect.get("policies") or {}
    values = [p for p in policies.values() if isinstance(p, dict)]

    for p in values:
        _ensure_outcome_fields(p)
        _recompute_policy_outcome_metrics(p)
        _score_effect_policy(p)

    total_decisions = sum(_safe_int(p.get("real_decisions", p.get("decisions"))) for p in values)
    total_outcomes = sum(_safe_int(p.get("outcomes")) for p in values)
    total_pnl_pct = sum(_safe_float(p.get("pnl_total_pct"), 0.0) for p in values)
    total_pnl_usdt = sum(_safe_float(p.get("pnl_total_usdt"), 0.0) for p in values)
    wins = sum(_safe_int(p.get("wins")) for p in values)
    losses = sum(_safe_int(p.get("losses")) for p in values)
    avg = 0.0
    if values:
        avg = sum(_safe_float(p.get("effect_score")) for p in values) / len(values)

    previous_unmatched = _safe_int((effect.get("summary") or {}).get("decisions_unmatched"))
    ready = sum(1 for p in values if p.get("readiness_label") == "READY_TO_LEARN")
    caution = sum(1 for p in values if p.get("readiness_label") == "LEARN_WITH_CAUTION")
    wait = sum(1 for p in values if p.get("readiness_label") == "WAIT_SAMPLE")

    effect["summary"] = {
        "policy_count": len(values),
        "decisions_processed": total_decisions,
        "real_decisions_correlated": total_decisions,
        "decisions_matched": total_decisions,
        "decisions_unmatched": previous_unmatched,
        "outcomes_detected": total_outcomes,
        "wins": wins,
        "losses": losses,
        "win_rate_pct": round((wins / total_outcomes) * 100.0, 2) if total_outcomes else 0.0,
        "pnl_total_pct": round(total_pnl_pct, 4),
        "pnl_total_usdt": round(total_pnl_usdt, 4),
        "average_effect_score": round(avg, 2),
        "ready_to_learn": ready,
        "learn_with_caution": caution,
        "wait_sample": wait,
        "outcome_sources": _CURRENT_OUTCOME_SOURCES,
        "updated_at": _now(),
    }


def run_executive_policy_learning_v2(context=None, commit=True, max_decisions=None):
    """
    V2.2:
    Lê decisões novas, associa policies por links explícitos/raw-aware e cruza com outcomes/lifecycle.
    """
    global _CURRENT_OUTCOME_INDEX, _CURRENT_OUTCOME_SOURCES
    started = time.time()
    state = _load_v2_state()
    effect = _load_effect()

    outcome_index = _load_policy_outcome_index()
    _CURRENT_OUTCOME_INDEX = outcome_index
    _CURRENT_OUTCOME_SOURCES = outcome_index.get("sources") or []

    decision_log_path = _resolve_decision_log_file()
    decision_log_candidates = getattr(_resolve_decision_log_file, "last_candidates", [])

    previous_path = state.get("decision_log_file")
    if previous_path and str(previous_path) != str(decision_log_path):
        offset = 0
    else:
        offset = _safe_int(state.get("decision_log_offset"), 0)

    max_decisions = int(max_decisions or MAX_DECISIONS_PER_RUN)

    decisions, new_offset, reached_eof = _read_new_jsonl(decision_log_path, offset, max_decisions)
    policy_events = _read_all_policy_events_light()
    timeline_seeds_skipped = getattr(_read_all_policy_events_light, "last_skipped_test_seeds", 0)

    processed = 0
    matched = 0
    unmatched = 0
    test_decisions_skipped = 0
    explicit_policy_links = 0
    timeline_fallback_links = 0
    outcomes_linked_now = 0

    policies = effect.setdefault("policies", {})

    for decision in decisions:
        if _is_test_seed_event(decision):
            test_decisions_skipped += 1
            continue

        explicit_codes = _decision_policy_codes(decision)
        dt = _decision_time(decision)
        codes = explicit_codes or _active_policy_codes_for_decision(dt, policy_events)

        if not codes:
            unmatched += 1
            processed += 1
            continue

        if explicit_codes:
            explicit_policy_links += 1
        else:
            timeline_fallback_links += 1

        before_outcomes_total = sum(_safe_int((policies.get(c) or {}).get("outcomes")) for c in codes if isinstance(policies.get(c), dict))

        for code in codes:
            policy = policies.get(code)
            if not isinstance(policy, dict):
                policy = _effect_policy_template(code)
                policies[code] = policy
            _apply_decision_to_effect(policy, decision)
            matched += 1

        after_outcomes_total = sum(_safe_int((policies.get(c) or {}).get("outcomes")) for c in codes if isinstance(policies.get(c), dict))
        if after_outcomes_total > before_outcomes_total:
            outcomes_linked_now += after_outcomes_total - before_outcomes_total

        processed += 1

    prior_summary = effect.get("summary") if isinstance(effect.get("summary"), dict) else {}
    prior_unmatched = _safe_int(prior_summary.get("decisions_unmatched"))
    effect.setdefault("summary", {})["decisions_unmatched"] = prior_unmatched + unmatched

    if commit:
        _save_effect(effect)
        _save_v2_state({
            **state,
            "version": VERSION,
            "decision_log_file": str(decision_log_path),
            "decision_log_candidates": decision_log_candidates,
            "decision_log_offset": new_offset,
            "last_run_at": _now(),
            "last_error": None,
            "decisions_processed": _safe_int(state.get("decisions_processed")) + processed,
            "last_batch": {
                "decisions_read": len(decisions),
                "decisions_processed": processed,
                "decisions_matched": matched,
                "decisions_unmatched": unmatched,
                "test_decisions_skipped": test_decisions_skipped,
                "explicit_policy_links": explicit_policy_links,
                "timeline_fallback_links": timeline_fallback_links,
                "timeline_test_seeds_skipped": timeline_seeds_skipped,
                "policy_events_loaded": len(policy_events),
                "outcome_events_loaded": outcome_index.get("total_events_loaded", 0),
                "outcomes_available": outcome_index.get("total_outcomes_loaded", 0),
                "outcomes_linked_now": outcomes_linked_now,
                "decision_log_file": str(decision_log_path),
                "decision_log_candidates": decision_log_candidates,
                "old_offset": offset,
                "new_offset": new_offset,
                "reached_eof": reached_eof,
            },
        })
    else:
        _recompute_effect_summary(effect)

    result = {
        "ok": True,
        "module": "executive_policy_learning_v2",
        "version": VERSION,
        "generated_at": _now(),
        "commit": commit,
        "decision_log_file": str(decision_log_path),
        "decision_log_candidates": decision_log_candidates,
        "timeline_file": str(TIMELINE_FILE),
        "effect_file": str(V2_EFFECT_FILE),
        "decisions_read": len(decisions),
        "decisions_processed": processed,
        "decisions_matched": matched,
        "decisions_unmatched": unmatched,
        "test_decisions_skipped": test_decisions_skipped,
        "explicit_policy_links": explicit_policy_links,
        "timeline_fallback_links": timeline_fallback_links,
        "timeline_test_seeds_skipped": timeline_seeds_skipped,
        "policy_events_loaded": len(policy_events),
        "outcome_events_loaded": outcome_index.get("total_events_loaded", 0),
        "outcomes_available": outcome_index.get("total_outcomes_loaded", 0),
        "outcomes_linked_now": outcomes_linked_now,
        "outcome_sources": outcome_index.get("sources") or [],
        "old_offset": offset,
        "new_offset": new_offset,
        "reached_eof": reached_eof,
        "duration_ms": round((time.time() - started) * 1000, 2),
        "summary": effect.get("summary") or {},
        "notes": [
            "V2.2 cruza Policy Effect com Lifecycle/Outcome quando houver dados fechados.",
            "Decisões DENY/BLOCK não recebem PnL inventado; são marcadas como sem trade executado.",
            "READY_TO_LEARN continua observacional e não altera execução real.",
        ],
    }

    try:
        with open(V2_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(result, ensure_ascii=False, sort_keys=True) + "\n")
    except Exception:
        pass

    return result


def build_executive_policy_effect_report(result=None, limit=12):
    if result is None:
        result = run_executive_policy_learning_v2(context={}, commit=True)

    effect = get_executive_policy_effect_stats()
    summary = effect.get("summary") or {}
    policies = effect.get("policies") or {}

    ranking = sorted(
        [p for p in policies.values() if isinstance(p, dict)],
        key=lambda p: (
            p.get("readiness_label") == "READY_TO_LEARN",
            p.get("readiness_label") == "LEARN_WITH_CAUTION",
            _safe_float(p.get("effect_score")),
            _safe_float(p.get("confidence_pct")),
            _safe_int(p.get("real_decisions", p.get("decisions"))),
        ),
        reverse=True,
    )

    lines = [
        "🧠 EXECUTIVE POLICY LEARNING V2.2.2 — POLICY OUTCOME LINKER",
        f"Data/hora: {_now()}",
        "",
        f"Status: {'✅' if result.get('ok') else '❌'}",
        f"Decisões lidas agora: {result.get('decisions_read', 0)}",
        f"Decisões reais processadas agora: {result.get('decisions_processed', 0)}",
        f"Matches policy↔decision: {result.get('decisions_matched', 0)}",
        f"Links explícitos no decision_log: {result.get('explicit_policy_links', 0)}",
        f"Fallback via timeline: {result.get('timeline_fallback_links', 0)}",
        f"Sem policy associada: {result.get('decisions_unmatched', 0)}",
        f"Seeds decision ignorados: {result.get('test_decisions_skipped', 0)}",
        f"Policy events reais carregados: {result.get('policy_events_loaded', 0)}",
        f"Outcome events carregados: {result.get('outcome_events_loaded', 0)}",
        f"Outcomes disponíveis: {result.get('outcomes_available', 0)}",
        f"Outcomes linkados agora: {result.get('outcomes_linked_now', 0)}",
        "",
        "Resumo acumulado:",
        f"- Policies com efeito medido: {summary.get('policy_count', 0)}",
        f"- Decisões reais correlacionadas: {summary.get('real_decisions_correlated', summary.get('decisions_processed', 0))}",
        f"- Outcomes detectados: {summary.get('outcomes_detected', 0)}",
        f"- Wins/Losses: {summary.get('wins', 0)}/{summary.get('losses', 0)}",
        f"- Win rate: {summary.get('win_rate_pct', 0)}%",
        f"- PnL total pct: {summary.get('pnl_total_pct', 0)}%",
        f"- READY_TO_LEARN: {summary.get('ready_to_learn', 0)}",
        f"- LEARN_WITH_CAUTION: {summary.get('learn_with_caution', 0)}",
        f"- WAIT_SAMPLE: {summary.get('wait_sample', 0)}",
        f"- Effect score médio: {summary.get('average_effect_score', 0)}",
        "",
    ]

    if not ranking:
        lines += [
            "Ainda não há correlação policy↔decision suficiente.",
            "",
            "Leitura:",
            "A V2.2 precisa de Decision Log com policy_codes e Lifecycle/Outcome para medir PnL real.",
        ]
        return "\n".join(lines)

    lines.append("Ranking de readiness/efeito/outcome:")
    for idx, p in enumerate(ranking[:limit], start=1):
        restrictions = _safe_int(p.get("deny")) + _safe_int(p.get("block")) + _safe_int(p.get("reduce_size")) + _safe_int(p.get("no_expansion"))
        lines += [
            f"{idx}. {p.get('code')}",
            f"- Readiness: {p.get('readiness_label')} | score={p.get('readiness_score')} | ready={p.get('ready_to_learn')}",
            f"- Effect Score: {p.get('effect_score')} | Confiança: {p.get('confidence_pct')}%",
            f"- Decisões reais: {p.get('real_decisions', p.get('decisions'))} | ALLOW: {p.get('allow')} | restrições: {restrictions}",
            f"- Outcomes: {p.get('outcomes', 0)} | W/L/BE: {p.get('wins', 0)}/{p.get('losses', 0)}/{p.get('breakeven', 0)} | Win rate: {p.get('win_rate_pct', 0)}%",
            f"- PnL pct: total={p.get('pnl_total_pct', 0)} | avg={p.get('pnl_avg_pct', 0)} | PF={p.get('profit_factor_pct')}",
            f"- R total/avg: {p.get('result_r_total', 0)} / {p.get('result_r_avg', 0)} | DD max: {p.get('max_drawdown_pct', 0)}%",
            f"- Outcome status: {p.get('outcome_status')}",
            f"- Recomendação: {p.get('recommendation')}",
        ]
        notes = p.get("notes") or []
        if notes:
            lines.append(f"- Nota: {notes[0]}")
        lines.append("")

    lines += [
        "Observação:",
        "V2.2 não inventa PnL para trades bloqueados. Ela só mede outcome real quando há ciclo/fechamento correlacionável.",
        "A próxima etapa pode criar uma análise hipotética separada para PnL evitado/perdido por bloqueios.",
    ]
    return "\n".join(lines)


def build_policy_compare_report(limit=10):
    effect = get_executive_policy_effect_stats()
    policies = effect.get("policies") or {}
    ranking = sorted(
        [p for p in policies.values() if isinstance(p, dict)],
        key=lambda p: (
            p.get("readiness_label") == "READY_TO_LEARN",
            _safe_float(p.get("effect_score")),
            _safe_int(p.get("outcomes")),
            _safe_int(p.get("real_decisions", p.get("decisions"))),
        ),
        reverse=True,
    )

    lines = [
        "⚖️ POLICY COMPARE — CENTRAL QUANT V2.2",
        f"Data/hora: {_now()}",
        "",
    ]

    if not ranking:
        lines += [
            "Sem policies suficientes para comparar.",
            "Rode /policyeffect após acumular decisões e outcomes.",
        ]
        return "\n".join(lines)

    for idx, p in enumerate(ranking[:limit], start=1):
        restrictions = _safe_int(p.get("deny")) + _safe_int(p.get("block")) + _safe_int(p.get("reduce_size")) + _safe_int(p.get("no_expansion"))
        lines.append(
            f"{idx}. {p.get('code')} | readiness={p.get('readiness_label')}({p.get('readiness_score')}) | "
            f"effect={p.get('effect_score')} | conf={p.get('confidence_pct')}% | "
            f"dec_reais={p.get('real_decisions', p.get('decisions'))} | allow={p.get('allow')} | restrições={restrictions} | "
            f"outcomes={p.get('outcomes', 0)} | W/L={p.get('wins', 0)}/{p.get('losses', 0)} | "
            f"PnL={p.get('pnl_total_pct', 0)}% | PF={p.get('profit_factor_pct')} | DD={p.get('max_drawdown_pct', 0)}%"
        )

    return "\n".join(lines)


def build_policy_insights_report():
    effect = get_executive_policy_effect_stats()
    policies = effect.get("policies") or {}
    values = [p for p in policies.values() if isinstance(p, dict)]
    summary = effect.get("summary") or {}

    lines = [
        "💡 POLICY INSIGHTS — CENTRAL QUANT V2.2",
        f"Data/hora: {_now()}",
        "",
        f"READY_TO_LEARN: {summary.get('ready_to_learn', 0)}",
        f"LEARN_WITH_CAUTION: {summary.get('learn_with_caution', 0)}",
        f"WAIT_SAMPLE: {summary.get('wait_sample', 0)}",
        f"Outcomes detectados: {summary.get('outcomes_detected', 0)}",
        f"PnL total correlacionado: {summary.get('pnl_total_pct', 0)}%",
        "",
    ]

    if not values:
        lines += [
            "Ainda não há dados suficientes para insights.",
            "Rode /policyeffect após acumular Decision Log e Lifecycle/Outcome.",
        ]
        return "\n".join(lines)

    best_effect = max(values, key=lambda p: _safe_float(p.get("effect_score")))
    worst_effect = min(values, key=lambda p: _safe_float(p.get("effect_score")))
    with_outcomes = [p for p in values if _safe_int(p.get("outcomes")) > 0]

    lines += [
        f"Melhor effect score: {best_effect.get('code')} — {best_effect.get('effect_score')}",
        f"Menor effect score: {worst_effect.get('code')} — {worst_effect.get('effect_score')}",
        "",
    ]

    if with_outcomes:
        best_pnl = max(with_outcomes, key=lambda p: _safe_float(p.get("pnl_total_pct")))
        worst_pnl = min(with_outcomes, key=lambda p: _safe_float(p.get("pnl_total_pct")))
        lines += [
            f"Melhor PnL correlacionado: {best_pnl.get('code')} — {best_pnl.get('pnl_total_pct')}% em {best_pnl.get('outcomes')} outcomes",
            f"Pior PnL correlacionado: {worst_pnl.get('code')} — {worst_pnl.get('pnl_total_pct')}% em {worst_pnl.get('outcomes')} outcomes",
            "",
        ]
    else:
        lines += [
            "Ainda não há outcomes fechados correlacionados às policies.",
            "Isso é esperado enquanto as decisões forem recentes ou enquanto os fechamentos não carregarem trade_id/signal_id compatível.",
            "",
        ]

    restrictive = sorted(
        values,
        key=lambda p: _safe_int(p.get("deny")) + _safe_int(p.get("block")) + _safe_int(p.get("reduce_size")) + _safe_int(p.get("no_expansion")),
        reverse=True,
    )

    lines.append("Mais restritivas:")
    for p in restrictive[:5]:
        restrictions = _safe_int(p.get("deny")) + _safe_int(p.get("block")) + _safe_int(p.get("reduce_size")) + _safe_int(p.get("no_expansion"))
        lines.append(
            f"- {p.get('code')}: restrições={restrictions}, decisões reais={p.get('real_decisions', p.get('decisions'))}, "
            f"outcomes={p.get('outcomes', 0)}, readiness={p.get('readiness_label')}, score={p.get('effect_score')}"
        )

    lines += [
        "",
        "Leitura:",
        "V2.2 mede PnL real apenas quando há outcome/lifecycle correlacionável. Para policies restritivas, PnL evitado/perdido exige uma análise hipotética separada.",
    ]
    return "\n".join(lines)


def rebuild_executive_policy_effect(commit=True, max_decisions=None):
    """
    V2.2 rebuild completo:
    - zera offset do decision_log da V2
    - limpa effect/outcome stats
    - reprocessa desde o início com Outcome Linker ativo
    """
    old_state = _load_v2_state()
    old_effect = _load_effect()

    decision_log_path = _resolve_decision_log_file()
    decision_log_candidates = getattr(_resolve_decision_log_file, "last_candidates", [])

    reset_state = {
        "version": VERSION,
        "decision_log_file": str(decision_log_path),
        "decision_log_candidates": decision_log_candidates,
        "decision_log_offset": 0,
        "decisions_processed": 0,
        "last_run_at": None,
        "last_error": None,
        "rebuild_requested_at": _now(),
        "previous_state": {
            "decision_log_file": old_state.get("decision_log_file"),
            "decision_log_offset": old_state.get("decision_log_offset"),
            "decisions_processed": old_state.get("decisions_processed"),
            "last_run_at": old_state.get("last_run_at"),
        },
    }

    reset_effect = _empty_effect()
    reset_effect["version"] = VERSION
    reset_effect["decision_log_file"] = str(decision_log_path)
    reset_effect["previous_summary"] = old_effect.get("summary") or {}

    if commit:
        _write_json(V2_STATE_FILE, reset_state)
        _write_json(V2_EFFECT_FILE, reset_effect)

    result = run_executive_policy_learning_v2(
        context={"source": "rebuild", "version": VERSION},
        commit=commit,
        max_decisions=max_decisions or MAX_DECISIONS_PER_RUN,
    )

    result["rebuild"] = True
    result["previous_decision_log_file"] = old_state.get("decision_log_file")
    result["previous_decision_log_offset"] = old_state.get("decision_log_offset")
    result["previous_summary"] = old_effect.get("summary") or {}

    try:
        with open(V2_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "event": "POLICY_EFFECT_REBUILD_V2_2",
                **result,
            }, ensure_ascii=False, sort_keys=True) + "\n")
    except Exception:
        pass

    return result


def build_policy_effect_rebuild_report(result=None):
    if result is None:
        result = rebuild_executive_policy_effect(commit=True)

    lines = [
        "♻️ POLICY EFFECT REBUILD — CENTRAL QUANT V2.2.2",
        f"Data/hora: {_now()}",
        "",
        f"Status: {'✅' if result.get('ok') else '❌'}",
        f"Rebuild: {result.get('rebuild')}",
        f"Decision Log usado: {result.get('decision_log_file')}",
        f"Offset anterior: {result.get('previous_decision_log_offset')}",
        f"Decisões lidas: {result.get('decisions_read', 0)}",
        f"Decisões reais processadas: {result.get('decisions_processed', 0)}",
        f"Matches policy↔decision: {result.get('decisions_matched', 0)}",
        f"Links explícitos no decision_log: {result.get('explicit_policy_links', 0)}",
        f"Fallback via timeline: {result.get('timeline_fallback_links', 0)}",
        f"Sem policy associada: {result.get('decisions_unmatched', 0)}",
        f"Outcome events carregados: {result.get('outcome_events_loaded', 0)}",
        f"Outcomes disponíveis: {result.get('outcomes_available', 0)}",
        f"Outcomes linkados agora: {result.get('outcomes_linked_now', 0)}",
        f"Novo offset: {result.get('new_offset')}",
        "",
    ]

    candidates = result.get("decision_log_candidates") or []
    if candidates:
        lines.append("Decision logs candidatos:")
        for item in candidates[:8]:
            lines.append(f"- {item.get('path')} | exists={item.get('exists')} | linhas={item.get('line_count')}")
        lines.append("")

    sources = result.get("outcome_sources") or []
    if sources:
        lines.append("Outcome sources candidatos:")
        for item in sources[:10]:
            lines.append(f"- {item.get('path')} | exists={item.get('exists')} | eventos={item.get('events')} | outcomes={item.get('outcomes')}")
        lines.append("")

    summary = result.get("summary") or {}
    if summary:
        lines += [
            "Resumo atual:",
            f"- Policies com efeito medido: {summary.get('policy_count', 0)}",
            f"- Decisões correlacionadas: {summary.get('decisions_processed', 0)}",
            f"- Outcomes detectados: {summary.get('outcomes_detected', 0)}",
            f"- PnL total pct: {summary.get('pnl_total_pct', 0)}%",
            f"- Effect score médio: {summary.get('average_effect_score', 0)}",
            "",
        ]

    lines += [
        "Leitura:",
        "A V2.2.2 cruza policies com outcomes/lifecycle quando houver fechamento correlacionável.",
        "Ela não inventa PnL para bloqueios; PnL evitado será uma camada hipotética futura.",
        "",
        "Próximos comandos:",
        "/policyeffect",
        "/policycompare",
        "/policyinsights",
    ]

    return "\n".join(lines)


# ==========================================================
# EXECUTIVE POLICY LEARNING V2.2.2 — OUTCOME VALUE PARSER HOTFIX
# ==========================================================
# Objetivo:
# - manter todo o linker da V2.2;
# - melhorar a extração real de valores de outcome/PnL/R;
# - ler campos dentro de raw/details/payload/context e strings JSON/Python-like;
# - calcular pnl_pct a partir de entry/exit/stop/tp quando possível;
# - não inventar PnL para bloqueios DENY/BLOCK.

VERSION = "2026-07-05-EXECUTIVE-POLICY-LEARNING-V2.2.2"

try:
    import ast as _ast_v222
except Exception:
    _ast_v222 = None


def _v222_normalize_key(key):
    return str(key or "").strip().lower().replace("-", "_").replace(" ", "_")


def _v222_parse_jsonish(value, depth=0):
    """Tenta transformar strings JSON/Python-like em dict/list sem quebrar se falhar."""
    if depth > 2 or not isinstance(value, str):
        return None
    txt = value.strip()
    if len(txt) < 2 or len(txt) > 60000:
        return None
    if not ((txt.startswith("{") and txt.endswith("}")) or (txt.startswith("[") and txt.endswith("]"))):
        return None

    # 1) JSON normal.
    try:
        return json.loads(txt)
    except Exception:
        pass

    # 2) Python repr com True/False/None.
    if _ast_v222 is not None:
        try:
            return _ast_v222.literal_eval(txt)
        except Exception:
            pass

    # 3) Python repr que veio uppercased pelo History: TRUE/FALSE/NONE.
    try:
        fixed = re.sub(r"\bTRUE\b", "True", txt)
        fixed = re.sub(r"\bFALSE\b", "False", fixed)
        fixed = re.sub(r"\bNONE\b", "None", fixed)
        fixed = re.sub(r"\bNULL\b", "None", fixed)
        if _ast_v222 is not None:
            return _ast_v222.literal_eval(fixed)
    except Exception:
        pass
    return None


def _v222_iter_nodes(obj, depth=0, seen=None):
    """Itera recursivamente por dict/list e por strings que contenham dict/list."""
    if seen is None:
        seen = set()
    if depth > 7:
        return
    oid = id(obj)
    if oid in seen:
        return
    seen.add(oid)

    if isinstance(obj, dict):
        yield obj
        # Primeiro fontes mais úteis para outcomes.
        preferred = ["raw", "details", "payload", "trade", "position", "context", "data", "result", "event"]
        keys = list(obj.keys())
        keys.sort(key=lambda k: 0 if _v222_normalize_key(k) in preferred else 1)
        for key in keys:
            val = obj.get(key)
            if isinstance(val, (dict, list)):
                yield from _v222_iter_nodes(val, depth + 1, seen)
            elif isinstance(val, str):
                parsed = _v222_parse_jsonish(val, depth + 1)
                if parsed is not None:
                    yield from _v222_iter_nodes(parsed, depth + 1, seen)
    elif isinstance(obj, list):
        for val in obj:
            if isinstance(val, (dict, list)):
                yield from _v222_iter_nodes(val, depth + 1, seen)
            elif isinstance(val, str):
                parsed = _v222_parse_jsonish(val, depth + 1)
                if parsed is not None:
                    yield from _v222_iter_nodes(parsed, depth + 1, seen)


def _v222_deep_get_any(event, keys):
    wanted = {_v222_normalize_key(k) for k in keys}
    for node in _v222_iter_nodes(event):
        if not isinstance(node, dict):
            continue
        # Busca exata case-insensitive/normalizada.
        for k, v in node.items():
            if _v222_normalize_key(k) in wanted and v not in (None, "", "None", "NONE", "null", "NULL"):
                return v
        # Alguns logs guardam tudo dentro de raw.raw ou detalhes textuais.
    return None


def _v222_safe_float(value, default=None):
    if value in (None, "", "None", "NONE", "null", "NULL"):
        return default
    if isinstance(value, bool):
        return default
    try:
        if isinstance(value, (int, float)):
            return float(value)
        txt = str(value).strip()
        if not txt:
            return default
        # Remove símbolos comuns.
        txt = txt.replace("%", "").replace("USDT", "").replace("R$", "").replace("$", "").strip()
        # Trata vírgula decimal brasileira.
        if "," in txt and "." not in txt:
            txt = txt.replace(",", ".")
        # Remove milhares simples.
        txt = re.sub(r"(?<=\d),(?=\d{3}\b)", "", txt)
        m = re.search(r"[-+]?\d+(?:\.\d+)?", txt)
        if not m:
            return default
        return float(m.group(0))
    except Exception:
        return default


def _v222_extract_numeric_any(event, keys, default=None):
    value = _v222_deep_get_any(event, keys)
    return _v222_safe_float(value, default=default)


def _v222_text_blob(event):
    try:
        return json.dumps(event, ensure_ascii=False, default=str).upper()
    except Exception:
        return str(event).upper()


def _v222_pick_label(event):
    label = _v222_deep_get_any(event, [
        "outcome", "result_outcome", "trade_outcome", "closed_result", "pnl_result",
        "lifecycle_outcome", "trade_result", "final_result", "result_label", "close_reason",
        "reason", "status", "result", "event", "event_type", "type", "action"
    ])
    label = str(label or "").strip().upper()
    blob = _v222_text_blob(event)

    # Evita tratar decisão operacional como outcome.
    if label in {"ALLOW", "DENY", "BLOCK", "VERIFY", "OPEN", "ACTIVE", "NONE", "NULL"}:
        label = ""

    if not label:
        if any(x in blob for x in ["STOP_LOSS", "STOP LOSS", " SL", "LOSS", "PREJUIZO", "PREJUÍZO", "STOP"]):
            label = "LOSS"
        elif any(x in blob for x in ["TAKE_PROFIT", "TAKE PROFIT", "TP50", "TP100", "WIN", "PROFIT", "GAIN", "LUCRO"]):
            label = "WIN"
        elif any(x in blob for x in ["BREAKEVEN", "BREAK EVEN", "EMPATE", "BE"]):
            label = "BREAKEVEN"
        elif any(x in blob for x in ["TRADE_CLOSED", "CLOSED", "ENCERRADO", "FECHADO", "CLOSE"]):
            label = "UNKNOWN_CLOSED"
    return label or "UNKNOWN"


def _v222_extract_prices_and_side(event):
    entry = _v222_extract_numeric_any(event, [
        "entry", "entry_price", "entrada", "open_price", "price_entry", "avg_entry", "entry_avg"
    ])
    exit_price = _v222_extract_numeric_any(event, [
        "exit_price", "exit", "close_price", "closed_price", "preco_saida", "saida", "price_exit", "final_price"
    ])
    stop = _v222_extract_numeric_any(event, ["stop", "sl", "stop_loss", "stop_price", "stop_atual"])
    tp50 = _v222_extract_numeric_any(event, ["tp50", "take_profit", "tp", "target", "target_price"])
    side = _v222_deep_get_any(event, ["side", "direction", "lado"])
    side = str(side or "").strip().upper()
    if side == "BUY":
        side = "LONG"
    elif side == "SELL":
        side = "SHORT"
    return entry, exit_price, stop, tp50, side


def _v222_compute_pct_from_prices(event, label):
    entry, exit_price, stop, tp50, side = _v222_extract_prices_and_side(event)
    if entry is None or entry == 0:
        return None
    # Se não veio exit_price, usa stop/tp como proxy factual do evento fechado, quando o label indica.
    if exit_price is None:
        if any(x in label for x in ["LOSS", "STOP", "SL"]):
            exit_price = stop
        elif any(x in label for x in ["WIN", "TP", "PROFIT", "GAIN"]):
            exit_price = tp50
    if exit_price is None:
        return None
    try:
        if side == "SHORT":
            return round(((entry - exit_price) / entry) * 100.0, 6)
        # Default LONG se ausente, pois muitos logs não preservam side no subevento.
        return round(((exit_price - entry) / entry) * 100.0, 6)
    except Exception:
        return None


def _extract_outcome_payload(event):
    """V2.2.2: extrai outcome + valores reais de PnL/R de logs heterogêneos."""
    if not isinstance(event, dict):
        return None

    label = _v222_pick_label(event)

    pnl_pct = _v222_extract_numeric_any(event, [
        "pnl_pct", "result_pct", "profit_pct", "pnl_percent", "return_pct", "pnl_total_pct",
        "realized_pnl_pct", "realized_pct", "net_pnl_pct", "profit_loss_pct", "performance_pct",
        "change_pct", "roi_pct", "roi", "pnl_percentage", "final_pnl_pct", "trade_pnl_pct",
        "resultado_pct", "lucro_pct", "prejuizo_pct", "prejuízo_pct"
    ])
    result_r = _v222_extract_numeric_any(event, [
        "result_r", "pnl_r", "r", "r_result", "r_multiple", "profit_r", "r_total", "rr", "r_pct",
        "resultado_r", "risk_reward", "multiple_r"
    ])
    pnl_usdt = _v222_extract_numeric_any(event, [
        "pnl_usdt", "pnl", "profit_usdt", "realized_pnl", "net_pnl", "pnl_total_usdt",
        "profit", "loss", "profit_loss", "realized_profit", "resultado_usdt", "lucro_usdt"
    ])

    if pnl_pct is None:
        pnl_pct = _v222_compute_pct_from_prices(event, label)

    # Se R não veio mas temos pnl_pct e risk_pct, deriva R factual pela relação retorno/risco do trade.
    if result_r is None and pnl_pct is not None:
        risk_pct = _v222_extract_numeric_any(event, ["risk_pct", "risk", "risco", "initial_risk_pct"])
        if risk_pct not in (None, 0):
            try:
                result_r = round(float(pnl_pct) / abs(float(risk_pct)), 6)
            except Exception:
                result_r = None

    blob = _v222_text_blob(event)
    event_type = str(_v222_deep_get_any(event, ["event", "event_type", "type", "action"]) or "").upper()

    has_close_signal = any(token in blob for token in [
        "TRADE_CLOSED", "CLOSED", "FECHADO", "ENCERRADO", "STOP", "TP50", "TP100",
        "TAKE_PROFIT", "TAKE PROFIT", "LOSS", "WIN", "BREAKEVEN", "CLOSE"
    ]) or any(token in event_type for token in ["CLOSE", "CLOSED", "TRADE_CLOSED", "ENCERRADO"])
    has_numeric = pnl_pct is not None or result_r is not None or pnl_usdt is not None

    if not has_close_signal and not has_numeric and label in {"UNKNOWN", ""}:
        return None

    # Reclassifica pelo valor numérico quando possível. Isso corrige status genérico/enganoso.
    if result_r is not None:
        label = "WIN" if result_r > 0 else "LOSS" if result_r < 0 else "BREAKEVEN"
    elif pnl_pct is not None:
        label = "WIN" if pnl_pct > 0 else "LOSS" if pnl_pct < 0 else "BREAKEVEN"
    elif pnl_usdt is not None:
        label = "WIN" if pnl_usdt > 0 else "LOSS" if pnl_usdt < 0 else "BREAKEVEN"
    elif label in {"UNKNOWN", "UNKNOWN_CLOSED"}:
        # Mantém fechado, mas sem dizer win/loss quando não há valor.
        label = "UNKNOWN_CLOSED"

    return {
        "label": label,
        "pnl_pct": pnl_pct,
        "result_r": result_r,
        "pnl_usdt": pnl_usdt,
        "event_type": event_type,
        "dt": _outcome_identity(event).get("dt"),
        "source_event": str(_v222_deep_get_any(event, ["source", "event", "event_type"]) or "unknown")[:80],
        "parser_version": "V2.2.2",
    }


def _apply_outcome_to_policy(policy, decision, outcome_match):
    """V2.2.2: aplica outcome sem transformar close sem valor em loss/pnl zero."""
    _ensure_outcome_fields(policy)
    decision_name = _extract_decision(decision)

    if "DENY" in decision_name or "BLOCK" in decision_name:
        policy["no_executed_trade_outcome"] = _safe_int(policy.get("no_executed_trade_outcome")) + 1
        _recompute_policy_outcome_metrics(policy)
        return False

    if not outcome_match:
        policy["waiting_outcome"] = _safe_int(policy.get("waiting_outcome")) + 1
        _recompute_policy_outcome_metrics(policy)
        return False

    outcome = outcome_match.get("outcome") or {}
    label = str(outcome.get("label") or "UNKNOWN").upper()
    pnl_pct = outcome.get("pnl_pct")
    result_r = outcome.get("result_r")
    pnl_usdt = outcome.get("pnl_usdt")

    has_value = pnl_pct is not None or result_r is not None or pnl_usdt is not None
    policy["outcomes"] = _safe_int(policy.get("outcomes")) + 1

    is_win = False
    is_loss = False
    is_be = False
    if result_r is not None:
        is_win = float(result_r) > 0
        is_loss = float(result_r) < 0
        is_be = float(result_r) == 0
    elif pnl_pct is not None:
        is_win = float(pnl_pct) > 0
        is_loss = float(pnl_pct) < 0
        is_be = float(pnl_pct) == 0
    elif pnl_usdt is not None:
        is_win = float(pnl_usdt) > 0
        is_loss = float(pnl_usdt) < 0
        is_be = float(pnl_usdt) == 0
    else:
        # Só usa label como W/L quando o label é inequívoco; mas marca unknown para alertar falta de valor.
        if any(x in label for x in ["WIN", "TP", "PROFIT", "GAIN"]):
            is_win = True
        elif any(x in label for x in ["LOSS", "STOP", "SL"]):
            is_loss = True
        elif any(x in label for x in ["BE", "BREAKEVEN", "ZERO"]):
            is_be = True
        policy["outcome_unknown"] = _safe_int(policy.get("outcome_unknown")) + 1

    if is_win:
        policy["wins"] = _safe_int(policy.get("wins")) + 1
    elif is_loss:
        policy["losses"] = _safe_int(policy.get("losses")) + 1
    elif is_be:
        policy["breakeven"] = _safe_int(policy.get("breakeven")) + 1

    if pnl_pct is not None:
        pnl_pct = float(pnl_pct)
        policy["pnl_total_pct"] = round(_safe_float(policy.get("pnl_total_pct")) + pnl_pct, 6)
        if pnl_pct > 0:
            policy["gross_profit_pct"] = round(_safe_float(policy.get("gross_profit_pct")) + pnl_pct, 6)
        elif pnl_pct < 0:
            policy["gross_loss_pct"] = round(_safe_float(policy.get("gross_loss_pct")) + pnl_pct, 6)
        curve = policy.setdefault("pnl_curve_pct", [])
        last = float(curve[-1]) if curve else 0.0
        curve.append(round(last + pnl_pct, 6))
        if len(curve) > 500:
            del curve[:-500]

    if result_r is not None:
        policy["result_r_total"] = round(_safe_float(policy.get("result_r_total")) + float(result_r), 6)

    if pnl_usdt is not None:
        policy["pnl_total_usdt"] = round(_safe_float(policy.get("pnl_total_usdt")) + float(pnl_usdt), 6)

    # Contador auxiliar para diagnóstico de outcomes sem valor numérico.
    if not has_value:
        policy["outcomes_without_value"] = _safe_int(policy.get("outcomes_without_value")) + 1

    odt = outcome.get("dt")
    if odt:
        try:
            policy["last_outcome_at"] = odt.strftime("%d/%m/%Y %H:%M:%S")
        except Exception:
            policy["last_outcome_at"] = str(odt)
    policy["last_outcome_source"] = outcome_match.get("source_file")

    _recompute_policy_outcome_metrics(policy)
    return True


def _recompute_effect_summary(effect):
    """V2.2.2 summary com diagnóstico de outcomes sem valor."""
    policies = effect.get("policies") or {}
    values = [p for p in policies.values() if isinstance(p, dict)]
    total_decisions = sum(_safe_int(p.get("real_decisions", p.get("decisions"))) for p in values)
    total_outcomes = sum(_safe_int(p.get("outcomes")) for p in values)
    wins = sum(_safe_int(p.get("wins")) for p in values)
    losses = sum(_safe_int(p.get("losses")) for p in values)
    be = sum(_safe_int(p.get("breakeven")) for p in values)
    unknown = sum(_safe_int(p.get("outcome_unknown")) for p in values)
    without_value = sum(_safe_int(p.get("outcomes_without_value")) for p in values)
    pnl_total = round(sum(_safe_float(p.get("pnl_total_pct"), 0.0) for p in values), 6)
    r_total = round(sum(_safe_float(p.get("result_r_total"), 0.0) for p in values), 6)
    avg = 0.0
    if values:
        avg = sum(_safe_float(p.get("effect_score")) for p in values) / len(values)
    ready = sum(1 for p in values if p.get("readiness_label") == "READY_TO_LEARN")
    caution = sum(1 for p in values if p.get("readiness_label") == "LEARN_WITH_CAUTION")
    wait = sum(1 for p in values if p.get("readiness_label") == "WAIT_SAMPLE")

    effect["summary"] = {
        "policy_count": len(values),
        "decisions_processed": total_decisions,
        "decisions_matched": total_decisions,
        "outcomes_detected": total_outcomes,
        "wins": wins,
        "losses": losses,
        "breakeven": be,
        "outcome_unknown": unknown,
        "outcomes_without_value": without_value,
        "win_rate_pct": round((wins / total_outcomes) * 100.0, 2) if total_outcomes else 0.0,
        "pnl_total_pct": pnl_total,
        "result_r_total": r_total,
        "ready_to_learn": ready,
        "learn_with_caution": caution,
        "wait_sample": wait,
        "average_effect_score": round(avg, 2),
        "parser_version": "V2.2.2",
        "updated_at": _now(),
    }
