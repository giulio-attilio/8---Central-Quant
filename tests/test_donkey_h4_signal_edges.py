"""Synthetic H4 edges and fake delivery only; guards precede project imports."""
import ast
import copy
import importlib
import sys
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_signal_only_integration as fixtures
import test_manual_signal_tracking as manual

donkey, workflow, delivery = fixtures.donkey, fixtures.workflow, fixtures.delivery
SOURCE, CONFIG, POLICY = fixtures.SOURCE, fixtures.CONFIG, fixtures.harness.POLICY
H4 = donkey.PERIODS['4h']
VARIANTS = workflow.DONKEY_VARIANTS


def snapshot(setup='DONKEY', side='LONG', *, edge=True, public=False):
    snap, now = fixtures.donkey_fixture(side, edge=edge)
    if setup == 'EARLY_DONKEY':
        snap, now = fixtures.donkey_fixture('SHORT', edge=False)
        for i, row in enumerate(snap['frames']['4h']):
            if i >= 189:
                price = 130.5 + (i-189)*0.6 - (4 if edge and i == 197 else 0)
                row[1:5] = [price, price+0.5, price-0.5, price]
            if side == 'SHORT':
                opening, high, low, close = row[1:5]
                row[1:5] = [300-opening, 300-low, 300-high, 300-close]
    snap['quote']['price'] = snap['frames']['4h'][-2][4]
    if public:
        snap.update(synthetic=False, source='BINGX_PUBLIC_SWAP', symbol='BTC-USDT',
            frame_received_at_ms={tf: now for tf in snap['frames']},
            source_qualified=False, delivery_allowed=False, live_allowed=False,
            manual_trade_authorized=False)
    return snap, now


def replace_price(row, price, width=0.5):
    row[1:5] = [price, price+width, price-width, price]


def advance(snap, now, price):
    """Close the forming H4, append one forming row; never scan old edges."""
    snap = copy.deepcopy(snap)
    rows = snap['frames']['4h']
    replace_price(rows[-1], price)
    rows.append([rows[-1][0]+H4, price, price+0.5, price-0.5, price, 100.])
    now += H4
    snap['observed_at_ms'] = snap['quote']['at_ms'] = now
    snap['quote']['price'] = price
    if not snap['synthetic']:
        snap['frame_received_at_ms'] = {tf: now for tf in snap['frames']}
    return snap, now


class H4Edges(fixtures.unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ns = dict(CONFIG, pd=donkey.pd)
        exec(donkey.reviewed_analysis(SOURCE), cls.ns)

    def core_sides(self, snap, setup):
        rows = snap['frames']['4h'][-200:]
        frame = self.ns['preparar_df'](donkey.pd.DataFrame(rows,
            columns=['time', 'open', 'high', 'low', 'close', 'volume']))
        core = self.ns['strategy_core_h4_side']
        return core(frame.iloc[-3], setup), core(frame.iloc[-2], setup), frame

    def analyze(self, snap, now, setup='DONKEY', **changes):
        return donkey.analyze(SOURCE, snap, CONFIG, POLICY, setup=setup, now_ms=now,
                              public_data_authorized=not snap['synthetic'], **changes)

    def test_all_variants_directional_truth_table_real_indicators(self):
        for setup in VARIANTS:
            for side in ('LONG', 'SHORT'):
                for previous, current in ((False, True), (True, True), (False, False), (True, False)):
                    with self.subTest(setup=setup, side=side, previous=previous, current=current):
                        snap, now = snapshot(setup, side, edge=not previous)
                        if not previous and not current:
                            for row in snap['frames']['4h']:
                                replace_price(row, 100.)
                        elif not current:
                            _, _, frame = self.core_sides(snap, setup)
                            price = float(frame.iloc[-3]['ema20']) + (-0.5 if side == 'LONG' else 0.5)
                            replace_price(snap['frames']['4h'][-2], price)
                        snap['quote']['price'] = snap['frames']['4h'][-2][4]
                        before, after, _ = self.core_sides(snap, setup)
                        self.assertEqual((before == side, after == side), (previous, current))
                        out = self.analyze(snap, now, setup)
                        self.assertEqual(out['status'], 'OFFLINE_PREVIEW' if not previous and current else 'NO_SIGNAL', out)
                        self.assertIs(out['live_allowed'], False)

    def test_rearm_only_after_core_loses_qualification_both_sides(self):
        for side in ('LONG', 'SHORT'):
            snap, now = snapshot(side=side)
            self.assertEqual(self.analyze(snap, now)['status'], 'OFFLINE_PREVIEW')
            old_id = self.analyze(snap, now)['signal']['signal_id']
            entry = snap['quote']['price']
            snap, now = advance(snap, now, entry)
            self.assertEqual(self.core_sides(snap, 'DONKEY')[:2], (side, side))
            self.assertEqual(self.analyze(snap, now)['status'], 'NO_SIGNAL')
            snap, now = advance(snap, now, entry + (-3 if side == 'LONG' else 3))
            self.assertEqual(self.analyze(snap, now)['status'], 'NO_SIGNAL')
            snap, now = advance(snap, now, entry)
            out = self.analyze(snap, now)
            self.assertEqual(self.core_sides(snap, 'DONKEY')[:2], (None, side))
            self.assertEqual(out['status'], 'OFFLINE_PREVIEW', out)
            self.assertNotEqual(out['signal']['signal_id'], old_id)

    def test_original_daily_permission_both_sides_not_daily_trigger(self):
        for side in ('LONG', 'SHORT'):
            opposite = 'SHORT' if side == 'LONG' else 'LONG'
            for edge in (False, True):
                for daily_valid in (False, True):
                    with self.subTest(side=side, edge=edge, daily_valid=daily_valid):
                        snap, now = snapshot('DONKEY_ORIGINAL', side, edge=edge)
                        daily, _ = fixtures.donkey_fixture(side if daily_valid else opposite, edge=False)
                        snap['frames']['1d'] = daily['frames']['1d']
                        out = self.analyze(snap, now, 'DONKEY_ORIGINAL')
                        self.assertEqual(out['status'], 'OFFLINE_PREVIEW' if edge and daily_valid else 'NO_SIGNAL', out)
            # Daily false->true alone must never manufacture an H4 edge.
            snap, now = snapshot('DONKEY_ORIGINAL', side, edge=False)
            row = snap['frames']['1d'][-3]
            replace_price(row, row[4] + (-3 if side == 'LONG' else 3))
            daily = self.ns['preparar_df'](donkey.pd.DataFrame(snap['frames']['1d'][-120:],
                columns=['time', 'open', 'high', 'low', 'close', 'volume']))
            sign = 1 if side == 'LONG' else -1
            self.assertLess(sign*(daily.iloc[-3]['close']-daily.iloc[-3]['ema20']), 0)
            self.assertGreater(sign*(daily.iloc[-2]['close']-daily.iloc[-2]['ema20']), 0)
            self.assertEqual(self.analyze(snap, now, 'DONKEY_ORIGINAL')['status'], 'NO_SIGNAL')

    def test_forming_h4_and_daily_candles_do_not_affect_edges(self):
        for setup in VARIANTS:
            for side in ('LONG', 'SHORT'):
                snap, now = snapshot(setup, side)
                first = self.analyze(snap, now, setup)
                for rows in snap['frames'].values():
                    replace_price(rows[-1], 999.)
                self.assertEqual(self.analyze(snap, now, setup)['signal'], first['signal'])

    def test_expired_edge_and_restart_have_no_backlog(self):
        for setup in VARIANTS:
            snap, now = snapshot(setup)
            expired = copy.deepcopy(snap)
            expired['observed_at_ms'] = expired['quote']['at_ms'] = now+60000
            self.assertEqual(self.analyze(expired, now+60000, setup)['reason'], 'EXPIRED')
            later, later_now = advance(snap, now, snap['quote']['price'])
            # New analysis instances and module reload cannot resurrect the old edge.
            for _ in range(2):
                importlib.reload(donkey)
                self.assertEqual(self.analyze(later, later_now, setup)['status'], 'NO_SIGNAL')

    def test_projected_core_preserves_strict_and_early_inclusive_boundaries(self):
        core = self.ns['strategy_core_h4_side']
        for setup in VARIANTS:
            for macd in (-1., 0., 1.):
                for close in (99., 100., 101.):
                    for ema50 in (99., 100., 101.):
                        candle = dict(close=close, ema20=100., ema50=ema50, macd=macd)
                        if setup == 'EARLY_DONKEY':
                            expected = ('LONG' if close > 100 and macd > 0 and 100 <= ema50
                                        else 'SHORT' if close < 100 and macd < 0 and 100 >= ema50 else None)
                        else:
                            expected = ('LONG' if close > 100 > ema50 and macd > 0
                                        else 'SHORT' if close < 100 < ema50 and macd < 0 else None)
                        with self.subTest(setup=setup, candle=candle):
                            self.assertEqual(core(candle, setup), expected)

    def test_source_digest_and_original_detector_bodies_remain_pinned(self):
        self.assertEqual(donkey.SOURCE_DIGEST, 'ae5e1e1caea30ef9f4e289f04e28ebcaf95fa53e86c625dde471cb794deac6a6')
        static = (fixtures.ROOT / 'signals_sources/donkey.txt').read_text(encoding='utf-8-sig')
        donkey.reviewed_analysis(static)
        for source in (SOURCE, static):
            snap, now = snapshot()
            self.assertEqual(donkey.analyze(source, snap, CONFIG, POLICY,
                setup='DONKEY', now_ms=now)['status'], 'OFFLINE_PREVIEW')
            with self.assertRaises(fixtures.harness.offline.OfflineInputError):
                donkey.reviewed_analysis(source.replace('macd > 0', 'macd >= 0'))
        # The edge helper is compiled alongside the original functions, not into them.
        original_nodes = [n for n in ast.walk(ast.parse(SOURCE))
                          if isinstance(n, ast.FunctionDef) and n.name in donkey.FUNCTIONS]
        self.assertEqual(len(original_nodes), 9)


class EdgeDelivery(manual.Harness):
    def ready(self, snap, now, setups=VARIANTS):
        with patch.object(workflow.time, 'monotonic', return_value=0):
            results = [workflow.run_once('DONKEY', SOURCE, snap, CONFIG, POLICY,
                setup=setup, now_ms=now, network_authorized=True, public_data_authorized=True,
                public_delivery_authorized=True, defer_public_delivery=True) for setup in setups]
        return [item for item in results if item['status'] == 'PUBLIC_CANDIDATE_READY']

    def dispatch(self, ready):
        with patch.object(delivery, '_post', side_effect=self.post):
            return workflow.dispatch_ready_candidates('DONKEY', ready, values=manual.VALUES,
                ledger_path=self.path, network_authorized=True, public_delivery_authorized=True,
                manual_tracking=True)

    def test_real_new_edges_consolidate_and_restart_dedup_remains(self):
        for side in ('LONG', 'SHORT'):
            snap, now = snapshot(side=side, public=True)
            if side == 'SHORT':
                # Existing per-setup/symbol/candle dedup also excludes opposite
                # directions on that same candle. Keep that contract intact.
                snap['symbol'] = 'ETH-USDT'
            ready = self.ready(snap, now)
            self.assertEqual([item['candidate']['signal']['setup'] for item in ready], list(VARIANTS[:2]))
            out = self.dispatch(ready)
            self.assertEqual(out['status'], 'CONFIRMED', out)
            self.assertIn('Confirmação: DONKEY + DONKEY_ORIGINAL', self.sent[-1]['text'])
            importlib.reload(workflow)
            before = Path(self.path).read_bytes()
            self.assertEqual(self.dispatch(self.ready(snap, now))['reason'], 'PRIOR_ATTEMPT_NO_RETRY')
            self.assertEqual(Path(self.path).read_bytes(), before)
        self.assertEqual(len(self.sent), 2)
        with closing(manual.tracking.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM manual_trade_v1').fetchone()[0], 2)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM manual_trade_candidate_v1').fetchone()[0], 4)

    def test_current_daily_veto_keeps_original_out_of_confirmation(self):
        snap, now = snapshot(public=True)
        bearish, _ = fixtures.donkey_fixture('SHORT', edge=False)
        snap['frames']['1d'] = bearish['frames']['1d']
        ready = self.ready(snap, now)
        self.assertEqual([item['candidate']['signal']['setup'] for item in ready], ['DONKEY'])
        self.assertEqual(self.dispatch(ready)['status'], 'CONFIRMED')
        self.assertIn('Setup: DONKEY', self.sent[0]['text'])
        self.assertNotIn('DONKEY_ORIGINAL', self.sent[0]['text'])

    def test_blocked_drift_loses_edge_next_h4_even_after_restart(self):
        snap, now = snapshot(public=True)
        row = snap['frames']['4h'][-2]
        replace_price(row, row[4], width=0.8)
        snap['quote']['price'] = row[4]*1.006
        with patch.object(delivery, '_post') as post:
            out = workflow.run_once('DONKEY', SOURCE, snap, CONFIG, POLICY, setup='DONKEY',
                now_ms=now, network_authorized=True, public_data_authorized=True,
                public_delivery_authorized=True, values=manual.VALUES, ledger_path=self.path)
            self.assertEqual(out['reason'], 'ENTRY_DEVIATION', out)
            post.assert_not_called()
        later, later_now = advance(snap, now, row[4])
        importlib.reload(donkey)
        self.assertEqual(self.ready(later, later_now), [])
        self.assertEqual(self.dispatch([])['status'], 'BLOCKED')
        self.assertEqual(self.sent, [])

    def test_previous_spike_and_risk_veto_do_not_rearm_persistent_core(self):
        for gate in ('spike', 'risk'):
            snap, now = snapshot(public=True)
            if gate == 'spike':
                row = snap['frames']['4h'][-2]
                row[2], row[3] = row[4]+20, row[4]-20
                cfg = CONFIG
            else:
                cfg = dict(CONFIG, DONKEY_MAX_RISK_PCT=0.01)
            self.assertEqual(donkey.analyze(SOURCE, snap, cfg, POLICY,
                setup='DONKEY_ORIGINAL', now_ms=now, public_data_authorized=True)['status'], 'NO_SIGNAL')
            later, later_now = advance(snap, now, snap['frames']['4h'][-2][4])
            self.assertEqual(self.ready(later, later_now), [])

    def test_stale_quote_or_delivery_failure_loses_edge_next_h4(self):
        snap, now = snapshot(public=True)
        stale = copy.deepcopy(snap)
        stale['quote']['at_ms'] = now-POLICY['quote_max_age_ms']-1
        with patch.object(delivery, '_post') as post:
            self.assertEqual(self.ready(stale, now), [])
            post.assert_not_called()
        ready = self.ready(snap, now)
        with patch.object(delivery, '_post', return_value=(403, dict(ok=False))) as post:
            failed = workflow.dispatch_ready_candidates('DONKEY', ready, values=manual.VALUES,
                ledger_path=self.path, network_authorized=True, public_delivery_authorized=True,
                manual_tracking=True)
            self.assertNotEqual(failed['status'], 'CONFIRMED')
            self.assertEqual(post.call_count, 1)
        later, later_now = advance(snap, now, snap['quote']['price'])
        self.assertEqual(self.ready(later, later_now), [])

    def test_only_candidate_edges_participate_and_economic_differences_stay_separate(self):
        # Boundary fixtures only: these combinations are not claims of realizable
        # H4 states (Normal/Original cores coincide; Early is mutually exclusive).
        ready = [dict(status='PUBLIC_CANDIDATE_READY', candidate=manual.candidate(
            manual.signal(setup, stop=99, tp50=101, candle=manual.NOW-3000))) for setup in VARIANTS]
        self.assertEqual(self.dispatch(ready)['status'], 'CONFIRMED')
        self.assertIn('Confirmação: ' + ' + '.join(VARIANTS), self.sent[-1]['text'])
        next_ready = [dict(status='PUBLIC_CANDIDATE_READY', candidate=manual.candidate(
            manual.signal('DONKEY', suffix='new', stop=99, tp50=101, candle=manual.NOW-2000))),
            dict(status='BLOCKED', reason='NO_SIGNAL')]
        edges = [item for item in next_ready if item['status'] == 'PUBLIC_CANDIDATE_READY']
        out = self.dispatch(edges)
        self.assertEqual(out['status'], 'CONFIRMED', out)
        self.assertIn('Setup: DONKEY', self.sent[-1]['text'])
        separate = [dict(status='PUBLIC_CANDIDATE_READY', candidate=manual.candidate(
            manual.signal(setup, suffix='different', stop=99, tp50=101+i)))
            for i, setup in enumerate(VARIANTS[:2])]
        self.assertEqual(self.dispatch(separate)['status'], 'CONFIRMED')
        self.assertEqual(len(self.sent), 4)


if __name__ == '__main__':
    fixtures.unittest.main()
