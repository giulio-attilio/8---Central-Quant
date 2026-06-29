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

    def test_load_events_filters_and_aggregation(self):
        history_manager.log_event("SIGNAL_CREATED", {"symbol": "BTCUSDT", "side": "buy", "setup": "breakout", "trade_id": "A1"}, source="falcon", trade_id="A1")
        history_manager.log_event("TRADE_OPENED", {"symbol": "BTCUSDT", "side": "buy", "setup": "breakout", "trade_id": "A2"}, source="falcon", trade_id="A2")
        history_manager.log_event("TRADE_CLOSED", {"symbol": "ETHUSDT", "side": "sell", "setup": "trend", "trade_id": "A3", "result_pct": 1.5, "reason": "take_profit"}, source="meme", trade_id="A3")
        history_manager.log_event("TRADE_CLOSED", {"symbol": "ETHUSDT", "side": "sell", "setup": "trend", "trade_id": "A4", "result_pct": -0.5, "reason": "stop"}, source="meme", trade_id="A4")

        filtered = history_manager.load_events(filters={"bot": "falcon"})
        self.assertEqual(len(filtered), 2)

        stats = history_manager.calculate_stats()
        self.assertGreaterEqual(stats["total_events"], 4)
        self.assertGreaterEqual(stats["signals"], 1)
        self.assertGreaterEqual(stats["entries"], 1)
        self.assertGreaterEqual(stats["closed"], 2)
        self.assertGreaterEqual(stats["wins"], 1)
        self.assertGreaterEqual(stats["losses"], 1)
        self.assertGreaterEqual(stats["stops"], 1)
        self.assertGreaterEqual(stats["pnl_total_pct"], 1.0)

        grouped = history_manager.group_stats(group_by="bot")
        self.assertIn("FALCON", grouped)
        self.assertIn("MEME", grouped)


if __name__ == "__main__":
    unittest.main()
