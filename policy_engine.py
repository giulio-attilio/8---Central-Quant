# ==============================================================================
# CENTRAL QUANT - POLICY ENGINE
# Versão: 2026-07-02-POLICY-ENGINE-V1
#
# Objetivo:
# - Separar política operacional do código dos robôs.
# - Manter uma camada auditável entre Learning Engine e execução.
# - Por enquanto NÃO altera decisões automaticamente.
# - Entrega estado, relatório e simulação de score/política.
# ==============================================================================

import json
import os
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import defaultdict

TIMEZONE_BR = timezone(timedelta(hours=-3))
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data"))).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)

POLICY_STATE_FILE = DATA_DIR / "policy_state.json"
POLICY_AUDIT_FILE = DATA_DIR / "policy_audit.jsonl"
POLICY_EXPORT_FILE = DATA_DIR / "policy_export.json"

VERSION = "2026-07-02-POLICY-ENGINE-V1"

DEFAULT_POLICY = {
    "version": VERSION,
    "mode": "OBSERVE",
    "updated_at": None,
    "description": "Policy Engine inicial. Não altera operações automaticamente.",
    "global": {
        "enabled": True,
        "adaptive_enabled": False,
        "max_learning_adjustment": 0,
        "min_confidence_to_apply": 90,
        "require_manual_approval": True,
    },
    "bots": {
        "FALCON": {
            "enabled": True,
            "score_min": 70,
            "adaptive_enabled": False,
            "learning_adjustment": 0,
            "confidence": 0,
            "reason": "Aguardando amostra estatística suficiente.",
        },
        "PREDATOR": {
            "enabled": True,
            "score_min": 70,
            "adaptive_enabled": False,
            "learning_adjustment": 0,
            "confidence": 0,
            "reason": "Aguardando amostra estatística suficiente.",
        },
        "TURTLE": {
            "enabled": True,
            "score_min": 70,
            "adaptive_enabled": False,
            "learning_adjustment": 0,
            "confidence": 0,
            "reason": "Aguardando amostra estatística suficiente.",
        },
        "DONKEY": {
            "enabled": True,
            "score_min": 70,
            "adaptive_enabled": False,
            "learning_adjustment": 0,
            "confidence": 0,
            "reason": "Aguardando amostra estatística suficiente.",
        },
        "TRENDPRO": {
            "enabled": True,
            "score_min": 70,
            "adaptive_enabled": False,
            "learning_adjustment": 0,
            "confidence": 0,
            "reason": "Aguardando amostra estatística suficiente.",
        },
        "COBRA": {
            "enabled": True,
            "score_min": 70,
            "adaptive_enabled": False,
            "learning_adjustment": 0,
            "confidence": 0,
            "reason": "Aguardando amostra estatística suficiente.",
        },
        "MEME": {
            "enabled": True,
            "score_min": 70,
            "adaptive_enabled": False,
            "learning_adjustment": 0,
            "confidence": 0,
            "reason": "Aguardando amostra estatística suficiente.",
        },
    },
    "dynamic_rules": [],
}


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


def _read_json(path, default):
    try:
        if not path.exists():
            return default
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else default
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
    except Exception:
        return False


def _merge_defaults(default, current):
    if not isinstance(default, dict):
        return current
    if not isinstance(current, dict):
        return dict(default)
    merged = dict(default)
    for key, value in current.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_defaults(merged[key], value)
        else:
            merged[key] = value
    return merged


def ensure_policy_state():
    if not POLICY_STATE_FILE.exists():
        state = dict(DEFAULT_POLICY)
        state["updated_at"] = data_hora_sp_str()
        _write_json(POLICY_STATE_FILE, state)
    if not POLICY_AUDIT_FILE.exists():
        POLICY_AUDIT_FILE.touch()


ensure_policy_state()


def load_policy_state():
    state = _read_json(POLICY_STATE_FILE, {})
    state = _merge_defaults(DEFAULT_POLICY, state)
    return state


def save_policy_state(state, reason="policy_state_update"):
    if not isinstance(state, dict):
        return {"ok": False, "error": "state precisa ser dict"}
    state["version"] = VERSION
    state["updated_at"] = data_hora_sp_str()
    ok = _write_json(POLICY_STATE_FILE, state)
    audit = {
        "ts": data_hora_sp_str(),
        "epoch": time.time(),
        "event": "POLICY_STATE_UPDATED",
        "reason": reason,
        "ok": ok,
        "state": state,
    }
    _append_jsonl(POLICY_AUDIT_FILE, audit)
    return {"ok": ok, "state": state}


def get_status():
    state = load_policy_state()
    bots = state.get("bots") or {}
    adaptive_bots = [k for k, v in bots.items() if isinstance(v, dict) and v.get("adaptive_enabled")]
    return {
        "ok": True,
        "module": "policy_engine",
        "version": VERSION,
        "data_dir": str(DATA_DIR),
        "state_file": str(POLICY_STATE_FILE),
        "audit_file": str(POLICY_AUDIT_FILE),
        "export_file": str(POLICY_EXPORT_FILE),
        "mode": state.get("mode"),
        "global_adaptive_enabled": bool((state.get("global") or {}).get("adaptive_enabled")),
        "bots_configured": len(bots),
        "adaptive_bots": adaptive_bots,
    }


def normalize_bot(bot):
    b = str(bot or "").upper().strip()
    aliases = {
        "SMARTPREDATOR": "PREDATOR",
        "SMART_PREDATOR": "PREDATOR",
        "TREND": "TRENDPRO",
        "TREND_PRO": "TRENDPRO",
    }
    return aliases.get(b, b)


def get_bot_policy(bot):
    state = load_policy_state()
    bot_key = normalize_bot(bot)
    bots = state.get("bots") or {}
    return bots.get(bot_key, {
        "enabled": True,
        "score_min": 70,
        "adaptive_enabled": False,
        "learning_adjustment": 0,
        "confidence": 0,
        "reason": "Política padrão aplicada por ausência de configuração específica.",
    })


def calculate_policy_decision(bot=None, score=None, context=None, dry_run=True):
    """
    Calcula a decisão política para um sinal.
    V1 é conservador: adaptive_enabled=false por padrão e max_learning_adjustment=0.
    """
    state = load_policy_state()
    bot_key = normalize_bot(bot)
    bot_policy = get_bot_policy(bot_key)
    global_policy = state.get("global") or {}

    original_score = _safe_float(score, None)
    score_min = _safe_float(bot_policy.get("score_min"), 70)
    confidence = _safe_float(bot_policy.get("confidence"), 0) or 0
    requested_adjustment = _safe_float(bot_policy.get("learning_adjustment"), 0) or 0
    max_adjustment = abs(_safe_float(global_policy.get("max_learning_adjustment"), 0) or 0)
    min_confidence = _safe_float(global_policy.get("min_confidence_to_apply"), 90) or 90

    global_adaptive = bool(global_policy.get("adaptive_enabled"))
    bot_adaptive = bool(bot_policy.get("adaptive_enabled"))
    can_apply = bool(global_adaptive and bot_adaptive and confidence >= min_confidence and max_adjustment > 0)

    applied_adjustment = 0
    if can_apply:
        applied_adjustment = max(-max_adjustment, min(max_adjustment, requested_adjustment))

    adjusted_score = None if original_score is None else original_score + applied_adjustment
    allowed_by_score = None if adjusted_score is None else adjusted_score >= score_min

    decision = {
        "ok": True,
        "dry_run": bool(dry_run),
        "mode": state.get("mode"),
        "bot": bot_key,
        "original_score": original_score,
        "adjusted_score": adjusted_score,
        "score_min": score_min,
        "learning_adjustment_requested": requested_adjustment,
        "learning_adjustment_applied": applied_adjustment,
        "confidence": confidence,
        "adaptive_allowed": can_apply,
        "allowed_by_score": allowed_by_score,
        "reason": bot_policy.get("reason"),
        "policy": bot_policy,
    }
    if isinstance(context, dict):
        decision["context"] = {
            "hour": context.get("hour"),
            "session_br": context.get("session_br"),
            "market_regime": context.get("market_regime"),
            "btc_alignment": context.get("btc_alignment"),
            "volatility": context.get("volatility"),
            "score_bucket": context.get("score_bucket"),
            "risk_bucket": context.get("risk_bucket"),
        }
    return decision


def apply_policy_to_event(event, dry_run=True):
    if not isinstance(event, dict):
        return calculate_policy_decision(dry_run=dry_run)
    context = event.get("context") if isinstance(event.get("context"), dict) else event
    return calculate_policy_decision(
        bot=event.get("bot") or event.get("source"),
        score=event.get("score"),
        context=context,
        dry_run=dry_run,
    )


def build_policy_report(bot=None):
    state = load_policy_state()
    status = get_status()
    bots = state.get("bots") or {}
    bot_key = normalize_bot(bot) if bot else None

    lines = [
        "🧭 POLICY ENGINE — CENTRAL QUANT",
        f"Data/hora: {data_hora_sp_str()}",
        f"Status: {'OK' if status.get('ok') else 'ERRO'}",
        f"Modo: {state.get('mode')}",
        "",
        "Função:",
        "Separar política operacional do código dos robôs.",
        "Nesta V1, nenhuma decisão é alterada automaticamente.",
        "",
        "Estado global:",
        f"Adaptive enabled: {bool((state.get('global') or {}).get('adaptive_enabled'))}",
        f"Require manual approval: {bool((state.get('global') or {}).get('require_manual_approval'))}",
        f"Max learning adjustment: {(state.get('global') or {}).get('max_learning_adjustment')}",
        f"Min confidence to apply: {(state.get('global') or {}).get('min_confidence_to_apply')}",
        "",
        "Políticas por bot:",
    ]

    items = {bot_key: get_bot_policy(bot_key)} if bot_key else bots
    for key, policy in items.items():
        if not isinstance(policy, dict):
            continue
        lines += [
            "",
            f"{key}",
            f"Score mínimo: {policy.get('score_min')}",
            f"Adaptive: {bool(policy.get('adaptive_enabled'))}",
            f"Learning adjustment: {policy.get('learning_adjustment')}",
            f"Confiança: {policy.get('confidence')}",
            f"Motivo: {policy.get('reason')}",
        ]

    lines += [
        "",
        "Próximo passo:",
        "Quando o Learning Engine tiver amostra suficiente, ele poderá sugerir políticas.",
        "O Policy Engine aplicará apenas regras aprovadas, rastreáveis e com confiança mínima.",
    ]
    return "\n".join(lines)


def build_policy_payload():
    state = load_policy_state()
    payload = {
        "ok": True,
        "generated_at": data_hora_sp_str(),
        "status": get_status(),
        "state": state,
    }
    _write_json(POLICY_EXPORT_FILE, payload)
    return payload


def build_policy_audit_payload(limit=100):
    try:
        limit = int(limit or 100)
    except Exception:
        limit = 100
    rows = []
    try:
        if POLICY_AUDIT_FILE.exists():
            with POLICY_AUDIT_FILE.open("r", encoding="utf-8") as f:
                for line in f.readlines()[-limit:]:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rows.append(json.loads(line))
                    except Exception:
                        rows.append({"raw": line})
    except Exception:
        rows = []
    return {"ok": True, "generated_at": data_hora_sp_str(), "items": rows, "count": len(rows)}


def propose_policy(bot, learning_adjustment=0, confidence=0, reason=None, score_min=None):
    """
    Registra uma proposta de política sem ativar adaptação automática.
    Usado futuramente pelo Learning Engine.
    """
    state = load_policy_state()
    bot_key = normalize_bot(bot)
    bots = state.setdefault("bots", {})
    current = get_bot_policy(bot_key)
    proposed = dict(current)
    proposed["learning_adjustment"] = _safe_float(learning_adjustment, 0) or 0
    proposed["confidence"] = _safe_float(confidence, 0) or 0
    proposed["reason"] = reason or "Proposta gerada pelo Learning Engine."
    proposed["adaptive_enabled"] = False
    if score_min is not None:
        proposed["score_min"] = _safe_float(score_min, current.get("score_min", 70))
    bots[bot_key] = proposed
    state["mode"] = "RECOMMENDATION"
    return save_policy_state(state, reason=f"policy_proposal_{bot_key}")


if __name__ == "__main__":
    print(json.dumps(get_status(), ensure_ascii=False, indent=2))
