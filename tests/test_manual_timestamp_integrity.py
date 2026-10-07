"""Offline synthetic fixtures; inherited audit enforces byte-identical SQLite."""
import test_manual_ledger_read_only_audit as base


class TimestampIntegrity(base.h.base.Harness):
    def setUp(self):
        super().setUp()
        base.legacy.provision(self.path)
        self.click_update = 0
    sql = base.ReadOnlyAudit.sql
    activate = base.ReadOnlyAudit.activate
    inspect = base.ReadOnlyAudit.inspect
    def check_category(self, category):
        out = self.inspect()
        counters = out['manual_timestamp_integrity']
        self.assertGreater(counters[category], 0, out)
        self.assertIs(out['review_complete'], False)
        self.assertEqual(sum(counters.values()), out['manual_integrity']['invalid_timestamps'])
        samples = out['manual_timestamp_diagnostics']
        self.assertTrue(any(d['category'] == category for d in samples))
        for d in samples:
            self.assertEqual(set(d), {'table', 'field', 'reason', 'row_tag', 'category'})
            self.assertRegex(d['row_tag'], r'^[a-f0-9]{12}$')
        return out

    def test_valid_and_every_trade_field(self):
        for field in ('created_ms', 'active_ms', 'tp_ms', 'last_quote_ms', 'closed_ms'):
            with self.subTest(field=field):
                self.activate(bot='FALCON', setups=('FALCON15',), symbol='BTC-USDT')
                valid = self.inspect()
                self.assertEqual(sum(valid['manual_timestamp_integrity'].values()), 0)
                self.sql(f"UPDATE manual_trade_v1 SET {field}='invalid'")
                self.check_category('invalid_trade_' + field)
                # Restore only the disposable synthetic fixture between cases.
                self.sql('DELETE FROM manual_trade_candidate_v1')
                self.sql('DELETE FROM manual_trade_v1')
                self.sql('DELETE FROM delivery_v1')

    def test_relations_and_overlapping_counts(self):
        cases = (
            ('expires_ms=created_ms', 'invalid_trade_expiry_relation'),
            ('active_ms=created_ms-1', 'invalid_trade_activation_relation'),
            ("state='WAITING'", 'invalid_trade_inactive_timestamps'),
            ('last_quote_ms=active_ms-1', 'invalid_trade_quote_relation'),
            ("state='CLOSED', close_reason='MANUAL_CLOSE', closed_ms=active_ms+1", 'invalid_trade_close_control_relation'),
        )
        self.activate(bot='FALCON', setups=('FALCON15',))
        original = self.path
        from pathlib import Path
        import sqlite3
        from contextlib import closing
        snapshot = Path(original).read_bytes()
        for assignment, category in cases:
            with self.subTest(category=category):
                clone = Path(self.temp.name) / (category + '.sqlite')
                clone.write_bytes(snapshot)
                with closing(sqlite3.connect(clone)) as db, db:
                    db.execute('UPDATE manual_trade_v1 SET ' + assignment)
                self.path = str(clone)
                self.check_category(category)
        self.path = original

    def test_event_reasons_and_future_flag(self):
        ref = self.activate(bot='FALCON', setups=('FALCON15',))
        for value, reason in (('invalid', 'NON_INTEGER'), (0, 'NON_POSITIVE'),
                              (base.NOW + 1, 'AFTER_AUDIT_NOW')):
            with self.subTest(reason=reason):
                self.sql("INSERT OR REPLACE INTO manual_trade_event_v1 VALUES (?, 'TP50', 'r', 'fixture', 'PENDING', ?)", (ref, value))
                out = self.check_category('invalid_event_created_ms')
                self.assertEqual(out['manual_integrity']['invalid_timestamps'], 1)
                sample = next(d for d in out['manual_timestamp_diagnostics'] if d['category'] == 'invalid_event_created_ms')
                self.assertEqual(sample['reason'], reason)
                self.assertEqual(out['manual_integrity']['clock_ahead'], value == base.NOW + 1)

    def test_samples_bounded_full_counts(self):
        for i in range(40):
            self.sql("INSERT INTO manual_trade_event_v1 VALUES (?, 'TP50', 'r', 'fixture', 'PENDING', 0)", (str(i),))
        out = self.check_category('invalid_event_created_ms')
        self.assertEqual(out['manual_timestamp_integrity']['invalid_event_created_ms'], 40)
        self.assertEqual(len(out['manual_timestamp_diagnostics']), 32)
