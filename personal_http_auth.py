"""Runtime-only helper for authenticated Central Quant HTTP calls."""

import hashlib
import hmac
import os
import secrets
import time
from urllib.parse import urlsplit


_RUNTIME_AUTH_USERNAME = "cq-runtime"
_RUNTIME_AUTH_KEY = secrets.token_bytes(32)
_RUNTIME_AUTH_BUCKET_SECONDS = 120


def central_personal_http_auth_expected_passwords(*, now=None):
    """Return configured Basic credentials or a process-local fallback.

    When the Render service has the personal HTTP username/password configured,
    use them without persisting or exposing their values here. The runtime-only
    fallback keeps same-process internal calls working if no external
    credentials are configured; it is not a production login credential.
    """
    configured_username = os.environ.get("CENTRAL_PERSONAL_HTTP_USER")
    configured_password = os.environ.get("CENTRAL_PERSONAL_HTTP_PASSWORD")
    if configured_username and configured_password:
        return configured_username, (configured_password,)

    current_time = time.time() if now is None else float(now)
    current_bucket = int(current_time // _RUNTIME_AUTH_BUCKET_SECONDS)
    passwords = []
    for bucket in (current_bucket, current_bucket - 1):
        message = f"central-personal-http-auth-v1:{bucket}".encode("ascii")
        passwords.append(
            hmac.new(_RUNTIME_AUTH_KEY, message, hashlib.sha256).hexdigest()
        )
    return _RUNTIME_AUTH_USERNAME, tuple(passwords)


def central_personal_http_get_mutation_block(method, path, args):
    """Reject mutation intent over GET, even for an authenticated caller."""
    if str(method or "").strip().upper() != "GET":
        return None

    normalized_path = str(path or "").split("?", 1)[0].strip().lower().rstrip("/") or "/"
    action_paths = {
        "/history/rotation/commit/text",
        "/history/rotation/emergency/commit/text",
        "/history/trades/rebuild",
        "/policyautorelease",
        "/executive/policy/auto_release",
        "/policypriority",
        "/executive/policy/priority",
        "/outcome/evaluate",
        "/outcome_evaluator/evaluate",
        # Recording an outcome appends to the Learning Engine event log; never
        # accept that mutation intent through an authenticated GET.
        "/learning/outcome/v1",
        "/learning/result/v1",
        "/learn/outcome/v1",
        # Manual learning refresh appends an audit record; expose it only via POST.
        "/learning/refresh",
        # These aliases imply confirmation in the handler even with no query
        # string, so GET must always remain read-only.
        "/traderegistry/sync/confirm",
        "/trade_registry/sync/confirm",
        "/trades/sync/confirm",
        "/pilotcooldown/release",
        "/pilot/cooldown/release",
        "/falcon/liveaudit/ack",
        "/paper_lifecycle/update",
        "/paper/lifecycle/update",
        "/paperlifecycleupdate",
        "/paperupdate",
        "/paper_lifecycle/test_tp50",
        "/paper/lifecycle/test_tp50",
        "/paperlifecycletesttp50",
        "/papertesttp50",
        "/paper_lifecycle/test_close",
        "/paper/lifecycle/test_close",
        "/paperlifecycletestclose",
        "/papertestclose",
        "/executionenginerun",
        "/executionrun",
        "/execution_engine/run",
        "/execution/engine/run",
        "/executionverify",
        "/executionengineverify",
        "/execution/verify",
        "/execution/engine/verify",
        # Memory stabilization may invoke GC and trim allocator pages even
        # when gc=false if the process is above its configured RSS threshold.
        "/memory/stabilizer",
        "/memorystabilizer",
    }
    # These legacy GET handlers perform a write by default. Keep them usable
    # only when the caller explicitly selects the handler's documented
    # read-only mode (or explicitly disables its default commit/save).
    default_mutation_paths = {
        "/realpnlr": ("commit", "false"),
        "/realpnlr/text": ("commit", "false"),
        "/adaptive/build": ("commit", "false"),
        "/adaptive_weights/build": ("commit", "false"),
        "/executive/alerts/check": ("check_only", "true"),
        "/executive_alerts/check": ("check_only", "true"),
        "/policyexpiration": ("check_only", "true"),
        "/executive/policy/expiration": ("check_only", "true"),
        "/policytimeline": ("check_only", "true"),
        "/executive/policy/timeline": ("check_only", "true"),
        "/policylearning": ("check_only", "true"),
        "/executive/policy/learning": ("check_only", "true"),
        "/policylearningseed": ("check_only", "true"),
        "/executive/policy/learning/seed": ("check_only", "true"),
        "/policyeffect": ("check_only", "true"),
        "/executive/policy/learning/effect": ("check_only", "true"),
        "/policyeffectseed": ("check_only", "true"),
        "/executive/policy/learning/effect/seed": ("check_only", "true"),
        "/policyeffectrebuild": ("check_only", "true"),
        "/executive/policy/learning/effect/rebuild": ("check_only", "true"),
        # Keep reconciliation GETs available as previews, but reject an
        # explicit commit intent at the shared HTTP boundary as well.
        "/falcon/centralonly/reconcile": ("commit", "false"),
        "/falcon/centralonly/reconcile/text": ("commit", "false"),
    }
    action_fields = {
        "auto_rebuild",
        "autorebuild",
        "ack",
        "clear_block",
        "close",
        "close_registry",
        "close_ack",
        "commit",
        "confirmation",
        "confirmation_phrase",
        "confirm",
        "execute",
        "evaluate",
        "evaluate_closed",
        "execution_confirm",
        "force",
        "force_notify",
        "notify",
        "notify_only",
        "persist",
        "record",
        "record_decision",
        "rebuild",
        "rebuild_registry",
        "repair_registry",
        "restore",
        "restore_from_snapshot",
        "restore_registry",
        "save",
        "send",
        "send_test",
        "update_registry",
        "mark_closed",
    }
    false_values = {"", "0", "false", "no", "off", "none", "null"}
    true_values = {"1", "true", "yes", "on", "sim"}

    if normalized_path in action_paths:
        blocked = {
            "ok": False,
            "status": "GET_MUTATION_REQUIRES_POST",
            "write_executed": False,
            "order_attempted": False,
            "no_order_sent": True,
        }

    else:
        blocked = None

    path_flag = default_mutation_paths.get(normalized_path)
    if path_flag is not None:
        field, allowed_value = path_flag
        try:
            values = args.getlist(field)
        except Exception:
            try:
                value = args.get(field)
            except Exception:
                value = None
            values = value if isinstance(value, (list, tuple)) else ([] if value is None else [value])
        normalized_values = [str(value or "").strip().lower() for value in values]
        allowed_values = false_values if allowed_value == "false" else true_values
        if not normalized_values or any(value not in allowed_values for value in normalized_values):
            blocked = {
                "ok": False,
                "status": "GET_MUTATION_REQUIRES_POST",
                "write_executed": False,
                "order_attempted": False,
                "no_order_sent": True,
            }
    if blocked is not None:
        return blocked

    for field in action_fields:
        try:
            values = args.getlist(field)
        except Exception:
            try:
                value = args.get(field)
            except Exception:
                value = None
            values = value if isinstance(value, (list, tuple)) else [value]
        if any(str(value or "").strip().lower() not in false_values for value in values):
            return {
                "ok": False,
                "status": "GET_MUTATION_REQUIRES_POST",
                "write_executed": False,
                "order_attempted": False,
                "no_order_sent": True,
            }
    try:
        action_values = args.getlist("action")
    except Exception:
        try:
            action = args.get("action")
        except Exception:
            action = None
        action_values = action if isinstance(action, (list, tuple)) else ([] if action is None else [action])
    safe_actions = {"", "preview", "status", "health", "read", "check", "none"}
    if any(str(value or "").strip().lower() not in safe_actions for value in action_values):
        return {
            "ok": False,
            "status": "GET_MUTATION_REQUIRES_POST",
            "write_executed": False,
            "order_attempted": False,
            "no_order_sent": True,
        }
    return None


def central_personal_http_auth(target_url):
    """Return Basic credentials only for this service's own HTTPS/loopback URL."""
    try:
        target = urlsplit(str(target_url or ""))
        target_host = (target.hostname or "").lower()
        target_scheme = target.scheme.lower()
        target_port = target.port
    except (TypeError, ValueError):
        return None

    if not target_host or target.username is not None or target.password is not None:
        return None

    loopback_hosts = {"localhost", "127.0.0.1", "::1"}
    try:
        configured_port = int(os.environ.get("PORT", "10000"))
    except (TypeError, ValueError):
        configured_port = None
    is_loopback_target = (
        target_scheme == "http"
        and target_host in loopback_hosts
        and configured_port is not None
        and target_port == configured_port
    )

    is_render_origin = False
    render_url = os.environ.get("RENDER_EXTERNAL_URL")
    if render_url:
        try:
            expected = urlsplit(render_url)
            expected_host = (expected.hostname or "").lower()
            expected_scheme = expected.scheme.lower()
            expected_port = expected.port or (443 if expected_scheme == "https" else 80)
            actual_port = target_port or (443 if target_scheme == "https" else 80)
            is_render_origin = bool(
                expected_scheme == "https"
                and target_scheme == "https"
                and expected_host
                and target_host == expected_host
                and actual_port == expected_port
                and expected.username is None
                and expected.password is None
            )
        except (TypeError, ValueError):
            is_render_origin = False

    if not (is_loopback_target or is_render_origin):
        return None

    username, passwords = central_personal_http_auth_expected_passwords()
    if not username or not passwords:
        return None
    return username, passwords[0]
