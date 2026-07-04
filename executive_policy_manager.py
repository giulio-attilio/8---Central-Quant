# ============================================================
# EXECUTIVE POLICY MANAGER V1 — CENTRAL QUANT
# Versao: 2026-07-04-EXECUTIVE-POLICY-MANAGER-V1
# Arquivo sugerido: executive_policy_manager.py
# ============================================================
# Objetivo:
# - Transformar diretivas executivas em politicas persistentes.
# - Centralizar regras globais como NO_NEW_LONG, NO_NEW_SHORT,
#   BLOCK_BOT, REDUCE_SIZE, CAPITAL_PRESERVATION etc.
# - Permitir que Risk Manager, Capital Allocator e Execution
#   Orchestrator consultem a mesma fonte de verdade.
#
# Modo atual:
# - OBSERVATION / VERIFY friendly.
# - Nao executa ordem.
# - Apenas salva, consulta e aplica decisoes em objetos.
# ============================================================

import os
import json
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


EXECUTIVE_POLICY_MANAGER_VERSION = "2026-07-04-EXECUTIVE-POLICY-MANAGER-V1"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
POLICY_FILE = os.path.join(DATA_DIR, "executive_policy.json")
POLICY_LOG_FILE = os.path.join(DATA_DIR, "executive_policy_log.jsonl")


def _now_str() -> str:
    return datetime.now().strftime("%d/%m/%Y %H:%M:%S")


def _now_epoch() -> float:
    return time.time()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "sim", "on", "enabled")
    if value is None:
        return default
    return bool(value)


def _ensure_data_dir() -> None:
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
    except Exception:
        pass


def _read_json(path: str, default: Any) -> Any:
    try:
        if not os.path.exists(path):
            return default
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _write_json(path: str, payload: Any) -> bool:
    try:
        _ensure_data_dir()
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
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


# ============================================================
# ESTADO PADRAO
# ============================================================

def _default_policy_state() -> Dict[str, Any]:
    return {
        "ok": True,
        "module": "executive_policy_manager",
        "version": EXECUTIVE_POLICY_MANAGER_VERSION,
        "generated_at": _now_str(),
        "updated_at": None,
        "policies": [],
        "notes": [
            "Executive Policy Manager centraliza politicas executivas persistentes.",
            "V1 nao executa ordens e nao altera corretora diretamente.",
            "Risk Manager, Capital Allocator e Execution Orchestrator podem consultar este arquivo.",
        ],
    }


def load_policy_state() -> Dict[str, Any]:
    state = _read_json(POLICY_FILE, None)
    if not isinstance(state, dict):
        state = _default_policy_state()
        save_policy_state(state, reason="bootstrap")
    state.setdefault("ok", True)
    state.setdefault("module", "executive_policy_manager")
    state.setdefault("version", EXECUTIVE_POLICY_MANAGER_VERSION)
    state.setdefault("generated_at", _now_str())
    state.setdefault("updated_at", None)
    state.setdefault("policies", [])
    return state


def save_policy_state(state: Dict[str, Any], reason: str = "save") -> bool:
    state["updated_at"] = _now_str()
    state["version"] = EXECUTIVE_POLICY_MANAGER_VERSION
    ok = _write_json(POLICY_FILE, state)
    _append_jsonl(POLICY_LOG_FILE, {
        "event": "POLICY_STATE_SAVED",
        "reason": reason,
        "ok": ok,
        "epoch": _now_epoch(),
        "generated_at": _now_str(),
        "active_codes": [p.get("code") for p in state.get("policies", []) if p.get("enabled")],
    })
    return ok


# ============================================================
# NORMALIZACAO DE POLITICAS
# ============================================================

def normalize_policy(policy: Dict[str, Any]) -> Dict[str, Any]:
    code = str(policy.get("code") or policy.get("policy_code") or "UNKNOWN").strip().upper()
    title = policy.get("title") or code
    level = str(policy.get("level") or "P2").strip().upper()
    category = str(policy.get("category") or "EXECUTIVE").strip().upper()

    normalized = {
        "code": code,
        "title": title,
        "enabled": _safe_bool(policy.get("enabled", True), True),
        "level": level,
        "category": category,
        "action": policy.get("action"),
        "reason": policy.get("reason") or policy.get("rationale"),
        "created_at": policy.get("created_at") or _now_str(),
        "updated_at": _now_str(),
        "expires_at": policy.get("expires_at"),
        "release_condition": policy.get("release_condition"),
        "source": policy.get("source") or "executive_decision_engine",
        "payload": policy.get("payload") or {},
    }

    raw_policy = policy.get("policy")
    if isinstance(raw_policy, dict):
        normalized["payload"].update(raw_policy)
        if raw_policy.get("release_condition") and not normalized.get("release_condition"):
            normalized["release_condition"] = raw_policy.get("release_condition")

    # Campos auxiliares muito usados
    for key in [
        "allow_new_long", "allow_new_short", "allow_expansion", "blocks_expansion",
        "dominant_side", "dominant_pct", "max_risk_pct", "size_multiplier",
        "blocked_bot", "blocked_setup", "blocked_symbol", "only_core_bots",
    ]:
        if key in policy:
            normalized["payload"][key] = policy.get(key)
        if isinstance(raw_policy, dict) and key in raw_policy:
            normalized["payload"][key] = raw_policy.get(key)

    return normalized


def _policy_is_expired(policy: Dict[str, Any]) -> bool:
    # V1: mantem simples. Se expires_at existir como epoch numerico e passou, expira.
    expires_at = policy.get("expires_at")
    if expires_at is None:
        return False
    try:
        return float(expires_at) <= _now_epoch()
    except Exception:
        return False


def get_all_policies(include_disabled: bool = True) -> List[Dict[str, Any]]:
    state = load_policy_state()
    policies = state.get("policies", [])
    if not isinstance(policies, list):
        policies = []
    if include_disabled:
        return policies
    return [p for p in policies if p.get("enabled") and not _policy_is_expired(p)]


def get_active_policies() -> List[Dict[str, Any]]:
    return get_all_policies(include_disabled=False)


def get_policy(code: str) -> Optional[Dict[str, Any]]:
    code = str(code or "").strip().upper()
    for p in get_all_policies(include_disabled=True):
        if str(p.get("code", "")).upper() == code:
            return p
    return None


def is_policy_active(code: str) -> bool:
    p = get_policy(code)
    if not p:
        return False
    return bool(p.get("enabled")) and not _policy_is_expired(p)


# ============================================================
# MUTACOES
# ============================================================

def upsert_policy(policy: Dict[str, Any], reason: str = "upsert") -> Dict[str, Any]:
    state = load_policy_state()
    policies = state.get("policies", [])
    if not isinstance(policies, list):
        policies = []

    normalized = normalize_policy(policy)
    code = normalized["code"]

    replaced = False
    new_policies = []
    for existing in policies:
        if str(existing.get("code", "")).upper() == code:
            merged = dict(existing)
            merged.update(normalized)
            # preserva created_at original quando existir
            if existing.get("created_at"):
                merged["created_at"] = existing.get("created_at")
            new_policies.append(merged)
            replaced = True
        else:
            new_policies.append(existing)

    if not replaced:
        new_policies.append(normalized)

    state["policies"] = new_policies
    saved = save_policy_state(state, reason=reason)

    _append_jsonl(POLICY_LOG_FILE, {
        "event": "POLICY_UPSERTED",
        "code": code,
        "reason": reason,
        "saved": saved,
        "policy": normalized,
        "epoch": _now_epoch(),
        "generated_at": _now_str(),
    })

    return {"ok": saved, "policy": normalized, "replaced": replaced, "version": EXECUTIVE_POLICY_MANAGER_VERSION}


def disable_policy(code: str, reason: str = "manual_disable") -> Dict[str, Any]:
    state = load_policy_state()
    policies = state.get("policies", [])
    code = str(code or "").strip().upper()
    found = False

    for p in policies:
        if str(p.get("code", "")).upper() == code:
            p["enabled"] = False
            p["disabled_at"] = _now_str()
            p["disabled_reason"] = reason
            p["updated_at"] = _now_str()
            found = True

    state["policies"] = policies
    saved = save_policy_state(state, reason=f"disable:{code}")

    _append_jsonl(POLICY_LOG_FILE, {
        "event": "POLICY_DISABLED",
        "code": code,
        "reason": reason,
        "found": found,
        "saved": saved,
        "epoch": _now_epoch(),
        "generated_at": _now_str(),
    })

    return {"ok": saved and found, "found": found, "code": code}


def enable_policy(code: str, reason: str = "manual_enable") -> Dict[str, Any]:
    state = load_policy_state()
    policies = state.get("policies", [])
    code = str(code or "").strip().upper()
    found = False

    for p in policies:
        if str(p.get("code", "")).upper() == code:
            p["enabled"] = True
            p["enabled_at"] = _now_str()
            p["enabled_reason"] = reason
            p["updated_at"] = _now_str()
            found = True

    state["policies"] = policies
    saved = save_policy_state(state, reason=f"enable:{code}")

    _append_jsonl(POLICY_LOG_FILE, {
        "event": "POLICY_ENABLED",
        "code": code,
        "reason": reason,
        "found": found,
        "saved": saved,
        "epoch": _now_epoch(),
        "generated_at": _now_str(),
    })

    return {"ok": saved and found, "found": found, "code": code}


def clear_policies(reason: str = "manual_clear") -> Dict[str, Any]:
    state = load_policy_state()
    previous = state.get("policies", [])
    state["policies"] = []
    saved = save_policy_state(state, reason=reason)

    _append_jsonl(POLICY_LOG_FILE, {
        "event": "POLICIES_CLEARED",
        "reason": reason,
        "previous_count": len(previous) if isinstance(previous, list) else 0,
        "saved": saved,
        "epoch": _now_epoch(),
        "generated_at": _now_str(),
    })

    return {"ok": saved, "cleared": True}


# ============================================================
# INGESTAO DE DIRETIVAS EXECUTIVAS
# ============================================================

def ingest_executive_directives(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Aceita payload vindo do Executive Decision Engine / Executive Intelligence.

    Formatos aceitos:
    - {"directives": [{...}, {...}]}
    - {"payload": {"directives": [...]}}
    - {"policies": [{...}]}
    """
    if not isinstance(payload, dict):
        return {"ok": False, "error": "payload_not_dict", "version": EXECUTIVE_POLICY_MANAGER_VERSION}

    source_payload = payload.get("payload") if isinstance(payload.get("payload"), dict) else payload

    directives = []
    if isinstance(source_payload.get("directives"), list):
        directives = source_payload.get("directives")
    elif isinstance(source_payload.get("policies"), list):
        directives = source_payload.get("policies")

    results = []
    for d in directives:
        if not isinstance(d, dict):
            continue
        code = str(d.get("code") or d.get("policy_code") or "").strip().upper()
        if not code:
            continue
        normalized_input = dict(d)
        normalized_input["source"] = normalized_input.get("source") or "executive_directives"
        result = upsert_policy(normalized_input, reason="ingest_executive_directives")
        results.append(result)

    return {
        "ok": True,
        "ingested": len(results),
        "results": results,
        "active_policies": get_active_policies(),
        "version": EXECUTIVE_POLICY_MANAGER_VERSION,
        "generated_at": _now_str(),
    }


# ============================================================
# APLICACAO EM TRADES / DECISOES
# ============================================================

def _infer_side(trade: Dict[str, Any]) -> str:
    side = trade.get("side") or trade.get("direction") or trade.get("signal_side")
    return str(side or "").strip().upper()


def _infer_bot(trade: Dict[str, Any]) -> str:
    return str(trade.get("bot") or trade.get("robot") or trade.get("strategy") or "").strip().upper()


def _infer_setup(trade: Dict[str, Any]) -> str:
    return str(trade.get("setup") or trade.get("signal_setup") or "").strip().upper()


def _infer_symbol(trade: Dict[str, Any]) -> str:
    return str(trade.get("symbol") or trade.get("ticker") or "").strip().upper()


def evaluate_trade_against_policies(trade: Dict[str, Any]) -> Dict[str, Any]:
    """
    Retorna decisao executiva para um trade hipotetico/real.
    Nao executa nada. Apenas avalia.
    """
    if not isinstance(trade, dict):
        trade = {}

    side = _infer_side(trade)
    bot = _infer_bot(trade)
    setup = _infer_setup(trade)
    symbol = _infer_symbol(trade)

    decision = "ALLOW"
    reasons: List[str] = []
    warnings: List[str] = []
    applied: List[Dict[str, Any]] = []
    size_multiplier = 1.0
    max_risk_pct: Optional[float] = None

    for p in get_active_policies():
        code = str(p.get("code") or "").upper()
        payload = p.get("payload") if isinstance(p.get("payload"), dict) else {}
        applied_policy = {"code": code, "title": p.get("title"), "level": p.get("level")}

        if code == "NO_NEW_LONG" and side == "LONG":
            decision = "DENY"
            reasons.append("Política executiva ativa: NO_NEW_LONG.")
            applied.append(applied_policy)

        elif code == "NO_NEW_SHORT" and side == "SHORT":
            decision = "DENY"
            reasons.append("Política executiva ativa: NO_NEW_SHORT.")
            applied.append(applied_policy)

        elif code == "ALLOW_ONLY_LONG" and side == "SHORT":
            decision = "DENY"
            reasons.append("Política executiva ativa: somente LONG permitido.")
            applied.append(applied_policy)

        elif code == "ALLOW_ONLY_SHORT" and side == "LONG":
            decision = "DENY"
            reasons.append("Política executiva ativa: somente SHORT permitido.")
            applied.append(applied_policy)

        elif code == "BLOCK_BOT":
            blocked_bot = str(payload.get("blocked_bot") or "").upper()
            if blocked_bot and bot == blocked_bot:
                decision = "DENY"
                reasons.append(f"Política executiva ativa: bot bloqueado ({blocked_bot}).")
                applied.append(applied_policy)

        elif code == "BLOCK_SETUP":
            blocked_setup = str(payload.get("blocked_setup") or "").upper()
            if blocked_setup and setup == blocked_setup:
                decision = "DENY"
                reasons.append(f"Política executiva ativa: setup bloqueado ({blocked_setup}).")
                applied.append(applied_policy)

        elif code == "BLOCK_SYMBOL":
            blocked_symbol = str(payload.get("blocked_symbol") or "").upper()
            if blocked_symbol and symbol == blocked_symbol:
                decision = "DENY"
                reasons.append(f"Política executiva ativa: ativo bloqueado ({blocked_symbol}).")
                applied.append(applied_policy)

        elif code == "ONLY_CORE_BOTS":
            # Espera trade["category"] = CORE/DEVELOPING/EXPERIMENTAL quando existir.
            category = str(trade.get("category") or trade.get("bot_category") or "").upper()
            if category and category != "CORE":
                decision = "DENY"
                reasons.append("Política executiva ativa: somente robôs CORE permitidos.")
                applied.append(applied_policy)
            elif not category:
                warnings.append("ONLY_CORE_BOTS ativo, mas trade não informou categoria do robô.")
                applied.append(applied_policy)

        elif code in ("FORCE_HALF_SIZE", "REDUCE_SIZE"):
            multiplier = _safe_float(payload.get("size_multiplier"), 0.5)
            if multiplier <= 0 or multiplier > 1:
                multiplier = 0.5
            size_multiplier = min(size_multiplier, multiplier)
            warnings.append(f"Política executiva reduz tamanho: multiplicador {multiplier}.")
            applied.append(applied_policy)

        elif code in ("MAX_RISK", "MAX_RISK_PCT", "CAP_RISK"):
            cap = _safe_float(payload.get("max_risk_pct"), 0.0)
            if cap > 0:
                max_risk_pct = cap if max_risk_pct is None else min(max_risk_pct, cap)
                warnings.append(f"Política executiva limita risco máximo a {cap}%.")
                applied.append(applied_policy)

        elif code == "CAPITAL_PRESERVATION":
            size_multiplier = min(size_multiplier, _safe_float(payload.get("size_multiplier"), 0.5) or 0.5)
            warnings.append("Modo preservação de capital ativo.")
            applied.append(applied_policy)

    return {
        "ok": True,
        "decision": decision,
        "allowed": decision == "ALLOW",
        "reasons": reasons,
        "warnings": warnings,
        "applied_policies": applied,
        "size_multiplier": size_multiplier,
        "max_risk_pct": max_risk_pct,
        "trade": {
            "symbol": symbol,
            "side": side,
            "bot": bot,
            "setup": setup,
        },
        "active_policy_count": len(get_active_policies()),
        "version": EXECUTIVE_POLICY_MANAGER_VERSION,
        "generated_at": _now_str(),
    }


def policy_allows_trade(trade: Dict[str, Any]) -> bool:
    return bool(evaluate_trade_against_policies(trade).get("allowed"))


def apply_policy_to_decision(decision_payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Envolve uma decisao existente do Risk/Allocator/Orchestrator.
    Se politica negar, sobrescreve para DENY.
    Se politica reduzir tamanho, anexa sugestao.
    """
    if not isinstance(decision_payload, dict):
        decision_payload = {}

    trade = dict(decision_payload)
    if isinstance(decision_payload.get("trade"), dict):
        trade.update(decision_payload.get("trade"))

    evaluation = evaluate_trade_against_policies(trade)

    output = dict(decision_payload)
    output["executive_policy"] = evaluation

    if not evaluation.get("allowed"):
        output["decision"] = "DENY"
        output["blocked_by_executive_policy"] = True
        output.setdefault("reasons", [])
        if isinstance(output["reasons"], list):
            output["reasons"].extend(evaluation.get("reasons", []))
    else:
        output.setdefault("warnings", [])
        if isinstance(output["warnings"], list):
            output["warnings"].extend(evaluation.get("warnings", []))
        if evaluation.get("size_multiplier", 1.0) < 1.0:
            output["size_multiplier"] = evaluation.get("size_multiplier")
        if evaluation.get("max_risk_pct") is not None:
            output["max_risk_pct"] = evaluation.get("max_risk_pct")

    output["executive_policy_checked"] = True
    output["executive_policy_version"] = EXECUTIVE_POLICY_MANAGER_VERSION
    return output


# ============================================================
# HEALTH / RELATORIOS / TELEGRAM
# ============================================================

def build_policy_health() -> Dict[str, Any]:
    state = load_policy_state()
    active = get_active_policies()
    all_policies = get_all_policies(include_disabled=True)

    return {
        "ok": True,
        "module": "executive_policy_manager",
        "loaded": True,
        "version": EXECUTIVE_POLICY_MANAGER_VERSION,
        "file": POLICY_FILE,
        "log_file": POLICY_LOG_FILE,
        "policy_count": len(all_policies),
        "active_policy_count": len(active),
        "active_codes": [p.get("code") for p in active],
        "updated_at": state.get("updated_at"),
        "generated_at": _now_str(),
        "notes": state.get("notes", []),
    }


def build_policy_report() -> Dict[str, Any]:
    active = get_active_policies()
    all_policies = get_all_policies(include_disabled=True)
    return {
        "ok": True,
        "version": EXECUTIVE_POLICY_MANAGER_VERSION,
        "generated_at": _now_str(),
        "active_policy_count": len(active),
        "policy_count": len(all_policies),
        "active_policies": active,
        "policies": all_policies,
    }


def format_policy_health_text() -> str:
    h = build_policy_health()
    lines = []
    lines.append("🧭 EXECUTIVE POLICY MANAGER — CENTRAL QUANT")
    lines.append(f"Data/hora: {h.get('generated_at')}")
    lines.append(f"Status: {'OK ✅' if h.get('ok') else 'ERRO ❌'}")
    lines.append(f"Versão: {h.get('version')}")
    lines.append("")
    lines.append(f"Políticas totais: {h.get('policy_count')}")
    lines.append(f"Políticas ativas: {h.get('active_policy_count')}")
    lines.append(f"Atualizado em: {h.get('updated_at')}")
    lines.append("")
    active_codes = h.get("active_codes") or []
    if active_codes:
        lines.append("Ativas:")
        for code in active_codes:
            lines.append(f"- {code}")
    else:
        lines.append("Nenhuma política executiva ativa.")
    return "\n".join(lines)


def format_policies_text(include_disabled: bool = False) -> str:
    policies = get_all_policies(include_disabled=include_disabled)
    if not include_disabled:
        policies = get_active_policies()

    lines = []
    lines.append("📜 EXECUTIVE POLICIES — CENTRAL QUANT")
    lines.append(f"Data/hora: {_now_str()}")
    lines.append(f"Exibindo: {'todas' if include_disabled else 'ativas'}")
    lines.append("")

    if not policies:
        lines.append("Nenhuma política encontrada.")
        return "\n".join(lines)

    for idx, p in enumerate(policies, 1):
        enabled = "ATIVA ✅" if p.get("enabled") and not _policy_is_expired(p) else "INATIVA ⚪"
        lines.append(f"{idx}. {p.get('code')} — {enabled}")
        lines.append(f"Título: {p.get('title')}")
        lines.append(f"Nível: {p.get('level')} | Categoria: {p.get('category')}")
        if p.get("reason"):
            lines.append(f"Motivo: {p.get('reason')}")
        if p.get("release_condition"):
            lines.append(f"Liberação: {p.get('release_condition')}")
        payload = p.get("payload") if isinstance(p.get("payload"), dict) else {}
        if payload:
            simple_payload = {k: v for k, v in payload.items() if k not in ("raw", "debug")}
            lines.append(f"Payload: {json.dumps(simple_payload, ensure_ascii=False)}")
        lines.append("")

    return "\n".join(lines).strip()


def format_single_policy_text(code: str) -> str:
    p = get_policy(code)
    if not p:
        return f"📜 EXECUTIVE POLICY\n\nPolítica não encontrada: {str(code).upper()}"

    active = bool(p.get("enabled")) and not _policy_is_expired(p)
    lines = []
    lines.append("📜 EXECUTIVE POLICY — CENTRAL QUANT")
    lines.append(f"Data/hora: {_now_str()}")
    lines.append("")
    lines.append(f"Código: {p.get('code')}")
    lines.append(f"Status: {'ATIVA ✅' if active else 'INATIVA ⚪'}")
    lines.append(f"Título: {p.get('title')}")
    lines.append(f"Nível: {p.get('level')}")
    lines.append(f"Categoria: {p.get('category')}")
    if p.get("reason"):
        lines.append(f"Motivo: {p.get('reason')}")
    if p.get("release_condition"):
        lines.append(f"Liberação: {p.get('release_condition')}")
    lines.append(f"Criada em: {p.get('created_at')}")
    lines.append(f"Atualizada em: {p.get('updated_at')}")
    payload = p.get("payload") if isinstance(p.get("payload"), dict) else {}
    if payload:
        lines.append("")
        lines.append("Payload:")
        lines.append(json.dumps(payload, ensure_ascii=False, indent=2))
    return "\n".join(lines)


# ============================================================
# BOOTSTRAP OPCIONAL PARA TESTE MANUAL
# ============================================================

def bootstrap_no_new_long(dominant_pct: float = 86.49) -> Dict[str, Any]:
    return upsert_policy({
        "code": "NO_NEW_LONG",
        "title": "Bloquear novas entradas LONG",
        "enabled": True,
        "level": "P1",
        "category": "RISK",
        "action": "Não aceitar novas entradas LONG até concentração cair abaixo de 75%.",
        "reason": f"Concentração direcional crítica: LONG {dominant_pct}%.",
        "release_condition": "LONG abaixo de 75%",
        "payload": {
            "allow_new_long": False,
            "allow_new_short": True,
            "allow_expansion": False,
            "dominant_side": "LONG",
            "dominant_pct": dominant_pct,
        },
    }, reason="bootstrap_no_new_long")


if __name__ == "__main__":
    # Teste local opcional:
    # python executive_policy_manager.py
    load_policy_state()
    print(format_policy_health_text())
