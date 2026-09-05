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
)

_WRITER_MUTATION_MARKER = "_c3_closed_repair_writer_mutation_v1"
_PROVIDER_INSTALL_MARKER = "_install_c3_closed_repair_writer_coordination_v1"
_STARTUP_RECOVERY_MARKER = "_recover_c3_closed_repair_registry_v1"
_STALE_LEASE_RECOVERY_MARKER = "recover_stale_maintenance_lease_v1"
_LIVE_PREFLIGHT_CHECK_CODE = "TRADE_REGISTRY_C3_WRITER_COORDINATION_READY"
_PRODUCTION_STORE_MODULE = (
    "trade_registry_closed_identity_conflict_repair_raw_transaction_store_production_v1"
)
_REQUIRED_RUNTIME_MODULES = frozenset(
    {
        "trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1",
        "trade_registry_closed_identity_conflict_repair_writer_invocation_adapter_v1",
        _PRODUCTION_STORE_MODULE,
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
_RUNTIME_MODULE_SOURCE_KEYS = {
    module_name: f"{module_name}.py" for module_name in _REQUIRED_RUNTIME_MODULES
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
) -> dict[str, dict[str, Any]]:
    details: dict[str, dict[str, Any]] = {}
    for module_name, spec in _PRODUCTION_CAPABILITY_SPECS.items():
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


def _string_literals(node: ast.AST) -> set[str]:
    return {
        candidate.value
        for candidate in ast.walk(node)
        if isinstance(candidate, ast.Constant)
        and isinstance(candidate.value, str)
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
    preflight_has_c3 = bool(
        len(preflight_nodes) == 1
        and _LIVE_PREFLIGHT_CHECK_CODE in _string_literals(preflight_nodes[0])
    )
    add(
        "LIVE_PREFLIGHT_REQUIRES_C3_COORDINATION",
        preflight_has_c3,
        required_check_code=_LIVE_PREFLIGHT_CHECK_CODE,
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
