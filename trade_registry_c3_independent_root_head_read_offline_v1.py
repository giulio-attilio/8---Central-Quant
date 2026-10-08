"""Default-off, read-only candidate for an independent C3 root head.

The DynamoDB client is injected. Importing or constructing this adapter never
creates credentials or performs I/O. A matching head is evidence for an offline
test only: this module does not admit startup, recovery, trading, or LIVE.
"""

from __future__ import annotations

import hmac
import re
from dataclasses import dataclass, field
from typing import Any

from trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_source_ports_contract_v2 import (
    startup_recovery_evidence_source_object_identity_sha256_v2,
)


INDEPENDENT_ROOT_HEAD_READ_SCOPE_V1 = "C3_INDEPENDENT_ROOT_HEAD_READ_OFFLINE_V1"
ROOT_HEAD_SCHEMA_V1 = "C3_ROOT_HEAD_V1"
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_TABLE_ARN_RE = re.compile(
    r"^arn:aws:dynamodb:[a-z0-9-]+:[0-9]{12}:table/[A-Za-z0-9_.-]{3,255}$"
)
_ITEM_FIELDS = frozenset(
    {
        "schema_version",
        "root_identity_sha256",
        "storage_binding_sha256",
        "key_id_sha256",
        "key_epoch",
        "head_attestation_sha256",
        "revoked",
    }
)


def _sha(value: Any) -> bool:
    return type(value) is str and _SHA_RE.fullmatch(value) is not None


def _attribute(value: Any, kind: str) -> Any:
    if type(value) is not dict or set(value) != {kind}:
        raise ValueError("ROOT_HEAD_ATTRIBUTE_INVALID")
    result = value[kind]
    if kind in ("S", "N") and type(result) is not str:
        raise ValueError("ROOT_HEAD_ATTRIBUTE_INVALID")
    if kind == "BOOL" and type(result) is not bool:
        raise ValueError("ROOT_HEAD_ATTRIBUTE_INVALID")
    return result


@dataclass(frozen=True)
class IndependentRootHeadReadConfigV1:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    table_arn: str | None = field(default=None, repr=False)
    root_identity_sha256: str | None = field(default=None, repr=False)
    expected_client_object_identity_sha256: str | None = field(
        default=None, repr=False
    )


class IndependentRootHeadReaderV1:
    """Check one pinned DynamoDB item using a strongly consistent read."""

    def __init__(
        self, config: IndependentRootHeadReadConfigV1 | None = None, *, client: Any = None
    ) -> None:
        self._config = config or IndependentRootHeadReadConfigV1()
        self._client = client

    def __repr__(self) -> str:
        return "IndependentRootHeadReaderV1(<protected>)"

    @staticmethod
    def _result(reason: str, *, matched: bool = False, read_attempted: bool = False) -> dict[str, Any]:
        return {
            "head_matches": matched,
            "reason": reason,
            "external_read_attempted": read_attempted,
            "production_ready": False,
            "runtime_integrated": False,
            "admission_allowed": False,
            "live_allowed": False,
        }

    def check_head(
        self,
        *,
        storage_binding_sha256: str,
        key_id_sha256: str,
        key_epoch: int,
        attestation_sha256: str,
    ) -> dict[str, Any]:
        config = self._config
        if config.enabled is not True:
            return self._result("ROOT_HEAD_READER_DEFAULT_OFF")
        if not (
            config.scope_attestation == INDEPENDENT_ROOT_HEAD_READ_SCOPE_V1
            and type(config.table_arn) is str
            and _TABLE_ARN_RE.fullmatch(config.table_arn) is not None
            and _sha(config.root_identity_sha256)
            and _sha(config.expected_client_object_identity_sha256)
            and all(_sha(value) for value in (
                storage_binding_sha256, key_id_sha256, attestation_sha256
            ))
            and type(key_epoch) is int
            and 1 <= key_epoch <= 2**53 - 1
            and self._client is not None
        ):
            return self._result("ROOT_HEAD_READER_INPUT_INVALID")
        try:
            actual_client_identity = (
                startup_recovery_evidence_source_object_identity_sha256_v2(
                    self._client
                )
            )
        except Exception:
            return self._result("ROOT_HEAD_READER_CLIENT_INVALID")
        if not hmac.compare_digest(
            actual_client_identity, config.expected_client_object_identity_sha256
        ):
            return self._result("ROOT_HEAD_READER_CLIENT_MISMATCH")
        try:
            read = getattr(self._client, "get_item", None)
        except Exception:
            return self._result("ROOT_HEAD_READER_CLIENT_INVALID")
        if not callable(read):
            return self._result("ROOT_HEAD_READER_CLIENT_INVALID")
        try:
            response = read(
                TableName=config.table_arn,
                Key={"root_identity_sha256": {"S": config.root_identity_sha256}},
                ConsistentRead=True,
                ReturnConsumedCapacity="NONE",
            )
        except Exception:
            return self._result("ROOT_HEAD_READ_FAILED", read_attempted=True)
        try:
            if type(response) is not dict or type(response.get("Item")) is not dict:
                raise ValueError("ROOT_HEAD_MISSING")
            item = response["Item"]
            if set(item) != _ITEM_FIELDS:
                raise ValueError("ROOT_HEAD_FIELDS_INVALID")
            schema = _attribute(item["schema_version"], "S")
            root = _attribute(item["root_identity_sha256"], "S")
            storage = _attribute(item["storage_binding_sha256"], "S")
            key = _attribute(item["key_id_sha256"], "S")
            epoch_text = _attribute(item["key_epoch"], "N")
            head = _attribute(item["head_attestation_sha256"], "S")
            revoked = _attribute(item["revoked"], "BOOL")
            if not (
                schema == ROOT_HEAD_SCHEMA_V1
                and all(_sha(value) for value in (root, storage, key, head))
                and epoch_text == str(key_epoch)
                and revoked is False
                and hmac.compare_digest(root, config.root_identity_sha256)
                and hmac.compare_digest(storage, storage_binding_sha256)
                and hmac.compare_digest(key, key_id_sha256)
                and hmac.compare_digest(head, attestation_sha256)
            ):
                raise ValueError("ROOT_HEAD_MISMATCH")
        except Exception:
            return self._result("ROOT_HEAD_MISMATCH", read_attempted=True)
        return self._result("ROOT_HEAD_MATCHED_OFFLINE", matched=True, read_attempted=True)


__all__ = [
    "INDEPENDENT_ROOT_HEAD_READ_SCOPE_V1",
    "ROOT_HEAD_SCHEMA_V1",
    "IndependentRootHeadReadConfigV1",
    "IndependentRootHeadReaderV1",
]
