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

    def test_existing_writer_cross_route_is_valid_without_recovery(self):
        ref = self.activate(bot='FALCON', setups=('FALCON15',))
        now = fixtures.base.h.base.NOW + 100
        update = self.callback('DONKEY', 'mc:' + ref, update=99)
        self.tracker.accept('DONKEY', update, now)
        out = self.inspect()
        self.assertEqual(out['manual_integrity']['invalid_timestamps'], 0)
        self.assertEqual(out['manual_timestamp_integrity']['invalid_trade_closed_ms'], 0)
        self.assertEqual(sum(out['manual_close_control_integrity'].values()), 0)
        self.assertTrue(out['review_complete'])
        self.assertEqual(out['manual_close_control_diagnostics'], [])

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

    def test_same_operator_watermark_validation_and_failed_diagnostics(self):
        from contextlib import closing
        import sqlite3
        self.activate(bot='FALCON', setups=('FALCON15',))
        self.sql("UPDATE manual_trade_v1 SET state='CLOSED', close_reason='MANUAL_CLOSE', closed_ms=active_ms+100")
        with closing(sqlite3.connect(self.path)) as db:
            closed, origin_route = db.execute('SELECT closed_ms, route FROM manual_trade_v1').fetchone()
        cases = (
            ('sufficient', [(77, closed)], True, 1, closed, closed),
            ('strictly_greater', [(77, closed+10)], True, 1, closed+10, closed+10),
            ('insufficient', [(77, closed-1)], False, 0, closed-1, None),
            ('other_operator', [(88, closed+10)], False, 0, closed-100, None),
            ('text_clock', [(77, 'invalid')], False, 0, closed-100, None),
            ('real_clock', [(77, closed+0.5)], False, 0, closed-100, None),
            ('multiple', [(77, closed+20), (77, closed+5), (88, closed+30)],
             True, 2, closed+20, closed+5),
            ('equal_clock_tie', [(77, closed), (77, closed)], True, 2, closed, closed),
        )
        for name, extra, satisfied, covering_count, maximum, minimum in cases:
            with self.subTest(case=name):
                self.sql('DELETE FROM manual_trade_control_v1 WHERE route != ?', (origin_route,))
                for i, (operator, clock) in enumerate(extra):
                    self.sql('INSERT INTO manual_trade_control_v1 VALUES (?, ?, ?, 0, ?, NULL)',
                             ('private-route-' + str(i), '909', operator, clock))
                out = self.inspect()  # Also checks SQLite bytes and no delivery/live.
                self.assertIs(out['review_complete'], satisfied)
                self.assertEqual(out['manual_timestamp_integrity']['invalid_trade_close_control_relation'], int(not satisfied))
                self.assertEqual(out['manual_close_control_integrity']['close_after_control_clock'], int(not satisfied))
                self.assertEqual(out['manual_integrity']['invalid_timestamps'], int(not satisfied))
                self.assertEqual(sum(out['manual_timestamp_integrity'].values()), out['manual_integrity']['invalid_timestamps'])
                if satisfied:
                    self.assertEqual(out['reason'], 'READ_ONLY_NO_RECOVERY')
                    self.assertEqual(out['manual_close_control_diagnostics'], [])
                    continue
                self.assertEqual(out['reason'], 'MANUAL_TRACKING_CLOCK_REVIEW_REQUIRED')
                d = out['manual_close_control_diagnostics'][0]
                self.assertEqual(d['failed_term'], 'close_after_control_clock')
                self.assertEqual(d['same_operator_control_count'], 1 + sum(op == 77 for op, _ in extra))
                self.assertEqual(d['same_operator_integer_clock_count'],
                                 1 + sum(op == 77 and type(clock) is int for op, clock in extra))
                self.assertIs(d['corrected_invariant_satisfied'], False)
                self.assertEqual(d['same_operator_covering_control_count'], covering_count)
                self.assertEqual(d['same_operator_max_control_clock_ms'], maximum)
                self.assertEqual(d['same_operator_max_minus_closed_ms'], maximum-closed)
                self.assertNotIn('minimum_covering_control_clock_ms', d)
                self.assertNotIn('minimum_covering_minus_closed_ms', d)
                self.assertNotIn('minimum_covering_route_tag', d)
                self.assertFalse({'operator', 'route', 'chat', 'ref'} & set(d))
                self.assertNotIn('private-route-', str(d))
                self.assertNotIn(origin_route, str(d))

    def test_expired_keeps_origin_route_rule_and_no_same_operator_diagnostic(self):
        self.send('FALCON', [fixtures.base.h.signal('FALCON15')])
        self.sql("UPDATE manual_trade_v1 SET state='EXPIRED', close_reason='EXPIRED', closed_ms=expires_ms")
        self.sql('UPDATE manual_trade_control_v1 SET clock=(SELECT created_ms FROM manual_trade_v1)')
        self.sql("INSERT INTO manual_trade_control_v1 SELECT 'private-covering-route', '909', 77, 0, closed_ms+1, NULL FROM manual_trade_v1")
        out = self.inspect()
        self.assertFalse(out['review_complete'])
        self.assertEqual(out['manual_close_control_integrity']['close_after_control_clock'], 1)
        d = out['manual_close_control_diagnostics'][0]
        self.assertEqual(d['state'], 'EXPIRED')
        self.assertFalse(any(k.startswith(('same_operator_', 'minimum_covering_')) for k in d))
        self.assertNotIn('corrected_invariant_satisfied', d)

    def test_invalid_origin_operator_is_not_inferred_from_family(self):
        self.activate(bot='FALCON', setups=('FALCON15',))
        self.sql("UPDATE manual_trade_v1 SET state='CLOSED', close_reason='MANUAL_CLOSE', closed_ms=active_ms+1")
        self.sql("UPDATE manual_trade_control_v1 SET operator='invalid'")
        out = self.inspect()
        self.assertFalse(out['review_complete'])
        self.assertNotIn('corrected_invariant_satisfied', out['manual_close_control_diagnostics'][0])

    def test_origin_equal_or_greater_and_other_errors_still_block(self):
        self.activate(bot='FALCON', setups=('FALCON15',))
        self.sql("UPDATE manual_trade_v1 SET state='CLOSED', close_reason='MANUAL_CLOSE', closed_ms=active_ms")
        for delta in (0, 10):
            with self.subTest(delta=delta):
                self.sql('UPDATE manual_trade_control_v1 SET clock=(SELECT closed_ms FROM manual_trade_v1)+?', (delta,))
                out = self.inspect()
                self.assertTrue(out['review_complete'])
                self.assertEqual(out['manual_integrity']['invalid_timestamps'], 0)
                self.assertEqual(out['manual_close_control_diagnostics'], [])
        self.sql('UPDATE manual_trade_v1 SET stop=0')
        out = self.inspect()
        self.assertFalse(out['review_complete'])
        self.assertEqual(out['manual_integrity']['invalid_prices'], 1)
        self.assertEqual(out['manual_timestamp_integrity']['invalid_trade_close_control_relation'], 0)

    def test_invalid_origin_operator_cannot_use_sufficient_watermark(self):
        self.activate(bot='FALCON', setups=('FALCON15',))
        self.sql("UPDATE manual_trade_v1 SET state='CLOSED', close_reason='MANUAL_CLOSE', closed_ms=active_ms")
        for operator in ('invalid', 0, -1, 77.5):
            with self.subTest(operator=operator):
                self.sql('UPDATE manual_trade_control_v1 SET operator=?, clock=(SELECT closed_ms FROM manual_trade_v1)+1', (operator,))
                out = self.inspect()
                self.assertFalse(out['review_complete'])
                self.assertEqual(out['manual_timestamp_integrity']['invalid_trade_close_control_relation'], 1)
                self.assertEqual(out['manual_close_control_integrity']['invalid_origin_operator'], 1)
                self.assertEqual(out['manual_close_control_diagnostics'][0]['failed_term'], 'invalid_origin_operator')
                self.assertEqual(sum(out['manual_timestamp_integrity'].values()), out['manual_integrity']['invalid_timestamps'])

    def test_bad_clock_elsewhere_still_blocks_a_covered_close(self):
        ref = self.activate(bot='FALCON', setups=('FALCON15',))
        now = fixtures.base.h.base.NOW + 100
        self.tracker.accept('DONKEY', self.callback('DONKEY', 'mc:' + ref, update=99), now)
        self.sql("INSERT INTO manual_trade_control_v1 VALUES ('private-invalid-route', '909', 77, 0, 'invalid', NULL)")
        out = self.inspect()
        self.assertFalse(out['review_complete'])
        self.assertEqual(out['manual_timestamp_integrity']['invalid_trade_close_control_relation'], 0)
        self.assertEqual(out['manual_integrity']['invalid_timestamps'], 0)
        self.assertEqual(out['manual_integrity']['invalid_clocks'], 1)
        self.assertEqual(out['manual_close_control_diagnostics'], [])

    def test_non_integer_origin_clock_does_not_define_manual_watermark(self):
        from contextlib import closing
        import sqlite3
        self.activate(bot='FALCON', setups=('FALCON15',))
        self.sql("UPDATE manual_trade_v1 SET state='CLOSED', close_reason='MANUAL_CLOSE', closed_ms=active_ms")
        with closing(sqlite3.connect(self.path)) as db:
            origin = db.execute('SELECT route FROM manual_trade_v1').fetchone()[0]
        self.sql('UPDATE manual_trade_control_v1 SET clock=(SELECT closed_ms FROM manual_trade_v1) WHERE route!=?', (origin,))
        self.sql("UPDATE manual_trade_control_v1 SET clock='invalid' WHERE route=?", (origin,))
        out = self.inspect()
        self.assertFalse(out['review_complete'])  # Other clock/activation invariants still fail.
        self.assertEqual(out['manual_timestamp_integrity']['invalid_trade_close_control_relation'], 0)
        self.assertEqual(out['manual_integrity']['invalid_clocks'], 1)
        self.assertEqual(out['manual_timestamp_integrity']['invalid_trade_activation_relation'], 1)

    def test_real_values_synthetic_snapshot_is_valid_and_halt_is_preserved(self):
        from contextlib import closing
        from pathlib import Path
        from unittest.mock import patch
        import sqlite3
        self.activate(bot='FALCON', setups=('FALCON15',))
        origin_clock, closed = 1791136056751, 1791151116911
        self.sql("UPDATE manual_trade_v1 SET state='CLOSED', close_reason='MANUAL_CLOSE', closed_ms=?", (closed,))
        with closing(sqlite3.connect(self.path)) as db:
            origin = db.execute('SELECT route FROM manual_trade_v1').fetchone()[0]
        self.sql('UPDATE manual_trade_control_v1 SET clock=? WHERE route=?', (origin_clock, origin))
        self.sql('UPDATE manual_trade_control_v1 SET clock=? WHERE route!=?', (closed, origin))
        halt = Path(self.path + '.halted')
        halt.write_bytes(b'MANUAL_REVIEW_REQUIRED\n')
        with patch.object(fixtures.base, 'NOW', closed+1000):
            out = self.inspect()
        self.assertLess(origin_clock, closed)  # Old origin-only rule rejected this snapshot.
        self.assertTrue(out['review_complete'], out)
        self.assertEqual(out['manual_timestamp_integrity']['invalid_trade_close_control_relation'], 0)
        self.assertEqual(out['manual_integrity']['invalid_timestamps'], 0)
        self.assertEqual(sum(out['manual_close_control_integrity'].values()), 0)
        self.assertEqual(out['manual_close_control_diagnostics'], [])
        self.assertEqual(halt.read_bytes(), b'MANUAL_REVIEW_REQUIRED\n')
