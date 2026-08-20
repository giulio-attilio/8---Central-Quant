from __future__ import annotations

import ast
import copy
import json
import threading
from pathlib import Path

from redis_bandwidth import build_bounded_event_history_payload


ROOT = Path(__file__).resolve().parents[1]
FALCON_PATH = ROOT / "bots" / "falcon.py"
FALCON_SOURCE = FALCON_PATH.read_text(encoding="utf-8")
FALCON_TREE = ast.parse(FALCON_SOURCE, filename=str(FALCON_PATH))

EVENT_FUNCTIONS = (
    "_set_falcon_events_persist_health",
    "_falcon_events_exception_code",
    "_fail_falcon_events_persist",
    "_decode_falcon_events_value",
    "_build_falcon_events_payload",
    "_append_falcon_event_bounded",
    "redis_list_append",
)


def _function(name: str) -> ast.FunctionDef:
    return next(
        node
        for node in FALCON_TREE.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    )


def _load_functions(namespace: dict) -> None:
    module = ast.Module(
        body=[copy.deepcopy(_function(name)) for name in EVENT_FUNCTIONS],
        type_ignores=[],
    )
    ast.fix_missing_locations(module)
    exec(compile(module, str(FALCON_PATH), "exec"), namespace)


class FakeRedisBandwidth:
    def __init__(self, raw=None, *, get_error=None, set_error=None):
        self.raw = raw
        self.get_error = get_error
        self.set_error = set_error
        self.get_calls = []
        self.set_calls = []

    def get(self, client, key, *, caller):
        self.get_calls.append((client, key, caller))
        if self.get_error is not None:
            raise self.get_error
        return self.raw

    def set(self, client, key, value, *, caller):
        self.set_calls.append((client, key, value, caller))
        if self.set_error is not None:
            raise self.set_error
        self.raw = value
        return True


def _runtime(raw=None, *, max_count=5000, max_bytes=4 * 1024 * 1024, get_error=None, set_error=None):
    fake = FakeRedisBandwidth(raw, get_error=get_error, set_error=set_error)
    health = {
        "last_warning": None,
        "events_persist_status": "NOT_ATTEMPTED",
        "events_persist_last_at": None,
        "events_persist_count": 0,
        "events_persist_bytes": 0,
        "events_persist_trimmed_count": 0,
        "events_persist_last_error": None,
    }
    namespace = {
        "__name__": "central_bots.falcon_isolated_test",
        "json": json,
        "redis": object(),
        "redis_lock": threading.Lock(),
        "events_redis_lock": threading.Lock(),
        "EVENTS_KEY": "falcon:events",
        "FALCON_EVENTS_MAX_COUNT": max_count,
        "FALCON_EVENTS_MAX_SERIALIZED_BYTES": max_bytes,
        "HEALTH": health,
        "data_hora_sp_str": lambda: "20/08/2026 12:34",
        "bandwidth_build_bounded_event_history_payload": build_bounded_event_history_payload,
        "bandwidth_redis_get": fake.get,
        "bandwidth_redis_set": fake.set,
        "redis_get_json": lambda _key, default: list(default) if isinstance(default, list) else default,
        "redis_set_json": lambda _key, _value: True,
    }
    _load_functions(namespace)
    return namespace, fake


def _decoded(fake: FakeRedisBandwidth):
    return json.loads(fake.raw)


def test_four_mib_budget_fits_worst_case_upstash_json_command_envelope():
    budget = 4 * 1024 * 1024
    request_body = json.dumps(
        ["SET", "falcon:events", "\\" * budget],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    assert "FALCON_EVENTS_MAX_SERIALIZED_BYTES = 4 * 1024 * 1024" in FALCON_SOURCE
    assert len(request_body) < 10_485_760


def test_byte_limit_removes_oldest_and_always_keeps_new_fitting_event():
    events = [
        {"id": "oldest", "blob": "a" * 60},
        {"id": "middle", "blob": "b" * 60},
        {"id": "newest", "blob": "c" * 60},
    ]
    expected = events[1:]
    budget = len(json.dumps(expected, ensure_ascii=False).encode("utf-8"))
    namespace, fake = _runtime(json.dumps(events[:2]), max_bytes=budget)

    assert namespace["redis_list_append"]("falcon:events", events[2]) is True
    assert _decoded(fake) == expected
    assert len(fake.raw.encode("utf-8")) <= budget
    assert namespace["HEALTH"]["events_persist_status"] == "TRIMMED_BY_BYTES"


def test_count_limit_keeps_new_event_and_newest_contiguous_tail():
    original = [{"id": index} for index in range(3)]
    namespace, fake = _runtime(json.dumps(original), max_count=3, max_bytes=4096)

    assert namespace["redis_list_append"]("falcon:events", {"id": 3}) is True
    assert _decoded(fake) == [{"id": 1}, {"id": 2}, {"id": 3}]
    assert namespace["HEALTH"]["events_persist_status"] == "TRIMMED_BY_COUNT"


def test_single_event_over_budget_is_fail_open_and_preserves_remote_history():
    raw = json.dumps([{"id": "preserved"}])
    namespace, fake = _runtime(raw, max_bytes=128)

    assert namespace["redis_list_append"](
        "falcon:events",
        {"id": "huge", "blob": "x" * 300},
    ) is False
    assert fake.raw == raw
    assert fake.set_calls == []
    assert namespace["HEALTH"]["events_persist_status"] == "EVENT_TOO_LARGE"


def test_corrupt_or_wrong_type_remote_history_is_never_replaced():
    for raw in ("{not-json", '{"id":"object"}', '"string"'):
        namespace, fake = _runtime(raw)
        assert namespace["redis_list_append"]("falcon:events", {"id": "new"}) is False
        assert fake.raw == raw
        assert fake.set_calls == []
        assert namespace["HEALTH"]["events_persist_status"] == "PARSE_FAILED"


def test_get_and_set_failures_preserve_remote_history():
    namespace, fake = _runtime("[]", get_error=RuntimeError("offline"))
    assert namespace["redis_list_append"]("falcon:events", {"id": "new"}) is False
    assert fake.set_calls == []
    assert namespace["HEALTH"]["events_persist_status"] == "GET_FAILED"

    raw = json.dumps([{"id": "preserved"}])
    namespace, fake = _runtime(
        raw,
        set_error=RuntimeError("ERR max request size exceeded; payload omitted"),
    )
    assert namespace["redis_list_append"]("falcon:events", {"id": "new"}) is False
    assert fake.raw == raw
    assert namespace["HEALTH"]["events_persist_status"] == "SET_FAILED"
    assert namespace["HEALTH"]["events_persist_last_error"] == "RuntimeError:MAX_REQUEST_SIZE_EXCEEDED"


def test_other_falcon_histories_keep_generic_count_bounded_path():
    persisted = []
    namespace, fake = _runtime("[]")
    namespace["redis_get_json"] = lambda _key, _default: [{"id": 1}, {"id": 2}]
    namespace["redis_set_json"] = lambda key, value: persisted.append((key, value)) or True

    assert namespace["redis_list_append"]("falcon:signals", {"id": 3}, max_len=2) is True
    assert fake.get_calls == []
    assert fake.set_calls == []
    assert persisted == [("falcon:signals", [{"id": 2}, {"id": 3}])]


def test_lock_order_has_no_redis_to_events_inversion():
    event_lock_callers = {
        "_append_falcon_event_bounded",
        "redis_list_append",
        "record_event",
    }
    for node in ast.walk(FALCON_TREE):
        if not isinstance(node, ast.With):
            continue
        lock_names = {
            child.id
            for item in node.items
            for child in ast.walk(item.context_expr)
            if isinstance(child, ast.Name)
        }
        if "redis_lock" not in lock_names:
            continue
        nested_names = {
            child.id
            for child in ast.walk(node)
            if isinstance(child, ast.Name)
        }
        nested_calls = {
            child.func.id
            for child in ast.walk(node)
            if isinstance(child, ast.Call) and isinstance(child.func, ast.Name)
        }
        assert "events_redis_lock" not in nested_names
        assert event_lock_callers.isdisjoint(nested_calls)
