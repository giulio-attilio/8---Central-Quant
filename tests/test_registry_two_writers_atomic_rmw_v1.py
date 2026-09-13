"""Synthetic AST-only regressions; never import main or connect to a broker."""
import ast
import copy
import threading
from contextlib import ContextDecorator
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
TREE = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))
OPEN = "_rtlm_v1_update_open_trade_snapshot"
CLOSED = "trade_close_outcome_v1_commit"


class Store:
    def __init__(self, shape):
        self._lock = threading.RLock()
        self.original = {"trade_id": "synthetic-closed", "metadata": {},
                         "gross_r_multiple": -1.0}
        closed = [copy.deepcopy(self.original)] if shape == "list" else {
            "closed-key": copy.deepcopy(self.original)}
        self.document = {"open_trades": {"open-key": {"trade_id": "synthetic-open"}},
                         "closed_trades": closed, "unrelated": {"keep": [1, 2]}}
        self.reads = self.writes = self.audits = 0
        self.after_read = lambda: None
        self.save_mode = "ok"

    def load(self):
        with self._lock:
            self.reads += 1
            result = copy.deepcopy(self.document)
        self.after_read()
        return result

    def save_registry(self, document):
        with self._lock:
            if self.save_mode == "raise":
                raise RuntimeError("synthetic save failure")
            if self.save_mode == "false":
                return False
            self.writes += 1
            self.document = copy.deepcopy(document)
            return True

    def audit(self, *_args):
        self.audits += 1
        return True


class Seam(ContextDecorator):
    """Injected admission dependency: ordering and rejection remain observable."""
    def __init__(self, calls, blocked=False):
        self.calls, self.blocked = calls, blocked

    def __enter__(self):
        self.calls.append("c3-enter")
        if self.blocked:
            raise RuntimeError("synthetic C3 rejection")

    def __exit__(self, *_args):
        self.calls.append("c3-exit")


def compile_writer(store, name, blocked=False):
    calls = []
    def closed_items(document):
        rows = document["closed_trades"]
        return (rows, list(rows.items()) if isinstance(rows, dict) else [
            (f"closed_index|{i}|{trade['trade_id']}", trade)
            for i, trade in enumerate(rows)])
    ns = {
        "central_trade_registry": store,
        "c3_runtime_seam_v1": SimpleNamespace(
            _c3_closed_repair_writer_mutation_v1=lambda _id: Seam(calls, blocked)),
        "_rtlm_v1_load_registry": store.load,
        "_rtlm_v1_registry_open_items": lambda doc: (doc["open_trades"], list(doc["open_trades"].items())),
        "_rtlm_v1_match_trade": lambda trade, **_kw: trade["trade_id"] == "synthetic-open",
        "_rtlm_v1_now": lambda: "synthetic-now",
        "REAL_TRADE_LIFECYCLE_MONITOR_V1_VERSION": "synthetic",
        "TRADE_REGISTRY_IMPORT_ERROR": "synthetic-unavailable",
        "_tco_v1_load_registry": store.load,
        "_tco_v1_closed_items": closed_items,
        "_tco_v1_now": lambda: "synthetic-now",
        "_closed_trade_identity_state_v1": lambda trade: {
            "canonical_key": trade.get("trade_id"), "has_alias_conflict": False},
        "_closed_trade_records_equivalent_v1": lambda a, b: a.get("trade_id") == b.get("trade_id"),
        "TRADE_CLOSE_OUTCOME_V1_VERSION": "synthetic",
        "TRADE_CLOSE_OUTCOME_V1_LATEST_FILE": "unused-memory-audit",
        "TRADE_CLOSE_OUTCOME_V1_EVENTS_FILE": "unused-memory-events",
        "_tco_v1_atomic_write_json": store.audit,
        "_tco_v1_append_event": store.audit,
    }
    names = {name, "_trpsf_v1_registry_lock"}
    nodes = [copy.deepcopy(n) for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name in names]
    assert len(nodes) == 2
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "<synthetic-rmw-fragments>", "exec"), ns)
    return ns, calls


def invoke(ns, store, name):
    if name == OPEN:
        return ns[name](commit=True, lifecycle={"status": "OBSERVED"})
    return ns[name]({}, {"trade": copy.deepcopy(store.original)}, {
        "ok": True, "close_reason": "STOP", "pnl_r": -1.25,
        "gross_r_multiple": -1.0, "status": "EVALUATED"})


@pytest.mark.parametrize("name", [OPEN, CLOSED])
@pytest.mark.parametrize("shape", ["list", "dict"])
def test_competing_close_is_not_resurrected_or_lost(name, shape):
    store = Store(shape)
    ns, calls = compile_writer(store, name)
    read_done, attempt_done, competitor_done = (threading.Event() for _ in range(3))
    acquired, errors, results = [], [], []

    def after_read():
        read_done.set()
        assert attempt_done.wait(3), "competitor did not attempt lock"
        if acquired[0]:
            assert competitor_done.wait(3), "unprotected competitor did not finish"
    store.after_read = after_read

    def compete():
        try:
            assert read_done.wait(3)
            won = store._lock.acquire(blocking=False)
            acquired.append(won)
            attempt_done.set()
            if not won:
                assert store._lock.acquire(timeout=3)
            try:
                # A different, fully locked writer closes an OPEN lifecycle.
                store.document["open_trades"].pop("open-key")
                store.document["unrelated"]["concurrent_close"] = True
            finally:
                store._lock.release()
        except BaseException as exc:
            errors.append(exc)
        finally:
            competitor_done.set()

    def primary():
        try:
            results.append(invoke(ns, store, name))
        except BaseException as exc:
            errors.append(exc)

    workers = [threading.Thread(target=primary, daemon=True), threading.Thread(target=compete, daemon=True)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(10)
    assert not any(worker.is_alive() for worker in workers), "lock deadlock"
    assert not errors, errors
    assert results[0]["committed"] is True
    assert "open-key" not in store.document["open_trades"], "stale writer resurrected a closed lifecycle"
    assert store.document["unrelated"] == {"keep": [1, 2], "concurrent_close": True}
    assert acquired == [False], "complete RMW was not held under Registry lock"
    assert calls == ["c3-enter", "c3-exit"]
    if name == CLOSED:
        rows = store.document["closed_trades"]
        row = rows[0] if shape == "list" else rows["closed-key"]
        assert row["close_reason"] == "STOP"
        assert row["pnl_r"] == row["result_r"] == row["r_multiple"] == -1.25
        assert row["gross_r_multiple"] == -1.0


@pytest.mark.parametrize("name", [OPEN, CLOSED])
@pytest.mark.parametrize("lock", [None, object()])
def test_missing_or_invalid_lock_blocks_before_read(name, lock):
    store = Store("list")
    ns, _ = compile_writer(store, name)
    store._lock = lock
    result = invoke(ns, store, name)
    assert result == {"attempted": True, "committed": False, "status": "REGISTRY_LOCK_UNAVAILABLE"}
    assert store.reads == store.writes == store.audits == 0


@pytest.mark.parametrize("name", [OPEN, CLOSED])
@pytest.mark.parametrize("mode", ["false", "raise"])
def test_failed_save_preserves_data_and_releases_lock(name, mode):
    store = Store("list")
    original = copy.deepcopy(store.document)
    ns, _ = compile_writer(store, name)
    store.save_mode = mode
    result = invoke(ns, store, name)
    assert result["committed"] is False and result["status"] == "SAVE_ERROR"
    assert store.document == original and store.audits == 0
    acquired = []
    def check():
        won = store._lock.acquire(timeout=1)
        acquired.append(won)
        if won:
            store._lock.release()
    thread = threading.Thread(target=check, daemon=True)
    thread.start()
    thread.join(2)
    assert acquired == [True]


@pytest.mark.parametrize("name", [OPEN, CLOSED])
def test_c3_rejection_still_precedes_local_read_and_write(name):
    store = Store("list")
    ns, calls = compile_writer(store, name, blocked=True)
    with pytest.raises(RuntimeError, match="synthetic C3 rejection"):
        invoke(ns, store, name)
    assert store.reads == store.writes == store.audits == 0
    assert calls == ["c3-enter"]


def test_preview_does_not_require_lock_or_read():
    store = Store("list")
    ns, _ = compile_writer(store, OPEN)
    store._lock = None
    assert ns[OPEN](commit=False)["status"] == "COMMIT_NOT_REQUESTED"
    assert store.reads == store.writes == store.audits == 0
