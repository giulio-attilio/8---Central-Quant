"""Bounded, passive readers for Trade Lifecycle Shadow Runtime evidence.

This module has no operational authority.  It never imports the Registry,
Lifecycle Manager, Broker, HTTP clients, or the application runtime, and it
never writes to the evidence it observes.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import hmac
import json
import os
import threading
import time
import uuid
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Mapping, Optional, Tuple


VERSION = "1.0.0-SHADOW"
SCHEMA_VERSION = "1.0"
MODE = "SHADOW"
MODULE = "trade_lifecycle_shadow_observability"
ENV_ENABLED = "TRADE_LIFECYCLE_SHADOW_OBSERVABILITY_ENABLED"

DEFAULT_LIMIT = 50
MAX_LIMIT = 200
MAX_LINE_BYTES = 256 * 1024
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_STRING_LENGTH = 4 * 1024
MAX_DEPTH = 8
MAX_COLLECTION_ITEMS = 100
MAX_READ_BYTES = 8 * 1024 * 1024
MAX_CACHE_ENTRIES = 128
MAX_CACHE_BYTES = 16 * 1024 * 1024
STATE_TTL_SECONDS = 2.0
TAIL_TTL_SECONDS = 5.0
AGGREGATE_TTL_SECONDS = 10.0
STALE_STATE_SECONDS = 300.0

_TRUE = {"1", "true", "yes", "sim", "on"}
_SENSITIVE = {
    "password", "secret", "token", "authorization", "cookie", "api_key",
    "apikey", "private_key", "credential", "headers",
}
_EVENT_FILTERS = {
    "lifecycle_id", "trade_id", "event_id", "bot", "setup", "symbol",
    "side", "event_type", "status", "date_from", "date_to",
}
_DIVERGENCE_FILTERS = {
    "lifecycle_id", "trade_id", "field", "severity", "resolved", "category",
    "date_from", "date_to",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_datetime(value: Any) -> Optional[datetime]:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        raise ValueError("timezone is required")
    return parsed.astimezone(timezone.utc)


def _safe_error(exc: BaseException) -> str:
    text = f"{type(exc).__name__}: {exc}"
    # Paths and raw payloads are not useful in the public contract.
    for part in str(exc).replace("\\", "/").split():
        if "/" in part or ":/" in part:
            text = text.replace(part, "<redacted>")
    return text[:512]


def _authorities() -> Dict[str, bool]:
    return {
        "operational_authority": False,
        "broker_access": False,
        "registry_write_access": False,
        "lifecycle_write_access": False,
        "execution_control": False,
        "automatic_repair": False,
    }


def _base() -> Dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "module": MODULE,
        "version": VERSION,
        "mode": MODE,
        **_authorities(),
    }


def _sanitize(value: Any, depth: int = 0) -> Any:
    if depth >= MAX_DEPTH:
        return "<truncated:depth>"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        if len(value) > MAX_STRING_LENGTH:
            return f"<truncated:string:{len(value)}>"
        return value
    if isinstance(value, Mapping):
        result: Dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= MAX_COLLECTION_ITEMS:
                result["__truncated__"] = f"{len(value) - MAX_COLLECTION_ITEMS} items"
                break
            key_text = str(key)
            if key_text.casefold() in _SENSITIVE:
                result[key_text] = "<redacted>"
            else:
                result[key_text] = _sanitize(item, depth + 1)
        return result
    if isinstance(value, (list, tuple, set)):
        items = list(value)
        result = [_sanitize(item, depth + 1) for item in items[:MAX_COLLECTION_ITEMS]]
        if len(items) > MAX_COLLECTION_ITEMS:
            result.append(f"<truncated:collection:{len(items) - MAX_COLLECTION_ITEMS}>")
        return result
    return _sanitize(str(value), depth)


class _LRUCache:
    def __init__(self, max_entries: int, max_bytes: int) -> None:
        self.max_entries = min(max(1, int(max_entries)), MAX_CACHE_ENTRIES)
        self.max_bytes = min(max(1024, int(max_bytes)), MAX_CACHE_BYTES)
        self._items: "OrderedDict[str, Tuple[float, int, Any]]" = OrderedDict()
        self._bytes = 0
        self._lock = threading.RLock()

    def get(self, key: str) -> Any:
        with self._lock:
            item = self._items.get(key)
            if item is None:
                return None
            expires, size, value = item
            if expires < time.monotonic():
                self._items.pop(key, None)
                self._bytes -= size
                return None
            self._items.move_to_end(key)
            return copy.deepcopy(value)

    def put(self, key: str, value: Any, ttl: float) -> None:
        safe_value = copy.deepcopy(value)
        size = len(json.dumps(safe_value, ensure_ascii=False, default=str).encode("utf-8"))
        if size > self.max_bytes:
            return
        with self._lock:
            previous = self._items.pop(key, None)
            if previous:
                self._bytes -= previous[1]
            self._items[key] = (time.monotonic() + ttl, size, safe_value)
            self._bytes += size
            while len(self._items) > self.max_entries or self._bytes > self.max_bytes:
                _, (_, removed_size, _) = self._items.popitem(last=False)
                self._bytes -= removed_size

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._items)

    @property
    def bytes_used(self) -> int:
        with self._lock:
            return self._bytes


class TradeLifecycleShadowObservability:
    """Read-only facade over Runtime Adapter evidence files."""

    def __init__(
        self,
        *,
        enabled: Optional[bool] = None,
        data_dir: Optional[Path] = None,
        adapter_health_provider: Optional[Callable[[], Dict[str, Any]]] = None,
        adapter_metrics_provider: Optional[Callable[[], Dict[str, Any]]] = None,
        lifecycle_health_provider: Optional[Callable[[], Dict[str, Any]]] = None,
        cursor_secret: Optional[Any] = None,
        max_read_bytes: int = MAX_READ_BYTES,
        max_cache_entries: int = MAX_CACHE_ENTRIES,
        max_cache_bytes: int = MAX_CACHE_BYTES,
        stale_state_seconds: float = STALE_STATE_SECONDS,
    ) -> None:
        configured = os.getenv(ENV_ENABLED, "false").strip().lower() in _TRUE
        self.enabled = configured if enabled is None else bool(enabled)
        root = Path(data_dir) if data_dir is not None else Path(
            os.getenv("TRADE_LIFECYCLE_SHADOW_DATA_DIR")
            or os.getenv("CENTRAL_DATA_DIR")
            or Path(__file__).resolve().parent / "data"
        )
        self.data_dir = root.resolve(strict=False)
        self.events_file = self.data_dir / "trade_lifecycle_shadow_runtime_events.jsonl"
        self.divergences_file = self.data_dir / "trade_lifecycle_shadow_runtime_divergences.jsonl"
        self.state_file = self.data_dir / "trade_lifecycle_shadow_runtime_state.json"
        self.adapter_health_provider = adapter_health_provider
        self.adapter_metrics_provider = adapter_metrics_provider
        self.lifecycle_health_provider = lifecycle_health_provider
        supplied_secret = cursor_secret.encode() if isinstance(cursor_secret, str) else cursor_secret
        self._cursor_secret = bytes(supplied_secret or os.urandom(32))
        self.max_read_bytes = min(max(4096, int(max_read_bytes)), MAX_READ_BYTES)
        self.stale_state_seconds = max(1.0, float(stale_state_seconds))
        self.boot_id = str(uuid.uuid4())
        self.process_started_at = _now()
        self._started_dt = _parse_datetime(self.process_started_at)
        self._cache = _LRUCache(max_cache_entries, max_cache_bytes)
        self._internal_lock = threading.RLock()
        self._internal = {
            "requests": 0,
            "request_errors": 0,
            "journal_read_errors": 0,
            "invalid_json_lines": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "last_successful_read": None,
            "last_error": None,
        }

    def _record(self, **increments: int) -> None:
        with self._internal_lock:
            for key, amount in increments.items():
                self._internal[key] = int(self._internal.get(key) or 0) + amount

    def _success(self) -> None:
        with self._internal_lock:
            self._internal["last_successful_read"] = _now()

    def _failure(self, exc: BaseException, *, journal: bool = False) -> None:
        with self._internal_lock:
            self._internal["request_errors"] += 1
            if journal:
                self._internal["journal_read_errors"] += 1
            self._internal["last_error"] = _safe_error(exc)

    def _internal_snapshot(self) -> Dict[str, Any]:
        with self._internal_lock:
            return copy.deepcopy(self._internal)

    def _disabled(self, kind: str) -> Dict[str, Any]:
        payload = {**_base(), "ok": True, "status": "DISABLED", "enabled": False}
        if kind in {"events", "divergences"}:
            payload.update({"items": [], "page": {"limit": DEFAULT_LIMIT, "returned": 0, "next_cursor": None, "partial": False}})
        return payload

    @staticmethod
    def _file_meta(path: Path) -> Dict[str, Any]:
        if not path.exists():
            return {"exists": False, "size": 0, "mtime_ns": None, "identity": None}
        if not path.is_file():
            raise OSError("evidence source is not a regular file")
        stat = path.stat()
        identity_material = f"{getattr(stat, 'st_dev', 0)}:{getattr(stat, 'st_ino', 0)}"
        return {
            "exists": True,
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
            "identity": hashlib.sha256(identity_material.encode()).hexdigest(),
        }

    def _read_state(self) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
        meta = self._file_meta(self.state_file)
        detail = {**meta, "status": "MISSING" if not meta["exists"] else "UNKNOWN", "stale": False}
        if not meta["exists"]:
            return None, detail
        cache_key = f"state:{meta['identity']}:{meta['size']}:{meta['mtime_ns']}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            self._record(cache_hits=1)
            cached_state, cached_detail = cached
            cached_detail["cached"] = True
            return cached_state, cached_detail
        self._record(cache_misses=1)
        try:
            before = self._file_meta(self.state_file)
            with self.state_file.open("rb") as handle:
                raw = handle.read(min(MAX_LINE_BYTES, before["size"] + 1))
            after = self._file_meta(self.state_file)
            if before != after:
                with self.state_file.open("rb") as handle:
                    raw = handle.read(min(MAX_LINE_BYTES, after["size"] + 1))
                after = self._file_meta(self.state_file)
            if len(raw) > MAX_LINE_BYTES:
                raise ValueError("state exceeds size limit")
            state = json.loads(raw.decode("utf-8"))
            if not isinstance(state, dict) or not isinstance(state.get("metrics"), dict):
                raise ValueError("invalid state contract")
            updated = _parse_datetime(state.get("updated_at"))
            stale = bool(updated and (datetime.now(timezone.utc) - updated).total_seconds() > self.stale_state_seconds)
            detail = {**after, "status": "STALE" if stale else "VALID", "stale": stale, "updated_at": state.get("updated_at"), "cached": False}
            self._cache.put(cache_key, (state, detail), STATE_TTL_SECONDS)
            self._success()
            return state, detail
        except Exception as exc:
            self._failure(exc)
            return None, {**detail, "status": "INVALID", "error": _safe_error(exc)}

    def _encode_cursor(self, payload: Dict[str, Any]) -> str:
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        signature = hmac.new(self._cursor_secret, raw, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(raw + signature).decode().rstrip("=")

    def _decode_cursor(self, token: str) -> Dict[str, Any]:
        if not isinstance(token, str) or not token or len(token) > 4096:
            raise ValueError("INVALID_CURSOR")
        try:
            padded = token + "=" * (-len(token) % 4)
            signed = base64.urlsafe_b64decode(padded.encode())
            raw, supplied = signed[:-32], signed[-32:]
            expected = hmac.new(self._cursor_secret, raw, hashlib.sha256).digest()
            if not hmac.compare_digest(supplied, expected):
                raise ValueError("INVALID_CURSOR")
            payload = json.loads(raw.decode())
            if not isinstance(payload, dict):
                raise ValueError("INVALID_CURSOR")
            return payload
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("INVALID_CURSOR") from exc

    @staticmethod
    def _filter_hash(filters: Dict[str, Any]) -> str:
        return hashlib.sha256(json.dumps(filters, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def _validate_filters(self, filters: Optional[Dict[str, Any]], allowed: set[str]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        if filters is None:
            return {}, None
        if not isinstance(filters, dict):
            return None, "filters must be a dict"
        unknown = sorted(set(filters) - allowed)
        if unknown:
            return None, f"unknown filters: {', '.join(unknown)}"
        normalized: Dict[str, Any] = {}
        try:
            for key, value in filters.items():
                if value is None or value == "":
                    continue
                if key in {"date_from", "date_to"}:
                    parsed = _parse_datetime(value)
                    normalized[key] = parsed.isoformat() if parsed else None
                elif key == "resolved":
                    if isinstance(value, bool):
                        normalized[key] = value
                    elif str(value).lower() in {"true", "false", "null", "unknown"}:
                        normalized[key] = {"true": True, "false": False}.get(str(value).lower())
                    else:
                        raise ValueError("resolved must be true, false, or null")
                else:
                    text = str(value).strip()
                    if len(text) > 128:
                        raise ValueError(f"{key} exceeds 128 characters")
                    normalized[key] = text.upper() if key in {"side", "event_type", "status", "severity", "category"} else text
            if normalized.get("date_from") and normalized.get("date_to"):
                if _parse_datetime(normalized["date_from"]) > _parse_datetime(normalized["date_to"]):
                    raise ValueError("date_from must not exceed date_to")
            return normalized, None
        except Exception as exc:
            return None, _safe_error(exc)

    def _reverse_records(
        self,
        path: Path,
        *,
        source: str,
        filters_hash: str,
        limit: int,
        cursor: Optional[str],
    ) -> Tuple[list[Tuple[Dict[str, Any], int]], Optional[str], bool, Dict[str, int], Optional[str]]:
        meta = self._file_meta(path)
        stats = {"invalid": 0, "truncated": 0, "incomplete": 0, "bytes_read": 0, "records_examined": 0}
        end = meta["size"]
        observed_size = meta["size"]
        if cursor:
            try:
                decoded = self._decode_cursor(cursor)
                typed = (
                    isinstance(decoded.get("v"), str)
                    and isinstance(decoded.get("source"), str)
                    and isinstance(decoded.get("direction"), str)
                    and isinstance(decoded.get("filters"), str)
                    and isinstance(decoded.get("identity"), str)
                    and isinstance(decoded.get("size"), int) and not isinstance(decoded.get("size"), bool)
                    and isinstance(decoded.get("offset"), int) and not isinstance(decoded.get("offset"), bool)
                    and isinstance(decoded.get("mtime"), int) and not isinstance(decoded.get("mtime"), bool)
                )
                if not typed:
                    return [], None, False, stats, "INVALID_CURSOR"
                required = {
                    "v": SCHEMA_VERSION, "source": source, "direction": "backward",
                    "filters": filters_hash,
                }
                if any(decoded.get(key) != value for key, value in required.items()):
                    return [], None, False, stats, "INVALID_CURSOR"
                if decoded["size"] < 0 or decoded["offset"] < 0 or decoded["offset"] > decoded["size"]:
                    return [], None, False, stats, "INVALID_CURSOR"
                if decoded["identity"] != meta["identity"] or meta["size"] < decoded["size"]:
                    return [], None, False, stats, "CURSOR_STALE"
                # Same-size mtime change is not append-only and indicates rewrite/replacement.
                if meta["size"] == decoded["size"] and meta["mtime_ns"] != decoded["mtime"]:
                    return [], None, False, stats, "CURSOR_STALE"
                end = decoded["offset"]
                observed_size = decoded["size"]
            except ValueError:
                return [], None, False, stats, "INVALID_CURSOR"
        if not meta["exists"] or meta["size"] == 0:
            return [], None, False, stats, None
        start = max(0, end - self.max_read_bytes)
        try:
            with path.open("rb") as handle:
                handle.seek(start)
                data = handle.read(end - start)
            stats["bytes_read"] = len(data)
        except Exception as exc:
            self._failure(exc, journal=True)
            return [], None, False, stats, "UNAVAILABLE"
        base = start
        if start > 0:
            newline = data.find(b"\n")
            if newline < 0:
                return [], None, True, stats, None
            data = data[newline + 1:]
            base += newline + 1
        if end == meta["size"] and data and not data.endswith(b"\n"):
            cut = data.rfind(b"\n")
            stats["incomplete"] += 1
            data = data[:cut + 1] if cut >= 0 else b""
        records: list[Tuple[Dict[str, Any], int]] = []
        position = base
        indexed: list[Tuple[bytes, int]] = []
        for raw in data.splitlines(keepends=True):
            indexed.append((raw.rstrip(b"\r\n"), position))
            position += len(raw)
        for raw, offset in reversed(indexed):
            if not raw.strip():
                continue
            if len(raw) > MAX_LINE_BYTES:
                stats["truncated"] += 1
                continue
            try:
                item = json.loads(raw.decode("utf-8"))
                if not isinstance(item, dict):
                    raise ValueError("JSONL item must be object")
                records.append((item, offset))
            except Exception:
                stats["invalid"] += 1
                self._record(invalid_json_lines=1)
        stats["records_examined"] = len(indexed)
        partial = start > 0 or bool(stats["incomplete"] or stats["invalid"] or stats["truncated"])
        next_cursor = None
        if records:
            oldest_offset = records[-1][1]
            if oldest_offset > 0:
                next_cursor = self._encode_cursor({
                    "v": SCHEMA_VERSION, "source": source, "offset": oldest_offset,
                    "direction": "backward", "identity": meta["identity"],
                    "size": observed_size, "mtime": meta["mtime_ns"], "filters": filters_hash,
                })
        self._success()
        return records, next_cursor, partial, stats, None

    @staticmethod
    def _nested_snapshot(item: Dict[str, Any]) -> Dict[str, Any]:
        manager = item.get("manager_result") if isinstance(item.get("manager_result"), dict) else {}
        snapshot = manager.get("snapshot") if isinstance(manager.get("snapshot"), dict) else {}
        return snapshot

    def _project_event(self, item: Dict[str, Any]) -> Dict[str, Any]:
        manager = item.get("manager_result") if isinstance(item.get("manager_result"), dict) else {}
        snapshot = self._nested_snapshot(item)
        identity = item.get("identity") if isinstance(item.get("identity"), dict) else {}
        event_type = item.get("event_type")
        semantic = "NOOP" if manager.get("status") == "NOOP" else manager.get("status")
        external = bool(snapshot.get("external_position")) or event_type == "EXTERNAL_POSITION_DETECTED" or str(item.get("lifecycle_id") or "").startswith("CENTRAL-SHADOW-EXTERNAL-")
        summary = {
            "semantic_status": semantic,
            "duplicate": manager.get("duplicate"),
            "blocked": manager.get("blocked"),
            "warning": manager.get("warning"),
            "reasons": manager.get("reasons") if isinstance(manager.get("reasons"), list) else [],
        }
        return _sanitize({
            "timestamp": item.get("timestamp"),
            "event_id": item.get("event_id"),
            "event_type": event_type,
            "lifecycle_id": item.get("lifecycle_id"),
            "trade_id": snapshot.get("trade_id"),
            "bot": None if external else snapshot.get("bot"),
            "setup": None if external else snapshot.get("setup"),
            "symbol": snapshot.get("symbol"),
            "side": snapshot.get("side"),
            "identity_source": identity.get("source"),
            "status": item.get("status"),
            "summary": summary,
            "external_position": external,
        })

    @staticmethod
    def _matches(item: Dict[str, Any], filters: Dict[str, Any], *, timestamp_key: str = "timestamp") -> bool:
        timestamp = item.get(timestamp_key) or item.get("first_seen_at")
        try:
            if filters.get("date_from") and (not timestamp or _parse_datetime(timestamp) < _parse_datetime(filters["date_from"])):
                return False
            if filters.get("date_to") and (not timestamp or _parse_datetime(timestamp) > _parse_datetime(filters["date_to"])):
                return False
        except Exception:
            return False
        for key, expected in filters.items():
            if key in {"date_from", "date_to"}:
                continue
            actual = item.get(key)
            if isinstance(expected, str) and key in {"side", "event_type", "status", "severity", "category"}:
                if str(actual or "").upper() != expected.upper():
                    return False
            elif actual != expected:
                return False
        return True

    def list_events(self, filters: Optional[Dict[str, Any]] = None, limit: int = DEFAULT_LIMIT, cursor: Optional[str] = None) -> Dict[str, Any]:
        self._record(requests=1)
        try:
            if not self.enabled:
                payload = self._disabled("events")
                payload["page"]["limit"] = limit if isinstance(limit, int) else DEFAULT_LIMIT
                return payload
            if not isinstance(limit, int) or isinstance(limit, bool) or limit < 0 or limit > MAX_LIMIT:
                return {**_base(), "ok": False, "status": "INVALID_LIMIT", "items": [], "page": {"limit": limit, "returned": 0, "next_cursor": None, "partial": False}, "warnings": [], "errors": ["limit must be between 0 and 200"]}
            normalized, error = self._validate_filters(filters, _EVENT_FILTERS)
            if error:
                return {**_base(), "ok": False, "status": "INVALID_FILTER", "items": [], "page": {"limit": limit, "returned": 0, "next_cursor": None, "partial": False}, "warnings": [], "errors": [error]}
            filter_hash = self._filter_hash(normalized or {})
            meta_before = self._file_meta(self.events_file)
            cache_key = f"events:{meta_before['identity']}:{meta_before['size']}:{meta_before['mtime_ns']}:{limit}:{filter_hash}:{cursor or ''}"
            cached = self._cache.get(cache_key)
            if cached is not None:
                self._record(cache_hits=1)
                cached["cached"] = True
                return cached
            self._record(cache_misses=1)
            if limit == 0:
                result = {**_base(), "ok": True, "status": "OK", "items": [], "page": {"limit": 0, "returned": 0, "next_cursor": None, "partial": False, "coverage_complete": True}, "persistence": {"invalid": 0, "truncated": 0, "incomplete": 0, "bytes_read": 0, "records_examined": 0}, "cached": False, "as_of": _now(), "warnings": [], "errors": []}
                self._cache.put(cache_key, result, TAIL_TTL_SECONDS)
                return result
            records, next_cursor, partial, stats, reader_error = self._reverse_records(
                self.events_file, source="events", filters_hash=filter_hash, limit=limit, cursor=cursor,
            )
            if reader_error:
                return {**_base(), "ok": False, "status": reader_error, "items": [], "page": {"limit": limit, "returned": 0, "next_cursor": None, "partial": partial}, "warnings": [], "errors": [reader_error]}
            projected = []
            response_bytes = 0
            cursor_for_page = next_cursor
            for raw, offset in records:
                event = self._project_event(raw)
                if self._matches(event, normalized or {}):
                    item_bytes = len(json.dumps(event, ensure_ascii=False, default=str).encode("utf-8"))
                    if response_bytes + item_bytes > MAX_RESPONSE_BYTES:
                        partial = True
                        meta = self._file_meta(self.events_file)
                        cursor_for_page = self._encode_cursor({"v": SCHEMA_VERSION, "source": "events", "offset": offset, "direction": "backward", "identity": meta["identity"], "size": meta["size"] if cursor is None else self._decode_cursor(cursor)["size"], "mtime": meta["mtime_ns"], "filters": filter_hash}) if offset > 0 else None
                        break
                    projected.append(event)
                    response_bytes += item_bytes
                    if len(projected) >= limit:
                        meta = self._file_meta(self.events_file)
                        cursor_for_page = self._encode_cursor({"v": SCHEMA_VERSION, "source": "events", "offset": offset, "direction": "backward", "identity": meta["identity"], "size": meta["size"] if cursor is None else self._decode_cursor(cursor)["size"], "mtime": meta["mtime_ns"], "filters": filter_hash}) if offset > 0 else None
                        break
            warnings = []
            if stats["invalid"]:
                warnings.append("invalid JSONL lines were isolated")
            if stats["incomplete"]:
                warnings.append("incomplete final line was ignored")
            if stats["truncated"]:
                warnings.append("oversized lines were ignored")
            partial = bool(partial or cursor_for_page)
            coverage_complete = not partial
            result = {**_base(), "ok": True, "status": "PARTIAL" if partial else "OK", "items": projected, "page": {"limit": limit, "returned": len(projected), "next_cursor": cursor_for_page, "partial": partial, "coverage_complete": coverage_complete}, "persistence": stats, "cached": False, "as_of": _now(), "warnings": warnings, "errors": []}
            self._cache.put(cache_key, result, TAIL_TTL_SECONDS)
            return result
        except Exception as exc:
            self._failure(exc)
            return {**_base(), "ok": False, "status": "UNAVAILABLE", "items": [], "page": {"limit": limit if isinstance(limit, int) else DEFAULT_LIMIT, "returned": 0, "next_cursor": None, "partial": True}, "warnings": [], "errors": [_safe_error(exc)]}

    @staticmethod
    def _divergence_identity(item: Dict[str, Any], category: str) -> str:
        material = {
            "lifecycle_id": item.get("lifecycle_id"), "trade_id": item.get("trade_id"),
            "field": item.get("field"), "registry_value": item.get("registry_value"),
            "lifecycle_value": item.get("shadow_value"), "category": category,
        }
        return hashlib.sha256(json.dumps(material, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":")).encode()).hexdigest()

    def _project_divergence(self, item: Dict[str, Any]) -> Dict[str, Any]:
        field = str(item.get("field") or "")
        category = "MISSING_IN_REGISTRY" if field == "MISSING_IN_REGISTRY" else "MISSING_IN_LIFECYCLE" if field == "MISSING_IN_LIFECYCLE" else "EXTERNAL_POSITION" if field == "EXTERNAL_POSITION" else "FIELD_MISMATCH"
        original_severity = str(item.get("severity") or "").upper() or None
        severity = {"CRITICAL": "HIGH", "WARNING": "MEDIUM", "LOW": "LOW"}.get(original_severity, "UNKNOWN")
        timestamp = item.get("timestamp")
        return _sanitize({
            "divergence_id": self._divergence_identity(item, category),
            "lifecycle_id": item.get("lifecycle_id"), "trade_id": item.get("trade_id"),
            "field": item.get("field"), "registry_value": item.get("registry_value"),
            "lifecycle_value": item.get("shadow_value"), "severity": severity,
            "source_severity": original_severity,
            "first_seen_at": timestamp, "last_seen_at": timestamp, "occurrences": 1,
            "resolved": None, "resolved_at": None, "source": "SHADOW_RUNTIME_ADAPTER",
            "category": category,
        })

    def list_divergences(self, filters: Optional[Dict[str, Any]] = None, limit: int = DEFAULT_LIMIT, cursor: Optional[str] = None) -> Dict[str, Any]:
        self._record(requests=1)
        try:
            if not self.enabled:
                payload = self._disabled("divergences")
                payload["page"]["limit"] = limit if isinstance(limit, int) else DEFAULT_LIMIT
                return payload
            if not isinstance(limit, int) or isinstance(limit, bool) or limit < 0 or limit > MAX_LIMIT:
                return {**_base(), "ok": False, "status": "INVALID_LIMIT", "items": [], "page": {"limit": limit, "returned": 0, "next_cursor": None, "partial": False}, "warnings": [], "errors": ["limit must be between 0 and 200"]}
            normalized, error = self._validate_filters(filters, _DIVERGENCE_FILTERS)
            if error:
                return {**_base(), "ok": False, "status": "INVALID_FILTER", "items": [], "page": {"limit": limit, "returned": 0, "next_cursor": None, "partial": False}, "warnings": [], "errors": [error]}
            filter_hash = self._filter_hash(normalized or {})
            meta_before = self._file_meta(self.divergences_file)
            cache_key = f"divergences:{meta_before['identity']}:{meta_before['size']}:{meta_before['mtime_ns']}:{limit}:{filter_hash}:{cursor or ''}:v1"
            cached = self._cache.get(cache_key)
            if cached is not None:
                self._record(cache_hits=1)
                cached["cached"] = True
                return cached
            self._record(cache_misses=1)
            if limit == 0:
                result = {**_base(), "ok": True, "status": "OK", "items": [], "page": {"limit": 0, "returned": 0, "next_cursor": None, "partial": False, "coverage_complete": True}, "persistence": {"invalid": 0, "truncated": 0, "incomplete": 0, "bytes_read": 0, "records_examined": 0}, "cached": False, "as_of": _now(), "warnings": [], "errors": []}
                self._cache.put(cache_key, result, AGGREGATE_TTL_SECONDS)
                return result
            records, next_cursor, partial, stats, reader_error = self._reverse_records(self.divergences_file, source="divergences", filters_hash=filter_hash, limit=limit, cursor=cursor)
            if reader_error:
                return {**_base(), "ok": False, "status": reader_error, "items": [], "page": {"limit": limit, "returned": 0, "next_cursor": None, "partial": partial}, "warnings": [], "errors": [reader_error]}
            grouped: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
            oldest_offset = None
            for raw, offset in records:
                item = self._project_divergence(raw)
                if item["category"] == "EXTERNAL_POSITION":
                    continue
                if not self._matches(item, normalized or {}, timestamp_key="first_seen_at"):
                    continue
                key = item["divergence_id"]
                if key in grouped:
                    grouped[key]["occurrences"] += 1
                    grouped[key]["first_seen_at"] = item["first_seen_at"]
                else:
                    grouped[key] = item
                oldest_offset = offset
                if len(grouped) >= limit:
                    break
            if oldest_offset is not None and oldest_offset > 0:
                meta = self._file_meta(self.divergences_file)
                observed_size = meta["size"] if cursor is None else self._decode_cursor(cursor)["size"]
                next_cursor = self._encode_cursor({"v": SCHEMA_VERSION, "source": "divergences", "offset": oldest_offset, "direction": "backward", "identity": meta["identity"], "size": observed_size, "mtime": meta["mtime_ns"], "filters": filter_hash})
            items = list(grouped.values())
            response_bytes = 0
            bounded_items = []
            for item in items:
                item_bytes = len(json.dumps(item, ensure_ascii=False, default=str).encode("utf-8"))
                if response_bytes + item_bytes > MAX_RESPONSE_BYTES:
                    partial = True
                    break
                bounded_items.append(item)
                response_bytes += item_bytes
            items = bounded_items
            partial = bool(partial or next_cursor)
            coverage_complete = not partial
            for item in items:
                item["coverage_complete"] = coverage_complete
                item["continuation_possible"] = not coverage_complete
            warnings = [message for condition, message in ((stats["invalid"], "invalid JSONL lines were isolated"), (stats["incomplete"], "incomplete final line was ignored"), (stats["truncated"], "oversized lines were ignored")) if condition]
            if not coverage_complete:
                warnings.append("group occurrences cover only the examined page; merge repeated divergence_id values across pages")
            result = {**_base(), "ok": True, "status": "PARTIAL" if partial else "OK", "items": items, "page": {"limit": limit, "returned": len(items), "next_cursor": next_cursor, "partial": partial, "coverage_complete": coverage_complete, "group_continuation_key": "divergence_id"}, "persistence": stats, "cached": False, "as_of": _now(), "warnings": warnings, "errors": []}
            self._cache.put(cache_key, result, AGGREGATE_TTL_SECONDS)
            return result
        except Exception as exc:
            self._failure(exc)
            return {**_base(), "ok": False, "status": "UNAVAILABLE", "items": [], "page": {"limit": limit if isinstance(limit, int) else DEFAULT_LIMIT, "returned": 0, "next_cursor": None, "partial": True}, "warnings": [], "errors": [_safe_error(exc)]}

    def _provider(self, provider: Optional[Callable[[], Dict[str, Any]]], name: str) -> Tuple[Dict[str, Any], Optional[str], bool]:
        if provider is None:
            return {"available": False}, f"{name} provider unavailable", False
        try:
            result = provider()
            if not isinstance(result, dict):
                raise TypeError("provider must return dict")
            sanitized = _sanitize(result)
            unhealthy_statuses = {"ERROR", "UNAVAILABLE", "FAILED", "FAILURE", "DOWN"}
            status = str(result.get("status") or "").upper()
            healthy = result.get("ok") is not False and result.get("available") is not False and status not in unhealthy_statuses
            return sanitized, None if healthy else f"{name} provider unhealthy", healthy
        except Exception as exc:
            return {"available": False, "error": _safe_error(exc)}, f"{name} provider failed", False

    def get_health(self) -> Dict[str, Any]:
        self._record(requests=1)
        try:
            if not self.enabled:
                return {**self._disabled("health"), "adapter": {}, "lifecycle": {}, "persistence": {}, "last_event_at": None, "last_reconciliation_at": None, "last_divergence_at": None, "restart": {"boot_id": self.boot_id, "process_started_at": self.process_started_at, "activity_after_restart": "UNKNOWN"}, "observability_internal": self._internal_snapshot(), "warnings": [], "errors": []}
            state, state_detail = self._read_state()
            adapter, adapter_error, adapter_healthy = self._provider(self.adapter_health_provider, "adapter health")
            lifecycle, lifecycle_error, lifecycle_healthy = self._provider(self.lifecycle_health_provider, "lifecycle health")
            events = self.list_events(limit=1)
            divergences = self.list_divergences(limit=1)
            last_event = events.get("items", [{}])[0].get("timestamp") if events.get("items") else None
            last_divergence = divergences.get("items", [{}])[0].get("last_seen_at") if divergences.get("items") else None
            warnings = [item for item in (adapter_error, lifecycle_error) if item]
            if state_detail.get("status") in {"INVALID", "STALE"}:
                warnings.append(f"state is {state_detail['status'].lower()}")
            if events.get("status") == "PARTIAL" or divergences.get("status") == "PARTIAL":
                warnings.append("journal evidence is partial")
            useful = bool(state or adapter_healthy or lifecycle_healthy or events.get("items") or divergences.get("items"))
            if not useful:
                status, ok = "UNAVAILABLE", False
            elif warnings:
                status, ok = "DEGRADED", True
            else:
                status, ok = "OK", True
            activity = "UNKNOWN"
            if last_event and self._started_dt:
                activity = "CONFIRMED" if _parse_datetime(last_event) >= self._started_dt else "NOT_OBSERVED"
            warnings.append("last_reconciliation_at is unavailable because reconciliation rounds are not persisted")
            return {**_base(), "ok": ok, "status": status, "enabled": True, "adapter": adapter, "lifecycle": lifecycle, "persistence": {"state": state_detail, "events": self._file_meta(self.events_file), "divergences": self._file_meta(self.divergences_file)}, "last_event_at": last_event, "last_reconciliation_at": None, "last_divergence_at": last_divergence, "restart": {"boot_id": self.boot_id, "process_started_at": self.process_started_at, "activity_after_restart": activity}, "observability_internal": self._internal_snapshot(), "warnings": warnings, "errors": [] if ok else ["no useful source or provider"]}
        except Exception as exc:
            self._failure(exc)
            return {**_base(), "ok": False, "status": "UNAVAILABLE", "enabled": True, "adapter": {}, "lifecycle": {}, "persistence": {}, "last_event_at": None, "last_reconciliation_at": None, "last_divergence_at": None, "restart": {"boot_id": self.boot_id, "process_started_at": self.process_started_at, "activity_after_restart": "UNKNOWN"}, "observability_internal": self._internal_snapshot(), "warnings": [], "errors": [_safe_error(exc)]}

    def get_metrics(self) -> Dict[str, Any]:
        self._record(requests=1)
        empty = {
            "events": {"observed": 0, "applied": 0, "noop": 0, "duplicate": 0, "blocked": 0, "errors": 0, "invalid": 0},
            "reconciliation": {"attempted": 0, "matches": None, "divergences": 0, "missing_in_registry": None, "missing_in_lifecycle": None},
            "divergences": {"open": 0, "resolved": 0, "high": 0, "medium": 0, "low": 0, "unknown_resolution": 0},
            "external_positions": {"observed": None, "currently_known": None},
            "persistence": {"invalid_lines": 0, "truncated_lines": 0, "last_state_load": None, "rebuild_count": 0},
        }
        try:
            if not self.enabled:
                return {**_base(), "ok": True, "status": "DISABLED", "enabled": False, "as_of": _now(), "partial": False, **empty, "provenance": {}, "observability_internal": self._internal_snapshot(), "warnings": [], "errors": []}
            state, state_detail = self._read_state()
            provider_metrics, provider_error, _ = self._provider(self.adapter_metrics_provider, "adapter metrics")
            declared = state.get("metrics", {}) if state else provider_metrics.get("metrics", {}) if isinstance(provider_metrics.get("metrics"), dict) else {}
            events_result = self.list_events(limit=MAX_LIMIT)
            divergence_result = self.list_divergences(limit=MAX_LIMIT)
            journal_events = events_result.get("items", [])
            journal_divergences = divergence_result.get("items", [])
            events = dict(empty["events"])
            for key in ("observed", "applied", "duplicate", "blocked", "errors"):
                events[key] = int(declared.get(key) or 0)
            events["noop"] = sum(item.get("summary", {}).get("semantic_status") == "NOOP" for item in journal_events)
            invalid = int(events_result.get("persistence", {}).get("invalid", 0)) + int(divergence_result.get("persistence", {}).get("invalid", 0))
            truncated = int(events_result.get("persistence", {}).get("truncated", 0)) + int(divergence_result.get("persistence", {}).get("truncated", 0))
            events["invalid"] = invalid
            divergence_metrics = dict(empty["divergences"])
            divergence_metrics["open"] = sum(item.get("resolved") is False for item in journal_divergences)
            divergence_metrics["resolved"] = sum(item.get("resolved") is True for item in journal_divergences)
            divergence_metrics["unknown_resolution"] = sum(item.get("resolved") is None for item in journal_divergences)
            for severity, key in (("HIGH", "high"), ("MEDIUM", "medium"), ("LOW", "low")):
                divergence_metrics[key] = sum(item.get("severity") == severity for item in journal_divergences)
            reconciliation = dict(empty["reconciliation"])
            reconciliation["attempted"] = int(declared.get("reconciled") or 0)
            reconciliation["divergences"] = int(declared.get("divergences") or len(journal_divergences))
            events_page = events_result.get("page", {})
            divergences_page = divergence_result.get("page", {})
            events_complete = not bool(events_page.get("next_cursor")) and bool(events_page.get("coverage_complete", not events_page.get("partial", False)))
            divergences_complete = not bool(divergences_page.get("next_cursor")) and bool(divergences_page.get("coverage_complete", not divergences_page.get("partial", False)))
            partial = not events_complete or not divergences_complete or state_detail.get("status") in {"INVALID", "STALE"}
            warnings = [provider_error] if provider_error else []
            if state_detail.get("status") in {"INVALID", "STALE"}:
                warnings.append(f"state is {state_detail['status'].lower()}")
            provenance = {
                "declared_counters": {"source": "adapter_state" if state else "adapter_metrics_provider" if declared else None, "combined_with_journal": False},
                "events": {
                    "source": "runtime_events_journal", "coverage_complete": events_complete,
                    "items_examined": int(events_result.get("persistence", {}).get("records_examined", 0)),
                    "items_projected": len(journal_events),
                    "bytes_read": int(events_result.get("persistence", {}).get("bytes_read", 0)),
                    "next_cursor": bool(events_page.get("next_cursor")),
                    "derived_fields": ["noop", "invalid"],
                },
                "divergences": {
                    "source": "runtime_divergences_journal", "coverage_complete": divergences_complete,
                    "items_examined": int(divergence_result.get("persistence", {}).get("records_examined", 0)),
                    "groups_projected": len(journal_divergences),
                    "bytes_read": int(divergence_result.get("persistence", {}).get("bytes_read", 0)),
                    "next_cursor": bool(divergences_page.get("next_cursor")),
                    "derived_fields": ["open", "resolved", "unknown_resolution", "high", "medium", "low"],
                },
            }
            if not events_complete:
                warnings.append("event-derived metrics cover only the examined range")
            if not divergences_complete:
                warnings.append("divergence-derived metrics cover only the examined range")
            return {**_base(), "ok": True, "status": "PARTIAL" if partial else "OK", "as_of": _now(), "partial": bool(partial), "events": events, "reconciliation": reconciliation, "divergences": divergence_metrics, "external_positions": dict(empty["external_positions"]), "persistence": {"invalid_lines": invalid, "truncated_lines": truncated, "last_state_load": state_detail.get("updated_at"), "rebuild_count": 1 if journal_events or journal_divergences else 0}, "provenance": provenance, "observability_internal": self._internal_snapshot(), "warnings": warnings, "errors": []}
        except Exception as exc:
            self._failure(exc)
            return {**_base(), "ok": False, "status": "UNAVAILABLE", "as_of": _now(), "partial": True, **empty, "provenance": {}, "observability_internal": self._internal_snapshot(), "warnings": [], "errors": [_safe_error(exc)]}

    def get_reconciliation_summary(self) -> Dict[str, Any]:
        self._record(requests=1)
        base = {**_base(), "known_at": None, "last_divergence_at": None, "reconciliation_id": None, "compared": None, "matches": None, "divergences": 0, "errors": 0, "missing_in_registry": None, "missing_in_lifecycle": None, "sample": [], "sample_truncated": False, "evidence_quality": "INSUFFICIENT", "warnings": ["reconciliation round timestamps are not persisted"], "errors_detail": []}
        try:
            if not self.enabled:
                return {**base, "ok": True, "status": "DISABLED"}
            result = self.list_divergences(limit=20)
            if not result.get("ok"):
                return {**base, "ok": False, "status": "UNAVAILABLE", "errors_detail": result.get("errors", [])}
            sample = result.get("items", [])[:20]
            if not sample:
                return {**base, "ok": True, "status": "NO_EVIDENCE"}
            return {**base, "ok": True, "status": "DIVERGENCE" if not result.get("page", {}).get("partial") else "PARTIAL", "known_at": None, "last_divergence_at": sample[0].get("last_seen_at"), "divergences": len(sample), "sample": sample, "sample_truncated": bool(result.get("page", {}).get("next_cursor")), "evidence_quality": "PARTIAL"}
        except Exception as exc:
            self._failure(exc)
            return {**base, "ok": False, "status": "UNAVAILABLE", "errors_detail": [_safe_error(exc)]}


_default_observability = TradeLifecycleShadowObservability()


def get_health() -> Dict[str, Any]:
    return _default_observability.get_health()


def get_metrics() -> Dict[str, Any]:
    return _default_observability.get_metrics()


def list_events(filters: Optional[Dict[str, Any]] = None, limit: int = DEFAULT_LIMIT, cursor: Optional[str] = None) -> Dict[str, Any]:
    return _default_observability.list_events(filters=filters, limit=limit, cursor=cursor)


def list_divergences(filters: Optional[Dict[str, Any]] = None, limit: int = DEFAULT_LIMIT, cursor: Optional[str] = None) -> Dict[str, Any]:
    return _default_observability.list_divergences(filters=filters, limit=limit, cursor=cursor)


def get_reconciliation_summary() -> Dict[str, Any]:
    return _default_observability.get_reconciliation_summary()


__all__ = [
    "TradeLifecycleShadowObservability", "get_health", "get_metrics", "list_events",
    "list_divergences", "get_reconciliation_summary", "VERSION", "SCHEMA_VERSION", "MODE",
]
