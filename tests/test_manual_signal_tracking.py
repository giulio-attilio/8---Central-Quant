"""Offline manual-tracking tests. All Telegram calls are fakes; no broker imports."""
import sqlite3
import sys
import tempfile
import json
import threading
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import manual_signal_tracking as tracking
import signal_only_service as service
import telegram_signal_delivery as delivery


VALUES = dict(FALCON_TOKEN="1:" + "A" * 30, FALCON_CHAT_ID="101",
              DONKEY_H4_TOKEN="2:" + "B" * 30, DONKEY_H4_CHAT_ID="202",
              CENTRAL_TELEGRAM_BOT_TOKEN="3:" + "C" * 30,
              CENTRAL_TELEGRAM_CHAT_ID="303")
NOW = 1767657601000


def signal(setup="FALCON15", side="LONG", symbol="BTC-USDT", suffix="a",
           entry=100.0, stop=None, tp50=None, candle=None):
    stop = (98.0 if side == "LONG" else 102.0) if stop is None else stop
    tp50 = (102.0 if side == "LONG" else 98.0) if tp50 is None else tp50
    bot = "FALCON" if setup.startswith("FALCON") else "DONKEY"
    return dict(synthetic=False, source="BINGX_PUBLIC_SWAP", setup=setup,
                symbol=symbol, signal_id=f"{bot}:{setup}:{suffix}", side=side,
                entry=entry, stop=stop, tp50=tp50,
                timeframe="15m" if bot == "FALCON" else "4h",
                candle_closed_at_ms=NOW - 1000 if candle is None else candle,
                generated_at_ms=NOW, invalidated=False)


def candidate(item, now=NOW):
    return dict(signal=item, now_ms=now, expires_at_ms=NOW + 900000,
                validity_basis="explicit fixture policy",
                data_valid_until_ms=NOW + 60000)


class Harness(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = str(Path(self.temp.name) / "ledger.sqlite")
        delivery.initialize_ledger(self.path)
        tracking.provision(self.path)
        self.sent = []
        self.tracker = tracking.ManualTradeTracker(
            self.path, VALUES, 77, authorized=True
        )

    def post(self, token, chat, text, timeout, reply_markup=None):
        message_id = 100 + len(self.sent)
        self.sent.append(dict(token=token, chat=chat, text=text,
                              markup=reply_markup, message_id=message_id))
        return 200, dict(ok=True, result=dict(message_id=message_id,
                                              chat=dict(id=int(chat)), text=text))

    def send(self, bot, signals):
        with patch.object(delivery, "_post", side_effect=self.post):
            return delivery.dispatch_public_candidates(
                bot, [candidate(item) for item in signals], values=VALUES,
                ledger_path=self.path, network_authorized=True,
                public_delivery_authorized=True, manual_tracking=True,
            )

    def callback(self, bot, data, *, message_id=None, user=77, chat=None, update=1):
        target = 101 if bot == "FALCON" else 202
        return dict(update_id=update, callback_query=dict(
            id=f"query-{update}", from_=None,
            **{"from": dict(id=user, is_bot=False)}, data=data,
            message=dict(message_id=message_id or self.sent[-1]["message_id"],
                         chat=dict(id=target if chat is None else chat))))

    def enter_last(self, bot="FALCON", update=1):
        data = self.sent[-1]["markup"]["inline_keyboard"][0][0]["callback_data"]
        return self.tracker.accept(bot, self.callback(bot, data, update=update), NOW + update)

    def active(self):
        with closing(sqlite3.connect(self.path)) as db:
            db.row_factory = sqlite3.Row
            return db.execute(
                "SELECT * FROM manual_trade_v1 WHERE state='ACTIVE' ORDER BY active_ms, ref"
            ).fetchall()


class TestMessagesAndConsolidation(Harness):
    def test_long_short_colors_compact_body_and_button(self):
        first = self.send("FALCON", [signal(side="LONG")])
        second = self.send("FALCON", [signal(side="SHORT", suffix="b", candle=NOW)])
        assert first["status"] == second["status"] == "CONFIRMED"
        assert self.sent[0]["text"].startswith("🟢 FALCON — SINAL MANUAL")
        assert self.sent[1]["text"].startswith("🔴 FALCON — SINAL MANUAL")
        for sent in self.sent:
            assert "Nenhuma ordem foi enviada." in sent["text"]
            assert "SIGNAL-ONLY" in sent["text"]
            assert "signal_id" not in sent["text"] and "Unix" not in sent["text"]
            assert sent["markup"]["inline_keyboard"][0][0]["text"] == "✅ ENTREI NO TRADE"
        assert first["live_allowed"] is False

    def test_identical_falcon_pair_is_one_message_with_two_identities(self):
        result = self.send("FALCON", [signal("FALCON15"), signal("FALCON30", suffix="b")])
        assert result["status"] == "CONFIRMED"
        assert len(self.sent) == 1
        assert "Confirmação: FALCON15 + FALCON30" in self.sent[0]["text"]
        buttons = self.sent[0]["markup"]["inline_keyboard"]
        assert len(buttons) == 1 and len(buttons[0]) == 1
        assert buttons[0][0]["text"] == "✅ ENTREI NO TRADE"
        with closing(sqlite3.connect(self.path)) as db:
            assert db.execute("SELECT COUNT(*) FROM delivery_v1").fetchone()[0] == 2
            assert db.execute("SELECT COUNT(*) FROM manual_trade_candidate_v1").fetchone()[0] == 2
            assert db.execute("SELECT COUNT(DISTINCT message_id) FROM delivery_v1").fetchone()[0] == 1

    def test_identical_short_falcon_pair_has_one_message_and_one_button(self):
        result = self.send("FALCON", [signal("FALCON15", side="SHORT"),
                                      signal("FALCON30", side="SHORT", suffix="b")])
        assert result["status"] == "CONFIRMED"
        assert len(self.sent) == 1
        assert self.sent[0]["text"].startswith("🔴 FALCON — SINAL MANUAL")
        buttons = self.sent[0]["markup"]["inline_keyboard"]
        assert len(buttons) == 1 and len(buttons[0]) == 1
        assert buttons[0][0]["text"] == "✅ ENTREI NO TRADE"

    def test_different_falcon_pair_is_two_messages_and_dedup_survives(self):
        signals = [signal("FALCON15"), signal("FALCON30", suffix="b", tp50=103.0)]
        assert self.send("FALCON", signals)["status"] == "CONFIRMED"
        assert len(self.sent) == 2
        assert self.send("FALCON", signals)["reason"] == "PRIOR_ATTEMPT_NO_RETRY"
        assert len(self.sent) == 2

    def test_donkey_message_and_variants_are_independent(self):
        variants = [signal("DONKEY", suffix="d"),
                    signal("DONKEY_ORIGINAL", suffix="o"),
                    signal("EARLY_DONKEY", suffix="e")]
        result = self.send("DONKEY", variants)
        assert result["status"] == "CONFIRMED"
        assert len(self.sent) == 3
        assert all(item["text"].startswith("🟢 DONKEY — SINAL MANUAL") for item in self.sent)
        assert ["Setup: " + item["setup"] in sent["text"]
                for item, sent in zip(variants, self.sent)] == [True, True, True]
        assert all(item["markup"]["inline_keyboard"][0][0]["text"] == "✅ ENTREI NO TRADE"
                   for item in self.sent)

    def test_donkey_short_has_entry_button(self):
        result = self.send("DONKEY", [signal("DONKEY", side="SHORT")])
        assert result["status"] == "CONFIRMED"
        assert self.sent[0]["text"].startswith("🔴 DONKEY — SINAL MANUAL")
        assert self.sent[0]["markup"]["inline_keyboard"][0][0]["text"] == "✅ ENTREI NO TRADE"


class TestBlockingAndCallbacks(Harness):
    def test_same_side_suppressed_opposite_alerted_cross_family_allowed(self):
        assert self.send("FALCON", [signal(suffix="first")])["status"] == "CONFIRMED"
        self.enter_last()
        same = self.send("FALCON", [signal(suffix="same", candle=NOW)])
        assert same["reason"] == "MANUAL_TRADE_SAME_SIDE_ACTIVE"
        assert len(self.sent) == 1
        opposite = self.send("FALCON", [signal(side="SHORT", suffix="opposite", candle=NOW - 1)])
        assert opposite["status"] == "CONFIRMED"
        assert "SINAL OPOSTO" in self.sent[-1]["text"]
        assert "Trade manual atual:\n🟢 LONG" in self.sent[-1]["text"]
        assert self.sent[-1]["markup"] is None
        assert len(self.active()) == 1  # Opposite alert does not close the current trade.
        donkey = self.send("DONKEY", [signal("DONKEY", suffix="cross")])
        assert donkey["status"] == "CONFIRMED"

    def test_donkey_family_blocks_same_side_alerts_opposite_and_keeps_variants_independent(self):
        assert self.send("DONKEY", [signal("DONKEY", suffix="first")])["status"] == "CONFIRMED"
        self.enter_last("DONKEY")
        same = self.send("DONKEY", [signal("DONKEY", suffix="same", candle=NOW)])
        assert same["reason"] == "MANUAL_TRADE_SAME_SIDE_ACTIVE"
        opposite = self.send("DONKEY", [signal("DONKEY", side="SHORT",
                                                       suffix="opposite", candle=NOW - 1)])
        assert opposite["status"] == "CONFIRMED"
        assert "SINAL OPOSTO" in self.sent[-1]["text"]
        assert self.sent[-1]["markup"] is None
        original = self.send("DONKEY", [signal("DONKEY_ORIGINAL", suffix="original")])
        early = self.send("DONKEY", [signal("EARLY_DONKEY", suffix="early")])
        falcon = self.send("FALCON", [signal("FALCON15", suffix="falcon")])
        assert all(item["status"] == "CONFIRMED" for item in (original, early, falcon))

    def test_operator_and_message_binding_required_then_restart_preserves_active(self):
        self.send("FALCON", [signal()])
        button = self.sent[-1]["markup"]["inline_keyboard"][0][0]["callback_data"]
        denied = self.tracker.accept("FALCON", self.callback("FALCON", button, user=88), NOW + 1)
        assert "não autorizada" in denied["answer"]
        denied = self.tracker.accept("FALCON", self.callback("FALCON", button, chat=999, update=2), NOW + 2)
        assert "não autorizada" in denied["answer"]
        denied = self.tracker.accept("FALCON", self.callback("FALCON", button, message_id=999, update=3), NOW + 3)
        assert "não autorizada" in denied["answer"]
        accepted = self.tracker.accept("FALCON", self.callback("FALCON", button, update=4), NOW + 4)
        assert "ativado" in accepted["answer"]
        restarted = tracking.ManualTradeTracker(self.path, VALUES, 77, authorized=True)
        assert restarted.operator == 77
        assert len(self.active()) == 1
        with closing(sqlite3.connect(self.path)) as db:
            row = db.execute("SELECT family, side, entry, stop, tp50, state FROM manual_trade_v1").fetchone()
        assert row == ("FALCON", "LONG", 100.0, 98.0, 102.0, "ACTIVE")


class TestLifecycleAndPanel(Harness):
    def activate(self):
        self.send("FALCON", [signal()])
        self.enter_last()
        return self.active()[0]

    def quote(self, price, at):
        return dict(synthetic=False, connected=True, symbol="BTC-USDT",
                    observed_at_ms=at, quote=dict(price=price, at_ms=at), frames={})

    def test_tp50_once_stays_active_and_stop_closes_with_colored_events(self):
        self.activate()
        self.tracker.observe(self.quote(102.0, NOW + 10), NOW + 10, 1000)
        self.tracker.observe(self.quote(103.0, NOW + 11), NOW + 11, 1000)
        assert len(self.active()) == 1
        with closing(sqlite3.connect(self.path)) as db:
            events = db.execute("SELECT kind, text FROM manual_trade_event_v1").fetchall()
        assert len(events) == 1 and events[0][0] == "TP50"
        assert events[0][1].startswith("🔵 TP50")
        self.tracker.observe(self.quote(98.0, NOW + 12), NOW + 12, 1000)
        assert not self.active()
        with closing(sqlite3.connect(self.path)) as db:
            state = db.execute("SELECT state, close_reason, tp_ms FROM manual_trade_v1").fetchone()
            stop_text = db.execute("SELECT text FROM manual_trade_event_v1 WHERE kind='STOP'").fetchone()[0]
        assert state[0:2] == ("CLOSED", "STOP") and state[2] is not None
        assert stop_text.startswith("🟡 STOP")
        with patch.object(delivery, "_post", side_effect=self.post):
            self.tracker.flush()
        notices = [item for item in self.sent if item["text"].startswith(("🔵 TP50", "🟡 STOP"))]
        assert len(notices) == 2 and all(item["markup"] is None for item in notices)

    def test_panel_stop_update_persists_and_updated_stop_is_used(self):
        row = self.activate()
        panel_update = dict(update_id=2, message={"from": dict(id=77, is_bot=False),
                                                  "chat": dict(id=101), "text": "/ativos"})
        panel = self.tracker.accept("FALCON", panel_update, NOW + 2)["outbound"]
        assert "📋 TRADES MANUAIS ATIVOS" in panel["text"]
        assert "FALCON | LONG" in panel["text"] and "TP50: ⏳ pendente" in panel["text"]
        stop_button = panel["reply_markup"]["inline_keyboard"][0][0]["callback_data"]
        prompt = self.tracker.accept("FALCON", self.callback("FALCON", stop_button,
                                                             message_id=500, update=3), NOW + 3)
        assert "Informe o novo stop" in prompt["outbound"]["text"]
        bad = dict(update_id=4, message={"from": dict(id=77, is_bot=False),
                                         "chat": dict(id=101), "text": "abc"})
        assert "inválido" in self.tracker.accept("FALCON", bad, NOW + 4)["outbound"]["text"]
        with closing(sqlite3.connect(self.path)) as db:
            assert db.execute("SELECT stop FROM manual_trade_v1 WHERE ref=?", (row["ref"],)).fetchone()[0] == 98.0
        good = dict(update_id=5, message={"from": dict(id=77, is_bot=False),
                                          "chat": dict(id=101), "text": "99,5"})
        assert "99.5" in self.tracker.accept("FALCON", good, NOW + 5)["outbound"]["text"]
        with closing(sqlite3.connect(self.path)) as db:
            assert db.execute("SELECT stop FROM manual_trade_v1 WHERE ref=?", (row["ref"],)).fetchone()[0] == 99.5
        self.tracker.observe(self.quote(99.4, NOW + 6), NOW + 6, 1000)
        with closing(sqlite3.connect(self.path)) as db:
            assert db.execute("SELECT close_reason FROM manual_trade_v1").fetchone()[0] == "STOP"

    def test_manual_close_records_reason_and_releases_family(self):
        self.activate()
        panel = self.tracker.accept("FALCON", dict(
            update_id=2, message={"from": dict(id=77, is_bot=False),
                                  "chat": dict(id=101), "text": "/ativos"}), NOW + 2)["outbound"]
        close_button = panel["reply_markup"]["inline_keyboard"][0][1]["callback_data"]
        answer = self.tracker.accept("FALCON", self.callback(
            "FALCON", close_button, message_id=500, update=3), NOW + 3)
        assert "encerrado" in answer["answer"]
        with closing(sqlite3.connect(self.path)) as db:
            assert db.execute("SELECT close_reason FROM manual_trade_v1").fetchone()[0] == "MANUAL_CLOSE"
        assert self.send("FALCON", [signal(suffix="released", candle=NOW - 2)])["status"] == "CONFIRMED"

    def test_panel_survives_tracker_restart_and_has_no_entry_button(self):
        self.activate()
        restarted = tracking.ManualTradeTracker(self.path, VALUES, 77, authorized=True)
        panel = restarted.accept("FALCON", dict(
            update_id=2, message={"from": dict(id=77, is_bot=False),
                                  "chat": dict(id=101), "text": "/ativos"}), NOW + 2)["outbound"]
        callbacks = [button["callback_data"] for row in panel["reply_markup"]["inline_keyboard"]
                     for button in row]
        assert callbacks and all(value.startswith(("ms:", "mc:")) for value in callbacks)
        assert all(not value.startswith("mt:") for value in callbacks)


class TestSchemaProvisioning(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = str(Path(self.temp.name) / "ledger.sqlite")
        delivery.initialize_ledger(self.path)

    def test_provision_twice_is_idempotent_and_preserves_existing_data(self):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("INSERT INTO delivery_v1 VALUES ('kept', 'kept-candle', 'route', 'CONFIRMED', 1, 9)")
        tracking.provision(self.path)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("INSERT INTO manual_trade_control_v1 VALUES ('kept-route', '101', 77, 5, 6, NULL)")
        tracking.provision(self.path)
        with closing(sqlite3.connect(self.path)) as db:
            tables = {row[0] for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'manual_trade_%'"
            )}
            kept = db.execute("SELECT status, message_id FROM delivery_v1 WHERE identity='kept'").fetchone()
            control = db.execute(
                "SELECT offset, clock FROM manual_trade_control_v1 WHERE route='kept-route'"
            ).fetchone()
        assert tables == {"manual_trade_v1", "manual_trade_candidate_v1",
                          "manual_trade_event_v1", "manual_trade_control_v1",
                          "manual_trade_clock_v1"}
        assert kept == ("CONFIRMED", 9) and control == (5, 6)

    def test_provision_failure_rolls_back_partial_schema(self):
        def partial_then_fail(db):
            db.execute("CREATE TABLE should_rollback (id INTEGER)")
            raise sqlite3.OperationalError("fixture")
        with patch.object(tracking, "_provision_in_transaction", side_effect=partial_then_fail):
            with self.assertRaises(sqlite3.OperationalError):
                tracking.provision(self.path)
        with closing(sqlite3.connect(self.path)) as db:
            assert db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='should_rollback'"
            ).fetchone() is None


class TestSafetyAndSupervisor(unittest.TestCase):
    @staticmethod
    def _config():
        config = json.loads(Path("signals-config.validation.json").read_text(encoding="utf-8"))
        for entry in config["bots"].values():
            entry["symbols"] = ["BTC-USDT"]
        return config

    def test_modules_have_no_broker_or_live_execution_dependency(self):
        source = Path(tracking.__file__).read_text(encoding="utf-8")
        self.assertNotIn("create_order", source)
        self.assertNotIn("bingx", source.lower())
        self.assertNotIn("live_allowed", source)

    def test_supervisor_batches_falcon_before_telegram_without_changing_analysis(self):
        config = self._config()
        snapshot = dict(synthetic=False, connected=True, symbol="BTC-USDT",
                        observed_at_ms=NOW, quote=dict(price=100.0, at_ms=NOW),
                        frames={"15m": [], "4h": [], "1d": []},
                        frame_received_at_ms={"15m": NOW, "4h": NOW, "1d": NOW})
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "ledger.sqlite")
            delivery.initialize_ledger(path)
            sent = []

            def analyzed(bot, source, snap, analysis, policy, *, setup, now_ms, **kwargs):
                if bot == "FALCON":
                    item = signal(setup, suffix=setup)
                    return dict(status="PUBLIC_CANDIDATE_READY", reason=None,
                                candidate=candidate(item))
                return dict(status="BLOCKED", reason="NO_SIGNAL")

            def post(token, chat, text, timeout, reply_markup=None):
                sent.append(text)
                return 200, dict(ok=True, result=dict(message_id=9, chat=dict(id=int(chat)), text=text))

            with patch.object(service, "reviewed_analysis"), \
                 patch.object(service, "donkey_source"), \
                 patch.object(service, "collect_snapshot", return_value=snapshot), \
                 patch.object(service, "run_once", side_effect=analyzed) as evaluate, \
                 patch.object(service.time, "time_ns", return_value=NOW * 1000000), \
                 patch.object(delivery, "_post", side_effect=post):
                result = service.run_service(
                    config, {"FALCON": "reviewed", "DONKEY": "reviewed"}, values=VALUES,
                    ledger_path=path, stop_event=threading.Event(), service_authorized=True,
                    public_data_authorized=True, public_delivery_authorized=True, max_cycles=1,
                )
        self.assertEqual(result["status"], "STOPPED")
        self.assertEqual((result["evaluations"], result["confirmed"]), (5, 1))
        self.assertEqual(evaluate.call_count, 5)
        self.assertEqual(len(sent), 1)
        self.assertIn("FALCON15 + FALCON30", sent[0])

    def test_authorized_startup_provisions_schema_before_tracker(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "ledger.sqlite")
            delivery.initialize_ledger(path)
            stopped = threading.Event()
            stopped.set()
            with patch.object(service, "reviewed_analysis"), \
                 patch.object(service, "donkey_source"), \
                 patch.object(tracking, "ManualTradeTracker") as tracker:
                result = service.run_service(
                    self._config(), {"FALCON": "reviewed", "DONKEY": "reviewed"},
                    values=VALUES, ledger_path=path, stop_event=stopped,
                    service_authorized=True, public_data_authorized=True,
                    public_delivery_authorized=True, max_cycles=1, donkey_operator_id=77,
                )
            with closing(sqlite3.connect(path)) as db:
                exists = db.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='manual_trade_v1'"
                ).fetchone()
        self.assertEqual(result["status"], "STOPPED")
        self.assertIsNotNone(exists)
        tracker.assert_called_once()

    def test_startup_schema_failure_is_fail_closed_before_polling(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "ledger.sqlite")
            delivery.initialize_ledger(path)
            with patch.object(service, "reviewed_analysis"), \
                 patch.object(service, "donkey_source"), \
                 patch.object(tracking, "provision", side_effect=sqlite3.OperationalError("fixture")), \
                 patch.object(tracking, "ManualTradeTracker") as tracker, \
                 patch.object(service, "collect_snapshot") as collect:
                result = service.run_service(
                    self._config(), {"FALCON": "reviewed", "DONKEY": "reviewed"},
                    values=VALUES, ledger_path=path, stop_event=threading.Event(),
                    service_authorized=True, public_data_authorized=True,
                    public_delivery_authorized=True, max_cycles=1, donkey_operator_id=77,
                )
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual((result["reason"], result["stage"]),
                         ("SQLITE_FAILURE", "tracking_schema_provision"))
        tracker.assert_not_called()
        collect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
