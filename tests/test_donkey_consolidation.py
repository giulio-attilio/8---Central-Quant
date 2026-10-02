"""Offline Donkey consolidation regression; guards precede repository imports."""
import sys
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_falcon_advisory_offline as guard_harness
import test_manual_signal_tracking as base

tracking, delivery = base.tracking, base.delivery
NOW, VALUES = base.NOW, base.VALUES
signal, candidate = base.signal, base.candidate
VARIANTS = ("DONKEY", "DONKEY_ORIGINAL", "EARLY_DONKEY")


class DonkeyConsolidation(base.Harness):
    def dispatch(self, candidates):
        with patch.object(delivery, "_post", side_effect=self.post):
            return delivery.dispatch_public_candidates(
                "DONKEY", candidates, values=VALUES, ledger_path=self.path,
                network_authorized=True, public_delivery_authorized=True,
                manual_tracking=True)

    def activate_pair(self):
        self.send("DONKEY", [signal(setup) for setup in VARIANTS[:2]])
        self.enter_last("DONKEY")
        return self.active()[0]

    def decision(self, setup, side="LONG"):
        with closing(tracking.connect(self.path)) as db:
            return tracking.active_signal_decision(db, setup, "BTC-USDT", side)[0]

    def panel(self, update=2):
        return self.tracker.accept("DONKEY", dict(update_id=update, message={
            "from": dict(id=77, is_bot=False), "chat": dict(id=202),
            "text": "/ativos"}), NOW + update)["outbound"]

    def test_participants_restart_dedup_blocking_and_independence(self):
        self.activate_pair()
        row = self.active()[0]
        assert json.loads(row["setups"]) == list(VARIANTS[:2])
        self.tracker = tracking.ManualTradeTracker(self.path, VALUES, 77, authorized=True)
        assert len(self.active()) == 1
        for setup in VARIANTS[:2]:
            assert self.decision(setup) == "SAME_SIDE_ACTIVE"
            same = self.send("DONKEY", [signal(setup, suffix="next", candle=NOW)])
            assert same["reason"] == "MANUAL_TRADE_SAME_SIDE_ACTIVE"
            opposite = self.send("DONKEY", [signal(setup, side="SHORT", suffix="opposite", candle=NOW)])
            assert opposite["status"] == "CONFIRMED"
            assert "SINAL OPOSTO" in self.sent[-1]["text"]
            assert self.sent[-1]["markup"] is None
            assert len(self.active()) == 1
        assert self.send("DONKEY", [signal("EARLY_DONKEY")])["status"] == "CONFIRMED"
        assert self.sent[-1]["markup"] is not None
        assert self.send("FALCON", [signal()])["status"] == "CONFIRMED"
        assert self.send("DONKEY", [signal(setup) for setup in VARIANTS[:2]])["reason"] == "PRIOR_ATTEMPT_NO_RETRY"

    def test_partial_active_group_preserves_unrelated_candidate(self):
        self.send("DONKEY", [signal("DONKEY")])
        self.enter_last("DONKEY")
        out = self.send("DONKEY", [signal("DONKEY", suffix="next", candle=NOW),
                                   signal("EARLY_DONKEY", suffix="next", candle=NOW)])
        assert out["status"] == "PARTIAL"
        assert len(self.sent) == 2
        assert "Setup: EARLY_DONKEY" in self.sent[-1]["text"]
        assert self.sent[-1]["markup"] is not None

    def test_opposite_participant_does_not_absorb_independent_variant(self):
        self.activate_pair()
        out = self.send("DONKEY", [signal(setup, side="SHORT", suffix="opposite", candle=NOW) for setup in VARIANTS])
        assert out["status"] == "CONFIRMED"
        assert len(self.sent) == 3
        assert "SINAL OPOSTO" in self.sent[1]["text"] and self.sent[1]["markup"] is None
        assert "SINAL MANUAL" in self.sent[2]["text"] and self.sent[2]["markup"] is not None

    def test_panel_one_row_and_stop_update(self):
        self.activate_pair()
        panel = self.panel()
        assert "DONKEY + DONKEY_ORIGINAL | LONG" in panel["text"]
        assert panel["text"].count("1.") == 1 and "2." not in panel["text"]
        assert len(panel["reply_markup"]["inline_keyboard"]) == 1
        button = panel["reply_markup"]["inline_keyboard"][0][0]["callback_data"]
        self.tracker.accept("DONKEY", self.callback("DONKEY", button, update=3), NOW+3)
        self.tracker.accept("DONKEY", dict(update_id=4, message={
            "from": dict(id=77, is_bot=False), "chat": dict(id=202), "text": "99.5"}), NOW+4)
        assert self.active()[0]["stop"] == 99.5

    def test_tp_once_stop_releases_all(self):
        self.activate_pair()
        def quote(price, at):
            return dict(synthetic=False, connected=True, symbol="BTC-USDT",
                        observed_at_ms=at, quote=dict(price=price, at_ms=at))
        self.tracker.observe(quote(102, NOW+10), NOW+10, 1000)
        self.tracker.observe(quote(103, NOW+11), NOW+11, 1000)
        assert all(self.decision(setup) == "SAME_SIDE_ACTIVE" for setup in VARIANTS[:2])
        with closing(tracking.connect(self.path)) as db:
            events = db.execute("SELECT * FROM manual_trade_event_v1").fetchall()
            assert len(events) == 1 and events[0]["kind"] == "TP50"
            assert "DONKEY + DONKEY_ORIGINAL" in events[0]["text"]
        self.tracker.observe(quote(98, NOW+12), NOW+12, 1000)
        assert len(self.active()) == 1  # Numeric stop is a protection reference only.
        with patch("donkey_advisory_offline.closed_h4_indicators", return_value=dict(
                close=97, ema20=99, macd=0, closed_at_ms=NOW+10)):
            self.tracker.observe_h4(dict(symbol="BTC-USDT"), NOW+12, "fixture", {},
                                    frame_max_age_ms=1000, quote_max_age_ms=1000)
        assert not self.active()
        assert all(self.decision(setup) is None for setup in VARIANTS[:2])
        assert self.send("DONKEY", [signal(setup, suffix="released", candle=NOW) for setup in VARIANTS[:2]])["status"] == "CONFIRMED"

    def test_manual_close_releases_all(self):
        self.activate_pair()
        panel = self.panel()
        button = panel["reply_markup"]["inline_keyboard"][0][1]["callback_data"]
        self.tracker.accept("DONKEY", self.callback("DONKEY", button, update=3), NOW+3)
        assert not self.active()
        assert all(self.decision(setup) is None for setup in VARIANTS[:2])
        assert self.send("DONKEY", [signal(setup, suffix="released", candle=NOW) for setup in VARIANTS[:2]])["status"] == "CONFIRMED"

    def test_pending_offer_checks_every_participant_on_click(self):
        self.send("DONKEY", [signal(setup) for setup in VARIANTS[:2]])
        first = self.sent[0]
        self.send("DONKEY", [signal("DONKEY_ORIGINAL", suffix="other", candle=NOW)])
        self.enter_last("DONKEY")
        button = first["markup"]["inline_keyboard"][0][0]["callback_data"]
        response = self.tracker.accept("DONKEY", self.callback(
            "DONKEY", button, message_id=first["message_id"], update=2), NOW+2)
        assert "ativo" in response["answer"] and len(self.active()) == 1

    def test_ambiguous_transport_reserves_all_without_retry(self):
        candidates = [candidate(signal(setup)) for setup in VARIANTS]
        with patch.object(delivery, "_post", side_effect=TimeoutError):
            out = delivery.dispatch_public_candidates("DONKEY", candidates, values=VALUES,
                ledger_path=self.path, network_authorized=True,
                public_delivery_authorized=True, manual_tracking=True)
        assert out["status"] == "UNKNOWN"
        assert self.dispatch(candidates)["reason"] == "PRIOR_ATTEMPT_NO_RETRY"
        assert not self.sent

    def test_btc_example(self):
        out = self.send("DONKEY", [signal(setup, entry=84834.1, stop=84025.0635,
                   tp50=85643.1365) for setup in VARIANTS[:2]])
        assert out["status"] == "CONFIRMED"
        text = self.sent[0]["text"]
        assert "Entrada: 84834.1" in text and "Stop de prote\u00e7\u00e3o: 84025.0635" in text
        assert "TP50: 85643.1365" in text and "0.95%" in text


def consolidated_test(setups, side="LONG"):
    def test(self):
        out = self.send("DONKEY", [signal(setup, side=side) for setup in setups])
        assert out["status"] == "CONFIRMED" and out["live_allowed"] is False
        assert len(self.sent) == 1
        assert "Confirma\u00e7\u00e3o: " + " + ".join(setups) in self.sent[0]["text"]
        assert len(self.sent[0]["markup"]["inline_keyboard"]) == 1
        assert len(self.sent[0]["markup"]["inline_keyboard"][0]) == 1
        with closing(tracking.connect(self.path)) as db:
            assert db.execute("SELECT COUNT(*) FROM delivery_v1").fetchone()[0] == len(setups)
            assert db.execute("SELECT COUNT(*) FROM manual_trade_candidate_v1").fetchone()[0] == len(setups)
            assert db.execute("SELECT COUNT(DISTINCT message_id) FROM delivery_v1").fetchone()[0] == 1
        self.enter_last("DONKEY")
        self.enter_last("DONKEY", update=2)
        assert len(self.active()) == 1
        assert set(json.loads(self.active()[0]["setups"])) == set(setups)
    return test


for name, setups in (("original", VARIANTS[:2]), ("early", (VARIANTS[0], VARIANTS[2])),
                     ("original_early", VARIANTS[1:]), ("three", VARIANTS)):
    setattr(DonkeyConsolidation, "test_identical_"+name, consolidated_test(setups))
setattr(DonkeyConsolidation, "test_identical_short", consolidated_test(VARIANTS, "SHORT"))


def different_test(field, value, operational=False):
    def test(self):
        first, second = candidate(signal("DONKEY")), candidate(signal("DONKEY_ORIGINAL"))
        (second if operational else second["signal"])[field] = value
        out = self.dispatch([first, second])
        assert out["status"] == "CONFIRMED" and len(self.sent) == 2
        assert all("Setup:" in sent["text"] for sent in self.sent)
    return test


for field, value, operational in (
    ("entry", 100.0000000001, False), ("stop", 97.9999999999, False),
    ("tp50", 102.0000000001, False), ("symbol", "ETH-USDT", False),
    ("candle_closed_at_ms", NOW-2, False),
    ("expires_at_ms", NOW+899999, True), ("validity_basis", "different policy", True),
    ("data_valid_until_ms", NOW+59999, True)):
    setattr(DonkeyConsolidation, "test_separate_"+field, different_test(field, value, operational))


def test_direction(self):
    assert self.send("DONKEY", [signal("DONKEY"), signal("DONKEY_ORIGINAL", side="SHORT")])["status"] == "CONFIRMED"
    assert len(self.sent) == 2
DonkeyConsolidation.test_separate_direction = test_direction


def test_invalid_timeframe(self):
    first, second = candidate(signal("DONKEY")), candidate(signal("DONKEY_ORIGINAL"))
    second["signal"]["timeframe"] = "1h"
    assert delivery._same_economics([first, second]) is False
    out = self.dispatch([first, second])
    assert out["status"] == "PARTIAL" and len(self.sent) == 1
    assert out["deliveries"][1]["status"] == "BLOCKED"
DonkeyConsolidation.test_separate_invalid_timeframe = test_invalid_timeframe


def test_canonical_numbers_and_order(self):
    first = signal("DONKEY_ORIGINAL", entry=100, stop=98, tp50=102)
    second = signal("DONKEY", entry=100.0, stop=98.0, tp50=102.0)
    assert self.send("DONKEY", [first, second])["status"] == "CONFIRMED"
    assert len(self.sent) == 1
    assert "Confirma\u00e7\u00e3o: DONKEY + DONKEY_ORIGINAL" in self.sent[0]["text"]
DonkeyConsolidation.test_canonical_numbers_and_order = test_canonical_numbers_and_order


def test_grouped_same_side_is_suppressed(self):
    self.activate_pair()
    out = self.send("DONKEY", [signal(setup, suffix="next", candle=NOW) for setup in VARIANTS[:2]])
    assert out["reason"] == "MANUAL_TRADE_SAME_SIDE_ACTIVE"
    assert len(self.sent) == 1
DonkeyConsolidation.test_grouped_same_side_is_suppressed = test_grouped_same_side_is_suppressed


def test_tracking_change_fails_closed(self):
    with patch.object(tracking, "active_signal_decision", side_effect=[
            (None, None), (None, None), (None, None), ("SAME_SIDE_ACTIVE", "LONG")]):
        out = self.send("DONKEY", [signal(setup) for setup in VARIANTS[:2]])
    assert out["reason"] == "MANUAL_TRACKING_GROUP_CHANGED"
    assert not self.sent
    with closing(tracking.connect(self.path)) as db:
        assert db.execute("SELECT COUNT(*) FROM delivery_v1").fetchone()[0] == 0
DonkeyConsolidation.test_tracking_change_fails_closed = test_tracking_change_fails_closed


def test_network_and_broker_blocked(self):
    import socket
    import importlib
    with self.assertRaises(AssertionError):
        socket.socket()
    with self.assertRaises(AssertionError):
        importlib.import_module("broker")
DonkeyConsolidation.test_network_and_broker_blocked = test_network_and_broker_blocked
