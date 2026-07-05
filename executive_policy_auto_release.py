# ============================================================
# CENTRAL QUANT PRO
# EXECUTIVE POLICY AUTO RELEASE V1
# Versão: 2026-07-04-EXECUTIVE-POLICY-AUTO-RELEASE-V1
#
# Objetivo:
# - Remover automaticamente políticas executivas quando a condição
#   que justificou a política deixar de existir.
# - Não executa trades.
# - Não altera lote.
# - Não altera risco real.
# - Apenas governa o ciclo de vida das executive policies.
#
# Uso sugerido no main.py:
#
# from executive_policy_auto_release import (
#     run_executive_policy_auto_release,
#     build_executive_policy_auto_release_report,
# )
#
# Dentro do dashboard/loop executivo, após atualizar exposição/riskstats:
# auto_release_result = run_executive_policy_auto_release(context={
#     "exposure": exposure_payload,
#     "riskstats": riskstats_payload,
#     "learning": learning_payload,
#     "health": health_payload,
# })
#
# Para endpoint Telegram/HTTP:
# @app.route('/policyautorelease')
# def policy_auto_release_route():
#     result = run_executive_policy_auto_release(context={})
#     return build_executive_policy_auto_release_report(result)
# ============================================================

from __future__ import annotations

import json
import os
import time
import traceback
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


VERSION = "2026-07-04-EXECUTIVE-POLICY-AUTO-RELEASE-V1"
MODULE = "executive_policy_auto_release"

DATA_DIR = os.getenv("CENTRAL_DATA_DIR", "/opt/render/project/src/data")
POLICY_STATE_FILE = os.path.join(DATA_DIR, "executive_policy_state.json")
POLICY_LOG_FILE = os.path.join(DATA_DIR, "executive_policy_log.jsonl")
AUTO_RELEASE_LOG_FILE = os.path.join(DATA_DIR, "executive_policy_auto_release_log.jsonl")
AUTO_RELEASE_STATE_FILE = os.path.join(DATA_DIR, "executive_policy_auto_release_state.json")

# Compatibilidade com nomes alternativos, caso sua Central esteja usando
# outro arquivo para persistência de policies.
POLICY_STATE_CANDIDATES = [
    POLICY_STATE_FILE,
    os.path.join(DATA_DIR, "executive_policies.json"),
    os.path.join(DATA_DIR, "executive_policy_manager_state.json"),
    os.path.join(DATA_DIR, "executive_policy_active.json"),
]

DEFAULT_RELEASE_RULES = {
    # Concentração direcional
    "NO_NEW_LONG": {
        "type": "directional_concentration_below",
        "side": "LONG",
        "threshold_pct": 75.0,
        "reason": "Concentração LONG normalizada abaixo de 75%.",
    },
    "LIMIT_NEW_LONG": {
        "type": "directional_concentration_below",
        "side": "LONG",
        "threshold_pct": 75.0,
        "reason": "Concentração LONG voltou para zona aceitável.",
    },
    "NO_NEW_SHORT": {
        "type": "directional_concentration_below",
        "side": "SHORT",
        "threshold_pct": 75.0,
        "reason": "Concentração SHORT normalizada abaixo de 75%.",
    },
    "LIMIT_NEW_SHORT": {
        "type": "directional_concentration_below",
        "side": "SHORT",
        "threshold_pct": 75.0,
        "reason": "Concentração SHORT voltou para zona aceitável.",
    },

    # Amostra/learning
    "WAIT_SAMPLE": {
        "type": "sample_at_least",
        "min_trades": 30,
        "reason": "Amostra mínima alcançada para avaliação estatística.",
    },

    # Fallbacks operacionais comuns
    "NORMAL_WITH_MONITORING": {
        "type": "never_auto_release",
        "reason": "Política estrutural de monitoramento; não removida automaticamente na V1.",
    },
    "BLOCK_REAL_EXECUTION": {
        "type": "manual_only",
        "reason": "Bloqueio de execução real exige liberação manual na V1.",
    },
    "EXECUTION_BLOCKED": {
        "type": "manual_only",
        "reason": "Bloqueio de execução exige liberação manual na V1.",
    },
}


@dataclass
class PolicyReleaseDecision:
    code: str
    release: bool
    reason: str
    rule_type: str
    evidence: Dict[str, Any]
    policy: Dict[str, Any]


def _now_br() -> str:
    # Render normalmente usa UTC. A Central já costuma formatar string simples.
    # Mantemos formato brasileiro operacional sem depender de timezone externo.
    return datetime.now().strftime("%d/%m/%Y %H:%M:%S")


def _ensure_data_dir() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)


def _safe_read_json(path: str, default: Any) -> Any:
    try:
        if not path or not os.path.exists(path):
            return default
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read().strip()
        if not raw:
            return default
        return json.loads(raw)
    except Exception:
        return default


def _safe_write_json(path: str, payload: Any) -> None:
    _ensure_data_dir()
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)
    os.replace(tmp, path)


def _append_jsonl(path: str, payload: Dict[str, Any]) -> None:
    _ensure_data_dir()
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def _find_policy_state_file() -> str:
    for path in POLICY_STATE_CANDIDATES:
        if os.path.exists(path):
            return path
    return POLICY_STATE_FILE


def _normalize_policy_entry(item: Any) -> Optional[Dict[str, Any]]:
    if not item:
        return None
    if isinstance(item, str):
        return {
            "code": item,
            "active": True,
            "source": "string_policy_code",
        }
    if isinstance(item, dict):
        code = item.get("code") or item.get("policy_code") or item.get("name") or item.get("id")
        if not code:
            return None
        normalized = dict(item)
        normalized["code"] = str(code)
        normalized["active"] = bool(item.get("active", True))
        return normalized
    return None


def _extract_active_policies(state: Any) -> List[Dict[str, Any]]:
    """
    Aceita múltiplos formatos de persistência:
    1) {"active_policies": [{...}]}
    2) {"policies": [{...}]}
    3) {"active_codes": ["NO_NEW_LONG"]}
    4) [{"code":"NO_NEW_LONG"}]
    5) {"NO_NEW_LONG": {"active": true}}
    """
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
            # Formato dict por código.
            for key, value in state.items():
                if isinstance(value, dict):
                    item = dict(value)
                    item.setdefault("code", key)
                    raw_items.append(item)

    policies: List[Dict[str, Any]] = []
    seen = set()
    for item in raw_items:
        normalized = _normalize_policy_entry(item)
        if not normalized:
            continue
        code = normalized.get("code")
        if not code or code in seen:
            continue
        if normalized.get("active", True) is False:
            continue
        seen.add(code)
        policies.append(normalized)
    return policies


def _save_policy_state_without_released(
    original_state: Any,
    released_codes: List[str],
    state_file: str,
) -> Any:
    released_set = set(released_codes or [])
    if not released_set:
        return original_state

    updated = original_state

    if isinstance(original_state, list):
        updated = []
        for item in original_state:
            p = _normalize_policy_entry(item)
            code = p.get("code") if p else None
            if code in released_set:
                continue
            updated.append(item)

    elif isinstance(original_state, dict):
        updated = dict(original_state)

        for key in ["active_policies", "policies", "items", "data"]:
            if isinstance(updated.get(key), list):
                filtered = []
                for item in updated.get(key, []):
                    p = _normalize_policy_entry(item)
                    code = p.get("code") if p else None
                    if code in released_set:
                        continue
                    filtered.append(item)
                updated[key] = filtered

        if isinstance(updated.get("active_codes"), list):
            updated["active_codes"] = [c for c in updated["active_codes"] if c not in released_set]

        # Formato dict por código.
        for code in list(released_set):
            if code in updated and isinstance(updated[code], dict):
                # Preferimos manter histórico marcando inactive, em vez de apagar.
                updated[code] = dict(updated[code])
                updated[code]["active"] = False
                updated[code]["released_at"] = _now_br()
                updated[code]["released_by"] = MODULE

        updated["last_auto_release_at"] = _now_br()
        updated["last_auto_release_codes"] = list(released_set)
        updated["version_auto_release"] = VERSION

    _safe_write_json(state_file, updated)
    return updated


def _get_nested_number(payload: Any, keys: List[str], default: Optional[float] = None) -> Optional[float]:
    if not isinstance(payload, dict):
        return default

    # Busca direta por nomes comuns.
    for key in keys:
        if key in payload:
            try:
                return float(payload[key])
            except Exception:
                pass

    # Busca rasa em subdicts comuns.
    for parent_key in ["payload", "exposure", "risk", "riskstats", "summary", "portfolio", "data"]:
        child = payload.get(parent_key)
        if isinstance(child, dict):
            value = _get_nested_number(child, keys, None)
            if value is not None:
                return value

    return default


def _extract_direction_pct(context: Dict[str, Any], side: str) -> Optional[float]:
    side = (side or "").upper()
    if side == "LONG":
        keys = [
            "long_pct", "long_percentage", "long_concentration_pct", "long_dominance_pct",
            "pct_long", "LONG_pct", "long_percent", "dominant_pct",
        ]
    elif side == "SHORT":
        keys = [
            "short_pct", "short_percentage", "short_concentration_pct", "short_dominance_pct",
            "pct_short", "SHORT_pct", "short_percent", "dominant_pct",
        ]
    else:
        keys = ["dominant_pct", "concentration_pct"]

    # Se dominant_side existir e não for o lado analisado, dominant_pct não serve.
    dominant_side = None
    for root in [context, context.get("payload", {}), context.get("exposure", {}), context.get("riskstats", {})]:
        if isinstance(root, dict) and root.get("dominant_side"):
            dominant_side = str(root.get("dominant_side")).upper()
            break

    for root_key in [None, "exposure", "riskstats", "portfolio", "executive", "payload"]:
        root = context if root_key is None else context.get(root_key, {})
        value = _get_nested_number(root, keys, None)
        if value is None:
            continue
        if "dominant_pct" in keys and dominant_side and dominant_side != side:
            # Caso só haja dominant_pct mas o lado dominante seja outro,
            # não podemos assumir que esse é o percentual do lado analisado.
            # Porém se a chave específica foi encontrada, _get_nested_number não informa qual foi.
            # Para segurança, só bloqueamos quando o payload não tem chave específica.
            specific_keys = [k for k in keys if "dominant" not in k]
            specific_value = _get_nested_number(root, specific_keys, None)
            if specific_value is not None:
                return specific_value
            return None
        return value

    # Fallback por contagem: long_count/short_count/total_positions.
    long_count = _get_nested_number(context, ["long_count", "long", "LONG", "positions_long"], None)
    short_count = _get_nested_number(context, ["short_count", "short", "SHORT", "positions_short"], None)
    total = _get_nested_number(context, ["total_positions", "positions", "total", "open_positions"], None)
    if total and total > 0:
        if side == "LONG" and long_count is not None:
            return round((long_count / total) * 100.0, 2)
        if side == "SHORT" and short_count is not None:
            return round((short_count / total) * 100.0, 2)

    return None


def _extract_sample_size(context: Dict[str, Any], policy: Dict[str, Any]) -> Optional[int]:
    # Pode ser global, por bot ou por setup.
    bot = policy.get("bot") or policy.get("policy", {}).get("bot")
    setup = policy.get("setup") or policy.get("policy", {}).get("setup")

    candidates = [
        "trades", "closed_count", "sample", "sample_size", "total_trades",
        "decisions", "evaluated_trades",
    ]

    roots = [context, context.get("learning", {}), context.get("analytics", {}), context.get("riskstats", {})]

    # Busca segmentada por bot/setup.
    for root in roots:
        if not isinstance(root, dict):
            continue
        for group_key in ["by_bot", "bots", "bot_stats"]:
            group = root.get(group_key)
            if bot and isinstance(group, dict) and isinstance(group.get(bot), dict):
                value = _get_nested_number(group.get(bot), candidates, None)
                if value is not None:
                    return int(value)
        for group_key in ["by_setup", "setups", "setup_stats"]:
            group = root.get(group_key)
            if setup and isinstance(group, dict) and isinstance(group.get(setup), dict):
                value = _get_nested_number(group.get(setup), candidates, None)
                if value is not None:
                    return int(value)

    # Busca global.
    for root in roots:
        value = _get_nested_number(root, candidates, None)
        if value is not None:
            return int(value)

    return None


def _resolve_rule(policy: Dict[str, Any]) -> Dict[str, Any]:
    code = str(policy.get("code", "")).upper()

    # A própria policy pode trazer release_condition/release_when.
    embedded = policy.get("release_when") or policy.get("release_condition") or policy.get("policy", {}).get("release_condition")
    if isinstance(embedded, dict):
        rule = dict(embedded)
        rule.setdefault("reason", f"Condição de liberação da policy {code} atendida.")
        return rule

    # Se vier como string, tratamos algumas formas comuns.
    if isinstance(embedded, str):
        text = embedded.upper().strip()
        if "LONG" in text and ("75" in text or "75%" in text):
            return dict(DEFAULT_RELEASE_RULES["NO_NEW_LONG"])
        if "SHORT" in text and ("75" in text or "75%" in text):
            return dict(DEFAULT_RELEASE_RULES["NO_NEW_SHORT"])
        if "SAMPLE" in text or "AMOSTRA" in text:
            return dict(DEFAULT_RELEASE_RULES["WAIT_SAMPLE"])

    if code in DEFAULT_RELEASE_RULES:
        return dict(DEFAULT_RELEASE_RULES[code])

    return {
        "type": "unknown",
        "reason": "Policy sem regra de auto release conhecida na V1.",
    }


def _evaluate_policy(policy: Dict[str, Any], context: Dict[str, Any]) -> PolicyReleaseDecision:
    code = str(policy.get("code", "UNKNOWN")).upper()
    rule = _resolve_rule(policy)
    rule_type = str(rule.get("type", "unknown"))

    if rule_type == "directional_concentration_below":
        side = str(rule.get("side", "")).upper()
        threshold = float(rule.get("threshold_pct", 75.0))
        current_pct = _extract_direction_pct(context, side)
        evidence = {
            "side": side,
            "threshold_pct": threshold,
            "current_pct": current_pct,
        }
        if current_pct is None:
            return PolicyReleaseDecision(
                code=code,
                release=False,
                reason=f"Sem dado confiável de concentração {side}; manter policy por segurança.",
                rule_type=rule_type,
                evidence=evidence,
                policy=policy,
            )
        if current_pct < threshold:
            return PolicyReleaseDecision(
                code=code,
                release=True,
                reason=rule.get("reason") or f"Concentração {side} abaixo de {threshold}%.",
                rule_type=rule_type,
                evidence=evidence,
                policy=policy,
            )
        return PolicyReleaseDecision(
            code=code,
            release=False,
            reason=f"Concentração {side} ainda em {current_pct}%, acima/igual ao limite de release {threshold}%.",
            rule_type=rule_type,
            evidence=evidence,
            policy=policy,
        )

    if rule_type == "sample_at_least":
        min_trades = int(rule.get("min_trades", 30))
        sample = _extract_sample_size(context, policy)
        evidence = {
            "min_trades": min_trades,
            "sample": sample,
            "bot": policy.get("bot"),
            "setup": policy.get("setup"),
        }
        if sample is None:
            return PolicyReleaseDecision(
                code=code,
                release=False,
                reason="Sem dado confiável de amostra; manter WAIT_SAMPLE por segurança.",
                rule_type=rule_type,
                evidence=evidence,
                policy=policy,
            )
        if sample >= min_trades:
            return PolicyReleaseDecision(
                code=code,
                release=True,
                reason=rule.get("reason") or f"Amostra alcançada: {sample}/{min_trades}.",
                rule_type=rule_type,
                evidence=evidence,
                policy=policy,
            )
        return PolicyReleaseDecision(
            code=code,
            release=False,
            reason=f"Amostra ainda insuficiente: {sample}/{min_trades}.",
            rule_type=rule_type,
            evidence=evidence,
            policy=policy,
        )

    if rule_type in ["manual_only", "never_auto_release"]:
        return PolicyReleaseDecision(
            code=code,
            release=False,
            reason=rule.get("reason") or "Policy não deve ser removida automaticamente na V1.",
            rule_type=rule_type,
            evidence={},
            policy=policy,
        )

    return PolicyReleaseDecision(
        code=code,
        release=False,
        reason=rule.get("reason") or "Regra de auto release desconhecida; manter policy por segurança.",
        rule_type=rule_type,
        evidence={},
        policy=policy,
    )


def run_executive_policy_auto_release(context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Executa uma rodada de auto release.

    context esperado, quando disponível:
    {
      "exposure": {"long_pct": 72.0, "short_pct": 28.0, "total_positions": 25},
      "riskstats": {...},
      "learning": {"trades": 31, "by_setup": {...}},
      "health": {...}
    }

    Se context vier vazio, o módulo ainda carrega policies, mas só libera
    regras que tenham evidência suficiente. Na dúvida, mantém a policy.
    """
    started = time.time()
    context = context or {}
    state_file = _find_policy_state_file()
    original_state = _safe_read_json(state_file, {})
    active_policies = _extract_active_policies(original_state)

    decisions: List[PolicyReleaseDecision] = []
    released_codes: List[str] = []
    kept_codes: List[str] = []

    try:
        for policy in active_policies:
            decision = _evaluate_policy(policy, context)
            decisions.append(decision)
            if decision.release:
                released_codes.append(decision.code)
            else:
                kept_codes.append(decision.code)

        updated_state = _save_policy_state_without_released(original_state, released_codes, state_file)

        result = {
            "ok": True,
            "module": MODULE,
            "version": VERSION,
            "generated_at": _now_br(),
            "policy_state_file": state_file,
            "active_before": len(active_policies),
            "released_count": len(released_codes),
            "kept_count": len(kept_codes),
            "released_codes": released_codes,
            "kept_codes": kept_codes,
            "decisions": [asdict(d) for d in decisions],
            "duration_ms": round((time.time() - started) * 1000, 2),
            "notes": [
                "Auto Release V1 remove apenas policies com evidência objetiva.",
                "Na ausência de dados confiáveis, a policy é mantida por segurança.",
                "Policies manual_only/never_auto_release não são removidas na V1.",
            ],
        }

        if released_codes:
            for d in decisions:
                if d.release:
                    _append_jsonl(POLICY_LOG_FILE, {
                        "event": "POLICY_AUTO_RELEASED",
                        "code": d.code,
                        "reason": d.reason,
                        "evidence": d.evidence,
                        "policy": d.policy,
                        "generated_at": result["generated_at"],
                        "module": MODULE,
                        "version": VERSION,
                    })
                    _append_jsonl(AUTO_RELEASE_LOG_FILE, {
                        "event": "AUTO_RELEASE_DECISION",
                        "decision": asdict(d),
                        "generated_at": result["generated_at"],
                        "module": MODULE,
                        "version": VERSION,
                    })
        else:
            _append_jsonl(AUTO_RELEASE_LOG_FILE, {
                "event": "AUTO_RELEASE_NO_RELEASE",
                "active_before": len(active_policies),
                "kept_codes": kept_codes,
                "generated_at": result["generated_at"],
                "module": MODULE,
                "version": VERSION,
            })

        _safe_write_json(AUTO_RELEASE_STATE_FILE, result)
        return result

    except Exception as exc:
        result = {
            "ok": False,
            "module": MODULE,
            "version": VERSION,
            "generated_at": _now_br(),
            "policy_state_file": state_file,
            "error": str(exc),
            "traceback": traceback.format_exc(),
            "released_codes": [],
            "kept_codes": [p.get("code") for p in active_policies if isinstance(p, dict)],
            "notes": ["Falha no Auto Release; nenhuma policy deve ser removida neste ciclo."],
        }
        _append_jsonl(AUTO_RELEASE_LOG_FILE, {
            "event": "AUTO_RELEASE_ERROR",
            "result": result,
            "generated_at": result["generated_at"],
            "module": MODULE,
            "version": VERSION,
        })
        _safe_write_json(AUTO_RELEASE_STATE_FILE, result)
        return result


def build_executive_policy_auto_release_report(result: Optional[Dict[str, Any]] = None) -> str:
    if result is None:
        result = _safe_read_json(AUTO_RELEASE_STATE_FILE, {})

    if not result:
        result = run_executive_policy_auto_release(context={})

    ok = "✅" if result.get("ok") else "❌"
    lines = []
    lines.append("🔓 EXECUTIVE POLICY AUTO RELEASE — CENTRAL QUANT")
    lines.append(f"Data/hora: {result.get('generated_at', _now_br())}")
    lines.append(f"Status: {ok}")
    lines.append(f"Versão: {result.get('version', VERSION)}")
    lines.append("")
    lines.append(f"Policies ativas antes: {result.get('active_before', 0)}")
    lines.append(f"Liberadas agora: {result.get('released_count', 0)}")
    lines.append(f"Mantidas: {result.get('kept_count', 0)}")

    released = result.get("released_codes") or []
    kept = result.get("kept_codes") or []

    lines.append("")
    if released:
        lines.append("✅ Policies liberadas:")
        for code in released:
            lines.append(f"- {code}")
    else:
        lines.append("✅ Nenhuma policy liberada neste ciclo.")

    if kept:
        lines.append("")
        lines.append("🛡️ Policies mantidas:")
        for code in kept:
            lines.append(f"- {code}")

    decisions = result.get("decisions") or []
    if decisions:
        lines.append("")
        lines.append("📌 Decisões:")
        for d in decisions[:12]:
            code = d.get("code")
            release = "RELEASE" if d.get("release") else "KEEP"
            reason = d.get("reason")
            lines.append(f"- {code}: {release} | {reason}")

    if result.get("error"):
        lines.append("")
        lines.append(f"Erro: {result.get('error')}")

    lines.append("")
    lines.append("Notas:")
    for note in result.get("notes", []):
        lines.append(f"- {note}")

    return "\n".join(lines)


def get_executive_policy_auto_release_health() -> Dict[str, Any]:
    state_file = _find_policy_state_file()
    state = _safe_read_json(AUTO_RELEASE_STATE_FILE, {})
    policy_state = _safe_read_json(state_file, {})
    active = _extract_active_policies(policy_state)
    return {
        "ok": True,
        "module": MODULE,
        "version": VERSION,
        "generated_at": _now_br(),
        "loaded": True,
        "policy_state_file": state_file,
        "auto_release_state_file": AUTO_RELEASE_STATE_FILE,
        "auto_release_log_file": AUTO_RELEASE_LOG_FILE,
        "policy_log_file": POLICY_LOG_FILE,
        "active_policy_count": len(active),
        "active_codes": [p.get("code") for p in active],
        "last_run_at": state.get("generated_at"),
        "last_released_codes": state.get("released_codes", []),
        "notes": [
            "Health apenas informa o estado do Auto Release.",
            "Use run_executive_policy_auto_release(context=...) para executar uma rodada.",
        ],
    }


if __name__ == "__main__":
    # Teste local seguro.
    demo_context = {
        "exposure": {
            "long_pct": 72.0,
            "short_pct": 28.0,
            "total_positions": 25,
        },
        "learning": {
            "trades": 31,
        },
    }
    result = run_executive_policy_auto_release(demo_context)
    print(build_executive_policy_auto_release_report(result))
