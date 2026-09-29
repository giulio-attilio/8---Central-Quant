"""Offline fixtures only; no live smoke call belongs in this test suite."""
import importlib.util
import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


def guard(event, args):
    if event.startswith(("socket.", "subprocess.", "os.exec", "os.spawn")) or event in ("os.system", "os.startfile"):
        raise AssertionError("External effects forbidden")
    if event == "open" and any(x in str(args[0]).lower() for x in (".env", "credentials", ".pem")):
        raise AssertionError("Sensitive file forbidden")


sys.addaudithook(guard)
spec = importlib.util.spec_from_file_location("public_source", Path(__file__).resolve().parents[1] / "bingx_public_signal_source.py")
source = importlib.util.module_from_spec(spec)
spec.loader.exec_module(source)


class PublicTests(unittest.TestCase):
    def snapshot(self):
        return dict(synthetic=False, connected=True, source="BINGX_PUBLIC_SWAP",
                    symbol="BTC-USDT", observed_at_ms=1800100,
                    frames={"15m": source.normalize_candles(self.candles(), "15m")},
                    frame_received_at_ms={"15m": 1800050},
                    quote=dict(price=100, at_ms=1800090), source_qualified=False,
                    delivery_allowed=False, live_allowed=False, manual_trade_authorized=False)

    def validate(self, snapshot, **kwargs):
        options = dict(now_ms=1800200, frame_max_age_ms=1000, quote_max_age_ms=1000)
        options.update(kwargs)
        return source.validate_snapshot(snapshot, **options)

    def test_intake_copy_and_no_qualification(self):
        snapshot = self.snapshot()
        snapshot["account"] = "must not project"
        original = copy.deepcopy(snapshot)
        out = self.validate(snapshot)
        self.assertEqual(snapshot, original)
        self.assertNotIn("account", out)
        self.assertIs(out["input_validated"], True)
        for flag in ("synthetic", "source_qualified", "delivery_allowed", "live_allowed", "manual_trade_authorized"):
            self.assertIs(out[flag], False)
        out["frames"]["15m"][0][1] = 999
        self.assertEqual(snapshot, original)

    def test_intake_checks_each_receipt_and_quote(self):
        for key, value in (("frame_received_at_ms", {"15m": 1799000}),
                           ("frame_received_at_ms", {"15m": 1800101}),
                           ("frame_received_at_ms", {}),
                           ("quote", dict(price=100, at_ms=1799000)),
                           ("quote", dict(price=100, at_ms=1800101)),
                           ("observed_at_ms", 1800201)):
            snapshot = self.snapshot()
            snapshot[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(source.PublicDataError):
                self.validate(snapshot)

    def test_intake_candle_boundary_and_order(self):
        with self.assertRaisesRegex(source.PublicDataError, "FRAME_NOT_CURRENT"):
            self.validate(self.snapshot(), now_ms=2700000, frame_max_age_ms=1000000,
                          quote_max_age_ms=1000000)
        snapshot = self.snapshot()
        snapshot["frames"]["15m"].reverse()
        with self.assertRaisesRegex(source.PublicDataError, "CANDLE_ORDER"):
            self.validate(snapshot)

    def test_intake_requires_policy_and_unqualified_public_input(self):
        for value in (0, -1, True, 1.5, None):
            with self.subTest(value=value), self.assertRaises(source.PublicDataError):
                self.validate(self.snapshot(), frame_max_age_ms=value)
        for field, value in (("synthetic", True), ("source", "OTHER"),
                             ("delivery_allowed", True), ("connected", False)):
            snapshot = self.snapshot()
            snapshot[field] = value
            with self.subTest(field=field), self.assertRaises(source.PublicDataError):
                self.validate(snapshot)

    def candles(self):
        return [dict(time=1800000, open="100", high="102", low="99", close="101", volume="0"),
                dict(time=900000, open="100", high="102", low="99", close="101", volume="5")]

    def test_normalization_and_zero_volume(self):
        rows = source.normalize_candles(self.candles(), "15m")
        self.assertEqual([r[0] for r in rows], [900000, 1800000])
        self.assertEqual(rows[-1][-1], 0)

    def test_bad_candles(self):
        for field, value in (("time", 1800001), ("close", "nan"), ("volume", "-1"), ("low", "103"), ("time", 900000)):
            data = self.candles()
            data[0][field] = value
            with self.assertRaises(source.PublicDataError):
                source.normalize_candles(data, "15m")
        with self.assertRaises(source.PublicDataError):
            source.normalize_candles([[1,2,3,4,5,6]], "15m")

    def test_quote_identity_and_time(self):
        self.assertEqual(source.normalize_quote(dict(symbol="BTC-USDT", price="100", time=900000), "BTC-USDT")["price"], 100)
        for data in (dict(symbol="OTHER", price="100", time=900000), dict(symbol="BTC-USDT", price="inf", time=900000), dict(symbol="BTC-USDT", price="100")):
            with self.assertRaises(source.PublicDataError):
                source.normalize_quote(data, "BTC-USDT")

    def test_no_private_path_or_credentials(self):
        with patch.object(source.http.client, "HTTPSConnection") as factory:
            for kind, symbol, args in (("orders", "BTC-USDT", {}), ("quote", "BTC-USDT&signature=x", {}),
                                       ("candles", "BTC-USDT", {"interval":"1s"}),
                                       ("quote", "BTC-USDT", {"authorized":False})):
                opts = dict(authorized=True)
                opts.update(args)
                with self.assertRaises(source.PublicDataError):
                    source.request_public(kind, symbol, **opts)
            factory.assert_not_called()

    def test_http_allowlist_and_no_retry(self):
        with patch.object(source.http.client, "HTTPSConnection") as factory:
            response = factory.return_value.getresponse.return_value
            response.status = 200
            response.read.return_value = b'{"code":0,"data":{"price":"100"}}'
            source.request_public("quote", "BTC-USDT", authorized=True)
            call = factory.return_value.request.call_args
            self.assertEqual(factory.call_args.args, ("open-api.bingx.com",))
            self.assertEqual(call.args, ("GET", "/openApi/swap/v2/quote/price?symbol=BTC-USDT"))
            self.assertEqual(call.kwargs["headers"], {"Accept":"application/json"})
            response.status = 429
            with self.assertRaises(source.PublicDataError):
                source.request_public("quote", "BTC-USDT", authorized=True)
            self.assertEqual(factory.return_value.request.call_count, 2)

    def test_snapshot_never_becomes_synthetic_or_qualified(self):
        quote = dict(symbol="BTC-USDT", price="100", time=1800000)
        with patch.object(source, "request_public", side_effect=[self.candles(), quote]), patch.object(source.time, "sleep"), patch.object(source.time, "time_ns", return_value=1800001000000):
            out = source.collect_snapshot("BTC-USDT", ["15m"], authorized=True)
        for k in ("synthetic", "source_qualified", "delivery_allowed", "live_allowed", "manual_trade_authorized"):
            self.assertIs(out[k], False)
        self.assertEqual(out["source"], "BINGX_PUBLIC_SWAP")

    def test_guard(self):
        with self.assertRaises(AssertionError):
            sys.audit("socket.connect", "offline probe")


if __name__ == "__main__":
    unittest.main()
