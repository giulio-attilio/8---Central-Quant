import ast
import threading
from pathlib import Path

import pytest


SOURCE = Path(__file__).resolve().parents[1] / "bots" / "falcon.py"


def _load_position_read_helpers(*, read_result=None, read_error=None):
    source = SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    wanted = {"redis_get_json", "get_positions"}
    nodes = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in wanted
    ]
    assert {node.name for node in nodes} == wanted
    module = ast.Module(body=nodes, type_ignores=[])
    ast.fix_missing_locations(module)

    class RedisReadLock:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def bandwidth_redis_get(_redis, _key, *, caller):
        assert caller == "central_bots.falcon"
        if read_error is not None:
            raise read_error
        return read_result

    namespace = {
        "threading": threading,
        "redis_lock": RedisReadLock(),
        "position_mutation_lock": threading.RLock(),
        "redis": object(),
        "POSITIONS_KEY": "falcon:positions",
        "__name__": "central_bots.falcon",
        "HEALTH": {},
        "bandwidth_redis_get": bandwidth_redis_get,
    }
    exec(compile(module, str(SOURCE), "exec"), namespace)
    return namespace


def test_get_positions_returns_valid_persisted_mapping():
    positions = {"trade-1": {"symbol": "BTC/USDT"}}
    namespace = _load_position_read_helpers(read_result=positions)

    assert namespace["get_positions"]() == positions


def test_get_positions_fails_closed_on_redis_read_error():
    namespace = _load_position_read_helpers(read_error=OSError("offline"))

    with pytest.raises(RuntimeError, match="FALCON_POSITIONS_READ_FAILED|redis get falcon:positions failed"):
        namespace["get_positions"]()


@pytest.mark.parametrize("invalid_value", [[], 0])
def test_get_positions_rejects_non_mapping_persisted_values(invalid_value):
    namespace = _load_position_read_helpers(read_result=invalid_value)

    with pytest.raises(RuntimeError, match="FALCON_POSITIONS_READ_INVALID"):
        namespace["get_positions"]()


def test_get_positions_fails_closed_on_malformed_json():
    namespace = _load_position_read_helpers(read_result="not-json")

    with pytest.raises(RuntimeError, match="redis get falcon:positions failed"):
        namespace["get_positions"]()


def test_other_redis_json_reads_keep_the_existing_default_fallback():
    namespace = _load_position_read_helpers(read_error=OSError("offline"))

    assert namespace["redis_get_json"]("falcon:other", ["fallback"]) == ["fallback"]
