"""Fourth incident recovery: synthetic SQLite/receipts, blocked network/worker."""
import contextlib
import copy
import io
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Installs import/network guards before loading repository modules.
import test_manual_ledger_read_only_audit as fixtures
import signal_only_runner as runner

manual, legacy, delivery = fixtures.manual, fixtures.legacy, fixtures.delivery
REVIEW = '20261002-070002'
NOW = manual.H4_MODERN_FIRST_LIVE_MS + 86400000
PRIOR = ('20260930-205047', '20260930-222218', '20261001-110546')


class FourthReviewedRecovery(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        a = fixtures.ReadOnlyAudit()
        a.setUp()
        try:
            def activate(bot, setups, symbol):
                # Distinct identities across symbols: exercise actual dedup,
                # never bypass it with a shared synthetic signal_id.
                a.send(bot, [fixtures.h.signal(setup, symbol=symbol,
                    suffix=f'cohort-{symbol}-{setup}') for setup in setups])
                a.click_update += 1
                a.enter_last(bot, update=a.click_update)
                with contextlib.closing(sqlite3.connect(a.path)) as db:
                    return db.execute("SELECT ref FROM manual_trade_v1 WHERE symbol=? AND state='ACTIVE'",
                                      (symbol,)).fetchone()[0]
            activate('DONKEY', ('DONKEY', 'DONKEY_ORIGINAL'), 'BTC-USDT')
            activate('DONKEY', ('DONKEY', 'EARLY_DONKEY'), 'ETH-USDT')
            sol = activate('FALCON', ('FALCON15', 'FALCON30'), 'SOL-USDT')
            ada = activate('FALCON', ('FALCON15', 'FALCON30'), 'ADA-USDT')
            for offset, symbol in enumerate(('BTC-USDT', 'ETH-USDT', 'SOL-USDT'), 10):
                at = fixtures.h.base.NOW+offset
                a.tracker.observe(dict(synthetic=False, connected=True, symbol=symbol,
                    observed_at_ms=at, quote=dict(price=102, at_ms=at)), at, 1000)
            for update, ref in ((5, sol), (6, ada)):
                a.tracker.accept('FALCON', a.callback('FALCON', 'mc:'+ref, update=update),
                                 fixtures.h.base.NOW+update+8)
            historic = activate('DONKEY', ('DONKEY',), 'XRP-USDT')
            for symbol in ('BTC-USDT', 'ETH-USDT'):
                a.tracker.observe_h4(fixtures.h.snapshot(symbol=symbol), fixtures.h.LATER,
                    fixtures.h.fixtures.SOURCE, fixtures.h.fixtures.CONFIG,
                    frame_max_age_ms=10000, quote_max_age_ms=5000)
            closed = manual.H4_LEGACY_LAST_POSSIBLE_MS-1
            a.sql("UPDATE manual_trade_v1 SET state='CLOSED', closed_ms=?, last_quote_ms=?, close_reason='STOP' WHERE ref=?",
                  (closed, closed, historic))
            with contextlib.closing(sqlite3.connect(a.path)) as db:
                route = db.execute('SELECT route FROM manual_trade_v1 WHERE ref=?', (historic,)).fetchone()[0]
            a.sql("INSERT INTO manual_trade_event_v1 VALUES (?, 'STOP', ?, 'synthetic legacy stop', 'CONFIRMED', ?)",
                  (historic, route, closed))
            a.sql('UPDATE manual_trade_clock_v1 SET clock=?', (closed,))
            a.sql("UPDATE manual_trade_event_v1 SET status='CONFIRMED'")
            for index in range(52):
                setups = ('DONKEY', 'DONKEY_ORIGINAL') if index < 4 else ('DONKEY',)
                a.send('DONKEY', [fixtures.h.signal(setup, symbol=f'WAIT{index}-USDT',
                    suffix=f'waiting-{index}-{setup}') for setup in setups])
            with contextlib.closing(sqlite3.connect(a.path)) as db, db:
                for index in range(152):
                    identity = format(10000+index, '064x')
                    db.execute("INSERT INTO delivery_v1 VALUES (?, ?, ?, 'CONFIRMED', ?, ?)",
                        (identity, f'synthetic-history-{index}', route, fixtures.h.base.NOW, 1000+index))
                    if index < 12:
                        legacy.offer(db, identity, route,
                            fixtures.h.signal('DONKEY', symbol=f'LEGACY{index}-USDT'),
                            fixtures.h.base.NOW+900000)
                ref = db.execute('SELECT ref FROM donkey_reference_v1 ORDER BY ref LIMIT 1').fetchone()[0]
                db.execute("UPDATE donkey_reference_v1 SET state='ACTIVE', active_ms=? WHERE ref=?",
                           (fixtures.h.base.NOW+1, ref))
                db.execute('INSERT INTO donkey_reference_control_v1 VALUES (1, ?, 77, 0, ?)',
                           (route, fixtures.h.base.NOW+1))
                for bot in ('FALCON', 'DONKEY'):
                    db.execute("INSERT INTO route_check_v1 VALUES (?, ?, 'CONFIRMED')",
                               (bot, a.tracker.routes[bot]['route']))
            with patch.object(runner.time, 'time_ns', return_value=NOW*1000000):
                report = runner.inspect_halted_ledger(a.path)
            assert report['review_complete'], report
            assert report['delivery'] == {'CONFIRMED': 217}, report
            assert report['references'] == {'ACTIVE': 1, 'WAITING': 11}, report
            assert report['manual_trades'] == {'ACTIVE': 2, 'CLOSED': 3, 'WAITING': 52}, report
            assert report['manual_participants'] == {'rows': 65}, report
            assert report['manual_h4'] == {'rows': 2, 'active_with_cursor': 2}, report
            assert report['manual_tp50'] == {'reached': 3}, report
            assert report['manual_notices'] == {'CONFIRMED': 4}, report
            assert report['manual_h4_integrity']['legacy_stop_without_h4_cursor'] == 1, report
            cls.ledger_bytes = Path(a.path).read_bytes()
        finally:
            a.doCleanups()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'synthetic-reviewed.sqlite'
        self.path.write_bytes(self.ledger_bytes)
        self.halted = Path(str(self.path)+'.halted')
        self.halted.write_bytes(runner.REVIEWED_HALT_BYTES)
        for review in PRIOR:
            runner.reviewed_halt_archive(self.path, review).write_bytes(runner.REVIEWED_HALT_BYTES)
        self.archive = runner.reviewed_halt_archive(self.path, REVIEW)

    def inspect(self):
        with patch.object(runner.time, 'time_ns', return_value=NOW*1000000):
            return runner.inspect_halted_ledger(self.path)

    def recover(self):
        before = self.path.read_bytes()
        with patch.object(runner.time, 'time_ns', return_value=NOW*1000000), \
             patch.object(manual, 'provision', side_effect=AssertionError('no provisioning')), \
             patch.object(manual, 'connect', side_effect=AssertionError('no writable DB')), \
             patch.object(legacy, 'provision', side_effect=AssertionError('no provisioning')), \
             patch.object(runner, 'run_service', side_effect=AssertionError('no worker')), \
             patch.object(delivery, '_post', side_effect=AssertionError('no network')), \
             patch.object(delivery, '_telegram_api', side_effect=AssertionError('no network')):
            result = runner.resume_reviewed_halt(self.path, REVIEW)
        self.assertEqual(self.path.read_bytes(), before)
        return result

    def assert_blocked(self):
        self.assertFalse(self.recover())
        self.assertEqual(self.halted.read_bytes(), runner.REVIEWED_HALT_BYTES)
        self.assertFalse(self.archive.exists())

    def test_fourth_chain_single_use_and_all_manual_state_bytes_preserved(self):
        self.assertEqual(runner.FOURTH_REVIEWED_HALT_ID, REVIEW)
        self.assertEqual(runner.REVIEWED_HALT_REVIEWS[REVIEW], PRIOR)
        before = self.inspect()
        self.assertTrue(runner.frame_expired_review_is_valid(before))
        self.assertTrue(self.recover())
        self.assertEqual(self.inspect(), before)
        self.assertFalse(self.halted.exists())
        for review in (*PRIOR, REVIEW):
            self.assertEqual(runner.reviewed_halt_archive(self.path, review).read_bytes(), runner.REVIEWED_HALT_BYTES)
        self.assertFalse(self.recover())
        self.halted.write_bytes(runner.REVIEWED_HALT_BYTES)
        self.assertFalse(self.recover())
        self.assertTrue(self.halted.exists())

    def test_missing_or_corrupt_each_prior_receipt_blocks_without_repair(self):
        for review in PRIOR:
            receipt = runner.reviewed_halt_archive(self.path, review)
            for changed in (None, b'CHANGED\n'):
                with self.subTest(review=review, changed=changed):
                    if changed is None:
                        receipt.unlink()
                    else:
                        receipt.write_bytes(changed)
                    self.assert_blocked()
                    if changed is not None:
                        self.assertEqual(receipt.read_bytes(), changed)
                    receipt.write_bytes(runner.REVIEWED_HALT_BYTES)

    def test_old_ids_and_future_halt_refuse_without_credentials_or_worker(self):
        for old_review in PRIOR:
            with self.subTest(review=old_review), \
                 patch.object(runner.os.environ, 'get', side_effect=AssertionError('no credentials')), \
                 patch.object(runner, 'run_service') as run:
                result = runner.execute({}, {}, self.path, authorized=True, reviewed_halt=old_review)
            self.assertEqual(result['reason'], 'REVIEWED_HALT_RECEIPT_PRESENT_REVIEW_REQUIRED')
            run.assert_not_called()
        self.assertTrue(self.recover())
        self.halted.write_bytes(runner.REVIEWED_HALT_BYTES)
        for old_review in (*PRIOR, REVIEW):
            with self.subTest(future_review=old_review), \
                 patch.object(runner.os.environ, 'get', side_effect=AssertionError('no credentials')), \
                 patch.object(runner, 'run_service') as run:
                result = runner.execute({}, {}, self.path, authorized=True, reviewed_halt=old_review)
            self.assertEqual(result['reason'], 'REVIEWED_HALT_RECEIPT_PRESENT_REVIEW_REQUIRED')
            run.assert_not_called()

    def test_crash_after_new_receipt_stays_fail_closed_and_consumes_id(self):
        with patch.object(Path, 'unlink', side_effect=OSError('synthetic crash')):
            self.assertFalse(self.recover())
        self.assertEqual(self.archive.read_bytes(), runner.REVIEWED_HALT_BYTES)
        self.assertTrue(self.halted.exists())
        self.assertFalse(self.recover())

    def test_incomplete_or_inconsistent_review_blocks_even_if_boolean_is_true(self):
        valid = self.inspect()
        mutations = [('review_complete', False), ('clock_ahead', True),
            ('live_allowed', True), ('delivery_allowed', True),
            ('reason', 'OTHER'), ('status', 'OTHER')]
        for field, value in mutations:
            with self.subTest(field=field):
                report = copy.deepcopy(valid)
                report[field] = value
                with patch.object(runner, 'inspect_halted_ledger', return_value=report):
                    self.assert_blocked()
        for section, fields in (('manual_integrity', valid['manual_integrity']),
                                ('manual_h4_integrity', valid['manual_h4_integrity'])):
            for field in fields:
                if field == 'legacy_stop_without_h4_cursor':
                    continue
                with self.subTest(section=section, field=field):
                    report = copy.deepcopy(valid)
                    report[section][field] = False if field == 'schema_ok' else (True if field == 'clock_ahead' else 1)
                    with patch.object(runner, 'inspect_halted_ledger', return_value=report):
                        self.assert_blocked()
                with self.subTest(missing_section=section, missing_field=field):
                    report = copy.deepcopy(valid)
                    del report[section][field]
                    with patch.object(runner, 'inspect_halted_ledger', return_value=report):
                        self.assert_blocked()

    def test_unknown_bad_count_or_missing_summary_blocks(self):
        valid = self.inspect()
        for section in ('delivery', 'routes', 'notices', 'manual_notices', 'references', 'manual_trades'):
            with self.subTest(unknown=section):
                report = copy.deepcopy(valid)
                report[section]['UNKNOWN'] = 1
                with patch.object(runner, 'inspect_halted_ledger', return_value=report):
                    self.assert_blocked()
        for section, field, value in (
            ('manual_h4_integrity', 'legacy_stop_without_h4_cursor', -1),
            ('manual_h4_integrity', 'legacy_stop_without_h4_cursor', 2),
            ('manual_tp50', 'reached', 99), ('manual_h4', 'active_with_cursor', 3),
            ('manual_protection', 'positive_stops', 56), ('manual_participants', 'rows', 1),
            ('routes', 'CONFIRMED', 2.0), ('manual_closes', 'STOP', 0)):
            with self.subTest(section=section, field=field, value=value):
                report = copy.deepcopy(valid)
                report[section][field] = value
                with patch.object(runner, 'inspect_halted_ledger', return_value=report):
                    self.assert_blocked()
        for section in ('manual_h4_integrity', 'manual_participants', 'manual_h4', 'manual_tp50', 'manual_protection'):
            with self.subTest(missing=section):
                report = copy.deepcopy(valid)
                del report[section]
                with patch.object(runner, 'inspect_halted_ledger', return_value=report):
                    self.assert_blocked()

    def test_counts_are_not_frozen_to_the_operator_snapshot(self):
        # Add a valid WAITING offer through the real reservation/dedup path;
        # only the transport boundary is fake.
        def confirmed(token, chat, text, timeout, reply_markup=None):
            return 200, {'ok': True, 'result': {'message_id': 10000,
                'chat': {'id': int(chat)}, 'text': text}}
        with patch.object(delivery, '_post', side_effect=confirmed):
            delivery.dispatch_public_candidates('DONKEY', [fixtures.h.base.candidate(
                fixtures.h.signal('DONKEY', symbol='EXTRAWAIT-USDT', suffix='extra-wait'))],
                values=fixtures.h.base.VALUES, ledger_path=self.path,
                network_authorized=True, public_delivery_authorized=True, manual_tracking=True)
        self.assertEqual(self.inspect()['delivery'], {'CONFIRMED': 218})
        self.assertEqual(self.inspect()['manual_trades']['WAITING'], 53)
        self.assertEqual(self.inspect()['manual_participants'], {'rows': 66})
        self.assertTrue(self.recover())

    def test_real_read_only_audit_rejects_missing_manual_schema(self):
        with contextlib.closing(sqlite3.connect(self.path)) as db, db:
            db.execute('DROP TABLE manual_trade_h4_v2')
        self.assert_blocked()

    def test_actual_manual_corruption_and_indeterminate_stop_block(self):
        original = self.path.read_bytes()
        for statement, params in (
            ('UPDATE manual_trade_v1 SET stop=0 WHERE state=\'ACTIVE\'', ()),
            ('UPDATE manual_trade_h4_v2 SET closed_at_ms=closed_at_ms+1', ()),
            ("UPDATE manual_trade_v1 SET closed_ms=?, last_quote_ms=? WHERE close_reason='STOP'",
             (manual.H4_LEGACY_LAST_POSSIBLE_MS, manual.H4_LEGACY_LAST_POSSIBLE_MS))):
            with self.subTest(statement=statement):
                self.path.write_bytes(original)
                with contextlib.closing(sqlite3.connect(self.path)) as db, db:
                    db.execute(statement, params)
                    if params:
                        db.execute("UPDATE manual_trade_event_v1 SET created_ms=? WHERE kind='STOP'", (params[0],))
                        db.execute('UPDATE manual_trade_clock_v1 SET clock=?', (params[0],))
                self.assert_blocked()

    def test_cli_new_id_requires_run_and_forwards_without_starting_worker(self):
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            runner.main(['--check-config', '--config', 'unused.json', '--reviewed-halt', REVIEW])
        argv = ['--run', '--config', 'unused.json', '--ledger', 'unused.sqlite',
            '--authorize-service', '--authorize-public-data', '--authorize-telegram',
            '--donkey-operator-id', '77', '--authorize-donkey-polling', '--reviewed-halt', REVIEW]
        with patch.object(runner, 'load_inputs', return_value=({}, {})), \
             patch.object(runner, 'execute', return_value={'status': 'STOPPED'}) as execute, \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(runner.main(argv), 0)
        self.assertEqual(execute.call_args.kwargs['reviewed_halt'], REVIEW)
        self.assertFalse(json.loads(output.getvalue())['live_allowed'])

    def test_temporary_recovery_then_normal_startup_without_id_preserves_db(self):
        before = self.path.read_bytes()
        with patch.object(runner.time, 'time_ns', return_value=NOW*1000000), \
             patch.object(runner.os.environ, 'get', return_value='SYNTHETIC'), \
             patch.object(runner, 'verify_routes_once', return_value={'status': 'ROUTES_CONFIRMED'}) as verify, \
             patch.object(runner, 'run_service', return_value={'status': 'STOPPED'}) as run, \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(runner.execute({}, {}, self.path, authorized=True, verify_telegram=True,
                donkey_operator_id=77, reviewed_halt=REVIEW)['status'], 'STOPPED')
            self.assertEqual(runner.execute({}, {}, self.path, authorized=True, verify_telegram=True,
                donkey_operator_id=77)['status'], 'STOPPED')
        self.assertEqual(run.call_count, 2)
        self.assertEqual(verify.call_count, 2)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse(self.halted.exists())
        self.assertEqual(self.archive.read_bytes(), runner.REVIEWED_HALT_BYTES)

    def test_new_receipt_exists_or_wrong_latch_refuses(self):
        self.archive.write_bytes(b'PARTIAL')
        self.assertFalse(self.recover())
        self.assertEqual(self.archive.read_bytes(), b'PARTIAL')
        self.archive.unlink()
        self.halted.write_bytes(b'OTHER_FAILURE\n')
        self.assertFalse(self.recover())
        self.assertFalse(self.archive.exists())


if __name__ == '__main__':
    unittest.main()
