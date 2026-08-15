"""Explicit, shadow-only CLI for Trade Evidence Identity Offset Index V1.

Nothing is opened or created at import time.  ``main`` requires explicit
source, index, and source-id arguments; it never discovers ``/data`` or starts
an application/runtime process.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Sequence


def _load_index_module():
    repo_root = Path(__file__).resolve().parents[1]
    root_text = os.fspath(repo_root)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)
    import trade_evidence_identity_offset_index_v1 as index_module

    return index_module


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def _identity(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("identity must use TYPE=VALUE")
    identity_type, identity_value = value.split("=", 1)
    if not identity_type.strip() or not identity_value.strip():
        raise argparse.ArgumentTypeError("identity type and value are required")
    return identity_type.strip(), identity_value.strip()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Manual Phase A shadow builder/revalidator and READY append catch-up; "
            "no productive reader integration."
        ),
    )
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--index", required=True, type=Path)
    parser.add_argument(
        "--source-id",
        required=True,
        choices=("history_manager", "timeline"),
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--build", action="store_true")
    mode.add_argument("--resume", action="store_true")
    mode.add_argument("--catch-up", action="store_true")
    mode.add_argument("--validate", action="store_true")
    mode.add_argument("--deep-validate", action="store_true")
    mode.add_argument("--verify-shadow", action="store_true")
    parser.add_argument("--staging", type=Path)
    parser.add_argument("--identity", action="append", type=_identity, default=[])
    parser.add_argument("--sample-limit", type=_positive_int, default=100)
    parser.add_argument("--report-json", type=Path)
    parser.add_argument("--block-bytes", type=_positive_int)
    parser.add_argument("--segment-target-bytes", type=_positive_int)
    parser.add_argument("--batch-bytes", type=_positive_int)
    parser.add_argument("--batch-lines", type=_positive_int)
    parser.add_argument("--max-line-bytes", type=_positive_int)
    parser.add_argument("--anchor-bytes", type=_positive_int)
    return parser


def _build_config(args: argparse.Namespace, index_module: Any):
    defaults = index_module.BuildConfig()
    return index_module.BuildConfig(
        block_bytes=args.block_bytes or defaults.block_bytes,
        segment_target_bytes=args.segment_target_bytes or defaults.segment_target_bytes,
        batch_bytes=args.batch_bytes or defaults.batch_bytes,
        batch_lines=args.batch_lines or defaults.batch_lines,
        max_line_bytes=args.max_line_bytes or defaults.max_line_bytes,
        anchor_bytes=args.anchor_bytes or defaults.anchor_bytes,
        busy_timeout_ms=defaults.busy_timeout_ms,
    )


def _write_report(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    index_module = _load_index_module()
    try:
        if args.build or args.resume:
            report = index_module.build_index(
                args.source,
                args.index,
                args.source_id,
                resume=bool(args.resume),
                staging_path=args.staging,
                config=_build_config(args, index_module),
            )
            payload = {"mode": "resume" if args.resume else "build", **report.to_dict()}
            exit_code = 0
        elif args.catch_up:
            if args.staging is not None:
                raise index_module.IndexBuildError(
                    "--catch-up operates only on the published READY index and does not accept --staging"
                )
            if any(
                value is not None
                for value in (
                    args.block_bytes,
                    args.segment_target_bytes,
                    args.batch_bytes,
                    args.batch_lines,
                    args.max_line_bytes,
                    args.anchor_bytes,
                )
            ):
                raise index_module.IndexBuildError(
                    "--catch-up uses the READY index stored config and does not accept build overrides"
                )
            report = index_module.catch_up_index(
                args.source,
                args.index,
                args.source_id,
            )
            payload = report.to_dict()
            exit_code = 0
        elif args.validate or args.deep_validate:
            result = index_module.validate_index(
                args.source,
                args.index,
                args.source_id,
                deep=bool(args.deep_validate),
            )
            payload = {"mode": "deep-validate" if args.deep_validate else "validate", **result.to_dict()}
            exit_code = 0 if result.status in {
                index_module.INDEX_COMPLETE_FOR_SNAPSHOT,
                index_module.INDEX_PARTIAL,
            } else 1
        else:
            validation = index_module.validate_index(
                args.source,
                args.index,
                args.source_id,
                deep=False,
            )
            if validation.status not in {
                index_module.INDEX_COMPLETE_FOR_SNAPSHOT,
                index_module.INDEX_PARTIAL,
            }:
                raise index_module.IndexValidationError(
                    f"index is not eligible for shadow verification: {validation.status}"
                )
            result = index_module.verify_shadow(
                args.source,
                args.index,
                args.identity or None,
                sample_limit=args.sample_limit,
            )
            payload = {
                "mode": "verify-shadow",
                "index_validation": validation.to_dict(),
                **result.to_dict(),
            }
            exit_code = 0 if result.ok else 1
        if args.report_json is not None:
            _write_report(args.report_json, payload)
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return exit_code
    except Exception as exc:
        payload = {
            "ok": False,
            "error_type": type(exc).__name__,
            "message": str(exc),
        }
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
