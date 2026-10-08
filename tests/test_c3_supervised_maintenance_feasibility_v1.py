"""Test-only state model: supervised maintenance is NOT production authority.

All state is in memory; signatures use publicly reproducible synthetic seeds.
No runtime, broker, filesystem backend, writer coordinator or repair is run.
The restore-all counterexample MUST remain visible, even when pytest passes.
"""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import asdict, dataclass, replace
import hashlib
import json
import os
import socket
import subprocess
import sys
import threading

# Reuse the existing sealed launcher, without changing its production/test lists.
if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "inside":
        raise SystemExit("explicit isolated laboratory invocation required")
    sys.path.insert(0, "/work/tests/helpers")
    from c3_linux_lab import verify_isolation
    verify_isolation(sys.argv[2])
    sys.path.insert(0, "/work")

import pytest


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(value):
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


@dataclass(frozen=True, repr=False)
class _Plan:
    operation: str = "SYNTHETIC_CLOSED_REPAIR"
    namespace: str = "synthetic-maintenance"
    target: str = "synthetic-registry"
    instance: str = "synthetic-instance"
    trade_identity: str = "synthetic-trade-1"
    revision: str = "synthetic-code-revision-1"
    source_sha: str = _digest({"value": "synthetic-before"})
    candidate_sha: str = _digest({"value": "synthetic-after"})
    preservation: str = "synthetic-stop-net-r-gross-r-preserved"

    def action_id(self):
        # Logical identity excludes nonce, code revision and key epoch.
        return _digest({key: getattr(self, key) for key in (
            "operation", "namespace", "target", "instance", "trade_identity", "source_sha"
        )})


def _review(plan):
    # The displayed artifact IS the canonical content, not a separate summary.
    return _canonical(asdict(plan))


@dataclass(frozen=True, repr=False)
class _Approval:
    plan: _Plan
    nonce: str
    generation: int
    issued_at: float
    deadline: float
    signature: object

    def payload(self):
        return _digest({"domain": "SYNTHETIC_SUPERVISED_REQUEST_V1",
                        "plan": asdict(self.plan), "nonce": self.nonce,
                        "generation": self.generation, "issued_at": self.issued_at,
                        "deadline": self.deadline})


@dataclass(frozen=True, repr=False)
class _Receipt:
    action_id: str
    approval_sha: str
    challenge: str
    signature: object = None

    def payload(self):
        return _digest({"domain": "SYNTHETIC_SUPERVISED_CONSUMPTION_V1",
                        "action": self.action_id, "approval": self.approval_sha,
                        "challenge": self.challenge})


class _Interrupted(Exception):
    pass


class _Authority:
    """Trusted in-memory fixture, not authenticated/durable operator storage."""
    def __init__(self):
        self.lock = threading.Lock()
        self.records = {}
        self.generation = 1
        self.revoked = set()
        self.available = True


class _Local:
    def __init__(self):
        self.lock = threading.Lock()
        self.document = {"value": "synthetic-before"}
        self.transactions = {}


class _Model:
    """Finite test model; no real ports, durability or readiness guarantees."""
    def __init__(self, authority, local, signers, verifiers, oracle, *, enabled=False):
        self.authority, self.local = authority, local
        self.signers, self.verifiers = signers, verifiers
        # Oracle is the TEST'S non-restored event log, NEVER consulted to admit.
        self.oracle = oracle
        self.enabled = enabled
        self.now = 100.0
        self.last_time = 100.0

    def approve(self, plan, nonce, reviewed):
        if type(plan) is not _Plan or reviewed != _review(plan):
            raise ValueError("synthetic review mismatch")
        approval = _Approval(plan, nonce, self.authority.generation, self.now,
                             self.now + 10.0, None)
        return replace(approval, signature=self.signers["request"](
            purpose="request", payload_sha256=approval.payload()))

    def _safe(self, approval, attempt_deadline):
        now = self.now
        if not self.last_time <= now < min(approval.deadline, attempt_deadline):
            return False
        self.last_time = now
        return (self.authority.available
                and approval.generation == self.authority.generation
                and not self.authority.revoked
                and approval.issued_at <= now)

    @staticmethod
    def _result(status):
        return {"status": status, "synthetic_only": True, "registry_write": False,
                "production_ready": False, "runtime_activation_allowed": False,
                "live_allowed": False}

    def run(self, plan, approval, challenge, *, fault=None, hook=None, receipt_filter=None):
        if self.enabled is not True:
            return self._result("DEFAULT_OFF")
        action_id = plan.action_id()
        attempt_deadline = self.now + 5.0

        def boundary(name):
            if hook:
                hook(name)
            if fault == name:
                raise _Interrupted(name)

        with self.local.lock:
            try:
                if (type(plan) is not _Plan or type(approval) is not _Approval
                        or approval.plan != plan or plan.operation != "SYNTHETIC_CLOSED_REPAIR"
                        or plan.namespace != "synthetic-maintenance"
                        or plan.target != "synthetic-registry" or plan.instance != "synthetic-instance"
                        or not isinstance(challenge, str) or not challenge
                        or not self.verifiers["request"].verify(approval.signature,
                            purpose="request", payload_sha256=approval.payload())
                        or not self._safe(approval, attempt_deadline)):
                    return self._result("DENIED")
                if _digest(self.local.document) != plan.source_sha:
                    return self._result("SOURCE_CHANGED")
                # This model has exactly one fixed synthetic effect, not a callback.
                if plan.candidate_sha != _digest({"value": "synthetic-after"}):
                    return self._result("CANDIDATE_CHANGED")
                boundary("before_reserve")
                with self.authority.lock:
                    if not self._safe(approval, attempt_deadline):
                        return self._result("DENIED")
                    if action_id in self.authority.records:
                        return self._result("ALREADY_CONSUMED")
                    self.authority.records[action_id] = {
                        "phase": "RESERVED", "plan_sha": _digest(asdict(plan))}
                    boundary("after_reserve")
                    receipt = _Receipt(action_id, approval.payload(), challenge)
                    receipt = replace(receipt, signature=self.signers["consumption"](
                        purpose="consumption", payload_sha256=receipt.payload()))
                if receipt_filter:
                    receipt = receipt_filter(receipt)
                if (type(receipt) is not _Receipt or receipt.action_id != action_id
                        or receipt.approval_sha != approval.payload() or receipt.challenge != challenge
                        or not self.verifiers["consumption"].verify(receipt.signature,
                            purpose="consumption", payload_sha256=receipt.payload())
                        or not self._safe(approval, attempt_deadline)):
                    return self._result("PENDING")
                self.local.transactions[action_id] = "PREPARED"
                boundary("after_prepare")
                # Serialize the final policy check with the simulated effect.
                with self.authority.lock:
                    if not self._safe(approval, attempt_deadline):
                        return self._result("PENDING")
                    self.local.document = {"value": "synthetic-after"}
                    self.oracle.append(action_id)
                    self.local.transactions[action_id] = "APPLIED"
                    boundary("after_effect")
                    self.local.transactions[action_id] = "COMPLETED"
                    boundary("before_ack")
                    if not self._safe(approval, attempt_deadline):
                        return self._result("PENDING")
                    self.authority.records[action_id]["phase"] = "COMPLETED"
                    boundary("after_ack")
                return self._result("SYNTHETIC_COMPLETED")
            except _Interrupted:
                # Represents a lost response, NOT successful recovery or retry.
                return self._result("AMBIGUOUS")


@pytest.fixture(autouse=True)
def _deny_external(monkeypatch):
    def denied(*_args, **_kwargs):
        raise AssertionError("network/subprocess forbidden in synthetic experiment")
    for name in ("socket", "create_connection", "getaddrinfo"):
        monkeypatch.setattr(socket, name, denied)
    monkeypatch.setattr(subprocess, "Popen", denied)
    monkeypatch.setattr(os, "system", denied)


@pytest.fixture
def model(_deny_external):
    # Existing public-key primitive; no public_env fixture because it creates SQLite.
    import trade_registry_c3_public_authority_offline_v2 as public
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    signers, verifiers = {}, {}
    for role, purpose in (("request", "request"), ("consumption", "consumption")):
        seed = hashlib.sha256(("PUBLIC-SYNTHETIC-SUPERVISED-" + role).encode()).digest()
        key = Ed25519PrivateKey.from_private_bytes(seed)
        verifier = public.Ed25519VerifierOfflineV2(enabled=True, scope=public.SCOPE,
            public_key_bytes=key.public_key().public_bytes_raw(), key_epoch=1)
        verifiers[role] = verifier

        def sign(*, purpose, payload_sha256, key=key, verifier=verifier):
            message = public.signing_message_v2(purpose, verifier.key_id,
                                                verifier.key_epoch, payload_sha256)
            return public.SignatureV2(purpose, verifier.key_id, verifier.key_epoch,
                                      payload_sha256, key.sign(message).hex())
        signers[role] = sign
    return _Model(_Authority(), _Local(), signers, verifiers, [], enabled=True)


def _attempt(model, *, plan=None, nonce="synthetic-nonce-1", challenge="synthetic-challenge-1", **kwargs):
    plan = plan or _Plan()
    approval = model.approve(plan, nonce, _review(plan))
    return model.run(plan, approval, challenge, **kwargs)


def _restart(model, *, restore_local=False, restore_authority=False):
    # Full pre-consumption snapshots in this model are empty histories/before value.
    return _Model(_Authority() if restore_authority else model.authority,
                  _Local() if restore_local else model.local,
                  model.signers, model.verifiers, model.oracle, enabled=True)


def test_default_off_does_not_call_any_port(model):
    model.enabled = False
    assert model.run(None, None, None)["status"] == "DEFAULT_OFF"
    assert model.oracle == [] and model.authority.records == {}


@pytest.mark.parametrize("field", tuple(_Plan.__dataclass_fields__))
def test_every_reviewed_plan_field_is_signature_bound(model, field):
    original = _Plan()
    approval = model.approve(original, "synthetic-nonce", _review(original))
    tampered = replace(original, **{field: "synthetic-tampered"})
    # Change both transmitted copies while retaining the old signature.
    result = model.run(tampered, replace(approval, plan=tampered), "fresh")
    assert result["status"] == "DENIED"
    assert model.oracle == [] and model.authority.records == {}


def test_display_cannot_be_detached_from_signed_plan(model):
    with pytest.raises(ValueError, match="review mismatch"):
        model.approve(_Plan(), "synthetic-nonce", "approve an unrelated action")
    assert model.authority.records == {}


def test_wrong_signing_identity_denied(model):
    plan = _Plan()
    approval = model.approve(plan, "nonce", _review(plan))
    foreign = model.signers["consumption"](purpose="request", payload_sha256=approval.payload())
    assert model.run(plan, replace(approval, signature=foreign), "challenge")["status"] == "DENIED"
    assert model.authority.records == {}


@pytest.mark.parametrize("field,value", [("nonce", "other"), ("generation", 2),
    ("issued_at", 99.0), ("deadline", 200.0)])
def test_approval_metadata_is_signed(model, field, value):
    plan = _Plan()
    approval = model.approve(plan, "nonce", _review(plan))
    assert model.run(plan, replace(approval, **{field: value}), "challenge")["status"] == "DENIED"
    assert model.authority.records == {}


@pytest.mark.parametrize("change", ["expiry", "clock_regression", "policy", "request_revoked",
                                   "consumption_revoked", "unavailable"])
def test_admission_rechecks_current_policy_and_time(model, change):
    plan = _Plan()
    approval = model.approve(plan, "nonce", _review(plan))
    if change == "expiry":
        model.now = approval.deadline
    elif change == "clock_regression":
        model.now = 99.0
    elif change == "policy":
        model.authority.generation += 1
    elif change.endswith("revoked"):
        model.authority.revoked.add(change)
    else:
        model.authority.available = False
    assert model.run(plan, approval, "challenge")["status"] == "DENIED"
    assert model.authority.records == {} and model.oracle == []


@pytest.mark.parametrize("change", ["expiry", "clock_regression", "policy", "revoked", "unavailable"])
def test_late_change_burns_claim_without_applying(model, change):
    def hook(phase):
        if phase != "after_prepare":
            return
        if change == "expiry":
            model.now = 105.0  # Internal attempt deadline, not approval expiry.
        elif change == "clock_regression":
            model.now = 99.0
        elif change == "policy":
            model.authority.generation += 1
        elif change == "revoked":
            model.authority.revoked.add("request")
        else:
            model.authority.available = False
    assert _attempt(model, hook=hook)["status"] == "PENDING"
    assert model.oracle == []
    assert model.authority.records[_Plan().action_id()]["phase"] == "RESERVED"
    assert model.local.transactions[_Plan().action_id()] == "PREPARED"


@pytest.mark.parametrize("phase,effects", [("before_reserve", 0), ("after_reserve", 0),
    ("after_prepare", 0), ("after_effect", 1), ("before_ack", 1), ("after_ack", 1)])
def test_lost_response_at_each_boundary_does_not_authorize_retry(model, phase, effects):
    assert _attempt(model, fault=phase)["status"] == "AMBIGUOUS"
    assert len(model.oracle) == effects
    fresh = _restart(model, restore_local=True)
    result = _attempt(fresh, nonce="synthetic-nonce-2", challenge="synthetic-challenge-2")
    if phase == "before_reserve":
        assert result["status"] == "SYNTHETIC_COMPLETED"  # No prior consume/effect.
        assert len(model.oracle) == 1
    else:
        assert result["status"] == "ALREADY_CONSUMED"
        assert len(model.oracle) == effects
        expected = "COMPLETED" if phase == "after_ack" else "RESERVED"
        assert model.authority.records[_Plan().action_id()]["phase"] == expected


def test_thread_race_one_logical_action_consumed(model):
    # Multiple simulated local processes, but actual concurrency is THREADS ONLY.
    contenders = [_restart(model, restore_local=True) for _ in range(8)]
    with ThreadPoolExecutor(8) as pool:
        results = list(pool.map(lambda pair: _attempt(pair[1], nonce=f"nonce-{pair[0]}",
            challenge=f"challenge-{pair[0]}")["status"], enumerate(contenders)))
    assert results.count("SYNTHETIC_COMPLETED") == 1
    assert results.count("ALREADY_CONSUMED") == 7
    assert len(model.oracle) == len(model.authority.records) == 1


@pytest.mark.parametrize("phase", [None, "after_reserve", "after_effect"])
def test_local_restore_and_new_nonce_cannot_reissue_same_action(model, phase):
    _attempt(model, fault=phase)
    effects = len(model.oracle)
    fresh = _restart(model, restore_local=True)
    assert _attempt(fresh, nonce="new-nonce", challenge="new-challenge")["status"] == "ALREADY_CONSUMED"
    assert len(model.oracle) == effects


def test_revision_or_key_rotation_does_not_reset_logical_consumption(model):
    _attempt(model, fault="after_reserve")
    fresh = _restart(model, restore_local=True)
    fresh.authority.generation += 1
    for verifier in fresh.verifiers.values():
        verifier.key_epoch += 1  # Synthetic epoch change, NOT operational rotation.
    updated = replace(_Plan(), revision="synthetic-code-revision-2")
    assert updated.action_id() == _Plan().action_id()
    assert _attempt(fresh, plan=updated, nonce="new", challenge="new")["status"] == "ALREADY_CONSUMED"
    assert model.oracle == []


@pytest.mark.parametrize("field", ["action_id", "approval_sha", "challenge"])
def test_receipt_binding_tamper_leaves_consumed_pending(model, field):
    result = _attempt(model, receipt_filter=lambda receipt: replace(receipt, **{field: "tampered"}))
    assert result["status"] == "PENDING"
    assert model.oracle == [] and len(model.authority.records) == 1


def test_old_receipt_rejected_with_fresh_challenge_even_if_all_stores_restored(model):
    captured = []
    def capture(receipt):
        captured.append(receipt)
        return receipt
    assert _attempt(model, receipt_filter=capture)["status"] == "SYNTHETIC_COMPLETED"
    fresh = _restart(model, restore_local=True, restore_authority=True)
    result = _attempt(fresh, challenge="fresh-challenge", receipt_filter=lambda _: captured[0])
    assert result["status"] == "PENDING"
    assert len(model.oracle) == 1


def test_counterexample_restore_all_plus_fresh_human_approval_allows_duplicate(model, record_property):
    # Deliberately fail the SECURITY hypothesis, not the test runner.
    before_local = deepcopy((model.local.document, model.local.transactions))
    before_authority = deepcopy(model.authority.records)
    assert _attempt(model)["status"] == "SYNTHETIC_COMPLETED"
    fresh = _restart(model, restore_local=True, restore_authority=True)
    assert (fresh.local.document, fresh.local.transactions) == before_local
    assert fresh.authority.records == before_authority
    second = _attempt(fresh, nonce="fresh-human-nonce", challenge="fresh-os-challenge")
    assert second["status"] == "SYNTHETIC_COMPLETED"
    assert model.oracle == [_Plan().action_id(), _Plan().action_id()]
    assert second["live_allowed"] is second["production_ready"] is False
    record_property("security_verdict", "COUNTEREXAMPLE_RESTORE_ALL_DUPLICATE")
    record_property("synthetic_effect_count", len(model.oracle))


def test_no_result_grants_production_or_runtime_authority(model):
    result = _attempt(model)
    assert result["status"] == "SYNTHETIC_COMPLETED"
    for field in ("production_ready", "runtime_activation_allowed", "live_allowed", "registry_write"):
        assert result[field] is False
    assert result["synthetic_only"] is True


def test_experiment_blocks_network_and_subprocess(_deny_external):
    with pytest.raises(AssertionError, match="forbidden"):
        socket.socket()
    with pytest.raises(AssertionError, match="forbidden"):
        subprocess.Popen(["forbidden-synthetic-process"])


if __name__ == "__main__":
    raise SystemExit(pytest.main(["-q", "-rs", "--tb=short", "--noconftest",
        "-p", "no:cacheprovider", "-o", "junit_family=legacy",
        "--junitxml=/scratch/supervised-results.xml", __file__]))
