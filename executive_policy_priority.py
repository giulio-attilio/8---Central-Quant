# ============================================================
# CENTRAL QUANT PRO
# EXECUTIVE POLICY PRIORITY V1
# Versão: 2026-07-05-EXECUTIVE-POLICY-PRIORITY-V1
#
# Objetivo:
# - Resolver conflitos entre múltiplas políticas executivas ativas.
# - Definir a política dominante por prioridade/severidade.
# - Produzir uma decisão executiva única para o Risk Manager / Execution Engine.
# - Não executa trades.
# - Não remove policies.
# - Não altera estado operacional de robôs.
# ============================================================

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

VERSION = "2026-07-05-EXECUTIVE-POLICY-PRIORITY-V1"
MODULE = "executive_policy_priority"

DATA_DIR = os.getenv("CENTRAL_DATA_DIR", "/opt/render/project/src/data")
POLICY_STATE_FILE = os.path.join(DATA_DIR, "executive_policy_state.json")
PRIORITY_LOG_FILE = os.path.join(DATA_DIR, "executive_policy_priority_log.jsonl")
PRIORITY_STATE_FILE = os.path.join(DATA_DIR, "executive_policy_priority_state.json")

POLICY_STATE_CANDIDATES = [
    POLICY_STATE_FILE,
    os.path.join(DATA_DIR, "executive_policies.json"),
    os.path.join(DATA_DIR, "executive_policy_manager_state.json"),
    os.path.join(DATA_DIR, "executive_policy_state.json"),
]

# Quanto menor o número, maior a prioridade.
# P0: trava absoluta/emergencial.
# P1: bloqueio estrutural ou por escopo.
# P2: bloqueio prudencial de amostra/learning.
# P3: bloqueio direcional.
# P4: limitação de tamanho/risco.
# P5: monitoramento.
PRIORITY_TABLE = {
    "EMERGENCY_STOP": 0,
    "KILL_SWITCH": 0,
    "BLOCK_ALL": 0,
    "TRADING_HALT": 0,
    "HALT_TRADING": 0,
    "MEMORY_CRITICAL": 0,
    "BROKER_NOT_READY": 0,

    "BLOCK_BOT": 1,
    "BLOCK_SETUP": 1,
    "BLOCK_SYMBOL": 1,
    "ONLY_CORE_BOTS": 1,
    "CAPITAL_PRESERVATION": 1,

    "WAIT_SAMPLE": 2,
    "WAIT_MORE_SAMPLE": 2,
    "LEARNING_LOCK": 2,
    "INSUFFICIENT_SAMPLE": 2,

    "NO_NEW_LONG": 3,
    "NO_NEW_SHORT": 3,
    "ALLOW_ONLY_LONG": 3,
    "ALLOW_ONLY_SHORT": 3,
    "LIMIT_NEW_LONG": 3,
    "LIMIT_NEW_SHORT": 3,

    "REDUCE_SIZE": 4,
    "FORCE_HALF_SIZE": 4,
    "MAX_RISK": 4,
    "CAP_RISK": 4,
    "LIMIT_RISK": 4,

    "NORMAL_WITH_MONITORING": 5,
    "MONITOR_ONLY": 5,
    "WATCH": 5,
}

DEFAULT_PRIORITY = 9


def _now_br() -> str:
    # Render normalmente roda UTC; mantemos BR fixo para consistência com a Central.
    try:
        return datetime.utcfromtimestamp(time.time() - 3 * 3600).strftime("%d/%m/%Y %H:%M:%S")
    except Exception:
        return datetime.now().strftime("%d/%m/%Y %H:%M:%S")


def _ensure_data_dir() -> None:
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
    except Exception:
        pass


def _safe_read_json(path: str, default: Any = None) -> Any:
    try:
        if not path or not os.path.exists(path):
            return default
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _safe_write_json(path: str, data: Any) -> bool:
    try:
        _ensure_data_dir()
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
        return True
    except Exception:
        return False


def _append_jsonl(path: str, payload: Dict[str, Any]) -> bool:
    try:
        _ensure_data_dir()
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        return True
    except Exception:
        return False


def _normalize_code(code: Any) -> str:
    return str(code or "").upper().strip().replace(" ", "_").replace("-", "_")


def _normalize_side(side: Any) -> str:
    side = str(side or "").upper().strip()
    if side == "BUY":
        return "LONG"
    if side == "SELL":
        return "SHORT"
    return side


def _normalize_policy_entry(item: Any) -> Optional[Dict[str, Any]]:
    if isinstance(item, str):
        code = _normalize_code(item)
        return {"code": code, "active": True} if code else None
    if isinstance(item, dict):
        code = _normalize_code(item.get("code") or item.get("policy_code") or item.get("name") or item.get("id"))
        if not code:
            return None
        normalized = dict(item)
        normalized["code"] = code
        normalized["active"] = bool(item.get("active", True))
        return normalized
    return None


def _extract_active_policies(state: Any) -> List[Dict[str, Any]]:
    raw_items: List[Any] = []
    if isinstance(state, list):
        raw_items = state
    elif isinstance(state, dict):
        for key in ["active_policies", "policies", "items", "data"]:
            if isinstance(state.get(key), list):
                raw_items = state.get(key, [])
                break
        if not raw_items and isinstance(state.get("active_codes"), list):
            raw_items = state.get("active_codes", [])
        if not raw_items:
            for key, value in state.items():
                if isinstance(value, dict):
                    item = dict(value)
                    item.setdefault("code", key)
                    raw_items.append(item)

    policies: List[Dict[str, Any]] = []
    seen = set()
    for item in raw_items:
        p = _normalize_policy_entry(item)
        if not p:
            continue
        code = p.get("code")
        if not code or code in seen:
            continue
        if p.get("active", True) is False:
            continue
        seen.add(code)
        policies.append(p)
    return policies


def _load_policy_state() -> Tuple[Any, Optional[str]]:
    for path in POLICY_STATE_CANDIDATES:
        data = _safe_read_json(path, default=None)
        if data is not None:
            return data, path
    return {}, None


def _policy_priority(policy: Dict[str, Any]) -> int:
    code = _normalize_code(policy.get("code"))
    explicit = policy.get("priority") or policy.get("level_priority")
    if explicit is not None:
        try:
            return int(explicit)
        except Exception:
            pass

    level = str(policy.get("level") or "").upper().strip()
    if level.startswith("P") and level[1:].isdigit():
        try:
            return int(level[1:])
        except Exception:
            pass

    return PRIORITY_TABLE.get(code, DEFAULT_PRIORITY)


def _policy_severity(policy: Dict[str, Any]) -> int:
    level = str(policy.get("level") or "").upper().strip()
    mapping = {"CRITICAL": 100, "HIGH": 80, "MEDIUM": 50, "LOW": 20, "INFO": 5}
    if level in mapping:
        return mapping[level]
    if level.startswith("P") and level[1:].isdigit():
        return max(0, 100 - int(level[1:]) * 10)
    code = _normalize_code(policy.get("code"))
    return max(0, 100 - PRIORITY_TABLE.get(code, DEFAULT_PRIORITY) * 10)


def _policy_targets_trade(policy: Dict[str, Any], trade_payload: Optional[Dict[str, Any]]) -> bool:
    if not trade_payload:
        return True

    trade_payload = trade_payload or {}
    bot = _normalize_code(trade_payload.get("bot"))
    setup = _normalize_code(trade_payload.get("setup") or trade_payload.get("strategy") or trade_payload.get("signal_type"))
    symbol = _normalize_code(trade_payload.get("symbol") or trade_payload.get("ativo") or trade_payload.get("pair"))
    side = _normalize_side(trade_payload.get("side") or trade_payload.get("direction"))
    category = _normalize_code(trade_payload.get("category") or trade_payload.get("bot_category"))

    code = _normalize_code(policy.get("code"))
    p_bot = _normalize_code(policy.get("bot") or policy.get("target_bot"))
    p_setup = _normalize_code(policy.get("setup") or policy.get("target_setup"))
    p_symbol = _normalize_code(policy.get("symbol") or policy.get("target_symbol"))
    p_side = _normalize_side(policy.get("side") or policy.get("target_side"))
    p_category = _normalize_code(policy.get("category") or policy.get("target_category"))

    if p_bot and bot and p_bot != bot:
        return False
    if p_setup and setup and p_setup != setup:
        return False
    if p_symbol and symbol and p_symbol != symbol:
        return False
    if p_side and side and p_side != side:
        return False
    if p_category and category and p_category != category:
        return False

    if code in {"NO_NEW_LONG", "LIMIT_NEW_LONG", "ALLOW_ONLY_SHORT"} and side and side != "LONG":
        return False
    if code in {"NO_NEW_SHORT", "LIMIT_NEW_SHORT", "ALLOW_ONLY_LONG"} and side and side != "SHORT":
        return False
    if code == "ONLY_CORE_BOTS" and category in {"CORE", "CORE_BOT"}:
        return False

    return True


def _policy_effect(policy: Dict[str, Any], trade_payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    code = _normalize_code(policy.get("code"))
    side = _normalize_side((trade_payload or {}).get("side") or (trade_payload or {}).get("direction"))
    targets_trade = _policy_targets_trade(policy, trade_payload)

    effect = {
        "decision": "ALLOW",
        "allowed": True,
        "action": "ALLOW",
        "size_multiplier": 1.0,
        "max_risk_pct": None,
        "reason": None,
    }

    if not targets_trade:
        effect["action"] = "NOT_APPLICABLE"
        effect["reason"] = "Policy ativa, mas não aplicável a este trade."
        return effect

    if code in {"EMERGENCY_STOP", "KILL_SWITCH", "BLOCK_ALL", "TRADING_HALT", "HALT_TRADING", "MEMORY_CRITICAL", "BROKER_NOT_READY"}:
        effect.update({"decision": "DENY", "allowed": False, "action": "BLOCK", "reason": f"{code}: bloqueio executivo de prioridade máxima."})
    elif code in {"WAIT_SAMPLE", "WAIT_MORE_SAMPLE", "LEARNING_LOCK", "INSUFFICIENT_SAMPLE"}:
        effect.update({"decision": "DENY", "allowed": False, "action": "BLOCK", "reason": f"{code}: aguardando amostra/learning suficiente."})
    elif code in {"BLOCK_BOT", "BLOCK_SETUP", "BLOCK_SYMBOL", "ONLY_CORE_BOTS", "CAPITAL_PRESERVATION"}:
        effect.update({"decision": "DENY", "allowed": False, "action": "BLOCK", "reason": f"{code}: escopo bloqueado por política executiva."})
    elif code == "NO_NEW_LONG" and side == "LONG":
        effect.update({"decision": "DENY", "allowed": False, "action": "BLOCK", "reason": "NO_NEW_LONG: novas entradas LONG bloqueadas."})
    elif code == "NO_NEW_SHORT" and side == "SHORT":
        effect.update({"decision": "DENY", "allowed": False, "action": "BLOCK", "reason": "NO_NEW_SHORT: novas entradas SHORT bloqueadas."})
    elif code == "ALLOW_ONLY_LONG" and side == "SHORT":
        effect.update({"decision": "DENY", "allowed": False, "action": "BLOCK", "reason": "ALLOW_ONLY_LONG: somente LONG permitido."})
    elif code == "ALLOW_ONLY_SHORT" and side == "LONG":
        effect.update({"decision": "DENY", "allowed": False, "action": "BLOCK", "reason": "ALLOW_ONLY_SHORT: somente SHORT permitido."})
    elif code in {"LIMIT_NEW_LONG", "LIMIT_NEW_SHORT", "REDUCE_SIZE", "FORCE_HALF_SIZE"}:
        try:
            mult = float(policy.get("size_multiplier", policy.get("multiplier", 0.5)))
        except Exception:
            mult = 0.5
        mult = max(0.0, min(1.0, mult))
        effect.update({"decision": "ALLOW_WITH_LIMITS", "allowed": True, "action": "REDUCE_SIZE", "size_multiplier": mult, "reason": f"{code}: entrada permitida com lote reduzido."})
    elif code in {"MAX_RISK", "CAP_RISK", "LIMIT_RISK"}:
        try:
            cap = float(policy.get("max_risk_pct") or policy.get("risk_cap_pct") or policy.get("risk_pct"))
        except Exception:
            cap = None
        effect.update({"decision": "ALLOW_WITH_LIMITS", "allowed": True, "action": "CAP_RISK", "max_risk_pct": cap, "reason": f"{code}: risco limitado pela política executiva."})
    elif code in {"NORMAL_WITH_MONITORING", "MONITOR_ONLY", "WATCH"}:
        effect.update({"decision": "ALLOW", "allowed": True, "action": "MONITOR", "reason": f"{code}: monitoramento ativo."})
    else:
        # Política desconhecida: não bloqueia por padrão na V1, mas aparece no relatório.
        effect.update({"decision": "ALLOW", "allowed": True, "action": "UNKNOWN_POLICY_MONITOR", "reason": f"{code}: policy desconhecida na Priority V1; monitorando."})

    return effect


def resolve_executive_policy_priority(trade_payload: Optional[Dict[str, Any]] = None, policies: Optional[List[Dict[str, Any]]] = None, commit: bool = True) -> Dict[str, Any]:
    state, state_file = _load_policy_state()
    active_policies = policies if isinstance(policies, list) else _extract_active_policies(state)

    ranked: List[Dict[str, Any]] = []
    for p in active_policies:
        if not isinstance(p, dict):
            continue
        item = dict(p)
        item["code"] = _normalize_code(item.get("code"))
        item["priority"] = _policy_priority(item)
        item["severity"] = _policy_severity(item)
        item["targets_trade"] = _policy_targets_trade(item, trade_payload)
        item["effect"] = _policy_effect(item, trade_payload)
        ranked.append(item)

    # A dominante deve ser aplicável ao trade quando há trade_payload.
    applicable = [p for p in ranked if p.get("targets_trade", True)]
    ranked_sorted = sorted(ranked, key=lambda p: (p.get("priority", DEFAULT_PRIORITY), -p.get("severity", 0), str(p.get("code") or "")))
    applicable_sorted = sorted(applicable, key=lambda p: (p.get("priority", DEFAULT_PRIORITY), -p.get("severity", 0), str(p.get("code") or "")))
    dominant = applicable_sorted[0] if applicable_sorted else None

    decision = "ALLOW"
    allowed = True
    reasons: List[str] = []
    warnings: List[str] = []
    size_multiplier = 1.0
    max_risk_pct = None

    if dominant:
        effect = dominant.get("effect") or {}
        decision = effect.get("decision") or "ALLOW"
        allowed = bool(effect.get("allowed", True))
        if effect.get("reason"):
            reasons.append(str(effect.get("reason")))
        if effect.get("size_multiplier") not in [None, 1, 1.0]:
            try:
                size_multiplier = min(size_multiplier, float(effect.get("size_multiplier")))
            except Exception:
                size_multiplier = 0.5
        if effect.get("max_risk_pct") is not None:
            try:
                max_risk_pct = float(effect.get("max_risk_pct"))
            except Exception:
                max_risk_pct = effect.get("max_risk_pct")

    # Mesmo que a policy dominante seja bloqueio, preservamos alertas de limites secundários.
    for item in applicable_sorted[1:]:
        effect = item.get("effect") or {}
        if effect.get("decision") == "ALLOW_WITH_LIMITS":
            warnings.append(effect.get("reason") or f"{item.get('code')}: limite secundário ativo.")
            if effect.get("size_multiplier") not in [None, 1, 1.0]:
                try:
                    size_multiplier = min(size_multiplier, float(effect.get("size_multiplier")))
                except Exception:
                    pass
            if effect.get("max_risk_pct") is not None and max_risk_pct is None:
                max_risk_pct = effect.get("max_risk_pct")

    result = {
        "ok": True,
        "module": MODULE,
        "version": VERSION,
        "generated_at": _now_br(),
        "source": "executive_policy_priority",
        "state_file": state_file,
        "active_policy_count": len(active_policies),
        "applicable_policy_count": len(applicable),
        "active_codes": [p.get("code") for p in ranked_sorted],
        "applicable_codes": [p.get("code") for p in applicable_sorted],
        "dominant_policy": _compact_policy(dominant) if dominant else None,
        "dominant_code": dominant.get("code") if dominant else None,
        "priority_level": dominant.get("priority") if dominant else None,
        "decision": decision,
        "allowed": allowed,
        "size_multiplier": size_multiplier,
        "max_risk_pct": max_risk_pct,
        "reasons": reasons,
        "warnings": warnings,
        "ranked_policies": [_compact_policy(p) for p in ranked_sorted],
        "notes": [
            "Priority V1 não cria, remove ou executa policies.",
            "Quanto menor o priority, maior a força da policy.",
            "A policy dominante é a primeira aplicável ao trade/contexto.",
        ],
    }

    if commit:
        _safe_write_json(PRIORITY_STATE_FILE, result)
        _append_jsonl(PRIORITY_LOG_FILE, result)

    return result


def _compact_policy(policy: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(policy, dict):
        return None
    effect = policy.get("effect") or {}
    return {
        "code": policy.get("code"),
        "priority": policy.get("priority"),
        "severity": policy.get("severity"),
        "level": policy.get("level"),
        "title": policy.get("title"),
        "category": policy.get("category"),
        "target_bot": policy.get("target_bot") or policy.get("bot"),
        "target_symbol": policy.get("target_symbol") or policy.get("symbol"),
        "target_side": policy.get("target_side") or policy.get("side"),
        "targets_trade": policy.get("targets_trade", True),
        "effect": effect,
        "release_condition": policy.get("release_condition"),
    }


def get_executive_policy_priority_health() -> Dict[str, Any]:
    state, state_file = _load_policy_state()
    active = _extract_active_policies(state)
    last = _safe_read_json(PRIORITY_STATE_FILE, default={}) or {}
    return {
        "ok": True,
        "loaded": True,
        "module": MODULE,
        "version": VERSION,
        "generated_at": _now_br(),
        "policy_state_file": state_file,
        "priority_state_file": PRIORITY_STATE_FILE,
        "priority_log_file": PRIORITY_LOG_FILE,
        "active_policy_count": len(active),
        "active_codes": [_normalize_code(p.get("code")) for p in active],
        "last_run_at": last.get("generated_at"),
        "last_dominant_code": last.get("dominant_code"),
        "last_decision": last.get("decision"),
        "notes": ["Health apenas informa o estado do Priority V1."],
    }


def build_executive_policy_priority_report(result: Optional[Dict[str, Any]] = None) -> str:
    result = result or resolve_executive_policy_priority(trade_payload=None, commit=True)
    dominant = result.get("dominant_policy") or {}
    lines = [
        "🏛️ EXECUTIVE POLICY PRIORITY — CENTRAL QUANT",
        f"Data/hora: {result.get('generated_at') or _now_br()}",
        f"Status: {'✅' if result.get('ok') else '❌'}",
        f"Versão: {VERSION}",
        "",
        f"Policies ativas: {result.get('active_policy_count', 0)}",
        f"Policies aplicáveis: {result.get('applicable_policy_count', 0)}",
        f"Decisão executiva: {result.get('decision')}",
        f"Permitido: {result.get('allowed')}",
        f"Size multiplier: {result.get('size_multiplier')}",
        f"Max risk pct: {result.get('max_risk_pct')}",
        "",
    ]

    if dominant:
        lines += [
            "Policy dominante:",
            f"- Código: {dominant.get('code')}",
            f"- Prioridade: P{dominant.get('priority')}",
            f"- Título: {dominant.get('title') or 'N/A'}",
            f"- Efeito: {(dominant.get('effect') or {}).get('action')}",
            f"- Motivo: {(dominant.get('effect') or {}).get('reason')}",
            "",
        ]
    else:
        lines += ["✅ Nenhuma policy dominante ativa neste ciclo.", ""]

    ranked = result.get("ranked_policies") or []
    if ranked:
        lines.append("Ranking ativo:")
        for item in ranked[:15]:
            effect = item.get("effect") or {}
            lines.append(
                f"- P{item.get('priority')} | {item.get('code')} | "
                f"aplicável={item.get('targets_trade')} | ação={effect.get('action')}"
            )
        lines.append("")

    reasons = result.get("reasons") or []
    warnings = result.get("warnings") or []
    if reasons:
        lines.append("Motivos:")
        for reason in reasons[:10]:
            lines.append(f"- {reason}")
        lines.append("")
    if warnings:
        lines.append("Avisos:")
        for warning in warnings[:10]:
            lines.append(f"- {warning}")
        lines.append("")

    lines += [
        "Notas:",
        "- Priority V1 resolve conflito entre policies ativas.",
        "- Quanto menor P, maior a prioridade.",
        "- O Risk Manager pode usar a policy dominante como decisão executiva final.",
    ]
    return "\n".join(lines)


def read_executive_policy_priority_log(limit: int = 20) -> Dict[str, Any]:
    try:
        limit = max(1, min(200, int(limit)))
    except Exception:
        limit = 20
    if not os.path.exists(PRIORITY_LOG_FILE):
        return {"ok": True, "items": [], "count": 0, "log_file": PRIORITY_LOG_FILE}
    items: List[Dict[str, Any]] = []
    try:
        with open(PRIORITY_LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()[-limit:]
        for line in lines:
            try:
                items.append(json.loads(line))
            except Exception:
                pass
        return {"ok": True, "items": items, "count": len(items), "log_file": PRIORITY_LOG_FILE}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "items": [], "log_file": PRIORITY_LOG_FILE}


if __name__ == "__main__":
    print(build_executive_policy_priority_report())
