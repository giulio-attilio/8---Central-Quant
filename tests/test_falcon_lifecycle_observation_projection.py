from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FALCON_SOURCE = ROOT / "bots" / "falcon.py"


def _function(name: str, globals_dict: dict, definition_index: int = -1):
    """Load one function without importing Falcon or starting its runtime."""
    tree = ast.parse(FALCON_SOURCE.read_text(encoding="utf-8"))
    definitions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name]
    assert definitions, name
    module = ast.Module(body=[definitions[definition_index]], type_ignores=[])
    namespace = dict(globals_dict)
    exec(compile(module, str(FALCON_SOURCE), "exec"), namespace)
    return namespace[name]


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class _RegistryProbe:
    def __init__(self):
        self.updates = []
        self.opens = []

    def register_open_trade(self, **payload):
        self.opens.append(payload)
        return {"ok": True, "action": "OPEN_REGISTERED", "trade_id": "FALCON:FALCON15:SOLUSDT:SHORT"}

    def update_trade(self, trade_id, **updates):
        self.updates.append((trade_id, updates))
        return {"ok": True, "action": "TRADE_UPDATED", "trade_id": trade_id}

    def close_trade(self, **updates):
        self.updates.append((updates.get("trade_id"), updates))
        return {"ok": True, "action": "TRADE_CLOSED", "trade_id": updates.get("trade_id")}

    @staticmethod
    def make_trade_id(*_args):
        return "FALCON:FALCON15:SOLUSDT:SHORT"


def test_live_order_projection_preserves_complete_factual_stop_without_importing_runtime():
    health = {}
    project = _function(
        "falcon_sync_live_order_state",
        {
            "safe_float": _safe_float,
            "FALCON_REAL_POSITION_MANAGEMENT_HARDENING_VERSION": "TEST",
            "FALCON_CLIENT_ORDER_ID_GENERATOR_VERSION": "TEST-CID-V1",
            "HEALTH": health,
        },
    )
    signal = {"symbol": "SOLUSDT", "side": "SHORT", "stop": 77.5585142857143}
    order = {
        "sent": True,
        "order_id": "2077030442691940352",
        "client_order_id": "FALCON-LIVE-FALCON15-1784037618",
        "amount": 0.12,
        "price_ref": 76.93,
        "ts": "14/07/2026 11:00:22",
        "disaster_stop": {
            "ok": True,
            "created": True,
            "status": "DISASTER_STOP_CREATED",
            "order_id": "2077030444402577408",
            "client_order_id": "FDS1-0123456789ABCDEF01234567",
            "stop_created": True,
            "client_order_id_reserved": True,
            "client_order_id_unique": True,
            "client_order_id_reservation_status": "RESERVED_UNIQUE",
            "stop_operationally_armed": True,
            "symbol": "SOL/USDT:USDT",
            "side": "buy",
            "amount": 0.12,
            "stop_price": 77.5585142857143,
            "working_type": "MARK_PRICE",
        },
    }

    projected = project(signal, order)

    assert projected["broker_stop_order_id"] == "2077030444402577408"
    assert projected["broker_stop_client_order_id"] == "FDS1-0123456789ABCDEF01234567"
    assert projected["disaster_stop_client_order_id"] == "FDS1-0123456789ABCDEF01234567"
    assert projected["disaster_stop_client_order_id_unique"] is True
    assert projected["lifecycle_id"] == "CENTRAL-FALCON-LIFECYCLE:FALCON-LIVE-FALCON15-1784037618"
    assert projected["broker_stop_status"] == "DISASTER_STOP_CREATED"
    assert projected["broker_stop_trigger_type"] == "MARK_PRICE"
    assert projected["broker_stop_side"] == "buy"
    assert projected["broker_stop_symbol"] == "SOL/USDT:USDT"
    assert projected["broker_stop_confirmed_at"] == "14/07/2026 11:00:22"
    assert projected["broker_ack_at"] == "14/07/2026 11:00:22"
    assert projected["disaster_stop_confirmed"] is True
    assert health["falcon_disaster_stop_client_order_id"] == "FDS1-0123456789ABCDEF01234567"
    assert health["falcon_disaster_stop_client_order_id_unique"] is True


def test_protected_entry_with_ack_persistence_failure_is_consumed_and_registered_once():
    health = {}
    sync = _function(
        "falcon_sync_live_order_state",
        {
            "safe_float": _safe_float,
            "FALCON_REAL_POSITION_MANAGEMENT_HARDENING_VERSION": "TEST",
            "FALCON_CLIENT_ORDER_ID_GENERATOR_VERSION": "TEST-CID-V1",
            "HEALTH": health,
        },
    )
    broker_result = {
        "ok": False,
        "status": "LIVE_SENT_PROTECTED_ENTRY_ACK_PERSISTENCE_ERROR",
        "sent": True,
        "entry_acknowledged": True,
        "entry_ack_persistence_degraded": True,
        "order_id": "ENTRY-ACK-DEGRADED-1",
        "client_order_id": "FALCON-LIVE-FALCON15-ACK-1",
        "amount": 0.13,
        "price_ref": 76.212,
        "ts": "21/07/2026 12:00:00",
        "disaster_stop": {
            "ok": True,
            "stop_created": True,
            "stop_operationally_armed": True,
            "order_id": "STOP-ACK-DEGRADED-1",
            "client_order_id": "FDS1-ACK-DEGRADED-000000001",
            "client_order_id_reserved": True,
            "client_order_id_unique": True,
            "client_order_id_reservation_status": "RESERVED_UNIQUE",
            "status": "DISASTER_STOP_CREATED",
            "stop_price": 75.924,
            "amount": 0.13,
            "symbol": "SOL/USDT:USDT",
            "side": "sell",
            "position_side": "LONG",
        },
    }

    class BrokerProbe:
        def __init__(self):
            self.place_calls = []

        @staticmethod
        def issue_execution_auth_token(context):
            assert context["client_tag"] == "FALCON-LIVE-FALCON15-ACK-1"
            return {"ok": True, "token": "TEST-ONLY-TOKEN"}

        def place_market_order(self, **payload):
            self.place_calls.append(payload)
            return broker_result

    broker = BrokerProbe()
    original_consumer = _function(
        "execute_signal_if_allowed",
        {
            "FALCON_MODE": "LIVE",
            "FALCON_REAL_NOTIONAL_USDT": 10.0,
            "FALCON_REQUIRE_REAL_TP50_CAPABLE": False,
            "FALCON_REAL_MAX_POSITIONS": 1,
            "ENABLE_REAL_TRADING": True,
            "BROKER_IMPORT_ERROR": None,
            "ROLE_ENTRY": "ENTRY",
            "HEALTH": health,
            "central_broker": broker,
            "safe_float": _safe_float,
            "falcon_resolve_partial_capable_notional": lambda _sig: {
                "allowed": True,
                "notional_usdt": 10.0,
            },
            "falcon_live_positions_count": lambda _positions: 0,
            "central_can_open_trade": lambda _sig, positions=None: {
                "allowed": True,
                "decision": "ALLOW",
                "reasons": [],
                "warnings": [],
            },
            "falcon_validate_position_ownership_limit_evidence": (
                lambda _decision, sig=None: {"ok": True, "evidence": {}}
            ),
            "falcon_prepare_canonical_client_order_id": lambda _identity: {
                "ok": True,
                "send_allowed": True,
                "client_order_id": "FALCON-LIVE-FALCON15-ACK-1",
            },
            "falcon_prepare_initial_disaster_stop_client_order_id": (
                lambda **_identity: {
                    "ok": True,
                    "send_allowed": True,
                    "client_order_id_unique": True,
                    "client_order_id": "FDS1-ACK-DEGRADED-000000001",
                }
            ),
        },
        definition_index=0,
    )

    consume = _function(
        "execute_signal_if_allowed",
        {
            "_ORIGINAL_EXECUTE_SIGNAL_IF_ALLOWED_BEFORE_RPM_V1": original_consumer,
            "falcon_sync_live_order_state": sync,
            "HEALTH": health,
        },
    )
    signal = {
        "id": "FALCON15:SOLUSDT:LONG",
        "symbol": "SOLUSDT",
        "side": "LONG",
        "setup": "FALCON15",
        "entry": 76.212,
        "stop": 75.924,
        "tp50": 76.50,
        "execution_mode": "LIVE",
        "lifecycle_id": "CENTRAL-FALCON-LIFECYCLE:ACK-DEGRADED-1",
    }

    accepted_for_persistence, decision = consume(signal, positions={})

    assert accepted_for_persistence is True
    assert len(broker.place_calls) == 1
    assert broker.place_calls[0]["client_tag"] == "FALCON-LIVE-FALCON15-ACK-1"
    assert decision["decision"] == "LIVE_POSITION_RECOGNIZED_RECONCILIATION_REQUIRED"
    assert decision["management_allowed"] is False
    assert signal["live_order"] is broker_result
    assert signal["live_order_id"] == "ENTRY-ACK-DEGRADED-1"
    assert signal["live_client_order_id"] == "FALCON-LIVE-FALCON15-ACK-1"
    assert signal["lifecycle_id"] == "CENTRAL-FALCON-LIFECYCLE:ACK-DEGRADED-1"
    assert signal["initial_qty"] == 0.13
    assert signal["remaining_qty"] == 0.13
    assert signal["broker_stop_order_id"] == "STOP-ACK-DEGRADED-1"
    assert signal["disaster_stop_operationally_armed"] is True
    assert signal["reconciliation_required"] is True
    assert signal["live_management_reconciliation_pending"] is True

    registry = _RegistryProbe()
    initial_register = _function(
        "register_falcon_trade_registry_open",
        {
            "central_trade_registry": registry,
            "normalize_symbol_for_central": lambda value: value,
            "TRADE_REGISTRY_IMPORT_ERROR": None,
            "HEALTH": health,
            "TIMEFRAME": "15m",
            "FALCON_MODE": "LIVE",
            "data_hora_sp_str": lambda: "21/07/2026 12:00:00",
        },
        definition_index=0,
    )
    register = _function(
        "register_falcon_trade_registry_open",
        {
            "_ORIGINAL_REGISTER_FALCON_TRADE_REGISTRY_OPEN_BEFORE_RPM_V1": initial_register,
            "falcon_is_live_real_position": lambda _pos: True,
            "central_trade_registry": registry,
            "falcon_real_remaining_qty": lambda pos: pos["remaining_qty"],
            "FALCON_REAL_POSITION_MANAGEMENT_HARDENING_VERSION": "TEST",
            "HEALTH": health,
        },
    )

    memory_writes = []
    persist = _function(
        "falcon_persist_accepted_signal",
        {
            "register_falcon_trade_registry_open": register,
            "save_positions": lambda positions: memory_writes.append(
                dict(positions)
            )
            or True,
            "HEALTH": health,
        },
    )
    positions = {}

    first_sync = persist(signal, positions)
    second_sync = persist(signal, positions)

    assert first_sync["ok"] is True
    assert first_sync["status"] == "FALCON_ACCEPTED_SIGNAL_SYNCHRONIZED"
    assert second_sync["status"] == "FALCON_ACCEPTED_SIGNAL_ALREADY_SYNCHRONIZED"
    assert second_sync["idempotent"] is True
    assert len(registry.opens) == 1
    assert len(registry.updates) == 0
    assert len(memory_writes) == 1
    assert memory_writes[0][signal["id"]]["live_order_id"] == "ENTRY-ACK-DEGRADED-1"
    open_metadata = registry.opens[0]["metadata"]
    open_payload = registry.opens[0]
    assert open_metadata["reconciliation_required"] is True
    assert open_metadata["entry_acknowledged"] is True
    assert open_payload["reconciliation_required"] is True
    assert open_payload["lifecycle_id"] == signal["lifecycle_id"]
    assert open_payload["broker_order_id"] == "ENTRY-ACK-DEGRADED-1"
    assert open_payload["client_order_id"] == "FALCON-LIVE-FALCON15-ACK-1"
    assert open_metadata["broker_stop_order_id"] == "STOP-ACK-DEGRADED-1"
    assert open_metadata["disaster_stop_operationally_armed"] is True


def test_registry_open_projects_stop_evidence_in_single_official_write():
    registry = _RegistryProbe()
    health = {}
    project = _function(
        "register_falcon_trade_registry_open",
        {
            "central_trade_registry": registry,
            "normalize_symbol_for_central": lambda value: value,
            "TRADE_REGISTRY_IMPORT_ERROR": None,
            "HEALTH": health,
            "TIMEFRAME": "15m",
            "FALCON_MODE": "LIVE",
            "data_hora_sp_str": lambda: "14/07/2026 11:00:22",
        },
        definition_index=0,
    )
    position = {
        "id": "FALCON15:SOLUSDT:SHORT",
        "symbol": "SOLUSDT",
        "side": "SHORT",
        "setup": "FALCON15",
        "entry": 76.93,
        "stop": 77.5585142857143,
        "tp50": 76.30,
        "execution_mode": "LIVE",
        "registry_mode": "REAL",
        "reconciliation_required": True,
        "entry_acknowledged": True,
        "live_order": {"sent": True},
        "live_order_id": "2077030442691940352",
        "live_client_order_id": "FALCON-LIVE-FALCON15-1784037618",
        "lifecycle_id": "CENTRAL-FALCON-LIFECYCLE:FALCON-LIVE-FALCON15-1784037618",
        "broker_entry_reference": 76.93,
        "broker_ack_at": "14/07/2026 11:00:22",
        "broker_stop_order_id": "2077030444402577408",
        "broker_stop_client_order_id": "FDS1-0123456789ABCDEF01234567",
        "disaster_stop_client_order_id": "FDS1-0123456789ABCDEF01234567",
        "disaster_stop_client_order_id_unique": True,
        "client_order_id_reservation_status": "CLIENT_ORDER_ID_RESERVED",
        "falcon_client_order_id_generator_version": "TEST-CID-V1",
        "broker_stop_price": 77.5585142857143,
        "broker_stop_amount": 0.12,
        "broker_stop_status": "DISASTER_STOP_CREATED",
        "broker_stop_side": "buy",
        "broker_stop_symbol": "SOL/USDT:USDT",
        "broker_stop_confirmed_at": "14/07/2026 11:00:22",
        "disaster_stop_confirmed": True,
        "initial_qty": 0.12,
        "remaining_qty": 0.12,
    }

    result = project(position)

    assert result["ok"] is True
    assert len(registry.opens) == 1
    assert len(registry.updates) == 0
    opened = registry.opens[0]
    metadata = opened["metadata"]
    assert metadata["execution_sent"] is True
    assert opened["lifecycle_id"] == "CENTRAL-FALCON-LIFECYCLE:FALCON-LIVE-FALCON15-1784037618"
    assert opened["broker_order_id"] == "2077030442691940352"
    assert opened["client_order_id"] == "FALCON-LIVE-FALCON15-1784037618"
    assert opened["reconciliation_required"] is True
    assert metadata["broker_entry_reference"] == 76.93
    assert metadata["broker_ack_at"] == "14/07/2026 11:00:22"
    assert metadata["broker_stop_status"] == "DISASTER_STOP_CREATED"
    assert metadata["broker_stop_client_order_id"] == "FDS1-0123456789ABCDEF01234567"
    assert metadata["disaster_stop_client_order_id"] == "FDS1-0123456789ABCDEF01234567"
    assert metadata["disaster_stop_client_order_id_unique"] is True
    assert metadata["broker_stop_side"] == "buy"
    assert metadata["broker_stop_symbol"] == "SOL/USDT:USDT"
    assert metadata["broker_stop_confirmed_at"] == "14/07/2026 11:00:22"
    assert metadata["disaster_stop_confirmed"] is True


def test_initial_registry_open_persists_explicit_lifecycle_before_first_shadow_hook():
    registry = _RegistryProbe()
    project = _function(
        "register_falcon_trade_registry_open",
        {
            "central_trade_registry": registry,
            "normalize_symbol_for_central": lambda value: value,
            "TRADE_REGISTRY_IMPORT_ERROR": None,
            "HEALTH": {},
            "TIMEFRAME": "15m",
            "FALCON_MODE": "LIVE",
            "data_hora_sp_str": lambda: "14/07/2026 11:00:22",
        },
        definition_index=0,
    )
    position = {
        "id": "POS-1",
        "symbol": "SOLUSDT",
        "side": "SHORT",
        "setup": "FALCON15",
        "entry": 76.912,
        "stop": 77.5585,
        "tp50": 76.2655,
        "qty": 0.12,
        "execution_mode": "LIVE",
        "execution_decision": {"allowed": True, "decision": "ALLOW", "mode": "LIVE"},
        "lifecycle_id": "CENTRAL-FALCON-LIFECYCLE:FALCON-LIVE-FALCON15-1784037618",
    }

    result = project(position)

    assert result["ok"] is True
    assert registry.opens[0]["lifecycle_id"] == position["lifecycle_id"]
    assert registry.opens[0]["metadata"]["lifecycle_id"] == position["lifecycle_id"]


def test_management_projection_preserves_tp50_and_replacement_facts_without_broker_call():
    registry = _RegistryProbe()
    project = _function(
        "falcon_update_registry_management",
        {
            "central_trade_registry": registry,
            "safe_float": _safe_float,
            "normalize_symbol_for_central": lambda value: value,
            "falcon_real_remaining_qty": lambda _pos: 0.06,
            "FALCON_REAL_POSITION_MANAGEMENT_HARDENING_VERSION": "TEST",
            "HEALTH": {},
        },
    )
    position = {
        "trade_registry_id": "FALCON:FALCON15:SOLUSDT:SHORT",
        "initial_qty": 0.12,
        "remaining_qty": 0.06,
        "runner_qty": 0.06,
        "stop": 76.912,
        "broker_stop_order_id": "STOP-RUNNER-1",
        "broker_stop_client_order_id": "FBE1-0123456789ABCDEF01234567",
        "disaster_stop_client_order_id": "FBE1-0123456789ABCDEF01234567",
        "disaster_stop_client_order_id_unique": True,
        "client_order_id_reservation_status": "CLIENT_ORDER_ID_RESERVED",
        "falcon_client_order_id_generator_version": "TEST-CID-V1",
        "broker_stop_price": 76.912,
        "broker_stop_amount": 0.06,
        "broker_stop_status": "STOP_REPLACED_CANCEL_CREATE",
        "broker_stop_side": "buy",
        "broker_stop_symbol": "SOL/USDT:USDT",
        "broker_stop_confirmed_at": "14/07/2026 11:30:00",
        "disaster_stop_confirmed": True,
        "tp50_real_executed": True,
        "tp50_real_order_id": "TP50-ORDER-1",
        "tp50_amount": 0.06,
        "tp50_fill_price": 75.50,
    }

    result = project(position, tp50_status="REAL_EXECUTED")

    assert result["ok"] is True
    metadata = registry.updates[0][1]["metadata"]
    assert metadata["remaining_qty"] == 0.06
    assert metadata["tp50_real_order_id"] == "TP50-ORDER-1"
    assert metadata["tp50_amount"] == 0.06
    assert metadata["tp50_fill_price"] == 75.50
    assert metadata["broker_stop_order_id"] == "STOP-RUNNER-1"
    assert metadata["broker_stop_client_order_id"] == "FBE1-0123456789ABCDEF01234567"
    assert metadata["disaster_stop_client_order_id_unique"] is True
    assert metadata["disaster_stop_confirmed"] is True


def test_failed_stop_update_is_projected_after_broker_result_without_changing_result():
    registry = _RegistryProbe()
    project = _function(
        "falcon_apply_live_stop_update",
        {
            "falcon_real_remaining_qty": lambda _pos: 0.12,
            "FALCON_MANAGEMENT_AMOUNT_TOLERANCE": 1e-9,
            "_falcon_resize_runner_stop": lambda *_args: {
                "ok": False,
                "status": "STOP_REPLACE_CRITICAL_UNPROTECTED",
            },
            "falcon_update_registry_management": lambda pos, **metadata: registry.update_trade(
                pos["trade_registry_id"], metadata=metadata
            ),
            "HEALTH": {},
            "data_hora_sp_str": lambda: "14/07/2026 12:31:59",
        },
    )
    position = {
        "trade_registry_id": "FALCON:FALCON15:SOLUSDT:SHORT",
        "symbol": "SOLUSDT",
        "side": "SHORT",
        "broker_stop_order_id": "OLD-STOP-1",
        "broker_stop_price": 77.5585,
        "broker_stop_amount": 0.12,
        "broker_stop_status": "ACTIVE",
        "broker_stop_confirmed_at": "14/07/2026 11:00:22",
        "disaster_stop_confirmed": True,
    }
    before = dict(position)

    result = project(position, 77.0, "TRAILING")

    assert result["ok"] is False
    assert result["status"] == "STOP_REPLACE_CRITICAL_UNPROTECTED"
    metadata = registry.updates[0][1]["metadata"]
    assert metadata["stop_update_failed"] is True
    assert metadata["stop_update_reason"] == "TRAILING"
    assert metadata["stop_update"]["status"] == "STOP_REPLACE_CRITICAL_UNPROTECTED"
    assert metadata["stop_update_confirmed"] is False
    assert metadata["stop_update_confirmed_at"] == "14/07/2026 12:31:59"
    assert metadata["stop_update_final_protection_confirmed"] is False
    assert metadata["broker_stop_order_id"] is None
    assert metadata["broker_stop_price"] is None
    assert metadata["broker_stop_amount"] is None
    assert metadata["broker_stop_status"] == "STOP_REPLACE_CRITICAL_UNPROTECTED"
    assert metadata["disaster_stop_confirmed"] is False
    assert position == before


def test_close_projection_preserves_tp50_without_republishing_stale_stop_facts():
    registry = _RegistryProbe()
    project = _function(
        "close_falcon_trade_registry",
        {
            "central_trade_registry": registry,
            "normalize_symbol_for_central": lambda value: value,
            "HEALTH": {},
            "data_hora_sp_str": lambda: "14/07/2026 12:32:04",
        },
    )
    position = {
        "trade_registry_id": "FALCON:FALCON15:SOLUSDT:SHORT",
        "id": "POS-1",
        "symbol": "SOLUSDT",
        "setup": "FALCON15",
        "side": "SHORT",
        "initial_qty": 0.12,
        "remaining_qty": 0.0,
        "tp50_real_executed": True,
        "tp50_real_order_id": "TP50-1",
        "tp50_amount": 0.12,
        "tp50_fill_price": 77.621,
        "tp50_real_execution": {
            "status": "TP50_REAL_EXECUTED_RUNNER_FAILSAFE_CLOSED",
            "stop_resize": {
                "ok": False,
                "status": "STOP_REPLACE_CRITICAL_UNPROTECTED",
                "rollback": {"ok": False},
            },
        },
    }

    result = project(
        position,
        exit_price=77.621,
        result_pct=-0.9218,
        result_r=-1.0966,
        reason="TP50_FAILSAFE_FULL_CLOSE",
    )

    assert result["ok"] is True
    metadata = registry.updates[0][1]["metadata"]
    assert metadata["tp50_real_order_id"] == "TP50-1"
    assert metadata["tp50_amount"] == 0.12
    assert "broker_stop_order_id" not in metadata
    assert "broker_stop_price" not in metadata
    assert "broker_stop_amount" not in metadata
    assert "broker_stop_status" not in metadata
    assert "disaster_stop_confirmed" not in metadata
    assert "stop_update_failed" not in metadata


def test_failed_stop_replacement_projects_confirmed_rollback_as_latest_protection():
    registry = _RegistryProbe()
    project = _function(
        "falcon_apply_live_stop_update",
        {
            "falcon_real_remaining_qty": lambda _pos: 0.12,
            "FALCON_MANAGEMENT_AMOUNT_TOLERANCE": 1e-9,
            "_falcon_resize_runner_stop": lambda *_args: {
                "ok": False,
                "status": "STOP_REPLACE_FAILED_ROLLED_BACK",
                "rollback": {
                    "ok": True,
                    "order_id": "ROLLBACK-STOP-2",
                    "stop_price": 77.5585,
                    "amount": 0.12,
                },
            },
            "falcon_update_registry_management": lambda pos, **metadata: registry.update_trade(
                pos["trade_registry_id"], metadata=metadata
            ),
            "HEALTH": {},
            "data_hora_sp_str": lambda: "14/07/2026 12:31:59",
        },
    )
    position = {
        "trade_registry_id": "FALCON:FALCON15:SOLUSDT:SHORT",
        "symbol": "SOLUSDT",
        "side": "SHORT",
        "broker_stop_order_id": "OLD-STOP-1",
    }
    before = dict(position)

    result = project(position, 77.0, "TRAILING")

    assert result["ok"] is False
    metadata = registry.updates[0][1]["metadata"]
    assert metadata["stop_update_failed"] is True
    assert metadata["stop_update_recovered"] is True
    assert metadata["stop_update_confirmed"] is False
    assert metadata["stop_update_confirmed_at"] == "14/07/2026 12:31:59"
    assert metadata["stop_update_final_protection_confirmed"] is True
    assert metadata["broker_stop_order_id"] == "ROLLBACK-STOP-2"
    assert metadata["broker_stop_status"] == "ROLLBACK_PROTECTED"
    assert metadata["disaster_stop_confirmed"] is True
    assert position == before


def test_successful_stop_replacement_refreshes_factual_confirmation_timestamp():
    registry = _RegistryProbe()
    project = _function(
        "falcon_apply_live_stop_update",
        {
            "falcon_real_remaining_qty": lambda _pos: 0.12,
            "FALCON_MANAGEMENT_AMOUNT_TOLERANCE": 1e-9,
            "_falcon_resize_runner_stop": lambda *_args: {
                "ok": True,
                "status": "STOP_REPLACED_EDIT",
                "new_order_id": "NEW-STOP-2",
            },
            "falcon_update_registry_management": lambda pos, **metadata: registry.update_trade(
                pos["trade_registry_id"], metadata={**pos, **metadata}
            ),
            "HEALTH": {},
            "data_hora_sp_str": lambda: "14/07/2026 12:45:00",
        },
    )
    position = {
        "trade_registry_id": "FALCON:FALCON15:SOLUSDT:SHORT",
        "symbol": "SOLUSDT",
        "side": "SHORT",
        "broker_stop_order_id": "OLD-STOP-1",
        "broker_stop_confirmed_at": "14/07/2026 11:00:22",
    }

    result = project(position, 77.0, "TRAILING")

    assert result["ok"] is True
    assert position["broker_stop_order_id"] == "NEW-STOP-2"
    assert position["broker_stop_confirmed_at"] == "14/07/2026 12:45:00"
    metadata = registry.updates[0][1]["metadata"]
    assert metadata["stop_update_failed"] is False
    assert metadata["stop_update_recovered"] is False
    assert metadata["stop_update_confirmed"] is True
    assert metadata["stop_update_confirmed_at"] == "14/07/2026 12:45:00"
    assert metadata["stop_update_final_protection_confirmed"] is True
    assert metadata["disaster_stop_confirmed"] is True


def test_tp50_stop_resize_success_clears_stale_failure_flags():
    registry = _RegistryProbe()
    project = _function(
        "_falcon_finalize_tp50_after_partial",
        {
            "_falcon_resize_runner_stop": lambda *_args: {
                "ok": True,
                "status": "STOP_REPLACED_CANCEL_CREATE",
                "new_order_id": "RUNNER-STOP-2",
            },
            "falcon_update_registry_management": lambda pos, **metadata: registry.update_trade(
                pos["trade_registry_id"], metadata=metadata
            ),
            "safe_float": _safe_float,
            "data_hora_sp_str": lambda: "14/07/2026 11:30:00",
            "FALCON_MANAGEMENT_AMOUNT_TOLERANCE": 1e-9,
            "FALCON_TP50_REAL_EXECUTION_AUDIT_VERSION": "TEST",
            "FALCON_MANAGEMENT_FAILSAFE_ENABLED": False,
        },
    )
    position = {
        "trade_registry_id": "FALCON:FALCON15:SOLUSDT:SHORT",
        "stop": 76.912,
        "broker_stop_order_id": "OLD-STOP-1",
    }

    result = project(
        position,
        0.06,
        75.50,
        {"order_id": "TP50-1", "filled_amount": 0.06, "average": 75.50},
    )

    assert result["ok"] is True
    metadata = registry.updates[0][1]["metadata"]
    assert metadata["stop_update_failed"] is False
    assert metadata["stop_update_confirmed"] is True
    assert metadata["stop_update_final_protection_confirmed"] is True
    assert metadata["stop_update_confirmed_at"] == "14/07/2026 11:30:00"


def test_tp50_unprotected_resize_failure_is_projected_before_failsafe():
    registry = _RegistryProbe()
    project = _function(
        "_falcon_finalize_tp50_after_partial",
        {
            "_falcon_resize_runner_stop": lambda *_args: {
                "ok": False,
                "status": "STOP_REPLACE_CRITICAL_UNPROTECTED",
                "rollback": {"ok": False},
            },
            "falcon_update_registry_management": lambda pos, **metadata: registry.update_trade(
                pos["trade_registry_id"], metadata=metadata
            ),
            "safe_float": _safe_float,
            "data_hora_sp_str": lambda: "14/07/2026 11:30:01",
            "FALCON_MANAGEMENT_AMOUNT_TOLERANCE": 1e-9,
            "FALCON_TP50_REAL_EXECUTION_AUDIT_VERSION": "TEST",
            "FALCON_MANAGEMENT_FAILSAFE_ENABLED": False,
        },
    )
    position = {
        "trade_registry_id": "FALCON:FALCON15:SOLUSDT:SHORT",
        "stop": 76.912,
        "broker_stop_order_id": "OLD-STOP-1",
        "disaster_stop_confirmed": True,
    }
    before_stop = position["broker_stop_order_id"]

    result = project(
        position,
        0.06,
        75.50,
        {"order_id": "TP50-1", "filled_amount": 0.06, "average": 75.50},
    )

    assert result["ok"] is False
    metadata = registry.updates[0][1]["metadata"]
    assert metadata["stop_update_failed"] is True
    assert metadata["stop_update_final_protection_confirmed"] is False
    assert metadata["broker_stop_order_id"] is None
    assert metadata["disaster_stop_confirmed"] is False
    assert position["broker_stop_order_id"] == before_stop
