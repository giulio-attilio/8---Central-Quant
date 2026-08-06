"""Pure Falcon execution-intent identity contract.

The module is deliberately limited to deterministic identity construction:
no environment, network, persistence, broker, or runtime imports are used.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


FALCON_EXECUTION_INTENT_IDENTITY_VERSION = "FALCON-EXECUTION-INTENT-IDENTITY-V1"


def _text(value: Any) -> str:
    return str(value or "").strip()


def derive_falcon_execution_intent_idempotency_key(
    *,
    signal_id: Any,
    lifecycle_id: Any,
    decision_id: Any,
    client_order_attempt_id: Any,
    client_order_attempt_sequence: Any,
) -> str:
    """Derive the sole Falcon intent key from its immutable entry identity."""
    material = {
        "version": FALCON_EXECUTION_INTENT_IDENTITY_VERSION,
        "signal_id": _text(signal_id),
        "lifecycle_id": _text(lifecycle_id),
        "decision_id": _text(decision_id),
        "client_order_attempt_id": _text(client_order_attempt_id),
        "client_order_attempt_sequence": client_order_attempt_sequence,
    }
    encoded = json.dumps(
        material, ensure_ascii=True, sort_keys=True, separators=(",", ":"), default=str
    )
    return "FALCON-ENGINE-INTENT:" + hashlib.sha256(
        encoded.encode("utf-8")
    ).hexdigest().upper()[:32]
