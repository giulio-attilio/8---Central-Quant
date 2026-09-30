"""AST-isolated tests: never import the operational Central or bots."""
import ast
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


def deny_external(event, args):
    if event.startswith(('socket.', 'subprocess.', 'os.system')):
        raise AssertionError('External execution prohibited')


sys.addaudithook(deny_external)
ROOT = Path(__file__).resolve().parents[1]


def extract(path, name, namespace):
    tree = ast.parse((ROOT / path).read_text(encoding='utf-8-sig'))
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name]
    assert len(nodes) == 1
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), namespace)
    return namespace[name]


class ReceiverHandoffTests(unittest.TestCase):
    def test_donkey_route_disabled_even_if_override_enabled(self):
        calls = []
        fn = extract('main.py', 'central_route_enabled_for_bot', {
            'COMMAND_ROUTER_DEFAULTS': {},
            'env_bool': lambda *a, **kw: calls.append(a) or True})
        for key in ('DONKEY', 'donkey'):
            self.assertFalse(fn(key))
        self.assertEqual(calls, [])
        self.assertTrue(fn('FALCON'))
        self.assertEqual(calls, [('CENTRAL_ROUTE_FALCON_TELEGRAM',)])

    def test_direct_donkey_router_returns_before_credentials_or_http(self):
        messages = []
        fn = extract('main.py', 'central_command_router_loop', {'print': messages.append})
        fn('DONKEY', {})  # No os, requests or operational dependencies available.
        self.assertIn('DONKEY_TELEGRAM_RECEIVER_DISABLED', messages[0])

    def test_only_scanner_and_watchdog_threads_remain(self):
        started, boot, messages = [], [], []
        def thread(**kwargs):
            return SimpleNamespace(start=lambda: started.append(kwargs))
        scanner, watchdog, guarded = object(), object(), object()
        fn = extract('bots/donkey.py', 'iniciar_threads_monitoradas', {
            'registrar_boot': lambda: boot.append(True),
            'threading': SimpleNamespace(Thread=thread), 'print': messages.append,
            'run_thread_guarded': guarded, 'scanner': scanner, 'watchdog_loop': watchdog})
        fn()
        self.assertEqual(boot, [True])
        self.assertEqual([x['args'] for x in started], [('scanner', scanner), ('watchdog', watchdog)])
        self.assertTrue(all(x['target'] is guarded and x['daemon'] for x in started))
        self.assertIn('DONKEY_TELEGRAM_RECEIVER_DISABLED', messages[0])


if __name__ == '__main__':
    unittest.main()
