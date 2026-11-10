"""Position reads in personal signal bots must never turn an error into empty state."""

import ast
import json
import socket
from pathlib import Path

import pytest

from redis_bandwidth import install_redis_get_timeout


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


def test_all_get_timeouts_are_per_request_and_do_not_change_writes():
    underlying = _FakeHTTPClient()
    redis_client = _FakeRedis(underlying)
    install_redis_get_timeout(redis_client, timeout_seconds=7.5)
    bounded = redis_client._http._client

    bounded.post("https://redis.invalid", json=["GET", "trendpro:positions"])
    bounded.post("https://redis.invalid", json=["GET", "trendpro:signals"])
    bounded.post("https://redis.invalid", json=["SET", "trendpro:positions", "{}"])

    assert underlying.calls[0][2]["timeout"] == 7.5
    assert underlying.calls[1][2]["timeout"] == 7.5
    assert "timeout" not in underlying.calls[2][2]


def test_redis_get_timeout_is_idempotent_and_preserves_close():
    underlying = _FakeHTTPClient()
    redis_client = _FakeRedis(underlying)
    install_redis_get_timeout(redis_client)
    wrapper = redis_client._http._client

    install_redis_get_timeout(redis_client)
    wrapper.close()

    assert redis_client._http._client is wrapper
    assert underlying.closed is True


@pytest.mark.parametrize("timeout_seconds", [0, -1, 61, "bad"])
def test_redis_get_timeout_rejects_invalid_bounds(timeout_seconds):
    redis_client = _FakeRedis(_FakeHTTPClient())

    with pytest.raises(RuntimeError, match="REDIS_GET_TIMEOUT_INVALID"):
        install_redis_get_timeout(redis_client, timeout_seconds=timeout_seconds)


def test_redis_get_timeout_fails_closed_if_sdk_internal_seam_changes():
    redis_client = _FakeRedis(object())

    with pytest.raises(RuntimeError, match="REDIS_GET_TIMEOUT_CLIENT_UNSUPPORTED"):
        install_redis_get_timeout(redis_client)


def test_upstash_httpx_redis_get_timeout_with_mock_transport(monkeypatch):
    httpx = pytest.importorskip("httpx")
    upstash_redis = pytest.importorskip("upstash_redis")
    redis = upstash_redis.Redis(
        url="https://redis.invalid",
        token="synthetic-test-token",
        allow_telemetry=False,
    )
    seen = []

    def handler(request):
        command = json.loads(request.content.decode("utf-8"))
        seen.append((command, request.extensions.get("timeout")))
        result = "{}" if command[0].upper() == "GET" else "OK"
        return httpx.Response(200, json={"result": result})

    redis._http._client.close()
    redis._http._client = httpx.Client(
        timeout=None, transport=httpx.MockTransport(handler)
    )
    install_redis_get_timeout(redis, timeout_seconds=7.5)

    def reject_network(*_args, **_kwargs):
        raise AssertionError("network access is blocked in this test")

    try:
        with monkeypatch.context() as patch_network:
            patch_network.setattr(socket, "socket", reject_network)
            patch_network.setattr(socket, "create_connection", reject_network)
            redis.get("trendpro:positions")
            redis.get("trendpro:signals")
            assert redis.set("trendpro:positions", "{}")
    finally:
        redis._http._client.close()

    assert len(seen) == 3
    assert seen[0][0] == ["GET", "trendpro:positions"]
    assert all(value == 7.5 for value in seen[0][1].values())
    assert seen[1][0] == ["GET", "trendpro:signals"]
    assert all(value == 7.5 for value in seen[1][1].values())
    assert seen[2][0][0] == "SET"
    assert all(value is None for value in seen[2][1].values())
