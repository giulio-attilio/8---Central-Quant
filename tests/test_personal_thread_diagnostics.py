import json

from personal_thread_diagnostics import collect_thread_diagnostics


def test_thread_diagnostics_returns_bounded_locations_without_values_or_paths():
    local_secret_sentinel = "DO_NOT_SERIALIZE_THIS_VALUE"
    payload = collect_thread_diagnostics()
    serialized = json.dumps(payload)

    assert payload["ok"] is True
    assert payload["status"] == "THREAD_DIAGNOSTIC_ONLY"
    assert 1 <= len(payload["threads"]) <= 64
    assert local_secret_sentinel not in serialized
    for thread in payload["threads"]:
        assert set(thread) == {
            "name",
            "ident",
            "native_id",
            "daemon",
            "alive",
            "stack_available",
            "stack_truncated",
            "frames",
        }
        assert len(thread["frames"]) <= 24
        for frame in thread["frames"]:
            assert set(frame) == {"file", "function", "line"}
            assert "/" not in frame["file"]
            assert "\\" not in frame["file"]
            assert isinstance(frame["line"], int)


def test_thread_diagnostic_bounds_filename_and_name_values():
    from personal_thread_diagnostics import _safe_basename, _safe_thread_name

    assert _safe_basename(r"C:\private\main.py") == "main.py"
    assert _safe_basename("/srv/project/main.py") == "main.py"
    assert _safe_thread_name("scan\nscanner") == "scan?scanner"
    assert len(_safe_thread_name("x" * 200)) == 80
