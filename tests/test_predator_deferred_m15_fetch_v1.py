from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class _Frame:
    def __init__(self, size: int, row=None):
        self._size = size
        self.iloc = {-2: row or {"spike_suspeito": False, "volume_ok": True}}

    def __len__(self):
        return self._size


def _load_scanner(fetch_df, bullish_sweep=None, bearish_sweep=None):
    tree = ast.parse((ROOT / "bots" / "predator.py").read_text(encoding="utf-8"))
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "scan_smart_predator_symbol"
    )
    module = ast.Module(body=[function], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {
        "SMART_PREDATOR_ENABLED": True,
        "TIMEFRAME_H1": "1h",
        "TIMEFRAME_H4": "4h",
        "TIMEFRAME_M15": "15m",
        "SWING_LOOKBACK": 20,
        "OB_LOOKBACK": 20,
        "USE_MAX_RISK_FILTER": True,
        "MAX_RISK_H1": 2.0,
        "MIN_PREDATOR_SCORE": 85,
        "SMART_PREDATOR_AUTO_TRADE": False,
        "inc_funnel_stat": lambda *_args: None,
        "existe_posicao_ativa": lambda _symbol: False,
        "limite_posicoes_atingido": lambda: False,
        "fetch_df": fetch_df,
        "detect_bullish_sweep": lambda *_args: bullish_sweep,
        "detect_bearish_sweep": lambda *_args: bearish_sweep,
        "detect_bullish_choch_m15_after_sweep": lambda *_args: None,
        "detect_bearish_choch_m15_after_sweep": lambda *_args: None,
        "find_bullish_order_block": lambda *_args: None,
        "find_bearish_order_block": lambda *_args: None,
        "em_cooldown": lambda *_args: False,
        "nome_limpo": lambda value: value,
        "contexto_h4_txt": lambda _row: ("NEUTRO", 20.0),
    }
    exec(compile(module, "bots/predator.py", "exec"), namespace)
    return namespace["scan_smart_predator_symbol"]


def test_predator_skips_m15_request_when_h1_has_no_sweep():
    calls = []

    def fetch_df(_symbol, timeframe, limit):
        calls.append((timeframe, limit))
        return _Frame(100)

    scanner = _load_scanner(fetch_df)

    assert scanner("BTC/USDT:USDT") is None
    assert calls == [("1h", 100), ("4h", 100)]


def test_predator_fetches_m15_only_after_h1_sweep_candidate():
    calls = []

    def fetch_df(_symbol, timeframe, limit):
        calls.append((timeframe, limit))
        return _Frame(10 if timeframe == "15m" else 100)

    scanner = _load_scanner(fetch_df, bullish_sweep={"found": True})

    assert scanner("BTC/USDT:USDT") is None
    assert calls == [("1h", 100), ("4h", 100), ("15m", 100)]


def test_predator_uses_valid_m15_for_candidate_confirmation():
    calls = []

    def fetch_df(_symbol, timeframe, limit):
        calls.append((timeframe, limit))
        return _Frame(100)

    scanner = _load_scanner(fetch_df, bullish_sweep={"found": True})

    assert scanner("BTC/USDT:USDT") is None
    assert calls == [("1h", 100), ("4h", 100), ("15m", 100)]
