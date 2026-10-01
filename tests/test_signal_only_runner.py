"""No external effects: install the existing audit guards before local imports."""
import contextlib
import io
import json
from pathlib import Path
import signal
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_signal_only_service as fixtures
import signal_only_runner as runner


class RunnerTests(unittest.TestCase):
    def reviewed_fixture(self, directory):
        import donkey_signal_tracking as tracking
        path = Path(directory) / 'reviewed.sqlite'
        runner.provision_ledger(path)
        tracking.provision(path)
        with contextlib.closing(runner.sqlite3.connect(path)) as db, db:
            db.executemany("INSERT INTO delivery_v1 VALUES (?, ?, 'test-route', 'CONFIRMED', 1, 1)",
                           [(str(i), str(i)) for i in range(85)])
            db.executemany("INSERT INTO route_check_v1 VALUES (?, 'test-route', 'CONFIRMED')", [('FALCON',), ('DONKEY',)])
        Path(str(path) + '.halted').write_bytes(b'MANUAL_REVIEW_REQUIRED\n')
        return path

    def test_reviewed_resume_archives_once_and_never_changes_ledger(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.reviewed_fixture(directory)
            before = path.read_bytes()
            self.assertTrue(runner.resume_reviewed_halt(path, '20260930-205047'))
            self.assertEqual(path.read_bytes(), before)
            self.assertFalse(Path(str(path) + '.halted').exists())
            self.assertEqual(Path(str(path) + '.halted.reviewed-20260930-205047').read_bytes(), b'MANUAL_REVIEW_REQUIRED\n')
            Path(str(path) + '.halted').write_bytes(b'MANUAL_REVIEW_REQUIRED\n')
            self.assertFalse(runner.resume_reviewed_halt(path, '20260930-205047'))
            self.assertTrue(Path(str(path) + '.halted').exists())

    def test_reviewed_resume_rejects_changed_state_or_incident(self):
        changes = ["UPDATE delivery_v1 SET status='UNKNOWN' WHERE identity='0'",
                   "DELETE FROM delivery_v1 WHERE identity='0'",
                   "INSERT INTO donkey_reference_events_v1 VALUES ('test', 'STOP', 'test', 'PENDING')",
                   "INSERT INTO donkey_reference_v1 VALUES ('test', 'test', 'test', '{}', 1, 'ACTIVE', 1, NULL, NULL, NULL, 1)",
                   "UPDATE route_check_v1 SET status='UNKNOWN'",
                   "INSERT INTO delivery_clock_v1 VALUES (1, 4102444800000)"]
        for sql in changes:
            with self.subTest(sql=sql), tempfile.TemporaryDirectory() as directory:
                path = self.reviewed_fixture(directory)
                with contextlib.closing(runner.sqlite3.connect(path)) as db, db:
                    db.execute(sql)
                self.assertFalse(runner.resume_reviewed_halt(path, '20260930-205047'))
                self.assertTrue(Path(str(path) + '.halted').exists())
                self.assertFalse(Path(str(path) + '.halted.reviewed-20260930-205047').exists())
        self.assertFalse(runner.resume_reviewed_halt('unused', '../other'))

    def test_reviewed_resume_disk_failure_keeps_original_block(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.reviewed_fixture(directory)
            with patch.object(runner.os, 'fsync', side_effect=OSError('private')):
                self.assertFalse(runner.resume_reviewed_halt(path, '20260930-205047'))
            self.assertTrue(Path(str(path) + '.halted').exists())
            self.assertFalse(runner.resume_reviewed_halt(path, '20260930-205047'))

    def test_resume_requires_authorization_before_any_recovery_or_credentials(self):
        with patch.object(runner, 'resume_reviewed_halt') as resume, \
             patch.object(runner.os.environ, 'get', side_effect=AssertionError('no env')):
            self.assertEqual(runner.execute({}, {}, 'unused', reviewed_halt='20260930-205047')['status'], 'BLOCKED')
            resume.assert_not_called()

    def test_new_failure_cannot_reuse_reviewed_resume_on_platform_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.reviewed_fixture(directory)
            with patch.object(runner.os.environ, 'get', return_value='FAKE'), \
                 patch.object(runner, 'run_service', return_value=dict(status='FAILED')) as run:
                self.assertEqual(runner.execute({}, {}, path, authorized=True, reviewed_halt='20260930-205047')['status'], 'FAILED')
                self.assertEqual(runner.execute({}, {}, path, authorized=True, reviewed_halt='20260930-205047')['reason'],
                                 'REVIEWED_HALT_RECEIPT_PRESENT_REVIEW_REQUIRED')
                run.assert_called_once()

    def test_completed_recovery_normal_restart_needs_no_incident_argument(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.reviewed_fixture(directory)
            with patch.object(runner.os.environ, 'get', return_value='FAKE'), \
                 patch.object(runner, 'run_service', return_value=dict(status='STOPPED')) as run:
                first = runner.execute({}, {}, path, authorized=True, reviewed_halt='20260930-205047')
                second = runner.execute({}, {}, path, authorized=True)
            self.assertEqual(first['status'], 'STOPPED')
            self.assertEqual(second['status'], 'STOPPED')
            self.assertFalse(Path(str(path) + '.halted').exists())
            self.assertTrue(runner.reviewed_halt_archive(path).is_file())
            self.assertEqual(run.call_count, 2)

    def test_consumed_receipt_blocks_before_credentials_or_recovery_attempt(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.reviewed_fixture(directory)
            runner.reviewed_halt_archive(path).write_bytes(b'MANUAL_REVIEW_REQUIRED\n')
            with patch.object(runner.os.environ, 'get', side_effect=AssertionError('no credentials')), \
                 patch.object(runner, 'resume_reviewed_halt') as resume, \
                 patch.object(runner, 'run_service') as run:
                result = runner.execute({}, {}, path, authorized=True, reviewed_halt='20260930-205047')
            self.assertEqual(result['reason'], 'REVIEWED_HALT_RECEIPT_PRESENT_REVIEW_REQUIRED')
            resume.assert_not_called()
            run.assert_not_called()

    def test_halted_review_is_read_only_and_keeps_unknown_and_active_visible(self):
        import donkey_signal_tracking as tracking
        with tempfile.TemporaryDirectory() as directory:
            _, path = self.inputs(directory)
            runner.provision_ledger(path)
            tracking.provision(path)
            with contextlib.closing(runner.sqlite3.connect(path)) as db, db:
                db.execute("INSERT INTO delivery_v1 VALUES ('private-id', 'private-candle', 'private-route', 'UNKNOWN', 1, NULL)")
                db.execute("INSERT INTO donkey_reference_v1 VALUES ('private-ref', 'private-id', 'private-route', '{}', 1, 'ACTIVE', 1, NULL, NULL, NULL, 1)")
            halted = Path(str(path) + '.halted')
            halted.write_text('MANUAL_REVIEW_REQUIRED\n')
            before = path.read_bytes()
            with patch.object(runner.os.environ, 'get', side_effect=AssertionError('no credentials')), \
                 patch.object(runner, 'run_service') as run, contextlib.redirect_stdout(io.StringIO()) as output:
                result = runner.execute({}, {}, path, authorized=True)
            report = json.loads(output.getvalue())
            self.assertTrue(report['review_complete'])
            self.assertEqual(report['delivery'], {'UNKNOWN': 1})
            self.assertEqual(report['references'], {'ACTIVE': 1})
            self.assertNotIn('private-', output.getvalue())
            self.assertEqual(result['status'], 'BLOCKED')
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(halted.read_text(), 'MANUAL_REVIEW_REQUIRED\n')
            run.assert_not_called()

    def test_halted_review_missing_schema_never_creates_or_repairs(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'absent.sqlite'
            self.assertFalse(runner.inspect_halted_ledger(path)['review_complete'])
            self.assertFalse(path.exists())
            runner.provision_ledger(path)
            before = path.read_bytes()
            self.assertFalse(runner.inspect_halted_ledger(path)['review_complete'])
            self.assertEqual(path.read_bytes(), before)

    def test_route_check_failure_prevents_service(self):
        with tempfile.TemporaryDirectory() as directory:
            _, path = self.inputs(directory)
            runner.provision_ledger(path)
            with patch.object(runner.os.environ, 'get', return_value='FAKE'), \
                 patch.object(runner, 'verify_routes_once', return_value=dict(status='BLOCKED')) as verify, \
                 patch.object(runner, 'run_service') as run:
                self.assertEqual(runner.execute({}, {}, path, authorized=True, verify_telegram=True)['status'], 'BLOCKED')
            verify.assert_called_once()
            run.assert_not_called()

    def test_named_attempt_preserves_previous_claim_and_blocks_restart(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(runner.os.path, 'ismount', return_value=True), \
             patch.object(runner, 'diagnose_public_cycle', return_value={'status': 'DIAGNOSTIC_COMPLETE'}) as collect:
            old = Path(directory) / 'signals-public-diagnostic.claimed'
            old.write_bytes(b'PREVIOUS_ATTEMPT')
            kwargs = dict(authorized=True, state_dir=directory, attempt='20260930-expiry-v2')
            self.assertEqual(runner.diagnose_once({}, {}, **kwargs)['status'], 'DIAGNOSTIC_COMPLETE')
            self.assertEqual(runner.diagnose_once({}, {}, **kwargs)['reason'], 'DIAGNOSTIC_ALREADY_CLAIMED_NO_RETRY')
            self.assertEqual(old.read_bytes(), b'PREVIOUS_ATTEMPT')
            collect.assert_called_once()

    def test_invalid_attempts_rejected_before_storage_or_network(self):
        with patch.object(runner.os.path, 'ismount') as mount, \
             patch.object(runner, 'diagnose_public_cycle') as collect:
            for attempt in ('', '../old', 'a/b', 'a\\b', 'A', 'a' * 49, 123):
                self.assertEqual(runner.diagnose_once({}, {}, authorized=True, attempt=attempt)['reason'],
                                 'DIAGNOSTIC_ATTEMPT_INVALID')
            self.assertEqual(runner.diagnose_once({}, {}, attempt='valid')['reason'],
                             'PUBLIC_READ_AUTHORIZATION_REQUIRED')
            mount.assert_not_called()
            collect.assert_not_called()

    def test_once_requires_authorization_and_mounted_storage(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(runner, 'diagnose_public_cycle') as collect, \
             patch.object(runner.os.environ, 'get', side_effect=AssertionError('no env')):
            self.assertEqual(runner.diagnose_once({}, {}, state_dir=directory)['reason'],
                             'PUBLIC_READ_AUTHORIZATION_REQUIRED')
            self.assertEqual(runner.diagnose_once({}, {}, state_dir=directory, authorized=True)['reason'],
                             'PERSISTENT_MOUNT_REQUIRED')
            collect.assert_not_called()
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_once_claim_survives_success_failure_and_restart(self):
        for outcome in ({'status': 'DIAGNOSTIC_COMPLETE'}, {'status': 'FAILED'}, RuntimeError('private')):
            with self.subTest(outcome=type(outcome).__name__), tempfile.TemporaryDirectory() as directory, \
                 patch.object(runner.os.path, 'ismount', return_value=True), \
                 patch.object(runner.os.environ, 'get', side_effect=AssertionError('no env')), \
                 patch.object(runner, 'diagnose_public_cycle') as collect:
                if isinstance(outcome, Exception):
                    collect.side_effect = outcome
                    with self.assertRaises(RuntimeError):
                        runner.diagnose_once({}, {}, authorized=True, state_dir=directory)
                else:
                    collect.return_value = outcome
                    self.assertEqual(runner.diagnose_once({}, {}, authorized=True, state_dir=directory), outcome)
                self.assertEqual(runner.diagnose_once({}, {}, authorized=True, state_dir=directory)['reason'],
                                 'DIAGNOSTIC_ALREADY_CLAIMED_NO_RETRY')
                collect.assert_called_once()
                self.assertEqual((Path(directory) / 'signals-public-diagnostic.claimed').read_bytes(),
                                 b'CLAIMED_NO_AUTOMATIC_RETRY\n')

    def test_once_storage_failure_blocks_network_and_keeps_claim(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(runner.os.path, 'ismount', return_value=True), \
             patch.object(runner.os, 'fsync', side_effect=OSError('private')), \
             patch.object(runner, 'diagnose_public_cycle') as collect:
            self.assertEqual(runner.diagnose_once({}, {}, authorized=True, state_dir=directory)['reason'],
                             'DIAGNOSTIC_STORAGE_REVIEW_REQUIRED')
            self.assertTrue((Path(directory) / 'signals-public-diagnostic.claimed').exists())
            collect.assert_not_called()

    def test_once_cli_does_not_read_credentials_or_enable_service(self):
        with tempfile.TemporaryDirectory() as directory:
            config, _ = self.inputs(directory)
            with patch.object(runner, 'diagnose_once', return_value=dict(status='DIAGNOSTIC_COMPLETE')) as once, \
                 patch.object(runner, 'execute') as execute, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(runner.main(['--diagnose-public-once', '--config', str(config),
                                             '--authorize-public-data', '--diagnostic-attempt', 'explicit-v2']), 0)
            self.assertIs(once.call_args.kwargs['authorized'], True)
            self.assertEqual(once.call_args.kwargs['attempt'], 'explicit-v2')
            execute.assert_not_called()

    def test_diagnostic_cli_has_no_credential_reads_ledger_or_delivery(self):
        def locale_only(key, default=None):
            if key not in {'LANGUAGE', 'LC_ALL', 'LC_MESSAGES', 'LANG', 'COLUMNS', 'LINES'}:
                raise AssertionError('credential read forbidden')
            return default
        with tempfile.TemporaryDirectory() as directory:
            config, path = self.inputs(directory)
            argv = ['--diagnose-public', '--config', str(config)]
            with patch.object(runner.os.environ, 'get', side_effect=locale_only), \
                 patch.object(fixtures.service, 'collect_snapshot', side_effect=fixtures.service.PublicDataError('PUBLIC_HTTP_FAILED_NO_RETRY')) as collect, \
                 patch.object(runner, 'execute') as execute, \
                 contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(runner.main(argv), 1)
                collect.assert_not_called()
                self.assertEqual(runner.main(argv + ['--authorize-public-data']), 1)
            reports = [json.loads(line) for line in output.getvalue().splitlines()]
            self.assertEqual(reports[0]['reason'], 'PUBLIC_READ_AUTHORIZATION_REQUIRED')
            self.assertEqual(reports[1]['reason'], 'PUBLIC_HTTP_FAILED_NO_RETRY')
            self.assertEqual(reports[1]['stage'], 'collection')
            self.assertIs(reports[1]['delivery_allowed'], False)
            collect.assert_called_once()
            execute.assert_not_called()
            self.assertFalse(path.exists())

    def inputs(self, directory):
        config = Path(directory) / 'config.json'
        config.write_text(json.dumps(fixtures.config()), encoding='utf-8')
        return config, Path(directory) / 'delivery.sqlite'

    def test_packaged_sources_are_pinned_and_config_check_has_no_credential_reads(self):
        def language_only(key, default=None):
            if key not in {'LANGUAGE', 'LC_ALL', 'LC_MESSAGES', 'LANG', 'COLUMNS', 'LINES'}:
                raise AssertionError('non-locale environment read')
            return default
        with tempfile.TemporaryDirectory() as directory:
            config, _ = self.inputs(directory)
            with patch.object(runner.os.environ, 'get', side_effect=language_only), \
                 patch.object(runner, 'execute') as execute, contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(runner.main(['--check-config', '--config', str(config)]), 0)
            execute.assert_not_called()
            self.assertEqual(json.loads(output.getvalue())['status'], 'CONFIG_VALID')

    def test_explicit_provision_never_overwrites(self):
        with tempfile.TemporaryDirectory() as directory:
            _, path = self.inputs(directory)
            runner.provision_ledger(path)
            before = path.read_bytes()
            with self.assertRaises(FileExistsError):
                runner.provision_ledger(path)
            self.assertEqual(path.read_bytes(), before)

    def test_authorization_gate_precedes_environment_reads(self):
        with patch.object(runner.os.environ, 'get', side_effect=AssertionError('no env')):
            out = runner.execute({}, {}, 'unused.sqlite')
        self.assertEqual(out['reason'], 'EXPLICIT_AUTHORIZATIONS_REQUIRED')

    def test_missing_ledger_does_not_create_or_read_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'absent.sqlite'
            with patch.object(runner.os.environ, 'get', side_effect=AssertionError('no env')):
                out = runner.execute({}, {}, path, authorized=True)
            self.assertEqual(out['status'], 'BLOCKED')
            self.assertFalse(path.exists())

    def test_only_four_telegram_keys_and_sigterm_stops_and_handlers_restored(self):
        previous = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT)}
        with tempfile.TemporaryDirectory() as directory:
            _, path = self.inputs(directory)
            runner.provision_ledger(path)
            def run(*args, **kwargs):
                self.assertFalse(kwargs['stop_event'].is_set())
                signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
                self.assertTrue(kwargs['stop_event'].is_set())
                return dict(status='STOPPED', reason='STOP_REQUESTED')
            with patch.object(runner.os.environ, 'get', return_value='FAKE') as get, \
                 patch.object(runner, 'run_service', side_effect=run):
                self.assertEqual(runner.execute({}, {}, path, authorized=True)['status'], 'STOPPED')
            self.assertEqual({c.args[0] for c in get.call_args_list},
                             {'FALCON_TOKEN', 'FALCON_CHAT_ID', 'DONKEY_H4_TOKEN', 'DONKEY_H4_CHAT_ID'})
            self.assertFalse(Path(str(path) + '.halted').exists())
        self.assertEqual({sig: signal.getsignal(sig) for sig in previous}, previous)

    def test_tracking_quote_skip_stopped_result_does_not_latch_or_exit_one(self):
        stopped = dict(status='STOPPED', reason='CYCLE_LIMIT_REACHED',
                       tracking_quote_skips=1, live_allowed=False)
        with tempfile.TemporaryDirectory() as directory:
            config, path = self.inputs(directory)
            runner.provision_ledger(path)
            with patch.object(runner.os.environ, 'get', return_value='FAKE'), \
                 patch.object(runner, 'run_service', return_value=stopped):
                self.assertEqual(runner.execute({}, {}, path, authorized=True), stopped)
            self.assertFalse(Path(str(path) + '.halted').exists())
            argv = ['--run', '--config', str(config), '--ledger', str(path),
                    '--authorize-service', '--authorize-public-data', '--authorize-telegram']
            with patch.object(runner, 'load_inputs', return_value=({}, {})), \
                 patch.object(runner, 'execute', return_value=stopped), \
                 contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(runner.main(argv), 0)
            self.assertIs(json.loads(output.getvalue())['live_allowed'], False)

    def test_failure_latches_and_platform_restart_cannot_send(self):
        with tempfile.TemporaryDirectory() as directory:
            _, path = self.inputs(directory)
            runner.provision_ledger(path)
            with patch.object(runner.os.environ, 'get', return_value='FAKE'), \
                 patch.object(runner, 'run_service', return_value=dict(status='FAILED')) as run:
                self.assertEqual(runner.execute({}, {}, path, authorized=True)['status'], 'FAILED')
                self.assertEqual(runner.execute({}, {}, path, authorized=True)['status'], 'BLOCKED')
                self.assertEqual(run.call_count, 1)
            self.assertEqual(Path(str(path) + '.halted').read_text(), 'MANUAL_REVIEW_REQUIRED\n')

    def test_public_diagnostic_survives_cli_and_latches_without_delivery(self):
        with tempfile.TemporaryDirectory() as directory:
            config, path = self.inputs(directory)
            runner.provision_ledger(path)
            argv = ['--run', '--config', str(config), '--ledger', str(path),
                    '--authorize-service', '--authorize-public-data', '--authorize-telegram']
            with patch.object(runner.os.environ, 'get', side_effect=lambda key, default=None: fixtures.fixtures.VALUES.get(key, default)), \
                 patch.object(fixtures.service, 'collect_snapshot', side_effect=fixtures.service.PublicDataError('CANDLE_GAP_OR_DUPLICATE')) as collect, \
                 patch.object(fixtures.service, 'run_once') as evaluate, \
                 contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(runner.main(argv), 1)
                self.assertEqual(runner.main(argv), 1)
            reports = [json.loads(line) for line in output.getvalue().splitlines()]
            self.assertEqual(reports[0]['reason'], 'CANDLE_GAP_OR_DUPLICATE')
            self.assertEqual(reports[-1]['reason'], 'LEDGER_OR_MANUAL_REVIEW_REQUIRED')
            self.assertTrue(all(r['live_allowed'] is False for r in reports))
            collect.assert_called_once()
            evaluate.assert_not_called()
            self.assertEqual(Path(str(path) + '.halted').read_text(), 'MANUAL_REVIEW_REQUIRED\n')

    def test_error_output_does_not_expose_exception(self):
        with patch.object(runner, 'load_inputs', side_effect=ValueError('PRIVATE_TEST_SENTINEL')), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            code = runner.main(['--check-config', '--config', 'unused.json'])
        self.assertEqual(code, 1)
        self.assertNotIn('PRIVATE_TEST_SENTINEL', output.getvalue())

    def test_no_operational_or_secret_files_in_container_copy_allowlist(self):
        root = runner.ROOT
        docker = (root / 'signals.Dockerfile').read_text()
        self.assertNotIn('COPY . ', docker)
        self.assertNotIn('main.py', docker)
        self.assertNotIn('bots/', docker)
        rules = (root / 'signals.Dockerfile.dockerignore').read_text().splitlines()
        self.assertEqual(rules[0], '**')
        self.assertFalse(any('.env' in x or 'broker' in x for x in rules))


if __name__ == '__main__':
    unittest.main()
