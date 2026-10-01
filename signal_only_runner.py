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
from signal_only_service import run_service, validate_service_config, diagnose_public_cycle
from falcon_advisory_offline import reviewed_analysis
from donkey_advisory_offline import reviewed_analysis as review_donkey
from telegram_signal_delivery import initialize_ledger, ROUTES, verify_routes_once


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
            report['clock_ahead'] = any(type(c) is not int or c > now for c in clocks)
        return dict(report, review_complete=True, reason='READ_ONLY_NO_RECOVERY')
    except Exception:
        return dict(report, reason='LEDGER_INSPECTION_FAILED_REDACTED')


def execute(config, sources, ledger_path, *, authorized=False, verify_telegram=False, donkey_operator_id=None):
    if authorized is not True:
        return dict(status='BLOCKED', reason='EXPLICIT_AUTHORIZATIONS_REQUIRED')
    path = Path(ledger_path).resolve()
    halted = Path(str(path) + '.halted')
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
    args = parser.parse_args(argv)
    if args.diagnostic_attempt is not None and not args.diagnose_public_once:
        parser.error('--diagnostic-attempt requires --diagnose-public-once')
    if args.verify_telegram_once and not args.run:
        parser.error('--verify-telegram-once requires --run')
    if args.donkey_operator_id is not None and (not args.run or args.donkey_operator_id <= 0 or not args.authorize_donkey_polling):
        parser.error('Donkey tracking requires --run, a positive operator id and explicit polling authorization')
    if args.authorize_donkey_polling and args.donkey_operator_id is None:
        parser.error('Donkey polling requires an explicit operator id')
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
            from donkey_signal_tracking import provision
            provision(args.ledger)
            result = dict(status='TRACKING_SCHEMA_INITIALIZED', live_allowed=False)
        elif args.initialize_ledger:
            provision_ledger(args.ledger)
            result = dict(status='LEDGER_INITIALIZED', live_allowed=False)
        else:
            result = execute(config, sources, args.ledger, authorized=(args.authorize_service
                             and args.authorize_public_data and args.authorize_telegram),
                             verify_telegram=args.verify_telegram_once, donkey_operator_id=args.donkey_operator_id)
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
