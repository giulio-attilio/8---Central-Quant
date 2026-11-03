"""Fail-closed, preview-only HTTP boundary for the auto-real bridge route."""

from __future__ import annotations


def dispatch_auto_real_execution_bridge_route_v1(
    request,
    processor,
    normalize_payload,
    parse_bool,
    sanitize,
    auth_guard,
):
    """Keep the endpoint preview-only; refuse all real execution requests."""
    method = str(getattr(request, "method", "") or "").strip().upper()
    if method == "GET":
        if any(key in request.args for key in ("execute", "commit", "ack")):
            return {
                "ok": False,
                "status": "LIVE_ACTION_REQUIRES_AUTHENTICATED_POST",
                "order_attempted": False,
                "no_order_sent": True,
            }, 405
        payload = normalize_payload(
            {key: value for key, value in request.args.items()},
            manual_defaults=True,
        )
        result = processor(
            payload=payload,
            risk_result={
                "allowed": True,
                "decision": "ALLOW",
                "mode": payload.get("mode") or "VERIFY",
            },
            source="manual_route_preview",
            execute=False,
            dry_run=True,
        )
        return sanitize(result), 200

    if method != "POST":
        return {
            "ok": False,
            "status": "METHOD_NOT_ALLOWED",
            "order_attempted": False,
            "no_order_sent": True,
        }, 405

    if request.args:
        return {
            "ok": False,
            "status": "POST_QUERY_PARAMETERS_NOT_ALLOWED",
            "order_attempted": False,
            "no_order_sent": True,
        }, 400

    if not callable(auth_guard):
        return {
            "ok": False,
            "status": "EXECUTION_AUTH_UNAVAILABLE",
            "order_attempted": False,
            "no_order_sent": True,
        }, 403
    auth_result = auth_guard()
    if not isinstance(auth_result, dict) or auth_result.get("ok") is not True:
        return {
            "ok": False,
            "status": (
                auth_result.get("status")
                if isinstance(auth_result, dict)
                else "EXECUTION_AUTH_INVALID"
            ),
            "order_attempted": False,
            "no_order_sent": True,
        }, 403

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return {
            "ok": False,
            "status": "JSON_OBJECT_REQUIRED",
            "order_attempted": False,
            "no_order_sent": True,
        }, 400

    execute = parse_bool(payload.get("execute"), default=False)
    commit = parse_bool(payload.get("commit"), default=False)
    ack = str(payload.get("ack") or "").strip().upper()
    action_requested = bool(execute or commit or ack)
    if action_requested and not (
        execute
        and commit
        and ack in {"AUTO_REAL_EXECUTE", "AUTO_REAL_EXECUTION_BRIDGE"}
    ):
        return {
            "ok": False,
            "status": "LIVE_ACTION_CONFIRMATION_INVALID",
            "required": {
                "execute": True,
                "commit": True,
                "ack": "AUTO_REAL_EXECUTE",
            },
            "order_attempted": False,
            "no_order_sent": True,
        }, 400

    if action_requested:
        return {
            "ok": False,
            "status": "LIVE_EXECUTION_DISABLED_BY_SAFETY_POLICY",
            "order_attempted": False,
            "no_order_sent": True,
        }, 403

    normalized = normalize_payload(payload, manual_defaults=True)
    result = processor(
        payload=normalized,
        risk_result={
            "allowed": True,
            "decision": "ALLOW",
            "mode": normalized.get("mode") or "VERIFY",
        },
        source="manual_route_preview",
        execute=False,
        dry_run=True,
    )
    return sanitize(result), 200
