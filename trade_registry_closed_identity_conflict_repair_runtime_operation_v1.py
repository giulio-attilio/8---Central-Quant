"""Protected runtime preview/apply operation for one CLOSED financial conflict.

Construction is side-effect free and apply is default-off.  The controller
accepts injected Registry/audit/lock/control dependencies so tests never need
the application runtime.  A preview selects an existing factual source value;
apply revalidates the exact preimage under the Registry lock, creates an
immutable content-addressed backup, atomically replaces the target and verifies
the result.  Any uncertainty fails closed.
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
import os
import tempfile
import threading
import time
from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_OPERATION_V1_VERSION = (
    "2026-09-05-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-OPERATION-V1"
)
PREVIEW_ACK_V1 = "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_PREVIEW_V1"
APPLY_ACK_V1 = "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_APPLY_V1"
APPLY_SCOPE_ATTESTATION_V1 = (
    "C3_CLOSED_IDENTITY_CONFLICT_REPAIR_EXPLICIT_PRODUCTION_APPLY_V1"
)

_EXPECTED_FIELDS = frozenset({"close_reason", "pnl_r"})
_MAX_PREVIEW_AGE_SECONDS = 300


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _stable_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _document_copy(value: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(_canonical_json(dict(value)))


def _valid_sha256(value: Any) -> str:
    normalized = str(value or "").lower().strip()
    if len(normalized) != 64:
        return ""
    try:
        bytes.fromhex(normalized)
    except ValueError:
        return ""
    return normalized


def _read_path(record: Mapping[str, Any], path: str) -> tuple[bool, Any]:
    parts = str(path or "").split(".")
    if len(parts) < 2 or parts[0] != "trade" or any(not item for item in parts):
        return False, None
    current: Any = record
    for part in parts[1:]:
        if not isinstance(current, Mapping) or part not in current:
            return False, None
        current = current[part]
    return True, current


def _write_path(record: dict[str, Any], path: str, value: Any) -> bool:
    parts = str(path or "").split(".")
    if len(parts) < 2 or parts[0] != "trade" or any(not item for item in parts):
        return False
    current: Any = record
    for part in parts[1:-1]:
        if not isinstance(current, dict) or not isinstance(current.get(part), dict):
            return False
        current = current[part]
    leaf = parts[-1]
    if not isinstance(current, dict) or leaf not in current:
        return False
    current[leaf] = copy.deepcopy(value)
    return True


def _closed_record_at(document: Mapping[str, Any], index: int) -> Mapping[str, Any] | None:
    closed = document.get("closed_trades")
    if isinstance(closed, list):
        if 0 <= index < len(closed) and isinstance(closed[index], Mapping):
            return closed[index]
        return None
    if isinstance(closed, Mapping):
        rows = list(closed.values())
        if 0 <= index < len(rows) and isinstance(rows[index], Mapping):
            return rows[index]
    return None


def _mutable_closed_record_at(document: dict[str, Any], index: int) -> dict[str, Any] | None:
    closed = document.get("closed_trades")
    if isinstance(closed, list):
        if 0 <= index < len(closed) and isinstance(closed[index], dict):
            return closed[index]
        return None
    if isinstance(closed, dict):
        keys = list(closed)
        if 0 <= index < len(keys) and isinstance(closed[keys[index]], dict):
            return closed[keys[index]]
    return None


def _closed_record_document_prefix(document: Mapping[str, Any], index: int) -> str:
    closed = document.get("closed_trades")
    if isinstance(closed, list):
        return f"closed_trades[{index}]"
    if isinstance(closed, Mapping):
        keys = list(closed)
        if 0 <= index < len(keys):
            return f"closed_trades.{keys[index]}"
    return ""


def _leaf_differences(before: Any, after: Any, prefix: str = "") -> set[str]:
    if isinstance(before, Mapping) and isinstance(after, Mapping):
        paths: set[str] = set()
        for key in set(before) | set(after):
            child = f"{prefix}.{key}" if prefix else str(key)
            if key not in before or key not in after:
                paths.add(child)
            else:
                paths.update(_leaf_differences(before[key], after[key], child))
        return paths
    if isinstance(before, list) and isinstance(after, list):
        paths = set()
        if len(before) != len(after):
            paths.add(prefix)
            return paths
        for index, (left, right) in enumerate(zip(before, after)):
            paths.update(_leaf_differences(left, right, f"{prefix}[{index}]"))
        return paths
    return set() if before == after else {prefix}


def _sync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


@dataclass(frozen=True)
class ClosedIdentityRepairRuntimeConfigV1:
    apply_enabled: bool = False
    apply_scope_attestation: str | None = field(default=None, repr=False)
    preview_ttl_seconds: int = _MAX_PREVIEW_AGE_SECONDS


class ClosedIdentityRepairRuntimeOperationV1:
    """Build reviewed previews and conditionally apply one exact transaction."""

    def __init__(
        self,
        *,
        registry_loader: Callable[[], Mapping[str, Any]],
        conflict_auditor: Callable[[], Mapping[str, Any]],
        registry_lock: Callable[[], AbstractContextManager[Any] | None],
        trading_controls: Callable[[], Mapping[str, Any]],
        target_path: str | os.PathLike[str],
        backup_root: str | os.PathLike[str],
        config: ClosedIdentityRepairRuntimeConfigV1 | None = None,
        clock: Callable[[], float] | None = None,
        replacer: Callable[[str, str], None] | None = None,
        fault_injector: Callable[[str], None] | None = None,
    ) -> None:
        self._registry_loader = registry_loader
        self._conflict_auditor = conflict_auditor
        self._registry_lock = registry_lock
        self._trading_controls = trading_controls
        self._target = Path(target_path).resolve(strict=False)
        self._backup_root = Path(backup_root).resolve(strict=False)
        self._config = config or ClosedIdentityRepairRuntimeConfigV1()
        self._clock = clock or time.time
        self._replacer = replacer or os.replace
        self._fault_injector = fault_injector or (lambda _step: None)
        self._pending: dict[str, dict[str, Any]] = {}
        self._state_lock = threading.RLock()

    def snapshot(self) -> dict[str, Any]:
        return {
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_OPERATION_V1_VERSION,
            "default_off": not self._config.apply_enabled,
            "preview_available": True,
            "apply_enabled": self._config.apply_enabled,
            "pending_preview_count": len(self._pending),
            "real_registry_accessed": False,
            "write_executed": False,
            "registry_write": False,
            "broker_called": False,
            "no_order_sent": True,
        }

    @staticmethod
    def _base() -> dict[str, Any]:
        return {
            "ok": False,
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_OPERATION_V1_VERSION,
            "real_registry_accessed": False,
            "write_executed": False,
            "registry_write": False,
            "broker_called": False,
            "no_order_sent": True,
        }

    def _build_candidate(
        self, selected_sources: Mapping[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        result = self._base()
        try:
            registry = self._registry_loader()
            audit = self._conflict_auditor()
            source = _document_copy(registry)
        except Exception as exc:
            result.update(status="REPAIR_PREVIEW_READ_FAILED", reason=type(exc).__name__)
            return result, None
        result["real_registry_accessed"] = True
        conflicts = list(audit.get("conflicts") or []) if isinstance(audit, Mapping) else []
        if not (
            audit.get("ok") is True
            and audit.get("read_only") is True
            and audit.get("write_executed") is False
            and len(conflicts) == 1
        ):
            result.update(status="REPAIR_PREVIEW_CONFLICT_SET_MISMATCH")
            return result, None
        conflict = conflicts[0]
        fields = frozenset(conflict.get("financial_conflict_fields") or [])
        indexes = list(conflict.get("registry_indexes_envolvidos") or [])
        if fields != _EXPECTED_FIELDS or conflict.get("record_count") != 1 or len(indexes) != 1:
            result.update(status="REPAIR_PREVIEW_SCOPE_MISMATCH")
            return result, None
        index = indexes[0]
        if not isinstance(index, int) or isinstance(index, bool):
            result.update(status="REPAIR_PREVIEW_INDEX_INVALID")
            return result, None
        record = _closed_record_at(source, index)
        if not isinstance(record, Mapping):
            result.update(status="REPAIR_PREVIEW_RECORD_UNAVAILABLE")
            return result, None
        source_map = conflict.get("conflicting_value_sources_by_field") or {}
        options: dict[str, list[dict[str, Any]]] = {}
        selected_values: dict[str, Any] = {}
        selected_paths: dict[str, str] = {}
        all_update_paths: dict[str, list[str]] = {}
        missing_selections: list[str] = []
        for field_name in sorted(_EXPECTED_FIELDS):
            field_sources = source_map.get(field_name) or []
            field_options: list[dict[str, Any]] = []
            actual_by_path: dict[str, Any] = {}
            for item in field_sources:
                path = str((item or {}).get("path") or "")
                exists, actual_value = _read_path(record, path)
                if not exists or actual_value != (item or {}).get("value"):
                    result.update(status="REPAIR_PREVIEW_SOURCE_EVIDENCE_DRIFT")
                    return result, None
                actual_by_path[path] = actual_value
                field_options.append(
                    {
                        "path": path,
                        "value": copy.deepcopy(actual_value),
                        "value_sha256": _stable_sha256(actual_value),
                    }
                )
            requested_path = str(selected_sources.get(field_name) or "")
            options[field_name] = sorted(field_options, key=lambda item: item["path"])
            if requested_path not in actual_by_path:
                missing_selections.append(field_name)
                continue
            selected_paths[field_name] = requested_path
            selected_values[field_name] = copy.deepcopy(actual_by_path[requested_path])
            all_update_paths[field_name] = sorted(actual_by_path)

        if missing_selections:
            result.update(
                status="REPAIR_PREVIEW_SELECTION_REQUIRED",
                selection_options=options,
                required_fields=sorted(_EXPECTED_FIELDS),
                missing_or_invalid_selections=missing_selections,
            )
            return result, None

        candidate = _document_copy(source)
        mutable_record = _mutable_closed_record_at(candidate, index)
        if mutable_record is None:
            result.update(status="REPAIR_PREVIEW_RECORD_UNAVAILABLE")
            return result, None
        expected_changed: set[str] = set()
        for field_name in sorted(_EXPECTED_FIELDS):
            for path in all_update_paths[field_name]:
                exists, old_value = _read_path(mutable_record, path)
                if not exists or not _write_path(mutable_record, path, selected_values[field_name]):
                    result.update(status="REPAIR_PREVIEW_PATH_UPDATE_FAILED")
                    return result, None
                if old_value != selected_values[field_name]:
                    prefix = _closed_record_document_prefix(candidate, index)
                    if not prefix:
                        result.update(status="REPAIR_PREVIEW_RECORD_LOCATOR_INVALID")
                        return result, None
                    expected_changed.add(f"{prefix}.{path[6:]}")
        actual_changed = _leaf_differences(source, candidate)
        if actual_changed != expected_changed or not actual_changed:
            result.update(status="REPAIR_PREVIEW_PRESERVATION_FAILED")
            return result, None
        source_sha = _stable_sha256(source)
        candidate_sha = _stable_sha256(candidate)
        conflict_binding = {
            "source_registry_sha256": source_sha,
            "registry_index": index,
            "fields": sorted(_EXPECTED_FIELDS),
            "source_paths": {
                field_name: [item["path"] for item in options[field_name]]
                for field_name in sorted(options)
            },
            "source_value_sha256": {
                field_name: [item["value_sha256"] for item in options[field_name]]
                for field_name in sorted(options)
            },
        }
        material = {
            "source_registry": source,
            "candidate_registry": candidate,
            "source_registry_sha256": source_sha,
            "candidate_registry_sha256": candidate_sha,
            "conflict_binding_sha256": _stable_sha256(conflict_binding),
            "selected_source_paths": selected_paths,
            "changed_paths": sorted(actual_changed),
            "registry_index": index,
        }
        result.update(
            ok=True,
            status="REPAIR_PREVIEW_CANDIDATE_VERIFIED",
            source_registry_sha256=source_sha,
            candidate_registry_sha256=candidate_sha,
            conflict_binding_sha256=material["conflict_binding_sha256"],
            selected_source_paths=selected_paths,
            changed_paths=sorted(actual_changed),
            selection_options=options,
            preservation_verified=True,
        )
        return result, material

    def preview(self, request_payload: Mapping[str, Any]) -> dict[str, Any]:
        result = self._base()
        if not isinstance(request_payload, Mapping):
            result.update(status="REPAIR_PREVIEW_REQUEST_INVALID")
            return result
        if str(request_payload.get("ack") or "") != PREVIEW_ACK_V1:
            result.update(status="REPAIR_PREVIEW_ACK_REQUIRED", required_ack=PREVIEW_ACK_V1)
            return result
        selections = request_payload.get("selected_sources")
        if not isinstance(selections, Mapping):
            selections = {}
        elif not set(selections).issubset(_EXPECTED_FIELDS):
            result.update(status="REPAIR_PREVIEW_SELECTION_FIELDS_INVALID")
            return result
        result, material = self._build_candidate(selections)
        if material is None:
            return result
        issued_at = int(self._clock())
        ttl = max(1, min(int(self._config.preview_ttl_seconds), _MAX_PREVIEW_AGE_SECONDS))
        receipt = {
            "receipt_version": "C3_CLOSED_IDENTITY_REPAIR_PREVIEW_RECEIPT_V1",
            "source_registry_sha256": material["source_registry_sha256"],
            "candidate_registry_sha256": material["candidate_registry_sha256"],
            "conflict_binding_sha256": material["conflict_binding_sha256"],
            "selected_source_paths": material["selected_source_paths"],
            "changed_paths": material["changed_paths"],
            "issued_at_epoch": issued_at,
            "expires_at_epoch": issued_at + ttl,
            "apply_allowed": False,
        }
        receipt["preview_receipt_sha256"] = _stable_sha256(receipt)
        receipt_sha = receipt["preview_receipt_sha256"]
        with self._state_lock:
            self._pending[receipt_sha] = {
                "receipt": copy.deepcopy(receipt),
                "selected_sources": dict(material["selected_source_paths"]),
            }
        result.update(preview_receipt=receipt, apply_enabled=self._config.apply_enabled)
        return result

    def _controls_safe(self) -> bool:
        try:
            controls = self._trading_controls()
        except Exception:
            return False
        return bool(
            isinstance(controls, Mapping)
            and controls.get("enable_real_trading") is False
            and controls.get("broker_dry_run") is True
            and controls.get("falcon_mode") == "VERIFY"
            and controls.get("central_real_execution_enabled") is False
            and controls.get("central_real_pilot_enabled") is False
            and controls.get("live_trading_enabled") is False
            and controls.get("order_submission_authorized") is False
        )

    def apply(self, request_payload: Mapping[str, Any]) -> dict[str, Any]:
        result = self._base()
        if not self._config.apply_enabled:
            result.update(status="REPAIR_APPLY_DEFAULT_OFF")
            return result
        if self._config.apply_scope_attestation != APPLY_SCOPE_ATTESTATION_V1:
            result.update(status="REPAIR_APPLY_SCOPE_ATTESTATION_REQUIRED")
            return result
        if not isinstance(request_payload, Mapping):
            result.update(status="REPAIR_APPLY_REQUEST_INVALID")
            return result
        if str(request_payload.get("ack") or "") != APPLY_ACK_V1:
            result.update(status="REPAIR_APPLY_ACK_REQUIRED", required_ack=APPLY_ACK_V1)
            return result
        receipt_sha = _valid_sha256(request_payload.get("preview_receipt_sha256"))
        with self._state_lock:
            pending = copy.deepcopy(self._pending.get(receipt_sha))
        if not pending:
            result.update(status="REPAIR_APPLY_PREVIEW_REQUIRED")
            return result
        if isinstance(pending.get("committed_result"), Mapping):
            result.update(copy.deepcopy(pending["committed_result"]))
            result["status"] = "REPAIR_TRANSACTION_ALREADY_COMMITTED"
            result["idempotent_replay"] = True
            result["write_executed"] = False
            result["registry_write"] = False
            return result
        receipt = pending["receipt"]
        if int(self._clock()) > int(receipt["expires_at_epoch"]):
            result.update(status="REPAIR_APPLY_PREVIEW_EXPIRED")
            return result
        if not self._controls_safe():
            result.update(status="REPAIR_APPLY_TRADING_CONTROLS_UNSAFE")
            return result
        lock = self._registry_lock()
        if lock is None:
            result.update(status="REPAIR_APPLY_REGISTRY_LOCK_UNAVAILABLE")
            return result
        try:
            with lock:
                validation, material = self._build_candidate(pending["selected_sources"])
                if material is None:
                    result["real_registry_accessed"] = bool(
                        validation.get("real_registry_accessed")
                    )
                    result.update(status="REPAIR_APPLY_REVALIDATION_FAILED")
                    return result
                if not (
                    hmac.compare_digest(
                        material["source_registry_sha256"], receipt["source_registry_sha256"]
                    )
                    and hmac.compare_digest(
                        material["candidate_registry_sha256"], receipt["candidate_registry_sha256"]
                    )
                    and hmac.compare_digest(
                        material["conflict_binding_sha256"], receipt["conflict_binding_sha256"]
                    )
                ):
                    result.update(status="REPAIR_APPLY_COMPARE_AND_SWAP_MISMATCH")
                    result["real_registry_accessed"] = True
                    return result
                transaction = self._apply_file_transaction(material, receipt_sha)
        except Exception as exc:
            result.update(status="REPAIR_APPLY_FAILED_CLOSED", reason=type(exc).__name__)
            return result
        result.update(transaction)
        if transaction.get("ok") is True:
            with self._state_lock:
                if receipt_sha in self._pending:
                    self._pending[receipt_sha]["committed_result"] = copy.deepcopy(
                        transaction
                    )
        return result

    def _apply_file_transaction(
        self, material: Mapping[str, Any], receipt_sha: str
    ) -> dict[str, Any]:
        result = self._base()
        if self._target.parent != self._backup_root.parent:
            result.update(status="REPAIR_TRANSACTION_PATH_BINDING_INVALID")
            return result
        try:
            raw_before = self._target.read_bytes()
            current = json.loads(raw_before.decode("utf-8"))
            current_sha = _stable_sha256(current)
            result["real_registry_accessed"] = True
        except Exception as exc:
            result.update(status="REPAIR_TRANSACTION_SOURCE_READ_FAILED", reason=type(exc).__name__)
            return result
        source_sha = material["source_registry_sha256"]
        candidate_sha = material["candidate_registry_sha256"]
        if hmac.compare_digest(current_sha, candidate_sha):
            result.update(
                ok=True,
                status="REPAIR_TRANSACTION_ALREADY_COMMITTED",
                idempotent_replay=True,
            )
            return result
        if not hmac.compare_digest(current_sha, source_sha):
            result.update(status="REPAIR_TRANSACTION_COMPARE_AND_SWAP_MISMATCH")
            return result
        self._backup_root.mkdir(parents=True, exist_ok=True)
        backup = self._backup_root / f"{source_sha}.{receipt_sha}.json"
        try:
            if backup.exists():
                backup_payload = json.loads(backup.read_text(encoding="utf-8"))
                if not hmac.compare_digest(_stable_sha256(backup_payload), source_sha):
                    raise RuntimeError("BACKUP_CONTENT_MISMATCH")
            else:
                with backup.open("xb") as handle:
                    handle.write(raw_before)
                    handle.flush()
                    os.fsync(handle.fileno())
                _sync_directory(self._backup_root)
            self._fault_injector("AFTER_BACKUP")
        except Exception as exc:
            result.update(status="REPAIR_TRANSACTION_BACKUP_FAILED", reason=type(exc).__name__)
            return result

        candidate_bytes = (
            json.dumps(
                material["candidate_registry"],
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
        staged_path: Path | None = None
        replaced = False
        try:
            descriptor, staged_name = tempfile.mkstemp(
                prefix=f".{self._target.name}.c3-repair-",
                suffix=".tmp",
                dir=str(self._target.parent),
            )
            staged_path = Path(staged_name)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(candidate_bytes)
                handle.flush()
                os.fsync(handle.fileno())
            self._fault_injector("BEFORE_REPLACE")
            self._replacer(str(staged_path), str(self._target))
            staged_path = None
            replaced = True
            _sync_directory(self._target.parent)
            self._fault_injector("AFTER_REPLACE")
            verified = json.loads(self._target.read_text(encoding="utf-8"))
            if not hmac.compare_digest(_stable_sha256(verified), candidate_sha):
                raise RuntimeError("CANDIDATE_VERIFY_FAILED")
            result.update(
                ok=True,
                status="REPAIR_TRANSACTION_COMMITTED",
                write_executed=True,
                registry_write=True,
                source_registry_sha256=source_sha,
                candidate_registry_sha256=candidate_sha,
                backup_name=backup.name,
                idempotent_replay=False,
            )
            return result
        except Exception as exc:
            rollback_confirmed = False
            if replaced:
                try:
                    descriptor, rollback_name = tempfile.mkstemp(
                        prefix=f".{self._target.name}.c3-rollback-",
                        suffix=".tmp",
                        dir=str(self._target.parent),
                    )
                    rollback_path = Path(rollback_name)
                    with os.fdopen(descriptor, "wb") as handle:
                        handle.write(raw_before)
                        handle.flush()
                        os.fsync(handle.fileno())
                    self._replacer(str(rollback_path), str(self._target))
                    _sync_directory(self._target.parent)
                    restored = json.loads(self._target.read_text(encoding="utf-8"))
                    rollback_confirmed = hmac.compare_digest(
                        _stable_sha256(restored), source_sha
                    )
                except Exception:
                    rollback_confirmed = False
            result.update(
                status=(
                    "REPAIR_TRANSACTION_FAILED_ROLLED_BACK"
                    if rollback_confirmed
                    else "REPAIR_TRANSACTION_FAILED_CLOSED"
                ),
                reason=type(exc).__name__,
                write_executed=bool(replaced),
                registry_write=False,
                rollback_attempted=bool(replaced),
                rollback_confirmed=rollback_confirmed,
                backup_name=backup.name,
            )
            return result
        finally:
            if staged_path is not None:
                try:
                    staged_path.unlink(missing_ok=True)
                except Exception:
                    pass


__all__ = [
    "APPLY_ACK_V1",
    "APPLY_SCOPE_ATTESTATION_V1",
    "ClosedIdentityRepairRuntimeConfigV1",
    "ClosedIdentityRepairRuntimeOperationV1",
    "PREVIEW_ACK_V1",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_OPERATION_V1_VERSION",
]
