"""Persistent advisory tracking for trades entered manually by the operator.

This module has no broker/account imports and never submits or changes orders.
It consumes sampled public quotes and Telegram updates only after explicit runtime
authorization. Schema creation is additive and runs under the authorized worker's
exclusive startup lock before polling begins.
"""
import hashlib
import json
import math
import re
import sqlite3
import time
from contextlib import closing
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo

from donkey_signal_tracking import TrackingPollTransientError, _poll_transport_call


def connect(path):
    db = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=rw", uri=True, timeout=5)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA synchronous=FULL")
    return db


def provision(path):
    """Add manual-tracking tables without resetting delivery or legacy history."""
    with closing(connect(path)) as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            _provision_in_transaction(db)
            db.commit()
        except Exception:
            db.rollback()
            raise


def _provision_in_transaction(db):
    """Create and verify only additive v1 objects under the caller's transaction."""
    expected = {
        "manual_trade_v1": (
            "ref", "group_identity", "route", "family", "setups", "symbol", "side",
            "entry", "stop", "tp50", "expires_ms", "state", "created_ms", "active_ms",
            "tp_ms", "last_quote_ms", "closed_ms", "close_reason",
        ),
        "manual_trade_candidate_v1": ("ref", "identity", "setup"),
        "manual_trade_event_v1": ("ref", "kind", "route", "text", "status", "created_ms"),
        "manual_trade_control_v1": ("route", "chat", "operator", "offset", "clock", "pending_ref"),
        "manual_trade_clock_v1": ("id", "clock"),
    }
    db.execute("SELECT identity FROM delivery_v1 LIMIT 0")
    db.execute("""CREATE TABLE IF NOT EXISTS manual_trade_v1 (
        ref TEXT PRIMARY KEY, group_identity TEXT UNIQUE NOT NULL,
        route TEXT NOT NULL, family TEXT NOT NULL, setups TEXT NOT NULL,
        symbol TEXT NOT NULL, side TEXT NOT NULL, entry REAL NOT NULL,
        stop REAL NOT NULL, tp50 REAL NOT NULL, expires_ms INTEGER NOT NULL,
        state TEXT NOT NULL, created_ms INTEGER NOT NULL, active_ms INTEGER,
        tp_ms INTEGER, last_quote_ms INTEGER, closed_ms INTEGER,
        close_reason TEXT)""")
    db.execute("""CREATE TABLE IF NOT EXISTS manual_trade_candidate_v1 (
        ref TEXT NOT NULL, identity TEXT UNIQUE NOT NULL, setup TEXT NOT NULL,
        PRIMARY KEY(ref, identity), FOREIGN KEY(ref) REFERENCES manual_trade_v1(ref))""")
    db.execute("""CREATE TABLE IF NOT EXISTS manual_trade_event_v1 (
        ref TEXT NOT NULL, kind TEXT NOT NULL, route TEXT NOT NULL,
        text TEXT NOT NULL, status TEXT NOT NULL, created_ms INTEGER NOT NULL,
        PRIMARY KEY(ref, kind))""")
    db.execute("""CREATE TABLE IF NOT EXISTS manual_trade_control_v1 (
        route TEXT PRIMARY KEY, chat TEXT NOT NULL, operator INTEGER NOT NULL,
        offset INTEGER NOT NULL, clock INTEGER NOT NULL, pending_ref TEXT)""")
    db.execute("""CREATE TABLE IF NOT EXISTS manual_trade_clock_v1 (
        id INTEGER PRIMARY KEY CHECK(id=1), clock INTEGER NOT NULL)""")
    db.execute("INSERT OR IGNORE INTO manual_trade_clock_v1 VALUES (1, 0)")
    for table, columns in expected.items():
        actual = tuple(row[1] for row in db.execute(f"PRAGMA table_info({table})"))
        if actual != columns:
            raise sqlite3.DatabaseError("MANUAL_TRACKING_SCHEMA_MISMATCH")


def family_for(bot, setup):
    if bot == "FALCON" and setup in {"FALCON15", "FALCON30"}:
        return "FALCON"
    if bot == "DONKEY" and setup in {"DONKEY", "DONKEY_ORIGINAL", "EARLY_DONKEY"}:
        return setup
    raise ValueError("MANUAL_TRADE_FAMILY_REQUIRED")


def active_signal_decision(db, family, symbol, side, *, exclude_ref=None):
    """Return SAME/OPPOSITE using family+symbol; same side takes precedence."""
    rows = db.execute(
        "SELECT ref, side FROM manual_trade_v1 WHERE family=? AND symbol=? AND state='ACTIVE'",
        (family, symbol),
    ).fetchall()
    sides = [row["side"] for row in rows if row["ref"] != exclude_ref]
    if side in sides:
        return "SAME_SIDE_ACTIVE", side
    opposite = "SHORT" if side == "LONG" else "LONG"
    if opposite in sides:
        return "OPPOSITE_ACTIVE", opposite
    return None, None


def offer(db, bot, identities, signals, route, expires_ms, created_ms):
    """Persist one advisory offer inside the delivery reservation transaction."""
    if not signals or len(identities) != len(signals):
        raise ValueError("MANUAL_TRADE_OFFER_REQUIRED")
    first = signals[0]
    family = family_for(bot, first["setup"])
    if any(family_for(bot, signal["setup"]) != family for signal in signals):
        raise ValueError("MANUAL_TRADE_FAMILY_MISMATCH")
    group_identity = hashlib.sha256(
        ("manual-trade:" + ":".join(sorted(identities))).encode()
    ).hexdigest()
    ref = group_identity[:32]
    setups = [signal["setup"] for signal in signals]
    db.execute(
        """INSERT INTO manual_trade_v1
        (ref, group_identity, route, family, setups, symbol, side, entry, stop, tp50,
         expires_ms, state, created_ms)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'WAITING', ?)""",
        (ref, group_identity, route, family, json.dumps(setups), first["symbol"],
         first["side"], first["entry"], first["stop"], first["tp50"], expires_ms,
         created_ms),
    )
    for identity, signal in zip(identities, signals):
        db.execute(
            "INSERT INTO manual_trade_candidate_v1 VALUES (?, ?, ?)",
            (ref, identity, signal["setup"]),
        )
    return ref, {
        "inline_keyboard": [[{
            "text": "✅ ENTREI NO TRADE",
            "callback_data": "mt:" + ref,
        }]]
    }


def _price(value):
    return format(float(value), ".10g")


def _panel(db):
    rows = db.execute(
        "SELECT * FROM manual_trade_v1 WHERE state='ACTIVE' ORDER BY active_ms, ref"
    ).fetchall()
    if not rows:
        return "📋 TRADES MANUAIS ATIVOS\n\nNenhum trade manual ativo.", None
    lines = ["📋 TRADES MANUAIS ATIVOS", ""]
    keyboard = []
    for number, row in enumerate(rows, 1):
        color = "🟢" if row["side"] == "LONG" else "🔴"
        since = datetime.fromtimestamp(
            row["active_ms"] / 1000, ZoneInfo("America/Sao_Paulo")
        ).strftime("%d/%m %H:%M")
        lines.extend([
            f"{number}. {color} {row['symbol']}",
            f"   {row['family']} | {row['side']}",
            f"   Entrada: {_price(row['entry'])}",
            f"   Stop atual: {_price(row['stop'])}",
            f"   TP50: {_price(row['tp50'])}",
            f"   Desde: {since}",
            "   TP50: ✅ atingido" if row["tp_ms"] is not None else "   TP50: ⏳ pendente",
            "",
        ])
        keyboard.append([
            {"text": "✏️ ATUALIZAR STOP", "callback_data": "ms:" + row["ref"]},
            {"text": "⚪ ENCERRAR TRADE", "callback_data": "mc:" + row["ref"]},
        ])
    return "\n".join(lines).rstrip(), {"inline_keyboard": keyboard}


def _valid_update(update):
    return (type(update) is dict and type(update.get("update_id")) is int
            and update["update_id"] >= 0)


def _authorized_sender(payload, operator, chat):
    sender = payload.get("from")
    target = payload.get("chat")
    return (type(sender) is dict and sender.get("is_bot") is False
            and type(sender.get("id")) is int and sender["id"] == operator
            and type(target) is dict and type(target.get("id")) is int
            and str(target["id"]) == chat)


def _parse_positive_number(text):
    if type(text) is not str or re.fullmatch(r"\s*[0-9]+(?:[.,][0-9]+)?\s*", text) is None:
        return None
    try:
        value = Decimal(text.strip().replace(",", "."))
    except InvalidOperation:
        return None
    if not value.is_finite() or value <= 0:
        return None
    number = float(value)
    return number if math.isfinite(number) and number > 0 else None


class ManualTradeTracker:
    """Poll both signal bots and track only the operator's explicit manual entries."""

    def __init__(self, path, values, operator_id, *, authorized=False):
        if authorized is not True or type(operator_id) is not int or operator_id <= 0:
            raise ValueError("MANUAL_TRACKING_OPERATOR_AND_AUTHORIZATION_REQUIRED")
        from telegram_signal_delivery import _route
        self.path = path
        self.operator = operator_id
        self.routes = {}
        with closing(connect(path)) as db, db:
            db.execute("SELECT ref FROM manual_trade_v1 LIMIT 0")
            for bot in ("FALCON", "DONKEY"):
                token, chat, route = _route(bot, values)
                old = db.execute(
                    "SELECT * FROM manual_trade_control_v1 WHERE route=?", (route,)
                ).fetchone()
                if old and (old["chat"] != chat or old["operator"] != operator_id):
                    raise ValueError("MANUAL_TRACKING_IDENTITY_CHANGED")
                db.execute(
                    "INSERT OR IGNORE INTO manual_trade_control_v1 VALUES (?, ?, ?, 0, 0, NULL)",
                    (route, chat, operator_id),
                )
                self.routes[bot] = dict(token=token, chat=chat, route=route)

    @staticmethod
    def _clock(db, route, now):
        old = db.execute(
            "SELECT clock FROM manual_trade_control_v1 WHERE route=?", (route,)
        ).fetchone()[0]
        if type(now) is not int or now <= 0 or now < old:
            raise ValueError("MANUAL_TRACKING_CLOCK_REGRESSION")
        db.execute(
            "UPDATE manual_trade_control_v1 SET clock=? WHERE route=?", (now, route)
        )

    def check_polling(self):
        from telegram_signal_delivery import _telegram_api
        for item in self.routes.values():
            code, body = _telegram_api(item["token"], "getWebhookInfo", {}, 10)
            if (code != 200 or type(body) is not dict or body.get("ok") is not True
                    or type(body.get("result")) is not dict
                    or body["result"].get("url") != ""):
                raise ValueError("MANUAL_TRACKING_POLLING_NOT_AVAILABLE")

    def accept(self, bot, update, now):
        """Persist one Telegram update and return safe UI actions for poll()."""
        if bot not in self.routes or not _valid_update(update):
            raise ValueError("MANUAL_TRACKING_UPDATE_INVALID")
        item = self.routes[bot]
        answer = "Ação não autorizada ou sinal indisponível."
        outbound = None
        with closing(connect(self.path)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            self._clock(db, item["route"], now)
            control = db.execute(
                "SELECT * FROM manual_trade_control_v1 WHERE route=?", (item["route"],)
            ).fetchone()
            if update["update_id"] < control["offset"]:
                return dict(answer="Atualização já processada.")
            query = update.get("callback_query")
            message = update.get("message")
            if type(query) is dict:
                source_message = query.get("message")
                data = query.get("data")
                if (type(source_message) is dict
                        and _authorized_sender({"from": query.get("from"),
                                                "chat": source_message.get("chat")},
                                               self.operator, item["chat"])
                        and type(source_message.get("message_id")) is int
                        and type(data) is str
                        and re.fullmatch(r"m[tsc]:[a-f0-9]{32}", data)):
                    action, ref = data[:2], data[3:]
                    row = db.execute(
                        "SELECT * FROM manual_trade_v1 WHERE ref=?", (ref,)
                    ).fetchone()
                    if action == "mt" and row:
                        bound = db.execute(
                            """SELECT 1 FROM manual_trade_candidate_v1 c
                            JOIN delivery_v1 d ON d.identity=c.identity
                            WHERE c.ref=? AND d.route=? AND d.status='CONFIRMED'
                              AND d.message_id=?""",
                            (ref, item["route"], source_message["message_id"]),
                        ).fetchone()
                        if bound and row["state"] == "WAITING" and now < row["expires_ms"]:
                            block, _ = active_signal_decision(
                                db, row["family"], row["symbol"], row["side"], exclude_ref=ref
                            )
                            if block == "SAME_SIDE_ACTIVE":
                                answer = "Já existe tracking ativo nessa família, ativo e direção."
                            else:
                                db.execute(
                                    "UPDATE manual_trade_v1 SET state='ACTIVE', active_ms=? WHERE ref=?",
                                    (now, ref),
                                )
                                answer = "Tracking manual ativado. Nenhuma ordem foi enviada."
                        elif bound and row["state"] == "WAITING" and now >= row["expires_ms"]:
                            db.execute(
                                "UPDATE manual_trade_v1 SET state='EXPIRED', closed_ms=?, close_reason='EXPIRED' WHERE ref=?",
                                (now, ref),
                            )
                            answer = "Sinal vencido. Tracking não iniciado."
                        elif bound:
                            answer = "Tracking já iniciado ou encerrado."
                    elif action == "ms" and row and row["state"] == "ACTIVE":
                        db.execute(
                            "UPDATE manual_trade_control_v1 SET pending_ref=? WHERE route=?",
                            (ref, item["route"]),
                        )
                        answer = "Informe o novo stop."
                        outbound = dict(text=f"Informe o novo stop para {row['symbol']}:")
                    elif action == "mc" and row and row["state"] == "ACTIVE":
                        db.execute(
                            """UPDATE manual_trade_v1 SET state='CLOSED', closed_ms=?,
                            close_reason='MANUAL_CLOSE' WHERE ref=?""",
                            (now, ref),
                        )
                        answer = "Trade manual encerrado. Nenhuma ordem foi alterada."
            elif type(message) is dict and _authorized_sender(message, self.operator, item["chat"]):
                text = message.get("text")
                if type(text) is str and text.strip().split("@", 1)[0] == "/ativos":
                    panel, markup = _panel(db)
                    outbound = dict(text=panel, reply_markup=markup)
                elif control["pending_ref"]:
                    row = db.execute(
                        "SELECT * FROM manual_trade_v1 WHERE ref=?", (control["pending_ref"],)
                    ).fetchone()
                    value = _parse_positive_number(text)
                    if row and row["state"] == "ACTIVE" and value is not None:
                        db.execute(
                            "UPDATE manual_trade_v1 SET stop=? WHERE ref=?",
                            (value, row["ref"]),
                        )
                        db.execute(
                            "UPDATE manual_trade_control_v1 SET pending_ref=NULL WHERE route=?",
                            (item["route"],),
                        )
                        outbound = dict(text=f"Stop de {row['symbol']} atualizado para {_price(value)}")
                    else:
                        outbound = dict(text="Stop inválido. Informe apenas um número positivo.")
            db.execute(
                "UPDATE manual_trade_control_v1 SET offset=? WHERE route=?",
                (update["update_id"] + 1, item["route"]),
            )
        return dict(answer=answer, outbound=outbound)

    def poll(self, now):
        from telegram_signal_delivery import _post
        started = time.monotonic()
        for bot, item in self.routes.items():
            with closing(connect(self.path)) as db:
                offset = db.execute(
                    "SELECT offset FROM manual_trade_control_v1 WHERE route=?", (item["route"],)
                ).fetchone()[0]
            code, body = _poll_transport_call(
                item["token"], "getUpdates",
                dict(offset=offset, limit=100, timeout=0,
                     allowed_updates=["callback_query", "message"]),
            )
            if (type(code) is not int or code == 0 or code in {408, 425, 429}
                    or 500 <= code <= 599):
                raise TrackingPollTransientError()
            if (code != 200 or type(body) is not dict or body.get("ok") is not True
                    or type(body.get("result")) is not list):
                raise ValueError("MANUAL_TRACKING_POLL_FAILED_NO_RETRY")
            for update in body["result"]:
                effective_now = now + max(0, int((time.monotonic() - started) * 1000))
                action = self.accept(bot, update, effective_now)
                query = update.get("callback_query")
                if type(query) is dict and type(query.get("id")) is str and len(query["id"]) <= 256:
                    _poll_transport_call(
                        item["token"], "answerCallbackQuery",
                        dict(callback_query_id=query["id"], text=action["answer"]),
                    )
                outbound = action.get("outbound")
                if outbound:
                    _post(item["token"], item["chat"], outbound["text"], 10,
                          reply_markup=outbound.get("reply_markup"))

    def observe(self, snapshot, now, quote_max_age_ms):
        """Apply one fresh sampled public quote; TP50 is informational and one-shot."""
        if (type(snapshot) is not dict or snapshot.get("synthetic") is not False
                or snapshot.get("connected") is not True or type(now) is not int
                or type(quote_max_age_ms) is not int or quote_max_age_ms <= 0):
            raise ValueError("MANUAL_TRACKING_PUBLIC_QUOTE_REQUIRED")
        quote = snapshot.get("quote")
        observed = snapshot.get("observed_at_ms")
        if (type(quote) is not dict or type(observed) is not int
                or type(quote.get("at_ms")) is not int
                or not quote["at_ms"] <= observed <= now
                or now - quote["at_ms"] > quote_max_age_ms
                or type(quote.get("price")) not in (int, float)
                or not math.isfinite(quote["price"]) or quote["price"] <= 0):
            raise ValueError("MANUAL_TRACKING_PUBLIC_QUOTE_REQUIRED")
        symbol, price, quote_ms = snapshot.get("symbol"), quote["price"], quote["at_ms"]
        if type(symbol) is not str:
            raise ValueError("MANUAL_TRACKING_PUBLIC_QUOTE_REQUIRED")
        with closing(connect(self.path)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            old_clock = db.execute("SELECT clock FROM manual_trade_clock_v1 WHERE id=1").fetchone()[0]
            if now < old_clock:
                raise ValueError("MANUAL_TRACKING_CLOCK_REGRESSION")
            db.execute("UPDATE manual_trade_clock_v1 SET clock=? WHERE id=1", (now,))
            rows = db.execute(
                "SELECT * FROM manual_trade_v1 WHERE symbol=? AND state='ACTIVE'", (symbol,)
            ).fetchall()
            for row in rows:
                if quote_ms < row["active_ms"] or (row["last_quote_ms"] is not None
                                                    and quote_ms <= row["last_quote_ms"]):
                    continue
                is_long = row["side"] == "LONG"
                hit_stop = price <= row["stop"] if is_long else price >= row["stop"]
                hit_tp = price >= row["tp50"] if is_long else price <= row["tp50"]
                if hit_stop:
                    db.execute(
                        """UPDATE manual_trade_v1 SET state='CLOSED', last_quote_ms=?,
                        closed_ms=?, close_reason='STOP' WHERE ref=?""",
                        (quote_ms, now, row["ref"]),
                    )
                    text = (f"🟡 STOP — {row['symbol']}\n\n{row['family']} | {row['side']}\n"
                            f"Stop atingido: {_price(row['stop'])}\n\nTrade manual encerrado.\n"
                            "Novos sinais desta estratégia/ativo foram liberados.\n\n"
                            "Nenhuma ordem foi alterada.")
                    db.execute(
                        "INSERT INTO manual_trade_event_v1 VALUES (?, 'STOP', ?, ?, 'PENDING', ?)",
                        (row["ref"], row["route"], text, now),
                    )
                elif row["tp_ms"] is None and hit_tp:
                    db.execute(
                        "UPDATE manual_trade_v1 SET tp_ms=?, last_quote_ms=? WHERE ref=?",
                        (now, quote_ms, row["ref"]),
                    )
                    text = (f"🔵 TP50 — {row['symbol']}\n\n{row['family']} | {row['side']}\n"
                            f"TP50 atingido: {_price(row['tp50'])}\n\nTrade continua ATIVO.\n"
                            f"Stop atual: {_price(row['stop'])}\n\nNenhuma ordem foi alterada.")
                    db.execute(
                        "INSERT INTO manual_trade_event_v1 VALUES (?, 'TP50', ?, ?, 'PENDING', ?)",
                        (row["ref"], row["route"], text, now),
                    )
                else:
                    db.execute(
                        "UPDATE manual_trade_v1 SET last_quote_ms=? WHERE ref=?",
                        (quote_ms, row["ref"]),
                    )

    def flush(self):
        from telegram_signal_delivery import _post
        by_route = {item["route"]: item for item in self.routes.values()}
        while True:
            with closing(connect(self.path)) as db, db:
                db.execute("BEGIN IMMEDIATE")
                if db.execute(
                    "SELECT 1 FROM manual_trade_event_v1 WHERE status='UNKNOWN'"
                ).fetchone():
                    raise ValueError("MANUAL_TRACKING_NOTICE_UNKNOWN_NO_RETRY")
                event = db.execute(
                    "SELECT * FROM manual_trade_event_v1 WHERE status='PENDING' ORDER BY created_ms, rowid LIMIT 1"
                ).fetchone()
                if not event:
                    return
                db.execute(
                    "UPDATE manual_trade_event_v1 SET status='UNKNOWN' WHERE ref=? AND kind=?",
                    (event["ref"], event["kind"]),
                )
            route = by_route.get(event["route"])
            if not route:
                raise ValueError("MANUAL_TRACKING_ROUTE_CHANGED")
            code, body = _post(route["token"], route["chat"], event["text"], 10)
            sent = body.get("result") if type(body) is dict else None
            if (code != 200 or type(body) is not dict or body.get("ok") is not True or type(sent) is not dict
                    or type(sent.get("message_id")) is not int or sent["message_id"] <= 0
                    or type(sent.get("chat")) is not dict
                    or str(sent["chat"].get("id")) != route["chat"]
                    or sent.get("text") != event["text"]):
                raise ValueError("MANUAL_TRACKING_NOTICE_UNKNOWN_NO_RETRY")
            with closing(connect(self.path)) as db, db:
                db.execute(
                    "UPDATE manual_trade_event_v1 SET status='CONFIRMED' WHERE ref=? AND kind=?",
                    (event["ref"], event["kind"]),
                )
