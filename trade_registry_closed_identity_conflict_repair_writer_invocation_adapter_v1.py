"""Default-off invocation interfaces for CLOSED-repair writer callables.

The synthetic adapter remains available for its original rehearsal.  The
production-shaped interface added here accepts only an explicit, attested set
of injected invokers and is not imported or installed by the runtime.
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1 as coordinator_module


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_WRITER_INVOCATION_ADAPTER_V1_VERSION = (
    "2026-09-04-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-WRITER-INVOCATION-ADAPTER-V1"
)

SYNTHETIC_WRITER_CALLABLE_SCOPE_ATTESTATION_V1 = (
    "SYNTHETIC_IN_MEMORY_WRITER_CALLABLES_ONLY_V1"
)
PRODUCTION_WRITER_CALLABLE_EXPLICIT_BINDING_ATTESTATION_V1 = (
    "C3_PRODUCTION_WRITER_CALLABLE_EXPLICIT_BINDING_V1"
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_LABEL_RE = re.compile(r"^[A-Z0-9_.:-]{1,160}$")
_ORIGIN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]{0,255}$")
_CALLABLE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.:<>]{0,255}$")
_REENTRANCY_MODE = "OWNER_TOKEN_REENTRANT_OUTERMOST_RELEASE_V1"
_PRODUCTION_CALLABLE_BINDING_SCOPES = frozenset(
    {"TEMPORARY_TEST", "EXPLICIT_RUNTIME"}
)


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


class SyntheticWriterInvocationBlocked(RuntimeError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class SyntheticWriterInvocationContextV1:
    writer_id: str
    depth: int
    reentrant: bool
    shared_lock_acquired: bool
    owner_token: str = field(repr=False)


@dataclass(frozen=True)
class ProductionWriterInvocationContextV1:
    writer_id: str
    depth: int
    reentrant: bool
    shared_lock_acquired: bool
    owner_token: str = field(repr=False)


@dataclass(frozen=True)
class ProductionWriterInvocationConfigV1:
    enabled: bool = False
    scope_attestation: str | None = None
    callable_binding_scope: str | None = None
    callable_manifest_sha256: str | None = None


@dataclass(frozen=True)
class SyntheticWriterCallableV1:
    writer_id: str
    label: str
    origin_module: str
    binding_sha256: str
    callback: Callable[[Mapping[str, Any], SyntheticWriterInvocationContextV1], Mapping[str, Any]] = field(
        repr=False, compare=False
    )


@dataclass(frozen=True)
class ProductionWriterCallableV1:
    writer_id: str
    label: str
    origin_module: str
    callable_name: str
    source_signature_sha256: str
    binding_scope: str
    binding_sha256: str
    callback: Callable[
        [Mapping[str, Any], ProductionWriterInvocationContextV1],
        Mapping[str, Any],
    ] = field(repr=False, compare=False)


def _production_callable_binding_payload_v1(
    wrapper: ProductionWriterCallableV1,
) -> dict[str, str]:
    return {
        "writer_id": wrapper.writer_id,
        "label": wrapper.label,
        "origin_module": wrapper.origin_module,
        "callable_name": wrapper.callable_name,
        "source_signature_sha256": wrapper.source_signature_sha256,
        "binding_scope": wrapper.binding_scope,
        "scope_attestation": (
            PRODUCTION_WRITER_CALLABLE_EXPLICIT_BINDING_ATTESTATION_V1
        ),
    }


def production_writer_callable_manifest_sha256_v1(
    callables: Sequence[ProductionWriterCallableV1],
) -> str:
    if not isinstance(callables, Sequence) or isinstance(
        callables, (str, bytes, bytearray)
    ):
        raise TypeError("callables must be a sequence")
    payloads = []
    for wrapper in callables:
        if not isinstance(wrapper, ProductionWriterCallableV1):
            raise TypeError("unattested production callable")
        payloads.append(
            {
                **_production_callable_binding_payload_v1(wrapper),
                "binding_sha256": wrapper.binding_sha256,
            }
        )
    return _stable_sha256(payloads)


def build_production_writer_callable_v1(
    writer_id: str,
    callback: Callable[
        [Mapping[str, Any], ProductionWriterInvocationContextV1],
        Mapping[str, Any],
    ],
    *,
    label: str,
    source_signature_sha256: str,
    binding_scope: str,
    scope_attestation: str,
) -> ProductionWriterCallableV1:
    normalized_writer_id = str(writer_id or "").strip()
    normalized_label = str(label or "").upper().strip()
    normalized_signature_sha = str(source_signature_sha256 or "").lower().strip()
    normalized_scope = str(binding_scope or "").upper().strip()
    if (
        scope_attestation
        != PRODUCTION_WRITER_CALLABLE_EXPLICIT_BINDING_ATTESTATION_V1
    ):
        raise SyntheticWriterInvocationBlocked(
            "PRODUCTION_CALLABLE_SCOPE_ATTESTATION_REQUIRED"
        )
    canonical_ids = {
        item["writer_id"]
        for item in coordinator_module.canonical_runtime_writer_inventory_v1()
    }
    if normalized_writer_id not in canonical_ids:
        raise SyntheticWriterInvocationBlocked("UNKNOWN_WRITER")
    if not callable(callback):
        raise SyntheticWriterInvocationBlocked("PRODUCTION_CALLBACK_REQUIRED")
    if not _LABEL_RE.fullmatch(normalized_label):
        raise SyntheticWriterInvocationBlocked("PRODUCTION_CALLBACK_LABEL_INVALID")
    if not _SHA256_RE.fullmatch(normalized_signature_sha):
        raise SyntheticWriterInvocationBlocked("SOURCE_SIGNATURE_SHA256_INVALID")
    if normalized_scope not in _PRODUCTION_CALLABLE_BINDING_SCOPES:
        raise SyntheticWriterInvocationBlocked(
            "PRODUCTION_CALLABLE_BINDING_SCOPE_INVALID"
        )
    origin = str(
        getattr(callback, "__module__", callback.__class__.__module__) or ""
    ).strip()
    callable_name = str(
        getattr(callback, "__qualname__", callback.__class__.__qualname__) or ""
    ).strip()
    if not _ORIGIN_RE.fullmatch(origin) or not _CALLABLE_NAME_RE.fullmatch(
        callable_name
    ):
        raise SyntheticWriterInvocationBlocked(
            "PRODUCTION_CALLBACK_IDENTITY_INVALID"
        )
    if normalized_scope == "TEMPORARY_TEST" and (
        origin == "main"
        or origin == "trade_registry"
        or origin.startswith("bots")
    ):
        raise SyntheticWriterInvocationBlocked(
            "REAL_RUNTIME_CALLBACK_FORBIDDEN_IN_TEMPORARY_SCOPE"
        )
    provisional = ProductionWriterCallableV1(
        writer_id=normalized_writer_id,
        label=normalized_label,
        origin_module=origin,
        callable_name=callable_name,
        source_signature_sha256=normalized_signature_sha,
        binding_scope=normalized_scope,
        binding_sha256="",
        callback=callback,
    )
    return ProductionWriterCallableV1(
        **{
            **provisional.__dict__,
            "binding_sha256": _stable_sha256(
                _production_callable_binding_payload_v1(provisional)
            ),
        }
    )


def build_synthetic_writer_callable_v1(
    writer_id: str,
    callback: Callable[
        [Mapping[str, Any], SyntheticWriterInvocationContextV1], Mapping[str, Any]
    ],
    *,
    label: str,
    scope_attestation: str,
) -> SyntheticWriterCallableV1:
    normalized_writer_id = str(writer_id or "").strip()
    normalized_label = str(label or "").upper().strip()
    if scope_attestation != SYNTHETIC_WRITER_CALLABLE_SCOPE_ATTESTATION_V1:
        raise SyntheticWriterInvocationBlocked("SYNTHETIC_CALLABLE_SCOPE_REQUIRED")
    canonical_ids = {
        item["writer_id"]
        for item in coordinator_module.canonical_runtime_writer_inventory_v1()
    }
    if normalized_writer_id not in canonical_ids:
        raise SyntheticWriterInvocationBlocked("UNKNOWN_WRITER")
    if not callable(callback):
        raise SyntheticWriterInvocationBlocked("SYNTHETIC_CALLBACK_REQUIRED")
    if not _LABEL_RE.fullmatch(normalized_label):
        raise SyntheticWriterInvocationBlocked("SYNTHETIC_CALLBACK_LABEL_INVALID")
    origin = str(
        getattr(callback, "__module__", callback.__class__.__module__) or ""
    ).strip()
    if origin == "main" or origin == "trade_registry" or origin.startswith("bots"):
        raise SyntheticWriterInvocationBlocked("REAL_RUNTIME_CALLBACK_FORBIDDEN")
    binding = {
        "writer_id": normalized_writer_id,
        "label": normalized_label,
        "origin_module": origin,
        "scope_attestation": scope_attestation,
    }
    return SyntheticWriterCallableV1(
        writer_id=normalized_writer_id,
        label=normalized_label,
        origin_module=origin,
        binding_sha256=_stable_sha256(binding),
        callback=callback,
    )


class DormantSyntheticWriterInvocationAdapterV1:
    """Invoke only attested synthetic callables through coordinator permits."""

    def __init__(
        self,
        *,
        enabled: bool = False,
        coordinator: coordinator_module.ClosedRepairWriterRuntimeCoordinatorV1
        | None = None,
        seam_bindings: Sequence[Mapping[str, Any]] | None = None,
        synthetic_callables: Sequence[SyntheticWriterCallableV1] | None = None,
        scope_attestation: str | None = None,
    ) -> None:
        self._enabled = bool(enabled)
        self._coordinator = coordinator
        self._bindings: dict[str, dict[str, Any]] = {}
        self._callables: dict[str, SyntheticWriterCallableV1] = {}
        if not self._enabled:
            return
        if scope_attestation != SYNTHETIC_WRITER_CALLABLE_SCOPE_ATTESTATION_V1:
            raise SyntheticWriterInvocationBlocked("SYNTHETIC_ADAPTER_SCOPE_REQUIRED")
        if coordinator is None or coordinator.enabled is not True:
            raise SyntheticWriterInvocationBlocked("ENABLED_COORDINATOR_REQUIRED")
        if coordinator.all_writers_registered is not True:
            raise SyntheticWriterInvocationBlocked("ALL_19_WRITERS_MUST_BE_REGISTERED")
        expected = coordinator_module.canonical_runtime_writer_inventory_v1()
        bindings = list(seam_bindings or ())
        wrappers = list(synthetic_callables or ())
        if len(bindings) != 19:
            raise SyntheticWriterInvocationBlocked("EXACTLY_19_SEAM_BINDINGS_REQUIRED")
        if len(wrappers) != 19:
            raise SyntheticWriterInvocationBlocked("EXACTLY_19_SYNTHETIC_CALLABLES_REQUIRED")
        expected_ids = [item["writer_id"] for item in expected]
        binding_ids: list[str] = []
        for expected_writer, binding in zip(expected, bindings, strict=True):
            if not isinstance(binding, Mapping):
                raise SyntheticWriterInvocationBlocked("SEAM_BINDING_INVALID")
            writer = binding.get("writer")
            writer_id = str(
                writer.get("writer_id") if isinstance(writer, Mapping) else ""
            )
            if (
                dict(writer) != expected_writer
                or binding.get("reentrancy_mode") != _REENTRANCY_MODE
                or binding.get("same_owner_token_required_for_nested_calls")
                is not True
                or binding.get("sink_token_validation_required") is not True
                or binding.get("runtime_callable_bound") is not False
                or not _SHA256_RE.fullmatch(
                    str(binding.get("source_signature_sha256") or "")
                )
            ):
                raise SyntheticWriterInvocationBlocked("SEAM_BINDING_INVALID")
            binding_ids.append(writer_id)
            self._bindings[writer_id] = copy.deepcopy(dict(binding))
        if binding_ids != expected_ids or len(set(binding_ids)) != 19:
            raise SyntheticWriterInvocationBlocked("SEAM_BINDING_ORDER_OR_ID_INVALID")
        wrapper_ids: list[str] = []
        for wrapper in wrappers:
            if not isinstance(wrapper, SyntheticWriterCallableV1):
                raise SyntheticWriterInvocationBlocked(
                    "UNATTESTED_SYNTHETIC_CALLABLE_FORBIDDEN"
                )
            if not _SHA256_RE.fullmatch(wrapper.binding_sha256):
                raise SyntheticWriterInvocationBlocked(
                    "SYNTHETIC_CALLABLE_BINDING_INVALID"
                )
            expected_sha = _stable_sha256(
                {
                    "writer_id": wrapper.writer_id,
                    "label": wrapper.label,
                    "origin_module": wrapper.origin_module,
                    "scope_attestation": scope_attestation,
                }
            )
            if not hmac.compare_digest(wrapper.binding_sha256, expected_sha):
                raise SyntheticWriterInvocationBlocked(
                    "SYNTHETIC_CALLABLE_BINDING_INVALID"
                )
            wrapper_ids.append(wrapper.writer_id)
            self._callables[wrapper.writer_id] = wrapper
        if set(wrapper_ids) != set(expected_ids) or len(set(wrapper_ids)) != 19:
            raise SyntheticWriterInvocationBlocked(
                "SYNTHETIC_CALLABLE_WRITER_SET_INVALID"
            )

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def bound_writer_count(self) -> int:
        return len(self._callables)

    @staticmethod
    def _base_result(writer_id: str) -> dict[str, Any]:
        return {
            "ok": False,
            "status": "SYNTHETIC_WRITER_INVOCATION_BLOCKED",
            "reason": None,
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_WRITER_INVOCATION_ADAPTER_V1_VERSION,
            "writer_id": writer_id,
            "dormant": True,
            "offline_only": True,
            "synthetic_only": True,
            "callable_invoked": False,
            "write_executed": False,
            "registry_write": False,
            "runtime_integrated": False,
            "real_callable_bound": False,
            "real_registry_accessed": False,
            "network_accessed": False,
            "broker_called": False,
            "no_order_sent": True,
        }

    def invoke(
        self,
        writer_id: str,
        payload: Mapping[str, Any],
        *,
        expected_owner_token: str | None = None,
    ) -> dict[str, Any]:
        normalized_writer_id = str(writer_id or "").strip()
        result = self._base_result(normalized_writer_id)
        if not self._enabled:
            result["reason"] = "WRITER_INVOCATION_ADAPTER_DEFAULT_OFF"
            return result
        wrapper = self._callables.get(normalized_writer_id)
        binding = self._bindings.get(normalized_writer_id)
        if wrapper is None or binding is None:
            result["reason"] = "WRITER_NOT_BOUND"
            return result
        if not isinstance(payload, Mapping):
            result["reason"] = "SYNTHETIC_PAYLOAD_MAPPING_REQUIRED"
            return result
        try:
            canonical_payload = json.loads(_canonical_json(dict(payload)))
        except Exception:
            result["reason"] = "SYNTHETIC_PAYLOAD_NOT_CANONICALIZABLE"
            return result
        payload_sha = _stable_sha256(canonical_payload)
        try:
            with self._coordinator.mutation(normalized_writer_id) as permit:
                if (
                    permit.admitted is not True
                    or permit.coordinated is not True
                    or permit.writer_id != normalized_writer_id
                    or permit.shared_lock_acquired is not True
                    or not _SHA256_RE.fullmatch(str(permit.owner_token or ""))
                    or not isinstance(permit.depth, int)
                    or isinstance(permit.depth, bool)
                    or permit.depth < 1
                ):
                    raise SyntheticWriterInvocationBlocked(
                        "COORDINATOR_MUTATION_PERMIT_INVALID"
                    )
                if permit.reentrant:
                    if (
                        not _SHA256_RE.fullmatch(str(expected_owner_token or ""))
                        or not hmac.compare_digest(
                            str(permit.owner_token), str(expected_owner_token)
                        )
                        or permit.depth < 2
                    ):
                        raise SyntheticWriterInvocationBlocked(
                            "REENTRANT_OWNER_TOKEN_INVALID"
                        )
                elif expected_owner_token is not None:
                    raise SyntheticWriterInvocationBlocked(
                        "OUTER_INVOCATION_OWNER_TOKEN_FORBIDDEN"
                    )
                context = SyntheticWriterInvocationContextV1(
                    writer_id=normalized_writer_id,
                    depth=permit.depth,
                    reentrant=permit.reentrant,
                    shared_lock_acquired=permit.shared_lock_acquired,
                    owner_token=str(permit.owner_token),
                )
                result["callable_invoked"] = True
                callback_result = wrapper.callback(
                    copy.deepcopy(canonical_payload), context
                )
                if not isinstance(callback_result, Mapping):
                    raise SyntheticWriterInvocationBlocked(
                        "SYNTHETIC_CALLBACK_RESULT_MAPPING_REQUIRED"
                    )
                canonical_callback_result = json.loads(
                    _canonical_json(dict(callback_result))
                )
                if str(permit.owner_token) in _canonical_json(
                    canonical_callback_result
                ):
                    raise SyntheticWriterInvocationBlocked(
                        "OWNER_TOKEN_DISCLOSURE_BLOCKED"
                    )
                receipt = {
                    "writer_id": normalized_writer_id,
                    "synthetic_callable_binding_sha256": wrapper.binding_sha256,
                    "source_signature_sha256": binding[
                        "source_signature_sha256"
                    ],
                    "payload_sha256": payload_sha,
                    "result_sha256": _stable_sha256(canonical_callback_result),
                    "owner_token_sha256": _stable_sha256(
                        {"owner_token": permit.owner_token}
                    ),
                    "depth": permit.depth,
                    "reentrant": permit.reentrant,
                    "shared_lock_acquired": permit.shared_lock_acquired,
                }
                receipt["receipt_sha256"] = _stable_sha256(receipt)
                result.update(
                    {
                        "ok": True,
                        "status": "SYNTHETIC_WRITER_INVOCATION_ADMITTED",
                        "reason": None,
                        "result_payload": canonical_callback_result,
                        "invocation_receipt": receipt,
                    }
                )
                return result
        except Exception as exc:
            result["reason"] = (
                exc.reason
                if isinstance(
                    exc,
                    (
                        SyntheticWriterInvocationBlocked,
                        coordinator_module.WriterRuntimeCoordinationBlocked,
                    ),
                )
                else "SYNTHETIC_CALLBACK_FAILED_CLOSED"
            )
            return result


def _validated_production_seam_bindings_v1(
    seam_bindings: Sequence[Mapping[str, Any]] | None,
) -> tuple[list[str], dict[str, dict[str, Any]]]:
    expected = coordinator_module.canonical_runtime_writer_inventory_v1()
    supplied = list(seam_bindings or ())
    if len(supplied) != 19:
        raise SyntheticWriterInvocationBlocked(
            "EXACTLY_19_PRODUCTION_SEAM_BINDINGS_REQUIRED"
        )
    writer_ids: list[str] = []
    validated: dict[str, dict[str, Any]] = {}
    for expected_writer, binding in zip(expected, supplied, strict=True):
        if not isinstance(binding, Mapping):
            raise SyntheticWriterInvocationBlocked(
                "PRODUCTION_SEAM_BINDING_INVALID"
            )
        writer = binding.get("writer")
        writer_id = str(
            writer.get("writer_id") if isinstance(writer, Mapping) else ""
        )
        if (
            not isinstance(writer, Mapping)
            or dict(writer) != expected_writer
            or binding.get("reentrancy_mode") != _REENTRANCY_MODE
            or binding.get("same_owner_token_required_for_nested_calls")
            is not True
            or binding.get("sink_token_validation_required") is not True
            or binding.get("result_contract_preserved") is not True
            or binding.get("runtime_callable_bound") is not False
            or not _SHA256_RE.fullmatch(
                str(binding.get("source_signature_sha256") or "")
            )
        ):
            raise SyntheticWriterInvocationBlocked(
                "PRODUCTION_SEAM_BINDING_INVALID"
            )
        writer_ids.append(writer_id)
        validated[writer_id] = copy.deepcopy(dict(binding))
    expected_ids = [item["writer_id"] for item in expected]
    if writer_ids != expected_ids or len(set(writer_ids)) != 19:
        raise SyntheticWriterInvocationBlocked(
            "PRODUCTION_SEAM_BINDING_ORDER_OR_ID_INVALID"
        )
    return writer_ids, validated


class ProductionWriterInvocationAdapterV1:
    """Coordinate an exact, explicitly attested set of injected invokers."""

    def __init__(
        self,
        *,
        config: ProductionWriterInvocationConfigV1 | None = None,
        coordinator: coordinator_module.ClosedRepairWriterRuntimeCoordinatorV1
        | None = None,
        seam_bindings: Sequence[Mapping[str, Any]] | None = None,
        production_callables: Sequence[ProductionWriterCallableV1] | None = None,
    ) -> None:
        self._config = config or ProductionWriterInvocationConfigV1()
        self._coordinator = coordinator
        self._bindings: dict[str, dict[str, Any]] = {}
        self._callables: dict[str, ProductionWriterCallableV1] = {}
        self._binding_scope: str | None = None
        self._manifest_sha256: str | None = None
        self._seam_bindings_sha256: str | None = None
        if not self._config.enabled:
            return
        if (
            self._config.scope_attestation
            != PRODUCTION_WRITER_CALLABLE_EXPLICIT_BINDING_ATTESTATION_V1
        ):
            raise SyntheticWriterInvocationBlocked(
                "PRODUCTION_INVOCATION_SCOPE_ATTESTATION_REQUIRED"
            )
        binding_scope = str(
            self._config.callable_binding_scope or ""
        ).upper().strip()
        manifest_sha = str(
            self._config.callable_manifest_sha256 or ""
        ).lower().strip()
        if binding_scope not in _PRODUCTION_CALLABLE_BINDING_SCOPES:
            raise SyntheticWriterInvocationBlocked(
                "PRODUCTION_INVOCATION_BINDING_SCOPE_INVALID"
            )
        if not _SHA256_RE.fullmatch(manifest_sha):
            raise SyntheticWriterInvocationBlocked(
                "PRODUCTION_CALLABLE_MANIFEST_SHA256_INVALID"
            )
        if (
            type(coordinator)
            is not coordinator_module.ClosedRepairWriterRuntimeCoordinatorV1
            or coordinator.enabled is not True
        ):
            raise SyntheticWriterInvocationBlocked(
                "ENABLED_PRODUCTION_COORDINATOR_REQUIRED"
            )
        if coordinator.all_writers_registered is not True:
            raise SyntheticWriterInvocationBlocked(
                "ALL_19_WRITERS_MUST_BE_REGISTERED"
            )
        writer_ids, validated_bindings = (
            _validated_production_seam_bindings_v1(seam_bindings)
        )
        wrappers = list(production_callables or ())
        if len(wrappers) != 19:
            raise SyntheticWriterInvocationBlocked(
                "EXACTLY_19_PRODUCTION_CALLABLES_REQUIRED"
            )
        wrapper_ids: list[str] = []
        for writer_id, wrapper in zip(writer_ids, wrappers, strict=True):
            if not isinstance(wrapper, ProductionWriterCallableV1):
                raise SyntheticWriterInvocationBlocked(
                    "UNATTESTED_PRODUCTION_CALLABLE_FORBIDDEN"
                )
            binding = validated_bindings[writer_id]
            expected_binding_sha = _stable_sha256(
                _production_callable_binding_payload_v1(wrapper)
            )
            if (
                wrapper.writer_id != writer_id
                or wrapper.binding_scope != binding_scope
                or wrapper.source_signature_sha256
                != binding["source_signature_sha256"]
                or not _SHA256_RE.fullmatch(wrapper.binding_sha256)
                or not hmac.compare_digest(
                    wrapper.binding_sha256, expected_binding_sha
                )
                or not callable(wrapper.callback)
            ):
                raise SyntheticWriterInvocationBlocked(
                    "PRODUCTION_CALLABLE_BINDING_INVALID"
                )
            wrapper_ids.append(wrapper.writer_id)
            self._callables[writer_id] = wrapper
        if wrapper_ids != writer_ids or len(set(wrapper_ids)) != 19:
            raise SyntheticWriterInvocationBlocked(
                "PRODUCTION_CALLABLE_WRITER_SET_INVALID"
            )
        expected_manifest_sha = production_writer_callable_manifest_sha256_v1(
            wrappers
        )
        if not hmac.compare_digest(manifest_sha, expected_manifest_sha):
            raise SyntheticWriterInvocationBlocked(
                "PRODUCTION_CALLABLE_MANIFEST_MISMATCH"
            )
        self._bindings = validated_bindings
        self._binding_scope = binding_scope
        self._manifest_sha256 = manifest_sha
        self._seam_bindings_sha256 = _stable_sha256(
            [validated_bindings[writer_id] for writer_id in writer_ids]
        )

    @property
    def enabled(self) -> bool:
        return bool(self._config.enabled)

    @property
    def bound_writer_count(self) -> int:
        return len(self._callables)

    def is_bound_to_coordinator(
        self,
        candidate: coordinator_module.ClosedRepairWriterRuntimeCoordinatorV1,
    ) -> bool:
        return self._coordinator is candidate

    def _base_result(self, writer_id: str) -> dict[str, Any]:
        temporary = self._binding_scope == "TEMPORARY_TEST"
        return {
            "ok": False,
            "status": "PRODUCTION_WRITER_INVOCATION_ADAPTER_V1_BLOCKED",
            "reason": None,
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_WRITER_INVOCATION_ADAPTER_V1_VERSION,
            "writer_id": writer_id,
            "default_off": not self.enabled,
            "explicit_binding_only": True,
            "callable_binding_scope": self._binding_scope,
            "callable_manifest_sha256": self._manifest_sha256,
            "seam_bindings_sha256": self._seam_bindings_sha256,
            "callable_invoked": False,
            "write_executed": False if temporary or not self.enabled else None,
            "registry_write": False if temporary or not self.enabled else None,
            "production_ready": False,
            "runtime_integrated": False,
            "real_callable_bound": self._binding_scope == "EXPLICIT_RUNTIME",
            "real_registry_accessed": False if temporary or not self.enabled else None,
            "network_accessed": False if temporary or not self.enabled else None,
            "broker_called": False if temporary or not self.enabled else None,
            "no_order_sent": True if temporary or not self.enabled else None,
        }

    def snapshot(self) -> dict[str, Any]:
        result = self._base_result("")
        result.update(
            {
                "ok": True,
                "status": (
                    "PRODUCTION_WRITER_INVOCATION_ADAPTER_V1_BOUND_NOT_RUNTIME_INTEGRATED"
                    if self.enabled
                    else "PRODUCTION_WRITER_INVOCATION_ADAPTER_V1_DEFAULT_OFF"
                ),
                "bound_writer_count": self.bound_writer_count,
            }
        )
        return result

    def invoke(
        self,
        writer_id: str,
        payload: Mapping[str, Any],
        *,
        expected_owner_token: str | None = None,
    ) -> dict[str, Any]:
        normalized_writer_id = str(writer_id or "").strip()
        result = self._base_result(normalized_writer_id)
        if not self.enabled:
            result["reason"] = "PRODUCTION_WRITER_INVOCATION_ADAPTER_DEFAULT_OFF"
            return result
        wrapper = self._callables.get(normalized_writer_id)
        binding = self._bindings.get(normalized_writer_id)
        if wrapper is None or binding is None:
            result["reason"] = "PRODUCTION_WRITER_NOT_BOUND"
            return result
        if not isinstance(payload, Mapping):
            result["reason"] = "PRODUCTION_PAYLOAD_MAPPING_REQUIRED"
            return result
        try:
            canonical_payload = json.loads(_canonical_json(dict(payload)))
        except Exception:
            result["reason"] = "PRODUCTION_PAYLOAD_NOT_CANONICALIZABLE"
            return result
        payload_sha = _stable_sha256(canonical_payload)
        try:
            with self._coordinator.mutation(normalized_writer_id) as permit:
                if (
                    permit.admitted is not True
                    or permit.coordinated is not True
                    or permit.writer_id != normalized_writer_id
                    or permit.shared_lock_acquired is not True
                    or not _SHA256_RE.fullmatch(str(permit.owner_token or ""))
                    or not isinstance(permit.depth, int)
                    or isinstance(permit.depth, bool)
                    or permit.depth < 1
                ):
                    raise SyntheticWriterInvocationBlocked(
                        "PRODUCTION_COORDINATOR_MUTATION_PERMIT_INVALID"
                    )
                if permit.reentrant:
                    if (
                        not _SHA256_RE.fullmatch(str(expected_owner_token or ""))
                        or not hmac.compare_digest(
                            str(permit.owner_token), str(expected_owner_token)
                        )
                        or permit.depth < 2
                    ):
                        raise SyntheticWriterInvocationBlocked(
                            "PRODUCTION_REENTRANT_OWNER_TOKEN_INVALID"
                        )
                elif expected_owner_token is not None:
                    raise SyntheticWriterInvocationBlocked(
                        "PRODUCTION_OUTER_OWNER_TOKEN_FORBIDDEN"
                    )
                context = ProductionWriterInvocationContextV1(
                    writer_id=normalized_writer_id,
                    depth=permit.depth,
                    reentrant=permit.reentrant,
                    shared_lock_acquired=permit.shared_lock_acquired,
                    owner_token=str(permit.owner_token),
                )
                result["callable_invoked"] = True
                callback_result = wrapper.callback(
                    copy.deepcopy(canonical_payload), context
                )
                if not isinstance(callback_result, Mapping):
                    raise SyntheticWriterInvocationBlocked(
                        "PRODUCTION_CALLBACK_RESULT_MAPPING_REQUIRED"
                    )
                canonical_callback_result = json.loads(
                    _canonical_json(dict(callback_result))
                )
                if str(permit.owner_token) in _canonical_json(
                    canonical_callback_result
                ):
                    raise SyntheticWriterInvocationBlocked(
                        "PRODUCTION_OWNER_TOKEN_DISCLOSURE_BLOCKED"
                    )
                receipt = {
                    "writer_id": normalized_writer_id,
                    "production_callable_binding_sha256": wrapper.binding_sha256,
                    "source_signature_sha256": binding[
                        "source_signature_sha256"
                    ],
                    "payload_sha256": payload_sha,
                    "result_sha256": _stable_sha256(canonical_callback_result),
                    "owner_token_sha256": _stable_sha256(
                        {"owner_token": permit.owner_token}
                    ),
                    "depth": permit.depth,
                    "reentrant": permit.reentrant,
                    "shared_lock_acquired": permit.shared_lock_acquired,
                    "callable_binding_scope": self._binding_scope,
                }
                receipt["receipt_sha256"] = _stable_sha256(receipt)
                result.update(
                    {
                        "ok": True,
                        "status": "PRODUCTION_WRITER_INVOCATION_ADMITTED",
                        "reason": None,
                        "result_payload": canonical_callback_result,
                        "invocation_receipt": receipt,
                    }
                )
                return result
        except Exception as exc:
            result["reason"] = (
                exc.reason
                if isinstance(
                    exc,
                    (
                        SyntheticWriterInvocationBlocked,
                        coordinator_module.WriterRuntimeCoordinationBlocked,
                    ),
                )
                else "PRODUCTION_CALLBACK_FAILED_CLOSED"
            )
            return result


def build_production_writer_invocation_adapter_v1(
    *,
    config: ProductionWriterInvocationConfigV1 | None = None,
    coordinator: coordinator_module.ClosedRepairWriterRuntimeCoordinatorV1
    | None = None,
    seam_bindings: Sequence[Mapping[str, Any]] | None = None,
    production_callables: Sequence[ProductionWriterCallableV1] | None = None,
) -> ProductionWriterInvocationAdapterV1:
    return ProductionWriterInvocationAdapterV1(
        config=config,
        coordinator=coordinator,
        seam_bindings=seam_bindings,
        production_callables=production_callables,
    )


__all__ = [
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_WRITER_INVOCATION_ADAPTER_V1_VERSION",
    "SYNTHETIC_WRITER_CALLABLE_SCOPE_ATTESTATION_V1",
    "PRODUCTION_WRITER_CALLABLE_EXPLICIT_BINDING_ATTESTATION_V1",
    "DormantSyntheticWriterInvocationAdapterV1",
    "ProductionWriterCallableV1",
    "ProductionWriterInvocationAdapterV1",
    "ProductionWriterInvocationConfigV1",
    "ProductionWriterInvocationContextV1",
    "SyntheticWriterCallableV1",
    "SyntheticWriterInvocationBlocked",
    "SyntheticWriterInvocationContextV1",
    "build_production_writer_callable_v1",
    "build_production_writer_invocation_adapter_v1",
    "build_synthetic_writer_callable_v1",
    "production_writer_callable_manifest_sha256_v1",
]
