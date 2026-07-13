from __future__ import annotations

import ast
import importlib
import sys
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
def test_ceo_daily_modes_run_when_both_flags_are_enabled(monkeypatch, mode):
    contract = _fresh_contract(
        monkeypatch,
        CENTRAL_AUTO_DAILY_SUMMARIES_ENABLED="true",
        CENTRAL_AUTO_CEO_DAILY_ENABLED="true",
    )
    assert contract.central_daily_report_automatic_enabled(mode) is True


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


@pytest.mark.parametrize("mode", ["daily", "executivo", "unknown", None, ""])
def test_global_flag_disabled_blocks_every_mode(monkeypatch, mode):
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
    loop_start = source.index("def central_daily_report_loop():")
    loop_end = source.index("# CENTRAL TELEGRAM COMMAND ROUTER", loop_start)
    loop = source[loop_start:loop_end]
    assert loop.index("central_daily_report_automatic_enabled(") < loop.index(
        'save_daily_snapshot(label="auto")'
    )

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
    namespace = {
        "central_watchdog_status": lambda: {"ok": True},
        "central_trade_registry_snapshot": lambda include_trades=False: {
            "ok": True,
            "include_trades": include_trades,
        },
        "automatic_daily_summaries_health": lambda: expected.copy(),
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
    for field, value in {**learning, **disk, **timeline}.items():
        assert result[field] == value
    assert forbidden_calls == []


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
