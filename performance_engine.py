from collections import defaultdict
import history_manager
import rating_engine


# Eventos administrativos que podem aparecer no Super History,
# mas não devem entrar em performance, rankings ou recomendações.
ADMIN_EVENTS = {
    "CENTRAL_COMMAND",
    "BOT_COMMAND",
    "MEMORY",
    "HEALTH",
    "BOT_STATUS",
    "CENTRAL_STATUS",
    "WATCHDOG",
    "STARTUP",
    "RISK_SNAPSHOT",
}


def _safe_float(value, default=None):
    try:
        if value is None:
            return default
        if isinstance(value, str):
            value = value.replace("%", "").replace(",", ".").strip()
        return float(value)
    except Exception:
        return default


def _event_name(event):
    return history_manager.normalize_event_type(
        event.get("event") or event.get("event_type") or event.get("type"),
        event,
    )


def _is_admin_event(event):
    return _event_name(event) in ADMIN_EVENTS


def _event_pnl(event):
    raw = event.get("raw") if isinstance(event.get("raw"), dict) else {}
    return (
        _safe_float(event.get("result_pct"), None)
        or _safe_float(event.get("pnl_pct"), None)
        or _safe_float(event.get("pnl"), None)
        or _safe_float(raw.get("result_pct"), None)
        or _safe_float(raw.get("pnl_pct"), None)
        or _safe_float(raw.get("pnl"), None)
    )


def _metric_from_event(event, names):
    raw = event.get("raw") if isinstance(event.get("raw"), dict) else {}
    for name in names:
        value = _safe_float(event.get(name), None)
        if value is not None:
            return value
        value = _safe_float(raw.get(name), None)
        if value is not None:
            return value
    return None


def calculate_metrics(events):
    closed = []

    for event in events or []:
        if _is_admin_event(event):
            continue

        event_name = _event_name(event)
        if event_name != "TRADE_CLOSED":
            continue

        pnl = _event_pnl(event)
        if pnl is None:
            continue

        closed.append({
            "pnl": pnl,
            "r": _metric_from_event(event, ["result_r", "pnl_r"]),
            "mfe": _metric_from_event(event, ["mfe_pct", "mfe_max_pct"]),
            "mae": _metric_from_event(event, ["mae_pct", "mae_min_pct"]),
            "giveback": _metric_from_event(event, ["giveback_pct", "mfe_gave_back_pct"]),
        })

    trades = len(closed)
    wins = sum(1 for x in closed if x["pnl"] > 0)
    losses = sum(1 for x in closed if x["pnl"] < 0)
    breakeven = sum(1 for x in closed if x["pnl"] == 0)

    pnl_values = [x["pnl"] for x in closed]
    win_values = [x["pnl"] for x in closed if x["pnl"] > 0]
    loss_values = [abs(x["pnl"]) for x in closed if x["pnl"] < 0]

    gross_win = sum(win_values)
    gross_loss = sum(loss_values)

    avg_win = round(gross_win / len(win_values), 4) if win_values else 0.0
    avg_loss = round(gross_loss / len(loss_values), 4) if loss_values else 0.0

    win_rate = round((wins / trades) * 100, 2) if trades else 0.0
    payoff = round(avg_win / avg_loss, 4) if avg_loss else 0.0
    profit_factor = round(gross_win / gross_loss, 4) if gross_loss else (999 if gross_win > 0 else 0.0)
    expectancy = round((win_rate / 100) * avg_win - ((100 - win_rate) / 100) * avg_loss, 4) if trades else 0.0

    max_win_streak = 0
    max_loss_streak = 0
    cur_win = 0
    cur_loss = 0

    for item in closed:
        pnl = item["pnl"]
        if pnl > 0:
            cur_win += 1
            cur_loss = 0
        elif pnl < 0:
            cur_loss += 1
            cur_win = 0
        else:
            cur_win = 0
            cur_loss = 0

        max_win_streak = max(max_win_streak, cur_win)
        max_loss_streak = max(max_loss_streak, cur_loss)

    def avg_field(name):
        values = [x[name] for x in closed if x.get(name) is not None]
        return round(sum(values) / len(values), 4) if values else 0.0

    return {
        "trades": trades,
        "wins": wins,
        "losses": losses,
        "breakeven": breakeven,
        "win_rate_pct": win_rate,
        "pnl_total_pct": round(sum(pnl_values), 4),
        "pnl_avg_pct": round(sum(pnl_values) / trades, 4) if trades else 0.0,
        "avg_win_pct": avg_win,
        "avg_loss_pct": avg_loss,
        "payoff_ratio": payoff,
        "profit_factor_pct": profit_factor,
        "expectancy_pct": expectancy,
        "max_win_streak": max_win_streak,
        "max_loss_streak": max_loss_streak,
        "avg_r": avg_field("r"),
        "avg_mfe_pct": avg_field("mfe"),
        "avg_mae_pct": avg_field("mae"),
        "avg_giveback_pct": avg_field("giveback"),
    }


def _group_key(event, group_by):
    if group_by == "setup":
        return str(event.get("setup") or "").upper().strip()
    if group_by == "symbol":
        return str(event.get("symbol") or "").upper().strip()
    return str(event.get("bot") or "").upper().strip()


def _has_operational_value(stats, metrics):
    """Evita grupos vazios, N/A e itens apenas administrativos."""
    return any([
        int(stats.get("total_events") or 0) > 0,
        int(stats.get("signals") or 0) > 0,
        int(stats.get("entries") or 0) > 0,
        int(stats.get("closed") or 0) > 0,
        int(stats.get("tp50") or 0) > 0,
        int(stats.get("blocked") or 0) > 0,
        int(metrics.get("trades") or 0) > 0,
    ])


def build_performance_payload(days=None, group_by="bot"):
    if group_by not in {"bot", "setup", "symbol"}:
        group_by = "bot"

    if days:
        result = history_manager.query_history(days=days, limit=None)
        events = result.get("events", [])
    else:
        events = history_manager.load_events()

    buckets = defaultdict(list)
    for event in events:
        if _is_admin_event(event):
            continue

        key = _group_key(event, group_by)
        if not key or key in {"N/A", "NA", "NONE", "NULL"}:
            continue

        buckets[key].append(event)

    items = []
    for key, rows in buckets.items():
        stats = history_manager.calculate_stats(rows=rows)
        metrics = calculate_metrics(rows)

        if not _has_operational_value(stats, metrics):
            continue

        item = {
            group_by: key,
            "total_events": stats.get("total_events", 0),
            "signals": stats.get("signals", 0),
            "entries": stats.get("entries", 0),
            "closed": stats.get("closed", 0),
            "blocked": stats.get("blocked", 0),
            "denied": stats.get("denied", 0),
            "tp50": stats.get("tp50", 0),
            **metrics,
        }
        item.update(rating_engine.rate_item(item))
        items.append(item)

    # Prioriza grupos com trades reais. Depois, expectativa/PF/PnL.
    items.sort(key=lambda x: (
        -int(x.get("trades", 0) or 0),
        -float(x.get("expectancy_pct", 0) or 0),
        -float(x.get("profit_factor_pct", 0) or 0),
        -float(x.get("pnl_total_pct", 0) or 0),
        -int(x.get("total_events", 0) or 0),
    ))

    return {
        "ok": True,
        "generated_at": history_manager.data_hora_sp_str(),
        "filters": {
            "days": int(days) if str(days or "").isdigit() else None,
            "group_by": group_by,
        },
        "items": items,
    }


def _recommendation_for_item(name, metrics):
    trades = int(metrics.get("trades") or 0)
    expectancy = _safe_float(metrics.get("expectancy_pct"), 0.0) or 0.0
    profit_factor = _safe_float(metrics.get("profit_factor_pct"), 0.0) or 0.0
    win_rate = _safe_float(metrics.get("win_rate_pct"), 0.0) or 0.0
    pnl_total = _safe_float(metrics.get("pnl_total_pct"), 0.0) or 0.0
    avg_giveback = _safe_float(metrics.get("avg_giveback_pct"), 0.0) or 0.0

    if trades < 5:
        action = "AGUARDAR_AMOSTRA"
        severity = "INFO"
        reason = "Amostra insuficiente para decisão estatística."
    elif expectancy < 0 and profit_factor < 1:
        action = "PAUSAR_OU_OBSERVAR"
        severity = "ALTA"
        reason = "Expectancy negativa e Profit Factor abaixo de 1."
    elif pnl_total < 0 and win_rate < 35:
        action = "REDUZIR_EXPOSICAO"
        severity = "MEDIA"
        reason = "PnL negativo com baixo win rate."
    elif avg_giveback >= 2.5:
        action = "REVISAR_TRAILING"
        severity = "MEDIA"
        reason = "Devolução média elevada após MFE."
    elif expectancy > 0 and profit_factor > 1.5:
        action = "MANTER_OU_AUMENTAR_GRADUAL"
        severity = "POSITIVA"
        reason = "Expectancy positiva e Profit Factor saudável."
    else:
        action = "MANTER_OBSERVACAO"
        severity = "BAIXA"
        reason = "Sem sinal estatístico forte para ajuste."

    rating = rating_engine.rate_item(metrics)

    return {
        "name": name,
        "action": action,
        "severity": severity,
        "reason": reason,
        "trades": trades,
        "expectancy_pct": expectancy,
        "profit_factor_pct": profit_factor,
        "win_rate_pct": win_rate,
        "pnl_total_pct": pnl_total,
        "avg_giveback_pct": avg_giveback,
        "score_0_100": metrics.get("score_0_100"),
        "rating": metrics.get("rating"),
        "confidence": metrics.get("confidence"),
        "sample_status": metrics.get("sample_status"),
        "risk_bias": metrics.get("risk_bias"),
        **rating,
    }


def build_recommendations_payload(days=None, group_by="setup"):
    payload = build_performance_payload(days=days, group_by=group_by)
    items = payload.get("items", [])

    recommendations = []
    for item in items:
        name = item.get(group_by) or item.get("bot") or item.get("setup") or item.get("symbol") or ""
        name = str(name or "").upper().strip()
        if not name or name in {"N/A", "NA", "NONE", "NULL"}:
            continue
        recommendations.append(_recommendation_for_item(name, item))

    priority = {
        "ALTA": 0,
        "MEDIA": 1,
        "POSITIVA": 2,
        "BAIXA": 3,
        "INFO": 4,
    }

    recommendations.sort(key=lambda item: (
        priority.get(item.get("severity"), 9),
        -int(item.get("trades", 0) or 0),
        item.get("expectancy_pct", 0),
        item.get("profit_factor_pct", 0),
    ))

    return {
        "ok": True,
        "generated_at": history_manager.data_hora_sp_str(),
        "filters": {
            "days": int(days) if str(days or "").isdigit() else None,
            "group_by": group_by,
        },
        "recommendations": recommendations,
    }
