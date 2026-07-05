# paper_lifecycle.py
# CENTRAL QUANT — PAPER LIFECYCLE V1.1
# Versão: 2026-07-05-PAPER-LIFECYCLE-V1.1-PRICE-RECORDER
#
# Objetivo:
# - Gerenciar posições abertas pelo Paper Executor Integrated V2.
# - Simular TP50, breakeven, stop e fechamento.
# - NÃO chama corretora.
# - Atualiza o arquivo paper_integrated_positions.json.
# - Registra eventos em JSONL.
# - V1.1: grava eventos paper com entry/stop/exit/qty/pnl_pct/r_result explícitos,
#   permitindo que History, Closed Trades e Real PnL/R Mapper calculem PnL e R sem
#   depender de dados escondidos em before/after.
#
# Arquivo:
#   /opt/render/project/src/paper_lifecycle.py

import os
import json
import time
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, Optional


VERSION = "2026-07-05-PAPER-LIFECYCLE-V1.1-PRICE-RECORDER"

DATA_DIR = Path(os.getenv("CENTRAL_DATA_DIR", "/opt/render/project/src/data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

PAPER_POSITIONS_FILE = DATA_DIR / "paper_integrated_positions.json"
PAPER_LIFECYCLE_LOG_FILE = DATA_DIR / "paper_lifecycle_log.jsonl"

PAPER_LIFECYCLE_ENABLED = os.getenv("CENTRAL_PAPER_LIFECYCLE_ENABLED", "true").lower() == "true"
# Mantém integração segura com Super History. Se falhar, o lifecycle continua funcionando.
PAPER_LIFECYCLE_HISTORY_ENABLED = os.getenv("CENTRAL_PAPER_LIFECYCLE_HISTORY_ENABLED", "true").lower() in {
    "1", "true", "yes", "sim", "on"
}


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
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _append_jsonl(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")


def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None:
            return default
        if isinstance(value, str):
            value = value.strip().replace("%", "").replace(",", ".")
            if value == "":
                return default
        return float(value)
    except Exception:
        return default


def _first(position: Dict[str, Any], keys, default=None):
    if not isinstance(position, dict):
        return default
    for key in keys:
        value = position.get(key)
        if value is not None and value != "":
            return value
    return default


def _normalize_side(side: Any) -> Optional[str]:
    s = str(side or "").upper().strip()
    if s in {"BUY", "LONG"}:
        return "LONG"
    if s in {"SELL", "SHORT"}:
        return "SHORT"
    return None


def _normalize_symbol(symbol: Any) -> str:
    s = str(symbol or "").upper().strip()
    if not s:
        return ""
    return s.replace("/USDT:USDT", "USDT").replace("/USDT", "USDT").replace(":USDT", "").replace("-", "")


def _entry_price(position: Dict[str, Any]) -> Optional[float]:
    return _safe_float(_first(position, ["entry", "entrada", "entry_price", "avg_entry_price", "open_price"]))


def _stop_initial(position: Dict[str, Any]) -> Optional[float]:
    return _safe_float(_first(position, ["sl_initial", "initial_sl", "initial_stop", "stop_initial", "stop", "sl"]))


def _stop_current(position: Dict[str, Any]) -> Optional[float]:
    return _safe_float(_first(position, ["sl_current", "stop_current", "stop_atual", "stop", "sl", "sl_initial"]))


def _quantity(position: Dict[str, Any]) -> Optional[float]:
    return _safe_float(_first(position, ["qty", "quantity", "size", "amount", "contracts", "position_size"]))


def _pnl_pct(position: Dict[str, Any], price: float) -> Optional[float]:
    entry = _entry_price(position)
    side = _normalize_side(position.get("side"))

    if not entry or entry <= 0 or price <= 0:
        return None

    if side == "LONG":
        return round(((price - entry) / entry) * 100, 4)

    if side == "SHORT":
        return round(((entry - price) / entry) * 100, 4)

    return None


def _r_result(position: Dict[str, Any], price: float) -> Optional[float]:
    entry = _entry_price(position)
    sl_initial = _stop_initial(position)
    side = _normalize_side(position.get("side"))

    if not entry or not sl_initial or entry <= 0 or sl_initial <= 0 or price <= 0:
        return None

    risk = abs(entry - sl_initial)
    if risk <= 0:
        return None

    if side == "LONG":
        return round((price - entry) / risk, 4)

    if side == "SHORT":
        return round((entry - price) / risk, 4)

    return None


def _hit_tp50(position: Dict[str, Any], price: float) -> bool:
    tp50 = _safe_float(position.get("tp50"))
    side = _normalize_side(position.get("side"))

    if not tp50 or price <= 0:
        return False

    if side == "LONG":
        return price >= tp50

    if side == "SHORT":
        return price <= tp50

    return False


def _hit_stop(position: Dict[str, Any], price: float) -> bool:
    sl = _stop_current(position)
    side = _normalize_side(position.get("side"))

    if not sl or price <= 0:
        return False

    if side == "LONG":
        return price <= sl

    if side == "SHORT":
        return price >= sl

    return False


def _move_to_breakeven(position: Dict[str, Any]) -> Dict[str, Any]:
    entry = _entry_price(position)
    if entry:
        position["sl_current"] = entry
        position["breakeven"] = True
        position["last_update"] = _now_br()
    return position


def _event_name_for_history(paper_event_name: str) -> str:
    """
    Traduz eventos paper para nomes que o Super History já entende.
    O evento paper original continua preservado em paper_event/raw_event.
    """
    event_name = str(paper_event_name or "").upper().strip()
    mapping = {
        "PAPER_TP50_HIT": "TP50_HIT",
        "PAPER_BREAKEVEN_SET": "BREAKEVEN",
        "PAPER_TRADE_CLOSED": "TRADE_CLOSED",
        "PAPER_PRICE_UPDATED": "PAPER_PRICE_UPDATED",
    }
    return mapping.get(event_name, event_name or "EVENT")


def _build_lifecycle_event(
    event_name: str,
    pos: Dict[str, Any],
    before: Dict[str, Any],
    price: float,
    close_reason: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Cria evento completo e plano.
    V1.1: campos críticos ficam no topo do payload para serem lidos por:
    - history_manager.normalize_payload
    - closed_trades.jsonl
    - real_pnl_r_mapper
    - outcome/adaptive learning
    """
    now = _now_br()
    epoch = time.time()
    side = _normalize_side(pos.get("side")) or str(pos.get("side") or "").upper().strip()
    symbol = _normalize_symbol(pos.get("symbol") or pos.get("pair") or pos.get("ativo"))
    entry = _entry_price(pos)
    sl_initial = _stop_initial(pos)
    sl_current = _stop_current(pos)
    exit_price = _safe_float(pos.get("exit_price") or price)
    pnl_pct = _safe_float(pos.get("pnl_pct"))
    r_result = _safe_float(pos.get("r_result"))

    # Para eventos de preço/TP/BE ainda abertos, price é o último preço. Para fechamento,
    # exit_price é explicitamente igual ao preço de fechamento.
    history_event = _event_name_for_history(event_name)
    is_closed = history_event == "TRADE_CLOSED"

    event = {
        "event": history_event,
        "event_type": history_event,
        "paper_event": event_name,
        "raw_event": event_name,
        "version": VERSION,
        "generated_at": now,
        "created_at": now,
        "epoch": epoch,
        "source": "paper_lifecycle",
        "mode": "PAPER",
        "trade_id": pos.get("trade_id"),
        "position_id": pos.get("position_id") or pos.get("trade_id"),
        "bot": pos.get("bot"),
        "setup": pos.get("setup") or pos.get("signal_type") or pos.get("strategy"),
        "symbol": symbol,
        "side": side,
        "status": pos.get("status"),
        "price": price,
        "last_price": price,
        "entry": entry,
        "entry_price": entry,
        "entrada": entry,
        "stop": sl_initial,
        "sl": sl_initial,
        "sl_initial": sl_initial,
        "initial_sl": sl_initial,
        "sl_current": sl_current,
        "stop_current": sl_current,
        "tp50": _safe_float(pos.get("tp50")),
        "tp50_hit": bool(pos.get("tp50_hit")),
        "tp50_price": _safe_float(pos.get("tp50_price")),
        "breakeven": bool(pos.get("breakeven")),
        "qty": _quantity(pos),
        "quantity": _quantity(pos),
        "pnl_pct": pnl_pct,
        "result_pct": pnl_pct,
        "r_result": r_result,
        "result_r": r_result,
        "r": r_result,
        "close_reason": pos.get("close_reason") or close_reason,
        "reason": pos.get("close_reason") or close_reason,
        "entry_time": pos.get("entry_time") or pos.get("opened_at") or pos.get("created_at"),
        "opened_at": pos.get("opened_at") or pos.get("entry_time") or pos.get("created_at"),
        "entry_epoch": _safe_float(pos.get("entry_epoch") or pos.get("opened_epoch")),
        "closed_at": pos.get("closed_at"),
        "closed_epoch": _safe_float(pos.get("closed_epoch")),
        "after": dict(pos),
        "before": dict(before or {}),
    }

    if is_closed:
        event.update({
            "exit": exit_price,
            "exit_price": exit_price,
            "close_price": exit_price,
            "exit_time": pos.get("closed_at") or now,
            "closed_at": pos.get("closed_at") or now,
            "closed_epoch": _safe_float(pos.get("closed_epoch"), epoch),
            "closed": True,
            "result": "WIN" if (pnl_pct is not None and pnl_pct > 0) else ("LOSS" if (pnl_pct is not None and pnl_pct < 0) else "BREAKEVEN"),
        })
    else:
        event.update({
            "exit": None,
            "exit_price": None,
            "close_price": None,
            "closed": False,
        })

    return event


def _emit_history_event(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Envia evento ao Super History quando disponível.
    Falha aqui nunca pode quebrar o Paper Lifecycle.
    """
    if not PAPER_LIFECYCLE_HISTORY_ENABLED:
        return {"ok": True, "skipped": True, "reason": "PAPER_LIFECYCLE_HISTORY_DISABLED"}

    try:
        import history_manager
        if not hasattr(history_manager, "log_event"):
            return {"ok": False, "error": "history_manager.log_event ausente"}
        history_event = event.get("event") or event.get("event_type") or "EVENT"
        return history_manager.log_event(
            history_event,
            event,
            source="paper_lifecycle",
            trade_id=event.get("trade_id"),
        )
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def paper_lifecycle_health() -> Dict[str, Any]:
    positions = _read_json(PAPER_POSITIONS_FILE, [])
    open_positions = [
        p for p in positions
        if isinstance(p, dict) and p.get("status") == "OPEN"
    ]

    return {
        "ok": True,
        "module": "paper_lifecycle",
        "loaded": True,
        "version": VERSION,
        "generated_at": _now_br(),
        "enabled": PAPER_LIFECYCLE_ENABLED,
        "history_enabled": PAPER_LIFECYCLE_HISTORY_ENABLED,
        "open_positions": len(open_positions),
        "total_positions": len(positions),
        "files": {
            "paper_positions": str(PAPER_POSITIONS_FILE),
            "paper_lifecycle_log": str(PAPER_LIFECYCLE_LOG_FILE),
        },
        "notes": [
            "Paper Lifecycle V1.1 gerencia posições paper já abertas.",
            "Simula TP50, breakeven, stop e fechamento.",
            "Não chama corretora.",
            "V1.1 grava entry, stop, exit, qty, pnl_pct e r_result no topo do evento.",
        ],
    }


def update_paper_position_price(
    trade_id: Optional[str] = None,
    symbol: Optional[str] = None,
    price: Optional[float] = None,
    close: bool = False,
    close_reason: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Atualiza uma posição paper com preço manual.
    Pode ser usado via endpoint para testar TP50/BE/STOP.
    """
    if not PAPER_LIFECYCLE_ENABLED:
        return {
            "ok": False,
            "status": "PAPER_LIFECYCLE_DISABLED",
            "generated_at": _now_br(),
            "version": VERSION,
        }

    price = _safe_float(price)
    if price is None or price <= 0:
        return {
            "ok": False,
            "status": "INVALID_PRICE",
            "error": "price inválido ou ausente",
            "generated_at": _now_br(),
            "version": VERSION,
        }

    positions = _read_json(PAPER_POSITIONS_FILE, [])
    updated = []
    events = []
    history_results = []

    for pos in positions:
        if not isinstance(pos, dict):
            continue
        if pos.get("status") != "OPEN":
            continue

        if trade_id and str(pos.get("trade_id")) != str(trade_id):
            continue
        if symbol and _normalize_symbol(pos.get("symbol", "")) != _normalize_symbol(symbol):
            continue

        before = dict(pos)
        pos["last_price"] = price
        pos["last_update"] = _now_br()
        pos["pnl_pct"] = _pnl_pct(pos, price)
        pos["r_result"] = _r_result(pos, price)

        event_names = []

        if not pos.get("tp50_hit") and _hit_tp50(pos, price):
            pos["tp50_hit"] = True
            pos["tp50_hit_at"] = _now_br()
            pos["tp50_price"] = price
            _move_to_breakeven(pos)
            # Recalcula stop atual após breakeven.
            pos["pnl_pct"] = _pnl_pct(pos, price)
            pos["r_result"] = _r_result(pos, price)
            event_names.append("PAPER_TP50_HIT")
            event_names.append("PAPER_BREAKEVEN_SET")

        if _hit_stop(pos, price):
            pos["status"] = "CLOSED"
            pos["closed_at"] = _now_br()
            pos["closed_epoch"] = time.time()
            pos["exit_price"] = price
            pos["close_reason"] = close_reason or "STOP_HIT"
            pos["pnl_pct"] = _pnl_pct(pos, price)
            pos["r_result"] = _r_result(pos, price)
            event_names.append("PAPER_TRADE_CLOSED")

        if close and pos.get("status") == "OPEN":
            pos["status"] = "CLOSED"
            pos["closed_at"] = _now_br()
            pos["closed_epoch"] = time.time()
            pos["exit_price"] = price
            pos["close_reason"] = close_reason or "MANUAL_CLOSE"
            pos["pnl_pct"] = _pnl_pct(pos, price)
            pos["r_result"] = _r_result(pos, price)
            event_names.append("PAPER_TRADE_CLOSED")

        if not event_names:
            event_names.append("PAPER_PRICE_UPDATED")

        for event_name in event_names:
            event = _build_lifecycle_event(
                event_name=event_name,
                pos=pos,
                before=before,
                price=price,
                close_reason=close_reason,
            )
            _append_jsonl(PAPER_LIFECYCLE_LOG_FILE, event)
            history_result = _emit_history_event(event)
            if history_result is not None:
                event["history_result"] = history_result
                history_results.append({
                    "event": event.get("event"),
                    "paper_event": event.get("paper_event"),
                    "trade_id": event.get("trade_id"),
                    "ok": history_result.get("ok") if isinstance(history_result, dict) else None,
                    "dedup": history_result.get("dedup") if isinstance(history_result, dict) else None,
                    "error": history_result.get("error") if isinstance(history_result, dict) else None,
                })
            events.append(event)

        updated.append(pos.get("trade_id"))

    _write_json(PAPER_POSITIONS_FILE, positions)

    return {
        "ok": True,
        "status": "PAPER_LIFECYCLE_UPDATED",
        "version": VERSION,
        "generated_at": _now_br(),
        "updated_count": len(updated),
        "updated_trade_ids": updated,
        "events_count": len(events),
        "history_events_count": len(history_results),
        "history_results": history_results,
        "events": events,
    }


def get_paper_lifecycle_positions(status: Optional[str] = None) -> Dict[str, Any]:
    positions = _read_json(PAPER_POSITIONS_FILE, [])
    if status:
        s = str(status).upper().strip()
        positions = [
            p for p in positions
            if isinstance(p, dict) and str(p.get("status", "")).upper() == s
        ]

    return {
        "ok": True,
        "generated_at": _now_br(),
        "count": len(positions),
        "positions": positions,
    }


def read_paper_lifecycle_log(limit: int = 20) -> Dict[str, Any]:
    if not PAPER_LIFECYCLE_LOG_FILE.exists():
        return {
            "ok": True,
            "generated_at": _now_br(),
            "count": 0,
            "items": [],
        }

    lines = PAPER_LIFECYCLE_LOG_FILE.read_text(encoding="utf-8").splitlines()
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


def paper_lifecycle_test_tp50() -> Dict[str, Any]:
    """
    Teste simples para a posição ETHUSDT paper aberta:
    preço acima do TP50 do exemplo 3501 -> 3571.
    """
    return update_paper_position_price(
        symbol="ETHUSDT",
        price=3572,
        close=False,
        close_reason="TEST_TP50",
    )


def paper_lifecycle_test_close() -> Dict[str, Any]:
    """
    Fecha manualmente posição paper ETHUSDT em preço exemplo.
    """
    return update_paper_position_price(
        symbol="ETHUSDT",
        price=3580,
        close=True,
        close_reason="TEST_MANUAL_CLOSE",
    )
