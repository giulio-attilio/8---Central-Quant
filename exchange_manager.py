import os
import threading
import time
import ccxt
from exchange_throttle_policy_v1 import (
    exchange_throttle_cooldown_remaining,
    is_exchange_throttle_error,
    record_exchange_throttle_cooldown,
    reset_exchange_throttle_backoff,
)

_exchange = None
_markets_loaded = False
_last_markets_load_ts = 0
_exchange_lock = threading.RLock()
_shared_ohlcv_request_lock = threading.Lock()

DEFAULT_TYPE = os.environ.get("BINGX_DEFAULT_TYPE", "swap")
MARKETS_RELOAD_SECONDS = int(os.environ.get("BINGX_MARKETS_RELOAD_SECONDS", "21600"))  # 6h


def get_exchange():
    """
    Retorna uma única instância compartilhada da BingX para toda a Central Quant.
    Evita que cada robô carregue seu próprio cache pesado do ccxt.
    """
    global _exchange

    with _exchange_lock:
        if _exchange is None:
            ex = ccxt.bingx({"enableRateLimit": True})
            ex.options["defaultType"] = DEFAULT_TYPE
            _install_shared_ohlcv_throttle_guard(ex)
            _exchange = ex

        return _exchange


def _install_shared_ohlcv_throttle_guard(ex):
    """Share a bounded throttle cooldown across all bots using this client."""
    original_fetch_ohlcv = getattr(ex, "fetch_ohlcv", None)
    if not callable(original_fetch_ohlcv) or getattr(
        original_fetch_ohlcv, "_central_throttle_guard_v1", False
    ):
        return False

    def guarded_fetch_ohlcv(*args, **kwargs):
        # The client is shared by concurrent bot threads. Serialize the check
        # and request so only one in-flight scanner call can pass before a
        # throttling response opens the process-wide cooldown.
        with _shared_ohlcv_request_lock:
            remaining = exchange_throttle_cooldown_remaining()
            if remaining > 0:
                raise ccxt.RateLimitExceeded(
                    f"Central shared OHLCV throttle cooldown active ({remaining:.1f}s)"
                )
            try:
                result = original_fetch_ohlcv(*args, **kwargs)
            except Exception as exc:
                if is_exchange_throttle_error(exc):
                    record_exchange_throttle_cooldown()
                raise
            reset_exchange_throttle_backoff()
            return result

    guarded_fetch_ohlcv._central_throttle_guard_v1 = True
    ex.fetch_ohlcv = guarded_fetch_ohlcv
    return True


def load_markets_once(force=False):
    """
    Carrega markets uma vez e reaproveita o cache.
    Use nos validadores de watchlist.
    """
    global _markets_loaded, _last_markets_load_ts

    with _exchange_lock:
        ex = get_exchange()
        now = time.time()

        should_reload = (
            force
            or not _markets_loaded
            or not getattr(ex, "markets", None)
            or (MARKETS_RELOAD_SECONDS > 0 and now - _last_markets_load_ts > MARKETS_RELOAD_SECONDS)
        )

        if should_reload:
            ex.load_markets(reload=True)
            _markets_loaded = True
            _last_markets_load_ts = now

        return ex.markets or {}


def clear_markets_cache():
    """
    Limpeza manual de cache se a memória subir demais.
    """
    global _markets_loaded

    with _exchange_lock:
        ex = get_exchange()
        try:
            ex.markets = None
            ex.markets_by_id = None
            ex.currencies = None
            _markets_loaded = False
            return True
        except Exception:
            return False


def exchange_status():
    ex = get_exchange()
    return {
        "ok": True,
        "default_type": DEFAULT_TYPE,
        "markets_loaded": bool(_markets_loaded),
        "markets_count": len(getattr(ex, "markets", {}) or {}),
        "last_markets_load_ts": _last_markets_load_ts,
        "markets_reload_seconds": MARKETS_RELOAD_SECONDS,
    }
