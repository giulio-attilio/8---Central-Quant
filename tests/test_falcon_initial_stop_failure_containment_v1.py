from __future__ import annotations

import ast
import copy
import hashlib
import json
import threading
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
FALCON_SOURCE = ROOT / "bots" / "falcon.py"


def _load_falcon_functions(names: tuple[str, ...], namespace: dict) -> dict:
    tree = ast.parse(FALCON_SOURCE.read_text(encoding="utf-8"))
    selected = []
    for name in names:
        nodes = [
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == name
        ]
        assert nodes, name
        selected.append(copy.deepcopy(nodes[-1]))
    module = ast.Module(
        body=sorted(selected, key=lambda node: node.lineno), type_ignores=[]
    )
    ast.fix_missing_locations(module)
    result = dict(namespace)
    exec(compile(module, str(FALCON_SOURCE), "exec"), result)
    return result


def _float(value, default=None):
    try:
        return float(value) if value not in (None, "") else default
    except (TypeError, ValueError):
        return default


def _norm_symbol(value):
    return str(value or "").upper().replace("/", "").replace(":USDT", "")


def _norm_side(value):
    value = str(value or "").upper()
    return "LONG" if value in {"LONG", "BUY"} else "SHORT" if value in {"SHORT", "SELL"} else value


def _identity(pos):
    pos = pos if isinstance(pos, dict) else {}
    order = pos.get("live_order") if isinstance(pos.get("live_order"), dict) else {}
    return {
        "position_id": pos.get("id"),
        "trade_id": pos.get("trade_registry_id") or pos.get("trade_id"),
        "lifecycle_id": pos.get("lifecycle_id"),
        "order_id": pos.get("live_order_id") or pos.get("bingx_order_id") or order.get("order_id") or order.get("id"),
        "client_order_id": pos.get("live_client_order_id") or pos.get("client_order_id") or order.get("client_order_id") or order.get("client_tag"),
        "symbol": _norm_symbol(pos.get("symbol")),
        "side": _norm_side(pos.get("side")),
    }


class _Broker:
    def __init__(
        self,
        *,
        residual=0.0,
        pre_close_amount=None,
        close_result=None,
        close_lookup=None,
        raise_close=False,
        entry_side="BUY",
        entry_position_side="LONG",
        position_position_side="LONG",
        position_mode=None,
        opposite_position_open=None,
        manual_position=False,
    ):
        self.residual = residual
        self.pre_close_amount = pre_close_amount
        self.close_result = close_result
        self.close_lookup = close_lookup
        self.raise_close = raise_close
        self.entry_side = entry_side
        self.entry_position_side = entry_position_side
        self.position_position_side = position_position_side
        self.position_mode = position_mode
        self.opposite_position_open = opposite_position_open
        self.manual_position = manual_position
        self.calls = []
        self.position_calls = []

    def managed_order_snapshot(self, symbol, order_id):
        return {
            "ok": True,
            "read_only": True,
            "order_id": order_id,
            "symbol": symbol,
            "side": self.entry_side,
            "position_side": self.entry_position_side,
            "filled": 0.5,
        }

    def managed_position_snapshot(self, symbol, side, expected_amount=None):
        self.position_calls.append((symbol, side, expected_amount))
        amount = 0.5 if expected_amount is not None else (
            self.residual
            if self.calls or self.pre_close_amount is None
            else self.pre_close_amount
        )
        snapshot = {
            "ok": True,
            "read_only": True,
            "symbol": symbol,
            "side": side,
            "position_side": self.position_position_side,
            "amount": amount,
            "position_closed": amount == 0.0,
            "ownership_safe": True,
            "matched_count": 1,
            "positions": [
                {
                    "symbol": symbol,
                    "side": self.position_position_side,
                    "manual_position": self.manual_position,
                }
            ],
        }
        if self.position_mode is not None:
            snapshot["position_mode"] = self.position_mode
        if self.opposite_position_open is not None:
            snapshot["opposite_position_open"] = self.opposite_position_open
        return snapshot

    def reconcile_order_from_bingx(self, symbol, client_order_id=None):
        del symbol, client_order_id
        return copy.deepcopy(self.close_lookup or {"ok": False, "status": "ORDER_NOT_FOUND"})

    def managed_close_position_market(self, **kwargs):
        self.calls.append(kwargs)
        if self.raise_close:
            raise RuntimeError("managed close failure")
        return self.close_result or {
            "ok": True,
            "status": "MANAGED_CLOSE_CONFIRMED",
            "sent": True,
            "confirmed": True,
            "send_attempted": True,
            "send_outcome_unknown": False,
            "order_id": "CLOSE-1",
            "client_order_id": kwargs["client_tag"],
            "symbol": kwargs["symbol"],
            "side": kwargs["side"],
            "filled_amount": kwargs["amount"],
            "remaining_amount": 0.0,
        }


def _signal(*, ownership=None, side="LONG"):
    ownership = ownership or {
        "allowed": True,
        "requested_symbol": "SOLUSDT",
        "requested_side": side,
        "manual_same_symbol_side_count": 0,
        "reason_codes": [],
    }
    return {
        "id": "SIGNAL-INITIAL-STOP-1",
        "signal_id": "SIGNAL-INITIAL-STOP-1",
        "lifecycle_id": "LC-INITIAL-STOP-1",
        "symbol": "SOLUSDT",
        "side": side,
        "setup": "FALCON15",
        "falcon_real_position_ownership_limit_v1": {
            "ok": True,
            "evidence": ownership,
        },
    }


def _order(stop_status="CANCELED"):
    return {
        "ok": False,
        "status": "LIVE_SENT_BUT_DISASTER_STOP_FAILED",
        "sent": True,
        "order_id": "ENTRY-1",
        "client_order_id": "ENTRY-CID-1",
        "amount": 0.5,
        "disaster_stop": {
            "status": stop_status,
            "stop_operationally_armed": False,
            "client_order_id": "STOP-CID-1",
        },
    }


def _incident_id_for_test():
    components = (
        "FALCON_INITIAL_STOP_FAILURE",
        "ENTRY-1",
        "ENTRY-CID-1",
        "SIGNAL-INITIAL-STOP-1",
        "LC-INITIAL-STOP-1",
        "",
        "SOLUSDT",
        "LONG",
        "",
    )
    digest = hashlib.sha256("|".join(components).encode("utf-8")).hexdigest().upper()
    return f"FALCON-INITIAL-STOP-{digest[:32]}"


def _persisted_incident_state(status="UNSAFE_LIVE_ENTRY_UNPROTECTED", **updates):
    state = {
        "version": "TEST-V1",
        "incident_id": _incident_id_for_test(),
        "incident_type": "INITIAL_STOP_FAILURE_CONTAINMENT",
        "attempt_state": status,
        "containment_status": (
            "INITIAL_STOP_FAILED_EMERGENCY_CLOSE_FAILED"
            if status == "INITIAL_STOP_FAILED_EMERGENCY_CLOSE_FAILED"
            else status
        ),
        "containment_reason": "TEST_RESTART",
        "bot": "FALCON",
        "symbol": "SOLUSDT",
        "side": "LONG",
        "position_side": "LONG",
        "lifecycle_id": "LC-INITIAL-STOP-1",
        "entry_order_id": "ENTRY-1",
        "entry_client_order_id": "ENTRY-CID-1",
        "signal_id": "SIGNAL-INITIAL-STOP-1",
        "entry_sent": True,
        "stop_operationally_armed": False,
        "unsafe_entry_persisted": True,
        "ownership_confirmed": False,
        "emergency_close_attempted": False,
        "emergency_close_sent": False,
        "emergency_close_confirmed": False,
        "falcon_live_entries_locked": True,
        "client_order_id_reservation": {
            "ok": True,
            "send_allowed": True,
            "client_order_id": "FEC1-INITIAL-STOP-1",
            "role": "EMERGENCY_TERMINAL_STOP_CLOSE",
            "revision": 0,
            "attempt": 0,
        },
    }
    state.update(updates)
    return state


def _current_registry_for_test(
    pos, *, same_leg_other_records=None, ignored_same_leg_records=None, partial=False
):
    identity = _identity(pos)
    return {
        "ok": True,
        "status": "REGISTRY_LIFECYCLE_MATCHED",
        "partial": partial,
        "lifecycle_match_count": 1,
        "matches": [{
            "bot": "FALCON",
            "execution_mode": "LIVE",
            "registry_mode": "REAL",
            "lifecycle_id": identity["lifecycle_id"],
            "broker_order_id": identity["order_id"],
            "client_order_id": identity["client_order_id"],
            "symbol": identity["symbol"],
            "side": identity["side"],
        }],
        "same_leg_other_records": list(same_leg_other_records or []),
        "ignored_same_leg_records": list(ignored_same_leg_records or []),
    }


def _harness(
    *,
    broker=None,
    store=None,
    persistence_ok=True,
    token_ok=True,
    lock_ok=True,
    lock_release_ok=True,
    other_incident_owns_lock=False,
    save_outcomes=None,
    lock_helper_present=True,
    lifecycle_lock_ok=True,
    resume_send_allowed=True,
    current_registry=None,
    unsafe_registry_open=None,
):
    store = {} if store is None else store
    broker = broker or _Broker()
    timeline = []
    entry_locks = []
    health = {}
    lock_state = {
        "locked": bool(other_incident_owns_lock),
        "incident_id": "FALCON-INITIAL-STOP-OTHER" if other_incident_owns_lock else None,
    }
    save_outcomes = list(save_outcomes or [])
    save_count = 0

    def load(incident_id):
        return {"ok": True, "incident": copy.deepcopy(store.get(incident_id, {}))}

    def save(incident_id, state):
        nonlocal save_count
        timeline.append(("persist", state.get("attempt_state")))
        save_count += 1
        write_ok = (
            save_outcomes[save_count - 1]
            if save_count <= len(save_outcomes)
            else persistence_ok
        )
        if not write_ok:
            return {"ok": False, "status": "INCIDENT_PERSISTENCE_ERROR"}
        store[incident_id] = copy.deepcopy(state)
        return {"ok": True, "status": "INCIDENT_PERSISTED"}

    def lock_writer(incident_id, *, active, reason=None):
        entry_locks.append((incident_id, active, reason))
        timeline.append(("live_entry_lock", bool(active)))
        write_ok = lock_ok if active else lock_release_ok
        if active and other_incident_owns_lock:
            return {
                "ok": True,
                "locked": True,
                "status": "INITIAL_STOP_FAILURE_LIVE_ENTRY_LOCK_OWNED_BY_OTHER_INCIDENT",
            }
        if not active and other_incident_owns_lock:
            return {
                "ok": False,
                "locked": True,
                "status": "INITIAL_STOP_FAILURE_LIVE_ENTRY_LOCK_OWNED_BY_OTHER_INCIDENT",
            }
        if write_ok:
            lock_state["locked"] = bool(active)
            lock_state["incident_id"] = incident_id
        return {"ok": write_ok, "locked": bool(active) or not write_ok}

    def lock_reader():
        return {
            "ok": True,
            "locked": lock_state["locked"],
            "incident_id": lock_state["incident_id"],
        }

    def issue_token(pos, operation, extra=None):
        context = {
            "operation": operation,
            "symbol": pos.get("symbol"),
            "side": pos.get("side"),
            **dict(extra or {}),
        }
        return {"ok": token_ok, "token": "TEST-TOKEN" if token_ok else None, "context": context}

    def registry_field(row, *names):
        row = row if isinstance(row, dict) else {}
        metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        for name in names:
            value = row.get(name)
            if value not in (None, ""):
                return value
            value = metadata.get(name)
            if value not in (None, ""):
                return value
        return None

    def current_registry_evidence(pos):
        if callable(current_registry):
            return copy.deepcopy(current_registry(pos))
        if isinstance(current_registry, dict):
            return copy.deepcopy(current_registry)
        return _current_registry_for_test(pos)

    def registry_open(pos):
        if callable(unsafe_registry_open):
            result = unsafe_registry_open(pos)
        else:
            result = {"ok": True, "trade_id": "TR-UNSAFE-ENTRY-1"}
        if isinstance(result, dict) and result.get("ok") is True:
            pos["trade_registry_id"] = result.get("trade_id")
        return result

    runtime = {
            "hashlib": hashlib,
            "secrets": SimpleNamespace(token_hex=lambda _n: "NONCE"),
            "FALCON_INITIAL_STOP_FAILURE_CONTAINMENT_VERSION": "TEST-V1",
            "FALCON_MANAGEMENT_AMOUNT_TOLERANCE": 1e-9,
            "ROLE_EMERGENCY_TERMINAL_STOP_CLOSE": "EMERGENCY_TERMINAL_STOP_CLOSE",
            "HEALTH": health,
            "central_broker": broker,
            "data_hora_sp_str": lambda: "02/08/2026 12:00",
            "safe_float": _float,
            "falcon_position_identity": _identity,
            "_falcon_management_norm_symbol": _norm_symbol,
            "_falcon_management_norm_side": _norm_side,
            "_falcon_terminal_safe_text": lambda value, limit=240: (
                str(value)[:limit] if value not in (None, "") else None
            ),
            "_falcon_terminal_sanitize_projection": lambda value: copy.deepcopy(value),
            "falcon_terminal_stop_recovery_load": load,
            "falcon_terminal_stop_recovery_save": save,
            "register_falcon_trade_registry_open": registry_open,
            "_falcon_terminal_registry_evidence": current_registry_evidence,
            "_falcon_terminal_registry_field": registry_field,
            "_falcon_terminal_bool": lambda value: value is True or str(value).lower() in {"1", "true", "yes"},
            "falcon_terminal_stop_lifecycle_lock_id": lambda _pos: "LIFECYCLE-LOCK-1",
            "falcon_terminal_stop_acquire_lifecycle_lock": lambda _key, _nonce: {
                "ok": lifecycle_lock_ok,
                "acquired": lifecycle_lock_ok,
                "status": "LIFECYCLE_LOCK_ACQUIRED" if lifecycle_lock_ok else "LIFECYCLE_LOCK_HELD_BY_OTHER_WORKER",
                "backend_unavailable": False,
            },
            "falcon_prepare_position_client_order_id": lambda _pos, role, revision, attempt=0: {
                "ok": True,
                "send_allowed": resume_send_allowed,
                "client_order_id": "FEC1-INITIAL-STOP-1",
                "role": role,
                "revision": revision,
                "attempt": attempt,
            },
            "falcon_issue_management_token": issue_token,
            "_falcon_client_order_authority_projection": lambda value: dict(value),
            "_falcon_terminal_auth_projection": lambda auth, matches: {
                "ok": auth.get("ok"),
                "token_present": bool(auth.get("token")),
                "context_matches": matches,
            },
            "_falcon_terminal_stop_result_projection": lambda result, **_expected: dict(result),
            "falcon_terminal_stop_critical_alert": lambda _pos, state, blocked=False: {
                "attempted": True,
                "blocked": blocked,
                "state": state.get("attempt_state"),
            },
        }
    if lock_helper_present:
        runtime["falcon_initial_stop_failure_save_live_entry_lock"] = lock_writer
        runtime["falcon_initial_stop_failure_live_entry_lock_status"] = lock_reader

    namespace = _load_falcon_functions(
        (
            "falcon_initial_stop_failure_incident_id",
            "falcon_initial_stop_failure_lifecycle_lock_owner",
            "falcon_persist_unsafe_live_entry_registry",
            "falcon_initial_stop_failure_read_close_reconciliation",
            "_falcon_initial_stop_failure_position_mode_evidence",
            "falcon_initial_stop_failure_current_ownership_evidence",
            "falcon_initial_stop_failure_finalize_confirmed",
            "falcon_handle_initial_stop_failure_containment",
        ),
        runtime,
    )
    return namespace["falcon_handle_initial_stop_failure_containment"], broker, store, timeline, entry_locks, health


def test_not_sent_or_armed_entries_never_trigger_or_close():
    contain, broker, _store, _timeline, _locks, _health = _harness()
    not_sent = _order()
    not_sent["sent"] = False
    armed = _order()
    armed["disaster_stop"]["stop_operationally_armed"] = True

    assert contain(_signal(), not_sent)["initial_stop_failure_containment_triggered"] is False
    assert contain(_signal(), armed)["initial_stop_failure_containment_triggered"] is False
    assert broker.calls == []


@pytest.mark.parametrize("active", [False, True])
def test_incident_cannot_overwrite_or_clear_a_different_open_p0_lock(active):
    raw_lock = json.dumps(
        {
            "incident_id": "FALCON-INITIAL-STOP-OTHER",
            "active": True,
            "reason": "OTHER_UNRESOLVED_INCIDENT",
        }
    )
    writes = []
    namespace = _load_falcon_functions(
        ("falcon_initial_stop_failure_save_live_entry_lock",),
        {
            "json": json,
            "redis_lock": nullcontext(),
            "redis": object(),
            "__name__": "falcon_test",
            "FALCON_INITIAL_STOP_FAILURE_CONTAINMENT_VERSION": "TEST-V1",
            "FALCON_INITIAL_STOP_FAILURE_LIVE_ENTRIES_LOCK_KEY": "test:lock",
            "data_hora_sp_str": lambda: "02/08/2026 12:00",
            "_falcon_terminal_safe_text": lambda value, limit=240: str(value)[:limit],
            "bandwidth_redis_get_authoritative": lambda *_args, **_kwargs: raw_lock,
            "bandwidth_redis_set_if_absent": lambda *_args, **_kwargs: writes.append(True) or False,
            "bandwidth_redis_compare_and_delete": lambda *_args, **_kwargs: pytest.fail("active foreign lock must not be removed"),
        },
    )

    result = namespace["falcon_initial_stop_failure_save_live_entry_lock"](
        "FALCON-INITIAL-STOP-RESOLVED", active=active, reason="CLOSED"
    )

    assert result["ok"] is False
    assert result["locked"] is True
    assert result["status"] == "INITIAL_STOP_FAILURE_LIVE_ENTRY_LOCK_OWNED_BY_OTHER_INCIDENT"
    assert writes == ([True] if active else [])


@pytest.mark.parametrize(
    ("set_result", "existing", "expected_status", "expected_acquired"),
    [
        (False, "OWNER-SAME", "LIFECYCLE_LOCK_REENTERED_SAME_OWNER", True),
        (False, "OWNER-OTHER", "LIFECYCLE_LOCK_HELD_BY_OTHER_WORKER", False),
        (None, None, "LIFECYCLE_LOCK_BACKEND_UNAVAILABLE", False),
    ],
)
def test_lifecycle_lock_distinguishes_same_owner_other_worker_and_backend(
    set_result, existing, expected_status, expected_acquired
):
    namespace = _load_falcon_functions(
        ("falcon_terminal_stop_acquire_lifecycle_lock",),
        {
            "redis_lock": nullcontext(),
            "redis": object(),
            "__name__": "falcon_test",
            "FALCON_TERMINAL_STOP_LIFECYCLE_LOCK_PREFIX": "test:lifecycle",
            "bandwidth_redis_set_if_absent": lambda *_args, **_kwargs: set_result,
            "bandwidth_redis_get_authoritative": lambda *_args, **_kwargs: existing,
            "_falcon_terminal_safe_text": lambda value, limit=240: str(value)[:limit],
        },
    )

    result = namespace["falcon_terminal_stop_acquire_lifecycle_lock"](
        "LIFECYCLE-1", "OWNER-SAME"
    )

    assert result["acquired"] is expected_acquired
    assert result["status"] == expected_status


def test_initial_stop_lifecycle_lock_owner_is_deterministic_and_only_same_owner_reenters():
    owners = _load_falcon_functions(
        ("falcon_initial_stop_failure_lifecycle_lock_owner",),
        {"hashlib": hashlib},
    )
    incident_id = _incident_id_for_test()
    owner = owners["falcon_initial_stop_failure_lifecycle_lock_owner"](incident_id)

    assert owner == owners["falcon_initial_stop_failure_lifecycle_lock_owner"](incident_id)
    assert owner != owners["falcon_initial_stop_failure_lifecycle_lock_owner"](
        "FALCON-INITIAL-STOP-OTHER"
    )

    namespace = _load_falcon_functions(
        ("falcon_terminal_stop_acquire_lifecycle_lock",),
        {
            "redis_lock": nullcontext(),
            "redis": object(),
            "__name__": "falcon_test",
            "FALCON_TERMINAL_STOP_LIFECYCLE_LOCK_PREFIX": "test:lifecycle",
            "bandwidth_redis_set_if_absent": lambda *_args, **_kwargs: False,
            "bandwidth_redis_get_authoritative": lambda *_args, **_kwargs: owner,
            "_falcon_terminal_safe_text": lambda value, limit=240: str(value)[:limit],
        },
    )

    same = namespace["falcon_terminal_stop_acquire_lifecycle_lock"]("LIFECYCLE-1", owner)
    other = namespace["falcon_terminal_stop_acquire_lifecycle_lock"]("LIFECYCLE-1", "OTHER")

    assert same["status"] == "LIFECYCLE_LOCK_REENTERED_SAME_OWNER"
    assert same["acquired"] is True
    assert other["status"] == "LIFECYCLE_LOCK_HELD_BY_OTHER_WORKER"
    assert other["acquired"] is False


def test_lifecycle_lock_held_by_another_worker_reconciles_read_only_without_close():
    contain, broker, store, _timeline, _locks, health = _harness(
        broker=_Broker(pre_close_amount=0.5), lifecycle_lock_ok=False
    )

    result = contain(_signal(), _order())

    assert result["containment_status"] == (
        "INITIAL_STOP_FAILED_LIFECYCLE_LOCK_HELD_BY_OTHER_WORKER"
    )
    assert result["reconciliation"]["read_only"] is True
    assert result["reconciliation"]["residual_position_qty"] == 0.5
    assert result["falcon_live_entries_locked"] is True
    assert broker.calls == []
    assert health["falcon_live_entries_locked"] is True
    assert next(iter(store.values()))["ownership_evidence_current"]["ok"] is True


def test_unarmed_partial_stop_response_without_an_order_id_is_contained():
    contain, broker, store, _timeline, _locks, _health = _harness()
    order = _order("STOP_ORDER_ID_MISSING")
    order["disaster_stop"].pop("client_order_id")
    order["disaster_stop"].pop("order_id", None)

    result = contain(_signal(), order)

    assert result["initial_stop_failure_containment_triggered"] is True
    assert result["emergency_close_confirmed"] is True
    assert len(broker.calls) == 1
    assert next(iter(store.values()))["stop_status"] == "STOP_ORDER_ID_MISSING"


@pytest.mark.parametrize("stop_status", ["CANCELED", "NOT_FOUND", "REJECTED", "STOP_ORDER_ID_MISSING", "TIMEOUT"])
def test_all_unarmed_initial_stop_outcomes_persist_before_one_confirmed_close(stop_status):
    contain, broker, store, timeline, _locks, _health = _harness()

    result = contain(_signal(), _order(stop_status))

    assert result["containment_status"] == "INITIAL_STOP_FAILED_EMERGENCY_CLOSE_CONFIRMED"
    assert result["unsafe_entry_persisted"] is True
    assert result["ownership_confirmed"] is True
    assert result["emergency_close_attempted"] is True
    assert result["emergency_close_confirmed"] is True
    assert result["residual_position_qty"] == 0.0
    assert len(broker.calls) == 1
    assert timeline.index(("persist", "UNSAFE_LIVE_ENTRY_UNPROTECTED")) < timeline.index(("persist", "BROKER_CALL_PENDING"))
    assert next(iter(store.values()))["stop_status"] == stop_status


def test_exact_owned_leg_uses_token_exact_qty_side_and_factual_post_close_confirmation():
    contain, broker, store, _timeline, _locks, _health = _harness()

    result = contain(_signal(), _order())

    assert result["emergency_close_idempotency_key"].startswith("FALCON-INITIAL-STOP-")
    assert broker.calls[0]["amount"] == 0.5
    assert broker.calls[0]["expected_position_amount"] == 0.5
    assert broker.calls[0]["side"] == "LONG"
    assert broker.calls[0]["execution_auth_token"] == "TEST-TOKEN"
    assert broker.position_calls == [("SOLUSDT", "LONG", 0.5), ("SOLUSDT", "LONG", None)]
    state = next(iter(store.values()))
    assert state["emergency_close_confirmed"] is True
    assert state["position_snapshot_after"]["position_closed"] is True


def test_residual_position_after_sent_close_is_never_reported_confirmed_and_keeps_lock():
    contain, broker, store, _timeline, locks, _health = _harness(broker=_Broker(residual=0.1))

    result = contain(_signal(), _order())

    assert result["containment_status"] == "INITIAL_STOP_FAILED_EMERGENCY_CLOSE_FAILED"
    assert result["emergency_close_sent"] is True
    assert result["emergency_close_confirmed"] is False
    assert result["residual_position_qty"] == 0.1
    assert result["falcon_live_entries_locked"] is True
    assert len(broker.calls) == 1
    assert locks == [(result["emergency_close_idempotency_key"], True, "CANCELED")]
    assert next(iter(store.values()))["falcon_live_entries_locked"] is True


def test_confirmed_close_does_not_report_live_entry_unlock_when_durable_release_fails():
    contain, broker, store, _timeline, locks, _health = _harness(
        lock_release_ok=False
    )

    result = contain(_signal(), _order())

    assert result["emergency_close_confirmed"] is True
    assert result["falcon_live_entries_locked"] is True
    assert len(broker.calls) == 1
    assert locks[-1][1] is False
    assert next(iter(store.values()))["falcon_live_entries_locked"] is True


def test_historical_ownership_is_audit_only_when_current_ownership_confirms():
    historical = {
        "ok": False,
        "allowed": False,
        "requested_symbol": "SOLUSDT",
        "requested_side": "LONG",
        "reason_codes": ["HISTORICAL_DECISION_BLOCKED"],
    }
    contain, broker, store, _timeline, _locks, _health = _harness()

    result = contain(_signal(ownership=historical), _order())
    state = next(iter(store.values()))

    assert result["emergency_close_confirmed"] is True
    assert len(broker.calls) == 1
    assert state["ownership_evidence_at_entry"]["evidence"]["allowed"] is False
    assert state["ownership_evidence_current"]["ok"] is True


def test_current_manual_same_leg_blocks_even_when_historical_ownership_allowed():
    current_manual = lambda pos: _current_registry_for_test(
        pos,
        same_leg_other_records=[{"conflict_reason": "MANUAL_OR_EXTERNAL_SAME_LEG"}],
    )
    contain, broker, store, _timeline, _locks, health = _harness(
        current_registry=current_manual
    )

    result = contain(_signal(), _order())
    state = next(iter(store.values()))

    assert result["containment_status"] == "INITIAL_STOP_FAILED_OWNERSHIP_UNCONFIRMED"
    assert result["ownership_confirmed"] is False
    assert result["emergency_close_attempted"] is False
    assert result["falcon_live_entries_locked"] is True
    assert broker.calls == []
    assert state["attempt_state"] == "OWNERSHIP_EVIDENCE_INSUFFICIENT"
    assert state["ownership_evidence_current"]["manual_or_external_detected"] is True
    assert health["falcon_live_entries_locked"] is True


def test_manual_position_other_symbol_does_not_prevent_exact_owned_containment():
    ownership = {
        "allowed": True,
        "requested_symbol": "SOLUSDT",
        "requested_side": "LONG",
        "manual_same_symbol_side_count": 0,
        "manual_external_open_count": 1,
        "manual_external_positions": [{"symbol": "BTCUSDT", "side": "LONG"}],
        "reason_codes": [],
    }
    contain, broker, _store, _timeline, _locks, _health = _harness(
        current_registry=lambda pos: _current_registry_for_test(
            pos,
            ignored_same_leg_records=[{"symbol": "BTCUSDT", "side": "LONG"}],
        )
    )

    result = contain(_signal(ownership=ownership), _order())

    assert result["emergency_close_confirmed"] is True
    assert len(broker.calls) == 1


def test_manual_position_that_appears_after_pending_close_blocks_any_resend():
    incident_id = _incident_id_for_test()
    store = {
        incident_id: _persisted_incident_state(
            "BROKER_CALL_PENDING",
            emergency_close_attempted=True,
            emergency_close_sent=False,
        )
    }
    contain, broker, store, _timeline, _locks, health = _harness(
        store=store,
        broker=_Broker(pre_close_amount=0.5),
        current_registry=lambda pos: _current_registry_for_test(
            pos,
            same_leg_other_records=[{"conflict_reason": "MANUAL_OR_EXTERNAL_SAME_LEG"}],
        ),
    )

    result = contain(_signal(), _order())

    assert result["containment_status"] == "INITIAL_STOP_FAILED_OWNERSHIP_UNCONFIRMED"
    assert result["falcon_live_entries_locked"] is True
    assert broker.calls == []
    assert store[incident_id]["ownership_evidence_current"]["manual_or_external_detected"] is True
    assert health["falcon_live_entries_locked"] is True


def test_restart_uses_current_ownership_not_historical_signal_evidence():
    incident_id = _incident_id_for_test()
    store = {incident_id: _persisted_incident_state()}
    historical = {
        "ok": False,
        "evidence": {"allowed": False, "reason_codes": ["STALE_AT_ENTRY"]},
    }
    contain, broker, store, _timeline, _locks, _health = _harness(
        store=store, broker=_Broker(pre_close_amount=0.5)
    )

    result = contain(_signal(ownership=historical), _order())

    assert result["emergency_close_confirmed"] is True
    assert result["emergency_close_idempotency_key"] == incident_id
    assert len(broker.calls) == 1
    assert store[incident_id]["ownership_evidence_current"]["ok"] is True


def test_current_ownership_query_exception_keeps_incident_and_never_closes():
    def unavailable(_pos):
        raise RuntimeError("registry unavailable")

    contain, broker, store, _timeline, _locks, health = _harness(
        current_registry=unavailable
    )

    result = contain(_signal(), _order())
    state = next(iter(store.values()))

    assert result["containment_status"] == "INITIAL_STOP_FAILED_OWNERSHIP_UNCONFIRMED"
    assert result["falcon_live_entries_locked"] is True
    assert broker.calls == []
    assert state["ownership_evidence_current"]["ok"] is False
    assert state["ownership_checked_at"]
    assert health["falcon_live_entries_locked"] is True


@pytest.mark.parametrize(
    "current_registry",
    [
        {"ok": True, "status": "INVALID", "lifecycle_match_count": 1, "matches": {}},
        lambda pos: _current_registry_for_test(pos, partial=True),
    ],
)
def test_invalid_or_partial_current_ownership_payload_never_closes(current_registry):
    contain, broker, store, _timeline, _locks, _health = _harness(
        current_registry=current_registry
    )

    result = contain(_signal(), _order())

    assert result["containment_status"] == "INITIAL_STOP_FAILED_OWNERSHIP_UNCONFIRMED"
    assert result["falcon_live_entries_locked"] is True
    assert broker.calls == []
    assert next(iter(store.values()))["ownership_evidence_current"]["ok"] is False


@pytest.mark.parametrize(
    ("entry_position_side", "position_position_side"),
    [
        ("", "LONG"),
        ("BOTH", "LONG"),
        ("LONG", ""),
        ("LONG", "BOTH"),
    ],
)
def test_hedge_mode_requires_exact_entry_and_position_side(
    entry_position_side, position_position_side
):
    contain, broker, store, _timeline, _locks, _health = _harness(
        broker=_Broker(
            entry_position_side=entry_position_side,
            position_position_side=position_position_side,
            position_mode="HEDGE",
        )
    )

    result = contain(_signal(), _order())

    assert result["containment_status"] == "INITIAL_STOP_FAILED_OWNERSHIP_UNCONFIRMED"
    assert result["falcon_live_entries_locked"] is True
    assert broker.calls == []
    evidence = next(iter(store.values()))["position_mode_evidence"]
    assert evidence["position_mode"] == "HEDGE"
    assert evidence["expected_position_side"] == "LONG"


@pytest.mark.parametrize(
    ("side", "entry_side"),
    [("LONG", "BUY"), ("SHORT", "SELL")],
)
def test_exact_hedge_leg_allows_close_when_current_ownership_is_unique(side, entry_side):
    contain, broker, store, _timeline, _locks, _health = _harness(
        broker=_Broker(
            entry_side=entry_side,
            entry_position_side=side,
            position_position_side=side,
            position_mode="HEDGE",
        )
    )

    result = contain(_signal(side=side), _order())

    assert result["emergency_close_confirmed"] is True
    assert len(broker.calls) == 1
    assert next(iter(store.values()))["position_mode_evidence"]["position_mode"] == "HEDGE"


def test_explicit_one_way_both_side_with_no_opposite_leg_is_supported():
    contain, broker, store, _timeline, _locks, _health = _harness(
        broker=_Broker(
            entry_position_side="BOTH",
            position_position_side="BOTH",
            position_mode="ONE_WAY",
            opposite_position_open=False,
        )
    )

    result = contain(_signal(), _order())

    assert result["emergency_close_confirmed"] is True
    assert len(broker.calls) == 1
    evidence = next(iter(store.values()))["position_mode_evidence"]
    assert evidence["position_mode"] == "ONE_WAY"
    assert evidence["observed_position_side"] == "BOTH"


def test_position_side_conflict_never_closes_an_ambiguous_leg():
    class ConflictingPositionSideBroker(_Broker):
        def managed_position_snapshot(self, symbol, side, expected_amount=None):
            snapshot = super().managed_position_snapshot(symbol, side, expected_amount)
            if expected_amount is not None:
                snapshot["position_side"] = "SHORT"
            return snapshot

    contain, broker, store, _timeline, _locks, _health = _harness(
        broker=ConflictingPositionSideBroker()
    )

    result = contain(_signal(), _order())

    assert result["containment_status"] == "INITIAL_STOP_FAILED_OWNERSHIP_UNCONFIRMED"
    assert broker.calls == []
    assert next(iter(store.values()))["attempt_state"] == "OWNERSHIP_EVIDENCE_INSUFFICIENT"


def test_repeat_and_simulated_restart_reuse_persisted_incident_without_second_close():
    store = {}
    contain, broker, _store, _timeline, _locks, _health = _harness(store=store)
    first = contain(_signal(), _order())
    contain_after_restart, restarted_broker, _store, _timeline, _locks, _health = _harness(
        store=store, broker=broker
    )

    second = contain_after_restart(_signal(), _order())

    assert first["emergency_close_confirmed"] is True
    assert second["idempotent"] is True
    assert second["containment_status"] == "INITIAL_STOP_FAILED_EMERGENCY_CLOSE_CONFIRMED"
    assert len(restarted_broker.calls) == 1


def test_restart_from_unsafe_state_reconciles_the_same_incident_and_closes_once():
    incident_id = _incident_id_for_test()
    store = {incident_id: _persisted_incident_state()}
    contain, broker, store, _timeline, _locks, _health = _harness(
        store=store, broker=_Broker(pre_close_amount=0.5)
    )

    result = contain(_signal(), _order())

    assert result["emergency_close_confirmed"] is True
    assert result["emergency_close_idempotency_key"] == incident_id
    assert len(broker.calls) == 1
    assert store[incident_id]["containment_status"] == "INITIAL_STOP_FAILED_EMERGENCY_CLOSE_CONFIRMED"


def test_restart_from_pre_send_pending_reuses_the_same_close_client_order_id_once():
    incident_id = _incident_id_for_test()
    store = {
        incident_id: _persisted_incident_state(
            "BROKER_CALL_PENDING",
            emergency_close_attempted=True,
            emergency_close_sent=False,
        )
    }
    contain, broker, _store, _timeline, _locks, _health = _harness(
        store=store, broker=_Broker(pre_close_amount=0.5)
    )

    result = contain(_signal(), _order())

    assert result["emergency_close_confirmed"] is True
    assert broker.calls[0]["client_tag"] == "FEC1-INITIAL-STOP-1"
    assert len(broker.calls) == 1


def test_pending_restart_without_persisted_client_order_id_never_sends_blindly():
    incident_id = _incident_id_for_test()
    store = {
        incident_id: _persisted_incident_state(
            "BROKER_CALL_PENDING",
            emergency_close_attempted=True,
            emergency_close_sent=False,
            client_order_id_reservation={},
        )
    }
    contain, broker, _store, _timeline, _locks, health = _harness(
        store=store, broker=_Broker(pre_close_amount=0.5)
    )

    result = contain(_signal(), _order())

    assert result["containment_reason"] == "PERSISTED_CLOSE_CLIENT_ORDER_ID_REQUIRED"
    assert result["falcon_live_entries_locked"] is True
    assert broker.calls == []
    assert health["falcon_live_entries_locked"] is True


def test_pending_restart_never_resends_when_account_authority_cannot_prove_it_is_safe():
    incident_id = _incident_id_for_test()
    store = {
        incident_id: _persisted_incident_state(
            "BROKER_CALL_PENDING",
            emergency_close_attempted=True,
            emergency_close_sent=False,
        )
    }
    contain, broker, _store, _timeline, _locks, health = _harness(
        store=store,
        broker=_Broker(pre_close_amount=0.5),
        resume_send_allowed=False,
    )

    result = contain(_signal(), _order())

    assert result["containment_reason"] == (
        "ACCOUNT_CLIENT_ORDER_AUTHORITY_RECONCILIATION_REQUIRED"
    )
    assert result["falcon_live_entries_locked"] is True
    assert broker.calls == []
    assert health["falcon_live_entries_locked"] is True


def test_restart_after_lost_close_response_reconciles_flat_position_without_second_close():
    incident_id = _incident_id_for_test()
    store = {
        incident_id: _persisted_incident_state(
            "BROKER_CALL_PENDING",
            emergency_close_attempted=True,
            emergency_close_sent=None,
            send_outcome_unknown=True,
        )
    }
    contain, broker, _store, _timeline, _locks, _health = _harness(
        store=store,
        broker=_Broker(
            pre_close_amount=0.0,
            close_lookup={"ok": True, "status": "FILLED", "confirmed": True},
        ),
    )

    result = contain(_signal(), _order())

    assert result["emergency_close_confirmed"] is True
    assert result["containment_status"] == "INITIAL_STOP_FAILED_EMERGENCY_CLOSE_CONFIRMED"
    assert broker.calls == []


def test_restart_with_open_inconclusive_send_keeps_p0_lock_without_second_close():
    incident_id = _incident_id_for_test()
    store = {
        incident_id: _persisted_incident_state(
            "BROKER_CALL_PENDING",
            emergency_close_attempted=True,
            emergency_close_sent=None,
            send_outcome_unknown=True,
        )
    }
    contain, broker, _store, _timeline, _locks, health = _harness(
        store=store,
        broker=_Broker(
            pre_close_amount=0.5,
            close_lookup={"ok": True, "status": "OPEN", "order_id": "CLOSE-1"},
        ),
    )

    result = contain(_signal(), _order())

    assert result["emergency_close_confirmed"] is False
    assert result["falcon_live_entries_locked"] is True
    assert broker.calls == []
    assert health["falcon_live_entries_locked"] is True


@pytest.mark.parametrize(
    "status",
    ["INITIAL_STOP_FAILED_EMERGENCY_CLOSE_FAILED", "INITIAL_STOP_FAILED_OWNERSHIP_UNCONFIRMED"],
)
def test_existing_failed_or_ownership_incident_reconciles_and_can_evolve_without_new_identity(status):
    incident_id = _incident_id_for_test()
    store = {incident_id: _persisted_incident_state(status)}
    contain, broker, _store, _timeline, _locks, _health = _harness(
        store=store, broker=_Broker(pre_close_amount=0.5)
    )

    result = contain(_signal(), _order())

    assert result.get("idempotent") is not True
    assert result["emergency_close_idempotency_key"] == incident_id
    assert result["emergency_close_confirmed"] is True
    assert len(broker.calls) == 1
    assert ("SOLUSDT", "LONG", None) in broker.position_calls


def test_missing_live_entry_lock_helper_is_factual_but_does_not_block_owned_reduce_only_close():
    contain, broker, store, _timeline, _locks, health = _harness(
        lock_helper_present=False
    )

    result = contain(_signal(), _order())
    state = next(iter(store.values()))

    assert result["emergency_close_confirmed"] is True
    assert result["falcon_live_entries_locked"] is True
    assert len(broker.calls) == 1
    assert state["live_entry_lock_persistence_failed"] is True
    assert health["falcon_live_entries_locked"] is True


def test_auxiliary_lock_write_failure_keeps_entries_blocked_but_allows_owned_close():
    contain, broker, store, _timeline, _locks, health = _harness(
        lock_ok=False, lifecycle_lock_ok=True
    )

    result = contain(_signal(), _order())
    state = next(iter(store.values()))

    assert result["emergency_close_confirmed"] is True
    assert result["falcon_live_entries_locked"] is True
    assert len(broker.calls) == 1
    assert state["live_entry_lock_persistence_failed"] is True
    assert health["falcon_live_entries_locked"] is True


def test_terminal_persistence_failure_never_releases_the_live_entry_lock():
    contain, broker, store, _timeline, locks, health = _harness(
        save_outcomes=[True, True, True, False]
    )

    result = contain(_signal(), _order())

    assert result["emergency_close_confirmed"] is True
    assert result["containment_status"] == "INITIAL_STOP_FAILED_TERMINAL_PERSISTENCE_REQUIRED"
    assert result["falcon_live_entries_locked"] is True
    assert len(broker.calls) == 1
    assert all(active is True for _incident, active, _reason in locks)
    assert health["falcon_live_entries_locked"] is True
    assert next(iter(store.values()))["attempt_state"] == "BROKER_CALL_PENDING"


def test_terminal_save_then_durable_unlock_clears_health_when_no_other_p0_exists():
    contain, broker, _store, timeline, _locks, health = _harness()

    result = contain(_signal(), _order())

    assert result["emergency_close_confirmed"] is True
    assert result["falcon_live_entries_locked"] is False
    assert broker.calls
    assert health["falcon_live_entries_locked"] is False
    assert timeline.index(("persist", "INITIAL_STOP_FAILED_EMERGENCY_CLOSE_CONFIRMED")) < (
        timeline.index(("live_entry_lock", False))
    )


def test_terminal_incident_after_unlock_before_ack_save_remains_terminal_without_duplicate_close():
    incident_id = _incident_id_for_test()
    state = _persisted_incident_state(
        "INITIAL_STOP_FAILED_EMERGENCY_CLOSE_CONFIRMED",
        containment_status="INITIAL_STOP_FAILED_EMERGENCY_CLOSE_CONFIRMED",
        emergency_close_attempted=True,
        emergency_close_sent=True,
        emergency_close_confirmed=True,
        residual_position_qty=0.0,
        position_snapshot_after={"position_closed": True, "amount": 0.0},
    )
    store = {incident_id: state}
    contain, broker, store, _timeline, _locks, health = _harness(
        store=store,
        broker=_Broker(pre_close_amount=0.0),
        save_outcomes=[True, False],
    )

    first = contain(_signal(), _order())
    contain_after_restart, restarted_broker, _store, _timeline, _locks, health_after = _harness(
        store=store, broker=broker
    )
    second = contain_after_restart(_signal(), _order())

    assert first["emergency_close_confirmed"] is True
    assert first["falcon_live_entries_locked"] is False
    assert second["idempotent"] is True
    assert second["emergency_close_confirmed"] is True
    assert restarted_broker.calls == []
    assert health_after["falcon_live_entries_locked"] is False


def test_other_active_p0_lock_is_never_cleared_and_health_remains_true():
    contain, broker, _store, _timeline, _locks, health = _harness(
        other_incident_owns_lock=True
    )

    result = contain(_signal(), _order())

    assert result["emergency_close_confirmed"] is True
    assert result["falcon_live_entries_locked"] is True
    assert len(broker.calls) == 1
    assert health["falcon_live_entries_locked"] is True


def test_timestamp_fallback_persists_a_sent_entry_but_never_authorizes_a_close():
    contain, broker, store, _timeline, _locks, _health = _harness()
    signal = _signal()
    for key in ("id", "signal_id", "lifecycle_id"):
        signal.pop(key, None)
    order = _order()
    order.pop("order_id")
    order.pop("client_order_id")
    order.pop("client_tag", None)
    order["ts"] = "2026-08-02T12:00:00Z"

    result = contain(signal, order)

    assert result["unsafe_entry_persisted"] is True
    assert result["containment_status"] == "INITIAL_STOP_FAILED_OWNERSHIP_UNCONFIRMED"
    assert result["falcon_live_entries_locked"] is True
    assert broker.calls == []
    assert len(store) == 1


def test_incident_persistence_or_token_or_close_exception_never_allows_blind_retry():
    failed_save, broker_a, _store_a, _timeline_a, _locks_a, _health_a = _harness(persistence_ok=False)
    no_token, broker_b, store_b, _timeline_b, _locks_b, _health_b = _harness(token_ok=False)
    close_exception, broker_c, store_c, _timeline_c, _locks_c, _health_c = _harness(
        broker=_Broker(raise_close=True)
    )

    persistence = failed_save(_signal(), _order())
    token = no_token(_signal(), _order())
    exception = close_exception(_signal(), _order())

    assert persistence["containment_status"] == "INITIAL_STOP_FAILED_PERSISTENCE_REQUIRED"
    assert broker_a.calls == []
    assert token["containment_status"] == "INITIAL_STOP_FAILED_EMERGENCY_CLOSE_FAILED"
    assert broker_b.calls == []
    assert next(iter(store_b.values()))["attempt_state"] == "EMERGENCY_CLOSE_PRE_SEND_BLOCKED"
    assert exception["emergency_close_confirmed"] is False
    assert exception["falcon_live_entries_locked"] is True
    assert len(broker_c.calls) == 1
    assert next(iter(store_c.values()))["containment_status"] == "INITIAL_STOP_FAILED_EMERGENCY_CLOSE_FAILED"


def test_direct_falcon_consumer_invokes_containment_before_generic_rejection_and_preserves_risk_decision():
    tree = ast.parse(FALCON_SOURCE.read_text(encoding="utf-8"))
    original = next(
        copy.deepcopy(node)
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "execute_signal_if_allowed"
    )
    module = ast.Module(body=[original], type_ignores=[])
    ast.fix_missing_locations(module)
    risk_decision = {"allowed": True, "decision": "ALLOW", "reasons": [], "warnings": []}
    calls = []

    class Broker:
        def issue_execution_auth_token(self, **_kwargs):
            return {"ok": True, "token": "TEST"}

        def place_market_order(self, **_kwargs):
            return {
                **_order("CANCELED"),
                "entry_acknowledged": True,
                "returned_client_order_id_matches": True,
            }

    namespace = {
        "FALCON_MODE": "LIVE",
        "FALCON_REAL_NOTIONAL_USDT": 10.0,
        "FALCON_REQUIRE_REAL_TP50_CAPABLE": False,
        "FALCON_REAL_MAX_POSITIONS": 1,
        "ENABLE_REAL_TRADING": True,
        "BROKER_IMPORT_ERROR": None,
        "ROLE_ENTRY": "ENTRY",
        "HEALTH": {},
        "central_broker": Broker(),
        "get_positions": lambda: {},
        "falcon_initial_stop_failure_live_entry_lock_status": lambda: {"ok": True, "locked": False},
        "falcon_resolve_partial_capable_notional": lambda _sig: {"allowed": True, "notional_usdt": 10.0},
        "safe_float": _float,
        "falcon_live_positions_count": lambda _positions: 0,
        "central_can_open_trade": lambda _sig, positions=None: risk_decision,
        "falcon_validate_position_ownership_limit_evidence": lambda _decision, sig=None: {"ok": True, "evidence": {"allowed": True}},
        "falcon_prepare_canonical_client_order_id": lambda _identity: {"send_allowed": True, "client_order_id": "ENTRY-CID-1"},
        "falcon_prepare_initial_disaster_stop_client_order_id": lambda **_identity: {"send_allowed": True},
        "falcon_handle_unsafe_live_entry_identity": lambda _sig, _order: pytest.fail("identity path is not expected"),
        "falcon_handle_initial_stop_failure_containment": lambda _sig, received_order: calls.append(received_order) or {
            "initial_stop_failure_containment_triggered": True,
            "falcon_live_entries_locked": True,
            "containment_status": "INITIAL_STOP_FAILED_OWNERSHIP_UNCONFIRMED",
            "containment_reason": "OWNERSHIP_EVIDENCE_INSUFFICIENT",
        },
        "hashlib": hashlib,
        "json": __import__("json"),
    }
    exec(compile(module, str(FALCON_SOURCE), "exec"), namespace)
    sig = {
        "id": "SIG-1",
        "signal_id": "SIG-1",
        "lifecycle_id": "LC-1",
        "symbol": "SOLUSDT",
        "side": "LONG",
        "setup": "FALCON15",
        "stop": 75.0,
    }

    allowed, decision = namespace["execute_signal_if_allowed"](sig, positions={})

    assert allowed is False
    assert decision["status"] == "INITIAL_STOP_FAILED_OWNERSHIP_UNCONFIRMED"
    assert decision["risk_manager_decision"] is risk_decision
    assert len(calls) == 1
    assert sig["initial_stop_failure_containment"]["initial_stop_failure_containment_triggered"] is True
    assert sig.get("entry_retry_blocked") is not True  # Stub did not claim state mutation.


def test_scanner_persists_only_allowed_signals_after_the_containment_rejection_branch():
    tree = ast.parse(FALCON_SOURCE.read_text(encoding="utf-8"))
    scanner = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "scanner_loop"
    )
    execute_calls = [
        node
        for node in ast.walk(scanner)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "execute_signal_if_allowed"
    ]
    persist_calls = [
        node
        for node in ast.walk(scanner)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "falcon_persist_accepted_signal"
    ]
    rejected_continue = any(
        isinstance(node, ast.If)
        and isinstance(node.test, ast.UnaryOp)
        and isinstance(node.test.op, ast.Not)
        and isinstance(node.test.operand, ast.Name)
        and node.test.operand.id == "execution_allowed"
        and any(isinstance(child, ast.Continue) for child in ast.walk(node))
        for node in ast.walk(scanner)
    )

    assert len(execute_calls) == 1
    assert len(persist_calls) == 1
    assert execute_calls[0].lineno < persist_calls[0].lineno
    assert rejected_continue is True


@pytest.mark.parametrize(
    ("live_send_enabled", "preview_isolation"),
    [(False, None), (None, True), (False, True)],
)
def test_sent_entry_execution_state_conflicts_are_persisted_and_still_contained(
    live_send_enabled, preview_isolation
):
    contain, broker, store, _timeline, locks, _health = _harness()
    order = _order()
    if live_send_enabled is not None:
        order["live_send_enabled"] = live_send_enabled
    if preview_isolation is not None:
        order["preview_isolation"] = preview_isolation

    result = contain(_signal(), order)
    state = next(iter(store.values()))

    assert result["initial_stop_failure_containment_triggered"] is True
    assert result["execution_state_conflict_status"] == (
        "INITIAL_STOP_FAILURE_EXECUTION_STATE_CONFLICT"
    )
    assert result["containment_reason"] != "DRY_RUN_OR_PREVIEW_NO_CLOSE"
    assert state["execution_state_conflict"] is True
    assert state["execution_state_conflict_status"] == (
        "INITIAL_STOP_FAILURE_EXECUTION_STATE_CONFLICT"
    )
    assert any(active is True for _incident, active, _reason in locks)
    assert result["emergency_close_confirmed"] is True
    assert len(broker.calls) == 1


def test_unsent_conflicting_local_execution_labels_never_close():
    contain, broker, _store, _timeline, _locks, _health = _harness()
    order = _order()
    order.update({"sent": False, "live_send_enabled": False, "preview_isolation": True})

    result = contain(_signal(), order)

    assert result["initial_stop_failure_containment_triggered"] is False
    assert result["containment_reason"] == "ENTRY_NOT_SENT"
    assert broker.calls == []


def test_registry_write_is_required_before_current_ownership_recheck_and_close():
    registry_rows = []
    ownership_reads = []

    class EntryAndContainmentBroker(_Broker):
        def __init__(self):
            super().__init__()
            self.entry_calls = []

        def issue_execution_auth_token(self, **_kwargs):
            return {"ok": True, "token": "TEST"}

        def place_market_order(self, **kwargs):
            self.entry_calls.append(kwargs)
            return {
                **_order("CANCELED"),
                "entry_acknowledged": True,
                "returned_client_order_id_matches": True,
            }

        def managed_position_snapshot(self, symbol, side, expected_amount=None):
            # ``broker.managed_position_snapshot`` exposes the factual leg as
            # ``positions[0].side``; it does not manufacture a top-level
            # ``position_side``/position mode for the current broker contract.
            snapshot = super().managed_position_snapshot(
                symbol, side, expected_amount=expected_amount
            )
            snapshot.pop("position_side", None)
            snapshot.pop("position_mode", None)
            snapshot.pop("opposite_position_open", None)
            return snapshot

    def unsafe_registry_open(pos):
        assert registry_rows == []
        assert pos["unsafe_entry_status"] == "UNSAFE_LIVE_ENTRY_UNPROTECTED"
        assert pos["initial_stop_failure_incident_id"].startswith(
            "FALCON-INITIAL-STOP-"
        )
        assert pos["execution_mode"] == "LIVE"
        assert pos["registry_mode"] == "REAL"
        assert pos["live_order_id"] == "ENTRY-1"
        assert pos["live_client_order_id"] == "ENTRY-CID-1"
        assert pos["lifecycle_id"] == "LC-INITIAL-STOP-1"
        assert pos["symbol"] == "SOLUSDT"
        assert pos["side"] == "LONG"
        row = {
            "trade_id": "TR-UNSAFE-ENTRY-1",
            "bot": "FALCON",
            "execution_mode": "LIVE",
            "registry_mode": "REAL",
            "lifecycle_id": pos["lifecycle_id"],
            "broker_order_id": pos["live_order_id"],
            "client_order_id": pos["live_client_order_id"],
            "symbol": pos["symbol"],
            "side": pos["side"],
            "metadata": {
                "unsafe_entry_status": pos["unsafe_entry_status"],
                "initial_stop_failure_incident_id": pos[
                    "initial_stop_failure_incident_id"
                ],
            },
        }
        registry_rows.append(row)
        return {"ok": True, "trade_id": row["trade_id"]}

    def current_registry(pos):
        ownership_reads.append(copy.deepcopy(pos))
        assert registry_rows, "ownership may only read the Registry after unsafe entry persistence"
        return {
            "ok": True,
            "status": "REGISTRY_LIFECYCLE_MATCHED",
            "partial": False,
            "lifecycle_match_count": 1,
            "matches": [copy.deepcopy(registry_rows[0])],
            "same_leg_other_records": [],
            "ignored_same_leg_records": [],
        }

    broker = EntryAndContainmentBroker()
    contain, broker, store, _timeline, _locks, _health = _harness(
        broker=broker,
        current_registry=current_registry,
        unsafe_registry_open=unsafe_registry_open,
    )
    namespace, _execution_broker, risk_decision = _original_execute_signal_namespace(
        handler_marker=contain,
        fallback=lambda *_args, **_kwargs: pytest.fail("normal containment is expected"),
        broker=broker,
    )
    sig = {
        "id": "SIGNAL-INITIAL-STOP-1",
        "signal_id": "SIGNAL-INITIAL-STOP-1",
        "lifecycle_id": "LC-INITIAL-STOP-1",
        "symbol": "SOLUSDT",
        "side": "LONG",
        "setup": "FALCON15",
        "stop": 75.0,
    }

    allowed, decision = namespace["execute_signal_if_allowed"](sig, positions={})

    assert allowed is False
    assert decision["risk_manager_decision"] is risk_decision
    assert decision["initial_stop_failure_containment"]["emergency_close_confirmed"] is True
    assert len(broker.entry_calls) == 1
    assert len(broker.calls) == 1
    assert len(registry_rows) == 1
    assert ownership_reads
    state = next(iter(store.values()))
    assert state["unsafe_entry_registry_persisted"] is True
    assert state["unsafe_entry_registry_trade_id"] == "TR-UNSAFE-ENTRY-1"
    assert state["ownership_evidence_current"]["ok"] is True


def test_registry_write_failure_blocks_close_without_claiming_current_ownership():
    contain, broker, store, _timeline, _locks, health = _harness(
        unsafe_registry_open=lambda _pos: {
            "ok": False,
            "status": "TRADE_REGISTRY_WRITE_FAILED",
        }
    )

    result = contain(_signal(), _order())

    assert result["containment_status"] == "INITIAL_STOP_FAILED_OWNERSHIP_UNCONFIRMED"
    assert result["containment_reason"] == "UNSAFE_ENTRY_REGISTRY_PERSISTENCE_REQUIRED"
    assert broker.calls == []
    assert next(iter(store.values()))["attempt_state"] == (
        "UNSAFE_ENTRY_REGISTRY_PERSISTENCE_REQUIRED"
    )
    assert health["falcon_live_entries_locked"] is True


def _original_execute_signal_namespace(*, handler_marker, fallback, broker=None):
    tree = ast.parse(FALCON_SOURCE.read_text(encoding="utf-8"))
    original = next(
        copy.deepcopy(node)
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "execute_signal_if_allowed"
    )
    module = ast.Module(body=[original], type_ignores=[])
    ast.fix_missing_locations(module)
    risk_decision = {"allowed": True, "decision": "ALLOW", "reasons": [], "warnings": []}

    class EntryBroker:
        def __init__(self):
            self.place_calls = []

        def issue_execution_auth_token(self, **_kwargs):
            return {"ok": True, "token": "TEST"}

        def place_market_order(self, **kwargs):
            self.place_calls.append(kwargs)
            return {
                **_order("CANCELED"),
                "entry_acknowledged": True,
                "returned_client_order_id_matches": True,
            }

    broker = broker or EntryBroker()
    namespace = {
        "FALCON_MODE": "LIVE",
        "FALCON_REAL_NOTIONAL_USDT": 10.0,
        "FALCON_REQUIRE_REAL_TP50_CAPABLE": False,
        "FALCON_REAL_MAX_POSITIONS": 1,
        "ENABLE_REAL_TRADING": True,
        "BROKER_IMPORT_ERROR": None,
        "ROLE_ENTRY": "ENTRY",
        "HEALTH": {},
        "central_broker": broker,
        "get_positions": lambda: {},
        "falcon_initial_stop_failure_live_entry_lock_status": lambda: {"ok": True, "locked": False},
        "falcon_resolve_partial_capable_notional": lambda _sig: {"allowed": True, "notional_usdt": 10.0},
        "safe_float": _float,
        "falcon_live_positions_count": lambda _positions: 0,
        "central_can_open_trade": lambda _sig, positions=None: risk_decision,
        "falcon_validate_position_ownership_limit_evidence": lambda _decision, sig=None: {"ok": True, "evidence": {"allowed": True}},
        "falcon_prepare_canonical_client_order_id": lambda _identity: {"send_allowed": True, "client_order_id": "ENTRY-CID-1"},
        "falcon_prepare_initial_disaster_stop_client_order_id": lambda **_identity: {"send_allowed": True},
        "falcon_handle_unsafe_live_entry_identity": lambda _sig, _order: pytest.fail("identity path is not expected"),
        "falcon_initial_stop_failure_containment_internal_error": fallback,
        "_falcon_terminal_safe_text": lambda value, limit=240: str(value)[:limit],
        "hashlib": hashlib,
        "json": json,
    }
    if handler_marker is not _MISSING:
        namespace["falcon_handle_initial_stop_failure_containment"] = handler_marker
    exec(compile(module, str(FALCON_SOURCE), "exec"), namespace)
    return namespace, broker, risk_decision


_MISSING = object()


@pytest.mark.parametrize(
    "handler_marker",
    [
        _MISSING,
        lambda _sig, _order: (_ for _ in ()).throw(RuntimeError("handler exploded")),
        lambda _sig, _order: None,
        lambda _sig, _order: {},
    ],
    ids=["missing", "exception", "none", "invalid_dict"],
)
def test_unusable_initial_stop_handler_denies_with_p0_fallback_without_blind_close(
    handler_marker,
):
    fallback_calls = []

    def fallback(sig, order, *, error=None):
        fallback_calls.append((copy.deepcopy(sig), copy.deepcopy(order), error))
        return {
            "initial_stop_failure_containment_triggered": True,
            "initial_stop_failure_containment_attempted": True,
            "containment_status": "INITIAL_STOP_FAILURE_CONTAINMENT_INTERNAL_ERROR",
            "containment_reason": error,
            "falcon_live_entries_locked": True,
            "reconciliation_required": True,
        }

    namespace, broker, risk_decision = _original_execute_signal_namespace(
        handler_marker=handler_marker,
        fallback=fallback,
    )
    sig = {
        "id": "SIG-HANDLER-FAIL",
        "signal_id": "SIG-HANDLER-FAIL",
        "lifecycle_id": "LC-HANDLER-FAIL",
        "symbol": "SOLUSDT",
        "side": "LONG",
        "setup": "FALCON15",
        "stop": 75.0,
    }

    allowed, decision = namespace["execute_signal_if_allowed"](sig, positions={})

    assert allowed is False
    assert decision["decision"] == "DENY"
    assert decision["status"] == "INITIAL_STOP_FAILURE_CONTAINMENT_INTERNAL_ERROR"
    assert decision["risk_manager_decision"] is risk_decision
    assert decision["initial_stop_failure_containment"]["reconciliation_required"] is True
    assert len(fallback_calls) == 1
    assert len(broker.place_calls) == 1


def test_internal_handler_error_persists_minimal_p0_record_lock_and_critical_alert():
    store = {}
    locks = []
    alerts = []

    def load(incident_id):
        return {"ok": True, "incident": copy.deepcopy(store.get(incident_id, {}))}

    def save(incident_id, state):
        store[incident_id] = copy.deepcopy(state)
        return {"ok": True, "status": "PERSISTED"}

    def lock(incident_id, *, active, reason=None):
        locks.append((incident_id, active, reason))
        return {"ok": True, "locked": bool(active), "status": "LOCKED"}

    namespace = _load_falcon_functions(
        (
            "falcon_initial_stop_failure_incident_id",
            "falcon_initial_stop_failure_containment_internal_error",
        ),
        {
            "hashlib": hashlib,
            "FALCON_INITIAL_STOP_FAILURE_CONTAINMENT_VERSION": "TEST-V1",
            "HEALTH": {},
            "data_hora_sp_str": lambda: "03/08/2026 12:00",
            "falcon_position_identity": _identity,
            "_falcon_management_norm_symbol": _norm_symbol,
            "_falcon_management_norm_side": _norm_side,
            "_falcon_terminal_safe_text": lambda value, limit=240: str(value)[:limit],
            "_falcon_terminal_sanitize_projection": lambda value: copy.deepcopy(value),
            "falcon_terminal_stop_recovery_load": load,
            "falcon_terminal_stop_recovery_save": save,
            "falcon_initial_stop_failure_save_live_entry_lock": lock,
            "falcon_terminal_stop_critical_alert": lambda _pos, state, blocked=False: alerts.append(
                (state["incident_id"], blocked)
            ) or {"attempted": True, "blocked": blocked},
        },
    )

    result = namespace["falcon_initial_stop_failure_containment_internal_error"](
        _signal(), _order(), error="handler missing"
    )

    assert result["initial_stop_failure_containment_triggered"] is True
    assert result["initial_stop_failure_containment_attempted"] is True
    assert result["containment_status"] == "INITIAL_STOP_FAILURE_CONTAINMENT_INTERNAL_ERROR"
    assert result["reconciliation_required"] is True
    assert len(store) == 1
    state = next(iter(store.values()))
    assert state["emergency_close_attempted"] is False
    assert state["falcon_live_entries_locked"] is True
    assert locks and locks[0][1] is True
    assert alerts and alerts[0][1] is True


def test_live_entry_lock_check_and_write_are_atomic_for_competing_incidents():
    backend = {}
    backend_lock = threading.RLock()
    barrier = threading.Barrier(3)
    results = {}

    def get(_redis, key, **_kwargs):
        with backend_lock:
            return backend.get(key)

    def set_if_absent(_redis, key, value, **_kwargs):
        with backend_lock:
            if key in backend:
                return False
            backend[key] = value
            return True

    def compare_and_delete(_redis, key, expected, **_kwargs):
        with backend_lock:
            if backend.get(key) != expected:
                return False
            backend.pop(key, None)
            return True

    namespace = _load_falcon_functions(
        ("falcon_initial_stop_failure_save_live_entry_lock",),
        {
            "json": json,
            "redis_lock": backend_lock,
            "redis": object(),
            "__name__": "falcon_test",
            "FALCON_INITIAL_STOP_FAILURE_CONTAINMENT_VERSION": "TEST-V1",
            "FALCON_INITIAL_STOP_FAILURE_LIVE_ENTRIES_LOCK_KEY": "test:lock",
            "data_hora_sp_str": lambda: "02/08/2026 12:00",
            "_falcon_terminal_safe_text": lambda value, limit=240: str(value)[:limit],
            "bandwidth_redis_get_authoritative": get,
            "bandwidth_redis_set_if_absent": set_if_absent,
            "bandwidth_redis_compare_and_delete": compare_and_delete,
        },
    )
    writer = namespace["falcon_initial_stop_failure_save_live_entry_lock"]

    def activate(incident_id):
        barrier.wait()
        results[incident_id] = writer(incident_id, active=True, reason="P0")

    threads = [
        threading.Thread(target=activate, args=(incident_id,))
        for incident_id in ("INCIDENT-A", "INCIDENT-B")
    ]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join(timeout=5)
        assert not thread.is_alive()

    winners = [key for key, value in results.items() if value["ok"] is True]
    losers = [key for key, value in results.items() if value["ok"] is False]
    assert len(winners) == 1
    assert len(losers) == 1
    assert results[losers[0]]["status"] == (
        "INITIAL_STOP_FAILURE_LIVE_ENTRY_LOCK_OWNED_BY_OTHER_INCIDENT"
    )
    assert json.loads(backend["test:lock"])["incident_id"] == winners[0]

    wrong_release = writer(losers[0], active=False, reason="wrong owner")
    winner_release = writer(winners[0], active=False, reason="resolved")
    assert wrong_release["ok"] is False
    assert winner_release["ok"] is True
    assert winner_release["locked"] is False


def test_close_requires_current_ownership_ok_and_has_no_permissive_position_side_check():
    tree = ast.parse(FALCON_SOURCE.read_text(encoding="utf-8"))
    handler = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "falcon_handle_initial_stop_failure_containment"
    )
    ownership_assign = next(
        node
        for node in ast.walk(handler)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Subscript)
            and isinstance(target.value, ast.Name)
            and target.value.id == "state"
            and isinstance(target.slice, ast.Constant)
            and target.slice.value == "ownership_confirmed"
            for target in node.targets
        )
    )
    position_assign = next(
        node
        for node in ast.walk(handler)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "position_evidence_ok"
            for target in node.targets
        )
    )

    ownership_source = ast.unparse(ownership_assign.value)
    position_source = ast.unparse(position_assign.value)
    assert "current_ownership['ok'] is True" in ownership_source
    assert "position_side" not in position_source
