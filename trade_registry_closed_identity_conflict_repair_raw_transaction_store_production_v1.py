"""Default-off production interface for a durable raw transaction store.

This module is deliberately not imported by the runtime.  It contains the
original synthetic rehearsal adapter plus a path-bound interface for an
explicitly injected durable backend.  It never discovers a Registry path.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import trade_registry_closed_identity_conflict_repair_raw_transaction_store_v1 as raw_store
import trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1 as coordinator_module


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RAW_TRANSACTION_STORE_PRODUCTION_V1_VERSION = (
    "2026-09-04-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RAW-TRANSACTION-STORE-PRODUCTION-V1"
)

SYNTHETIC_DORMANT_PRODUCTION_STORE_REHEARSAL_ATTESTATION_V1 = (
    "SYNTHETIC_DORMANT_PRODUCTION_STORE_REHEARSAL_ONLY_V1"
)
PRODUCTION_RAW_TRANSACTION_STORE_EXPLICIT_PATH_BINDING_ATTESTATION_V1 = (
    "C3_PRODUCTION_RAW_TRANSACTION_STORE_EXPLICIT_PATH_BINDING_V1"
)
_SYNTHETIC_TARGET_NAME = "synthetic_trade_registry.json"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_BACKEND_LABEL_RE = re.compile(r"^[A-Z0-9_.:-]{1,160}$")
_BACKEND_CAPABILITY_ATTESTATION_VERSION = (
    "C3_DURABLE_RAW_TRANSACTION_BACKEND_CAPABILITIES_V1"
)
_REQUIRED_BACKEND_CAPABILITIES = (
    "append_only_hash_chained_wal",
    "atomic_same_directory_replace",
    "compare_and_swap_hash_and_generation",
    "exact_raw_loader",
    "file_and_directory_fsync",
    "idempotency_key_enforcement",
    "immutable_content_addressed_backup",
    "interrupted_transaction_recovery",
    "rollback_to_exact_preimage",
)
_STORAGE_SCOPES = frozenset({"TEMPORARY_TEST", "EXPLICIT_PRODUCTION"})


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


def _normalized_root_text(storage_root: str | os.PathLike[str]) -> str:
    root = Path(storage_root).resolve(strict=False)
    if root == Path(root.anchor):
        raise ValueError("storage_root cannot be a filesystem root")
    return os.path.normcase(str(root))


def synthetic_storage_root_binding_sha256_v1(
    storage_root: str | os.PathLike[str],
) -> str:
    """Bind one synthetic rehearsal root without exposing it in receipts."""

    return _stable_sha256(
        {
            "scope_attestation": (
                SYNTHETIC_DORMANT_PRODUCTION_STORE_REHEARSAL_ATTESTATION_V1
            ),
            "storage_root": _normalized_root_text(storage_root),
            "target_name": _SYNTHETIC_TARGET_NAME,
            "backend_version": (
                raw_store.TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RAW_TRANSACTION_STORE_V1_VERSION
            ),
        }
    )


def _normalized_registry_path(
    registry_path: str | os.PathLike[str],
) -> Path:
    target = Path(registry_path).resolve(strict=False)
    if target == Path(target.anchor) or not target.name:
        raise ValueError("registry_path must identify one file")
    return target


def production_registry_path_binding_sha256_v1(
    registry_path: str | os.PathLike[str],
) -> str:
    """Bind one explicitly supplied Registry path without exposing it."""

    target = _normalized_registry_path(registry_path)
    return _stable_sha256(
        {
            "binding_version": "C3_PRODUCTION_RAW_REGISTRY_PATH_BINDING_V1",
            "registry_path": os.path.normcase(str(target)),
            "interface_version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RAW_TRANSACTION_STORE_PRODUCTION_V1_VERSION,
        }
    )


def production_backend_capability_attestation_sha256_v1(
    attestation: Mapping[str, Any],
) -> str:
    if not isinstance(attestation, Mapping):
        raise TypeError("attestation must be a mapping")
    return _stable_sha256(
        {
            key: value
            for key, value in attestation.items()
            if key != "attestation_sha256"
        }
    )


def build_production_backend_capability_attestation_v1(
    registry_path: str | os.PathLike[str],
    *,
    backend_kind: str,
    storage_scope: str,
) -> dict[str, Any]:
    normalized_kind = str(backend_kind or "").upper().strip()
    normalized_scope = str(storage_scope or "").upper().strip()
    if not _BACKEND_LABEL_RE.fullmatch(normalized_kind):
        raise ValueError("backend_kind invalid")
    if normalized_scope not in _STORAGE_SCOPES:
        raise ValueError("storage_scope invalid")
    attestation = {
        "attestation_version": _BACKEND_CAPABILITY_ATTESTATION_VERSION,
        "backend_kind": normalized_kind,
        "storage_scope": normalized_scope,
        "registry_path_binding_sha256": production_registry_path_binding_sha256_v1(
            registry_path
        ),
        "lock_namespace_sha256": (
            coordinator_module.canonical_runtime_lock_namespace_v1()
        ),
        "capabilities": {
            capability: True for capability in _REQUIRED_BACKEND_CAPABILITIES
        },
    }
    attestation["attestation_sha256"] = (
        production_backend_capability_attestation_sha256_v1(attestation)
    )
    return attestation


class ProductionRawTransactionStoreBlocked(RuntimeError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class ProductionRawTransactionStoreConfigV1:
    enabled: bool = False
    scope_attestation: str | None = None
    storage_root_binding_sha256: str | None = None


@dataclass(frozen=True)
class ProductionRawTransactionStoreRuntimeConfigV1:
    enabled: bool = False
    scope_attestation: str | None = None
    registry_path_binding_sha256: str | None = None


class DurableRawTransactionBackendV1(Protocol):
    @property
    def enabled(self) -> bool: ...

    @property
    def storage_root(self) -> Path: ...

    @property
    def target_path(self) -> Path: ...

    @property
    def lock_namespace_sha256(self) -> str: ...

    def load_exact_raw_registry(self) -> Any: ...

    def apply_attested_transaction(
        self,
        request: Mapping[str, Any],
        maintenance_attestation: Mapping[str, Any],
    ) -> Mapping[str, Any]: ...

    def reconcile_attested_transaction(
        self,
        transaction_sha256: str,
        maintenance_attestation: Mapping[str, Any],
    ) -> Mapping[str, Any]: ...


class DormantProductionRawTransactionStoreV1:
    """Gate a durable backend for synthetic rehearsal; production stays denied."""

    def __init__(
        self,
        *,
        config: ProductionRawTransactionStoreConfigV1 | None = None,
        storage_root: str | os.PathLike[str] | None = None,
        backend: raw_store.IsolatedRawRegistryTransactionStoreV1 | None = None,
    ) -> None:
        self._config = config or ProductionRawTransactionStoreConfigV1()
        self._backend = backend
        self._storage_root_binding_sha256: str | None = None
        if not self._config.enabled:
            return
        if (
            self._config.scope_attestation
            != SYNTHETIC_DORMANT_PRODUCTION_STORE_REHEARSAL_ATTESTATION_V1
        ):
            raise ProductionRawTransactionStoreBlocked(
                "PRODUCTION_STORE_SYNTHETIC_REHEARSAL_SCOPE_REQUIRED"
            )
        supplied_binding = str(
            self._config.storage_root_binding_sha256 or ""
        ).lower().strip()
        if not _SHA256_RE.fullmatch(supplied_binding):
            raise ProductionRawTransactionStoreBlocked(
                "PRODUCTION_STORE_ROOT_BINDING_INVALID"
            )
        if storage_root is None:
            raise ProductionRawTransactionStoreBlocked(
                "PRODUCTION_STORE_ROOT_REQUIRED"
            )
        try:
            normalized_root = Path(_normalized_root_text(storage_root))
            expected_binding = synthetic_storage_root_binding_sha256_v1(
                normalized_root
            )
        except Exception:
            raise ProductionRawTransactionStoreBlocked(
                "PRODUCTION_STORE_ROOT_INVALID"
            ) from None
        if not hmac.compare_digest(supplied_binding, expected_binding):
            raise ProductionRawTransactionStoreBlocked(
                "PRODUCTION_STORE_ROOT_BINDING_MISMATCH"
            )
        if not isinstance(
            backend, raw_store.IsolatedRawRegistryTransactionStoreV1
        ):
            raise ProductionRawTransactionStoreBlocked(
                "PRODUCTION_STORE_SYNTHETIC_BACKEND_REQUIRED"
            )
        if (
            backend.enabled is not True
            or backend.storage_root != normalized_root
            or backend.target_path.parent != normalized_root
            or backend.target_path.name != _SYNTHETIC_TARGET_NAME
        ):
            raise ProductionRawTransactionStoreBlocked(
                "PRODUCTION_STORE_BACKEND_BINDING_MISMATCH"
            )
        self._storage_root_binding_sha256 = supplied_binding

    @property
    def enabled(self) -> bool:
        return bool(self._config.enabled)

    def _base_result(self) -> dict[str, Any]:
        return {
            "ok": False,
            "status": "DORMANT_PRODUCTION_RAW_TRANSACTION_STORE_V1_BLOCKED",
            "reason": None,
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RAW_TRANSACTION_STORE_PRODUCTION_V1_VERSION,
            "dormant": True,
            "default_off": not self.enabled,
            "offline_only": True,
            "synthetic_only": True,
            "temporary_storage_only": True,
            "production_ready": False,
            "production_apply_allowed": False,
            "runtime_integrated": False,
            "real_registry_accessed": False,
            "network_accessed": False,
            "write_executed": False,
            "registry_write": False,
            "rollback_attempted": False,
            "rollback_confirmed": False,
            "idempotent_replay": False,
            "broker_called": False,
            "no_order_sent": True,
            "storage_root_binding_sha256": self._storage_root_binding_sha256,
        }

    def snapshot(self) -> dict[str, Any]:
        result = self._base_result()
        result.update(
            {
                "ok": True,
                "status": (
                    "DORMANT_PRODUCTION_RAW_TRANSACTION_STORE_V1_SYNTHETIC_REHEARSAL_BOUND"
                    if self.enabled
                    else "DORMANT_PRODUCTION_RAW_TRANSACTION_STORE_V1_DEFAULT_OFF"
                ),
            }
        )
        return result

    def _require_synthetic_backend(
        self,
    ) -> raw_store.IsolatedRawRegistryTransactionStoreV1:
        if not self.enabled:
            raise ProductionRawTransactionStoreBlocked(
                "PRODUCTION_RAW_TRANSACTION_STORE_DEFAULT_OFF"
            )
        if self._backend is None or self._storage_root_binding_sha256 is None:
            raise ProductionRawTransactionStoreBlocked(
                "PRODUCTION_STORE_BACKEND_NOT_BOUND"
            )
        return self._backend

    def load_exact_raw_registry_offline(
        self,
    ) -> raw_store.ExactRawRegistrySnapshotV1:
        return self._require_synthetic_backend().load_exact_raw_registry()

    def apply_attested_transaction_offline(
        self,
        request: Mapping[str, Any],
        maintenance_attestation: Mapping[str, Any],
    ) -> dict[str, Any]:
        result = self._base_result()
        if not self.enabled:
            result["reason"] = "PRODUCTION_RAW_TRANSACTION_STORE_DEFAULT_OFF"
            return result
        try:
            delegated = self._require_synthetic_backend().apply_synthetic_transaction(
                request, maintenance_attestation
            )
        except Exception:
            result["reason"] = "PRODUCTION_STORE_DELEGATE_FAILED_CLOSED"
            return result
        result.update(dict(delegated))
        result.update(
            {
                "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RAW_TRANSACTION_STORE_PRODUCTION_V1_VERSION,
                "dormant": True,
                "default_off": False,
                "offline_only": True,
                "synthetic_only": True,
                "temporary_storage_only": True,
                "production_ready": False,
                "production_apply_allowed": False,
                "runtime_integrated": False,
                "real_registry_accessed": False,
                "network_accessed": False,
                "broker_called": False,
                "no_order_sent": True,
                "storage_root_binding_sha256": self._storage_root_binding_sha256,
            }
        )
        return result

    def reconcile_attested_transaction_offline(
        self,
        transaction_sha256: str,
        maintenance_attestation: Mapping[str, Any],
    ) -> dict[str, Any]:
        result = self._base_result()
        if not self.enabled:
            result["reason"] = "PRODUCTION_RAW_TRANSACTION_STORE_DEFAULT_OFF"
            return result
        try:
            delegated = self._require_synthetic_backend().reconcile_synthetic_prepared_transaction(
                transaction_sha256, maintenance_attestation
            )
        except Exception:
            result["reason"] = "PRODUCTION_STORE_RECOVERY_DELEGATE_FAILED_CLOSED"
            return result
        result.update(dict(delegated))
        result.update(
            {
                "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RAW_TRANSACTION_STORE_PRODUCTION_V1_VERSION,
                "dormant": True,
                "default_off": False,
                "offline_only": True,
                "synthetic_only": True,
                "temporary_storage_only": True,
                "production_ready": False,
                "production_apply_allowed": False,
                "runtime_integrated": False,
                "real_registry_accessed": False,
                "network_accessed": False,
                "broker_called": False,
                "no_order_sent": True,
                "storage_root_binding_sha256": self._storage_root_binding_sha256,
            }
        )
        return result


def build_dormant_production_raw_transaction_store_v1(
    *,
    config: ProductionRawTransactionStoreConfigV1 | None = None,
    storage_root: str | os.PathLike[str] | None = None,
    backend: raw_store.IsolatedRawRegistryTransactionStoreV1 | None = None,
) -> DormantProductionRawTransactionStoreV1:
    return DormantProductionRawTransactionStoreV1(
        config=config,
        storage_root=storage_root,
        backend=backend,
    )


class ProductionRawTransactionStoreV1:
    """Path-bound gate for an injected durable transaction backend."""

    def __init__(
        self,
        *,
        config: ProductionRawTransactionStoreRuntimeConfigV1 | None = None,
        registry_path: str | os.PathLike[str] | None = None,
        backend: DurableRawTransactionBackendV1 | None = None,
        backend_capability_attestation: Mapping[str, Any] | None = None,
    ) -> None:
        self._config = config or ProductionRawTransactionStoreRuntimeConfigV1()
        self._backend = backend
        self._registry_path_binding_sha256: str | None = None
        self._backend_attestation_sha256: str | None = None
        self._storage_scope: str | None = None
        self._lock_namespace_sha256: str | None = None
        if not self._config.enabled:
            return
        if (
            self._config.scope_attestation
            != PRODUCTION_RAW_TRANSACTION_STORE_EXPLICIT_PATH_BINDING_ATTESTATION_V1
        ):
            raise ProductionRawTransactionStoreBlocked(
                "PRODUCTION_RAW_STORE_SCOPE_ATTESTATION_REQUIRED"
            )
        supplied_path_sha = str(
            self._config.registry_path_binding_sha256 or ""
        ).lower().strip()
        if not _SHA256_RE.fullmatch(supplied_path_sha):
            raise ProductionRawTransactionStoreBlocked(
                "PRODUCTION_RAW_STORE_PATH_BINDING_INVALID"
            )
        if registry_path is None:
            raise ProductionRawTransactionStoreBlocked(
                "PRODUCTION_RAW_STORE_PATH_REQUIRED"
            )
        try:
            target = _normalized_registry_path(registry_path)
            expected_path_sha = production_registry_path_binding_sha256_v1(
                target
            )
        except Exception:
            raise ProductionRawTransactionStoreBlocked(
                "PRODUCTION_RAW_STORE_PATH_INVALID"
            ) from None
        if not hmac.compare_digest(supplied_path_sha, expected_path_sha):
            raise ProductionRawTransactionStoreBlocked(
                "PRODUCTION_RAW_STORE_PATH_BINDING_MISMATCH"
            )
        if backend is None:
            raise ProductionRawTransactionStoreBlocked(
                "PRODUCTION_RAW_STORE_BACKEND_REQUIRED"
            )
        required_members = (
            "load_exact_raw_registry",
            "apply_attested_transaction",
            "reconcile_attested_transaction",
        )
        if any(not callable(getattr(backend, name, None)) for name in required_members):
            raise ProductionRawTransactionStoreBlocked(
                "PRODUCTION_RAW_STORE_BACKEND_INTERFACE_INVALID"
            )
        try:
            backend_enabled = backend.enabled is True
            backend_target = _normalized_registry_path(backend.target_path)
            backend_root = Path(backend.storage_root).resolve(strict=False)
            backend_lock_namespace = str(
                backend.lock_namespace_sha256 or ""
            ).lower().strip()
        except Exception:
            raise ProductionRawTransactionStoreBlocked(
                "PRODUCTION_RAW_STORE_BACKEND_BINDING_INVALID"
            ) from None
        if (
            not backend_enabled
            or backend_target != target
            or backend_root != target.parent
            or not hmac.compare_digest(
                backend_lock_namespace,
                coordinator_module.canonical_runtime_lock_namespace_v1(),
            )
        ):
            raise ProductionRawTransactionStoreBlocked(
                "PRODUCTION_RAW_STORE_BACKEND_BINDING_INVALID"
            )
        if not isinstance(backend_capability_attestation, Mapping):
            raise ProductionRawTransactionStoreBlocked(
                "PRODUCTION_RAW_STORE_CAPABILITY_ATTESTATION_REQUIRED"
            )
        try:
            attestation = json.loads(
                _canonical_json(dict(backend_capability_attestation))
            )
            supplied_attestation_sha = str(
                attestation.get("attestation_sha256") or ""
            ).lower().strip()
            expected_attestation_sha = (
                production_backend_capability_attestation_sha256_v1(attestation)
            )
        except Exception:
            raise ProductionRawTransactionStoreBlocked(
                "PRODUCTION_RAW_STORE_CAPABILITY_ATTESTATION_INVALID"
            ) from None
        capabilities = attestation.get("capabilities")
        storage_scope = str(attestation.get("storage_scope") or "").upper().strip()
        if (
            attestation.get("attestation_version")
            != _BACKEND_CAPABILITY_ATTESTATION_VERSION
            or not _BACKEND_LABEL_RE.fullmatch(
                str(attestation.get("backend_kind") or "")
            )
            or storage_scope not in _STORAGE_SCOPES
            or attestation.get("registry_path_binding_sha256")
            != supplied_path_sha
            or attestation.get("lock_namespace_sha256")
            != backend_lock_namespace
            or not isinstance(capabilities, Mapping)
            or tuple(sorted(capabilities))
            != tuple(sorted(_REQUIRED_BACKEND_CAPABILITIES))
            or not all(
                capabilities.get(capability) is True
                for capability in _REQUIRED_BACKEND_CAPABILITIES
            )
            or not _SHA256_RE.fullmatch(supplied_attestation_sha)
            or not hmac.compare_digest(
                supplied_attestation_sha, expected_attestation_sha
            )
        ):
            raise ProductionRawTransactionStoreBlocked(
                "PRODUCTION_RAW_STORE_CAPABILITY_ATTESTATION_INVALID"
            )
        self._registry_path_binding_sha256 = supplied_path_sha
        self._backend_attestation_sha256 = supplied_attestation_sha
        self._storage_scope = storage_scope
        self._lock_namespace_sha256 = backend_lock_namespace

    @property
    def enabled(self) -> bool:
        return bool(self._config.enabled)

    def _base_result(self) -> dict[str, Any]:
        return {
            "ok": False,
            "status": "PRODUCTION_RAW_TRANSACTION_STORE_V1_BLOCKED",
            "reason": None,
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RAW_TRANSACTION_STORE_PRODUCTION_V1_VERSION,
            "default_off": not self.enabled,
            "production_interface_bound": self._backend_attestation_sha256
            is not None,
            "production_ready": False,
            "runtime_integrated": False,
            "real_registry_accessed": False,
            "network_accessed": False,
            "write_executed": False,
            "registry_write": False,
            "rollback_attempted": False,
            "rollback_confirmed": False,
            "idempotent_replay": False,
            "broker_called": False,
            "no_order_sent": True,
            "storage_scope": self._storage_scope,
            "lock_namespace_sha256": self._lock_namespace_sha256,
            "registry_path_binding_sha256": self._registry_path_binding_sha256,
            "backend_capability_attestation_sha256": self._backend_attestation_sha256,
        }

    def snapshot(self) -> dict[str, Any]:
        result = self._base_result()
        result.update(
            {
                "ok": True,
                "status": (
                    "PRODUCTION_RAW_TRANSACTION_STORE_V1_PATH_BOUND_NOT_RUNTIME_INTEGRATED"
                    if self.enabled
                    else "PRODUCTION_RAW_TRANSACTION_STORE_V1_DEFAULT_OFF"
                ),
            }
        )
        return result

    def _bound_backend(self) -> DurableRawTransactionBackendV1:
        if not self.enabled:
            raise ProductionRawTransactionStoreBlocked(
                "PRODUCTION_RAW_TRANSACTION_STORE_DEFAULT_OFF"
            )
        if self._backend is None or self._backend_attestation_sha256 is None:
            raise ProductionRawTransactionStoreBlocked(
                "PRODUCTION_RAW_STORE_BACKEND_NOT_BOUND"
            )
        return self._backend

    def load_exact_raw_registry(self) -> Any:
        return self._bound_backend().load_exact_raw_registry()

    def _delegated_result(
        self,
        delegated: Mapping[str, Any],
    ) -> dict[str, Any]:
        result = self._base_result()
        result.update(dict(delegated))
        result.update(
            {
                "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RAW_TRANSACTION_STORE_PRODUCTION_V1_VERSION,
                "default_off": False,
                "production_interface_bound": True,
                "production_ready": False,
                "runtime_integrated": False,
                "network_accessed": False,
                "broker_called": False,
                "no_order_sent": True,
                "storage_scope": self._storage_scope,
                "registry_path_binding_sha256": self._registry_path_binding_sha256,
                "backend_capability_attestation_sha256": self._backend_attestation_sha256,
            }
        )
        return result

    def apply_attested_transaction(
        self,
        request: Mapping[str, Any],
        maintenance_attestation: Mapping[str, Any],
    ) -> dict[str, Any]:
        result = self._base_result()
        if not self.enabled:
            result["reason"] = "PRODUCTION_RAW_TRANSACTION_STORE_DEFAULT_OFF"
            return result
        if not isinstance(request, Mapping) or not isinstance(
            maintenance_attestation, Mapping
        ):
            result["reason"] = "PRODUCTION_RAW_STORE_MAPPING_INPUTS_REQUIRED"
            return result
        try:
            delegated = self._bound_backend().apply_attested_transaction(
                request, maintenance_attestation
            )
        except Exception:
            result["reason"] = "PRODUCTION_RAW_STORE_DELEGATE_FAILED_CLOSED"
            return result
        if not isinstance(delegated, Mapping):
            result["reason"] = "PRODUCTION_RAW_STORE_DELEGATE_RESULT_INVALID"
            return result
        return self._delegated_result(delegated)

    def reconcile_attested_transaction(
        self,
        transaction_sha256: str,
        maintenance_attestation: Mapping[str, Any],
    ) -> dict[str, Any]:
        result = self._base_result()
        if not self.enabled:
            result["reason"] = "PRODUCTION_RAW_TRANSACTION_STORE_DEFAULT_OFF"
            return result
        if not _SHA256_RE.fullmatch(str(transaction_sha256 or "").lower().strip()):
            result["reason"] = "PRODUCTION_RAW_STORE_TRANSACTION_SHA_INVALID"
            return result
        if not isinstance(maintenance_attestation, Mapping):
            result["reason"] = "PRODUCTION_RAW_STORE_MAPPING_INPUTS_REQUIRED"
            return result
        try:
            delegated = self._bound_backend().reconcile_attested_transaction(
                transaction_sha256, maintenance_attestation
            )
        except Exception:
            result["reason"] = "PRODUCTION_RAW_STORE_RECOVERY_DELEGATE_FAILED_CLOSED"
            return result
        if not isinstance(delegated, Mapping):
            result["reason"] = "PRODUCTION_RAW_STORE_DELEGATE_RESULT_INVALID"
            return result
        return self._delegated_result(delegated)


def build_production_raw_transaction_store_v1(
    *,
    config: ProductionRawTransactionStoreRuntimeConfigV1 | None = None,
    registry_path: str | os.PathLike[str] | None = None,
    backend: DurableRawTransactionBackendV1 | None = None,
    backend_capability_attestation: Mapping[str, Any] | None = None,
) -> ProductionRawTransactionStoreV1:
    return ProductionRawTransactionStoreV1(
        config=config,
        registry_path=registry_path,
        backend=backend,
        backend_capability_attestation=backend_capability_attestation,
    )


__all__ = [
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RAW_TRANSACTION_STORE_PRODUCTION_V1_VERSION",
    "SYNTHETIC_DORMANT_PRODUCTION_STORE_REHEARSAL_ATTESTATION_V1",
    "PRODUCTION_RAW_TRANSACTION_STORE_EXPLICIT_PATH_BINDING_ATTESTATION_V1",
    "DurableRawTransactionBackendV1",
    "DormantProductionRawTransactionStoreV1",
    "ProductionRawTransactionStoreV1",
    "ProductionRawTransactionStoreBlocked",
    "ProductionRawTransactionStoreConfigV1",
    "ProductionRawTransactionStoreRuntimeConfigV1",
    "build_production_backend_capability_attestation_v1",
    "build_dormant_production_raw_transaction_store_v1",
    "build_production_raw_transaction_store_v1",
    "production_backend_capability_attestation_sha256_v1",
    "production_registry_path_binding_sha256_v1",
    "synthetic_storage_root_binding_sha256_v1",
]
