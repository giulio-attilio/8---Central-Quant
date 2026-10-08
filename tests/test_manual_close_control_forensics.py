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
        d = out['manual_close_control_diagnostics'][0]
        self.assertIs(d['corrected_invariant_satisfied'], True)
        self.assertEqual(d['same_operator_covering_control_count'], 1)
        self.assertEqual(d['minimum_covering_control_clock_ms'], now)
        self.assertEqual(d['minimum_covering_minus_closed_ms'], 0)

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

    def test_same_operator_watermark_cases_remain_fail_closed(self):
        import hashlib
        from contextlib import closing
        import sqlite3
        self.activate(bot='FALCON', setups=('FALCON15',))
        self.sql("UPDATE manual_trade_v1 SET state='CLOSED', close_reason='MANUAL_CLOSE', closed_ms=active_ms+100")
        with closing(sqlite3.connect(self.path)) as db:
            closed, origin_route = db.execute('SELECT closed_ms, route FROM manual_trade_v1').fetchone()
        cases = (
            ('sufficient', [(77, closed)], True, 1, closed, closed),
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
                self.assertFalse(out['review_complete'])
                self.assertEqual(out['reason'], 'MANUAL_TRACKING_CLOCK_REVIEW_REQUIRED')
                self.assertEqual(out['manual_timestamp_integrity']['invalid_trade_close_control_relation'], 1)
                self.assertEqual(out['manual_close_control_integrity']['close_after_control_clock'], 1)
                self.assertEqual(out['manual_integrity']['invalid_timestamps'], 1)
                d = out['manual_close_control_diagnostics'][0]
                self.assertEqual(d['failed_term'], 'close_after_control_clock')
                self.assertEqual(d['same_operator_control_count'], 1 + sum(op == 77 for op, _ in extra))
                self.assertEqual(d['same_operator_integer_clock_count'],
                                 1 + sum(op == 77 and type(clock) is int for op, clock in extra))
                self.assertIs(d['corrected_invariant_satisfied'], satisfied)
                self.assertEqual(d['same_operator_covering_control_count'], covering_count)
                self.assertEqual(d['same_operator_max_control_clock_ms'], maximum)
                self.assertEqual(d['same_operator_max_minus_closed_ms'], maximum-closed)
                if minimum is None:
                    self.assertNotIn('minimum_covering_control_clock_ms', d)
                    self.assertNotIn('minimum_covering_minus_closed_ms', d)
                    self.assertNotIn('minimum_covering_route_tag', d)
                else:
                    self.assertEqual(d['minimum_covering_control_clock_ms'], minimum)
                    self.assertEqual(d['minimum_covering_minus_closed_ms'], minimum-closed)
                    minimum_index = next(i for i, (op, clock) in enumerate(extra)
                                         if op == 77 and clock == minimum)
                    self.assertEqual(d['minimum_covering_route_tag'], hashlib.sha256(
                        ('private-route-' + str(minimum_index)).encode()).hexdigest()[:12])
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
