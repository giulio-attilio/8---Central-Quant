"""Reference-only Donkey follow-ups. Never imports trading/position runtimes.

Explicit schema provisioning and runtime opt-in. No network or IO on import.
Quotes are sampled, not a tick history: crossings between samples can be missed.
"""
import errno
import hashlib
import http.client
import json
import re
import socket
import sqlite3
import time
from contextlib import closing
from pathlib import Path

from bingx_public_signal_source import validate_snapshot, PERIODS

SETUPS = {'DONKEY', 'DONKEY_ORIGINAL', 'EARLY_DONKEY'}
TRANSIENT_POLL_HTTP_STATUS = frozenset({408, 425, 429})
TRANSIENT_POLL_ERRNOS = frozenset(value for value in (
    getattr(errno, name, None) for name in (
        'ECONNABORTED', 'ECONNREFUSED', 'ECONNRESET', 'EHOSTDOWN',
        'EHOSTUNREACH', 'ENETDOWN', 'ENETRESET', 'ENETUNREACH', 'EPIPE', 'ETIMEDOUT'))
    if value is not None)


class TrackingPollTransientError(Exception):
    """Remote polling failed before any ambiguous local persistence."""


def _poll_transport_call(token, method, payload):
    from telegram_signal_delivery import _telegram_api
    try:
        return _telegram_api(token, method, payload, 10)
    except (json.JSONDecodeError, UnicodeDecodeError, http.client.HTTPException):
        raise TrackingPollTransientError() from None
    except OSError as error:
        if (isinstance(error, (TimeoutError, ConnectionError, socket.gaierror))
                or error.errno in TRANSIENT_POLL_ERRNOS):
            raise TrackingPollTransientError() from None
        raise


def connect(path):
    db = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=rw', uri=True, timeout=5)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA synchronous=FULL')
    return db


def provision(path):
    """Add isolated tables to an existing ledger; never reset existing state."""
    with closing(connect(path)) as db, db:
        db.execute('SELECT identity FROM delivery_v1 LIMIT 0')
        db.execute('CREATE TABLE IF NOT EXISTS donkey_reference_v1 (ref TEXT PRIMARY KEY, identity TEXT UNIQUE NOT NULL, route TEXT NOT NULL, signal TEXT NOT NULL, expires INTEGER NOT NULL, state TEXT NOT NULL, active_ms INTEGER, tp_ms INTEGER, last_quote INTEGER, last_h4 INTEGER, stop REAL NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS donkey_reference_events_v1 (ref TEXT NOT NULL, kind TEXT NOT NULL, text TEXT NOT NULL, status TEXT NOT NULL, PRIMARY KEY(ref, kind))')
        db.execute('CREATE TABLE IF NOT EXISTS donkey_reference_control_v1 (id INTEGER PRIMARY KEY CHECK(id=1), route TEXT NOT NULL, operator INTEGER NOT NULL, offset INTEGER NOT NULL, clock INTEGER NOT NULL)')


def entry_block_reason(db, route, signal, *, candle_closed_at_ms=None):
    """Called under BEGIN IMMEDIATE; scope is route + symbol + setup, not side."""
    rows = db.execute("SELECT signal, state, last_quote FROM donkey_reference_v1 WHERE route=? AND state IN ('ACTIVE','RUNNER','CLOSED')", (route,))
    for encoded, state, last_quote in rows:
        previous = json.loads(encoded)
        if (previous['symbol'], previous['setup']) != (signal['symbol'], signal['setup']):
            continue
        if state in ('ACTIVE', 'RUNNER'):
            return 'DONKEY_REFERENCE_ALREADY_ACTIVE'
        if candle_closed_at_ms is not None and (last_quote is None or candle_closed_at_ms <= last_quote):
            return 'DONKEY_WAIT_NEXT_H4_AFTER_EXIT'
    return None


def offer(db, identity, route, signal, expires):
    """Inside the delivery reservation transaction, before sendMessage."""
    if signal.get('setup') not in SETUPS or signal.get('synthetic') is not False:
        raise ValueError('DONKEY_REFERENCE_REQUIRED')
    ref = hashlib.sha256(('donkey-reference:' + identity).encode()).hexdigest()[:32]
    fields = {key: signal[key] for key in ('setup', 'symbol', 'side', 'entry', 'stop', 'tp50')}
    if 'candle_closed_at_ms' in signal:
        fields['candle_closed_at_ms'] = signal['candle_closed_at_ms']
    db.execute("INSERT INTO donkey_reference_v1 VALUES (?, ?, ?, ?, ?, 'WAITING', NULL, NULL, NULL, NULL, ?)",
               (ref, identity, route, json.dumps(fields), expires, signal['stop']))
    return {'inline_keyboard': [[{'text': '✅ Entrei na operação', 'callback_data': 'dq:' + ref}]]}


class ReferenceTracker:
    def __init__(self, path, values, operator_id, *, authorized=False):
        if authorized is not True or type(operator_id) is not int or operator_id <= 0:
            raise ValueError('DONKEY_OPERATOR_AND_AUTHORIZATION_REQUIRED')
        from telegram_signal_delivery import _route
        self.path = path
        self.token, self.chat, self.route = _route('DONKEY', values)
        self.operator = operator_id
        with closing(connect(path)) as db, db:
            old = db.execute('SELECT * FROM donkey_reference_control_v1 WHERE id=1').fetchone()
            if old and (old['route'] != self.route or old['operator'] != operator_id):
                raise ValueError('DONKEY_REFERENCE_IDENTITY_CHANGED')
            db.execute('INSERT OR IGNORE INTO donkey_reference_control_v1 VALUES (1, ?, ?, 0, 0)',
                       (self.route, operator_id))

    def _clock(self, db, now):
        old = db.execute('SELECT clock FROM donkey_reference_control_v1 WHERE id=1').fetchone()[0]
        if type(now) is not int or now < old or now <= 0:
            raise ValueError('DONKEY_REFERENCE_CLOCK_REGRESSION')
        db.execute('UPDATE donkey_reference_control_v1 SET clock=? WHERE id=1', (now,))

    def check_polling(self):
        from telegram_signal_delivery import _telegram_api
        code, body = _telegram_api(self.token, 'getWebhookInfo', {}, 10)
        if (code != 200 or type(body) is not dict or body.get('ok') is not True
                or type(body.get('result')) is not dict or body['result'].get('url') != ''):
            raise ValueError('DONKEY_POLLING_NOT_AVAILABLE')

    def accept(self, update, now):
        """Atomic cursor and activation. Only the configured human/chat/message."""
        if type(update) is not dict or type(update.get('update_id')) is not int or update['update_id'] < 0:
            raise ValueError('DONKEY_UPDATE_INVALID')
        answer = 'Clique não autorizado ou sinal indisponível.'
        with closing(connect(self.path)) as db, db:
            db.execute('BEGIN IMMEDIATE')
            self._clock(db, now)
            offset = db.execute('SELECT offset FROM donkey_reference_control_v1 WHERE id=1').fetchone()[0]
            if update['update_id'] < offset:
                return 'Clique já processado.'
            query = update.get('callback_query')
            if type(query) is dict:
                sender, message, data = query.get('from'), query.get('message'), query.get('data')
                if (type(sender) is dict and type(sender.get('id')) is int and sender['id'] == self.operator
                        and sender.get('is_bot') is False and type(message) is dict
                        and type(message.get('chat')) is dict and type(message['chat'].get('id')) is int
                        and str(message['chat']['id']) == self.chat
                        and type(message.get('message_id')) is int
                        and type(data) is str and re.fullmatch(r'dq:[a-f0-9]{32}', data)):
                    row = db.execute('SELECT r.*, d.message_id, d.status AS delivery_status FROM donkey_reference_v1 r JOIN delivery_v1 d ON d.identity=r.identity WHERE r.ref=?', (data[3:],)).fetchone()
                    if (row and row['route'] == self.route and row['delivery_status'] == 'CONFIRMED'
                            and row['message_id'] == message['message_id']):
                        if row['state'] != 'WAITING':
                            answer = 'Acompanhamento já iniciado ou encerrado.'
                        elif now >= row['expires']:
                            db.execute("UPDATE donkey_reference_v1 SET state='EXPIRED' WHERE ref=?", (row['ref'],))
                            answer = 'Sinal vencido. Acompanhamento não iniciado.'
                        elif entry_block_reason(db, self.route, json.loads(row['signal']),
                                                candle_closed_at_ms=json.loads(row['signal']).get('candle_closed_at_ms')):
                            answer = 'Acompanhamento ativo ou candle anterior à última saída nesta variante.'
                        else:
                            db.execute("UPDATE donkey_reference_v1 SET state='ACTIVE', active_ms=? WHERE ref=?", (now, row['ref']))
                            answer = 'Acompanhamento de referência ativado. Nenhuma ordem enviada.'
            db.execute('UPDATE donkey_reference_control_v1 SET offset=? WHERE id=1', (update['update_id'] + 1,))
        return answer

    def poll(self, now):
        started = time.monotonic()
        with closing(connect(self.path)) as db:
            offset = db.execute('SELECT offset FROM donkey_reference_control_v1 WHERE id=1').fetchone()[0]
        code, body = _poll_transport_call(self.token, 'getUpdates',
                                          dict(offset=offset, limit=100, timeout=0,
                                               allowed_updates=['callback_query']))
        if (type(code) is not int or code == 0 or code in TRANSIENT_POLL_HTTP_STATUS
                or 500 <= code <= 599):
            raise TrackingPollTransientError()
        if code == 200 and (type(body) is not dict or body.get('ok') is not True
                            or type(body.get('result')) is not list):
            raise TrackingPollTransientError()
        if code != 200:
            raise ValueError('DONKEY_POLL_FAILED_NO_RETRY')
        for update in body['result']:
            answer = self.accept(update, now + max(0, int((time.monotonic() - started) * 1000)))
            query = update.get('callback_query')
            if type(query) is dict and type(query.get('id')) is str and len(query['id']) <= 256:
                # This acknowledgment does not modify tracking, and is never retried.
                _poll_transport_call(self.token, 'answerCallbackQuery',
                                     dict(callback_query_id=query['id'], text=answer))

    def observe(self, snapshot, now, policy):
        snap = validate_snapshot(snapshot, now_ms=now, frame_max_age_ms=policy['snapshot_max_age_ms'],
                                 quote_max_age_ms=policy['quote_max_age_ms'])
        rows = snap['frames'].get('4h')
        if rows is None or len(rows) < 21:
            raise ValueError('DONKEY_REFERENCE_H4_REQUIRED')
        rows = rows[-80:]  # Same 80-row H4 window as legacy remainder management.
        price, quote_ms = snap['quote']['price'], snap['quote']['at_ms']
        # Match preparar_df: EWM span=20, adjust=False. Exclude forming candle.
        ema = rows[0][4]
        closed = []
        for row in rows[:-1]:
            ema = (2 / 21) * row[4] + (19 / 21) * ema
            closed.append((row[0] + PERIODS['4h'], row[4], ema))
        with closing(connect(self.path)) as db, db:
            db.execute('BEGIN IMMEDIATE')
            self._clock(db, now)
            items = db.execute("SELECT * FROM donkey_reference_v1 WHERE route=? AND state IN ('ACTIVE','RUNNER')", (self.route,)).fetchall()
            for item in items:
                sig = json.loads(item['signal'])
                if sig['symbol'] != snap['symbol'] or quote_ms < item['active_ms']:
                    continue
                if item['last_quote'] is not None and quote_ms <= item['last_quote']:
                    continue
                long = sig['side'] == 'LONG'
                kind, state, stop, tp_ms = None, item['state'], item['stop'], item['tp_ms']
                if (price <= stop if long else price >= stop):
                    kind, state = 'STOP', 'CLOSED'
                    detail = f'Stop de referência atingido: {stop:.10g}. Acompanhamento encerrado.'
                elif state == 'ACTIVE' and (price >= sig['tp50'] if long else price <= sig['tp50']):
                    kind, state, tp_ms = 'TP50', 'RUNNER', now
                    stop = sig['entry'] * (1.001 if long else 0.999)
                    detail = (f'TP50 de referência atingido: {sig["tp50"]:.10g}.\n'
                              f'50% considerado realizado apenas na simulação.\nStop de referência dos 50% restantes: {stop:.10g}.')
                elif state == 'RUNNER':
                    for end, close, average in closed:
                        if end <= max(tp_ms, item['last_h4'] or 0):
                            continue
                        if (close < average if long else close > average):
                            kind, state = 'EMA20_EXIT', 'CLOSED'
                            detail = (f'Saída de referência dos 50% restantes: H4 fechou contra EMA20.\n'
                                      f'Fechamento: {close:.10g} | EMA20: {average:.10g}. Acompanhamento encerrado.')
                            break
                db.execute('UPDATE donkey_reference_v1 SET state=?, stop=?, tp_ms=?, last_quote=?, last_h4=? WHERE ref=?',
                           (state, stop, tp_ms, quote_ms, closed[-1][0], item['ref']))
                if kind:
                    text = (f'🐴 {sig["setup"]} | {sig["symbol"]} | {sig["side"]}\n'
                            f'Referência {item["ref"][:8]} — entrada {sig["entry"]:.10g}\n{detail}\n'
                            'Acompanhamento hipotético por preços amostrados. Não confirma sua execução. Nenhuma ordem alterada.')
                    db.execute("INSERT INTO donkey_reference_events_v1 VALUES (?, ?, ?, 'PENDING')", (item['ref'], kind, text))

    def flush(self):
        from telegram_signal_delivery import _post
        while True:
            with closing(connect(self.path)) as db, db:
                db.execute('BEGIN IMMEDIATE')
                if db.execute("SELECT 1 FROM donkey_reference_events_v1 WHERE status='UNKNOWN'").fetchone():
                    raise ValueError('DONKEY_NOTICE_UNKNOWN_NO_RETRY')
                event = db.execute("SELECT * FROM donkey_reference_events_v1 WHERE status='PENDING' ORDER BY rowid LIMIT 1").fetchone()
                if not event:
                    return
                db.execute("UPDATE donkey_reference_events_v1 SET status='UNKNOWN' WHERE ref=? AND kind=?", (event['ref'], event['kind']))
            code, body = _post(self.token, self.chat, event['text'], 10)
            sent = body.get('result') if type(body) is dict else None
            if (code != 200 or body.get('ok') is not True or type(sent) is not dict
                    or type(sent.get('message_id')) is not int or sent['message_id'] <= 0
                    or type(sent.get('chat')) is not dict or str(sent['chat'].get('id')) != self.chat
                    or sent.get('text') != event['text']):
                raise ValueError('DONKEY_NOTICE_UNKNOWN_NO_RETRY')
            with closing(connect(self.path)) as db, db:
                db.execute("UPDATE donkey_reference_events_v1 SET status='CONFIRMED' WHERE ref=? AND kind=?", (event['ref'], event['kind']))
