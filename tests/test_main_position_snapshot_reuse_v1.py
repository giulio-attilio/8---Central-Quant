import ast
import copy
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "main.py"
TREE = ast.parse(SOURCE.read_text(encoding="utf-8"))


def _load_functions(names, namespace):
    selected = {}
    for node in TREE.body:
        if isinstance(node, ast.FunctionDef) and node.name in names:
            selected[node.name] = copy.deepcopy(node)
    assert not names.difference(selected)
    module = ast.Module(
        body=sorted(selected.values(), key=lambda node: node.lineno),
        type_ignores=[],
    )
    ast.fix_missing_locations(module)
    exec(compile(module, str(SOURCE), "exec"), namespace)
    return namespace


def _position(*, mode, order_id=None):
    return {
        "symbol": "BTC/USDT:USDT",
        "side": "LONG",
        "setup": "TEST",
        "entry": 100.0,
        "sl": 90.0,
        "tp50": 110.0,
        "execution_mode": mode,
        "live_order_id": order_id,
        "qty": 1.0,
    }


def test_open_and_live_views_share_one_bot_position_read_per_decision():
    modules = {"PAPERBOT": SimpleNamespace(), "LIVEBOT": SimpleNamespace()}
    source_positions = {
        "PAPERBOT": [_position(mode="PAPER")],
        "LIVEBOT": [_position(mode="LIVE", order_id="LIVE-1")],
    }
    calls = []

    def load(module, *, key, raise_on_error=False):
        calls.append((key, raise_on_error))
        return copy.deepcopy(source_positions[key])

    namespace = {
        "LOADED_BOTS": modules,
        "get_open_positions_from_module": load,
        "_compact_symbol": lambda value: str(value).replace("/", "").replace(":USDT", ""),
        "_symbol_sector": lambda _symbol: "TEST",
        "_position_runner_r": lambda _position: 0.0,
        "_position_runner_pct": lambda _position: 0.0,
        "normalize_symbol_for_risk": lambda value: str(value).replace("/", "").replace(":USDT", ""),
        "_flad_v1_public": lambda value: copy.deepcopy(value),
    }
    _load_functions(
        {
            "_bot_open_positions_snapshot",
            "_all_open_positions_payload",
            "_central_live_positions_payload",
        },
        namespace,
    )

    snapshot = namespace["_bot_open_positions_snapshot"]()
    all_rows = namespace["_all_open_positions_payload"](snapshot)
    live_rows = namespace["_central_live_positions_payload"](
        positions_by_bot=snapshot
    )

    assert calls == [("PAPERBOT", False), ("LIVEBOT", False)]
    assert len(all_rows) == 2
    assert [row["bot"] for row in all_rows] == ["PAPERBOT", "LIVEBOT"]
    assert len(live_rows) == 1
    assert live_rows[0]["bot"] == "LIVEBOT"
    assert live_rows[0]["order_id"] == "LIVE-1"
    assert calls == [("PAPERBOT", False), ("LIVEBOT", False)]


def test_live_projection_without_shared_snapshot_keeps_standalone_read_behavior():
    modules = {"LIVEBOT": SimpleNamespace()}
    calls = []

    def load(module, *, key="LIVEBOT", raise_on_error=False):
        calls.append((key, raise_on_error))
        return [_position(mode="LIVE", order_id="LIVE-1")]

    namespace = {
        "LOADED_BOTS": modules,
        "get_open_positions_from_module": load,
        "normalize_symbol_for_risk": lambda value: str(value),
        "_flad_v1_public": lambda value: value,
    }
    _load_functions({"_central_live_positions_payload"}, namespace)

    rows = namespace["_central_live_positions_payload"]()

    assert len(rows) == 1
    assert rows[0]["order_id"] == "LIVE-1"
    assert calls == [("LIVEBOT", False)]


def test_can_open_trade_wires_the_same_snapshot_to_both_position_views():
    source = SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    base = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "can_open_trade_decision"
        and node.lineno < 20000
    )
    calls = [
        node for node in ast.walk(base)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    ]
    snapshot_assignment = next(
        node for node in calls if node.func.id == "_bot_open_positions_snapshot"
    )
    assert snapshot_assignment is not None

    def snapshot_arg(call):
        for arg in call.args:
            if isinstance(arg, ast.Name) and arg.id == "bot_positions_snapshot":
                return True
        for keyword in call.keywords:
            if (
                keyword.arg == "positions_by_bot"
                and isinstance(keyword.value, ast.Name)
                and keyword.value.id == "bot_positions_snapshot"
            ):
                return True
        return False

    assert any(
        node.func.id == "_all_open_positions_payload" and snapshot_arg(node)
        for node in calls
    )
    assert any(
        node.func.id == "_central_live_positions_payload" and snapshot_arg(node)
        for node in calls
    )
