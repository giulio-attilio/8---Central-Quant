"""Standalone synthetic tests. Blocks effects before loading repository modules."""
import ast
import copy
import importlib.abc
import json
import platform
import sys
import unittest
from unittest.mock import patch
from datetime import datetime, timezone, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]


def guard(event, args):
    # gethostname is a local OS query used by pandas/platform on Windows;
    # socket creation, resolution and connections remain forbidden.
    if (event.startswith("socket.") and event != "socket.gethostname") or event.startswith(("subprocess.", "os.exec", "os.spawn")) or event in ("os.system", "os.startfile"):
        raise AssertionError("External effects forbidden")
    if event == "open":
        name = str(args[0]).lower()
        # Python's stdlib secrets.py is code, not a credentials file.
        parts = Path(name).parts
        if ".env" in name or "credentials" in name or name.endswith(".pem") or "secrets" in parts:
            raise AssertionError("Sensitive file forbidden")


class BlockOperational(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in {"bots", "main", "broker", "execution_engine", "exchange_manager", "trade_registry", "requests", "ccxt", "upstash_redis", "telegram_notification_policy"}:
            raise AssertionError("Operational import forbidden")


sys.addaudithook(guard)
sys.meta_path.insert(0, BlockOperational())
sys.path.insert(0, str(ROOT))
# pandas asks platform.machine(); Windows may spawn `ver` to answer it.
# A test-only OS metadata fixture avoids allowing that subprocess.
with patch.object(platform, "machine", return_value="AMD64"):
    import falcon_advisory_offline as offline

SOURCE = (ROOT / "bots" / "falcon.py").read_text(encoding="utf-8-sig")
CONFIG = dict(ORB_START_HOUR=9, ORB_START_MINUTE=30, ORB_TRADE_END_HOUR=12,
              ORB_TRADE_END_MINUTE=0, ATR_LEN=14, ADX_LEN=14, EMA_FAST=20,
              EMA_SLOW=50, SCORE_MIN_QUALITY_TO_SIGNAL=55, TP50_R=1.0,
              STOP_ATR_BUFFER=0.1, MIN_ATR_PCT=0.2, MAX_RISK_PCT=3.0,
              MIN_RANGE_ATR=0.4, MAX_RANGE_ATR=4.0, MIN_VOLUME_REL_TO_SIGNAL=1.1,
              MIN_ADX_TO_SIGNAL=12.0, ALIGNMENT_MODE="off")
# Explicit fixture policy, NOT approved parameters for real signals.
POLICY = dict(signal_ttl_ms=60000, snapshot_max_age_ms=10000,
              quote_max_age_ms=5000, max_entry_deviation_fraction=0.005,
              basis="synthetic fixture policy only")


def fixture(setup="FALCON15", side="LONG", day="2026-01-05"):
    stamp = datetime.fromisoformat(day + ("T15:00:00+00:00" if setup == "FALCON15" else "T15:15:00+00:00"))
    now = int(stamp.timestamp() * 1000) + 1000
    frames = {}
    for tf, duration in offline.PERIODS.items():
        forming = now // duration * duration
        rows = []
        for i in range(121):
            price = 100 + i * 0.001
            if side == "SHORT":
                price = 200 - price
            rows.append([forming - (120-i)*duration, price, price+0.5, price-0.5, price, 10.0])
        if tf == "15m":
            price = 101.0 if side == "LONG" else 99.0
            rows[-2] = [rows[-2][0], price, price+0.2, price-0.2, price, 80.0]
        frames[tf] = rows
    return dict(synthetic=True, connected=True, symbol="TESTUSDT", observed_at_ms=now,
                frames=frames, quote=dict(price=101.0 if side == "LONG" else 99.0, at_ms=now)), now


def session(config=None, policy=None, state=None, source=SOURCE):
    return offline.OfflineSignalSession(source, config or CONFIG, policy or POLICY,
        session_id="synthetic-session", prior_state=state if state is not None else
        dict(session_id="synthetic-session", seen=[], revoked=[], last_now_ms=None, context=None))


def original_oracle(snapshot, setup, now, config):
    """Independent direct extraction of original functions; no adapter filtering.

    Comparing shared source is not an independent strategy proof. This tests that
    snapshot injection/projection preserves the original arithmetic and gates.
    """
    frames = {}
    for tf, rows in snapshot["frames"].items():
        frames[tf] = offline.pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
        frames[tf]["dt"] = offline.pd.to_datetime(frames[tf]["ts"], unit="ms", utc=True)
    counts = {}
    def count(key, amount=1):
        counts[key] = counts.get(key, 0) + amount
    ns = dict(config, pd=offline.pd, np=offline.np, dtime=dtime,
              TIMEZONE_NY=ZoneInfo("America/New_York"), TIMEFRAME="15m", BOT_NAME="FALCON",
              funnel_inc=count, safe_fetch_ohlcv=lambda symbol, timeframe, limit: frames[timeframe].tail(limit).copy(),
              data_hora_sp_str=lambda: datetime.fromtimestamp(now/1000, timezone.utc).isoformat(),
              attach_falcon_signal_identity=offline.attach_falcon_signal_identity,
              FalconSignalIdentityConstructionError=offline.FalconSignalIdentityConstructionError)
    nodes = [n for n in ast.parse(SOURCE).body if isinstance(n, ast.FunctionDef) and n.name in offline.FUNCTIONS]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "<offline-original-oracle>", "exec"), ns)
    sig = ns["analyze_symbol_setup"](snapshot["symbol"], setup,
        dict(range_minutes=15 if setup == "FALCON15" else 30, label=setup),
        ns["closed_candles"](frames["15m"]))
    return sig, counts


class OfflineTests(unittest.TestCase):
    def test_four_direction_setup_cases_match_original(self):
        for setup in ("FALCON15", "FALCON30"):
            for side in ("LONG", "SHORT"):
                with self.subTest(setup=setup, side=side):
                    snap, now = fixture(setup, side)
                    original, counts = original_oracle(snap, setup, now, CONFIG)
                    self.assertIsNotNone(original)
                    out = session().evaluate(snap, setup=setup, now_ms=now)
                    self.assertEqual(out["status"], "OFFLINE_PREVIEW", out)
                    for key in ("signal_id", "symbol", "side", "entry", "stop", "tp50", "timeframe"):
                        self.assertEqual(out["signal"][key], original[key])
                    self.assertEqual(out["counters"], counts)
                    self.assertEqual(out["signal"]["candle_closed_at_ms"], original["signal_ts"]+900000)

    def test_filters_match_original(self):
        for changes in ({"MIN_ATR_PCT": 100}, {"MIN_VOLUME_REL_TO_SIGNAL": 100},
                        {"MIN_ADX_TO_SIGNAL": 101}, {"MAX_RISK_PCT": 0.01},
                        {"SCORE_MIN_QUALITY_TO_SIGNAL": 100}, {"MIN_RANGE_ATR": 3}):
            config = dict(CONFIG, **changes)
            snap, now = fixture()
            original, counts = original_oracle(snap, "FALCON15", now, config)
            out = session(config).evaluate(snap, setup="FALCON15", now_ms=now)
            with self.subTest(changes=changes):
                self.assertIsNone(original)
                self.assertEqual(out["status"], "NO_SIGNAL", out)
                self.assertEqual(out["counters"], counts)

    def test_alignment_from_local_frames(self):
        for mode in ("h1", "h1_h4"):
            for side in ("LONG", "SHORT"):
                snap, now = fixture(side=side)
                cfg = dict(CONFIG, ALIGNMENT_MODE=mode)
                original, _ = original_oracle(snap, "FALCON15", now, cfg)
                out = session(cfg).evaluate(snap, setup="FALCON15", now_ms=now)
                self.assertIsNotNone(original)
                self.assertEqual(out["status"], "OFFLINE_PREVIEW", out)
        snap, now = fixture()
        del snap["frames"]["4h"]
        out = session(dict(CONFIG, ALIGNMENT_MODE="h1_h4")).evaluate(snap, setup="FALCON15", now_ms=now)
        self.assertEqual(out["reason"], "FRAMES_REQUIRED")

    def test_duplicate_restart_revocation(self):
        snap, now = fixture()
        first = session()
        out = first.evaluate(snap, setup="FALCON15", now_ms=now)
        self.assertEqual(out["status"], "OFFLINE_PREVIEW", out)
        state = first.state()
        restored = session(state=state)
        self.assertEqual(restored.evaluate(snap, setup="FALCON15", now_ms=now)["reason"], "DUPLICATE")
        restored.revoke(out["signal"]["signal_id"])
        self.assertEqual(session(state=restored.state()).evaluate(snap, setup="FALCON15", now_ms=now)["reason"], "REVOKED")
        self.assertNotEqual(state, restored.state())
        with self.assertRaises(offline.OfflineInputError):
            offline.OfflineSignalSession(SOURCE, CONFIG, POLICY, session_id="synthetic-session", prior_state=None)

    def test_no_input_mutation_and_no_authority(self):
        snap, now = fixture()
        before = copy.deepcopy(snap)
        out = session().evaluate(snap, setup="FALCON15", now_ms=now)
        self.assertEqual(snap, before)
        for key in ("delivery_allowed", "live_allowed", "manual_trade_authorized", "source_qualified"):
            self.assertIs(out[key], False)
        self.assertNotIn("risk_pct", out["signal"])
        self.assertNotIn("status", out["signal"])

    def test_feed_disconnection_and_reconnection(self):
        snap, now = fixture()
        subject = session()
        snap["connected"] = False
        self.assertEqual(subject.evaluate(snap, setup="FALCON15", now_ms=now)["reason"], "FEED_DISCONNECTED")
        snap["connected"] = True
        self.assertEqual(subject.evaluate(snap, setup="FALCON15", now_ms=now)["status"], "OFFLINE_PREVIEW")
        self.assertEqual(subject.evaluate(snap, setup="FALCON15", now_ms=now-1)["reason"], "CLOCK_REGRESSION")

    def test_data_rejections(self):
        cases = (
            (lambda s,n: s.update(synthetic=False), "SYNTHETIC_ONLY"),
            (lambda s,n: s.update(observed_at_ms=n+1), "SNAPSHOT_TIME"),
            (lambda s,n: s.update(observed_at_ms=n-10001), "SNAPSHOT_STALE"),
            (lambda s,n: s["quote"].update(at_ms=n-5001), "QUOTE_STALE"),
            (lambda s,n: s["quote"].update(at_ms=n+1), "QUOTE_TIME"),
            (lambda s,n: s["quote"].update(price=float("nan")), "QUOTE_PRICE"),
            (lambda s,n: s["quote"].update(price=1000), "LEVEL_ALREADY_CROSSED"),
            (lambda s,n: s["quote"].update(price=101.6), "ENTRY_DEVIATION"),
            (lambda s,n: s["frames"]["15m"].pop(40), "CANDLE_GAP_OR_DUPLICATE"),
            (lambda s,n: s["frames"]["15m"][-2].__setitem__(4, float("inf")), "CANDLE_NUMERIC"),
            (lambda s,n: s["frames"]["15m"][-2].__setitem__(2, 1), "CANDLE_OHLC"),
            (lambda s,n: s["frames"]["15m"].pop(), "FRAME_NOT_CURRENT"),
        )
        for change, reason in cases:
            snap, now = fixture()
            change(snap, now)
            with self.subTest(reason=reason):
                out = session().evaluate(snap, setup="FALCON15", now_ms=now)
                self.assertEqual(out["reason"], reason, out)
                self.assertIsNone(out["message"])

    def test_forming_candle_not_used(self):
        snap, now = fixture()
        a = session().evaluate(snap, setup="FALCON15", now_ms=now)
        snap["frames"]["15m"][-1][1:] = [10000, 11000, 9000, 10500, 100000]
        b = session().evaluate(snap, setup="FALCON15", now_ms=now)
        self.assertEqual(a["signal"], b["signal"])

    def test_source_pin_and_top_level_not_executed(self):
        with self.assertRaises(offline.OfflineInputError):
            session(source=SOURCE.replace('score += 20', 'score += 19', 1))
        snap, now = fixture()
        subject = session(source=SOURCE + '\nraise RuntimeError("TOP LEVEL MUST NOT RUN")\n')
        self.assertEqual(subject.evaluate(snap, setup="FALCON15", now_ms=now)["status"], "OFFLINE_PREVIEW")

    def test_configuration_is_explicit(self):
        for changes in ({"ALIGNMENT_MODE":"unknown"}, {"ATR_LEN":True}, {"TP50_R":float("nan")},
                        {"ORB_START_HOUR":25}, {"MIN_RANGE_ATR":10}):
            with self.subTest(changes=changes), self.assertRaises(offline.OfflineInputError):
                session(dict(CONFIG, **changes))
        with self.assertRaises(offline.OfflineInputError):
            session(policy={"basis":"missing"})

    def test_effect_guards(self):
        for event in ("socket.connect", "subprocess.Popen", "os.system"):
            with self.assertRaises(AssertionError):
                sys.audit(event, "synthetic probe")
        for name in ("bots.falcon", "broker", "main", "trade_registry"):
            self.assertNotIn(name, sys.modules)
            with self.assertRaises(AssertionError):
                __import__(name)

    def test_expiry_with_fresh_snapshot_and_quote(self):
        snap, now = fixture()
        closed_at = snap["frames"]["15m"][-1][0]
        for elapsed, status in ((59999, "OFFLINE_PREVIEW"), (60000, "REJECTED")):
            at = closed_at + elapsed
            snap["observed_at_ms"] = at
            snap["quote"]["at_ms"] = at
            out = session().evaluate(snap, setup="FALCON15", now_ms=at)
            self.assertEqual(out["status"], status, out)
            if status == "REJECTED":
                self.assertEqual(out["reason"], "EXPIRED")

    def test_corrected_candle_does_not_emit_second_alert(self):
        snap, now = fixture()
        subject = session()
        out = subject.evaluate(snap, setup="FALCON15", now_ms=now)
        self.assertEqual(out["status"], "OFFLINE_PREVIEW")
        snap["frames"]["15m"][-2][2] += 0.01
        out = subject.evaluate(snap, setup="FALCON15", now_ms=now)
        self.assertEqual(out["reason"], "CANDLE_ALREADY_PRESENTED")

    def test_policy_state_and_non_finite_input_boundaries(self):
        for value in (True, 0, -1, float("inf")):
            with self.assertRaises(offline.OfflineInputError):
                session(policy=dict(POLICY, signal_ttl_ms=value))
        for state in ({}, dict(session_id="wrong", seen=[], revoked=[], last_now_ms=None),
                      dict(session_id="synthetic-session", seen=[], revoked=[], last_now_ms=True)):
            with self.assertRaises(offline.OfflineInputError):
                session(state=state)
        snap, now = fixture()
        self.assertEqual(session().evaluate(snap, setup="FALCON15", now_ms=True)["reason"], "NOW_TIME")
        self.assertEqual(session().evaluate(None, setup="FALCON15", now_ms=now)["reason"], "SYNTHETIC_ONLY")

    def test_incomplete_range_and_undefined_indicators(self):
        snap, now = fixture()
        # Flat OHLC makes ADX undefined; finite raw inputs alone must not pass.
        for row in snap["frames"]["15m"]:
            row[1:] = [100, 100, 100, 100, 10]
        out = session().evaluate(snap, setup="FALCON15", now_ms=now)
        self.assertEqual(out["reason"], "INDICATORS_UNDEFINED")
        # Same current candle but range window has not yet completed for FALCON30.
        snap, now = fixture()
        snap["observed_at_ms"] -= 900000
        snap["quote"]["at_ms"] -= 900000
        for row in snap["frames"]["15m"]:
            row[0] -= 900000
        out = session().evaluate(snap, setup="FALCON30", now_ms=now-900000)
        self.assertEqual(out["reason"], "ORB_INCOMPLETE")

    def test_summer_dst_fixture_matches_existing_ny_window(self):
        snap, now = fixture(day="2026-07-06")
        # 10 NY is 14 UTC in summer, not 15 UTC. Shift synthetic candles only.
        for row in snap["frames"]["15m"]:
            row[0] -= 3600000
        now -= 3600000
        snap["observed_at_ms"] = snap["quote"]["at_ms"] = now
        original, counts = original_oracle(snap, "FALCON15", now, CONFIG)
        out = session().evaluate(snap, setup="FALCON15", now_ms=now)
        self.assertIsNotNone(original)
        self.assertEqual(out["status"], "OFFLINE_PREVIEW", out)
        self.assertEqual(out["signal"]["entry"], original["entry"])
        self.assertEqual(out["counters"], counts)

    def test_checkpoint_rejects_policy_change_and_defensive_copy(self):
        snap, now = fixture()
        subject = session()
        subject.evaluate(snap, setup="FALCON15", now_ms=now)
        checkpoint = subject.state()
        with self.assertRaises(offline.OfflineInputError):
            session(policy=dict(POLICY, signal_ttl_ms=120000), state=checkpoint)
        checkpoint["seen"].clear()
        self.assertTrue(subject.state()["seen"])

    def test_serialized_checkpoint_and_failure_do_not_consume_signal(self):
        snap, now = fixture()
        subject = session()
        bad = copy.deepcopy(snap)
        bad["quote"]["price"] = 101.6
        self.assertEqual(subject.evaluate(bad, setup="FALCON15", now_ms=now)["reason"], "ENTRY_DEVIATION")
        self.assertEqual(subject.state()["seen"], [])
        self.assertEqual(subject.evaluate(snap, setup="FALCON15", now_ms=now)["status"], "OFFLINE_PREVIEW")
        restored = session(state=json.loads(json.dumps(subject.state())))
        self.assertEqual(restored.evaluate(snap, setup="FALCON15", now_ms=now)["reason"], "DUPLICATE")

    def test_invalid_upstream_returns_no_partial_alert(self):
        snap, now = fixture()
        subject = session()
        with patch.object(offline, "attach_falcon_signal_identity", side_effect=RuntimeError("PRIVATE_FIXTURE_DETAIL")):
            out = subject.evaluate(snap, setup="FALCON15", now_ms=now)
        self.assertEqual(out["reason"], "ANALYSIS_FAILED")
        self.assertIsNone(out["message"])
        self.assertNotIn("PRIVATE_FIXTURE_DETAIL", str(out))
        self.assertEqual(subject.state()["seen"], [])


if __name__ == "__main__":
    unittest.main()
