from __future__ import annotations

import ast
import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
MAIN_TREE = ast.parse(MAIN.read_text(encoding="utf-8"), filename=str(MAIN))


def _load_functions(names: set[str], namespace: dict | None = None) -> dict:
    selected = [
        node
        for node in MAIN_TREE.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names
    ]
    found = {node.name for node in selected}
    assert found == names, f"missing functions in main.py: {sorted(names - found)}"
    module = ast.Module(body=sorted(selected, key=lambda node: node.lineno), type_ignores=[])
    values = dict(namespace or {})
    exec(compile(module, str(MAIN), "exec"), values)
    return values


def _valid_divergence(**overrides):
    payload = {
        "ok": True,
        "broker_bingx_open_count": 0,
        "central_live_count": 0,
        "only_bingx_count": 0,
        "only_central_count": 0,
        "live_without_stop_count": 0,
    }
    payload.update(overrides)
    return payload


def _preflight_namespace(divergence):
    def collect(name, collector, fallback, _started_at, diagnostics):
        try:
            value = collector()
        except Exception as exc:
            diagnostics[name] = {
                "status": "ERROR",
                "ok": False,
                "error_type": type(exc).__name__,
            }
            return dict(fallback or {})
        diagnostics[name] = {
            "status": "OK",
            "ok": True,
            "timeout_seconds": 1.0,
            "elapsed_ms": 0.0,
        }
        return value

    return {
        "time": time,
        "FALCON_REAL_PILOT_PREFLIGHT_CHECKLIST_V1_VERSION": "test-version",
        "FALCON_REAL_PILOT_PREFLIGHT_TOTAL_DEADLINE_SECONDS": 10.0,
        "FALCON_REAL_PILOT_PREFLIGHT_CHECKLIST_V1_LATEST_FILE": "unused-latest.json",
        "FALCON_REAL_PILOT_PREFLIGHT_CHECKLIST_V1_EVENTS_FILE": "unused-events.jsonl",
        "MANUAL_POSITION_OWNERSHIP_ISOLATION_V1_VERSION": "test-ownership-policy",
        "c3_runtime_seam_v1": SimpleNamespace(
            c3_closed_repair_writer_coordination_status_v1=lambda: {
                "enabled": True,
                "coordination_ready": True,
                "runtime_activation_allowed": True,
                "registered_writer_count": 19,
                "all_writers_registered": True,
                "inflight_mutations": 0,
                "shared_lock_backend_ready": True,
                "maintenance_lease_store_ready": True,
                "registry_interlock_ready": True,
                "activation_receipt_verified": True,
                "source_hashes_verified": True,
                "rollback_ready": True,
                "kill_switch_ready": True,
            }
        ),
        "_frpp_v1_collect": collect,
        "_frpp_v1_env_snapshot": lambda: {
            "enable_real_trading_bool": False,
            "broker_dry_run_bool": True,
            "central_real_execution_enabled_bool": False,
            "central_real_pilot_enabled_bool": False,
            "falcon_mode": "VERIFY",
        },
        "_frpp_v1_get_bots_snapshot": lambda: {
            "FALCON": {
                "token_configured": True,
                "chat_configured": True,
                "health": {"mode": "VERIFY"},
            },
            "PREDATOR": {
                "health": {
                    "execution_mode": "PAPER",
                    "predator_real_sent_or_live_event_count": 0,
                    "predator_lifecycle_audit_ok": True,
                }
            },
            "TURTLE": {"health": {"mode": "PAPER"}},
        },
        "_frpp_v1_get_falcon_audit": lambda divergence_snapshot=None: {
            "ok": True,
            "live_audit_status": "OK",
            "bad_execution_events_total_count": 0,
            "bad_execution_events_acked_count": 0,
            "bad_execution_events_unacked_count": 0,
            "divergence": divergence_snapshot,
            "divergence_evidence_source": "INJECTED_PREFLIGHT_SNAPSHOT",
        },
        "_frpp_v1_get_broker_ready": lambda: {"ready": {"ok": True}, "broker": {}},
        "_frpp_v1_get_divergence": lambda: divergence,
        "_frpp_v1_get_runtime": lambda: {
            "ok": True,
            "status": "OK",
            "current_memory_pct": 10,
            "peak_memory_pct_observed": 20,
            "restart_like_count_24h": 0,
        },
        "_frpp_v1_get_trade_registry_storage": lambda: {
            "status": "OK",
            "registry_file_active": "/data/trade_registry.json",
            "persistent_storage_enabled": True,
            "last_load_ok": True,
            "last_write_ok": True,
            "migration_pending": False,
            "write_allowed": True,
            "temporary_read_only": False,
            "live_entry_readiness": {
                "ok": True,
                "status": "TRADE_REGISTRY_LIVE_ENTRY_STORAGE_READY",
                "checks": {
                    "patch_installed": True,
                    "persistent_path": True,
                    "active_file_exists": True,
                    "last_load_ok": True,
                    "last_write_ok": True,
                    "write_allowed": True,
                    "temporary_read_only_clear": True,
                },
                "read_only": True,
                "write_executed": False,
            },
            "current_counts": {"open_count": 0, "closed_count": 0},
        },
        "_frpp_v1_get_disaster_preview_status": lambda: {
            "ok": True,
            "long_ok": True,
            "short_ok": True,
        },
        "_frpp_v1_safe_sanitize": lambda value: value,
        "_frpp_v1_now": lambda: "2026-08-29T00:00:00Z",
        "_frpp_v1_write_json_atomic": lambda _path, _payload: (True, None),
        "_frpp_v1_append_event": lambda _payload: (True, None),
    }


def _compile_preflight(namespace):
    namespace = _load_functions(
        {
            "_frpp_v1_float",
            "_frpp_v1_int",
            "_frpp_v1_nonnegative_count",
            "_frpp_v1_upper",
            "_frpp_v1_build_checklist",
        },
        namespace,
    )
    return namespace["_frpp_v1_build_checklist"]()


def _build_preflight(divergence):
    return _compile_preflight(_preflight_namespace(divergence))


def _check(payload, code):
    return next(item for item in payload["checks"] if item["code"] == code)


def test_preflight_storage_collector_embeds_exported_live_entry_interlock_result():
    status_calls = []
    readiness_calls = []
    readiness = {
        "ok": True,
        "status": "TRADE_REGISTRY_LIVE_ENTRY_STORAGE_READY",
        "checks": {"write_allowed": True},
        "read_only": True,
        "write_executed": False,
    }

    class Registry:
        @staticmethod
        def falcon_live_entry_storage_readiness():
            readiness_calls.append(True)
            return readiness

    namespace = _load_functions(
        {"_frpp_v1_get_trade_registry_storage"},
        {
            "central_trade_registry": Registry,
            "trade_registry_persistent_storage_fix_v1_status": (
                lambda force=False: status_calls.append(force)
                or {"status": "ACTIVE_PERSISTENT"}
            ),
        },
    )

    result = namespace["_frpp_v1_get_trade_registry_storage"]()

    assert status_calls == [False]
    assert readiness_calls == [True]
    assert result["status"] == "ACTIVE_PERSISTENT"
    assert result["live_entry_readiness"] is readiness


@pytest.mark.parametrize(
    "provider, expected_status",
    [
        (None, "TRADE_REGISTRY_LIVE_ENTRY_STORAGE_READINESS_UNAVAILABLE"),
        (lambda: None, "TRADE_REGISTRY_LIVE_ENTRY_STORAGE_READINESS_INVALID"),
        (
            lambda: (_ for _ in ()).throw(RuntimeError("sensitive detail")),
            "TRADE_REGISTRY_LIVE_ENTRY_STORAGE_READINESS_ERROR",
        ),
    ],
)
def test_preflight_storage_collector_fails_closed_for_invalid_provider(
    provider, expected_status
):
    class Registry:
        falcon_live_entry_storage_readiness = staticmethod(provider) if provider else None

    namespace = _load_functions(
        {"_frpp_v1_get_trade_registry_storage"},
        {
            "central_trade_registry": Registry,
            "trade_registry_persistent_storage_fix_v1_status": (
                lambda force=False: {
                    "ok": True,
                    "status": "ACTIVE_PERSISTENT",
                }
            ),
        },
    )

    result = namespace["_frpp_v1_get_trade_registry_storage"]()
    readiness = result["live_entry_readiness"]

    assert readiness["ok"] is False
    assert readiness["status"] == expected_status
    assert readiness["read_only"] is True
    assert readiness["write_executed"] is False
    assert "sensitive detail" not in json.dumps(result)


def test_preflight_registry_check_uses_exact_live_entry_interlock_result():
    namespace = _preflight_namespace(_valid_divergence())
    namespace["_frpp_v1_get_trade_registry_storage"] = lambda: {
        "ok": True,
        "status": "CLOSED_IDENTITY_MERGE_BLOCKED",
        "registry_file_active": "/data/trade_registry.json",
        "persistent_storage_enabled": True,
        "last_load_ok": True,
        "last_write_ok": True,
        "migration_pending": True,
        "write_allowed": False,
        "temporary_read_only": False,
        "live_entry_readiness": {
            "ok": False,
            "status": "TRADE_REGISTRY_LIVE_ENTRY_STORAGE_NOT_READY",
            "checks": {
                "patch_installed": True,
                "persistent_path": True,
                "active_file_exists": True,
                "last_load_ok": True,
                "last_write_ok": True,
                "write_allowed": False,
                "temporary_read_only_clear": True,
            },
            "read_only": True,
            "write_executed": False,
        },
        "current_counts": {"open_count": 20, "closed_count": 1924},
    }

    payload = _compile_preflight(namespace)
    check = _check(payload, "TRADE_REGISTRY_PERSISTENT_OK")

    assert payload["ok"] is False
    assert payload["manual_rearm_next_step_allowed"] is False
    assert check["ok"] is False
    assert check["blocking"] is True
    assert check["details"]["live_entry_readiness_status"] == (
        "TRADE_REGISTRY_LIVE_ENTRY_STORAGE_NOT_READY"
    )
    assert check["details"]["live_entry_readiness_checks"]["write_allowed"] is False
    assert check["details"]["live_entry_readiness_read_only"] is True
    assert check["details"]["live_entry_readiness_write_executed"] is False


@pytest.mark.parametrize("readiness", [None, {}, {"ok": False}, {"ok": 1}, "ready"])
def test_preflight_registry_check_fails_closed_without_explicit_true_readiness(
    readiness,
):
    namespace = _preflight_namespace(_valid_divergence())
    storage = {
        "status": "ACTIVE_PERSISTENT",
        "registry_file_active": "/data/trade_registry.json",
        "persistent_storage_enabled": True,
        "last_load_ok": True,
        "last_write_ok": True,
        "write_allowed": True,
        "temporary_read_only": False,
        "current_counts": {"open_count": 0, "closed_count": 0},
    }
    if readiness is not None:
        storage["live_entry_readiness"] = readiness
    namespace["_frpp_v1_get_trade_registry_storage"] = lambda: storage

    payload = _compile_preflight(namespace)

    assert payload["ok"] is False
    assert _check(payload, "TRADE_REGISTRY_PERSISTENT_OK")["ok"] is False


def test_preflight_bot_snapshot_uses_only_light_health():
    light_calls = []
    heavy_calls = []

    def light_health(key, cfg):
        light_calls.append((key, cfg["name"]))
        return {
            "name": cfg["name"],
            "enabled": True,
            "loaded": True,
            "health": {"mode": "VERIFY"},
            "health_source": "MODULE_MEMORY_LIGHT",
        }

    namespace = _load_functions(
        {"_frpp_v1_get_bots_snapshot"},
        {
            "BOT_CONFIGS": {
                "FALCON": {"name": "Falcon"},
                "TURTLE": {"name": "Turtle"},
            },
            "light_bot_health": light_health,
            "bot_health": lambda *_args: heavy_calls.append(True) or {},
        },
    )

    payload = namespace["_frpp_v1_get_bots_snapshot"]()

    assert light_calls == [("FALCON", "Falcon"), ("TURTLE", "Turtle")]
    assert heavy_calls == []
    assert payload["FALCON"]["health_source"] == "MODULE_MEMORY_LIGHT"
    assert payload["TURTLE"]["health_source"] == "MODULE_MEMORY_LIGHT"


def test_preflight_bot_snapshot_fails_closed_without_light_health():
    namespace = _load_functions(
        {"_frpp_v1_get_bots_snapshot"},
        {
            "BOT_CONFIGS": {"FALCON": {"name": "Falcon"}},
            "light_bot_health": None,
            "bot_health": lambda *_args: pytest.fail("heavy health must not run"),
        },
    )

    with pytest.raises(RuntimeError, match="light bot health unavailable"):
        namespace["_frpp_v1_get_bots_snapshot"]()


def _deadline_namespace():
    return {
        "threading": threading,
        "time": time,
        "_FRPP_V1_COLLECTOR_LOCK": threading.Lock(),
        "_FRPP_V1_COLLECTOR_INFLIGHT": {},
    }


def test_preflight_deadline_returns_without_waiting_for_blocked_collector():
    namespace = _load_functions(
        {"_frpp_v1_run_with_deadline"},
        _deadline_namespace(),
    )
    run_with_deadline = namespace["_frpp_v1_run_with_deadline"]
    entered = threading.Event()
    release = threading.Event()
    finished = threading.Event()

    def blocked_collector():
        entered.set()
        release.wait(1.0)
        finished.set()
        return {"ok": True}

    started = time.monotonic()
    value, meta = run_with_deadline("blocked", blocked_collector, 0.02)
    elapsed = time.monotonic() - started

    assert entered.is_set()
    assert value is None
    assert meta["status"] == "TIMEOUT"
    assert meta["ok"] is False
    assert meta["worker_daemon"] is True
    assert elapsed < 0.5

    duplicate_value, duplicate_meta = run_with_deadline(
        "blocked",
        lambda: {"ok": True},
        0.02,
    )
    assert duplicate_value is None
    assert duplicate_meta["status"] == "ALREADY_INFLIGHT"

    release.set()
    assert finished.wait(1.0)


def test_preflight_deadline_converts_collector_exception_to_sanitized_error():
    namespace = _load_functions(
        {"_frpp_v1_run_with_deadline"},
        _deadline_namespace(),
    )

    def raises_sensitive_message():
        raise RuntimeError("sensitive-value-must-not-be-returned")

    value, meta = namespace["_frpp_v1_run_with_deadline"](
        "error",
        raises_sensitive_message,
        0.2,
    )

    assert value is None
    assert meta["status"] == "ERROR"
    assert meta["error_type"] == "RuntimeError"
    assert "sensitive-value" not in json.dumps(meta)


def test_preflight_collect_skips_work_after_total_deadline_is_exhausted():
    namespace = _deadline_namespace()
    namespace.update(
        {
            "FALCON_REAL_PILOT_PREFLIGHT_TOTAL_DEADLINE_SECONDS": 0.01,
            "FALCON_REAL_PILOT_PREFLIGHT_COLLECTOR_TIMEOUT_SECONDS": {
                "late": 1.0,
            },
        }
    )
    namespace = _load_functions(
        {"_frpp_v1_run_with_deadline", "_frpp_v1_collect"},
        namespace,
    )
    calls = []
    diagnostics = {}

    value = namespace["_frpp_v1_collect"](
        "late",
        lambda: calls.append(True) or {"ok": True},
        {"ok": False},
        time.monotonic() - 1.0,
        diagnostics,
    )

    assert value == {"ok": False}
    assert calls == []
    assert diagnostics["late"]["status"] == "TOTAL_DEADLINE_EXHAUSTED"
    assert diagnostics["late"]["ok"] is False


def test_preflight_build_uses_real_bounded_collector_with_synthetic_sources():
    namespace = _preflight_namespace(_valid_divergence())
    namespace.pop("_frpp_v1_collect")
    namespace.update(_deadline_namespace())
    namespace.update(
        {
            "FALCON_REAL_PILOT_PREFLIGHT_TOTAL_DEADLINE_SECONDS": 2.0,
            "FALCON_REAL_PILOT_PREFLIGHT_COLLECTOR_TIMEOUT_SECONDS": {
                "env": 0.2,
                "bots": 0.2,
                "falcon_audit": 0.2,
                "broker_ready": 0.2,
                "divergence": 0.2,
                "runtime": 0.2,
                "trade_registry_storage": 0.2,
                "disaster_stop_preview": 0.2,
            },
        }
    )
    namespace = _load_functions(
        {
            "_frpp_v1_run_with_deadline",
            "_frpp_v1_collect",
            "_frpp_v1_float",
            "_frpp_v1_int",
            "_frpp_v1_nonnegative_count",
            "_frpp_v1_upper",
            "_frpp_v1_build_checklist",
        },
        namespace,
    )

    payload = namespace["_frpp_v1_build_checklist"]()

    assert payload["ok"] is True
    assert payload["evidence_collection"]["ok"] is True
    assert payload["evidence_collection"]["failed_collectors"] == []
    assert all(
        meta["ok"] is True
        for meta in payload["evidence_collection"]["collectors"].values()
    )


def test_preflight_timeout_fails_closed_and_still_writes_audit_report():
    divergence = _valid_divergence()
    namespace = _preflight_namespace(divergence)
    base_collect = namespace["_frpp_v1_collect"]
    writes = []
    events = []

    def collect(name, collector, fallback, started_at, diagnostics):
        if name == "broker_ready":
            diagnostics[name] = {
                "status": "TIMEOUT",
                "ok": False,
                "timeout_seconds": 0.01,
                "elapsed_ms": 10.0,
            }
            return dict(fallback or {})
        return base_collect(name, collector, fallback, started_at, diagnostics)

    namespace["_frpp_v1_collect"] = collect
    namespace["_frpp_v1_write_json_atomic"] = lambda path, payload: (
        writes.append((path, payload)) or True,
        None,
    )
    namespace["_frpp_v1_append_event"] = lambda payload: (
        events.append(payload) or True,
        None,
    )

    payload = _compile_preflight(namespace)

    assert payload["ok"] is False
    assert payload["status"] == "PREFLIGHT_REVIEW_REQUIRED"
    assert payload["manual_rearm_next_step_allowed"] is False
    assert payload["no_order_sent"] is True
    assert payload["sent"] is False
    assert payload["rearm_executed"] is False
    assert payload["evidence_collection"]["ok"] is False
    assert payload["evidence_collection"]["failed_collectors"] == ["broker_ready"]
    assert _check(payload, "PREFLIGHT_EVIDENCE_COLLECTION_COMPLETE")["ok"] is False
    assert _check(payload, "BROKER_READY_TRUE")["ok"] is False
    assert payload["diagnostic_write"]["latest_ok"] is True
    assert payload["diagnostic_write"]["events_ok"] is True
    assert len(writes) == 1
    assert len(events) == 1


def test_preflight_divergence_timeout_skips_audit_and_broker_collectors():
    namespace = _preflight_namespace(_valid_divergence())
    base_collect = namespace["_frpp_v1_collect"]
    audit_calls = []
    broker_calls = []

    def collect(name, collector, fallback, started_at, diagnostics):
        if name == "divergence":
            diagnostics[name] = {
                "status": "TIMEOUT",
                "ok": False,
                "timeout_seconds": 0.01,
                "elapsed_ms": 10.0,
            }
            return dict(fallback or {})
        return base_collect(name, collector, fallback, started_at, diagnostics)

    namespace["_frpp_v1_collect"] = collect
    namespace["_frpp_v1_get_falcon_audit"] = (
        lambda _snapshot=None: audit_calls.append(True) or {}
    )
    namespace["_frpp_v1_get_broker_ready"] = (
        lambda: broker_calls.append(True) or {}
    )

    payload = _compile_preflight(namespace)

    assert payload["ok"] is False
    assert payload["sent"] is False
    assert audit_calls == []
    assert broker_calls == []
    collectors = payload["evidence_collection"]["collectors"]
    assert collectors["divergence"]["status"] == "TIMEOUT"
    assert collectors["falcon_audit"]["status"] == "SKIPPED_DEPENDENCY_UNAVAILABLE"
    assert collectors["broker_ready"]["status"] == "SKIPPED_DEPENDENCY_UNAVAILABLE"


def test_preflight_audit_timeout_skips_broker_but_keeps_divergence_evidence():
    divergence = _valid_divergence()
    namespace = _preflight_namespace(divergence)
    base_collect = namespace["_frpp_v1_collect"]
    broker_calls = []

    def collect(name, collector, fallback, started_at, diagnostics):
        if name == "falcon_audit":
            diagnostics[name] = {
                "status": "TIMEOUT",
                "ok": False,
                "timeout_seconds": 0.01,
                "elapsed_ms": 10.0,
            }
            return dict(fallback or {})
        return base_collect(name, collector, fallback, started_at, diagnostics)

    namespace["_frpp_v1_collect"] = collect
    namespace["_frpp_v1_get_broker_ready"] = (
        lambda: broker_calls.append(True) or {}
    )

    payload = _compile_preflight(namespace)

    assert payload["ok"] is False
    assert payload["snapshots"]["divergence"] == divergence
    assert broker_calls == []
    collectors = payload["evidence_collection"]["collectors"]
    assert collectors["divergence"]["status"] == "OK"
    assert collectors["falcon_audit"]["status"] == "TIMEOUT"
    assert collectors["broker_ready"]["status"] == "SKIPPED_DEPENDENCY_UNAVAILABLE"


def test_preflight_collects_divergence_once_and_injects_same_snapshot_into_audit():
    divergence = _valid_divergence(broker_bingx_open_count=2, only_bingx_count=2)
    namespace = _preflight_namespace(divergence)
    direct_divergence_calls = []
    audit_snapshots = []

    def audit(divergence_snapshot=None):
        audit_snapshots.append(divergence_snapshot)
        return {
            "ok": True,
            "live_audit_status": "OK",
            "bad_execution_events_total_count": 0,
            "bad_execution_events_acked_count": 0,
            "bad_execution_events_unacked_count": 0,
            "divergence": divergence_snapshot,
            "divergence_evidence_source": "INJECTED_PREFLIGHT_SNAPSHOT",
        }

    namespace["_frpp_v1_get_falcon_audit"] = audit

    def direct_divergence():
        direct_divergence_calls.append(True)
        return divergence

    namespace["_frpp_v1_get_divergence"] = direct_divergence

    payload = _compile_preflight(namespace)

    assert payload["ok"] is True
    assert direct_divergence_calls == [True]
    assert audit_snapshots == [divergence]
    assert audit_snapshots[0] is divergence
    assert payload["evidence_collection"]["collectors"]["divergence"]["status"] == "OK"
    assert payload["evidence_collection"]["collectors"]["falcon_audit"]["divergence_source"] == "SHARED_PREFLIGHT_SNAPSHOT"
    assert payload["summary"]["broker_bingx_open_count"] == 2


@pytest.mark.parametrize(
    "value, expected",
    [
        (0, 0),
        (7, 7),
        ("0", 0),
        (" 12 ", 12),
        (None, None),
        (True, None),
        (False, None),
        (-1, None),
        (0.0, None),
        (0.5, None),
        ("0.0", None),
        ("-1", None),
        ("", None),
        ("zero", None),
    ],
)
def test_preflight_count_evidence_accepts_only_explicit_nonnegative_integers(value, expected):
    namespace = _load_functions({"_frpp_v1_nonnegative_count"})
    assert namespace["_frpp_v1_nonnegative_count"](value) == expected


@pytest.mark.parametrize("missing_key", ["only_central_count", "live_without_stop_count"])
def test_preflight_blocks_when_ownership_evidence_is_missing(missing_key):
    divergence = _valid_divergence()
    divergence.pop(missing_key)

    payload = _build_preflight(divergence)
    ownership = _check(payload, "SYNC_NO_CENTRAL_OWNERSHIP_DIVERGENCE")

    assert payload["ok"] is False
    assert payload["manual_rearm_next_step_allowed"] is False
    assert ownership["ok"] is False
    assert ownership["blocking"] is True
    assert ownership["details"]["evidence_complete"] is False


def test_preflight_blocks_zero_counts_when_divergence_source_failed():
    payload = _build_preflight(_valid_divergence(ok=False, broker_error="unavailable"))

    assert _check(payload, "SYNC_CENTRAL_LIVE_ZERO")["ok"] is False
    assert _check(payload, "SYNC_NO_CENTRAL_OWNERSHIP_DIVERGENCE")["ok"] is False
    assert payload["manual_rearm_next_step_allowed"] is False


@pytest.mark.parametrize("bad_value", [True, -1, 0.0, 0.5, "0.0", "-1", "bad"])
def test_preflight_blocks_malformed_ownership_counts(bad_value):
    payload = _build_preflight(_valid_divergence(only_central_count=bad_value))

    ownership = _check(payload, "SYNC_NO_CENTRAL_OWNERSHIP_DIVERGENCE")
    assert ownership["ok"] is False
    assert ownership["details"]["only_central_count"] is None
    assert payload["ok"] is False


def test_preflight_keeps_manual_external_positions_informational():
    payload = _build_preflight(
        _valid_divergence(broker_bingx_open_count=1, only_bingx_count=1)
    )

    manual = _check(payload, "BINGX_MANUAL_POSITIONS_INFORMATIONAL")
    ownership = _check(payload, "SYNC_NO_CENTRAL_OWNERSHIP_DIVERGENCE")
    assert manual["ok"] is True
    assert manual["blocking"] is False
    assert manual["details"]["manual_external_blocks_falcon"] is False
    assert ownership["ok"] is True
    assert payload["ok"] is True


def _divergence_namespace(broker_result, central_result):
    def broker():
        if isinstance(broker_result, BaseException):
            raise broker_result
        return broker_result

    def central():
        if isinstance(central_result, BaseException):
            raise central_result
        return central_result

    return {
        "_broker_open_positions": broker,
        "_central_live_positions_payload": central,
        "MANUAL_POSITION_OWNERSHIP_ISOLATION_V1_VERSION": "test-policy",
    }


def _run_divergence(broker_result=([], None), central_result=None):
    namespace = _load_functions(
        {
            "_fleag_v1_norm_symbol",
            "_fleag_v1_norm_side",
            "_fleag_v1_divergence_payload",
        },
        _divergence_namespace(broker_result, [] if central_result is None else central_result),
    )
    return namespace["_fleag_v1_divergence_payload"]()


def test_divergence_payload_fails_closed_when_central_source_raises():
    payload = _run_divergence(central_result=RuntimeError("central unavailable"))

    assert payload["ok"] is False
    assert payload["central_error"] == "central unavailable"


def test_divergence_payload_fails_closed_on_invalid_source_shapes():
    broker_invalid = _run_divergence(broker_result=({"not": "a list"}, None))
    central_invalid = _run_divergence(central_result={"not": "a list"})

    assert broker_invalid["ok"] is False
    assert broker_invalid["broker_error"] == "invalid broker open positions payload"
    assert central_invalid["ok"] is False
    assert central_invalid["central_error"] == "invalid central live positions payload"


def test_divergence_payload_preserves_manual_position_isolation_with_valid_sources():
    broker_position = {"symbol": "BTC/USDT:USDT", "side": "LONG", "contracts": 1}
    payload = _run_divergence(broker_result=([broker_position], None), central_result=[])

    assert payload["ok"] is True
    assert payload["only_bingx_count"] == 1
    assert payload["only_central_count"] == 0
    assert payload["manual_external_blocks_falcon"] is False


class _MissingAuditFile:
    @staticmethod
    def exists():
        return False


def _audit_status_namespace(divergence_fn):
    return {
        "json": json,
        "FALCON_LIVE_AUDIT_LATEST_FILE": _MissingAuditFile(),
        "FALCON_LIVE_EXECUTION_AUDIT_GUARD_V1_VERSION": "test-version",
        "MANUAL_POSITION_OWNERSHIP_ISOLATION_V1_VERSION": "test-policy",
        "_fleag_v1_config": lambda: {
            "enabled": True,
            "block_on_previous_failure": True,
            "block_on_divergence": True,
        },
        "_fleag_v1_load_state": lambda: {},
        "_fleag_v1_read_bad_execution_events": lambda limit=200: [],
        "_fleag_v1_dedup_bad_events_v1_3": lambda _events, _state: {
            "unique_bad_events_unacked": [],
            "unique_bad_events_acked": [],
            "unique_bad_events": [],
            "raw_bad_events_total_count": 0,
            "unique_bad_events_total_count": 0,
            "duplicate_bad_events_removed_count": 0,
            "duplicate_bad_event_groups_count": 0,
            "duplicate_bad_event_samples": [],
        },
        "_fleag_v1_divergence_payload": divergence_fn,
        "_fleag_v1_public": lambda value: value,
        "_fleag_v1_now": lambda: "2026-08-29T00:00:00Z",
        "_fleag_v1_read_events": lambda limit=10: [],
    }


def test_live_audit_guard_blocks_when_divergence_evidence_is_unavailable():
    namespace = _load_functions(
        {"falcon_live_execution_audit_guard_v1_status"},
        _audit_status_namespace(
            lambda: {
                "ok": False,
                "broker_error": "unavailable",
                "broker_bingx_open_count": 0,
                "central_live_count": 0,
                "only_bingx_count": 0,
                "only_central_count": 0,
                "live_without_stop_count": 0,
            }
        ),
    )

    payload = namespace["falcon_live_execution_audit_guard_v1_status"]()

    assert payload["ok"] is False
    assert payload["live_audit_status"] == "BLOCKED"
    assert payload["divergence_evidence_source"] == "LIVE_COLLECTION"
    assert any("evidência autoritativa" in reason for reason in payload["reasons"])


def test_live_audit_guard_uses_injected_divergence_without_live_recollection():
    live_collection_calls = []
    namespace = _load_functions(
        {"falcon_live_execution_audit_guard_v1_status"},
        _audit_status_namespace(
            lambda: live_collection_calls.append(True) or _valid_divergence()
        ),
    )
    snapshot = _valid_divergence(
        broker_bingx_open_count=1,
        only_bingx_count=1,
        manual_external_count=1,
    )

    payload = namespace["falcon_live_execution_audit_guard_v1_status"](
        include_recent=False,
        divergence_snapshot=snapshot,
    )

    assert payload["ok"] is True
    assert payload["divergence"] is snapshot
    assert payload["divergence_evidence_source"] == "INJECTED_PREFLIGHT_SNAPSHOT"
    assert payload["manual_position_ownership"]["manual_external_count"] == 1
    assert live_collection_calls == []


def test_live_audit_guard_rejects_invalid_injected_divergence_without_recollection():
    live_collection_calls = []
    namespace = _load_functions(
        {"falcon_live_execution_audit_guard_v1_status"},
        _audit_status_namespace(
            lambda: live_collection_calls.append(True) or _valid_divergence()
        ),
    )

    payload = namespace["falcon_live_execution_audit_guard_v1_status"](
        include_recent=False,
        divergence_snapshot="invalid",
    )

    assert payload["ok"] is False
    assert payload["live_audit_status"] == "BLOCKED"
    assert payload["divergence_evidence_source"] == "INVALID_INJECTED_SNAPSHOT"
    assert live_collection_calls == []
