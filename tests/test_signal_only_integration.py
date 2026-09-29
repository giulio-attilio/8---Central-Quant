"""Offline integration only. Run directly with -I -B, no pytest discovery.

Reuse the existing offline test harness: it installs audit/import blockers before
repository imports and provides synthetic Falcon fixtures. Never uses real env.
"""
import copy
import importlib.util
import json
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_falcon_advisory_offline as harness
import donkey_advisory_offline as donkey
import telegram_signal_delivery as delivery
import signal_only_workflow as workflow

ROOT = harness.ROOT
SOURCE = (ROOT / "bots/donkey.py").read_text(encoding="utf-8-sig")
CONFIG = dict(EMA_FAST=9, EMA20=20, EMA_MID=21, EMA50=50, EMA200=200,
              ATR_LEN=14, ADX_LEN=14, SUPERTREND_PERIOD=10,
              DONKEY_MACD_FAST=12, DONKEY_MACD_SLOW=26, DONKEY_MACD_SIGNAL=9,
              SUPERTREND_FACTOR=3.5, ADX_MIN=20, SPIKE_RANGE_ATR_MULT=4,
              SPIKE_BODY_ATR_MULT=3, DONKEY_BUFFER_PCT=0.1, TP50_R=1,
              DONKEY_MAX_RISK_PCT=5, ENABLE_SPIKE_FILTER=True, USE_MAX_RISK_FILTER=True)
# Not real tokens/destinations: passed only to a fake HTTP boundary.
VALUES = dict(FALCON_TOKEN="1:" + "A" * 30, FALCON_CHAT_ID="101",
              DONKEY_H4_TOKEN="2:" + "B" * 30, DONKEY_H4_CHAT_ID="202",
              CENTRAL_TELEGRAM_BOT_TOKEN="3:" + "C" * 30, CENTRAL_TELEGRAM_CHAT_ID="303")


def donkey_fixture(side="LONG"):
    now = 1767657600000 + 1000  # Fixture time, not system clock.
    frames = {}
    for tf, duration in donkey.PERIODS.items():
        forming = now // duration * duration
        rows = []
        for i in range(200):
            price = 100 + i * 0.1 if side == "LONG" else 150 - i * 0.1
            rows.append([forming - (199-i)*duration, price, price+0.5, price-0.5, price, 100.])
        frames[tf] = rows
    return dict(synthetic=True, connected=True, symbol="TESTUSDT", observed_at_ms=now,
                frames=frames, quote=dict(price=frames["4h"][-2][4], at_ms=now)), now


class PublicPreviewTests(unittest.TestCase):
    def public_fixture(self, bot):
        # Fabricated records in the public input schema, never fetched market data.
        snap, now = donkey_fixture() if bot == "DONKEY" else harness.fixture()
        snap.update(synthetic=False, source="BINGX_PUBLIC_SWAP", symbol="TEST-USDT",
                    frame_received_at_ms={tf: now for tf in snap["frames"]},
                    source_qualified=False, delivery_allowed=False, live_allowed=False,
                    manual_trade_authorized=False)
        return snap, now

    def test_public_preview_preserves_origin_and_never_sends(self):
        for bot, text, config, setups in (
            ("FALCON", harness.SOURCE, harness.CONFIG, ("FALCON15",)),
            ("DONKEY", SOURCE, CONFIG, ("DONKEY", "DONKEY_ORIGINAL"))):
            snap, now = self.public_fixture(bot)
            original = copy.deepcopy(snap)
            for setup in setups:
                with self.subTest(bot=bot, setup=setup), patch.object(delivery, "_post") as post:
                    out = workflow.run_once(bot, text, snap, config, harness.POLICY,
                        setup=setup, now_ms=now, public_data_authorized=True, network_authorized=True)
                    self.assertEqual(out["status"], "LOCAL_PUBLIC_PREVIEW", out)
                    self.assertIs(out["analysis"]["signal"]["synthetic"], False)
                    self.assertEqual(out["analysis"]["signal"]["source"], "BINGX_PUBLIC_SWAP")
                    self.assertIn("DADOS PÚBLICOS", out["analysis"]["message"])
                    self.assertNotIn("SIMULAÇÃO", out["analysis"]["message"])
                    self.assertIs(out["analysis"]["delivery_allowed"], False)
                    self.assertIsNone(out["delivery"])
                    post.assert_not_called()
            self.assertEqual(snap, original)

    def test_public_missing_policy_or_receipt_fails_closed(self):
        for bot, text, config, setup in (("FALCON", harness.SOURCE, harness.CONFIG, "FALCON15"),
                                          ("DONKEY", SOURCE, CONFIG, "DONKEY")):
            snap, now = self.public_fixture(bot)
            for policy, damaged in ((None, False), (harness.POLICY, True)):
                candidate = copy.deepcopy(snap)
                if damaged:
                    candidate["frame_received_at_ms"] = {}
                with patch.object(delivery, "_post") as post:
                    out = workflow.run_once(bot, text, candidate, config, policy,
                        setup=setup, now_ms=now, public_data_authorized=True, network_authorized=True)
                    self.assertEqual(out["status"], "BLOCKED", out)
                    post.assert_not_called()

    def test_public_cannot_enter_synthetic_transport(self):
        snap, now = self.public_fixture("DONKEY")
        out = workflow.run_once("DONKEY", SOURCE, snap, CONFIG, harness.POLICY,
            setup="DONKEY", now_ms=now, public_data_authorized=True)
        with patch.object(delivery, "_post") as post:
            result = delivery.dispatch_synthetic("DONKEY", out["analysis"]["signal"],
                values=VALUES, ledger_path="not-created.sqlite", now_ms=now,
                expires_at_ms=now+1000, validity_basis="test only", network_authorized=True)
            self.assertNotEqual(result["status"], "ACCEPTED")
            post.assert_not_called()


class DonkeyTests(unittest.TestCase):
    def test_all_selected_variants_independent(self):
        snap, now = donkey_fixture()
        with patch.object(delivery, "_post") as post:
            out = workflow.preview_donkey_variants(SOURCE, snap, CONFIG, harness.POLICY, now_ms=now)
        self.assertEqual(tuple(out), ("DONKEY", "DONKEY_ORIGINAL", "EARLY_DONKEY"))
        self.assertEqual(out["DONKEY"]["status"], "LOCAL_PREVIEW")
        self.assertEqual(out["DONKEY_ORIGINAL"]["status"], "LOCAL_PREVIEW")
        self.assertEqual(out["EARLY_DONKEY"]["reason"], "NO_SIGNAL")
        signals = [out[k]["analysis"]["signal"] for k in ("DONKEY", "DONKEY_ORIGINAL")]
        self.assertNotEqual(signals[0]["signal_id"], signals[1]["signal_id"])
        for setup in ("DONKEY", "DONKEY_ORIGINAL"):
            self.assertIn(setup, out[setup]["analysis"]["message"])
        post.assert_not_called()

    def analyze(self, snap=None, setup="DONKEY", **changes):
        fixture, now = donkey_fixture()
        args = dict(source=SOURCE, snapshot=fixture if snap is None else snap, config=CONFIG,
                    policy=harness.POLICY, setup=setup, now_ms=now)
        args.update(changes)
        return donkey.analyze(**args)

    def test_sides_variants_and_reference_arithmetic(self):
        for side in ("LONG", "SHORT"):
            snap, now = donkey_fixture(side)
            for setup in ("DONKEY", "DONKEY_ORIGINAL"):
                out = self.analyze(snap, setup=setup, now_ms=now)
                self.assertEqual(out["status"], "OFFLINE_PREVIEW", out)
                sig = out["signal"]
                self.assertEqual(sig["side"], side)
                row = snap["frames"]["4h"][-2]
                stop = row[3]*0.999 if side == "LONG" else row[2]*1.001
                target = row[4] + (row[4]-stop) if side == "LONG" else row[4] - (stop-row[4])
                self.assertAlmostEqual(sig["stop"], stop)
                self.assertAlmostEqual(sig["tp50"], target)
                self.assertEqual(sig["entry"], row[4])
                self.assertEqual(sig["candle_closed_at_ms"], row[0]+14400000)
                self.assertNotIn("donkey_risk_usdt", sig)
            self.assertEqual(self.analyze(snap, setup="EARLY_DONKEY", now_ms=now)["status"], "NO_SIGNAL")

    def test_fail_closed_data(self):
        for mutation in (lambda s: s.update(synthetic=False),
                         lambda s: s.update(connected=False),
                         lambda s: s["frames"]["4h"].pop(-3),
                         lambda s: s["frames"]["4h"][-2].__setitem__(4, float("nan")),
                         lambda s: s["quote"].update(at_ms=0),
                         lambda s: s["quote"].update(price=999),
                         lambda s: s["frames"].pop("1d")):
            snap, now = donkey_fixture()
            mutation(snap)
            out = self.analyze(snap, setup="DONKEY_ORIGINAL", now_ms=now)
            self.assertEqual(out["status"], "REJECTED", out)
            self.assertIsNone(out["message"])

    def test_pinned_source_and_no_mutation(self):
        snap, _ = donkey_fixture()
        before = copy.deepcopy(snap)
        out = self.analyze(snap, source=SOURCE + '\nraise RuntimeError("STARTUP MUST NOT RUN")\n')
        self.assertEqual(out["status"], "OFFLINE_PREVIEW", out)
        self.assertEqual(snap, before)
        self.assertEqual(self.analyze(source=SOURCE.replace('entry = close', 'entry = close + 1'))["reason"], "SOURCE_CHANGED_REVIEW_REQUIRED")

    def test_forming_excluded_expiry_and_policy(self):
        snap, now = donkey_fixture()
        first = self.analyze(snap)
        snap["frames"]["4h"][-1][1:5] = [999, 1000, 998, 999]
        self.assertEqual(self.analyze(snap)["signal"], first["signal"])
        snap["observed_at_ms"] = snap["quote"]["at_ms"] = now + 60000
        self.assertEqual(self.analyze(snap, now_ms=now+60000)["reason"], "EXPIRED")
        self.assertEqual(self.analyze(policy={})["status"], "REJECTED")

    def test_early_reversal_both_sides(self):
        for side in ("LONG", "SHORT"):
            snap, now = donkey_fixture("SHORT")
            for i, row in enumerate(snap["frames"]["4h"]):
                if i >= 189:
                    price = 130.5 + (i-189)*0.6
                    row[1:5] = [price, price+0.5, price-0.5, price]
                if side == "SHORT":
                    op, high, low, close = row[1:5]
                    row[1:5] = [300-op, 300-low, 300-high, 300-close]
            snap["quote"]["price"] = snap["frames"]["4h"][-2][4]
            out = self.analyze(snap, setup="EARLY_DONKEY", now_ms=now)
            self.assertEqual(out["status"], "OFFLINE_PREVIEW", out)
            self.assertEqual(out["signal"]["side"], side)

    def test_daily_alignment_and_risk_filter(self):
        snap, now = donkey_fixture()
        bearish, _ = donkey_fixture("SHORT")
        snap["frames"]["1d"] = bearish["frames"]["1d"]
        self.assertEqual(self.analyze(snap, setup="DONKEY_ORIGINAL")["status"], "NO_SIGNAL")
        cfg = dict(CONFIG, DONKEY_MAX_RISK_PCT=0.01)
        self.assertEqual(self.analyze(setup="DONKEY_ORIGINAL", config=cfg)["status"], "NO_SIGNAL")

    def test_local_workflow_without_credentials(self):
        snap, now = donkey_fixture()
        with patch.object(delivery, "_post") as post:
            out = workflow.run_once("DONKEY", SOURCE, snap, CONFIG, harness.POLICY,
                                    setup="DONKEY", now_ms=now)
            self.assertEqual(out["status"], "LOCAL_PREVIEW", out)
            snap["synthetic"] = False
            out = workflow.run_once("DONKEY", SOURCE, snap, CONFIG, harness.POLICY,
                                    setup="DONKEY", now_ms=now, network_authorized=True)
            self.assertEqual(out["reason"], "REAL_MARKET_SOURCE_NOT_AUTHORIZED")
            post.assert_not_called()


class TelegramTests(unittest.TestCase):
    def test_public_workflow_delivery_and_deduplication(self):
        for bot, source, cfg, setup in (("FALCON", harness.SOURCE, harness.CONFIG, "FALCON15"),
                                        ("DONKEY", SOURCE, CONFIG, "DONKEY_ORIGINAL")):
            snapshot, now = PublicPreviewTests().public_fixture(bot)
            path = str(Path(self.temp.name) / (bot + ".sqlite"))
            delivery.initialize_ledger(path)
            kwargs = dict(setup=setup, now_ms=now, public_data_authorized=True,
                          public_delivery_authorized=True, network_authorized=True,
                          values=VALUES, ledger_path=path)
            # UTC is fixed in this fixture; elapsed time must also be fixed so
            # a faster second analysis cannot simulate a clock rollback.
            with patch.object(delivery, "_post", side_effect=self.accepted), \
                 patch.object(workflow.time, "monotonic", return_value=0):
                result = workflow.run_once(bot, source, snapshot, cfg, harness.POLICY, **kwargs)
                self.assertEqual(result["status"], "CONFIRMED", result)
                again = workflow.run_once(bot, source, snapshot, cfg, harness.POLICY, **kwargs)
                self.assertEqual(again["reason"], "PRIOR_ATTEMPT_NO_RETRY", again)
            text = self.calls[-1][2]
            self.assertIn("SINAL INFORMATIVO", text)
            self.assertIn("Nenhuma ordem enviada", text)
            self.assertNotIn("SIMULAÇÃO", text)
            self.assertNotIn("PRÉVIA LOCAL", text)
            self.assertIs(result["live_allowed"], False)
        self.assertEqual([call[1] for call in self.calls], ["101", "202"])

    def test_public_transport_explicit_gates_and_data_deadline(self):
        signal = dict(self.signal, synthetic=False, source="BINGX_PUBLIC_SWAP")
        kwargs = dict(values=VALUES, ledger_path=self.path, now_ms=self.now,
                      expires_at_ms=self.now+10000, data_valid_until_ms=self.now+1000,
                      validity_basis="fixture only", network_authorized=True,
                      public_delivery_authorized=True)
        with patch.object(delivery, "_post") as post:
            for changes in (dict(network_authorized=False), dict(public_delivery_authorized=False),
                            dict(data_valid_until_ms=self.now), dict(data_valid_until_ms=True),
                            dict(data_valid_until_ms=self.now+10001)):
                result = delivery.dispatch_public_signal("FALCON", signal, **dict(kwargs, **changes))
                self.assertEqual(result["status"], "BLOCKED")
            with patch.object(delivery.time, "monotonic", side_effect=[0, 2]):
                result = delivery.dispatch_public_signal("FALCON", signal, **kwargs)
            self.assertEqual(result["reason"], "EXPIRED_BEFORE_HTTP")
            post.assert_not_called()

    def test_public_timeout_is_unknown_without_retry(self):
        signal = dict(self.signal, synthetic=False, source="BINGX_PUBLIC_SWAP")
        kwargs = dict(values=VALUES, ledger_path=self.path, now_ms=self.now,
                      expires_at_ms=self.now+10000, data_valid_until_ms=self.now+1000,
                      validity_basis="fixture only", network_authorized=True,
                      public_delivery_authorized=True)
        with patch.object(delivery, "_post", side_effect=TimeoutError("sensitive sentinel")) as post:
            result = delivery.dispatch_public_signal("FALCON", signal, **kwargs)
            self.assertEqual(result["status"], "UNKNOWN")
            self.assertNotIn("sensitive sentinel", str(result))
            result = delivery.dispatch_public_signal("FALCON", signal, **kwargs)
            self.assertEqual(result["reason"], "PRIOR_ATTEMPT_NO_RETRY")
            self.assertEqual(post.call_count, 1)

    def test_variants_same_candle_are_separate_alerts(self):
        snap, now = donkey_fixture()
        out = donkey.analyze(SOURCE, snap, CONFIG, harness.POLICY, setup="DONKEY", now_ms=now)
        with patch.object(delivery, "_post", side_effect=self.accepted):
            for setup in workflow.DONKEY_VARIANTS:
                # Transport fixture only: no claim all strategies trigger together.
                signal = dict(out["signal"], setup=setup, signal_id="fixture:" + setup)
                args = dict(bot="DONKEY", signal=signal, now_ms=now,
                            expires_at_ms=out["expires_at_ms"])
                self.assertEqual(self.send(**args)["status"], "CONFIRMED")
                self.assertEqual(self.send(**args)["reason"], "PRIOR_ATTEMPT_NO_RETRY")
        self.assertEqual(len(self.calls), 3)
        for setup, call in zip(workflow.DONKEY_VARIANTS, self.calls):
            self.assertEqual(call[1], "202")
            self.assertIn(setup + " |", call[2])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = str(Path(self.temp.name) / "delivery.sqlite")
        delivery.initialize_ledger(self.path)
        snap, self.now = harness.fixture()
        self.out = harness.session().evaluate(snap, setup="FALCON15", now_ms=self.now)
        self.signal = self.out["signal"]
        self.calls = []

    def accepted(self, token, chat, text, timeout):
        self.calls.append((token, chat, text))
        return 200, dict(ok=True, result=dict(message_id=17, chat={"id": int(chat)}, text=text))

    def send(self, **changes):
        args = dict(bot="FALCON", signal=self.signal, values=VALUES, ledger_path=self.path,
                    now_ms=self.now, expires_at_ms=self.now+10000, validity_basis="fixture only",
                    network_authorized=True)
        args.update(changes)
        return delivery.dispatch_synthetic(**args)

    def test_two_bot_pipeline_and_routes(self):
        snap, now = donkey_fixture()
        out = donkey.analyze(SOURCE, snap, CONFIG, harness.POLICY, setup="DONKEY_ORIGINAL", now_ms=now)
        with patch.object(delivery, "_post", side_effect=self.accepted):
            first = self.send(bot="DONKEY", signal=out["signal"], now_ms=now, expires_at_ms=out["expires_at_ms"])
            # Separate synthetic sessions may have different time axes; use another ledger.
            path = str(Path(self.temp.name) / "falcon.sqlite")
            delivery.initialize_ledger(path)
            second = self.send(ledger_path=path)
        self.assertEqual(first["status"], "CONFIRMED", first)
        self.assertEqual(second["status"], "CONFIRMED", second)
        self.assertEqual([c[1] for c in self.calls], ["202", "101"])
        self.assertTrue(all("NÃO OPERAR" in c[2] for c in self.calls))

    def test_default_disabled_and_validation_before_http(self):
        with patch.object(delivery, "_post") as post:
            for args in (dict(network_authorized=False), dict(values={}), dict(bot="CENTRAL"),
                         dict(bot="DONKEY"), dict(now_ms=self.now+10000),
                         dict(ledger_path=str(Path(self.temp.name)/"missing.sqlite")),
                         dict(signal=dict(self.signal, synthetic=False)),
                         dict(signal=dict(self.signal, setup=[]))):
                self.assertEqual(self.send(**args)["status"], "BLOCKED")
            post.assert_not_called()

    def test_duplicate_restart_and_correction(self):
        with patch.object(delivery, "_post", side_effect=self.accepted):
            self.assertEqual(self.send()["status"], "CONFIRMED")
            self.assertEqual(self.send()["reason"], "PRIOR_ATTEMPT_NO_RETRY")
            revised = dict(self.signal, signal_id="corrected", entry=self.signal["entry"]+0.01)
            self.assertEqual(self.send(signal=revised)["reason"], "PRIOR_ATTEMPT_NO_RETRY")
        self.assertEqual(len(self.calls), 1)

    def test_timeout_redaction_and_no_retry(self):
        with patch.object(delivery, "_post", side_effect=TimeoutError(VALUES["FALCON_TOKEN"])) as post:
            out = self.send()
            self.assertEqual(out["status"], "UNKNOWN")
            self.assertNotIn(VALUES["FALCON_TOKEN"], str(out))
            self.assertEqual(self.send()["reason"], "PRIOR_ATTEMPT_NO_RETRY")
            self.assertEqual(post.call_count, 1)

    def test_response_validation(self):
        for i, reply in enumerate(((200, {"ok": True}), (500, {"ok": False, "error_code": 500}),
                                  (200, {"ok": True, "result": {"message_id": True, "chat": {"id": 101}}}),
                                  (302, None), (200, None))):
            path = str(Path(self.temp.name)/f"case{i}.sqlite")
            delivery.initialize_ledger(path)
            with patch.object(delivery, "_post", return_value=reply):
                self.assertEqual(self.send(ledger_path=path)["status"], "UNKNOWN")

    def test_rejection_rate_limit_pause_and_clock(self):
        with patch.object(delivery, "_post", return_value=(429, dict(ok=False, error_code=429, parameters={"retry_after": 30}))):
            self.assertEqual(self.send()["status"], "REJECTED")
        with patch.object(delivery, "_post") as post:
            self.assertEqual(self.send()["reason"], "RATE_LIMIT_PAUSE")
            self.assertEqual(self.send(now_ms=self.now-1, signal=dict(self.signal, generated_at_ms=self.now-2))["reason"], "CLOCK_REGRESSION")
            post.assert_not_called()

    def test_no_fallback_or_collision(self):
        values = dict(VALUES, FALCON_TOKEN=VALUES["CENTRAL_TELEGRAM_BOT_TOKEN"], FALCON_CHAT_ID="303")
        with patch.object(delivery, "_post") as post:
            self.assertEqual(self.send(values=values)["reason"], "DESTINATION_COLLISION")
            rotated = dict(VALUES, FALCON_TOKEN="3:" + "D" * 30, FALCON_CHAT_ID="303")
            self.assertEqual(self.send(values=rotated)["reason"], "DESTINATION_COLLISION")
            for key in ("FALCON_TOKEN", "FALCON_CHAT_ID"):
                values = dict(VALUES)
                del values[key]
                self.assertEqual(self.send(values=values)["status"], "BLOCKED")
            post.assert_not_called()

    def test_ledger_stores_no_token_or_message(self):
        with patch.object(delivery, "_post", side_effect=self.accepted):
            self.send()
        with closing(sqlite3.connect(self.path)) as db:
            dump = "\n".join(db.iterdump())
        self.assertNotIn(VALUES["FALCON_TOKEN"], dump)
        self.assertNotIn("NÃO OPERAR", dump)

    def test_concurrent_duplicate_reservation(self):
        with patch.object(delivery, "_post", side_effect=self.accepted):
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(lambda _: self.send(), range(2)))
        self.assertEqual(sorted(x["status"] for x in results), ["BLOCKED", "CONFIRMED"])
        self.assertEqual(len(self.calls), 1)

    def test_crash_after_reservation_never_retries(self):
        with patch.object(delivery, "_post", side_effect=RuntimeError("lost reply")):
            self.send()
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute("SELECT status FROM delivery_v1").fetchone()[0], "UNKNOWN")
        with patch.object(delivery, "_post") as post:
            self.assertEqual(self.send()["reason"], "PRIOR_ATTEMPT_NO_RETRY")
            post.assert_not_called()

    def test_http_boundary_serialization_and_no_paid_option(self):
        class Response:
            status = 200
            def read(self, size):
                return b'{"ok":false,"error_code":400}'
        class Connection:
            def __init__(self):
                self.requests = []
                self.closed = False
            def request(self, *args, **kwargs):
                self.requests.append((args, kwargs))
            def getresponse(self):
                return Response()
            def close(self):
                self.closed = True
        conn = Connection()
        with patch.object(delivery.http.client, "HTTPSConnection", return_value=conn) as factory:
            status, body = delivery._post(VALUES["FALCON_TOKEN"], "101", "synthetic <>&", 10)
        self.assertEqual(factory.call_args.args[0], "api.telegram.org")
        self.assertEqual(status, 200)
        self.assertTrue(conn.closed)
        args, kwargs = conn.requests[0]
        self.assertEqual(args[0], "POST")
        self.assertTrue(args[1].endswith("/sendMessage"))
        payload = json.loads(kwargs["body"])
        self.assertIs(payload["allow_paid_broadcast"], False)
        self.assertNotIn("parse_mode", payload)
        self.assertEqual(payload["chat_id"], "101")

    def test_expired_while_waiting_for_ledger_never_posts(self):
        with patch.object(delivery.time, "monotonic", side_effect=[0, 20]), patch.object(delivery, "_post") as post:
            self.assertEqual(self.send()["reason"], "EXPIRED_BEFORE_HTTP")
            post.assert_not_called()

    def test_workflow_end_to_end_and_repeat(self):
        snap, now = harness.fixture()
        with patch.object(delivery, "_post", side_effect=self.accepted), patch.object(workflow.time, "monotonic", return_value=0):
            def run():
                return workflow.run_once("FALCON", harness.SOURCE, snap, harness.CONFIG,
                    harness.POLICY, setup="FALCON15", now_ms=now, values=VALUES,
                    ledger_path=self.path, network_authorized=True)
            self.assertEqual(run()["status"], "CONFIRMED")
            self.assertEqual(run()["reason"], "PRIOR_ATTEMPT_NO_RETRY")
        self.assertEqual(len(self.calls), 1)


if __name__ == "__main__":
    unittest.main()
