from __future__ import annotations

import ast
import copy
import json
import multiprocessing
import os
from pathlib import Path
import subprocess
import sys
import threading

import pytest

import decision_identity_store as identity
from decision_identity_store import (
    DECISION_IDENTITY_VERSION,
    DECISION_ID_PREFIX,
    DECISION_REQUEST_DIGEST_VERSION,
    DECISION_REQUEST_IDENTITY_VERSION,
    DECISION_REQUEST_ID_PREFIX,
    DecisionIdentityConstructionError,
    DecisionIdentityRecordStore,
    DecisionIdentityStoreCorruptionError,
    canonical_decision_request,
    decision_request_from_payload,
    ensure_decision_request_identity,
    evaluate_current_decision_with_identity,
)


ROOT = Path(__file__).resolve().parents[1]
FALCON_SOURCE = ROOT / "bots" / "falcon.py"
MAIN_SOURCE = ROOT / "main.py"
STORE_SOURCE = ROOT / "decision_identity_store.py"
_PROVIDER_PROVENANCE = {
    "provider_file": "main.py",
    "provider_function": "can_open_trade_decision",
    "provider_version": "V2.7A.2",
    "completed_decision_boundary": "TEST_FINAL_PROVIDER",
}


def _payload(
    *, signal_id: str = "FALCON-SIGNAL-V2.7A.1:exact-signal-a", **overrides
) -> dict:
    payload = {
        "bot": "FALCON",
        "symbol": "BTCUSDT",
        "side": "LONG",
        "setup": "FALCON15",
        "mode": "VERIFY",
        "intended_live": False,
        "signal_id": signal_id,
        "risk_pct": 0.5,
        "notional_usdt": 25.0,
        "entry": 101.25,
        "stop": 99.75,
        "tp50": 102.75,
        "material_policy": {"max_positions": 3, "reduce_only": False},
    }
    payload.update(overrides)
    issued = ensure_decision_request_identity({"signal_id": payload["signal_id"]})
    payload.update(
        {
            field: issued[field]
            for field in (
                "decision_request_id",
                "decision_request_identity_version",
                "decision_request_identity_provenance",
            )
        }
    )
    return payload


def _request_and_canonical(payload: dict) -> tuple[dict, dict]:
    return decision_request_from_payload(payload), canonical_decision_request(payload)


def _v1_result(payload: dict, *, allowed: bool) -> dict:
    return {
        "allowed": allowed,
        "decision": "ALLOW" if allowed else "DENY",
        "reasons": ["V1 current provider reason"],
        "warnings": [],
        "risk_pct": payload["risk_pct"],
        "notional_usdt": payload["notional_usdt"],
        "policy_directive": {
            "max_positions": payload["material_policy"]["max_positions"],
            "reduce_only": payload["material_policy"]["reduce_only"],
        },
    }


def _current_provider(expected: dict, calls: list):
    def provider(payload):
        calls.append(copy.deepcopy(payload))
        return copy.deepcopy(expected)

    return provider


def _same_request_with_signal(payload: dict, signal_id: str) -> dict:
    changed = _payload(signal_id=signal_id)
    changed.update(
        {
            "decision_request_id": payload["decision_request_id"],
            "decision_request_identity_version": payload[
                "decision_request_identity_version"
            ],
            "decision_request_identity_provenance": {
                **payload["decision_request_identity_provenance"],
                "signal_id": signal_id,
            },
        }
    )
    return changed


def _cross_process_claim_worker(path_text: str, payload: dict, queue) -> None:
    """Module-level target so Windows spawn can exercise the real file lock."""

    try:
        store = DecisionIdentityRecordStore(path_text)
        request, canonical = _request_and_canonical(payload)
        result = store.claim(
            request,
            canonical,
            issuer_provider_provenance=_PROVIDER_PROVENANCE,
        )
        queue.put(("ok", result["status"]))
    except BaseException as exc:  # pragma: no cover - child diagnostic path
        queue.put(("error", type(exc).__name__, str(exc)))


def _load_function(path: Path, name: str, namespace: dict, *, latest: bool = False):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    nodes = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    ]
    assert nodes, f"{name} not found in {path}"
    node = copy.deepcopy(nodes[-1] if latest else nodes[0])
    node.decorator_list = []
    module = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(module)
    values = dict(namespace)
    exec(compile(module, str(path), "exec"), values)
    return values[name]


def test_request_id_is_random_opaque_versioned_and_explicit_transport_is_stable():
    signal = {"signal_id": "FALCON-SIGNAL-V2.7A.1:exact-signal-a"}
    first = ensure_decision_request_identity(signal)
    second = ensure_decision_request_identity(signal)

    assert signal == {"signal_id": "FALCON-SIGNAL-V2.7A.1:exact-signal-a"}
    assert first["decision_request_id"].startswith(DECISION_REQUEST_ID_PREFIX)
    assert second["decision_request_id"].startswith(DECISION_REQUEST_ID_PREFIX)
    assert first["decision_request_id"] != second["decision_request_id"]
    assert first["decision_request_identity_version"] == DECISION_REQUEST_IDENTITY_VERSION
    assert first["decision_request_identity_provenance"] == {
        "issuer_file": "bots/falcon.py",
        "issuer_function": "central_can_open_trade",
        "mechanism": "SECRETS_TOKEN_URLSAFE",
        "identity_version": DECISION_REQUEST_IDENTITY_VERSION,
        "signal_id": signal["signal_id"],
        "signal_correlation_method": "EXACT_SIGNAL_ID",
        "issuance_kind": "NEW_EVALUATION",
    }
    assert first["decision_request_identity_transport"] == "NEW_EVALUATION"

    transported_signal = {
        "signal_id": signal["signal_id"],
        "decision_request_id": first["decision_request_id"],
        "decision_request_identity_version": first["decision_request_identity_version"],
        "decision_request_identity_provenance": first[
            "decision_request_identity_provenance"
        ],
    }
    transported = ensure_decision_request_identity(transported_signal)

    assert transported["decision_request_id"] == first["decision_request_id"]
    assert transported["decision_request_identity_transport"] == "EXPLICIT_SAME_EVALUATION"

    invalid_provenance = copy.deepcopy(transported_signal)
    invalid_provenance["decision_request_identity_provenance"]["issuer_function"] = "other"
    with pytest.raises(DecisionIdentityConstructionError, match="factual provenance"):
        ensure_decision_request_identity(invalid_provenance)


def test_restart_without_explicit_transport_is_a_new_reevaluation_and_requires_signal_id():
    first = ensure_decision_request_identity({"signal_id": "FALCON-SIGNAL:stable"})
    restarted = ensure_decision_request_identity({"signal_id": "FALCON-SIGNAL:stable"})

    assert restarted["decision_request_id"] != first["decision_request_id"]
    assert restarted["decision_request_identity_provenance"]["issuance_kind"] == "NEW_EVALUATION"
    with pytest.raises(DecisionIdentityConstructionError, match="signal_id"):
        ensure_decision_request_identity({})


def test_canonical_request_is_stable_covers_material_inputs_and_excludes_identities():
    payload = _payload(
        decision_id="PREVIOUS-DECISION",
        execution_id="EXECUTION-EXCLUDED",
        lifecycle_id="LIFECYCLE-EXCLUDED",
        logical_trade_id="LOGICAL-EXCLUDED",
        trade_id="TRADE-EXCLUDED",
        registry_execution_id="REGISTRY-EXECUTION-EXCLUDED",
        registry_position_id="REGISTRY-POSITION-EXCLUDED",
        client_order_id="CLIENT-EXCLUDED",
        broker_order_id="BROKER-EXCLUDED",
        exchange_order_id="EXCHANGE-EXCLUDED",
        fill_id="FILL-EXCLUDED",
        position_id="POSITION-EXCLUDED",
    )
    reordered = {key: payload[key] for key in reversed(tuple(payload))}
    canonical = canonical_decision_request(payload)
    canonical_reordered = canonical_decision_request(reordered)

    assert canonical["canonical_request_digest"] == canonical_reordered[
        "canonical_request_digest"
    ]
    assert canonical["canonical_request_digest_version"] == DECISION_REQUEST_DIGEST_VERSION
    material = canonical["canonical_request"]
    assert material["signal_id"] == payload["signal_id"]
    assert set(material["provider_inputs"]) == {
        key
        for key in payload
        if key not in identity._EXCLUDED_CANONICAL_REQUEST_FIELDS
    }
    for field in (
        "bot",
        "symbol",
        "side",
        "setup",
        "mode",
        "intended_live",
        "risk_pct",
        "notional_usdt",
        "entry",
        "stop",
        "tp50",
        "material_policy",
    ):
        assert field in material["provider_inputs"]

    excluded_values = {
        "PREVIOUS-DECISION",
        "EXECUTION-EXCLUDED",
        "LIFECYCLE-EXCLUDED",
        "LOGICAL-EXCLUDED",
        "TRADE-EXCLUDED",
        "REGISTRY-EXECUTION-EXCLUDED",
        "REGISTRY-POSITION-EXCLUDED",
        "CLIENT-EXCLUDED",
        "BROKER-EXCLUDED",
        "EXCHANGE-EXCLUDED",
        "FILL-EXCLUDED",
        "POSITION-EXCLUDED",
    }
    serialized = json.dumps(material, sort_keys=True)
    assert not any(value in serialized for value in excluded_values)

    changed_material = dict(payload)
    changed_material["risk_pct"] = 0.75
    assert canonical_decision_request(changed_material)["canonical_request_digest"] != canonical[
        "canonical_request_digest"
    ]
    changed_excluded = dict(payload)
    changed_excluded["broker_order_id"] = "ANOTHER-BROKER-EXCLUDED"
    assert canonical_decision_request(changed_excluded)["canonical_request_digest"] == canonical[
        "canonical_request_digest"
    ]


def test_store_requires_explicit_path_and_constructor_has_no_io(tmp_path):
    with pytest.raises(DecisionIdentityConstructionError, match="explicit local path"):
        DecisionIdentityRecordStore("")

    path = tmp_path / "decision-identity.json"
    store = DecisionIdentityRecordStore(path)

    assert store.path == path
    assert not path.exists()
    assert not store.lock_path.exists()
    assert not list(tmp_path.iterdir())


def test_importing_store_creates_no_files_or_directories(tmp_path):
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONPATH"] = str(ROOT) + os.pathsep + environment.get("PYTHONPATH", "")
    completed = subprocess.run(
        [sys.executable, "-B", "-c", "import decision_identity_store"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert not list(tmp_path.iterdir())


def test_claim_and_completion_are_one_immutable_lineage(tmp_path):
    store = DecisionIdentityRecordStore(tmp_path / "decision-identity.json")
    payload = _payload()
    request, canonical = _request_and_canonical(payload)

    claimed = store.claim(
        request,
        canonical,
        issuer_provider_provenance=_PROVIDER_PROVENANCE,
    )
    assert claimed["status"] == "CLAIMED"
    assert claimed["record"]["state"] == "CLAIMED"
    assert store.inspect(request["decision_request_id"])["status"] == "IDENTITY_REQUEST_INCOMPLETE"

    completed = store.complete(
        request,
        canonical,
        decision_id=DECISION_ID_PREFIX + "unit-test-candidate",
        decision_result="ALLOW",
        allowed=True,
        factual_provider=_PROVIDER_PROVENANCE,
    )
    assert completed["status"] == "COMPLETED"
    assert completed["record"]["state"] == "COMPLETED"
    assert completed["record"]["signal_id"] == payload["signal_id"]
    assert completed["record"]["decision_result"] == "ALLOW"
    assert completed["record"]["allowed"] is True
    assert store.inspect(request["decision_request_id"])["status"] == "IDENTITY_REPLAY"

    overwrite = store.complete(
        request,
        canonical,
        decision_id=DECISION_ID_PREFIX + "second-candidate",
        decision_result="ALLOW",
        allowed=True,
        factual_provider=_PROVIDER_PROVENANCE,
    )
    assert overwrite["status"] == "COMPLETED_OVERWRITE_FORBIDDEN"
    state = json.loads(store.path.read_text(encoding="utf-8"))
    assert {record["state"] for record in state["records"].values()} <= {
        "CLAIMED",
        "COMPLETED",
    }


def test_same_request_rejects_different_digest_and_stale_signal_binding(tmp_path):
    store = DecisionIdentityRecordStore(tmp_path / "decision-identity.json")
    payload = _payload()
    request, canonical = _request_and_canonical(payload)
    assert (
        store.claim(request, canonical, issuer_provider_provenance=_PROVIDER_PROVENANCE)[
            "status"
        ]
        == "CLAIMED"
    )

    changed_digest = dict(payload)
    changed_digest["risk_pct"] = 0.75
    changed_request, changed_canonical = _request_and_canonical(changed_digest)
    assert (
        store.claim(
            changed_request,
            changed_canonical,
            issuer_provider_provenance=_PROVIDER_PROVENANCE,
        )["status"]
        == "DECISION_REQUEST_ID_CONFLICT"
    )

    stale_signal = _same_request_with_signal(payload, "FALCON-SIGNAL-V2.7A.1:other")
    stale_request, stale_canonical = _request_and_canonical(stale_signal)
    assert (
        store.claim(
            stale_request,
            stale_canonical,
            issuer_provider_provenance=_PROVIDER_PROVENANCE,
        )["status"]
        == "DECISION_REQUEST_ID_CONFLICT"
    )


@pytest.mark.parametrize(("allowed", "literal"), [(True, "ALLOW"), (False, "DENY")])
def test_terminal_current_result_is_completed_only_after_durable_commit(
    tmp_path, allowed, literal
):
    store = DecisionIdentityRecordStore(tmp_path / "decision-identity.json")
    payload = _payload()
    expected = _v1_result(payload, allowed=allowed)
    calls = []

    result = evaluate_current_decision_with_identity(
        payload,
        _current_provider(expected, calls),
        store=store,
        provider_provenance=_PROVIDER_PROVENANCE,
    )

    assert calls == [payload]
    assert {field: result[field] for field in expected} == expected
    assert result["decision"] == literal
    assert result["decision_request_id"] == payload["decision_request_id"]
    assert result["decision_request_identity_version"] == DECISION_REQUEST_IDENTITY_VERSION
    assert result["decision_id"].startswith(DECISION_ID_PREFIX)
    assert result["decision_identity_version"] == DECISION_IDENTITY_VERSION
    assert result["decision_identity_v2_7a_2"]["status"] == "COMPLETED"
    assert (
        store.inspect(payload["decision_request_id"])["record"]["decision_id"]
        == result["decision_id"]
    )


def test_no_store_path_is_exact_v1_equivalent(tmp_path):
    del tmp_path
    payload = _payload()
    expected = _v1_result(payload, allowed=True)
    calls = []

    result = evaluate_current_decision_with_identity(
        payload,
        _current_provider(expected, calls),
        store=None,
    )

    assert calls == [payload]
    assert result == expected


def test_claim_failure_runs_current_v1_provider_without_decision_id(tmp_path, monkeypatch):
    store = DecisionIdentityRecordStore(tmp_path / "decision-identity.json")
    payload = _payload()
    expected = _v1_result(payload, allowed=True)
    calls = []

    def failed_claim_write(*_args, **_kwargs):
        raise RuntimeError("simulated claim write failure")

    monkeypatch.setattr(store, "_write_state_locked", failed_claim_write)
    result = evaluate_current_decision_with_identity(
        payload,
        _current_provider(expected, calls),
        store=store,
        provider_provenance=_PROVIDER_PROVENANCE,
    )

    assert calls == [payload]
    assert {field: result[field] for field in expected} == expected
    assert "decision_id" not in result
    assert result["decision_identity_v2_7a_2"]["status"] == "IDENTITY_UNAVAILABLE"


def test_completion_failure_keeps_current_v1_result_and_never_exposes_candidate(
    tmp_path, monkeypatch
):
    store = DecisionIdentityRecordStore(tmp_path / "decision-identity.json")
    payload = _payload()
    expected = _v1_result(payload, allowed=True)
    calls = []

    original_write = store._write_state_locked
    write_count = 0

    def fail_only_completed_write(state):
        nonlocal write_count
        write_count += 1
        if write_count == 2:
            raise RuntimeError("simulated completed write failure")
        return original_write(state)

    monkeypatch.setattr(store, "_write_state_locked", fail_only_completed_write)
    result = evaluate_current_decision_with_identity(
        payload,
        _current_provider(expected, calls),
        store=store,
        provider_provenance=_PROVIDER_PROVENANCE,
    )

    assert calls == [payload]
    assert {field: result[field] for field in expected} == expected
    assert "decision_id" not in result
    assert result["decision_identity_v2_7a_2"]["status"] == "IDENTITY_COMPLETION_UNAVAILABLE"
    assert store.inspect(payload["decision_request_id"])["status"] == "IDENTITY_REQUEST_INCOMPLETE"


def test_corrupt_or_missing_store_never_changes_current_v1_result(tmp_path):
    path = tmp_path / "decision-identity.json"
    store = DecisionIdentityRecordStore(path)
    payload = _payload()
    expected = _v1_result(payload, allowed=False)
    calls = []

    assert store.inspect(payload["decision_request_id"])["status"] == "IDENTITY_RECORD_MISSING"
    path.write_text("{not valid json", encoding="utf-8")
    result = evaluate_current_decision_with_identity(
        payload,
        _current_provider(expected, calls),
        store=store,
        provider_provenance=_PROVIDER_PROVENANCE,
    )

    assert calls == [payload]
    assert {field: result[field] for field in expected} == expected
    assert "decision_id" not in result
    assert result["decision_identity_v2_7a_2"]["status"] == "IDENTITY_UNAVAILABLE"


def test_preexisting_v1_identity_field_is_never_overwritten(tmp_path):
    store = DecisionIdentityRecordStore(tmp_path / "decision-identity.json")
    payload = _payload()
    expected = _v1_result(payload, allowed=True)
    expected["decision_id"] = "PREEXISTING-V1-DECISION"
    calls = []

    result = evaluate_current_decision_with_identity(
        payload,
        _current_provider(expected, calls),
        store=store,
        provider_provenance=_PROVIDER_PROVENANCE,
    )

    assert calls == [payload]
    assert {field: result[field] for field in expected} == expected
    assert result["decision_identity_v2_7a_2"]["status"] == "DECISION_ID_FIELD_CONFLICT"
    assert store.inspect(payload["decision_request_id"])["status"] == "IDENTITY_REQUEST_INCOMPLETE"


def test_claimed_request_is_incomplete_but_still_runs_current_provider(tmp_path):
    store = DecisionIdentityRecordStore(tmp_path / "decision-identity.json")
    payload = _payload()
    request, canonical = _request_and_canonical(payload)
    assert (
        store.claim(request, canonical, issuer_provider_provenance=_PROVIDER_PROVENANCE)[
            "status"
        ]
        == "CLAIMED"
    )
    expected = _v1_result(payload, allowed=True)
    calls = []

    result = evaluate_current_decision_with_identity(
        payload,
        _current_provider(expected, calls),
        store=store,
        provider_provenance=_PROVIDER_PROVENANCE,
    )

    assert calls == [payload]
    assert {field: result[field] for field in expected} == expected
    assert "decision_id" not in result
    assert result["decision_identity_v2_7a_2"]["status"] == "IDENTITY_REQUEST_INCOMPLETE"


@pytest.mark.parametrize(
    ("stored_allowed", "current_allowed"), [(True, False), (False, True)]
)
def test_completed_replay_is_historical_only_never_current_approval_or_denial(
    tmp_path, stored_allowed, current_allowed
):
    store = DecisionIdentityRecordStore(tmp_path / "decision-identity.json")
    payload = _payload()
    first_expected = _v1_result(payload, allowed=stored_allowed)
    first_calls = []
    first = evaluate_current_decision_with_identity(
        payload,
        _current_provider(first_expected, first_calls),
        store=store,
        provider_provenance=_PROVIDER_PROVENANCE,
    )
    current_expected = _v1_result(payload, allowed=current_allowed)
    replay_calls = []
    replay = evaluate_current_decision_with_identity(
        payload,
        _current_provider(current_expected, replay_calls),
        store=store,
        provider_provenance=_PROVIDER_PROVENANCE,
    )

    assert first_calls == [payload]
    assert replay_calls == [payload]
    assert {field: replay[field] for field in current_expected} == current_expected
    assert "decision_id" not in replay
    historical = replay["decision_identity_v2_7a_2"]
    assert historical["status"] == "IDENTITY_REPLAY_HISTORICAL_ONLY"
    assert historical["historical"]["decision_id"] == first["decision_id"]
    assert historical["historical"]["decision_result"] == first_expected["decision"]
    assert replay["allowed"] is current_allowed
    assert replay["decision"] == current_expected["decision"]


def test_new_reevaluation_gets_distinct_request_and_decision_ids(tmp_path):
    store = DecisionIdentityRecordStore(tmp_path / "decision-identity.json")
    first_payload = _payload()
    second_payload = _payload(signal_id=first_payload["signal_id"])
    first = evaluate_current_decision_with_identity(
        first_payload,
        lambda value: _v1_result(value, allowed=True),
        store=store,
        provider_provenance=_PROVIDER_PROVENANCE,
    )
    second = evaluate_current_decision_with_identity(
        second_payload,
        lambda value: _v1_result(value, allowed=True),
        store=store,
        provider_provenance=_PROVIDER_PROVENANCE,
    )

    assert first_payload["decision_request_id"] != second_payload["decision_request_id"]
    assert first["decision_id"] != second["decision_id"]


def test_signal_binding_mismatch_is_identity_only_and_never_repaired(tmp_path):
    store = DecisionIdentityRecordStore(tmp_path / "decision-identity.json")
    payload = _payload()
    payload["decision_request_identity_provenance"] = {
        **payload["decision_request_identity_provenance"],
        "signal_id": "FALCON-SIGNAL-V2.7A.1:mismatch",
    }
    expected = _v1_result(payload, allowed=True)
    calls = []

    result = evaluate_current_decision_with_identity(
        payload,
        _current_provider(expected, calls),
        store=store,
        provider_provenance=_PROVIDER_PROVENANCE,
    )

    assert calls == [payload]
    assert {field: result[field] for field in expected} == expected
    assert "decision_id" not in result
    assert result["decision_identity_v2_7a_2"]["status"] == "IDENTITY_UNAVAILABLE"


def test_crash_before_claim_allows_first_claim_only_when_no_witness_exists(tmp_path):
    store = DecisionIdentityRecordStore(tmp_path / "decision-identity.json")
    payload = _payload()

    assert store.inspect(payload["decision_request_id"])["status"] == "IDENTITY_RECORD_MISSING"
    result = evaluate_current_decision_with_identity(
        payload,
        lambda value: _v1_result(value, allowed=True),
        store=store,
        provider_provenance=_PROVIDER_PROVENANCE,
    )
    assert result["decision_identity_v2_7a_2"]["status"] == "COMPLETED"


def test_crash_after_claim_before_provider_result_consumes_request_without_id(tmp_path):
    store = DecisionIdentityRecordStore(tmp_path / "decision-identity.json")
    payload = _payload()
    request, canonical = _request_and_canonical(payload)
    store.claim(request, canonical, issuer_provider_provenance=_PROVIDER_PROVENANCE)
    calls = []
    expected = _v1_result(payload, allowed=False)

    result = evaluate_current_decision_with_identity(
        payload,
        _current_provider(expected, calls),
        store=store,
        provider_provenance=_PROVIDER_PROVENANCE,
    )
    assert calls == [payload]
    assert result["allowed"] is False
    assert "decision_id" not in result
    assert result["decision_identity_v2_7a_2"]["status"] == "IDENTITY_REQUEST_INCOMPLETE"


def test_crash_after_provider_result_before_completion_keeps_same_incomplete_rule(tmp_path):
    store = DecisionIdentityRecordStore(tmp_path / "decision-identity.json")
    payload = _payload()
    request, canonical = _request_and_canonical(payload)
    store.claim(request, canonical, issuer_provider_provenance=_PROVIDER_PROVENANCE)
    stale_provider_result = _v1_result(payload, allowed=True)
    assert stale_provider_result["decision"] == "ALLOW"

    result = evaluate_current_decision_with_identity(
        payload,
        lambda value: _v1_result(value, allowed=False),
        store=store,
        provider_provenance=_PROVIDER_PROVENANCE,
    )
    assert result["allowed"] is False
    assert "decision_id" not in result
    assert result["decision_identity_v2_7a_2"]["status"] == "IDENTITY_REQUEST_INCOMPLETE"


def test_crash_after_completed_permits_historical_projection_only(tmp_path):
    store = DecisionIdentityRecordStore(tmp_path / "decision-identity.json")
    payload = _payload()
    completed = evaluate_current_decision_with_identity(
        payload,
        lambda value: _v1_result(value, allowed=True),
        store=store,
        provider_provenance=_PROVIDER_PROVENANCE,
    )
    replay = evaluate_current_decision_with_identity(
        payload,
        lambda value: _v1_result(value, allowed=False),
        store=store,
        provider_provenance=_PROVIDER_PROVENANCE,
    )

    assert completed["decision_id"].startswith(DECISION_ID_PREFIX)
    assert replay["allowed"] is False
    assert "decision_id" not in replay
    assert replay["decision_identity_v2_7a_2"]["historical"]["decision_id"] == completed[
        "decision_id"
    ]


def test_retention_is_bounded_and_retired_request_ids_are_not_reusable(tmp_path):
    store = DecisionIdentityRecordStore(
        tmp_path / "decision-identity.json", retention_max_records=1
    )
    first_payload = _payload(signal_id="FALCON-SIGNAL-V2.7A.1:first")
    second_payload = _payload(signal_id="FALCON-SIGNAL-V2.7A.1:second")
    for payload in (first_payload, second_payload):
        evaluate_current_decision_with_identity(
            payload,
            lambda value: _v1_result(value, allowed=True),
            store=store,
            provider_provenance=_PROVIDER_PROVENANCE,
        )

    state = json.loads(store.path.read_text(encoding="utf-8"))
    assert len(state["records"]) == 1
    assert store.inspect(first_payload["decision_request_id"])["status"] == "IDENTITY_REQUEST_RETIRED"
    calls = []
    expected = _v1_result(first_payload, allowed=False)
    reused = evaluate_current_decision_with_identity(
        first_payload,
        _current_provider(expected, calls),
        store=store,
        provider_provenance=_PROVIDER_PROVENANCE,
    )
    assert calls == [first_payload]
    assert "decision_id" not in reused
    assert reused["decision_identity_v2_7a_2"]["status"] == "DECISION_REQUEST_ID_RETIRED"


def test_corruption_is_detected_without_silent_repair(tmp_path):
    store = DecisionIdentityRecordStore(tmp_path / "decision-identity.json")
    payload = _payload()
    evaluate_current_decision_with_identity(
        payload,
        lambda value: _v1_result(value, allowed=True),
        store=store,
        provider_provenance=_PROVIDER_PROVENANCE,
    )
    store.path.write_text("{corrupt", encoding="utf-8")
    corrupted = store.path.read_text(encoding="utf-8")

    with pytest.raises(DecisionIdentityStoreCorruptionError):
        store.inspect(payload["decision_request_id"])

    assert store.path.read_text(encoding="utf-8") == corrupted


def test_thread_claim_serialization_allows_one_lineage_only(tmp_path):
    store = DecisionIdentityRecordStore(tmp_path / "decision-identity.json")
    payload = _payload()
    request, canonical = _request_and_canonical(payload)
    barrier = threading.Barrier(2)
    statuses = []

    def claim_once():
        barrier.wait(timeout=5)
        statuses.append(
            store.claim(
                request,
                canonical,
                issuer_provider_provenance=_PROVIDER_PROVENANCE,
            )["status"]
        )

    workers = [threading.Thread(target=claim_once) for _ in range(2)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=10)
        assert not worker.is_alive()

    assert sorted(statuses) == ["CLAIMED", "IDENTITY_REQUEST_INCOMPLETE"]


def test_independent_store_instances_serialize_same_request_with_file_lock(tmp_path):
    path = tmp_path / "decision-identity.json"
    stores = [DecisionIdentityRecordStore(path), DecisionIdentityRecordStore(path)]
    payload = _payload()
    request, canonical = _request_and_canonical(payload)
    barrier = threading.Barrier(2)
    statuses = []
    errors = []

    def claim_once(store):
        try:
            barrier.wait(timeout=5)
            statuses.append(
                store.claim(
                    request,
                    canonical,
                    issuer_provider_provenance=_PROVIDER_PROVENANCE,
                )["status"]
            )
        except BaseException as exc:  # pragma: no cover - thread diagnostic path
            errors.append(exc)

    workers = [threading.Thread(target=claim_once, args=(store,)) for store in stores]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=10)
        assert not worker.is_alive()

    assert errors == []
    assert sorted(statuses) == ["CLAIMED", "IDENTITY_REQUEST_INCOMPLETE"]


def test_cross_process_claim_serialization_allows_one_lineage_only(tmp_path):
    path = tmp_path / "decision-identity.json"
    payload = _payload()
    context = multiprocessing.get_context("spawn")
    queue = context.Queue()
    processes = [
        context.Process(target=_cross_process_claim_worker, args=(str(path), payload, queue))
        for _ in range(2)
    ]
    for process in processes:
        process.start()
    outcomes = [queue.get(timeout=20) for _ in processes]
    for process in processes:
        process.join(timeout=20)
        assert process.exitcode == 0

    assert sorted(outcome[1] for outcome in outcomes if outcome[0] == "ok") == [
        "CLAIMED",
        "IDENTITY_REQUEST_INCOMPLETE",
    ]
    assert all(outcome[0] == "ok" for outcome in outcomes)


class _CentralResponse:
    status_code = 200
    text = "ok"

    def __init__(self, body):
        self._body = body

    def json(self):
        return copy.deepcopy(self._body)


class _CentralRequests:
    def __init__(self, body):
        self.body = body
        self.calls = []

    def post(self, url, *, json, timeout):
        self.calls.append({"url": url, "json": copy.deepcopy(json), "timeout": timeout})
        return _CentralResponse(self.body)


def _run_falcon_caller(identity_issuer):
    requests = _CentralRequests({"allowed": True, "decision": "ALLOW", "reasons": [], "warnings": []})
    caller = _load_function(
        FALCON_SOURCE,
        "central_can_open_trade",
        {
            "FALCON_MODE": "VERIFY",
            "FALCON_SINGLE_LIVE_EXECUTION_PATH_VERSION": "TEST-CONTRACT",
            "FALCON_USE_CENTRAL_RISK": True,
            "FALCON_REAL_NOTIONAL_USDT": 25.0,
            "CENTRAL_CAN_OPEN_TRADE_URL": "http://central.test/can_open_trade",
            "normalize_symbol_for_central": lambda value: str(value or "").upper(),
            "safe_float": lambda value, default: default if value is None else float(value),
            "ensure_decision_request_identity": identity_issuer,
            "requests": requests,
        },
    )
    signal = {
        "signal_id": "FALCON-SIGNAL-V2.7A.1:caller-seam",
        "symbol": "BTCUSDT",
        "side": "LONG",
        "setup": "FALCON15",
        "risk_pct": 0.5,
        "real_notional_usdt": 25.0,
        "entry": 101.25,
        "stop": 99.75,
        "tp50": 102.75,
    }
    result = caller(signal)
    assert result == {"allowed": True, "decision": "ALLOW", "reasons": [], "warnings": []}
    assert len(requests.calls) == 1
    return signal, requests.calls[0]["json"]


def test_falcon_issues_and_transports_request_identity_once_before_provider_call():
    baseline_signal, baseline_payload = _run_falcon_caller(None)

    def failed_identity(_signal):
        raise RuntimeError("identity unavailable")

    failed_signal, failed_payload = _run_falcon_caller(failed_identity)
    issued_signal, issued_payload = _run_falcon_caller(ensure_decision_request_identity)

    assert failed_signal == baseline_signal
    assert failed_payload == baseline_payload
    assert not {
        "decision_request_id",
        "decision_request_identity_version",
        "decision_request_identity_provenance",
    } & set(failed_payload)
    for field in (
        "decision_request_id",
        "decision_request_identity_version",
        "decision_request_identity_provenance",
    ):
        assert issued_payload[field] == issued_signal[field]
    assert issued_payload["decision_request_id"].startswith(DECISION_REQUEST_ID_PREFIX)
    assert issued_payload["decision_request_identity_provenance"]["signal_id"] == issued_signal[
        "signal_id"
    ]


@pytest.mark.parametrize(
    "response",
    [
        {"allowed": True, "decision": "ALLOW", "reasons": [], "warnings": []},
        {"allowed": False, "decision": "DENY", "reasons": ["V1 deny"], "warnings": []},
    ],
)
def test_falcon_absent_optional_identity_helper_keeps_exact_v1_live_payload(response):
    requests = _CentralRequests(response)
    caller = _load_function(
        FALCON_SOURCE,
        "central_can_open_trade",
        {
            "FALCON_MODE": "LIVE",
            "FALCON_SINGLE_LIVE_EXECUTION_PATH_VERSION": "TEST-SINGLE-PATH-V1",
            "FALCON_USE_CENTRAL_RISK": True,
            "FALCON_REAL_NOTIONAL_USDT": 25.0,
            "CENTRAL_CAN_OPEN_TRADE_URL": "http://central.test/can_open_trade",
            "normalize_symbol_for_central": lambda value: str(value or "").upper(),
            "safe_float": lambda value, default: default if value is None else float(value),
            "requests": requests,
        },
    )
    signal = {
        "id": "LEGACY-SIGNAL-ID-MUST-NOT-BE-USED",
        "signal_id": None,
        "symbol": "BTCUSDT",
        "side": "LONG",
        "setup": "FALCON15",
        "risk_pct": 0.5,
        "real_notional_usdt": 25.0,
        "entry": 101.25,
        "stop": 99.75,
        "tp50": 102.75,
    }
    original_signal = copy.deepcopy(signal)

    result = caller(signal)

    assert result == response
    assert signal == original_signal
    assert len(requests.calls) == 1
    assert requests.calls[0] == {
        "url": "http://central.test/can_open_trade",
        "timeout": 8,
        "json": {
            "bot": "FALCON",
            "symbol": "BTCUSDT",
            "side": "LONG",
            "setup": "FALCON15",
            "mode": "LIVE",
            "intended_live": True,
            "falcon_single_live_execution_path_v1": "TEST-SINGLE-PATH-V1",
            "falcon_live_execution_path": "ORCHESTRATOR_ENGINE",
            "suppress_auto_real_bridge": True,
            "signal_id": None,
            "decision_id": None,
            "lifecycle_id": None,
            "trade_id": None,
            "client_order_attempt_id": None,
            "client_order_attempt_sequence": None,
            "risk_pct": 0.5,
            "notional_usdt": 25.0,
            "entry": 101.25,
            "stop": 99.75,
            "tp50": 102.75,
        },
    }


def test_final_main_wrapper_is_dormant_without_injection_and_uses_one_explicit_store(tmp_path):
    payload = _payload()
    expected = _v1_result(payload, allowed=True)
    calls = []

    def base_provider(value):
        calls.append(copy.deepcopy(value))
        return copy.deepcopy(expected)

    dormant = _load_function(
        MAIN_SOURCE,
        "can_open_trade_decision",
        {
            "DECISION_IDENTITY_RECORD_STORE": None,
            "evaluate_current_decision_with_identity": evaluate_current_decision_with_identity,
            "_can_open_trade_decision_v1_final": base_provider,
            "_DECISION_IDENTITY_PROVIDER_PROVENANCE_V2_7A_2": _PROVIDER_PROVENANCE,
        },
        latest=True,
    )
    assert dormant(payload) == expected
    assert calls == [payload]

    store = DecisionIdentityRecordStore(tmp_path / "decision-identity.json")
    active = _load_function(
        MAIN_SOURCE,
        "can_open_trade_decision",
        {
            "DECISION_IDENTITY_RECORD_STORE": store,
            "evaluate_current_decision_with_identity": evaluate_current_decision_with_identity,
            "_can_open_trade_decision_v1_final": base_provider,
            "_DECISION_IDENTITY_PROVIDER_PROVENANCE_V2_7A_2": _PROVIDER_PROVENANCE,
        },
        latest=True,
    )
    result = active(payload)

    assert calls == [payload, payload]
    assert {field: result[field] for field in expected} == expected
    assert result["decision_id"].startswith(DECISION_ID_PREFIX)


def test_source_guards_prove_one_local_store_and_exact_seams_only():
    store_tree = ast.parse(STORE_SOURCE.read_text(encoding="utf-8"), filename=str(STORE_SOURCE))
    imported_roots = {
        alias.name.split(".", 1)[0]
        for node in ast.walk(store_tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported_roots.update(
        (node.module or "").split(".", 1)[0]
        for node in ast.walk(store_tree)
        if isinstance(node, ast.ImportFrom)
    )
    assert {"broker", "trade_registry", "registry_v2", "redis", "requests", "socket"}.isdisjoint(
        imported_roots
    )
    assert [
        node.name
        for node in store_tree.body
        if isinstance(node, ast.ClassDef) and node.name == "DecisionIdentityRecordStore"
    ] == ["DecisionIdentityRecordStore"]
    store_text = STORE_SOURCE.read_text(encoding="utf-8")
    assert "/data" not in store_text
    assert "os.environ" not in store_text
    assert "http://" not in store_text
    assert "https://" not in store_text
    assert "generate_execution_id" not in store_text
    assert "generate_lifecycle_id" not in store_text
    assert "falcon_registry_v2_verify_shadow" not in store_text

    falcon_tree = ast.parse(FALCON_SOURCE.read_text(encoding="utf-8"), filename=str(FALCON_SOURCE))
    caller = next(
        node
        for node in falcon_tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "central_can_open_trade"
    )
    identity_helper_lookup_calls = [
        node
        for node in ast.walk(caller)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "get"
        and isinstance(node.func.value, ast.Call)
        and isinstance(node.func.value.func, ast.Name)
        and node.func.value.func.id == "globals"
    ]
    issuance_calls = [
        node
        for node in ast.walk(caller)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "decision_request_identity_helper"
    ]
    post_calls = [
        node
        for node in ast.walk(caller)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "requests"
        and node.func.attr == "post"
    ]
    assert len(identity_helper_lookup_calls) == 1
    assert len(issuance_calls) == 1
    assert len(post_calls) == 1
    assert issuance_calls[0].lineno < post_calls[0].lineno
    assert "falcon_registry_v2_verify_shadow" not in FALCON_SOURCE.read_text(encoding="utf-8")

    central_call_sites = [
        node
        for node in ast.walk(falcon_tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "central_can_open_trade"
    ]
    execute_functions = [
        node
        for node in falcon_tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "execute_signal_if_allowed"
    ]
    scanner = next(
        node
        for node in falcon_tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "scanner_loop"
    )
    final_execute_call_names = [
        node.func.id
        for node in ast.walk(execute_functions[-1])
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    ]
    scanner_call_names = [
        node.func.id
        for node in ast.walk(scanner)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    ]
    assert len(central_call_sites) == 1
    assert len(execute_functions) == 2
    assert final_execute_call_names.count(
        "_ORIGINAL_EXECUTE_SIGNAL_IF_ALLOWED_BEFORE_RPM_V1"
    ) == 1
    assert scanner_call_names.count("analyze_symbol_setup") == 1
    assert scanner_call_names.count("execute_signal_if_allowed") == 1

    main_tree = ast.parse(MAIN_SOURCE.read_text(encoding="utf-8"), filename=str(MAIN_SOURCE))
    final_wrappers = [
        node
        for node in main_tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "can_open_trade_decision"
    ]
    final_wrapper = final_wrappers[-1]
    final_call_names = {
        node.func.id
        for node in ast.walk(final_wrapper)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "evaluate_current_decision_with_identity" in final_call_names
    assert "_can_open_trade_decision_v1_final" in final_call_names
    assert sum(
        isinstance(node, ast.FunctionDef) and node.name == "_can_open_trade_decision_v1_final"
        for node in main_tree.body
    ) == 1
    assert "falcon_registry_v2_verify_shadow" not in MAIN_SOURCE.read_text(encoding="utf-8")
