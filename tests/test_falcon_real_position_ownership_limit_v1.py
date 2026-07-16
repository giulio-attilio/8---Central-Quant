from __future__ import annotations

import ast
import copy
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
BROKER = ROOT / "broker.py"
FALCON = ROOT / "bots" / "falcon.py"
VERSION = "2026-07-16-FALCON-REAL-POSITION-OWNERSHIP-LIMIT-V1"
_POLICY = None
_BROKER_VALIDATORS = {}


def _functions(path: Path, names: set[str], namespace: dict) -> dict:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    latest = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names:
            latest[node.name] = copy.deepcopy(node)
    assert set(latest) == names, f"missing functions in {path}: {sorted(names - set(latest))}"
    module = ast.Module(body=sorted(latest.values(), key=lambda item: item.lineno), type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, str(path), "exec"), namespace)
    return namespace


def _norm_symbol(value):
    return str(value or "").upper().replace("/USDT:USDT", "USDT").replace("/USDT", "USDT").replace(":USDT", "").replace("-", "").replace("/", "")


def _norm_side(value):
    side = str(value or "").upper().strip()
    return {"BUY": "LONG", "SELL": "SHORT"}.get(side, side)


def _main_policy():
    global _POLICY
    if _POLICY is not None:
        return _POLICY
    namespace = {
        "FALCON_REAL_POSITION_OWNERSHIP_LIMIT_V1_VERSION": VERSION,
        "_rpg_safe_norm_symbol": _norm_symbol,
        "_rpg_safe_norm_side": _norm_side,
        "_rpg_safe_norm_bot": lambda value: str(value or "").upper().strip(),
        "_rpg_safe_int": lambda value, default=None: default if value in (None, "") else int(float(value)),
        "_rpg_safe_now": lambda: "2026-07-16T12:00:00-03:00",
        "time": SimpleNamespace(time=lambda: 1_784_225_600.0),
    }
    _POLICY = _functions(
        MAIN,
        {"_frpol_v1_identity", "_frpol_v1_position_key", "_frpol_v1_evaluate"},
        namespace,
    )["_frpol_v1_evaluate"]
    return _POLICY


def _evaluate(*, symbol="SOLUSDT", side="LONG", central=None, broker=None, audit=None, registry=None, errors=None):
    return _main_policy()(
        {"bot": "FALCON", "symbol": symbol, "side": side},
        central or [],
        broker or [],
        {"ok": True, "live_audit_status": "OK"} if audit is None else audit,
        {"ok": True, "unknown_open_count": 0, "status": "READY"} if registry is None else registry,
        max_positions=1,
        errors=errors,
    )


def _manual_btc_long(**updates):
    row = {"symbol": "BTCUSDT", "side": "LONG", "position_side": "LONG", "contracts": 0.01}
    row.update(updates)
    return row


def _falcon_live(**updates):
    row = {
        "bot": "FALCON",
        "trade_id": "TR-FALCON-1",
        "lifecycle_id": "LC-FALCON-1",
        "order_id": "ORDER-FALCON-1",
        "symbol": "BTCUSDT",
        "side": "LONG",
        "execution_mode": "LIVE",
    }
    row.update(updates)
    return row


def test_manual_btc_long_does_not_block_falcon_sol_long():
    for symbol, side in (
        ("SOLUSDT", "LONG"),
        ("SOLUSDT", "SHORT"),
        ("XRPUSDT", "LONG"),
        ("XRPUSDT", "SHORT"),
    ):
        result = _evaluate(symbol=symbol, side=side, broker=[_manual_btc_long()])

        assert result["allowed"] is True
        assert result["status"] == "allowed_with_external_manual_position"
        assert result["falcon_owned_limit_count"] == 0
        assert result["manual_external_ignored_for_falcon_own_limit"] is True


def test_manual_btc_long_does_not_block_falcon_xrp_short():
    result = _evaluate(symbol="XRPUSDT", side="SHORT", broker=[_manual_btc_long()])

    assert result["allowed"] is True
    assert result["reason_codes"] == []


def test_manual_btc_long_blocks_falcon_btc_long_with_explicit_reason():
    result = _evaluate(symbol="BTCUSDT", side="LONG", broker=[_manual_btc_long()])

    assert result["allowed"] is False
    assert result["status"] == "blocked_by_manual_same_symbol_side"
    assert "MANUAL_EXTERNAL_SAME_SYMBOL_SIDE_BLOCK" in result["reason_codes"]


def test_same_symbol_opposite_side_is_allowed_only_with_explicit_hedge_side():
    hedged = _evaluate(symbol="BTCUSDT", side="SHORT", broker=[_manual_btc_long(position_side="LONG")])
    ambiguous = _evaluate(symbol="BTCUSDT", side="SHORT", broker=[_manual_btc_long(position_side="BOTH")])

    assert hedged["allowed"] is True
    assert ambiguous["allowed"] is False
    assert "MANUAL_EXTERNAL_SAME_SYMBOL_MODE_AMBIGUOUS_BLOCK" in ambiguous["reason_codes"]


def test_confirmed_own_falcon_live_position_reaches_own_limit():
    position = _falcon_live()
    result = _evaluate(central=[position], broker=[{"symbol": "BTCUSDT", "side": "LONG", "contracts": 1}])

    assert result["allowed"] is False
    assert result["status"] == "blocked_by_own_falcon_limit"
    assert result["falcon_owned_limit_count"] == 1
    assert "FALCON_OWN_POSITION_LIMIT_REACHED" in result["reason_codes"]


def test_other_central_bot_does_not_consume_falcon_own_limit():
    other = _falcon_live(bot="TURTLE", trade_id="TR-TURTLE")
    result = _evaluate(central=[other], broker=[{"symbol": "BTCUSDT", "side": "LONG", "contracts": 1}])

    assert result["allowed"] is True
    assert result["central_other_bots_open_count"] == 1
    assert result["falcon_owned_limit_count"] == 0


def test_falcon_central_only_pending_blocks():
    position = _falcon_live(central_only_reconcile_required=True)
    result = _evaluate(central=[position], broker=[])

    assert result["allowed"] is False
    assert result["status"] == "blocked_by_central_only_pending"
    assert "FALCON_CENTRAL_ONLY_PENDING" in result["reason_codes"]


def test_uncertain_falcon_ownership_blocks_fail_closed():
    uncertain = {"bot": "FALCON", "symbol": "BTCUSDT", "side": "LONG", "execution_mode": "LIVE"}
    result = _evaluate(central=[uncertain], broker=[{"symbol": "BTCUSDT", "side": "LONG", "contracts": 1}])

    assert result["allowed"] is False
    assert result["status"] == "blocked_by_ownership_uncertainty"
    assert "FALCON_OWNERSHIP_UNCERTAIN" in result["reason_codes"]


def test_audit_or_registry_uncertainty_blocks():
    audit_block = _evaluate(audit={"ok": False, "live_audit_status": "BLOCKED"})
    registry_block = _evaluate(registry={"ok": False, "unknown_open_count": 1})

    assert "FALCON_AUDIT_NOT_OK" in audit_block["reason_codes"]
    assert "OWNERSHIP_REGISTRY_NOT_OK" in registry_block["reason_codes"]


def test_no_positions_allows_and_does_not_emit_stale_aggregate_warning():
    result = _evaluate()

    assert result["allowed"] is True
    assert result["status"] == "allowed_no_open_positions"
    assert "Limite de posições reais atingido" not in str(result)


def test_health_overlay_exposes_current_classification_not_stale_warning():
    current = _evaluate(symbol="SOLUSDT", side="LONG", broker=[_manual_btc_long()])
    namespace = {
        "FALCON_REAL_POSITION_OWNERSHIP_LIMIT_V1_VERSION": VERSION,
        "_frpol_v1_collect": lambda _payload: {"falcon_real_position_ownership_limit_v1": current},
    }
    overlay = _functions(MAIN, {"_frpol_v1_health_overlay"}, namespace)["_frpol_v1_health_overlay"]()

    assert overlay["falcon_real_position_ownership_limit_status"] == "allowed_with_external_manual_position"
    assert overlay["falcon_real_position_ownership_limit_active_block"] is False
    assert overlay["falcon_manual_external_ignored_for_own_limit"] is True
    assert "Limite de posições reais atingido" not in str(overlay)


def test_bots_health_clears_only_stale_aggregate_limit_warning():
    current = _evaluate(symbol="SOLUSDT", side="LONG", broker=[_manual_btc_long()])
    original = lambda _key, _cfg: {
        "health": {
            "last_warning": "execução bloqueada: ordem rejeitada: Limite de posições reais atingido ou não confirmado: 1 / 1",
        }
    }
    namespace = {
        "_ORIGINAL_BOT_HEALTH_FOR_PREDATOR_AUTO_CLOSED_SYNC_V1": original,
        "_frpol_v1_health_overlay": lambda: {
            "falcon_real_position_ownership_limit_status": current["status"],
            "falcon_real_position_ownership_limit_allowed": current["allowed"],
        },
    }
    bot_health = _functions(MAIN, {"bot_health"}, namespace)["bot_health"]

    payload = bot_health("FALCON", {"name": "Falcon"})

    assert payload["health"]["last_warning"] is None
    assert payload["health"]["falcon_position_ownership_stale_warning_cleared"] is True
    assert payload["falcon_real_position_ownership_limit_status"] == "allowed_with_external_manual_position"


def _broker_validator(now=1_784_225_600.0):
    if now in _BROKER_VALIDATORS:
        return _BROKER_VALIDATORS[now]
    namespace = {
        "FALCON_REAL_POSITION_OWNERSHIP_LIMIT_V1_VERSION": VERSION,
        "FALCON_OWNERSHIP_EVIDENCE_MAX_AGE_SECONDS": 30.0,
        "time": SimpleNamespace(time=lambda: now),
    }
    validator = _functions(
        BROKER,
        {"_broker_rpg_v1_norm_symbol", "_broker_rpg_v1_norm_side", "_broker_validate_falcon_ownership_limit"},
        namespace,
    )["_broker_validate_falcon_ownership_limit"]
    _BROKER_VALIDATORS[now] = validator
    return validator


def test_broker_preflight_accepts_fresh_manual_external_ownership_evidence():
    evidence = _evaluate(symbol="SOLUSDT", side="LONG", broker=[_manual_btc_long()])
    snapshot = {"ok": True, "count": 1, "open_items": [{"symbol": "BTC/USDT:USDT", "side": "long"}]}

    result = _broker_validator()(evidence, symbol="SOLUSDT", side="LONG", position_snapshot=snapshot, max_positions=1)

    assert result["allowed"] is True
    assert result["falcon_owned_limit_count"] == 0
    assert result["manual_external_ignored_for_falcon_own_limit"] is True


def test_broker_preflight_blocks_stale_or_changed_ownership_evidence():
    evidence = _evaluate(symbol="SOLUSDT", side="LONG", broker=[_manual_btc_long()])
    evidence["generated_epoch"] -= 60
    snapshot = {"ok": True, "count": 0, "open_items": []}

    result = _broker_validator()(evidence, symbol="SOLUSDT", side="LONG", position_snapshot=snapshot, max_positions=1)

    assert result["allowed"] is False
    assert any("expired" in reason for reason in result["reasons"])
    assert any("changed" in reason for reason in result["reasons"])


def test_falcon_evidence_gate_is_pure_and_blocks_missing_evidence_before_broker():
    namespace = {
        "FALCON_REAL_POSITION_OWNERSHIP_LIMIT_V1_VERSION": VERSION,
        "FALCON_OWNERSHIP_EVIDENCE_MAX_AGE_SECONDS": 30.0,
        "normalize_symbol_for_central": _norm_symbol,
        "time": SimpleNamespace(time=lambda: 1_784_225_600.0),
    }
    validator = _functions(FALCON, {"falcon_validate_position_ownership_limit_evidence"}, namespace)["falcon_validate_position_ownership_limit_evidence"]

    missing = validator({"allowed": True}, {"symbol": "SOLUSDT", "side": "LONG"})
    valid_evidence = _evaluate(symbol="SOLUSDT", side="LONG", broker=[_manual_btc_long()])
    valid = validator({"falcon_real_position_ownership_limit_v1": valid_evidence}, {"symbol": "SOLUSDT", "side": "LONG"}, now_epoch=valid_evidence["generated_epoch"])

    assert missing["ok"] is False
    assert missing["status"] == "FALCON_OWNERSHIP_EVIDENCE_MISSING"
    assert valid["ok"] is True


def test_policy_is_read_only_and_contains_no_order_or_broker_calls():
    source = MAIN.read_text(encoding="utf-8")
    tree = ast.parse(source)
    node = next(item for item in tree.body if isinstance(item, ast.FunctionDef) and item.name == "_frpol_v1_evaluate")
    calls = {item.func.attr for item in ast.walk(node) if isinstance(item, ast.Call) and isinstance(item.func, ast.Attribute)}
    names = {item.func.id for item in ast.walk(node) if isinstance(item, ast.Call) and isinstance(item.func, ast.Name)}

    forbidden = {"place_market_order", "create_order", "cancel_order", "close_position_market", "get_positions"}
    assert not (calls | names) & forbidden


def test_engine_and_orchestrator_are_not_referenced_by_the_new_policy():
    combined = "\n".join(path.read_text(encoding="utf-8") for path in (MAIN, BROKER, FALCON))
    marker = "FALCON_REAL_POSITION_OWNERSHIP_LIMIT_V1_VERSION"
    snippets = [line for line in combined.splitlines() if marker in line or "falcon_position_ownership_limit" in line]

    assert all("execution_engine" not in line and "execution_orchestrator" not in line for line in snippets)
