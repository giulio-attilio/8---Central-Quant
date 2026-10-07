import test_manual_timestamp_integrity as fixtures


class CloseControlForensics(fixtures.TimestampIntegrity):
    def test_four_real_terms_and_valid_relation(self):
        from pathlib import Path
        import sqlite3
        from contextlib import closing
        self.activate(bot='FALCON', setups=('FALCON15',))
        self.sql("UPDATE manual_trade_v1 SET state='CLOSED', close_reason='MANUAL_CLOSE', closed_ms=active_ms")
        valid = self.inspect()
        self.assertEqual(sum(valid['manual_close_control_integrity'].values()), 0)
        self.assertTrue(valid['review_complete'])
        original = self.path
        snapshot = Path(original).read_bytes()
        cases = (
            ('DELETE FROM manual_trade_control_v1', 'missing_route_control'),
            ("UPDATE manual_trade_control_v1 SET clock='invalid'", 'non_integer_control_clock'),
            ("UPDATE manual_trade_v1 SET closed_ms='invalid'", 'non_integer_closed_ms'),
            ('UPDATE manual_trade_v1 SET closed_ms=active_ms+1', 'close_after_control_clock'),
        )
        for sql, subtype in cases:
            with self.subTest(subtype=subtype):
                clone = Path(self.temp.name) / (subtype + '.sqlite')
                clone.write_bytes(snapshot)
                with closing(sqlite3.connect(clone)) as db, db:
                    db.execute(sql)
                self.path = str(clone)
                out = self.inspect()
                self.assertFalse(out['review_complete'])
                self.assertEqual(out['manual_timestamp_integrity']['invalid_trade_close_control_relation'], 1)
                self.assertEqual(sum(out['manual_close_control_integrity'].values()), 1)
                self.assertEqual(out['manual_close_control_integrity'][subtype], 1)
                self.assertEqual(sum(out['manual_timestamp_integrity'].values()), out['manual_integrity']['invalid_timestamps'])
                d = out['manual_close_control_diagnostics'][0]
                self.assertEqual(d['reason'], subtype.upper())
                self.assertEqual(d['failed_term'], subtype)
                self.assertRegex(d['row_tag'], r'^[a-f0-9]{12}$')
                self.assertRegex(d['route_tag'], r'^[a-f0-9]{12}$')
                self.assertFalse({'ref', 'route', 'chat', 'operator', 'text'} & set(d))
                self.assertEqual(d['stop_event_created_ms'], [])
                self.assertEqual(d['matching_stop_event_count'], 0)
                if subtype == 'close_after_control_clock':
                    self.assertEqual(d['closed_minus_control_ms'], 1)
        self.path = original

    def test_stop_is_not_subject_to_close_control_rule(self):
        ref = self.activate(bot='FALCON', setups=('FALCON15',))
        self.sql("UPDATE manual_trade_v1 SET state='CLOSED', close_reason='STOP', closed_ms=active_ms+1")
        out = self.inspect()
        self.assertEqual(sum(out['manual_close_control_integrity'].values()), 0)
        self.assertEqual(out['manual_close_control_diagnostics'], [])

    def test_existing_writer_cross_route_reproduces_single_failure(self):
        ref = self.activate(bot='FALCON', setups=('FALCON15',))
        now = fixtures.base.h.base.NOW + 100
        update = self.callback('DONKEY', 'mc:' + ref, update=99)
        self.tracker.accept('DONKEY', update, now)
        out = self.inspect()
        self.assertEqual(out['manual_integrity']['invalid_timestamps'], 1)
        self.assertEqual(out['manual_timestamp_integrity']['invalid_trade_closed_ms'], 0)
        self.assertEqual(out['manual_close_control_integrity']['close_after_control_clock'], 1)
        self.assertFalse(out['review_complete'])

    def test_stop_event_match_and_redaction(self):
        ref = self.activate(bot='FALCON', setups=('FALCON15',))
        self.sql("UPDATE manual_trade_v1 SET state='CLOSED', close_reason='MANUAL_CLOSE', closed_ms=active_ms+1")
        self.sql("INSERT INTO manual_trade_event_v1 SELECT ref, 'STOP', route, 'private fixture text', 'PENDING', closed_ms FROM manual_trade_v1")
        out = self.inspect()
        d = out['manual_close_control_diagnostics'][0]
        self.assertEqual(d['matching_stop_event_count'], 1)
        self.assertNotIn(ref, str(d))
        self.assertNotIn('private fixture text', str(d))
        self.sql("UPDATE manual_trade_event_v1 SET created_ms=created_ms+1")
        self.assertEqual(self.inspect()['manual_close_control_diagnostics'][0]['matching_stop_event_count'], 0)
