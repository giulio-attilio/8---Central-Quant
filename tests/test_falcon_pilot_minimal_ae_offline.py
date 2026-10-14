"""Offline A-E regressions: python -I -S tests/test_falcon_pilot_minimal_ae_offline.py.

Operational modules are parsed, never imported. All state and exchange responses
are synthetic. Network and subprocess calls raise BaseException before any
extracted production function can run.
"""

import ast
import builtins
import copy
import io
import json
import socket
import subprocess
import threading
import types
import unittest
from contextlib import nullcontext
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


class OfflineBoundaryViolation(BaseException):
    pass


def forbidden(*args, **kwargs):
    raise OfflineBoundaryViolation("network or subprocess attempted")


socket.socket = forbidden
socket.create_connection = forbidden
subprocess.Popen = forbidden
subprocess.run = forbidden

ROOT = Path(__file__).resolve().parents[1]


def isolated_functions(path, names, namespace):
    source = (ROOT / path).read_text(encoding="utf-8")
    tree = ast.parse(source)
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    assert {node.name for node in nodes} == set(names)
    safe_builtins = dict(vars(builtins), __import__=forbidden)
    namespace["__builtins__"] = safe_builtins
    module = ast.Module(body=nodes, type_ignores=[])
    exec(compile(module, str(path), "exec"), namespace)
    return tree, source


def identity_state(record, field):
    aliases = {
        "lifecycle_id": ("lifecycle_id",),
        "client_order_id": ("client_order_id",),
        "order_id": ("order_id", "broker_order_id"),
    }[field]
    meta = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    values = {str(source[alias]) for source in (record, meta) for alias in aliases if source.get(alias) not in (None, "")}
    return {"value": next(iter(values)) if len(values) == 1 else None, "conflict": len(values) > 1}


class RegistryA(unittest.TestCase):
    def setUp(self):
        self.registry = {"open_trades": {}, "closed_trades": []}
        self.saves = 0

        def load_registry():
            return copy.deepcopy(self.registry)

        def save_registry(value):
            self.registry = copy.deepcopy(value)
            self.saves += 1
            return True

        def normalize(record):
            record["registry_mode"] = record.get("metadata", {}).get("registry_mode") or record.get("registry_mode") or "PAPER"
            return record

        def identity_matches(record, expected):
            fields = [field for field in ("lifecycle_id", "client_order_id", "order_id") if expected.get(field)]
            return bool(fields) and all(identity_state(record, field)["value"] == expected[field] for field in fields), {}

        self.ns = {
            "Any": Any, "Dict": Dict, "Optional": Optional,
            "STRONG_IDENTITY_ALIASES": {field: () for field in ("lifecycle_id", "client_order_id", "order_id")},
            "strong_identity_alias_state": identity_state,
            "_identity_matches": identity_matches,
            "_normalize_symbol": lambda value: str(value).upper().replace("/", "").replace(":USDT", ""),
            "_normalize_side": lambda value: str(value).upper(),
            "_normalize_mode": lambda value: "REAL" if str(value).upper() == "LIVE" else str(value).upper(),
            "_normalize_trade_record": normalize,
            "_now": lambda: "synthetic",
            "copy": copy,
            "time": types.SimpleNamespace(time=lambda: 1.0),
            "_lock": threading.RLock(),
            "_c3_closed_repair_writer_mutation_v1": lambda _: nullcontext(),
            "load_registry": load_registry, "save_registry": save_registry,
            "_observe_shadow_registry_snapshot": lambda *args: None,
        }
        isolated_functions("trade_registry.py", ("make_trade_id", "_falcon_open_replay_matches", "register_open_trade", "update_trade"), self.ns)

    def opening(self, lifecycle, order=None, mode="LIVE"):
        return self.ns["register_open_trade"](
            bot="FALCON", symbol="BTCUSDT", side="LONG", setup="FALCON15",
            entry=100.0, qty=1.0, registry_mode="REAL" if mode == "LIVE" else "PAPER",
            execution_mode=mode, lifecycle_id=lifecycle, broker_order_id=order,
        )

    def test_distinct_lifecycle_cannot_replace_open_row(self):
        first = self.opening("L-A", "O-A")
        second = self.opening("L-B", "O-B")
        self.assertTrue(first["ok"])
        self.assertEqual(second["error"], "FALCON_OPEN_IDENTITY_COLLISION")
        self.assertEqual(self.saves, 1)
        self.assertEqual(self.registry["open_trades"][first["trade_id"]]["lifecycle_id"], "L-A")

    def test_exact_replay_is_no_write_but_missing_identity_is_not(self):
        first = self.opening("L-A", "O-A")
        replay = self.opening("L-A", "O-A")
        self.assertEqual(replay["action"], "OPEN_ALREADY_REGISTERED")
        self.assertEqual(self.saves, 1)
        self.assertEqual(self.opening(None, None)["error"], "FALCON_OPEN_IDENTITY_COLLISION")
        self.assertEqual(self.saves, 1)

    def test_new_real_row_requires_strong_identity(self):
        self.assertEqual(self.opening(None, None)["error"], "FALCON_REAL_OPEN_IDENTITY_REQUIRED")
        self.assertEqual(self.saves, 0)

    def test_management_requires_matching_identity(self):
        first = self.opening("L-A", "O-A")
        trade_id = first["trade_id"]
        update = self.ns["update_trade"]
        self.assertEqual(update(trade_id, sl=99)["error"], "FALCON_REAL_UPDATE_IDENTITY_REQUIRED")
        self.assertEqual(update(trade_id, expected_identity={"lifecycle_id": "L-B"}, sl=99)["error"], "FALCON_REAL_UPDATE_IDENTITY_MISMATCH")
        self.assertEqual(update(trade_id, expected_identity={"lifecycle_id": "L-A"}, lifecycle_id="L-B")["error"], "FALCON_REAL_UPDATE_IDENTITY_CHANGE")
        self.assertEqual(self.saves, 1)
        self.assertTrue(update(trade_id, expected_identity={"lifecycle_id": "L-A"}, sl=99)["ok"])
        self.assertEqual(self.registry["open_trades"][trade_id]["sl"], 99)

    def test_existing_lifecycle_can_gain_ack_ids_but_not_replace_them(self):
        first = self.opening("L-A")
        trade_id = first["trade_id"]
        update = self.ns["update_trade"]
        self.assertTrue(update(trade_id, lifecycle_id="L-A", order_id="O-A", client_order_id="C-A")["ok"])
        self.assertEqual(update(trade_id, expected_identity={"lifecycle_id": "L-A"}, order_id="O-B")["error"], "FALCON_REAL_UPDATE_IDENTITY_CHANGE")
        self.assertEqual(self.registry["open_trades"][trade_id]["order_id"], "O-A")


class PolicyB(unittest.TestCase):
    def policy(self, manager=None, sync=None, priority=None):
        ns = {
            "EXECUTIVE_POLICY_MANAGER_LOADED": manager is not None,
            "EXECUTIVE_POLICY_MANAGER_ERROR": "synthetic missing",
            "executive_policy_manager": manager,
            "_ensure_executive_policy_manager_synced_for_risk": lambda force=False: sync if sync is not None else {"ok": True},
            "resolve_executive_policy_priority": lambda **kwargs: priority if priority is not None else {"ok": True, "allowed": True},
            "extract_policy_decision_link": lambda *args: {},
            "_executive_policy_for_can_open_trade": lambda: {"ok": False, "available": False, "error": "synthetic missing"},
        }
        isolated_functions("main.py", ("_apply_executive_policy_to_risk_reasons",), ns)
        return ns["_apply_executive_policy_to_risk_reasons"]

    def evaluate(self, function, mode="LIVE", reduce_only=False):
        reasons, warnings = [], []
        result = function({"bot": "FALCON", "mode": mode, "intended_live": mode == "LIVE", "reduce_only": reduce_only, "side": "LONG"}, reasons, warnings)
        return result, reasons

    def test_manager_missing_denies_falcon_live(self):
        result, reasons = self.evaluate(self.policy())
        self.assertIs(result["allowed"], False)
        self.assertIn("FALCON_LIVE_EXECUTIVE_POLICY_MANAGER_UNAVAILABLE", reasons)

    def test_invalid_manager_or_sync_denies_falcon_live(self):
        for response, sync in (({}, {"ok": True}), ({"ok": True, "allowed": True}, {"ok": False})):
            manager = types.SimpleNamespace(evaluate_trade_against_policies=lambda _: response)
            result, reasons = self.evaluate(self.policy(manager=manager, sync=sync))
            self.assertIs(result["allowed"], False)
            self.assertTrue(reasons)

    def test_denial_without_reason_and_invalid_priority_cannot_allow(self):
        manager = types.SimpleNamespace(evaluate_trade_against_policies=lambda _: {"ok": True, "allowed": False, "reasons": []})
        result, reasons = self.evaluate(self.policy(manager=manager))
        self.assertIs(result["allowed"], False)
        self.assertIn("FALCON_LIVE_EXECUTIVE_POLICY_DENIED_WITHOUT_REASON", reasons)
        manager.evaluate_trade_against_policies = lambda _: {"ok": True, "allowed": True}
        result, reasons = self.evaluate(self.policy(manager=manager, priority={"ok": False, "allowed": True}))
        self.assertIs(result["allowed"], False)
        self.assertIn("FALCON_LIVE_EXECUTIVE_POLICY_PRIORITY_UNAVAILABLE", reasons)
        result, reasons = self.evaluate(self.policy(manager=manager, priority={"ok": True, "allowed": False, "reasons": []}))
        self.assertIs(result["allowed"], False)
        self.assertIn("FALCON_LIVE_EXECUTIVE_POLICY_PRIORITY_DENIED_WITHOUT_REASON", reasons)


class ExchangeC(unittest.TestCase):
    def setUp(self):
        ns = {"BINGX_MARGIN_MODE": "isolated"}
        tree, _ = isolated_functions("broker.py", ("_confirm_entry_margin_and_leverage",), ns)
        place = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "place_market_order")
        setup_try = next(node for node in ast.walk(place) if isinstance(node, ast.Try) and any(
            isinstance(statement, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "setup_confirmation" for target in statement.targets)
            for statement in node.body
        ))
        prefix = []
        for statement in setup_try.body:
            prefix.append(statement)
            if isinstance(statement, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "entry_create_result" for target in statement.targets):
                break
        assert isinstance(prefix[-1], ast.Assign)
        probe = ast.FunctionDef(
            name="pre_send_probe",
            args=ast.arguments(posonlyargs=[], args=[], vararg=None, kwonlyargs=[], kw_defaults=[], kwarg=None, defaults=[]),
            body=prefix + [ast.Return(value=ast.Name(id="entry_create_result", ctx=ast.Load()))],
            decorator_list=[],
        )
        ast.fix_missing_locations(probe)
        exec(compile(ast.Module(body=[probe], type_ignores=[]), "broker-pre-send-fragment", "exec"), ns)
        self.ns = ns

    def probe(self, margin_mode, leverage_value, setup_error=False, reduce_only=False):
        calls = []

        class Exchange:
            def set_margin_mode(self, *args):
                if setup_error:
                    raise RuntimeError("synthetic margin error")

            def set_leverage(self, *args):
                if setup_error:
                    raise RuntimeError("synthetic leverage error")

            def fetch_margin_mode(self, symbol):
                return {"marginMode": margin_mode}

            def fetch_leverage(self, symbol):
                return {"longLeverage": leverage_value}

        ns = self.ns
        ns.update({
            "ex": Exchange(), "sym": "BTC/USDT:USDT", "lev": 2, "position_side": "LONG",
            "reduce_only": reduce_only,
            "order_side": "buy", "amount": 0.01, "params": {}, "entry_send_state": {},
            "client_order_id_reservation": "synthetic", "ROLE_ENTRY": "ENTRY",
            "client_order_id_reservation_verifier": lambda *args: True,
            "_create_order_with_reserved_attempt": lambda *args, **kwargs: calls.append("create") or {"ok": True},
            "log_execution_event": lambda *args: None,
            "log_execution_audit_event": lambda *args: None,
            "margin": 10, "planned_exposure": 20,
        })
        return ns["pre_send_probe"](), calls

    def test_setup_error_with_unknown_readback_never_sends(self):
        result, calls = self.probe(None, None, setup_error=True)
        self.assertEqual(result["status"], "BROKER_ENTRY_SETUP_UNCONFIRMED")
        self.assertEqual(calls, [])

    def test_wrong_leverage_never_sends(self):
        result, calls = self.probe("isolated", 3)
        self.assertEqual(result["status"], "BROKER_ENTRY_SETUP_UNCONFIRMED")
        self.assertEqual(calls, [])

    def test_wrong_margin_mode_never_sends(self):
        result, calls = self.probe("cross", 2)
        self.assertEqual(result["status"], "BROKER_ENTRY_SETUP_UNCONFIRMED")
        self.assertEqual(calls, [])

    def test_factual_readback_permits_one_send_even_if_set_said_already_configured(self):
        result, calls = self.probe("isolated", 2, setup_error=True)
        self.assertTrue(result["ok"])
        self.assertEqual(calls, ["create"])

    def test_reduce_only_does_not_depend_on_entry_setup_readback(self):
        result, calls = self.probe(None, None, setup_error=True, reduce_only=True)
        self.assertTrue(result["ok"])
        self.assertEqual(calls, ["create"])

    def test_one_way_requires_both_sides_confirmed_and_sets_both(self):
        class Exchange:
            def __init__(self, short_leverage):
                self.short_leverage = short_leverage
                self.set_sides = []

            def set_margin_mode(self, *_args):
                return None

            def set_leverage(self, _leverage, _symbol, params):
                self.set_sides.append(params["side"])

            def fetch_margin_mode(self, _symbol):
                return {"marginMode": "isolated"}

            def fetch_leverage(self, _symbol):
                return {"longLeverage": 2, "shortLeverage": self.short_leverage}

        mismatched = Exchange(3)
        result = self.ns["_confirm_entry_margin_and_leverage"](mismatched, "BTC/USDT:USDT", 2, None)
        self.assertIs(result["ok"], False)
        self.assertEqual(mismatched.set_sides, ["BOTH"])
        matched = Exchange(2)
        result = self.ns["_confirm_entry_margin_and_leverage"](matched, "BTC/USDT:USDT", 2, None)
        self.assertIs(result["ok"], True)
        self.assertEqual(matched.set_sides, ["BOTH"])


class ExposureD(unittest.TestCase):
    def test_paper_does_not_veto_falcon_live_but_live_does(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        base = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "can_open_trade_decision")
        selected = [node for node in base.body if isinstance(node, ast.If) and (
            ast.get_source_segment(source, node).startswith("if symbol:\n")
            or ast.get_source_segment(source, node).startswith('if side in {"LONG", "BUY"}:')
        )]
        assert len(selected) == 2
        code = compile(ast.Module(body=selected, type_ignores=[]), "risk-exposure-fragment", "exec")
        paper = [{"symbol": "BTCUSDT", "bot": "FALCON", "side": "LONG"}]
        base_ns = {
            "symbol": "BTCUSDT", "side": "LONG", "bot": "FALCON",
            "rows": paper, "total_pos": 1, "long_pos": 1, "short_pos": 0,
            "live_total_pos": 0, "live_long_pos": 0, "live_short_pos": 0,
            "paper_total_after": 2, "live_total_after": 1,
            "GLOBAL_RISK_MAX_SYMBOL_EXPOSURE": 1,
            "GLOBAL_RISK_MAX_SIDE_CONCENTRATION_PCT": 85,
            "normalize_symbol_for_risk": lambda value: value,
        }
        ns = dict(base_ns, intended_live=True, live_rows=[], reasons=[])
        exec(code, ns)
        self.assertEqual(ns["reasons"], [])
        ns = dict(base_ns, intended_live=True, live_rows=paper, live_total_pos=1, live_long_pos=1, live_total_after=2, reasons=[])
        exec(code, ns)
        self.assertTrue(any("LIVE" in reason or "já possui exposição" in reason for reason in ns["reasons"]))
        ns = dict(base_ns, intended_live=False, live_rows=[], reasons=[])
        exec(code, ns)
        self.assertTrue(any("Central/PAPER" in reason for reason in ns["reasons"]))


class WatchlistE(unittest.TestCase):
    def run_watchlist(self, mode, exists, content="[]"):
        health = {}
        ns = {
            "WATCHLIST_FILE": "synthetic/falcon.json", "FALCON_MODE": mode,
            "HEALTH": health, "json": json,
            "os": types.SimpleNamespace(path=types.SimpleNamespace(exists=lambda _: exists)),
            "open": lambda *args, **kwargs: io.StringIO(content),
            "data_hora_sp_str": lambda: "synthetic",
        }
        isolated_functions("bots/falcon.py", ("load_watchlist",), ns)
        return ns["load_watchlist"](), health

    def test_live_missing_or_invalid_file_never_uses_default(self):
        for exists, content in ((False, "[]"), (True, "[]"), (True, "not-json")):
            symbols, health = self.run_watchlist("LIVE", exists, content)
            self.assertEqual(symbols, [])
            self.assertIs(health["watchlist_fallback_used"], False)
            self.assertTrue(health["watchlist_error"])

    def test_live_uses_only_explicit_file_and_reports_source(self):
        symbols, health = self.run_watchlist("LIVE", True, '["BTC/USDT:USDT"]')
        self.assertEqual(symbols, ["BTCUSDT"])
        self.assertEqual(health["watchlist_source"], "synthetic/falcon.json")
        self.assertIs(health["watchlist_fallback_used"], False)

    def test_paper_legacy_fallback_remains(self):
        symbols, health = self.run_watchlist("PAPER", False)
        self.assertEqual(len(symbols), 5)
        self.assertIs(health["watchlist_fallback_used"], True)


if __name__ == "__main__":
    unittest.main()
