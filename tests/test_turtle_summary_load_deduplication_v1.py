from __future__ import annotations

import ast
import copy
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TURTLE_PATH = ROOT / "bots" / "turtle.py"
TURTLE_SOURCE = TURTLE_PATH.read_text(encoding="utf-8")
TURTLE_TREE = ast.parse(TURTLE_SOURCE, filename=str(TURTLE_PATH))

FILTER_NAMES = (
    "_trades_today_from_rows",
    "_trades_month_from_rows",
    "_signals_today_from_rows",
    "_signals_month_from_rows",
)
PUBLIC_FILTER_NAMES = (
    "trades_today",
    "trades_month",
    "signals_today",
    "signals_month",
)


def _function(name: str) -> ast.FunctionDef:
    return next(
        node
        for node in TURTLE_TREE.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    )


def _load_functions(names: tuple[str, ...], namespace: dict) -> dict:
    nodes = [copy.deepcopy(_function(name)) for name in names]
    module = ast.Module(body=nodes, type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, str(TURTLE_PATH), "exec"), namespace)
    return {name: namespace[name] for name in names}


def _filter_namespace() -> dict:
    namespace = {}
    _load_functions(
        (
            "signal_date_matches",
            "trade_month_matches",
            "trade_date_matches",
            *FILTER_NAMES,
        ),
        namespace,
    )
    return namespace


def _representative_rows() -> tuple[list[dict], list[dict]]:
    trades = [
        {"id": "today-boundary", "closed_at": "12/08/2026 00:00", "setup": "TURTLE20", "side": "LONG"},
        {"id": "yesterday", "closed_at": "11/08/2026 23:59", "setup": "TURTLE55", "side": "SHORT"},
        {"id": "month-boundary", "closed_at": "01/08/2026 00:00", "setup": "TURTLE20", "side": "SHORT"},
        {"id": "previous-month", "closed_at": "31/07/2026 23:59", "setup": "TURTLE55", "side": "LONG"},
        {"id": "invalid", "closed_at": None, "setup": None, "side": None},
    ]
    signals = [
        {"id": "today-boundary", "created_at": "12/08/2026 00:00", "setup": "TURTLE20", "side": "LONG"},
        {"id": "yesterday", "created_at": "11/08/2026 23:59", "setup": "TURTLE55", "side": "SHORT"},
        {"id": "month-boundary", "created_at": "01/08/2026 00:00", "setup": "TURTLE20", "side": "SHORT"},
        {"id": "previous-month", "created_at": "31/07/2026 23:59", "setup": "TURTLE55", "side": "LONG"},
        {"id": "invalid", "created_at": None, "setup": None, "side": None},
    ]
    return trades, signals


def _stats(rows: list[dict]) -> dict:
    count = len(rows)
    return {
        "mfe_avg_pct": float(count),
        "mae_avg_pct": -float(count),
        "mfe_avg_r": float(count) / 10,
        "mae_avg_r": -float(count) / 10,
        "giveback_avg_pct": float(count) / 2,
        "giveback_avg_r": float(count) / 20,
        "expectancy_r": float(count) / 5,
        "profit_factor_pct": float(count),
        "profit_factor_r": float(count) + 1,
        "trend_capture_pct": float(count) * 2,
        "top_mfe": [{"symbol": rows[0].get("id")}] if rows else [],
        "runners_3r": count,
        "runners_5r": count // 2,
        "runners_10r": count // 3,
    }


def _runtime_namespace(calls: list[str]) -> dict:
    trades, signals = _representative_rows()
    events = [
        {"created_at": "12/08/2026 00:00", "event_type": "TP50"},
        {"created_at": "12/08/2026 10:00", "event_type": "BE"},
        {"created_at": "11/08/2026 23:59", "event_type": "STOP"},
    ]

    def load(name, rows):
        def getter():
            calls.append(name)
            return rows
        return getter

    namespace = _filter_namespace()
    namespace.update({
        "HEALTH": {},
        "get_trades": load("get_trades", trades),
        "get_signals": load("get_signals", signals),
        "get_events": load("get_events", events),
        "month_key_br": lambda: "08/2026",
        "date_key_br": lambda: "12/08/2026",
        "next_memory_observation_cycle_id": lambda _prefix: "cycle-equivalence",
        "start_memory_workload_span": lambda: {"started_at": 1.0, "rss_start_mb": 100.0},
        "transition_memory_phase_observation": lambda *_args, **_kwargs: {
            "started_at": 2.0,
            "rss_start_mb": 120.0,
        },
        "finish_memory_phase_observation": lambda *_args, **_kwargs: True,
        "calc_stats": _stats,
        "slim_stats": lambda stats: dict(stats),
        "funnel_snapshot": lambda: {"ativos_analisados": 9},
        "get_open_runner": lambda: {
            "symbol": "BTC/USDT:USDT",
            "setup": "TURTLE20",
            "side": "LONG",
            "mfe_r": 3.5,
            "mfe_pct": 7.0,
        },
        "safe_float": lambda value: float(value or 0.0),
        "split_by_setup": lambda rows: {
            "TURTLE20": [row for row in rows if row.get("setup") == "TURTLE20"],
            "TURTLE55": [row for row in rows if row.get("setup") == "TURTLE55"],
        },
        "split_by_direction": lambda rows: {
            "LONG": [row for row in rows if row.get("side") == "LONG"],
            "SHORT": [row for row in rows if row.get("side") == "SHORT"],
        },
        "build_ranking_month": lambda rows: [
            {"name": "TURTLE20", "trades": len(rows)},
            {"name": "TURTLE55", "trades": len(rows)},
        ],
        "data_hora_sp_str": lambda: "12/08/2026 10:00",
    })
    _load_functions(PUBLIC_FILTER_NAMES, namespace)
    return namespace


def _load_refresh(namespace: dict, *, legacy_loads: bool = False):
    refresh = copy.deepcopy(_function("refresh_health_stats"))
    if legacy_loads:
        transition_index = next(
            index
            for index, statement in enumerate(refresh.body)
            if isinstance(statement, ast.Assign)
            and isinstance(statement.value, ast.Call)
            and isinstance(statement.value.func, ast.Name)
            and statement.value.func.id == "transition_memory_phase_observation"
        )
        legacy = ast.parse(
            "month_trades = trades_month()\n"
            "month_signals = signals_month()\n"
            "today_trades = trades_today()\n"
            "today_signals = signals_today()\n"
            "today_events = [e for e in get_events() if str(e.get('created_at', '')).startswith(date_key_br())]\n"
        ).body
        refresh.body[2:transition_index] = legacy
    module = ast.Module(body=[refresh], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, str(TURTLE_PATH), "exec"), namespace)
    return namespace["refresh_health_stats"]


class TurtleSummaryLoadDeduplicationTests(unittest.TestCase):
    def test_pure_filters_match_previous_expressions_and_reuse_row_objects(self):
        namespace = _filter_namespace()
        trades, signals = _representative_rows()

        trade_month_expected = [t for t in trades if namespace["trade_month_matches"](t, "08/2026")]
        trade_today_expected = [t for t in trades if namespace["trade_date_matches"](t, "12/08/2026")]
        signal_month_expected = [s for s in signals if "08/2026" in str(s.get("created_at", ""))]
        signal_today_expected = [s for s in signals if namespace["signal_date_matches"](s, "12/08/2026")]

        cases = (
            ("_trades_month_from_rows", trades, "08/2026", trade_month_expected),
            ("_trades_today_from_rows", trades, "12/08/2026", trade_today_expected),
            ("_signals_month_from_rows", signals, "08/2026", signal_month_expected),
            ("_signals_today_from_rows", signals, "12/08/2026", signal_today_expected),
        )
        for name, rows, key, expected in cases:
            with self.subTest(name=name):
                actual = namespace[name](rows, key)
                self.assertEqual(actual, expected)
                self.assertTrue(all(actual_row is expected_row for actual_row, expected_row in zip(actual, expected)))

        self.assertEqual([row["id"] for row in trade_month_expected], ["today-boundary", "yesterday", "month-boundary"])
        self.assertEqual([row["id"] for row in trade_today_expected], ["today-boundary"])
        self.assertEqual([row["id"] for row in signal_month_expected], ["today-boundary", "yesterday", "month-boundary"])
        self.assertEqual([row["id"] for row in signal_today_expected], ["today-boundary"])

    def test_public_helpers_keep_independent_api_and_one_load_each(self):
        calls = []
        namespace = _runtime_namespace(calls)

        self.assertEqual(len(namespace["trades_month"]()), 3)
        self.assertEqual(len(namespace["trades_today"]()), 1)
        self.assertEqual(len(namespace["signals_month"]()), 3)
        self.assertEqual(len(namespace["signals_today"]()), 1)
        self.assertEqual(calls.count("get_trades"), 2)
        self.assertEqual(calls.count("get_signals"), 2)

    def test_refresh_deduplicates_loads_and_matches_legacy_health(self):
        legacy_calls = []
        legacy_namespace = _runtime_namespace(legacy_calls)
        legacy_refresh = _load_refresh(legacy_namespace, legacy_loads=True)
        self.assertIsNone(legacy_refresh())

        new_calls = []
        new_namespace = _runtime_namespace(new_calls)
        new_refresh = _load_refresh(new_namespace)
        self.assertIsNone(new_refresh())

        self.assertEqual(legacy_calls.count("get_trades"), 2)
        self.assertEqual(legacy_calls.count("get_signals"), 2)
        self.assertEqual(legacy_calls.count("get_events"), 1)
        self.assertEqual(new_calls.count("get_trades"), 1)
        self.assertEqual(new_calls.count("get_signals"), 1)
        self.assertEqual(new_calls.count("get_events"), 1)
        self.assertEqual(new_namespace["HEALTH"], legacy_namespace["HEALTH"])

        health = new_namespace["HEALTH"]
        self.assertEqual(health["trades_closed_month"], 3)
        self.assertEqual(health["trades_closed_today"], 1)
        self.assertEqual(health["signals_month"], 3)
        self.assertEqual(health["signals_today"], 1)
        self.assertEqual(set(health["setups"]), {"TURTLE20", "TURTLE55"})
        self.assertEqual(set(health["directions"]), {"LONG", "SHORT"})
        self.assertEqual([row["name"] for row in health["ranking_month"]], ["TURTLE20", "TURTLE55"])
        self.assertEqual(health["open_runner_symbol"], "BTC/USDT:USDT")

    def test_refresh_has_no_parsed_global_cache_or_json_loads(self):
        refresh = _function("refresh_health_stats")
        called = [
            node.func.id
            for node in ast.walk(refresh)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        ]
        self.assertEqual(called.count("get_trades"), 1)
        self.assertEqual(called.count("get_signals"), 1)
        self.assertEqual(called.count("get_events"), 1)
        self.assertNotIn("json.loads", ast.get_source_segment(TURTLE_SOURCE, refresh) or "")

        global_names = {
            target.id
            for statement in TURTLE_TREE.body
            if isinstance(statement, (ast.Assign, ast.AnnAssign))
            for target in (
                statement.targets
                if isinstance(statement, ast.Assign)
                else [statement.target]
            )
            if isinstance(target, ast.Name)
        }
        suspicious = {
            name
            for name in global_names
            if "cache" in name.lower() and ("trade" in name.lower() or "signal" in name.lower())
        }
        self.assertEqual(suspicious, set())


if __name__ == "__main__":
    unittest.main()
