# executive_policy_learning.py
# Central Quant — Executive Policy Learning V1
# Versão: 2026-07-05-EXECUTIVE-POLICY-LEARNING-V1
#
# Objetivo:
# - Avaliar estatisticamente se as políticas executivas estão ajudando ou prejudicando.
# - Registrar impactos por policy code: bloqueios, releases, wins/losses, PnL salvo/perdido,
#   eficiência e recomendação.
# - Ser leve em memória: leitura incremental, arquivos pequenos e sem carregar histórico inteiro.

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


VERSION = "2026-07-05-EXECUTIVE-POLICY-LEARNING-V1"
MODULE = "executive_policy_learning"

DATA_DIR = os.getenv("CENTRAL_DATA_DIR", "/opt/render/project/src/data")

POLICY_LEARNING_STATE_FILE = os.path.join(DATA_DIR, "executive_policy_learning_state.json")
POLICY_LEARNING_STATS_FILE = os.path.join(DATA_DIR, "executive_policy_learning_stats.json")
POLICY_LEARNING_EVENTS_FILE = os.path.join(DATA_DIR, "executive_policy_learning_events.jsonl")

# Fontes possíveis já existentes na Central.
EXECUTIVE_POLICY_TIMELINE_FILE = os.path.join(DATA_DIR, "executive_policy_timeline.jsonl")
DECISION_LOG_FILE = os.path.join(DATA_DIR, "decision_log.jsonl")
HISTORY_EVENTS_FILE = os.path.join(DATA_DIR, "history_events.jsonl")

MAX_EVENTS_PER_RUN = int(os.getenv("POLICY_LEARNING_MAX_EVENTS_PER_RUN", "250"))
MAX_RECENT_EVENTS = int(os.getenv("POLICY_LEARNING_MAX_RECENT_EVENTS", "50"))
MIN_SAMPLE_FOR_CONFIDENCE = int(os.getenv("POLICY_LEARNING_MIN_SAMPLE", "20"))


# -----------------------------------------------------------------------------
# Utilidades leves
# -----------------------------------------------------------------------------

def _now_str() -> str:
    return datetime.now().strftime("%d/%m/%Y %H:%M:%S")


def _ensure_data_dir() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def _read_json(path: str, default: Any) -> Any:
    try:
        if not os.path.exists(path):
            return default
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _write_json_atomic(path: str, payload: Any) -> None:
    _ensure_data_dir()
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _append_jsonl(path: str, payload: Dict[str, Any]) -> None:
    _ensure_data_dir()
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _file_size(path: str) -> int:
    try:
        return os.path.getsize(path)
    except Exception:
        return 0


def _read_jsonl_incremental(path: str, offset: int, max_events: int) -> Tuple[List[Dict[str, Any]], int, bool]:
    """
    Lê JSONL a partir de um offset em bytes.
    Retorna: eventos, novo_offset, truncated.
    Não carrega arquivo inteiro na memória.
    """
    events: List[Dict[str, Any]] = []
    new_offset = offset
    truncated = False

    if not os.path.exists(path):
        return events, 0, False

    size = _file_size(path)
    if offset > size:
        # Arquivo rotacionou ou foi reescrito.
        offset = 0

    try:
        with open(path, "r", encoding="utf-8") as f:
            f.seek(offset)
            while len(events) < max_events:
                line = f.readline()
                if not line:
                    break
                new_offset = f.tell()
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                    if isinstance(item, dict):
                        events.append(item)
                except Exception:
                    continue

            # Se ainda existe conteúdo depois do limite, marca truncado.
            pos = f.tell()
            maybe_more = f.readline()
            truncated = bool(maybe_more)
            if maybe_more:
                new_offset = pos
    except Exception:
        return events, offset, False

    return events, new_offset, truncated


# -----------------------------------------------------------------------------
# Estado e stats
# -----------------------------------------------------------------------------

def _default_state() -> Dict[str, Any]:
    return {
        "ok": True,
        "module": MODULE,
        "version": VERSION,
        "created_at": _now_str(),
        "updated_at": None,
        "offsets": {
            EXECUTIVE_POLICY_TIMELINE_FILE: 0,
            DECISION_LOG_FILE: 0,
            HISTORY_EVENTS_FILE: 0,
        },
        "last_run_at": None,
        "total_events_processed": 0,
        "last_errors": [],
    }


def _load_state() -> Dict[str, Any]:
    state = _read_json(POLICY_LEARNING_STATE_FILE, _default_state())
    if not isinstance(state, dict):
        state = _default_state()
    state.setdefault("offsets", {})
    state.setdefault("total_events_processed", 0)
    state.setdefault("last_errors", [])
    return state


def _default_stats() -> Dict[str, Any]:
    return {
        "ok": True,
        "module": MODULE,
        "version": VERSION,
        "generated_at": _now_str(),
        "policy_count": 0,
        "policies": {},
        "ranking": [],
        "summary": {
            "policies_reliable": 0,
            "policies_observation": 0,
            "policies_bad": 0,
            "avg_efficiency": 0.0,
        },
        "recent_events": [],
    }


def _load_stats() -> Dict[str, Any]:
    stats = _read_json(POLICY_LEARNING_STATS_FILE, _default_stats())
    if not isinstance(stats, dict):
        stats = _default_stats()
    stats.setdefault("policies", {})
    stats.setdefault("ranking", [])
    stats.setdefault("summary", {})
    stats.setdefault("recent_events", [])
    return stats


def _empty_policy(code: str) -> Dict[str, Any]:
    return {
        "code": code,
        "created_at": _now_str(),
        "updated_at": _now_str(),
        "times_triggered": 0,
        "times_released": 0,
        "blocked_trades": 0,
        "allowed_trades": 0,
        "wins": 0,
        "losses": 0,
        "breakevens": 0,
        "runner_count": 0,
        "pnl_saved_pct": 0.0,
        "pnl_lost_pct": 0.0,
        "drawdown_avoided_pct": 0.0,
        "sample": 0,
        "efficiency_score": 0.0,
        "confidence": "AMOSTRA INSUFICIENTE",
        "recommendation": "OBSERVAR",
        "notes": [],
        "last_event_at": None,
    }


def _get_policy(stats: Dict[str, Any], code: str) -> Dict[str, Any]:
    policies = stats.setdefault("policies", {})
    if code not in policies or not isinstance(policies.get(code), dict):
        policies[code] = _empty_policy(code)
    return policies[code]


# -----------------------------------------------------------------------------
# Normalização de eventos
# -----------------------------------------------------------------------------

def _extract_policy_codes(event: Dict[str, Any]) -> List[str]:
    codes: List[str] = []

    # Formatos possíveis.
    for key in ("code", "policy_code", "active_codes"):
        value = event.get(key)
        if isinstance(value, str) and value.strip():
            codes.append(value.strip())
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, str) and item.strip():
                    codes.append(item.strip())

    policy = event.get("policy")
    if isinstance(policy, dict):
        value = policy.get("code") or policy.get("policy_code")
        if isinstance(value, str) and value.strip():
            codes.append(value.strip())

    applied = event.get("applied_policies")
    if isinstance(applied, list):
        for item in applied:
            if isinstance(item, str) and item.strip():
                codes.append(item.strip())
            elif isinstance(item, dict):
                value = item.get("code") or item.get("policy_code")
                if isinstance(value, str) and value.strip():
                    codes.append(value.strip())

    sync = event.get("sync")
    if isinstance(sync, dict):
        active_codes = sync.get("active_codes")
        if isinstance(active_codes, list):
            for item in active_codes:
                if isinstance(item, str) and item.strip():
                    codes.append(item.strip())

    # Remove duplicados preservando ordem.
    seen = set()
    clean: List[str] = []
    for code in codes:
        if code not in seen:
            seen.add(code)
            clean.append(code)
    return clean


def _event_type(event: Dict[str, Any]) -> str:
    raw = (
        event.get("event")
        or event.get("event_type")
        or event.get("type")
        or event.get("action")
        or event.get("decision")
        or "UNKNOWN"
    )
    return str(raw).upper()


def _extract_pnl_pct(event: Dict[str, Any]) -> float:
    for key in ("pnl_pct", "pnl", "realized_pnl_pct", "result_pct", "pnl_total_pct"):
        if key in event:
            return _safe_float(event.get(key), 0.0)

    payload = event.get("payload")
    if isinstance(payload, dict):
        for key in ("pnl_pct", "pnl", "realized_pnl_pct", "result_pct", "pnl_total_pct"):
            if key in payload:
                return _safe_float(payload.get(key), 0.0)

    return 0.0


def _extract_r_multiple(event: Dict[str, Any]) -> float:
    for key in ("r", "r_multiple", "r_result", "result_r"):
        if key in event:
            return _safe_float(event.get(key), 0.0)
    payload = event.get("payload")
    if isinstance(payload, dict):
        for key in ("r", "r_multiple", "r_result", "result_r"):
            if key in payload:
                return _safe_float(payload.get(key), 0.0)
    return 0.0


def _is_release_event(event: Dict[str, Any]) -> bool:
    etype = _event_type(event)
    text = json.dumps(event, ensure_ascii=False).upper()
    return "RELEASE" in etype or "AUTO_RELEASE" in etype or "LIBER" in text


def _is_block_event(event: Dict[str, Any]) -> bool:
    etype = _event_type(event)
    decision = str(event.get("decision", "")).upper()
    text = json.dumps(event, ensure_ascii=False).upper()
    return (
        "BLOCK" in etype
        or "DENY" in etype
        or decision in {"BLOCK", "DENY", "REJECT"}
        or "BLOQUE" in text
    )


def _is_allow_event(event: Dict[str, Any]) -> bool:
    etype = _event_type(event)
    decision = str(event.get("decision", "")).upper()
    return "ALLOW" in etype or decision == "ALLOW"


def _is_closed_trade_event(event: Dict[str, Any]) -> bool:
    etype = _event_type(event)
    return any(x in etype for x in ("TRADE_CLOSED", "CLOSE", "CLOSED", "OUTCOME"))


# -----------------------------------------------------------------------------
# Aprendizado
# -----------------------------------------------------------------------------

def _apply_event_to_policy(policy: Dict[str, Any], event: Dict[str, Any]) -> Dict[str, Any]:
    now = _now_str()
    policy["updated_at"] = now
    policy["last_event_at"] = event.get("generated_at") or event.get("timestamp") or now

    pnl_pct = _extract_pnl_pct(event)
    r_multiple = _extract_r_multiple(event)

    if _is_release_event(event):
        policy["times_released"] = _safe_int(policy.get("times_released")) + 1
        policy["sample"] = _safe_int(policy.get("sample")) + 1
        return policy

    if _is_block_event(event):
        policy["times_triggered"] = _safe_int(policy.get("times_triggered")) + 1
        policy["blocked_trades"] = _safe_int(policy.get("blocked_trades")) + 1
        policy["sample"] = _safe_int(policy.get("sample")) + 1

        # Quando existe PnL associado a um trade bloqueado simulado:
        # - PnL negativo = perda evitada => pnl_saved positivo.
        # - PnL positivo = lucro perdido => pnl_lost positivo.
        if pnl_pct < 0:
            policy["pnl_saved_pct"] = round(_safe_float(policy.get("pnl_saved_pct")) + abs(pnl_pct), 6)
            policy["losses"] = _safe_int(policy.get("losses")) + 1
        elif pnl_pct > 0:
            policy["pnl_lost_pct"] = round(_safe_float(policy.get("pnl_lost_pct")) + pnl_pct, 6)
            policy["wins"] = _safe_int(policy.get("wins")) + 1
        else:
            policy["breakevens"] = _safe_int(policy.get("breakevens")) + 1

        return policy

    if _is_allow_event(event):
        policy["times_triggered"] = _safe_int(policy.get("times_triggered")) + 1
        policy["allowed_trades"] = _safe_int(policy.get("allowed_trades")) + 1
        policy["sample"] = _safe_int(policy.get("sample")) + 1
        return policy

    if _is_closed_trade_event(event):
        policy["sample"] = _safe_int(policy.get("sample")) + 1
        if pnl_pct > 0:
            policy["wins"] = _safe_int(policy.get("wins")) + 1
        elif pnl_pct < 0:
            policy["losses"] = _safe_int(policy.get("losses")) + 1
        else:
            policy["breakevens"] = _safe_int(policy.get("breakevens")) + 1

        if r_multiple >= 1.0 or pnl_pct >= 3.0:
            policy["runner_count"] = _safe_int(policy.get("runner_count")) + 1

        return policy

    # Evento genérico de policy/timeline.
    policy["times_triggered"] = _safe_int(policy.get("times_triggered")) + 1
    policy["sample"] = _safe_int(policy.get("sample")) + 1
    return policy


def _score_policy(policy: Dict[str, Any]) -> Dict[str, Any]:
    sample = _safe_int(policy.get("sample"))
    blocked = max(1, _safe_int(policy.get("blocked_trades")))
    pnl_saved = _safe_float(policy.get("pnl_saved_pct"))
    pnl_lost = _safe_float(policy.get("pnl_lost_pct"))
    losses = _safe_int(policy.get("losses"))
    wins = _safe_int(policy.get("wins"))
    breakevens = _safe_int(policy.get("breakevens"))
    runners = _safe_int(policy.get("runner_count"))

    protection_ratio = pnl_saved / max(0.0001, pnl_saved + pnl_lost)
    avoided_loss_rate = losses / max(1, wins + losses + breakevens)
    runner_penalty = min(0.25, runners / max(1, sample))
    sample_factor = min(1.0, sample / max(1, MIN_SAMPLE_FOR_CONFIDENCE))

    # Score conservador: prioriza proteção, mas penaliza lucro perdido.
    raw_score = (
        protection_ratio * 45.0
        + avoided_loss_rate * 25.0
        + sample_factor * 20.0
        + min(1.0, pnl_saved / max(1.0, blocked)) * 10.0
        - runner_penalty * 20.0
    )

    score = max(0.0, min(100.0, round(raw_score, 2)))
    policy["efficiency_score"] = score

    if sample < MIN_SAMPLE_FOR_CONFIDENCE:
        policy["confidence"] = "AMOSTRA INSUFICIENTE"
        policy["recommendation"] = "OBSERVAR"
    elif score >= 80:
        policy["confidence"] = "ALTA"
        policy["recommendation"] = "MANTER"
    elif score >= 60:
        policy["confidence"] = "BOA"
        policy["recommendation"] = "MANTER_COM_MONITORAMENTO"
    elif score >= 40:
        policy["confidence"] = "MÉDIA"
        policy["recommendation"] = "REDUZIR_SEVERIDADE"
    else:
        policy["confidence"] = "BAIXA"
        policy["recommendation"] = "REVISAR_OU_DESCONTINUAR"

    notes: List[str] = []
    if pnl_lost > pnl_saved and sample >= MIN_SAMPLE_FOR_CONFIDENCE:
        notes.append("Lucro perdido maior que PnL salvo; revisar severidade da política.")
    if pnl_saved > pnl_lost and sample >= MIN_SAMPLE_FOR_CONFIDENCE:
        notes.append("Política historicamente protetiva: PnL salvo maior que lucro perdido.")
    if sample < MIN_SAMPLE_FOR_CONFIDENCE:
        notes.append("Amostra ainda insuficiente para decisão estatística forte.")

    policy["notes"] = notes[:5]
    return policy


def _rebuild_summary(stats: Dict[str, Any]) -> Dict[str, Any]:
    policies = stats.get("policies", {})
    ranking: List[Dict[str, Any]] = []

    reliable = 0
    observation = 0
    bad = 0
    score_sum = 0.0
    count = 0

    for code, policy in policies.items():
        if not isinstance(policy, dict):
            continue
        scored = _score_policy(policy)
        score = _safe_float(scored.get("efficiency_score"))
        rec = str(scored.get("recommendation", ""))
        conf = str(scored.get("confidence", ""))

        if conf != "AMOSTRA INSUFICIENTE":
            score_sum += score
            count += 1

        if rec in {"MANTER", "MANTER_COM_MONITORAMENTO"} and conf != "AMOSTRA INSUFICIENTE":
            reliable += 1
        elif rec in {"REVISAR_OU_DESCONTINUAR", "REDUZIR_SEVERIDADE"} and conf != "AMOSTRA INSUFICIENTE":
            bad += 1
        else:
            observation += 1

        ranking.append({
            "code": code,
            "efficiency_score": score,
            "confidence": conf,
            "recommendation": rec,
            "sample": _safe_int(scored.get("sample")),
            "pnl_saved_pct": _safe_float(scored.get("pnl_saved_pct")),
            "pnl_lost_pct": _safe_float(scored.get("pnl_lost_pct")),
        })

    ranking.sort(key=lambda x: (x.get("efficiency_score", 0), x.get("sample", 0)), reverse=True)

    stats["policy_count"] = len(policies)
    stats["ranking"] = ranking
    stats["summary"] = {
        "policies_reliable": reliable,
        "policies_observation": observation,
        "policies_bad": bad,
        "avg_efficiency": round(score_sum / count, 2) if count else 0.0,
    }
    stats["generated_at"] = _now_str()
    stats["ok"] = True
    stats["module"] = MODULE
    stats["version"] = VERSION
    return stats


def ingest_policy_event(event: Dict[str, Any], source: str = "manual") -> Dict[str, Any]:
    """
    API simples para outros módulos chamarem diretamente.
    Exemplo:
        executive_policy_learning.ingest_policy_event(payload, source="outcome_evaluator")
    """
    stats = _load_stats()
    codes = _extract_policy_codes(event)

    if not codes:
        return {
            "ok": False,
            "module": MODULE,
            "version": VERSION,
            "reason": "no_policy_code_found",
            "generated_at": _now_str(),
        }

    applied = []
    for code in codes:
        policy = _get_policy(stats, code)
        _apply_event_to_policy(policy, event)
        applied.append(code)

    event_record = {
        "generated_at": _now_str(),
        "source": source,
        "codes": applied,
        "event_type": _event_type(event),
        "pnl_pct": _extract_pnl_pct(event),
    }
    _append_jsonl(POLICY_LEARNING_EVENTS_FILE, event_record)

    recent = stats.setdefault("recent_events", [])
    recent.insert(0, event_record)
    stats["recent_events"] = recent[:MAX_RECENT_EVENTS]

    stats = _rebuild_summary(stats)
    _write_json_atomic(POLICY_LEARNING_STATS_FILE, stats)

    return {
        "ok": True,
        "module": MODULE,
        "version": VERSION,
        "generated_at": _now_str(),
        "applied_codes": applied,
        "policy_count": stats.get("policy_count", 0),
    }


def run_policy_learning(max_events_per_run: Optional[int] = None) -> Dict[str, Any]:
    """
    Varredura incremental das fontes conhecidas.
    Projetada para rodar em /health, /policylearning ou scheduler sem estourar memória.
    """
    max_events = max_events_per_run or MAX_EVENTS_PER_RUN
    state = _load_state()
    stats = _load_stats()
    errors: List[str] = []
    processed = 0
    truncated_sources: List[str] = []

    sources = [
        EXECUTIVE_POLICY_TIMELINE_FILE,
        DECISION_LOG_FILE,
        HISTORY_EVENTS_FILE,
    ]

    for source_path in sources:
        if processed >= max_events:
            break

        remaining = max(1, max_events - processed)
        offset = _safe_int(state.get("offsets", {}).get(source_path, 0))
        events, new_offset, truncated = _read_jsonl_incremental(source_path, offset, remaining)
        state.setdefault("offsets", {})[source_path] = new_offset

        if truncated:
            truncated_sources.append(source_path)

        for event in events:
            try:
                codes = _extract_policy_codes(event)
                if not codes:
                    continue

                for code in codes:
                    policy = _get_policy(stats, code)
                    _apply_event_to_policy(policy, event)

                record = {
                    "generated_at": _now_str(),
                    "source": source_path,
                    "codes": codes,
                    "event_type": _event_type(event),
                    "pnl_pct": _extract_pnl_pct(event),
                }
                _append_jsonl(POLICY_LEARNING_EVENTS_FILE, record)

                recent = stats.setdefault("recent_events", [])
                recent.insert(0, record)
                stats["recent_events"] = recent[:MAX_RECENT_EVENTS]

                processed += 1
            except Exception as exc:
                errors.append(f"{source_path}: {exc}")

    stats = _rebuild_summary(stats)
    _write_json_atomic(POLICY_LEARNING_STATS_FILE, stats)

    state["updated_at"] = _now_str()
    state["last_run_at"] = _now_str()
    state["total_events_processed"] = _safe_int(state.get("total_events_processed")) + processed
    state["last_errors"] = errors[-10:]
    _write_json_atomic(POLICY_LEARNING_STATE_FILE, state)

    return {
        "ok": True,
        "module": MODULE,
        "version": VERSION,
        "generated_at": _now_str(),
        "processed_now": processed,
        "total_events_processed": state.get("total_events_processed", 0),
        "policy_count": stats.get("policy_count", 0),
        "summary": stats.get("summary", {}),
        "truncated_sources": truncated_sources,
        "errors": errors[-10:],
        "files": {
            "state": POLICY_LEARNING_STATE_FILE,
            "stats": POLICY_LEARNING_STATS_FILE,
            "events": POLICY_LEARNING_EVENTS_FILE,
        },
        "notes": [
            "Leitura incremental por offset para reduzir consumo de memória.",
            "V1 não executa trades e não altera políticas; apenas aprende e recomenda.",
            "Se truncated_sources vier preenchido, rode novamente para processar o restante aos poucos.",
        ],
    }


# -----------------------------------------------------------------------------
# Relatórios / comandos
# -----------------------------------------------------------------------------

def get_policy_learning_stats() -> Dict[str, Any]:
    stats = _load_stats()
    return _rebuild_summary(stats)


def get_policy_history(code: str) -> Dict[str, Any]:
    stats = get_policy_learning_stats()
    policy = stats.get("policies", {}).get(code)
    if not policy:
        return {
            "ok": False,
            "module": MODULE,
            "version": VERSION,
            "generated_at": _now_str(),
            "reason": "policy_not_found",
            "code": code,
        }
    return {
        "ok": True,
        "module": MODULE,
        "version": VERSION,
        "generated_at": _now_str(),
        "policy": policy,
    }


def build_policy_learning_report(limit: int = 10) -> str:
    result = run_policy_learning()
    stats = get_policy_learning_stats()
    summary = stats.get("summary", {})
    ranking = stats.get("ranking", [])[:limit]

    lines: List[str] = []
    lines.append("🧠 EXECUTIVE POLICY LEARNING — CENTRAL QUANT")
    lines.append(f"Data/hora: {_now_str()}")
    lines.append(f"Status: {'✅' if result.get('ok') else '⚠️'}")
    lines.append(f"Versão: {VERSION}")
    lines.append("")
    lines.append("Resumo:")
    lines.append(f"- Eventos processados agora: {result.get('processed_now', 0)}")
    lines.append(f"- Policies avaliadas: {stats.get('policy_count', 0)}")
    lines.append(f"- Policies confiáveis: {summary.get('policies_reliable', 0)}")
    lines.append(f"- Policies em observação: {summary.get('policies_observation', 0)}")
    lines.append(f"- Policies ruins/revisar: {summary.get('policies_bad', 0)}")
    lines.append(f"- Eficiência média: {summary.get('avg_efficiency', 0.0)}%")
    lines.append("")

    if ranking:
        lines.append("Ranking:")
        for idx, item in enumerate(ranking, start=1):
            lines.append(
                f"{idx}. {item.get('code')} | score={item.get('efficiency_score')} | "
                f"confiança={item.get('confidence')} | recomendação={item.get('recommendation')} | "
                f"amostra={item.get('sample')} | salvo={item.get('pnl_saved_pct')}% | perdido={item.get('pnl_lost_pct')}%"
            )
    else:
        lines.append("Ranking: ainda sem policies avaliadas.")

    truncated = result.get("truncated_sources") or []
    if truncated:
        lines.append("")
        lines.append("Observação:")
        lines.append("- Ainda há eventos antigos para processar. Rode /policylearning novamente para continuar incrementalmente.")

    errors = result.get("errors") or []
    if errors:
        lines.append("")
        lines.append("Erros recentes:")
        for err in errors[:5]:
            lines.append(f"- {err}")

    return "\n".join(lines)


def build_policy_ranking_report(limit: int = 20) -> str:
    stats = get_policy_learning_stats()
    ranking = stats.get("ranking", [])[:limit]

    lines = [
        "🏆 POLICY RANKING — CENTRAL QUANT",
        f"Data/hora: {_now_str()}",
        f"Versão: {VERSION}",
        "",
    ]

    if not ranking:
        lines.append("Ainda não há policies avaliadas.")
        return "\n".join(lines)

    for idx, item in enumerate(ranking, start=1):
        lines.append(
            f"{idx}. {item.get('code')} — score={item.get('efficiency_score')} | "
            f"{item.get('recommendation')} | confiança={item.get('confidence')} | amostra={item.get('sample')}"
        )

    return "\n".join(lines)


def build_policy_history_report(code: str) -> str:
    result = get_policy_history(code)
    lines = [
        f"📚 POLICY HISTORY — {code}",
        f"Data/hora: {_now_str()}",
        f"Versão: {VERSION}",
        "",
    ]

    if not result.get("ok"):
        lines.append("Policy não encontrada no learning ainda.")
        return "\n".join(lines)

    p = result.get("policy", {})
    lines.extend([
        f"Score: {p.get('efficiency_score')}%",
        f"Confiança: {p.get('confidence')}",
        f"Recomendação: {p.get('recommendation')}",
        "",
        f"Amostra: {p.get('sample')}",
        f"Acionamentos: {p.get('times_triggered')}",
        f"Releases: {p.get('times_released')}",
        f"Trades bloqueados: {p.get('blocked_trades')}",
        f"Trades permitidos: {p.get('allowed_trades')}",
        "",
        f"Wins: {p.get('wins')}",
        f"Losses evitados/associados: {p.get('losses')}",
        f"Breakevens: {p.get('breakevens')}",
        f"Runners: {p.get('runner_count')}",
        "",
        f"PnL salvo estimado: {p.get('pnl_saved_pct')}%",
        f"Lucro perdido estimado: {p.get('pnl_lost_pct')}%",
    ])

    notes = p.get("notes") or []
    if notes:
        lines.append("")
        lines.append("Notas:")
        for note in notes:
            lines.append(f"- {note}")

    return "\n".join(lines)


def health() -> Dict[str, Any]:
    state = _load_state()
    stats = get_policy_learning_stats()
    return {
        "ok": True,
        "loaded": True,
        "module": MODULE,
        "version": VERSION,
        "generated_at": _now_str(),
        "policy_count": stats.get("policy_count", 0),
        "summary": stats.get("summary", {}),
        "last_run_at": state.get("last_run_at"),
        "total_events_processed": state.get("total_events_processed", 0),
        "files": {
            "state": POLICY_LEARNING_STATE_FILE,
            "stats": POLICY_LEARNING_STATS_FILE,
            "events": POLICY_LEARNING_EVENTS_FILE,
        },
        "notes": [
            "Executive Policy Learning V1 carregado.",
            "Módulo somente observacional: não executa trades e não altera políticas automaticamente.",
            "Leitura incremental para evitar pico de memória no Render.",
        ],
    }


# Aliases úteis para integração com main.py
build_report = build_policy_learning_report
build_stats_report = build_policy_learning_report
build_ranking_report = build_policy_ranking_report
