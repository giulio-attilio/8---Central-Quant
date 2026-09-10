from __future__ import annotations

import ast
import copy
import inspect
import threading
from dataclasses import replace

import pytest

import trade_registry_closed_identity_conflict_repair_runtime_durable_handoff_harness_v1 as harness
import trade_registry_closed_identity_conflict_repair_runtime_durable_handoff_v1 as handoff_module


@pytest.fixture(scope="module")
def handoff_inputs() -> dict:
    return harness.build_synthetic_durable_handoff_inputs_v1()


def _handoff(*, wal=None, clock=None):
    return harness.build_synthetic_durable_handoff_v1(
        wal=(
            wal
            if wal is not None
            else handoff_module.InMemoryHashChainedHandoffWalV1()
        ),
        clock=clock,
    )


def _reseal_intent(inputs: dict) -> None:
    intent = inputs["handoff_intent"]
    intent["intent_sha256"] = handoff_module.durable_handoff_intent_sha256_v1(
        intent
    )


def _terminal(command, state: str, *, event_epoch=harness._NOW):
    return harness.build_synthetic_terminal_attestation_v1(
        command, state, event_epoch=event_epoch
    )


def test_valid_handoff_prepares_deterministic_non_executable_command(
    handoff_inputs: dict,
) -> None:
    result = _handoff().prepare(**copy.deepcopy(handoff_inputs))

    assert result["ok"] is True
    assert result["handoff_contract_verified"] is True
    assert result["gateway_verified"] is True
    assert result["authorization_verified_synthetic"] is True
    assert result["transaction_identity_verified"] is True
    assert result["strict_deadline_verified"] is True
    assert result["wal_prepared"] is True
    assert result["production_durability_verified"] is False
    assert result["controller_invocation_allowed"] is False
    assert result["registry_write_allowed"] is False
    assert result["runtime_binding_satisfied"] is False
    assert result["production_ready"] is False
    assert result["apply_allowed"] is False
    assert result["activation_allowed"] is False
    assert result["live_allowed"] is False
    assert result["no_order_sent"] is True

    command = result["protected_command"]
    assert type(command) is handoff_module.ProtectedDurableHandoffCommandV1
    assert repr(command) == "ProtectedDurableHandoffCommandV1(<protected>)"
    assert command.transaction_id == command.idempotency_key
    assert command.command_version == handoff_module.HANDOFF_COMMAND_VERSION_V1
    for method_name in ("serialize", "to_payload", "send", "apply", "invoke", "commit"):
        assert not hasattr(command, method_name)


def test_transaction_identity_is_deterministic_across_fresh_stores(
    handoff_inputs: dict,
) -> None:
    first = _handoff().prepare(**copy.deepcopy(handoff_inputs))
    second = _handoff().prepare(**copy.deepcopy(handoff_inputs))

    assert first["ok"] is True
    assert second["ok"] is True
    assert first["protected_command"].transaction_id == second[
        "protected_command"
    ].transaction_id
    assert first["protected_command"].handoff_binding_sha256 == second[
        "protected_command"
    ].handoff_binding_sha256
    assert first["protected_command"].wal_prepared_record_sha256 == second[
        "protected_command"
    ].wal_prepared_record_sha256


def test_prepared_replay_does_not_append_a_second_record(handoff_inputs: dict) -> None:
    wal = handoff_module.InMemoryHashChainedHandoffWalV1()
    handoff = _handoff(wal=wal)

    first = handoff.prepare(**copy.deepcopy(handoff_inputs))
    replay = handoff.prepare(**copy.deepcopy(handoff_inputs))

    assert first["ok"] is True
    assert first["idempotent_replay"] is False
    assert replay["ok"] is True
    assert replay["idempotent_replay"] is True
    assert replay["protected_command"].transaction_id == first[
        "protected_command"
    ].transaction_id
    assert wal.snapshot()["record_count"] == 1
    assert wal.snapshot()["states"] == {"PREPARED": 1}


def test_terminal_commit_is_one_shot_and_idempotent(handoff_inputs: dict) -> None:
    wal = handoff_module.InMemoryHashChainedHandoffWalV1()
    handoff = _handoff(wal=wal)
    prepared = handoff.prepare(**copy.deepcopy(handoff_inputs))
    command = prepared["protected_command"]
    attestation = _terminal(command, "COMMITTED")

    first = handoff.finalize_offline(command, attestation)
    replay = handoff.finalize_offline(command, copy.deepcopy(attestation))

    assert first["ok"] is True
    assert first["terminal_state"] == "COMMITTED"
    assert first["idempotent_replay"] is False
    assert first["production_commit_verified"] is False
    assert first["controller_invoked"] is False
    assert first["registry_write"] is False
    assert replay["ok"] is True
    assert replay["idempotent_replay"] is True
    assert wal.snapshot()["states"] == {"PREPARED": 1, "COMMITTED": 1}


def test_conflicting_terminal_transition_fails_closed(handoff_inputs: dict) -> None:
    wal = handoff_module.InMemoryHashChainedHandoffWalV1()
    handoff = _handoff(wal=wal)
    prepared = handoff.prepare(**copy.deepcopy(handoff_inputs))
    command = prepared["protected_command"]
    committed = handoff.finalize_offline(command, _terminal(command, "COMMITTED"))
    conflict = handoff.finalize_offline(command, _terminal(command, "ABORTED"))

    assert committed["ok"] is True
    assert conflict["ok"] is False
    assert conflict["reason"] == "HANDOFF_WAL_TERMINAL_CONFLICT"
    assert conflict["registry_write"] is False
    assert wal.snapshot()["states"] == {"PREPARED": 1, "COMMITTED": 1}


def test_restart_harness_recovers_all_states_without_runtime() -> None:
    result = harness.run_synthetic_durable_handoff_restart_harness_v1()

    assert result["ok"] is True
    assert result["protected_surface_safe"] is True
    assert result["commit_recovered_after_restart"] is True
    assert result["commit_replay_idempotent"] is True
    assert result["prepared_recovered_after_restart"] is True
    assert result["abort_recovered_after_restart"] is True
    assert result["wal_hash_chain_verified"] is True
    assert result["restart_recovery_rehearsed"] is True
    assert result["production_durability_verified"] is False
    assert result["controller_invocation_allowed"] is False
    assert result["registry_write_allowed"] is False
    assert result["runtime_binding_satisfied"] is False
    assert result["apply_allowed"] is False
    assert result["write_executed"] is False
    assert result["no_order_sent"] is True


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("candidate_registry_sha256", "f" * 64),
        ("controller_instance_sha256", "e" * 64),
        ("terminal_policy", "AUTO_COMMIT"),
        ("controller_call_requested", True),
        ("registry_write_requested", True),
        ("runtime_binding_requested", True),
        ("max_terminal_transition_count", 2),
    ],
)
def test_any_handoff_intent_drift_fails_closed(
    handoff_inputs: dict, field_name: str, value: object
) -> None:
    inputs = copy.deepcopy(handoff_inputs)
    inputs["handoff_intent"][field_name] = value
    _reseal_intent(inputs)

    result = _handoff().prepare(**inputs)

    assert result["ok"] is False
    assert "HANDOFF_INTENT_INVALID" in result["reasons"]
    assert result["protected_command"] is None
    assert result["controller_invocation_allowed"] is False
    assert result["registry_write_allowed"] is False


def test_unknown_intent_field_fails_closed(handoff_inputs: dict) -> None:
    inputs = copy.deepcopy(handoff_inputs)
    inputs["handoff_intent"]["production_authority"] = True
    _reseal_intent(inputs)

    result = _handoff().prepare(**inputs)

    assert result["ok"] is False
    assert "HANDOFF_INTENT_INVALID" in result["reasons"]
    assert result["apply_allowed"] is False


def test_gateway_or_authorization_tampering_fails_closed(handoff_inputs: dict) -> None:
    gateway_inputs = copy.deepcopy(handoff_inputs)
    gateway_inputs["gateway_result"]["gateway_receipt"]["apply_allowed"] = True
    authorization_inputs = copy.deepcopy(handoff_inputs)
    authorization_inputs["authorization_result"]["authorization_receipt"][
        "max_apply_count"
    ] = 2

    gateway_result = _handoff().prepare(**gateway_inputs)
    authorization_result = _handoff().prepare(**authorization_inputs)

    assert "HANDOFF_GATEWAY_INVALID" in gateway_result["reasons"]
    assert "HANDOFF_AUTHORIZATION_INVALID" in authorization_result["reasons"]
    for result in (gateway_result, authorization_result):
        assert result["ok"] is False
        assert result["protected_command"] is None
        assert result["registry_write_allowed"] is False


def test_exact_expiry_blocks_prepare(handoff_inputs: dict) -> None:
    inputs = copy.deepcopy(handoff_inputs)
    expiry = inputs["gateway_result"]["protected_envelope"].expires_at_epoch

    result = _handoff(clock=lambda: expiry).prepare(**inputs)

    assert result["ok"] is False
    assert "HANDOFF_DEADLINE_INVALID_OR_EXPIRED" in result["reasons"]
    assert result["strict_deadline_verified"] is False
    assert result["protected_command"] is None


def test_exact_expiry_blocks_terminal_transition(handoff_inputs: dict) -> None:
    source_wal = handoff_module.InMemoryHashChainedHandoffWalV1()
    source_handoff = _handoff(wal=source_wal)
    source_prepared = source_handoff.prepare(**copy.deepcopy(handoff_inputs))
    source_command = source_prepared["protected_command"]
    terminal_handoff = _handoff(
        wal=handoff_module.InMemoryHashChainedHandoffWalV1(
            source_wal.export_restart_snapshot()
        ),
        clock=lambda: source_command.expires_at_epoch,
    )
    attestation = _terminal(
        source_command,
        "COMMITTED",
        event_epoch=source_command.expires_at_epoch,
    )

    result = terminal_handoff.finalize_offline(source_command, attestation)

    assert result["ok"] is False
    assert result["reason"] == "HANDOFF_TERMINAL_ATTESTATION_INVALID"
    assert result["registry_write"] is False


def test_stale_prepared_handoff_can_only_be_aborted(handoff_inputs: dict) -> None:
    wal = handoff_module.InMemoryHashChainedHandoffWalV1()
    source_handoff = _handoff(wal=wal)
    prepared = source_handoff.prepare(**copy.deepcopy(handoff_inputs))
    command = prepared["protected_command"]
    stale_now = command.expires_at_epoch + 1
    restored_wal = handoff_module.InMemoryHashChainedHandoffWalV1(
        wal.export_restart_snapshot()
    )
    recovery = _handoff(wal=restored_wal, clock=lambda: stale_now)

    committed = recovery.finalize_offline(
        command,
        _terminal(command, "COMMITTED", event_epoch=stale_now),
    )
    aborted = recovery.finalize_offline(
        command,
        _terminal(command, "ABORTED", event_epoch=stale_now),
    )

    assert committed["ok"] is False
    assert committed["reason"] == "HANDOFF_TERMINAL_ATTESTATION_INVALID"
    assert aborted["ok"] is True
    assert aborted["terminal_state"] == "ABORTED"
    assert aborted["registry_write"] is False
    assert restored_wal.snapshot()["states"] == {"PREPARED": 1, "ABORTED": 1}


def test_reconstructed_command_with_extended_deadline_is_rejected(
    handoff_inputs: dict,
) -> None:
    wal = handoff_module.InMemoryHashChainedHandoffWalV1()
    handoff = _handoff(wal=wal)
    prepared = handoff.prepare(**copy.deepcopy(handoff_inputs))
    command = prepared["protected_command"]
    forged = replace(command, expires_at_epoch=command.expires_at_epoch + 100)

    result = handoff.finalize_offline(forged, _terminal(forged, "COMMITTED"))

    assert result["ok"] is False
    assert result["reason"] == "HANDOFF_TERMINAL_INPUT_INVALID"
    assert result["registry_write"] is False
    assert wal.snapshot()["states"] == {"PREPARED": 1}


@pytest.mark.parametrize(
    "mutation",
    ["record_sha", "previous_sha", "state", "sequence", "binding", "truncate"],
)
def test_corrupted_or_truncated_restart_snapshot_is_rejected(
    handoff_inputs: dict, mutation: str
) -> None:
    wal = handoff_module.InMemoryHashChainedHandoffWalV1()
    handoff = _handoff(wal=wal)
    prepared = handoff.prepare(**copy.deepcopy(handoff_inputs))
    command = prepared["protected_command"]
    handoff.finalize_offline(command, _terminal(command, "COMMITTED"))
    snapshot = [dict(record) for record in wal.export_restart_snapshot()]
    if mutation == "record_sha":
        snapshot[-1]["record_sha256"] = "f" * 64
    elif mutation == "previous_sha":
        snapshot[-1]["previous_record_sha256"] = "e" * 64
    elif mutation == "state":
        snapshot[-1]["state"] = "PREPARED"
    elif mutation == "sequence":
        snapshot[-1]["sequence"] = 99
    elif mutation == "binding":
        snapshot[-1]["handoff_binding_sha256"] = "d" * 64
    else:
        snapshot = snapshot[1:]

    with pytest.raises(handoff_module.HandoffWalIntegrityError):
        handoff_module.InMemoryHashChainedHandoffWalV1(snapshot)


@pytest.mark.parametrize("mutation", ["binding", "event_order"])
def test_resealed_terminal_record_cannot_change_prepared_history(
    handoff_inputs: dict, mutation: str
) -> None:
    wal = handoff_module.InMemoryHashChainedHandoffWalV1()
    handoff = _handoff(wal=wal)
    prepared = handoff.prepare(**copy.deepcopy(handoff_inputs))
    command = prepared["protected_command"]
    handoff.finalize_offline(command, _terminal(command, "COMMITTED"))
    snapshot = [dict(record) for record in wal.export_restart_snapshot()]
    if mutation == "binding":
        snapshot[-1]["handoff_binding_sha256"] = "d" * 64
    else:
        snapshot[-1]["event_epoch"] = snapshot[0]["event_epoch"] - 1
    snapshot[-1]["record_sha256"] = handoff_module._receipt_sha256(
        snapshot[-1], "record_sha256"
    )

    with pytest.raises(handoff_module.HandoffWalIntegrityError):
        handoff_module.InMemoryHashChainedHandoffWalV1(snapshot)


def test_concurrent_prepare_appends_exactly_one_wal_record(handoff_inputs: dict) -> None:
    wal = handoff_module.InMemoryHashChainedHandoffWalV1()
    handoff = _handoff(wal=wal)
    inputs = copy.deepcopy(handoff_inputs)
    barrier = threading.Barrier(8)
    results: list[dict] = []
    result_lock = threading.Lock()

    def worker() -> None:
        barrier.wait()
        result = handoff.prepare(**inputs)
        with result_lock:
            results.append(result)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert all(not thread.is_alive() for thread in threads)
    assert len(results) == 8
    assert all(result["ok"] is True for result in results)
    assert sum(result["idempotent_replay"] is False for result in results) == 1
    assert wal.snapshot()["record_count"] == 1


def test_default_off_scope_mapping_and_wal_guards(handoff_inputs: dict) -> None:
    inputs = copy.deepcopy(handoff_inputs)
    default_result = handoff_module.DurableHandoffOfflineV1().prepare(**inputs)
    wrong_scope = handoff_module.DurableHandoffOfflineV1(
        config=handoff_module.DurableHandoffConfigV1(
            enabled=True, scope_attestation="wrong"
        )
    ).prepare(**inputs)
    bad_mapping_inputs = copy.deepcopy(inputs)
    bad_mapping_inputs["handoff_intent"] = None
    bad_mapping = _handoff().prepare(**bad_mapping_inputs)
    missing_wal = handoff_module.DurableHandoffOfflineV1(
        config=handoff_module.DurableHandoffConfigV1(
            enabled=True,
            scope_attestation=handoff_module.OFFLINE_DURABLE_HANDOFF_SCOPE_ATTESTATION_V1,
        ),
        clock=lambda: harness._NOW,
    ).prepare(**copy.deepcopy(inputs))

    assert default_result["status"] == "C3_DURABLE_HANDOFF_OFFLINE_DEFAULT_OFF"
    assert wrong_scope["status"] == "C3_DURABLE_HANDOFF_OFFLINE_SCOPE_REQUIRED"
    assert bad_mapping["reasons"] == ["HANDOFF_MAPPING_INPUTS_REQUIRED"]
    assert "HANDOFF_WAL_UNAVAILABLE" in missing_wal["reasons"]
    for result in (default_result, wrong_scope, bad_mapping, missing_wal):
        assert result["ok"] is False
        assert result["protected_command"] is None
        assert result["controller_invocation_allowed"] is False
        assert result["registry_write_allowed"] is False


def test_prepare_does_not_mutate_inputs(handoff_inputs: dict) -> None:
    inputs = copy.deepcopy(handoff_inputs)
    before = copy.deepcopy(inputs)

    result = _handoff().prepare(**inputs)

    assert result["ok"] is True
    assert inputs == before


def test_handoff_receipt_binds_all_authority_and_registry_hashes(
    handoff_inputs: dict,
) -> None:
    result = _handoff().prepare(**copy.deepcopy(handoff_inputs))
    command = result["protected_command"]
    receipt = result["handoff_receipt"]

    assert receipt["handoff_receipt_sha256"] == handoff_module._receipt_sha256(
        receipt, "handoff_receipt_sha256"
    )
    assert receipt["transaction_id"] == command.transaction_id
    assert receipt["idempotency_key"] == command.idempotency_key
    assert receipt["gateway_receipt_sha256"] == command.gateway_receipt_sha256
    assert receipt["authorization_receipt_sha256"] == command.authorization_receipt_sha256
    assert receipt["preview_receipt_sha256"] == command.preview_receipt_sha256
    assert receipt["source_registry_sha256"] == command.source_registry_sha256
    assert receipt["candidate_registry_sha256"] == command.candidate_registry_sha256
    assert receipt["changed_paths_sha256"] == command.changed_paths_sha256
    assert receipt["wal_state"] == "PREPARED"
    assert receipt["production_durability_verified"] is False
    assert receipt["controller_invocation_allowed"] is False
    assert receipt["registry_write_allowed"] is False


def test_handoff_modules_have_no_runtime_or_external_surface() -> None:
    modules = (handoff_module, harness)
    sources = [inspect.getsource(module) for module in modules]
    trees = [ast.parse(source) for source in sources]
    imported = {
        alias.name
        for tree in trees
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    source = "\n".join(sources)

    assert "main" not in imported
    assert "trade_registry_closed_identity_conflict_repair_runtime_operation_v1" not in imported
    runtime_module_name = (
        "trade_registry_closed_identity_conflict_repair_runtime_operation_v1"
    )
    assert all(
        getattr(value, "__name__", None) != runtime_module_name
        for module in modules
        for value in vars(module).values()
    )
    for token in (
        "Path(",
        "read_text(",
        "read_bytes(",
        "write_text(",
        "write_bytes(",
        "open(",
        "requests.",
        "httpx.",
        "subprocess",
        "os.environ",
        "controller.apply(",
        "save_registry(",
        "start_central_runtime_once(",
    ):
        assert token not in source
    assert not hasattr(handoff_module, "apply")
    assert not hasattr(handoff_module, "invoke")
    assert not hasattr(handoff_module, "activate")
    assert not hasattr(handoff_module, "serialize")
