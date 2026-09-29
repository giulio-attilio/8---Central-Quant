"""Run directly with python -I -B; no pytest discovery or operational imports."""
import ast
import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def guard(event, args):
    if event.startswith(("socket.", "subprocess.", "os.exec", "os.spawn")) or event in ("os.system", "os.startfile"):
        raise AssertionError("External execution/network forbidden")
    if event == "open":
        name = str(args[0]).lower()
        if ".env" in name or any(x in name for x in ("credentials", "secrets", ".pem")):
            raise AssertionError("Sensitive file forbidden")


sys.addaudithook(guard)  # Installed before any repository code is loaded.
source = ROOT / "falcon_advisory_preview.py"
tree = ast.parse(source.read_text(encoding="utf-8"))
for node in ast.walk(tree):
    if isinstance(node, ast.Import):
        assert all(alias.name in {"math", "re"} for alias in node.names)
    if isinstance(node, ast.ImportFrom):
        raise AssertionError("Unexpected import")
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        assert node.func.id not in {"open", "exec", "eval", "compile", "__import__"}
spec = importlib.util.spec_from_file_location("advisory_preview", source)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PreviewTests(unittest.TestCase):
    def fixture(self, **changes):
        return dict(synthetic=True, signal_id="fixture:1", symbol="TESTUSDT",
                    setup="FALCON15", timeframe="15m", side="LONG", entry=100,
                    stop=95, tp50=105, candle_closed_at_ms=1000,
                    generated_at_ms=1100, invalidated=False, **changes)

    def run_preview(self, signal=None, **changes):
        args = dict(now_ms=1200, expires_at_ms=1500,
                    validity_basis="synthetic fixture only; not a production TTL")
        args.update(changes)
        return module.preview_signal(self.fixture() if signal is None else signal, **args)

    def test_preview_not_authorization(self):
        out = self.run_preview()
        self.assertEqual(out["status"], "OFFLINE_PREVIEW")
        for key in ("live_allowed", "delivery_allowed", "source_qualified", "manual_trade_authorized"):
            self.assertIs(out[key], False)
        self.assertIn("NÃO OPERAR", out["message"])

    def test_rejections(self):
        for field, value, reason in (
            ("synthetic", False, "SYNTHETIC_FIXTURE_REQUIRED"),
            ("signal_id", "bad\ntext", "INVALID_IDENTIFIER"),
            ("setup", "OTHER", "INVALID_SETUP"),
            ("side", "BUY", "INVALID_SIDE"),
            ("invalidated", True, "INVALIDATED_OR_UNKNOWN"),
            ("invalidated", None, "INVALIDATED_OR_UNKNOWN"),
            ("entry", float("nan"), "INVALID_PRICE"),
            ("entry", float("inf"), "INVALID_PRICE"),
            ("entry", True, "INVALID_PRICE"),
            ("stop", 0, "INVALID_PRICE"),
            ("stop", 100, "INVALID_PRICE_ORDER"),
            ("tp50", 99, "INVALID_PRICE_ORDER"),
            ("candle_closed_at_ms", 1150, "INCONSISTENT_TIME"),
            ("generated_at_ms", 1300, "INCONSISTENT_TIME"),
            ("generated_at_ms", True, "INVALID_TIME"),
        ):
            with self.subTest(field=field, value=value):
                sig = self.fixture()
                sig[field] = value
                out = self.run_preview(sig)
                self.assertEqual(out["reason"], reason)
                self.assertIsNone(out["message"])

    def test_expiry_boundaries_and_missing_policy(self):
        self.assertEqual(self.run_preview(now_ms=1499)["status"], "OFFLINE_PREVIEW")
        self.assertEqual(self.run_preview(now_ms=1500)["reason"], "EXPIRED")
        self.assertEqual(self.run_preview(now_ms=1501)["reason"], "EXPIRED")
        self.assertEqual(self.run_preview(validity_basis="")["reason"], "EXPLICIT_VALIDITY_BASIS_REQUIRED")
        self.assertEqual(self.run_preview(expires_at_ms=None)["reason"], "INVALID_TIME")

    def test_duplicate_context_and_short(self):
        self.assertEqual(self.run_preview(seen_ids=("fixture:1",))["reason"], "DUPLICATE")
        self.assertEqual(self.run_preview(seen_ids="fixture:1")["reason"], "INVALID_DUPLICATE_CONTEXT")
        sig = self.fixture()
        sig.update(side="SHORT", stop=105, tp50=95)
        self.assertEqual(self.run_preview(sig)["status"], "OFFLINE_PREVIEW")

    def test_no_mutation_or_operational_field_leak(self):
        sig = self.fixture()
        sig.update(status="OPEN", live_allowed=True, account="SYNTHETIC_PRIVATE",
                   risk_pct=99, live_order_id="FAKE_ORDER", quantity=999)
        before = dict(sig)
        out = self.run_preview(sig)
        self.assertEqual(sig, before)
        self.assertNotIn("SYNTHETIC_PRIVATE", str(out))
        self.assertNotIn("FAKE_ORDER", str(out))
        self.assertNotIn("risk_pct", str(out))
        self.assertIs(out["live_allowed"], False)

    def test_missing_fields(self):
        for key in self.fixture():
            sig = self.fixture()
            del sig[key]
            with self.subTest(key=key):
                self.assertEqual(self.run_preview(sig)["status"], "REJECTED")

    def test_operational_modules_not_loaded(self):
        for name in ("bots.falcon", "main", "broker", "execution_engine", "exchange_manager", "trade_registry"):
            self.assertNotIn(name, sys.modules)

    def test_guards_are_active_without_external_attempts(self):
        for event in ("socket.connect", "subprocess.Popen", "os.system"):
            with self.subTest(event=event), self.assertRaises(AssertionError):
                sys.audit(event, "synthetic guard probe")
        with self.assertRaises(AssertionError):
            sys.audit("open", "synthetic.env", "r", 0)


if __name__ == "__main__":
    unittest.main()
