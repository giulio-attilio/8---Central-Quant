# execution_engine.py
# CENTRAL QUANT — EXECUTION ENGINE V2.5.3
# Versão: 2026-07-05-EXECUTION-ENGINE-V2.5.3-EXECUTION-PREVIEW-GUARD
#
# Objetivo:
# - Ser o ponto único de decisão antes de qualquer execução.
# - Integrar Orchestrator V1 com a arquitetura Flask da Central.
# - Manter OBSERVATION_ONLY e PAPER.
# - Permitir piloto LIVE/REAL apenas com travas rígidas:
#   * CENTRAL_REAL_EXECUTION_ENABLED=true
#   * CENTRAL_REAL_PILOT_ENABLED=true
#   * dry_run=false para envio real; dry_run=true permitido apenas para preview seguro
#   * robô permitido
#   * símbolo permitido
#   * margem dentro do máximo
#   * alavancagem dentro do máximo
#   * side/entry/sl válidos
#   * broker carregado e pronto
#
# Importante:
# - Este arquivo NÃO aumenta risco automaticamente.
# - Este arquivo NÃO remove kill switch.
# - Em caso de dúvida, bloqueia.
# - O envio real final continua passando pelo broker.py, que também possui
#   travas próprias: EXECUTION_MODE=LIVE, ENABLE_REAL_TRADING=true e BROKER_DRY_RUN=false.

import os
import json
import time
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, Optional, List, Tuple

try:
    from execution_orchestrator import orchestrate_execution, execution_health
except Exception as exc:
    orchestrate_execution = None
    execution_health = None
    ORCHESTRATOR_IMPORT_ERROR = str(exc)
else:
    ORCHESTRATOR_IMPORT_ERROR = None

try:
    from paper_executor_integrated import execute_paper_from_engine, paper_integrated_health
except Exception as exc:
    execute_paper_from_engine = None
    paper_integrated_health = None
    PAPER_EXECUTOR_IMPORT_ERROR = str(exc)
else:
    PAPER_EXECUTOR_IMPORT_ERROR = None

try:
    import broker as central_broker
except Exception as exc:
    central_broker = None
    BROKER_IMPORT_ERROR = str(exc)
else:
    BROKER_IMPORT_ERROR = None


VERSION = "2026-07-05-EXECUTION-ENGINE-V2.5.3-EXECUTION-PREVIEW-GUARD"

DATA_DIR = Path(os.getenv("CENTRAL_DATA_DIR", "/opt/render/project/src/data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

EXECUTION_ENGINE_LOG_FILE = DATA_DIR / "execution_engine_log.jsonl"

DEFAULT_ENGINE_MODE = os.getenv("CENTRAL_EXECUTION_ENGINE_MODE", "OBSERVATION_ONLY").upper()

# Kill switches principais.
REAL_EXECUTION_ENABLED = os.getenv("CENTRAL_REAL_EXECUTION_ENABLED", "false").lower() == "true"
PAPER_EXECUTION_ENABLED = os.getenv("CENTRAL_PAPER_EXECUTION_ENABLED", "false").lower() == "true"

# Piloto real controlado.
REAL_PILOT_ENABLED = os.getenv("CENTRAL_REAL_PILOT_ENABLED", "false").strip().lower() in {"1", "true", "yes", "sim", "on"}
REAL_PILOT_ALLOWED_BOTS = {
    x.strip().upper()
    for x in os.getenv("REAL_PILOT_ALLOWED_BOTS", os.getenv("REAL_TRADING_ALLOWED_BOTS", "FALCON")).split(",")
    if x.strip()
}
REAL_PILOT_ALLOWED_SYMBOLS = {
    _s.strip().upper().replace("/", "").replace(":USDT", "")
    for _s in os.getenv("REAL_PILOT_ALLOWED_SYMBOLS", os.getenv("REAL_TRADING_ALLOWED_SYMBOLS", "BTCUSDT,ETHUSDT")).split(",")
    if _s.strip()
}
REAL_PILOT_MAX_MARGIN_USDT = float(os.getenv("REAL_PILOT_MAX_MARGIN_USDT", os.getenv("REAL_TRADING_MAX_MARGIN_USDT", "10")))
REAL_PILOT_MAX_LEVERAGE = int(os.getenv("REAL_PILOT_MAX_LEVERAGE", os.getenv("REAL_TRADING_MAX_LEVERAGE", "2")))
REAL_PILOT_MAX_NOTIONAL_USDT = float(os.getenv("REAL_PILOT_MAX_NOTIONAL_USDT", str(REAL_PILOT_MAX_MARGIN_USDT * REAL_PILOT_MAX_LEVERAGE)))
REAL_PILOT_MAX_RISK_PCT = float(os.getenv("REAL_PILOT_MAX_RISK_PCT", os.getenv("REAL_TRADING_MAX_RISK_PCT", "3.0")))
REAL_PILOT_REQUIRE_READY = os.getenv("REAL_PILOT_REQUIRE_READY", "true").strip().lower() in {"1", "true", "yes", "sim", "on"}
REAL_PILOT_REQUIRE_STOP = os.getenv("REAL_PILOT_REQUIRE_STOP", "true").strip().lower() in {"1", "true", "yes", "sim", "on"}
REAL_PILOT_REQUIRE_ENTRY = os.getenv("REAL_PILOT_REQUIRE_ENTRY", "true").strip().lower() in {"1", "true", "yes", "sim", "on"}
REAL_PILOT_ALLOW_REDUCE_ONLY = os.getenv("REAL_PILOT_ALLOW_REDUCE_ONLY", "true").strip().lower() in {"1", "true", "yes", "sim", "on"}

# Default conservador: 1 posição real por vez. Se não conseguir consultar posições, bloqueia quando require_ready=true.
REAL_PILOT_MAX_OPEN_POSITIONS = int(os.getenv("REAL_PILOT_MAX_OPEN_POSITIONS", "1"))
REAL_PILOT_BLOCK_IF_POSITIONS_UNKNOWN = os.getenv("REAL_PILOT_BLOCK_IF_POSITIONS_UNKNOWN", "true").strip().lower() in {"1", "true", "yes", "sim", "on"}
REAL_PILOT_IGNORE_EXISTING_POSITIONS = os.getenv("REAL_PILOT_IGNORE_EXISTING_POSITIONS","false").strip().lower() in {"1","true","yes","sim","on"}


def _now_br() -> str:
    return datetime.now().strftime("%d/%m/%Y %H:%M:%S")


def _append_jsonl(path: Path, payload: Dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass


def _safe_mode(value: Optional[str]) -> str:
    mode = str(value or DEFAULT_ENGINE_MODE).upper().strip()
    if mode in {"OBS", "OBSERVATION", "OBSERVATION_ONLY"}:
        return "OBSERVATION_ONLY"
    if mode in {"PAPER", "SIM", "SIMULATION"}:
        return "PAPER"
    if mode in {"LIVE", "REAL"}:
        return "LIVE"
    return "OBSERVATION_ONLY"


def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None:
            return default
        if isinstance(value, str):
            value = value.replace("%", "").replace(",", ".").strip()
            if not value:
                return default
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    try:
        if value is None:
            return default
        return int(float(value))
    except Exception:
        return default


def _normalize_symbol(symbol: Any) -> str:
    s = str(symbol or "").upper().strip()
    if not s:
        return ""
    return s.replace("/", "").replace(":USDT", "")


def _normalize_side(side: Any) -> str:
    s = str(side or "").upper().strip()
    if s in {"BUY", "LONG"}:
        return "LONG"
    if s in {"SELL", "SHORT"}:
        return "SHORT"
    return s


def _extract_plan_value(payload: Dict[str, Any], plan: Dict[str, Any], keys: List[str], default: Any = None) -> Any:
    for source in (payload, plan):
        if not isinstance(source, dict):
            continue
        for key in keys:
            if source.get(key) is not None:
                return source.get(key)
    return default


def _bot_from_payload(payload: Dict[str, Any], plan: Dict[str, Any]) -> str:
    return str(_extract_plan_value(payload, plan, ["bot", "robot", "strategy", "source"], "UNKNOWN") or "UNKNOWN").upper().strip()


def _symbol_from_payload(payload: Dict[str, Any], plan: Dict[str, Any]) -> str:
    return _normalize_symbol(_extract_plan_value(payload, plan, ["symbol", "pair", "market", "ativo"], ""))


def _side_from_payload(payload: Dict[str, Any], plan: Dict[str, Any]) -> str:
    return _normalize_side(_extract_plan_value(payload, plan, ["side", "direction", "signal"], ""))


def _margin_from_payload(payload: Dict[str, Any], plan: Dict[str, Any]) -> float:
    margin = _safe_float(_extract_plan_value(payload, plan, ["margin_usdt", "real_margin_usdt", "requested_margin_usdt"], None))
    if margin is not None:
        return margin

    bot = _bot_from_payload(payload, plan)
    prefix = bot.upper().replace("SMART_PREDATOR", "PREDATOR").replace("TRENDPRO", "TREND")
    env_margin = os.getenv(f"{prefix}_REAL_MARGIN_USDT")
    margin = _safe_float(env_margin, None)
    if margin is not None:
        return margin

    return _safe_float(os.getenv("DEFAULT_REAL_MARGIN_USDT", os.getenv("REAL_TRADING_MARGIN_USDT", "5")), 5.0) or 5.0


def _leverage_from_payload(payload: Dict[str, Any], plan: Dict[str, Any]) -> int:
    lev = _safe_int(_extract_plan_value(payload, plan, ["leverage", "real_leverage", "requested_leverage"], None))
    if lev is not None:
        return lev

    bot = _bot_from_payload(payload, plan)
    prefix = bot.upper().replace("SMART_PREDATOR", "PREDATOR").replace("TRENDPRO", "TREND")
    env_lev = os.getenv(f"{prefix}_REAL_LEVERAGE")
    lev = _safe_int(env_lev, None)
    if lev is not None:
        return lev

    return _safe_int(os.getenv("DEFAULT_REAL_LEVERAGE", os.getenv("REAL_TRADING_LEVERAGE", "1")), 1) or 1


def _risk_pct_from_payload(payload: Dict[str, Any], plan: Dict[str, Any]) -> Optional[float]:
    return _safe_float(_extract_plan_value(payload, plan, ["risk_pct", "risco_pct", "risk"], None))


def _entry_from_payload(payload: Dict[str, Any], plan: Dict[str, Any]) -> Optional[float]:
    return _safe_float(_extract_plan_value(payload, plan, ["entry", "entry_price", "entrada"], None))


def _stop_from_payload(payload: Dict[str, Any], plan: Dict[str, Any]) -> Optional[float]:
    return _safe_float(_extract_plan_value(payload, plan, ["sl", "stop", "stop_loss", "initial_sl"], None))


def _tp50_from_payload(payload: Dict[str, Any], plan: Dict[str, Any]) -> Optional[float]:
    return _safe_float(_extract_plan_value(payload, plan, ["tp50", "tp_50"], None))


def _count_real_open_positions(symbol: Optional[str] = None) -> Tuple[Optional[int], Dict[str, Any]]:
    """
    Consulta posições reais via broker.
    Retorna (count, details). Se não conseguir consultar, count=None.
    """
    if central_broker is None or not hasattr(central_broker, "get_positions"):
        return None, {"ok": False, "error": BROKER_IMPORT_ERROR or "broker.get_positions indisponível"}

    try:
        symbols = [symbol] if symbol else None
        positions = central_broker.get_positions(symbols=symbols)
        open_positions = []
        for p in positions or []:
            if not isinstance(p, dict):
                continue

            contracts = _safe_float(
                p.get("contracts")
                or p.get("contractSize")
                or p.get("positionAmt")
                or p.get("positionAmt".lower())
                or p.get("amount"),
                0.0,
            ) or 0.0

            # CCXT/BingX pode trazer vários formatos. Se houver notional/entryPrice positivo,
            # também tratamos como posição aberta.
            notional = _safe_float(p.get("notional") or p.get("notionalValue"), 0.0) or 0.0
            entry_price = _safe_float(p.get("entryPrice") or p.get("entry_price"), 0.0) or 0.0

            if abs(contracts) > 0 or abs(notional) > 0 or entry_price > 0:
                open_positions.append(p)

        return len(open_positions), {
            "ok": True,
            "checked": True,
            "symbol": symbol,
            "open_positions": len(open_positions),
            "sample": open_positions[:3],
        }
    except Exception as exc:
        return None, {"ok": False, "checked": False, "symbol": symbol, "error": str(exc)}


def validate_real_pilot_guard(payload: Dict[str, Any], plan: Dict[str, Any], dry_run: bool = True) -> Dict[str, Any]:
    """
    Validação conservadora para operação real.
    Em qualquer inconsistência, bloqueia.
    """
    payload = payload if isinstance(payload, dict) else {}
    plan = plan if isinstance(plan, dict) else {}

    reasons: List[str] = []
    warnings: List[str] = []

    bot = _bot_from_payload(payload, plan)
    symbol = _symbol_from_payload(payload, plan)
    side = _side_from_payload(payload, plan)
    margin = _margin_from_payload(payload, plan)
    leverage = _leverage_from_payload(payload, plan)
    notional = margin * leverage
    risk_pct = _risk_pct_from_payload(payload, plan)
    entry = _entry_from_payload(payload, plan)
    stop = _stop_from_payload(payload, plan)
    tp50 = _tp50_from_payload(payload, plan)

    decision = str(_extract_plan_value(payload, plan, ["decision", "final_decision"], "ALLOW") or "ALLOW").upper().strip()
    allowed = _extract_plan_value(payload, plan, ["allowed"], None)

    if not REAL_EXECUTION_ENABLED:
        reasons.append("CENTRAL_REAL_EXECUTION_ENABLED=false")
    if not REAL_PILOT_ENABLED:
        reasons.append("CENTRAL_REAL_PILOT_ENABLED=false")
    preview_mode = bool(dry_run)
    if preview_mode:
        warnings.append("dry_run=true; modo preview: broker pode montar VERIFY/DRY_RUN, mas não deve enviar ordem real")

    if decision in {"DENY", "BLOCK", "BLOCKED", "REJECT", "REJECTED"}:
        reasons.append(f"decision={decision}")
    if allowed is False:
        reasons.append("allowed=false")

    if bot not in REAL_PILOT_ALLOWED_BOTS:
        reasons.append(f"bot não permitido no piloto: {bot}; permitidos={sorted(REAL_PILOT_ALLOWED_BOTS)}")

    if symbol not in REAL_PILOT_ALLOWED_SYMBOLS:
        reasons.append(f"symbol não permitido no piloto: {symbol}; permitidos={sorted(REAL_PILOT_ALLOWED_SYMBOLS)}")

    if side not in {"LONG", "SHORT"}:
        reasons.append(f"side inválido para piloto: {side}")

    if margin <= 0:
        reasons.append(f"margin_usdt inválida: {margin}")
    if margin > REAL_PILOT_MAX_MARGIN_USDT:
        reasons.append(f"margin_usdt {margin} acima do máximo piloto {REAL_PILOT_MAX_MARGIN_USDT}")

    if leverage <= 0:
        reasons.append(f"leverage inválida: {leverage}")
    if leverage > REAL_PILOT_MAX_LEVERAGE:
        reasons.append(f"leverage {leverage} acima do máximo piloto {REAL_PILOT_MAX_LEVERAGE}")

    if notional <= 0:
        reasons.append(f"notional inválido: {notional}")
    if notional > REAL_PILOT_MAX_NOTIONAL_USDT:
        reasons.append(f"notional {notional} acima do máximo piloto {REAL_PILOT_MAX_NOTIONAL_USDT}")

    if risk_pct is not None and risk_pct > REAL_PILOT_MAX_RISK_PCT:
        reasons.append(f"risk_pct {risk_pct} acima do máximo piloto {REAL_PILOT_MAX_RISK_PCT}")

    if REAL_PILOT_REQUIRE_ENTRY and not entry:
        reasons.append("entry ausente; piloto exige entry")
    if REAL_PILOT_REQUIRE_STOP and not stop:
        reasons.append("stop/sl ausente; piloto exige stop")

    if entry and stop:
        if side == "LONG" and stop >= entry:
            reasons.append(f"stop inválido para LONG: stop={stop} >= entry={entry}")
        if side == "SHORT" and stop <= entry:
            reasons.append(f"stop inválido para SHORT: stop={stop} <= entry={entry}")

    ready_payload = None
    if REAL_PILOT_REQUIRE_READY:
        if central_broker is None:
            reasons.append(f"broker indisponível: {BROKER_IMPORT_ERROR}")
        elif hasattr(central_broker, "ready_check"):
            try:
                ready_payload = central_broker.ready_check(cache_seconds=0)
                if not ready_payload.get("ok"):
                    reasons.append(f"broker NOT_READY: {ready_payload.get('error') or ready_payload.get('status')}")
            except Exception as exc:
                reasons.append(f"erro no broker.ready_check: {exc}")
        else:
            reasons.append("broker.ready_check indisponível")

    positions_count = None
    positions_payload = None
    if REAL_PILOT_MAX_OPEN_POSITIONS >= 0:
        positions_count, positions_payload = _count_real_open_positions(symbol=symbol)
        if positions_count is None:
            if REAL_PILOT_BLOCK_IF_POSITIONS_UNKNOWN:
                reasons.append(f"não foi possível consultar posições reais: {positions_payload.get('error') if isinstance(positions_payload, dict) else positions_payload}")
            else:
                warnings.append("posições reais não consultadas; seguindo porque REAL_PILOT_BLOCK_IF_POSITIONS_UNKNOWN=false")
        elif (not REAL_PILOT_IGNORE_EXISTING_POSITIONS) and positions_count >= REAL_PILOT_MAX_OPEN_POSITIONS:
            reasons.append(f"limite de posições reais atingido: {positions_count}/{REAL_PILOT_MAX_OPEN_POSITIONS}")
        elif REAL_PILOT_IGNORE_EXISTING_POSITIONS and positions_count >= REAL_PILOT_MAX_OPEN_POSITIONS:
            warnings.append("Posições reais existentes ignoradas pelo piloto (REAL_PILOT_IGNORE_EXISTING_POSITIONS=true).")

    return {
        "ok": len(reasons) == 0,
        "allowed": len(reasons) == 0,
        "status": ("REAL_PILOT_PREVIEW_ALLOWED" if dry_run and len(reasons) == 0 else ("REAL_PILOT_ALLOWED" if len(reasons) == 0 else "REAL_PILOT_BLOCKED")),
        "version": VERSION,
        "generated_at": _now_br(),
        "reasons": reasons,
        "warnings": warnings,
        "config": {
            "real_execution_enabled": REAL_EXECUTION_ENABLED,
            "real_pilot_enabled": REAL_PILOT_ENABLED,
            "preview_mode": preview_mode,
            "allowed_bots": sorted(REAL_PILOT_ALLOWED_BOTS),
            "allowed_symbols": sorted(REAL_PILOT_ALLOWED_SYMBOLS),
            "max_margin_usdt": REAL_PILOT_MAX_MARGIN_USDT,
            "max_leverage": REAL_PILOT_MAX_LEVERAGE,
            "max_notional_usdt": REAL_PILOT_MAX_NOTIONAL_USDT,
            "max_risk_pct": REAL_PILOT_MAX_RISK_PCT,
            "max_open_positions": REAL_PILOT_MAX_OPEN_POSITIONS,
            "require_ready": REAL_PILOT_REQUIRE_READY,
            "require_entry": REAL_PILOT_REQUIRE_ENTRY,
            "require_stop": REAL_PILOT_REQUIRE_STOP,
            "block_if_positions_unknown": REAL_PILOT_BLOCK_IF_POSITIONS_UNKNOWN,
            "ignore_existing_positions": REAL_PILOT_IGNORE_EXISTING_POSITIONS,
        },
        "trade": {
            "bot": bot,
            "symbol": symbol,
            "side": side,
            "margin_usdt": margin,
            "leverage": leverage,
            "notional_usdt": notional,
            "risk_pct": risk_pct,
            "entry": entry,
            "stop": stop,
            "tp50": tp50,
            "decision": decision,
            "allowed_field": allowed,
        },
        "broker": {
            "available": central_broker is not None,
            "import_error": BROKER_IMPORT_ERROR,
            "ready": ready_payload,
            "positions": positions_payload,
        },
    }


def execution_engine_health() -> Dict[str, Any]:
    orchestrator_payload = None
    if callable(execution_health):
        try:
            orchestrator_payload = execution_health()
        except Exception as exc:
            orchestrator_payload = {"ok": False, "error": str(exc)}

    broker_status = None
    if central_broker is not None and hasattr(central_broker, "status_payload"):
        try:
            broker_status = central_broker.status_payload(check_ready=False)
        except Exception as exc:
            broker_status = {"ok": False, "error": str(exc)}

    return {
        "ok": callable(orchestrate_execution),
        "module": "execution_engine",
        "loaded": True,
        "version": VERSION,
        "generated_at": _now_br(),
        "mode": DEFAULT_ENGINE_MODE,
        "real_execution_enabled": REAL_EXECUTION_ENABLED,
        "paper_execution_enabled": PAPER_EXECUTION_ENABLED,
        "real_pilot_enabled": REAL_PILOT_ENABLED,
        "real_pilot": {
            "allowed_bots": sorted(REAL_PILOT_ALLOWED_BOTS),
            "allowed_symbols": sorted(REAL_PILOT_ALLOWED_SYMBOLS),
            "max_margin_usdt": REAL_PILOT_MAX_MARGIN_USDT,
            "max_leverage": REAL_PILOT_MAX_LEVERAGE,
            "max_notional_usdt": REAL_PILOT_MAX_NOTIONAL_USDT,
            "max_risk_pct": REAL_PILOT_MAX_RISK_PCT,
            "max_open_positions": REAL_PILOT_MAX_OPEN_POSITIONS,
            "require_ready": REAL_PILOT_REQUIRE_READY,
            "require_entry": REAL_PILOT_REQUIRE_ENTRY,
            "require_stop": REAL_PILOT_REQUIRE_STOP,
        },
        "orchestrator_loaded": callable(orchestrate_execution),
        "orchestrator_import_error": ORCHESTRATOR_IMPORT_ERROR,
        "orchestrator": orchestrator_payload,
        "paper_executor_loaded": callable(execute_paper_from_engine),
        "paper_executor_import_error": PAPER_EXECUTOR_IMPORT_ERROR,
        "paper_executor": paper_integrated_health() if callable(paper_integrated_health) else None,
        "broker_loaded": central_broker is not None,
        "broker_import_error": BROKER_IMPORT_ERROR,
        "broker": broker_status,
        "files": {
            "execution_engine_log": str(EXECUTION_ENGINE_LOG_FILE),
        },
        "notes": [
            "Execution Engine V2.5.3 é o ponto único antes de qualquer executor.",
            "Modo OBSERVATION_ONLY cria plano e loga.",
            "Modo PAPER chama Paper Executor integrado quando habilitado.",
            "Modo LIVE chama broker.py em preview seguro quando dry_run=true e em envio real apenas se Real Pilot Guard aprovar.",
            "Em caso de dúvida, bloqueia.",
        ],
    }


def run_execution_engine(
    payload: Dict[str, Any],
    mode: Optional[str] = None,
    dry_run: bool = True,
) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        payload = {}

    mode = _safe_mode(mode or payload.get("mode"))

    if not callable(orchestrate_execution):
        result = {
            "ok": False,
            "status": "ENGINE_BLOCKED",
            "reason": "execution_orchestrator indisponível",
            "error": ORCHESTRATOR_IMPORT_ERROR,
            "version": VERSION,
            "generated_at": _now_br(),
        }
        _append_jsonl(EXECUTION_ENGINE_LOG_FILE, {"event": "EXECUTION_ENGINE_BLOCKED", "payload": result})
        return {"ok": False, "payload": result}

    orchestration = orchestrate_execution(
        payload=payload,
        mode=mode,
        requested_qty=payload.get("requested_qty"),
        capital_allocated=payload.get("capital_allocated"),
        dry_run=dry_run,
    )

    plan = orchestration.get("payload", {}) if isinstance(orchestration, dict) else {}

    engine_status = "PLAN_CREATED"
    engine_ok = bool(orchestration.get("ok")) if isinstance(orchestration, dict) else False
    executor_route = "NONE"
    result_extra_paper = None
    result_extra_live = None
    real_guard = None

    if mode == "OBSERVATION_ONLY":
        executor_route = "PLAN_ONLY"

    elif mode == "PAPER":
        executor_route = "PAPER"
        if not PAPER_EXECUTION_ENABLED:
            engine_ok = False
            engine_status = "PAPER_BLOCKED"
            plan.setdefault("errors", []).append("PAPER bloqueado: CENTRAL_PAPER_EXECUTION_ENABLED=false")
        elif not callable(execute_paper_from_engine):
            engine_ok = False
            engine_status = "PAPER_EXECUTOR_NOT_LOADED"
            plan.setdefault("errors", []).append(f"Paper Executor não carregado: {PAPER_EXECUTOR_IMPORT_ERROR}")
        else:
            paper_result = execute_paper_from_engine({"plan": plan})
            engine_ok = bool(paper_result.get("ok"))
            engine_status = paper_result.get("payload", {}).get("status", "PAPER_RESULT")
            result_extra_paper = paper_result

    elif mode == "LIVE":
        executor_route = "LIVE_GUARD"
        real_guard = validate_real_pilot_guard(payload=payload, plan=plan, dry_run=dry_run)

        if not real_guard.get("allowed"):
            engine_ok = False
            engine_status = "LIVE_BLOCKED_BY_PILOT_GUARD"
            plan.setdefault("errors", []).extend(real_guard.get("reasons") or [])
        elif central_broker is None or not hasattr(central_broker, "place_market_order"):
            engine_ok = False
            engine_status = "LIVE_BROKER_NOT_LOADED"
            plan.setdefault("errors", []).append(f"Broker indisponível: {BROKER_IMPORT_ERROR}")
        else:
            bot = real_guard["trade"]["bot"]
            symbol = real_guard["trade"]["symbol"]
            side = real_guard["trade"]["side"]
            margin = real_guard["trade"]["margin_usdt"]
            leverage = real_guard["trade"]["leverage"]
            risk_pct = real_guard["trade"]["risk_pct"]
            client_tag = str(
                payload.get("client_order_id")
                or payload.get("client_tag")
                or payload.get("trade_id")
                or payload.get("signal_id")
                or f"CQ-{bot}-{symbol}-{int(time.time())}"
            )[:32]

            # Ordem real final. broker.py ainda bloqueia se EXECUTION_MODE/ENABLE_REAL_TRADING/BROKER_DRY_RUN não estiverem corretos.
            live_result = central_broker.place_market_order(
                symbol=symbol,
                side=side,
                margin_usdt=margin,
                reduce_only=False,
                client_tag=client_tag,
                leverage=leverage,
                bot=bot,
                risk_pct=risk_pct,
            )
            result_extra_live = live_result

            if dry_run:
                # Preview seguro: broker.py deve retornar VERIFY/DRY_RUN com sent=False.
                # Isto valida assinatura, quantidade, margem, alavancagem e ready-check
                # sem mandar ordem real para a BingX.
                sent = bool(live_result.get("sent"))
                engine_ok = bool(live_result.get("ok") and not sent)
                engine_status = "LIVE_PREVIEW_OK" if engine_ok else live_result.get("status", "LIVE_PREVIEW_RESULT")
                executor_route = "LIVE_BROKER_PREVIEW"
                if sent:
                    engine_ok = False
                    engine_status = "SAFETY_VIOLATION_PREVIEW_SENT_ORDER"
                    plan.setdefault("errors", []).append("dry_run=true, mas broker retornou sent=true")
            else:
                engine_ok = bool(live_result.get("ok") and live_result.get("sent"))
                engine_status = "LIVE_SENT" if engine_ok else live_result.get("status", "LIVE_RESULT")
                executor_route = "LIVE_BROKER"

    result = {
        "ok": engine_ok,
        "status": engine_status,
        "version": VERSION,
        "generated_at": _now_br(),
        "mode": mode,
        "dry_run": dry_run,
        "executor_route": executor_route,
        "real_execution_enabled": REAL_EXECUTION_ENABLED,
        "paper_execution_enabled": PAPER_EXECUTION_ENABLED,
        "real_pilot_enabled": REAL_PILOT_ENABLED,
        "orchestration": orchestration,
        "plan": plan,
        "real_guard": real_guard,
        "paper_result": result_extra_paper,
        "live_result": result_extra_live,
        "paper_executor_called": result_extra_paper is not None,
        "live_broker_called": result_extra_live is not None,
        "notes": [
            "Execution Engine V2.5.3 recebeu o payload e delegou validação ao Orchestrator.",
            "LIVE com dry_run=true faz preview seguro; LIVE real só envia se o Real Pilot Guard e o broker aprovarem.",
            "O broker.py mantém uma segunda camada de kill switch.",
        ],
    }

    _append_jsonl(EXECUTION_ENGINE_LOG_FILE, {
        "event": "EXECUTION_ENGINE_RUN",
        "version": VERSION,
        "generated_at": _now_br(),
        "epoch": time.time(),
        "mode": mode,
        "dry_run": dry_run,
        "payload": payload,
        "result": result,
    })

    return {"ok": engine_ok, "payload": result}


def execution_engine_test() -> Dict[str, Any]:
    payload = {
        "decision": "ALLOW",
        "bot": "FALCON",
        "setup": "FALCON",
        "symbol": "ETHUSDT",
        "side": "LONG",
        "entry": 3500,
        "sl": 3430,
        "tp50": 3570,
        "risk_pct": 2.0,
        "capital_allocated": 4500,
        "requested_qty": 0.1,
        "signal_id": "EXECUTION-ENGINE-V2.5.3-TEST-FALCON-ETHUSDT-LONG",
    }
    return run_execution_engine(payload=payload, mode="OBSERVATION_ONLY", dry_run=True)


def execution_engine_real_pilot_test(dry_run: bool = True) -> Dict[str, Any]:
    """
    Teste de guarda LIVE.
    Por padrão dry_run=True, então deve bloquear antes de qualquer ordem real.
    Para envio real, use somente depois de conferir health/ready e chamar com dry_run=false via rota controlada.
    """
    payload = {
        "decision": "ALLOW",
        "allowed": True,
        "bot": "FALCON",
        "setup": "FALCON",
        "symbol": "ETHUSDT",
        "side": "LONG",
        "entry": 3500,
        "sl": 3430,
        "tp50": 3570,
        "risk_pct": min(2.0, REAL_PILOT_MAX_RISK_PCT),
        "margin_usdt": min(5.0, REAL_PILOT_MAX_MARGIN_USDT),
        "leverage": min(1, REAL_PILOT_MAX_LEVERAGE),
        "signal_id": "EXECUTION-ENGINE-V2.5.3-REAL-PILOT-TEST-FALCON-ETHUSDT-LONG",
    }
    return run_execution_engine(payload=payload, mode="LIVE", dry_run=dry_run)


def read_execution_engine_log(limit: int = 20) -> Dict[str, Any]:
    if not EXECUTION_ENGINE_LOG_FILE.exists():
        return {
            "ok": True,
            "generated_at": _now_br(),
            "count": 0,
            "items": [],
        }

    try:
        limit = max(1, min(int(limit), 200))
    except Exception:
        limit = 20

    lines = EXECUTION_ENGINE_LOG_FILE.read_text(encoding="utf-8").splitlines()
    selected = lines[-limit:]

    items = []
    for line in selected:
        try:
            items.append(json.loads(line))
        except Exception:
            continue

    return {
        "ok": True,
        "generated_at": _now_br(),
        "count": len(items),
        "items": items,
    }
