"""Local source-contract regressions for fail-closed trading mode defaults."""

import ast
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]


def _module_assignments(path, names):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {
        target.id: node
        for node in tree.body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name) and target.id in names
    }


def _module_functions(path, names):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in names
    }


def _eval_assignment(node, environment):
    expression = ast.Expression(node.value)
    ast.fix_missing_locations(expression)
    return eval(compile(expression, "assignment", "eval"), {
        "os": SimpleNamespace(
            environ=environment,
            getenv=lambda key, default=None: environment.get(key, default),
        ),
    })


def _broker_namespace(environment):
    path = ROOT / "broker.py"
    assignments = _module_assignments(
        path, {"ENABLE_REAL_TRADING", "EXECUTION_MODE", "BROKER_DRY_RUN"}
    )
    functions = _module_functions(
        path,
        {"env_bool", "_broker_dry_run_enabled", "_broker_factual_writes_enabled"},
    )
    ns = {"os": SimpleNamespace(environ=dict(environment))}
    for name in ("env_bool", "_broker_dry_run_enabled"):
        module = ast.Module(body=[functions[name]], type_ignores=[])
        exec(compile(ast.fix_missing_locations(module), str(path), "exec"), ns)
    for name in ("ENABLE_REAL_TRADING", "EXECUTION_MODE", "BROKER_DRY_RUN"):
        module = ast.Module(body=[assignments[name]], type_ignores=[])
        exec(compile(ast.fix_missing_locations(module), str(path), "exec"), ns)
    module = ast.Module(
        body=[functions["_broker_factual_writes_enabled"]], type_ignores=[]
    )
    exec(compile(ast.fix_missing_locations(module), str(path), "exec"), ns)
    return ns


def test_omitted_or_malformed_dry_run_cannot_enable_broker_writes():
    for raw in (None, "", "garbage", "falsee"):
        ns = _broker_namespace({
            "EXECUTION_MODE": "LIVE",
            "ENABLE_REAL_TRADING": "true",
            **({} if raw is None else {"BROKER_DRY_RUN": raw}),
        })
        assert ns["BROKER_DRY_RUN"] is True
        assert ns["_broker_factual_writes_enabled"]() is False


def test_falcon_defaults_to_paper_even_if_global_execution_mode_is_live():
    path = ROOT / "bots" / "falcon.py"
    assignments = _module_assignments(path, {"FALCON_MODE"})
    for environment in (
        {},
        {"EXECUTION_MODE": "LIVE"},
        {"EXECUTION_MODE": "LIVE", "FALCON_MODE": "PAPER"},
    ):
        mode = _eval_assignment(assignments["FALCON_MODE"], environment)
        assert mode == "PAPER"


def test_all_environment_selectable_bot_modes_default_to_paper():
    cases = (
        ("cobra.py", "EXECUTION_MODE", {}),
        ("donkey.py", "EXECUTION_MODE", {}),
        ("falcon.py", "FALCON_MODE", {"EXECUTION_MODE": "LIVE"}),
        ("predator.py", "PREDATOR_MODE", {"EXECUTION_MODE": "LIVE"}),
        ("trendpro.py", "EXECUTION_MODE", {}),
    )
    for filename, variable, environment in cases:
        path = ROOT / "bots" / filename
        assignment = _module_assignments(path, {variable})[variable]
        assert _eval_assignment(assignment, environment) == "PAPER", filename


def test_empty_runtime_environment_defaults_broker_and_engine_to_non_live():
    broker = _broker_namespace({})
    assert broker["ENABLE_REAL_TRADING"] is False
    assert broker["EXECUTION_MODE"] == "PAPER"
    assert broker["BROKER_DRY_RUN"] is True
    assert broker["_broker_factual_writes_enabled"]() is False

    engine_path = ROOT / "execution_engine.py"
    engine_assignments = _module_assignments(
        engine_path,
        {
            "DEFAULT_ENGINE_MODE",
            "REAL_EXECUTION_ENABLED",
            "PAPER_EXECUTION_ENABLED",
        },
    )
    assert _eval_assignment(engine_assignments["DEFAULT_ENGINE_MODE"], {}) == "OBSERVATION_ONLY"
    assert _eval_assignment(engine_assignments["REAL_EXECUTION_ENABLED"], {}) is False
    assert _eval_assignment(engine_assignments["PAPER_EXECUTION_ENABLED"], {}) is False


def test_broker_dry_run_can_only_be_disabled_by_an_explicit_false_value():
    ns = _broker_namespace({
        "EXECUTION_MODE": "LIVE",
        "ENABLE_REAL_TRADING": "true",
        "BROKER_DRY_RUN": "false",
    })
    assert ns["BROKER_DRY_RUN"] is False
    assert ns["_broker_factual_writes_enabled"]() is True


def test_malformed_or_missing_broker_flags_never_enable_factual_writes():
    configurations = (
        {
            "EXECUTION_MODE": "LIVE",
            "ENABLE_REAL_TRADING": "true",
            "BROKER_DRY_RUN": "of",
        },
        {
            "EXECUTION_MODE": "LIVE",
            "ENABLE_REAL_TRADING": "enabled",
            "BROKER_DRY_RUN": "false",
        },
        {
            "EXECUTION_MODE": "LIVE?",
            "ENABLE_REAL_TRADING": "true",
            "BROKER_DRY_RUN": "false",
        },
        {
            "EXECUTION_MODE": "LIVE",
            "ENABLE_REAL_TRADING": "true",
        },
    )
    for environment in configurations:
        broker = _broker_namespace(environment)
        assert broker["_broker_factual_writes_enabled"]() is False, environment


def test_unrecognized_falcon_mode_is_not_interpreted_as_live():
    path = ROOT / "bots" / "falcon.py"
    assignment = _module_assignments(path, {"FALCON_MODE"})["FALCON_MODE"]

    assert _eval_assignment(assignment, {"FALCON_MODE": "LIVE?"}) != "LIVE"
    assert _eval_assignment(assignment, {"FALCON_MODE": " PAPER "}) == "PAPER"


def test_raw_exchange_write_boundary_independently_fails_closed():
    import ast
    from unittest.mock import Mock

    path = ROOT / "broker.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    helper = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_create_order_with_reserved_attempt"
    )
    exchange = SimpleNamespace(create_order=Mock())
    namespace = {"_broker_factual_writes_enabled": lambda: False}
    module = ast.Module(body=[helper], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), str(path), "exec"), namespace)

    result = namespace["_create_order_with_reserved_attempt"](
        exchange,
        "BTC/USDT:USDT",
        "market",
        "buy",
        1,
        None,
        {},
        client_order_id_reservation={},
        expected_reservation_roles=set(),
    )

    assert result["status"] == "BROKER_WRITE_MODE_DISABLED"
    assert result["sent"] is False
    assert result["send_attempted"] is False
    exchange.create_order.assert_not_called()


def test_all_raw_exchange_order_calls_are_confined_to_the_fail_closed_sink():
    raw_calls = []
    for path in ROOT.rglob("*.py"):
        relative = path.relative_to(ROOT)
        if "tests" in relative.parts or any(
            part.startswith(".") for part in relative.parts
        ):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in {"create_order", "createOrder"}
            ):
                raw_calls.append((path, tree, node))

    assert len(raw_calls) == 1
    path, tree, raw_call = raw_calls[0]
    assert path == ROOT / "broker.py"
    helper = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_create_order_with_reserved_attempt"
    )
    assert raw_call in ast.walk(helper)

    guard_index = 1 if (
        isinstance(helper.body[0], ast.Expr)
        and isinstance(helper.body[0].value, ast.Constant)
        and isinstance(helper.body[0].value.value, str)
    ) else 0
    guard = helper.body[guard_index]
    assert isinstance(guard, ast.If)
    assert isinstance(guard.test, ast.UnaryOp)
    assert isinstance(guard.test.op, ast.Not)
    assert isinstance(guard.test.operand, ast.Call)
    assert isinstance(guard.test.operand.func, ast.Name)
    assert guard.test.operand.func.id == "_broker_factual_writes_enabled"
    assert any(
        isinstance(node, ast.Return)
        and isinstance(node.value, ast.Dict)
        and any(
            isinstance(value, ast.Constant)
            and value.value == "BROKER_WRITE_MODE_DISABLED"
            for value in node.value.values
        )
        for node in ast.walk(guard)
    )
