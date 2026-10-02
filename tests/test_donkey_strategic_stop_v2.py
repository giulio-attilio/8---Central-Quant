"""Offline manual Donkey H4 exit; guards are installed before project imports."""
import sys
import json
import copy
import unittest
import sqlite3
import threading
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_falcon_advisory_offline as guard_harness
import test_signal_only_integration as fixtures
import test_manual_signal_tracking as base
import donkey_advisory_offline as donkey
import test_signal_only_service as service_fixtures

tracking, delivery, service = base.tracking, base.delivery, base.service
NOW, VALUES, signal = base.NOW, base.VALUES, base.signal
H4 = 14400000
CLOSED = (NOW // H4 + 1) * H4
LATER = CLOSED + 1000


def snapshot(closed_price=100, forming_price=100, symbol="BTC-USDT", now=LATER):
    forming = now // H4 * H4
    rows = []
    for i in range(200):
        price = closed_price if i == 198 else (forming_price if i == 199 else 100)
        rows.append([forming-(199-i)*H4, price, price+1, price-1, price, 10])
    return dict(synthetic=False, source="BINGX_PUBLIC_SWAP", connected=True,
        symbol=symbol, observed_at_ms=now, frames={"4h": rows},
        frame_received_at_ms={"4h": now}, quote=dict(price=100, at_ms=now),
        source_qualified=False, delivery_allowed=False, live_allowed=False,
        manual_trade_authorized=False)


class StrategicStop(base.Harness):
    def activate(self, side="LONG", setups=("DONKEY", "DONKEY_ORIGINAL")):
        self.send("DONKEY", [signal(setup, side=side) for setup in setups])
        self.enter_last("DONKEY")
        return self.active()[0]

    def observe(self, snap=None, now=LATER):
        self.tracker.observe_h4(snap or snapshot(now=now), now, fixtures.SOURCE,
            fixtures.CONFIG, frame_max_age_ms=10000, quote_max_age_ms=5000)

    def values(self, close, ema, macd, closed=CLOSED, now=LATER):
        with patch.object(donkey, "closed_h4_indicators", return_value=dict(
                close=close, ema20=ema, macd=macd, closed_at_ms=closed)):
            self.observe(now=now)

    def events(self):
        with closing(tracking.connect(self.path)) as db:
            return db.execute("SELECT * FROM manual_trade_event_v1 ORDER BY created_ms").fetchall()

    def decision(self, setup):
        with closing(tracking.connect(self.path)) as db:
            return tracking.active_signal_decision(db, setup, "BTC-USDT", "LONG")[0]

    def test_both_reasons_one_event_and_one_message_restart(self):
        self.activate()
        self.values(90, 100, -1)
        assert not self.active()
        event = self.events()[0]
        assert event["kind"] == "STOP" and event["text"].count("\u2022 ") == 2
        assert "DONKEY + DONKEY_ORIGINAL" in event["text"]
        assert self.decision("DONKEY") is None and self.decision("DONKEY_ORIGINAL") is None
        assert self.decision("EARLY_DONKEY") is None
        self.tracker = tracking.ManualTradeTracker(self.path, VALUES, 77, authorized=True)
        self.observe(now=LATER+1)
        with patch.object(delivery, "_post", side_effect=self.post):
            self.tracker.flush()
            self.tracker.flush()
        assert len(self.sent) == 2 and "STOP" in self.sent[-1]["text"]
        assert self.sent[-1]["markup"] is None
        assert len(self.events()) == 1

    def test_same_h4_persisted_even_without_stop_then_restart(self):
        row = self.activate()
        self.values(100, 100, 0)
        with closing(tracking.connect(self.path)) as db:
            assert db.execute("SELECT closed_at_ms FROM manual_trade_h4_v2 WHERE ref=?",
                              (row["ref"],)).fetchone()[0] == CLOSED
        self.tracker = tracking.ManualTradeTracker(self.path, VALUES, 77, authorized=True)
        self.values(90, 100, -1)  # Corrected same candle must not evaluate twice.
        assert len(self.active()) == 1 and not self.events()
        self.values(90, 100, -1, closed=CLOSED+H4, now=LATER+H4)
        assert not self.active() and len(self.events()) == 1

    def test_real_indicators_forming_candle_never_stops(self):
        self.activate()
        self.observe(snapshot(forming_price=50))
        assert len(self.active()) == 1 and not self.events()
        values = donkey.closed_h4_indicators(fixtures.SOURCE, snapshot(forming_price=50),
            fixtures.CONFIG, now_ms=LATER, frame_max_age_ms=10000, quote_max_age_ms=5000)
        assert values == dict(close=100.0, ema20=100.0, macd=0.0, closed_at_ms=CLOSED)

    def test_same_real_h4_does_not_recalculate_indicators(self):
        self.activate()
        with patch.object(donkey, "reviewed_analysis", wraps=donkey.reviewed_analysis) as reviewed:
            self.observe()
            self.tracker = tracking.ManualTradeTracker(self.path, VALUES, 77, authorized=True)
            self.observe()
        assert reviewed.call_count == 1 and len(self.active()) == 1

    def test_real_closed_candle_uses_entry_formula(self):
        self.activate()
        snap = snapshot(closed_price=90, forming_price=150)
        closes = donkey.pd.Series([r[4] for r in snap["frames"]["4h"]])
        expected_macd = (closes.ewm(span=fixtures.CONFIG["DONKEY_MACD_FAST"], adjust=False).mean()
                         - closes.ewm(span=fixtures.CONFIG["DONKEY_MACD_SLOW"], adjust=False).mean()).iloc[-2]
        values = donkey.closed_h4_indicators(fixtures.SOURCE, snap, fixtures.CONFIG,
            now_ms=LATER, frame_max_age_ms=10000, quote_max_age_ms=5000)
        assert values["macd"] == expected_macd and values["macd"] < 0
        self.observe(snap)
        assert not self.active() and self.events()[0]["text"].count("\u2022 ") == 2

    def test_old_candle_before_activation_never_closes(self):
        self.activate()
        self.values(90, 100, -1, closed=NOW)
        assert len(self.active()) == 1 and not self.events()

    def test_missing_stale_and_wrong_source_fail_closed(self):
        self.activate()
        for change in (dict(frames={}, frame_received_at_ms={}),
                       dict(source="UNTRUSTED"), dict(observed_at_ms=LATER-10001)):
            snap = dict(snapshot(), **change)
            with self.assertRaises(ValueError):
                self.observe(snap)
            assert len(self.active()) == 1 and not self.events()

    def test_tp50_stays_active_then_strategic_stop_releases_all(self):
        self.activate()
        for at in (NOW+10, NOW+11):
            quote = dict(synthetic=False, connected=True, symbol="BTC-USDT",
                         observed_at_ms=at, quote=dict(price=102, at_ms=at))
            self.tracker.observe(quote, at, 1000)
        assert len(self.active()) == 1 and len(self.events()) == 1
        assert self.events()[0]["kind"] == "TP50"
        assert self.decision("DONKEY") == self.decision("DONKEY_ORIGINAL") == "SAME_SIDE_ACTIVE"
        self.values(90, 100, 1)
        assert not self.active()
        assert [e["kind"] for e in self.events()] == ["TP50", "STOP"]
        assert self.decision("DONKEY") is self.decision("DONKEY_ORIGINAL") is None

    def test_protection_update_persists_but_does_not_trigger_exit(self):
        row = self.activate()
        button = "ms:"+row["ref"]
        self.tracker.accept("DONKEY", self.callback("DONKEY", button, update=2), NOW+2)
        self.tracker.accept("DONKEY", dict(update_id=3, message={
            "from": dict(id=77, is_bot=False), "chat": dict(id=202), "text": "99.5"}), NOW+3)
        self.tracker = tracking.ManualTradeTracker(self.path, VALUES, 77, authorized=True)
        quote = dict(synthetic=False, connected=True, symbol="BTC-USDT", observed_at_ms=NOW+4,
                     quote=dict(price=98, at_ms=NOW+4))
        self.tracker.observe(quote, NOW+4, 1000)
        assert self.active()[0]["stop"] == 99.5 and not self.events()
        with closing(tracking.connect(self.path)) as db:
            panel, _ = tracking._panel(db)
        assert "Stop de prote\u00e7\u00e3o: 99.5" in panel
        assert "H4 close < EMA20 OU MACD negativo" in panel

    def test_short_numeric_protection_touch_keeps_active(self):
        self.activate(side="SHORT", setups=("EARLY_DONKEY",))
        quote = dict(synthetic=False, connected=True, symbol="BTC-USDT", observed_at_ms=NOW+4,
                     quote=dict(price=103, at_ms=NOW+4))
        self.tracker.observe(quote, NOW+4, 1000)
        assert len(self.active()) == 1 and not self.events()
        with closing(tracking.connect(self.path)) as db:
            panel, _ = tracking._panel(db)
        assert "H4 close > EMA20 OU MACD positivo" in panel

    def test_short_both_conditions_make_one_stop_with_two_reasons(self):
        self.activate(side="SHORT", setups=("EARLY_DONKEY",))
        self.values(101, 100, 1)
        assert not self.active() and len(self.events()) == 1
        assert self.events()[0]["text"].count("\u2022 ") == 2

    def test_falcon_numeric_stop_preserved_no_h4_exit(self):
        self.send("FALCON", [signal()])
        self.enter_last("FALCON")
        self.values(90, 100, -1)
        assert len(self.active()) == 1 and not self.events()
        quote = dict(synthetic=False, connected=True, symbol="BTC-USDT", observed_at_ms=NOW+4,
                     quote=dict(price=98, at_ms=NOW+4))
        self.tracker.observe(quote, NOW+4, 1000)
        assert not self.active() and self.events()[0]["kind"] == "STOP"

    def test_schema_additive_idempotent_preserves_active_trade(self):
        row = self.activate()
        with closing(tracking.connect(self.path)) as db, db:
            db.execute("DROP TABLE manual_trade_h4_v2")  # Synthetic v1 fixture only.
        tracking.provision(self.path)
        tracking.provision(self.path)
        assert self.active()[0]["ref"] == row["ref"]
        assert set(json.loads(self.active()[0]["setups"])) == {"DONKEY", "DONKEY_ORIGINAL"}
        self.values(100, 100, 0)
        with closing(tracking.connect(self.path)) as db:
            assert db.execute("SELECT COUNT(*) FROM manual_trade_candidate_v1").fetchone()[0] == 2
            assert db.execute("SELECT COUNT(*) FROM manual_trade_h4_v2").fetchone()[0] == 1

    def test_schema_failure_rolls_back_without_losing_history(self):
        self.activate()
        with closing(tracking.connect(self.path)) as db, db:
            db.execute("DROP TABLE manual_trade_h4_v2")
            db.execute("CREATE TABLE manual_trade_h4_v2 (wrong INTEGER)")
        with self.assertRaises(sqlite3.DatabaseError):
            tracking.provision(self.path)
        assert len(self.active()) == 1

    def test_active_outside_watchlist_monitored_without_new_setup(self):
        self.activate()
        config = service_fixtures.config()  # TEST-USDT configured; BTC-USDT active only.
        sources = dict(FALCON=guard_harness.SOURCE, DONKEY=fixtures.SOURCE)
        collected = []
        def collect(symbol, intervals, **kwargs):
            collected.append((symbol, intervals))
            return snapshot(closed_price=90, symbol=symbol)
        with patch.object(tracking.ManualTradeTracker, "check_polling"), \
             patch.object(tracking.ManualTradeTracker, "poll"), \
             patch.object(tracking.ManualTradeTracker, "flush"), \
             patch.object(service, "collect_snapshot", side_effect=collect), \
             patch.object(service, "run_once", return_value=dict(status="BLOCKED", reason="NO_SIGNAL")) as run, \
             patch.object(service.time, "time_ns", return_value=LATER*1000000):
            out = service.run_service(config, sources, values=VALUES, ledger_path=self.path,
                stop_event=threading.Event(), service_authorized=True,
                public_data_authorized=True, public_delivery_authorized=True,
                donkey_operator_id=77, max_cycles=1)
        assert out["status"] == "STOPPED", out
        assert ("BTC-USDT", ["4h"]) in collected
        assert all(call.args[2]["symbol"] == "TEST-USDT" for call in run.call_args_list)
        assert not self.active() and self.events()[0]["kind"] == "STOP"
        assert out["live_allowed"] is False


def condition_test(side, close, ema, macd, stop, reason=None):
    def test(self):
        self.activate(side=side)
        self.values(close, ema, macd)
        assert bool(self.active()) is not stop
        assert len(self.events()) == int(stop)
        if reason:
            assert reason in self.events()[0]["text"]
    return test


for name, args in {
    "long_ema": ("LONG", 99, 100, 0, True, "abaixo da EMA20"),
    "long_ema_equal": ("LONG", 100, 100, 0, False),
    "long_macd": ("LONG", 101, 100, -0.01, True, "negativo"),
    "short_ema": ("SHORT", 101, 100, 0, True, "acima da EMA20"),
    "short_ema_equal": ("SHORT", 100, 100, 0, False),
    "short_macd": ("SHORT", 99, 100, 0.01, True, "positivo"),
    "long_no_stop": ("LONG", 101, 100, 1, False),
    "short_no_stop": ("SHORT", 99, 100, -1, False),
}.items():
    setattr(StrategicStop, "test_"+name, condition_test(*args))

if __name__ == "__main__":
    unittest.main()
