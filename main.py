# CENTRAL QUANT PRO FULL - SUPERVISOR MODULAR
# Versão: 2026-06-29-SUPER-CENTRAL-QUANT-V4-7-FORCE-HISTORY-V2
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
from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import deque
from flask import Flask, request

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
CENTRAL_DAILY_REPORT_MODE = os.environ.get("CENTRAL_DAILY_REPORT_MODE", "executivo").strip().lower()

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
CENTRAL_DATA_DIR = BASE_DIR / "data"
CENTRAL_DATA_DIR.mkdir(exist_ok=True)
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
    total = 0
    longs = 0
    shorts = 0
    by_bot = {}
    open_runner_buckets = _empty_runner_buckets()
    best_open_runner = None

    for key, module in LOADED_BOTS.items():
        memory_profile_step(f"before_exposure_bot_{key}")
        positions = get_open_positions_from_module(module, key=key)
        bot_longs = 0
        bot_shorts = 0
        bot_buckets = _empty_runner_buckets()
        bot_best_runner = None

        for p in positions:
            side = str(p.get("side", p.get("direction", ""))).upper()
            if side in {"LONG", "BUY"}:
                longs += 1
                bot_longs += 1
            elif side in {"SHORT", "SELL"}:
                shorts += 1
                bot_shorts += 1

            runner_r = _position_runner_r(p)
            runner_pct = _position_runner_pct(p)
            _update_runner_buckets(open_runner_buckets, runner_r)
            _update_runner_buckets(bot_buckets, runner_r)

            runner_payload = {
                "bot": key,
                "symbol": p.get("symbol") or p.get("ativo") or p.get("pair"),
                "setup": p.get("setup") or p.get("setup_label"),
                "side": side,
                "runner_r": round(runner_r, 4),
                "runner_pct": round(runner_pct, 4),
                "entry": p.get("entry") or p.get("entrada"),
                "stop": p.get("stop") or p.get("sl") or p.get("stop_atual"),
                "tp50": p.get("tp50"),
            }

            if bot_best_runner is None or runner_r > bot_best_runner.get("runner_r", 0):
                bot_best_runner = dict(runner_payload)
            if best_open_runner is None or runner_r > best_open_runner.get("runner_r", 0):
                best_open_runner = dict(runner_payload)

        total += len(positions)
        by_bot[key] = {
            "total": len(positions),
            "long": bot_longs,
            "short": bot_shorts,
            "open_runners": bot_buckets,
            "best_open_runner": bot_best_runner,
        }
        memory_profile_step(f"after_exposure_bot_{key}")

    result = {
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


@app.route("/")
def home():
    return f"{BOT_NAME} Online"


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


@app.route("/health")
def health():
    return central_watchdog_status()


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


@app.route("/memory")
@app.route("/memoria")
@app.route("/memória")
def memory_route():
    text, payload = build_memory_text(run_gc=False)
    payload["text"] = text
    return payload


@app.route("/memory/gc")
@app.route("/memoria/gc")
def memory_gc_route():
    text, payload = build_memory_text(run_gc=True)
    payload["text"] = text
    return payload


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


def append_decision_log(payload, decision_result):
    payload = payload or {}
    result = decision_result or {}
    bot = str(result.get("bot") or payload.get("bot") or "").upper()
    symbol = normalize_symbol_for_risk(result.get("symbol") or payload.get("symbol"))
    side = str(result.get("side") or payload.get("side") or "").upper()
    trade_id = payload.get("trade_id") or payload.get("client_trade_id") or generate_trade_id(bot, symbol, side)
    allowed = bool(result.get("allowed"))
    state = "VERIFY" if allowed and str(result.get("mode") or "").upper() == "VERIFY" else ("DENIED" if not allowed else str(result.get("mode") or "ALLOW").upper())
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
        "score": payload.get("score"),
        "setup": payload.get("setup"),
        "risk_pct": payload.get("risk_pct"),
        "notional_usdt": payload.get("notional_usdt"),
        "exposure": result.get("exposure") or {},
    }
    _append_jsonl(CENTRAL_DECISION_LOG_FILE, item)
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
    return _read_jsonl_tail(CENTRAL_DECISION_LOG_FILE, limit=limit)


def timeline_items(limit=100):
    return _read_jsonl_tail(CENTRAL_TIMELINE_LOG_FILE, limit=limit)


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
    for r in rows:
        reasons = r.get("reasons") or []
        warnings = r.get("warnings") or []
        lines.append(f"- {r.get('ts')} | {r.get('decision')} | {r.get('mode')} | {r.get('bot')} {r.get('symbol')} {r.get('side')} | score={r.get('score')} | risco={r.get('risk_pct')} | id={r.get('trade_id')}")
        if reasons:
            lines.append("  motivos: " + "; ".join(str(x) for x in reasons[:3]))
        if warnings:
            lines.append("  avisos: " + "; ".join(str(x) for x in warnings[:3]))
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
    bot = str(payload.get("bot") or payload.get("robot") or "").upper().strip()
    symbol = normalize_symbol_for_risk(payload.get("symbol"))
    side = str(payload.get("side") or "").upper().strip()
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
            append_decision_log(payload, decision_result)
        except Exception as exc:
            print("ERRO decision log:", exc)
        return decision_result

    if not bot:
        reasons.append("bot ausente")
    if bot and bot not in BOT_CONFIGS:
        reasons.append(f"bot inválido: {bot}")
    if symbol and REAL_TRADING_ALLOWED_SYMBOLS and symbol not in REAL_TRADING_ALLOWED_SYMBOLS:
        reasons.append(f"símbolo não liberado para real: {symbol}")

    # Hard blocks globais da Central, valem para PAPER/VERIFY/LIVE.
    if memory_risk.get("blocked"):
        reasons.append(
            f"memória acima do limite operacional: {memory_risk.get('usage_pct')}% >= {GLOBAL_RISK_MEMORY_BLOCK_PCT}%"
        )

    if GLOBAL_RISK_BLOCK_ON_PAPER_EXPOSURE and total_pos >= GLOBAL_RISK_MAX_POSITIONS:
        reasons.append(f"limite global Central/PAPER atingido: {total_pos}/{GLOBAL_RISK_MAX_POSITIONS}")

    if live_total_pos >= GLOBAL_RISK_MAX_POSITIONS:
        reasons.append(f"limite global LIVE atingido: {live_total_pos}/{GLOBAL_RISK_MAX_POSITIONS}")

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
    if total_pos >= max(1, int(GLOBAL_RISK_MAX_POSITIONS * 0.9)):
        warnings.append(f"exposição Central/PAPER alta: {total_pos}/{GLOBAL_RISK_MAX_POSITIONS}")
    if live_total_pos >= max(1, int(GLOBAL_RISK_MAX_POSITIONS * 0.9)):
        warnings.append(f"exposição LIVE alta: {live_total_pos}/{GLOBAL_RISK_MAX_POSITIONS}")
    if memory_risk.get("usage_pct") is not None and float(memory_risk.get("usage_pct")) >= MEMORY_ALERT_THRESHOLD_PCT:
        warnings.append(f"memória elevada: {memory_risk.get('usage_pct')}%")

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
        append_decision_log(payload, decision_result)
    except Exception as exc:
        print("ERRO decision log:", exc)
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


def build_risk_report():
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
        f"Health Score: {score.get('score')}/100 — {score.get('label')}",
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
            bloco.append("📈 QUALIDADE EXECUTIVA V2.0\nAmostra insuficiente hoje.\nAguardar trades encerrados.")

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


@app.route("/dashboard")
def dashboard_route():
    return {"text": build_dashboard_report()}


@app.route("/daily")
@app.route("/diario")
@app.route("/diário")
def daily_route():
    return {"text": build_daily_report()}


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


@app.route("/can_open_trade", methods=["GET", "POST"])
@app.route("/canopen", methods=["GET", "POST"])
def can_open_trade_route():
    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
    else:
        payload = dict(request.args)
    return can_open_trade_decision(payload)


@app.route("/risk")
@app.route("/riskmanager")
def risk_route():
    return {"text": build_risk_report()}


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


@app.route("/snapshot")
def snapshot_route():
    return {"text": build_snapshot_report()}


@app.route("/simulate")
@app.route("/simulate/<key>")
def simulate_route(key=None):
    return {"text": build_simulate_report(key)}


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
        "/history\n/riskstats\n/exporthistory\n/journal\n/trade <ativo>\n/globalstats\n/signalai <ativo>\n/capital\n/correlation\n/timeheat\n/marketscore\n/allocation\n/rankingvivo\n/evolution\n/learning\n/quantos\n/snapshot\n/history\n/simulate TURTLE\n/simulateoff TURTLE\n\n"
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
    if cmd0 in {"/daily", "/diario", "/diário"}:
        return build_daily_report()
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
        "/dashboard", "/daily", "/diario", "/diário", "/support",
        "/audit", "/auditoria", "/relatoriocompleto", "/relatorio_completo",
        "/full", "/trend", "/donkey", "/cobra", "/meme", "/predator", "/turtle", "/falcon",
        "/quantos", "/journal", "/trade", "/globalstats", "/signalai", "/capital",
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
    Envia relatório diário automático pelo Telegram exclusivo da Central.
    Usa os mesmos mecanismos de chunking do Telegram para evitar perder mensagens grandes.
    """
    global CENTRAL_DAILY_REPORT_SENT_DATE

    if not CENTRAL_DAILY_REPORT_ENABLED:
        print("RELATÓRIO DIÁRIO CENTRAL DESLIGADO POR ENV")
        return

    while True:
        try:
            now = agora_sp()
            current_hm = now.strftime("%H:%M")
            today = now.strftime("%Y-%m-%d")

            if current_hm == CENTRAL_DAILY_REPORT_TIME and CENTRAL_DAILY_REPORT_SENT_DATE != today:
                print(f"GERANDO RELATÓRIO DIÁRIO CENTRAL {today} {current_hm}")
                try:
                    save_daily_snapshot(label="auto")
                except Exception as exc:
                    print("ERRO SNAPSHOT RELATÓRIO DIÁRIO CENTRAL:", exc)

                mode = (CENTRAL_DAILY_REPORT_MODE or "executivo").strip().lower()
                if mode in {"completo", "full", "audit", "auditoria"}:
                    payload = build_audit_parts()
                    title = "RELATÓRIO DIÁRIO COMPLETO"
                elif mode in {"daily", "diario", "diário"}:
                    payload = build_daily_report()
                    title = "RELATÓRIO DIÁRIO"
                else:
                    payload = build_dashboard_report()
                    title = "DASHBOARD DIÁRIO"

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

        except Exception as exc:
            print("ERRO RELATÓRIO DIÁRIO CENTRAL:", exc)

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
        text, _payload = build_memory_text(run_gc=False)
        return text

    if cmd0 in {"/memorygc", "/memory_gc", "/memoriagc", "/memoria_gc"}:
        text, _payload = build_memory_text(run_gc=True)
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
        return build_daily_report()
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

@app.route("/journal")
@app.route("/journal/<arg>")
def journal_route(arg=None):
    return {"text": build_journal_report(arg)}


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


@app.route("/learning")
@app.route("/aprendizado")
def learning_route():
    return {"text": build_learning_report()}


@app.route("/quantos")
@app.route("/quantsystem")
def quantos_route():
    return {"text": build_quantos_report()}


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

    @app.route("/history/raw")
    def super_history_raw_route():
        return super_history_manager.build_history_payload()

    print("SUPER HISTORY MANAGER carregado com sucesso")

except Exception as exc:
    print("ERRO AO CARREGAR SUPER HISTORY MANAGER:", exc)

start_central_runtime_once()

if __name__ == "__main__":
    porta = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=porta)
