# -*- coding: utf-8 -*-
"""
Executive Policy Learning V2.0 — Central Quant
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

VERSION = "2026-07-05-EXECUTIVE-POLICY-LEARNING-V2.0"

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("CENTRAL_DATA_DIR", str(BASE_DIR / "data")))
DATA_DIR.mkdir(exist_ok=True)

TIMELINE_FILE = Path(os.environ.get("EXECUTIVE_POLICY_TIMELINE_FILE", str(DATA_DIR / "executive_policy_timeline.jsonl")))
STATE_FILE = Path(os.environ.get("EXECUTIVE_POLICY_LEARNING_STATE_FILE", str(DATA_DIR / "executive_policy_learning_state.json")))
STATS_FILE = Path(os.environ.get("EXECUTIVE_POLICY_LEARNING_STATS_FILE", str(DATA_DIR / "executive_policy_learning_stats.json")))
LOG_FILE = Path(os.environ.get("EXECUTIVE_POLICY_LEARNING_LOG_FILE", str(DATA_DIR / "executive_policy_learning_log.jsonl")))

MAX_EVENTS_PER_RUN = int(os.environ.get("EXECUTIVE_POLICY_LEARNING_MAX_EVENTS_PER_RUN", "500"))
MIN_SAMPLE_FOR_CONFIDENCE = int(os.environ.get("EXECUTIVE_POLICY_LEARNING_MIN_SAMPLE", "10"))

# V2.0 — correlação entre Policy Timeline e Decision Log.
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
        "🧠 EXECUTIVE POLICY LEARNING — CENTRAL QUANT V2.0",
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
# EXECUTIVE POLICY LEARNING V2.0
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
    Não é usado em loop pesado; V2.0 trabalha com limite.
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


def _active_policy_codes_for_decision(decision_dt, policy_events, window_minutes=POLICY_DECISION_WINDOW_MINUTES):
    """
    V2.0: associação simples.
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
    V2.0:
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
        dt = _decision_time(decision)
        codes = _active_policy_codes_for_decision(dt, policy_events)

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
        "🧠 EXECUTIVE POLICY LEARNING V2.0 — POLICY EFFECT",
        f"Data/hora: {_now()}",
        "",
        f"Status: {'✅' if result.get('ok') else '❌'}",
        f"Decisões lidas agora: {result.get('decisions_read', 0)}",
        f"Decisões processadas agora: {result.get('decisions_processed', 0)}",
        f"Matches policy↔decision: {result.get('decisions_matched', 0)}",
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
            "A V2.0 precisa de eventos no Timeline e decisões no Decision Log dentro da janela configurada.",
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
        "V2.0 correlaciona Timeline + Decision Log.",
        "V2.1 deve cruzar com Lifecycle/Outcome para PnL, Profit Factor e Drawdown.",
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
        "⚖️ POLICY COMPARE — CENTRAL QUANT V2.0",
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
        "💡 POLICY INSIGHTS — CENTRAL QUANT V2.0",
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



if __name__ == "__main__":
    print(build_executive_policy_learning_report())
