from __future__ import annotations

import ast
import copy
import json
import threading
import time
import unittest
from pathlib import Path

from redis_bandwidth import build_bounded_event_history_payload


ROOT = Path(__file__).resolve().parents[1]
TURTLE_PATH = ROOT / "bots" / "turtle.py"
TURTLE_SOURCE = TURTLE_PATH.read_text(encoding="utf-8")
TURTLE_TREE = ast.parse(TURTLE_SOURCE, filename=str(TURTLE_PATH))

EVENT_FUNCTIONS = (
    "_set_turtle_events_persist_health",
    "_turtle_events_exception_code",
    "_fail_turtle_events_persist",
    "_decode_turtle_events_value",
    "_build_turtle_events_payload",
    "_append_turtle_event_bounded",
    "redis_list_append",
)
EVENT_HEALTH_KEYS = (
    "events_persist_status",
    "events_persist_last_at",
    "events_persist_count",
    "events_persist_bytes",
    "events_persist_trimmed_count",
    "events_persist_last_error",
)


def _function(name: str) -> ast.FunctionDef:
    return next(
        node
        for node in TURTLE_TREE.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    )


def _load_functions(names: tuple[str, ...], namespace: dict) -> None:
    module = ast.Module(
        body=[copy.deepcopy(_function(name)) for name in names],
        type_ignores=[],
    )
    ast.fix_missing_locations(module)
    exec(compile(module, str(TURTLE_PATH), "exec"), namespace)


class FakeRedisBandwidth:
    def __init__(self, raw=None, *, get_error=None, set_error=None, get_delay=0.0):
        self.raw = raw
        self.get_error = get_error
        self.set_error = set_error
        self.get_delay = get_delay
        self.get_calls = []
        self.set_calls = []

    def get(self, client, key, *, caller):
        self.get_calls.append((client, key, caller))
        if self.get_delay:
            time.sleep(self.get_delay)
        if self.get_error is not None:
            raise self.get_error
        return self.raw

    def set(self, client, key, value, *, caller):
        self.set_calls.append((client, key, value, caller))
        if self.set_error is not None:
            raise self.set_error
        self.raw = value
        return True


def _runtime(
    raw=None,
    *,
    max_count=5000,
    max_bytes=4 * 1024 * 1024,
    get_error=None,
    set_error=None,
    get_delay=0.0,
    last_warning=None,
):
    fake = FakeRedisBandwidth(
        raw,
        get_error=get_error,
        set_error=set_error,
        get_delay=get_delay,
    )
    health = {
        "last_warning": last_warning,
        "events_persist_status": "NOT_ATTEMPTED",
        "events_persist_last_at": None,
        "events_persist_count": 0,
        "events_persist_bytes": 0,
        "events_persist_trimmed_count": 0,
        "events_persist_last_error": None,
    }
    namespace = {
        "__name__": "central_bots.turtle_isolated_test",
        "json": json,
        "threading": threading,
        "redis": object(),
        "redis_lock": threading.Lock(),
        "events_redis_lock": threading.Lock(),
        "EVENTS_KEY": "turtle_pro:events",
        "TURTLE_EVENTS_MAX_COUNT": max_count,
        "TURTLE_EVENTS_MAX_SERIALIZED_BYTES": max_bytes,
        "HEALTH": health,
        "data_hora_sp_str": lambda: "13/08/2026 12:34",
        "bandwidth_build_bounded_event_history_payload": build_bounded_event_history_payload,
        "bandwidth_redis_get": fake.get,
        "bandwidth_redis_set": fake.set,
        "redis_get_json": lambda _key, default: list(default) if isinstance(default, list) else default,
        "redis_set_json": lambda _key, _value: True,
    }
    _load_functions(EVENT_FUNCTIONS, namespace)
    return namespace, fake


def _decoded(fake: FakeRedisBandwidth):
    return json.loads(fake.raw)


class TurtleEventsRedisBoundedStorageV1Tests(unittest.TestCase):
    def test_four_mib_budget_fits_worst_case_upstash_json_command_envelope(self):
        budget = 4 * 1024 * 1024
        worst_case_value = "\\" * budget
        request_body = json.dumps(
            ["SET", "turtle_pro:events", worst_case_value],
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")

        self.assertIn(
            "TURTLE_EVENTS_MAX_SERIALIZED_BYTES = 4 * 1024 * 1024",
            TURTLE_SOURCE,
        )
        self.assertLess(len(request_body), 10_485_760)

    def test_small_list_preserves_content_and_uses_one_set(self):
        original = [{"id": "old", "kind": "SIGNAL"}]
        namespace, fake = _runtime(json.dumps(original, ensure_ascii=False))
        new_event = {"id": "new", "kind": "TP50"}

        self.assertTrue(namespace["redis_list_append"]("turtle_pro:events", new_event))

        self.assertEqual(_decoded(fake), original + [new_event])
        self.assertEqual(len(fake.set_calls), 1)
        self.assertEqual(namespace["HEALTH"]["events_persist_status"], "OK")
        self.assertEqual(namespace["HEALTH"]["events_persist_trimmed_count"], 0)

    def test_count_limit_keeps_last_5000_before_byte_cap(self):
        original = [{"id": index} for index in range(5000)]
        namespace, fake = _runtime(
            json.dumps(original),
            max_count=5000,
            max_bytes=10 * 1024 * 1024,
        )

        self.assertTrue(namespace["redis_list_append"]("turtle_pro:events", {"id": 5000}))

        stored = _decoded(fake)
        self.assertEqual(len(stored), 5000)
        self.assertEqual(stored[0]["id"], 1)
        self.assertEqual(stored[-1]["id"], 5000)
        self.assertEqual(namespace["HEALTH"]["events_persist_status"], "TRIMMED_BY_COUNT")
        self.assertEqual(namespace["HEALTH"]["events_persist_trimmed_count"], 1)

    def test_byte_limit_removes_only_oldest_and_preserves_order(self):
        events = [
            {"id": "oldest", "blob": "a" * 60},
            {"id": "middle", "blob": "b" * 60},
            {"id": "newest", "blob": "c" * 60},
        ]
        expected = events[1:]
        budget = len(json.dumps(expected, ensure_ascii=False).encode("utf-8"))
        namespace, fake = _runtime(
            json.dumps(events[:2], ensure_ascii=False),
            max_bytes=budget,
        )

        self.assertTrue(namespace["redis_list_append"]("turtle_pro:events", events[2]))

        self.assertEqual(_decoded(fake), expected)
        self.assertLessEqual(len(fake.raw.encode("utf-8")), budget)
        self.assertEqual(namespace["HEALTH"]["events_persist_status"], "TRIMMED_BY_BYTES")
        self.assertEqual(namespace["HEALTH"]["events_persist_trimmed_count"], 1)

    def test_payload_exactly_at_budget_is_not_trimmed(self):
        events = [
            {"id": 1, "text": "ação" * 10},
            {"id": 2, "text": "posição" * 10},
        ]
        final_json = json.dumps(events, ensure_ascii=False)
        budget = len(final_json.encode("utf-8"))
        namespace, fake = _runtime(
            json.dumps(events[:1], ensure_ascii=False),
            max_bytes=budget,
        )

        self.assertTrue(namespace["redis_list_append"]("turtle_pro:events", events[1]))

        self.assertEqual(fake.raw, final_json)
        self.assertEqual(len(fake.raw.encode("utf-8")), budget)
        self.assertEqual(namespace["HEALTH"]["events_persist_status"], "OK")

    def test_payload_one_byte_over_budget_trims_only_the_oldest(self):
        events = [
            {"id": "old", "text": "a" * 20},
            {"id": "new", "text": "b" * 20},
        ]
        full_bytes = len(json.dumps(events, ensure_ascii=False).encode("utf-8"))
        namespace, fake = _runtime(
            json.dumps(events[:1], ensure_ascii=False),
            max_bytes=full_bytes - 1,
        )

        self.assertTrue(namespace["redis_list_append"]("turtle_pro:events", events[1]))

        self.assertEqual(_decoded(fake), events[1:])
        self.assertEqual(namespace["HEALTH"]["events_persist_status"], "TRIMMED_BY_BYTES")
        self.assertLessEqual(len(fake.raw.encode("utf-8")), full_bytes - 1)

    def test_utf8_and_json_escaping_match_the_final_serializer_at_boundary(self):
        event = {
            "id": "special",
            "text": "a\u00e7\u00e3o \U0001f680 \\\"aspas\\\" \\\\ barra\nlinha\x01",
        }
        final_json = json.dumps([event], ensure_ascii=False)
        budget = len(final_json.encode("utf-8"))
        namespace, fake = _runtime(None, max_bytes=budget)

        self.assertTrue(namespace["redis_list_append"]("turtle_pro:events", event))

        self.assertEqual(fake.raw, final_json)
        self.assertEqual(len(fake.raw.encode("utf-8")), budget)
        self.assertEqual(_decoded(fake), [event])

    def test_single_event_over_budget_does_not_set_or_replace_history(self):
        raw = json.dumps([{"id": "preserved"}])
        namespace, fake = _runtime(
            raw,
            max_bytes=128,
            last_warning="watchdog: preserve this warning",
        )

        result = namespace["redis_list_append"](
            "turtle_pro:events",
            {"id": "huge", "blob": "x" * 300},
        )

        self.assertFalse(result)
        self.assertEqual(fake.raw, raw)
        self.assertEqual(fake.set_calls, [])
        self.assertEqual(namespace["HEALTH"]["events_persist_status"], "EVENT_TOO_LARGE")
        self.assertEqual(
            namespace["HEALTH"]["last_warning"],
            "watchdog: preserve this warning",
        )

    def test_get_failure_does_not_set(self):
        namespace, fake = _runtime(
            json.dumps([{"id": "preserved"}]),
            get_error=RuntimeError("offline"),
        )

        self.assertFalse(namespace["redis_list_append"]("turtle_pro:events", {"id": "new"}))

        self.assertEqual(fake.set_calls, [])
        self.assertEqual(namespace["HEALTH"]["events_persist_status"], "GET_FAILED")

    def test_json_parse_failure_does_not_set(self):
        raw = "{not-json"
        namespace, fake = _runtime(raw)

        self.assertFalse(namespace["redis_list_append"]("turtle_pro:events", {"id": "new"}))

        self.assertEqual(fake.raw, raw)
        self.assertEqual(fake.set_calls, [])
        self.assertEqual(namespace["HEALTH"]["events_persist_status"], "PARSE_FAILED")

    def test_absent_key_can_create_first_event(self):
        namespace, fake = _runtime(None)
        event = {"id": "first"}

        self.assertTrue(namespace["redis_list_append"]("turtle_pro:events", event))

        self.assertEqual(_decoded(fake), [event])
        self.assertEqual(len(fake.set_calls), 1)

    def test_empty_json_list_can_append_first_event(self):
        namespace, fake = _runtime("[]")
        event = {"id": "first"}

        self.assertTrue(namespace["redis_list_append"]("turtle_pro:events", event))

        self.assertEqual(_decoded(fake), [event])
        self.assertEqual(len(fake.set_calls), 1)

    def test_wrong_json_type_does_not_set(self):
        for raw in ('{"id": "object"}', '"string"', "1", "true"):
            with self.subTest(raw=raw):
                namespace, fake = _runtime(raw)

                self.assertFalse(
                    namespace["redis_list_append"]("turtle_pro:events", {"id": "new"})
                )
                self.assertEqual(fake.set_calls, [])
                self.assertEqual(namespace["HEALTH"]["events_persist_status"], "PARSE_FAILED")

    def test_two_threads_do_not_lose_updates(self):
        namespace, fake = _runtime("[]", get_delay=0.02)
        start = threading.Barrier(3)
        results = []

        def append(event_id):
            start.wait()
            results.append(
                namespace["redis_list_append"](
                    "turtle_pro:events",
                    {"id": event_id},
                )
            )

        threads = [threading.Thread(target=append, args=(event_id,)) for event_id in ("A", "B")]
        for thread in threads:
            thread.start()
        start.wait()
        for thread in threads:
            thread.join(timeout=2)

        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertEqual(results, [True, True])
        self.assertEqual({event["id"] for event in _decoded(fake)}, {"A", "B"})
        self.assertEqual(len(fake.set_calls), 2)

    def test_existing_oversized_key_self_heals_on_first_valid_write(self):
        original = [
            {"id": index, "blob": chr(97 + index) * 90}
            for index in range(5)
        ]
        new_event = {"id": 5, "blob": "z" * 90}
        expected_tail = [original[-1], new_event]
        budget = len(json.dumps(expected_tail, ensure_ascii=False).encode("utf-8"))
        namespace, fake = _runtime(
            json.dumps(original, ensure_ascii=False),
            max_bytes=budget,
        )

        self.assertTrue(namespace["redis_list_append"]("turtle_pro:events", new_event))

        self.assertEqual(_decoded(fake), expected_tail)
        self.assertLessEqual(len(fake.raw.encode("utf-8")), budget)
        self.assertEqual(namespace["HEALTH"]["events_persist_status"], "TRIMMED_BY_BYTES")

    def test_existing_get_events_reader_contract_remains_list_of_dicts(self):
        expected = [{"id": 1}, {"id": 2}]
        namespace = {"redis_get_json": lambda _key, _default: expected, "EVENTS_KEY": "turtle_pro:events"}
        _load_functions(("get_events",), namespace)

        result = namespace["get_events"]()

        self.assertIs(result, expected)
        self.assertTrue(all(isinstance(event, dict) for event in result))

    def test_observability_fields_contain_only_scalars(self):
        namespace, _fake = _runtime("[]")

        self.assertTrue(namespace["redis_list_append"]("turtle_pro:events", {"id": 1}))

        scalar_types = (str, int, float, bool, type(None))
        for key in EVENT_HEALTH_KEYS:
            with self.subTest(key=key):
                self.assertIsInstance(namespace["HEALTH"][key], scalar_types)

    def test_success_clears_only_previous_events_set_warning(self):
        namespace, _fake = _runtime(
            "[]",
            last_warning="redis set turtle_pro:events: old upstream error",
        )

        self.assertTrue(namespace["redis_list_append"]("turtle_pro:events", {"id": 1}))

        self.assertIsNone(namespace["HEALTH"]["last_warning"])

    def test_success_preserves_unrelated_warning(self):
        namespace, _fake = _runtime("[]", last_warning="watchdog: unrelated")

        self.assertTrue(namespace["redis_list_append"]("turtle_pro:events", {"id": 1}))

        self.assertEqual(namespace["HEALTH"]["last_warning"], "watchdog: unrelated")

    def test_set_failure_is_fail_open_and_keeps_remote_history(self):
        raw = json.dumps([{"id": "preserved"}])
        namespace, fake = _runtime(
            raw,
            set_error=RuntimeError("ERR max request size exceeded; payload omitted"),
        )

        self.assertFalse(namespace["redis_list_append"]("turtle_pro:events", {"id": "new"}))

        self.assertEqual(fake.raw, raw)
        self.assertEqual(len(fake.set_calls), 1)
        self.assertEqual(namespace["HEALTH"]["events_persist_status"], "SET_FAILED")
        self.assertEqual(
            namespace["HEALTH"]["events_persist_last_error"],
            "RuntimeError:MAX_REQUEST_SIZE_EXCEEDED",
        )
        self.assertTrue(namespace["HEALTH"]["last_warning"].startswith("redis set turtle_pro:events:"))

    def test_other_keys_keep_the_generic_append_path(self):
        persisted = []
        namespace, fake = _runtime("[]")
        namespace["redis_get_json"] = lambda _key, _default: [{"id": 1}, {"id": 2}]
        namespace["redis_set_json"] = lambda key, value: persisted.append((key, value)) or True

        self.assertTrue(namespace["redis_list_append"]("turtle_pro:signals", {"id": 3}, max_len=2))

        self.assertEqual(fake.get_calls, [])
        self.assertEqual(fake.set_calls, [])
        self.assertEqual(persisted, [("turtle_pro:signals", [{"id": 2}, {"id": 3}])])

    def test_no_parsed_events_cache_or_function_local_import_was_added(self):
        module_assignments = set()
        for node in TURTLE_TREE.body:
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    if isinstance(target, ast.Name):
                        module_assignments.add(target.id.lower())

        self.assertFalse(any("events" in name and "cache" in name for name in module_assignments))
        for name in EVENT_FUNCTIONS:
            function = _function(name)
            self.assertFalse(any(isinstance(node, (ast.Import, ast.ImportFrom)) for node in ast.walk(function)))

    def test_lock_order_has_no_redis_to_events_inversion(self):
        event_lock_callers = {
            "_append_turtle_event_bounded",
            "redis_list_append",
            "record_event",
            "reset_paper_route",
        }
        redis_locked_blocks = []
        for node in ast.walk(TURTLE_TREE):
            if not isinstance(node, ast.With):
                continue
            lock_names = {
                child.id
                for item in node.items
                for child in ast.walk(item.context_expr)
                if isinstance(child, ast.Name)
            }
            if "redis_lock" in lock_names:
                redis_locked_blocks.append(node)

        self.assertGreaterEqual(len(redis_locked_blocks), 4)
        for locked_block in redis_locked_blocks:
            nested_names = {
                child.id
                for child in ast.walk(locked_block)
                if isinstance(child, ast.Name)
            }
            nested_calls = {
                child.func.id
                for child in ast.walk(locked_block)
                if isinstance(child, ast.Call) and isinstance(child.func, ast.Name)
            }
            self.assertNotIn("events_redis_lock", nested_names)
            self.assertTrue(event_lock_callers.isdisjoint(nested_calls))


if __name__ == "__main__":
    unittest.main()
