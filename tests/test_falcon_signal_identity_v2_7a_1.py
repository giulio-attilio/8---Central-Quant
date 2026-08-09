from __future__ import annotations

import ast
import copy
from pathlib import Path

import pytest

from falcon_signal_identity import (
    FALCON_SIGNAL_IDENTITY_VERSION,
    FALCON_SIGNAL_ID_PREFIX,
    FalconSignalIdentityConstructionError,
    attach_falcon_signal_identity,
    canonical_falcon_signal_identity_material,
)


ROOT = Path(__file__).resolve().parents[1]
FALCON_SOURCE = ROOT / "bots" / "falcon.py"
HELPER_SOURCE = ROOT / "falcon_signal_identity.py"


def _signal(**overrides):
    signal = {
        "id": "FALCON15:BTCUSDT:LONG:2026-08-09",
        "bot": "Falcon Strike ORB PRO",
        "setup": "FALCON15",
        "setup_label": "Falcon 15",
        "symbol": "BTCUSDT",
        "side": "LONG",
        "direction": "BUY",
        "entry": 101.25,
        "initial_stop": 97.75,
        "stop": 97.75,
        "tp50": 104.75,
        "range_high": 100.0,
        "range_low": 98.0,
        "range_minutes": 15,
        "range_start_ny": "09:30",
        "range_end_ny": "09:45",
        "ny_date": "2026-08-09",
        "timeframe": "15m",
        "signal_ts": 1786281300000,
        "created_at": "09/08/2026 10:01",
        "status": "OPEN",
    }
    signal.update(overrides)
    return signal


def _birth_facts(**overrides):
    facts = {
        "closed_candle_ts": 1786281300000,
        "closed_candle_high": 102.0,
        "closed_candle_low": 99.0,
        "closed_candle_close": 101.25,
        "orb_range_high": 100.0,
        "orb_range_low": 98.0,
        "orb_range_minutes": 15,
        "orb_range_start_ny": "09:30",
        "orb_range_end_ny": "09:45",
    }
    facts.update(overrides)
    return facts


def _expected_v1_signal(created_at):
    return {
        "id": "FALCON15:BTCUSDT:LONG:2026-08-09",
        "bot": "Falcon Strike ORB PRO",
        "setup": "FALCON15",
        "setup_label": "Falcon 15",
        "symbol": "BTCUSDT",
        "side": "LONG",
        "direction": "BUY",
        "entry": 101.25,
        "initial_stop": 97.8,
        "stop": 97.8,
        "tp50": 104.7,
        "atr": 2.0,
        "atr_pct": 1.9753086419753085,
        "risk_pct": 1.0,
        "score_falcon": 80,
        "quality": "HIGH",
        "volume_rel": 1.5,
        "adx": 20.0,
        "breakout_atr": 0.625,
        "range_atr": 1.0,
        "range_high": 100.0,
        "range_low": 98.0,
        "range_minutes": 15,
        "range_start_ny": "09:30",
        "range_end_ny": "09:45",
        "ny_date": "2026-08-09",
        "timeframe": "15m",
        "signal_ts": 1786281300000,
        "signal_dt": "2026-08-09T14:15:00+00:00",
        "created_at": created_at,
        "status": "OPEN",
        "tp50_hit": False,
        "be_moved": False,
        "trailing_active": False,
        "mfe_pct": 0.0,
        "mae_pct": 0.0,
        "mfe_r": 0.0,
        "mae_r": 0.0,
        "best_price": 101.25,
        "worst_price": 101.25,
        "management_cycles": 0,
        "candles_to_tp50": None,
        "opened_candle_ts": 1786281300000,
    }


def _load_analyze_symbol_setup(namespace):
    tree = ast.parse(FALCON_SOURCE.read_text(encoding="utf-8"), filename=str(FALCON_SOURCE))
    nodes = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "analyze_symbol_setup"
    ]
    assert len(nodes) == 1
    module = ast.Module(body=[copy.deepcopy(nodes[0])], type_ignores=[])
    ast.fix_missing_locations(module)
    values = dict(namespace)
    exec(compile(module, str(FALCON_SOURCE), "exec"), values)
    return values["analyze_symbol_setup"], values


class _Row(dict):
    pass


class _ILoc:
    def __init__(self, row):
        self.row = row

    def __getitem__(self, index):
        assert index == -1
        return self.row


class _Frame:
    def __init__(self, row):
        self.iloc = _ILoc(row)


def _productive_analyze(*, created_at, identity_attachment=attach_falcon_signal_identity):
    row = _Row(
        {
            "high": 102.0,
            "low": 99.0,
            "close": 101.25,
            "atr": 2.0,
            "adx": 20.0,
            "volume_rel": 1.5,
            "ts": 1786281300000,
            "dt": "2026-08-09T14:15:00+00:00",
        }
    )
    frame = _Frame(row)
    namespace = {
        "add_indicators": lambda _closed: frame,
        "funnel_inc": lambda *_args: None,
        "is_trade_window": lambda _row, _minutes: True,
        "get_orb_range": lambda _df, _minutes: {
            "ny_date": "2026-08-09",
            "range_high": 100.0,
            "range_low": 98.0,
            "range_start_ny": "09:30",
            "range_end_ny": "09:45",
        },
        "safe_float": lambda value, default=0.0: default if value is None else float(value),
        "MIN_ATR_PCT": 0.2,
        "MIN_RANGE_ATR": 0.4,
        "MAX_RANGE_ATR": 4.0,
        "MIN_VOLUME_REL_TO_SIGNAL": 1.1,
        "MIN_ADX_TO_SIGNAL": 12.0,
        "passes_alignment": lambda _symbol, _side: True,
        "STOP_ATR_BUFFER": 0.1,
        "TP50_R": 1.0,
        "risk_pct": lambda _entry, _stop: 1.0,
        "MAX_RISK_PCT": 3.0,
        "calc_falcon_score": lambda *_args: (80, 0.625, 1.0),
        "SCORE_MIN_QUALITY_TO_SIGNAL": 55,
        "quality_from_score": lambda _score: "HIGH",
        "position_id": lambda symbol, setup, side, ny_date: f"{setup}:{symbol}:{side}:{ny_date}",
        "BOT_NAME": "Falcon Strike ORB PRO",
        "TIMEFRAME": "15m",
        "data_hora_sp_str": lambda: created_at,
        "attach_falcon_signal_identity": identity_attachment,
        "FalconSignalIdentityConstructionError": FalconSignalIdentityConstructionError,
    }
    analyze, _ = _load_analyze_symbol_setup(namespace)
    return analyze("BTCUSDT", "FALCON15", {"label": "Falcon 15", "range_minutes": 15}, [None] * 80)


def test_productive_signal_birth_attaches_only_additive_identity_fields():
    signal = _productive_analyze(created_at="09/08/2026 10:01")

    expected_v1 = _expected_v1_signal("09/08/2026 10:01")
    assert {key: signal[key] for key in expected_v1} == expected_v1
    assert set(signal) == set(expected_v1) | {
        "signal_id",
        "signal_identity_version",
        "signal_identity_provenance",
    }
    assert signal["id"] == "FALCON15:BTCUSDT:LONG:2026-08-09"
    assert signal["signal_id"].startswith(FALCON_SIGNAL_ID_PREFIX)
    assert signal["signal_id"] != signal["id"]
    assert signal["signal_identity_version"] == FALCON_SIGNAL_IDENTITY_VERSION
    provenance = signal["signal_identity_provenance"]
    assert provenance["issuer_function"] == "analyze_symbol_setup"
    assert provenance["factual_signal_birth_basis"] == "FALCON_ORB_CLOSED_CANDLE_BREAKOUT"
    assert provenance["canonical_material_sha256"] == signal["signal_id"].split(":", 1)[1]
    assert provenance["legacy_signal_id_equivalence"] == "NOT_ASSUMED"
    assert provenance["plan_provenance"] == {
        "plan_origin": "CENTRAL_FALCON_PRODUCTIVE_SIGNAL",
        "plan_owner_type": "CENTRAL",
        "ownership_scope": "PLAN_ONLY_NOT_BROKER_POSITION_OWNERSHIP",
        "explicit_owner_type_preserved": None,
    }


def test_identity_construction_failure_returns_the_exact_v1_signal_without_io():
    attachment_calls = []

    def reject_identity(signal, *, birth_facts):
        attachment_calls.append((dict(signal), dict(birth_facts)))
        raise FalconSignalIdentityConstructionError("closed candle facts unavailable")

    failed = _productive_analyze(
        created_at="09/08/2026 10:01",
        identity_attachment=reject_identity,
    )
    expected_v1 = _expected_v1_signal("09/08/2026 10:01")

    assert failed == expected_v1
    assert attachment_calls == [
        (
            expected_v1,
            {
                "closed_candle_ts": 1786281300000,
                "closed_candle_high": 102.0,
                "closed_candle_low": 99.0,
                "closed_candle_close": 101.25,
                "orb_range_high": 100.0,
                "orb_range_low": 98.0,
                "orb_range_minutes": 15,
                "orb_range_start_ny": "09:30",
                "orb_range_end_ny": "09:45",
            },
        )
    ]
    for field in (
        "signal_id",
        "signal_identity_version",
        "signal_identity_provenance",
        "execution_id",
        "lifecycle_id",
        "decision_request_id",
        "decision_id",
    ):
        assert field not in failed


def test_identity_seam_does_not_swallow_unrelated_programming_errors():
    def unexpected_error(_signal, *, birth_facts):
        raise RuntimeError("unrelated test failure")

    with pytest.raises(RuntimeError, match="unrelated test failure"):
        _productive_analyze(
            created_at="09/08/2026 10:01",
            identity_attachment=unexpected_error,
        )


def test_same_factual_signal_retry_is_stable_even_when_created_at_changes():
    first = _productive_analyze(created_at="09/08/2026 10:01")
    retry = _productive_analyze(created_at="09/08/2026 10:02")

    assert first["created_at"] != retry["created_at"]
    assert first["signal_id"] == retry["signal_id"]


def test_reconstructed_signal_object_is_stable_without_object_identity():
    first = attach_falcon_signal_identity(_signal(), birth_facts=_birth_facts())
    reconstructed = attach_falcon_signal_identity(
        copy.deepcopy(_signal()), birth_facts=copy.deepcopy(_birth_facts())
    )

    assert first["signal_id"] == reconstructed["signal_id"]
    assert first["signal_identity_provenance"] == reconstructed["signal_identity_provenance"]


def test_legitimate_same_day_reentry_is_distinct_from_coarse_legacy_grouping():
    first = attach_falcon_signal_identity(_signal(), birth_facts=_birth_facts())
    reentry = attach_falcon_signal_identity(
        _signal(created_at="09/08/2026 11:31"),
        birth_facts=_birth_facts(
            closed_candle_ts=1786282200000,
            closed_candle_high=103.0,
            closed_candle_low=100.5,
            closed_candle_close=102.5,
        ),
    )

    assert first["id"] == reentry["id"]
    assert first["setup"] == reentry["setup"]
    assert first["symbol"] == reentry["symbol"]
    assert first["side"] == reentry["side"]
    assert first["ny_date"] == reentry["ny_date"]
    assert first["signal_id"] != reentry["signal_id"]


def test_material_conflict_generates_a_distinct_factual_signal_id():
    first = attach_falcon_signal_identity(_signal(), birth_facts=_birth_facts())
    changed_material = attach_falcon_signal_identity(
        _signal(), birth_facts=_birth_facts(orb_range_high=100.25)
    )

    assert first["signal_id"] != changed_material["signal_id"]
    with pytest.raises(ValueError, match="conflicts with factual birth material"):
        attach_falcon_signal_identity(
            first, birth_facts=_birth_facts(orb_range_high=100.25)
        )


def test_canonical_numeric_and_timestamp_inputs_are_deterministic_and_strict():
    baseline = canonical_falcon_signal_identity_material(
        _signal(), birth_facts=_birth_facts()
    )
    integer_numeric_equivalent = canonical_falcon_signal_identity_material(
        _signal(),
        birth_facts=_birth_facts(
            closed_candle_high=102,
            closed_candle_low=99,
            orb_range_high=100,
            orb_range_low=98,
        ),
    )
    timestamp_text_equivalent = canonical_falcon_signal_identity_material(
        _signal(), birth_facts=_birth_facts(closed_candle_ts="1786281300000")
    )
    positive_zero = canonical_falcon_signal_identity_material(
        _signal(), birth_facts=_birth_facts(closed_candle_low=0)
    )
    negative_zero = canonical_falcon_signal_identity_material(
        _signal(), birth_facts=_birth_facts(closed_candle_low=-0.0)
    )

    assert baseline == integer_numeric_equivalent
    assert baseline == timestamp_text_equivalent
    assert positive_zero == negative_zero
    for non_finite in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(FalconSignalIdentityConstructionError):
            canonical_falcon_signal_identity_material(
                _signal(), birth_facts=_birth_facts(closed_candle_high=non_finite)
            )

    helper_text = HELPER_SOURCE.read_text(encoding="utf-8")
    assert "locale" not in helper_text
    assert "repr(" not in helper_text


def test_legacy_id_and_broker_facts_do_not_participate_in_signal_identity():
    baseline = attach_falcon_signal_identity(_signal(), birth_facts=_birth_facts())
    altered = attach_falcon_signal_identity(
        _signal(
            id="FALCON15:BTCUSDT:LONG:LEGACY-CHANGED",
            broker_order_id="BROKER-1",
            exchange_order_id="EXCHANGE-1",
            fill_id="FILL-1",
            client_order_id="CLIENT-1",
            live_order={"order_id": "BROKER-1"},
        ),
        birth_facts=_birth_facts(),
    )

    assert baseline["signal_id"] == altered["signal_id"]
    material = canonical_falcon_signal_identity_material(
        altered, birth_facts=_birth_facts()
    )
    assert "broker_order_id" not in repr(material)
    assert "exchange_order_id" not in repr(material)
    assert "fill_id" not in repr(material)
    assert "client_order_id" not in repr(material)


@pytest.mark.parametrize(
    ("fields", "expected_value", "expected_source"),
    [
        ({"positionSide": "SHORT", "position_side": "LONG", "side": "LONG"}, "SHORT", "positionSide"),
        ({"positionSide": "", "position_side": "SHORT", "side": "LONG"}, "SHORT", "position_side"),
        ({"positionSide": None, "position_side": "", "side": "LONG"}, "LONG", "side"),
    ],
)
def test_position_side_uses_exact_existing_v1_precedence(fields, expected_value, expected_source):
    result = attach_falcon_signal_identity(_signal(**fields), birth_facts=_birth_facts())
    provenance = result["signal_identity_provenance"]["position_side"]

    assert provenance["selected_value"] == expected_value
    assert provenance["selected_source"] == expected_source


def test_position_side_conflict_and_both_net_are_preserved_without_conversion():
    result = attach_falcon_signal_identity(
        _signal(positionSide="BOTH", position_side="NET", side="LONG"),
        birth_facts=_birth_facts(),
    )
    provenance = result["signal_identity_provenance"]["position_side"]

    assert result["positionSide"] == "BOTH"
    assert result["position_side"] == "NET"
    assert provenance["raw_positionSide"] == "BOTH"
    assert provenance["raw_position_side"] == "NET"
    assert provenance["explicit_position_side_conflict"] is True
    assert provenance["selected_value"] == "BOTH"
    assert provenance["selected_value"] != "LONG"


def test_external_owner_evidence_is_never_overwritten_or_adopted():
    original = _signal(owner_type="MANUAL_EXTERNAL", external_position=True)
    result = attach_falcon_signal_identity(original, birth_facts=_birth_facts())
    plan = result["signal_identity_provenance"]["plan_provenance"]

    assert result["owner_type"] == "MANUAL_EXTERNAL"
    assert result["external_position"] is True
    assert plan["plan_origin"] == "EXTERNAL_OWNER_EVIDENCE_PRESERVED"
    assert plan["plan_owner_type"] is None
    assert plan["explicit_owner_type_preserved"] == "MANUAL_EXTERNAL"
    assert plan["ownership_scope"] == "PLAN_ONLY_NOT_BROKER_POSITION_OWNERSHIP"


def test_preexisting_fields_are_unchanged_and_no_disallowed_identity_is_created():
    original = _signal(positionSide="LONG", position_side="LONG")
    before = copy.deepcopy(original)
    result = attach_falcon_signal_identity(original, birth_facts=_birth_facts())

    assert original == before
    assert {key: result[key] for key in before} == before
    for field in (
        "execution_id",
        "lifecycle_id",
        "client_order_id",
        "broker_order_id",
        "exchange_order_id",
        "fill_id",
        "decision_request_id",
        "decision_id",
    ):
        assert field not in result


def test_scanner_treats_one_closed_candle_as_one_signal_birth_attempt():
    falcon_tree = ast.parse(FALCON_SOURCE.read_text(encoding="utf-8"), filename=str(FALCON_SOURCE))
    functions = {
        node.name: node
        for node in falcon_tree.body
        if isinstance(node, ast.FunctionDef)
    }
    scanner_source = ast.get_source_segment(
        FALCON_SOURCE.read_text(encoding="utf-8"), functions["scanner_loop"]
    )
    open_position_source = ast.get_source_segment(
        FALCON_SOURCE.read_text(encoding="utf-8"),
        functions["has_open_position_for_symbol"],
    )
    daily_guard_source = ast.get_source_segment(
        FALCON_SOURCE.read_text(encoding="utf-8"), functions["had_trade_today"]
    )

    assert "symbol_last_closed_ts = int(closed.iloc[-1][\"ts\"])" in scanner_source
    assert "int(last_candles.get(symbol, 0) or 0) == symbol_last_closed_ts" in scanner_source
    assert "last_candles[symbol] = symbol_last_closed_ts" in scanner_source
    assert "save_last_candles_by_symbol(last_candles)" in scanner_source
    assert "has_open_position_for_symbol(positions, symbol, setup_key, sig[\"side\"])" in scanner_source
    assert "had_trade_today(symbol, sig[\"ny_date\"])" in scanner_source
    assert "for p in positions.values()" in open_position_source
    assert "if not ONE_TRADE_PER_SYMBOL_PER_DAY" in daily_guard_source
    assert "for s in get_signals()" in daily_guard_source
    assert "for t in get_trades()" in daily_guard_source


def test_helper_is_pure_and_productive_seam_has_one_additive_attachment_only():
    helper_tree = ast.parse(HELPER_SOURCE.read_text(encoding="utf-8"), filename=str(HELPER_SOURCE))
    imported_modules = {
        alias.name.split(".", 1)[0]
        for node in ast.walk(helper_tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported_modules.update(
        (node.module or "").split(".", 1)[0]
        for node in ast.walk(helper_tree)
        if isinstance(node, ast.ImportFrom)
    )
    assert imported_modules <= {"__future__", "decimal", "hashlib", "json", "typing"}

    forbidden_calls = {
        "open", "connect", "request", "get", "post", "put", "delete", "write",
        "write_text", "write_bytes", "mkdir", "touch", "rename", "replace", "unlink",
    }
    calls = [
        node.func.id
        for node in ast.walk(helper_tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    ]
    assert forbidden_calls.isdisjoint(calls)
    helper_text = HELPER_SOURCE.read_text(encoding="utf-8")
    for forbidden_name in ("execution_id", "lifecycle_id", "decision_request_id", "decision_id"):
        assert forbidden_name not in helper_text

    falcon_tree = ast.parse(FALCON_SOURCE.read_text(encoding="utf-8"), filename=str(FALCON_SOURCE))
    analyzer = [
        node
        for node in falcon_tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "analyze_symbol_setup"
    ]
    assert len(analyzer) == 1
    attachment_calls = [
        node
        for node in ast.walk(falcon_tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "attach_falcon_signal_identity"
    ]
    assert len(attachment_calls) == 1
    assert attachment_calls[0] in set(ast.walk(analyzer[0]))
    identity_handlers = [
        handler
        for node in ast.walk(analyzer[0])
        if isinstance(node, ast.Try)
        for handler in node.handlers
    ]
    assert len(identity_handlers) == 1
    assert isinstance(identity_handlers[0].type, ast.Name)
    assert identity_handlers[0].type.id == "FalconSignalIdentityConstructionError"
    analyzer_call_names = {
        node.func.id
        for node in ast.walk(analyzer[0])
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert {
        "register_falcon_trade_registry_open",
        "redis_set_json",
        "redis_list_append",
        "save_positions",
        "safe_send_telegram",
        "execute_signal_if_allowed",
        "open",
    }.isdisjoint(analyzer_call_names)
    keyword_names = {
        node.value
        for node in ast.walk(attachment_calls[0])
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert {
        "closed_candle_ts",
        "closed_candle_high",
        "closed_candle_low",
        "closed_candle_close",
        "orb_range_high",
        "orb_range_low",
    } <= keyword_names
    assert "falcon_registry_v2_verify_shadow" not in FALCON_SOURCE.read_text(encoding="utf-8")
