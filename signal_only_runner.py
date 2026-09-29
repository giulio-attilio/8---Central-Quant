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
from signal_only_service import run_service, validate_service_config
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


def main(argv=None):
    parser = argparse.ArgumentParser(description='Isolated Falcon/Donkey signals worker')
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check-config', action='store_true')
    mode.add_argument('--initialize-ledger', action='store_true')
    mode.add_argument('--run', action='store_true')
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
    allowed = {key: result[key] for key in ('status', 'reason', 'cycles', 'evaluations', 'confirmed') if key in result}
    allowed['live_allowed'] = False
    print(json.dumps(allowed), flush=True)
    return 0 if result.get('status') in ('CONFIG_VALID', 'LEDGER_INITIALIZED', 'STOPPED') else 1


if __name__ == '__main__':
    raise SystemExit(main())
