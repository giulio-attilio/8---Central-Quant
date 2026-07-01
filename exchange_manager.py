import os
import threading
import ccxt

_exchange = None
_exchange_lock = threading.Lock()


def get_exchange():
    global _exchange

    with _exchange_lock:
        if _exchange is None:
            ex = ccxt.bingx({"enableRateLimit": True})
            ex.options["defaultType"] = os.environ.get("BINGX_DEFAULT_TYPE", "swap")
            _exchange = ex

        return _exchange