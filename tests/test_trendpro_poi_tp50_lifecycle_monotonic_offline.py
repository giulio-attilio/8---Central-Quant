from __future__ import annotations

import ast
import copy
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "bots" / "trendpro.py"


def _function_node() -> ast.FunctionDef:
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
    return next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "atualizar_posicao_com_poi"
    )


@pytest.mark.parametrize("tp50_hit", [False, True])
def test_poi_update_preserves_tp50_state_for_same_position_lifecycle(tp50_hit: bool) -> None:
    position = {
        "status": "ATIVO",
        "tp50_hit": tp50_hit,
        "tp50_message_sent": tp50_hit,
        "breakeven": False,
        "trailing_activated_at": None,
        "symbol_clean": "NEARUSDT",
        "side": "LONG",
    }
    poi = {
        "symbol": "NEAR/USDT:USDT",
        "symbol_clean": "NEARUSDT",
        "side": "LONG",
        "entry": 5.221,
        "sl": 5.0925444435592695,
        "tp50": 5.349455556440731,
        "risk_abs": 0.1284555564407305,
        "risk_pct": 2.460363080649887,
        "timestamp": 1792238460,
    }
    writes: list[dict] = []
    events: list[dict] = []
    saved: list[dict] = []
    namespace = {
        "ALLOW_POI_UPDATE_ENTRY": True,
        "carregar_posicoes": lambda: {poi["symbol"]: copy.deepcopy(position)},
        "salvar_posicoes": lambda payload: saved.append(copy.deepcopy(payload)),
        "update_trade_registry_trade": lambda trade, **updates: writes.append(copy.deepcopy(updates)),
        "registrar_evento_trade": lambda event: events.append(copy.deepcopy(event)),
        "data_hoje_sp_str": lambda: "16/10/2026",
        "data_hora_sp_str": lambda: "16/10/2026 12:01",
        "time": SimpleNamespace(time=lambda: 1792238460),
    }
    isolated = ast.Module(body=[_function_node()], type_ignores=[])
    ast.fix_missing_locations(isolated)
    exec(compile(isolated, "<isolated-trendpro-poi-update>", "exec"), namespace)

    namespace["atualizar_posicao_com_poi"](poi)

    assert saved[0][poi["symbol"]]["tp50_hit"] is tp50_hit
    assert saved[0][poi["symbol"]]["tp50_message_sent"] is tp50_hit
    assert writes[0]["last_update_type"] == "POI"
    assert "tp50_hit" not in writes[0]
    assert events[0]["event"] == "POI"
