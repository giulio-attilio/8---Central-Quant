"""Concrete public-key authorization experiment, exclusively synthetic/offline.

Private keys never enter a verifier. Trusted signing, policy-reading and external
anchor ports are injected explicitly. The test anchor is NOT production storage:
rolling back that anchor as well defeats the model and must remain a negative
control. No service, credentials, runtime import, readiness or automatic retry.
The old HMAC protocol remains unchanged and is not an accepted V2 fallback.
"""

from dataclasses import dataclass, fields
import hashlib
import json
import math
import os
import re

from trade_registry_c3_maintenance_authorization_v1 import (
    AuthorizationBindingV1, OFFLINE_MAINTENANCE_SCOPE, SQLiteMaintenanceAuthorizationLedgerV1,
    _sha, _digest, maintenance_authorization_payload_sha256,
)
from trade_registry_c3_postgres_consumption_offline_v1 import (
    PostgresConsumptionOfflineV1, CommittedDigestOfflineV1,
)

SCOPE = "C3_PUBLIC_AUTHORITY_SYNTHETIC_ONLY_V2"
PURPOSES = {"request", "policy", "anchor_head", "anchor_reserve", "consumption"}
EPOCH_REQUEST_SCOPE = "C3_PUBLIC_EPOCH_REQUEST_SYNTHETIC_ONLY_V3"
EPOCH_STATEMENT_SCOPE = "C3_PUBLIC_EPOCH_STATEMENT_SYNTHETIC_ONLY_V3"


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _now(clock, floor, deadline):
    value = clock()
    if not _number(value) or not _number(deadline) or not floor <= value < deadline:
        raise ValueError("C3_PUBLIC_AUTHORITY_DEADLINE")
    return value


def remaining_epoch_window_ms_offline_v2(*, enabled=False, scope=None,
        not_before_epoch_ms=None, expires_epoch_ms=None, now_lower_epoch_ms=None,
        now_upper_epoch_ms=None, local_remaining_ms=None, max_interval_width_ms=None):
    """Pure synthetic arithmetic, NOT authentication or a time-source verifier.

    All inputs are integer milliseconds. The current epoch interval must come
    from a separately trusted, fresh source. local_remaining_ms must be measured
    against the last admitted LOCAL monotonic deadline, not a renewed budget or
    another machine's clock. No current request/signature format is converted.
    Returning a duration grants no authority and has no runtime integration.
    """
    if enabled is not True or scope != SCOPE:
        return None
    values = (not_before_epoch_ms, expires_epoch_ms, now_lower_epoch_ms,
              now_upper_epoch_ms, local_remaining_ms, max_interval_width_ms)
    if any(type(value) is not int or not 0 <= value <= 2**53 - 1 for value in values):
        return None
    if (not 0 < expires_epoch_ms - not_before_epoch_ms <= 300_000
            or not not_before_epoch_ms <= now_lower_epoch_ms <= now_upper_epoch_ms < expires_epoch_ms
            or now_upper_epoch_ms - now_lower_epoch_ms > max_interval_width_ms
            or local_remaining_ms == 0):
        return None
    return min(5_000, local_remaining_ms, expires_epoch_ms - now_upper_epoch_ms)


@dataclass(frozen=True, repr=False)
class EpochRequestOfflineV3:
    """Signed common-time representation only, NOT an execution authorization.

    No local monotonic deadline is serialized. V2 consumers reject this type.
    Construction has no I/O; public functions remain explicitly default-off.
    """
    namespace: str
    storage_root_binding_sha256: str
    nonce: str
    not_before_epoch_ms: int
    expires_epoch_ms: int
    key_id: str
    key_epoch: int
    scope: str = OFFLINE_MAINTENANCE_SCOPE
    writer_count: int = 19
    maintenance_only: bool = True
    signature_hex: str | None = None

    def __repr__(self):
        return "<EpochRequestOfflineV3 protected>"


def epoch_request_signing_message_offline_v3(request, *, enabled=False, scope=None):
    """Canonical unsigned bytes or None; no signer, decoder or V2 conversion."""
    if enabled is not True or scope != EPOCH_REQUEST_SCOPE:
        return None
    try:
        if (type(request) is not EpochRequestOfflineV3
                or type(request.scope) is not str or request.scope != OFFLINE_MAINTENANCE_SCOPE
                or any(not _sha(v) for v in (request.namespace, request.storage_root_binding_sha256, request.key_id))
                or type(request.nonce) is not str or not 1 <= len(request.nonce) <= 256
                or type(request.writer_count) is not int or request.writer_count != 19
                or request.maintenance_only is not True
                or any(type(v) is not int or not 0 <= v <= 2**53 - 1 for v in (
                    request.not_before_epoch_ms, request.expires_epoch_ms, request.key_epoch))
                or request.key_epoch < 1
                or not 0 < request.expires_epoch_ms - request.not_before_epoch_ms <= 300_000):
            return None
        request.nonce.encode("utf-8", errors="strict")  # Reject unpaired surrogates.
        content = {f.name: getattr(request, f.name) for f in fields(request) if f.name != "signature_hex"}
        message = json.dumps({"version": EPOCH_REQUEST_SCOPE, "algorithm": "Ed25519",
            "purpose": "request", **content}, sort_keys=True, separators=(",", ":"),
            ensure_ascii=True, allow_nan=False).encode("ascii")
        return message if len(message) <= 4096 else None
    except Exception:
        return None


def epoch_request_claim_offline_v3(request, *, enabled=False, scope=None):
    """Compatibility replay key ONLY; neither signature verification nor a grant.

    Storage must still bind this digest to its pinned namespace and retain history.
    Changing a signature version, key or validity must not change this identity.
    """
    if epoch_request_signing_message_offline_v3(request, enabled=enabled, scope=scope) is None:
        return None
    return _digest({"scope": request.scope, "root": request.storage_root_binding_sha256,
                    "nonce": request.nonce})


def epoch_request_signature_verified_offline_v3(request, *, enabled=False, scope=None,
        public_key_bytes=None, expected_key_epoch=None, expected_namespace=None, expected_root=None):
    """Verify signature + explicit pins ONLY, not current validity or authority.

    No clock, revocation, consumption, policy, root authentication or network.
    True can recur for the same signed request; it must never be used as a permit.
    Trusted provisioning of the public key and pins is an external prerequisite.
    """
    if enabled is not True or scope != EPOCH_REQUEST_SCOPE:
        return False
    try:
        message = epoch_request_signing_message_offline_v3(request, enabled=True, scope=scope)
        if (message is None or type(public_key_bytes) is not bytes or len(public_key_bytes) != 32
                or type(expected_key_epoch) is not int or not 1 <= expected_key_epoch <= 2**53 - 1
                or not _sha(expected_namespace) or not _sha(expected_root)
                or request.namespace != expected_namespace or request.storage_root_binding_sha256 != expected_root
                or request.key_epoch != expected_key_epoch
                or request.key_id != hashlib.sha256(public_key_bytes).hexdigest()
                or type(request.signature_hex) is not str
                or re.fullmatch(r"[0-9a-f]{128}", request.signature_hex) is None):
            return False
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        Ed25519PublicKey.from_public_bytes(public_key_bytes).verify(bytes.fromhex(request.signature_hex), message)
        return True
    except Exception:
        return False


@dataclass(frozen=True, repr=False)
class EpochPolicyOfflineV3:
    namespace: str
    generation: int
    issued_at_epoch_ms: int
    expires_epoch_ms: int
    revoked_key_ids: tuple
    key_id: str
    key_epoch: int
    signature_hex: str | None = None

    def __repr__(self):
        return "<EpochPolicyOfflineV3 protected>"


@dataclass(frozen=True, repr=False)
class EpochAnchorOfflineV3:
    purpose: str
    namespace: str
    instance: str
    policy_generation: int
    policy_sha256: str
    payload_sha256: str
    challenge: str
    not_before_epoch_ms: int
    expires_epoch_ms: int
    key_id: str
    key_epoch: int
    claim_sha256: str | None = None
    signature_hex: str | None = None

    def __repr__(self):
        return "<EpochAnchorOfflineV3 protected>"


@dataclass(frozen=True, repr=False)
class EpochConsumptionOfflineV3:
    reservation: EpochAnchorOfflineV3
    committed_digest: str
    key_id: str
    key_epoch: int
    signature_hex: str | None = None

    def __repr__(self):
        return "<EpochConsumptionOfflineV3 protected>"


def _epoch_interval_v3(start, end, maximum):
    return (all(type(v) is int and 0 <= v <= 2**53 - 1 for v in (start, end))
            and 0 < end - start <= maximum)


def epoch_statement_signing_message_offline_v3(statement, *, enabled=False, scope=None):
    """Canonical representation only. Signed claims are not storage/freshness proof."""
    if enabled is not True or scope != EPOCH_STATEMENT_SCOPE:
        return None
    try:
        kind = type(statement)
        if (kind not in (EpochPolicyOfflineV3, EpochAnchorOfflineV3, EpochConsumptionOfflineV3)
                or not _sha(statement.key_id) or type(statement.key_epoch) is not int
                or not 1 <= statement.key_epoch <= 2**53 - 1):
            return None
        content = {f.name: getattr(statement, f.name) for f in fields(statement) if f.name != "signature_hex"}
        if kind is EpochPolicyOfflineV3:
            purpose = "policy"
            if (not _sha(statement.namespace) or type(statement.generation) is not int
                    or not 1 <= statement.generation <= 2**53 - 1
                    or not _epoch_interval_v3(statement.issued_at_epoch_ms, statement.expires_epoch_ms, 300_000)
                    or type(statement.revoked_key_ids) is not tuple or len(statement.revoked_key_ids) > 128
                    or any(not _sha(k) for k in statement.revoked_key_ids)
                    or tuple(sorted(set(statement.revoked_key_ids))) != statement.revoked_key_ids):
                return None
        elif kind is EpochAnchorOfflineV3:
            purpose = statement.purpose
            if (type(purpose) is not str or purpose not in ("anchor_head", "anchor_reserve")
                    or any(not _sha(v) for v in (statement.namespace, statement.instance,
                        statement.policy_sha256, statement.payload_sha256, statement.challenge))
                    or type(statement.policy_generation) is not int or not 1 <= statement.policy_generation <= 2**53 - 1
                    or not _epoch_interval_v3(statement.not_before_epoch_ms, statement.expires_epoch_ms, 5_000)
                    or (purpose == "anchor_head" and statement.claim_sha256 is not None)
                    or (purpose == "anchor_reserve" and not _sha(statement.claim_sha256))):
                return None
        else:
            purpose = "consumption"
            if type(statement.reservation) is not EpochAnchorOfflineV3 or statement.reservation.purpose != "anchor_reserve":
                return None
            reservation_message = epoch_statement_signing_message_offline_v3(
                statement.reservation, enabled=True, scope=scope)
            if reservation_message is None or not _sha(statement.committed_digest):
                return None
            reservation_digest = hashlib.sha256(reservation_message).hexdigest()
            if statement.committed_digest != reservation_digest:
                return None
            del content["reservation"]
            content["reservation_sha256"] = reservation_digest
        message = json.dumps({"version": EPOCH_STATEMENT_SCOPE, "algorithm": "Ed25519",
            "purpose": purpose, **content}, sort_keys=True, separators=(",", ":"),
            ensure_ascii=True, allow_nan=False).encode("ascii")
        return message if len(message) <= 16_384 else None
    except Exception:
        return None


def epoch_statement_signature_verified_offline_v3(statement, *, enabled=False, scope=None,
        public_key_bytes=None, expected_key_epoch=None, expected_namespace=None,
        expected_instance=None, expected_purpose=None):
    """Signature + pins only; repeated True is never a permit or a commit check."""
    if enabled is not True or scope != EPOCH_STATEMENT_SCOPE:
        return False
    try:
        message = epoch_statement_signing_message_offline_v3(statement, enabled=True, scope=scope)
        if message is None:
            return False
        purpose = ("policy" if type(statement) is EpochPolicyOfflineV3 else
                   "consumption" if type(statement) is EpochConsumptionOfflineV3 else statement.purpose)
        context = statement.reservation if type(statement) is EpochConsumptionOfflineV3 else statement
        instance = None if type(statement) is EpochPolicyOfflineV3 else context.instance
        if (purpose != expected_purpose or not _sha(expected_namespace) or context.namespace != expected_namespace
                or instance != expected_instance or (purpose != "policy" and not _sha(expected_instance))
                or type(public_key_bytes) is not bytes or len(public_key_bytes) != 32
                or type(expected_key_epoch) is not int or not 1 <= expected_key_epoch <= 2**53 - 1
                or statement.key_epoch != expected_key_epoch
                or statement.key_id != hashlib.sha256(public_key_bytes).hexdigest()
                or type(statement.signature_hex) is not str
                or re.fullmatch(r"[0-9a-f]{128}", statement.signature_hex) is None):
            return False
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        Ed25519PublicKey.from_public_bytes(public_key_bytes).verify(bytes.fromhex(statement.signature_hex), message)
        return True
    except Exception:
        return False


def epoch_evidence_signatures_consistent_offline_v3(*, enabled=False, scope=None,
        request=None, policy=None, head=None, reservation=None, consumption=None,
        public_keys=None, key_epochs=None, expected_namespace=None, expected_root=None,
        expected_instance=None, expected_head_challenge=None, expected_reservation_challenge=None):
    """Static signed evidence consistency ONLY, NOT current operational authority.

    No clock, authenticated live head, storage, consumption or network is read.
    Even a complete valid historical chain can return True repeatedly. Actual
    freshness, one-shot use and post-commit revocation remain separate requirements.
    """
    if enabled is not True or scope != EPOCH_STATEMENT_SCOPE:
        return False
    try:
        roles = {"request", "policy", "anchor", "consumption"}
        if (type(public_keys) is not dict or type(key_epochs) is not dict
                or set(public_keys) != roles or set(key_epochs) != roles
                or any(type(k) is not bytes or len(k) != 32 for k in public_keys.values())
                or len(set(public_keys.values())) != 4
                or any(not _sha(v) for v in (expected_namespace, expected_root, expected_instance,
                                             expected_head_challenge, expected_reservation_challenge))
                or type(request) is not EpochRequestOfflineV3 or type(policy) is not EpochPolicyOfflineV3
                or type(head) is not EpochAnchorOfflineV3 or type(reservation) is not EpochAnchorOfflineV3
                or type(consumption) is not EpochConsumptionOfflineV3):
            return False
        if not epoch_request_signature_verified_offline_v3(request, enabled=True, scope=EPOCH_REQUEST_SCOPE,
                public_key_bytes=public_keys["request"], expected_key_epoch=key_epochs["request"],
                expected_namespace=expected_namespace, expected_root=expected_root):
            return False
        for statement, purpose, role in ((policy, "policy", "policy"), (head, "anchor_head", "anchor"),
                (reservation, "anchor_reserve", "anchor"), (consumption, "consumption", "consumption")):
            if not epoch_statement_signature_verified_offline_v3(statement, enabled=True, scope=scope,
                    public_key_bytes=public_keys[role], expected_key_epoch=key_epochs[role],
                    expected_namespace=expected_namespace,
                    expected_instance=None if purpose == "policy" else expected_instance, expected_purpose=purpose):
                return False
        payload = hashlib.sha256(epoch_request_signing_message_offline_v3(
            request, enabled=True, scope=EPOCH_REQUEST_SCOPE)).hexdigest()
        policy_digest = hashlib.sha256(epoch_statement_signing_message_offline_v3(
            policy, enabled=True, scope=scope)).hexdigest()
        if (set(policy.revoked_key_ids).intersection(hashlib.sha256(k).hexdigest() for k in public_keys.values())
                or head.challenge != expected_head_challenge or reservation.challenge != expected_reservation_challenge
                or consumption.reservation != reservation
                or reservation.claim_sha256 != epoch_request_claim_offline_v3(request, enabled=True, scope=EPOCH_REQUEST_SCOPE)
                or any(s.payload_sha256 != payload or s.policy_generation != policy.generation
                       or s.policy_sha256 != policy_digest for s in (head, reservation))):
            return False
        return (max(request.not_before_epoch_ms, policy.issued_at_epoch_ms) <= head.not_before_epoch_ms
                <= reservation.not_before_epoch_ms < reservation.expires_epoch_ms <= head.expires_epoch_ms
                <= min(request.expires_epoch_ms, policy.expires_epoch_ms))
    except Exception:
        return False


def epoch_wire_encode_offline_v3(value, *, enabled=False, scope=None):
    """Canonical signed representation ONLY; does not verify the signature."""
    if enabled is not True or scope not in (EPOCH_REQUEST_SCOPE, EPOCH_STATEMENT_SCOPE):
        return None
    try:
        message = (epoch_request_signing_message_offline_v3(value, enabled=True, scope=scope)
                   if scope == EPOCH_REQUEST_SCOPE else
                   epoch_statement_signing_message_offline_v3(value, enabled=True, scope=scope))
        if (message is None or type(value.signature_hex) is not str
                or re.fullmatch(r"[0-9a-f]{128}", value.signature_hex) is None):
            return None
        # message is already a bounded, validated canonical representation.
        document = json.loads(message)
        document["signature_hex"] = value.signature_hex
        wire = json.dumps(document, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False).encode("ascii")
        # Adding ,"signature_hex":"<128 lowercase hex>" costs exactly 147 bytes.
        limit = 4243 if scope == EPOCH_REQUEST_SCOPE else 16531
        return wire if len(wire) <= limit else None
    except Exception:
        return None


def epoch_wire_decode_offline_v3(wire, *, enabled=False, scope=None, reservation=None):
    """Strict bounded codec, NOT signature verification or authorization.

    Only exact canonical bytes are accepted. No V2 conversion or inferred scope.
    Consumption requires an explicitly supplied reservation; its signature must
    still be verified separately. No I/O, transport or operational integration.
    """
    if enabled is not True or scope not in (EPOCH_REQUEST_SCOPE, EPOCH_STATEMENT_SCOPE):
        return None
    limit = 4243 if scope == EPOCH_REQUEST_SCOPE else 16531
    if type(wire) is not bytes or not 0 < len(wire) <= limit:
        return None
    try:
        def unique_object(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("C3_EPOCH_WIRE_DUPLICATE")
                result[key] = value
            return result
        def integer(token):
            if len(token) > 16 or not token.isascii() or not token.isdigit():
                raise ValueError("C3_EPOCH_WIRE_INTEGER")
            value = int(token)
            if value > 2**53 - 1:
                raise ValueError("C3_EPOCH_WIRE_INTEGER")
            return value
        def forbidden_number(token):
            raise ValueError("C3_EPOCH_WIRE_NONINTEGER")
        document = json.loads(wire.decode("utf-8", errors="strict"),
            object_pairs_hook=unique_object, parse_int=integer,
            parse_float=forbidden_number, parse_constant=forbidden_number)
        if type(document) is not dict or document.get("version") != scope or document.get("algorithm") != "Ed25519":
            return None
        types = {(EPOCH_REQUEST_SCOPE, "request"): EpochRequestOfflineV3,
                 (EPOCH_STATEMENT_SCOPE, "policy"): EpochPolicyOfflineV3,
                 (EPOCH_STATEMENT_SCOPE, "anchor_head"): EpochAnchorOfflineV3,
                 (EPOCH_STATEMENT_SCOPE, "anchor_reserve"): EpochAnchorOfflineV3,
                 (EPOCH_STATEMENT_SCOPE, "consumption"): EpochConsumptionOfflineV3}
        purpose = document.get("purpose")
        if type(purpose) is not str:
            return None
        kind = types.get((scope, purpose))
        if kind is None:
            return None
        required = {f.name for f in fields(kind)} | {"version", "algorithm", "purpose"}
        if kind is EpochConsumptionOfflineV3:
            required = (required - {"reservation"}) | {"reservation_sha256"}
        if set(document) != required:
            return None
        integer_fields = {"key_epoch", "generation", "policy_generation", "not_before_epoch_ms",
                          "issued_at_epoch_ms", "expires_epoch_ms", "writer_count"}
        for name, value in document.items():
            if name in integer_fields:
                if type(value) is not int:
                    return None
            elif name == "maintenance_only":
                if type(value) is not bool:
                    return None
            elif name == "revoked_key_ids":
                if type(value) is not list or len(value) > 128 or any(type(v) is not str for v in value):
                    return None
            elif name == "claim_sha256" and purpose == "anchor_head":
                if value is not None:
                    return None
            elif type(value) is not str:
                return None
        if re.fullmatch(r"[0-9a-f]{128}", document["signature_hex"]) is None:
            return None
        # Reject whitespace/order/escape aliases rather than normalizing signed input.
        if json.dumps(document, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii") != wire:
            return None
        content = {k: v for k, v in document.items() if k not in {"version", "algorithm", "purpose"}}
        if kind is EpochAnchorOfflineV3:
            content["purpose"] = purpose
        if kind is EpochPolicyOfflineV3:
            content["revoked_key_ids"] = tuple(content["revoked_key_ids"])
        if kind is EpochConsumptionOfflineV3:
            if (type(reservation) is not EpochAnchorOfflineV3 or reservation.purpose != "anchor_reserve"
                    or epoch_wire_encode_offline_v3(reservation, enabled=True, scope=scope) is None):
                return None
            reservation_message = epoch_statement_signing_message_offline_v3(reservation, enabled=True, scope=scope)
            if content.pop("reservation_sha256") != hashlib.sha256(reservation_message).hexdigest():
                return None
            content["reservation"] = reservation
        elif reservation is not None:
            return None  # Unexpected context is not silently discarded.
        value = kind(**content)
        return value if epoch_wire_encode_offline_v3(value, enabled=True, scope=scope) == wire else None
    except Exception:
        return None


@dataclass(frozen=True, repr=False)
class SignatureV2:
    purpose: str
    key_id: str
    key_epoch: int
    payload_sha256: str
    signature_hex: str

    def __repr__(self):
        return "<SignatureV2 protected>"


def signing_message_v2(purpose, key_id, key_epoch, payload_sha256):
    """Version, purpose, pinned key identity and epoch are all signed."""
    if (purpose not in PURPOSES or not _sha(key_id) or not _sha(payload_sha256)
            or type(key_epoch) is not int or key_epoch < 1):
        raise ValueError("C3_PUBLIC_AUTHORITY_SIGNATURE_CONTEXT")
    return json.dumps({"version": SCOPE, "algorithm": "Ed25519", "purpose": purpose,
        "key_id": key_id, "key_epoch": key_epoch, "payload_sha256": payload_sha256},
        sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii")


class Ed25519VerifierOfflineV2:
    def __init__(self, *, enabled=False, scope=None, public_key_bytes=None, key_epoch=0):
        self.enabled, self.scope = enabled is True, scope
        self._public = public_key_bytes
        self.key_epoch = key_epoch

    def __repr__(self):
        return "<Ed25519VerifierOfflineV2 public-only protected>"

    @property
    def key_id(self):
        return hashlib.sha256(self._public).hexdigest() if type(self._public) is bytes else None

    def ready(self):
        return (self.enabled and self.scope == SCOPE and type(self._public) is bytes
                and len(self._public) == 32 and type(self.key_epoch) is int and self.key_epoch >= 1)

    def verify(self, signature, *, purpose, payload_sha256):
        if not self.ready():
            return False
        try:
            if (type(signature) is not SignatureV2 or signature.purpose != purpose
                    or signature.key_id != self.key_id or signature.key_epoch != self.key_epoch
                    or type(signature.key_epoch) is not int or signature.payload_sha256 != payload_sha256
                    or type(signature.signature_hex) is not str
                    or re.fullmatch(r"[0-9a-f]{128}", signature.signature_hex) is None):
                return False
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
            Ed25519PublicKey.from_public_bytes(self._public).verify(
                bytes.fromhex(signature.signature_hex),
                signing_message_v2(purpose, self.key_id, self.key_epoch, payload_sha256))
            return True
        except Exception:
            return False


@dataclass(frozen=True, repr=False)
class RevocationsV2:
    namespace: str
    generation: int
    issued_at: float
    expires_at: float
    revoked_key_ids: tuple
    signature: SignatureV2 | None = None

    def __repr__(self):
        return "<RevocationsV2 protected>"


@dataclass(frozen=True, repr=False)
class AnchorReceiptV2:
    namespace: str
    instance: str
    policy_generation: int
    policy_sha256: str
    challenge: str
    deadline: float
    claim_sha256: str | None = None
    payload_sha256: str | None = None
    signature: SignatureV2 | None = None

    def __repr__(self):
        return "<AnchorReceiptV2 protected>"


def statement_digest_v2(statement):
    if type(statement) not in (RevocationsV2, AnchorReceiptV2):
        raise ValueError("C3_PUBLIC_AUTHORITY_STATEMENT_TYPE")
    return _digest({"domain": type(statement).__name__, **{
        f.name: getattr(statement, f.name) for f in fields(statement) if f.name != "signature"}})


class AnchoredRevocationsOfflineV2:
    """Read signed policy and require equality with a fresh external head.

    A signed old policy alone is insufficient. No cached head or local-only
    generation floor may authorize after reconstruction. Missing external
    evidence fails closed. The external anchor itself is a trusted dependency.
    """
    def __init__(self, *, enabled=False, scope=None, namespace=None, instance=None,
                 policy_verifier=None, anchor_verifier=None, protected_key_ids=(),
                 policy_reader=None, anchor=None, clock=None):
        self.enabled, self.scope = enabled is True, scope
        self.namespace, self.instance = namespace, instance
        self.policy_verifier, self.anchor_verifier = policy_verifier, anchor_verifier
        self.protected_key_ids = protected_key_ids
        self.policy_reader, self.anchor, self.clock = policy_reader, anchor, clock

    def __repr__(self):
        return "<AnchoredRevocationsOfflineV2 synthetic-only protected>"

    def ready(self):
        return (self.enabled and self.scope == SCOPE and _sha(self.namespace) and _sha(self.instance)
            and all(type(v) is Ed25519VerifierOfflineV2 and v.ready()
                    for v in (self.policy_verifier, self.anchor_verifier))
            and type(self.protected_key_ids) is tuple and len(self.protected_key_ids) == 4
            and len(set(self.protected_key_ids)) == 4 and all(_sha(k) for k in self.protected_key_ids)
            and self.policy_verifier.key_id in self.protected_key_ids
            and self.anchor_verifier.key_id in self.protected_key_ids
            and callable(self.policy_reader) and callable(self.clock)
            and callable(getattr(self.anchor, "read_head", None)))

    def valid_anchor(self, receipt, *, purpose, challenge, deadline, claim=None, payload=None):
        return (type(receipt) is AnchorReceiptV2 and receipt.namespace == self.namespace
            and receipt.instance == self.instance and receipt.challenge == challenge and _sha(challenge)
            and _number(receipt.deadline) and receipt.deadline == deadline
            and type(receipt.policy_generation) is int and receipt.policy_generation >= 1
            and _sha(receipt.policy_sha256) and receipt.claim_sha256 == claim
            and receipt.payload_sha256 == payload
            and self.anchor_verifier.verify(receipt.signature, purpose=purpose,
                payload_sha256=statement_digest_v2(receipt)))

    def current(self, deadline):
        if not self.enabled:
            return None
        try:
            if not self.ready():
                return None
            now = _now(self.clock, 0, deadline)
            policy = self.policy_reader()
            if (type(policy) is not RevocationsV2 or policy.namespace != self.namespace
                    or type(policy.generation) is not int or policy.generation < 1
                    or not _number(policy.issued_at) or not _number(policy.expires_at)
                    or not 0 <= policy.issued_at <= now < policy.expires_at
                    or type(policy.revoked_key_ids) is not tuple or len(policy.revoked_key_ids) > 128
                    or any(not _sha(k) for k in policy.revoked_key_ids)
                    or tuple(sorted(set(policy.revoked_key_ids))) != policy.revoked_key_ids
                    or set(policy.revoked_key_ids).intersection(self.protected_key_ids)
                    or not self.policy_verifier.verify(policy.signature, purpose="policy",
                        payload_sha256=statement_digest_v2(policy))):
                return None
            challenge = os.urandom(32).hex()
            head = self.anchor.read_head(namespace=self.namespace, instance=self.instance,
                challenge=challenge, deadline=deadline)
            if not self.valid_anchor(head, purpose="anchor_head", challenge=challenge, deadline=deadline):
                return None
            after = _now(self.clock, now, deadline)
            if (after >= policy.expires_at or head.policy_generation != policy.generation
                    or head.policy_sha256 != statement_digest_v2(policy)):
                return None
            return head
        except Exception:
            return None


@dataclass(frozen=True, repr=False)
class PublicConsumptionReceiptV2:
    reservation: AnchorReceiptV2
    committed_digest: str
    signature: SignatureV2 | None = None

    def __repr__(self):
        return "<PublicConsumptionReceiptV2 protected>"


def consumption_digest_v2(receipt):
    return _digest({"domain": "C3_PUBLIC_CONSUMPTION_V2",
        "reservation": statement_digest_v2(receipt.reservation), "committed_digest": receipt.committed_digest})


class PublicPostgresConsumerOfflineV2:
    """External one-shot reservation -> PG commit -> public-key signed receipt.

    Reservation burns the claim even if PG/signing fails. No compensation.
    The anchor must retain (namespace, claim) across DB and key/instance recovery.
    Tests simulate that assumption; they do not provision an external service.
    A complete signed request is required even on direct calls. This validates
    maintenance authorization, NOT a remote caller's transport identity.
    """
    def __init__(self, *, enabled=False, scope=None, store=None, guard=None,
                 verifier=None, signer=None, clock=None, request_verifier=None,
                 root_binding=None):
        self.enabled, self.scope = enabled is True, scope
        self.store, self.guard, self.verifier = store, guard, verifier
        self.signer, self.clock = signer, clock
        self.request_verifier, self.root_binding = request_verifier, root_binding

    def __repr__(self):
        return "<PublicPostgresConsumerOfflineV2 synthetic-only protected>"

    def ready(self):
        return (self.enabled and self.scope == SCOPE and type(self.store) is PostgresConsumptionOfflineV1
            and type(self.guard) is AnchoredRevocationsOfflineV2 and self.guard.ready()
            and self.store._config.enabled is True
            and self.store._config.namespace_sha256 == self.guard.namespace
            and self.store._config.instance_sha256 == self.guard.instance
            and type(self.verifier) is Ed25519VerifierOfflineV2 and self.verifier.ready()
            and type(self.request_verifier) is Ed25519VerifierOfflineV2 and self.request_verifier.ready()
            and _sha(self.root_binding)
            and set(self.guard.protected_key_ids) == {self.verifier.key_id,
                self.request_verifier.key_id, self.guard.policy_verifier.key_id,
                self.guard.anchor_verifier.key_id}
            and callable(self.signer) and callable(self.clock)
            and callable(getattr(self.guard.anchor, "reserve_once", None)))

    def consume_once(self, *, namespace, claim_sha256, payload_sha256, challenge, deadline,
                     request=None, binding=None):
        if not self.enabled:
            return None
        try:
            if (not self.ready() or namespace != self.guard.namespace
                    or any(not _sha(v) for v in (claim_sha256, payload_sha256, challenge))):
                return None
            now = _now(self.clock, 0, deadline)
            expected_payload, expected_claim = _verified_request_context_v2(
                request, binding, verifier=self.request_verifier, namespace=namespace,
                root_binding=self.root_binding, now=now, deadline=deadline)
            if (payload_sha256, claim_sha256) != (expected_payload, expected_claim):
                return None
            now = _now(self.clock, now, deadline)
            head = self.guard.current(deadline)
            if head is None:
                return None
            reservation = self.guard.anchor.reserve_once(head=head, claim_sha256=claim_sha256,
                payload_sha256=payload_sha256, challenge=challenge, deadline=deadline)
            if (not self.guard.valid_anchor(reservation, purpose="anchor_reserve", challenge=challenge,
                    deadline=deadline, claim=claim_sha256, payload=payload_sha256)
                    or reservation.policy_generation != head.policy_generation
                    or reservation.policy_sha256 != head.policy_sha256):
                return None
            now = _now(self.clock, now, deadline)
            digest = statement_digest_v2(reservation)
            committed = self.store.commit_digest_once(namespace_sha256=namespace,
                claim_sha256=claim_sha256, digest=digest, deadline=deadline)
            if type(committed) is not CommittedDigestOfflineV1 or committed.digest != digest:
                return None
            now = _now(self.clock, now, deadline)
            latest = self.guard.current(deadline)
            if latest is None or (latest.policy_generation, latest.policy_sha256) != (
                    reservation.policy_generation, reservation.policy_sha256):
                return None
            receipt = PublicConsumptionReceiptV2(reservation, digest)
            signature = self.signer(purpose="consumption", payload_sha256=consumption_digest_v2(receipt))
            if not self.verifier.verify(signature, purpose="consumption", payload_sha256=consumption_digest_v2(receipt)):
                return None
            _now(self.clock, now, deadline)
            return PublicConsumptionReceiptV2(reservation, digest, signature)
        except Exception:
            return None


def request_digest_v2(namespace, binding, key_epoch):
    return _digest({"domain": "C3_PUBLIC_MAINTENANCE_REQUEST_V2", "namespace": namespace,
        "binding": maintenance_authorization_payload_sha256(binding, key_epoch)})


def _verified_request_context_v2(request, binding, *, verifier, namespace, root_binding,
                                 now, deadline):
    """One validation path for both sides of the synthetic consumption boundary."""
    if (not _sha(namespace) or not _sha(root_binding)
            or type(verifier) is not Ed25519VerifierOfflineV2 or not verifier.ready()
            or type(binding) is not AuthorizationBindingV1
            or binding.scope != OFFLINE_MAINTENANCE_SCOPE
            or binding.storage_root_binding_sha256 != root_binding
            or binding.maintenance_only is not True or type(binding.writer_count) is not int
            or binding.writer_count != 19 or type(binding.nonce) is not str
            or not 1 <= len(binding.nonce) <= 256
            or not all(_number(v) for v in (now, deadline, binding.deadline))
            or not 0 <= now < deadline <= min(binding.deadline, now + 5.0)):
        raise ValueError("C3_PUBLIC_AUTHORITY_REQUEST_CONTEXT")
    payload = request_digest_v2(namespace, binding, verifier.key_epoch)
    if not verifier.verify(request, purpose="request", payload_sha256=payload):
        raise ValueError("C3_PUBLIC_AUTHORITY_REQUEST_SIGNATURE")
    claim = _digest({"scope": binding.scope, "root": binding.storage_root_binding_sha256,
                     "nonce": binding.nonce})
    return payload, claim


class PublicMaintenanceAuthorizationOfflineV2:
    """Authorization callable for the existing OFFLINE maintenance harness only.

    Main's dormant startup binder still rejects this type; it is not modified.
    All I/O-like ports are cooperative and explicitly bounded by the deadline.
    """
    def __init__(self, *, enabled=False, scope=None, root_binding=None, ledger_binding=None,
                 ledger=None, request_verifier=None, consumer=None, guard=None, clock=None):
        self.enabled, self.scope = enabled is True, scope
        self.root_binding, self.ledger_binding = root_binding, ledger_binding
        self.ledger, self.request_verifier = ledger, request_verifier
        self.consumer, self.guard, self.clock = consumer, guard, clock

    def __repr__(self):
        return "<PublicMaintenanceAuthorizationOfflineV2 synthetic-only protected>"

    def __call__(self, request, binding):
        if not self.enabled:
            return False
        try:
            if (self.scope != SCOPE or not _sha(self.root_binding) or not _sha(self.ledger_binding)
                    or type(self.ledger) is not SQLiteMaintenanceAuthorizationLedgerV1
                    or self.ledger.storage_binding_sha256() != self.ledger_binding
                    or type(self.guard) is not AnchoredRevocationsOfflineV2 or not self.guard.ready()
                    or type(self.consumer) is not PublicPostgresConsumerOfflineV2 or not self.consumer.ready()
                    or self.consumer.guard is not self.guard
                    or self.consumer.request_verifier is not self.request_verifier
                    or self.consumer.root_binding != self.root_binding
                    or type(self.request_verifier) is not Ed25519VerifierOfflineV2 or not self.request_verifier.ready()
                    or set(self.guard.protected_key_ids) != {self.request_verifier.key_id,
                        self.consumer.verifier.key_id, self.guard.policy_verifier.key_id, self.guard.anchor_verifier.key_id}
                    or type(binding) is not AuthorizationBindingV1):
                return False
            now = _now(self.clock, 0, binding.deadline)
            deadline = min(binding.deadline, now + 5.0)
            payload, claim = _verified_request_context_v2(request, binding,
                verifier=self.request_verifier, namespace=self.guard.namespace,
                root_binding=self.root_binding, now=now, deadline=deadline)
            if self.guard.current(deadline) is None:
                return False
            challenge = os.urandom(32).hex()
            receipt = self.consumer.consume_once(namespace=self.guard.namespace, claim_sha256=claim,
                payload_sha256=payload, challenge=challenge, deadline=deadline,
                request=request, binding=binding)
            if (type(receipt) is not PublicConsumptionReceiptV2
                    or not self.guard.valid_anchor(receipt.reservation, purpose="anchor_reserve",
                        challenge=challenge, deadline=deadline, claim=claim, payload=payload)
                    or receipt.committed_digest != statement_digest_v2(receipt.reservation)
                    or not self.consumer.verifier.verify(receipt.signature, purpose="consumption",
                        payload_sha256=consumption_digest_v2(receipt))):
                return False
            now = _now(self.clock, now, deadline)
            if self.guard.current(deadline) is None:
                return False
            if self.ledger.consume_once(claim_sha256=claim, payload_sha256=payload) is not True:
                return False
            now = _now(self.clock, now, deadline)
            if self.guard.current(deadline) is None:
                return False
            _now(self.clock, now, deadline)
            return True
        except Exception:
            return False
