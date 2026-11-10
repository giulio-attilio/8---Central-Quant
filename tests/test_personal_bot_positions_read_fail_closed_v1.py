"""Position reads in personal signal bots must never turn an error into empty state."""

import ast
import json
from pathlib import Path

import pytest

from redis_bandwidth import install_position_read_timeout


ROOT = Path(__file__).resolve().parents[1]
MODULES = ("trendpro", "donkey", "meme")


def _load_helpers(module_name, *, read_result=None, read_error=None):
    source = ROOT / "bots" / f"{module_name}.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    wanted = {"redis_get_json", "carregar_posicoes"}
    nodes = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in wanted
    ]
    assert {node.name for node in nodes} == wanted

    def bandwidth_redis_get(_redis, _key, *, caller):
        assert caller == f"bots.{module_name}"
        if read_error is not None:
            raise read_error
        return read_result

    namespace = {
        "bandwidth_redis_get": bandwidth_redis_get,
        "redis": object(),
        "POSITIONS_KEY": f"{module_name}:positions",
        "__name__": f"bots.{module_name}",
        "json": json,
    }
    module = ast.Module(body=nodes, type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, str(source), "exec"), namespace)
    return namespace


@pytest.mark.parametrize("module_name", MODULES)
def test_position_read_error_is_not_converted_to_empty_positions(module_name):
    namespace = _load_helpers(module_name, read_error=OSError("offline"))

    with pytest.raises(RuntimeError, match="REDIS_JSON_READ_FAILED"):
        namespace["carregar_posicoes"]()


@pytest.mark.parametrize("module_name", MODULES)
@pytest.mark.parametrize("read_result", ["not-json", "[]", "0"])
def test_malformed_or_non_mapping_position_state_fails_closed(module_name, read_result):
    namespace = _load_helpers(module_name, read_result=read_result)

    with pytest.raises(RuntimeError, match="REDIS_JSON_READ_FAILED|POSITIONS_READ_INVALID"):
        namespace["carregar_posicoes"]()


@pytest.mark.parametrize("module_name", MODULES)
def test_missing_position_key_remains_an_empty_mapping(module_name):
    namespace = _load_helpers(module_name, read_result=None)

    assert namespace["carregar_posicoes"]() == {}


@pytest.mark.parametrize("module_name", MODULES)
def test_non_position_json_reads_keep_existing_fallback(module_name):
    namespace = _load_helpers(module_name, read_error=OSError("offline"))

    assert namespace["redis_get_json"]("unrelated:key", ["fallback"]) == ["fallback"]


class _FakeHTTPClient:
    def __init__(self):
        self.calls = []
        self.closed = False

    def post(self, url, *args, **kwargs):
        self.calls.append((url, args, kwargs))
        return "response"

    def close(self):
        self.closed = True


class _FakeHTTP:
    def __init__(self, client):
        self._client = client


class _FakeRedis:
    def __init__(self, http_client):
        self._http = _FakeHTTP(http_client)


def test_position_get_timeout_is_per_request_and_does_not_change_other_commands():
    underlying = _FakeHTTPClient()
    redis_client = _FakeRedis(underlying)
    install_position_read_timeout(
        redis_client, "trendpro:positions", timeout_seconds=7.5
    )
    bounded = redis_client._http._client

    bounded.post("https://redis.invalid", json=["GET", "trendpro:positions"])
    bounded.post("https://redis.invalid", json=["GET", "trendpro:signals"])
    bounded.post("https://redis.invalid", json=["SET", "trendpro:positions", "{}"])

    assert underlying.calls[0][2]["timeout"] == 7.5
    assert "timeout" not in underlying.calls[1][2]
    assert "timeout" not in underlying.calls[2][2]


def test_position_get_timeout_is_idempotent_and_preserves_close():
    underlying = _FakeHTTPClient()
    redis_client = _FakeRedis(underlying)
    install_position_read_timeout(redis_client, "donkey:positions")
    wrapper = redis_client._http._client

    install_position_read_timeout(redis_client, "donkey:positions")
    wrapper.close()

    assert redis_client._http._client is wrapper
    assert underlying.closed is True


@pytest.mark.parametrize("timeout_seconds", [0, -1, 61, "bad"])
def test_position_get_timeout_rejects_invalid_bounds(timeout_seconds):
    redis_client = _FakeRedis(_FakeHTTPClient())

    with pytest.raises(RuntimeError, match="POSITION_READ_TIMEOUT_INVALID"):
        install_position_read_timeout(
            redis_client, "memepro:positions", timeout_seconds=timeout_seconds
        )


def test_position_get_timeout_fails_closed_if_sdk_internal_seam_changes():
    redis_client = _FakeRedis(object())

    with pytest.raises(RuntimeError, match="POSITION_READ_TIMEOUT_CLIENT_UNSUPPORTED"):
        install_position_read_timeout(redis_client, "memepro:positions")
