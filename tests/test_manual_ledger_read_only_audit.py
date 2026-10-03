"""Synthetic SQLite only; install network/import guards before project imports."""
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing, redirect_stdout
import io
from pathlib import Path
from unittest.mock import patch
import test_donkey_strategic_stop_v2 as h
import donkey_signal_tracking as legacy
import signal_only_runner as runner

manual, delivery = h.tracking, h.delivery
NOW = h.LATER + 1000000


class ReadOnlyAudit(h.base.Harness):
    def setUp(self):
        super().setUp()
        legacy.provision(self.path)
        self.click_update = 0

    def sql(self, statement, params=()):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute(statement, params)

    def activate(self, bot='DONKEY', setups=('DONKEY', 'DONKEY_ORIGINAL'), side='LONG', symbol='BTC-USDT'):
        self.send(bot, [h.signal(s, side=side, symbol=symbol, suffix=s) for s in setups])
        self.click_update += 1
        self.enter_last(bot, update=self.click_update)
        return self.active()[-1]['ref']

    def inspect(self, path=None):
        path = Path(path or self.path)
        before = path.read_bytes()
        with patch.object(runner.time, 'time_ns', return_value=NOW * 1000000), \
             patch.object(manual, 'provision', side_effect=AssertionError('no provisioning')), \
             patch.object(manual, 'connect', side_effect=AssertionError('no writable connect')), \
             patch.object(legacy, 'provision', side_effect=AssertionError('no provisioning')), \
             patch.object(runner, 'run_service', side_effect=AssertionError('no worker')), \
             patch.object(runner, 'resume_reviewed_halt', side_effect=AssertionError('no recovery')), \
             patch.object(delivery, '_post', side_effect=AssertionError('no network')), \
             patch.object(delivery, '_telegram_api', side_effect=AssertionError('no network')):
            out = runner.inspect_halted_ledger(path)
        self.assertEqual(path.read_bytes(), before)
        self.assertIs(out['live_allowed'], False)
        self.assertIs(out['delivery_allowed'], False)
        return out

    def reject(self, reason=None):
        out = self.inspect()
        self.assertFalse(out['review_complete'], out)
        if reason:
            self.assertEqual(out['reason'], reason, out)
        return out

    def test_empty_complete_ledger_and_read_only_authorizer(self):
        real_connect = sqlite3.connect
        statements = []
        def readonly(*args, **kwargs):
            self.assertIn('?mode=ro', args[0])
            db = real_connect(*args, **kwargs)
            forbidden = {sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE,
                         sqlite3.SQLITE_CREATE_TABLE, sqlite3.SQLITE_DROP_TABLE,
                         sqlite3.SQLITE_ALTER_TABLE, sqlite3.SQLITE_CREATE_INDEX}
            def authorizer(action, *_):
                if action in forbidden:
                    raise AssertionError('write attempted')
                return sqlite3.SQLITE_OK
            db.set_authorizer(authorizer)
            db.set_trace_callback(statements.append)
            return db
        with patch.object(runner.sqlite3, 'connect', side_effect=readonly):
            out = self.inspect()
        self.assertTrue(out['review_complete'], out)
        self.assertTrue(out['manual_integrity']['schema_ok'])
        self.assertTrue(all(s.lstrip().upper().startswith(('SELECT', 'PRAGMA', 'BEGIN')) for s in statements))

    def test_each_required_manual_table_missing_and_column_missing_or_extra(self):
        original = Path(self.path).read_bytes()
        for table in manual.MANUAL_TRACKING_COLUMNS:
            with self.subTest(table=table):
                clone = Path(self.temp.name) / 'clone.sqlite'
                clone.write_bytes(original)
                with closing(sqlite3.connect(clone)) as db, db:
                    db.execute(f'DROP TABLE {table}')
                out = self.inspect(clone)
                self.assertFalse(out['review_complete'])
                self.assertEqual(out['reason'], 'MANUAL_TRACKING_SCHEMA_REVIEW_REQUIRED')
        for statement in ('ALTER TABLE manual_trade_v1 DROP COLUMN stop',
                          'ALTER TABLE manual_trade_v1 ADD COLUMN unexpected TEXT'):
            with self.subTest(statement=statement):
                clone = Path(self.temp.name) / 'columns.sqlite'
                clone.write_bytes(original)
                with closing(sqlite3.connect(clone)) as db, db:
                    db.execute(statement)
                out = self.inspect(clone)
                self.assertFalse(out['review_complete'])
                self.assertEqual(out['reason'], 'MANUAL_TRACKING_SCHEMA_REVIEW_REQUIRED')

    def test_active_consolidated_donkey_preserved(self):
        self.activate()
        out = self.inspect()
        self.assertTrue(out['review_complete'], out)
        self.assertEqual(out['manual_trades'], {'ACTIVE': 1})
        self.assertEqual(out['manual_participants'], {'rows': 2})
        self.assertEqual(len(self.active()), 1)

    def test_waiting_and_rejected_delivery_offer_are_valid(self):
        self.send('DONKEY', [h.signal('EARLY_DONKEY')])
        self.sql("UPDATE delivery_v1 SET status='REJECTED', message_id=NULL")
        out = self.inspect()
        self.assertTrue(out['review_complete'], out)
        self.assertEqual(out['manual_trades'], {'WAITING': 1})

    def test_falcon_manual_stop_can_cross_entry_after_operator_update(self):
        ref = self.activate(bot='FALCON', setups=('FALCON15', 'FALCON30'))
        self.sql('UPDATE manual_trade_v1 SET stop=101 WHERE ref=?', (ref,))
        self.assertTrue(self.inspect()['review_complete'])

    def test_h4_cursor_real_writer_and_stop_are_valid(self):
        self.activate()
        self.tracker.observe_h4(h.snapshot(closed_price=90), h.LATER, h.fixtures.SOURCE,
            h.fixtures.CONFIG, frame_max_age_ms=10000, quote_max_age_ms=5000)
        out = self.inspect()
        self.assertTrue(out['review_complete'], out)
        self.assertEqual(out['manual_closes'], {'STOP': 1})
        self.assertEqual(out['manual_notices'], {'PENDING': 1})
        self.assertEqual(out['manual_h4']['rows'], 1)

    def test_tp50_real_writer_valid_even_if_sampled_quote_precedes_tp_timestamp(self):
        self.activate()
        self.tracker.observe(dict(synthetic=False, connected=True, symbol='BTC-USDT',
            observed_at_ms=h.base.NOW+9, quote=dict(price=102, at_ms=h.base.NOW+9)),
            h.base.NOW+10, 1000)
        out = self.inspect()
        self.assertTrue(out['review_complete'], out)
        self.assertEqual(out['manual_tp50'], {'reached': 1})

    def test_manual_close_and_expired_offer_from_real_callbacks_valid(self):
        ref = self.activate()
        self.tracker.accept('DONKEY', self.callback('DONKEY', 'mc:'+ref, update=2), h.base.NOW+2)
        self.assertTrue(self.inspect()['review_complete'])
        self.send('DONKEY', [h.signal('EARLY_DONKEY', suffix='expired')])
        self.tracker.accept('DONKEY', self.callback('DONKEY', self.sent[-1]['markup']['inline_keyboard'][0][0]['callback_data'],
            update=3), h.base.NOW+900000)
        out = self.inspect()
        self.assertTrue(out['review_complete'], out)
        self.assertEqual(out['manual_closes'], {'MANUAL_CLOSE': 1, 'EXPIRED': 1})

    def test_orphan_participant(self):
        self.sql("INSERT INTO manual_trade_candidate_v1 VALUES ('orphan', 'unknown', 'DONKEY')")
        out = self.reject('MANUAL_TRACKING_INTEGRITY_REVIEW_REQUIRED')
        self.assertEqual(out['manual_integrity']['orphan_participants'], 1)

    def test_orphan_h4(self):
        self.sql("INSERT INTO manual_trade_h4_v2 VALUES ('orphan', ?)", (h.CLOSED,))
        self.assertEqual(self.reject()['manual_integrity']['orphan_h4'], 1)

    def test_orphan_event_and_pending_input(self):
        self.sql("INSERT INTO manual_trade_event_v1 VALUES ('orphan','TP50','private-route','private-body','PENDING',?)", (h.base.NOW,))
        self.sql("UPDATE manual_trade_control_v1 SET pending_ref='orphan'")
        out = self.reject('MANUAL_TRACKING_INTEGRITY_REVIEW_REQUIRED')
        self.assertEqual(out['manual_integrity']['orphan_events'], 1)
        self.assertEqual(out['manual_integrity']['orphan_pending_inputs'], 2)

    def test_invalid_state_sanitized(self):
        self.activate()
        self.sql("UPDATE manual_trade_v1 SET state='private-sentinel'")
        out = self.reject('MANUAL_TRACKING_STATE_REVIEW_REQUIRED')
        self.assertNotIn('private-sentinel', json.dumps(out))

    def test_close_reason_incompatible(self):
        self.activate()
        self.sql("UPDATE manual_trade_v1 SET close_reason='MANUAL_CLOSE'")
        self.assertGreater(self.reject()['manual_integrity']['invalid_close'], 0)

    def test_tp50_without_matching_event(self):
        self.activate()
        self.sql('UPDATE manual_trade_v1 SET tp_ms=?, last_quote_ms=?', (h.base.NOW+2, h.base.NOW+2))
        self.sql('UPDATE manual_trade_clock_v1 SET clock=?', (h.base.NOW+2,))
        self.assertEqual(self.reject()['manual_integrity']['invalid_tp50'], 1)

    def test_future_clocks_and_observation_timestamp(self):
        original = Path(self.path).read_bytes()
        for table, column in (('manual_trade_clock_v1','clock'), ('manual_trade_control_v1','clock')):
            with self.subTest(table=table):
                Path(self.path).write_bytes(original)
                self.sql(f'UPDATE {table} SET {column}=?', (NOW+1,))
                out = self.reject('MANUAL_TRACKING_CLOCK_REVIEW_REQUIRED')
                self.assertTrue(out['clock_ahead'])

    def test_invalid_participants_and_active_conflict(self):
        self.send('DONKEY', [h.signal('DONKEY'), h.signal('DONKEY_ORIGINAL')])
        self.send('DONKEY', [h.signal('DONKEY_ORIGINAL', suffix='other', candle=h.base.NOW)])
        self.sql("UPDATE manual_trade_v1 SET state='ACTIVE', active_ms=?", (h.base.NOW+1,))
        self.sql('UPDATE manual_trade_control_v1 SET clock=?', (h.base.NOW+1,))
        self.assertGreater(self.reject()['manual_integrity']['incompatible_active'], 0)

    def test_opposite_side_and_different_participants_remain_valid(self):
        self.activate(setups=('DONKEY',))
        self.activate(setups=('EARLY_DONKEY',))
        out = self.inspect()
        self.assertTrue(out['review_complete'], out)
        self.assertEqual(out['manual_trades']['ACTIVE'], 2)

    def test_h4_before_activation_or_falcon_h4_is_invalid(self):
        ref = self.activate(bot='FALCON', setups=('FALCON15',))
        self.sql('INSERT INTO manual_trade_h4_v2 VALUES (?,?)', (ref, h.CLOSED))
        self.assertGreater(self.reject()['manual_integrity']['invalid_h4'], 0)

    def test_donkey_h4_grid_and_future_cursor(self):
        ref = self.activate()
        self.sql('UPDATE manual_trade_clock_v1 SET clock=?', (NOW,))
        self.sql('INSERT INTO manual_trade_h4_v2 VALUES (?,?)', (ref, h.CLOSED+1))
        self.assertEqual(self.reject()['manual_integrity']['invalid_h4'], 1)
        self.sql('UPDATE manual_trade_h4_v2 SET closed_at_ms=?', (NOW+14400000,))
        self.assertTrue(self.reject()['clock_ahead'])

    def test_wrong_participant_setup_group_and_delivery_binding(self):
        self.activate()
        original = Path(self.path).read_bytes()
        statements = ("UPDATE manual_trade_candidate_v1 SET setup='FALCON15'",
                      "UPDATE manual_trade_v1 SET setups='[[\"private-value\"]]'",
                      "UPDATE manual_trade_v1 SET group_identity='invalid'",
                      "UPDATE delivery_v1 SET route='wrong-route'",
                      "DELETE FROM delivery_v1",
                      "UPDATE delivery_v1 SET message_id=0")
        for sql in statements:
            with self.subTest(sql=sql):
                Path(self.path).write_bytes(original)
                self.sql(sql)
                out = self.reject('MANUAL_TRACKING_INTEGRITY_REVIEW_REQUIRED')
                self.assertGreater(out['manual_integrity']['invalid_participants'], 0)

    def test_pending_input_active_same_route_valid_but_other_route_or_closed_requires_review(self):
        ref = self.activate()
        self.sql('UPDATE manual_trade_control_v1 SET pending_ref=? WHERE route=(SELECT route FROM manual_trade_v1 WHERE ref=?)', (ref, ref))
        out = self.inspect()
        self.assertTrue(out['review_complete'], out)
        self.assertEqual(out['manual_pending_inputs'], {'count': 1})
        self.sql('UPDATE manual_trade_control_v1 SET pending_ref=?', (ref,))
        self.assertGreater(self.reject()['manual_integrity']['invalid_controls'], 0)

    def test_opposite_same_participant_is_permitted_by_activation_contract(self):
        self.send('DONKEY', [h.signal('DONKEY', side='LONG', suffix='long')])
        self.send('DONKEY', [h.signal('DONKEY', side='SHORT', suffix='short', candle=h.base.NOW)])
        self.sql("UPDATE manual_trade_v1 SET state='ACTIVE', active_ms=?", (h.base.NOW+1,))
        self.sql('UPDATE manual_trade_control_v1 SET clock=?', (h.base.NOW+1,))
        out = self.inspect()
        self.assertTrue(out['review_complete'], out)
        self.assertEqual(out['manual_trades']['ACTIVE'], 2)

    def test_future_trade_timestamp_and_missing_clock_row(self):
        self.activate()
        self.sql('UPDATE manual_trade_v1 SET created_ms=?', (NOW+1,))
        self.reject('MANUAL_TRACKING_CLOCK_REVIEW_REQUIRED')
        self.sql('DELETE FROM manual_trade_clock_v1')
        self.reject('MANUAL_TRACKING_CLOCK_REVIEW_REQUIRED')

    def test_stop_protection_must_be_positive_finite(self):
        self.activate()
        self.sql('UPDATE manual_trade_v1 SET stop=0')
        self.assertEqual(self.reject()['manual_integrity']['invalid_prices'], 1)

    def test_unknown_notice_is_ambiguous(self):
        ref = self.activate()
        self.sql("INSERT INTO manual_trade_event_v1 VALUES (?, 'TP50', 'private-route', 'private-body', 'UNKNOWN', ?)", (ref, h.base.NOW+2))
        out = self.reject('MANUAL_TRACKING_STATE_REVIEW_REQUIRED')
        self.assertEqual(out['manual_integrity']['ambiguous_notices'], 1)
        self.assertNotIn('private-', json.dumps(out))

    def test_legacy_unknown_and_clock_future_also_prevent_complete(self):
        self.sql("INSERT INTO delivery_v1 VALUES ('private-id','private-candle','private-route','UNKNOWN',1,NULL)")
        self.reject('LEDGER_STATE_REVIEW_REQUIRED')
        self.sql('INSERT INTO delivery_clock_v1 VALUES (1,?)', (NOW+1,))
        self.reject('LEDGER_CLOCK_REVIEW_REQUIRED')

    def test_quick_check_failure(self):
        real_connect = sqlite3.connect
        class Connection:
            def __init__(self, db): self.db = db
            def execute(self, sql, *args):
                if sql == 'PRAGMA quick_check':
                    class Result:
                        def fetchone(self): return ('invalid',)
                    return Result()
                return self.db.execute(sql, *args)
            def close(self): self.db.close()
        with patch.object(runner.sqlite3, 'connect', side_effect=lambda *a, **k: Connection(real_connect(*a, **k))):
            self.reject('LEDGER_INTEGRITY')

    def test_halted_execute_prints_manual_projection_without_recovery_or_credentials(self):
        self.activate()
        Path(self.path+'.halted').write_bytes(runner.REVIEWED_HALT_BYTES)
        before = Path(self.path).read_bytes()
        with patch.object(runner.os.environ, 'get', side_effect=AssertionError('no credentials')), \
             patch.object(runner, 'resume_reviewed_halt', side_effect=AssertionError('no recovery')), \
             patch.object(runner, 'run_service', side_effect=AssertionError('no worker')), \
             redirect_stdout(io.StringIO()) as output:
            out = runner.execute({}, {}, self.path, authorized=True)
        report = json.loads(output.getvalue())
        self.assertEqual(report['manual_trades'], {'ACTIVE': 1})
        self.assertNotIn(self.active()[0]['ref'], output.getvalue())
        self.assertEqual(out['reason'], 'LEDGER_OR_MANUAL_REVIEW_REQUIRED')
        self.assertEqual(Path(self.path).read_bytes(), before)
        self.assertTrue(Path(self.path+'.halted').exists())

    def assert_h4_subtype(self, out, subtype=None, count=1):
        nonzero = {k: v for k, v in out['manual_h4_integrity'].items() if v}
        self.assertEqual(nonzero, {} if subtype is None else {subtype: count}, out)
        self.assertEqual(sum(out['manual_h4_integrity'].values()),
                         out['manual_integrity']['invalid_h4'])

    def observe_valid_h4(self):
        self.tracker.observe_h4(h.snapshot(), h.LATER, h.fixtures.SOURCE,
            h.fixtures.CONFIG, frame_max_age_ms=10000, quote_max_age_ms=5000)

    def test_h4_subtypes_zero_for_valid_active_waiting_and_historical_manual_close(self):
        ref = self.activate()
        # No missing-for-ACTIVE rule: before the first new H4 there is no cursor.
        out = self.inspect()
        self.assertTrue(out['review_complete'], out)
        self.assert_h4_subtype(out)
        self.observe_valid_h4()
        out = self.inspect()
        self.assertTrue(out['review_complete'], out)
        self.assertEqual(out['manual_h4']['active_with_cursor'], 1)
        self.assert_h4_subtype(out)
        self.send('DONKEY', [h.signal('EARLY_DONKEY', suffix='waiting')])
        self.tracker.accept('DONKEY', self.callback('DONKEY', 'mc:'+ref, update=2), h.LATER+1)
        out = self.inspect()
        self.assertTrue(out['review_complete'], out)
        self.assert_h4_subtype(out)
        self.sql('DELETE FROM manual_trade_h4_v2')  # synthetic pre-H4 manual close
        out = self.inspect()
        self.assertTrue(out['review_complete'], out)
        self.assert_h4_subtype(out)

    def test_h4_each_timestamp_and_order_subtype_is_distinct(self):
        self.activate()
        self.observe_valid_h4()
        original = Path(self.path).read_bytes()
        cases = (
            ('invalid_cursor_timestamp', 'UPDATE manual_trade_h4_v2 SET closed_at_ms=?', (0,)),
            ('invalid_cursor_timestamp', 'UPDATE manual_trade_h4_v2 SET closed_at_ms=?', ('bad',)),
            ('invalid_cursor_timestamp', 'UPDATE manual_trade_h4_v2 SET closed_at_ms=?', (NOW+1,)),
            ('cursor_off_h4_grid', 'UPDATE manual_trade_h4_v2 SET closed_at_ms=?', (h.CLOSED+1,)),
            ('invalid_activation_timestamp', 'UPDATE manual_trade_v1 SET active_ms=NULL', ()),
            ('cursor_not_after_activation', 'UPDATE manual_trade_h4_v2 SET closed_at_ms=?', (h.CLOSED-14400000,)),
            ('cursor_ahead_observation_clock', 'UPDATE manual_trade_clock_v1 SET clock=?', (h.CLOSED-1,)),
            ('invalid_closed_timestamp', 'UPDATE manual_trade_v1 SET closed_ms=?', ('bad',)),
            ('cursor_after_close', "UPDATE manual_trade_v1 SET state='CLOSED', close_reason='MANUAL_CLOSE', closed_ms=?", (h.CLOSED-1,)),
        )
        for subtype, statement, params in cases:
            with self.subTest(subtype=subtype, value=params):
                Path(self.path).write_bytes(original)
                self.sql(statement, params)
                if subtype == 'cursor_after_close':
                    self.sql('UPDATE manual_trade_control_v1 SET clock=?', (h.CLOSED,))
                out = self.reject()
                self.assert_h4_subtype(out, subtype)
                if subtype == 'cursor_ahead_observation_clock':
                    self.assertFalse(out['clock_ahead'])  # relative order, not wall-clock future
                    self.assertEqual(out['manual_integrity']['invalid_clocks'], 0)
                if subtype == 'invalid_cursor_timestamp' and params == (NOW+1,):
                    self.assertTrue(out['clock_ahead'])

    def test_h4_cursor_for_falcon_subtype(self):
        ref = self.activate(bot='FALCON', setups=('FALCON15',))
        self.sql('INSERT INTO manual_trade_h4_v2 VALUES (?,?)', (ref, h.CLOSED))
        self.sql('UPDATE manual_trade_clock_v1 SET clock=?', (h.LATER,))
        self.assert_h4_subtype(self.reject(), 'cursor_for_falcon')

    def test_h4_cursor_for_waiting_and_expired_subtype(self):
        self.send('DONKEY', [h.signal('EARLY_DONKEY')])
        with closing(sqlite3.connect(self.path)) as db:
            ref = db.execute('SELECT ref FROM manual_trade_v1').fetchone()[0]
        self.sql('INSERT INTO manual_trade_h4_v2 VALUES (?,?)', (ref, h.CLOSED))
        self.assert_h4_subtype(self.reject(), 'cursor_for_inactive_trade')
        self.sql("UPDATE manual_trade_v1 SET state='EXPIRED', closed_ms=?, close_reason='EXPIRED'", (h.base.NOW+900000,))
        self.sql('UPDATE manual_trade_control_v1 SET clock=?', (h.base.NOW+900000,))
        self.assert_h4_subtype(self.reject(), 'cursor_for_inactive_trade')

    def test_h4_duplicate_subtype_in_exact_columns_but_missing_unique_constraint(self):
        self.activate()
        self.observe_valid_h4()
        # Test-only malformed schema. The auditor checks columns, not PK DDL.
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('ALTER TABLE manual_trade_h4_v2 RENAME TO synthetic_h4')
            db.execute('CREATE TABLE manual_trade_h4_v2 (ref TEXT, closed_at_ms INTEGER)')
            db.execute('INSERT INTO manual_trade_h4_v2 SELECT * FROM synthetic_h4')
            db.execute('INSERT INTO manual_trade_h4_v2 SELECT * FROM synthetic_h4')
            db.execute('DROP TABLE synthetic_h4')
        self.assert_h4_subtype(self.reject(), 'duplicate_ref')

    def test_h4_orphan_and_global_clocks_stay_separate(self):
        self.sql("INSERT INTO manual_trade_h4_v2 VALUES ('orphan', ?)", (h.CLOSED,))
        out = self.reject()
        self.assertEqual(out['manual_integrity']['orphan_h4'], 1)
        self.assert_h4_subtype(out)
        self.sql('DELETE FROM manual_trade_h4_v2')
        self.sql('UPDATE manual_trade_clock_v1 SET clock=?', (NOW+1,))
        out = self.reject('MANUAL_TRACKING_CLOCK_REVIEW_REQUIRED')
        self.assert_h4_subtype(out)

    def test_h4_historical_donkey_price_stop_still_requires_review_without_cursor(self):
        ref = self.activate(setups=('DONKEY',))
        # Reconstruct fa2e4af's legitimate price-stop result without loading
        # operational code: that version had no H4 table/writer.
        closed = h.base.NOW+10
        self.sql("UPDATE manual_trade_v1 SET state='CLOSED', close_reason='STOP', closed_ms=?, last_quote_ms=?", (closed, closed))
        self.sql('UPDATE manual_trade_clock_v1 SET clock=?', (closed,))
        with closing(sqlite3.connect(self.path)) as db:
            route = db.execute('SELECT route FROM manual_trade_v1').fetchone()[0]
        self.sql("INSERT INTO manual_trade_event_v1 VALUES (?, 'STOP', ?, 'synthetic historic stop', 'CONFIRMED', ?)", (ref, route, closed))
        out = self.reject('MANUAL_TRACKING_INTEGRITY_REVIEW_REQUIRED')
        self.assert_h4_subtype(out, 'missing_for_donkey_stop')
        self.assertTrue(all(v == 0 for k, v in out['manual_integrity'].items()
                            if k not in {'schema_ok', 'invalid_h4'}), out)

    def test_h4_first_failure_priority_and_aggregate_counts_unchanged(self):
        self.activate()
        self.observe_valid_h4()
        self.sql('UPDATE manual_trade_h4_v2 SET closed_at_ms=?', (0,))
        self.sql('UPDATE manual_trade_v1 SET active_ms=NULL')
        out = self.reject()
        self.assert_h4_subtype(out, 'invalid_cursor_timestamp')
        self.assertFalse(out['clock_ahead'])

    def test_h4_supplied_count_shape_needs_at_least_two_invalid_occurrences(self):
        # Seven non-orphan cursors cannot all fit in five eligible trades.
        for index in range(7):
            self.send('DONKEY', [h.signal('DONKEY', symbol=f'TEST{index}-USDT', suffix=str(index))])
        with closing(sqlite3.connect(self.path)) as db, db:
            refs = [r[0] for r in db.execute('SELECT ref FROM manual_trade_v1 ORDER BY symbol')]
            for index, ref in enumerate(refs):
                if index < 5:
                    state = 'ACTIVE' if index < 2 else 'CLOSED'
                    db.execute('UPDATE manual_trade_v1 SET state=?, active_ms=?, closed_ms=?, close_reason=? WHERE ref=?',
                        (state, h.base.NOW+1, None if index < 2 else h.LATER,
                         None if index < 2 else 'MANUAL_CLOSE', ref))
                db.execute('INSERT INTO manual_trade_h4_v2 VALUES (?,?)', (ref, h.CLOSED))
            db.execute('UPDATE manual_trade_control_v1 SET clock=?', (h.LATER,))
            db.execute('UPDATE manual_trade_clock_v1 SET clock=?', (h.LATER,))
        out = self.reject('MANUAL_TRACKING_INTEGRITY_REVIEW_REQUIRED')
        self.assertEqual(out['manual_trades'], {'ACTIVE': 2, 'CLOSED': 3, 'WAITING': 2})
        self.assertEqual(out['manual_h4'], {'rows': 7, 'active_with_cursor': 2})
        self.assertEqual(out['manual_integrity']['orphan_h4'], 0)
        self.assert_h4_subtype(out, 'cursor_for_inactive_trade', 2)


if __name__ == '__main__':
    unittest.main()
