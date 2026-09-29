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
from signal_only_workflow import run_once, DONKEY_VARIANTS
from bingx_public_signal_source import collect_snapshot
from telegram_signal_delivery import _route


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
                public_delivery_authorized=False, max_cycles=None):
    """Explicit blocking supervisor, never spawned/installed automatically.

    Fresh per-symbol collection followed immediately by evaluation/delivery.
    No catch-up queue or automatic retry after a transport/analysis failure.
    Ledger must be explicitly provisioned beforehand. Credentials are injected
    in memory; there is no .env/Render/private exchange/account access.
    max_cycles bounds a supervised run; None runs until stop_event or a failure.
    Caller must provide durable local (not shared/network/cloud-sync) storage.
    """
    state = dict(status="BLOCKED", reason=None, cycles=0, evaluations=0,
                 confirmed=0, live_allowed=False)
    if not (service_authorized is True and public_data_authorized is True and public_delivery_authorized is True):
        return dict(state, reason="SERVICE_AUTHORIZATIONS_REQUIRED")
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
        with closing(sqlite3.connect(path.as_uri() + "?mode=rw", uri=True, timeout=5)) as db:
            _require(db.execute("PRAGMA quick_check").fetchone() == ("ok",), "LEDGER_INTEGRITY")
            db.execute("SELECT identity, candle, route, status, attempted_ms, message_id FROM delivery_v1 LIMIT 0")
            db.execute("SELECT id, now_ms FROM delivery_clock_v1 LIMIT 0")
            db.execute("SELECT route, until_ms FROM delivery_pause_v1 LIMIT 0")
        symbols = list(dict.fromkeys(s for entry in config["bots"].values() for s in entry["symbols"]))
        benign = {"NO_SIGNAL", "ORB_INCOMPLETE", "ENTRY_DEVIATION", "LEVEL_ALREADY_CROSSED",
                  "EXPIRED", "PRIOR_ATTEMPT_NO_RETRY", "EXPIRED_BEFORE_HTTP", "DATA_AGED_DURING_ANALYSIS"}
        last_now = None
        with exclusive_service(path):
            while not stop_event.is_set():
                for symbol in symbols:
                    if stop_event.is_set():
                        return dict(state, status="STOPPED", reason="STOP_REQUESTED")
                    selected = {bot: entry for bot, entry in config["bots"].items() if symbol in entry["symbols"]}
                    needed = set().union(*(required_frames(bot, entry) for bot, entry in selected.items()))
                    intervals = [tf for tf in ("15m", "1h", "4h", "1d") if tf in needed]
                    snapshot = collect_snapshot(symbol, intervals, authorized=True, limit=200)
                    _require(type(snapshot) is dict and snapshot.get("symbol") == symbol and
                             snapshot.get("synthetic") is False, "SNAPSHOT_IDENTITY_MISMATCH")
                    for bot, entry in selected.items():
                        scoped = scoped_snapshot(snapshot, required_frames(bot, entry))
                        for setup in entry["setups"]:
                            if stop_event.is_set():
                                return dict(state, status="STOPPED", reason="STOP_REQUESTED")
                            now = time.time_ns() // 1000000
                            _require(last_now is None or now >= last_now, "CLOCK_REGRESSION")
                            last_now = now
                            result = run_once(bot, sources[bot], scoped, entry["analysis"], entry["policy"],
                                setup=setup, now_ms=now, values=values, ledger_path=str(path),
                                network_authorized=True, public_data_authorized=True, public_delivery_authorized=True)
                            state["evaluations"] += 1
                            if result["status"] == "CONFIRMED":
                                state["confirmed"] += 1
                            elif result.get("reason") not in benign:
                                # Never return untrusted response/exception contents or credentials.
                                return dict(state, status="FAILED", reason="EVALUATION_OR_DELIVERY_STOPPED")
                            if stop_event.wait(1):
                                return dict(state, status="STOPPED", reason="STOP_REQUESTED")
                state["cycles"] += 1
                if max_cycles is not None and state["cycles"] >= max_cycles:
                    return dict(state, status="STOPPED", reason="CYCLE_LIMIT_REACHED")
                # No backlog replay after sleep/resume. Next cycle always recollects.
                if stop_event.wait(config["poll_interval_ms"] / 1000):
                    break
            return dict(state, status="STOPPED", reason="STOP_REQUESTED")
    except KeyboardInterrupt:
        return dict(state, status="STOPPED", reason="INTERRUPTED")
    except Exception:
        return dict(state, status="FAILED", reason="SERVICE_VALIDATION_OR_IO_FAILED")
