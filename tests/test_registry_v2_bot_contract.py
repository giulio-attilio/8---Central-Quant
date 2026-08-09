from __future__ import annotations

import ast
import copy
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

import registry_execution_schema as schema
import registry_v2_bot_contract as contract


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "registry_v2_bot_contract.py"
BOT_COMPONENTS = ("FALCON", "TURTLE", "PREDATOR", "DONKEY", "TRENDPRO", "COBRA", "MEME")
EXEC_A = "exec_11111111-1111-4111-8111-111111111111"
EXEC_B = "exec_22222222-2222-4222-8222-222222222222"
EXEC_LONG = "exec_33333333-3333-4333-8333-333333333333"
EXEC_SHORT = "exec_44444444-4444-4444-8444-444444444444"
EXEC_REENTRY = "exec_55555555-5555-4555-8555-555555555555"
AUXILIARY_COMPONENTS = (
    "MAIN_SYNC",
    "LIFECYCLE_SHADOW_ADAPTER",
    "REAL_PNL_R_MAPPER",
    "OUTCOME_EVALUATOR",
    "REPORTS_DOCTOR",
)
CRITICAL_TOP_LEVEL_FILES = (
    "main.py",
    "execution_engine.py",
    "execution_orchestrator.py",
    "trade_registry.py",
)
_NON_PRODUCTIVE_DIRS = {
    ".agents",
    ".codex",
    ".git",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "node_modules",
    "tests",
}
_RELATED_COMPONENT_TOKENS = ("lifecycle", "pnl", "outcome")


def _payload(component="FALCON", **overrides):
    bot = component if component in BOT_COMPONENTS else "FALCON"
    setup = {
        "FALCON": "FALCON15",
        "TURTLE": "TURTLE5",
        "PREDATOR": "PREDATOR1",
        "DONKEY": "DONKEY1",
        "TRENDPRO": "TRENDPRO1",
        "COBRA": "COBRA1",
        "MEME": "MEME1",
    }.get(bot, "FALCON15")
    payload = {
        "execution_id": EXEC_A,
        "lifecycle_id": EXEC_A,
        "bot": bot,
        "setup": setup,
        "symbol": "BTCUSDT",
        "side": "LONG",
        "position_side": "LONG",
        "owner_type": schema.CENTRAL,
        "execution_mode": schema.PAPER,
        "registry_mode": schema.PAPER,
        "signal_id": "signal-a",
        "decision_id": "decision-a",
        "logical_trade_id": f"{bot}:{setup}:BTCUSDT:LONG",
        "metadata": {"nested": {"stable": True}},
    }
    payload.update(overrides)
    return payload


def _discover_productive_sources():
    bots_root = ROOT / "bots"
    assert bots_root.is_dir()
    bot_sources = tuple(sorted(path for path in bots_root.rglob("*.py") if path.is_file()))
    assert bot_sources

    sources = set(bot_sources)
    for filename in CRITICAL_TOP_LEVEL_FILES:
        path = ROOT / filename
        if path.is_file():
            sources.add(path)

    pending = [ROOT]
    while pending:
        current = pending.pop()
        for path in current.iterdir():
            if path.is_dir():
                if path.name not in _NON_PRODUCTIVE_DIRS and not path.name.startswith(".pytest"):
                    pending.append(path)
                continue
            if path.suffix.lower() == ".py" and any(
                token in path.stem.lower() for token in _RELATED_COMPONENT_TOKENS
            ):
                sources.add(path)
    return tuple(sorted(sources))


def test_supported_component_specs_are_explicit_and_immutable():
    for component in (*BOT_COMPONENTS, *AUXILIARY_COMPONENTS):
        spec = contract.get_registry_v2_bot_contract(component)
        assert spec is not None
        assert spec.component == component
        assert spec.requires_execution_id
        assert spec.requires_lifecycle_alias
        assert spec.requirements

    assert contract.get_registry_v2_bot_contract("unknown-component") is None


def test_execution_and_lifecycle_identity_must_be_supplied_and_equal():
    valid = contract.validate_registry_v2_bot_payload("FALCON", _payload())
    mismatch = contract.validate_registry_v2_bot_payload(
        "FALCON", _payload(lifecycle_id=EXEC_B),
    )
    missing_execution = contract.validate_registry_v2_bot_payload(
        "FALCON", _payload(execution_id=None, lifecycle_id=None),
    )
    missing_lifecycle = contract.validate_registry_v2_bot_payload(
        "FALCON", _payload(lifecycle_id=None),
    )
    empty_execution = contract.validate_registry_v2_bot_payload(
        "FALCON", _payload(execution_id=""),
    )

    assert valid.ok
    assert valid.projection.execution_id == EXEC_A
    assert valid.projection.lifecycle_id == EXEC_A
    assert mismatch.status == contract.REGISTRY_V2_BOT_CONTRACT_LIFECYCLE_CONFLICT
    assert missing_execution.status == contract.REGISTRY_V2_BOT_CONTRACT_ID_REQUIRED
    assert missing_execution.errors == ("execution_id",)
    assert missing_lifecycle.status == contract.REGISTRY_V2_BOT_CONTRACT_ID_REQUIRED
    assert missing_lifecycle.errors == ("lifecycle_id",)
    assert empty_execution.status == contract.REGISTRY_V2_BOT_CONTRACT_ID_REQUIRED


@pytest.mark.parametrize(
    "invalid_id",
    (
        "exec-a",
        "foo",
        "BTCUSDT-LONG",
        "11111111-1111-4111-8111-111111111111",
        "EXEC_11111111-1111-4111-8111-111111111111",
        "exec_11111111-1111-4111-8111-11111111111A",
    ),
)
def test_execution_identity_requires_canonical_v2_format(invalid_id):
    result = contract.validate_registry_v2_bot_payload(
        "FALCON", _payload(execution_id=invalid_id, lifecycle_id=invalid_id),
    )

    assert result.status == contract.REGISTRY_V2_BOT_CONTRACT_ID_INVALID
    assert result.errors == ("execution_id", "lifecycle_id")


def test_malformed_lifecycle_id_fails_closed_even_with_valid_execution_id():
    result = contract.validate_registry_v2_bot_payload(
        "FALCON", _payload(lifecycle_id="exec-a"),
    )

    assert not result.ok
    assert result.status == contract.REGISTRY_V2_BOT_CONTRACT_LIFECYCLE_CONFLICT


def test_logical_or_strong_ids_cannot_rescue_malformed_physical_identity():
    result = contract.validate_registry_v2_bot_payload(
        "FALCON",
        _payload(
            execution_id="exec-a",
            lifecycle_id="exec-a",
            logical_trade_id="FALCON:FALCON15:BTCUSDT:LONG",
            client_order_id="client-a",
        ),
    )

    assert result.status == contract.REGISTRY_V2_BOT_CONTRACT_ID_INVALID
    assert result.errors == ("execution_id", "lifecycle_id")


def test_logical_id_is_validated_only_as_grouping_and_never_generates_identity():
    valid = contract.validate_registry_v2_bot_payload("FALCON", _payload())
    contradictory = contract.validate_registry_v2_bot_payload(
        "FALCON", _payload(logical_trade_id="FALCON:FALCON15:ETHUSDT:LONG"),
    )
    without_logical = contract.validate_registry_v2_bot_payload(
        "FALCON", _payload(logical_trade_id=None),
    )
    first = contract.validate_registry_v2_bot_payload(
        "FALCON", _payload(execution_id=EXEC_A, lifecycle_id=EXEC_A),
    )
    second = contract.validate_registry_v2_bot_payload(
        "FALCON", _payload(execution_id=EXEC_B, lifecycle_id=EXEC_B),
    )

    assert valid.ok
    assert contradictory.status == contract.REGISTRY_V2_BOT_CONTRACT_LOGICAL_CONFLICT
    assert without_logical.status == contract.REGISTRY_V2_BOT_CONTRACT_REQUIRED_FIELD_MISSING
    assert without_logical.errors == ("logical_trade_id",)
    assert first.projection.execution_id != second.projection.execution_id
    assert first.projection.logical_trade_id == second.projection.logical_trade_id


def test_logical_trade_id_is_required_for_live_execution_shape():
    result = contract.validate_registry_v2_bot_payload(
        "FALCON",
        _payload(execution_mode=schema.LIVE, registry_mode=schema.UNKNOWN, logical_trade_id=None),
    )

    assert result.status == contract.REGISTRY_V2_BOT_CONTRACT_REQUIRED_FIELD_MISSING
    assert result.errors == ("logical_trade_id",)


def test_manual_external_is_not_a_central_execution_contract():
    result = contract.validate_registry_v2_bot_payload(
        "FALCON", _payload(owner_type=schema.MANUAL_EXTERNAL),
    )

    assert result.status == contract.REGISTRY_V2_BOT_CONTRACT_OWNER_CONFLICT
    assert result.errors == ("owner_type",)


def test_source_payload_is_deep_equal_after_validation_and_projection():
    payload = _payload(
        client_order_id="client-a",
        broker_order_id="broker-a",
        exchange_order_id="exchange-a",
        fill_id="fill-a",
        close_event_id="close-a",
        metadata={"nested": {"items": [1, 2]}},
    )
    before = copy.deepcopy(payload)

    result = contract.project_registry_v2_bot_payload("FALCON", payload)

    assert result.ok
    assert payload == before
    assert result.projection.metadata == (("nested", (("items", (1, 2)),)),)
    with pytest.raises(FrozenInstanceError):
        result.projection.execution_id = EXEC_B


def test_falcon_requires_full_identity_contract_fields():
    complete = contract.validate_registry_v2_bot_payload("FALCON", _payload())
    missing_signal = contract.validate_registry_v2_bot_payload(
        "FALCON", _payload(signal_id=None),
    )
    missing_decision = contract.validate_registry_v2_bot_payload(
        "FALCON", _payload(decision_id=None),
    )
    missing_position_side = contract.validate_registry_v2_bot_payload(
        "FALCON", _payload(position_side=None),
    )

    assert complete.ok
    assert missing_signal.status == contract.REGISTRY_V2_BOT_CONTRACT_REQUIRED_FIELD_MISSING
    assert missing_signal.errors == ("signal_id",)
    assert missing_decision.errors == ("decision_id",)
    assert missing_position_side.errors == ("position_side",)


def test_falcon_live_shape_is_data_only_and_never_authorizes_execution():
    result = contract.validate_registry_v2_bot_payload(
        "FALCON",
        _payload(execution_mode=schema.LIVE, registry_mode=schema.UNKNOWN),
    )

    assert result.ok
    assert result.projection.execution_mode == schema.LIVE
    assert result.projection.registry_mode == schema.UNKNOWN


def test_falcon_live_verify_registry_mode_is_preserved_as_factual_classification():
    result = contract.validate_registry_v2_bot_payload(
        "FALCON",
        _payload(execution_mode=schema.LIVE, registry_mode=schema.VERIFY),
    )

    assert result.ok
    assert result.projection.execution_mode == schema.LIVE
    assert result.projection.registry_mode == schema.VERIFY


@pytest.mark.parametrize("registry_mode", [schema.UNKNOWN, schema.REAL, schema.VERIFY, schema.CONFLICT])
def test_falcon_live_accepts_all_authoritative_registry_modes(registry_mode):
    result = contract.validate_registry_v2_bot_payload(
        "FALCON", _payload(execution_mode=schema.LIVE, registry_mode=registry_mode),
    )

    assert result.ok
    assert result.projection.registry_mode == registry_mode


def test_falcon_live_paper_registry_mode_remains_invalid():
    result = contract.validate_registry_v2_bot_payload(
        "FALCON", _payload(execution_mode=schema.LIVE, registry_mode=schema.PAPER),
    )

    assert result.status == contract.REGISTRY_V2_BOT_CONTRACT_MODE_INVALID
    assert result.errors == ("registry_mode",)


def test_verify_is_description_only_without_physical_identity():
    payload = _payload(
        execution_mode=schema.VERIFY,
        registry_mode=schema.VERIFY,
        execution_id=None,
        lifecycle_id=None,
        logical_trade_id=None,
    )
    before = copy.deepcopy(payload)

    result = contract.validate_registry_v2_bot_payload("FALCON", payload)

    assert result.ok
    assert result.status == contract.REGISTRY_V2_BOT_CONTRACT_VERIFY_DESCRIPTION
    assert result.projection.execution_id is None
    assert result.projection.lifecycle_id is None
    assert result.projection.registry_mode == schema.VERIFY
    assert result.projection.logical_trade_id is None
    assert payload == before


def test_verify_never_generates_identity_and_rejects_supplied_physical_identity():
    result = contract.validate_registry_v2_bot_payload(
        "FALCON",
        _payload(execution_mode=schema.VERIFY, registry_mode=schema.VERIFY),
    )

    assert result.status == contract.REGISTRY_V2_BOT_CONTRACT_VERIFY_NON_EXECUTION
    assert result.projection is None


def test_verify_registry_mode_must_not_be_real():
    valid = contract.validate_registry_v2_bot_payload(
        "FALCON",
        _payload(execution_mode=schema.VERIFY, registry_mode=schema.VERIFY, execution_id=None, lifecycle_id=None),
    )
    invalid = contract.validate_registry_v2_bot_payload(
        "FALCON",
        _payload(execution_mode=schema.VERIFY, registry_mode=schema.REAL, execution_id=None, lifecycle_id=None),
    )

    assert valid.status == contract.REGISTRY_V2_BOT_CONTRACT_VERIFY_DESCRIPTION
    assert invalid.status == contract.REGISTRY_V2_BOT_CONTRACT_MODE_INVALID


def test_registry_mode_is_preserved_without_inference_when_optional():
    result = contract.validate_registry_v2_bot_payload(
        "FALCON",
        _payload(execution_mode=schema.LIVE, registry_mode=None),
    )

    assert result.ok
    assert result.projection.registry_mode is None


@pytest.mark.parametrize(
    "side,position_side,expected_ok",
    [
        ("LONG", "LONG", True),
        ("SHORT", "SHORT", True),
        ("LONG", "SHORT", False),
        ("SHORT", "LONG", False),
        ("LONG", "BOTH", False),
        ("LONG", "NET", False),
    ],
)
def test_falcon_position_side_is_exactly_the_economic_side(side, position_side, expected_ok):
    result = contract.validate_registry_v2_bot_payload(
        "FALCON",
        _payload(side=side, position_side=position_side, logical_trade_id=f"FALCON:FALCON15:BTCUSDT:{side}"),
    )

    assert result.ok is expected_ok
    if not expected_ok:
        assert result.errors == ("position_side",)


def test_turtle_paper_requires_supplied_physical_identity():
    valid = contract.validate_registry_v2_bot_payload("TURTLE", _payload("TURTLE"))
    missing_identity = contract.validate_registry_v2_bot_payload(
        "TURTLE", _payload("TURTLE", execution_id=None, lifecycle_id=None),
    )
    logical_only = contract.validate_registry_v2_bot_payload(
        "TURTLE",
        _payload("TURTLE", execution_id=None, lifecycle_id=None, logical_trade_id="TURTLE:TURTLE5:BTCUSDT:LONG"),
    )

    assert valid.ok
    assert missing_identity.status == contract.REGISTRY_V2_BOT_CONTRACT_ID_REQUIRED
    assert logical_only.status == contract.REGISTRY_V2_BOT_CONTRACT_ID_REQUIRED


def test_turtle_live_contract_is_not_enabled_by_this_spec():
    result = contract.validate_registry_v2_bot_payload(
        "TURTLE",
        _payload("TURTLE", execution_mode=schema.LIVE, registry_mode=schema.UNKNOWN),
    )

    assert result.status == contract.REGISTRY_V2_BOT_CONTRACT_MODE_INVALID


@pytest.mark.parametrize("mode", [schema.PAPER, schema.LIVE])
def test_predator_supports_paper_and_live_shaped_data(mode):
    registry_mode = schema.PAPER if mode == schema.PAPER else schema.UNKNOWN
    result = contract.validate_registry_v2_bot_payload(
        "PREDATOR",
        _payload("PREDATOR", execution_mode=mode, registry_mode=registry_mode),
    )

    assert result.ok
    assert result.projection.registry_mode == registry_mode


def test_predator_live_verify_registry_mode_is_accepted_and_preserved():
    result = contract.validate_registry_v2_bot_payload(
        "PREDATOR", _payload("PREDATOR", execution_mode=schema.LIVE, registry_mode=schema.VERIFY),
    )

    assert result.ok
    assert result.projection.execution_mode == schema.LIVE
    assert result.projection.registry_mode == schema.VERIFY


def test_predator_requires_explicit_factual_registry_mode():
    paper_missing = contract.validate_registry_v2_bot_payload(
        "PREDATOR", _payload("PREDATOR", registry_mode=None),
    )
    live_missing = contract.validate_registry_v2_bot_payload(
        "PREDATOR",
        _payload("PREDATOR", execution_mode=schema.LIVE, registry_mode=None),
    )
    spec = contract.get_registry_v2_bot_contract("PREDATOR")

    assert spec.requires_registry_mode
    assert paper_missing.status == contract.REGISTRY_V2_BOT_CONTRACT_REQUIRED_FIELD_MISSING
    assert paper_missing.errors == ("registry_mode",)
    assert live_missing.status == contract.REGISTRY_V2_BOT_CONTRACT_REQUIRED_FIELD_MISSING
    assert live_missing.errors == ("registry_mode",)


def test_donkey_future_contract_marks_alternate_setup_fallback_forbidden():
    spec = contract.get_registry_v2_bot_contract("DONKEY")
    result = contract.validate_registry_v2_bot_payload("DONKEY", _payload("DONKEY"))

    assert result.ok
    assert "no_alternative_setup_fallback" in spec.requirements


def test_trendpro_projection_preserves_reentry_identity():
    result = contract.validate_registry_v2_bot_payload(
        "TRENDPRO", _payload("TRENDPRO", execution_id=EXEC_REENTRY, lifecycle_id=EXEC_REENTRY),
    )

    assert result.ok
    assert result.projection.execution_id == EXEC_REENTRY
    assert result.projection.lifecycle_id == EXEC_REENTRY
    assert "execution_identity_persists_through_reentry" in contract.get_registry_v2_bot_contract("TRENDPRO").requirements


def test_cobra_long_and_short_are_separate_physical_contracts():
    long_result = contract.validate_registry_v2_bot_payload(
        "COBRA",
        _payload("COBRA", execution_id=EXEC_LONG, lifecycle_id=EXEC_LONG, side="LONG"),
    )
    short_result = contract.validate_registry_v2_bot_payload(
        "COBRA",
        _payload(
            "COBRA",
            execution_id=EXEC_SHORT,
            lifecycle_id=EXEC_SHORT,
            side="SHORT",
            position_side="SHORT",
            logical_trade_id="COBRA:COBRA1:BTCUSDT:SHORT",
        ),
    )

    assert long_result.ok and short_result.ok
    assert long_result.projection.execution_id != short_result.projection.execution_id
    assert "opposite_sides_are_independent_executions" in contract.get_registry_v2_bot_contract("COBRA").requirements


def test_meme_contract_describes_realized_r_requirement_without_calculating_it():
    payload = _payload("MEME", mfe_r=99, realized_r=-1)
    before = copy.deepcopy(payload)

    result = contract.validate_registry_v2_bot_payload("MEME", payload)

    assert result.ok
    assert payload == before
    assert "realized_r_not_inferred_from_mfe" in contract.get_registry_v2_bot_contract("MEME").requirements


def test_strong_ids_are_preserved_as_payload_facts_without_lookup_or_ownership_inference():
    result = contract.validate_registry_v2_bot_payload(
        "FALCON",
        _payload(
            client_order_id="client-a",
            broker_order_id="broker-a",
            exchange_order_id="exchange-a",
            fill_id="fill-a",
            close_event_id="close-a",
        ),
    )

    assert result.ok
    assert result.projection.client_order_id == "client-a"
    assert result.projection.broker_order_id == "broker-a"
    assert result.projection.exchange_order_id == "exchange-a"
    assert result.projection.fill_id == "fill-a"
    assert result.projection.close_event_id == "close-a"


@pytest.mark.parametrize("component", AUXILIARY_COMPONENTS)
def test_auxiliary_component_contracts_are_identity_first_metadata_only(component):
    result = contract.validate_registry_v2_bot_payload(component, _payload(component))

    assert result.ok
    assert result.projection.execution_id == EXEC_A
    assert "execution_id" in " ".join(contract.get_registry_v2_bot_contract(component).requirements)


def test_contract_module_source_has_no_runtime_or_writer_dependencies():
    source = MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_modules = {
        "main",
        "execution_engine",
        "execution_orchestrator",
        "trade_registry",
        "registry_v2_core",
        "registry_v2_wal",
        "registry_v2_reader",
        "broker",
        "requests",
        "httpx",
        "subprocess",
        "flask",
        "fastapi",
        "uuid",
        "os",
        "pathlib",
    }
    forbidden_calls = {
        "uuid4",
        "generate_execution_lifecycle_id",
        "generate_execution_id",
        "open",
        "write",
        "write_text",
        "write_bytes",
        "mkdir",
        "rename",
        "unlink",
        "getenv",
    }
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported.update(
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    )
    called = {
        node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and (isinstance(node.func, ast.Attribute) or isinstance(node.func, ast.Name))
    }

    assert not imported.intersection(forbidden_modules)
    assert not called.intersection(forbidden_calls)
    assert "os.environ" not in source


def test_productive_modules_do_not_import_dormant_v27_contract():
    paths = _discover_productive_sources()
    bot_paths = tuple(path for path in paths if "bots" in path.relative_to(ROOT).parts)
    assert bot_paths
    for required in ("main.py", "execution_engine.py", "execution_orchestrator.py"):
        required_path = ROOT / required
        if required_path.is_file():
            assert required_path in paths

    for path in paths:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        imported_modules = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_modules.add(node.module)
        assert "registry_v2_bot_contract" not in imported_modules, str(path)


def test_productive_source_discovery_is_nonempty_and_excludes_test_contract_files():
    paths = _discover_productive_sources()

    assert len(paths) >= 1
    assert any("bots" in path.relative_to(ROOT).parts for path in paths)
    assert ROOT / "main.py" in paths
    assert ROOT / "execution_engine.py" in paths
    assert ROOT / "execution_orchestrator.py" in paths
    assert MODULE_PATH not in paths
    assert Path(__file__).resolve() not in paths


def test_dormant_import_is_pure_and_has_no_activation_surface():
    source = MODULE_PATH.read_text(encoding="utf-8")

    assert "threading" not in source
    assert "socket" not in source
    assert "requests" not in source
    assert "feature_flag" not in source
    assert "os.environ" not in source
    assert "route" not in source
    assert "registry_v2_core" not in source
    assert "registry_v2_wal" not in source
