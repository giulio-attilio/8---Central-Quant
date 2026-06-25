# CENTRAL QUANT PRO FULL - SUPERVISOR MODULAR
# Versão: 2026-06-25-CENTRAL-FULL-RELATORIO-DIAGNOSTICO-SELFTEST-MEMORY-ROUTES-FIX
#
# Objetivo:
# - Rodar os robôs em um único serviço Render.
# - Preservar as lógicas originais dos arquivos enviados.
# - Evitar reescrever estratégias por aproximação.
# - Permitir ativação gradual por ENABLE_*.
# - Adicionar Turtle Breakout 2.0 como robô de pesquisa/paper.
# - Adicionar painel de runners abertos por R na Central.
#
# Importante:
# - Pause os serviços antigos no Render antes de ativar o mesmo bot aqui.
# - Se dois processos usarem o mesmo token Telegram com getUpdates, ocorre erro 409.
# - O Turtle aqui é apenas carregado como módulo em bots/turtle.py.
# - A execução real na BingX NÃO é feita pela Central.

import os
import time
import json
import threading
import gc
from collections import deque
import requests
import importlib.util
from pathlib import Path
from datetime import datetime, timezone, timedelta
from flask import Flask

app = Flask(__name__)

BOT_NAME = os.environ.get("BOT_NAME", "Central Quant PRO FULL")
TIMEZONE_BR = timezone(timedelta(hours=-3))
BASE_DIR = Path(__file__).resolve().parent
BOTS_DIR = BASE_DIR / "bots"

WATCHDOG_CHECK_SECONDS = int(os.environ.get("WATCHDOG_CHECK_SECONDS", "300"))
WATCHDOG_THRESHOLD_MINUTES = int(os.environ.get("WATCHDOG_THRESHOLD_MINUTES", "20"))
WATCHDOG_ALERT_COOLDOWN_SECONDS = int(os.environ.get("WATCHDOG_ALERT_COOLDOWN_SECONDS", "3600"))

# Limites internos de observabilidade de memória.
# Render free/starter costuma reiniciar perto de 512 MB; use env para ajustar.
MEMORY_LIMIT_MB = float(os.environ.get("CENTRAL_MEMORY_LIMIT_MB", "512"))
MEMORY_GC_THRESHOLD_MB = float(os.environ.get("CENTRAL_MEMORY_GC_THRESHOLD_MB", "430"))
MEMORY_HISTORY_MAXLEN = int(os.environ.get("CENTRAL_MEMORY_HISTORY_MAXLEN", "120"))
MEMORY_LOG_EVERY_SECONDS = int(os.environ.get("CENTRAL_MEMORY_LOG_EVERY_SECONDS", "300"))
MEMORY_HISTORY = deque(maxlen=MEMORY_HISTORY_MAXLEN)
LAST_MEMORY_LOG_TS = 0.0
LAST_GC_TS = 0.0


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "sim", "on"}


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


def current_rss_mb():
    """RSS atual do processo em MB, usando /proc para não depender de psutil."""
    try:
        with open("/proc/self/statm", "r", encoding="utf-8") as f:
            pages = int(f.read().split()[1])
        return round(pages * os.sysconf("SC_PAGE_SIZE") / (1024 * 1024), 2)
    except Exception:
        return None


def memory_percent(rss_mb=None):
    try:
        rss = current_rss_mb() if rss_mb is None else rss_mb
        if rss is None or MEMORY_LIMIT_MB <= 0:
            return None
        return round((float(rss) / float(MEMORY_LIMIT_MB)) * 100, 2)
    except Exception:
        return None


def memory_snapshot(label="snapshot"):
    rss = current_rss_mb()
    pct = memory_percent(rss)
    snap = {
        "ts": data_hora_sp_str(),
        "label": str(label),
        "rss_mb": rss,
        "limit_mb": MEMORY_LIMIT_MB,
        "usage_pct": pct,
        "gc_count": list(gc.get_count()),
        "loaded_bots": list(LOADED_BOTS.keys()),
        "threads": threading.active_count(),
    }
    MEMORY_HISTORY.append(snap)
    return snap


def maybe_collect_garbage(label="auto"):
    """Coleta GC se a memória estiver alta. Evita rodar GC em loop a cada request."""
    global LAST_GC_TS
    rss = current_rss_mb()
    if rss is None:
        return {"ran": False, "rss_before_mb": None, "rss_after_mb": None, "reason": "rss_unavailable"}

    now = time.time()
    if rss < MEMORY_GC_THRESHOLD_MB and now - LAST_GC_TS < 60:
        return {"ran": False, "rss_before_mb": rss, "rss_after_mb": rss, "reason": "below_threshold"}

    if rss >= MEMORY_GC_THRESHOLD_MB or now - LAST_GC_TS >= 300:
        before = rss
        collected = gc.collect()
        after = current_rss_mb()
        LAST_GC_TS = now
        MEMORY_HISTORY.append({
            "ts": data_hora_sp_str(),
            "label": f"gc:{label}",
            "rss_mb": after,
            "limit_mb": MEMORY_LIMIT_MB,
            "usage_pct": memory_percent(after),
            "collected": collected,
            "rss_before_mb": before,
            "threads": threading.active_count(),
        })
        return {"ran": True, "rss_before_mb": before, "rss_after_mb": after, "collected": collected}

    return {"ran": False, "rss_before_mb": rss, "rss_after_mb": rss, "reason": "cooldown"}


def log_memory_if_needed(label="periodic"):
    global LAST_MEMORY_LOG_TS
    now = time.time()
    if now - LAST_MEMORY_LOG_TS < MEMORY_LOG_EVERY_SECONDS:
        return
    LAST_MEMORY_LOG_TS = now
    snap = memory_snapshot(label)
    print(
        "MEMORY",
        f"label={snap.get('label')}",
        f"rss_mb={snap.get('rss_mb')}",
        f"usage_pct={snap.get('usage_pct')}",
        f"threads={snap.get('threads')}",
    )


def build_memory_report():
    snap_before = memory_snapshot("/memory_before_gc")
    gc_result = maybe_collect_garbage("/memory")
    snap_after = memory_snapshot("/memory_after_gc")

    status = "OK"
    pct = snap_after.get("usage_pct")
    if pct is not None and pct >= 90:
        status = "ATENÇÃO"
    if pct is not None and pct >= 97:
        status = "CRÍTICO"

    recent = list(MEMORY_HISTORY)[-8:]
    hist_lines = [
        f"{x.get('ts')} | {x.get('label')} | {x.get('rss_mb')} MB | {x.get('usage_pct')}%"
        for x in recent
    ]

    lines = [
        "🧠 MEMÓRIA CENTRAL QUANT",
        f"Data/hora: {data_hora_sp_str()}",
        f"Status: {status}",
        "",
        f"RSS antes GC: {snap_before.get('rss_mb')} MB ({snap_before.get('usage_pct')}%)",
        f"RSS atual: {snap_after.get('rss_mb')} MB ({snap_after.get('usage_pct')}%)",
        f"Limite configurado: {MEMORY_LIMIT_MB:.0f} MB",
        f"Threshold GC: {MEMORY_GC_THRESHOLD_MB:.0f} MB",
        f"Threads ativas: {snap_after.get('threads')}",
        f"GC count: {snap_after.get('gc_count')}",
        f"GC executado: {gc_result.get('ran')} | coletados: {gc_result.get('collected')}",
        "",
        "Histórico recente:",
        *(hist_lines or ["Sem histórico."]),
        "",
        "Observação:",
        "Se a memória ficar acima de 90% por muito tempo, o Render pode reiniciar o serviço.",
    ]
    return "\n".join(lines)


@app.after_request
def after_request_memory_housekeeping(response):
    try:
        log_memory_if_needed("after_request")
        # Coleta apenas quando estiver acima do limite configurado.
        if (current_rss_mb() or 0) >= MEMORY_GC_THRESHOLD_MB:
            maybe_collect_garbage("after_request")
    except Exception:
        pass
    return response


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
# Importante para impedir respostas duplicadas no Telegram caso o módulo principal
# seja importado mais de uma vez pelo servidor.
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

    # Alguns códigos usam variáveis específicas além do padrão TELEGRAM_*.
    for extra in cfg.get("extra_token_envs", []):
        env_map[extra] = token
    for extra in cfg.get("extra_chat_envs", []):
        env_map[extra] = chat_id

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


def start_enabled_bots():
    for key, cfg in BOT_CONFIGS.items():
        if not env_bool(cfg["enabled_env"], default=False):
            continue
        try:
            LOADED_BOTS[key] = load_bot(key, cfg)
            print(f"BOT CARREGADO: {key} - {cfg['name']}")
        except Exception as exc:
            LOAD_ERRORS[key] = str(exc)
            print(f"ERRO AO CARREGAR {key}: {exc}")


def bot_health(key: str, cfg: dict):
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

    return payload


def get_open_positions_from_module(module):
    positions = []
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
    return positions


def _safe_float(value, default=0.0):
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _position_runner_r(position: dict):
    """
    Retorna o melhor R disponível para uma posição aberta.

    Prioridade:
    1. Campos de R atual, se algum bot passar no futuro.
    2. Campos de R aberto/resultado parcial, se existirem.
    3. MFE em R, que já é preenchido pelo Turtle e por futuros bots compatíveis.

    Observação: para bots sem métrica em R, retorna 0.0 sem quebrar o painel.
    """
    if not isinstance(position, dict):
        return 0.0

    candidates = [
        "current_r",
        "pnl_r",
        "unrealized_r",
        "open_r",
        "result_r",
        "mfe_r",
    ]

    for field in candidates:
        if field in position and position.get(field) is not None:
            return _safe_float(position.get(field), 0.0)

    return 0.0


def _position_runner_pct(position: dict):
    if not isinstance(position, dict):
        return 0.0

    candidates = [
        "current_pct",
        "pnl_pct",
        "unrealized_pct",
        "open_pct",
        "result_pct",
        "mfe_pct",
    ]

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
    total = 0
    longs = 0
    shorts = 0
    by_bot = {}
    open_runner_buckets = _empty_runner_buckets()
    best_open_runner = None

    for key, module in LOADED_BOTS.items():
        positions = get_open_positions_from_module(module)
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

    return {
        "total_positions_open": total,
        "long_positions_open": longs,
        "short_positions_open": shorts,
        "open_runners": open_runner_buckets,
        "best_open_runner": best_open_runner,
        "by_bot": by_bot,
    }


def central_watchdog_status():
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

    return {
        "ok": len(reasons) == 0,
        "status": "OK" if len(reasons) == 0 else "ALERTA",
        "central_started_at": CENTRAL_HEALTH["started_at"],
        "threshold_minutes": WATCHDOG_THRESHOLD_MINUTES,
        "reasons": reasons,
        "bots": bots,
    }


def send_central_alert(message: str):
    # Usa o send_telegram/safe_send_telegram de cada módulo carregado para não depender de outro bot.
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
            log_memory_if_needed("watchdog")
            maybe_collect_garbage("watchdog")
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
    status = central_watchdog_status()
    exposure_snapshot = central_exposure_snapshot()

    resumo = {}
    for key, cfg in BOT_CONFIGS.items():
        b = bot_health(key, cfg)
        h = b.get("health", {}) or {}

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
            "positions_open": h.get("last_positions_count"),
            "signals_last_cycle": h.get("last_signals_sent"),
            "watchdog_status": h.get("watchdog_last_status"),

            # Métricas estatísticas avançadas.
            # O Turtle já preenche esses campos; os outros bots podem passar a preencher depois.
            "mfe_avg_pct": h.get("mfe_avg_pct"),
            "mae_avg_pct": h.get("mae_avg_pct"),
            "mfe_avg_r": h.get("mfe_avg_r"),
            "mae_avg_r": h.get("mae_avg_r"),
            "top_mfe_month": h.get("top_mfe_month", []),
            "runners_3r": h.get("runners_3r"),
            "runners_5r": h.get("runners_5r"),
            "runners_10r": h.get("runners_10r"),

            # Runners abertos informados pelo próprio bot, quando existirem.
            # O Turtle já preenche esses campos; a Central também calcula o consolidado em /exposure.
            "open_runner_symbol": h.get("open_runner_symbol"),
            "open_runner_setup": h.get("open_runner_setup"),
            "open_runner_side": h.get("open_runner_side"),
            "open_runner_r": h.get("open_runner_r"),
            "open_runner_pct": h.get("open_runner_pct"),
        }

    enabled = [k for k, v in resumo.items() if v.get("enabled")]
    loaded = [k for k, v in resumo.items() if v.get("loaded")]
    alerts = [
        k for k, v in resumo.items()
        if v.get("enabled") and not v.get("ok")
    ]

    return {
        "ok": status.get("ok"),
        "status": status.get("status"),
        "central_started_at": status.get("central_started_at"),
        "enabled_bots": enabled,
        "loaded_bots": loaded,
        "alerts": alerts,
        "reasons": status.get("reasons", []),
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






@app.route("/relatorio")
def relatorio_curto():
    return {"text": build_central_report("curto")}


@app.route("/relatorio/completo")
def relatorio_completo():
    return {"text": build_central_report("completo")}


@app.route("/relatorio/<key>")
def relatorio_bot(key):
    bot_key = REPORT_BOT_ALIASES.get(str(key).lower(), str(key).upper())
    if bot_key not in BOT_CONFIGS:
        return {"error": "bot inválido"}, 404
    return {"text": build_central_report("completo", bot_key=bot_key)}


@app.route("/diagnostico")
def diagnostico():
    return {"text": build_diagnostic_report()}


@app.route("/selftest")
def selftest():
    return {"text": build_selftest_report()}


@app.route("/memory")
@app.route("/memoria")
@app.route("/memória")
def memory():
    return {"text": build_memory_report(), "history": list(MEMORY_HISTORY)[-20:]}


# ==========================================================
# CENTRAL REPORT BUILDER
# ==========================================================
# Comandos/rotas:
# - /relatorio           -> relatório consolidado resumido
# - /relatorio completo  -> relatório completo com health/funil/eventos/resumo
# - /relatorio <bot>     -> relatório completo de um bot
# - /relatorio curto     -> igual ao resumido

REPORT_COMMANDS = {"/relatorio", "/relatório", "/report"}
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
    ok = enabled and loaded and not b.get("load_error") and not last_error
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

    if last_error:
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


def _bot_funil_text(key: str, module):
    if key == "TURTLE":
        return _json_or_text(_call_first(module, ["funnel_text"]))
    if key == "FALCON":
        return _json_or_text(_call_first(module, ["funnel_text"]))
    return _json_or_text(_call_first(module, [
        "montar_funil_texto", "montar_funil", "funnel_text", "funil_texto", "build_funnel_text"
    ]))


def _bot_eventos_text(key: str, module):
    if key == "TURTLE":
        return _json_or_text(_call_first(module, ["events_text"]))
    if key == "FALCON":
        return _json_or_text(_call_first(module, ["events_text"]))
    return _json_or_text(_call_first(module, [
        "montar_eventos_texto", "events_text", "eventos_texto", "build_events_text"
    ]))


def _bot_resumo_text(key: str, module):
    if key in {"TURTLE", "FALCON"}:
        if hasattr(module, "build_summary") and hasattr(module, "trades_today"):
            return module.build_summary("DIA", module.trades_today())
    return _json_or_text(_call_first(module, [
        "montar_resumo_diario", "build_daily_summary", "summary_text", "build_summary_text", "resumo_texto"
    ]))


def build_single_bot_report(key: str, complete: bool = True):
    key = str(key).upper()
    cfg = BOT_CONFIGS.get(key)
    if not cfg:
        return f"Bot inválido: {key}"
    module = LOADED_BOTS.get(key)

    parts = [f"🤖 RELATÓRIO {key} - {cfg.get('name')}\n", "🩺 HEALTH\n" + _bot_report_health_text(key)]

    if module is None:
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

    return "\n\n".join(parts)


def build_central_status_text():
    status = central_watchdog_status()
    exposure_snapshot = central_exposure_snapshot()
    best = exposure_snapshot.get("best_open_runner") or {}
    by_bot_exposure = exposure_snapshot.get("by_bot", {}) or {}
    open_runners = exposure_snapshot.get("open_runners") or {}

    lines = [
        "📊 RELATÓRIO CENTRAL QUANT",
        f"Data/hora: {data_hora_sp_str()}",
        f"Status: {status.get('status')} | OK: {status.get('ok')}",
        f"Central iniciou: {status.get('central_started_at')}",
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
    if concentration_msgs:
        lines += ["", "⚠️ OBSERVAÇÕES DE RISCO"] + [f"- {m}" for m in concentration_msgs]

    lines += ["", "🤖 BOTS"]
    for key in BOT_CONFIGS.keys():
        lines.append(_bot_compact_status_line(key, by_bot_exposure))

    return "\n".join(lines)


def build_central_report(mode: str = "curto", bot_key: str = None):
    mode = (mode or "curto").lower().strip()
    complete = mode in {"completo", "full", "complete"}

    if bot_key:
        return build_single_bot_report(bot_key, complete=True)

    if not complete:
        return build_central_status_text()

    parts = [build_central_status_text()]
    parts.append("\n\n==============================\nCHECKLIST COMPLETO DOS BOTS\n==============================")
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
        error_ok = not b.get("last_error") and not b.get("load_error")
        wl_total = h.get("watchlist_total")
        wl_valid = h.get("watchlist_valid")
        wl_invalid = h.get("watchlist_invalid", []) or []
        watchlist_ok = (wl_total is None) or (wl_valid == wl_total and not wl_invalid)
        warning = _clean_warning(h.get("last_warning"))

        all_enabled_loaded = all_enabled_loaded and loaded
        all_cycles_ok = all_cycles_ok and scanner_ok and management_ok
        all_errors_ok = all_errors_ok and error_ok
        all_watchlists_ok = all_watchlists_ok and watchlist_ok

        if warning:
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

    apto = bool(status.get("ok")) and all_enabled_loaded and all_cycles_ok and all_errors_ok and all_watchlists_ok
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
        f"Memória: {current_rss_mb()} MB ({memory_percent()}%)",
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
    """
    Self test operacional da Central.
    Não altera estado dos bots. Apenas valida carregamento, health, ciclos,
    watchlists, exposição, runners e rotas críticas.
    """
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
        error_ok = not b.get("last_error") and not b.get("load_error")

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
            + (f" | warning={warning}" if warning else "")
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
    mem_pct = memory_percent()
    add_test("Memória abaixo de 95%", mem_pct is None or mem_pct < 95, f"{current_rss_mb()} MB | {mem_pct}%")

    risk_notes = []
    if total_pos >= 50:
        risk_notes.append(f"Muitas posições abertas: {total_pos}.")
    if total_pos and short_pos / max(total_pos, 1) >= 0.80:
        risk_notes.append(f"Exposição muito SHORT: {short_pos}/{total_pos}.")
    if total_pos and long_pos / max(total_pos, 1) >= 0.80:
        risk_notes.append(f"Exposição muito LONG: {long_pos}/{total_pos}.")

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

    mode = "curto"
    bot_key = None
    for p in parts[1:]:
        p = p.strip().lower().replace("/", "")
        if p in {"completo", "full", "complete"}:
            mode = "completo"
        elif p in {"curto", "resumido", "short"}:
            mode = "curto"
        elif p in REPORT_BOT_ALIASES:
            bot_key = REPORT_BOT_ALIASES[p]
            mode = "completo"
    return mode, bot_key

# ==========================================================
# CENTRAL TELEGRAM COMMAND ROUTER
# ==========================================================
# Objetivo:
# - Permitir que a Central responda comandos dos bots que NÃO rodam command_loop próprio.
# - Evitar conflito Telegram getUpdates 409.
# - Hoje fica ativo por padrão para TURTLE e FALCON, pois esses bots devem ter o command_loop interno desligado.
# - Para qualquer outro bot, só ligue CENTRAL_ROUTE_<BOT>_TELEGRAM=true depois de desligar o command_loop interno dele.

COMMAND_ROUTER_DEFAULTS = {
    "TRENDPRO": False,
    "DONKEY": False,
    "COBRA": False,
    "MEME": False,
    "PREDATOR": False,
    "TURTLE": True,
    "FALCON": True,
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


def telegram_send_with_token(token, chat_id, text):
    if not token or not chat_id:
        print(text)
        return False
    try:
        partes = [str(text)[i:i + 3900] for i in range(0, len(str(text)), 3900)] or [""]
        for parte in partes:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": parte,
                "disable_web_page_preview": True,
            }
            requests.post(url, json=payload, timeout=15)
            time.sleep(0.25)
        return True
    except Exception as exc:
        print("ERRO TELEGRAM CENTRAL ROUTER:", exc)
        return False


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


def build_command_reply_for_module(key: str, module, cmd: str):
    """
    Converte comandos padronizados em resposta textual.
    Mantém a lógica individual em cada bot e só padroniza o acesso pela Central.
    """
    raw_cmd = (cmd or "").strip()
    cmd0 = raw_cmd.lower().split()[0].split("@")[0] if raw_cmd else ""

    if cmd0 in {"/diagnostico", "/diagnóstico", "/diag"}:
        return build_diagnostic_report()

    if cmd0 in {"/selftest", "/self-test", "/teste", "/autoteste"}:
        return build_selftest_report()

    if cmd0 in {"/memory", "/memoria", "/memória"}:
        return build_memory_report()

    parsed_report = parse_report_command(raw_cmd)
    if parsed_report:
        mode, bot_key = parsed_report
        return build_central_report(mode, bot_key=bot_key)

    cmd = cmd0

    # TURTLE tem handle_command próprio, mas ele envia pelo próprio módulo.
    # Preferimos respostas diretas para evitar depender do CHAT_ID interno.
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
                "/health\n/posicoes\n/resumo\n/funil\n/eventos\n/top\n/ranking\n/relatorio\n/relatorio completo"
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
            return "🦅 Comandos Falcon:\n/health\n/posicoes\n/resumo\n/funil\n/eventos\n/watchlist\n/relatorio\n/relatorio completo"

    # Padrão genérico para outros bots, caso você ligue o roteador central depois.
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

                reply = build_command_reply_for_module(key, module, text)
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
    """
    Inicializa bots, watchdog e roteadores apenas uma vez por processo.

    Sem esta trava, múltiplas importações do main.py podem iniciar mais de um
    roteador Telegram para o mesmo token, causando respostas duplicadas e/ou
    conflitos getUpdates 409.
    """
    global CENTRAL_RUNTIME_STARTED

    with CENTRAL_RUNTIME_LOCK:
        if CENTRAL_RUNTIME_STARTED:
            print("CENTRAL RUNTIME JÁ INICIADO - ignorando nova chamada")
            return

        CENTRAL_RUNTIME_STARTED = True

    memory_snapshot("before_start_bots")
    start_enabled_bots()
    memory_snapshot("after_start_bots")
    maybe_collect_garbage("after_start_bots")
    threading.Thread(target=central_watchdog_loop, daemon=True).start()
    start_central_command_routers()


start_central_runtime_once()

if __name__ == "__main__":
    porta = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=porta)
