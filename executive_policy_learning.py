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
