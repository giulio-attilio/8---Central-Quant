# trade_record.py
# CENTRAL QUANT — TRADE RECORD BUILDER
# Versão: 2026-07-03-TRADE-RECORD-V1

def _safe_float(value, default=None):
    try:
        if value is None:
            return default
        if isinstance(value, str):
            value = value.replace("%", "").replace(",", ".").strip()
        return float(value)
    except Exception:
        return default


def _first(*values, default=None):
    for value in values:
        if value is not None and value != "":
            return value
    return default


def build_trade_record(item: dict) -> dict:
    item = item if isinstance(item, dict) else {}
    raw = item.get("raw") if isinstance(item.get("raw"), dict) else {}
    inner = raw.get("raw") if isinstance(raw.get("raw"), dict) else raw
    context = item.get("context") if isinstance(item.get("context"), dict) else raw.get("context", {})

    pnl_pct = _safe_float(
        _first(item.get("result_pct"), item.get("pnl_pct"), raw.get("result_pct"), raw.get("pnl_pct"), inner.get("pnl_pct"), inner.get("pnl"))
    )

    r_multiple = _safe_float(
        _first(item.get("result_r"), raw.get("result_r"), raw.get("pnl_r"), inner.get("pnl_r"), inner.get("r"))
    )

    result_type = _first(
        inner.get("result_type"),
        raw.get("result_type"),
        item.get("result"),
        default=None,
    )

    if not result_type and pnl_pct is not None:
        result_type = "WIN" if pnl_pct > 0 else "LOSS" if pnl_pct < 0 else "BREAKEVEN"

    return {
        "schema": "TRADE_RECORD_V1",
        "event": "TRADE_CLOSED",

        "uid": item.get("uid"),
        "trade_id": item.get("trade_id"),

        "bot": item.get("bot"),
        "setup": item.get("setup"),
        "symbol": item.get("symbol"),
        "side": item.get("side"),

        "entry_time": inner.get("datetime") or raw.get("ts") or item.get("ts"),
        "exit_time": item.get("ts"),

        "entry_price": _safe_float(_first(item.get("entry"), raw.get("entry"), inner.get("entry"))),
        "exit_price": _safe_float(_first(item.get("exit_price"), raw.get("exit_price"), inner.get("exit_price"), inner.get("exit"))),

        "stop": _safe_float(_first(item.get("stop"), raw.get("stop"), raw.get("sl"), inner.get("stop"), inner.get("sl"))),
        "tp50": _safe_float(_first(item.get("tp50"), raw.get("tp50"), inner.get("tp50"))),

        "risk_pct": _safe_float(_first(item.get("risk_pct"), raw.get("risk_pct"), inner.get("risk_pct"))),
        "score": _safe_float(_first(item.get("score"), raw.get("score"), inner.get("score"))),
        "quality": _first(item.get("quality"), raw.get("quality"), inner.get("quality")),

        "pnl_pct": pnl_pct,
        "r_multiple": r_multiple,
        "result_type": str(result_type).upper() if result_type else None,

        "mfe_pct": _safe_float(_first(raw.get("mfe"), raw.get("mfe_max_pct"), inner.get("mfe_max_pct"))),
        "mae_pct": _safe_float(_first(raw.get("mae"), raw.get("mae_min_pct"), inner.get("mae_min_pct"))),
        "giveback_pct": _safe_float(_first(raw.get("mfe_gave_back_pct"), inner.get("mfe_gave_back_pct"))),

        "tp50_hit": _first(raw.get("tp50_hit"), inner.get("tp50_hit")),
        "exit_model": _first(raw.get("exit_model"), inner.get("exit_model"), item.get("reason")),

        "management_cycles": _first(raw.get("management_cycles"), inner.get("management_cycles")),
        "weekday": _first(item.get("weekday"), raw.get("weekday"), context.get("weekday")),
        "weekday_num": _first(item.get("weekday_num"), raw.get("weekday_num"), context.get("weekday_num")),
        "session": _first(item.get("session_br"), raw.get("session_br"), context.get("session_br")),

        "context": context,
        "source_event": item,
        "raw": raw,
    }