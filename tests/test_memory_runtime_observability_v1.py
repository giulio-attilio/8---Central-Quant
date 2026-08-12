import ast
import copy
import gc
import io
import os
import threading
import unittest
from collections import deque
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN_PATH = ROOT / "main.py"
MAIN_SOURCE = MAIN_PATH.read_text(encoding="utf-8")
MAIN_TREE = ast.parse(MAIN_SOURCE, filename=str(MAIN_PATH))


def _function_node(name):
    return next(
        node
        for node in MAIN_TREE.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    )


def _compile_function(name, namespace):
    node = copy.deepcopy(_function_node(name))
    module = ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[]))
    exec(compile(module, str(MAIN_PATH), "exec"), namespace)
    return namespace[name]


class MemoryRuntimeObservabilityV1Tests(unittest.TestCase):
    def _snapshot_namespace(self, include_boot_id=True):
        class FixedDatetime:
            @classmethod
            def now(cls, tz=None):
                return datetime(2026, 8, 12, 9, 1, 23, 456000, tzinfo=tz)

        namespace = {
            "os": os,
            "threading": threading,
            "gc": gc,
            "datetime": FixedDatetime,
            "TIMEZONE_BR": timezone(timedelta(hours=-3)),
            "current_rss_mb": lambda: 875.35,
            "memory_usage_pct": lambda rss: 42.74,
            "data_hora_sp_str": lambda: "2026-08-12 12:00:00",
            "MEMORY_LIMIT_MB": 2048.0,
            "MEMORY_HISTORY": deque(maxlen=40),
            "MEMORY_LOCK": threading.Lock(),
            "LOADED_BOTS": {},
        }
        if include_boot_id:
            namespace["CENTRAL_RUNTIME_BOOT_ID"] = "boot-test-1234"
        return namespace

    def test_snapshot_log_contains_process_runtime_and_monitor_sequence(self):
        namespace = self._snapshot_namespace()
        memory_snapshot = _compile_function("memory_snapshot", namespace)

        output = io.StringIO()
        with redirect_stdout(output):
            snapshot = memory_snapshot(
                "memory_loop",
                extra={"seq": 7},
                store=True,
                print_log=True,
            )

        self.assertEqual(snapshot["pid"], os.getpid())
        self.assertEqual(snapshot["ppid"], os.getppid())
        self.assertEqual(snapshot["thread"], threading.current_thread().name)
        self.assertEqual(snapshot["boot_id"], "boot-test-1234")
        self.assertEqual(snapshot["sampled_at"], "2026-08-12T09:01:23.456-03:00")
        self.assertEqual(snapshot["seq"], 7)
        rendered = output.getvalue()
        self.assertIn(
            "MEMORY memory_loop | sampled_at=2026-08-12T09:01:23.456-03:00 | "
            "rss=875.35 MB | usage=42.74%",
            rendered,
        )
        self.assertIn(f"pid={os.getpid()} | ppid={os.getppid()}", rendered)
        self.assertIn("thread=MainThread | boot_id=boot-test-1234 | seq=7", rendered)

    def test_snapshot_has_safe_boot_id_fallback_for_isolated_harness(self):
        namespace = self._snapshot_namespace(include_boot_id=False)
        memory_snapshot = _compile_function("memory_snapshot", namespace)

        snapshot = memory_snapshot("isolated", store=False, print_log=False)

        self.assertEqual(snapshot["boot_id"], "unknown")

    def test_monitor_sequence_is_local_and_increments_per_successful_sample(self):
        class StopMonitor(BaseException):
            pass

        samples = []

        def memory_snapshot(label, extra=None, store=True, print_log=False):
            if len(samples) == 2:
                raise StopMonitor()
            samples.append((label, dict(extra or {}), store, print_log))
            return {"rss_mb": 0}

        class FakeTime:
            @staticmethod
            def sleep(_seconds):
                return None

        namespace = {
            "memory_snapshot": memory_snapshot,
            "MEMORY_GC_THRESHOLD_MB": 380,
            "MEMORY_LOG_INTERVAL_SECONDS": 300,
            "force_gc_if_needed": lambda _label: None,
            "time": FakeTime(),
        }
        memory_monitor_loop = _compile_function("memory_monitor_loop", namespace)

        with self.assertRaises(StopMonitor):
            memory_monitor_loop()

        self.assertEqual([sample[1]["seq"] for sample in samples], [1, 2])
        self.assertTrue(all(sample[0] == "memory_loop" for sample in samples))
        self.assertTrue(all(sample[2] is True and sample[3] is True for sample in samples))

    def test_force_gc_logs_elapsed_and_rss_delta_without_changing_gc_decision(self):
        snapshots = []
        sleep_calls = []
        trim_calls = []

        def memory_snapshot(label, extra=None, store=True, print_log=False):
            rss = 900.0 if label.endswith("_before_gc") else 725.25
            snapshot = {
                "label": label,
                "sampled_at": "2026-08-12T09:02:03.456-03:00",
                "rss_mb": rss,
                "pid": 67,
                "ppid": 1,
                "thread": "central-memory-monitor",
                "boot_id": "boot-test-1234",
            }
            snapshot.update(dict(extra or {}))
            snapshots.append(snapshot)
            return snapshot

        class FakeGc:
            @staticmethod
            def collect():
                return 13

        class FakeTime:
            monotonic_values = iter((100.0, 100.125))

            @classmethod
            def monotonic(cls):
                return next(cls.monotonic_values)

            @staticmethod
            def sleep(seconds):
                sleep_calls.append(seconds)

        namespace = {
            "memory_snapshot": memory_snapshot,
            "MEMORY_GC_THRESHOLD_MB": 380,
            "gc": FakeGc(),
            "time": FakeTime(),
            "malloc_trim_safe": lambda: trim_calls.append(True),
        }
        force_gc_if_needed = _compile_function("force_gc_if_needed", namespace)

        output = io.StringIO()
        with redirect_stdout(output):
            before, after = force_gc_if_needed("memory_loop")

        self.assertEqual(before["rss_mb"], 900.0)
        self.assertEqual(after["rss_mb"], 725.25)
        self.assertEqual(after["gc_elapsed_ms"], 125.0)
        self.assertEqual(after["rss_before_gc_mb"], 900.0)
        self.assertEqual(after["rss_after_gc_mb"], 725.25)
        self.assertEqual(after["rss_freed_mb"], 174.75)
        self.assertEqual(sleep_calls, [0.05])
        self.assertEqual(trim_calls, [True])
        self.assertEqual(len(snapshots), 2)
        rendered = output.getvalue()
        self.assertIn("MEMORY GC | reason=memory_loop", rendered)
        self.assertIn("freed_mb=174.75 | elapsed_ms=125.0", rendered)
        self.assertIn("pid=67 | ppid=1 | thread=central-memory-monitor", rendered)

    def test_memory_logs_request_immediate_flush(self):
        for function_name in ("memory_snapshot", "force_gc_if_needed"):
            function = _function_node(function_name)
            print_calls = [
                call
                for call in ast.walk(function)
                if isinstance(call, ast.Call)
                and isinstance(call.func, ast.Name)
                and call.func.id == "print"
            ]
            self.assertTrue(print_calls)
            for call in print_calls:
                keywords = {keyword.arg: keyword.value for keyword in call.keywords}
                flush = keywords.get("flush")
                self.assertIsInstance(flush, ast.Constant)
                self.assertIs(flush.value, True)

    def test_boot_id_and_memory_monitor_thread_name_are_declared_once(self):
        self.assertEqual(
            MAIN_SOURCE.count("CENTRAL_RUNTIME_BOOT_ID = uuid.uuid4().hex"),
            1,
        )
        startup = _function_node("start_central_runtime_once")
        monitor_thread_calls = []
        for call in (node for node in ast.walk(startup) if isinstance(node, ast.Call)):
            if not isinstance(call.func, ast.Attribute) or call.func.attr != "Thread":
                continue
            keywords = {keyword.arg: keyword.value for keyword in call.keywords}
            target = keywords.get("target")
            if isinstance(target, ast.Name) and target.id == "memory_monitor_loop":
                monitor_thread_calls.append(keywords)

        self.assertEqual(len(monitor_thread_calls), 1)
        name = monitor_thread_calls[0].get("name")
        self.assertIsInstance(name, ast.Constant)
        self.assertEqual(name.value, "central-memory-monitor")


if __name__ == "__main__":
    unittest.main()
