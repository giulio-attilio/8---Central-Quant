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
            self.assertEqual(reports[1]['reason'], 'LEDGER_OR_MANUAL_REVIEW_REQUIRED')
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
