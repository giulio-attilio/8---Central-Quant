# CENTRAL QUANT PRO FULL - SUPERVISOR MODULAR
# Versão: 2026-06-25-CENTRAL-FULL-EXPOSURE-RUNNERS-PANEL
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
        health = getattr(module, "HEALTH", {})
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
    cmd = (cmd or "").strip().lower().split("@")[0]

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
                "/health\n/posicoes\n/resumo\n/funil\n/eventos\n/top\n/ranking"
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
            return "🦅 Comandos Falcon:\n/health\n/posicoes\n/resumo\n/funil\n/eventos\n/watchlist"

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

                cmd = text.split()[0].lower().split("@")[0]
                reply = build_command_reply_for_module(key, module, cmd)
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


start_enabled_bots()
threading.Thread(target=central_watchdog_loop, daemon=True).start()
start_central_command_routers()

if __name__ == "__main__":
    porta = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=porta)
