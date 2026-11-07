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

    def test_position_ledger_blocks_retry_when_seen_write_failed(self):
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
        self.positions_file.write_text("{invalid", encoding="utf-8")

        result = paper_executor.execute_paper_from_engine({"plan": self._plan()})

        self.assertFalse(result["ok"])
        self.assertEqual(result["payload"]["status"], "PAPER_STATE_INVALID")
        self.assertEqual(self.positions_file.read_text(encoding="utf-8"), "{invalid")
        self.assertFalse(self.seen_file.exists())

    def test_non_string_idempotency_key_is_rejected_before_state_access(self):
        plan = self._plan()
        plan["idempotency_key"] = {"not": "hashable"}

        result = paper_executor.execute_paper_from_engine({"plan": plan})

        self.assertFalse(result["ok"])
        self.assertEqual(result["payload"]["status"], "PAPER_INVALID_PLAN")
        self.assertFalse(self.positions_file.exists())
        self.assertFalse(self.seen_file.exists())


if __name__ == "__main__":
    unittest.main()
