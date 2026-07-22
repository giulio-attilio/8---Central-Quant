from __future__ import annotations

import ast
import importlib
import inspect
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

import account_client_order_id as authority


ROOT = Path(__file__).resolve().parents[1]
FACTUAL_ENTRY_CLIENT_ORDER_IDS = (
    "FALCON-LIVE-FALCON15-1784037618",  # 2026-07-14
    "FALCON-LIVE-FALCON15-1784124020",  # 2026-07-15
    "FALCON-LIVE-FALCON15-1784470538",  # 2026-07-19
)
LEGACY_DUPLICATED_DISASTER_STOP_ID = "FALCON-LIVE-FALCON15-178-DS"


class FakeLifetimeLedger:
    """Minimal persistent SET-NX ledger; intentionally has no expiry API."""

    def __init__(self, data=None):
        self.data = data if data is not None else {}
        self.set_calls = []
        self.get_calls = []

    def set_if_absent(self, redis_client, key, value, **kwargs):
        assert redis_client is self
        self.set_calls.append((key, value, dict(kwargs)))
        if key in self.data:
            return False
        self.data[key] = value
        return True

    def get_authoritative(self, redis_client, key, **kwargs):
        assert redis_client is self
        self.get_calls.append((key, dict(kwargs)))
        return self.data.get(key)


class ThreadSafeAuthorizationRaceLedger(FakeLifetimeLedger):
    """Thread-safe SET-NX ledger with a barrier on the authorization slot."""

    def __init__(self):
        super().__init__()
        self._lock = threading.RLock()
        self.authorization_barrier = None

    def set_if_absent(self, redis_client, key, value, **kwargs):
        assert redis_client is self
        barrier = self.authorization_barrier
        if (
            barrier is not None
            and key.startswith(authority.ACCOUNT_CLIENT_ORDER_AUTHORIZATION_PREFIX + ":")
        ):
            barrier.wait(timeout=10)
        with self._lock:
            self.set_calls.append((key, value, dict(kwargs)))
            if key in self.data:
                return False
            self.data[key] = value
            return True

    def get_authoritative(self, redis_client, key, **kwargs):
        assert redis_client is self
        with self._lock:
            self.get_calls.append((key, dict(kwargs)))
            return self.data.get(key)


class DroppedWriteLedger(FakeLifetimeLedger):
    """Reports SETNX success while omitting one selected persistence write."""

    def __init__(self, drop_call):
        super().__init__()
        self.drop_call = drop_call

    def set_if_absent(self, redis_client, key, value, **kwargs):
        assert redis_client is self
        self.set_calls.append((key, value, dict(kwargs)))
        if len(self.set_calls) == self.drop_call:
            return True
        if key in self.data:
            return False
        self.data[key] = value
        return True


class RaisingAfterPersistLedger(FakeLifetimeLedger):
    def __init__(self, raise_call):
        super().__init__()
        self.raise_call = raise_call

    def set_if_absent(self, redis_client, key, value, **kwargs):
        assert redis_client is self
        self.set_calls.append((key, value, dict(kwargs)))
        if key in self.data:
            return False
        self.data[key] = value
        if len(self.set_calls) == self.raise_call:
            raise ConnectionError("synthetic persistence acknowledgement loss")
        return True


def identity(
    *,
    role=authority.ROLE_INITIAL_DISASTER_STOP,
    lifecycle_id="LC-FALCON-SOL-1",
    symbol="SOLUSDT",
    side="LONG",
    attempt_id="ATTEMPT-0",
    attempt_sequence=0,
    entry_client_order_id="FALCON-LIVE-FALCON15-1784470538",
    entry_order_id="2078846000000000000",
    stop_revision=0,
    order_type="STOP_MARKET",
    canonical_operation_id=None,
    bot="FALCON",
):
    values = {
        "bot": bot,
        "role": role,
        "lifecycle_id": lifecycle_id,
        "symbol": symbol,
        "side": side,
        "attempt_id": attempt_id,
        "attempt_sequence": attempt_sequence,
        "entry_client_order_id": entry_client_order_id,
        "entry_order_id": entry_order_id,
        "stop_revision": stop_revision,
        "order_type": order_type,
    }
    if canonical_operation_id is not None:
        values["canonical_operation_id"] = canonical_operation_id
    return values


def reserve(ledger, values, *, client_order_id=None):
    return authority.reserve_account_client_order_attempt(
        values,
        client_order_id=client_order_id,
        redis_client=ledger,
        set_if_absent=ledger.set_if_absent,
        get_authoritative=ledger.get_authoritative,
        now=lambda: "2026-07-20T00:00:00+00:00",
    )


def claim(ledger, receipt):
    return authority.claim_account_client_order_send_authorization(
        receipt,
        expected_client_order_id=receipt["client_order_id"],
        redis_client=ledger,
        set_if_absent=ledger.set_if_absent,
        get_authoritative=ledger.get_authoritative,
        now=lambda: "2026-07-20T00:00:01+00:00",
    )


def record_outcome(
    ledger,
    receipt,
    outcome_state,
    *,
    reason=None,
    failure_phase=None,
    now=None,
):
    return authority.record_account_client_order_attempt_outcome(
        receipt,
        outcome_state=outcome_state,
        reason=reason,
        failure_phase=failure_phase,
        redis_client=ledger,
        set_if_absent=ledger.set_if_absent,
        get_authoritative=ledger.get_authoritative,
        now=now,
    )


def consume_pre_send(
    ledger,
    receipt,
    *,
    reason="PRE_SEND_VALIDATION_FAILED",
    failure_phase="PRE_SEND_VALIDATION",
    now=None,
):
    return authority.consume_account_client_order_attempt_pre_send(
        receipt,
        reason=reason,
        failure_phase=failure_phase,
        redis_client=ledger,
        set_if_absent=ledger.set_if_absent,
        get_authoritative=ledger.get_authoritative,
        now=now,
    )


def factual_not_created_reconciler(
    *,
    source="FACTUAL_BROKER_QUERY",
    reconciled_at="2026-07-20T00:02:00Z",
    **updates,
):
    def reconcile(request):
        result = {
            "read_only": True,
            "query_complete": True,
            "order_found": False,
            "fills_found": False,
            "ambiguous": False,
            "reconciliation_status": "NOT_CREATED",
            "canonical_operation_id": request["canonical_operation_id"],
            "prior_attempt_id": request["prior_attempt_id"],
            "queried_client_order_id": request["prior_client_order_id"],
            "evidence_source": source,
            "reconciled_at": reconciled_at,
        }
        result.update(updates)
        return result

    return reconcile


def test_factual_14_15_19_entries_generate_distinct_account_wide_stop_ids():
    generated = {
        authority.generate_account_client_order_id(
            **identity(
                lifecycle_id=f"LC-{entry_id}",
                entry_client_order_id=entry_id,
                entry_order_id=f"ORDER-{index}",
                attempt_id=f"ATTEMPT-{index}",
            )
        )
        for index, entry_id in enumerate(FACTUAL_ENTRY_CLIENT_ORDER_IDS, 1)
    }

    assert len(generated) == 3
    assert LEGACY_DUPLICATED_DISASTER_STOP_ID not in generated
    assert all(item.startswith("FDS1-") for item in generated)
    assert all(len(item) <= authority.ACCOUNT_CLIENT_ORDER_ID_MAX_LENGTH for item in generated)


def test_ids_are_uppercase_safe_and_case_insensitive_at_account_boundary():
    generated = authority.generate_account_client_order_id(**identity())

    assert generated == generated.upper()
    assert authority.normalize_account_client_order_id(generated.lower()) == generated
    assert authority.account_client_order_id_ledger_key(
        generated.lower()
    ) == authority.account_client_order_id_ledger_key(generated.upper())
    assert authority.is_valid_account_client_order_id(generated.lower()) is True


def test_lowercase_and_uppercase_forms_share_one_ledger_slot_and_detect_collision():
    values = identity()
    generated = authority.generate_account_client_order_id(**values)
    key = authority.account_client_order_id_ledger_key(generated.upper())
    ledger = FakeLifetimeLedger(
        {
            key: {
                "client_order_id": generated.lower(),
                "canonical_operation_id": "OP1-OTHER",
                "attempt_id": "OTHER-ATTEMPT",
                "attempt_identity_hash": "OTHER-HASH",
                "state": "RESERVED_PRE_SEND",
                "lifetime": True,
            }
        }
    )

    result = reserve(ledger, values, client_order_id=generated.lower())

    assert result["status"] == "CLIENT_ORDER_ID_COLLISION_DETECTED"
    assert result["collision_detected"] is True
    assert result["send_allowed"] is False
    assert result["client_order_id"] == generated.upper()


@pytest.mark.parametrize(
    "role,namespace",
    list(authority.ACCOUNT_CLIENT_ORDER_ID_ROLE_NAMESPACES.items()),
)
def test_each_account_wide_role_uses_its_namespace(role, namespace):
    generated = authority.generate_account_client_order_id(
        **identity(role=role, lifecycle_id=f"LC-{role}")
    )

    assert generated.startswith(f"{namespace}-")
    assert len(generated) <= 32


def test_symbols_roles_and_order_types_are_part_of_account_wide_identity():
    base = authority.generate_account_client_order_id(**identity())
    other_symbol = authority.generate_account_client_order_id(
        **identity(symbol="BTCUSDT")
    )
    other_role = authority.generate_account_client_order_id(
        **identity(role=authority.ROLE_TP50_CLOSE)
    )
    other_order_type = authority.generate_account_client_order_id(
        **identity(order_type="MARKET")
    )

    assert len({base, other_symbol, other_role, other_order_type}) == 4


def test_supplied_operation_id_cannot_override_immutable_operation_identity():
    ledger = FakeLifetimeLedger()
    values = identity()
    canonical = authority.canonical_account_order_attempt_identity(**values)

    mismatched = reserve(
        ledger,
        {
            **values,
            "canonical_operation_id": "OP1-" + "F" * 64,
            "attempt_id": "ATTEMPT-OTHER",
        },
    )

    assert canonical["canonical_operation_id"].startswith("OP1-")
    assert mismatched["status"] == "CLIENT_ORDER_IDENTITY_INVALID"
    assert mismatched["send_allowed"] is False
    assert ledger.set_calls == []


def test_symbol_side_and_text_normalization_is_stable():
    canonical = authority.generate_account_client_order_id(**identity())
    aliased = authority.generate_account_client_order_id(
        **identity(
            bot="falcon",
            role="initial_disaster_stop",
            lifecycle_id="lc-falcon-sol-1",
            symbol="sol/usdt:usdt",
            side="buy",
            attempt_id="attempt-0",
            entry_client_order_id="falcon-live-falcon15-1784470538",
            entry_order_id="2078846000000000000",
            order_type="stop_market",
        )
    )

    assert aliased == canonical


def test_large_account_wide_sample_has_no_observed_collision():
    generated = {
        authority.generate_account_client_order_id(
            **identity(
                bot=f"BOT-{index % 13}",
                lifecycle_id=f"LC-{index}",
                symbol=("SOLUSDT", "BTCUSDT", "ETHUSDT", "XRPUSDT")[index % 4],
                side="LONG" if index % 2 == 0 else "SHORT",
                attempt_id=f"ATTEMPT-{index}",
                entry_client_order_id=f"ENTRY-{index}",
                entry_order_id=f"ORDER-{index}",
                stop_revision=index % 50,
            )
        )
        for index in range(10_000)
    }

    assert len(generated) == 10_000


def test_reservation_uses_append_only_set_nx_without_ttl_or_delete():
    ledger = FakeLifetimeLedger()
    result = reserve(ledger, identity())

    assert result["status"] == "RESERVED_UNIQUE"
    assert result["send_allowed"] is True
    assert result["persistent"] is True
    assert len(ledger.set_calls) == 4
    for _key, _value, kwargs in ledger.set_calls:
        assert set(kwargs) == {"caller"}
        assert not ({"ttl", "ex", "px", "expires", "expire_at"} & set(kwargs))

    tree = ast.parse(inspect.getsource(authority))
    called_attributes = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert called_attributes.isdisjoint(
        {"delete", "unlink", "expire", "expireat", "pexpire", "pexpireat"}
    )
    assert result["sequence_slot_unique"] is True
    assert result["reservation_readback"]["integral"] is True
    assert all(result["reservation_readback"]["matches"].values())


@pytest.mark.parametrize(
    "drop_call,missing_record",
    [
        (1, "sequence"),
        (2, "client_order_id"),
        (3, "attempt"),
        (4, "operation"),
    ],
)
def test_reservation_never_succeeds_after_partial_or_unconfirmed_setnx(
    drop_call,
    missing_record,
):
    ledger = DroppedWriteLedger(drop_call)

    result = reserve(ledger, identity())
    retry = reserve(ledger, identity())

    assert result["ok"] is False
    assert result["send_allowed"] is False
    assert result["status"] == "PARTIAL_RESERVATION_REQUIRES_RECONCILIATION"
    assert result["reservation_readback"]["integral"] is False
    assert missing_record in result["reservation_readback"]["missing"]
    if drop_call == 1:
        # Authoritative read-back proved that no slot or ID was persisted, so
        # a later independent reservation may safely acquire the untouched slot.
        assert retry["status"] == "RESERVED_UNIQUE"
        assert retry["send_allowed"] is True
    else:
        assert retry["send_allowed"] is False
        assert retry["status"] == "PARTIAL_RESERVATION_REQUIRES_RECONCILIATION"


@pytest.mark.parametrize(
    "raise_call,readback_integral",
    [
        (1, False),
        (2, False),
        (3, False),
        # The final operation record was persisted before its acknowledgement
        # was lost.  Readback can therefore be integral, but the ambiguous
        # write still must never authorize the send in this invocation.
        (4, True),
    ],
)
def test_reservation_exception_after_a_persisted_write_is_explicitly_partial(
    raise_call,
    readback_integral,
):
    ledger = RaisingAfterPersistLedger(raise_call)

    result = reserve(ledger, identity())

    assert result["ok"] is False
    assert result["send_allowed"] is False
    assert result["status"] == "PARTIAL_RESERVATION_REQUIRES_RECONCILIATION"
    assert result["persistent"] is True
    assert result["reservation_readback"]["integral"] is readback_integral
    assert result["reconciliation_required"] is True


def test_same_persisted_attempt_is_idempotent_evidence_but_never_resend_permission():
    ledger = FakeLifetimeLedger()
    first = reserve(ledger, identity())
    second = reserve(ledger, identity())

    assert first["send_allowed"] is True
    assert second["ok"] is True
    assert second["same_attempt"] is True
    assert second["client_order_id_unique"] is True
    assert second["send_allowed"] is False
    assert second["status"] == "CLIENT_ORDER_ID_ALREADY_RESERVED_RECONCILIATION_REQUIRED"


def test_operation_sequence_slot_rejects_a_different_attempt_id_at_same_sequence():
    ledger = FakeLifetimeLedger()
    first_identity = identity(attempt_id="ATTEMPT-A", attempt_sequence=0)
    second_identity = identity(attempt_id="ATTEMPT-B", attempt_sequence=0)

    first = reserve(ledger, first_identity)
    second = reserve(ledger, second_identity)
    second_generated_id = authority.generate_account_client_order_id(**second_identity)
    second_id_key = authority.account_client_order_id_ledger_key(second_generated_id)

    assert first["status"] == "RESERVED_UNIQUE"
    assert second["status"] == "CLIENT_ORDER_ATTEMPT_SEQUENCE_SLOT_COLLISION"
    assert second["send_allowed"] is False
    assert second["collision_detected"] is True
    assert second_id_key not in ledger.data
    sequence_records = [
        json.loads(value)
        for key, value in ledger.data.items()
        if key.startswith(authority.ACCOUNT_CLIENT_ORDER_SEQUENCE_PREFIX)
    ]
    assert len(sequence_records) == 1
    assert sequence_records[0]["attempt_id"] == "ATTEMPT-A"


def test_send_claim_is_permanent_and_same_receipt_cannot_authorize_second_send():
    ledger = FakeLifetimeLedger()
    receipt = reserve(ledger, identity())

    first = claim(ledger, receipt)
    second = claim(ledger, receipt)
    passive_after_claim = authority.verify_account_client_order_id_reservation(
        receipt,
        expected_client_order_id=receipt["client_order_id"],
        redis_client=ledger,
        get_authoritative=ledger.get_authoritative,
    )

    assert first["status"] == "SEND_CLAIMED"
    assert first["send_allowed"] is True
    assert first["send_claimed"] is True
    assert second["status"] == "CLIENT_ORDER_ATTEMPT_SEND_ALREADY_CLAIMED"
    assert second["send_allowed"] is False
    assert passive_after_claim["status"] == "CLIENT_ORDER_ATTEMPT_SEND_ALREADY_CLAIMED"
    assert passive_after_claim["send_allowed"] is False
    assert first["attempt_disposition"] == authority.ATTEMPT_DISPOSITION_SEND_CLAIMED
    assert first["send_claim_key"] == first["attempt_disposition_key"]
    assert not any(
        key.startswith(authority.ACCOUNT_CLIENT_ORDER_SEND_CLAIM_PREFIX)
        for key in ledger.data
    )
    assert not any(
        {"ttl", "ex", "px", "expires", "expire_at"} & set(kwargs)
        for _key, _value, kwargs in ledger.set_calls
    )


def test_custom_account_namespace_is_preserved_during_authoritative_verification():
    ledger = FakeLifetimeLedger()
    values = {**identity(), "account_namespace": "BINGX-SUBACCOUNT-A"}
    receipt = reserve(ledger, values)

    verified = authority.verify_account_client_order_id_reservation(
        receipt,
        expected_client_order_id=receipt["client_order_id"],
        redis_client=ledger,
        get_authoritative=ledger.get_authoritative,
    )

    assert receipt["account_namespace"] == "BINGX-SUBACCOUNT-A"
    assert verified["account_namespace"] == "BINGX-SUBACCOUNT-A"
    assert verified["send_allowed"] is True


@pytest.mark.parametrize(
    "outcome",
    [
        "PRE_SEND_FAILED_ATTEMPT_CONSUMED",
        "CREATE_ORDER_OUTCOME_UNKNOWN",
        "ACKNOWLEDGED",
        "REJECTED",
        "FAILED",
        "CANCELED",
        "FILLED",
        "TERMINAL",
    ],
)
def test_outcome_never_releases_or_reauthorizes_the_consumed_id(outcome):
    ledger = FakeLifetimeLedger()
    receipt = reserve(ledger, identity())
    if outcome != "PRE_SEND_FAILED_ATTEMPT_CONSUMED":
        assert claim(ledger, receipt)["status"] == "SEND_CLAIMED"
    recorded = record_outcome(
        ledger,
        receipt,
        outcome,
        now=lambda: "2026-07-20T00:01:00+00:00",
    )
    retry = reserve(ledger, identity())

    assert recorded["ok"] is True
    assert recorded["id_released"] is False
    assert recorded["attempt_disposition"] in {
        authority.ATTEMPT_DISPOSITION_PRE_SEND_CONSUMED,
        authority.ATTEMPT_DISPOSITION_SEND_CLAIMED,
    }
    assert retry["send_allowed"] is False
    assert retry["status"] == "CLIENT_ORDER_ID_ALREADY_RESERVED_RECONCILIATION_REQUIRED"


def test_same_outcome_retry_is_idempotent_even_when_observation_time_changes():
    ledger = FakeLifetimeLedger()
    receipt = reserve(ledger, identity())
    assert claim(ledger, receipt)["status"] == "SEND_CLAIMED"

    first = record_outcome(
        ledger,
        receipt,
        "ACKNOWLEDGED",
        now=lambda: "2026-07-20T00:01:00+00:00",
    )
    records_after_first = dict(ledger.data)
    second = record_outcome(
        ledger,
        receipt,
        "ACKNOWLEDGED",
        now=lambda: "2026-07-20T00:02:00+00:00",
    )

    assert first["ok"] is True
    assert first["status"] == "ACKNOWLEDGED"
    assert first["idempotent"] is False
    assert second["ok"] is True
    assert second["status"] == "OUTCOME_ALREADY_RECORDED"
    assert second["idempotent"] is True
    assert second["persistent"] is True
    assert second["id_released"] is False
    assert ledger.data == records_after_first


def test_positive_outcome_setnx_without_authoritative_readback_is_not_persisted():
    ledger = FakeLifetimeLedger()
    receipt = reserve(ledger, identity())
    assert claim(ledger, receipt)["status"] == "SEND_CLAIMED"

    def drop_outcome_write(redis_client, key, value, **kwargs):
        if key.startswith(authority.ACCOUNT_CLIENT_ORDER_OUTCOME_PREFIX + ":"):
            ledger.set_calls.append((key, value, dict(kwargs)))
            return True
        return ledger.set_if_absent(redis_client, key, value, **kwargs)

    result = authority.record_account_client_order_attempt_outcome(
        receipt,
        outcome_state="ACKNOWLEDGED",
        redis_client=ledger,
        set_if_absent=drop_outcome_write,
        get_authoritative=ledger.get_authoritative,
    )

    assert result["ok"] is False
    assert result["status"] == "ATTEMPT_OUTCOME_PERSISTENCE_ERROR"
    assert result["persistent"] is False
    assert result["reconciliation_required"] is True
    assert result["id_released"] is False


def test_pre_send_consumed_and_send_claimed_share_one_exclusive_disposition_slot():
    pre_send_ledger = FakeLifetimeLedger()
    pre_send_receipt = reserve(pre_send_ledger, identity())
    pre_send = consume_pre_send(
        pre_send_ledger,
        pre_send_receipt,
    )
    blocked_claim = claim(pre_send_ledger, pre_send_receipt)
    pre_send_key = authority.account_client_order_disposition_key(
        pre_send_receipt["canonical_operation_id"], pre_send_receipt["attempt_id"]
    )

    assert pre_send["attempt_disposition"] == authority.ATTEMPT_DISPOSITION_PRE_SEND_CONSUMED
    assert blocked_claim["status"] == "CLIENT_ORDER_ATTEMPT_PRE_SEND_CONSUMED"
    assert blocked_claim["send_allowed"] is False
    assert json.loads(pre_send_ledger.data[pre_send_key])["disposition"] == "PRE_SEND_CONSUMED"

    claimed_ledger = FakeLifetimeLedger()
    claimed_receipt = reserve(claimed_ledger, identity())
    assert claim(claimed_ledger, claimed_receipt)["status"] == "SEND_CLAIMED"
    blocked_pre_send = consume_pre_send(
        claimed_ledger,
        claimed_receipt,
    )
    claimed_key = authority.account_client_order_disposition_key(
        claimed_receipt["canonical_operation_id"], claimed_receipt["attempt_id"]
    )

    assert blocked_pre_send["status"] == "ATTEMPT_DISPOSITION_CONFLICT"
    assert blocked_pre_send["ok"] is False
    assert json.loads(claimed_ledger.data[claimed_key])["disposition"] == "SEND_CLAIMED"


def test_pre_send_consume_is_idempotent_only_for_the_same_safe_evidence():
    ledger = FakeLifetimeLedger()
    receipt = reserve(ledger, identity())

    first = consume_pre_send(
        ledger,
        receipt,
        reason="LOCAL_VALIDATION_FAILED",
        failure_phase="PRE_SEND_CONTEXT_VALIDATION",
        now=lambda: "2026-07-20T00:01:00Z",
    )
    same = consume_pre_send(
        ledger,
        receipt,
        reason="LOCAL_VALIDATION_FAILED",
        failure_phase="PRE_SEND_CONTEXT_VALIDATION",
        now=lambda: "2026-07-20T00:02:00Z",
    )
    different = consume_pre_send(
        ledger,
        receipt,
        reason="OTHER_LOCAL_FAILURE",
        failure_phase="PRE_SEND_CONTEXT_VALIDATION",
    )

    assert first["status"] == "PRE_SEND_FAILED_ATTEMPT_CONSUMED"
    assert first["idempotent"] is False
    assert same["status"] == "PRE_SEND_CONSUMPTION_ALREADY_RECORDED"
    assert same["idempotent"] is True
    assert different["status"] == "ATTEMPT_PRE_SEND_EVIDENCE_MISMATCH"
    assert different["send_allowed"] is False


@pytest.mark.parametrize(
    "reason,failure_phase",
    [
        ("raw exception: secret value", "PRE_SEND"),
        ("VALID_REASON", "phase\nwith-newline"),
        ("X" * 513, "PRE_SEND"),
        (123, "PRE_SEND"),
    ],
)
def test_pre_send_consume_rejects_unsafe_reason_or_failure_phase(
    reason,
    failure_phase,
):
    ledger = FakeLifetimeLedger()
    receipt = reserve(ledger, identity())
    disposition_key = authority.account_client_order_disposition_key(
        receipt["canonical_operation_id"], receipt["attempt_id"]
    )

    result = consume_pre_send(
        ledger,
        receipt,
        reason=reason,
        failure_phase=failure_phase,
    )

    assert result["ok"] is False
    assert result["status"] == "ATTEMPT_PRE_SEND_CONSUMPTION_ERROR"
    assert result["send_allowed"] is False
    assert result["error_type"] == "ValueError"
    assert disposition_key not in ledger.data


def test_record_pre_send_outcome_delegates_to_public_consume_helper(monkeypatch):
    ledger = FakeLifetimeLedger()
    receipt = reserve(ledger, identity())
    calls = []

    def probe(reservation, **kwargs):
        calls.append((reservation, kwargs))
        return {
            "ok": True,
            "status": "PRE_SEND_FAILED_ATTEMPT_CONSUMED",
            "idempotent": False,
            "reason": kwargs["reason"],
            "failure_phase": kwargs["failure_phase"],
        }

    monkeypatch.setattr(
        authority,
        "consume_account_client_order_attempt_pre_send",
        probe,
    )

    result = record_outcome(
        ledger,
        receipt,
        "PRE_SEND_FAILED_ATTEMPT_CONSUMED",
        reason="LOCAL_CONTEXT_REJECTED",
        failure_phase="PRE_SEND_CONTEXT_VALIDATION",
    )

    assert result["ok"] is True
    assert len(calls) == 1
    assert calls[0][0] == receipt
    assert calls[0][1]["reason"] == "LOCAL_CONTEXT_REJECTED"
    assert calls[0][1]["failure_phase"] == "PRE_SEND_CONTEXT_VALIDATION"


def test_pre_send_consume_requires_integral_authoritative_reservation():
    ledger = FakeLifetimeLedger()
    receipt = reserve(ledger, identity())
    attempt_key = next(
        key
        for key in ledger.data
        if key.startswith(authority.ACCOUNT_CLIENT_ORDER_ATTEMPT_PREFIX)
    )
    del ledger.data[attempt_key]
    disposition_key = authority.account_client_order_disposition_key(
        receipt["canonical_operation_id"], receipt["attempt_id"]
    )

    result = consume_pre_send(ledger, receipt)

    assert result["status"] == "PARTIAL_RESERVATION_REQUIRES_RECONCILIATION"
    assert result["send_allowed"] is False
    assert result["reservation_readback"]["integral"] is False
    assert disposition_key not in ledger.data


def test_pre_send_consume_requires_authoritative_disposition_readback():
    ledger = DroppedWriteLedger(drop_call=5)
    receipt = reserve(ledger, identity())

    result = consume_pre_send(ledger, receipt)

    assert result["ok"] is False
    assert result["status"] == "ATTEMPT_DISPOSITION_PERSISTENCE_ERROR"
    assert result["send_allowed"] is False
    assert result["persistent"] is False


def test_post_send_outcome_requires_authoritative_send_disposition():
    ledger = FakeLifetimeLedger()
    receipt = reserve(ledger, identity())

    result = record_outcome(ledger, receipt, "ACKNOWLEDGED")

    assert result["ok"] is False
    assert result["status"] == "ATTEMPT_SEND_NOT_CLAIMED"
    assert result["reconciliation_required"] is True


def test_verification_reads_every_outcome_slot_and_blocks_missing_disposition():
    ledger = FakeLifetimeLedger()
    receipt = reserve(ledger, identity())
    outcome_key = authority._identity_key(
        authority.ACCOUNT_CLIENT_ORDER_OUTCOME_PREFIX,
        receipt["canonical_operation_id"],
        f"{receipt['attempt_id']}:ACKNOWLEDGED",
    )
    ledger.data[outcome_key] = json.dumps(
        {
            "status": "ACKNOWLEDGED",
            "canonical_operation_id": receipt["canonical_operation_id"],
            "attempt_id": receipt["attempt_id"],
            "attempt_identity_hash": receipt["attempt_identity_hash"],
            "client_order_id": receipt["client_order_id"],
            "lifetime": True,
            "id_released": False,
        }
    )
    ledger.get_calls.clear()

    result = authority.verify_account_client_order_id_reservation(
        receipt,
        expected_client_order_id=receipt["client_order_id"],
        redis_client=ledger,
        get_authoritative=ledger.get_authoritative,
    )

    queried_outcome_keys = {
        key
        for key, _kwargs in ledger.get_calls
        if key.startswith(authority.ACCOUNT_CLIENT_ORDER_OUTCOME_PREFIX)
    }
    assert len(queried_outcome_keys) == 8
    assert result["ok"] is False
    assert result["status"] == "CLIENT_ORDER_ATTEMPT_OUTCOME_DISPOSITION_CONFLICT"
    assert result["outcomes_found"] == ["ACKNOWLEDGED"]
    assert result["send_allowed"] is False


def test_verification_blocks_pre_send_outcome_after_send_disposition():
    ledger = FakeLifetimeLedger()
    receipt = reserve(ledger, identity())
    assert claim(ledger, receipt)["status"] == "SEND_CLAIMED"
    outcome_key = authority._identity_key(
        authority.ACCOUNT_CLIENT_ORDER_OUTCOME_PREFIX,
        receipt["canonical_operation_id"],
        f"{receipt['attempt_id']}:PRE_SEND_FAILED_ATTEMPT_CONSUMED",
    )
    ledger.data[outcome_key] = json.dumps(
        {
            "status": "PRE_SEND_FAILED_ATTEMPT_CONSUMED",
            "canonical_operation_id": receipt["canonical_operation_id"],
            "attempt_id": receipt["attempt_id"],
            "attempt_identity_hash": receipt["attempt_identity_hash"],
            "client_order_id": receipt["client_order_id"],
            "attempt_disposition": authority.ATTEMPT_DISPOSITION_PRE_SEND_CONSUMED,
            "lifetime": True,
            "id_released": False,
        }
    )

    result = authority.verify_account_client_order_id_reservation(
        receipt,
        expected_client_order_id=receipt["client_order_id"],
        redis_client=ledger,
        get_authoritative=ledger.get_authoritative,
    )

    assert result["status"] == "CLIENT_ORDER_ATTEMPT_OUTCOME_DISPOSITION_CONFLICT"
    assert result["outcome_conflicts"] == ["PRE_SEND_FAILED_ATTEMPT_CONSUMED"]
    assert result["send_allowed"] is False


@pytest.mark.parametrize(
    "prefix,projection_name",
    [
        (authority.ACCOUNT_CLIENT_ORDER_ID_LEDGER_PREFIX, "client_order_id"),
        (authority.ACCOUNT_CLIENT_ORDER_ATTEMPT_PREFIX, "attempt"),
        (authority.ACCOUNT_CLIENT_ORDER_OPERATION_PREFIX, "operation"),
        (authority.ACCOUNT_CLIENT_ORDER_SEQUENCE_PREFIX, "sequence"),
    ],
)
def test_verification_requires_every_authoritative_reservation_record(
    prefix,
    projection_name,
):
    ledger = FakeLifetimeLedger()
    receipt = reserve(ledger, identity())
    key = next(key for key in ledger.data if key.startswith(prefix))
    del ledger.data[key]

    result = authority.verify_account_client_order_id_reservation(
        receipt,
        expected_client_order_id=receipt["client_order_id"],
        redis_client=ledger,
        get_authoritative=ledger.get_authoritative,
    )

    assert result["status"] == "PARTIAL_RESERVATION_REQUIRES_RECONCILIATION"
    assert result["reservation_readback"]["integral"] is False
    assert result["reservation_readback"]["present"][projection_name] is False
    assert result["send_allowed"] is False


def test_unknown_outcome_blocks_lifecycle_and_account_attempt_until_reconciliation():
    ledger = FakeLifetimeLedger()
    receipt = reserve(ledger, identity())
    assert claim(ledger, receipt)["status"] == "SEND_CLAIMED"

    outcome = record_outcome(
        ledger,
        receipt,
        "CREATE_ORDER_OUTCOME_UNKNOWN",
        now=lambda: "2026-07-20T00:01:00+00:00",
    )
    same_attempt = reserve(ledger, identity())
    next_attempt = reserve(
        ledger,
        identity(
            canonical_operation_id=receipt["canonical_operation_id"],
            attempt_id="ATTEMPT-1",
            attempt_sequence=1,
        ),
    )

    assert outcome["ok"] is True
    assert outcome["status"] == "CREATE_ORDER_OUTCOME_UNKNOWN"
    assert outcome["client_order_id"] == receipt["client_order_id"]
    assert outcome["id_released"] is False
    assert outcome["persistent"] is True
    assert outcome["idempotent"] is False
    assert outcome["lifecycle_id"] == "LC-FALCON-SOL-1"
    assert outcome["lifecycle_blocked"] is True
    assert outcome["reconciliation_required"] is True
    assert same_attempt["send_allowed"] is False
    assert same_attempt["status"] == "CLIENT_ORDER_ID_ALREADY_RESERVED_RECONCILIATION_REQUIRED"
    assert next_attempt["send_allowed"] is False
    assert next_attempt["status"] == "CLIENT_ORDER_ATTEMPT_NOT_AUTHORIZED_BY_RECONCILIATION"


@pytest.mark.parametrize(
    "field,tampered_value",
    [
        ("bot", "PREDATOR"),
        ("role", authority.ROLE_REPLACEMENT_STOP),
        ("lifecycle_id", "LC-FALCON-SOL-OTHER"),
        ("symbol", "BTCUSDT"),
        ("side", "SHORT"),
        ("entry_client_order_id", "ENTRY-OTHER"),
        ("entry_order_id", "ORDER-OTHER"),
        ("stop_revision", 1),
        ("order_type", "MARKET"),
    ],
)
def test_authoritative_verification_rejects_every_tampered_context_field(
    field,
    tampered_value,
):
    ledger = FakeLifetimeLedger()
    receipt = reserve(ledger, identity())
    tampered = {**receipt, field: tampered_value}

    result = authority.verify_account_client_order_id_reservation(
        tampered,
        expected_client_order_id=receipt["client_order_id"],
        redis_client=ledger,
        get_authoritative=ledger.get_authoritative,
    )

    assert result["ok"] is False
    assert result["send_allowed"] is False
    assert result["status"] == "CLIENT_ORDER_ID_LEDGER_MISMATCH"
    assert result["reconciliation_required"] is True


def test_restart_does_not_release_terminal_attempt():
    persisted = {}
    before_restart = FakeLifetimeLedger(persisted)
    receipt = reserve(before_restart, identity())
    assert claim(before_restart, receipt)["status"] == "SEND_CLAIMED"
    record_outcome(before_restart, receipt, "TERMINAL")

    after_restart = FakeLifetimeLedger(persisted)
    retry = reserve(after_restart, identity())

    assert retry["send_allowed"] is False
    assert retry["persistent"] is True
    assert retry["same_attempt"] is True


def test_authority_failure_is_fail_closed():
    ledger = FakeLifetimeLedger()

    def unavailable(*_args, **_kwargs):
        raise ConnectionError("authority unavailable")

    result = authority.reserve_account_client_order_attempt(
        identity(),
        redis_client=ledger,
        set_if_absent=unavailable,
        get_authoritative=ledger.get_authoritative,
    )

    assert result["ok"] is False
    assert result["send_allowed"] is False
    assert result["client_order_id_unique"] is False
    assert result["persistent"] is False
    assert result["status"] == "CLIENT_ORDER_ID_AUTHORITY_ERROR"
    assert result["error_type"] == "ConnectionError"


def test_missing_authority_is_fail_closed_without_importing_operational_modules(monkeypatch):
    monkeypatch.setattr(authority, "_default_redis_client", lambda: None)
    before = set(sys.modules)

    result = authority.reserve_account_client_order_attempt(identity())

    assert result["status"] == "CLIENT_ORDER_ID_AUTHORITY_UNAVAILABLE"
    assert result["send_allowed"] is False
    assert "broker" not in set(sys.modules) - before
    assert "redis_bandwidth" not in set(sys.modules) - before
    assert "upstash_redis" not in set(sys.modules) - before


def test_overlength_id_is_blocked_and_never_truncated_or_reserved():
    ledger = FakeLifetimeLedger()
    overlength = "X" * 33

    with pytest.raises(ValueError, match="CLIENT_ORDER_ID_INVALID_LENGTH"):
        authority.normalize_account_client_order_id(overlength)
    result = reserve(ledger, identity(), client_order_id=overlength)

    assert result["status"] == "CLIENT_ORDER_ID_INVALID_LENGTH"
    assert result["send_allowed"] is False
    assert result["client_order_id"] != overlength[:32]
    assert ledger.set_calls == []


def test_new_attempt_requires_explicit_not_created_authorization_and_gets_new_id():
    ledger = FakeLifetimeLedger()
    first_identity = identity()
    first = reserve(ledger, first_identity)
    operation_id = first["canonical_operation_id"]
    second_identity = identity(
        attempt_id="ATTEMPT-1",
        attempt_sequence=1,
        canonical_operation_id=operation_id,
    )
    unauthorized = reserve(ledger, second_identity)

    assert unauthorized["status"] == "CLIENT_ORDER_ATTEMPT_NOT_AUTHORIZED_BY_RECONCILIATION"
    assert unauthorized["send_allowed"] is False

    assert claim(ledger, first)["status"] == "SEND_CLAIMED"
    assert record_outcome(
        ledger,
        first,
        "CREATE_ORDER_OUTCOME_UNKNOWN",
        now=lambda: "2026-07-20T00:01:00Z",
    )["status"] == "CREATE_ORDER_OUTCOME_UNKNOWN"

    authorization = authority.authorize_account_client_order_next_attempt(
        canonical_operation_id=operation_id,
        prior_attempt_id="ATTEMPT-0",
        next_attempt_id="ATTEMPT-1",
        next_attempt_sequence=1,
        reconciliation_status="NOT_CREATED",
        evidence_source="FACTUAL_BROKER_QUERY",
        reconciled_at="2026-07-20T00:02:00Z",
        redis_client=ledger,
        set_if_absent=ledger.set_if_absent,
        get_authoritative=ledger.get_authoritative,
        factual_reconciler=factual_not_created_reconciler(),
    )
    second = reserve(ledger, second_identity)

    assert authorization["status"] == "RECONCILED_NEW_ATTEMPT_AUTHORIZED"
    assert authorization["send_allowed"] is False
    assert second["status"] == "RESERVED_UNIQUE"
    assert second["send_allowed"] is True
    assert second["attempt_sequence"] == 1
    assert second["client_order_id"] != first["client_order_id"]


def test_timeout_blocks_old_and_new_automatic_attempts_until_factual_authorization():
    ledger = FakeLifetimeLedger()
    first = reserve(ledger, identity())
    assert claim(ledger, first)["status"] == "SEND_CLAIMED"
    outcome = record_outcome(ledger, first, "CREATE_ORDER_OUTCOME_UNKNOWN")
    same_attempt = reserve(ledger, identity())
    next_attempt = reserve(
        ledger,
        identity(
            canonical_operation_id=first["canonical_operation_id"],
            attempt_id="ATTEMPT-1",
            attempt_sequence=1,
        ),
    )

    assert outcome["id_released"] is False
    assert same_attempt["send_allowed"] is False
    assert next_attempt["send_allowed"] is False
    assert next_attempt["status"] == "CLIENT_ORDER_ATTEMPT_NOT_AUTHORIZED_BY_RECONCILIATION"


def _claimed_unknown_attempt(ledger):
    receipt = reserve(ledger, identity())
    assert claim(ledger, receipt)["status"] == "SEND_CLAIMED"
    assert record_outcome(
        ledger,
        receipt,
        "CREATE_ORDER_OUTCOME_UNKNOWN",
        now=lambda: "2026-07-20T00:01:00Z",
    )["status"] == "CREATE_ORDER_OUTCOME_UNKNOWN"
    return receipt


def _authorize_attempt_one(ledger, receipt, **updates):
    parameters = {
        "canonical_operation_id": receipt["canonical_operation_id"],
        "prior_attempt_id": receipt["attempt_id"],
        "next_attempt_id": "ATTEMPT-1",
        "next_attempt_sequence": 1,
        "reconciliation_status": "NOT_CREATED",
        "evidence_source": "FACTUAL_BROKER_QUERY",
        "reconciled_at": "2026-07-20T00:02:00Z",
        "redis_client": ledger,
        "set_if_absent": ledger.set_if_absent,
        "get_authoritative": ledger.get_authoritative,
    }
    parameters.update(updates)
    return authority.authorize_account_client_order_next_attempt(**parameters)


def test_unknown_outcome_rejects_not_created_strings_without_factual_reader():
    ledger = FakeLifetimeLedger()
    receipt = _claimed_unknown_attempt(ledger)

    result = _authorize_attempt_one(ledger, receipt)

    assert result["ok"] is False
    assert result["status"] == "FACTUAL_READ_ONLY_RECONCILER_REQUIRED"
    assert result["send_allowed"] is False


@pytest.mark.parametrize(
    "evidence_update",
    [
        {"read_only": False},
        {"query_complete": False},
        {"order_found": True},
        {"fills_found": True},
        {"ambiguous": True},
        {"queried_client_order_id": "FDS1-AAAAAAAAAAAAAAAAAAAAAAAA"},
        {"canonical_operation_id": "OP1-OTHER"},
        {"prior_attempt_id": "OTHER-ATTEMPT"},
    ],
)
def test_unknown_outcome_rejects_incomplete_ambiguous_or_mismatched_evidence(
    evidence_update,
):
    ledger = FakeLifetimeLedger()
    receipt = _claimed_unknown_attempt(ledger)

    result = _authorize_attempt_one(
        ledger,
        receipt,
        factual_reconciler=factual_not_created_reconciler(**evidence_update),
    )

    assert result["ok"] is False
    assert result["send_allowed"] is False
    assert result["status"] in {
        "FACTUAL_NOT_CREATED_RECONCILIATION_INVALID",
        "FACTUAL_RECONCILIATION_CLIENT_ORDER_ID_INVALID",
    }


def test_retry_sequence_must_be_exactly_prior_plus_one():
    ledger = FakeLifetimeLedger()
    receipt = _claimed_unknown_attempt(ledger)

    result = _authorize_attempt_one(
        ledger,
        receipt,
        next_attempt_id="ATTEMPT-2",
        next_attempt_sequence=2,
        factual_reconciler=factual_not_created_reconciler(),
    )

    assert result["status"] == "NEXT_ATTEMPT_SEQUENCE_NOT_CONTIGUOUS"
    assert result["send_allowed"] is False


@pytest.mark.parametrize("mutation", ["missing", "different_attempt"])
def test_retry_authorization_revalidates_the_prior_sequence_slot(mutation):
    ledger = FakeLifetimeLedger()
    receipt = reserve(ledger, identity())
    assert consume_pre_send(ledger, receipt)["ok"] is True
    prior_sequence_key = authority.account_client_order_sequence_key(
        receipt["canonical_operation_id"], receipt["attempt_sequence"]
    )
    if mutation == "missing":
        del ledger.data[prior_sequence_key]
    else:
        record = json.loads(ledger.data[prior_sequence_key])
        record["attempt_id"] = "OTHER-ATTEMPT"
        ledger.data[prior_sequence_key] = json.dumps(record)

    result = _authorize_attempt_one(ledger, receipt)

    assert result["status"] == "PRIOR_ATTEMPT_SEQUENCE_SLOT_MISMATCH"
    assert result["send_allowed"] is False


def test_legacy_attempt_keyed_authorization_cannot_authorize_a_retry():
    ledger = FakeLifetimeLedger()
    receipt = reserve(ledger, identity())
    assert consume_pre_send(ledger, receipt)["ok"] is True
    authorization = _authorize_attempt_one(ledger, receipt)
    assert authorization["status"] == "RECONCILED_NEW_ATTEMPT_AUTHORIZED"
    sequence_authorization_key = authority._authorization_sequence_key(
        receipt["canonical_operation_id"], 1
    )
    legacy_authorization_key = authority._identity_key(
        authority.ACCOUNT_CLIENT_ORDER_AUTHORIZATION_PREFIX,
        receipt["canonical_operation_id"],
        "ATTEMPT-1",
    )
    ledger.data[legacy_authorization_key] = ledger.data.pop(sequence_authorization_key)

    result = reserve(
        ledger,
        identity(
            canonical_operation_id=receipt["canonical_operation_id"],
            attempt_id="ATTEMPT-1",
            attempt_sequence=1,
        ),
    )

    assert result["status"] == "CLIENT_ORDER_ATTEMPT_NOT_AUTHORIZED_BY_RECONCILIATION"
    assert result["send_allowed"] is False


def test_legacy_pre_send_outcome_without_disposition_cannot_authorize_retry():
    ledger = FakeLifetimeLedger()
    receipt = reserve(ledger, identity())
    recorded = record_outcome(
        ledger,
        receipt,
        "PRE_SEND_FAILED_ATTEMPT_CONSUMED",
        reason="LOCAL_VALIDATION_FAILED",
        failure_phase="PRE_SEND_CONTEXT_VALIDATION",
    )
    assert recorded["ok"] is True
    disposition_key = authority.account_client_order_disposition_key(
        receipt["canonical_operation_id"], receipt["attempt_id"]
    )
    del ledger.data[disposition_key]

    result = _authorize_attempt_one(ledger, receipt)

    assert result["status"] == "PRIOR_ATTEMPT_DISPOSITION_CONFLICT"
    assert result["send_allowed"] is False


def test_retry_authorization_requires_authoritative_sequence_slot_readback():
    ledger = DroppedWriteLedger(drop_call=6)
    receipt = reserve(ledger, identity())
    assert consume_pre_send(ledger, receipt)["ok"] is True

    result = _authorize_attempt_one(ledger, receipt)

    assert result["status"] == "ATTEMPT_AUTHORIZATION_PERSISTENCE_ERROR"
    assert result["send_allowed"] is False
    assert result["persistent"] is False


def test_retry_verification_requires_its_exact_sequence_authorization_record():
    ledger = FakeLifetimeLedger()
    first = reserve(ledger, identity())
    assert consume_pre_send(ledger, first)["ok"] is True
    assert _authorize_attempt_one(ledger, first)["ok"] is True
    second = reserve(
        ledger,
        identity(
            canonical_operation_id=first["canonical_operation_id"],
            attempt_id="ATTEMPT-1",
            attempt_sequence=1,
        ),
    )
    assert second["status"] == "RESERVED_UNIQUE"
    authorization_key = authority._authorization_sequence_key(
        first["canonical_operation_id"], 1
    )
    del ledger.data[authorization_key]

    result = authority.verify_account_client_order_id_reservation(
        second,
        expected_client_order_id=second["client_order_id"],
        redis_client=ledger,
        get_authoritative=ledger.get_authoritative,
    )

    assert result["status"] == "PARTIAL_RESERVATION_REQUIRES_RECONCILIATION"
    assert result["reservation_readback"]["present"]["authorization"] is False
    assert result["reservation_readback"]["integral"] is False
    assert result["send_allowed"] is False


def test_pre_send_failure_uses_authority_proof_and_authorization_is_idempotent():
    ledger = FakeLifetimeLedger()
    receipt = reserve(ledger, identity())
    record_outcome(
        ledger,
        receipt,
        "PRE_SEND_FAILED_ATTEMPT_CONSUMED",
        now=lambda: "2026-07-20T00:01:00Z",
    )

    first = _authorize_attempt_one(ledger, receipt)
    second = _authorize_attempt_one(ledger, receipt)

    assert first["status"] == "RECONCILED_NEW_ATTEMPT_AUTHORIZED"
    assert first["proof_mode"] == "AUTHORITATIVE_PRE_SEND_NO_SEND_CLAIM"
    assert first["send_allowed"] is False
    assert second["ok"] is True
    assert second["status"] == "ATTEMPT_AUTHORIZATION_ALREADY_EXISTS"
    assert second["idempotent"] is True
    assert second["evidence_hash"] == first["evidence_hash"]


def test_retry_authorization_sequence_slot_rejects_two_next_attempt_ids():
    ledger = FakeLifetimeLedger()
    receipt = reserve(ledger, identity())
    recorded = record_outcome(
        ledger,
        receipt,
        "PRE_SEND_FAILED_ATTEMPT_CONSUMED",
        now=lambda: "2026-07-20T00:01:00Z",
    )
    assert recorded["ok"] is True

    first = _authorize_attempt_one(ledger, receipt)
    conflicting = _authorize_attempt_one(
        ledger,
        receipt,
        next_attempt_id="ATTEMPT-OTHER",
        next_attempt_sequence=1,
    )
    first_reservation = reserve(
        ledger,
        identity(
            canonical_operation_id=receipt["canonical_operation_id"],
            attempt_id="ATTEMPT-1",
            attempt_sequence=1,
        ),
    )
    conflicting_reservation = reserve(
        ledger,
        identity(
            canonical_operation_id=receipt["canonical_operation_id"],
            attempt_id="ATTEMPT-OTHER",
            attempt_sequence=1,
        ),
    )

    assert first["status"] == "RECONCILED_NEW_ATTEMPT_AUTHORIZED"
    assert conflicting["status"] == "NEXT_ATTEMPT_SEQUENCE_ALREADY_AUTHORIZED"
    assert conflicting["send_allowed"] is False
    assert first_reservation["status"] == "RESERVED_UNIQUE"
    assert first_reservation["send_allowed"] is True
    assert conflicting_reservation["status"] == "CLIENT_ORDER_ATTEMPT_NOT_AUTHORIZED_BY_RECONCILIATION"
    assert conflicting_reservation["send_allowed"] is False


def test_concurrent_a1_b1_sequence_race_allows_one_authorization_reservation_claim_and_raw_create():
    ledger = ThreadSafeAuthorizationRaceLedger()
    initial = reserve(ledger, identity())
    consumed = record_outcome(
        ledger,
        initial,
        "PRE_SEND_FAILED_ATTEMPT_CONSUMED",
        reason="PRE_SEND_SETUP_FAILED",
        failure_phase="PRE_SEND_SETUP",
        now=lambda: "2026-07-20T00:01:00Z",
    )
    assert consumed["ok"] is True
    ledger.authorization_barrier = threading.Barrier(2)

    class RawExchangeProbe:
        def __init__(self):
            self.calls = []
            self.lock = threading.Lock()

        def create_order(self, client_order_id):
            with self.lock:
                self.calls.append(client_order_id)

    exchange = RawExchangeProbe()

    def compete(next_attempt_id):
        authorization = _authorize_attempt_one(
            ledger,
            initial,
            next_attempt_id=next_attempt_id,
        )
        reservation = None
        send_claim = None
        if authorization.get("ok") is True:
            reservation = reserve(
                ledger,
                identity(
                    canonical_operation_id=initial["canonical_operation_id"],
                    attempt_id=next_attempt_id,
                    attempt_sequence=1,
                ),
            )
            if reservation.get("send_allowed") is True:
                send_claim = claim(ledger, reservation)
                if send_claim.get("send_allowed") is True:
                    exchange.create_order(reservation["client_order_id"])
        return authorization, reservation, send_claim

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(compete, ("ATTEMPT-A1", "ATTEMPT-B1")))

    authorizations = [item[0] for item in results]
    reservations = [item[1] for item in results if item[1] is not None]
    claims = [item[2] for item in results if item[2] is not None]
    assert sum(item.get("ok") is True for item in authorizations) == 1
    assert sum(
        item.get("status") == "NEXT_ATTEMPT_SEQUENCE_ALREADY_AUTHORIZED"
        for item in authorizations
    ) == 1
    assert sum(item.get("send_allowed") is True for item in reservations) == 1
    assert sum(item.get("send_allowed") is True for item in claims) == 1
    assert len(exchange.calls) == 1


def test_new_replacement_revision_is_a_new_operation_and_new_client_order_id():
    first = identity(
        role=authority.ROLE_REPLACEMENT_STOP,
        stop_revision=1,
        attempt_id="REPLACE-1-ATTEMPT-0",
    )
    second = identity(
        role=authority.ROLE_REPLACEMENT_STOP,
        stop_revision=2,
        attempt_id="REPLACE-2-ATTEMPT-0",
    )

    assert authority.build_canonical_operation_id(
        **{key: value for key, value in first.items() if key not in {"attempt_id", "attempt_sequence"}}
    ) != authority.build_canonical_operation_id(
        **{key: value for key, value in second.items() if key not in {"attempt_id", "attempt_sequence"}}
    )
    assert authority.generate_account_client_order_id(
        **first
    ) != authority.generate_account_client_order_id(**second)


def test_replacement_and_rollback_are_distinct_initial_operations():
    ledger = FakeLifetimeLedger()
    replacement_identity = identity(
        role=authority.ROLE_REPLACEMENT_STOP,
        stop_revision=1,
        attempt_id="REPLACEMENT-REVISION-1",
    )
    rollback_identity = identity(
        role=authority.ROLE_ROLLBACK_STOP,
        stop_revision=1,
        attempt_id="ROLLBACK-REVISION-1",
    )

    replacement = reserve(ledger, replacement_identity)
    rollback = reserve(ledger, rollback_identity)

    assert replacement["status"] == rollback["status"] == "RESERVED_UNIQUE"
    assert replacement["send_allowed"] is True
    assert rollback["send_allowed"] is True
    assert replacement["canonical_operation_id"] != rollback["canonical_operation_id"]
    assert replacement["client_order_id"].startswith("FRP1-")
    assert rollback["client_order_id"].startswith("FRB1-")
    assert replacement["client_order_id"] != rollback["client_order_id"]


def test_module_is_side_effect_free_and_does_not_import_operational_layers():
    source = (ROOT / "account_client_order_id.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    top_level_imports = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            top_level_imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module != "__future__":
            top_level_imports.add(node.module.split(".")[0])

    assert top_level_imports.isdisjoint(
        {
            "broker",
            "main",
            "bots",
            "requests",
            "socket",
            "redis",
            "upstash_redis",
            "redis_bandwidth",
            "threading",
        }
    )


def test_clean_import_does_not_create_network_redis_broker_or_threads(monkeypatch):
    tracked = {"broker", "redis_bandwidth", "upstash_redis", "requests"}
    before = {name for name in tracked if name in sys.modules}
    imported = importlib.reload(authority)
    after = {name for name in tracked if name in sys.modules}

    assert imported.ACCOUNT_CLIENT_ORDER_ID_GENERATOR_VERSION == "ACCOUNT_CLIENT_ORDER_ID_V1"
    assert after == before
