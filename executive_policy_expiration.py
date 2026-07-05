# ============================================================
# CENTRAL QUANT PRO
# EXECUTIVE POLICY EXPIRATION V1
# Versão: 2026-07-05-EXECUTIVE-POLICY-EXPIRATION-V1
#
# Objetivo:
# - Controlar expiração temporal de políticas executivas.
# - Remover/desativar policies cujo expires_at já passou.
# - Usar o Executive Policy Manager como fonte oficial quando disponível.
# - Não executa trades.
# - Não altera lote.
# - Não altera risco real.
# - Não remove policies sem expires_at na V1, por segurança.
# ============================================================

from __future__ import annotations

import inspect
import json
import os
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

VERSION = "2026-07-05-EXECUTIVE-POLICY-EXPIRATION-V1"
MODULE = "executive_policy_expiration"

DATA_DIR = os.getenv("CENTRAL_DATA_DIR", "/opt/render/project/src/data")
POLICY_STATE_FILE = os.path.join(DATA_DIR, "executive_policy_state.json")
POLICY_LOG_FILE = os.path.join(DATA_DIR, "executive_policy_log.jsonl")
EXPIRATION_LOG_FILE = os.path.join(DATA_DIR, "executive_policy_expiration_log.jsonl")
EXPIRATION_STATE_FILE = os.path.join(DATA_DIR, "executive_policy_expiration_state.json")

POLICY_STATE_CANDIDATES = [
    POLICY_STATE_FILE,
    os.path.join(DATA_DIR, "executive_policies.json"),
    os.path.join(DATA_DIR, "executive_policy_manager_state.json"),
    os.path.join(DATA_DIR, "executive_policy_active.json"),
]

# Segurança: V1 não aplica TTL padrão automaticamente, a menos que você ligue por env.
# Assim, policies sem expires_at continuam sendo governadas por Auto Release/Priority.
ENABLE_DEFAULT_TTL = str(os.getenv("EXECUTIVE_POLICY_EXPIRATION_ENABLE_DEFAULT_TTL", "false")).strip().lower() in {"1", "true", "yes", "sim", "on"}

DEFAULT_TTL_HOURS = {
    "LIMIT_NEW_LONG": 12,
    "LIMIT_NEW_SHORT": 12,
    "NO_NEW_LONG": 12,
    "NO_NEW_SHORT": 12,
    "WAIT_SAMPLE": 24,
    "NORMAL_WITH_MONITORING": 24,
}

MANUAL_ONLY_CODES = {
    "EMERGENCY_STOP",
    "KILL_SWITCH",
    "BLOCK_ALL",
    "TRADING_HALT",
    "HALT_TRADING",
    "BLOCK_REAL_EXECUTION",
    "EXECUTION_BLOCKED",
}


def _now_br_dt() -> datetime:
    # Horário operacional da Central: UTC-3 fixo.
    return datetime.utcfromtimestamp(time.time() - 3 * 3600)


def _now_br() -> str:
    return _now_br_dt().strftime("%d/%m/%Y %H:%M:%S")


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
            raw = f.read().strip()
        if not raw:
            return default
        return json.loads(raw)
    except Exception:
        return default


def _safe_write_json(path: str, payload: Any) -> bool:
    try:
        _ensure_data_dir()
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)
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


def _normalize_policy_entry(item: Any) -> Optional[Dict[str, Any]]:
    if isinstance(item, str):
        code = _normalize_code(item)
        return {"code": code, "enabled": True, "active": True} if code else None
    if isinstance(item, dict):
        code = _normalize_code(item.get("code") or item.get("policy_code") or item.get("name") or item.get("id"))
        if not code:
            return None
        normalized = dict(item)
        normalized["code"] = code
        enabled = normalized.get("enabled", normalized.get("active", True))
        enabled_str = str(enabled).strip().lower()
        disabled = enabled is False or enabled_str in {"false", "0", "no", "não", "nao", "off", "disabled"}
        normalized["enabled"] = not disabled
        normalized["active"] = not disabled
        return normalized
    return None


def _extract_policy_items(raw: Any, include_disabled: bool = False) -> List[Dict[str, Any]]:
    def first_list(value: Any, depth: int = 0) -> List[Any]:
        if value is None or depth > 5:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            for key in ["active_policies", "policies", "items", "data", "payload", "result", "active"]:
                found = first_list(value.get(key), depth + 1)
                if found:
                    return found
            codes = value.get("active_codes") or value.get("codes")
            if isinstance(codes, list) and codes:
                return [{"code": code, "enabled": True, "active": True} for code in codes]
            dict_items = []
            for key, child in value.items():
                if isinstance(child, dict):
                    item = dict(child)
                    item.setdefault("code", key)
                    dict_items.append(item)
            return dict_items
        return []

    items = first_list(raw)
    out: List[Dict[str, Any]] = []
    seen = set()
    for item in items:
        p = _normalize_policy_entry(item)
        if not p:
            continue
        code = p.get("code")
        if not code or code in seen:
            continue
        if p.get("active", True) is False and not include_disabled:
            continue
        seen.add(code)
        out.append(p)
    return out


def _load_from_manager() -> Tuple[List[Dict[str, Any]], str, Optional[str]]:
    try:
        import executive_policy_manager  # type: ignore
    except Exception as exc:
        return [], "manager_import_failed", str(exc)

    try:
        if hasattr(executive_policy_manager, "get_active_policies"):
            raw = executive_policy_manager.get_active_policies()
            return _extract_policy_items(raw, include_disabled=False), "executive_policy_manager.get_active_policies", None
        if hasattr(executive_policy_manager, "load_policy_state"):
            raw = executive_policy_manager.load_policy_state()
            return _extract_policy_items(raw, include_disabled=False), "executive_policy_manager.load_policy_state", None
        if hasattr(executive_policy_manager, "policy_manager_health"):
            raw = executive_policy_manager.policy_manager_health()
            return _extract_policy_items(raw, include_disabled=False), "executive_policy_manager.policy_manager_health", None
        return [], "manager_no_supported_function", "Executive Policy Manager não tem função suportada para listar policies."
    except Exception as exc:
        return [], "manager_call_failed", str(exc)


def _load_policy_state_file() -> Tuple[Any, Optional[str]]:
    for path in POLICY_STATE_CANDIDATES:
        data = _safe_read_json(path, default=None)
        if data is not None:
            return data, path
    return {}, None


def _parse_datetime(value: Any) -> Optional[datetime]:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        try:
            # Epoch em segundos. Se vier em ms, reduzimos.
            ts = float(value)
            if ts > 10_000_000_000:
                ts = ts / 1000.0
            return datetime.utcfromtimestamp(ts - 3 * 3600)
        except Exception:
            return None

    txt = str(value).strip()
    if not txt or txt.lower() in {"none", "null", "n/a"}:
        return None
    txt = txt.replace("T", " ").replace("Z", "").strip()

    formats = [
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%d/%m/%Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(txt[:19] if "%S" in fmt and len(txt) >= 19 else txt, fmt)
        except Exception:
            pass
    return None


def _ttl_expiration_for_policy(policy: Dict[str, Any]) -> Optional[datetime]:
    """Retorna expiração por TTL apenas se habilitada explicitamente por env ou policy."""
    code = _normalize_code(policy.get("code"))

    ttl_hours = None
    for key in ["ttl_hours", "expires_after_hours", "expiration_hours"]:
        if policy.get(key) is not None:
            try:
                ttl_hours = float(policy.get(key))
                break
            except Exception:
                pass

    if ttl_hours is None and ENABLE_DEFAULT_TTL:
        ttl_hours = DEFAULT_TTL_HOURS.get(code)

    if ttl_hours is None:
        return None

    created_at = _parse_datetime(policy.get("created_at") or policy.get("created") or policy.get("updated_at"))
    if not created_at:
        return None
    return created_at + timedelta(hours=ttl_hours)


def _policy_expiration_datetime(policy: Dict[str, Any]) -> Tuple[Optional[datetime], str]:
    for key in ["expires_at", "expire_at", "expiration_at", "valid_until", "expires"]:
        dt = _parse_datetime(policy.get(key))
        if dt:
            return dt, key

    ttl_dt = _ttl_expiration_for_policy(policy)
    if ttl_dt:
        return ttl_dt, "ttl"

    payload = policy.get("payload") if isinstance(policy.get("payload"), dict) else {}
    for key in ["expires_at", "expire_at", "expiration_at", "valid_until"]:
        dt = _parse_datetime(payload.get(key))
        if dt:
            return dt, f"payload.{key}"

    return None, "none"


def _is_manual_only(policy: Dict[str, Any]) -> bool:
    code = _normalize_code(policy.get("code"))
    if code in MANUAL_ONLY_CODES:
        return True
    for key in ["manual_only", "never_auto_release", "never_expire", "permanent"]:
        value = policy.get(key)
        if str(value).strip().lower() in {"1", "true", "yes", "sim", "on"}:
            return True
    payload = policy.get("payload") if isinstance(policy.get("payload"), dict) else {}
    for key in ["manual_only", "never_auto_release", "never_expire", "permanent"]:
        value = payload.get(key)
        if str(value).strip().lower() in {"1", "true", "yes", "sim", "on"}:
            return True
    return False


def _manager_mutate_policy(code: str, reason: str) -> Tuple[bool, str]:
    try:
        import executive_policy_manager  # type: ignore
    except Exception as exc:
        return False, f"manager_import_failed: {exc}"

    candidate_names = [
        "expire_policy",
        "release_policy",
        "remove_policy",
        "disable_policy",
        "deactivate_policy",
        "set_policy_inactive",
    ]

    for name in candidate_names:
        fn = getattr(executive_policy_manager, name, None)
        if not callable(fn):
            continue
        try:
            sig = inspect.signature(fn)
            params = list(sig.parameters.keys())
            kwargs = {}
            if "reason" in params:
                kwargs["reason"] = reason
            if "source" in params:
                kwargs["source"] = MODULE
            if "released_by" in params:
                kwargs["released_by"] = MODULE
            if "expired_by" in params:
                kwargs["expired_by"] = MODULE
            result = fn(code, **kwargs)
            return True, f"executive_policy_manager.{name}: {result}"
        except TypeError:
            try:
                result = fn(code)
                return True, f"executive_policy_manager.{name}: {result}"
            except Exception as exc2:
                last_error = str(exc2)
        except Exception as exc:
            last_error = str(exc)
    return False, f"manager_mutator_not_available_or_failed: {locals().get('last_error', 'no callable mutator')}"


def _save_policy_state_without_expired(original_state: Any, expired_codes: List[str], state_file: Optional[str]) -> Tuple[bool, Any, str]:
    expired_set = {_normalize_code(c) for c in expired_codes if _normalize_code(c)}
    if not expired_set:
        return True, original_state, "nothing_to_expire"
    if not state_file:
        return False, original_state, "state_file_not_found"

    updated = original_state
    if isinstance(original_state, list):
        updated = []
        for item in original_state:
            p = _normalize_policy_entry(item)
            code = p.get("code") if p else None
            if code in expired_set:
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
                    if code in expired_set:
                        continue
                    filtered.append(item)
                updated[key] = filtered
        if isinstance(updated.get("active_codes"), list):
            updated["active_codes"] = [c for c in updated["active_codes"] if _normalize_code(c) not in expired_set]
        for code in list(expired_set):
            if code in updated and isinstance(updated[code], dict):
                updated[code] = dict(updated[code])
                updated[code]["active"] = False
                updated[code]["enabled"] = False
                updated[code]["expired_at"] = _now_br()
                updated[code]["expired_by"] = MODULE
        updated["last_policy_expiration_at"] = _now_br()
        updated["last_policy_expiration_codes"] = sorted(expired_set)
        updated["version_policy_expiration"] = VERSION
    else:
        return False, original_state, "unsupported_state_format"

    ok = _safe_write_json(state_file, updated)
    return ok, updated, f"file_update:{state_file}" if ok else f"file_update_failed:{state_file}"


def _expire_codes(expired_codes: List[str], reason_by_code: Dict[str, str]) -> Dict[str, Any]:
    actions = []
    manager_success = []
    manager_failed = []

    for code in expired_codes:
        ok, msg = _manager_mutate_policy(code, reason_by_code.get(code) or "Policy expirada pelo Executive Policy Expiration V1.")
        actions.append({"code": code, "manager_ok": ok, "manager_msg": msg})
        if ok:
            manager_success.append(code)
        else:
            manager_failed.append(code)

    fallback_ok = None
    fallback_msg = None
    if manager_failed:
        original_state, state_file = _load_policy_state_file()
        fallback_ok, _, fallback_msg = _save_policy_state_without_expired(original_state, manager_failed, state_file)

    return {
        "manager_success": manager_success,
        "manager_failed": manager_failed,
        "fallback_ok": fallback_ok,
        "fallback_msg": fallback_msg,
        "actions": actions,
    }


def run_executive_policy_expiration(context: Optional[Dict[str, Any]] = None, commit: bool = True) -> Dict[str, Any]:
    context = context or {}
    now = _now_br_dt()
    policies, source, source_error = _load_from_manager()

    checked = []
    expired_codes: List[str] = []
    kept_codes: List[str] = []
    skipped_codes: List[str] = []
    reason_by_code: Dict[str, str] = {}

    for policy in policies:
        code = _normalize_code(policy.get("code"))
        exp_dt, exp_source = _policy_expiration_datetime(policy)
        manual_only = _is_manual_only(policy)

        item = {
            "code": code,
            "title": policy.get("title"),
            "level": policy.get("level"),
            "category": policy.get("category"),
            "expires_at_raw": policy.get("expires_at"),
            "expiration_source": exp_source,
            "expiration_at": exp_dt.strftime("%d/%m/%Y %H:%M:%S") if exp_dt else None,
            "manual_only": manual_only,
            "decision": "KEEP",
            "reason": None,
        }

        if manual_only:
            item["decision"] = "SKIP"
            item["reason"] = "Policy manual/permanente; Expiration V1 não remove."
            skipped_codes.append(code)
        elif not exp_dt:
            item["decision"] = "KEEP"
            item["reason"] = "Policy sem expires_at/TTL; mantida por segurança na V1."
            kept_codes.append(code)
        elif exp_dt <= now:
            item["decision"] = "EXPIRE"
            item["reason"] = f"Policy expirada em {item['expiration_at']} ({exp_source})."
            expired_codes.append(code)
            reason_by_code[code] = item["reason"]
        else:
            item["decision"] = "KEEP"
            remaining = exp_dt - now
            item["reason"] = f"Policy ainda válida por aproximadamente {round(remaining.total_seconds()/3600, 2)}h."
            kept_codes.append(code)

        checked.append(item)

    mutation = {"manager_success": [], "manager_failed": [], "fallback_ok": None, "fallback_msg": None, "actions": []}
    if commit and expired_codes:
        mutation = _expire_codes(expired_codes, reason_by_code)

    result = {
        "ok": True,
        "module": MODULE,
        "version": VERSION,
        "generated_at": _now_br(),
        "policy_source": source,
        "source_error": source_error,
        "active_policy_count": len(policies),
        "checked_count": len(checked),
        "expired_count": len(expired_codes),
        "kept_count": len(kept_codes),
        "skipped_count": len(skipped_codes),
        "expired_codes": expired_codes,
        "kept_codes": kept_codes,
        "skipped_codes": skipped_codes,
        "checked": checked,
        "mutation": mutation,
        "commit": commit,
        "default_ttl_enabled": ENABLE_DEFAULT_TTL,
        "notes": [
            "Expiration V1 remove apenas policies com expires_at/TTL vencido.",
            "Policies sem expires_at são mantidas por segurança.",
            "Policies manual_only/never_expire/permanent não são removidas na V1.",
            "Auto Release continua responsável por liberar policies quando a condição objetiva desaparece.",
        ],
    }

    if commit:
        _safe_write_json(EXPIRATION_STATE_FILE, result)
        _append_jsonl(EXPIRATION_LOG_FILE, result)
        if expired_codes:
            for code in expired_codes:
                _append_jsonl(POLICY_LOG_FILE, {
                    "event": "POLICY_EXPIRED",
                    "code": code,
                    "reason": reason_by_code.get(code),
                    "module": MODULE,
                    "version": VERSION,
                    "generated_at": _now_br(),
                })

    return result


def build_executive_policy_expiration_report(result: Optional[Dict[str, Any]] = None) -> str:
    result = result or run_executive_policy_expiration(context={}, commit=True)
    lines = [
        "⏳ EXECUTIVE POLICY EXPIRATION — CENTRAL QUANT",
        f"Data/hora: {result.get('generated_at') or _now_br()}",
        f"Status: {'✅' if result.get('ok') else '❌'}",
        f"Versão: {VERSION}",
        "",
        f"Fonte: {result.get('policy_source')}",
        f"Policies ativas: {result.get('active_policy_count', 0)}",
        f"Verificadas: {result.get('checked_count', 0)}",
        f"Expiradas agora: {result.get('expired_count', 0)}",
        f"Mantidas: {result.get('kept_count', 0)}",
        f"Ignoradas/manual: {result.get('skipped_count', 0)}",
        f"Default TTL ativo: {result.get('default_ttl_enabled')}",
        "",
    ]

    if result.get("source_error"):
        lines += ["Aviso de fonte:", f"- {result.get('source_error')}", ""]

    expired = result.get("expired_codes") or []
    if expired:
        lines.append("Policies expiradas:")
        for code in expired:
            lines.append(f"- {code}")
        lines.append("")
    else:
        lines += ["✅ Nenhuma policy expirada neste ciclo.", ""]

    checked = result.get("checked") or []
    if checked:
        lines.append("Checagem:")
        for item in checked[:20]:
            exp = item.get("expiration_at") or "sem expires_at"
            lines.append(f"- {item.get('code')}: {item.get('decision')} | {exp} | {item.get('reason')}")
        lines.append("")

    mutation = result.get("mutation") or {}
    if expired:
        lines.append("Mutação:")
        lines.append(f"- Manager success: {mutation.get('manager_success')}")
        lines.append(f"- Manager failed: {mutation.get('manager_failed')}")
        lines.append(f"- Fallback: {mutation.get('fallback_ok')} | {mutation.get('fallback_msg')}")
        lines.append("")

    lines += ["Notas:"]
    for note in result.get("notes") or []:
        lines.append(f"- {note}")
    return "\n".join(lines)


def get_executive_policy_expiration_health() -> Dict[str, Any]:
    policies, source, source_error = _load_from_manager()
    last = _safe_read_json(EXPIRATION_STATE_FILE, default={}) or {}
    expirable = []
    for p in policies:
        code = _normalize_code(p.get("code"))
        exp_dt, exp_source = _policy_expiration_datetime(p)
        expirable.append({
            "code": code,
            "expiration_source": exp_source,
            "expiration_at": exp_dt.strftime("%d/%m/%Y %H:%M:%S") if exp_dt else None,
            "manual_only": _is_manual_only(p),
        })
    return {
        "ok": True,
        "loaded": True,
        "module": MODULE,
        "version": VERSION,
        "generated_at": _now_br(),
        "policy_source": source,
        "source_error": source_error,
        "active_policy_count": len(policies),
        "active_codes": [_normalize_code(p.get("code")) for p in policies],
        "expiration_state_file": EXPIRATION_STATE_FILE,
        "expiration_log_file": EXPIRATION_LOG_FILE,
        "last_run_at": last.get("generated_at"),
        "last_expired_codes": last.get("expired_codes", []),
        "default_ttl_enabled": ENABLE_DEFAULT_TTL,
        "expirable": expirable,
        "notes": ["Health apenas informa o estado do Expiration V1."],
    }


def read_executive_policy_expiration_log(limit: int = 20) -> Dict[str, Any]:
    try:
        limit = max(1, min(200, int(limit)))
    except Exception:
        limit = 20
    if not os.path.exists(EXPIRATION_LOG_FILE):
        return {"ok": True, "items": [], "count": 0, "log_file": EXPIRATION_LOG_FILE}
    items: List[Dict[str, Any]] = []
    try:
        with open(EXPIRATION_LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()[-limit:]
        for line in lines:
            try:
                items.append(json.loads(line))
            except Exception:
                pass
        return {"ok": True, "items": items, "count": len(items), "log_file": EXPIRATION_LOG_FILE}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "items": [], "log_file": EXPIRATION_LOG_FILE}


if __name__ == "__main__":
    print(build_executive_policy_expiration_report())
