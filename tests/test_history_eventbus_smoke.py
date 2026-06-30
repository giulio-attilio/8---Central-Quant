import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import event_bus
import history_manager
import main as central_main


class HistoryEventBusSmokeTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.history_dir = self.root / "history"
        self.history_dir.mkdir(parents=True, exist_ok=True)
        self.event_dir = self.root / "eventbus"
        self.event_dir.mkdir(parents=True, exist_ok=True)
        self.central_timeline_log = self.root / "central_timeline.jsonl"
        self.central_decision_log = self.root / "central_decision.jsonl"

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
            mock.patch.object(central_main, "CENTRAL_TIMELINE_LOG_FILE", self.central_timeline_log),
            mock.patch.object(central_main, "CENTRAL_DECISION_LOG_FILE", self.central_decision_log),
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
        history_manager.log_event("SIGNAL", {"symbol": "BTCUSDT", "side": "buy", "setup": "breakout", "trade_id": "A1"}, source="falcon", trade_id="A1")
        history_manager.log_event("ENTRY", {"symbol": "BTCUSDT", "side": "buy", "setup": "breakout", "trade_id": "A2"}, source="falcon", trade_id="A2")
        history_manager.log_event("CLOSE", {"symbol": "ETHUSDT", "side": "sell", "setup": "trend", "trade_id": "A3", "pnl_pct": 1.5, "result": "WIN"}, source="meme", trade_id="A3")
        history_manager.log_event("STOP", {"symbol": "ETHUSDT", "side": "sell", "setup": "trend", "trade_id": "A4", "pnl_pct": -0.5, "result": "LOSS"}, source="meme", trade_id="A4")

        filtered = history_manager.load_events(filters={"bot": "falcon"})
        self.assertEqual(len(filtered), 2)

        stats = history_manager.calculate_stats()
        self.assertGreaterEqual(stats["total_events"], 4)
        self.assertGreaterEqual(stats["signals"], 1)
        self.assertGreaterEqual(stats["entries"], 1)
        self.assertGreaterEqual(stats["closed"], 2)
        self.assertGreaterEqual(stats["blocked"], 0)
        self.assertGreaterEqual(stats["denied"], 0)
        self.assertGreaterEqual(stats["wins"], 1)
        self.assertGreaterEqual(stats["losses"], 1)
        self.assertGreaterEqual(stats["stops"], 1)
        self.assertGreaterEqual(stats["pnl_total_pct"], 1.0)

        grouped = history_manager.group_stats(group_by="bot")
        self.assertIn("FALCON", grouped)
        self.assertIn("MEME", grouped)

    def test_main_history_stats_payload(self):
        payload = central_main.build_history_stats_payload()
        self.assertTrue(payload["ok"])
        self.assertIn("general", payload)
        self.assertIn("by_bot", payload)
        self.assertIn("by_symbol", payload)
        self.assertIn("by_setup", payload)

    def test_append_timeline_event_updates_history(self):
        central_main.append_timeline_event(
            "TP50",
            bot="falcon",
            symbol="BTCUSDT",
            side="buy",
            trade_id="T-TP50",
            state="OPEN",
            details={"setup": "trend", "pnl_pct": 1.25},
        )
        events = history_manager.load_events(filters={"event_type": "TP50_HIT", "bot": "falcon"})
        self.assertGreaterEqual(len(events), 1)

    def test_history_events_routes_read_events(self):
        history_manager.log_event("TEST_EVENT", {"symbol": "BTCUSDT", "bot": "falcon"}, source="falcon", trade_id="T-ROUTE")
        with central_main.app.test_client() as client:
            response = client.get("/history/events?limit=5")
            self.assertEqual(response.status_code, 200)
            payload = response.get_json()
            self.assertTrue(payload["ok"])
            self.assertGreaterEqual(payload["count"], 1)

            latest = client.get("/history/events/latest")
            self.assertEqual(latest.status_code, 200)
            latest_payload = latest.get_json()
            self.assertTrue(latest_payload["ok"])

            query = client.get("/history/query?bot=falcon&symbol=BTCUSDT&limit=5")
            self.assertEqual(query.status_code, 200)
            query_payload = query.get_json()
            self.assertTrue(query_payload["ok"])
            self.assertIn("filters", query_payload)
            self.assertIn("stats", query_payload)
            self.assertIn("events", query_payload)
            self.assertGreaterEqual(len(query_payload["events"]), 1)

    def test_simulate_full_is_blocked_by_default(self):
        with central_main.app.test_client() as client:
            response = client.get("/simulate/full")
            self.assertEqual(response.status_code, 200)
            payload = response.get_json()
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["error"], "simulation endpoint disabled")

    def test_simulate_full_runs_when_enabled(self):
        with mock.patch.dict(central_main.os.environ, {"ENABLE_SIMULATION_ENDPOINT": "true"}, clear=False):
            with central_main.app.test_client() as client:
                response = client.get("/simulate/full")
                self.assertEqual(response.status_code, 200)
                payload = response.get_json()
                self.assertTrue(payload["ok"])
                self.assertEqual(payload["generated"], 8)
                self.assertIn("stats_after", payload)
                self.assertIn("query_predator", payload)
                self.assertIn("riskstats_hint", payload)

    def test_calculate_performance_metrics_from_closed_trades(self):
        history_manager.log_event("TRADE_CLOSED", {"symbol": "BTCUSDT", "pnl_pct": 2.5}, source="unit-test", trade_id="P-1")
        history_manager.log_event("TRADE_CLOSED", {"symbol": "ETHUSDT", "pnl_pct": 1.0}, source="unit-test", trade_id="P-2")
        history_manager.log_event("TRADE_CLOSED", {"symbol": "SOLUSDT", "pnl_pct": -1.5}, source="unit-test", trade_id="P-3")
        history_manager.log_event("TRADE_CLOSED", {"symbol": "XRPUSDT", "pnl_pct": 0.0}, source="unit-test", trade_id="P-4")

        metrics = history_manager.calculate_performance_metrics(history_manager.load_events(filters={"event_type": "TRADE_CLOSED"}))

        self.assertEqual(metrics["trades"], 4)
        self.assertEqual(metrics["wins"], 2)
        self.assertEqual(metrics["losses"], 1)
        self.assertEqual(metrics["breakeven"], 1)
        self.assertEqual(metrics["win_rate_pct"], 50.0)
        self.assertEqual(metrics["pnl_total_pct"], 2.0)
        self.assertEqual(metrics["pnl_avg_pct"], 0.5)
        self.assertEqual(metrics["avg_win_pct"], 1.75)
        self.assertEqual(metrics["avg_loss_pct"], 1.5)
        self.assertEqual(metrics["payoff_ratio"], 1.1667)
        self.assertEqual(metrics["profit_factor_pct"], 2.3333)
        self.assertEqual(metrics["expectancy_pct"], 0.875)
        self.assertEqual(metrics["max_win_streak"], 2)
        self.assertEqual(metrics["max_loss_streak"], 1)

    def test_can_open_trade_does_not_block_paper_by_default(self):
        with mock.patch.object(central_main, "GLOBAL_RISK_MAX_POSITIONS", 50), \
             mock.patch.object(central_main, "GLOBAL_RISK_MAX_PAPER_POSITIONS", 100), \
             mock.patch.object(central_main, "GLOBAL_RISK_BLOCK_ON_PAPER_LIMIT", False), \
             mock.patch.object(central_main, "GLOBAL_RISK_MAX_SIDE_CONCENTRATION_PCT", 100), \
             mock.patch.object(central_main, "GLOBAL_RISK_MAX_SYMBOL_EXPOSURE", 3), \
             mock.patch.object(central_main, "GLOBAL_RISK_ALLOW_REDUCE_ONLY", False), \
             mock.patch.object(central_main, "ENABLE_REAL_TRADING", True), \
             mock.patch.object(central_main, "REAL_TRADING_ALLOWED_BOTS", {"FALCON"}), \
             mock.patch.object(central_main, "_all_open_positions_payload", return_value=[{"bot": "FALCON", "symbol": "BTCUSDT", "side": "LONG"}] * 101), \
             mock.patch.object(central_main, "_central_live_positions_payload", return_value=[]), \
             mock.patch.object(central_main, "central_exposure_snapshot", return_value={"total_positions_open": 101, "long_positions_open": 101, "short_positions_open": 0}), \
             mock.patch.object(central_main, "_risk_memory_block_payload", return_value={"blocked": False, "usage_pct": 0}), \
             mock.patch.object(central_main, "append_decision_log", return_value=None), \
             mock.patch.object(central_main, "broker_status_payload", return_value={"ok": True}):
            result = central_main.can_open_trade_decision({"bot": "FALCON", "symbol": "ETHUSDT", "side": "SHORT", "mode": "PAPER"})

        self.assertTrue(result["allowed"])
        self.assertIn("exposição PAPER alta", " ".join(result["warnings"]))
        self.assertNotIn("bloqueio PAPER ativo", " ".join(result["reasons"]))

    def test_blocked_and_nested_payloads_are_normalized(self):
        history_manager.log_event(
            "TRADE_BLOCKED",
            {
                "symbol": "ETHUSDT",
                "setup": "trend",
                "side": "sell",
                "result": "DENY",
                "raw": {"falcon_event": {"symbol": "ETHUSDT", "setup": "trend", "side": "sell"}},
            },
            source="falcon",
            trade_id="T-BLOCKED",
        )
        history_manager.log_event(
            "RISK_DECISION",
            {
                "decision": "DENY",
                "raw": {"execution_decision": {"symbol": "BTCUSDT", "setup": "breakout", "side": "buy"}},
            },
            source="central",
            trade_id="T-RISK",
        )
        history_manager.log_event(
            "TEST_EVENT",
            {"bot": "{'name': 'falcon'}", "raw": {"bot": "Falcon Strike"}},
            source="falcon",
            trade_id="T-BOT",
        )
        history_manager.log_event(
            "RISK_DECISION",
            {
                "result": "DENY",
                "raw": {"event": "{'BOT': 'PREDATOR', 'SYMBOL': 'AVAXUSDT', 'SIDE': 'LONG', 'SETUP': 'SMART_PREDATOR'}"},
            },
            source="predator",
            trade_id="T-PREDATOR",
        )
        history_manager.log_event(
            "RISK_DECISION",
            {
                "result": "DENY",
                "raw": {"state": "{'BOT': 'Turtle Breakout PRO 2.0', 'SYMBOL': 'SOLUSDT', 'SIDE': 'SHORT', 'SETUP': 'BREAKOUT'}"},
            },
            source="turtle",
            trade_id="T-TURTLE",
        )

        blocked_events = history_manager.load_events(filters={"event_type": "TRADE_BLOCKED"})
        self.assertGreaterEqual(len(blocked_events), 1)

        bot_normalized = history_manager.normalize_payload("TEST_EVENT", {"bot": "{'name': 'falcon'}", "raw": {"bot": "Falcon Strike"}}, source="falcon")
        self.assertEqual(bot_normalized["bot"], "FALCON")

        predator_payload = history_manager.normalize_payload(
            "RISK_DECISION",
            {"result": "DENY", "raw": {"event": "{'BOT': 'PREDATOR', 'SYMBOL': 'AVAXUSDT', 'SIDE': 'LONG', 'SETUP': 'SMART_PREDATOR'}"}},
            source="predator",
            trade_id="T-PREDATOR",
        )
        self.assertEqual(predator_payload["bot"], "PREDATOR")
        self.assertEqual(predator_payload["symbol"], "AVAXUSDT")
        self.assertEqual(predator_payload["side"], "LONG")
        self.assertEqual(predator_payload["setup"], "SMART_PREDATOR")

        turtle_payload = history_manager.normalize_payload(
            "RISK_DECISION",
            {"result": "DENY", "raw": {"state": "{'BOT': 'Turtle Breakout PRO 2.0', 'SYMBOL': 'SOLUSDT', 'SIDE': 'SHORT', 'SETUP': 'BREAKOUT'}"}},
            source="turtle",
            trade_id="T-TURTLE",
        )
        self.assertEqual(turtle_payload["bot"], "TURTLE")
        self.assertEqual(turtle_payload["symbol"], "SOLUSDT")
        self.assertEqual(turtle_payload["side"], "SHORT")
        self.assertEqual(turtle_payload["setup"], "BREAKOUT")

        stats = history_manager.calculate_stats()
        self.assertGreaterEqual(stats["blocked"], 4)
        self.assertGreaterEqual(stats["denied"], 4)

        grouped = history_manager.group_stats(group_by="bot")
        self.assertIn("FALCON", grouped)
        self.assertIn("PREDATOR", grouped)
        self.assertIn("TURTLE", grouped)
        self.assertGreaterEqual(grouped["FALCON"]["blocked"], 1)
        self.assertGreaterEqual(grouped["FALCON"]["denied"], 1)
        self.assertGreaterEqual(grouped["PREDATOR"]["blocked"], 1)
        self.assertGreaterEqual(grouped["TURTLE"]["blocked"], 1)


if __name__ == "__main__":
    unittest.main()
