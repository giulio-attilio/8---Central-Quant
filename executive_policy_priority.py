# ============================================================
# CENTRAL QUANT PRO
# EXECUTIVE POLICY PRIORITY V1.1
# Versão: 2026-07-05-EXECUTIVE-POLICY-PRIORITY-V1.1
#
# Objetivo:
# - Resolver conflitos entre múltiplas políticas executivas ativas.
# - Definir a política dominante por prioridade/severidade.
# - Produzir uma decisão executiva única para Risk Manager / Execution Engine.
# - Usar o Executive Policy Manager como FONTE ÚNICA DE VERDADE.
# - Não executa trades.
# - Não remove policies.
# - Não altera estado operacional de robôs.
#
# Correção V1.1:
# - Remove leitura própria de arquivos de policies.
# - Consome executive_policy_manager.get_active_policies().
# - Garante que /policies e /policypriority enxerguem a mesma base.
# - Corrige horário para America/Sao_Paulo sem subtrair 3h duas vezes.
# ============================================================

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

VERSION = "2026-07-05-EXECUTIVE-POLICY-PRIORITY-V1.1"
MODULE = "executive_policy_priority"

TIMEZONE_BR = timezone(timedelta(hours=-3))
DATA_DIR = os.getenv("CENTRAL_DATA_DIR", "/opt/render/project/src/data")
PRIORITY_LOG_FILE = os.path.join(DATA_DIR, "executive_policy_priority_log.jsonl")
PRIORITY_STATE_FILE = os.path.join(DATA_DIR, "executive_policy_priority_state.json")

try:
    import executive_policy_manager
    EXECUTIVE_POLICY_MANAGER_LOADED = True
    EXECUTIVE_POLICY_MANAGER_ERROR = None
except Exception as exc:
    executive_policy_manager = None
    EXECUTIVE_POLICY_MANAGER_LOADED = False
    EXECUTIVE_POLICY_MANAGER_ERROR = str(exc)


# Quanto menor o número, maior a prioridade.
PRIORITY_TABLE = {
    # P0 — trava absoluta/emergencial
    "EMERGENCY_STOP": 0,
    "KILL_SWITCH": 0,
    "BLOCK_ALL": 0,
    "TRADING_HALT": 0,
    "HALT_TRADING": 0,
    "MEMORY_CRITICAL": 0,
    "BROKER_NOT_READY": 0,

    # P1 — bloqueio estrutural/escopo
    "BLOCK_BOT": 1,
    "BLOCK_SETUP": 1,
    "BLOCK_SYMBOL": 1,
    "ONLY_CORE_BOTS": 1,
    "CAPITAL_PRESERVATION": 1,

    # P2 — prudência/learning/amostra
    "WAIT_SAMPLE": 2,
    "WAIT_MORE_SAMPLE": 2,
    "LEARNING_LOCK": 2,
    "INSUFFICIENT_SAMPLE": 2,

    # P3 — direção/concentração
    "NO_NEW_LONG": 3,
    "NO_NEW_SHORT": 3,
    "ALLOW_ONLY_LONG": 3,
    "ALLOW_ONLY_SHORT": 3,
    "LIMIT_NEW_LONG": 3,
    "LIMIT_NEW_SHORT": 3,

    # P4 — tamanho/risco
    "REDUCE_SIZE": 4,
    "FORCE_HALF_SIZE": 4,
    "MAX_RISK": 4,
    "CAP_RISK": 4,
    "LIMIT_RISK": 4,

    # P5 — monitoramento
    "NORMAL_WITH_MONITORING": 5,
    "MONITOR_ONLY": 5,
    "WATCH": 5,
}

DEFAULT_PRIORITY = 9


def _now_br() -> str:
    return datetime.now(TIMEZONE_BR).strftime("%d/%m/%Y %H:%M:%S")


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


def _normalize_symbol(symbol: Any) -> str:
    s = str(symbol or "").upper().strip()
    s = s.replace("/USDT:USDT", "USDT")
    s = s.replace("/USDT", "USDT")
    s = s.replace(":USDT", "")
    s = s.replace("-", "")
    return s


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
        return {"code": code, "enabled": True} if code else None

    if isinstance(item, dict):
        code = _normalize_code(
            item.get("code")
            or item.get("policy_code")
            or item.get("name")
            or item.get("id")
        )
        if not code:
            return None
        normalized = dict(item)
        normalized["code"] = code
        normalized.setdefault("enabled", item.get("active", True))
        return normalized

    return None


def _extract_active_policies_from_any(value: Any) -> List[Dict[str, Any]]:
    """
    Normaliza retornos possíveis do Executive Policy Manager:
    - list[dict]
    - {"policies": [...]}
    - {"active_policies": [...]}
    - {"items": [...]}
    - {"payload": {"policies": [...]}}
    - {"active_codes": [...]}
    """
    raw_items: List[Any] = []

    if isinstance(value, list):
        raw_items = value

    elif isinstance(value, dict):
        payload = value.get("payload")
        if isinstance(payload, dict):
            nested = _extract_active_policies_from_any(payload)
            if nested:
                return nested

        for key in ["active_policies", "policies", "items", "data"]:
            if isinstance(value.get(key), list):
                raw_items = value.get(key, [])
                break

        if not raw_items and isinstance(value.get("active_codes"), list):
            raw_items = value.get("active_codes", [])

        if not raw_items:
            for key, item in value.items():
                if isinstance(item, dict):
                    candidate = dict(item)
                    candidate.setdefault("code", key)
                    raw_items.append(candidate)

    policies: List[Dict[str, Any]] = []
    seen = set()

    for raw in raw_items:
        policy = _normalize_policy_entry(raw)
        if not policy:
            continue

        code = policy.get("code")
        if not code or code in seen:
            continue

        enabled = policy.get("enabled", policy.get("active", True))
        if enabled is False:
            continue

        seen.add(code)
        policies.append(policy)

    return policies


def _load_active_policies_from_manager() -> Dict[str, Any]:
    """
    Fonte única de verdade da V1.1:
    Executive Policy Manager.
    Não lemos mais executive_policy_state.json diretamente aqui.
    """
    if not EXECUTIVE_POLICY_MANAGER_LOADED or executive_policy_manager is None:
        return {
            "ok": False,
            "source": "executive_policy_manager",
            "manager_loaded": False,
            "manager_error": EXECUTIVE_POLICY_MANAGER_ERROR,
            "policies": [],
        }

    errors = []
    raw = None
    used_function = None

    for fn_name in [
        "get_active_policies",
        "list_active_policies",
        "load_active_policies",
    ]:
        fn = getattr(executive_policy_manager, fn_name, None)
        if not callable(fn):
            continue
        try:
            raw = fn()
            used_function = fn_name
            policies = _extract_active_policies_from_any(raw)
            return {
                "ok": True,
                "source": "executive_policy_manager",
                "manager_loaded": True,
                "manager_function": used_function,
                "raw_type": type(raw).__name__,
                "policies": policies,
            }
        except Exception as exc:
            errors.append(f"{fn_name}: {exc}")

    # Fallback controlado: se o manager tiver load_policy_state, usamos via API dele,
    # não por caminho próprio deste módulo.
    fn = getattr(executive_policy_manager, "load_policy_state", None)
    if callable(fn):
        try:
            raw = fn()
            used_function = "load_policy_state"
            policies = _extract_active_policies_from_any(raw)
            return {
                "ok": True,
                "source": "executive_policy_manager",
                "manager_loaded": True,
                "manager_function": used_function,
                "raw_type": type(raw).__name__,
                "policies": policies,
            }
        except Exception as exc:
            errors.append(f"load_policy_state: {exc}")

    return {
        "ok": False,
        "source": "executive_policy_manager",
        "manager_loaded": True,
        "manager_error": "; ".join(errors) or "Nenhuma função compatível encontrada no executive_policy_manager.",
        "policies": [],
    }


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
        try:
            return max(0, 100 - int(level[1:]) * 10)
        except Exception:
            pass

    code = _normalize_code(policy.get("code"))
    return max(0, 100 - PRIORITY_TABLE.get(code, DEFAULT_PRIORITY) * 10)


def _policy_targets_trade(policy: Dict[str, Any], trade_payload: Optional[Dict[str, Any]]) -> bool:
    if not trade_payload:
        return True

    trade_payload = trade_payload or {}
    bot = _normalize_code(trade_payload.get("bot"))
    setup = _normalize_code(trade_payload.get("setup") or trade_payload.get("strategy") or trade_payload.get("signal_type"))
    symbol = _normalize_symbol(trade_payload.get("symbol") or trade_payload.get("ativo") or trade_payload.get("pair"))
    side = _normalize_side(trade_payload.get("side") or trade_payload.get("direction"))
    category = _normalize_code(trade_payload.get("category") or trade_payload.get("bot_category"))

    code = _normalize_code(policy.get("code"))
    payload = policy.get("payload") if isinstance(policy.get("payload"), dict) else {}

    p_bot = _normalize_code(policy.get("bot") or policy.get("target_bot") or payload.get("bot") or payload.get("target_bot"))
    p_setup = _normalize_code(policy.get("setup") or policy.get("target_setup") or payload.get("setup") or payload.get("target_setup"))
    p_symbol = _normalize_symbol(policy.get("symbol") or policy.get("target_symbol") or payload.get("symbol") or payload.get("target_symbol"))
    p_side = _normalize_side(policy.get("side") or policy.get("target_side") or payload.get("side") or payload.get("target_side"))
    p_category = _normalize_code(policy.get("target_category") or payload.get("target_category"))

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
    payload = policy.get("payload") if isinstance(policy.get("payload"), dict) else {}

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
        effect.update({
            "decision": "DENY",
            "allowed": False,
            "action": "BLOCK",
            "reason": f"{code}: bloqueio executivo de prioridade máxima.",
        })

    elif code in {"WAIT_SAMPLE", "WAIT_MORE_SAMPLE", "LEARNING_LOCK", "INSUFFICIENT_SAMPLE"}:
        # Importante: WAIT_SAMPLE não deve bloquear tudo na V1.1.
        # Ele bloqueia expansão/agressividade, mas permite operação normal/observação.
        effect.update({
            "decision": "ALLOW_WITH_LIMITS",
            "allowed": True,
            "action": "NO_RISK_INCREASE",
            "size_multiplier": 1.0,
            "reason": f"{code}: não aumentar risco enquanto a amostra/learning é insuficiente.",
        })

    elif code in {"BLOCK_BOT", "BLOCK_SETUP", "BLOCK_SYMBOL", "ONLY_CORE_BOTS", "CAPITAL_PRESERVATION"}:
        effect.update({
            "decision": "DENY",
            "allowed": False,
            "action": "BLOCK",
            "reason": f"{code}: escopo bloqueado por política executiva.",
        })

    elif code == "NO_NEW_LONG" and (not trade_payload or side == "LONG"):
        effect.update({
            "decision": "DENY",
            "allowed": False,
            "action": "BLOCK",
            "reason": "NO_NEW_LONG: novas entradas LONG bloqueadas.",
        })

    elif code == "NO_NEW_SHORT" and (not trade_payload or side == "SHORT"):
        effect.update({
            "decision": "DENY",
            "allowed": False,
            "action": "BLOCK",
            "reason": "NO_NEW_SHORT: novas entradas SHORT bloqueadas.",
        })

    elif code == "ALLOW_ONLY_LONG" and side == "SHORT":
        effect.update({
            "decision": "DENY",
            "allowed": False,
            "action": "BLOCK",
            "reason": "ALLOW_ONLY_LONG: somente LONG permitido.",
        })

    elif code == "ALLOW_ONLY_SHORT" and side == "LONG":
        effect.update({
            "decision": "DENY",
            "allowed": False,
            "action": "BLOCK",
            "reason": "ALLOW_ONLY_SHORT: somente SHORT permitido.",
        })

    elif code in {"LIMIT_NEW_LONG", "LIMIT_NEW_SHORT", "REDUCE_SIZE", "FORCE_HALF_SIZE"}:
        raw_mult = (
            policy.get("size_multiplier")
            or policy.get("multiplier")
            or payload.get("size_multiplier")
            or payload.get("multiplier")
        )
        try:
            mult = float(raw_mult) if raw_mult is not None else 0.5
        except Exception:
            mult = 0.5
        mult = max(0.0, min(1.0, mult))

        # LIMIT_NEW_LONG/SHORT vindos do Executive Engine normalmente carregam
        # blocks_expansion=true. Isso deve limitar expansão, não zerar a operação.
        action = "LIMIT_EXPANSION" if payload.get("blocks_expansion") or policy.get("blocks_expansion") else "REDUCE_SIZE"
        effect.update({
            "decision": "ALLOW_WITH_LIMITS",
            "allowed": True,
            "action": action,
            "size_multiplier": mult,
            "reason": f"{code}: entrada permitida com limitação executiva.",
        })

    elif code in {"MAX_RISK", "CAP_RISK", "LIMIT_RISK"}:
        raw_cap = (
            policy.get("max_risk_pct")
            or policy.get("risk_cap_pct")
            or policy.get("risk_pct")
            or payload.get("max_risk_pct")
            or payload.get("risk_cap_pct")
            or payload.get("risk_pct")
        )
        try:
            cap = float(raw_cap) if raw_cap is not None else None
        except Exception:
            cap = None

        effect.update({
            "decision": "ALLOW_WITH_LIMITS",
            "allowed": True,
            "action": "CAP_RISK",
            "max_risk_pct": cap,
            "reason": f"{code}: risco limitado pela política executiva.",
        })

    elif code in {"NORMAL_WITH_MONITORING", "MONITOR_ONLY", "WATCH"}:
        effect.update({
            "decision": "ALLOW",
            "allowed": True,
            "action": "MONITOR",
            "reason": f"{code}: monitoramento ativo.",
        })

    else:
        effect.update({
            "decision": "ALLOW",
            "allowed": True,
            "action": "UNKNOWN_POLICY_MONITOR",
            "reason": f"{code}: policy desconhecida na Priority V1.1; monitorando.",
        })

    return effect


def _compact_policy(policy: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(policy, dict):
        return None
    effect = policy.get("effect") or {}
    payload = policy.get("payload") if isinstance(policy.get("payload"), dict) else {}
    return {
        "code": policy.get("code"),
        "priority": policy.get("priority"),
        "severity": policy.get("severity"),
        "level": policy.get("level"),
        "title": policy.get("title"),
        "category": policy.get("category"),
        "source": policy.get("source"),
        "target_bot": policy.get("target_bot") or policy.get("bot") or payload.get("target_bot") or payload.get("bot"),
        "target_symbol": policy.get("target_symbol") or policy.get("symbol") or payload.get("target_symbol") or payload.get("symbol"),
        "target_side": policy.get("target_side") or policy.get("side") or payload.get("target_side") or payload.get("side"),
        "targets_trade": policy.get("targets_trade", True),
        "effect": effect,
        "payload": payload,
        "release_condition": policy.get("release_condition"),
        "created_at": policy.get("created_at"),
        "updated_at": policy.get("updated_at"),
    }


def resolve_executive_policy_priority(
    trade_payload: Optional[Dict[str, Any]] = None,
    policies: Optional[List[Dict[str, Any]]] = None,
    commit: bool = True,
) -> Dict[str, Any]:
    manager_result = _load_active_policies_from_manager()

    if isinstance(policies, list):
        active_policies = _extract_active_policies_from_any(policies)
        policy_source = "provided_policies"
        manager_ok = manager_result.get("ok")
    else:
        active_policies = manager_result.get("policies") or []
        policy_source = "executive_policy_manager"
        manager_ok = manager_result.get("ok")

    ranked: List[Dict[str, Any]] = []

    for policy in active_policies:
        if not isinstance(policy, dict):
            continue
        item = dict(policy)
        item["code"] = _normalize_code(item.get("code"))
        item["priority"] = _policy_priority(item)
        item["severity"] = _policy_severity(item)
        item["targets_trade"] = _policy_targets_trade(item, trade_payload)
        item["effect"] = _policy_effect(item, trade_payload)
        ranked.append(item)

    applicable = [p for p in ranked if p.get("targets_trade", True)]
    ranked_sorted = sorted(
        ranked,
        key=lambda p: (p.get("priority", DEFAULT_PRIORITY), -p.get("severity", 0), str(p.get("code") or "")),
    )
    applicable_sorted = sorted(
        applicable,
        key=lambda p: (p.get("priority", DEFAULT_PRIORITY), -p.get("severity", 0), str(p.get("code") or "")),
    )

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

    # Consolida limites secundários.
    for item in applicable_sorted:
        effect = item.get("effect") or {}

        if item is not dominant and effect.get("reason"):
            if effect.get("decision") == "ALLOW_WITH_LIMITS":
                warnings.append(effect.get("reason"))

        if effect.get("size_multiplier") not in [None, 1, 1.0]:
            try:
                size_multiplier = min(size_multiplier, float(effect.get("size_multiplier")))
            except Exception:
                pass

        if effect.get("max_risk_pct") is not None and max_risk_pct is None:
            max_risk_pct = effect.get("max_risk_pct")

    if not manager_ok and not policies:
        warnings.append(manager_result.get("manager_error") or "Executive Policy Manager indisponível para Priority V1.1.")

    result = {
        "ok": bool(manager_ok) if not policies else True,
        "module": MODULE,
        "version": VERSION,
        "generated_at": _now_br(),
        "source": "executive_policy_priority",
        "policy_source": policy_source,
        "manager_loaded": EXECUTIVE_POLICY_MANAGER_LOADED,
        "manager_function": manager_result.get("manager_function"),
        "manager_error": manager_result.get("manager_error"),
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
            "Priority V1.1 usa o Executive Policy Manager como fonte única de verdade.",
            "Não cria, remove ou executa policies.",
            "Quanto menor o priority, maior a força da policy.",
            "A policy dominante é a primeira aplicável ao trade/contexto.",
        ],
    }

    if commit:
        _safe_write_json(PRIORITY_STATE_FILE, result)
        _append_jsonl(PRIORITY_LOG_FILE, result)

    return result


def get_executive_policy_priority_health() -> Dict[str, Any]:
    manager_result = _load_active_policies_from_manager()
    active = manager_result.get("policies") or []
    last = _safe_read_json(PRIORITY_STATE_FILE, default={}) or {}

    return {
        "ok": bool(manager_result.get("ok")),
        "loaded": True,
        "module": MODULE,
        "version": VERSION,
        "generated_at": _now_br(),
        "policy_source": "executive_policy_manager",
        "manager_loaded": EXECUTIVE_POLICY_MANAGER_LOADED,
        "manager_function": manager_result.get("manager_function"),
        "manager_error": manager_result.get("manager_error"),
        "priority_state_file": PRIORITY_STATE_FILE,
        "priority_log_file": PRIORITY_LOG_FILE,
        "active_policy_count": len(active),
        "active_codes": [_normalize_code(p.get("code")) for p in active],
        "last_run_at": last.get("generated_at"),
        "last_dominant_code": last.get("dominant_code"),
        "last_decision": last.get("decision"),
        "notes": [
            "Health apenas informa o estado do Priority V1.1.",
            "A contagem de policies vem do executive_policy_manager.",
        ],
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
        f"Fonte: {result.get('policy_source')}",
        f"Manager: {'✅' if result.get('manager_loaded') else '❌'} | função: {result.get('manager_function')}",
        f"Policies ativas: {result.get('active_policy_count', 0)}",
        f"Policies aplicáveis: {result.get('applicable_policy_count', 0)}",
        f"Decisão executiva: {result.get('decision')}",
        f"Permitido: {result.get('allowed')}",
        f"Size multiplier: {result.get('size_multiplier')}",
        f"Max risk pct: {result.get('max_risk_pct')}",
        "",
    ]

    if dominant:
        effect = dominant.get("effect") or {}
        lines += [
            "Policy dominante:",
            f"- Código: {dominant.get('code')}",
            f"- Prioridade: P{dominant.get('priority')}",
            f"- Título: {dominant.get('title') or 'N/A'}",
            f"- Efeito: {effect.get('action')}",
            f"- Motivo: {effect.get('reason')}",
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

    if result.get("manager_error"):
        warnings.append(f"Manager error: {result.get('manager_error')}")

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
        "- Priority V1.1 resolve conflito entre policies ativas.",
        "- Quanto menor P, maior a prioridade.",
        "- A fonte oficial é o Executive Policy Manager.",
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
