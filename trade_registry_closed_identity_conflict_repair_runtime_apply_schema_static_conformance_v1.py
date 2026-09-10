"""Offline AST conformance contract for the dormant CLOSED-repair apply DTO.

The evaluator accepts source text supplied by the caller.  It never imports the
runtime modules, reads files, serializes an apply request or invokes a
controller.  Its purpose is to make the currently reviewed controller, HTTP
route and protected DTO surfaces explicit and to fail closed when one of those
surfaces changes.
"""

from __future__ import annotations

import ast
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_APPLY_SCHEMA_STATIC_CONFORMANCE_V1_VERSION = (
    "2026-09-06-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-APPLY-SCHEMA-STATIC-CONFORMANCE-V1"
)

OFFLINE_STATIC_CONFORMANCE_SCOPE_ATTESTATION_V1 = (
    "C3_CLOSED_REPAIR_APPLY_SCHEMA_STATIC_CONFORMANCE_OFFLINE_ONLY_V1"
)

_EXPECTED_APPLY_ACK = "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_APPLY_V1"
_EXPECTED_CONTROLLER_REQUEST_FIELDS = ("ack", "preview_receipt_sha256")
_EXPECTED_PROTECTED_DTO_FIELDS = (
    "ack",
    "preview_receipt_sha256",
    "package_receipt_sha256",
    "authorization_receipt_sha256",
    "controller_instance_sha256",
    "reservation_token_sha256",
    "expires_at_epoch",
)
_PROTECTED_AUTHORITY_FIELDS = frozenset(
    {
        "package_receipt_sha256",
        "authorization_receipt_sha256",
        "controller_instance_sha256",
        "reservation_token_sha256",
    }
)
_EXPECTED_ROUTE_OPERATIONS = frozenset({"apply", "preview"})


@dataclass(frozen=True)
class StaticApplySchemaConformanceConfigV1:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    max_source_bytes: int = 4_000_000

    def __post_init__(self) -> None:
        if not 1_024 <= self.max_source_bytes <= 8_000_000:
            raise ValueError("max_source_bytes must be between 1024 and 8000000")


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


def _source_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _base() -> dict[str, Any]:
    return {
        "ok": False,
        "status": "C3_APPLY_SCHEMA_STATIC_CONFORMANCE_BLOCKED",
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_APPLY_SCHEMA_STATIC_CONFORMANCE_V1_VERSION,
        "static_conformance_verified": False,
        "drift_detected": True,
        "direct_controller_schema_compatible": False,
        "http_route_payload_compatible": False,
        "deadline_semantics_aligned": False,
        "authorization_gateway_bound": False,
        "same_runtime_instance_verified": False,
        "runtime_binding_satisfied": False,
        "production_ready": False,
        "apply_allowed": False,
        "activation_allowed": False,
        "live_allowed": False,
        "offline_only": True,
        "runtime_imported": False,
        "runtime_invoked": False,
        "real_registry_accessed": False,
        "network_accessed": False,
        "broker_called": False,
        "write_executed": False,
        "no_order_sent": True,
        "checks": {},
        "drift_reasons": [],
        "known_blockers": [],
        "conformance_receipt": None,
    }


def _parse_source(
    label: str,
    source: Any,
    max_source_bytes: int,
    reasons: list[str],
    checks: dict[str, bool],
) -> tuple[ast.Module | None, str]:
    valid = isinstance(source, str) and bool(source) and "\x00" not in source
    encoded = source.encode("utf-8") if valid else b""
    valid = valid and len(encoded) <= max_source_bytes
    tree: ast.Module | None = None
    if valid:
        try:
            tree = ast.parse(source)
        except (SyntaxError, ValueError, MemoryError, RecursionError):
            tree = None
    checks[f"{label}_source_parsed"] = tree is not None
    if tree is None:
        reasons.append(f"{label.upper()}_SOURCE_INVALID")
        return None, ""
    return tree, hashlib.sha256(encoded).hexdigest()


def _literal_assignment(tree: ast.Module, name: str) -> Any:
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
                try:
                    return ast.literal_eval(node.value)
                except (ValueError, TypeError):
                    return None
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == name:
                try:
                    return ast.literal_eval(node.value)
                except (ValueError, TypeError):
                    return None
    return None


def _find_function(tree: ast.AST, name: str) -> ast.FunctionDef | None:
    matches = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    ]
    return matches[0] if len(matches) == 1 and isinstance(matches[0], ast.FunctionDef) else None


def _find_class(tree: ast.Module, name: str) -> ast.ClassDef | None:
    matches = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == name]
    return matches[0] if len(matches) == 1 else None


def _class_fields(class_node: ast.ClassDef | None) -> tuple[str, ...]:
    if class_node is None:
        return ()
    return tuple(
        node.target.id
        for node in class_node.body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
    )


def _request_get_fields(function: ast.FunctionDef | None, receiver: str) -> tuple[str, ...]:
    if function is None:
        return ()
    fields: set[str] = set()
    for node in ast.walk(function):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "get" or not isinstance(node.func.value, ast.Name):
            continue
        if node.func.value.id != receiver or not node.args:
            continue
        if isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
            fields.add(node.args[0].value)
    return tuple(sorted(fields))


def _imports(tree: ast.Module) -> frozenset[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return frozenset(names)


def _contains_all(node: ast.AST | None, values: set[str]) -> bool:
    if node is None:
        return False
    dumped = ast.dump(node, include_attributes=False)
    return all(value in dumped for value in values)


def _has_compare(
    node: ast.AST | None,
    operator_type: type[ast.cmpop],
    required_tokens: set[str],
) -> bool:
    if node is None:
        return False
    for candidate in ast.walk(node):
        if not isinstance(candidate, ast.Compare):
            continue
        if not any(isinstance(operator, operator_type) for operator in candidate.ops):
            continue
        if _contains_all(candidate, required_tokens):
            return True
    return False


def _has_receiver_call(
    node: ast.AST | None,
    receiver_attribute: str,
    method: str,
    argument_name: str,
) -> bool:
    if node is None:
        return False
    for candidate in ast.walk(node):
        if not isinstance(candidate, ast.Call) or not isinstance(candidate.func, ast.Attribute):
            continue
        owner = candidate.func.value
        if not (
            candidate.func.attr == method
            and isinstance(owner, ast.Attribute)
            and owner.attr == receiver_attribute
            and isinstance(owner.value, ast.Name)
            and owner.value.id == "self"
            and candidate.args
            and isinstance(candidate.args[0], ast.Name)
            and candidate.args[0].id == argument_name
        ):
            continue
        return True
    return False


def _literal_list_comparison(
    node: ast.AST | None, receiver: str, key: str
) -> tuple[str, ...]:
    if node is None:
        return ()
    for candidate in ast.walk(node):
        if not isinstance(candidate, ast.Compare) or len(candidate.comparators) != 1:
            continue
        left = candidate.left
        if not (
            isinstance(left, ast.Call)
            and isinstance(left.func, ast.Attribute)
            and left.func.attr == "get"
            and isinstance(left.func.value, ast.Name)
            and left.func.value.id == receiver
            and left.args
            and isinstance(left.args[0], ast.Constant)
            and left.args[0].value == key
        ):
            continue
        right = candidate.comparators[0]
        if isinstance(right, (ast.List, ast.Tuple)):
            try:
                value = ast.literal_eval(right)
            except (ValueError, TypeError):
                return ()
            if isinstance(value, (list, tuple)) and all(isinstance(item, str) for item in value):
                return tuple(value)
    return ()


def _route_operations(function: ast.FunctionDef | None) -> frozenset[str]:
    if function is None:
        return frozenset()
    for node in ast.walk(function):
        if not isinstance(node, ast.Compare):
            continue
        for comparator in node.comparators:
            if isinstance(comparator, (ast.Set, ast.Tuple, ast.List)):
                try:
                    value = ast.literal_eval(comparator)
                except (ValueError, TypeError):
                    continue
                if isinstance(value, (set, tuple, list)) and "apply" in value:
                    return frozenset(str(item) for item in value)
    return frozenset()


def _has_controller_apply_dispatch(function: ast.FunctionDef | None) -> bool:
    if function is None:
        return False
    for node in ast.walk(function):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if not (
            node.func.attr == "apply"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "controller"
            and len(node.args) == 1
        ):
            continue
        argument = node.args[0]
        if (
            isinstance(argument, ast.Subscript)
            and isinstance(argument.value, ast.Name)
            and argument.value.id == "decision"
            and isinstance(argument.slice, ast.Constant)
            and argument.slice.value == "payload"
        ):
            return True
    return False


def _has_exact_mapping_enforcement(function: ast.FunctionDef | None, receiver: str) -> bool:
    if function is None:
        return False
    for node in ast.walk(function):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        if node.func.id == "set" and node.args and isinstance(node.args[0], ast.Name):
            if node.args[0].id == receiver:
                return True
    return False


def _has_default_false(class_node: ast.ClassDef | None, field_name: str) -> bool:
    if class_node is None:
        return False
    for node in class_node.body:
        if not isinstance(node, ast.AnnAssign) or not isinstance(node.target, ast.Name):
            continue
        if node.target.id == field_name and isinstance(node.value, ast.Constant):
            return node.value.value is False
    return False


def evaluate_c3_apply_schema_static_conformance_offline_v1(
    *,
    operation_source: str,
    route_source: str,
    adapter_source: str,
    config: StaticApplySchemaConformanceConfigV1 | None = None,
) -> dict[str, Any]:
    """Compare three supplied source snapshots without importing any of them."""

    result = _base()
    cfg = config or StaticApplySchemaConformanceConfigV1()
    if cfg.enabled is not True:
        result["status"] = "C3_APPLY_SCHEMA_STATIC_CONFORMANCE_DEFAULT_OFF"
        result["drift_reasons"] = ["STATIC_CONFORMANCE_DEFAULT_OFF"]
        return result
    if cfg.scope_attestation != OFFLINE_STATIC_CONFORMANCE_SCOPE_ATTESTATION_V1:
        result["status"] = "C3_APPLY_SCHEMA_STATIC_CONFORMANCE_SCOPE_REQUIRED"
        result["drift_reasons"] = ["OFFLINE_SCOPE_ATTESTATION_REQUIRED"]
        return result

    reasons: list[str] = []
    checks: dict[str, bool] = {}
    operation_tree, operation_sha = _parse_source(
        "operation", operation_source, cfg.max_source_bytes, reasons, checks
    )
    route_tree, route_sha = _parse_source(
        "route", route_source, cfg.max_source_bytes, reasons, checks
    )
    adapter_tree, adapter_sha = _parse_source(
        "adapter", adapter_source, cfg.max_source_bytes, reasons, checks
    )
    if not all((operation_tree, route_tree, adapter_tree)):
        result.update(checks=checks, drift_reasons=sorted(set(reasons)))
        return result

    operation_apply = _find_function(operation_tree, "apply")
    operation_config = _find_class(operation_tree, "ClosedIdentityRepairRuntimeConfigV1")
    route_parser = _find_function(route_tree, "_c3_closed_identity_repair_request_v1")
    route_dispatch = _find_function(
        route_tree, "trade_registry_closed_identity_repair_runtime_operation_v1_route"
    )
    adapter_intent_check = _find_function(adapter_tree, "_check_intent")
    adapter_prepare = _find_function(adapter_tree, "prepare")
    protected_dto = _find_class(adapter_tree, "ProtectedDormantApplyRequestV1")

    operation_ack = _literal_assignment(operation_tree, "APPLY_ACK_V1")
    adapter_ack = _literal_assignment(adapter_tree, "_APPLY_ACK_V1")
    controller_fields = _request_get_fields(operation_apply, "request_payload")
    adapter_fields = _literal_list_comparison(
        adapter_intent_check, "value", "request_payload_fields"
    )
    protected_fields = _class_fields(protected_dto)
    route_fields = _request_get_fields(route_parser, "body")
    route_operations = _route_operations(route_parser)
    operation_imported_by_route = (
        "trade_registry_closed_identity_conflict_repair_runtime_operation_v1"
        in _imports(route_tree)
    )
    adapter_runtime_import_absent = not any(
        name == "main"
        or name == "trade_registry_closed_identity_conflict_repair_runtime_operation_v1"
        for name in _imports(adapter_tree)
    )

    operation_dump = ast.dump(operation_apply, include_attributes=False) if operation_apply else ""
    route_dump = "".join(
        ast.dump(node, include_attributes=False)
        for node in (route_parser, route_dispatch)
        if node is not None
    )
    protected_authority_consumed = any(
        field_name in operation_dump or field_name in route_dump
        for field_name in _PROTECTED_AUTHORITY_FIELDS
    )

    checks.update(
        {
            "operation_apply_found": operation_apply is not None,
            "operation_apply_default_off": _has_default_false(operation_config, "apply_enabled"),
            "operation_ack_exact": operation_ack == _EXPECTED_APPLY_ACK,
            "adapter_ack_exact": adapter_ack == _EXPECTED_APPLY_ACK,
            "ack_constants_aligned": operation_ack == adapter_ack == _EXPECTED_APPLY_ACK,
            "controller_request_fields_exact": controller_fields
            == tuple(sorted(_EXPECTED_CONTROLLER_REQUEST_FIELDS)),
            "adapter_request_fields_exact": adapter_fields
            == _EXPECTED_CONTROLLER_REQUEST_FIELDS,
            "direct_schema_aligned": set(controller_fields) == set(adapter_fields),
            "protected_dto_fields_exact": protected_fields == _EXPECTED_PROTECTED_DTO_FIELDS,
            "same_instance_pending_lookup_present": _has_receiver_call(
                operation_apply, "_pending", "get", "receipt_sha"
            ),
            "controller_apply_allowed_gate_present": _contains_all(
                operation_apply, {"apply_allowed", "IsNot", "True"}
            ),
            "controller_expiry_snapshot_is_legacy_gt": _has_compare(
                operation_apply, ast.Gt, {"_clock", "expires_at_epoch"}
            ),
            "adapter_expiry_is_strict_lt": _has_compare(
                adapter_prepare, ast.Lt, {"now", "expiry"}
            ),
            "controller_unknown_fields_currently_accepted": not _has_exact_mapping_enforcement(
                operation_apply, "request_payload"
            ),
            "route_operation_field_present": route_fields == ("operation",),
            "route_operations_exact": route_operations == _EXPECTED_ROUTE_OPERATIONS,
            "route_apply_dispatch_exact": _has_controller_apply_dispatch(route_dispatch),
            "route_imports_expected_operation": operation_imported_by_route,
            "adapter_runtime_import_absent": adapter_runtime_import_absent,
            "protected_authority_not_consumed_by_runtime": not protected_authority_consumed,
        }
    )

    for check_name, passed in checks.items():
        if not passed:
            reasons.append(f"STATIC_CONFORMANCE_DRIFT_{check_name.upper()}")

    drift_reasons = sorted(set(reasons))
    direct_compatible = bool(
        checks.get("ack_constants_aligned")
        and checks.get("direct_schema_aligned")
        and checks.get("same_instance_pending_lookup_present")
    )
    route_payload_compatible = bool(
        direct_compatible and "operation" in set(adapter_fields)
    )
    deadline_aligned = bool(
        checks.get("adapter_expiry_is_strict_lt")
        and not checks.get("controller_expiry_snapshot_is_legacy_gt")
    )
    authorization_bound = protected_authority_consumed

    known_blockers = [
        "HTTP_ROUTE_REQUIRES_OPERATION_ENVELOPE_NOT_PRESENT_IN_PROJECTED_FIELDS",
        "CONTROLLER_DOES_NOT_CONSUME_PACKAGE_AUTHORIZATION_OR_RESERVATION",
        "SAME_RUNTIME_INSTANCE_IS_NOT_PROVEN_BY_OFFLINE_DTO",
        "CONTROLLER_AND_ADAPTER_DEADLINE_SEMANTICS_DIFFER",
        "CONTROLLER_ACCEPTS_UNKNOWN_REQUEST_FIELDS",
        "ADAPTER_HAS_NO_RUNTIME_BINDING_OR_INVOCATION_SURFACE",
    ]
    semantic_snapshot = {
        "operation_source_sha256": operation_sha,
        "route_source_sha256": route_sha,
        "adapter_source_sha256": adapter_sha,
        "apply_ack_sha256": _source_sha256(_EXPECTED_APPLY_ACK),
        "controller_request_fields": list(controller_fields),
        "adapter_request_fields": list(adapter_fields),
        "protected_dto_fields": list(protected_fields),
        "route_request_fields": list(route_fields),
        "route_operations": sorted(route_operations),
        "direct_controller_schema_compatible": direct_compatible,
        "http_route_payload_compatible": route_payload_compatible,
        "deadline_semantics_aligned": deadline_aligned,
        "authorization_gateway_bound": authorization_bound,
        "runtime_binding_satisfied": False,
        "production_ready": False,
        "apply_allowed": False,
    }
    receipt = dict(semantic_snapshot)
    receipt["semantic_snapshot_sha256"] = _stable_sha256(semantic_snapshot)
    receipt["conformance_receipt_sha256"] = _stable_sha256(receipt)

    verified = not drift_reasons and all(checks.values())
    result.update(
        ok=verified,
        status=(
            "C3_APPLY_SCHEMA_STATIC_CONFORMANCE_VERIFIED_OFFLINE"
            if verified
            else "C3_APPLY_SCHEMA_STATIC_CONFORMANCE_DRIFT_DETECTED"
        ),
        static_conformance_verified=verified,
        drift_detected=not verified,
        direct_controller_schema_compatible=direct_compatible,
        http_route_payload_compatible=route_payload_compatible,
        deadline_semantics_aligned=deadline_aligned,
        authorization_gateway_bound=authorization_bound,
        checks=checks,
        drift_reasons=drift_reasons,
        known_blockers=known_blockers,
        conformance_receipt=receipt if verified else None,
    )
    return result


__all__ = [
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_APPLY_SCHEMA_STATIC_CONFORMANCE_V1_VERSION",
    "OFFLINE_STATIC_CONFORMANCE_SCOPE_ATTESTATION_V1",
    "StaticApplySchemaConformanceConfigV1",
    "evaluate_c3_apply_schema_static_conformance_offline_v1",
]
