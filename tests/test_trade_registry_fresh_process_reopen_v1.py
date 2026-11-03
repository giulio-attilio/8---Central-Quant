"""A nonempty synthetic Registry must survive a fresh local process read."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NETWORK_BLOCK = r"""
import socket

def _deny_network(*_args, **_kwargs):
    raise AssertionError("network access is forbidden in this local persistence test")

socket.create_connection = _deny_network
socket.getaddrinfo = _deny_network
socket.socket.connect = _deny_network
"""


def _run_child(tmp_path: Path, body: str) -> dict:
    env = os.environ.copy()
    env["CENTRAL_DATA_DIR"] = str(tmp_path)
    env["TRADE_REGISTRY_FILE"] = str(tmp_path / "trade_registry.json")
    result = subprocess.run(
        [sys.executable, "-c", NETWORK_BLOCK + "\n" + body],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip())


def test_nonempty_registry_reopens_in_fresh_process_without_read_mutation(tmp_path):
    seeded = _run_child(
        tmp_path,
        r"""
import json
import trade_registry

trade_registry.save_registry({
    "ok": True,
    "version": trade_registry.VERSION,
    "open_trades": {
        "SYNTHETIC-OPEN": {
            "trade_id": "SYNTHETIC-OPEN", "status": "OPEN", "bot": "TEST",
            "setup": "REOPEN", "symbol": "BTCUSDT", "side": "LONG", "entry": 1,
            "qty": 1, "source": "offline-reopen-test"
        }
    },
    "closed_trades": [{
        "trade_id": "SYNTHETIC-CLOSED", "status": "CLOSED", "bot": "TEST",
        "setup": "REOPEN", "symbol": "ETHUSDT", "side": "SHORT", "entry": 2,
        "exit": 3, "qty": 1, "source": "offline-reopen-test"
    }]
})
print(json.dumps({"seeded": True}))
""",
    )
    assert seeded == {"seeded": True}

    registry_path = tmp_path / "trade_registry.json"
    before = registry_path.read_bytes()
    before_sha256 = hashlib.sha256(before).hexdigest()

    reopened = _run_child(
        tmp_path,
        r"""
import json
import trade_registry

registry = trade_registry.load_registry()
print(json.dumps({
    "open_count": len(registry.get("open_trades", {})),
    "closed_count": len(registry.get("closed_trades", [])),
    "open_ids": sorted(registry.get("open_trades", {})),
}))
""",
    )

    after = registry_path.read_bytes()
    assert reopened == {
        "open_count": 1,
        "closed_count": 1,
        "open_ids": ["SYNTHETIC-OPEN"],
    }
    assert hashlib.sha256(after).hexdigest() == before_sha256
    assert after == before
