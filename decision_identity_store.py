"""Local/test-only V2.7A.2 decision request and completed-decision identity.

The module is deliberately independent from broker, Registry, Redis, network,
and runtime configuration.  Persistence is available only through an explicit
path supplied to :class:`DecisionIdentityRecordStore`.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import secrets
import tempfile
import threading
import time
from typing import Any, Callable, Iterator, Mapping


DECISION_REQUEST_IDENTITY_VERSION = "DECISION-REQUEST-IDENTITY-V2.7A.2"
DECISION_IDENTITY_VERSION = "DECISION-IDENTITY-V2.7A.2"
DECISION_REQUEST_DIGEST_VERSION = "DECISION-REQUEST-DIGEST-V2.7A.2"
DECISION_IDENTITY_STORE_SCHEMA_VERSION = "DECISION-IDENTITY-STORE-V2.7A.2"
DECISION_IDENTITY_RECORD_SCHEMA_VERSION = "DECISION-IDENTITY-RECORD-V2.7A.2"
DECISION_IDENTITY_INTEGRITY_VERSION = "SHA256-CANONICAL-JSON-V1"
DECISION_REQUEST_ID_PREFIX = "DECISION-REQUEST-V2_7A_2:"
DECISION_ID_PREFIX = "DECISION-V2_7A_2:"
DECISION_REQUEST_ISSUER_FILE = "bots/falcon.py"
DECISION_REQUEST_ISSUER_FUNCTION = "central_can_open_trade"
DECISION_PROVIDER_FILE = "main.py"
DECISION_PROVIDER_FUNCTION = "can_open_trade_decision"
DECISION_PROVIDER_VERSION = "V2.7A.2"
RETENTION_CONTRACT = (
    "Bounded explicit-local records retain at most retention_max_records "
    "lineages; retired request identifiers remain non-reusable through a "
    "persistent deny-only bloom witness."
)

_DURABLE_STATES = frozenset({"CLAIMED", "COMPLETED"})
_TERMINAL_DECISIONS = frozenset({"ALLOW", "DENY"})
_BLOOM_BYTES = 4096
_BLOOM_HASH_COUNT = 4
_IDENTITY_TRANSPORT_FIELDS = frozenset(
    {
        "decision_request_id",
        "decision_request_identity_version",
        "decision_request_identity_provenance",
        "decision_request_identity_transport",
    }
)
_EXCLUDED_CANONICAL_REQUEST_FIELDS = frozenset(
    {
        "decision_request_id",
        "decision_request_identity_version",
        "decision_request_identity_provenance",
        "decision_id",
        "decision_identity_version",
        "decision_identity_provenance",
        "decision_identity_v2_7a_2",
        "execution_id",
        "lifecycle_id",
        "logical_trade_id",
        "trade_id",
        "trade_registry_id",
        "registry_id",
        "registry_record_id",
        "registry_execution_id",
        "registry_lifecycle_id",
        "registry_trade_id",
        "registry_position_id",
        "position_id",
        "position_identity",
        "physical_position_id",
        "broker_position_id",
        "client_order_id",
        "client_order_attempt_id",
        "client_order_attempt_sequence",
        "broker_order_id",
        "exchange_order_id",
        "fill_id",
        "live_order_id",
        "live_client_order_id",
        "execution_intent_idempotency_key",
    }
) | _IDENTITY_TRANSPORT_FIELDS


class DecisionIdentityError(Exception):
    """Base error for V2.7A.2 identity-only failures."""


class DecisionIdentityConstructionError(DecisionIdentityError):
    """Request identity or canonical request material is invalid."""


class DecisionIdentityStoreError(DecisionIdentityError):
    """Explicit local store could not perform an identity operation."""


class DecisionIdentityStoreCorruptionError(DecisionIdentityStoreError):
    """Store data exists but fails schema or integrity validation."""


class DecisionIdentityStoreWriteError(DecisionIdentityStoreError):
    """An atomic local identity-store write did not complete."""


def _nonempty(value: Any) -> bool:
    return value is not None and str(value).strip() != ""


def _required_text(value: Any, name: str) -> str:
    if not _nonempty(value):
        raise DecisionIdentityConstructionError(f"{name} is required")
    return str(value).strip()


def _number_text(value: Any, name: str) -> str:
    if isinstance(value, bool) or value is None:
        raise DecisionIdentityConstructionError(f"{name} must be a finite number")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise DecisionIdentityConstructionError(
            f"{name} must be a finite number"
        ) from exc
    if not number.is_finite():
        raise DecisionIdentityConstructionError(f"{name} must be a finite number")
    text = format(number.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in {"", "-0"} else text


def _canonical_value(value: Any, name: str = "value") -> Any:
    """Return an object-repr-free, locale-independent canonical value."""

    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return {"$number": str(value)}
    if isinstance(value, (float, Decimal)):
        return {"$number": _number_text(value, name)}
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key in sorted(value):
            if not isinstance(key, str):
                raise DecisionIdentityConstructionError(
                    f"{name} contains a non-string mapping key"
                )
            result[key] = _canonical_value(value[key], f"{name}.{key}")
        return result
    if isinstance(value, (list, tuple)):
        return [
            _canonical_value(item, f"{name}[{index}]")
            for index, item in enumerate(value)
        ]
    raise DecisionIdentityConstructionError(
        f"{name} has unsupported type {type(value).__name__}"
    )


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest().upper()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _validate_decision_request_id(value: Any) -> str:
    request_id = _required_text(value, "decision_request_id")
    if not request_id.startswith(DECISION_REQUEST_ID_PREFIX):
        raise DecisionIdentityConstructionError("decision_request_id has an invalid version")
    if not request_id[len(DECISION_REQUEST_ID_PREFIX) :]:
        raise DecisionIdentityConstructionError("decision_request_id is missing opaque material")
    return request_id


def _validate_decision_id(value: Any) -> str:
    decision_id = _required_text(value, "decision_id")
    if not decision_id.startswith(DECISION_ID_PREFIX):
        raise DecisionIdentityConstructionError("decision_id has an invalid version")
    if not decision_id[len(DECISION_ID_PREFIX) :]:
        raise DecisionIdentityConstructionError("decision_id is missing opaque material")
    return decision_id


def ensure_decision_request_identity(
    signal: Mapping[str, Any],
    *,
    issuer_file: str = DECISION_REQUEST_ISSUER_FILE,
    issuer_function: str = DECISION_REQUEST_ISSUER_FUNCTION,
) -> dict[str, Any]:
    """Create once or explicitly transport a request identity for one signal."""

    if not isinstance(signal, Mapping):
        raise DecisionIdentityConstructionError("signal must be a mapping")
    signal_id = _required_text(signal.get("signal_id"), "signal_id")
    existing_request_id = signal.get("decision_request_id")
    if _nonempty(existing_request_id):
        request_id = _validate_decision_request_id(existing_request_id)
        version = signal.get("decision_request_identity_version")
        provenance = signal.get("decision_request_identity_provenance")
        if version != DECISION_REQUEST_IDENTITY_VERSION or not isinstance(
            provenance, Mapping
        ):
            raise DecisionIdentityConstructionError(
                "explicit decision_request_id lacks its factual identity transport"
            )
        if _required_text(provenance.get("signal_id"), "provenance.signal_id") != signal_id:
            raise DecisionIdentityConstructionError(
                "explicit decision_request_id has a mismatched signal_id"
            )
        if (
            provenance.get("issuer_file") != issuer_file
            or provenance.get("issuer_function") != issuer_function
            or provenance.get("mechanism") != "SECRETS_TOKEN_URLSAFE"
            or provenance.get("identity_version") != DECISION_REQUEST_IDENTITY_VERSION
            or provenance.get("signal_correlation_method") != "EXACT_SIGNAL_ID"
        ):
            raise DecisionIdentityConstructionError(
                "explicit decision_request_id has invalid factual provenance"
            )
        return {
            "decision_request_id": request_id,
            "decision_request_identity_version": version,
            "decision_request_identity_provenance": dict(provenance),
            "decision_request_identity_transport": "EXPLICIT_SAME_EVALUATION",
        }

    request_id = DECISION_REQUEST_ID_PREFIX + secrets.token_urlsafe(32)
    provenance = {
        "issuer_file": _required_text(issuer_file, "issuer_file"),
        "issuer_function": _required_text(issuer_function, "issuer_function"),
        "mechanism": "SECRETS_TOKEN_URLSAFE",
        "identity_version": DECISION_REQUEST_IDENTITY_VERSION,
        "signal_id": signal_id,
        "signal_correlation_method": "EXACT_SIGNAL_ID",
        "issuance_kind": "NEW_EVALUATION",
    }
    return {
        "decision_request_id": request_id,
        "decision_request_identity_version": DECISION_REQUEST_IDENTITY_VERSION,
        "decision_request_identity_provenance": provenance,
        "decision_request_identity_transport": "NEW_EVALUATION",
    }


def canonical_decision_request(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Canonicalize all supplied provider inputs except prohibited identities."""

    if not isinstance(payload, Mapping):
        raise DecisionIdentityConstructionError("provider payload must be a mapping")
    signal_id = _required_text(payload.get("signal_id"), "signal_id")
    provider_inputs: dict[str, Any] = {}
    for key, value in payload.items():
        if not isinstance(key, str):
            raise DecisionIdentityConstructionError(
                "provider payload contains a non-string mapping key"
            )
        if key in _EXCLUDED_CANONICAL_REQUEST_FIELDS:
            continue
        provider_inputs[key] = value
    material = {
        "canonical_request_version": DECISION_REQUEST_DIGEST_VERSION,
        "signal_id": signal_id,
        "provider_inputs": _canonical_value(provider_inputs, "provider_inputs"),
    }
    canonical_json = _canonical_json(material)
    return {
        "canonical_request": material,
        "canonical_request_digest": _sha256_text(canonical_json),
        "canonical_request_digest_version": DECISION_REQUEST_DIGEST_VERSION,
    }


def decision_request_from_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate caller-issued request transport without repairing it."""

    if not isinstance(payload, Mapping):
        raise DecisionIdentityConstructionError("provider payload must be a mapping")
    signal_id = _required_text(payload.get("signal_id"), "signal_id")
    request_id = _validate_decision_request_id(payload.get("decision_request_id"))
    version = payload.get("decision_request_identity_version")
    provenance = payload.get("decision_request_identity_provenance")
    if version != DECISION_REQUEST_IDENTITY_VERSION or not isinstance(provenance, Mapping):
        raise DecisionIdentityConstructionError("decision request transport is incomplete")
    provenance_signal_id = _required_text(provenance.get("signal_id"), "provenance.signal_id")
    if provenance_signal_id != signal_id:
        raise DecisionIdentityConstructionError("decision request signal_id mismatch")
    if (
        provenance.get("issuer_file") != DECISION_REQUEST_ISSUER_FILE
        or provenance.get("issuer_function") != DECISION_REQUEST_ISSUER_FUNCTION
        or provenance.get("mechanism") != "SECRETS_TOKEN_URLSAFE"
        or provenance.get("identity_version") != DECISION_REQUEST_IDENTITY_VERSION
        or provenance.get("signal_correlation_method") != "EXACT_SIGNAL_ID"
    ):
        raise DecisionIdentityConstructionError("decision request provenance is invalid")
    return {
        "decision_request_id": request_id,
        "decision_request_identity_version": version,
        "decision_request_identity_provenance": dict(provenance),
        "signal_id": signal_id,
    }


def _validate_request_and_canonical(
    request: Mapping[str, Any], canonical_request: Mapping[str, Any]
) -> tuple[str, str, str, str, Mapping[str, Any]]:
    """Validate immutable request/digest material at the store boundary."""

    if not isinstance(request, Mapping) or not isinstance(canonical_request, Mapping):
        raise DecisionIdentityConstructionError(
            "decision identity request and canonical material must be mappings"
        )
    request_id = _validate_decision_request_id(request.get("decision_request_id"))
    signal_id = _required_text(request.get("signal_id"), "signal_id")
    if request.get("decision_request_identity_version") != DECISION_REQUEST_IDENTITY_VERSION:
        raise DecisionIdentityConstructionError("request identity version is invalid")
    provenance = request.get("decision_request_identity_provenance")
    if not isinstance(provenance, Mapping):
        raise DecisionIdentityConstructionError("request identity provenance is invalid")
    if _required_text(provenance.get("signal_id"), "provenance.signal_id") != signal_id:
        raise DecisionIdentityConstructionError("request provenance signal_id mismatch")

    digest = _required_text(
        canonical_request.get("canonical_request_digest"), "canonical_request_digest"
    )
    digest_version = _required_text(
        canonical_request.get("canonical_request_digest_version"),
        "canonical_request_digest_version",
    )
    material = canonical_request.get("canonical_request")
    if not isinstance(material, Mapping):
        raise DecisionIdentityConstructionError("canonical request material is invalid")
    if material.get("canonical_request_version") != digest_version:
        raise DecisionIdentityConstructionError("canonical request digest version mismatch")
    if _required_text(material.get("signal_id"), "canonical_request.signal_id") != signal_id:
        raise DecisionIdentityConstructionError("canonical request signal_id mismatch")
    if _sha256_text(_canonical_json(material)) != digest:
        raise DecisionIdentityConstructionError("canonical request digest mismatch")
    return request_id, signal_id, digest, digest_version, provenance


def _validate_provider_provenance(
    value: Mapping[str, Any], name: str
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise DecisionIdentityConstructionError(f"{name} is invalid")
    for field in ("provider_file", "provider_function", "provider_version"):
        _required_text(value.get(field), f"{name}.{field}")
    return dict(value)


def _generate_decision_id() -> str:
    """Generate an opaque candidate only after a factual terminal result exists."""

    return DECISION_ID_PREFIX + secrets.token_urlsafe(32)


def _record_integrity(record: Mapping[str, Any]) -> str:
    material = dict(record)
    material.pop("integrity_sha256", None)
    material.pop("integrity_version", None)
    return _sha256_text(_canonical_json(material))


def _state_integrity(state: Mapping[str, Any]) -> str:
    material = dict(state)
    material.pop("integrity_sha256", None)
    material.pop("integrity_version", None)
    return _sha256_text(_canonical_json(material))


def _new_bloom() -> str:
    return bytes(_BLOOM_BYTES).hex()


def _bloom_positions(request_id: str) -> tuple[int, ...]:
    digest = hashlib.sha256(request_id.encode("utf-8")).digest()
    modulus = _BLOOM_BYTES * 8
    return tuple(
        int.from_bytes(digest[index * 4 : index * 4 + 4], "big") % modulus
        for index in range(_BLOOM_HASH_COUNT)
    )


def _bloom_contains(bloom_hex: str, request_id: str) -> bool:
    try:
        bloom = bytes.fromhex(bloom_hex)
    except ValueError as exc:
        raise DecisionIdentityStoreCorruptionError("retired request bloom is invalid") from exc
    if len(bloom) != _BLOOM_BYTES:
        raise DecisionIdentityStoreCorruptionError("retired request bloom has invalid size")
    return all(bloom[position // 8] & (1 << (position % 8)) for position in _bloom_positions(request_id))


def _bloom_add(bloom_hex: str, request_id: str) -> str:
    try:
        bloom = bytearray.fromhex(bloom_hex)
    except ValueError as exc:
        raise DecisionIdentityStoreCorruptionError("retired request bloom is invalid") from exc
    if len(bloom) != _BLOOM_BYTES:
        raise DecisionIdentityStoreCorruptionError("retired request bloom has invalid size")
    for position in _bloom_positions(request_id):
        bloom[position // 8] |= 1 << (position % 8)
    return bytes(bloom).hex()


class DecisionIdentityRecordStore:
    """One explicit-path, cross-process serialized local identity store."""

    def __init__(self, path: str | Path, *, retention_max_records: int = 256):
        if not isinstance(path, (str, Path)) or not str(path).strip():
            raise DecisionIdentityConstructionError(
                "DecisionIdentityRecordStore requires an explicit local path"
            )
        if isinstance(retention_max_records, bool) or int(retention_max_records) < 1:
            raise DecisionIdentityConstructionError(
                "retention_max_records must be a positive integer"
            )
        self.path = Path(path)
        self.lock_path = self.path.with_name(self.path.name + ".lock")
        self.retention_max_records = int(retention_max_records)
        self._thread_lock = threading.RLock()

    def _empty_state(self) -> dict[str, Any]:
        state = {
            "store_schema_version": DECISION_IDENTITY_STORE_SCHEMA_VERSION,
            "retention_max_records": self.retention_max_records,
            "records": {},
            "retired_request_id_bloom": _new_bloom(),
        }
        state["integrity_version"] = DECISION_IDENTITY_INTEGRITY_VERSION
        state["integrity_sha256"] = _state_integrity(state)
        return state

    @contextmanager
    def _exclusive_lock(self) -> Iterator[None]:
        """Combine a process-local lock with an OS-level file lock."""

        with self._thread_lock:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.lock_path, "a+b") as lock_file:
                    lock_file.seek(0)
                    lock_file.write(b"0")
                    lock_file.flush()
                    os.fsync(lock_file.fileno())
                    self._acquire_platform_lock(lock_file)
                    try:
                        yield
                    finally:
                        self._release_platform_lock(lock_file)
            except DecisionIdentityStoreError:
                raise
            except OSError as exc:
                raise DecisionIdentityStoreError("local identity store lock unavailable") from exc

    @staticmethod
    def _acquire_platform_lock(lock_file: Any) -> None:
        if os.name == "nt":
            import msvcrt

            lock_file.seek(0)
            while True:
                try:
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                    return
                except OSError:
                    time.sleep(0.01)
        else:
            import fcntl

            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)

    @staticmethod
    def _release_platform_lock(lock_file: Any) -> None:
        if os.name == "nt":
            import msvcrt

            lock_file.seek(0)
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def _load_state_locked(self) -> dict[str, Any]:
        if not self.path.exists():
            return self._empty_state()
        try:
            raw = self.path.read_text(encoding="utf-8")
            state = json.loads(raw)
        except (OSError, json.JSONDecodeError) as exc:
            raise DecisionIdentityStoreCorruptionError(
                "local identity store is unreadable or invalid JSON"
            ) from exc
        self._validate_state(state)
        return state

    def _validate_state(self, state: Any) -> None:
        if not isinstance(state, Mapping):
            raise DecisionIdentityStoreCorruptionError("identity store root is not a mapping")
        if state.get("store_schema_version") != DECISION_IDENTITY_STORE_SCHEMA_VERSION:
            raise DecisionIdentityStoreCorruptionError("identity store schema mismatch")
        if state.get("integrity_version") != DECISION_IDENTITY_INTEGRITY_VERSION:
            raise DecisionIdentityStoreCorruptionError("identity store integrity version mismatch")
        if state.get("retention_max_records") != self.retention_max_records:
            raise DecisionIdentityStoreCorruptionError("identity store retention contract mismatch")
        if not isinstance(state.get("records"), Mapping):
            raise DecisionIdentityStoreCorruptionError("identity store records are invalid")
        if not isinstance(state.get("retired_request_id_bloom"), str):
            raise DecisionIdentityStoreCorruptionError("identity store retired bloom is invalid")
        _bloom_contains(state["retired_request_id_bloom"], "integrity-probe")
        if state.get("integrity_sha256") != _state_integrity(state):
            raise DecisionIdentityStoreCorruptionError("identity store integrity mismatch")
        for request_id, record in state["records"].items():
            if not isinstance(request_id, str) or not isinstance(record, Mapping):
                raise DecisionIdentityStoreCorruptionError("identity store record shape is invalid")
            self._validate_record(request_id, record)

    @staticmethod
    def _validate_record(request_id: str, record: Mapping[str, Any]) -> None:
        if record.get("decision_request_id") != request_id:
            raise DecisionIdentityStoreCorruptionError("record request id mismatch")
        if record.get("state") not in _DURABLE_STATES:
            raise DecisionIdentityStoreCorruptionError("record state is invalid")
        if record.get("integrity_version") != DECISION_IDENTITY_INTEGRITY_VERSION:
            raise DecisionIdentityStoreCorruptionError("record integrity version mismatch")
        if record.get("integrity_sha256") != _record_integrity(record):
            raise DecisionIdentityStoreCorruptionError("record integrity mismatch")
        required_claim = {
            "claim_schema_version",
            "record_schema_version",
            "decision_request_id",
            "decision_request_identity_version",
            "decision_request_identity_provenance",
            "signal_id",
            "canonical_request_digest",
            "canonical_request_digest_version",
            "claimed_at",
            "issuer_provider_provenance",
        }
        if not required_claim.issubset(record):
            raise DecisionIdentityStoreCorruptionError("record claim material is incomplete")
        if record.get("decision_request_identity_version") != DECISION_REQUEST_IDENTITY_VERSION:
            raise DecisionIdentityStoreCorruptionError("record request identity version is invalid")
        provenance = record.get("decision_request_identity_provenance")
        if not isinstance(provenance, Mapping) or provenance.get("signal_id") != record.get(
            "signal_id"
        ):
            raise DecisionIdentityStoreCorruptionError("record request signal binding is invalid")
        if record.get("canonical_request_digest_version") != DECISION_REQUEST_DIGEST_VERSION:
            raise DecisionIdentityStoreCorruptionError("record digest version is invalid")
        for provenance_name in ("issuer_provider_provenance",):
            provenance_value = record.get(provenance_name)
            if not isinstance(provenance_value, Mapping) or any(
                not _nonempty(provenance_value.get(field))
                for field in ("provider_file", "provider_function", "provider_version")
            ):
                raise DecisionIdentityStoreCorruptionError(
                    f"record {provenance_name} is invalid"
                )
        if record.get("state") == "COMPLETED":
            required_completed = {
                "decision_id",
                "decision_result",
                "allowed",
                "decision_identity_version",
                "decision_identity_provenance",
                "decision_to_signal_correlation",
                "completed_at",
                "factual_provider",
            }
            if not required_completed.issubset(record):
                raise DecisionIdentityStoreCorruptionError(
                    "record completed material is incomplete"
                )
            if record.get("decision_result") not in _TERMINAL_DECISIONS:
                raise DecisionIdentityStoreCorruptionError("record decision result is invalid")
            if not isinstance(record.get("allowed"), bool):
                raise DecisionIdentityStoreCorruptionError("record allowed value is invalid")
            if record.get("decision_identity_version") != DECISION_IDENTITY_VERSION:
                raise DecisionIdentityStoreCorruptionError("record decision identity version is invalid")
            if (record.get("decision_result") == "ALLOW") != record.get("allowed"):
                raise DecisionIdentityStoreCorruptionError(
                    "record decision result and allowed value conflict"
                )
            factual_provider = record.get("factual_provider")
            if not isinstance(factual_provider, Mapping) or any(
                not _nonempty(factual_provider.get(field))
                for field in ("provider_file", "provider_function", "provider_version")
            ):
                raise DecisionIdentityStoreCorruptionError(
                    "record factual provider is invalid"
                )

    def _write_state_locked(self, state: Mapping[str, Any]) -> None:
        material = dict(state)
        material["integrity_version"] = DECISION_IDENTITY_INTEGRITY_VERSION
        material["integrity_sha256"] = _state_integrity(material)
        encoded = _canonical_json(material)
        temp_path: str | None = None
        try:
            descriptor, temp_path = tempfile.mkstemp(
                prefix=self.path.name + ".", suffix=".tmp", dir=self.path.parent
            )
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, self.path)
            temp_path = None
            if os.name != "nt":
                try:
                    directory_fd = os.open(self.path.parent, os.O_RDONLY)
                    try:
                        os.fsync(directory_fd)
                    finally:
                        os.close(directory_fd)
                except OSError:
                    pass
        except OSError as exc:
            raise DecisionIdentityStoreWriteError(
                "local identity store atomic write failed"
            ) from exc
        finally:
            if temp_path:
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass

    def _apply_retention_locked(self, state: dict[str, Any]) -> None:
        records = state["records"]
        overflow = len(records) - self.retention_max_records
        if overflow <= 0:
            return
        ordered = sorted(
            records.items(),
            key=lambda item: (
                str(item[1].get("completed_at") or item[1].get("claimed_at") or ""),
                item[0],
            ),
        )
        bloom = state["retired_request_id_bloom"]
        for request_id, _record in ordered[:overflow]:
            bloom = _bloom_add(bloom, request_id)
            del records[request_id]
        state["retired_request_id_bloom"] = bloom

    def inspect(self, decision_request_id: str) -> dict[str, Any]:
        request_id = _validate_decision_request_id(decision_request_id)
        with self._exclusive_lock():
            state = self._load_state_locked()
            record = state["records"].get(request_id)
            if isinstance(record, Mapping):
                return {
                    "status": "IDENTITY_REPLAY"
                    if record.get("state") == "COMPLETED"
                    else "IDENTITY_REQUEST_INCOMPLETE",
                    "record": dict(record),
                }
            if _bloom_contains(state["retired_request_id_bloom"], request_id):
                return {"status": "IDENTITY_REQUEST_RETIRED", "record": None}
            return {"status": "IDENTITY_RECORD_MISSING", "record": None}

    def claim(
        self,
        request: Mapping[str, Any],
        canonical_request: Mapping[str, Any],
        *,
        issuer_provider_provenance: Mapping[str, Any],
    ) -> dict[str, Any]:
        (
            request_id,
            signal_id,
            digest,
            digest_version,
            provenance,
        ) = _validate_request_and_canonical(request, canonical_request)
        issuer_provider = _validate_provider_provenance(
            issuer_provider_provenance, "issuer_provider_provenance"
        )

        with self._exclusive_lock():
            state = self._load_state_locked()
            record = state["records"].get(request_id)
            if isinstance(record, Mapping):
                if (
                    record.get("canonical_request_digest") != digest
                    or record.get("signal_id") != signal_id
                ):
                    return {"status": "DECISION_REQUEST_ID_CONFLICT", "record": dict(record)}
                if record.get("state") == "COMPLETED":
                    return {"status": "IDENTITY_REPLAY", "record": dict(record)}
                return {"status": "IDENTITY_REQUEST_INCOMPLETE", "record": dict(record)}
            if _bloom_contains(state["retired_request_id_bloom"], request_id):
                return {"status": "DECISION_REQUEST_ID_RETIRED", "record": None}

            record = {
                "claim_schema_version": DECISION_IDENTITY_RECORD_SCHEMA_VERSION,
                "record_schema_version": DECISION_IDENTITY_RECORD_SCHEMA_VERSION,
                "state": "CLAIMED",
                "decision_request_id": request_id,
                "decision_request_identity_version": request.get(
                    "decision_request_identity_version"
                ),
                "decision_request_identity_provenance": dict(provenance),
                "signal_id": signal_id,
                "canonical_request_digest": digest,
                "canonical_request_digest_version": digest_version,
                "claimed_at": _utc_now(),
                "issuer_provider_provenance": issuer_provider,
                "integrity_version": DECISION_IDENTITY_INTEGRITY_VERSION,
            }
            record["integrity_sha256"] = _record_integrity(record)
            state["records"][request_id] = record
            self._apply_retention_locked(state)
            self._write_state_locked(state)
            return {"status": "CLAIMED", "record": dict(record)}

    def complete(
        self,
        request: Mapping[str, Any],
        canonical_request: Mapping[str, Any],
        *,
        decision_id: str,
        decision_result: str,
        allowed: bool,
        factual_provider: Mapping[str, Any],
    ) -> dict[str, Any]:
        request_id, signal_id, digest, _digest_version, _provenance = (
            _validate_request_and_canonical(request, canonical_request)
        )
        literal = _required_text(decision_result, "decision_result").upper()
        if literal not in _TERMINAL_DECISIONS or not isinstance(allowed, bool):
            raise DecisionIdentityConstructionError("completed result is not literal ALLOW/DENY")
        if (literal == "ALLOW") != allowed:
            raise DecisionIdentityConstructionError("completed allowed boolean is incompatible")
        candidate_id = _validate_decision_id(decision_id)
        completed_provider = _validate_provider_provenance(
            factual_provider, "factual_provider"
        )

        with self._exclusive_lock():
            state = self._load_state_locked()
            record = state["records"].get(request_id)
            if not isinstance(record, Mapping):
                return {"status": "DECISION_REQUEST_CLAIM_MISSING", "record": None}
            if (
                record.get("canonical_request_digest") != digest
                or record.get("signal_id") != signal_id
            ):
                return {"status": "DECISION_REQUEST_ID_CONFLICT", "record": dict(record)}
            if record.get("state") == "COMPLETED":
                return {"status": "COMPLETED_OVERWRITE_FORBIDDEN", "record": dict(record)}

            completed = dict(record)
            completed.update(
                {
                    "state": "COMPLETED",
                    "decision_id": candidate_id,
                    "decision_result": literal,
                    "allowed": allowed,
                    "decision_identity_version": DECISION_IDENTITY_VERSION,
                    "decision_identity_provenance": {
                        "mechanism": "SECRETS_TOKEN_URLSAFE_AFTER_TERMINAL_RESULT",
                        "identity_version": DECISION_IDENTITY_VERSION,
                        "request_id": request_id,
                        "signal_id": signal_id,
                    },
                    "decision_to_signal_correlation": {
                        "method": "EXACT_SIGNAL_ID",
                        "version": DECISION_IDENTITY_VERSION,
                        "signal_id": signal_id,
                        "evidence": "CANONICAL_REQUEST_AND_COMPLETED_RECORD",
                    },
                    "completed_at": _utc_now(),
                    "factual_provider": completed_provider,
                    "integrity_version": DECISION_IDENTITY_INTEGRITY_VERSION,
                }
            )
            completed["integrity_sha256"] = _record_integrity(completed)
            state["records"][request_id] = completed
            self._apply_retention_locked(state)
            self._write_state_locked(state)
            return {"status": "COMPLETED", "record": dict(completed)}


def _identity_overlay(
    result: Any, *, status: str, request: Mapping[str, Any] | None = None, **extra: Any
) -> Any:
    if not isinstance(result, Mapping):
        return result
    merged = dict(result)
    metadata = {
        "status": status,
        "identity_version": DECISION_IDENTITY_VERSION,
        **extra,
    }
    if request is not None:
        metadata["decision_request_id"] = request.get("decision_request_id")
        metadata["signal_id"] = request.get("signal_id")
    merged["decision_identity_v2_7a_2"] = metadata
    return merged


def evaluate_current_decision_with_identity(
    payload: Mapping[str, Any],
    current_provider: Callable[[Mapping[str, Any]], Any],
    *,
    store: DecisionIdentityRecordStore | None,
    provider_provenance: Mapping[str, Any] | None = None,
) -> Any:
    """Run the V1 provider exactly once; attach identity only when durable."""

    if not callable(current_provider):
        raise DecisionIdentityConstructionError("current_provider must be callable")
    if store is None:
        return current_provider(payload)

    request: dict[str, Any] | None = None
    canonical: dict[str, Any] | None = None
    claim_status = "IDENTITY_UNAVAILABLE"
    claim_record: Mapping[str, Any] | None = None
    try:
        request = decision_request_from_payload(payload)
        canonical = canonical_decision_request(payload)
        claim = store.claim(
            request,
            canonical,
            issuer_provider_provenance=provider_provenance
            or {
                "provider_file": DECISION_PROVIDER_FILE,
                "provider_function": DECISION_PROVIDER_FUNCTION,
                "provider_version": DECISION_PROVIDER_VERSION,
            },
        )
        claim_status = str(claim.get("status") or "IDENTITY_UNAVAILABLE")
        claim_record = claim.get("record") if isinstance(claim.get("record"), Mapping) else None
    except Exception as exc:
        claim_status = "IDENTITY_UNAVAILABLE"
        claim_record = {"error_type": type(exc).__name__}

    # Never substitute a stored result for the current V1 provider result.
    current_result = current_provider(payload)

    if request is None or canonical is None:
        return _identity_overlay(
            current_result,
            status=claim_status,
            identity_available=False,
            claim_record=claim_record,
        )
    if claim_status == "IDENTITY_REPLAY":
        historical = {
            "decision_request_id": claim_record.get("decision_request_id") if claim_record else None,
            "decision_id": claim_record.get("decision_id") if claim_record else None,
            "decision_result": claim_record.get("decision_result") if claim_record else None,
            "signal_id": claim_record.get("signal_id") if claim_record else None,
            "completed_at": claim_record.get("completed_at") if claim_record else None,
        }
        return _identity_overlay(
            current_result,
            status="IDENTITY_REPLAY_HISTORICAL_ONLY",
            request=request,
            historical=historical,
        )
    if claim_status != "CLAIMED":
        return _identity_overlay(
            current_result,
            status=claim_status,
            request=request,
            identity_available=False,
        )
    if not isinstance(current_result, Mapping):
        return _identity_overlay(
            current_result,
            status="IDENTITY_TERMINAL_RESULT_UNAVAILABLE",
            request=request,
            identity_available=False,
        )

    literal = str(current_result.get("decision") or "").upper().strip()
    allowed = current_result.get("allowed")
    if literal not in _TERMINAL_DECISIONS or not isinstance(allowed, bool) or (
        literal == "ALLOW"
    ) != allowed:
        return _identity_overlay(
            current_result,
            status="IDENTITY_TERMINAL_RESULT_UNAVAILABLE",
            request=request,
            identity_available=False,
        )

    for field, expected in (
        ("decision_request_id", request["decision_request_id"]),
        (
            "decision_request_identity_version",
            request["decision_request_identity_version"],
        ),
        (
            "decision_request_identity_provenance",
            request["decision_request_identity_provenance"],
        ),
    ):
        if field in current_result and current_result.get(field) != expected:
            return _identity_overlay(
                current_result,
                status="DECISION_IDENTITY_FIELD_CONFLICT",
                request=request,
                identity_available=False,
            )
    if _nonempty(current_result.get("decision_id")):
        return _identity_overlay(
            current_result,
            status="DECISION_ID_FIELD_CONFLICT",
            request=request,
            identity_available=False,
        )

    try:
        completion = store.complete(
            request,
            canonical,
            decision_id=_generate_decision_id(),
            decision_result=literal,
            allowed=allowed,
            factual_provider=provider_provenance
            or {
                "provider_file": DECISION_PROVIDER_FILE,
                "provider_function": DECISION_PROVIDER_FUNCTION,
                "provider_version": DECISION_PROVIDER_VERSION,
            },
        )
    except Exception as exc:
        return _identity_overlay(
            current_result,
            status="IDENTITY_COMPLETION_UNAVAILABLE",
            request=request,
            identity_available=False,
            error_type=type(exc).__name__,
        )
    if completion.get("status") != "COMPLETED" or not isinstance(
        completion.get("record"), Mapping
    ):
        return _identity_overlay(
            current_result,
            status=str(completion.get("status") or "IDENTITY_COMPLETION_UNAVAILABLE"),
            request=request,
            identity_available=False,
        )

    record = completion["record"]
    merged = dict(current_result)
    merged["decision_request_id"] = request["decision_request_id"]
    merged["decision_request_identity_version"] = request[
        "decision_request_identity_version"
    ]
    merged["decision_request_identity_provenance"] = request[
        "decision_request_identity_provenance"
    ]
    merged["decision_id"] = record["decision_id"]
    merged["decision_identity_version"] = record["decision_identity_version"]
    merged["decision_identity_provenance"] = record[
        "decision_identity_provenance"
    ]
    return _identity_overlay(
        merged,
        status="COMPLETED",
        request=request,
        identity_available=True,
        completed_at=record.get("completed_at"),
        canonical_request_digest=record.get("canonical_request_digest"),
    )


__all__ = [
    "DECISION_IDENTITY_INTEGRITY_VERSION",
    "DECISION_IDENTITY_RECORD_SCHEMA_VERSION",
    "DECISION_IDENTITY_STORE_SCHEMA_VERSION",
    "DECISION_IDENTITY_VERSION",
    "DECISION_ID_PREFIX",
    "DECISION_PROVIDER_FILE",
    "DECISION_PROVIDER_FUNCTION",
    "DECISION_PROVIDER_VERSION",
    "DECISION_REQUEST_DIGEST_VERSION",
    "DECISION_REQUEST_IDENTITY_VERSION",
    "DECISION_REQUEST_ID_PREFIX",
    "DECISION_REQUEST_ISSUER_FILE",
    "DECISION_REQUEST_ISSUER_FUNCTION",
    "DecisionIdentityConstructionError",
    "DecisionIdentityError",
    "DecisionIdentityRecordStore",
    "DecisionIdentityStoreCorruptionError",
    "DecisionIdentityStoreError",
    "DecisionIdentityStoreWriteError",
    "RETENTION_CONTRACT",
    "canonical_decision_request",
    "decision_request_from_payload",
    "ensure_decision_request_identity",
    "evaluate_current_decision_with_identity",
]
