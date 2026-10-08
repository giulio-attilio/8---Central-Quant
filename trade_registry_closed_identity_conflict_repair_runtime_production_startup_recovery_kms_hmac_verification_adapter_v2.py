"""Default-off AWS KMS VerifyMac adapter for the C3 root HMAC boundary.

The caller supplies a preconfigured KMS client and an exact key ARN. This
module never creates a client, discovers credentials, or makes a call at import
or construction time. Runtime wiring and key provisioning are out of scope.
"""

from __future__ import annotations

import hashlib
import hmac
import re
from dataclasses import dataclass, field
from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_persistent_authority_production_adapters_v2 as adapters_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_source_ports_contract_v2 as identity_v2


_KEY_ARN_RE = re.compile(
    r"^arn:aws:kms:[a-z0-9-]+:[0-9]{12}:key/"
    r"(?:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
    r"|mrk-[0-9a-f]{32})$"
)
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_SHA_BYTES_RE = re.compile(rb"^[0-9a-f]{64}$")
_MAC_ALGORITHM = "HMAC_SHA_256"


def kms_root_hmac_key_id_sha256_v2(key_arn: str) -> str:
    """Bind an attestation key ID to an immutable, full KMS key ARN."""
    if type(key_arn) is not str or _KEY_ARN_RE.fullmatch(key_arn) is None:
        raise ValueError("C3_KMS_ROOT_KEY_ARN_INVALID")
    return hashlib.sha256(key_arn.encode("ascii")).hexdigest()


@dataclass(frozen=True)
class KmsRootHmacVerificationConfigV2:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    key_arn: str | None = field(default=None, repr=False)
    expected_client_object_identity_sha256: str | None = field(
        default=None, repr=False
    )


class KmsRootHmacVerificationProviderV2:
    """Verify only against one pinned KMS HMAC key; never fall back locally."""

    def __init__(
        self, config: KmsRootHmacVerificationConfigV2 | None = None, *, client: Any = None
    ) -> None:
        self._config = config or KmsRootHmacVerificationConfigV2()
        self._client = client

    def __repr__(self) -> str:
        return "KmsRootHmacVerificationProviderV2(<protected>)"

    def verify_root_hmac_v2(
        self, *, key_id_sha256: str, message: bytes, mac: bytes, mac_algorithm: str
    ) -> bool:
        config = self._config
        if not (
            config.enabled is True
            and config.scope_attestation
            == adapters_v2.PRODUCTION_AUTHORITY_ADAPTERS_EXPLICIT_DEPENDENCY_SCOPE_V2
            and type(config.expected_client_object_identity_sha256) is str
            and _SHA_RE.fullmatch(config.expected_client_object_identity_sha256)
            and self._client is not None
        ):
            return False
        try:
            expected_key_id = kms_root_hmac_key_id_sha256_v2(config.key_arn)
            client_identity = (
                identity_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
                    self._client
                )
            )
        except Exception:
            return False
        if not (
            type(key_id_sha256) is str
            and _SHA_RE.fullmatch(key_id_sha256)
            and hmac.compare_digest(key_id_sha256, expected_key_id)
            and hmac.compare_digest(
                client_identity, config.expected_client_object_identity_sha256
            )
            and type(message) is bytes
            and _SHA_BYTES_RE.fullmatch(message)
            and type(mac) is bytes
            and len(mac) == 32
            and type(mac_algorithm) is str
            and mac_algorithm == _MAC_ALGORITHM
        ):
            return False
        try:
            verify = getattr(self._client, "verify_mac", None)
            if not callable(verify):
                return False
            response = verify(
                KeyId=config.key_arn,
                Message=message,
                Mac=mac,
                MacAlgorithm=_MAC_ALGORITHM,
            )
            return bool(
                type(response) is dict
                and response.get("MacValid") is True
                and type(response.get("KeyId")) is str
                and response.get("KeyId") == config.key_arn
                and type(response.get("MacAlgorithm")) is str
                and response.get("MacAlgorithm") == _MAC_ALGORITHM
            )
        except Exception:
            return False


__all__ = [
    "KmsRootHmacVerificationConfigV2",
    "KmsRootHmacVerificationProviderV2",
    "kms_root_hmac_key_id_sha256_v2",
]
