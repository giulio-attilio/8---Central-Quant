import json
import os
import sys
from types import ModuleType
from pathlib import Path

import paper_registry_source_capture
from paper_registry_source_capture import capture_paper_registry_sources


_KEYS = (
    "cobra:positions",
    "donkey:positions",
    "falcon:positions",
    "memepro:positions",
    "smartpredator:positions",
    "trendpro:positions",
    "turtle_pro:positions",
)
_PRIVATE_ID = "private-lifecycle-capture-test"
_PRIVATE_TOKEN = "private-token-capture-test"


def _registry(path):
    payload = {
        "open_trades": {
            "logical-open-key": {
                "bot": "TURTLE",
                "lifecycle_id": _PRIVATE_ID,
                "registry_mode": "PAPER",
                "execution_mode": "PAPER",
            },
        },
        "closed_trades": [],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _source_values(*, turtle=None):
    values = [json.dumps({}) for _ in _KEYS]
    if turtle is not None:
        values[-1] = json.dumps(turtle)
    return values


class FakeRedis:
    def __init__(self, values=None, error=None):
        self.values = list(values if values is not None else _source_values())
        self.error = error
        self.calls = []

    def mget(self, *keys):
        self.calls.append(keys)
        if self.error is not None:
            raise RuntimeError(self.error)
        return self.values


def test_capture_uses_one_mget_and_returns_only_sanitized_review_counts(tmp_path):
    registry = _registry(tmp_path / "trade_registry.json")
    redis = FakeRedis(values=_source_values(turtle={
        "position-a": {
            "bot": "TURTLE",
            "lifecycle_id": _PRIVATE_ID,
            "execution_mode": "PAPER",
        },
    }))
    before = registry.read_bytes()

    report = capture_paper_registry_sources(redis_client=redis, registry_path=registry)
    encoded = json.dumps(report, sort_keys=True)

    assert len(redis.calls) == 1
    assert redis.calls[0] == _KEYS
    assert report["ok"] is True
    assert report["status"] == "PREVIEW_COMPLETE_NOT_MIGRATABLE"
    assert report["registry_status_counts"] == {"STRONG_IDENTITY_MATCH_REVIEW": 1}
    assert report["registry_mode_status_counts"] == {"PAPER_CONFIRMED_BY_BOTH_SNAPSHOTS": 1}
    assert report["source_reconciliation_counts"]["unique_strong_match_open"] == 1
    assert report["source_reconciliation_counts"]["orphan_no_registry_candidate"] == 0
    assert report["all_rows_ineligible_for_import"] is True
    assert report["writes_performed"] is False
    assert report["cross_store_atomic_snapshot"] is False
    assert _PRIVATE_ID not in encoded
    assert _PRIVATE_TOKEN not in encoded
    assert registry.read_bytes() == before


def test_capture_omits_arbitrary_source_status_and_mode_values(tmp_path):
    registry = _registry(tmp_path / "trade_registry.json")
    private_status = "private-status-value-must-not-escape"
    private_mode = "private-execution-mode-must-not-escape"
    redis = FakeRedis(values=_source_values(turtle={
        "position-a": {
            "bot": "TURTLE",
            "lifecycle_id": _PRIVATE_ID,
            "status": private_status,
            "execution_mode": private_mode,
        },
    }))

    report = capture_paper_registry_sources(redis_client=redis, registry_path=registry)
    encoded = json.dumps(report, sort_keys=True)
    diagnostics = report["source_diagnostics"]["by_bot"]["TURTLE"]

    assert report["ok"] is True
    assert diagnostics["record_count"] == 1
    assert diagnostics["identity_field_presence_counts"] == {"lifecycle_id": 1}
    assert "status_counts" not in diagnostics
    assert "execution_mode_counts" not in diagnostics
    assert private_status not in encoded
    assert private_mode not in encoded
    assert _PRIVATE_ID not in encoded


def test_capture_buckets_arbitrary_registry_mode_claim_without_echoing_value(tmp_path):
    registry = _registry(tmp_path / "trade_registry.json")
    private_mode = "private-registry-mode-must-not-escape"
    payload = json.loads(registry.read_text(encoding="utf-8"))
    payload["open_trades"]["logical-open-key"]["registry_mode"] = private_mode
    registry.write_text(json.dumps(payload), encoding="utf-8")
    redis = FakeRedis(values=_source_values(turtle={
        "position-a": {
            "bot": "TURTLE",
            "lifecycle_id": _PRIVATE_ID,
            "execution_mode": "PAPER",
        },
    }))

    report = capture_paper_registry_sources(redis_client=redis, registry_path=registry)
    encoded = json.dumps(report, sort_keys=True)

    assert report["registry_mode_claim_counts"] == {"INVALID": 1}
    assert private_mode not in encoded
    assert _PRIVATE_ID not in encoded


def test_any_missing_key_blocks_all_registry_matching(tmp_path):
    registry = _registry(tmp_path / "trade_registry.json")
    values = _source_values(turtle={"position-a": {"lifecycle_id": _PRIVATE_ID}})
    values[-1] = None
    redis = FakeRedis(values=values)

    report = capture_paper_registry_sources(redis_client=redis, registry_path=registry)

    assert report["ok"] is False
    assert report["status"] == "SOURCE_SNAPSHOT_INCOMPLETE"
    assert report["source_status_by_bot"]["TURTLE"] == "KEY_MISSING"
    assert report["registry_status_counts"] == {"SOURCE_SNAPSHOT_INCOMPLETE": 1}
    assert report["all_rows_ineligible_for_import"] is True
    assert report["writes_performed"] is False


def test_invalid_json_is_sanitized_and_does_not_match(tmp_path):
    registry = _registry(tmp_path / "trade_registry.json")
    values = _source_values(turtle={"position-a": {"lifecycle_id": _PRIVATE_ID}})
    values[-1] = "INVALID-BODY-MUST-NOT-ESCAPE"
    redis = FakeRedis(values=values)

    report = capture_paper_registry_sources(redis_client=redis, registry_path=registry)

    assert report["ok"] is False
    assert report["source_status_by_bot"]["TURTLE"] == "INVALID_JSON"
    assert report["registry_status_counts"] == {"SOURCE_SNAPSHOT_INCOMPLETE": 1}
    assert "INVALID-BODY-MUST-NOT-ESCAPE" not in json.dumps(report)


def test_upstash_failure_message_and_token_are_not_returned(tmp_path):
    registry = _registry(tmp_path / "trade_registry.json")
    redis = FakeRedis(error=f"failed with {_PRIVATE_TOKEN}")

    report = capture_paper_registry_sources(redis_client=redis, registry_path=registry)

    assert report["status"] == "SOURCE_SNAPSHOT_INCOMPLETE"
    assert set(report["source_status_by_bot"].values()) == {"READ_FAILED"}
    assert _PRIVATE_TOKEN not in json.dumps(report)
    assert report["writes_performed"] is False


def test_missing_registry_stops_before_upstash_read(tmp_path):
    redis = FakeRedis()

    report = capture_paper_registry_sources(
        redis_client=redis,
        registry_path=tmp_path / "absent-registry.json",
    )

    assert report["ok"] is False
    assert report["status"] == "REGISTRY_FILE_MISSING"
    assert redis.calls == []
    assert report["writes_performed"] is False


def test_default_registry_requires_verified_persistent_mount(monkeypatch):
    monkeypatch.delenv("CENTRAL_DATA_DIR", raising=False)
    monkeypatch.delenv("TRADE_REGISTRY_FILE", raising=False)
    monkeypatch.setenv("DATA_DIR", "/data")
    monkeypatch.setattr(
        paper_registry_source_capture,
        "paper_data_mount_verified",
        lambda *_args, **_kwargs: False,
    )
    redis = FakeRedis()

    report = capture_paper_registry_sources(redis_client=redis)

    assert report["ok"] is False
    assert report["status"] == "DATA_MOUNT_NOT_VERIFIED"
    assert redis.calls == []


def test_render_rejects_explicit_ephemeral_registry_before_upstash_read(
    monkeypatch, tmp_path
):
    registry = _registry(tmp_path / "trade_registry.json")
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.delenv("CENTRAL_DATA_DIR", raising=False)
    monkeypatch.delenv("TRADE_REGISTRY_FILE", raising=False)
    monkeypatch.setenv("DATA_DIR", "/data")
    monkeypatch.setattr(
        paper_registry_source_capture,
        "paper_data_mount_verified",
        lambda path, **_kwargs: Path(path).as_posix().startswith("/data/"),
    )
    redis = FakeRedis()

    report = capture_paper_registry_sources(redis_client=redis, registry_path=registry)

    assert report["ok"] is False
    assert report["status"] == "REGISTRY_OUTSIDE_DATA_DIR"
    assert redis.calls == []
    assert report["writes_performed"] is False


def test_render_rejects_configured_non_mount_registry_directory(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.delenv("TRADE_REGISTRY_FILE", raising=False)
    monkeypatch.setenv("CENTRAL_DATA_DIR", str(tmp_path / "ephemeral-data"))
    monkeypatch.delenv("DATA_DIR", raising=False)
    monkeypatch.setattr(
        paper_registry_source_capture,
        "paper_data_mount_verified",
        lambda path, **_kwargs: Path(path).as_posix().startswith("/data/"),
    )
    redis = FakeRedis()

    report = capture_paper_registry_sources(redis_client=redis)

    assert report["ok"] is False
    assert report["status"] == "DATA_MOUNT_NOT_VERIFIED"
    assert redis.calls == []


def test_registry_outside_configured_data_dir_is_rejected_before_upstash(monkeypatch):
    monkeypatch.delenv("CENTRAL_DATA_DIR", raising=False)
    monkeypatch.delenv("TRADE_REGISTRY_FILE", raising=False)
    monkeypatch.setenv("DATA_DIR", "/data")
    monkeypatch.setenv("TRADE_REGISTRY_FILE", "/opt/registry.json")
    redis = FakeRedis()

    report = capture_paper_registry_sources(redis_client=redis)

    assert report["ok"] is False
    assert report["status"] == "REGISTRY_OUTSIDE_DATA_DIR"
    assert redis.calls == []


def test_missing_upstash_config_stops_before_client_import(monkeypatch, tmp_path):
    registry = _registry(tmp_path / "trade_registry.json")
    monkeypatch.setenv("UPSTASH_REDIS_REST_URL", "https://redis.example.invalid")
    monkeypatch.setenv("UPSTASH_REDIS_REST_TOKEN", _PRIVATE_TOKEN)
    monkeypatch.delenv("UPSTASH_REDIS_REST_READONLY_TOKEN", raising=False)
    fake_sdk = ModuleType("upstash_redis")
    fake_sdk.Redis = lambda **_kwargs: (_ for _ in ()).throw(AssertionError("client must not be constructed"))
    monkeypatch.setitem(sys.modules, "upstash_redis", fake_sdk)

    report = capture_paper_registry_sources(registry_path=registry)

    assert report["ok"] is False
    assert report["status"] == "UPSTASH_READ_ONLY_CONFIG_MISSING"
    assert report["writes_performed"] is False


def test_cli_hidden_readonly_prompt_uses_one_mget_and_does_not_echo_token(
    monkeypatch, tmp_path, capsys
):
    registry = _registry(tmp_path / "trade_registry.json")
    before = registry.read_bytes()
    captured = {}

    class FakeRestRedis:
        def __init__(self, *, url, token):
            captured["url"] = url
            captured["token"] = token
            self.calls = []
            captured["client"] = self

        def mget(self, *keys):
            self.calls.append(keys)
            return _source_values()

    monkeypatch.setenv("UPSTASH_REDIS_REST_URL", "https://redis.example.invalid")
    monkeypatch.delenv("UPSTASH_REDIS_REST_TOKEN", raising=False)
    monkeypatch.delenv("UPSTASH_REDIS_REST_READONLY_TOKEN", raising=False)
    monkeypatch.setitem(sys.modules, "upstash_redis", ModuleType("upstash_redis"))
    sys.modules["upstash_redis"].Redis = FakeRestRedis
    monkeypatch.setattr(
        paper_registry_source_capture.getpass,
        "getpass",
        lambda _prompt: _PRIVATE_TOKEN,
    )

    result = paper_registry_source_capture.main([
        "--read-upstash",
        "--prompt-readonly-token",
        "--registry-file",
        str(registry),
    ])

    output = capsys.readouterr().out
    report = json.loads(output)
    assert result == 0
    assert report["ok"] is True
    assert report["all_rows_ineligible_for_import"] is True
    assert report["writes_performed"] is False
    assert captured["token"] == _PRIVATE_TOKEN
    assert captured["client"].calls == [_KEYS]
    assert _PRIVATE_TOKEN not in output
    assert registry.read_bytes() == before


def test_cli_hidden_prompt_failure_is_sanitized_and_fails_closed(
    monkeypatch, tmp_path, capsys
):
    registry = _registry(tmp_path / "trade_registry.json")
    constructed = []

    class UnexpectedRedis:
        def __init__(self, **_kwargs):
            constructed.append(True)

    def unavailable_prompt(_prompt):
        raise paper_registry_source_capture.getpass.GetPassWarning(
            "private terminal diagnostic"
        )

    monkeypatch.setenv("UPSTASH_REDIS_REST_URL", "https://redis.example.invalid")
    monkeypatch.delenv("UPSTASH_REDIS_REST_READONLY_TOKEN", raising=False)
    monkeypatch.setitem(sys.modules, "upstash_redis", ModuleType("upstash_redis"))
    sys.modules["upstash_redis"].Redis = UnexpectedRedis
    monkeypatch.setattr(
        paper_registry_source_capture.getpass, "getpass", unavailable_prompt
    )

    result = paper_registry_source_capture.main([
        "--read-upstash",
        "--prompt-readonly-token",
        "--registry-file",
        str(registry),
    ])

    output = capsys.readouterr().out
    report = json.loads(output)
    assert result == 2
    assert report["status"] == "UPSTASH_READ_ONLY_TOKEN_PROMPT_FAILED"
    assert report["all_rows_ineligible_for_import"] is True
    assert report["writes_performed"] is False
    assert constructed == []
    assert "private terminal diagnostic" not in output


def test_invalid_registry_json_stops_before_upstash_read(tmp_path):
    registry = tmp_path / "trade_registry.json"
    registry.write_text("{invalid-registry-private-data", encoding="utf-8")
    redis = FakeRedis()

    report = capture_paper_registry_sources(redis_client=redis, registry_path=registry)

    assert report["status"] == "REGISTRY_READ_INVALID"
    assert redis.calls == []
    assert "invalid-registry-private-data" not in json.dumps(report)


def test_mget_wrong_result_count_fails_closed(tmp_path):
    registry = _registry(tmp_path / "trade_registry.json")
    redis = FakeRedis(values=[json.dumps({})])

    report = capture_paper_registry_sources(redis_client=redis, registry_path=registry)

    assert report["status"] == "SOURCE_SNAPSHOT_INCOMPLETE"
    assert set(report["source_status_by_bot"].values()) == {"READ_FAILED"}
    assert report["all_rows_ineligible_for_import"] is True


def test_invalid_source_row_exposes_only_fixed_error_code(tmp_path):
    registry = _registry(tmp_path / "trade_registry.json")
    private_marker = "private-production-row-value"
    values = _source_values()
    values[0] = json.dumps({"legacy-position-key": private_marker})
    redis = FakeRedis(values=values)

    report = capture_paper_registry_sources(redis_client=redis, registry_path=registry)

    serialized = json.dumps(report)
    assert report["ok"] is False
    assert report["status"] == "SOURCE_SNAPSHOT_INVALID"
    assert report["validation_error_code"] == "SOURCE_POSITION_INVALID"
    assert report["all_rows_ineligible_for_import"] is True
    assert report["writes_performed"] is False
    assert redis.calls == [_KEYS]
    assert private_marker not in serialized
    assert "legacy-position-key" not in serialized


def test_unclassified_preview_exception_never_echoes_exception_text(monkeypatch, tmp_path):
    registry = _registry(tmp_path / "trade_registry.json")
    private_marker = "private-exception-payload"
    redis = FakeRedis()

    def fail_preview(_registry, _source):
        raise ValueError(private_marker)

    monkeypatch.setattr(
        paper_registry_source_capture,
        "preview_paper_registry_sources",
        fail_preview,
    )
    report = capture_paper_registry_sources(redis_client=redis, registry_path=registry)

    serialized = json.dumps(report)
    assert report["status"] == "SOURCE_SNAPSHOT_INVALID"
    assert report["validation_error_code"] == "UNCLASSIFIED_VALUE_ERROR"
    assert report["writes_performed"] is False
    assert private_marker not in serialized


def test_unexpected_preview_exception_is_sanitized_and_fails_closed(monkeypatch, tmp_path):
    registry = _registry(tmp_path / "trade_registry.json")
    private_marker = "private-unexpected-preview-error"
    redis = FakeRedis()

    def fail_preview(_registry, _source):
        raise RuntimeError(private_marker)

    monkeypatch.setattr(
        paper_registry_source_capture,
        "preview_paper_registry_sources",
        fail_preview,
    )

    report = capture_paper_registry_sources(redis_client=redis, registry_path=registry)

    serialized = json.dumps(report)
    assert report["status"] == "SOURCE_SNAPSHOT_INVALID"
    assert report["validation_error_code"] == "UNCLASSIFIED_PREVIEW_ERROR"
    assert report["all_rows_ineligible_for_import"] is True
    assert report["writes_performed"] is False
    assert private_marker not in serialized


def test_cli_does_not_read_upstash_without_explicit_flag(monkeypatch, capsys):
    def unexpected_read(**_kwargs):
        raise AssertionError("Upstash must not be contacted without --read-upstash")

    def unexpected_prompt(_prompt):
        raise AssertionError("token must not be prompted without --read-upstash")

    monkeypatch.setattr(paper_registry_source_capture, "capture_paper_registry_sources", unexpected_read)
    monkeypatch.setattr(
        paper_registry_source_capture.getpass,
        "getpass",
        unexpected_prompt,
    )

    result = paper_registry_source_capture.main(["--prompt-readonly-token"])

    report = json.loads(capsys.readouterr().out)
    assert result == 2
    assert report["status"] == "UPSTASH_READ_NOT_REQUESTED"
    assert report["writes_performed"] is False
