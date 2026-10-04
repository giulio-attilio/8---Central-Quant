"""Closed M15 edges only. Offline guards precede all repository imports."""
import ast
import copy
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_signal_only_integration as fixtures
import test_manual_signal_tracking as manual
import test_signal_only_service as service_fixtures

h = fixtures.harness
offline, workflow, delivery = h.offline, fixtures.workflow, fixtures.delivery
M15 = offline.PERIODS['15m']
SETUPS = ('FALCON15', 'FALCON30')


def price(row, value, volume=80):
    row[1:] = [value, value + .2, value - .2, value, volume]


def advance(snap, now, value):
    snap = copy.deepcopy(snap)
    price(snap['frames']['15m'][-1], value)
    now += M15
    for tf, rows in snap['frames'].items():
        duration = offline.PERIODS[tf]
        while rows[-1][0] < now // duration * duration:
            rows.append([rows[-1][0] + duration] + rows[-1][1:])
    snap['observed_at_ms'] = snap['quote']['at_ms'] = now
    snap['quote']['price'] = value
    if not snap['synthetic']:
        snap['frame_received_at_ms'] = {tf: now for tf in snap['frames']}
    return snap, now


def snapshot(side='LONG', *, previous=False, current=True, public=False):
    snap, now = h.fixture('FALCON30', side)
    value = 101 if side == 'LONG' else 99
    # Both preceding/current candles are after formation of both ORBs.
    snap, now = advance(snap, now, value)
    if not previous:
        price(snap['frames']['15m'][-3], 100, 10)
    if not current:
        price(snap['frames']['15m'][-2], 100, 10)
    snap['quote']['price'] = snap['frames']['15m'][-2][4]
    if public:
        snap.update(synthetic=False, source='BINGX_PUBLIC_SWAP', symbol='BTC-USDT',
            frame_received_at_ms={tf: now for tf in snap['frames']},
            source_qualified=False, delivery_allowed=False, live_allowed=False,
            manual_trade_authorized=False)
    return snap, now


def historical(snap, now):
    snap = copy.deepcopy(snap)
    previous_close = snap['frames']['15m'][-3][0] + M15
    for tf, rows in snap['frames'].items():
        forming = previous_close // offline.PERIODS[tf] * offline.PERIODS[tf]
        snap['frames'][tf] = [r for r in rows if r[0] <= forming]
    return snap, previous_close + 1000


class M15Edges(h.unittest.TestCase):
    def analyze(self, snap, now, setup, config=None):
        return h.session(config).evaluate(snap, setup=setup, now_ms=now,
                                         public_data_authorized=not snap['synthetic'])

    def test_truth_tables_both_variants_and_directions_real_indicators(self):
        for setup in SETUPS:
            for side in ('LONG', 'SHORT'):
                for previous, current in ((False, True), (True, True), (False, False), (True, False)):
                    with self.subTest(setup=setup, side=side, previous=previous, current=current):
                        snap, now = snapshot(side, previous=previous, current=current)
                        before, before_now = historical(snap, now)
                        prior, _ = h.original_oracle(before, setup, before_now, h.CONFIG)
                        current_sig, counts = h.original_oracle(snap, setup, now, h.CONFIG)
                        self.assertEqual(prior is not None and prior['side'] == side, previous)
                        self.assertEqual(current_sig is not None and current_sig['side'] == side, current)
                        out = self.analyze(snap, now, setup)
                        self.assertEqual(out['status'], 'OFFLINE_PREVIEW' if not previous and current else 'NO_SIGNAL', out)
                        self.assertEqual(out['counters'], counts)
                        self.assertIs(out['live_allowed'], False)
                        if out['status'] == 'OFFLINE_PREVIEW':
                            for key in ('entry', 'stop', 'tp50', 'signal_id', 'side', 'timeframe'):
                                self.assertEqual(out['signal'][key], current_sig[key])

    def test_requalification_after_loss_both_variants_and_directions(self):
        for setup in SETUPS:
            for side in ('LONG', 'SHORT'):
                snap, now = snapshot(side)
                self.assertEqual(self.analyze(snap, now, setup)['status'], 'OFFLINE_PREVIEW')
                lost, lost_now = advance(snap, now, 100)
                self.assertEqual(self.analyze(lost, lost_now, setup)['status'], 'NO_SIGNAL')
                regained, regained_now = advance(lost, lost_now, 101 if side == 'LONG' else 99)
                out = self.analyze(regained, regained_now, setup)
                self.assertEqual(out['status'], 'OFFLINE_PREVIEW', out)

    def test_direction_change_uses_its_own_previous_boolean(self):
        for setup in SETUPS:
            snap, now = snapshot(previous=True)
            price(snap['frames']['15m'][-2], 99)
            snap['quote']['price'] = 99
            out = self.analyze(snap, now, setup)
            self.assertEqual(out['status'], 'OFFLINE_PREVIEW', out)
            self.assertEqual(out['signal']['side'], 'SHORT')

    def test_restart_persistent_and_no_historical_catchup(self):
        for setup in SETUPS:
            snap, now = snapshot(previous=True)
            for _ in range(2):
                self.assertEqual(h.session().evaluate(snap, setup=setup, now_ms=now)['status'], 'NO_SIGNAL')
            later, later_now = advance(snap, now, 101)
            self.assertEqual(self.analyze(later, later_now, setup)['status'], 'NO_SIGNAL')

    def test_previous_missing_warmup_or_undefined_is_fail_closed(self):
        for setup in SETUPS:
            snap, now = snapshot()
            snap['frames']['15m'] = snap['frames']['15m'][-81:]
            self.assertEqual(self.analyze(snap, now, setup)['reason'], 'PREVIOUS_CORE_UNAVAILABLE')
            snap, now = snapshot()
            for row in snap['frames']['15m'][:-2]:
                row[1:] = [100, 100, 100, 100, 10]
            out = self.analyze(snap, now, setup)
            self.assertNotEqual(out['status'], 'OFFLINE_PREVIEW', out)

    def test_forming_candle_never_participates(self):
        for setup in SETUPS:
            snap, now = snapshot(previous=True)
            for tf, rows in snap['frames'].items():
                price(rows[-1], 500)
            self.assertEqual(self.analyze(snap, now, setup)['status'], 'NO_SIGNAL')

    def test_first_window_candle_uses_previous_own_orb_and_new_ny_session(self):
        for day in ('2026-01-05', '2026-07-06'):
            for setup in SETUPS:
                snap, now = h.fixture(setup, day=day)
                if day.endswith('07-06'):
                    for row in snap['frames']['15m']:
                        row[0] -= 3600000
                    now -= 3600000
                    snap['observed_at_ms'] = snap['quote']['at_ms'] = now
                before, before_now = historical(snap, now)
                prior, _ = h.original_oracle(before, setup, before_now, h.CONFIG)
                self.assertIsNone(prior)  # Previous candle is before this variant's window.
                out = self.analyze(snap, now, setup)
                self.assertEqual(out['status'], 'OFFLINE_PREVIEW', out)
                # No qualification persistence crosses a session; only dedup is restored.
                state = h.session().state()
                state['seen'] = ['FALCON:prior-session']
                self.assertEqual(h.session(state=state).evaluate(snap, setup=setup, now_ms=now)['status'], 'OFFLINE_PREVIEW')

    def test_ny_window_boundaries_preserve_original_qualification(self):
        for setup in SETUPS:
            for clock in ('14:30', '14:45', '17:15', '17:30'):
                snap, now = snapshot()
                target = int(h.datetime.fromisoformat('2026-01-05T' + clock + ':00+00:00').timestamp()*1000)+1000
                offset = target - now
                for row in snap['frames']['15m']:
                    row[0] += offset
                now = target
                snap['observed_at_ms'] = snap['quote']['at_ms'] = now
                original, _ = h.original_oracle(snap, setup, now, h.CONFIG)
                out = self.analyze(snap, now, setup)
                if original is None:
                    self.assertNotEqual(out['status'], 'OFFLINE_PREVIEW', out)

    def test_previous_orb_never_sees_current_candle(self):
        for setup in SETUPS:
            snap, now = snapshot()
            # Observe calls without changing the strategy, including ORB input prefixes.
            extra = ast.parse('''
original_get_orb = get_orb_range
def get_orb_range(closed, minutes):
    observed.append((minutes, int(closed.iloc[-1]["ts"]), len(closed)))
    return original_get_orb(closed, minutes)
''')
            ns_probe = []
            original_exec = __builtins__['exec'] if isinstance(__builtins__, dict) else __builtins__.exec
            def probe(compiled, ns):
                original_exec(compiled, ns)
                ns['observed'] = ns_probe
                original_exec(compile(extra, '<test-orb-observer>', 'exec'), ns)
            with patch.object(offline, 'exec', side_effect=probe, create=True):
                out = self.analyze(snap, now, setup)
            self.assertEqual(out['status'], 'OFFLINE_PREVIEW', out)
            current_ts, previous_ts = snap['frames']['15m'][-2][0], snap['frames']['15m'][-3][0]
            self.assertEqual([last for _, last, _ in ns_probe], [current_ts, current_ts, previous_ts, previous_ts])
            self.assertTrue(all(minutes == (15 if setup == 'FALCON15' else 30) for minutes, _, _ in ns_probe))

    def test_alignment_is_asof_previous_close_no_future_h1_or_h4(self):
        # Current closes at 12:00 UTC; previous closed at 11:45 UTC. Current
        # alignment can use 11:00 H1 / 08:00 H4; previous must not use them.
        for mode, tf in (('h1', '1h'), ('h1_h4', '4h')):
            for setup in SETUPS:
                cfg = dict(h.CONFIG, ALIGNMENT_MODE=mode, ORB_START_HOUR=6, ORB_START_MINUTE=0)
                snap, now = snapshot(previous=True)
                target = int(h.datetime.fromisoformat('2026-01-05T12:00:00+00:00').timestamp()*1000)+1000
                offset = target - now
                for row in snap['frames']['15m']:
                    row[0] += offset
                now = target
                snap['observed_at_ms'] = snap['quote']['at_ms'] = now
                for higher in ('1h', '4h'):
                    duration = offline.PERIODS[higher]
                    rows = snap['frames'][higher]
                    forming = now // duration * duration
                    for i, row in enumerate(rows):
                        row[0] = forming - (len(rows)-1-i)*duration
                        price(row, 110-i*.05, 10)
                    price(rows[-2], 120, 10)
                if mode == 'h1_h4':
                    for i, row in enumerate(snap['frames']['1h']):
                        price(row, 100+i*.01, 10)
                before, before_now = historical(snap, now)
                prior, _ = h.original_oracle(before, setup, before_now, cfg)
                current, counts = h.original_oracle(snap, setup, now, cfg)
                self.assertIsNone(prior)
                self.assertIsNotNone(current, (mode, setup, counts))
                out = self.analyze(snap, now, setup, cfg)
                self.assertEqual(out['status'], 'OFFLINE_PREVIEW', out)

    def test_source_hash_and_original_arithmetic_unchanged(self):
        packaged = (h.ROOT / 'signals_sources/falcon.txt').read_text(encoding='utf-8')
        offline.reviewed_analysis(packaged)
        offline.reviewed_analysis(h.SOURCE)
        self.assertEqual(offline.SOURCE_DIGEST, '8ff4aaa7340a9577f19defe851dbcec6b4b932d5ae57d34ef32e742095f195bb')


class DeliveryEdges(manual.Harness):
    def setUp(self):
        super().setUp()
        # Explicit fixture clock: host scheduling must not age quotes or make
        # separately qualified candidates regress the transport ledger clock.
        clock = patch.object(workflow.time, 'monotonic', return_value=0)
        clock.start()
        self.addCleanup(clock.stop)

    def test_missing_previous_is_benign_in_diagnostic_and_supervisor(self):
        service = manual.service
        snap, _ = fixtures.PublicPreviewTests().public_fixture('DONKEY')
        sources = dict(FALCON=h.SOURCE, DONKEY=fixtures.SOURCE)
        with patch.object(service, 'collect_snapshot', return_value=snap), \
             patch.object(service, 'validate_snapshot'), \
             patch.object(service, 'run_once', return_value=dict(status='BLOCKED', reason='PREVIOUS_CORE_UNAVAILABLE')), \
             patch.object(service, 'dispatch_ready_candidates') as send:
            out = service.diagnose_public_cycle(service_fixtures.config(), sources,
                                                public_data_authorized=True)
            self.assertEqual(out['status'], 'DIAGNOSTIC_COMPLETE', out)
            args = service_fixtures.ServiceTests().supervisor_args(self.path)
            out = service.run_service(service_fixtures.config(), sources, **args)
            self.assertEqual(out['status'], 'STOPPED', out)
            self.assertEqual(out['evaluations'], 5)
            send.assert_not_called()

    def ready(self, snap, now):
        results = [workflow.run_once('FALCON', h.SOURCE, snap, h.CONFIG, h.POLICY,
            setup=setup, now_ms=now, network_authorized=True, public_data_authorized=True,
            public_delivery_authorized=True, defer_public_delivery=True) for setup in SETUPS]
        return [item for item in results if item['status'] == 'PUBLIC_CANDIDATE_READY']

    def dispatch(self, ready):
        with patch.object(delivery, '_post', side_effect=self.post):
            return workflow.dispatch_ready_candidates('FALCON', ready, values=manual.VALUES,
                ledger_path=self.path, network_authorized=True, public_delivery_authorized=True,
                manual_tracking=True)

    def test_both_fresh_consolidate_restart_dedup_and_both_persistent_suppress(self):
        snap, now = snapshot(public=True)
        ready = self.ready(snap, now)
        self.assertEqual(len(ready), 2)
        out = self.dispatch(ready)
        self.assertEqual(out['status'], 'CONFIRMED', out)
        self.assertEqual(len(self.sent), 1)
        self.assertIn('FALCON15 + FALCON30', self.sent[0]['text'])
        self.assertEqual(self.dispatch(self.ready(snap, now+1000))['reason'], 'PRIOR_ATTEMPT_NO_RETRY')
        later, later_now = advance(snap, now, 101)
        self.assertEqual(self.ready(later, later_now), [])
        self.assertEqual(len(self.sent), 1)

    def test_real_f15_persistent_f30_fresh_at_its_own_window_start(self):
        for side in ('LONG', 'SHORT'):
            snap, now = h.fixture('FALCON30', side)
            price(snap['frames']['15m'][-3], 101 if side == 'LONG' else 99)
            value = 101.5 if side == 'LONG' else 98.5
            price(snap['frames']['15m'][-2], value)
            snap['quote']['price'] = value
            snap.update(synthetic=False, source='BINGX_PUBLIC_SWAP', symbol='BTC-USDT',
                frame_received_at_ms={tf: now for tf in snap['frames']},
                source_qualified=False, delivery_allowed=False, live_allowed=False,
                manual_trade_authorized=False)
            before, before_now = historical(snap, now)
            prior15, _ = h.original_oracle(before, 'FALCON15', before_now, h.CONFIG)
            prior30, _ = h.original_oracle(before, 'FALCON30', before_now, h.CONFIG)
            self.assertEqual(prior15['side'], side)
            self.assertIsNone(prior30)
            ready = self.ready(snap, now)
            self.assertEqual([r['candidate']['signal']['setup'] for r in ready], ['FALCON30'])

    def test_real_f15_fresh_f30_persistent_own_range_filter(self):
        for side in ('LONG', 'SHORT'):
            snap, now = snapshot(side, previous=True, public=True)
            orb_ts = int(h.datetime.fromisoformat('2026-01-05T14:30:00+00:00').timestamp()*1000)
            row = next(r for r in snap['frames']['15m'] if r[0] == orb_ts)
            center = 100.1 if side == 'LONG' else 99.9
            row[1:5] = [center, center+.19, center-.19, center]
            # Narrow ORB15 fails the unchanged MIN_RANGE_ATR on previous,
            # then passes as ATR falls. Wider ORB30 qualifies on both candles.
            before, before_now = historical(snap, now)
            prior15, counts = h.original_oracle(before, 'FALCON15', before_now, h.CONFIG)
            prior30, _ = h.original_oracle(before, 'FALCON30', before_now, h.CONFIG)
            self.assertIsNone(prior15)
            self.assertEqual(counts, dict(reprovados_range=1))
            self.assertEqual(prior30['side'], side)
            for setup in SETUPS:
                current, _ = h.original_oracle(snap, setup, now, h.CONFIG)
                self.assertEqual(current['side'], side)
            ready = self.ready(snap, now)
            self.assertEqual([r['candidate']['signal']['setup'] for r in ready], ['FALCON15'])

    def test_fresh_but_different_economics_stay_separate(self):
        snap, now = snapshot(public=True)
        # ORB30 contains a wider low than ORB15, without changing breakouts.
        orb_second_ts = int(h.datetime.fromisoformat('2026-01-05T14:45:00+00:00').timestamp()*1000)
        next(row for row in snap['frames']['15m'] if row[0] == orb_second_ts)[3] = 99.4
        ready = self.ready(snap, now)
        self.assertEqual(len(ready), 2)
        self.assertNotEqual(ready[0]['candidate']['signal']['stop'], ready[1]['candidate']['signal']['stop'])
        self.assertEqual(self.dispatch(ready)['status'], 'CONFIRMED')
        self.assertEqual(len(self.sent), 2)

    def test_delivery_gates_cannot_rearm_next_candle(self):
        for gate in ('drift', 'stale', 'future', 'delivery', 'ttl'):
            snap, now = snapshot(public=True)
            bad = copy.deepcopy(snap)
            if gate == 'drift':
                bad['quote']['price'] *= 1.006
            elif gate == 'stale':
                bad['quote']['at_ms'] = now - h.POLICY['quote_max_age_ms'] - 1
            elif gate == 'future':
                bad['quote']['at_ms'] = now + 1
            with patch.object(delivery, '_post', return_value=(403, dict(ok=False))) as post:
                if gate == 'ttl':
                    expired_now = now + h.POLICY['signal_ttl_ms']
                    bad['observed_at_ms'] = bad['quote']['at_ms'] = expired_now
                    bad['frame_received_at_ms'] = {tf: expired_now for tf in bad['frames']}
                    self.assertEqual(self.ready(bad, expired_now), [])
                else:
                    ready = self.ready(bad, now)
                    if gate == 'delivery':
                        out = workflow.dispatch_ready_candidates('FALCON', ready, values=manual.VALUES,
                            ledger_path=self.path, network_authorized=True,
                            public_delivery_authorized=True, manual_tracking=True)
                        self.assertNotEqual(out['status'], 'CONFIRMED')
                        self.assertEqual(post.call_count, 1)
                    else:
                        self.assertEqual(ready, [])
                        post.assert_not_called()
            later, later_now = advance(snap, now, 101)
            self.assertEqual(self.ready(later, later_now), [], gate)
        self.assertEqual(self.sent, [])


if __name__ == '__main__':
    h.unittest.main()
