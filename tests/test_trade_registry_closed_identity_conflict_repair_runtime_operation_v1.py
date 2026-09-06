from __future__ import annotations

import json
import threading
import ast
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import trade_registry_closed_identity_conflict_repair_runtime_operation_v1 as operation


def _registry() -> dict:
    return {
        "version": "synthetic-v1",
        "open_trades": {"keep": {"trade_id": "open-must-remain-exact"}},
        "closed_trades": [
            {
                "trade_id": "synthetic-closed",
                "status": "CLOSED",
                "close_reason": "BROKER_RECONCILED_CLOSE",
                "pnl_r": -1.26907189,
                "r_multiple": -1.08850668,
                "metadata": {
                    "exit_reason": "STOP",
                    "outcome": {
                        "close_reason": "BROKER_RECONCILED_CLOSE",
                        "r_multiple": -1.08850668,
                    },
                    "keep": {"nested": True},
                },
            }
        ],
        "extension": {"must_remain_exact": True},
    }


def _audit_for(registry: dict) -> dict:
    trade = registry["closed_trades"][0]
    return {
        "ok": True,
        "read_only": True,
        "write_executed": False,
        "conflicts": [
            {
                "financial_conflict_fields": ["close_reason", "pnl_r"],
                "record_count": 1,
                "registry_indexes_envolvidos": [0],
                "conflicting_value_sources_by_field": {
                    "close_reason": [
                        {
                            "path": "trade.close_reason",
                            "value": trade["close_reason"],
                        },
                        {
                            "path": "trade.metadata.exit_reason",
                            "value": trade["metadata"]["exit_reason"],
                        },
                        {
                            "path": "trade.metadata.outcome.close_reason",
                            "value": trade["metadata"]["outcome"]["close_reason"],
                        },
                    ],
                    "pnl_r": [
                        {"path": "trade.pnl_r", "value": trade["pnl_r"]},
                        {
                            "path": "trade.r_multiple",
                            "value": trade["r_multiple"],
                        },
                        {
                            "path": "trade.metadata.outcome.r_multiple",
                            "value": trade["metadata"]["outcome"]["r_multiple"],
                        },
                    ],
                },
            }
        ],
    }


def _safe_controls() -> dict:
    return {
        "enable_real_trading": False,
        "broker_dry_run": True,
        "falcon_mode": "VERIFY",
        "central_real_execution_enabled": False,
        "central_real_pilot_enabled": False,
        "live_trading_enabled": False,
        "order_submission_authorized": False,
    }


def _safe_writer_coordination() -> dict:
    return {
        "enabled": True,
        "coordination_ready": True,
        "runtime_activation_allowed": True,
        "registered_writer_count": 19,
        "all_writers_registered": True,
        "inflight_mutations": 0,
        "shared_lock_backend_ready": True,
        "maintenance_lease_store_ready": True,
        "registry_interlock_ready": True,
        "activation_receipt_verified": True,
        "source_hashes_verified": True,
        "rollback_ready": True,
        "kill_switch_ready": True,
        "kill_switch_engaged": False,
    }


@contextmanager
def _safe_maintenance_lease(events=None):
    if events is not None:
        events.append("maintenance_enter")
    try:
        yield SimpleNamespace(
            state="QUIESCED",
            registered_writer_count=19,
            inflight_mutations=0,
            shared_lock_acquired=True,
            maintenance_epoch="a" * 64,
            lock_namespace_sha256="b" * 64,
        )
    finally:
        if events is not None:
            events.append("maintenance_exit")


def _selections() -> dict:
    return {
        "close_reason": "trade.metadata.exit_reason",
        "pnl_r": "trade.pnl_r",
    }


def _controller(
    target: Path,
    *,
    apply_enabled: bool,
    controls=None,
    fault_injector=None,
    now: list[float] | None = None,
) -> operation.ClosedIdentityRepairRuntimeOperationV1:
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        target.write_text(json.dumps(_registry()), encoding="utf-8")

    def loader():
        return json.loads(target.read_text(encoding="utf-8"))

    return operation.ClosedIdentityRepairRuntimeOperationV1(
        registry_loader=loader,
        conflict_auditor=lambda: _audit_for(loader()),
        registry_lock=lambda: threading.RLock(),
        trading_controls=controls or _safe_controls,
        target_path=target,
        backup_root=target.parent / "c3_closed_identity_repair_backups",
        writer_coordination_status=_safe_writer_coordination,
        maintenance_lease=_safe_maintenance_lease,
        config=operation.ClosedIdentityRepairRuntimeConfigV1(
            apply_enabled=apply_enabled,
            apply_scope_attestation=(
                operation.APPLY_SCOPE_ATTESTATION_V1 if apply_enabled else None
            ),
        ),
        clock=(lambda: now[0]) if now is not None else None,
        fault_injector=fault_injector,
    )


def _preview(controller):
    return controller.preview(
        {
            "ack": operation.PREVIEW_ACK_V1,
            "selected_sources": _selections(),
            "gross_r_source": "trade.r_multiple",
        }
    )


def _apply(controller, preview):
    return controller.apply(
        {
            "ack": operation.APPLY_ACK_V1,
            "preview_receipt_sha256": preview["preview_receipt"][
                "preview_receipt_sha256"
            ],
        }
    )


def test_construction_and_default_off_apply_do_not_access_registry(tmp_path) -> None:
    calls = []
    controller = operation.ClosedIdentityRepairRuntimeOperationV1(
        registry_loader=lambda: calls.append("load"),
        conflict_auditor=lambda: calls.append("audit"),
        registry_lock=lambda: calls.append("lock"),
        trading_controls=lambda: calls.append("controls"),
        target_path=tmp_path / "absent" / "trade_registry.json",
        backup_root=tmp_path / "absent" / "backups",
    )

    assert controller.snapshot()["default_off"] is True
    result = controller.apply(
        {"ack": operation.APPLY_ACK_V1, "preview_receipt_sha256": "0" * 64}
    )
    assert result["status"] == "REPAIR_APPLY_DEFAULT_OFF"
    assert result["write_executed"] is False
    assert calls == []
    assert (tmp_path / "absent").exists() is False


def test_preview_requires_existing_source_choices_and_never_writes(tmp_path) -> None:
    target = tmp_path / "data" / "trade_registry.json"
    controller = _controller(target, apply_enabled=False)
    before = target.read_bytes()

    missing = controller.preview({"ack": operation.PREVIEW_ACK_V1})
    assert missing["status"] == "REPAIR_PREVIEW_SELECTION_REQUIRED"
    assert set(missing["selection_options"]) == {"close_reason", "pnl_r"}

    missing_gross = controller.preview(
        {
            "ack": operation.PREVIEW_ACK_V1,
            "selected_sources": _selections(),
        }
    )
    assert missing_gross["status"] == "REPAIR_PREVIEW_GROSS_R_SOURCE_REQUIRED"
    assert missing_gross["write_executed"] is False

    preview = _preview(controller)
    assert preview["ok"] is True
    assert preview["status"] == "REPAIR_PREVIEW_CANDIDATE_VERIFIED"
    assert preview["preservation_verified"] is True
    assert preview["gross_r_preservation_verified"] is True
    assert preview["gross_r_preservation"] == {
        "source_path": "trade.r_multiple",
        "equivalent_source_paths": [
            "trade.metadata.outcome.r_multiple",
            "trade.r_multiple",
        ],
        "value": -1.08850668,
        "value_sha256": operation._stable_sha256(-1.08850668),
        "target_paths": [
            "trade.gross_r_multiple",
            "trade.metadata.outcome.gross_r_multiple",
        ],
        "verified": True,
    }
    assert preview["changed_paths"] == [
        "closed_trades[0].close_reason",
        "closed_trades[0].gross_r_multiple",
        "closed_trades[0].metadata.outcome.close_reason",
        "closed_trades[0].metadata.outcome.gross_r_multiple",
        "closed_trades[0].metadata.outcome.r_multiple",
        "closed_trades[0].r_multiple",
    ]
    assert preview["write_executed"] is False
    assert preview["registry_write"] is False
    assert preview["apply_enabled"] is False
    assert target.read_bytes() == before
    assert (target.parent / "c3_closed_identity_repair_backups").exists() is False


def test_apply_is_atomic_preserves_unrelated_data_and_is_idempotent(tmp_path) -> None:
    target = tmp_path / "data" / "trade_registry.json"
    controller = _controller(target, apply_enabled=True)
    before = json.loads(target.read_text(encoding="utf-8"))
    preview = _preview(controller)
    assert preview["apply_enabled"] is True
    assert preview["preview_receipt"]["apply_allowed"] is True

    applied = _apply(controller, preview)
    assert applied["ok"] is True
    assert applied["status"] == "REPAIR_TRANSACTION_COMMITTED"
    assert applied["write_executed"] is True
    assert applied["registry_write"] is True
    after = json.loads(target.read_text(encoding="utf-8"))
    repaired = after["closed_trades"][0]
    assert repaired["close_reason"] == "STOP"
    assert repaired["metadata"]["outcome"]["close_reason"] == "STOP"
    assert repaired["pnl_r"] == -1.26907189
    assert repaired["r_multiple"] == -1.26907189
    assert repaired["metadata"]["outcome"]["r_multiple"] == -1.26907189
    assert repaired["gross_r_multiple"] == -1.08850668
    assert repaired["metadata"]["outcome"]["gross_r_multiple"] == -1.08850668
    assert after["open_trades"] == before["open_trades"]
    assert after["extension"] == before["extension"]
    backups = list((target.parent / "c3_closed_identity_repair_backups").glob("*.json"))
    assert len(backups) == 1
    assert json.loads(backups[0].read_text(encoding="utf-8")) == before

    replay = _apply(controller, preview)
    assert replay["ok"] is True
    assert replay["status"] == "REPAIR_TRANSACTION_ALREADY_COMMITTED"
    assert replay["idempotent_replay"] is True
    assert replay["write_executed"] is False
    assert len(list((target.parent / "c3_closed_identity_repair_backups").glob("*.json"))) == 1


def test_apply_rejects_expired_preview_drift_and_unsafe_controls(tmp_path) -> None:
    target = tmp_path / "expiry" / "trade_registry.json"
    now = [1000.0]
    controller = _controller(target, apply_enabled=True, now=now)
    preview = _preview(controller)
    now[0] = 1400.0
    expired = _apply(controller, preview)
    assert expired["status"] == "REPAIR_APPLY_PREVIEW_EXPIRED"
    assert expired["write_executed"] is False

    target = tmp_path / "drift" / "trade_registry.json"
    controller = _controller(target, apply_enabled=True)
    preview = _preview(controller)
    drifted = json.loads(target.read_text(encoding="utf-8"))
    drifted["extension"]["concurrent_change"] = True
    target.write_text(json.dumps(drifted), encoding="utf-8")
    conflict = _apply(controller, preview)
    assert conflict["status"] == "REPAIR_APPLY_COMPARE_AND_SWAP_MISMATCH"
    assert conflict["write_executed"] is False

    target = tmp_path / "unsafe" / "trade_registry.json"
    unsafe = _safe_controls()
    unsafe["enable_real_trading"] = True
    controller = _controller(target, apply_enabled=True, controls=lambda: unsafe)
    preview = _preview(controller)
    denied = _apply(controller, preview)
    assert denied["status"] == "REPAIR_APPLY_TRADING_CONTROLS_UNSAFE"
    assert denied["write_executed"] is False


def test_apply_requires_full_writer_coordination_and_quiescent_lease(tmp_path) -> None:
    target = tmp_path / "coordination" / "trade_registry.json"
    controller = _controller(target, apply_enabled=True)
    preview = _preview(controller)
    before = target.read_bytes()

    controller._writer_coordination_status = None
    unavailable = _apply(controller, preview)
    assert unavailable["status"] == "REPAIR_APPLY_WRITER_COORDINATION_UNSAFE"
    assert unavailable["write_executed"] is False

    unsafe = _safe_writer_coordination()
    unsafe["inflight_mutations"] = 1
    controller._writer_coordination_status = lambda: unsafe
    inflight = _apply(controller, preview)
    assert inflight["status"] == "REPAIR_APPLY_WRITER_COORDINATION_UNSAFE"
    assert inflight["write_executed"] is False

    controller._writer_coordination_status = _safe_writer_coordination
    controller._maintenance_lease = None
    missing_lease = _apply(controller, preview)
    assert missing_lease["status"] == "REPAIR_APPLY_MAINTENANCE_LEASE_UNAVAILABLE"
    assert missing_lease["write_executed"] is False

    @contextmanager
    def invalid_lease():
        yield SimpleNamespace(
            state="DRAINING",
            registered_writer_count=19,
            inflight_mutations=0,
            shared_lock_acquired=True,
            maintenance_epoch="a" * 64,
            lock_namespace_sha256="b" * 64,
        )

    controller._maintenance_lease = invalid_lease
    invalid_permit = _apply(controller, preview)
    assert invalid_permit["status"] == "REPAIR_APPLY_MAINTENANCE_PERMIT_INVALID"
    assert invalid_permit["write_executed"] is False
    assert target.read_bytes() == before


def test_apply_holds_maintenance_lease_for_the_complete_transaction(tmp_path) -> None:
    target = tmp_path / "lease-scope" / "trade_registry.json"
    events = []
    controller = _controller(target, apply_enabled=True)
    controller._maintenance_lease = lambda: _safe_maintenance_lease(events)
    controller._fault_injector = lambda step: events.append(step)
    preview = _preview(controller)

    applied = _apply(controller, preview)

    assert applied["status"] == "REPAIR_TRANSACTION_COMMITTED"
    assert events[0] == "maintenance_enter"
    assert events[-1] == "maintenance_exit"
    assert events.index("maintenance_enter") < events.index("AFTER_BACKUP")
    assert events.index("AFTER_REPLACE") < events.index("maintenance_exit")


def test_apply_reports_commit_truthfully_when_lease_release_fails(tmp_path) -> None:
    target = tmp_path / "lease-release-failure" / "trade_registry.json"
    controller = _controller(target, apply_enabled=True)

    @contextmanager
    def release_failure_lease():
        yield SimpleNamespace(
            state="QUIESCED",
            registered_writer_count=19,
            inflight_mutations=0,
            shared_lock_acquired=True,
            maintenance_epoch="a" * 64,
            lock_namespace_sha256="b" * 64,
        )
        raise RuntimeError("synthetic lease release failure")

    controller._maintenance_lease = release_failure_lease
    preview = _preview(controller)
    applied = _apply(controller, preview)

    assert applied["ok"] is False
    assert (
        applied["status"]
        == "REPAIR_APPLY_COMMITTED_MAINTENANCE_RELEASE_FAILED"
    )
    assert applied["write_executed"] is True
    assert applied["registry_write"] is True
    assert applied["maintenance_lease_release_confirmed"] is False
    repaired = json.loads(target.read_text(encoding="utf-8"))["closed_trades"][0]
    assert repaired["close_reason"] == "STOP"
    assert repaired["gross_r_multiple"] == -1.08850668


def test_failure_after_replace_rolls_back_exact_preimage(tmp_path) -> None:
    target = tmp_path / "rollback" / "trade_registry.json"
    before = json.dumps(_registry()).encode("utf-8")
    target.parent.mkdir(parents=True)
    target.write_bytes(before)

    def fail_after_replace(step: str) -> None:
        if step == "AFTER_REPLACE":
            raise RuntimeError("synthetic fault")

    controller = _controller(
        target,
        apply_enabled=True,
        fault_injector=fail_after_replace,
    )
    preview = _preview(controller)
    failed = _apply(controller, preview)
    assert failed["status"] == "REPAIR_TRANSACTION_FAILED_ROLLED_BACK"
    assert failed["rollback_attempted"] is True
    assert failed["rollback_confirmed"] is True
    assert failed["registry_write"] is False
    assert target.read_bytes() == before


def test_unknown_or_tampered_preview_is_denied(tmp_path) -> None:
    target = tmp_path / "tamper" / "trade_registry.json"
    controller = _controller(target, apply_enabled=True)
    before = target.read_bytes()
    denied = controller.apply(
        {"ack": operation.APPLY_ACK_V1, "preview_receipt_sha256": "a" * 64}
    )
    assert denied["status"] == "REPAIR_APPLY_PREVIEW_REQUIRED"
    assert denied["write_executed"] is False
    assert target.read_bytes() == before


def test_apply_requires_attested_config_and_integral_authorized_receipt(tmp_path) -> None:
    target = tmp_path / "attestation" / "trade_registry.json"
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps(_registry()), encoding="utf-8")

    configured_without_attestation = operation.ClosedIdentityRepairRuntimeOperationV1(
        registry_loader=lambda: json.loads(target.read_text(encoding="utf-8")),
        conflict_auditor=lambda: _audit_for(
            json.loads(target.read_text(encoding="utf-8"))
        ),
        registry_lock=lambda: threading.RLock(),
        trading_controls=_safe_controls,
        target_path=target,
        backup_root=target.parent / "c3_closed_identity_repair_backups",
        config=operation.ClosedIdentityRepairRuntimeConfigV1(apply_enabled=True),
    )
    snapshot = configured_without_attestation.snapshot()
    assert snapshot["apply_configured"] is True
    assert snapshot["apply_scope_attested"] is False
    assert snapshot["apply_enabled"] is False
    assert snapshot["default_off"] is True
    preview = _preview(configured_without_attestation)
    assert preview["preview_receipt"]["apply_allowed"] is False
    denied = _apply(configured_without_attestation, preview)
    assert denied["status"] == "REPAIR_APPLY_SCOPE_ATTESTATION_REQUIRED"
    assert denied["write_executed"] is False

    controller = _controller(target, apply_enabled=True)
    preview = _preview(controller)
    receipt_sha = preview["preview_receipt"]["preview_receipt_sha256"]
    controller._pending[receipt_sha]["receipt"]["changed_paths"] = [
        "closed_trades[0].unexpected"
    ]
    tampered = _apply(controller, preview)
    assert tampered["status"] == "REPAIR_APPLY_RECEIPT_INTEGRITY_FAILED"
    assert tampered["write_executed"] is False
    assert json.loads(target.read_text(encoding="utf-8")) == _registry()


def test_apply_rejects_receipt_that_was_issued_while_default_off(tmp_path) -> None:
    target = tmp_path / "unauthorized-receipt" / "trade_registry.json"
    controller = _controller(target, apply_enabled=True)
    preview = _preview(controller)
    receipt_sha = preview["preview_receipt"]["preview_receipt_sha256"]
    receipt = controller._pending[receipt_sha]["receipt"]
    receipt["apply_allowed"] = False
    receipt_without_sha = dict(receipt)
    receipt_without_sha.pop("preview_receipt_sha256")
    denied_receipt_sha = operation._stable_sha256(receipt_without_sha)
    receipt["preview_receipt_sha256"] = denied_receipt_sha
    controller._pending[denied_receipt_sha] = controller._pending.pop(receipt_sha)

    denied = controller.apply(
        {
            "ack": operation.APPLY_ACK_V1,
            "preview_receipt_sha256": denied_receipt_sha,
        }
    )
    assert denied["status"] == "REPAIR_APPLY_RECEIPT_NOT_AUTHORIZED"
    assert denied["write_executed"] is False
    assert json.loads(target.read_text(encoding="utf-8")) == _registry()


def test_preview_fails_closed_on_conflicting_gross_r_target(tmp_path) -> None:
    target = tmp_path / "gross-conflict" / "trade_registry.json"
    registry = _registry()
    registry["closed_trades"][0]["gross_r_multiple"] = 99.0
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps(registry), encoding="utf-8")
    controller = _controller(target, apply_enabled=False)
    before = target.read_bytes()

    preview = _preview(controller)

    assert preview["status"] == "REPAIR_PREVIEW_GROSS_R_TARGET_CONFLICT"
    assert preview["gross_r_target_path"] == "trade.gross_r_multiple"
    assert preview["write_executed"] is False
    assert target.read_bytes() == before


def test_preview_rejects_reversed_financial_semantics(tmp_path) -> None:
    target = tmp_path / "reversed-semantics" / "trade_registry.json"
    controller = _controller(target, apply_enabled=False)
    before = target.read_bytes()

    technical_reason = controller.preview(
        {
            "ack": operation.PREVIEW_ACK_V1,
            "selected_sources": {
                "close_reason": "trade.close_reason",
                "pnl_r": "trade.pnl_r",
            },
            "gross_r_source": "trade.r_multiple",
        }
    )
    assert technical_reason["status"] == "REPAIR_PREVIEW_CAUSAL_STOP_SOURCE_REQUIRED"

    gross_as_canonical = controller.preview(
        {
            "ack": operation.PREVIEW_ACK_V1,
            "selected_sources": {
                "close_reason": "trade.metadata.exit_reason",
                "pnl_r": "trade.r_multiple",
            },
            "gross_r_source": "trade.pnl_r",
        }
    )
    assert gross_as_canonical["status"] == "REPAIR_PREVIEW_CANONICAL_NET_R_SOURCE_REQUIRED"
    assert technical_reason["write_executed"] is False
    assert gross_as_canonical["write_executed"] is False
    assert target.read_bytes() == before


def test_main_wires_authenticated_post_only_route_and_default_off_apply() -> None:
    source = (Path(__file__).resolve().parents[1] / "main.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    routes = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            if not (
                isinstance(decorator.func, ast.Attribute)
                and decorator.func.attr == "route"
                and decorator.args
                and isinstance(decorator.args[0], ast.Constant)
            ):
                continue
            if decorator.args[0].value == "/traderegistry/closedidentity/repair":
                routes.append((node, decorator))
    assert len(routes) == 1
    route_node, decorator = routes[0]
    methods = next(
        keyword.value for keyword in decorator.keywords if keyword.arg == "methods"
    )
    assert isinstance(methods, ast.List)
    assert [item.value for item in methods.elts] == ["POST"]
    route_source = ast.get_source_segment(source, route_node)
    assert "_c3_closed_identity_repair_request_v1" in route_source
    assert "controller.preview" in route_source
    assert "controller.apply" in route_source
    assert '_ee_auth_resolver_v1_resolve' in source
    assert "ENABLE_C3_CLOSED_IDENTITY_REPAIR_APPLY" not in source
    assert "C3_CLOSED_IDENTITY_REPAIR_APPLY_SCOPE" not in source
    assert "ClosedIdentityRepairRuntimeConfigV1()" in source
    assert "C3_CLOSED_IDENTITY_REPAIR_RUNTIME_OPERATION_V1 =" in source
    builder = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_build_c3_closed_identity_repair_runtime_operation_v1"
    )
    builder_source = ast.get_source_segment(source, builder)
    assert "writer_coordination_status=" not in builder_source
    assert "maintenance_lease=" not in builder_source
