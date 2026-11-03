"""HTTP boundary for the disaster-stop fallback route."""

from __future__ import annotations


def persist_disaster_stop_fallback_result_v1(
    payload,
    *,
    commit,
    latest_file,
    atomic_write_json,
    append_event,
):
    """Persist fallback diagnostics only for an explicitly committed action."""

    if not commit:
        return False
    atomic_write_json(latest_file, payload)
    append_event({"event": "DISASTER_STOP_FALLBACK", **payload})
    return True


def dispatch_disaster_stop_fallback_route_v1(request, builder, auth_guard):
    """Keep GET preview-only and guard the order-capable POST boundary."""

    if request.method == "GET":
        commit_query = str(request.args.get("commit") or "").strip().lower()
        if commit_query in {"1", "true", "yes", "sim", "on"}:
            return {
                "ok": False,
                "status": "COMMIT_REQUIRES_AUTHENTICATED_POST",
                "commit_attempted": False,
            }, 405
        return builder(
            symbol=request.args.get("symbol"),
            side=request.args.get("side"),
            bot=request.args.get("bot"),
            setup=request.args.get("setup"),
            sl=request.args.get("sl") or request.args.get("stop") or request.args.get("stop_loss"),
            commit=False,
            ack="",
            source_result=None,
            safety_before=None,
            auto=False,
        )

    # A commit must not be smuggled in via query parameters; POST body is the
    # only source of operation inputs, and the existing exact-header guard is
    # required before the order-capable builder can be reached.
    if request.args:
        return {
            "ok": False,
            "status": "POST_QUERY_PARAMETERS_NOT_ALLOWED",
            "commit_attempted": False,
        }, 400
    if not callable(auth_guard):
        return {
            "ok": False,
            "status": "EXECUTION_AUTH_UNAVAILABLE",
            "commit_attempted": False,
        }, 403
    auth_result = auth_guard()
    if not isinstance(auth_result, dict) or not auth_result.get("ok"):
        return {
            "ok": False,
            "status": (
                auth_result.get("status")
                if isinstance(auth_result, dict)
                else "EXECUTION_AUTH_INVALID"
            ),
            "commit_attempted": False,
        }, 403

    body = request.get_json(silent=True)
    if not hasattr(body, "get"):
        return {
            "ok": False,
            "status": "JSON_OBJECT_REQUIRED",
            "commit_attempted": False,
        }, 400
    commit_value = str(body.get("commit") or "").strip().lower()
    if commit_value not in {"1", "true", "yes", "sim", "on"}:
        return {
            "ok": False,
            "status": "EXPLICIT_COMMIT_REQUIRED",
            "commit_attempted": False,
        }, 400
    ack = str(body.get("ack") or "").strip().upper()
    if ack != "DISASTER_STOP_FALLBACK":
        return {
            "ok": False,
            "status": "ACK_REQUIRED",
            "commit_attempted": False,
        }, 400

    return builder(
        symbol=body.get("symbol"),
        side=body.get("side"),
        bot=body.get("bot"),
        setup=body.get("setup"),
        sl=body.get("sl") or body.get("stop") or body.get("stop_loss"),
        commit=True,
        ack=ack,
        source_result=None,
        safety_before=None,
        auto=False,
    )
