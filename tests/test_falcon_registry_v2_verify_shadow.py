from __future__ import annotations

import ast
import copy
import runpy
from pathlib import Path

import pytest

import falcon_registry_v2_verify_shadow as shadow
from falcon_registry_v2_verify_shadow import (
    IDENTITY_CONFLICT,
    IDENTITY_HISTORICAL_ONLY,
    IDENTITY_INCOMPLETE,
    IDENTITY_UNAVAILABLE,
    NOT_APPLICABLE,
    OBSERVED,
    SHADOW_STAGE_POST_DECISION,
    SHADOW_STAGE_PRE_DECISION,
    FalconRegistryV2VerifyShadowInput,
    FalconRegistryV2VerifyShadowObservationError,
    observe_falcon_registry_v2_verify_shadow,
)
from falcon_registry_v2_verify_shadow_runtime_adapter import (
    FALCON_REGISTRY_V2_VERIFY_SHADOW_ENABLED_DEFAULT,
    RUNTIME_SHADOW_DISABLED,
    RUNTIME_SHADOW_INELIGIBLE,
    RUNTIME_SHADOW_OBSERVER_ERROR,
    FalconRegistryV2VerifyShadowRuntimeAdapter,
)


ROOT = Path(__file__).resolve().parents[1]
SHADOW_SOURCE = ROOT / "falcon_registry_v2_verify_shadow.py"
ADAPTER_SOURCE = ROOT / "falcon_registry_v2_verify_shadow_runtime_adapter.py"


def _signal(**updates):
    value = {
        "bot": "FALCON",
        "setup": "FALCON15",
        "symbol": "BTCUSDT",
        "side": "LONG",
        "signal_id": "FALCON-SIGNAL-V2.7A.1:signal-a",
        "signal_identity_version": "V2.7A.1",
        "signal_identity_provenance": {
            "identity_version": "V2.7A.1",
            "position_side": {
                "selected_value": "LONG",
                "selected_source": "side",
                "raw_positionSide": None,
                "raw_position_side": None,
                "raw_side": "LONG",
                "explicit_position_side_conflict": False,
            },
            "plan_provenance": {
                "plan_origin": "CENTRAL_FALCON_PRODUCTIVE_SIGNAL",
                "plan_owner_type": "CENTRAL",
                "ownership_scope": "PLAN_ONLY_NOT_BROKER_POSITION_OWNERSHIP",
            },
        },
        "decision_request_id": "FALCON-DECISION-REQUEST-V2.7A.2:request-a",
        "decision_request_identity_version": "V2.7A.2",
        "decision_request_identity_provenance": {
            "identity_version": "V2.7A.2",
            "signal_id": "FALCON-SIGNAL-V2.7A.1:signal-a",
            "issuer_file": "bots/falcon.py",
            "issuer_function": "central_can_open_trade",
            "mechanism": "SECRETS_TOKEN_URLSAFE",
            "signal_correlation_method": "EXACT_SIGNAL_ID",
        },
    }
    value.update(updates)
    return value


def _decision(signal, **updates):
    value = {
        "allowed": True,
        "decision": "ALLOW",
        "decision_request_id": signal["decision_request_id"],
        "decision_id": "FALCON-DECISION-V2.7A.2:decision-a",
        "decision_identity_version": "V2.7A.2",
        "decision_identity_provenance": {
            "identity_version": "V2.7A.2",
            "request_id": signal["decision_request_id"],
            "signal_id": signal["signal_id"],
            "mechanism": "SECRETS_TOKEN_URLSAFE_AFTER_TERMINAL_RESULT",
        },
        "decision_identity_v2_7a_2": {
            "status": "COMPLETED",
            "identity_available": True,
            "decision_request_id": signal["decision_request_id"],
            "signal_id": signal["signal_id"],
        },
    }
    value.update(updates)
    return value


def _pre(signal):
    return observe_falcon_registry_v2_verify_shadow(
        {
            "shadow_stage": SHADOW_STAGE_PRE_DECISION,
            "execution_mode": "VERIFY",
            "signal": signal,
        }
    )


def _post(signal, decision, paired_pre=None, **updates):
    payload = {
        "shadow_stage": SHADOW_STAGE_POST_DECISION,
        "execution_mode": "VERIFY",
        "signal": signal,
        "decision": decision,
        "paired_pre": _pre(signal) if paired_pre is None else paired_pre,
    }
    payload.update(updates)
    return observe_falcon_registry_v2_verify_shadow(payload)


def test_pre_decision_observes_factual_signal_and_request_without_decision_id():
    signal = _signal()
    before = copy.deepcopy(signal)

    result = _pre(signal)

    assert result.ok is True
    assert result.status == OBSERVED
    assert result.projection.shadow_stage == SHADOW_STAGE_PRE_DECISION
    assert result.projection.signal_id == signal["signal_id"]
    assert result.projection.decision_request_id == signal["decision_request_id"]
    assert result.projection.decision_id is None
    assert result.projection.decision_identity_status == NOT_APPLICABLE
    assert signal == before


def test_pre_decision_missing_signal_is_reported_not_generated():
    signal = _signal()
    signal.pop("signal_id")

    result = _pre(signal)

    assert result.status == IDENTITY_UNAVAILABLE
    assert result.projection.signal_id is None
    assert result.projection.signal_identity_status == IDENTITY_UNAVAILABLE
    assert result.projection.decision_request_identity_status == IDENTITY_UNAVAILABLE
    assert "signal_id" not in signal
    assert result.projection.execution_id is None
    assert result.projection.lifecycle_id is None


def test_pre_decision_missing_request_is_reported_not_generated():
    signal = _signal()
    signal.pop("decision_request_id")

    result = _pre(signal)

    assert result.status == IDENTITY_UNAVAILABLE
    assert result.projection.decision_request_id is None
    assert result.projection.decision_request_identity_status == IDENTITY_UNAVAILABLE
    assert "decision_request_id" not in signal


def test_request_provenance_is_incomplete_only_when_signal_and_request_exist():
    signal = _signal()
    signal.pop("decision_request_identity_version")

    result = _pre(signal)

    assert result.status == IDENTITY_INCOMPLETE
    assert result.projection.signal_identity_status == OBSERVED
    assert result.projection.decision_request_identity_status == IDENTITY_INCOMPLETE


def test_post_decision_observes_exact_factual_v27a_lineage():
    signal = _signal()
    decision = _decision(signal)

    result = _post(signal, decision)

    assert result.ok is True
    assert result.status == OBSERVED
    assert result.projection.signal_id == signal["signal_id"]
    assert result.projection.decision_request_id == signal["decision_request_id"]
    assert result.projection.decision_id == decision["decision_id"]


def test_post_decision_missing_or_incomplete_identity_is_not_repaired():
    signal = _signal()
    missing = _post(signal, {})
    incomplete = _post(
        signal,
        {
            "decision_identity_v2_7a_2": {
                "status": "IDENTITY_REQUEST_INCOMPLETE",
                "identity_available": False,
            }
        },
    )

    assert missing.status == IDENTITY_UNAVAILABLE
    assert missing.projection.decision_id is None
    assert incomplete.status == IDENTITY_INCOMPLETE
    assert incomplete.projection.decision_id is None
    assert "decision_id" not in signal


@pytest.mark.parametrize(
    ("mutate", "expected_diagnostic"),
    (
        (
            lambda decision: decision["decision_identity_provenance"].update(
                {"signal_id": "FALCON-SIGNAL-V2.7A.1:other"}
            ),
            "decision_signal_id:IDENTITY_CONFLICT",
        ),
        (
            lambda decision: decision.update(
                {"decision_request_id": "FALCON-DECISION-REQUEST-V2.7A.2:other"}
            ),
            "decision_request_response:IDENTITY_CONFLICT",
        ),
        (
            lambda decision: decision["decision_identity_v2_7a_2"].update(
                {"decision_id": "FALCON-DECISION-V2.7A.2:other"}
            ),
            "decision_id:IDENTITY_CONFLICT",
        ),
    ),
)
def test_post_decision_identity_mismatches_are_conflicts(mutate, expected_diagnostic):
    signal = _signal()
    decision = _decision(signal)
    mutate(decision)

    result = _post(signal, decision)

    assert result.status == IDENTITY_CONFLICT
    assert expected_diagnostic in result.diagnostics
    assert result.projection.decision_id == "FALCON-DECISION-V2.7A.2:decision-a"


def test_post_decision_requires_the_same_observed_pre_plan():
    signal = _signal()
    pre = _pre(signal)
    changed = copy.deepcopy(signal)
    changed["symbol"] = "ETHUSDT"

    result = _post(changed, _decision(changed), paired_pre=pre)

    assert result.status == IDENTITY_CONFLICT
    assert "paired_pre_symbol:IDENTITY_CONFLICT" in result.diagnostics


def test_historical_only_identity_never_qualifies_as_current_post_decision():
    signal = _signal()
    decision = {
        "decision_identity_v2_7a_2": {
            "status": "IDENTITY_REPLAY_HISTORICAL_ONLY",
            "historical": {"decision_id": "old-decision"},
        }
    }

    result = _post(signal, decision)

    assert result.status == IDENTITY_HISTORICAL_ONLY
    assert result.ok is False
    assert result.projection.decision_id is None


def test_verify_never_projects_or_creates_physical_execution_identity():
    signal = _signal(execution_id="not-allowed", lifecycle_id="also-not-allowed")
    result = _pre(signal)

    assert result.status == IDENTITY_CONFLICT
    assert result.projection.execution_id is None
    assert result.projection.lifecycle_id is None
    assert result.projection.shadow_identity_operational is False


def test_logical_trade_id_is_diagnostic_only_not_identity_fallback():
    signal = _signal(logical_trade_id="FALCON:FALCON15:BTCUSDT:LONG")
    signal.pop("signal_id")
    signal.pop("decision_request_id")

    result = _pre(signal)

    assert result.status == IDENTITY_UNAVAILABLE
    assert result.projection.logical_trade_id == "FALCON:FALCON15:BTCUSDT:LONG"
    assert result.projection.execution_id is None
    assert result.projection.lifecycle_id is None


@pytest.mark.parametrize(
    ("updates", "selected", "source"),
    (
        (
            {"positionSide": "BOTH", "position_side": "NET"},
            "BOTH",
            "positionSide",
        ),
        ({"positionSide": None, "position_side": "NET"}, "NET", "position_side"),
        ({"positionSide": None, "position_side": None}, "LONG", "side"),
    ),
)
def test_position_side_precedence_preserves_raw_values(updates, selected, source):
    signal = _signal(**updates)

    result = _pre(signal)

    assert result.projection.position_side == selected
    assert result.projection.position_side_source == source
    assert result.projection.raw_positionSide == updates.get("positionSide")
    assert result.projection.raw_position_side == updates.get("position_side")
    assert result.projection.raw_side == "LONG"


def test_position_side_conflict_and_both_net_are_visible_without_normalization():
    result = _pre(_signal(positionSide="BOTH", position_side="NET"))

    assert result.status == OBSERVED
    assert result.projection.position_side == "BOTH"
    assert result.projection.raw_position_side == "NET"
    assert result.projection.raw_position_side_conflict is True


@pytest.mark.parametrize("owner_type", ("MANUAL_EXTERNAL", "EXTERNAL"))
def test_external_owner_evidence_is_preserved_without_adoption(owner_type):
    result = _pre(_signal(owner_type=owner_type))

    assert result.status == OBSERVED
    assert result.projection.owner_type == owner_type
    assert result.projection.owner_status == "EXTERNAL_PRESERVED"
    assert result.projection.central_plan_provenance is False


def test_central_provenance_is_plan_only_not_broker_position_ownership():
    result = _pre(_signal())

    assert result.projection.owner_status == "CENTRAL_PLAN_ONLY"
    assert result.projection.central_plan_provenance is True
    assert result.projection.ownership_scope == "PLAN_ONLY_NOT_BROKER_POSITION_OWNERSHIP"


def test_repeated_observation_is_deterministic_and_input_is_unchanged():
    signal = _signal(positionSide="BOTH", position_side="NET")
    decision = _decision(signal)
    before_signal = copy.deepcopy(signal)
    before_decision = copy.deepcopy(decision)

    first = _post(signal, decision)
    second = _post(signal, decision)

    assert first == second
    assert signal == before_signal
    assert decision == before_decision


def test_dataclass_input_is_supported_without_identity_synthesis():
    signal = _signal()
    result = observe_falcon_registry_v2_verify_shadow(
        FalconRegistryV2VerifyShadowInput(
            shadow_stage=SHADOW_STAGE_PRE_DECISION,
            execution_mode="VERIFY",
            signal=signal,
        )
    )

    assert result.status == OBSERVED
    assert result.projection.decision_id is None
    assert result.projection.execution_id is None


def test_runtime_adapter_is_off_by_default_and_has_no_verify_activation():
    calls = []

    def observer(payload):
        calls.append(payload)
        return observe_falcon_registry_v2_verify_shadow(payload)

    adapter = FalconRegistryV2VerifyShadowRuntimeAdapter(observer=observer)
    facts = {
        "shadow_stage": SHADOW_STAGE_PRE_DECISION,
        "execution_mode": "VERIFY",
        "signal": _signal(),
    }

    disabled = adapter.observe(facts)
    observed = adapter.observe(facts, enabled=True)
    non_verify = adapter.observe({**facts, "execution_mode": "PAPER"}, enabled=True)

    assert FALCON_REGISTRY_V2_VERIFY_SHADOW_ENABLED_DEFAULT is False
    assert disabled.status == RUNTIME_SHADOW_DISABLED
    assert calls == [facts]
    assert observed.status == OBSERVED
    assert non_verify.status == RUNTIME_SHADOW_INELIGIBLE


def test_runtime_adapter_isolates_only_the_dedicated_observer_error():
    def expected_failure(payload):
        del payload
        raise FalconRegistryV2VerifyShadowObservationError("projection fixture")

    diagnostic = FalconRegistryV2VerifyShadowRuntimeAdapter(
        observer=expected_failure
    ).observe(
        {
            "shadow_stage": SHADOW_STAGE_PRE_DECISION,
            "execution_mode": "VERIFY",
            "signal": _signal(),
        },
        enabled=True,
    )

    assert diagnostic.status == RUNTIME_SHADOW_OBSERVER_ERROR
    assert diagnostic.execution_id is None
    assert diagnostic.lifecycle_id is None


def test_shadow_modules_have_no_io_broker_registry_or_store_management_dependency():
    forbidden_modules = {
        "broker",
        "requests",
        "redis",
        "decision_identity_store",
        "trade_registry",
        "registry_v2_wal",
        "os",
        "pathlib",
        "socket",
    }
    forbidden_calls = {
        "open",
        "write",
        "write_text",
        "write_bytes",
        "mkdir",
        "touch",
        "rename",
        "replace",
        "unlink",
        "claim",
        "complete",
    }
    forbidden_store_text = (
        "DecisionIdentityRecordStore",
        "set_decision_identity_record_store_for_tests",
        ".claim(",
        ".complete(",
    )
    for path in (SHADOW_SOURCE, ADAPTER_SOURCE):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        imported = {
            alias.name.split(".", 1)[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imported.update(
            (node.module or "").split(".", 1)[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        )
        calls = {
            node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, (ast.Attribute, ast.Name))
        }
        assert not imported.intersection(forbidden_modules)
        assert not calls.intersection(forbidden_calls)
        assert all(fragment not in source for fragment in forbidden_store_text)


def test_shadow_module_execution_creates_no_files_or_directories(tmp_path, monkeypatch):
    before = tuple(tmp_path.iterdir())
    monkeypatch.chdir(tmp_path)

    runpy.run_path(str(SHADOW_SOURCE))
    runpy.run_path(str(ADAPTER_SOURCE))

    assert tuple(tmp_path.iterdir()) == before


def test_shadow_source_has_no_identity_generators_or_operational_aliases():
    source = SHADOW_SOURCE.read_text(encoding="utf-8")

    for forbidden in ("uuid", "token_urlsafe", "secrets", "hashlib", "execution_id=", "lifecycle_id="):
        assert forbidden not in source
    assert "logical_trade_id" in source
