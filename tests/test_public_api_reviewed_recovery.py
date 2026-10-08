"""Fifth recovery: synthetic SQLite and receipts only; guards precede imports."""
import contextlib
import copy
import io
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import test_frame_expired_reviewed_recovery as base

runner, manual, legacy, delivery = base.runner, base.manual, base.legacy, base.delivery
REVIEW = '20261004-210018'
PRIOR = ('20260930-205047', '20260930-222218', '20261001-110546', '20261002-070002')


class PublicApiReviewedRecovery(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Reuse the nonempty cohort with manual trades, H4, events, participants,
        # legacy references, delivery history and dedup; do not duplicate writers.
        base.FourthReviewedRecovery.setUpClass()
        cls.ledger_bytes = base.FourthReviewedRecovery.ledger_bytes

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'signals-delivery.sqlite'
        self.path.write_bytes(self.ledger_bytes)
        self.halted = Path(str(self.path) + '.halted')
        self.halted.write_bytes(runner.REVIEWED_HALT_BYTES)
        for review in PRIOR:
            runner.reviewed_halt_archive(self.path, review).write_bytes(runner.REVIEWED_HALT_BYTES)
        self.archive = runner.reviewed_halt_archive(self.path, REVIEW)
        self.now = base.NOW

    def inspect(self):
        with patch.object(runner.time, 'time_ns', return_value=self.now * 1000000):
            return runner.inspect_halted_ledger(self.path)

    def table_snapshot(self):
        with contextlib.closing(sqlite3.connect(self.path.as_uri() + '?mode=ro', uri=True)) as db:
            db.execute('PRAGMA query_only=ON')
            tables = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            return {table: db.execute('SELECT * FROM "' + table + '" ORDER BY rowid').fetchall()
                    for table in tables}

    def recover(self):
        before = self.path.read_bytes()
        with patch.object(runner.time, 'time_ns', return_value=self.now * 1000000), \
             patch.object(manual, 'provision', side_effect=AssertionError('no provision')), \
             patch.object(manual, 'connect', side_effect=AssertionError('no writable connect')), \
             patch.object(legacy, 'provision', side_effect=AssertionError('no provision')), \
             patch.object(runner.os.environ, 'get', side_effect=AssertionError('no credentials')), \
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

    def test_valid_chain_receipt_single_use_and_all_tables_preserved(self):
        self.assertEqual(runner.FIFTH_REVIEWED_HALT_ID, REVIEW)
        self.assertEqual(runner.REVIEWED_HALT_REVIEWS[REVIEW], PRIOR)
        self.assertEqual(self.archive.name, 'signals-delivery.sqlite.halted.reviewed-' + REVIEW)
        audit, tables = self.inspect(), self.table_snapshot()
        self.assertTrue(audit['review_complete'])
        self.assertFalse(audit['live_allowed'])
        self.assertFalse(audit['delivery_allowed'])
        for table in manual.MANUAL_TRACKING_COLUMNS:
            self.assertTrue(tables[table], table)
        self.assertTrue(self.recover())
        self.assertFalse(self.halted.exists())
        self.assertEqual(self.archive.read_bytes(), runner.REVIEWED_HALT_BYTES)
        for review in PRIOR:
            self.assertEqual(runner.reviewed_halt_archive(self.path, review).read_bytes(), runner.REVIEWED_HALT_BYTES)
        self.assertEqual(self.table_snapshot(), tables)
        self.assertEqual(self.inspect(), audit)
        self.assertFalse(self.recover())
        self.halted.write_bytes(runner.REVIEWED_HALT_BYTES)
        self.assertFalse(self.recover())
        self.assertEqual(self.halted.read_bytes(), runner.REVIEWED_HALT_BYTES)

    def test_each_missing_corrupt_or_nonfile_prior_receipt_blocks(self):
        for review in PRIOR:
            receipt = runner.reviewed_halt_archive(self.path, review)
            for value in (None, b'CORRUPT', b''):
                with self.subTest(review=review, value=value):
                    receipt.unlink()
                    if value is not None:
                        receipt.write_bytes(value)
                    self.assert_blocked()
                    if value is not None:
                        self.assertEqual(receipt.read_bytes(), value)
                    else:
                        self.assertFalse(receipt.exists())
                    receipt.write_bytes(runner.REVIEWED_HALT_BYTES)
            receipt.unlink()
            receipt.mkdir()
            self.assert_blocked()
            receipt.rmdir()
            receipt.write_bytes(runner.REVIEWED_HALT_BYTES)

    def test_own_receipt_canonical_or_corrupt_blocks_without_overwrite(self):
        for value in (runner.REVIEWED_HALT_BYTES, b'PARTIAL', b''):
            with self.subTest(value=value):
                self.archive.write_bytes(value)
                self.assertFalse(self.recover())
                self.assertEqual(self.archive.read_bytes(), value)
                self.assertEqual(self.halted.read_bytes(), runner.REVIEWED_HALT_BYTES)
                self.archive.unlink()
        self.archive.mkdir()
        self.assertFalse(self.recover())
        self.assertTrue(self.archive.is_dir())

    def test_latch_absent_or_mismatch_blocks(self):
        self.halted.unlink()
        self.assertFalse(self.recover())
        self.assertFalse(self.archive.exists())
        for value in (b'', b'OTHER_FAILURE\n', b'MANUAL_REVIEW_REQUIRED\r\n'):
            with self.subTest(value=value):
                self.halted.write_bytes(value)
                self.assertFalse(self.recover())
                self.assertEqual(self.halted.read_bytes(), value)
                self.assertFalse(self.archive.exists())

    def test_audit_exception_or_incomplete_or_unsafe_report_blocks(self):
        with patch.object(runner, 'inspect_halted_ledger', side_effect=RuntimeError('synthetic audit failure')):
            self.assert_blocked()
        valid = self.inspect()
        for key, value in (('review_complete', False), ('clock_ahead', True),
                           ('live_allowed', True), ('delivery_allowed', True),
                           ('reason', 'OTHER'), ('status', 'OTHER')):
            with self.subTest(key=key):
                report = dict(valid, **{key: value})
                with patch.object(runner, 'inspect_halted_ledger', return_value=report):
                    self.assert_blocked()
        for key in valid['manual_integrity']:
            with self.subTest(manual_key=key):
                report = copy.deepcopy(valid)
                report['manual_integrity'][key] = False if key == 'schema_ok' else True if key == 'clock_ahead' else 1
                with patch.object(runner, 'inspect_halted_ledger', return_value=report):
                    self.assert_blocked()
        for section in ('manual_integrity', 'manual_h4_integrity', 'manual_trades', 'routes'):
            report = copy.deepcopy(valid)
            del report[section]
            with patch.object(runner, 'inspect_halted_ledger', return_value=report):
                self.assert_blocked()

    def test_actual_manual_corruption_is_rejected_without_repair(self):
        with contextlib.closing(sqlite3.connect(self.path)) as db, db:
            db.execute("UPDATE manual_trade_v1 SET stop=0 WHERE state='ACTIVE'")
        self.assertFalse(self.inspect()['review_complete'])
        self.assert_blocked()

    def test_partial_archive_failure_consumes_id_and_keeps_latch(self):
        with patch.object(Path, 'unlink', side_effect=OSError('synthetic crash')):
            self.assertFalse(self.recover())
        self.assertEqual(self.archive.read_bytes(), runner.REVIEWED_HALT_BYTES)
        self.assertEqual(self.halted.read_bytes(), runner.REVIEWED_HALT_BYTES)
        self.assertFalse(self.recover())

    def test_real_values_equivalent_audit_and_recovery(self):
        origin_clock, closed = 1791136056751, 1791151116911
        with contextlib.closing(sqlite3.connect(self.path)) as db, db:
            route = db.execute("SELECT route FROM manual_trade_v1 WHERE family='FALCON' AND close_reason='MANUAL_CLOSE' LIMIT 1").fetchone()[0]
            db.execute("UPDATE manual_trade_v1 SET closed_ms=? WHERE family='FALCON' AND close_reason='MANUAL_CLOSE'", (closed,))
            db.execute('UPDATE manual_trade_control_v1 SET clock=? WHERE route=?', (origin_clock, route))
            db.execute('UPDATE manual_trade_control_v1 SET clock=? WHERE route!=?', (closed, route))
        self.now = closed + 1000
        audit = self.inspect()
        self.assertTrue(audit['review_complete'], audit)
        self.assertEqual(audit['manual_integrity']['invalid_timestamps'], 0)
        self.assertEqual(audit['manual_timestamp_integrity']['invalid_trade_close_control_relation'], 0)
        self.assertTrue(self.recover())

    def test_recovery_and_normal_startup_are_signal_only_with_fake_worker(self):
        before = self.path.read_bytes()
        with patch.object(runner.time, 'time_ns', return_value=self.now * 1000000), \
             patch.object(runner.os.environ, 'get', return_value='SYNTHETIC'), \
             patch.object(runner, 'verify_routes_once', return_value={'status': 'ROUTES_CONFIRMED'}) as verify, \
             patch.object(runner, 'run_service', return_value={'status': 'STOPPED', 'live_allowed': False}) as run, \
             contextlib.redirect_stdout(io.StringIO()) as output:
            resumed = runner.execute({}, {}, self.path, authorized=True, verify_telegram=True,
                                     donkey_operator_id=77, reviewed_halt=REVIEW)
            normal = runner.execute({}, {}, self.path, authorized=True, verify_telegram=True, donkey_operator_id=77)
        self.assertFalse(resumed['live_allowed'])
        self.assertFalse(normal['live_allowed'])
        self.assertEqual(run.call_count, 2)
        self.assertEqual(verify.call_count, 2)
        archived = json.loads(output.getvalue().splitlines()[0])
        self.assertEqual(archived, dict(status='REVIEWED_HALT_ARCHIVED', live_allowed=False))
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.archive.read_bytes(), runner.REVIEWED_HALT_BYTES)

    def test_recurrence_remains_failed_and_new_latch_cannot_reuse_id(self):
        failed = dict(status='FAILED', reason='PUBLIC_API_REJECTED_NO_RETRY', stage='public_collection', live_allowed=False)
        before = self.path.read_bytes()
        with patch.object(runner.time, 'time_ns', return_value=self.now * 1000000), \
             patch.object(runner.os.environ, 'get', return_value='SYNTHETIC'), \
             patch.object(runner, 'run_service', return_value=failed), \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(runner.execute({}, {}, self.path, authorized=True, reviewed_halt=REVIEW), failed)
        latch = self.halted.read_bytes()
        with patch.object(runner.os.environ, 'get', side_effect=AssertionError('no credentials')), \
             patch.object(runner, 'run_service', side_effect=AssertionError('no worker')):
            blocked = runner.execute({}, {}, self.path, authorized=True, reviewed_halt=REVIEW)
        self.assertEqual(blocked['reason'], 'REVIEWED_HALT_RECEIPT_PRESENT_REVIEW_REQUIRED')
        self.assertEqual(self.halted.read_bytes(), latch)
        self.assertEqual(self.path.read_bytes(), before)

    def test_execute_refuses_new_id_without_latch_or_after_consumption(self):
        self.halted.unlink()
        with patch.object(runner.os.environ, 'get', side_effect=AssertionError('no credentials')), \
             patch.object(runner, 'run_service', side_effect=AssertionError('no worker')):
            blocked = runner.execute({}, {}, self.path, authorized=True, reviewed_halt=REVIEW)
        self.assertEqual(blocked['reason'], 'REVIEWED_RESUME_REFUSED')
        self.assertFalse(self.archive.exists())
        self.halted.write_bytes(runner.REVIEWED_HALT_BYTES)
        self.assertTrue(self.recover())
        with patch.object(runner.os.environ, 'get', side_effect=AssertionError('no credentials')), \
             patch.object(runner, 'run_service', side_effect=AssertionError('no worker')):
            blocked = runner.execute({}, {}, self.path, authorized=True, reviewed_halt=REVIEW)
        self.assertEqual(blocked['reason'], 'REVIEWED_RESUME_REFUSED')
        self.assertEqual(self.archive.read_bytes(), runner.REVIEWED_HALT_BYTES)

    def test_cli_accepts_new_id_only_for_run_and_keeps_live_false(self):
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


if __name__ == '__main__':
    unittest.main()
