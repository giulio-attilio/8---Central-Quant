from __future__ import annotations

import ast
import importlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]

AUTOMATIC_ENTRY_POINTS = (
    ("bots/falcon.py", "maybe_send_daily_summary"),
    ("bots/turtle.py", "maybe_send_daily_summary"),
    ("bots/predator.py", "enviar_resumo_diario_se_preciso"),
    ("bots/donkey.py", "enviar_resumo_diario_se_preciso"),
    ("bots/meme.py", "enviar_resumo_diario_se_preciso"),
    ("bots/cobra.py", "enviar_resumo_diario_se_preciso"),
)


def _fresh_contract(monkeypatch, **environment):
    for name in (
        "CENTRAL_AUTO_DAILY_SUMMARIES_ENABLED",
        "CENTRAL_AUTO_CEO_DAILY_ENABLED",
    ):
        monkeypatch.delenv(name, raising=False)
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    sys.modules.pop("automatic_daily_summaries", None)
    return importlib.import_module("automatic_daily_summaries")


def _function_node(relative_path: str, function_name: str) -> ast.FunctionDef:
    source = (ROOT / relative_path).read_text(encoding="utf-8")
    tree = ast.parse(source)
    return next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == function_name
    )


def _run_isolated_function(node: ast.FunctionDef, namespace: dict):
    isolated = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(isolated)
    exec(compile(isolated, "<isolated-summary-entry-point>", "exec"), namespace)
    return namespace[node.name]()


def test_automatic_daily_summaries_are_disabled_when_env_is_absent(monkeypatch):
    contract = _fresh_contract(monkeypatch)

    assert contract.CENTRAL_AUTO_DAILY_SUMMARIES_ENABLED is False
    assert contract.CENTRAL_AUTO_CEO_DAILY_ENABLED is False
    assert contract.central_daily_report_automatic_enabled("daily") is False
    assert contract.central_daily_report_automatic_enabled("executivo") is False


def test_ceo_daily_is_disabled_when_env_is_absent(monkeypatch):
    contract = _fresh_contract(monkeypatch)
    assert contract.CENTRAL_AUTO_CEO_DAILY_ENABLED is False


def test_mode_sets_match_the_explicit_central_contract(monkeypatch):
    contract = _fresh_contract(monkeypatch)
    assert contract.CENTRAL_STANDARD_DAILY_MODES == frozenset(
        {
            "completo",
            "full",
            "audit",
            "auditoria",
            "daily",
            "diario",
            "diário",
            "legacy",
            "dashboard",
            "painel",
        }
    )
    assert contract.CENTRAL_CEO_DAILY_MODES == frozenset(
        {"executivo", "executive", "ceo", "ceo_daily", "ceodaily", "light", "leve"}
    )

    main_source = (ROOT / "main.py").read_text(encoding="utf-8")
    assert 'os.environ.get("CENTRAL_DAILY_REPORT_MODE", "executivo").strip().lower()' in main_source


@pytest.mark.parametrize("value", ["true", "1", "yes", "sim", "on", "TRUE", " Sim "])
def test_only_explicit_true_values_enable_automatic_daily_summaries(monkeypatch, value):
    contract = _fresh_contract(
        monkeypatch,
        CENTRAL_AUTO_DAILY_SUMMARIES_ENABLED=value,
    )
    assert contract.CENTRAL_AUTO_DAILY_SUMMARIES_ENABLED is True


@pytest.mark.parametrize("value", ["", "false", "0", "no", "nao", "off", "enabled"])
def test_other_values_keep_automatic_daily_summaries_disabled(monkeypatch, value):
    contract = _fresh_contract(
        monkeypatch,
        CENTRAL_AUTO_DAILY_SUMMARIES_ENABLED=value,
    )
    assert contract.CENTRAL_AUTO_DAILY_SUMMARIES_ENABLED is False


@pytest.mark.parametrize(
    "mode",
    [
        "completo",
        "full",
        "audit",
        "auditoria",
        "daily",
        "diario",
        "diário",
        "legacy",
        "dashboard",
        "painel",
    ],
)
def test_standard_daily_modes_only_require_global_flag(monkeypatch, mode):
    contract = _fresh_contract(
        monkeypatch,
        CENTRAL_AUTO_DAILY_SUMMARIES_ENABLED="true",
        CENTRAL_AUTO_CEO_DAILY_ENABLED="false",
    )
    assert contract.central_daily_report_automatic_enabled(mode) is True


@pytest.mark.parametrize(
    "mode",
    ["executivo", "executive", "ceo", "ceo_daily", "ceodaily", "light", "leve"],
)
def test_ceo_daily_modes_require_independent_ceo_flag(monkeypatch, mode):
    contract = _fresh_contract(
        monkeypatch,
        CENTRAL_AUTO_DAILY_SUMMARIES_ENABLED="true",
        CENTRAL_AUTO_CEO_DAILY_ENABLED="false",
    )
    assert contract.central_daily_report_automatic_enabled(mode) is False


@pytest.mark.parametrize(
    "mode",
    ["executivo", "executive", "ceo", "ceo_daily", "ceodaily", "light", "leve"],
)
def test_ceo_daily_modes_only_require_independent_ceo_flag(monkeypatch, mode):
    contract = _fresh_contract(
        monkeypatch,
        CENTRAL_AUTO_DAILY_SUMMARIES_ENABLED="false",
        CENTRAL_AUTO_CEO_DAILY_ENABLED="true",
    )
    assert contract.central_daily_report_automatic_enabled(mode) is True
    assert contract.central_daily_report_policy_reason(mode) == "CENTRAL_CEO_DAILY_POLICY"


@pytest.mark.parametrize("mode", ["unknown", "executivoo", "ceo-daily", None, "", "   "])
def test_unknown_missing_and_typo_modes_fail_closed(monkeypatch, mode):
    contract = _fresh_contract(
        monkeypatch,
        CENTRAL_AUTO_DAILY_SUMMARIES_ENABLED="true",
        CENTRAL_AUTO_CEO_DAILY_ENABLED="true",
    )
    assert contract.central_daily_report_automatic_enabled(mode) is False


@pytest.mark.parametrize("mode", ["daily", "executivo", "unknown", None, ""])
def test_legacy_daily_disabled_blocks_every_mode(monkeypatch, mode):
    contract = _fresh_contract(
        monkeypatch,
        CENTRAL_AUTO_DAILY_SUMMARIES_ENABLED="true",
        CENTRAL_AUTO_CEO_DAILY_ENABLED="true",
    )
    assert contract.central_daily_report_automatic_enabled(
        mode,
        legacy_daily_enabled=False,
    ) is False


@pytest.mark.parametrize("mode", ["daily", "dashboard", "audit"])
def test_global_flag_disabled_blocks_standard_modes(monkeypatch, mode):
    contract = _fresh_contract(
        monkeypatch,
        CENTRAL_AUTO_DAILY_SUMMARIES_ENABLED="false",
        CENTRAL_AUTO_CEO_DAILY_ENABLED="true",
    )
    assert contract.central_daily_report_automatic_enabled(mode) is False


@pytest.mark.parametrize("relative_path,function_name", AUTOMATIC_ENTRY_POINTS)
def test_disabled_bot_entry_points_return_before_any_heavy_dependency(
    relative_path,
    function_name,
):
    node = _function_node(relative_path, function_name)

    def forbidden(*args, **kwargs):
        raise AssertionError("automatic summary touched a heavy dependency")

    namespace = {
        "CENTRAL_AUTO_DAILY_SUMMARIES_ENABLED": False,
        "agora_sp": forbidden,
        "redis_get_json": forbidden,
        "redis_get_str": forbidden,
        "safe_send_telegram": forbidden,
        "safe_send_telegram_donkey": forbidden,
        "send_telegram": forbidden,
        "montar_resumo": forbidden,
        "montar_resumo_diario": forbidden,
        "montar_resumo_donkey": forbidden,
        "build_summary": forbidden,
        "trades_today": forbidden,
    }

    assert _run_isolated_function(node, namespace) is None


def test_trendpro_and_meme_inline_schedulers_gate_before_summary_state_reads():
    for relative_path in ("bots/trendpro.py", "bots/meme.py"):
        source = (ROOT / relative_path).read_text(encoding="utf-8")
        guarded = (
            "if CENTRAL_AUTO_DAILY_SUMMARIES_ENABLED and agora_brasil.hour == 23 "
            "and agora_brasil.minute >= 55:"
        )
        assert guarded in source
        assert source.index(guarded) < source.index(
            "if not resumo_diario_ja_enviado():",
            source.index(guarded),
        )


def test_central_scheduler_gates_before_snapshot_builders_and_thread_start():
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    attempt_start = source.index("def central_daily_report_run_once")
    loop_start = source.index("def central_daily_report_loop():", attempt_start)
    attempt = source[attempt_start:loop_start]
    assert attempt.index("central_daily_report_automatic_enabled(") < attempt.index(
        'save_daily_snapshot(label="auto")'
    )
    assert 'event_type = "CENTRAL_CEO_DAILY_SUMMARY"' in attempt

    runtime_start = source.index("def start_central_runtime_once():")
    runtime = source[runtime_start:]
    assert runtime.index("if central_daily_automatic_enabled or CENTRAL_MONTHLY_REPORT_ENABLED:") < runtime.index(
        "threading.Thread(target=central_daily_report_loop"
    )
    assert "if CENTRAL_AUTO_DAILY_SUMMARIES_ENABLED and TRENDPRO_DAILY_SUMMARY_ENABLED:" in runtime


def test_manual_summary_surfaces_remain_available_when_automatic_is_disabled(monkeypatch):
    contract = _fresh_contract(monkeypatch)
    health = contract.automatic_daily_summaries_health()
    assert health["daily_summary_manual_commands_available"] is True

    expected_manual_surfaces = {
        "bots/falcon.py": "/resumo",
        "bots/turtle.py": "/resumo",
        "bots/predator.py": "return montar_resumo_diario()",
        "bots/donkey.py": "/resumo",
        "bots/cobra.py": "/resumo",
        "bots/meme.py": "/resumo",
        "bots/trendpro.py": "/resumo",
        "main.py": "def build_daily_report(",
    }
    for relative_path, marker in expected_manual_surfaces.items():
        assert marker in (ROOT / relative_path).read_text(encoding="utf-8")


def test_health_is_lightweight_and_does_not_fabricate_skips(monkeypatch):
    contract = _fresh_contract(monkeypatch)
    health = contract.automatic_daily_summaries_health()

    assert health == {
        "auto_daily_summaries_enabled": False,
        "auto_ceo_daily_enabled": False,
        "daily_summary_manual_commands_available": True,
        "auto_daily_summaries_last_skipped_at": None,
        "auto_daily_summaries_skipped_bots": [],
    }


def test_health_contract_has_no_datetime_dependency_or_fake_skip_state():
    source = (ROOT / "automatic_daily_summaries.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = {
        alias.name
        for node in tree.body
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported_from_modules = {
        node.module
        for node in tree.body
        if isinstance(node, ast.ImportFrom)
    }

    assert "datetime" not in imported_modules
    assert "datetime" not in imported_from_modules
    assert "_DISABLED_AT" not in source


def test_reimports_never_fabricate_skips(monkeypatch):
    first = _fresh_contract(monkeypatch).automatic_daily_summaries_health()
    second = _fresh_contract(monkeypatch).automatic_daily_summaries_health()

    for health in (first, second):
        assert health["auto_daily_summaries_last_skipped_at"] is None
        assert health["auto_daily_summaries_skipped_bots"] == []


def test_main_health_exposes_lightweight_fields_without_building_reports():
    node = _function_node("main.py", "health")
    node.decorator_list = []
    expected = {
        "auto_daily_summaries_enabled": False,
        "auto_ceo_daily_enabled": False,
        "daily_summary_manual_commands_available": True,
        "auto_daily_summaries_last_skipped_at": None,
        "auto_daily_summaries_skipped_bots": [],
    }
    forbidden_calls = []

    def forbidden(name):
        return lambda *args, **kwargs: forbidden_calls.append(name) or pytest.fail(
            f"health attempted forbidden operation: {name}"
        )

    learning = {
        "auto_learning_refresh_enabled": False,
        "auto_learning_refresh_thread_started": False,
        "auto_learning_refresh_manual_available": True,
        "auto_learning_refresh_interval_seconds": 900,
        "auto_learning_refresh_disabled_reason": "DISABLED_BY_POLICY",
    }
    disk = {
        "disk_forensics_available": True,
        "disk_forensics_usage_pct": 50.0,
        "disk_forensics_free_mb": 1024.0,
        "disk_forensics_partial": False,
        "disk_forensics_largest_file": "history_events.jsonl",
        "disk_forensics_largest_file_mb": 295.0,
    }
    timeline = {
        "timeline_emergency_recovery_enabled": False,
        "timeline_emergency_recovery_status": "DISABLED",
    }
    scheduler = {
        "daily_summary_scheduler_enabled": False,
        "daily_summary_next_run_at": None,
        "daily_summary_last_run_at": None,
        "daily_summary_last_error": None,
        "daily_summary_policy_reason": "DISABLED_CEO_DAILY_POLICY",
        "daily_summary_thread_started": False,
        "daily_summary_last_success_at": None,
        "daily_summary_last_status": "NOT_RUN",
    }
    namespace = {
        "central_watchdog_status": lambda: {"ok": True},
        "central_trade_registry_snapshot": lambda include_trades=False: {
            "ok": True,
            "include_trades": include_trades,
        },
        "automatic_daily_summaries_health": lambda: expected.copy(),
        "central_daily_scheduler_health": lambda: scheduler.copy(),
        "automatic_learning_refresh_health": lambda **kwargs: learning.copy(),
        "LEARNING_AUTO_REFRESH_SECONDS": 900,
        "LEARNING_AUTO_REFRESH_MIN_SECONDS": 300,
        "LEARNING_AUTO_REFRESH_THREAD_STARTED": False,
        "LEARNING_AUTO_REFRESH_LEGACY_ENABLED": False,
        "build_disk_forensics_health": lambda cached: disk.copy(),
        "STARTUP_DISK_FORENSICS_RESULT": {"ok": True, "cached": True},
        "build_timeline_emergency_recovery_health": lambda cached: timeline.copy(),
        "TIMELINE_EMERGENCY_RECOVERY_RESULT": {"enabled": False},
        "load_events": forbidden("history_events"),
        "iter_jsonl_tail": forbidden("iter_jsonl_tail"),
        "open": forbidden("filesystem"),
        "redis": forbidden("redis"),
        "socket": forbidden("network"),
    }

    result = _run_isolated_function(node, namespace)

    assert result["ok"] is True
    assert result["trade_registry"]["include_trades"] is False
    for field, value in expected.items():
        assert result[field] == value
    for field, value in {**learning, **disk, **timeline, **scheduler}.items():
        assert result[field] == value
    assert forbidden_calls == []


def _isolated_daily_scheduler(send_result=True):
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    names = {
        "_central_daily_report_scheduled_at",
        "central_daily_scheduler_health",
        "central_daily_report_run_once",
    }
    nodes = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    calls = []
    namespace = {
        "datetime": datetime,
        "timedelta": timedelta,
        "CENTRAL_DAILY_REPORT_MODE": "executivo",
        "CENTRAL_DAILY_REPORT_ENABLED": True,
        "CENTRAL_DAILY_REPORT_TIME": "23:55",
        "CENTRAL_DAILY_REPORT_RETRY_COOLDOWN_SECONDS": 300,
        "CENTRAL_DAILY_REPORT_SENT_DATE": None,
        "CENTRAL_DAILY_REPORT_THREAD_STARTED": True,
        "CENTRAL_DAILY_REPORT_LAST_RUN_AT": None,
        "CENTRAL_DAILY_REPORT_LAST_SUCCESS_AT": None,
        "CENTRAL_DAILY_REPORT_LAST_ERROR": None,
        "CENTRAL_DAILY_REPORT_LAST_STATUS": "NOT_RUN",
        "CENTRAL_DAILY_REPORT_LAST_ATTEMPT_EPOCH": None,
        "CENTRAL_TELEGRAM_BOT_TOKEN": "test-token",
        "CENTRAL_TELEGRAM_CHAT_ID": "test-chat",
        "central_daily_report_automatic_enabled": lambda mode, legacy: True,
        "central_daily_report_policy_reason": lambda mode, legacy: "CENTRAL_CEO_DAILY_POLICY",
        "agora_sp": lambda: datetime(2026, 7, 17, 23, 56, tzinfo=timezone.utc),
        "save_daily_snapshot": lambda **kwargs: calls.append(("snapshot", kwargs)),
        "build_audit_parts": lambda: "audit",
        "build_daily_report": lambda: "daily",
        "build_dashboard_report": lambda: "dashboard",
        "build_ceo_daily_report": lambda: calls.append(("build", "ceo")) or "ceo",
        "central_send_automatic_telegram": lambda *args, **kwargs: (
            calls.append(("send", kwargs))
            or (
                send_result
                if isinstance(send_result, dict)
                else {"allowed": True, "sent": bool(send_result)}
            )
        ),
        "force_gc_if_needed": lambda *args, **kwargs: None,
    }
    isolated = ast.Module(body=nodes, type_ignores=[])
    ast.fix_missing_locations(isolated)
    exec(compile(isolated, "<isolated-central-daily-scheduler>", "exec"), namespace)
    return namespace, calls


def test_scheduler_does_not_mark_sent_when_transport_returns_false():
    namespace, calls = _isolated_daily_scheduler(send_result=False)
    now = datetime(2026, 7, 17, 23, 56, tzinfo=timezone.utc)

    result = namespace["central_daily_report_run_once"](now=now)

    assert result["status"] == "SEND_FAILED"
    assert namespace["CENTRAL_DAILY_REPORT_SENT_DATE"] is None
    assert any(call[0] == "send" for call in calls)


def test_scheduler_marks_sent_only_after_confirmed_delivery():
    namespace, calls = _isolated_daily_scheduler(send_result=True)
    now = datetime(2026, 7, 17, 23, 56, tzinfo=timezone.utc)

    result = namespace["central_daily_report_run_once"](now=now)

    assert result == {"ok": True, "status": "SENT", "sent": True}
    assert namespace["CENTRAL_DAILY_REPORT_SENT_DATE"] == "2026-07-17"
    send_kwargs = next(call[1] for call in calls if call[0] == "send")
    assert send_kwargs["event_type"] == "CENTRAL_CEO_DAILY_SUMMARY"
    assert send_kwargs["mode"] == "PAPER"


def test_policy_block_does_not_mark_scheduler_sent():
    blocked = {"allowed": False, "sent": False, "reason": "LIVE_ONLY_POLICY"}
    namespace, _calls = _isolated_daily_scheduler(send_result=blocked)

    result = namespace["central_daily_report_run_once"](
        now=datetime(2026, 7, 17, 23, 56, tzinfo=timezone.utc)
    )

    assert result["reason"] == "LIVE_ONLY_POLICY"
    assert namespace["CENTRAL_DAILY_REPORT_SENT_DATE"] is None
    assert namespace["CENTRAL_DAILY_REPORT_LAST_ERROR"] == "LIVE_ONLY_POLICY"


def test_missing_telegram_credentials_do_not_mark_scheduler_sent():
    namespace, calls = _isolated_daily_scheduler(send_result=True)
    namespace["CENTRAL_TELEGRAM_BOT_TOKEN"] = None

    result = namespace["central_daily_report_run_once"](
        now=datetime(2026, 7, 17, 23, 56, tzinfo=timezone.utc)
    )

    assert result["status"] == "CREDENTIALS_MISSING"
    assert namespace["CENTRAL_DAILY_REPORT_SENT_DATE"] is None
    assert not any(call[0] == "send" for call in calls)


def test_scheduler_runs_after_configured_minute_but_not_before_it():
    before_namespace, before_calls = _isolated_daily_scheduler(send_result=True)
    before = before_namespace["central_daily_report_run_once"](
        now=datetime(2026, 7, 17, 23, 54, tzinfo=timezone.utc)
    )
    assert before["status"] == "WAITING"
    assert before_calls == []

    after_namespace, _after_calls = _isolated_daily_scheduler(send_result=True)
    after = after_namespace["central_daily_report_run_once"](
        now=datetime(2026, 7, 17, 23, 59, tzinfo=timezone.utc)
    )
    assert after["status"] == "SENT"


def test_scheduler_failed_attempt_uses_retry_cooldown():
    namespace, calls = _isolated_daily_scheduler(send_result=False)
    first = datetime(2026, 7, 17, 23, 56, tzinfo=timezone.utc)
    second = datetime(2026, 7, 17, 23, 57, tzinfo=timezone.utc)

    assert namespace["central_daily_report_run_once"](now=first)["status"] == "SEND_FAILED"
    assert namespace["central_daily_report_run_once"](now=second)["status"] == "RETRY_COOLDOWN"
    assert len([call for call in calls if call[0] == "send"]) == 1


def test_scheduler_health_is_lightweight_and_exposes_next_run():
    namespace, calls = _isolated_daily_scheduler(send_result=True)
    now = datetime(2026, 7, 17, 20, 0, tzinfo=timezone.utc)

    health = namespace["central_daily_scheduler_health"](now=now)

    assert health["daily_summary_scheduler_enabled"] is True
    assert health["daily_summary_next_run_at"].endswith("23:55:00+00:00")
    assert health["daily_summary_policy_reason"] == "CENTRAL_CEO_DAILY_POLICY"
    assert health["daily_summary_thread_started"] is True
    assert calls == []


def test_scanners_and_position_management_are_not_gated_by_daily_summary_flag():
    for relative_path in (
        "bots/predator.py",
        "bots/donkey.py",
        "bots/trendpro.py",
        "bots/meme.py",
        "bots/cobra.py",
    ):
        scanner = _function_node(relative_path, "scanner")
        scanner_source = ast.unparse(scanner)
        assert "while True" in scanner_source
        for condition in (
            node
            for node in ast.walk(scanner)
            if isinstance(node, ast.If)
            and "CENTRAL_AUTO_DAILY_SUMMARIES_ENABLED" in ast.unparse(node.test)
        ):
            assert not any(
                isinstance(child, (ast.Return, ast.Break, ast.Continue))
                for statement in condition.body
                for child in ast.walk(statement)
            )

    for relative_path in ("bots/falcon.py", "bots/turtle.py"):
        scanner = _function_node(relative_path, "scanner_loop")
        assert "CENTRAL_AUTO_DAILY_SUMMARIES_ENABLED" not in ast.unparse(scanner)


def test_watchdogs_tp50_trailing_and_stops_remain_outside_summary_gate():
    management_functions = {
        "bots/predator.py": "gerenciar_posicoes",
        "bots/donkey.py": "gerenciar_posicoes",
        "bots/trendpro.py": "gerenciar_posicoes",
        "bots/meme.py": "gerenciar_posicoes",
        "bots/cobra.py": "gerenciar_posicoes",
        "bots/falcon.py": "scanner_loop",
        "bots/turtle.py": "scanner_loop",
    }
    watchdog_functions = {
        "bots/predator.py": "watchdog_loop",
        "bots/donkey.py": "watchdog_loop",
        "bots/trendpro.py": "watchdog_loop",
        "bots/meme.py": "watchdog_loop",
        "bots/cobra.py": "watchdog",
        "bots/falcon.py": "watchdog_loop",
        "bots/turtle.py": "watchdog_loop",
    }

    operational_source = ""
    for relative_path, function_name in management_functions.items():
        source = (ROOT / relative_path).read_text(encoding="utf-8")
        operational_source += source.upper()
        management = ast.unparse(_function_node(relative_path, function_name))
        assert "CENTRAL_AUTO_DAILY_SUMMARIES_ENABLED" not in management

    assert "TP50" in operational_source
    assert "TRAIL" in operational_source
    assert "STOP" in operational_source

    for relative_path, function_name in watchdog_functions.items():
        watchdog = ast.unparse(_function_node(relative_path, function_name))
        assert "CENTRAL_AUTO_DAILY_SUMMARIES_ENABLED" not in watchdog
