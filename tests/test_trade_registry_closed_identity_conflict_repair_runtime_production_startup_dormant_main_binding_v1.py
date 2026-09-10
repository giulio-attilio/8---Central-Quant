from __future__ import annotations

import ast
from functools import lru_cache
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN_PATH = ROOT / "main.py"


@lru_cache(maxsize=1)
def _main_source():
    return MAIN_PATH.read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def _main_tree():
    return ast.parse(_main_source(), filename=str(MAIN_PATH))


def _function(tree, name):
    return next(
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    )


def test_main_parses_after_dormant_binding_installation():
    assert isinstance(_main_tree(), ast.Module)


def test_main_imports_only_the_dormant_port_binding_contract():
    source = _main_source()
    assert (
        "import trade_registry_closed_identity_conflict_repair_runtime_production_startup_port_binding_adapter_contract_v1 "
        "as c3_production_startup_port_binding_v1"
    ) in source
    assert "runtime_production_startup_port_binding_adapter_harness_v1" not in source


def test_all_five_main_sources_are_explicitly_fail_closed():
    tree = _main_tree()
    names = (
        "_c3_production_startup_state_source_dormant_v1",
        "_c3_production_seam_binding_source_dormant_v1",
        "_c3_production_maintenance_completion_source_dormant_v1",
        "_c3_production_evidence_verifier_source_dormant_v1",
        "_c3_production_startup_callback_source_dormant_v1",
    )
    for name in names:
        function = _function(tree, name)
        assert len(function.body) == 1
        assert isinstance(function.body[0], ast.Raise)


def test_dormant_installer_binds_but_never_invokes_sources_gate_or_composition():
    tree = _main_tree()
    function = _function(tree, "_install_c3_production_startup_port_binding_dormant_v1")
    calls = [node for node in ast.walk(function) if isinstance(node, ast.Call)]
    attribute_calls = {
        node.func.attr for node in calls if isinstance(node.func, ast.Attribute)
    }
    direct_calls = {node.func.id for node in calls if isinstance(node.func, ast.Name)}
    assert "bind_dormant" in attribute_calls
    assert "rehearse_offline" not in attribute_calls
    assert "startup_admission" not in attribute_calls
    assert "start_central_runtime_once" not in direct_calls
    dormant_sources = {
        "_c3_production_startup_state_source_dormant_v1",
        "_c3_production_seam_binding_source_dormant_v1",
        "_c3_production_maintenance_completion_source_dormant_v1",
        "_c3_production_evidence_verifier_source_dormant_v1",
        "_c3_production_startup_callback_source_dormant_v1",
    }
    assert direct_calls.isdisjoint(dormant_sources)


def test_dormant_main_binding_has_no_authority_and_no_activation_path():
    source = _main_source()
    start = source.index("def _install_c3_production_startup_port_binding_dormant_v1")
    end = source.index("if CENTRAL_AUTO_START_RUNTIME:", start)
    block = source[start:end]
    assert "authority_root_sha256=None" in block
    assert '"production_authority_configured": False' in block
    assert '"activation_possible": False' in block
    assert '"live_allowed": False' in block
    assert '"order_submission_authorized": False' in block


def test_dormant_binding_is_installed_before_unchanged_runtime_autostart():
    source = _main_source()
    binding_position = source.index(
        "C3_PRODUCTION_STARTUP_PORT_BINDING_DORMANT_V1 = ("
    )
    autostart_position = source.index("if CENTRAL_AUTO_START_RUNTIME:", binding_position)
    assert binding_position < autostart_position
    assert (
        source[autostart_position:].splitlines()[:2]
        == ["if CENTRAL_AUTO_START_RUNTIME:", "    start_central_runtime_once()"]
    )


def test_main_binding_does_not_enable_gate_composition_live_or_orders():
    source = _main_source()
    start = source.index("def _install_c3_production_startup_port_binding_dormant_v1")
    end = source.index("if CENTRAL_AUTO_START_RUNTIME:", start)
    block = source[start:end]
    assert "enabled=False" in block
    assert "dormant_only=True" in block
    assert "enabled=True" not in block
    assert "rehearse_offline" not in block
    assert "startup_admission(" not in block
