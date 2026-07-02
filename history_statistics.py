from collections import defaultdict
import history_manager


def _safe_float(value, default=0.0):
    try:
        if value is None:
            return default
        if isinstance(value, str):
            value = value.replace("%", "").replace(",", ".").strip()
        return float(value)
    except Exception:
        return default


def load_events():
    return history_manager.load_events()


def get_closed_trades(events=None):
    rows = events if events is not None else load_events()
    closed = []

    for event in rows or []:
        event_name = history_manager.normalize_event_type(
            event.get("event") or event.get("event_type") or event.get("type"),
            event,
        )
        if event_name == "TRADE_CLOSED":
            closed.append(event)

    return closed


def calculate_stats(trades):
    trades = list(trades or [])

    total = len(trades)
    wins = 0
    losses = 0
    breakeven = 0

    pnl_values = []
    win_values = []
    loss_values = []

    for trade in trades:
        pnl = _safe_float(
            trade.get("result_pct")
            or trade.get("pnl_pct")
            or trade.get("pnl")
            or 0
        )

        pnl_values.append(pnl)

        if pnl > 0:
            wins += 1
            win_values.append(pnl)
        elif pnl < 0:
            losses += 1
            loss_values.append(abs(pnl))
        else:
            breakeven += 1

    gross_win = sum(win_values)
    gross_loss = sum(loss_values)

    win_rate = round((wins / total) * 100, 2) if total else 0.0
    pnl_total = round(sum(pnl_values), 4)
    pnl_avg = round(pnl_total / total, 4) if total else 0.0

    avg_win = round(gross_win / len(win_values), 4) if win_values else 0.0
    avg_loss = round(gross_loss / len(loss_values), 4) if loss_values else 0.0

    profit_factor = round(gross_win / gross_loss, 4) if gross_loss else (999 if gross_win > 0 else 0.0)
    expectancy = round((win_rate / 100) * avg_win - ((100 - win_rate) / 100) * avg_loss, 4) if total else 0.0

    return {
        "trades": total,
        "wins": wins,
        "losses": losses,
        "breakeven": breakeven,
        "win_rate_pct": win_rate,
        "pnl_total_pct": pnl_total,
        "pnl_avg_pct": pnl_avg,
        "avg_win_pct": avg_win,
        "avg_loss_pct": avg_loss,
        "profit_factor_pct": profit_factor,
        "expectancy_pct": expectancy,
    }


def _group_stats(trades, field):
    buckets = defaultdict(list)

    for trade in trades:
        key = str(trade.get(field) or "N/A").upper()
        buckets[key].append(trade)

    result = {}
    for key, rows in buckets.items():
        result[key] = calculate_stats(rows)

    return dict(sorted(
        result.items(),
        key=lambda item: (
            -item[1].get("expectancy_pct", 0),
            -item[1].get("profit_factor_pct", 0),
            -item[1].get("pnl_total_pct", 0),
            -item[1].get("trades", 0),
        )
    ))


def build_statistics():
    events = load_events()
    closed = get_closed_trades(events)

    return {
        "ok": True,
        "generated_at": history_manager.data_hora_sp_str(),
        "events_total": len(events),
        "closed_trades": len(closed),
        "overall": calculate_stats(closed),
        "by_bot": _group_stats(closed, "bot"),
        "by_symbol": _group_stats(closed, "symbol"),
        "by_setup": _group_stats(closed, "setup"),
        "by_side": _group_stats(closed, "side"),
    }