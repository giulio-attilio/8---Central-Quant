"""Local presentation for synthetic replay or explicitly public-source previews.

All times and the expiry policy are supplied by the caller. Validation
does not qualify a clock, prove provenance, or authorize manual/live trading.
Never import bots.falcon to use this module: that module starts runtime threads.
"""

import math
import re


def preview_signal(signal, *, now_ms, expires_at_ms, validity_basis, seen_ids=()):
    """Project an allowlist into a synthetic alert; never mutate caller state.

The caller owns the fixture's expiry and duplicate set. Neither is persistent
delivery idempotency. No TTL, price-deviation tolerance or position size is
inferred. Raw Falcon ``signal_ts`` is not a verified candle-close timestamp.
"""
    return _preview(signal, now_ms=now_ms, expires_at_ms=expires_at_ms,
                    validity_basis=validity_basis, seen_ids=seen_ids, public=False)


def preview_public_signal(signal, *, now_ms, expires_at_ms, validity_basis, seen_ids=(), for_delivery=False):
    """Validated informational text; formatting never authorizes transport.

    Default text is a local preview. Explicit delivery formatting avoids labeling
    a public alert synthetic, without claiming executed orders or guaranteed fills.
    """
    return _preview(signal, now_ms=now_ms, expires_at_ms=expires_at_ms,
                    validity_basis=validity_basis, seen_ids=seen_ids, public=True, for_delivery=for_delivery is True)


def _preview(signal, *, now_ms, expires_at_ms, validity_basis, seen_ids, public, for_delivery=False):
    result = {
        "status": "REJECTED", "reason": None, "message": None,
        "live_allowed": False, "delivery_allowed": False,
        "source_qualified": False, "manual_trade_authorized": False,
    }

    def reject(reason):
        return {**result, "reason": reason}

    if public:
        if (type(signal) is not dict or signal.get("synthetic") is not False
                or signal.get("source") != "BINGX_PUBLIC_SWAP"):
            return reject("PUBLIC_SOURCE_REQUIRED")
    elif type(signal) is not dict or signal.get("synthetic") is not True:
        return reject("SYNTHETIC_FIXTURE_REQUIRED")
    for key in ("signal_id", "symbol", "setup", "timeframe"):
        value = signal.get(key)
        if type(value) is not str or not re.fullmatch(r"[A-Za-z0-9_:/.-]{1,100}", value):
            return reject("INVALID_IDENTIFIER")
    setup_frames = {"FALCON15": "15m", "FALCON30": "15m", "DONKEY": "4h",
                    "DONKEY_ORIGINAL": "4h", "EARLY_DONKEY": "4h"}
    if signal["setup"] not in setup_frames:
        return reject("INVALID_SETUP")
    if signal["timeframe"] != setup_frames[signal["setup"]]:
        return reject("INVALID_TIMEFRAME")
    if type(seen_ids) not in (tuple, list, set, frozenset) or any(type(x) is not str for x in seen_ids):
        return reject("INVALID_DUPLICATE_CONTEXT")
    if signal["signal_id"] in seen_ids:
        return reject("DUPLICATE")
    if type(validity_basis) is not str or not validity_basis.strip() or len(validity_basis) > 200:
        return reject("EXPLICIT_VALIDITY_BASIS_REQUIRED")
    times = (signal.get("candle_closed_at_ms"), signal.get("generated_at_ms"), now_ms, expires_at_ms)
    if any(type(x) is not int or x < 0 for x in times):
        return reject("INVALID_TIME")
    closed, generated, now, expiry = times
    if not closed <= generated <= now or expiry <= generated:
        return reject("INCONSISTENT_TIME")
    if now >= expiry:
        return reject("EXPIRED")
    if signal.get("invalidated") is not False:
        return reject("INVALIDATED_OR_UNKNOWN")
    side = signal.get("side")
    if side not in ("LONG", "SHORT"):
        return reject("INVALID_SIDE")
    prices = [signal.get(key) for key in ("entry", "stop", "tp50")]
    if any(type(x) not in (int, float) for x in prices):
        return reject("INVALID_PRICE")
    try:
        valid_prices = all(math.isfinite(x) and x > 0 for x in prices)
    except OverflowError:
        valid_prices = False
    if not valid_prices:
        return reject("INVALID_PRICE")
    entry, stop, target = prices
    if not (stop < entry < target if side == "LONG" else target < entry < stop):
        return reject("INVALID_PRICE_ORDER")
    # Never forward raw input, order IDs, status OPEN, risk_pct or account fields.
    header = "PRÉVIA LOCAL — DADOS PÚBLICOS — NÃO OPERAR\n" if public else "SIMULAÇÃO OFFLINE — NÃO OPERAR\n"
    id_label = "ID do candidato" if public else "ID de exemplo"
    expiry_label = "Expiração da prévia" if public else "Expiração do exemplo"
    message = (
        header +
        f"{signal['setup']} | {signal['symbol']} | {side} | {signal['timeframe']}\n"
        f"{id_label}: {signal['signal_id']}\n"
        f"Entrada de referência (não é fill): {entry}\n"
        f"Stop de referência (não é ordem de proteção): {stop}\n"
        f"TP50 de referência (não é ordem): {target}\n"
        f"Fechamento do candle: {closed} ms UTC Unix\n"
        f"Geração: {generated} ms UTC Unix | Avaliação: {now} ms UTC Unix\n"
        f"{expiry_label}: {expiry} ms UTC Unix\n"
        "Invalidar no vencimento ou se a estratégia revogar o exemplo.\n"
        "Sem cotação atual: distância do preço e viabilidade de entrada não avaliadas.\n"
        "Sem envio, posição registrada, gestão, tamanho de ordem ou rentabilidade comprovada."
    )
    if public:
        message = message.replace("revogar o exemplo", "revogar o candidato").replace(
            "Sem cotação atual: distância do preço e viabilidade de entrada não avaliadas.",
            "Prévia de análise: não constitui liberação de entrada ou confirmação de preço executável.")
        if for_delivery:
            message = message.replace("PRÉVIA LOCAL — DADOS PÚBLICOS — NÃO OPERAR", "SINAL INFORMATIVO — DADOS PÚBLICOS — SEM EXECUÇÃO AUTOMÁTICA")
            message = message.replace("Expiração da prévia", "Validade do alerta").replace(
                "Sem envio, posição registrada, gestão, tamanho de ordem ou rentabilidade comprovada.",
                "Nenhuma ordem enviada ou proteção instalada. Sem gestão de posições ou rentabilidade comprovada.")
    return {**result, "status": "PUBLIC_DATA_PREVIEW" if public else "OFFLINE_PREVIEW", "message": message}
