"""Explicit signals worker entry point. No startup or environment reads on import.

Only --run reads the four Telegram environment values, after authorization and
configuration checks. Never reads .env, broker credentials or operational modules.
"""
import argparse
import json
import os
from pathlib import Path
import signal
import sys
import threading

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from signal_only_service import run_service, validate_service_config, diagnose_public_cycle
from falcon_advisory_offline import reviewed_analysis
from donkey_advisory_offline import reviewed_analysis as review_donkey
from telegram_signal_delivery import initialize_ledger, ROUTES


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


def execute(config, sources, ledger_path, *, authorized=False):
    if authorized is not True:
        return dict(status='BLOCKED', reason='EXPLICIT_AUTHORIZATIONS_REQUIRED')
    path = Path(ledger_path).resolve()
    halted = Path(str(path) + '.halted')
    if not path.is_file() or halted.exists():
        return dict(status='BLOCKED', reason='LEDGER_OR_MANUAL_REVIEW_REQUIRED')
    values = {key: os.environ.get(key) for pair in ROUTES.values() for key in pair}
    stop = threading.Event()
    previous = {}
    try:
        for sig in (signal.SIGTERM, signal.SIGINT):
            previous[sig] = signal.signal(sig, lambda *_: stop.set())
        result = run_service(config, sources, values=values, ledger_path=str(path), stop_event=stop,
                             service_authorized=True, public_data_authorized=True,
                             public_delivery_authorized=True)
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


def diagnose_once(config, sources, *, authorized=False, state_dir=Path('/var/data')):
    """Claim on the mounted disk before any public request; never reset or retry."""
    blocked = dict(status='BLOCKED', delivery_allowed=False, live_allowed=False,
                   capacity_approved=False)
    if authorized is not True:
        return dict(blocked, reason='PUBLIC_READ_AUTHORIZATION_REQUIRED')
    state_dir = Path(state_dir)
    if state_dir.is_symlink() or not os.path.ismount(state_dir):
        return dict(blocked, reason='PERSISTENT_MOUNT_REQUIRED')
    marker = state_dir / 'signals-public-diagnostic.claimed'
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
    mode.add_argument('--run', action='store_true')
    mode.add_argument('--diagnose-public', action='store_true')
    mode.add_argument('--diagnose-public-once', action='store_true')
    parser.add_argument('--config', required=True)
    parser.add_argument('--ledger')
    parser.add_argument('--authorize-service', action='store_true')
    parser.add_argument('--authorize-public-data', action='store_true')
    parser.add_argument('--authorize-telegram', action='store_true')
    args = parser.parse_args(argv)
    try:
        config, sources = load_inputs(args.config)
        if args.check_config:
            result = dict(status='CONFIG_VALID', live_allowed=False)
        elif args.diagnose_public_once:
            result = diagnose_once(config, sources, authorized=args.authorize_public_data)
        elif args.diagnose_public:
            result = diagnose_public_cycle(config, sources,
                                           public_data_authorized=args.authorize_public_data)
        elif not args.ledger:
            result = dict(status='BLOCKED', reason='LEDGER_PATH_REQUIRED')
        elif args.initialize_ledger:
            provision_ledger(args.ledger)
            result = dict(status='LEDGER_INITIALIZED', live_allowed=False)
        else:
            result = execute(config, sources, args.ledger, authorized=(args.authorize_service
                             and args.authorize_public_data and args.authorize_telegram))
    except Exception:
        result = dict(status='BLOCKED', reason='CONFIGURATION_OR_STORAGE_REVIEW_REQUIRED')
    # Never print exceptions, paths, config, credentials or raw transport responses.
    allowed = {key: result[key] for key in ('status', 'reason', 'cycles', 'evaluations', 'confirmed',
               'stage', 'completed_symbols', 'planned_symbols', 'scan_seconds',
               'cycle_with_pause_seconds', 'reason_counts', 'delivery_allowed', 'capacity_approved') if key in result}
    allowed['live_allowed'] = False
    print(json.dumps(allowed), flush=True)
    return 0 if result.get('status') in ('CONFIG_VALID', 'LEDGER_INITIALIZED', 'STOPPED', 'DIAGNOSTIC_COMPLETE') else 1


if __name__ == '__main__':
    raise SystemExit(main())
