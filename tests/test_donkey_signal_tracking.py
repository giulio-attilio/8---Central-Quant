"""Offline only: install audit/network/import guards before repository imports."""
import copy
import json
import sys
import tempfile
import unittest
from contextlib import closing, contextmanager
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_signal_only_integration as fixture
import donkey_signal_tracking as tracking
import telegram_signal_delivery as delivery


class TrackingTests(unittest.TestCase):
    def test_service_fixed_diagnostics_redact_transport_and_untrusted_errors(self):
        import signal_only_service as service
        cases = [(TimeoutError('secret-url'), 'IO_TIMEOUT'),
                 (ValueError('secret-url'), 'SERVICE_VALIDATION_OR_IO_FAILED'),
                 (ValueError('DONKEY_REFERENCE_H4_REQUIRED'), 'DONKEY_REFERENCE_H4_REQUIRED'),
                 (service.PublicDataError('QUOTE_STALE_OR_FUTURE'), 'QUOTE_STALE_OR_FUTURE')]
        for error, code in cases:
            self.assertEqual(service.service_error_code(error), code)

    def test_supervisor_reports_tracking_stage_and_stops_without_evaluation(self):
        import test_signal_only_service as sf
        import threading
        for method, stage in [('check_polling', 'tracking_webhook_check'),
                              ('poll', 'tracking_poll'), ('observe', 'tracking_observe'),
                              ('flush', 'tracking_notice_flush')]:
            with self.subTest(method=method), patch.object(tracking, 'ReferenceTracker') as factory, \
                 patch.object(sf.service, 'collect_snapshot', return_value=self.snapshot), \
                 patch.object(sf.service, 'run_once') as evaluate:
                getattr(factory.return_value, method).side_effect = TimeoutError('private-token')
                out = sf.service.run_service(sf.config(), dict(FALCON=fixture.harness.SOURCE, DONKEY=fixture.SOURCE),
                    values=fixture.VALUES, ledger_path=self.path, stop_event=threading.Event(),
                    service_authorized=True, public_data_authorized=True, public_delivery_authorized=True,
                    max_cycles=1, donkey_operator_id=77)
                self.assertEqual(out['status'], 'FAILED')
                self.assertEqual(out['reason'], 'IO_TIMEOUT')
                self.assertEqual(out['stage'], stage)
                self.assertNotIn('private-token', str(out))
                evaluate.assert_not_called()

    @contextmanager
    def db(self):
        with closing(tracking.connect(self.path)) as db, db:
            yield db

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = str(Path(self.tmp.name) / 'ledger.sqlite')
        delivery.initialize_ledger(self.path)
        tracking.provision(self.path)
        self.tracker = tracking.ReferenceTracker(self.path, fixture.VALUES, 77, authorized=True)
        self.snapshot, self.now = fixture.PublicPreviewTests().public_fixture('DONKEY')
        self.snapshot['frames'] = {'4h': self.snapshot['frames']['4h']}
        self.snapshot['frame_received_at_ms'] = {'4h': self.now}
        self.policy = dict(snapshot_max_age_ms=60000, quote_max_age_ms=15000)

    def offer(self, setup='DONKEY', side='LONG', identity='one'):
        signal = dict(synthetic=False, setup=setup, symbol='TEST-USDT', side=side,
                      entry=100., stop=90. if side == 'LONG' else 110., tp50=110. if side == 'LONG' else 90.)
        with self.db() as db:
            db.execute("INSERT INTO delivery_v1 VALUES (?, ?, ?, 'CONFIRMED', ?, 9)",
                       (identity, identity, self.tracker.route, self.now))
            markup = tracking.offer(db, identity, self.tracker.route, signal, self.now + 900000)
        return markup['inline_keyboard'][0][0]['callback_data']

    def click(self, key, uid=1, **changes):
        query = dict(id='callback', data=key, **{'from': dict(id=77, is_bot=False)},
                     message=dict(message_id=9, chat=dict(id=202)))
        query.update(changes)
        return dict(update_id=uid, callback_query=query)

    def state(self, data):
        with self.db() as db:
            return dict(db.execute('SELECT * FROM donkey_reference_v1 WHERE ref=?', (data[3:],)).fetchone())

    def observe(self, price, advance=1):
        self.now += advance
        self.snapshot['observed_at_ms'] = self.now
        self.snapshot['quote'] = dict(price=price, at_ms=self.now)
        self.tracker.observe(self.snapshot, self.now, self.policy)

    def test_opt_in_and_existing_ledger_required(self):
        with self.assertRaises(ValueError):
            tracking.ReferenceTracker(self.path, fixture.VALUES, 77)
        with self.assertRaises(Exception):
            tracking.provision(str(Path(self.tmp.name) / 'missing.sqlite'))
        self.assertFalse((Path(self.tmp.name) / 'missing.sqlite').exists())

    def test_offer_click_duplicate_restart_and_three_independent_variants(self):
        keys = [self.offer(setup, identity=setup) for setup in sorted(tracking.SETUPS)]
        self.assertEqual(len(set(keys)), 3)
        for i, key in enumerate(keys):
            self.assertLessEqual(len(key.encode()), 64)
            self.tracker.accept(self.click(key, i + 1), self.now)
        tracking.provision(self.path)
        tracker = tracking.ReferenceTracker(self.path, fixture.VALUES, 77, authorized=True)
        tracker.accept(self.click(keys[0], 4), self.now + 1)
        self.assertTrue(all(self.state(key)['state'] == 'ACTIVE' for key in keys))
        self.assertEqual(self.state(keys[0])['active_ms'], self.now)

    def test_wrong_user_chat_message_and_forged_callback_rejected(self):
        key = self.offer()
        variants = [dict(**{'from': dict(id=78, is_bot=False)}),
                    dict(message=dict(message_id=9, chat=dict(id=303))),
                    dict(message=dict(message_id=10, chat=dict(id=202))),
                    dict(data='dq:' + '0' * 32), dict(**{'from': dict(id=77, is_bot=True)})]
        for i, fields in enumerate(variants):
            self.tracker.accept(self.click(key, i + 1, **fields), self.now)
            self.assertEqual(self.state(key)['state'], 'WAITING')

    def test_expired_unconfirmed_and_changed_route_do_not_activate(self):
        key = self.offer()
        with self.db() as db:
            db.execute("UPDATE delivery_v1 SET status='UNKNOWN'")
        self.tracker.accept(self.click(key), self.now)
        self.assertEqual(self.state(key)['state'], 'WAITING')
        with self.db() as db:
            db.execute("UPDATE delivery_v1 SET status='CONFIRMED'")
        self.tracker.accept(self.click(key, 2), self.now + 900000)
        self.assertEqual(self.state(key)['state'], 'EXPIRED')
        with self.assertRaises(ValueError):
            tracking.ReferenceTracker(self.path, dict(fixture.VALUES, DONKEY_H4_CHAT_ID='999'), 77, authorized=True)

    def test_long_tp50_break_even_stop_terminal_and_no_reactivation(self):
        key = self.offer()
        self.tracker.accept(self.click(key), self.now)
        self.observe(111)
        row = self.state(key)
        self.assertEqual(row['state'], 'RUNNER')
        self.assertAlmostEqual(row['stop'], 100.1)
        self.observe(100)
        self.assertEqual(self.state(key)['state'], 'CLOSED')
        self.tracker.accept(self.click(key, 2), self.now)
        self.observe(120)
        with self.db() as db:
            kinds = [r[0] for r in db.execute('SELECT kind FROM donkey_reference_events_v1 ORDER BY rowid')]
        self.assertEqual(kinds, ['TP50', 'STOP'])
        self.assertEqual(self.state(key)['state'], 'CLOSED')

    def test_short_tp50_and_original_stop_before_partial(self):
        short = self.offer(side='SHORT')
        long = self.offer(identity='other')
        self.tracker.accept(self.click(short, 1), self.now)
        self.tracker.accept(self.click(long, 2), self.now)
        self.observe(89)
        self.assertAlmostEqual(self.state(short)['stop'], 99.9)
        self.assertEqual(self.state(short)['state'], 'RUNNER')
        self.assertEqual(self.state(long)['state'], 'CLOSED')

    def test_ema_exit_only_closed_h4_after_tp50(self):
        key = self.offer()
        self.tracker.accept(self.click(key), self.now)
        self.observe(111)
        self.observe(105)  # Old closed H4 cannot close a new runner.
        self.assertEqual(self.state(key)['state'], 'RUNNER')
        rows = self.snapshot['frames']['4h']
        end = rows[-1][0] + tracking.PERIODS['4h']
        # New closed candle below EMA, quote still above reference stop.
        rows[-1] = [rows[-1][0], 110., 150., 80., 90., 100.]
        rows.append([end, 105., 106., 104., 105., 100.])
        rows.pop(0)
        self.now = end + 1000
        self.snapshot['frame_received_at_ms']['4h'] = self.now
        self.observe(105)
        self.assertEqual(self.state(key)['state'], 'CLOSED')
        with self.db() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM donkey_reference_events_v1 WHERE kind='EMA20_EXIT'").fetchone()[0], 1)

    def test_stale_data_clock_regression_and_duplicate_quote_do_not_advance(self):
        key = self.offer()
        self.tracker.accept(self.click(key), self.now)
        with self.assertRaises(ValueError):
            self.tracker.accept(self.click(key, 2), self.now - 1)
        with self.assertRaises(Exception):
            self.tracker.observe(self.snapshot, self.now + 100000, self.policy)
        self.assertEqual(self.state(key)['state'], 'ACTIVE')
        self.observe(105)
        self.snapshot['quote']['price'] = 111
        self.tracker.observe(self.snapshot, self.now, self.policy)
        self.assertEqual(self.state(key)['state'], 'ACTIVE')

    def test_unknown_delivery_latched_and_no_retry_after_restart(self):
        key = self.offer()
        self.tracker.accept(self.click(key), self.now)
        self.observe(111)
        with patch.object(delivery, '_post', side_effect=TimeoutError('PRIVATE')) as post:
            with self.assertRaises(Exception):
                self.tracker.flush()
            with self.assertRaises(ValueError):
                self.tracker.flush()
            post.assert_called_once()

    def test_confirmed_notice_once_and_no_price_or_trade_claim(self):
        key = self.offer()
        self.tracker.accept(self.click(key), self.now)
        self.observe(111)
        def send(token, chat, text, timeout):
            self.assertIn('apenas na simulação', text)
            self.assertIn('Nenhuma ordem alterada', text)
            return 200, dict(ok=True, result=dict(message_id=2, chat=dict(id=202), text=text))
        with patch.object(delivery, '_post', side_effect=send) as post:
            self.tracker.flush()
            self.tracker.flush()
            post.assert_called_once()

    def test_webhook_conflict_and_poll_error_fail_closed(self):
        with patch.object(delivery, '_telegram_api', return_value=(200, dict(ok=True, result=dict(url='https://existing.invalid')))):
            with self.assertRaises(ValueError):
                self.tracker.check_polling()
        with patch.object(delivery, '_telegram_api', return_value=(409, dict(ok=False))):
            with self.assertRaises(ValueError):
                self.tracker.poll(self.now)

    def test_poll_activation_and_durable_cursor(self):
        key = self.offer()
        def api(token, method, payload, timeout):
            if method == 'getUpdates':
                self.assertEqual(payload['allowed_updates'], ['callback_query'])
                return 200, dict(ok=True, result=[self.click(key)])
            return 200, dict(ok=True, result=True)
        with patch.object(delivery, '_telegram_api', side_effect=api):
            self.tracker.poll(self.now)
        self.assertEqual(self.state(key)['state'], 'ACTIVE')
        with self.db() as db:
            self.assertEqual(db.execute('SELECT offset FROM donkey_reference_control_v1').fetchone()[0], 2)

    def test_public_delivery_button_and_confirmed_message_binding(self):
        signal = dict(synthetic=False, source='BINGX_PUBLIC_SWAP', setup='DONKEY', symbol='TEST-USDT',
                      signal_id='reference-test', side='LONG', entry=100., stop=90., tp50=110.,
                      timeframe='4h', candle_closed_at_ms=self.now-1000, generated_at_ms=self.now,
                      invalidated=False)
        def send(token, chat, text, timeout, reply_markup=None):
            self.assertIsNotNone(reply_markup)
            self.button = reply_markup['inline_keyboard'][0][0]['callback_data']
            return 200, dict(ok=True, result=dict(message_id=19, chat=dict(id=202), text=text))
        with patch.object(delivery, '_post', side_effect=send):
            out = delivery.dispatch_public_signal('DONKEY', signal, values=fixture.VALUES,
                ledger_path=self.path, now_ms=self.now, expires_at_ms=self.now+900000,
                data_valid_until_ms=self.now+15000, validity_basis='Explicit test policy',
                network_authorized=True, public_delivery_authorized=True, donkey_tracking=True)
        self.assertEqual(out['status'], 'CONFIRMED')
        self.tracker.accept(self.click(self.button, message=dict(message_id=19, chat=dict(id=202))), self.now)
        self.assertEqual(self.state(self.button)['state'], 'ACTIVE')

    def test_supervisor_tracking_is_opt_in_and_reuses_collected_snapshot(self):
        import test_signal_only_service as service_fixture
        import threading
        service = service_fixture.service
        config = service_fixture.config()
        sources = dict(FALCON=fixture.harness.SOURCE, DONKEY=fixture.SOURCE)
        snap, _ = fixture.PublicPreviewTests().public_fixture('DONKEY')
        with patch.object(tracking, 'ReferenceTracker') as factory, \
             patch.object(service, 'collect_snapshot', return_value=snap) as collect, \
             patch.object(service, 'run_once', return_value=dict(status='BLOCKED', reason='NO_SIGNAL')) as run:
            out = service.run_service(config, sources, values=fixture.VALUES, ledger_path=self.path,
                                      stop_event=threading.Event(), service_authorized=True,
                                      public_data_authorized=True, public_delivery_authorized=True,
                                      max_cycles=1, donkey_operator_id=77)
        self.assertEqual(out['status'], 'STOPPED')
        collect.assert_called_once()
        factory.return_value.check_polling.assert_called_once()
        factory.return_value.poll.assert_called_once()
        factory.return_value.observe.assert_called_once()
        self.assertTrue(all(call.kwargs['donkey_tracking'] for call in run.call_args_list))


if __name__ == '__main__':
    unittest.main()
