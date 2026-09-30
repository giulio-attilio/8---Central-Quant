"""One-shot local analysis and separately authorized Telegram delivery.

No loop, scheduler, market client, .env loading or operational bot imports.
Public data defaults to preview; delivery requires its own explicit authorization.
"""
import time
from falcon_advisory_offline import OfflineSignalSession, _policy
from donkey_advisory_offline import analyze as analyze_donkey
from telegram_signal_delivery import dispatch_synthetic, dispatch_public_signal
from bingx_public_signal_source import PERIODS

DONKEY_VARIANTS = ("DONKEY", "DONKEY_ORIGINAL", "EARLY_DONKEY")


def preview_donkey_variants(source, snapshot, config, policy, *, now_ms, public_data_authorized=False):
    """Evaluate all user-selected variants independently, never send a batch.

No legacy priority/continue: Original must not suppress H4 or Early results.
Each keyed result retains its own signal identity and setup. The caller must
inspect each result; NO_SIGNAL or rejection is not an alert to deliver.
"""
    return {setup: run_once("DONKEY", source, snapshot, config, policy,
                           setup=setup, now_ms=now_ms, public_data_authorized=public_data_authorized)
            for setup in DONKEY_VARIANTS}


def run_once(bot, source, snapshot, config, policy, *, setup, now_ms,
             values=None, ledger_path=None, network_authorized=False, public_data_authorized=False,
             public_delivery_authorized=False, donkey_tracking=False):
    """Explicit caller-owned inputs. No credentials are needed for local preview.

The transport ledger owns attempted-delivery deduplication. The Falcon analysis
session is deliberately ephemeral: previewing must not mark a signal delivered.
Expiry is derived from candle close and policy, never extended by delivery time.
"""
    base = dict(status="BLOCKED", reason=None, analysis=None, delivery=None,
                live_allowed=False, manual_trade_authorized=False)
    started = time.monotonic()
    try:
        public = type(snapshot) is dict and snapshot.get("synthetic") is False
        if type(snapshot) is not dict or (snapshot.get("synthetic") is not True and
                                         not (public and public_data_authorized is True)):
            return dict(base, reason="REAL_MARKET_SOURCE_NOT_AUTHORIZED")
        policy = _policy(policy)
        if bot == "FALCON":
            session = OfflineSignalSession(source, config, policy, session_id="one-shot-preview",
                prior_state=dict(session_id="one-shot-preview", seen=[], revoked=[], last_now_ms=None, context=None))
            out = session.evaluate(snapshot, setup=setup, now_ms=now_ms,
                                   public_data_authorized=public_data_authorized)
        elif bot == "DONKEY":
            out = analyze_donkey(source, snapshot, config, policy, setup=setup, now_ms=now_ms,
                                public_data_authorized=public_data_authorized)
        else:
            return dict(base, reason="BOT_NOT_ALLOWLISTED")
        base["analysis"] = out
        if public and (public_delivery_authorized is not True or network_authorized is not True
                       or out["status"] != "PUBLIC_DATA_PREVIEW"):
            # Public analysis authority never implies messaging or service authority.
            return dict(base, status="LOCAL_PUBLIC_PREVIEW" if out["status"] == "PUBLIC_DATA_PREVIEW" else "BLOCKED",
                        reason="PUBLIC_DELIVERY_NOT_ENABLED" if out["status"] == "PUBLIC_DATA_PREVIEW" else out.get("reason") or "NO_SIGNAL")
        if out["status"] not in ("OFFLINE_PREVIEW", "PUBLIC_DATA_PREVIEW"):
            return dict(base, reason=out.get("reason") or "NO_SIGNAL")
        if network_authorized is not True:
            return dict(base, status="LOCAL_PREVIEW", reason="NETWORK_DISABLED")
        delivery_now = now_ms + max(0, int((time.monotonic() - started) * 1000))
        if (delivery_now - snapshot["observed_at_ms"] > policy["snapshot_max_age_ms"]
                or delivery_now - snapshot["quote"]["at_ms"] > policy["quote_max_age_ms"]):
            return dict(base, reason="DATA_AGED_DURING_ANALYSIS")
        expiry = out["signal"]["candle_closed_at_ms"] + policy["signal_ttl_ms"]
        if public:
            deadline = min(expiry, snapshot["quote"]["at_ms"] + policy["quote_max_age_ms"],
                           min(snapshot["frame_received_at_ms"].values()) + policy["snapshot_max_age_ms"],
                           min(rows[-1][0] + PERIODS[tf] for tf, rows in snapshot["frames"].items()))
            delivered = dispatch_public_signal(bot, out["signal"], values=values,
                ledger_path=ledger_path, now_ms=delivery_now, expires_at_ms=expiry,
                validity_basis=policy["basis"], data_valid_until_ms=deadline,
                network_authorized=True, public_delivery_authorized=True, donkey_tracking=donkey_tracking)
        else:
            delivered = dispatch_synthetic(bot, out["signal"], values=values,
            ledger_path=ledger_path, now_ms=delivery_now,
            expires_at_ms=expiry,
            validity_basis=policy["basis"], network_authorized=True)
        return dict(base, status=delivered["status"], delivery=delivered, reason=delivered["reason"])
    except Exception:
        # Never propagate potentially credential-bearing exception payloads.
        return dict(base, reason="WORKFLOW_INPUT_OR_ANALYSIS_FAILED")
