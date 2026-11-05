from __future__ import annotations

import ast
from pathlib import Path

import pytest
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SCANNERS = [
    ("bots/trendpro.py", "analisar_sinal_h1"),
    ("bots/trendpro.py", "detectar_early_a"),
    ("bots/trendpro.py", "detectar_poi"),
    ("bots/trendpro.py", "detectar_reentry"),
    ("bots/meme.py", "detectar_early_hunter"),
    ("bots/meme.py", "detectar_breakout_meme"),
    ("bots/meme.py", "analisar_sinal_h1"),
    ("bots/meme.py", "detectar_early_a"),
    ("bots/meme.py", "detectar_poi"),
    ("bots/meme.py", "detectar_reentry"),
    ("bots/donkey.py", "analisar_sinal_h1"),
    ("bots/donkey.py", "detectar_early_a"),
    ("bots/donkey.py", "detectar_poi"),
    ("bots/donkey.py", "detectar_reentry"),
    ("bots/donkey.py", "detectar_donkey_h4"),
    ("bots/donkey.py", "detectar_donkey_h4_original"),
    ("bots/donkey.py", "detectar_early_donkey_h4"),
    ("bots/donkey.py", "detectar_poi_donkey_h4"),
]


def _data_guards_before_dataframe(relative_path: str, function_name: str):
    source = (ROOT / relative_path).read_text(encoding="utf-8")
    tree = ast.parse(source, filename=relative_path)
    function = next(
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == function_name
    )
    dataframe_line = min(
        node.lineno
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "DataFrame"
    )
    guards = []
    for node in ast.walk(function):
        if not isinstance(node, ast.If) or node.lineno >= dataframe_line:
            continue
        names = {
            item.id
            for item in ast.walk(node.test)
            if isinstance(item, ast.Name)
        }
        if names and all(name.startswith("ohlcv_") or name == "len" for name in names):
            if any(isinstance(item, ast.Return) for item in ast.walk(node)):
                guards.append(node.test)
    return guards


@pytest.mark.parametrize(("relative_path", "function_name"), SCANNERS)
@pytest.mark.parametrize("row_count", [0, 1])
def test_scanner_returns_before_dataframe_for_empty_or_single_candle(
    relative_path: str, function_name: str, row_count: int
):
    guards = _data_guards_before_dataframe(relative_path, function_name)
    assert guards, f"missing pre-DataFrame OHLCV guard in {relative_path}:{function_name}"

    for guard in guards:
        names = {
            item.id
            for item in ast.walk(guard)
            if isinstance(item, ast.Name)
        }
        local_values = {
            name: ([[1, 2, 3, 4, 5, 6]] * row_count)
            for name in names
            if name != "len"
        }
        if eval(compile(ast.Expression(guard), relative_path, "eval"), {"__builtins__": {"len": len}}, local_values):
            return

    pytest.fail(
        f"{relative_path}:{function_name} has no fail-closed guard for {row_count} candle(s)"
    )


@pytest.mark.parametrize("relative_path", ["bots/trendpro.py", "bots/meme.py", "bots/donkey.py"])
def test_supertrend_handles_empty_dataframe_without_iloc_growth(relative_path: str):
    tree = ast.parse((ROOT / relative_path).read_text(encoding="utf-8"))
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "calcular_supertrend_df"
    )
    module = ast.Module(body=[function], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {"pd": pd}
    exec(compile(module, relative_path, "exec"), namespace)

    frame = pd.DataFrame(columns=["high", "low", "close"])
    supertrend, direction = namespace["calcular_supertrend_df"](frame)

    assert supertrend.empty
    assert direction.empty
    assert supertrend.index.equals(frame.index)
    assert direction.index.equals(frame.index)
    assert str(supertrend.dtype) == "float64"
    assert str(direction.dtype) == "int64"


@pytest.mark.parametrize("relative_path", ["bots/trendpro.py", "bots/meme.py", "bots/donkey.py"])
def test_empty_ohlcv_survives_full_indicator_preparation(relative_path: str):
    tree = ast.parse((ROOT / relative_path).read_text(encoding="utf-8"))
    required = {
        "calcular_supertrend_df",
        "calcular_adx",
        "marcar_spikes",
        "preparar_df",
    }
    functions = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in required
    ]
    assert {node.name for node in functions} == required
    module = ast.Module(body=functions, type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {
        "pd": pd,
        "ENABLE_SPIKE_FILTER": False,
        "EMA_FAST": 9,
        "EMA20": 20,
        "EMA_MID": 21,
        "EMA50": 50,
        "EMA200": 200,
        "ATR_LEN": 14,
        "SUPERTREND_PERIOD": 10,
        "SUPERTREND_FACTOR": 3.5,
        "ADX_LEN": 14,
        "ADX_MIN": 20,
        "DONKEY_MACD_FAST": 12,
        "DONKEY_MACD_SLOW": 26,
        "DONKEY_MACD_SIGNAL": 9,
        "calcular_atr": lambda frame, _period: pd.Series(index=frame.index, dtype="float64"),
    }
    exec(compile(module, relative_path, "exec"), namespace)

    frame = pd.DataFrame(columns=["time", "open", "high", "low", "close", "volume"])
    prepared = namespace["preparar_df"](frame)

    assert prepared.empty
    assert len(prepared.columns) > len(frame.columns)


@pytest.mark.parametrize("row_count", [0, 1])
def test_donkey_chandelier_fails_closed_before_indexing_insufficient_ohlcv(row_count: int):
    source = (ROOT / "bots/donkey.py").read_text(encoding="utf-8")
    tree = ast.parse(source, filename="bots/donkey.py")
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "calcular_chandelier"
    )
    module = ast.Module(body=[function], type_ignores=[])
    ast.fix_missing_locations(module)
    ohlcv = [[1, 2, 3, 1, 2, 10] for _ in range(row_count)]
    health = {}
    namespace = {
        "safe_fetch_ohlcv": lambda *_args, **_kwargs: ohlcv,
        "TIMEFRAME_H1": "1h",
        "HEALTH": health,
        "nome_limpo": lambda symbol: symbol,
    }
    exec(compile(module, "bots/donkey.py", "exec"), namespace)

    with pytest.raises(ValueError, match="OHLCV_INSUFFICIENT_FOR_DONKEY_CHANDELIER"):
        namespace["calcular_chandelier"]("TEST/USDT", "LONG")
    assert "OHLCV insuficiente" in health["last_warning"]
