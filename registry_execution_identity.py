"""Pure V2.0 execution/lifecycle identity contract.

This module defines only values and in-memory transformations.  It is dormant
until a future, separately authorized integration phase imports it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import uuid


REGISTRY_EXECUTION_IDENTITY_VERSION = "REGISTRY-EXECUTION-IDENTITY-V2.0"
V2_EXECUTION_ID_PREFIX = "exec_"

REGISTRY_EXECUTION_LIFECYCLE_ID_CONFLICT = (
    "REGISTRY_EXECUTION_LIFECYCLE_ID_CONFLICT"
)
REGISTRY_REQUIRED_ID_MISSING = "REGISTRY_REQUIRED_ID_MISSING"
REGISTRY_EXECUTION_IDENTITY_CONFLICT = "REGISTRY_EXECUTION_IDENTITY_CONFLICT"
REGISTRY_EXECUTION_IDENTITY_INVALID_FORMAT = (
    "REGISTRY_EXECUTION_IDENTITY_INVALID_FORMAT"
)
REGISTRY_EXECUTION_IDENTITY_VALID = "REGISTRY_EXECUTION_IDENTITY_VALID"

IDENTITY_FORMAT_V2_CANONICAL = "V2_CANONICAL"
IDENTITY_FORMAT_LEGACY_UNVERIFIED = "LEGACY_UNVERIFIED"


@dataclass(frozen=True)
class ExecutionLifecycleIdentityResult:
    """Pure result for execution/lifecycle alias normalization and validation.

    ``identity_format`` classifies syntax only.  In particular,
    ``LEGACY_UNVERIFIED`` preserves a legacy value without asserting ownership
    or other factual properties.
    """

    ok: bool
    status: str
    conflict: bool
    execution_id: str | None
    lifecycle_id: str | None
    diagnostics: tuple[str, ...] = ()
    identity_format: str | None = None


def generate_execution_lifecycle_id() -> str:
    """Return one new canonical V2 execution/lifecycle identity."""
    return f"{V2_EXECUTION_ID_PREFIX}{uuid.uuid4()}"


def is_v2_execution_id(value: Any) -> bool:
    """Return whether *value* is already a canonical, lowercase V2 ID.

    This predicate is intentionally strict: callers that accept surrounding
    whitespace must use the normalizer, which trims only the outer whitespace.
    """
    return isinstance(value, str) and _is_canonical_v2_execution_id(value)


def normalize_execution_lifecycle_identity(
    *,
    execution_id: Any = None,
    lifecycle_id: Any = None,
    allow_lifecycle_id_compatibility: bool = False,
) -> ExecutionLifecycleIdentityResult:
    """Normalize one identity without inferring from market or runtime data.

    An execution ID projects its lifecycle alias.  A lifecycle-only payload is
    accepted only when the explicitly named compatibility option is enabled.
    Missing identities are permitted here because this function performs
    normalization rather than enforcing an operation-specific requirement.
    """
    return _resolve_execution_lifecycle_identity(
        execution_id=execution_id,
        lifecycle_id=lifecycle_id,
        require_identity=False,
        require_v2_execution_id=False,
        allow_lifecycle_id_compatibility=allow_lifecycle_id_compatibility,
    )


def validate_execution_lifecycle_identity(
    *,
    execution_id: Any = None,
    lifecycle_id: Any = None,
    require_identity: bool = True,
    require_v2_execution_id: bool = False,
    allow_lifecycle_id_compatibility: bool = False,
) -> ExecutionLifecycleIdentityResult:
    """Validate an identity contract without generating or replacing an ID.

    ``require_v2_execution_id`` is for newly created V2 records.  When it is
    false, a non-V2 value is preserved and classified as
    ``LEGACY_UNVERIFIED`` rather than treated as a new V2 ID.
    """
    return _resolve_execution_lifecycle_identity(
        execution_id=execution_id,
        lifecycle_id=lifecycle_id,
        require_identity=require_identity,
        require_v2_execution_id=require_v2_execution_id,
        allow_lifecycle_id_compatibility=allow_lifecycle_id_compatibility,
    )


def _resolve_execution_lifecycle_identity(
    *,
    execution_id: Any,
    lifecycle_id: Any,
    require_identity: bool,
    require_v2_execution_id: bool,
    allow_lifecycle_id_compatibility: bool,
) -> ExecutionLifecycleIdentityResult:
    execution_text, execution_error = _trim_optional_identifier(
        execution_id, "execution_id"
    )
    lifecycle_text, lifecycle_error = _trim_optional_identifier(
        lifecycle_id, "lifecycle_id"
    )

    if execution_error or lifecycle_error:
        diagnostics = tuple(
            item for item in (execution_error, lifecycle_error) if item is not None
        )
        return ExecutionLifecycleIdentityResult(
            ok=False,
            status=REGISTRY_EXECUTION_IDENTITY_CONFLICT,
            conflict=True,
            execution_id=None,
            lifecycle_id=None,
            diagnostics=diagnostics,
        )

    if execution_text is not None and lifecycle_text is not None:
        if execution_text != lifecycle_text:
            return ExecutionLifecycleIdentityResult(
                ok=False,
                status=REGISTRY_EXECUTION_LIFECYCLE_ID_CONFLICT,
                conflict=True,
                execution_id=execution_text,
                lifecycle_id=lifecycle_text,
                diagnostics=("execution_id_lifecycle_id_mismatch",),
            )
    elif execution_text is not None:
        lifecycle_text = execution_text
    elif lifecycle_text is not None:
        if not allow_lifecycle_id_compatibility:
            return ExecutionLifecycleIdentityResult(
                ok=False,
                status=REGISTRY_REQUIRED_ID_MISSING,
                conflict=False,
                execution_id=None,
                lifecycle_id=lifecycle_text,
                diagnostics=("execution_id_required_for_lifecycle_alias",),
            )
        execution_text = lifecycle_text
    elif require_identity or require_v2_execution_id:
        return ExecutionLifecycleIdentityResult(
            ok=False,
            status=REGISTRY_REQUIRED_ID_MISSING,
            conflict=False,
            execution_id=None,
            lifecycle_id=None,
            diagnostics=("execution_lifecycle_identity_required",),
        )
    else:
        return ExecutionLifecycleIdentityResult(
            ok=True,
            status=REGISTRY_EXECUTION_IDENTITY_VALID,
            conflict=False,
            execution_id=None,
            lifecycle_id=None,
        )

    identity_format = _classify_identity_format(execution_text)
    if require_v2_execution_id and identity_format != IDENTITY_FORMAT_V2_CANONICAL:
        return ExecutionLifecycleIdentityResult(
            ok=False,
            status=REGISTRY_EXECUTION_IDENTITY_INVALID_FORMAT,
            conflict=False,
            execution_id=execution_text,
            lifecycle_id=lifecycle_text,
            diagnostics=("canonical_v2_execution_id_required",),
            identity_format=identity_format,
        )

    return ExecutionLifecycleIdentityResult(
        ok=True,
        status=REGISTRY_EXECUTION_IDENTITY_VALID,
        conflict=False,
        execution_id=execution_text,
        lifecycle_id=lifecycle_text,
        identity_format=identity_format,
    )


def _trim_optional_identifier(value: Any, field_name: str) -> tuple[str | None, str | None]:
    if value is None:
        return None, None
    if not isinstance(value, str):
        return None, f"{field_name}_must_be_string"

    normalized = value.strip()
    return (normalized or None), None


def _classify_identity_format(value: str) -> str:
    if _is_canonical_v2_execution_id(value):
        return IDENTITY_FORMAT_V2_CANONICAL
    return IDENTITY_FORMAT_LEGACY_UNVERIFIED


def _is_canonical_v2_execution_id(value: str) -> bool:
    if not value.startswith(V2_EXECUTION_ID_PREFIX):
        return False

    uuid_text = value[len(V2_EXECUTION_ID_PREFIX) :]
    try:
        parsed = uuid.UUID(uuid_text)
    except (AttributeError, TypeError, ValueError):
        return False

    return (
        parsed.version == 4
        and parsed.variant == uuid.RFC_4122
        and str(parsed) == uuid_text
    )


__all__ = (
    "ExecutionLifecycleIdentityResult",
    "IDENTITY_FORMAT_LEGACY_UNVERIFIED",
    "IDENTITY_FORMAT_V2_CANONICAL",
    "REGISTRY_EXECUTION_IDENTITY_CONFLICT",
    "REGISTRY_EXECUTION_IDENTITY_INVALID_FORMAT",
    "REGISTRY_EXECUTION_IDENTITY_VALID",
    "REGISTRY_EXECUTION_IDENTITY_VERSION",
    "REGISTRY_EXECUTION_LIFECYCLE_ID_CONFLICT",
    "REGISTRY_REQUIRED_ID_MISSING",
    "V2_EXECUTION_ID_PREFIX",
    "generate_execution_lifecycle_id",
    "is_v2_execution_id",
    "normalize_execution_lifecycle_identity",
    "validate_execution_lifecycle_identity",
)
