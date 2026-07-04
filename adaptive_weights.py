# adaptive_weights.py
# CENTRAL QUANT — ADAPTIVE WEIGHTS V1
# Versão: 2026-07-04-ADAPTIVE-WEIGHTS-V1
#
# Objetivo:
# - Ler estatísticas do Outcome Evaluator.
# - Transformar performance PAPER em ajustes de confiança por bot/setup.
# - Ainda NÃO altera execução real, lote ou risco.
# - Gera recomendações: BOOST, KEEP, REDUCE, PAUSE_SAMPLE.
#
# Arquivo:
#   /opt/render/project/src/adaptive_weights.py

import os
import json
from pathlib import Path
from datetime import datetime
from typing import Any, Dict


VERSION = "2026-07-04-ADAPTIVE-WEIGHTS-V1"

DATA_DIR = Path(os.getenv("CENTRAL_DATA_DIR", "/opt/render/project/src/data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

OUTCOME_STATS_FILE = DATA_DIR / "outcome_stats.json"
ADAPTIVE_WEIGHTS_FILE = DATA_DIR / "adaptive_weights.json"
ADAPTIVE_WEIGHTS_LOG_FILE = DATA_DIR / "adaptive_weights_log.jsonl"

ADAPTIVE_WEIGHTS_ENABLED = os.getenv("CENTRAL_ADAPTIVE_WEIGHTS_ENABLED", "true").lower() == "true"

MIN_TRADES_FOR_CONFIDENCE = int(os.getenv("ADAPTIVE_WEIGHTS_MIN_TRADES", "10"))
MIN_TRADES_FOR_ACTION = int(os.getenv("ADAPTIVE_WEIGHTS_MIN_ACTION_TRADES", "20"))


def _now_br() -> str:
    return datetime.now().strftime("%d/%m/%Y %H:%M:%S")


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _append_jsonl(path: Path, payload: Dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


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


def _score_bucket(stats: Dict[str, Any]) -> Dict[str, Any]:
    trades = _safe_int(stats.get("trades"))
    win_rate = _safe_float(stats.get("win_rate_pct"))
    tp50_rate = _safe_float(stats.get("tp50_hit_rate_pct"))
    pnl_avg = _safe_float(stats.get("pnl_avg_pct"))
    r_avg = _safe_float(stats.get("r_avg"))
    pnl_total = _safe_float(stats.get("pnl_total_pct"))
    r_total = _safe_float(stats.get("r_total"))

    sample_score = min(100.0, round((trades / max(1, MIN_TRADES_FOR_CONFIDENCE)) * 100, 2))

    performance_score = 50.0
    performance_score += max(-25, min(25, r_avg * 20))
    performance_score += max(-15, min(15, pnl_avg * 3))
    performance_score += max(-10, min(10, (win_rate - 50) / 2))
    performance_score += max(-10, min(10, (tp50_rate - 50) / 3))
    performance_score = round(max(0.0, min(100.0, performance_score)), 2)

    confidence = round((sample_score * 0.45) + (performance_score * 0.55), 2)

    if trades < MIN_TRADES_FOR_CONFIDENCE:
        action = "WAIT_SAMPLE"
        weight = 1.0
        reason = f"Amostra insuficiente: {trades}/{MIN_TRADES_FOR_CONFIDENCE} trades."
    elif trades < MIN_TRADES_FOR_ACTION:
        if r_avg > 0 and pnl_avg > 0:
            action = "KEEP_POSITIVE_SAMPLE"
            weight = 1.05
            reason = "Amostra ainda moderada, mas performance positiva."
        else:
            action = "OBSERVE"
            weight = 0.95
            reason = "Amostra moderada sem vantagem clara."
    else:
        if r_avg >= 0.5 and pnl_avg > 0 and win_rate >= 50:
            action = "BOOST"
            weight = 1.15
            reason = "Performance consistente com R médio positivo e win rate saudável."
        elif r_avg > 0 and pnl_avg > 0:
            action = "KEEP"
            weight = 1.0
            reason = "Performance positiva, sem necessidade de boost agressivo."
        elif r_avg <= -0.25 or pnl_avg < 0:
            action = "REDUCE"
            weight = 0.75
            reason = "Performance negativa ou R médio fraco."
        else:
            action = "OBSERVE"
            weight = 0.9
            reason = "Performance neutra ou inconclusiva."

    return {
        "trades": trades,
        "win_rate_pct": win_rate,
        "tp50_hit_rate_pct": tp50_rate,
        "pnl_avg_pct": pnl_avg,
        "pnl_total_pct": pnl_total,
        "r_avg": r_avg,
        "r_total": r_total,
        "sample_score": sample_score,
        "performance_score": performance_score,
        "confidence": confidence,
        "recommended_action": action,
        "suggested_weight": round(weight, 4),
        "reason": reason,
    }


def adaptive_weights_health() -> Dict[str, Any]:
    outcome = _read_json(OUTCOME_STATS_FILE, {})
    weights = _read_json(ADAPTIVE_WEIGHTS_FILE, {})

    return {
        "ok": True,
        "module": "adaptive_weights",
        "loaded": True,
        "version": VERSION,
        "generated_at": _now_br(),
        "enabled": ADAPTIVE_WEIGHTS_ENABLED,
        "outcome_stats_exists": OUTCOME_STATS_FILE.exists(),
        "weights_exists": ADAPTIVE_WEIGHTS_FILE.exists(),
        "outcome_updated_at": outcome.get("updated_at"),
        "weights_updated_at": weights.get("updated_at"),
        "min_trades_for_confidence": MIN_TRADES_FOR_CONFIDENCE,
        "min_trades_for_action": MIN_TRADES_FOR_ACTION,
        "files": {
            "outcome_stats": str(OUTCOME_STATS_FILE),
            "adaptive_weights": str(ADAPTIVE_WEIGHTS_FILE),
            "adaptive_weights_log": str(ADAPTIVE_WEIGHTS_LOG_FILE),
        },
        "notes": [
            "Adaptive Weights V1 é advisory/observacional.",
            "Não altera lote, risco ou execução real.",
            "Usa Outcome Evaluator como fonte estatística.",
        ],
    }


def build_adaptive_weights(commit: bool = True) -> Dict[str, Any]:
    if not ADAPTIVE_WEIGHTS_ENABLED:
        return {
            "ok": False,
            "status": "ADAPTIVE_WEIGHTS_DISABLED",
            "version": VERSION,
            "generated_at": _now_br(),
        }

    outcome = _read_json(OUTCOME_STATS_FILE, {})
    result = {
        "ok": True,
        "status": "ADAPTIVE_WEIGHTS_BUILT",
        "version": VERSION,
        "generated_at": _now_br(),
        "source_outcome_updated_at": outcome.get("updated_at"),
        "mode": "ADVISORY_ONLY",
        "global": _score_bucket(outcome.get("global") or {}),
        "by_bot": {},
        "by_setup": {},
        "by_symbol": {},
        "by_side": {},
        "policy": {
            "does_not_change_real_execution": True,
            "does_not_change_position_size": True,
            "does_not_change_risk": True,
            "requires_human_review": True,
            "min_trades_for_confidence": MIN_TRADES_FOR_CONFIDENCE,
            "min_trades_for_action": MIN_TRADES_FOR_ACTION,
        },
        "notes": [
            "Pesos são apenas recomendação.",
            "Amostras pequenas ficam em WAIT_SAMPLE.",
            "Futura integração poderá alimentar score/risk/capital allocator.",
        ],
    }

    for group_name in ["by_bot", "by_setup", "by_symbol", "by_side"]:
        group = outcome.get(group_name) or {}
        if isinstance(group, dict):
            for key, stats in group.items():
                if isinstance(stats, dict):
                    result[group_name][str(key)] = _score_bucket(stats)

    if commit:
        result["updated_at"] = _now_br()
        _write_json(ADAPTIVE_WEIGHTS_FILE, result)
        _append_jsonl(ADAPTIVE_WEIGHTS_LOG_FILE, {
            "event": "ADAPTIVE_WEIGHTS_BUILT",
            "version": VERSION,
            "generated_at": _now_br(),
            "result": result,
        })

    return result


def get_adaptive_weights() -> Dict[str, Any]:
    weights = _read_json(ADAPTIVE_WEIGHTS_FILE, None)
    if weights is None:
        weights = build_adaptive_weights(commit=False)

    return {
        "ok": True,
        "generated_at": _now_br(),
        "weights": weights,
    }


def read_adaptive_weights_log(limit: int = 20) -> Dict[str, Any]:
    if not ADAPTIVE_WEIGHTS_LOG_FILE.exists():
        return {
            "ok": True,
            "generated_at": _now_br(),
            "count": 0,
            "items": [],
        }

    lines = ADAPTIVE_WEIGHTS_LOG_FILE.read_text(encoding="utf-8").splitlines()
    selected = lines[-max(1, int(limit)):]

    items = []
    for line in selected:
        try:
            items.append(json.loads(line))
        except Exception:
            continue

    return {
        "ok": True,
        "generated_at": _now_br(),
        "count": len(items),
        "items": items,
    }


def build_adaptive_weights_text() -> str:
    data = get_adaptive_weights().get("weights") or {}

    lines = [
        "🧠 ADAPTIVE WEIGHTS — CENTRAL QUANT",
        f"Data/hora: {_now_br()}",
        f"Versão: {VERSION}",
        "",
        "Status:",
        f"- Modo: {data.get('mode')}",
        f"- Fonte outcome: {data.get('source_outcome_updated_at')}",
        "",
        "Global:",
    ]

    g = data.get("global") or {}
    lines += [
        f"- Trades: {g.get('trades')}",
        f"- Win rate: {g.get('win_rate_pct')}%",
        f"- TP50 hit rate: {g.get('tp50_hit_rate_pct')}%",
        f"- PnL médio: {g.get('pnl_avg_pct')}%",
        f"- R médio: {g.get('r_avg')}",
        f"- Confiança: {g.get('confidence')}/100",
        f"- Ação: {g.get('recommended_action')}",
        f"- Peso sugerido: {g.get('suggested_weight')}",
        f"- Motivo: {g.get('reason')}",
        "",
        "Por bot:",
    ]

    by_bot = data.get("by_bot") or {}
    if not by_bot:
        lines.append("- Sem dados por bot.")
    else:
        for bot, item in sorted(by_bot.items()):
            lines.append(
                f"- {bot}: trades={item.get('trades')} | "
                f"conf={item.get('confidence')} | "
                f"ação={item.get('recommended_action')} | "
                f"peso={item.get('suggested_weight')} | "
                f"Ravg={item.get('r_avg')}"
            )

    lines += [
        "",
        "Observação:",
        "V1 é apenas advisory. Ainda não altera lote, risco ou execução.",
    ]

    return "\n".join(lines)
