"""Candidate-only controls: corrupt source projection, never production data."""
from pathlib import Path
import pytest
import trade_registry_closed_identity_conflict_repair_runtime_readiness_binding_harness_v1 as binding
import trade_registry_closed_identity_conflict_repair_runtime_readiness_preflight_patch_plan_harness_v1 as plan

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("verify", [binding._attest_pinned_sources_read_only_v1,
                                    plan._verify_source_pins_read_only_v1])
def test_actual_main_source_drift_is_rejected_without_writing(monkeypatch, verify):
    original = Path.read_text
    main = ROOT / "main.py"

    def altered_read(path, *args, **kwargs):
        value = original(path, *args, **kwargs)
        return value + "\n# synthetic source drift\n" if path == main else value

    monkeypatch.setattr(Path, "read_text", altered_read)
    with pytest.raises(AssertionError, match="drifted: live_preflight_owner"):
        verify(ROOT)
