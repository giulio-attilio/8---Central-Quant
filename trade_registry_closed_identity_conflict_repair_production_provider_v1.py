"""Default-off provider for the three production-shaped CLOSED-repair interfaces.

The provider composes only explicitly injected objects.  It performs no path
discovery, runtime installation, environment lookup or external I/O by itself.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import trade_registry_closed_identity_conflict_repair_raw_transaction_store_production_v1 as production_store
import trade_registry_closed_identity_conflict_repair_writer_invocation_adapter_v1 as invocation
import trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1 as coordinator_module


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_PRODUCTION_PROVIDER_V1_VERSION = (
    "2026-09-04-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-PRODUCTION-PROVIDER-V1"
)

PRODUCTION_CLOSED_REPAIR_PROVIDER_EXPLICIT_COMPOSITION_ATTESTATION_V1 = (
    "C3_PRODUCTION_CLOSED_REPAIR_PROVIDER_EXPLICIT_COMPOSITION_V1"
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_BINDING_SCOPES = frozenset({"TEMPORARY_TEST", "EXPLICIT_RUNTIME"})


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


class ProductionClosedRepairProviderBlocked(RuntimeError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class ProductionClosedRepairProviderConfigV1:
    enabled: bool = False
    scope_attestation: str | None = None
    binding_scope: str | None = None
    composition_attestation_sha256: str | None = None


def production_closed_repair_provider_attestation_sha256_v1(
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


def build_production_closed_repair_provider_attestation_v1(
    *,
    coordinator: coordinator_module.ClosedRepairWriterRuntimeCoordinatorV1,
    transaction_store: production_store.ProductionRawTransactionStoreV1,
    invocation_adapter: invocation.ProductionWriterInvocationAdapterV1,
    seam_bindings: Sequence[Mapping[str, Any]],
    binding_scope: str,
) -> dict[str, Any]:
    normalized_scope = str(binding_scope or "").upper().strip()
    if normalized_scope not in _BINDING_SCOPES:
        raise ProductionClosedRepairProviderBlocked(
            "PROVIDER_BINDING_SCOPE_INVALID"
        )
    if (
        type(coordinator)
        is not coordinator_module.ClosedRepairWriterRuntimeCoordinatorV1
        or type(transaction_store)
        is not production_store.ProductionRawTransactionStoreV1
        or type(invocation_adapter)
        is not invocation.ProductionWriterInvocationAdapterV1
    ):
        raise ProductionClosedRepairProviderBlocked(
            "PROVIDER_COMPONENT_TYPE_INVALID"
        )
    try:
        coordinator_snapshot = coordinator.snapshot()
        store_snapshot = transaction_store.snapshot()
        invocation_snapshot = invocation_adapter.snapshot()
    except Exception:
        raise ProductionClosedRepairProviderBlocked(
            "PROVIDER_COMPONENT_SNAPSHOT_FAILED"
        ) from None
    expected_ids = [
        item["writer_id"]
        for item in coordinator_module.canonical_runtime_writer_inventory_v1()
    ]
    supplied_bindings = list(seam_bindings or ())
    supplied_ids = [
        str(item.get("writer", {}).get("writer_id") or "")
        if isinstance(item, Mapping)
        else ""
        for item in supplied_bindings
    ]
    seam_binding_sha256 = _stable_sha256(supplied_bindings)
    expected_store_scope = (
        "TEMPORARY_TEST"
        if normalized_scope == "TEMPORARY_TEST"
        else "EXPLICIT_PRODUCTION"
    )
    expected_invocation_scope = (
        "TEMPORARY_TEST"
        if normalized_scope == "TEMPORARY_TEST"
        else "EXPLICIT_RUNTIME"
    )
    valid = bool(
        coordinator.enabled is True
        and coordinator_snapshot.get("all_writers_registered") is True
        and coordinator_snapshot.get("registered_writer_count") == 19
        and _SHA256_RE.fullmatch(
            str(coordinator_snapshot.get("lock_namespace_sha256") or "")
        )
        and transaction_store.enabled is True
        and store_snapshot.get("production_interface_bound") is True
        and store_snapshot.get("storage_scope") == expected_store_scope
        and store_snapshot.get("lock_namespace_sha256")
        == coordinator_snapshot.get("lock_namespace_sha256")
        and _SHA256_RE.fullmatch(
            str(store_snapshot.get("registry_path_binding_sha256") or "")
        )
        and _SHA256_RE.fullmatch(
            str(
                store_snapshot.get(
                    "backend_capability_attestation_sha256"
                )
                or ""
            )
        )
        and invocation_adapter.enabled is True
        and invocation_adapter.bound_writer_count == 19
        and invocation_adapter.is_bound_to_coordinator(coordinator)
        and invocation_snapshot.get("callable_binding_scope")
        == expected_invocation_scope
        and _SHA256_RE.fullmatch(
            str(invocation_snapshot.get("callable_manifest_sha256") or "")
        )
        and invocation_snapshot.get("seam_bindings_sha256")
        == seam_binding_sha256
        and supplied_ids == expected_ids
        and len(set(supplied_ids)) == 19
        and all(
            isinstance(item, Mapping)
            and _SHA256_RE.fullmatch(
                str(item.get("source_signature_sha256") or "")
            )
            for item in supplied_bindings
        )
        and coordinator_snapshot.get("production_ready") is not True
        and store_snapshot.get("production_ready") is False
        and invocation_snapshot.get("production_ready") is False
        and coordinator_snapshot.get("runtime_integrated") is False
        and store_snapshot.get("runtime_integrated") is False
        and invocation_snapshot.get("runtime_integrated") is False
    )
    if not valid:
        raise ProductionClosedRepairProviderBlocked(
            "PROVIDER_COMPONENT_BINDING_INVALID"
        )
    attestation = {
        "attestation_version": (
            PRODUCTION_CLOSED_REPAIR_PROVIDER_EXPLICIT_COMPOSITION_ATTESTATION_V1
        ),
        "binding_scope": normalized_scope,
        "same_coordinator_for_writer_invocation": True,
        "coordinator": {
            "version": coordinator_snapshot["version"],
            "lock_namespace_sha256": coordinator_snapshot[
                "lock_namespace_sha256"
            ],
            "registered_writer_count": 19,
        },
        "transaction_store": {
            "version": store_snapshot["version"],
            "storage_scope": store_snapshot["storage_scope"],
            "lock_namespace_sha256": store_snapshot[
                "lock_namespace_sha256"
            ],
            "registry_path_binding_sha256": store_snapshot[
                "registry_path_binding_sha256"
            ],
            "backend_capability_attestation_sha256": store_snapshot[
                "backend_capability_attestation_sha256"
            ],
        },
        "invocation_adapter": {
            "version": invocation_snapshot["version"],
            "callable_binding_scope": invocation_snapshot[
                "callable_binding_scope"
            ],
            "callable_manifest_sha256": invocation_snapshot[
                "callable_manifest_sha256"
            ],
            "seam_bindings_sha256": invocation_snapshot[
                "seam_bindings_sha256"
            ],
            "bound_writer_count": 19,
        },
        "seam_binding_sha256": seam_binding_sha256,
        "writer_inventory_sha256": _stable_sha256(expected_ids),
        "production_ready": False,
        "runtime_integrated": False,
    }
    attestation["attestation_sha256"] = (
        production_closed_repair_provider_attestation_sha256_v1(attestation)
    )
    return attestation


class ProductionClosedRepairProviderV1:
    """Hold one verified component graph without installing it anywhere."""

    def __init__(
        self,
        *,
        config: ProductionClosedRepairProviderConfigV1 | None = None,
        coordinator: coordinator_module.ClosedRepairWriterRuntimeCoordinatorV1
        | None = None,
        transaction_store: production_store.ProductionRawTransactionStoreV1
        | None = None,
        invocation_adapter: invocation.ProductionWriterInvocationAdapterV1
        | None = None,
        seam_bindings: Sequence[Mapping[str, Any]] | None = None,
        composition_attestation: Mapping[str, Any] | None = None,
    ) -> None:
        self._config = config or ProductionClosedRepairProviderConfigV1()
        self._coordinator = coordinator
        self._transaction_store = transaction_store
        self._invocation_adapter = invocation_adapter
        self._attestation_sha256: str | None = None
        self._binding_scope: str | None = None
        if not self._config.enabled:
            return
        if (
            self._config.scope_attestation
            != PRODUCTION_CLOSED_REPAIR_PROVIDER_EXPLICIT_COMPOSITION_ATTESTATION_V1
        ):
            raise ProductionClosedRepairProviderBlocked(
                "PROVIDER_SCOPE_ATTESTATION_REQUIRED"
            )
        binding_scope = str(self._config.binding_scope or "").upper().strip()
        supplied_sha = str(
            self._config.composition_attestation_sha256 or ""
        ).lower().strip()
        if binding_scope not in _BINDING_SCOPES:
            raise ProductionClosedRepairProviderBlocked(
                "PROVIDER_BINDING_SCOPE_INVALID"
            )
        if not _SHA256_RE.fullmatch(supplied_sha):
            raise ProductionClosedRepairProviderBlocked(
                "PROVIDER_ATTESTATION_SHA256_INVALID"
            )
        if not isinstance(composition_attestation, Mapping):
            raise ProductionClosedRepairProviderBlocked(
                "PROVIDER_COMPOSITION_ATTESTATION_REQUIRED"
            )
        expected_attestation = build_production_closed_repair_provider_attestation_v1(
            coordinator=coordinator,
            transaction_store=transaction_store,
            invocation_adapter=invocation_adapter,
            seam_bindings=seam_bindings,
            binding_scope=binding_scope,
        )
        try:
            supplied_attestation = json.loads(
                _canonical_json(dict(composition_attestation))
            )
        except Exception:
            raise ProductionClosedRepairProviderBlocked(
                "PROVIDER_COMPOSITION_ATTESTATION_INVALID"
            ) from None
        actual_sha = str(
            supplied_attestation.get("attestation_sha256") or ""
        ).lower().strip()
        recomputed_sha = (
            production_closed_repair_provider_attestation_sha256_v1(
                supplied_attestation
            )
        )
        if (
            supplied_attestation != expected_attestation
            or not _SHA256_RE.fullmatch(actual_sha)
            or not hmac.compare_digest(actual_sha, recomputed_sha)
            or not hmac.compare_digest(supplied_sha, actual_sha)
        ):
            raise ProductionClosedRepairProviderBlocked(
                "PROVIDER_COMPOSITION_ATTESTATION_INVALID"
            )
        self._attestation_sha256 = actual_sha
        self._binding_scope = binding_scope

    @property
    def enabled(self) -> bool:
        return bool(self._config.enabled)

    @property
    def coordinator(self) -> coordinator_module.ClosedRepairWriterRuntimeCoordinatorV1:
        if not self.enabled or self._coordinator is None:
            raise ProductionClosedRepairProviderBlocked("PROVIDER_DEFAULT_OFF")
        return self._coordinator

    def _base_result(self) -> dict[str, Any]:
        temporary = self._binding_scope == "TEMPORARY_TEST"
        return {
            "ok": False,
            "status": "PRODUCTION_CLOSED_REPAIR_PROVIDER_V1_BLOCKED",
            "reason": None,
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_PRODUCTION_PROVIDER_V1_VERSION,
            "default_off": not self.enabled,
            "binding_scope": self._binding_scope,
            "composition_attestation_sha256": self._attestation_sha256,
            "components_bound": self._attestation_sha256 is not None,
            "production_ready": False,
            "runtime_integrated": False,
            "real_registry_accessed": False if temporary or not self.enabled else None,
            "network_accessed": False if temporary or not self.enabled else None,
            "broker_called": False if temporary or not self.enabled else None,
            "no_order_sent": True if temporary or not self.enabled else None,
            "write_executed": False if temporary or not self.enabled else None,
            "registry_write": False if temporary or not self.enabled else None,
        }

    def snapshot(self) -> dict[str, Any]:
        result = self._base_result()
        result.update(
            {
                "ok": True,
                "status": (
                    "PRODUCTION_CLOSED_REPAIR_PROVIDER_V1_BOUND_NOT_RUNTIME_INTEGRATED"
                    if self.enabled
                    else "PRODUCTION_CLOSED_REPAIR_PROVIDER_V1_DEFAULT_OFF"
                ),
                "writer_count": (
                    self._invocation_adapter.bound_writer_count
                    if self.enabled and self._invocation_adapter is not None
                    else 0
                ),
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
        if not self.enabled or self._invocation_adapter is None:
            result = self._base_result()
            result["reason"] = "PROVIDER_DEFAULT_OFF"
            return result
        return self._invocation_adapter.invoke(
            writer_id,
            payload,
            expected_owner_token=expected_owner_token,
        )

    def load_exact_raw_registry(self) -> Any:
        if not self.enabled or self._transaction_store is None:
            raise ProductionClosedRepairProviderBlocked("PROVIDER_DEFAULT_OFF")
        return self._transaction_store.load_exact_raw_registry()

    def apply_attested_transaction(
        self,
        request: Mapping[str, Any],
        maintenance_attestation: Mapping[str, Any],
    ) -> dict[str, Any]:
        if not self.enabled or self._transaction_store is None:
            result = self._base_result()
            result["reason"] = "PROVIDER_DEFAULT_OFF"
            return result
        return self._transaction_store.apply_attested_transaction(
            request, maintenance_attestation
        )

    def reconcile_attested_transaction(
        self,
        transaction_sha256: str,
        maintenance_attestation: Mapping[str, Any],
    ) -> dict[str, Any]:
        if not self.enabled or self._transaction_store is None:
            result = self._base_result()
            result["reason"] = "PROVIDER_DEFAULT_OFF"
            return result
        return self._transaction_store.reconcile_attested_transaction(
            transaction_sha256, maintenance_attestation
        )


def build_production_closed_repair_provider_v1(
    *,
    config: ProductionClosedRepairProviderConfigV1 | None = None,
    coordinator: coordinator_module.ClosedRepairWriterRuntimeCoordinatorV1
    | None = None,
    transaction_store: production_store.ProductionRawTransactionStoreV1
    | None = None,
    invocation_adapter: invocation.ProductionWriterInvocationAdapterV1
    | None = None,
    seam_bindings: Sequence[Mapping[str, Any]] | None = None,
    composition_attestation: Mapping[str, Any] | None = None,
) -> ProductionClosedRepairProviderV1:
    return ProductionClosedRepairProviderV1(
        config=config,
        coordinator=coordinator,
        transaction_store=transaction_store,
        invocation_adapter=invocation_adapter,
        seam_bindings=seam_bindings,
        composition_attestation=composition_attestation,
    )


__all__ = [
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_PRODUCTION_PROVIDER_V1_VERSION",
    "PRODUCTION_CLOSED_REPAIR_PROVIDER_EXPLICIT_COMPOSITION_ATTESTATION_V1",
    "ProductionClosedRepairProviderBlocked",
    "ProductionClosedRepairProviderConfigV1",
    "ProductionClosedRepairProviderV1",
    "build_production_closed_repair_provider_attestation_v1",
    "build_production_closed_repair_provider_v1",
    "production_closed_repair_provider_attestation_sha256_v1",
]
