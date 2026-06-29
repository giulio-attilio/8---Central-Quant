import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import event_bus
import history_manager


class HistoryEventBusSmokeTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.history_dir = self.root / "history"
        self.history_dir.mkdir(parents=True, exist_ok=True)
        self.event_dir = self.root / "eventbus"
        self.event_dir.mkdir(parents=True, exist_ok=True)

        self.patches = [
            mock.patch.object(history_manager, "DATA_DIR", self.history_dir),
            mock.patch.object(history_manager, "HISTORY_EVENTS_FILE", self.history_dir / "history_events.jsonl"),
            mock.patch.object(history_manager, "DECISION_LOG_FILE", self.history_dir / "decision_log.jsonl"),
            mock.patch.object(history_manager, "TIMELINE_LOG_FILE", self.history_dir / "timeline.jsonl"),
            mock.patch.object(history_manager, "HISTORY_EXPORT_FILE", self.history_dir / "history_export.json"),
            mock.patch.object(history_manager, "HISTORY_SEEN_FILE", self.history_dir / "history_seen.json"),
            mock.patch.object(event_bus, "DATA_DIR", self.event_dir),
            mock.patch.object(event_bus, "EVENT_BUS_LOG_FILE", self.event_dir / "event_bus.jsonl"),
            mock.patch.object(event_bus, "EVENT_BUS_SEEN_FILE", self.event_dir / "event_bus_seen.json"),
            mock.patch.object(event_bus, "history_manager", history_manager),
        ]
        for patcher in self.patches:
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_log_event_and_status(self):
        result = history_manager.log_event(
            "TEST_EVENT",
            {"symbol": "BTCUSDT", "side": "buy", "trade_id": "T-1"},
            source="unit-test",
            trade_id="T-1",
        )
        self.assertTrue(result["ok"])
        self.assertFalse(result["dedup"])
        self.assertEqual(result["event"]["trade_id"], "T-1")

        status = history_manager.get_status()
        self.assertTrue(status["ok"])
        self.assertEqual(status["events_file"], str(self.history_dir / "history_events.jsonl"))

    def test_emit_from_http_logs_event(self):
        result = event_bus.emit_from_http({"event": "TEST_EVENT", "symbol": "ETHUSDT", "bot": "unit-test"})
        self.assertTrue(result["ok"])
        self.assertTrue(result["event_bus_logged"])
        self.assertIn("uid", result)


if __name__ == "__main__":
    unittest.main()
