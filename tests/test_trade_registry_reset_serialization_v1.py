from __future__ import annotations

import ast
from contextlib import nullcontext
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "trade_registry.py"


class _ProbeLock:
    def __init__(self):
        self.depth = 0
        self.enter_count = 0

    def __enter__(self):
        self.depth += 1
        self.enter_count += 1
        return self

    def __exit__(self, *_exc):
        self.depth -= 1
        return False


def _load_reset_function():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "reset_trade_registry"
    )
    lock = _ProbeLock()
    writes = []

    def save_registry(payload):
        assert lock.depth == 1, "Registry reset must hold the shared RLock while saving"
        writes.append(payload)
        return True

    namespace = {
        "_lock": lock,
        "_c3_closed_repair_writer_mutation_v1": lambda _writer: nullcontext(),
        "_empty_registry": lambda: {"open_trades": {}, "closed_trades": []},
        "save_registry": save_registry,
    }
    module = ast.Module(body=[function], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), str(SOURCE), "exec"), namespace)
    return namespace["reset_trade_registry"], lock, writes


def test_reset_without_confirmation_does_not_lock_or_write():
    reset, lock, writes = _load_reset_function()

    result = reset(confirm=False)

    assert result == {"ok": False, "error": "CONFIRM_REQUIRED"}
    assert lock.enter_count == 0
    assert writes == []


def test_confirmed_reset_holds_the_shared_lock_for_the_write():
    reset, lock, writes = _load_reset_function()

    result = reset(confirm=True)

    assert result == {"ok": True, "action": "TRADE_REGISTRY_RESET"}
    assert lock.enter_count == 1
    assert writes == [{"open_trades": {}, "closed_trades": []}]
