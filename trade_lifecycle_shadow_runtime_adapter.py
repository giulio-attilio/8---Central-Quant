"""Passive runtime adapter for Trade Lifecycle Manager V3 Shadow Mode.

The adapter consumes caller-supplied facts, never acquires operational authority,
and never imports Broker or writes to the operational Trade Registry.
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional

import trade_lifecycle_manager as lifecycle_manager


VERSION = "1.0.0-SHADOW"
MODE = "SHADOW"
_TRUE = {"1", "true", "yes", "sim", "on"}
LOGGER = logging.getLogger(__name__)
LEGACY_EVENT_MAP = {
    "SIGNAL": "SIGNAL_CREATED",
    "SIGNAL_CREATED": "SIGNAL_CREATED",
    "DECISION_PENDING": "DECISION_PENDING_RECORDED",
    "DECISION_ALLOWED": "DECISION_ALLOWED_RECORDED",
    "DECISION_DENIED": "DECISION_DENIED_RECORDED",
    "RISK_PENDING": "RISK_PENDING_RECORDED",
    "RISK_APPROVED": "RISK_APPROVED_RECORDED",
    "RISK_DENIED": "RISK_DENIED_RECORDED",
    "ENTRY_INTENT": "ENTRY_INTENT_CREATED",
    "ENTRY_SUBMITTED": "ENTRY_SUBMITTED",
    "ENTRY_UNKNOWN": "ENTRY_SUBMISSION_BECAME_UNKNOWN",
    "ENTRY_FILL": "ENTRY_FILL_RECORDED",
    "ENTRY_CONFIRMED": "ENTRY_CONFIRMED",
    "STOP_REQUESTED": "DISASTER_STOP_REQUESTED",
    "STOP_CONFIRMED": "DISASTER_STOP_CONFIRMED",
    "STOP_FAILED": "DISASTER_STOP_FAILED",
    "POSITION_MANAGED": "POSITION_MANAGEMENT_STARTED",
    "TRADE_UPDATED": "TRADE_UPDATED",
    "TP50_REQUESTED": "TP50_REQUESTED",
    "TP50_FILL": "TP50_FILL_RECORDED",
    "TP50_CONFIRMED": "TP50_CONFIRMED",
    "RUNNER_PROTECTED": "RUNNER_PROTECTION_CONFIRMED",
    "BREAK_EVEN_REQUESTED": "BREAK_EVEN_REQUESTED",
    "BREAK_EVEN_CONFIRMED": "BREAK_EVEN_CONFIRMED",
    "TRAILING_REQUESTED": "TRAILING_REQUESTED",
    "TRAILING_CONFIRMED": "TRAILING_CONFIRMED",
    "CLOSE_REQUESTED": "CLOSE_REQUESTED",
    "CLOSE_FILL": "CLOSE_FILL_RECORDED",
    "CLOSE_CONFIRMED": "CLOSE_CONFIRMED",
    "OUTCOME": "OUTCOME_CONFIRMED",
    "EXTERNAL_POSITION": "EXTERNAL_POSITION_DETECTED",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def _first(record: Mapping[str, Any], keys: Iterable[str]) -> Any:
    metadata = record.get("metadata") if isinstance(record.get("metadata"), Mapping) else {}
    for key in keys:
        if record.get(key) not in (None, ""):
            return record.get(key)
        if metadata.get(key) not in (None, ""):
            return metadata.get(key)
    return None


def _canonical_identity(record: Mapping[str, Any]) -> Dict[str, str]:
    identity = {
        "trade_id": _first(record, ("trade_id", "canonical_trade_id")),
        "registry_id": _first(record, ("registry_id",)),
        "execution_id": _first(record, ("execution_id",)),
        "decision_id": _first(record, ("decision_id",)),
        "signal_id": _first(record, ("signal_id",)),
    }
    value = next((str(value).strip() for value in identity.values() if value not in (None, "")), "")
    if not value:
        stable = {
            "bot": _first(record, ("bot",)),
            "setup": _first(record, ("setup",)),
            "source_id": _first(record, ("source_id", "id")),
            "opened_at": _first(record, ("opened_at", "created_at")),
        }
        if not any(stable.values()):
            return {"value": "", "source": "INSUFFICIENT_IDENTITY"}
        digest = hashlib.sha256(json.dumps(stable, sort_keys=True, default=str).encode()).hexdigest()[:24]
        return {"value": f"CENTRAL-SHADOW-{digest.upper()}", "source": "DETERMINISTIC_FALLBACK"}
    source = next(key for key, item in identity.items() if item not in (None, ""))
    return {"value": value, "source": source.upper()}


class TradeLifecycleShadowRuntimeAdapter:
    """Thread-safe, fail-open adapter with no operational authority."""

    def __init__(self, *, enabled: Optional[bool] = None, data_dir: Optional[Path] = None, manager: Any = None) -> None:
        configured = os.getenv("TRADE_LIFECYCLE_SHADOW_RUNTIME_ADAPTER_ENABLED", "false").strip().lower() in _TRUE
        self.enabled = configured if enabled is None else bool(enabled)
        self.manager = manager or lifecycle_manager
        root = Path(data_dir) if data_dir is not None else Path(os.getenv("TRADE_LIFECYCLE_SHADOW_DATA_DIR") or os.getenv("CENTRAL_DATA_DIR") or Path(__file__).resolve().parent / "data")
        self.events_file = root / "trade_lifecycle_shadow_runtime_events.jsonl"
        self.divergences_file = root / "trade_lifecycle_shadow_runtime_divergences.jsonl"
        self.state_file = root / "trade_lifecycle_shadow_runtime_state.json"
        self._lock = threading.RLock()
        self._seen: set[str] = set()
        self._divergence_keys: set[str] = set()
        self._metrics = {"observed": 0, "applied": 0, "duplicate": 0, "blocked": 0, "errors": 0, "reconciled": 0, "divergences": 0}
        self._last_error: Optional[str] = None

    def _result(self, status: str, *, ok: bool = True, **extra: Any) -> Dict[str, Any]:
        return {"ok": ok, "status": status, "mode": MODE, "shadow_mode": True, "production_blocked": False, "operational_authority": False, **extra}

    def _append(self, path: Path, item: Mapping[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(item, ensure_ascii=False, default=str) + "\n")

    def _persist_state(self) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        temp = self.state_file.with_suffix(self.state_file.suffix + ".tmp")
        temp.write_text(json.dumps({"version": VERSION, "updated_at": _now(), "metrics": self._metrics}, indent=2), encoding="utf-8")
        os.replace(temp, self.state_file)

    def _event_id(self, event_type: str, identity: str, source: Mapping[str, Any]) -> str:
        supplied = _first(source, ("event_id",))
        if supplied:
            return str(supplied)
        material = {
            "event_type": event_type,
            "identity": identity,
            "source_event_id": _first(source, ("source_event_id", "registry_event_id", "execution_id", "fill_id", "order_id")),
            "occurred_at": _first(source, ("occurred_at", "timestamp", "updated_at", "last_update", "opened_at", "closed_at")),
            "sequence": _first(source, ("sequence", "revision", "version", "attempt")),
        }
        digest = hashlib.sha256(json.dumps(material, sort_keys=True, default=str).encode()).hexdigest()
        return f"CENTRAL-SHADOW-EVENT-{digest[:32].upper()}"

    def observe_event(self, event_type: str, payload: Dict[str, Any], *, persist: bool = True) -> Dict[str, Any]:
        """Normalize and forward a factual event; never propagate an exception."""
        try:
            if not isinstance(payload, dict):
                return self._result("INVALID_CONTRACT", ok=False, reasons=["payload must be dict"])
            original = copy.deepcopy(payload)
            canonical = LEGACY_EVENT_MAP.get(str(event_type or "").upper().strip(), str(event_type or "").upper().strip())
            if not self.enabled:
                return self._result("DISABLED", forwarded=False, event_type=canonical)
            identity = _canonical_identity(original)
            lifecycle_id = str(_first(original, ("lifecycle_id",)) or "").strip()
            external = bool(_first(original, ("external_position", "manual_position"))) or canonical == "EXTERNAL_POSITION_DETECTED"
            if external and not lifecycle_id:
                lifecycle_id = f"CENTRAL-SHADOW-EXTERNAL-{hashlib.sha256(json.dumps(original, sort_keys=True, default=str).encode()).hexdigest()[:24].upper()}"
            if not lifecycle_id:
                if external:
                    lifecycle_id = f"CENTRAL-SHADOW-EXTERNAL-{hashlib.sha256(json.dumps(original, sort_keys=True, default=str).encode()).hexdigest()[:24].upper()}"
                else:
                    return self._result("INSUFFICIENT_IDENTITY", ok=False, forwarded=False, reasons=["lifecycle_id missing"])
            if not identity["value"] and not external:
                return self._result("INSUFFICIENT_IDENTITY", ok=False, forwarded=False, reasons=["canonical trade identity missing"])
            event_id = self._event_id(canonical, identity["value"] or lifecycle_id, original)
            key = f"{lifecycle_id}|{canonical}|{event_id}"
            with self._lock:
                self._metrics["observed"] += 1
                if key in self._seen:
                    self._metrics["duplicate"] += 1
                    return self._result("DUPLICATE", duplicate=True, event_id=event_id, lifecycle_id=lifecycle_id)
                event = {"event_id": event_id, "event_type": canonical, "lifecycle_id": lifecycle_id, "source_component": str(_first(original, ("source_component", "source")) or "SHADOW_RUNTIME_ADAPTER"), "occurred_at": str(_first(original, ("occurred_at", "timestamp", "updated_at")) or _now()), "evidence": _json_safe(original.get("evidence") or original), "payload": _json_safe(original)}
                if canonical in {"SIGNAL_CREATED", "EXTERNAL_POSITION_DETECTED"}:
                    create_payload = copy.deepcopy(original)
                    create_payload.update({"lifecycle_id": lifecycle_id, "trade_id": "" if external else identity["value"], "external_position": external, "manual_position": external})
                    if external:
                        create_payload["bot"] = ""
                        create_payload["setup"] = ""
                        create_payload["signal_id"] = ""
                        create_payload["decision_id"] = ""
                    result = self.manager.create_lifecycle(create_payload, persist=persist)
                elif canonical == "TRADE_UPDATED":
                    # Lifecycle V3 has no dedicated generic-update transition. Keep this as a shadow-only observation
                    # without mutating lifecycle state or implying a management/TP/close transition.
                    result = {"ok": True, "event_applied": False, "duplicate": False, "blocked": False, "status": "NOOP", "warning": "TRADE_UPDATED is a registry-side observation and does not map to a lifecycle transition"}
                else:
                    result = self.manager.apply_event(lifecycle_id, event, persist=persist)
                if result.get("duplicate"):
                    self._seen.add(key)
                    self._metrics["duplicate"] += 1
                    status = "DUPLICATE"
                elif result.get("event_applied"):
                    self._seen.add(key)
                    self._metrics["applied"] += 1
                    status = "APPLIED"
                else:
                    self._metrics["blocked"] += 1
                    status = "BLOCKED"
                journal = {"timestamp": _now(), "event_id": event_id, "event_type": canonical, "lifecycle_id": lifecycle_id, "identity": identity, "status": status, "manager_result": _json_safe(result)}
                if persist:
                    self._append(self.events_file, journal)
                    self._persist_state()
                return self._result(status, ok=status in {"APPLIED", "DUPLICATE"}, duplicate=status == "DUPLICATE", forwarded=True, event_id=event_id, lifecycle_id=lifecycle_id, manager_result=result)
        except Exception as exc:
            with self._lock:
                self._metrics["errors"] += 1
                self._last_error = f"{type(exc).__name__}: {exc}"
            LOGGER.warning("shadow runtime adapter observe_event failed: %s", exc)
            return self._result("ERROR", ok=False, forwarded=False, error=self._last_error)

    def reconcile_trade(self, registry_trade: Dict[str, Any], *, persist: bool = True) -> Dict[str, Any]:
        try:
            if not self.enabled:
                return self._result("DISABLED", reconciled=False)
            lifecycle_id = str(_first(registry_trade, ("lifecycle_id",)) or "")
            if not lifecycle_id:
                return self._result("INSUFFICIENT_IDENTITY", ok=False, reconciled=False)
            comparison = self.manager.compare_with_registry(lifecycle_id, copy.deepcopy(registry_trade))
            with self._lock:
                self._metrics["reconciled"] += 1
                differences = comparison.get("differences") or []
                for difference in differences:
                    key = hashlib.sha256(json.dumps({"lifecycle_id": lifecycle_id, "field": difference.get("field"), "shadow": difference.get("shadow_value"), "registry": difference.get("registry_value")}, sort_keys=True, default=str).encode()).hexdigest()
                    if key in self._divergence_keys:
                        continue
                    self._divergence_keys.add(key)
                    self._metrics["divergences"] += 1
                    if persist:
                        self._append(self.divergences_file, {"timestamp": _now(), "key": key, **difference})
                if persist:
                    self._persist_state()
            return self._result(comparison.get("status", "UNKNOWN"), ok=True, reconciled=True, comparison=comparison)
        except Exception as exc:
            with self._lock:
                self._metrics["errors"] += 1
                self._last_error = f"{type(exc).__name__}: {exc}"
            LOGGER.warning("shadow runtime adapter reconcile_trade failed: %s", exc)
            return self._result("ERROR", ok=False, reconciled=False, error=self._last_error)

    def reconcile_all(self, registry_snapshot: Dict[str, Any], *, persist: bool = True) -> Dict[str, Any]:
        try:
            open_items = registry_snapshot.get("open_trades", {})
            closed_items = registry_snapshot.get("closed_trades", [])
            records = list(open_items.values()) if isinstance(open_items, dict) else list(open_items or [])
            records.extend(list(closed_items or []))
            results = [self.reconcile_trade(item, persist=persist) for item in records if isinstance(item, dict)]
            return self._result("RECONCILED", count=len(results), results=results)
        except Exception as exc:
            return self._result("ERROR", ok=False, error=f"{type(exc).__name__}: {exc}")

    def get_metrics(self) -> Dict[str, Any]:
        try:
            with self._lock:
                return self._result("OK", metrics=copy.deepcopy(self._metrics))
        except Exception as exc:
            return self._result("ERROR", ok=False, error=str(exc))

    def get_health(self) -> Dict[str, Any]:
        try:
            manager_health = self.manager.trade_lifecycle_health()
            return self._result("ENABLED" if self.enabled else "DISABLED", enabled=self.enabled, version=VERSION, operational_authority=False, broker_access=False, registry_write_access=False, last_error=self._last_error, metrics=self.get_metrics().get("metrics", {}), lifecycle_manager_health=manager_health)
        except Exception as exc:
            return self._result("ERROR", ok=False, enabled=self.enabled, version=VERSION, broker_access=False, registry_write_access=False, error=str(exc))


_default_adapter = TradeLifecycleShadowRuntimeAdapter()


def safe_observe_shadow_event(event_type: str, payload: Dict[str, Any], *, persist: bool = True) -> Dict[str, Any]:
    """Stable fail-open entrypoint for runtime producers."""
    return _default_adapter.observe_event(event_type, payload, persist=persist)


def safe_reconcile_shadow_trade(registry_trade: Dict[str, Any], *, persist: bool = True) -> Dict[str, Any]:
    """Read-only best-effort comparison for a Registry-confirmed snapshot."""
    return _default_adapter.reconcile_trade(registry_trade, persist=persist)


__all__ = ["TradeLifecycleShadowRuntimeAdapter", "safe_observe_shadow_event", "safe_reconcile_shadow_trade", "VERSION", "MODE"]
