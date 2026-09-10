"""Offline fail-closed startup admission gate for the C3 maintenance chain.

The gate consumes only injected state and authenticated, sanitized attestations.
It never imports the runtime, opens the Registry or starts workers.  A future
runtime composition must invoke its startup callback while holding the yielded
permit and the same seam lock.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Callable, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_STARTUP_ADMISSION_GATE_CONTRACT_V1_VERSION = (
    "2026-09-10-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-STARTUP-ADMISSION-GATE-CONTRACT-V1"
)
RUNTIME_STARTUP_ADMISSION_GATE_ACK_V1 = (
    "C3_CLOSED_REPAIR_RUNTIME_STARTUP_ADMISSION_GATE_V1"
)
RUNTIME_STARTUP_ADMISSION_GATE_SCOPE_ATTESTATION_V1 = (
    "C3_CLOSED_REPAIR_EXPLICIT_OFFLINE_RUNTIME_STARTUP_ADMISSION_GATE_V1"
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_REQUEST_KEYS = frozenset({"ack", "scope_attestation", "evidence", "request_sha256"})
_EVIDENCE_KEYS = frozenset(
    {"trading_controls", "startup_state", "seam_binding", "maintenance_completion"}
)
_STARTUP_STATE_KEYS = frozenset(
    {
        "mode",
        "startup_phase",
        "runtime_started",
        "workers_started",
        "server_accepting_requests",
        "writer_invocations_seen",
        "generation",
        "process_boot_epoch_sha256",
        "current_coordinator_identity_sha256",
        "writer_guard_bound",
        "writer_mutations_allowed",
        "runtime_activation_allowed",
        "synthetic_only",
        "runtime_integrated",
    }
)
_SEAM_BINDING_KEYS = frozenset(
    {
        "ok",
        "status",
        "writer_guard_bound",
        "same_atomic_lock",
        "registered_writer_count",
        "all_writers_routed",
        "dynamic_at_invocation",
        "coordinator_restored",
        "generation_after",
        "binding_receipt_sha256",
        "synthetic_only",
        "runtime_integrated",
        "production_ready",
        "runtime_activation_allowed",
    }
)
_MAINTENANCE_KEYS = frozenset(
    {
        "ok",
        "status",
        "observation_verified",
        "repair_verified",
        "bootstrap_verified",
        "recovery_verified",
        "postflight_verified",
        "rollback_verified",
        "maintenance_lease_released",
        "unresolved_transactions_after",
        "conflicts_remaining",
        "registry_preservation_verified",
        "authority_commit_verified",
        "maintenance_epoch",
        "source_registry_sha256",
        "candidate_registry_sha256",
        "completion_receipt_sha256",
        "real_registry_accessed",
        "write_executed",
        "registry_write",
        "network_accessed",
        "broker_called",
        "no_order_sent",
        "synthetic_only",
        "runtime_integrated",
        "production_authority",
    }
)
_AUTHORITY_RECEIPT_KEYS = frozenset(
    {
        "ok",
        "status",
        "evidence_sha256",
        "process_boot_epoch_sha256",
        "authority_root_sha256",
        "authority_generation",
        "signature_verified",
        "revocation_checked",
        "authority_revoked",
        "freshness_verified",
        "production_authority",
        "synthetic_only",
        "runtime_integrated",
        "receipt_sha256",
    }
)
_SAFE_TRADING_CONTROLS = {
    "enable_real_trading": False,
    "broker_dry_run": True,
    "falcon_mode": "VERIFY",
    "central_real_execution_enabled": False,
    "central_real_pilot_enabled": False,
    "live_trading_enabled": False,
    "order_submission_authorized": False,
}


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _stable_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _valid_sha256(value: Any) -> str | None:
    candidate = str(value or "").lower().strip()
    return candidate if _SHA256_RE.fullmatch(candidate) else None


def runtime_startup_admission_request_sha256_v1(request: Mapping[str, Any]) -> str:
    if not isinstance(request, Mapping):
        raise TypeError("request must be a mapping")
    return _stable_sha256(
        {key: value for key, value in request.items() if key != "request_sha256"}
    )


def production_evidence_verifier_identity_sha256_v1(verifier: Any) -> str:
    if not callable(verifier):
        raise TypeError("verifier must be callable")
    module = str(getattr(verifier, "__module__", "") or "")
    qualname = str(getattr(verifier, "__qualname__", "") or "")
    owner = getattr(verifier, "__self__", None)
    owner_name = type(owner).__qualname__ if owner is not None else ""
    if not module or not qualname:
        raise TypeError("verifier identity is unavailable")
    return hashlib.sha256(
        f"{module}:{qualname}:{owner_name}".encode("utf-8")
    ).hexdigest()


class RuntimeStartupAdmissionBlocked(RuntimeError):
    def __init__(self, reason: str) -> None:
        self.reason = str(reason or "C3_RUNTIME_STARTUP_ADMISSION_BLOCKED")
        super().__init__(self.reason)


@dataclass(frozen=True)
class RuntimeStartupAdmissionGateConfigV1:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    expected_authority_root_sha256: str | None = field(default=None, repr=False)
    expected_verifier_identity_sha256: str | None = field(default=None, repr=False)


@dataclass(frozen=True)
class RuntimeStartupAdmissionPermitV1:
    startup_allowed: bool
    runtime_activation_allowed: bool
    live_allowed: bool
    order_submission_authorized: bool
    same_atomic_lock: bool
    generation: int
    process_boot_epoch_sha256: str = field(repr=False)
    evidence_sha256: str = field(repr=False)
    authority_receipt_sha256: str = field(repr=False)
    seam_binding_receipt_sha256: str = field(repr=False)
    maintenance_completion_receipt_sha256: str = field(repr=False)


class RuntimeStartupAdmissionGateContractV1:
    """Issue one process-local startup permit from complete production proof."""

    def __init__(
        self,
        *,
        startup_state: Callable[[], Mapping[str, Any]],
        production_evidence_verifier: Callable[[Mapping[str, Any], str], Mapping[str, Any]],
        atomic_lock: Any,
        config: RuntimeStartupAdmissionGateConfigV1 | None = None,
    ) -> None:
        if not callable(startup_state) or not callable(production_evidence_verifier):
            raise TypeError("startup state and production verifier are required")
        if atomic_lock is None or not all(
            callable(getattr(atomic_lock, name, None))
            for name in ("__enter__", "__exit__")
        ):
            raise TypeError("one context-manager atomic lock is required")
        self._startup_state = startup_state
        self._verifier = production_evidence_verifier
        self._lock = atomic_lock
        self._config = config or RuntimeStartupAdmissionGateConfigV1()
        self._active_permit: RuntimeStartupAdmissionPermitV1 | None = None
        self._consumed: set[str] = set()

    def __repr__(self) -> str:
        return "<RuntimeStartupAdmissionGateContractV1 protected>"

    def snapshot(self) -> dict[str, Any]:
        enabled = bool(
            self._config.enabled is True
            and self._config.scope_attestation
            == RUNTIME_STARTUP_ADMISSION_GATE_SCOPE_ATTESTATION_V1
            and _valid_sha256(self._config.expected_authority_root_sha256)
            and _valid_sha256(self._config.expected_verifier_identity_sha256)
        )
        return {
            "ok": enabled,
            "status": (
                "C3_RUNTIME_STARTUP_ADMISSION_GATE_OFFLINE_READY"
                if enabled
                else "C3_RUNTIME_STARTUP_ADMISSION_GATE_DORMANT_DEFAULT_OFF"
            ),
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_STARTUP_ADMISSION_GATE_CONTRACT_V1_VERSION,
            "enabled": enabled,
            "default_off": not enabled,
            "active_admission": self._active_permit is not None,
            "consumed_request_count": len(self._consumed),
            "runtime_integrated": False,
            "production_ready": False,
            "live_allowed": False,
            "order_submission_authorized": False,
            "real_registry_accessed": False,
            "write_executed": False,
            "registry_write": False,
            "network_accessed": False,
            "broker_called": False,
            "no_order_sent": True,
        }

    def _require_enabled(self) -> tuple[str, str]:
        if self._config.enabled is not True:
            raise RuntimeStartupAdmissionBlocked(
                "C3_RUNTIME_STARTUP_ADMISSION_GATE_DEFAULT_OFF"
            )
        if (
            self._config.scope_attestation
            != RUNTIME_STARTUP_ADMISSION_GATE_SCOPE_ATTESTATION_V1
        ):
            raise RuntimeStartupAdmissionBlocked(
                "C3_RUNTIME_STARTUP_ADMISSION_GATE_SCOPE_REQUIRED"
            )
        root = _valid_sha256(self._config.expected_authority_root_sha256)
        expected_verifier = _valid_sha256(
            self._config.expected_verifier_identity_sha256
        )
        if not root or not expected_verifier:
            raise RuntimeStartupAdmissionBlocked(
                "C3_RUNTIME_STARTUP_ADMISSION_AUTHORITY_BINDING_REQUIRED"
            )
        try:
            actual_verifier = production_evidence_verifier_identity_sha256_v1(
                self._verifier
            )
        except TypeError as exc:
            raise RuntimeStartupAdmissionBlocked(
                "C3_RUNTIME_STARTUP_ADMISSION_VERIFIER_IDENTITY_INVALID"
            ) from exc
        if not hmac.compare_digest(expected_verifier, actual_verifier):
            raise RuntimeStartupAdmissionBlocked(
                "C3_RUNTIME_STARTUP_ADMISSION_VERIFIER_IDENTITY_MISMATCH"
            )
        return root, expected_verifier

    @staticmethod
    def _startup_state_safe(value: Any) -> bool:
        return bool(
            isinstance(value, Mapping)
            and set(value) == _STARTUP_STATE_KEYS
            and value.get("mode") == "DORMANT"
            and value.get("startup_phase") == "PRE_RUNTIME"
            and value.get("runtime_started") is False
            and value.get("workers_started") is False
            and value.get("server_accepting_requests") is False
            and type(value.get("writer_invocations_seen")) is int
            and value.get("writer_invocations_seen") == 0
            and type(value.get("generation")) is int
            and value.get("generation") >= 2
            and _valid_sha256(value.get("process_boot_epoch_sha256"))
            and _valid_sha256(value.get("current_coordinator_identity_sha256"))
            and value.get("writer_guard_bound") is True
            and value.get("writer_mutations_allowed") is True
            and value.get("runtime_activation_allowed") is False
            and value.get("synthetic_only") is False
            and value.get("runtime_integrated") is True
        )

    @staticmethod
    def _seam_binding_safe(value: Any, startup: Mapping[str, Any]) -> bool:
        return bool(
            isinstance(value, Mapping)
            and set(value) == _SEAM_BINDING_KEYS
            and value.get("ok") is True
            and value.get("status")
            == "C3_PREBOOTSTRAP_REAL_SEAM_CAS_ADAPTER_BOUND_PRODUCTION"
            and value.get("writer_guard_bound") is True
            and value.get("same_atomic_lock") is True
            and value.get("registered_writer_count") == 19
            and value.get("all_writers_routed") is True
            and value.get("dynamic_at_invocation") is True
            and value.get("coordinator_restored") is True
            and type(value.get("generation_after")) is int
            and value.get("generation_after") == startup.get("generation")
            and _valid_sha256(value.get("binding_receipt_sha256"))
            and value.get("synthetic_only") is False
            and value.get("runtime_integrated") is True
            and value.get("production_ready") is True
            and value.get("runtime_activation_allowed") is False
        )

    @staticmethod
    def _maintenance_safe(value: Any) -> bool:
        required_true = (
            "observation_verified",
            "repair_verified",
            "bootstrap_verified",
            "recovery_verified",
            "postflight_verified",
            "rollback_verified",
            "maintenance_lease_released",
            "registry_preservation_verified",
            "authority_commit_verified",
        )
        return bool(
            isinstance(value, Mapping)
            and set(value) == _MAINTENANCE_KEYS
            and value.get("ok") is True
            and value.get("status") == "C3_PREBOOTSTRAP_MAINTENANCE_COMPLETED"
            and all(value.get(key) is True for key in required_true)
            and type(value.get("unresolved_transactions_after")) is int
            and value.get("unresolved_transactions_after") == 0
            and type(value.get("conflicts_remaining")) is int
            and value.get("conflicts_remaining") == 0
            and type(value.get("maintenance_epoch")) is int
            and value.get("maintenance_epoch") >= 1
            and _valid_sha256(value.get("source_registry_sha256"))
            and _valid_sha256(value.get("candidate_registry_sha256"))
            and _valid_sha256(value.get("completion_receipt_sha256"))
            and value.get("real_registry_accessed") is True
            and type(value.get("write_executed")) is bool
            and type(value.get("registry_write")) is bool
            and value.get("write_executed") is value.get("registry_write")
            and value.get("network_accessed") is False
            and value.get("broker_called") is False
            and value.get("no_order_sent") is True
            and value.get("synthetic_only") is False
            and value.get("runtime_integrated") is True
            and value.get("production_authority") is True
        )

    @staticmethod
    def _authority_receipt_safe(
        receipt: Any,
        *,
        evidence_sha: str,
        boot_sha: str,
        authority_root_sha: str,
    ) -> bool:
        if not isinstance(receipt, Mapping) or set(receipt) != _AUTHORITY_RECEIPT_KEYS:
            return False
        payload = dict(receipt)
        supplied = _valid_sha256(payload.pop("receipt_sha256", None))
        return bool(
            receipt.get("ok") is True
            and receipt.get("status")
            == "C3_PRODUCTION_STARTUP_EVIDENCE_AUTHENTICATED"
            and receipt.get("evidence_sha256") == evidence_sha
            and receipt.get("process_boot_epoch_sha256") == boot_sha
            and receipt.get("authority_root_sha256") == authority_root_sha
            and type(receipt.get("authority_generation")) is int
            and receipt.get("authority_generation") >= 1
            and receipt.get("signature_verified") is True
            and receipt.get("revocation_checked") is True
            and receipt.get("authority_revoked") is False
            and receipt.get("freshness_verified") is True
            and receipt.get("production_authority") is True
            and receipt.get("synthetic_only") is False
            and receipt.get("runtime_integrated") is True
            and supplied
            and hmac.compare_digest(supplied, _stable_sha256(payload))
        )

    def _validate_request(self, request: Any) -> tuple[str, Mapping[str, Any]]:
        if not isinstance(request, Mapping) or set(request) != _REQUEST_KEYS:
            raise RuntimeStartupAdmissionBlocked(
                "C3_RUNTIME_STARTUP_ADMISSION_REQUEST_INVALID"
            )
        if request.get("ack") != RUNTIME_STARTUP_ADMISSION_GATE_ACK_V1:
            raise RuntimeStartupAdmissionBlocked(
                "C3_RUNTIME_STARTUP_ADMISSION_ACK_REQUIRED"
            )
        if (
            request.get("scope_attestation")
            != RUNTIME_STARTUP_ADMISSION_GATE_SCOPE_ATTESTATION_V1
        ):
            raise RuntimeStartupAdmissionBlocked(
                "C3_RUNTIME_STARTUP_ADMISSION_REQUEST_SCOPE_INVALID"
            )
        supplied = _valid_sha256(request.get("request_sha256"))
        try:
            expected = runtime_startup_admission_request_sha256_v1(request)
        except (TypeError, ValueError, OverflowError) as exc:
            raise RuntimeStartupAdmissionBlocked(
                "C3_RUNTIME_STARTUP_ADMISSION_REQUEST_INVALID"
            ) from exc
        if not supplied or not hmac.compare_digest(supplied, expected):
            raise RuntimeStartupAdmissionBlocked(
                "C3_RUNTIME_STARTUP_ADMISSION_REQUEST_HASH_MISMATCH"
            )
        evidence = request.get("evidence")
        if not isinstance(evidence, Mapping) or set(evidence) != _EVIDENCE_KEYS:
            raise RuntimeStartupAdmissionBlocked(
                "C3_RUNTIME_STARTUP_ADMISSION_EVIDENCE_INVALID"
            )
        return supplied, evidence

    @contextmanager
    def startup_admission(
        self, request: Any
    ) -> Iterator[RuntimeStartupAdmissionPermitV1]:
        authority_root, _ = self._require_enabled()
        if self._active_permit is not None:
            raise RuntimeStartupAdmissionBlocked(
                "C3_RUNTIME_STARTUP_ADMISSION_NESTED_FORBIDDEN"
            )
        request_sha, evidence = self._validate_request(request)
        if request_sha in self._consumed:
            raise RuntimeStartupAdmissionBlocked(
                "C3_RUNTIME_STARTUP_ADMISSION_REQUEST_REPLAY_BLOCKED"
            )
        controls = evidence.get("trading_controls")
        startup = evidence.get("startup_state")
        seam_binding = evidence.get("seam_binding")
        maintenance = evidence.get("maintenance_completion")
        if not (
            isinstance(controls, Mapping)
            and dict(controls) == _SAFE_TRADING_CONTROLS
            and self._startup_state_safe(startup)
            and self._seam_binding_safe(seam_binding, startup)
            and self._maintenance_safe(maintenance)
        ):
            raise RuntimeStartupAdmissionBlocked(
                "C3_RUNTIME_STARTUP_ADMISSION_EVIDENCE_UNSAFE"
            )
        evidence_sha = _stable_sha256(evidence)
        with self._lock:
            try:
                before = self._startup_state()
            except Exception as exc:
                raise RuntimeStartupAdmissionBlocked(
                    "C3_RUNTIME_STARTUP_ADMISSION_STATE_READ_FAILED"
                ) from exc
            if before != startup or not self._startup_state_safe(before):
                raise RuntimeStartupAdmissionBlocked(
                    "C3_RUNTIME_STARTUP_ADMISSION_STATE_MISMATCH"
                )
            try:
                authority = self._verifier(evidence, evidence_sha)
            except Exception as exc:
                raise RuntimeStartupAdmissionBlocked(
                    "C3_RUNTIME_STARTUP_ADMISSION_AUTHORITY_FAILED"
                ) from exc
            if not self._authority_receipt_safe(
                authority,
                evidence_sha=evidence_sha,
                boot_sha=startup["process_boot_epoch_sha256"],
                authority_root_sha=authority_root,
            ):
                raise RuntimeStartupAdmissionBlocked(
                    "C3_RUNTIME_STARTUP_ADMISSION_AUTHORITY_INVALID"
                )
            try:
                final_state = self._startup_state()
            except Exception as exc:
                raise RuntimeStartupAdmissionBlocked(
                    "C3_RUNTIME_STARTUP_ADMISSION_FINAL_STATE_READ_FAILED"
                ) from exc
            if final_state != before:
                raise RuntimeStartupAdmissionBlocked(
                    "C3_RUNTIME_STARTUP_ADMISSION_STATE_DRIFT"
                )
            self._consumed.add(request_sha)
            permit = RuntimeStartupAdmissionPermitV1(
                startup_allowed=True,
                runtime_activation_allowed=False,
                live_allowed=False,
                order_submission_authorized=False,
                same_atomic_lock=True,
                generation=startup["generation"],
                process_boot_epoch_sha256=startup["process_boot_epoch_sha256"],
                evidence_sha256=evidence_sha,
                authority_receipt_sha256=authority["receipt_sha256"],
                seam_binding_receipt_sha256=seam_binding[
                    "binding_receipt_sha256"
                ],
                maintenance_completion_receipt_sha256=maintenance[
                    "completion_receipt_sha256"
                ],
            )
            self._active_permit = permit
            try:
                yield permit
            finally:
                self._active_permit = None


__all__ = [
    "RUNTIME_STARTUP_ADMISSION_GATE_ACK_V1",
    "RUNTIME_STARTUP_ADMISSION_GATE_SCOPE_ATTESTATION_V1",
    "RuntimeStartupAdmissionBlocked",
    "RuntimeStartupAdmissionGateConfigV1",
    "RuntimeStartupAdmissionGateContractV1",
    "RuntimeStartupAdmissionPermitV1",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_STARTUP_ADMISSION_GATE_CONTRACT_V1_VERSION",
    "production_evidence_verifier_identity_sha256_v1",
    "runtime_startup_admission_request_sha256_v1",
]
