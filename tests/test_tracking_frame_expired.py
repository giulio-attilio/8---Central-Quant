"""Offline regression proof using real SQLite tracking and intake validation."""
import io
import sqlite3
from contextlib import closing, redirect_stdout
from pathlib import Path
from unittest.mock import patch
import test_donkey_strategic_stop_v2 as h
import signal_only_runner as runner


class IntakeExpiry(h.base.Harness):
    def activate(self):
        self.send('DONKEY', [h.signal('DONKEY')])
        self.enter_last('DONKEY')

    def dump(self):
        with closing(sqlite3.connect(self.path)) as db:
            return list(db.iterdump())

    def run_frames(self, frames, *, cycles=1, observe_error=None):
        config = h.service_fixtures.config()
        for entry in config['bots'].values():
            entry['symbols'] = ['BTC-USDT']
        args = h.service_fixtures.ServiceTests().supervisor_args(self.path)
        args.update(max_cycles=cycles, donkey_operator_id=77, values=h.VALUES)
        sources = dict(FALCON=h.guard_harness.SOURCE, DONKEY=h.fixtures.SOURCE)
        with patch.object(h.tracking, 'provision'), \
             patch.object(h.tracking.ManualTradeTracker, 'check_polling'), \
             patch.object(h.tracking.ManualTradeTracker, 'poll'), \
             patch.object(h.tracking.ManualTradeTracker, 'flush') as flush, \
             patch.object(h.service, 'collect_snapshot', side_effect=frames) as collect, \
             patch.object(h.service.time, 'time_ns', return_value=h.LATER*1000000), \
             patch.object(h.service, 'run_once', return_value=dict(status='BLOCKED', reason='NO_SIGNAL')) as analyze, \
             patch.object(h.delivery, '_post') as post, redirect_stdout(io.StringIO()) as logs:
            if observe_error:
                with patch.object(h.tracking.ManualTradeTracker, 'observe', side_effect=observe_error):
                    out = h.service.run_service(config, sources, **args)
            else:
                out = h.service.run_service(config, sources, **args)
        post.assert_not_called()
        return out, analyze.call_count, collect.call_count, flush.call_count, args['stop_event'].waits, logs.getvalue()

    def expired(self):
        snap = h.snapshot(closed_price=90)
        for row in snap['frames']['4h']:
            row[0] -= h.H4
        snap['quote']['price'] = 200  # Would generate TP50 if observed.
        return snap

    def test_expiry_preserves_entire_ledger_no_tp_stop_delivery_or_halt(self):
        self.activate()
        before = self.dump()
        out, evaluations, collections, flushes, waits, logs = self.run_frames([self.expired()])
        self.assertEqual(out['status'], 'STOPPED', out)
        self.assertEqual(out['discarded_snapshots'], 1)
        self.assertEqual((evaluations, collections, flushes), (0, 1, 1))
        self.assertEqual(self.dump(), before)
        self.assertEqual(len(self.active()), 1)
        self.assertIn('FRAME_EXPIRED', logs)
        self.assertFalse(Path(self.path + '.halted').exists())

    def test_next_paced_cycle_valid_frame_still_generates_real_strategic_stop(self):
        self.activate()
        out, evaluations, collections, flushes, waits, _ = self.run_frames(
            [self.expired(), h.snapshot(closed_price=90)], cycles=2)
        self.assertEqual(out['status'], 'STOPPED', out)
        self.assertEqual(out['discarded_snapshots'], 1)
        self.assertEqual((evaluations, collections, flushes), (5, 2, 2))
        self.assertEqual(waits, [1.0])
        self.assertFalse(self.active())
        with closing(h.tracking.connect(self.path)) as db:
            events = db.execute('SELECT kind FROM manual_trade_event_v1').fetchall()
        self.assertEqual([row[0] for row in events], ['STOP'])

    def test_stale_quote_is_discarded_before_mutation(self):
        self.activate()
        snap = h.snapshot()
        snap['quote']['at_ms'] -= 6000
        before = self.dump()
        out, evaluations, *_ = self.run_frames([snap])
        self.assertEqual(out['status'], 'STOPPED', out)
        self.assertEqual(out['tracking_quote_skips'], 1)
        self.assertEqual(evaluations, 0)
        self.assertEqual(self.dump(), before)

    def test_persisted_clock_regression_is_fatal_even_with_expired_frame(self):
        with closing(h.tracking.connect(self.path)) as db, db:
            db.execute('UPDATE manual_trade_clock_v1 SET clock=? WHERE id=1', (h.LATER+1,))
        out, evaluations, *_ = self.run_frames([self.expired()])
        self.assertEqual(out['status'], 'FAILED', out)
        self.assertEqual(out['reason'], 'MANUAL_TRACKING_CLOCK_REGRESSION')
        self.assertEqual(evaluations, 0)
        self.assertNotIn('discarded_snapshots', out)

    def test_sqlite_clock_unclassified_and_post_intake_expiry_remain_fatal(self):
        for error in (sqlite3.OperationalError('fixture'),
                      ValueError('MANUAL_TRACKING_CLOCK_REGRESSION'),
                      RuntimeError('fixture'), h.service.PublicDataError('FRAME_EXPIRED')):
            with self.subTest(error=repr(error)):
                out, evaluations, *_ = self.run_frames([h.snapshot()], observe_error=error)
                self.assertEqual(out['status'], 'FAILED', out)
                self.assertEqual(out['stage'], 'tracking_observe')
                self.assertEqual(evaluations, 0)
                self.assertNotIn('discarded_snapshots', out)

    def test_h4_expiry_after_quote_commit_is_fatal(self):
        self.activate()
        snap = h.snapshot()
        snap['quote']['price'] = 200
        with patch.object(h.tracking.ManualTradeTracker, 'observe_h4',
                          side_effect=h.service.PublicDataError('FRAME_EXPIRED')):
            out, evaluations, *_ = self.run_frames([snap])
        self.assertEqual(out['status'], 'FAILED', out)
        self.assertEqual(out['reason'], 'FRAME_EXPIRED')
        self.assertEqual(evaluations, 0)
        self.assertNotIn('discarded_snapshots', out)
        self.assertIsNotNone(self.active()[0]['tp_ms'])

    def test_runner_does_not_write_halt_for_benign_intake_expiry(self):
        self.activate()
        config = h.service_fixtures.config()
        for entry in config['bots'].values():
            entry['symbols'] = ['BTC-USDT']
        sources = dict(FALCON=h.guard_harness.SOURCE, DONKEY=h.fixtures.SOURCE)
        real_run = h.service.run_service
        def bounded(*args, **kwargs):
            return real_run(*args, **kwargs, max_cycles=1)
        with patch.object(runner, 'run_service', side_effect=bounded), \
             patch.object(runner.os, 'environ', dict(h.VALUES)), \
             patch.object(h.tracking.ManualTradeTracker, 'check_polling'), \
             patch.object(h.tracking.ManualTradeTracker, 'poll'), \
             patch.object(h.tracking.ManualTradeTracker, 'flush'), \
             patch.object(h.service, 'collect_snapshot', return_value=self.expired()), \
             patch.object(h.service.time, 'time_ns', return_value=h.LATER*1000000), \
             patch.object(h.delivery, '_post') as post:
            out = runner.execute(config, sources, Path(self.path), authorized=True,
                                 donkey_operator_id=77)
        self.assertEqual(out['status'], 'STOPPED', out)
        self.assertFalse(Path(self.path + '.halted').exists())
        post.assert_not_called()
