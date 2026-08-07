from __future__ import annotations

import ast
import builtins
import importlib
import inspect
from pathlib import Path
import uuid

import pytest

import registry_execution_identity as identity
from registry_execution_identity import (
    IDENTITY_FORMAT_LEGACY_UNVERIFIED,
    IDENTITY_FORMAT_V2_CANONICAL,
    REGISTRY_EXECUTION_IDENTITY_CONFLICT,
    REGISTRY_EXECUTION_IDENTITY_INVALID_FORMAT,
    REGISTRY_EXECUTION_IDENTITY_VALID,
    REGISTRY_EXECUTION_LIFECYCLE_ID_CONFLICT,
    REGISTRY_REQUIRED_ID_MISSING,
    generate_execution_lifecycle_id,
    is_v2_execution_id,
    normalize_execution_lifecycle_identity,
    validate_execution_lifecycle_identity,
)


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "registry_execution_identity.py"
MODULE_NAME = "registry_execution_identity"


def _new_v2_id() -> str:
    return generate_execution_lifecycle_id()


def _module_tree() -> ast.Module:
    return ast.parse(MODULE_PATH.read_text(encoding="utf-8"))


def _import_roots(tree: ast.Module) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", maxsplit=1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".", maxsplit=1)[0])
    return roots


def test_generated_id_uses_exec_prefix_and_uuid4():
    generated = _new_v2_id()

    assert generated.startswith("exec_")
    assert uuid.UUID(generated.removeprefix("exec_")).version == 4
    assert is_v2_execution_id(generated) is True


def test_generated_id_is_lowercase_canonical():
    generated = _new_v2_id()

    assert generated == generated.lower()
    assert str(uuid.UUID(generated.removeprefix("exec_"))) == generated.removeprefix(
        "exec_"
    )


def test_one_thousand_generated_ids_are_unique():
    generated = {_new_v2_id() for _ in range(1_000)}

    assert len(generated) == 1_000


def test_generation_accepts_no_market_or_runtime_inputs():
    assert tuple(inspect.signature(generate_execution_lifecycle_id).parameters) == ()

    with pytest.raises(TypeError):
        generate_execution_lifecycle_id(symbol="BTCUSDT")


def test_execution_only_projects_lifecycle_alias():
    execution_id = _new_v2_id()

    result = normalize_execution_lifecycle_identity(execution_id=execution_id)

    assert result.ok is True
    assert result.status == REGISTRY_EXECUTION_IDENTITY_VALID
    assert result.execution_id == execution_id
    assert result.lifecycle_id == execution_id
    assert result.identity_format == IDENTITY_FORMAT_V2_CANONICAL


def test_lifecycle_only_projects_execution_only_with_explicit_compatibility():
    lifecycle_id = "LEGACY-LIFECYCLE-001"

    result = normalize_execution_lifecycle_identity(
        lifecycle_id=lifecycle_id,
        allow_lifecycle_id_compatibility=True,
    )

    assert result.ok is True
    assert result.execution_id == lifecycle_id
    assert result.lifecycle_id == lifecycle_id
    assert result.identity_format == IDENTITY_FORMAT_LEGACY_UNVERIFIED


def test_lifecycle_only_without_explicit_compatibility_fails_closed():
    result = normalize_execution_lifecycle_identity(lifecycle_id="LEGACY-LIFECYCLE-001")

    assert result.ok is False
    assert result.status == REGISTRY_REQUIRED_ID_MISSING
    assert result.execution_id is None


def test_matching_aliases_are_accepted():
    execution_id = _new_v2_id()

    result = validate_execution_lifecycle_identity(
        execution_id=execution_id,
        lifecycle_id=execution_id,
        require_v2_execution_id=True,
    )

    assert result.ok is True
    assert result.conflict is False
    assert result.execution_id == result.lifecycle_id == execution_id


def test_divergent_aliases_return_conflict():
    result = validate_execution_lifecycle_identity(
        execution_id=_new_v2_id(),
        lifecycle_id=_new_v2_id(),
        require_v2_execution_id=True,
    )

    assert result.ok is False
    assert result.conflict is True
    assert result.status == REGISTRY_EXECUTION_LIFECYCLE_ID_CONFLICT


def test_divergence_never_generates_a_third_identity():
    execution_id = _new_v2_id()
    lifecycle_id = _new_v2_id()

    result = normalize_execution_lifecycle_identity(
        execution_id=f"  {execution_id}  ",
        lifecycle_id=f"  {lifecycle_id}  ",
    )

    assert result.ok is False
    assert result.execution_id == execution_id
    assert result.lifecycle_id == lifecycle_id
    assert {result.execution_id, result.lifecycle_id} == {execution_id, lifecycle_id}


def test_outer_whitespace_is_trimmed_without_changing_identifier_case():
    result = normalize_execution_lifecycle_identity(
        execution_id="  LEGACY-Case-Preserved  "
    )

    assert result.ok is True
    assert result.execution_id == "LEGACY-Case-Preserved"
    assert result.lifecycle_id == "LEGACY-Case-Preserved"
    assert result.identity_format == IDENTITY_FORMAT_LEGACY_UNVERIFIED


def test_missing_both_ids_is_required_failure_when_identity_is_required():
    result = validate_execution_lifecycle_identity()

    assert result.ok is False
    assert result.conflict is False
    assert result.status == REGISTRY_REQUIRED_ID_MISSING
    assert result.execution_id is None
    assert result.lifecycle_id is None


def test_missing_both_ids_can_be_normalized_when_not_required():
    result = normalize_execution_lifecycle_identity()

    assert result.ok is True
    assert result.status == REGISTRY_EXECUTION_IDENTITY_VALID
    assert result.execution_id is None
    assert result.lifecycle_id is None


def test_malformed_new_v2_identity_is_rejected_by_strict_validation():
    malformed = "exec_not-a-uuid"

    result = validate_execution_lifecycle_identity(
        execution_id=malformed,
        require_v2_execution_id=True,
    )

    assert is_v2_execution_id(malformed) is False
    assert result.ok is False
    assert result.status == REGISTRY_EXECUTION_IDENTITY_INVALID_FORMAT
    assert result.execution_id == malformed


def test_non_v4_uuid_is_not_accepted_as_new_v2_identity():
    non_v4 = f"exec_{uuid.uuid1()}"

    result = validate_execution_lifecycle_identity(
        execution_id=non_v4,
        require_v2_execution_id=True,
    )

    assert is_v2_execution_id(non_v4) is False
    assert result.ok is False
    assert result.status == REGISTRY_EXECUTION_IDENTITY_INVALID_FORMAT


def test_legacy_identity_is_preserved_and_never_regenerated():
    legacy = "CENTRAL-FALCON-LIFECYCLE:existing-identity"

    result = normalize_execution_lifecycle_identity(execution_id=legacy)

    assert result.ok is True
    assert result.execution_id == legacy
    assert result.lifecycle_id == legacy
    assert result.identity_format == IDENTITY_FORMAT_LEGACY_UNVERIFIED
    assert not result.execution_id.startswith("exec_")


def test_legacy_identity_is_not_confused_with_v2_canonical_format():
    legacy_that_looks_new = f"exec_{uuid.uuid1()}"

    result = normalize_execution_lifecycle_identity(execution_id=legacy_that_looks_new)

    assert result.ok is True
    assert result.identity_format == IDENTITY_FORMAT_LEGACY_UNVERIFIED
    assert is_v2_execution_id(legacy_that_looks_new) is False


def test_validation_is_deterministic_for_the_same_input():
    execution_id = _new_v2_id()

    first = validate_execution_lifecycle_identity(
        execution_id=f" {execution_id} ",
        lifecycle_id=execution_id,
        require_v2_execution_id=True,
    )
    second = validate_execution_lifecycle_identity(
        execution_id=f" {execution_id} ",
        lifecycle_id=execution_id,
        require_v2_execution_id=True,
    )

    assert first == second


def test_non_string_identifier_fails_closed_without_coercion():
    result = normalize_execution_lifecycle_identity(execution_id=123)

    assert result.ok is False
    assert result.conflict is True
    assert result.status == REGISTRY_EXECUTION_IDENTITY_CONFLICT
    assert result.execution_id is None
    assert result.lifecycle_id is None


def test_uppercase_or_outer_whitespace_is_not_already_canonical_v2_format():
    generated = _new_v2_id()

    assert is_v2_execution_id(generated.upper()) is False
    assert is_v2_execution_id(f" {generated} ") is False


def test_module_import_has_no_builtin_file_open_side_effect(monkeypatch):
    observed: list[tuple[object, ...]] = []

    def forbidden_open(*args, **kwargs):
        observed.append(args)
        raise AssertionError("registry_execution_identity must not call open() on import")

    with monkeypatch.context() as context:
        context.setattr(builtins, "open", forbidden_open)
        reloaded = importlib.reload(identity)

    assert observed == []
    assert reloaded.generate_execution_lifecycle_id is not None


def test_module_does_not_import_runtime_boundaries():
    roots = _import_roots(_module_tree())
    allowed = {"__future__", "dataclasses", "typing", "uuid"}
    forbidden = {
        "bots",
        "broker",
        "execution_engine",
        "execution_orchestrator",
        "flask",
        "main",
        "redis",
        "requests",
        "trade_registry",
    }

    assert roots <= allowed
    assert roots.isdisjoint(forbidden)


def test_v2_0_source_contains_no_persistence_or_external_capabilities():
    source = MODULE_PATH.read_text(encoding="utf-8").lower()
    tree = _module_tree()
    forbidden_words = (
        "journal",
        "migration",
        "persistence",
        "subprocess",
        "thread",
        "wal",
    )
    forbidden_calls = {"open"}
    forbidden_attributes = {
        "environ",
        "open",
        "read_bytes",
        "read_text",
        "write_bytes",
        "write_text",
    }

    assert not any(word in source for word in forbidden_words)
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in forbidden_calls
        for node in ast.walk(tree)
    )
    assert not any(
        isinstance(node, ast.Attribute) and node.attr in forbidden_attributes
        for node in ast.walk(tree)
    )
