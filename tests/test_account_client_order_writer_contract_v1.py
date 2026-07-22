from __future__ import annotations

import ast
import os
from functools import lru_cache
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

EXCLUDED_PRODUCTION_SOURCE_PARTS = frozenset(
    {
        ".git",
        ".agents",
        ".codex",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "env",
        "tests",
        "venv",
    }
)

# Public broker APIs which can ultimately create a factual LIVE order.  Read-only
# reconciliation/snapshot helpers and cancellation are deliberately not included.
FACTUAL_ORDER_WRITERS = {
    "place_market_order",
    "create_disaster_stop_order",
    "replace_position_stop_order",
    "managed_close_position_market",
    "close_position_market",
}

CLIENT_ID_ALIASES = {
    "clientid",
    "clientorderid",
    "clienttag",
    "brokerclientorderid",
    "newclientorderid",
}


def _production_sources() -> tuple[Path, ...]:
    """Return project-owned Python sources without traversing tests/temp/venv."""

    sources = []
    for directory, child_directories, filenames in os.walk(ROOT):
        child_directories[:] = [
            name
            for name in child_directories
            if name not in EXCLUDED_PRODUCTION_SOURCE_PARTS
            and not name.startswith(".pytest_tmp")
        ]
        current = Path(directory)
        sources.extend(current / name for name in filenames if name.endswith(".py"))
    return tuple(sorted(sources))


@lru_cache(maxsize=None)
def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _normalized_name(value: str | None) -> str:
    return "".join(char for char in str(value or "").lower() if char.isalnum())


def _is_client_id_name(value: str | None) -> bool:
    normalized = _normalized_name(value)
    return (
        normalized in CLIENT_ID_ALIASES
        or normalized.endswith("clientorderid")
        or normalized.endswith("clientid")
    )


def _call_name(node: ast.Call) -> str:
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    if isinstance(node.func, ast.Name):
        return node.func.id
    return ""


class _CallInventory(ast.NodeVisitor):
    def __init__(self, path: Path):
        self.path = path
        self.functions: list[str] = []
        self.if_tests: list[str] = []
        self.raw_create_order_calls: list[dict] = []
        self.factual_writer_calls: list[dict] = []
        self.private_boundary_calls: list[dict] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.functions.append(node.name)
        self.generic_visit(node)
        self.functions.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_If(self, node: ast.If) -> None:
        self.if_tests.append(ast.unparse(node.test))
        for child in node.body:
            self.visit(child)
        self.if_tests.pop()
        for child in node.orelse:
            self.visit(child)

    def visit_Call(self, node: ast.Call) -> None:
        name = _call_name(node)
        record = {
            "path": self.path.relative_to(ROOT).as_posix(),
            "line": node.lineno,
            "function": self.functions[-1] if self.functions else "<module>",
            "keywords": {item.arg: item.value for item in node.keywords if item.arg},
            "if_tests": tuple(self.if_tests),
            "node": node,
        }
        if isinstance(node.func, ast.Attribute) and node.func.attr == "create_order":
            self.raw_create_order_calls.append(record)
        if name in FACTUAL_ORDER_WRITERS:
            self.factual_writer_calls.append({**record, "writer": name})
        if name == "_create_order_with_reserved_attempt":
            self.private_boundary_calls.append(record)
        self.generic_visit(node)


@lru_cache(maxsize=1)
def _call_inventory() -> _CallInventory:
    combined = _CallInventory(ROOT)
    for path in _production_sources():
        visitor = _CallInventory(path)
        visitor.visit(_tree(path))
        combined.raw_create_order_calls.extend(visitor.raw_create_order_calls)
        combined.factual_writer_calls.extend(visitor.factual_writer_calls)
        combined.private_boundary_calls.extend(visitor.private_boundary_calls)
    return combined


def _function(path: Path, name: str, *, last: bool = True) -> ast.FunctionDef:
    matches = [
        node
        for node in _tree(path).body
        if isinstance(node, ast.FunctionDef) and node.name == name
    ]
    assert matches, f"function not found: {path.name}:{name}"
    return matches[-1] if last else matches[0]


def _contains_slice(node: ast.AST) -> bool:
    return any(
        isinstance(child, ast.Subscript) and isinstance(child.slice, ast.Slice)
        for child in ast.walk(node)
    )


def _loaded_names(node: ast.AST) -> set[str]:
    return {
        child.id
        for child in ast.walk(node)
        if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load)
    }


def _assigned_names(target: ast.AST) -> set[str]:
    return {
        child.id
        for child in ast.walk(target)
        if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store)
    }


def _constant_dict_key(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _client_id_slice_violations(path: Path) -> list[dict]:
    """Small intra-function taint check: slice -> clientOrderId/client_tag sink."""

    violations: list[dict] = []
    tree = _tree(path)
    scopes: list[tuple[str, ast.AST]] = [("<module>", tree)]
    scopes.extend(
        (node.name, node)
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    )

    for function_name, owner in scopes:
        # Do not mix nested function bodies into their parent's data-flow scope.
        nodes: list[ast.AST] = []

        class ScopeVisitor(ast.NodeVisitor):
            def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
                return None

            visit_AsyncFunctionDef = visit_FunctionDef

            def visit_ClassDef(self, node: ast.ClassDef) -> None:
                return None

            def generic_visit(self, node: ast.AST) -> None:
                nodes.append(node)
                super().generic_visit(node)

        visitor = ScopeVisitor()
        statements = owner.body if hasattr(owner, "body") else []
        for statement in statements:
            if isinstance(
                statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
            ):
                continue
            visitor.visit(statement)

        assignments: list[tuple[set[str], ast.AST, int]] = []
        for node in nodes:
            if isinstance(node, ast.Assign):
                names = set().union(*(_assigned_names(item) for item in node.targets))
                assignments.append((names, node.value, node.lineno))
            elif isinstance(node, ast.AnnAssign) and node.value is not None:
                assignments.append(
                    (_assigned_names(node.target), node.value, node.lineno)
                )
            elif isinstance(node, ast.NamedExpr):
                assignments.append(
                    (_assigned_names(node.target), node.value, node.lineno)
                )

        sliced_names = {
            name
            for names, value, _line in assignments
            if _contains_slice(value)
            for name in names
        }
        def taint_flows(value: ast.AST) -> bool:
            if _contains_slice(value):
                return True
            if not (_loaded_names(value) & sliced_names):
                return False
            if isinstance(
                value,
                (
                    ast.Name,
                    ast.BinOp,
                    ast.BoolOp,
                    ast.Compare,
                    ast.IfExp,
                    ast.JoinedStr,
                    ast.FormattedValue,
                    ast.List,
                    ast.Tuple,
                    ast.Set,
                    ast.Dict,
                    ast.Subscript,
                ),
            ):
                return True
            if isinstance(value, ast.Call):
                # String/normalization wrappers preserve a sliced value.  An
                # arbitrary helper call is a semantic boundary (notably the
                # common cryptographic generator/reservation authority).
                transparent = {
                    "str",
                    "bytes",
                    "normalize_account_client_order_id",
                    "validate_broker_client_order_id",
                }
                name = _call_name(value)
                return name in transparent or name in {
                    "upper",
                    "lower",
                    "strip",
                    "replace",
                    "removeprefix",
                    "removesuffix",
                }
            return False

        changed = True
        while changed:
            changed = False
            for names, value, _line in assignments:
                new_names = names - sliced_names
                if new_names and taint_flows(value):
                    sliced_names.update(new_names)
                    changed = True

        def sliced(value: ast.AST) -> bool:
            return taint_flows(value)

        for names, value, line in assignments:
            if any(_is_client_id_name(name) for name in names) and sliced(value):
                violations.append(
                    {
                        "path": path.relative_to(ROOT).as_posix(),
                        "function": function_name,
                        "line": line,
                        "sink": sorted(names),
                    }
                )

        for node in nodes:
            if isinstance(node, ast.Call):
                for keyword in node.keywords:
                    if keyword.arg and _is_client_id_name(keyword.arg) and sliced(
                        keyword.value
                    ):
                        violations.append(
                            {
                                "path": path.relative_to(ROOT).as_posix(),
                                "function": function_name,
                                "line": node.lineno,
                                "sink": keyword.arg,
                            }
                        )
            elif isinstance(node, ast.Dict):
                for key, value in zip(node.keys, node.values):
                    key_name = _constant_dict_key(key) if key is not None else None
                    if key_name and _is_client_id_name(key_name) and sliced(value):
                        violations.append(
                            {
                                "path": path.relative_to(ROOT).as_posix(),
                                "function": function_name,
                                "line": node.lineno,
                                "sink": key_name,
                            }
                        )
            elif (
                isinstance(node, ast.Return)
                and node.value is not None
                and _is_client_id_name(function_name)
                and sliced(node.value)
            ):
                violations.append(
                    {
                        "path": path.relative_to(ROOT).as_posix(),
                        "function": function_name,
                        "line": node.lineno,
                        "sink": "return",
                    }
                )

    # Multiple AST paths can point to the same sink; report each source location once.
    unique = {
        (item["path"], item["function"], item["line"], str(item["sink"])): item
        for item in violations
    }
    return list(unique.values())


def test_all_factual_order_writers_cross_the_common_account_boundary():
    inventory = _call_inventory()

    # The account-wide broker boundary is the only project-owned raw CCXT sink.
    raw = [
        (item["path"], item["function"], item["line"])
        for item in inventory.raw_create_order_calls
    ]
    assert len(raw) == 1
    assert raw[0][:2] == ("broker.py", "_create_order_with_reserved_attempt")

    # Every factual writer must pass a rich receipt.  The sole exception is the
    # Falcon VERIFY preview, whose lexical branch is statically VERIFY-only and
    # therefore cannot reach create_order under the broker's dry-run contract.
    unreserved = []
    for item in inventory.factual_writer_calls:
        if "client_order_id_reservation" in item["keywords"]:
            continue
        tests = " | ".join(item["if_tests"]).upper()
        preview_only = (
            item["path"] == "bots/falcon.py"
            and item["writer"] == "place_market_order"
            and item["function"] == "execute_signal_if_allowed"
            and "VERIFY" in tests
        )
        if not preview_only:
            unreserved.append(
                (item["path"], item["function"], item["line"], item["writer"])
            )
    assert unreserved == []

    # Every broker-internal transition to the sole sink carries the receipt too.
    missing_at_boundary = [
        (item["path"], item["function"], item["line"])
        for item in inventory.private_boundary_calls
        if "client_order_id_reservation" not in item["keywords"]
        or isinstance(
            item["keywords"].get("client_order_id_reservation"), ast.Constant
        )
        and item["keywords"]["client_order_id_reservation"].value is None
    ]
    assert missing_at_boundary == []


def test_account_wide_writer_inventory_recurses_all_project_packages():
    sources = _production_sources()
    relative_sources = {path.relative_to(ROOT).as_posix() for path in sources}

    assert "account_client_order_id.py" in relative_sources
    assert "broker.py" in relative_sources
    assert "bots/falcon.py" in relative_sources
    assert all("tests" not in path.parts for path in sources)
    assert all(".venv" not in path.parts for path in sources)
    inventory_source = ast.unparse(_function(Path(__file__), "_production_sources"))
    assert "os.walk(ROOT)" in inventory_source
    assert "child_directories[:]" in inventory_source


def test_dynamic_disaster_stop_writer_cannot_bypass_common_reservation():
    """The main.py compatibility wrapper uses a dynamic callable, so inspect it."""

    function = _function(ROOT / "main.py", "_dsf_v1_attempt_broker_stop_order")
    parameters = {item.arg for item in function.args.args + function.args.kwonlyargs}
    assert "client_order_id_reservation" in parameters

    calls = [node for node in ast.walk(function) if isinstance(node, ast.Call)]
    assert any(
        _call_name(node) == "_dsf_v1_client_order_id_reservation_allows"
        for node in calls
    )
    assert not any(
        isinstance(node.func, ast.Attribute) and node.func.attr == "create_order"
        for node in calls
    )

    wrappers = []
    reservation_forwarded = False
    for node in ast.walk(function):
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "wrapper_methods"
            for target in node.targets
        ):
            wrappers.extend(
                item.value
                for item in node.value.elts
                if isinstance(node.value, (ast.List, ast.Tuple))
                and isinstance(item, ast.Constant)
                and isinstance(item.value, str)
            )
        if isinstance(node, ast.Dict):
            keys = {_constant_dict_key(key) for key in node.keys if key is not None}
            if "client_order_id_reservation" in keys:
                reservation_forwarded = True
    assert wrappers == ["create_disaster_stop_order"]
    assert reservation_forwarded is True


def test_operational_client_order_id_is_never_built_by_slicing():
    violations = [
        item
        for path in _production_sources()
        for item in _client_id_slice_violations(path)
    ]

    # A cryptographic digest projection is generation, not destructive truncation
    # of caller input.  No route, preview, writer, or compatibility helper is
    # exempt from the prohibition against slicing a client-order identifier.
    allowed = {
        ("account_client_order_id.py", "generate_account_client_order_id"),
    }
    unexpected = [
        item
        for item in violations
        if (item["path"], item["function"]) not in allowed
    ]
    assert unexpected == []

    generator = _function(
        ROOT / "account_client_order_id.py", "generate_account_client_order_id"
    )
    slices = [
        node
        for node in ast.walk(generator)
        if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Slice)
    ]
    assert len(slices) == 1
    assert isinstance(slices[0].value, ast.Name)
    assert slices[0].value.id == "digest"
    assert isinstance(slices[0].slice.upper, ast.Name)
    assert slices[0].slice.upper.id == "ACCOUNT_CLIENT_ORDER_ID_HASH_HEX_LENGTH"

    # Prove that the legacy sliced EFG ID can never leave its manual diagnostic
    # through a factual execution path: every Engine invocation hard-codes dry_run.
    dry_run_helper = _function(
        ROOT / "main.py", "_efg_v1_call_engine_dry_run_with_auth"
    )
    engine_calls = [
        node
        for node in ast.walk(dry_run_helper)
        if isinstance(node, ast.Call) and _call_name(node) == "run_execution_engine"
    ]
    assert len(engine_calls) == 2
    for call in engine_calls:
        keywords = {item.arg: item.value for item in call.keywords if item.arg}
        assert isinstance(keywords.get("dry_run"), ast.Constant)
        assert keywords["dry_run"].value is True


def test_private_create_order_sink_requires_reserved_attempt_before_call():
    path = ROOT / "broker.py"
    boundary = _function(path, "_create_order_with_reserved_attempt")
    keyword_names = [item.arg for item in boundary.args.kwonlyargs]
    reservation_index = keyword_names.index("client_order_id_reservation")
    assert boundary.args.kw_defaults[reservation_index] is None  # required keyword

    calls = [node for node in ast.walk(boundary) if isinstance(node, ast.Call)]
    raw = [
        node
        for node in calls
        if isinstance(node.func, ast.Attribute) and node.func.attr == "create_order"
    ]
    verification = [
        node
        for node in calls
        if _call_name(node) == "_broker_account_reservation_verification"
    ]
    claims = [
        node
        for node in calls
        if _call_name(node) == "claim_account_client_order_send_authorization"
    ]
    assert len(raw) == len(verification) == len(claims) == 1
    assert verification[0].lineno < claims[0].lineno < raw[0].lineno

    # No second private raw writer can silently appear anywhere in the project.
    inventory = _call_inventory()
    assert [item["function"] for item in inventory.raw_create_order_calls] == [
        "_create_order_with_reserved_attempt"
    ]

    # Also reject alias-based bypasses such as ``writer = ex.create_order`` or
    # ``getattr(ex, 'create_order')`` which would evade a call-only inventory.
    attribute_references = []
    dynamic_lookups = []
    for source in _production_sources():
        relative = source.relative_to(ROOT).as_posix()
        for node in ast.walk(_tree(source)):
            if isinstance(node, ast.Attribute) and node.attr == "create_order":
                attribute_references.append((relative, node.lineno))
            if (
                isinstance(node, ast.Call)
                and _call_name(node) in {"getattr", "setattr"}
                and len(node.args) >= 2
                and isinstance(node.args[1], ast.Constant)
                and node.args[1].value == "create_order"
            ):
                dynamic_lookups.append((relative, node.lineno, _call_name(node)))
    assert attribute_references == [("broker.py", raw[0].lineno)]
    assert dynamic_lookups == []

    # A stop replacement must be an explicit cancel/create through the same
    # reservation boundary.  ``edit_order`` may be implemented by an exchange
    # as an implicit cancel/create and cannot prove a fresh clientOrderID.
    edit_order_references = []
    for source in _production_sources():
        relative = source.relative_to(ROOT).as_posix()
        for node in ast.walk(_tree(source)):
            if isinstance(node, ast.Attribute) and node.attr in {
                "edit_order",
                "editOrder",
            }:
                edit_order_references.append((relative, node.lineno, node.attr))
    assert edit_order_references == []

    public_stop_writer = _function(
        ROOT / "broker.py", "create_disaster_stop_order"
    )
    assert any(
        isinstance(node, ast.Call)
        and _call_name(node) == "_broker_factual_writes_enabled"
        for node in ast.walk(public_stop_writer)
    )


def test_public_writers_preserve_exact_client_order_id_validation_status():
    path = ROOT / "broker.py"
    directly_validating_writers = {
        "place_market_order",
        "create_disaster_stop_order",
        "replace_position_stop_order",
        "managed_close_position_market",
    }

    for writer in directly_validating_writers:
        function = _function(path, writer)
        source = ast.unparse(function)
        assert "validate_broker_client_order_id" in source
        assert "startswith('CLIENT_ORDER_ID_')" in source

    # The compatibility close writer delegates validation to the sole private
    # boundary and returns its exact status instead of replacing it.
    close_writer = _function(path, "close_position_market")
    close_source = ast.unparse(close_writer)
    assert "_create_order_with_reserved_attempt" in close_source
    assert "create_result.get('status')" in close_source


def test_legacy_exchange_create_order_alias_is_statically_unreachable():
    """The compatibility hook must never alias, patch, or call exchange.create_order."""

    function = _function(ROOT / "main.py", "_dshm_v1_patch_exchange_create_order")
    assert isinstance(function.body[0], ast.If)
    assert any(isinstance(node, ast.Return) for node in function.body[0].body)
    assert isinstance(function.body[1], ast.Return)
    alias_lookups = [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and _call_name(node) == "getattr"
        and len(node.args) >= 2
        and isinstance(node.args[1], ast.Constant)
        and node.args[1].value == "create_order"
    ]
    assert alias_lookups == []
    assert not any(
        isinstance(node, ast.Call)
        and _call_name(node) == "setattr"
        and any(
            isinstance(argument, ast.Constant) and argument.value == "create_order"
            for argument in node.args
        )
        for node in ast.walk(function)
    )
