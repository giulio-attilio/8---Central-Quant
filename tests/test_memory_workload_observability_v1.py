from __future__ import annotations

import ast
import unittest
from pathlib import Path
from unittest.mock import patch

import memory_source_observability as observability


ROOT = Path(__file__).resolve().parents[1]
SCANNERS = {
    "bots/cobra.py": ("scanner", "COBRA"),
    "bots/donkey.py": ("scanner", "DONKEY"),
    "bots/falcon.py": ("scanner_loop", "FALCON"),
    "bots/meme.py": ("scanner", "MEME"),
    "bots/predator.py": ("scanner", "PREDATOR"),
    "bots/trendpro.py": ("scanner", "TRENDPRO"),
    "bots/turtle.py": ("scanner_loop", "TURTLE"),
}


def _function(tree: ast.Module, name: str) -> ast.FunctionDef:
    return next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    )


def _called_names(node: ast.AST) -> list[str]:
    return [
        call.func.id
        for call in ast.walk(node)
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
    ]


class MemoryWorkloadObservabilityTests(unittest.TestCase):
    def test_workload_span_tracks_only_scalar_count_and_peak(self):
        rss_values = iter((100.0, 125.0, 180.0, 140.0))
        monotonic_values = iter((10.0, 10.25))
        emitted = []
        with (
            patch.object(
                observability,
                "memory_source_current_rss_mb",
                side_effect=lambda: next(rss_values),
            ),
            patch.object(
                observability.time,
                "monotonic",
                side_effect=lambda: next(monotonic_values),
            ),
            patch.object(
                observability,
                "emit_memory_source_observation",
                side_effect=lambda event_name, **fields: emitted.append((event_name, fields)) or True,
            ),
        ):
            span = observability.start_memory_workload_span()
            self.assertEqual(
                list(observability.observe_memory_workload_items(("A", "B"), span)),
                ["A", "B"],
            )
            self.assertTrue(observability.finish_memory_workload_span(
                "SCANNER_CYCLE_MEMORY",
                span,
                bot="TURTLE",
                include_symbols_processed=True,
            ))

        self.assertEqual(span, {
            "started_at": 10.0,
            "rss_start_mb": 100.0,
            "rss_peak_mb": 180.0,
            "items_processed": 2,
        })
        self.assertEqual(emitted, [(
            "SCANNER_CYCLE_MEMORY",
            {
                "bot": "TURTLE",
                "symbols_processed": 2,
                "elapsed_ms": 250.0,
                "rss_start_mb": 100.0,
                "rss_end_mb": 140.0,
                "rss_delta_mb": 40.0,
                "rss_peak_mb": 180.0,
            },
        )])

    def test_item_observer_does_not_hide_operational_exception(self):
        class OperationalFailure(RuntimeError):
            pass

        with patch.object(observability, "memory_source_current_rss_mb", return_value=10.0):
            span = observability.start_memory_workload_span()
            with self.assertRaisesRegex(OperationalFailure, "scanner failure"):
                for symbol in observability.observe_memory_workload_items(("A", "B"), span):
                    if symbol == "B":
                        raise OperationalFailure("scanner failure")

        self.assertEqual(span["items_processed"], 2)

    def test_workload_observability_is_fail_open(self):
        span = observability.start_memory_workload_span()

        def fail_rss():
            raise RuntimeError("rss unavailable")

        with patch.object(observability, "memory_source_current_rss_mb", side_effect=fail_rss):
            self.assertEqual(
                list(observability.observe_memory_workload_items((1, 2), span)),
                [1, 2],
            )
            self.assertFalse(observability.finish_memory_workload_span(
                "SCANNER_CYCLE_MEMORY",
                span,
                bot="COBRA",
                include_symbols_processed=True,
            ))

    def test_all_scanners_have_one_aggregate_cycle_boundary_and_no_bot_imports(self):
        for relative_path, (function_name, bot) in SCANNERS.items():
            with self.subTest(relative_path=relative_path):
                source = (ROOT / relative_path).read_text(encoding="utf-8")
                tree = ast.parse(source, filename=relative_path)
                scanner = _function(tree, function_name)
                called = _called_names(scanner)

                self.assertIn("start_memory_workload_span", called)
                self.assertIn("observe_memory_workload_items", called)
                self.assertIn("finish_memory_workload_span", called)
                self.assertIn("SCANNER_CYCLE_MEMORY", source)
                self.assertIn(f'bot="{bot}"', source)

                observed_loops = [
                    node
                    for node in ast.walk(scanner)
                    if isinstance(node, ast.For)
                    and isinstance(node.iter, ast.Call)
                    and isinstance(node.iter.func, ast.Name)
                    and node.iter.func.id == "observe_memory_workload_items"
                ]
                self.assertEqual(len(observed_loops), 1)

    def test_only_turtle_and_falcon_summary_cycles_are_instrumented(self):
        for relative_path, bot in (
            ("bots/turtle.py", "TURTLE"),
            ("bots/falcon.py", "FALCON"),
        ):
            with self.subTest(relative_path=relative_path):
                source = (ROOT / relative_path).read_text(encoding="utf-8")
                tree = ast.parse(source, filename=relative_path)
                summary = _function(tree, "summary_loop")
                summary_source = ast.get_source_segment(source, summary) or ""
                called = _called_names(summary)

                self.assertIn("start_memory_workload_span", called)
                self.assertEqual(called.count("finish_memory_workload_span"), 1)
                self.assertIn("SUMMARY_CYCLE_MEMORY", summary_source)
                self.assertIn(f'bot="{bot}"', summary_source)

    def test_helper_has_no_operational_main_or_external_dependency_imports(self):
        source = (ROOT / "memory_source_observability.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }

        self.assertNotIn("main", imported)
        self.assertNotIn("pandas", imported)
        self.assertNotIn("requests", imported)
        self.assertNotIn("redis", imported)


if __name__ == "__main__":
    unittest.main()
