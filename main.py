# CENTRAL QUANT PRO FULL - SUPERVISOR MODULAR
# Versão: 2026-07-05-SUPER-CENTRAL-QUANT-V5-REAL-PNL-R-MAPPER-V2.4
#
# Objetivo:
# - Rodar os robôs em um único serviço Render.
# - Preservar as lógicas originais dos arquivos enviados.
# - Evitar reescrever estratégias por aproximação.
# - Permitir ativação gradual por ENABLE_*.
# - Adicionar Turtle Breakout 2.0 como robô de pesquisa/paper.
# - Adicionar painel de runners abertos por R na Central.
# - Adicionar /relatorio, /diagnostico, /selftest e /memory.
# - Instrumentar memória por etapa/bot no nível da Central.
# - Fazer /relatorio completo virar o pacote ideal da avaliação diária:
#   selftest + diagnóstico + exposição + health/funil/eventos/resumo dos 7 bots.
# - Adicionar Telegram exclusivo da Central Quant.
# - Adicionar /executive, /risk, /heat, /ranking, /healthscore, /history e /meta.
# - Adicionar relatório diário automático consolidado pela Central.
# - Adicionar Risk Manager Global em modo consultivo/advisory.
#
# Importante:
# - Pause os serviços antigos no Render antes de ativar o mesmo bot aqui.
# - Se dois processos usarem o mesmo token Telegram com getUpdates, ocorre erro 409.
# - O Turtle aqui é apenas carregado como módulo em bots/turtle.py.
# - A execução real na BingX NÃO é feita pela Central.
# - A memória por scanner interno de cada bot só pode ser medida dentro do próprio bot.
#   Este main mede memória antes/depois de carregar, consultar health, posições,
#   exposure, relatório, diagnóstico, selftest e rotas centralizadas.

import os
import time
import json
import re
import uuid
import gc
import threading
import requests
import importlib.util
import ctypes
try:
    import fcntl
except Exception:
    fcntl = None
try:
    import executive_policy_manager
    EXECUTIVE_POLICY_MANAGER_LOADED = True
    EXECUTIVE_POLICY_MANAGER_ERROR = None
except Exception as e:
    executive_policy_manager = None
    EXECUTIVE_POLICY_MANAGER_LOADED = False
    EXECUTIVE_POLICY_MANAGER_ERROR = str(e)

try:
    from executive_policy_auto_release import (
        run_executive_policy_auto_release,
        build_executive_policy_auto_release_report,
        get_executive_policy_auto_release_health,
    )
    EXECUTIVE_POLICY_AUTO_RELEASE_LOADED = True
    EXECUTIVE_POLICY_AUTO_RELEASE_IMPORT_ERROR = None
except Exception as e:
    EXECUTIVE_POLICY_AUTO_RELEASE_LOADED = False
    EXECUTIVE_POLICY_AUTO_RELEASE_IMPORT_ERROR = str(e)

    def run_executive_policy_auto_release(context=None):
        return {
            "ok": False,
            "module": "executive_policy_auto_release",
            "loaded": False,
            "error": EXECUTIVE_POLICY_AUTO_RELEASE_IMPORT_ERROR,
            "released_codes": [],
            "kept_codes": [],
            "notes": ["Falha ao importar Executive Policy Auto Release no main.py."],
        }

    def build_executive_policy_auto_release_report(result=None):
        result = result or run_executive_policy_auto_release(context={})
        return (
            "🔓 EXECUTIVE POLICY AUTO RELEASE — CENTRAL QUANT\n"
            "Status: ❌\n"
            "Carregado: False\n"
            f"Erro: {EXECUTIVE_POLICY_AUTO_RELEASE_IMPORT_ERROR}"
        )

    def get_executive_policy_auto_release_health():
        return {
            "ok": False,
            "module": "executive_policy_auto_release",
            "loaded": False,
            "error": EXECUTIVE_POLICY_AUTO_RELEASE_IMPORT_ERROR,
        }


try:
    from executive_policy_priority import (
        resolve_executive_policy_priority,
        build_executive_policy_priority_report,
        get_executive_policy_priority_health,
        read_executive_policy_priority_log,
    )
    EXECUTIVE_POLICY_PRIORITY_LOADED = True
    EXECUTIVE_POLICY_PRIORITY_IMPORT_ERROR = None
except Exception as e:
    EXECUTIVE_POLICY_PRIORITY_LOADED = False
    EXECUTIVE_POLICY_PRIORITY_IMPORT_ERROR = str(e)

    def resolve_executive_policy_priority(trade_payload=None, policies=None, commit=True):
        return {
            "ok": False,
            "module": "executive_policy_priority",
            "loaded": False,
            "error": EXECUTIVE_POLICY_PRIORITY_IMPORT_ERROR,
            "decision": "ALLOW",
            "allowed": True,
            "reasons": [],
            "warnings": ["Falha ao importar Executive Policy Priority no main.py."],
        }

    def build_executive_policy_priority_report(result=None):
        return (
            "🏛️ EXECUTIVE POLICY PRIORITY — CENTRAL QUANT\n"
            "Status: ❌\n"
            "Carregado: False\n"
            f"Erro: {EXECUTIVE_POLICY_PRIORITY_IMPORT_ERROR}"
        )

    def get_executive_policy_priority_health():
        return {
            "ok": False,
            "module": "executive_policy_priority",
            "loaded": False,
            "error": EXECUTIVE_POLICY_PRIORITY_IMPORT_ERROR,
        }

    def read_executive_policy_priority_log(limit=20):
        return {
            "ok": False,
            "module": "executive_policy_priority",
            "loaded": False,
            "error": EXECUTIVE_POLICY_PRIORITY_IMPORT_ERROR,
            "items": [],
        }


try:
    from executive_policy_expiration import (
        run_executive_policy_expiration,
        build_executive_policy_expiration_report,
        get_executive_policy_expiration_health,
        read_executive_policy_expiration_log,
    )
    EXECUTIVE_POLICY_EXPIRATION_LOADED = True
    EXECUTIVE_POLICY_EXPIRATION_IMPORT_ERROR = None
except Exception as e:
    EXECUTIVE_POLICY_EXPIRATION_LOADED = False
    EXECUTIVE_POLICY_EXPIRATION_IMPORT_ERROR = str(e)

    def run_executive_policy_expiration(context=None, commit=True):
        return {
            "ok": False,
            "module": "executive_policy_expiration",
            "loaded": False,
            "error": EXECUTIVE_POLICY_EXPIRATION_IMPORT_ERROR,
            "expired_codes": [],
            "kept_codes": [],
            "notes": ["Falha ao importar Executive Policy Expiration no main.py."],
        }

    def build_executive_policy_expiration_report(result=None):
        return (
            "⏳ EXECUTIVE POLICY EXPIRATION — CENTRAL QUANT\n"
            "Status: ❌\n"
            "Carregado: False\n"
            f"Erro: {EXECUTIVE_POLICY_EXPIRATION_IMPORT_ERROR}"
        )

    def get_executive_policy_expiration_health():
        return {
            "ok": False,
            "module": "executive_policy_expiration",
            "loaded": False,
            "error": EXECUTIVE_POLICY_EXPIRATION_IMPORT_ERROR,
        }

    def read_executive_policy_expiration_log(limit=20):
        return {
            "ok": False,
            "module": "executive_policy_expiration",
            "loaded": False,
            "error": EXECUTIVE_POLICY_EXPIRATION_IMPORT_ERROR,
            "items": [],
        }



try:
    from executive_policy_timeline import (
        sync_executive_policy_timeline,
        build_executive_policy_timeline_report,
        get_executive_policy_timeline_health,
        read_executive_policy_timeline,
        get_executive_policy_timeline_stats,
        build_executive_policy_timeline_stats_report,
    )
    EXECUTIVE_POLICY_TIMELINE_LOADED = True
    EXECUTIVE_POLICY_TIMELINE_IMPORT_ERROR = None
except Exception as e:
    EXECUTIVE_POLICY_TIMELINE_LOADED = False
    EXECUTIVE_POLICY_TIMELINE_IMPORT_ERROR = str(e)

    def sync_executive_policy_timeline(context=None, commit=True):
        return {
            "ok": False,
            "module": "executive_policy_timeline",
            "loaded": False,
            "error": EXECUTIVE_POLICY_TIMELINE_IMPORT_ERROR,
            "events_created": 0,
            "events": [],
            "notes": ["Falha ao importar Executive Policy Timeline no main.py."],
        }

    def build_executive_policy_timeline_report(result=None, limit=20):
        return (
            "🧭 EXECUTIVE POLICY TIMELINE — CENTRAL QUANT\n"
            "Status: ❌\n"
            "Carregado: False\n"
            f"Erro: {EXECUTIVE_POLICY_TIMELINE_IMPORT_ERROR}"
        )

    def get_executive_policy_timeline_health():
        return {
            "ok": False,
            "module": "executive_policy_timeline",
            "loaded": False,
            "error": EXECUTIVE_POLICY_TIMELINE_IMPORT_ERROR,
        }

    def read_executive_policy_timeline(limit=30, event_type=None, code=None):
        return {
            "ok": False,
            "module": "executive_policy_timeline",
            "loaded": False,
            "error": EXECUTIVE_POLICY_TIMELINE_IMPORT_ERROR,
            "items": [],
        }

    def get_executive_policy_timeline_stats():
        return {
            "ok": False,
            "module": "executive_policy_timeline",
            "loaded": False,
            "error": EXECUTIVE_POLICY_TIMELINE_IMPORT_ERROR,
        }

    def build_executive_policy_timeline_stats_report():
        return (
            "📊 EXECUTIVE POLICY TIMELINE STATS — CENTRAL QUANT\n"
            "Status: ❌\n"
            "Carregado: False\n"
            f"Erro: {EXECUTIVE_POLICY_TIMELINE_IMPORT_ERROR}"
        )


try:
    from executive_policy_learning import (
        run_executive_policy_learning,
        build_executive_policy_learning_report,
        get_executive_policy_learning_health,
        get_executive_policy_learning_stats,
        build_policy_history_report,
        read_executive_policy_learning_log,
        seed_executive_policy_learning_events,
        build_executive_policy_learning_seed_report,
        run_executive_policy_learning_v2,
        build_executive_policy_effect_report,
        get_executive_policy_effect_stats,
        get_executive_policy_learning_v2_health,
        build_policy_compare_report,
        build_policy_insights_report,
        rebuild_executive_policy_effect,
        build_policy_effect_rebuild_report,
        seed_policy_effect_decision,
        build_policy_effect_seed_report,
    )
    EXECUTIVE_POLICY_LEARNING_LOADED = True
    EXECUTIVE_POLICY_LEARNING_IMPORT_ERROR = None
except Exception as e:
    EXECUTIVE_POLICY_LEARNING_LOADED = False
    EXECUTIVE_POLICY_LEARNING_IMPORT_ERROR = str(e)

    def run_executive_policy_learning(context=None, commit=True, max_events=None):
        return {
            "ok": False,
            "module": "executive_policy_learning",
            "loaded": False,
            "error": EXECUTIVE_POLICY_LEARNING_IMPORT_ERROR,
            "events_read": 0,
            "events_processed": 0,
            "summary": {},
        }

    def build_executive_policy_learning_report(result=None, limit=12):
        return (
            "🧠 EXECUTIVE POLICY LEARNING — CENTRAL QUANT\n"
            "Status: ❌\n"
            "Carregado: False\n"
            f"Erro: {EXECUTIVE_POLICY_LEARNING_IMPORT_ERROR}"
        )

    def get_executive_policy_learning_health():
        return {
            "ok": False,
            "module": "executive_policy_learning",
            "loaded": False,
            "error": EXECUTIVE_POLICY_LEARNING_IMPORT_ERROR,
        }

    def get_executive_policy_learning_stats():
        return {
            "ok": False,
            "module": "executive_policy_learning",
            "loaded": False,
            "error": EXECUTIVE_POLICY_LEARNING_IMPORT_ERROR,
            "policies": {},
            "summary": {},
        }

    def build_policy_history_report(code, limit=1):
        return (
            f"🧠 POLICY HISTORY — {code}\n"
            "Status: ❌\n"
            "Carregado: False\n"
            f"Erro: {EXECUTIVE_POLICY_LEARNING_IMPORT_ERROR}"
        )

    def read_executive_policy_learning_log(limit=20):
        return {
            "ok": False,
            "module": "executive_policy_learning",
            "loaded": False,
            "error": EXECUTIVE_POLICY_LEARNING_IMPORT_ERROR,
            "items": [],
        }

    def seed_executive_policy_learning_events(commit=True):
        return {
            "ok": False,
            "module": "executive_policy_learning",
            "loaded": False,
            "error": EXECUTIVE_POLICY_LEARNING_IMPORT_ERROR,
            "events_created": 0,
        }

    def build_executive_policy_learning_seed_report(result=None):
        return (
            "🌱 EXECUTIVE POLICY LEARNING SEED — CENTRAL QUANT\n"
            "Status: ❌\n"
            "Carregado: False\n"
            f"Erro: {EXECUTIVE_POLICY_LEARNING_IMPORT_ERROR}"
        )

    def run_executive_policy_learning_v2(context=None, commit=True, max_decisions=None):
        return {
            "ok": False,
            "module": "executive_policy_learning_v2",
            "loaded": False,
            "error": EXECUTIVE_POLICY_LEARNING_IMPORT_ERROR,
            "decisions_read": 0,
            "decisions_processed": 0,
        }

    def build_executive_policy_effect_report(result=None, limit=12):
        return (
            "🧠 EXECUTIVE POLICY LEARNING V2.1.2 — POLICY EFFECT\n"
            "Status: ❌\n"
            "Carregado: False\n"
            f"Erro: {EXECUTIVE_POLICY_LEARNING_IMPORT_ERROR}"
        )

    def get_executive_policy_effect_stats():
        return {
            "ok": False,
            "module": "executive_policy_learning_v2",
            "loaded": False,
            "error": EXECUTIVE_POLICY_LEARNING_IMPORT_ERROR,
            "policies": {},
            "summary": {},
        }

    def get_executive_policy_learning_v2_health():
        return {
            "ok": False,
            "module": "executive_policy_learning_v2",
            "loaded": False,
            "error": EXECUTIVE_POLICY_LEARNING_IMPORT_ERROR,
        }

    def build_policy_compare_report(limit=10):
        return (
            "⚖️ POLICY COMPARE — CENTRAL QUANT V2.1.2\n"
            "Status: ❌\n"
            "Carregado: False\n"
            f"Erro: {EXECUTIVE_POLICY_LEARNING_IMPORT_ERROR}"
        )

    def build_policy_insights_report():
        return (
            "💡 POLICY INSIGHTS — CENTRAL QUANT V2.1.2\n"
            "Status: ❌\n"
            "Carregado: False\n"
            f"Erro: {EXECUTIVE_POLICY_LEARNING_IMPORT_ERROR}"
        )

    def rebuild_executive_policy_effect(commit=True, max_decisions=None):
        return {
            "ok": False,
            "module": "executive_policy_learning_v2",
            "loaded": False,
            "error": EXECUTIVE_POLICY_LEARNING_IMPORT_ERROR,
            "rebuild": False,
        }

    def build_policy_effect_rebuild_report(result=None):
        return (
            "♻️ POLICY EFFECT REBUILD — CENTRAL QUANT V2.1.2\n"
            "Status: ❌\n"
            "Carregado: False\n"
            f"Erro: {EXECUTIVE_POLICY_LEARNING_IMPORT_ERROR}"
        )

    def seed_policy_effect_decision(commit=True):
        return {
            "ok": False,
            "module": "executive_policy_learning_v2",
            "loaded": False,
            "error": EXECUTIVE_POLICY_LEARNING_IMPORT_ERROR,
            "events_created": 0,
        }

    def build_policy_effect_seed_report(result=None):
        return (
            "🌱 POLICY EFFECT DECISION SEED — CENTRAL QUANT V2.1.2\n"
            "Status: ❌\n"
            "Carregado: False\n"
            f"Erro: {EXECUTIVE_POLICY_LEARNING_IMPORT_ERROR}"
        )






from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import deque
from flask import Flask, request
from execution_pipeline_status import build_execution_pipeline_text
from execution_orchestrator import (
    execution_health,
    orchestrate_execution,
    read_execution_log,
)
from execution_engine import (
    execution_engine_health,
    run_execution_engine,
    execution_engine_test,
    read_execution_engine_log,
)
from execution_pipeline_status import (
    build_execution_pipeline_status,
    build_execution_pipeline_text,
)
from paper_executor_integrated import (
    paper_integrated_health,
    get_paper_integrated_open_positions,
    read_paper_integrated_log,
)
from paper_lifecycle import (
    paper_lifecycle_health,
    update_paper_position_price,
    get_paper_lifecycle_positions,
    read_paper_lifecycle_log,
    paper_lifecycle_test_tp50,
    paper_lifecycle_test_close,
)
from outcome_evaluator import (
    outcome_evaluator_health,
    evaluate_closed_paper_trades,
    get_outcome_stats,
    read_outcome_log,
)
from adaptive_weights import (
    adaptive_weights_health,
    build_adaptive_weights,
    get_adaptive_weights,
    read_adaptive_weights_log,
    build_adaptive_weights_text,
)
from executive_alert_manager import (
    executive_alert_manager_health,
    build_executive_alerts,
    build_executive_alerts_text,
    build_executive_alert_text,
    read_executive_alert_log,
)
from ceo_confidence import (
    build_ceo_confidence_index,
    build_ceo_confidence_text,
)
from strategic_advisor import (
    build_strategic_advisor,
    build_strategic_advisor_text,
)
from decision_pack import (
    build_decision_pack,
    build_decision_pack_text,
)
from executive_decision_engine import (
    build_executive_decision,
    build_executive_decision_text,
)



# ==========================================================
# MEMORY PROFILER V1.4 — IMPORT SEGURO
# ==========================================================
try:
    import memory_profiler_v1 as memory_profiler
    MEMORY_PROFILER_LOADED = True
    MEMORY_PROFILER_ERROR = None
except Exception as _memory_profiler_exc:
    memory_profiler = None
    MEMORY_PROFILER_LOADED = False
    MEMORY_PROFILER_ERROR = str(_memory_profiler_exc)

app = Flask(__name__)

try:
    import broker as central_broker
except Exception as _broker_import_exc:
    central_broker = None
    BROKER_IMPORT_ERROR = str(_broker_import_exc)
else:
    BROKER_IMPORT_ERROR = None

try:
    import event_bus as central_event_bus
except Exception as _event_bus_import_exc:
    central_event_bus = None
    EVENT_BUS_IMPORT_ERROR = str(_event_bus_import_exc)
else:
    EVENT_BUS_IMPORT_ERROR = None

try:
    import trade_registry as central_trade_registry
except Exception as _trade_registry_import_exc:
    central_trade_registry = None
    TRADE_REGISTRY_IMPORT_ERROR = str(_trade_registry_import_exc)
else:
    TRADE_REGISTRY_IMPORT_ERROR = None

# ==========================================================
# REAL PNL/R MAPPER V2.4 — IMPORT SEGURO
# ==========================================================
try:
    import real_pnl_r_mapper
    REAL_PNL_R_MAPPER_AVAILABLE = True
    REAL_PNL_R_MAPPER_IMPORT_ERROR = None
except Exception as _real_pnl_r_mapper_exc:
    real_pnl_r_mapper = None
    REAL_PNL_R_MAPPER_AVAILABLE = False
    REAL_PNL_R_MAPPER_IMPORT_ERROR = str(_real_pnl_r_mapper_exc)

BOT_NAME = os.environ.get("BOT_NAME", "Central Quant PRO FULL")
TIMEZONE_BR = timezone(timedelta(hours=-3))
BASE_DIR = Path(__file__).resolve().parent
BOTS_DIR = BASE_DIR / "bots"

WATCHDOG_CHECK_SECONDS = int(os.environ.get("WATCHDOG_CHECK_SECONDS", "300"))
WATCHDOG_THRESHOLD_MINUTES = int(os.environ.get("WATCHDOG_THRESHOLD_MINUTES", "20"))
WATCHDOG_ALERT_COOLDOWN_SECONDS = int(os.environ.get("WATCHDOG_ALERT_COOLDOWN_SECONDS", "3600"))

# Memória Render free costuma ser 512 MB.
MEMORY_LIMIT_MB = float(os.environ.get("MEMORY_LIMIT_MB", "512"))
MEMORY_GC_THRESHOLD_MB = float(os.environ.get("MEMORY_GC_THRESHOLD_MB", "430"))
MEMORY_ALERT_THRESHOLD_PCT = float(os.environ.get("MEMORY_ALERT_THRESHOLD_PCT", "90"))
MEMORY_HISTORY_MAXLEN = int(os.environ.get("MEMORY_HISTORY_MAXLEN", "120"))
MEMORY_LOG_INTERVAL_SECONDS = int(os.environ.get("MEMORY_LOG_INTERVAL_SECONDS", "300"))
MEMORY_PROFILE_BOT_STEPS = os.environ.get("MEMORY_PROFILE_BOT_STEPS", "false").strip().lower() in {"1", "true", "yes", "sim", "on"}

MEMORY_HISTORY = deque(maxlen=MEMORY_HISTORY_MAXLEN)
MEMORY_LOCK = threading.Lock()

def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "sim", "on"}


# Telegram exclusivo da Central Quant.
# Use um token diferente dos robôs e, se quiser, o mesmo CHAT_ID que você já usa.
CENTRAL_TELEGRAM_BOT_TOKEN = os.environ.get("CENTRAL_TELEGRAM_BOT_TOKEN")
CENTRAL_TELEGRAM_CHAT_ID = os.environ.get("CENTRAL_TELEGRAM_CHAT_ID")
CENTRAL_TELEGRAM_POLLING_ENABLED = env_bool("CENTRAL_TELEGRAM_POLLING_ENABLED", True)
CENTRAL_DAILY_REPORT_ENABLED = env_bool("CENTRAL_DAILY_REPORT_ENABLED", True)
CENTRAL_DAILY_REPORT_TIME = os.environ.get("CENTRAL_DAILY_REPORT_TIME", "23:55")
# A partir desta versão, "executivo" envia o Executive Report Diário compacto.
# Use CENTRAL_DAILY_REPORT_MODE=dashboard, daily ou audit se quiser voltar aos modos antigos.
CENTRAL_DAILY_REPORT_MODE = os.environ.get("CENTRAL_DAILY_REPORT_MODE", "executivo").strip().lower()
CENTRAL_MONTHLY_REPORT_ENABLED = env_bool("CENTRAL_MONTHLY_REPORT_ENABLED", True)
# Envia no dia 1 às 00:05 consolidando o mês anterior.
CENTRAL_MONTHLY_REPORT_DAY = int(os.environ.get("CENTRAL_MONTHLY_REPORT_DAY", "1"))
CENTRAL_MONTHLY_REPORT_TIME = os.environ.get("CENTRAL_MONTHLY_REPORT_TIME", "00:05")

# Telegram limita mensagens em ~4096 caracteres. Mantemos margem para cabeçalhos.
TELEGRAM_CHUNK_SIZE = int(os.environ.get("TELEGRAM_CHUNK_SIZE", "3400"))
TELEGRAM_LONG_COMMAND_NOTICE = env_bool("TELEGRAM_LONG_COMMAND_NOTICE", True)

# Proteções contra respostas duplicadas no Telegram da Central.
# DROP_PENDING evita reprocessar comandos antigos depois de deploy/restart.
# DUPLICATE_WINDOW evita responder duas vezes ao mesmo comando em poucos segundos
# quando o Telegram reentrega update ou quando o usuário toca no comando duas vezes.
CENTRAL_TELEGRAM_DROP_PENDING_ON_START = env_bool("CENTRAL_TELEGRAM_DROP_PENDING_ON_START", True)
CENTRAL_COMMAND_DUPLICATE_WINDOW_SECONDS = int(os.environ.get("CENTRAL_COMMAND_DUPLICATE_WINDOW_SECONDS", "10"))

# Risk Manager Global decisório. Ele responde ALLOW/DENY em /can_open_trade.
# Em LIVE, o robô executa automaticamente se a Central aprovar e o kill switch estiver ligado.
GLOBAL_RISK_MAX_POSITIONS = int(os.environ.get("GLOBAL_RISK_MAX_POSITIONS", "50"))
GLOBAL_RISK_MAX_PAPER_POSITIONS = int(os.environ.get("GLOBAL_RISK_MAX_PAPER_POSITIONS", "100"))
GLOBAL_RISK_BLOCK_ON_PAPER_LIMIT = env_bool("GLOBAL_RISK_BLOCK_ON_PAPER_LIMIT", False)
# V3.1 hard blocks:
# - acima do limite global de posições, negar novas entradas
# - concentração direcional acima de 70%, negar novas entradas no lado dominante
# - memória acima de 95%, negar novas entradas
# - 3+ exposições no mesmo ativo, negar nova entrada no ativo
GLOBAL_RISK_MAX_SIDE_CONCENTRATION_PCT = float(os.environ.get("GLOBAL_RISK_MAX_SIDE_CONCENTRATION_PCT", "70"))
GLOBAL_RISK_MAX_SYMBOL_EXPOSURE = int(os.environ.get("GLOBAL_RISK_MAX_SYMBOL_EXPOSURE", "3"))
GLOBAL_RISK_MEMORY_BLOCK_PCT = float(os.environ.get("GLOBAL_RISK_MEMORY_BLOCK_PCT", "95"))
GLOBAL_RISK_BLOCK_ON_PAPER_EXPOSURE = env_bool("GLOBAL_RISK_BLOCK_ON_PAPER_EXPOSURE", True)
GLOBAL_RISK_ALLOW_REDUCE_ONLY = env_bool("GLOBAL_RISK_ALLOW_REDUCE_ONLY", True)

# Execução real / BingX.
# ENABLE_REAL_TRADING=false é a trava global: mesmo se um robô estiver LIVE,
# a Central bloqueia ordens reais enquanto esta variável não estiver true.
ENABLE_REAL_TRADING = env_bool("ENABLE_REAL_TRADING", False)
EXECUTION_MODE = os.environ.get("EXECUTION_MODE", "PAPER").strip().upper()
BINGX_READY_CHECK_ENABLED = env_bool("BINGX_READY_CHECK_ENABLED", True)
REAL_TRADING_ALLOWED_BOTS = {
    x.strip().upper() for x in os.environ.get("REAL_TRADING_ALLOWED_BOTS", "FALCON").split(",") if x.strip()
}
REAL_TRADING_ALLOWED_SYMBOLS = {
    x.strip().upper() for x in os.environ.get("REAL_TRADING_ALLOWED_SYMBOLS", "").split(",") if x.strip()
}
REAL_TRADING_MAX_RISK_PCT = float(os.environ.get("REAL_TRADING_MAX_RISK_PCT", "3.0"))
DEFAULT_REAL_MARGIN_USDT = float(os.environ.get("DEFAULT_REAL_MARGIN_USDT", os.environ.get("REAL_TRADING_MARGIN_USDT", os.environ.get("REAL_TRADING_MAX_NOTIONAL_USDT", "20"))))
DEFAULT_REAL_LEVERAGE = int(os.environ.get("DEFAULT_REAL_LEVERAGE", os.environ.get("REAL_TRADING_LEVERAGE", os.environ.get("BINGX_DEFAULT_LEVERAGE", "3"))))
DEFAULT_REAL_EFFECTIVE_NOTIONAL_USDT = DEFAULT_REAL_MARGIN_USDT * DEFAULT_REAL_LEVERAGE
REAL_TRADING_MAX_MARGIN_USDT = float(os.environ.get("REAL_TRADING_MAX_MARGIN_USDT", str(DEFAULT_REAL_MARGIN_USDT)))
REAL_TRADING_MAX_NOTIONAL_USDT = float(os.environ.get("REAL_TRADING_MAX_NOTIONAL_USDT", str(DEFAULT_REAL_EFFECTIVE_NOTIONAL_USDT)))
REAL_TRADING_REQUIRE_READY = env_bool("REAL_TRADING_REQUIRE_READY", True)


def _bot_env_prefix_for_execution(bot):
    bot = str(bot or "").upper().strip()
    aliases = {"TRENDPRO": "TREND", "SMARTPREDATOR": "PREDATOR", "SMART_PREDATOR": "PREDATOR"}
    return aliases.get(bot, bot)


def real_execution_config_for_bot(bot):
    prefix = _bot_env_prefix_for_execution(bot)
    try:
        margin = float(os.environ.get(f"{prefix}_REAL_MARGIN_USDT", DEFAULT_REAL_MARGIN_USDT))
    except Exception:
        margin = DEFAULT_REAL_MARGIN_USDT
    try:
        leverage = int(os.environ.get(f"{prefix}_REAL_LEVERAGE", DEFAULT_REAL_LEVERAGE))
    except Exception:
        leverage = DEFAULT_REAL_LEVERAGE
    return {
        "bot": str(bot or "").upper(),
        "env_prefix": prefix,
        "margin_usdt": margin,
        "leverage": leverage,
        "effective_notional_usdt": margin * leverage,
    }


def all_real_execution_configs():
    return {key: real_execution_config_for_bot(key) for key in BOT_CONFIGS.keys()} if "BOT_CONFIGS" in globals() else {}

DAILY_HISTORY_DIR = BASE_DIR / "daily_history"
DAILY_HISTORY_DIR.mkdir(exist_ok=True)

# Persistência leve do OMS/Decision Engine da Central.
# Não exige banco externo: grava JSONL/JSON local no Render.
#
# V2.1.6 — Main Integration / Data Dir Alignment:
# - A Central passa a respeitar CENTRAL_DATA_DIR quando existir.
# - No Render, se /data existir, ele vira o padrão preferencial.
# - Isso alinha append_decision_log() com o arquivo lido pelo Policy Learning
#   e evita gravar o log rico em /opt/render/project/src/data enquanto
#   /policyeffect lê /data/decision_log.jsonl.
def _resolve_central_data_dir():
    configured = os.environ.get("CENTRAL_DATA_DIR") or os.environ.get("DATA_DIR")
    if configured:
        return Path(configured)
    try:
        if os.path.isdir("/data"):
            return Path("/data")
    except Exception:
        pass
    return BASE_DIR / "data"

CENTRAL_DATA_DIR = _resolve_central_data_dir()
CENTRAL_DATA_DIR.mkdir(parents=True, exist_ok=True)
CENTRAL_DECISION_LOG_FILE = CENTRAL_DATA_DIR / "decision_log.jsonl"
CENTRAL_TIMELINE_LOG_FILE = CENTRAL_DATA_DIR / "timeline.jsonl"
CENTRAL_SHADOW_POSITIONS_FILE = CENTRAL_DATA_DIR / "shadow_positions.json"
CENTRAL_EXECUTION_STATS_FILE = CENTRAL_DATA_DIR / "execution_stats.json"
CENTRAL_STATUS_SNAPSHOTS_FILE = CENTRAL_DATA_DIR / "status_snapshots.jsonl"
CENTRAL_DECISION_LOG_MAX_READ = int(os.environ.get("CENTRAL_DECISION_LOG_MAX_READ", "200"))
CENTRAL_TIMELINE_MAX_READ = int(os.environ.get("CENTRAL_TIMELINE_MAX_READ", "300"))
CENTRAL_TELEGRAM_OFFSET = None
CENTRAL_TELEGRAM_PROCESSED_UPDATES = set()
CENTRAL_TELEGRAM_RECENT_COMMANDS = {}
CENTRAL_TELEGRAM_RECENT_SENDS = {}
CENTRAL_SEND_DUPLICATE_WINDOW_SECONDS = int(os.environ.get("CENTRAL_SEND_DUPLICATE_WINDOW_SECONDS", "8"))
CENTRAL_TELEGRAM_ROUTER_STARTED = False
CENTRAL_TELEGRAM_ROUTER_LOCK = threading.Lock()
CENTRAL_DAILY_REPORT_SENT_DATE = None
CENTRAL_MONTHLY_REPORT_SENT_KEY = None





def agora_sp():
    return datetime.now(TIMEZONE_BR)


def data_hora_sp_str():
    return agora_sp().strftime("%d/%m/%Y %H:%M")


def parse_data_hora_sp(value):
    try:
        if not value:
            return None
        return datetime.strptime(str(value), "%d/%m/%Y %H:%M")
    except Exception:
        return None


def minutes_since(value):
    dt = parse_data_hora_sp(value)
    if not dt:
        return None
    return round((agora_sp().replace(tzinfo=None) - dt).total_seconds() / 60, 2)


def is_benign_bingx_quote_error(value):
    txt = str(value or "").lower()
    return "109500" in txt or "quote service unavailable" in txt


def is_benign_telegram_conflict(value):
    txt = str(value or "").lower()
    return (
        "getupdates" in txt
        and ("409" in txt or "conflict" in txt)
        and "terminated by other getupdates request" in txt
    )


def clean_operational_warning(value):
    if not value:
        return None
    if is_benign_telegram_conflict(value):
        return None
    return value


def safe_round(value, ndigits=2, default=None):
    try:
        if value is None:
            return default
        return round(float(value), ndigits)
    except Exception:
        return default


# ==========================================================
# MEMORY MONITOR
# ==========================================================

def malloc_trim_safe():
    """
    Tenta devolver memória livre do Python/glibc para o sistema operacional.
    Em Render/Linux isso ajuda quando relatórios grandes aumentam o RSS.
    Se não estiver disponível, falha silenciosamente.
    """
    try:
        libc = ctypes.CDLL("libc.so.6")
        libc.malloc_trim(0)
        return True
    except Exception:
        return False


def current_rss_mb():
    """RSS real do processo em MB. Preferimos /proc/self/status no Linux/Render."""
    try:
        with open("/proc/self/status", "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    kb = float(line.split()[1])
                    return round(kb / 1024.0, 2)
    except Exception:
        pass

    try:
        import resource
        usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # Linux retorna KB; macOS retorna bytes. Render é Linux.
        return round(float(usage) / 1024.0, 2)
    except Exception:
        return None


def memory_usage_pct(rss_mb=None):
    rss = current_rss_mb() if rss_mb is None else rss_mb
    if rss is None or not MEMORY_LIMIT_MB:
        return None
    return round((float(rss) / float(MEMORY_LIMIT_MB)) * 100, 2)


def memory_snapshot(label="snapshot", extra=None, store=True, print_log=False):
    rss = current_rss_mb()
    snap = {
        "ts": data_hora_sp_str(),
        "label": str(label),
        "rss_mb": rss,
        "limit_mb": MEMORY_LIMIT_MB,
        "usage_pct": memory_usage_pct(rss),
        "threads": threading.active_count(),
        "gc_count": list(gc.get_count()),
        "loaded_bots": list(LOADED_BOTS.keys()) if "LOADED_BOTS" in globals() else [],
    }
    if isinstance(extra, dict):
        snap.update(extra)

    if store:
        with MEMORY_LOCK:
            MEMORY_HISTORY.append(snap)

    if print_log:
        print(
            f"MEMORY {snap.get('label')} | "
            f"rss={snap.get('rss_mb')} MB | "
            f"usage={snap.get('usage_pct')}% | "
            f"threads={snap.get('threads')}"
        )
    return snap


def force_gc_if_needed(label="gc", force=False):
    before = memory_snapshot(f"{label}_before_gc", store=True)
    before_mb = before.get("rss_mb") or 0
    should_gc = bool(force or before_mb >= MEMORY_GC_THRESHOLD_MB)
    collected = None
    if should_gc:
        collected = gc.collect()
        malloc_trim_safe()
        time.sleep(0.05)
    after = memory_snapshot(
        f"{label}_after_gc",
        extra={"gc_executed": should_gc, "collected": collected, "rss_before_mb": before_mb},
        store=True,
    )
    return before, after


def memory_status_payload(run_gc=False, label="/memory"):
    before = memory_snapshot(f"{label}_before_gc", store=True)
    collected = None
    gc_executed = False
    if run_gc or ((before.get("rss_mb") or 0) >= MEMORY_GC_THRESHOLD_MB):
        gc_executed = True
        collected = gc.collect()
        malloc_trim_safe()
        time.sleep(0.05)
    after = memory_snapshot(
        f"{label}_after_gc",
        extra={"gc_executed": gc_executed, "collected": collected, "rss_before_mb": before.get("rss_mb")},
        store=True,
    )
    with MEMORY_LOCK:
        history = list(MEMORY_HISTORY)[-20:]
    return {
        "ok": (after.get("usage_pct") or 0) < MEMORY_ALERT_THRESHOLD_PCT,
        "status": "OK" if (after.get("usage_pct") or 0) < MEMORY_ALERT_THRESHOLD_PCT else "ALERTA",
        "before_gc": before,
        "current": after,
        "limit_mb": MEMORY_LIMIT_MB,
        "gc_threshold_mb": MEMORY_GC_THRESHOLD_MB,
        "alert_threshold_pct": MEMORY_ALERT_THRESHOLD_PCT,
        "history": history,
    }


def build_memory_text(run_gc=False):
    payload = memory_status_payload(run_gc=run_gc, label="/memory")
    before = payload.get("before_gc") or {}
    cur = payload.get("current") or {}
    history = payload.get("history") or []

    lines = [
        "🧠 MEMÓRIA CENTRAL QUANT",
        f"Data/hora: {data_hora_sp_str()}",
        f"Status: {payload.get('status')}",
        "",
        f"RSS antes GC: {before.get('rss_mb')} MB ({before.get('usage_pct')}%)",
        f"RSS atual: {cur.get('rss_mb')} MB ({cur.get('usage_pct')}%)",
        f"Limite configurado: {payload.get('limit_mb')} MB",
        f"Threshold GC: {payload.get('gc_threshold_mb')} MB",
        f"Threads ativas: {cur.get('threads')}",
        f"GC count: {cur.get('gc_count')}",
        f"GC executado: {cur.get('gc_executed')} | coletados: {cur.get('collected')}",
        "",
        "Histórico recente:",
    ]
    for item in history[-12:]:
        lines.append(f"{item.get('ts')} | {item.get('label')} | {item.get('rss_mb')} MB | {item.get('usage_pct')}% | threads={item.get('threads')}")
    lines += [
        "",
        "Observação:",
        "Se a memória ficar acima de 90% por muito tempo, o Render pode reiniciar o serviço.",
    ]
    return "\n".join(lines), payload


def memory_profile_step(label):
    """Atalho para snapshots pequenos por etapa. Desligável por MEMORY_PROFILE_BOT_STEPS=false."""
    if MEMORY_PROFILE_BOT_STEPS:
        return memory_snapshot(label, store=True, print_log=False)
    return None


def memory_monitor_loop():
    while True:
        try:
            snap = memory_snapshot("memory_loop", store=True, print_log=True)
            if (snap.get("rss_mb") or 0) >= MEMORY_GC_THRESHOLD_MB:
                force_gc_if_needed("memory_loop")
        except Exception as exc:
            print("ERRO MEMORY MONITOR:", exc)
        time.sleep(MEMORY_LOG_INTERVAL_SECONDS)


# Cada bot recebe seus tokens próprios, mapeados para TELEGRAM_BOT_TOKEN/CHAT_ID
# apenas durante o import do módulo. Assim o código original continua intacto.
BOT_CONFIGS = {
    "TRENDPRO": {
        "enabled_env": "ENABLE_TRENDPRO",
        "module": "trendpro",
        "file": BOTS_DIR / "trendpro.py",
        "name": "Trend PRO Elite",
        "token_env": "TREND_PRO_ELITE_TOKEN",
        "chat_env": "TREND_PRO_ELITE_CHAT_ID",
    },
    "DONKEY": {
        "enabled_env": "ENABLE_DONKEY",
        "module": "donkey",
        "file": BOTS_DIR / "donkey.py",
        "name": "Donkey H4",
        "token_env": "DONKEY_H4_TOKEN",
        "chat_env": "DONKEY_H4_CHAT_ID",
    },
    "COBRA": {
        "enabled_env": "ENABLE_COBRA",
        "module": "cobra",
        "file": BOTS_DIR / "cobra.py",
        "name": "Cobra Attack",
        "token_env": "COBRA_ATTACK_TOKEN",
        "chat_env": "COBRA_ATTACK_CHAT_ID",
        "extra_token_envs": ["COBRA_TELEGRAM_BOT_TOKEN", "COBRA_TOKEN"],
        "extra_chat_envs": ["COBRA_TELEGRAM_CHAT_ID", "COBRA_CHAT_ID"],
    },
    "MEME": {
        "enabled_env": "ENABLE_MEME",
        "module": "meme",
        "file": BOTS_DIR / "meme.py",
        "name": "Meme Hunter",
        "token_env": "MEME_HUNTER_TOKEN",
        "chat_env": "MEME_HUNTER_CHAT_ID",
    },
    "PREDATOR": {
        "enabled_env": "ENABLE_PREDATOR",
        "module": "predator",
        "file": BOTS_DIR / "predator.py",
        "name": "Smart Predator",
        "token_env": "SMART_PREDATOR_TOKEN",
        "chat_env": "SMART_PREDATOR_CHAT_ID",
    },
    "TURTLE": {
        "enabled_env": "ENABLE_TURTLE",
        "module": "turtle",
        "file": BOTS_DIR / "turtle.py",
        "name": "Turtle Breakout 2.0",
        "token_env": "TURTLE_TOKEN",
        "chat_env": "TURTLE_CHAT_ID",
        "extra_token_envs": ["TURTLE_TELEGRAM_BOT_TOKEN", "TELEGRAM_BOT_TOKEN"],
        "extra_chat_envs": ["TURTLE_TELEGRAM_CHAT_ID", "TELEGRAM_CHAT_ID"],
    },
    "FALCON": {
        "enabled_env": "ENABLE_FALCON",
        "module": "falcon",
        "file": BOTS_DIR / "falcon.py",
        "name": "Falcon Strike",
        "token_env": "FALCON_TOKEN",
        "chat_env": "FALCON_CHAT_ID",
        "extra_token_envs": ["FALCON_TELEGRAM_BOT_TOKEN", "TELEGRAM_BOT_TOKEN"],
        "extra_chat_envs": ["FALCON_TELEGRAM_CHAT_ID", "TELEGRAM_CHAT_ID"],
    },
}

LOADED_BOTS = {}
LOAD_ERRORS = {}
CENTRAL_HEALTH = {
    "started_at": data_hora_sp_str(),
    "last_watchdog_check": None,
    "last_watchdog_alert": None,
    "last_watchdog_alert_ts": 0,
    "watchdog_status": "OK",
}


TRADE_REGISTRY_AUTOSYNC_STATUS = {
    "last_run": None,
    "last_ok": None,
    "last_error": None,
    "last_result": None,
}

# Evita inicialização duplicada de bots/roteadores no mesmo processo.
CENTRAL_RUNTIME_STARTED = False
CENTRAL_RUNTIME_LOCK = threading.Lock()

# Locks de processo para evitar duplicidade quando o Render/Gunicorn inicia
# mais de um worker/processo. A trava em memória evita duplicidade só dentro
# do mesmo processo; esta trava em arquivo vale para o container inteiro.
CENTRAL_PROCESS_LOCK_HANDLES = {}


def acquire_runtime_file_lock(lock_name: str):
    """
    Retorna True se este processo virou o líder daquele trabalho.
    Retorna False se outro processo já estiver executando o mesmo polling/loop.

    Importante: mantemos o file handle aberto em CENTRAL_PROCESS_LOCK_HANDLES.
    Se fechar, o lock é liberado pelo sistema operacional.
    """
    try:
        safe_name = re.sub(r"[^a-zA-Z0-9_.-]+", "_", str(lock_name or "runtime"))
        lock_path = CENTRAL_DATA_DIR / f"{safe_name}.lock"
        lock_path.parent.mkdir(exist_ok=True)
        fh = open(lock_path, "w", encoding="utf-8")

        if fcntl is not None:
            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                print(f"LOCK ATIVO - {safe_name}: outro processo já é líder")
                try:
                    fh.close()
                except Exception:
                    pass
                return False

        fh.seek(0)
        fh.truncate()
        fh.write(json.dumps({
            "lock": safe_name,
            "pid": os.getpid(),
            "ts": data_hora_sp_str(),
            "base_dir": str(BASE_DIR),
            "data_dir": str(CENTRAL_DATA_DIR),
        }, ensure_ascii=False))
        fh.flush()
        CENTRAL_PROCESS_LOCK_HANDLES[safe_name] = fh
        print(f"LOCK OK - {safe_name}: pid={os.getpid()}")
        return True
    except Exception as exc:
        # Fallback conservador: se não conseguir travar, deixa rodar para não derrubar a Central.
        print(f"ERRO LOCK {lock_name}: {exc}")
        return True


def _set_env_temporarily(mapping):
    old = {}
    for key, value in mapping.items():
        old[key] = os.environ.get(key)
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = str(value)
    return old


def _restore_env(old):
    for key, value in old.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def load_bot(key: str, cfg: dict):
    if not cfg["file"].exists():
        raise FileNotFoundError(str(cfg["file"]))

    token = os.environ.get(cfg["token_env"])
    chat_id = os.environ.get(cfg["chat_env"])

    env_map = {
        "TELEGRAM_BOT_TOKEN": token,
        "TELEGRAM_CHAT_ID": chat_id,
        "BOT_NAME": cfg["name"],
    }

    for extra in cfg.get("extra_token_envs", []):
        env_map[extra] = token
    for extra in cfg.get("extra_chat_envs", []):
        env_map[extra] = chat_id

    memory_profile_step(f"before_import_{key}")
    old_env = _set_env_temporarily(env_map)
    try:
        module_name = f"central_bots.{cfg['module']}"
        spec = importlib.util.spec_from_file_location(module_name, cfg["file"])
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)
        return module
    finally:
        _restore_env(old_env)
        memory_profile_step(f"after_import_{key}")


def start_enabled_bots():
    for key, cfg in BOT_CONFIGS.items():
        if not env_bool(cfg["enabled_env"], default=False):
            continue
        try:
            memory_profile_step(f"before_load_bot_{key}")
            LOADED_BOTS[key] = load_bot(key, cfg)
            try:
                import history_manager as super_history_manager
                super_history_manager.wrap_bot_module(LOADED_BOTS[key], key)
            except Exception as _history_wrap_exc:
                print(f"AVISO HISTORY WRAP BOT {key}: {_history_wrap_exc}")
            print(f"BOT CARREGADO: {key} - {cfg['name']}")
            memory_profile_step(f"after_load_bot_{key}")
            if (current_rss_mb() or 0) >= MEMORY_GC_THRESHOLD_MB:
                force_gc_if_needed(f"after_load_bot_{key}")
        except Exception as exc:
            LOAD_ERRORS[key] = str(exc)
            print(f"ERRO AO CARREGAR {key}: {exc}")
            memory_profile_step(f"load_error_{key}")


def bot_health(key: str, cfg: dict):
    memory_profile_step(f"before_bot_health_{key}")
    module = LOADED_BOTS.get(key)
    enabled = env_bool(cfg["enabled_env"], default=False)
    token_configured = bool(os.environ.get(cfg["token_env"]))
    chat_configured = bool(os.environ.get(cfg["chat_env"]))

    payload = {
        "name": cfg["name"],
        "enabled": enabled,
        "loaded": module is not None,
        "token_configured": token_configured,
        "chat_configured": chat_configured,
        "load_error": LOAD_ERRORS.get(key),
    }

    if module is not None:
        raw_health = getattr(module, "HEALTH", {}) or {}
        health = dict(raw_health) if isinstance(raw_health, dict) else {}
        health["last_warning"] = clean_operational_warning(health.get("last_warning"))

        payload["health"] = health
        payload["last_scanner_run"] = health.get("last_scanner_run")
        payload["last_management_run"] = health.get("last_management_run")
        payload["last_error"] = health.get("last_error")
        payload["minutes_since_scanner"] = minutes_since(health.get("last_scanner_run"))
        payload["minutes_since_management"] = minutes_since(health.get("last_management_run"))

    memory_profile_step(f"after_bot_health_{key}")
    return payload


def get_open_positions_from_module(module, key=None):
    positions = []
    label = key or getattr(module, "__name__", "unknown")
    memory_profile_step(f"before_positions_{label}")
    try:
        if hasattr(module, "carregar_posicoes"):
            raw = module.carregar_posicoes()
        elif hasattr(module, "get_positions"):
            raw = module.get_positions()
        else:
            raw = {}

        if isinstance(raw, dict):
            iterable = raw.values()
        elif isinstance(raw, list):
            iterable = raw
        else:
            iterable = []

        for p in iterable:
            if not isinstance(p, dict):
                continue
            status = str(p.get("status", "OPEN")).upper()
            if status in {"ENCERRADO", "CLOSED", "FECHADO"}:
                continue
            positions.append(p)
    except Exception:
        pass
    finally:
        memory_profile_step(f"after_positions_{label}")
    return positions


def _safe_float(value, default=0.0):
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _position_runner_r(position: dict):
    if not isinstance(position, dict):
        return 0.0
    candidates = ["current_r", "pnl_r", "unrealized_r", "open_r", "result_r", "mfe_r"]
    for field in candidates:
        if field in position and position.get(field) is not None:
            return _safe_float(position.get(field), 0.0)
    return 0.0


def _position_runner_pct(position: dict):
    if not isinstance(position, dict):
        return 0.0
    candidates = ["current_pct", "pnl_pct", "unrealized_pct", "open_pct", "result_pct", "mfe_pct"]
    for field in candidates:
        if field in position and position.get(field) is not None:
            return _safe_float(position.get(field), 0.0)
    return 0.0


def _empty_runner_buckets():
    return {
        "runners_1r_open": 0,
        "runners_2r_open": 0,
        "runners_3r_open": 0,
        "runners_5r_open": 0,
        "runners_10r_open": 0,
    }


def _update_runner_buckets(buckets: dict, runner_r: float):
    if runner_r >= 1.0:
        buckets["runners_1r_open"] += 1
    if runner_r >= 2.0:
        buckets["runners_2r_open"] += 1
    if runner_r >= 3.0:
        buckets["runners_3r_open"] += 1
    if runner_r >= 5.0:
        buckets["runners_5r_open"] += 1
    if runner_r >= 10.0:
        buckets["runners_10r_open"] += 1


def central_exposure_snapshot():
    memory_profile_step("before_exposure_snapshot")

    positions = get_open_positions_central()

    total = 0
    longs = 0
    shorts = 0
    by_bot = {}
    open_runner_buckets = _empty_runner_buckets()
    best_open_runner = None

    for p in positions:
        if not isinstance(p, dict):
            continue

        bot = normalize_registry_bot(p.get("bot") or "UNKNOWN")
        symbol = normalize_registry_symbol(
            p.get("symbol_clean") or p.get("symbol") or p.get("ativo") or p.get("pair")
        )
        setup = p.get("setup") or p.get("signal_type") or p.get("setup_label")
        side = str(p.get("side") or p.get("direction") or "").upper()

        by_bot.setdefault(bot, {
            "total": 0,
            "long": 0,
            "short": 0,
            "open_runners": _empty_runner_buckets(),
            "best_open_runner": None,
        })

        if side in {"LONG", "BUY"}:
            longs += 1
            by_bot[bot]["long"] += 1
        elif side in {"SHORT", "SELL"}:
            shorts += 1
            by_bot[bot]["short"] += 1

        runner_r = _position_runner_r(p)
        runner_pct = _position_runner_pct(p)

        _update_runner_buckets(open_runner_buckets, runner_r)
        _update_runner_buckets(by_bot[bot]["open_runners"], runner_r)

        runner_payload = {
            "bot": bot,
            "symbol": symbol,
            "setup": setup,
            "side": side,
            "runner_r": round(runner_r, 4),
            "runner_pct": round(runner_pct, 4),
            "entry": p.get("entry") or p.get("entrada"),
            "stop": p.get("stop") or p.get("sl") or p.get("stop_atual"),
            "tp50": p.get("tp50"),
        }

        if by_bot[bot]["best_open_runner"] is None or runner_r > by_bot[bot]["best_open_runner"].get("runner_r", 0):
            by_bot[bot]["best_open_runner"] = dict(runner_payload)

        if best_open_runner is None or runner_r > best_open_runner.get("runner_r", 0):
            best_open_runner = dict(runner_payload)

        by_bot[bot]["total"] += 1
        total += 1

    result = {
        "source": "trade_registry",
        "total_positions_open": total,
        "long_positions_open": longs,
        "short_positions_open": shorts,
        "open_runners": open_runner_buckets,
        "best_open_runner": best_open_runner,
        "by_bot": by_bot,
    }

    memory_profile_step("after_exposure_snapshot")
    return result


def central_watchdog_status():
    memory_profile_step("before_watchdog_status")
    reasons = []
    bots = {}

    for key, cfg in BOT_CONFIGS.items():
        b = bot_health(key, cfg)
        bots[key] = b

        if not b["enabled"]:
            continue
        if not b["loaded"]:
            reasons.append(f"{key}: não carregado ({b.get('load_error')})")
            continue

        last_error = b.get("last_error")
        if last_error and not is_benign_bingx_quote_error(last_error):
            reasons.append(f"{key}: last_error={last_error}")

        ms = b.get("minutes_since_scanner")
        mm = b.get("minutes_since_management")
        if ms is not None and ms > WATCHDOG_THRESHOLD_MINUTES:
            reasons.append(f"{key}: scanner parado há {ms} min")
        if mm is not None and mm > WATCHDOG_THRESHOLD_MINUTES:
            reasons.append(f"{key}: gestão parada há {mm} min")

    result = {
        "ok": len(reasons) == 0,
        "status": "OK" if len(reasons) == 0 else "ALERTA",
        "central_started_at": CENTRAL_HEALTH["started_at"],
        "threshold_minutes": WATCHDOG_THRESHOLD_MINUTES,
        "reasons": reasons,
        "bots": bots,
    }
    memory_profile_step("after_watchdog_status")
    return result


def send_central_alert(message: str):
    for module in LOADED_BOTS.values():
        try:
            if hasattr(module, "safe_send_telegram"):
                module.safe_send_telegram(message)
            elif hasattr(module, "send_telegram"):
                module.send_telegram(message)
        except Exception:
            pass


def central_watchdog_loop():
    while True:
        try:
            CENTRAL_HEALTH["last_watchdog_check"] = data_hora_sp_str()
            memory_profile_step("watchdog_loop_start")
            status = central_watchdog_status()
            CENTRAL_HEALTH["watchdog_status"] = status["status"]

            if not status["ok"]:
                last = float(CENTRAL_HEALTH.get("last_watchdog_alert_ts", 0) or 0)
                if time.time() - last >= WATCHDOG_ALERT_COOLDOWN_SECONDS:
                    msg = (
                        f"🚨 WATCHDOG CENTRAL - {BOT_NAME}\n\n"
                        "Possível falha detectada:\n"
                        + "\n".join([f"- {r}" for r in status["reasons"]])
                    )
                    send_central_alert(msg)
                    CENTRAL_HEALTH["last_watchdog_alert"] = data_hora_sp_str()
                    CENTRAL_HEALTH["last_watchdog_alert_ts"] = time.time()
            memory_profile_step("watchdog_loop_end")
            if (current_rss_mb() or 0) >= MEMORY_GC_THRESHOLD_MB:
                force_gc_if_needed("watchdog_loop")
        except Exception as exc:
            print("ERRO WATCHDOG CENTRAL:", exc)

        time.sleep(WATCHDOG_CHECK_SECONDS)


def central_trade_registry_snapshot(include_trades=True):
    """Snapshot seguro do Trade Registry central usando leitura direta do arquivo."""
    if central_trade_registry is None:
        return {
            "ok": False,
            "loaded": False,
            "module": "trade_registry",
            "import_error": TRADE_REGISTRY_IMPORT_ERROR,
            "open_count": 0,
            "closed_count": 0,
            "by_bot": {},
            "by_symbol": {},
            "by_side": {},
        }

    try:
        registry = central_trade_registry.load_registry()

        open_raw = registry.get("open_trades", {})
        closed_raw = registry.get("closed_trades", [])

        if isinstance(open_raw, dict):
            open_trades = list(open_raw.values())
        elif isinstance(open_raw, list):
            open_trades = open_raw
        else:
            open_trades = []

        if isinstance(closed_raw, dict):
            closed_trades = list(closed_raw.values())
        elif isinstance(closed_raw, list):
            closed_trades = closed_raw
        else:
            closed_trades = []

        open_trades = [t for t in open_trades if isinstance(t, dict)]
        closed_trades = [t for t in closed_trades if isinstance(t, dict)]

        by_bot = {}
        by_symbol = {}
        by_side = {}

        for trade in open_trades:
            bot = normalize_registry_bot(trade.get("bot") or "UNKNOWN")
            symbol = normalize_registry_symbol(
                trade.get("symbol_clean")
                or trade.get("symbol")
                or trade.get("ativo")
                or trade.get("pair")
                or "UNKNOWN"
            )
            side = str(
                trade.get("side")
                or trade.get("direction")
                or "UNKNOWN"
            ).upper().strip()

            if side == "BUY":
                side = "LONG"
            elif side == "SELL":
                side = "SHORT"

            by_bot[bot] = by_bot.get(bot, 0) + 1
            by_symbol[symbol] = by_symbol.get(symbol, 0) + 1
            by_side[side] = by_side.get(side, 0) + 1

        payload = {
            "ok": True,
            "loaded": True,
            "module": "trade_registry",
            "import_error": None,
            "version": registry.get("version"),
            "updated_at": registry.get("updated_at"),
            "open_count": len(open_trades),
            "closed_count": len(closed_trades),
            "by_bot": by_bot,
            "by_symbol": by_symbol,
            "by_side": by_side,
            "trade_registry_file": str(getattr(central_trade_registry, "TRADE_REGISTRY_FILE", "")),
            "data_dir": str(getattr(central_trade_registry, "DATA_DIR", "")),
        }

        if include_trades:
            payload["open_trades"] = open_trades
            payload["closed_trades"] = closed_trades

        return payload

    except Exception as exc:
        return {
            "ok": False,
            "loaded": True,
            "module": "trade_registry",
            "import_error": None,
            "error": str(exc),
            "open_count": 0,
            "closed_count": 0,
            "by_bot": {},
            "by_symbol": {},
            "by_side": {},
            "trade_registry_file": str(getattr(central_trade_registry, "TRADE_REGISTRY_FILE", "")),
            "data_dir": str(getattr(central_trade_registry, "DATA_DIR", "")),
        }


def get_open_positions_central():
    """
    Fonte oficial de posições abertas da Central Quant.
    Prioridade: Trade Registry.
    Fallback: posições lidas diretamente dos robôs.
    """
    # 1) Fonte oficial: Trade Registry direto
    try:
        if central_trade_registry is not None:
            registry = central_trade_registry.load_registry()
            open_trades = registry.get("open_trades", {})

            if isinstance(open_trades, dict):
                trades = list(open_trades.values())
            elif isinstance(open_trades, list):
                trades = open_trades
            else:
                trades = []

            trades = [t for t in trades if isinstance(t, dict)]

            if trades:
                return trades
    except Exception:
        pass

    # 2) Fallback: snapshot central
    try:
        snap = central_trade_registry_snapshot(include_trades=True)
        trades = snap.get("open_trades", [])

        if isinstance(trades, dict):
            trades = list(trades.values())
        elif not isinstance(trades, list):
            trades = []

        trades = [t for t in trades if isinstance(t, dict)]

        if trades:
            return trades
    except Exception:
        pass

    # 3) Fallback final: posições lidas dos robôs
    positions = []
    for key, module in LOADED_BOTS.items():
        for p in get_open_positions_from_module(module, key=key):
            if isinstance(p, dict):
                p = dict(p)
                p.setdefault("bot", key)
                positions.append(p)

    return positions        


@app.route("/")
def home():
    return f"{BOT_NAME} Online"


@app.route("/memory")
def memory_profiler_route():
    """
    Memory Profiler V1.4.
    Endpoint leve.
    Não inclui legacy_memory.
    Não inclui text.
    Uma chamada HTTP = um único snapshot.
    """
    try:
        if MEMORY_PROFILER_LOADED and memory_profiler:
            deep = str(request.args.get("deep", "false")).strip().lower() in {"1", "true", "yes", "sim", "on"}
            return memory_profiler.build_memory_json(deep=deep, include_text=False), 200
        return {"ok": False, "loaded": False, "error": MEMORY_PROFILER_ERROR}, 500
    except Exception as exc:
        return {"ok": False, "route": "/memory", "error": str(exc)}, 500


@app.route("/memorytext")
def memory_profiler_text_route():
    """
    Relatório texto separado.
    """
    try:
        if MEMORY_PROFILER_LOADED and memory_profiler:
            deep = str(request.args.get("deep", "false")).strip().lower() in {"1", "true", "yes", "sim", "on"}
            return memory_profiler.build_memory_report(include_tracemalloc=deep, deep=deep), 200, {"Content-Type": "text/plain; charset=utf-8"}
        return f"Memory Profiler não carregado: {MEMORY_PROFILER_ERROR}", 500, {"Content-Type": "text/plain; charset=utf-8"}
    except Exception as exc:
        return f"Erro no /memorytext: {exc}", 500, {"Content-Type": "text/plain; charset=utf-8"}


@app.route("/memorylegacy")
def memory_legacy_route():
    """
    Comparação opcional com o monitor legado.
    Separado do /memory para evitar duplicidade de medição.
    """
    try:
        return memory_status_payload(run_gc=False, label="/memory_legacy")
    except Exception as exc:
        return {"ok": False, "route": "/memorylegacy", "error": str(exc)}, 500





@app.route("/eventbus/status")
def eventbus_status():
    """Status simples do Event Bus da Super Central Quant."""
    payload = {
        "ok": central_event_bus is not None,
        "module": "event_bus",
        "loaded": central_event_bus is not None,
        "import_error": EVENT_BUS_IMPORT_ERROR,
        "history_manager_loaded": False,
        "history_manager_error": None,
    }
    if central_event_bus is not None:
        payload.update({
            "history_manager_loaded": getattr(central_event_bus, "history_manager", None) is not None,
            "history_manager_error": getattr(central_event_bus, "HISTORY_MANAGER_ERROR", None),
            "event_bus_log_file": str(getattr(central_event_bus, "EVENT_BUS_LOG_FILE", "")),
            "event_bus_seen_file": str(getattr(central_event_bus, "EVENT_BUS_SEEN_FILE", "")),
            "version": "2026-06-28-EVENT-BUS-V1",
        })
    return payload


@app.route("/eventbus/emit", methods=["POST"])
def eventbus_emit_route():
    """Entrada HTTP interna para emitir eventos padronizados no Super History."""
    if central_event_bus is None:
        return {"ok": False, "error": EVENT_BUS_IMPORT_ERROR or "event_bus import failed"}, 500
    payload = request.get_json(silent=True) or {}
    result = central_event_bus.emit_from_http(payload)
    status = 200 if result.get("ok") else 500
    return result, status


@app.route("/executive/alerts/health")
@app.route("/executive_alerts/health")
def executive_alerts_health_route():
    return executive_alert_manager_health()


@app.route("/executive/policy/health")
@app.route("/policy/health")
def executive_policy_health_route():
    if not EXECUTIVE_POLICY_MANAGER_LOADED:
        return {"ok": False, "loaded": False, "error": EXECUTIVE_POLICY_MANAGER_ERROR}, 500
    try:
        as_text = str(request.args.get("format", "")).strip().lower() in {"text", "txt", "1", "true"}
        if as_text:
            return executive_policy_manager.format_policy_health_text()
        return executive_policy_manager.policy_manager_health()
    except Exception as exc:
        return {"ok": False, "loaded": True, "error": str(exc)}, 500


def _normalize_executive_policy_items_for_text(raw, include_disabled=False):
    """
    Normaliza a saída do Executive Policy Manager para relatório humano.
    V1.2: aceita retorno direto em lista, dict com listas internas, active_codes
    e estruturas aninhadas em payload/data/result.
    """
    def _first_policy_list(value, depth=0):
        if depth > 4 or value is None:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            for key in ["active_policies", "policies", "items", "data", "payload", "result", "active"]:
                child = value.get(key)
                found = _first_policy_list(child, depth + 1)
                if found:
                    return found
            codes = value.get("active_codes") or value.get("codes")
            if isinstance(codes, list) and codes:
                return [{"code": code, "enabled": True} for code in codes]
            # Alguns estados podem ser dict code -> policy.
            dict_items = []
            for key, child in value.items():
                if isinstance(child, dict):
                    item = dict(child)
                    item.setdefault("code", key)
                    dict_items.append(item)
            return dict_items
        return []

    items = _first_policy_list(raw)
    out = []
    seen = set()

    for item in items:
        if isinstance(item, str):
            item = {"code": item, "enabled": True}
        if not isinstance(item, dict):
            continue

        code = str(
            item.get("code")
            or item.get("policy_code")
            or item.get("name")
            or item.get("id")
            or ""
        ).upper().strip()
        if not code or code in seen:
            continue

        enabled = item.get("enabled", item.get("active", True))
        enabled_str = str(enabled).strip().lower()
        is_disabled = enabled is False or enabled_str in {"false", "0", "no", "não", "nao", "off", "disabled"}
        if is_disabled and not include_disabled:
            continue

        normalized = dict(item)
        normalized["code"] = code
        normalized["enabled"] = not is_disabled
        seen.add(code)
        out.append(normalized)

    return out


def _build_executive_policies_text_from_manager(include_disabled=False):
    """
    Formatter local e resiliente para /policies.
    V1.2: usa o retorno direto em lista de executive_policy_manager.get_active_policies().
    """
    if not EXECUTIVE_POLICY_MANAGER_LOADED or executive_policy_manager is None:
        return f"❌ Executive Policy Manager não carregado: {EXECUTIVE_POLICY_MANAGER_ERROR}"

    manager_function = None
    raw = None
    error = None

    try:
        # Para o relatório de ativas, usar exatamente a mesma função validada pelo Priority V1.1.
        if not include_disabled and hasattr(executive_policy_manager, "get_active_policies"):
            manager_function = "get_active_policies"
            raw = executive_policy_manager.get_active_policies()
        elif include_disabled and hasattr(executive_policy_manager, "get_all_policies"):
            manager_function = "get_all_policies"
            raw = executive_policy_manager.get_all_policies()
        elif hasattr(executive_policy_manager, "get_active_policies"):
            manager_function = "get_active_policies"
            raw = executive_policy_manager.get_active_policies()
        elif hasattr(executive_policy_manager, "load_policy_state"):
            manager_function = "load_policy_state"
            raw = executive_policy_manager.load_policy_state()
        else:
            manager_function = "format_policies_text_fallback"
            return executive_policy_manager.format_policies_text(include_disabled=include_disabled)
    except Exception as exc:
        error = str(exc)
        try:
            return executive_policy_manager.format_policies_text(include_disabled=include_disabled)
        except Exception:
            return (
                "📜 EXECUTIVE POLICIES — CENTRAL QUANT\n"
                f"Data/hora: {data_hora_sp_str()}\n"
                "Status: ❌\n"
                f"Erro: {error}"
            )

    policies = _normalize_executive_policy_items_for_text(raw, include_disabled=include_disabled)

    raw_type = type(raw).__name__
    raw_len = len(raw) if isinstance(raw, (list, dict)) else "N/A"

    lines = [
        "📜 EXECUTIVE POLICIES — CENTRAL QUANT",
        f"Data/hora: {data_hora_sp_str()}",
        f"Exibindo: {'todas' if include_disabled else 'ativas'}",
        f"Fonte: executive_policy_manager.{manager_function}",
        f"Raw type: {raw_type} | Raw len: {raw_len}",
        "",
    ]

    if not policies:
        lines += [
            "Nenhuma política encontrada.",
            "",
            "Diagnóstico:",
            "- A fonte foi chamada, mas o formatter não encontrou itens normalizáveis.",
            "- Se /executive/policy retornar uma lista, envie esse JSON para ajuste fino.",
        ]
        return "\n".join(lines)

    lines.append(f"Policies encontradas: {len(policies)}")
    lines.append("")

    def _sort_key(policy):
        level = str(policy.get("level") or "P9").upper().strip()
        try:
            p = int(level[1:]) if level.startswith("P") and level[1:].isdigit() else 9
        except Exception:
            p = 9
        return (p, str(policy.get("code") or ""))

    for idx, policy in enumerate(sorted(policies, key=_sort_key), start=1):
        payload = policy.get("payload") if isinstance(policy.get("payload"), dict) else {}
        enabled = policy.get("enabled", True)
        lines += [
            f"{idx}. {policy.get('code')}",
            f"- Título: {policy.get('title') or 'N/A'}",
            f"- Status: {'ATIVA' if enabled else 'INATIVA'}",
            f"- Level: {policy.get('level') or 'N/A'} | Categoria: {policy.get('category') or 'N/A'}",
            f"- Ação: {policy.get('action') or 'N/A'}",
            f"- Motivo: {policy.get('reason') or 'N/A'}",
            f"- Criada em: {policy.get('created_at') or 'N/A'}",
            f"- Atualizada em: {policy.get('updated_at') or 'N/A'}",
        ]
        if policy.get("expires_at"):
            lines.append(f"- Expira em: {policy.get('expires_at')}")
        if policy.get("release_condition"):
            lines.append(f"- Release: {policy.get('release_condition')}")
        if payload:
            compact_payload = []
            for key in [
                "dominant_side", "dominant_pct", "allow_expansion", "blocks_expansion",
                "monthly_trades", "adaptive_confidence", "ceo_confidence", "allow_risk_increase",
            ]:
                if key in payload:
                    compact_payload.append(f"{key}={payload.get(key)}")
            if compact_payload:
                lines.append(f"- Payload: {', '.join(compact_payload)}")
        lines.append("")

    lines += [
        "Notas:",
        "- Este relatório usa a mesma fonte oficial do Priority V1.1.",
        "- get_active_policies() retorna lista direta; o formatter agora trata list corretamente.",
    ]
    return "\n".join(lines)

@app.route("/executive/policy")
@app.route("/policies")
def executive_policy_route():
    if not EXECUTIVE_POLICY_MANAGER_LOADED:
        return {"ok": False, "loaded": False, "error": EXECUTIVE_POLICY_MANAGER_ERROR}, 500
    try:
        as_text = str(request.args.get("format", "")).strip().lower() in {"text", "txt", "1", "true"}
        include_disabled = str(request.args.get("include_disabled", "false")).strip().lower() in {"1", "true", "yes", "sim", "on"}
        if as_text:
            return _build_executive_policies_text_from_manager(include_disabled=include_disabled)
        return executive_policy_manager.get_active_policies()
    except Exception as exc:
        return {"ok": False, "loaded": True, "error": str(exc)}, 500



@app.route("/policyautorelease", methods=["GET"])
@app.route("/executive/policy/auto_release", methods=["GET"])
def policy_auto_release_route():
    """
    Executa uma rodada segura do Executive Policy Auto Release.
    V1 não executa trades; apenas remove policies cuja condição de risco deixou de existir.
    """
    try:
        result = run_executive_policy_auto_release(context={})
        report = build_executive_policy_auto_release_report(result)
        return report, 200, {"Content-Type": "text/plain; charset=utf-8"}
    except Exception as exc:
        return (
            "🔓 EXECUTIVE POLICY AUTO RELEASE — CENTRAL QUANT\n"
            "Status: ❌\n"
            f"Erro na rota /policyautorelease: {exc}",
            500,
            {"Content-Type": "text/plain; charset=utf-8"},
        )


@app.route("/policyautoreleasehealth", methods=["GET"])
@app.route("/executive/policy/auto_release/health", methods=["GET"])
def policy_auto_release_health_route():
    """
    Health check do Auto Release.
    Não remove policies; apenas informa se o módulo carregou e o estado recente.
    """
    try:
        health = get_executive_policy_auto_release_health()
        return health, 200
    except Exception as exc:
        return {
            "ok": False,
            "module": "executive_policy_auto_release",
            "route": "/policyautoreleasehealth",
            "error": str(exc),
        }, 500



@app.route("/policypriority", methods=["GET"])
@app.route("/executive/policy/priority", methods=["GET"])
def policy_priority_route():
    """
    Executa uma rodada do Executive Policy Priority V1.
    V1 não executa trades; apenas resolve conflito entre policies ativas.
    """
    try:
        result = resolve_executive_policy_priority(trade_payload=None, commit=True)
        report = build_executive_policy_priority_report(result)
        return report, 200, {"Content-Type": "text/plain; charset=utf-8"}
    except Exception as exc:
        return (
            "🏛️ EXECUTIVE POLICY PRIORITY — CENTRAL QUANT\n"
            "Status: ❌\n"
            f"Erro na rota /policypriority: {exc}",
            500,
            {"Content-Type": "text/plain; charset=utf-8"},
        )


@app.route("/policypriorityhealth", methods=["GET"])
@app.route("/executive/policy/priority/health", methods=["GET"])
def policy_priority_health_route():
    """Health check do Priority V1."""
    try:
        return get_executive_policy_priority_health(), 200
    except Exception as exc:
        return {
            "ok": False,
            "module": "executive_policy_priority",
            "route": "/policypriorityhealth",
            "error": str(exc),
        }, 500


@app.route("/policyprioritylog", methods=["GET"])
@app.route("/executive/policy/priority/log", methods=["GET"])
def policy_priority_log_route():
    try:
        limit = int(request.args.get("limit", "20"))
    except Exception:
        limit = 20
    return read_executive_policy_priority_log(limit=limit), 200




@app.route("/policyexpiration", methods=["GET"])
@app.route("/executive/policy/expiration", methods=["GET"])
def policy_expiration_route():
    """
    Executa uma rodada segura do Executive Policy Expiration V1.
    V1 não executa trades; apenas expira policies cujo expires_at/TTL venceu.
    """
    try:
        check_only = str(request.args.get("check_only", "false")).strip().lower() in {"1", "true", "yes", "sim", "on"}
        result = run_executive_policy_expiration(context={}, commit=not check_only)
        report = build_executive_policy_expiration_report(result)
        return report, 200, {"Content-Type": "text/plain; charset=utf-8"}
    except Exception as exc:
        return (
            "⏳ EXECUTIVE POLICY EXPIRATION — CENTRAL QUANT\n"
            "Status: ❌\n"
            f"Erro na rota /policyexpiration: {exc}",
            500,
            {"Content-Type": "text/plain; charset=utf-8"},
        )


@app.route("/policyexpirationhealth", methods=["GET"])
@app.route("/executive/policy/expiration/health", methods=["GET"])
def policy_expiration_health_route():
    """Health check do Expiration V1."""
    try:
        return get_executive_policy_expiration_health(), 200
    except Exception as exc:
        return {
            "ok": False,
            "module": "executive_policy_expiration",
            "route": "/policyexpirationhealth",
            "error": str(exc),
        }, 500


@app.route("/policyexpirationlog", methods=["GET"])
@app.route("/executive/policy/expiration/log", methods=["GET"])
def policy_expiration_log_route():
    try:
        limit = int(request.args.get("limit", "20"))
    except Exception:
        limit = 20
    return read_executive_policy_expiration_log(limit=limit), 200



@app.route("/policytimeline", methods=["GET"])
@app.route("/executive/policy/timeline", methods=["GET"])
def policy_timeline_route():
    """
    Executa uma rodada do Executive Policy Timeline V1.
    V1 não executa trades e não altera policies; apenas registra eventos de governança.
    """
    try:
        check_only = str(request.args.get("check_only", "false")).strip().lower() in {"1", "true", "yes", "sim", "on"}
        try:
            limit = int(request.args.get("limit", "20"))
        except Exception:
            limit = 20
        result = sync_executive_policy_timeline(context={}, commit=not check_only)
        report = build_executive_policy_timeline_report(result, limit=limit)
        return report, 200, {"Content-Type": "text/plain; charset=utf-8"}
    except Exception as exc:
        return (
            "🧭 EXECUTIVE POLICY TIMELINE — CENTRAL QUANT\n"
            "Status: ❌\n"
            f"Erro na rota /policytimeline: {exc}",
            500,
            {"Content-Type": "text/plain; charset=utf-8"},
        )


@app.route("/policytimelinehealth", methods=["GET"])
@app.route("/executive/policy/timeline/health", methods=["GET"])
def policy_timeline_health_route():
    """Health check do Timeline V1."""
    try:
        return get_executive_policy_timeline_health(), 200
    except Exception as exc:
        return {
            "ok": False,
            "module": "executive_policy_timeline",
            "route": "/policytimelinehealth",
            "error": str(exc),
        }, 500


@app.route("/lastpolicyevents", methods=["GET"])
@app.route("/policytimeline/events", methods=["GET"])
@app.route("/executive/policy/timeline/events", methods=["GET"])
def last_policy_events_route():
    try:
        limit = int(request.args.get("limit", "20"))
    except Exception:
        limit = 20
    event_type = request.args.get("event_type")
    code = request.args.get("code")
    return read_executive_policy_timeline(limit=limit, event_type=event_type, code=code), 200


@app.route("/policytimelinestats", methods=["GET"])
@app.route("/executive/policy/timeline/stats", methods=["GET"])
def policy_timeline_stats_route():
    try:
        as_json = str(request.args.get("format", "")).strip().lower() in {"json", "raw"}
        if as_json:
            return get_executive_policy_timeline_stats(), 200
        report = build_executive_policy_timeline_stats_report()
        return report, 200, {"Content-Type": "text/plain; charset=utf-8"}
    except Exception as exc:
        return (
            "📊 EXECUTIVE POLICY TIMELINE STATS — CENTRAL QUANT\n"
            "Status: ❌\n"
            f"Erro na rota /policytimelinestats: {exc}",
            500,
            {"Content-Type": "text/plain; charset=utf-8"},
        )



@app.route("/policylearning", methods=["GET"])
@app.route("/executive/policy/learning", methods=["GET"])
def policy_learning_route():
    """
    Executa uma rodada incremental do Executive Policy Learning V1.
    Não executa trades e não altera policies.
    """
    try:
        check_only = str(request.args.get("check_only", "false")).strip().lower() in {"1", "true", "yes", "sim", "on"}
        try:
            limit = int(request.args.get("limit", "12"))
        except Exception:
            limit = 12
        result = run_executive_policy_learning(context={}, commit=not check_only)
        report = build_executive_policy_learning_report(result, limit=limit)
        return report, 200, {"Content-Type": "text/plain; charset=utf-8"}
    except Exception as exc:
        return (
            "🧠 EXECUTIVE POLICY LEARNING — CENTRAL QUANT\n"
            "Status: ❌\n"
            f"Erro na rota /policylearning: {exc}",
            500,
            {"Content-Type": "text/plain; charset=utf-8"},
        )




@app.route("/policylearningseed", methods=["GET"])
@app.route("/executive/policy/learning/seed", methods=["GET"])
def policy_learning_seed_route():
    """
    Cria eventos seed controlados para validar Executive Policy Learning.
    Não executa trades e não altera policies reais.
    """
    try:
        check_only = str(request.args.get("check_only", "false")).strip().lower() in {"1", "true", "yes", "sim", "on"}
        result = seed_executive_policy_learning_events(commit=not check_only)
        report = build_executive_policy_learning_seed_report(result)
        return report, 200, {"Content-Type": "text/plain; charset=utf-8"}
    except Exception as exc:
        return (
            "🌱 EXECUTIVE POLICY LEARNING SEED — CENTRAL QUANT\n"
            "Status: ❌\n"
            f"Erro na rota /policylearningseed: {exc}",
            500,
            {"Content-Type": "text/plain; charset=utf-8"},
        )




@app.route("/policyeffect", methods=["GET"])
@app.route("/executive/policy/learning/effect", methods=["GET"])
def policy_effect_route():
    """
    Executive Policy Learning V2.1.2.
    Correlaciona Executive Policy Timeline + Decision Log.
    """
    try:
        check_only = str(request.args.get("check_only", "false")).strip().lower() in {"1", "true", "yes", "sim", "on"}
        try:
            limit = int(request.args.get("limit", "12"))
        except Exception:
            limit = 12
        result = run_executive_policy_learning_v2(context={}, commit=not check_only)
        report = build_executive_policy_effect_report(result, limit=limit)
        return report, 200, {"Content-Type": "text/plain; charset=utf-8"}
    except Exception as exc:
        return (
            "🧠 EXECUTIVE POLICY LEARNING V2.1.2 — POLICY EFFECT\n"
            "Status: ❌\n"
            f"Erro na rota /policyeffect: {exc}",
            500,
            {"Content-Type": "text/plain; charset=utf-8"},
        )






@app.route("/policyeffectseed", methods=["GET"])
@app.route("/executive/policy/learning/effect/seed", methods=["GET"])
def policy_effect_seed_route():
    """
    Cria uma decisão seed para validar match Policy Timeline + Decision Log.
    Não executa trades e não altera policies reais.
    """
    try:
        check_only = str(request.args.get("check_only", "false")).strip().lower() in {"1", "true", "yes", "sim", "on"}
        result = seed_policy_effect_decision(commit=not check_only)
        report = build_policy_effect_seed_report(result)
        return report, 200, {"Content-Type": "text/plain; charset=utf-8"}
    except Exception as exc:
        return (
            "🌱 POLICY EFFECT DECISION SEED — CENTRAL QUANT V2.1.2\n"
            "Status: ❌\n"
            f"Erro na rota /policyeffectseed: {exc}",
            500,
            {"Content-Type": "text/plain; charset=utf-8"},
        )


@app.route("/policyeffectrebuild", methods=["GET"])
@app.route("/executive/policy/learning/effect/rebuild", methods=["GET"])
def policy_effect_rebuild_route():
    """
    Rebuild completo da correlação Policy Timeline + Decision Log.
    Não executa trades e não altera policies reais.
    """
    try:
        check_only = str(request.args.get("check_only", "false")).strip().lower() in {"1", "true", "yes", "sim", "on"}
        try:
            max_decisions = int(request.args.get("max_decisions", "700"))
        except Exception:
            max_decisions = 700
        result = rebuild_executive_policy_effect(commit=not check_only, max_decisions=max_decisions)
        report = build_policy_effect_rebuild_report(result)
        return report, 200, {"Content-Type": "text/plain; charset=utf-8"}
    except Exception as exc:
        return (
            "♻️ POLICY EFFECT REBUILD — CENTRAL QUANT V2.1.2\n"
            "Status: ❌\n"
            f"Erro na rota /policyeffectrebuild: {exc}",
            500,
            {"Content-Type": "text/plain; charset=utf-8"},
        )


@app.route("/policyeffecthealth", methods=["GET"])
@app.route("/executive/policy/learning/effect/health", methods=["GET"])
def policy_effect_health_route():
    try:
        return get_executive_policy_learning_v2_health(), 200
    except Exception as exc:
        return {
            "ok": False,
            "module": "executive_policy_learning_v2",
            "route": "/policyeffecthealth",
            "error": str(exc),
        }, 500




@app.route("/realpnlr/health", methods=["GET"])
def real_pnl_r_health_route():
    """
    Health check do Real PnL/R Mapper V2.4.
    Observacional: não executa ordens, não altera lotes e não muda risco real.
    """
    try:
        return {
            "ok": True,
            "module": "real_pnl_r_mapper",
            "available": REAL_PNL_R_MAPPER_AVAILABLE,
            "import_error": REAL_PNL_R_MAPPER_IMPORT_ERROR,
            "version": getattr(real_pnl_r_mapper, "VERSION", "unavailable") if REAL_PNL_R_MAPPER_AVAILABLE else "unavailable",
            "mode": "OBSERVATION_ONLY",
            "notes": [
                "V2.4 mapeia PnL real e R real de trades encerrados.",
                "Não executa ordens, não altera lotes e não muda risco real.",
            ],
        }, 200
    except Exception as exc:
        return {
            "ok": False,
            "module": "real_pnl_r_mapper",
            "route": "/realpnlr/health",
            "error": str(exc),
        }, 500


@app.route("/realpnlr", methods=["GET"])
def real_pnl_r_dashboard_route():
    """
    Dashboard JSON do Real PnL/R Mapper V2.4.
    commit=true grava o snapshot/mapa em arquivo; commit=false roda apenas leitura.
    """
    try:
        if not REAL_PNL_R_MAPPER_AVAILABLE:
            return {
                "ok": False,
                "module": "real_pnl_r_mapper",
                "available": False,
                "error": REAL_PNL_R_MAPPER_IMPORT_ERROR,
            }, 500

        commit = str(request.args.get("commit", "true")).strip().lower() in {"1", "true", "yes", "sim", "on"}
        try:
            limit = int(request.args.get("limit", "5000"))
        except Exception:
            limit = 5000

        return real_pnl_r_mapper.build_real_pnl_r_map(limit=limit, commit=commit), 200
    except Exception as exc:
        return {
            "ok": False,
            "module": "real_pnl_r_mapper",
            "route": "/realpnlr",
            "error": str(exc),
        }, 500


@app.route("/realpnlr/text", methods=["GET"])
def real_pnl_r_text_route():
    """
    Relatório textual do Real PnL/R Mapper V2.4.
    Ideal para Telegram/validação rápida após deploy.
    """
    try:
        if not REAL_PNL_R_MAPPER_AVAILABLE:
            text = "❌ Real PnL/R Mapper indisponível: " + str(REAL_PNL_R_MAPPER_IMPORT_ERROR)
            return {"ok": False, "text": text}, 500

        commit = str(request.args.get("commit", "true")).strip().lower() in {"1", "true", "yes", "sim", "on"}
        try:
            limit = int(request.args.get("limit", "5000"))
        except Exception:
            limit = 5000

        payload = real_pnl_r_mapper.build_real_pnl_r_map(limit=limit, commit=commit)
        return {
            "ok": True,
            "text": real_pnl_r_mapper.build_real_pnl_r_text(payload),
            "payload": payload,
        }, 200
    except Exception as exc:
        return {
            "ok": False,
            "module": "real_pnl_r_mapper",
            "route": "/realpnlr/text",
            "error": str(exc),
        }, 500


@app.route("/policyperformance", methods=["GET"])
@app.route("/executive/policy/learning/performance", methods=["GET"])
def policy_performance_route():
    try:
        as_text = str(request.args.get("format", "")).strip().lower() in {"text", "txt", "1", "true"}
        if as_text:
            return build_executive_policy_effect_report(result=None), 200, {"Content-Type": "text/plain; charset=utf-8"}
        return get_executive_policy_effect_stats(), 200
    except Exception as exc:
        return {
            "ok": False,
            "module": "executive_policy_learning_v2",
            "route": "/policyperformance",
            "error": str(exc),
        }, 500


@app.route("/policycompare", methods=["GET"])
@app.route("/executive/policy/learning/compare", methods=["GET"])
def policy_compare_route():
    try:
        try:
            limit = int(request.args.get("limit", "10"))
        except Exception:
            limit = 10
        return build_policy_compare_report(limit=limit), 200, {"Content-Type": "text/plain; charset=utf-8"}
    except Exception as exc:
        return (
            "⚖️ POLICY COMPARE — CENTRAL QUANT V2.1.2\n"
            f"Erro na rota /policycompare: {exc}",
            500,
            {"Content-Type": "text/plain; charset=utf-8"},
        )


@app.route("/policyinsights", methods=["GET"])
@app.route("/executive/policy/learning/insights", methods=["GET"])
def policy_insights_route():
    try:
        return build_policy_insights_report(), 200, {"Content-Type": "text/plain; charset=utf-8"}
    except Exception as exc:
        return (
            "💡 POLICY INSIGHTS — CENTRAL QUANT V2.1.2\n"
            f"Erro na rota /policyinsights: {exc}",
            500,
            {"Content-Type": "text/plain; charset=utf-8"},
        )


@app.route("/policylearninghealth", methods=["GET"])
@app.route("/executive/policy/learning/health", methods=["GET"])
def policy_learning_health_route():
    try:
        return get_executive_policy_learning_health(), 200
    except Exception as exc:
        return {
            "ok": False,
            "module": "executive_policy_learning",
            "route": "/policylearninghealth",
            "error": str(exc),
        }, 500


@app.route("/policystats", methods=["GET"])
@app.route("/executive/policy/learning/stats", methods=["GET"])
def policy_learning_stats_route():
    try:
        as_text = str(request.args.get("format", "")).strip().lower() in {"text", "txt", "1", "true"}
        if as_text:
            return build_executive_policy_learning_report(result=None), 200, {"Content-Type": "text/plain; charset=utf-8"}
        return get_executive_policy_learning_stats(), 200
    except Exception as exc:
        return {
            "ok": False,
            "module": "executive_policy_learning",
            "route": "/policystats",
            "error": str(exc),
        }, 500


@app.route("/policyranking", methods=["GET"])
@app.route("/executive/policy/learning/ranking", methods=["GET"])
def policy_learning_ranking_route():
    try:
        try:
            limit = int(request.args.get("limit", "15"))
        except Exception:
            limit = 15
        stats = get_executive_policy_learning_stats()
        policies = stats.get("policies") or {}
        ranking = sorted(
            [p for p in policies.values() if isinstance(p, dict)],
            key=lambda p: (float(p.get("score") or 0), float(p.get("confidence_pct") or 0), int(p.get("events") or 0)),
            reverse=True,
        )[:limit]
        return {
            "ok": True,
            "module": "executive_policy_learning",
            "version": stats.get("version"),
            "generated_at": data_hora_sp_str(),
            "ranking": ranking,
            "summary": stats.get("summary") or {},
        }, 200
    except Exception as exc:
        return {
            "ok": False,
            "module": "executive_policy_learning",
            "route": "/policyranking",
            "error": str(exc),
        }, 500


@app.route("/policyhistory", methods=["GET"])
@app.route("/executive/policy/learning/history", methods=["GET"])
def policy_learning_history_route():
    try:
        code = request.args.get("code") or request.args.get("policy") or ""
        if not code:
            return (
                "🧠 POLICY HISTORY — CENTRAL QUANT\n"
                "Informe a policy com ?code=WAIT_SAMPLE",
                400,
                {"Content-Type": "text/plain; charset=utf-8"},
            )
        return build_policy_history_report(code), 200, {"Content-Type": "text/plain; charset=utf-8"}
    except Exception as exc:
        return (
            "🧠 POLICY HISTORY — CENTRAL QUANT\n"
            f"Erro na rota /policyhistory: {exc}",
            500,
            {"Content-Type": "text/plain; charset=utf-8"},
        )


@app.route("/policylearninglog", methods=["GET"])
@app.route("/executive/policy/learning/log", methods=["GET"])
def policy_learning_log_route():
    try:
        try:
            limit = int(request.args.get("limit", "20"))
        except Exception:
            limit = 20
        return read_executive_policy_learning_log(limit=limit), 200
    except Exception as exc:
        return {
            "ok": False,
            "module": "executive_policy_learning",
            "route": "/policylearninglog",
            "error": str(exc),
        }, 500


@app.route("/executive/alerts/check")
@app.route("/executive_alerts/check")
def executive_alerts_check_route():
    check_only = str(request.args.get("check_only", "false")).strip().lower() in {"1", "true", "yes", "sim", "on"}
    return build_executive_alerts(check_only=check_only)


@app.route("/executive/alerts")
@app.route("/executive_alerts")
def executive_alerts_route():
    notify_only = str(request.args.get("notify_only", "false")).strip().lower() in {"1", "true", "yes", "sim", "on"}
    try:
        limit = int(request.args.get("limit", "10"))
    except Exception:
        limit = 10
    return build_executive_alerts_text(limit=limit, notify_only=notify_only)


@app.route("/executive/alerts/log")
@app.route("/executive_alerts/log")
def executive_alerts_log_route():
    try:
        limit = int(request.args.get("limit", "20"))
    except Exception:
        limit = 20
    return read_executive_alert_log(limit=limit)


@app.route("/execution/pipeline/status")
@app.route("/execution_pipeline/status")
def execution_pipeline_status_route():
    as_text = str(request.args.get("format", "")).strip().lower() in {"text", "txt", "1", "true"}
    if as_text:
        return build_execution_pipeline_text()
    return build_execution_pipeline_status()


@app.route("/adaptive/health")
@app.route("/adaptive_weights/health")
def adaptive_weights_health_route():
    return adaptive_weights_health()


@app.route("/adaptive/build")
@app.route("/adaptive_weights/build")
def adaptive_weights_build_route():
    commit = str(request.args.get("commit", "true")).strip().lower() in {"1", "true", "yes", "sim", "on"}
    return build_adaptive_weights(commit=commit)


@app.route("/adaptive/weights")
@app.route("/adaptive_weights")
def adaptive_weights_route():
    as_text = str(request.args.get("format", "")).strip().lower() in {"text", "txt", "1", "true"}
    if as_text:
        return build_adaptive_weights_text()
    return get_adaptive_weights()


@app.route("/adaptive/log")
@app.route("/adaptive_weights/log")
def adaptive_weights_log_route():
    try:
        limit = int(request.args.get("limit", "20"))
    except Exception:
        limit = 20
    return read_adaptive_weights_log(limit=limit)


@app.route("/outcome/health")
@app.route("/outcome_evaluator/health")
def outcome_evaluator_health_route():
    return outcome_evaluator_health()


@app.route("/outcome/evaluate")
@app.route("/outcome_evaluator/evaluate")
def outcome_evaluator_evaluate_route():
    force = str(request.args.get("force", "false")).strip().lower() in {"1", "true", "yes", "sim", "on"}
    return evaluate_closed_paper_trades(force=force)


@app.route("/outcome/stats")
@app.route("/outcome_evaluator/stats")
def outcome_evaluator_stats_route():
    return get_outcome_stats()


@app.route("/outcome/log")
@app.route("/outcome_evaluator/log")
def outcome_evaluator_log_route():
    try:
        limit = int(request.args.get("limit", "20"))
    except Exception:
        limit = 20
    return read_outcome_log(limit=limit)


@app.route("/paper_lifecycle/health")
@app.route("/paper/lifecycle/health")
def paper_lifecycle_health_route():
    return paper_lifecycle_health()


@app.route("/paper_lifecycle/positions")
@app.route("/paper/lifecycle/positions")
def paper_lifecycle_positions_route():
    status = request.args.get("status")
    return get_paper_lifecycle_positions(status=status)


@app.route("/paper_lifecycle/update", methods=["GET", "POST"])
@app.route("/paper/lifecycle/update", methods=["GET", "POST"])
def paper_lifecycle_update_route():
    payload = request.get_json(silent=True) or {}

    trade_id = payload.get("trade_id") or request.args.get("trade_id")
    symbol = payload.get("symbol") or request.args.get("symbol")
    price = payload.get("price") or request.args.get("price")
    close_raw = payload.get("close", request.args.get("close", "false"))
    close = str(close_raw).strip().lower() in {"1", "true", "yes", "sim", "on"}
    close_reason = payload.get("close_reason") or request.args.get("close_reason")

    return update_paper_position_price(
        trade_id=trade_id,
        symbol=symbol,
        price=price,
        close=close,
        close_reason=close_reason,
    )


@app.route("/paper_lifecycle/log")
@app.route("/paper/lifecycle/log")
def paper_lifecycle_log_route():
    try:
        limit = int(request.args.get("limit", "20"))
    except Exception:
        limit = 20
    return read_paper_lifecycle_log(limit=limit)


@app.route("/paper_lifecycle/test_tp50")
@app.route("/paper/lifecycle/test_tp50")
def paper_lifecycle_test_tp50_route():
    return paper_lifecycle_test_tp50()


@app.route("/paper_lifecycle/test_close")
@app.route("/paper/lifecycle/test_close")
def paper_lifecycle_test_close_route():
    return paper_lifecycle_test_close()


@app.route("/execution_engine/health")
@app.route("/execution/engine/health")
def execution_engine_health_route():
    return execution_engine_health()


@app.route("/execution_engine/run", methods=["GET", "POST"])
@app.route("/execution/engine/run", methods=["GET", "POST"])
def execution_engine_run_route():
    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
    else:
        payload = {key: value for key, value in request.args.items()}

    url_mode = request.args.get("mode")

    if not payload:
        payload = {
            "decision": "ALLOW",
            "bot": "DONKEY",
            "setup": "DONKEY",
            "symbol": "ETHUSDT",
            "side": "LONG",
            "entry": 3501,
            "sl": 3431,
            "tp50": 3571,
            "risk_pct": 2.0,
            "capital_allocated": 4500,
            "requested_qty": 0.1,
            "signal_id": f"EXECUTION-ENGINE-MANUAL-TEST-{int(time.time())}",
        }

    # Em chamadas GET, normalmente enviamos bot/symbol/side/entry/etc.,
    # mas não enviamos decision. O Execution Engine exige uma decisão executável.
    # A policy é avaliada antes; se ela permitir, usamos ALLOW para seguir ao plano.
    payload.setdefault("decision", "ALLOW")

    # Executive Policy Manager gate — última trava antes do Execution Engine.
    # Protege chamadas diretas ao executor, mesmo se o Risk Manager ou o
    # Execution Orchestrator não tiverem sido chamados antes.
    policy_reasons = []
    policy_warnings = []
    executive_policy_eval = _apply_executive_policy_to_risk_reasons(
        trade_payload=payload,
        reasons=policy_reasons,
        warnings=policy_warnings,
    )

    if isinstance(executive_policy_eval, dict) and not executive_policy_eval.get("allowed", True):
        blocked_payload = dict(payload or {})
        blocked_payload["decision"] = "DENY"
        blocked_payload["blocked_by"] = "EXECUTIVE_POLICY_MANAGER"
        blocked_payload["executive_policy"] = executive_policy_eval

        return {
            "ok": True,
            "mode": url_mode or payload.get("mode") or "VERIFY",
            "dry_run": True,
            "decision": "DENY",
            "allowed": False,
            "status": "BLOCKED_BY_EXECUTIVE_POLICY",
            "blocked_by": "EXECUTIVE_POLICY_MANAGER",
            "executive_policy": executive_policy_eval,
            "reasons": policy_reasons or executive_policy_eval.get("reasons") or ["Bloqueado por política executiva ativa."],
            "warnings": policy_warnings or executive_policy_eval.get("warnings") or [],
            "payload": blocked_payload,
            "notes": [
                "Execution Engine protegido pelo Executive Policy Manager.",
                "Nenhuma chamada a run_execution_engine foi feita porque a política executiva bloqueou a trade.",
            ],
        }

    if isinstance(executive_policy_eval, dict):
        payload["executive_policy"] = executive_policy_eval

    engine_result = run_execution_engine(
        payload=payload,
        mode=url_mode or payload.get("mode"),
        dry_run=True,
    )

    if isinstance(engine_result, dict):
        engine_result.setdefault("executive_policy", executive_policy_eval)
        engine_result.setdefault("policy_gate", {
            "checked": True,
            "allowed": True,
            "source": "executive_policy_manager",
            "warnings": policy_warnings,
        })

    return engine_result


@app.route("/execution_engine/test")
@app.route("/execution/engine/test")
def execution_engine_test_route():
    return execution_engine_test()


@app.route("/execution_engine/log")
@app.route("/execution/engine/log")
def execution_engine_log_route():
    try:
        limit = int(request.args.get("limit", "20"))
    except Exception:
        limit = 20
    return read_execution_engine_log(limit=limit)


@app.route("/paper_integrated/health")
@app.route("/paper/integrated/health")
def paper_integrated_health_route():
    return paper_integrated_health()


@app.route("/paper_integrated/open")
@app.route("/paper/integrated/open")
def paper_integrated_open_route():
    return get_paper_integrated_open_positions()


@app.route("/paper_integrated/log")
@app.route("/paper/integrated/log")
def paper_integrated_log_route():
    try:
        limit = int(request.args.get("limit", "20"))
    except Exception:
        limit = 20
    return read_paper_integrated_log(limit=limit)


@app.route("/history/hooks/status")
def history_hooks_status_route():
    """Diagnóstico simples para confirmar se os hooks do History foram instalados."""
    try:
        import history_manager as super_history_manager
        history_loaded = True
        history_error = None
    except Exception as exc:
        super_history_manager = None
        history_loaded = False
        history_error = str(exc)

    append_decision = globals().get("append_decision_log")
    append_timeline = globals().get("append_timeline_event")

    return {
        "ok": bool(history_loaded),
        "history_manager_loaded": history_loaded,
        "history_manager_error": history_error,
        "append_decision_log_exists": callable(append_decision),
        "append_decision_log_wrapped": bool(getattr(append_decision, "_history_wrapped", False)),
        "append_timeline_event_exists": callable(append_timeline),
        "append_timeline_event_wrapped": bool(getattr(append_timeline, "_history_wrapped", False)),
        "build_history_report_source": str(globals().get("build_history_report")),
    }



@app.route("/data/status")
def data_status_route():
    """Diagnóstico dos caminhos usados por Main, Event Bus e History."""
    payload = {
        "ok": True,
        "pid": os.getpid(),
        "cwd": os.getcwd(),
        "base_dir": str(BASE_DIR),
        "central_data_dir": str(CENTRAL_DATA_DIR),
        "main_files": {
            "decision_log": str(CENTRAL_DECISION_LOG_FILE),
            "timeline": str(CENTRAL_TIMELINE_LOG_FILE),
            "shadow_positions": str(CENTRAL_SHADOW_POSITIONS_FILE),
            "execution_stats": str(CENTRAL_EXECUTION_STATS_FILE),
        },
        "locks": {
            "held_by_this_process": list(CENTRAL_PROCESS_LOCK_HANDLES.keys()),
            "lock_files": [str(p) for p in CENTRAL_DATA_DIR.glob("*.lock")],
        },
        "event_bus": None,
        "history_manager": None,
    }
    try:
        if central_event_bus is not None:
            payload["event_bus"] = {
                "data_dir": str(getattr(central_event_bus, "DATA_DIR", "")),
                "event_bus_log_file": str(getattr(central_event_bus, "EVENT_BUS_LOG_FILE", "")),
                "event_bus_seen_file": str(getattr(central_event_bus, "EVENT_BUS_SEEN_FILE", "")),
                "history_manager_loaded": getattr(central_event_bus, "history_manager", None) is not None,
            }
    except Exception as exc:
        payload["event_bus"] = {"error": str(exc)}
    try:
        import history_manager as super_history_manager
        payload["history_manager"] = {
            "data_dir": str(getattr(super_history_manager, "DATA_DIR", "")),
            "history_events": str(getattr(super_history_manager, "HISTORY_EVENTS_FILE", "")),
            "decision_log": str(getattr(super_history_manager, "DECISION_LOG_FILE", "")),
            "timeline": str(getattr(super_history_manager, "TIMELINE_LOG_FILE", "")),
            "export": str(getattr(super_history_manager, "HISTORY_EXPORT_FILE", "")),
        }
    except Exception as exc:
        payload["history_manager"] = {"error": str(exc)}
    return payload


@app.route("/traderegistry")
@app.route("/trade_registry")
@app.route("/trades")
def trade_registry_route():
    full = str(request.args.get("full", "true")).strip().lower() in {"1", "true", "yes", "sim", "on"}
    return central_trade_registry_snapshot(include_trades=full)


def _trade_registry_report_iter_trades(values):
    """Normaliza open_trades/closed_trades vindos como lista ou dict."""
    if isinstance(values, dict):
        iterable = values.values()
    elif isinstance(values, list):
        iterable = values
    else:
        iterable = []
    return [item for item in iterable if isinstance(item, dict)]


def _trade_registry_report_count(items, key):
    out = {}
    for item in items:
        value = item.get(key)
        if value is None and key == "symbol":
            value = item.get("symbol_clean")
        if value is None:
            value = "N/A"
        value = str(value).upper().strip() or "N/A"
        out[value] = out.get(value, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: (-kv[1], kv[0])))


def _trade_registry_report_duplicates(items):
    seen = {}
    duplicates = []
    for item in items:
        trade_id = str(item.get("trade_id") or "").strip()
        if not trade_id:
            continue
        if trade_id in seen:
            duplicates.append(trade_id)
        seen[trade_id] = True
    return sorted(set(duplicates))


def _trade_registry_report_integrity(open_trades, closed_trades):
    required = ["trade_id", "bot", "symbol", "side", "setup", "entry"]
    problems = []
    for status_name, trades in [("OPEN", open_trades), ("CLOSED", closed_trades)]:
        for item in trades:
            missing = [field for field in required if item.get(field) in [None, ""]]
            if missing:
                problems.append({
                    "status": status_name,
                    "trade_id": item.get("trade_id"),
                    "bot": item.get("bot"),
                    "symbol": item.get("symbol"),
                    "missing": missing,
                })
    total = len(open_trades) + len(closed_trades)
    ok_count = max(0, total - len(problems))
    score = round((ok_count / total) * 100, 2) if total else 100.0
    return {"score": score, "problems": problems[:100], "problems_count": len(problems)}


def _trade_registry_report_conflicts(open_trades):
    by_symbol = {}
    for item in open_trades:
        symbol = str(item.get("symbol") or item.get("symbol_clean") or "N/A").upper().strip()
        by_symbol.setdefault(symbol, []).append(item)

    opposite_side = []
    multi_bot = []
    concentration = []

    try:
        max_symbol_exposure = int(GLOBAL_RISK_MAX_SYMBOL_EXPOSURE)
    except Exception:
        max_symbol_exposure = 3

    for symbol, trades in sorted(by_symbol.items()):
        sides = sorted({str(t.get("side") or "").upper() for t in trades if t.get("side")})
        bots = sorted({str(t.get("bot") or "").upper() for t in trades if t.get("bot")})
        if "LONG" in sides and "SHORT" in sides:
            opposite_side.append({"symbol": symbol, "count": len(trades), "sides": sides, "bots": bots})
        if len(bots) > 1:
            multi_bot.append({"symbol": symbol, "count": len(trades), "bots": bots, "sides": sides})
        if len(trades) >= max_symbol_exposure:
            concentration.append({"symbol": symbol, "count": len(trades), "limit": max_symbol_exposure, "bots": bots, "sides": sides})

    return {
        "opposite_side": opposite_side,
        "multi_bot": multi_bot,
        "concentration": concentration,
    }


def build_trade_registry_report():
    """Relatório humano do Trade Registry central."""
    snap = central_trade_registry_snapshot(include_trades=True)
    open_trades = _trade_registry_report_iter_trades(snap.get("open_trades", []))
    closed_trades = _trade_registry_report_iter_trades(snap.get("closed_trades", []))

    by_bot = snap.get("by_bot") or _trade_registry_report_count(open_trades, "bot")
    by_symbol = snap.get("by_symbol") or _trade_registry_report_count(open_trades, "symbol")
    by_side = snap.get("by_side") or _trade_registry_report_count(open_trades, "side")
    by_setup = _trade_registry_report_count(open_trades, "setup")
    duplicates = _trade_registry_report_duplicates(open_trades + closed_trades)
    integrity = _trade_registry_report_integrity(open_trades, closed_trades)
    conflicts = _trade_registry_report_conflicts(open_trades)

    open_count = int(snap.get("open_count", len(open_trades)) or 0)
    closed_count = int(snap.get("closed_count", len(closed_trades)) or 0)
    total = open_count + closed_count

    def _top_lines(title, data, limit=10):
        lines = [title]
        if not data:
            lines.append("N/A")
            return lines
        for key, value in list(data.items())[:limit]:
            lines.append(f"- {key}: {value}")
        return lines

    long_count = int(by_side.get("LONG", 0) or 0)
    short_count = int(by_side.get("SHORT", 0) or 0)
    dominant_side = "LONG" if long_count >= short_count else "SHORT"
    dominant_qty = max(long_count, short_count)
    dominant_pct = round((dominant_qty / open_count) * 100, 2) if open_count else 0.0

    lines = [
        "📒 TRADE REGISTRY — CENTRAL QUANT",
        f"Data/hora: {data_hora_sp_str()}",
        "",
        "Resumo:",
        f"- OK: {snap.get('ok')}",
        f"- Carregado: {snap.get('loaded')}",
        f"- Trades abertos: {open_count}",
        f"- Trades fechados: {closed_count}",
        f"- Total registrado: {total}",
        f"- Integridade: {integrity.get('score')}%",
        "",
        "Direção:",
        f"- LONG: {long_count}",
        f"- SHORT: {short_count}",
        f"- Lado dominante: {dominant_side} ({dominant_pct}%)",
        "",
    ]
    lines += _top_lines("Por robô:", by_bot, limit=12)
    lines += [""]
    lines += _top_lines("Por setup:", by_setup, limit=12)
    lines += [""]
    lines += _top_lines("Maior exposição por ativo:", by_symbol, limit=15)
    lines += [""]

    lines += ["Conflitos e alertas:"]
    if not duplicates and not conflicts["opposite_side"] and not conflicts["concentration"] and not integrity["problems_count"]:
        lines.append("- Nenhum alerta crítico encontrado ✅")
    else:
        if duplicates:
            lines.append(f"- Trade IDs duplicados: {len(duplicates)}")
        if conflicts["opposite_side"]:
            lines.append(f"- Ativos com LONG e SHORT simultâneos: {len(conflicts['opposite_side'])}")
            for item in conflicts["opposite_side"][:8]:
                lines.append(f"  • {item['symbol']}: {item['count']} posições | {','.join(item['sides'])} | bots={','.join(item['bots'])}")
        if conflicts["multi_bot"]:
            lines.append(f"- Ativos operados por mais de um robô: {len(conflicts['multi_bot'])}")
            for item in conflicts["multi_bot"][:8]:
                lines.append(f"  • {item['symbol']}: {item['count']} posições | bots={','.join(item['bots'])}")
        if conflicts["concentration"]:
            lines.append(f"- Ativos no limite/acima do limite por ativo: {len(conflicts['concentration'])}")
            for item in conflicts["concentration"][:8]:
                lines.append(f"  • {item['symbol']}: {item['count']}/{item['limit']} posições")
        if integrity["problems_count"]:
            lines.append(f"- Trades com campos ausentes: {integrity['problems_count']}")

    lines += [
        "",
        "Arquivos:",
        f"- Registry: {snap.get('trade_registry_file')}",
        f"- Data dir: {snap.get('data_dir')}",
    ]

    payload = {
        "ok": bool(snap.get("ok", True)) and integrity.get("score", 0) >= 90 and not duplicates,
        "updated_at": data_hora_sp_str(),
        "open_count": open_count,
        "closed_count": closed_count,
        "by_bot": by_bot,
        "by_side": by_side,
        "by_symbol": by_symbol,
        "by_setup": by_setup,
        "dominant_side": dominant_side,
        "dominant_side_pct": dominant_pct,
        "duplicates": duplicates,
        "integrity": integrity,
        "conflicts": conflicts,
        "text": "\n".join(lines),
    }
    return payload


@app.route("/traderegistry/report")
@app.route("/trade_registry/report")
@app.route("/trades/report")
def trade_registry_report_route():
    report = build_trade_registry_report()
    as_text = str(request.args.get("format", request.args.get("text", ""))).strip().lower() in {"1", "true", "yes", "sim", "on", "text", "txt"}
    if as_text:
        return report.get("text", "")
    return report


def _trade_registry_sync_symbol(symbol):
    s = str(symbol or "").upper().strip()
    s = s.replace("/USDT:USDT", "USDT").replace("/USDT", "USDT").replace(":USDT", "")
    return s


def normalize_registry_symbol(symbol):
    s = str(symbol or "").upper().strip()
    s = s.replace("/USDT:USDT", "USDT")
    s = s.replace("/USDT", "USDT")
    s = s.replace(":USDT", "")
    s = s.replace("-", "")
    return s


def normalize_registry_bot(bot):
    b = str(bot or "").upper().strip()
    aliases = {
        "FALCON STRIKE": "FALCON",
        "SMART PREDATOR": "PREDATOR",
        "SMART_PREDATOR": "PREDATOR",
        "TREND PRO": "TRENDPRO",
        "TREND PRO ELITE": "TRENDPRO",
        "MEME HUNTER": "MEME",
        "COBRA ATTACK": "COBRA",
        "DONKEY H4": "DONKEY",
    }
    return aliases.get(b, b)


def _trade_registry_sync_side(position):
    side = str(
        position.get("side")
        or position.get("signal")
        or position.get("direction")
        or ""
    ).upper().strip()
    if side == "BUY":
        return "LONG"
    if side == "SELL":
        return "SHORT"
    return side


def _trade_registry_sync_setup(bot_key, position):
    setup = (
        position.get("setup")
        or position.get("signal_type")
        or position.get("setup_label")
        or position.get("origin")
        or position.get("origem")
        or bot_key
    )
    return str(setup or bot_key).upper().strip()


def _trade_registry_sync_entry(position):
    return (
        position.get("entry")
        or position.get("entrada")
        or position.get("entry_price")
        or position.get("price")
    )


def _trade_registry_sync_sl(position):
    return (
        position.get("sl")
        or position.get("stop")
        or position.get("initial_stop")
        or position.get("stop_atual")
        or position.get("current_stop")
    )


def _trade_registry_sync_qty(position):
    return (
        position.get("qty")
        or position.get("amount")
        or position.get("quantity")
        or position.get("position_size")
    )


def _trade_registry_existing_trade_ids():
    ids = set()
    if central_trade_registry is None:
        return ids

    try:
        registry = central_trade_registry.load_registry()
    except Exception:
        registry = None

    try:
        if isinstance(registry, dict):
            for section in ["open_trades", "closed_trades"]:
                values = registry.get(section, {})
                if isinstance(values, dict):
                    iterable = values.values()
                elif isinstance(values, list):
                    iterable = values
                else:
                    iterable = []
                for item in iterable:
                    if isinstance(item, dict) and item.get("trade_id"):
                        ids.add(str(item.get("trade_id")))
                    elif isinstance(item, str):
                        ids.add(item)
    except Exception:
        pass

    try:
        snapshot = central_trade_registry.get_trade_registry_snapshot()
        if isinstance(snapshot, dict):
            for section in ["open_trades", "closed_trades"]:
                values = snapshot.get(section, [])
                if isinstance(values, dict):
                    iterable = values.values()
                elif isinstance(values, list):
                    iterable = values
                else:
                    iterable = []
                for item in iterable:
                    if isinstance(item, dict) and item.get("trade_id"):
                        ids.add(str(item.get("trade_id")))
    except Exception:
        pass

    return ids


def _trade_registry_sync_candidate(bot_key, position):
    symbol = _trade_registry_sync_symbol(
        position.get("symbol") or position.get("ativo") or position.get("pair")
    )
    side = _trade_registry_sync_side(position)
    setup = _trade_registry_sync_setup(bot_key, position)
    entry = _trade_registry_sync_entry(position)

    if not symbol or side not in {"LONG", "SHORT"} or entry is None:
        return None

    try:
        trade_id = central_trade_registry.make_trade_id(bot_key, symbol, side, setup)
    except Exception:
        trade_id = f"{bot_key}:{symbol}:{side}:{setup}"

    return {
        "trade_id": trade_id,
        "bot": bot_key,
        "symbol": symbol,
        "side": side,
        "setup": setup,
        "entry": entry,
        "sl": _trade_registry_sync_sl(position),
        "tp50": position.get("tp50"),
        "qty": _trade_registry_sync_qty(position),
        "source": "main_traderegistry_sync",
        "metadata": {
            "synced_from": "central_open_positions",
            "synced_at": data_hora_sp_str(),
            "original_symbol": position.get("symbol") or position.get("ativo") or position.get("pair"),
            "position_id": position.get("id") or position.get("position_id"),
            "status": position.get("status", "OPEN"),
            "created_at": position.get("created_at") or position.get("opened_at") or position.get("datetime"),
            "risk_pct": position.get("risk_pct"),
            "score": position.get("score") or position.get("score_turtle") or position.get("score_falcon") or position.get("signal_score") or position.get("meme_score"),
            "quality": position.get("quality") or position.get("qualidade"),
            "runner_r": _position_runner_r(position),
            "runner_pct": _position_runner_pct(position),
            "mfe_pct": position.get("mfe_pct"),
            "mae_pct": position.get("mae_pct"),
            "mfe_r": position.get("mfe_r"),
            "mae_r": position.get("mae_r"),
        },
    }


def _trade_registry_signature_from_items(items):
    signature = set()

    if isinstance(items, dict):
        iterable = items.values()
    elif isinstance(items, list):
        iterable = items
    else:
        iterable = []

    for item in iterable:
        if not isinstance(item, dict):
            continue

        bot = normalize_registry_bot(item.get("bot") or "UNKNOWN")
        symbol = normalize_registry_symbol(
            item.get("symbol_clean")
            or item.get("symbol")
            or item.get("ativo")
            or item.get("pair")
            or "UNKNOWN"
        )
        side = str(item.get("side") or item.get("direction") or "UNKNOWN").upper().strip()
        if side == "BUY":
            side = "LONG"
        elif side == "SELL":
            side = "SHORT"

        setup = str(
            item.get("setup")
            or item.get("signal_type")
            or item.get("setup_label")
            or item.get("origin")
            or "DEFAULT"
        ).upper().strip()

        signature.add(f"{bot}:{setup}:{symbol}:{side}")

    return signature


def _trade_registry_signature_map(items):
    out = {}

    if isinstance(items, dict):
        iterable = items.values()
    elif isinstance(items, list):
        iterable = items
    else:
        iterable = []

    for item in iterable:
        if not isinstance(item, dict):
            continue

        sig = _trade_registry_signature_from_items([item])
        key = next(iter(sig), None)
        if key:
            out[key] = item

    return out


def mark_registry_missing_trades(removed):
    if central_trade_registry is None:
        return {"ok": False, "error": "trade_registry unavailable"}

    if not removed:
        return {"ok": True, "marked_count": 0, "marked": []}

    try:
        registry = central_trade_registry.load_registry()
        open_trades = registry.get("open_trades", {})

        if not isinstance(open_trades, dict):
            return {"ok": False, "error": "open_trades is not dict"}

        marked = []

        for item in removed:
            trade_id = item.get("trade_id")
            if not trade_id or trade_id not in open_trades:
                continue

            trade = open_trades[trade_id]
            trade["status"] = "MISSING_FROM_BOTS"
            trade["missing_from_bots"] = True
            trade["missing_detected_at"] = data_hora_sp_str()
            trade["last_update"] = data_hora_sp_str()

            open_trades[trade_id] = trade
            marked.append({
                "trade_id": trade_id,
                "bot": trade.get("bot"),
                "symbol": trade.get("symbol"),
                "side": trade.get("side"),
                "status": trade.get("status"),
            })

        registry["open_trades"] = open_trades
        central_trade_registry.save_registry(registry)

        return {
            "ok": True,
            "marked_count": len(marked),
            "marked": marked,
        }

    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def sync_trade_registry_from_open_positions(commit=False):
    if central_trade_registry is None:
        return {
            "ok": False,
            "error": TRADE_REGISTRY_IMPORT_ERROR or "trade_registry import failed",
            "commit": bool(commit),
        }

    existing_ids = _trade_registry_existing_trade_ids()
    imported = []
    skipped = []
    errors = []
    candidates = []

    existing_signature = set()
    existing_map = {}
    try:
        registry = central_trade_registry.load_registry()
        existing_open = registry.get("open_trades", {})
        existing_signature = _trade_registry_signature_from_items(existing_open)
        existing_map = _trade_registry_signature_map(existing_open)
    except Exception:
        existing_signature = set()
        existing_map = {}

    for bot_key, module in LOADED_BOTS.items():
        positions = get_open_positions_from_module(module, key=bot_key)
        for position in positions:
            candidate = _trade_registry_sync_candidate(bot_key, position)
            
            if not candidate:
                skipped.append({
                    "bot": bot_key,
                    "reason": "INVALID_POSITION_FIELDS",
                    "symbol": position.get("symbol") or position.get("ativo") or position.get("pair"),
                    "side": position.get("side") or position.get("direction") or position.get("signal"),
                })
                continue

            candidate_signature = _trade_registry_signature_from_items([candidate])
            candidate_key = next(iter(candidate_signature), None)

            candidates.append(candidate)
            trade_id = str(candidate.get("trade_id"))
            if trade_id in existing_ids or candidate_key in existing_signature:
                skipped.append({
                    "bot": bot_key,
                    "trade_id": trade_id,
                    "symbol": candidate.get("symbol"),
                    "side": candidate.get("side"),
                    "setup": candidate.get("setup"),
                    "reason": "ALREADY_EXISTS",
                })
                continue

            if not commit:
                continue

            try:
                result = central_trade_registry.register_open_trade(
                    bot=candidate.get("bot"),
                    symbol=candidate.get("symbol"),
                    side=candidate.get("side"),
                    entry=candidate.get("entry"),
                    sl=candidate.get("sl"),
                    tp50=candidate.get("tp50"),
                    setup=candidate.get("setup"),
                    qty=candidate.get("qty"),
                    source=candidate.get("source"),
                    metadata=candidate.get("metadata"),
                )
                if isinstance(result, dict) and result.get("ok"):
                    imported.append({
                        "trade_id": result.get("trade_id") or trade_id,
                        "bot": candidate.get("bot"),
                        "symbol": candidate.get("symbol"),
                        "side": candidate.get("side"),
                        "setup": candidate.get("setup"),
                    })
                    existing_ids.add(str(result.get("trade_id") or trade_id))
                    if candidate_key:
                        existing_signature.add(candidate_key)
                else:
                    errors.append({
                        "trade_id": trade_id,
                        "bot": candidate.get("bot"),
                        "symbol": candidate.get("symbol"),
                        "error": result if isinstance(result, dict) else str(result),
                    })
            except Exception as exc:
                errors.append({
                    "trade_id": trade_id,
                    "bot": candidate.get("bot"),
                    "symbol": candidate.get("symbol"),
                    "error": str(exc),
                })

    candidate_signature_all = _trade_registry_signature_from_items(candidates)
    removed_keys = sorted(list(existing_signature - candidate_signature_all))

    removed = []
    for key in removed_keys:
        item = existing_map.get(key, {})
        removed.append({
            "signature": key,
            "trade_id": item.get("trade_id"),
            "bot": normalize_registry_bot(item.get("bot") or "UNKNOWN"),
            "symbol": normalize_registry_symbol(item.get("symbol_clean") or item.get("symbol") or "UNKNOWN"),
            "side": str(item.get("side") or item.get("direction") or "UNKNOWN").upper(),
            "setup": item.get("setup") or item.get("signal_type") or item.get("setup_label"),
            "last_update": item.get("last_update"),
            "status": item.get("status"),
            "note": "Presente no Registry, ausente nas posições atuais dos robôs.",
        })

    missing_mark_result = None
    if commit and removed:
        missing_mark_result = mark_registry_missing_trades(removed)

    return {
        "ok": len(errors) == 0,
        "commit": bool(commit),
        "updated_at": data_hora_sp_str(),
        "loaded_bots": list(LOADED_BOTS.keys()),
        "candidates_count": len(candidates),
        "imported_count": len(imported),
        "skipped_count": len(skipped),
        "errors_count": len(errors),
        "imported": imported,
        "skipped": skipped[:200],
        "errors": errors,
        "removed_count": len(removed),
        "removed": removed[:200],
        "missing_mark_result": missing_mark_result,
        "after": central_trade_registry_snapshot(include_trades=False) if commit else None,
        "note": "GET faz prévia/dry-run. Para importar, use POST com confirm=true ou confirm=SYNC.",
    }


def autosync_trade_registry(reason="manual"):
    global TRADE_REGISTRY_AUTOSYNC_STATUS

    try:
        result = sync_trade_registry_from_open_positions(commit=True)
        TRADE_REGISTRY_AUTOSYNC_STATUS = {
            "last_run": data_hora_sp_str(),
            "last_ok": bool(result.get("ok")),
            "last_error": None,
            "reason": reason,
            "last_result": {
            "candidates_count": result.get("candidates_count"),
            "imported_count": result.get("imported_count"),
            "skipped_count": result.get("skipped_count"),
            "errors_count": result.get("errors_count"),
            "removed_count": result.get("removed_count"),
            "removed": result.get("removed", [])[:50],
            "missing_mark_result": result.get("missing_mark_result"),
            "after": result.get("after"),
        },
        }
        return result

    except Exception as exc:
        TRADE_REGISTRY_AUTOSYNC_STATUS = {
            "last_run": data_hora_sp_str(),
            "last_ok": False,
            "last_error": str(exc),
            "reason": reason,
            "last_result": None,
        }
        raise


@app.route("/traderegistry/autosync/status")
@app.route("/trade_registry/autosync/status")
@app.route("/trades/autosync/status")
def trade_registry_autosync_status_route():
    return {
        "ok": True,
        "autosync": TRADE_REGISTRY_AUTOSYNC_STATUS,
    }


@app.route("/traderegistry/sync", methods=["GET", "POST"])
@app.route("/trade_registry/sync", methods=["GET", "POST"])
@app.route("/trades/sync", methods=["GET", "POST"])
@app.route("/traderegistry/sync/confirm", methods=["GET", "POST"])
@app.route("/trade_registry/sync/confirm", methods=["GET", "POST"])
@app.route("/trades/sync/confirm", methods=["GET", "POST"])
def trade_registry_sync_route():
    payload = request.get_json(silent=True) or {}
    confirm_raw = payload.get("confirm", request.args.get("confirm", ""))

    # Permite confirmação simples pelo navegador:
    # /traderegistry/sync?confirm=1
    # /traderegistry/sync/confirm
    path_confirm = str(request.path or "").rstrip("/").endswith("/confirm")
    confirm = bool(
        path_confirm
        or confirm_raw is True
        or str(confirm_raw).strip().upper() in {"1", "TRUE", "YES", "SIM", "ON", "SYNC", "CONFIRM"}
    )

    # Antes exigia POST para gravar. Agora GET com confirm=1 ou /confirm também grava,
    # para administração direta pelo navegador, mantendo GET sem confirmação como dry-run.
    commit = bool(confirm)
    result = sync_trade_registry_from_open_positions(commit=commit)
    if commit:
        result["note"] = "Importação confirmada. GET sem confirm continua fazendo apenas prévia/dry-run."
    else:
        result["note"] = "GET faz prévia/dry-run. Para importar pelo navegador, use /traderegistry/sync?confirm=1 ou /traderegistry/sync/confirm."
    return result


@app.route("/traderegistry/reset", methods=["POST"])
def trade_registry_reset_route():
    if central_trade_registry is None:
        return {"ok": False, "error": TRADE_REGISTRY_IMPORT_ERROR or "trade_registry import failed"}, 500

    payload = request.get_json(silent=True) or {}
    confirm_raw = str(payload.get("confirm", "")).strip().upper()

    required_phrase = "RESET_TRADE_REGISTRY_CONFIRMADO"

    if confirm_raw != required_phrase:
        return {
            "ok": False,
            "error": "CONFIRM_REQUIRED",
            "message": "Reset bloqueado por segurança.",
            "required_confirm": required_phrase,
            "example_payload": {
                "confirm": required_phrase
            },
            "warning": "Esta ação apaga todas as posições abertas e fechadas do Trade Registry.",
        }, 400

    result = central_trade_registry.reset_trade_registry(confirm=True)
    status = 200 if result.get("ok") else 400
    return result, status


@app.route("/positions/central")
@app.route("/central/positions")
def central_positions_route():
    positions = get_open_positions_central()

    by_bot = {}
    by_side = {}
    by_symbol = {}

    for p in positions:
        bot = normalize_registry_bot(p.get("bot") or "UNKNOWN")
        side = str(p.get("side") or p.get("direction") or "UNKNOWN").upper()
        symbol = normalize_registry_symbol(
            p.get("symbol_clean") or p.get("symbol") or p.get("ativo") or p.get("pair") or "UNKNOWN"
        )

        by_bot[bot] = by_bot.get(bot, 0) + 1
        by_side[side] = by_side.get(side, 0) + 1
        by_symbol[symbol] = by_symbol.get(symbol, 0) + 1

    return {
    "ok": True,
    "source": "trade_registry" if positions else "fallback_modules",
        "count": len(positions),
        "by_bot": by_bot,
        "by_side": by_side,
        "by_symbol": by_symbol,
        "positions": positions,
    }


@app.route("/traderegistry/health")
@app.route("/trade_registry/health")
@app.route("/trades/health")
def trade_registry_health_route():
    return central_trade_registry_snapshot(include_trades=False)

@app.route("/health")
def health():
    payload = central_watchdog_status()
    payload["trade_registry"] = central_trade_registry_snapshot(include_trades=False)
    return payload


@app.route("/watchdog")
def watchdog():
    return central_watchdog_status()


@app.route("/bots")
def bots():
    return {key: bot_health(key, cfg) for key, cfg in BOT_CONFIGS.items()}


@app.route("/bot/<key>")
def bot_detail(key):
    key = key.upper()
    if key not in BOT_CONFIGS:
        return {"error": "bot inválido"}, 404
    return bot_health(key, BOT_CONFIGS[key])


@app.route("/central")
def central():
    memory_profile_step("route_central_start")
    status = central_watchdog_status()
    exposure_snapshot = central_exposure_snapshot()

    resumo = {}
    for key, cfg in BOT_CONFIGS.items():
        b = bot_health(key, cfg)
        h = b.get("health", {}) or {}
        exposure_info = (exposure_snapshot.get("by_bot") or {}).get(key, {}) or {}

        resumo[key] = {
            "name": b.get("name"),
            "ok": (
                bool(b.get("enabled"))
                and bool(b.get("loaded"))
                and not (
                    b.get("last_error")
                    and not is_benign_bingx_quote_error(b.get("last_error"))
                )
                and not b.get("load_error")
            ),
            "enabled": b.get("enabled"),
            "loaded": b.get("loaded"),
            "telegram": {
                "token_configured": b.get("token_configured"),
                "chat_configured": b.get("chat_configured"),
            },
            "last_error": b.get("last_error"),
            "last_warning": h.get("last_warning"),
            "load_error": b.get("load_error"),
            "last_scanner_run": b.get("last_scanner_run"),
            "last_management_run": b.get("last_management_run"),
            "minutes_since_scanner": b.get("minutes_since_scanner"),
            "minutes_since_management": b.get("minutes_since_management"),
            "watchlist_total": h.get("watchlist_total"),
            "watchlist_valid": h.get("watchlist_valid"),
            "watchlist_invalid": h.get("watchlist_invalid", []),
            "positions_open": h.get("last_positions_count") if h.get("last_positions_count") is not None else exposure_info.get("total"),
            "signals_last_cycle": h.get("last_signals_sent"),
            "watchdog_status": h.get("watchdog_last_status"),
            "mfe_avg_pct": h.get("mfe_avg_pct"),
            "mae_avg_pct": h.get("mae_avg_pct"),
            "mfe_avg_r": h.get("mfe_avg_r"),
            "mae_avg_r": h.get("mae_avg_r"),
            "top_mfe_month": h.get("top_mfe_month", []),
            "runners_3r": h.get("runners_3r"),
            "runners_5r": h.get("runners_5r"),
            "runners_10r": h.get("runners_10r"),
            "open_runner_symbol": h.get("open_runner_symbol"),
            "open_runner_setup": h.get("open_runner_setup"),
            "open_runner_side": h.get("open_runner_side"),
            "open_runner_r": h.get("open_runner_r"),
            "open_runner_pct": h.get("open_runner_pct"),
        }

    enabled = [k for k, v in resumo.items() if v.get("enabled")]
    loaded = [k for k, v in resumo.items() if v.get("loaded")]
    alerts = [k for k, v in resumo.items() if v.get("enabled") and not v.get("ok")]
    mem = memory_snapshot("route_central_end", store=True)

    return {
        "ok": status.get("ok"),
        "status": status.get("status"),
        "central_started_at": status.get("central_started_at"),
        "enabled_bots": enabled,
        "loaded_bots": loaded,
        "alerts": alerts,
        "reasons": status.get("reasons", []),
        "memory": mem,
        "exposure": exposure_snapshot,
        "trade_registry": central_trade_registry_snapshot(include_trades=False),
        "open_runners": exposure_snapshot.get("open_runners"),
        "best_open_runner": exposure_snapshot.get("best_open_runner"),
        "bots": resumo,
    }


@app.route("/exposure")
def exposure():
    return central_exposure_snapshot()


@app.route("/runners")
def runners():
    snapshot = central_exposure_snapshot()
    return {
        "open_runners": snapshot.get("open_runners"),
        "best_open_runner": snapshot.get("best_open_runner"),
        "by_bot": {
            key: {
                "open_runners": value.get("open_runners"),
                "best_open_runner": value.get("best_open_runner"),
                "positions_open": value.get("total"),
            }
            for key, value in snapshot.get("by_bot", {}).items()
        },
    }





@app.route("/memoria")
@app.route("/memória")
def memory_route():
    try:
        if MEMORY_PROFILER_LOADED and memory_profiler:
            payload = memory_profiler.build_memory_json(deep=False, include_text=False)
            return payload
    except Exception as exc:
        text, payload = build_memory_text(run_gc=False)
        payload["text"] = text
        payload["memory_profiler_error"] = str(exc)
        return payload
    text, payload = build_memory_text(run_gc=False)
    payload["text"] = text
    payload["memory_profiler_loaded"] = MEMORY_PROFILER_LOADED
    payload["memory_profiler_import_error"] = MEMORY_PROFILER_ERROR
    return payload


@app.route("/memory/gc")
@app.route("/memoria/gc")
def memory_gc_route():
    text, payload = build_memory_text(run_gc=True)
    try:
        if MEMORY_PROFILER_LOADED and memory_profiler:
            payload["memory_profiler"] = memory_profiler.build_memory_json(deep=False, include_text=False)
            payload["memory_profiler_text"] = memory_profiler.build_memory_report(include_tracemalloc=False)
    except Exception as exc:
        payload["memory_profiler_error"] = str(exc)
    payload["text"] = text
    return payload


@app.route("/memory/deep")
@app.route("/memoria/deep")
def memory_deep_route():
    try:
        if MEMORY_PROFILER_LOADED and memory_profiler:
            text = memory_profiler.build_memory_report(include_tracemalloc=True)
            return {"ok": True, "text": text}
        return {"ok": False, "error": MEMORY_PROFILER_ERROR}, 500
    except Exception as exc:
        return {"ok": False, "error": str(exc)}, 500


@app.route("/memory/top")
def memory_top_route():
    import gc
    import sys
    from collections import defaultdict

    try:
        gc.collect()
        objects = gc.get_objects()

        by_type = defaultdict(lambda: {"count": 0, "bytes": 0})
        largest = []

        for obj in objects:
            try:
                size = sys.getsizeof(obj)
                type_name = type(obj).__name__

                by_type[type_name]["count"] += 1
                by_type[type_name]["bytes"] += size

                if size >= 1024 * 50:
                    largest.append({
                        "type": type_name,
                        "size_kb": round(size / 1024, 2),
                        "repr": repr(obj)[:200],
                    })
            except Exception:
                continue

        types = []
        for type_name, data in by_type.items():
            types.append({
                "type": type_name,
                "count": data["count"],
                "size_mb": round(data["bytes"] / 1024 / 1024, 4),
            })

        types.sort(key=lambda x: x["size_mb"], reverse=True)
        largest.sort(key=lambda x: x["size_kb"], reverse=True)

        return {
            "ok": True,
            "generated_at": data_hora_sp_str() if "data_hora_sp_str" in globals() else None,
            "object_count": len(objects),
            "top_types": types[:30],
            "largest_objects": largest[:30],
            "note": "Tamanho aproximado via sys.getsizeof; não inclui sempre objetos referenciados internamente.",
        }

    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    

@app.route("/relatorio")
def relatorio_curto():
    memory_profile_step("route_relatorio_start")
    text = build_central_report("curto")
    memory_profile_step("route_relatorio_end")
    return {"text": text}


@app.route("/relatorio/completo")
@app.route("/relatorio/diario")
@app.route("/relatorio/diário")
@app.route("/auditoria")
def relatorio_completo():
    memory_profile_step("route_relatorio_completo_start")
    text = build_central_report("completo")
    memory_profile_step("route_relatorio_completo_end")
    return {"text": text}


@app.route("/relatorio/<key>")
def relatorio_bot(key):
    bot_key = REPORT_BOT_ALIASES.get(str(key).lower(), str(key).upper())
    if bot_key not in BOT_CONFIGS:
        return {"error": "bot inválido"}, 404
    return {"text": build_central_report("completo", bot_key=bot_key)}


@app.route("/diagnostico")
def diagnostico():
    memory_profile_step("route_diagnostico_start")
    text = build_diagnostic_report()
    memory_profile_step("route_diagnostico_end")
    return {"text": text}


@app.route("/selftest")
def selftest():
    memory_profile_step("route_selftest_start")
    text = build_selftest_report()
    memory_profile_step("route_selftest_end")
    return {"text": text}


# ==========================================================
# CENTRAL REPORT BUILDER
# ==========================================================
REPORT_COMMANDS = {"/relatorio", "/relatório", "/report", "/auditoria", "/diario", "/diário", "/relatoriocompleto", "/relatorio_completo"}
REPORT_BOT_ALIASES = {
    "trend": "TRENDPRO",
    "trendpro": "TRENDPRO",
    "trend_pro": "TRENDPRO",
    "trend-pro": "TRENDPRO",
    "donkey": "DONKEY",
    "cobra": "COBRA",
    "meme": "MEME",
    "predator": "PREDATOR",
    "smart": "PREDATOR",
    "smartpredator": "PREDATOR",
    "turtle": "TURTLE",
    "falcon": "FALCON",
}


def _short(value, max_len=1200):
    txt = "" if value is None else str(value)
    if len(txt) <= max_len:
        return txt
    return txt[:max_len].rstrip() + "\n... [cortado]"


def _clean_warning(value):
    return clean_operational_warning(value)


def _fmt_metric(value, suffix="", ndigits=2, empty="N/A"):
    val = safe_round(value, ndigits, None)
    if val is None:
        return empty
    sign = "+" if isinstance(val, (int, float)) and val > 0 and suffix in {"%", "R"} else ""
    return f"{sign}{val:.{ndigits}f}{suffix}"


def _bot_compact_status_line(key: str, exposure_by_bot: dict = None):
    cfg = BOT_CONFIGS.get(key)
    if not cfg:
        return f"⚠️ {key}: bot inválido"

    b = bot_health(key, cfg)
    h = b.get("health", {}) or {}
    exposure_info = (exposure_by_bot or {}).get(key, {})
    warning = _clean_warning(h.get("last_warning"))
    last_error = b.get("last_error")
    loaded = bool(b.get("loaded"))
    enabled = bool(b.get("enabled"))
    ok = enabled and loaded and not b.get("load_error") and not (last_error and not is_benign_bingx_quote_error(last_error))
    emoji = "✅" if ok else ("⚠️" if enabled else "⏸️")

    positions = h.get("last_positions_count")
    if positions is None:
        positions = exposure_info.get("total")

    pf_r = h.get("profit_factor_r")
    expectancy = h.get("expectancy_r")
    open_r = h.get("open_runner_r")
    open_symbol = h.get("open_runner_symbol")
    if open_r is None and exposure_info.get("best_open_runner"):
        open_r = exposure_info["best_open_runner"].get("runner_r")
        open_symbol = exposure_info["best_open_runner"].get("symbol")

    runners = exposure_info.get("open_runners") or {}
    runner_txt = (
        f"1R:{runners.get('runners_1r_open', 0)} "
        f"2R:{runners.get('runners_2r_open', 0)} "
        f"3R:{runners.get('runners_3r_open', 0)}"
    )

    pieces = [
        f"{emoji} {key} ({b.get('name')})",
        f"scan {b.get('minutes_since_scanner')}m",
        f"gestão {b.get('minutes_since_management')}m",
        f"pos {positions}",
        f"WL {h.get('watchlist_valid')}/{h.get('watchlist_total')}",
        f"sinais {h.get('last_signals_sent')}",
    ]

    if pf_r is not None:
        pieces.append(f"PF {_fmt_metric(pf_r, '', 2)}")
    if expectancy is not None:
        pieces.append(f"Exp {_fmt_metric(expectancy, 'R', 2)}")
    if open_r is not None:
        runner_label = f"runner {_fmt_metric(open_r, 'R', 2)}"
        if open_symbol:
            runner_label += f" {open_symbol}"
        pieces.append(runner_label)
    pieces.append(runner_txt)

    if last_error and not is_benign_bingx_quote_error(last_error):
        pieces.append(f"erro={last_error}")
    if warning:
        pieces.append(f"warning={warning}")
    if b.get("load_error"):
        pieces.append(f"load_error={b.get('load_error')}")

    return " | ".join(pieces)


def _bot_report_health_text(key: str):
    cfg = BOT_CONFIGS.get(key)
    if not cfg:
        return f"{key}: bot inválido"
    b = bot_health(key, cfg)
    h = b.get("health", {}) or {}
    warning = _clean_warning(h.get("last_warning"))
    return (
        f"{key} - {b.get('name')}\n"
        f"enabled: {b.get('enabled')} | loaded: {b.get('loaded')} | ok: {not bool(b.get('load_error') or b.get('last_error'))}\n"
        f"scanner: {b.get('last_scanner_run')} ({b.get('minutes_since_scanner')} min)\n"
        f"gestão: {b.get('last_management_run')} ({b.get('minutes_since_management')} min)\n"
        f"erro: {b.get('last_error')}\n"
        f"warning: {warning}\n"
        f"watchdog: {h.get('watchdog_last_status') or h.get('watchdog_status')}\n"
        f"watchlist: {h.get('watchlist_valid')}/{h.get('watchlist_total')} inválidos={h.get('watchlist_invalid', [])}\n"
        f"posições: {h.get('last_positions_count')} | sinais ciclo: {h.get('last_signals_sent')}"
    )


def _json_or_text(value):
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, indent=2)
    return str(value)


def _call_first(module, names, *args):
    for name in names:
        fn = getattr(module, name, None)
        if callable(fn):
            return fn(*args)
    return None


def _call_bot_text_safely(key: str, label: str, func):
    """
    Executa chamadas de texto dos bots sem derrubar /audit, /daily ou /relatoriocompleto.

    Alguns robôs podem ter bugs internos em comandos específicos (ex.: variável
    ausente em resumo/funil/eventos). A Central deve registrar o erro naquela
    seção e continuar gerando o relatório dos demais bots.
    """
    try:
        value = func()
        if value is None:
            return "N/A"
        return _json_or_text(value)
    except Exception as exc:
        return f"⚠️ Erro ao gerar {label} de {key}: {exc}"




# ==========================================================
# FORMATAÇÃO EXECUTIVA V3.0 — MÉTRICAS PADRONIZADAS DOS BOTS
# ==========================================================
#
# Filosofia V3.0:
# - Relatórios executivos em português claro.
# - Destaque operacional em % e classificações.
# - R fica apenas como auditoria/grandes vencedores.
# - Robôs sem amostra suficiente não exibem métricas falsas.
# - /daily deve ser curto, limpo e acionável.
# ==========================================================

def _v3_text_to_float(value, default=None):
    try:
        if value is None:
            return default
        s = str(value).strip()
        if not s or s.upper() in {"N/A", "NONE", "NULL"}:
            return default
        s = s.replace("%", "").replace("R", "").replace("+", "").replace("−", "-")
        s = s.replace("∞", "999999")
        s = s.replace(" ", "")
        # pt-BR: 1.234,56 -> 1234.56 | decimal simples: 1,23 -> 1.23
        if "," in s and "." in s:
            s = s.replace(".", "").replace(",", ".")
        elif "," in s:
            s = s.replace(",", ".")
        return float(s)
    except Exception:
        return default


def _v3_fmt_num(value, casas=2, default="N/A"):
    val = _v3_text_to_float(value, None)
    if val is None:
        return default
    if val >= 999999:
        return "∞"
    return f"{val:.{casas}f}".replace(".", ",")


def _v3_fmt_pct(value, casas=2, sinal=True, default="N/A"):
    val = _v3_text_to_float(value, None)
    if val is None:
        return default
    prefix = "+" if sinal and val > 0 else ""
    return f"{prefix}{val:.{casas}f}%".replace(".", ",")


def _v3_find_number_after_labels(text, labels):
    if not text:
        return None
    for label in labels:
        # Captura número na mesma linha ou na linha seguinte.
        pattern = rf"{re.escape(label)}\s*[:\n]\s*([+\-−]?\d+(?:[\.,]\d+)?)"
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if m:
            return _v3_text_to_float(m.group(1), None)
    return None


def _v3_find_count(patterns, text):
    if not text:
        return 0
    for pattern in patterns:
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if m:
            try:
                return int(float(str(m.group(1)).replace(",", ".")))
            except Exception:
                return 0
    return 0


def _v3_classificar_profit_factor(pf):
    pf = _v3_text_to_float(pf, None)
    if pf is None:
        return "⚪ N/A"
    if pf < 1.0:
        return "🔴 Estratégia perdedora"
    if pf < 1.3:
        return "🟡 Lucro baixo"
    if pf < 1.8:
        return "🟢 Boa estratégia"
    return "⭐ Excelente estratégia"


def _v3_classificar_gerenciamento(valor):
    valor = _v3_text_to_float(valor, None)
    if valor is None:
        return "⚪ N/A"
    if valor < 1.0:
        return "🔴 Ruim"
    if valor < 1.5:
        return "🟡 Aceitável"
    if valor < 2.0:
        return "🟢 Bom"
    return "⭐ Excelente"


def _v3_classificar_lucro_pct(valor):
    valor = _v3_text_to_float(valor, None)
    if valor is None:
        return "⚪ N/A"
    if valor < 0:
        return "🔴 Negativo"
    if valor < 0.25:
        return "🟡 Baixo"
    if valor < 0.75:
        return "🟢 Muito bom"
    return "⭐ Excelente"


def _v3_classificar_captura(valor):
    valor = _v3_text_to_float(valor, None)
    if valor is None:
        return "⚪ N/A"
    if valor < 30:
        return "🔴 Baixo"
    if valor < 45:
        return "🟡 Regular"
    if valor < 60:
        return "🟢 Muito bom"
    return "⭐ Excelente"


def _v3_classificar_devolucao(valor):
    """
    Classificação V3.0 para lucro devolvido antes do fechamento.
    Quanto menor a devolução, melhor.
    """
    valor = abs(_v3_text_to_float(valor, 0.0))
    if valor < 0.8:
        return "⭐ Excelente"
    if valor < 1.5:
        return "🟢 Muito bom"
    if valor < 2.5:
        return "🟡 Bom"
    if valor < 4.0:
        return "🟠 Alto"
    return "🔴 Muito alto"


def _v3_ciclos_para_dias_horas(ciclos, bot_key=None, default_minutes=5):
    val = _v3_text_to_float(ciclos, None)
    if val is None:
        return "N/A"
    try:
        env_key = f"{str(bot_key or '').upper()}_MANAGEMENT_CYCLE_MINUTES"
        minutos_por_ciclo = float(os.environ.get(env_key, os.environ.get("MANAGEMENT_CYCLE_MINUTES", str(default_minutes))))
        total_min = int(round(val * minutos_por_ciclo))
    except Exception:
        total_min = int(round(val * default_minutes))
    dias = total_min // 1440
    horas = (total_min % 1440) // 60
    minutos = total_min % 60
    partes = []
    if dias:
        partes.append(f"{dias}d")
    if horas:
        partes.append(f"{horas}h")
    if minutos and not dias:
        partes.append(f"{minutos}min")
    return " ".join(partes) if partes else "0min"


def _v3_is_insufficient_sample(metrics):
    """Amostra insuficiente quando não há trades encerrados ou quando tudo está zerado."""
    trades = metrics.get("trades")
    if trades is None:
        return False
    try:
        return float(trades) <= 0
    except Exception:
        return False


def _v3_bot_metrics_from_summary(bot_key, summary_text):
    txt = str(summary_text or "")
    trades = _v3_find_number_after_labels(txt, ["Trades encerrados", "Trades fechados"])
    pnl_pct = _v3_find_number_after_labels(txt, ["PnL realizado", "Resultado financeiro"])
    profit_factor = _v3_find_number_after_labels(txt, ["Profit Factor %", "Profit Factor"])
    eficiencia = _v3_find_number_after_labels(txt, ["Profit Factor R", "Eficiência do gerenciamento"])
    expectancy_r = _v3_find_number_after_labels(txt, ["Expectancy", "Expectativa"])
    pos_tp50_r = _v3_find_number_after_labels(txt, ["Expectancy pós-TP50", "Expectativa pós-TP50", "Lucro médio após TP50"])
    captura = _v3_find_number_after_labels(txt, ["Captura de tendência", "Captura do movimento", "Aproveitamento do movimento"])
    mfe = _v3_find_number_after_labels(txt, ["MFE médio", "Maior lucro durante o trade"])
    mae = _v3_find_number_after_labels(txt, ["MAE médio", "Maior perda durante o trade"])
    devolucao = _v3_find_number_after_labels(txt, ["Devolução média", "Lucro devolvido antes do fechamento"])
    tempo_tp50 = _v3_find_number_after_labels(txt, ["Tempo médio até TP50"])
    tempo_fechamento = _v3_find_number_after_labels(txt, ["Tempo médio até fechamento"])
    sinais = _v3_find_number_after_labels(txt, ["Sinais Falcon", "Sinais H1 do dia", "Sinais H1 do período", "Sinais Donkey do dia", "Sinais Turtle"])

    lucro_esperado_pct = None
    if pnl_pct is not None and trades and trades > 0:
        lucro_esperado_pct = pnl_pct / trades

    r3 = _v3_find_count([r"3R\+\s*[:=]\s*(\d+)", r"Acima de 3R\s*[:=]\s*(\d+)"], txt)
    r5 = _v3_find_count([r"5R\+\s*[:=]\s*(\d+)", r"Acima de 5R\s*[:=]\s*(\d+)"], txt)
    r10 = _v3_find_count([r"10R\+\s*[:=]\s*(\d+)", r"Acima de 10R\s*[:=]\s*(\d+)"], txt)

    return {
        "trades": trades,
        "sinais": sinais,
        "pnl_pct": pnl_pct,
        "profit_factor": profit_factor,
        "eficiencia": eficiencia,
        "expectancy_r": expectancy_r,
        "pos_tp50_r": pos_tp50_r,
        "lucro_esperado_pct": lucro_esperado_pct,
        "captura": captura,
        "mfe": mfe,
        "mae": mae,
        "devolucao": devolucao,
        "tempo_tp50": tempo_tp50,
        "tempo_fechamento": tempo_fechamento,
        "r3": r3,
        "r5": r5,
        "r10": r10,
    }



V3_MIN_TRADES_FOR_RATING = int(os.environ.get('V3_MIN_TRADES_FOR_RATING', '5'))

def _v3_strategy_score_0_10(metrics):
    """
    Nota executiva 0-10.
    Só calcula nota quando há amostra mínima.
    Regra V3.1:
    - Trades encerrados < V3_MIN_TRADES_FOR_RATING → Nota N/A / Amostra insuficiente.
    """
    trades = metrics.get("trades")
    if trades is not None:
        try:
            if float(trades) < V3_MIN_TRADES_FOR_RATING:
                return None
        except Exception:
            pass

    pf = metrics.get("profit_factor")
    lucro = metrics.get("lucro_esperado_pct")
    eg = metrics.get("eficiencia")
    cap = metrics.get("captura")
    dev = metrics.get("devolucao")
    score = 0.0
    peso = 0.0

    if pf is not None:
        pf = _v3_text_to_float(pf, 0.0)
        s = 0.0 if pf < 1.0 else (4.5 if pf < 1.3 else (7.5 if pf < 1.8 else 10.0))
        score += s * 0.30
        peso += 0.30

    if lucro is not None:
        lucro = _v3_text_to_float(lucro, 0.0)
        s = 0.0 if lucro < 0 else (4.5 if lucro < 0.25 else (7.5 if lucro < 0.75 else 10.0))
        score += s * 0.25
        peso += 0.25

    if eg is not None:
        eg = _v3_text_to_float(eg, 0.0)
        s = 2.0 if eg < 1.0 else (5.5 if eg < 1.5 else (7.5 if eg < 2.0 else 10.0))
        score += s * 0.20
        peso += 0.20

    if cap is not None:
        cap = _v3_text_to_float(cap, 0.0)
        s = 3.0 if cap < 30 else (6.0 if cap < 45 else (8.0 if cap < 60 else 10.0))
        score += s * 0.15
        peso += 0.15

    if dev is not None:
        dev = abs(_v3_text_to_float(dev, 0.0))
        s = 10.0 if dev < 0.8 else (8.0 if dev < 1.5 else (6.0 if dev < 2.5 else (3.0 if dev < 4.0 else 1.0)))
        score += s * 0.10
        peso += 0.10

    if peso <= 0:
        return None
    return round(score / peso, 1)


def _v3_note_label(score):
    if score is None:
        return "Amostra insuficiente"
    try:
        score = float(score)
    except Exception:
        return "Amostra insuficiente"
    if score >= 8.5:
        return "⭐⭐⭐⭐⭐ Excelente"
    if score >= 7.0:
        return "⭐⭐⭐⭐ Boa"
    if score >= 5.0:
        return "⭐⭐⭐ Regular"
    return "⭐⭐ Atenção"


def _v3_pct_from_r_and_avg_r(r_value, avg_r_value):
    """
    Converte uma métrica em R para uma estimativa em % usando a relação:
    1R financeiro médio ≈ MFE% / MFE_R, quando disponível.
    É uma aproximação para deixar o painel executivo mais didático.
    """
    r = _v3_text_to_float(r_value, None)
    avg_r = _v3_text_to_float(avg_r_value, None)
    if r is None or avg_r is None or avg_r == 0:
        return None
    return r * avg_r



def build_strategy_executive_metrics_v3(bot_key, summary_text, compact=False):
    """
    Camada única da Central V3.1.
    Não altera a lógica dos robôs: apenas traduz métricas para linguagem executiva.
    """
    m = _v3_bot_metrics_from_summary(bot_key, summary_text)
    has_any = any(v not in (None, 0, "") for v in m.values())
    if not has_any:
        return "📈 QUALIDADE EXECUTIVA V3.1\nAmostra insuficiente hoje.\nAguardar trades encerrados."

    if _v3_is_insufficient_sample(m):
        sinais_txt = ""
        if m.get("sinais") is not None:
            sinais_txt = f"\nSinais hoje: {int(m.get('sinais') or 0)}"
        return (
            "📈 QUALIDADE EXECUTIVA V3.1\n"
            "Amostra insuficiente hoje.\n"
            f"Trades encerrados: {int(m.get('trades') or 0)}{sinais_txt}\n"
            "Aguardar trades encerrados para calcular Profit Factor, lucro esperado e eficiência."
        )

    lines = ["📈 QUALIDADE EXECUTIVA V3.1", ""]

    if m.get("profit_factor") is not None:
        lines += ["Profit Factor:", f"{_v3_fmt_num(m.get('profit_factor'))} {_v3_classificar_profit_factor(m.get('profit_factor'))}", ""]

    if m.get("eficiencia") is not None:
        lines += ["Eficiência do gerenciamento:", f"{_v3_fmt_num(m.get('eficiencia'))} {_v3_classificar_gerenciamento(m.get('eficiencia'))}"]
        if not compact:
            lines += ["Cada trade vencedor capturou, em média,", f"{_v3_fmt_num(m.get('eficiencia'))} vezes o risco inicial."]
        lines.append("")

    if m.get("lucro_esperado_pct") is not None:
        lines += ["Lucro esperado por trade:", f"{_v3_fmt_pct(m.get('lucro_esperado_pct'))} {_v3_classificar_lucro_pct(m.get('lucro_esperado_pct'))}", ""]

    if not compact and m.get("expectancy_r") is not None:
        lines += ["Auditoria em R:", f"Expectativa técnica: {_v3_fmt_num(m.get('expectancy_r'))}R", ""]

    if not compact and m.get("pos_tp50_r") is not None:
        pos_tp50_pct = _v3_pct_from_r_and_avg_r(m.get("pos_tp50_r"), m.get("mfe"))
        lines += ["Lucro médio após TP50:"]
        if pos_tp50_pct is not None:
            lines.append(f"+{_v3_fmt_num(m.get('pos_tp50_r'))}R ({_v3_fmt_pct(pos_tp50_pct)})")
        else:
            lines.append(f"+{_v3_fmt_num(m.get('pos_tp50_r'))}R")
        lines += ["Auditoria:", f"{_v3_fmt_num(m.get('pos_tp50_r'))} vezes o risco inicial", ""]

    if m.get("captura") is not None:
        lines += ["Aproveitamento da tendência:", f"{_v3_fmt_num(m.get('captura'))}% {_v3_classificar_captura(m.get('captura'))}", ""]

    if m.get("mfe") is not None:
        lines += ["Maior lucro durante o trade:", _v3_fmt_pct(m.get("mfe")), ""]
    if m.get("mae") is not None:
        lines += ["Maior perda durante o trade:", _v3_fmt_pct(m.get("mae")), ""]
    if m.get("devolucao") is not None:
        lines += ["Lucro devolvido antes do fechamento:", f"{_v3_fmt_pct(m.get('devolucao'), sinal=False)} {_v3_classificar_devolucao(m.get('devolucao'))}", ""]

    if m.get("pnl_pct") is not None:
        lines += ["Resultado financeiro:", _v3_fmt_pct(m.get("pnl_pct"))]
        if not compact and m.get("expectancy_r") is not None:
            lines += ["", "Resultado técnico:", f"{_v3_fmt_num(m.get('expectancy_r'))}R"]
        lines.append("")

    if not compact and (m.get("tempo_tp50") is not None or m.get("tempo_fechamento") is not None):
        lines += ["⏱ TEMPO MÉDIO DOS TRADES"]
        if m.get("tempo_tp50") is not None:
            lines.append(f"Até TP50: {_v3_ciclos_para_dias_horas(m.get('tempo_tp50'), bot_key)}")
        if m.get("tempo_fechamento") is not None:
            lines.append(f"Até fechamento: {_v3_ciclos_para_dias_horas(m.get('tempo_fechamento'), bot_key)}")
        lines += ["", "Auditoria:"]
        if m.get("tempo_tp50") is not None:
            lines.append(f"TP50: {_v3_fmt_num(m.get('tempo_tp50'), 1)} ciclos")
        if m.get("tempo_fechamento") is not None:
            lines.append(f"Fechamento: {_v3_fmt_num(m.get('tempo_fechamento'), 1)} ciclos")
        lines.append("")

    if any([m.get("r3"), m.get("r5"), m.get("r10")]):
        lines += ["Grandes vencedores:", f"Acima de 3R: {m.get('r3')}", f"Acima de 5R: {m.get('r5')}", f"Acima de 10R: {m.get('r10')}", ""]

    score10 = _v3_strategy_score_0_10(m)
    lines += ["🏆 Nota da estratégia:"]
    if score10 is None:
        trades = m.get("trades")
        if trades is not None:
            lines.append(f"Trades encerrados < {V3_MIN_TRADES_FOR_RATING}")
        lines += ["Nota:", "N/A", "Amostra insuficiente"]
    else:
        lines += [f"{_v3_fmt_num(score10, 1)}/10", _v3_note_label(score10)]

    return "\n".join([line for line in lines if line is not None]).strip()


# Compatibilidade com chamadas antigas V2.
def build_strategy_executive_metrics_v2(bot_key, summary_text):
    return build_strategy_executive_metrics_v3(bot_key, summary_text, compact=False)


def transform_bot_summary_v3(bot_key, summary_text):
    """Transforma nomes técnicos do resumo sem recalcular estratégia."""
    txt = str(summary_text or "")
    if not txt or txt == "N/A":
        return txt

    replacements = {
        "PnL realizado:": "Resultado financeiro:",
        "Profit Factor %:": "Profit Factor:",
        "Profit Factor R:": "Eficiência do gerenciamento (auditoria):",
        "Expectancy:": "Lucro esperado por trade (auditoria em R):",
        "Expectancy pós-TP50:": "Lucro médio após TP50 (auditoria em R):",
        "Captura de tendência:": "Captura do movimento:",
        "MFE médio:": "Maior lucro durante o trade:",
        "MAE médio:": "Maior perda durante o trade:",
        "Devolução média:": "Lucro devolvido antes do fechamento:",
        "Runners:": "Grandes vencedores:",
    }
    for old, new in replacements.items():
        txt = txt.replace(old, new)

    def repl_tp50(match):
        ciclos = match.group(1)
        return f"Tempo médio até TP50:\n{_v3_ciclos_para_dias_horas(ciclos, bot_key)} ({_v3_fmt_num(ciclos, 1)} ciclos)"

    def repl_close(match):
        ciclos = match.group(1)
        return f"Tempo médio até fechamento:\n{_v3_ciclos_para_dias_horas(ciclos, bot_key)} ({_v3_fmt_num(ciclos, 1)} ciclos)"

    txt = re.sub(r"Tempo médio até TP50:\s*([\d\.,]+)\s*ciclos de gestão", repl_tp50, txt, flags=re.IGNORECASE)
    txt = re.sub(r"Tempo médio até fechamento:\s*([\d\.,]+)\s*ciclos de gestão", repl_close, txt, flags=re.IGNORECASE)
    return txt


# Compatibilidade com chamadas antigas V2.
def transform_bot_summary_v2(bot_key, summary_text):
    return transform_bot_summary_v3(bot_key, summary_text)

def _bot_funil_text(key: str, module):
    def _run():
        if key == "TURTLE":
            return _call_first(module, ["funnel_text"])
        if key == "FALCON":
            return _call_first(module, ["funnel_text"])
        return _call_first(module, [
            "montar_funil_texto", "montar_funil", "funnel_text", "funil_texto", "build_funnel_text"
        ])
    return _call_bot_text_safely(key, "funil", _run)


def _bot_eventos_text(key: str, module):
    def _run():
        if key == "TURTLE":
            return _call_first(module, ["events_text"])
        if key == "FALCON":
            return _call_first(module, ["events_text"])
        return _call_first(module, [
            "montar_eventos_texto", "events_text", "eventos_texto", "build_events_text"
        ])
    return _call_bot_text_safely(key, "eventos", _run)


def _bot_resumo_text(key: str, module):
    def _run():
        # Donkey tem resumo próprio. Usar montar_resumo_diario nele chama o bloco Trend
        # e pode quebrar métricas específicas do Donkey.
        if key == "DONKEY" and hasattr(module, "montar_resumo_donkey"):
            return module.montar_resumo_donkey()

        if key in {"TURTLE", "FALCON"}:
            if hasattr(module, "build_summary") and hasattr(module, "trades_today"):
                return module.build_summary("DIA", module.trades_today())

        return _call_first(module, [
            "montar_resumo_diario", "build_daily_summary", "summary_text", "build_summary_text", "resumo_texto"
        ])
    return _call_bot_text_safely(key, "resumo", _run)


def build_single_bot_report(key: str, complete: bool = True):
    key = str(key).upper()
    cfg = BOT_CONFIGS.get(key)
    if not cfg:
        return f"Bot inválido: {key}"
    module = LOADED_BOTS.get(key)

    memory_profile_step(f"build_single_bot_report_start_{key}")
    parts = [f"🤖 RELATÓRIO {key} - {cfg.get('name')}\n", "🩺 HEALTH\n" + _bot_report_health_text(key)]

    if module is None:
        memory_profile_step(f"build_single_bot_report_end_{key}")
        return "\n\n".join(parts + [f"Módulo não carregado: {LOAD_ERRORS.get(key)}"])

    funil = _bot_funil_text(key, module)
    eventos = _bot_eventos_text(key, module)
    resumo = _bot_resumo_text(key, module)

    if funil and funil != "None":
        parts.append("📈 FUNIL\n" + _short(funil, 2200 if complete else 900))
    if eventos and eventos != "None":
        parts.append("📋 EVENTOS\n" + _short(eventos, 2200 if complete else 900))
    if resumo and resumo != "None":
        resumo_v3 = transform_bot_summary_v3(key, resumo)
        executivo_v3 = build_strategy_executive_metrics_v3(key, resumo, compact=False)
        if executivo_v3:
            parts.append(_short(executivo_v3, 2000 if complete else 900))
        parts.append("📊 RESUMO\n" + _short(resumo_v3, 3000 if complete else 1200))

    memory_profile_step(f"build_single_bot_report_end_{key}")
    return "\n\n".join(parts)


def build_central_status_text():
    memory_profile_step("build_central_status_start")
    status = central_watchdog_status()
    exposure_snapshot = central_exposure_snapshot()
    best = exposure_snapshot.get("best_open_runner") or {}
    by_bot_exposure = exposure_snapshot.get("by_bot", {}) or {}
    open_runners = exposure_snapshot.get("open_runners") or {}
    mem = memory_snapshot("build_central_status_memory", store=True)

    lines = [
        "📊 RELATÓRIO CENTRAL QUANT",
        f"Data/hora: {data_hora_sp_str()}",
        f"Status: {status.get('status')} | OK: {status.get('ok')}",
        f"Central iniciou: {status.get('central_started_at')}",
        f"Memória: {mem.get('rss_mb')} MB ({mem.get('usage_pct')}%)",
        f"Motivos: {status.get('reasons', [])}",
        "",
        "📌 EXPOSIÇÃO",
        f"Total: {exposure_snapshot.get('total_positions_open')}",
        f"LONG: {exposure_snapshot.get('long_positions_open')}",
        f"SHORT: {exposure_snapshot.get('short_positions_open')}",
        (
            "Runners abertos: "
            f"1R={open_runners.get('runners_1r_open', 0)} | "
            f"2R={open_runners.get('runners_2r_open', 0)} | "
            f"3R={open_runners.get('runners_3r_open', 0)} | "
            f"5R={open_runners.get('runners_5r_open', 0)} | "
            f"10R={open_runners.get('runners_10r_open', 0)}"
        ),
    ]

    if best:
        lines += [
            "",
            "🏃 Melhor runner aberto",
            f"{best.get('bot')} {best.get('symbol')} {best.get('side')} {best.get('setup')}",
            f"{best.get('runner_pct')}% | {best.get('runner_r')}R",
        ]

    total_pos = int(exposure_snapshot.get("total_positions_open") or 0)
    short_pos = int(exposure_snapshot.get("short_positions_open") or 0)
    long_pos = int(exposure_snapshot.get("long_positions_open") or 0)
    concentration_msgs = []
    if total_pos >= 50:
        concentration_msgs.append(f"Atenção: {total_pos} posições abertas.")
    if total_pos and short_pos / max(total_pos, 1) >= 0.80:
        concentration_msgs.append(f"Concentração SHORT alta: {short_pos}/{total_pos}.")
    if total_pos and long_pos / max(total_pos, 1) >= 0.80:
        concentration_msgs.append(f"Concentração LONG alta: {long_pos}/{total_pos}.")
    if mem.get("usage_pct") and mem.get("usage_pct") >= MEMORY_ALERT_THRESHOLD_PCT:
        concentration_msgs.append(f"Memória alta: {mem.get('rss_mb')} MB ({mem.get('usage_pct')}%).")
    if concentration_msgs:
        lines += ["", "⚠️ OBSERVAÇÕES DE RISCO"] + [f"- {m}" for m in concentration_msgs]

    lines += ["", "🤖 BOTS"]
    for key in BOT_CONFIGS.keys():
        lines.append(_bot_compact_status_line(key, by_bot_exposure))

    memory_profile_step("build_central_status_end")
    return "\n".join(lines)


def build_central_report(mode: str = "curto", bot_key: str = None):
    """
    Relatórios da Central.

    /relatorio:
      Painel resumido para acompanhamento rápido.

    /relatorio completo:
      Pacote ideal para avaliação diária:
      1) Selftest
      2) Diagnóstico
      3) Exposição/central
      4) Health + funil + eventos + resumo de todos os bots

    /relatorio <bot>:
      Health + funil + eventos + resumo de um único bot.
    """
    mode = (mode or "curto").lower().strip()
    complete = mode in {"completo", "full", "complete", "diario", "diário", "auditoria"}

    if bot_key:
        return build_single_bot_report(bot_key, complete=True)

    if not complete:
        return build_central_status_text()

    parts = [
        "📦 PACOTE DE AVALIAÇÃO DIÁRIA - CENTRAL QUANT",
        f"Data/hora: {data_hora_sp_str()}",
        "",
        "==============================\n1) SELFTEST\n==============================",
        build_selftest_report(),
        "",
        "==============================\n2) DIAGNÓSTICO\n==============================",
        build_diagnostic_report(),
        "",
        "==============================\n3) CENTRAL / EXPOSIÇÃO\n==============================",
        build_central_status_text(),
        "",
        "==============================\n4) CHECKLIST COMPLETO DOS BOTS\n==============================",
    ]

    for key in BOT_CONFIGS.keys():
        parts.append(build_single_bot_report(key, complete=True))

    return "\n\n==============================\n".join(parts)


def build_diagnostic_report():
    status = central_watchdog_status()
    exposure_snapshot = central_exposure_snapshot()
    by_bot_exposure = exposure_snapshot.get("by_bot", {}) or {}
    reasons = list(status.get("reasons", []) or [])
    warnings = []
    checks = []
    mem = memory_snapshot("diagnostic_memory", store=True)

    all_enabled_loaded = True
    all_watchlists_ok = True
    all_cycles_ok = True
    all_errors_ok = True

    for key, cfg in BOT_CONFIGS.items():
        b = bot_health(key, cfg)
        h = b.get("health", {}) or {}
        if not b.get("enabled"):
            continue

        loaded = bool(b.get("loaded"))
        scanner_ok = b.get("minutes_since_scanner") is not None and b.get("minutes_since_scanner") <= WATCHDOG_THRESHOLD_MINUTES
        management_ok = b.get("minutes_since_management") is not None and b.get("minutes_since_management") <= WATCHDOG_THRESHOLD_MINUTES
        error_ok = not (b.get("last_error") and not is_benign_bingx_quote_error(b.get("last_error"))) and not b.get("load_error")
        wl_total = h.get("watchlist_total")
        wl_valid = h.get("watchlist_valid")
        wl_invalid = h.get("watchlist_invalid", []) or []
        watchlist_ok = (wl_total is None) or (wl_valid == wl_total and not wl_invalid)
        warning = _clean_warning(h.get("last_warning"))

        all_enabled_loaded = all_enabled_loaded and loaded
        all_cycles_ok = all_cycles_ok and scanner_ok and management_ok
        all_errors_ok = all_errors_ok and error_ok
        all_watchlists_ok = all_watchlists_ok and watchlist_ok

        if warning and not is_benign_bingx_quote_error(warning):
            warnings.append(f"{key}: {warning}")

        checks.append(
            f"{key}: "
            f"loaded={'✅' if loaded else '❌'} | "
            f"scanner={'✅' if scanner_ok else '❌'} {b.get('minutes_since_scanner')}m | "
            f"gestão={'✅' if management_ok else '❌'} {b.get('minutes_since_management')}m | "
            f"WL={'✅' if watchlist_ok else '❌'} {wl_valid}/{wl_total} | "
            f"erro={'✅' if error_ok else '❌'} | "
            f"pos={(by_bot_exposure.get(key) or {}).get('total')}"
        )

    total_pos = int(exposure_snapshot.get("total_positions_open") or 0)
    short_pos = int(exposure_snapshot.get("short_positions_open") or 0)
    long_pos = int(exposure_snapshot.get("long_positions_open") or 0)
    open_runners = exposure_snapshot.get("open_runners") or {}
    best = exposure_snapshot.get("best_open_runner") or {}

    risk_notes = []
    if total_pos >= 50:
        risk_notes.append(f"Muitas posições abertas: {total_pos}.")
    if total_pos and short_pos / max(total_pos, 1) >= 0.80:
        risk_notes.append(f"Exposição muito SHORT: {short_pos}/{total_pos}.")
    if total_pos and long_pos / max(total_pos, 1) >= 0.80:
        risk_notes.append(f"Exposição muito LONG: {long_pos}/{total_pos}.")
    if mem.get("usage_pct") and mem.get("usage_pct") >= MEMORY_ALERT_THRESHOLD_PCT:
        risk_notes.append(f"Memória alta: {mem.get('rss_mb')} MB ({mem.get('usage_pct')}%).")

    memory_ok = not mem.get("usage_pct") or mem.get("usage_pct") < 95
    apto = bool(status.get("ok")) and all_enabled_loaded and all_cycles_ok and all_errors_ok and all_watchlists_ok and memory_ok
    resultado = "✅ APTO PARA OPERAR" if apto else "⚠️ ATENÇÃO / VERIFICAR"

    lines = [
        "🩺 DIAGNÓSTICO CENTRAL QUANT",
        f"Data/hora: {data_hora_sp_str()}",
        f"Resultado: {resultado}",
        "",
        "CHECKS GERAIS",
        f"Central status: {status.get('status')}",
        f"Bots carregados: {'✅' if all_enabled_loaded else '❌'}",
        f"Scanners/Gestão recentes: {'✅' if all_cycles_ok else '❌'}",
        f"Sem erros críticos: {'✅' if all_errors_ok else '❌'}",
        f"Watchlists válidas: {'✅' if all_watchlists_ok else '❌'}",
        f"Memória: {mem.get('rss_mb')} MB ({mem.get('usage_pct')}%)",
        f"Execução real: {'ATIVA' if ENABLE_REAL_TRADING else 'BLOQUEADA'} | Modo: {EXECUTION_MODE}",
        "",
        "EXPOSIÇÃO",
        f"Total: {total_pos} | LONG: {long_pos} | SHORT: {short_pos}",
        (
            "Runners: "
            f"1R={open_runners.get('runners_1r_open', 0)} | "
            f"2R={open_runners.get('runners_2r_open', 0)} | "
            f"3R={open_runners.get('runners_3r_open', 0)} | "
            f"5R={open_runners.get('runners_5r_open', 0)} | "
            f"10R={open_runners.get('runners_10r_open', 0)}"
        ),
    ]

    if best:
        lines += [
            f"Melhor runner: {best.get('bot')} {best.get('symbol')} {best.get('side')} {best.get('setup')} | "
            f"{best.get('runner_pct')}% | {best.get('runner_r')}R"
        ]

    if reasons:
        lines += ["", "MOTIVOS DO WATCHDOG"] + [f"- {r}" for r in reasons]
    if warnings:
        lines += ["", "WARNINGS RELEVANTES"] + [f"- {w}" for w in warnings]
    if risk_notes:
        lines += ["", "OBSERVAÇÕES DE RISCO"] + [f"- {r}" for r in risk_notes]

    lines += ["", "BOTS"] + checks
    return "\n".join(lines)


def build_selftest_report():
    status = central_watchdog_status()
    exposure_snapshot = central_exposure_snapshot()
    by_bot_exposure = exposure_snapshot.get("by_bot", {}) or {}

    tests = []
    bot_lines = []
    passed = 0
    total = 0

    def add_test(name, ok, detail=""):
        nonlocal passed, total
        total += 1
        if ok:
            passed += 1
        tests.append(f"{'✅' if ok else '❌'} {name}{(' — ' + str(detail)) if detail else ''}")

    enabled_count = 0
    loaded_count = 0
    scanner_ok_count = 0
    management_ok_count = 0
    watchlist_ok_count = 0
    error_ok_count = 0

    for key, cfg in BOT_CONFIGS.items():
        b = bot_health(key, cfg)
        h = b.get("health", {}) or {}
        if not b.get("enabled"):
            continue

        enabled_count += 1
        loaded = bool(b.get("loaded"))
        if loaded:
            loaded_count += 1

        scanner_min = b.get("minutes_since_scanner")
        management_min = b.get("minutes_since_management")
        scanner_ok = scanner_min is not None and scanner_min <= WATCHDOG_THRESHOLD_MINUTES
        management_ok = management_min is not None and management_min <= WATCHDOG_THRESHOLD_MINUTES
        error_ok = not (b.get("last_error") and not is_benign_bingx_quote_error(b.get("last_error"))) and not b.get("load_error")

        wl_total = h.get("watchlist_total")
        wl_valid = h.get("watchlist_valid")
        wl_invalid = h.get("watchlist_invalid", []) or []
        watchlist_ok = (wl_total is None) or (wl_valid == wl_total and not wl_invalid)

        if scanner_ok:
            scanner_ok_count += 1
        if management_ok:
            management_ok_count += 1
        if watchlist_ok:
            watchlist_ok_count += 1
        if error_ok:
            error_ok_count += 1

        warning = _clean_warning(h.get("last_warning") or b.get("last_warning"))
        exp = by_bot_exposure.get(key, {}) or {}
        runner_r = exp.get("best_open_runner", {}).get("runner_r") if exp.get("best_open_runner") else None

        bot_lines.append(
            f"{key:<9} "
            f"load={'OK' if loaded else 'ERRO'} | "
            f"scan={'OK' if scanner_ok else 'FALHA'} {scanner_min}m | "
            f"gestão={'OK' if management_ok else 'FALHA'} {management_min}m | "
            f"WL={'OK' if watchlist_ok else 'FALHA'} {wl_valid}/{wl_total} | "
            f"erro={'OK' if error_ok else 'ERRO'} | "
            f"pos={exp.get('total')} | "
            f"runner={safe_round(runner_r, 2, 0)}R"
            + (f" | warning={warning}" if warning and not is_benign_bingx_quote_error(warning) else "")
        )

    add_test("Bots habilitados carregados", enabled_count > 0 and loaded_count == enabled_count, f"{loaded_count}/{enabled_count}")
    add_test("Scanners recentes", enabled_count > 0 and scanner_ok_count == enabled_count, f"{scanner_ok_count}/{enabled_count}")
    add_test("Gestões recentes", enabled_count > 0 and management_ok_count == enabled_count, f"{management_ok_count}/{enabled_count}")
    add_test("Watchlists válidas", enabled_count > 0 and watchlist_ok_count == enabled_count, f"{watchlist_ok_count}/{enabled_count}")
    add_test("Sem erros críticos", enabled_count > 0 and error_ok_count == enabled_count, f"{error_ok_count}/{enabled_count}")
    add_test("Central watchdog OK", bool(status.get("ok")), status.get("status"))

    total_pos = int(exposure_snapshot.get("total_positions_open") or 0)
    long_pos = int(exposure_snapshot.get("long_positions_open") or 0)
    short_pos = int(exposure_snapshot.get("short_positions_open") or 0)
    open_runners = exposure_snapshot.get("open_runners") or {}
    best = exposure_snapshot.get("best_open_runner") or {}

    add_test("Exposure disponível", "total_positions_open" in exposure_snapshot, f"pos={total_pos}")
    add_test("Runners calculados", isinstance(open_runners, dict), f"3R={open_runners.get('runners_3r_open', 0)}")
    add_test("Relatório central gera texto", bool(build_central_status_text()), "OK")
    add_test("Diagnóstico gera texto", bool(build_diagnostic_report()), "OK")
    # Testes de execução/BingX sem enviar ordens. Validam geração de /live e /sync.
    live_txt = build_live_report() if "build_live_report" in globals() else ""
    sync_txt = build_sync_report() if "build_sync_report" in globals() else ""
    add_test("Live report gera texto", bool(live_txt), "OK")
    add_test("Sync Central x BingX gera texto", bool(sync_txt), "OK")

    mem = memory_snapshot("selftest_memory", store=True)
    mem_ok = (mem.get("usage_pct") or 0) < 95
    add_test("Memória abaixo de 95%", mem_ok, f"{mem.get('rss_mb')} MB | {mem.get('usage_pct')}%")

    risk_notes = []
    if total_pos >= 50:
        risk_notes.append(f"Muitas posições abertas: {total_pos}.")
    if total_pos and short_pos / max(total_pos, 1) >= 0.80:
        risk_notes.append(f"Exposição muito SHORT: {short_pos}/{total_pos}.")
    if total_pos and long_pos / max(total_pos, 1) >= 0.80:
        risk_notes.append(f"Exposição muito LONG: {long_pos}/{total_pos}.")
    if not mem_ok:
        risk_notes.append(f"Memória alta: {mem.get('rss_mb')} MB ({mem.get('usage_pct')}%).")

    critical_ok = passed == total and bool(status.get("ok"))
    result = "✅ SELFTEST APROVADO" if critical_ok else "⚠️ SELFTEST COM PENDÊNCIAS"

    lines = [
        "🧪 SELFTEST CENTRAL QUANT",
        f"Data/hora: {data_hora_sp_str()}",
        f"Resultado: {result}",
        f"Testes: {passed}/{total} aprovados",
        "",
        "CHECKS",
        *tests,
        "",
        "EXPOSIÇÃO",
        f"Total: {total_pos} | LONG: {long_pos} | SHORT: {short_pos}",
        (
            "Runners: "
            f"1R={open_runners.get('runners_1r_open', 0)} | "
            f"2R={open_runners.get('runners_2r_open', 0)} | "
            f"3R={open_runners.get('runners_3r_open', 0)} | "
            f"5R={open_runners.get('runners_5r_open', 0)} | "
            f"10R={open_runners.get('runners_10r_open', 0)}"
        ),
    ]

    if best:
        lines.append(
            f"Melhor runner: {best.get('bot')} {best.get('symbol')} {best.get('side')} {best.get('setup')} | "
            f"{best.get('runner_pct')}% | {best.get('runner_r')}R"
        )

    if risk_notes:
        lines += ["", "OBSERVAÇÕES DE RISCO"] + [f"- {r}" for r in risk_notes]

    lines += ["", "BOTS"] + bot_lines

    if critical_ok:
        lines += ["", "CONCLUSÃO", "Sistema pronto para operar. Monitorar apenas os alertas de risco direcional."]
    else:
        lines += ["", "CONCLUSÃO", "Há pendências técnicas. Verifique os itens marcados com ❌ antes de confiar nos robôs."]

    return "\n".join(lines)


def parse_report_command(text: str):
    raw = (text or "").strip()
    if not raw:
        return None
    raw_no_mention = raw.split("@", 1)[0] if raw.startswith("/") and "@" in raw.split()[0] else raw
    parts = raw_no_mention.lower().split()
    if not parts or parts[0] not in REPORT_COMMANDS:
        return None

    mode = "completo" if parts[0] in {"/relatoriocompleto", "/relatorio_completo", "/auditoria", "/diario", "/diário"} else "curto"
    bot_key = None
    for p in parts[1:]:
        p = p.strip().lower().replace("/", "")
        if p in {"completo", "full", "complete", "diario", "diário", "auditoria"}:
            mode = "completo"
        elif p in {"curto", "resumido", "short"}:
            mode = "curto"
        elif p in REPORT_BOT_ALIASES:
            bot_key = REPORT_BOT_ALIASES[p]
            mode = "completo"
    return mode, bot_key




# ==========================================================
# EXECUTIVE DASHBOARD / RISK / HISTORY / META SUPERVISOR
# ==========================================================

def _compact_symbol(symbol):
    s = str(symbol or "").upper()
    s = s.replace("/USDT:USDT", "USDT").replace("/USDT", "USDT").replace(":USDT", "")
    return s


def _symbol_sector(symbol):
    s = _compact_symbol(symbol)
    if s in {"BTCUSDT"}:
        return "BTC"
    if s in {"ETHUSDT"}:
        return "ETH"
    if s in {"SOLUSDT", "BNBUSDT", "ADAUSDT", "AVAXUSDT", "SUIUSDT", "APTUSDT", "NEARUSDT", "ATOMUSDT", "DOTUSDT", "ALGOUSDT", "HBARUSDT", "TRXUSDT", "BCHUSDT", "LTCUSDT"}:
        return "Layer1"
    if s in {"ARBUSDT", "OPUSDT"}:
        return "Layer2"
    if s in {"DOGEUSDT", "1000PEPEUSDT", "WIFUSDT", "1000BONKUSDT", "FLOKIUSDT"}:
        return "Memecoin"
    if s in {"INJUSDT", "RUNEUSDT", "UNIUSDT", "AAVEUSDT", "JUPUSDT"}:
        return "DeFi"
    if s in {"FETUSDT", "WLDUSDT", "TAOUSDT"}:
        return "AI"
    if s in {"ONDOUSDT", "PENDLEUSDT"}:
        return "RWA/Yield"
    if s in {"LINKUSDT"}:
        return "Oracle"
    if s in {"FILUSDT"}:
        return "Storage"
    if s in {"HYPEUSDT"}:
        return "Exchange/Perp"
    if s in {"ENAUSDT"}:
        return "Stable/Yield"
    if s in {"ETCUSDT"}:
        return "Legacy"
    return "Outros"


def _all_open_positions_payload():
    rows = []
    for key, module in LOADED_BOTS.items():
        for p in get_open_positions_from_module(module, key=key):
            symbol = _compact_symbol(p.get("symbol") or p.get("ativo") or p.get("pair"))
            side = str(p.get("side", p.get("direction", ""))).upper()
            rows.append({
                "bot": key,
                "symbol": symbol,
                "sector": _symbol_sector(symbol),
                "side": side,
                "setup": p.get("setup") or p.get("setup_label"),
                "runner_r": round(_position_runner_r(p), 4),
                "runner_pct": round(_position_runner_pct(p), 4),
                "entry": p.get("entry") or p.get("entrada"),
                "stop": p.get("stop") or p.get("sl") or p.get("stop_atual"),
                "tp50": p.get("tp50"),
            })
    return rows


def central_health_score_payload():
    status = central_watchdog_status()
    exposure_snapshot = central_exposure_snapshot()
    mem = memory_snapshot("healthscore_memory", store=True)
    score = 100
    penalties = []

    if not status.get("ok"):
        n = min(30, 10 * len(status.get("reasons", []) or []))
        score -= n
        penalties.append(f"Watchdog com pendências: -{n}")

    enabled = 0
    loaded = 0
    stale = 0
    invalid_wl = 0
    errors = 0

    for key, cfg in BOT_CONFIGS.items():
        b = bot_health(key, cfg)
        h = b.get("health", {}) or {}
        if not b.get("enabled"):
            continue
        enabled += 1
        if b.get("loaded"):
            loaded += 1
        if b.get("last_error") and not is_benign_bingx_quote_error(b.get("last_error")):
            errors += 1
        ms = b.get("minutes_since_scanner")
        mm = b.get("minutes_since_management")
        if ms is None or mm is None or ms > WATCHDOG_THRESHOLD_MINUTES or mm > WATCHDOG_THRESHOLD_MINUTES:
            stale += 1
        wl_total = h.get("watchlist_total")
        wl_valid = h.get("watchlist_valid")
        wl_invalid = h.get("watchlist_invalid", []) or []
        if wl_total is not None and (wl_valid != wl_total or wl_invalid):
            invalid_wl += 1

    if enabled and loaded < enabled:
        n = min(30, (enabled - loaded) * 10)
        score -= n
        penalties.append(f"Bots não carregados: -{n}")

    if stale:
        n = min(25, stale * 8)
        score -= n
        penalties.append(f"Ciclos atrasados: -{n}")

    if errors:
        n = min(25, errors * 10)
        score -= n
        penalties.append(f"Erros críticos: -{n}")

    if invalid_wl:
        n = min(15, invalid_wl * 5)
        score -= n
        penalties.append(f"Watchlists inválidas: -{n}")

    usage = mem.get("usage_pct") or 0
    if usage >= 95:
        score -= 20
        penalties.append("Memória >=95%: -20")
    elif usage >= MEMORY_ALERT_THRESHOLD_PCT:
        score -= 10
        penalties.append("Memória alta: -10")

    total_pos = int(exposure_snapshot.get("total_positions_open") or 0)
    long_pos = int(exposure_snapshot.get("long_positions_open") or 0)
    short_pos = int(exposure_snapshot.get("short_positions_open") or 0)

    if total_pos >= GLOBAL_RISK_MAX_POSITIONS:
        score -= 10
        penalties.append("Muitas posições abertas: -10")

    if total_pos:
        side_conc = max(long_pos, short_pos) / max(total_pos, 1) * 100
        if side_conc >= 95:
            score -= 10
            penalties.append("Concentração direcional extrema: -10")
        elif side_conc >= GLOBAL_RISK_MAX_SIDE_CONCENTRATION_PCT:
            score -= 5
            penalties.append("Concentração direcional alta: -5")

    score = max(0, min(100, int(round(score))))
    if score >= 90:
        label = "EXCELENTE"
    elif score >= 75:
        label = "BOM"
    elif score >= 60:
        label = "ATENÇÃO"
    else:
        label = "CRÍTICO"

    return {
        "score": score,
        "label": label,
        "penalties": penalties,
        "memory": mem,
        "enabled_bots": enabled,
        "loaded_bots": loaded,
        "total_positions": total_pos,
        "long_positions": long_pos,
        "short_positions": short_pos,
    }


def build_healthscore_report():
    p = central_health_score_payload()
    lines = [
        "🧭 HEALTH SCORE CENTRAL QUANT",
        f"Data/hora: {data_hora_sp_str()}",
        "",
        f"Score: {p.get('score')}/100",
        f"Classificação: {p.get('label')}",
        "",
        f"Bots carregados: {p.get('loaded_bots')}/{p.get('enabled_bots')}",
        f"Memória: {p.get('memory', {}).get('rss_mb')} MB ({p.get('memory', {}).get('usage_pct')}%)",
        f"Exposição: {p.get('total_positions')} posições | LONG {p.get('long_positions')} | SHORT {p.get('short_positions')}",
    ]
    penalties = p.get("penalties") or []
    if penalties:
        lines += ["", "Perdas de pontos:"] + [f"- {x}" for x in penalties]
    else:
        lines += ["", "Sem penalidades relevantes."]
    return "\n".join(lines)


def build_heatmap_report():
    rows = _all_open_positions_payload()
    by_sector = {}
    by_symbol = {}
    for r in rows:
        sec = r.get("sector") or "Outros"
        sym = r.get("symbol") or "N/A"
        side = r.get("side") or "N/A"
        by_sector.setdefault(sec, {"total": 0, "long": 0, "short": 0})
        by_symbol.setdefault(sym, {"total": 0, "long": 0, "short": 0, "bots": set()})
        by_sector[sec]["total"] += 1
        by_symbol[sym]["total"] += 1
        by_symbol[sym]["bots"].add(r.get("bot"))
        if side in {"LONG", "BUY"}:
            by_sector[sec]["long"] += 1
            by_symbol[sym]["long"] += 1
        elif side in {"SHORT", "SELL"}:
            by_sector[sec]["short"] += 1
            by_symbol[sym]["short"] += 1

    lines = [
        "🔥 HEAT MAP DA CARTEIRA",
        f"Data/hora: {data_hora_sp_str()}",
        f"Posições abertas: {len(rows)}",
        "",
        "Por setor:",
    ]
    for sec, v in sorted(by_sector.items(), key=lambda kv: kv[1]["total"], reverse=True):
        lines.append(f"{sec:<15} total={v['total']} | L={v['long']} | S={v['short']}")

    lines += ["", "Top ativos:"]
    for sym, v in sorted(by_symbol.items(), key=lambda kv: kv[1]["total"], reverse=True)[:20]:
        bots = ",".join(sorted([str(x) for x in v["bots"] if x]))
        lines.append(f"{sym:<16} total={v['total']} | L={v['long']} | S={v['short']} | bots={bots}")

    return "\n".join(lines)




# ==========================================================
# OMS / DECISION LOG / TIMELINE / SHADOW POSITIONS
# ==========================================================

TRADE_STATES = {
    "NEW", "SIGNALLED", "VERIFY", "ORDER_SENT", "FILLED",
    "TP50", "BE", "RUNNER", "CLOSED", "ERROR", "DENIED"
}


def _json_default(value):
    try:
        if isinstance(value, Path):
            return str(value)
    except Exception:
        pass
    try:
        return str(value)
    except Exception:
        return None


def _append_jsonl(path, item):
    try:
        path.parent.mkdir(exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(item, ensure_ascii=False, default=_json_default) + "\n")
        return True
    except Exception as exc:
        print(f"ERRO append_jsonl {path}:", exc)
        return False


def _read_jsonl_tail(path, limit=50):
    try:
        if not path.exists():
            return []
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()[-int(limit):]
        rows = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                rows.append({"raw": line})
        return rows
    except Exception as exc:
        print(f"ERRO read_jsonl_tail {path}:", exc)
        return []


def _read_json_file(path, default):
    try:
        if not path.exists():
            return default
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _write_json_file(path, payload):
    try:
        path.parent.mkdir(exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, default=_json_default)
        return True
    except Exception as exc:
        print(f"ERRO write_json_file {path}:", exc)
        return False


def generate_trade_id(bot=None, symbol=None, side=None):
    bot = str(bot or "CENTRAL").upper().replace(" ", "")[:12]
    symbol = normalize_symbol_for_risk(symbol or "NA") if "normalize_symbol_for_risk" in globals() else str(symbol or "NA").upper()
    side = str(side or "").upper()[:5]
    stamp = agora_sp().strftime("%Y%m%d-%H%M%S")
    suffix = uuid.uuid4().hex[:6].upper()
    return f"{bot}-{stamp}-{symbol}-{side}-{suffix}".replace("--", "-")


def _event_trade_id(bot=None, symbol=None, side=None, existing=None):
    if existing:
        return str(existing)
    return generate_trade_id(bot, symbol, side)


def _history_payload_from_event(event_type, bot=None, symbol=None, side=None, trade_id=None, state=None, details=None):
    source_payload = dict(details or {}) if isinstance(details, dict) else {}
    source_payload.update({
        "event_type": str(event_type or "EVENT").upper(),
        "bot": str(bot or source_payload.get("bot") or "").upper(),
        "symbol": normalize_symbol_for_risk(symbol or source_payload.get("symbol")),
        "side": str(side or source_payload.get("side") or "").upper(),
        "trade_id": str(trade_id or source_payload.get("trade_id") or ""),
        "state": str(state or source_payload.get("state") or "").upper(),
        "timestamp": source_payload.get("timestamp") or source_payload.get("ts") or data_hora_sp_str(),
        "ts": source_payload.get("timestamp") or source_payload.get("ts") or data_hora_sp_str(),
        "setup": source_payload.get("setup"),
        "result": source_payload.get("result") or source_payload.get("decision") or source_payload.get("status"),
        "pnl_pct": source_payload.get("pnl_pct") or source_payload.get("result_pct") or source_payload.get("pnl"),
    })
    return source_payload


def _emit_history_event(event_type, bot=None, symbol=None, side=None, trade_id=None, state=None, details=None):
    try:
        import history_manager as super_history_manager
    except Exception:
        return None

    try:
        payload = _history_payload_from_event(event_type, bot=bot, symbol=symbol, side=side, trade_id=trade_id, state=state, details=details)
        normalized_event = str(event_type or "EVENT").upper()
        mapping = {
            "SIGNAL": "SIGNAL_CREATED",
            "ENTRY": "TRADE_OPENED",
            "TP50": "TP50_HIT",
            "BE": "BREAKEVEN",
            "TRAILING": "TRAILING_UPDATED",
            "STOP": "TRADE_CLOSED",
            "CLOSE": "TRADE_CLOSED",
            "DENY": "TRADE_BLOCKED",
            "ALLOW": "RISK_ALLOW",
        }
        history_event_type = mapping.get(normalized_event, normalized_event)
        return super_history_manager.log_event(
            history_event_type,
            payload,
            source=str(payload.get("bot") or "central").lower(),
            trade_id=payload.get("trade_id") or None,
        )
    except Exception as exc:
        print(f"ERRO history hook {event_type}: {exc}")
        return None


def append_timeline_event(event_type, bot=None, symbol=None, side=None, trade_id=None, state=None, details=None):
    item = {
        "ts": data_hora_sp_str(),
        "epoch": time.time(),
        "trade_id": _event_trade_id(bot, symbol, side, trade_id),
        "event": str(event_type or "EVENT").upper(),
        "state": str(state or event_type or "EVENT").upper(),
        "bot": str(bot or "").upper(),
        "symbol": normalize_symbol_for_risk(symbol),
        "side": str(side or "").upper(),
        "details": details or {},
    }
    _append_jsonl(CENTRAL_TIMELINE_LOG_FILE, item)
    _emit_history_event(event_type, bot=bot, symbol=symbol, side=side, trade_id=item.get("trade_id"), state=item.get("state"), details=item)
    return item



def _policy_linker_add_code(codes, value):
    """
    V2.1.2 — normaliza códigos de policy sem duplicar.
    Aceita strings, listas e dicts vindos do Executive Policy Manager/Priority.
    """
    if value is None:
        return

    if isinstance(value, (list, tuple, set)):
        for item in value:
            _policy_linker_add_code(codes, item)
        return

    if isinstance(value, dict):
        for key in [
            "code", "policy_code", "policy_code_normalized", "dominant_code",
            "dominant_policy_code", "id", "name",
        ]:
            if value.get(key):
                _policy_linker_add_code(codes, value.get(key))
        return

    text = str(value or "").strip().upper()
    if not text:
        return

    # Evita gravar mensagens inteiras como se fossem códigos.
    if len(text) > 80:
        return

    # Normalização leve para valores separados por vírgula.
    if "," in text:
        for part in text.split(","):
            _policy_linker_add_code(codes, part)
        return

    if text not in codes:
        codes.append(text)


def extract_policy_decision_link(decision_result=None, payload=None):
    """
    Executive Policy Decision Linker V2.1.2.

    Objetivo:
    - anexar ao decision_log quais policies influenciaram a decisão;
    - preservar também policies ativas como contexto;
    - não alterar decisão, risco, lote ou execução.
    """
    result = decision_result if isinstance(decision_result, dict) else {}
    source_payload = payload if isinstance(payload, dict) else {}

    evaluation = result.get("executive_policy") or source_payload.get("executive_policy") or {}
    if not isinstance(evaluation, dict):
        evaluation = {}

    priority = evaluation.get("priority") if isinstance(evaluation.get("priority"), dict) else {}
    sync = evaluation.get("sync") if isinstance(evaluation.get("sync"), dict) else {}

    policy_codes = []
    active_policy_codes = []

    # Códigos que realmente apareceram como aplicados/influentes.
    for key in [
        "policy_codes",
        "applied_policy_codes",
        "blocked_policy_codes",
        "matched_policy_codes",
        "applied_policies",
        "policies_applied",
        "dominant_policy_code",
        "dominant_code",
        "dominant_policy",
    ]:
        _policy_linker_add_code(policy_codes, evaluation.get(key))

    for key in [
        "policy_codes",
        "applied_policy_codes",
        "applied_policies",
        "dominant_policy_code",
        "dominant_code",
        "dominant_policy",
    ]:
        _policy_linker_add_code(policy_codes, priority.get(key))

    # Códigos ativos no momento da avaliação: contexto, não necessariamente influência.
    for key in ["active_codes", "active_policy_codes", "policies", "active_policies"]:
        _policy_linker_add_code(active_policy_codes, sync.get(key))
        _policy_linker_add_code(active_policy_codes, evaluation.get(key))

    # Fallback conservador: se a policy bloqueou/restringiu mas o manager não
    # informou applied_policies, usa a dominante; se nem dominante existir, usa
    # active_codes apenas como linked_by=active_context_fallback.
    linked_by = "explicit_applied_policies" if policy_codes else "none"
    if not policy_codes and (evaluation.get("allowed") is False or evaluation.get("size_multiplier") not in (None, 1, 1.0) or evaluation.get("max_risk_pct") is not None):
        for key in ["dominant_policy_code", "dominant_code", "dominant_policy"]:
            _policy_linker_add_code(policy_codes, evaluation.get(key))
            _policy_linker_add_code(policy_codes, priority.get(key))
        if policy_codes:
            linked_by = "dominant_policy_fallback"

    if not policy_codes and active_policy_codes and (evaluation.get("allowed") is False):
        for code in active_policy_codes:
            _policy_linker_add_code(policy_codes, code)
        linked_by = "active_context_fallback_blocked_decision"

    return {
        "version": "2026-07-05-POLICY-DECISION-LINKER-V2.1.2",
        "linked": bool(policy_codes),
        "linked_by": linked_by,
        "policy_codes": policy_codes,
        "active_policy_codes": active_policy_codes,
        "dominant_policy_code": (
            evaluation.get("dominant_policy_code")
            or evaluation.get("dominant_code")
            or priority.get("dominant_policy_code")
            or priority.get("dominant_code")
        ),
        "source": evaluation.get("source") or "unknown",
    }


def enrich_decision_result_with_policy_links(decision_result=None, payload=None):
    """
    V2.1.7 — Top-Level Policy Link Persistence.

    Garante que os vínculos de policy fiquem no nível principal do objeto
    usado pelo append_decision_log(), pelo History wrapper e pela resposta HTTP.

    A resposta do Executive Policy Manager já contém executive_policy.policy_codes,
    mas o Policy Learning V2 precisa ler policy_codes diretamente no JSONL.
    Esta função não altera ALLOW/DENY, risco, lote ou execução.
    """
    if not isinstance(decision_result, dict):
        return decision_result

    source_payload = payload if isinstance(payload, dict) else {}
    policy_link = extract_policy_decision_link(decision_result, source_payload)

    executive_policy = decision_result.get("executive_policy")
    if not isinstance(executive_policy, dict):
        executive_policy = source_payload.get("executive_policy") if isinstance(source_payload.get("executive_policy"), dict) else {}

    # Fallback explícito: se o linker não conseguiu montar policy_codes, usa
    # diretamente os campos já validados dentro de executive_policy.
    if not policy_link.get("policy_codes") and isinstance(executive_policy, dict):
        fallback_codes = []
        for key in [
            "policy_codes",
            "applied_policies",
            "applied_policy_codes",
            "dominant_policy_code",
            "dominant_code",
        ]:
            _policy_linker_add_code(fallback_codes, executive_policy.get(key))

        nested_linker = executive_policy.get("policy_linker") if isinstance(executive_policy.get("policy_linker"), dict) else {}
        for key in ["policy_codes", "applied_policies", "dominant_policy_code"]:
            _policy_linker_add_code(fallback_codes, nested_linker.get(key))

        if fallback_codes:
            policy_link["policy_codes"] = fallback_codes
            policy_link["linked"] = True
            policy_link["linked_by"] = "executive_policy_top_level_fallback"

    if not policy_link.get("active_policy_codes") and isinstance(executive_policy, dict):
        active_codes = []
        for key in ["active_policy_codes", "active_codes"]:
            _policy_linker_add_code(active_codes, executive_policy.get(key))
        if active_codes:
            policy_link["active_policy_codes"] = active_codes

    if not policy_link.get("dominant_policy_code") and isinstance(executive_policy, dict):
        policy_link["dominant_policy_code"] = (
            executive_policy.get("dominant_policy_code")
            or executive_policy.get("dominant_code")
        )

    policy_codes = policy_link.get("policy_codes") or []
    active_policy_codes = policy_link.get("active_policy_codes") or []

    decision_result["policy_codes"] = policy_codes
    decision_result["active_policy_codes"] = active_policy_codes
    decision_result["applied_policies"] = policy_codes
    decision_result["dominant_policy_code"] = policy_link.get("dominant_policy_code")
    decision_result["policy_linker"] = policy_link

    # Mantém o executive_policy também enriquecido, para compatibilidade com
    # relatórios humanos e wrappers que mesclam payload/result.
    if isinstance(executive_policy, dict):
        executive_policy.setdefault("policy_codes", policy_codes)
        executive_policy.setdefault("active_policy_codes", active_policy_codes)
        executive_policy.setdefault("applied_policies", policy_codes)
        executive_policy.setdefault("dominant_policy_code", policy_link.get("dominant_policy_code"))
        executive_policy.setdefault("policy_linker", policy_link)
        decision_result["executive_policy"] = executive_policy

    return decision_result


def append_decision_log(payload, decision_result):
    payload = payload or {}
    result = decision_result or {}
    bot = str(result.get("bot") or payload.get("bot") or "").upper()
    symbol = normalize_symbol_for_risk(result.get("symbol") or payload.get("symbol"))
    side = str(result.get("side") or payload.get("side") or "").upper()
    trade_id = payload.get("trade_id") or payload.get("client_trade_id") or generate_trade_id(bot, symbol, side)
    if isinstance(trade_id, dict):
        trade_id = (
            trade_id.get("trade_id")
            or trade_id.get("ALLOWED")
            or trade_id.get("DENIED")
            or trade_id.get("id")
            or str(trade_id)
        )

    trade_id = str(trade_id)
    allowed = bool(result.get("allowed"))
    state = "VERIFY" if allowed and str(result.get("mode") or "").upper() == "VERIFY" else ("DENIED" if not allowed else str(result.get("mode") or "ALLOW").upper())

    # V2.1.7 — Top-Level Policy Link Persistence
    # Enriquecimento ocorre antes de montar o item persistido, garantindo que
    # o JSONL, o History wrapper e a resposta HTTP tenham os mesmos links.
    enrich_decision_result_with_policy_links(result, payload)
    policy_link = result.get("policy_linker") if isinstance(result.get("policy_linker"), dict) else extract_policy_decision_link(result, payload)

    item = {
        "ts": data_hora_sp_str(),
        "epoch": time.time(),
        "trade_id": trade_id,
        "bot": bot,
        "symbol": symbol,
        "side": side,
        "mode": result.get("mode") or payload.get("mode") or EXECUTION_MODE,
        "decision": result.get("decision") or ("ALLOW" if allowed else "DENY"),
        "allowed": allowed,
        "reasons": result.get("reasons") or [],
        "warnings": result.get("warnings") or [],
        "policy_codes": policy_link.get("policy_codes") or [],
        "active_policy_codes": policy_link.get("active_policy_codes") or [],
        "applied_policies": policy_link.get("policy_codes") or [],
        "dominant_policy_code": policy_link.get("dominant_policy_code"),
        "policy_linker": policy_link,
        "executive_policy": result.get("executive_policy") or payload.get("executive_policy") or {},
        "bingx_divergence": result.get("bingx_divergence") or {},
        "score": payload.get("score"),
        "setup": payload.get("setup"),
        "risk_pct": payload.get("risk_pct"),
        "notional_usdt": payload.get("notional_usdt"),
        "exposure": result.get("exposure") or {},
    }
    _append_jsonl(CENTRAL_DECISION_LOG_FILE, item)

    # V2.1.5 — também persiste no decision_log real do History Manager
    # quando ele usa DATA_DIR diferente do main.py. No Render, o Learning V2.1.4
    # detectou /data/decision_log.jsonl como fonte com mais decisões; por isso
    # gravamos o mesmo item lá também.
    try:
        import history_manager as _policy_history_manager
        history_decision_file = getattr(_policy_history_manager, "DECISION_LOG_FILE", None)
        if history_decision_file:
            history_decision_file = Path(history_decision_file)
            if history_decision_file.resolve() != Path(CENTRAL_DECISION_LOG_FILE).resolve():
                _append_jsonl(history_decision_file, item)
    except Exception as exc:
        print("AVISO policy linker history decision log:", exc)

    try:
        result["policy_codes"] = item.get("policy_codes") or []
        result["active_policy_codes"] = item.get("active_policy_codes") or []
        result["applied_policies"] = item.get("applied_policies") or []
        result["dominant_policy_code"] = item.get("dominant_policy_code")
        result["policy_linker"] = item.get("policy_linker") or {}
    except Exception:
        pass
    append_timeline_event("RISK_ALLOW" if allowed else "RISK_DENY", bot, symbol, side, trade_id, state, item)
    if allowed and str(item.get("mode")).upper() == "VERIFY":
        upsert_shadow_position(item)
    return item


def shadow_positions_payload():
    data = _read_json_file(CENTRAL_SHADOW_POSITIONS_FILE, {})
    return data if isinstance(data, dict) else {}


def upsert_shadow_position(decision_item):
    try:
        if not isinstance(decision_item, dict):
            return None
        if str(decision_item.get("mode") or "").upper() not in {"VERIFY", "READY"}:
            return None
        if not decision_item.get("allowed"):
            return None
        trade_id = decision_item.get("trade_id") or generate_trade_id(decision_item.get("bot"), decision_item.get("symbol"), decision_item.get("side"))
        data = shadow_positions_payload()
        data[trade_id] = {
            "trade_id": trade_id,
            "created_at": decision_item.get("ts") or data_hora_sp_str(),
            "updated_at": data_hora_sp_str(),
            "state": "VERIFY",
            "bot": decision_item.get("bot"),
            "symbol": decision_item.get("symbol"),
            "side": decision_item.get("side"),
            "setup": decision_item.get("setup"),
            "score": decision_item.get("score"),
            "risk_pct": decision_item.get("risk_pct"),
            "notional_usdt": decision_item.get("notional_usdt"),
            "source": "decision_log",
        }
        _write_json_file(CENTRAL_SHADOW_POSITIONS_FILE, data)
        append_timeline_event("SHADOW_POSITION", decision_item.get("bot"), decision_item.get("symbol"), decision_item.get("side"), trade_id, "VERIFY", data[trade_id])
        return data[trade_id]
    except Exception as exc:
        print("ERRO upsert_shadow_position:", exc)
        return None


def decision_log_items(limit=50):
    rows = []

    try:
        rows.extend(_read_jsonl_tail(CENTRAL_DECISION_LOG_FILE, limit=limit))
    except Exception:
        pass

    try:
        import history_manager as super_history_manager
        history_file = getattr(super_history_manager, "DECISION_LOG_FILE", None)
        if history_file:
            rows.extend(_read_jsonl_tail(history_file, limit=limit))
    except Exception:
        pass

    def _epoch(row):
        try:
            return float(row.get("epoch") or 0)
        except Exception:
            return 0

    rows = sorted(rows, key=_epoch)
    return rows[-limit:]


def timeline_items(limit=100):
    return _read_jsonl_tail(CENTRAL_TIMELINE_LOG_FILE, limit=limit)


def clean_decision_trade_id(value):
    if isinstance(value, dict):
        value = (
            value.get("trade_id")
            or value.get("ALLOWED")
            or value.get("DENIED")
            or value.get("id")
            or str(value)
        )

    text = str(value or "")

    if text.startswith("{'ALLOWED':") or text.startswith('{"ALLOWED":'):
        text = text.replace("{'ALLOWED':", "").replace('{"ALLOWED":', "")
    if text.startswith("{'DENIED':") or text.startswith('{"DENIED":'):
        text = text.replace("{'DENIED':", "").replace('{"DENIED":', "")

    text = text.strip().strip("{}").strip("'").strip('"')

    return text


def normalize_decision_log_row(r):
    r = r or {}

    raw = r.get("raw") if isinstance(r.get("raw"), dict) else {}
    execution_decision = (
        r.get("execution_decision")
        or raw.get("execution_decision")
        or raw.get("execution_decision".upper())
        or {}
    )

    if not isinstance(execution_decision, dict):
        execution_decision = {}

    decision = (
        r.get("decision")
        or r.get("result")
        or r.get("risk_decision")
        or execution_decision.get("decision")
        or execution_decision.get("result")
    )

    mode = (
        r.get("mode")
        or r.get("execution_mode")
        or execution_decision.get("mode")
    )

    bot = (
        r.get("bot")
        or execution_decision.get("bot")
        or raw.get("bot")
    )

    symbol = (
        r.get("symbol")
        or execution_decision.get("symbol")
        or raw.get("symbol_clean")
        or raw.get("symbol")
    )

    side = (
        r.get("side")
        or execution_decision.get("side")
        or raw.get("side")
        or raw.get("direction")
    )

    warnings = (
        r.get("warnings")
        or r.get("risk_warnings")
        or execution_decision.get("warnings")
        or []
    )

    reasons = (
        r.get("reasons")
        or execution_decision.get("reasons")
        or []
    )

    bingx_divergence = (
        r.get("bingx_divergence")
        or execution_decision.get("bingx_divergence")
        or {}
    )

    trade_id = (
        r.get("trade_id")
        or execution_decision.get("trade_id")
        or raw.get("trade_id")
        or ""
    )

    def unique_list(values):
        out = []
        for x in values or []:
            if x and x not in out:
                out.append(x)
        return out

    return {
        "ts": r.get("ts") or r.get("created_at") or r.get("datetime"),
        "decision": decision,
        "mode": mode,
        "bot": normalize_registry_bot(bot or "UNKNOWN"),
        "symbol": normalize_registry_symbol(symbol or "UNKNOWN"),
        "side": str(side or "UNKNOWN").upper(),
        "score": r.get("score") or raw.get("score"),
        "risk_pct": r.get("risk_pct") or raw.get("risk_pct"),
        "trade_id": clean_decision_trade_id(trade_id),
        "reasons": unique_list(reasons if isinstance(reasons, list) else [reasons]),
        "warnings": unique_list(warnings if isinstance(warnings, list) else [warnings]),
        "bingx_divergence": bingx_divergence if isinstance(bingx_divergence, dict) else {},
    }    


def build_decision_log_report(arg=None, limit=30):
    token = normalize_symbol_for_risk(arg) if arg else None
    rows = decision_log_items(limit=max(limit, CENTRAL_DECISION_LOG_MAX_READ))
    if token:
        rows = [r for r in rows if normalize_symbol_for_risk(r.get("symbol")) == token or str(r.get("bot") or "").upper() == token or str(r.get("trade_id") or "").upper().startswith(token)]
    rows = rows[-limit:]
    lines = ["🧾 DECISION LOG — CENTRAL QUANT", f"Data/hora: {data_hora_sp_str()}"]
    if token:
        lines.append(f"Filtro: {token}")
    lines += ["", f"Decisões exibidas: {len(rows)}"]
    if not rows:
        lines.append("Nenhuma decisão registrada ainda. O log será preenchido quando Falcon/Predator consultarem /can_open_trade.")
        return "\n".join(lines)
    for raw_row in rows:
        r = normalize_decision_log_row(raw_row)

        reasons = r.get("reasons") or []
        warnings = r.get("warnings") or []

        lines.append(
            f"- {r.get('ts')} | {r.get('decision')} | {r.get('mode')} | "
            f"{r.get('bot')} {r.get('symbol')} {r.get('side')} | "
            f"score={r.get('score')} | risco={r.get('risk_pct')} | id={r.get('trade_id')}"
        )

        if reasons:
            lines.append("  motivos: " + "; ".join(str(x) for x in reasons[:3]))

        if warnings:
            lines.append("  avisos: " + "; ".join(str(x) for x in warnings[:3]))

        divergence = r.get("bingx_divergence") or {}
        if divergence.get("active"):
            only_bingx = divergence.get("only_bingx") or []
            only_central = divergence.get("only_central") or []
            lines.append(
                "  bingx_divergence: "
                f"{divergence.get('status')} | "
                f"policy={divergence.get('policy')} | "
                f"só_bingx={','.join(only_bingx) if only_bingx else '0'} | "
                f"só_central={','.join(only_central) if only_central else '0'}"
            )

    return "\n".join(lines)


def build_timeline_report(arg=None, limit=40):
    token = normalize_symbol_for_risk(arg) if arg else None
    rows = timeline_items(limit=max(limit, CENTRAL_TIMELINE_MAX_READ))
    if token:
        rows = [r for r in rows if normalize_symbol_for_risk(r.get("symbol")) == token or str(r.get("bot") or "").upper() == token or token in str(r.get("trade_id") or "").upper()]
    rows = rows[-limit:]
    lines = ["🧭 TIMELINE — CENTRAL QUANT", f"Data/hora: {data_hora_sp_str()}"]
    if token:
        lines.append(f"Filtro: {token}")
    lines += ["", f"Eventos exibidos: {len(rows)}"]
    if not rows:
        lines.append("Nenhum evento de timeline registrado ainda.")
        return "\n".join(lines)
    for r in rows:
        lines.append(f"- {r.get('ts')} | {r.get('event')} | {r.get('state')} | {r.get('bot')} {r.get('symbol')} {r.get('side')} | id={r.get('trade_id')}")
    return "\n".join(lines)


def build_live_positions_report():
    live_rows = _central_live_positions_payload() if "_central_live_positions_payload" in globals() else []
    shadows = shadow_positions_payload()
    lines = ["📌 LIVE / SHADOW POSITIONS — CENTRAL QUANT", f"Data/hora: {data_hora_sp_str()}", ""]
    lines.append(f"LIVE Central: {len(live_rows)}")
    if live_rows:
        for p in live_rows[:30]:
            lines.append(f"- LIVE {p.get('bot')} {p.get('symbol')} {p.get('side')} | order={p.get('order_id')} | entry={p.get('entry')}")
    else:
        lines.append("- Nenhuma posição LIVE registrada.")
    lines += ["", f"Shadow VERIFY/READY: {len(shadows)}"]
    for _, p in list(shadows.items())[-30:]:
        lines.append(f"- SHADOW {p.get('bot')} {p.get('symbol')} {p.get('side')} | {p.get('state')} | notional={p.get('notional_usdt')} | id={p.get('trade_id')}")
    return "\n".join(lines)


def build_verify_queue_report():
    shadows = shadow_positions_payload()
    rows = [p for p in shadows.values() if str(p.get("state") or "").upper() in {"VERIFY", "READY", "SIGNALLED"}]
    lines = ["🧪 VERIFY QUEUE / SHADOW BOOK", f"Data/hora: {data_hora_sp_str()}", "", f"Itens em VERIFY/READY: {len(rows)}"]
    if not rows:
        lines.append("Fila vazia. Aguardando novos sinais em VERIFY.")
        return "\n".join(lines)
    for p in rows[-30:]:
        lines.append(f"- {p.get('created_at')} | {p.get('bot')} {p.get('symbol')} {p.get('side')} | score={p.get('score')} | notional={p.get('notional_usdt')} | id={p.get('trade_id')}")
    return "\n".join(lines)


def build_execution_stats_report():
    decisions = decision_log_items(limit=1000)
    timelines = timeline_items(limit=1000)
    exec_items, exec_err = _execution_log_items(limit=1000) if "_execution_log_items" in globals() else ([], "execution log indisponível")
    total_decisions = len(decisions)
    allow = sum(1 for d in decisions if d.get("allowed"))
    deny = total_decisions - allow
    verify = sum(1 for d in decisions if str(d.get("mode") or "").upper() == "VERIFY")
    live = sum(1 for d in decisions if str(d.get("mode") or "").upper() == "LIVE")
    sent = sum(1 for e in exec_items or [] if isinstance(e, dict) and e.get("sent"))
    rejected = sum(1 for e in exec_items or [] if isinstance(e, dict) and (e.get("error") or str(e.get("status") or "").upper() in {"DENIED", "REJECTED", "ERROR", "BROKER_EXCEPTION"}))
    by_bot = {}
    for d in decisions:
        bot = str(d.get("bot") or "N/A").upper()
        by_bot.setdefault(bot, {"total": 0, "allow": 0, "deny": 0, "verify": 0, "live": 0})
        by_bot[bot]["total"] += 1
        by_bot[bot]["allow" if d.get("allowed") else "deny"] += 1
        m = str(d.get("mode") or "").upper()
        if m == "VERIFY":
            by_bot[bot]["verify"] += 1
        elif m == "LIVE":
            by_bot[bot]["live"] += 1
    lines = [
        "📊 EXECUTION STATS — CENTRAL QUANT",
        f"Data/hora: {data_hora_sp_str()}",
        "",
        f"Decisões registradas: {total_decisions}",
        f"ALLOW: {allow} | DENY: {deny}",
        f"VERIFY: {verify} | LIVE: {live}",
        f"Eventos de timeline: {len(timelines)}",
        f"Eventos broker: {len(exec_items or [])} | sent={sent} | rejected/error={rejected}",
    ]
    if exec_err:
        lines.append(f"Broker log aviso: {exec_err}")
    lines += ["", "Por robô:"]
    if not by_bot:
        lines.append("- Sem decisões ainda.")
    else:
        for bot, st in sorted(by_bot.items()):
            lines.append(f"- {bot}: total={st['total']} | allow={st['allow']} | deny={st['deny']} | verify={st['verify']} | live={st['live']}")
    return "\n".join(lines)


def build_latency_report():
    exec_items, err = _execution_log_items(limit=500) if "_execution_log_items" in globals() else ([], "execution log indisponível")
    latencies = []
    for e in exec_items or []:
        if not isinstance(e, dict):
            continue
        for k in ("latency_ms", "elapsed_ms", "duration_ms"):
            if e.get(k) is not None:
                val = safe_round(e.get(k), 2, None)
                if val is not None:
                    latencies.append(val)
                break
    lines = ["⏱️ LATÊNCIA DE EXECUÇÃO — CENTRAL QUANT", f"Data/hora: {data_hora_sp_str()}", ""]
    if err:
        lines.append(f"Aviso: {err}")
    if not latencies:
        lines.append("Ainda sem latências registradas no broker. Elas aparecerão após os primeiros VERIFY/LIVE com medição no broker.py.")
        return "\n".join(lines)
    avg = sum(latencies) / len(latencies)
    lines += [
        f"Amostra: {len(latencies)}",
        f"Média: {round(avg, 2)} ms",
        f"Mínima: {round(min(latencies), 2)} ms",
        f"Máxima: {round(max(latencies), 2)} ms",
    ]
    return "\n".join(lines)


def build_broker_health_report():
    ready = bingx_ready_payload() if "bingx_ready_payload" in globals() else {"ok": False, "status": "NO_READY_FN"}
    broker_status = broker_status_payload() if "broker_status_payload" in globals() else {}
    exec_items, err = _execution_log_items(limit=20) if "_execution_log_items" in globals() else ([], "execution log indisponível")
    lines = [
        "🏦 BROKER HEALTH — CENTRAL QUANT",
        f"Data/hora: {data_hora_sp_str()}",
        "",
        f"Broker carregado: {broker_status.get('broker_loaded')}",
        f"Import error: {broker_status.get('broker_import_error')}",
        f"READY: {ready.get('ok')} | {ready.get('status')}",
    ]
    if ready.get("error"):
        lines.append(f"Erro: {ready.get('error')}")
    bal = ready.get("balance") or {}
    if bal:
        lines.append(f"Saldo USDT total/free/used: {bal.get('total_usdt')} / {bal.get('free_usdt')} / {bal.get('used_usdt')}")
    lines += ["", f"Últimos eventos broker lidos: {len(exec_items or [])}"]
    if err:
        lines.append(f"Aviso log: {err}")
    return "\n".join(lines)


def build_consistency_report():
    decisions = decision_log_items(limit=1000)
    timelines = timeline_items(limit=1000)
    shadows = shadow_positions_payload()
    live_rows = _central_live_positions_payload() if "_central_live_positions_payload" in globals() else []
    broker_positions, pos_err = _broker_open_positions() if "_broker_open_positions" in globals() else ([], "broker positions indisponível")
    issues = []
    trade_ids = [str(d.get("trade_id")) for d in decisions if d.get("trade_id")]
    dupes = sorted({x for x in trade_ids if trade_ids.count(x) > 1})
    if dupes:
        issues.append(f"Trade IDs duplicados no decision log: {len(dupes)}")
    if pos_err:
        issues.append(f"Erro ao ler posições BingX: {pos_err}")
    broker_keys = {(p.get("symbol"), str(p.get("side") or "").upper()) for p in broker_positions}
    live_keys = {(p.get("symbol"), str(p.get("side") or "").upper()) for p in live_rows}
    only_broker = broker_keys - live_keys
    only_live = live_keys - broker_keys
    if only_broker:
        issues.append(f"Posições só na BingX: {len(only_broker)}")
    if only_live:
        issues.append(f"Posições LIVE só na Central: {len(only_live)}")
    denied_shadows = [p for p in shadows.values() if str(p.get("state") or "").upper() == "DENIED"]
    if denied_shadows:
        issues.append(f"Shadow positions em estado DENIED: {len(denied_shadows)}")
    lines = [
        "🧩 CONSISTÊNCIA — CENTRAL QUANT",
        f"Data/hora: {data_hora_sp_str()}",
        "",
        f"Decision logs: {len(decisions)}",
        f"Timeline events: {len(timelines)}",
        f"Shadow positions: {len(shadows)}",
        f"LIVE Central: {len(live_rows)} | BingX: {len(broker_positions)}",
        "",
        "Resultado:",
    ]
    if not issues:
        lines.append("✅ Nenhuma inconsistência relevante encontrada.")
    else:
        lines += [f"⚠️ {x}" for x in issues]
    return "\n".join(lines)


def build_trade_registry_status_line():
    try:
        autosync_trade_registry(reason="status")

        registry = central_trade_registry_snapshot(include_trades=False)
        autosync = TRADE_REGISTRY_AUTOSYNC_STATUS or {}

        return (
            f"Trade Registry: "
            f"{registry.get('open_count')} abertas | "
            f"ok={registry.get('ok')} | "
            f"autosync={autosync.get('last_ok')} | "
            f"último={autosync.get('last_run')}"
        )
    except Exception as exc:
        return f"Trade Registry: erro ao gerar status ({exc})"

        
def build_bingx_divergence_status_line():
    try:
        txt = build_sync_report()

        if "Só na BingX: 0" in txt and "Só na Central: 0" in txt:
            return "Central x BingX: OK | sem divergência LIVE"

        only_bingx = None
        only_central = None

        for line in txt.splitlines():
            if line.startswith("Só na BingX:"):
                only_bingx = line.replace("Só na BingX:", "").strip()
            elif line.startswith("Só na Central:"):
                only_central = line.replace("Só na Central:", "").strip()

        return (
            f"Central x BingX: ALERTA | "
            f"só BingX={only_bingx or 'N/A'} | "
            f"só Central={only_central or 'N/A'}"
        )

    except Exception as exc:
        return f"Central x BingX: erro ao verificar divergência ({exc})"


def bingx_divergence_payload():
    try:
        txt = build_sync_report()

        only_bingx = []
        only_central = []

        current_section = None

        for line in txt.splitlines():
            clean = line.strip()

            if clean.startswith("⚠️ Só na BingX"):
                current_section = "only_bingx"
                continue

            if clean.startswith("⚠️ Só na Central"):
                current_section = "only_central"
                continue

            if clean.startswith("- "):
                item = clean.replace("- ", "", 1).strip()

                if current_section == "only_bingx":
                    only_bingx.append(item)
                elif current_section == "only_central":
                    only_central.append(item)

        return {
            "ok": len(only_bingx) == 0 and len(only_central) == 0,
            "status": "OK" if len(only_bingx) == 0 and len(only_central) == 0 else "ALERTA",
            "only_bingx_count": len(only_bingx),
            "only_central_count": len(only_central),
            "only_bingx": only_bingx,
            "only_central": only_central,
            "text": txt,
        }

    except Exception as exc:
        return {
            "ok": False,
            "status": "ERRO",
            "error": str(exc),
        }


def bingx_divergence_warning_payload():
    payload = bingx_divergence_payload()

    return {
        "active": not bool(payload.get("ok")),
        "status": payload.get("status"),
        "only_bingx_count": payload.get("only_bingx_count", 0),
        "only_central_count": payload.get("only_central_count", 0),
        "only_bingx": payload.get("only_bingx", []),
        "only_central": payload.get("only_central", []),
        "policy": "LEVEL_2_WARNING_ONLY",
        "message": "Divergência Central x BingX detectada. Operação permitida, mas requer atenção operacional.",
    }


def build_status_report():
    score_payload = central_health_score_payload() if "central_health_score_payload" in globals() else {"score": None, "status": "N/A"}
    ready = bingx_ready_payload() if "bingx_ready_payload" in globals() else {"ok": None, "status": "N/A"}
    sync_txt = build_sync_report() if "build_sync_report" in globals() else "Sync indisponível"
    mem = memory_snapshot("status_memory", store=True)
    lines = [
        "✅ STATUS CENTRAL QUANT",
        f"Data/hora: {data_hora_sp_str()}",
        "",
        f"Health Score: {score_payload.get('score')}/100 — {score_payload.get('status')}",
        f"Watchdog: {CENTRAL_HEALTH.get('watchdog_status')}",
        f"Execução: {'ATIVA' if ENABLE_REAL_TRADING else 'BLOQUEADA'} | Modo {EXECUTION_MODE}",
        f"BingX: {ready.get('ok')} | {ready.get('status')}",
        build_trade_registry_status_line(),
        build_bingx_divergence_status_line(),
        f"Memória: {mem.get('rss_mb')} MB ({mem.get('usage_pct')}%)",
        "",
        _short(sync_txt, 900),
    ]
    return "\n".join(lines)

# ==========================================================
# EXECUTION / DECISIONAL RISK MANAGER
# ==========================================================

def normalize_symbol_for_risk(symbol):
    s = str(symbol or "").upper().strip()
    s = s.replace("/USDT:USDT", "USDT").replace("/USDT", "USDT").replace(":USDT", "")
    return s


def broker_status_payload():
    """Status seguro do broker. Nunca expõe API key/secret."""
    payload = {
        "execution_mode": EXECUTION_MODE,
        "enable_real_trading": ENABLE_REAL_TRADING,
        "allowed_bots": sorted(list(REAL_TRADING_ALLOWED_BOTS)),
        "allowed_symbols": sorted(list(REAL_TRADING_ALLOWED_SYMBOLS)),
        "max_risk_pct": REAL_TRADING_MAX_RISK_PCT,
        "default_margin_usdt": DEFAULT_REAL_MARGIN_USDT,
        "default_leverage": DEFAULT_REAL_LEVERAGE,
        "max_margin_usdt": REAL_TRADING_MAX_MARGIN_USDT,
        "max_notional_usdt": REAL_TRADING_MAX_NOTIONAL_USDT,
        "bot_execution_configs": all_real_execution_configs(),
        "broker_import_error": BROKER_IMPORT_ERROR,
        "broker_loaded": central_broker is not None,
    }
    if central_broker is not None:
        try:
            payload["broker"] = central_broker.status_payload(check_ready=False)
        except Exception as exc:
            payload["broker"] = {"ok": False, "error": str(exc)}
    return payload


def bingx_ready_payload():
    if central_broker is None:
        return {"ok": False, "status": "BROKER_IMPORT_ERROR", "error": BROKER_IMPORT_ERROR}
    try:
        return central_broker.ready_check()
    except Exception as exc:
        return {"ok": False, "status": "READY_ERROR", "error": str(exc)}



def _risk_memory_block_payload():
    """
    Snapshot de memória para o Risk Manager.
    Se a memória estiver alta, tenta GC/malloc_trim antes de decidir.
    """
    try:
        snap = memory_snapshot("risk_memory_before", store=True)
        usage = snap.get("usage_pct")
        if usage is not None and float(usage) >= GLOBAL_RISK_MEMORY_BLOCK_PCT:
            _before, after = force_gc_if_needed("risk_memory_block_check", force=True)
            snap = after or snap
            usage = snap.get("usage_pct")
        return {
            "rss_mb": snap.get("rss_mb"),
            "usage_pct": usage,
            "limit_mb": snap.get("limit_mb"),
            "threshold_pct": GLOBAL_RISK_MEMORY_BLOCK_PCT,
            "blocked": bool(usage is not None and float(usage) >= GLOBAL_RISK_MEMORY_BLOCK_PCT),
        }
    except Exception as exc:
        return {
            "rss_mb": None,
            "usage_pct": None,
            "limit_mb": MEMORY_LIMIT_MB,
            "threshold_pct": GLOBAL_RISK_MEMORY_BLOCK_PCT,
            "blocked": False,
            "error": str(exc),
        }


def _risk_is_reduce_only(payload):
    payload = payload or {}
    value = payload.get("reduce_only")
    if value is None:
        value = payload.get("reduceOnly")
    if value is None:
        value = payload.get("close_only")
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "sim", "on"}





def _ensure_executive_policy_manager_synced_for_risk(force=False):
    """
    Garante que o Executive Policy Manager tenha políticas ativas antes do
    /can_open_trade avaliar uma entrada.

    Por que existe:
    - em deploy/restart, o arquivo data/executive_policy.json pode iniciar vazio;
    - o /can_open_trade não pode depender do CEO rodar /executivedecision antes;
    - a fonte de verdade continua sendo:
      Executive Decision Engine -> Executive Policy Manager -> Risk Manager.
    """
    result = {
        "ok": False,
        "attempted": False,
        "reason": None,
        "before_active_policy_count": None,
        "after_active_policy_count": None,
        "active_codes": [],
        "ingested": 0,
    }

    try:
        if not EXECUTIVE_POLICY_MANAGER_LOADED or executive_policy_manager is None:
            result["reason"] = f"Executive Policy Manager não carregado: {EXECUTIVE_POLICY_MANAGER_ERROR}"
            return result

        before = executive_policy_manager.build_policy_health()
        before_count = int(before.get("active_policy_count") or 0)
        result["before_active_policy_count"] = before_count

        if before_count > 0 and not force:
            result["ok"] = True
            result["reason"] = "policies_already_active"
            result["after_active_policy_count"] = before_count
            result["active_codes"] = before.get("active_codes") or []
            return result

        if "_executive_decision_snapshot_for_reports" not in globals():
            result["reason"] = "executive_decision_snapshot_unavailable"
            return result

        result["attempted"] = True
        decision_payload = _executive_decision_snapshot_for_reports(compact_source=True)

        # _executive_decision_snapshot_for_reports já chama _sync_executive_policy_manager_from_decision.
        sync_payload = decision_payload.get("executive_policy_manager") if isinstance(decision_payload, dict) else {}
        if isinstance(sync_payload, dict):
            result["ingested"] = int(sync_payload.get("ingested", 0) or 0)

        after = executive_policy_manager.build_policy_health()
        after_count = int(after.get("active_policy_count") or 0)
        result["after_active_policy_count"] = after_count
        result["active_codes"] = after.get("active_codes") or []
        result["ok"] = after_count > 0
        result["reason"] = "synced_from_executive_decision" if result["ok"] else "sync_finished_but_no_active_policies"
        return result

    except Exception as exc:
        result["reason"] = str(exc)
        return result



def _executive_policy_for_can_open_trade():
    """
    Consulta o Executive Policy Manager persistente para o Risk Manager.

    Esta é a fonte correta depois da integração V1:
    Executive Decision Engine -> Executive Policy Manager -> Risk Manager/can_open_trade.

    Se o Policy Manager não estiver disponível, faz fallback seguro para o
    Executive Decision Engine, sem derrubar /can_open_trade.
    """
    try:
        if EXECUTIVE_POLICY_MANAGER_LOADED and executive_policy_manager is not None:
            health = executive_policy_manager.build_policy_health()
            return {
                "ok": bool(health.get("ok", True)),
                "available": True,
                "source": "executive_policy_manager",
                "version": health.get("version"),
                "active_policy_count": health.get("active_policy_count"),
                "active_codes": health.get("active_codes") or [],
                "updated_at": health.get("updated_at"),
                "generated_at": health.get("generated_at"),
            }
    except Exception as exc:
        return {
            "ok": False,
            "available": False,
            "source": "executive_policy_manager",
            "error": str(exc),
        }

    # Fallback legado: Executive Decision Engine direto.
    try:
        if "_executive_decision_snapshot_for_reports" not in globals():
            return {"ok": False, "available": False, "source": "fallback", "error": "executive policy manager unavailable"}

        payload = _executive_decision_snapshot_for_reports(compact_source=True)
        if not isinstance(payload, dict):
            return {"ok": False, "available": False, "source": "fallback", "error": "executive decision payload invalid"}

        policy = payload.get("policy") or {}
        if not isinstance(policy, dict):
            policy = {}

        primary = payload.get("primary_decision") or payload.get("primary_directive", {}).get("code")
        return {
            "ok": bool(payload.get("ok", True)),
            "available": True,
            "source": "executive_decision_engine_fallback",
            "primary_decision": primary,
            "primary_directive": payload.get("primary_directive") or {},
            "policy": policy,
            "assistant_action": payload.get("assistant_action"),
            "generated_at": payload.get("generated_at"),
            "version": payload.get("version"),
            "risk": payload.get("risk") or {},
            "ceo_confidence": payload.get("ceo_confidence") or {},
        }
    except Exception as exc:
        return {"ok": False, "available": False, "source": "fallback", "error": str(exc)}


def _apply_executive_policy_to_risk_reasons(trade_payload, reasons, warnings):
    """
    Aplica políticas executivas persistentes dentro do /can_open_trade.

    Fonte principal:
    - executive_policy_manager.evaluate_trade_against_policies(trade_payload)

    Bloqueios efetivos atuais:
    - NO_NEW_LONG
    - NO_NEW_SHORT
    - ALLOW_ONLY_LONG / ALLOW_ONLY_SHORT
    - BLOCK_BOT / BLOCK_SETUP / BLOCK_SYMBOL
    - ONLY_CORE_BOTS

    Ajustes consultivos:
    - FORCE_HALF_SIZE / REDUCE_SIZE
    - MAX_RISK / CAP_RISK
    - CAPITAL_PRESERVATION
    """
    trade_payload = trade_payload or {}

    try:
        if EXECUTIVE_POLICY_MANAGER_LOADED and executive_policy_manager is not None:
            sync_result = _ensure_executive_policy_manager_synced_for_risk(force=False)
            evaluation = executive_policy_manager.evaluate_trade_against_policies(trade_payload)
            if not isinstance(evaluation, dict):
                evaluation = {"ok": False, "allowed": True, "warnings": ["Policy Manager retornou payload inválido."]}

            if not evaluation.get("allowed", True):
                for reason in evaluation.get("reasons") or []:
                    reasons.append(str(reason))

            for warning in evaluation.get("warnings") or []:
                warnings.append(str(warning))

            if evaluation.get("size_multiplier", 1.0) not in (None, 1, 1.0):
                warnings.append(f"Policy Manager sugere size_multiplier={evaluation.get('size_multiplier')}.")

            if evaluation.get("max_risk_pct") is not None:
                warnings.append(f"Policy Manager limita max_risk_pct={evaluation.get('max_risk_pct')}%.")

            # Executive Policy Priority V1 — resolve conflito entre policies ativas
            # e anexa a policy dominante ao payload usado pelo Risk Manager.
            try:
                priority_eval = resolve_executive_policy_priority(trade_payload=trade_payload, commit=True)
                evaluation["priority"] = priority_eval
                evaluation["dominant_policy"] = priority_eval.get("dominant_policy")
                evaluation["dominant_policy_code"] = priority_eval.get("dominant_code")

                if priority_eval.get("allowed") is False:
                    evaluation["allowed"] = False
                    evaluation.setdefault("reasons", [])
                    for reason in priority_eval.get("reasons") or []:
                        if reason not in evaluation["reasons"]:
                            evaluation["reasons"].append(str(reason))
                        if reason not in reasons:
                            reasons.append(str(reason))

                if priority_eval.get("size_multiplier") not in (None, 1, 1.0):
                    current_multiplier = evaluation.get("size_multiplier", 1.0)
                    try:
                        evaluation["size_multiplier"] = min(float(current_multiplier or 1.0), float(priority_eval.get("size_multiplier")))
                    except Exception:
                        evaluation["size_multiplier"] = priority_eval.get("size_multiplier")
                    warnings.append(f"Policy Priority sugere size_multiplier={evaluation.get('size_multiplier')}.")

                if priority_eval.get("max_risk_pct") is not None and evaluation.get("max_risk_pct") is None:
                    evaluation["max_risk_pct"] = priority_eval.get("max_risk_pct")
                    warnings.append(f"Policy Priority limita max_risk_pct={evaluation.get('max_risk_pct')}%.")

                for warning in priority_eval.get("warnings") or []:
                    warnings.append(str(warning))
            except Exception as priority_exc:
                warnings.append(f"Erro ao aplicar Executive Policy Priority: {priority_exc}")

            evaluation["source"] = "executive_policy_manager+priority"
            evaluation["available"] = True
            evaluation["sync"] = sync_result
            try:
                policy_link = extract_policy_decision_link({"executive_policy": evaluation}, trade_payload)
                evaluation["policy_codes"] = policy_link.get("policy_codes") or []
                evaluation["active_policy_codes"] = policy_link.get("active_policy_codes") or []
                evaluation["policy_linker"] = policy_link
            except Exception as linker_exc:
                evaluation["policy_linker_error"] = str(linker_exc)
            return evaluation

        warnings.append(f"Executive Policy Manager não carregado: {EXECUTIVE_POLICY_MANAGER_ERROR}")

    except Exception as exc:
        warnings.append(f"Erro ao aplicar Executive Policy Manager: {exc}")

    # Fallback legado: lê policy atual do Executive Decision Engine.
    policy_payload = _executive_policy_for_can_open_trade()
    policy = policy_payload.get("policy") or {}
    primary = policy_payload.get("primary_decision") or "UNKNOWN"
    normalized_side = str(trade_payload.get("side") or trade_payload.get("direction") or "").upper().strip()
    if normalized_side == "BUY":
        normalized_side = "LONG"
    elif normalized_side == "SELL":
        normalized_side = "SHORT"

    if not policy_payload.get("available"):
        warnings.append(f"Executive Decision Engine indisponível para política: {policy_payload.get('error')}")
        return policy_payload

    if policy.get("allow_new_entries") is False:
        reasons.append(f"Executive Decision Engine {primary}: novas entradas bloqueadas")

    if normalized_side == "LONG" and policy.get("allow_new_long") is False:
        release = policy.get("release_condition") or "condição de liberação não informada"
        reasons.append(f"Executive Decision Engine {primary}: novas entradas LONG bloqueadas ({release})")

    if normalized_side == "SHORT" and policy.get("allow_new_short") is False:
        release = policy.get("release_condition") or "condição de liberação não informada"
        reasons.append(f"Executive Decision Engine {primary}: novas entradas SHORT bloqueadas ({release})")

    if policy.get("allow_expansion") is False:
        warnings.append(f"Executive Decision Engine {primary}: expansão estrutural bloqueada")

    if policy.get("allow_risk_increase") is False:
        warnings.append(f"Executive Decision Engine {primary}: aumento de risco estrutural bloqueado")

    policy_payload["source"] = policy_payload.get("source") or "executive_decision_engine_fallback"
    return policy_payload

def can_open_trade_decision(payload: dict):
    """
    Risk Manager decisório da Central.
    Retorna ALLOW/DENY para qualquer robô antes de abrir posição.

    V3.1 hard blocks:
    - Memória >= GLOBAL_RISK_MEMORY_BLOCK_PCT: DENY novas entradas.
    - Posições Central/PAPER >= GLOBAL_RISK_MAX_POSITIONS: DENY novas entradas.
    - Posições LIVE >= GLOBAL_RISK_MAX_POSITIONS: DENY novas entradas.
    - Concentração direcional >= GLOBAL_RISK_MAX_SIDE_CONCENTRATION_PCT:
      DENY novas entradas no lado dominante.
    - Ativo com GLOBAL_RISK_MAX_SYMBOL_EXPOSURE ou mais exposições: DENY.
    - reduceOnly/fechamento continua permitido quando GLOBAL_RISK_ALLOW_REDUCE_ONLY=true.
    """
    payload = payload or {}

    # Mantém o Trade Registry sincronizado antes da decisão de risco
    try:
        autosync_trade_registry(reason="can_open_trade")
    except Exception as exc:
        print("AVISO SYNC REGISTRY ANTES DO CAN_OPEN_TRADE:", exc)

    bot = normalize_registry_bot(
        payload.get("bot")
        or payload.get("robot")
        or payload.get("strategy")
        or ""
    )

    symbol = normalize_registry_symbol(
        payload.get("symbol")
        or payload.get("symbol_clean")
        or payload.get("pair")
        or payload.get("ativo")
        or ""
    )

    side = str(
        payload.get("side")
        or payload.get("direction")
        or payload.get("signal")
        or ""
    ).upper().strip()

    if side == "BUY":
        side = "LONG"
    elif side == "SELL":
        side = "SHORT"
    mode = str(payload.get("mode") or payload.get("execution_mode") or EXECUTION_MODE).upper().strip()
    intended_live = bool(payload.get("intended_live", mode == "LIVE"))
    reduce_only = _risk_is_reduce_only(payload)

    risk_pct = safe_round(payload.get("risk_pct"), 4, 0) or 0
    bot_cfg = real_execution_config_for_bot(bot)
    margin = safe_round(payload.get("margin_usdt"), 4, None)
    leverage = safe_round(payload.get("leverage"), 0, None)
    if margin is None:
        margin = bot_cfg.get("margin_usdt", DEFAULT_REAL_MARGIN_USDT)
    if leverage is None:
        leverage = bot_cfg.get("leverage", DEFAULT_REAL_LEVERAGE)
    try:
        leverage = int(leverage)
    except Exception:
        leverage = DEFAULT_REAL_LEVERAGE
    notional = safe_round(payload.get("notional_usdt"), 4, None)
    if notional is None or notional == 0:
        notional = float(margin) * int(leverage)

    exposure_snapshot = central_exposure_snapshot()
    rows = _all_open_positions_payload()
    total_pos = int(exposure_snapshot.get("total_positions_open") or 0)
    long_pos = int(exposure_snapshot.get("long_positions_open") or 0)
    short_pos = int(exposure_snapshot.get("short_positions_open") or 0)

    live_rows = _central_live_positions_payload() if "_central_live_positions_payload" in globals() else []
    live_total_pos = len(live_rows)
    live_long_pos = sum(1 for r in live_rows if str(r.get("side") or "").upper() in {"LONG", "BUY"})
    live_short_pos = sum(1 for r in live_rows if str(r.get("side") or "").upper() in {"SHORT", "SELL"})

    # A Central/PAPER representa a verdade estatística e de exposição agregada.
    # Em VERIFY/LIVE, ela também deve bloquear novas entradas quando a carteira
    # paper/central já estiver saturada.
    if intended_live or mode in {"LIVE", "VERIFY"}:
        risk_rows = live_rows
        risk_total_pos = live_total_pos
        risk_long_pos = live_long_pos
        risk_short_pos = live_short_pos
    else:
        risk_rows = rows
        risk_total_pos = total_pos
        risk_long_pos = long_pos
        risk_short_pos = short_pos

    memory_risk = _risk_memory_block_payload()

    reasons = []
    warnings = []
    executive_policy_payload = None

    if reduce_only and GLOBAL_RISK_ALLOW_REDUCE_ONLY:
        decision_result = {
            "allowed": True,
            "decision": "ALLOW",
            "bot": bot,
            "symbol": symbol,
            "side": side,
            "mode": mode,
            "intended_live": intended_live,
            "reduce_only": True,
            "reasons": [],
            "warnings": ["reduceOnly/fechamento permitido mesmo com travas de risco"],
            "executive_policy": _executive_policy_for_can_open_trade(),
            "memory": memory_risk,
            "exposure": {
                "total": risk_total_pos,
                "long": risk_long_pos,
                "short": risk_short_pos,
                "paper_total": total_pos,
                "paper_long": long_pos,
                "paper_short": short_pos,
                "live_total": live_total_pos,
                "live_long": live_long_pos,
                "live_short": live_short_pos,
                "max_positions": GLOBAL_RISK_MAX_POSITIONS,
                "max_paper_positions": GLOBAL_RISK_MAX_PAPER_POSITIONS,
                "block_on_paper_limit": GLOBAL_RISK_BLOCK_ON_PAPER_LIMIT,
                "max_paper_positions": GLOBAL_RISK_MAX_PAPER_POSITIONS,
                "block_on_paper_limit": GLOBAL_RISK_BLOCK_ON_PAPER_LIMIT,
                "max_symbol_exposure": GLOBAL_RISK_MAX_SYMBOL_EXPOSURE,
                "max_side_concentration_pct": GLOBAL_RISK_MAX_SIDE_CONCENTRATION_PCT,
            },
            "requested_margin_usdt": margin,
            "requested_leverage": leverage,
            "requested_effective_notional_usdt": notional,
            "execution": broker_status_payload(),
        }
        try:
            enrich_decision_result_with_policy_links(decision_result, payload)
            append_decision_log(payload, decision_result)
            enrich_decision_result_with_policy_links(decision_result, payload)
        except Exception as exc:
            print("ERRO decision log:", exc)
        return decision_result

    if not bot:
        reasons.append("bot ausente")
    if bot and bot not in BOT_CONFIGS:
        reasons.append(f"bot inválido: {bot}")
    if symbol and REAL_TRADING_ALLOWED_SYMBOLS and symbol not in REAL_TRADING_ALLOWED_SYMBOLS:
        reasons.append(f"símbolo não liberado para real: {symbol}")

    # Política executiva decidida pela camada superior da Central.
    # Exemplo atual esperado: NO_NEW_LONG enquanto concentração LONG >= 85%.
    executive_policy_payload = _apply_executive_policy_to_risk_reasons({
        "bot": bot,
        "symbol": symbol,
        "side": side,
        "mode": mode,
        "intended_live": intended_live,
        "reduce_only": reduce_only,
        "risk_pct": risk_pct,
        "margin_usdt": margin,
        "leverage": leverage,
        "notional_usdt": notional,
        "setup": payload.get("setup") or payload.get("signal_type") or payload.get("strategy"),
        "category": payload.get("category") or payload.get("bot_category"),
    }, reasons, warnings)

    # Hard blocks globais da Central, valem para PAPER/VERIFY/LIVE.
    if memory_risk.get("blocked"):
        reasons.append(
            f"memória acima do limite operacional: {memory_risk.get('usage_pct')}% >= {GLOBAL_RISK_MEMORY_BLOCK_PCT}%"
        )

    if intended_live or mode in {"LIVE", "VERIFY"}:
        paper_limit = GLOBAL_RISK_MAX_PAPER_POSITIONS
        paper_limit_enabled = False
    else:
        paper_limit = GLOBAL_RISK_MAX_PAPER_POSITIONS
        paper_limit_enabled = GLOBAL_RISK_BLOCK_ON_PAPER_LIMIT

    if paper_limit_enabled and total_pos >= paper_limit:
        reasons.append(f"bloqueio PAPER ativo: {total_pos}/{paper_limit}")
    elif total_pos >= max(1, int(paper_limit * 0.9)):
        warnings.append(f"exposição PAPER alta: {total_pos}/{paper_limit}")

    if live_total_pos >= GLOBAL_RISK_MAX_POSITIONS:
        reasons.append(f"limite LIVE atingido: {live_total_pos}/{GLOBAL_RISK_MAX_POSITIONS}")

    if intended_live:
        if not ENABLE_REAL_TRADING:
            reasons.append("ENABLE_REAL_TRADING=false")
        if bot and bot not in REAL_TRADING_ALLOWED_BOTS:
            reasons.append(f"bot não liberado para real: {bot}")
        if REAL_TRADING_REQUIRE_READY:
            ready = bingx_ready_payload()
            if not ready.get("ok"):
                reasons.append(f"BingX não está READY: {ready.get('status') or ready.get('error')}")

    # Exposição por ativo: usa a Central/PAPER como verdade estatística,
    # e também confere LIVE quando houver posição real.
    if symbol:
        same_symbol_paper = [r for r in rows if normalize_symbol_for_risk(r.get("symbol")) == symbol]
        same_symbol_live = [r for r in live_rows if normalize_symbol_for_risk(r.get("symbol")) == symbol]

        if len(same_symbol_paper) >= GLOBAL_RISK_MAX_SYMBOL_EXPOSURE:
            reasons.append(f"limite por ativo Central/PAPER atingido em {symbol}: {len(same_symbol_paper)}/{GLOBAL_RISK_MAX_SYMBOL_EXPOSURE}")
        if len(same_symbol_live) >= GLOBAL_RISK_MAX_SYMBOL_EXPOSURE:
            reasons.append(f"limite por ativo LIVE atingido em {symbol}: {len(same_symbol_live)}/{GLOBAL_RISK_MAX_SYMBOL_EXPOSURE}")

        same_bot_symbol = [r for r in same_symbol_paper if str(r.get("bot") or "").upper() == bot]
        if same_bot_symbol:
            reasons.append(f"{bot} já possui exposição em {symbol}")

    # Concentração direcional: bloqueia apenas novas entradas no lado dominante.
    paper_total_after = total_pos + 1
    live_total_after = live_total_pos + 1

    if side in {"LONG", "BUY"}:
        paper_side_conc = (long_pos + 1) / max(paper_total_after, 1) * 100
        live_side_conc = (live_long_pos + 1) / max(live_total_after, 1) * 100 if live_total_pos else 0
        if paper_side_conc >= GLOBAL_RISK_MAX_SIDE_CONCENTRATION_PCT:
            reasons.append(f"concentração LONG Central/PAPER ficaria {paper_side_conc:.1f}%")
        if live_total_pos and live_side_conc >= GLOBAL_RISK_MAX_SIDE_CONCENTRATION_PCT:
            reasons.append(f"concentração LONG LIVE ficaria {live_side_conc:.1f}%")

    if side in {"SHORT", "SELL"}:
        paper_side_conc = (short_pos + 1) / max(paper_total_after, 1) * 100
        live_side_conc = (live_short_pos + 1) / max(live_total_after, 1) * 100 if live_total_pos else 0
        if paper_side_conc >= GLOBAL_RISK_MAX_SIDE_CONCENTRATION_PCT:
            reasons.append(f"concentração SHORT Central/PAPER ficaria {paper_side_conc:.1f}%")
        if live_total_pos and live_side_conc >= GLOBAL_RISK_MAX_SIDE_CONCENTRATION_PCT:
            reasons.append(f"concentração SHORT LIVE ficaria {live_side_conc:.1f}%")

    if risk_pct and risk_pct > REAL_TRADING_MAX_RISK_PCT:
        reasons.append(f"risco acima do máximo real: {risk_pct}% > {REAL_TRADING_MAX_RISK_PCT}%")
    if intended_live and margin and margin > REAL_TRADING_MAX_MARGIN_USDT:
        reasons.append(f"margem acima do máximo real: {margin} > {REAL_TRADING_MAX_MARGIN_USDT} USDT")
    if intended_live and notional and notional > REAL_TRADING_MAX_NOTIONAL_USDT:
        reasons.append(f"exposição efetiva acima do máximo real: {notional} > {REAL_TRADING_MAX_NOTIONAL_USDT} USDT")

    # Avisos não bloqueantes.
    if total_pos >= max(1, int(GLOBAL_RISK_MAX_POSITIONS * 0.9)) and not any("exposição PAPER alta" in w for w in warnings):
        warnings.append(f"exposição PAPER alta: {total_pos}/{GLOBAL_RISK_MAX_POSITIONS}")
    if live_total_pos >= max(1, int(GLOBAL_RISK_MAX_POSITIONS * 0.9)):
        warnings.append(f"exposição LIVE alta: {live_total_pos}/{GLOBAL_RISK_MAX_POSITIONS}")
    if memory_risk.get("usage_pct") is not None and float(memory_risk.get("usage_pct")) >= MEMORY_ALERT_THRESHOLD_PCT:
        warnings.append(f"memória elevada: {memory_risk.get('usage_pct')}%")

    divergence_warning = bingx_divergence_warning_payload()
    if divergence_warning.get("active"):
        warnings.append(divergence_warning.get("message"))

    allowed = len(reasons) == 0
    decision_result = {
        "allowed": allowed,
        "decision": "ALLOW" if allowed else "DENY",
        "bot": bot,
        "symbol": symbol,
        "side": side,
        "mode": mode,
        "intended_live": intended_live,
        "reduce_only": reduce_only,
        "reasons": reasons,
        "warnings": warnings,
        "executive_policy": executive_policy_payload,
        "bingx_divergence": divergence_warning,
        "memory": memory_risk,
        "exposure": {
            "total": risk_total_pos,
            "long": risk_long_pos,
            "short": risk_short_pos,
            "paper_total": total_pos,
            "paper_long": long_pos,
            "paper_short": short_pos,
            "live_total": live_total_pos,
            "live_long": live_long_pos,
            "live_short": live_short_pos,
            "max_positions": GLOBAL_RISK_MAX_POSITIONS,
            "max_symbol_exposure": GLOBAL_RISK_MAX_SYMBOL_EXPOSURE,
            "max_side_concentration_pct": GLOBAL_RISK_MAX_SIDE_CONCENTRATION_PCT,
        },
        "requested_margin_usdt": margin,
        "requested_leverage": leverage,
        "requested_effective_notional_usdt": notional,
        "execution": broker_status_payload(),
    }
    try:
        enrich_decision_result_with_policy_links(decision_result, payload)
        append_decision_log(payload, decision_result)
        enrich_decision_result_with_policy_links(decision_result, payload)
        decision_result["decision_log_saved"] = True
    except Exception as exc:
        print("ERRO decision log:", repr(exc))
        decision_result["decision_log_saved"] = False
        decision_result["decision_log_error"] = str(exc)
    return decision_result


def build_execution_report():
    status = broker_status_payload()
    ready = bingx_ready_payload() if BINGX_READY_CHECK_ENABLED else {"ok": None, "status": "READY_CHECK_DISABLED"}
    lines = [
        "⚙️ EXECUÇÃO / BINGX — CENTRAL QUANT",
        f"Data/hora: {data_hora_sp_str()}",
        "",
        f"Execution mode Central: {EXECUTION_MODE}",
        f"ENABLE_REAL_TRADING: {ENABLE_REAL_TRADING}",
        f"Validação final: automática pelo robô + Risk Manager da Central",
        f"Bots liberados para real: {', '.join(status.get('allowed_bots') or [])}",
        f"Símbolos liberados: {', '.join(status.get('allowed_symbols') or []) if status.get('allowed_symbols') else 'TODOS (respeitando risco)'}",
        f"Margem padrão: {DEFAULT_REAL_MARGIN_USDT} USDT",
        f"Alavancagem padrão: {DEFAULT_REAL_LEVERAGE}x",
        f"Exposição padrão: {DEFAULT_REAL_EFFECTIVE_NOTIONAL_USDT} USDT",
        f"Margem máxima real: {REAL_TRADING_MAX_MARGIN_USDT} USDT",
        f"Exposição máxima real: {REAL_TRADING_MAX_NOTIONAL_USDT} USDT",
        f"Max risco real: {REAL_TRADING_MAX_RISK_PCT}%",
        "",
        "Configuração por robô:",
        *[f"- {k}: margem={v.get('margin_usdt')} USDT | lev={v.get('leverage')}x | exposição={v.get('effective_notional_usdt')} USDT" for k, v in (status.get('bot_execution_configs') or {}).items() if k in (status.get('allowed_bots') or [])],
        "",
        f"Broker carregado: {status.get('broker_loaded')}",
        f"Broker import error: {status.get('broker_import_error')}",
        "",
        "BingX READY:",
        f"OK: {ready.get('ok')}",
        f"Status: {ready.get('status')}",
    ]
    if ready.get("error"):
        lines.append(f"Erro: {ready.get('error')}")
    if ready.get("balance"):
        bal = ready.get("balance") or {}
        lines.append(f"Saldo USDT total/free: {bal.get('total_usdt')} / {bal.get('free_usdt')}")
    lines += [
        "",
        "Estados seguros:",
        "PAPER = não consulta execução real.",
        "READY = valida API/saldo/permissões, mas não envia ordem.",
        "VERIFY = monta/valida a ordem completa, mas não envia.",
        "LIVE = envia automaticamente se ENABLE_REAL_TRADING=true e Risk Manager permitir.",
    ]
    return "\n".join(lines)


# ==========================================================
# LIVE / SYNC / EXECUTIONS LOG
# ==========================================================

def _broker_call(name, *args, **kwargs):
    if central_broker is None:
        return None, f"broker import error: {BROKER_IMPORT_ERROR}"
    fn = getattr(central_broker, name, None)
    if not callable(fn):
        return None, f"broker sem função {name}"
    try:
        return fn(*args, **kwargs), None
    except Exception as exc:
        return None, str(exc)


def _broker_open_positions():
    raw, err = _broker_call("get_positions")
    if err:
        return [], err
    rows = []
    for p in raw or []:
        if not isinstance(p, dict):
            continue
        contracts = p.get("contracts") or p.get("contractSize") or p.get("amount") or p.get("positionAmt")
        notional = p.get("notional") or p.get("initialMargin") or p.get("margin")
        symbol = normalize_symbol_for_risk(p.get("symbol") or (p.get("info") or {}).get("symbol"))
        side = str(p.get("side") or (p.get("info") or {}).get("side") or "").upper()
        # CCXT costuma retornar contracts=0 para posição zerada.
        try:
            contracts_f = abs(float(contracts or 0))
        except Exception:
            contracts_f = 0.0
        try:
            notional_f = abs(float(notional or 0))
        except Exception:
            notional_f = 0.0
        if contracts_f <= 0 and notional_f <= 0:
            continue
        rows.append({
            "symbol": symbol,
            "side": side,
            "contracts": contracts,
            "notional": notional,
            "entry_price": p.get("entryPrice") or p.get("entry_price") or (p.get("info") or {}).get("avgPrice"),
            "unrealized_pnl": p.get("unrealizedPnl") or p.get("unrealized_pnl"),
            "leverage": p.get("leverage") or (p.get("info") or {}).get("leverage"),
            "raw_symbol": p.get("symbol"),
        })
    return rows, None


def _central_live_positions_payload():
    rows = []
    for key, module in LOADED_BOTS.items():
        try:
            positions = get_open_positions_from_module(module)
        except Exception:
            positions = []
        for p in positions:
            if not isinstance(p, dict):
                continue
            is_live = (
                str(p.get("execution_mode") or "").upper() == "LIVE"
                or bool(p.get("live_order_id"))
                or bool(p.get("bingx_order_id"))
            )
            if not is_live:
                continue
            rows.append({
                "bot": key,
                "symbol": normalize_symbol_for_risk(p.get("symbol") or p.get("ativo") or p.get("pair")),
                "side": str(p.get("side") or p.get("direction") or "").upper(),
                "setup": p.get("setup") or p.get("setup_label"),
                "entry": p.get("entry") or p.get("entrada"),
                "stop": p.get("stop") or p.get("sl") or p.get("stop_atual"),
                "tp50": p.get("tp50"),
                "order_id": p.get("live_order_id") or p.get("bingx_order_id"),
            })
    return rows


def _execution_log_items(limit=20):
    items, err = _broker_call("get_executions_log", limit)
    if err:
        return [], err
    return items or [], None


def build_executions_log_report(limit=20):
    items, err = _execution_log_items(limit=limit)
    lines = [
        "📜 EXECUTIONS LOG — CENTRAL QUANT",
        f"Data/hora: {data_hora_sp_str()}",
        f"Eventos lidos: {len(items)}",
    ]
    if err:
        lines.append(f"Erro: {err}")
        return "\n".join(lines)
    if not items:
        lines += ["", "Nenhum evento de execução registrado ainda."]
        return "\n".join(lines)
    lines += ["", "Últimos eventos:"]
    for e in items[-limit:]:
        if not isinstance(e, dict):
            lines.append(f"- {e}")
            continue
        lines.append(
            f"- {e.get('ts')} | {e.get('event')} | {e.get('status')} | "
            f"sent={e.get('sent')} | {e.get('symbol')} {e.get('side')} | "
            f"notional={e.get('notional_usdt')} | amount={e.get('amount')} | id={e.get('order_id') or e.get('id')}"
        )
        if e.get("error"):
            lines.append(f"  erro: {e.get('error')}")
        if e.get("client_order_id"):
            lines.append(f"  clientOrderId: {e.get('client_order_id')}")
    return "\n".join(lines)


def build_live_report():
    ready = bingx_ready_payload() if BINGX_READY_CHECK_ENABLED else {"ok": None, "status": "READY_CHECK_DISABLED"}
    balance = (ready.get("balance") or {}) if isinstance(ready, dict) else {}
    broker_positions, pos_err = _broker_open_positions()
    central_live = _central_live_positions_payload()
    exec_items, exec_err = _execution_log_items(limit=5)

    lines = [
        "🟢 LIVE STATUS — CENTRAL QUANT / BINGX",
        f"Data/hora: {data_hora_sp_str()}",
        "",
        f"Execution mode: {EXECUTION_MODE}",
        f"ENABLE_REAL_TRADING: {ENABLE_REAL_TRADING}",
        f"Broker READY: {ready.get('ok')} | {ready.get('status')}",
    ]
    if ready.get("error"):
        lines.append(f"Erro READY: {ready.get('error')}")
    if balance:
        lines.append(f"Saldo USDT total/free/used: {balance.get('total_usdt')} / {balance.get('free_usdt')} / {balance.get('used_usdt')}")
    lines += [
        "",
        "POSIÇÕES BINGX",
    ]
    if pos_err:
        lines.append(f"Erro ao ler posições: {pos_err}")
    elif not broker_positions:
        lines.append("Nenhuma posição aberta na BingX.")
    else:
        for p in broker_positions[:30]:
            lines.append(
                f"- {p.get('symbol')} {p.get('side')} | contracts={p.get('contracts')} | "
                f"notional={p.get('notional')} | entry={p.get('entry_price')} | uPnL={p.get('unrealized_pnl')} | lev={p.get('leverage')}"
            )

    lines += ["", "POSIÇÕES LIVE REGISTRADAS NA CENTRAL"]
    if not central_live:
        lines.append("Nenhuma posição LIVE registrada na Central.")
    else:
        for p in central_live[:30]:
            lines.append(f"- {p.get('bot')} {p.get('symbol')} {p.get('side')} {p.get('setup')} | order={p.get('order_id')}")

    lines += ["", "ÚLTIMAS EXECUÇÕES"]
    if exec_err:
        lines.append(f"Erro ao ler log: {exec_err}")
    elif not exec_items:
        lines.append("Nenhum evento registrado ainda.")
    else:
        for e in exec_items[-5:]:
            lines.append(f"- {e.get('ts')} | {e.get('status')} | sent={e.get('sent')} | {e.get('symbol')} {e.get('side')} | id={e.get('order_id') or e.get('id')}")
    return "\n".join(lines)


def build_sync_report():
    broker_positions, pos_err = _broker_open_positions()
    central_live = _central_live_positions_payload()

    broker_keys = {(p.get("symbol"), str(p.get("side") or "").upper()) for p in broker_positions}
    central_keys = {(p.get("symbol"), str(p.get("side") or "").upper()) for p in central_live}

    only_bingx = sorted(list(broker_keys - central_keys))
    only_central = sorted(list(central_keys - broker_keys))
    matched = sorted(list(broker_keys & central_keys))

    lines = [
        "🔄 SYNC CENTRAL x BINGX",
        f"Data/hora: {data_hora_sp_str()}",
        "",
        f"BingX positions: {len(broker_positions)}",
        f"Central LIVE positions: {len(central_live)}",
        f"Casadas: {len(matched)}",
        f"Só na BingX: {len(only_bingx)}",
        f"Só na Central: {len(only_central)}",
    ]
    if pos_err:
        lines += ["", f"Erro ao ler BingX: {pos_err}"]
        return "\n".join(lines)
    if matched:
        lines += ["", "Casadas:"] + [f"- {sym} {side}" for sym, side in matched[:20]]
    if only_bingx:
        lines += ["", "⚠️ Só na BingX:"] + [f"- {sym} {side}" for sym, side in only_bingx[:20]]
    if only_central:
        lines += ["", "⚠️ Só na Central:"] + [f"- {sym} {side}" for sym, side in only_central[:20]]
    if not only_bingx and not only_central:
        lines += ["", "✅ Central LIVE e BingX sincronizadas."]
    else:
        lines += ["", "Ação sugerida: antes de LIVE, investigar qualquer divergência acima."]
    return "\n".join(lines)




# ==========================================================
# RISK AUDIT — /auditrisk
# ==========================================================

def _auditrisk_hours_from_arg(arg=None, default=2):
    try:
        if arg is None or str(arg).strip() == "":
            return int(default)
        raw = str(arg).strip().lower().replace("h", "")
        value = int(float(raw))
        return max(1, min(value, 168))
    except Exception:
        return int(default)


def _auditrisk_event_epoch(row):
    try:
        value = row.get("epoch")
        if value is not None:
            return float(value)
    except Exception:
        pass
    return 0.0


def _auditrisk_raw_dict(row):
    raw = row.get("raw") if isinstance(row, dict) else None
    return raw if isinstance(raw, dict) else {}


def _auditrisk_field(row, key, default=None):
    if not isinstance(row, dict):
        return default
    value = row.get(key)
    if value is not None and value != "":
        return value
    raw = _auditrisk_raw_dict(row)
    value = raw.get(key)
    if value is not None and value != "":
        return value
    return default


def _auditrisk_norm_bot(value):
    txt = str(value or "").upper().strip()
    if not txt or txt in {"NONE", "NULL", "N/A"}:
        return "N/A"
    if "PREDATOR" in txt:
        return "PREDATOR"
    if "DONKEY" in txt:
        return "DONKEY"
    if "TURTLE" in txt:
        return "TURTLE"
    if "FALCON" in txt:
        return "FALCON"
    if "COBRA" in txt:
        return "COBRA"
    if "MEME" in txt:
        return "MEME"
    if "TREND" in txt:
        return "TRENDPRO"
    return txt


def _auditrisk_history_events(limit=3000):
    try:
        import history_manager as super_history_manager
        path = Path(getattr(super_history_manager, "HISTORY_EVENTS_FILE", CENTRAL_DATA_DIR / "history_events.jsonl"))
        return _read_jsonl_tail(path, limit=limit)
    except Exception as exc:
        print("ERRO auditrisk history events:", exc)
        return []


def _auditrisk_decision_events(limit=3000):
    rows = []
    try:
        rows.extend(decision_log_items(limit=limit))
    except Exception:
        pass
    for ev in _auditrisk_history_events(limit=limit):
        event_name = str(ev.get("event") or ev.get("event_type") or ev.get("type") or "").upper()
        raw = _auditrisk_raw_dict(ev)
        raw_decision = str(raw.get("decision") or raw.get("allowed") or raw.get("status") or "").upper()
        if event_name in {"RISK_DECISION", "RISK_ALLOW", "RISK_DENY", "TRADE_BLOCKED"} or raw_decision in {"ALLOW", "DENY", "TRUE", "FALSE"}:
            rows.append(ev)

    dedup = {}
    for r in rows:
        key = str(r.get("uid") or r.get("trade_id") or "") + "|" + str(r.get("epoch") or r.get("ts") or "")
        if not key.strip("|"):
            key = json.dumps(r, ensure_ascii=False, default=str)[:300]
        dedup[key] = r
    return list(dedup.values())


def _auditrisk_open_events(limit=3000):
    rows = []
    for ev in _auditrisk_history_events(limit=limit):
        event_name = str(ev.get("event") or ev.get("event_type") or ev.get("type") or "").upper()
        event_raw = str(ev.get("event_raw") or "").upper()
        if event_name in {"TRADE_OPENED"} or event_raw in {"ENTRY", "OPEN", "ENTRADA"}:
            rows.append(ev)
    return rows


def _auditrisk_poi_events(limit=3000):
    rows = []
    for ev in _auditrisk_history_events(limit=limit):
        event_name = str(ev.get("event") or ev.get("event_type") or ev.get("type") or "").upper()
        event_raw = str(ev.get("event_raw") or "").upper()
        setup = str(ev.get("setup") or "").upper()
        if event_name == "POI" or event_raw == "POI" or setup == "POI":
            rows.append(ev)
    return rows


def _auditrisk_decision_payload(row):
    raw = _auditrisk_raw_dict(row)
    decision = str(row.get("decision") or row.get("result") or row.get("risk_decision") or raw.get("decision") or raw.get("result") or "").upper()
    allowed_value = row.get("allowed")
    if allowed_value is None:
        allowed_value = raw.get("allowed")
    if allowed_value is None and decision in {"ALLOW", "ALLOWED", "RISK_ALLOW"}:
        allowed = True
    elif allowed_value is None and decision in {"DENY", "DENIED", "BLOCKED", "RISK_DENY"}:
        allowed = False
    else:
        allowed = str(allowed_value).strip().lower() in {"1", "true", "yes", "sim", "allow", "allowed"}
    bot = _auditrisk_norm_bot(_auditrisk_field(row, "bot", ""))
    symbol = normalize_symbol_for_risk(_auditrisk_field(row, "symbol", ""))
    side = str(_auditrisk_field(row, "side", "") or "").upper()
    return {
        "epoch": _auditrisk_event_epoch(row),
        "ts": row.get("ts"),
        "bot": bot,
        "symbol": symbol,
        "side": side,
        "decision": "ALLOW" if allowed else "DENY",
        "allowed": allowed,
        "trade_id": row.get("trade_id") or raw.get("trade_id"),
        "reasons": row.get("reasons") or raw.get("reasons") or [],
    }


def _auditrisk_entry_payload(row):
    raw = _auditrisk_raw_dict(row)
    return {
        "epoch": _auditrisk_event_epoch(row),
        "ts": row.get("ts"),
        "bot": _auditrisk_norm_bot(_auditrisk_field(row, "bot", "")),
        "symbol": normalize_symbol_for_risk(_auditrisk_field(row, "symbol", "")),
        "side": str(_auditrisk_field(row, "side", "") or "").upper(),
        "setup": str(_auditrisk_field(row, "setup", "") or "").upper(),
        "trade_id": row.get("trade_id") or raw.get("trade_id"),
    }


def _auditrisk_has_risk_in_code(bot_key):
    try:
        cfg = BOT_CONFIGS.get(bot_key) or {}
        file_path = cfg.get("file")
        if not file_path or not Path(file_path).exists():
            return False
        txt = Path(file_path).read_text(encoding="utf-8", errors="ignore")
        return ("can_open_trade" in txt or "/can_open_trade" in txt) and ("ALLOW" in txt or "DENY" in txt or "allowed" in txt.lower())
    except Exception:
        return False


def _auditrisk_match_decision(entry, decisions, window_seconds=1800):
    best = None
    e_epoch = float(entry.get("epoch") or 0)
    for dec in decisions:
        if not dec.get("allowed"):
            continue
        if dec.get("bot") != entry.get("bot"):
            continue
        if dec.get("symbol") and entry.get("symbol") and dec.get("symbol") != entry.get("symbol"):
            continue
        if dec.get("side") and entry.get("side") and dec.get("side") != entry.get("side"):
            continue
        d_epoch = float(dec.get("epoch") or 0)
        if e_epoch and d_epoch and abs(e_epoch - d_epoch) > window_seconds:
            continue
        if best is None or abs((d_epoch or 0) - (e_epoch or 0)) < abs((best.get("epoch") or 0) - (e_epoch or 0)):
            best = dec
    return best


def build_audit_risk_report(hours=2, limit=3000):
    hours = _auditrisk_hours_from_arg(hours, default=2)
    since_epoch = time.time() - (hours * 3600)

    entries_all = [_auditrisk_entry_payload(x) for x in _auditrisk_open_events(limit=limit)]
    pois_all = [_auditrisk_entry_payload(x) for x in _auditrisk_poi_events(limit=limit)]
    decisions_all = [_auditrisk_decision_payload(x) for x in _auditrisk_decision_events(limit=limit)]

    entries = [e for e in entries_all if not e.get("epoch") or e.get("epoch") >= since_epoch]
    pois = [e for e in pois_all if not e.get("epoch") or e.get("epoch") >= since_epoch]
    decisions = [d for d in decisions_all if not d.get("epoch") or d.get("epoch") >= since_epoch]

    exposure_rows = _all_open_positions_payload()
    exposure_by_bot = {}
    for r in exposure_rows:
        bot = _auditrisk_norm_bot(r.get("bot"))
        exposure_by_bot[bot] = exposure_by_bot.get(bot, 0) + 1

    stats = {}
    for key in BOT_CONFIGS.keys():
        b = bot_health(key, BOT_CONFIGS[key])
        stats[key] = {
            "enabled": bool(b.get("enabled")),
            "loaded": bool(b.get("loaded")),
            "risk_code": _auditrisk_has_risk_in_code(key),
            "exposure": exposure_by_bot.get(key, 0),
            "entries": 0,
            "entries_with_allow": 0,
            "entries_without_allow": 0,
            "allows": 0,
            "denies": 0,
            "pois": 0,
            "unmatched_examples": [],
        }

    for dec in decisions:
        bot = dec.get("bot") or "N/A"
        if bot not in stats:
            stats[bot] = {"enabled": False, "loaded": False, "risk_code": False, "exposure": exposure_by_bot.get(bot, 0), "entries": 0, "entries_with_allow": 0, "entries_without_allow": 0, "allows": 0, "denies": 0, "pois": 0, "unmatched_examples": []}
        if dec.get("allowed"):
            stats[bot]["allows"] += 1
        else:
            stats[bot]["denies"] += 1

    for poi in pois:
        bot = poi.get("bot") or "N/A"
        if bot in stats:
            stats[bot]["pois"] += 1

    for entry in entries:
        bot = entry.get("bot") or "N/A"
        if bot not in stats:
            stats[bot] = {"enabled": False, "loaded": False, "risk_code": False, "exposure": exposure_by_bot.get(bot, 0), "entries": 0, "entries_with_allow": 0, "entries_without_allow": 0, "allows": 0, "denies": 0, "pois": 0, "unmatched_examples": []}
        stats[bot]["entries"] += 1
        match = _auditrisk_match_decision(entry, decisions)
        if match:
            stats[bot]["entries_with_allow"] += 1
        else:
            stats[bot]["entries_without_allow"] += 1
            if len(stats[bot]["unmatched_examples"]) < 3:
                stats[bot]["unmatched_examples"].append(entry)

    total_entries = sum(v.get("entries", 0) for v in stats.values())
    total_unmatched = sum(v.get("entries_without_allow", 0) for v in stats.values())
    total_allows = sum(v.get("allows", 0) for v in stats.values())
    total_denies = sum(v.get("denies", 0) for v in stats.values())

    lines = [
        "🧪 AUDITORIA DE RISCO — CENTRAL QUANT",
        f"Data/hora: {data_hora_sp_str()}",
        f"Janela auditada: últimas {hours}h",
        "",
        "Resumo:",
        f"- Entradas detectadas no History: {total_entries}",
        f"- Entradas com ALLOW correspondente: {total_entries - total_unmatched}",
        f"- Entradas sem ALLOW correspondente: {total_unmatched}",
        f"- Decisões ALLOW lidas: {total_allows}",
        f"- Decisões DENY/BLOCK lidas: {total_denies}",
        f"- Exposição atual: {len(exposure_rows)} posições",
        "",
        "Leitura por robô:",
    ]

    for key in BOT_CONFIGS.keys():
        s = stats.get(key) or {}
        if not s.get("enabled"):
            status = "⚪ PAUSADO"
        elif not s.get("loaded"):
            status = "🔴 NÃO CARREGADO"
        elif s.get("entries_without_allow", 0) > 0:
            status = "🔴 ALERTA"
        elif not s.get("risk_code"):
            status = "🟠 RISK NÃO CONFIRMADO"
        elif s.get("entries", 0) == 0 and s.get("allows", 0) == 0 and s.get("denies", 0) == 0:
            status = "🟡 OBSERVAR"
        else:
            status = "✅ OK"

        lines += [
            "",
            f"{key} — {status}",
            f"- Carregado: {s.get('loaded')} | Habilitado: {s.get('enabled')}",
            f"- Risk no código: {'sim' if s.get('risk_code') else 'não confirmado'}",
            f"- Posições atuais: {s.get('exposure', 0)}",
            f"- Entradas: {s.get('entries', 0)} | com ALLOW: {s.get('entries_with_allow', 0)} | sem ALLOW: {s.get('entries_without_allow', 0)}",
            f"- ALLOW: {s.get('allows', 0)} | DENY/BLOCK: {s.get('denies', 0)} | POI: {s.get('pois', 0)}",
        ]
        examples = s.get("unmatched_examples") or []
        if examples:
            lines.append("- Exemplos sem ALLOW:")
            for e in examples:
                lines.append(f"  • {e.get('ts')} | {e.get('symbol')} {e.get('side')} {e.get('setup')} | id={e.get('trade_id')}")

    lines += [
        "",
        "Interpretação:",
        "- OK: entradas recentes têm autorização da Central ou o robô não abriu novas entradas na janela.",
        "- OBSERVAR: robô está carregado, mas não teve decisão/entrada recente na janela.",
        "- ALERTA: houve entrada recente sem ALLOW correspondente no History/Decision Log.",
        "",
        "Comandos úteis:",
        "/auditrisk 1 — audita última 1h",
        "/auditrisk 24 — audita últimas 24h",
        "/decisionlog — vê decisões recentes",
        "/history — vê eventos consolidados",
    ]

    if total_unmatched > 0:
        lines += ["", "Ação sugerida: manter pausado ou revisar qualquer robô com ALERTA antes de aumentar risco."]
    else:
        lines += ["", "Conclusão: nenhum vazamento recente de entrada foi detectado na janela auditada."]

    return "\n".join(lines)


def build_risk_report():
    try:
        autosync_trade_registry(reason="risk")
    except Exception as exc:
        print("AVISO SYNC REGISTRY ANTES DO RISK:", exc)
    exposure_snapshot = central_exposure_snapshot()
    rows = _all_open_positions_payload()
    by_symbol = {}
    for r in rows:
        by_symbol.setdefault(r.get("symbol"), []).append(r)

    total_pos = int(exposure_snapshot.get("total_positions_open") or 0)
    long_pos = int(exposure_snapshot.get("long_positions_open") or 0)
    short_pos = int(exposure_snapshot.get("short_positions_open") or 0)
    mem = _risk_memory_block_payload()

    notes = []
    blocks = []

    if total_pos >= GLOBAL_RISK_MAX_POSITIONS:
        blocks.append(f"DENY novas entradas: posições abertas {total_pos}/{GLOBAL_RISK_MAX_POSITIONS}.")
    if mem.get("blocked"):
        blocks.append(f"DENY novas entradas: memória {mem.get('usage_pct')}% >= {GLOBAL_RISK_MEMORY_BLOCK_PCT}%.")

    if total_pos:
        long_conc = long_pos / max(total_pos, 1) * 100
        short_conc = short_pos / max(total_pos, 1) * 100
        side_conc = max(long_conc, short_conc)
        dominant = "SHORT" if short_pos >= long_pos else "LONG"
        if side_conc >= GLOBAL_RISK_MAX_SIDE_CONCENTRATION_PCT:
            notes.append(f"Concentração {dominant}: {side_conc:.1f}% ({max(long_pos, short_pos)}/{total_pos}).")
            blocks.append(f"DENY novos {dominant}s até concentração ficar abaixo de {GLOBAL_RISK_MAX_SIDE_CONCENTRATION_PCT}%.")

    repeated = []
    for sym, items in by_symbol.items():
        if len(items) >= GLOBAL_RISK_MAX_SYMBOL_EXPOSURE:
            repeated.append((sym, len(items), sorted(set([x.get("bot") for x in items]))))
            blocks.append(f"DENY nova entrada em {sym}: {len(items)} exposições abertas.")

    lines = [
        "🛡️ RISK MANAGER GLOBAL — DECISIONAL",
        f"Data/hora: {data_hora_sp_str()}",
        "",
        f"Posições: {total_pos} | LONG {long_pos} | SHORT {short_pos}",
        f"Limite global: {GLOBAL_RISK_MAX_POSITIONS}",
        f"Limite concentração direcional: {GLOBAL_RISK_MAX_SIDE_CONCENTRATION_PCT}%",
        f"Limite por ativo: {GLOBAL_RISK_MAX_SYMBOL_EXPOSURE}",
        f"Bloqueio por memória: {GLOBAL_RISK_MEMORY_BLOCK_PCT}%",
        f"Memória atual: {mem.get('rss_mb')} MB | {mem.get('usage_pct')}%",
        "",
        "Observações:",
    ]
    lines += [f"- {n}" for n in notes] if notes else ["- Nenhuma concentração crítica além dos parâmetros definidos."]

    if repeated:
        lines += ["", "Ativos repetidos:"]
        for sym, count, bots in repeated[:20]:
            lines.append(f"- {sym}: {count} posições | bots={','.join([str(b) for b in bots])}")

    lines += ["", "Bloqueios decisórios ativos:"]
    if blocks:
        lines += [f"- {b}" for b in blocks]
    else:
        lines.append("- Nenhum bloqueio decisório ativo.")

    lines += [
        "",
        "Regras V3.1:",
        f"- Posições >= {GLOBAL_RISK_MAX_POSITIONS}: DENY novas entradas.",
        f"- Memória >= {GLOBAL_RISK_MEMORY_BLOCK_PCT}%: DENY novas entradas.",
        f"- Concentração LONG/SHORT >= {GLOBAL_RISK_MAX_SIDE_CONCENTRATION_PCT}%: DENY novas entradas no lado dominante.",
        f"- Ativo com {GLOBAL_RISK_MAX_SYMBOL_EXPOSURE}+ exposições: DENY nova entrada no ativo.",
        "- Fechamento/reduceOnly continua permitido.",
        "",
        "Importante:",
        "Este Risk Manager responde ALLOW/DENY em /can_open_trade. Para bloquear entradas reais/VERIFY, o robô precisa consultar esta rota antes de executar.",
    ]
    try:
        import history_manager as _risk_history_manager
        _risk_history_manager.log_event(
            "RISK_SNAPSHOT",
            {
                "bot": "CENTRAL",
                "source": "risk_report",
                "total_positions_open": total_pos,
                "long_positions_open": long_pos,
                "short_positions_open": short_pos,
                "global_limit": GLOBAL_RISK_MAX_POSITIONS,
                "side_concentration_limit_pct": GLOBAL_RISK_MAX_SIDE_CONCENTRATION_PCT,
                "symbol_exposure_limit": GLOBAL_RISK_MAX_SYMBOL_EXPOSURE,
                "memory_block_pct": GLOBAL_RISK_MEMORY_BLOCK_PCT,
                "memory": mem,
                "notes": notes,
                "blocks": blocks,
                "repeated_symbols": [
                    {"symbol": sym, "count": count, "bots": bots}
                    for sym, count, bots in repeated
                ],
                "result": "SNAPSHOT",
            },
            source="risk_report",
            trade_id=f"RISK-SNAPSHOT-{int(time.time())}",
        )
    except Exception as exc:
        print("ERRO HISTORY risk snapshot:", exc)

    return "\n".join(lines)


def build_ranking_report():
    rows = []
    exposure_snapshot = central_exposure_snapshot()
    by_bot_exposure = exposure_snapshot.get("by_bot", {}) or {}
    for key, cfg in BOT_CONFIGS.items():
        b = bot_health(key, cfg)
        h = b.get("health", {}) or {}
        exp = by_bot_exposure.get(key, {}) or {}
        best = exp.get("best_open_runner") or {}
        expectancy = safe_round(h.get("expectancy_r"), 4, None)
        pf = safe_round(h.get("profit_factor_r"), 4, None)
        runner = safe_round(best.get("runner_r"), 4, 0)
        mfe = safe_round(h.get("mfe_avg_r"), 4, None)
        score = (expectancy or 0) * 10 + (pf or 0) + (runner or 0) + (mfe or 0)
        rows.append({
            "key": key,
            "name": cfg.get("name"),
            "score": score,
            "pf": pf,
            "expectancy": expectancy,
            "runner": runner,
            "positions": exp.get("total"),
            "mfe_r": mfe,
        })

    rows.sort(key=lambda x: x["score"], reverse=True)
    lines = ["🏆 RANKING DOS ROBÔS", f"Data/hora: {data_hora_sp_str()}", ""]
    for i, r in enumerate(rows, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
        lines.append(
            f"{medal} {r['key']} — {r['name']} | "
            f"score={safe_round(r['score'],2,0)} | PF={r['pf']} | Exp={r['expectancy']}R | "
            f"Runner={r['runner']}R | MFE={r['mfe_r']}R | pos={r['positions']}"
        )
    return "\n".join(lines)


def build_meta_supervisor_report():
    exposure_snapshot = central_exposure_snapshot()
    mem = memory_snapshot("meta_memory", store=True)
    suggestions = []
    by_bot = exposure_snapshot.get("by_bot", {}) or {}

    total_pos = int(exposure_snapshot.get("total_positions_open") or 0)
    long_pos = int(exposure_snapshot.get("long_positions_open") or 0)
    short_pos = int(exposure_snapshot.get("short_positions_open") or 0)

    if total_pos and short_pos / max(total_pos, 1) >= 0.90:
        suggestions.append("Exposição 90%+ SHORT: pausar novas entradas SHORT ou reduzir risco até equilibrar.")
    if total_pos and long_pos / max(total_pos, 1) >= 0.90:
        suggestions.append("Exposição 90%+ LONG: pausar novas entradas LONG ou reduzir risco até equilibrar.")
    if mem.get("usage_pct") and mem.get("usage_pct") >= MEMORY_ALERT_THRESHOLD_PCT:
        suggestions.append("Memória acima do alerta: considerar upgrade Render, separar Turtle/Donkey ou reduzir históricos.")

    for key, cfg in BOT_CONFIGS.items():
        b = bot_health(key, cfg)
        h = b.get("health", {}) or {}
        exp = by_bot.get(key, {}) or {}
        pf = safe_round(h.get("profit_factor_r"), 4, None)
        expectancy = safe_round(h.get("expectancy_r"), 4, None)
        pos = int(exp.get("total") or 0)
        last_signals = h.get("last_signals_sent")
        if pf is not None and pf < 1:
            suggestions.append(f"{key}: PF abaixo de 1. Monitorar degradação antes de aumentar risco.")
        if expectancy is not None and expectancy < 0:
            suggestions.append(f"{key}: expectancy negativa. Avaliar reduzir risco/filtrar setups fracos.")
        if pos >= 20:
            suggestions.append(f"{key}: muitas posições abertas ({pos}). Avaliar limite/cooldown.")
        if last_signals == 0 and key in {"TRENDPRO", "FALCON"}:
            suggestions.append(f"{key}: sem sinais no último ciclo; verificar funil antes de concluir falha.")

    if not suggestions:
        suggestions.append("Nenhuma recomendação crítica agora. Manter monitoramento normal.")

    lines = [
        "🧠 META SUPERVISOR — INTELIGÊNCIA OPERACIONAL",
        f"Data/hora: {data_hora_sp_str()}",
        "",
        "Recomendações:",
    ] + [f"- {s}" for s in suggestions]
    lines += [
        "",
        "Observação:",
        "As recomendações são estatísticas/operacionais. Não alteram automaticamente as estratégias.",
    ]
    return "\n".join(lines)




# ==========================================================
# EXECUTIVE ALERT MANAGER — INTEGRAÇÃO COM DASHBOARD/REPORTS
# ==========================================================

def _executive_alerts_snapshot_for_reports(check_only=True):
    """
    Lê o Executive Alert Manager de forma segura para uso em:
    - Executive Dashboard
    - CEO Daily Report
    - Executive Report Diário
    - Executive Report Mensal

    Usa check_only=True por padrão para não gerar spam, não alterar cooldown e não
    poluir o log quando o relatório apenas precisa exibir o estado atual.
    """
    try:
        payload = build_executive_alerts(check_only=check_only)
        if not isinstance(payload, dict):
            raise ValueError("build_executive_alerts retornou payload inválido")
        hs = payload.get("health_score") or {}
        if not isinstance(hs, dict):
            hs = {}
        return {
            "ok": bool(payload.get("ok", True)),
            "enabled": bool(payload.get("enabled", True)),
            "status": payload.get("status", "UNKNOWN"),
            "version": payload.get("version"),
            "generated_at": payload.get("generated_at"),
            "health_score": {
                "score": int(hs.get("score", 100) or 100),
                "label": hs.get("label", "EXCELENTE"),
                "reasons": hs.get("reasons", []) or [],
            },
            "alerts_count": int(payload.get("alerts_count", 0) or 0),
            "alerts_to_notify_count": int(payload.get("alerts_to_notify_count", 0) or 0),
            "resolved_count": len(payload.get("resolved") or []),
            "pipeline_status": payload.get("pipeline_status"),
            "executive_summary": payload.get("executive_summary") or "Resumo executivo indisponível.",
            "alerts": payload.get("alerts") or [],
            "alerts_to_notify": payload.get("alerts_to_notify") or [],
            "resolved": payload.get("resolved") or [],
        }
    except Exception as exc:
        return {
            "ok": False,
            "enabled": False,
            "status": "ERROR",
            "version": None,
            "generated_at": data_hora_sp_str(),
            "health_score": {
                "score": 0,
                "label": "ERRO",
                "reasons": [str(exc)],
            },
            "alerts_count": 1,
            "alerts_to_notify_count": 1,
            "resolved_count": 0,
            "pipeline_status": "UNKNOWN",
            "executive_summary": f"Erro ao ler Executive Alert Manager: {exc}",
            "alerts": [{
                "level": "CRITICAL",
                "category": "SYSTEM",
                "title": "Executive Alert Manager indisponível",
                "message": str(exc),
                "action": "Verificar import, deploy e logs do executive_alert_manager.py.",
            }],
            "alerts_to_notify": [],
            "resolved": [],
        }


def _executive_alerts_report_block(title="EXECUTIVE ALERT MANAGER"):
    snap = _executive_alerts_snapshot_for_reports(check_only=True)
    hs = snap.get("health_score") or {}
    alerts = snap.get("alerts") or []
    resolved = snap.get("resolved") or []

    lines = [
        f"🚨 {title}",
        f"Status: {snap.get('status')}",
        f"Health Score: {hs.get('score', 0)}/100 — {hs.get('label', 'N/A')}",
        f"Pipeline: {snap.get('pipeline_status')}",
        f"Alertas ativos: {snap.get('alerts_count', 0)} | Para notificar: {snap.get('alerts_to_notify_count', 0)} | Resolvidos: {snap.get('resolved_count', 0)}",
        f"Resumo: {snap.get('executive_summary')}",
    ]

    reasons = hs.get("reasons") or []
    if reasons:
        lines += ["", "Motivos do Health Score:"]
        for reason in reasons[:6]:
            lines.append(f"- {reason}")

    if alerts:
        lines += ["", "Alertas ativos:"]
        for alert in alerts[:8]:
            level = alert.get("level", "INFO")
            category = alert.get("category", "SYSTEM")
            title = alert.get("title") or alert.get("code") or "Alerta"
            action = alert.get("action")
            line = f"- {level} | {category} | {title}"
            if action:
                line += f" — ação: {action}"
            lines.append(line)
    else:
        lines += ["", "Nenhum alerta executivo ativo."]

    if resolved:
        lines += ["", "Recuperações recentes:"]
        for item in resolved[:5]:
            lines.append(f"- {item.get('title', 'Alerta resolvido')} | {item.get('generated_at')}")

    return "\n".join(lines)

def build_executive_report():
    status = central_watchdog_status()
    exposure_snapshot = central_exposure_snapshot()
    mem = memory_snapshot("executive_memory", store=True)
    score = central_health_score_payload()
    best = exposure_snapshot.get("best_open_runner") or {}
    open_runners = exposure_snapshot.get("open_runners") or {}
    total_pos = int(exposure_snapshot.get("total_positions_open") or 0)
    long_pos = int(exposure_snapshot.get("long_positions_open") or 0)
    short_pos = int(exposure_snapshot.get("short_positions_open") or 0)

    ranking_rows = []
    for key, cfg in BOT_CONFIGS.items():
        b = bot_health(key, cfg)
        h = b.get("health", {}) or {}
        exp = (exposure_snapshot.get("by_bot") or {}).get(key, {}) or {}
        runner = safe_round((exp.get("best_open_runner") or {}).get("runner_r"), 2, 0)
        expectancy = safe_round(h.get("expectancy_r"), 2, 0)
        ranking_rows.append((key, runner + expectancy, runner, expectancy, exp.get("total")))
    ranking_rows.sort(key=lambda x: x[1], reverse=True)
    bot_dia = ranking_rows[0] if ranking_rows else None

    risk_status = "ATENÇÃO" if total_pos and max(long_pos, short_pos) / max(total_pos, 1) >= 0.80 else "OK"

    lines = [
        "📌 EXECUTIVE DASHBOARD — CENTRAL QUANT",
        f"Data/hora: {data_hora_sp_str()}",
        "",
        f"Status operacional: {status.get('status')}",
        f"Health Score Central: {score.get('score')}/100 — {score.get('label')}",
        "",
        _ceo_confidence_report_block(),
        "",
        _strategic_advisor_report_block(compact=True),
        "",
        _decision_pack_report_block(compact=True),
        "",
        _executive_decision_report_block(compact=True),
        "",
        _executive_alerts_report_block(),
        "",
        f"Risco direcional: {risk_status}",
        f"Memória: {mem.get('rss_mb')} MB ({mem.get('usage_pct')}%)",
        f"Execução real: {'ATIVA' if ENABLE_REAL_TRADING else 'BLOQUEADA'} | Modo: {EXECUTION_MODE}",
        "",
        "Exposição:",
        f"Total: {total_pos} | LONG: {long_pos} | SHORT: {short_pos}",
        f"Runners: 1R={open_runners.get('runners_1r_open', 0)} | 2R={open_runners.get('runners_2r_open', 0)} | 3R={open_runners.get('runners_3r_open', 0)} | 5R={open_runners.get('runners_5r_open', 0)}",
    ]
    if best:
        lines += [
            "",
            "Melhor runner:",
            f"{best.get('bot')} {best.get('symbol')} {best.get('side')} {best.get('setup')} | {best.get('runner_pct')}% | {best.get('runner_r')}R",
        ]
    if bot_dia:
        lines += [
            "",
            f"Bot destaque: {bot_dia[0]} | runner={bot_dia[2]}R | exp={bot_dia[3]}R | pos={bot_dia[4]}",
        ]
    lines += [
        "",
        "Ações sugeridas:",
    ]
    if risk_status != "OK":
        side = "SHORT" if short_pos >= long_pos else "LONG"
        lines.append(f"- Evitar novas entradas {side} até reduzir concentração.")
    if mem.get("usage_pct") and mem.get("usage_pct") >= MEMORY_ALERT_THRESHOLD_PCT:
        lines.append("- Memória alta: considerar upgrade Render ou separar robôs pesados.")
    if not status.get("ok"):
        lines += [f"- {r}" for r in status.get("reasons", [])]
    if len(lines) and lines[-1] == "Ações sugeridas:":
        lines.append("- Nenhuma ação crítica além do monitoramento normal.")
    return "\n".join(lines)


def daily_snapshot_payload():
    return {
        "ts": data_hora_sp_str(),
        "date": agora_sp().strftime("%Y-%m-%d"),
        "central": central_watchdog_status(),
        "exposure": central_exposure_snapshot(),
        "memory": memory_snapshot("daily_snapshot_memory", store=True),
        "health_score": central_health_score_payload(),
        "ceo_confidence": _ceo_confidence_snapshot_for_reports(),
        "strategic_advisor": _strategic_advisor_snapshot_for_reports(),
        "decision_pack": _decision_pack_snapshot_for_reports(),
        "executive_decision": _executive_decision_snapshot_for_reports(),
    }


def save_daily_snapshot(label=None):
    payload = daily_snapshot_payload()
    date_key = payload.get("date")
    suffix = f"_{label}" if label else ""
    path = DAILY_HISTORY_DIR / f"{date_key}{suffix}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
    return str(path), payload


def build_history_report(days=7):
    files = sorted(DAILY_HISTORY_DIR.glob("*.json"), reverse=True)[:days]
    lines = ["📚 HISTÓRICO CENTRAL QUANT", f"Arquivos: {len(files)}", ""]
    if not files:
        lines.append("Nenhum histórico salvo ainda. Use /snapshot ou aguarde o relatório automático.")
        return "\n".join(lines)
    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            exp = data.get("exposure", {}) or {}
            mem = data.get("memory", {}) or {}
            score = data.get("health_score", {}) or {}
            lines.append(
                f"{data.get('date')} | score={score.get('score')}/100 | "
                f"pos={exp.get('total_positions_open')} L={exp.get('long_positions_open')} S={exp.get('short_positions_open')} | "
                f"mem={mem.get('rss_mb')} MB"
            )
        except Exception as exc:
            lines.append(f"{path.name}: erro ao ler ({exc})")
    return "\n".join(lines)


def build_snapshot_report():
    path, payload = save_daily_snapshot(label="manual")
    exp = payload.get("exposure", {}) or {}
    score = payload.get("health_score", {}) or {}
    return (
        "💾 SNAPSHOT SALVO\n"
        f"Arquivo: {path}\n"
        f"Score: {score.get('score')}/100\n"
        f"Posições: {exp.get('total_positions_open')} | LONG {exp.get('long_positions_open')} | SHORT {exp.get('short_positions_open')}"
    )


def build_simulate_report(arg=None):
    target = str(arg or "").upper().strip()
    exposure_snapshot = central_exposure_snapshot()
    by_bot = exposure_snapshot.get("by_bot", {}) or {}
    if target in by_bot:
        remaining_total = int(exposure_snapshot.get("total_positions_open") or 0) - int(by_bot[target].get("total") or 0)
        return (
            f"🧪 SIMULAÇÃO CONSULTIVA\n\n"
            f"Remover/pausar {target} agora reduziria posições abertas de "
            f"{exposure_snapshot.get('total_positions_open')} para {remaining_total}.\n"
            f"Isso não altera trades; é apenas leitura de exposição atual."
        )
    return (
        "🧪 SIMULAÇÃO CONSULTIVA\n\n"
        "Uso: /simulate TURTLE, /simulate DONKEY, /simulate PREDATOR etc.\n"
        "Nesta versão a simulação usa exposição atual. Simulações estatísticas 30/90 dias exigem histórico consolidado salvo."
    )



def _brief_exposure_text():
    snap = central_exposure_snapshot()
    runners = snap.get("open_runners") or {}
    best = snap.get("best_open_runner") or {}
    lines = [
        "📌 EXPOSIÇÃO RESUMIDA",
        f"Total: {snap.get('total_positions_open')} | LONG: {snap.get('long_positions_open')} | SHORT: {snap.get('short_positions_open')}",
        (
            "Runners: "
            f"1R={runners.get('runners_1r_open', 0)} | "
            f"2R={runners.get('runners_2r_open', 0)} | "
            f"3R={runners.get('runners_3r_open', 0)} | "
            f"5R={runners.get('runners_5r_open', 0)} | "
            f"10R={runners.get('runners_10r_open', 0)}"
        ),
    ]
    if best:
        lines += [
            "",
            "Melhor runner:",
            f"{best.get('bot')} {best.get('symbol')} {best.get('side')} {best.get('setup')} | {best.get('runner_pct')}% | {best.get('runner_r')}R",
        ]
    return "\n".join(lines)


def _brief_memory_text():
    snap = memory_snapshot("brief_memory", store=True)
    return (
        "🧠 MEMÓRIA\n"
        f"RSS: {snap.get('rss_mb')} MB ({snap.get('usage_pct')}%) | "
        f"Threads: {snap.get('threads')} | Limite: {MEMORY_LIMIT_MB} MB"
    )


def build_dashboard_report():
    """
    Painel operacional principal. Organização em blocos: OPERAÇÃO, SAÚDE e CARTEIRA.
    Evita JSON bruto para não estourar o Telegram.
    """
    parts = [
        "📊 DASHBOARD CENTRAL QUANT",
        f"Data/hora: {data_hora_sp_str()}",
        "",
        "==============================\nOPERAÇÃO\n==============================",
        "==============================\nEXECUTIVE\n==============================",
        build_executive_report(),
        "",
        "==============================\nEXECUÇÃO / BINGX\n==============================",
        build_execution_report(),
        "",
        "==============================\nLIVE / SYNC\n==============================",
        _short(build_live_report(), 1800) + "\n\n" + _short(build_sync_report(), 1200),
        "",
        "==============================\nRISK DECISIONAL\n==============================",
        build_risk_report(),
        "",
        "==============================\nSAÚDE\n==============================",
        "==============================\nDIAGNÓSTICO\n==============================",
        build_diagnostic_report(),
        "",
        "==============================\nSELFTEST\n==============================",
        build_selftest_report(),
        "",
        "==============================\nMEMÓRIA\n==============================",
        _brief_memory_text(),
        "",
        "==============================\nCARTEIRA\n==============================",
        "==============================\nHEAT\n==============================",
        _short(build_heatmap_report(), 2600),
        "",
        "==============================\nEXPOSIÇÃO / RUNNERS\n==============================",
        _brief_exposure_text(),
    ]
    return "\n\n".join(parts)

def _line_has_value_v2(line: str) -> bool:
    """
    Remove linhas de /daily que são apenas rótulo vazio:
    Ex.: 'Resultado financeiro:' sem valor logo ao lado.
    """
    if line is None:
        return False
    s = str(line).strip()
    if not s:
        return False

    empty_labels = {
        "Resultado financeiro:",
        "Maior lucro durante o trade:",
        "Maior perda durante o trade:",
        "Lucro devolvido antes do fechamento:",
        "Melhor trade:",
        "Pior trade:",
        "Grandes vencedores:",
    }
    if s in empty_labels:
        return False
    return True


def _clean_daily_text_v2(text: str) -> str:
    """Limpa linhas vazias/labels sem valor para deixar /daily mais executivo."""
    linhas = []
    for raw in str(text or "").splitlines():
        line = raw.strip()
        if not _line_has_value_v2(line):
            continue
        linhas.append(line)
    return "\n".join(linhas).strip()


def _extract_daily_summary_core_v2(bot_key, resumo_text, max_len=900):
    """
    Resumo enxuto para /daily.
    Prioriza números operacionais e evita blocos longos que causam corte no Telegram.
    """
    txt = transform_bot_summary_v2(bot_key, resumo_text or "")
    if not txt:
        return "N/A"

    keep_prefixes = (
        "Modo:", "Smart Predator ativo:", "Sinais", "LONG:", "SHORT:",
        "Trades encerrados:", "Wins:", "Breakeven:", "Loss:",
        "Win rate:", "Win rate sem BE:", "Profit Factor:",
        "Eficiência do gerenciamento", "Lucro esperado", "Lucro médio após TP50",
        "Captura do movimento:", "TP50", "BE hoje:", "Trailing", "Stops",
        "Resultado financeiro:", "Maior lucro", "Maior perda",
        "Lucro devolvido", "Grandes vencedores:", "3R+:", "5R+:", "10R+:",
        "Melhor trade:", "Pior trade:", "Trades ainda ativos:", "Trades Smart Predator ainda ativos:"
    )

    linhas = []
    raw_lines = [line.strip() for line in str(txt).splitlines()]

    for i, line in enumerate(raw_lines):
        if not line:
            continue
        if line.startswith(("📊", "🦅", "🐢", "🐴", "📈", "🦈")):
            continue
        if any(line.startswith(pref) for pref in keep_prefixes):
            # Se for label sozinho e a próxima linha estiver vazia/ausente, remove.
            if line.endswith(":") and i + 1 < len(raw_lines):
                nxt = raw_lines[i + 1].strip()
                if nxt:
                    linhas.append(line)
                    # Mantém a linha seguinte quando ela é o valor do label.
                    if not any(nxt.startswith(pref) for pref in keep_prefixes):
                        linhas.append(nxt)
                elif _line_has_value_v2(line):
                    linhas.append(line)
            elif _line_has_value_v2(line):
                linhas.append(line)

    if not linhas:
        linhas = [line.strip() for line in str(txt).splitlines() if line.strip()][:20]

    out = _clean_daily_text_v2("\n".join(linhas))
    return _short(out, max_len)


def _daily_bot_block_v2(key, cfg, resumo):
    """
    Monta bloco diário curto por robô.
    Regra:
    - Se há leitura executiva, usa ela.
    - Se não há dados suficientes, mostra status operacional + amostra insuficiente.
    - Nunca deixa labels sem valor.
    """
    executivo_v2 = build_strategy_executive_metrics_v2(key, resumo)
    bloco = [f"🤖 {key} — {cfg.get('name')}"]

    if executivo_v2:
        bloco.append(_short(_clean_daily_text_v2(executivo_v2), 950))
    else:
        core = _extract_daily_summary_core_v2(key, resumo, max_len=750)
        if core and core != "N/A":
            bloco.append(core)
        else:
            bloco.append("📈 QUALIDADE EXECUTIVA V2.0.3\nAmostra insuficiente hoje.\nAguardar trades encerrados.")

    return "\n".join(bloco).strip()


def build_daily_risk_summary_v3():
    """Risk enxuto para /daily."""
    try:
        snapshot = central_exposure_snapshot()
        total = int(snapshot.get("total_positions_open") or 0)
        longs = int(snapshot.get("long_positions_open") or 0)
        shorts = int(snapshot.get("short_positions_open") or 0)
        by_symbol = {}
        for key, module in LOADED_BOTS.items():
            try:
                for p in get_open_positions_from_module(module, key=key):
                    sym = str(p.get("symbol") or p.get("ativo") or p.get("pair") or "").upper()
                    if not sym:
                        continue
                    by_symbol.setdefault(sym, set()).add(key)
            except Exception:
                pass

        repeated = sorted(
            [(sym, len(bots), sorted(bots)) for sym, bots in by_symbol.items() if len(bots) >= GLOBAL_RISK_MAX_SYMBOL_EXPOSURE],
            key=lambda x: x[1],
            reverse=True,
        )[:5]

        mem = _risk_memory_block_payload()
        status = "🟢 Dentro do limite"
        if total >= GLOBAL_RISK_MAX_POSITIONS or mem.get("blocked"):
            status = "🔴 BLOQUEAR NOVAS ENTRADAS"
        elif total:
            long_conc = longs / max(total, 1) * 100
            short_conc = shorts / max(total, 1) * 100
            if max(long_conc, short_conc) >= GLOBAL_RISK_MAX_SIDE_CONCENTRATION_PCT:
                dominant = "SHORT" if short_conc >= long_conc else "LONG"
                status = f"🟠 BLOQUEAR NOVOS {dominant}s"
        usage_pct = round((total / max(GLOBAL_RISK_MAX_POSITIONS, 1)) * 100, 1)
        lines = [
            "🛡️ RISCO GLOBAL",
            "Uso da capacidade:",
            f"{total} / {GLOBAL_RISK_MAX_POSITIONS}",
            f"{usage_pct}%",
            f"LONG {longs} | SHORT {shorts}",
            f"Memória: {mem.get('usage_pct')}%",
            f"Status: {status}",
        ]
        if repeated:
            lines += ["", "Ativos com maior exposição:"]
            for sym, count, bots in repeated:
                lines.append(f"- {sym}: {count} bots ({','.join(bots)})")
        return "\n".join(lines)
    except Exception as exc:
        return f"Erro ao gerar risk compacto: {exc}"


def build_daily_ranking_summary_v3():
    """
    Ranking executivo para /daily.
    V3.1:
    - Robôs com menos de V3_MIN_TRADES_FOR_RATING trades não entram no ranking competitivo.
    - São listados como N/A / Amostra insuficiente.
    """
    try:
        exp = central_exposure_snapshot()
        ranked = []
        insufficient = []

        for key in BOT_CONFIGS.keys():
            module = LOADED_BOTS.get(key)
            cfg = BOT_CONFIGS.get(key, {})
            if not module:
                continue

            nota = None
            trades = None
            try:
                resumo = _bot_resumo_text(key, module)
                m = _v3_bot_metrics_from_summary(key, resumo)
                trades = m.get("trades")
                nota = _v3_strategy_score_0_10(m)
            except Exception:
                m = {}

            runner = 0.0
            try:
                bot_exp = (exp.get("by_bot") or {}).get(key, {}) or {}
                best = bot_exp.get("best_open_runner") or {}
                runner = float(best.get("runner_r") or 0.0)
            except Exception:
                runner = 0.0

            if nota is None:
                insufficient.append((key, cfg.get("name"), trades, runner))
                continue

            sort_score = nota + min(max(runner, 0.0), 5.0) * 0.2
            ranked.append((sort_score, key, cfg.get("name"), nota, runner))

        ranked.sort(reverse=True, key=lambda x: x[0])
        medals = ["🥇", "🥈", "🥉", "4.", "5."]
        lines = ["🏆 RANKING EXECUTIVO"]

        if ranked:
            for idx, item in enumerate(ranked[:5]):
                _score, key, name, nota, runner = item
                prefix = medals[idx] if idx < len(medals) else f"{idx+1}."
                runner_txt = f" | runner {runner:.2f}R" if runner and runner > 0 else ""
                lines.append(f"{prefix} {key} — {name}")
                lines.append(f"Nota {_v3_fmt_num(nota, 1)}/10 | {_v3_note_label(nota)}{runner_txt}")
        else:
            lines.append("Nenhum robô com amostra suficiente hoje.")

        if insufficient:
            lines += ["", "Amostra insuficiente:"]
            for key, name, trades, runner in insufficient[:7]:
                trades_txt = f"trades={int(trades or 0)}" if trades is not None else "trades=N/A"
                runner_txt = f" | runner {runner:.2f}R" if runner and runner > 0 else ""
                lines.append(f"- {key}: Nota N/A | {trades_txt}{runner_txt}")

        return "\n".join(lines)
    except Exception as exc:
        return f"Erro ao gerar ranking compacto: {exc}"


def _daily_core_status_from_summary_v3(bot_key, resumo_text):
    """Resumo mínimo quando não há leitura executiva útil."""
    txt = transform_bot_summary_v3(bot_key, resumo_text or "")
    fields = [
        "Modo:", "Sinais Falcon:", "Sinais H1 do dia:", "Sinais H1 do período:", "Sinais Donkey do dia:", "Sinais Turtle:",
        "LONG:", "SHORT:", "Trades encerrados:", "Wins:", "Breakeven:", "Loss:", "Win rate:",
        "TP50 hoje:", "TP50 atingidos:", "BE hoje:", "Trailing hoje:", "Stops hoje:",
        "Trades ainda ativos:", "Trades Smart Predator ainda ativos:",
    ]
    raw = [line.strip() for line in str(txt).splitlines() if line.strip()]
    out = []
    for line in raw:
        if any(line.startswith(f) for f in fields):
            out.append(line)
    return "\n".join(out[:16]).strip()


def _daily_bot_block_v3(key, cfg, resumo):
    m = _v3_bot_metrics_from_summary(key, resumo)
    header = f"🤖 {key} — {cfg.get('name')}"

    # Sem trades encerrados: não mostrar métricas zeradas.
    if _v3_is_insufficient_sample(m):
        sinais = m.get("sinais")
        sinais_line = f"\nSinais hoje: {int(sinais or 0)}" if sinais is not None else ""
        core = _daily_core_status_from_summary_v3(key, resumo)
        return (
            f"{header}\n"
            "📈 QUALIDADE EXECUTIVA V3.1\n"
            "Amostra insuficiente hoje.\n"
            f"Trades encerrados: {int(m.get('trades') or 0)}{sinais_line}\n"
            "Aguardar trades encerrados para calcular as métricas.\n"
            + (("\n" + core) if core else "")
        ).strip()

    executivo = build_strategy_executive_metrics_v3(key, resumo, compact=True)
    if executivo:
        return f"{header}\n{_short(executivo, 900)}"

    core = _daily_core_status_from_summary_v3(key, resumo)
    if core:
        return f"{header}\n{core}"

    return f"{header}\n📈 QUALIDADE EXECUTIVA V3.1\nAmostra insuficiente hoje."


def build_daily_report():
    """
    Pacote diário executivo para colar no ChatGPT.
    V3.0:
    - Risk compacto.
    - Ranking compacto.
    - Sem campos vazios.
    - Sem métricas falsas quando trades encerrados = 0.
    - R apenas como auditoria/grandes vencedores.
    """
    mem = memory_snapshot("daily_light_memory", store=True)
    status = central_watchdog_status()
    exposure_snapshot = central_exposure_snapshot()
    open_runners = exposure_snapshot.get("open_runners") or {}
    best = exposure_snapshot.get("best_open_runner") or {}

    header = [
        "📅 DAILY EXECUTIVO — CENTRAL QUANT V3.1",
        f"Data/hora: {data_hora_sp_str()}",
        "",
        "STATUS",
        f"Central: {status.get('status')} | OK: {status.get('ok')}",
        f"Memória: {mem.get('rss_mb')} MB ({mem.get('usage_pct')}%) | Threads: {mem.get('threads')}",
        "",
        "EXPOSIÇÃO",
        f"Total: {exposure_snapshot.get('total_positions_open')} | LONG: {exposure_snapshot.get('long_positions_open')} | SHORT: {exposure_snapshot.get('short_positions_open')}",
        (
            "Runners: "
            f"1R={open_runners.get('runners_1r_open', 0)} | "
            f"2R={open_runners.get('runners_2r_open', 0)} | "
            f"3R={open_runners.get('runners_3r_open', 0)} | "
            f"5R={open_runners.get('runners_5r_open', 0)} | "
            f"10R={open_runners.get('runners_10r_open', 0)}"
        ),
    ]

    if best:
        header += [
            "",
            "Melhor runner:",
            f"{best.get('bot')} {best.get('symbol')} {best.get('side')} {best.get('setup')} | {best.get('runner_pct')}% | {best.get('runner_r')}R",
        ]

    parts = [
        "\n".join(header),
        build_daily_risk_summary_v3(),
        build_daily_ranking_summary_v3(),
        "🤖 ROBÔS — LEITURA EXECUTIVA",
    ]

    for key in BOT_CONFIGS.keys():
        module = LOADED_BOTS.get(key)
        cfg = BOT_CONFIGS.get(key, {})
        if not module:
            parts.append(f"🤖 {key} — {cfg.get('name')}\nMódulo não carregado: {LOAD_ERRORS.get(key)}")
            continue

        try:
            resumo = _bot_resumo_text(key, module)
        except Exception as exc:
            resumo = f"Erro ao gerar resumo: {exc}"

        parts.append(_daily_bot_block_v3(key, cfg, resumo))

    text = "\n\n==============================\n".join(parts)
    force_gc_if_needed("daily_report_end", force=True)
    return text



# ==========================================================
# EXECUTIVE REPORT DIÁRIO/MENSAL — COMPACTO PARA ANÁLISE
# ==========================================================

def _counter_top_lines(title, data, limit=10, empty="Sem dados."):
    lines = [title]
    if isinstance(data, dict) and data:
        for key, value in list(data.items())[:limit]:
            lines.append(f"- {key}: {value}")
    else:
        lines.append(f"- {empty}")
    return lines


def _safe_history_payload(limit=3000):
    try:
        import history_manager as super_history_manager
        if hasattr(super_history_manager, "build_history_payload"):
            return super_history_manager.build_history_payload(limit=limit)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": False, "error": "history_manager indisponível"}


def _safe_riskstats_payload():
    try:
        import history_manager as super_history_manager
        if hasattr(super_history_manager, "build_riskstats_payload"):
            return super_history_manager.build_riskstats_payload()
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": False, "error": "riskstats indisponível"}


def _compact_history_block(limit=3000):
    payload = _safe_history_payload(limit=limit)
    if not payload.get("ok"):
        return "📚 HISTORY\n- Indisponível: " + str(payload.get("error"))

    totals = payload.get("totals", {}) or {}
    perf = payload.get("performance", {}) or {}
    lines = [
        "📚 HISTORY — RESUMO COMPACTO",
        f"Eventos: {totals.get('events', 0)} | Sinais: {totals.get('signals', 0)} | Entradas: {totals.get('opened', 0)} | Encerrados: {totals.get('closed', 0)}",
        f"Bloqueados: {totals.get('blocked', 0)} | TP50: {totals.get('tp50', 0)} | BE: {totals.get('breakeven', 0)} | Trailing: {totals.get('trailing', 0)}",
        f"PnL total: {perf.get('pnl_total_pct', 0)}% | WR: {perf.get('win_rate_pct', 0)}% | PF: {perf.get('profit_factor_pct', 0)} | R total: {perf.get('r_total', 0)}R",
        "",
    ]
    lines += _counter_top_lines("Eventos por robô:", payload.get("by_bot", {}), limit=8, empty="sem eventos de robôs")
    lines += [""] + _counter_top_lines("Top ativos:", payload.get("by_symbol", {}), limit=8, empty="sem ativos")
    lines += [""] + _counter_top_lines("Top setups:", payload.get("by_setup", {}), limit=8, empty="sem setups")
    return "\n".join(lines)


def _compact_riskstats_block():
    payload = _safe_riskstats_payload()
    if not payload.get("ok"):
        return "📊 RISKSTATS\n- Indisponível: " + str(payload.get("error"))

    summary = payload.get("summary", {}) or {}
    by_bot = payload.get("by_bot_closed", {}) or {}
    by_symbol = payload.get("by_symbol_closed", {}) or {}
    blocked = payload.get("blocked_by_reason", {}) or {}

    lines = [
        "📊 PERFORMANCE / RISKSTATS",
        f"Trades encerrados: {payload.get('totals', {}).get('closed', 0)}",
        f"WR: {summary.get('win_rate_pct', 0)}% | PnL: {summary.get('pnl_total_pct', 0)}% | PF: {summary.get('profit_factor_pct', 0)} | R: {summary.get('r_total', 0)}R",
        "",
        "Por robô:",
    ]
    if by_bot:
        ranked = sorted(by_bot.items(), key=lambda x: float((x[1] or {}).get("pnl_total_pct") or 0), reverse=True)
        for bot, s in ranked[:8]:
            lines.append(f"- {bot}: {s.get('trades', 0)} trades | WR {s.get('win_rate_pct', 0)}% | PnL {s.get('pnl_total_pct', 0)}% | PF {s.get('profit_factor_pct', 0)}")
    else:
        lines.append("- Ainda sem trades encerrados.")

    if by_symbol:
        lines += ["", "Melhores ativos por PnL:"]
        ranked_symbols = sorted(by_symbol.items(), key=lambda x: float((x[1] or {}).get("pnl_total_pct") or 0), reverse=True)
        for sym, s in ranked_symbols[:8]:
            lines.append(f"- {sym}: {s.get('trades', 0)} trades | PnL {s.get('pnl_total_pct', 0)}% | WR {s.get('win_rate_pct', 0)}%")

    lines += ["", "Bloqueios relevantes:"]
    if blocked:
        for reason, count in list(blocked.items())[:8]:
            lines.append(f"- {reason}: {count}")
    else:
        lines.append("- Nenhum bloqueio registrado.")
    return "\n".join(lines)


def _compact_decisionlog_block(limit=120):
    rows = _read_jsonl_tail_v3(CENTRAL_DECISION_LOG_FILE, limit)
    if not rows:
        return "🧾 DECISION LOG\n- Sem decisões recentes registradas."

    total = len(rows)
    allow = 0
    deny = 0
    by_reason = {}
    by_bot = {}
    for item in rows:
        decision = str(item.get("decision", item.get("status", item.get("result", "")))).upper()
        if decision == "ALLOW":
            allow += 1
        if decision in {"DENY", "DENIED", "BLOCKED"}:
            deny += 1
        bot = str(item.get("bot") or item.get("robot") or item.get("source") or "N/A").upper()
        by_bot[bot] = by_bot.get(bot, 0) + 1
        reason = str(item.get("reason") or item.get("motivo") or item.get("result") or "N/A")
        if decision in {"DENY", "DENIED", "BLOCKED"} or reason not in {"N/A", "ALLOW"}:
            by_reason[reason] = by_reason.get(reason, 0) + 1

    lines = [
        "🧾 DECISION LOG — RECENTE",
        f"Decisões lidas: {total} | ALLOW: {allow} | DENY/BLOCK: {deny}",
        "",
    ]
    lines += _counter_top_lines("Por robô:", dict(sorted(by_bot.items(), key=lambda x: x[1], reverse=True)), limit=8)
    lines += [""] + _counter_top_lines("Motivos relevantes:", dict(sorted(by_reason.items(), key=lambda x: x[1], reverse=True)), limit=8, empty="sem motivos críticos")
    return "\n".join(lines)


def _compact_alerts_block():
    """Bloco de alertas agora usa o Executive Alert Manager como fonte principal."""
    try:
        return _executive_alerts_report_block("ALERTAS EXECUTIVOS")
    except Exception as exc:
        status = central_watchdog_status()
        mem = memory_snapshot("executive_alerts_memory", store=True)
        alerts = []
        if not status.get("ok"):
            alerts.extend(status.get("reasons", []) or [])
        if mem.get("usage_pct") and mem.get("usage_pct") >= MEMORY_ALERT_THRESHOLD_PCT:
            alerts.append(f"Memória alta: {mem.get('usage_pct')}%")
        for key, err in LOAD_ERRORS.items():
            if err:
                alerts.append(f"{key}: erro de carregamento: {err}")

        lines = ["🚨 ALERTAS", f"Executive Alert Manager indisponível: {exc}"]
        if alerts:
            for item in alerts[:12]:
                lines.append(f"- {item}")
        else:
            lines.append("- Nenhum alerta crítico no fallback.")
        return "\n".join(lines)


def _compact_execution_pipeline_block():
    try:
        return build_execution_pipeline_text()
    except Exception as exc:
        return (
            "⚙️ EXECUTION PIPELINE — CENTRAL QUANT\n"
            f"Data/hora: {data_hora_sp_str()}\n"
            "Status: ERRO\n"
            f"Erro ao gerar bloco do pipeline: {exc}\n"
            "\n"
            "Observação: este erro não impede o restante do relatório diário."
        )
    

def build_executive_report_daily():
    """
    Relatório diário unificado para análise no ChatGPT.
    Ele substitui a necessidade de rodar vários comandos diariamente, mas mantém
    /history, /risk, /analytics, /decisionlog etc. para investigação sob demanda.
    """
    parts = [
        "📦 EXECUTIVE REPORT DIÁRIO — CENTRAL QUANT",
        f"Data/hora: {data_hora_sp_str()}",
        "Objetivo: resumo compacto para análise diária sem colar centenas de linhas.",
        "",
        "==============================\nEXECUTIVE\n==============================",
        build_executive_report(),
        "",
        "==============================\nEXECUTION PIPELINE\n==============================",
        _compact_execution_pipeline_block(),
        "",
        "==============================\nRISCO GLOBAL\n==============================",
        build_daily_risk_summary_v3(),
        "",
        "==============================\nRANKING / ROBÔS\n==============================",
        build_daily_ranking_summary_v3(),
        "",
        "==============================\nHISTORY\n==============================",
        _compact_history_block(limit=3000),
        "",
        "==============================\nRISKSTATS\n==============================",
        _compact_riskstats_block(),
        "",
        "==============================\nDECISION LOG\n==============================",
        _compact_decisionlog_block(limit=120),
        "",
        "==============================\nALERTAS\n==============================",
        _compact_alerts_block(),
        "",
        "==============================\nROBÔS — LEITURA EXECUTIVA\n==============================",
    ]

    for key in BOT_CONFIGS.keys():
        module = LOADED_BOTS.get(key)
        cfg = BOT_CONFIGS.get(key, {})
        if not module:
            parts.append(f"🤖 {key} — {cfg.get('name')}\nMódulo não carregado: {LOAD_ERRORS.get(key)}")
            continue
        try:
            resumo = _bot_resumo_text(key, module)
            parts.append(_daily_bot_block_v3(key, cfg, resumo))
        except Exception as exc:
            parts.append(f"🤖 {key} — {cfg.get('name')}\nErro ao gerar leitura executiva: {exc}")

    parts += [
        "",
        "==============================\nCOMANDOS SOB DEMANDA\n==============================",
        "Se precisar investigar detalhes: /history, /riskstats, /decisionlog, /executionstats, /risk, /heat, /bots, /health, /analytics.",
    ]
    text = "\n\n".join([str(x).strip() for x in parts if str(x).strip()])
    force_gc_if_needed("executive_report_daily_end", force=True)
    return text


# ==========================================================
# EXECUTIVE DASHBOARD JSON
# Fonte única para CEO Report, Dashboard e futuras APIs
# ==========================================================

def build_executive_dashboard_json():
    try:
        memory_mb = current_rss_mb()
    except Exception:
        memory_mb = None

    try:
        memory_pct = memory_usage_pct(memory_mb)
    except Exception:
        memory_pct = None

    try:
        exposure = central_exposure_snapshot()
    except Exception:
        exposure = {}

    try:
        watchdog = central_watchdog_status()
    except Exception:
        watchdog = {}

    total = exposure.get("total_positions_open", 0)
    longs = exposure.get("long_positions_open", 0)
    shorts = exposure.get("short_positions_open", 0)

    risk_status = "OK"
    try:
        if total >= GLOBAL_RISK_MAX_POSITIONS:
            risk_status = "ATENÇÃO"
        elif memory_pct is not None and memory_pct >= GLOBAL_RISK_MEMORY_BLOCK_PCT:
            risk_status = "ATENÇÃO"
    except Exception:
        pass

    executive_alerts = _executive_alerts_snapshot_for_reports(check_only=True)
    executive_alert_health = executive_alerts.get("health_score") or {}
    ceo_confidence = _ceo_confidence_snapshot_for_reports()
    strategic_advisor = _strategic_advisor_snapshot_for_reports(ceo_confidence=ceo_confidence, compact_source=True)

    return {
        "generated_at": data_hora_sp_str(),
        "status": executive_alerts.get("status") or watchdog.get("status", "OK"),
        "health_score": int(executive_alert_health.get("score", 100) or 100),
        "health_label": executive_alert_health.get("label", "EXCELENTE"),
        "watchdog_status": watchdog.get("status", "OK"),
        "central_watchdog_health_score": 100 if watchdog.get("ok", True) else 70,
        "executive_alerts": executive_alerts,
        "ceo_confidence": ceo_confidence,
        "strategic_advisor": strategic_advisor,
        "decision_pack": _decision_pack_snapshot_for_reports(compact_source=True),
        "executive_decision": _executive_decision_snapshot_for_reports(compact_source=True),
        "real_execution_enabled": bool(ENABLE_REAL_TRADING),
        "execution_mode": EXECUTION_MODE,
        "memory_mb": memory_mb or 0,
        "memory_pct": memory_pct or 0,
        "risk_status": risk_status,
        "positions": total,
        "long": longs,
        "short": shorts,
        "best_runner": exposure.get("best_open_runner"),
    }


def build_ceo_daily_report():
    now = data_hora_sp_str()

    executive = build_executive_dashboard_json()
    pipeline = build_execution_pipeline_status()

    adaptive = pipeline.get("adaptive") or {}
    positions = pipeline.get("positions") or {}
    alerts = pipeline.get("alerts") or []

    risk_status = executive.get("risk_status", "OK")
    confidence = adaptive.get("confidence", 0)
    suggested_weight = adaptive.get("suggested_weight", 1.0)
    action = adaptive.get("recommended_action", "WAIT_SAMPLE")

    components = ((pipeline.get("pipeline") or {}).get("components") or {})

    lines = [
        "🧠 CEO DAILY REPORT — CENTRAL QUANT",
        "",
        f"Data/hora: {now}",
        "",
        "════════════════════════════",
        "STATUS GERAL DA CENTRAL QUANT",
        "════════════════════════════",
        f"Status Operacional: {executive.get('status', 'OK')}",
        f"Modo de Execução: {'REAL' if executive.get('real_execution_enabled') else 'VERIFY'}",
        f"Uso de Memória (Render): {float(executive.get('memory_pct') or 0):.1f}%",
        f"Risco Operacional: {risk_status}",
        f"Confiança Estatística: {float(confidence or 0):.1f}%",
        "",
        "════════════════════════════",
        "CEO CONFIDENCE INDEX",
        "════════════════════════════",
        _ceo_confidence_report_block(),
        "",
        "════════════════════════════",
        "STRATEGIC ADVISOR",
        "════════════════════════════",
        _strategic_advisor_report_block(compact=True),
        "",
        "════════════════════════════",
        "DECISION PACK",
        "════════════════════════════",
        _decision_pack_report_block(compact=True),
        "",
        "════════════════════════════",
        "EXECUTIVE DECISION ENGINE",
        "════════════════════════════",
        _executive_decision_report_block(compact=True),
        "",
        "════════════════════════════",
        "EXECUTIVE ALERT MANAGER",
        "════════════════════════════",
        _executive_alerts_report_block(),
        "",
        "════════════════════════════",
        "PIPELINE",
        "════════════════════════════",
        f"Execution Engine: {'✅' if components.get('execution_engine', {}).get('ok') else '❌'}",
        f"Paper Executor: {'✅' if components.get('paper_executor', {}).get('ok') else '❌'}",
        f"Lifecycle: {'✅' if components.get('paper_lifecycle', {}).get('ok') else '❌'}",
        f"Outcome Evaluator: {'✅' if components.get('outcome_evaluator', {}).get('ok') else '❌'}",
        f"Adaptive Weights: {'✅' if components.get('adaptive_weights', {}).get('ok') else '❌'}",
        "",
        "════════════════════════════",
        "OPERAÇÃO",
        "════════════════════════════",
        f"Posições abertas na Central: {executive.get('positions', 0)}",
        f"LONG: {executive.get('long', 0)} | SHORT: {executive.get('short', 0)}",
        f"PAPER abertas: {positions.get('open', 0)}",
        f"PAPER fechadas: {positions.get('closed', 0)}",
        f"Outcomes pendentes: {positions.get('pending_outcome', 0)}",
        "",
        "════════════════════════════",
        "APRENDIZADO",
        "════════════════════════════",
        f"Ação sugerida: {action}",
        f"Peso sugerido: {suggested_weight}",
        f"Confiança Estatística: {float(confidence or 0):.1f}%",
        f"Trades analisados: {adaptive.get('trades', 0)}",
        "",
        "════════════════════════════",
        "AÇÃO NECESSÁRIA",
        "════════════════════════════",
    ]

    if alerts:
        for alert in alerts:
            lines.append(f"• {alert}")
    else:
        lines.append("Nenhuma ação necessária.")
        lines.append("A Central está operando normalmente.")

    return "\n".join(lines)


def _month_bounds_previous(now=None):
    now = now or agora_sp()
    first_current = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_prev = first_current - timedelta(seconds=1)
    first_prev = last_prev.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    key = first_prev.strftime("%Y-%m")
    label = first_prev.strftime("%m/%Y")
    return first_prev, first_current, key, label


def _event_epoch_value(event):
    try:
        if event.get("epoch") is not None:
            return float(event.get("epoch"))
    except Exception:
        pass
    return None


def _history_events_for_period(start_dt, end_dt, limit=20000):
    try:
        import history_manager as super_history_manager
        if hasattr(super_history_manager, "load_events"):
            events = super_history_manager.load_events(limit=limit)
        else:
            events = (_safe_history_payload(limit=limit).get("recent_events") or [])
    except Exception:
        events = []

    start_epoch = start_dt.timestamp()
    end_epoch = end_dt.timestamp()
    filtered = []
    for event in events or []:
        if not isinstance(event, dict):
            continue
        epoch = _event_epoch_value(event)
        if epoch is None:
            # Sem epoch confiável, mantém apenas quando for o mês pelo texto de data.
            ts = str(event.get("ts") or "")
            if start_dt.strftime("/%m/%Y") in ts:
                filtered.append(event)
            continue
        if start_epoch <= epoch < end_epoch:
            filtered.append(event)
    return filtered


def _stats_from_closed_events(rows):
    pnls = []
    r_values = []
    for item in rows:
        pnl = _safe_float(item.get("result_pct"), None)
        if pnl is not None:
            pnls.append(pnl)
        rr = _safe_float(item.get("result_r"), None)
        if rr is not None:
            r_values.append(rr)
    wins = len([x for x in pnls if x > 0])
    losses = len([x for x in pnls if x < 0])
    be = len([x for x in pnls if x == 0])
    gross_win = sum(x for x in pnls if x > 0)
    gross_loss = abs(sum(x for x in pnls if x < 0))
    return {
        "trades": len(rows),
        "wins": wins,
        "losses": losses,
        "be": be,
        "win_rate_pct": round((wins / max(wins + losses, 1)) * 100, 2),
        "pnl_total_pct": round(sum(pnls), 4),
        "pnl_avg_pct": round(sum(pnls) / max(len(pnls), 1), 4) if pnls else 0.0,
        "r_total": round(sum(r_values), 4),
        "r_avg": round(sum(r_values) / max(len(r_values), 1), 4) if r_values else 0.0,
        "profit_factor_pct": round(gross_win / gross_loss, 4) if gross_loss > 0 else (999 if gross_win > 0 else 0),
    }


def _monthly_group_stats(events, field):
    groups = {}
    for event in events:
        key = str(event.get(field) or "N/A").upper()
        groups.setdefault(key, []).append(event)
    stats = {key: _stats_from_closed_events(rows) for key, rows in groups.items()}
    return dict(sorted(stats.items(), key=lambda x: float(x[1].get("pnl_total_pct") or 0), reverse=True))



def _executive_alert_log_file_path():
    """Caminho padrão do log do Executive Alert Manager."""
    try:
        return CENTRAL_DATA_DIR / "executive_alert_log.jsonl"
    except Exception:
        return Path("data") / "executive_alert_log.jsonl"


def _read_executive_alert_log_rows(limit=50000):
    """Lê o log JSONL do Executive Alert Manager sem depender da rota HTTP."""
    path = _executive_alert_log_file_path()
    rows = []
    try:
        if not path.exists():
            return []
        lines = path.read_text(encoding="utf-8").splitlines()
        if limit:
            lines = lines[-int(limit):]
        for line in lines:
            try:
                item = json.loads(line)
                if isinstance(item, dict):
                    rows.append(item)
            except Exception:
                pass
    except Exception:
        return []
    return rows


def _executive_alert_rows_for_period(start_dt, end_dt, limit=50000):
    start_epoch = start_dt.timestamp()
    end_epoch = end_dt.timestamp()
    rows = []
    for item in _read_executive_alert_log_rows(limit=limit):
        epoch = _safe_float(item.get("epoch"), None)
        if epoch is None:
            generated = str(item.get("generated_at") or "")
            if start_dt.strftime("/%m/%Y") in generated:
                rows.append(item)
            continue
        if start_epoch <= epoch < end_epoch:
            rows.append(item)
    return rows


def _executive_alert_health_score_from_row(row):
    hs = row.get("health_score") or {}
    if isinstance(hs, dict):
        return _safe_float(hs.get("score"), None)
    return None


def _executive_alert_day_key(row):
    epoch = _safe_float(row.get("epoch"), None)
    if epoch is not None:
        try:
            return datetime.fromtimestamp(epoch, TIMEZONE_BR).strftime("%Y-%m-%d")
        except Exception:
            pass
    generated = str(row.get("generated_at") or "")
    try:
        return datetime.strptime(generated[:10], "%d/%m/%Y").strftime("%Y-%m-%d")
    except Exception:
        return "N/A"



def _ceo_confidence_snapshot_for_reports(monthly_stats=None):
    """
    Lê os módulos atuais da Central e calcula o CEO Confidence Index V1.
    É seguro para relatórios: não altera risco, não executa trades e não envia Telegram.
    """
    try:
        executive_alerts = _executive_alerts_snapshot_for_reports(check_only=True)
    except Exception:
        executive_alerts = {}

    try:
        pipeline = build_execution_pipeline_status()
    except Exception:
        pipeline = {}

    try:
        exposure = central_exposure_snapshot()
    except Exception:
        exposure = {}

    try:
        memory = memory_snapshot("ceo_confidence_memory", store=True)
    except Exception:
        memory = {}

    try:
        return build_ceo_confidence_index(
            executive_alerts=executive_alerts,
            pipeline=pipeline,
            exposure=exposure,
            memory=memory,
            monthly_stats=monthly_stats or {},
            extra={
                "execution_mode": EXECUTION_MODE,
                "real_execution_enabled": bool(ENABLE_REAL_TRADING),
            },
        )
    except Exception as exc:
        return {
            "ok": False,
            "version": "CEO-CONFIDENCE-ERROR",
            "generated_at": data_hora_sp_str(),
            "score": 0,
            "label": "ERRO",
            "action": "INVESTIGAR",
            "recommendation": f"Erro ao calcular CEO Confidence Index: {exc}",
            "components": {},
            "strengths": [],
            "risks": [str(exc)],
            "reasons": [],
            "mode": "OBSERVATION_ONLY",
        }


def _ceo_confidence_report_block(monthly_stats=None):
    try:
        payload = _ceo_confidence_snapshot_for_reports(monthly_stats=monthly_stats)
        return build_ceo_confidence_text(payload)
    except Exception as exc:
        return (
            "🧭 CEO CONFIDENCE INDEX — CENTRAL QUANT V1\n"
            f"Data/hora: {data_hora_sp_str()}\n\n"
            "Status: ERRO\n"
            f"Erro ao gerar CEO Confidence Index: {exc}"
        )


def _strategic_advisor_snapshot_for_reports(monthly_stats=None, ceo_confidence=None, compact_source=False):
    """
    Calcula o Strategic Advisor V1 usando snapshots técnicos atuais.
    Não executa trades, não altera risco e não envia Telegram.
    A saída é desenhada para uso assistido: o CEO não decide; o assistente consulta
    comandos técnicos e devolve a ação prática.
    """
    try:
        executive_alerts = _executive_alerts_snapshot_for_reports(check_only=True)
    except Exception:
        executive_alerts = {}

    try:
        pipeline = build_execution_pipeline_status()
    except Exception:
        pipeline = {}

    try:
        exposure = central_exposure_snapshot()
    except Exception:
        exposure = {}

    try:
        memory = memory_snapshot("strategic_advisor_memory", store=True)
    except Exception:
        memory = {}

    try:
        confidence_payload = ceo_confidence or _ceo_confidence_snapshot_for_reports(monthly_stats=monthly_stats)
    except Exception:
        confidence_payload = {}

    portfolio_payload = {}
    try:
        fn = globals().get("build_portfolio_advisor_v1")
        if callable(fn):
            portfolio_payload = fn()
    except Exception:
        portfolio_payload = {}

    try:
        return build_strategic_advisor(
            ceo_confidence=confidence_payload,
            executive_alerts=executive_alerts,
            pipeline=pipeline,
            exposure=exposure,
            memory=memory,
            monthly_stats=monthly_stats or {},
            portfolio_advisor=portfolio_payload,
            extra={
                "execution_mode": EXECUTION_MODE,
                "real_execution_enabled": bool(ENABLE_REAL_TRADING),
                "compact_source": bool(compact_source),
            },
        )
    except Exception as exc:
        return {
            "ok": False,
            "version": "STRATEGIC-ADVISOR-ERROR",
            "generated_at": data_hora_sp_str(),
            "mode": "ASSISTED_DECISION_ENGINE",
            "human_decision_required": False,
            "assistant_decision_required": True,
            "primary_directive": "INVESTIGAR_STRATEGIC_ADVISOR",
            "strategic_label": "ERRO",
            "ceo_confidence_score": 0,
            "ceo_confidence_label": "ERRO",
            "expansion_blocked": True,
            "recommendations": [{
                "priority": "P0",
                "category": "SYSTEM",
                "title": "Strategic Advisor indisponível",
                "rationale": str(exc),
                "action": "Verificar import, deploy e logs do strategic_advisor.py.",
                "technical_commands": ["/strategy", "/ceoconfidence", "/alertscheck"],
                "human_decision_required": False,
                "assistant_decision_required": True,
                "blocks_expansion": True,
            }],
            "top_recommendation": None,
            "strengths": [],
            "risks": [str(exc)],
            "next_technical_commands": ["/strategy", "/ceoconfidence", "/alertscheck"],
            "operational_note": "Erro ao gerar Strategic Advisor.",
        }


def _strategic_advisor_report_block(monthly_stats=None, compact=False):
    try:
        payload = _strategic_advisor_snapshot_for_reports(monthly_stats=monthly_stats)
        return build_strategic_advisor_text(payload, compact=compact)
    except Exception as exc:
        return (
            "🧭 STRATEGIC ADVISOR — CENTRAL QUANT V1\n"
            f"Data/hora: {data_hora_sp_str()}\n\n"
            "Status: ERRO\n"
            f"Erro ao gerar Strategic Advisor: {exc}"
        )




def _decision_pack_snapshot_for_reports(monthly_stats=None, ceo_confidence=None, strategic_advisor=None, compact_source=False):
    """
    Consolida o Decision Pack V1 para uso técnico do assistente.
    Não executa ordens, não altera risco, não envia Telegram e não muda cooldowns.
    """
    try:
        executive_alerts = _executive_alerts_snapshot_for_reports(check_only=True)
    except Exception:
        executive_alerts = {}

    try:
        pipeline = build_execution_pipeline_status()
    except Exception:
        pipeline = {}

    try:
        exposure = central_exposure_snapshot()
    except Exception:
        exposure = {}

    try:
        memory = memory_snapshot("decision_pack_memory", store=True)
    except Exception:
        memory = {}

    try:
        confidence_payload = ceo_confidence or _ceo_confidence_snapshot_for_reports(monthly_stats=monthly_stats)
    except Exception:
        confidence_payload = {}

    try:
        strategy_payload = strategic_advisor or _strategic_advisor_snapshot_for_reports(
            monthly_stats=monthly_stats,
            ceo_confidence=confidence_payload,
            compact_source=compact_source,
        )
    except Exception:
        strategy_payload = {}

    try:
        adaptive_payload = get_adaptive_weights()
    except Exception:
        adaptive_payload = {}

    try:
        outcome_payload = get_outcome_stats()
    except Exception:
        outcome_payload = {}

    try:
        return build_decision_pack(
            ceo_confidence=confidence_payload,
            strategic_advisor=strategy_payload,
            executive_alerts=executive_alerts,
            pipeline=pipeline,
            exposure=exposure,
            memory=memory,
            adaptive=adaptive_payload,
            outcome=outcome_payload,
            monthly_stats=monthly_stats or {},
        )
    except Exception as exc:
        return {
            "ok": False,
            "version": "DECISION-PACK-ERROR",
            "generated_at": data_hora_sp_str(),
            "directive": "INVESTIGAR_DECISION_PACK",
            "classification": "ERRO",
            "priority": "P0",
            "expansion_allowed": False,
            "human_decision_required": False,
            "assistant_decision_required": True,
            "next_action_for_assistant": f"Corrigir Decision Pack: {exc}",
            "ceo_confidence": {"score": 0, "label": "ERRO"},
            "risk": {},
            "learning": {},
            "pipeline": {},
            "executive_alerts": {},
            "technical_commands": ["/decisionpack", "/strategy", "/ceoconfidence", "/alertscheck"],
            "errors": [str(exc)],
        }


def _decision_pack_report_block(monthly_stats=None, compact=False):
    try:
        payload = _decision_pack_snapshot_for_reports(monthly_stats=monthly_stats, compact_source=compact)
        return build_decision_pack_text(payload, compact=compact)
    except Exception as exc:
        return (
            "🧩 DECISION PACK — CENTRAL QUANT V1\n"
            f"Data/hora: {data_hora_sp_str()}\n\n"
            "Status: ERRO\n"
            f"Erro ao gerar Decision Pack: {exc}\n\n"
            "Ação prática: verificar decision_pack.py e imports do main.py."
        )




# ==========================================================
# EXECUTIVE DECISION ENGINE — INTEGRAÇÃO COM REPORTS
# ==========================================================

def _executive_decision_snapshot_for_reports(monthly_stats=None, compact_source=False):
    """
    Consolida o Executive Decision Engine V1.
    V1 decide política operacional, mas não executa bloqueios sozinho.
    """
    try:
        ceo_payload = _ceo_confidence_snapshot_for_reports(monthly_stats=monthly_stats)
    except Exception:
        ceo_payload = {}

    try:
        strategy_payload = _strategic_advisor_snapshot_for_reports(
            monthly_stats=monthly_stats,
            ceo_confidence=ceo_payload,
            compact_source=compact_source,
        )
    except Exception:
        strategy_payload = {}

    try:
        decision_pack_payload = _decision_pack_snapshot_for_reports(
            monthly_stats=monthly_stats,
            ceo_confidence=ceo_payload,
            strategic_advisor=strategy_payload,
            compact_source=compact_source,
        )
    except Exception:
        decision_pack_payload = {}

    try:
        executive_alerts = _executive_alerts_snapshot_for_reports(check_only=True)
    except Exception:
        executive_alerts = {}

    try:
        pipeline = build_execution_pipeline_status()
    except Exception:
        pipeline = {}

    try:
        exposure = central_exposure_snapshot()
    except Exception:
        exposure = {}

    try:
        memory = memory_snapshot("executive_decision_memory", store=True)
    except Exception:
        memory = {}

    try:
        adaptive = get_adaptive_weights()
    except Exception:
        adaptive = {}

    try:
        executive_decision_payload = build_executive_decision(
            decision_pack=decision_pack_payload,
            strategic_advisor=strategy_payload,
            ceo_confidence=ceo_payload,
            executive_alerts=executive_alerts,
            pipeline=pipeline,
            exposure=exposure,
            memory=memory,
            adaptive=adaptive,
            monthly_stats=monthly_stats or {},
        )

        executive_decision_payload["executive_policy_manager"] = _sync_executive_policy_manager_from_decision(
            executive_decision_payload
        )

        return executive_decision_payload
    except Exception as exc:
        return {
            "ok": False,
            "version": "EXECUTIVE-DECISION-ERROR",
            "generated_at": data_hora_sp_str(),
            "mode": "EXECUTIVE_DECISION_ENGINE",
            "human_decision_required": False,
            "assistant_decision_required": True,
            "primary_decision": "INVESTIGAR_EXECUTIVE_DECISION_ENGINE",
            "primary_directive": {
                "level": "P0",
                "category": "SYSTEM",
                "title": "Executive Decision Engine indisponível",
                "action": "Verificar import, deploy e logs do executive_decision_engine.py.",
                "rationale": str(exc),
            },
            "policy": {"allow_expansion": False, "allow_new_entries": False},
            "expansion_blocked": True,
            "assistant_action": f"Corrigir Executive Decision Engine: {exc}",
            "ceo_confidence": {"score": 0, "label": "ERRO"},
            "risk": {},
            "pipeline": {},
            "learning": {},
            "directives": [],
            "technical_commands": ["/executivedecision", "/decisionpack", "/strategy", "/ceoconfidence"],
            "errors": [str(exc)],
        }



def _sync_executive_policy_manager_from_decision(executive_decision_payload):
    """
    Integra o Executive Decision Engine ao Executive Policy Manager.

    Toda vez que o Executive Decision Engine gera diretivas executivas,
    elas passam a ser persistidas como políticas oficiais da Central Quant.

    V1 é conservador:
    - não executa ordens;
    - não limpa políticas manualmente criadas;
    - apenas cria/atualiza políticas presentes em directives/policies.
    """
    try:
        if not EXECUTIVE_POLICY_MANAGER_LOADED or executive_policy_manager is None:
            return {
                "ok": False,
                "loaded": False,
                "error": EXECUTIVE_POLICY_MANAGER_ERROR,
                "ingested": 0,
            }

        if not isinstance(executive_decision_payload, dict):
            return {
                "ok": False,
                "loaded": True,
                "error": "executive_decision_payload_not_dict",
                "ingested": 0,
            }

        result = executive_policy_manager.ingest_executive_directives(executive_decision_payload)

        try:
            active_codes = [p.get("code") for p in result.get("active_policies", []) if isinstance(p, dict)]
        except Exception:
            active_codes = []

        return {
            "ok": bool(result.get("ok")),
            "loaded": True,
            "ingested": int(result.get("ingested", 0) or 0),
            "active_codes": active_codes,
            "version": result.get("version"),
            "generated_at": result.get("generated_at"),
        }
    except Exception as exc:
        return {
            "ok": False,
            "loaded": EXECUTIVE_POLICY_MANAGER_LOADED,
            "error": str(exc),
            "ingested": 0,
        }

def _executive_decision_report_block(monthly_stats=None, compact=False):
    try:
        payload = _executive_decision_snapshot_for_reports(monthly_stats=monthly_stats, compact_source=compact)
        return build_executive_decision_text(payload, compact=compact)
    except Exception as exc:
        return (
            "⚖️ EXECUTIVE DECISION ENGINE — CENTRAL QUANT V1\n"
            f"Data/hora: {data_hora_sp_str()}\n\n"
            "Status: ERRO\n"
            f"Erro ao gerar Executive Decision Engine: {exc}\n\n"
            "Ação prática: verificar executive_decision_engine.py e imports do main.py."
        )


def _executive_policy_auto_release_report_block():
    """Executa Auto Release e devolve relatório em texto para Telegram/HTTP."""
    try:
        result = run_executive_policy_auto_release(context={})
        return build_executive_policy_auto_release_report(result)
    except Exception as exc:
        return (
            "🔓 EXECUTIVE POLICY AUTO RELEASE — CENTRAL QUANT\n"
            f"Data/hora: {data_hora_sp_str()}\n\n"
            "Status: ERRO\n"
            f"Erro ao executar Auto Release: {exc}\n\n"
            "Ação prática: verificar executive_policy_auto_release.py e o import no main.py."
        )


def _executive_policy_auto_release_health_text():
    """Health em texto para comando Telegram. Não executa release."""
    try:
        health = get_executive_policy_auto_release_health()
    except Exception as exc:
        health = {"ok": False, "loaded": False, "error": str(exc)}
    return (
        "🔓 POLICY AUTO RELEASE HEALTH — CENTRAL QUANT\n"
        f"Data/hora: {data_hora_sp_str()}\n"
        f"OK: {health.get('ok')}\n"
        f"Carregado: {health.get('loaded')}\n"
        f"Policies ativas: {health.get('active_policy_count')}\n"
        f"Códigos ativos: {health.get('active_codes')}\n"
        f"Última rodada: {health.get('last_run_at')}\n"
        f"Erro: {health.get('error')}"
    )


def _executive_alert_monthly_stats(start_dt, end_dt):
    """
    Consolida a saúde executiva do mês com base no log do Executive Alert Manager.
    Não dispara novos alertas; apenas lê histórico persistido.
    """
    rows = _executive_alert_rows_for_period(start_dt, end_dt)
    days_in_period = max(1, (end_dt.date() - start_dt.date()).days)

    scores = []
    alerts_total = 0
    to_notify_total = 0
    resolved_total = 0
    critical_total = 0
    warning_total = 0
    recovery_total = 0
    by_category = {}
    by_level = {}
    by_day = {}
    timeline = []

    for row in rows:
        score = _executive_alert_health_score_from_row(row)
        if score is not None:
            scores.append(score)

        day_key = _executive_alert_day_key(row)
        by_day.setdefault(day_key, {"checks": 0, "critical": 0, "warning": 0, "alerts": 0, "resolved": 0, "min_score": None})
        by_day[day_key]["checks"] += 1
        if score is not None:
            current = by_day[day_key].get("min_score")
            by_day[day_key]["min_score"] = score if current is None else min(current, score)

        alerts = row.get("alerts") or []
        if not isinstance(alerts, list):
            alerts = []
        resolved = row.get("resolved") or []
        if not isinstance(resolved, list):
            resolved = []
        to_notify = row.get("alerts_to_notify") or []
        if not isinstance(to_notify, list):
            to_notify = []

        alerts_total += len(alerts)
        to_notify_total += len(to_notify)
        resolved_total += len(resolved)
        recovery_total += len(resolved)
        by_day[day_key]["alerts"] += len(alerts)
        by_day[day_key]["resolved"] += len(resolved)

        for alert in alerts:
            if not isinstance(alert, dict):
                continue
            level = str(alert.get("level") or "UNKNOWN").upper()
            category = str(alert.get("category") or "UNKNOWN").upper()
            by_level[level] = by_level.get(level, 0) + 1
            by_category[category] = by_category.get(category, 0) + 1
            if level == "CRITICAL":
                critical_total += 1
                by_day[day_key]["critical"] += 1
            elif level == "WARNING":
                warning_total += 1
                by_day[day_key]["warning"] += 1
            title = alert.get("title") or alert.get("code") or "Alerta executivo"
            generated = row.get("generated_at") or alert.get("generated_at") or day_key
            timeline.append({"generated_at": generated, "level": level, "category": category, "title": str(title)})

        for rec in resolved:
            if not isinstance(rec, dict):
                continue
            generated = row.get("generated_at") or rec.get("generated_at") or day_key
            resolved_alert = rec.get("resolved_alert") or {}
            title = resolved_alert.get("title") or rec.get("title") or "Alerta resolvido"
            category = resolved_alert.get("category") or rec.get("category") or "RECOVERY"
            timeline.append({"generated_at": generated, "level": "RECOVERY", "category": str(category).upper(), "title": str(title)})

    days_with_critical = len([d for d, v in by_day.items() if d != "N/A" and v.get("critical", 0) > 0])
    days_with_warning = len([d for d, v in by_day.items() if d != "N/A" and v.get("warning", 0) > 0 and v.get("critical", 0) == 0])
    days_with_any_alert = len([d for d, v in by_day.items() if d != "N/A" and v.get("alerts", 0) > 0])
    healthy_days_observed = len([d for d, v in by_day.items() if d != "N/A" and v.get("alerts", 0) == 0 and (v.get("min_score") or 100) >= 90])

    # Melhor sequência saudável observada nos dias com algum check no log.
    streak = 0
    best_streak = 0
    try:
        cur = start_dt.date()
        while cur < end_dt.date():
            key = cur.strftime("%Y-%m-%d")
            item = by_day.get(key)
            is_healthy = bool(item and item.get("alerts", 0) == 0 and (item.get("min_score") or 100) >= 90)
            if is_healthy:
                streak += 1
                best_streak = max(best_streak, streak)
            else:
                streak = 0
            cur += timedelta(days=1)
    except Exception:
        best_streak = healthy_days_observed

    avg_score = round(sum(scores) / max(len(scores), 1), 2) if scores else None
    min_score = round(min(scores), 2) if scores else None
    latest_snapshot = _executive_alerts_snapshot_for_reports(check_only=True)

    timeline = sorted(timeline, key=lambda x: str(x.get("generated_at") or ""))[-12:]
    by_category = dict(sorted(by_category.items(), key=lambda x: (-x[1], x[0])))
    by_level = dict(sorted(by_level.items(), key=lambda x: (-x[1], x[0])))

    return {
        "ok": True,
        "rows": rows,
        "checks": len(rows),
        "days_in_period": days_in_period,
        "days_observed": len([d for d in by_day.keys() if d != "N/A"]),
        "avg_score": avg_score,
        "min_score": min_score,
        "alerts_total": alerts_total,
        "alerts_to_notify_total": to_notify_total,
        "resolved_total": resolved_total,
        "recovery_total": recovery_total,
        "critical_total": critical_total,
        "warning_total": warning_total,
        "days_with_critical": days_with_critical,
        "days_with_warning": days_with_warning,
        "days_with_any_alert": days_with_any_alert,
        "healthy_days_observed": healthy_days_observed,
        "best_healthy_streak": best_streak,
        "by_category": by_category,
        "by_level": by_level,
        "timeline": timeline,
        "latest_snapshot": latest_snapshot,
        "log_file": str(_executive_alert_log_file_path()),
    }


def _executive_monthly_health_block(start_dt, end_dt):
    stats = _executive_alert_monthly_stats(start_dt, end_dt)
    latest = stats.get("latest_snapshot") or {}
    latest_hs = latest.get("health_score") or {}

    avg_score = stats.get("avg_score")
    min_score = stats.get("min_score")
    avg_txt = f"{avg_score}/100" if avg_score is not None else "sem amostra mensal"
    min_txt = f"{min_score}/100" if min_score is not None else "sem amostra mensal"

    lines = [
        "🚨 EXECUTIVE HEALTH DO MÊS",
        "",
        f"Checks registrados: {stats.get('checks', 0)}",
        f"Dias observados: {stats.get('days_observed', 0)}/{stats.get('days_in_period', 0)}",
        f"Health Score médio: {avg_txt}",
        f"Menor Health Score: {min_txt}",
        f"Status atual: {latest.get('status', 'UNKNOWN')}",
        f"Health atual: {latest_hs.get('score', 0)}/100 — {latest_hs.get('label', 'N/A')}",
        "",
        "Alertas:",
        f"- CRITICAL: {stats.get('critical_total', 0)}",
        f"- WARNING: {stats.get('warning_total', 0)}",
        f"- Para notificar: {stats.get('alerts_to_notify_total', 0)}",
        f"- Recoveries: {stats.get('recovery_total', 0)}",
        "",
        "Dias:",
        f"- Dias sem alertas observados: {stats.get('healthy_days_observed', 0)}",
        f"- Dias com WARNING: {stats.get('days_with_warning', 0)}",
        f"- Dias com CRITICAL: {stats.get('days_with_critical', 0)}",
        f"- Melhor sequência saudável observada: {stats.get('best_healthy_streak', 0)} dia(s)",
        "",
        "Categorias mais frequentes:",
    ]

    by_category = stats.get("by_category") or {}
    if by_category:
        for category, count in list(by_category.items())[:8]:
            lines.append(f"- {category}: {count}")
    else:
        lines.append("- Nenhuma categoria de alerta registrada no mês.")

    timeline = stats.get("timeline") or []
    lines += ["", "Executive timeline:"]
    if timeline:
        for item in timeline[-10:]:
            lines.append(f"- {item.get('generated_at')} | {item.get('level')} | {item.get('category')} | {item.get('title')}")
    else:
        lines.append("- Nenhum alerta/recovery registrado no período.")

    lines += ["", "Leitura executiva:"]
    if stats.get("checks", 0) == 0:
        lines.append("- Ainda não há histórico mensal suficiente do Executive Alert Manager. A partir deste deploy, o log mensal passará a alimentar esta seção.")
    elif stats.get("critical_total", 0) > 0:
        lines.append("- O mês teve alerta crítico. Revisar a timeline e a categoria dominante antes de aumentar risco operacional.")
    elif stats.get("warning_total", 0) > 0:
        lines.append("- O mês teve warnings, mas sem incidente crítico. Manter observação e acompanhar recorrência por categoria.")
    else:
        lines.append("- A Central permaneceu saudável nos checks observados. Nenhuma interrupção executiva relevante foi registrada.")

    return "\n".join(lines)


def build_executive_report_monthly():
    """Relatório mensal consolidando o mês anterior com Executive Monthly Report V2."""
    start_dt, end_dt, month_key, month_label = _month_bounds_previous()
    events = _history_events_for_period(start_dt, end_dt, limit=30000)

    by_event = {}
    blocked_by_reason = {}
    closed = []
    for event in events:
        et = str(event.get("event") or "EVENT").upper()
        by_event[et] = by_event.get(et, 0) + 1
        if et == "TRADE_CLOSED":
            closed.append(event)
        if et == "TRADE_BLOCKED" or str(event.get("result") or "").upper() in {"DENY", "DENIED", "BLOCKED"}:
            reason = str(event.get("reason") or event.get("result") or "N/A")
            blocked_by_reason[reason] = blocked_by_reason.get(reason, 0) + 1

    perf = _stats_from_closed_events(closed)
    monthly_stats_for_confidence = dict(perf) if isinstance(perf, dict) else {}
    monthly_stats_for_confidence["events_total"] = len(events)
    by_bot = _monthly_group_stats(closed, "bot")
    by_symbol = _monthly_group_stats(closed, "symbol")
    by_setup = _monthly_group_stats(closed, "setup")

    try:
        pipeline = build_execution_pipeline_status()
    except Exception:
        pipeline = {}
    adaptive = pipeline.get("adaptive") or {}
    positions = pipeline.get("positions") or {}

    lines = [
        "📆 EXECUTIVE REPORT MENSAL — CENTRAL QUANT V2",
        f"Mês consolidado: {month_label}",
        f"Período: {start_dt.strftime('%d/%m/%Y %H:%M')} até {(end_dt - timedelta(seconds=1)).strftime('%d/%m/%Y %H:%M')}",
        f"Gerado em: {data_hora_sp_str()}",
        "",
        "==============================\nEXECUTIVE HEALTH DO MÊS\n==============================",
        _executive_monthly_health_block(start_dt, end_dt),
        "",
        "==============================\nCEO CONFIDENCE INDEX\n==============================",
        _ceo_confidence_report_block(monthly_stats=monthly_stats_for_confidence),
        "",
        "==============================\nSTRATEGIC ADVISOR\n==============================",
        _strategic_advisor_report_block(monthly_stats=monthly_stats_for_confidence, compact=False),
        "",
        "==============================\nDECISION PACK\n==============================",
        _decision_pack_report_block(monthly_stats=monthly_stats_for_confidence, compact=True),
        "",
        "==============================\nEXECUTIVE DECISION ENGINE\n==============================",
        _executive_decision_report_block(monthly_stats=monthly_stats_for_confidence, compact=True),
        "",
        "==============================\nPERFORMANCE DO MÊS\n==============================",
        f"Trades encerrados: {perf.get('trades', 0)} | Wins: {perf.get('wins', 0)} | Losses: {perf.get('losses', 0)} | BE: {perf.get('be', 0)}",
        f"Win rate: {perf.get('win_rate_pct', 0)}% | PnL total: {perf.get('pnl_total_pct', 0)}% | PnL médio: {perf.get('pnl_avg_pct', 0)}%",
        f"Profit Factor: {perf.get('profit_factor_pct', 0)} | R total: {perf.get('r_total', 0)}R | R médio: {perf.get('r_avg', 0)}R",
        "",
        "==============================\nPIPELINE E APRENDIZADO ATUAIS\n==============================",
        f"Pipeline atual: {pipeline.get('status', 'UNKNOWN')}",
        f"PAPER abertas: {positions.get('open', 0)} | PAPER fechadas: {positions.get('closed', 0)} | Outcomes pendentes: {positions.get('pending_outcome', 0)}",
        f"Adaptive action: {adaptive.get('recommended_action', 'N/A')} | Weight: {adaptive.get('suggested_weight', 'N/A')} | Confidence: {safe_round(adaptive.get('confidence'), 1, 0)}%",
        f"Trades no Adaptive: {adaptive.get('trades', 0)}",
        "",
        "==============================\nEVENTOS DO MÊS\n==============================",
    ]
    lines += _counter_top_lines("Eventos:", dict(sorted(by_event.items(), key=lambda x: x[1], reverse=True)), limit=12, empty="sem eventos no mês")

    lines += ["", "==============================\nROBÔS\n==============================", "Ranking por PnL:"]
    if by_bot:
        for bot, s in list(by_bot.items())[:10]:
            lines.append(f"- {bot}: {s.get('trades')} trades | WR {s.get('win_rate_pct')}% | PnL {s.get('pnl_total_pct')}% | PF {s.get('profit_factor_pct')}")
    else:
        lines.append("- Sem trades encerrados no mês.")

    lines += ["", "==============================\nATIVOS\n==============================", "Top ativos por PnL:"]
    if by_symbol:
        for sym, s in list(by_symbol.items())[:10]:
            lines.append(f"- {sym}: {s.get('trades')} trades | WR {s.get('win_rate_pct')}% | PnL {s.get('pnl_total_pct')}%")
    else:
        lines.append("- Sem ativos com trades encerrados no mês.")

    lines += ["", "==============================\nSETUPS\n==============================", "Top setups por PnL:"]
    if by_setup:
        for setup, s in list(by_setup.items())[:10]:
            lines.append(f"- {setup}: {s.get('trades')} trades | WR {s.get('win_rate_pct')}% | PnL {s.get('pnl_total_pct')}%")
    else:
        lines.append("- Sem setups com trades encerrados no mês.")

    lines += ["", "==============================\nBLOQUEIOS\n=============================="]
    lines += _counter_top_lines("Motivos:", dict(sorted(blocked_by_reason.items(), key=lambda x: x[1], reverse=True)), limit=10, empty="sem bloqueios no mês")

    lines += [
        "",
        "==============================\nSTATUS ATUAL PÓS-FECHAMENTO\n==============================",
        build_executive_report(),
        "",
        "==============================\nRECOMENDAÇÃO EXECUTIVA\n==============================",
    ]
    if perf.get("trades", 0) <= 0:
        lines.append("- Ainda não há trades encerrados suficientes no Super History para avaliação mensal estatística.")
    else:
        if perf.get("profit_factor_pct", 0) < 1:
            lines.append("- Mês com Profit Factor abaixo de 1: revisar robôs/setups negativos antes de aumentar risco.")
        elif perf.get("profit_factor_pct", 0) >= 1.5 and perf.get("pnl_total_pct", 0) > 0:
            lines.append("- Mês positivo: considerar aumento gradual apenas nos robôs com amostra e expectativa positiva.")
        else:
            lines.append("- Manter risco controlado e aprofundar análise por robô antes de mudanças estruturais.")

    try:
        health_stats = _executive_alert_monthly_stats(start_dt, end_dt)
        if health_stats.get("critical_total", 0) > 0:
            lines.append("- Como houve alerta crítico no mês, priorizar estabilidade operacional antes de aumentar automação ou lote.")
        elif health_stats.get("warning_total", 0) > 0:
            lines.append("- Como houve warnings no mês, acompanhar recorrência antes de subir exposição.")
        elif health_stats.get("checks", 0) > 0:
            lines.append("- Saúde executiva do mês foi estável nos checks observados.")
    except Exception:
        pass

    text = "\n".join(lines)
    force_gc_if_needed("executive_report_monthly_v2_end", force=True)
    return text

def _read_jsonl_tail_v3(path, limit=200):
    try:
        p = Path(path)
        if not p.exists():
            return []
        lines = p.read_text(encoding="utf-8").splitlines()[-int(limit):]
        out = []
        for line in lines:
            try:
                out.append(json.loads(line))
            except Exception:
                pass
        return out
    except Exception:
        return []


def build_evolution_dashboard_v3():
    """
    Dashboard de evolução V3.0 baseado nos logs locais disponíveis.
    Para histórico 7/30 dias permanente, o ideal é persistir em Redis/Upstash.
    """
    decision_log = _read_jsonl_tail_v3(CENTRAL_DECISION_LOG_FILE, 300)
    timeline_log = _read_jsonl_tail_v3(CENTRAL_TIMELINE_LOG_FILE, 500)

    decisions_total = len(decision_log)
    allow = sum(1 for x in decision_log if str(x.get("decision", x.get("status", ""))).upper() == "ALLOW")
    deny = sum(1 for x in decision_log if str(x.get("decision", x.get("status", ""))).upper() == "DENY")
    verify = sum(1 for x in decision_log if str(x.get("execution_mode", x.get("mode", ""))).upper() == "VERIFY")
    live = sum(1 for x in decision_log if str(x.get("execution_mode", x.get("mode", ""))).upper() == "LIVE")

    by_bot = {}
    for item in decision_log:
        bot = str(item.get("bot") or item.get("robot") or "").upper() or "N/A"
        by_bot.setdefault(bot, {"total": 0, "allow": 0, "deny": 0})
        by_bot[bot]["total"] += 1
        dec = str(item.get("decision", item.get("status", ""))).upper()
        if dec == "ALLOW":
            by_bot[bot]["allow"] += 1
        elif dec == "DENY":
            by_bot[bot]["deny"] += 1

    lines = [
        "📈 DASHBOARD DE EVOLUÇÃO — CENTRAL QUANT V3.1",
        f"Data/hora: {data_hora_sp_str()}",
        "",
        "Decisões registradas:",
        str(decisions_total),
        f"ALLOW: {allow} | DENY: {deny}",
        f"VERIFY: {verify} | LIVE: {live}",
        "",
        "Eventos de timeline:",
        str(len(timeline_log)),
    ]

    if by_bot:
        lines += ["", "Por robô:"]
        for bot, stats in sorted(by_bot.items(), key=lambda x: x[1]["total"], reverse=True):
            lines.append(f"- {bot}: total={stats['total']} | allow={stats['allow']} | deny={stats['deny']}")

    lines += [
        "",
        "Observação:",
        "Para evolução histórica real de 7/30 dias, sem perder dados em deploy/restart,",
        "o próximo passo é persistir métricas em Redis/Upstash ou banco externo.",
    ]
    return "\n".join(lines)


def build_support_report():
    """
    Pacote de troubleshooting: não foca no desempenho, foca em saúde técnica.
    """
    parts = [
        "🛠️ SUPORTE CENTRAL QUANT",
        f"Data/hora: {data_hora_sp_str()}",
        "",
        "==============================\nDIAGNÓSTICO\n==============================",
        build_diagnostic_report(),
        "",
        "==============================\nSELFTEST\n==============================",
        build_selftest_report(),
        "",
        "==============================\nMEMÓRIA\n==============================",
        build_memory_text(run_gc=False)[0],
        "",
        "==============================\nHISTORY\n==============================",
        __import__("history_manager").build_history_report(),
        "",
        "==============================\nHEALTH DOS BOTS\n==============================",
    ]
    for key in BOT_CONFIGS.keys():
        parts.append(_bot_report_health_text(key))
    return "\n\n==============================\n".join(parts)


def build_audit_parts():
    """Retorna seções independentes para envio em partes pelo Telegram."""
    parts = [
        ("AUDITORIA — CENTRAL", "🔍 AUDITORIA CENTRAL QUANT\n" + f"Data/hora: {data_hora_sp_str()}"),
        ("DASHBOARD", build_dashboard_report()),
        ("RANKING", build_ranking_report()),
        ("HISTORY", __import__("history_manager").build_history_report()),
        ("RISK", build_risk_report()),
        ("HEAT", build_heatmap_report()),
        ("EXPOSIÇÃO", _brief_exposure_text()),
    ]
    for key in BOT_CONFIGS.keys():
        try:
            bot_text = build_single_bot_report(key, complete=True)
        except Exception as exc:
            bot_text = f"⚠️ Erro ao gerar relatório completo de {key}: {exc}"
        parts.append((f"BOT {key}", bot_text))
    return parts


def build_audit_report():
    """
    Auditoria técnica completa. Para HTTP devolve texto único; no Telegram
    o roteador usa build_audit_parts() para enviar em partes.
    """
    return "\n\n==============================\n".join(
        [f"==============================\n{title}\n==============================\n{text}" for title, text in build_audit_parts()]
    )


def build_full_parts():
    """Modo nuclear em partes: snapshot + auditoria + relatório nativo."""
    parts = [
        ("FULL — SNAPSHOT", build_snapshot_report()),
    ]
    parts.extend(build_audit_parts())
    try:
        native_report = build_central_report("completo")
    except Exception as exc:
        native_report = f"⚠️ Erro ao gerar relatório completo nativo: {exc}"
    parts.append(("RELATÓRIO COMPLETO NATIVO", native_report))
    return parts


def build_full_report():
    """
    Modo nuclear: salva snapshot e despeja praticamente tudo.
    Para Telegram, é enviado em partes por build_full_parts().
    """
    return "\n\n==============================\n".join(
        [f"==============================\n{title}\n==============================\n{text}" for title, text in build_full_parts()]
    )


@app.route("/executive")
def executive_route():
    return {"text": build_executive_report()}


@app.route("/ceodaily")
def ceo_daily_route():
    return {"text": build_ceo_daily_report()}


@app.route("/ceoconfidence")
@app.route("/ceo_confidence")
@app.route("/confidence")
def ceo_confidence_route():
    payload = _ceo_confidence_snapshot_for_reports()
    return {"text": build_ceo_confidence_text(payload), "payload": payload}


@app.route("/strategicadvisor")
@app.route("/strategic_advisor")
@app.route("/strategy")
@app.route("/estrategia")
@app.route("/estratégia")
def strategic_advisor_route():
    compact = str(request.args.get("compact", "false")).strip().lower() in {"1", "true", "yes", "sim", "on"}
    payload = _strategic_advisor_snapshot_for_reports()
    return {"text": build_strategic_advisor_text(payload, compact=compact), "payload": payload}


@app.route("/decisionpack")
@app.route("/decision_pack")
@app.route("/decision")
@app.route("/decisao")
@app.route("/decisão")
def decision_pack_route():
    compact = str(request.args.get("compact", "false")).strip().lower() in {"1", "true", "yes", "sim", "on"}
    payload = _decision_pack_snapshot_for_reports()
    return {"text": build_decision_pack_text(payload, compact=compact), "payload": payload}


@app.route("/executivedecision")
@app.route("/executive_decision")
@app.route("/decisionengine")
@app.route("/decision_engine")
@app.route("/policy")
@app.route("/politica")
@app.route("/política")
def executive_decision_route():
    compact = str(request.args.get("compact", "false")).strip().lower() in {"1", "true", "yes", "sim", "on"}
    payload = _executive_decision_snapshot_for_reports()
    return {"text": build_executive_decision_text(payload, compact=compact), "payload": payload}


@app.route("/policyautorelease/report")
@app.route("/policy_auto_release")
def policy_auto_release_report_route():
    return {"text": _executive_policy_auto_release_report_block()}



@app.route("/policypriority/report")
@app.route("/policy_priority")
def policy_priority_report_route():
    result = resolve_executive_policy_priority(trade_payload=None, commit=True)
    return {"text": build_executive_policy_priority_report(result), "payload": result}


@app.route("/dashboard")
def dashboard_route():
    return {"text": build_dashboard_report()}


@app.route("/daily")
@app.route("/diario")
@app.route("/diário")
def daily_route():
    return {"text": build_daily_report()}


@app.route("/executivereport")
@app.route("/executive_report")
@app.route("/dailyexecutive")
@app.route("/daily_executive")
def executive_report_daily_route():
    return {"text": build_ceo_daily_report()}


@app.route("/monthly")
@app.route("/mensal")
@app.route("/monthlyreport")
@app.route("/monthly_report")
def executive_report_monthly_route():
    return {"text": build_executive_report_monthly()}


@app.route("/evolution")
@app.route("/evolucao")
@app.route("/evolução")
def evolution_route():
    return {"text": build_evolution_dashboard_v3()}


@app.route("/support")
def support_route():
    return {"text": build_support_report()}


@app.route("/menu")
@app.route("/comandos")
@app.route("/start")
def menu_route():
    return {"text": build_central_menu_text()}


@app.route("/comandosfull")
@app.route("/commandsfull")
def commands_full_route():
    return {"text": build_central_help_text()}


@app.route("/audit")
@app.route("/auditoria2")
def audit_route():
    return {"text": build_audit_report()}


@app.route("/full")
def full_route():
    return {"text": build_full_report()}


@app.route("/relatoriocompleto")
@app.route("/relatorio_completo")
def relatorio_completo_sem_espaco_route():
    return {"text": build_audit_report()}




@app.route("/execution")
@app.route("/execucao")
@app.route("/execução")
@app.route("/bingx")
def execution_route():
    return {"text": build_execution_report(), "payload": broker_status_payload(), "ready": bingx_ready_payload()}


@app.route("/live")
@app.route("/livestatus")
def live_route():
    return {"text": build_live_report()}


@app.route("/sync")
@app.route("/reconcile")
def sync_route():
    return {"text": build_sync_report()}


@app.route("/bingx/divergence")
@app.route("/bingxdivergence")
@app.route("/divergence")
def bingx_divergence_route():
    return bingx_divergence_payload()


@app.route("/executions")
@app.route("/exec_log")
@app.route("/executionlog")
def executions_route():
    return {"text": build_executions_log_report()}



@app.route("/decisionlog")
@app.route("/decisions")
def decisionlog_route():
    arg = request.args.get("q") or request.args.get("symbol") or request.args.get("bot")
    return {"text": build_decision_log_report(arg)}


@app.route("/decisionlograw")
@app.route("/decisionlog/raw")
def decisionlog_raw_route():
    """
    V2.1.7 — diagnóstico bruto do decision_log.
    Mostra as últimas linhas com policy_codes/policy_linker para validar persistência.
    """
    try:
        limit = int(request.args.get("limit", "5"))
    except Exception:
        limit = 5
    limit = max(1, min(limit, 50))
    items = decision_log_items(limit=limit)
    return {
        "ok": True,
        "version": "2026-07-05-MAIN-POLICY-LINK-PERSISTENCE-V2.1.7",
        "decision_log_file": str(CENTRAL_DECISION_LOG_FILE),
        "items": items,
    }


@app.route("/timeline")
@app.route("/timeline/<arg>")
def timeline_route(arg=None):
    arg = arg or request.args.get("q") or request.args.get("symbol") or request.args.get("bot")
    return {"text": build_timeline_report(arg)}


@app.route("/executionstats")
@app.route("/execstats")
def executionstats_route():
    return {"text": build_execution_stats_report()}


@app.route("/consistency")
@app.route("/consistencia")
def consistency_route():
    return {"text": build_consistency_report()}


@app.route("/brokerhealth")
@app.route("/brokerstats")
def brokerhealth_route():
    return {"text": build_broker_health_report()}


@app.route("/latency")
@app.route("/latencia")
def latency_route():
    return {"text": build_latency_report()}


@app.route("/livepositions")
def livepositions_route():
    return {"text": build_live_positions_report()}


@app.route("/verifyqueue")
def verifyqueue_route():
    return {"text": build_verify_queue_report()}


@app.route("/status")
def status_route():
    return {"text": build_status_report()}


@app.route("/systemdebug")
@app.route("/debug")
def system_debug_route():
    decision_main_file = str(CENTRAL_DECISION_LOG_FILE)

    history_decision_file = None
    history_loaded = False
    try:
        import history_manager as super_history_manager
        history_loaded = True
        history_decision_file = str(getattr(super_history_manager, "DECISION_LOG_FILE", None))
    except Exception:
        pass

    def count_jsonl(path):
        try:
            if not path or not os.path.exists(path):
                return 0
            with open(path, "r", encoding="utf-8") as f:
                return sum(1 for line in f if line.strip())
        except Exception:
            return None

    registry = central_trade_registry_snapshot(include_trades=False)

    return {
        "ok": True,
        "pid": os.getpid(),
        "cwd": os.getcwd(),
        "base_dir": str(globals().get("BASE_DIR", os.getcwd())),
        "central_data_dir": str(globals().get("CENTRAL_DATA_DIR", os.path.join(os.getcwd(), "data"))),
        "decision_log": {
            "main_file": decision_main_file,
            "main_count": count_jsonl(decision_main_file),
            "history_file": history_decision_file,
            "history_count": count_jsonl(history_decision_file),
        },
        "history_manager": {
            "loaded": history_loaded,
        },
        "trade_registry": {
            "ok": registry.get("ok"),
            "loaded": registry.get("loaded"),
            "open_count": registry.get("open_count"),
            "closed_count": registry.get("closed_count"),
            "file": registry.get("trade_registry_file"),
            "data_dir": registry.get("data_dir"),
        },
        "autosync": TRADE_REGISTRY_AUTOSYNC_STATUS,
        "memory": memory_snapshot("systemdebug", store=False),
    }


@app.route("/can_open_trade", methods=["GET", "POST"])
@app.route("/canopen", methods=["GET", "POST"])
def can_open_trade_route():
    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
    else:
        payload = dict(request.args)
    return can_open_trade_decision(payload)


@app.route("/auditrisk")
@app.route("/riskaudit")
def auditrisk_route():
    hours = request.args.get("hours") or request.args.get("h") or request.args.get("janela") or 2
    return {"text": build_audit_risk_report(hours)}


@app.route("/risk")
@app.route("/riskmanager")
def risk_route():
    return {"text": build_risk_report()}


@app.route("/risk/registry")
@app.route("/riskregistry")
def risk_registry_route():
    try:
        autosync_trade_registry(reason="risk_registry")
    except Exception as exc:
        print("AVISO SYNC REGISTRY ANTES DO RISK_REGISTRY:", exc)
    exposure = central_exposure_snapshot()
    registry = {
    "loaded": central_trade_registry is not None,
    "ok": True,
    "open_count": exposure.get("total_positions_open"),
    "by_bot": {k: v.get("total") for k, v in (exposure.get("by_bot") or {}).items()},
    "by_side": {
        "LONG": exposure.get("long_positions_open"),
        "SHORT": exposure.get("short_positions_open"),
    },
    "source": exposure.get("source"),
}

    return {
        "ok": True,
        "risk_source": exposure.get("source"),
        "registry_loaded": registry.get("loaded"),
        "registry_ok": registry.get("ok"),
        "positions": {
            "total": exposure.get("total_positions_open"),
            "long": exposure.get("long_positions_open"),
            "short": exposure.get("short_positions_open"),
        },
        "by_bot": exposure.get("by_bot"),
        "registry": registry,
    }


@app.route("/risk/registry/check")
@app.route("/riskregistry/check")
def risk_registry_check_route():
    try:
        autosync_trade_registry(reason="risk_registry_check")
    except Exception as exc:
        print("AVISO SYNC REGISTRY ANTES DO RISK_REGISTRY_CHECK:", exc)
    exposure = central_exposure_snapshot()
    registry = central_trade_registry_snapshot(include_trades=False)

    risk_total = int(exposure.get("total_positions_open") or 0)
    risk_long = int(exposure.get("long_positions_open") or 0)
    risk_short = int(exposure.get("short_positions_open") or 0)

    registry_total = int(registry.get("open_count") or 0)

    issues = []

    if exposure.get("source") != "trade_registry":
        issues.append(f"Risk source não é trade_registry: {exposure.get('source')}")

    if not registry.get("loaded"):
        issues.append("Trade Registry não carregado.")

    if not registry.get("ok"):
        issues.append("Trade Registry retornou ok=False.")

    if registry_total != risk_total:
        issues.append(f"Divergência open_count: registry={registry_total} risk={risk_total}")

    return {
        "ok": len(issues) == 0,
        "status": "OK" if len(issues) == 0 else "ALERTA",
        "issues": issues,
        "risk": {
            "source": exposure.get("source"),
            "total": risk_total,
            "long": risk_long,
            "short": risk_short,
        },
        "registry": {
            "loaded": registry.get("loaded"),
            "ok": registry.get("ok"),
            "open_count": registry_total,
            "updated_at": registry.get("updated_at"),
            "file": registry.get("trade_registry_file"),
        },
    }


@app.route("/heat")
@app.route("/heatmap")
def heat_route():
    return {"text": build_heatmap_report()}


@app.route("/ranking")
def ranking_route():
    return {"text": build_ranking_report()}


@app.route("/healthscore")
@app.route("/score")
def healthscore_route():
    return {"text": build_healthscore_report(), "payload": central_health_score_payload()}


@app.route("/meta")
@app.route("/metasupervisor")
def meta_route():
    return {"text": build_meta_supervisor_report()}


def build_history_stats_payload():
    """Retorna estatísticas agregadas do history manager sem quebrar a rota antiga /history."""
    try:
        import history_manager as super_history_manager
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

    try:
        return {
            "ok": True,
            "generated_at": super_history_manager.data_hora_sp_str(),
            "general": super_history_manager.calculate_stats(),
            "by_bot": super_history_manager.group_stats(group_by="bot"),
            "by_symbol": super_history_manager.group_stats(group_by="symbol"),
            "by_setup": super_history_manager.group_stats(group_by="setup"),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _analytics_group_response(group_by, label_key, list_key):
    try:
        import history_manager as super_history_manager
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

    try:
        days = request.args.get("days", default="", type=str)
        if days:
            query_result = super_history_manager.query_history(days=days, limit=None)
            events = query_result.get("events", [])
            grouped = super_history_manager.group_stats(group_by=group_by, events=events)
        else:
            grouped = super_history_manager.group_stats(group_by=group_by)

        items = []
        for name, stats in grouped.items():
            items.append({
                label_key: name,
                "total_events": stats.get("total_events", 0),
                "signals": stats.get("signals", 0),
                "entries": stats.get("entries", 0),
                "closed": stats.get("closed", 0),
                "wins": stats.get("wins", 0),
                "losses": stats.get("losses", 0),
                "breakeven": stats.get("breakeven", 0),
                "blocked": stats.get("blocked", 0),
                "denied": stats.get("denied", 0),
                "tp50": stats.get("tp50", 0),
                "pnl_total_pct": stats.get("pnl_total_pct", 0.0),
                "pnl_avg_pct": stats.get("pnl_avg_pct", 0.0),
                "win_rate_pct": round((stats.get("wins", 0) / stats.get("closed", 1)) * 100, 2) if stats.get("closed", 0) else 0.0,
            })

        items.sort(key=lambda item: (-item["pnl_total_pct"], -item["wins"], -item["total_events"], item[label_key]))

        return {
            "ok": True,
            "generated_at": super_history_manager.data_hora_sp_str(),
            "filters": {
                "days": days or None,
            },
            list_key: items,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@app.route("/analytics/bots")
def analytics_bots_route():
    return _analytics_group_response("bot", "bot", "bots")


@app.route("/analytics/ranking")
def analytics_ranking_route():
    try:
        import analytics_engine

        payload = analytics_engine.bot_ranking()

        lines = [
            "🧠 ANALYTICS RANKING — CENTRAL QUANT",
            f"Data/hora: {payload.get('generated_at')}",
            "",
            "Ranking inteligente por robô:",
        ]

        for i, bot in enumerate(payload.get("bots", []), start=1):
            lines += [
                "",
                f"{i}. {bot.get('bot')}",
                f"Score: {bot.get('score')}/100",
                f"Confiança: {bot.get('confidence')}",
                f"Recomendação: {bot.get('recommendation')}",
                f"Trades: {bot.get('trades')}",
                f"Win rate: {bot.get('win_rate_pct')}%",
                f"PnL total: {bot.get('pnl_total_pct')}%",
                f"PnL médio: {bot.get('pnl_avg_pct')}%",    
                f"TP50 hit rate: {bot.get('tp50_hit_rate_pct')}%",
            ]

            strengths = bot.get("strengths") or []
            weaknesses = bot.get("weaknesses") or []
            notes = bot.get("notes") or []

            if strengths:
                lines.append("Pontos fortes:")
                for s in strengths:
                    lines.append(f"✅ {s}")

            if weaknesses:
                lines.append("Pontos fracos:")
                for w in weaknesses:
                    lines.append(f"⚠️ {w}")

            if notes:
                lines.append("Notas:")
                for n in notes:
                    lines.append(f"- {n}")

        return {
            "ok": True,
            "text": "\n".join(lines),
            "payload": payload,
        }

    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
        }


@app.route("/analytics/setups/ranking")
def analytics_setups_ranking_route():

    try:
        import analytics_engine

        payload = analytics_engine.setup_ranking()

        lines = [
            "🧠 ANALYTICS SETUPS — CENTRAL QUANT",
            f"Data/hora: {payload.get('generated_at')}",
            "",
            "Ranking inteligente por setup:",
        ]

        for i, setup in enumerate(payload.get("setups", []), start=1):

            lines += [
                "",
                f"{i}. {setup.get('setup')}",
                f"Score: {setup.get('score')}/100",
                f"Confiança: {setup.get('confidence')}",
                f"Recomendação: {setup.get('recommendation')}",
                f"Trades: {setup.get('trades')}",
                f"Win rate: {setup.get('win_rate_pct')}%",
                f"PnL total: {setup.get('pnl_total_pct')}%",
                f"PnL médio: {setup.get('pnl_avg_pct')}%",
                f"TP50 hit rate: {setup.get('tp50_hit_rate_pct')}%",
            ]

            strengths = setup.get("strengths") or []
            weaknesses = setup.get("weaknesses") or []
            notes = setup.get("notes") or []

            if strengths:
                lines.append("Pontos fortes:")
                for s in strengths:
                    lines.append(f"✅ {s}")

            if weaknesses:
                lines.append("Pontos fracos:")
                for w in weaknesses:
                    lines.append(f"⚠️ {w}")

            if notes:
                lines.append("Notas:")
                for n in notes:
                    lines.append(f"- {n}")

        return {
            "ok": True,
            "text": "\n".join(lines),
            "payload": payload,
        }

    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
        }
    

@app.route("/analytics/decision")
def analytics_decision_engine_route():
    try:
        import analytics_engine

        payload = analytics_engine.decision_engine_observation()

        lines = [
            "🧠 DECISION ENGINE — CENTRAL QUANT",
            f"Data/hora: {payload.get('generated_at')}",
            f"Modo: {payload.get('mode')}",
            "",
            "Decisões em observação:",
        ]

        health = payload.get("portfolio_health", {})

        lines += [
            "",
            "Saúde da carteira:",
            f"Concentração: {health.get('concentration')}",
            f"Diversificação: {health.get('diversification')}",
            f"Risco: {health.get('risk_level')}",
            f"Maior peso: {health.get('top_weight_pct')}%",
        ]

        for item in payload.get("decisions", []):
            lines += [
                "",
                f"{item.get('name')}: {item.get('decision')}",
                f"Peso sugerido: {item.get('suggested_weight_pct')}%",
                f"Categoria: {item.get('category')}",
                f"Motivo: {item.get('reason')}",
                f"Origem: {item.get('source_action')}",
            ]

        return {
            "ok": True,
            "text": "\n".join(lines),
            "payload": payload,
        }

    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
        }    


@app.route("/analytics/weights")
def analytics_weights_route():
    try:
        import analytics_engine

        payload = analytics_engine.portfolio_weights()

        lines = [
            "⚖️ PORTFOLIO WEIGHTS — CENTRAL QUANT",
            f"Data/hora: {payload.get('generated_at')}",
            f"Modo: {payload.get('mode')}",
            "",
            "Saúde da carteira:",
            f"Concentração: {payload.get('portfolio_health', {}).get('concentration')}",
            f"Diversificação: {payload.get('portfolio_health', {}).get('diversification')}",
            f"Risco: {payload.get('portfolio_health', {}).get('risk_level')}",
            f"Dependência do maior robô: {payload.get('portfolio_health', {}).get('dependency_on_top_bot')}",
            f"Maior peso: {payload.get('portfolio_health', {}).get('top_weight_pct')}%",
            "",
            "Alocação sugerida por robô:",
        ]

        for item in payload.get("weights", []):
            lines += [
                "",
                f"{item.get('name')}: {item.get('suggested_weight_pct')}%",
                f"Score: {item.get('score')}",
                f"Confiança: {item.get('confidence')}",
                f"PnL: {item.get('pnl_total_pct')}%",
                f"Trades: {item.get('trades')}",
                f"Ação base: {item.get('source_action')}",
                f"Categoria: {item.get('category')}",
                f"Peso bruto: {item.get('base_weight_pct')}%",
                f"Peso limitado: {item.get('capped_weight_pct')}%",
            ]

        lines += ["", "Notas:"]
        for note in payload.get("notes", []):
            lines.append(f"- {note}")

        return {
            "ok": True,
            "text": "\n".join(lines),
            "payload": payload,
        }

    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
        }
    

@app.route("/analytics/portfolio-manager")
def analytics_portfolio_manager_route():
    try:
        from flask import request
        import portfolio_manager

        capital = request.args.get("capital", default=10000, type=float)

        payload = portfolio_manager.portfolio_manager(capital=capital)

        health = payload.get("portfolio_health", {})

        lines = [
            "📊 PORTFOLIO MANAGER — CENTRAL QUANT",
            f"Data/hora: {payload.get('generated_at')}",
            f"Modo: {payload.get('mode')}",
            f"Capital analisado: {payload.get('capital')} USDT",
            f"Capital alocado: {payload.get('total_allocated')} USDT",
            f"Risco aberto máximo teórico: {payload.get('total_max_open_risk_usdt')} USDT ({payload.get('total_max_open_risk_pct')}%)",
            "",
            "Saúde da carteira:",
            f"Concentração: {health.get('concentration')}",
            f"Diversificação: {health.get('diversification')}",
            f"Risco: {health.get('risk_level')}",
            f"Maior peso: {health.get('top_weight_pct')}%",
            "",
            "Alocação teórica por robô:",
        ]

        for item in payload.get("allocations", []):
            lines += [
                "",
                f"{item.get('name')}:",
                f"Peso: {item.get('weight_pct')}%",
                f"Capital: {item.get('capital_allocated')} USDT",
                f"Risco máximo por trade: {item.get('risk_policy', {}).get('max_risk_per_trade_usdt')} USDT ({item.get('risk_policy', {}).get('max_risk_per_trade_pct')}%)",
                f"Risco aberto máximo: {item.get('risk_policy', {}).get('max_open_risk_usdt')} USDT ({item.get('risk_policy', {}).get('max_open_risk_pct')}%)",
                f"Categoria: {item.get('category')}",
                f"Decisão: {item.get('decision')}",
                f"Score: {item.get('score')}",
                f"Confiança: {item.get('confidence')}",
                f"PnL: {item.get('pnl_total_pct')}%",
                f"Trades: {item.get('trades')}",
                f"Motivo: {item.get('reason')}",
            ]

        lines += ["", "Notas:"]
        for note in payload.get("notes", []):
            lines.append(f"- {note}")

        return {
            "ok": True,
            "text": "\n".join(lines),
            "payload": payload,
        }

    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
        }    


@app.route("/analytics/portfolio")
def analytics_portfolio_route():
    try:
        import analytics_engine

        payload = analytics_engine.portfolio_advisor()
        p = payload.get("portfolio", {})

        lines = [
            "🧭 PORTFOLIO ADVISOR — CENTRAL QUANT",
            f"Data/hora: {payload.get('generated_at')}",
            "",
            "Núcleo principal:",
        ]

        core = p.get("core_bots", [])
        if core:
            for item in core:
                lines.append(
                    f"- {item.get('name')} | Score {item.get('score')} | "
                    f"Confiança {item.get('confidence')} | PnL {item.get('pnl_total_pct')}%"
                )
        else:
            lines.append("- Nenhum robô ainda atingiu critérios de núcleo principal.")

        lines += ["", "Amostra insuficiente:"]
        for item in p.get("insufficient_sample_bots", []):
            lines.append(
                f"- {item.get('name')} | Score {item.get('score')} | "
                f"Trades {item.get('trades')} | Recomendação {item.get('recommendation')}"
            )

        lines += ["", "Reduzir / atenção:"]
        reduce_items = p.get("reduce_bots", [])
        if reduce_items:
            for item in reduce_items:
                lines.append(
                    f"- {item.get('name')} | Score {item.get('score')} | "
                    f"PnL {item.get('pnl_total_pct')}%"
                )
        else:
            lines.append("- Nenhum robô em redução prioritária.")

        lines += ["", "Setups principais:"]
        for item in p.get("core_setups", []):
            lines.append(
                f"- {item.get('name')} | Score {item.get('score')} | "
                f"PnL {item.get('pnl_total_pct')}%"
            )

        lines += ["", "Alertas:"]
        alerts = p.get("alerts", [])
        if alerts:
            for alert in alerts:
                lines.append(
                    f"- {alert.get('name')}: {alert.get('type')} "
                    f"({alert.get('giveback_avg_pct')}%)"
                )
        else:
            lines.append("- Nenhum alerta relevante.")

        lines += ["", "Recomendação geral:"]
        recs = p.get("general_recommendations", [])
        if recs:
            for rec in recs:
                lines.append(
                    f"- {rec.get('name')}: {rec.get('action')} — {rec.get('reason')}"
                )
        else:
            lines.append("- Nenhuma recomendação geral disponível.")

        lines += ["", "Prioridades da semana:"]
        priorities = p.get("weekly_priorities", [])
        if priorities:
            for priority in priorities:
                lines.append(f"- {priority}")
        else:
            lines.append("- Nenhuma prioridade específica.")    

        return {
            "ok": True,
            "text": "\n".join(lines),
            "payload": payload,
        }

    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
        }        


@app.route("/analytics/exposure")
def analytics_exposure_route():
    try:
        from flask import request
        import bot_exposure_manager

        capital = request.args.get("capital", default=10000, type=float)

        payload = bot_exposure_manager.bot_exposure_manager(capital=capital)

        lines = [
            "📡 BOT EXPOSURE MANAGER — CENTRAL QUANT",
            f"Data/hora: {payload.get('generated_at')}",
            f"Modo: {payload.get('mode')}",
            f"Capital analisado: {payload.get('capital')} USDT",
            "",
            "Exposição por robô:",
        ]

        for item in payload.get("exposures", []):
            lines += [
                "",
                f"{item.get('name')}:",
                f"Categoria: {item.get('category')}",
                f"Decisão: {item.get('decision')}",
                f"Capital destinado: {item.get('capital_allocated')} USDT",
                f"Capital usado: {item.get('capital_used')} USDT",
                f"Capital livre: {item.get('capital_free')} USDT",
                f"Uso do capital: {item.get('usage_pct')}%",
                f"Risco máximo aberto: {item.get('max_open_risk_usdt')} USDT",
                f"Risco usado: {item.get('risk_used_usdt')} USDT",
                f"Risco livre: {item.get('risk_free_usdt')} USDT",
                f"Uso do risco: {item.get('risk_usage_pct')}%",
            ]

        lines += ["", "Notas:"]
        for note in payload.get("notes", []):
            lines.append(f"- {note}")

        return {
            "ok": True,
            "text": "\n".join(lines),
            "payload": payload,
        }

    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
        }
    

# ==========================================================
# BOT EXPOSURE MANAGER V2 - CENTRAL QUANT
# ==========================================================

BOT_EXPOSURE_MANAGER_V2_VERSION = "2026-07-03-BOT-EXPOSURE-MANAGER-V2.1"
BOT_EXPOSURE_MANAGER_V2_MODE = os.environ.get("BOT_EXPOSURE_MANAGER_V2_MODE", "OBSERVATION_ONLY").strip().upper()
BOT_EXPOSURE_MANAGER_V21_ESTIMATE_MISSING_VALUES = env_bool("BOT_EXPOSURE_MANAGER_V21_ESTIMATE_MISSING_VALUES", True)
BOT_EXPOSURE_MANAGER_V21_CAP_ESTIMATE_TO_ALLOCATION = env_bool("BOT_EXPOSURE_MANAGER_V21_CAP_ESTIMATE_TO_ALLOCATION", True)
BOT_EXPOSURE_MANAGER_V2_CACHE = {
    "last_snapshot": None,
    "last_generated_at": None,
    "last_capital": None,
}
BOT_EXPOSURE_MANAGER_V2_LOCK = threading.Lock()


def _bem_v2_env_float(name, default):
    try:
        return float(os.environ.get(name, default))
    except Exception:
        return float(default)


def _bem_v2_bot_profiles(capital=10000.0):
    """
    Perfil inicial consultivo por robô.
    Pode ser ajustado por ENV sem alterar código:
    DONKEY_CAPITAL_PCT, DONKEY_MAX_OPEN_RISK_PCT etc.
    """
    defaults = {
        "TRENDPRO": {"category": "CORE", "capital_pct": 15.0, "max_open_risk_pct": 1.5},
        "DONKEY": {"category": "CORE", "capital_pct": 45.0, "max_open_risk_pct": 4.0},
        "PREDATOR": {"category": "CORE", "capital_pct": 20.0, "max_open_risk_pct": 2.0},
        "TURTLE": {"category": "SATELLITE", "capital_pct": 10.0, "max_open_risk_pct": 1.0},
        "FALCON": {"category": "TACTICAL", "capital_pct": 5.0, "max_open_risk_pct": 0.75},
        "COBRA": {"category": "TACTICAL", "capital_pct": 3.0, "max_open_risk_pct": 0.50},
        "MEME": {"category": "EXPERIMENTAL", "capital_pct": 2.0, "max_open_risk_pct": 0.25},
    }

    profiles = {}
    known_bots = set(defaults.keys())
    try:
        known_bots.update([str(k).upper() for k in BOT_CONFIGS.keys()])
    except Exception:
        pass

    for bot in sorted(known_bots):
        base = defaults.get(bot, {"category": "OTHER", "capital_pct": 0.0, "max_open_risk_pct": 0.0})
        capital_pct = _bem_v2_env_float(f"{bot}_CAPITAL_PCT", base.get("capital_pct", 0.0))
        max_risk_pct = _bem_v2_env_float(f"{bot}_MAX_OPEN_RISK_PCT", base.get("max_open_risk_pct", 0.0))
        profiles[bot] = {
            "bot": bot,
            "category": os.environ.get(f"{bot}_CATEGORY", base.get("category", "OTHER")).strip().upper(),
            "capital_pct": round(capital_pct, 4),
            "capital_allocated": round(float(capital or 0) * capital_pct / 100.0, 4),
            "max_open_risk_pct": round(max_risk_pct, 4),
            "max_open_risk_usdt": round(float(capital or 0) * max_risk_pct / 100.0, 4),
        }
    return profiles


def _bem_v2_first_value(item, keys, default=None):
    if not isinstance(item, dict):
        return default
    for key in keys:
        value = item.get(key)
        if value not in [None, ""]:
            return value
    return default


def _bem_v2_float(value, default=0.0):
    try:
        if value in [None, ""]:
            return default
        return float(value)
    except Exception:
        return default


def _bem_v2_side(position):
    side = str(_bem_v2_first_value(position, ["side", "direction", "signal"], "UNKNOWN")).upper().strip()
    if side == "BUY":
        return "LONG"
    if side == "SELL":
        return "SHORT"
    return side or "UNKNOWN"


def _bem_v2_symbol(position):
    try:
        return normalize_registry_symbol(
            _bem_v2_first_value(position, ["symbol_clean", "symbol", "ativo", "pair"], "UNKNOWN")
        )
    except Exception:
        return str(_bem_v2_first_value(position, ["symbol_clean", "symbol", "ativo", "pair"], "UNKNOWN")).upper().strip()


def _bem_v2_bot(position):
    try:
        return normalize_registry_bot(_bem_v2_first_value(position, ["bot", "robot", "source_bot"], "UNKNOWN"))
    except Exception:
        return str(_bem_v2_first_value(position, ["bot", "robot", "source_bot"], "UNKNOWN")).upper().strip()


def _bem_v2_setup(position, bot="UNKNOWN"):
    return str(_bem_v2_first_value(
        position,
        ["setup", "signal_type", "setup_label", "origin", "origem", "strategy"],
        bot,
    )).upper().strip() or bot


def _bem_v2_qty(position):
    return _bem_v2_float(_bem_v2_first_value(position, ["qty", "quantity", "amount", "position_size", "size"], 0), 0.0)


def _bem_v2_entry(position):
    return _bem_v2_float(_bem_v2_first_value(position, ["entry", "entrada", "entry_price", "price"], 0), 0.0)


def _bem_v2_stop(position):
    return _bem_v2_float(_bem_v2_first_value(position, ["sl", "stop", "initial_stop", "stop_atual", "current_stop"], 0), 0.0)


def _bem_v2_capital_used(position):
    explicit = _bem_v2_first_value(position, [
        "capital_used", "capital_usdt", "margin_usdt", "required_capital", "notional_usdt",
        "effective_notional_usdt", "value_usdt", "position_value_usdt",
    ], None)
    if explicit not in [None, ""]:
        return max(0.0, _bem_v2_float(explicit, 0.0))

    entry = _bem_v2_entry(position)
    qty = _bem_v2_qty(position)
    if entry > 0 and qty > 0:
        return max(0.0, abs(entry * qty))

    return 0.0


def _bem_v21_default_position_capital(bot, profile=None):
    """
    Capital estimado por posição quando o Registry ainda não possui qty/capital.
    Pode ser ajustado por ENV:
    - BOT_EXPOSURE_MANAGER_V21_DEFAULT_POSITION_CAPITAL_USDT
    - DONKEY_ESTIMATED_POSITION_CAPITAL_USDT, COBRA_ESTIMATED_POSITION_CAPITAL_USDT etc.
    """
    bot = normalize_registry_bot(str(bot or "UNKNOWN").upper().strip())
    defaults = {
        "DONKEY": 300.0,
        "PREDATOR": 400.0,
        "TRENDPRO": 300.0,
        "TURTLE": 250.0,
        "FALCON": 250.0,
        "COBRA": 150.0,
        "MEME": 100.0,
    }
    global_default = _bem_v2_env_float("BOT_EXPOSURE_MANAGER_V21_DEFAULT_POSITION_CAPITAL_USDT", defaults.get(bot, 100.0))
    return _bem_v2_env_float(f"{bot}_ESTIMATED_POSITION_CAPITAL_USDT", global_default)


def _bem_v21_capital_used(position, bot="UNKNOWN", profile=None, bot_position_count=1):
    explicit = _bem_v2_capital_used(position)
    if explicit > 0:
        return explicit, "EXPLICIT"

    if not BOT_EXPOSURE_MANAGER_V21_ESTIMATE_MISSING_VALUES:
        return 0.0, "MISSING"

    profile = profile or {}
    count = max(1, int(bot_position_count or 1))
    estimated = max(0.0, _bem_v21_default_position_capital(bot, profile=profile))
    allocated = _bem_v2_float(profile.get("capital_allocated"), 0.0)

    # Se a estimativa padrão estourar a alocação do robô, distribui a alocação entre as posições.
    if BOT_EXPOSURE_MANAGER_V21_CAP_ESTIMATE_TO_ALLOCATION and allocated > 0 and estimated * count > allocated:
        estimated = allocated / count

    return max(0.0, estimated), "ESTIMATED"


def _bem_v21_risk_pct_from_entry_stop(position):
    entry = _bem_v2_entry(position)
    stop = _bem_v2_stop(position)
    if entry > 0 and stop > 0:
        return abs(entry - stop) / entry * 100.0
    return 0.0


def _bem_v2_risk_used(position):
    explicit = _bem_v2_first_value(position, [
        "risk_usdt", "required_risk_usdt", "open_risk_usdt", "risk_value_usdt", "max_loss_usdt"
    ], None)
    if explicit not in [None, ""]:
        return max(0.0, _bem_v2_float(explicit, 0.0))

    entry = _bem_v2_entry(position)
    stop = _bem_v2_stop(position)
    qty = _bem_v2_qty(position)
    if entry > 0 and stop > 0 and qty > 0:
        return max(0.0, abs(entry - stop) * qty)

    risk_pct = _bem_v2_float(_bem_v2_first_value(position, ["risk_pct", "risco_pct", "risk_percent"], 0), 0.0)
    capital_used = _bem_v2_capital_used(position)
    if risk_pct > 0 and capital_used > 0:
        return max(0.0, capital_used * risk_pct / 100.0)

    return 0.0


def _bem_v21_risk_used(position, capital_used=0.0):
    explicit = _bem_v2_risk_used(position)
    if explicit > 0:
        return explicit, "EXPLICIT", _bem_v2_float(_bem_v2_first_value(position, ["risk_pct", "risco_pct", "risk_percent"], 0), 0.0)

    if not BOT_EXPOSURE_MANAGER_V21_ESTIMATE_MISSING_VALUES:
        return 0.0, "MISSING", 0.0

    risk_pct = _bem_v2_float(_bem_v2_first_value(position, ["risk_pct", "risco_pct", "risk_percent"], 0), 0.0)
    if risk_pct <= 0:
        risk_pct = _bem_v21_risk_pct_from_entry_stop(position)

    if risk_pct > 0 and capital_used > 0:
        return max(0.0, capital_used * risk_pct / 100.0), "ESTIMATED", risk_pct

    return 0.0, "MISSING", 0.0


def _bem_v2_pnl_open(position):
    return _bem_v2_float(_bem_v2_first_value(position, [
        "pnl_usdt", "unrealized_pnl_usdt", "open_pnl_usdt", "profit_usdt", "pnl"
    ], 0), 0.0)


def _bem_v2_empty_bot_state(bot, profile=None):
    profile = profile or {}
    capital_allocated = _bem_v2_float(profile.get("capital_allocated"), 0.0)
    max_risk_usdt = _bem_v2_float(profile.get("max_open_risk_usdt"), 0.0)
    return {
        "bot": bot,
        "category": profile.get("category", "OTHER"),
        "capital_pct": profile.get("capital_pct", 0.0),
        "capital_allocated": round(capital_allocated, 4),
        "capital_used": 0.0,
        "capital_free": round(capital_allocated, 4),
        "usage_pct": 0.0,
        "max_open_risk_pct": profile.get("max_open_risk_pct", 0.0),
        "max_open_risk_usdt": round(max_risk_usdt, 4),
        "risk_used_usdt": 0.0,
        "risk_free_usdt": round(max_risk_usdt, 4),
        "risk_usage_pct": 0.0,
        "positions": 0,
        "long": 0,
        "short": 0,
        "unknown_side": 0,
        "net_direction": "FLAT",
        "symbols": {},
        "setups": {},
        "largest_symbol": None,
        "largest_symbol_count": 0,
        "largest_position": None,
        "largest_risk": None,
        "open_pnl_usdt": 0.0,
        "runner_buckets": _empty_runner_buckets(),
        "best_open_runner": None,
        "status": "IDLE",
        "alerts": [],
        "decision": "ALLOW_OBSERVATION",
        "data_quality": {
            "explicit_capital_positions": 0,
            "estimated_capital_positions": 0,
            "missing_capital_positions": 0,
            "explicit_risk_positions": 0,
            "estimated_risk_positions": 0,
            "missing_risk_positions": 0,
        },
    }


def _bem_v2_add_counter(target, key, amount=1):
    key = str(key or "UNKNOWN").upper().strip() or "UNKNOWN"
    target[key] = target.get(key, 0) + amount


def _bem_v2_finalize_state(state):
    capital_allocated = _bem_v2_float(state.get("capital_allocated"), 0.0)
    capital_used = _bem_v2_float(state.get("capital_used"), 0.0)
    max_risk_usdt = _bem_v2_float(state.get("max_open_risk_usdt"), 0.0)
    risk_used = _bem_v2_float(state.get("risk_used_usdt"), 0.0)

    state["capital_used"] = round(capital_used, 4)
    state["capital_free"] = round(capital_allocated - capital_used, 4)
    state["usage_pct"] = round((capital_used / capital_allocated) * 100.0, 2) if capital_allocated > 0 else 0.0
    state["risk_used_usdt"] = round(risk_used, 4)
    state["risk_free_usdt"] = round(max_risk_usdt - risk_used, 4)
    state["risk_usage_pct"] = round((risk_used / max_risk_usdt) * 100.0, 2) if max_risk_usdt > 0 else 0.0

    if state.get("long", 0) > state.get("short", 0):
        state["net_direction"] = "LONG"
    elif state.get("short", 0) > state.get("long", 0):
        state["net_direction"] = "SHORT"
    elif state.get("positions", 0) > 0:
        state["net_direction"] = "BALANCED"
    else:
        state["net_direction"] = "FLAT"

    symbols = state.get("symbols") or {}
    if symbols:
        largest_symbol, count = sorted(symbols.items(), key=lambda kv: (-kv[1], kv[0]))[0]
        state["largest_symbol"] = largest_symbol
        state["largest_symbol_count"] = count

    alerts = []
    if state["capital_free"] < 0:
        alerts.append("CAPITAL_EXCEEDED")
    if state["risk_free_usdt"] < 0:
        alerts.append("RISK_EXCEEDED")
    if state.get("usage_pct", 0) >= 90:
        alerts.append("CAPITAL_NEAR_LIMIT")
    if state.get("risk_usage_pct", 0) >= 90:
        alerts.append("RISK_NEAR_LIMIT")
    if state.get("positions", 0) == 0:
        status = "IDLE"
    elif alerts:
        status = "OVERLOADED" if ("CAPITAL_EXCEEDED" in alerts or "RISK_EXCEEDED" in alerts) else "LOADED_ATTENTION"
    else:
        status = "LOADED"

    state["alerts"] = alerts
    state["status"] = status

    if "RISK_EXCEEDED" in alerts or "CAPITAL_EXCEEDED" in alerts:
        state["decision"] = "REDUCE_OR_BLOCK_OBSERVATION"
    elif "RISK_NEAR_LIMIT" in alerts or "CAPITAL_NEAR_LIMIT" in alerts:
        state["decision"] = "REDUCE_SIZE_OBSERVATION"
    else:
        state["decision"] = "ALLOW_OBSERVATION"

    return state


def build_bot_exposure_manager_v2(capital=10000.0, bot_filter=None):
    """
    Bot Exposure Manager V2 consultivo.
    Fonte oficial: get_open_positions_central(), priorizando Trade Registry.
    Não bloqueia, não executa e não altera lote. Apenas consolida estado.
    """
    try:
        capital = float(capital or 0)
    except Exception:
        capital = 10000.0

    profiles = _bem_v2_bot_profiles(capital=capital)
    positions = get_open_positions_central()
    bot_position_counts = {}
    for _position_count_item in positions:
        if isinstance(_position_count_item, dict):
            _count_bot = _bem_v2_bot(_position_count_item)
            bot_position_counts[_count_bot] = bot_position_counts.get(_count_bot, 0) + 1
    bots = {bot: _bem_v2_empty_bot_state(bot, profile) for bot, profile in profiles.items()}

    total_capital_used = 0.0
    total_risk_used = 0.0
    total_open_pnl = 0.0
    by_symbol_total = {}
    by_setup_total = {}
    by_side_total = {"LONG": 0, "SHORT": 0, "UNKNOWN": 0}
    runner_buckets_total = _empty_runner_buckets()
    best_open_runner = None
    position_count = 0

    for position in positions:
        if not isinstance(position, dict):
            continue

        bot = _bem_v2_bot(position)
        if bot not in bots:
            bots[bot] = _bem_v2_empty_bot_state(bot, {
                "category": "OTHER",
                "capital_pct": 0.0,
                "capital_allocated": 0.0,
                "max_open_risk_pct": 0.0,
                "max_open_risk_usdt": 0.0,
            })

        state = bots[bot]
        symbol = _bem_v2_symbol(position)
        side = _bem_v2_side(position)
        setup = _bem_v2_setup(position, bot=bot)
        profile = profiles.get(bot, {})
        capital_used, capital_source = _bem_v21_capital_used(
            position,
            bot=bot,
            profile=profile,
            bot_position_count=bot_position_counts.get(bot, 1),
        )
        risk_used, risk_source, risk_pct_estimated = _bem_v21_risk_used(position, capital_used=capital_used)
        open_pnl = _bem_v2_pnl_open(position)
        runner_r = _position_runner_r(position)
        runner_pct = _position_runner_pct(position)

        state["positions"] += 1
        position_count += 1
        if side == "LONG":
            state["long"] += 1
            by_side_total["LONG"] += 1
        elif side == "SHORT":
            state["short"] += 1
            by_side_total["SHORT"] += 1
        else:
            state["unknown_side"] += 1
            by_side_total["UNKNOWN"] += 1

        _bem_v2_add_counter(state["symbols"], symbol)
        _bem_v2_add_counter(state["setups"], setup)
        _bem_v2_add_counter(by_symbol_total, symbol)
        _bem_v2_add_counter(by_setup_total, setup)

        state["capital_used"] += capital_used
        state["risk_used_usdt"] += risk_used
        state["open_pnl_usdt"] += open_pnl
        dq = state.setdefault("data_quality", {})
        dq[f"{str(capital_source).lower()}_capital_positions"] = dq.get(f"{str(capital_source).lower()}_capital_positions", 0) + 1
        dq[f"{str(risk_source).lower()}_risk_positions"] = dq.get(f"{str(risk_source).lower()}_risk_positions", 0) + 1
        total_capital_used += capital_used
        total_risk_used += risk_used
        total_open_pnl += open_pnl

        position_summary = {
            "bot": bot,
            "symbol": symbol,
            "setup": setup,
            "side": side,
            "capital_used": round(capital_used, 4),
            "risk_used_usdt": round(risk_used, 4),
            "risk_pct_estimated": round(risk_pct_estimated, 4),
            "capital_source": capital_source,
            "risk_source": risk_source,
            "open_pnl_usdt": round(open_pnl, 4),
            "entry": _bem_v2_first_value(position, ["entry", "entrada", "entry_price", "price"], None),
            "stop": _bem_v2_first_value(position, ["sl", "stop", "initial_stop", "stop_atual", "current_stop"], None),
            "tp50": position.get("tp50"),
            "runner_r": round(runner_r, 4),
            "runner_pct": round(runner_pct, 4),
            "trade_id": position.get("trade_id") or position.get("id") or position.get("position_id"),
        }

        if state.get("largest_position") is None or capital_used > state["largest_position"].get("capital_used", 0):
            state["largest_position"] = dict(position_summary)
        if state.get("largest_risk") is None or risk_used > state["largest_risk"].get("risk_used_usdt", 0):
            state["largest_risk"] = dict(position_summary)

        _update_runner_buckets(state["runner_buckets"], runner_r)
        _update_runner_buckets(runner_buckets_total, runner_r)

        if state.get("best_open_runner") is None or runner_r > state["best_open_runner"].get("runner_r", 0):
            state["best_open_runner"] = dict(position_summary)
        if best_open_runner is None or runner_r > best_open_runner.get("runner_r", 0):
            best_open_runner = dict(position_summary)

    for bot, state in list(bots.items()):
        state["open_pnl_usdt"] = round(_bem_v2_float(state.get("open_pnl_usdt"), 0.0), 4)
        bots[bot] = _bem_v2_finalize_state(state)

    if bot_filter:
        wanted = normalize_registry_bot(str(bot_filter).upper().strip())
        bots = {wanted: bots.get(wanted, _bem_v2_finalize_state(_bem_v2_empty_bot_state(wanted, profiles.get(wanted, {}))))}

    summary = {
        "positions": position_count,
        "capital": round(capital, 4),
        "capital_used": round(total_capital_used, 4),
        "capital_free": round(capital - total_capital_used, 4),
        "capital_usage_pct": round((total_capital_used / capital) * 100.0, 2) if capital > 0 else 0.0,
        "risk_used_usdt": round(total_risk_used, 4),
        "open_pnl_usdt": round(total_open_pnl, 4),
        "long": by_side_total.get("LONG", 0),
        "short": by_side_total.get("SHORT", 0),
        "unknown_side": by_side_total.get("UNKNOWN", 0),
        "net_direction": "LONG" if by_side_total.get("LONG", 0) > by_side_total.get("SHORT", 0) else ("SHORT" if by_side_total.get("SHORT", 0) > by_side_total.get("LONG", 0) else "BALANCED"),
        "symbols": dict(sorted(by_symbol_total.items(), key=lambda kv: (-kv[1], kv[0]))),
        "setups": dict(sorted(by_setup_total.items(), key=lambda kv: (-kv[1], kv[0]))),
        "runner_buckets": runner_buckets_total,
        "best_open_runner": best_open_runner,
        "data_quality": {
            "estimate_missing_values": BOT_EXPOSURE_MANAGER_V21_ESTIMATE_MISSING_VALUES,
            "cap_estimate_to_allocation": BOT_EXPOSURE_MANAGER_V21_CAP_ESTIMATE_TO_ALLOCATION,
            "estimated_capital_positions": sum((b.get("data_quality") or {}).get("estimated_capital_positions", 0) for b in bots.values()),
            "missing_capital_positions": sum((b.get("data_quality") or {}).get("missing_capital_positions", 0) for b in bots.values()),
            "estimated_risk_positions": sum((b.get("data_quality") or {}).get("estimated_risk_positions", 0) for b in bots.values()),
            "missing_risk_positions": sum((b.get("data_quality") or {}).get("missing_risk_positions", 0) for b in bots.values()),
        },
    }

    payload = {
        "ok": True,
        "version": BOT_EXPOSURE_MANAGER_V2_VERSION,
        "generated_at": data_hora_sp_str(),
        "mode": BOT_EXPOSURE_MANAGER_V2_MODE,
        "source": "central_trade_registry_or_bot_positions",
        "capital": round(capital, 4),
        "summary": summary,
        "bots": bots,
        "notes": [
            "Bot Exposure Manager V2.1 está em modo consultivo/observação.",
            "Não altera lote, execução, risco real ou permissões de entrada.",
            "Fonte preferencial: Trade Registry; fallback: posições abertas dos robôs carregados.",
            "Quando qty/capital/risk não vêm no Registry, estima capital por perfil do robô e risco pela distância entrada-stop.",
            "Preparado para alimentar Portfolio Advisor, Capital Allocator V2 e Dynamic Risk Budget.",
        ],
    }

    with BOT_EXPOSURE_MANAGER_V2_LOCK:
        BOT_EXPOSURE_MANAGER_V2_CACHE["last_snapshot"] = payload
        BOT_EXPOSURE_MANAGER_V2_CACHE["last_generated_at"] = payload.get("generated_at")
        BOT_EXPOSURE_MANAGER_V2_CACHE["last_capital"] = payload.get("capital")

    return payload


def build_bot_exposure_manager_v2_text(capital=10000.0, bot_filter=None):
    payload = build_bot_exposure_manager_v2(capital=capital, bot_filter=bot_filter)
    summary = payload.get("summary", {})
    bots = payload.get("bots", {})

    lines = [
        "📡 BOT EXPOSURE MANAGER V2.1 — CENTRAL QUANT",
        f"Data/hora: {payload.get('generated_at')}",
        f"Versão: {payload.get('version')}",
        f"Modo: {payload.get('mode')}",
        "",
        "Resumo geral:",
        f"Capital analisado: {summary.get('capital')} USDT",
        f"Capital usado: {summary.get('capital_used')} USDT",
        f"Capital livre: {summary.get('capital_free')} USDT",
        f"Uso do capital: {summary.get('capital_usage_pct')}%",
        f"Risco aberto estimado: {summary.get('risk_used_usdt')} USDT",
        f"PnL aberto estimado: {summary.get('open_pnl_usdt')} USDT",
        f"Posições: {summary.get('positions')} | LONG {summary.get('long')} | SHORT {summary.get('short')}",
        f"Direção líquida: {summary.get('net_direction')}",
        f"Estimativas: capital={((summary.get('data_quality') or {}).get('estimated_capital_positions'))} posições | risco={((summary.get('data_quality') or {}).get('estimated_risk_positions'))} posições",
        "",
        "Robôs:",
    ]

    for bot, item in sorted(bots.items(), key=lambda kv: (-kv[1].get("positions", 0), kv[0])):
        lines += [
            "",
            f"{bot} — {item.get('status')}",
            f"Categoria: {item.get('category')} | Decisão: {item.get('decision')}",
            f"Posições: {item.get('positions')} | LONG {item.get('long')} | SHORT {item.get('short')} | Net {item.get('net_direction')}",
            f"Capital: usado {item.get('capital_used')} / alocado {item.get('capital_allocated')} USDT ({item.get('usage_pct')}%)",
            f"Risco: usado {item.get('risk_used_usdt')} / limite {item.get('max_open_risk_usdt')} USDT ({item.get('risk_usage_pct')}%)",
            f"Capital livre: {item.get('capital_free')} USDT | Risco livre: {item.get('risk_free_usdt')} USDT",
            f"Maior ativo: {item.get('largest_symbol')} ({item.get('largest_symbol_count')})",
            f"Qualidade dados: capital estimado={(item.get('data_quality') or {}).get('estimated_capital_positions', 0)} | risco estimado={(item.get('data_quality') or {}).get('estimated_risk_positions', 0)}",
        ]
        if item.get("alerts"):
            lines.append("Alertas: " + ", ".join(item.get("alerts") or []))

    lines += ["", "Notas:"]
    for note in payload.get("notes", []):
        lines.append(f"- {note}")

    return "\n".join(lines), payload


@app.route("/exposure/v2")
@app.route("/exposure/bots/v2")
@app.route("/bot-exposure/v2")
def bot_exposure_manager_v2_route():
    capital = request.args.get("capital", default=10000, type=float)
    as_text = str(request.args.get("format", request.args.get("text", ""))).strip().lower() in {"1", "true", "yes", "sim", "on", "text", "txt"}
    text, payload = build_bot_exposure_manager_v2_text(capital=capital)
    if as_text:
        return text
    return {"ok": True, "text": text, "payload": payload}


@app.route("/exposure/bot/<bot>/v2")
@app.route("/bot-exposure/<bot>/v2")
def bot_exposure_manager_v2_bot_route(bot):
    capital = request.args.get("capital", default=10000, type=float)
    as_text = str(request.args.get("format", request.args.get("text", ""))).strip().lower() in {"1", "true", "yes", "sim", "on", "text", "txt"}
    text, payload = build_bot_exposure_manager_v2_text(capital=capital, bot_filter=bot)
    if as_text:
        return text
    return {"ok": True, "text": text, "payload": payload}


@app.route("/exposure/summary/v2")
def bot_exposure_manager_v2_summary_route():
    capital = request.args.get("capital", default=10000, type=float)
    payload = build_bot_exposure_manager_v2(capital=capital)
    return {
        "ok": True,
        "version": payload.get("version"),
        "generated_at": payload.get("generated_at"),
        "mode": payload.get("mode"),
        "summary": payload.get("summary"),
        "cache": {
            "last_generated_at": BOT_EXPOSURE_MANAGER_V2_CACHE.get("last_generated_at"),
            "last_capital": BOT_EXPOSURE_MANAGER_V2_CACHE.get("last_capital"),
        },
    }

# ==========================================================
# EXPOSURE SCORE ENGINE V1 - CENTRAL QUANT
# ==========================================================

EXPOSURE_SCORE_ENGINE_V1_VERSION = "2026-07-03-EXPOSURE-SCORE-ENGINE-V1"
EXPOSURE_SCORE_ENGINE_V1_MODE = os.environ.get("EXPOSURE_SCORE_ENGINE_V1_MODE", "OBSERVATION_ONLY").strip().upper()
EXPOSURE_SCORE_ENGINE_V1_CACHE = {
    "last_snapshot": None,
    "last_generated_at": None,
    "last_capital": None,
}
EXPOSURE_SCORE_ENGINE_V1_LOCK = threading.Lock()


def _ese_v1_clamp(value, minimum=0.0, maximum=100.0):
    try:
        value = float(value)
    except Exception:
        value = 0.0
    return max(float(minimum), min(float(maximum), value))


def _ese_v1_component_capital(usage_pct, positions=0):
    """Score de saúde do uso de capital. 0 posição fica neutro; lotado perde score."""
    usage = _ese_v1_clamp(usage_pct, 0.0, 200.0)
    positions = int(positions or 0)
    if positions <= 0:
        return 55.0
    if usage <= 50:
        return 95.0
    if usage <= 75:
        return 85.0
    if usage <= 90:
        return 70.0
    if usage <= 100:
        return 55.0
    if usage <= 120:
        return 35.0
    return 15.0


def _ese_v1_component_risk(risk_usage_pct, positions=0):
    """Score de saúde do risco aberto. Baixo uso de risco é positivo; excesso é penalizado."""
    usage = _ese_v1_clamp(risk_usage_pct, 0.0, 250.0)
    positions = int(positions or 0)
    if positions <= 0:
        return 60.0
    if usage <= 25:
        return 100.0
    if usage <= 50:
        return 90.0
    if usage <= 75:
        return 70.0
    if usage <= 100:
        return 45.0
    if usage <= 150:
        return 20.0
    return 5.0


def _ese_v1_component_concentration(bot_state):
    positions = int((bot_state or {}).get("positions", 0) or 0)
    if positions <= 0:
        return 60.0

    long_count = int((bot_state or {}).get("long", 0) or 0)
    short_count = int((bot_state or {}).get("short", 0) or 0)
    largest_symbol_count = int((bot_state or {}).get("largest_symbol_count", 0) or 0)

    dominant_side_pct = (max(long_count, short_count) / positions) * 100.0 if positions else 0.0
    symbol_pct = (largest_symbol_count / positions) * 100.0 if positions else 0.0

    side_score = 100.0
    if positions >= 4:
        if dominant_side_pct >= 90:
            side_score = 45.0
        elif dominant_side_pct >= 80:
            side_score = 60.0
        elif dominant_side_pct >= 70:
            side_score = 75.0
        else:
            side_score = 95.0

    symbol_score = 100.0
    if symbol_pct >= 50 and positions >= 3:
        symbol_score = 45.0
    elif symbol_pct >= 35 and positions >= 4:
        symbol_score = 65.0
    elif symbol_pct >= 25 and positions >= 6:
        symbol_score = 80.0

    return round((side_score * 0.65) + (symbol_score * 0.35), 2)


def _ese_v1_component_activity(positions, category="OTHER"):
    positions = int(positions or 0)
    category = str(category or "OTHER").upper()
    if positions <= 0:
        return 50.0
    if category == "CORE":
        if 3 <= positions <= 15:
            return 90.0
        if positions <= 20:
            return 70.0
        return 45.0
    if category in {"TACTICAL", "SATELLITE"}:
        if 1 <= positions <= 5:
            return 85.0
        if positions <= 8:
            return 65.0
        return 40.0
    if category == "EXPERIMENTAL":
        if 1 <= positions <= 3:
            return 80.0
        if positions <= 5:
            return 55.0
        return 30.0
    if positions <= 6:
        return 75.0
    return 55.0


def _ese_v1_load_analytics_ranking():
    """Tenta carregar score estatístico do analytics_engine. Falha de forma neutra."""
    try:
        import analytics_engine
        payload = analytics_engine.bot_ranking()
        items = payload.get("bots", []) if isinstance(payload, dict) else []
    except Exception as exc:
        return {}, str(exc)

    ranking = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        bot_name = normalize_registry_bot(
            item.get("bot") or item.get("name") or item.get("robot") or item.get("setup") or "UNKNOWN"
        )
        ranking[bot_name] = dict(item)
    return ranking, None


def _ese_v1_performance_component(bot, analytics_item=None):
    if not isinstance(analytics_item, dict):
        return {
            "score": 50.0,
            "source": "NEUTRAL_NO_ANALYTICS",
            "trades": 0,
            "win_rate_pct": 0.0,
            "pnl_total_pct": 0.0,
            "pnl_avg_pct": 0.0,
            "recommendation": "WAIT_SAMPLE",
            "confidence": "UNKNOWN",
        }

    raw_score = _ese_v1_clamp(analytics_item.get("score", 50.0), 0.0, 100.0)
    trades = int(_bem_v2_float(analytics_item.get("trades"), 0.0))
    if trades <= 0:
        raw_score = min(raw_score, 55.0)
    elif trades < 10:
        raw_score = (raw_score * 0.70) + 15.0  # reduz excesso de confiança com amostra pequena

    return {
        "score": round(_ese_v1_clamp(raw_score), 2),
        "source": "ANALYTICS_ENGINE",
        "trades": trades,
        "win_rate_pct": round(_bem_v2_float(analytics_item.get("win_rate_pct"), 0.0), 2),
        "pnl_total_pct": round(_bem_v2_float(analytics_item.get("pnl_total_pct"), 0.0), 4),
        "pnl_avg_pct": round(_bem_v2_float(analytics_item.get("pnl_avg_pct"), 0.0), 4),
        "recommendation": analytics_item.get("recommendation") or analytics_item.get("action") or "N/A",
        "confidence": analytics_item.get("confidence") or analytics_item.get("rating") or "N/A",
    }


def _ese_v1_decision(score, bot_state, performance):
    positions = int((bot_state or {}).get("positions", 0) or 0)
    usage_pct = _bem_v2_float((bot_state or {}).get("usage_pct"), 0.0)
    risk_usage_pct = _bem_v2_float((bot_state or {}).get("risk_usage_pct"), 0.0)
    recommendation = str((performance or {}).get("recommendation") or "").upper()

    if score >= 82 and usage_pct < 85 and risk_usage_pct < 55 and positions > 0:
        return "SCALE_UP_OBSERVATION"
    if score >= 72 and risk_usage_pct < 75:
        return "MAINTAIN_OR_ALLOW_OBSERVATION"
    if score >= 58:
        if usage_pct >= 90:
            return "REDUCE_SIZE_OBSERVATION"
        return "MAINTAIN_OBSERVATION"
    if score >= 45:
        return "REDUCE_SIZE_OBSERVATION"
    if "PAUS" in recommendation or "AGUARD" in recommendation:
        return "PAUSE_OR_WAIT_SAMPLE_OBSERVATION"
    return "PAUSE_OR_REVIEW_OBSERVATION"


def _ese_v1_rating(score):
    score = float(score or 0.0)
    if score >= 85:
        return "EXCELLENT"
    if score >= 72:
        return "GOOD"
    if score >= 58:
        return "ATTENTION"
    if score >= 45:
        return "WEAK"
    return "CRITICAL"


def _ese_v1_reasons(bot_state, components, performance):
    reasons = []
    usage_pct = _bem_v2_float((bot_state or {}).get("usage_pct"), 0.0)
    risk_usage_pct = _bem_v2_float((bot_state or {}).get("risk_usage_pct"), 0.0)
    positions = int((bot_state or {}).get("positions", 0) or 0)

    if positions <= 0:
        reasons.append("Robô sem posições abertas; score fica neutro até haver atividade.")
    if usage_pct >= 90:
        reasons.append("Capital alocado praticamente cheio; novas entradas deveriam reduzir tamanho.")
    if risk_usage_pct <= 25 and positions > 0:
        reasons.append("Risco aberto ainda baixo em relação ao limite consultivo.")
    elif risk_usage_pct >= 75:
        reasons.append("Risco aberto alto em relação ao limite consultivo.")

    perf_source = (performance or {}).get("source")
    if perf_source == "ANALYTICS_ENGINE":
        reasons.append(f"Score estatístico do Analytics: {(performance or {}).get('score')}/100.")
    else:
        reasons.append("Sem ranking estatístico suficiente; performance tratada como neutra.")

    if (components or {}).get("concentration_score", 100) < 70:
        reasons.append("Concentração direcional/por ativo exige atenção.")
    return reasons[:6]


def build_exposure_score_engine_v1(capital=10000.0, bot_filter=None):
    try:
        capital = float(capital or 0)
    except Exception:
        capital = 10000.0

    exposure = build_bot_exposure_manager_v2(capital=capital, bot_filter=bot_filter)
    analytics_ranking, analytics_error = _ese_v1_load_analytics_ranking()
    bots = exposure.get("bots", {}) if isinstance(exposure, dict) else {}

    scored_bots = {}
    ranking_items = []

    for bot, state in sorted(bots.items()):
        performance = _ese_v1_performance_component(bot, analytics_ranking.get(bot))
        components = {
            "capital_score": round(_ese_v1_component_capital(state.get("usage_pct"), state.get("positions")), 2),
            "risk_score": round(_ese_v1_component_risk(state.get("risk_usage_pct"), state.get("positions")), 2),
            "performance_score": round(performance.get("score", 50.0), 2),
            "concentration_score": round(_ese_v1_component_concentration(state), 2),
            "activity_score": round(_ese_v1_component_activity(state.get("positions"), state.get("category")), 2),
        }

        score = (
            components["performance_score"] * 0.35
            + components["risk_score"] * 0.25
            + components["capital_score"] * 0.20
            + components["concentration_score"] * 0.10
            + components["activity_score"] * 0.10
        )
        score = round(_ese_v1_clamp(score), 2)

        item = {
            "bot": bot,
            "score": score,
            "rating": _ese_v1_rating(score),
            "decision": _ese_v1_decision(score, state, performance),
            "category": state.get("category"),
            "status": state.get("status"),
            "positions": state.get("positions"),
            "capital_used": state.get("capital_used"),
            "capital_allocated": state.get("capital_allocated"),
            "usage_pct": state.get("usage_pct"),
            "risk_used_usdt": state.get("risk_used_usdt"),
            "max_open_risk_usdt": state.get("max_open_risk_usdt"),
            "risk_usage_pct": state.get("risk_usage_pct"),
            "net_direction": state.get("net_direction"),
            "largest_symbol": state.get("largest_symbol"),
            "largest_symbol_count": state.get("largest_symbol_count"),
            "components": components,
            "performance": performance,
            "reasons": _ese_v1_reasons(state, components, performance),
            "exposure_alerts": state.get("alerts") or [],
            "data_quality": state.get("data_quality") or {},
        }
        scored_bots[bot] = item
        ranking_items.append(item)

    ranking_items.sort(key=lambda item: (-item.get("score", 0), -int(item.get("positions", 0) or 0), item.get("bot")))

    active_items = [item for item in ranking_items if int(item.get("positions", 0) or 0) > 0]
    best_bot = ranking_items[0] if ranking_items else None
    weakest_active = sorted(active_items, key=lambda item: (item.get("score", 0), -int(item.get("positions", 0) or 0)))[0] if active_items else None

    category_summary = {}
    for item in ranking_items:
        cat = str(item.get("category") or "OTHER").upper()
        bucket = category_summary.setdefault(cat, {"bots": 0, "positions": 0, "avg_score": 0.0, "capital_used": 0.0, "risk_used_usdt": 0.0})
        bucket["bots"] += 1
        bucket["positions"] += int(item.get("positions", 0) or 0)
        bucket["avg_score"] += float(item.get("score", 0.0) or 0.0)
        bucket["capital_used"] += _bem_v2_float(item.get("capital_used"), 0.0)
        bucket["risk_used_usdt"] += _bem_v2_float(item.get("risk_used_usdt"), 0.0)
    for cat, bucket in category_summary.items():
        bucket["avg_score"] = round(bucket["avg_score"] / bucket["bots"], 2) if bucket.get("bots") else 0.0
        bucket["capital_used"] = round(bucket["capital_used"], 4)
        bucket["risk_used_usdt"] = round(bucket["risk_used_usdt"], 4)

    avg_score = round(sum(item.get("score", 0) for item in ranking_items) / len(ranking_items), 2) if ranking_items else 0.0
    active_avg_score = round(sum(item.get("score", 0) for item in active_items) / len(active_items), 2) if active_items else 0.0

    summary = {
        "bots": len(ranking_items),
        "active_bots": len(active_items),
        "avg_score": avg_score,
        "active_avg_score": active_avg_score,
        "best_bot": best_bot,
        "weakest_active_bot": weakest_active,
        "category_summary": category_summary,
        "exposure_summary": exposure.get("summary", {}),
    }

    payload = {
        "ok": True,
        "version": EXPOSURE_SCORE_ENGINE_V1_VERSION,
        "generated_at": data_hora_sp_str(),
        "mode": EXPOSURE_SCORE_ENGINE_V1_MODE,
        "capital": round(capital, 4),
        "summary": summary,
        "bots": scored_bots,
        "ranking": ranking_items,
        "inputs": {
            "exposure_version": exposure.get("version"),
            "analytics_loaded": analytics_error is None,
            "analytics_error": analytics_error,
        },
        "notes": [
            "Exposure Score Engine V1 está em modo consultivo/observação.",
            "Não altera lote, execução, risco real ou permissões de entrada.",
            "Combina Exposure Manager V2.1 com score estatístico do Analytics quando disponível.",
            "Quando não há estatística suficiente, usa score neutro de performance para evitar decisões agressivas.",
            "Preparado para alimentar Portfolio Advisor V1.",
        ],
    }

    with EXPOSURE_SCORE_ENGINE_V1_LOCK:
        EXPOSURE_SCORE_ENGINE_V1_CACHE["last_snapshot"] = payload
        EXPOSURE_SCORE_ENGINE_V1_CACHE["last_generated_at"] = payload.get("generated_at")
        EXPOSURE_SCORE_ENGINE_V1_CACHE["last_capital"] = payload.get("capital")

    return payload


def build_exposure_score_engine_v1_text(capital=10000.0, bot_filter=None):
    payload = build_exposure_score_engine_v1(capital=capital, bot_filter=bot_filter)
    summary = payload.get("summary", {})
    ranking = payload.get("ranking", [])
    exposure_summary = summary.get("exposure_summary", {}) or {}

    lines = [
        "🧠 EXPOSURE SCORE ENGINE V1 — CENTRAL QUANT",
        f"Data/hora: {payload.get('generated_at')}",
        f"Versão: {payload.get('version')}",
        f"Modo: {payload.get('mode')}",
        "",
        "Resumo geral:",
        f"Capital analisado: {payload.get('capital')} USDT",
        f"Robôs avaliados: {summary.get('bots')} | ativos: {summary.get('active_bots')}",
        f"Score médio geral: {summary.get('avg_score')}/100",
        f"Score médio dos ativos: {summary.get('active_avg_score')}/100",
        f"Posições: {exposure_summary.get('positions')} | LONG {exposure_summary.get('long')} | SHORT {exposure_summary.get('short')} | Net {exposure_summary.get('net_direction')}",
        f"Capital usado: {exposure_summary.get('capital_used')} USDT ({exposure_summary.get('capital_usage_pct')}%)",
        f"Risco aberto estimado: {exposure_summary.get('risk_used_usdt')} USDT",
        "",
        "Ranking por robô:",
    ]

    for i, item in enumerate(ranking, start=1):
        components = item.get("components") or {}
        perf = item.get("performance") or {}
        lines += [
            "",
            f"{i}. {item.get('bot')} — Score {item.get('score')}/100 ({item.get('rating')})",
            f"Decisão: {item.get('decision')}",
            f"Categoria: {item.get('category')} | Status: {item.get('status')}",
            f"Posições: {item.get('positions')} | Net {item.get('net_direction')} | Maior ativo: {item.get('largest_symbol')} ({item.get('largest_symbol_count')})",
            f"Capital: {item.get('capital_used')} / {item.get('capital_allocated')} USDT ({item.get('usage_pct')}%)",
            f"Risco: {item.get('risk_used_usdt')} / {item.get('max_open_risk_usdt')} USDT ({item.get('risk_usage_pct')}%)",
            f"Componentes: perf {components.get('performance_score')} | risco {components.get('risk_score')} | capital {components.get('capital_score')} | concentração {components.get('concentration_score')} | atividade {components.get('activity_score')}",
            f"Analytics: trades {perf.get('trades')} | win {perf.get('win_rate_pct')}% | pnl {perf.get('pnl_total_pct')}% | fonte {perf.get('source')}",
        ]
        reasons = item.get("reasons") or []
        if reasons:
            lines.append("Leitura:")
            for reason in reasons[:4]:
                lines.append(f"- {reason}")
        alerts = item.get("exposure_alerts") or []
        if alerts:
            lines.append("Alertas Exposure: " + ", ".join(alerts))

    lines += ["", "Notas:"]
    for note in payload.get("notes", []):
        lines.append(f"- {note}")

    return "\n".join(lines), payload


@app.route("/exposure/score/v1")
@app.route("/exposure/scores/v1")
@app.route("/score/exposure/v1")
@app.route("/analytics/exposure-score")
def exposure_score_engine_v1_route():
    capital = request.args.get("capital", default=10000, type=float)
    as_text = str(request.args.get("format", request.args.get("text", ""))).strip().lower() in {"1", "true", "yes", "sim", "on", "text", "txt"}
    text, payload = build_exposure_score_engine_v1_text(capital=capital)
    if as_text:
        return text
    return {"ok": True, "text": text, "payload": payload}


@app.route("/exposure/score/<bot>/v1")
@app.route("/score/exposure/<bot>/v1")
def exposure_score_engine_v1_bot_route(bot):
    capital = request.args.get("capital", default=10000, type=float)
    as_text = str(request.args.get("format", request.args.get("text", ""))).strip().lower() in {"1", "true", "yes", "sim", "on", "text", "txt"}
    text, payload = build_exposure_score_engine_v1_text(capital=capital, bot_filter=bot)
    if as_text:
        return text
    return {"ok": True, "text": text, "payload": payload}


@app.route("/exposure/score/summary/v1")
def exposure_score_engine_v1_summary_route():
    capital = request.args.get("capital", default=10000, type=float)
    payload = build_exposure_score_engine_v1(capital=capital)
    return {
        "ok": True,
        "version": payload.get("version"),
        "generated_at": payload.get("generated_at"),
        "mode": payload.get("mode"),
        "summary": payload.get("summary"),
        "ranking": payload.get("ranking"),
        "cache": {
            "last_generated_at": EXPOSURE_SCORE_ENGINE_V1_CACHE.get("last_generated_at"),
            "last_capital": EXPOSURE_SCORE_ENGINE_V1_CACHE.get("last_capital"),
        },
    }


# ==========================================================
# EXPOSURE SCORE ENGINE V2 - CENTRAL QUANT
# ==========================================================

EXPOSURE_SCORE_ENGINE_V2_VERSION = "2026-07-03-EXPOSURE-SCORE-ENGINE-V2"
EXPOSURE_SCORE_ENGINE_V2_MODE = os.environ.get("EXPOSURE_SCORE_ENGINE_V2_MODE", "OBSERVATION_ONLY").strip().upper()
EXPOSURE_SCORE_ENGINE_V2_CACHE = {
    "last_snapshot": None,
    "last_generated_at": None,
    "last_capital": None,
}
EXPOSURE_SCORE_ENGINE_V2_LOCK = threading.Lock()


def _ese_v2_clamp(value, minimum=0.0, maximum=100.0):
    try:
        value = float(value)
    except Exception:
        value = 0.0
    return max(float(minimum), min(float(maximum), value))


def _ese_v2_float_from_any(*values, default=0.0):
    for value in values:
        try:
            if value is None:
                continue
            return float(value)
        except Exception:
            continue
    return default


def _ese_v2_text_from_any(*values, default="N/A"):
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return default


def _ese_v2_confidence_score(performance):
    """Score de confiança estatística: amostra e rótulo de confiança pesam muito."""
    performance = performance or {}
    trades = int(_ese_v2_float_from_any(performance.get("trades"), default=0.0))
    confidence = str(performance.get("confidence") or "").upper()

    if trades <= 0:
        trade_score = 20.0
    elif trades < 5:
        trade_score = 35.0
    elif trades < 10:
        trade_score = 50.0
    elif trades < 20:
        trade_score = 65.0
    elif trades < 40:
        trade_score = 78.0
    elif trades < 80:
        trade_score = 88.0
    else:
        trade_score = 96.0

    label_score = 55.0
    if "ALTA" in confidence or "FORTE" in confidence:
        label_score = 90.0
    elif "MÉDIA" in confidence or "MEDIA" in confidence:
        label_score = 75.0
    elif "BAIXA" in confidence:
        label_score = 50.0
    elif "INSUFICIENTE" in confidence or "AMOSTRA" in confidence:
        label_score = 40.0
    elif "UNKNOWN" in confidence or not confidence:
        label_score = 45.0

    return round(_ese_v2_clamp((trade_score * 0.70) + (label_score * 0.30)), 2)


def _ese_v2_expectancy_score(performance, analytics_item=None):
    """Score de expectancy. Usa expectancy explícita se existir; senão usa PnL médio como proxy conservador."""
    performance = performance or {}
    analytics_item = analytics_item or {}

    expectancy = _ese_v2_float_from_any(
        analytics_item.get("expectancy_pct"),
        analytics_item.get("expectancy"),
        analytics_item.get("expectancy_r"),
        analytics_item.get("pnl_avg_pct"),
        performance.get("pnl_avg_pct"),
        default=0.0,
    )

    # Mapeamento conservador para pct por trade/proxy.
    if expectancy >= 1.00:
        score = 95.0
    elif expectancy >= 0.50:
        score = 85.0
    elif expectancy >= 0.20:
        score = 75.0
    elif expectancy >= 0.05:
        score = 65.0
    elif expectancy >= -0.05:
        score = 52.0
    elif expectancy >= -0.20:
        score = 40.0
    elif expectancy >= -0.50:
        score = 25.0
    else:
        score = 12.0

    return {
        "score": round(_ese_v2_clamp(score), 2),
        "expectancy_value": round(expectancy, 6),
        "source": "ANALYTICS_EXPECTANCY_OR_PNL_AVG_PROXY",
    }


def _ese_v2_drawdown_score(performance, analytics_item=None):
    """Score de drawdown. Se o Analytics ainda não trouxer DD, usa proxy neutro/conservador."""
    performance = performance or {}
    analytics_item = analytics_item or {}

    dd = _ese_v2_float_from_any(
        analytics_item.get("drawdown_pct"),
        analytics_item.get("max_drawdown_pct"),
        analytics_item.get("dd_pct"),
        analytics_item.get("drawdown"),
        default=None,
    )

    if dd is None:
        # Sem drawdown explícito: usa proxy suave por PnL total negativo.
        pnl_total = _ese_v2_float_from_any(performance.get("pnl_total_pct"), analytics_item.get("pnl_total_pct"), default=0.0)
        if pnl_total >= 0:
            return {"score": 65.0, "drawdown_pct": None, "source": "NEUTRAL_NO_DRAWDOWN_DATA"}
        proxy_dd = abs(pnl_total)
        source = "PNL_TOTAL_NEGATIVE_PROXY"
    else:
        proxy_dd = abs(dd)
        source = "ANALYTICS_DRAWDOWN"

    if proxy_dd <= 1:
        score = 95.0
    elif proxy_dd <= 3:
        score = 85.0
    elif proxy_dd <= 6:
        score = 70.0
    elif proxy_dd <= 10:
        score = 55.0
    elif proxy_dd <= 15:
        score = 35.0
    else:
        score = 15.0

    return {"score": round(_ese_v2_clamp(score), 2), "drawdown_pct": round(proxy_dd, 4), "source": source}


def _ese_v2_consistency_score(performance, analytics_item=None):
    """Score de consistência com base em win rate, PnL total, trades e sinais de estabilidade disponíveis."""
    performance = performance or {}
    analytics_item = analytics_item or {}

    explicit = _ese_v2_float_from_any(
        analytics_item.get("consistency_score"),
        analytics_item.get("stability_score"),
        analytics_item.get("consistencia_score"),
        default=None,
    )
    if explicit is not None:
        return {"score": round(_ese_v2_clamp(explicit), 2), "source": "ANALYTICS_CONSISTENCY"}

    trades = int(_ese_v2_float_from_any(performance.get("trades"), analytics_item.get("trades"), default=0.0))
    win_rate = _ese_v2_float_from_any(performance.get("win_rate_pct"), analytics_item.get("win_rate_pct"), default=0.0)
    pnl_total = _ese_v2_float_from_any(performance.get("pnl_total_pct"), analytics_item.get("pnl_total_pct"), default=0.0)
    pnl_avg = _ese_v2_float_from_any(performance.get("pnl_avg_pct"), analytics_item.get("pnl_avg_pct"), default=0.0)

    score = 50.0
    if trades >= 20:
        score += 12.0
    elif trades >= 10:
        score += 7.0
    elif trades < 5:
        score -= 8.0

    if win_rate >= 60:
        score += 13.0
    elif win_rate >= 50:
        score += 7.0
    elif win_rate >= 40:
        score += 0.0
    else:
        score -= 12.0

    if pnl_total > 5:
        score += 12.0
    elif pnl_total > 0:
        score += 6.0
    elif pnl_total < -5:
        score -= 15.0
    elif pnl_total < 0:
        score -= 7.0

    if pnl_avg > 0.2:
        score += 7.0
    elif pnl_avg > 0:
        score += 3.0
    elif pnl_avg < -0.2:
        score -= 8.0

    return {"score": round(_ese_v2_clamp(score), 2), "source": "DERIVED_FROM_WINRATE_PNL_TRADES"}


def _ese_v2_rating(score):
    score = float(score or 0.0)
    if score >= 85:
        return "EXCELLENT"
    if score >= 74:
        return "GOOD"
    if score >= 60:
        return "ATTENTION"
    if score >= 45:
        return "WEAK"
    return "CRITICAL"


def _ese_v2_decision(score, bot_state, performance, components):
    positions = int((bot_state or {}).get("positions", 0) or 0)
    usage_pct = _bem_v2_float((bot_state or {}).get("usage_pct"), 0.0)
    risk_usage_pct = _bem_v2_float((bot_state or {}).get("risk_usage_pct"), 0.0)
    confidence_score = _bem_v2_float((components or {}).get("confidence_score"), 0.0)
    drawdown_score = _bem_v2_float((components or {}).get("drawdown_score"), 0.0)
    expectancy_score = _bem_v2_float((components or {}).get("expectancy_score"), 0.0)
    recommendation = str((performance or {}).get("recommendation") or "").upper()

    if score >= 84 and confidence_score >= 70 and expectancy_score >= 65 and drawdown_score >= 60 and usage_pct < 85 and risk_usage_pct < 55 and positions > 0:
        return "SCALE_UP_OBSERVATION"
    if score >= 74 and risk_usage_pct < 75 and expectancy_score >= 50:
        return "MAINTAIN_OR_ALLOW_OBSERVATION"
    if score >= 60:
        if usage_pct >= 90:
            return "REDUCE_SIZE_OBSERVATION"
        return "MAINTAIN_OBSERVATION"
    if score >= 45:
        return "REDUCE_SIZE_OBSERVATION"
    if "PAUS" in recommendation or "AGUARD" in recommendation:
        return "PAUSE_OR_WAIT_SAMPLE_OBSERVATION"
    return "PAUSE_OR_REVIEW_OBSERVATION"


def _ese_v2_reasons(bot_state, components, performance, detail):
    reasons = _ese_v1_reasons(bot_state, components, performance) if callable(globals().get("_ese_v1_reasons")) else []
    detail = detail or {}
    confidence_score = _bem_v2_float((components or {}).get("confidence_score"), 0.0)
    expectancy_score = _bem_v2_float((components or {}).get("expectancy_score"), 0.0)
    drawdown_score = _bem_v2_float((components or {}).get("drawdown_score"), 0.0)
    consistency_score = _bem_v2_float((components or {}).get("consistency_score"), 0.0)

    if confidence_score < 55:
        reasons.append("Confiança estatística ainda baixa; evitar aumentar exposição agressivamente.")
    if expectancy_score >= 70:
        reasons.append("Expectancy/proxy positivo favorece manutenção ou aumento gradual.")
    elif expectancy_score < 45:
        reasons.append("Expectancy/proxy fraco exige redução ou espera por melhora.")
    if drawdown_score < 55:
        reasons.append("Drawdown/proxy de queda exige atenção antes de liberar mais capital.")
    if consistency_score < 55:
        reasons.append("Consistência operacional ainda fraca ou instável.")

    return reasons[:8]


def build_exposure_score_engine_v2(capital=10000.0, bot_filter=None):
    try:
        capital = float(capital or 0)
    except Exception:
        capital = 10000.0

    base = build_exposure_score_engine_v1(capital=capital, bot_filter=bot_filter)
    analytics_ranking, analytics_error = _ese_v1_load_analytics_ranking()

    scored_bots = {}
    ranking_items = []

    for base_item in base.get("ranking", []) or []:
        if not isinstance(base_item, dict):
            continue

        bot = normalize_registry_bot(base_item.get("bot") or "UNKNOWN")
        analytics_item = analytics_ranking.get(bot, {}) if isinstance(analytics_ranking, dict) else {}
        performance = dict(base_item.get("performance") or {})
        components_v1 = dict(base_item.get("components") or {})

        expectancy = _ese_v2_expectancy_score(performance, analytics_item)
        drawdown = _ese_v2_drawdown_score(performance, analytics_item)
        consistency = _ese_v2_consistency_score(performance, analytics_item)
        confidence_score = _ese_v2_confidence_score(performance)

        components = {
            "performance_score": round(_ese_v2_clamp(components_v1.get("performance_score", performance.get("score", 50.0))), 2),
            "risk_score": round(_ese_v2_clamp(components_v1.get("risk_score", 60.0)), 2),
            "capital_score": round(_ese_v2_clamp(components_v1.get("capital_score", 55.0)), 2),
            "concentration_score": round(_ese_v2_clamp(components_v1.get("concentration_score", 60.0)), 2),
            "activity_score": round(_ese_v2_clamp(components_v1.get("activity_score", 50.0)), 2),
            "drawdown_score": drawdown.get("score"),
            "expectancy_score": expectancy.get("score"),
            "consistency_score": consistency.get("score"),
            "confidence_score": confidence_score,
        }

        # V2 aumenta peso de qualidade estatística real e reduz risco de amostras pequenas dominarem.
        score = (
            components["performance_score"] * 0.24
            + components["expectancy_score"] * 0.16
            + components["confidence_score"] * 0.13
            + components["consistency_score"] * 0.12
            + components["drawdown_score"] * 0.10
            + components["risk_score"] * 0.10
            + components["capital_score"] * 0.07
            + components["concentration_score"] * 0.05
            + components["activity_score"] * 0.03
        )
        score = round(_ese_v2_clamp(score), 2)

        detail = {
            "expectancy": expectancy,
            "drawdown": drawdown,
            "consistency": consistency,
            "confidence_score_source": "TRADES_AND_CONFIDENCE_LABEL",
            "v1_score": base_item.get("score"),
            "v1_rating": base_item.get("rating"),
            "v1_decision": base_item.get("decision"),
        }

        item = dict(base_item)
        item.update({
            "score": score,
            "rating": _ese_v2_rating(score),
            "decision": _ese_v2_decision(score, base_item, performance, components),
            "components": components,
            "quality_detail": detail,
            "reasons": _ese_v2_reasons(base_item, components, performance, detail),
            "engine_upgrade": "V2_ADDS_DRAWDOWN_EXPECTANCY_CONSISTENCY_CONFIDENCE",
        })

        scored_bots[bot] = item
        ranking_items.append(item)

    ranking_items.sort(key=lambda item: (-item.get("score", 0), -int(item.get("positions", 0) or 0), item.get("bot")))

    active_items = [item for item in ranking_items if int(item.get("positions", 0) or 0) > 0]
    best_bot = ranking_items[0] if ranking_items else None
    weakest_active = sorted(active_items, key=lambda item: (item.get("score", 0), -int(item.get("positions", 0) or 0)))[0] if active_items else None

    category_summary = {}
    for item in ranking_items:
        cat = str(item.get("category") or "OTHER").upper()
        bucket = category_summary.setdefault(cat, {"bots": 0, "positions": 0, "avg_score": 0.0, "capital_used": 0.0, "risk_used_usdt": 0.0})
        bucket["bots"] += 1
        bucket["positions"] += int(item.get("positions", 0) or 0)
        bucket["avg_score"] += float(item.get("score", 0.0) or 0.0)
        bucket["capital_used"] += _bem_v2_float(item.get("capital_used"), 0.0)
        bucket["risk_used_usdt"] += _bem_v2_float(item.get("risk_used_usdt"), 0.0)
    for cat, bucket in category_summary.items():
        bucket["avg_score"] = round(bucket["avg_score"] / bucket["bots"], 2) if bucket.get("bots") else 0.0
        bucket["capital_used"] = round(bucket["capital_used"], 4)
        bucket["risk_used_usdt"] = round(bucket["risk_used_usdt"], 4)

    avg_score = round(sum(item.get("score", 0) for item in ranking_items) / len(ranking_items), 2) if ranking_items else 0.0
    active_avg_score = round(sum(item.get("score", 0) for item in active_items) / len(active_items), 2) if active_items else 0.0

    summary = {
        "bots": len(ranking_items),
        "active_bots": len(active_items),
        "avg_score": avg_score,
        "active_avg_score": active_avg_score,
        "best_bot": best_bot,
        "weakest_active_bot": weakest_active,
        "category_summary": category_summary,
        "exposure_summary": (base.get("summary", {}) or {}).get("exposure_summary", {}),
        "v1_comparison": {
            "v1_avg_score": (base.get("summary", {}) or {}).get("avg_score"),
            "v1_active_avg_score": (base.get("summary", {}) or {}).get("active_avg_score"),
        },
    }

    payload = {
        "ok": True,
        "version": EXPOSURE_SCORE_ENGINE_V2_VERSION,
        "generated_at": data_hora_sp_str(),
        "mode": EXPOSURE_SCORE_ENGINE_V2_MODE,
        "capital": round(capital, 4),
        "summary": summary,
        "bots": scored_bots,
        "ranking": ranking_items,
        "inputs": {
            "exposure_version": ((base.get("summary", {}) or {}).get("exposure_summary", {}) or {}).get("version"),
            "score_engine_v1_version": base.get("version"),
            "analytics_loaded": analytics_error is None,
            "analytics_error": analytics_error,
        },
        "notes": [
            "Exposure Score Engine V2 está em modo consultivo/observação.",
            "Não altera lote, execução, risco real ou permissões de entrada.",
            "Adiciona Drawdown Score, Expectancy Score, Consistency Score e Confidence Score ao V1.",
            "Quando drawdown ou consistência explícitos não existem, usa proxies conservadores baseados em PnL, win rate e amostra.",
            "Preparado para alimentar Portfolio Advisor V1 com score mais robusto.",
        ],
    }

    with EXPOSURE_SCORE_ENGINE_V2_LOCK:
        EXPOSURE_SCORE_ENGINE_V2_CACHE["last_snapshot"] = payload
        EXPOSURE_SCORE_ENGINE_V2_CACHE["last_generated_at"] = payload.get("generated_at")
        EXPOSURE_SCORE_ENGINE_V2_CACHE["last_capital"] = payload.get("capital")

    return payload


def build_exposure_score_engine_v2_text(capital=10000.0, bot_filter=None):
    payload = build_exposure_score_engine_v2(capital=capital, bot_filter=bot_filter)
    summary = payload.get("summary", {})
    ranking = payload.get("ranking", [])
    exposure_summary = summary.get("exposure_summary", {}) or {}

    lines = [
        "🧠 EXPOSURE SCORE ENGINE V2 — CENTRAL QUANT",
        f"Data/hora: {payload.get('generated_at')}",
        f"Versão: {payload.get('version')}",
        f"Modo: {payload.get('mode')}",
        "",
        "Resumo geral:",
        f"Capital analisado: {payload.get('capital')} USDT",
        f"Robôs avaliados: {summary.get('bots')} | ativos: {summary.get('active_bots')}",
        f"Score médio geral: {summary.get('avg_score')}/100",
        f"Score médio dos ativos: {summary.get('active_avg_score')}/100",
        f"V1 comparação: geral {summary.get('v1_comparison', {}).get('v1_avg_score')} | ativos {summary.get('v1_comparison', {}).get('v1_active_avg_score')}",
        f"Posições: {exposure_summary.get('positions')} | LONG {exposure_summary.get('long')} | SHORT {exposure_summary.get('short')} | Net {exposure_summary.get('net_direction')}",
        f"Capital usado: {exposure_summary.get('capital_used')} USDT ({exposure_summary.get('capital_usage_pct')}%)",
        f"Risco aberto estimado: {exposure_summary.get('risk_used_usdt')} USDT",
        "",
        "Ranking por robô:",
    ]

    for i, item in enumerate(ranking, start=1):
        components = item.get("components") or {}
        perf = item.get("performance") or {}
        detail = item.get("quality_detail") or {}
        expectancy = detail.get("expectancy") or {}
        drawdown = detail.get("drawdown") or {}
        consistency = detail.get("consistency") or {}
        lines += [
            "",
            f"{i}. {item.get('bot')} — Score {item.get('score')}/100 ({item.get('rating')})",
            f"Decisão: {item.get('decision')} | V1: {detail.get('v1_score')}/100 ({detail.get('v1_decision')})",
            f"Categoria: {item.get('category')} | Status: {item.get('status')}",
            f"Posições: {item.get('positions')} | Net {item.get('net_direction')} | Maior ativo: {item.get('largest_symbol')} ({item.get('largest_symbol_count')})",
            f"Capital: {item.get('capital_used')} / {item.get('capital_allocated')} USDT ({item.get('usage_pct')}%)",
            f"Risco: {item.get('risk_used_usdt')} / {item.get('max_open_risk_usdt')} USDT ({item.get('risk_usage_pct')}%)",
            "Componentes V2: "
            f"perf {components.get('performance_score')} | exp {components.get('expectancy_score')} | conf {components.get('confidence_score')} | "
            f"cons {components.get('consistency_score')} | DD {components.get('drawdown_score')} | risco {components.get('risk_score')} | capital {components.get('capital_score')}",
            f"Analytics: trades {perf.get('trades')} | win {perf.get('win_rate_pct')}% | pnl {perf.get('pnl_total_pct')}% | fonte {perf.get('source')}",
            f"Expectancy/proxy: {expectancy.get('expectancy_value')} | Drawdown/proxy: {drawdown.get('drawdown_pct')} | Consistência fonte: {consistency.get('source')}",
        ]
        reasons = item.get("reasons") or []
        if reasons:
            lines.append("Leitura:")
            for reason in reasons[:5]:
                lines.append(f"- {reason}")
        alerts = item.get("exposure_alerts") or []
        if alerts:
            lines.append("Alertas Exposure: " + ", ".join(alerts))

    lines += ["", "Notas:"]
    for note in payload.get("notes", []):
        lines.append(f"- {note}")

    return "\n".join(lines), payload


@app.route("/exposure/score/v2")
@app.route("/exposure/scores/v2")
@app.route("/score/exposure/v2")
@app.route("/analytics/exposure-score/v2")
def exposure_score_engine_v2_route():
    capital = request.args.get("capital", default=10000, type=float)
    as_text = str(request.args.get("format", request.args.get("text", ""))).strip().lower() in {"1", "true", "yes", "sim", "on", "text", "txt"}
    text, payload = build_exposure_score_engine_v2_text(capital=capital)
    if as_text:
        return text
    return {"ok": True, "text": text, "payload": payload}


@app.route("/exposure/score/<bot>/v2")
@app.route("/score/exposure/<bot>/v2")
def exposure_score_engine_v2_bot_route(bot):
    capital = request.args.get("capital", default=10000, type=float)
    as_text = str(request.args.get("format", request.args.get("text", ""))).strip().lower() in {"1", "true", "yes", "sim", "on", "text", "txt"}
    text, payload = build_exposure_score_engine_v2_text(capital=capital, bot_filter=bot)
    if as_text:
        return text
    return {"ok": True, "text": text, "payload": payload}


@app.route("/exposure/score/summary/v2")
def exposure_score_engine_v2_summary_route():
    capital = request.args.get("capital", default=10000, type=float)
    payload = build_exposure_score_engine_v2(capital=capital)
    return {
        "ok": True,
        "version": payload.get("version"),
        "generated_at": payload.get("generated_at"),
        "mode": payload.get("mode"),
        "summary": payload.get("summary"),
        "ranking": payload.get("ranking"),
        "cache": {
            "last_generated_at": EXPOSURE_SCORE_ENGINE_V2_CACHE.get("last_generated_at"),
            "last_capital": EXPOSURE_SCORE_ENGINE_V2_CACHE.get("last_capital"),
        },
    }


# ==========================================================
# PORTFOLIO ADVISOR V1 - CENTRAL QUANT
# ==========================================================

PORTFOLIO_ADVISOR_V1_VERSION = "2026-07-03-PORTFOLIO-ADVISOR-V1"
PORTFOLIO_ADVISOR_V1_MODE = "OBSERVATION_ONLY"
PORTFOLIO_ADVISOR_V1_CACHE = {
    "last_generated_at": None,
    "last_capital": None,
    "last_payload": None,
}


def _portfolio_advisor_live_context():
    """Contexto real da BingX, apenas consultivo."""
    payload = {
        "bingx_ready": None,
        "bingx_status": "UNKNOWN",
        "total_usdt": None,
        "free_usdt": None,
        "theoretical_new_orders": None,
        "real_trading_enabled": ENABLE_REAL_TRADING,
        "execution_mode": EXECUTION_MODE,
        "max_notional_usdt": REAL_TRADING_MAX_NOTIONAL_USDT,
        "live_positions": 0,
        "notes": [],
    }

    try:
        ready = bingx_ready_payload() if BINGX_READY_CHECK_ENABLED else {"ok": None, "status": "READY_CHECK_DISABLED"}
        bal = ready.get("balance") or {}
        free = safe_round(bal.get("free_usdt"), 4, None)
        total = safe_round(bal.get("total_usdt"), 4, None)
        capacity = int((free or 0) // REAL_TRADING_MAX_NOTIONAL_USDT) if REAL_TRADING_MAX_NOTIONAL_USDT > 0 and free is not None else 0
        live = _central_live_positions_payload()
        payload.update({
            "bingx_ready": ready.get("ok"),
            "bingx_status": ready.get("status"),
            "total_usdt": total,
            "free_usdt": free,
            "theoretical_new_orders": capacity,
            "live_positions": len(live) if isinstance(live, list) else 0,
        })
        if not ENABLE_REAL_TRADING:
            payload["notes"].append("Real trading bloqueado pela trava global ENABLE_REAL_TRADING=false.")
        if capacity <= 0:
            payload["notes"].append("Saldo livre/capacidade real insuficiente para novas ordens no notional atual.")
    except Exception as exc:
        payload["error"] = str(exc)
        payload["notes"].append("Não foi possível ler o contexto real da BingX; Advisor segue apenas consultivo/paper.")

    return payload


def _portfolio_advisor_action_for_bot(item, live_context=None):
    """Transforma score/exposure em recomendação consultiva por robô."""
    score = _safe_float(item.get("score"), 0.0)
    positions = int(item.get("positions") or 0)
    usage_pct = _safe_float(item.get("usage_pct"), 0.0)
    risk_usage_pct = _safe_float(item.get("risk_usage_pct"), 0.0)
    category = str(item.get("category") or "UNKNOWN").upper()
    rating = str(item.get("rating") or "UNKNOWN").upper()
    components = item.get("components") or {}
    confidence_score = _safe_float(components.get("confidence_score"), 50.0)
    expectancy_score = _safe_float(components.get("expectancy_score"), 50.0)
    consistency_score = _safe_float(components.get("consistency_score"), 50.0)
    perf_score = _safe_float(components.get("performance_score"), 50.0)
    exposure_alerts = item.get("exposure_alerts") or []

    action = "OBSERVE"
    priority = "MEDIUM"
    capital_bias = "NEUTRAL"
    risk_bias = "NEUTRAL"
    suggested_new_trade_policy = "ALLOW_SMALL_OR_NORMAL_PAPER"
    reasons = []

    if score >= 78 and expectancy_score >= 70 and consistency_score >= 70:
        action = "PRIORITIZE"
        priority = "HIGH"
        capital_bias = "FAVOR"
        risk_bias = "ALLOW_GRADUAL"
        suggested_new_trade_policy = "ALLOW_OR_MAINTAIN_PAPER"
        reasons.append("Score V2 alto com expectancy/consistência favoráveis; robô merece prioridade consultiva.")
    elif score >= 65:
        action = "MAINTAIN"
        priority = "MEDIUM"
        capital_bias = "NEUTRAL_TO_FAVOR"
        risk_bias = "CONTROLLED"
        suggested_new_trade_policy = "ALLOW_REDUCED_IF_CAPITAL_FULL"
        reasons.append("Score intermediário/positivo; manter em observação com controle de tamanho.")
    elif score >= 50:
        action = "REDUCE_OR_WAIT"
        priority = "LOW"
        capital_bias = "REDUCE"
        risk_bias = "CONSERVATIVE"
        suggested_new_trade_policy = "REDUCE_SIZE_OR_WAIT"
        reasons.append("Score ainda fraco/intermediário; evitar aumento de exposição até melhora estatística.")
    else:
        action = "PAUSE_OR_REVIEW"
        priority = "LOW"
        capital_bias = "DEFUND"
        risk_bias = "DEFENSIVE"
        suggested_new_trade_policy = "PAUSE_NEW_ENTRIES_OBSERVATION"
        reasons.append("Score baixo; revisar estratégia ou pausar novas entradas em modo consultivo.")

    if confidence_score < 50:
        if action == "PRIORITIZE":
            action = "MAINTAIN_SMALL_SAMPLE"
            priority = "MEDIUM"
            capital_bias = "NEUTRAL"
            suggested_new_trade_policy = "ALLOW_SMALL_SIZE_ONLY"
        reasons.append("Confiança estatística baixa; não aumentar capital de forma agressiva.")

    if usage_pct >= 95:
        if action in {"PRIORITIZE", "MAINTAIN"}:
            suggested_new_trade_policy = "REDUCE_SIZE_NEW_ENTRIES"
        reasons.append("Capital alocado já está praticamente cheio; novas entradas devem reduzir tamanho ou aguardar liberação.")

    if risk_usage_pct >= 80:
        action = "REDUCE_RISK"
        priority = "HIGH"
        risk_bias = "REDUCE"
        suggested_new_trade_policy = "BLOCK_OR_REDUCE_RISK_OBSERVATION"
        reasons.append("Uso de risco próximo do limite consultivo; priorizar redução de risco.")
    elif risk_usage_pct <= 25 and score >= 75:
        reasons.append("Risco usado ainda baixo; há margem consultiva, desde que capital/qualidade permitam.")

    if positions == 0 and score < 60:
        reasons.append("Robô sem posições abertas e score fraco; aguardar nova amostra antes de realocar capital.")

    if "CAPITAL_NEAR_LIMIT" in exposure_alerts:
        reasons.append("Exposure Manager marcou CAPITAL_NEAR_LIMIT.")

    if category == "EXPERIMENTAL" and confidence_score < 60:
        if action in {"PRIORITIZE", "MAINTAIN"}:
            action = "MAINTAIN_EXPERIMENTAL_SMALL"
            suggested_new_trade_policy = "ALLOW_SMALL_SIZE_ONLY"
        reasons.append("Categoria experimental com baixa confiança; manter lote pequeno até amadurecer amostra.")

    if live_context:
        capacity = live_context.get("theoretical_new_orders")
        real_enabled = bool(live_context.get("real_trading_enabled"))
        free_usdt = live_context.get("free_usdt")
        if (not real_enabled) or capacity == 0 or (free_usdt is not None and free_usdt < REAL_TRADING_MAX_NOTIONAL_USDT):
            reasons.append("Contexto real não permite aumento LIVE agora; recomendação vale para paper/observação.")

    return {
        "action": action,
        "priority": priority,
        "capital_bias": capital_bias,
        "risk_bias": risk_bias,
        "suggested_new_trade_policy": suggested_new_trade_policy,
        "reasons": reasons[:8],
    }


def _portfolio_advisor_build_reallocation(ranking):
    """Sugestão consultiva de redistribuição entre robôs."""
    donors = []
    receivers = []

    for item in ranking:
        score = _safe_float(item.get("score"), 0.0)
        usage_pct = _safe_float(item.get("usage_pct"), 0.0)
        cap_alloc = _safe_float(item.get("capital_allocated"), 0.0)
        positions = int(item.get("positions") or 0)
        action = str((item.get("advisor") or {}).get("action") or "").upper()

        if score < 55 and positions == 0 and cap_alloc > 0:
            donors.append({
                "bot": item.get("bot"),
                "score": score,
                "capital_allocated": cap_alloc,
                "reason": "score baixo/sem posição; possível fonte de capital consultivo.",
            })
        elif score >= 75 and usage_pct >= 90:
            receivers.append({
                "bot": item.get("bot"),
                "score": score,
                "capital_allocated": cap_alloc,
                "reason": "score alto e capital cheio; candidato a prioridade futura, não necessariamente aumento imediato.",
            })
        elif score >= 70 and action in {"PRIORITIZE", "MAINTAIN"}:
            receivers.append({
                "bot": item.get("bot"),
                "score": score,
                "capital_allocated": cap_alloc,
                "reason": "score favorável; candidato a receber alocação se houver folga.",
            })

    suggestions = []
    if donors and receivers:
        for receiver in receivers[:3]:
            suggestions.append({
                "to": receiver.get("bot"),
                "from_candidates": [d.get("bot") for d in donors[:4]],
                "type": "CONSULTATIVE_REALLOCATION_CANDIDATE",
                "reason": f"{receiver.get('bot')} tem score superior; doadores são robôs com score fraco/sem atividade.",
            })

    return {
        "donor_candidates": donors,
        "receiver_candidates": receivers,
        "suggestions": suggestions,
        "note": "Apenas consultivo. Não altera percentuais, lotes, risco ou execução.",
    }


def build_portfolio_advisor_v1(capital=10000.0, bot_filter=None):
    global PORTFOLIO_ADVISOR_V1_CACHE

    score_payload = build_exposure_score_engine_v2(capital=capital, bot_filter=bot_filter)
    live_context = _portfolio_advisor_live_context()
    ranking = []

    for raw in score_payload.get("ranking", []) or []:
        item = dict(raw)
        advisor = _portfolio_advisor_action_for_bot(item, live_context=live_context)
        item["advisor"] = advisor
        ranking.append(item)

    ranking = sorted(
        ranking,
        key=lambda x: (
            {"HIGH": 3, "MEDIUM": 2, "LOW": 1}.get(str((x.get("advisor") or {}).get("priority") or "LOW"), 1),
            _safe_float(x.get("score"), 0.0),
        ),
        reverse=True,
    )

    active = [x for x in ranking if int(x.get("positions") or 0) > 0]
    prioritize = [x for x in ranking if str((x.get("advisor") or {}).get("action") or "").upper() in {"PRIORITIZE", "MAINTAIN"}]
    reduce = [x for x in ranking if str((x.get("advisor") or {}).get("action") or "").upper() in {"REDUCE_OR_WAIT", "REDUCE_RISK", "PAUSE_OR_REVIEW"}]
    pause = [x for x in ranking if str((x.get("advisor") or {}).get("action") or "").upper() == "PAUSE_OR_REVIEW"]

    reallocation = _portfolio_advisor_build_reallocation(ranking)
    score_summary = score_payload.get("summary") or {}
    exposure_summary = score_summary.get("exposure_summary") or {}

    portfolio_state = "BALANCED_OBSERVATION"
    state_reasons = []
    if exposure_summary.get("net_direction") in {"LONG", "SHORT"}:
        portfolio_state = "DIRECTIONAL_EXPOSURE"
        state_reasons.append(f"Carteira paper está líquida {exposure_summary.get('net_direction')}.")
    if live_context.get("theoretical_new_orders") == 0:
        state_reasons.append("Capacidade LIVE teórica para novas ordens é zero no notional atual.")
    if pause:
        state_reasons.append(f"{len(pause)} robô(s) em PAUSE_OR_REVIEW consultivo.")
    if active:
        weakest_active = min(active, key=lambda x: _safe_float(x.get("score"), 0.0))
    else:
        weakest_active = None

    payload = {
        "ok": True,
        "version": PORTFOLIO_ADVISOR_V1_VERSION,
        "generated_at": data_hora_sp_str(),
        "mode": PORTFOLIO_ADVISOR_V1_MODE,
        "capital": float(capital or 0.0),
        "inputs": {
            "score_engine_version": score_payload.get("version"),
            "exposure_version": (score_summary.get("exposure_summary") or {}).get("version"),
            "analytics_loaded": (score_payload.get("inputs") or {}).get("analytics_loaded"),
        },
        "live_context": live_context,
        "portfolio_state": portfolio_state,
        "state_reasons": state_reasons,
        "summary": {
            "bots": len(ranking),
            "active_bots": len(active),
            "avg_score": score_summary.get("avg_score"),
            "active_avg_score": score_summary.get("active_avg_score"),
            "best_bot": ranking[0] if ranking else None,
            "weakest_active_bot": weakest_active,
            "prioritize_count": len(prioritize),
            "reduce_count": len(reduce),
            "pause_count": len(pause),
            "exposure_summary": exposure_summary,
            "category_summary": score_summary.get("category_summary"),
        },
        "ranking": ranking,
        "reallocation": reallocation,
        "notes": [
            "Portfolio Advisor V1 está em modo consultivo/observação.",
            "Não altera capital, lote, risco, permissões de entrada ou execução real.",
            "Usa Exposure Score Engine V2, Bot Exposure Manager V2.1, Analytics e contexto de capital real quando disponível.",
            "Recomenda priorização, manutenção, redução ou revisão por robô.",
            "Preparado para alimentar Portfolio Optimizer e Dynamic Risk Budget.",
        ],
    }

    PORTFOLIO_ADVISOR_V1_CACHE = {
        "last_generated_at": payload.get("generated_at"),
        "last_capital": capital,
        "last_payload": payload,
    }
    return payload


def build_portfolio_advisor_v1_text(capital=10000.0, bot_filter=None):
    payload = build_portfolio_advisor_v1(capital=capital, bot_filter=bot_filter)
    summary = payload.get("summary") or {}
    exposure = summary.get("exposure_summary") or {}
    live = payload.get("live_context") or {}

    lines = [
        "🧭 PORTFOLIO ADVISOR V1 — CENTRAL QUANT",
        f"Data/hora: {payload.get('generated_at')}",
        f"Versão: {payload.get('version')}",
        f"Modo: {payload.get('mode')}",
        "",
        "Resumo geral:",
        f"Capital analisado: {payload.get('capital')} USDT",
        f"Robôs avaliados: {summary.get('bots')} | ativos: {summary.get('active_bots')}",
        f"Score médio geral: {summary.get('avg_score')}/100 | ativos: {summary.get('active_avg_score')}/100",
        f"Estado do portfólio: {payload.get('portfolio_state')}",
        f"Posições paper: {exposure.get('positions')} | LONG {exposure.get('long')} | SHORT {exposure.get('short')} | Net {exposure.get('net_direction')}",
        f"Capital paper usado: {exposure.get('capital_used')} USDT ({exposure.get('capital_usage_pct')}%)",
        f"Risco aberto estimado: {exposure.get('risk_used_usdt')} USDT",
        "",
        "Contexto real/BingX:",
        f"READY: {live.get('bingx_ready')} | {live.get('bingx_status')}",
        f"Saldo USDT total/free: {live.get('total_usdt')} / {live.get('free_usdt')}",
        f"Capacidade teórica novas ordens: {live.get('theoretical_new_orders')}",
        f"Real trading: {'ATIVO' if live.get('real_trading_enabled') else 'BLOQUEADO'} | Modo {live.get('execution_mode')}",
        "",
    ]

    state_reasons = payload.get("state_reasons") or []
    if state_reasons:
        lines.append("Leitura do estado:")
        for reason in state_reasons:
            lines.append(f"- {reason}")
        lines.append("")

    lines.append("Ranking consultivo:")
    for i, item in enumerate(payload.get("ranking", []), start=1):
        adv = item.get("advisor") or {}
        perf = item.get("performance") or {}
        components = item.get("components") or {}
        lines += [
            "",
            f"{i}. {item.get('bot')} — Advisor: {adv.get('action')} | Prioridade {adv.get('priority')}",
            f"Score V2: {item.get('score')}/100 ({item.get('rating')}) | Categoria {item.get('category')}",
            f"Capital bias: {adv.get('capital_bias')} | Risk bias: {adv.get('risk_bias')}",
            f"Política novo trade: {adv.get('suggested_new_trade_policy')}",
            f"Posições: {item.get('positions')} | Net {item.get('net_direction')} | Capital {item.get('capital_used')}/{item.get('capital_allocated')} ({item.get('usage_pct')}%)",
            f"Risco: {item.get('risk_used_usdt')}/{item.get('max_open_risk_usdt')} ({item.get('risk_usage_pct')}%)",
            f"Componentes: perf {components.get('performance_score')} | exp {components.get('expectancy_score')} | conf {components.get('confidence_score')} | cons {components.get('consistency_score')} | DD {components.get('drawdown_score')}",
            f"Analytics: trades {perf.get('trades')} | win {perf.get('win_rate_pct')}% | pnl {perf.get('pnl_total_pct')}% | recomendação {perf.get('recommendation')}",
        ]
        reasons = adv.get("reasons") or []
        if reasons:
            lines.append("Motivos:")
            for reason in reasons[:6]:
                lines.append(f"- {reason}")

    realloc = payload.get("reallocation") or {}
    lines += ["", "Redistribuição consultiva:"]
    suggestions = realloc.get("suggestions") or []
    if suggestions:
        for s in suggestions[:5]:
            lines.append(f"- Priorizar {s.get('to')} usando como candidatos: {', '.join(s.get('from_candidates') or [])}. {s.get('reason')}")
    else:
        lines.append("- Nenhuma redistribuição clara agora; manter observação e aguardar mais dados.")

    donor_candidates = realloc.get("donor_candidates") or []
    receiver_candidates = realloc.get("receiver_candidates") or []
    lines.append(f"Candidatos a doar capital: {', '.join([d.get('bot') for d in donor_candidates]) if donor_candidates else 'nenhum'}")
    lines.append(f"Candidatos a receber prioridade: {', '.join([r.get('bot') for r in receiver_candidates]) if receiver_candidates else 'nenhum'}")

    lines += ["", "Notas:"]
    for note in payload.get("notes", []):
        lines.append(f"- {note}")

    return "\n".join(lines), payload


@app.route("/portfolio/advisor/v1")
@app.route("/portfolioadvisor/v1")
@app.route("/advisor/portfolio/v1")
@app.route("/portfolio/v1")
def portfolio_advisor_v1_route():
    capital = request.args.get("capital", default=10000, type=float)
    as_text = str(request.args.get("format", request.args.get("text", ""))).strip().lower() in {"1", "true", "yes", "sim", "on", "text", "txt"}
    text, payload = build_portfolio_advisor_v1_text(capital=capital)
    if as_text:
        return text
    return {"ok": True, "text": text, "payload": payload}


@app.route("/portfolio/advisor/<bot>/v1")
@app.route("/advisor/portfolio/<bot>/v1")
def portfolio_advisor_v1_bot_route(bot):
    capital = request.args.get("capital", default=10000, type=float)
    as_text = str(request.args.get("format", request.args.get("text", ""))).strip().lower() in {"1", "true", "yes", "sim", "on", "text", "txt"}
    text, payload = build_portfolio_advisor_v1_text(capital=capital, bot_filter=bot)
    if as_text:
        return text
    return {"ok": True, "text": text, "payload": payload}


@app.route("/portfolio/advisor/summary/v1")
@app.route("/portfolio/summary/v1")
def portfolio_advisor_v1_summary_route():
    capital = request.args.get("capital", default=10000, type=float)
    payload = build_portfolio_advisor_v1(capital=capital)
    return {
        "ok": True,
        "version": payload.get("version"),
        "generated_at": payload.get("generated_at"),
        "mode": payload.get("mode"),
        "portfolio_state": payload.get("portfolio_state"),
        "summary": payload.get("summary"),
        "live_context": payload.get("live_context"),
        "reallocation": payload.get("reallocation"),
        "ranking": payload.get("ranking"),
        "cache": {
            "last_generated_at": PORTFOLIO_ADVISOR_V1_CACHE.get("last_generated_at"),
            "last_capital": PORTFOLIO_ADVISOR_V1_CACHE.get("last_capital"),
        },
    }


# ==========================================================
# PORTFOLIO OPTIMIZER V1.1 - CENTRAL QUANT
# ==========================================================

PORTFOLIO_OPTIMIZER_V1_VERSION = "2026-07-03-PORTFOLIO-OPTIMIZER-V1.1"
PORTFOLIO_OPTIMIZER_V1_1_VERSION = PORTFOLIO_OPTIMIZER_V1_VERSION
PORTFOLIO_OPTIMIZER_V1_MODE = "OBSERVATION_ONLY"
PORTFOLIO_OPTIMIZER_V1_CACHE = {
    "last_generated_at": None,
    "last_capital": None,
    "last_payload": None,
}


def _optimizer_category_constraints(category):
    category = str(category or "UNKNOWN").upper().strip()
    constraints = {
        "CORE": {"min_pct": 0.0, "max_pct": 55.0, "note": "Core pode receber maior alocação quando score/confiança sustentam."},
        "TACTICAL": {"min_pct": 0.0, "max_pct": 12.0, "note": "Tático deve ser limitado até provar consistência."},
        "SATELLITE": {"min_pct": 0.0, "max_pct": 8.0, "note": "Satélite deve ficar menor e diversificador."},
        "EXPERIMENTAL": {"min_pct": 0.0, "max_pct": 5.0, "note": "Experimental deve ter teto rígido até amadurecer amostra."},
        "UNKNOWN": {"min_pct": 0.0, "max_pct": 8.0, "note": "Categoria desconhecida recebe teto conservador."},
    }
    return constraints.get(category, constraints["UNKNOWN"])


def _optimizer_current_pct(item, capital):
    try:
        return (_safe_float(item.get("capital_allocated"), 0.0) / float(capital or 1.0)) * 100.0
    except Exception:
        return 0.0


def _optimizer_action(item):
    return str(((item.get("advisor") or {}).get("action")) or "OBSERVE").upper().strip()


def _optimizer_max_target_pct(item, capital):
    """
    V1.1: o teto passa a obedecer primeiro a política do Advisor.
    - REDUCE_OR_WAIT nunca aumenta alocação: teto <= alocação atual.
    - PAUSE_OR_REVIEW fica em target mínimo defensivo.
    - MAINTAIN_EXPERIMENTAL_SMALL respeita teto rígido experimental.
    - PRIORITIZE pode receber excesso liberado, mas ainda com teto prudente.
    """
    category = str(item.get("category") or "UNKNOWN").upper().strip()
    action = _optimizer_action(item)
    score = _safe_float(item.get("score"), 0.0)
    current_pct = _optimizer_current_pct(item, capital)
    base_cap = _safe_float(_optimizer_category_constraints(category).get("max_pct"), 8.0)

    cap = base_cap

    if action == "PRIORITIZE":
        # Permite absorver excesso de robôs fracos, mas sem dominar 100% do portfólio.
        cap = 70.0 if category == "CORE" else min(base_cap * 1.5, 25.0)
    elif action == "MAINTAIN_EXPERIMENTAL_SMALL":
        cap = min(base_cap, 5.0)
    elif action == "REDUCE_OR_WAIT":
        # Regra crítica do V1.1: nunca aumentar robô em reduce/wait.
        cap = min(base_cap, current_pct)
    elif action in {"PAUSE_OR_REVIEW", "REDUCE_RISK"}:
        # Target mínimo defensivo, maior só se for necessário para fechar 100% em cenário extremo.
        if score < 40:
            cap = 1.5
        elif score < 50:
            cap = 2.5
        else:
            cap = 3.0
    else:
        if score < 45:
            cap = min(base_cap, 3.0)
        elif score < 55:
            cap = min(base_cap, 6.0)

    return max(0.0, round(cap, 6))


def _optimizer_health_multiplier(item):
    """Multiplicador conservador de elegibilidade com base em score, ação, confiança e consistência."""
    score = _safe_float(item.get("score"), 0.0)
    components = item.get("components") or {}
    confidence = _safe_float(components.get("confidence_score"), 50.0)
    consistency = _safe_float(components.get("consistency_score"), 50.0)
    expectancy = _safe_float(components.get("expectancy_score"), 50.0)
    action = _optimizer_action(item)
    category = str(item.get("category") or "UNKNOWN").upper()

    mult = 1.0

    if score >= 80:
        mult *= 1.25
    elif score >= 70:
        mult *= 1.08
    elif score < 45:
        mult *= 0.22
    elif score < 55:
        mult *= 0.45
    elif score < 60:
        mult *= 0.70

    if confidence < 40:
        mult *= 0.55
    elif confidence < 55:
        mult *= 0.75
    elif confidence >= 75:
        mult *= 1.10

    if consistency < 35:
        mult *= 0.55
    elif consistency < 55:
        mult *= 0.80
    elif consistency >= 80:
        mult *= 1.15

    if expectancy < 35:
        mult *= 0.45
    elif expectancy >= 75:
        mult *= 1.12

    if action in {"PAUSE_OR_REVIEW", "REDUCE_RISK"}:
        mult *= 0.12
    elif action == "REDUCE_OR_WAIT":
        mult *= 0.40
    elif action == "PRIORITIZE":
        mult *= 1.28
    elif action == "MAINTAIN_EXPERIMENTAL_SMALL":
        mult *= 0.70

    if category == "EXPERIMENTAL":
        mult *= 0.72
    elif category == "CORE" and action == "PRIORITIZE":
        mult *= 1.08

    return max(0.02, min(1.80, round(mult, 4)))


def _optimizer_raw_weight(item):
    score = _safe_float(item.get("score"), 0.0)
    components = item.get("components") or {}
    perf = _safe_float(components.get("performance_score"), score)
    expectancy = _safe_float(components.get("expectancy_score"), 50.0)
    confidence = _safe_float(components.get("confidence_score"), 50.0)
    consistency = _safe_float(components.get("consistency_score"), 50.0)
    risk = _safe_float(components.get("risk_score"), 50.0)
    positions = int(item.get("positions") or 0)

    quality = (
        score * 0.30
        + perf * 0.20
        + expectancy * 0.20
        + consistency * 0.15
        + confidence * 0.10
        + risk * 0.05
    )

    activity_factor = 1.00 if positions > 0 else 0.70
    health_factor = _optimizer_health_multiplier(item)
    return max(0.0, quality * activity_factor * health_factor)


def _optimizer_apply_policy_caps(weight_map, item_map, capital):
    """Normaliza pesos, aplica tetos do Advisor e fecha exatamente 100% em base não arredondada."""
    if not weight_map:
        return {}

    max_caps = {bot: _optimizer_max_target_pct(item_map.get(bot) or {}, capital) for bot in weight_map.keys()}
    min_floors = {bot: 0.0 for bot in weight_map.keys()}

    # Se todos os pesos forem zero, usa pesos iguais respeitando caps.
    if sum(max(0.0, v) for v in weight_map.values()) <= 0:
        weight_map = {bot: 1.0 for bot in weight_map.keys()}

    # Primeiro aloca proporcionalmente, travando quem ultrapassa o teto.
    remaining = set(weight_map.keys())
    fixed = {}
    weights = {bot: 0.0 for bot in weight_map.keys()}

    for _ in range(20):
        fixed_total = sum(fixed.values())
        rem_pct = max(0.0, 100.0 - fixed_total)
        rem_weight_total = sum(max(0.0, weight_map.get(bot, 0.0)) for bot in remaining)
        if not remaining or rem_pct <= 0:
            break
        if rem_weight_total <= 0:
            proposal = {bot: rem_pct / max(1, len(remaining)) for bot in remaining}
        else:
            proposal = {bot: (max(0.0, weight_map.get(bot, 0.0)) / rem_weight_total) * rem_pct for bot in remaining}

        changed = False
        for bot, pct in list(proposal.items()):
            cap = max_caps.get(bot, 100.0)
            if pct > cap:
                fixed[bot] = cap
                remaining.remove(bot)
                changed = True
        if not changed:
            for bot, pct in proposal.items():
                weights[bot] = pct
            break

    for bot, pct in fixed.items():
        weights[bot] = pct

    # Se os tetos somarem menos de 100, libera excesso apenas para PRIORITIZE; se ainda assim não der, para melhor score.
    total = sum(weights.values())
    if total < 99.999:
        deficit = 100.0 - total
        priority_bots = [bot for bot, item in item_map.items() if _optimizer_action(item) == "PRIORITIZE"]
        if not priority_bots:
            priority_bots = sorted(weight_map.keys(), key=lambda b: _safe_float((item_map.get(b) or {}).get("score"), 0.0), reverse=True)[:1]
        for bot in priority_bots:
            # Em exceção de fechamento de soma, PRIORITIZE pode absorver todo o déficit consultivo.
            weights[bot] = weights.get(bot, 0.0) + deficit / max(1, len(priority_bots))

    # Remove ruído e normaliza base não arredondada.
    total = sum(weights.values()) or 1.0
    weights = {bot: (pct / total) * 100.0 for bot, pct in weights.items()}
    return weights


def _optimizer_recommendation_for_bot(item, target_pct, capital):
    bot = item.get("bot")
    current_pct = _optimizer_current_pct(item, capital)
    current_capital = _safe_float(item.get("capital_allocated"), 0.0)
    target_capital = float(capital or 0.0) * float(target_pct or 0.0) / 100.0
    delta_pct = target_pct - current_pct
    delta_capital = target_capital - current_capital
    advisor = item.get("advisor") or {}
    action = _optimizer_action(item)
    score = _safe_float(item.get("score"), 0.0)
    category = str(item.get("category") or "UNKNOWN").upper()

    if action == "PAUSE_OR_REVIEW" or score < 45:
        recommendation = "DEFUND_OR_PAUSE_OBSERVATION"
    elif action == "REDUCE_OR_WAIT":
        if delta_pct < -1.0:
            recommendation = "DECREASE_ALLOCATION_OBSERVATION"
        else:
            recommendation = "HOLD_OR_WAIT_OBSERVATION"
    elif category == "EXPERIMENTAL" or action == "MAINTAIN_EXPERIMENTAL_SMALL":
        recommendation = "CAP_EXPERIMENTAL_OBSERVATION"
    elif delta_pct >= 3.0:
        recommendation = "INCREASE_ALLOCATION_OBSERVATION"
    elif delta_pct <= -3.0:
        recommendation = "DECREASE_ALLOCATION_OBSERVATION"
    else:
        recommendation = "KEEP_NEAR_CURRENT_OBSERVATION"

    reasons = []
    if recommendation.startswith("INCREASE"):
        reasons.append("Target otimizado acima da alocação atual por score/qualidade relativa e permitido pela política do Advisor.")
    elif recommendation.startswith("DECREASE"):
        reasons.append("Target otimizado abaixo da alocação atual por score, confiança, consistência ou política do Advisor.")
    elif recommendation.startswith("DEFUND"):
        reasons.append("Score/Advisor indicam pausa ou revisão; target foi reduzido para mínimo defensivo consultivo.")
    elif recommendation.startswith("HOLD"):
        reasons.append("Advisor indica reduzir/aguardar; V1.1 impede aumento e mantém no máximo próximo da alocação atual.")
    elif recommendation.startswith("CAP_EXPERIMENTAL"):
        reasons.append("Categoria experimental mantém teto rígido e lote pequeno até amadurecer amostra.")
    else:
        reasons.append("Alocação atual está próxima do target consultivo.")

    if action == "REDUCE_OR_WAIT":
        reasons.append("Regra V1.1: REDUCE_OR_WAIT nunca aumenta alocação.")
    if action == "PAUSE_OR_REVIEW":
        reasons.append("Regra V1.1: PAUSE_OR_REVIEW recebe apenas target mínimo defensivo.")
    if category == "EXPERIMENTAL":
        reasons.append("Regra V1.1: experimental respeita teto rígido de capital.")
    if _safe_float(item.get("usage_pct"), 0.0) >= 95:
        reasons.append("Robô está com capital alocado praticamente cheio; novas entradas devem respeitar redução de tamanho.")

    return {
        "bot": bot,
        "category": category,
        "score": round(score, 2),
        "advisor_action": action,
        "current_pct": round(current_pct, 2),
        "target_pct": round(target_pct, 2),
        "delta_pct": round(delta_pct, 2),
        "current_capital": round(current_capital, 4),
        "target_capital": round(target_capital, 4),
        "delta_capital": round(delta_capital, 4),
        "recommendation": recommendation,
        "priority": advisor.get("priority"),
        "new_trade_policy": advisor.get("suggested_new_trade_policy"),
        "reasons": reasons[:7],
    }


def _optimizer_adjust_rounded_targets(items, capital):
    """Ajusta target_pct arredondado para o total fechar em 100.00%."""
    if not items:
        return items
    total = round(sum(_safe_float(x.get("target_pct"), 0.0) for x in items), 2)
    residual = round(100.0 - total, 2)
    if abs(residual) >= 0.01:
        idx = 0
        for i, item in enumerate(items):
            if str(item.get("recommendation")) == "INCREASE_ALLOCATION_OBSERVATION":
                idx = i
                break
        items[idx]["target_pct"] = round(_safe_float(items[idx].get("target_pct"), 0.0) + residual, 2)
        items[idx]["target_capital"] = round(float(capital or 0.0) * items[idx]["target_pct"] / 100.0, 4)
        items[idx]["delta_pct"] = round(items[idx]["target_pct"] - _safe_float(items[idx].get("current_pct"), 0.0), 2)
        items[idx]["delta_capital"] = round(items[idx]["target_capital"] - _safe_float(items[idx].get("current_capital"), 0.0), 4)
    return items


def _optimizer_category_summary(items):
    out = {}
    for item in items:
        category = str(item.get("category") or "UNKNOWN").upper()
        bucket = out.setdefault(category, {"target_pct": 0.0, "current_pct": 0.0, "target_capital": 0.0, "current_capital": 0.0, "bots": 0})
        bucket["target_pct"] += _safe_float(item.get("target_pct"), 0.0)
        bucket["current_pct"] += _safe_float(item.get("current_pct"), 0.0)
        bucket["target_capital"] += _safe_float(item.get("target_capital"), 0.0)
        bucket["current_capital"] += _safe_float(item.get("current_capital"), 0.0)
        bucket["bots"] += 1
    for v in out.values():
        for k in ["target_pct", "current_pct", "target_capital", "current_capital"]:
            v[k] = round(v[k], 4 if "capital" in k else 2)
        v["delta_pct"] = round(v["target_pct"] - v["current_pct"], 2)
        v["delta_capital"] = round(v["target_capital"] - v["current_capital"], 4)
    return out


def build_portfolio_optimizer_v1(capital=10000.0, bot_filter=None):
    global PORTFOLIO_OPTIMIZER_V1_CACHE

    advisor_payload = build_portfolio_advisor_v1(capital=capital, bot_filter=bot_filter)
    ranking = advisor_payload.get("ranking") or []
    item_map = {str(item.get("bot") or "UNKNOWN").upper(): item for item in ranking}

    raw_weights = {}
    for item in ranking:
        bot = str(item.get("bot") or "UNKNOWN").upper()
        raw_weights[bot] = _optimizer_raw_weight(item)

    target_weights = _optimizer_apply_policy_caps(raw_weights, item_map, capital)
    optimized = []
    for bot, item in item_map.items():
        rec = _optimizer_recommendation_for_bot(item, target_weights.get(bot, 0.0), capital)
        optimized.append(rec)

    optimized = sorted(optimized, key=lambda x: (-_safe_float(x.get("target_pct"), 0.0), str(x.get("bot"))))
    optimized = _optimizer_adjust_rounded_targets(optimized, capital)

    total_target_pct = round(sum(_safe_float(x.get("target_pct"), 0.0) for x in optimized), 2)
    total_current_pct = round(sum(_safe_float(x.get("current_pct"), 0.0) for x in optimized), 2)
    increase = [x for x in optimized if str(x.get("recommendation") or "").startswith("INCREASE")]
    decrease = [x for x in optimized if str(x.get("recommendation") or "").startswith("DECREASE")]
    defund = [x for x in optimized if str(x.get("recommendation") or "").startswith("DEFUND")]
    hold_wait = [x for x in optimized if str(x.get("recommendation") or "").startswith("HOLD")]

    exposure = ((advisor_payload.get("summary") or {}).get("exposure_summary") or {})
    live_context = advisor_payload.get("live_context") or {}

    portfolio_alerts = []
    if exposure.get("net_direction") in {"LONG", "SHORT"}:
        portfolio_alerts.append(f"Carteira paper líquida {exposure.get('net_direction')}; optimizer recomenda observar concentração direcional.")
    if live_context.get("theoretical_new_orders") == 0:
        portfolio_alerts.append("Capacidade LIVE teórica zero; otimização é apenas paper/consultiva agora.")
    if defund:
        portfolio_alerts.append(f"{len(defund)} robô(s) com recomendação DEFUND/PAUSE consultiva.")
    if hold_wait:
        portfolio_alerts.append(f"{len(hold_wait)} robô(s) em HOLD/WAIT por política do Advisor; V1.1 impede aumento automático.")

    payload = {
        "ok": True,
        "version": PORTFOLIO_OPTIMIZER_V1_VERSION,
        "generated_at": data_hora_sp_str(),
        "mode": PORTFOLIO_OPTIMIZER_V1_MODE,
        "capital": float(capital or 0.0),
        "inputs": {
            "portfolio_advisor_version": advisor_payload.get("version"),
            "score_engine_version": (advisor_payload.get("inputs") or {}).get("score_engine_version"),
            "optimizer_basis": "advisor_policy_first_score_quality_with_caps_v1_1",
            "important_fix": "REDUCE_OR_WAIT never increases; PAUSE_OR_REVIEW defensive minimum; experimental hard cap; total closes at 100.00",
        },
        "summary": {
            "bots": len(optimized),
            "total_target_pct": total_target_pct,
            "total_current_pct": total_current_pct,
            "increase_count": len(increase),
            "decrease_count": len(decrease),
            "defund_count": len(defund),
            "hold_wait_count": len(hold_wait),
            "top_target_bot": optimized[0] if optimized else None,
            "category_summary": _optimizer_category_summary(optimized),
            "advisor_summary": advisor_payload.get("summary"),
            "portfolio_state": advisor_payload.get("portfolio_state"),
        },
        "optimized_allocation": optimized,
        "current_vs_target": optimized,
        "increase_candidates": increase,
        "decrease_candidates": decrease,
        "defund_candidates": defund,
        "hold_wait_candidates": hold_wait,
        "portfolio_alerts": portfolio_alerts,
        "live_context": live_context,
        "notes": [
            "Portfolio Optimizer V1.1 está em modo consultivo/observação.",
            "Não altera alocação real, lotes, risco, permissões de entrada ou execução.",
            "Correção V1.1: REDUCE_OR_WAIT nunca aumenta alocação.",
            "Correção V1.1: PAUSE_OR_REVIEW recebe target mínimo defensivo.",
            "Correção V1.1: robôs experimentais mantêm teto rígido conservador.",
            "Correção V1.1: o total alvo fecha em 100.00% após arredondamento.",
            "Preparado para alimentar Dynamic Risk Budget e futuras regras de rebalanceamento.",
        ],
    }

    PORTFOLIO_OPTIMIZER_V1_CACHE = {
        "last_generated_at": payload.get("generated_at"),
        "last_capital": capital,
        "last_payload": payload,
    }
    return payload


# Alias explícito para a versão corrigida.
def build_portfolio_optimizer_v1_1(capital=10000.0, bot_filter=None):
    return build_portfolio_optimizer_v1(capital=capital, bot_filter=bot_filter)


def build_portfolio_optimizer_v1_text(capital=10000.0, bot_filter=None):
    payload = build_portfolio_optimizer_v1(capital=capital, bot_filter=bot_filter)
    summary = payload.get("summary") or {}
    advisor_summary = summary.get("advisor_summary") or {}
    exposure = advisor_summary.get("exposure_summary") or {}
    live = payload.get("live_context") or {}

    lines = [
        "🧮 PORTFOLIO OPTIMIZER V1.1 — CENTRAL QUANT",
        f"Data/hora: {payload.get('generated_at')}",
        f"Versão: {payload.get('version')}",
        f"Modo: {payload.get('mode')}",
        "",
        "Resumo geral:",
        f"Capital analisado: {payload.get('capital')} USDT",
        f"Robôs otimizados: {summary.get('bots')}",
        f"Target total: {summary.get('total_target_pct')}% | Atual total: {summary.get('total_current_pct')}%",
        f"Aumentar: {summary.get('increase_count')} | Reduzir: {summary.get('decrease_count')} | Pausar/defund: {summary.get('defund_count')} | Hold/wait: {summary.get('hold_wait_count')}",
        f"Estado Advisor: {summary.get('portfolio_state')}",
        f"Paper: posições {exposure.get('positions')} | LONG {exposure.get('long')} | SHORT {exposure.get('short')} | Net {exposure.get('net_direction')}",
        f"Capital paper usado: {exposure.get('capital_used')} USDT ({exposure.get('capital_usage_pct')}%)",
        f"Risco aberto estimado: {exposure.get('risk_used_usdt')} USDT",
        "",
        "Contexto real/BingX:",
        f"READY: {live.get('bingx_ready')} | {live.get('bingx_status')}",
        f"Saldo total/free: {live.get('total_usdt')} / {live.get('free_usdt')} USDT",
        f"Capacidade teórica novas ordens: {live.get('theoretical_new_orders')}",
        f"Real trading: {'ATIVO' if live.get('real_trading_enabled') else 'BLOQUEADO'} | Modo {live.get('execution_mode')}",
        "",
    ]

    alerts = payload.get("portfolio_alerts") or []
    if alerts:
        lines.append("Alertas do otimizador:")
        for alert in alerts:
            lines.append(f"- {alert}")
        lines.append("")

    lines.append("Alocação ideal consultiva:")
    for i, item in enumerate(payload.get("optimized_allocation") or [], start=1):
        lines += [
            "",
            f"{i}. {item.get('bot')} — Target {item.get('target_pct')}% ({item.get('target_capital')} USDT)",
            f"Atual: {item.get('current_pct')}% ({item.get('current_capital')} USDT) | Δ {item.get('delta_pct')}% ({item.get('delta_capital')} USDT)",
            f"Score: {item.get('score')}/100 | Categoria: {item.get('category')} | Advisor: {item.get('advisor_action')}",
            f"Recomendação: {item.get('recommendation')}",
            f"Política novo trade: {item.get('new_trade_policy')}",
        ]
        reasons = item.get("reasons") or []
        if reasons:
            lines.append("Motivos:")
            for reason in reasons[:5]:
                lines.append(f"- {reason}")

    cat = summary.get("category_summary") or {}
    lines += ["", "Resumo por categoria:"]
    for category, data in sorted(cat.items()):
        lines.append(
            f"- {category}: target {data.get('target_pct')}% ({data.get('target_capital')} USDT) | "
            f"atual {data.get('current_pct')}% ({data.get('current_capital')} USDT) | Δ {data.get('delta_pct')}%"
        )

    lines += ["", "Notas:"]
    for note in payload.get("notes", []):
        lines.append(f"- {note}")

    return "\n".join(lines), payload


# Alias explícito para texto da versão corrigida.
def build_portfolio_optimizer_v1_1_text(capital=10000.0, bot_filter=None):
    return build_portfolio_optimizer_v1_text(capital=capital, bot_filter=bot_filter)


@app.route("/portfolio/optimizer/v1")
@app.route("/portfoliooptimizer/v1")
@app.route("/optimizer/portfolio/v1")
@app.route("/optimizer/v1")
@app.route("/portfolio/optimizer/v1.1")
@app.route("/portfoliooptimizer/v1.1")
@app.route("/optimizer/portfolio/v1.1")
@app.route("/optimizer/v1.1")
def portfolio_optimizer_v1_route():
    capital = request.args.get("capital", default=10000, type=float)
    as_text = str(request.args.get("format", request.args.get("text", ""))).strip().lower() in {"1", "true", "yes", "sim", "on", "text", "txt"}
    text, payload = build_portfolio_optimizer_v1_text(capital=capital)
    if as_text:
        return text
    return {"ok": True, "text": text, "payload": payload}


@app.route("/portfolio/optimizer/<bot>/v1")
@app.route("/optimizer/portfolio/<bot>/v1")
@app.route("/portfolio/optimizer/<bot>/v1.1")
@app.route("/optimizer/portfolio/<bot>/v1.1")
def portfolio_optimizer_v1_bot_route(bot):
    capital = request.args.get("capital", default=10000, type=float)
    as_text = str(request.args.get("format", request.args.get("text", ""))).strip().lower() in {"1", "true", "yes", "sim", "on", "text", "txt"}
    text, payload = build_portfolio_optimizer_v1_text(capital=capital, bot_filter=bot)
    if as_text:
        return text
    return {"ok": True, "text": text, "payload": payload}


@app.route("/portfolio/optimizer/summary/v1")
@app.route("/optimizer/summary/v1")
@app.route("/portfolio/optimizer/summary/v1.1")
@app.route("/optimizer/summary/v1.1")
def portfolio_optimizer_v1_summary_route():
    capital = request.args.get("capital", default=10000, type=float)
    payload = build_portfolio_optimizer_v1(capital=capital)
    return {
        "ok": True,
        "version": payload.get("version"),
        "generated_at": payload.get("generated_at"),
        "mode": payload.get("mode"),
        "summary": payload.get("summary"),
        "optimized_allocation": payload.get("optimized_allocation"),
        "increase_candidates": payload.get("increase_candidates"),
        "decrease_candidates": payload.get("decrease_candidates"),
        "defund_candidates": payload.get("defund_candidates"),
        "hold_wait_candidates": payload.get("hold_wait_candidates"),
        "portfolio_alerts": payload.get("portfolio_alerts"),
        "live_context": payload.get("live_context"),
        "cache": {
            "last_generated_at": PORTFOLIO_OPTIMIZER_V1_CACHE.get("last_generated_at"),
            "last_capital": PORTFOLIO_OPTIMIZER_V1_CACHE.get("last_capital"),
        },
    }






# ==========================================================
# DYNAMIC RISK BUDGET V1 - CENTRAL QUANT
# ==========================================================

DYNAMIC_RISK_BUDGET_V1_VERSION = "2026-07-04-DYNAMIC-RISK-BUDGET-V1"
DYNAMIC_RISK_BUDGET_V1_MODE = "OBSERVATION_ONLY"
DYNAMIC_RISK_BUDGET_V1_CACHE = {"last_payload": None, "last_generated_at": None, "last_capital": None}


def _drb_safe_float(value, default=0.0):
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _drb_clip(value, low, high):
    try:
        value = float(value)
    except Exception:
        value = low
    return max(float(low), min(float(high), value))


def _drb_round_pct(value, ndigits=2):
    return round(_drb_safe_float(value, 0.0), ndigits)


def _dynamic_risk_policy_for_bot(item, total_risk_budget_pct):
    """
    Traduz a alocação ideal do Portfolio Optimizer V1.1 em orçamento de risco.
    Continua consultivo: não altera lote, risco, capital ou execução real.
    """
    bot = str(item.get("bot") or "UNKNOWN").upper().strip()
    category = str(item.get("category") or "UNKNOWN").upper().strip()
    advisor_action = str(item.get("advisor_action") or "").upper().strip()
    recommendation = str(item.get("recommendation") or "").upper().strip()
    new_trade_policy = str(item.get("new_trade_policy") or "").upper().strip()
    score = _drb_safe_float(item.get("score"), 0.0)
    target_pct = _drb_safe_float(item.get("target_pct"), 0.0)
    current_pct = _drb_safe_float(item.get("current_pct"), 0.0)
    delta_pct = _drb_safe_float(item.get("delta_pct"), 0.0)

    base_budget_pct = (target_pct / 100.0) * float(total_risk_budget_pct)
    policy_multiplier = 1.0
    per_trade_cap_pct = 0.50
    min_per_trade_pct = 0.05
    max_open_trades = 3
    risk_state = "NORMAL"
    risk_action = "HOLD_RISK_BUDGET_OBSERVATION"
    reasons = []

    if advisor_action == "PRIORITIZE":
        policy_multiplier = 1.08
        per_trade_cap_pct = 0.75
        max_open_trades = 6
        risk_state = "PRIORITY"
        risk_action = "INCREASE_RISK_BUDGET_OBSERVATION" if delta_pct > 1 else "MAINTAIN_PRIORITY_RISK_OBSERVATION"
        reasons.append("Advisor prioriza o robô; orçamento de risco pode ser maior em modo consultivo.")
    elif advisor_action == "MAINTAIN_EXPERIMENTAL_SMALL" or category == "EXPERIMENTAL":
        policy_multiplier = 0.65
        per_trade_cap_pct = 0.25
        max_open_trades = 2
        risk_state = "EXPERIMENTAL_CAPPED"
        risk_action = "CAP_EXPERIMENTAL_RISK_OBSERVATION"
        reasons.append("Categoria experimental: risco por trade e risco total ficam limitados até amadurecer amostra.")
    elif advisor_action == "REDUCE_OR_WAIT":
        policy_multiplier = 0.50
        per_trade_cap_pct = 0.25
        max_open_trades = 2
        risk_state = "WAIT_REDUCED"
        risk_action = "REDUCE_OR_HOLD_RISK_OBSERVATION"
        reasons.append("Advisor indica reduzir/aguardar; V1 limita risco e impede expansão agressiva.")
    elif advisor_action == "PAUSE_OR_REVIEW" or "PAUSE" in recommendation:
        policy_multiplier = 0.20
        per_trade_cap_pct = 0.10
        max_open_trades = 1
        risk_state = "DEFENSIVE_MINIMUM"
        risk_action = "PAUSE_OR_MINIMUM_RISK_OBSERVATION"
        reasons.append("Advisor indica pausa/revisão; risco fica em mínimo defensivo consultivo.")
    else:
        reasons.append("Sem política especial; orçamento segue target do Portfolio Optimizer com limites conservadores.")

    if "REDUCE_SIZE" in new_trade_policy:
        per_trade_cap_pct = min(per_trade_cap_pct, 0.35)
        reasons.append("Política de novo trade exige redução de tamanho; limite por trade foi comprimido.")
    if "PAUSE" in new_trade_policy:
        per_trade_cap_pct = min(per_trade_cap_pct, 0.10)
        max_open_trades = min(max_open_trades, 1)
        reasons.append("Política de novo trade está em pausa; apenas orçamento defensivo de observação.")

    if score >= 80:
        reasons.append("Score alto permite orçamento acima da média, respeitando concentração e capital disponível.")
    elif score < 50:
        policy_multiplier *= 0.75
        reasons.append("Score abaixo de 50 reduz orçamento de risco calculado.")
    elif score < 60:
        policy_multiplier *= 0.90
        reasons.append("Score intermediário/fraco mantém orçamento conservador.")

    raw_budget_pct = base_budget_pct * policy_multiplier

    # Caps por categoria/política para evitar que o orçamento de risco fique agressivo demais.
    if advisor_action == "PRIORITIZE":
        max_budget_pct = 4.0
    elif category == "CORE":
        max_budget_pct = 2.0
    elif category == "TACTICAL":
        max_budget_pct = 0.75
    elif category == "SATELLITE":
        max_budget_pct = 0.60
    elif category == "EXPERIMENTAL":
        max_budget_pct = 0.50
    else:
        max_budget_pct = 0.75

    if advisor_action == "PAUSE_OR_REVIEW":
        max_budget_pct = min(max_budget_pct, 0.15)
    if advisor_action == "REDUCE_OR_WAIT":
        max_budget_pct = min(max_budget_pct, 0.60)
    if category == "EXPERIMENTAL":
        max_budget_pct = min(max_budget_pct, 0.35)

    min_budget_pct = 0.0 if target_pct <= 0 else 0.05
    budget_pct = _drb_clip(raw_budget_pct, min_budget_pct, max_budget_pct)

    # Risco por trade sugerido.
    if max_open_trades <= 0:
        max_open_trades = 1
    per_trade_pct = budget_pct / max_open_trades if max_open_trades else budget_pct
    per_trade_pct = _drb_clip(per_trade_pct, min_per_trade_pct if budget_pct > 0 else 0.0, per_trade_cap_pct)

    # Recalcula capacidade consultiva máxima com base no per_trade sugerido.
    if per_trade_pct > 0:
        suggested_max_open_trades = int(max(1, min(max_open_trades, budget_pct // per_trade_pct if budget_pct >= per_trade_pct else 1)))
    else:
        suggested_max_open_trades = 0

    if risk_action.startswith("INCREASE") and budget_pct <= 0.25:
        risk_action = "MAINTAIN_SMALL_RISK_OBSERVATION"
    if advisor_action == "PAUSE_OR_REVIEW":
        suggested_max_open_trades = min(suggested_max_open_trades, 1)

    return {
        "bot": bot,
        "category": category,
        "score": round(score, 2),
        "advisor_action": advisor_action,
        "optimizer_recommendation": recommendation,
        "new_trade_policy": new_trade_policy,
        "target_pct": round(target_pct, 2),
        "current_pct": round(current_pct, 2),
        "delta_pct": round(delta_pct, 2),
        "risk_state": risk_state,
        "risk_action": risk_action,
        "risk_budget_pct": round(budget_pct, 4),
        "risk_budget_usdt": None,
        "risk_per_trade_pct": round(per_trade_pct, 4),
        "risk_per_trade_usdt": None,
        "suggested_max_open_trades": int(suggested_max_open_trades),
        "raw_budget_pct": round(raw_budget_pct, 4),
        "base_budget_pct": round(base_budget_pct, 4),
        "policy_multiplier": round(policy_multiplier, 4),
        "max_budget_pct": round(max_budget_pct, 4),
        "per_trade_cap_pct": round(per_trade_cap_pct, 4),
        "reasons": reasons,
    }


def build_dynamic_risk_budget_v1(capital=10000.0, total_risk_budget_pct=None, bot_filter=None):
    global DYNAMIC_RISK_BUDGET_V1_CACHE

    capital = _drb_safe_float(capital, 10000.0)
    if total_risk_budget_pct is None:
        total_risk_budget_pct = _drb_safe_float(os.environ.get("DYNAMIC_RISK_TOTAL_BUDGET_PCT"), 6.0)
    total_risk_budget_pct = _drb_clip(total_risk_budget_pct, 0.5, 12.0)

    try:
        optimizer = build_portfolio_optimizer_v1(capital=capital)
    except Exception as exc:
        optimizer = {"ok": False, "error": str(exc), "optimized_allocation": [], "summary": {}, "live_context": {}}

    allocation = optimizer.get("optimized_allocation") or []
    if bot_filter:
        wanted = str(bot_filter).upper().strip()
        allocation = [x for x in allocation if str(x.get("bot") or "").upper().strip() == wanted]

    budgets = []
    total_budget_pct = 0.0
    total_budget_usdt = 0.0
    priority_count = 0
    defensive_count = 0
    capped_count = 0
    pause_count = 0

    for item in allocation:
        b = _dynamic_risk_policy_for_bot(item, total_risk_budget_pct)
        b["risk_budget_usdt"] = round((capital * b["risk_budget_pct"]) / 100.0, 4)
        b["risk_per_trade_usdt"] = round((capital * b["risk_per_trade_pct"]) / 100.0, 4)
        total_budget_pct += _drb_safe_float(b.get("risk_budget_pct"), 0.0)
        total_budget_usdt += _drb_safe_float(b.get("risk_budget_usdt"), 0.0)
        if b.get("risk_state") == "PRIORITY":
            priority_count += 1
        if b.get("risk_state") in {"DEFENSIVE_MINIMUM", "WAIT_REDUCED"}:
            defensive_count += 1
        if b.get("risk_state") == "EXPERIMENTAL_CAPPED":
            capped_count += 1
        if b.get("advisor_action") == "PAUSE_OR_REVIEW":
            pause_count += 1
        budgets.append(b)

    budgets = sorted(budgets, key=lambda x: (-_drb_safe_float(x.get("risk_budget_pct"), 0), -_drb_safe_float(x.get("score"), 0), str(x.get("bot"))))

    live_context = optimizer.get("live_context") or {}
    exposure_summary = ((optimizer.get("summary") or {}).get("advisor_summary") or {}).get("exposure_summary") or {}

    alerts = []
    if (exposure_summary.get("net_direction") or "") in {"LONG", "SHORT"}:
        alerts.append(f"Carteira paper líquida {exposure_summary.get('net_direction')}; risco dinâmico deve observar concentração direcional.")
    if not bool(live_context.get("real_trading_enabled")):
        alerts.append("Real trading bloqueado; orçamento de risco é consultivo/paper neste momento.")
    if _drb_safe_float(live_context.get("theoretical_new_orders"), 0) <= 0:
        alerts.append("Capacidade LIVE teórica zero no notional atual; não aumentar risco real agora.")
    if pause_count:
        alerts.append(f"{pause_count} robô(s) em PAUSE_OR_REVIEW com orçamento mínimo defensivo.")

    category_summary = {}
    for b in budgets:
        cat = b.get("category") or "UNKNOWN"
        category_summary.setdefault(cat, {"bots": 0, "risk_budget_pct": 0.0, "risk_budget_usdt": 0.0, "target_pct": 0.0})
        category_summary[cat]["bots"] += 1
        category_summary[cat]["risk_budget_pct"] += _drb_safe_float(b.get("risk_budget_pct"), 0.0)
        category_summary[cat]["risk_budget_usdt"] += _drb_safe_float(b.get("risk_budget_usdt"), 0.0)
        category_summary[cat]["target_pct"] += _drb_safe_float(b.get("target_pct"), 0.0)
    for cat, data in category_summary.items():
        data["risk_budget_pct"] = round(data["risk_budget_pct"], 4)
        data["risk_budget_usdt"] = round(data["risk_budget_usdt"], 4)
        data["target_pct"] = round(data["target_pct"], 2)

    payload = {
        "ok": True,
        "version": DYNAMIC_RISK_BUDGET_V1_VERSION,
        "generated_at": data_hora_sp_str(),
        "mode": DYNAMIC_RISK_BUDGET_V1_MODE,
        "capital": capital,
        "total_risk_budget_pct_configured": round(total_risk_budget_pct, 4),
        "total_risk_budget_usdt_configured": round((capital * total_risk_budget_pct) / 100.0, 4),
        "total_risk_budget_pct_allocated": round(total_budget_pct, 4),
        "total_risk_budget_usdt_allocated": round(total_budget_usdt, 4),
        "budgets": budgets,
        "summary": {
            "bots": len(budgets),
            "priority_count": priority_count,
            "defensive_count": defensive_count,
            "experimental_capped_count": capped_count,
            "pause_count": pause_count,
            "top_risk_bot": budgets[0] if budgets else None,
            "category_summary": category_summary,
            "portfolio_state": (optimizer.get("summary") or {}).get("portfolio_state") or ((optimizer.get("summary") or {}).get("advisor_summary") or {}).get("portfolio_state"),
            "optimizer_version": optimizer.get("version"),
            "exposure_summary": exposure_summary,
        },
        "live_context": live_context,
        "optimizer_summary": optimizer.get("summary"),
        "alerts": alerts,
        "inputs": {
            "optimizer_version": optimizer.get("version"),
            "optimizer_basis": (optimizer.get("inputs") or {}).get("optimizer_basis"),
            "total_risk_budget_pct_source": "DYNAMIC_RISK_TOTAL_BUDGET_PCT env or default 6.0",
        },
        "notes": [
            "Dynamic Risk Budget V1 está em modo consultivo/observação.",
            "Não altera risco real, lote, capital, permissões de entrada ou execução.",
            "Converte a alocação ideal do Portfolio Optimizer V1.1 em orçamento de risco por robô.",
            "Aplica limites por política do Advisor: PRIORITIZE, REDUCE_OR_WAIT, PAUSE_OR_REVIEW e experimental.",
            "Preparado para alimentar Dynamic Position Sizing, Risk Manager decisório e OMS futuro.",
        ],
    }

    DYNAMIC_RISK_BUDGET_V1_CACHE = {
        "last_payload": payload,
        "last_generated_at": payload.get("generated_at"),
        "last_capital": capital,
        "last_total_risk_budget_pct": total_risk_budget_pct,
    }
    return payload


def build_dynamic_risk_budget_v1_text(capital=10000.0, total_risk_budget_pct=None, bot_filter=None):
    payload = build_dynamic_risk_budget_v1(capital=capital, total_risk_budget_pct=total_risk_budget_pct, bot_filter=bot_filter)
    summary = payload.get("summary") or {}
    exposure = summary.get("exposure_summary") or {}
    live = payload.get("live_context") or {}

    lines = [
        "🎚️ DYNAMIC RISK BUDGET V1 — CENTRAL QUANT",
        f"Data/hora: {payload.get('generated_at')}",
        f"Versão: {payload.get('version')}",
        f"Modo: {payload.get('mode')}",
        "",
        "Resumo geral:",
        f"Capital analisado: {payload.get('capital')} USDT",
        f"Risk budget configurado: {payload.get('total_risk_budget_pct_configured')}% ({payload.get('total_risk_budget_usdt_configured')} USDT)",
        f"Risk budget alocado: {payload.get('total_risk_budget_pct_allocated')}% ({payload.get('total_risk_budget_usdt_allocated')} USDT)",
        f"Robôs avaliados: {summary.get('bots')} | prioridade: {summary.get('priority_count')} | defensivos: {summary.get('defensive_count')} | experimentais capped: {summary.get('experimental_capped_count')}",
        f"Paper: posições {exposure.get('positions')} | LONG {exposure.get('long')} | SHORT {exposure.get('short')} | Net {exposure.get('net_direction')}",
        f"Capital paper usado: {exposure.get('capital_used')} USDT ({exposure.get('capital_usage_pct')}%)",
        f"Risco aberto estimado: {exposure.get('risk_used_usdt')} USDT",
        "",
        "Contexto real/BingX:",
        f"READY: {live.get('bingx_ready')} | {live.get('bingx_status')}",
        f"Saldo total/free: {live.get('total_usdt')} / {live.get('free_usdt')} USDT",
        f"Capacidade teórica novas ordens: {live.get('theoretical_new_orders')}",
        f"Real trading: {'LIBERADO' if live.get('real_trading_enabled') else 'BLOQUEADO'} | Modo {live.get('execution_mode')}",
    ]

    alerts = payload.get("alerts") or []
    if alerts:
        lines += ["", "Alertas do orçamento dinâmico:"]
        for alert in alerts:
            lines.append(f"- {alert}")

    lines += ["", "Orçamento de risco por robô:"]
    for idx, b in enumerate(payload.get("budgets") or [], start=1):
        lines += [
            "",
            f"{idx}. {b.get('bot')} — {b.get('risk_state')}",
            f"Risk budget: {b.get('risk_budget_pct')}% ({b.get('risk_budget_usdt')} USDT)",
            f"Risco por trade sugerido: {b.get('risk_per_trade_pct')}% ({b.get('risk_per_trade_usdt')} USDT)",
            f"Máx. trades simultâneos sugerido: {b.get('suggested_max_open_trades')}",
            f"Score: {b.get('score')}/100 | Categoria: {b.get('category')} | Advisor: {b.get('advisor_action')}",
            f"Target capital: {b.get('target_pct')}% | Atual: {b.get('current_pct')}% | Δ {b.get('delta_pct')}%",
            f"Ação de risco: {b.get('risk_action')}",
            f"Política novo trade: {b.get('new_trade_policy')}",
            "Motivos:",
        ]
        for reason in b.get("reasons", [])[:5]:
            lines.append(f"- {reason}")

    cat = summary.get("category_summary") or {}
    if cat:
        lines += ["", "Resumo por categoria:"]
        for category, data in sorted(cat.items()):
            lines.append(
                f"- {category}: risk budget {data.get('risk_budget_pct')}% ({data.get('risk_budget_usdt')} USDT) | "
                f"target capital {data.get('target_pct')}% | bots {data.get('bots')}"
            )

    lines += ["", "Notas:"]
    for note in payload.get("notes", []):
        lines.append(f"- {note}")

    return "\n".join(lines), payload


@app.route("/dynamic/risk/budget/v1")
@app.route("/dynamic-risk-budget/v1")
@app.route("/risk/budget/v1")
@app.route("/riskbudget/v1")
@app.route("/dynamicrisk/v1")
def dynamic_risk_budget_v1_route():
    capital = request.args.get("capital", default=10000, type=float)
    total_risk = request.args.get("risk", default=None, type=float)
    as_text = str(request.args.get("format", request.args.get("text", ""))).strip().lower() in {"1", "true", "yes", "sim", "on", "text", "txt"}
    text, payload = build_dynamic_risk_budget_v1_text(capital=capital, total_risk_budget_pct=total_risk)
    if as_text:
        return text
    return {"ok": True, "text": text, "payload": payload}


@app.route("/dynamic/risk/budget/<bot>/v1")
@app.route("/risk/budget/<bot>/v1")
@app.route("/riskbudget/<bot>/v1")
def dynamic_risk_budget_v1_bot_route(bot):
    capital = request.args.get("capital", default=10000, type=float)
    total_risk = request.args.get("risk", default=None, type=float)
    as_text = str(request.args.get("format", request.args.get("text", ""))).strip().lower() in {"1", "true", "yes", "sim", "on", "text", "txt"}
    text, payload = build_dynamic_risk_budget_v1_text(capital=capital, total_risk_budget_pct=total_risk, bot_filter=bot)
    if as_text:
        return text
    return {"ok": True, "text": text, "payload": payload}


@app.route("/dynamic/risk/budget/summary/v1")
@app.route("/risk/budget/summary/v1")
@app.route("/riskbudget/summary/v1")
def dynamic_risk_budget_v1_summary_route():
    capital = request.args.get("capital", default=10000, type=float)
    total_risk = request.args.get("risk", default=None, type=float)
    payload = build_dynamic_risk_budget_v1(capital=capital, total_risk_budget_pct=total_risk)
    return {
        "ok": True,
        "version": payload.get("version"),
        "generated_at": payload.get("generated_at"),
        "mode": payload.get("mode"),
        "capital": payload.get("capital"),
        "total_risk_budget_pct_configured": payload.get("total_risk_budget_pct_configured"),
        "total_risk_budget_usdt_configured": payload.get("total_risk_budget_usdt_configured"),
        "total_risk_budget_pct_allocated": payload.get("total_risk_budget_pct_allocated"),
        "total_risk_budget_usdt_allocated": payload.get("total_risk_budget_usdt_allocated"),
        "summary": payload.get("summary"),
        "budgets": payload.get("budgets"),
        "alerts": payload.get("alerts"),
        "live_context": payload.get("live_context"),
        "cache": {
            "last_generated_at": DYNAMIC_RISK_BUDGET_V1_CACHE.get("last_generated_at"),
            "last_capital": DYNAMIC_RISK_BUDGET_V1_CACHE.get("last_capital"),
            "last_total_risk_budget_pct": DYNAMIC_RISK_BUDGET_V1_CACHE.get("last_total_risk_budget_pct"),
        },
    }


# ==========================================================
# DYNAMIC POSITION SIZING V1 - CENTRAL QUANT
# ==========================================================

DYNAMIC_POSITION_SIZING_V1_VERSION = "2026-07-04-DYNAMIC-POSITION-SIZING-V1"
DYNAMIC_POSITION_SIZING_V1_MODE = "OBSERVATION_ONLY"
DYNAMIC_POSITION_SIZING_V1_CACHE = {"last_payload": None, "last_generated_at": None, "last_capital": None}


def _dps_safe_float(value, default=0.0):
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _dps_clip(value, low, high):
    try:
        value = float(value)
    except Exception:
        value = low
    return max(float(low), min(float(high), value))


def _dps_normalize_side(side):
    s = str(side or "").upper().strip()
    if s == "BUY":
        return "LONG"
    if s == "SELL":
        return "SHORT"
    if s not in {"LONG", "SHORT"}:
        return None
    return s


def _dps_stop_distance_pct(entry=None, stop=None, default_pct=None):
    default_pct = _dps_safe_float(default_pct, _dps_safe_float(os.environ.get("DYNAMIC_POSITION_DEFAULT_STOP_PCT"), 2.0))
    entry_f = _dps_safe_float(entry, 0.0)
    stop_f = _dps_safe_float(stop, 0.0)
    if entry_f > 0 and stop_f > 0:
        return round(abs(entry_f - stop_f) / entry_f * 100.0, 4), "ENTRY_STOP"
    return round(_dps_clip(default_pct, 0.10, 20.0), 4), "DEFAULT_STOP_DISTANCE"


def _dps_live_caps(live_context):
    live_context = live_context or {}
    max_notional = _dps_safe_float(live_context.get("max_notional_usdt"), REAL_TRADING_MAX_NOTIONAL_USDT if "REAL_TRADING_MAX_NOTIONAL_USDT" in globals() else 60.0)
    free_usdt = _dps_safe_float(live_context.get("free_usdt"), 0.0)
    real_enabled = bool(live_context.get("real_trading_enabled"))
    theoretical_orders = _dps_safe_float(live_context.get("theoretical_new_orders"), 0.0)
    return {
        "max_notional_usdt": max_notional,
        "free_usdt": free_usdt,
        "real_trading_enabled": real_enabled,
        "theoretical_new_orders": theoretical_orders,
    }


def _dynamic_position_size_for_budget(budget, capital, entry=None, stop=None, side=None, leverage=None, live_context=None):
    bot = str(budget.get("bot") or "UNKNOWN").upper().strip()
    side_norm = _dps_normalize_side(side)
    leverage = int(_dps_clip(_dps_safe_float(leverage, DEFAULT_REAL_LEVERAGE if "DEFAULT_REAL_LEVERAGE" in globals() else 3), 1, 50))
    risk_usdt = _dps_safe_float(budget.get("risk_per_trade_usdt"), 0.0)
    risk_pct = _dps_safe_float(budget.get("risk_per_trade_pct"), 0.0)
    risk_budget_usdt = _dps_safe_float(budget.get("risk_budget_usdt"), 0.0)
    risk_state = str(budget.get("risk_state") or "UNKNOWN").upper().strip()
    new_trade_policy = str(budget.get("new_trade_policy") or "").upper().strip()
    advisor_action = str(budget.get("advisor_action") or "").upper().strip()
    score = _dps_safe_float(budget.get("score"), 0.0)

    stop_distance_pct, stop_distance_source = _dps_stop_distance_pct(entry=entry, stop=stop)
    risk_fraction = max(stop_distance_pct / 100.0, 0.0001)
    raw_notional = risk_usdt / risk_fraction if risk_usdt > 0 else 0.0
    raw_margin = raw_notional / leverage if leverage > 0 else raw_notional

    live_caps = _dps_live_caps(live_context)
    max_notional_env = _dps_safe_float(os.environ.get("DYNAMIC_POSITION_MAX_NOTIONAL_USDT"), 0.0)
    max_margin_env = _dps_safe_float(os.environ.get("DYNAMIC_POSITION_MAX_MARGIN_USDT"), 0.0)
    min_notional = _dps_safe_float(os.environ.get("DYNAMIC_POSITION_MIN_NOTIONAL_USDT"), 10.0)

    # Limites consultivos por política. Em modo paper, ainda usamos esses limites para evitar sugestões absurdas.
    policy_notional_cap = None
    if risk_state == "PRIORITY":
        policy_notional_cap = max_notional_env if max_notional_env > 0 else 300.0
    elif risk_state == "EXPERIMENTAL_CAPPED":
        policy_notional_cap = 80.0
    elif risk_state == "WAIT_REDUCED":
        policy_notional_cap = 120.0
    elif risk_state == "DEFENSIVE_MINIMUM" or advisor_action == "PAUSE_OR_REVIEW" or "PAUSE" in new_trade_policy:
        policy_notional_cap = 30.0
    else:
        policy_notional_cap = 150.0

    if max_notional_env > 0:
        policy_notional_cap = min(policy_notional_cap, max_notional_env)

    suggested_notional = min(raw_notional, policy_notional_cap) if raw_notional > 0 else 0.0
    if 0 < suggested_notional < min_notional and not ("PAUSE" in new_trade_policy or risk_state == "DEFENSIVE_MINIMUM"):
        suggested_notional = min_notional

    suggested_margin = suggested_notional / leverage if leverage > 0 else suggested_notional
    if max_margin_env > 0 and suggested_margin > max_margin_env:
        suggested_margin = max_margin_env
        suggested_notional = suggested_margin * leverage

    # LIVE cap: se não há capacidade real, não sugerir execução real; manter apenas sizing paper.
    live_notional_cap = live_caps.get("max_notional_usdt") or 0.0
    live_suggested_notional = min(suggested_notional, live_notional_cap) if live_notional_cap > 0 else suggested_notional
    live_suggested_margin = live_suggested_notional / leverage if leverage > 0 else live_suggested_notional

    if not live_caps.get("real_trading_enabled") or live_caps.get("theoretical_new_orders", 0) <= 0:
        live_allowed = False
        live_block_reason = "REAL_TRADING_BLOCKED_OR_NO_CAPACITY"
        live_suggested_notional = 0.0
        live_suggested_margin = 0.0
    else:
        live_allowed = True
        live_block_reason = None

    # Recalcula risco efetivo da sugestão paper após caps.
    effective_risk_usdt = suggested_notional * risk_fraction
    effective_risk_pct = (effective_risk_usdt / capital * 100.0) if capital > 0 else 0.0

    if "PAUSE" in new_trade_policy or advisor_action == "PAUSE_OR_REVIEW":
        sizing_action = "DO_NOT_OPEN_OR_MINIMUM_SIZE_OBSERVATION"
    elif "REDUCE_SIZE" in new_trade_policy or risk_state == "WAIT_REDUCED":
        sizing_action = "REDUCED_SIZE_OBSERVATION"
    elif risk_state == "PRIORITY" and score >= 75:
        sizing_action = "PRIORITY_SIZE_OBSERVATION"
    elif risk_state == "EXPERIMENTAL_CAPPED":
        sizing_action = "SMALL_EXPERIMENTAL_SIZE_OBSERVATION"
    else:
        sizing_action = "STANDARD_SIZE_OBSERVATION"

    reasons = []
    reasons.append(f"Risk per trade vem do Dynamic Risk Budget: {round(risk_pct, 4)}% / {round(risk_usdt, 4)} USDT.")
    if stop_distance_source == "ENTRY_STOP":
        reasons.append("Distância de stop calculada pela entrada e stop informados.")
    else:
        reasons.append("Sem entrada/stop informados; usa distância padrão conservadora para estimar tamanho.")
    if suggested_notional < raw_notional:
        reasons.append("Tamanho foi comprimido por teto de política/categoria para evitar exposição excessiva.")
    if not live_allowed:
        reasons.append("Execução LIVE não está permitida ou não há capacidade; sizing LIVE fica zerado e sizing paper é apenas consultivo.")
    if "PAUSE" in new_trade_policy:
        reasons.append("Política do Advisor está em pausa; não abrir novas entradas, exceto simulação/observação defensiva.")

    entry_f = _dps_safe_float(entry, None)
    stop_f = _dps_safe_float(stop, None)
    suggested_qty = None
    if entry_f and entry_f > 0 and suggested_notional > 0:
        suggested_qty = suggested_notional / entry_f

    return {
        "bot": bot,
        "category": budget.get("category"),
        "score": round(score, 2),
        "risk_state": risk_state,
        "advisor_action": advisor_action,
        "optimizer_recommendation": budget.get("optimizer_recommendation"),
        "new_trade_policy": new_trade_policy,
        "sizing_action": sizing_action,
        "side": side_norm,
        "entry": entry,
        "stop": stop,
        "stop_distance_pct": round(stop_distance_pct, 4),
        "stop_distance_source": stop_distance_source,
        "leverage": leverage,
        "risk_budget_pct": budget.get("risk_budget_pct"),
        "risk_budget_usdt": risk_budget_usdt,
        "risk_per_trade_pct": round(risk_pct, 4),
        "risk_per_trade_usdt": round(risk_usdt, 4),
        "paper_suggested_notional_usdt": round(suggested_notional, 4),
        "paper_suggested_margin_usdt": round(suggested_margin, 4),
        "paper_suggested_qty": round(suggested_qty, 8) if suggested_qty is not None else None,
        "paper_effective_risk_usdt": round(effective_risk_usdt, 4),
        "paper_effective_risk_pct": round(effective_risk_pct, 4),
        "raw_notional_usdt": round(raw_notional, 4),
        "raw_margin_usdt": round(raw_margin, 4),
        "policy_notional_cap_usdt": round(policy_notional_cap, 4) if policy_notional_cap is not None else None,
        "suggested_max_open_trades": budget.get("suggested_max_open_trades"),
        "live_allowed": live_allowed,
        "live_block_reason": live_block_reason,
        "live_suggested_notional_usdt": round(live_suggested_notional, 4),
        "live_suggested_margin_usdt": round(live_suggested_margin, 4),
        "live_caps": live_caps,
        "reasons": reasons,
    }


def build_dynamic_position_sizing_v1(capital=10000.0, bot_filter=None, entry=None, stop=None, side=None, leverage=None, total_risk_budget_pct=None):
    global DYNAMIC_POSITION_SIZING_V1_CACHE

    capital = _dps_safe_float(capital, 10000.0)
    try:
        risk_budget = build_dynamic_risk_budget_v1(capital=capital, total_risk_budget_pct=total_risk_budget_pct, bot_filter=bot_filter)
    except Exception as exc:
        risk_budget = {"ok": False, "error": str(exc), "budgets": [], "summary": {}, "live_context": {}, "alerts": []}

    budgets = risk_budget.get("budgets") or []
    sizes = []
    priority_count = 0
    reduced_count = 0
    paused_count = 0
    experimental_count = 0

    live_context = risk_budget.get("live_context") or {}
    for b in budgets:
        s = _dynamic_position_size_for_budget(
            b,
            capital=capital,
            entry=entry,
            stop=stop,
            side=side,
            leverage=leverage,
            live_context=live_context,
        )
        action = str(s.get("sizing_action") or "").upper()
        if "PRIORITY" in action:
            priority_count += 1
        if "REDUCED" in action:
            reduced_count += 1
        if "DO_NOT_OPEN" in action:
            paused_count += 1
        if "EXPERIMENTAL" in action:
            experimental_count += 1
        sizes.append(s)

    sizes = sorted(sizes, key=lambda x: (-_dps_safe_float(x.get("paper_suggested_notional_usdt"), 0), -_dps_safe_float(x.get("score"), 0), str(x.get("bot"))))

    total_paper_notional = sum(_dps_safe_float(x.get("paper_suggested_notional_usdt"), 0) for x in sizes)
    total_paper_margin = sum(_dps_safe_float(x.get("paper_suggested_margin_usdt"), 0) for x in sizes)
    total_paper_effective_risk = sum(_dps_safe_float(x.get("paper_effective_risk_usdt"), 0) for x in sizes)

    alerts = list(risk_budget.get("alerts") or [])
    if any(not x.get("live_allowed") for x in sizes):
        alerts.append("Sizing LIVE zerado enquanto real trading estiver bloqueado ou sem capacidade livre.")
    if entry is None or stop is None:
        alerts.append("Sem entrada/stop informados: sizing usa distância de stop padrão, apenas para referência por robô.")

    payload = {
        "ok": True,
        "version": DYNAMIC_POSITION_SIZING_V1_VERSION,
        "generated_at": data_hora_sp_str(),
        "mode": DYNAMIC_POSITION_SIZING_V1_MODE,
        "capital": capital,
        "inputs": {
            "bot_filter": bot_filter,
            "entry": entry,
            "stop": stop,
            "side": _dps_normalize_side(side),
            "leverage": int(_dps_clip(_dps_safe_float(leverage, DEFAULT_REAL_LEVERAGE if "DEFAULT_REAL_LEVERAGE" in globals() else 3), 1, 50)),
            "risk_budget_version": risk_budget.get("version"),
            "stop_distance_default_pct": _dps_safe_float(os.environ.get("DYNAMIC_POSITION_DEFAULT_STOP_PCT"), 2.0),
        },
        "sizes": sizes,
        "summary": {
            "bots": len(sizes),
            "priority_count": priority_count,
            "reduced_count": reduced_count,
            "paused_count": paused_count,
            "experimental_count": experimental_count,
            "top_size_bot": sizes[0] if sizes else None,
            "total_paper_suggested_notional_usdt": round(total_paper_notional, 4),
            "total_paper_suggested_margin_usdt": round(total_paper_margin, 4),
            "total_paper_effective_risk_usdt": round(total_paper_effective_risk, 4),
            "total_paper_effective_risk_pct": round((total_paper_effective_risk / capital * 100.0) if capital > 0 else 0.0, 4),
            "risk_budget_summary": risk_budget.get("summary"),
        },
        "live_context": live_context,
        "risk_budget_summary": risk_budget.get("summary"),
        "alerts": alerts,
        "notes": [
            "Dynamic Position Sizing V1 está em modo consultivo/observação.",
            "Não abre ordens, não altera lote real, não altera risco real e não executa na corretora.",
            "Converte o Dynamic Risk Budget V1 em tamanho sugerido de posição por robô.",
            "Quando entrada e stop são informados, calcula tamanho pela distância real até o stop.",
            "Quando entrada/stop não são informados, usa distância padrão conservadora apenas para referência.",
            "Preparado para alimentar Risk Manager decisório, OMS e executor no futuro.",
        ],
    }

    DYNAMIC_POSITION_SIZING_V1_CACHE = {
        "last_payload": payload,
        "last_generated_at": payload.get("generated_at"),
        "last_capital": capital,
    }
    return payload


def build_dynamic_position_sizing_v1_text(capital=10000.0, bot_filter=None, entry=None, stop=None, side=None, leverage=None, total_risk_budget_pct=None):
    payload = build_dynamic_position_sizing_v1(
        capital=capital,
        bot_filter=bot_filter,
        entry=entry,
        stop=stop,
        side=side,
        leverage=leverage,
        total_risk_budget_pct=total_risk_budget_pct,
    )
    summary = payload.get("summary") or {}
    live = payload.get("live_context") or {}
    inp = payload.get("inputs") or {}

    lines = [
        "📐 DYNAMIC POSITION SIZING V1 — CENTRAL QUANT",
        f"Data/hora: {payload.get('generated_at')}",
        f"Versão: {payload.get('version')}",
        f"Modo: {payload.get('mode')}",
        "",
        "Resumo geral:",
        f"Capital analisado: {payload.get('capital')} USDT",
        f"Robôs avaliados: {summary.get('bots')} | prioridade: {summary.get('priority_count')} | reduzidos: {summary.get('reduced_count')} | pausados: {summary.get('paused_count')} | experimentais: {summary.get('experimental_count')}",
        f"Notional paper sugerido total: {summary.get('total_paper_suggested_notional_usdt')} USDT",
        f"Margem paper sugerida total: {summary.get('total_paper_suggested_margin_usdt')} USDT",
        f"Risco efetivo paper estimado: {summary.get('total_paper_effective_risk_usdt')} USDT ({summary.get('total_paper_effective_risk_pct')}%)",
        "",
        "Parâmetros de sizing:",
        f"Bot filtro: {inp.get('bot_filter')}",
        f"Entrada: {inp.get('entry')} | Stop: {inp.get('stop')} | Side: {inp.get('side')} | Leverage: {inp.get('leverage')}x",
        f"Stop padrão usado quando ausente: {inp.get('stop_distance_default_pct')}%",
        "",
        "Contexto real/BingX:",
        f"READY: {live.get('bingx_ready')} | {live.get('bingx_status')}",
        f"Saldo total/free: {live.get('total_usdt')} / {live.get('free_usdt')} USDT",
        f"Capacidade teórica novas ordens: {live.get('theoretical_new_orders')}",
        f"Real trading: {'LIBERADO' if live.get('real_trading_enabled') else 'BLOQUEADO'} | Modo {live.get('execution_mode')}",
    ]

    alerts = payload.get("alerts") or []
    if alerts:
        lines += ["", "Alertas de position sizing:"]
        for alert in alerts:
            lines.append(f"- {alert}")

    lines += ["", "Sizing sugerido por robô:"]
    for idx, s in enumerate(payload.get("sizes") or [], start=1):
        lines += [
            "",
            f"{idx}. {s.get('bot')} — {s.get('sizing_action')}",
            f"Estado risco: {s.get('risk_state')} | Advisor: {s.get('advisor_action')} | Score: {s.get('score')}/100",
            f"Risk per trade: {s.get('risk_per_trade_pct')}% ({s.get('risk_per_trade_usdt')} USDT)",
            f"Stop distance: {s.get('stop_distance_pct')}% ({s.get('stop_distance_source')}) | Leverage: {s.get('leverage')}x",
            f"Paper notional sugerido: {s.get('paper_suggested_notional_usdt')} USDT",
            f"Paper margem sugerida: {s.get('paper_suggested_margin_usdt')} USDT",
            f"Paper qty sugerida: {s.get('paper_suggested_qty')}",
            f"Risco efetivo paper: {s.get('paper_effective_risk_usdt')} USDT ({s.get('paper_effective_risk_pct')}%)",
            f"LIVE permitido: {s.get('live_allowed')} | LIVE notional: {s.get('live_suggested_notional_usdt')} USDT | motivo: {s.get('live_block_reason')}",
            "Motivos:",
        ]
        for reason in s.get("reasons", [])[:5]:
            lines.append(f"- {reason}")

    lines += ["", "Notas:"]
    for note in payload.get("notes", []):
        lines.append(f"- {note}")

    return "\n".join(lines), payload


@app.route("/dynamic/position/sizing/v1")
@app.route("/dynamic-position-sizing/v1")
@app.route("/position/sizing/v1")
@app.route("/positionsizing/v1")
@app.route("/sizing/v1")
def dynamic_position_sizing_v1_route():
    capital = request.args.get("capital", default=10000, type=float)
    bot = request.args.get("bot", default=None, type=str)
    entry = request.args.get("entry", default=None, type=float)
    stop = request.args.get("stop", default=None, type=float)
    side = request.args.get("side", default=None, type=str)
    leverage = request.args.get("leverage", default=None, type=float)
    total_risk = request.args.get("risk", default=None, type=float)
    as_text = str(request.args.get("format", request.args.get("text", ""))).strip().lower() in {"1", "true", "yes", "sim", "on", "text", "txt"}
    text, payload = build_dynamic_position_sizing_v1_text(capital=capital, bot_filter=bot, entry=entry, stop=stop, side=side, leverage=leverage, total_risk_budget_pct=total_risk)
    if as_text:
        return text
    return {"ok": True, "text": text, "payload": payload}


@app.route("/dynamic/position/sizing/<bot>/v1")
@app.route("/position/sizing/<bot>/v1")
@app.route("/positionsizing/<bot>/v1")
def dynamic_position_sizing_v1_bot_route(bot):
    capital = request.args.get("capital", default=10000, type=float)
    entry = request.args.get("entry", default=None, type=float)
    stop = request.args.get("stop", default=None, type=float)
    side = request.args.get("side", default=None, type=str)
    leverage = request.args.get("leverage", default=None, type=float)
    total_risk = request.args.get("risk", default=None, type=float)
    as_text = str(request.args.get("format", request.args.get("text", ""))).strip().lower() in {"1", "true", "yes", "sim", "on", "text", "txt"}
    text, payload = build_dynamic_position_sizing_v1_text(capital=capital, bot_filter=bot, entry=entry, stop=stop, side=side, leverage=leverage, total_risk_budget_pct=total_risk)
    if as_text:
        return text
    return {"ok": True, "text": text, "payload": payload}


@app.route("/dynamic/position/sizing/summary/v1")
@app.route("/position/sizing/summary/v1")
@app.route("/positionsizing/summary/v1")
def dynamic_position_sizing_v1_summary_route():
    capital = request.args.get("capital", default=10000, type=float)
    bot = request.args.get("bot", default=None, type=str)
    entry = request.args.get("entry", default=None, type=float)
    stop = request.args.get("stop", default=None, type=float)
    side = request.args.get("side", default=None, type=str)
    leverage = request.args.get("leverage", default=None, type=float)
    total_risk = request.args.get("risk", default=None, type=float)
    payload = build_dynamic_position_sizing_v1(capital=capital, bot_filter=bot, entry=entry, stop=stop, side=side, leverage=leverage, total_risk_budget_pct=total_risk)
    return {
        "ok": True,
        "version": payload.get("version"),
        "generated_at": payload.get("generated_at"),
        "mode": payload.get("mode"),
        "capital": payload.get("capital"),
        "inputs": payload.get("inputs"),
        "summary": payload.get("summary"),
        "sizes": payload.get("sizes"),
        "alerts": payload.get("alerts"),
        "live_context": payload.get("live_context"),
        "cache": {
            "last_generated_at": DYNAMIC_POSITION_SIZING_V1_CACHE.get("last_generated_at"),
            "last_capital": DYNAMIC_POSITION_SIZING_V1_CACHE.get("last_capital"),
        },
    }


# ==========================================================
# DYNAMIC POSITION SIZING V1.1 - CENTRAL QUANT
# ==========================================================

DYNAMIC_POSITION_SIZING_V11_VERSION = "2026-07-04-DYNAMIC-POSITION-SIZING-V1.1"
DYNAMIC_POSITION_SIZING_V11_MODE = "OBSERVATION_ONLY"
DYNAMIC_POSITION_SIZING_V11_CACHE = {"last_payload": None, "last_generated_at": None, "last_capital": None}


def _dps_v11_limit_item(name, value, reason, active=True):
    try:
        value_f = float(value)
    except Exception:
        value_f = 0.0
    return {
        "name": str(name),
        "value_usdt": round(value_f, 4),
        "reason": str(reason),
        "active": bool(active and value_f > 0),
    }


def _dps_v11_select_binding_limit(limits):
    active_limits = [x for x in (limits or []) if x.get("active") and _dps_safe_float(x.get("value_usdt"), 0.0) > 0]
    if not active_limits:
        return None
    return min(active_limits, key=lambda x: _dps_safe_float(x.get("value_usdt"), 0.0))


def _dynamic_position_size_for_budget_v11(budget, capital, entry=None, stop=None, side=None, leverage=None, live_context=None):
    bot = str(budget.get("bot") or "UNKNOWN").upper().strip()
    side_norm = _dps_normalize_side(side)
    leverage = int(_dps_clip(_dps_safe_float(leverage, DEFAULT_REAL_LEVERAGE if "DEFAULT_REAL_LEVERAGE" in globals() else 3), 1, 50))
    risk_usdt = _dps_safe_float(budget.get("risk_per_trade_usdt"), 0.0)
    risk_pct = _dps_safe_float(budget.get("risk_per_trade_pct"), 0.0)
    risk_budget_usdt = _dps_safe_float(budget.get("risk_budget_usdt"), 0.0)
    risk_state = str(budget.get("risk_state") or "UNKNOWN").upper().strip()
    new_trade_policy = str(budget.get("new_trade_policy") or "").upper().strip()
    advisor_action = str(budget.get("advisor_action") or "").upper().strip()
    optimizer_recommendation = str(budget.get("optimizer_recommendation") or "").upper().strip()
    score = _dps_safe_float(budget.get("score"), 0.0)
    category = str(budget.get("category") or "UNKNOWN").upper().strip()

    stop_distance_pct, stop_distance_source = _dps_stop_distance_pct(entry=entry, stop=stop)
    risk_fraction = max(stop_distance_pct / 100.0, 0.0001)
    raw_notional = risk_usdt / risk_fraction if risk_usdt > 0 else 0.0
    raw_margin = raw_notional / leverage if leverage > 0 else raw_notional

    live_caps = _dps_live_caps(live_context)
    max_notional_env = _dps_safe_float(os.environ.get("DYNAMIC_POSITION_MAX_NOTIONAL_USDT"), 0.0)
    max_margin_env = _dps_safe_float(os.environ.get("DYNAMIC_POSITION_MAX_MARGIN_USDT"), 0.0)
    min_notional = _dps_safe_float(os.environ.get("DYNAMIC_POSITION_MIN_NOTIONAL_USDT"), 10.0)

    # Caps por política/categoria. V1.1 mantém o cálculo baseado no risco bruto,
    # mas explicita todos os limitadores e qual deles travou o tamanho final.
    if risk_state == "PRIORITY":
        policy_notional_cap = _dps_safe_float(os.environ.get("DYNAMIC_POSITION_PRIORITY_CAP_USDT"), 300.0)
    elif risk_state == "EXPERIMENTAL_CAPPED" or category == "EXPERIMENTAL":
        policy_notional_cap = _dps_safe_float(os.environ.get("DYNAMIC_POSITION_EXPERIMENTAL_CAP_USDT"), 80.0)
    elif risk_state == "WAIT_REDUCED" or advisor_action == "REDUCE_OR_WAIT":
        policy_notional_cap = _dps_safe_float(os.environ.get("DYNAMIC_POSITION_REDUCED_CAP_USDT"), 120.0)
    elif risk_state == "DEFENSIVE_MINIMUM" or advisor_action == "PAUSE_OR_REVIEW" or "PAUSE" in new_trade_policy:
        policy_notional_cap = _dps_safe_float(os.environ.get("DYNAMIC_POSITION_DEFENSIVE_CAP_USDT"), 30.0)
    else:
        policy_notional_cap = _dps_safe_float(os.environ.get("DYNAMIC_POSITION_STANDARD_CAP_USDT"), 150.0)

    # Cap derivado do capital alvo do optimizer. Não é a alocação inteira; é um teto por novo trade.
    try:
        target_pct = _dps_safe_float(budget.get("target_pct"), 0.0)
        target_capital_usdt = capital * target_pct / 100.0
    except Exception:
        target_pct = 0.0
        target_capital_usdt = 0.0
    target_trade_fraction = _dps_safe_float(os.environ.get("DYNAMIC_POSITION_TARGET_TRADE_FRACTION"), 0.10)
    target_capital_cap = target_capital_usdt * _dps_clip(target_trade_fraction, 0.01, 1.0) if target_capital_usdt > 0 else 0.0

    # Cap por orçamento total de risco do robô convertido em notional, para impedir que uma entrada consuma tudo.
    max_budget_fraction_per_trade = _dps_safe_float(os.environ.get("DYNAMIC_POSITION_MAX_BUDGET_FRACTION_PER_TRADE"), 0.25)
    budget_fraction_risk_usdt = risk_budget_usdt * _dps_clip(max_budget_fraction_per_trade, 0.01, 1.0)
    budget_fraction_cap = budget_fraction_risk_usdt / risk_fraction if budget_fraction_risk_usdt > 0 else 0.0

    limits = [
        _dps_v11_limit_item("RISK_BUDGET_RAW", raw_notional, "Notional necessário para usar 100% do risk per trade pela distância até o stop."),
        _dps_v11_limit_item("POLICY_CATEGORY_CAP", policy_notional_cap, "Teto por política/categoria do Advisor e do Risk Budget."),
        _dps_v11_limit_item("TARGET_ALLOCATION_CAP", target_capital_cap, "Fração máxima da alocação alvo por uma nova entrada.", active=target_capital_cap > 0),
        _dps_v11_limit_item("BUDGET_FRACTION_CAP", budget_fraction_cap, "Evita consumir parcela excessiva do orçamento total de risco do robô em uma única entrada.", active=budget_fraction_cap > 0),
    ]
    if max_notional_env > 0:
        limits.append(_dps_v11_limit_item("ENV_MAX_NOTIONAL_CAP", max_notional_env, "Teto global DYNAMIC_POSITION_MAX_NOTIONAL_USDT."))
    if max_margin_env > 0:
        limits.append(_dps_v11_limit_item("ENV_MAX_MARGIN_CAP", max_margin_env * leverage, "Teto global DYNAMIC_POSITION_MAX_MARGIN_USDT convertido em notional."))

    binding = _dps_v11_select_binding_limit(limits)
    suggested_notional = _dps_safe_float(binding.get("value_usdt"), 0.0) if binding else 0.0
    if raw_notional > 0:
        suggested_notional = min(suggested_notional, raw_notional)
    if 0 < suggested_notional < min_notional and not ("PAUSE" in new_trade_policy or risk_state == "DEFENSIVE_MINIMUM"):
        suggested_notional = min_notional

    suggested_margin = suggested_notional / leverage if leverage > 0 else suggested_notional

    live_notional_cap = live_caps.get("max_notional_usdt") or 0.0
    live_suggested_notional = min(suggested_notional, live_notional_cap) if live_notional_cap > 0 else suggested_notional
    live_suggested_margin = live_suggested_notional / leverage if leverage > 0 else live_suggested_notional
    if not live_caps.get("real_trading_enabled") or live_caps.get("theoretical_new_orders", 0) <= 0:
        live_allowed = False
        live_block_reason = "REAL_TRADING_BLOCKED_OR_NO_CAPACITY"
        live_suggested_notional = 0.0
        live_suggested_margin = 0.0
    else:
        live_allowed = True
        live_block_reason = None

    effective_risk_usdt = suggested_notional * risk_fraction
    effective_risk_pct = (effective_risk_usdt / capital * 100.0) if capital > 0 else 0.0
    risk_budget_utilization_pct = (effective_risk_usdt / risk_usdt * 100.0) if risk_usdt > 0 else 0.0

    # Separa prioridade estratégica do tamanho executável.
    if risk_state == "PRIORITY" or advisor_action == "PRIORITIZE":
        strategic_priority = "PRIORITY"
    elif advisor_action == "PAUSE_OR_REVIEW" or risk_state == "DEFENSIVE_MINIMUM":
        strategic_priority = "DEFENSIVE"
    elif risk_state == "EXPERIMENTAL_CAPPED":
        strategic_priority = "EXPERIMENTAL"
    elif advisor_action == "REDUCE_OR_WAIT" or risk_state == "WAIT_REDUCED":
        strategic_priority = "WAIT_REDUCED"
    else:
        strategic_priority = "STANDARD"

    binding_name = binding.get("name") if binding else None
    if advisor_action == "PAUSE_OR_REVIEW" or "PAUSE" in new_trade_policy:
        executable_size_state = "DO_NOT_OPEN_OR_MINIMUM_SIZE"
    elif binding_name == "RISK_BUDGET_RAW" and risk_budget_utilization_pct >= 95:
        executable_size_state = "FULL_RISK_SIZE"
    elif binding_name in {"POLICY_CATEGORY_CAP", "TARGET_ALLOCATION_CAP", "BUDGET_FRACTION_CAP", "ENV_MAX_NOTIONAL_CAP", "ENV_MAX_MARGIN_CAP"}:
        executable_size_state = "CAP_LIMITED_SIZE"
    elif strategic_priority == "EXPERIMENTAL":
        executable_size_state = "SMALL_EXPERIMENTAL_SIZE"
    else:
        executable_size_state = "REDUCED_SIZE"

    if executable_size_state == "DO_NOT_OPEN_OR_MINIMUM_SIZE":
        sizing_action = "DO_NOT_OPEN_OR_MINIMUM_SIZE_OBSERVATION"
    elif executable_size_state == "FULL_RISK_SIZE":
        sizing_action = "FULL_RISK_SIZE_OBSERVATION"
    elif executable_size_state == "CAP_LIMITED_SIZE":
        sizing_action = "CAP_LIMITED_SIZE_OBSERVATION"
    elif executable_size_state == "SMALL_EXPERIMENTAL_SIZE":
        sizing_action = "SMALL_EXPERIMENTAL_SIZE_OBSERVATION"
    else:
        sizing_action = "REDUCED_SIZE_OBSERVATION"

    reasons = []
    reasons.append(f"Risk per trade vem do Dynamic Risk Budget: {round(risk_pct, 4)}% / {round(risk_usdt, 4)} USDT.")
    if stop_distance_source == "ENTRY_STOP":
        reasons.append("Distância de stop calculada pela entrada e stop informados.")
    else:
        reasons.append("Sem entrada/stop informados; usa distância padrão conservadora para estimar tamanho.")
    if binding:
        reasons.append(f"Limitador dominante: {binding.get('name')} — {binding.get('reason')}")
    if risk_budget_utilization_pct < 80 and risk_usdt > 0:
        reasons.append(f"A sugestão usa apenas {round(risk_budget_utilization_pct, 2)}% do risk per trade por causa dos limitadores.")
    if not live_allowed:
        reasons.append("Execução LIVE não está permitida ou não há capacidade; sizing LIVE fica zerado e sizing paper é apenas consultivo.")
    if advisor_action == "PAUSE_OR_REVIEW" or "PAUSE" in new_trade_policy:
        reasons.append("Política do Advisor está em pausa; não abrir novas entradas, exceto simulação/observação defensiva.")

    entry_f = _dps_safe_float(entry, None)
    suggested_qty = None
    if entry_f and entry_f > 0 and suggested_notional > 0:
        suggested_qty = suggested_notional / entry_f

    return {
        "bot": bot,
        "category": budget.get("category"),
        "score": round(score, 2),
        "strategic_priority": strategic_priority,
        "executable_size_state": executable_size_state,
        "risk_state": risk_state,
        "advisor_action": advisor_action,
        "optimizer_recommendation": budget.get("optimizer_recommendation"),
        "new_trade_policy": new_trade_policy,
        "sizing_action": sizing_action,
        "side": side_norm,
        "entry": entry,
        "stop": stop,
        "stop_distance_pct": round(stop_distance_pct, 4),
        "stop_distance_source": stop_distance_source,
        "leverage": leverage,
        "risk_budget_pct": budget.get("risk_budget_pct"),
        "risk_budget_usdt": round(risk_budget_usdt, 4),
        "risk_per_trade_pct": round(risk_pct, 4),
        "risk_per_trade_usdt": round(risk_usdt, 4),
        "paper_suggested_notional_usdt": round(suggested_notional, 4),
        "paper_suggested_margin_usdt": round(suggested_margin, 4),
        "paper_suggested_qty": round(suggested_qty, 8) if suggested_qty is not None else None,
        "paper_effective_risk_usdt": round(effective_risk_usdt, 4),
        "paper_effective_risk_pct": round(effective_risk_pct, 4),
        "risk_budget_utilization_pct": round(risk_budget_utilization_pct, 4),
        "unused_risk_per_trade_usdt": round(max(0.0, risk_usdt - effective_risk_usdt), 4),
        "raw_notional_usdt": round(raw_notional, 4),
        "raw_margin_usdt": round(raw_margin, 4),
        "binding_limit": binding,
        "limit_chain": limits,
        "policy_notional_cap_usdt": round(policy_notional_cap, 4) if policy_notional_cap is not None else None,
        "target_capital_cap_usdt": round(target_capital_cap, 4),
        "budget_fraction_cap_usdt": round(budget_fraction_cap, 4),
        "suggested_max_open_trades": budget.get("suggested_max_open_trades"),
        "live_allowed": live_allowed,
        "live_block_reason": live_block_reason,
        "live_suggested_notional_usdt": round(live_suggested_notional, 4),
        "live_suggested_margin_usdt": round(live_suggested_margin, 4),
        "live_caps": live_caps,
        "reasons": reasons,
    }


def build_dynamic_position_sizing_v11(capital=10000.0, bot_filter=None, entry=None, stop=None, side=None, leverage=None, total_risk_budget_pct=None):
    global DYNAMIC_POSITION_SIZING_V11_CACHE
    capital = _dps_safe_float(capital, 10000.0)
    try:
        risk_budget = build_dynamic_risk_budget_v1(capital=capital, total_risk_budget_pct=total_risk_budget_pct, bot_filter=bot_filter)
    except Exception as exc:
        risk_budget = {"ok": False, "error": str(exc), "budgets": [], "summary": {}, "live_context": {}, "alerts": []}

    budgets = risk_budget.get("budgets") or []
    live_context = risk_budget.get("live_context") or {}
    sizes = []
    strategic_priority_counts = {}
    executable_size_counts = {}

    for b in budgets:
        s = _dynamic_position_size_for_budget_v11(
            b,
            capital=capital,
            entry=entry,
            stop=stop,
            side=side,
            leverage=leverage,
            live_context=live_context,
        )
        sizes.append(s)
        strategic_priority_counts[s.get("strategic_priority")] = strategic_priority_counts.get(s.get("strategic_priority"), 0) + 1
        executable_size_counts[s.get("executable_size_state")] = executable_size_counts.get(s.get("executable_size_state"), 0) + 1

    sizes.sort(key=lambda x: (_dps_safe_float(x.get("paper_suggested_notional_usdt"), 0.0), _dps_safe_float(x.get("score"), 0.0)), reverse=True)

    total_paper_notional = sum(_dps_safe_float(s.get("paper_suggested_notional_usdt"), 0.0) for s in sizes)
    total_paper_margin = sum(_dps_safe_float(s.get("paper_suggested_margin_usdt"), 0.0) for s in sizes)
    total_paper_effective_risk = sum(_dps_safe_float(s.get("paper_effective_risk_usdt"), 0.0) for s in sizes)
    total_risk_per_trade = sum(_dps_safe_float(s.get("risk_per_trade_usdt"), 0.0) for s in sizes)
    total_util = (total_paper_effective_risk / total_risk_per_trade * 100.0) if total_risk_per_trade > 0 else 0.0

    alerts = list(risk_budget.get("alerts") or [])
    if not (live_context or {}).get("real_trading_enabled"):
        alerts.append("Sizing LIVE zerado enquanto real trading estiver bloqueado ou sem capacidade livre.")
    if entry is None or stop is None:
        alerts.append("Sem entrada/stop informados: sizing usa distância de stop padrão, apenas para referência por robô.")
    if total_util < 50 and total_risk_per_trade > 0:
        alerts.append("Uso efetivo do risk per trade está baixo; limitadores de política/capital estão comprimindo os tamanhos.")

    payload = {
        "ok": True,
        "version": DYNAMIC_POSITION_SIZING_V11_VERSION,
        "generated_at": data_hora_sp_str(),
        "mode": DYNAMIC_POSITION_SIZING_V11_MODE,
        "capital": capital,
        "inputs": {
            "bot_filter": bot_filter,
            "entry": entry,
            "stop": stop,
            "side": _dps_normalize_side(side),
            "leverage": int(_dps_clip(_dps_safe_float(leverage, DEFAULT_REAL_LEVERAGE if "DEFAULT_REAL_LEVERAGE" in globals() else 3), 1, 50)),
            "risk_budget_version": risk_budget.get("version"),
            "stop_distance_default_pct": _dps_safe_float(os.environ.get("DYNAMIC_POSITION_DEFAULT_STOP_PCT"), 2.0),
        },
        "sizes": sizes,
        "summary": {
            "bots": len(sizes),
            "strategic_priority_counts": strategic_priority_counts,
            "executable_size_counts": executable_size_counts,
            "top_size_bot": sizes[0] if sizes else None,
            "total_paper_suggested_notional_usdt": round(total_paper_notional, 4),
            "total_paper_suggested_margin_usdt": round(total_paper_margin, 4),
            "total_paper_effective_risk_usdt": round(total_paper_effective_risk, 4),
            "total_paper_effective_risk_pct": round((total_paper_effective_risk / capital * 100.0) if capital > 0 else 0.0, 4),
            "total_risk_per_trade_usdt": round(total_risk_per_trade, 4),
            "total_risk_budget_utilization_pct": round(total_util, 4),
            "risk_budget_summary": risk_budget.get("summary"),
        },
        "live_context": live_context,
        "risk_budget_summary": risk_budget.get("summary"),
        "alerts": alerts,
        "notes": [
            "Dynamic Position Sizing V1.1 está em modo consultivo/observação.",
            "Não abre ordens, não altera lote real, não altera risco real e não executa na corretora.",
            "Correção V1.1: mostra cadeia de limitadores e limitador dominante.",
            "Correção V1.1: calcula utilização real do risk per trade após caps.",
            "Correção V1.1: separa prioridade estratégica de tamanho efetivamente executável.",
            "Preparado para alimentar Risk Manager decisório, OMS e executor no futuro.",
        ],
    }
    DYNAMIC_POSITION_SIZING_V11_CACHE = {
        "last_payload": payload,
        "last_generated_at": payload.get("generated_at"),
        "last_capital": capital,
    }
    return payload


def build_dynamic_position_sizing_v11_text(capital=10000.0, bot_filter=None, entry=None, stop=None, side=None, leverage=None, total_risk_budget_pct=None):
    payload = build_dynamic_position_sizing_v11(capital=capital, bot_filter=bot_filter, entry=entry, stop=stop, side=side, leverage=leverage, total_risk_budget_pct=total_risk_budget_pct)
    summary = payload.get("summary") or {}
    live = payload.get("live_context") or {}
    inp = payload.get("inputs") or {}

    lines = [
        "📐 DYNAMIC POSITION SIZING V1.1 — CENTRAL QUANT",
        f"Data/hora: {payload.get('generated_at')}",
        f"Versão: {payload.get('version')}",
        f"Modo: {payload.get('mode')}",
        "",
        "Resumo geral:",
        f"Capital analisado: {payload.get('capital')} USDT",
        f"Robôs avaliados: {summary.get('bots')}",
        f"Notional paper sugerido total: {summary.get('total_paper_suggested_notional_usdt')} USDT",
        f"Margem paper sugerida total: {summary.get('total_paper_suggested_margin_usdt')} USDT",
        f"Risco efetivo paper estimado: {summary.get('total_paper_effective_risk_usdt')} USDT ({summary.get('total_paper_effective_risk_pct')}%)",
        f"Uso do risk per trade disponível: {summary.get('total_risk_budget_utilization_pct')}%",
        "",
        "Parâmetros de sizing:",
        f"Bot filtro: {inp.get('bot_filter')}",
        f"Entrada: {inp.get('entry')} | Stop: {inp.get('stop')} | Side: {inp.get('side')} | Leverage: {inp.get('leverage')}x",
        f"Stop padrão usado quando ausente: {inp.get('stop_distance_default_pct')}%",
        "",
        "Contexto real/BingX:",
        f"READY: {live.get('bingx_ready')} | {live.get('bingx_status')}",
        f"Saldo total/free: {live.get('total_usdt')} / {live.get('free_usdt')} USDT",
        f"Capacidade teórica novas ordens: {live.get('theoretical_new_orders')}",
        f"Real trading: {'LIBERADO' if live.get('real_trading_enabled') else 'BLOQUEADO'} | Modo {live.get('execution_mode')}",
    ]

    alerts = payload.get("alerts") or []
    if alerts:
        lines += ["", "Alertas de position sizing:"]
        for alert in alerts:
            lines.append(f"- {alert}")

    lines += ["", "Sizing sugerido por robô:"]
    for idx, s in enumerate(payload.get("sizes") or [], start=1):
        bind = s.get("binding_limit") or {}
        lines += [
            "",
            f"{idx}. {s.get('bot')} — {s.get('sizing_action')}",
            f"Prioridade estratégica: {s.get('strategic_priority')} | Tamanho executável: {s.get('executable_size_state')}",
            f"Estado risco: {s.get('risk_state')} | Advisor: {s.get('advisor_action')} | Score: {s.get('score')}/100",
            f"Risk per trade: {s.get('risk_per_trade_pct')}% ({s.get('risk_per_trade_usdt')} USDT)",
            f"Stop distance: {s.get('stop_distance_pct')}% ({s.get('stop_distance_source')}) | Leverage: {s.get('leverage')}x",
            f"Raw notional necessário: {s.get('raw_notional_usdt')} USDT",
            f"Paper notional sugerido: {s.get('paper_suggested_notional_usdt')} USDT",
            f"Paper margem sugerida: {s.get('paper_suggested_margin_usdt')} USDT",
            f"Paper qty sugerida: {s.get('paper_suggested_qty')}",
            f"Risco efetivo paper: {s.get('paper_effective_risk_usdt')} USDT ({s.get('paper_effective_risk_pct')}%)",
            f"Uso do risk per trade: {s.get('risk_budget_utilization_pct')}% | Risco não usado: {s.get('unused_risk_per_trade_usdt')} USDT",
            f"Limitador dominante: {bind.get('name')} ({bind.get('value_usdt')} USDT)",
            f"LIVE permitido: {s.get('live_allowed')} | LIVE notional: {s.get('live_suggested_notional_usdt')} USDT | motivo: {s.get('live_block_reason')}",
            "Motivos:",
        ]
        for reason in s.get("reasons", [])[:6]:
            lines.append(f"- {reason}")

    lines += ["", "Notas:"]
    for note in payload.get("notes", []):
        lines.append(f"- {note}")

    return "\n".join(lines), payload


@app.route("/dynamic/position/sizing/v1.1")
@app.route("/dynamic-position-sizing/v1.1")
@app.route("/position/sizing/v1.1")
@app.route("/positionsizing/v1.1")
@app.route("/sizing/v1.1")
def dynamic_position_sizing_v11_route():
    capital = request.args.get("capital", default=10000, type=float)
    bot = request.args.get("bot", default=None, type=str)
    entry = request.args.get("entry", default=None, type=float)
    stop = request.args.get("stop", default=None, type=float)
    side = request.args.get("side", default=None, type=str)
    leverage = request.args.get("leverage", default=None, type=float)
    total_risk = request.args.get("risk", default=None, type=float)
    as_text = str(request.args.get("format", request.args.get("text", ""))).strip().lower() in {"1", "true", "yes", "sim", "on", "text", "txt"}
    text, payload = build_dynamic_position_sizing_v11_text(capital=capital, bot_filter=bot, entry=entry, stop=stop, side=side, leverage=leverage, total_risk_budget_pct=total_risk)
    if as_text:
        return text
    return {"ok": True, "text": text, "payload": payload}


@app.route("/dynamic/position/sizing/<bot>/v1.1")
@app.route("/position/sizing/<bot>/v1.1")
@app.route("/positionsizing/<bot>/v1.1")
def dynamic_position_sizing_v11_bot_route(bot):
    capital = request.args.get("capital", default=10000, type=float)
    entry = request.args.get("entry", default=None, type=float)
    stop = request.args.get("stop", default=None, type=float)
    side = request.args.get("side", default=None, type=str)
    leverage = request.args.get("leverage", default=None, type=float)
    total_risk = request.args.get("risk", default=None, type=float)
    as_text = str(request.args.get("format", request.args.get("text", ""))).strip().lower() in {"1", "true", "yes", "sim", "on", "text", "txt"}
    text, payload = build_dynamic_position_sizing_v11_text(capital=capital, bot_filter=bot, entry=entry, stop=stop, side=side, leverage=leverage, total_risk_budget_pct=total_risk)
    if as_text:
        return text
    return {"ok": True, "text": text, "payload": payload}


@app.route("/dynamic/position/sizing/summary/v1.1")
@app.route("/position/sizing/summary/v1.1")
@app.route("/positionsizing/summary/v1.1")
def dynamic_position_sizing_v11_summary_route():
    capital = request.args.get("capital", default=10000, type=float)
    bot = request.args.get("bot", default=None, type=str)
    entry = request.args.get("entry", default=None, type=float)
    stop = request.args.get("stop", default=None, type=float)
    side = request.args.get("side", default=None, type=str)
    leverage = request.args.get("leverage", default=None, type=float)
    total_risk = request.args.get("risk", default=None, type=float)
    payload = build_dynamic_position_sizing_v11(capital=capital, bot_filter=bot, entry=entry, stop=stop, side=side, leverage=leverage, total_risk_budget_pct=total_risk)
    return {
        "ok": True,
        "version": payload.get("version"),
        "generated_at": payload.get("generated_at"),
        "mode": payload.get("mode"),
        "capital": payload.get("capital"),
        "inputs": payload.get("inputs"),
        "summary": payload.get("summary"),
        "sizes": payload.get("sizes"),
        "alerts": payload.get("alerts"),
        "live_context": payload.get("live_context"),
        "cache": {
            "last_generated_at": DYNAMIC_POSITION_SIZING_V11_CACHE.get("last_generated_at"),
            "last_capital": DYNAMIC_POSITION_SIZING_V11_CACHE.get("last_capital"),
        },
    }

# ==========================================================
# EXECUTION POLICY ENGINE V1 - CENTRAL QUANT
# ==========================================================

EXECUTION_POLICY_ENGINE_V1_VERSION = "2026-07-04-EXECUTION-POLICY-ENGINE-V1"
EXECUTION_POLICY_ENGINE_V1_MODE = "OBSERVATION_ONLY"
EXECUTION_POLICY_ENGINE_V1_CACHE = {"last_payload": None, "last_generated_at": None, "last_capital": None}


def _epe_safe_float(value, default=0.0):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _epe_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "sim", "on", "live"}


def _epe_normalize_side(value):
    side = str(value or "").upper().strip()
    if side == "BUY":
        return "LONG"
    if side == "SELL":
        return "SHORT"
    return side


def _epe_vote(module, vote, weight=1.0, reason="", details=None):
    vote = str(vote or "WAIT").upper().strip()
    if vote not in {"ALLOW", "REDUCE", "WAIT", "DENY", "INFO"}:
        vote = "WAIT"
    return {"module": str(module), "vote": vote, "weight": round(_epe_safe_float(weight, 1.0), 4), "reason": str(reason or ""), "details": details or {}}


def _epe_final_decision(votes, sizing_item=None, intended_live=False, real_trading_enabled=False):
    vals = [str(v.get("vote") or "INFO").upper() for v in (votes or [])]
    if "DENY" in vals:
        base = "DENY"
    elif "WAIT" in vals:
        base = "WAIT"
    elif "REDUCE" in vals:
        base = "REDUCE"
    else:
        base = "ALLOW"
    if intended_live and not real_trading_enabled and base == "ALLOW":
        base = "WAIT"
    if sizing_item:
        action = str(sizing_item.get("sizing_action") or "").upper()
        if "DO_NOT_OPEN" in action:
            base = "DENY"
        elif ("CAP_LIMITED" in action or "REDUCED" in action) and base == "ALLOW":
            base = "REDUCE"
    return base


def _epe_confidence_score(votes, final_decision, sizing_item=None):
    votes = votes or []
    if not votes:
        return 50.0
    final_decision = str(final_decision or "WAIT").upper()
    total = sum(_epe_safe_float(v.get("weight"), 1.0) for v in votes) or 1.0
    agree = sum(_epe_safe_float(v.get("weight"), 1.0) for v in votes if str(v.get("vote") or "").upper() == final_decision)
    if final_decision == "REDUCE":
        agree += 0.35 * sum(_epe_safe_float(v.get("weight"), 1.0) for v in votes if str(v.get("vote") or "").upper() in {"ALLOW", "WAIT"})
    score = 45.0 + 55.0 * (agree / total)
    if sizing_item:
        util = _epe_safe_float(sizing_item.get("risk_budget_utilization_pct"), 0.0)
        if util < 5:
            score -= 5
        elif util > 80:
            score += 3
    return round(max(0.0, min(100.0, score)), 2)


def _epe_capital_allocator_check(capital, bot, required_capital, required_risk):
    try:
        import capital_allocator
        result = capital_allocator.capital_check(capital=capital, bot=bot, required=required_capital, risk=required_risk)
        return result if isinstance(result, dict) else {"ok": False, "error": str(result)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _epe_vote_from_capital_allocator(result):
    if not isinstance(result, dict) or not result.get("ok"):
        return _epe_vote("Capital Allocator", "INFO", 0.6, "Capital Allocator indisponível ou sem resposta válida.", result if isinstance(result, dict) else {})
    decision = str(result.get("decision") or result.get("base_decision") or "").upper()
    if decision in {"BLOCK", "DENY"}:
        vote = "DENY"
    elif "REDUCE" in decision:
        vote = "REDUCE"
    elif "ALLOW" in decision:
        vote = "ALLOW"
    else:
        vote = "WAIT"
    return _epe_vote("Capital Allocator", vote, 1.15, result.get("reason") or f"Capital Allocator retornou {decision}.", {
        "decision": decision,
        "capital_free": result.get("capital_free"),
        "risk_free_usdt": result.get("risk_free_usdt"),
        "required_capital": result.get("required_capital"),
        "required_risk_usdt": result.get("required_risk_usdt"),
        "suggested_required_capital": result.get("suggested_required_capital"),
    })


def _epe_vote_from_risk_manager(result):
    if isinstance(result, tuple):
        result = result[0]
    if not isinstance(result, dict):
        return _epe_vote("Risk Manager Global", "INFO", 0.7, "Risk Manager retornou resposta não estruturada.", {})
    decision = str(result.get("decision") or ("ALLOW" if result.get("allowed") else "DENY")).upper()
    vote = "ALLOW" if decision == "ALLOW" or result.get("allowed") is True else "DENY"
    reasons = result.get("reasons") or []
    warnings = result.get("warnings") or []
    reason = "; ".join([str(x) for x in reasons[:3]]) or "; ".join([str(x) for x in warnings[:3]]) or f"Risk Manager retornou {decision}."
    return _epe_vote("Risk Manager Global", vote, 1.4, reason, {"decision": decision, "allowed": result.get("allowed"), "reasons": reasons[:10], "warnings": warnings[:10], "exposure": result.get("exposure")})


def _epe_vote_from_sizing(item):
    if not isinstance(item, dict):
        return _epe_vote("Dynamic Position Sizing V1.1", "WAIT", 1.2, "Sizing indisponível; aguardar cálculo válido.", {})
    action = str(item.get("sizing_action") or "").upper()
    executable = str(item.get("executable_size_state") or "").upper()
    binding = item.get("binding_limit") or {}
    util = _epe_safe_float(item.get("risk_budget_utilization_pct"), 0.0)
    if "DO_NOT_OPEN" in action:
        vote = "DENY"
    elif "CAP_LIMITED" in action or "REDUCED" in action:
        vote = "REDUCE"
    elif "FULL_RISK" in action:
        vote = "ALLOW"
    else:
        vote = "WAIT"
    return _epe_vote("Dynamic Position Sizing V1.1", vote, 1.35, f"Sizing={action}; executável={executable}; limitador={binding.get('name')}; uso risk={round(util, 4)}%.", {
        "sizing_action": action,
        "strategic_priority": item.get("strategic_priority"),
        "executable_size_state": executable,
        "binding_limit": binding,
        "paper_suggested_notional_usdt": item.get("paper_suggested_notional_usdt"),
        "paper_suggested_margin_usdt": item.get("paper_suggested_margin_usdt"),
        "paper_suggested_qty": item.get("paper_suggested_qty"),
        "paper_effective_risk_usdt": item.get("paper_effective_risk_usdt"),
        "risk_budget_utilization_pct": item.get("risk_budget_utilization_pct"),
        "unused_risk_per_trade_usdt": item.get("unused_risk_per_trade_usdt"),
    })


def _epe_votes_from_advisor_budget(item):
    if not isinstance(item, dict):
        return []
    advisor = str(item.get("advisor_action") or "").upper()
    risk_state = str(item.get("risk_state") or "").upper()
    policy = str(item.get("new_trade_policy") or "").upper()
    if advisor == "PRIORITIZE" or risk_state == "PRIORITY":
        return [_epe_vote("Portfolio Advisor / Risk Budget", "ALLOW", 1.0, "Robô está priorizado estrategicamente e possui risk budget prioritário.", {"advisor_action": advisor, "risk_state": risk_state})]
    if advisor == "PAUSE_OR_REVIEW" or "PAUSE" in policy or risk_state == "DEFENSIVE_MINIMUM":
        return [_epe_vote("Portfolio Advisor / Risk Budget", "DENY", 1.2, "Advisor/Risk Budget indicam pausa ou mínimo defensivo; não abrir nova entrada.", {"advisor_action": advisor, "risk_state": risk_state, "new_trade_policy": policy})]
    if advisor == "REDUCE_OR_WAIT" or risk_state == "WAIT_REDUCED":
        return [_epe_vote("Portfolio Advisor / Risk Budget", "WAIT", 1.0, "Advisor/Risk Budget indicam reduzir ou aguardar; não expandir agressivamente.", {"advisor_action": advisor, "risk_state": risk_state, "new_trade_policy": policy})]
    if risk_state == "EXPERIMENTAL_CAPPED":
        return [_epe_vote("Portfolio Advisor / Risk Budget", "REDUCE", 0.9, "Robô experimental: permitir apenas tamanho pequeno/controlado.", {"advisor_action": advisor, "risk_state": risk_state})]
    return [_epe_vote("Portfolio Advisor / Risk Budget", "INFO", 0.5, "Sem política forte do Advisor/Risk Budget.", {"advisor_action": advisor, "risk_state": risk_state})]




def _epe_vote_from_correlation_engine(result):
    if not isinstance(result, dict) or not result.get("ok"):
        return _epe_vote("Correlation Engine V1", "INFO", 0.7, "Correlation Engine indisponível ou sem resposta válida.", result if isinstance(result, dict) else {})
    sig = result.get("signal_policy") or {}
    if not sig:
        return _epe_vote("Correlation Engine V1", "INFO", 0.7, "Sem símbolo/sinal específico; correlação usada apenas como contexto de portfólio.", {
            "dominant_cluster": (result.get("automation_policy") or {}).get("dominant_cluster"),
            "high_risk_clusters": (result.get("automation_policy") or {}).get("high_risk_clusters"),
        })
    action = str(sig.get("correlation_action") or "").upper()
    gate = str(sig.get("signal_gate") or "").upper()
    severity = str(sig.get("severity") or "").upper()
    risk_multiplier = _epe_safe_float(sig.get("risk_multiplier"), 1.0)
    reasons = sig.get("reasons") or []
    reason = "; ".join([str(x) for x in reasons[:3]]) or f"Correlation Engine retornou {action}."
    if "BLOCK" in action or "BLOCK" in gate or risk_multiplier <= 0:
        vote = "DENY"
    elif "COMPRESS" in action or risk_multiplier < 0.5 or severity == "HIGH":
        vote = "REDUCE"
    elif "WATCH" in action or risk_multiplier < 1.0 or severity == "MEDIUM":
        vote = "WAIT"
    else:
        vote = "ALLOW"
    return _epe_vote("Correlation Engine V1", vote, 1.25, reason, {
        "correlation_action": action,
        "signal_gate": gate,
        "severity": severity,
        "risk_multiplier": risk_multiplier,
        "primary_cluster": sig.get("primary_cluster"),
        "binding_cluster": sig.get("binding_cluster"),
        "same_symbol_count": sig.get("same_symbol_count"),
        "clusters": sig.get("clusters"),
        "cluster_pressures_count": len(sig.get("cluster_pressures") or []),
        "reasons": reasons[:5],
    })


def _epe_apply_correlation_multiplier(value, multiplier):
    try:
        if value is None:
            return None
        return round(float(value) * float(multiplier), 8)
    except Exception:
        return value


def _epe_request_payload_from_args(default_payload=None):
    p = dict(default_payload or {})
    for key in ["bot", "symbol", "side", "entry", "stop", "setup", "leverage", "capital", "mode", "intended_live"]:
        val = request.args.get(key)
        if val not in [None, ""]:
            p[key] = val
    return p


def _epe_compact_correlation_payload(payload):
    if not isinstance(payload, dict):
        return {}
    sig = payload.get("signal_policy") or None
    auto = payload.get("automation_policy") or {}
    top = payload.get("top_cluster") or {}
    compact_sig = None
    if isinstance(sig, dict):
        compact_pressures = []
        for p in sig.get("cluster_pressures") or []:
            compact_pressures.append({
                "cluster": p.get("cluster"),
                "positions": p.get("positions"),
                "position_pct": p.get("position_pct"),
                "severity": p.get("severity"),
                "risk_multiplier": p.get("risk_multiplier"),
                "signal_gate": p.get("signal_gate"),
                "action": p.get("action"),
                "reasons": (p.get("reasons") or [])[:3],
            })
        compact_sig = {
            "bot": sig.get("bot"),
            "setup": sig.get("setup"),
            "symbol": sig.get("symbol"),
            "side": sig.get("side"),
            "primary_cluster": sig.get("primary_cluster"),
            "clusters": sig.get("clusters") or [],
            "same_symbol_count": sig.get("same_symbol_count"),
            "binding_cluster": sig.get("binding_cluster"),
            "correlation_action": sig.get("correlation_action"),
            "signal_gate": sig.get("signal_gate"),
            "risk_multiplier": sig.get("risk_multiplier"),
            "severity": sig.get("severity"),
            "reasons": (sig.get("reasons") or [])[:5],
            "cluster_pressures": compact_pressures,
        }
    return {
        "ok": bool(payload.get("ok")),
        "version": payload.get("version"),
        "generated_at": payload.get("generated_at"),
        "mode": payload.get("mode"),
        "source": payload.get("source"),
        "market_regime": payload.get("market_regime"),
        "exposure_summary": payload.get("exposure_summary"),
        "top_cluster": {
            "cluster": top.get("cluster"),
            "positions": top.get("positions"),
            "position_pct": top.get("position_pct"),
            "severity": top.get("severity"),
            "symbols_count": top.get("symbols_count"),
        } if isinstance(top, dict) else None,
        "signal_policy": compact_sig,
        "automation_policy": {
            "correlation_gate_required": auto.get("correlation_gate_required"),
            "dominant_cluster": auto.get("dominant_cluster"),
            "dominant_cluster_severity": auto.get("dominant_cluster_severity"),
            "compressed_clusters": auto.get("compressed_clusters") or [],
            "high_risk_clusters": auto.get("high_risk_clusters") or [],
            "watch_clusters": auto.get("watch_clusters") or [],
            "route_new_signals_to": auto.get("route_new_signals_to"),
        },
        "alerts": (payload.get("alerts") or [])[:8],
    }


def build_execution_policy_v1(capital=10000.0, bot=None, symbol=None, side=None, entry=None, stop=None, setup=None, leverage=None, mode=None, intended_live=None):
    global EXECUTION_POLICY_ENGINE_V1_CACHE
    capital = _epe_safe_float(capital, 10000.0)
    bot_norm = normalize_registry_bot(bot or "")
    symbol_norm = normalize_registry_symbol(symbol or "")
    side_norm = _epe_normalize_side(side)
    mode_norm = str(mode or EXECUTION_MODE or "VERIFY").upper().strip()
    intended_live_bool = _epe_bool(intended_live, mode_norm == "LIVE")
    leverage_i = int(_dps_clip(_epe_safe_float(leverage, DEFAULT_REAL_LEVERAGE if "DEFAULT_REAL_LEVERAGE" in globals() else 3), 1, 50))
    entry_f = _epe_safe_float(entry, None)
    stop_f = _epe_safe_float(stop, None)

    votes = []
    missing = []
    if not bot_norm:
        missing.append("bot")
    if not symbol_norm:
        missing.append("symbol")
    if side_norm not in {"LONG", "SHORT"}:
        missing.append("side")
    if entry_f is None:
        missing.append("entry")
    if stop_f is None:
        missing.append("stop")
    votes.append(_epe_vote("Input Validation", "WAIT" if missing else "ALLOW", 1.3 if missing else 0.8, "Campos ausentes para decisão executável: " + ", ".join(missing) if missing else "Entrada operacional completa para avaliação.", {"missing": missing}))

    try:
        sizing_payload = build_dynamic_position_sizing_v11(capital=capital, bot_filter=bot_norm or None, entry=entry_f, stop=stop_f, side=side_norm, leverage=leverage_i)
    except Exception as exc:
        sizing_payload = {"ok": False, "error": str(exc), "sizes": [], "summary": {}, "live_context": {}}
    sizes = sizing_payload.get("sizes") or []
    sizing_item = sizes[0] if sizes else None
    votes.append(_epe_vote_from_sizing(sizing_item))
    votes.extend(_epe_votes_from_advisor_budget(sizing_item))

    suggested_notional = _epe_safe_float((sizing_item or {}).get("paper_suggested_notional_usdt"), 0.0)
    suggested_margin = _epe_safe_float((sizing_item or {}).get("paper_suggested_margin_usdt"), 0.0)
    suggested_qty = (sizing_item or {}).get("paper_suggested_qty")
    effective_risk_usdt = _epe_safe_float((sizing_item or {}).get("paper_effective_risk_usdt"), 0.0)
    effective_risk_pct = _epe_safe_float((sizing_item or {}).get("paper_effective_risk_pct"), 0.0)

    try:
        correlation_payload = build_correlation_engine_v1(capital=capital, bot=bot_norm or None, symbol=symbol_norm or None, side=side_norm or None, setup=setup)
    except Exception as exc:
        correlation_payload = {"ok": False, "error": str(exc), "signal_policy": None}
    correlation_payload = _epe_compact_correlation_payload(correlation_payload)
    correlation_vote = _epe_vote_from_correlation_engine(correlation_payload)
    votes.append(correlation_vote)

    correlation_policy = correlation_payload.get("signal_policy") if isinstance(correlation_payload, dict) else None
    correlation_multiplier = 1.0
    correlation_adjusted = False
    if isinstance(correlation_policy, dict):
        correlation_multiplier = _epe_safe_float(correlation_policy.get("risk_multiplier"), 1.0)
        correlation_multiplier = max(0.0, min(1.0, correlation_multiplier))
        if correlation_multiplier < 1.0:
            correlation_adjusted = True
            suggested_notional = _epe_apply_correlation_multiplier(suggested_notional, correlation_multiplier) or 0.0
            suggested_margin = _epe_apply_correlation_multiplier(suggested_margin, correlation_multiplier) or 0.0
            suggested_qty = _epe_apply_correlation_multiplier(suggested_qty, correlation_multiplier)
            effective_risk_usdt = _epe_apply_correlation_multiplier(effective_risk_usdt, correlation_multiplier) or 0.0
            effective_risk_pct = _epe_apply_correlation_multiplier(effective_risk_pct, correlation_multiplier) or 0.0

    capital_result = _epe_capital_allocator_check(capital, bot_norm, suggested_notional, effective_risk_usdt)
    votes.append(_epe_vote_from_capital_allocator(capital_result))

    risk_payload = {"bot": bot_norm, "symbol": symbol_norm, "side": side_norm, "entry": entry_f, "stop": stop_f, "setup": setup, "mode": mode_norm, "intended_live": intended_live_bool, "notional_usdt": suggested_notional, "margin_usdt": suggested_margin, "leverage": leverage_i, "risk_pct": effective_risk_pct, "source": "execution_policy_engine_v1"}
    try:
        risk_result = can_open_trade_decision(risk_payload)
    except Exception as exc:
        risk_result = {"allowed": False, "decision": "DENY", "reasons": [f"Erro no Risk Manager: {exc}"], "warnings": []}
    votes.append(_epe_vote_from_risk_manager(risk_result))

    live_context = sizing_payload.get("live_context") or {}
    live_enabled = bool(live_context.get("real_trading_enabled"))
    if intended_live_bool and not live_enabled:
        votes.append(_epe_vote("Live Execution Context", "WAIT", 1.0, "Trade solicitado como LIVE, mas real trading está bloqueado ou sem capacidade.", live_context))
    else:
        votes.append(_epe_vote("Live Execution Context", "INFO", 0.4, "Contexto LIVE usado apenas como trava informativa nesta avaliação consultiva.", live_context))

    final_decision = _epe_final_decision(votes, sizing_item=sizing_item, intended_live=intended_live_bool, real_trading_enabled=live_enabled)
    confidence = _epe_confidence_score(votes, final_decision, sizing_item=sizing_item)
    execution_action = {"ALLOW": "ALLOW_OBSERVATION", "REDUCE": "ALLOW_REDUCED_SIZE_OBSERVATION", "WAIT": "WAIT_OR_VERIFY_OBSERVATION", "DENY": "DENY_OBSERVATION"}.get(final_decision, "WAIT_OR_VERIFY_OBSERVATION")

    reasons = [v.get("reason") for v in votes if str(v.get("vote") or "").upper() == final_decision and v.get("reason")]
    if not reasons:
        reasons = [v.get("reason") for v in votes if str(v.get("vote") or "").upper() in {"DENY", "WAIT", "REDUCE"} and v.get("reason")]
    if sizing_item and (sizing_item.get("binding_limit") or {}).get("name"):
        reasons.append(f"Sizing limitado por {(sizing_item.get('binding_limit') or {}).get('name')}.")
    if not reasons:
        reasons = ["Decisão gerada pela consolidação dos módulos consultivos."]

    payload = {
        "ok": True,
        "version": EXECUTION_POLICY_ENGINE_V1_VERSION,
        "generated_at": data_hora_sp_str(),
        "mode": EXECUTION_POLICY_ENGINE_V1_MODE,
        "capital": capital,
        "inputs": {"bot": bot_norm, "symbol": symbol_norm, "setup": setup, "side": side_norm, "entry": entry_f, "stop": stop_f, "leverage": leverage_i, "execution_mode": mode_norm, "intended_live": intended_live_bool},
        "decision": final_decision,
        "execution_action": execution_action,
        "confidence_score": confidence,
        "recommended_order": {"bot": bot_norm, "symbol": symbol_norm, "side": side_norm, "entry": entry_f, "stop": stop_f, "setup": setup, "leverage": leverage_i, "paper_notional_usdt": round(suggested_notional, 4), "paper_margin_usdt": round(suggested_margin, 4), "paper_qty": suggested_qty, "paper_effective_risk_usdt": round(effective_risk_usdt, 4), "paper_effective_risk_pct": round(effective_risk_pct, 4), "live_allowed": (sizing_item or {}).get("live_allowed"), "live_notional_usdt": (sizing_item or {}).get("live_suggested_notional_usdt"), "live_block_reason": (sizing_item or {}).get("live_block_reason"), "correlation_adjusted": correlation_adjusted, "correlation_multiplier": round(correlation_multiplier, 4)},
        "sizing": sizing_item,
        "correlation": correlation_payload,
        "correlation_policy": correlation_policy or {},
        "capital_allocator": capital_result,
        "risk_manager": risk_result[0] if isinstance(risk_result, tuple) else risk_result,
        "votes": votes,
        "reasons": reasons[:8],
        "alerts": list(dict.fromkeys((sizing_payload.get("alerts") or []) + (correlation_payload.get("alerts") or [] if isinstance(correlation_payload, dict) else []) + (["Correlation Gate aplicou compressão ao tamanho sugerido."] if correlation_adjusted else []) + (["Decisão final contém DENY consultivo."] if final_decision == "DENY" else []) + (["Decisão final exige REDUCE/WAIT antes de qualquer execução."] if final_decision in {"REDUCE", "WAIT"} else []))),
        "notes": ["Execution Policy Engine V1 está em modo consultivo/observação.", "Não executa ordens, não altera lote real, não altera risco real e não envia ordem para a corretora.", "Consolida Market Regime, Meta Strategy, Correlation Gate, Risk Manager, Capital Allocator, Dynamic Risk Budget e Dynamic Position Sizing em uma decisão única.", "A decisão final é auditável por votos de cada módulo.", "Preparado para alimentar OMS e Executor no futuro."],
    }
    EXECUTION_POLICY_ENGINE_V1_CACHE = {"last_generated_at": payload.get("generated_at"), "last_capital": capital, "last_decision": payload.get("decision")}
    return payload


def build_execution_policy_v1_text(capital=10000.0, bot=None, symbol=None, side=None, entry=None, stop=None, setup=None, leverage=None, mode=None, intended_live=None):
    payload = build_execution_policy_v1(capital=capital, bot=bot, symbol=symbol, side=side, entry=entry, stop=stop, setup=setup, leverage=leverage, mode=mode, intended_live=intended_live)
    inp = payload.get("inputs") or {}
    order = payload.get("recommended_order") or {}
    sizing = payload.get("sizing") or {}
    binding = sizing.get("binding_limit") or {}
    lines = [
        "🧠 EXECUTION POLICY ENGINE V1 — CENTRAL QUANT",
        f"Data/hora: {payload.get('generated_at')}",
        f"Versão: {payload.get('version')}",
        f"Modo: {payload.get('mode')}",
        "",
        "Trade avaliado:",
        f"Bot: {inp.get('bot')} | Setup: {inp.get('setup')}",
        f"Ativo: {inp.get('symbol')} | Side: {inp.get('side')}",
        f"Entrada: {inp.get('entry')} | Stop: {inp.get('stop')} | Leverage: {inp.get('leverage')}x",
        f"Execution mode: {inp.get('execution_mode')} | Intended LIVE: {inp.get('intended_live')}",
        "",
        "Decisão final:",
        f"Decision: {payload.get('decision')}",
        f"Execution action: {payload.get('execution_action')}",
        f"Confidence: {payload.get('confidence_score')}/100",
        "",
        "Ordem sugerida:",
        f"Paper notional: {order.get('paper_notional_usdt')} USDT",
        f"Paper margem: {order.get('paper_margin_usdt')} USDT",
        f"Paper qty: {order.get('paper_qty')}",
        f"Risco efetivo paper: {order.get('paper_effective_risk_usdt')} USDT ({order.get('paper_effective_risk_pct')}%)",
        f"LIVE permitido: {order.get('live_allowed')} | LIVE notional: {order.get('live_notional_usdt')} | motivo: {order.get('live_block_reason')}",
        "",
        "Sizing e limitadores:",
        f"Prioridade estratégica: {sizing.get('strategic_priority')} | Tamanho executável: {sizing.get('executable_size_state')}",
        f"Risk per trade: {sizing.get('risk_per_trade_pct')}% ({sizing.get('risk_per_trade_usdt')} USDT)",
        f"Stop distance: {sizing.get('stop_distance_pct')}% ({sizing.get('stop_distance_source')})",
        f"Raw notional necessário: {sizing.get('raw_notional_usdt')} USDT",
        f"Limitador dominante: {binding.get('name')} ({binding.get('value_usdt')} USDT)",
        f"Uso do risk per trade: {sizing.get('risk_budget_utilization_pct')}% | Risco não usado: {sizing.get('unused_risk_per_trade_usdt')} USDT",
    ]
    if payload.get("alerts"):
        lines += ["", "Alertas:"] + [f"- {x}" for x in payload.get("alerts", [])[:8]]
    lines += ["", "Votos dos módulos:"]
    for v in payload.get("votes") or []:
        lines.append(f"- {v.get('module')}: {v.get('vote')} | {v.get('reason')}")
    lines += ["", "Motivos principais:"] + [f"- {x}" for x in payload.get("reasons", [])]
    lines += ["", "Notas:"] + [f"- {x}" for x in payload.get("notes", [])]
    return "\n".join(lines), payload


@app.route("/execution/policy/v1", methods=["GET", "POST"])
@app.route("/executionpolicy/v1", methods=["GET", "POST"])
@app.route("/policy/execution/v1", methods=["GET", "POST"])
@app.route("/policy/v1", methods=["GET", "POST"])
@app.route("/can_execute_trade", methods=["GET", "POST"])
def execution_policy_v1_route():
    body = request.get_json(silent=True) or {}
    args_payload = _epe_request_payload_from_args(body)
    capital = _epe_safe_float(args_payload.get("capital"), 10000.0)
    as_text = str(request.args.get("format", request.args.get("text", ""))).strip().lower() in {"1", "true", "yes", "sim", "on", "text", "txt"}
    text, payload = build_execution_policy_v1_text(capital=capital, bot=args_payload.get("bot"), symbol=args_payload.get("symbol"), side=args_payload.get("side"), entry=args_payload.get("entry"), stop=args_payload.get("stop"), setup=args_payload.get("setup"), leverage=args_payload.get("leverage"), mode=args_payload.get("mode"), intended_live=args_payload.get("intended_live"))
    if as_text:
        return text
    return {"ok": True, "text": text, "payload": payload}


@app.route("/execution/policy/summary/v1", methods=["GET", "POST"])
@app.route("/executionpolicy/summary/v1", methods=["GET", "POST"])
@app.route("/policy/summary/v1", methods=["GET", "POST"])
def execution_policy_v1_summary_route():
    body = request.get_json(silent=True) or {}
    args_payload = _epe_request_payload_from_args(body)
    capital = _epe_safe_float(args_payload.get("capital"), 10000.0)
    payload = build_execution_policy_v1(capital=capital, bot=args_payload.get("bot"), symbol=args_payload.get("symbol"), side=args_payload.get("side"), entry=args_payload.get("entry"), stop=args_payload.get("stop"), setup=args_payload.get("setup"), leverage=args_payload.get("leverage"), mode=args_payload.get("mode"), intended_live=args_payload.get("intended_live"))
    return {"ok": True, "version": payload.get("version"), "generated_at": payload.get("generated_at"), "mode": payload.get("mode"), "inputs": payload.get("inputs"), "decision": payload.get("decision"), "execution_action": payload.get("execution_action"), "confidence_score": payload.get("confidence_score"), "recommended_order": payload.get("recommended_order"), "votes": payload.get("votes"), "reasons": payload.get("reasons"), "alerts": payload.get("alerts"), "cache": {"last_generated_at": EXECUTION_POLICY_ENGINE_V1_CACHE.get("last_generated_at"), "last_capital": EXECUTION_POLICY_ENGINE_V1_CACHE.get("last_capital")}}


@app.route("/execution/health")
def api_execution_health():
    return execution_health()


@app.route("/execution/plan", methods=["GET", "POST"])
def api_execution_plan():
    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
    else:
        payload = {
            "decision": request.args.get("decision", "ALLOW"),
            "bot": request.args.get("bot", "DONKEY"),
            "setup": request.args.get("setup", "DONKEY"),
            "symbol": request.args.get("symbol", "ETHUSDT"),
            "side": request.args.get("side", "LONG"),
            "entry": request.args.get("entry", 3500),
            "sl": request.args.get("sl", 3430),
            "tp50": request.args.get("tp50", 3570),
            "risk_pct": request.args.get("risk_pct", 2.0),
            "mode": request.args.get("mode"),
            "requested_qty": request.args.get("requested_qty", 0.1),
            "capital_allocated": request.args.get("capital_allocated", 4500),
        }

    return orchestrate_execution(
        payload=payload,
        mode=payload.get("mode"),
        requested_qty=payload.get("requested_qty"),
        capital_allocated=payload.get("capital_allocated"),
        dry_run=True,
    )


@app.route("/execution/log")
def api_execution_log():
    try:
        limit = int(request.args.get("limit", 20))
    except Exception:
        limit = 20
    return read_execution_log(limit=limit)



# ==========================================================
# DECISION SCORE ENGINE V1 - CENTRAL QUANT
# ==========================================================

DECISION_SCORE_ENGINE_V1_VERSION = "2026-07-04-DECISION-SCORE-ENGINE-V1"
DECISION_SCORE_ENGINE_V1_MODE = "OBSERVATION_ONLY"
DECISION_SCORE_ENGINE_V1_CACHE = {"last_payload": None, "last_generated_at": None, "last_capital": None}

DECISION_SCORE_ENGINE_V1_WEIGHTS = {
    "Input Validation": 8.0,
    "Dynamic Position Sizing V1.1": 18.0,
    "Portfolio Advisor / Risk Budget": 17.0,
    "Capital Allocator": 15.0,
    "Correlation Engine V1": 20.0,
    "Risk Manager Global": 30.0,
    "Live Execution Context": 5.0,
}

DECISION_SCORE_ENGINE_V1_POINTS = {
    "ALLOW": 100.0,
    "REDUCE": 67.0,
    "WAIT": 45.0,
    "DENY": 0.0,
    "INFO": 55.0,
}


def _dse_safe_float(value, default=0.0):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _dse_clip(value, low, high):
    return max(float(low), min(float(high), float(value)))


def _dse_vote_weight(vote):
    module = str((vote or {}).get("module") or "").strip()
    return float(DECISION_SCORE_ENGINE_V1_WEIGHTS.get(module, _dse_safe_float((vote or {}).get("weight"), 1.0) * 10.0))


def _dse_vote_points(vote):
    raw_vote = str((vote or {}).get("vote") or "INFO").upper().strip()
    return float(DECISION_SCORE_ENGINE_V1_POINTS.get(raw_vote, 45.0))


def _dse_adjust_vote_points(vote, execution_payload=None):
    """Ajustes pequenos para tornar o score mais explicativo sem substituir o voto original."""
    vote = vote or {}
    module = str(vote.get("module") or "")
    raw_vote = str(vote.get("vote") or "INFO").upper().strip()
    points = _dse_vote_points(vote)
    adjustments = []

    if module == "Dynamic Position Sizing V1.1":
        details = vote.get("details") or {}
        util = _dse_safe_float(details.get("risk_budget_utilization_pct"), None)
        if util is not None:
            if util < 2:
                points -= 7
                adjustments.append("uso do risk budget muito baixo")
            elif util < 10:
                points -= 3
                adjustments.append("uso do risk budget baixo")
            elif util > 75 and raw_vote in {"ALLOW", "REDUCE"}:
                points += 3
                adjustments.append("uso do risk budget saudável")
        executable = str(details.get("executable_size_state") or "").upper()
        if "CAP_LIMITED" in executable:
            points -= 4
            adjustments.append("tamanho limitado por cap")

    if module == "Risk Manager Global":
        details = vote.get("details") or {}
        reasons = " ".join([str(x) for x in details.get("reasons") or []]).lower()
        if raw_vote == "DENY" and ("concentração" in reasons or "exposição" in reasons):
            points -= 5
            adjustments.append("deny por concentração/exposição")
        if details.get("warnings"):
            points -= 2
            adjustments.append("warnings operacionais")

    if module == "Correlation Engine V1":
        details = vote.get("details") or {}
        mult = _dse_safe_float(details.get("risk_multiplier"), 1.0)
        same_symbol = _dse_safe_float(details.get("same_symbol_count"), 0.0)
        severity = str(details.get("severity") or "").upper()
        if mult < 0.25:
            points -= 8
            adjustments.append("correlação comprime fortemente o risco")
        elif mult < 0.5:
            points -= 4
            adjustments.append("correlação comprime risco")
        if same_symbol > 0:
            points -= 5
            adjustments.append("ativo já possui exposição aberta")
        if severity == "HIGH" and raw_vote in {"REDUCE", "DENY"}:
            points -= 3
            adjustments.append("cluster correlacionado em severidade alta")

    if module == "Live Execution Context":
        # Em OBSERVATION_ONLY, contexto LIVE é informativo, mas se LIVE estivesse pretendido e bloqueado, pesa contra.
        try:
            intended_live = bool(((execution_payload or {}).get("inputs") or {}).get("intended_live"))
            live_ctx = (execution_payload or {}).get("sizing", {}).get("live_caps", {}) or {}
            real_enabled = bool(live_ctx.get("real_trading_enabled"))
            if intended_live and not real_enabled:
                points = min(points, 20.0)
                adjustments.append("LIVE pretendido mas real trading bloqueado")
        except Exception:
            pass

    return round(_dse_clip(points, 0.0, 100.0), 4), adjustments


def _dse_decision_from_score(score, hard_deny=False, hard_wait=False, sizing_action=""):
    sizing_action = str(sizing_action or "").upper()
    if hard_deny:
        return "DENY"
    if "DO_NOT_OPEN" in sizing_action:
        return "DENY"
    if hard_wait and score < 72:
        return "WAIT"
    if score >= 72:
        return "ALLOW"
    if score >= 56:
        return "REDUCE"
    if score >= 42:
        return "WAIT"
    return "DENY"


def _dse_confidence(score, votes, hard_deny=False):
    votes = votes or []
    if not votes:
        return 50.0
    deny_weight = sum(_dse_vote_weight(v) for v in votes if str(v.get("vote") or "").upper() == "DENY")
    allow_weight = sum(_dse_vote_weight(v) for v in votes if str(v.get("vote") or "").upper() == "ALLOW")
    total = sum(_dse_vote_weight(v) for v in votes) or 1.0
    separation = abs(allow_weight - deny_weight) / total
    distance = abs(float(score) - 50.0) / 50.0
    confidence = 45.0 + (distance * 35.0) + (separation * 20.0)
    if hard_deny:
        confidence += 8.0
    return round(_dse_clip(confidence, 0.0, 100.0), 2)


def _dse_request_payload_from_args(default_payload=None):
    p = dict(default_payload or {})
    for key in ["bot", "symbol", "side", "entry", "stop", "setup", "leverage", "capital", "mode", "intended_live"]:
        val = request.args.get(key)
        if val not in [None, ""]:
            p[key] = val
    return p


def build_decision_score_engine_v1(capital=10000.0, bot=None, symbol=None, side=None, entry=None, stop=None, setup=None, leverage=None, mode=None, intended_live=None):
    global DECISION_SCORE_ENGINE_V1_CACHE

    capital = _dse_safe_float(capital, 10000.0)
    execution_payload = build_execution_policy_v1(
        capital=capital,
        bot=bot,
        symbol=symbol,
        side=side,
        entry=entry,
        stop=stop,
        setup=setup,
        leverage=leverage,
        mode=mode,
        intended_live=intended_live,
    )

    votes = execution_payload.get("votes") or []
    module_scores = []
    total_weight = 0.0
    weighted_points = 0.0

    for vote in votes:
        weight = _dse_vote_weight(vote)
        base_points = _dse_vote_points(vote)
        adjusted_points, adjustments = _dse_adjust_vote_points(vote, execution_payload=execution_payload)
        contribution = weight * adjusted_points
        total_weight += weight
        weighted_points += contribution
        module_scores.append({
            "module": vote.get("module"),
            "vote": vote.get("vote"),
            "weight": round(weight, 4),
            "base_points": round(base_points, 4),
            "adjusted_points": round(adjusted_points, 4),
            "contribution": round(contribution, 4),
            "reason": vote.get("reason"),
            "adjustments": adjustments,
            "details": vote.get("details") or {},
        })

    raw_score = (weighted_points / total_weight) if total_weight else 50.0

    sizing = execution_payload.get("sizing") or {}
    risk_manager = execution_payload.get("risk_manager") or {}
    hard_deny = any(str(v.get("vote") or "").upper() == "DENY" and str(v.get("module") or "") == "Risk Manager Global" for v in votes)
    hard_wait = False
    try:
        hard_wait = bool(((execution_payload.get("inputs") or {}).get("intended_live")) and not (((sizing.get("live_caps") or {}).get("real_trading_enabled"))))
    except Exception:
        hard_wait = False

    decision = _dse_decision_from_score(raw_score, hard_deny=hard_deny, hard_wait=hard_wait, sizing_action=sizing.get("sizing_action"))
    confidence = _dse_confidence(raw_score, votes, hard_deny=hard_deny)

    deny_votes = [m for m in module_scores if str(m.get("vote") or "").upper() == "DENY"]
    reduce_votes = [m for m in module_scores if str(m.get("vote") or "").upper() == "REDUCE"]
    allow_votes = [m for m in module_scores if str(m.get("vote") or "").upper() == "ALLOW"]
    wait_votes = [m for m in module_scores if str(m.get("vote") or "").upper() == "WAIT"]

    score_band = "EXCELLENT" if raw_score >= 82 else "GOOD" if raw_score >= 72 else "REDUCE_ZONE" if raw_score >= 56 else "WAIT_ZONE" if raw_score >= 42 else "DENY_ZONE"
    execution_action = {
        "ALLOW": "ALLOW_SCORE_OBSERVATION",
        "REDUCE": "ALLOW_REDUCED_BY_SCORE_OBSERVATION",
        "WAIT": "WAIT_BY_SCORE_OBSERVATION",
        "DENY": "DENY_BY_SCORE_OBSERVATION",
    }.get(decision, "WAIT_BY_SCORE_OBSERVATION")

    reasons = []
    if hard_deny:
        reasons.append("Risk Manager Global gerou hard deny consultivo; decisão final permanece DENY mesmo com módulos favoráveis.")
    if deny_votes:
        reasons.append("Há voto DENY relevante no comitê decisório.")
    if reduce_votes:
        reasons.append("Sizing ou política operacional recomenda redução de tamanho.")
    if allow_votes and not deny_votes:
        reasons.append("Módulos principais favorecem execução consultiva.")
    if sizing.get("binding_limit"):
        binding = sizing.get("binding_limit") or {}
        reasons.append(f"Limitador dominante do sizing: {binding.get('name')} ({binding.get('value_usdt')} USDT).")
    util = _dse_safe_float(sizing.get("risk_budget_utilization_pct"), None)
    if util is not None and util < 10:
        reasons.append(f"Uso efetivo do risk per trade baixo: {round(util, 4)}%.")
    if not reasons:
        reasons.append("Decision Score calculado por ponderação dos votos dos módulos.")

    payload = {
        "ok": True,
        "version": DECISION_SCORE_ENGINE_V1_VERSION,
        "generated_at": data_hora_sp_str(),
        "mode": DECISION_SCORE_ENGINE_V1_MODE,
        "capital": capital,
        "inputs": execution_payload.get("inputs") or {},
        "decision_score": round(raw_score, 2),
        "score_band": score_band,
        "decision": decision,
        "execution_action": execution_action,
        "confidence_score": confidence,
        "hard_deny": bool(hard_deny),
        "hard_wait": bool(hard_wait),
        "execution_policy_decision": execution_payload.get("decision"),
        "execution_policy_confidence": execution_payload.get("confidence_score"),
        "recommended_order": execution_payload.get("recommended_order") or {},
        "sizing": sizing,
        "correlation": execution_payload.get("correlation") or {},
        "correlation_policy": execution_payload.get("correlation_policy") or {},
        "risk_manager": risk_manager,
        "capital_allocator": execution_payload.get("capital_allocator") or {},
        "module_scores": module_scores,
        "vote_summary": {
            "allow": len(allow_votes),
            "reduce": len(reduce_votes),
            "wait": len(wait_votes),
            "deny": len(deny_votes),
            "total_weight": round(total_weight, 4),
            "weighted_points": round(weighted_points, 4),
        },
        "reasons": reasons[:10],
        "alerts": list(dict.fromkeys((execution_payload.get("alerts") or []) + (["Decision Score aplicado com hard deny do Risk Manager."] if hard_deny else []) + (["Decision Score indica redução/espera antes de execução."] if decision in {"REDUCE", "WAIT"} else []))),
        "notes": [
            "Decision Score Engine V1 está em modo consultivo/observação.",
            "Não executa ordens, não altera lote real, não altera risco real e não envia ordem para a corretora.",
            "Converte votos do Execution Policy Engine V1 em pontuação ponderada.",
            "Risk Manager pode atuar como hard deny consultivo quando a regra de risco for crítica.",
            "Preparado para calibração futura dos pesos por histórico de acertos/erros.",
        ],
    }
    DECISION_SCORE_ENGINE_V1_CACHE = {"last_generated_at": payload.get("generated_at"), "last_capital": capital, "last_decision": payload.get("decision"), "last_score": payload.get("decision_score")}
    return payload


def build_decision_score_engine_v1_text(capital=10000.0, bot=None, symbol=None, side=None, entry=None, stop=None, setup=None, leverage=None, mode=None, intended_live=None):
    payload = build_decision_score_engine_v1(capital=capital, bot=bot, symbol=symbol, side=side, entry=entry, stop=stop, setup=setup, leverage=leverage, mode=mode, intended_live=intended_live)
    inp = payload.get("inputs") or {}
    order = payload.get("recommended_order") or {}
    sizing = payload.get("sizing") or {}
    binding = sizing.get("binding_limit") or {}
    lines = [
        "🧮 DECISION SCORE ENGINE V1 — CENTRAL QUANT",
        f"Data/hora: {payload.get('generated_at')}",
        f"Versão: {payload.get('version')}",
        f"Modo: {payload.get('mode')}",
        "",
        "Trade avaliado:",
        f"Bot: {inp.get('bot')} | Setup: {inp.get('setup')}",
        f"Ativo: {inp.get('symbol')} | Side: {inp.get('side')}",
        f"Entrada: {inp.get('entry')} | Stop: {inp.get('stop')} | Leverage: {inp.get('leverage')}x",
        "",
        "Resultado decisório:",
        f"Decision Score: {payload.get('decision_score')}/100 | Faixa: {payload.get('score_band')}",
        f"Decision: {payload.get('decision')} | Action: {payload.get('execution_action')}",
        f"Confidence: {payload.get('confidence_score')}/100",
        f"Hard deny: {payload.get('hard_deny')} | Execution Policy V1: {payload.get('execution_policy_decision')} ({payload.get('execution_policy_confidence')}/100)",
        "",
        "Ordem sugerida:",
        f"Paper notional: {order.get('paper_notional_usdt')} USDT",
        f"Paper margem: {order.get('paper_margin_usdt')} USDT",
        f"Paper qty: {order.get('paper_qty')}",
        f"Risco efetivo paper: {order.get('paper_effective_risk_usdt')} USDT ({order.get('paper_effective_risk_pct')}%)",
        f"LIVE permitido: {order.get('live_allowed')} | LIVE notional: {order.get('live_notional_usdt')} | motivo: {order.get('live_block_reason')}",
        "",
        "Sizing e limitadores:",
        f"Prioridade estratégica: {sizing.get('strategic_priority')} | Tamanho executável: {sizing.get('executable_size_state')}",
        f"Risk per trade: {sizing.get('risk_per_trade_pct')}% ({sizing.get('risk_per_trade_usdt')} USDT)",
        f"Stop distance: {sizing.get('stop_distance_pct')}% ({sizing.get('stop_distance_source')})",
        f"Raw notional necessário: {sizing.get('raw_notional_usdt')} USDT",
        f"Limitador dominante: {binding.get('name')} ({binding.get('value_usdt')} USDT)",
        f"Uso do risk per trade: {sizing.get('risk_budget_utilization_pct')}% | Risco não usado: {sizing.get('unused_risk_per_trade_usdt')} USDT",
        "",
        "Pontuação por módulo:",
    ]
    for item in payload.get("module_scores") or []:
        adj = f" | ajustes: {', '.join(item.get('adjustments') or [])}" if item.get("adjustments") else ""
        lines.append(f"- {item.get('module')}: voto={item.get('vote')} | peso={item.get('weight')} | pontos={item.get('adjusted_points')} | contribuição={item.get('contribution')}{adj}")
        if item.get("reason"):
            lines.append(f"  motivo: {item.get('reason')}")
    if payload.get("alerts"):
        lines += ["", "Alertas:"] + [f"- {x}" for x in payload.get("alerts", [])[:10]]
    lines += ["", "Motivos principais:"] + [f"- {x}" for x in payload.get("reasons", [])]
    lines += ["", "Notas:"] + [f"- {x}" for x in payload.get("notes", [])]
    return "\n".join(lines), payload


@app.route("/decision/score/v1", methods=["GET", "POST"])
@app.route("/decisionscore/v1", methods=["GET", "POST"])
@app.route("/score/decision/v1", methods=["GET", "POST"])
@app.route("/decision-score/v1", methods=["GET", "POST"])
def decision_score_engine_v1_route():
    body = request.get_json(silent=True) or {}
    args_payload = _dse_request_payload_from_args(body)
    capital = _dse_safe_float(args_payload.get("capital"), 10000.0)
    as_text = str(request.args.get("format", request.args.get("text", ""))).strip().lower() in {"1", "true", "yes", "sim", "on", "text", "txt"}
    text, payload = build_decision_score_engine_v1_text(capital=capital, bot=args_payload.get("bot"), symbol=args_payload.get("symbol"), side=args_payload.get("side"), entry=args_payload.get("entry"), stop=args_payload.get("stop"), setup=args_payload.get("setup"), leverage=args_payload.get("leverage"), mode=args_payload.get("mode"), intended_live=args_payload.get("intended_live"))
    if as_text:
        return text
    return {"ok": True, "text": text, "payload": payload}


@app.route("/decision/score/summary/v1", methods=["GET", "POST"])
@app.route("/decisionscore/summary/v1", methods=["GET", "POST"])
@app.route("/score/decision/summary/v1", methods=["GET", "POST"])
def decision_score_engine_v1_summary_route():
    body = request.get_json(silent=True) or {}
    args_payload = _dse_request_payload_from_args(body)
    capital = _dse_safe_float(args_payload.get("capital"), 10000.0)
    payload = build_decision_score_engine_v1(capital=capital, bot=args_payload.get("bot"), symbol=args_payload.get("symbol"), side=args_payload.get("side"), entry=args_payload.get("entry"), stop=args_payload.get("stop"), setup=args_payload.get("setup"), leverage=args_payload.get("leverage"), mode=args_payload.get("mode"), intended_live=args_payload.get("intended_live"))
    return {"ok": True, "version": payload.get("version"), "generated_at": payload.get("generated_at"), "mode": payload.get("mode"), "inputs": payload.get("inputs"), "decision_score": payload.get("decision_score"), "score_band": payload.get("score_band"), "decision": payload.get("decision"), "execution_action": payload.get("execution_action"), "confidence_score": payload.get("confidence_score"), "hard_deny": payload.get("hard_deny"), "recommended_order": payload.get("recommended_order"), "module_scores": payload.get("module_scores"), "vote_summary": payload.get("vote_summary"), "reasons": payload.get("reasons"), "alerts": payload.get("alerts"), "cache": {"last_generated_at": DECISION_SCORE_ENGINE_V1_CACHE.get("last_generated_at"), "last_capital": DECISION_SCORE_ENGINE_V1_CACHE.get("last_capital")}}



# ==========================================================
# ADAPTIVE WEIGHT ENGINE V1 - CENTRAL QUANT
# ==========================================================

ADAPTIVE_WEIGHT_ENGINE_V1_VERSION = "2026-07-04-ADAPTIVE-WEIGHT-ENGINE-V1"
ADAPTIVE_WEIGHT_ENGINE_V1_MODE = "OBSERVATION_ONLY"
ADAPTIVE_WEIGHT_ENGINE_V1_FILE = CENTRAL_DATA_DIR / "adaptive_weight_engine_v1.json"
ADAPTIVE_WEIGHT_ENGINE_V1_CACHE = {"last_payload": None, "last_generated_at": None, "last_capital": None}

ADAPTIVE_WEIGHT_ENGINE_V1_MIN_OBSERVATIONS = int(os.environ.get("ADAPTIVE_WEIGHT_MIN_OBSERVATIONS", "10"))
ADAPTIVE_WEIGHT_ENGINE_V1_MAX_ADJUSTMENT_PCT = float(os.environ.get("ADAPTIVE_WEIGHT_MAX_ADJUSTMENT_PCT", "25"))
ADAPTIVE_WEIGHT_ENGINE_V1_TOTAL_WEIGHT = sum(DECISION_SCORE_ENGINE_V1_WEIGHTS.values())

ADAPTIVE_WEIGHT_ENGINE_V1_MODULE_LIMITS = {
    "Input Validation": {"min": 4.0, "max": 12.0},
    "Dynamic Position Sizing V1.1": {"min": 10.0, "max": 25.0},
    "Portfolio Advisor / Risk Budget": {"min": 10.0, "max": 25.0},
    "Capital Allocator": {"min": 8.0, "max": 22.0},
    "Risk Manager Global": {"min": 22.0, "max": 40.0},
    "Live Execution Context": {"min": 2.0, "max": 10.0},
}


def _awe_safe_float(value, default=0.0):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _awe_clip(value, low, high):
    return max(float(low), min(float(high), float(value)))


def _awe_default_state():
    return {
        "version": ADAPTIVE_WEIGHT_ENGINE_V1_VERSION,
        "created_at": data_hora_sp_str(),
        "updated_at": data_hora_sp_str(),
        "mode": ADAPTIVE_WEIGHT_ENGINE_V1_MODE,
        "modules": {
            module: {
                "module": module,
                "base_weight": float(weight),
                "current_weight": float(weight),
                "observations": 0,
                "correct": 0,
                "wrong": 0,
                "accuracy_pct": None,
                "adjustment_pct": 0.0,
                "source": "BOOTSTRAP_DEFAULT",
            }
            for module, weight in DECISION_SCORE_ENGINE_V1_WEIGHTS.items()
        },
        "notes": [
            "V1 começa em modo consultivo com pesos base do Decision Score Engine V1.",
            "Ajustes automáticos só devem ganhar força após amostra mínima de outcomes rotulados.",
        ],
    }


def _awe_load_state():
    try:
        if ADAPTIVE_WEIGHT_ENGINE_V1_FILE.exists():
            with open(ADAPTIVE_WEIGHT_ENGINE_V1_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                default = _awe_default_state()
                data.setdefault("modules", {})
                for module, base_weight in DECISION_SCORE_ENGINE_V1_WEIGHTS.items():
                    data["modules"].setdefault(module, default["modules"][module])
                return data
    except Exception:
        pass
    return _awe_default_state()


def _awe_save_state(state):
    try:
        state = dict(state or {})
        state["updated_at"] = data_hora_sp_str()
        ADAPTIVE_WEIGHT_ENGINE_V1_FILE.parent.mkdir(exist_ok=True)
        with open(ADAPTIVE_WEIGHT_ENGINE_V1_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def _awe_extract_outcome_records(limit=600):
    """
    Tenta encontrar decisões antigas com outcome explícito.
    Se não houver outcome rotulado, V1 permanece em bootstrap conservador.
    """
    records = []
    paths = [CENTRAL_DECISION_LOG_FILE, CENTRAL_TIMELINE_LOG_FILE, CENTRAL_DATA_DIR / "learning_engine_v1.jsonl"]
    for path in paths:
        try:
            if not path or not Path(path).exists():
                continue
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()[-int(limit):]
            for line in lines:
                try:
                    item = json.loads(line)
                except Exception:
                    continue
                if not isinstance(item, dict):
                    continue
                outcome = item.get("outcome") or item.get("final_outcome") or item.get("trade_outcome") or item.get("result_label")
                if outcome is None:
                    # Alguns logs usam result, mas muitas vezes é apenas ALLOW/DENY. Só aceita se parecer resultado de trade.
                    raw_result = str(item.get("trade_result") or item.get("pnl_result") or "").upper().strip()
                    outcome = raw_result if raw_result in {"WIN", "LOSS", "BE", "BREAKEVEN", "TP", "SL", "STOP", "PROFIT", "LOSS"} else None
                if outcome is None:
                    continue
                decision = str(item.get("decision") or item.get("policy_decision") or item.get("execution_decision") or "").upper().strip()
                records.append({"decision": decision, "outcome": str(outcome).upper().strip(), "raw": item})
        except Exception:
            continue
    return records[-int(limit):]


def _awe_estimate_module_stats_from_outcomes(records):
    """
    Estima acerto por módulo a partir de outcomes rotulados.
    Quando o Learning/Outcome Evaluator fornece module_outcomes/module_evaluations,
    usa a atribuição por módulo. Se não houver, cai no proxy conservador pela decisão final.
    """
    stats = {module: {"observations": 0, "correct": 0, "wrong": 0} for module in DECISION_SCORE_ENGINE_V1_WEIGHTS.keys()}
    if not records:
        return stats

    positive = {"WIN", "TP", "PROFIT", "BREAKEVEN", "BE"}
    negative = {"LOSS", "SL", "STOP"}
    for record in records:
        raw = record.get("raw") if isinstance(record.get("raw"), dict) else record
        module_rows = []
        if isinstance(raw, dict):
            module_rows = raw.get("module_outcomes") or raw.get("module_evaluations") or []
        used_module_rows = False
        for row in module_rows or []:
            module = row.get("module")
            if module not in stats:
                continue
            correct = row.get("correct")
            if correct is None:
                continue
            used_module_rows = True
            stats[module]["observations"] += 1
            if correct is True:
                stats[module]["correct"] += 1
            else:
                stats[module]["wrong"] += 1
        if used_module_rows:
            continue

        outcome = str(record.get("outcome") or "").upper().strip()
        decision = str(record.get("decision") or "").upper().strip()
        if outcome not in positive | negative or decision not in {"ALLOW", "REDUCE", "WAIT", "DENY"}:
            continue
        good_decision = (decision in {"ALLOW", "REDUCE"} and outcome in positive) or (decision in {"WAIT", "DENY"} and outcome in negative)
        for module in stats:
            stats[module]["observations"] += 1
            if good_decision:
                stats[module]["correct"] += 1
            else:
                stats[module]["wrong"] += 1
    return stats


def _awe_recommend_weights(state=None):
    state = state or _awe_load_state()
    records = _awe_extract_outcome_records()
    inferred_stats = _awe_estimate_module_stats_from_outcomes(records)

    table = []
    recommended = {}
    for module, base_weight in DECISION_SCORE_ENGINE_V1_WEIGHTS.items():
        stored = (state.get("modules") or {}).get(module) or {}
        observations = int(stored.get("observations") or 0)
        correct = int(stored.get("correct") or 0)
        wrong = int(stored.get("wrong") or 0)

        # Se ainda não há stats persistidos, usa apenas outcomes rotulados detectados como sombra.
        if observations <= 0 and inferred_stats.get(module, {}).get("observations", 0) > 0:
            observations = int(inferred_stats[module]["observations"])
            correct = int(inferred_stats[module]["correct"])
            wrong = int(inferred_stats[module]["wrong"])
            source = "INFERRED_FROM_OUTCOME_LOGS"
        else:
            source = stored.get("source") or "BOOTSTRAP_DEFAULT"

        accuracy = (correct / observations * 100.0) if observations > 0 else None
        if observations >= ADAPTIVE_WEIGHT_ENGINE_V1_MIN_OBSERVATIONS and accuracy is not None:
            # Baseline neutro 55%; acima aumenta, abaixo reduz. Ajuste máximo controlado.
            raw_adjustment = ((accuracy - 55.0) / 45.0) * ADAPTIVE_WEIGHT_ENGINE_V1_MAX_ADJUSTMENT_PCT
            adjustment_pct = _awe_clip(raw_adjustment, -ADAPTIVE_WEIGHT_ENGINE_V1_MAX_ADJUSTMENT_PCT, ADAPTIVE_WEIGHT_ENGINE_V1_MAX_ADJUSTMENT_PCT)
            evidence = "ACTIVE_ADAPTIVE"
        else:
            adjustment_pct = 0.0
            evidence = "BOOTSTRAP_WAIT_SAMPLE"

        raw_weight = float(base_weight) * (1.0 + adjustment_pct / 100.0)
        limits = ADAPTIVE_WEIGHT_ENGINE_V1_MODULE_LIMITS.get(module, {"min": 1.0, "max": 50.0})
        bounded_weight = _awe_clip(raw_weight, limits.get("min", 1.0), limits.get("max", 50.0))
        recommended[module] = bounded_weight
        table.append({
            "module": module,
            "base_weight": round(float(base_weight), 4),
            "raw_recommended_weight": round(raw_weight, 4),
            "recommended_weight_pre_normalization": round(bounded_weight, 4),
            "observations": observations,
            "correct": correct,
            "wrong": wrong,
            "accuracy_pct": round(accuracy, 2) if accuracy is not None else None,
            "adjustment_pct": round(adjustment_pct, 4),
            "evidence": evidence,
            "source": source,
            "limits": limits,
        })

    current_total = sum(recommended.values()) or ADAPTIVE_WEIGHT_ENGINE_V1_TOTAL_WEIGHT
    normalization_factor = ADAPTIVE_WEIGHT_ENGINE_V1_TOTAL_WEIGHT / current_total
    normalized = {module: round(weight * normalization_factor, 4) for module, weight in recommended.items()}

    for item in table:
        module = item["module"]
        item["recommended_weight"] = normalized.get(module, item["base_weight"])
        item["delta_weight"] = round(item["recommended_weight"] - item["base_weight"], 4)

    return {
        "weights": normalized,
        "table": table,
        "normalization_factor": round(normalization_factor, 6),
        "outcome_records_detected": len(records),
        "total_weight": round(sum(normalized.values()), 4),
    }


def _awe_score_with_weights(decision_payload, adaptive_weights):
    module_scores = decision_payload.get("module_scores") or []
    weighted_points = 0.0
    total_weight = 0.0
    adaptive_module_scores = []
    for item in module_scores:
        module = item.get("module")
        weight = _awe_safe_float(adaptive_weights.get(module), _awe_safe_float(item.get("weight"), 1.0))
        points = _awe_safe_float(item.get("adjusted_points"), 50.0)
        contribution = weight * points
        weighted_points += contribution
        total_weight += weight
        clone = dict(item)
        clone["base_weight_from_decision_score"] = item.get("weight")
        clone["adaptive_weight"] = round(weight, 4)
        clone["adaptive_contribution"] = round(contribution, 4)
        adaptive_module_scores.append(clone)
    score = (weighted_points / total_weight) if total_weight else _awe_safe_float(decision_payload.get("decision_score"), 50.0)
    return round(score, 2), round(weighted_points, 4), round(total_weight, 4), adaptive_module_scores


def build_adaptive_weight_engine_v1(capital=10000.0, bot=None, symbol=None, side=None, entry=None, stop=None, setup=None, leverage=None, mode=None, intended_live=None, persist=False):
    global ADAPTIVE_WEIGHT_ENGINE_V1_CACHE
    capital = _awe_safe_float(capital, 10000.0)
    state = _awe_load_state()
    recommendation = _awe_recommend_weights(state)
    adaptive_weights = recommendation.get("weights") or dict(DECISION_SCORE_ENGINE_V1_WEIGHTS)

    decision_payload = build_decision_score_engine_v1(
        capital=capital,
        bot=bot,
        symbol=symbol,
        side=side,
        entry=entry,
        stop=stop,
        setup=setup,
        leverage=leverage,
        mode=mode,
        intended_live=intended_live,
    )
    adaptive_score, weighted_points, total_weight, adaptive_module_scores = _awe_score_with_weights(decision_payload, adaptive_weights)
    sizing = decision_payload.get("sizing") or {}
    hard_deny = bool(decision_payload.get("hard_deny"))
    hard_wait = bool(decision_payload.get("hard_wait"))
    adaptive_decision = _dse_decision_from_score(adaptive_score, hard_deny=hard_deny, hard_wait=hard_wait, sizing_action=sizing.get("sizing_action"))
    adaptive_action = {
        "ALLOW": "ALLOW_ADAPTIVE_SCORE_OBSERVATION",
        "REDUCE": "ALLOW_REDUCED_ADAPTIVE_SCORE_OBSERVATION",
        "WAIT": "WAIT_ADAPTIVE_SCORE_OBSERVATION",
        "DENY": "DENY_ADAPTIVE_SCORE_OBSERVATION",
    }.get(adaptive_decision, "WAIT_ADAPTIVE_SCORE_OBSERVATION")
    adaptive_confidence = _dse_confidence(adaptive_score, decision_payload.get("votes") or [], hard_deny=hard_deny)

    active_adjustments = [x for x in recommendation.get("table") or [] if abs(_awe_safe_float(x.get("delta_weight"), 0.0)) > 0.001]
    evidence_quality = "ACTIVE" if any((x.get("evidence") == "ACTIVE_ADAPTIVE") for x in recommendation.get("table") or []) else "BOOTSTRAP_INSUFFICIENT_OUTCOME_SAMPLE"

    reasons = []
    if evidence_quality.startswith("BOOTSTRAP"):
        reasons.append("Ainda não há amostra suficiente de outcomes rotulados; pesos permanecem próximos do padrão do Decision Score Engine V1.")
    else:
        reasons.append("Pesos ajustados por histórico de outcomes rotulados acima da amostra mínima.")
    if hard_deny:
        reasons.append("Hard deny do Risk Manager permanece soberano mesmo com pesos adaptativos.")
    if active_adjustments:
        reasons.append(f"{len(active_adjustments)} módulo(s) tiveram ajuste de peso recomendado.")
    else:
        reasons.append("Nenhum ajuste de peso ativo aplicado nesta leitura.")

    payload = {
        "ok": True,
        "version": ADAPTIVE_WEIGHT_ENGINE_V1_VERSION,
        "generated_at": data_hora_sp_str(),
        "mode": ADAPTIVE_WEIGHT_ENGINE_V1_MODE,
        "capital": capital,
        "inputs": decision_payload.get("inputs") or {},
        "evidence_quality": evidence_quality,
        "outcome_records_detected": recommendation.get("outcome_records_detected"),
        "min_observations_required": ADAPTIVE_WEIGHT_ENGINE_V1_MIN_OBSERVATIONS,
        "base_decision_score_version": decision_payload.get("version"),
        "base_decision_score": decision_payload.get("decision_score"),
        "base_decision": decision_payload.get("decision"),
        "base_confidence": decision_payload.get("confidence_score"),
        "adaptive_decision_score": adaptive_score,
        "adaptive_decision": adaptive_decision,
        "adaptive_execution_action": adaptive_action,
        "adaptive_confidence_score": adaptive_confidence,
        "hard_deny": hard_deny,
        "hard_wait": hard_wait,
        "weight_total": total_weight,
        "weighted_points": weighted_points,
        "weights": adaptive_weights,
        "weight_table": recommendation.get("table") or [],
        "adaptive_module_scores": adaptive_module_scores,
        "recommended_order": decision_payload.get("recommended_order") or {},
        "sizing": sizing,
        "risk_manager": decision_payload.get("risk_manager") or {},
        "capital_allocator": decision_payload.get("capital_allocator") or {},
        "alerts": list(dict.fromkeys((decision_payload.get("alerts") or []) + (["Adaptive Weight Engine está em bootstrap; pesos ainda não foram alterados por falta de outcomes suficientes."] if evidence_quality.startswith("BOOTSTRAP") else ["Adaptive Weight Engine aplicou pesos ajustados por histórico."])))[:12],
        "reasons": reasons[:10],
        "notes": [
            "Adaptive Weight Engine V1 está em modo consultivo/observação.",
            "Não altera execução, lote, risco real ou permissões operacionais.",
            "Calcula pesos recomendados para o Decision Score Engine com base em histórico rotulado quando disponível.",
            "Sem amostra suficiente, mantém pesos base e informa estado BOOTSTRAP.",
            "Preparado para futura calibração automática de pesos por acerto/erro dos módulos.",
        ],
    }
    if persist:
        new_state = _awe_load_state()
        for item in recommendation.get("table") or []:
            module = item.get("module")
            if module:
                new_state.setdefault("modules", {}).setdefault(module, {})
                new_state["modules"][module].update({
                    "module": module,
                    "base_weight": item.get("base_weight"),
                    "current_weight": item.get("recommended_weight"),
                    "observations": item.get("observations"),
                    "correct": item.get("correct"),
                    "wrong": item.get("wrong"),
                    "accuracy_pct": item.get("accuracy_pct"),
                    "adjustment_pct": item.get("adjustment_pct"),
                    "source": item.get("source"),
                })
        new_state["last_payload_summary"] = {
            "generated_at": payload.get("generated_at"),
            "adaptive_decision_score": payload.get("adaptive_decision_score"),
            "adaptive_decision": payload.get("adaptive_decision"),
            "evidence_quality": payload.get("evidence_quality"),
        }
        payload["state_saved"] = _awe_save_state(new_state)
    else:
        payload["state_saved"] = False

    ADAPTIVE_WEIGHT_ENGINE_V1_CACHE = {"last_generated_at": payload.get("generated_at"), "last_capital": capital, "last_decision": payload.get("adaptive_decision")}
    return payload


def build_adaptive_weight_engine_v1_text(capital=10000.0, bot=None, symbol=None, side=None, entry=None, stop=None, setup=None, leverage=None, mode=None, intended_live=None, persist=False):
    payload = build_adaptive_weight_engine_v1(capital=capital, bot=bot, symbol=symbol, side=side, entry=entry, stop=stop, setup=setup, leverage=leverage, mode=mode, intended_live=intended_live, persist=persist)
    inp = payload.get("inputs") or {}
    order = payload.get("recommended_order") or {}
    sizing = payload.get("sizing") or {}
    lines = [
        "⚖️ ADAPTIVE WEIGHT ENGINE V1 — CENTRAL QUANT",
        f"Data/hora: {payload.get('generated_at')}",
        f"Versão: {payload.get('version')}",
        f"Modo: {payload.get('mode')}",
        "",
        "Trade avaliado:",
        f"Bot: {inp.get('bot')} | Setup: {inp.get('setup')}",
        f"Ativo: {inp.get('symbol')} | Side: {inp.get('side')}",
        f"Entrada: {inp.get('entry')} | Stop: {inp.get('stop')} | Leverage: {inp.get('leverage')}x",
        "",
        "Resultado adaptativo:",
        f"Base Decision Score: {payload.get('base_decision_score')}/100 | Decisão base: {payload.get('base_decision')} | Confiança base: {payload.get('base_confidence')}/100",
        f"Adaptive Decision Score: {payload.get('adaptive_decision_score')}/100 | Decisão adaptativa: {payload.get('adaptive_decision')}",
        f"Action: {payload.get('adaptive_execution_action')} | Confiança adaptativa: {payload.get('adaptive_confidence_score')}/100",
        f"Hard deny: {payload.get('hard_deny')} | Evidência: {payload.get('evidence_quality')}",
        f"Outcomes detectados: {payload.get('outcome_records_detected')} | Mínimo para adaptar: {payload.get('min_observations_required')}",
        "",
        "Ordem sugerida:",
        f"Paper notional: {order.get('paper_notional_usdt')} USDT | Margem: {order.get('paper_margin_usdt')} USDT | Qty: {order.get('paper_qty')}",
        f"Risco efetivo: {order.get('paper_effective_risk_usdt')} USDT ({order.get('paper_effective_risk_pct')}%)",
        "",
        "Sizing:",
        f"Prioridade estratégica: {sizing.get('strategic_priority')} | Executável: {sizing.get('executable_size_state')}",
        f"Limitador dominante: {(sizing.get('binding_limit') or {}).get('name')} ({(sizing.get('binding_limit') or {}).get('value_usdt')} USDT)",
        f"Uso do risk per trade: {sizing.get('risk_budget_utilization_pct')}%",
        "",
        "Pesos por módulo:",
    ]
    for item in payload.get("weight_table") or []:
        lines.append(
            f"- {item.get('module')}: base {item.get('base_weight')} → recomendado {item.get('recommended_weight')} "
            f"(Δ {item.get('delta_weight')}) | obs={item.get('observations')} | acc={item.get('accuracy_pct')} | {item.get('evidence')}"
        )
    if payload.get("alerts"):
        lines += ["", "Alertas:"] + [f"- {x}" for x in payload.get("alerts", [])[:12]]
    lines += ["", "Motivos principais:"] + [f"- {x}" for x in payload.get("reasons", [])]
    lines += ["", "Notas:"] + [f"- {x}" for x in payload.get("notes", [])]
    return "\n".join(lines), payload


@app.route("/adaptive/weights/v1", methods=["GET", "POST"])
@app.route("/adaptiveweights/v1", methods=["GET", "POST"])
@app.route("/weights/adaptive/v1", methods=["GET", "POST"])
@app.route("/awe/v1", methods=["GET", "POST"])
def adaptive_weight_engine_v1_route():
    body = request.get_json(silent=True) or {}
    args_payload = _dse_request_payload_from_args(body)
    capital = _awe_safe_float(args_payload.get("capital"), 10000.0)
    persist_raw = body.get("persist", request.args.get("persist", ""))
    persist = str(persist_raw).strip().lower() in {"1", "true", "yes", "sim", "on", "save"}
    as_text = str(request.args.get("format", request.args.get("text", ""))).strip().lower() in {"1", "true", "yes", "sim", "on", "text", "txt"}
    text, payload = build_adaptive_weight_engine_v1_text(capital=capital, bot=args_payload.get("bot"), symbol=args_payload.get("symbol"), side=args_payload.get("side"), entry=args_payload.get("entry"), stop=args_payload.get("stop"), setup=args_payload.get("setup"), leverage=args_payload.get("leverage"), mode=args_payload.get("mode"), intended_live=args_payload.get("intended_live"), persist=persist)
    if as_text:
        return text
    return {"ok": True, "text": text, "payload": payload}


@app.route("/adaptive/weights/summary/v1", methods=["GET", "POST"])
@app.route("/adaptiveweights/summary/v1", methods=["GET", "POST"])
@app.route("/awe/summary/v1", methods=["GET", "POST"])
def adaptive_weight_engine_v1_summary_route():
    body = request.get_json(silent=True) or {}
    args_payload = _dse_request_payload_from_args(body)
    capital = _awe_safe_float(args_payload.get("capital"), 10000.0)
    payload = build_adaptive_weight_engine_v1(capital=capital, bot=args_payload.get("bot"), symbol=args_payload.get("symbol"), side=args_payload.get("side"), entry=args_payload.get("entry"), stop=args_payload.get("stop"), setup=args_payload.get("setup"), leverage=args_payload.get("leverage"), mode=args_payload.get("mode"), intended_live=args_payload.get("intended_live"), persist=False)
    return {
        "ok": True,
        "version": payload.get("version"),
        "generated_at": payload.get("generated_at"),
        "mode": payload.get("mode"),
        "inputs": payload.get("inputs"),
        "evidence_quality": payload.get("evidence_quality"),
        "outcome_records_detected": payload.get("outcome_records_detected"),
        "base_decision_score": payload.get("base_decision_score"),
        "base_decision": payload.get("base_decision"),
        "adaptive_decision_score": payload.get("adaptive_decision_score"),
        "adaptive_decision": payload.get("adaptive_decision"),
        "adaptive_confidence_score": payload.get("adaptive_confidence_score"),
        "hard_deny": payload.get("hard_deny"),
        "weights": payload.get("weights"),
        "weight_table": payload.get("weight_table"),
        "recommended_order": payload.get("recommended_order"),
        "reasons": payload.get("reasons"),
        "alerts": payload.get("alerts"),
        "cache": {"last_generated_at": ADAPTIVE_WEIGHT_ENGINE_V1_CACHE.get("last_generated_at"), "last_capital": ADAPTIVE_WEIGHT_ENGINE_V1_CACHE.get("last_capital")},
    }


# ==========================================================
# LEARNING ENGINE V1 - CENTRAL QUANT
# ==========================================================

LEARNING_ENGINE_V1_VERSION = "2026-07-04-LEARNING-ENGINE-V1"
LEARNING_ENGINE_V1_MODE = "OBSERVATION_ONLY"
LEARNING_ENGINE_V1_FILE = CENTRAL_DATA_DIR / "learning_engine_v1.jsonl"
LEARNING_ENGINE_V1_CACHE = {"last_payload": None, "last_generated_at": None, "last_learning_id": None}
LEARNING_ENGINE_V1_DEFAULT_READ_LIMIT = int(os.environ.get("LEARNING_ENGINE_READ_LIMIT", "1000"))


def _le_safe_float(value, default=None):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _le_now_id(prefix="LEARN"):
    try:
        return f"{prefix}-{agora_sp().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8].upper()}"
    except Exception:
        return f"{prefix}-{uuid.uuid4().hex[:12].upper()}"


def _le_append_jsonl(item):
    try:
        LEARNING_ENGINE_V1_FILE.parent.mkdir(exist_ok=True)
        with open(LEARNING_ENGINE_V1_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
        return True, None
    except Exception as exc:
        return False, str(exc)


def _le_read_records(limit=None):
    limit = int(limit or LEARNING_ENGINE_V1_DEFAULT_READ_LIMIT)
    records = []
    try:
        if not LEARNING_ENGINE_V1_FILE.exists():
            return []
        with open(LEARNING_ENGINE_V1_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()[-limit:]
        for line in lines:
            try:
                item = json.loads(line)
            except Exception:
                continue
            if isinstance(item, dict):
                records.append(item)
    except Exception:
        return records
    return records


def _le_normalize_outcome(outcome=None, result_r=None, pnl_pct=None):
    raw = str(outcome or "").upper().strip()
    aliases = {
        "WIN": "WIN", "W": "WIN", "TP": "WIN", "PROFIT": "WIN", "GAIN": "WIN", "LUCRO": "WIN",
        "LOSS": "LOSS", "L": "LOSS", "SL": "LOSS", "STOP": "LOSS", "PREJUIZO": "LOSS", "PREJUÍZO": "LOSS",
        "BE": "BE", "BREAKEVEN": "BE", "BREAK_EVEN": "BE", "0": "BE",
    }
    if raw in aliases:
        return aliases[raw]
    r = _le_safe_float(result_r, None)
    if r is not None:
        if r > 0.05:
            return "WIN"
        if r < -0.05:
            return "LOSS"
        return "BE"
    p = _le_safe_float(pnl_pct, None)
    if p is not None:
        if p > 0.02:
            return "WIN"
        if p < -0.02:
            return "LOSS"
        return "BE"
    return "UNKNOWN"


def _le_vote_direction(vote):
    v = str(vote or "").upper().strip()
    if v in {"ALLOW", "REDUCE"}:
        return "POSITIVE"
    if v in {"DENY", "WAIT"}:
        return "NEGATIVE"
    return "NEUTRAL"


def _le_module_correctness(vote, normalized_outcome):
    direction = _le_vote_direction(vote)
    outcome = str(normalized_outcome or "").upper().strip()
    if outcome == "UNKNOWN" or direction == "NEUTRAL":
        return None
    if outcome == "WIN":
        return direction == "POSITIVE"
    if outcome == "LOSS":
        return direction == "NEGATIVE"
    if outcome == "BE":
        return str(vote or "").upper().strip() in {"REDUCE", "WAIT", "DENY"}
    return None


def _le_find_latest_decision(records, learning_id=None, trade_id=None):
    learning_id = str(learning_id or "").strip()
    trade_id = str(trade_id or "").strip()
    for item in reversed(records or []):
        if item.get("record_type") != "DECISION":
            continue
        if learning_id and str(item.get("learning_id") or "") == learning_id:
            return item
        if trade_id and str(item.get("trade_id") or "") == trade_id:
            return item
    return None


def _le_outcome_stats(records=None):
    records = records if records is not None else _le_read_records()
    decisions = [x for x in records if x.get("record_type") == "DECISION"]
    outcomes = [x for x in records if x.get("record_type") == "OUTCOME"]
    by_module = {}
    by_decision = {}
    for out in outcomes:
        decision = str(out.get("decision") or out.get("adaptive_decision") or "UNKNOWN").upper()
        by_decision.setdefault(decision, {"count": 0, "wins": 0, "losses": 0, "be": 0})
        by_decision[decision]["count"] += 1
        outcome = str(out.get("outcome") or "UNKNOWN").upper()
        if outcome == "WIN":
            by_decision[decision]["wins"] += 1
        elif outcome == "LOSS":
            by_decision[decision]["losses"] += 1
        elif outcome == "BE":
            by_decision[decision]["be"] += 1
        for m in out.get("module_outcomes") or []:
            module = m.get("module") or "UNKNOWN"
            if module not in by_module:
                by_module[module] = {"observations": 0, "correct": 0, "wrong": 0, "neutral": 0, "accuracy_pct": None}
            correct = m.get("correct")
            if correct is None:
                by_module[module]["neutral"] += 1
                continue
            by_module[module]["observations"] += 1
            if correct:
                by_module[module]["correct"] += 1
            else:
                by_module[module]["wrong"] += 1
    for module, stats in by_module.items():
        obs = stats.get("observations") or 0
        stats["accuracy_pct"] = round((stats.get("correct", 0) / obs) * 100.0, 2) if obs else None
    return {
        "records": len(records),
        "decisions": len(decisions),
        "outcomes": len(outcomes),
        "by_module": by_module,
        "by_decision": by_decision,
    }


def build_learning_engine_v1(capital=10000.0, bot=None, symbol=None, side=None, entry=None, stop=None, setup=None, leverage=None, mode=None, intended_live=None, record=False):
    global LEARNING_ENGINE_V1_CACHE
    adaptive = build_adaptive_weight_engine_v1(
        capital=capital,
        bot=bot,
        symbol=symbol,
        side=side,
        entry=entry,
        stop=stop,
        setup=setup,
        leverage=leverage,
        mode=mode,
        intended_live=intended_live,
        persist=False,
    )
    inp = adaptive.get("inputs") or {}
    order = adaptive.get("recommended_order") or {}
    learning_id = _le_now_id("LEARN")
    trade_id = str(inp.get("trade_id") or order.get("trade_id") or f"{inp.get('bot')}:{inp.get('symbol')}:{inp.get('side')}:{learning_id}")
    module_votes = []
    for item in adaptive.get("adaptive_module_scores") or adaptive.get("module_scores") or []:
        module_votes.append({
            "module": item.get("module"),
            "vote": item.get("vote"),
            "weight": item.get("adaptive_weight", item.get("weight")),
            "points": item.get("adjusted_points"),
            "reason": item.get("reason"),
            "details": item.get("details"),
        })
    record_item = {
        "record_type": "DECISION",
        "learning_id": learning_id,
        "trade_id": trade_id,
        "created_at": data_hora_sp_str(),
        "version": LEARNING_ENGINE_V1_VERSION,
        "source": "Learning Engine V1",
        "inputs": inp,
        "decision": adaptive.get("adaptive_decision"),
        "adaptive_decision": adaptive.get("adaptive_decision"),
        "adaptive_decision_score": adaptive.get("adaptive_decision_score"),
        "adaptive_confidence_score": adaptive.get("adaptive_confidence_score"),
        "base_decision": adaptive.get("base_decision"),
        "base_decision_score": adaptive.get("base_decision_score"),
        "hard_deny": adaptive.get("hard_deny"),
        "hard_wait": adaptive.get("hard_wait"),
        "recommended_order": order,
        "sizing": adaptive.get("sizing"),
        "risk_manager": adaptive.get("risk_manager"),
        "capital_allocator": adaptive.get("capital_allocator"),
        "module_votes": module_votes,
        "outcome_status": "PENDING_OUTCOME",
    }
    saved = False
    save_error = None
    if record:
        saved, save_error = _le_append_jsonl(record_item)
    records = _le_read_records()
    stats = _le_outcome_stats(records)
    payload = {
        "ok": True,
        "version": LEARNING_ENGINE_V1_VERSION,
        "mode": LEARNING_ENGINE_V1_MODE,
        "generated_at": data_hora_sp_str(),
        "learning_id": learning_id,
        "trade_id": trade_id,
        "record_saved": saved,
        "record_error": save_error,
        "record_mode": "SAVED" if saved else "PREVIEW_ONLY",
        "decision_record": record_item,
        "adaptive_decision": adaptive.get("adaptive_decision"),
        "adaptive_decision_score": adaptive.get("adaptive_decision_score"),
        "adaptive_confidence_score": adaptive.get("adaptive_confidence_score"),
        "hard_deny": adaptive.get("hard_deny"),
        "recommended_order": order,
        "module_votes": module_votes,
        "learning_stats": stats,
        "alerts": list(adaptive.get("alerts") or []),
        "reasons": [
            "Learning Engine V1 registra decisão, votos, score e ordem sugerida para futura avaliação de outcome.",
            "O outcome ainda precisa ser registrado quando o trade fechar para gerar acertos/erros por módulo.",
        ],
        "notes": [
            "Learning Engine V1 está em modo consultivo/observação.",
            "Não executa ordens e não altera decisões; apenas registra decisões e outcomes rotulados.",
            "Os outcomes registrados alimentam o Adaptive Weight Engine V1 como base de aprendizado.",
            "Use record=true ou POST para salvar uma decisão; use /learning/outcome/v1 para registrar o resultado posterior.",
        ],
    }
    if not record:
        payload["alerts"].append("Prévia não salva. Use record=true ou POST para registrar esta decisão no Learning Engine.")
    LEARNING_ENGINE_V1_CACHE = {"last_generated_at": payload.get("generated_at"), "last_learning_id": learning_id, "last_decision": payload.get("adaptive_decision")}
    return payload


def build_learning_outcome_v1(learning_id=None, trade_id=None, outcome=None, result_r=None, pnl_pct=None, note=None, force=False):
    records = _le_read_records(limit=max(LEARNING_ENGINE_V1_DEFAULT_READ_LIMIT, 5000))
    decision_record = _le_find_latest_decision(records, learning_id=learning_id, trade_id=trade_id)
    normalized = _le_normalize_outcome(outcome=outcome, result_r=result_r, pnl_pct=pnl_pct)
    module_outcomes = []
    if decision_record:
        for vote in decision_record.get("module_votes") or []:
            correct = _le_module_correctness(vote.get("vote"), normalized)
            module_outcomes.append({
                "module": vote.get("module"),
                "vote": vote.get("vote"),
                "correct": correct,
                "points": vote.get("points"),
                "weight": vote.get("weight"),
                "reason": vote.get("reason"),
            })
    item = {
        "record_type": "OUTCOME",
        "learning_id": learning_id or (decision_record or {}).get("learning_id") or _le_now_id("ORPHAN"),
        "trade_id": trade_id or (decision_record or {}).get("trade_id"),
        "created_at": data_hora_sp_str(),
        "version": LEARNING_ENGINE_V1_VERSION,
        "source": "Learning Engine V1",
        "decision_found": decision_record is not None,
        "decision": (decision_record or {}).get("decision"),
        "adaptive_decision": (decision_record or {}).get("adaptive_decision"),
        "adaptive_decision_score": (decision_record or {}).get("adaptive_decision_score"),
        "outcome": normalized,
        "raw_outcome": outcome,
        "result_r": _le_safe_float(result_r, None),
        "pnl_pct": _le_safe_float(pnl_pct, None),
        "note": note,
        "module_outcomes": module_outcomes,
    }
    if normalized == "UNKNOWN" and not force:
        return {
            "ok": False,
            "error": "OUTCOME_UNKNOWN",
            "message": "Informe outcome=WIN/LOSS/BE ou result_r/pnl_pct.",
            "preview": item,
        }
    saved, err = _le_append_jsonl(item)
    stats = _le_outcome_stats(_le_read_records())
    return {
        "ok": saved,
        "version": LEARNING_ENGINE_V1_VERSION,
        "generated_at": data_hora_sp_str(),
        "outcome_saved": saved,
        "error": err,
        "outcome_record": item,
        "learning_stats": stats,
        "notes": [
            "Outcome registrado para calibrar acertos/erros por módulo.",
            "O Adaptive Weight Engine V1 passa a detectar este outcome na próxima leitura.",
        ],
    }


def build_learning_engine_v1_text(payload):
    rec = payload.get("decision_record") or {}
    order = payload.get("recommended_order") or {}
    stats = payload.get("learning_stats") or {}
    lines = [
        "🧬 LEARNING ENGINE V1 — CENTRAL QUANT",
        f"Data/hora: {payload.get('generated_at')}",
        f"Versão: {payload.get('version')}",
        f"Modo: {payload.get('mode')}",
        "",
        "Registro de decisão:",
        f"Learning ID: {payload.get('learning_id')}",
        f"Trade ID: {payload.get('trade_id')}",
        f"Status: {payload.get('record_mode')} | salvo: {payload.get('record_saved')}",
        "",
        "Decisão registrada:",
        f"Decision: {payload.get('adaptive_decision')} | Score: {payload.get('adaptive_decision_score')} | Confidence: {payload.get('adaptive_confidence_score')}",
        f"Hard deny: {payload.get('hard_deny')}",
        "",
        "Ordem sugerida:",
        f"Paper notional: {order.get('paper_notional_usdt')} USDT | Margem: {order.get('paper_margin_usdt')} USDT | Qty: {order.get('paper_qty')}",
        f"Risco efetivo: {order.get('paper_effective_risk_usdt')} USDT ({order.get('paper_effective_risk_pct')}%)",
        "",
        "Votos registrados:",
    ]
    for vote in payload.get("module_votes") or []:
        lines.append(f"- {vote.get('module')}: {vote.get('vote')} | peso={vote.get('weight')} | pontos={vote.get('points')}")
    lines += [
        "",
        "Estatísticas de aprendizado:",
        f"Registros totais: {stats.get('records')} | Decisões: {stats.get('decisions')} | Outcomes: {stats.get('outcomes')}",
    ]
    by_module = stats.get("by_module") or {}
    if by_module:
        lines += ["", "Acurácia por módulo:"]
        for module, item in by_module.items():
            lines.append(f"- {module}: obs={item.get('observations')} | acertos={item.get('correct')} | erros={item.get('wrong')} | acc={item.get('accuracy_pct')}%")
    if payload.get("alerts"):
        lines += ["", "Alertas:"] + [f"- {x}" for x in payload.get("alerts", [])[:12]]
    lines += ["", "Motivos:"] + [f"- {x}" for x in payload.get("reasons", [])]
    lines += ["", "Notas:"] + [f"- {x}" for x in payload.get("notes", [])]
    return "\n".join(lines)


def build_learning_outcome_v1_text(payload):
    item = payload.get("outcome_record") or payload.get("preview") or {}
    stats = payload.get("learning_stats") or {}
    lines = [
        "🏁 LEARNING OUTCOME V1 — CENTRAL QUANT",
        f"Data/hora: {payload.get('generated_at', data_hora_sp_str())}",
        f"Versão: {payload.get('version', LEARNING_ENGINE_V1_VERSION)}",
        "",
        f"OK: {payload.get('ok')}",
        f"Learning ID: {item.get('learning_id')}",
        f"Trade ID: {item.get('trade_id')}",
        f"Decision found: {item.get('decision_found')}",
        f"Decision: {item.get('adaptive_decision') or item.get('decision')}",
        f"Outcome: {item.get('outcome')} | R: {item.get('result_r')} | PnL%: {item.get('pnl_pct')}",
        "",
        "Acerto por módulo:",
    ]
    for m in item.get("module_outcomes") or []:
        lines.append(f"- {m.get('module')}: voto={m.get('vote')} | correto={m.get('correct')}")
    lines += [
        "",
        "Estatísticas:",
        f"Registros: {stats.get('records')} | Decisões: {stats.get('decisions')} | Outcomes: {stats.get('outcomes')}",
    ]
    if payload.get("notes"):
        lines += ["", "Notas:"] + [f"- {x}" for x in payload.get("notes", [])]
    return "\n".join(lines)


@app.route("/learning/engine/v1", methods=["GET", "POST"])
@app.route("/learning/v1", methods=["GET", "POST"])
@app.route("/learn/v1", methods=["GET", "POST"])
def learning_engine_v1_route():
    body = request.get_json(silent=True) or {}
    args_payload = _dse_request_payload_from_args(body)
    capital = _le_safe_float(args_payload.get("capital"), 10000.0)
    record_raw = body.get("record", request.args.get("record", ""))
    record = request.method == "POST" or str(record_raw).strip().lower() in {"1", "true", "yes", "sim", "on", "save", "record"}
    as_text = str(request.args.get("format", request.args.get("text", ""))).strip().lower() in {"1", "true", "yes", "sim", "on", "text", "txt"}
    payload = build_learning_engine_v1(capital=capital, bot=args_payload.get("bot"), symbol=args_payload.get("symbol"), side=args_payload.get("side"), entry=args_payload.get("entry"), stop=args_payload.get("stop"), setup=args_payload.get("setup"), leverage=args_payload.get("leverage"), mode=args_payload.get("mode"), intended_live=args_payload.get("intended_live"), record=record)
    text = build_learning_engine_v1_text(payload)
    if as_text:
        return text
    return {"ok": True, "text": text, "payload": payload}


@app.route("/learning/outcome/v1", methods=["GET", "POST"])
@app.route("/learning/result/v1", methods=["GET", "POST"])
@app.route("/learn/outcome/v1", methods=["GET", "POST"])
def learning_outcome_v1_route():
    body = request.get_json(silent=True) or {}
    learning_id = body.get("learning_id", request.args.get("learning_id"))
    trade_id = body.get("trade_id", request.args.get("trade_id"))
    outcome = body.get("outcome", request.args.get("outcome"))
    result_r = body.get("result_r", request.args.get("result_r"))
    pnl_pct = body.get("pnl_pct", request.args.get("pnl_pct"))
    note = body.get("note", request.args.get("note"))
    force_raw = body.get("force", request.args.get("force", ""))
    force = str(force_raw).strip().lower() in {"1", "true", "yes", "sim", "on"}
    as_text = str(request.args.get("format", request.args.get("text", ""))).strip().lower() in {"1", "true", "yes", "sim", "on", "text", "txt"}
    payload = build_learning_outcome_v1(learning_id=learning_id, trade_id=trade_id, outcome=outcome, result_r=result_r, pnl_pct=pnl_pct, note=note, force=force)
    text = build_learning_outcome_v1_text(payload)
    if as_text:
        return text
    return {"ok": bool(payload.get("ok")), "text": text, "payload": payload}


@app.route("/learning/stats/v1")
@app.route("/learn/stats/v1")
def learning_stats_v1_route():
    limit = request.args.get("limit", default=LEARNING_ENGINE_V1_DEFAULT_READ_LIMIT, type=int)
    records = _le_read_records(limit=limit)
    stats = _le_outcome_stats(records)
    lines = [
        "📚 LEARNING STATS V1 — CENTRAL QUANT",
        f"Data/hora: {data_hora_sp_str()}",
        f"Registros: {stats.get('records')} | Decisões: {stats.get('decisions')} | Outcomes: {stats.get('outcomes')}",
        "",
        "Por módulo:",
    ]
    for module, item in (stats.get("by_module") or {}).items():
        lines.append(f"- {module}: obs={item.get('observations')} | acertos={item.get('correct')} | erros={item.get('wrong')} | neutros={item.get('neutral')} | acc={item.get('accuracy_pct')}%")
    return {"ok": True, "version": LEARNING_ENGINE_V1_VERSION, "text": "\n".join(lines), "payload": stats}


# ==========================================================
# OUTCOME EVALUATOR V1 - CENTRAL QUANT
# ==========================================================

OUTCOME_EVALUATOR_V1_VERSION = "2026-07-04-OUTCOME-EVALUATOR-V1"
OUTCOME_EVALUATOR_V1_MODE = "OBSERVATION_ONLY"
OUTCOME_EVALUATOR_V1_FILE = CENTRAL_DATA_DIR / "outcome_evaluator_v1.jsonl"
OUTCOME_EVALUATOR_V1_CACHE = {"last_payload": None, "last_generated_at": None, "last_learning_id": None}


def _oe_safe_float(value, default=None):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _oe_append_jsonl(path, item):
    try:
        path.parent.mkdir(exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
        return True, None
    except Exception as exc:
        return False, str(exc)


def _oe_read_records(path=None, limit=1000):
    path = path or OUTCOME_EVALUATOR_V1_FILE
    records = []
    try:
        if not path.exists():
            return []
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()[-int(limit or 1000):]
        for line in lines:
            try:
                item = json.loads(line)
            except Exception:
                continue
            if isinstance(item, dict):
                records.append(item)
    except Exception:
        return records
    return records


def _oe_decision_direction(decision):
    d = str(decision or "").upper().strip()
    if d in {"ALLOW", "REDUCE", "ALLOW_BY_SCORE", "ALLOW_ADAPTIVE", "REDUCE_BY_SCORE"}:
        return "POSITIVE"
    if d in {"DENY", "WAIT", "DENY_BY_SCORE", "DENY_ADAPTIVE", "WAIT_BY_SCORE"}:
        return "NEGATIVE"
    return "NEUTRAL"


def _oe_vote_direction(vote):
    v = str(vote or "").upper().strip()
    if v in {"ALLOW", "REDUCE"}:
        return "POSITIVE"
    if v in {"DENY", "WAIT"}:
        return "NEGATIVE"
    return "NEUTRAL"


def _oe_outcome_direction(outcome):
    o = str(outcome or "").upper().strip()
    if o in {"WIN", "TP", "PROFIT", "GAIN", "LUCRO"}:
        return "POSITIVE"
    if o in {"LOSS", "SL", "STOP", "PREJUIZO", "PREJUÍZO"}:
        return "NEGATIVE"
    if o in {"BE", "BREAKEVEN", "BREAK_EVEN"}:
        return "NEUTRAL"
    return "UNKNOWN"


def _oe_correctness_from_direction(signal_direction, outcome_direction, neutral_policy="DEFENSIVE_OK"):
    sd = str(signal_direction or "NEUTRAL").upper()
    od = str(outcome_direction or "UNKNOWN").upper()
    if od == "UNKNOWN" or sd == "NEUTRAL":
        return None
    if od == "POSITIVE":
        return sd == "POSITIVE"
    if od == "NEGATIVE":
        return sd == "NEGATIVE"
    if od == "NEUTRAL":
        if neutral_policy == "DEFENSIVE_OK":
            return sd == "NEGATIVE"
        return None
    return None


def _oe_score_correctness_value(correct):
    if correct is True:
        return 1.0
    if correct is False:
        return -1.0
    return 0.0


def _oe_module_evaluations(decision_record, normalized_outcome):
    outcome_direction = _oe_outcome_direction(normalized_outcome)
    evaluations = []
    total_abs_influence = 0.0
    correct_influence = 0.0
    wrong_influence = 0.0

    for vote in (decision_record or {}).get("module_votes") or []:
        module = vote.get("module") or "UNKNOWN"
        vote_value = vote.get("vote")
        vote_direction = _oe_vote_direction(vote_value)
        correct = _oe_correctness_from_direction(vote_direction, outcome_direction)
        weight = _oe_safe_float(vote.get("weight"), 0.0) or 0.0
        points = _oe_safe_float(vote.get("points"), 50.0) or 0.0
        contribution = round(weight * points, 4)
        influence = abs(contribution)
        total_abs_influence += influence
        if correct is True:
            correct_influence += influence
        elif correct is False:
            wrong_influence += influence
        evaluations.append({
            "module": module,
            "vote": vote_value,
            "vote_direction": vote_direction,
            "outcome_direction": outcome_direction,
            "correct": correct,
            "correctness_score": _oe_score_correctness_value(correct),
            "weight": weight,
            "points": points,
            "contribution": contribution,
            "influence_abs": round(influence, 4),
            "reason": vote.get("reason"),
            "details": vote.get("details"),
        })

    for item in evaluations:
        if total_abs_influence > 0:
            item["influence_pct"] = round((item.get("influence_abs", 0.0) / total_abs_influence) * 100.0, 2)
        else:
            item["influence_pct"] = 0.0

    return {
        "module_evaluations": evaluations,
        "total_abs_influence": round(total_abs_influence, 4),
        "correct_influence": round(correct_influence, 4),
        "wrong_influence": round(wrong_influence, 4),
        "correct_influence_pct": round((correct_influence / total_abs_influence) * 100.0, 2) if total_abs_influence else None,
        "wrong_influence_pct": round((wrong_influence / total_abs_influence) * 100.0, 2) if total_abs_influence else None,
    }


def _oe_evaluator_stats(records=None):
    records = records if records is not None else _oe_read_records(limit=5000)
    by_module = {}
    by_decision = {}
    total = 0
    decisions_correct = 0
    decisions_wrong = 0
    decisions_neutral = 0

    for item in records or []:
        if item.get("record_type") != "OUTCOME_EVALUATION":
            continue
        total += 1
        decision = str(item.get("decision") or "UNKNOWN").upper()
        by_decision.setdefault(decision, {"count": 0, "correct": 0, "wrong": 0, "neutral": 0, "accuracy_pct": None})
        by_decision[decision]["count"] += 1
        dc = item.get("decision_correct")
        if dc is True:
            decisions_correct += 1
            by_decision[decision]["correct"] += 1
        elif dc is False:
            decisions_wrong += 1
            by_decision[decision]["wrong"] += 1
        else:
            decisions_neutral += 1
            by_decision[decision]["neutral"] += 1
        for ev in item.get("module_evaluations") or []:
            module = ev.get("module") or "UNKNOWN"
            by_module.setdefault(module, {
                "observations": 0,
                "correct": 0,
                "wrong": 0,
                "neutral": 0,
                "accuracy_pct": None,
                "avg_influence_pct": 0.0,
                "influence_samples": 0,
            })
            correct = ev.get("correct")
            if correct is True:
                by_module[module]["observations"] += 1
                by_module[module]["correct"] += 1
            elif correct is False:
                by_module[module]["observations"] += 1
                by_module[module]["wrong"] += 1
            else:
                by_module[module]["neutral"] += 1
            if ev.get("influence_pct") is not None:
                n = by_module[module]["influence_samples"]
                old = by_module[module]["avg_influence_pct"]
                val = _oe_safe_float(ev.get("influence_pct"), 0.0) or 0.0
                by_module[module]["avg_influence_pct"] = round(((old * n) + val) / (n + 1), 4)
                by_module[module]["influence_samples"] = n + 1

    for module, stats in by_module.items():
        obs = stats.get("observations") or 0
        stats["accuracy_pct"] = round((stats.get("correct", 0) / obs) * 100.0, 2) if obs else None
    for decision, stats in by_decision.items():
        obs = (stats.get("correct", 0) + stats.get("wrong", 0))
        stats["accuracy_pct"] = round((stats.get("correct", 0) / obs) * 100.0, 2) if obs else None

    return {
        "records": len(records or []),
        "evaluations": total,
        "decision_correct": decisions_correct,
        "decision_wrong": decisions_wrong,
        "decision_neutral": decisions_neutral,
        "decision_accuracy_pct": round((decisions_correct / (decisions_correct + decisions_wrong)) * 100.0, 2) if (decisions_correct + decisions_wrong) else None,
        "by_module": by_module,
        "by_decision": by_decision,
    }


def build_outcome_evaluator_v1(learning_id=None, trade_id=None, outcome=None, result_r=None, pnl_pct=None, note=None, save=True, force=False):
    global OUTCOME_EVALUATOR_V1_CACHE
    records = _le_read_records(limit=max(LEARNING_ENGINE_V1_DEFAULT_READ_LIMIT, 5000))
    decision_record = _le_find_latest_decision(records, learning_id=learning_id, trade_id=trade_id)
    normalized = _le_normalize_outcome(outcome=outcome, result_r=result_r, pnl_pct=pnl_pct)
    outcome_direction = _oe_outcome_direction(normalized)

    if normalized == "UNKNOWN" and not force:
        return {
            "ok": False,
            "version": OUTCOME_EVALUATOR_V1_VERSION,
            "mode": OUTCOME_EVALUATOR_V1_MODE,
            "generated_at": data_hora_sp_str(),
            "error": "OUTCOME_UNKNOWN",
            "message": "Informe outcome=WIN/LOSS/BE ou result_r/pnl_pct.",
            "inputs": {"learning_id": learning_id, "trade_id": trade_id, "outcome": outcome, "result_r": result_r, "pnl_pct": pnl_pct},
        }

    if not decision_record:
        return {
            "ok": False,
            "version": OUTCOME_EVALUATOR_V1_VERSION,
            "mode": OUTCOME_EVALUATOR_V1_MODE,
            "generated_at": data_hora_sp_str(),
            "error": "DECISION_RECORD_NOT_FOUND",
            "message": "Não encontrei decisão registrada para este learning_id/trade_id.",
            "inputs": {"learning_id": learning_id, "trade_id": trade_id, "outcome": normalized, "result_r": result_r, "pnl_pct": pnl_pct},
            "learning_stats": _le_outcome_stats(records),
        }

    decision = str(decision_record.get("adaptive_decision") or decision_record.get("decision") or "UNKNOWN").upper().strip()
    decision_direction = _oe_decision_direction(decision)
    decision_correct = _oe_correctness_from_direction(decision_direction, outcome_direction)
    module_eval_payload = _oe_module_evaluations(decision_record, normalized)

    eval_id = _le_now_id("EVAL")
    evaluation_record = {
        "record_type": "OUTCOME_EVALUATION",
        "evaluation_id": eval_id,
        "learning_id": decision_record.get("learning_id"),
        "trade_id": decision_record.get("trade_id"),
        "created_at": data_hora_sp_str(),
        "version": OUTCOME_EVALUATOR_V1_VERSION,
        "source": "Outcome Evaluator V1",
        "decision": decision,
        "decision_score": decision_record.get("adaptive_decision_score") or decision_record.get("base_decision_score"),
        "decision_direction": decision_direction,
        "decision_correct": decision_correct,
        "outcome": normalized,
        "outcome_direction": outcome_direction,
        "raw_outcome": outcome,
        "result_r": _oe_safe_float(result_r, None),
        "pnl_pct": _oe_safe_float(pnl_pct, None),
        "note": note,
        "module_evaluations": module_eval_payload.get("module_evaluations"),
        "influence_summary": {
            "total_abs_influence": module_eval_payload.get("total_abs_influence"),
            "correct_influence": module_eval_payload.get("correct_influence"),
            "wrong_influence": module_eval_payload.get("wrong_influence"),
            "correct_influence_pct": module_eval_payload.get("correct_influence_pct"),
            "wrong_influence_pct": module_eval_payload.get("wrong_influence_pct"),
        },
        "decision_snapshot": {
            "inputs": decision_record.get("inputs"),
            "recommended_order": decision_record.get("recommended_order"),
            "hard_deny": decision_record.get("hard_deny"),
            "hard_wait": decision_record.get("hard_wait"),
        },
    }

    saved_learning_outcome = False
    learning_outcome_error = None
    learning_outcome_payload = None
    saved_eval = False
    eval_error = None

    if save:
        learning_outcome_payload = build_learning_outcome_v1(
            learning_id=decision_record.get("learning_id"),
            trade_id=decision_record.get("trade_id"),
            outcome=normalized,
            result_r=result_r,
            pnl_pct=pnl_pct,
            note=note,
            force=True,
        )
        saved_learning_outcome = bool(learning_outcome_payload.get("ok"))
        learning_outcome_error = learning_outcome_payload.get("error")
        saved_eval, eval_error = _oe_append_jsonl(OUTCOME_EVALUATOR_V1_FILE, evaluation_record)

    stats = _oe_evaluator_stats(_oe_read_records(limit=5000))
    learning_stats = _le_outcome_stats(_le_read_records(limit=5000))
    alerts = []
    if decision_correct is False:
        alerts.append("A decisão final parece ter errado contra o outcome informado; revisar pesos ou regras se a amostra crescer.")
    elif decision_correct is True:
        alerts.append("A decisão final parece alinhada ao outcome informado.")
    if module_eval_payload.get("wrong_influence_pct") is not None and module_eval_payload.get("wrong_influence_pct") >= 40:
        alerts.append("Grande parte da influência ponderada veio de módulos que erraram neste outcome.")
    if not save:
        alerts.append("Preview não salvo. Use save=true ou POST para registrar a avaliação.")

    payload = {
        "ok": bool((saved_eval and saved_learning_outcome) if save else True),
        "version": OUTCOME_EVALUATOR_V1_VERSION,
        "mode": OUTCOME_EVALUATOR_V1_MODE,
        "generated_at": data_hora_sp_str(),
        "evaluation_id": eval_id,
        "learning_id": decision_record.get("learning_id"),
        "trade_id": decision_record.get("trade_id"),
        "save_requested": bool(save),
        "evaluation_saved": saved_eval,
        "evaluation_error": eval_error,
        "learning_outcome_saved": saved_learning_outcome,
        "learning_outcome_error": learning_outcome_error,
        "decision": decision,
        "decision_correct": decision_correct,
        "outcome": normalized,
        "outcome_direction": outcome_direction,
        "result_r": _oe_safe_float(result_r, None),
        "pnl_pct": _oe_safe_float(pnl_pct, None),
        "module_evaluations": module_eval_payload.get("module_evaluations"),
        "influence_summary": evaluation_record.get("influence_summary"),
        "evaluation_record": evaluation_record,
        "stats": stats,
        "learning_stats": learning_stats,
        "alerts": alerts,
        "reasons": [
            "Outcome Evaluator V1 compara a decisão registrada com o resultado informado.",
            "Cada voto de módulo recebe acerto/erro/neutro conforme sua direção e o outcome.",
            "A avaliação salva também registra um OUTCOME no Learning Engine para alimentar o Adaptive Weight Engine.",
        ],
        "notes": [
            "Outcome Evaluator V1 está em modo consultivo/observação.",
            "Não altera pesos diretamente; ele cria a base rotulada que será usada pelo Adaptive Weight Engine.",
            "Para DENY/WAIT, o outcome representa o resultado observado/counterfactual do sinal ou paper tracking.",
        ],
    }
    OUTCOME_EVALUATOR_V1_CACHE = {"last_generated_at": payload.get("generated_at"), "last_learning_id": payload.get("learning_id"), "last_decision_correct": payload.get("decision_correct")}
    return payload


def build_outcome_evaluator_v1_text(payload):
    lines = [
        "🧾 OUTCOME EVALUATOR V1 — CENTRAL QUANT",
        f"Data/hora: {payload.get('generated_at')}",
        f"Versão: {payload.get('version')}",
        f"Modo: {payload.get('mode')}",
        "",
        "Outcome avaliado:",
        f"Evaluation ID: {payload.get('evaluation_id')}",
        f"Learning ID: {payload.get('learning_id')}",
        f"Trade ID: {payload.get('trade_id')}",
        f"Outcome: {payload.get('outcome')} | R: {payload.get('result_r')} | PnL%: {payload.get('pnl_pct')}",
        "",
        "Decisão:",
        f"Decision: {payload.get('decision')} | correta: {payload.get('decision_correct')}",
        f"Avaliação salva: {payload.get('evaluation_saved')} | Learning outcome salvo: {payload.get('learning_outcome_saved')}",
        "",
        "Influência:",
    ]
    inf = payload.get("influence_summary") or {}
    lines += [
        f"Influência correta: {inf.get('correct_influence_pct')}%",
        f"Influência errada: {inf.get('wrong_influence_pct')}%",
        "",
        "Acerto por módulo:",
    ]
    for m in payload.get("module_evaluations") or []:
        lines.append(
            f"- {m.get('module')}: voto={m.get('vote')} | correto={m.get('correct')} | "
            f"peso={m.get('weight')} | pontos={m.get('points')} | influência={m.get('influence_pct')}%"
        )
    stats = payload.get("stats") or {}
    lines += [
        "",
        "Estatísticas do evaluator:",
        f"Avaliações: {stats.get('evaluations')} | decisão correta: {stats.get('decision_correct')} | decisão errada: {stats.get('decision_wrong')} | acc={stats.get('decision_accuracy_pct')}%",
    ]
    by_module = stats.get("by_module") or {}
    if by_module:
        lines += ["", "Acurácia acumulada por módulo:"]
        for module, item in by_module.items():
            lines.append(f"- {module}: obs={item.get('observations')} | acertos={item.get('correct')} | erros={item.get('wrong')} | acc={item.get('accuracy_pct')}% | influência média={item.get('avg_influence_pct')}%")
    if payload.get("alerts"):
        lines += ["", "Alertas:"] + [f"- {x}" for x in payload.get("alerts", [])]
    lines += ["", "Motivos:"] + [f"- {x}" for x in payload.get("reasons", [])]
    lines += ["", "Notas:"] + [f"- {x}" for x in payload.get("notes", [])]
    return "\n".join(lines)


@app.route("/outcome/evaluator/v1", methods=["GET", "POST"])
@app.route("/outcome/evaluate/v1", methods=["GET", "POST"])
@app.route("/learning/evaluate/v1", methods=["GET", "POST"])
def outcome_evaluator_v1_route():
    body = request.get_json(silent=True) or {}
    learning_id = body.get("learning_id", request.args.get("learning_id"))
    trade_id = body.get("trade_id", request.args.get("trade_id"))
    outcome = body.get("outcome", request.args.get("outcome"))
    result_r = body.get("result_r", request.args.get("result_r"))
    pnl_pct = body.get("pnl_pct", request.args.get("pnl_pct"))
    note = body.get("note", request.args.get("note"))
    save_raw = body.get("save", request.args.get("save", "true"))
    save = request.method == "POST" or str(save_raw).strip().lower() in {"1", "true", "yes", "sim", "on", "save", "record"}
    force_raw = body.get("force", request.args.get("force", ""))
    force = str(force_raw).strip().lower() in {"1", "true", "yes", "sim", "on"}
    as_text = str(request.args.get("format", request.args.get("text", ""))).strip().lower() in {"1", "true", "yes", "sim", "on", "text", "txt"}
    payload = build_outcome_evaluator_v1(learning_id=learning_id, trade_id=trade_id, outcome=outcome, result_r=result_r, pnl_pct=pnl_pct, note=note, save=save, force=force)
    text = build_outcome_evaluator_v1_text(payload)
    if as_text:
        return text
    return {"ok": bool(payload.get("ok")), "text": text, "payload": payload}


@app.route("/outcome/evaluator/summary/v1")
@app.route("/outcome/evaluator/stats/v1")
@app.route("/learning/evaluator/stats/v1")
def outcome_evaluator_stats_v1_route():
    limit = request.args.get("limit", default=5000, type=int)
    stats = _oe_evaluator_stats(_oe_read_records(limit=limit))
    lines = [
        "📊 OUTCOME EVALUATOR STATS V1 — CENTRAL QUANT",
        f"Data/hora: {data_hora_sp_str()}",
        f"Avaliações: {stats.get('evaluations')}",
        f"Decisão correta: {stats.get('decision_correct')} | decisão errada: {stats.get('decision_wrong')} | neutra: {stats.get('decision_neutral')} | acc={stats.get('decision_accuracy_pct')}%",
        "",
        "Por módulo:",
    ]
    for module, item in (stats.get("by_module") or {}).items():
        lines.append(f"- {module}: obs={item.get('observations')} | acertos={item.get('correct')} | erros={item.get('wrong')} | neutros={item.get('neutral')} | acc={item.get('accuracy_pct')}% | influência média={item.get('avg_influence_pct')}%")
    return {"ok": True, "version": OUTCOME_EVALUATOR_V1_VERSION, "text": "\n".join(lines), "payload": stats}



@app.route("/analytics/exposure-v2")
@app.route("/analytics/bot-exposure-v2")
def analytics_bot_exposure_v2_route():
    capital = request.args.get("capital", default=10000, type=float)
    text, payload = build_bot_exposure_manager_v2_text(capital=capital)
    return {"ok": True, "text": text, "payload": payload}


@app.route("/analytics/capital-check")
def analytics_capital_check_route():
    try:
        from flask import request
        import capital_allocator

        capital = request.args.get("capital", default=10000, type=float)
        bot = request.args.get("bot", default="", type=str)
        required = request.args.get("required", default=0, type=float)
        risk = request.args.get("risk", default=0, type=float)

        payload = capital_allocator.capital_check(
            capital=capital,
            bot=bot,
            required=required,
            risk=risk,
        )

        if not payload.get("ok"):
            return payload

        lines = [
            "💰 CAPITAL ALLOCATOR — CENTRAL QUANT",
            f"Data/hora: {payload.get('generated_at')}",
            f"Modo: {payload.get('mode')}",
            "",
            f"Bot: {payload.get('bot')}",
            f"Categoria: {payload.get('category')}",
            f"Decisão base: {payload.get('base_decision')}",
            "",
            "Capital:",
            f"Capital total analisado: {payload.get('capital')} USDT",
            f"Capital destinado ao robô: {payload.get('capital_allocated')} USDT",
            f"Capital usado: {payload.get('capital_used')} USDT",
            f"Capital livre: {payload.get('capital_free')} USDT",
            f"Capital solicitado: {payload.get('required_capital')} USDT",
            f"Excesso de capital: {payload.get('capital_excess')} USDT",
            "",
            "Risco:",
            f"Risco livre: {payload.get('risk_free_usdt')} USDT",
            f"Risco solicitado: {payload.get('required_risk_usdt')} USDT",
            f"Excesso de risco: {payload.get('risk_excess_usdt')} USDT",
            "",
            f"Resultado: {payload.get('decision')}",
            f"Motivo: {payload.get('reason')}",
            f"Capital sugerido: {payload.get('suggested_required_capital')} USDT",
            f"Redução sugerida: {payload.get('suggested_reduction_pct')}%",
        ]

        lines += ["", "Notas:"]
        for note in payload.get("notes", []):
            lines.append(f"- {note}")

        return {
            "ok": True,
            "text": "\n".join(lines),
            "payload": payload,
        }

    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
        }    
    

@app.route("/analytics/symbols")
def analytics_symbols_route():
    return _analytics_group_response("symbol", "symbol", "symbols")


@app.route("/analytics/setups")
def analytics_setups_route():
    return _analytics_group_response("setup", "setup", "setups")


@app.route("/analytics/performance")
def analytics_performance_route():
    try:
        import performance_engine
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

    days = request.args.get("days", default="", type=str)
    group_by = request.args.get("group_by", default="bot", type=str)

    return performance_engine.build_performance_payload(
        days=days or None,
        group_by=group_by or "bot",
    )


@app.route("/analytics/report")
def analytics_report_route():
    try:
        import performance_engine
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

    days = request.args.get("days", default="", type=str)
    group_by = request.args.get("group_by", default="setup", type=str)

    show_all = str(
        request.args.get("all")
        or request.args.get("show_all")
        or request.args.get("full")
        or ""
    ).lower() in {
        "1", "true", "yes", "sim", "on"
    }

    return {
    "text": performance_engine.build_analytics_report(
        days=days or None,
        group_by=group_by or "setup",
        show_all=show_all,
    )
}


@app.route("/analytics/recommendations")
def analytics_recommendations_route():
    try:
        import performance_engine
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

    days = request.args.get("days", default="", type=str)
    group_by = request.args.get("group_by", default="setup", type=str)

    return performance_engine.build_recommendations_payload(
        days=days or None,
        group_by=group_by or "setup",
    )    




@app.route("/journal/status")
def journal_status_route():
    try:
        import journal_manager
        return journal_manager.get_status()
    except Exception as exc:
        return {"ok": False, "error": str(exc)}, 500


@app.route("/journal")
def journal_route():
    try:
        import journal_manager
    except Exception as exc:
        return {"ok": False, "error": str(exc)}, 500

    group_by = request.args.get("group_by", default="bot", type=str)
    days = request.args.get("days", default="", type=str)
    limit = request.args.get("limit", default="", type=str)

    try:
        return {
            "text": journal_manager.build_journal_report(
                group_by=group_by or "bot",
                days=days or None,
                limit=int(limit) if str(limit or "").isdigit() else None,
            )
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}, 500


@app.route("/journal/raw")
def journal_raw_route():
    try:
        import journal_manager
    except Exception as exc:
        return {"ok": False, "error": str(exc)}, 500

    return journal_manager.query_journal(
        bot=request.args.get("bot", default="", type=str) or None,
        setup=request.args.get("setup", default="", type=str) or None,
        symbol=request.args.get("symbol", default="", type=str) or None,
        side=request.args.get("side", default="", type=str) or None,
        result=request.args.get("result", default="", type=str) or None,
        quality=request.args.get("quality", default="", type=str) or None,
        market_regime=request.args.get("market_regime", default="", type=str) or None,
        hour=request.args.get("hour", default="", type=str) or None,
        days=request.args.get("days", default="", type=str) or None,
        limit=request.args.get("limit", default=None, type=int),
    )


@app.route("/journal/export")
def journal_export_route():
    try:
        import journal_manager
    except Exception as exc:
        return {"ok": False, "error": str(exc)}, 500

    limit = request.args.get("limit", default=None, type=int)
    return journal_manager.export_journal(limit=limit)


@app.route("/journal/bot")
def journal_bot_route():
    try:
        import journal_manager
        return {"text": journal_manager.build_journal_report(group_by="bot", days=request.args.get("days", default="", type=str) or None)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}, 500


@app.route("/journal/setup")
def journal_setup_route():
    try:
        import journal_manager
        return {"text": journal_manager.build_journal_report(group_by="setup", days=request.args.get("days", default="", type=str) or None)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}, 500


@app.route("/journal/symbol")
def journal_symbol_route():
    try:
        import journal_manager
        return {"text": journal_manager.build_journal_report(group_by="symbol", days=request.args.get("days", default="", type=str) or None)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}, 500


@app.route("/journal/hour")
def journal_hour_route():
    try:
        import journal_manager
        return {"text": journal_manager.build_journal_report(group_by="hour", days=request.args.get("days", default="", type=str) or None)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}, 500


@app.route("/journal/weekday")
def journal_weekday_route():
    try:
        import journal_manager
        return {"text": journal_manager.build_journal_report(group_by="weekday", days=request.args.get("days", default="", type=str) or None)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}, 500


@app.route("/journal/regime")
def journal_regime_route():
    try:
        import journal_manager
        return {"text": journal_manager.build_journal_report(group_by="market_regime", days=request.args.get("days", default="", type=str) or None)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}, 500


@app.route("/journal/quality")
def journal_quality_route():
    try:
        import journal_manager
        return {"text": journal_manager.build_journal_report(group_by="quality", days=request.args.get("days", default="", type=str) or None)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}, 500


@app.route("/journal/lifecycle")
def journal_lifecycle_route():
    try:
        import journal_manager
        return {
            "text": journal_manager.build_lifecycle_report(
                days=request.args.get("days", default="", type=str) or None,
                limit=request.args.get("limit", default=None, type=int),
                symbol=request.args.get("symbol", default="", type=str) or None,
                bot=request.args.get("bot", default="", type=str) or None,
            )
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}, 500


@app.route("/journal/events")
def journal_events_route():
    """Relatório leve dos eventos de lifecycle, seguro para Telegram."""
    try:
        import journal_manager
        return {
            "text": journal_manager.build_events_report(
                event=request.args.get("event", default="", type=str) or None,
                bot=request.args.get("bot", default="", type=str) or None,
                setup=request.args.get("setup", default="", type=str) or None,
                symbol=request.args.get("symbol", default="", type=str) or None,
                side=request.args.get("side", default="", type=str) or None,
                quality=request.args.get("quality", default="", type=str) or None,
                market_regime=request.args.get("market_regime", default="", type=str) or None,
                hour=request.args.get("hour", default="", type=str) or None,
                days=request.args.get("days", default="", type=str) or None,
                limit=request.args.get("limit", default=20, type=int),
            )
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}, 500


@app.route("/journal/events/raw")
def journal_events_raw_route():
    """Payload bruto completo, para auditoria/debug. Pode ser pesado."""
    try:
        import journal_manager
        return journal_manager.query_lifecycle(
            event=request.args.get("event", default="", type=str) or None,
            bot=request.args.get("bot", default="", type=str) or None,
            setup=request.args.get("setup", default="", type=str) or None,
            symbol=request.args.get("symbol", default="", type=str) or None,
            side=request.args.get("side", default="", type=str) or None,
            quality=request.args.get("quality", default="", type=str) or None,
            market_regime=request.args.get("market_regime", default="", type=str) or None,
            hour=request.args.get("hour", default="", type=str) or None,
            days=request.args.get("days", default="", type=str) or None,
            limit=request.args.get("limit", default=None, type=int),
        )
    except Exception as exc:
        return {"ok": False, "error": str(exc)}, 500


@app.route("/journal/events/json")
def journal_events_json_route():
    """Payload compacto em JSON, sem raw pesado."""
    try:
        import journal_manager
        return journal_manager.query_lifecycle_clean(
            event=request.args.get("event", default="", type=str) or None,
            bot=request.args.get("bot", default="", type=str) or None,
            setup=request.args.get("setup", default="", type=str) or None,
            symbol=request.args.get("symbol", default="", type=str) or None,
            side=request.args.get("side", default="", type=str) or None,
            quality=request.args.get("quality", default="", type=str) or None,
            market_regime=request.args.get("market_regime", default="", type=str) or None,
            hour=request.args.get("hour", default="", type=str) or None,
            days=request.args.get("days", default="", type=str) or None,
            limit=request.args.get("limit", default=100, type=int),
            include_timeline=request.args.get("timeline", default="", type=str).lower() in {"1", "true", "yes", "sim", "on"},
        )
    except Exception as exc:
        return {"ok": False, "error": str(exc)}, 500


@app.route("/journal/open")
def journal_open_route():
    try:
        import journal_manager
        rows = journal_manager.load_lifecycle_events(limit=journal_manager.LIFECYCLE_MAX_READ)
        lifecycles = journal_manager.build_trade_lifecycles(rows)
        if isinstance(lifecycles, dict):
            lifecycle_items = list(lifecycles.values())
        else:
            lifecycle_items = list(lifecycles or [])
        open_items = [item for item in lifecycle_items if item.get("status") == "OPEN"]
        return {
            "ok": True,
            "generated_at": data_hora_sp_str(),
            "open_count": len(open_items),
            "items": open_items[-100:],
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}, 500


@app.route("/journal/lifecycle/export")
def journal_lifecycle_export_route():
    try:
        import journal_manager
        return journal_manager.export_lifecycle(limit=request.args.get("limit", default=None, type=int))
    except Exception as exc:
        return {"ok": False, "error": str(exc)}, 500


@app.route("/stats")
def stats_route():
    try:
        import history_manager
        import history_statistics

        days = request.args.get("days", default="", type=str)

        if days and str(days).isdigit():
            result = history_manager.query_history(days=int(days), limit=None)
            events = result.get("events", [])
            return history_statistics.build_statistics_from_events(events, days=int(days))

        return history_statistics.build_statistics()

    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc),
        }
    

@app.route("/history")
def history_route():
    super_history_manager = __import__("history_manager")
    result = {"text": super_history_manager.build_history_report()}
    stats_payload = build_history_stats_payload()
    if stats_payload.get("ok"):
        result["payload"] = stats_payload
        result["stats"] = stats_payload
    else:
        result["stats_error"] = stats_payload.get("error")
    return result


@app.route("/history/stats")
def history_stats_route():
    return build_history_stats_payload()


@app.route("/history/events")
def history_events_route():
    try:
        import history_manager as super_history_manager
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

    limit = request.args.get("limit", default="50", type=int)
    bot = request.args.get("bot", default="", type=str)
    symbol = request.args.get("symbol", default="", type=str)
    event_type = request.args.get("event_type", default="", type=str)

    filters = {}
    if bot:
        filters["bot"] = bot
    if symbol:
        filters["symbol"] = symbol
    if event_type:
        filters["event_type"] = event_type

    events = super_history_manager.load_events(limit=limit, filters=filters)
    return {"ok": True, "count": len(events), "events": events}


@app.route("/history/events/latest")
def history_events_latest_route():
    try:
        import history_manager as super_history_manager
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

    events = super_history_manager.load_events(limit=1)
    return {"ok": True, "count": len(events), "event": events[-1] if events else None}


@app.route("/history/query")
def history_query_route():
    try:
        import history_manager as super_history_manager
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

    bot = request.args.get("bot", default="", type=str)
    symbol = request.args.get("symbol", default="", type=str)
    setup = request.args.get("setup", default="", type=str)
    side = request.args.get("side", default="", type=str)
    result = request.args.get("result", default="", type=str)
    days = request.args.get("days", default="", type=str)
    limit = request.args.get("limit", default="50", type=str)

    return {
        "ok": True,
        **super_history_manager.query_history(
            bot=bot or None,
            symbol=symbol or None,
            setup=setup or None,
            side=side or None,
            result=result or None,
            days=days or None,
            limit=limit or None,
        ),
    }


@app.route("/history/audit")
def history_audit_route():
    try:
        import history_manager as super_history_manager
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

    days = request.args.get("days", default="", type=str)

    try:
        if days:
            query_result = super_history_manager.query_history(days=days, limit=None)
            events = query_result.get("events", [])
            return super_history_manager.audit_events(events=events)

        return super_history_manager.audit_events()
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    

@app.route("/history/simulate")
def history_simulate_route():
    if os.environ.get("ENABLE_HISTORY_SIMULATION", "false").lower() != "true":
        return {"ok": False, "error": "history simulation disabled"}

    try:
        import history_manager as super_history_manager
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

    bot = request.args.get("bot", default="TRENDPRO", type=str).upper()
    symbol = request.args.get("symbol", default="BTCUSDT", type=str).upper()
    setup = request.args.get("setup", default="NORMAL", type=str).upper()
    side = request.args.get("side", default="LONG", type=str).upper()

    trade_id = f"SIM-{bot}-{symbol}-{setup}-{side}"

    events = [
        ("TRADE_OPENED", {
            "trade_id": trade_id,
            "bot": bot,
            "symbol": symbol,
            "side": side,
            "setup": setup,
            "entry": 60000,
            "sl": 59400,
            "tp50": 60600,
            "risk_pct": 1.0,
            "score": 82,
            "quality": "ALTA 🟢",
        }),
        ("TP50_HIT", {
            "trade_id": trade_id,
            "bot": bot,
            "symbol": symbol,
            "side": side,
            "setup": setup,
            "entry": 60000,
            "price": 60600,
            "tp50": 60600,
            "pnl_pct": 1.0,
        }),
        ("BREAKEVEN_MOVED", {
            "trade_id": trade_id,
            "bot": bot,
            "symbol": symbol,
            "side": side,
            "setup": setup,
            "entry": 60000,
            "new_stop": 60000,
            "result_r": 1.5,
        }),
        ("TRAILING", {
            "trade_id": trade_id,
            "bot": bot,
            "symbol": symbol,
            "side": side,
            "setup": setup,
            "entry": 60000,
            "new_stop": 60650,
            "pnl_pct": 1.8,
            "result_r": 1.8,
            "mfe_max_pct": 2.4,
            "mae_min_pct": 0.2,
            "mfe_gave_back_pct": 0.6,
        }),
        ("TRADE_CLOSED", {
            "trade_id": trade_id,
            "bot": bot,
            "symbol": symbol,
            "side": side,
            "setup": setup,
            "entry": 60000,
            "exit": 61200,
            "pnl_pct": 2.0,
            "result": "WIN",
            "result_r": 2.0,
            "mfe_max_pct": 2.8,
            "mae_min_pct": 0.2,
            "mfe_gave_back_pct": 0.8,
            "reason": "SIMULATION",
        }),
    ]

    generated = []
    for event_name, payload in events:
        payload["event"] = event_name
        payload["bot"] = bot

        saved = super_history_manager.log_event(
            event_type=event_name,
            payload=payload,
            source="history_simulate",
            trade_id=trade_id,
        )
        generated.append(saved)

    return {
        "ok": True,
        "generated": len(generated),
        "bot": bot,
        "symbol": symbol,
        "setup": setup,
        "side": side,
        "events": generated,
        "audit": super_history_manager.audit_events(events=generated),
    }


@app.route("/snapshot")
def snapshot_route():
    return {"text": build_snapshot_report()}


@app.route("/simulate")
@app.route("/simulate/<key>")
def simulate_route(key=None):
    return {"text": build_simulate_report(key)}


@app.route("/simulate/full")
def simulate_full_route():
    if str(os.environ.get("ENABLE_SIMULATION_ENDPOINT", "false")).strip().lower() != "true":
        return {"ok": False, "error": "simulation endpoint disabled"}

    try:
        import history_manager as super_history_manager
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

    generated_events = []
    sequence = [
        ("SIGNAL_CREATED", {"bot": "PREDATOR", "symbol": "BTCUSDT", "setup": "SMART_PREDATOR", "side": "LONG", "sim_test": True}, "SIM_TEST-1"),
        ("TRADE_OPENED", {"bot": "PREDATOR", "symbol": "BTCUSDT", "setup": "SMART_PREDATOR", "side": "LONG", "sim_test": True}, "SIM_TEST-2"),
        ("TP50_HIT", {"bot": "PREDATOR", "symbol": "BTCUSDT", "setup": "SMART_PREDATOR", "side": "LONG", "sim_test": True}, "SIM_TEST-3"),
        ("BREAKEVEN_MOVED", {"event_type": "BREAKEVEN", "bot": "PREDATOR", "symbol": "BTCUSDT", "setup": "SMART_PREDATOR", "side": "LONG", "sim_test": True}, "SIM_TEST-4"),
        ("TRADE_CLOSED", {"bot": "PREDATOR", "symbol": "BTCUSDT", "setup": "SMART_PREDATOR", "side": "LONG", "result": "WIN", "pnl_pct": 2.5, "sim_test": True}, "SIM_TEST-5"),
        ("TRADE_CLOSED", {"bot": "TURTLE", "symbol": "ETHUSDT", "setup": "TURTLE20", "side": "SHORT", "result": "LOSS", "pnl_pct": -1.0, "sim_test": True}, "SIM_TEST-6"),
        ("TRADE_BLOCKED", {"bot": "TRENDPRO", "symbol": "SOLUSDT", "setup": "NORMAL", "side": "LONG", "result": "DENY", "sim_test": True}, "SIM_TEST-7"),
        ("RISK_DECISION", {"bot": "FALCON", "symbol": "XRPUSDT", "setup": "FALCON30", "side": "LONG", "decision": "DENY", "result": "DENY", "sim_test": True}, "SIM_TEST-8"),
    ]

    for event_type, payload, trade_id in sequence:
        try:
            result = super_history_manager.log_event(event_type, payload, source="sim_test", trade_id=trade_id)
            if result.get("ok"):
                generated_events.append(result.get("event") or {"event": event_type, "trade_id": trade_id})
        except Exception:
            continue

    stats_after = super_history_manager.calculate_stats()
    query_predator = super_history_manager.query_history(bot="PREDATOR", limit=10)
    return {
        "ok": True,
        "generated": len(generated_events),
        "events": generated_events,
        "stats_after": stats_after,
        "query_predator": query_predator,
        "riskstats_hint": "use /history/stats for the aggregated risk history payload",
    }


@app.route("/trend")
def trend_route():
    return {"text": build_single_bot_report("TRENDPRO", complete=True)}


@app.route("/donkey")
def donkey_route():
    return {"text": build_single_bot_report("DONKEY", complete=True)}


@app.route("/cobra")
def cobra_route():
    return {"text": build_single_bot_report("COBRA", complete=True)}


@app.route("/meme")
def meme_route():
    return {"text": build_single_bot_report("MEME", complete=True)}


@app.route("/predator")
def predator_route():
    return {"text": build_single_bot_report("PREDATOR", complete=True)}


@app.route("/turtle")
def turtle_route():
    return {"text": build_single_bot_report("TURTLE", complete=True)}


@app.route("/falcon")
def falcon_route():
    return {"text": build_single_bot_report("FALCON", complete=True)}


def build_central_menu_text():
    return (
        "📦 MENU CENTRAL QUANT\n\n"
        "Use quase sempre apenas estes comandos:\n\n"
        "1) Rotina diária\n"
        "/dashboard — visão geral para operar e monitorar\n"
        "/daily — relatório enxuto para copiar e mandar ao ChatGPT\n\n"
        "2) Pós-deploy / antes de LIVE\n"
        "/selftest — valida saúde geral da Central\n"
        "/execution — valida modo, BingX e permissões\n"
        "/sync — compara Central LIVE x BingX\n\n"
        "3) Execução real\n"
        "/live — saldo, posições reais e últimas execuções\n"
        "/executions — log das tentativas VERIFY/LIVE\n"
        "/risk — decisão global ALLOW/DENY e concentração\n\n"
        "3.1) Super History\n"
        "/history — diário da Central\n"
        "/riskstats — estatísticas do History\n"
        "/exporthistory — exportação JSON para análise\n\n"
        "4) Se algo parecer errado\n"
        "/support — pacote técnico de troubleshooting\n"
        "/memory — memória/risco de restart\n"
        "/audit — auditoria completa em partes\n\n"
        "5) Investigar operação específica\n"
        "/journal — histórico resumido\n"
        "/trade <ativo> — replay do último trade do ativo\n"
        "/timeline <ativo> — linha do tempo quando disponível\n"
        "/decisionlog — decisões quando disponível\n\n"
        "Comandos por robô:\n"
        "/falcon /predator /turtle /trend /donkey /cobra /meme\n\n"
        "Lista completa avançada: /comandosfull"
    )


def build_central_help_text():
    return (
        "🤖 CENTRAL QUANT — LISTA COMPLETA DE COMANDOS\n\n"
        "Uso recomendado: /menu\n\n"
        "Pacotes principais:\n"
        "/dashboard — visão geral inteligente\n"
        "/daily — relatório diário enxuto para avaliação\n"
        "/support — troubleshooting técnico\n"
        "/audit — auditoria completa\n"
        "/full — dump completo com snapshot\n\n"
        "Operação:\n"
        "/executive\n/selftest\n/diagnostico\n/memory\n/execution\n/bingx\n/live\n/sync\n/executions\n/risk\n/heat\n/ranking\n/healthscore\n/meta\n/exposure\n/runners\n\n"
        "Relatórios:\n"
        "/relatorio — resumo central\n"
        "/relatoriocompleto — pacote completo sem espaço\n"
        "/auditoria — alias do relatório completo nativo\n\n"
        "Por robô:\n"
        "/trend\n/donkey\n/cobra\n/meme\n/predator\n/turtle\n/falcon\n\n"
        "Histórico, estatística e simulação:\n"
        "/history\n/riskstats\n/exporthistory\n/journal\n/trade <ativo>\n/globalstats\n/signalai <ativo>\n/capital\n/correlation\n/timeheat\n/marketscore\n/allocation\n/exposurescore\n/rankingvivo\n/evolution\n/learning\n/quantos\n/snapshot\n/history\n/simulate TURTLE\n/simulateoff TURTLE\n\n"
        "Sugestão de uso diário: /dashboard. Para colar no ChatGPT: /daily."
    )



# ==========================================================
# QUANT OS - JOURNAL / STATS / CAPITAL / LEARNING
# ==========================================================
# Esta camada é apenas analítica/consultiva. Não envia ordens.

QUANT_OS_MAX_ITEMS = int(os.environ.get("QUANT_OS_MAX_ITEMS", "1500"))
CAPITAL_ALLOCATION_BASE_NOTIONAL_USDT = float(os.environ.get("CAPITAL_ALLOCATION_BASE_NOTIONAL_USDT", os.environ.get("REAL_TRADING_MAX_NOTIONAL_USDT", "10")))
CAPITAL_ALLOCATION_MIN_NOTIONAL_USDT = float(os.environ.get("CAPITAL_ALLOCATION_MIN_NOTIONAL_USDT", "5"))
CAPITAL_ALLOCATION_MAX_NOTIONAL_USDT = float(os.environ.get("CAPITAL_ALLOCATION_MAX_NOTIONAL_USDT", os.environ.get("REAL_TRADING_MAX_NOTIONAL_USDT", "10")))


def _module_call_optional(module, names, default=None):
    for name in names:
        fn = getattr(module, name, None)
        if callable(fn):
            try:
                return fn()
            except Exception:
                continue
    return default


def _all_trades_payload(limit=None):
    rows = []
    for key, module in LOADED_BOTS.items():
        raw = _module_call_optional(module, ["get_trades", "trades_today", "carregar_trades", "load_trades"], default=[])
        if isinstance(raw, dict):
            raw = list(raw.values())
        if not isinstance(raw, list):
            raw = []
        for t in raw:
            if not isinstance(t, dict):
                continue
            sym = _compact_symbol(t.get("symbol") or t.get("ativo") or t.get("pair"))
            rows.append({
                "bot": key,
                "symbol": sym,
                "sector": _symbol_sector(sym),
                "side": str(t.get("side") or t.get("direction") or "").upper(),
                "setup": t.get("setup") or t.get("setup_label") or t.get("origem"),
                "created_at": t.get("created_at") or t.get("opened_at") or t.get("entry_at"),
                "closed_at": t.get("closed_at") or t.get("exit_at") or t.get("updated_at"),
                "entry": t.get("entry") or t.get("entrada"),
                "exit": t.get("exit_price") or t.get("saida") or t.get("exit"),
                "result_pct": safe_round(t.get("result_pct") or t.get("pnl_pct") or t.get("resultado_pct"), 4, 0) or 0,
                "result_r": safe_round(t.get("result_r") or t.get("pnl_r") or t.get("resultado_r"), 4, 0) or 0,
                "mfe_pct": safe_round(t.get("mfe_pct"), 4, 0) or 0,
                "mfe_r": safe_round(t.get("mfe_r"), 4, 0) or 0,
                "mae_pct": safe_round(t.get("mae_pct"), 4, 0) or 0,
                "mae_r": safe_round(t.get("mae_r"), 4, 0) or 0,
                "exit_reason": t.get("exit_reason") or t.get("reason") or t.get("status"),
                "tp50_hit": bool(t.get("tp50_hit")),
            })
    rows = rows[-(limit or QUANT_OS_MAX_ITEMS):]
    return rows


def _all_events_payload(limit=None):
    rows = []
    for key, module in LOADED_BOTS.items():
        raw = _module_call_optional(module, ["get_events", "events_today", "carregar_eventos", "load_events"], default=[])
        if isinstance(raw, dict):
            raw = list(raw.values())
        if not isinstance(raw, list):
            raw = []
        for e in raw:
            if not isinstance(e, dict):
                continue
            sym = _compact_symbol(e.get("symbol") or e.get("ativo") or e.get("pair"))
            rows.append({
                "bot": key,
                "symbol": sym,
                "side": str(e.get("side") or e.get("direction") or "").upper(),
                "setup": e.get("setup") or e.get("setup_label"),
                "event_type": e.get("event_type") or e.get("type") or e.get("evento"),
                "created_at": e.get("created_at") or e.get("ts") or e.get("time"),
                "mfe_pct": safe_round(e.get("mfe_pct"), 4, 0) or 0,
                "mfe_r": safe_round(e.get("mfe_r"), 4, 0) or 0,
                "result_pct": safe_round(e.get("result_pct"), 4, 0) or 0,
                "result_r": safe_round(e.get("result_r"), 4, 0) or 0,
            })
    return rows[-(limit or QUANT_OS_MAX_ITEMS):]


def _stats_from_rows(rows):
    rows = rows or []
    if not rows:
        return {"trades": 0, "wins": 0, "losses": 0, "be": 0, "wr": 0.0, "pnl_pct": 0.0, "pnl_r": 0.0, "pf_r": 0.0, "exp_r": 0.0, "mfe_r": 0.0, "mae_r": 0.0}
    results = [safe_round(r.get("result_r"), 6, 0) or 0 for r in rows]
    results_pct = [safe_round(r.get("result_pct"), 6, 0) or 0 for r in rows]
    wins = [x for x in results if x > 0.05]
    losses = [x for x in results if x < -0.05]
    be = len(rows) - len(wins) - len(losses)
    gross_profit = sum(x for x in results if x > 0)
    gross_loss = abs(sum(x for x in results if x < 0))
    return {
        "trades": len(rows),
        "wins": len(wins),
        "losses": len(losses),
        "be": be,
        "wr": round(len(wins) / max(len(rows), 1) * 100, 2),
        "pnl_pct": round(sum(results_pct), 4),
        "pnl_r": round(sum(results), 4),
        "pf_r": round(gross_profit / gross_loss, 2) if gross_loss > 0 else (round(gross_profit, 2) if gross_profit else 0.0),
        "exp_r": round(sum(results) / max(len(rows), 1), 4),
        "mfe_r": round(sum((safe_round(r.get("mfe_r"), 6, 0) or 0) for r in rows) / max(len(rows), 1), 4),
        "mae_r": round(sum((safe_round(r.get("mae_r"), 6, 0) or 0) for r in rows) / max(len(rows), 1), 4),
    }


def _group_stats(rows, key_fn):
    groups = {}
    for r in rows or []:
        k = key_fn(r)
        if not k:
            continue
        groups.setdefault(k, []).append(r)
    out = []
    for k, items in groups.items():
        st = _stats_from_rows(items)
        st["key"] = k
        out.append(st)
    out.sort(key=lambda x: (x.get("exp_r", 0), x.get("pf_r", 0), x.get("trades", 0)), reverse=True)
    return out


def build_journal_report(arg=None):
    token = normalize_symbol_for_risk(arg) if arg else None
    trades = _all_trades_payload()
    events = _all_events_payload()
    if token:
        trades = [t for t in trades if normalize_symbol_for_risk(t.get("symbol")) == token or str(t.get("bot")).upper() == token]
        events = [e for e in events if normalize_symbol_for_risk(e.get("symbol")) == token or str(e.get("bot")).upper() == token]
    lines = ["📓 JOURNAL CENTRAL QUANT", f"Data/hora: {data_hora_sp_str()}"]
    if token:
        lines.append(f"Filtro: {token}")
    lines += ["", f"Trades encontrados: {len(trades)} | Eventos: {len(events)}"]
    if not trades and not events:
        lines.append("Nenhum item encontrado ainda.")
        return "\n".join(lines)
    lines += ["", "Últimos eventos:"]
    for e in events[-20:]:
        lines.append(f"- {e.get('created_at')} | {e.get('bot')} | {e.get('event_type')} | {e.get('symbol')} {e.get('side')} {e.get('setup')} | MFE {e.get('mfe_pct')}%/{e.get('mfe_r')}R")
    lines += ["", "Últimos trades fechados:"]
    for t in trades[-15:]:
        lines.append(f"- {t.get('closed_at')} | {t.get('bot')} | {t.get('symbol')} {t.get('side')} {t.get('setup')} | {t.get('result_pct')}% | {t.get('result_r')}R | {t.get('exit_reason')}")
    return "\n".join(lines)


def build_trade_replay_report(arg=None):
    sym = normalize_symbol_for_risk(arg) if arg else None
    trades = _all_trades_payload()
    events = _all_events_payload()
    if sym:
        trades = [t for t in trades if normalize_symbol_for_risk(t.get("symbol")) == sym]
        events = [e for e in events if normalize_symbol_for_risk(e.get("symbol")) == sym]
    last = trades[-1] if trades else None
    lines = ["🎬 REPLAY DE TRADE — CENTRAL QUANT", f"Data/hora: {data_hora_sp_str()}"]
    if sym:
        lines.append(f"Ativo: {sym}")
    if not last:
        lines += ["", "Nenhum trade fechado encontrado para replay.", "Dica: use /journal para ver eventos em aberto."]
        return "\n".join(lines)
    lines += [
        "",
        f"Bot/setup: {last.get('bot')} | {last.get('setup')}",
        f"Ativo: {last.get('symbol')} {last.get('side')}",
        f"Entrada: {last.get('entry')} | Saída: {last.get('exit')}",
        f"Resultado: {last.get('result_pct')}% | {last.get('result_r')}R",
        f"MFE: {last.get('mfe_pct')}% | {last.get('mfe_r')}R",
        f"MAE: {last.get('mae_pct')}% | {last.get('mae_r')}R",
        f"TP50: {'sim' if last.get('tp50_hit') else 'não'}",
        f"Motivo saída: {last.get('exit_reason')}",
        f"Aberto: {last.get('created_at')} | Fechado: {last.get('closed_at')}",
        "",
        "Linha do tempo recente:",
    ]
    for e in events[-20:]:
        lines.append(f"- {e.get('created_at')} | {e.get('event_type')} | {e.get('symbol')} | MFE {e.get('mfe_r')}R")
    return "\n".join(lines)


def build_global_stats_report():
    trades = _all_trades_payload()
    open_rows = _all_open_positions_payload()
    st_all = _stats_from_rows(trades)
    by_bot = _group_stats(trades, lambda r: r.get("bot"))[:10]
    by_symbol = _group_stats(trades, lambda r: r.get("symbol"))[:15]
    lines = [
        "🌐 ESTATÍSTICAS GLOBAIS — CENTRAL QUANT",
        f"Data/hora: {data_hora_sp_str()}",
        "",
        f"Trades fechados: {st_all['trades']} | WR {st_all['wr']}% | PF {st_all['pf_r']} | Exp {st_all['exp_r']}R | PnL {st_all['pnl_r']}R",
        f"Abertos agora: {len(open_rows)}",
        "",
        "Por robô:",
    ]
    for x in by_bot:
        lines.append(f"- {x['key']}: trades={x['trades']} | WR={x['wr']}% | PF={x['pf_r']} | Exp={x['exp_r']}R | PnL={x['pnl_r']}R")
    lines += ["", "Top ativos:"]
    for x in by_symbol:
        lines.append(f"- {x['key']}: trades={x['trades']} | WR={x['wr']}% | PF={x['pf_r']} | Exp={x['exp_r']}R | PnL={x['pnl_r']}R")
    return "\n".join(lines)


def build_signal_ai_report(arg=None):
    sym = normalize_symbol_for_risk(arg) if arg else None
    trades = _all_trades_payload()
    if sym:
        trades = [t for t in trades if normalize_symbol_for_risk(t.get("symbol")) == sym]
    stats = _stats_from_rows(trades)
    confidence = "BAIXA"
    if stats["trades"] >= 30 and stats["exp_r"] > 0 and stats["wr"] >= 55:
        confidence = "ALTA"
    elif stats["trades"] >= 10 and stats["exp_r"] > 0:
        confidence = "MÉDIA"
    lines = [
        "🧠 IA DE QUALIDADE DO SINAL — CENTRAL QUANT",
        f"Data/hora: {data_hora_sp_str()}",
        f"Filtro: {sym or 'histórico global'}",
        "",
        f"Amostra histórica: {stats['trades']} trades",
        f"Win rate: {stats['wr']}%",
        f"Profit Factor R: {stats['pf_r']}",
        f"Expectancy: {stats['exp_r']}R",
        f"MFE médio: {stats['mfe_r']}R | MAE médio: {stats['mae_r']}R",
        f"Confiabilidade estatística: {confidence}",
        "",
        "Leitura:",
    ]
    if stats["trades"] < 10:
        lines.append("- Amostra ainda pequena. Use como observação, não como filtro duro.")
    elif stats["exp_r"] > 0:
        lines.append("- Histórico favorece continuidade do setup dentro deste filtro.")
    else:
        lines.append("- Histórico pede cautela; avaliar score mínimo, horário e direção.")
    return "\n".join(lines)


def build_capital_report():
    ready = bingx_ready_payload() if BINGX_READY_CHECK_ENABLED else {"ok": None, "status": "READY_CHECK_DISABLED"}
    bal = ready.get("balance") or {}
    exposure = central_exposure_snapshot()
    live = _central_live_positions_payload()
    free = safe_round(bal.get("free_usdt"), 4, None)
    total = safe_round(bal.get("total_usdt"), 4, None)
    max_notional = REAL_TRADING_MAX_NOTIONAL_USDT
    capacity = int((free or 0) // max_notional) if max_notional > 0 and free is not None else 0
    lines = [
        "💰 CAPITAL DASHBOARD — CENTRAL QUANT",
        f"Data/hora: {data_hora_sp_str()}",
        "",
        f"BingX READY: {ready.get('ok')} | {ready.get('status')}",
        f"Saldo USDT total/free: {total} / {free}",
        f"Capacidade teórica no notional atual ({max_notional} USDT): {capacity} novas ordens",
        f"Real trading: {'ATIVO' if ENABLE_REAL_TRADING else 'BLOQUEADO'} | Modo {EXECUTION_MODE}",
        "",
        f"Posições Central/Paper: {exposure.get('total_positions_open')} | LONG {exposure.get('long_positions_open')} | SHORT {exposure.get('short_positions_open')}",
        f"Posições LIVE Central: {len(live)}",
        "",
        "Observação: equity/drawdown reais serão calculados após os primeiros eventos LIVE registrados.",
    ]
    return "\n".join(lines)


def build_correlation_report():
    rows = _all_open_positions_payload()
    by_symbol = {}
    for r in rows:
        by_symbol.setdefault(r.get("symbol"), []).append(r)
    lines = ["🔗 CORRELAÇÃO ENTRE ROBÔS", f"Data/hora: {data_hora_sp_str()}", ""]
    conflicts = []
    confirmations = []
    for sym, items in by_symbol.items():
        if len(items) < 2:
            continue
        longs = [x for x in items if str(x.get("side")).upper() in {"LONG", "BUY"}]
        shorts = [x for x in items if str(x.get("side")).upper() in {"SHORT", "SELL"}]
        bots = ",".join(sorted(set(str(x.get("bot")) for x in items)))
        if longs and shorts:
            conflicts.append(f"- {sym}: conflito L={len(longs)} S={len(shorts)} | bots={bots}")
        else:
            side = "LONG" if longs else "SHORT"
            confirmations.append(f"- {sym}: confirmação {side} x{len(items)} | bots={bots}")
    lines += ["Conflitos:"] + (conflicts[:20] if conflicts else ["- Nenhum conflito relevante."])
    lines += ["", "Confirmações:"] + (confirmations[:20] if confirmations else ["- Nenhuma confirmação múltipla."])
    return "\n".join(lines)


def build_time_heatmap_report():
    events = _all_events_payload()
    buckets = {h: {"events": 0, "tp50": 0, "stop": 0} for h in range(24)}
    for e in events:
        txt = str(e.get("created_at") or "")
        hour = None
        try:
            # Formato comum: dd/mm/YYYY HH:MM
            hour = int(txt.split()[1].split(":")[0])
        except Exception:
            continue
        if hour not in buckets:
            continue
        buckets[hour]["events"] += 1
        et = str(e.get("event_type") or "").upper()
        if "TP50" in et:
            buckets[hour]["tp50"] += 1
        if "STOP" in et:
            buckets[hour]["stop"] += 1
    lines = ["⏱️ HEATMAP TEMPORAL", f"Data/hora: {data_hora_sp_str()}", "", "Eventos por hora:"]
    for h, v in sorted(buckets.items(), key=lambda kv: kv[1]["events"], reverse=True)[:12]:
        if v["events"]:
            lines.append(f"- {h:02d}:00 | eventos={v['events']} | TP50={v['tp50']} | STOP={v['stop']}")
    if len(lines) == 4:
        lines.append("- Ainda sem eventos suficientes.")
    return "\n".join(lines)


def build_market_score_report():
    rows = _all_open_positions_payload()
    total = len(rows)
    longs = sum(1 for r in rows if str(r.get("side")).upper() in {"LONG", "BUY"})
    shorts = sum(1 for r in rows if str(r.get("side")).upper() in {"SHORT", "SELL"})
    runners = [safe_round(r.get("runner_r"), 4, 0) or 0 for r in rows]
    avg_runner = sum(runners) / max(len(runners), 1)
    bullish = round(longs / max(total, 1) * 100, 1)
    bearish = round(shorts / max(total, 1) * 100, 1)
    trend_bias = "BULLISH" if bullish > bearish + 15 else ("BEARISH" if bearish > bullish + 15 else "NEUTRO")
    score = 50 + (bullish - bearish) / 2 + min(20, max(-20, avg_runner * 5))
    score = max(0, min(100, round(score, 1)))
    lines = [
        "🌡️ MARKET SCORE — CENTRAL QUANT",
        f"Data/hora: {data_hora_sp_str()}",
        "",
        f"Score interno: {score}/100",
        f"Viés: {trend_bias}",
        f"Bullish: {bullish}% | Bearish: {bearish}%",
        f"Posições analisadas: {total}",
        f"Runner médio aberto: {round(avg_runner, 2)}R",
        "",
        "Observação: score baseado nos robôs/posições atuais; não usa dados externos como funding, OI ou Fear & Greed ainda.",
    ]
    return "\n".join(lines)


def build_capital_allocation_report():
    trades = _all_trades_payload()
    stats = _group_stats(trades, lambda r: r.get("bot"))
    lines = ["💼 CAPITAL ALLOCATION — CENTRAL QUANT", f"Data/hora: {data_hora_sp_str()}", ""]
    if not stats:
        lines.append("Sem histórico fechado suficiente. Usando notional base.")
        for key in BOT_CONFIGS.keys():
            lines.append(f"- {key}: {CAPITAL_ALLOCATION_BASE_NOTIONAL_USDT:.2f} USDT")
        return "\n".join(lines)
    for x in stats:
        mult = 1.0
        if x["trades"] >= 10 and x["exp_r"] > 0:
            mult += min(1.0, x["exp_r"])
        if x["pf_r"] < 1 and x["trades"] >= 10:
            mult *= 0.6
        notional = max(CAPITAL_ALLOCATION_MIN_NOTIONAL_USDT, min(CAPITAL_ALLOCATION_MAX_NOTIONAL_USDT, CAPITAL_ALLOCATION_BASE_NOTIONAL_USDT * mult))
        lines.append(f"- {x['key']}: {notional:.2f} USDT | trades={x['trades']} | PF={x['pf_r']} | Exp={x['exp_r']}R | WR={x['wr']}%")
    lines += ["", "Modo consultivo. A execução real continua limitada por REAL_TRADING_MAX_NOTIONAL_USDT."]
    return "\n".join(lines)


def build_ranking_vivo_report():
    trades = _all_trades_payload()
    windows = {"GLOBAL": trades, "AMOSTRA RECENTE": trades[-100:], "ÚLTIMOS 30": trades[-30:]}
    lines = ["🏆 RANKING VIVO — CENTRAL QUANT", f"Data/hora: {data_hora_sp_str()}"]
    for label, rows in windows.items():
        lines += ["", label]
        grouped = _group_stats(rows, lambda r: r.get("bot"))[:7]
        if not grouped:
            lines.append("- Sem dados.")
            continue
        for i, x in enumerate(grouped, 1):
            medal = "🥇" if i == 1 else ("🥈" if i == 2 else ("🥉" if i == 3 else f"{i}."))
            lines.append(f"{medal} {x['key']} | trades={x['trades']} | PF={x['pf_r']} | Exp={x['exp_r']}R | WR={x['wr']}% | PnL={x['pnl_r']}R")
    return "\n".join(lines)


def build_simulate_off_report(arg=None):
    bot = str(arg or "").upper().strip()
    trades = _all_trades_payload()
    all_stats = _stats_from_rows(trades)
    lines = ["🧪 SIMULADOR DE DESLIGAMENTO", f"Data/hora: {data_hora_sp_str()}"]
    if not bot:
        lines += ["", "Use: /simulateoff TURTLE"]
        return "\n".join(lines)
    without = [t for t in trades if str(t.get("bot")).upper() != bot]
    st = _stats_from_rows(without)
    lines += [
        "",
        f"Robô removido: {bot}",
        f"Atual: trades={all_stats['trades']} | PnL={all_stats['pnl_r']}R | Exp={all_stats['exp_r']}R | PF={all_stats['pf_r']}",
        f"Sem {bot}: trades={st['trades']} | PnL={st['pnl_r']}R | Exp={st['exp_r']}R | PF={st['pf_r']}",
        f"Diferença PnL: {round(st['pnl_r'] - all_stats['pnl_r'], 4)}R",
    ]
    return "\n".join(lines)


def build_learning_report():
    trades = _all_trades_payload()
    by_bot = _group_stats(trades, lambda r: r.get("bot"))
    by_symbol = _group_stats(trades, lambda r: r.get("symbol"))
    lines = ["🧬 APRENDIZADO AUTOMÁTICO — CENTRAL QUANT", f"Data/hora: {data_hora_sp_str()}", "", "Sugestões:"]
    suggestions = []
    for x in by_bot:
        if x["trades"] >= 10 and x["exp_r"] < 0:
            suggestions.append(f"- {x['key']}: expectancy negativa ({x['exp_r']}R). Revisar score mínimo, janela ou filtro de direção.")
        elif x["trades"] >= 10 and x["exp_r"] > 0.5:
            suggestions.append(f"- {x['key']}: boa expectancy ({x['exp_r']}R). Candidato a maior alocação após validação LIVE.")
    for x in by_symbol[:20]:
        if x["trades"] >= 5 and x["exp_r"] < 0:
            suggestions.append(f"- {x['key']}: desempenho fraco ({x['exp_r']}R). Considerar filtro por ativo.")
    if not suggestions:
        suggestions.append("- Ainda sem amostra suficiente para recomendações fortes. Continuar coletando histórico.")
    lines += suggestions[:25]
    return "\n".join(lines)


def build_quantos_report():
    parts = [
        "🧠 QUANT OS — CENTRAL QUANT",
        f"Data/hora: {data_hora_sp_str()}",
        "",
        build_capital_report(),
        "\n==============================\n" + build_global_stats_report(),
        "\n==============================\n" + build_correlation_report(),
        "\n==============================\n" + build_market_score_report(),
        "\n==============================\n" + build_capital_allocation_report(),
        "\n==============================\n" + build_learning_report(),
    ]
    return "\n".join(parts)

def build_central_command_reply(text: str):
    raw = (text or "").strip()
    if not raw:
        return None
    cmd0 = raw.lower().split()[0].split("@")[0]

    if cmd0 in {"/start", "/help", "/menu", "/comandos"}:
        return build_central_menu_text()
    if cmd0 in {"/comandosfull", "/commandsfull", "/helpfull"}:
        return build_central_help_text()
    if cmd0 in {"/dashboard"}:
        return build_dashboard_report()
    if cmd0 in {"/ceo", "/ceodaily", "/ceo_daily"}:
        return build_ceo_daily_report()
    if cmd0 in {"/daily", "/diario", "/diário"}:
        return build_ceo_daily_report()
    if cmd0 in {"/executivereport", "/executive_report", "/dailyexecutive", "/daily_executive"}:
        return build_ceo_daily_report()
    if cmd0 in {"/ceoconfidence", "/ceo_confidence", "/confidence", "/confianca", "/confiança"}:
        return _ceo_confidence_report_block()
    if cmd0 in {"/strategicadvisor", "/strategic_advisor", "/strategy", "/estrategia", "/estratégia"}:
        return _strategic_advisor_report_block(compact=False)
    if cmd0 in {"/decisionpack", "/decision_pack", "/decision", "/decisao", "/decisão"}:
        return _decision_pack_report_block(compact=False)
    if cmd0 in {"/monthly", "/mensal", "/monthlyreport", "/monthly_report"}:
        return build_executive_report_monthly()
    if cmd0 in {"/support"}:
        return build_support_report()
    if cmd0 in {"/audit", "/auditoria", "/relatoriocompleto", "/relatorio_completo"}:
        return build_audit_parts()
    if cmd0 in {"/full"}:
        return build_full_parts()
    if cmd0 in {"/relatoriocompleto", "/relatorio_completo"}:
        return build_audit_parts()
    if cmd0 in {"/trend", "/trendpro"}:
        return build_single_bot_report("TRENDPRO", complete=True)
    if cmd0 in {"/alerts", "/executivealerts", "/executive_alerts"}:
        return build_executive_alerts_text()
    if cmd0 in {"/alertscheck", "/alerts_check"}:
        result = build_executive_alerts(check_only=False)
        alerts = result.get("alerts_to_notify") or []
        if not alerts:
            return "✅ Executive Alert Manager\n\nNenhum alerta que precise interromper o CEO agora."
        return "\n\n".join([build_executive_alert_text(a) for a in alerts])
    if cmd0 in {"/policyhealth", "/policy_health"}:
        if EXECUTIVE_POLICY_MANAGER_LOADED:
            return executive_policy_manager.format_policy_health_text()
        return f"❌ Executive Policy Manager não carregado: {EXECUTIVE_POLICY_MANAGER_ERROR}"

    if cmd0 in {"/policies", "/policylist", "/policy_list"}:
        return _build_executive_policies_text_from_manager(include_disabled=False)

    if cmd0 in {"/policyautorelease", "/policy_auto_release", "/autorelease", "/releasepolicies"}:
        return _executive_policy_auto_release_report_block()

    if cmd0 in {"/policyautoreleasehealth", "/policy_auto_release_health", "/autoreleasehealth"}:
        return _executive_policy_auto_release_health_text()

    if cmd0 in {"/policypriority", "/policy_priority", "/priority", "/policyrank"}:
        result = resolve_executive_policy_priority(trade_payload=None, commit=True)
        return build_executive_policy_priority_report(result)

    if cmd0 in {"/policypriorityhealth", "/policy_priority_health", "/priorityhealth"}:
        health = get_executive_policy_priority_health()
        return json.dumps(health, ensure_ascii=False, indent=2)

    if cmd0 == "/policy":
        if EXECUTIVE_POLICY_MANAGER_LOADED:
            parts = raw.split(maxsplit=1)
            code = parts[1].strip() if len(parts) > 1 else ""
            if not code:
                return "Use: /policy NO_NEW_LONG"
            return executive_policy_manager.format_single_policy_text(code)
        return f"❌ Executive Policy Manager não carregado: {EXECUTIVE_POLICY_MANAGER_ERROR}"

    if cmd0 in {"/donkey"}:
        return build_single_bot_report("DONKEY", complete=True)
    if cmd0 in {"/cobra"}:
        return build_single_bot_report("COBRA", complete=True)
    if cmd0 in {"/meme"}:
        return build_single_bot_report("MEME", complete=True)
    if cmd0 in {"/predator", "/smart", "/smartpredator"}:
        return build_single_bot_report("PREDATOR", complete=True)
    if cmd0 in {"/turtle"}:
        return build_single_bot_report("TURTLE", complete=True)
    if cmd0 in {"/falcon"}:
        return build_single_bot_report("FALCON", complete=True)
    if cmd0 in {"/health", "/central"}:
        return json.dumps(central(), ensure_ascii=False, indent=2, default=str)
    if cmd0 in {"/bots"}:
        return json.dumps(bots(), ensure_ascii=False, indent=2, default=str)
    if cmd0 in {"/watchdog"}:
        return json.dumps(central_watchdog_status(), ensure_ascii=False, indent=2, default=str)
    if cmd0 in {"/exposure"}:
        return json.dumps(central_exposure_snapshot(), ensure_ascii=False, indent=2, default=str)
    if cmd0 in {"/runners"}:
        snapshot = central_exposure_snapshot()
        return json.dumps({
            "open_runners": snapshot.get("open_runners"),
            "best_open_runner": snapshot.get("best_open_runner"),
            "by_bot": snapshot.get("by_bot"),
        }, ensure_ascii=False, indent=2, default=str)
    if cmd0 in {"/selftest", "/self-test", "/teste", "/autoteste"}:
        return build_selftest_report()
    if cmd0 in {"/diagnostico", "/diagnóstico", "/diag"}:
        return build_diagnostic_report()
    if cmd0 in {"/memory", "/memoria", "/memória"}:
        text_mem, _ = build_memory_text(run_gc=False)
        return text_mem
    if cmd0 in {"/memorygc", "/memory_gc", "/memoriagc", "/memoria_gc"}:
        text_mem, _ = build_memory_text(run_gc=True)
        return text_mem
    if cmd0 in {"/executive", "/dashboard"}:
        return build_executive_report()
    if cmd0 in {"/execution", "/execucao", "/execução", "/bingx"}:
        return build_execution_report()
    if cmd0 in {"/live", "/livestatus"}:
        return build_live_report()
    if cmd0 in {"/sync", "/reconcile"}:
        return build_sync_report()
    if cmd0 in {"/executions", "/exec_log", "/executionlog"}:
        return build_executions_log_report()
    if cmd0 in {"/auditrisk", "/riskaudit"}:
        parts = raw.split()
        return build_audit_risk_report(parts[1] if len(parts) > 1 else 2)
    if cmd0 in {"/risk", "/riskmanager"}:
        return build_risk_report()
    if cmd0 in {"/heat", "/heatmap"}:
        return build_heatmap_report()
    if cmd0 in {"/ranking"}:
        return build_ranking_report()
    if cmd0 in {"/healthscore", "/score"}:
        return build_healthscore_report()
    if cmd0 in {"/meta", "/metasupervisor"}:
        return build_meta_supervisor_report()
    if cmd0 in {"/history"}:
        return __import__("history_manager").build_history_report()
    if cmd0 in {"/riskstats", "/riscoestatisticas", "/estatisticashistory"}:
        try:
            import history_manager as super_history_manager
            return super_history_manager.build_riskstats_report()
        except Exception as exc:
            return f"⚠️ Erro ao gerar /riskstats: {exc}"
    if cmd0 in {"/exporthistory", "/exportarhistory"}:
        try:
            import history_manager as super_history_manager
            return super_history_manager.build_export_report()
        except Exception as exc:
            return f"⚠️ Erro ao gerar /exporthistory: {exc}"
    if cmd0 in {"/snapshot"}:
        return build_snapshot_report()
    if cmd0 in {"/simulate"}:
        parts = raw.split()
        return build_simulate_report(parts[1] if len(parts) > 1 else None)
    if cmd0 in {"/simulateoff", "/simoff"}:
        parts = raw.split()
        return build_simulate_off_report(parts[1] if len(parts) > 1 else None)
    if cmd0 in {"/journal"}:
        parts = raw.split()
        return build_journal_report(parts[1] if len(parts) > 1 else None)
    if cmd0 in {"/trade", "/replay"}:
        parts = raw.split()
        return build_trade_replay_report(parts[1] if len(parts) > 1 else None)
    if cmd0 in {"/globalstats", "/statsglobal", "/estatisticas"}:
        return build_global_stats_report()
    if cmd0 in {"/signalai", "/ia", "/quality"}:
        parts = raw.split()
        return build_signal_ai_report(parts[1] if len(parts) > 1 else None)
    if cmd0 in {"/capital", "/equity"}:
        return build_capital_report()
    if cmd0 in {"/correlation", "/correlacao", "/correlação"}:
        return build_correlation_report()
    if cmd0 in {"/timeheat", "/temporal", "/heat24"}:
        return build_time_heatmap_report()
    if cmd0 in {"/marketscore", "/mercado"}:
        return build_market_score_report()
    if cmd0 in {"/allocation", "/alocacao", "/alocação"}:
        return build_capital_allocation_report()
    if cmd0 in {"/exposurev2", "/exposicaov2", "/exposiçãov2", "/botexposurev2"}:
        parts = raw.split()
        try:
            capital_arg = float(parts[1]) if len(parts) > 1 else 10000.0
        except Exception:
            capital_arg = 10000.0
        text_v2, _ = build_bot_exposure_manager_v2_text(capital=capital_arg)
        return text_v2
    if cmd0 in {"/adaptiveweights", "/adaptiveweightsv1", "/awe", "/awev1", "/pesos", "/pesosadaptativos", "/adaptive"}:
        parts = raw.split()
        bot_arg = parts[1].upper() if len(parts) > 1 else None
        symbol_arg = parts[2].upper() if len(parts) > 2 else None
        side_arg = parts[3].upper() if len(parts) > 3 else None
        try:
            entry_arg = float(parts[4]) if len(parts) > 4 else None
        except Exception:
            entry_arg = None
        try:
            stop_arg = float(parts[5]) if len(parts) > 5 else None
        except Exception:
            stop_arg = None
        setup_arg = parts[6].upper() if len(parts) > 6 else None
        text_awe, _ = build_adaptive_weight_engine_v1_text(capital=10000.0, bot=bot_arg, symbol=symbol_arg, side=side_arg, entry=entry_arg, stop=stop_arg, setup=setup_arg)
        return text_awe
    if cmd0 in {"/decisionscore", "/decisionscorev1", "/decisionscoreengine", "/dse", "/scoredecision", "/scoredecisao", "/scoredecisão"}:
        parts = raw.split()
        bot_arg = parts[1].upper() if len(parts) > 1 else None
        symbol_arg = parts[2].upper() if len(parts) > 2 else None
        side_arg = parts[3].upper() if len(parts) > 3 else None
        try:
            entry_arg = float(parts[4]) if len(parts) > 4 else None
        except Exception:
            entry_arg = None
        try:
            stop_arg = float(parts[5]) if len(parts) > 5 else None
        except Exception:
            stop_arg = None
        setup_arg = parts[6].upper() if len(parts) > 6 else None
        text_score, _ = build_decision_score_engine_v1_text(capital=10000.0, bot=bot_arg, symbol=symbol_arg, side=side_arg, entry=entry_arg, stop=stop_arg, setup=setup_arg)
        return text_score
    if cmd0 in {"/executionpolicy", "/executionpolicyv1", "/policy", "/policyv1", "/canexecute", "/execpolicy", "/epe", "/politicaexecucao", "/políticaexecução"}:
        parts = raw.split()
        bot_arg = parts[1].upper() if len(parts) > 1 else None
        symbol_arg = parts[2].upper() if len(parts) > 2 else None
        side_arg = parts[3].upper() if len(parts) > 3 else None
        try:
            entry_arg = float(parts[4]) if len(parts) > 4 else None
        except Exception:
            entry_arg = None
        try:
            stop_arg = float(parts[5]) if len(parts) > 5 else None
        except Exception:
            stop_arg = None
        setup_arg = parts[6].upper() if len(parts) > 6 else None
        text_policy, _ = build_execution_policy_v1_text(capital=10000.0, bot=bot_arg, symbol=symbol_arg, side=side_arg, entry=entry_arg, stop=stop_arg, setup=setup_arg)
        return text_policy
    if cmd0 in {"/positionsizing", "/positionsizingv1", "/sizing", "/sizingv1", "/dps", "/dynamicposition", "/dynamicpositionv1", "/tamanho", "/tamanhoposicao", "/tamanhoposição"}:
        parts = raw.split()
        try:
            capital_arg = float(parts[1]) if len(parts) > 1 else 10000.0
        except Exception:
            capital_arg = 10000.0
        bot_arg = parts[2].upper() if len(parts) > 2 else None
        text_dps, _ = build_dynamic_position_sizing_v11_text(capital=capital_arg, bot_filter=bot_arg)
        return text_dps
    if cmd0 in {"/riskbudget", "/riskbudgetv1", "/dynamicrisk", "/dynamicriskv1", "/drb", "/orcamentorisco", "/orçamentorisco"}:
        parts = raw.split()
        try:
            capital_arg = float(parts[1]) if len(parts) > 1 else 10000.0
        except Exception:
            capital_arg = 10000.0
        text_drb, _ = build_dynamic_risk_budget_v1_text(capital=capital_arg)
        return text_drb
    if cmd0 in {"/portfoliooptimizer", "/optimizer", "/optimizador", "/otimizador", "/portfolioopt", "/optimizerv1"}:
        parts = raw.split()
        try:
            capital_arg = float(parts[1]) if len(parts) > 1 else 10000.0
        except Exception:
            capital_arg = 10000.0
        text_optimizer, _ = build_portfolio_optimizer_v1_text(capital=capital_arg)
        return text_optimizer
    if cmd0 in {"/portfolioadvisor", "/advisor", "/portfolio", "/portfoliov1", "/advisorv1"}:
        parts = raw.split()
        try:
            capital_arg = float(parts[1]) if len(parts) > 1 else 10000.0
        except Exception:
            capital_arg = 10000.0
        text_advisor, _ = build_portfolio_advisor_v1_text(capital=capital_arg)
        return text_advisor
    if cmd0 in {"/exposurescorev2", "/scorev2", "/scoreexposurev2"}:
        parts = raw.split()
        try:
            capital_arg = float(parts[1]) if len(parts) > 1 else 10000.0
        except Exception:
            capital_arg = 10000.0
        text_score, _ = build_exposure_score_engine_v2_text(capital=capital_arg)
        return text_score
    if cmd0 in {"/exposurescore", "/scoreexposure", "/exposurescorev1", "/scorev1"}:
        parts = raw.split()
        try:
            capital_arg = float(parts[1]) if len(parts) > 1 else 10000.0
        except Exception:
            capital_arg = 10000.0
        text_score, _ = build_exposure_score_engine_v1_text(capital=capital_arg)
        return text_score
    if cmd0 in {"/rankingvivo", "/rankinglive"}:
        return build_ranking_vivo_report()
    if cmd0 in {"/evolution", "/evolucao", "/evolução"}:
        return build_evolution_dashboard_v3()
    if cmd0 in {"/learning", "/aprendizado"}:
        return build_learning_report()
    if cmd0 in {"/quantos", "/quantsystem"}:
        return build_quantos_report()
    if cmd0 in {"/status"}:
        return build_status_report()
    if cmd0 in {"/timeline"}:
        parts = raw.split()
        return build_timeline_report(parts[1] if len(parts) > 1 else None)
    if cmd0 in {"/decisionlog", "/decisions"}:
        parts = raw.split()
        return build_decision_log_report(parts[1] if len(parts) > 1 else None)
    if cmd0 in {"/executionstats", "/execstats"}:
        return build_execution_stats_report()
    if cmd0 in {"/consistency", "/consistencia"}:
        return build_consistency_report()
    if cmd0 in {"/brokerhealth", "/brokerstats"}:
        return build_broker_health_report()
    if cmd0 in {"/latency", "/latencia"}:
        return build_latency_report()
    if cmd0 in {"/livepositions"}:
        return build_live_positions_report()
    if cmd0 in {"/verifyqueue"}:
        return build_verify_queue_report()

    parsed_report = parse_report_command(raw)
    if parsed_report:
        mode, bot_key = parsed_report
        return build_central_report(mode, bot_key=bot_key)

    return None


def _central_command_title(text: str):
    cmd = (text or "").strip().lower().split()[0].split("@")[0] if text else ""
    mapping = {
        "/menu": "MENU",
        "/comandos": "MENU",
        "/start": "MENU",
        "/dashboard": "DASHBOARD",
        "/daily": "DAILY",
        "/diario": "DAILY",
        "/diário": "DAILY",
        "/executivereport": "EXECUTIVE REPORT",
        "/executive_report": "EXECUTIVE REPORT",
        "/dailyexecutive": "EXECUTIVE REPORT",
        "/daily_executive": "EXECUTIVE REPORT",
        "/ceoconfidence": "CEO CONFIDENCE",
        "/ceo_confidence": "CEO CONFIDENCE",
        "/confidence": "CEO CONFIDENCE",
        "/confianca": "CEO CONFIDENCE",
        "/confiança": "CEO CONFIDENCE",
        "/strategicadvisor": "STRATEGIC ADVISOR",
        "/strategic_advisor": "STRATEGIC ADVISOR",
        "/strategy": "STRATEGIC ADVISOR",
        "/estrategia": "STRATEGIC ADVISOR",
        "/estratégia": "STRATEGIC ADVISOR",
        "/decisionpack": "DECISION PACK",
        "/decision_pack": "DECISION PACK",
        "/decision": "DECISION PACK",
        "/decisao": "DECISION PACK",
        "/decisão": "DECISION PACK",
        "/executivedecision": "EXECUTIVE DECISION",
        "/executive_decision": "EXECUTIVE DECISION",
        "/decisionengine": "EXECUTIVE DECISION",
        "/decision_engine": "EXECUTIVE DECISION",
        "/policy": "EXECUTIVE POLICY",
        "/policyautorelease": "POLICY AUTO RELEASE",
        "/policyautoreleasehealth": "POLICY AUTO RELEASE HEALTH",
        "/policypriority": "POLICY PRIORITY",
        "/policypriorityhealth": "POLICY PRIORITY HEALTH",
        "/politica": "EXECUTIVE POLICY",
        "/política": "EXECUTIVE POLICY",
        "/monthly": "MENSAL",
        "/mensal": "MENSAL",
        "/monthlyreport": "MENSAL",
        "/monthly_report": "MENSAL",
        "/support": "SUPORTE",
        "/audit": "AUDITORIA",
        "/auditoria": "AUDITORIA",
        "/relatoriocompleto": "AUDITORIA",
        "/relatorio_completo": "AUDITORIA",
        "/full": "FULL",
        "/trend": "TRENDPRO",
        "/donkey": "DONKEY",
        "/cobra": "COBRA",
        "/meme": "MEME",
        "/predator": "PREDATOR",
        "/turtle": "TURTLE",
        "/falcon": "FALCON",
        "/live": "LIVE",
        "/sync": "SYNC",
        "/executions": "EXECUTIONS",
        "/journal": "JOURNAL",
        "/trade": "TRADE",
        "/globalstats": "GLOBAL STATS",
        "/signalai": "SIGNAL AI",
        "/capital": "CAPITAL",
        "/correlation": "CORRELATION",
        "/timeheat": "TIME HEAT",
        "/marketscore": "MARKET SCORE",
        "/allocation": "ALLOCATION",
        "/portfolioadvisor": "PORTFOLIO ADVISOR",
        "/advisor": "PORTFOLIO ADVISOR",
        "/portfolio": "PORTFOLIO ADVISOR",
        "/portfoliooptimizer": "PORTFOLIO OPTIMIZER",
        "/optimizer": "PORTFOLIO OPTIMIZER",
        "/otimizador": "PORTFOLIO OPTIMIZER",
        "/rankingvivo": "RANKING VIVO",
        "/evolution": "EVOLUTION",
        "/evolucao": "EVOLUÇÃO",
        "/evolução": "EVOLUÇÃO",
        "/learning": "LEARNING",
        "/quantos": "QUANT OS",
        "/status": "STATUS",
        "/timeline": "TIMELINE",
        "/decisionlog": "DECISION LOG",
        "/executionstats": "EXECUTION STATS",
        "/consistency": "CONSISTÊNCIA",
        "/brokerhealth": "BROKER HEALTH",
        "/latency": "LATÊNCIA",
        "/livepositions": "LIVE POSITIONS",
        "/verifyqueue": "VERIFY QUEUE",
    }
    return mapping.get(cmd, "CENTRAL QUANT")


def _is_heavy_central_command(text: str):
    cmd = (text or "").strip().lower().split()[0].split("@")[0] if text else ""
    return cmd in {
        "/dashboard", "/daily", "/diario", "/diário", "/executivereport", "/executive_report", "/dailyexecutive", "/daily_executive", "/ceoconfidence", "/ceo_confidence", "/confidence", "/confianca", "/confiança", "/strategicadvisor", "/strategic_advisor", "/strategy", "/estrategia", "/estratégia", "/decisionpack", "/decision_pack", "/decision", "/decisao", "/decisão", "/executivedecision", "/executive_decision", "/decisionengine", "/decision_engine", "/policy", "/politica", "/política", "/monthly", "/mensal", "/monthlyreport", "/monthly_report", "/support",
        "/audit", "/auditoria", "/relatoriocompleto", "/relatorio_completo",
        "/full", "/trend", "/donkey", "/cobra", "/meme", "/predator", "/turtle", "/falcon",
        "/quantos", "/journal", "/trade", "/globalstats", "/signalai", "/capital", "/portfolioadvisor", "/advisor", "/portfolio",
        "/portfoliooptimizer", "/optimizer", "/otimizador", "/portfolioopt",
                "/correlation", "/timeheat", "/marketscore", "/allocation", "/rankingvivo", "/evolution", "/evolucao", "/evolução", "/learning",
        "/timeline", "/decisionlog", "/executionstats", "/consistency", "/brokerhealth", "/latency",
        "/livepositions", "/verifyqueue", "/status",
    }



def cmd0_safe(text: str):
    try:
        return (text or "").strip().lower().split()[0].split("@")[0].replace("/", "") or "command"
    except Exception:
        return "command"

def central_telegram_command_loop():
    global CENTRAL_TELEGRAM_OFFSET, CENTRAL_TELEGRAM_ROUTER_STARTED

    token = CENTRAL_TELEGRAM_BOT_TOKEN
    allowed_chat = CENTRAL_TELEGRAM_CHAT_ID

    if not CENTRAL_TELEGRAM_POLLING_ENABLED:
        print("ROTEADOR TELEGRAM CENTRAL DESLIGADO POR ENV")
        return
    if not token:
        print("ROTEADOR TELEGRAM CENTRAL NÃO INICIADO: CENTRAL_TELEGRAM_BOT_TOKEN ausente")
        return

    # Trava forte dentro do processo: impede dois roteadores centrais usando o mesmo token.
    with CENTRAL_TELEGRAM_ROUTER_LOCK:
        if CENTRAL_TELEGRAM_ROUTER_STARTED:
            print("ROTEADOR TELEGRAM CENTRAL JÁ INICIADO - ignorando segunda thread")
            return
        CENTRAL_TELEGRAM_ROUTER_STARTED = True

    if CENTRAL_TELEGRAM_DROP_PENDING_ON_START and CENTRAL_TELEGRAM_OFFSET is None:
        drained_offset = telegram_drain_pending_updates(token)
        if drained_offset is not None:
            CENTRAL_TELEGRAM_OFFSET = drained_offset

    print("ROTEADOR TELEGRAM CENTRAL QUANT INICIADO")

    while True:
        try:
            updates, warning = telegram_get_updates_for_token(token, CENTRAL_TELEGRAM_OFFSET)
            if warning:
                if not is_benign_telegram_conflict(warning):
                    print("WARNING TELEGRAM CENTRAL:", warning)
                time.sleep(2)
                continue

            for upd in updates:
                update_id = upd.get("update_id", 0)
                CENTRAL_TELEGRAM_OFFSET = update_id + 1

                # Dedupe dentro do mesmo processo. Ajuda a evitar resposta duplicada
                # em reinícios rápidos ou quando o Telegram reentrega update.
                if update_id in CENTRAL_TELEGRAM_PROCESSED_UPDATES:
                    continue
                CENTRAL_TELEGRAM_PROCESSED_UPDATES.add(update_id)
                if len(CENTRAL_TELEGRAM_PROCESSED_UPDATES) > 500:
                    # mantém o set pequeno para não crescer indefinidamente
                    CENTRAL_TELEGRAM_PROCESSED_UPDATES.clear()
                    CENTRAL_TELEGRAM_PROCESSED_UPDATES.add(update_id)

                msg = upd.get("message") or {}
                text = (msg.get("text") or "").strip()
                chat_id = str((msg.get("chat") or {}).get("id", ""))

                if not text.startswith("/"):
                    continue
                if allowed_chat and chat_id != str(allowed_chat):
                    continue

                if _is_duplicate_recent_central_command(chat_id, text):
                    print(f"TELEGRAM CENTRAL: comando duplicado ignorado: chat={chat_id} text={text}")
                    continue

                title = _central_command_title(text)
                try:
                    try:
                        import history_manager as super_history_manager
                        super_history_manager.log_event("CENTRAL_COMMAND", {
                            "command": text.split()[0] if text else "",
                            "full_text": text,
                            "chat_id": chat_id,
                            "router": "central",
                        }, source="telegram_central")
                    except Exception as _history_exc:
                        print("ERRO HISTORY command central:", _history_exc)

                    if TELEGRAM_LONG_COMMAND_NOTICE and _is_heavy_central_command(text):
                        telegram_send_with_token(token, chat_id, f"⏳ Gerando {title.lower()}...\nVou enviar em partes se ficar grande.")

                    memory_profile_step(f"central_telegram_before_{text.split()[0]}")
                    reply = build_central_command_reply(text)
                    memory_profile_step(f"central_telegram_after_{text.split()[0]}")
                    if reply:
                        telegram_send_with_token(token, chat_id, reply, title=title)
                        try:
                            del reply
                        except Exception:
                            pass
                        if _is_heavy_central_command(text):
                            force_gc_if_needed(f"central_telegram_after_{cmd0_safe(text)}", force=True)
                    else:
                        telegram_send_with_token(token, chat_id, "Comando não reconhecido. Use /help para ver os comandos.")
                except Exception as exc:
                    print("ERRO COMANDO CENTRAL:", text, exc)
                    telegram_send_with_token(token, chat_id, f"⚠️ Erro ao executar {text}: {exc}")
        except Exception as exc:
            print("ERRO ROTEADOR TELEGRAM CENTRAL:", exc)

        time.sleep(2)


def central_daily_report_loop():
    """
    Envia relatórios automáticos pelo Telegram exclusivo da Central.
    - Diário: Executive Report compacto no horário configurado.
    - Mensal: dia 1 às 00:05 por padrão, consolidando o mês anterior.
    """
    global CENTRAL_DAILY_REPORT_SENT_DATE, CENTRAL_MONTHLY_REPORT_SENT_KEY

    if not CENTRAL_DAILY_REPORT_ENABLED and not CENTRAL_MONTHLY_REPORT_ENABLED:
        print("RELATÓRIOS AUTOMÁTICOS CENTRAL DESLIGADOS POR ENV")
        return

    while True:
        try:
            now = agora_sp()
            current_hm = now.strftime("%H:%M")
            today = now.strftime("%Y-%m-%d")

            # Relatório diário.
            if CENTRAL_DAILY_REPORT_ENABLED and current_hm == CENTRAL_DAILY_REPORT_TIME and CENTRAL_DAILY_REPORT_SENT_DATE != today:
                print(f"GERANDO EXECUTIVE REPORT DIÁRIO CENTRAL {today} {current_hm}")
                try:
                    save_daily_snapshot(label="auto")
                except Exception as exc:
                    print("ERRO SNAPSHOT RELATÓRIO DIÁRIO CENTRAL:", exc)

                mode = (CENTRAL_DAILY_REPORT_MODE or "executivo").strip().lower()
                if mode in {"completo", "full", "audit", "auditoria"}:
                    payload = build_audit_parts()
                    title = "RELATÓRIO DIÁRIO COMPLETO"
                elif mode in {"daily", "diario", "diário", "legacy"}:
                    payload = build_daily_report()
                    title = "RELATÓRIO DIÁRIO"
                elif mode in {"dashboard", "painel"}:
                    payload = build_dashboard_report()
                    title = "DASHBOARD DIÁRIO"
                else:
                    payload = build_ceo_daily_report()
                    title = "CEO DAILY REPORT"

                if CENTRAL_TELEGRAM_BOT_TOKEN and CENTRAL_TELEGRAM_CHAT_ID:
                    telegram_send_with_token(
                        CENTRAL_TELEGRAM_BOT_TOKEN,
                        CENTRAL_TELEGRAM_CHAT_ID,
                        payload,
                        title=title,
                    )
                else:
                    print("RELATÓRIO DIÁRIO CENTRAL NÃO ENVIADO: token/chat ausente")

                try:
                    del payload
                except Exception:
                    pass
                force_gc_if_needed("central_daily_report_after_send", force=True)
                CENTRAL_DAILY_REPORT_SENT_DATE = today

            # Relatório mensal: por padrão, dia 1 às 00:05, consolidando o mês anterior.
            if CENTRAL_MONTHLY_REPORT_ENABLED and now.day == CENTRAL_MONTHLY_REPORT_DAY and current_hm == CENTRAL_MONTHLY_REPORT_TIME:
                _start_dt, _end_dt, month_key, _month_label = _month_bounds_previous(now)
                if CENTRAL_MONTHLY_REPORT_SENT_KEY != month_key:
                    print(f"GERANDO EXECUTIVE REPORT MENSAL CENTRAL {month_key} {current_hm}")
                    payload = build_executive_report_monthly()
                    if CENTRAL_TELEGRAM_BOT_TOKEN and CENTRAL_TELEGRAM_CHAT_ID:
                        telegram_send_with_token(
                            CENTRAL_TELEGRAM_BOT_TOKEN,
                            CENTRAL_TELEGRAM_CHAT_ID,
                            payload,
                            title="EXECUTIVE REPORT MENSAL",
                        )
                    else:
                        print("RELATÓRIO MENSAL CENTRAL NÃO ENVIADO: token/chat ausente")
                    try:
                        del payload
                    except Exception:
                        pass
                    force_gc_if_needed("central_monthly_report_after_send", force=True)
                    CENTRAL_MONTHLY_REPORT_SENT_KEY = month_key

        except Exception as exc:
            print("ERRO RELATÓRIOS AUTOMÁTICOS CENTRAL:", exc)

        time.sleep(30)



# ==========================================================
# CENTRAL TELEGRAM COMMAND ROUTER
# ==========================================================
COMMAND_ROUTER_DEFAULTS = {
    "TRENDPRO": False,
    "DONKEY": False,
    "COBRA": False,
    "MEME": False,
    "PREDATOR": False,
    "TURTLE": False,
    "FALCON": False,
}

CENTRAL_COMMAND_OFFSETS = {}


def get_bot_module(name: str):
    return LOADED_BOTS.get(str(name).upper())


def central_route_enabled_for_bot(key: str) -> bool:
    default = COMMAND_ROUTER_DEFAULTS.get(key.upper(), False)
    return env_bool(f"CENTRAL_ROUTE_{key.upper()}_TELEGRAM", default=default)


def telegram_get_updates_for_token(token, offset=None):
    if not token:
        return [], None
    try:
        params = {"timeout": 20}
        if offset:
            params["offset"] = offset
        url = f"https://api.telegram.org/bot{token}/getUpdates"
        r = requests.get(url, params=params, timeout=25)
        if r.status_code != 200:
            return [], f"getUpdates {r.status_code}: {r.text[:180]}"
        return r.json().get("result", []), None
    except Exception as exc:
        return [], f"getUpdates: {exc}"



def telegram_drain_pending_updates(token):
    """
    Ao iniciar/reiniciar a Central, limpa comandos pendentes do Telegram
    sem responder a comandos antigos. Isso reduz duplicidade depois de deploy.
    Não apaga webhook nem mensagens futuras; apenas avança o offset local.
    """
    if not token:
        return None
    try:
        url = f"https://api.telegram.org/bot{token}/getUpdates"
        r = requests.get(url, params={"timeout": 0}, timeout=10)
        if r.status_code != 200:
            print(f"WARNING TELEGRAM CENTRAL DRAIN: {r.status_code}: {r.text[:180]}")
            return None
        updates = r.json().get("result", []) or []
        if not updates:
            return None
        max_update_id = max(int(u.get("update_id", 0) or 0) for u in updates)
        next_offset = max_update_id + 1
        print(f"TELEGRAM CENTRAL: pendentes ignorados no startup = {len(updates)} | next_offset={next_offset}")
        return next_offset
    except Exception as exc:
        print("WARNING TELEGRAM CENTRAL DRAIN:", exc)
        return None


def _central_command_fingerprint(chat_id, text):
    """Fingerprint curta para dedupe de comandos repetidos em poucos segundos."""
    raw = (text or "").strip()
    # Normaliza menção do bot e espaços, mas mantém argumentos.
    parts = raw.split()
    if parts:
        parts[0] = parts[0].split("@", 1)[0]
    normalized = " ".join(parts).lower()
    return f"{chat_id}|{normalized}"


def _is_duplicate_recent_central_command(chat_id, text):
    now = time.time()
    fp = _central_command_fingerprint(chat_id, text)

    # limpeza leve para não crescer indefinidamente
    expired = [k for k, ts in CENTRAL_TELEGRAM_RECENT_COMMANDS.items() if now - ts > max(60, CENTRAL_COMMAND_DUPLICATE_WINDOW_SECONDS * 4)]
    for k in expired[:200]:
        CENTRAL_TELEGRAM_RECENT_COMMANDS.pop(k, None)

    last = CENTRAL_TELEGRAM_RECENT_COMMANDS.get(fp)
    if last is not None and now - last < CENTRAL_COMMAND_DUPLICATE_WINDOW_SECONDS:
        return True

    CENTRAL_TELEGRAM_RECENT_COMMANDS[fp] = now
    return False

def split_telegram_text(text, limit=None):
    """Divide texto respeitando quebras de linha quando possível."""
    limit = int(limit or TELEGRAM_CHUNK_SIZE or 3400)
    txt = "" if text is None else str(text)
    if len(txt) <= limit:
        return [txt]

    chunks = []
    remaining = txt
    while len(remaining) > limit:
        cut = remaining.rfind("\n", 0, limit)
        if cut < int(limit * 0.55):
            cut = remaining.rfind(" ", 0, limit)
        if cut < int(limit * 0.55):
            cut = limit
        chunks.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip()
    if remaining:
        chunks.append(remaining)
    return chunks


def _is_duplicate_recent_central_send(chat_id, full_text):
    """Evita enviar exatamente a mesma mensagem duas vezes em poucos segundos."""
    try:
        now = time.time()
        txt = str(full_text or "")
        fp = f"{chat_id}|{hash(txt)}"
        expired = [k for k, ts in CENTRAL_TELEGRAM_RECENT_SENDS.items() if now - ts > max(60, CENTRAL_SEND_DUPLICATE_WINDOW_SECONDS * 4)]
        for k in expired[:200]:
            CENTRAL_TELEGRAM_RECENT_SENDS.pop(k, None)
        last = CENTRAL_TELEGRAM_RECENT_SENDS.get(fp)
        if last is not None and now - last < CENTRAL_SEND_DUPLICATE_WINDOW_SECONDS:
            return True
        CENTRAL_TELEGRAM_RECENT_SENDS[fp] = now
        return False
    except Exception:
        return False


def telegram_send_with_token(token, chat_id, text, title=None):
    """
    Envia mensagens longas em partes. Aceita string ou lista de tuplas
    (titulo, texto). Loga falhas do Telegram em vez de silenciar.
    """
    if not token or not chat_id:
        print(text)
        return False
    try:
        # Lista de seções: [(titulo, texto), ...]
        if isinstance(text, list):
            ok_all = True
            total_sections = len(text)
            for idx, item in enumerate(text, 1):
                if isinstance(item, tuple) and len(item) == 2:
                    section_title, section_text = item
                else:
                    section_title, section_text = f"PARTE {idx}", item
                header = f"📦 {title or 'RELATÓRIO CENTRAL'} — SEÇÃO {idx}/{total_sections}\n{section_title}\n\n"
                ok = telegram_send_with_token(token, chat_id, header + str(section_text), title=None)
                ok_all = ok_all and ok
                try:
                    del section_text
                except Exception:
                    pass
                if idx % 3 == 0:
                    force_gc_if_needed("telegram_sections", force=True)
                time.sleep(0.35)
            force_gc_if_needed("telegram_sections_done", force=True)
            return ok_all

        chunks = split_telegram_text(text, TELEGRAM_CHUNK_SIZE)
        total = len(chunks)
        ok_all = True
        for i, chunk in enumerate(chunks, 1):
            prefix = ""
            if title or total > 1:
                label = title or "CENTRAL QUANT"
                prefix = f"📦 {label} — PARTE {i}/{total}\n\n" if total > 1 else f"📦 {label}\n\n"
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            full_message = prefix + chunk
            if _is_duplicate_recent_central_send(chat_id, full_message):
                print(f"TELEGRAM CENTRAL: envio duplicado ignorado chat={chat_id} title={title}")
                continue
            payload = {
                "chat_id": chat_id,
                "text": full_message,
                "disable_web_page_preview": True,
            }
            r = requests.post(url, json=payload, timeout=20)
            if r.status_code != 200:
                ok_all = False
                print(f"ERRO TELEGRAM SEND {r.status_code}: {r.text[:300]}")
            time.sleep(0.35)
        return ok_all
    except Exception as exc:
        print("ERRO TELEGRAM CENTRAL ROUTER:", exc)
        return False


def build_command_reply_for_module(key: str, module, cmd: str):
    raw_cmd = (cmd or "").strip()
    cmd0 = raw_cmd.lower().split()[0].split("@")[0] if raw_cmd else ""

    if cmd0 in {"/diagnostico", "/diagnóstico", "/diag"}:
        return build_diagnostic_report()

    if cmd0 in {"/selftest", "/self-test", "/teste", "/autoteste"}:
        return build_selftest_report()

    if cmd0 in {"/memory", "/memoria", "/memória"}:
        try:
            if MEMORY_PROFILER_LOADED and memory_profiler:
                return memory_profiler.build_memory_report(include_tracemalloc=False)
        except Exception as exc:
            return f"⚠️ Erro no Memory Profiler V1.3.1.2: {exc}\n\nFallback antigo:\n{build_memory_text(run_gc=False)[0]}"
        text, _payload = build_memory_text(run_gc=False)
        return text

    if cmd0 in {"/memorydeep", "/memoriadeep", "/memory/deep", "/memoria/deep"}:
        try:
            if MEMORY_PROFILER_LOADED and memory_profiler:
                return memory_profiler.build_memory_report(include_tracemalloc=True)
        except Exception as exc:
            return f"⚠️ Erro no /memorydeep: {exc}"
        return "Memory Profiler V1.3.1.2 não carregado: " + str(MEMORY_PROFILER_ERROR)

    if cmd0 in {"/memorygc", "/memory_gc", "/memoriagc", "/memoria_gc"}:
        text, _payload = build_memory_text(run_gc=True)
        try:
            if MEMORY_PROFILER_LOADED and memory_profiler:
                return memory_profiler.build_memory_report(include_tracemalloc=False) + "\n\n" + text
        except Exception:
            pass
        return text

    if cmd0 in {"/executive", "/dashboard"}:
        return build_executive_report()
    if cmd0 in {"/execution", "/execucao", "/execução", "/bingx"}:
        return build_execution_report()
    if cmd0 in {"/live", "/livestatus"}:
        return build_live_report()
    if cmd0 in {"/sync", "/reconcile"}:
        return build_sync_report()
    if cmd0 in {"/executions", "/exec_log", "/executionlog"}:
        return build_executions_log_report()
    if cmd0 in {"/auditrisk", "/riskaudit"}:
        parts = cmd.split()
        return build_audit_risk_report(parts[1] if len(parts) > 1 else 2)
    if cmd0 in {"/risk", "/riskmanager"}:
        return build_risk_report()
    if cmd0 in {"/heat", "/heatmap"}:
        return build_heatmap_report()
    if cmd0 in {"/ranking"}:
        return build_ranking_report()
    if cmd0 in {"/healthscore", "/score"}:
        return build_healthscore_report()
    if cmd0 in {"/meta", "/metasupervisor"}:
        return build_meta_supervisor_report()
    if cmd0 in {"/history"}:
        return __import__("history_manager").build_history_report()
    if cmd0 in {"/riskstats", "/riscoestatisticas", "/estatisticashistory"}:
        try:
            import history_manager as super_history_manager
            return super_history_manager.build_riskstats_report()
        except Exception as exc:
            return f"⚠️ Erro ao gerar /riskstats: {exc}"
    if cmd0 in {"/exporthistory", "/exportarhistory"}:
        try:
            import history_manager as super_history_manager
            return super_history_manager.build_export_report()
        except Exception as exc:
            return f"⚠️ Erro ao gerar /exporthistory: {exc}"
    if cmd0 in {"/snapshot"}:
        return build_snapshot_report()
    if cmd0 in {"/simulate"}:
        parts = raw_cmd.split()
        return build_simulate_report(parts[1] if len(parts) > 1 else None)
    if cmd0 in {"/dashboard"}:
        return build_dashboard_report()
    if cmd0 in {"/daily", "/diario", "/diário"}:
        return build_ceo_daily_report()
    if cmd0 in {"/support"}:
        return build_support_report()
    if cmd0 in {"/audit", "/auditoria", "/relatoriocompleto", "/relatorio_completo"}:
        return build_audit_parts()
    if cmd0 in {"/full"}:
        return build_full_parts()
    if cmd0 in {"/relatoriocompleto", "/relatorio_completo"}:
        return build_audit_parts()
    if cmd0 in {"/trend", "/trendpro"}:
        return build_single_bot_report("TRENDPRO", complete=True)
    if cmd0 in {"/donkey"}:
        return build_single_bot_report("DONKEY", complete=True)
    if cmd0 in {"/cobra"}:
        return build_single_bot_report("COBRA", complete=True)
    if cmd0 in {"/meme"}:
        return build_single_bot_report("MEME", complete=True)
    if cmd0 in {"/predator", "/smart", "/smartpredator"}:
        return build_single_bot_report("PREDATOR", complete=True)
    if cmd0 in {"/turtle"}:
        return build_single_bot_report("TURTLE", complete=True)
    if cmd0 in {"/falcon"}:
        return build_single_bot_report("FALCON", complete=True)

    parsed_report = parse_report_command(raw_cmd)
    if parsed_report:
        mode, bot_key = parsed_report
        return build_central_report(mode, bot_key=bot_key)

    cmd = cmd0

    if key == "TURTLE":
        if cmd == "/health":
            fn = getattr(module, "refresh_health_stats", None)
            if callable(fn):
                fn()
            return json.dumps(getattr(module, "HEALTH", {}), ensure_ascii=False, indent=2)
        if cmd == "/funil":
            return _json_or_text(_call_first(module, ["funnel_text"]))
        if cmd == "/eventos":
            return _json_or_text(_call_first(module, ["events_text"]))
        if cmd == "/resumo":
            if hasattr(module, "build_summary") and hasattr(module, "trades_today"):
                return module.build_summary("DIA", module.trades_today())
        if cmd == "/posicoes":
            return _json_or_text(_call_first(module, ["positions_text"]))
        if cmd == "/top":
            return _json_or_text(_call_first(module, ["top_mfe_text"]))
        if cmd == "/ranking":
            return _json_or_text(_call_first(module, ["ranking_command_text"]))
        if cmd in ["/start", "/comandos"]:
            return (
                "🐢 COMANDOS TURTLE BREAKOUT PRO 2.0\n\n"
                "/health\n/posicoes\n/resumo\n/funil\n/eventos\n/top\n/ranking\n/relatorio\n/relatorio completo\n/memory\n/selftest"
            )

    if key == "FALCON":
        if cmd == "/health":
            return _json_or_text(_call_first(module, ["health_payload"]))
        if cmd == "/funil":
            return _json_or_text(_call_first(module, ["funnel_text"]))
        if cmd == "/eventos":
            return _json_or_text(_call_first(module, ["events_text"]))
        if cmd == "/resumo":
            if hasattr(module, "build_summary") and hasattr(module, "trades_today"):
                return module.build_summary("DIA", module.trades_today())
        if cmd == "/posicoes":
            return _json_or_text(_call_first(module, ["positions_text"]))
        if cmd == "/watchlist":
            if hasattr(module, "load_watchlist"):
                wl = module.load_watchlist()
                return "🦅 WATCHLIST FALCON\n\n" + "\n".join([str(x) for x in wl[:100]])
        if cmd in ["/start", "/comandos"]:
            return "🦅 Comandos Falcon:\n/health\n/posicoes\n/resumo\n/funil\n/eventos\n/watchlist\n/relatorio\n/relatorio completo\n/memory\n/selftest"

    if cmd == "/health":
        h = getattr(module, "HEALTH", None)
        return json.dumps(h or bot_health(key, BOT_CONFIGS[key]), ensure_ascii=False, indent=2)
    if cmd == "/funil":
        return _json_or_text(_call_first(module, ["montar_funil_texto", "montar_funil", "funnel_text", "funil_texto"]))
    if cmd == "/eventos":
        return _json_or_text(_call_first(module, ["montar_eventos_texto", "events_text", "eventos_texto"]))
    if cmd == "/resumo":
        return _json_or_text(_call_first(module, ["montar_resumo_diario", "build_daily_summary", "summary_text"]))

    return None


def central_command_router_loop(key: str, cfg: dict):
    token = os.environ.get(cfg.get("token_env"))
    allowed_chat = os.environ.get(cfg.get("chat_env"))

    if not token:
        print(f"ROTEADOR TELEGRAM {key} NÃO INICIADO: token ausente")
        return

    print(f"ROTEADOR TELEGRAM CENTRAL INICIADO - {key}")
    offset = CENTRAL_COMMAND_OFFSETS.get(key)

    while True:
        try:
            module = get_bot_module(key)
            updates, warning = telegram_get_updates_for_token(token, offset)

            if warning:
                if module is not None and hasattr(module, "HEALTH"):
                    if is_benign_telegram_conflict(warning):
                        module.HEALTH["last_warning"] = None
                    else:
                        module.HEALTH["last_warning"] = warning
                time.sleep(2)
                continue

            for upd in updates:
                offset = upd.get("update_id", 0) + 1
                CENTRAL_COMMAND_OFFSETS[key] = offset

                msg = upd.get("message") or {}
                text = (msg.get("text") or "").strip()
                chat_id = str((msg.get("chat") or {}).get("id", ""))

                if not text.startswith("/"):
                    continue
                if allowed_chat and chat_id != str(allowed_chat):
                    continue
                if module is None:
                    telegram_send_with_token(token, chat_id, f"{cfg.get('name', key)} não carregado na Central.")
                    continue

                try:
                    import history_manager as super_history_manager
                    super_history_manager.log_event("BOT_COMMAND", {
                        "bot": key,
                        "command": text.split()[0] if text else "",
                        "full_text": text,
                        "chat_id": chat_id,
                        "router": "bot_token_router",
                    }, source="telegram_bot")
                except Exception as _history_exc:
                    print(f"ERRO HISTORY command {key}:", _history_exc)

                memory_profile_step(f"telegram_command_before_{key}_{text.split()[0]}")
                reply = build_command_reply_for_module(key, module, text)
                memory_profile_step(f"telegram_command_after_{key}_{text.split()[0]}")
                if reply:
                    telegram_send_with_token(token, chat_id, reply)
                    health = getattr(module, "HEALTH", None)
                    if isinstance(health, dict):
                        health["last_command_run"] = data_hora_sp_str()

        except Exception as exc:
            print(f"ERRO ROTEADOR TELEGRAM {key}:", exc)
            module = get_bot_module(key)
            if module is not None and hasattr(module, "HEALTH"):
                module.HEALTH["last_warning"] = f"central router: {exc}"

        time.sleep(2)


def start_central_command_routers():
    for key, cfg in BOT_CONFIGS.items():
        if not env_bool(cfg["enabled_env"], default=False):
            continue
        if not central_route_enabled_for_bot(key):
            continue
        if not acquire_runtime_file_lock(f"bot_telegram_{key.lower()}"):
            print(f"ROTEADOR TELEGRAM {key} NÃO INICIADO: outro processo já é líder")
            continue
        threading.Thread(target=central_command_router_loop, args=(key, cfg), daemon=True).start()



# ==========================================================
# QUANT OS ROUTES
# ==========================================================


@app.route("/trade")
@app.route("/trade/<arg>")
@app.route("/replay")
@app.route("/replay/<arg>")
def trade_replay_route(arg=None):
    return {"text": build_trade_replay_report(arg)}


@app.route("/globalstats")
@app.route("/statsglobal")
@app.route("/estatisticas")
def globalstats_route():
    return {"text": build_global_stats_report()}


@app.route("/signalai")
@app.route("/signalai/<arg>")
@app.route("/ia")
@app.route("/ia/<arg>")
def signalai_route(arg=None):
    return {"text": build_signal_ai_report(arg)}


@app.route("/capital")
@app.route("/equity")
def capital_route():
    return {"text": build_capital_report()}


@app.route("/correlation")
@app.route("/correlacao")
def correlation_route():
    return {"text": build_correlation_report()}


@app.route("/timeheat")
@app.route("/temporal")
@app.route("/heat24")
def timeheat_route():
    return {"text": build_time_heatmap_report()}


@app.route("/marketscore")
@app.route("/mercado")
def marketscore_route():
    return {"text": build_market_score_report()}


@app.route("/allocation")
@app.route("/alocacao")
def allocation_route():
    return {"text": build_capital_allocation_report()}


@app.route("/rankingvivo")
@app.route("/rankinglive")
def rankingvivo_route():
    return {"text": build_ranking_vivo_report()}


@app.route("/simulateoff")
@app.route("/simulateoff/<arg>")
@app.route("/simoff")
@app.route("/simoff/<arg>")
def simulateoff_route(arg=None):
    return {"text": build_simulate_off_report(arg)}


# Legacy /learning route removed: handled by Learning Engine V1 routes below.


@app.route("/quantos")
@app.route("/quantsystem")
def quantos_route():
    return {"text": build_quantos_report()}


# ==========================================================
# CONTEXT MANAGER ROUTES
# ==========================================================
@app.route("/context/status")
@app.route("/contexto/status")
def context_status_route():
    try:
        import context_manager
        if hasattr(context_manager, "get_status"):
            return context_manager.get_status()
        return {"ok": False, "error": "context_manager sem get_status"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}, 500


@app.route("/context")
@app.route("/contexto")
def context_route():
    try:
        import context_manager
        return {"text": context_manager.build_context_report()}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}, 500



# ==========================================================
# POLICY ENGINE ROUTES
# ==========================================================
@app.route("/policy/status")
@app.route("/politica/status")
def policy_status_route():
    try:
        import policy_engine
        return policy_engine.get_status()
    except Exception as exc:
        return {"ok": False, "error": str(exc)}, 500


@app.route("/policy")
@app.route("/policy/report")
@app.route("/politica")
def policy_route():
    try:
        import policy_engine
        bot = request.args.get("bot") if "request" in globals() else None
        return {"text": policy_engine.build_policy_report(bot=bot)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}, 500


@app.route("/policy/state")
@app.route("/policy/json")
def policy_state_route():
    try:
        import policy_engine
        return policy_engine.build_policy_payload()
    except Exception as exc:
        return {"ok": False, "error": str(exc)}, 500


@app.route("/policy/audit")
def policy_audit_route():
    try:
        import policy_engine
        limit = request.args.get("limit", 100)
        return policy_engine.build_policy_audit_payload(limit=limit)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}, 500


@app.route("/policy/simulate")
@app.route("/policy/simulate/<bot>")
def policy_simulate_route(bot=None):
    try:
        import policy_engine
        payload = request.get_json(silent=True) or {} if request.method != "GET" else {}
        bot_value = bot or request.args.get("bot") or payload.get("bot")
        score = request.args.get("score") or payload.get("score")
        context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
        return policy_engine.calculate_policy_decision(bot=bot_value, score=score, context=context, dry_run=True)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}, 500



# ==========================================================
# LEARNING ENGINE V1 - OBSERVE ROUTES
# ==========================================================

@app.route("/learning/status")
def learning_status_route():
    try:
        import learning_engine
        return learning_engine.get_status()
    except Exception as exc:
        return {"ok": False, "error": str(exc)}, 500


@app.route("/learning")
@app.route("/learning/report")
@app.route("/aprendizado")
def learning_route():
    try:
        import learning_engine
        text, payload = learning_engine.build_learning_report()
        return {"text": text, "payload": payload}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}, 500


@app.route("/learning/brief")
@app.route("/learning/resumo")
def learning_brief_route():
    try:
        import learning_engine
        text, payload = learning_engine.build_learning_brief()
        return {"text": text, "payload": payload}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}, 500


@app.route("/learning/state")
def learning_state_route():
    try:
        import learning_engine
        return learning_engine.get_state()
    except Exception as exc:
        return {"ok": False, "error": str(exc)}, 500


@app.route("/learning/readiness")
def learning_readiness_route():
    try:
        import learning_engine
        text, payload = learning_engine.build_readiness_report()
        return {"text": text, "payload": payload}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}, 500


# ==========================================================
# LEARNING AUTO REFRESH — V1.3
# Mantém learning_state.json atualizado sem depender de comando manual.
# Não altera Policy, scores, risco, bots nem corretora.
# ==========================================================
LEARNING_AUTO_REFRESH_ENABLED = env_bool("LEARNING_AUTO_REFRESH_ENABLED", True)
LEARNING_AUTO_REFRESH_SECONDS = int(os.environ.get("LEARNING_AUTO_REFRESH_SECONDS", "900"))
LEARNING_AUTO_REFRESH_MIN_SECONDS = 300
LEARNING_AUTO_REFRESH_LAST = {"ts": None, "ok": None, "error": None, "summary": None, "readiness": None}


def learning_auto_refresh_loop():
    interval = max(LEARNING_AUTO_REFRESH_SECONDS, LEARNING_AUTO_REFRESH_MIN_SECONDS)
    while True:
        try:
            import learning_engine
            result = learning_engine.refresh_state(reason="auto_loop")
            LEARNING_AUTO_REFRESH_LAST.update({
                "ts": data_hora_sp_str(),
                "ok": bool(result.get("ok")),
                "error": None,
                "summary": result.get("summary"),
                "readiness": result.get("readiness"),
            })
        except Exception as exc:
            LEARNING_AUTO_REFRESH_LAST.update({
                "ts": data_hora_sp_str(),
                "ok": False,
                "error": str(exc),
            })
            print("ERRO LEARNING AUTO REFRESH:", exc)
        time.sleep(interval)


@app.route("/learning/auto/status")
def learning_auto_status_route():
    return {
        "ok": True,
        "enabled": LEARNING_AUTO_REFRESH_ENABLED,
        "interval_seconds": max(LEARNING_AUTO_REFRESH_SECONDS, LEARNING_AUTO_REFRESH_MIN_SECONDS),
        "last": LEARNING_AUTO_REFRESH_LAST,
        "note": "Auto refresh apenas recalcula o estado do Learning. Não altera operação.",
    }


@app.route("/learning/refresh")
def learning_refresh_route():
    try:
        import learning_engine
        result = learning_engine.refresh_state(reason="manual_route")
        LEARNING_AUTO_REFRESH_LAST.update({
            "ts": data_hora_sp_str(),
            "ok": bool(result.get("ok")),
            "error": None,
            "summary": result.get("summary"),
            "readiness": result.get("readiness"),
        })
        return result
    except Exception as exc:
        return {"ok": False, "error": str(exc)}, 500

def start_central_runtime_once():
    global CENTRAL_RUNTIME_STARTED

    with CENTRAL_RUNTIME_LOCK:
        if CENTRAL_RUNTIME_STARTED:
            print("CENTRAL RUNTIME JÁ INICIADO - ignorando nova chamada")
            return
        CENTRAL_RUNTIME_STARTED = True

    memory_snapshot("before_start_bots", store=True, print_log=True)
    start_enabled_bots()
    memory_snapshot("after_start_bots", store=True, print_log=True)
    force_gc_if_needed("after_start_bots", force=True)

    threading.Thread(target=central_watchdog_loop, daemon=True).start()
    threading.Thread(target=memory_monitor_loop, daemon=True).start()

    try:
        if MEMORY_PROFILER_LOADED and memory_profiler:
            print(memory_profiler.start_memory_profiler(interval_seconds=MEMORY_LOG_INTERVAL_SECONDS))
        else:
            print(f"MEMORY PROFILER V1 NÃO CARREGADO: {MEMORY_PROFILER_ERROR}")
    except Exception as exc:
        print(f"ERRO AO INICIAR MEMORY PROFILER V1: {exc}")

    if LEARNING_AUTO_REFRESH_ENABLED:
        if acquire_runtime_file_lock("learning_auto_refresh"):
            threading.Thread(target=learning_auto_refresh_loop, daemon=True).start()
        else:
            print("LEARNING AUTO REFRESH NÃO INICIADO: outro processo já é líder")

    if acquire_runtime_file_lock("central_telegram_polling"):
        threading.Thread(target=central_telegram_command_loop, daemon=True).start()
    else:
        print("ROTEADOR TELEGRAM CENTRAL NÃO INICIADO: outro processo já é líder")

    if acquire_runtime_file_lock("central_daily_report"):
        threading.Thread(target=central_daily_report_loop, daemon=True).start()
    else:
        print("RELATÓRIO DIÁRIO CENTRAL NÃO INICIADO: outro processo já é líder")

    start_central_command_routers()


# ==========================================================
# PATCH FINAL - SUPER HISTORY CENTRAL QUANT
# Cole este bloco no FINAL do main.py, imediatamente ANTES desta linha:
# start_central_runtime_once()
# ==========================================================

try:
    import history_manager as super_history_manager

    super_history_manager.wrap_central_functions(globals())

    @app.route("/riskstats")
    @app.route("/riscoestatisticas")
    def super_riskstats_route():
        return {"text": super_history_manager.build_riskstats_report(), "payload": super_history_manager.build_riskstats_payload()}

    @app.route("/exporthistory")
    @app.route("/exportarhistory")
    def super_exporthistory_route():
        return super_history_manager.build_export_payload()

    @app.route("/history/trades")
    def history_trades():
        try:
            import history_manager
            payload = history_manager.build_closed_trades_payload()

            return {
                "ok": True,
                "text": (
                    "🧾 HISTORY TRADES — CENTRAL QUANT\n"
                    f"Data/hora: {payload.get('generated_at')}\n\n"
                    f"Trades consolidados: {payload.get('count', 0)}\n\n"
                    f"Wins: {payload['metrics']['wins']}\n"
                    f"Losses: {payload['metrics']['losses']}\n"
                    f"Win Rate: {payload['metrics']['win_rate_pct']}%\n"
                    f"PnL Total: {payload['metrics']['pnl_total_pct']}%\n"
                    f"Profit Factor: {payload['metrics']['profit_factor_pct']}"
                ),
                "payload": payload,
            }

        except Exception as e:
            return {"ok": False, "error": str(e)}
    
    @app.route("/history/trades/analytics")
    def history_trades_analytics():
        try:
            import history_manager
            payload = history_manager.build_trade_record_analytics()

            s = payload.get("summary", {})

            return {
                "ok": True,
                "text": (
                    "📊 TRADE RECORD ANALYTICS — CENTRAL QUANT\n"
                    f"Data/hora: {payload.get('generated_at')}\n\n"
                    f"Trades analisados: {payload.get('count', 0)}\n\n"
                    "Resumo:\n"
                    f"- MFE médio: {s.get('mfe_avg_pct', 0)}%\n"
                    f"- MAE médio: {s.get('mae_avg_pct', 0)}%\n"
                    f"- Giveback médio: {s.get('giveback_avg_pct', 0)}%\n"
                    f"- TP50 hit rate: {s.get('tp50_hit_rate_pct', 0)}%"
                ),
                "payload": payload,
            }

        except Exception as e:
            return {"ok": False, "error": str(e)}
    
    @app.route("/analytics/bots")
    def analytics_bots():
        try:
            import analytics_engine

            payload = analytics_engine.bot_ranking()

            lines = [
                "🧠 ANALYTICS BOTS — CENTRAL QUANT",
                f"Data/hora: {payload.get('generated_at')}",
                "",
                "Ranking por robô:",
            ]

            for i, bot in enumerate(payload.get("bots", []), start=1):
                lines += [
                    "",
                    f"{i}. {bot.get('bot')}",
                    f"Score: {bot.get('score')}/100",
                    f"Recomendação: {bot.get('recommendation')}",
                    f"Trades: {bot.get('trades')}",
                    f"Win rate: {bot.get('win_rate_pct')}%",
                    f"PnL total: {bot.get('pnl_total_pct')}%",
                    f"TP50 hit rate: {bot.get('tp50_hit_rate_pct')}%",
                ]

            return {
                "ok": True,
                "text": "\n".join(lines),
                "payload": payload,
            }

        except Exception as e:
            return {
                "ok": False,
                "error": str(e),
            }
    
    @app.route("/history/trades/rebuild")
    def history_trades_rebuild():
        try:
            import history_manager
            payload = history_manager.rebuild_closed_trades_v4_from_events()

            return {
                "ok": payload.get("ok"),
                "text": (
                    "♻️ HISTORY TRADES REBUILD — CENTRAL QUANT\n"
                    f"Eventos fechados encontrados: {payload.get('closed_events', 0)}\n"
                    f"Registros criados: {payload.get('created', 0)}\n"
                    f"Erros: {payload.get('errors', 0)}\n"
                    f"Total no arquivo: {payload.get('records', 0)}"
                ),
                "payload": payload,
            }

        except Exception as e:
            return {"ok": False, "error": str(e)}
    
    @app.route("/history/raw")
    def super_history_raw_route():
        return super_history_manager.build_history_payload()

    print("SUPER HISTORY MANAGER carregado com sucesso")

except Exception as exc:
    print("ERRO AO CARREGAR SUPER HISTORY MANAGER:", exc)


# ==========================================================
# ADAPTIVE WEIGHT ENGINE V2 - CENTRAL QUANT
# ==========================================================

ADAPTIVE_WEIGHT_ENGINE_V2_VERSION = "2026-07-04-ADAPTIVE-WEIGHT-ENGINE-V2"
ADAPTIVE_WEIGHT_ENGINE_V2_MODE = "OBSERVATION_ONLY"
ADAPTIVE_WEIGHT_ENGINE_V2_FILE = CENTRAL_DATA_DIR / "adaptive_weight_engine_v2.json"
ADAPTIVE_WEIGHT_ENGINE_V2_CACHE = {"last_payload": None, "last_generated_at": None, "last_capital": None}

ADAPTIVE_WEIGHT_ENGINE_V2_MIN_OBSERVATIONS = int(os.environ.get("ADAPTIVE_WEIGHT_V2_MIN_OBSERVATIONS", os.environ.get("ADAPTIVE_WEIGHT_MIN_OBSERVATIONS", "10")))
ADAPTIVE_WEIGHT_ENGINE_V2_MAX_ADJUSTMENT_PCT = float(os.environ.get("ADAPTIVE_WEIGHT_V2_MAX_ADJUSTMENT_PCT", "22"))
ADAPTIVE_WEIGHT_ENGINE_V2_SINGLE_RUN_MAX_DELTA = float(os.environ.get("ADAPTIVE_WEIGHT_V2_SINGLE_RUN_MAX_DELTA", "4"))
ADAPTIVE_WEIGHT_ENGINE_V2_TOTAL_WEIGHT = sum(DECISION_SCORE_ENGINE_V1_WEIGHTS.values())

ADAPTIVE_WEIGHT_ENGINE_V2_MODULE_LIMITS = dict(ADAPTIVE_WEIGHT_ENGINE_V1_MODULE_LIMITS)


def _awe_v2_read_evaluations(limit=5000):
    records = []
    try:
        if OUTCOME_EVALUATOR_V1_FILE.exists():
            with open(OUTCOME_EVALUATOR_V1_FILE, "r", encoding="utf-8") as f:
                lines = f.readlines()[-int(limit or 5000):]
            for line in lines:
                try:
                    item = json.loads(line)
                except Exception:
                    continue
                if isinstance(item, dict) and item.get("record_type") == "OUTCOME_EVALUATION":
                    records.append(item)
    except Exception:
        pass
    return records


def _awe_v2_vote_structural_points(ev):
    vote = str((ev or {}).get("vote") or "").upper().strip()
    weight = _awe_safe_float((ev or {}).get("weight"), 0.0)
    if vote in {"ALLOW", "REDUCE", "DENY", "WAIT"}:
        return abs(weight * 100.0)
    if vote in {"INFO", "NEUTRAL"}:
        return abs(weight * 50.0)
    return abs(weight * 25.0)


def _awe_v2_module_stats_from_evaluations(records=None):
    records = records if records is not None else _awe_v2_read_evaluations()
    stats = {}
    for module in DECISION_SCORE_ENGINE_V1_WEIGHTS.keys():
        stats[module] = {
            "module": module,
            "observations": 0,
            "correct": 0,
            "wrong": 0,
            "neutral": 0,
            "accuracy_pct": None,
            "avg_influence_pct": 0.0,
            "avg_structural_influence_pct": 0.0,
            "influence_samples": 0,
            "structural_samples": 0,
        }

    for record in records or []:
        rows = record.get("module_evaluations") or []
        structural_total = 0.0
        for ev in rows:
            structural_total += _awe_v2_vote_structural_points(ev)

        for ev in rows:
            module = ev.get("module") or "UNKNOWN"
            if module not in stats:
                stats[module] = {
                    "module": module,
                    "observations": 0,
                    "correct": 0,
                    "wrong": 0,
                    "neutral": 0,
                    "accuracy_pct": None,
                    "avg_influence_pct": 0.0,
                    "avg_structural_influence_pct": 0.0,
                    "influence_samples": 0,
                    "structural_samples": 0,
                }
            correct = ev.get("correct")
            if correct is True:
                stats[module]["observations"] += 1
                stats[module]["correct"] += 1
            elif correct is False:
                stats[module]["observations"] += 1
                stats[module]["wrong"] += 1
            else:
                stats[module]["neutral"] += 1

            if ev.get("influence_pct") is not None:
                n = stats[module]["influence_samples"]
                old = stats[module]["avg_influence_pct"]
                val = _awe_safe_float(ev.get("influence_pct"), 0.0)
                stats[module]["avg_influence_pct"] = round(((old * n) + val) / (n + 1), 4)
                stats[module]["influence_samples"] = n + 1

            structural_points = _awe_v2_vote_structural_points(ev)
            structural_pct = (structural_points / structural_total * 100.0) if structural_total else 0.0
            n2 = stats[module]["structural_samples"]
            old2 = stats[module]["avg_structural_influence_pct"]
            stats[module]["avg_structural_influence_pct"] = round(((old2 * n2) + structural_pct) / (n2 + 1), 4)
            stats[module]["structural_samples"] = n2 + 1

    for module, item in stats.items():
        obs = int(item.get("observations") or 0)
        item["accuracy_pct"] = round((item.get("correct", 0) / obs) * 100.0, 2) if obs else None
    return stats


def _awe_v2_default_state():
    return {
        "version": ADAPTIVE_WEIGHT_ENGINE_V2_VERSION,
        "created_at": data_hora_sp_str(),
        "updated_at": data_hora_sp_str(),
        "mode": ADAPTIVE_WEIGHT_ENGINE_V2_MODE,
        "weights": dict(DECISION_SCORE_ENGINE_V1_WEIGHTS),
        "history": [],
        "notes": [
            "V2 usa outcomes avaliados pelo Outcome Evaluator V1.",
            "V2 corrige influência estrutural de votos DENY/WAIT, mesmo quando pontos=0.",
            "Ajustes ativos exigem amostra mínima por módulo para evitar overfitting.",
        ],
    }


def _awe_v2_load_state():
    try:
        if ADAPTIVE_WEIGHT_ENGINE_V2_FILE.exists():
            with open(ADAPTIVE_WEIGHT_ENGINE_V2_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                data.setdefault("weights", dict(DECISION_SCORE_ENGINE_V1_WEIGHTS))
                data.setdefault("history", [])
                return data
    except Exception:
        pass
    return _awe_v2_default_state()


def _awe_v2_save_state(state):
    try:
        state = dict(state or {})
        state["updated_at"] = data_hora_sp_str()
        ADAPTIVE_WEIGHT_ENGINE_V2_FILE.parent.mkdir(exist_ok=True)
        with open(ADAPTIVE_WEIGHT_ENGINE_V2_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        return True, None
    except Exception as exc:
        return False, str(exc)


def _awe_v2_normalize_weights(weights, total=ADAPTIVE_WEIGHT_ENGINE_V2_TOTAL_WEIGHT):
    weights = dict(weights or {})
    cur = sum(_awe_safe_float(x, 0.0) for x in weights.values()) or float(total or 1.0)
    factor = float(total or cur) / cur
    return {k: round(_awe_safe_float(v, 0.0) * factor, 4) for k, v in weights.items()}, round(factor, 6)


def _awe_v2_recommend_weights(state=None):
    state = state or _awe_v2_load_state()
    records = _awe_v2_read_evaluations()
    stats = _awe_v2_module_stats_from_evaluations(records)
    base_weights = dict(DECISION_SCORE_ENGINE_V1_WEIGHTS)
    current_weights = dict(state.get("weights") or base_weights)

    table = []
    active_pre = {}
    shadow_pre = {}
    active_adjustments = 0
    shadow_adjustments = 0

    for module, base_weight in base_weights.items():
        item = stats.get(module) or {}
        observations = int(item.get("observations") or 0)
        correct = int(item.get("correct") or 0)
        wrong = int(item.get("wrong") or 0)
        neutral = int(item.get("neutral") or 0)
        accuracy = item.get("accuracy_pct")
        accuracy_val = _awe_safe_float(accuracy, None)
        avg_influence = _awe_safe_float(item.get("avg_influence_pct"), 0.0)
        structural_influence = _awe_safe_float(item.get("avg_structural_influence_pct"), 0.0)
        confidence_factor = _awe_clip(observations / float(max(1, ADAPTIVE_WEIGHT_ENGINE_V2_MIN_OBSERVATIONS)), 0.0, 1.0)

        if accuracy_val is None:
            raw_adjustment = 0.0
        else:
            raw_adjustment = ((accuracy_val - 55.0) / 45.0) * ADAPTIVE_WEIGHT_ENGINE_V2_MAX_ADJUSTMENT_PCT
            # Módulos com alta influência estrutural e baixa acurácia sofrem penalização ligeiramente maior.
            if accuracy_val < 50.0 and structural_influence > 20.0:
                raw_adjustment -= min(6.0, (structural_influence - 20.0) * 0.2)
            # Módulos defensivos com alta acurácia e alta influência estrutural ganham um pouco mais.
            if accuracy_val >= 70.0 and structural_influence > 20.0:
                raw_adjustment += min(5.0, (structural_influence - 20.0) * 0.15)

        raw_adjustment = _awe_clip(raw_adjustment, -ADAPTIVE_WEIGHT_ENGINE_V2_MAX_ADJUSTMENT_PCT, ADAPTIVE_WEIGHT_ENGINE_V2_MAX_ADJUSTMENT_PCT)
        shadow_adjustment_pct = raw_adjustment * max(confidence_factor, 0.15 if observations > 0 else 0.0)
        active_adjustment_pct = raw_adjustment * confidence_factor if observations >= ADAPTIVE_WEIGHT_ENGINE_V2_MIN_OBSERVATIONS else 0.0

        # Limite de variação por ciclo para evitar oscilação brusca quando persist=true.
        active_adjustment_pct = _awe_clip(active_adjustment_pct, -ADAPTIVE_WEIGHT_ENGINE_V2_SINGLE_RUN_MAX_DELTA, ADAPTIVE_WEIGHT_ENGINE_V2_SINGLE_RUN_MAX_DELTA)
        shadow_adjustment_pct = _awe_clip(shadow_adjustment_pct, -ADAPTIVE_WEIGHT_ENGINE_V2_MAX_ADJUSTMENT_PCT, ADAPTIVE_WEIGHT_ENGINE_V2_MAX_ADJUSTMENT_PCT)

        limits = ADAPTIVE_WEIGHT_ENGINE_V2_MODULE_LIMITS.get(module, {"min": 1.0, "max": 50.0})
        active_raw = _awe_safe_float(current_weights.get(module), base_weight) * (1.0 + active_adjustment_pct / 100.0)
        shadow_raw = float(base_weight) * (1.0 + shadow_adjustment_pct / 100.0)
        active_bounded = _awe_clip(active_raw, limits.get("min", 1.0), limits.get("max", 50.0))
        shadow_bounded = _awe_clip(shadow_raw, limits.get("min", 1.0), limits.get("max", 50.0))

        if abs(active_bounded - _awe_safe_float(current_weights.get(module), base_weight)) > 0.001:
            active_adjustments += 1
        if abs(shadow_bounded - float(base_weight)) > 0.001:
            shadow_adjustments += 1

        active_pre[module] = active_bounded
        shadow_pre[module] = shadow_bounded
        evidence = "ACTIVE_ADAPTIVE" if observations >= ADAPTIVE_WEIGHT_ENGINE_V2_MIN_OBSERVATIONS else ("SHADOW_LEARNING_WAIT_SAMPLE" if observations > 0 else "BOOTSTRAP_NO_OUTCOMES")
        table.append({
            "module": module,
            "base_weight": round(float(base_weight), 4),
            "current_weight": round(_awe_safe_float(current_weights.get(module), base_weight), 4),
            "observations": observations,
            "correct": correct,
            "wrong": wrong,
            "neutral": neutral,
            "accuracy_pct": round(accuracy_val, 2) if accuracy_val is not None else None,
            "confidence_factor": round(confidence_factor, 4),
            "avg_influence_pct_v1": round(avg_influence, 4),
            "avg_structural_influence_pct": round(structural_influence, 4),
            "raw_adjustment_pct": round(raw_adjustment, 4),
            "active_adjustment_pct": round(active_adjustment_pct, 4),
            "shadow_adjustment_pct": round(shadow_adjustment_pct, 4),
            "active_weight_pre_normalization": round(active_bounded, 4),
            "shadow_weight_pre_normalization": round(shadow_bounded, 4),
            "limits": limits,
            "evidence": evidence,
        })

    active_weights, active_norm = _awe_v2_normalize_weights(active_pre)
    shadow_weights, shadow_norm = _awe_v2_normalize_weights(shadow_pre)
    for row in table:
        module = row["module"]
        row["active_weight"] = active_weights.get(module)
        row["shadow_weight"] = shadow_weights.get(module)
        row["delta_active_vs_base"] = round((active_weights.get(module) or row["base_weight"]) - row["base_weight"], 4)
        row["delta_shadow_vs_base"] = round((shadow_weights.get(module) or row["base_weight"]) - row["base_weight"], 4)

    return {
        "records": len(records),
        "module_stats": stats,
        "weight_table": table,
        "active_weights": active_weights,
        "shadow_weights": shadow_weights,
        "active_normalization_factor": active_norm,
        "shadow_normalization_factor": shadow_norm,
        "active_adjustments": active_adjustments,
        "shadow_adjustments": shadow_adjustments,
    }


def build_adaptive_weight_engine_v2(capital=10000.0, bot=None, symbol=None, side=None, entry=None, stop=None, setup=None, leverage=None, mode=None, intended_live=None, persist=False):
    global ADAPTIVE_WEIGHT_ENGINE_V2_CACHE
    capital = _awe_safe_float(capital, 10000.0)
    state = _awe_v2_load_state()
    recommendation = _awe_v2_recommend_weights(state)
    active_weights = recommendation.get("active_weights") or dict(DECISION_SCORE_ENGINE_V1_WEIGHTS)
    shadow_weights = recommendation.get("shadow_weights") or dict(DECISION_SCORE_ENGINE_V1_WEIGHTS)

    decision_payload = build_decision_score_engine_v1(
        capital=capital,
        bot=bot,
        symbol=symbol,
        side=side,
        entry=entry,
        stop=stop,
        setup=setup,
        leverage=leverage,
        mode=mode,
        intended_live=intended_live,
    )

    active_score, active_weighted_points, active_total_weight, active_module_scores = _awe_score_with_weights(decision_payload, active_weights)
    shadow_score, shadow_weighted_points, shadow_total_weight, shadow_module_scores = _awe_score_with_weights(decision_payload, shadow_weights)

    sizing = decision_payload.get("sizing") or {}
    hard_deny = bool(decision_payload.get("hard_deny"))
    hard_wait = bool(decision_payload.get("hard_wait"))
    active_decision = _dse_decision_from_score(active_score, hard_deny=hard_deny, hard_wait=hard_wait, sizing_action=sizing.get("sizing_action"))
    shadow_decision = _dse_decision_from_score(shadow_score, hard_deny=hard_deny, hard_wait=hard_wait, sizing_action=sizing.get("sizing_action"))

    action_map = {
        "ALLOW": "ALLOW_ADAPTIVE_V2_OBSERVATION",
        "REDUCE": "ALLOW_REDUCED_ADAPTIVE_V2_OBSERVATION",
        "WAIT": "WAIT_ADAPTIVE_V2_OBSERVATION",
        "DENY": "DENY_ADAPTIVE_V2_OBSERVATION",
    }
    active_action = action_map.get(active_decision, "WAIT_ADAPTIVE_V2_OBSERVATION")
    active_confidence = _dse_confidence(active_score, decision_payload.get("votes") or [], hard_deny=hard_deny)

    enough_modules = [x for x in recommendation.get("weight_table") or [] if int(x.get("observations") or 0) >= ADAPTIVE_WEIGHT_ENGINE_V2_MIN_OBSERVATIONS]
    evidence_quality = "ACTIVE_ADAPTIVE" if enough_modules else ("SHADOW_LEARNING_WAIT_SAMPLE" if recommendation.get("records") else "BOOTSTRAP_NO_OUTCOMES")

    save_ok = False
    save_error = None
    if persist:
        state["weights"] = active_weights
        hist = list(state.get("history") or [])
        hist.append({
            "ts": data_hora_sp_str(),
            "records": recommendation.get("records"),
            "evidence_quality": evidence_quality,
            "active_weights": active_weights,
            "shadow_weights": shadow_weights,
            "active_score": active_score,
            "shadow_score": shadow_score,
        })
        state["history"] = hist[-200:]
        save_ok, save_error = _awe_v2_save_state(state)

    reasons = []
    if evidence_quality == "BOOTSTRAP_NO_OUTCOMES":
        reasons.append("Ainda não há outcomes avaliados; V2 mantém pesos base.")
    elif evidence_quality == "SHADOW_LEARNING_WAIT_SAMPLE":
        reasons.append("Há outcomes avaliados, mas ainda não há amostra mínima; V2 mostra pesos sombra sem alterar pesos ativos.")
    else:
        reasons.append("Há amostra mínima em ao menos um módulo; V2 aplica ajustes ativos com limite de variação.")
    if hard_deny:
        reasons.append("Hard deny permanece soberano: pesos adaptativos não podem liberar trade vetado por regra crítica.")
    if recommendation.get("shadow_adjustments"):
        reasons.append(f"{recommendation.get('shadow_adjustments')} módulo(s) já possuem ajuste sombra sugerido.")
    if recommendation.get("active_adjustments"):
        reasons.append(f"{recommendation.get('active_adjustments')} módulo(s) possuem ajuste ativo aplicado.")
    else:
        reasons.append("Nenhum ajuste ativo aplicado nesta leitura.")

    alerts = list(decision_payload.get("alerts") or [])
    if evidence_quality == "SHADOW_LEARNING_WAIT_SAMPLE":
        alerts.append("Adaptive Weight V2 está em modo sombra: já calcula tendência, mas não altera pesos ativos sem amostra mínima.")
    if evidence_quality == "ACTIVE_ADAPTIVE":
        alerts.append("Adaptive Weight V2 aplicou pesos ativos baseados em outcomes suficientes.")
    if hard_deny:
        alerts.append("Hard deny ativo; decisão final continua protegida por regra crítica.")

    payload = {
        "ok": True,
        "version": ADAPTIVE_WEIGHT_ENGINE_V2_VERSION,
        "generated_at": data_hora_sp_str(),
        "mode": ADAPTIVE_WEIGHT_ENGINE_V2_MODE,
        "capital": capital,
        "inputs": decision_payload.get("inputs") or {},
        "evidence_quality": evidence_quality,
        "outcome_evaluations_detected": recommendation.get("records"),
        "min_observations_required": ADAPTIVE_WEIGHT_ENGINE_V2_MIN_OBSERVATIONS,
        "base_decision_score_version": decision_payload.get("version"),
        "base_decision_score": decision_payload.get("decision_score"),
        "base_decision": decision_payload.get("decision"),
        "base_confidence": decision_payload.get("confidence_score"),
        "active_decision_score": active_score,
        "active_decision": active_decision,
        "active_execution_action": active_action,
        "active_confidence_score": active_confidence,
        "shadow_decision_score": shadow_score,
        "shadow_decision": shadow_decision,
        "hard_deny": hard_deny,
        "hard_wait": hard_wait,
        "active_weights": active_weights,
        "shadow_weights": shadow_weights,
        "weight_table": recommendation.get("weight_table") or [],
        "active_module_scores": active_module_scores,
        "shadow_module_scores": shadow_module_scores,
        "active_weight_total": active_total_weight,
        "shadow_weight_total": shadow_total_weight,
        "active_weighted_points": active_weighted_points,
        "shadow_weighted_points": shadow_weighted_points,
        "active_adjustments": recommendation.get("active_adjustments"),
        "shadow_adjustments": recommendation.get("shadow_adjustments"),
        "recommended_order": decision_payload.get("recommended_order") or {},
        "sizing": sizing,
        "risk_manager": decision_payload.get("risk_manager") or {},
        "capital_allocator": decision_payload.get("capital_allocator") or {},
        "alerts": alerts,
        "reasons": reasons,
        "notes": [
            "Adaptive Weight Engine V2 está em modo consultivo/observação.",
            "V2 usa outcomes avaliados pelo Outcome Evaluator V1 para medir acerto/erro por módulo.",
            "V2 adiciona influência estrutural para capturar o impacto de votos DENY/WAIT mesmo quando pontos=0.",
            "Sem amostra mínima, os pesos ativos permanecem conservadores e os ajustes aparecem como shadow weights.",
            "Com amostra suficiente, V2 aplica ajustes ativos com limites por módulo e limite de variação por ciclo.",
        ],
        "state_saved": save_ok,
        "state_save_error": save_error,
    }
    ADAPTIVE_WEIGHT_ENGINE_V2_CACHE = {"last_generated_at": payload.get("generated_at"), "last_capital": capital, "last_decision": payload.get("active_decision")}
    return payload


def build_adaptive_weight_engine_v2_text(capital=10000.0, bot=None, symbol=None, side=None, entry=None, stop=None, setup=None, leverage=None, mode=None, intended_live=None, persist=False):
    payload = build_adaptive_weight_engine_v2(capital=capital, bot=bot, symbol=symbol, side=side, entry=entry, stop=stop, setup=setup, leverage=leverage, mode=mode, intended_live=intended_live, persist=persist)
    order = payload.get("recommended_order") or {}
    sizing = payload.get("sizing") or {}
    lines = [
        "⚖️ ADAPTIVE WEIGHT ENGINE V2 — CENTRAL QUANT",
        f"Data/hora: {payload.get('generated_at')}",
        f"Versão: {payload.get('version')}",
        f"Modo: {payload.get('mode')}",
        "",
        "Trade avaliado:",
        f"Bot: {(payload.get('inputs') or {}).get('bot')} | Setup: {(payload.get('inputs') or {}).get('setup')}",
        f"Ativo: {(payload.get('inputs') or {}).get('symbol')} | Side: {(payload.get('inputs') or {}).get('side')}",
        f"Entrada: {(payload.get('inputs') or {}).get('entry')} | Stop: {(payload.get('inputs') or {}).get('stop')} | Leverage: {(payload.get('inputs') or {}).get('leverage')}x",
        "",
        "Resultado adaptativo V2:",
        f"Base Decision Score: {payload.get('base_decision_score')}/100 | Decisão base: {payload.get('base_decision')} | Confiança base: {payload.get('base_confidence')}/100",
        f"Active Score: {payload.get('active_decision_score')}/100 | Decisão ativa: {payload.get('active_decision')} | Action: {payload.get('active_execution_action')}",
        f"Shadow Score: {payload.get('shadow_decision_score')}/100 | Decisão sombra: {payload.get('shadow_decision')}",
        f"Hard deny: {payload.get('hard_deny')} | Evidência: {payload.get('evidence_quality')}",
        f"Outcomes avaliados: {payload.get('outcome_evaluations_detected')} | Mínimo por módulo: {payload.get('min_observations_required')}",
        "",
        "Ordem sugerida:",
        f"Paper notional: {order.get('paper_notional_usdt')} USDT | Margem: {order.get('paper_margin_usdt')} USDT | Qty: {order.get('paper_qty')}",
        f"Risco efetivo: {order.get('paper_effective_risk_usdt')} USDT ({order.get('paper_effective_risk_pct')}%)",
        "",
        "Sizing:",
        f"Prioridade estratégica: {sizing.get('strategic_priority')} | Executável: {sizing.get('executable_size_state')}",
        f"Limitador dominante: {(sizing.get('binding_limit') or {}).get('name')} ({(sizing.get('binding_limit') or {}).get('value_usdt')} USDT)",
        f"Uso do risk per trade: {sizing.get('risk_budget_utilization_pct')}%",
        "",
        "Pesos por módulo:",
    ]
    for item in payload.get("weight_table") or []:
        lines.append(
            f"- {item.get('module')}: base {item.get('base_weight')} → ativo {item.get('active_weight')} (Δ {item.get('delta_active_vs_base')}) | sombra {item.get('shadow_weight')} (Δ {item.get('delta_shadow_vs_base')}) | obs={item.get('observations')} | acc={item.get('accuracy_pct')}% | influência estrutural={item.get('avg_structural_influence_pct')}% | {item.get('evidence')}"
        )
    lines += [
        "",
        "Alertas:",
    ]
    for alert in payload.get("alerts") or []:
        lines.append(f"- {alert}")
    lines += [
        "",
        "Motivos principais:",
    ]
    for reason in payload.get("reasons") or []:
        lines.append(f"- {reason}")
    lines += [
        "",
        "Notas:",
    ]
    for note in payload.get("notes") or []:
        lines.append(f"- {note}")
    return "\n".join(lines), payload


@app.route("/adaptive/weights/v2", methods=["GET", "POST"])
@app.route("/adaptive-weight/v2", methods=["GET", "POST"])
@app.route("/weights/adaptive/v2", methods=["GET", "POST"])
def adaptive_weight_engine_v2_route():
    body = request.get_json(silent=True) or {}
    args_payload = _dse_request_payload_from_args(body)
    capital = _awe_safe_float(args_payload.get("capital"), 10000.0)
    persist = str(args_payload.get("persist") or request.args.get("persist", "")).strip().lower() in {"1", "true", "yes", "sim", "on", "save"}
    text, payload = build_adaptive_weight_engine_v2_text(capital=capital, bot=args_payload.get("bot"), symbol=args_payload.get("symbol"), side=args_payload.get("side"), entry=args_payload.get("entry"), stop=args_payload.get("stop"), setup=args_payload.get("setup"), leverage=args_payload.get("leverage"), mode=args_payload.get("mode"), intended_live=args_payload.get("intended_live"), persist=persist)
    return {"ok": True, "payload": payload, "text": text}


@app.route("/adaptive/weights/summary/v2", methods=["GET", "POST"])
@app.route("/adaptive-weight/summary/v2", methods=["GET", "POST"])
@app.route("/weights/adaptive/summary/v2", methods=["GET", "POST"])
def adaptive_weight_engine_v2_summary_route():
    body = request.get_json(silent=True) or {}
    args_payload = _dse_request_payload_from_args(body)
    capital = _awe_safe_float(args_payload.get("capital"), 10000.0)
    payload = build_adaptive_weight_engine_v2(capital=capital, bot=args_payload.get("bot"), symbol=args_payload.get("symbol"), side=args_payload.get("side"), entry=args_payload.get("entry"), stop=args_payload.get("stop"), setup=args_payload.get("setup"), leverage=args_payload.get("leverage"), mode=args_payload.get("mode"), intended_live=args_payload.get("intended_live"), persist=False)
    return {
        "ok": True,
        "version": payload.get("version"),
        "generated_at": payload.get("generated_at"),
        "mode": payload.get("mode"),
        "evidence_quality": payload.get("evidence_quality"),
        "outcome_evaluations_detected": payload.get("outcome_evaluations_detected"),
        "min_observations_required": payload.get("min_observations_required"),
        "base_decision_score": payload.get("base_decision_score"),
        "active_decision_score": payload.get("active_decision_score"),
        "active_decision": payload.get("active_decision"),
        "shadow_decision_score": payload.get("shadow_decision_score"),
        "shadow_decision": payload.get("shadow_decision"),
        "hard_deny": payload.get("hard_deny"),
        "active_weights": payload.get("active_weights"),
        "shadow_weights": payload.get("shadow_weights"),
        "weight_table": payload.get("weight_table"),
        "reasons": payload.get("reasons"),
        "alerts": payload.get("alerts"),
    }


# ============================================================
# META STRATEGY ENGINE V1.1 — CENTRAL QUANT
# Versão: 2026-07-04-META-STRATEGY-ENGINE-V1.1
# Objetivo:
# - Orquestrar robôs/estratégias de forma autônoma e machine-first.
# - Corrige V1: consome corretamente Portfolio Advisor, Portfolio Optimizer e Dynamic Risk Budget.
# - Classifica robôs em PRIMARY, SECONDARY, WAIT/REDUCE e DEFENSIVE.
# - Não é relatório para usuário final; é política interna para Decision/Execution Engines.
# ============================================================

META_STRATEGY_ENGINE_V11_VERSION = "2026-07-04-META-STRATEGY-ENGINE-V1.1"
META_STRATEGY_ENGINE_V11_MODE = "OBSERVATION_ONLY"
META_STRATEGY_ENGINE_V11_CACHE = {"last_generated_at": None, "last_regime": None, "last_primary_strategy": None}


def _mse_safe_float(value, default=0.0):
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _mse_safe_upper(value, default="UNKNOWN"):
    if value is None:
        return default
    s = str(value).strip().upper()
    return s if s else default


def _mse_clamp(value, lo, hi):
    value = _mse_safe_float(value, lo)
    return max(lo, min(hi, value))


def _mse_strategy_family(bot, category=None):
    b = _mse_safe_upper(bot)
    mapping = {
        "DONKEY": "TREND_CONTINUATION",
        "TRENDPRO": "TREND_FOLLOWING",
        "TURTLE": "BREAKOUT_TREND",
        "FALCON": "OPENING_RANGE_BREAKOUT",
        "COBRA": "REVERSAL_TACTICAL",
        "PREDATOR": "SMART_MOMENTUM",
        "MEME": "EXPERIMENTAL_MOMENTUM",
    }
    if b in mapping:
        return mapping[b]
    c = _mse_safe_upper(category)
    if c == "EXPERIMENTAL":
        return "EXPERIMENTAL"
    if c == "TACTICAL":
        return "TACTICAL"
    if c == "SATELLITE":
        return "SATELLITE"
    return "CORE_STRATEGY"


def _mse_strategy_cluster(family):
    f = _mse_safe_upper(family)
    if "TREND" in f:
        return "TREND"
    if "BREAKOUT" in f or "RANGE" in f:
        return "BREAKOUT"
    if "REVERSAL" in f:
        return "REVERSAL"
    if "MOMENTUM" in f:
        return "MOMENTUM"
    if "EXPERIMENTAL" in f:
        return "EXPERIMENTAL"
    return "OTHER"


def _mse_infer_market_context(exposure_summary=None, explicit_regime=None):
    exposure_summary = exposure_summary or {}
    explicit = _mse_safe_upper(explicit_regime, "")
    long_count = int(_mse_safe_float(exposure_summary.get("long"), 0))
    short_count = int(_mse_safe_float(exposure_summary.get("short"), 0))
    positions = int(_mse_safe_float(exposure_summary.get("positions"), 0))
    net_direction = _mse_safe_upper(exposure_summary.get("net_direction"), "FLAT")
    long_pct = round((long_count / positions * 100.0), 2) if positions else 0.0
    short_pct = round((short_count / positions * 100.0), 2) if positions else 0.0

    if explicit and explicit not in {"NONE", "UNKNOWN", "AUTO"}:
        regime = explicit
        source = "EXPLICIT_INPUT"
    elif positions >= 10 and net_direction == "LONG" and long_pct >= 70:
        regime = "DIRECTIONAL_LONG_EXPOSURE"
        source = "EXPOSURE_PROXY"
    elif positions >= 10 and net_direction == "SHORT" and short_pct >= 70:
        regime = "DIRECTIONAL_SHORT_EXPOSURE"
        source = "EXPOSURE_PROXY"
    elif positions >= 15:
        regime = "HIGH_PORTFOLIO_ACTIVITY"
        source = "EXPOSURE_PROXY"
    elif positions <= 3:
        regime = "LOW_ACTIVITY_WAIT_SAMPLE"
        source = "EXPOSURE_PROXY"
    else:
        regime = "BALANCED_OR_UNCLEAR"
        source = "EXPOSURE_PROXY"

    return {
        "regime": regime,
        "source": source,
        "positions": positions,
        "long": long_count,
        "short": short_count,
        "net_direction": net_direction,
        "long_pct": long_pct,
        "short_pct": short_pct,
        "notes": [
            "Market Regime Detector ainda não está ativo; regime é inferido por exposição e contexto interno.",
            "Meta Strategy V1.1 usa esse proxy apenas para orquestrar compressão/prioridade até existir regime real.",
        ],
    }


def _mse_extract_advisor_item(advisor_payload, bot):
    wanted = _mse_safe_upper(bot)
    for item in (advisor_payload or {}).get("ranking") or []:
        if _mse_safe_upper(item.get("bot")) == wanted:
            return item or {}
    return {}


def _mse_extract_optimized_allocations(optimizer_payload):
    return (optimizer_payload or {}).get("optimized_allocation") or (optimizer_payload or {}).get("allocations") or (optimizer_payload or {}).get("current_vs_target") or []


def _mse_extract_exposure_summary(advisor_payload=None, optimizer_payload=None, risk_budget_payload=None):
    advisor_payload = advisor_payload or {}
    optimizer_payload = optimizer_payload or {}
    risk_budget_payload = risk_budget_payload or {}
    return (
        ((advisor_payload.get("summary") or {}).get("exposure_summary") or {})
        or (((optimizer_payload.get("summary") or {}).get("advisor_summary") or {}).get("exposure_summary") or {})
        or ((risk_budget_payload.get("summary") or {}).get("exposure_summary") or {})
    )


def _mse_policy_from_stack(advisor_action, optimizer_recommendation, new_trade_policy, score, risk_state, category, regime_context):
    advisor_action = _mse_safe_upper(advisor_action)
    optimizer_recommendation = _mse_safe_upper(optimizer_recommendation)
    new_trade_policy = _mse_safe_upper(new_trade_policy)
    risk_state = _mse_safe_upper(risk_state)
    category = _mse_safe_upper(category)
    regime = _mse_safe_upper((regime_context or {}).get("regime"))
    score = _mse_safe_float(score, 0.0)

    action = "HOLD_WAIT"
    signal_gate = "WAIT_SIGNAL"
    risk_multiplier = 0.50
    sizing_multiplier = 0.50
    priority = "LOW"
    autonomy_gate = "REQUIRES_STRONG_CONFIRMATION"
    reasons = []

    paused = advisor_action == "PAUSE_OR_REVIEW" or "PAUSE" in new_trade_policy or str(optimizer_recommendation).startswith("DEFUND")
    wait_reduce = advisor_action == "REDUCE_OR_WAIT" or "REDUCE" in new_trade_policy or str(optimizer_recommendation).startswith("HOLD")
    experimental = category == "EXPERIMENTAL" or advisor_action == "MAINTAIN_EXPERIMENTAL_SMALL"
    prioritized = advisor_action == "PRIORITIZE" or risk_state == "PRIORITY" or str(optimizer_recommendation).startswith("INCREASE")

    if paused:
        action = "DEFENSIVE_STRATEGY"
        signal_gate = "BLOCK_NEW_SIGNALS"
        risk_multiplier = 0.0
        sizing_multiplier = 0.0
        priority = "DEFENSIVE"
        autonomy_gate = "DO_NOT_OPEN_NEW_TRADES"
        reasons.append("Advisor/Optimizer indicam pausa, revisão ou defund; bloquear novo risco.")
    elif prioritized and score >= 75 and risk_state == "PRIORITY":
        action = "PRIMARY_STRATEGY"
        signal_gate = "ALLOW_FILTERED_SIGNALS"
        risk_multiplier = 1.00
        sizing_multiplier = 1.00
        priority = "HIGH"
        autonomy_gate = "ELIGIBLE_FOR_DECISION_ENGINE"
        reasons.append("Robô priorizado pelo Advisor/Optimizer e com Risk Budget PRIORITY.")
    elif experimental and score >= 55:
        action = "SECONDARY_EXPERIMENTAL_STRATEGY"
        signal_gate = "ALLOW_SMALL_FILTERED_SIGNALS"
        risk_multiplier = 0.30
        sizing_multiplier = 0.30
        priority = "MEDIUM"
        autonomy_gate = "ELIGIBLE_FOR_DECISION_ENGINE_SMALL_SIZE"
        reasons.append("Estratégia experimental com score aceitável; permitir apenas lote pequeno e filtrado.")
    elif wait_reduce:
        action = "WAIT_OR_REDUCE_STRATEGY"
        signal_gate = "REDUCE_OR_WAIT_SIGNALS"
        risk_multiplier = 0.20
        sizing_multiplier = 0.20
        priority = "LOW"
        autonomy_gate = "REQUIRES_STRONG_CONFIRMATION"
        reasons.append("Advisor/Optimizer recomendam reduzir ou aguardar; novas entradas exigem confirmação forte.")
    elif score >= 60:
        action = "SECONDARY_STRATEGY"
        signal_gate = "ALLOW_FILTERED_SIGNALS"
        risk_multiplier = 0.45
        sizing_multiplier = 0.45
        priority = "MEDIUM"
        autonomy_gate = "ELIGIBLE_FOR_DECISION_ENGINE"
        reasons.append("Score intermediário/positivo; estratégia secundária, sem expansão agressiva.")
    else:
        action = "WAIT_OR_REDUCE_STRATEGY"
        signal_gate = "WAIT_SIGNAL"
        risk_multiplier = 0.15
        sizing_multiplier = 0.15
        priority = "LOW"
        autonomy_gate = "REQUIRES_STRONG_CONFIRMATION"
        reasons.append("Score fraco ou dados insuficientes; aguardar nova amostra.")

    if experimental:
        risk_multiplier = min(risk_multiplier, 0.30)
        sizing_multiplier = min(sizing_multiplier, 0.30)
        reasons.append("Categoria experimental mantém teto conservador automático.")

    if regime in {"DIRECTIONAL_LONG_EXPOSURE", "DIRECTIONAL_SHORT_EXPOSURE"}:
        if action == "PRIMARY_STRATEGY":
            signal_gate = "ALLOW_ONLY_IF_REDUCES_CONCENTRATION_OR_HIGH_QUALITY"
            sizing_multiplier = min(sizing_multiplier, 0.75)
            reasons.append("Carteira já está direcional; estratégia primária deve reduzir concentração ou ter qualidade alta.")
        elif action in {"SECONDARY_STRATEGY", "SECONDARY_EXPERIMENTAL_STRATEGY", "WAIT_OR_REDUCE_STRATEGY"}:
            risk_multiplier = min(risk_multiplier, 0.20)
            sizing_multiplier = min(sizing_multiplier, 0.20)
            reasons.append("Carteira direcional; estratégias não primárias ficam comprimidas.")

    return {
        "orchestration_action": action,
        "signal_gate": signal_gate,
        "autonomy_gate": autonomy_gate,
        "risk_multiplier": round(risk_multiplier, 4),
        "sizing_multiplier": round(sizing_multiplier, 4),
        "priority": priority,
        "reasons": reasons,
    }


def build_meta_strategy_engine_v1_1(capital=10000.0, market_regime=None, persist=False):
    capital = _mse_safe_float(capital, 10000.0)
    generated_at = data_hora_sp_str() if "data_hora_sp_str" in globals() else None
    alerts = []
    notes = [
        "Meta Strategy Engine V1.1 é uma camada autônoma/machine-first, não um relatório para usuário final.",
        "Correção V1.1: consome ranking do Advisor, optimized_allocation do Optimizer e budgets do Risk Budget.",
        "Não executa ordens, não altera lotes e não muda risco real; apenas orquestra políticas para Decision/Execution Engines.",
        "Market Regime Detector ainda não está ativo; regime é inferido por proxies internos até o módulo dedicado existir.",
    ]

    try:
        advisor = build_portfolio_advisor_v1(capital=capital) if "build_portfolio_advisor_v1" in globals() else {"ranking": [], "summary": {}}
    except Exception as exc:
        advisor = {"ok": False, "error": str(exc), "ranking": [], "summary": {}}
        alerts.append(f"Advisor indisponível para Meta Strategy: {exc}")

    try:
        optimizer = build_portfolio_optimizer_v1_1(capital=capital) if "build_portfolio_optimizer_v1_1" in globals() else {"optimized_allocation": [], "summary": {}}
    except Exception as exc:
        optimizer = {"ok": False, "error": str(exc), "optimized_allocation": [], "summary": {}}
        alerts.append(f"Optimizer indisponível para Meta Strategy: {exc}")

    try:
        risk_budget = build_dynamic_risk_budget_v1(capital=capital) if "build_dynamic_risk_budget_v1" in globals() else {"budgets": [], "summary": {}}
    except Exception as exc:
        risk_budget = {"ok": False, "error": str(exc), "budgets": [], "summary": {}}
        alerts.append(f"Risk Budget indisponível para Meta Strategy: {exc}")

    try:
        adaptive = build_adaptive_weight_engine_v2(capital=capital, persist=False) if "build_adaptive_weight_engine_v2" in globals() else {}
    except Exception as exc:
        adaptive = {"ok": False, "error": str(exc)}
        alerts.append(f"Adaptive Weight indisponível para Meta Strategy: {exc}")

    ranking = (advisor or {}).get("ranking") or []
    optimized = _mse_extract_optimized_allocations(optimizer)
    budgets = (risk_budget or {}).get("budgets") or []
    exposure_summary = _mse_extract_exposure_summary(advisor, optimizer, risk_budget)
    context = _mse_infer_market_context(exposure_summary, explicit_regime=market_regime)

    advisor_by_bot = {_mse_safe_upper(x.get("bot")): x for x in ranking if isinstance(x, dict)}
    allocation_by_bot = {_mse_safe_upper(x.get("bot")): x for x in optimized if isinstance(x, dict)}
    budget_by_bot = {_mse_safe_upper(x.get("bot")): x for x in budgets if isinstance(x, dict)}

    all_bots = []
    seen = set()
    for source in (optimized, ranking, budgets):
        for item in source or []:
            b = _mse_safe_upper((item or {}).get("bot"), "")
            if b and b not in seen:
                seen.add(b)
                all_bots.append(b)

    strategies = []
    cluster_summary = {}
    counts = {
        "primary": 0,
        "secondary": 0,
        "wait_reduce": 0,
        "disabled": 0,
        "eligible_for_decision_engine": 0,
        "total": 0,
    }

    for bot in all_bots:
        advisor_item = advisor_by_bot.get(bot) or {}
        allocation = allocation_by_bot.get(bot) or {}
        budget = budget_by_bot.get(bot) or {}

        advisor_obj = advisor_item.get("advisor") or {}
        advisor_action = allocation.get("advisor_action") or advisor_obj.get("action") or budget.get("advisor_action")
        optimizer_recommendation = allocation.get("recommendation") or budget.get("optimizer_recommendation")
        new_trade_policy = allocation.get("new_trade_policy") or advisor_obj.get("suggested_new_trade_policy") or budget.get("new_trade_policy")
        category = allocation.get("category") or advisor_item.get("category") or budget.get("category") or "UNKNOWN"
        score = _mse_safe_float(allocation.get("score", advisor_item.get("score", budget.get("score", 0.0))), 0.0)
        risk_state = budget.get("risk_state") or "UNKNOWN"
        target_pct = _mse_safe_float(allocation.get("target_pct", budget.get("target_pct", 0.0)), 0.0)
        current_pct = _mse_safe_float(allocation.get("current_pct", budget.get("current_pct", 0.0)), 0.0)
        delta_pct = _mse_safe_float(allocation.get("delta_pct", budget.get("delta_pct", target_pct - current_pct)), 0.0)
        risk_budget_pct = _mse_safe_float(budget.get("risk_budget_pct"), 0.0)
        risk_per_trade_pct = _mse_safe_float(budget.get("risk_per_trade_pct"), 0.0)
        positions = int(_mse_safe_float(advisor_item.get("positions"), 0))
        net_direction = advisor_item.get("net_direction") or "FLAT"
        family = _mse_strategy_family(bot, category)
        cluster = _mse_strategy_cluster(family)
        policy = _mse_policy_from_stack(
            advisor_action=advisor_action,
            optimizer_recommendation=optimizer_recommendation,
            new_trade_policy=new_trade_policy,
            score=score,
            risk_state=risk_state,
            category=category,
            regime_context=context,
        )

        priority_score = (
            score * 0.42
            + target_pct * 0.20
            + risk_budget_pct * 7.5
            + max(delta_pct, 0.0) * 0.35
        )
        if policy.get("orchestration_action") == "PRIMARY_STRATEGY":
            priority_score += 25
        elif policy.get("orchestration_action") in {"SECONDARY_STRATEGY", "SECONDARY_EXPERIMENTAL_STRATEGY"}:
            priority_score += 10
        elif policy.get("orchestration_action") == "DEFENSIVE_STRATEGY":
            priority_score -= 35
        if risk_state == "PRIORITY":
            priority_score += 12
        if _mse_safe_upper(category) == "EXPERIMENTAL":
            priority_score -= 5
        priority_score = round(_mse_clamp(priority_score, 0, 100), 2)

        action = policy.get("orchestration_action")
        if action == "PRIMARY_STRATEGY":
            counts["primary"] += 1
        elif action in {"SECONDARY_STRATEGY", "SECONDARY_EXPERIMENTAL_STRATEGY"}:
            counts["secondary"] += 1
        elif action == "WAIT_OR_REDUCE_STRATEGY":
            counts["wait_reduce"] += 1
        elif action == "DEFENSIVE_STRATEGY":
            counts["disabled"] += 1
        if str(policy.get("autonomy_gate") or "").startswith("ELIGIBLE"):
            counts["eligible_for_decision_engine"] += 1

        item = {
            "bot": bot,
            "category": category,
            "strategy_family": family,
            "strategy_cluster": cluster,
            "score": round(score, 2),
            "positions": positions,
            "net_direction": net_direction,
            "advisor_action": advisor_action,
            "optimizer_recommendation": optimizer_recommendation,
            "new_trade_policy": new_trade_policy,
            "risk_state": risk_state,
            "target_pct": round(target_pct, 4),
            "current_pct": round(current_pct, 4),
            "delta_pct": round(delta_pct, 4),
            "risk_budget_pct": round(risk_budget_pct, 4),
            "risk_per_trade_pct": round(risk_per_trade_pct, 4),
            "autonomous_priority_score": priority_score,
            "orchestration_action": action,
            "signal_gate": policy.get("signal_gate"),
            "autonomy_gate": policy.get("autonomy_gate"),
            "risk_multiplier": policy.get("risk_multiplier"),
            "sizing_multiplier": policy.get("sizing_multiplier"),
            "priority": policy.get("priority"),
            "reasons": policy.get("reasons") or [],
        }
        strategies.append(item)
        cluster_summary.setdefault(cluster, {"bots": 0, "target_pct": 0.0, "risk_budget_pct": 0.0, "avg_score_sum": 0.0, "primary": 0, "secondary": 0, "disabled": 0})
        cluster_summary[cluster]["bots"] += 1
        cluster_summary[cluster]["target_pct"] += target_pct
        cluster_summary[cluster]["risk_budget_pct"] += risk_budget_pct
        cluster_summary[cluster]["avg_score_sum"] += score
        if action == "PRIMARY_STRATEGY":
            cluster_summary[cluster]["primary"] += 1
        if action in {"SECONDARY_STRATEGY", "SECONDARY_EXPERIMENTAL_STRATEGY"}:
            cluster_summary[cluster]["secondary"] += 1
        if action == "DEFENSIVE_STRATEGY":
            cluster_summary[cluster]["disabled"] += 1

    counts["total"] = len(strategies)
    strategies.sort(key=lambda x: (x.get("autonomous_priority_score", 0), x.get("score", 0), x.get("target_pct", 0)), reverse=True)

    for cluster, data in list(cluster_summary.items()):
        bots_n = max(1, int(data.get("bots") or 0))
        data["target_pct"] = round(data.get("target_pct", 0.0), 4)
        data["risk_budget_pct"] = round(data.get("risk_budget_pct", 0.0), 4)
        data["avg_score"] = round(data.get("avg_score_sum", 0.0) / bots_n, 2)
        data.pop("avg_score_sum", None)

    primary_candidates = [x for x in strategies if x.get("orchestration_action") == "PRIMARY_STRATEGY"]
    primary = primary_candidates[0] if primary_candidates else (strategies[0] if strategies else None)
    primary_strategy = primary.get("bot") if primary and primary.get("orchestration_action") == "PRIMARY_STRATEGY" else None
    portfolio_state = (advisor or {}).get("portfolio_state") or ((optimizer or {}).get("summary") or {}).get("portfolio_state")

    if context.get("regime") in {"DIRECTIONAL_LONG_EXPOSURE", "DIRECTIONAL_SHORT_EXPOSURE"}:
        alerts.append("Carteira já está em exposição direcional; Meta Strategy comprime novas entradas que aumentem concentração.")
    if counts.get("disabled", 0) > 0:
        alerts.append(f"{counts.get('disabled')} estratégia(s)/robô(s) em modo defensivo/bloqueado para novo risco.")
    if counts.get("primary", 0) == 0:
        alerts.append("Nenhuma estratégia primária encontrada; Central opera em modo defensivo/aguardar amostra.")
    if counts.get("primary", 0) == 1:
        alerts.append(f"Estratégia primária atual: {primary_strategy}.")
    if len(strategies) == 0:
        alerts.append("Meta Strategy não recebeu robôs do Advisor/Optimizer/Risk Budget; verificar integração upstream.")

    automation_policy = {
        "autonomous_mode_ready": counts.get("eligible_for_decision_engine", 0) > 0,
        "primary_strategy": primary_strategy,
        "primary_strategy_family": primary.get("strategy_family") if primary_strategy and primary else None,
        "route_new_signals_to": "DECISION_SCORE_ENGINE_V1_WITH_ADAPTIVE_WEIGHTS_V2",
        "default_new_signal_policy": "EVALUATE_BY_META_POLICY_THEN_DECISION_ENGINE",
        "meta_gate_required": True,
        "blocked_actions": ["DIRECT_EXECUTION_WITHOUT_DECISION_SCORE", "BYPASS_RISK_MANAGER", "BYPASS_POSITION_SIZING", "BYPASS_META_STRATEGY_POLICY"],
        "human_report_required": False,
        "supervisor_interpretation": "ASSISTANT_INTERPRETS_RETURNS_WHEN_USER_SENDS_OUTPUT",
    }

    payload = {
        "ok": True,
        "version": META_STRATEGY_ENGINE_V11_VERSION,
        "mode": META_STRATEGY_ENGINE_V11_MODE,
        "generated_at": generated_at,
        "capital": capital,
        "portfolio_state": portfolio_state,
        "market_context": context,
        "automation_policy": automation_policy,
        "counts": counts,
        "strategies": strategies,
        "cluster_summary": cluster_summary,
        "primary_strategy": primary if primary_strategy else None,
        "top_candidate": primary,
        "upstream_counts": {
            "advisor_ranking": len(ranking),
            "optimizer_allocations": len(optimized),
            "risk_budgets": len(budgets),
        },
        "adaptive_context": {
            "version": (adaptive or {}).get("version"),
            "evidence_quality": (adaptive or {}).get("evidence_quality"),
            "outcome_evaluations_detected": (adaptive or {}).get("outcome_evaluations_detected"),
            "active_weights": (adaptive or {}).get("active_weights"),
            "shadow_weights": (adaptive or {}).get("shadow_weights"),
        },
        "alerts": alerts,
        "notes": notes,
    }

    META_STRATEGY_ENGINE_V11_CACHE["last_generated_at"] = generated_at
    META_STRATEGY_ENGINE_V11_CACHE["last_regime"] = context.get("regime")
    META_STRATEGY_ENGINE_V11_CACHE["last_primary_strategy"] = primary_strategy
    return payload


# Compatibilidade: chamadas V1 passam a usar a lógica corrigida V1.1.
def build_meta_strategy_engine_v1(capital=10000.0, market_regime=None, persist=False):
    return build_meta_strategy_engine_v1_1(capital=capital, market_regime=market_regime, persist=persist)


def build_meta_strategy_engine_v1_1_text(capital=10000.0, market_regime=None, persist=False):
    payload = build_meta_strategy_engine_v1_1(capital=capital, market_regime=market_regime, persist=persist)
    ctx = payload.get("market_context") or {}
    pol = payload.get("automation_policy") or {}
    counts = payload.get("counts") or {}
    up = payload.get("upstream_counts") or {}
    lines = [
        "🧠 META STRATEGY ENGINE V1.1 — CENTRAL QUANT",
        f"Data/hora: {payload.get('generated_at')}",
        f"Versão: {payload.get('version')}",
        f"Modo: {payload.get('mode')}",
        "",
        "Estado autônomo:",
        f"Regime interno: {ctx.get('regime')} | fonte: {ctx.get('source')}",
        f"Portfólio: posições {ctx.get('positions')} | LONG {ctx.get('long')} ({ctx.get('long_pct')}%) | SHORT {ctx.get('short')} ({ctx.get('short_pct')}%) | Net {ctx.get('net_direction')}",
        f"Primary strategy: {pol.get('primary_strategy')} | família: {pol.get('primary_strategy_family')}",
        f"Autonomous mode ready: {pol.get('autonomous_mode_ready')} | Human report required: {pol.get('human_report_required')}",
        "",
        "Integração upstream:",
        f"Advisor ranking: {up.get('advisor_ranking')} | Optimizer allocations: {up.get('optimizer_allocations')} | Risk budgets: {up.get('risk_budgets')}",
        "",
        "Contagem de orquestração:",
        f"Primary: {counts.get('primary')} | Secondary: {counts.get('secondary')} | Wait/Reduce: {counts.get('wait_reduce')} | Defensive: {counts.get('disabled')} | Eligible: {counts.get('eligible_for_decision_engine')} | Total: {counts.get('total')}",
        "",
        "Política para novos sinais:",
        f"Rota: {pol.get('route_new_signals_to')}",
        f"Default: {pol.get('default_new_signal_policy')}",
        f"Meta gate required: {pol.get('meta_gate_required')}",
        "Bloqueios:",
    ]
    for item in pol.get("blocked_actions") or []:
        lines.append(f"- {item}")
    lines += ["", "Estratégias/robôs:"]
    for i, s in enumerate(payload.get("strategies") or [], start=1):
        lines += [
            f"{i}. {s.get('bot')} — {s.get('orchestration_action')} | Gate: {s.get('signal_gate')} | Autonomy: {s.get('autonomy_gate')}",
            f"Família: {s.get('strategy_family')} | Cluster: {s.get('strategy_cluster')} | Categoria: {s.get('category')} | Score: {s.get('score')}",
            f"Advisor: {s.get('advisor_action')} | Optimizer: {s.get('optimizer_recommendation')} | Risk state: {s.get('risk_state')}",
            f"Target: {s.get('target_pct')}% | Atual: {s.get('current_pct')}% | Δ {s.get('delta_pct')}% | Risk budget: {s.get('risk_budget_pct')}% | R/trade: {s.get('risk_per_trade_pct')}%",
            f"Priority score: {s.get('autonomous_priority_score')} | Risk mult: {s.get('risk_multiplier')} | Sizing mult: {s.get('sizing_multiplier')}",
            "Motivos:",
        ]
        for r in s.get("reasons") or []:
            lines.append(f"- {r}")
        lines.append("")
    lines += ["Resumo por cluster:"]
    for cluster, data in (payload.get("cluster_summary") or {}).items():
        lines.append(f"- {cluster}: bots={data.get('bots')} | target={data.get('target_pct')}% | risk={data.get('risk_budget_pct')}% | avg_score={data.get('avg_score')} | primary={data.get('primary')} | secondary={data.get('secondary')} | disabled={data.get('disabled')}")
    lines += ["", "Alertas:"]
    for a in payload.get("alerts") or []:
        lines.append(f"- {a}")
    lines += ["", "Notas:"]
    for n in payload.get("notes") or []:
        lines.append(f"- {n}")
    return "\n".join(lines), payload


def build_meta_strategy_engine_v1_text(capital=10000.0, market_regime=None, persist=False):
    return build_meta_strategy_engine_v1_1_text(capital=capital, market_regime=market_regime, persist=persist)


@app.route("/meta/strategy/v1", methods=["GET", "POST"])
@app.route("/meta-strategy/v1", methods=["GET", "POST"])
@app.route("/strategy/meta/v1", methods=["GET", "POST"])
@app.route("/meta/strategy/v1.1", methods=["GET", "POST"])
@app.route("/meta-strategy/v1.1", methods=["GET", "POST"])
@app.route("/strategy/meta/v1.1", methods=["GET", "POST"])
def meta_strategy_engine_v11_route():
    body = request.get_json(silent=True) or {}
    capital = _mse_safe_float(body.get("capital") or request.args.get("capital"), 10000.0)
    market_regime = body.get("market_regime") or body.get("regime") or request.args.get("market_regime") or request.args.get("regime")
    persist = str(body.get("persist") or request.args.get("persist", "")).strip().lower() in {"1", "true", "yes", "sim", "on", "save"}
    text, payload = build_meta_strategy_engine_v1_1_text(capital=capital, market_regime=market_regime, persist=persist)
    return {"ok": True, "payload": payload, "text": text}


@app.route("/meta/strategy/summary/v1", methods=["GET", "POST"])
@app.route("/meta-strategy/summary/v1", methods=["GET", "POST"])
@app.route("/meta/strategy/summary/v1.1", methods=["GET", "POST"])
@app.route("/meta-strategy/summary/v1.1", methods=["GET", "POST"])
def meta_strategy_engine_v11_summary_route():
    body = request.get_json(silent=True) or {}
    capital = _mse_safe_float(body.get("capital") or request.args.get("capital"), 10000.0)
    market_regime = body.get("market_regime") or body.get("regime") or request.args.get("market_regime") or request.args.get("regime")
    payload = build_meta_strategy_engine_v1_1(capital=capital, market_regime=market_regime, persist=False)
    return {
        "ok": True,
        "version": payload.get("version"),
        "generated_at": payload.get("generated_at"),
        "mode": payload.get("mode"),
        "market_context": payload.get("market_context"),
        "automation_policy": payload.get("automation_policy"),
        "counts": payload.get("counts"),
        "primary_strategy": payload.get("primary_strategy"),
        "top_candidate": payload.get("top_candidate"),
        "cluster_summary": payload.get("cluster_summary"),
        "upstream_counts": payload.get("upstream_counts"),
        "adaptive_context": payload.get("adaptive_context"),
        "alerts": payload.get("alerts"),
    }


@app.route("/metastrategy", methods=["GET", "POST"])
@app.route("/meta", methods=["GET", "POST"])
def meta_strategy_engine_v11_short_route():
    body = request.get_json(silent=True) or {}
    capital = _mse_safe_float(body.get("capital") or request.args.get("capital"), 10000.0)
    market_regime = body.get("market_regime") or body.get("regime") or request.args.get("market_regime") or request.args.get("regime")
    text, payload = build_meta_strategy_engine_v1_1_text(capital=capital, market_regime=market_regime, persist=False)
    return {"ok": True, "payload": payload, "text": text}


# ============================================================
# MARKET REGIME DETECTOR V1 — CENTRAL QUANT
# Machine-first regime layer. It does not execute; it classifies
# the current internal/portfolio context and provides policy hints
# for Meta Strategy and Decision engines.
# ============================================================

MARKET_REGIME_DETECTOR_V1_VERSION = "2026-07-04-MARKET-REGIME-DETECTOR-V1"


def _mrd_safe_float(value, default=0.0):
    try:
        if value is None or value == "":
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _mrd_safe_int(value, default=0):
    try:
        if value is None or value == "":
            return int(default)
        return int(float(value))
    except Exception:
        return int(default)


def _mrd_round(value, ndigits=4):
    try:
        return round(float(value), ndigits)
    except Exception:
        return value


def _mrd_get_exposure_summary(capital=10000.0):
    try:
        if "build_bot_exposure_manager_v2" in globals():
            payload = build_bot_exposure_manager_v2(capital=capital)
            return payload.get("summary") or payload or {}
    except Exception as exc:
        return {"error": str(exc)}
    return {}


def _mrd_get_meta_context(capital=10000.0):
    try:
        if "build_meta_strategy_engine_v1_1" in globals():
            return build_meta_strategy_engine_v1_1(capital=capital) or {}
    except Exception as exc:
        return {"error": str(exc), "strategies": []}
    return {"strategies": []}


def _mrd_classify_exposure_regime(exposure_summary):
    positions = _mrd_safe_int(exposure_summary.get("positions"), 0)
    long_n = _mrd_safe_int(exposure_summary.get("long"), 0)
    short_n = _mrd_safe_int(exposure_summary.get("short"), 0)
    risk_used = _mrd_safe_float(exposure_summary.get("risk_used_usdt"), 0.0)
    capital_used = _mrd_safe_float(exposure_summary.get("capital_used"), 0.0)
    capital = _mrd_safe_float(exposure_summary.get("capital"), 10000.0) or 10000.0
    capital_usage_pct = _mrd_safe_float(exposure_summary.get("capital_usage_pct"), (capital_used / capital * 100.0 if capital else 0.0))
    long_pct = (long_n / positions * 100.0) if positions else 0.0
    short_pct = (short_n / positions * 100.0) if positions else 0.0
    imbalance_pct = abs(long_pct - short_pct)

    if positions <= 0:
        regime = "NO_PORTFOLIO_EXPOSURE"
        family = "UNKNOWN_WAIT_SAMPLE"
        confidence = 35.0
        direction = "FLAT"
    elif long_pct >= 75.0:
        regime = "DIRECTIONAL_LONG_EXPOSURE"
        family = "TREND_BIASED"
        confidence = min(92.0, 55.0 + imbalance_pct * 0.45)
        direction = "LONG"
    elif short_pct >= 75.0:
        regime = "DIRECTIONAL_SHORT_EXPOSURE"
        family = "TREND_BIASED"
        confidence = min(92.0, 55.0 + imbalance_pct * 0.45)
        direction = "SHORT"
    elif imbalance_pct <= 20.0 and positions >= 6:
        regime = "BALANCED_OR_HEDGED_EXPOSURE"
        family = "BALANCED"
        confidence = 65.0
        direction = "BALANCED"
    elif positions >= 15 and capital_usage_pct >= 40.0:
        regime = "CROWDED_PORTFOLIO_EXPOSURE"
        family = "RISK_COMPRESSION"
        confidence = 72.0
        direction = "MIXED"
    else:
        regime = "MIXED_EXPOSURE"
        family = "TRANSITIONAL"
        confidence = 55.0
        direction = exposure_summary.get("net_direction") or "MIXED"

    return {
        "regime": regime,
        "regime_family": family,
        "confidence": _mrd_round(confidence, 2),
        "positions": positions,
        "long": long_n,
        "short": short_n,
        "long_pct": _mrd_round(long_pct, 2),
        "short_pct": _mrd_round(short_pct, 2),
        "imbalance_pct": _mrd_round(imbalance_pct, 2),
        "net_direction": direction,
        "capital_usage_pct": _mrd_round(capital_usage_pct, 2),
        "risk_used_usdt": _mrd_round(risk_used, 4),
    }


def _mrd_cluster_policy(exposure_regime, meta_payload):
    strategies = meta_payload.get("strategies") or []
    cluster_summary = meta_payload.get("cluster_summary") or {}
    primary = meta_payload.get("primary_strategy") or {}
    regime = exposure_regime.get("regime")
    net_direction = exposure_regime.get("net_direction")

    cluster_policy = {}
    for cluster, data in cluster_summary.items():
        cluster_key = str(cluster or "UNKNOWN").upper()
        primary_count = _mrd_safe_int(data.get("primary"), 0)
        disabled_count = _mrd_safe_int(data.get("disabled"), 0)
        avg_score = _mrd_safe_float(data.get("avg_score"), 0.0)
        risk_budget_pct = _mrd_safe_float(data.get("risk_budget_pct"), 0.0)
        target_pct = _mrd_safe_float(data.get("target_pct"), 0.0)

        action = "NEUTRAL_WAIT"
        multiplier = 0.35
        gate = "REQUIRES_DECISION_SCORE"
        reasons = []

        if primary_count > 0:
            action = "PRIMARY_CLUSTER"
            multiplier = 1.0
            gate = "ALLOW_ONLY_IF_META_AND_RISK_ALLOW"
            reasons.append("Cluster contém a estratégia primária atual.")
        elif disabled_count >= _mrd_safe_int(data.get("bots"), 0) and _mrd_safe_int(data.get("bots"), 0) > 0:
            action = "DISABLED_CLUSTER"
            multiplier = 0.0
            gate = "BLOCK_NEW_SIGNALS"
            reasons.append("Todos os robôs do cluster estão defensivos/bloqueados para novo risco.")
        elif avg_score >= 60.0 and risk_budget_pct > 0.15:
            action = "SECONDARY_CLUSTER"
            multiplier = 0.35
            gate = "ALLOW_SMALL_FILTERED_SIGNALS"
            reasons.append("Cluster tem score/risk budget suficientes para sinais filtrados.")
        else:
            action = "WAIT_CLUSTER"
            multiplier = 0.15
            gate = "REDUCE_OR_WAIT_SIGNALS"
            reasons.append("Cluster sem força suficiente para prioridade autônoma.")

        if regime in {"DIRECTIONAL_LONG_EXPOSURE", "DIRECTIONAL_SHORT_EXPOSURE"} and action != "PRIMARY_CLUSTER":
            multiplier = min(multiplier, 0.2)
            reasons.append("Portfólio já está direcional; clusters não primários ficam comprimidos.")

        cluster_policy[cluster_key] = {
            "cluster": cluster_key,
            "action": action,
            "signal_gate": gate,
            "risk_multiplier": _mrd_round(multiplier, 4),
            "target_pct": _mrd_round(target_pct, 4),
            "risk_budget_pct": _mrd_round(risk_budget_pct, 4),
            "avg_score": _mrd_round(avg_score, 2),
            "primary": primary_count,
            "disabled": disabled_count,
            "reasons": reasons,
        }

    return cluster_policy


def build_market_regime_detector_v1(capital=10000.0, persist=False):
    generated_at = data_hora_sp_str() if "data_hora_sp_str" in globals() else ""
    exposure_summary = _mrd_get_exposure_summary(capital=capital)
    meta_payload = _mrd_get_meta_context(capital=capital)
    exposure_regime = _mrd_classify_exposure_regime(exposure_summary)
    cluster_policy = _mrd_cluster_policy(exposure_regime, meta_payload)
    strategies = meta_payload.get("strategies") or []
    primary = meta_payload.get("primary_strategy") or None

    regime = exposure_regime.get("regime")
    family = exposure_regime.get("regime_family")
    confidence = _mrd_safe_float(exposure_regime.get("confidence"), 0.0)
    long_pct = _mrd_safe_float(exposure_regime.get("long_pct"), 0.0)
    short_pct = _mrd_safe_float(exposure_regime.get("short_pct"), 0.0)

    direction_policy = {
        "new_long_signals": "NORMAL",
        "new_short_signals": "NORMAL",
        "reason": "Sem compressão direcional extrema detectada.",
    }
    alerts = []

    if regime == "DIRECTIONAL_LONG_EXPOSURE":
        direction_policy = {
            "new_long_signals": "COMPRESS_OR_ALLOW_ONLY_HIGH_QUALITY",
            "new_short_signals": "ALLOW_IF_RISK_AND_META_APPROVE",
            "reason": "Portfólio já está fortemente LONG; novos LONGs precisam reduzir concentração ou ter qualidade excepcional.",
        }
        alerts.append("Regime interno direcional LONG; comprimir novos sinais LONG sem qualidade excepcional.")
    elif regime == "DIRECTIONAL_SHORT_EXPOSURE":
        direction_policy = {
            "new_long_signals": "ALLOW_IF_RISK_AND_META_APPROVE",
            "new_short_signals": "COMPRESS_OR_ALLOW_ONLY_HIGH_QUALITY",
            "reason": "Portfólio já está fortemente SHORT; novos SHORTs precisam reduzir concentração ou ter qualidade excepcional.",
        }
        alerts.append("Regime interno direcional SHORT; comprimir novos sinais SHORT sem qualidade excepcional.")
    elif regime == "CROWDED_PORTFOLIO_EXPOSURE":
        direction_policy = {
            "new_long_signals": "REDUCE_OR_WAIT",
            "new_short_signals": "REDUCE_OR_WAIT",
            "reason": "Portfólio cheio; priorizar qualidade, redução de exposição e sinais excepcionais.",
        }
        alerts.append("Portfólio carregado; Market Regime recomenda compressão de novos sinais.")

    eligible_clusters = [k for k, v in cluster_policy.items() if v.get("action") in {"PRIMARY_CLUSTER", "SECONDARY_CLUSTER"}]
    blocked_clusters = [k for k, v in cluster_policy.items() if v.get("action") == "DISABLED_CLUSTER"]
    compressed_clusters = [k for k, v in cluster_policy.items() if v.get("risk_multiplier", 0.0) <= 0.2 and v.get("action") != "DISABLED_CLUSTER"]

    if not primary:
        alerts.append("Nenhuma estratégia primária detectada pelo Meta Strategy; regime deve operar defensivo/aguardar amostra.")
    if exposure_regime.get("positions", 0) <= 0:
        alerts.append("Sem exposição suficiente para inferir regime robusto por proxy; aguardar Market Regime real com dados de mercado.")

    automation_policy = {
        "market_regime_ready": True,
        "source": "EXPOSURE_AND_META_PROXY_V1",
        "human_report_required": False,
        "route_new_signals_to": "META_STRATEGY_GATE_THEN_DECISION_SCORE_ENGINE",
        "meta_strategy_required": True,
        "decision_score_required": True,
        "direction_policy": direction_policy,
        "eligible_clusters": eligible_clusters,
        "blocked_clusters": blocked_clusters,
        "compressed_clusters": compressed_clusters,
        "primary_strategy": (primary or {}).get("bot") if isinstance(primary, dict) else None,
        "primary_strategy_family": (primary or {}).get("strategy_family") if isinstance(primary, dict) else None,
    }

    payload = {
        "ok": True,
        "version": MARKET_REGIME_DETECTOR_V1_VERSION,
        "generated_at": generated_at,
        "mode": "OBSERVATION_ONLY",
        "capital": _mrd_round(capital, 4),
        "regime": regime,
        "regime_family": family,
        "confidence": confidence,
        "source": "EXPOSURE_PROXY_PLUS_META_STRATEGY",
        "market_data_used": False,
        "exposure_regime": exposure_regime,
        "portfolio_state": meta_payload.get("portfolio_state"),
        "primary_strategy": primary,
        "strategy_count": len(strategies),
        "cluster_policy": cluster_policy,
        "automation_policy": automation_policy,
        "alerts": alerts,
        "notes": [
            "Market Regime Detector V1 é machine-first e não depende de leitura humana de relatório.",
            "V1 ainda não usa candles/indicadores de mercado; classifica regime por exposição, Meta Strategy e clusters internos.",
            "O regime detectado deve funcionar como gate adicional antes do Decision Score/Execution Policy.",
            "No futuro, Market Regime Detector V2 deve incorporar ADX, ATR, volatilidade, range, breadth e correlação real de mercado.",
        ],
    }
    return payload


def build_market_regime_detector_v1_text(capital=10000.0, persist=False):
    payload = build_market_regime_detector_v1(capital=capital, persist=persist)
    er = payload.get("exposure_regime") or {}
    auto = payload.get("automation_policy") or {}
    direction = auto.get("direction_policy") or {}
    lines = [
        "🧭 MARKET REGIME DETECTOR V1 — CENTRAL QUANT",
        f"Data/hora: {payload.get('generated_at')}",
        f"Versão: {payload.get('version')}",
        f"Modo: {payload.get('mode')}",
        "",
        "Regime interno detectado:",
        f"Regime: {payload.get('regime')} | Família: {payload.get('regime_family')} | Confiança: {payload.get('confidence')}/100",
        f"Fonte: {payload.get('source')} | Market data usado: {payload.get('market_data_used')}",
        f"Exposição: posições {er.get('positions')} | LONG {er.get('long')} ({er.get('long_pct')}%) | SHORT {er.get('short')} ({er.get('short_pct')}%) | Net {er.get('net_direction')}",
        f"Capital usado: {er.get('capital_usage_pct')}% | Risco aberto: {er.get('risk_used_usdt')} USDT",
        "",
        "Política direcional:",
        f"Novos LONG: {direction.get('new_long_signals')}",
        f"Novos SHORT: {direction.get('new_short_signals')}",
        f"Motivo: {direction.get('reason')}",
        "",
        "Política autônoma:",
        f"Market regime ready: {auto.get('market_regime_ready')} | Human report required: {auto.get('human_report_required')}",
        f"Rota: {auto.get('route_new_signals_to')}",
        f"Primary strategy: {auto.get('primary_strategy')} | Família: {auto.get('primary_strategy_family')}",
        f"Eligible clusters: {', '.join(auto.get('eligible_clusters') or []) or 'None'}",
        f"Compressed clusters: {', '.join(auto.get('compressed_clusters') or []) or 'None'}",
        f"Blocked clusters: {', '.join(auto.get('blocked_clusters') or []) or 'None'}",
        "",
        "Política por cluster:",
    ]
    for name, c in (payload.get("cluster_policy") or {}).items():
        lines.append(f"- {name}: {c.get('action')} | Gate: {c.get('signal_gate')} | Risk mult: {c.get('risk_multiplier')} | Score médio: {c.get('avg_score')} | Target: {c.get('target_pct')}%")
        for reason in c.get("reasons") or []:
            lines.append(f"  • {reason}")
    lines += ["", "Alertas:"]
    for a in payload.get("alerts") or []:
        lines.append(f"- {a}")
    lines += ["", "Notas:"]
    for n in payload.get("notes") or []:
        lines.append(f"- {n}")
    return "\n".join(lines), payload


@app.route("/market/regime/v1", methods=["GET", "POST"])
@app.route("/regime/market/v1", methods=["GET", "POST"])
@app.route("/market-regime/v1", methods=["GET", "POST"])
def market_regime_detector_v1_route():
    body = request.get_json(silent=True) or {}
    capital = _mrd_safe_float(body.get("capital") or request.args.get("capital"), 10000.0)
    persist = str(body.get("persist") or request.args.get("persist", "")).strip().lower() in {"1", "true", "yes", "sim", "on", "save"}
    text, payload = build_market_regime_detector_v1_text(capital=capital, persist=persist)
    return {"ok": True, "payload": payload, "text": text}


@app.route("/market/regime/summary/v1", methods=["GET", "POST"])
@app.route("/market-regime/summary/v1", methods=["GET", "POST"])
def market_regime_detector_v1_summary_route():
    body = request.get_json(silent=True) or {}
    capital = _mrd_safe_float(body.get("capital") or request.args.get("capital"), 10000.0)
    payload = build_market_regime_detector_v1(capital=capital, persist=False)
    return {
        "ok": True,
        "version": payload.get("version"),
        "generated_at": payload.get("generated_at"),
        "mode": payload.get("mode"),
        "regime": payload.get("regime"),
        "regime_family": payload.get("regime_family"),
        "confidence": payload.get("confidence"),
        "exposure_regime": payload.get("exposure_regime"),
        "automation_policy": payload.get("automation_policy"),
        "cluster_policy": payload.get("cluster_policy"),
        "alerts": payload.get("alerts"),
    }


@app.route("/regime", methods=["GET", "POST"])
def market_regime_detector_v1_short_route():
    body = request.get_json(silent=True) or {}
    capital = _mrd_safe_float(body.get("capital") or request.args.get("capital"), 10000.0)
    text, payload = build_market_regime_detector_v1_text(capital=capital, persist=False)
    return {"ok": True, "payload": payload, "text": text}



# ============================================================
# CORRELATION ENGINE V1 — CENTRAL QUANT
# Version: 2026-07-04-CORRELATION-ENGINE-V1
# Machine-first internal module. It does not execute orders.
# It estimates hidden concentration across correlated crypto clusters
# and acts as an additional gate before Meta/Decision/Execution flows.
# ============================================================

CORRELATION_ENGINE_V1_VERSION = "2026-07-04-CORRELATION-ENGINE-V1"


def _ce_safe_float(value, default=0.0):
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _ce_safe_int(value, default=0):
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def _ce_round(value, nd=4):
    try:
        return round(float(value), nd)
    except Exception:
        return value


def _ce_symbol_clean(symbol):
    s = str(symbol or "").upper().strip()
    s = s.replace("/USDT:USDT", "USDT").replace("/USDT", "USDT").replace(":USDT", "")
    s = s.replace("PERP", "").replace("-", "")
    if s and not s.endswith("USDT") and s not in {"BTC", "ETH", "SOL"}:
        # Keep raw symbols like BTC/ETH clean but do not force unknown suffixes.
        pass
    return s


def _ce_base_asset(symbol):
    s = _ce_symbol_clean(symbol)
    if s.endswith("USDT"):
        return s[:-4]
    return s


def _ce_primary_cluster_for_symbol(symbol):
    base = _ce_base_asset(symbol)
    # Static crypto correlation map V1. This is intentionally conservative;
    # Market Regime V2 may replace it with rolling return correlations.
    if base in {"BTC", "ETH", "BNB", "SOL", "AVAX", "LINK", "LTC", "BCH", "DOT", "NEAR", "INJ", "ATOM", "SUI", "APT", "ADA", "XRP", "TRX", "UNI"}:
        return "MAJOR_BETA"
    if base in {"DOGE", "WIF", "PEPE", "1000PEPE", "SHIB", "BONK", "FLOKI", "MEME", "BOME", "TURBO"}:
        return "MEME_BETA"
    if base in {"FET", "TAO", "RNDR", "RENDER", "WLD", "AI", "AGIX", "OCEAN", "ARKM", "GRT"}:
        return "AI_BETA"
    if base in {"AAVE", "UNI", "MKR", "COMP", "SNX", "CRV", "PENDLE", "LDO", "RUNE"}:
        return "DEFI_BETA"
    if base in {"FIL", "AR", "STX", "TIA", "SEI", "HBAR", "OP", "ARB", "JUP", "HYPE", "ENA", "RAY"}:
        return "ALT_BETA"
    return "OTHER_BETA"


def _ce_symbol_clusters(symbol):
    base = _ce_base_asset(symbol)
    clusters = {_ce_primary_cluster_for_symbol(symbol)}
    # Add broader overlays for hidden correlation.
    if base in {"BTC", "ETH", "SOL", "BNB", "AVAX", "ADA", "XRP", "LINK", "SUI", "LTC", "BCH"}:
        clusters.add("CRYPTO_CORE")
    if base not in {"BTC", "ETH"}:
        clusters.add("ALTCOIN_BETA")
    if base in {"SOL", "JUP", "RAY", "WIF", "BONK"}:
        clusters.add("SOL_ECOSYSTEM")
    if base in {"BTC", "ETH"}:
        clusters.add("MARKET_ANCHOR")
    return sorted(clusters)


def _ce_cluster_policy_from_pressure(positions, pct, same_symbol_count=0, side=None, net_direction=None):
    side = str(side or "").upper()
    net_direction = str(net_direction or "").upper()
    action = "ALLOW_CLUSTER_NORMAL"
    gate = "ALLOW_IF_DECISION_ENGINE_APPROVES"
    multiplier = 1.0
    severity = "LOW"
    reasons = []

    if same_symbol_count >= 1:
        action = "REDUCE_OR_BLOCK_SAME_SYMBOL"
        gate = "BLOCK_OR_REQUIRE_EXCEPTION_FOR_SAME_SYMBOL"
        multiplier = min(multiplier, 0.15)
        severity = "HIGH"
        reasons.append("Já existe exposição no mesmo ativo; evitar duplicar risco específico.")

    if positions >= 8 or pct >= 55:
        action = "COMPRESS_CLUSTER_RISK"
        gate = "ALLOW_ONLY_HIGH_QUALITY_OR_HEDGE"
        multiplier = min(multiplier, 0.25)
        severity = "HIGH"
        reasons.append("Cluster concentrado; novo risco deve ser comprimido ou exigir qualidade excepcional.")
    elif positions >= 5 or pct >= 35:
        action = "REDUCE_CLUSTER_RISK"
        gate = "REDUCE_SIZE_OR_WAIT"
        multiplier = min(multiplier, 0.5)
        severity = "MEDIUM"
        reasons.append("Cluster com exposição relevante; reduzir tamanho de novos sinais.")
    elif positions >= 3 or pct >= 20:
        action = "WATCH_CLUSTER_RISK"
        gate = "ALLOW_WITH_CORRELATION_AWARE_SIZING"
        multiplier = min(multiplier, 0.75)
        severity = "WATCH"
        reasons.append("Cluster com exposição moderada; acompanhar correlação antes de ampliar.")

    if side and net_direction and side == net_direction and net_direction in {"LONG", "SHORT"} and severity in {"MEDIUM", "HIGH", "WATCH"}:
        multiplier = min(multiplier, 0.5)
        if "Novo sinal aumenta a direção líquida atual do portfólio." not in reasons:
            reasons.append("Novo sinal aumenta a direção líquida atual do portfólio.")
        if severity == "WATCH":
            severity = "MEDIUM"

    return {
        "action": action,
        "signal_gate": gate,
        "risk_multiplier": _ce_round(multiplier, 4),
        "severity": severity,
        "reasons": reasons or ["Cluster sem concentração crítica detectada."],
    }


def _ce_get_exposure_summary(capital=10000.0):
    try:
       fn = globals().get("build_bot_exposure_manager_v21")
       if callable(fn):
            data = fn(capital=capital)
            if isinstance(data, dict):
                return data.get("summary") or data.get("payload", {}).get("summary") or {}
    except Exception:
        pass
    try:
        if "_mrd_get_exposure_summary" in globals():
            return _mrd_get_exposure_summary(capital=capital) or {}
    except Exception:
        pass
    return {}


def _ce_get_market_regime(capital=10000.0):
    """Lightweight proxy used by Correlation Engine.

    Important: do not call build_market_regime_detector_v1 here. That function
    can call Meta/Adaptive/Decision layers, and when Correlation is used inside
    Execution/Decision this creates a heavy cascade. Correlation V1 only needs
    a compact exposure-derived regime.
    """
    exposure = _ce_get_exposure_summary(capital=capital)
    long_n = _ce_safe_int(exposure.get("long"), 0)
    short_n = _ce_safe_int(exposure.get("short"), 0)
    positions = _ce_safe_int(exposure.get("positions"), long_n + short_n)
    net = str(exposure.get("net_direction") or "FLAT").upper()
    if positions <= 0:
        regime = "NO_OPEN_EXPOSURE"
        family = "NEUTRAL"
        confidence = 50.0
    else:
        long_pct = (long_n / positions * 100.0) if positions else 0.0
        short_pct = (short_n / positions * 100.0) if positions else 0.0
        imbalance = abs(long_pct - short_pct)
        if net == "LONG" and long_pct >= 65:
            regime, family = "DIRECTIONAL_LONG_EXPOSURE", "TREND_BIASED"
        elif net == "SHORT" and short_pct >= 65:
            regime, family = "DIRECTIONAL_SHORT_EXPOSURE", "TREND_BIASED"
        else:
            regime, family = "BALANCED_OR_MIXED_EXPOSURE", "MIXED"
        confidence = _ce_round(min(95.0, 50.0 + imbalance * 0.5), 2)
    return {
        "regime": regime,
        "regime_family": family,
        "confidence": confidence,
        "source": "LIGHTWEIGHT_EXPOSURE_PROXY_FOR_CORRELATION",
        "portfolio_state": "DIRECTIONAL_EXPOSURE" if "DIRECTIONAL" in regime else "BALANCED_EXPOSURE",
        "exposure_regime": {"net_direction": net, "positions": positions, "long": long_n, "short": short_n},
    }


def _ce_get_meta_strategy(capital=10000.0):
    """Compact meta context for Correlation Engine.

    Avoid calling the full Meta Strategy engine here to prevent recursive/heavy
    Decision -> Correlation -> Meta -> Adaptive -> Decision chains.
    """
    return {"portfolio_state": None}


def _ce_build_cluster_book(symbol_counts, capital=10000.0):
    total_positions = sum(_ce_safe_int(v, 0) for v in (symbol_counts or {}).values()) or 0
    cluster_book = {}
    symbol_details = []
    for raw_symbol, count in (symbol_counts or {}).items():
        symbol = _ce_symbol_clean(raw_symbol)
        count = _ce_safe_int(count, 0)
        clusters = _ce_symbol_clusters(symbol)
        primary_cluster = _ce_primary_cluster_for_symbol(symbol)
        detail = {
            "symbol": symbol,
            "base": _ce_base_asset(symbol),
            "count": count,
            "primary_cluster": primary_cluster,
            "clusters": clusters,
        }
        symbol_details.append(detail)
        for cluster in clusters:
            item = cluster_book.setdefault(cluster, {
                "cluster": cluster,
                "positions": 0,
                "symbols": {},
                "symbols_count": 0,
                "position_pct": 0.0,
                "estimated_cluster_capital_usdt": 0.0,
                "severity": "LOW",
            })
            item["positions"] += count
            item["symbols"][symbol] = item["symbols"].get(symbol, 0) + count
    estimated_capital_per_position = 0.0
    if total_positions > 0:
        estimated_capital_per_position = _ce_safe_float(capital, 10000.0) / max(total_positions, 1)
    for item in cluster_book.values():
        item["symbols_count"] = len(item.get("symbols") or {})
        item["position_pct"] = _ce_round((item.get("positions", 0) / total_positions * 100.0) if total_positions else 0.0, 2)
        item["estimated_cluster_capital_usdt"] = _ce_round(item.get("positions", 0) * estimated_capital_per_position, 4)
        pct = _ce_safe_float(item.get("position_pct"), 0.0)
        pos = _ce_safe_int(item.get("positions"), 0)
        if pos >= 8 or pct >= 55:
            item["severity"] = "HIGH"
        elif pos >= 5 or pct >= 35:
            item["severity"] = "MEDIUM"
        elif pos >= 3 or pct >= 20:
            item["severity"] = "WATCH"
        else:
            item["severity"] = "LOW"
    return cluster_book, symbol_details, total_positions


def build_correlation_engine_v1(capital=10000.0, symbol=None, side=None, bot=None, setup=None):
    generated_at = data_hora_sp_str() if "data_hora_sp_str" in globals() else ""
    exposure = _ce_get_exposure_summary(capital=capital)
    market_regime = _ce_get_market_regime(capital=capital)
    meta_strategy = _ce_get_meta_strategy(capital=capital)

    symbols = exposure.get("symbols") or {}
    cluster_book, symbol_details, total_positions = _ce_build_cluster_book(symbols, capital=capital)
    net_direction = str(exposure.get("net_direction") or market_regime.get("exposure_regime", {}).get("net_direction") or "FLAT").upper()

    primary_cluster = None
    signal_clusters = []
    signal_symbol = _ce_symbol_clean(symbol) if symbol else None
    same_symbol_count = 0
    signal_policy = None
    if signal_symbol:
        primary_cluster = _ce_primary_cluster_for_symbol(signal_symbol)
        signal_clusters = _ce_symbol_clusters(signal_symbol)
        same_symbol_count = _ce_safe_int(symbols.get(signal_symbol) or symbols.get(signal_symbol.upper()), 0)
        # Some stored symbols may not be normalized.
        if same_symbol_count <= 0:
            for k, v in symbols.items():
                if _ce_symbol_clean(k) == signal_symbol:
                    same_symbol_count += _ce_safe_int(v, 0)
        cluster_pressures = []
        for cluster in signal_clusters:
            c = cluster_book.get(cluster) or {"positions": 0, "position_pct": 0.0, "symbols": {}}
            policy = _ce_cluster_policy_from_pressure(
                positions=_ce_safe_int(c.get("positions"), 0),
                pct=_ce_safe_float(c.get("position_pct"), 0.0),
                same_symbol_count=same_symbol_count if cluster == primary_cluster else 0,
                side=side,
                net_direction=net_direction,
            )
            cluster_pressures.append({
                "cluster": cluster,
                "positions": _ce_safe_int(c.get("positions"), 0),
                "position_pct": _ce_safe_float(c.get("position_pct"), 0.0),
                "symbols": c.get("symbols") or {},
                **policy,
            })
        # Binding policy is the lowest multiplier / highest severity.
        severity_rank = {"LOW": 0, "WATCH": 1, "MEDIUM": 2, "HIGH": 3}
        binding = sorted(cluster_pressures, key=lambda x: (_ce_safe_float(x.get("risk_multiplier"), 1.0), -severity_rank.get(x.get("severity"), 0)))[0] if cluster_pressures else None
        signal_policy = {
            "bot": str(bot or "").upper() or None,
            "setup": setup,
            "symbol": signal_symbol,
            "side": str(side or "").upper() or None,
            "primary_cluster": primary_cluster,
            "clusters": signal_clusters,
            "same_symbol_count": same_symbol_count,
            "cluster_pressures": cluster_pressures,
            "binding_cluster": binding.get("cluster") if binding else None,
            "correlation_action": binding.get("action") if binding else "ALLOW_CLUSTER_NORMAL",
            "signal_gate": binding.get("signal_gate") if binding else "ALLOW_IF_DECISION_ENGINE_APPROVES",
            "risk_multiplier": _ce_round(binding.get("risk_multiplier", 1.0) if binding else 1.0, 4),
            "severity": binding.get("severity") if binding else "LOW",
            "reasons": (binding.get("reasons") if binding else ["Sem cluster relevante detectado."]),
        }

    # Portfolio-level hidden concentration.
    sorted_clusters = sorted(cluster_book.values(), key=lambda x: (_ce_safe_int(x.get("positions"), 0), _ce_safe_float(x.get("position_pct"), 0.0)), reverse=True)
    top_cluster = sorted_clusters[0] if sorted_clusters else None
    high_clusters = [c for c in sorted_clusters if c.get("severity") == "HIGH"]
    medium_clusters = [c for c in sorted_clusters if c.get("severity") == "MEDIUM"]
    watch_clusters = [c for c in sorted_clusters if c.get("severity") == "WATCH"]

    alerts = []
    if top_cluster and top_cluster.get("severity") in {"HIGH", "MEDIUM"}:
        alerts.append(f"Cluster dominante {top_cluster.get('cluster')} com {top_cluster.get('positions')} posições ({top_cluster.get('position_pct')}%).")
    if signal_policy and signal_policy.get("severity") in {"HIGH", "MEDIUM"}:
        alerts.append(f"Novo sinal em cluster correlacionado exige compressão: {signal_policy.get('binding_cluster')}.")
    if signal_policy and signal_policy.get("same_symbol_count", 0) > 0:
        alerts.append(f"Ativo {signal_policy.get('symbol')} já possui exposição aberta; evitar duplicação.")
    if net_direction in {"LONG", "SHORT"}:
        alerts.append(f"Portfólio líquido {net_direction}; correlação deve evitar reforçar a mesma direção sem qualidade excepcional.")

    automation_policy = {
        "correlation_engine_ready": True,
        "human_report_required": False,
        "route_new_signals_to": "MARKET_REGIME_THEN_META_THEN_CORRELATION_THEN_DECISION_SCORE",
        "correlation_gate_required": True,
        "default_policy": "ALLOW_IF_CLUSTER_AND_DECISION_ENGINE_APPROVE",
        "dominant_cluster": top_cluster.get("cluster") if top_cluster else None,
        "dominant_cluster_severity": top_cluster.get("severity") if top_cluster else None,
        "high_risk_clusters": [c.get("cluster") for c in high_clusters],
        "compressed_clusters": [c.get("cluster") for c in high_clusters + medium_clusters],
        "watch_clusters": [c.get("cluster") for c in watch_clusters],
        "signal_policy": signal_policy,
        "blocked_actions": [
            "BYPASS_CORRELATION_GATE",
            "ADD_SAME_SYMBOL_WITHOUT_EXCEPTION",
            "ADD_HIGH_CORRELATION_CLUSTER_WITHOUT_DECISION_SCORE",
        ],
    }

    payload = {
        "ok": True,
        "version": CORRELATION_ENGINE_V1_VERSION,
        "generated_at": generated_at,
        "mode": "OBSERVATION_ONLY",
        "capital": _ce_round(capital, 4),
        "market_data_used": False,
        "source": "STATIC_CRYPTO_CLUSTER_MAP_PLUS_EXPOSURE_PROXY_V1",
        "portfolio_state": market_regime.get("portfolio_state") or meta_strategy.get("portfolio_state"),
        "market_regime": {
            "regime": market_regime.get("regime"),
            "regime_family": market_regime.get("regime_family"),
            "confidence": market_regime.get("confidence"),
            "source": market_regime.get("source"),
        },
        "exposure_summary": {
            "positions": total_positions,
            "net_direction": net_direction,
            "long": exposure.get("long"),
            "short": exposure.get("short"),
            "capital_used": exposure.get("capital_used"),
            "capital_usage_pct": exposure.get("capital_usage_pct"),
            "risk_used_usdt": exposure.get("risk_used_usdt"),
        },
        "cluster_book": {k: v for k, v in sorted(cluster_book.items())},
        "cluster_rank": sorted_clusters,
        "top_cluster": top_cluster,
        "signal_policy": signal_policy,
        "automation_policy": automation_policy,
        "alerts": alerts,
        "notes": [
            "Correlation Engine V1 é machine-first e não depende de relatório humano.",
            "V1 usa mapa estático de clusters cripto e exposição aberta como proxy de correlação; não usa candles/retornos ainda.",
            "O gate de correlação deve rodar antes do Decision Score/Execution Policy para evitar concentração oculta.",
            "Correlation Engine V2 deve incorporar correlação real por retornos, beta dinâmico, regime de mercado e volatilidade.",
        ],
    }
    return payload


def build_correlation_engine_v1_text(capital=10000.0, symbol=None, side=None, bot=None, setup=None):
    payload = build_correlation_engine_v1(capital=capital, symbol=symbol, side=side, bot=bot, setup=setup)
    exp = payload.get("exposure_summary") or {}
    m = payload.get("market_regime") or {}
    sig = payload.get("signal_policy") or {}
    auto = payload.get("automation_policy") or {}
    lines = [
        "🔗 CORRELATION ENGINE V1 — CENTRAL QUANT",
        f"Data/hora: {payload.get('generated_at')}",
        f"Versão: {payload.get('version')}",
        f"Modo: {payload.get('mode')}",
        "",
        "Estado de correlação:",
        f"Fonte: {payload.get('source')} | Market data usado: {payload.get('market_data_used')}",
        f"Regime: {m.get('regime')} | Família: {m.get('regime_family')} | Confiança: {m.get('confidence')}",
        f"Exposição: posições {exp.get('positions')} | LONG {exp.get('long')} | SHORT {exp.get('short')} | Net {exp.get('net_direction')}",
        f"Capital usado: {exp.get('capital_usage_pct')}% | Risco aberto: {exp.get('risk_used_usdt')} USDT",
        "",
        "Política autônoma:",
        f"Correlation gate required: {auto.get('correlation_gate_required')} | Human report required: {auto.get('human_report_required')}",
        f"Rota: {auto.get('route_new_signals_to')}",
        f"Cluster dominante: {auto.get('dominant_cluster')} | Severidade: {auto.get('dominant_cluster_severity')}",
        f"Compressed clusters: {', '.join(auto.get('compressed_clusters') or []) or 'None'}",
        f"Watch clusters: {', '.join(auto.get('watch_clusters') or []) or 'None'}",
        "",
    ]
    if sig:
        lines += [
            "Política do sinal avaliado:",
            f"Bot: {sig.get('bot')} | Ativo: {sig.get('symbol')} | Side: {sig.get('side')}",
            f"Primary cluster: {sig.get('primary_cluster')} | Clusters: {', '.join(sig.get('clusters') or [])}",
            f"Ação: {sig.get('correlation_action')} | Gate: {sig.get('signal_gate')} | Risk mult: {sig.get('risk_multiplier')} | Severidade: {sig.get('severity')}",
            f"Same symbol count: {sig.get('same_symbol_count')} | Binding cluster: {sig.get('binding_cluster')}",
            "Motivos:",
        ]
        for r in sig.get("reasons") or []:
            lines.append(f"- {r}")
        lines.append("")

    lines.append("Ranking de clusters:")
    for c in payload.get("cluster_rank") or []:
        lines.append(f"- {c.get('cluster')}: posições={c.get('positions')} | pct={c.get('position_pct')}% | símbolos={c.get('symbols_count')} | severidade={c.get('severity')}")
    lines += ["", "Alertas:"]
    for a in payload.get("alerts") or []:
        lines.append(f"- {a}")
    lines += ["", "Notas:"]
    for n in payload.get("notes") or []:
        lines.append(f"- {n}")
    return "\n".join(lines), payload


@app.route("/correlation/engine/v1", methods=["GET", "POST"])
@app.route("/correlation/v1", methods=["GET", "POST"])
def correlation_engine_v1_route():
    body = request.get_json(silent=True) or {}
    capital = _ce_safe_float(body.get("capital") or request.args.get("capital"), 10000.0)
    symbol = body.get("symbol") or request.args.get("symbol")
    side = body.get("side") or request.args.get("side")
    bot = body.get("bot") or request.args.get("bot")
    setup = body.get("setup") or request.args.get("setup")
    text, payload = build_correlation_engine_v1_text(capital=capital, symbol=symbol, side=side, bot=bot, setup=setup)
    return {"ok": True, "payload": payload, "text": text}


@app.route("/correlation/summary/v1", methods=["GET", "POST"])
def correlation_engine_v1_summary_route():
    body = request.get_json(silent=True) or {}
    capital = _ce_safe_float(body.get("capital") or request.args.get("capital"), 10000.0)
    payload = build_correlation_engine_v1(capital=capital)
    return {
        "ok": True,
        "version": payload.get("version"),
        "generated_at": payload.get("generated_at"),
        "mode": payload.get("mode"),
        "market_regime": payload.get("market_regime"),
        "exposure_summary": payload.get("exposure_summary"),
        "top_cluster": payload.get("top_cluster"),
        "cluster_rank": payload.get("cluster_rank"),
        "automation_policy": payload.get("automation_policy"),
        "alerts": payload.get("alerts"),
    }


# ==========================================================
# STRATEGY EVOLUTION ENGINE V1 - CENTRAL QUANT
# ==========================================================

STRATEGY_EVOLUTION_ENGINE_V1_VERSION = "2026-07-04-STRATEGY-EVOLUTION-ENGINE-V1"
STRATEGY_EVOLUTION_ENGINE_V1_MODE = "OBSERVATION_ONLY"
STRATEGY_EVOLUTION_ENGINE_V1_FILE = CENTRAL_DATA_DIR / "strategy_evolution_engine_v1.jsonl"
STRATEGY_EVOLUTION_ENGINE_V1_CACHE = {"last_generated_at": None, "last_capital": None}


def _see_safe_float(value, default=0.0):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _see_safe_int(value, default=0):
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except Exception:
        return default


def _see_append_jsonl(item):
    try:
        STRATEGY_EVOLUTION_ENGINE_V1_FILE.parent.mkdir(exist_ok=True)
        with open(STRATEGY_EVOLUTION_ENGINE_V1_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
        return True, None
    except Exception as exc:
        return False, str(exc)


def _see_get_outcome_stats():
    try:
        return _oe_evaluator_stats(_oe_read_records(limit=5000))
    except Exception:
        try:
            return _le_outcome_stats(_le_read_records(limit=5000))
        except Exception:
            return {"by_module": {}, "by_decision": {}, "evaluations": 0, "records": 0}


def _see_get_trade_stats_by_bot():
    """Use Analytics when available; otherwise return empty stats.

    This keeps Strategy Evolution V1 lightweight and avoids calling heavy endpoints.
    """
    candidates = {}
    try:
        # Many Central versions expose analytics through build_analytics_report.
        fn = globals().get("build_analytics_report")
        if callable(fn):
            raw = fn()
            if isinstance(raw, dict):
                rows = raw.get("bots") or raw.get("by_bot") or raw.get("ranking") or []
                if isinstance(rows, dict):
                    rows = [{"bot": k, **(v if isinstance(v, dict) else {})} for k, v in rows.items()]
                for row in rows or []:
                    bot = str(row.get("bot") or row.get("name") or "").upper().strip()
                    if bot:
                        candidates[bot] = row
    except Exception:
        pass
    return candidates


def _see_find_optimizer_item(optimizer_payload, bot):
    bot = str(bot or "").upper().strip()
    for item in (optimizer_payload.get("optimized_allocation") or []):
        if str(item.get("bot") or "").upper().strip() == bot:
            return item
    return {}


def _see_find_risk_budget_item(risk_budget_payload, bot):
    bot = str(bot or "").upper().strip()
    for item in (risk_budget_payload.get("budgets") or []):
        if str(item.get("bot") or "").upper().strip() == bot:
            return item
    return {}


def _see_find_meta_item(meta_payload, bot):
    bot = str(bot or "").upper().strip()
    for item in (meta_payload.get("strategies") or []):
        if str(item.get("bot") or "").upper().strip() == bot:
            return item
    return {}


def _see_bot_family_from_meta(meta_item, bot):
    try:
        return meta_item.get("strategy_family") or _mse_strategy_family(bot)
    except Exception:
        return "UNKNOWN"


def _see_evolution_decision(bot, advisor_item, optimizer_item, risk_item, meta_item, outcome_stats):
    advisor = advisor_item.get("advisor") or {}
    bot_name = str(bot or advisor_item.get("bot") or "UNKNOWN").upper()
    score = _see_safe_float(advisor_item.get("score"), 0.0)
    trades = _see_safe_int(advisor_item.get("trades"), 0)
    win = _see_safe_float(advisor_item.get("win_rate_pct"), None)
    pnl = _see_safe_float(advisor_item.get("pnl_total_pct"), 0.0)
    expectancy = _see_safe_float(advisor_item.get("expectancy_score") or advisor_item.get("expectancy") or advisor_item.get("expectancy_pct"), None)
    advisor_action = str(advisor.get("action") or optimizer_item.get("advisor_action") or "UNKNOWN").upper()
    optimizer_rec = str(optimizer_item.get("recommendation") or optimizer_item.get("optimizer_recommendation") or "UNKNOWN").upper()
    risk_state = str(risk_item.get("risk_state") or "UNKNOWN").upper()
    meta_gate = str(meta_item.get("autonomy_gate") or "UNKNOWN").upper()
    signal_gate = str(meta_item.get("signal_gate") or "UNKNOWN").upper()
    priority_score = _see_safe_float(meta_item.get("autonomous_priority_score"), 0.0)
    target_pct = _see_safe_float(optimizer_item.get("target_pct") or meta_item.get("target_pct"), 0.0)
    current_pct = _see_safe_float(optimizer_item.get("current_pct") or meta_item.get("current_pct"), 0.0)
    delta_pct = _see_safe_float(optimizer_item.get("delta_pct") or meta_item.get("delta_pct"), 0.0)

    # Outcome evidence by bot is not yet complete in V1; use global evaluator stats as confidence context.
    evaluations = _see_safe_int(outcome_stats.get("evaluations") or outcome_stats.get("outcomes") or 0, 0)

    reasons = []
    action = "OBSERVE"
    evolution_state = "WAIT_MORE_EVIDENCE"
    parameter_policy = "NO_AUTO_CHANGE"
    deployment_policy = "KEEP_CURRENT_VERSION"
    capital_policy = "NO_CHANGE"
    risk_policy = "NO_CHANGE"
    next_experiment = None

    if advisor_action == "PRIORITIZE" and score >= 75 and risk_state == "PRIORITY":
        action = "PROMOTE_OR_MAINTAIN_LEADER"
        evolution_state = "LEADER_ACTIVE"
        parameter_policy = "PROTECT_CORE_LOGIC_NO_RANDOM_CHANGES"
        deployment_policy = "KEEP_CURRENT_VERSION_AND_COLLECT_OUTCOMES"
        capital_policy = "ALLOW_GRADUAL_PRIORITY_IF_RISK_APPROVES"
        risk_policy = "ALLOW_CURRENT_DYNAMIC_BUDGET"
        reasons.append("Robô lidera Advisor/Optimizer/Risk Budget; não alterar lógica vencedora sem evidência contrária.")
    elif advisor_action in {"PAUSE_OR_REVIEW", "DEFUND_OR_PAUSE_OBSERVATION"} or risk_state == "DEFENSIVE_MINIMUM" or "DO_NOT_OPEN" in meta_gate:
        action = "DEMOTE_OR_FREEZE_STRATEGY"
        evolution_state = "DEFENSIVE_REVIEW"
        parameter_policy = "FREEZE_NEW_RISK_AND_REVIEW_SETUP"
        deployment_policy = "NO_PROMOTION_UNTIL_RECOVERY"
        capital_policy = "DEFUND_OR_MINIMUM_ALLOCATION"
        risk_policy = "MINIMUM_RISK_ONLY"
        reasons.append("Advisor/Optimizer/Meta colocaram a estratégia em modo defensivo; bloquear evolução agressiva.")
    elif advisor_action == "REDUCE_OR_WAIT" or risk_state == "WAIT_REDUCED" or "STRONG_CONFIRMATION" in meta_gate:
        action = "REVIEW_AND_REQUIRE_STRONG_CONFIRMATION"
        evolution_state = "WATCHLIST_REDUCED"
        parameter_policy = "TEST_SMALL_VARIANTS_ONLY"
        deployment_policy = "NO_AUTO_PROMOTION"
        capital_policy = "HOLD_OR_REDUCE"
        risk_policy = "REDUCED_RISK"
        next_experiment = "A/B test conservador em paper antes de promover qualquer ajuste."
        reasons.append("Estratégia ainda não merece expansão; permitir apenas testes pequenos e filtrados.")
    elif "EXPERIMENTAL" in advisor_action or str(advisor_item.get("category") or "").upper() == "EXPERIMENTAL":
        action = "KEEP_EXPERIMENT_SMALL"
        evolution_state = "EXPERIMENTAL_CAPPED"
        parameter_policy = "RUN_PAPER_EXPERIMENTS_ONLY"
        deployment_policy = "PROMOTE_ONLY_AFTER_SAMPLE"
        capital_policy = "CAP_EXPERIMENTAL_ALLOCATION"
        risk_policy = "CAP_EXPERIMENTAL_RISK"
        next_experiment = "Acumular amostra antes de liberar aumento de lote."
        reasons.append("Estratégia experimental com teto rígido até haver amostra suficiente.")

    if trades and trades < 10:
        reasons.append("Amostra estatística ainda baixa; evitar conclusões definitivas.")
        if action == "PROMOTE_OR_MAINTAIN_LEADER":
            parameter_policy = "MAINTAIN_BUT_WAIT_MORE_SAMPLE"
    if win is not None and win < 30 and trades >= 5:
        reasons.append("Win rate baixo com alguma amostra; revisar setup antes de promover.")
    if pnl < -2:
        reasons.append("PnL acumulado negativo; reduzir agressividade até recuperação estatística.")
    if delta_pct < -5:
        reasons.append("Optimizer sugere retirada relevante de capital; estratégia deve perder prioridade.")
    if evaluations < 10:
        reasons.append("Learning/Outcome ainda em bootstrap; Strategy Evolution V1 não aplica mudanças automáticas.")

    # Simple evolutionary score: quality + meta priority + capital delta, penalized by defensive states.
    evo_score = score * 0.55 + min(max(priority_score, 0.0), 100.0) * 0.25 + max(min(delta_pct + 20, 40), 0) * 0.5
    if action == "DEMOTE_OR_FREEZE_STRATEGY":
        evo_score = min(evo_score, 35.0)
    if action == "REVIEW_AND_REQUIRE_STRONG_CONFIRMATION":
        evo_score = min(evo_score, 55.0)
    if action == "KEEP_EXPERIMENT_SMALL":
        evo_score = min(evo_score, 65.0)
    evo_score = round(evo_score, 2)

    return {
        "bot": bot_name,
        "category": advisor_item.get("category"),
        "strategy_family": _see_bot_family_from_meta(meta_item, bot_name),
        "strategy_cluster": meta_item.get("strategy_cluster"),
        "score": score,
        "trades": trades,
        "win_rate_pct": win,
        "pnl_total_pct": pnl,
        "advisor_action": advisor_action,
        "optimizer_recommendation": optimizer_rec,
        "risk_state": risk_state,
        "meta_gate": meta_gate,
        "signal_gate": signal_gate,
        "target_pct": target_pct,
        "current_pct": current_pct,
        "delta_pct": delta_pct,
        "evolution_score": evo_score,
        "evolution_state": evolution_state,
        "evolution_action": action,
        "parameter_policy": parameter_policy,
        "deployment_policy": deployment_policy,
        "capital_policy": capital_policy,
        "risk_policy": risk_policy,
        "next_experiment": next_experiment,
        "auto_apply_allowed": False,
        "human_report_required": False,
        "reasons": reasons[:8],
    }


def build_strategy_evolution_engine_v1(capital=10000.0, persist=False):
    global STRATEGY_EVOLUTION_ENGINE_V1_CACHE
    capital = _see_safe_float(capital, 10000.0)
    alerts = []
    errors = []

    try:
        advisor_payload = build_portfolio_advisor_v1(capital=capital)
    except Exception as exc:
        advisor_payload = {"ranking": []}
        errors.append(f"Advisor indisponível: {exc}")
    try:
        optimizer_payload = build_portfolio_optimizer_v1_1(capital=capital)
    except Exception as exc:
        optimizer_payload = {"optimized_allocation": []}
        errors.append(f"Optimizer indisponível: {exc}")
    try:
        risk_payload = build_dynamic_risk_budget_v1(capital=capital)
    except Exception as exc:
        risk_payload = {"budgets": []}
        errors.append(f"Risk Budget indisponível: {exc}")
    try:
        meta_payload = build_meta_strategy_engine_v1_1(capital=capital)
    except Exception as exc:
        meta_payload = {"strategies": []}
        errors.append(f"Meta Strategy indisponível: {exc}")
    try:
        market_payload = build_market_regime_detector_v1(capital=capital)
    except Exception as exc:
        market_payload = {}
        errors.append(f"Market Regime indisponível: {exc}")
    try:
        corr_payload = build_correlation_engine_v1(capital=capital)
    except Exception as exc:
        corr_payload = {}
        errors.append(f"Correlation Engine indisponível: {exc}")

    outcome_stats = _see_get_outcome_stats()
    analytics_by_bot = _see_get_trade_stats_by_bot()

    strategies = []
    for item in advisor_payload.get("ranking") or []:
        bot = str(item.get("bot") or "").upper().strip()
        if not bot:
            continue
        merged = dict(item)
        if bot in analytics_by_bot:
            for k, v in analytics_by_bot[bot].items():
                merged.setdefault(k, v)
        evo = _see_evolution_decision(
            bot,
            merged,
            _see_find_optimizer_item(optimizer_payload, bot),
            _see_find_risk_budget_item(risk_payload, bot),
            _see_find_meta_item(meta_payload, bot),
            outcome_stats,
        )
        strategies.append(evo)

    strategies = sorted(strategies, key=lambda x: (_see_safe_float(x.get("evolution_score"), 0), _see_safe_float(x.get("score"), 0)), reverse=True)

    counts = {
        "total": len(strategies),
        "leaders": len([x for x in strategies if x.get("evolution_action") == "PROMOTE_OR_MAINTAIN_LEADER"]),
        "watchlist": len([x for x in strategies if x.get("evolution_action") == "REVIEW_AND_REQUIRE_STRONG_CONFIRMATION"]),
        "experimental": len([x for x in strategies if x.get("evolution_action") == "KEEP_EXPERIMENT_SMALL"]),
        "defensive": len([x for x in strategies if x.get("evolution_action") == "DEMOTE_OR_FREEZE_STRATEGY"]),
    }

    top_strategy = strategies[0] if strategies else None
    evolution_ready = False
    auto_apply_ready = False
    evaluations = _see_safe_int(outcome_stats.get("evaluations") or outcome_stats.get("outcomes") or 0, 0)
    if evaluations >= 50:
        evolution_ready = True
    if evaluations >= 200:
        auto_apply_ready = True

    if not strategies:
        alerts.append("Strategy Evolution não recebeu estratégias do Advisor; manter modo defensivo.")
    if evaluations < 10:
        alerts.append("Learning/Outcome ainda em bootstrap; não aplicar evolução automática.")
    if counts.get("defensive"):
        alerts.append(f"{counts.get('defensive')} estratégia(s) em revisão/defensivo; bloquear promoção automática.")
    if top_strategy:
        alerts.append(f"Estratégia líder atual para preservação/evolução: {top_strategy.get('bot')}.")

    payload = {
        "ok": True,
        "version": STRATEGY_EVOLUTION_ENGINE_V1_VERSION,
        "generated_at": data_hora_sp_str(),
        "mode": STRATEGY_EVOLUTION_ENGINE_V1_MODE,
        "capital": capital,
        "machine_first": True,
        "human_report_required": False,
        "evolution_ready": evolution_ready,
        "auto_apply_ready": auto_apply_ready,
        "auto_apply_allowed": False,
        "counts": counts,
        "top_strategy": top_strategy,
        "strategies": strategies,
        "market_context": {
            "regime": market_payload.get("regime"),
            "regime_family": market_payload.get("regime_family"),
            "confidence": market_payload.get("confidence"),
            "source": market_payload.get("source"),
        },
        "correlation_context": {
            "dominant_cluster": ((corr_payload.get("automation_policy") or {}).get("dominant_cluster")),
            "dominant_cluster_severity": ((corr_payload.get("automation_policy") or {}).get("dominant_cluster_severity")),
            "compressed_clusters": ((corr_payload.get("automation_policy") or {}).get("compressed_clusters")),
        },
        "learning_context": {
            "evaluations": evaluations,
            "min_for_active_evolution": 50,
            "min_for_auto_apply": 200,
            "decision_accuracy_pct": outcome_stats.get("decision_accuracy_pct"),
            "by_module": outcome_stats.get("by_module"),
        },
        "automation_policy": {
            "route": "MARKET_REGIME_META_CORRELATION_DECISION_THEN_STRATEGY_EVOLUTION_FEEDBACK",
            "strategy_evolution_ready": True,
            "auto_parameter_changes_allowed": False,
            "auto_deploy_allowed": False,
            "allowed_actions_now": ["RANK_STRATEGIES", "FREEZE_DEFENSIVE", "PROPOSE_EXPERIMENTS", "PROTECT_LEADERS"],
            "blocked_actions": ["AUTO_DEPLOY_CODE", "AUTO_CHANGE_REAL_RISK", "PROMOTE_WITHOUT_OUTCOMES", "BYPASS_DECISION_ENGINE"],
        },
        "alerts": alerts,
        "errors": errors,
        "notes": [
            "Strategy Evolution Engine V1 é machine-first e não depende de relatório humano.",
            "V1 não altera código, parâmetros, risco real, lote ou deploy; apenas classifica estratégias para evolução futura.",
            "Usa Advisor, Optimizer, Risk Budget, Meta Strategy, Market Regime, Correlation e outcomes avaliados.",
            "Mudanças automáticas ficam bloqueadas até haver amostra suficiente de outcomes e integração com OMS/Executor.",
        ],
    }

    if persist:
        saved, err = _see_append_jsonl({"record_type": "STRATEGY_EVOLUTION_SNAPSHOT", **payload})
        payload["state_saved"] = saved
        payload["state_save_error"] = err
    else:
        payload["state_saved"] = False

    STRATEGY_EVOLUTION_ENGINE_V1_CACHE = {"last_generated_at": payload.get("generated_at"), "last_capital": capital}
    return payload


def build_strategy_evolution_engine_v1_text(capital=10000.0, persist=False):
    payload = build_strategy_evolution_engine_v1(capital=capital, persist=persist)
    market = payload.get("market_context") or {}
    corr = payload.get("correlation_context") or {}
    learn = payload.get("learning_context") or {}
    counts = payload.get("counts") or {}
    top = payload.get("top_strategy") or {}
    lines = [
        "🧬 STRATEGY EVOLUTION ENGINE V1 — CENTRAL QUANT",
        f"Data/hora: {payload.get('generated_at')}",
        f"Versão: {payload.get('version')}",
        f"Modo: {payload.get('mode')}",
        "",
        "Estado autônomo:",
        f"Evolution ready: {payload.get('evolution_ready')} | Auto apply ready: {payload.get('auto_apply_ready')} | Auto apply allowed: {payload.get('auto_apply_allowed')}",
        f"Human report required: {payload.get('human_report_required')}",
        f"Regime: {market.get('regime')} | Família: {market.get('regime_family')} | Confiança: {market.get('confidence')}",
        f"Cluster dominante: {corr.get('dominant_cluster')} | Severidade: {corr.get('dominant_cluster_severity')}",
        f"Outcomes avaliados: {learn.get('evaluations')} | mínimo evolução ativa: {learn.get('min_for_active_evolution')} | mínimo auto-apply: {learn.get('min_for_auto_apply')}",
        "",
        "Contagem:",
        f"Total: {counts.get('total')} | Leaders: {counts.get('leaders')} | Watchlist: {counts.get('watchlist')} | Experimental: {counts.get('experimental')} | Defensive: {counts.get('defensive')}",
        "",
    ]
    if top:
        lines += [
            "Estratégia líder:",
            f"{top.get('bot')} — {top.get('evolution_action')} | estado: {top.get('evolution_state')} | score evolução: {top.get('evolution_score')}",
            f"Política: parâmetros={top.get('parameter_policy')} | deploy={top.get('deployment_policy')} | risco={top.get('risk_policy')}",
            "",
        ]
    lines.append("Estratégias:")
    for i, item in enumerate(payload.get("strategies") or [], start=1):
        lines += [
            f"{i}. {item.get('bot')} — {item.get('evolution_action')} | {item.get('evolution_state')} | evo_score={item.get('evolution_score')}",
            f"Família: {item.get('strategy_family')} | Cluster: {item.get('strategy_cluster')} | Score: {item.get('score')} | Trades: {item.get('trades')}",
            f"Advisor: {item.get('advisor_action')} | Risk: {item.get('risk_state')} | Meta: {item.get('meta_gate')}",
            f"Target: {item.get('target_pct')}% | Atual: {item.get('current_pct')}% | Δ {item.get('delta_pct')}%",
            f"Políticas: capital={item.get('capital_policy')} | risco={item.get('risk_policy')} | parâmetros={item.get('parameter_policy')}",
        ]
        reasons = item.get("reasons") or []
        if reasons:
            lines.append("Motivos:")
            for r in reasons[:5]:
                lines.append(f"- {r}")
        lines.append("")
    lines.append("Alertas:")
    for a in payload.get("alerts") or []:
        lines.append(f"- {a}")
    if payload.get("errors"):
        lines.append("")
        lines.append("Erros upstream:")
        for e in payload.get("errors") or []:
            lines.append(f"- {e}")
    lines.append("")
    lines.append("Notas:")
    for n in payload.get("notes") or []:
        lines.append(f"- {n}")
    return "\n".join(lines), payload


@app.route("/strategy/evolution/v1", methods=["GET", "POST"])
@app.route("/evolution/strategy/v1", methods=["GET", "POST"])
@app.route("/strategy-evolution/v1", methods=["GET", "POST"])
def strategy_evolution_engine_v1_route():
    body = request.get_json(silent=True) or {}
    capital = _see_safe_float(body.get("capital") or request.args.get("capital"), 10000.0)
    persist_raw = body.get("persist", request.args.get("persist", ""))
    persist = str(persist_raw).strip().lower() in {"1", "true", "yes", "sim", "on", "save"}
    text, payload = build_strategy_evolution_engine_v1_text(capital=capital, persist=persist)
    return {"ok": True, "payload": payload, "text": text}


@app.route("/strategy/evolution/summary/v1", methods=["GET", "POST"])
@app.route("/strategy-evolution/summary/v1", methods=["GET", "POST"])
def strategy_evolution_engine_v1_summary_route():
    body = request.get_json(silent=True) or {}
    capital = _see_safe_float(body.get("capital") or request.args.get("capital"), 10000.0)
    payload = build_strategy_evolution_engine_v1(capital=capital, persist=False)
    return {
        "ok": True,
        "version": payload.get("version"),
        "generated_at": payload.get("generated_at"),
        "mode": payload.get("mode"),
        "evolution_ready": payload.get("evolution_ready"),
        "auto_apply_ready": payload.get("auto_apply_ready"),
        "counts": payload.get("counts"),
        "top_strategy": payload.get("top_strategy"),
        "market_context": payload.get("market_context"),
        "correlation_context": payload.get("correlation_context"),
        "learning_context": payload.get("learning_context"),
        "automation_policy": payload.get("automation_policy"),
        "alerts": payload.get("alerts"),
    }




# ==========================================================
# TRADE LIFECYCLE MANAGER V1 - CENTRAL QUANT
# ==========================================================

TRADE_LIFECYCLE_MANAGER_V1_VERSION = "2026-07-04-TRADE-LIFECYCLE-MANAGER-V1"
TRADE_LIFECYCLE_MANAGER_V1_MODE = "OBSERVATION_ONLY"
TRADE_LIFECYCLE_MANAGER_V1_FILE = CENTRAL_DATA_DIR / "trade_lifecycle_manager_v1.jsonl"
TRADE_LIFECYCLE_MANAGER_V1_CACHE = {"last_generated_at": None, "last_trade_id": None}


def _tlm_safe_float(value, default=None):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _tlm_safe_int(value, default=0):
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except Exception:
        return default


def _tlm_round(value, ndigits=4):
    try:
        return round(float(value), ndigits)
    except Exception:
        return value


def _tlm_norm_symbol(value):
    try:
        return normalize_registry_symbol(value)
    except Exception:
        return str(value or "").upper().replace("/USDT:USDT", "USDT").replace("/", "").strip()


def _tlm_norm_side(value):
    s = str(value or "").upper().strip()
    if s == "BUY":
        return "LONG"
    if s == "SELL":
        return "SHORT"
    return s


def _tlm_norm_bot(value):
    try:
        return normalize_registry_bot(value)
    except Exception:
        return str(value or "").upper().strip()


def _tlm_trade_id(trade):
    if not isinstance(trade, dict):
        return None
    return (
        trade.get("trade_id")
        or trade.get("id")
        or trade.get("uid")
        or trade.get("decision_id")
        or f"{_tlm_norm_bot(trade.get('bot'))}:{_tlm_norm_symbol(trade.get('symbol') or trade.get('symbol_clean'))}:{_tlm_norm_side(trade.get('side'))}:{trade.get('setup') or ''}:{trade.get('entry') or trade.get('entry_price') or ''}"
    )


def _tlm_trade_symbol(trade):
    return _tlm_norm_symbol((trade or {}).get("symbol_clean") or (trade or {}).get("symbol") or (trade or {}).get("ativo") or (trade or {}).get("pair"))


def _tlm_trade_side(trade):
    return _tlm_norm_side((trade or {}).get("side") or (trade or {}).get("direction"))


def _tlm_trade_entry(trade):
    return _tlm_safe_float((trade or {}).get("entry") or (trade or {}).get("entry_price") or (trade or {}).get("preco_entrada"), None)


def _tlm_trade_stop(trade):
    return _tlm_safe_float((trade or {}).get("stop") or (trade or {}).get("sl") or (trade or {}).get("stop_loss"), None)


def _tlm_trade_tp50(trade):
    return _tlm_safe_float((trade or {}).get("tp50") or (trade or {}).get("take_profit_50") or (trade or {}).get("tp_50"), None)


def _tlm_append_jsonl(item):
    try:
        TRADE_LIFECYCLE_MANAGER_V1_FILE.parent.mkdir(exist_ok=True)
        with open(TRADE_LIFECYCLE_MANAGER_V1_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
        return True, None
    except Exception as exc:
        return False, str(exc)


def _tlm_read_records(limit=1000):
    records = []
    try:
        if not TRADE_LIFECYCLE_MANAGER_V1_FILE.exists():
            return []
        with open(TRADE_LIFECYCLE_MANAGER_V1_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()[-int(limit or 1000):]
        for line in lines:
            try:
                item = json.loads(line)
            except Exception:
                continue
            if isinstance(item, dict):
                records.append(item)
    except Exception:
        return records
    return records


def _tlm_registry_snapshot_light():
    snap = central_trade_registry_snapshot(include_trades=True)
    open_trades = snap.get("open_trades") or []
    closed_trades = snap.get("closed_trades") or []
    if not isinstance(open_trades, list):
        open_trades = []
    if not isinstance(closed_trades, list):
        closed_trades = []
    return snap, [x for x in open_trades if isinstance(x, dict)], [x for x in closed_trades if isinstance(x, dict)]


def _tlm_find_trade(trades, trade_id=None, bot=None, symbol=None, side=None):
    trade_id = str(trade_id or "").strip()
    bot_n = _tlm_norm_bot(bot)
    symbol_n = _tlm_norm_symbol(symbol)
    side_n = _tlm_norm_side(side)
    for t in trades or []:
        if trade_id and str(_tlm_trade_id(t) or "") == trade_id:
            return t
    for t in trades or []:
        if bot_n and _tlm_norm_bot(t.get("bot")) != bot_n:
            continue
        if symbol_n and _tlm_trade_symbol(t) != symbol_n:
            continue
        if side_n and _tlm_trade_side(t) != side_n:
            continue
        return t
    return None


def _tlm_pnl_from_closed_trade(trade):
    if not isinstance(trade, dict):
        return {"pnl_pct": None, "result_r": None, "outcome": "UNKNOWN"}
    pnl_pct = _tlm_safe_float(trade.get("pnl_pct") or trade.get("pnl_percent") or trade.get("resultado_pct"), None)
    result_r = _tlm_safe_float(trade.get("r") or trade.get("result_r") or trade.get("r_multiple") or trade.get("pnl_r"), None)
    outcome = str(trade.get("outcome") or trade.get("result") or trade.get("status_result") or "").upper().strip()
    if outcome not in {"WIN", "LOSS", "BE"}:
        try:
            outcome = _le_normalize_outcome(outcome=None, result_r=result_r, pnl_pct=pnl_pct)
        except Exception:
            if result_r is not None:
                outcome = "WIN" if result_r > 0.05 else ("LOSS" if result_r < -0.05 else "BE")
            elif pnl_pct is not None:
                outcome = "WIN" if pnl_pct > 0.02 else ("LOSS" if pnl_pct < -0.02 else "BE")
            else:
                outcome = "UNKNOWN"
    return {"pnl_pct": pnl_pct, "result_r": result_r, "outcome": outcome}


def _tlm_open_trade_lifecycle_state(trade):
    symbol = _tlm_trade_symbol(trade)
    side = _tlm_trade_side(trade)
    entry = _tlm_trade_entry(trade)
    stop = _tlm_trade_stop(trade)
    tp50 = _tlm_trade_tp50(trade)
    runner_pct = _tlm_safe_float(trade.get("runner_pct") or trade.get("open_pnl_pct") or trade.get("pnl_pct"), 0.0) or 0.0
    runner_r = _tlm_safe_float(trade.get("runner_r") or trade.get("open_pnl_r") or trade.get("r"), 0.0) or 0.0
    flags = []
    if _tlm_safe_float(trade.get("tp50_hit"), None) or str(trade.get("status") or "").upper().find("TP50") >= 0:
        flags.append("TP50_REACHED")
    if _tlm_safe_float(trade.get("breakeven"), None) or str(trade.get("status") or "").upper().find("BE") >= 0:
        flags.append("BREAKEVEN_ACTIVE")
    if _tlm_safe_float(trade.get("trailing"), None) or str(trade.get("status") or "").upper().find("TRAIL") >= 0:
        flags.append("TRAILING_ACTIVE")
    if runner_r >= 1:
        flags.append("RUNNER_1R_PLUS")
    if runner_r >= 2:
        flags.append("RUNNER_2R_PLUS")
    state = "OPEN_TRACKING"
    if "TRAILING_ACTIVE" in flags:
        state = "OPEN_TRAILING"
    elif "BREAKEVEN_ACTIVE" in flags:
        state = "OPEN_BREAKEVEN"
    elif "TP50_REACHED" in flags:
        state = "OPEN_AFTER_TP50"
    return {
        "trade_id": _tlm_trade_id(trade),
        "bot": _tlm_norm_bot(trade.get("bot")),
        "setup": trade.get("setup"),
        "symbol": symbol,
        "side": side,
        "entry": entry,
        "stop": stop,
        "tp50": tp50,
        "state": state,
        "runner_pct": _tlm_round(runner_pct, 4),
        "runner_r": _tlm_round(runner_r, 4),
        "flags": flags,
        "needs_outcome": False,
    }


def _tlm_closed_trade_lifecycle_state(trade, learning_records=None, outcome_records=None):
    pnl = _tlm_pnl_from_closed_trade(trade)
    tid = _tlm_trade_id(trade)
    matching_learning = None
    matching_outcome = None
    for r in reversed(learning_records or []):
        if str(r.get("trade_id") or "") == str(tid):
            matching_learning = r
            break
    for r in reversed(outcome_records or []):
        if str(r.get("trade_id") or "") == str(tid):
            matching_outcome = r
            break
    return {
        "trade_id": tid,
        "bot": _tlm_norm_bot(trade.get("bot")),
        "setup": trade.get("setup"),
        "symbol": _tlm_trade_symbol(trade),
        "side": _tlm_trade_side(trade),
        "entry": _tlm_trade_entry(trade),
        "stop": _tlm_trade_stop(trade),
        "exit": _tlm_safe_float(trade.get("exit") or trade.get("exit_price") or trade.get("close_price"), None),
        "state": "CLOSED_PENDING_OUTCOME" if not matching_outcome else "CLOSED_EVALUATED",
        "outcome": pnl.get("outcome"),
        "result_r": pnl.get("result_r"),
        "pnl_pct": pnl.get("pnl_pct"),
        "learning_id": matching_learning.get("learning_id") if matching_learning else None,
        "outcome_evaluation_id": matching_outcome.get("evaluation_id") if matching_outcome else None,
        "needs_outcome": not bool(matching_outcome),
    }


def build_trade_lifecycle_manager_v1(capital=10000.0, bot=None, symbol=None, side=None, entry=None, stop=None, setup=None, leverage=None, trade_id=None, record_decision=False, evaluate_closed=False, persist=False):
    """
    Machine-first lifecycle layer.
    It does not execute. It connects: signal/decision -> registry -> close -> outcome -> learning.
    """
    global TRADE_LIFECYCLE_MANAGER_V1_CACHE
    generated_at = data_hora_sp_str()
    alerts = []
    errors = []
    actions = []

    snap, open_trades, closed_trades = _tlm_registry_snapshot_light()
    learning_records = _le_read_records(limit=max(LEARNING_ENGINE_V1_DEFAULT_READ_LIMIT, 5000)) if '_le_read_records' in globals() else []
    outcome_records = _oe_read_records(limit=5000) if '_oe_read_records' in globals() else []

    open_states = [_tlm_open_trade_lifecycle_state(t) for t in open_trades]
    closed_states = [_tlm_closed_trade_lifecycle_state(t, learning_records, outcome_records) for t in closed_trades[-50:]]
    pending_outcomes = [x for x in closed_states if x.get("needs_outcome")]

    # Optional signal decision registration.
    decision_payload = None
    decision_saved = False
    if bot or symbol or side or entry or stop:
        try:
            decision_payload = build_learning_engine_v1(
                capital=capital,
                bot=bot,
                symbol=symbol,
                side=side,
                entry=entry,
                stop=stop,
                setup=setup,
                leverage=leverage,
                record=bool(record_decision),
            )
            decision_saved = bool(decision_payload.get("record_saved"))
            if record_decision and decision_saved:
                actions.append("DECISION_RECORDED_FOR_LIFECYCLE")
            elif record_decision and not decision_saved:
                alerts.append("Learning decision foi solicitado, mas não foi salvo.")
        except Exception as exc:
            errors.append(f"decision_learning_error: {exc}")
            decision_payload = {"ok": False, "error": str(exc)}

    selected_open = _tlm_find_trade(open_trades, trade_id=trade_id, bot=bot, symbol=symbol, side=side)
    selected_closed = _tlm_find_trade(closed_trades, trade_id=trade_id, bot=bot, symbol=symbol, side=side)
    selected_trade_state = None
    if selected_open:
        selected_trade_state = _tlm_open_trade_lifecycle_state(selected_open)
    elif selected_closed:
        selected_trade_state = _tlm_closed_trade_lifecycle_state(selected_closed, learning_records, outcome_records)

    outcome_evaluation = None
    if evaluate_closed and selected_trade_state and selected_trade_state.get("state") == "CLOSED_PENDING_OUTCOME" and selected_trade_state.get("learning_id"):
        try:
            outcome_evaluation = build_outcome_evaluator_v1(
                learning_id=selected_trade_state.get("learning_id"),
                trade_id=selected_trade_state.get("trade_id"),
                outcome=selected_trade_state.get("outcome"),
                result_r=selected_trade_state.get("result_r"),
                pnl_pct=selected_trade_state.get("pnl_pct"),
                note="auto_from_trade_lifecycle_v1",
                save=True,
                force=True,
            )
            if outcome_evaluation.get("ok"):
                actions.append("OUTCOME_EVALUATED_FROM_CLOSED_TRADE")
            else:
                alerts.append(f"Outcome automático não aplicado: {outcome_evaluation.get('error') or outcome_evaluation.get('message')}")
        except Exception as exc:
            errors.append(f"outcome_auto_evaluation_error: {exc}")

    stats = {
        "open_trades": len(open_trades),
        "closed_trades": len(closed_trades),
        "open_tracking": len(open_states),
        "closed_evaluated": len([x for x in closed_states if x.get("state") == "CLOSED_EVALUATED"]),
        "closed_pending_outcome": len(pending_outcomes),
        "learning_records": len(learning_records or []),
        "outcome_evaluations": len([x for x in outcome_records if x.get("record_type") == "OUTCOME_EVALUATION"]),
    }

    if stats["closed_pending_outcome"]:
        alerts.append(f"{stats['closed_pending_outcome']} trade(s) fechado(s) ainda precisam de outcome avaliado.")
    if not open_trades and not closed_trades:
        alerts.append("Trade Registry sem trades; lifecycle fica em espera.")
    if decision_payload and decision_payload.get("adaptive_decision") in {"ALLOW", "REDUCE"} and not record_decision:
        alerts.append("Há decisão avaliável para sinal, mas ela não foi registrada. Use record_decision=true para lifecycle completo.")

    lifecycle_ready = bool(snap.get("ok"))
    learning_loop_ready = stats["outcome_evaluations"] > 0
    automation_policy = {
        "trade_lifecycle_ready": lifecycle_ready,
        "human_report_required": False,
        "route": "DECISION_SCORE_TO_LEARNING_TO_REGISTRY_TO_OUTCOME_TO_ADAPTIVE_WEIGHTS",
        "record_decisions_before_execution": True,
        "auto_outcome_evaluation_ready": True,
        "learning_loop_ready": learning_loop_ready,
        "blocked_actions": [
            "EXECUTE_WITHOUT_LIFECYCLE_RECORD",
            "CLOSE_WITHOUT_OUTCOME_EVALUATION",
            "BYPASS_LEARNING_FEEDBACK",
        ],
        "allowed_actions_now": [
            "TRACK_OPEN_TRADES",
            "LINK_DECISIONS_TO_TRADES",
            "EVALUATE_CLOSED_TRADES_WITH_KNOWN_OUTCOME",
            "FEED_OUTCOME_EVALUATOR",
        ],
    }

    payload = {
        "ok": True,
        "version": TRADE_LIFECYCLE_MANAGER_V1_VERSION,
        "generated_at": generated_at,
        "mode": TRADE_LIFECYCLE_MANAGER_V1_MODE,
        "capital": capital,
        "machine_first": True,
        "human_report_required": False,
        "registry": {
            "ok": snap.get("ok"),
            "open_count": snap.get("open_count"),
            "closed_count": snap.get("closed_count"),
            "by_bot": snap.get("by_bot"),
            "by_symbol": snap.get("by_symbol"),
            "by_side": snap.get("by_side"),
            "trade_registry_file": snap.get("trade_registry_file"),
        },
        "stats": stats,
        "selected_trade": selected_trade_state,
        "decision_context": decision_payload,
        "decision_saved": decision_saved,
        "outcome_evaluation": outcome_evaluation,
        "open_lifecycle_sample": open_states[:25],
        "closed_lifecycle_sample": closed_states[-25:],
        "pending_outcome_sample": pending_outcomes[:20],
        "automation_policy": automation_policy,
        "actions": actions,
        "alerts": alerts,
        "errors": errors,
        "notes": [
            "Trade Lifecycle Manager V1 é machine-first e não depende de relatório humano.",
            "V1 não executa ordens; ele conecta decisão, registro, acompanhamento, fechamento, outcome e aprendizado.",
            "Cada decisão executável deve gerar um learning_id antes da execução para permitir avaliação posterior.",
            "Trades fechados com resultado conhecido podem alimentar automaticamente Outcome Evaluator e Adaptive Weight Engine.",
        ],
    }

    if persist:
        saved, err = _tlm_append_jsonl({"record_type": "TRADE_LIFECYCLE_SNAPSHOT", **payload})
        payload["state_saved"] = saved
        payload["state_save_error"] = err
    else:
        payload["state_saved"] = False

    TRADE_LIFECYCLE_MANAGER_V1_CACHE = {"last_generated_at": generated_at, "last_trade_id": (selected_trade_state or {}).get("trade_id")}
    return payload


def build_trade_lifecycle_manager_v1_text(capital=10000.0, bot=None, symbol=None, side=None, entry=None, stop=None, setup=None, leverage=None, trade_id=None, record_decision=False, evaluate_closed=False, persist=False):
    payload = build_trade_lifecycle_manager_v1(
        capital=capital,
        bot=bot,
        symbol=symbol,
        side=side,
        entry=entry,
        stop=stop,
        setup=setup,
        leverage=leverage,
        trade_id=trade_id,
        record_decision=record_decision,
        evaluate_closed=evaluate_closed,
        persist=persist,
    )
    st = payload.get("stats") or {}
    reg = payload.get("registry") or {}
    auto = payload.get("automation_policy") or {}
    sel = payload.get("selected_trade") or {}
    dec = payload.get("decision_context") or {}
    lines = [
        "🔁 TRADE LIFECYCLE MANAGER V1 — CENTRAL QUANT",
        f"Data/hora: {payload.get('generated_at')}",
        f"Versão: {payload.get('version')}",
        f"Modo: {payload.get('mode')}",
        "",
        "Estado autônomo:",
        f"Lifecycle ready: {auto.get('trade_lifecycle_ready')} | Learning loop ready: {auto.get('learning_loop_ready')} | Human report required: {payload.get('human_report_required')}",
        f"Rota: {auto.get('route')}",
        "",
        "Registry:",
        f"Open: {reg.get('open_count')} | Closed: {reg.get('closed_count')} | arquivo: {reg.get('trade_registry_file')}",
        f"By bot: {reg.get('by_bot')}",
        "",
        "Lifecycle stats:",
        f"Open tracking: {st.get('open_tracking')} | Closed evaluated: {st.get('closed_evaluated')} | Pending outcome: {st.get('closed_pending_outcome')}",
        f"Learning records: {st.get('learning_records')} | Outcome evaluations: {st.get('outcome_evaluations')}",
        "",
    ]
    if sel:
        lines += [
            "Trade selecionado:",
            f"Trade ID: {sel.get('trade_id')}",
            f"Bot: {sel.get('bot')} | Setup: {sel.get('setup')} | Ativo: {sel.get('symbol')} | Side: {sel.get('side')}",
            f"Estado: {sel.get('state')} | Outcome: {sel.get('outcome')} | R: {sel.get('result_r')} | PnL%: {sel.get('pnl_pct')}",
            f"Learning ID: {sel.get('learning_id')} | Evaluation ID: {sel.get('outcome_evaluation_id')}",
            "",
        ]
    if dec:
        lines += [
            "Decisão/sinal avaliado:",
            f"Learning ID: {dec.get('learning_id')} | salvo: {dec.get('record_saved')} | modo: {dec.get('record_mode')}",
            f"Decision: {dec.get('adaptive_decision')} | Score: {dec.get('adaptive_decision_score')} | Hard deny: {dec.get('hard_deny')}",
            "",
        ]
    lines += ["Amostra de abertos:"]
    for t in payload.get("open_lifecycle_sample") or []:
        lines.append(f"- {t.get('bot')} {t.get('symbol')} {t.get('side')} | {t.get('state')} | R={t.get('runner_r')} | flags={','.join(t.get('flags') or []) or '-'}")
    lines += ["", "Pendentes de outcome:"]
    for t in payload.get("pending_outcome_sample") or []:
        lines.append(f"- {t.get('bot')} {t.get('symbol')} {t.get('side')} | trade_id={t.get('trade_id')} | outcome={t.get('outcome')} | learning={t.get('learning_id')}")
    lines += ["", "Ações:"]
    for a in payload.get("actions") or []:
        lines.append(f"- {a}")
    lines += ["", "Alertas:"]
    for a in payload.get("alerts") or []:
        lines.append(f"- {a}")
    if payload.get("errors"):
        lines += ["", "Erros:"]
        for e in payload.get("errors") or []:
            lines.append(f"- {e}")
    lines += ["", "Notas:"]
    for n in payload.get("notes") or []:
        lines.append(f"- {n}")
    return "\n".join(lines), payload


@app.route("/trade/lifecycle/v1", methods=["GET", "POST"])
@app.route("/lifecycle/trade/v1", methods=["GET", "POST"])
@app.route("/trade-lifecycle/v1", methods=["GET", "POST"])
def trade_lifecycle_manager_v1_route():
    body = request.get_json(silent=True) or {}
    def arg(name, default=None):
        return body.get(name, request.args.get(name, default))
    capital = _tlm_safe_float(arg("capital"), 10000.0)
    bot = arg("bot")
    symbol = arg("symbol")
    side = arg("side")
    entry = _tlm_safe_float(arg("entry"), None)
    stop = _tlm_safe_float(arg("stop"), None)
    setup = arg("setup")
    leverage = _tlm_safe_float(arg("leverage"), None)
    trade_id = arg("trade_id")
    record_decision = str(arg("record_decision", arg("record", ""))).lower() in {"1", "true", "yes", "sim", "on", "save"}
    evaluate_closed = str(arg("evaluate_closed", arg("evaluate", ""))).lower() in {"1", "true", "yes", "sim", "on"}
    persist = str(arg("persist", "")).lower() in {"1", "true", "yes", "sim", "on", "save"}
    text, payload = build_trade_lifecycle_manager_v1_text(
        capital=capital,
        bot=bot,
        symbol=symbol,
        side=side,
        entry=entry,
        stop=stop,
        setup=setup,
        leverage=leverage,
        trade_id=trade_id,
        record_decision=record_decision,
        evaluate_closed=evaluate_closed,
        persist=persist,
    )
    return {"ok": True, "payload": payload, "text": text}


@app.route("/trade/lifecycle/summary/v1", methods=["GET", "POST"])
@app.route("/trade-lifecycle/summary/v1", methods=["GET", "POST"])
def trade_lifecycle_manager_v1_summary_route():
    body = request.get_json(silent=True) or {}
    capital = _tlm_safe_float(body.get("capital") or request.args.get("capital"), 10000.0)
    payload = build_trade_lifecycle_manager_v1(capital=capital)
    return {
        "ok": True,
        "version": payload.get("version"),
        "generated_at": payload.get("generated_at"),
        "mode": payload.get("mode"),
        "registry": payload.get("registry"),
        "stats": payload.get("stats"),
        "automation_policy": payload.get("automation_policy"),
        "alerts": payload.eget("alerts"),
    }



start_central_runtime_once()

if __name__ == "__main__":
    porta = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=porta)
