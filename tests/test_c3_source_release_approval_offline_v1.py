from __future__ import annotations

import base64
import hashlib
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import trade_registry_closed_identity_conflict_repair_runtime_seam_v1 as runtime_seam
import trade_registry_closed_identity_conflict_repair_runtime_source_release_approval_offline_v1 as approval


def _candidate(tmp_path: Path, *, signer_id: str = approval.APPROVED_SIGNER_ID_V1):
    source_hashes = {}
    for relative in runtime_seam._CONTROLLED_ACTIVATION_SOURCE_FILES:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        content = relative.encode("utf-8")
        path.write_bytes(content)
        source_hashes[relative] = hashlib.sha256(content).hexdigest()
    key = Ed25519PrivateKey.generate()  # Ephemeral synthetic test key only.
    public_key = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    manifest = {
        "approval_version": approval.APPROVAL_VERSION_V1,
        "signer_id": signer_id,
        "source_hashes": source_hashes,
    }
    manifest["signature_base64"] = base64.b64encode(
        key.sign(approval.source_release_approval_signing_payload_v1(manifest))
    ).decode("ascii")
    return manifest, public_key


def test_valid_candidate_signature_never_grants_activation(tmp_path: Path) -> None:
    manifest, public_key = _candidate(tmp_path)

    result = approval.verify_source_release_approval_offline_v1(
        tmp_path,
        manifest,
        candidate_public_key_raw=public_key,
    )

    assert result["ok"] is True
    assert result["signature_valid_for_candidate_key"] is True
    assert result["source_hashes_match"] is True
    assert result["production_trust_root_bound"] is False
    assert result["production_ready"] is False
    assert result["activation_allowed"] is False
    assert result["live_allowed"] is False
    assert result["network_accessed"] is False
    assert result["broker_called"] is False


def test_missing_key_wrong_key_and_wrong_signer_fail_closed(tmp_path: Path) -> None:
    manifest, public_key = _candidate(tmp_path)
    verifier = approval.verify_source_release_approval_offline_v1
    assert verifier(tmp_path, manifest)["ok"] is False
    other_signer_manifest, other_signer_key = _candidate(
        tmp_path, signer_id="another-reviewer"
    )
    assert verifier(
        tmp_path, other_signer_manifest, candidate_public_key_raw=other_signer_key
    )["ok"] is False
    wrong_key = Ed25519PrivateKey.generate().public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    assert verifier(
        tmp_path,
        manifest,
        candidate_public_key_raw=wrong_key,
    )["ok"] is False


def test_tampered_manifest_or_source_fails_closed(tmp_path: Path) -> None:
    manifest, public_key = _candidate(tmp_path)
    verifier = approval.verify_source_release_approval_offline_v1
    manifest["source_hashes"]["main.py"] = "0" * 64
    assert verifier(
        tmp_path,
        manifest,
        candidate_public_key_raw=public_key,
    )["ok"] is False
    manifest, public_key = _candidate(tmp_path)
    (tmp_path / "main.py").write_bytes(b"changed-after-signing")
    result = verifier(
        tmp_path,
        manifest,
        candidate_public_key_raw=public_key,
    )
    assert result["signature_valid_for_candidate_key"] is True
    assert result["source_hashes_match"] is False
    assert result["ok"] is False
