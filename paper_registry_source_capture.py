"""One-shot, read-only capture of bot position snapshots for PAPER review.

The source values and Registry rows stay in process memory. The command makes
one Upstash MGET request, writes nothing, and emits only sanitized counts and
classification statuses. Its output is never an import/migration plan.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
import warnings
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from paper_state_storage import open_paper_binary, paper_data_mount_verified
from paper_registry_source_preview import (
    preview_paper_registry_sources,
    source_snapshot_structure_diagnostics,
)


_BOT_KEYS = (
    ("COBRA", "cobra:positions"),
    ("DONKEY", "donkey:positions"),
    ("FALCON", "falcon:positions"),
    ("MEME", "memepro:positions"),
    ("PREDATOR", "smartpredator:positions"),
    ("TRENDPRO", "trendpro:positions"),
    ("TURTLE", "turtle_pro:positions"),
)

# Only expose fixed, reviewed validation labels in production-shell output.
# Never print exception text from snapshots: malformed values may contain
# trade identifiers, arbitrary user strings, or other production data.
_SAFE_PREVIEW_ERROR_CODES = {
    "registry_snapshot_object_required": "REGISTRY_SNAPSHOT_OBJECT_REQUIRED",
    "registry_open_trades_invalid": "REGISTRY_OPEN_TRADES_INVALID",
    "registry_closed_trades_invalid": "REGISTRY_CLOSED_TRADES_INVALID",
    "registry_open_trades_row_invalid": "REGISTRY_OPEN_TRADES_ROW_INVALID",
    "registry_closed_trades_row_invalid": "REGISTRY_CLOSED_TRADES_ROW_INVALID",
    "source_snapshot_object_required": "SOURCE_SNAPSHOT_OBJECT_REQUIRED",
    "source_positions_by_bot_invalid": "SOURCE_POSITIONS_BY_BOT_INVALID",
    "source_status_by_bot_invalid": "SOURCE_STATUS_BY_BOT_INVALID",
    "source_status_bot_set_incomplete": "SOURCE_STATUS_BOT_SET_INCOMPLETE",
    "source_bot_name_invalid": "SOURCE_BOT_NAME_INVALID",
    "source_positions_bot_unknown": "SOURCE_POSITIONS_BOT_UNKNOWN",
    "source_positions_missing_for_ok_bot": "SOURCE_POSITIONS_MISSING_FOR_OK_BOT",
    "source_positions_for_bot_invalid": "SOURCE_POSITIONS_FOR_BOT_INVALID",
    "source_position_invalid": "SOURCE_POSITION_INVALID",
    "source_bot_key_conflict": "SOURCE_BOT_KEY_CONFLICT",
    "source_bot_alias_conflict": "SOURCE_BOT_ALIAS_CONFLICT",
}


def _safe_preview_error_code(exc: Exception) -> str:
    """Return a fixed diagnostic code without exposing exception details."""
    if isinstance(exc, ValueError):
        return _SAFE_PREVIEW_ERROR_CODES.get(str(exc), "UNCLASSIFIED_VALUE_ERROR")
    if isinstance(exc, TypeError):
        return "UNCLASSIFIED_TYPE_ERROR"
    return "UNCLASSIFIED_PREVIEW_ERROR"


def _registry_path(path: str | Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    explicit = os.environ.get("TRADE_REGISTRY_FILE")
    if explicit:
        return Path(explicit)
    data_dir = os.environ.get("CENTRAL_DATA_DIR") or os.environ.get("DATA_DIR") or "/data"
    return Path(data_dir) / "trade_registry.json"


def _load_registry_snapshot(path: Path) -> tuple[Mapping[str, Any] | None, str]:
    if not path.is_file():
        return None, "REGISTRY_FILE_MISSING"
    try:
        with open_paper_binary(path, "rb") as handle:
            raw = handle.read()
        registry = json.loads(
            raw.decode("utf-8"),
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError("non_finite_json_number")),
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        return None, "REGISTRY_READ_INVALID"
    if not isinstance(registry, Mapping):
        return None, "REGISTRY_SCHEMA_INVALID"
    for collection in ("open_trades", "closed_trades"):
        if not isinstance(registry.get(collection), (Mapping, list)):
            return None, "REGISTRY_SCHEMA_INVALID"
    return registry, "OK"


def _default_registry_storage_status(path: Path) -> str:
    """Require the configured active Registry to live on the persistent data dir."""
    data_dir = Path(os.environ.get("CENTRAL_DATA_DIR") or os.environ.get("DATA_DIR") or "/data")
    try:
        path.resolve().relative_to(data_dir.resolve())
    except (OSError, ValueError):
        return "REGISTRY_OUTSIDE_DATA_DIR"
    if not (
        paper_data_mount_verified(data_dir, platform_name="posix")
        and paper_data_mount_verified(path, platform_name="posix")
    ):
        return "DATA_MOUNT_NOT_VERIFIED"
    return "OK"


def _decode_source_value(value: Any) -> Mapping[str, Any] | list[Any] | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    if isinstance(value, str):
        value = json.loads(
            value,
            parse_constant=lambda _item: (_ for _ in ()).throw(ValueError("non_finite_json_number")),
        )
    if isinstance(value, (Mapping, list)):
        return value
    raise ValueError("source_snapshot_shape_invalid")


def _source_snapshot(redis_client: Any) -> dict[str, Any]:
    bots = tuple(bot for bot, _key in _BOT_KEYS)
    statuses = {bot: "READ_FAILED" for bot in bots}
    positions: dict[str, Any] = {}
    try:
        values = redis_client.mget(*(key for _bot, key in _BOT_KEYS))
    except Exception:
        return {"source_status_by_bot": statuses, "positions_by_bot": positions}
    if not isinstance(values, (list, tuple)) or len(values) != len(_BOT_KEYS):
        return {"source_status_by_bot": statuses, "positions_by_bot": positions}

    for (bot, _key), value in zip(_BOT_KEYS, values):
        if value is None:
            statuses[bot] = "KEY_MISSING"
            continue
        try:
            decoded = _decode_source_value(value)
        except (UnicodeError, json.JSONDecodeError, ValueError):
            statuses[bot] = "INVALID_JSON"
            continue
        if not isinstance(decoded, (Mapping, list)):
            statuses[bot] = "INVALID_SHAPE"
            continue
        statuses[bot] = "OK"
        positions[bot] = decoded
    return {"source_status_by_bot": statuses, "positions_by_bot": positions}


def capture_paper_registry_sources(
    *,
    redis_client: Any | None = None,
    registry_path: str | Path | None = None,
    upstash_readonly_token_provider: Callable[[], str] | None = None,
) -> dict[str, Any]:
    """Read Registry and source positions; return sanitized review counts only."""
    path = _registry_path(registry_path)
    # On Render, even an explicitly supplied path must remain inside the
    # verified persistent mount. Explicit paths are permitted for local tests.
    is_render = os.environ.get("RENDER", "").strip().lower() == "true"
    if registry_path is None or is_render:
        storage_status = _default_registry_storage_status(path)
        if storage_status != "OK":
            return {
                "ok": False,
                "status": storage_status,
                "source_status_by_bot": {},
                "all_rows_ineligible_for_import": True,
                "writes_performed": False,
            }
    registry, registry_status = _load_registry_snapshot(path)
    if registry is None:
        return {
            "ok": False,
            "status": registry_status,
            "source_status_by_bot": {},
            "all_rows_ineligible_for_import": True,
            "writes_performed": False,
        }

    if redis_client is None:
        url = os.environ.get("UPSTASH_REDIS_REST_URL")
        # Deliberately refuse the application's potentially long-lived token.
        # A caller may provide an interactive hidden prompt so no persistent
        # Render environment-variable change is needed for a one-shot read.
        if upstash_readonly_token_provider is not None:
            try:
                token = upstash_readonly_token_provider()
            except Exception:
                return {
                    "ok": False,
                    "status": "UPSTASH_READ_ONLY_TOKEN_PROMPT_FAILED",
                    "source_status_by_bot": {},
                    "all_rows_ineligible_for_import": True,
                    "writes_performed": False,
                }
        else:
            token = os.environ.get("UPSTASH_REDIS_REST_READONLY_TOKEN")
        if not url or not isinstance(token, str) or not token.strip():
            return {
                "ok": False,
                "status": "UPSTASH_READ_ONLY_CONFIG_MISSING",
                "source_status_by_bot": {},
                "all_rows_ineligible_for_import": True,
                "writes_performed": False,
            }
        token = token.strip()
        try:
            from upstash_redis import Redis

            redis_client = Redis(url=url, token=token)
        except Exception:
            return {
                "ok": False,
                "status": "UPSTASH_CLIENT_UNAVAILABLE",
                "source_status_by_bot": {},
                "all_rows_ineligible_for_import": True,
                "writes_performed": False,
            }

    source = _source_snapshot(redis_client)
    try:
        preview = preview_paper_registry_sources(registry, source)
    except Exception as exc:
        try:
            source_diagnostics = source_snapshot_structure_diagnostics(source)
        except Exception:
            source_diagnostics = {"record_count": 0, "by_bot": {}}
        return {
            "ok": False,
            "status": "SOURCE_SNAPSHOT_INVALID",
            "validation_error_code": _safe_preview_error_code(exc),
            "source_status_by_bot": source["source_status_by_bot"],
            "source_diagnostics": source_diagnostics,
            "all_rows_ineligible_for_import": True,
            "writes_performed": False,
        }

    complete = preview["source_snapshot_complete"] is True
    # The offline preview is intentionally detailed, but it includes arbitrary
    # status/execution_mode values as mapping keys. Keep only structural counts
    # in the production-shell report so malformed or user-controlled strings
    # cannot escape through otherwise "sanitized" output.
    source_diagnostics = preview["source_diagnostics"]
    safe_source_diagnostics = {
        "record_count": source_diagnostics["record_count"],
        "by_bot": {
            bot: {
                key: details[key]
                for key in (
                    "source_status",
                    "record_count",
                    "records_with_close_marker",
                    "records_without_close_marker",
                    "derived_logical_trade_id_records",
                    "identity_field_presence_counts",
                )
            }
            for bot, details in source_diagnostics["by_bot"].items()
        },
    }
    return {
        "ok": complete,
        "status": "PREVIEW_COMPLETE_NOT_MIGRATABLE" if complete else "SOURCE_SNAPSHOT_INCOMPLETE",
        "registry_open_count": preview["registry_open_count"],
        "registry_closed_count": preview["registry_closed_count"],
        "source_position_count": preview["source_position_count"],
        "source_status_by_bot": source["source_status_by_bot"],
        "source_diagnostics": safe_source_diagnostics,
        "identity_alias_conflict_field_counts": preview[
            "identity_alias_conflict_field_counts"
        ],
        "registry_status_counts": preview["registry_status_counts"],
        "registry_closed_status_counts": preview["registry_closed_status_counts"],
        "registry_mode_claim_counts": preview["registry_mode_claim_counts"],
        "registry_mode_status_counts": preview["registry_mode_status_counts"],
        "registry_closed_mode_status_counts": preview["registry_closed_mode_status_counts"],
        "source_reconciliation_counts": preview["source_reconciliation_counts"],
        "unmatched_source_count": preview["unmatched_source_count"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "cross_store_atomic_snapshot": False,
        "all_rows_ineligible_for_import": True,
        "writes_performed": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only sanitized comparison of PAPER Registry and Upstash bot snapshots."
    )
    parser.add_argument("--registry-file", help="Registry JSON path; defaults to the configured data directory.")
    parser.add_argument(
        "--read-upstash",
        action="store_true",
        help="Explicitly perform one read-only MGET for the seven bot position keys.",
    )
    parser.add_argument(
        "--prompt-readonly-token",
        action="store_true",
        help="Prompt for a Read-Only token without echo; requires an interactive terminal.",
    )
    args = parser.parse_args(argv)
    if not args.read_upstash:
        print(json.dumps({
            "ok": False,
            "status": "UPSTASH_READ_NOT_REQUESTED",
            "all_rows_ineligible_for_import": True,
            "writes_performed": False,
        }, sort_keys=True))
        return 2
    token_provider = None
    if args.prompt_readonly_token:
        def token_provider() -> str:
            with warnings.catch_warnings():
                # Fail closed rather than falling back to an echoed prompt on
                # Render Shells without a controlling TTY.
                warnings.simplefilter("error", getpass.GetPassWarning)
                return getpass.getpass("Temporary Upstash Read-Only token (input hidden): ")

    report = capture_paper_registry_sources(
        registry_path=args.registry_file,
        upstash_readonly_token_provider=token_provider,
    )
    print(json.dumps(report, sort_keys=True, ensure_ascii=False))
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
