"""AST-only preflight for the dormant CLOSED-repair runtime integration.

The evaluator accepts source text as data.  It never imports, executes or
modifies the inspected runtime modules and it can never authorize production.
"""

from __future__ import annotations

import ast
import hashlib
import json
from collections.abc import Mapping
from typing import Any

import trade_registry_closed_identity_conflict_repair_writer_coordination_contract_v1 as coordination
import trade_registry_closed_identity_conflict_repair_writer_seam_binding_contract_v1 as seam_contract


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_STATIC_PREFLIGHT_V1_VERSION = (
    "2026-09-04-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-STATIC-PREFLIGHT-V1"
)

REQUIRED_SOURCE_KEYS_V1 = (
    "main.py",
    "trade_registry.py",
    "bots/meme.py",
    "bots/predator.py",
    "bots/turtle.py",
    "trade_registry_closed_identity_conflict_repair_raw_transaction_store_production_v1.py",
    "trade_registry_closed_identity_conflict_repair_writer_invocation_adapter_v1.py",
    "trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1.py",
    "trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_resolved_authority_physical_store_reference_v2.py",
    "trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_resolved_authority_bridge_v2.py",
    "trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_persistent_authority_boundary_v2.py",
    "trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_persistent_authority_production_adapters_v2.py",
    "trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authority_provisioning_manifest_contract_v2.py",
    "trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authority_provisioning_receipt_contract_v2.py",
    "trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authority_provisioning_receipt_authenticated_verifier_contract_v2.py",
    "trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authority_provisioning_physical_binding_contract_v2.py",
)

_WRITER_MUTATION_MARKER = "_c3_closed_repair_writer_mutation_v1"
_PROVIDER_INSTALL_MARKER = "_install_c3_closed_repair_writer_coordination_v1"
_STARTUP_RECOVERY_MARKER = "_recover_c3_closed_repair_registry_v1"
_STALE_LEASE_RECOVERY_MARKER = "recover_stale_maintenance_lease_v1"
_LIVE_PREFLIGHT_CHECK_CODE = "TRADE_REGISTRY_C3_WRITER_COORDINATION_READY"
_LIVE_PREFLIGHT_REQUIRED_C3_VECTOR = (
    ("enabled", True),
    ("coordination_ready", True),
    ("runtime_activation_allowed", True),
    ("registered_writer_count", 19),
    ("all_writers_registered", True),
    ("inflight_mutations", 0),
    ("shared_lock_backend_ready", True),
    ("maintenance_lease_store_ready", True),
    ("registry_interlock_ready", True),
    ("activation_receipt_verified", True),
    ("source_hashes_verified", True),
    ("rollback_ready", True),
    ("startup_recovery_verified", True),
    ("kill_switch_ready", True),
)
_PRODUCTION_STORE_MODULE = (
    "trade_registry_closed_identity_conflict_repair_raw_transaction_store_production_v1"
)
_RESOLVED_AUTHORITY_PHYSICAL_STORE_MODULE = (
    "trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_resolved_authority_physical_store_reference_v2"
)
_RESOLVED_AUTHORITY_STARTUP_BRIDGE_MODULE = (
    "trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_resolved_authority_bridge_v2"
)
_RESOLVED_AUTHORITY_STARTUP_BRIDGE_BUILDER = (
    "build_dormant_resolved_authority_startup_recovery_bridge_v2"
)
_RESOLVED_AUTHORITY_STARTUP_BRIDGE_GLOBAL = (
    "C3_CLOSED_REPAIR_RESOLVED_AUTHORITY_STARTUP_BRIDGE_V2"
)
_AUTHENTICATED_PERSISTENT_AUTHORITY_BOUNDARY_MODULE = (
    "trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_persistent_authority_boundary_v2"
)
_AUTHENTICATED_PERSISTENT_AUTHORITY_BOUNDARY_BUILDER = (
    "build_dormant_authenticated_persistent_authority_boundary_v2"
)
_AUTHENTICATED_PERSISTENT_AUTHORITY_BOUNDARY_GLOBAL = (
    "C3_CLOSED_REPAIR_AUTHENTICATED_PERSISTENT_AUTHORITY_BOUNDARY_V2"
)
_AUTHENTICATED_PERSISTENT_AUTHORITY_ADAPTERS_MODULE = (
    "trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_persistent_authority_production_adapters_v2"
)
_AUTHENTICATED_PERSISTENT_AUTHORITY_ADAPTERS_BUILDER = (
    "build_dormant_authenticated_persistent_authority_production_adapters_v2"
)
_AUTHENTICATED_PERSISTENT_AUTHORITY_ADAPTERS_GLOBAL = (
    "C3_CLOSED_REPAIR_AUTHENTICATED_PERSISTENT_AUTHORITY_PRODUCTION_ADAPTERS_V2"
)
_AUTHORITY_PROVISIONING_MANIFEST_MODULE = (
    "trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authority_provisioning_manifest_contract_v2"
)
_AUTHORITY_PROVISIONING_MANIFEST_BUILDER = (
    "build_dormant_authority_provisioning_manifest_contract_v2"
)
_AUTHORITY_PROVISIONING_MANIFEST_GLOBAL = (
    "C3_CLOSED_REPAIR_AUTHORITY_PROVISIONING_MANIFEST_CONTRACT_V2"
)
_AUTHORITY_PROVISIONING_RECEIPT_MODULE = (
    "trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authority_provisioning_receipt_contract_v2"
)
_AUTHORITY_PROVISIONING_RECEIPT_BUILDER = (
    "build_dormant_authority_provisioning_receipt_contract_v2"
)
_AUTHORITY_PROVISIONING_RECEIPT_GLOBAL = (
    "C3_CLOSED_REPAIR_AUTHORITY_PROVISIONING_RECEIPT_CONTRACT_V2"
)
_AUTHORITY_PROVISIONING_RECEIPT_AUTHENTICATED_VERIFIER_MODULE = (
    "trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authority_provisioning_receipt_authenticated_verifier_contract_v2"
)
_AUTHORITY_PROVISIONING_RECEIPT_AUTHENTICATED_VERIFIER_BUILDER = (
    "build_dormant_authenticated_provisioning_receipt_verifier_v2"
)
_AUTHORITY_PROVISIONING_RECEIPT_AUTHENTICATED_VERIFIER_GLOBAL = (
    "C3_CLOSED_REPAIR_AUTHORITY_PROVISIONING_RECEIPT_AUTHENTICATED_VERIFIER_V2"
)
_AUTHORITY_PROVISIONING_PHYSICAL_BINDING_MODULE = (
    "trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authority_provisioning_physical_binding_contract_v2"
)
_AUTHORITY_PROVISIONING_PHYSICAL_BINDING_BUILDER = (
    "build_dormant_authority_provisioning_physical_binding_contract_v2"
)
_AUTHORITY_PROVISIONING_PHYSICAL_BINDING_GLOBAL = (
    "C3_CLOSED_REPAIR_AUTHORITY_PROVISIONING_PHYSICAL_BINDING_CONTRACT_V2"
)
_REQUIRED_RUNTIME_MODULES = frozenset(
    {
        "trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1",
        "trade_registry_closed_identity_conflict_repair_writer_invocation_adapter_v1",
        _PRODUCTION_STORE_MODULE,
        _RESOLVED_AUTHORITY_STARTUP_BRIDGE_MODULE,
        _AUTHENTICATED_PERSISTENT_AUTHORITY_BOUNDARY_MODULE,
        _AUTHENTICATED_PERSISTENT_AUTHORITY_ADAPTERS_MODULE,
        _AUTHORITY_PROVISIONING_MANIFEST_MODULE,
        _AUTHORITY_PROVISIONING_RECEIPT_MODULE,
        _AUTHORITY_PROVISIONING_RECEIPT_AUTHENTICATED_VERIFIER_MODULE,
        _AUTHORITY_PROVISIONING_PHYSICAL_BINDING_MODULE,
    }
)
_PRODUCTION_CAPABILITY_SPECS = {
    "trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1": {
        "class_name": "ClosedRepairWriterRuntimeCoordinatorV1",
        "required_methods": frozenset({"maintenance_lease", "mutation", "snapshot"}),
        "builder_name": "build_production_closed_repair_writer_runtime_coordinator_v1",
    },
    "trade_registry_closed_identity_conflict_repair_writer_invocation_adapter_v1": {
        "class_name": "ProductionWriterInvocationAdapterV1",
        "required_methods": frozenset({"invoke"}),
        "builder_name": "build_production_writer_invocation_adapter_v1",
    },
    _PRODUCTION_STORE_MODULE: {
        "class_name": "ProductionRawTransactionStoreV1",
        "required_methods": frozenset(
            {
                "apply_attested_transaction",
                "load_exact_raw_registry",
                "reconcile_attested_transaction",
                "snapshot",
            }
        ),
        "builder_name": "build_production_raw_transaction_store_v1",
    },
}
_RESOLVED_AUTHORITY_CAPABILITY_SPECS = {
    _RESOLVED_AUTHORITY_PHYSICAL_STORE_MODULE: {
        "class_name": "ResolvedAuthorityPhysicalStoreReferenceV2",
        "required_methods": frozenset(
            {
                "open_offline",
                "recover_offline",
                "read_resolved_records_offline",
                "snapshot",
            }
        ),
        "builder_name": "build_dormant_resolved_authority_physical_store_reference_v2",
    },
    _RESOLVED_AUTHORITY_STARTUP_BRIDGE_MODULE: {
        "class_name": "ResolvedAuthorityStartupRecoveryBridgeV2",
        "required_methods": frozenset({"__call__", "snapshot"}),
        "builder_name": _RESOLVED_AUTHORITY_STARTUP_BRIDGE_BUILDER,
    },
    _AUTHENTICATED_PERSISTENT_AUTHORITY_BOUNDARY_MODULE: {
        "class_name": "AuthenticatedPersistentAuthorityBoundaryV2",
        "required_methods": frozenset({"__call__", "snapshot"}),
        "builder_name": _AUTHENTICATED_PERSISTENT_AUTHORITY_BOUNDARY_BUILDER,
    },
    _AUTHENTICATED_PERSISTENT_AUTHORITY_ADAPTERS_MODULE: {
        "class_name": "DormantAuthenticatedPersistentAuthorityProductionAdaptersV2",
        "required_methods": frozenset({"snapshot"}),
        "builder_name": _AUTHENTICATED_PERSISTENT_AUTHORITY_ADAPTERS_BUILDER,
    },
    _AUTHORITY_PROVISIONING_MANIFEST_MODULE: {
        "class_name": "DormantAuthorityProvisioningManifestContractV2",
        "required_methods": frozenset({"define_offline"}),
        "builder_name": _AUTHORITY_PROVISIONING_MANIFEST_BUILDER,
    },
    _AUTHORITY_PROVISIONING_RECEIPT_MODULE: {
        "class_name": "DormantAuthorityProvisioningReceiptContractV2",
        "required_methods": frozenset({"issue_offline"}),
        "builder_name": _AUTHORITY_PROVISIONING_RECEIPT_BUILDER,
    },
    _AUTHORITY_PROVISIONING_RECEIPT_AUTHENTICATED_VERIFIER_MODULE: {
        "class_name": "DormantAuthenticatedProvisioningReceiptVerifierV2",
        "required_methods": frozenset({"verify_offline"}),
        "builder_name": _AUTHORITY_PROVISIONING_RECEIPT_AUTHENTICATED_VERIFIER_BUILDER,
    },
    _AUTHORITY_PROVISIONING_PHYSICAL_BINDING_MODULE: {
        "class_name": "DormantAuthorityProvisioningPhysicalBindingContractV2",
        "required_methods": frozenset({"bind_offline"}),
        "builder_name": _AUTHORITY_PROVISIONING_PHYSICAL_BINDING_BUILDER,
    },
}
_RUNTIME_MODULE_SOURCE_KEYS = {
    module_name: f"{module_name}.py"
    for module_name in (
        set(_PRODUCTION_CAPABILITY_SPECS)
        | set(_RESOLVED_AUTHORITY_CAPABILITY_SPECS)
    )
}
_PRODUCTION_BUILDER_NAMES = frozenset(
    spec["builder_name"] for spec in _PRODUCTION_CAPABILITY_SPECS.values()
)
_BOT_WRITER_IMPORTS = frozenset(
    {"register_open_trade", "update_trade", "close_trade"}
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


def _source_sha256(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def _base_result() -> dict[str, Any]:
    return {
        "ok": False,
        "evaluation_complete": False,
        "static_readiness": False,
        "production_ready": False,
        "apply_allowed": False,
        "live_allowed": False,
        "status": "C3_RUNTIME_STATIC_PREFLIGHT_V1_BLOCKED",
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_STATIC_PREFLIGHT_V1_VERSION,
        "read_only": True,
        "offline_only": True,
        "ast_only": True,
        "runtime_imported": False,
        "runtime_executed": False,
        "write_executed": False,
        "registry_write": False,
        "network_accessed": False,
        "broker_called": False,
        "no_order_sent": True,
        "checks": [],
        "blockers": [],
        "source_attestations": {},
    }


def _function_nodes(tree: ast.AST) -> dict[str, list[ast.FunctionDef | ast.AsyncFunctionDef]]:
    result: dict[str, list[ast.FunctionDef | ast.AsyncFunctionDef]] = {}
    for node in getattr(tree, "body", ()):  # top-level definitions only
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            result.setdefault(node.name, []).append(node)
    return result


def _class_nodes(tree: ast.AST) -> dict[str, list[ast.ClassDef]]:
    result: dict[str, list[ast.ClassDef]] = {}
    for node in getattr(tree, "body", ()):
        if isinstance(node, ast.ClassDef):
            result.setdefault(node.name, []).append(node)
    return result


def _class_method_names(node: ast.ClassDef) -> set[str]:
    return {
        candidate.name
        for candidate in node.body
        if isinstance(candidate, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _production_capability_details(
    trees: Mapping[str, ast.Module],
    function_maps: Mapping[
        str, dict[str, list[ast.FunctionDef | ast.AsyncFunctionDef]]
    ],
    specs: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    details: dict[str, dict[str, Any]] = {}
    selected_specs = specs or _PRODUCTION_CAPABILITY_SPECS
    for module_name, spec in selected_specs.items():
        source_key = _RUNTIME_MODULE_SOURCE_KEYS[module_name]
        tree = trees[source_key]
        class_name = str(spec["class_name"])
        builder_name = str(spec["builder_name"])
        required_methods = set(spec["required_methods"])
        matching_classes = _class_nodes(tree).get(class_name, [])
        observed_methods = (
            _class_method_names(matching_classes[0])
            if len(matching_classes) == 1
            else set()
        )
        missing_methods = sorted(required_methods - observed_methods)
        builder_count = len(function_maps[source_key].get(builder_name, []))
        capable = bool(
            len(matching_classes) == 1
            and builder_count == 1
            and not missing_methods
        )
        details[module_name] = {
            "ok": capable,
            "source_key": source_key,
            "required_class": class_name,
            "required_builder": builder_name,
            "required_methods": sorted(required_methods),
            "class_definition_count": len(matching_classes),
            "builder_definition_count": builder_count,
            "missing_methods": missing_methods,
        }
    return details


def _signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    rendered = f"({ast.unparse(node.args)})"
    if node.returns is not None:
        rendered += f" -> {ast.unparse(node.returns)}"
    return rendered


def _normalized_signature_text(value: str) -> str:
    try:
        probe = ast.parse(f"def __c3_signature_probe__{value}:\n    pass\n")
        node = probe.body[0]
        if isinstance(node, ast.FunctionDef):
            return _signature(node)
    except (SyntaxError, ValueError, TypeError):
        pass
    return str(value)


def _called_names(node: ast.AST) -> set[str]:
    names: set[str] = set()
    for candidate in ast.walk(node):
        if not isinstance(candidate, ast.Call):
            continue
        if isinstance(candidate.func, ast.Name):
            names.add(candidate.func.id)
        elif isinstance(candidate.func, ast.Attribute):
            names.add(candidate.func.attr)
    return names


def _imported_modules(tree: ast.AST) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def _top_level_calls(tree: ast.Module) -> list[tuple[str, int]]:
    calls: list[tuple[str, int]] = []

    def visit_statement(node: ast.AST) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            return
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                calls.append((node.func.id, node.lineno))
            elif isinstance(node.func, ast.Attribute):
                calls.append((node.func.attr, node.lineno))
        for child in ast.iter_child_nodes(node):
            visit_statement(child)

    for statement in tree.body:
        visit_statement(statement)
    return calls


def _first_line(calls: list[tuple[str, int]], name: str) -> int | None:
    lines = [line for called, line in calls if called == name]
    return min(lines) if lines else None


def _bot_by_name_imports(tree: ast.AST) -> list[str]:
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "trade_registry":
            imported.extend(
                alias.name for alias in node.names if alias.name in _BOT_WRITER_IMPORTS
            )
    return sorted(imported)


def _c3_status_sample_names(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[tuple[str, int]]:
    samples: list[tuple[str, int]] = []
    for candidate in node.body:
        if not isinstance(candidate, ast.Assign) or len(candidate.targets) != 1:
            continue
        target = candidate.targets[0]
        value = candidate.value
        if not isinstance(target, ast.Name) or not isinstance(value, ast.Call):
            continue
        if value.args or value.keywords or not isinstance(value.func, ast.Attribute):
            continue
        if (
            isinstance(value.func.value, ast.Name)
            and value.func.value.id == "c3_runtime_seam_v1"
            and value.func.attr == "c3_closed_repair_writer_coordination_status_v1"
        ):
            samples.append((target.id, candidate.lineno))
    return samples


def _c3_readiness_comparison(
    node: ast.AST,
    *,
    status_name: str,
) -> tuple[str, Any] | None:
    if (
        not isinstance(node, ast.Compare)
        or len(node.ops) != 1
        or len(node.comparators) != 1
        or not isinstance(node.left, ast.Call)
    ):
        return None
    getter = node.left
    if (
        getter.keywords
        or len(getter.args) != 1
        or not isinstance(getter.func, ast.Attribute)
        or getter.func.attr != "get"
        or not isinstance(getter.func.value, ast.Name)
        or getter.func.value.id != status_name
        or not isinstance(getter.args[0], ast.Constant)
        or not isinstance(getter.args[0].value, str)
        or not isinstance(node.comparators[0], ast.Constant)
    ):
        return None
    field = getter.args[0].value
    expected = node.comparators[0].value
    if isinstance(expected, bool):
        if not isinstance(node.ops[0], ast.Is):
            return None
    elif type(expected) is int:
        if not isinstance(node.ops[0], ast.Eq):
            return None
    else:
        return None
    return field, expected


def _live_preflight_c3_semantics(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> dict[str, Any]:
    samples = _c3_status_sample_names(node)
    gate_calls = [
        statement.value
        for statement in node.body
        if isinstance(statement, ast.Expr)
        and isinstance(statement.value, ast.Call)
        and isinstance(statement.value.func, ast.Name)
        and statement.value.func.id == "add"
        and len(statement.value.args) >= 2
        and isinstance(statement.value.args[0], ast.Constant)
        and statement.value.args[0].value == _LIVE_PREFLIGHT_CHECK_CODE
    ]
    required = dict(_LIVE_PREFLIGHT_REQUIRED_C3_VECTOR)
    observed: dict[str, Any] = {}
    all_fields_conjunctive = False
    sampled_at_decision_time = False
    if len(samples) == 1 and len(gate_calls) == 1:
        status_name, sample_line = samples[0]
        gate = gate_calls[0]
        status_assignment_count = sum(
            1
            for candidate in ast.walk(node)
            if isinstance(candidate, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == status_name
                for target in candidate.targets
            )
        )
        predicate = gate.args[1]
        if isinstance(predicate, ast.BoolOp) and isinstance(predicate.op, ast.And):
            parsed = [
                _c3_readiness_comparison(item, status_name=status_name)
                for item in predicate.values
            ]
            if all(item is not None for item in parsed):
                pairs = [item for item in parsed if item is not None]
                observed = dict(pairs)
                all_fields_conjunctive = bool(
                    len(pairs) == len(required)
                    and len(observed) == len(pairs)
                    and observed == required
                )
        sampled_at_decision_time = (
            sample_line < gate.lineno and status_assignment_count == 1
        )
    ok = bool(
        len(samples) == 1
        and len(gate_calls) == 1
        and all_fields_conjunctive
        and sampled_at_decision_time
    )
    return {
        "ok": ok,
        "required_fields": list(required),
        "observed_fields": list(observed),
        "status_sample_count": len(samples),
        "gate_call_count": len(gate_calls),
        "all_fields_conjunctive": all_fields_conjunctive,
        "sampled_at_decision_time": sampled_at_decision_time,
        "generic_ok_insufficient": True,
    }


def evaluate_closed_repair_runtime_static_preflight_v1(
    sources: Mapping[str, str],
) -> dict[str, Any]:
    """Evaluate runtime source text and always keep production/Live denied."""

    result = _base_result()
    if not isinstance(sources, Mapping):
        result["blockers"] = ["SOURCE_MAPPING_REQUIRED"]
        return result
    supplied_keys = sorted(str(key) for key in sources)
    if supplied_keys != sorted(REQUIRED_SOURCE_KEYS_V1):
        result["blockers"] = ["EXACT_SOURCE_SET_REQUIRED"]
        return result
    if any(not isinstance(sources[key], str) or "\x00" in sources[key] for key in REQUIRED_SOURCE_KEYS_V1):
        result["blockers"] = ["SOURCE_TEXT_INVALID"]
        return result
    try:
        trees = {
            key: ast.parse(sources[key], filename=key)
            for key in REQUIRED_SOURCE_KEYS_V1
        }
    except (SyntaxError, ValueError, TypeError):
        result["blockers"] = ["SOURCE_AST_PARSE_FAILED"]
        return result

    checks: list[dict[str, Any]] = []

    def add(code: str, ok: bool, **details: Any) -> None:
        checks.append({"code": code, "ok": bool(ok), "details": details})

    inventory = coordination.canonical_closed_repair_writer_inventory_v1()
    bindings = seam_contract.canonical_writer_seam_bindings_v1(
        {"participation_receipt_sha256": "0" * 64}
    )
    function_maps = {
        key: _function_nodes(trees[key]) for key in REQUIRED_SOURCE_KEYS_V1
    }
    discovered: list[str] = []
    missing: list[str] = []
    duplicate: list[str] = []
    signature_mismatches: list[str] = []
    anchor_mismatches: list[str] = []
    uncoordinated: list[str] = []
    for writer, binding in zip(inventory, bindings, strict=True):
        component = writer["component"]
        function = writer["function"]
        writer_id = writer["writer_id"]
        nodes = function_maps.get(component, {}).get(function, [])
        if not nodes:
            missing.append(writer_id)
            continue
        if len(nodes) != 1:
            duplicate.append(writer_id)
            continue
        node = nodes[0]
        discovered.append(writer_id)
        if _signature(node) != _normalized_signature_text(
            binding["source_signature"]
        ):
            signature_mismatches.append(writer_id)
        if node.lineno != binding["source_anchor_line"]:
            anchor_mismatches.append(writer_id)
        if _WRITER_MUTATION_MARKER not in _called_names(node):
            uncoordinated.append(writer_id)

    add(
        "EXACT_19_WRITER_FUNCTIONS_PRESENT",
        len(discovered) == 19 and not missing and not duplicate,
        discovered_count=len(discovered),
        missing_writer_ids=missing,
        duplicate_writer_ids=duplicate,
    )
    add(
        "WRITER_SIGNATURES_MATCH_AUDITED_CONTRACT",
        not signature_mismatches,
        mismatch_writer_ids=signature_mismatches,
    )
    add(
        "WRITER_SOURCE_ANCHORS_MATCH_AUDITED_CONTRACT",
        not anchor_mismatches,
        mismatch_writer_ids=anchor_mismatches,
    )
    add(
        "ALL_19_WRITER_BODY_SEAMS_COORDINATED",
        len(uncoordinated) == 0 and len(discovered) == 19,
        coordinated_count=len(discovered) - len(uncoordinated),
        uncoordinated_writer_ids=uncoordinated,
        required_marker=_WRITER_MUTATION_MARKER,
    )

    main_tree = trees["main.py"]
    main_imports = _imported_modules(main_tree)
    trade_registry_imports = _imported_modules(trees["trade_registry.py"])
    runtime_imports = main_imports | trade_registry_imports
    missing_runtime_imports = sorted(_REQUIRED_RUNTIME_MODULES - runtime_imports)
    production_capabilities = _production_capability_details(
        trees, function_maps
    )
    resolved_authority_capabilities = _production_capability_details(
        trees,
        function_maps,
        _RESOLVED_AUTHORITY_CAPABILITY_SPECS,
    )
    incapable_runtime_modules = sorted(
        module_name
        for module_name, capability in production_capabilities.items()
        if capability["ok"] is not True
    )
    add(
        "C3_RUNTIME_DEPENDENCIES_IMPORTED",
        not missing_runtime_imports,
        missing_modules=missing_runtime_imports,
    )
    add(
        "C3_RUNTIME_DEPENDENCIES_PRODUCTION_CAPABLE",
        not incapable_runtime_modules,
        incapable_modules=incapable_runtime_modules,
        capabilities=production_capabilities,
    )
    incapable_resolved_authority_modules = sorted(
        module_name
        for module_name, capability in resolved_authority_capabilities.items()
        if capability["ok"] is not True
    )
    add(
        "C3_RESOLVED_AUTHORITY_PHYSICAL_REFERENCE_CAPABLE",
        not incapable_resolved_authority_modules,
        incapable_modules=incapable_resolved_authority_modules,
        capabilities=resolved_authority_capabilities,
        temporary_synthetic_reference_only=True,
        production_ready=False,
    )
    production_store_capable = production_capabilities[
        _PRODUCTION_STORE_MODULE
    ]["ok"] is True
    add(
        "PRODUCTION_TRANSACTION_STORE_PRESENT",
        _PRODUCTION_STORE_MODULE in runtime_imports
        and production_store_capable,
        required_module=_PRODUCTION_STORE_MODULE,
        module_imported=_PRODUCTION_STORE_MODULE in runtime_imports,
        production_capability_valid=production_store_capable,
    )

    top_calls = _top_level_calls(main_tree)
    runtime_line = _first_line(top_calls, "start_central_runtime_once")
    persistence_line = _first_line(
        top_calls, "trade_registry_persistent_storage_fix_v1_status"
    )
    provider_line = _first_line(top_calls, _PROVIDER_INSTALL_MARKER)
    recovery_line = _first_line(top_calls, _STARTUP_RECOVERY_MARKER)
    resolved_bridge_builder_line = _first_line(
        top_calls, _RESOLVED_AUTHORITY_STARTUP_BRIDGE_BUILDER
    )
    authenticated_boundary_builder_line = _first_line(
        top_calls, _AUTHENTICATED_PERSISTENT_AUTHORITY_BOUNDARY_BUILDER
    )
    authenticated_adapters_builder_line = _first_line(
        top_calls, _AUTHENTICATED_PERSISTENT_AUTHORITY_ADAPTERS_BUILDER
    )
    provisioning_manifest_builder_line = _first_line(
        top_calls, _AUTHORITY_PROVISIONING_MANIFEST_BUILDER
    )
    provisioning_receipt_builder_line = _first_line(
        top_calls, _AUTHORITY_PROVISIONING_RECEIPT_BUILDER
    )
    authenticated_receipt_verifier_builder_line = _first_line(
        top_calls, _AUTHORITY_PROVISIONING_RECEIPT_AUTHENTICATED_VERIFIER_BUILDER
    )
    physical_binding_builder_line = _first_line(
        top_calls, _AUTHORITY_PROVISIONING_PHYSICAL_BINDING_BUILDER
    )
    provider_nodes = function_maps["main.py"].get(
        _PROVIDER_INSTALL_MARKER, []
    )
    provider_called_builders = (
        _called_names(provider_nodes[0]) & _PRODUCTION_BUILDER_NAMES
        if len(provider_nodes) == 1
        else set()
    )
    add(
        "PERSISTENCE_BOOTSTRAP_BEFORE_RUNTIME_START",
        persistence_line is not None
        and runtime_line is not None
        and persistence_line < runtime_line,
        persistence_bootstrap_line=persistence_line,
        runtime_start_line=runtime_line,
    )
    add(
        "C3_PROVIDER_INSTALLED_BEFORE_RUNTIME_START",
        provider_line is not None
        and runtime_line is not None
        and provider_line < runtime_line,
        provider_install_line=provider_line,
        runtime_start_line=runtime_line,
        required_marker=_PROVIDER_INSTALL_MARKER,
    )
    add(
        "C3_PROVIDER_BINDS_PRODUCTION_CAPABILITIES",
        len(provider_nodes) == 1
        and provider_called_builders == _PRODUCTION_BUILDER_NAMES
        and not incapable_runtime_modules,
        provider_definition_count=len(provider_nodes),
        required_builders=sorted(_PRODUCTION_BUILDER_NAMES),
        called_builders=sorted(provider_called_builders),
        incapable_modules=incapable_runtime_modules,
    )
    add(
        "C3_STARTUP_RECOVERY_BEFORE_RUNTIME_START",
        provider_line is not None
        and recovery_line is not None
        and runtime_line is not None
        and provider_line < recovery_line < runtime_line,
        provider_install_line=provider_line,
        recovery_line=recovery_line,
        runtime_start_line=runtime_line,
        required_marker=_STARTUP_RECOVERY_MARKER,
    )

    bridge_assignments = [
        node
        for node in main_tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name)
            and target.id == _RESOLVED_AUTHORITY_STARTUP_BRIDGE_GLOBAL
            for target in node.targets
        )
    ]
    boundary_assignments = [
        node
        for node in main_tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name)
            and target.id == _AUTHENTICATED_PERSISTENT_AUTHORITY_BOUNDARY_GLOBAL
            for target in node.targets
        )
    ]
    adapters_assignments = [
        node
        for node in main_tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name)
            and target.id == _AUTHENTICATED_PERSISTENT_AUTHORITY_ADAPTERS_GLOBAL
            for target in node.targets
        )
    ]
    manifest_assignments = [
        node
        for node in main_tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name)
            and target.id == _AUTHORITY_PROVISIONING_MANIFEST_GLOBAL
            for target in node.targets
        )
    ]
    receipt_assignments = [
        node
        for node in main_tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name)
            and target.id == _AUTHORITY_PROVISIONING_RECEIPT_GLOBAL
            for target in node.targets
        )
    ]
    authenticated_receipt_verifier_assignments = [
        node
        for node in main_tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name)
            and target.id
            == _AUTHORITY_PROVISIONING_RECEIPT_AUTHENTICATED_VERIFIER_GLOBAL
            for target in node.targets
        )
    ]
    physical_binding_assignments = [
        node
        for node in main_tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name)
            and target.id == _AUTHORITY_PROVISIONING_PHYSICAL_BINDING_GLOBAL
            for target in node.targets
        )
    ]
    recovery_assignments = [
        node
        for node in main_tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name)
            and target.id == "C3_CLOSED_REPAIR_STARTUP_RECOVERY_V1"
            for target in node.targets
        )
    ]
    installation_assignments = [
        node
        for node in main_tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name)
            and target.id == "C3_CLOSED_REPAIR_INSTALLATION_V1"
            for target in node.targets
        )
    ]
    bridge_builder_bound = False
    if len(bridge_assignments) == 1:
        value = bridge_assignments[0].value
        bridge_builder_bound = bool(
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Attribute)
            and value.func.attr == _RESOLVED_AUTHORITY_STARTUP_BRIDGE_BUILDER
            and not value.args
            and not value.keywords
        )
    recovery_bridge_bound = False
    adapters_builder_bound = False
    if len(adapters_assignments) == 1:
        value = adapters_assignments[0].value
        adapters_builder_bound = bool(
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Attribute)
            and value.func.attr == _AUTHENTICATED_PERSISTENT_AUTHORITY_ADAPTERS_BUILDER
            and not value.args
            and not value.keywords
        )
    manifest_builder_bound = False
    if len(manifest_assignments) == 1:
        value = manifest_assignments[0].value
        manifest_builder_bound = bool(
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Attribute)
            and value.func.attr == _AUTHORITY_PROVISIONING_MANIFEST_BUILDER
            and not value.args
            and not value.keywords
        )
    receipt_builder_bound = False
    if len(receipt_assignments) == 1:
        value = receipt_assignments[0].value
        receipt_builder_bound = bool(
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Attribute)
            and value.func.attr == _AUTHORITY_PROVISIONING_RECEIPT_BUILDER
            and not value.args
            and not value.keywords
        )
    authenticated_receipt_verifier_builder_bound = False
    if len(authenticated_receipt_verifier_assignments) == 1:
        value = authenticated_receipt_verifier_assignments[0].value
        authenticated_receipt_verifier_builder_bound = bool(
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Attribute)
            and value.func.attr
            == _AUTHORITY_PROVISIONING_RECEIPT_AUTHENTICATED_VERIFIER_BUILDER
            and not value.args
            and not value.keywords
        )
    physical_binding_builder_bound = False
    if len(physical_binding_assignments) == 1:
        value = physical_binding_assignments[0].value
        physical_binding_builder_bound = bool(
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Attribute)
            and value.func.attr == _AUTHORITY_PROVISIONING_PHYSICAL_BINDING_BUILDER
            and not value.args
            and not value.keywords
        )
    boundary_builder_bound = False
    if len(boundary_assignments) == 1 and adapters_builder_bound:
        value = boundary_assignments[0].value
        if (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Attribute)
            and value.func.attr
            == _AUTHENTICATED_PERSISTENT_AUTHORITY_BOUNDARY_BUILDER
            and not value.args
        ):
            keywords = {item.arg: item.value for item in value.keywords}
            adapter_attributes = {
                "root_state_provider": "root_state_provider",
                "root_authority_verifier": "root_authority_verifier",
                "root_revocation_source": "root_revocation_source",
                "multistore_recovery": "multistore_recovery",
            }
            boundary_builder_bound = bool(
                set(keywords) == set(adapter_attributes) | {"startup_bridge"}
                and all(
                    isinstance(keywords[name], ast.Attribute)
                    and keywords[name].attr == attribute
                    and isinstance(keywords[name].value, ast.Name)
                    and keywords[name].value.id
                    == _AUTHENTICATED_PERSISTENT_AUTHORITY_ADAPTERS_GLOBAL
                    for name, attribute in adapter_attributes.items()
                )
                and isinstance(keywords["startup_bridge"], ast.Name)
                and keywords["startup_bridge"].id
                == _RESOLVED_AUTHORITY_STARTUP_BRIDGE_GLOBAL
            )
    provider_recovery_binding_bound = False
    if len(provider_nodes) == 1:
        binding_calls = [
            node
            for node in ast.walk(provider_nodes[0])
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr
            == "bind_c3_closed_repair_runtime_interlocks_v1"
        ]
        if len(binding_calls) == 1:
            call = binding_calls[0]
            keywords = {item.arg: item.value for item in call.keywords}
            provider_recovery_binding_bound = bool(
                len(call.args) == 1
                and isinstance(call.args[0], ast.Name)
                and call.args[0].id == "coordinator"
                and set(keywords) == {"startup_recovery"}
                and isinstance(keywords["startup_recovery"], ast.Name)
                and keywords["startup_recovery"].id == "startup_recovery"
            )
    installation_authority_bound = False
    if len(installation_assignments) == 1 and boundary_builder_bound:
        value = installation_assignments[0].value
        if (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Name)
            and value.func.id == _PROVIDER_INSTALL_MARKER
            and not value.args
        ):
            keywords = {item.arg: item.value for item in value.keywords}
            installation_authority_bound = bool(
                set(keywords) == {"startup_recovery"}
                and isinstance(keywords["startup_recovery"], ast.Name)
                and keywords["startup_recovery"].id
                == _AUTHENTICATED_PERSISTENT_AUTHORITY_BOUNDARY_GLOBAL
            )
    if len(recovery_assignments) == 1 and installation_authority_bound:
        value = recovery_assignments[0].value
        if (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Name)
            and value.func.id == _STARTUP_RECOVERY_MARKER
            and not value.args
            and not value.keywords
        ):
            recovery_bridge_bound = bool(
                provider_recovery_binding_bound
                and installation_authority_bound
            )
    add(
        "C3_RESOLVED_AUTHORITY_STARTUP_BRIDGE_BOUND_DEFAULT_OFF",
        _RESOLVED_AUTHORITY_STARTUP_BRIDGE_MODULE in main_imports
        and _AUTHENTICATED_PERSISTENT_AUTHORITY_BOUNDARY_MODULE in main_imports
        and _AUTHENTICATED_PERSISTENT_AUTHORITY_ADAPTERS_MODULE in main_imports
        and _AUTHORITY_PROVISIONING_MANIFEST_MODULE in main_imports
        and _AUTHORITY_PROVISIONING_RECEIPT_MODULE in main_imports
        and _AUTHORITY_PROVISIONING_RECEIPT_AUTHENTICATED_VERIFIER_MODULE
        in main_imports
        and _AUTHORITY_PROVISIONING_PHYSICAL_BINDING_MODULE in main_imports
        and bridge_builder_bound
        and adapters_builder_bound
        and manifest_builder_bound
        and receipt_builder_bound
        and authenticated_receipt_verifier_builder_bound
        and physical_binding_builder_bound
        and boundary_builder_bound
        and provider_recovery_binding_bound
        and installation_authority_bound
        and recovery_bridge_bound
        and resolved_bridge_builder_line is not None
        and authenticated_adapters_builder_line is not None
        and provisioning_manifest_builder_line is not None
        and provisioning_receipt_builder_line is not None
        and authenticated_receipt_verifier_builder_line is not None
        and physical_binding_builder_line is not None
        and authenticated_boundary_builder_line is not None
        and provider_line is not None
        and recovery_line is not None
        and runtime_line is not None
        and resolved_bridge_builder_line
        < authenticated_adapters_builder_line
        < provisioning_manifest_builder_line
        < provisioning_receipt_builder_line
        < authenticated_receipt_verifier_builder_line
        < physical_binding_builder_line
        < authenticated_boundary_builder_line
        < provider_line
        < recovery_line
        < runtime_line,
        module_imported=(
            _RESOLVED_AUTHORITY_STARTUP_BRIDGE_MODULE in main_imports
        ),
        bridge_assignment_count=len(bridge_assignments),
        adapters_assignment_count=len(adapters_assignments),
        manifest_assignment_count=len(manifest_assignments),
        receipt_assignment_count=len(receipt_assignments),
        authenticated_receipt_verifier_assignment_count=len(
            authenticated_receipt_verifier_assignments
        ),
        physical_binding_assignment_count=len(physical_binding_assignments),
        boundary_assignment_count=len(boundary_assignments),
        installation_assignment_count=len(installation_assignments),
        recovery_assignment_count=len(recovery_assignments),
        bridge_builder_bound=bridge_builder_bound,
        production_adapters_builder_bound=adapters_builder_bound,
        provisioning_manifest_builder_bound=manifest_builder_bound,
        provisioning_receipt_builder_bound=receipt_builder_bound,
        authenticated_receipt_verifier_builder_bound=(
            authenticated_receipt_verifier_builder_bound
        ),
        physical_binding_builder_bound=physical_binding_builder_bound,
        authenticated_boundary_builder_bound=boundary_builder_bound,
        provider_recovery_binding_bound=provider_recovery_binding_bound,
        installation_authority_bound=installation_authority_bound,
        recovery_bridge_bound=recovery_bridge_bound,
        bridge_builder_line=resolved_bridge_builder_line,
        authenticated_boundary_builder_line=authenticated_boundary_builder_line,
        recovery_line=recovery_line,
        runtime_start_line=runtime_line,
        default_off_required=True,
    )

    bot_imports = {
        key: _bot_by_name_imports(trees[key])
        for key in ("bots/meme.py", "bots/predator.py", "bots/turtle.py")
    }
    bot_import_shape_valid = all(
        imported == sorted(_BOT_WRITER_IMPORTS)
        for imported in bot_imports.values()
    )
    bot_imports_safe = bool(
        bot_import_shape_valid
        and provider_line is not None
        and runtime_line is not None
        and provider_line < runtime_line
        and not uncoordinated
    )
    add(
        "BY_NAME_BOT_WRITER_IMPORTS_GATED",
        bot_imports_safe,
        imports=bot_imports,
        import_shape_valid=bot_import_shape_valid,
    )

    preflight_nodes = function_maps["main.py"].get(
        "_frpp_v1_build_checklist", []
    )
    preflight_c3_semantics = (
        _live_preflight_c3_semantics(preflight_nodes[0])
        if len(preflight_nodes) == 1
        else {
            "ok": False,
            "required_fields": [
                field for field, _ in _LIVE_PREFLIGHT_REQUIRED_C3_VECTOR
            ],
            "observed_fields": [],
            "status_sample_count": 0,
            "gate_call_count": 0,
            "all_fields_conjunctive": False,
            "sampled_at_decision_time": False,
            "generic_ok_insufficient": True,
        }
    )
    add(
        "LIVE_PREFLIGHT_REQUIRES_C3_COORDINATION",
        preflight_c3_semantics["ok"] is True,
        required_check_code=_LIVE_PREFLIGHT_CHECK_CODE,
        required_vector=dict(_LIVE_PREFLIGHT_REQUIRED_C3_VECTOR),
        semantic_evidence=preflight_c3_semantics,
    )

    coordinator_functions = function_maps[
        "trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1.py"
    ]
    add(
        "STALE_MAINTENANCE_LEASE_RECOVERY_POLICY_PRESENT",
        len(coordinator_functions.get(_STALE_LEASE_RECOVERY_MARKER, [])) == 1,
        required_function=_STALE_LEASE_RECOVERY_MARKER,
    )

    blockers = [item["code"] for item in checks if item["ok"] is not True]
    static_readiness = not blockers
    result.update(
        {
            "ok": static_readiness,
            "evaluation_complete": True,
            "static_readiness": static_readiness,
            "status": (
                "C3_RUNTIME_STATIC_PREFLIGHT_V1_SATISFIED_OFFLINE_NO_ACTIVATION"
                if static_readiness
                else "C3_RUNTIME_STATIC_PREFLIGHT_V1_BLOCKED"
            ),
            "checks": checks,
            "blockers": blockers,
            "writer_summary": {
                "expected_count": 19,
                "discovered_count": len(discovered),
                "signature_mismatch_count": len(signature_mismatches),
                "anchor_mismatch_count": len(anchor_mismatches),
                "coordinated_count": len(discovered) - len(uncoordinated),
            },
            "source_attestations": {
                key: {
                    "sha256": _source_sha256(sources[key]),
                    "size_bytes": len(sources[key].encode("utf-8")),
                }
                for key in REQUIRED_SOURCE_KEYS_V1
            },
        }
    )
    return result


__all__ = [
    "REQUIRED_SOURCE_KEYS_V1",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_STATIC_PREFLIGHT_V1_VERSION",
    "evaluate_closed_repair_runtime_static_preflight_v1",
]
