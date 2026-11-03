from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "execution_engine.py"
MAIN_SOURCE = ROOT / "main.py"


def _load_redactor():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_execution_engine_public_broker_status"
    )
    module = ast.Module(body=[function], type_ignores=[])
    namespace = {}
    exec(compile(ast.fix_missing_locations(module), str(SOURCE), "exec"), namespace)
    return namespace["_execution_engine_public_broker_status"]


def test_public_broker_health_drops_masked_api_key_without_mutating_source():
    status = {
        "api_key_masked": "SYNTHETIC-PARTIAL-KEY",
        "api_key_configured": True,
        "api_secret_configured": True,
        "execution_mode": "PAPER",
        "broker_dry_run": True,
    }

    public_status = _load_redactor()(status)

    assert "api_key_masked" not in public_status
    assert "SYNTHETIC-PARTIAL-KEY" not in repr(public_status)
    assert public_status["api_key_configured"] is True
    assert public_status["api_secret_configured"] is True
    assert public_status["execution_mode"] == "PAPER"
    assert public_status["broker_dry_run"] is True
    assert status["api_key_masked"] == "SYNTHETIC-PARTIAL-KEY"


def test_public_broker_health_preserves_non_dict_error_state():
    redactor = _load_redactor()
    assert redactor(None) is None
    assert redactor("unavailable") == "unavailable"


def test_execution_engine_health_redacts_broker_status_before_returning():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "execution_engine_health"
    )
    module = ast.Module(body=[function], type_ignores=[])
    namespace = {
        "execution_health": lambda: {"ok": True},
        "_now_br": lambda: "synthetic-time",
        "central_broker": SimpleNamespace(
            status_payload=lambda *, check_ready: {
                "api_key_masked": "SYNTHETIC-PARTIAL-KEY",
                "execution_mode": "PAPER",
                "broker_dry_run": True,
            }
        ),
        "_execution_engine_public_broker_status": _load_redactor(),
        "orchestrate_execution": lambda: None,
        "VERSION": "synthetic-version",
        "DEFAULT_ENGINE_MODE": "OBSERVATION_ONLY",
        "REAL_EXECUTION_ENABLED": False,
        "PAPER_EXECUTION_ENABLED": True,
        "REAL_PILOT_ENABLED": False,
        "REAL_PILOT_ALLOWED_BOTS": set(),
        "REAL_PILOT_ALLOWED_SYMBOLS": set(),
        "REAL_PILOT_MAX_MARGIN_USDT": 0,
        "REAL_PILOT_MAX_LEVERAGE": 0,
        "REAL_PILOT_MAX_NOTIONAL_USDT": 0,
        "REAL_PILOT_MAX_RISK_PCT": 0,
        "REAL_PILOT_MAX_OPEN_POSITIONS": 0,
        "REAL_PILOT_REQUIRE_READY": True,
        "REAL_PILOT_REQUIRE_ENTRY": True,
        "REAL_PILOT_REQUIRE_STOP": True,
        "EXECUTION_AUTH_TOKEN_ENABLED": False,
        "EXECUTION_AUTH_TOKEN_TTL_SECONDS": 1,
        "EXECUTION_CONFIRMATION_GUARD_ENABLED": True,
        "EXECUTION_CONFIRMATION_REQUIRE_TOKEN": True,
        "EXECUTION_CONFIRMATION_BLOCK_DUPLICATE_WINDOW_SECONDS": 1,
        "EXECUTION_CONFIRMATION_MIN_FREE_BALANCE_BUFFER_USDT": 0,
        "ORCHESTRATOR_IMPORT_ERROR": None,
        "execute_paper_from_engine": None,
        "PAPER_EXECUTOR_IMPORT_ERROR": None,
        "paper_integrated_health": None,
        "BROKER_IMPORT_ERROR": None,
        "EXECUTION_ENGINE_LOG_FILE": "synthetic-engine-log",
        "EXECUTION_AUDIT_LOG_FILE": "synthetic-audit-log",
    }
    exec(compile(ast.fix_missing_locations(module), str(SOURCE), "exec"), namespace)

    result = namespace["execution_engine_health"]()

    assert result["broker"]["execution_mode"] == "PAPER"
    assert result["broker"]["broker_dry_run"] is True
    assert "api_key_masked" not in result["broker"]
    assert "SYNTHETIC-PARTIAL-KEY" not in repr(result)


def _load_public_broker_payload_functions(
    status_payload, ready_check, broker_import_error=None
):
    tree = ast.parse(MAIN_SOURCE.read_text(encoding="utf-8"), filename=str(MAIN_SOURCE))
    wanted = {
        "_sanitize_public_broker_payload",
        "broker_status_payload",
        "bingx_ready_payload",
    }
    nodes = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in wanted
    ]
    assert {node.name for node in nodes} == wanted
    module = ast.Module(body=nodes, type_ignores=[])
    namespace = {
        "EXECUTION_MODE": "PAPER",
        "ENABLE_REAL_TRADING": False,
        "REAL_TRADING_ALLOWED_BOTS": set(),
        "REAL_TRADING_ALLOWED_SYMBOLS": set(),
        "REAL_TRADING_MAX_RISK_PCT": 0,
        "DEFAULT_REAL_MARGIN_USDT": 0,
        "DEFAULT_REAL_LEVERAGE": 0,
        "REAL_TRADING_MAX_MARGIN_USDT": 0,
        "REAL_TRADING_MAX_NOTIONAL_USDT": 0,
        "all_real_execution_configs": lambda: {},
        "BROKER_IMPORT_ERROR": broker_import_error,
        "central_broker": SimpleNamespace(
            status_payload=status_payload,
            ready_check=ready_check,
        ),
    }
    exec(compile(ast.fix_missing_locations(module), str(MAIN_SOURCE), "exec"), namespace)
    return namespace


def test_public_main_broker_payloads_remove_nested_credential_fragments():
    key_fragment = "SYNTHETIC-PARTIAL-KEY"
    secret_fragment = "SYNTHETIC-PARTIAL-SECRET"
    signature_fragment = "SYNTHETIC-PARTIAL-SIGNATURE"
    status_source = {
        "api_key_masked": key_fragment,
        "api_key_configured": True,
        "nested": {"api_secret_masked": secret_fragment},
    }
    ready_source = {
        "ok": True,
        "balance": 0,
        "signature_masked": signature_fragment,
        "headers": {"X-BX-APIKEY": key_fragment},
    }
    namespace = _load_public_broker_payload_functions(
        status_payload=lambda *, check_ready: status_source,
        ready_check=lambda: ready_source,
    )

    status = namespace["broker_status_payload"]()
    ready = namespace["bingx_ready_payload"]()

    assert status["broker"]["api_key_configured"] is True
    assert "api_key_masked" not in status["broker"]
    assert "api_secret_masked" not in status["broker"]["nested"]
    assert "signature_masked" not in ready
    assert "X-BX-APIKEY" not in ready["headers"]
    assert all(
        fragment not in repr((status, ready))
        for fragment in (key_fragment, secret_fragment, signature_fragment)
    )
    assert status_source["api_key_masked"] == key_fragment
    assert ready_source["signature_masked"] == signature_fragment


def test_public_main_broker_payloads_do_not_return_exception_or_import_text():
    secret_canary = "SYNTHETIC-SECRET-CANARY"

    def raise_status(*, check_ready):
        raise RuntimeError(f"transport failed while using {secret_canary}")

    def raise_ready():
        raise ValueError(f"bad response included {secret_canary}")

    namespace = _load_public_broker_payload_functions(
        status_payload=raise_status,
        ready_check=raise_ready,
        broker_import_error=f"ImportError: path contained {secret_canary}",
    )

    status = namespace["broker_status_payload"]()
    ready = namespace["bingx_ready_payload"]()

    assert status["broker_import_error"] == "BROKER_IMPORT_ERROR"
    assert status["broker"] == {
        "ok": False,
        "error": "BROKER_STATUS_ERROR",
        "error_type": "RuntimeError",
    }
    assert ready == {
        "ok": False,
        "status": "READY_ERROR",
        "error_type": "ValueError",
    }
    assert secret_canary not in repr((status, ready))
