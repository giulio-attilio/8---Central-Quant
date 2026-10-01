"""Explicit local signals-only supervisor and offline evaluation cycle.

No startup, credential lookup, filesystem or network on import/offline cycle.
The explicitly invoked supervisor reads public data and uses Telegram only.
This module never treats a valid configuration as approval to start that service.
"""
import re
import json
import copy
import os
import sqlite3
import time
from pathlib import Path
from contextlib import contextmanager, closing

from falcon_advisory_offline import _config, _policy, _require, _timestamp, reviewed_analysis
from donkey_advisory_offline import validate_config as donkey_config
from donkey_advisory_offline import reviewed_analysis as donkey_source
from signal_only_workflow import run_once, dispatch_ready_candidates, DONKEY_VARIANTS
from bingx_public_signal_source import collect_snapshot, validate_snapshot, PublicDataError, safe_error_code
from telegram_signal_delivery import _route


TRACKING_SNAPSHOT_DISCARD_ERRORS = frozenset({'QUOTE_STALE_OR_FUTURE'})


def service_error_code(error):
    """Only fixed codes/types, never exception text, URLs or payloads."""
    if type(error) is PublicDataError:
        return safe_error_code(error)
    codes = {'DONKEY_POLLING_NOT_AVAILABLE', 'DONKEY_POLL_FAILED_NO_RETRY',
             'DONKEY_UPDATE_INVALID', 'DONKEY_REFERENCE_CLOCK_REGRESSION',
             'DONKEY_NOTICE_UNKNOWN_NO_RETRY', 'DONKEY_REFERENCE_H4_REQUIRED',
             'DONKEY_REFERENCE_IDENTITY_CHANGED', 'CLOCK_REGRESSION', 'LEDGER_INTEGRITY',
             'MANUAL_TRACKING_POLLING_NOT_AVAILABLE',
             'MANUAL_TRACKING_POLL_FAILED_NO_RETRY',
             'MANUAL_TRACKING_UPDATE_INVALID', 'MANUAL_TRACKING_CLOCK_REGRESSION',
             'MANUAL_TRACKING_NOTICE_UNKNOWN_NO_RETRY',
             'MANUAL_TRACKING_IDENTITY_CHANGED', 'MANUAL_TRACKING_PUBLIC_QUOTE_REQUIRED',
             'MANUAL_TRACKING_ROUTE_CHANGED'}
    if type(error) is ValueError and len(error.args) == 1 and type(error.args[0]) is str and error.args[0] in codes:
        return error.args[0]
    if isinstance(error, TimeoutError):
        return 'IO_TIMEOUT'
    if isinstance(error, sqlite3.Error):
        return 'SQLITE_FAILURE'
    if isinstance(error, OSError):
        return 'IO_FAILURE'
    return 'SERVICE_VALIDATION_OR_IO_FAILED'


def required_frames(bot, entry):
    if bot == "DONKEY":
        return {"4h", "1d"}
    needed = {"15m"}
    if entry["analysis"]["ALIGNMENT_MODE"] in ("h1", "h1_h4"):
        needed.add("1h")
    if entry["analysis"]["ALIGNMENT_MODE"] == "h1_h4":
        needed.add("4h")
    return needed


def scoped_snapshot(snapshot, needed):
    _require(type(snapshot.get("frames")) is dict and type(snapshot.get("frame_received_at_ms")) is dict,
             "FRAMES_REQUIRED")
    return dict(snapshot, frames={k: v for k, v in snapshot["frames"].items() if k in needed},
                frame_received_at_ms={k: v for k, v in snapshot["frame_received_at_ms"].items() if k in needed})


def apply_shared_watchlist(config, watchlist_text):
    """Apply the explicitly selected JSON watchlist to both bots, without IO.

    Only the repository's USDT-settled swap notation is accepted. Preserve
    asset spelling, multipliers and order; do not guess aliases or skip entries.
    Full service validation still requires all other configuration decisions.
    """
    _require(type(watchlist_text) is str, "WATCHLIST_TEXT_REQUIRED")
    try:
        entries = json.loads(watchlist_text)
    except (ValueError, RecursionError):
        _require(False, "WATCHLIST_JSON_INVALID")
    _require(type(entries) is list and len(entries) > 0, "WATCHLIST_LIST_REQUIRED")
    symbols = []
    for entry in entries:
        _require(type(entry) is str, "WATCHLIST_SYMBOL_INVALID")
        match = re.fullmatch(r"([A-Z0-9]{2,25})/USDT:USDT", entry)
        _require(match is not None, "WATCHLIST_SYMBOL_INVALID")
        symbols.append(match.group(1) + "-USDT")
    _require(len(set(symbols)) == len(symbols), "WATCHLIST_DUPLICATE")
    _require(type(config) is dict and type(config.get("bots")) is dict and
             set(config["bots"]) == {"FALCON", "DONKEY"} and
             all(type(v) is dict for v in config["bots"].values()), "SERVICE_BOTS_REQUIRED")
    result = copy.deepcopy(config)
    for bot in ("FALCON", "DONKEY"):
        result["bots"][bot]["symbols"] = list(symbols)
    return validate_service_config(result)


def validate_service_config(config):
    """Strict nonsecret configuration; no inferred assets, strategy or TTL values."""
    _require(type(config) is dict and set(config) == {"version", "poll_interval_ms", "bots"}, "SERVICE_CONFIG_FIELDS")
    _require(type(config["version"]) is int and config["version"] == 1, "SERVICE_CONFIG_VERSION")
    interval = config["poll_interval_ms"]
    _require(type(interval) is int and interval > 0, "SERVICE_CADENCE_REQUIRED")
    bots = config["bots"]
    _require(type(bots) is dict and set(bots) == {"FALCON", "DONKEY"}, "SERVICE_BOTS_REQUIRED")
    result = dict(version=1, poll_interval_ms=interval, bots={})
    for bot in ("FALCON", "DONKEY"):
        entry = bots[bot]
        _require(type(entry) is dict and set(entry) == {"symbols", "setups", "analysis", "policy"}, "BOT_CONFIG_FIELDS")
        symbols, setups = entry["symbols"], entry["setups"]
        _require(type(symbols) is list and len(symbols) > 0 and
                 all(type(x) is str and re.fullmatch(r"[A-Z0-9]{2,25}-USDT", x) for x in symbols), "SYMBOLS_REQUIRED")
        _require(len(set(symbols)) == len(symbols), "DUPLICATE_SYMBOL")
        _require(type(setups) is list and len(setups) > 0 and all(type(x) is str for x in setups), "SETUPS_REQUIRED")
        _require(len(set(setups)) == len(setups), "DUPLICATE_SETUP")
        if bot == "DONKEY":
            _require(set(setups) == set(DONKEY_VARIANTS), "ALL_SELECTED_DONKEY_VARIANTS_REQUIRED")
            analysis = donkey_config(entry["analysis"])
        else:
            _require(set(setups) <= {"FALCON15", "FALCON30"}, "FALCON_SETUP")
            analysis = _config(entry["analysis"])
            # The approved public reader returns at most 200 rows including forming.
            warmup = max(80, analysis["EMA_SLOW"] + 5, analysis["ATR_LEN"], 2 * analysis["ADX_LEN"], 20)
            _require(warmup + 1 <= 200, "PUBLIC_HISTORY_TOO_SHORT_FOR_CONFIG")
        policy = _policy(entry["policy"])
        _require(interval <= policy["signal_ttl_ms"], "CADENCE_EXCEEDS_SIGNAL_VALIDITY")
        result["bots"][bot] = dict(symbols=list(symbols), setups=list(setups), analysis=analysis, policy=policy)
    return result


def evaluate_cycle(config, sources, snapshots, *, now_ms):
    """Evaluate supplied public-schema data once. No credential/transport path.

    All configuration, sources and requested snapshot identities are checked
    before analysis. Errors in an individual strategy remain explicit results;
    NO_SIGNAL and data rejection never become outbound messages.
    Each bot receives only its requested timeframes, even for a shared symbol.
    """
    config = validate_service_config(config)
    _require(_timestamp(now_ms), "NOW_TIME")
    _require(type(sources) is dict and set(sources) == {"FALCON", "DONKEY"}, "SOURCES_REQUIRED")
    reviewed_analysis(sources["FALCON"])
    donkey_source(sources["DONKEY"])
    requested = {symbol for entry in config["bots"].values() for symbol in entry["symbols"]}
    _require(type(snapshots) is dict and set(snapshots) == requested, "SNAPSHOT_UNIVERSE_MISMATCH")
    for symbol, snap in snapshots.items():
        _require(type(snap) is dict and snap.get("symbol") == symbol and snap.get("synthetic") is False,
                 "SNAPSHOT_IDENTITY_MISMATCH")
    results = []
    for bot, entry in config["bots"].items():
        needed = required_frames(bot, entry)
        for symbol in entry["symbols"]:
            snap = snapshots[symbol]
            scoped = scoped_snapshot(snap, needed)
            for setup in entry["setups"]:
                result = run_once(bot, sources[bot], scoped, entry["analysis"], entry["policy"],
                                  setup=setup, now_ms=now_ms, public_data_authorized=True)
                results.append(dict(bot=bot, symbol=symbol, setup=setup, result=result))
    return dict(status="CYCLE_EVALUATED", results=results, delivery_allowed=False, live_allowed=False)


def diagnose_public_cycle(config, sources, *, public_data_authorized=False):
    """One finite measurement, no ledger, credentials, delivery or retries.

    Reports only counts, durations, fixed stages/codes; never market payloads.
    A completed measurement does not qualify production capacity or delivery.
    """
    state = dict(status="BLOCKED", reason="PUBLIC_READ_AUTHORIZATION_REQUIRED",
                 stage="authorization", completed_symbols=0, evaluations=0,
                 delivery_allowed=False, live_allowed=False, capacity_approved=False)
    if public_data_authorized is not True:
        return state
    started = time.monotonic()
    stage = "configuration"
    try:
        config = validate_service_config(config)
        _require(type(sources) is dict and set(sources) == {"FALCON", "DONKEY"}, "SOURCES_REQUIRED")
        reviewed_analysis(sources["FALCON"])
        donkey_source(sources["DONKEY"])
        symbols = list(dict.fromkeys(s for entry in config["bots"].values() for s in entry["symbols"]))
        state["planned_symbols"] = len(symbols)
        counts = {}
        allowed = {"NO_SIGNAL", "ORB_INCOMPLETE", "ENTRY_DEVIATION", "LEVEL_ALREADY_CROSSED",
                   "EXPIRED", "PUBLIC_DELIVERY_NOT_ENABLED", "DONKEY_STOP_DISTANCE_ABOVE_IDEAL"}
        for symbol in symbols:
            selected = {bot: entry for bot, entry in config["bots"].items() if symbol in entry["symbols"]}
            needed = set().union(*(required_frames(bot, entry) for bot, entry in selected.items()))
            stage = "collection"
            snapshot = collect_snapshot(symbol, [tf for tf in ("15m", "1h", "4h", "1d") if tf in needed], authorized=True, limit=200)
            _require(type(snapshot) is dict and snapshot.get("symbol") == symbol and
                     snapshot.get("synthetic") is False, "SNAPSHOT_IDENTITY_MISMATCH")
            for bot, entry in selected.items():
                scoped = scoped_snapshot(snapshot, required_frames(bot, entry))
                for setup in entry["setups"]:
                    now = time.time_ns() // 1000000
                    stage = "freshness_validation"
                    try:
                        validate_snapshot(scoped, now_ms=now,
                                          frame_max_age_ms=entry["policy"]["snapshot_max_age_ms"],
                                          quote_max_age_ms=entry["policy"]["quote_max_age_ms"])
                    except PublicDataError as error:
                        if safe_error_code(error) != "FRAME_EXPIRED":
                            raise
                        counts["FRAME_EXPIRED"] = counts.get("FRAME_EXPIRED", 0) + 1
                        # Discard this bot's snapshot; no analysis, send or recollection.
                        break
                    stage = "analysis"
                    out = run_once(bot, sources[bot], scoped, entry["analysis"], entry["policy"],
                                   setup=setup, now_ms=now, public_data_authorized=True,
                                   network_authorized=False, public_delivery_authorized=False)
                    state["evaluations"] += 1
                    reason = out.get("reason")
                    if type(reason) is not str or reason not in allowed or out.get("status") not in {"BLOCKED", "LOCAL_PUBLIC_PREVIEW"}:
                        return dict(state, status="FAILED", reason="DIAGNOSTIC_ANALYSIS_STOPPED", stage=stage)
                    counts[reason] = counts.get(reason, 0) + 1
            state["completed_symbols"] += 1
        elapsed = max(0, time.monotonic() - started)
        return dict(state, status="DIAGNOSTIC_COMPLETE", reason="NO_DELIVERY_ATTEMPTED", stage="complete",
                    scan_seconds=round(elapsed, 3),
                    cycle_with_pause_seconds=round(elapsed + config["poll_interval_ms"] / 1000, 3),
                    reason_counts=counts)
    except PublicDataError as error:
        return dict(state, status="FAILED", reason=safe_error_code(error), stage=stage)
    except Exception:
        return dict(state, status="FAILED", reason="DIAGNOSTIC_FAILURE_REDACTED", stage=stage)


@contextmanager
def exclusive_service(ledger_path):
    """OS-held local lock, released on exit/crash. Never deletes lock/ledger files.

    Single instance for this ledger on this machine, not a distributed lease.
    A different ledger must not be used as an automatic recovery workaround.
    """
    lock = open(str(ledger_path) + ".service.lock", "a+b")
    acquired = False
    try:
        if os.name == "nt":
            import msvcrt
            lock.seek(0, 2)
            if lock.tell() == 0:
                lock.write(b"0")
                lock.flush()
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        acquired = True
        yield
    finally:
        if acquired:
            if os.name == "nt":
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        lock.close()


def run_service(config, sources, *, values, ledger_path, stop_event,
                service_authorized=False, public_data_authorized=False,
                public_delivery_authorized=False, max_cycles=None, donkey_operator_id=None):
    """Explicit blocking supervisor, never spawned/installed automatically.

    Fresh per-symbol collection followed immediately by evaluation/delivery.
    No catch-up queue or immediate retry. Classified transient polling failures
    are retried only on the next normally paced cycle.
    Ledger must be explicitly provisioned beforehand. Credentials are injected
    in memory; there is no .env/Render/private exchange/account access.
    max_cycles bounds a supervised run; None runs until stop_event or a failure.
    Caller must provide durable local (not shared/network/cloud-sync) storage.
    """
    state = dict(status="BLOCKED", reason=None, cycles=0, evaluations=0,
                 confirmed=0, live_allowed=False)
    if not (service_authorized is True and public_data_authorized is True and public_delivery_authorized is True):
        return dict(state, reason="SERVICE_AUTHORIZATIONS_REQUIRED")
    stage = 'configuration'
    try:
        config = validate_service_config(config)
        _require(max_cycles is None or type(max_cycles) is int and max_cycles > 0, "CYCLE_LIMIT")
        _require(type(sources) is dict and set(sources) == {"FALCON", "DONKEY"}, "SOURCES_REQUIRED")
        reviewed_analysis(sources["FALCON"])
        donkey_source(sources["DONKEY"])
        # Validate both routes before the first public read, not halfway through a cycle.
        _route("FALCON", values)
        _route("DONKEY", values)
        values = dict(values)
        sources = dict(sources)
        path = Path(ledger_path).resolve()
        stage = 'ledger_check'
        with closing(sqlite3.connect(path.as_uri() + "?mode=rw", uri=True, timeout=5)) as db:
            _require(db.execute("PRAGMA quick_check").fetchone() == ("ok",), "LEDGER_INTEGRITY")
            db.execute("SELECT identity, candle, route, status, attempted_ms, message_id FROM delivery_v1 LIMIT 0")
            db.execute("SELECT id, now_ms FROM delivery_clock_v1 LIMIT 0")
            db.execute("SELECT route, until_ms FROM delivery_pause_v1 LIMIT 0")
        symbols = list(dict.fromkeys(s for entry in config["bots"].values() for s in entry["symbols"]))
        benign = {"NO_SIGNAL", "ORB_INCOMPLETE", "ENTRY_DEVIATION", "LEVEL_ALREADY_CROSSED",
                  "EXPIRED", "PRIOR_ATTEMPT_NO_RETRY", "EXPIRED_BEFORE_HTTP", "DATA_AGED_DURING_ANALYSIS",
                  "DONKEY_STOP_DISTANCE_ABOVE_IDEAL", "DONKEY_REFERENCE_ALREADY_ACTIVE",
                  "DONKEY_WAIT_NEXT_H4_AFTER_EXIT", "MANUAL_TRADE_SAME_SIDE_ACTIVE"}
        last_now = None
        stage = 'exclusive_lock'
        with exclusive_service(path):
            tracker = None
            if donkey_operator_id is not None:
                from manual_signal_tracking import (ManualTradeTracker, TrackingPollTransientError,
                                                    provision as provision_manual_tracking)
                stage = 'tracking_schema_provision'
                provision_manual_tracking(str(path))
                stage = 'tracking_initialize'
                tracker = ManualTradeTracker(str(path), values, donkey_operator_id, authorized=True)
                stage = 'tracking_webhook_check'
                tracker.check_polling()
                stage = 'tracking_notice_flush'
                tracker.flush()
            while not stop_event.is_set():
                tracking_poll_deferred = False
                for symbol in symbols:
                    if stop_event.is_set():
                        return dict(state, status="STOPPED", reason="STOP_REQUESTED")
                    if tracker:
                        if tracking_poll_deferred:
                            continue
                        stage = 'tracking_poll'
                        try:
                            tracker.poll(time.time_ns() // 1000000)
                        except TrackingPollTransientError:
                            tracking_poll_deferred = True
                            state['tracking_poll_skips'] = state.get('tracking_poll_skips', 0) + 1
                            print(json.dumps(dict(status='TRACKING_POLL_DEFERRED',
                                                  reason='DONKEY_POLL_TRANSIENT',
                                                  tracking_poll_skips=state['tracking_poll_skips'],
                                                  live_allowed=False)), flush=True)
                            # Do not collect, analyze or deliver after a failed poll.
                            # The next attempt occurs only after the normal cycle pause.
                            continue
                    selected = {bot: entry for bot, entry in config["bots"].items() if symbol in entry["symbols"]}
                    needed = set().union(*(required_frames(bot, entry) for bot, entry in selected.items()))
                    intervals = [tf for tf in ("15m", "1h", "4h", "1d") if tf in needed]
                    try:
                        stage = 'public_collection'
                        snapshot = collect_snapshot(symbol, intervals, authorized=True, limit=200)
                    except PublicDataError as error:
                        return dict(state, status="FAILED", reason=safe_error_code(error), stage=stage)
                    _require(type(snapshot) is dict and snapshot.get("symbol") == symbol and
                             snapshot.get("synthetic") is False, "SNAPSHOT_IDENTITY_MISMATCH")
                    if tracker:
                        try:
                            stage = 'tracking_observe'
                            quote_age = min(entry['policy']['quote_max_age_ms']
                                            for entry in selected.values())
                            tracker.observe(snapshot, time.time_ns() // 1000000, quote_age)
                        except ValueError as error:
                            if str(error) == 'MANUAL_TRACKING_PUBLIC_QUOTE_REQUIRED':
                                state['discarded_snapshots'] = state.get('discarded_snapshots', 0) + 1
                                state['tracking_quote_skips'] = state.get('tracking_quote_skips', 0) + 1
                                print(json.dumps(dict(status='TRACKING_OBSERVATION_SKIPPED',
                                                      reason='QUOTE_STALE_OR_FUTURE',
                                                      tracking_quote_skips=state['tracking_quote_skips'],
                                                      live_allowed=False)), flush=True)
                                continue
                            raise
                        stage = 'tracking_notice_flush'
                        tracker.flush()
                    for bot, entry in selected.items():
                        scoped = scoped_snapshot(snapshot, required_frames(bot, entry))
                        ready = []
                        frame_expired = False
                        for setup in entry["setups"]:
                            if stop_event.is_set():
                                return dict(state, status="STOPPED", reason="STOP_REQUESTED")
                            now = time.time_ns() // 1000000
                            stage = 'signal_evaluation_or_delivery'
                            _require(last_now is None or now >= last_now, "CLOCK_REGRESSION")
                            last_now = now
                            result = run_once(bot, sources[bot], scoped, entry["analysis"], entry["policy"],
                                setup=setup, now_ms=now, values=values, ledger_path=str(path),
                                network_authorized=True, public_data_authorized=True, public_delivery_authorized=True,
                                defer_public_delivery=True)
                            state["evaluations"] += 1
                            if result.get("status") == "BLOCKED" and result.get("reason") == "FRAME_EXPIRED":
                                state["discarded_snapshots"] = state.get("discarded_snapshots", 0) + 1
                                frame_expired = True
                                break
                            if result["status"] == "PUBLIC_CANDIDATE_READY":
                                ready.append(result)
                            elif result.get("reason") not in benign:
                                # Never return untrusted response/exception contents or credentials.
                                return dict(state, status="FAILED", reason="EVALUATION_OR_DELIVERY_STOPPED")
                        if frame_expired or not ready:
                            continue
                        stage = 'signal_delivery'
                        delivered = dispatch_ready_candidates(
                            bot, ready, values=values, ledger_path=str(path),
                            network_authorized=True, public_delivery_authorized=True,
                            manual_tracking=tracker is not None,
                        )
                        physical = delivered.get('deliveries', [])
                        for item in physical:
                            if item.get('status') == 'CONFIRMED':
                                state['confirmed'] += 1
                                if stop_event.wait(1):
                                    return dict(state, status="STOPPED", reason="STOP_REQUESTED")
                            elif item.get('reason') not in benign:
                                return dict(state, status="FAILED", reason="EVALUATION_OR_DELIVERY_STOPPED")
                state["cycles"] += 1
                print(json.dumps(dict(status='SIGNALS_CYCLE_COMPLETE', cycles=state['cycles'],
                                      evaluations=state['evaluations'], confirmed=state['confirmed'],
                                      live_allowed=False)), flush=True)
                if max_cycles is not None and state["cycles"] >= max_cycles:
                    return dict(state, status="STOPPED", reason="CYCLE_LIMIT_REACHED")
                # No backlog replay after sleep/resume. Next cycle always recollects.
                if stop_event.wait(config["poll_interval_ms"] / 1000):
                    break
            return dict(state, status="STOPPED", reason="STOP_REQUESTED")
    except KeyboardInterrupt:
        return dict(state, status="STOPPED", reason="INTERRUPTED")
    except Exception as error:
        return dict(state, status="FAILED", reason=service_error_code(error), stage=stage)
