"""Explicit signals worker entry point. No startup or environment reads on import.

Only --run reads the four Telegram environment values, after authorization and
configuration checks. Never reads .env, broker credentials or operational modules.
"""
import argparse
import json
import os
import re
from pathlib import Path
import signal
import sys
import threading
import sqlite3
import time
from contextlib import closing

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from signal_only_service import run_service, validate_service_config, diagnose_public_cycle, exclusive_service
from falcon_advisory_offline import reviewed_analysis
from donkey_advisory_offline import reviewed_analysis as review_donkey
from telegram_signal_delivery import initialize_ledger, ROUTES, verify_routes_once


REVIEWED_HALT_ID = '20260930-205047'
SECOND_REVIEWED_HALT_ID = '20260930-222218'
THIRD_REVIEWED_HALT_ID = '20261001-110546'
FOURTH_REVIEWED_HALT_ID = '20261002-070002'
# Incident IDs are derived from the reviewed failure timestamps. Each later
# review is valid only when every earlier durable receipt is intact.
REVIEWED_HALT_REVIEWS = {
    REVIEWED_HALT_ID: (),
    SECOND_REVIEWED_HALT_ID: (REVIEWED_HALT_ID,),
    THIRD_REVIEWED_HALT_ID: (REVIEWED_HALT_ID, SECOND_REVIEWED_HALT_ID),
    # Operator-reviewed FRAME_EXPIRED / tracking_observe incident. The causal
    # fix is c22950e; the complete production ledger review followed b696651.
    FOURTH_REVIEWED_HALT_ID: (REVIEWED_HALT_ID, SECOND_REVIEWED_HALT_ID,
                            THIRD_REVIEWED_HALT_ID),
}
REVIEWED_HALT_IDS = tuple(REVIEWED_HALT_REVIEWS)
REVIEWED_HALT_BYTES = b'MANUAL_REVIEW_REQUIRED\n'


def reviewed_halt_archive(path, review=REVIEWED_HALT_ID):
    return Path(str(Path(path).resolve()) + '.halted.reviewed-' + review)


def load_inputs(config_path):
    # Explicit nonsecret JSON only. No strategy or freshness defaults.
    path = Path(config_path)
    if path.suffix != '.json' or path.stat().st_size > 65536:
        raise ValueError('CONFIG_FILE_INVALID')
    config = validate_service_config(json.loads(path.read_text(encoding='utf-8-sig')))
    sources = {bot: (ROOT / 'signals_sources' / (bot.lower() + '.txt')).read_text(encoding='utf-8')
               for bot in ('FALCON', 'DONKEY')}
    reviewed_analysis(sources['FALCON'])
    review_donkey(sources['DONKEY'])
    return config, sources


def provision_ledger(path):
    """One explicit first-use provision; never overwrite/reset an existing ledger."""
    path = Path(path)
    if Path(str(path) + '.halted').exists():
        raise ValueError('MANUAL_REVIEW_REQUIRED')
    with path.open('xb'):
        pass
    # If initialization fails, retain the file for investigation, never retry/reset.
    initialize_ledger(path)


def inspect_halted_ledger(path):
    """Read-only counts, not message contents, identifiers or credentials.

    Never repairs, clears a latch, starts a service or enables delivery.
    Unknown schema/status or IO failure keeps the review incomplete.
    """
    report = dict(status='HALTED_LEDGER_REVIEW', review_complete=False,
                  delivery_allowed=False, live_allowed=False)
    try:
        with closing(sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True, timeout=5)) as db:
            db.execute('PRAGMA query_only=ON')
            db.execute('BEGIN')
            if db.execute('PRAGMA quick_check').fetchone() != ('ok',):
                return dict(report, reason='LEDGER_INTEGRITY')
            tables = {
                'delivery': ('delivery_v1', 'status', {'CONFIRMED', 'UNKNOWN', 'REJECTED', 'EXPIRED'}),
                'routes': ('route_check_v1', 'status', {'CONFIRMED', 'UNKNOWN'}),
                'references': ('donkey_reference_v1', 'state', {'WAITING', 'ACTIVE', 'RUNNER', 'EXPIRED', 'CLOSED'}),
                'notices': ('donkey_reference_events_v1', 'status', {'PENDING', 'UNKNOWN', 'CONFIRMED'}),
            }
            for name, (table, column, allowed) in tables.items():
                counts = dict(db.execute(f'SELECT {column}, COUNT(*) FROM {table} GROUP BY {column}'))
                if not set(counts) <= allowed:
                    return dict(report, reason='LEDGER_STATE_REVIEW_REQUIRED')
                report[name] = counts
            now = time.time_ns() // 1000000
            clocks = [r[0] for r in db.execute('SELECT now_ms FROM delivery_clock_v1')]
            clocks += [r[0] for r in db.execute('SELECT clock FROM donkey_reference_control_v1')]
            clocks += [r[0] for r in db.execute('SELECT attempted_ms FROM delivery_v1')]
            clocks += [value for r in db.execute(
                'SELECT active_ms, tp_ms, last_quote, last_h4 FROM donkey_reference_v1')
                for value in r if value is not None]
            report['clock_ahead'] = any(type(c) is not int or c < 0 or c > now for c in clocks)
            from manual_signal_tracking import inspect_manual_tracking
            manual, manual_reason = inspect_manual_tracking(db, now_ms=now)
            report.update(manual)
            report['clock_ahead'] = (report['clock_ahead'] or
                manual['manual_integrity'].get('clock_ahead', False))
            if manual_reason:
                return dict(report, reason=manual_reason)
            if report['clock_ahead']:
                return dict(report, reason='LEDGER_CLOCK_REVIEW_REQUIRED')
            if any(report[name].get('UNKNOWN', 0) for name in ('delivery', 'routes', 'notices')):
                return dict(report, reason='LEDGER_STATE_REVIEW_REQUIRED')
        return dict(report, review_complete=True, reason='READ_ONLY_NO_RECOVERY')
    except Exception:
        return dict(report, reason='LEDGER_INSPECTION_FAILED_REDACTED')


def frame_expired_review_is_valid(audit):
    """Require the current full RO audit, not a transient delivery/trade count.

    Called only for the fourth human-reviewed incident. Historical approvals
    retain their frozen criteria. Legacy H4 classification is produced by the
    factual rollout rule in inspect_manual_tracking, never inferred here.
    """
    if (type(audit) is not dict or audit.get('status') != 'HALTED_LEDGER_REVIEW'
            or audit.get('reason') != 'READ_ONLY_NO_RECOVERY'
            or audit.get('review_complete') is not True or audit.get('clock_ahead') is not False
            or audit.get('delivery_allowed') is not False or audit.get('live_allowed') is not False):
        return False

    def counts(value, allowed, *, exact=False):
        return (type(value) is dict and (set(value) == allowed if exact else set(value) <= allowed)
                and all(type(n) is int and n >= 0 for n in value.values()))

    manual = audit.get('manual_integrity')
    zero_keys = set(('orphan_participants orphan_h4 orphan_events orphan_pending_inputs '
        'invalid_states invalid_participants incompatible_active invalid_h4 invalid_tp50 '
        'invalid_close invalid_events invalid_controls invalid_trades invalid_prices '
        'invalid_timestamps invalid_clocks ambiguous_notices').split())
    if (type(manual) is not dict or set(manual) != zero_keys | {'schema_ok', 'clock_ahead'}
            or manual['schema_ok'] is not True or manual['clock_ahead'] is not False
            or any(type(manual[k]) is not int or manual[k] != 0 for k in zero_keys)):
        return False
    h4 = audit.get('manual_h4_integrity')
    h4_zero = set(('duplicate_ref cursor_for_falcon cursor_for_inactive_trade '
        'invalid_cursor_timestamp cursor_off_h4_grid invalid_activation_timestamp '
        'cursor_not_after_activation cursor_ahead_observation_clock invalid_closed_timestamp '
        'cursor_after_close missing_for_donkey_stop indeterminate_stop_without_h4_cursor').split())
    if (not counts(h4, h4_zero | {'legacy_stop_without_h4_cursor'}, exact=True)
            or any(h4[k] != 0 for k in h4_zero)):
        return False
    buckets = {
        'delivery': {'CONFIRMED', 'REJECTED', 'EXPIRED'},
        'routes': {'CONFIRMED'},
        'references': {'WAITING', 'ACTIVE', 'RUNNER', 'EXPIRED', 'CLOSED'},
        'notices': {'PENDING', 'CONFIRMED'},
        'manual_trades': {'WAITING', 'ACTIVE', 'EXPIRED', 'CLOSED'},
        'manual_notices': {'PENDING', 'CONFIRMED'},
        'manual_closes': {'STOP', 'MANUAL_CLOSE', 'EXPIRED'},
    }
    if (any(not counts(audit.get(k), allowed) for k, allowed in buckets.items())
            or audit.get('routes') != {'CONFIRMED': len(ROUTES)}):
        return False
    summaries = {'manual_participants': {'rows'}, 'manual_h4': {'rows', 'active_with_cursor'},
        'manual_pending_inputs': {'count'}, 'manual_tp50': {'reached'},
        'manual_protection': {'positive_stops'}}
    if any(not counts(audit.get(k), fields, exact=True) for k, fields in summaries.items()):
        return False
    trades, closes = audit['manual_trades'], audit['manual_closes']
    active, closed = trades.get('ACTIVE', 0), trades.get('CLOSED', 0)
    return (audit['manual_protection']['positive_stops'] == sum(trades.values())
            and audit['manual_participants']['rows'] >= sum(trades.values())
            and audit['manual_pending_inputs']['count'] <= active
            and audit['manual_tp50']['reached'] <= active + closed
            and audit['manual_h4']['active_with_cursor'] <= min(active, audit['manual_h4']['rows'])
            and closes.get('STOP', 0) + closes.get('MANUAL_CLOSE', 0) == closed
            and closes.get('EXPIRED', 0) == trades.get('EXPIRED', 0)
            and h4['legacy_stop_without_h4_cursor'] <= closes.get('STOP', 0))


def resume_reviewed_halt(path, review):
    """One human-approved incident only; archive the latch, never edit the DB.

    A later failure cannot reuse this approval even if the command is unchanged.
    A crash after archive creation but before completion fails closed.
    """
    required_reviews = REVIEWED_HALT_REVIEWS.get(review)
    if required_reviews is None:
        return False
    path = Path(path)
    halted = Path(str(path) + '.halted')
    archive = reviewed_halt_archive(path, review)
    try:
        with exclusive_service(path):
            if path.is_symlink() or halted.is_symlink() or archive.exists() or archive.is_symlink():
                return False
            for required_review in required_reviews:
                receipt = reviewed_halt_archive(path, required_review)
                if receipt.is_symlink() or not receipt.is_file() or receipt.read_bytes() != REVIEWED_HALT_BYTES:
                    return False
            if halted.read_bytes() != REVIEWED_HALT_BYTES:
                return False
            audit = inspect_halted_ledger(path)
            if review == FOURTH_REVIEWED_HALT_ID:
                approved = frame_expired_review_is_valid(audit)
            else:
                approved = (audit.get('review_complete') is True and audit.get('clock_ahead') is False
                    and audit.get('delivery') == {'CONFIRMED': 85}
                    and audit.get('routes') == {'CONFIRMED': 2}
                    and audit.get('references') == {} and audit.get('notices') == {})
            if not approved:
                return False
            # Exclusive archive is the durable one-use receipt. Never overwrite it.
            with archive.open('xb') as handle:
                handle.write(REVIEWED_HALT_BYTES)
                handle.flush()
                os.fsync(handle.fileno())
            directory = None
            try:
                if os.name != 'nt':
                    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
                    os.fsync(directory)
                halted.unlink()  # Original bytes are preserved in the fsynced archive.
                if directory is not None:
                    os.fsync(directory)
            except OSError:
                if not halted.exists():
                    with halted.open('xb') as handle:
                        handle.write(REVIEWED_HALT_BYTES)
                        handle.flush()
                        os.fsync(handle.fileno())
                raise
            finally:
                if directory is not None:
                    os.close(directory)
        return True
    except Exception:
        return False


def execute(config, sources, ledger_path, *, authorized=False, verify_telegram=False, donkey_operator_id=None,
            reviewed_halt=None):
    if authorized is not True:
        return dict(status='BLOCKED', reason='EXPLICIT_AUTHORIZATIONS_REQUIRED')
    path = Path(ledger_path).resolve()
    halted = Path(str(path) + '.halted')
    if halted.exists() and reviewed_halt is not None:
        if reviewed_halt not in REVIEWED_HALT_REVIEWS:
            return dict(status='BLOCKED', reason='REVIEWED_RESUME_REFUSED')
        archive = reviewed_halt_archive(path, reviewed_halt)
        if archive.exists() or archive.is_symlink():
            return dict(status='BLOCKED', reason='REVIEWED_HALT_RECEIPT_PRESENT_REVIEW_REQUIRED')
        if not resume_reviewed_halt(path, reviewed_halt):
            return dict(status='BLOCKED', reason='REVIEWED_RESUME_REFUSED')
        print(json.dumps(dict(status='REVIEWED_HALT_ARCHIVED', live_allowed=False)), flush=True)
    if not path.is_file() or halted.exists():
        if path.is_file() and halted.exists():
            print(json.dumps(inspect_halted_ledger(path)), flush=True)
        return dict(status='BLOCKED', reason='LEDGER_OR_MANUAL_REVIEW_REQUIRED')
    values = {key: os.environ.get(key) for pair in ROUTES.values() for key in pair}
    stop = threading.Event()
    previous = {}
    try:
        if verify_telegram:
            checked = verify_routes_once(values=values, ledger_path=str(path), authorized=True)
            print(json.dumps(checked), flush=True)
            if checked.get('status') != 'ROUTES_CONFIRMED':
                return checked
        for sig in (signal.SIGTERM, signal.SIGINT):
            previous[sig] = signal.signal(sig, lambda *_: stop.set())
        options = {} if donkey_operator_id is None else dict(donkey_operator_id=donkey_operator_id)
        result = run_service(config, sources, values=values, ledger_path=str(path), stop_event=stop,
                             service_authorized=True, public_data_authorized=True,
                             public_delivery_authorized=True, **options)
        if result.get('status') not in ('STOPPED',):
            try:
                with halted.open('x', encoding='utf-8') as handle:
                    handle.write('MANUAL_REVIEW_REQUIRED\n')
            except FileExistsError:
                pass
        return result
    finally:
        values.clear()
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def diagnose_once(config, sources, *, authorized=False, state_dir=Path('/var/data'), attempt=None):
    """Claim on the mounted disk before any public request; never reset or retry."""
    blocked = dict(status='BLOCKED', delivery_allowed=False, live_allowed=False,
                   capacity_approved=False)
    if authorized is not True:
        return dict(blocked, reason='PUBLIC_READ_AUTHORIZATION_REQUIRED')
    if attempt is not None and (not isinstance(attempt, str) or
                               re.fullmatch(r'[a-z0-9][a-z0-9-]{0,47}', attempt) is None):
        return dict(blocked, reason='DIAGNOSTIC_ATTEMPT_INVALID')
    state_dir = Path(state_dir)
    if state_dir.is_symlink() or not os.path.ismount(state_dir):
        return dict(blocked, reason='PERSISTENT_MOUNT_REQUIRED')
    suffix = '' if attempt is None else '-' + attempt
    marker = state_dir / ('signals-public-diagnostic' + suffix + '.claimed')
    try:
        with marker.open('xb') as handle:
            handle.write(b'CLAIMED_NO_AUTOMATIC_RETRY\n')
            handle.flush()
            os.fsync(handle.fileno())
        if os.name != 'nt':
            directory = os.open(state_dir, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    except FileExistsError:
        return dict(blocked, reason='DIAGNOSTIC_ALREADY_CLAIMED_NO_RETRY')
    except OSError:
        return dict(blocked, reason='DIAGNOSTIC_STORAGE_REVIEW_REQUIRED')
    print(json.dumps(dict(status='DIAGNOSTIC_STARTED', delivery_allowed=False,
                          live_allowed=False)), flush=True)
    return diagnose_public_cycle(config, sources, public_data_authorized=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Isolated Falcon/Donkey signals worker')
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check-config', action='store_true')
    mode.add_argument('--initialize-ledger', action='store_true')
    mode.add_argument('--initialize-donkey-tracking', action='store_true')
    mode.add_argument('--run', action='store_true')
    mode.add_argument('--diagnose-public', action='store_true')
    mode.add_argument('--diagnose-public-once', action='store_true')
    parser.add_argument('--config', required=True)
    parser.add_argument('--ledger')
    parser.add_argument('--diagnostic-attempt')
    parser.add_argument('--authorize-service', action='store_true')
    parser.add_argument('--authorize-public-data', action='store_true')
    parser.add_argument('--authorize-telegram', action='store_true')
    parser.add_argument('--verify-telegram-once', action='store_true')
    parser.add_argument('--donkey-operator-id', type=int)
    parser.add_argument('--authorize-donkey-polling', action='store_true')
    parser.add_argument('--reviewed-halt', choices=REVIEWED_HALT_IDS)
    args = parser.parse_args(argv)
    if args.reviewed_halt is not None and not args.run:
        parser.error('--reviewed-halt requires --run')
    if args.diagnostic_attempt is not None and not args.diagnose_public_once:
        parser.error('--diagnostic-attempt requires --diagnose-public-once')
    if args.verify_telegram_once and not args.run:
        parser.error('--verify-telegram-once requires --run')
    if args.donkey_operator_id is not None and (not args.run or args.donkey_operator_id <= 0 or not args.authorize_donkey_polling):
        parser.error('Donkey tracking requires --run, a positive operator id and explicit polling authorization')
    if args.authorize_donkey_polling and args.donkey_operator_id is None:
        parser.error('Donkey polling requires an explicit operator id')
    if args.run and args.donkey_operator_id is None:
        parser.error('Signal delivery requires manual tracking and an explicit operator id')
    try:
        config, sources = load_inputs(args.config)
        if args.check_config:
            result = dict(status='CONFIG_VALID', live_allowed=False)
        elif args.diagnose_public_once:
            result = diagnose_once(config, sources, authorized=args.authorize_public_data,
                                   attempt=args.diagnostic_attempt)
        elif args.diagnose_public:
            result = diagnose_public_cycle(config, sources,
                                           public_data_authorized=args.authorize_public_data)
        elif not args.ledger:
            result = dict(status='BLOCKED', reason='LEDGER_PATH_REQUIRED')
        elif args.initialize_donkey_tracking:
            from donkey_signal_tracking import provision as provision_legacy_tracking
            from manual_signal_tracking import provision as provision_manual_tracking
            provision_legacy_tracking(args.ledger)
            provision_manual_tracking(args.ledger)
            result = dict(status='TRACKING_SCHEMA_INITIALIZED', live_allowed=False)
        elif args.initialize_ledger:
            provision_ledger(args.ledger)
            result = dict(status='LEDGER_INITIALIZED', live_allowed=False)
        else:
            result = execute(config, sources, args.ledger, authorized=(args.authorize_service
                             and args.authorize_public_data and args.authorize_telegram),
                             verify_telegram=args.verify_telegram_once, donkey_operator_id=args.donkey_operator_id,
                             reviewed_halt=args.reviewed_halt)
    except Exception:
        result = dict(status='BLOCKED', reason='CONFIGURATION_OR_STORAGE_REVIEW_REQUIRED')
    # Never print exceptions, paths, config, credentials or raw transport responses.
    allowed = {key: result[key] for key in ('status', 'reason', 'cycles', 'evaluations', 'confirmed',
               'stage', 'completed_symbols', 'planned_symbols', 'scan_seconds', 'discarded_snapshots',
               'cycle_with_pause_seconds', 'reason_counts', 'delivery_allowed', 'capacity_approved') if key in result}
    allowed['live_allowed'] = False
    print(json.dumps(allowed), flush=True)
    return 0 if result.get('status') in ('CONFIG_VALID', 'LEDGER_INITIALIZED', 'TRACKING_SCHEMA_INITIALIZED', 'STOPPED', 'DIAGNOSTIC_COMPLETE') else 1


if __name__ == '__main__':
    raise SystemExit(main())
