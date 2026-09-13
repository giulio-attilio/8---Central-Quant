"""Seven AST-only writers, synthetic memory and scratch; never import main."""
import ast
import copy
import json
import threading
import time
from contextlib import ContextDecorator
from pathlib import Path
from types import SimpleNamespace

import pytest

TREE = ast.parse((Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8"))
MANUAL = "_trs_v1_manual_register_open_trade"
RECOVER = "registry_persistence_v12_recover_closed_trade_from_params"
MODE = "registry_mode_segregation_v1_analyze"
MISSING = "mark_registry_missing_trades"
PAPER = "predator_paper_registry_sync_fix_v1_status"
ORPHAN = "predator_registry_orphan_open_fix_v1_status"
AUTO = "predator_auto_closed_sync_v1_status"
WRITERS = [MANUAL, RECOVER, MODE, MISSING, PAPER, ORPHAN, AUTO]


class Stage(ContextDecorator):
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def finish(self, *_, **__):
        pass


class Admission(Stage):
    def __init__(self, store, blocked):
        self.store, self.blocked = store, blocked

    def __enter__(self):
        self.store.admissions += 1
        if self.blocked:
            raise RuntimeError("synthetic C3 rejection")
        return self


class Store:
    def __init__(self):
        self.io_lock = self._lock = threading.RLock()
        self.document = {
            "open_trades": {
                "target": {"trade_id": "target", "bot": "PREDATOR", "status": "OPEN",
                           "lifecycle_id": "lc-target", "registry_mode": "PAPER", "metadata": {}},
                "other": {"trade_id": "other", "bot": "OTHER", "status": "OPEN"}},
            "closed_trades": [], "unrelated": {"keep": [1, 2]}}
        self.reads = self.writes = self.admissions = 0
        self.before_save = lambda: None
        self.external_hook = lambda: None
        self.save_mode = "ok"
        self.fail_read_at = None
        self.save_was_locked = []
        self.read_was_locked = []
        self.saved_documents = []

    def load_registry(self):
        self.read_was_locked.append(self.io_lock._is_owned())
        with self.io_lock:
            self.reads += 1
            if self.reads == self.fail_read_at:
                raise RuntimeError("synthetic reload failure")
            return copy.deepcopy(self.document)

    def save_registry(self, doc):
        self.save_was_locked.append(self.io_lock._is_owned())
        self.before_save()
        with self.io_lock:
            if self.save_mode == "raise":
                raise RuntimeError("synthetic save failure")
            if self.save_mode == "false":
                return False
            self.document = copy.deepcopy(doc)
            self.saved_documents.append(copy.deepcopy(doc))
            self.writes += 1
            return True

    def external(self):
        assert not self.io_lock._is_owned(), "external collection inside Registry lock"
        self.external_hook()


def harness(tmp_path, name, blocked=False):
    store = Store()
    closed = {"trade_id": "event", "lifecycle_id": "lc-event", "status": "CLOSED",
              "bot": "PREDATOR", "registry_mode": "PAPER", "close_reason": "STOP",
              "pnl_r": -1.25, "gross_r_multiple": -1.0}

    def read():
        try:
            return store.load_registry(), None
        except RuntimeError as exc:
            return None, str(exc)

    def lifecycle(**_):
        store.external()
        return {"mode": "PAPER", "execution_enabled": False, "execution_firewall_enabled": True,
                "samples": {}, "counts": {}, "pnl_audit_summary": {}}

    def positions():
        store.external()
        return []

    def events(**_):
        store.external()
        return [copy.deepcopy(closed)], {}

    def plan(doc, candidates):
        existing = {t.get("lifecycle_id") for t in doc["closed_trades"]}
        return {"planned": [copy.deepcopy(t) for t in candidates if t["lifecycle_id"] not in existing],
                "ambiguous": [], "skipped": []}

    def counts(doc):
        store.external()  # Production helper collects module positions/events.
        return {"registry_closed_count": len(doc["closed_trades"]), "orphan_registry_open_count": 0}

    ns = {
        "central_trade_registry": store, "json": json, "Path": Path, "time": time,
        "c3_runtime_seam_v1": SimpleNamespace(_c3_closed_repair_writer_mutation_v1=
            lambda _id: Admission(store, blocked)),
        "observe_predator_audit": lambda _: lambda f: f,
        "request_cached_predator_audit": lambda _: lambda f: f,
        "predator_audit_stage": lambda *_, **__: Stage(),
        "data_hora_sp_str": lambda: "synthetic-now",
        "_rp_v12_trade_key": lambda **_: ("recovered", "SYNTH", "LONG", "PREDATOR", "SETUP"),
        "_rp_v1_build_live_state": lambda **_: (store.external() or {"position_found": False}),
        "_rp_v12_load_raw_registry_safe": store.load_registry,
        "_rp_v1_float": lambda x: None if x is None else float(x),
        "_rp_v1_now": lambda: "synthetic-now",
        "_rp_v1_registry_snapshot_full": lambda: {}, "_rp_v1_data_dir_status": lambda: {},
        "_rp_v1_atomic_write_json": lambda *_: True, "_rp_v1_append_event": lambda *_: True,
        "REGISTRY_PERSISTENCE_V1_VERSION": "synthetic", "REGISTRY_PERSISTENCE_V1_LATEST_FILE": "unused",
        "_rms_v1_registry_items": lambda d: (list(d["open_trades"].items()), list(enumerate(d["closed_trades"]))),
        "_rms_v1_row": lambda k, t, b: {"registry_mode": "PAPER"},
        "registry_mode_segregation_v1_classify_trade": lambda *_, **__: {"mode": "PAPER", "confidence": "HIGH", "reasons": []},
        "_rms_v1_now": lambda: "synthetic-now",
        "_rms_v1_atomic_write_json": lambda *_: True, "_rms_v1_append_event": lambda *_: True,
        "REGISTRY_MODE_SEGREGATION_V1_VERSION": "synthetic", "REGISTRY_MODE_SEGREGATION_V1_LATEST_FILE": "unused",
        "_pprsf_v1_load_registry": read,
        "predator_paper_lifecycle_audit_v1_status": lifecycle,
        "_ppla_v1_get_predator_module_positions_raw": positions,
        "_ppla_v1_get_closed_paper_events": events,
        "_pprsf_v1_now": lambda: "synthetic-now",
        "_pprsf_v1_open_dict": lambda d: d["open_trades"],
        "_pprsf_v1_closed_list": lambda d: d["closed_trades"],
        "_pprsf_v1_existing_ids_and_signatures": lambda d: (set(d["open_trades"]), set(), set()),
        "_pprsf_v1_build_open_trade_from_position": copy.deepcopy,
        "_pprsf_v1_build_closed_trade_from_event": copy.deepcopy,
        "_pprsf_v1_signature_trade": lambda t: t["trade_id"],
        "_pprsf_v1_closed_signature": lambda t: t["lifecycle_id"],
        "_closed_trade_record_relation_v1": lambda a, b: "EQUIVALENT" if a["lifecycle_id"] == b["lifecycle_id"] else "DISTINCT",
        "_pprsf_v1_public": lambda v, **_: copy.deepcopy(v),
        "_pprsf_v1_recalculate_lifecycle_counts_from_registry": counts,
        "_ppla_v1_get_trade_id": lambda t: t.get("trade_id"),
        "_ppla_v1_trade_key": lambda t: t.get("trade_id"),
        "_PREDATOR_ORPHAN_OPEN_FIX_V1_STATE": {}, "_PREDATOR_AUTO_CLOSED_SYNC_V1_STATE": {},
        "_PREDATOR_AUTO_CLOSED_SYNC_V1_LOCK": threading.RLock(),
        "_pacs_v1_plan_closed_repairs": plan, "_pacs_v1_storage_status": lambda: {"ok": True},
        "_pacs_v1_lifecycle_blockers": lambda _: [], "_pacs_v1_write_audit": lambda _: None,
        "PREDATOR_AUTO_CLOSED_SYNC_V1_ENABLED": True,
        "PREDATOR_AUTO_CLOSED_SYNC_V1_MAX_PER_CYCLE": 3,
        "PREDATOR_AUTO_CLOSED_SYNC_V1_ACK": "PREDATOR_AUTO_CLOSED_SYNC_FIX",
        "PREDATOR_AUDIT_REQUEST_SHARED_LIMIT": 2000,
    }
    store.make_trade_id = lambda *_: "new-open"
    for prefix in ["PREDATOR_PAPER_REGISTRY_SYNC_FIX_V1", "PREDATOR_ORPHAN_OPEN_FIX_V1", "PREDATOR_AUTO_CLOSED_SYNC_V1"]:
        ns[prefix + "_VERSION"] = "synthetic"
        ns[prefix + "_EVENTS_FILE"] = str(tmp_path / (prefix + ".jsonl"))
        ns[prefix + "_LATEST_FILE"] = str(tmp_path / (prefix + ".json"))
    names = {name, "_trpsf_v1_registry_lock", "_rp_v12_closed_trade_exists", "_poof_v1_plan_orphans", "_poof_v1_trade_mode"}
    nodes = [copy.deepcopy(n) for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name in names]
    assert len(nodes) == len(names)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "<seven-synthetic-writers>", "exec"), ns)
    return ns, store


def invoke(ns, name, commit=True):
    if name == MANUAL:
        return ns[name]({"bot": "PREDATOR", "symbol": "SYNTH", "side": "LONG"})
    if name == MISSING:
        return ns[name]([{"trade_id": "target"}])
    if name == RECOVER:
        return ns[name](commit=commit, ack="RESTORE_CLOSED_TRADE_MANUAL", entry=100, qty=1)
    if name == MODE:
        return ns[name](commit=commit)
    ack = {PAPER: "PREDATOR_REGISTRY_SYNC_FIX", ORPHAN: "PREDATOR_ORPHAN_OPEN_FIX", AUTO: "PREDATOR_AUTO_CLOSED_SYNC_FIX"}[name]
    return ns[name](commit=commit, ack=ack)


@pytest.mark.parametrize("name", WRITERS)
def test_full_rmw_preserves_competing_close(tmp_path, name):
    ns, store = harness(tmp_path, name)
    saving, attempted, finished = (threading.Event() for _ in range(3))
    acquired, errors = [], []

    def before_save():
        saving.set()
        assert attempted.wait(3)
        if acquired[0]:
            assert finished.wait(3)

    def competitor():
        try:
            assert saving.wait(3)
            won = store.io_lock.acquire(blocking=False)
            acquired.append(won)
            attempted.set()
            if not won:
                assert store.io_lock.acquire(timeout=3)
            try:
                store.document["open_trades"].pop("other")
                store.document["unrelated"]["concurrent_close"] = True
            finally:
                store.io_lock.release()
        except BaseException as exc:
            errors.append(exc)
        finally:
            finished.set()

    store.before_save = before_save
    worker = threading.Thread(target=competitor, daemon=True)
    worker.start()
    result = invoke(ns, name)
    worker.join(5)
    assert not worker.is_alive() and not errors, errors
    assert store.writes == 1, result
    if name == MODE:
        assert result["commit"]["committed"] is True
    elif name in {MANUAL, MISSING}:
        assert result["ok"] is True
    else:
        assert result["committed"] is True
    assert store.save_was_locked == [True]
    assert store.read_was_locked[1 if name in {PAPER, ORPHAN, AUTO} else 0] is True
    assert acquired == [False], "writer did not hold Registry lock across RMW"
    assert "other" not in store.document["open_trades"], "closed trade resurrected"
    assert store.document["unrelated"] == {"keep": [1, 2], "concurrent_close": True}
    assert store.admissions == 1


@pytest.mark.parametrize("name", WRITERS)
@pytest.mark.parametrize("invalid", [None, object()])
def test_invalid_lock_never_saves(tmp_path, name, invalid):
    ns, store = harness(tmp_path, name)
    before = copy.deepcopy(store.document)
    store._lock = invalid
    result = invoke(ns, name)
    assert store.writes == 0 and store.document == before
    assert "REGISTRY_LOCK_UNAVAILABLE" in json.dumps(result)


@pytest.mark.parametrize("name", WRITERS)
@pytest.mark.parametrize("failure", ["false", "raise"])
def test_save_failure_preserves_document_and_unlocks(tmp_path, name, failure):
    ns, store = harness(tmp_path, name)
    original = copy.deepcopy(store.document)
    store.save_mode = failure
    try:
        result = invoke(ns, name)
    except RuntimeError as exc:
        assert name == MANUAL and failure == "raise"
        result = {"error": str(exc)}
    assert store.writes == 0 and store.document == original, result
    assert store.save_was_locked == [True]
    acquired = []
    def probe():
        won = store.io_lock.acquire(timeout=1)
        acquired.append(won)
        if won:
            store.io_lock.release()
    thread = threading.Thread(target=probe, daemon=True)
    thread.start()
    thread.join(2)
    assert acquired == [True]


@pytest.mark.parametrize("name", WRITERS)
def test_c3_admission_rejects_before_any_collection(tmp_path, name):
    ns, store = harness(tmp_path, name, blocked=True)
    with pytest.raises(RuntimeError, match="synthetic C3 rejection"):
        invoke(ns, name)
    assert store.reads == store.writes == 0


@pytest.mark.parametrize("name", [RECOVER, MODE, PAPER, ORPHAN, AUTO])
def test_preview_needs_no_registry_lock_and_does_not_write(tmp_path, name):
    ns, store = harness(tmp_path, name)
    before = copy.deepcopy(store.document)
    store._lock = None
    result = invoke(ns, name, commit=False)
    assert result["ok"] is True
    assert store.writes == 0 and store.document == before


@pytest.mark.parametrize("name", [PAPER, ORPHAN, AUTO])
def test_reload_preserves_change_during_external_collection(tmp_path, name):
    ns, store = harness(tmp_path, name)
    def update():
        with store.io_lock:
            store.document["unrelated"]["concurrent_update"] = "preserved"
    store.external_hook = update
    result = invoke(ns, name)
    assert store.writes == 1, result
    assert store.document["unrelated"]["concurrent_update"] == "preserved"
    assert store.saved_documents[0]["unrelated"]["concurrent_update"] == "preserved"
    assert store.save_was_locked == [True]


@pytest.mark.parametrize("name", [PAPER, ORPHAN, AUTO])
def test_fresh_read_failure_cannot_save_stale_preview(tmp_path, name):
    ns, store = harness(tmp_path, name)
    store.fail_read_at = 2
    before = copy.deepcopy(store.document)
    result = invoke(ns, name)
    assert store.writes == 0 and store.document == before, result
    assert not store.io_lock._is_owned()


def test_orphan_plan_change_aborts_instead_of_closing_new_lifecycle(tmp_path):
    ns, store = harness(tmp_path, ORPHAN)
    original_plan = ns["_poof_v1_plan_orphans"]
    def planned_then_replaced(doc, positions):
        result = original_plan(doc, positions)
        if not store.io_lock._is_owned():
            store.document["open_trades"]["target"]["lifecycle_id"] = "lc-new"
        return result
    ns["_poof_v1_plan_orphans"] = planned_then_replaced
    result = invoke(ns, ORPHAN)
    assert store.writes == 0 and not result["committed"]
    assert store.document["open_trades"]["target"]["lifecycle_id"] == "lc-new"


def test_post_commit_recount_failure_cannot_erase_confirmed_commit(tmp_path):
    ns, store = harness(tmp_path, AUTO)
    def failed_counts(_):
        store.external()
        raise RuntimeError("synthetic recount failure")
    ns["_pprsf_v1_recalculate_lifecycle_counts_from_registry"] = failed_counts
    result = invoke(ns, AUTO)
    assert store.writes == 1 and result["committed"] is True
    assert result["repaired_count"] == 1
    assert any("POST_COMMIT_RECOUNT_FAILED" in item for item in result["warnings"])
