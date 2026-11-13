import json
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import paper_executor_integrated as paper_executor
import paper_lifecycle
import outcome_evaluator
import paper_state_storage


class PaperExecutorIntegratedIdempotencyTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.positions_file = self.root / "positions.json"
        self.seen_file = self.root / "seen.json"
        self.log_file = self.root / "paper.jsonl"
        self.patches = [
            mock.patch.object(paper_executor, "PAPER_POSITIONS_FILE", self.positions_file),
            mock.patch.object(paper_executor, "PAPER_SEEN_FILE", self.seen_file),
            mock.patch.object(paper_executor, "PAPER_LOG_FILE", self.log_file),
            mock.patch.object(paper_executor, "PAPER_EXECUTION_ENABLED", True),
            mock.patch.object(paper_executor, "REAL_EXECUTION_ENABLED", False),
            mock.patch.object(
                paper_executor,
                "_paper_persistence_guard",
                return_value={
                    "allowed": True,
                    "status": "PAPER_PERSISTENCE_READY",
                    "free_bytes": 512 * 1024 * 1024,
                    "minimum_free_bytes": paper_executor.PAPER_MIN_FREE_DISK_BYTES,
                    "error_type": None,
                },
            ),
        ]
        for patcher in self.patches:
            patcher.start()
            self.addCleanup(patcher.stop)

    @staticmethod
    def _plan(idem="paper-idempotency-test-v1"):
        return {
            "status": "READY_FOR_EXECUTION",
            "idempotency_key": idem,
            "requested_qty": 1.0,
            "capital_allocated": 100.0,
            "payload": {
                "symbol": "BTCUSDT",
                "side": "LONG",
                "entry": 100.0,
                "sl": 95.0,
                "tp50": 110.0,
                "risk_pct": 1.0,
                "bot": "local-test",
                "setup": "idempotency-regression",
            },
        }

    def _positions(self):
        if not self.positions_file.exists():
            return []
        return json.loads(self.positions_file.read_text(encoding="utf-8"))

    def _initialize_state(self):
        self.positions_file.write_text("[]", encoding="utf-8")
        self.seen_file.write_text("{}", encoding="utf-8")

    def test_health_reports_missing_state_files_separately_from_empty_files(self):
        health = paper_executor.paper_integrated_health()

        self.assertTrue(health["ok"])
        self.assertFalse(health["state_files_present"])
        self.assertEqual(health["state_files_status"], "PAPER_STATE_FILES_MISSING")
        self.assertIsNone(health["open_positions"])
        self.assertIsNone(health["total_positions"])
        self.assertFalse(health["files"]["paper_positions_present"])
        self.assertFalse(health["files"]["paper_seen_present"])

        self.positions_file.write_text("[]", encoding="utf-8")
        self.seen_file.write_text("{}", encoding="utf-8")
        health = paper_executor.paper_integrated_health()

        self.assertTrue(health["state_files_present"])
        self.assertEqual(health["state_files_status"], "PAPER_STATE_FILES_PRESENT")
        self.assertEqual(health["open_positions"], 0)
        self.assertTrue(health["state_files_valid"])

    def test_health_does_not_report_zero_for_corrupt_or_unidentified_state(self):
        self.positions_file.write_text("{invalid", encoding="utf-8")
        self.seen_file.write_text("{}", encoding="utf-8")
        health = paper_executor.paper_integrated_health()
        self.assertEqual(health["state_files_status"], "PAPER_STATE_FILES_INVALID")
        self.assertFalse(health["state_files_valid"])
        self.assertIsNone(health["open_positions"])

        self.positions_file.write_text(json.dumps([{"status": "OPEN"}]), encoding="utf-8")
        health = paper_executor.paper_integrated_health()
        self.assertEqual(health["state_files_status"], "PAPER_STATE_FILES_INVALID")
        self.assertIsNone(health["total_positions"])

    def test_open_positions_query_does_not_turn_missing_state_into_empty_positions(self):
        result = paper_executor.get_paper_integrated_open_positions()
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "PAPER_STATE_FILES_MISSING")
        self.assertIsNone(result["count"])
        self.assertIsNone(result["positions"])

    def test_missing_position_ledger_blocks_without_initializing_or_logging(self):
        self.seen_file.write_text("{}", encoding="utf-8")
        self.positions_file.unlink(missing_ok=True)

        result = paper_executor.execute_paper_from_engine({"plan": self._plan()})

        self.assertFalse(result["ok"])
        self.assertEqual(result["payload"]["status"], "PAPER_STATE_UNINITIALIZED")
        self.assertEqual(result["payload"]["errors"], ["PAPER_POSITION_LEDGER_MISSING"])
        self.assertTrue(self.seen_file.exists())
        self.assertFalse(self.positions_file.exists())
        self.assertFalse(self.log_file.exists())

    def test_missing_seen_cache_blocks_new_key_but_recovers_existing_key(self):
        position = {
            "idempotency_key": "paper-existing-key",
            "trade_id": "paper-existing-trade",
            "status": "OPEN",
            "mode": "PAPER",
            "opened_at": "2026-11-10 12:00:00",
            "symbol": "BTCUSDT",
            "side": "LONG",
            "entry": 100.0,
            "sl_initial": 95.0,
            "sl_current": 95.0,
            "tp50": 110.0,
            "exchange_executor_called": False,
            "real_exchange_order_id": None,
        }
        self.positions_file.write_text(json.dumps([position]), encoding="utf-8")

        duplicate = paper_executor.execute_paper_from_engine({
            "plan": self._plan("paper-existing-key")
        })
        self.assertFalse(duplicate["ok"])
        self.assertEqual(duplicate["payload"]["status"], "PAPER_DUPLICATE_BLOCKED")
        self.assertTrue(json.loads(self.seen_file.read_text(encoding="utf-8"))[
            "paper-existing-key"]["recovered_from_position_ledger"]
        )

        self.seen_file.unlink()
        new_key = paper_executor.execute_paper_from_engine({
            "plan": self._plan("paper-new-key")
        })
        self.assertFalse(new_key["ok"])
        self.assertEqual(new_key["payload"]["status"], "PAPER_STATE_UNINITIALIZED")
        self.assertEqual(new_key["payload"]["errors"], ["PAPER_IDEMPOTENCY_STATE_MISSING"])
        self.assertEqual(len(self._positions()), 1)
        self.assertFalse(self.seen_file.exists())

    def test_position_ledger_blocks_retry_when_seen_write_failed(self):
        self._initialize_state()
        original_write = paper_executor._write_json
        failed_seen_write = False

        def fail_seen_once(path, payload):
            nonlocal failed_seen_write
            if Path(path) == self.seen_file and not failed_seen_write:
                failed_seen_write = True
                return False
            return original_write(path, payload)

        with mock.patch.object(paper_executor, "_write_json", side_effect=fail_seen_once):
            first = paper_executor.execute_paper_from_engine({"plan": self._plan()})
            retry = paper_executor.execute_paper_from_engine({"plan": self._plan()})

        self.assertTrue(first["ok"])
        self.assertIn("marcador de idempotência pendente", first["payload"]["warnings"][-1])
        self.assertFalse(retry["ok"])
        self.assertEqual(retry["payload"]["status"], "PAPER_DUPLICATE_BLOCKED")
        self.assertEqual(len(self._positions()), 1)
        seen = json.loads(self.seen_file.read_text(encoding="utf-8"))
        self.assertTrue(seen["paper-idempotency-test-v1"]["recovered_from_position_ledger"])

    def test_failed_position_write_does_not_consume_idempotency_key(self):
        self._initialize_state()
        original_write = paper_executor._write_json
        failed_position_write = False

        def fail_position_once(path, payload):
            nonlocal failed_position_write
            if Path(path) == self.positions_file and not failed_position_write:
                failed_position_write = True
                return False
            return original_write(path, payload)

        with mock.patch.object(paper_executor, "_write_json", side_effect=fail_position_once):
            first = paper_executor.execute_paper_from_engine({"plan": self._plan()})
            retry = paper_executor.execute_paper_from_engine({"plan": self._plan()})

        self.assertFalse(first["ok"])
        self.assertEqual(first["payload"]["status"], "PAPER_STATE_PERSISTENCE_FAILED")
        self.assertTrue(retry["ok"])
        self.assertEqual(len(self._positions()), 1)

    def test_concurrent_same_idempotency_key_opens_one_paper_position(self):
        self._initialize_state()
        barrier = threading.Barrier(8)

        def execute(_index):
            barrier.wait(timeout=3)
            return paper_executor.execute_paper_from_engine({"plan": self._plan("paper-concurrent-v1")})

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(execute, range(8)))

        self.assertEqual(sum(bool(result["ok"]) for result in results), 1)
        self.assertEqual(sum(result["payload"]["status"] == "PAPER_DUPLICATE_BLOCKED" for result in results), 7)
        self.assertEqual(len(self._positions()), 1)

    def test_corrupt_position_state_fails_closed(self):
        self.seen_file.write_text("{}", encoding="utf-8")
        self.positions_file.write_text("{invalid", encoding="utf-8")

        result = paper_executor.execute_paper_from_engine({"plan": self._plan()})

        self.assertFalse(result["ok"])
        self.assertEqual(result["payload"]["status"], "PAPER_STATE_INVALID")
        self.assertEqual(self.positions_file.read_text(encoding="utf-8"), "{invalid")
        self.assertEqual(self.seen_file.read_text(encoding="utf-8"), "{}")

    def test_position_without_idempotency_identity_fails_closed(self):
        self.seen_file.write_text("{}", encoding="utf-8")
        self.positions_file.write_text(json.dumps([{"status": "OPEN"}]), encoding="utf-8")

        result = paper_executor.execute_paper_from_engine({"plan": self._plan()})

        self.assertFalse(result["ok"])
        self.assertEqual(result["payload"]["status"], "PAPER_STATE_INVALID")
        self.assertEqual(json.loads(self.positions_file.read_text(encoding="utf-8")), [{"status": "OPEN"}])

    def test_unknown_position_status_fails_closed_in_health_and_execution(self):
        self._initialize_state()
        opened = paper_executor.execute_paper_from_engine({"plan": self._plan("paper-status-v1")})
        self.assertTrue(opened["ok"])
        positions = self._positions()
        positions[0]["status"] = "UNKNOWN"
        self.positions_file.write_text(json.dumps(positions), encoding="utf-8")

        health = paper_executor.paper_integrated_health()
        result = paper_executor.execute_paper_from_engine({"plan": self._plan("paper-next-v1")})

        self.assertEqual(health["state_files_status"], "PAPER_STATE_FILES_INVALID")
        self.assertIsNone(health["open_positions"])
        self.assertFalse(result["ok"])
        self.assertEqual(result["payload"]["status"], "PAPER_STATE_INVALID")
        self.assertEqual(len(self._positions()), 1)

    def test_noncanonical_persisted_idempotency_key_fails_closed(self):
        self._initialize_state()
        opened = paper_executor.execute_paper_from_engine({"plan": self._plan("paper-key-v1")})
        self.assertTrue(opened["ok"])
        positions = self._positions()
        positions[0]["idempotency_key"] = " paper-key-v1 "
        self.positions_file.write_text(json.dumps(positions), encoding="utf-8")

        result = paper_executor.execute_paper_from_engine({"plan": self._plan("paper-next-v1")})

        self.assertFalse(result["ok"])
        self.assertEqual(result["payload"]["status"], "PAPER_STATE_INVALID")

    def test_non_finite_persisted_entry_or_stop_fails_closed(self):
        for field in ("entry", "sl_initial", "sl_current"):
            with self.subTest(field=field):
                self._initialize_state()
                opened = paper_executor.execute_paper_from_engine({"plan": self._plan(f"paper-ledger-{field}")})
                self.assertTrue(opened["ok"])
                positions = self._positions()
                positions[0][field] = float("nan")
                self.positions_file.write_text(json.dumps(positions), encoding="utf-8")

                health = paper_executor.paper_integrated_health()
                result = paper_executor.execute_paper_from_engine({"plan": self._plan(f"paper-next-{field}")})

                self.assertEqual(health["state_files_status"], "PAPER_STATE_FILES_INVALID")
                self.assertIsNone(health["open_positions"])
                self.assertFalse(result["ok"])
                self.assertEqual(result["payload"]["status"], "PAPER_STATE_INVALID")
                self.assertEqual(len(self._positions()), 1)

    def test_non_finite_entry_and_stop_are_rejected(self):
        for field in ("entry", "sl"):
            for value in (float("nan"), float("inf"), float("-inf")):
                with self.subTest(field=field, value=value):
                    plan = self._plan(f"paper-nonfinite-{field}")
                    plan["payload"][field] = value
                    validation = paper_executor.validate_paper_plan(plan)
                    self.assertFalse(validation["ok"])
                    self.assertIsNone(validation["normalized"][field])

    def test_safe_float_uses_default_for_non_finite_values(self):
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=value):
                self.assertEqual(paper_executor._safe_float(value, 0.0), 0.0)

    def test_non_string_idempotency_key_is_rejected_before_state_access(self):
        plan = self._plan()
        plan["idempotency_key"] = {"not": "hashable"}

        result = paper_executor.execute_paper_from_engine({"plan": plan})

        self.assertFalse(result["ok"])
        self.assertEqual(result["payload"]["status"], "PAPER_INVALID_PLAN")
        self.assertFalse(self.positions_file.exists())
        self.assertFalse(self.seen_file.exists())

    def test_low_persistent_disk_blocks_integrated_paper_without_writing_state_or_log(self):
        with mock.patch.object(
            paper_executor,
            "_paper_persistence_guard",
            return_value={
                "allowed": False,
                "status": "PAPER_PERSISTENCE_BLOCKED",
                "free_bytes": 63 * 1024 * 1024,
                "minimum_free_bytes": paper_executor.PAPER_MIN_FREE_DISK_BYTES,
                "error_type": None,
            },
        ):
            result = paper_executor.execute_paper_from_engine({"plan": self._plan()})

        self.assertFalse(result["ok"])
        self.assertEqual(result["payload"]["status"], "PAPER_PERSISTENCE_BLOCKED")
        self.assertEqual(result["payload"]["persistence"]["free_bytes"], 63 * 1024 * 1024)
        self.assertFalse(result["payload"]["exchange_executor_called"])
        self.assertFalse(self.positions_file.exists())
        self.assertFalse(self.seen_file.exists())
        self.assertFalse(self.log_file.exists())

    def test_disk_drop_before_position_write_blocks_without_committing_position(self):
        self._initialize_state()
        ready = {
            "allowed": True,
            "status": "PAPER_PERSISTENCE_READY",
            "free_bytes": 512 * 1024 * 1024,
            "minimum_free_bytes": paper_executor.PAPER_MIN_FREE_DISK_BYTES,
            "error_type": None,
        }
        low = {
            "allowed": False,
            "status": "PAPER_PERSISTENCE_BLOCKED",
            "free_bytes": 63 * 1024 * 1024,
            "minimum_free_bytes": paper_executor.PAPER_MIN_FREE_DISK_BYTES,
            "error_type": None,
        }
        with mock.patch.object(
            paper_executor,
            "_paper_persistence_guard",
            side_effect=[ready, low],
        ):
            result = paper_executor.execute_paper_from_engine({"plan": self._plan()})

        self.assertFalse(result["ok"])
        self.assertEqual(result["payload"]["status"], "PAPER_PERSISTENCE_BLOCKED")
        self.assertEqual(result["payload"]["persistence"]["free_bytes"], 63 * 1024 * 1024)
        self.assertEqual(self._positions(), [])
        self.assertEqual(json.loads(self.seen_file.read_text(encoding="utf-8")), {})
        self.assertFalse(self.log_file.exists())

    def test_persistent_disk_measurement_error_blocks_integrated_paper(self):
        self.patches[-1].stop()
        with mock.patch.object(
            paper_executor.shutil,
            "disk_usage",
            side_effect=OSError("disk unavailable"),
        ):
            result = paper_executor._paper_persistence_guard()

        self.assertFalse(result["allowed"])
        self.assertEqual(result["status"], "PAPER_PERSISTENCE_BLOCKED")
        self.assertIsNone(result["free_bytes"])
        self.assertEqual(result["error_type"], "OSError")

    def test_persistent_disk_measurement_accepts_space_at_minimum(self):
        self.patches[-1].stop()
        usage = type("Usage", (), {"free": paper_executor.PAPER_MIN_FREE_DISK_BYTES})()
        with mock.patch.object(paper_executor.shutil, "disk_usage", return_value=usage):
            result = paper_executor._paper_persistence_guard()

        self.assertTrue(result["allowed"])
        self.assertEqual(result["status"], "PAPER_PERSISTENCE_READY")
        self.assertEqual(result["free_bytes"], paper_executor.PAPER_MIN_FREE_DISK_BYTES)

    def test_atomic_state_write_fsyncs_file_replaces_then_syncs_directory(self):
        target = self.root / "durable.json"
        events = []
        original_fsync = paper_executor.os.fsync
        original_replace = paper_executor.os.replace

        def record_fsync(fd):
            events.append("file_fsync")
            return original_fsync(fd)

        def record_replace(source, destination):
            events.append("replace")
            return original_replace(source, destination)

        with (
            mock.patch.object(paper_executor.os, "fsync", side_effect=record_fsync),
            mock.patch.object(paper_executor.os, "replace", side_effect=record_replace),
            mock.patch.object(
                paper_state_storage,
                "_fsync_directory",
                side_effect=lambda _directory: events.append("directory_fsync"),
            ),
        ):
            persisted = paper_executor._write_json(target, {"value": "new"})

        self.assertTrue(persisted)
        self.assertEqual(events, ["file_fsync", "replace", "directory_fsync"])
        self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"value": "new"})
        self.assertEqual(list(self.root.glob(".*.tmp")), [])

    def test_file_fsync_failure_preserves_existing_state(self):
        target = self.root / "durable.json"
        target.write_text('{"value":"old"}', encoding="utf-8")

        with mock.patch.object(paper_executor.os, "fsync", side_effect=OSError("fsync failed")):
            persisted = paper_executor._write_json(target, {"value": "new"})

        self.assertFalse(persisted)
        self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"value": "old"})
        self.assertEqual(list(self.root.glob(".*.tmp")), [])

    def test_directory_fsync_failure_reports_ambiguous_persistence(self):
        target = self.root / "durable.json"

        with mock.patch.object(
            paper_state_storage,
            "_fsync_directory",
            side_effect=OSError("directory fsync failed"),
        ):
            persisted = paper_executor._write_json(target, {"value": "new"})

        self.assertFalse(persisted)
        # Replace already occurred: caller must fail closed, and retries must
        # discover the committed idempotency key in the canonical ledger.
        self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"value": "new"})

    def test_directory_fsync_closes_directory_descriptor_after_failure(self):
        with (
            mock.patch.object(paper_state_storage.os, "name", "posix"),
            mock.patch.object(paper_state_storage.os, "open", return_value=37) as open_directory,
            mock.patch.object(paper_state_storage.os, "fsync", side_effect=OSError("sync failed")),
            mock.patch.object(paper_state_storage.os, "close") as close_directory,
        ):
            with self.assertRaises(OSError):
                paper_state_storage._fsync_directory(self.root)

        open_directory.assert_called_once_with(
            str(self.root),
            paper_state_storage.os.O_RDONLY | getattr(paper_state_storage.os, "O_DIRECTORY", 0),
        )
        close_directory.assert_called_once_with(37)

    def test_all_paper_position_writers_share_the_same_process_lock(self):
        self.assertIs(paper_executor._PAPER_EXECUTION_LOCK, paper_state_storage.PAPER_STATE_LOCK)
        self.assertIs(paper_lifecycle._PAPER_LIFECYCLE_LOCK, paper_state_storage.PAPER_STATE_LOCK)
        self.assertIs(outcome_evaluator.PAPER_STATE_LOCK, paper_state_storage.PAPER_STATE_LOCK)

    def test_lifecycle_update_waits_for_concurrent_paper_entry_and_closes_new_position(self):
        self._initialize_state()
        paper_lifecycle.PAPER_POSITIONS_FILE = self.positions_file
        paper_lifecycle.PAPER_LIFECYCLE_LOG_FILE = self.root / "lifecycle.jsonl"
        paper_lifecycle.PAPER_LIFECYCLE_HISTORY_ENABLED = False
        paper_lifecycle.PAPER_LIFECYCLE_ENABLED = True
        position_read = threading.Event()
        release_entry = threading.Event()
        lifecycle_requested_lock = threading.Event()
        original_read = paper_executor._read_state_json
        shared_lock = paper_state_storage.PAPER_STATE_LOCK

        def pause_after_positions_read(path, default):
            value = original_read(path, default)
            if Path(path) == self.positions_file:
                position_read.set()
                if not release_entry.wait(timeout=5):
                    raise TimeoutError("test did not release paper entry")
            return value

        class ObservedSharedLock:
            def __enter__(self):
                lifecycle_requested_lock.set()
                shared_lock.acquire()
                return self

            def __exit__(self, _exc_type, _exc, _tb):
                shared_lock.release()

        with (
            mock.patch.object(paper_executor, "_read_state_json", side_effect=pause_after_positions_read),
            mock.patch.object(paper_lifecycle, "_PAPER_LIFECYCLE_LOCK", ObservedSharedLock()),
        ):
            with ThreadPoolExecutor(max_workers=2) as pool:
                entry_future = pool.submit(
                    paper_executor.execute_paper_from_engine,
                    {"plan": self._plan("paper-cross-writer-v1")},
                )
                self.assertTrue(position_read.wait(timeout=3))
                lifecycle_future = pool.submit(
                    paper_lifecycle.update_paper_position_price,
                    symbol="BTCUSDT",
                    price=90.0,
                    close=True,
                    close_reason="TEST_CLOSE",
                )
                self.assertTrue(lifecycle_requested_lock.wait(timeout=3))
                release_entry.set()
                entry_result = entry_future.result(timeout=5)
                lifecycle_result = lifecycle_future.result(timeout=5)

        self.assertTrue(entry_result["ok"])
        self.assertTrue(lifecycle_result["ok"])
        positions = self._positions()
        self.assertEqual(len(positions), 1)
        self.assertEqual(positions[0]["status"], "CLOSED")

    def test_outcome_read_modify_write_cannot_overwrite_concurrent_lifecycle_close(self):
        self._initialize_state()
        initial = paper_executor.execute_paper_from_engine(
            {"plan": self._plan("paper-outcome-lifecycle-race-v1")}
        )
        self.assertTrue(initial["ok"])

        outcome_evaluator.PAPER_POSITIONS_FILE = self.positions_file
        outcome_evaluator.OUTCOME_STATS_FILE = self.root / "outcome_stats.json"
        outcome_evaluator.OUTCOME_LOG_FILE = self.root / "outcome.jsonl"
        outcome_evaluator.OUTCOME_EVALUATOR_ENABLED = True
        paper_lifecycle.PAPER_POSITIONS_FILE = self.positions_file
        paper_lifecycle.PAPER_LIFECYCLE_LOG_FILE = self.root / "lifecycle.jsonl"
        paper_lifecycle.PAPER_LIFECYCLE_HISTORY_ENABLED = False
        paper_lifecycle.PAPER_LIFECYCLE_ENABLED = True

        position_read = threading.Event()
        release_evaluation = threading.Event()
        lifecycle_requested_lock = threading.Event()
        original_read = outcome_evaluator._read_state_json
        shared_lock = paper_state_storage.PAPER_STATE_LOCK

        def pause_after_positions_read(path, default):
            value = original_read(path, default)
            if Path(path) == self.positions_file:
                position_read.set()
                if not release_evaluation.wait(timeout=5):
                    raise TimeoutError("test did not release outcome evaluation")
            return value

        class ObservedSharedLock:
            def __enter__(self):
                lifecycle_requested_lock.set()
                shared_lock.acquire()
                return self

            def __exit__(self, _exc_type, _exc, _tb):
                shared_lock.release()

        with (
            mock.patch.object(outcome_evaluator, "_read_state_json", side_effect=pause_after_positions_read),
            mock.patch.object(paper_lifecycle, "_PAPER_LIFECYCLE_LOCK", ObservedSharedLock()),
        ):
            with ThreadPoolExecutor(max_workers=2) as pool:
                evaluation_future = pool.submit(outcome_evaluator.evaluate_closed_paper_trades)
                self.assertTrue(position_read.wait(timeout=3))
                lifecycle_future = pool.submit(
                    paper_lifecycle.update_paper_position_price,
                    symbol="BTCUSDT",
                    price=90.0,
                    close=True,
                    close_reason="TEST_CLOSE",
                )
                self.assertTrue(lifecycle_requested_lock.wait(timeout=3))
                release_evaluation.set()
                evaluation_result = evaluation_future.result(timeout=5)
                lifecycle_result = lifecycle_future.result(timeout=5)

        self.assertTrue(evaluation_result["ok"])
        self.assertEqual(evaluation_result["evaluated_count"], 0)
        self.assertTrue(lifecycle_result["ok"])
        positions = self._positions()
        self.assertEqual(len(positions), 1)
        self.assertEqual(positions[0]["status"], "CLOSED")


if __name__ == "__main__":
    unittest.main()
