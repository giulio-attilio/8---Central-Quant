"""Finite-cycle tests; offline guards are installed before repository imports."""
import copy
import sys
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_signal_only_integration as fixtures
import signal_only_service as service


def config():
    return dict(version=1, poll_interval_ms=1000, bots={
        "FALCON": dict(symbols=["TEST-USDT"], setups=["FALCON15", "FALCON30"],
                       analysis=fixtures.harness.CONFIG.copy(), policy=fixtures.harness.POLICY.copy()),
        "DONKEY": dict(symbols=["TEST-USDT"], setups=list(fixtures.workflow.DONKEY_VARIANTS),
                       analysis=fixtures.CONFIG.copy(), policy=fixtures.harness.POLICY.copy())})


class ServiceTests(unittest.TestCase):
    def test_packaged_falcon_config_requires_high_quality(self):
        import json
        packaged = json.loads((Path(__file__).resolve().parents[1] / 'signals-config.validation.json').read_text())
        validated = service.validate_service_config(packaged)
        self.assertEqual(validated['bots']['FALCON']['analysis']['SCORE_MIN_QUALITY_TO_SIGNAL'], 80)

    def test_ideal_filter_is_benign_and_does_not_halt_worker(self):
        snapshot, _ = fixtures.PublicPreviewTests().public_fixture('DONKEY')
        sources = dict(FALCON=fixtures.harness.SOURCE, DONKEY=fixtures.SOURCE)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'delivery.sqlite'
            fixtures.delivery.initialize_ledger(path)
            with patch.object(service, 'collect_snapshot', return_value=snapshot), \
                 patch.object(service, 'run_once', return_value=dict(status='BLOCKED', reason='DONKEY_STOP_DISTANCE_ABOVE_IDEAL')):
                out = service.run_service(config(), sources, **self.supervisor_args(path))
        self.assertEqual(out['status'], 'STOPPED')
        self.assertEqual(out['evaluations'], 5)
        self.assertEqual(out['confirmed'], 0)

    def test_diagnostic_authorization_and_configuration_precede_collection(self):
        sources = dict(FALCON=fixtures.harness.SOURCE, DONKEY=fixtures.SOURCE)
        with patch.object(service, "collect_snapshot") as collect:
            self.assertEqual(service.diagnose_public_cycle(config(), sources)["status"], "BLOCKED")
            self.assertEqual(service.diagnose_public_cycle({}, sources, public_data_authorized=True)["stage"], "configuration")
            collect.assert_not_called()

    def test_diagnostic_finite_measurement_never_enables_delivery(self):
        snapshot, _ = fixtures.PublicPreviewTests().public_fixture("DONKEY")
        sources = dict(FALCON=fixtures.harness.SOURCE, DONKEY=fixtures.SOURCE)
        with patch.object(service, "collect_snapshot", return_value=snapshot) as collect, \
             patch.object(service, "validate_snapshot"), \
             patch.object(service, "run_once", return_value=dict(status="BLOCKED", reason="NO_SIGNAL")) as run, \
             patch.object(service.time, "monotonic", side_effect=[100, 110]), \
             patch.object(service.time, "sleep", side_effect=AssertionError("no cycle sleep")):
            out = service.diagnose_public_cycle(config(), sources, public_data_authorized=True)
        self.assertEqual(out["status"], "DIAGNOSTIC_COMPLETE")
        self.assertEqual(out["completed_symbols"], 1)
        self.assertEqual(out["evaluations"], 5)
        self.assertEqual(out["reason_counts"], {"NO_SIGNAL": 5})
        self.assertEqual(out["scan_seconds"], 10)
        self.assertEqual(out["cycle_with_pause_seconds"], 11)
        self.assertIs(out["capacity_approved"], False)
        collect.assert_called_once()
        for call in run.call_args_list:
            self.assertIs(call.kwargs["network_authorized"], False)
            self.assertIs(call.kwargs["public_delivery_authorized"], False)
            self.assertNotIn("values", call.kwargs)
            self.assertNotIn("ledger_path", call.kwargs)

    def test_diagnostic_failure_identifies_stage_without_raw_data_or_retry(self):
        snapshot, _ = fixtures.PublicPreviewTests().public_fixture("DONKEY")
        sources = dict(FALCON=fixtures.harness.SOURCE, DONKEY=fixtures.SOURCE)
        for stage in ("collection", "freshness_validation", "analysis"):
            with self.subTest(stage=stage), patch.object(service, "collect_snapshot", return_value=snapshot) as collect, \
                 patch.object(service, "validate_snapshot") as validate, \
                 patch.object(service, "run_once") as run:
                if stage == "collection":
                    collect.side_effect = service.PublicDataError("CANDLE_GAP_OR_DUPLICATE")
                elif stage == "freshness_validation":
                    validate.side_effect = service.PublicDataError("FRAME_NOT_CURRENT")
                else:
                    run.return_value = dict(status="FAILED", reason="PRIVATE_SENTINEL")
                out = service.diagnose_public_cycle(config(), sources, public_data_authorized=True)
            self.assertEqual(out["status"], "FAILED")
            self.assertEqual(out["stage"], stage)
            self.assertEqual(out["completed_symbols"], 0)
            self.assertNotIn("PRIVATE_SENTINEL", str(out))
            collect.assert_called_once()
            self.assertLessEqual(run.call_count, 1)

    def test_diagnostic_expired_frame_skips_only_affected_bot_without_retry(self):
        snapshot, _ = fixtures.PublicPreviewTests().public_fixture("DONKEY")
        sources = dict(FALCON=fixtures.harness.SOURCE, DONKEY=fixtures.SOURCE)
        with patch.object(service, 'collect_snapshot', return_value=snapshot) as collect, \
             patch.object(service, 'validate_snapshot', side_effect=[service.PublicDataError('FRAME_EXPIRED'), None, None, None]), \
             patch.object(service, 'run_once', return_value=dict(status='BLOCKED', reason='NO_SIGNAL')) as run:
            out = service.diagnose_public_cycle(config(), sources, public_data_authorized=True)
        self.assertEqual(out['status'], 'DIAGNOSTIC_COMPLETE')
        self.assertEqual(out['reason_counts'], {'FRAME_EXPIRED': 1, 'NO_SIGNAL': 3})
        self.assertEqual(out['evaluations'], 3)
        self.assertFalse(out['capacity_approved'])
        collect.assert_called_once()
        self.assertTrue(all(c.args[0] == 'DONKEY' for c in run.call_args_list))

    def test_supervisor_expired_frame_continues_and_recollects_only_next_cycle(self):
        snapshot, now = fixtures.PublicPreviewTests().public_fixture('DONKEY')
        sources = dict(FALCON=fixtures.harness.SOURCE, DONKEY=fixtures.SOURCE)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'delivery.sqlite'
            fixtures.delivery.initialize_ledger(path)
            args = self.supervisor_args(path)
            args['max_cycles'] = 2
            with patch.object(service, 'collect_snapshot', return_value=snapshot) as collect, \
                 patch.object(service.time, 'time_ns', return_value=now * 1000000), \
                 patch.object(service, 'run_once', side_effect=[dict(status='BLOCKED', reason='FRAME_EXPIRED')] +
                              [dict(status='BLOCKED', reason='NO_SIGNAL')] * 8) as run:
                out = service.run_service(config(), sources, **args)
            self.assertEqual(out['reason'], 'CYCLE_LIMIT_REACHED')
            self.assertEqual(out['discarded_snapshots'], 1)
            self.assertEqual(out['confirmed'], 0)
            self.assertEqual(collect.call_count, 2)
            self.assertEqual(args['stop_event'].waits, [1.0])
            self.assertEqual([c.kwargs['setup'] for c in run.call_args_list],
                             ['FALCON15', 'DONKEY', 'DONKEY_ORIGINAL', 'EARLY_DONKEY',
                              'FALCON15', 'FALCON30', 'DONKEY', 'DONKEY_ORIGINAL', 'EARLY_DONKEY'])

    def test_diagnostic_real_freshness_validation_blocks_stale_quote_before_analysis(self):
        snapshot, now = fixtures.PublicPreviewTests().public_fixture("FALCON")
        snapshot["quote"]["at_ms"] = now - config()["bots"]["FALCON"]["policy"]["quote_max_age_ms"] - 1
        sources = dict(FALCON=fixtures.harness.SOURCE, DONKEY=fixtures.SOURCE)
        with patch.object(service, "collect_snapshot", return_value=snapshot) as collect, \
             patch.object(service.time, "time_ns", return_value=now * 1000000), \
             patch.object(service, "run_once") as run:
            out = service.diagnose_public_cycle(config(), sources, public_data_authorized=True)
        self.assertEqual(out["stage"], "freshness_validation")
        self.assertEqual(out["reason"], "QUOTE_STALE_OR_FUTURE")
        self.assertEqual(out["evaluations"], 0)
        self.assertEqual(out["completed_symbols"], 0)
        collect.assert_called_once()
        run.assert_not_called()

    def test_public_failure_reports_only_fixed_code_and_never_evaluates_or_retries(self):
        sources = dict(FALCON=fixtures.harness.SOURCE, DONKEY=fixtures.SOURCE)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "delivery.sqlite"
            fixtures.delivery.initialize_ledger(path)
            for error, expected in (
                    (service.PublicDataError("CANDLE_GAP_OR_DUPLICATE"), "CANDLE_GAP_OR_DUPLICATE"),
                    (service.PublicDataError("PRIVATE_SENTINEL"), "PUBLIC_DATA_FAILURE_REDACTED"),
                    (RuntimeError("PRIVATE_SENTINEL"), "SERVICE_VALIDATION_OR_IO_FAILED")):
                with self.subTest(expected=expected), patch.object(service, "collect_snapshot", side_effect=error) as collect, patch.object(service, "run_once") as run:
                    result = service.run_service(config(), sources, **self.supervisor_args(path))
                self.assertEqual(result["status"], "FAILED")
                self.assertEqual(result["reason"], expected)
                self.assertEqual(result["evaluations"], 0)
                collect.assert_called_once()
                run.assert_not_called()
                self.assertNotIn("PRIVATE_SENTINEL", str(result))

    def test_no_signal_evaluations_do_not_add_delivery_pacing_waits(self):
        snapshot, now = fixtures.PublicPreviewTests().public_fixture("DONKEY")
        sources = dict(FALCON=fixtures.harness.SOURCE, DONKEY=fixtures.SOURCE)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "delivery.sqlite"
            fixtures.delivery.initialize_ledger(path)
            args = self.supervisor_args(path)
            with patch.object(service, "collect_snapshot", return_value=snapshot), \
                 patch.object(service, "run_once", return_value=dict(status="BLOCKED", reason="NO_SIGNAL")):
                out = service.run_service(config(), sources, **args)
            self.assertEqual(out["reason"], "CYCLE_LIMIT_REACHED")
            self.assertEqual(out["evaluations"], 5)
            self.assertEqual(args["stop_event"].waits, [])

    def supervisor_args(self, path):
        class Stop:
            stopped = False
            def __init__(self):
                self.waits = []
            def is_set(self):
                return self.stopped
            def wait(self, seconds):
                self.waits.append(seconds)
                return self.stopped
        return dict(values=fixtures.VALUES, ledger_path=str(path), stop_event=Stop(),
                    service_authorized=True, public_data_authorized=True,
                    public_delivery_authorized=True, max_cycles=1)

    def test_supervisor_one_cycle_batches_ready_candidates_by_bot(self):
        snapshot, now = fixtures.PublicPreviewTests().public_fixture("DONKEY")
        sources = dict(FALCON=fixtures.harness.SOURCE, DONKEY=fixtures.SOURCE)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "delivery.sqlite"
            fixtures.delivery.initialize_ledger(path)
            args = self.supervisor_args(path)
            with patch.object(service, "collect_snapshot", return_value=snapshot) as collect, \
                 patch.object(service, "run_once", return_value=dict(
                     status="PUBLIC_CANDIDATE_READY", candidate={})) as run, \
                 patch.object(service, "dispatch_ready_candidates", side_effect=[
                     dict(deliveries=[dict(status="CONFIRMED")]),
                     dict(deliveries=[dict(status="CONFIRMED")] * 3),
                 ]) as dispatch, \
                 patch.object(service.time, "time_ns", return_value=now * 1000000):
                out = service.run_service(config(), sources, **args)
            self.assertEqual(out["reason"], "CYCLE_LIMIT_REACHED", out)
            self.assertEqual((out["cycles"], out["evaluations"], out["confirmed"]), (1, 5, 4))
            self.assertEqual(args["stop_event"].waits, [1, 1, 1, 1])
            collect.assert_called_once_with("TEST-USDT", ["15m", "4h", "1d"], authorized=True, limit=200)
            self.assertEqual([c.kwargs["setup"] for c in run.call_args_list],
                             ["FALCON15", "FALCON30", "DONKEY", "DONKEY_ORIGINAL", "EARLY_DONKEY"])
            self.assertEqual([len(call.args[1]) for call in dispatch.call_args_list], [2, 3])

    def test_supervisor_gates_credentials_and_missing_ledger_before_market(self):
        sources = dict(FALCON=fixtures.harness.SOURCE, DONKEY=fixtures.SOURCE)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "missing.sqlite"
            args = self.supervisor_args(path)
            with patch.object(service, "collect_snapshot") as collect:
                for changes in (dict(service_authorized=False), dict(public_data_authorized=False),
                                dict(public_delivery_authorized=False), dict(values={}), {}):
                    result = service.run_service(config(), sources, **dict(args, **changes))
                    self.assertIn(result["status"], ("BLOCKED", "FAILED"))
                collect.assert_not_called()
            self.assertFalse(path.exists())

    def test_supervisor_unknown_delivery_halts_no_retry(self):
        snapshot, now = fixtures.PublicPreviewTests().public_fixture("DONKEY")
        sources = dict(FALCON=fixtures.harness.SOURCE, DONKEY=fixtures.SOURCE)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "delivery.sqlite"
            fixtures.delivery.initialize_ledger(path)
            with patch.object(service, "collect_snapshot", return_value=snapshot) as collect, \
                 patch.object(service, "run_once", return_value=dict(status="UNKNOWN", reason="NO_AUTOMATIC_RETRY")) as run:
                result = service.run_service(config(), sources, **self.supervisor_args(path))
            self.assertEqual(result["status"], "FAILED")
            self.assertEqual(run.call_count, 1)
            self.assertEqual(collect.call_count, 1)

    def test_supervisor_stop_after_collection_before_delivery(self):
        snapshot, now = fixtures.PublicPreviewTests().public_fixture("DONKEY")
        sources = dict(FALCON=fixtures.harness.SOURCE, DONKEY=fixtures.SOURCE)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "delivery.sqlite"
            fixtures.delivery.initialize_ledger(path)
            args = self.supervisor_args(path)
            def collect(*a, **kw):
                args["stop_event"].stopped = True
                return snapshot
            with patch.object(service, "collect_snapshot", side_effect=collect), patch.object(service, "run_once") as run:
                result = service.run_service(config(), sources, **args)
            self.assertEqual(result["reason"], "STOP_REQUESTED")
            run.assert_not_called()

    def test_supervisor_single_instance_lock_and_release(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "delivery.sqlite"
            with service.exclusive_service(path):
                with self.assertRaises(OSError):
                    with service.exclusive_service(path):
                        self.fail("second instance acquired lock")
            with service.exclusive_service(path):
                pass

    def test_shared_repository_watchlist(self):
        text = (fixtures.ROOT / "watchlist.json").read_text(encoding="utf-8-sig")
        import json
        entries = json.loads(text)
        original = config()
        out = service.apply_shared_watchlist(original, text)
        expected = [entry.split("/")[0] + "-USDT" for entry in entries]
        self.assertEqual(out["bots"]["FALCON"]["symbols"], expected)
        self.assertEqual(out["bots"]["DONKEY"]["symbols"], expected)
        self.assertEqual(original, config())
        out["bots"]["FALCON"]["symbols"].clear()
        self.assertEqual(out["bots"]["DONKEY"]["symbols"], expected)

    def test_watchlist_preserves_multipliers_and_order(self):
        out = service.apply_shared_watchlist(config(), '["1000PEPE/USDT:USDT", "1000BONK/USDT:USDT", "BTC/USDT:USDT"]')
        self.assertEqual(out["bots"]["DONKEY"]["symbols"], ["1000PEPE-USDT", "1000BONK-USDT", "BTC-USDT"])

    def test_watchlist_rejects_whole_invalid_list_without_fallback(self):
        for text in ('bad', '{}', '[]', '[1]', '["BTC/USDT"]', '["BTC/USDT:USDC"]',
                     '["BTC/USDT:USDT", "BTC/USDT:USDT"]', '["BTC/USDT:USDT", "eth/USDT:USDT"]'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                service.apply_shared_watchlist(config(), text)

    def test_config_defensive_copy(self):
        original = config()
        out = service.validate_service_config(original)
        self.assertEqual(original, out)
        out["bots"]["FALCON"]["symbols"].append("OTHER-USDT")
        out["bots"]["DONKEY"]["policy"]["basis"] = "changed"
        self.assertEqual(original, config())

    def test_missing_extra_and_unsafe_configuration(self):
        variants = [None, {}, dict(config(), token="not permitted"), dict(config(), poll_interval_ms=True),
                    dict(config(), poll_interval_ms=0), dict(config(), poll_interval_ms=60001)]
        for field, value in (("symbols", []), ("symbols", ["BTC-USDT", "BTC-USDT"]),
                             ("symbols", ["BTC-USDT&signature=x"]), ("setups", ["DONKEY"]),
                             ("analysis", {}), ("policy", {})):
            changed = config()
            changed["bots"]["DONKEY"][field] = value
            variants.append(changed)
        for candidate in variants:
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                service.validate_service_config(candidate)

    def test_all_identities_evaluated_no_delivery(self):
        snap, now = fixtures.PublicPreviewTests().public_fixture("DONKEY")
        falcon, _ = fixtures.harness.fixture()
        # Fabricated union schema; mock analysis here to test routing independently.
        snap["frames"].update(falcon["frames"])
        snap["frame_received_at_ms"] = {tf: now for tf in snap["frames"]}
        original = copy.deepcopy(snap)
        sources = dict(FALCON=fixtures.harness.SOURCE, DONKEY=fixtures.SOURCE)
        with patch.object(service, "run_once", return_value={"status": "LOCAL_PUBLIC_PREVIEW"}) as run:
            out = service.evaluate_cycle(config(), sources, {"TEST-USDT": snap}, now_ms=now)
        self.assertEqual(run.call_count, 5)
        self.assertEqual([r["setup"] for r in out["results"]],
                         ["FALCON15", "FALCON30", "DONKEY", "DONKEY_ORIGINAL", "EARLY_DONKEY"])
        for call in run.call_args_list:
            self.assertNotIn("network_authorized", call.kwargs)
            self.assertEqual(set(call.args[2]["frames"]), {"15m"} if call.args[0] == "FALCON" else {"4h", "1d"})
        self.assertEqual(snap, original)
        self.assertIs(out["delivery_allowed"], False)

    def test_invalid_source_or_universe_never_evaluated(self):
        snap, now = fixtures.PublicPreviewTests().public_fixture("DONKEY")
        sources = dict(FALCON=fixtures.harness.SOURCE, DONKEY=fixtures.SOURCE)
        for texts, snapshots in ((dict(sources, DONKEY="pass"), {"TEST-USDT": snap}),
                                  (sources, {}), (sources, {"WRONG-USDT": snap})):
            with patch.object(service, "run_once") as run, self.assertRaises(ValueError):
                service.evaluate_cycle(config(), texts, snapshots, now_ms=now)
            run.assert_not_called()

    def test_real_analysis_cycle_without_network_or_operational_imports(self):
        snap, now = fixtures.PublicPreviewTests().public_fixture("FALCON")
        # Donkey lacks D1/history in this fixture: it must remain explicitly blocked.
        sources = dict(FALCON=fixtures.harness.SOURCE, DONKEY=fixtures.SOURCE)
        with patch.object(fixtures.delivery, "_post") as post:
            out = service.evaluate_cycle(config(), sources, {"TEST-USDT": snap}, now_ms=now)
        self.assertEqual(len(out["results"]), 5)
        self.assertEqual(out["results"][0]["result"]["status"], "LOCAL_PUBLIC_PREVIEW")
        self.assertTrue(all(r["result"]["status"] == "BLOCKED" for r in out["results"][2:]))
        post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
