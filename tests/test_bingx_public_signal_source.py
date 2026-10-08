"""Offline fixtures only; no live smoke call belongs in this test suite."""
import importlib.util
import ast
import copy
import json
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
    def test_safe_error_codes_never_expose_unknown_payloads(self):
        for code in source.PUBLIC_ERROR_CODES:
            self.assertEqual(source.safe_error_code(source.PublicDataError(code)), code)
        class Hostile(Exception):
            def __str__(self):
                raise AssertionError("must not stringify")
        for error in (Hostile(), ValueError("FRAME_NOT_CURRENT"),
                      source.PublicDataError("PRIVATE_SENTINEL"),
                      source.PublicDataError("FRAME_NOT_CURRENT", "PRIVATE_SENTINEL"),
                      source.PublicDataError(["FRAME_NOT_CURRENT"])):
            self.assertEqual(source.safe_error_code(error), "PUBLIC_DATA_FAILURE_REDACTED")

    def test_diagnostic_allowlist_covers_all_reader_error_sites(self):
        tree = ast.parse(Path(source.__file__).read_text(encoding="utf-8"))
        codes = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                index = 1 if node.func.id == "require" else 0 if node.func.id == "PublicDataError" else None
                if index is not None and len(node.args) > index:
                    value = node.args[index]
                    if isinstance(value, ast.Constant) and type(value.value) is str:
                        codes.add(value.value)
        self.assertEqual(codes, source.PUBLIC_ERROR_CODES)

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
        with self.assertRaisesRegex(source.PublicDataError, "FRAME_EXPIRED"):
            self.validate(self.snapshot(), now_ms=2700000, frame_max_age_ms=1000000,
                          quote_max_age_ms=1000000)
        snapshot = self.snapshot()
        snapshot["frames"]["15m"].reverse()
        with self.assertRaisesRegex(source.PublicDataError, "CANDLE_ORDER"):
            self.validate(snapshot)

    def test_future_frame_is_not_classified_as_expired(self):
        snapshot = self.snapshot()
        snapshot['frame_received_at_ms']['15m'] = snapshot['frames']['15m'][-1][0] - 1
        with self.assertRaisesRegex(source.PublicDataError, 'FRAME_NOT_CURRENT'):
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
        with patch.object(source.http.client, "HTTPSConnection") as factory, patch.object(source.time, "sleep"), patch.object(source.time, "time_ns", return_value=1800001000000):
            response = factory.return_value.getresponse.return_value
            response.status = 200
            response.read.side_effect = [json.dumps(dict(code=0, data=data)).encode()
                                         for data in (self.candles(), quote)]
            out = source.collect_snapshot("BTC-USDT", ["15m"], authorized=True)
        for k in ("synthetic", "source_qualified", "delivery_allowed", "live_allowed", "manual_trade_authorized"):
            self.assertIs(out[k], False)
        self.assertEqual(out["source"], "BINGX_PUBLIC_SWAP")

    def test_collection_reuses_connection_and_preserves_spacing(self):
        frames = []
        for interval in ("15m", "4h", "1d"):
            rows = self.candles()
            for row, multiple in zip(rows, (2, 1)):
                row["time"] = source.PERIODS[interval] * multiple
            frames.append(rows)
        quote = dict(symbol="BTC-USDT", price="100", time=1800000)
        events = []
        with patch.object(source.http.client, "HTTPSConnection") as factory, patch.object(source.time, "sleep", side_effect=lambda seconds: events.append(("sleep", seconds))):
            connection = factory.return_value
            connection.request.side_effect = lambda *a, **kw: events.append(("request", a[0]))
            response = connection.getresponse.return_value
            response.status = 200
            response.read.side_effect = [json.dumps(dict(code=0, data=data)).encode()
                                         for data in (*frames, quote)]
            source.collect_snapshot("BTC-USDT", ["15m", "4h", "1d"], authorized=True)
            factory.assert_called_once_with("open-api.bingx.com", timeout=15)
            connection.close.assert_called_once_with()
            self.assertEqual(events, [("request", "GET"), ("sleep", 1)] * 3 + [("request", "GET")])
            self.assertTrue(all(call.args == (1048577,) for call in response.read.call_args_list))

    def test_collection_stops_and_closes_on_first_failure(self):
        for failure in ("http", "json", "schema", "timeout", "oversize"):
            with self.subTest(failure=failure), patch.object(source.http.client, "HTTPSConnection") as factory, patch.object(source.time, "sleep") as sleep:
                connection = factory.return_value
                response = connection.getresponse.return_value
                response.status = 429 if failure == "http" else 200
                response.read.return_value = (b"invalid" if failure == "json" else
                                              b"x" * 1048577 if failure == "oversize" else
                                              b'{"code":0,"data":[]}')
                if failure == "timeout":
                    connection.request.side_effect = TimeoutError("do not disclose")
                with self.assertRaises(source.PublicDataError):
                    source.collect_snapshot("BTC-USDT", ["15m", "4h"], authorized=True)
                self.assertEqual(connection.request.call_count, 1)
                connection.close.assert_called_once_with()
                sleep.assert_not_called()

    def test_collection_validates_before_connection(self):
        with patch.object(source.http.client, "HTTPSConnection") as factory:
            for symbol, intervals, opts in (("BTC-USDT", ["15m"], {}),
                    ("BTC-USDT&signature=x", ["15m"], dict(authorized=True)),
                    ("BTC-USDT", ["15m", "bad"], dict(authorized=True)),
                    ("BTC-USDT", ["15m"], dict(authorized=True, limit=201))):
                with self.assertRaises(source.PublicDataError):
                    source.collect_snapshot(symbol, intervals, **opts)
            factory.assert_not_called()

    def test_reused_connection_failure_does_not_retry_or_continue(self):
        with patch.object(source.http.client, "HTTPSConnection") as factory, patch.object(source.time, "sleep") as sleep:
            connection = factory.return_value
            response = connection.getresponse.return_value
            response.status = 200
            response.read.side_effect = [json.dumps(dict(code=0, data=self.candles())).encode(),
                                         ConnectionError("connection lost")]
            with self.assertRaisesRegex(source.PublicDataError, "PUBLIC_TRANSPORT_OR_JSON_FAILED_NO_RETRY"):
                source.collect_snapshot("BTC-USDT", ["15m", "4h", "1d"], authorized=True)
            factory.assert_called_once_with("open-api.bingx.com", timeout=15)
            self.assertEqual(connection.request.call_count, 2)
            sleep.assert_called_once_with(1)
            connection.close.assert_called_once_with()

    def test_guard(self):
        with self.assertRaises(AssertionError):
            sys.audit("socket.connect", "offline probe")


class PublicRejectionObservability(unittest.TestCase):
    def read(self, payload, *, status=200, kind="candles", symbol="BTC-USDT", interval="15m"):
        import contextlib
        import io
        from unittest.mock import Mock
        connection = Mock()
        connection.getresponse.return_value.status = status
        connection.getresponse.return_value.read.return_value = payload if type(payload) is bytes else json.dumps(payload).encode()
        output = io.StringIO()
        result, reason = None, None
        with contextlib.redirect_stdout(output):
            try:
                result = source._read_public(connection, '/unlogged-private-fixture-path',
                    kind=kind, symbol=symbol, interval=interval)
            except source.PublicDataError as error:
                reason = source.safe_error_code(error)
        return result, reason, output.getvalue(), connection

    def test_rejection_subtypes_and_sanitized_projection(self):
        cases = (({'code': 19}, 'NONZERO_API_CODE'), ({}, 'MISSING_CODE'),
                 ({'code': '19'}, 'NONINTEGER_CODE'), ({'code': True}, 'NONINTEGER_CODE'),
                 ({'code': 0.5}, 'NONINTEGER_CODE'), ([], 'INVALID_JSON_SHAPE'),
                 (None, 'INVALID_JSON_SHAPE'))
        for payload, subtype in cases:
            with self.subTest(payload=payload):
                if type(payload) is dict:
                    payload = dict(payload, msg='PRIVATE_MESSAGE_FIXTURE', token='PRIVATE_TOKEN_FIXTURE',
                                   data={'raw': 'PRIVATE_BODY_FIXTURE'})
                _, reason, output, connection = self.read(payload)
                self.assertEqual(reason, 'PUBLIC_API_REJECTED_NO_RETRY')
                d = json.loads(output)
                self.assertEqual(d['response_shape_reason'], subtype)
                self.assertEqual(d['public_endpoint_kind'], 'klines')
                self.assertEqual(d['symbol'], 'BTC-USDT')
                self.assertEqual(d['interval'], '15m')
                self.assertEqual(d['http_status'], 200)
                self.assertFalse(d['live_allowed'])
                if type(payload) is dict:
                    self.assertRegex(d['public_api_message_tag'], r'^[a-f0-9]{12}$')
                for sentinel in ('PRIVATE_MESSAGE_FIXTURE', 'PRIVATE_TOKEN_FIXTURE', 'PRIVATE_BODY_FIXTURE',
                                 '/unlogged-private-fixture-path'):
                    self.assertNotIn(sentinel, output)
                self.assertLess(len(output), 600)
                connection.request.assert_called_once()

    def test_success_missing_data_and_other_failures_do_not_emit_rejection(self):
        for payload, status, expected, reason in (
            ({'code': 0, 'data': {'value': 1}}, 200, {'value': 1}, None),
            ({'code': 0}, 200, None, None),
            (b'{invalid', 200, None, 'PUBLIC_TRANSPORT_OR_JSON_FAILED_NO_RETRY'),
            ({'code': 19}, 429, None, 'PUBLIC_HTTP_FAILED_NO_RETRY'),
            ({'code': 19}, 500, None, 'PUBLIC_HTTP_FAILED_NO_RETRY'),
            ({'code': 19}, 503, None, 'PUBLIC_HTTP_FAILED_NO_RETRY'),
        ):
            with self.subTest(payload=payload, status=status):
                result, actual, output, _ = self.read(payload, status=status)
                self.assertEqual(result, expected)
                self.assertEqual(actual, reason)
                self.assertEqual(output, '')

    def test_context_and_numbers_are_allowlisted_and_bounded(self):
        _, _, output, _ = self.read({'code': 2**100, 'msg': ['PRIVATE_FIXTURE']},
            kind='PRIVATE_FIXTURE', symbol='PRIVATE_FIXTURE\nTOKEN', interval='PRIVATE_FIXTURE')
        d = json.loads(output)
        self.assertFalse({'public_endpoint_kind', 'symbol', 'interval', 'public_api_code',
                          'public_api_message_tag'} & set(d))
        self.assertNotIn('PRIVATE_FIXTURE', output)

    def test_logging_failure_preserves_original_reason(self):
        with patch('builtins.print', side_effect=OSError('synthetic log failure')):
            _, reason, _, _ = self.read({'code': 19})
        self.assertEqual(reason, 'PUBLIC_API_REJECTED_NO_RETRY')

    def test_diagnostic_construction_failure_preserves_original_reason(self):
        with patch.object(source, '_public_rejection_diagnostic', side_effect=RuntimeError('synthetic failure')):
            _, reason, output, _ = self.read({'code': 19})
        self.assertEqual(reason, 'PUBLIC_API_REJECTED_NO_RETRY')
        self.assertEqual(output, '')

    def test_request_public_passes_both_endpoint_contexts_without_retry(self):
        import contextlib
        import io
        for kind, interval, endpoint in (('candles', '4h', 'klines'), ('quote', None, 'price')):
            with self.subTest(kind=kind), patch.object(source.http.client, 'HTTPSConnection') as factory:
                connection = factory.return_value
                connection.getresponse.return_value.status = 200
                connection.getresponse.return_value.read.return_value = b'{"code":19,"msg":"fixture"}'
                output = io.StringIO()
                with contextlib.redirect_stdout(output), self.assertRaisesRegex(source.PublicDataError, '^PUBLIC_API_REJECTED_NO_RETRY$'):
                    source.request_public(kind, 'BTC-USDT', interval=interval, authorized=True)
                d = json.loads(output.getvalue())
                self.assertEqual(d['public_endpoint_kind'], endpoint)
                self.assertEqual(d['public_api_code'], 19)
                self.assertEqual(d.get('interval'), interval)
                connection.request.assert_called_once()
                connection.close.assert_called_once()

    def test_collector_passes_price_context_after_successful_klines(self):
        import contextlib
        import io
        from unittest.mock import Mock
        with patch.object(source.http.client, 'HTTPSConnection') as factory, patch.object(source.time, 'sleep'):
            candle_response, quote_response = Mock(), Mock()
            candle_response.status = quote_response.status = 200
            candle_response.read.return_value = json.dumps({'code': 0, 'data': PublicTests().candles()}).encode()
            quote_response.read.return_value = b'{"code":19}'
            connection = factory.return_value
            connection.getresponse.side_effect = [candle_response, quote_response]
            output = io.StringIO()
            with contextlib.redirect_stdout(output), self.assertRaisesRegex(source.PublicDataError, '^PUBLIC_API_REJECTED_NO_RETRY$'):
                source.collect_snapshot('BTC-USDT', ['15m'], authorized=True)
            d = json.loads(output.getvalue())
            self.assertEqual(d['public_endpoint_kind'], 'price')
            self.assertNotIn('interval', d)
            self.assertEqual(connection.request.call_count, 2)
            connection.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
