from __future__ import annotations

import ast
import unittest
from pathlib import Path
from unittest.mock import patch

import memory_source_observability as observability


ROOT = Path(__file__).resolve().parents[1]
TURTLE_PATH = ROOT / "bots" / "turtle.py"


def _refresh_node() -> ast.FunctionDef:
    source = TURTLE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(TURTLE_PATH))
    return next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "refresh_health_stats"
    )


def _load_refresh(namespace: dict) -> object:
    module = ast.Module(body=[_refresh_node()], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, str(TURTLE_PATH), "exec"), namespace)
    return namespace["refresh_health_stats"]


def _stats() -> dict:
    return {
        "mfe_avg_pct": 0.0,
        "mae_avg_pct": 0.0,
        "mfe_avg_r": 0.0,
        "mae_avg_r": 0.0,
        "giveback_avg_pct": 0.0,
        "giveback_avg_r": 0.0,
        "expectancy_r": 0.0,
        "profit_factor_pct": 0.0,
        "profit_factor_r": 0.0,
        "trend_capture_pct": 0.0,
        "top_mfe": [],
        "runners_3r": 0,
        "runners_5r": 0,
        "runners_10r": 0,
    }


def _namespace(calls: list, *, real_observability: bool = False) -> dict:
    month_trades = [{"setup": "TURTLE20", "side": "LONG"}] * 2
    month_signals = [{"setup": "TURTLE20", "side": "LONG"}] * 3
    today_trades = [{"setup": "TURTLE55", "side": "SHORT"}]
    today_signals = [
        {"setup": "TURTLE20", "side": "LONG"},
        {"setup": "TURTLE55", "side": "SHORT"},
    ]
    events = [
        {"created_at": "12/08/2026 10:00", "event_type": "TP50"},
        {"created_at": "11/08/2026 10:00", "event_type": "STOP"},
    ]

    def loaded(name, value):
        def load():
            calls.append(name)
            return value
        return load

    def calc_stats(_trades):
        calls.append("calc_stats")
        return _stats()

    namespace = {
        "HEALTH": {},
        "next_memory_observation_cycle_id": lambda prefix: calls.append("cycle_id") or "cycle-17",
        "start_memory_workload_span": lambda: calls.append("load_start") or {
            "started_at": 1.0,
            "rss_start_mb": 100.0,
            "rss_peak_mb": 100.0,
            "items_processed": 0,
        },
        "get_trades": loaded("get_trades", month_trades + today_trades),
        "get_signals": loaded("get_signals", month_signals + today_signals),
        "get_events": loaded("get_events", events),
        "_trades_month_from_rows": lambda _rows, _key: month_trades,
        "_signals_month_from_rows": lambda _rows, _key: month_signals,
        "_trades_today_from_rows": lambda _rows, _key: today_trades,
        "_signals_today_from_rows": lambda _rows, _key: today_signals,
        "month_key_br": lambda: "08/2026",
        "date_key_br": lambda: "12/08/2026",
        "calc_stats": calc_stats,
        "slim_stats": lambda stats: dict(stats),
        "funnel_snapshot": lambda: calls.append("funnel_snapshot") or {},
        "get_open_runner": lambda: calls.append("get_open_runner") or None,
        "safe_float": lambda value: float(value or 0.0),
        "split_by_setup": lambda _items: {"TURTLE20": [], "TURTLE55": []},
        "split_by_direction": lambda _items: {"LONG": [], "SHORT": []},
        "build_ranking_month": lambda _items: calls.append("ranking") or [],
        "data_hora_sp_str": lambda: calls.append("last_summary_run") or "12/08/2026 10:00",
    }

    if real_observability:
        namespace.update({
            "transition_memory_phase_observation": observability.transition_memory_phase_observation,
            "finish_memory_phase_observation": observability.finish_memory_phase_observation,
        })
    else:
        def transition(event_name, span, **fields):
            calls.append(("load_observation", event_name, span, fields))
            return {
                "started_at": 2.0,
                "rss_start_mb": 150.0,
                "rss_peak_mb": 150.0,
                "items_processed": 0,
            }

        def finish(event_name, span, **fields):
            calls.append(("analytics_observation", event_name, span, fields))
            return True

        namespace.update({
            "transition_memory_phase_observation": transition,
            "finish_memory_phase_observation": finish,
        })
    return namespace


class TurtleSummaryMemoryPhaseObservabilityTests(unittest.TestCase):
    def test_refresh_preserves_exact_functional_loads_and_phase_order(self):
        calls = []
        namespace = _namespace(calls)
        refresh = _load_refresh(namespace)

        self.assertIsNone(refresh())

        for name in ("get_trades", "get_signals", "get_events"):
            self.assertEqual(calls.count(name), 1)
        load_event = next(item for item in calls if isinstance(item, tuple) and item[0] == "load_observation")
        analytics_event = next(item for item in calls if isinstance(item, tuple) and item[0] == "analytics_observation")
        self.assertLess(calls.index("get_events"), calls.index(load_event))
        self.assertLess(calls.index(load_event), calls.index("calc_stats"))
        self.assertLess(calls.index("last_summary_run"), calls.index(analytics_event))

        self.assertEqual(load_event[1], "TURTLE_SUMMARY_LOAD_MEMORY")
        self.assertEqual(load_event[3], {
            "cycle_id": "cycle-17",
            "month_trades_count": 2,
            "month_signals_count": 3,
            "today_trades_count": 1,
            "today_signals_count": 2,
            "today_events_count": 1,
        })
        self.assertEqual(analytics_event[1], "TURTLE_SUMMARY_ANALYTICS_MEMORY")
        self.assertEqual(analytics_event[3], {
            "cycle_id": "cycle-17",
            "setup_count": 2,
            "direction_count": 2,
        })
        self.assertTrue(all(
            value is None or isinstance(value, (str, int, float, bool))
            for value in (*load_event[3].values(), *analytics_event[3].values())
        ))

    def test_transition_reuses_one_exact_boundary_for_both_phases(self):
        emitted = []
        rss_values = iter((100.0, 150.0, 175.0))
        monotonic_values = iter((1.0, 2.0, 3.0))
        with (
            patch.object(observability, "memory_source_current_rss_mb", side_effect=lambda: next(rss_values)),
            patch.object(observability.time, "monotonic", side_effect=lambda: next(monotonic_values)),
            patch.object(
                observability,
                "emit_memory_source_observation",
                side_effect=lambda event_name, **fields: emitted.append((event_name, fields)) or True,
            ),
        ):
            load_span = observability.start_memory_workload_span()
            analytics_span = observability.transition_memory_phase_observation(
                "TURTLE_SUMMARY_LOAD_MEMORY",
                load_span,
                cycle_id="cycle-18",
                month_trades_count=2,
            )
            observability.finish_memory_phase_observation(
                "TURTLE_SUMMARY_ANALYTICS_MEMORY",
                analytics_span,
                cycle_id="cycle-18",
                setup_count=2,
            )

        self.assertEqual(analytics_span["rss_start_mb"], 150.0)
        self.assertEqual(analytics_span["started_at"], 2.0)
        self.assertEqual(emitted[0][1]["rss_end_mb"], 150.0)
        self.assertEqual(emitted[1][1]["rss_start_mb"], 150.0)
        self.assertEqual(emitted[0][1]["cycle_id"], emitted[1][1]["cycle_id"])

    def test_logger_failure_is_fail_open_for_refresh(self):
        calls = []
        namespace = _namespace(calls, real_observability=True)
        refresh = _load_refresh(namespace)

        with patch.object(
            observability,
            "emit_memory_source_observation",
            side_effect=RuntimeError("logger unavailable"),
        ):
            self.assertIsNone(refresh())

        self.assertEqual(namespace["HEALTH"]["last_summary_run"], "12/08/2026 10:00")

    def test_ast_has_only_existing_load_calls_and_no_main_import(self):
        refresh = _refresh_node()
        called_names = [
            node.func.id
            for node in ast.walk(refresh)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        ]
        for name in ("get_trades", "get_signals", "get_events"):
            self.assertEqual(called_names.count(name), 1)
        for name in ("trades_month", "signals_month", "trades_today", "signals_today"):
            self.assertEqual(called_names.count(name), 0)

        helper_source = (ROOT / "memory_source_observability.py").read_text(encoding="utf-8")
        helper_tree = ast.parse(helper_source)
        imported = {
            alias.name
            for node in ast.walk(helper_tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        self.assertNotIn("main", imported)
        self.assertNotIn("redis", imported)
        self.assertNotIn("pandas", imported)


if __name__ == "__main__":
    unittest.main()
