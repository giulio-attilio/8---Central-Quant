# ============================================================
# CENTRAL QUANT PRO
# EXECUTIVE POLICY TIMELINE V1
# Versão: 2026-07-05-EXECUTIVE-POLICY-TIMELINE-V1
#
# Objetivo:
# - Criar uma linha do tempo executiva das policies da Central Quant.
# - Registrar criação, atualização, remoção, prioridade, expiração e releases.
# - Consumir o Executive Policy Manager como fonte oficial.
# - Não executa trades.
# - Não altera estado operacional dos robôs.
# ============================================================

from __future__ import annotations

import json
import os
import time
import hashlib
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

VERSION = "2026-07-05-EXECUTIVE-POLICY-TIMELINE-V1"
MODULE = "executive_policy_timeline"

DATA_DIR = os.getenv("CENTRAL_DATA_DIR", "/opt/render/project/src/data")
TIMELINE_FILE = os.path.join(DATA_DIR, "executive_policy_timeline.jsonl")
TIMELINE_STATE_FILE = os.path.join(DATA_DIR, "executive_policy_timeline_state.json")
TIMELINE_STATS_FILE = os.path.join(DATA_DIR, "executive_policy_timeline_stats.json")

# Logs opcionais de módulos irmãos. A Timeline V1 consegue resumir esses logs
# quando existirem, mas sua função principal é comparar o snapshot atual de policies.
AUTO_RELEASE_LOG_FILE = os.path.join(DATA_DIR, "executive_policy_auto_release_log.jsonl")
EXPIRATION_LOG_FILE = os.path.join(DATA_DIR, "executive_policy_expiration_log.jsonl")
PRIORITY_LOG_FILE = os.path.join(DATA_DIR, "executive_policy_priority_log.jsonl")


def _now_br() -> str:
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


def _read_jsonl_tail(path: str, limit: int = 20) -> List[Dict[str, Any]]:
    if not os.path.exists(path):
        return []
    try:
        limit = max(1, min(500, int(limit)))
    except Exception:
        limit = 20
    items: List[Dict[str, Any]] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()[-limit:]
        for line in lines:
            try:
                item = json.loads(line)
                if isinstance(item, dict):
                    items.append(item)
            except Exception:
                pass
    except Exception:
        return []
    return items


def _normalize_code(code: Any) -> str:
    return str(code or "").upper().strip().replace(" ", "_").replace("-", "_")


def _normalize_policy_item(item: Any) -> Optional[Dict[str, Any]]:
    if isinstance(item, str):
        code = _normalize_code(item)
        if not code:
            return None
        return {"code": code, "enabled": True}
    if not isinstance(item, dict):
        return None
    code = _normalize_code(
        item.get("code")
        or item.get("policy_code")
        or item.get("name")
        or item.get("id")
    )
    if not code:
        return None
    out = dict(item)
    out["code"] = code
    enabled = out.get("enabled", out.get("active", True))
    out["enabled"] = not (enabled is False or str(enabled).strip().lower() in {"false", "0", "no", "nao", "não", "off", "disabled"})
    return out


def _extract_policy_list(raw: Any) -> List[Dict[str, Any]]:
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, dict):
        items = []
        for key in ["active_policies", "policies", "items", "data", "payload", "result", "active"]:
            value = raw.get(key)
            if isinstance(value, list):
                items = value
                break
            if isinstance(value, dict):
                nested = _extract_policy_list(value)
                if nested:
                    return nested
        if not items and isinstance(raw.get("active_codes"), list):
            items = [{"code": code, "enabled": True} for code in raw.get("active_codes", [])]
        if not items:
            for key, value in raw.items():
                if isinstance(value, dict):
                    item = dict(value)
                    item.setdefault("code", key)
                    items.append(item)
    else:
        items = []

    policies: List[Dict[str, Any]] = []
    seen = set()
    for item in items:
        p = _normalize_policy_item(item)
        if not p:
            continue
        code = p.get("code")
        if not code or code in seen:
            continue
        seen.add(code)
        policies.append(p)
    return policies


def _load_active_policies_from_manager() -> Tuple[List[Dict[str, Any]], Optional[str]]:
    try:
        import executive_policy_manager  # type: ignore
        if hasattr(executive_policy_manager, "get_active_policies"):
            raw = executive_policy_manager.get_active_policies()
            return _extract_policy_list(raw), "executive_policy_manager.get_active_policies"
        if hasattr(executive_policy_manager, "load_policy_state"):
            raw = executive_policy_manager.load_policy_state()
            return _extract_policy_list(raw), "executive_policy_manager.load_policy_state"
        return [], "executive_policy_manager.no_supported_function"
    except Exception as exc:
        return [], f"error:{exc}"


def _policy_fingerprint(policy: Dict[str, Any]) -> str:
    relevant = {
        "code": policy.get("code"),
        "title": policy.get("title"),
        "level": policy.get("level"),
        "category": policy.get("category"),
        "action": policy.get("action"),
        "reason": policy.get("reason"),
        "enabled": policy.get("enabled"),
        "expires_at": policy.get("expires_at"),
        "release_condition": policy.get("release_condition"),
        "payload": policy.get("payload") if isinstance(policy.get("payload"), dict) else {},
    }
    raw = json.dumps(relevant, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _compact_policy(policy: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(policy, dict):
        return None
    payload = policy.get("payload") if isinstance(policy.get("payload"), dict) else {}
    compact_payload = {}
    for key in [
        "dominant_side", "dominant_pct", "allow_expansion", "blocks_expansion",
        "monthly_trades", "adaptive_confidence", "ceo_confidence", "allow_risk_increase",
        "size_multiplier", "max_risk_pct",
    ]:
        if key in payload:
            compact_payload[key] = payload.get(key)
    return {
        "code": policy.get("code"),
        "title": policy.get("title"),
        "level": policy.get("level"),
        "category": policy.get("category"),
        "action": policy.get("action"),
        "reason": policy.get("reason"),
        "enabled": policy.get("enabled", True),
        "created_at": policy.get("created_at"),
        "updated_at": policy.get("updated_at"),
        "expires_at": policy.get("expires_at"),
        "release_condition": policy.get("release_condition"),
        "source": policy.get("source"),
        "payload": compact_payload,
    }


def _build_event(event_type: str, code: str, source: str, policy: Optional[Dict[str, Any]] = None, previous: Optional[Dict[str, Any]] = None, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "ok": True,
        "module": MODULE,
        "version": VERSION,
        "event_type": str(event_type or "").upper(),
        "code": _normalize_code(code),
        "source": source,
        "generated_at": _now_br(),
        "policy": _compact_policy(policy),
        "previous": _compact_policy(previous),
        "details": details or {},
    }


def _summarize_external_logs(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Registra eventos derivados dos logs de Auto Release, Expiration e Priority.
    Evita duplicidade guardando o último fingerprint processado por origem.
    """
    events: List[Dict[str, Any]] = []
    processed = state.setdefault("external_log_fingerprints", {})

    sources = [
        ("AUTO_RELEASE", AUTO_RELEASE_LOG_FILE),
        ("EXPIRATION", EXPIRATION_LOG_FILE),
        ("PRIORITY", PRIORITY_LOG_FILE),
    ]

    for source_name, path in sources:
        items = _read_jsonl_tail(path, limit=5)
        for item in items:
            fp_raw = json.dumps(item, ensure_ascii=False, sort_keys=True)
            fp = hashlib.sha256(fp_raw.encode("utf-8")).hexdigest()[:20]
            key = f"{source_name}:{fp}"
            if processed.get(key):
                continue

            if source_name == "AUTO_RELEASE":
                released = item.get("released_codes") or item.get("last_released_codes") or []
                for code in released if isinstance(released, list) else []:
                    events.append(_build_event(
                        event_type="POLICY_AUTO_RELEASED",
                        code=code,
                        source="executive_policy_auto_release",
                        details={"origin_log": path, "summary": item.get("summary") or item.get("notes")},
                    ))
            elif source_name == "EXPIRATION":
                expired = item.get("expired_codes") or item.get("last_expired_codes") or []
                for code in expired if isinstance(expired, list) else []:
                    events.append(_build_event(
                        event_type="POLICY_EXPIRED",
                        code=code,
                        source="executive_policy_expiration",
                        details={"origin_log": path, "summary": item.get("summary") or item.get("notes")},
                    ))
            elif source_name == "PRIORITY":
                dominant = item.get("dominant_code")
                if dominant:
                    last_dominant = state.get("last_priority_dominant_code")
                    if dominant != last_dominant:
                        events.append(_build_event(
                            event_type="POLICY_PRIORITY_DOMINANT",
                            code=dominant,
                            source="executive_policy_priority",
                            details={
                                "previous_dominant_code": last_dominant,
                                "decision": item.get("decision"),
                                "allowed": item.get("allowed"),
                                "size_multiplier": item.get("size_multiplier"),
                            },
                        ))
                        state["last_priority_dominant_code"] = dominant

            processed[key] = True

    # Limita crescimento do dicionário de fingerprints.
    if len(processed) > 300:
        keys = list(processed.keys())[-150:]
        state["external_log_fingerprints"] = {k: True for k in keys}

    return events


def sync_executive_policy_timeline(context: Optional[Dict[str, Any]] = None, commit: bool = True) -> Dict[str, Any]:
    """
    Compara o snapshot atual do Policy Manager com o último snapshot conhecido
    e gera eventos da linha do tempo.
    """
    policies, source = _load_active_policies_from_manager()
    state = _safe_read_json(TIMELINE_STATE_FILE, default={}) or {}

    previous_by_code = state.get("policies_by_code") if isinstance(state.get("policies_by_code"), dict) else {}
    current_by_code: Dict[str, Dict[str, Any]] = {}
    current_fingerprints: Dict[str, str] = {}

    events: List[Dict[str, Any]] = []

    for policy in policies:
        code = _normalize_code(policy.get("code"))
        if not code:
            continue
        current_by_code[code] = _compact_policy(policy) or {"code": code}
        current_fingerprints[code] = _policy_fingerprint(policy)

        previous = previous_by_code.get(code) if isinstance(previous_by_code, dict) else None
        previous_fp = previous.get("_fingerprint") if isinstance(previous, dict) else None

        if not previous:
            events.append(_build_event("POLICY_CREATED", code, source or "unknown", policy=policy))
        elif previous_fp and previous_fp != current_fingerprints[code]:
            events.append(_build_event("POLICY_UPDATED", code, source or "unknown", policy=policy, previous=previous))

    previous_codes = set(previous_by_code.keys()) if isinstance(previous_by_code, dict) else set()
    current_codes = set(current_by_code.keys())

    for code in sorted(previous_codes - current_codes):
        previous = previous_by_code.get(code)
        events.append(_build_event("POLICY_REMOVED", code, source or "unknown", previous=previous))

    # Events de módulos irmãos, sem alterar as policies.
    events.extend(_summarize_external_logs(state))

    for code, policy in current_by_code.items():
        policy["_fingerprint"] = current_fingerprints.get(code)

    if events and commit:
        for event in events:
            _append_jsonl(TIMELINE_FILE, event)

    # Atualiza estado mesmo se não houver evento, para snapshot corrente.
    if commit:
        state.update({
            "ok": True,
            "module": MODULE,
            "version": VERSION,
            "last_run_at": _now_br(),
            "policy_source": source,
            "active_policy_count": len(current_by_code),
            "active_codes": sorted(current_by_code.keys()),
            "policies_by_code": current_by_code,
            "last_event_count": len(events),
            "last_event_types": [e.get("event_type") for e in events],
        })
        _safe_write_json(TIMELINE_STATE_FILE, state)
        _rebuild_stats()

    return {
        "ok": True,
        "module": MODULE,
        "version": VERSION,
        "generated_at": _now_br(),
        "policy_source": source,
        "active_policy_count": len(current_by_code),
        "active_codes": sorted(current_by_code.keys()),
        "events_created": len(events),
        "events": events,
        "timeline_file": TIMELINE_FILE,
        "timeline_state_file": TIMELINE_STATE_FILE,
        "notes": [
            "Timeline V1 registra eventos comparando snapshot atual com snapshot anterior.",
            "O módulo não cria, remove ou executa policies.",
            "Auto Release, Expiration e Priority continuam sendo módulos independentes.",
        ],
    }


def read_executive_policy_timeline(limit: int = 30, event_type: Optional[str] = None, code: Optional[str] = None) -> Dict[str, Any]:
    try:
        limit = max(1, min(300, int(limit)))
    except Exception:
        limit = 30

    items = _read_jsonl_tail(TIMELINE_FILE, limit=max(limit * 3, limit))
    et = str(event_type or "").upper().strip()
    cd = _normalize_code(code)

    filtered = []
    for item in items:
        if et and str(item.get("event_type") or "").upper() != et:
            continue
        if cd and _normalize_code(item.get("code")) != cd:
            continue
        filtered.append(item)

    filtered = filtered[-limit:]
    return {
        "ok": True,
        "module": MODULE,
        "version": VERSION,
        "generated_at": _now_br(),
        "count": len(filtered),
        "items": filtered,
        "timeline_file": TIMELINE_FILE,
    }


def _rebuild_stats() -> Dict[str, Any]:
    items = _read_jsonl_tail(TIMELINE_FILE, limit=5000)
    by_type: Dict[str, int] = {}
    by_code: Dict[str, int] = {}
    created = 0
    removed = 0
    updated = 0

    for item in items:
        event_type = str(item.get("event_type") or "UNKNOWN").upper()
        code = _normalize_code(item.get("code")) or "UNKNOWN"
        by_type[event_type] = by_type.get(event_type, 0) + 1
        by_code[code] = by_code.get(code, 0) + 1
        if event_type == "POLICY_CREATED":
            created += 1
        elif event_type in {"POLICY_REMOVED", "POLICY_AUTO_RELEASED", "POLICY_EXPIRED"}:
            removed += 1
        elif event_type == "POLICY_UPDATED":
            updated += 1

    stats = {
        "ok": True,
        "module": MODULE,
        "version": VERSION,
        "generated_at": _now_br(),
        "total_events": len(items),
        "created_count": created,
        "removed_or_released_count": removed,
        "updated_count": updated,
        "by_event_type": dict(sorted(by_type.items(), key=lambda kv: (-kv[1], kv[0]))),
        "by_code": dict(sorted(by_code.items(), key=lambda kv: (-kv[1], kv[0]))[:30]),
        "timeline_file": TIMELINE_FILE,
        "stats_file": TIMELINE_STATS_FILE,
    }
    _safe_write_json(TIMELINE_STATS_FILE, stats)
    return stats


def get_executive_policy_timeline_stats() -> Dict[str, Any]:
    stats = _safe_read_json(TIMELINE_STATS_FILE, default=None)
    if isinstance(stats, dict) and stats.get("ok"):
        return stats
    return _rebuild_stats()


def get_executive_policy_timeline_health() -> Dict[str, Any]:
    state = _safe_read_json(TIMELINE_STATE_FILE, default={}) or {}
    policies, source = _load_active_policies_from_manager()
    stats = get_executive_policy_timeline_stats()
    return {
        "ok": True,
        "loaded": True,
        "module": MODULE,
        "version": VERSION,
        "generated_at": _now_br(),
        "policy_source": source,
        "active_policy_count": len(policies),
        "active_codes": [_normalize_code(p.get("code")) for p in policies],
        "last_run_at": state.get("last_run_at"),
        "last_event_count": state.get("last_event_count"),
        "total_events": stats.get("total_events", 0),
        "timeline_file": TIMELINE_FILE,
        "timeline_state_file": TIMELINE_STATE_FILE,
        "timeline_stats_file": TIMELINE_STATS_FILE,
        "notes": ["Health apenas informa o estado do Timeline V1."],
    }


def build_executive_policy_timeline_report(result: Optional[Dict[str, Any]] = None, limit: int = 20) -> str:
    if result is None:
        result = sync_executive_policy_timeline(context={}, commit=True)

    recent = read_executive_policy_timeline(limit=limit).get("items", [])
    stats = get_executive_policy_timeline_stats()

    lines = [
        "🧭 EXECUTIVE POLICY TIMELINE — CENTRAL QUANT",
        f"Data/hora: {result.get('generated_at') or _now_br()}",
        f"Status: {'✅' if result.get('ok') else '❌'}",
        f"Versão: {VERSION}",
        "",
        f"Fonte: {result.get('policy_source')}",
        f"Policies ativas: {result.get('active_policy_count', 0)}",
        f"Eventos criados agora: {result.get('events_created', 0)}",
        f"Eventos totais: {stats.get('total_events', 0)}",
        "",
    ]

    events = result.get("events") or []
    if events:
        lines.append("Eventos deste ciclo:")
        for event in events[:15]:
            lines.append(f"- {event.get('generated_at')} | {event.get('event_type')} | {event.get('code')} | origem={event.get('source')}")
        lines.append("")
    else:
        lines.append("✅ Nenhum novo evento neste ciclo.")
        lines.append("")

    if recent:
        lines.append("Últimos eventos:")
        for event in recent[-limit:]:
            policy = event.get("policy") or {}
            title = policy.get("title") or ""
            extra = f" — {title}" if title else ""
            lines.append(f"- {event.get('generated_at')} | {event.get('event_type')} | {event.get('code')}{extra}")
        lines.append("")

    by_type = stats.get("by_event_type") or {}
    if by_type:
        lines.append("Resumo por tipo:")
        for key, value in list(by_type.items())[:10]:
            lines.append(f"- {key}: {value}")
        lines.append("")

    lines += [
        "Notas:",
        "- Timeline V1 cria memória executiva das policies.",
        "- Ela não decide risco nem executa trades.",
        "- O próximo passo natural será usar essa linha do tempo no Policy Learning.",
    ]
    return "\n".join(lines)


def build_executive_policy_timeline_stats_report() -> str:
    stats = get_executive_policy_timeline_stats()
    lines = [
        "📊 EXECUTIVE POLICY TIMELINE STATS — CENTRAL QUANT",
        f"Data/hora: {stats.get('generated_at') or _now_br()}",
        f"Status: {'✅' if stats.get('ok') else '❌'}",
        f"Versão: {VERSION}",
        "",
        f"Eventos totais: {stats.get('total_events', 0)}",
        f"Policies criadas: {stats.get('created_count', 0)}",
        f"Policies removidas/liberadas/expiradas: {stats.get('removed_or_released_count', 0)}",
        f"Policies atualizadas: {stats.get('updated_count', 0)}",
        "",
        "Por tipo:",
    ]

    by_type = stats.get("by_event_type") or {}
    if by_type:
        for key, value in list(by_type.items())[:20]:
            lines.append(f"- {key}: {value}")
    else:
        lines.append("- N/A")

    lines += ["", "Por policy:"]
    by_code = stats.get("by_code") or {}
    if by_code:
        for key, value in list(by_code.items())[:20]:
            lines.append(f"- {key}: {value}")
    else:
        lines.append("- N/A")

    return "\n".join(lines)


if __name__ == "__main__":
    print(build_executive_policy_timeline_report())
