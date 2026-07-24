from __future__ import annotations

import ast
import copy
import importlib.util
import itertools
import json
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
MAIN_PATH = ROOT / "main.py"
REGISTRY_PATH = ROOT / "trade_registry.py"
XRP_TRADE_ID = "FALCON:FALCON15:XRPUSDT:LONG"
XRP_LIFECYCLE_ID = (
    "CENTRAL-FALCON-LIFECYCLE:FALCON-LIVE-FALCON15-1784384114"
)
XRP_CLIENT_ORDER_ID = "FALCON-LIVE-FALCON15-1784384114"
XRP_ORDER_ID = "2078483751332171776"
_MAIN_FUNCTION_NODES = None


@pytest.fixture()
def registry_module(tmp_path, monkeypatch):
    monkeypatch.setenv("CENTRAL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv(
        "TRADE_REGISTRY_FILE", str(tmp_path / "trade_registry.json")
    )
    spec = importlib.util.spec_from_file_location(
        f"_isolated_trade_registry_{tmp_path.name}", REGISTRY_PATH
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    module.TRADE_REGISTRY_LEGACY_FILE = str(
        tmp_path / "legacy-trade-registry-not-present.json"
    )
    return module


def _verify_trade():
    return {
        "trade_id": XRP_TRADE_ID,
        "status": "CLOSED",
        "bot": "FALCON",
        "setup": "FALCON15",
        "symbol": "XRPUSDT",
        "side": "LONG",
        "registry_mode": "VERIFY",
        "execution_mode": "VERIFY",
        "entry": 1.1123,
        "qty": 7,
        "closed_at": "2026-07-01T10:00:00-03:00",
        "metadata": {"verify_marker": "preserve-me"},
    }


def _real_trade(**updates):
    trade = {
        "trade_id": XRP_TRADE_ID,
        "status": "CLOSED",
        "bot": "FALCON",
        "setup": "FALCON15",
        "symbol": "XRPUSDT",
        "side": "LONG",
        "registry_mode": "REAL",
        "execution_mode": "LIVE",
        "lifecycle_id": XRP_LIFECYCLE_ID,
        "client_order_id": XRP_CLIENT_ORDER_ID,
        "broker_order_id": XRP_ORDER_ID,
        "order_id": XRP_ORDER_ID,
        "entry": 1.0871,
        "qty": 9,
        "closed_at": "2026-07-18T18:37:00-03:00",
        "outcome_status": "OUTCOME_RECORDED",
        "outcome_source": "MANUAL_CLOSE_RECONCILIATION",
        "outcome_id": "XRP_MANUAL_TP50_20260718_1837",
        "exit_price": 1.0902,
        "pnl_pct": 0.2851623585686696,
        "metadata": {"real_marker": "preserve-me"},
    }
    trade.update(updates)
    return trade


def _main_function(name):
    global _MAIN_FUNCTION_NODES
    if _MAIN_FUNCTION_NODES is None:
        tree = ast.parse(MAIN_PATH.read_text(encoding="utf-8"))
        _MAIN_FUNCTION_NODES = {
            node.name: node
            for node in tree.body
            if isinstance(node, ast.FunctionDef)
        }
    return _MAIN_FUNCTION_NODES[name]


def _compile_main_functions(names, namespace):
    namespace.setdefault(
        "_trpsf_v1_registry_lock", lambda: threading.RLock()
    )
    nodes = []
    for name in names:
        node = copy.deepcopy(_main_function(name))
        node.decorator_list = []
        nodes.append(node)
    tree = ast.Module(body=nodes, type_ignores=[])
    ast.fix_missing_locations(tree)
    exec(compile(tree, "<isolated-closed-identity-main>", "exec"), namespace)
    return namespace


def _canonical_rows(module, rows):
    return sorted(
        rows,
        key=lambda row: module.closed_trade_identity_state(row)["canonical_key"],
    )


def test_verify_and_real_same_trade_id_are_both_preserved(registry_module):
    verify = _verify_trade()
    real = _real_trade()
    result = registry_module.merge_closed_trade_records(
        [verify, real]
    )
    assert len(result["records"]) == 2
    by_mode = {row["registry_mode"]: row for row in result["records"]}
    assert by_mode["VERIFY"] == verify
    assert by_mode["REAL"]["entry"] == real["entry"]
    assert by_mode["REAL"]["qty"] == real["qty"]
    assert by_mode["REAL"]["lifecycle_id"] == XRP_LIFECYCLE_ID
    assert by_mode["REAL"]["client_order_id"] == XRP_CLIENT_ORDER_ID
    assert by_mode["REAL"]["broker_order_id"] == XRP_ORDER_ID
    assert by_mode["REAL"]["outcome_status"] == real["outcome_status"]
    assert by_mode["REAL"]["outcome_id"] == real["outcome_id"]
    assert by_mode["REAL"]["exit_price"] == real["exit_price"]
    assert by_mode["REAL"]["pnl_pct"] == real["pnl_pct"]
    assert by_mode["REAL"]["metadata"] == real["metadata"]
    diagnostics = result["diagnostics"]
    assert diagnostics["real_verify_collision_group_count"] == 1
    assert diagnostics["distinct_execution_count"] == 2


def test_two_real_executions_with_distinct_lifecycles_remain_separate(
    registry_module,
):
    second = _real_trade(
        lifecycle_id="LC-SECOND",
        client_order_id="CLIENT-SECOND",
        broker_order_id="ORDER-SECOND",
        order_id="ORDER-SECOND",
        entry=1.2,
        qty=10,
        closed_at="2026-07-20T12:00:00-03:00",
    )
    result = registry_module.merge_closed_trade_records(
        [_real_trade(), second]
    )
    assert len(result["records"]) == 2
    assert {row["lifecycle_id"] for row in result["records"]} == {
        XRP_LIFECYCLE_ID,
        "LC-SECOND",
    }


def test_specific_execution_id_conflict_is_not_merged(registry_module):
    first = _real_trade(position_id="POSITION-A")
    second = _real_trade(position_id="POSITION-B")
    result = registry_module.merge_closed_trade_records([first, second])
    assert len(result["records"]) == 2
    assert {row["position_id"] for row in result["records"]} == {
        "POSITION-A",
        "POSITION-B",
    }


def test_reusable_position_id_is_namespaced_by_execution_context(
    registry_module,
):
    first = _real_trade(
        lifecycle_id=None,
        client_order_id=None,
        broker_order_id=None,
        order_id=None,
        position_id="FALCON15:XRPUSDT:LONG",
    )
    second = copy.deepcopy(first)
    second["closed_at"] = "2026-07-19T18:37:00-03:00"
    result = registry_module.merge_closed_trade_records([first, second])
    assert len(result["records"]) == 2
    assert {
        row["closed_at"] for row in result["records"]
    } == {
        "2026-07-18T18:37:00-03:00",
        "2026-07-19T18:37:00-03:00",
    }


def test_equivalent_timestamps_and_decimal_values_deduplicate(
    registry_module,
):
    first = _real_trade()
    second = _real_trade(
        closed_at="2026-07-18T21:37:00Z",
        entry="1.0871000",
        qty="9.000",
        exit_price="1.090200",
    )
    result = registry_module.merge_closed_trade_records([first, second])
    assert len(result["records"]) == 1
    assert result["diagnostics"]["safe_to_commit"] is True


def test_non_closed_record_in_closed_history_blocks_commit(registry_module):
    invalid = _real_trade(status="OPEN")
    result = registry_module.merge_closed_trade_records([invalid])
    assert result["records"] == [invalid]
    assert result["diagnostics"]["invalid_closed_record_count"] == 1
    assert result["diagnostics"]["safe_to_commit"] is False


def test_same_execution_deduplicates_without_losing_factual_fields_in_any_order(
    registry_module,
):
    complete = _real_trade()
    incomplete = {
        "trade_id": XRP_TRADE_ID,
        "status": "CLOSED",
        "bot": "FALCON",
        "setup": "FALCON15",
        "symbol": "XRPUSDT",
        "side": "LONG",
        "registry_mode": "REAL",
        "execution_mode": "LIVE",
        "client_order_id": XRP_CLIENT_ORDER_ID,
        "broker_order_id": XRP_ORDER_ID,
    }
    forward = registry_module.merge_closed_trade_records(
        [complete, incomplete]
    )
    reverse = registry_module.merge_closed_trade_records(
        [incomplete, complete]
    )
    assert forward["records"] == reverse["records"]
    assert len(forward["records"]) == 1
    merged = forward["records"][0]
    assert merged["lifecycle_id"] == XRP_LIFECYCLE_ID
    assert merged["entry"] == 1.0871
    assert merged["qty"] == 9
    assert merged["exit_price"] == 1.0902
    assert merged["outcome_id"] == "XRP_MANUAL_TP50_20260718_1837"
    assert merged["pnl_pct"] == pytest.approx(0.2851623585686696)
    assert merged["metadata"]["real_marker"] == "preserve-me"
    assert forward["diagnostics"]["duplicate_execution_copy_count"] == 1


def test_consistent_identity_bridge_merges_one_component_in_every_permutation(
    registry_module,
):
    lifecycle_only = _real_trade()
    lifecycle_only.pop("client_order_id")
    lifecycle_only.pop("broker_order_id")
    lifecycle_only.pop("order_id")
    client_order_only = _real_trade()
    client_order_only.pop("lifecycle_id")
    connector = _real_trade()
    expected = None
    for rows in itertools.permutations(
        [lifecycle_only, client_order_only, connector]
    ):
        result = registry_module.merge_closed_trade_records(rows)
        assert len(result["records"]) == 1
        assert result["diagnostics"]["ambiguous_identity_bridge_count"] == 0
        serialized = json.dumps(
            result["records"], ensure_ascii=False, sort_keys=True
        )
        expected = expected or serialized
        assert serialized == expected


def test_contradictory_identity_bridge_is_preserved_in_every_permutation(
    registry_module,
):
    first = _real_trade(lifecycle_id="LC-1")
    second = _real_trade(lifecycle_id="LC-2")
    bridge = _real_trade(
        outcome_id="BRIDGE-OUTCOME",
        lifecycle_id=None,
        metadata={"bridge_only": True},
    )
    expected = None
    for rows in itertools.permutations([first, second, bridge]):
        result = registry_module.merge_closed_trade_records(rows)
        assert len(result["records"]) == 3
        assert result["diagnostics"]["ambiguous_identity_bridge_count"] == 1
        by_lifecycle = {
            row.get("lifecycle_id"): row for row in result["records"]
        }
        assert by_lifecycle["LC-1"]["outcome_id"] != "BRIDGE-OUTCOME"
        assert by_lifecycle["LC-2"]["outcome_id"] != "BRIDGE-OUTCOME"
        assert by_lifecycle[None]["outcome_id"] == "BRIDGE-OUTCOME"
        serialized = json.dumps(
            result["records"], ensure_ascii=False, sort_keys=True
        )
        expected = expected or serialized
        assert serialized == expected


def test_incomplete_legacy_identity_only_deduplicates_exact_copies(
    registry_module,
):
    first = {
        "trade_id": XRP_TRADE_ID,
        "status": "CLOSED",
        "registry_mode": "REAL",
        "execution_mode": "LIVE",
        "exit_price": 1.0,
    }
    second = dict(first, exit_price=2.0)
    distinct = registry_module.merge_closed_trade_records([first, second])
    assert len(distinct["records"]) == 2
    assert {
        registry_module.closed_trade_identity_state(row)["identity_kind"]
        for row in distinct["records"]
    } == {"LEGACY_INCOMPLETE_EXACT_ONLY"}
    exact = registry_module.merge_closed_trade_records([first, copy.deepcopy(first)])
    assert len(exact["records"]) == 1


def test_manual_confirmed_outcome_wins_over_generic_closed_in_any_order(
    registry_module,
):
    factual = _real_trade()
    generic = _real_trade(
        outcome_status="CLOSED",
        outcome_source="FALCON",
        outcome_id=None,
        exit_price=None,
        pnl_pct=None,
        metadata={"generic_only": "retained-when-non-conflicting"},
    )
    for rows in ([generic, factual], [factual, generic]):
        result = registry_module.merge_closed_trade_records(rows)
        assert len(result["records"]) == 1
        merged = result["records"][0]
        assert merged["outcome_status"] == "OUTCOME_RECORDED"
        assert merged["outcome_source"] == "MANUAL_CLOSE_RECONCILIATION"
        assert merged["outcome_id"] == "XRP_MANUAL_TP50_20260718_1837"
        assert merged["exit_price"] == 1.0902
        assert (
            merged["metadata"]["generic_only"]
            == "retained-when-non-conflicting"
        )


def test_nested_confirmed_outcome_cannot_be_masked_by_generic_top_level_alias(
    registry_module,
):
    manual = _real_trade(
        outcome_status=None,
        outcome_source=None,
        outcome_id=None,
        exit_price=None,
        metadata={
            "outcome": {
                "outcome_status": "OUTCOME_RECORDED",
                "outcome_source": "MANUAL_CLOSE_RECONCILIATION",
                "outcome_id": "NESTED-MANUAL",
                "exit_price": 1.0902,
                "data_quality": "MANUAL_CONFIRMED",
            }
        },
    )
    generic = _real_trade(
        outcome_status="CLOSED",
        outcome_source="FALCON",
        outcome_id=None,
        exit_price=1.089,
    )
    merged = registry_module.merge_closed_trade_records(
        [generic, manual]
    )["records"][0]
    assert merged["outcome_status"] == "OUTCOME_RECORDED"
    assert merged["outcome_source"] == "MANUAL_CLOSE_RECONCILIATION"
    assert merged["outcome_id"] == "NESTED-MANUAL"
    assert merged["exit_price"] == 1.0902


def test_conflicting_factual_financial_outcomes_are_preserved_fail_closed(
    registry_module,
):
    first = _real_trade(
        outcome_id="FACTUAL-A",
        exit_price=1.0902,
        pnl_pct=0.28,
        data_quality="MANUAL_CONFIRMED",
    )
    second = _real_trade(
        outcome_id="FACTUAL-B",
        exit_price=1.089,
        pnl_pct=0.17,
        data_quality="BROKER_CONFIRMED",
    )
    for rows in ([first, second], [second, first]):
        result = registry_module.merge_closed_trade_records(rows)
        assert len(result["records"]) == 2
        assert {row["outcome_id"] for row in result["records"]} == {
            "FACTUAL-A",
            "FACTUAL-B",
        }
        diagnostics = result["diagnostics"]
        assert diagnostics["safe_to_commit"] is False
        assert diagnostics["financial_conflict_count"] >= 3
        assert diagnostics["financial_conflicts"][0]["reason"] == (
            "FACTUAL_FINANCIAL_OUTCOME_CONFLICT_PRESERVED"
        )


def test_internal_financial_alias_conflict_blocks_commit_projection(
    registry_module,
):
    corrupt = _real_trade(
        outcome={
            "outcome_status": "OUTCOME_RECORDED",
            "outcome_source": "MANUAL_CLOSE_RECONCILIATION",
            "outcome_id": "XRP_MANUAL_TP50_20260718_1837",
            "exit_price": 1.5,
        }
    )
    result = registry_module.merge_closed_trade_records([corrupt])
    assert result["records"] == [corrupt]
    assert result["diagnostics"]["safe_to_commit"] is False
    conflict = result["diagnostics"]["financial_conflicts"][0]
    assert "exit_price" in conflict["financial_conflict_fields"]


def test_conflicting_strong_aliases_are_not_silently_merged(registry_module):
    corrupt = _real_trade()
    corrupt["metadata"] = {
        "trade_lifecycle_id": "LC-CONFLICT",
        "real_marker": "corrupt-copy",
    }
    result = registry_module.merge_closed_trade_records(
        [_real_trade(), corrupt]
    )
    assert len(result["records"]) == 2
    assert result["diagnostics"]["strong_alias_conflict_count"] == 1
    conflict = registry_module.closed_trade_identity_state(corrupt)
    assert conflict["identity_kind"] == "CONFLICT_QUARANTINED"
    assert conflict["merge_tokens"][0].startswith("exact_conflict|")
    assert result["diagnostics"]["safe_to_commit"] is False


def test_legacy_fallback_separates_modes_and_is_deterministic(registry_module):
    verify = _verify_trade()
    real = _real_trade()
    for row in (verify, real):
        for key in (
            "lifecycle_id",
            "client_order_id",
            "broker_order_id",
            "order_id",
        ):
            row.pop(key, None)
    forward = registry_module.merge_closed_trade_records([verify, real])
    reverse = registry_module.merge_closed_trade_records([real, verify])
    assert _canonical_rows(
        registry_module, forward["records"]
    ) == _canonical_rows(registry_module, reverse["records"])
    assert len(forward["records"]) == 2


def test_audit_reports_collisions_without_mutating_input(registry_module):
    real_copy = copy.deepcopy(_real_trade())
    corrupt = _real_trade()
    corrupt["metadata"]["trade_lifecycle_id"] = "LC-CONFLICT"
    rows = [_verify_trade(), _real_trade(), real_copy, corrupt]
    before = copy.deepcopy(rows)
    audit = registry_module.audit_closed_trade_identities(rows)
    assert rows == before
    assert audit["read_only"] is True
    assert audit["write_executed"] is False
    assert audit["automatic_changes"] is False
    assert audit["trade_id_collision_group_count"] == 1
    assert audit["real_verify_collision_group_count"] == 1
    assert audit["strong_alias_conflict_count"] == 1
    assert audit["duplicate_execution_copy_count"] == 1


def test_legacy_closed_lookup_is_fail_closed_when_trade_id_is_ambiguous(
    registry_module, monkeypatch
):
    registry = {
        "open_trades": {},
        "closed_trades": [_verify_trade(), _real_trade()],
    }
    writes = []
    monkeypatch.setattr(
        registry_module, "load_registry", lambda: copy.deepcopy(registry)
    )
    monkeypatch.setattr(
        registry_module, "save_registry", lambda payload: writes.append(payload)
    )
    result = registry_module.update_closed_trade(
        trade_id=XRP_TRADE_ID, metadata={"must_not_write": True}
    )
    assert result["error"] == "CLOSED_TRADE_IDENTITY_AMBIGUOUS"
    assert result["candidate_count"] == 2
    assert writes == []


def test_close_trade_never_rewrites_an_existing_closed_execution(
    registry_module, monkeypatch
):
    registry = {"open_trades": {}, "closed_trades": [_real_trade()]}
    writes = []
    monkeypatch.setattr(
        registry_module, "load_registry", lambda: copy.deepcopy(registry)
    )
    monkeypatch.setattr(
        registry_module, "save_registry", lambda payload: writes.append(payload)
    )
    result = registry_module.close_trade(
        XRP_TRADE_ID,
        exit_price=999,
        pnl_pct=999,
        reason="MUST_NOT_REWRITE",
    )
    assert result["action"] == "TRADE_ALREADY_CLOSED"
    assert result["trade"]["exit_price"] == 1.0902
    assert writes == []


def test_storage_overlay_merge_is_order_independent(registry_module):
    namespace = {
        "json": json,
        "_trpsf_v1_default_registry": lambda: {
            "version": "test",
            "open_trades": {},
            "closed_trades": [],
        },
        "_trpsf_v1_iter_trades": lambda value, preserve_closed_collection_keys=False: (
            [item for item in value.values() if isinstance(item, dict)]
            if isinstance(value, dict)
            else [item for item in (value or []) if isinstance(item, dict)]
        ),
        "_trpsf_v1_trade_key": lambda trade, closed=False: str(
            trade.get("trade_id") or ""
        ),
        "_merge_closed_trade_records_v1": registry_module.merge_closed_trade_records,
        "_trpsf_v1_now": lambda: "fixed",
        "TRADE_REGISTRY_PERSISTENT_STORAGE_FIX_V1_VERSION": "test-v1",
    }
    _compile_main_functions(
        [
            "_trpsf_v1_registry_shape_errors",
            "_trpsf_v1_merge_registries",
        ],
        namespace,
    )
    merge = namespace["_trpsf_v1_merge_registries"]
    left = [
        (
            "active",
            {
                "closed_trades": [_verify_trade()],
                "custom_policy": {"source": "active"},
            },
        )
    ]
    right = [
        (
            "legacy",
            {
                "closed_trades": [_real_trade()],
                "custom_policy": {"source": "legacy"},
            },
        )
    ]
    forward, forward_sources = merge(left + right)
    reverse, reverse_sources = merge(right + left)
    assert _canonical_rows(
        registry_module, forward["closed_trades"]
    ) == _canonical_rows(registry_module, reverse["closed_trades"])
    assert forward == reverse
    assert forward_sources == reverse_sources == ["active", "legacy"]
    assert len(forward["closed_trades"]) == 2
    assert (
        forward["closed_history_identity_merge"][
            "real_verify_collision_group_count"
        ]
        == 1
    )
    assert (
        forward["closed_history_identity_merge"][
            "non_trade_metadata_conflict_count"
        ]
        == 1
    )


def test_snapshot_restore_merge_preserves_verify_and_real(
    registry_module, monkeypatch
):
    saved = []
    events = []
    monkeypatch.setattr(
        registry_module,
        "save_registry",
        lambda payload: saved.append(copy.deepcopy(payload)) or True,
    )
    snapshot = {
        "registry_state": {
            "raw_registry": {
                "open_trades": {},
                "closed_trades": [_real_trade()],
            }
        }
    }
    namespace = {
        "central_trade_registry": registry_module,
        "hashlib": __import__("hashlib"),
        "json": json,
        "_rp_v1_now": lambda: "fixed",
        "_rp_v1_norm_symbol": lambda value: str(value or "").upper(),
        "_rp_v1_norm_side": lambda value: str(value or "").upper(),
        "_rp_v1_norm_bot": lambda value: str(value or "").upper(),
        "REGISTRY_PERSISTENCE_V1_VERSION": "test-v1",
        "_rp_v13_closed_pairs_from_outcome_files": lambda: [],
        "_rp_v1_registry_snapshot_full": lambda: {
            "ok": True,
            "registry_read_known": True,
            "raw_registry": {
                "open_trades": {},
                "closed_trades": [_verify_trade()],
            },
        },
        "_rp_v1_atomic_write_json": lambda path, payload: True,
        "REGISTRY_PERSISTENCE_V1_PRE_RESTORE_BACKUP_FILE": Path(
            "unused-backup.json"
        ),
        "_rp_v1_read_latest_snapshot": lambda: {
            "ok": True,
            "snapshot": snapshot,
        },
        "_rp_v1_append_event": lambda event: events.append(copy.deepcopy(event)),
    }
    _compile_main_functions(
        [
            "_closed_trade_identity_state_v1",
            "_merge_closed_trade_records_v1",
            "_rp_v13_trade_key",
            "_rp_v13_closed_pairs_from_obj",
            "_rp_v13_closed_collection_errors",
            "_rp_v13_snapshot_payload_errors",
            "_rp_v13_closed_pairs_from_snapshot_payload",
            "_rp_v13_merge_closed_history",
            "_rp_v13_as_list",
            "_rp_v13_update_registry_state_with_raw",
            "registry_persistence_v1_restore_from_latest_snapshot",
        ],
        namespace,
    )
    raw = {"open_trades": {}, "closed_trades": [_verify_trade()]}
    merged_raw, diagnostics = namespace["_rp_v13_merge_closed_history"](
        raw, latest_snapshot_payload=snapshot
    )
    assert len(merged_raw["closed_trades"]) == 2
    assert diagnostics["closed_identity"]["distinct_execution_count"] == 2
    state = namespace["_rp_v13_update_registry_state_with_raw"](
        {"snapshot": {}}, merged_raw, diagnostics
    )
    assert len(state["snapshot"]["closed_trades"]) == 2
    snapshot["registry_state"]["raw_registry"] = merged_raw
    restored = namespace[
        "registry_persistence_v1_restore_from_latest_snapshot"
    ](commit=True, ack="RESTORE_REGISTRY_FROM_SNAPSHOT")
    assert restored["committed"] is True
    assert len(saved) == 1
    assert len(saved[0]["closed_trades"]) == 2
    assert len(events) == 1


def test_snapshot_and_restore_real_functions_preserve_both_executions(
    registry_module,
):
    writes = []
    snapshots = []
    backups = []
    events = []
    current = {"open_trades": {}, "closed_trades": [_verify_trade()]}
    prior_snapshot = {
        "registry_state": {
            "raw_registry": {
                "open_trades": {},
                "closed_trades": [_real_trade()],
            }
        }
    }

    def read_latest():
        return {
            "ok": True,
            "snapshot": copy.deepcopy(
                snapshots[-1] if snapshots else prior_snapshot
            ),
        }

    def atomic_write(path, payload):
        if Path(path).name == "unused.json":
            snapshots.append(copy.deepcopy(payload))
        else:
            backups.append(copy.deepcopy(payload))
        return True

    namespace = {
        "central_trade_registry": SimpleNamespace(
            _lock=threading.RLock(),
            save_registry=lambda payload: writes.append(copy.deepcopy(payload)),
            merge_closed_trade_records=registry_module.merge_closed_trade_records,
            closed_trade_identity_state=registry_module.closed_trade_identity_state,
        ),
        "hashlib": __import__("hashlib"),
        "json": json,
        "Path": Path,
        "_rp_v1_now": lambda: "fixed",
        "_rp_v1_norm_symbol": lambda value: str(value or "").upper(),
        "_rp_v1_norm_side": lambda value: str(value or "").upper(),
        "_rp_v1_norm_bot": lambda value: str(value or "").upper(),
        "_rp_v1_build_live_state": lambda **kwargs: {
            "position_found": False,
            "registry_match": False,
            "stop_confirmed_by_central": False,
        },
        "_rp_v1_registry_snapshot_full": lambda: {
            "ok": True,
            "registry_read_known": True,
            "raw_registry": copy.deepcopy(current),
            "snapshot": {},
            "open_count": 0,
        },
        "_rp_v1_read_latest_snapshot": read_latest,
        "_rp_v1_data_dir_status": lambda: {"ok": True},
        "_rp_v1_atomic_write_json": atomic_write,
        "_rp_v1_append_event": lambda event: events.append(copy.deepcopy(event)),
        "_rp_v13_closed_pairs_from_outcome_files": lambda: [],
        "REGISTRY_PERSISTENCE_V1_VERSION": "test-v1",
        "REGISTRY_PERSISTENCE_V1_LATEST_FILE": Path("unused.json"),
        "REGISTRY_PERSISTENCE_V1_PRE_RESTORE_BACKUP_FILE": Path(
            "unused-backup.json"
        ),
    }
    _compile_main_functions(
        [
            "_closed_trade_identity_state_v1",
            "_merge_closed_trade_records_v1",
            "_rp_v13_trade_key",
            "_rp_v13_closed_pairs_from_obj",
            "_rp_v13_closed_collection_errors",
            "_rp_v13_snapshot_payload_errors",
            "_rp_v13_closed_pairs_from_snapshot_payload",
            "_rp_v13_merge_closed_history",
            "_rp_v13_as_list",
            "_rp_v13_update_registry_state_with_raw",
            "registry_persistence_v1_snapshot",
            "registry_persistence_v1_restore_from_latest_snapshot",
        ],
        namespace,
    )
    snapshot_result = namespace["registry_persistence_v1_snapshot"](
        commit=True
    )
    assert snapshot_result["snapshot_save"]["committed"] is True, json.dumps(
        snapshot_result["summary"]["closed_history_merge"],
        ensure_ascii=False,
        sort_keys=True,
    )
    assert len(writes) == 1
    assert len(writes[0]["closed_trades"]) == 2
    restored = namespace[
        "registry_persistence_v1_restore_from_latest_snapshot"
    ](commit=True, ack="RESTORE_REGISTRY_FROM_SNAPSHOT")
    assert restored["committed"] is True
    assert len(writes) == 2
    assert len(writes[-1]["closed_trades"]) == 2
    by_mode = {row["registry_mode"]: row for row in writes[-1]["closed_trades"]}
    assert by_mode["VERIFY"] == _verify_trade()
    factual_real = by_mode["REAL"]
    assert factual_real["lifecycle_id"] == XRP_LIFECYCLE_ID
    assert factual_real["client_order_id"] == XRP_CLIENT_ORDER_ID
    assert factual_real["broker_order_id"] == XRP_ORDER_ID
    assert factual_real["entry"] == 1.0871
    assert factual_real["qty"] == 9
    assert factual_real["outcome_id"] == "XRP_MANUAL_TP50_20260718_1837"
    assert factual_real["exit_price"] == 1.0902
    assert factual_real["pnl_pct"] == pytest.approx(0.2851623585686696)
    assert len(events) == 2


def test_snapshot_identity_conflict_blocks_auto_rebuild_before_side_effect():
    namespace = {
        "_rp_v1_build_live_state": lambda **kwargs: {
            "position_found": True,
            "registry_match": False,
            "stop_confirmed_by_central": True,
        },
        "_rp_v1_registry_snapshot_full": lambda: {
            "ok": True,
            "registry_read_known": True,
            "raw_registry": {"open_trades": {}, "closed_trades": []},
            "snapshot": {},
            "open_count": 0,
        },
        "_rp_v1_read_latest_snapshot": lambda: {"ok": False},
        "_rp_v13_merge_closed_history": lambda raw, latest_snapshot_payload=None: (
            raw,
            {"closed_identity": {"safe_to_commit": False}},
        ),
        "_rp_v13_update_registry_state_with_raw": lambda state, raw, merge_meta=None: {
            **state,
            "raw_registry": raw,
        },
        "registry_persistence_v1_rebuild_from_broker": lambda **kwargs: pytest.fail(
            "auto rebuild reached"
        ),
        "_rp_v1_now": lambda: "fixed",
        "_rp_v1_data_dir_status": lambda: {"ok": True},
        "_rp_v13_as_list": lambda value: list(value or []),
        "_rp_v1_norm_symbol": lambda value: value,
        "_rp_v1_norm_side": lambda value: value,
        "_rp_v1_norm_bot": lambda value: value,
        "central_trade_registry": SimpleNamespace(
            _lock=threading.RLock(),
            save_registry=lambda payload: pytest.fail("Registry writer reached")
        ),
        "REGISTRY_PERSISTENCE_V1_VERSION": "test-v1",
        "REGISTRY_PERSISTENCE_V1_LATEST_FILE": Path("unused.json"),
    }
    _compile_main_functions(["registry_persistence_v1_snapshot"], namespace)
    result = namespace["registry_persistence_v1_snapshot"](
        commit=True, auto_rebuild=True
    )
    assert result["status"] == "CLOSED_IDENTITY_REVIEW_REQUIRED"
    assert result["auto_rebuild"] is None
    assert result["snapshot_save"]["status"] == (
        "SNAPSHOT_BLOCKED_CLOSED_IDENTITY_CONFLICT"
    )


def test_bootstrap_reexecution_is_idempotent_and_confined_to_tmp_path(
    registry_module, tmp_path
):
    active = tmp_path / "active" / "trade_registry.json"
    legacy = tmp_path / "legacy" / "trade_registry.json"
    active.parent.mkdir(parents=True)
    legacy.parent.mkdir(parents=True)
    active.write_text(
        json.dumps({"open_trades": {}, "closed_trades": [_verify_trade()]}),
        encoding="utf-8",
    )
    legacy.write_text(
        json.dumps({"open_trades": {}, "closed_trades": [_real_trade()]}),
        encoding="utf-8",
    )
    written_paths = []

    def read_json(path):
        path = Path(path)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def atomic_write(path, payload):
        resolved = Path(path).resolve()
        assert resolved.is_relative_to(tmp_path.resolve())
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(json.dumps(payload), encoding="utf-8")
        written_paths.append(resolved)
        return True

    namespace = {
        "Path": Path,
        "json": json,
        "central_trade_registry": SimpleNamespace(
            load_registry=lambda: pytest.fail("real Registry loader called"),
            save_registry=lambda payload: pytest.fail(
                "real Registry writer called"
            ),
        ),
        "CENTRAL_DATA_DIR": tmp_path,
        "_TRPSF_V1_STATE": {},
        "_trpsf_v1_active_file": lambda: active,
        "_trpsf_v1_legacy_candidate_paths": lambda: [active, legacy],
        "_trpsf_v1_read_json": read_json,
        "_trpsf_v1_atomic_write_json": atomic_write,
        "_trpsf_v1_public": lambda payload: payload,
        "_trpsf_v1_now": lambda: "fixed",
        "_trpsf_v1_trade_key": lambda trade, closed=False: (
            "id|" + str(trade.get("trade_id") or "")
        ),
        "_merge_closed_trade_records_v1": registry_module.merge_closed_trade_records,
        "TRADE_REGISTRY_PERSISTENT_STORAGE_FIX_V1_VERSION": "test-v1",
        "TRADE_REGISTRY_PERSISTENT_STORAGE_FIX_V1_BACKUP_FILE": tmp_path
        / "backup.json",
        "TRADE_REGISTRY_PERSISTENT_STORAGE_FIX_V1_LATEST_FILE": tmp_path
        / "latest.json",
        "TRADE_REGISTRY_PERSISTENT_STORAGE_FIX_V1_EVENTS_FILE": tmp_path
        / "events.jsonl",
    }
    _compile_main_functions(
        [
            "_trpsf_v1_default_registry",
            "_trpsf_v1_iter_trades",
            "_trpsf_v1_registry_shape_errors",
            "_trpsf_v1_registry_counts",
            "_trpsf_v1_merge_registries",
            "_trpsf_v1_bootstrap_registry",
        ],
        namespace,
    )
    first = namespace["_trpsf_v1_bootstrap_registry"](force=True)
    first_registry = read_json(active)
    statuses = [first] + [
        namespace["_trpsf_v1_bootstrap_registry"](force=True)
        for _ in range(4)
    ]
    second = statuses[-1]
    second_registry = read_json(active)
    assert first["counts_after"]["closed_count"] == 2
    assert second["counts_after"]["closed_count"] == 2
    assert len(first_registry["closed_trades"]) == 2
    assert len(second_registry["closed_trades"]) == 2
    assert first_registry == second_registry
    assert all(status["write_performed"] is False for status in statuses[1:])
    assert written_paths
    assert all(path.is_relative_to(tmp_path.resolve()) for path in written_paths)


def test_bootstrap_quarantines_alias_conflict_without_rewriting_active(
    registry_module, tmp_path
):
    active = tmp_path / "active.json"
    legacy = tmp_path / "legacy.json"
    corrupt = _real_trade()
    corrupt["metadata"]["trade_lifecycle_id"] = "LC-CONFLICT"
    partial = _real_trade()
    partial.pop("lifecycle_id")
    partial.pop("broker_order_id")
    partial.pop("order_id")
    initial = {
        "open_trades": {},
        "closed_trades": [corrupt, partial],
        "storage_fix_version": "test-v1",
    }
    active.write_text(json.dumps(initial), encoding="utf-8")
    legacy.write_text(
        json.dumps({"open_trades": {}, "closed_trades": [corrupt, partial]}),
        encoding="utf-8",
    )
    registry_writes = []

    def read_json(path):
        path = Path(path)
        return (
            json.loads(path.read_text(encoding="utf-8"))
            if path.exists()
            else None
        )

    def atomic_write(path, payload):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
        if path.resolve() == active.resolve():
            registry_writes.append(copy.deepcopy(payload))
        return True

    namespace = {
        "Path": Path,
        "json": json,
        "central_trade_registry": SimpleNamespace(
            load_registry=lambda: pytest.fail("real Registry loader called"),
            save_registry=lambda payload: pytest.fail(
                "real Registry writer called"
            ),
        ),
        "CENTRAL_DATA_DIR": tmp_path,
        "_TRPSF_V1_STATE": {},
        "_trpsf_v1_active_file": lambda: active,
        "_trpsf_v1_legacy_candidate_paths": lambda: [active, legacy],
        "_trpsf_v1_read_json": read_json,
        "_trpsf_v1_atomic_write_json": atomic_write,
        "_trpsf_v1_public": lambda payload: payload,
        "_trpsf_v1_now": lambda: "fixed",
        "_merge_closed_trade_records_v1": registry_module.merge_closed_trade_records,
        "TRADE_REGISTRY_PERSISTENT_STORAGE_FIX_V1_VERSION": "test-v1",
        "TRADE_REGISTRY_PERSISTENT_STORAGE_FIX_V1_BACKUP_FILE": tmp_path
        / "backup.json",
        "TRADE_REGISTRY_PERSISTENT_STORAGE_FIX_V1_LATEST_FILE": tmp_path
        / "latest.json",
        "TRADE_REGISTRY_PERSISTENT_STORAGE_FIX_V1_EVENTS_FILE": tmp_path
        / "events.jsonl",
    }
    _compile_main_functions(
        [
            "_trpsf_v1_default_registry",
            "_trpsf_v1_iter_trades",
            "_trpsf_v1_registry_shape_errors",
            "_trpsf_v1_registry_counts",
            "_trpsf_v1_merge_registries",
            "_trpsf_v1_bootstrap_registry",
        ],
        namespace,
    )
    before = read_json(active)
    for _ in range(5):
        status = namespace["_trpsf_v1_bootstrap_registry"](force=True)
        assert status["status"] == "CLOSED_IDENTITY_MERGE_BLOCKED"
        assert status["write_performed"] is False
        assert read_json(active) == before
    assert registry_writes == []


def test_bootstrap_read_error_is_fail_closed_without_any_write(
    registry_module, tmp_path
):
    active = tmp_path / "trade_registry.json"
    active.write_text("{malformed", encoding="utf-8")
    writes = []
    namespace = {
        "Path": Path,
        "json": json,
        "central_trade_registry": SimpleNamespace(),
        "CENTRAL_DATA_DIR": tmp_path,
        "_TRPSF_V1_STATE": {},
        "_trpsf_v1_active_file": lambda: active,
        "_trpsf_v1_legacy_candidate_paths": lambda: [active],
        "_trpsf_v1_read_json": lambda path: None,
        "_trpsf_v1_atomic_write_json": lambda path, payload: writes.append(
            (path, payload)
        )
        or True,
        "_trpsf_v1_public": lambda payload: payload,
        "_trpsf_v1_now": lambda: "fixed",
        "_merge_closed_trade_records_v1": registry_module.merge_closed_trade_records,
        "TRADE_REGISTRY_PERSISTENT_STORAGE_FIX_V1_VERSION": "test-v1",
        "TRADE_REGISTRY_PERSISTENT_STORAGE_FIX_V1_BACKUP_FILE": tmp_path
        / "backup.json",
        "TRADE_REGISTRY_PERSISTENT_STORAGE_FIX_V1_LATEST_FILE": tmp_path
        / "latest.json",
        "TRADE_REGISTRY_PERSISTENT_STORAGE_FIX_V1_EVENTS_FILE": tmp_path
        / "events.jsonl",
    }
    _compile_main_functions(
        [
            "_trpsf_v1_default_registry",
            "_trpsf_v1_iter_trades",
            "_trpsf_v1_registry_shape_errors",
            "_trpsf_v1_registry_counts",
            "_trpsf_v1_merge_registries",
            "_trpsf_v1_bootstrap_registry",
        ],
        namespace,
    )
    status = namespace["_trpsf_v1_bootstrap_registry"](force=True)
    assert status["status"] == "ACTIVE_REGISTRY_READ_ERROR"
    assert status["write_performed"] is False
    assert status["closed_history_identity_merge"]["safe_to_commit"] is False
    assert namespace["_TRPSF_V1_STATE"]["migration_done"] is False
    assert writes == []
    assert active.read_text(encoding="utf-8") == "{malformed"


def test_bootstrap_backup_failure_preserves_active_and_retries(
    registry_module, tmp_path
):
    active = tmp_path / "active.json"
    legacy = tmp_path / "legacy.json"
    before = {"open_trades": {}, "closed_trades": [_verify_trade()]}
    active.write_text(json.dumps(before), encoding="utf-8")
    legacy.write_text(
        json.dumps({"open_trades": {}, "closed_trades": [_real_trade()]}),
        encoding="utf-8",
    )

    def read_json(path):
        return json.loads(Path(path).read_text(encoding="utf-8"))

    def atomic_write(path, payload):
        if Path(path).name == "backup.json":
            raise OSError("simulated backup failure")
        return True

    namespace = {
        "Path": Path,
        "json": json,
        "central_trade_registry": SimpleNamespace(),
        "CENTRAL_DATA_DIR": tmp_path,
        "_TRPSF_V1_STATE": {},
        "_trpsf_v1_active_file": lambda: active,
        "_trpsf_v1_legacy_candidate_paths": lambda: [active, legacy],
        "_trpsf_v1_read_json": read_json,
        "_trpsf_v1_atomic_write_json": atomic_write,
        "_trpsf_v1_public": lambda payload: payload,
        "_trpsf_v1_now": lambda: "fixed",
        "_merge_closed_trade_records_v1": registry_module.merge_closed_trade_records,
        "TRADE_REGISTRY_PERSISTENT_STORAGE_FIX_V1_VERSION": "test-v1",
        "TRADE_REGISTRY_PERSISTENT_STORAGE_FIX_V1_BACKUP_FILE": tmp_path
        / "backup.json",
        "TRADE_REGISTRY_PERSISTENT_STORAGE_FIX_V1_LATEST_FILE": tmp_path
        / "latest.json",
        "TRADE_REGISTRY_PERSISTENT_STORAGE_FIX_V1_EVENTS_FILE": tmp_path
        / "events.jsonl",
    }
    _compile_main_functions(
        [
            "_trpsf_v1_default_registry",
            "_trpsf_v1_iter_trades",
            "_trpsf_v1_registry_shape_errors",
            "_trpsf_v1_registry_counts",
            "_trpsf_v1_merge_registries",
            "_trpsf_v1_bootstrap_registry",
        ],
        namespace,
    )
    status = namespace["_trpsf_v1_bootstrap_registry"](force=True)
    assert status["status"] == "WRITE_ERROR"
    assert status["write_performed"] is False
    assert namespace["_TRPSF_V1_STATE"]["migration_done"] is False
    assert json.loads(active.read_text(encoding="utf-8")) == before


def test_patched_loader_never_fabricates_empty_registry_after_read_error():
    writes = []
    namespace = {
        "_trpsf_v1_active_file": lambda: Path("unavailable.json"),
        "_trpsf_v1_bootstrap_registry": lambda force=False: pytest.fail(
            "bootstrap called by read-only loader"
        ),
        "_trpsf_v1_read_json": lambda path: None,
        "_trpsf_v1_default_registry": lambda: pytest.fail(
            "empty Registry fabricated"
        ),
        "_trpsf_v1_atomic_write_json": lambda path, payload: writes.append(
            (path, payload)
        ),
        "_TRPSF_V1_STATE": {},
        "_trpsf_v1_registry_lock": lambda: threading.RLock(),
        "central_trade_registry": SimpleNamespace(
            _normalize_registry=lambda payload: payload
        ),
    }
    _compile_main_functions(
        [
            "_trpsf_v1_registry_shape_errors",
            "_trpsf_v1_patched_load_registry",
        ],
        namespace,
    )
    with pytest.raises(
        RuntimeError, match="TRADE_REGISTRY_PERSISTENCE_UNAVAILABLE"
    ):
        namespace["_trpsf_v1_patched_load_registry"]()
    assert writes == []


def test_read_only_preview_uses_only_read_only_loader(registry_module):
    rows = [_verify_trade(), _real_trade(), copy.deepcopy(_real_trade())]
    calls = []
    module = SimpleNamespace(
        load_registry_raw_read_only=lambda: calls.append("raw_read_only")
        or {"closed_trades": copy.deepcopy(rows)},
        merge_closed_trade_records=registry_module.merge_closed_trade_records,
        closed_trade_identity_state=registry_module.closed_trade_identity_state,
        load_registry=lambda: pytest.fail("mutating loader called"),
        save_registry=lambda payload: pytest.fail("writer called"),
    )
    namespace = {
        "central_trade_registry": module,
        "_trpsf_v1_iter_trades": lambda value, preserve_closed_collection_keys=False: list(value or []),
        "_closed_trade_identity_state_v1": registry_module.closed_trade_identity_state,
    }
    _compile_main_functions(
        [
            "_trpsf_v1_registry_shape_errors",
            "trade_registry_closed_identity_audit_v1",
        ],
        namespace,
    )
    payload = namespace["trade_registry_closed_identity_audit_v1"]()
    assert calls == ["raw_read_only"]
    assert payload["ok"] is True
    assert payload["read_only"] is True
    assert payload["write_executed"] is False
    assert payload["current_closed_count"] == 3
    assert payload["projected_closed_count"] == 2
    assert payload["diagnostics"]["real_verify_collision_group_count"] == 1
    assert payload["safe_to_commit"] is True


def test_read_only_preview_processes_290_closed_records_without_writes(
    registry_module,
):
    rows = []
    for number in range(287):
        rows.append(
            _real_trade(
                trade_id=f"FALCON:FALCON15:ASSET{number}USDT:LONG",
                symbol=f"ASSET{number}USDT",
                lifecycle_id=f"LC-{number}",
                client_order_id=f"CLIENT-{number}",
                broker_order_id=f"ORDER-{number}",
                order_id=f"ORDER-{number}",
                outcome_id=f"OUTCOME-{number}",
            )
        )
    rows.extend([_verify_trade(), _real_trade(), copy.deepcopy(_real_trade())])
    assert len(rows) == 290
    module = SimpleNamespace(
        load_registry_raw_read_only=lambda: {
            "closed_trades": copy.deepcopy(rows)
        },
        merge_closed_trade_records=registry_module.merge_closed_trade_records,
        closed_trade_identity_state=registry_module.closed_trade_identity_state,
        load_registry=lambda: pytest.fail("mutating loader called"),
        save_registry=lambda payload: pytest.fail("writer called"),
    )
    namespace = {
        "central_trade_registry": module,
        "_trpsf_v1_iter_trades": lambda value, preserve_closed_collection_keys=False: list(value or []),
        "_closed_trade_identity_state_v1": registry_module.closed_trade_identity_state,
    }
    _compile_main_functions(
        [
            "_trpsf_v1_registry_shape_errors",
            "trade_registry_closed_identity_audit_v1",
        ],
        namespace,
    )
    payload = namespace["trade_registry_closed_identity_audit_v1"]()
    assert payload["current_closed_count"] == 290
    assert payload["projected_closed_count"] == 289
    assert payload["projected_records_removed_as_proven_copies"] == 1
    assert payload["diagnostics"]["real_verify_collision_group_count"] == 1
    collision = next(
        item
        for item in payload["collision_preview"]
        if item["trade_id"] == XRP_TRADE_ID
    )
    assert collision["record_count"] == 3
    assert collision["distinct_execution_identity_count"] == 2
    assert payload["read_only"] is True
    assert payload["write_executed"] is False


def test_manual_audit_route_is_no_store_and_calls_only_read_only_audit():
    calls = []
    payload = {"ok": True, "read_only": True}
    namespace = {
        "trade_registry_closed_identity_audit_v1": lambda: calls.append(
            "audit"
        )
        or payload
    }
    _compile_main_functions(
        ["trade_registry_closed_identity_audit_v1_route"], namespace
    )
    body, status, headers = namespace[
        "trade_registry_closed_identity_audit_v1_route"
    ]()
    assert body == payload
    assert status == 200
    assert headers["Cache-Control"] == "no-store"
    assert headers["Pragma"] == "no-cache"
    assert calls == ["audit"]


def test_normal_health_snapshot_never_runs_full_closed_identity_audit():
    cached = {
        "persistent_storage_enabled": True,
        "status": "ACTIVE_PERSISTENT",
        "counts_before": {"closed_count": 290},
        "counts_after": {"closed_count": 291},
        "closed_history_identity_merge": {
            "input_record_count": 580,
            "output_record_count": 291,
            "trade_id_collision_group_count": 1,
            "distinct_execution_count": 291,
            "real_verify_collision_group_count": 1,
            "strong_alias_conflict_count": 0,
            "ambiguous_identity_bridge_count": 0,
            "safe_to_commit": True,
        },
    }
    namespace = {
        "_TRPSF_V1_ORIGINAL_SNAPSHOT": lambda include_trades=True: {
            "ok": True
        },
        "trade_registry_persistent_storage_fix_v1_status": (
            lambda force=False, read_only=False: cached
        ),
        "trade_registry_closed_identity_audit_v1": lambda: pytest.fail(
            "full audit reached normal health"
        ),
        "TRADE_REGISTRY_PERSISTENT_STORAGE_FIX_V1_VERSION": "test-v1",
        "CENTRAL_DATA_DIR": Path("data"),
    }
    _compile_main_functions(["central_trade_registry_snapshot"], namespace)
    result = namespace["central_trade_registry_snapshot"](include_trades=False)
    audit = result["closed_trade_identity_audit"]
    assert audit["status"] == "CACHED_BOOTSTRAP_DIAGNOSTIC"
    assert audit["current_closed_count"] == 290
    assert audit["projected_closed_count"] == 291
    assert audit["merge_input_record_count"] == 580
    assert audit["merge_output_record_count"] == 291
    assert audit["real_verify_collision_group_count"] == 1


def test_outcome_recovery_preserves_strong_identity_and_factual_close_time(
    registry_module,
):
    namespace = {
        "_rp_v1_norm_symbol": lambda value: str(value or "").upper(),
        "_rp_v1_norm_side": lambda value: str(value or "").upper(),
        "_rp_v1_norm_bot": lambda value: str(value or "").upper(),
        "_rp_v1_now": lambda: "generated-fallback",
    }
    _compile_main_functions(["_rp_v13_outcome_to_closed_trade"], namespace)
    outcome = {
        "ok": True,
        "trade_id": XRP_TRADE_ID,
        "bot": "FALCON",
        "setup": "FALCON15",
        "symbol": "XRPUSDT",
        "side": "LONG",
        "registry_mode": "REAL",
        "execution_mode": "LIVE",
        "lifecycle_id": XRP_LIFECYCLE_ID,
        "client_order_id": XRP_CLIENT_ORDER_ID,
        "order_id": XRP_ORDER_ID,
        "entry": 1.0871,
        "qty": 9,
        "opened_at": "2026-07-18T18:00:00-03:00",
        "closed_at": "2026-07-18T18:37:00-03:00",
        "generated_at": "2026-07-23T12:00:00-03:00",
        "status": "OUTCOME_EVALUATED",
    }
    recovered = namespace["_rp_v13_outcome_to_closed_trade"](outcome)
    assert recovered["lifecycle_id"] == XRP_LIFECYCLE_ID
    assert recovered["client_order_id"] == XRP_CLIENT_ORDER_ID
    assert recovered["broker_order_id"] == XRP_ORDER_ID
    assert recovered["registry_mode"] == "REAL"
    assert recovered["execution_mode"] == "LIVE"
    assert recovered["closed_at"] == "2026-07-18T18:37:00-03:00"
    merged = registry_module.merge_closed_trade_records(
        [_real_trade(), recovered]
    )
    assert len(merged["records"]) == 1


def test_trade_registry_corruption_is_never_replaced_with_empty_registry(
    registry_module,
):
    path = Path(registry_module.TRADE_REGISTRY_FILE)
    path.write_text("{malformed", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        registry_module.load_registry()
    assert path.read_text(encoding="utf-8") == "{malformed"
    assert not Path(str(path) + ".tmp").exists()


@pytest.mark.parametrize(
    "payload",
    [
        {"open_trades": "invalid", "closed_trades": []},
        {"open_trades": {}, "closed_trades": "invalid"},
        {"open_trades": {"x": "invalid"}, "closed_trades": []},
        {"open_trades": {}, "closed_trades": ["invalid"]},
    ],
)
def test_registry_structural_corruption_is_fail_closed(
    registry_module, payload
):
    with pytest.raises(ValueError, match="invalid trade registry"):
        registry_module.save_registry(payload)


def test_merge_invalid_closed_row_blocks_commit_diagnostic(registry_module):
    result = registry_module.merge_closed_trade_records(
        [_verify_trade(), "invalid-row"]
    )
    assert result["records"] == [_verify_trade()]
    diagnostics = result["diagnostics"]
    assert diagnostics["invalid_input_record_count"] == 1
    assert diagnostics["safe_to_commit"] is False


def test_snapshot_registry_loader_error_is_explicit_and_never_fabricates_raw():
    namespace = {
        "central_trade_registry": SimpleNamespace(
            TRADE_REGISTRY_FILE="unused.json",
            load_registry=lambda: (_ for _ in ()).throw(OSError("read")),
        ),
        "central_trade_registry_snapshot": lambda include_trades=True: {},
        "TRADE_REGISTRY_IMPORT_ERROR": None,
    }
    _compile_main_functions(["_rp_v1_registry_snapshot_full"], namespace)
    result = namespace["_rp_v1_registry_snapshot_full"]()
    assert result["ok"] is False
    assert result["registry_read_known"] is False
    assert result["status"] == "TRADE_REGISTRY_READ_ERROR"
    assert result["raw_registry"] is None


def test_manual_closed_recovery_blocks_before_writer_on_registry_read_error():
    writes = []
    namespace = {
        "central_trade_registry": SimpleNamespace(
            load_registry=lambda: (_ for _ in ()).throw(OSError("read")),
            save_registry=lambda payload: writes.append(payload),
        ),
        "_rp_v1_norm_symbol": lambda value: str(value or "").upper(),
        "_rp_v1_norm_side": lambda value: str(value or "").upper(),
        "_rp_v1_norm_bot": lambda value: str(value or "").upper(),
        "_rp_v1_build_live_state": lambda **kwargs: {
            "position_found": False
        },
        "REGISTRY_PERSISTENCE_V1_VERSION": "test-v1",
    }
    _compile_main_functions(
        [
            "_rp_v12_trade_key",
            "_rp_v12_load_raw_registry_safe",
            "registry_persistence_v12_recover_closed_trade_from_params",
        ],
        namespace,
    )
    result = namespace[
        "registry_persistence_v12_recover_closed_trade_from_params"
    ](
        symbol="XRPUSDT",
        side="LONG",
        bot="FALCON",
        setup="FALCON15",
        ack="RESTORE_CLOSED_TRADE_MANUAL",
        commit=True,
        entry=1.0871,
    )
    assert result["status"] == "TRADE_REGISTRY_READ_ERROR"
    assert result["committed"] is False
    assert writes == []


def test_outcome_source_malformed_line_blocks_closed_merge(
    registry_module, tmp_path
):
    events = tmp_path / "outcomes.jsonl"
    events.write_text("{malformed\n", encoding="utf-8")
    namespace = {
        "Path": Path,
        "json": json,
        "hashlib": __import__("hashlib"),
        "central_trade_registry": registry_module,
        "TRADE_CLOSE_OUTCOME_V1_EVENTS_FILE": events,
        "TRADE_CLOSE_OUTCOME_V1_LATEST_FILE": tmp_path / "missing.json",
        "REGISTRY_PERSISTENCE_V1_VERSION": "test-v1",
        "_rp_v1_now": lambda: "fixed",
        "_rp_v1_norm_symbol": lambda value: str(value or "").upper(),
        "_rp_v1_norm_side": lambda value: str(value or "").upper(),
        "_rp_v1_norm_bot": lambda value: str(value or "").upper(),
    }
    _compile_main_functions(
        [
            "_closed_trade_identity_state_v1",
            "_merge_closed_trade_records_v1",
            "_rp_v13_trade_key",
            "_rp_v13_closed_pairs_from_obj",
            "_rp_v13_closed_collection_errors",
            "_rp_v13_snapshot_payload_errors",
            "_rp_v13_closed_pairs_from_snapshot_payload",
            "_rp_v13_outcome_to_closed_trade",
            "_rp_v13_closed_pairs_from_outcome_files_with_status",
            "_rp_v13_closed_pairs_from_outcome_files",
            "_rp_v13_merge_closed_history",
        ],
        namespace,
    )
    merged, diagnostics = namespace["_rp_v13_merge_closed_history"](
        {"open_trades": {}, "closed_trades": [_verify_trade()]}
    )
    assert merged["closed_trades"] == [_verify_trade()]
    assert diagnostics["closed_identity"]["safe_to_commit"] is False
    assert "TRADE_CLOSE_OUTCOME_EVENTS_MALFORMED" in diagnostics[
        "closed_identity"
    ]["source_read_errors"]


def test_predator_auto_closed_planner_preserves_same_trade_id_executions(
    registry_module,
):
    def paper_trade(lifecycle, order_id, closed_at):
        return {
            "trade_id": "PREDATOR:SETUP:XRPUSDT:LONG",
            "status": "CLOSED",
            "bot": "PREDATOR",
            "setup": "SETUP",
            "symbol": "XRPUSDT",
            "side": "LONG",
            "registry_mode": "PAPER",
            "execution_mode": "PAPER",
            "lifecycle_id": lifecycle,
            "client_order_id": f"CLIENT-{lifecycle}",
            "order_id": order_id,
            "broker_order_id": order_id,
            "entry": 1.0,
            "exit_price": 1.1,
            "qty": 9,
            "closed_at": closed_at,
        }

    first = paper_trade("LC-A", "ORDER-A", "2026-07-01T10:00:00Z")
    second = paper_trade("LC-B", "ORDER-B", "2026-07-02T10:00:00Z")
    events = [
        {"trade_id": first["trade_id"], "trade": first, "key": "A"},
        {"trade_id": second["trade_id"], "trade": second, "key": "B"},
    ]
    namespace = {
        "json": json,
        "_pprsf_v1_open_dict": lambda registry: registry.get(
            "open_trades", {}
        ),
        "_pprsf_v1_closed_list": lambda registry: registry.get(
            "closed_trades", []
        ),
        "_pprsf_v1_closed_signature": lambda trade: registry_module.closed_trade_identity_state(
            trade
        )["canonical_key"],
        "_pacs_v1_event_safety": lambda event: (True, "SAFE"),
        "_pacs_v1_explicit_trade_id": lambda event: event.get("trade_id"),
        "_pprsf_v1_build_closed_trade_from_event": lambda event: copy.deepcopy(
            event.get("trade")
        ),
        "_merge_closed_trade_records_v1": registry_module.merge_closed_trade_records,
        "_closed_trade_identity_state_v1": registry_module.closed_trade_identity_state,
        "_pprsf_v1_now": lambda: "fixed",
        "PREDATOR_AUTO_CLOSED_SYNC_V1_VERSION": "test-v1",
    }
    _compile_main_functions(
        [
            "_closed_trade_record_relation_v1",
            "_closed_trade_records_equivalent_v1",
            "_pacs_v1_plan_closed_repairs",
        ],
        namespace,
    )
    plan = namespace["_pacs_v1_plan_closed_repairs"](
        {"open_trades": {}, "closed_trades": []}, events
    )
    assert len(plan["planned"]) == 2
    assert plan["ambiguous"] == []
    assert {
        trade["lifecycle_id"] for trade in plan["planned"]
    } == {"LC-A", "LC-B"}


def test_predator_auto_closed_planner_deduplicates_only_same_execution(
    registry_module,
):
    trade = {
        "trade_id": "PREDATOR:SETUP:XRPUSDT:LONG",
        "status": "CLOSED",
        "bot": "PREDATOR",
        "setup": "SETUP",
        "symbol": "XRPUSDT",
        "side": "LONG",
        "registry_mode": "PAPER",
        "execution_mode": "PAPER",
        "lifecycle_id": "LC-A",
        "client_order_id": "CLIENT-A",
        "order_id": "ORDER-A",
        "entry": 1.0,
        "exit_price": 1.1,
        "qty": 9,
        "closed_at": "2026-07-01T10:00:00Z",
    }
    events = [
        {"trade_id": trade["trade_id"], "trade": copy.deepcopy(trade), "key": "A"},
        {"trade_id": trade["trade_id"], "trade": copy.deepcopy(trade), "key": "A"},
    ]
    namespace = {
        "json": json,
        "_pprsf_v1_open_dict": lambda registry: {},
        "_pprsf_v1_closed_list": lambda registry: [],
        "_pprsf_v1_closed_signature": lambda item: registry_module.closed_trade_identity_state(
            item
        )["canonical_key"],
        "_pacs_v1_event_safety": lambda event: (True, "SAFE"),
        "_pacs_v1_explicit_trade_id": lambda event: event["trade_id"],
        "_pprsf_v1_build_closed_trade_from_event": lambda event: copy.deepcopy(
            event["trade"]
        ),
        "_merge_closed_trade_records_v1": registry_module.merge_closed_trade_records,
        "_closed_trade_identity_state_v1": registry_module.closed_trade_identity_state,
        "_pprsf_v1_now": lambda: "fixed",
        "PREDATOR_AUTO_CLOSED_SYNC_V1_VERSION": "test-v1",
    }
    _compile_main_functions(
        [
            "_closed_trade_record_relation_v1",
            "_closed_trade_records_equivalent_v1",
            "_pacs_v1_plan_closed_repairs",
        ],
        namespace,
    )
    plan = namespace["_pacs_v1_plan_closed_repairs"](
        {"open_trades": {}, "closed_trades": []}, events
    )
    assert len(plan["planned"]) == 1
    assert plan["ambiguous"] == []


def test_bootstrap_without_any_registry_source_never_writes(
    registry_module, tmp_path
):
    active = tmp_path / "missing" / "trade_registry.json"
    writes = []
    namespace = {
        "Path": Path,
        "json": json,
        "central_trade_registry": SimpleNamespace(),
        "CENTRAL_DATA_DIR": tmp_path,
        "_TRPSF_V1_STATE": {},
        "_trpsf_v1_active_file": lambda: active,
        "_trpsf_v1_legacy_candidate_paths": lambda: [],
        "_trpsf_v1_read_json": lambda path: None,
        "_trpsf_v1_atomic_write_json": lambda path, payload: writes.append(
            (path, payload)
        )
        or True,
        "_trpsf_v1_public": lambda payload: payload,
        "_trpsf_v1_now": lambda: "fixed",
        "_merge_closed_trade_records_v1": registry_module.merge_closed_trade_records,
        "TRADE_REGISTRY_PERSISTENT_STORAGE_FIX_V1_VERSION": "test-v1",
        "TRADE_REGISTRY_PERSISTENT_STORAGE_FIX_V1_BACKUP_FILE": tmp_path
        / "backup.json",
        "TRADE_REGISTRY_PERSISTENT_STORAGE_FIX_V1_LATEST_FILE": tmp_path
        / "latest.json",
        "TRADE_REGISTRY_PERSISTENT_STORAGE_FIX_V1_EVENTS_FILE": tmp_path
        / "events.jsonl",
    }
    _compile_main_functions(
        [
            "_trpsf_v1_default_registry",
            "_trpsf_v1_iter_trades",
            "_trpsf_v1_registry_shape_errors",
            "_trpsf_v1_registry_counts",
            "_trpsf_v1_merge_registries",
            "_trpsf_v1_bootstrap_registry",
        ],
        namespace,
    )
    result = namespace["_trpsf_v1_bootstrap_registry"](force=True)
    assert result["status"] == "NO_REGISTRY_SOURCES"
    assert result["write_performed"] is False
    assert writes == []
    assert not active.exists()


def test_bootstrap_open_trade_id_collision_blocks_without_write(
    registry_module, tmp_path
):
    active = tmp_path / "active.json"
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    open_a = {
        "trade_id": "FALCON:FALCON15:XRPUSDT:LONG",
        "status": "OPEN",
        "lifecycle_id": "LC-A",
    }
    open_b = {
        "trade_id": "FALCON:FALCON15:XRPUSDT:LONG",
        "status": "OPEN",
        "lifecycle_id": "LC-B",
    }
    first.write_text(
        json.dumps({"open_trades": {"x": open_a}, "closed_trades": []}),
        encoding="utf-8",
    )
    second.write_text(
        json.dumps({"open_trades": {"x": open_b}, "closed_trades": []}),
        encoding="utf-8",
    )
    writes = []

    def read_json(path):
        path = Path(path)
        return (
            json.loads(path.read_text(encoding="utf-8"))
            if path.exists()
            else None
        )

    namespace = {
        "Path": Path,
        "json": json,
        "central_trade_registry": SimpleNamespace(),
        "CENTRAL_DATA_DIR": tmp_path,
        "_TRPSF_V1_STATE": {},
        "_trpsf_v1_active_file": lambda: active,
        "_trpsf_v1_legacy_candidate_paths": lambda: [first, second],
        "_trpsf_v1_read_json": read_json,
        "_trpsf_v1_trade_key": lambda trade, closed=False: (
            "id|" + str(trade.get("trade_id") or "")
        ),
        "_trpsf_v1_atomic_write_json": lambda path, payload: writes.append(
            (path, payload)
        )
        or True,
        "_trpsf_v1_public": lambda payload: payload,
        "_trpsf_v1_now": lambda: "fixed",
        "_merge_closed_trade_records_v1": registry_module.merge_closed_trade_records,
        "TRADE_REGISTRY_PERSISTENT_STORAGE_FIX_V1_VERSION": "test-v1",
        "TRADE_REGISTRY_PERSISTENT_STORAGE_FIX_V1_BACKUP_FILE": tmp_path
        / "backup.json",
        "TRADE_REGISTRY_PERSISTENT_STORAGE_FIX_V1_LATEST_FILE": tmp_path
        / "latest.json",
        "TRADE_REGISTRY_PERSISTENT_STORAGE_FIX_V1_EVENTS_FILE": tmp_path
        / "events.jsonl",
    }
    _compile_main_functions(
        [
            "_trpsf_v1_default_registry",
            "_trpsf_v1_iter_trades",
            "_trpsf_v1_registry_shape_errors",
            "_trpsf_v1_registry_counts",
            "_trpsf_v1_merge_registries",
            "_trpsf_v1_bootstrap_registry",
        ],
        namespace,
    )
    result = namespace["_trpsf_v1_bootstrap_registry"](force=True)
    assert result["status"] == "OPEN_IDENTITY_MERGE_BLOCKED"
    assert result["write_performed"] is False
    assert writes == []
    assert not active.exists()


def test_storage_force_requires_post_ack_and_header_authentication():
    calls = []
    body = {
        "force": True,
        "ack": "TRADE_REGISTRY_CLOSED_IDENTITY_MIGRATION_V1",
    }
    request = SimpleNamespace(
        method="POST",
        args={},
        get_json=lambda silent=True: body,
    )
    namespace = {
        "request": request,
        "_ee_auth_resolver_v1_resolve": lambda allow_env_fallback=False: {
            "ok": True,
            "matched_source": "request.headers.X-Execution-Auth-Token",
        },
        "TRADE_REGISTRY_STORAGE_FORCE_ACK": (
            "TRADE_REGISTRY_CLOSED_IDENTITY_MIGRATION_V1"
        ),
        "trade_registry_persistent_storage_fix_v1_status": (
            lambda force=False, read_only=False: calls.append(
                (force, read_only)
            )
            or {"ok": True}
        ),
    }
    _compile_main_functions(
        [
            "_trpsf_v1_bool",
            "_trpsf_v1_storage_route_request",
            "trade_registry_persistent_storage_fix_v1_route",
        ],
        namespace,
    )
    payload, status, headers = namespace[
        "trade_registry_persistent_storage_fix_v1_route"
    ]()
    assert status == 200
    assert payload["ok"] is True
    assert calls == [(True, False)]
    assert headers["Cache-Control"] == "no-store"

    calls.clear()
    request.method = "GET"
    request.args = {"force": "true"}
    request.get_json = lambda silent=True: {}
    payload, status, _headers = namespace[
        "trade_registry_persistent_storage_fix_v1_route"
    ]()
    assert status == 400
    assert payload["write_executed"] is False
    assert calls == []


def test_storage_force_rejects_query_or_body_token_and_invalid_auth():
    calls = []
    request = SimpleNamespace(
        method="POST",
        args={"token": "must-not-be-read"},
        get_json=lambda silent=True: {
            "force": True,
            "ack": "TRADE_REGISTRY_CLOSED_IDENTITY_MIGRATION_V1",
        },
    )
    namespace = {
        "request": request,
        "_ee_auth_resolver_v1_resolve": lambda allow_env_fallback=False: {
            "ok": False
        },
        "TRADE_REGISTRY_STORAGE_FORCE_ACK": (
            "TRADE_REGISTRY_CLOSED_IDENTITY_MIGRATION_V1"
        ),
        "trade_registry_persistent_storage_fix_v1_status": (
            lambda force=False, read_only=False: calls.append(
                (force, read_only)
            )
            or {"ok": True}
        ),
    }
    _compile_main_functions(
        [
            "_trpsf_v1_bool",
            "_trpsf_v1_storage_route_request",
            "trade_registry_persistent_storage_fix_v1_route",
        ],
        namespace,
    )
    payload, status, _headers = namespace[
        "trade_registry_persistent_storage_fix_v1_route"
    ]()
    assert status == 403
    assert payload["write_executed"] is False
    assert "must-not-be-read" not in json.dumps(payload)
    assert calls == []


def test_legacy_identity_alias_conflict_is_quarantined_fail_closed(
    registry_module,
):
    corrupt = _real_trade()
    corrupt["metadata"].update(
        {
            "registry_mode": "VERIFY",
            "execution_mode": "VERIFY",
        }
    )
    state = registry_module.closed_trade_identity_state(corrupt)
    assert state["identity_kind"] == "CONFLICT_QUARANTINED"
    assert {
        item["field"] for item in state["alias_conflicts"]
    } >= {"registry_mode", "execution_mode"}

    result = registry_module.merge_closed_trade_records(
        [_real_trade(), corrupt]
    )
    assert len(result["records"]) == 2
    assert result["diagnostics"]["safe_to_commit"] is False
    assert result["diagnostics"]["legacy_alias_conflict_count"] == 1
    assert result["diagnostics"]["strong_alias_conflict_count"] == 0


def test_semantic_financial_alias_conflict_is_preserved_fail_closed(
    registry_module,
):
    first = _real_trade(
        outcome_id="FACTUAL-SAME",
        data_quality="MANUAL_CONFIRMED",
        exit_price=1.0902,
    )
    second = _real_trade(
        outcome_id="FACTUAL-SAME",
        data_quality="MANUAL_CONFIRMED",
        exit_price=None,
        exit=1.089,
    )
    result = registry_module.merge_closed_trade_records([first, second])
    assert len(result["records"]) == 2
    assert result["diagnostics"]["safe_to_commit"] is False
    assert result["diagnostics"]["distinct_execution_count"] == 1
    assert "exit_price" in result["diagnostics"]["financial_conflicts"][0][
        "financial_conflict_fields"
    ]


def test_equivalent_semantic_financial_aliases_merge_without_synthesis(
    registry_module,
):
    first = _real_trade(exit_price=1.0902)
    second = _real_trade(exit_price=None, exit="1.090200")
    result = registry_module.merge_closed_trade_records([first, second])
    assert len(result["records"]) == 1
    assert result["diagnostics"]["safe_to_commit"] is True
    merged = result["records"][0]
    effective_exit = (
        merged.get("exit_price")
        if merged.get("exit_price") not in (None, "")
        else merged.get("exit")
    )
    assert float(effective_exit) == pytest.approx(1.0902)


def test_sparse_copy_with_unknown_ownership_fields_enriches_same_execution(
    registry_module,
):
    sparse = _real_trade()
    sparse.pop("symbol")
    sparse.pop("side")
    result = registry_module.merge_closed_trade_records(
        [_real_trade(), sparse]
    )
    assert len(result["records"]) == 1
    assert result["records"][0]["symbol"] == "XRPUSDT"
    assert result["records"][0]["side"] == "LONG"
    assert result["diagnostics"]["safe_to_commit"] is True


def test_dict_closed_collection_keys_have_one_canonical_contract(
    registry_module,
):
    without_trade_id = _verify_trade()
    without_trade_id.pop("trade_id")
    by_trade_id = {XRP_TRADE_ID: without_trade_id}
    by_numeric_record = {XRP_ORDER_ID: without_trade_id}

    namespace = {"central_trade_registry": registry_module}
    _compile_main_functions(
        [
            "_closed_trade_identity_state_v1",
            "_rp_v13_trade_key",
            "_rp_v13_closed_pairs_from_obj",
            "_trpsf_v1_iter_trades",
        ],
        namespace,
    )

    registry_rows = registry_module._closed_trade_records_from_collection(
        by_trade_id
    )
    snapshot_rows = [
        item[1]
        for item in namespace["_rp_v13_closed_pairs_from_obj"](
            by_trade_id
        )
    ]
    bootstrap_rows = namespace["_trpsf_v1_iter_trades"](
        by_trade_id, preserve_closed_collection_keys=True
    )
    keys = {
        registry_module.closed_trade_identity_state(row)["canonical_key"]
        for row in registry_rows + snapshot_rows + bootstrap_rows
    }
    assert len(keys) == 1
    assert all(row["trade_id"] == XRP_TRADE_ID for row in registry_rows)

    numeric_registry = (
        registry_module._closed_trade_records_from_collection(
            by_numeric_record
        )
    )
    numeric_snapshot = [
        item[1]
        for item in namespace["_rp_v13_closed_pairs_from_obj"](
            by_numeric_record
        )
    ]
    numeric_bootstrap = namespace["_trpsf_v1_iter_trades"](
        by_numeric_record, preserve_closed_collection_keys=True
    )
    numeric_rows = numeric_registry + numeric_snapshot + numeric_bootstrap
    assert all(
        row.get("registry_collection_key") == XRP_ORDER_ID
        and row.get("registry_record_id") is None
        for row in numeric_rows
    )
    numeric_keys = {
        registry_module.closed_trade_identity_state(row)["canonical_key"]
        for row in numeric_rows
    }
    assert len(numeric_keys) == 1
    assert not next(iter(numeric_keys)).startswith("specific|")


def test_bootstrap_without_active_blocks_unsafe_legacy_without_any_write(
    registry_module, tmp_path
):
    active = tmp_path / "active" / "trade_registry.json"
    legacy = tmp_path / "legacy.json"
    corrupt = _real_trade()
    corrupt["metadata"]["trade_lifecycle_id"] = "LC-CONFLICT"
    legacy.write_text(
        json.dumps(
            {"open_trades": {}, "closed_trades": [corrupt]}
        ),
        encoding="utf-8",
    )
    writes = []

    def read_json(path):
        path = Path(path)
        return (
            json.loads(path.read_text(encoding="utf-8"))
            if path.exists()
            else None
        )

    namespace = {
        "Path": Path,
        "json": json,
        "central_trade_registry": SimpleNamespace(),
        "CENTRAL_DATA_DIR": tmp_path,
        "_TRPSF_V1_STATE": {},
        "_trpsf_v1_active_file": lambda: active,
        "_trpsf_v1_legacy_candidate_paths": lambda: [legacy],
        "_trpsf_v1_read_json": read_json,
        "_trpsf_v1_atomic_write_json": lambda path, payload: writes.append(
            (Path(path), copy.deepcopy(payload))
        )
        or True,
        "_trpsf_v1_public": lambda payload: payload,
        "_trpsf_v1_now": lambda: "fixed",
        "_merge_closed_trade_records_v1": (
            registry_module.merge_closed_trade_records
        ),
        "TRADE_REGISTRY_PERSISTENT_STORAGE_FIX_V1_VERSION": "test-v1",
        "TRADE_REGISTRY_PERSISTENT_STORAGE_FIX_V1_BACKUP_FILE": (
            tmp_path / "backup.json"
        ),
        "TRADE_REGISTRY_PERSISTENT_STORAGE_FIX_V1_LATEST_FILE": (
            tmp_path / "latest.json"
        ),
        "TRADE_REGISTRY_PERSISTENT_STORAGE_FIX_V1_EVENTS_FILE": (
            tmp_path / "events.jsonl"
        ),
    }
    _compile_main_functions(
        [
            "_trpsf_v1_default_registry",
            "_trpsf_v1_iter_trades",
            "_trpsf_v1_registry_shape_errors",
            "_trpsf_v1_registry_counts",
            "_trpsf_v1_merge_registries",
            "_trpsf_v1_bootstrap_registry",
        ],
        namespace,
    )
    result = namespace["_trpsf_v1_bootstrap_registry"](force=True)
    assert result["status"] == "CLOSED_IDENTITY_MERGE_BLOCKED"
    assert result["ok"] is False
    assert result["write_performed"] is False
    assert result["closed_history_identity_merge"]["safe_to_commit"] is False
    assert not active.exists()
    assert writes == []


def test_legacy_manual_recovery_never_equates_one_verify_by_trade_id():
    writes = []
    raw = {"open_trades": {}, "closed_trades": [_verify_trade()]}
    namespace = {
        "central_trade_registry": SimpleNamespace(
            load_registry=lambda: copy.deepcopy(raw),
            save_registry=lambda payload: writes.append(payload),
        ),
        "_rp_v1_norm_symbol": lambda value: str(value or "").upper(),
        "_rp_v1_norm_side": lambda value: str(value or "").upper(),
        "_rp_v1_norm_bot": lambda value: str(value or "").upper(),
        "_rp_v1_build_live_state": lambda **kwargs: {
            "position_found": False
        },
        "REGISTRY_PERSISTENCE_V1_VERSION": "test-v1",
    }
    _compile_main_functions(
        [
            "_rp_v12_trade_key",
            "_rp_v12_load_raw_registry_safe",
            "_rp_v12_closed_trade_exists",
            "registry_persistence_v12_recover_closed_trade_from_params",
        ],
        namespace,
    )
    result = namespace[
        "registry_persistence_v12_recover_closed_trade_from_params"
    ](
        symbol="XRPUSDT",
        side="LONG",
        bot="FALCON",
        setup="FALCON15",
        ack="RESTORE_CLOSED_TRADE_MANUAL",
        commit=True,
        entry=1.0871,
    )
    assert result["status"] == "CLOSED_TRADE_STRONG_IDENTITY_REQUIRED"
    assert result["candidate_count"] == 1
    assert writes == []


def test_report_duplicate_detector_distinguishes_trade_id_from_execution(
    registry_module,
):
    namespace = {
        "central_trade_registry": registry_module,
        "_merge_closed_trade_records_v1": (
            registry_module.merge_closed_trade_records
        ),
    }
    _compile_main_functions(
        [
            "_closed_trade_identity_state_v1",
            "_closed_trade_record_relation_v1",
            "_closed_trade_records_equivalent_v1",
            "_trade_registry_report_duplicates",
        ],
        namespace,
    )
    detect = namespace["_trade_registry_report_duplicates"]
    assert detect(
        [_verify_trade(), _real_trade()], canonical_closed=True
    ) == []
    duplicates = detect(
        [_real_trade(), copy.deepcopy(_real_trade())],
        canonical_closed=True,
    )
    assert len(duplicates) == 1


def test_snapshot_reports_registry_commit_when_later_audit_write_fails():
    raw = {"open_trades": {}, "closed_trades": [_verify_trade()]}
    registry_writes = []
    namespace = {
        "central_trade_registry": SimpleNamespace(
            _lock=threading.RLock(),
            save_registry=lambda payload: registry_writes.append(
                copy.deepcopy(payload)
            )
            or True
        ),
        "_rp_v1_registry_snapshot_full": lambda: {
            "ok": True,
            "registry_read_known": True,
            "raw_registry": copy.deepcopy(raw),
            "open_count": 0,
        },
        "_rp_v1_read_latest_snapshot": lambda: {"ok": False},
        "_rp_v13_merge_closed_history": lambda current, latest_snapshot_payload=None: (
            copy.deepcopy(current),
            {"closed_identity": {"safe_to_commit": True}},
        ),
        "_rp_v13_update_registry_state_with_raw": (
            lambda state, merged, merge_meta=None: {
                **state,
                "raw_registry": merged,
            }
        ),
        "_rp_v1_build_live_state": lambda **kwargs: {
            "position_found": False,
            "registry_match": False,
            "stop_confirmed_by_central": False,
        },
        "_rp_v13_as_list": lambda value: list(value or []),
        "_rp_v1_now": lambda: "fixed",
        "_rp_v1_norm_symbol": lambda value: str(value or "").upper(),
        "_rp_v1_norm_side": lambda value: str(value or "").upper(),
        "_rp_v1_norm_bot": lambda value: str(value or "").upper(),
        "_rp_v1_data_dir_status": lambda: {"ok": True},
        "_rp_v1_atomic_write_json": lambda path, payload: (
            _ for _ in ()
        ).throw(OSError("audit unavailable")),
        "_rp_v1_append_event": lambda event: None,
        "REGISTRY_PERSISTENCE_V1_VERSION": "test-v1",
        "REGISTRY_PERSISTENCE_V1_LATEST_FILE": Path("unused.json"),
    }
    _compile_main_functions(
        ["registry_persistence_v1_snapshot"], namespace
    )
    result = namespace["registry_persistence_v1_snapshot"](commit=True)
    save = result["snapshot_save"]
    assert save["committed"] is True
    assert (
        save["status"]
        == "SNAPSHOT_AUDIT_PERSISTENCE_ERROR_AFTER_REGISTRY_COMMIT"
    )
    assert len(registry_writes) == 1


def test_restore_reports_registry_commit_when_later_journal_write_fails():
    raw = {"open_trades": {}, "closed_trades": [_verify_trade()]}
    registry_writes = []
    namespace = {
        "json": json,
        "central_trade_registry": SimpleNamespace(
            _lock=threading.RLock(),
            save_registry=lambda payload: registry_writes.append(
                copy.deepcopy(payload)
            )
            or True
        ),
        "_rp_v1_read_latest_snapshot": lambda: {
            "ok": True,
            "snapshot": {
                "registry_state": {"raw_registry": copy.deepcopy(raw)}
            },
        },
        "_rp_v13_merge_closed_history": lambda current, latest_snapshot_payload=None: (
            copy.deepcopy(current),
            {"closed_identity": {"safe_to_commit": True}},
        ),
        "_rp_v1_registry_snapshot_full": lambda: {
            "ok": True,
            "raw_registry": copy.deepcopy(raw),
        },
        "_rp_v13_as_list": lambda value: list(value or []),
        "_rp_v1_atomic_write_json": lambda path, payload: True,
        "_rp_v1_append_event": lambda event: (
            _ for _ in ()
        ).throw(OSError("journal unavailable")),
        "_rp_v1_now": lambda: "fixed",
        "REGISTRY_PERSISTENCE_V1_VERSION": "test-v1",
        "REGISTRY_PERSISTENCE_V1_PRE_RESTORE_BACKUP_FILE": Path(
            "unused-backup.json"
        ),
    }
    _compile_main_functions(
        ["registry_persistence_v1_restore_from_latest_snapshot"],
        namespace,
    )
    result = namespace[
        "registry_persistence_v1_restore_from_latest_snapshot"
    ](commit=True, ack="RESTORE_REGISTRY_FROM_SNAPSHOT")
    assert result["committed"] is True
    assert (
        result["status"]
        == "RESTORE_AUDIT_PERSISTENCE_ERROR_AFTER_REGISTRY_COMMIT"
    )
    assert len(registry_writes) == 1


def test_lifecycle_selector_never_falls_back_after_trade_id_miss():
    namespace = {
        "_tlm_trade_id": lambda trade: trade.get("trade_id"),
        "_tlm_norm_bot": lambda value: str(value or "").upper(),
        "_tlm_norm_symbol": lambda value: str(value or "").upper(),
        "_tlm_norm_side": lambda value: str(value or "").upper(),
        "_tlm_trade_symbol": lambda trade: str(
            trade.get("symbol") or ""
        ).upper(),
        "_tlm_trade_side": lambda trade: str(
            trade.get("side") or ""
        ).upper(),
    }
    _compile_main_functions(["_tlm_find_trade"], namespace)
    selected = namespace["_tlm_find_trade"](
        [
            {
                "trade_id": "OTHER",
                "bot": "FALCON",
                "symbol": "XRPUSDT",
                "side": "LONG",
            }
        ],
        trade_id=XRP_TRADE_ID,
        bot="FALCON",
        symbol="XRPUSDT",
        side="LONG",
    )
    assert selected is None


def test_lifecycle_outcome_link_uses_canonical_execution_identity(
    registry_module,
):
    namespace = {
        "_tlm_trade_id": lambda trade: trade.get("trade_id"),
        "_closed_trade_identity_state_v1": (
            registry_module.closed_trade_identity_state
        ),
    }
    _compile_main_functions(["_tlm_related_closed_record"], namespace)
    related = namespace["_tlm_related_closed_record"]
    wrong = {
        "trade_id": XRP_TRADE_ID,
        "status": "CLOSED",
        "lifecycle_id": "LC-WRONG",
        "evaluation_id": "WRONG",
    }
    correct = {
        "trade_id": XRP_TRADE_ID,
        "status": "CLOSED",
        "lifecycle_id": XRP_LIFECYCLE_ID,
        "evaluation_id": "CORRECT",
    }
    assert related(_real_trade(), [wrong, correct])["evaluation_id"] == (
        "CORRECT"
    )
    assert related(_real_trade(), [correct, copy.deepcopy(correct)]) is None
    conflicting = {
        **correct,
        "client_order_id": "CLIENT-CONFLICT",
        "order_id": "ORDER-CONFLICT",
    }
    assert related(_real_trade(), [conflicting]) is None


def test_predator_closed_fallback_never_uses_bare_trade_id(
    registry_module,
):
    def deep_find(item, keys, max_depth=6):
        del max_depth
        for key in keys:
            if isinstance(item, dict) and item.get(key) not in (None, ""):
                return item.get(key)
        return None

    namespace = {
        "_closed_trade_identity_state_v1": (
            registry_module.closed_trade_identity_state
        ),
        "_pppa_v1_closed_trade_id_from_event": (
            lambda event: (event.get("raw_public") or {}).get("trade_id")
        ),
        "_pppa_v1_deep_find": deep_find,
        "_pppa_v1_source_event_key_from_closed": lambda event: None,
        "_pppa_v1_closed_semantic_fingerprint": lambda event: None,
        "_pppa_v1_norm_symbol": lambda value: str(value or "").upper(),
        "_pppa_v1_norm_side": lambda value: str(value or "").upper(),
        "_pppa_v1_norm_text": lambda value: str(value or "").upper(),
        "_pppa_v1_closed_at_key": lambda value: str(value or ""),
    }
    _compile_main_functions(
        [
            "_pppa_v1_closed_registry_identity",
            "_pppa_v1_closed_canonical_key",
        ],
        namespace,
    )
    canonical = namespace["_pppa_v1_closed_canonical_key"]

    def event(closed_at):
        return {
            "key": f"event-{closed_at}",
            "ts": closed_at,
            "symbol": "XRPUSDT",
            "side": "LONG",
            "setup": "FALCON15",
            "raw_public": {
                "trade_id": XRP_TRADE_ID,
                "status": "CLOSED",
                "bot": "PREDATOR",
                "setup": "FALCON15",
                "symbol": "XRPUSDT",
                "side": "LONG",
                "registry_mode": "PAPER",
                "execution_mode": "PAPER",
                "closed_at": closed_at,
                "entry": 1.0,
                "qty": 9,
            },
        }

    first = canonical(event("2026-07-18T18:37:00-03:00"))
    second = canonical(event("2026-07-19T18:37:00-03:00"))
    assert first != second
    assert not first.startswith("trade_id|")
    assert not second.startswith("trade_id|")


def test_sparse_unknown_placeholders_are_enriched_by_factual_same_execution(
    registry_module,
):
    sparse = {
        "status": "CLOSED",
        "lifecycle_id": XRP_LIFECYCLE_ID,
        "client_order_id": XRP_CLIENT_ORDER_ID,
        "broker_order_id": XRP_ORDER_ID,
        "metadata": {},
    }
    normalized_sparse = registry_module._normalize_trade_record(sparse)
    result = registry_module.merge_closed_trade_records(
        [normalized_sparse, _real_trade()]
    )
    assert result["diagnostics"]["safe_to_commit"] is True
    assert len(result["records"]) == 1
    merged = result["records"][0]
    assert merged["bot"] == "FALCON"
    assert merged["setup"] == "FALCON15"
    assert merged["symbol"] == "XRPUSDT"
    assert merged["side"] == "LONG"
    assert merged["registry_mode"] == "REAL"


def test_authoritative_manual_outcome_replaces_generic_nested_outcome(
    registry_module,
):
    structural = _real_trade(
        metadata={
            "real_marker": "complete",
            "outcome": {
                "outcome_status": "CLOSED",
                "outcome_source": "FALCON",
                "exit_price": 1.08,
            },
        },
        outcome={
            "outcome_status": "CLOSED",
            "outcome_source": "FALCON",
            "exit_price": 1.08,
        },
        outcome_status=None,
        outcome_source=None,
        outcome_id=None,
        exit_price=None,
        pnl_pct=None,
    )
    manual = _real_trade(
        metadata={
            "outcome": {
                "outcome_status": "OUTCOME_RECORDED",
                "outcome_source": "MANUAL_CLOSE_RECONCILIATION",
                "outcome_id": "MANUAL-1",
                "exit_price": 1.0902,
            }
        },
        outcome={
            "outcome_status": "OUTCOME_RECORDED",
            "outcome_source": "MANUAL_CLOSE_RECONCILIATION",
            "outcome_id": "MANUAL-1",
            "exit_price": 1.0902,
        },
        outcome_id="MANUAL-1",
        exit_price=1.0902,
    )
    result = registry_module.merge_closed_trade_records([structural, manual])
    assert result["diagnostics"]["safe_to_commit"] is True
    assert len(result["records"]) == 1
    merged = result["records"][0]
    assert merged["outcome"]["outcome_id"] == "MANUAL-1"
    assert merged["metadata"]["outcome"]["outcome_id"] == "MANUAL-1"
    assert merged["outcome_source"] == "MANUAL_CLOSE_RECONCILIATION"


@pytest.mark.parametrize(
    ("left_updates", "right_updates", "expected_field"),
    [
        ({"pnl_usdt": 1.0}, {"profit_usdt": 2.0}, "gross_pnl_usdt"),
        (
            {"broker_close_order_id": "CLOSE-A"},
            {"close_order_id": "CLOSE-B"},
            "close_order_id",
        ),
    ],
)
def test_additional_factual_alias_conflicts_block_automatic_merge(
    registry_module, left_updates, right_updates, expected_field
):
    left = _real_trade(**left_updates)
    right = _real_trade(**right_updates)
    result = registry_module.merge_closed_trade_records([left, right])
    assert len(result["records"]) == 2
    assert result["diagnostics"]["safe_to_commit"] is False
    assert expected_field in (
        result["diagnostics"]["financial_conflicts"][0][
            "financial_conflict_fields"
        ]
    )


def test_real_verify_collision_audit_uses_execution_mode_when_registry_mode_missing(
    registry_module,
):
    real = _real_trade(registry_mode=None, execution_mode="LIVE")
    verify = _verify_trade()
    verify["registry_mode"] = None
    result = registry_module.merge_closed_trade_records([real, verify])
    assert result["diagnostics"]["real_verify_collision_group_count"] == 1


def test_identity_audit_marks_review_required_as_not_ok(registry_module):
    conflict = _real_trade(
        metadata={"lifecycle_id": "LC-CONFLICT"}
    )
    audit = registry_module.audit_closed_trade_identities([conflict])
    assert audit["audit_completed"] is True
    assert audit["ok"] is False
    assert audit["status"] == "CLOSED_IDENTITY_REVIEW_REQUIRED"
    assert audit["safe_to_commit"] is False
