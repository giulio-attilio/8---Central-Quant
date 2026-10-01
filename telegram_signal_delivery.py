"""Explicit Telegram-only transport, inactive on import; no bot runtime imports.

Synthetic rehearsals and explicitly authorized informational public signals.
Requires an explicit network authorization on EACH dispatch, a pre-existing local
SQLite ledger, numeric destinations and an injected credential mapping. Never
reads environment, .env or Render, and never prints credentials or HTTP errors.
"""
import hashlib
import http.client
import json
import re
import sqlite3
import ssl
import time
from contextlib import closing
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from falcon_advisory_preview import preview_signal, preview_public_signal

ROUTES = {"FALCON": ("FALCON_TOKEN", "FALCON_CHAT_ID"),
          "DONKEY": ("DONKEY_H4_TOKEN", "DONKEY_H4_CHAT_ID")}
SETUPS = {"FALCON": {"FALCON15", "FALCON30"},
          "DONKEY": {"DONKEY", "DONKEY_ORIGINAL", "EARLY_DONKEY"}}


class DeliveryError(ValueError):
    """Contains a fixed reason code only."""


def _route(bot, values):
    if type(bot) is not str or bot not in ROUTES or type(values) is not dict:
        raise DeliveryError("ROUTE_REQUIRED")
    token_key, chat_key = ROUTES[bot]
    token, chat = values.get(token_key), values.get(chat_key)
    if type(token) is not str or not re.fullmatch(r"[0-9]+:[A-Za-z0-9_-]{20,200}", token):
        raise DeliveryError("BOT_SPECIFIC_TOKEN_REQUIRED")
    if type(chat) is not str or not re.fullmatch(r"-?[1-9][0-9]{0,19}", chat):
        raise DeliveryError("BOT_SPECIFIC_NUMERIC_CHAT_REQUIRED")
    pairs = list(ROUTES.values()) + [("CENTRAL_TELEGRAM_BOT_TOKEN", "CENTRAL_TELEGRAM_CHAT_ID")]
    for tk, ck in pairs:
        other_token = values.get(tk)
        same_bot = (type(other_token) is str
                    and other_token.split(":", 1)[0] == token.split(":", 1)[0])
        if tk != token_key and same_bot and values.get(ck) == chat:
            raise DeliveryError("DESTINATION_COLLISION")
    # Token secret is never stored; bot numeric identity survives token rotation.
    route_id = hashlib.sha256((bot + ":" + token.split(":")[0] + ":" + chat).encode()).hexdigest()
    return token, chat, route_id


def _post(token, chat, text, timeout, reply_markup=None):
    payload = dict(chat_id=chat, text=text, allow_paid_broadcast=False,
                   link_preview_options={"is_disabled": True})
    if reply_markup is not None:
        payload['reply_markup'] = reply_markup
    return _telegram_api(token, 'sendMessage', payload, timeout)


def _telegram_api(token, method, payload, timeout):
    """Exactly one HTTPS POST, fixed host, verified TLS, no redirect/proxy/retry.

Do not enable HTTP debugging or log request URLs: Telegram tokens are in paths.
The caller catches and discards all transport exception strings.
"""
    if method not in {'sendMessage', 'getUpdates', 'answerCallbackQuery', 'getWebhookInfo'}:
        raise DeliveryError('TELEGRAM_METHOD_NOT_ALLOWED')
    connection = http.client.HTTPSConnection("api.telegram.org", timeout=timeout,
                                             context=ssl.create_default_context())
    try:
        payload = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        connection.request("POST", "/bot" + token + "/" + method, body=payload,
                           headers={"Content-Type": "application/json"})
        response = connection.getresponse()
        limit = 1048576 if method == 'getUpdates' else 65536
        raw = response.read(limit + 1)
        if len(raw) > limit:
            return 0, None
        return response.status, json.loads(raw)
    finally:
        connection.close()


def initialize_ledger(path):
    """Explicit provisioning, never implicit reset/recovery of missing state."""
    with closing(sqlite3.connect(path, timeout=5)) as db:
        with db:
            db.execute("CREATE TABLE IF NOT EXISTS delivery_v1 (identity TEXT PRIMARY KEY, candle TEXT UNIQUE NOT NULL, route TEXT NOT NULL, status TEXT NOT NULL, attempted_ms INTEGER NOT NULL, message_id INTEGER)")
            db.execute("CREATE TABLE IF NOT EXISTS delivery_clock_v1 (id INTEGER PRIMARY KEY CHECK(id=1), now_ms INTEGER NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS delivery_pause_v1 (route TEXT PRIMARY KEY, until_ms INTEGER NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS route_check_v1 (bot TEXT PRIMARY KEY, route TEXT NOT NULL, status TEXT NOT NULL)")


def verify_routes_once(*, values, ledger_path, authorized=False):
    """One durable, non-actionable notice per route; ambiguous sends never retry."""
    if authorized is not True:
        return dict(status='BLOCKED', reason='NETWORK_AUTHORIZATION_REQUIRED')
    from pathlib import Path
    try:
        routes = {bot: _route(bot, values) for bot in ROUTES}
        with closing(sqlite3.connect(Path(ledger_path).resolve().as_uri() + '?mode=rw', uri=True, timeout=5)) as db:
            db.execute('PRAGMA synchronous=FULL')
            for bot, (token, chat, route) in routes.items():
                db.execute('BEGIN IMMEDIATE')
                previous = db.execute('SELECT route, status FROM route_check_v1 WHERE bot=?', (bot,)).fetchone()
                if previous:
                    db.rollback()
                    if previous != (route, 'CONFIRMED'):
                        return dict(status='BLOCKED', reason='ROUTE_CHECK_REVIEW_REQUIRED')
                    continue
                db.execute("INSERT INTO route_check_v1 VALUES (?, ?, 'UNKNOWN')", (bot, route))
                db.commit()
                text = (f'TESTE DE INTEGRAÇÃO — {bot} — NÃO OPERAR\n'
                        'Destino de sinais informativos verificado. Nenhuma ordem será enviada.\n'
                        'Este teste não é um sinal de compra ou venda. A ativação depende da verificação dos dois destinos.')
                status = 'UNKNOWN'
                try:
                    code, body = _post(token, chat, text, 10)
                    sent = body.get('result') if type(body) is dict else None
                    if (code == 200 and body.get('ok') is True and type(sent) is dict
                            and type(sent.get('message_id')) is int and sent['message_id'] > 0
                            and type(sent.get('chat')) is dict and type(sent['chat'].get('id')) is int
                            and str(sent['chat']['id']) == chat and sent.get('text') == text):
                        status = 'CONFIRMED'
                except Exception:
                    pass
                with db:
                    db.execute('UPDATE route_check_v1 SET status=? WHERE bot=?', (status, bot))
                if status != 'CONFIRMED':
                    return dict(status='BLOCKED', reason='ROUTE_CHECK_REVIEW_REQUIRED')
        return dict(status='ROUTES_CONFIRMED', live_allowed=False)
    except Exception:
        return dict(status='BLOCKED', reason='ROUTE_CHECK_REVIEW_REQUIRED')


def dispatch_synthetic(bot, signal, *, values, ledger_path, now_ms, expires_at_ms,
                       validity_basis, network_authorized=False, timeout_seconds=10):
    """Dispatch one unmistakably synthetic example, not an actionable alert.

Reservation commits before HTTP. Every reserved identity/candle is at-most-one
attempt, even on crash, lost reply, rejection or route change. This intentionally
prefers a missed message over duplicate delivery; it is not exactly-once delivery.
"""
    return _dispatch(bot, signal, values=values, ledger_path=ledger_path, now_ms=now_ms,
                     expires_at_ms=expires_at_ms, validity_basis=validity_basis,
                     network_authorized=network_authorized, timeout_seconds=timeout_seconds,
                     public=False, data_valid_until_ms=expires_at_ms)


def dispatch_public_signal(bot, signal, *, values, ledger_path, now_ms, expires_at_ms,
                           validity_basis, data_valid_until_ms, network_authorized=False,
                           public_delivery_authorized=False, timeout_seconds=10, donkey_tracking=False):
    """Only for a freshly validated analysis candidate from the trusted workflow.

    The caller derives the data deadline from every frame receipt and quote age.
    This function is not a provenance/authentication boundary for arbitrary callers.
    """
    if public_delivery_authorized is not True:
        return dict(status="BLOCKED", reason="PUBLIC_DELIVERY_AUTHORIZATION_REQUIRED",
                    actual_delivery_confirmed=False, live_allowed=False, manual_trade_authorized=False)
    return _dispatch(bot, signal, values=values, ledger_path=ledger_path, now_ms=now_ms,
                     expires_at_ms=expires_at_ms, validity_basis=validity_basis,
                     network_authorized=network_authorized, timeout_seconds=timeout_seconds,
                     public=True, data_valid_until_ms=data_valid_until_ms, donkey_tracking=donkey_tracking)


def _canonical_number(value):
    return Decimal(str(value)).normalize()


def _falcon_consolidates(candidates):
    if len(candidates) != 2:
        return False
    signals = [item.get("signal") for item in candidates]
    if any(type(signal) is not dict for signal in signals):
        return False
    if {signal.get("setup") for signal in signals} != {"FALCON15", "FALCON30"}:
        return False
    exact = ("symbol", "side", "timeframe", "candle_closed_at_ms")
    if any(signals[0].get(key) != signals[1].get(key) for key in exact):
        return False
    try:
        if any(_canonical_number(signals[0].get(key)) != _canonical_number(signals[1].get(key))
               for key in ("entry", "stop", "tp50")):
            return False
    except Exception:
        return False
    operational = ("expires_at_ms", "validity_basis", "data_valid_until_ms")
    return all(candidates[0].get(key) == candidates[1].get(key) for key in operational)


def _display_price(value):
    return format(float(value), ".10g")


def _manual_message(bot, signals, expires_at_ms, *, opposite_side=None):
    first = signals[0]
    color = "🟢" if first["side"] == "LONG" else "🔴"
    title = "SINAL OPOSTO" if opposite_side else "SINAL MANUAL"
    family = "FALCON" if bot == "FALCON" else "DONKEY"
    risk = abs(first["entry"] - first["stop"]) / first["entry"] * 100
    rr = abs(first["tp50"] - first["entry"]) / abs(first["entry"] - first["stop"])
    expiry = datetime.fromtimestamp(
        expires_at_ms / 1000, ZoneInfo("America/Sao_Paulo")
    ).strftime("%H:%M")
    setup_line = (("Confirmação: FALCON15 + FALCON30" if len(signals) == 2 else
                   f"Confirmação: {first['setup']}") if bot == "FALCON" else
                  f"Setup: {first['setup']}")
    timeframe = "H4" if first["timeframe"] == "4h" else first["timeframe"]
    lines = [
        f"{color} {family} — {title}", "",
        f"{first['symbol']} | {first['side']}",
    ]
    if opposite_side:
        old_color = "🟢" if opposite_side == "LONG" else "🔴"
        lines.extend(["", "Trade manual atual:", f"{old_color} {opposite_side}",
                      "", "Novo setup qualificado:", f"{color} {first['side']}"])
    lines.extend([
        setup_line,
        f"Timeframe: {timeframe}", "",
        f"Entrada: {_display_price(first['entry'])}",
        f"Stop: {_display_price(first['stop'])}",
        f"TP50: {_display_price(first['tp50'])}", "",
        f"Risco até o Stop: {risk:.2f}%",
        f"RR: 1:{format(rr, '.3g')}", "",
        f"Válido até: {expiry}",
        "Modo: SIGNAL-ONLY", "",
        "Nenhuma ordem foi enviada.",
    ])
    return "\n".join(lines)


def dispatch_public_candidates(bot, candidates, *, values, ledger_path,
                               network_authorized=False,
                               public_delivery_authorized=False,
                               manual_tracking=False, timeout_seconds=10):
    """Dispatch ready public candidates, consolidating only an exact Falcon pair.

    Every candidate still receives its own durable delivery identity and candle
    reservation.  Donkey variants and non-identical Falcon candidates are sent
    independently.
    """
    blocked = dict(status="BLOCKED", reason=None, deliveries=[],
                   actual_delivery_confirmed=False, live_allowed=False,
                   manual_trade_authorized=False)
    if public_delivery_authorized is not True:
        return dict(blocked, reason="PUBLIC_DELIVERY_AUTHORIZATION_REQUIRED")
    if type(candidates) is not list or not candidates:
        return dict(blocked, reason="PUBLIC_CANDIDATES_REQUIRED")
    groups = [candidates] if bot == "FALCON" and _falcon_consolidates(candidates) else [
        [candidate] for candidate in candidates
    ]
    deliveries = []
    for group in groups:
        delivered = _dispatch_public_group(
            bot, group, values=values, ledger_path=ledger_path,
            network_authorized=network_authorized, timeout_seconds=timeout_seconds,
            manual_tracking=manual_tracking,
        )
        deliveries.append(delivered)
    status = "CONFIRMED" if deliveries and all(
        item["status"] == "CONFIRMED" for item in deliveries
    ) else (deliveries[0]["status"] if len(deliveries) == 1 else "PARTIAL")
    reason = None if status == "CONFIRMED" else next(
        (item.get("reason") for item in deliveries if item.get("reason")), None
    )
    return dict(blocked, status=status, reason=reason, deliveries=deliveries,
                actual_delivery_confirmed=status == "CONFIRMED")


def _dispatch_public_group(bot, candidates, *, values, ledger_path,
                           network_authorized, timeout_seconds, manual_tracking):
    result = dict(status="BLOCKED", reason=None, actual_delivery_confirmed=False,
                  live_allowed=False, manual_trade_authorized=False)
    started = time.monotonic()
    if network_authorized is not True:
        return dict(result, reason="NETWORK_AUTHORIZATION_REQUIRED")
    if type(timeout_seconds) not in (int, float) or not 0 < timeout_seconds <= 60:
        return dict(result, reason="INVALID_TIMEOUT")
    signals = []
    try:
        for item in candidates:
            signal = item["signal"]
            if (type(signal) is not dict or signal.get("setup") not in SETUPS.get(bot, set())):
                return dict(result, reason="BOT_SETUP_MISMATCH")
            preview = preview_public_signal(
                signal, now_ms=item["now_ms"], expires_at_ms=item["expires_at_ms"],
                validity_basis=item["validity_basis"], for_delivery=True,
            )
            if preview["status"] != "PUBLIC_DATA_PREVIEW":
                return dict(result, reason=preview["reason"])
            deadline = item["data_valid_until_ms"]
            if type(deadline) is not int or not item["now_ms"] < deadline <= item["expires_at_ms"]:
                return dict(result, reason="DATA_VALIDITY_DEADLINE_REQUIRED")
            signals.append(signal)
        token, chat, route = _route(bot, values)
    except (KeyError, DeliveryError) as exc:
        return dict(result, reason=str(exc) if isinstance(exc, DeliveryError) else "PUBLIC_CANDIDATES_REQUIRED")
    now_ms = max(item["now_ms"] for item in candidates)
    expires_at_ms = candidates[0]["expires_at_ms"]
    deadline = min(item["data_valid_until_ms"] for item in candidates)
    identities = [hashlib.sha256((bot + ":" + signal["signal_id"]).encode()).hexdigest()
                  for signal in signals]
    candles = [hashlib.sha256(json.dumps([
        bot, signal["setup"], signal["symbol"], signal["timeframe"],
        signal["candle_closed_at_ms"],
    ]).encode()).hexdigest() for signal in signals]
    db = None
    opposite_side = None
    markup = None
    try:
        from pathlib import Path
        db = sqlite3.connect(Path(ledger_path).resolve().as_uri() + "?mode=rw", uri=True, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA synchronous=FULL")
        db.execute("BEGIN IMMEDIATE")
        last = db.execute("SELECT now_ms FROM delivery_clock_v1 WHERE id=1").fetchone()
        if last and now_ms < last[0]:
            raise DeliveryError("CLOCK_REGRESSION")
        paused = db.execute("SELECT until_ms FROM delivery_pause_v1 WHERE route=?", (route,)).fetchone()
        if paused and now_ms < paused[0]:
            raise DeliveryError("RATE_LIMIT_PAUSE")
        for identity, candle in zip(identities, candles):
            if db.execute(
                "SELECT 1 FROM delivery_v1 WHERE identity=? OR candle=?", (identity, candle)
            ).fetchone():
                raise DeliveryError("PRIOR_ATTEMPT_NO_RETRY")
        if manual_tracking:
            from manual_signal_tracking import active_signal_decision, family_for
            family = family_for(bot, signals[0]["setup"])
            decision, opposite_side = active_signal_decision(
                db, family, signals[0]["symbol"], signals[0]["side"]
            )
            if decision == "SAME_SIDE_ACTIVE":
                raise DeliveryError("MANUAL_TRADE_SAME_SIDE_ACTIVE")
        text = _manual_message(bot, signals, expires_at_ms, opposite_side=opposite_side)
        if len(text.encode("utf-16-le")) // 2 > 4096:
            raise DeliveryError("MESSAGE_TOO_LONG")
        db.execute("INSERT OR REPLACE INTO delivery_clock_v1 VALUES (1, ?)", (now_ms,))
        for identity, candle in zip(identities, candles):
            db.execute(
                "INSERT INTO delivery_v1 VALUES (?, ?, ?, 'UNKNOWN', ?, NULL)",
                (identity, candle, route, now_ms),
            )
        if manual_tracking and opposite_side is None:
            from manual_signal_tracking import offer
            _, markup = offer(db, bot, identities, signals, route, expires_at_ms, now_ms)
        db.commit()
    except Exception as exc:
        if db is not None:
            db.close()
        return dict(result, reason=str(exc) if isinstance(exc, DeliveryError) else "LEDGER_UNAVAILABLE")
    status, message_id, retry_after = "UNKNOWN", None, None
    try:
        elapsed_ms = max(0, int((time.monotonic() - started) * 1000))
        if now_ms + elapsed_ms >= deadline:
            with db:
                db.executemany(
                    "UPDATE delivery_v1 SET status='EXPIRED' WHERE identity=?",
                    [(identity,) for identity in identities],
                )
            db.close()
            return dict(result, reason="EXPIRED_BEFORE_HTTP")
        http_status, body = (_post(token, chat, text, timeout_seconds, reply_markup=markup)
                             if markup else _post(token, chat, text, timeout_seconds))
        if type(body) is dict:
            sent = body.get("result")
            if (http_status == 200 and body.get("ok") is True and type(sent) is dict
                    and type(sent.get("message_id")) is int and sent["message_id"] > 0
                    and type(sent.get("chat")) is dict and type(sent["chat"].get("id")) is int
                    and str(sent["chat"]["id"]) == chat and sent.get("text") == text):
                status, message_id = "CONFIRMED", sent["message_id"]
            elif body.get("ok") is False and type(body.get("error_code")) is int \
                    and 400 <= body["error_code"] < 500:
                status = "REJECTED"
                params = body.get("parameters")
                if body["error_code"] == 429 and type(params) is dict:
                    wait = params.get("retry_after")
                    if type(wait) is int and 0 < wait <= 86400:
                        retry_after = wait
    except Exception:
        pass
    try:
        with db:
            db.executemany(
                "UPDATE delivery_v1 SET status=?, message_id=? WHERE identity=?",
                [(status, message_id, identity) for identity in identities],
            )
            if retry_after:
                db.execute(
                    "INSERT OR REPLACE INTO delivery_pause_v1 VALUES (?, ?)",
                    (route, now_ms + retry_after * 1000),
                )
    except Exception:
        return dict(result, status="UNKNOWN", reason="DELIVERY_RECORD_FAILED")
    finally:
        db.close()
    return dict(result, status=status, actual_delivery_confirmed=status == "CONFIRMED",
                reason=None if status == "CONFIRMED" else "NO_AUTOMATIC_RETRY",
                consolidated=len(signals) == 2, candidate_count=len(signals))


def _dispatch(bot, signal, *, values, ledger_path, now_ms, expires_at_ms, validity_basis,
              network_authorized, timeout_seconds, public, data_valid_until_ms, donkey_tracking=False):
    result = dict(status="BLOCKED", reason=None, actual_delivery_confirmed=False,
                  live_allowed=False, manual_trade_authorized=False)
    started = time.monotonic()
    if network_authorized is not True:
        return dict(result, reason="NETWORK_AUTHORIZATION_REQUIRED")
    if type(timeout_seconds) not in (int, float) or not 0 < timeout_seconds <= 60:
        return dict(result, reason="INVALID_TIMEOUT")
    if (type(bot) is not str or bot not in SETUPS or type(signal) is not dict
            or type(signal.get("setup")) is not str or signal["setup"] not in SETUPS[bot]):
        return dict(result, reason="BOT_SETUP_MISMATCH")
    presenter = preview_public_signal if public else preview_signal
    preview = presenter(signal, now_ms=now_ms, expires_at_ms=expires_at_ms, validity_basis=validity_basis,
                        **({"for_delivery": True} if public else {}))
    if preview["status"] != ("PUBLIC_DATA_PREVIEW" if public else "OFFLINE_PREVIEW"):
        return dict(result, reason=preview["reason"])
    if type(data_valid_until_ms) is not int or not now_ms < data_valid_until_ms <= expires_at_ms:
        return dict(result, reason="DATA_VALIDITY_DEADLINE_REQUIRED")
    text = (_manual_message(bot, [signal], expires_at_ms) if public else
            "TESTE DE INTEGRAÇÃO TELEGRAM — DADOS SINTÉTICOS\n" + preview["message"])
    if len(text.encode("utf-16-le")) // 2 > 4096:
        return dict(result, reason="MESSAGE_TOO_LONG")
    try:
        token, chat, route = _route(bot, values)
    except DeliveryError as exc:
        return dict(result, reason=str(exc))
    identity = hashlib.sha256((bot + ":" + signal["signal_id"]).encode()).hexdigest()
    candle = hashlib.sha256(json.dumps([bot, signal["setup"], signal["symbol"], signal["timeframe"], signal["candle_closed_at_ms"]]).encode()).hexdigest()
    db = None
    markup = None
    try:
        # mode=rw forbids accidental creation after state loss. URI is generated
        # from a local path; the caller cannot supply query options or a remote URI.
        from pathlib import Path
        db = sqlite3.connect(Path(ledger_path).resolve().as_uri() + "?mode=rw", uri=True, timeout=5)
        db.execute("PRAGMA synchronous=FULL")
        db.execute("BEGIN IMMEDIATE")
        last = db.execute("SELECT now_ms FROM delivery_clock_v1 WHERE id=1").fetchone()
        if last and now_ms < last[0]:
            raise DeliveryError("CLOCK_REGRESSION")
        paused = db.execute("SELECT until_ms FROM delivery_pause_v1 WHERE route=?", (route,)).fetchone()
        if paused and now_ms < paused[0]:
            raise DeliveryError("RATE_LIMIT_PAUSE")
        if db.execute("SELECT 1 FROM delivery_v1 WHERE identity=? OR candle=?", (identity, candle)).fetchone():
            raise DeliveryError("PRIOR_ATTEMPT_NO_RETRY")
        if donkey_tracking is True and public and bot == 'DONKEY':
            from donkey_signal_tracking import entry_block_reason
            blocked = entry_block_reason(db, route, signal, candle_closed_at_ms=signal['candle_closed_at_ms'])
            if blocked:
                raise DeliveryError(blocked)
        db.execute("INSERT OR REPLACE INTO delivery_clock_v1 VALUES (1, ?)", (now_ms,))
        db.execute("INSERT INTO delivery_v1 VALUES (?, ?, ?, 'UNKNOWN', ?, NULL)", (identity, candle, route, now_ms))
        if donkey_tracking is True and public and bot == 'DONKEY':
            from donkey_signal_tracking import offer
            markup = offer(db, identity, route, signal, expires_at_ms)
        db.commit()
    except Exception as exc:
        if db is not None:
            db.close()
        return dict(result, reason=str(exc) if isinstance(exc, DeliveryError) else "LEDGER_UNAVAILABLE")
    status, message_id, retry_after = "UNKNOWN", None, None
    try:
        elapsed_ms = max(0, int((time.monotonic() - started) * 1000))
        if now_ms + elapsed_ms >= data_valid_until_ms:
            with db:
                db.execute("UPDATE delivery_v1 SET status='EXPIRED' WHERE identity=?", (identity,))
            db.close()
            return dict(result, reason="EXPIRED_BEFORE_HTTP")
        http_status, body = (_post(token, chat, text, timeout_seconds, reply_markup=markup)
                             if markup else _post(token, chat, text, timeout_seconds))
        if type(body) is dict:
            sent = body.get("result")
            if (http_status == 200 and body.get("ok") is True and type(sent) is dict
                    and type(sent.get("message_id")) is int and sent["message_id"] > 0
                    and type(sent.get("chat")) is dict and type(sent["chat"].get("id")) is int
                    and str(sent["chat"]["id"]) == chat and sent.get("text") == text):
                status, message_id = "CONFIRMED", sent["message_id"]
            elif body.get("ok") is False and type(body.get("error_code")) is int and 400 <= body["error_code"] < 500:
                status = "REJECTED"
                params = body.get("parameters")
                if body["error_code"] == 429 and type(params) is dict:
                    wait = params.get("retry_after")
                    if type(wait) is int and 0 < wait <= 86400:
                        retry_after = wait
    except Exception:
        pass  # Ambiguous acceptance: never retry or disclose exception/URL.
    try:
        with db:
            db.execute("UPDATE delivery_v1 SET status=?, message_id=? WHERE identity=?", (status, message_id, identity))
            if retry_after:
                db.execute("INSERT OR REPLACE INTO delivery_pause_v1 VALUES (?, ?)", (route, now_ms + retry_after * 1000))
    except Exception:
        return dict(result, status="UNKNOWN", reason="DELIVERY_RECORD_FAILED")
    finally:
        db.close()
    return dict(result, status=status, actual_delivery_confirmed=status == "CONFIRMED",
                reason=None if status == "CONFIRMED" else "NO_AUTOMATIC_RETRY")
