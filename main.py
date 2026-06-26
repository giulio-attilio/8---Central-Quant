# CENTRAL QUANT PRO FULL - SUPERVISOR MODULAR
# Versão: 2026-06-26-CENTRAL-SUPERVISOR-DASHBOARD-DAILY-AUDIT-FULL-CHUNKFIX
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
import gc
import threading
import requests
import importlib.util
import ctypes
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
GLOBAL_RISK_MAX_SIDE_CONCENTRATION_PCT = float(os.environ.get("GLOBAL_RISK_MAX_SIDE_CONCENTRATION_PCT", "80"))
GLOBAL_RISK_MAX_SYMBOL_EXPOSURE = int(os.environ.get("GLOBAL_RISK_MAX_SYMBOL_EXPOSURE", "3"))

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
REAL_TRADING_MAX_NOTIONAL_USDT = float(os.environ.get("REAL_TRADING_MAX_NOTIONAL_USDT", "10"))
REAL_TRADING_REQUIRE_READY = env_bool("REAL_TRADING_REQUIRE_READY", True)

DAILY_HISTORY_DIR = BASE_DIR / "daily_history"
DAILY_HISTORY_DIR.mkdir(exist_ok=True)
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
        parts.append("📊 RESUMO\n" + _short(resumo, 3000 if complete else 1200))

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
        "max_notional_usdt": REAL_TRADING_MAX_NOTIONAL_USDT,
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


def can_open_trade_decision(payload: dict):
    """
    Risk Manager decisório da Central.
    Retorna allow/deny para qualquer robô antes de abrir posição real.
    """
    payload = payload or {}
    bot = str(payload.get("bot") or payload.get("robot") or "").upper().strip()
    symbol = normalize_symbol_for_risk(payload.get("symbol"))
    side = str(payload.get("side") or "").upper().strip()
    mode = str(payload.get("mode") or payload.get("execution_mode") or EXECUTION_MODE).upper().strip()
    intended_live = bool(payload.get("intended_live", mode == "LIVE"))
    risk_pct = safe_round(payload.get("risk_pct"), 4, 0) or 0
    notional = safe_round(payload.get("notional_usdt"), 4, 0) or 0

    exposure_snapshot = central_exposure_snapshot()
    rows = _all_open_positions_payload()
    total_pos = int(exposure_snapshot.get("total_positions_open") or 0)
    long_pos = int(exposure_snapshot.get("long_positions_open") or 0)
    short_pos = int(exposure_snapshot.get("short_positions_open") or 0)

    reasons = []
    warnings = []

    if not bot:
        reasons.append("bot ausente")
    if bot and bot not in BOT_CONFIGS:
        reasons.append(f"bot inválido: {bot}")
    if symbol and REAL_TRADING_ALLOWED_SYMBOLS and symbol not in REAL_TRADING_ALLOWED_SYMBOLS:
        reasons.append(f"símbolo não liberado para real: {symbol}")
    if intended_live:
        if not ENABLE_REAL_TRADING:
            reasons.append("ENABLE_REAL_TRADING=false")
        if bot and bot not in REAL_TRADING_ALLOWED_BOTS:
            reasons.append(f"bot não liberado para real: {bot}")
        if REAL_TRADING_REQUIRE_READY:
            ready = bingx_ready_payload()
            if not ready.get("ok"):
                reasons.append(f"BingX não está READY: {ready.get('status') or ready.get('error')}")

    if total_pos >= GLOBAL_RISK_MAX_POSITIONS:
        reasons.append(f"limite global de posições atingido: {total_pos}/{GLOBAL_RISK_MAX_POSITIONS}")

    if symbol:
        same_symbol = [r for r in rows if normalize_symbol_for_risk(r.get("symbol")) == symbol]
        if len(same_symbol) >= GLOBAL_RISK_MAX_SYMBOL_EXPOSURE:
            reasons.append(f"limite por ativo atingido em {symbol}: {len(same_symbol)}/{GLOBAL_RISK_MAX_SYMBOL_EXPOSURE}")
        same_bot_symbol = [r for r in same_symbol if str(r.get("bot") or "").upper() == bot]
        if same_bot_symbol:
            reasons.append(f"{bot} já possui exposição em {symbol}")

    if side in {"LONG", "BUY"} and total_pos:
        next_long = long_pos + 1
        side_conc = next_long / max(total_pos + 1, 1) * 100
        if side_conc >= GLOBAL_RISK_MAX_SIDE_CONCENTRATION_PCT:
            reasons.append(f"concentração LONG ficaria {side_conc:.1f}%")
    if side in {"SHORT", "SELL"} and total_pos:
        next_short = short_pos + 1
        side_conc = next_short / max(total_pos + 1, 1) * 100
        if side_conc >= GLOBAL_RISK_MAX_SIDE_CONCENTRATION_PCT:
            reasons.append(f"concentração SHORT ficaria {side_conc:.1f}%")

    if risk_pct and risk_pct > REAL_TRADING_MAX_RISK_PCT:
        reasons.append(f"risco acima do máximo real: {risk_pct}% > {REAL_TRADING_MAX_RISK_PCT}%")
    if intended_live and notional and notional > REAL_TRADING_MAX_NOTIONAL_USDT:
        reasons.append(f"notional acima do máximo real: {notional} > {REAL_TRADING_MAX_NOTIONAL_USDT} USDT")

    # Avisos não bloqueantes.
    if total_pos >= max(1, int(GLOBAL_RISK_MAX_POSITIONS * 0.9)):
        warnings.append(f"exposição global alta: {total_pos}/{GLOBAL_RISK_MAX_POSITIONS}")

    allowed = len(reasons) == 0
    return {
        "allowed": allowed,
        "decision": "ALLOW" if allowed else "DENY",
        "bot": bot,
        "symbol": symbol,
        "side": side,
        "mode": mode,
        "intended_live": intended_live,
        "reasons": reasons,
        "warnings": warnings,
        "exposure": {
            "total": total_pos,
            "long": long_pos,
            "short": short_pos,
            "max_positions": GLOBAL_RISK_MAX_POSITIONS,
            "max_symbol_exposure": GLOBAL_RISK_MAX_SYMBOL_EXPOSURE,
        },
        "execution": broker_status_payload(),
    }


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
        f"Max notional real: {REAL_TRADING_MAX_NOTIONAL_USDT} USDT",
        f"Max risco real: {REAL_TRADING_MAX_RISK_PCT}%",
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

def build_risk_report():
    exposure_snapshot = central_exposure_snapshot()
    rows = _all_open_positions_payload()
    by_symbol = {}
    for r in rows:
        by_symbol.setdefault(r.get("symbol"), []).append(r)

    total_pos = int(exposure_snapshot.get("total_positions_open") or 0)
    long_pos = int(exposure_snapshot.get("long_positions_open") or 0)
    short_pos = int(exposure_snapshot.get("short_positions_open") or 0)
    notes = []
    blocks = []

    if total_pos >= GLOBAL_RISK_MAX_POSITIONS:
        blocks.append(f"Bloquear novas entradas: posições abertas {total_pos}/{GLOBAL_RISK_MAX_POSITIONS}.")
    if total_pos:
        side_conc = max(long_pos, short_pos) / max(total_pos, 1) * 100
        if side_conc >= GLOBAL_RISK_MAX_SIDE_CONCENTRATION_PCT:
            dominant = "SHORT" if short_pos >= long_pos else "LONG"
            notes.append(f"Concentração {dominant}: {side_conc:.1f}% ({max(long_pos, short_pos)}/{total_pos}).")
            blocks.append(f"Evitar novas entradas {dominant} até reduzir concentração.")

    repeated = []
    for sym, items in by_symbol.items():
        if len(items) >= GLOBAL_RISK_MAX_SYMBOL_EXPOSURE:
            repeated.append((sym, len(items), sorted(set([x.get("bot") for x in items]))))
            blocks.append(f"Evitar novas entradas em {sym}: {len(items)} exposições abertas.")

    lines = [
        "🛡️ RISK MANAGER GLOBAL — DECISIONAL",
        f"Data/hora: {data_hora_sp_str()}",
        "",
        f"Posições: {total_pos} | LONG {long_pos} | SHORT {short_pos}",
        f"Limite global sugerido: {GLOBAL_RISK_MAX_POSITIONS}",
        "",
        "Observações:",
    ]
    lines += [f"- {n}" for n in notes] if notes else ["- Nenhuma concentração crítica além dos parâmetros definidos."]

    if repeated:
        lines += ["", "Ativos repetidos:"]
        for sym, count, bots in repeated[:20]:
            lines.append(f"- {sym}: {count} posições | bots={','.join([str(b) for b in bots])}")

    lines += ["", "Recomendações consultivas:"]
    if blocks:
        lines += [f"- {b}" for b in blocks]
    else:
        lines.append("- Risco global dentro dos limites consultivos.")

    lines += [
        "",
        "Importante:",
        "Este Risk Manager já responde ALLOW/DENY em /can_open_trade. Para bloquear entradas reais, o robô precisa consultar esta rota antes de executar.",
    ]
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

def build_daily_report():
    """
    Pacote diário enxuto para colar no ChatGPT.
    Mantém o essencial: estado operacional, risco, memória, exposição e resumos dos bots.
    Evita selftest/diagnóstico completos e blocos repetidos para poupar memória/Telegram.
    """
    mem = memory_snapshot("daily_light_memory", store=True)
    status = central_watchdog_status()
    exposure_snapshot = central_exposure_snapshot()
    open_runners = exposure_snapshot.get("open_runners") or {}
    best = exposure_snapshot.get("best_open_runner") or {}

    header = [
        "📅 RELATÓRIO DIÁRIO CONSOLIDADO — CENTRAL QUANT",
        f"Data/hora: {data_hora_sp_str()}",
        "",
        "STATUS TÉCNICO",
        f"Central: {status.get('status')} | OK: {status.get('ok')}",
        f"Memória: {mem.get('rss_mb')} MB ({mem.get('usage_pct')}%) | Threads: {mem.get('threads')}",
        f"Motivos watchdog: {status.get('reasons', [])}",
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

    # Risco enxuto, sem heatmap grande.
    try:
        risk_txt = _short(build_risk_report(), 1800)
    except Exception as exc:
        risk_txt = f"Erro ao gerar risk: {exc}"

    try:
        ranking_txt = _short(build_ranking_report(), 1200)
    except Exception as exc:
        ranking_txt = f"Erro ao gerar ranking: {exc}"

    parts = [
        "\n".join(header),
        "==============================\nRISK\n==============================\n" + risk_txt,
        "==============================\nRANKING\n==============================\n" + ranking_txt,
        "==============================\nRESUMOS DOS BOTS\n==============================",
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

        # Limite menor por bot para evitar /daily de 5+ partes.
        parts.append(f"🤖 {key} — {cfg.get('name')}\n" + _short(resumo, 1400))

    text = "\n\n==============================\n".join(parts)
    force_gc_if_needed("daily_report_end", force=True)
    return text


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
        build_history_report(),
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
        ("HISTORY", build_history_report()),
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


@app.route("/support")
def support_route():
    return {"text": build_support_report()}


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


@app.route("/history")
def history_route():
    return {"text": build_history_report()}


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


def build_central_help_text():
    return (
        "🤖 CENTRAL QUANT — COMANDOS\n\n"
        "Pacotes principais:\n"
        "/dashboard — visão geral inteligente\n"
        "/daily — relatório diário enxuto para avaliação\n"
        "/support — troubleshooting técnico\n"
        "/audit — auditoria completa\n"
        "/full — dump completo com snapshot\n\n"
        "Operação:\n"
        "/executive\n/selftest\n/diagnostico\n/memory\n/execution\n/bingx\n/risk\n/heat\n/ranking\n/healthscore\n/meta\n/exposure\n/runners\n\n"
        "Relatórios:\n"
        "/relatorio — resumo central\n"
        "/relatoriocompleto — pacote completo sem espaço\n"
        "/auditoria — alias do relatório completo nativo\n\n"
        "Por robô:\n"
        "/trend\n/donkey\n/cobra\n/meme\n/predator\n/turtle\n/falcon\n\n"
        "Histórico e simulação:\n"
        "/snapshot\n/history\n/simulate TURTLE\n\n"
        "Sugestão de uso diário: /dashboard. Para colar no ChatGPT: /daily."
    )

def build_central_command_reply(text: str):
    raw = (text or "").strip()
    if not raw:
        return None
    cmd0 = raw.lower().split()[0].split("@")[0]

    if cmd0 in {"/start", "/help", "/comandos"}:
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
        return build_history_report()
    if cmd0 in {"/snapshot"}:
        return build_snapshot_report()
    if cmd0 in {"/simulate"}:
        parts = raw.split()
        return build_simulate_report(parts[1] if len(parts) > 1 else None)

    parsed_report = parse_report_command(raw)
    if parsed_report:
        mode, bot_key = parsed_report
        return build_central_report(mode, bot_key=bot_key)

    return None


def _central_command_title(text: str):
    cmd = (text or "").strip().lower().split()[0].split("@")[0] if text else ""
    mapping = {
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
    }
    return mapping.get(cmd, "CENTRAL QUANT")


def _is_heavy_central_command(text: str):
    cmd = (text or "").strip().lower().split()[0].split("@")[0] if text else ""
    return cmd in {
        "/dashboard", "/daily", "/diario", "/diário", "/support",
        "/audit", "/auditoria", "/relatoriocompleto", "/relatorio_completo",
        "/full", "/trend", "/donkey", "/cobra", "/meme", "/predator", "/turtle", "/falcon",
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
        return build_history_report()
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
        threading.Thread(target=central_command_router_loop, args=(key, cfg), daemon=True).start()


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
    threading.Thread(target=central_telegram_command_loop, daemon=True).start()
    threading.Thread(target=central_daily_report_loop, daemon=True).start()
    start_central_command_routers()


start_central_runtime_once()

if __name__ == "__main__":
    porta = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=porta)
