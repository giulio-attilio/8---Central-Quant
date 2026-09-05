from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

import trade_registry_closed_identity_conflict_repair_runtime_static_preflight_harness_v1 as harness
import trade_registry_closed_identity_conflict_repair_runtime_static_preflight_v1 as preflight
import trade_registry_closed_identity_conflict_repair_writer_seam_binding_contract_v1 as seam_contract


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def current_harness_result() -> dict:
    return harness.run_closed_repair_runtime_static_preflight_harness_v1(ROOT)


def _minimal_sources() -> dict[str, str]:
    bindings = seam_contract.canonical_writer_seam_bindings_v1(
        {"participation_receipt_sha256": "0" * 64}
    )
    component_lines: dict[str, list[str]] = {key: [] for key in preflight.REQUIRED_SOURCE_KEYS_V1}
    for binding in bindings:
        writer = binding["writer"]
        component_lines[writer["component"]].extend(
            [
                f"def {writer['function']}{binding['source_signature']}:",
                "    pass",
                "",
            ]
        )
    component_lines["main.py"].extend(
        [
            "def start_central_runtime_once():",
            "    pass",
            "",
            "def trade_registry_persistent_storage_fix_v1_status(force=False):",
            "    pass",
            "",
            "def _frpp_v1_build_checklist():",
            "    return []",
            "",
            "start_central_runtime_once()",
        ]
    )
    for bot in ("bots/meme.py", "bots/predator.py", "bots/turtle.py"):
        component_lines[bot].append(
            "from trade_registry import register_open_trade, update_trade, close_trade"
        )
    component_lines[
        "trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1.py"
    ].extend(["def placeholder():", "    pass"])
    return {key: "\n".join(lines) + "\n" for key, lines in component_lines.items()}


def _check(result: dict, code: str) -> dict:
    return next(item for item in result["checks"] if item["code"] == code)


def test_current_sources_have_static_readiness_without_runtime_execution(
    current_harness_result: dict,
) -> None:
    result = current_harness_result["preflight_result"]
    assert current_harness_result["ok"] is True
    assert current_harness_result["static_readiness"] is True
    assert result["evaluation_complete"] is True
    assert result["ok"] is True
    assert result["production_ready"] is False
    assert result["live_allowed"] is False
    assert result["runtime_imported"] is False
    assert result["runtime_executed"] is False
    assert result["write_executed"] is False
    assert result["no_order_sent"] is True


def test_current_inventory_and_audited_signatures_still_match(
    current_harness_result: dict,
) -> None:
    result = current_harness_result["preflight_result"]
    assert result["writer_summary"] == {
        "expected_count": 19,
        "discovered_count": 19,
        "signature_mismatch_count": 0,
        "anchor_mismatch_count": 0,
        "coordinated_count": 19,
    }
    assert _check(result, "EXACT_19_WRITER_FUNCTIONS_PRESENT")["ok"] is True
    assert _check(result, "WRITER_SIGNATURES_MATCH_AUDITED_CONTRACT")["ok"] is True
    assert _check(result, "WRITER_SOURCE_ANCHORS_MATCH_AUDITED_CONTRACT")["ok"] is True


def test_current_sources_cover_startup_writers_recovery_store_and_live_preflight(
    current_harness_result: dict,
) -> None:
    result = current_harness_result["preflight_result"]
    assert result["blockers"] == []
    assert all(item["ok"] is True for item in result["checks"])
    assert result["production_ready"] is False
    assert result["live_allowed"] is False


def test_current_startup_order_is_reported_without_executing_main(
    current_harness_result: dict,
) -> None:
    result = current_harness_result["preflight_result"]
    order = _check(result, "PERSISTENCE_BOOTSTRAP_BEFORE_RUNTIME_START")
    assert order["ok"] is True
    assert order["details"]["persistence_bootstrap_line"] < order["details"]["runtime_start_line"]


def test_source_attestations_expose_only_hash_and_size(
    current_harness_result: dict,
) -> None:
    attestations = current_harness_result["preflight_result"]["source_attestations"]
    assert set(attestations) == set(preflight.REQUIRED_SOURCE_KEYS_V1)
    assert all(set(value) == {"sha256", "size_bytes"} for value in attestations.values())
    assert all(len(value["sha256"]) == 64 for value in attestations.values())
    assert all(value["size_bytes"] > 0 for value in attestations.values())


def test_missing_source_fails_closed_before_ast_evaluation() -> None:
    sources = _minimal_sources()
    sources.pop("main.py")
    result = preflight.evaluate_closed_repair_runtime_static_preflight_v1(sources)
    assert result["ok"] is False
    assert result["evaluation_complete"] is False
    assert result["blockers"] == ["EXACT_SOURCE_SET_REQUIRED"]


def test_invalid_syntax_fails_closed_without_partial_result() -> None:
    sources = {key: "\n" for key in preflight.REQUIRED_SOURCE_KEYS_V1}
    sources["main.py"] = "def incomplete(:\n"
    result = preflight.evaluate_closed_repair_runtime_static_preflight_v1(sources)
    assert result["ok"] is False
    assert result["evaluation_complete"] is False
    assert result["blockers"] == ["SOURCE_AST_PARSE_FAILED"]


def test_missing_writer_is_reported_from_ast_not_text_search() -> None:
    sources = _minimal_sources()
    sources["trade_registry.py"] = sources["trade_registry.py"].replace(
        "def load_registry()", "def load_registry_removed()", 1
    )
    result = preflight.evaluate_closed_repair_runtime_static_preflight_v1(sources)
    check = _check(result, "EXACT_19_WRITER_FUNCTIONS_PRESENT")
    assert result["evaluation_complete"] is True
    assert check["ok"] is False
    assert "TRADE_REGISTRY_LOAD_INITIALIZE_OR_MIGRATE" in check["details"][
        "missing_writer_ids"
    ]


def test_marker_names_in_comments_do_not_satisfy_ast_checks() -> None:
    sources = _minimal_sources()
    sources["main.py"] += "\n# _install_c3_closed_repair_writer_coordination_v1()\n"
    sources["main.py"] += "# _recover_c3_closed_repair_registry_v1()\n"
    sources["main.py"] += "# TRADE_REGISTRY_C3_WRITER_COORDINATION_READY\n"
    result = preflight.evaluate_closed_repair_runtime_static_preflight_v1(sources)
    assert _check(result, "C3_PROVIDER_INSTALLED_BEFORE_RUNTIME_START")["ok"] is False
    assert _check(result, "C3_STARTUP_RECOVERY_BEFORE_RUNTIME_START")["ok"] is False
    assert _check(result, "LIVE_PREFLIGHT_REQUIRES_C3_COORDINATION")["ok"] is False


def test_importing_dormant_modules_cannot_create_false_production_readiness() -> None:
    sources = harness.load_closed_repair_runtime_sources_read_only_v1(ROOT)
    imports = "\n".join(
        f"import {module_name}"
        for module_name in sorted(preflight._REQUIRED_RUNTIME_MODULES)
    )
    sources["main.py"] = imports + "\n" + sources["main.py"]
    result = preflight.evaluate_closed_repair_runtime_static_preflight_v1(sources)
    imported = _check(result, "C3_RUNTIME_DEPENDENCIES_IMPORTED")
    capable = _check(result, "C3_RUNTIME_DEPENDENCIES_PRODUCTION_CAPABLE")
    store = _check(result, "PRODUCTION_TRANSACTION_STORE_PRESENT")
    provider = _check(result, "C3_PROVIDER_BINDS_PRODUCTION_CAPABILITIES")
    assert imported["ok"] is True
    assert capable["ok"] is True
    assert capable["details"]["incapable_modules"] == []
    assert store["ok"] is True
    assert store["details"]["module_imported"] is True
    assert store["details"]["production_capability_valid"] is True
    assert provider["ok"] is True
    assert result["static_readiness"] is False
    assert result["production_ready"] is False
    assert result["live_allowed"] is False


def test_exact_production_shapes_are_required_in_addition_to_imports() -> None:
    sources = _minimal_sources()
    coordinator_module = (
        "trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1"
    )
    invocation_module = (
        "trade_registry_closed_identity_conflict_repair_writer_invocation_adapter_v1"
    )
    store_module = (
        "trade_registry_closed_identity_conflict_repair_raw_transaction_store_production_v1"
    )
    sources[f"{coordinator_module}.py"] = """
class ClosedRepairWriterRuntimeCoordinatorV1:
    def maintenance_lease(self): pass
    def mutation(self): pass
    def snapshot(self): pass
def build_production_closed_repair_writer_runtime_coordinator_v1(): pass
def recover_stale_maintenance_lease_v1(): pass
"""
    sources[f"{invocation_module}.py"] = """
class ProductionWriterInvocationAdapterV1:
    def invoke(self): pass
def build_production_writer_invocation_adapter_v1(): pass
"""
    sources[f"{store_module}.py"] = """
class ProductionRawTransactionStoreV1:
    def apply_attested_transaction(self): pass
    def load_exact_raw_registry(self): pass
    def reconcile_attested_transaction(self): pass
    def snapshot(self): pass
def build_production_raw_transaction_store_v1(): pass
"""
    imports = "\n".join(
        f"import {module_name}" for module_name in sorted(preflight._REQUIRED_RUNTIME_MODULES)
    )
    provider = """
def _install_c3_closed_repair_writer_coordination_v1():
    build_production_closed_repair_writer_runtime_coordinator_v1()
    build_production_writer_invocation_adapter_v1()
    build_production_raw_transaction_store_v1()
"""
    sources["main.py"] = imports + provider + sources["main.py"].replace(
        "\nstart_central_runtime_once()\n",
        "\n_install_c3_closed_repair_writer_coordination_v1()\nstart_central_runtime_once()\n",
        1,
    )
    result = preflight.evaluate_closed_repair_runtime_static_preflight_v1(sources)
    assert _check(result, "C3_RUNTIME_DEPENDENCIES_IMPORTED")["ok"] is True
    assert _check(result, "C3_RUNTIME_DEPENDENCIES_PRODUCTION_CAPABLE")["ok"] is True
    assert _check(result, "PRODUCTION_TRANSACTION_STORE_PRESENT")["ok"] is True
    assert _check(result, "C3_PROVIDER_BINDS_PRODUCTION_CAPABILITIES")["ok"] is True
    assert result["production_ready"] is False
    assert result["live_allowed"] is False


def test_loader_rejects_oversized_allowlisted_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for relative in preflight.REQUIRED_SOURCE_KEYS_V1:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("pass\n", encoding="utf-8")
    (tmp_path / "main.py").write_text("0123456789", encoding="utf-8")
    monkeypatch.setattr(harness, "_MAX_SOURCE_BYTES", 8)
    with pytest.raises(
        harness.RuntimeStaticPreflightSourceBlocked,
        match="SOURCE_SIZE_LIMIT_EXCEEDED",
    ):
        harness.load_closed_repair_runtime_sources_read_only_v1(tmp_path)


def test_preflight_modules_import_no_runtime_network_or_broker() -> None:
    modules = (preflight, harness)
    imported = {
        alias.name
        for module in modules
        for node in ast.walk(ast.parse(inspect.getsource(module)))
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert "main" not in imported
    assert "trade_registry" not in imported
    assert "broker" not in imported
    source = "\n".join(inspect.getsource(module).lower() for module in modules)
    assert all(
        token not in source
        for token in (
            "import requests",
            "import httpx",
            "import ccxt",
            "import render",
            "subprocess",
            ".env",
        )
    )
