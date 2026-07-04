# paper_lifecycle.py
# CENTRAL QUANT — PAPER LIFECYCLE V1
# Versão: 2026-07-04-PAPER-LIFECYCLE-V1
#
# Objetivo:
# - Gerenciar posições abertas pelo Paper Executor Integrated V2.
# - Simular TP50, breakeven, stop e fechamento.
# - NÃO chama corretora.
# - Atualiza o arquivo paper_integrated_positions.json.
# - Registra eventos em JSONL.
#
# Arquivo:
#   /opt/render/project/src/paper_lifecycle.py

import os
import json
import time
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, Optional


VERSION = "2026-07-04-PAPER-LIFECYCLE-V1"

DATA_DIR = Path(os.getenv("CENTRAL_DATA_DIR", "/opt/render/project/src/data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

PAPER_POSITIONS_FILE = DATA_DIR / "paper_integrated_positions.json"
PAPER_LIFECYCLE_LOG_FILE = DATA_DIR / "paper_lifecycle_log.jsonl"

PAPER_LIFECYCLE_ENABLED = os.getenv("CENTRAL_PAPER_LIFECYCLE_ENABLED", "true").lower() == "true"


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
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _append_jsonl(path: Path, payload: Dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _normalize_side(side: Any) -> Optional[str]:
    s = str(side or "").upper().strip()
    if s in {"BUY", "LONG"}:
        return "LONG"
    if s in {"SELL", "SHORT"}:
        return "SHORT"
    return None


def _pnl_pct(position: Dict[str, Any], price: float) -> Optional[float]:
    entry = _safe_float(position.get("entry"))
    side = _normalize_side(position.get("side"))

    if not entry or entry <= 0 or price <= 0:
        return None

    if side == "LONG":
        return round(((price - entry) / entry) * 100, 4)

    if side == "SHORT":
        return round(((entry - price) / entry) * 100, 4)

    return None


def _r_result(position: Dict[str, Any], price: float) -> Optional[float]:
    entry = _safe_float(position.get("entry"))
    sl_initial = _safe_float(position.get("sl_initial"))
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
    sl = _safe_float(position.get("sl_current") or position.get("sl_initial"))
    side = _normalize_side(position.get("side"))

    if not sl or price <= 0:
        return False

    if side == "LONG":
        return price <= sl

    if side == "SHORT":
        return price >= sl

    return False


def _move_to_breakeven(position: Dict[str, Any]) -> Dict[str, Any]:
    entry = _safe_float(position.get("entry"))
    if entry:
        position["sl_current"] = entry
        position["breakeven"] = True
        position["last_update"] = _now_br()
    return position


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
        "open_positions": len(open_positions),
        "total_positions": len(positions),
        "files": {
            "paper_positions": str(PAPER_POSITIONS_FILE),
            "paper_lifecycle_log": str(PAPER_LIFECYCLE_LOG_FILE),
        },
        "notes": [
            "Paper Lifecycle V1 gerencia posições paper já abertas.",
            "Simula TP50, breakeven, stop e fechamento.",
            "Não chama corretora.",
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

    for pos in positions:
        if not isinstance(pos, dict):
            continue
        if pos.get("status") != "OPEN":
            continue

        if trade_id and str(pos.get("trade_id")) != str(trade_id):
            continue
        if symbol and str(pos.get("symbol", "")).upper() != str(symbol).upper():
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
            event = {
                "event": event_name,
                "version": VERSION,
                "generated_at": _now_br(),
                "epoch": time.time(),
                "trade_id": pos.get("trade_id"),
                "symbol": pos.get("symbol"),
                "side": pos.get("side"),
                "price": price,
                "before": before,
                "after": pos,
            }
            _append_jsonl(PAPER_LIFECYCLE_LOG_FILE, event)
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
