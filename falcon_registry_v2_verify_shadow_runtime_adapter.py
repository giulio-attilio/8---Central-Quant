"""Dormant, in-memory adapter for the pure Falcon V2.8 VERIFY observer.

This module has no activation mechanism.  Callers must explicitly pass
``enabled=True`` in a local/test seam; the default is always off.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from falcon_registry_v2_verify_shadow import (
    FalconRegistryV2VerifyShadowObservationError,
    FalconRegistryV2VerifyShadowResult,
    observe_falcon_registry_v2_verify_shadow,
)


FALCON_REGISTRY_V2_VERIFY_SHADOW_ENABLED_DEFAULT = False
RUNTIME_SHADOW_DISABLED = "DISABLED"
RUNTIME_SHADOW_INELIGIBLE = "INELIGIBLE"
RUNTIME_SHADOW_OBSERVER_ERROR = "OBSERVER_ERROR"


@dataclass(frozen=True)
class FalconRegistryV2VerifyShadowRuntimeDiagnostic:
    """Immutable diagnostic return value with no execution authority."""

    enabled: bool
    eligible: bool
    status: str
    shadow_stage: str | None = None
    result: FalconRegistryV2VerifyShadowResult | None = None
    error: str | None = None
    execution_id: None = None
    lifecycle_id: None = None
    shadow_identity_operational: bool = False


class FalconRegistryV2VerifyShadowRuntimeAdapter:
    """Run a supplied pure observer only for an explicitly enabled VERIFY call."""

    def __init__(
        self,
        observer: Callable[[Any], FalconRegistryV2VerifyShadowResult]
        | None = None,
    ) -> None:
        self._observer = observer or observe_falcon_registry_v2_verify_shadow

    def observe(
        self,
        runtime_facts: Mapping[str, Any],
        *,
        enabled: bool = FALCON_REGISTRY_V2_VERIFY_SHADOW_ENABLED_DEFAULT,
    ) -> FalconRegistryV2VerifyShadowRuntimeDiagnostic:
        if enabled is not True:
            return FalconRegistryV2VerifyShadowRuntimeDiagnostic(
                enabled=False,
                eligible=False,
                status=RUNTIME_SHADOW_DISABLED,
            )
        if not isinstance(runtime_facts, Mapping):
            return FalconRegistryV2VerifyShadowRuntimeDiagnostic(
                enabled=True,
                eligible=False,
                status=RUNTIME_SHADOW_INELIGIBLE,
                error="runtime_facts",
            )
        if _upper(runtime_facts.get("execution_mode")) != "VERIFY":
            return FalconRegistryV2VerifyShadowRuntimeDiagnostic(
                enabled=True,
                eligible=False,
                status=RUNTIME_SHADOW_INELIGIBLE,
                shadow_stage=_text(runtime_facts.get("shadow_stage")),
                error="execution_mode",
            )
        try:
            result = self._observer(runtime_facts)
        except FalconRegistryV2VerifyShadowObservationError as exc:
            return FalconRegistryV2VerifyShadowRuntimeDiagnostic(
                enabled=True,
                eligible=True,
                status=RUNTIME_SHADOW_OBSERVER_ERROR,
                shadow_stage=_text(runtime_facts.get("shadow_stage")),
                error=f"{type(exc).__name__}: {exc}",
            )
        if not isinstance(result, FalconRegistryV2VerifyShadowResult):
            raise TypeError("observer returned an invalid result")
        return FalconRegistryV2VerifyShadowRuntimeDiagnostic(
            enabled=True,
            eligible=True,
            status=result.status,
            shadow_stage=result.projection.shadow_stage,
            result=result,
        )


def observe_falcon_registry_v2_verify_shadow_runtime(
    runtime_facts: Mapping[str, Any],
    *,
    enabled: bool = FALCON_REGISTRY_V2_VERIFY_SHADOW_ENABLED_DEFAULT,
) -> FalconRegistryV2VerifyShadowRuntimeDiagnostic:
    """Evaluate one explicit local/test observation without retaining state."""

    return FalconRegistryV2VerifyShadowRuntimeAdapter().observe(
        runtime_facts, enabled=enabled
    )


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _upper(value: Any) -> str | None:
    text = _text(value)
    return text.upper() if text is not None else None


__all__ = (
    "FALCON_REGISTRY_V2_VERIFY_SHADOW_ENABLED_DEFAULT",
    "FalconRegistryV2VerifyShadowRuntimeAdapter",
    "FalconRegistryV2VerifyShadowRuntimeDiagnostic",
    "RUNTIME_SHADOW_DISABLED",
    "RUNTIME_SHADOW_INELIGIBLE",
    "RUNTIME_SHADOW_OBSERVER_ERROR",
    "observe_falcon_registry_v2_verify_shadow_runtime",
)
