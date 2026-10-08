"""Offline signature check for a proposed C3 source-release approval.

This module pins the approver ID but has no production trust root, signing key,
activation hook, Registry access or network access. A valid signature is evidence
only for the injected candidate public key; it never grants runtime or LIVE authority.
"""

from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_seam_v1 as runtime_seam


APPROVAL_VERSION_V1 = "C3_SOURCE_RELEASE_APPROVAL_OFFLINE_V1"
APPROVED_SIGNER_ID_V1 = "giulio-release-approver"
_SIGNING_DOMAIN_V1 = b"C3-SOURCE-RELEASE-APPROVAL-OFFLINE-V1\x00"
_MANIFEST_KEYS_V1 = frozenset(
    {"approval_version", "signer_id", "source_hashes", "signature_base64"}
)


def source_release_approval_signing_payload_v1(manifest: Mapping[str, Any]) -> bytes:
    """Encode the exact signed fields with domain separation."""

    if not isinstance(manifest, Mapping):
        raise TypeError("manifest must be a mapping")
    payload = {key: value for key, value in manifest.items() if key != "signature_base64"}
    return _SIGNING_DOMAIN_V1 + json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def verify_source_release_approval_offline_v1(
    repository_root: str | Path,
    manifest: Mapping[str, Any],
    *,
    candidate_public_key_raw: bytes | None = None,
) -> dict[str, Any]:
    """Check one candidate signature and local bytes; never assert trust."""

    result: dict[str, Any] = {
        "ok": False,
        "status": "C3_SOURCE_RELEASE_APPROVAL_OFFLINE_BLOCKED",
        "signature_valid_for_candidate_key": False,
        "source_hashes_match": False,
        "production_trust_root_bound": False,
        "production_ready": False,
        "activation_allowed": False,
        "runtime_integrated": False,
        "live_allowed": False,
        "read_only": True,
        "network_accessed": False,
        "broker_called": False,
        "no_order_sent": True,
    }
    if (
        not isinstance(manifest, Mapping)
        or set(manifest) != _MANIFEST_KEYS_V1
        or manifest.get("approval_version") != APPROVAL_VERSION_V1
        or manifest.get("signer_id") != APPROVED_SIGNER_ID_V1
        or not isinstance(candidate_public_key_raw, bytes)
        or len(candidate_public_key_raw) != 32
        or not isinstance(manifest.get("signature_base64"), str)
    ):
        return result
    try:
        from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError:
        return result
    try:
        signature = base64.b64decode(manifest["signature_base64"], validate=True)
        if (
            len(signature) != 64
            or base64.b64encode(signature).decode("ascii")
            != manifest["signature_base64"]
        ):
            return result
        payload = source_release_approval_signing_payload_v1(manifest)
        Ed25519PublicKey.from_public_bytes(candidate_public_key_raw).verify(
            signature, payload
        )
    except (
        binascii.Error,
        InvalidSignature,
        UnsupportedAlgorithm,
        TypeError,
        ValueError,
    ):
        return result
    result["signature_valid_for_candidate_key"] = True
    source_check = runtime_seam.verify_controlled_activation_source_hashes_read_only_v1(
        repository_root, manifest.get("source_hashes")
    )
    if source_check["ok"] is not True:
        return result
    result["source_hashes_match"] = True
    result["ok"] = True
    result["status"] = "C3_SOURCE_RELEASE_APPROVAL_VERIFIED_OFFLINE_TRUST_UNBOUND"
    return result


__all__ = [
    "APPROVAL_VERSION_V1",
    "APPROVED_SIGNER_ID_V1",
    "source_release_approval_signing_payload_v1",
    "verify_source_release_approval_offline_v1",
]
