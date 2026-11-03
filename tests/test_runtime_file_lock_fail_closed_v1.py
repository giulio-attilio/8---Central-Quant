"""Source-level regressions for fail-closed runtime process locks."""

import ast
import copy
import json
import os
from pathlib import Path
import re
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "main.py"


def _lock_function():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
    return next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "acquire_runtime_file_lock"
    )


LOCK_FUNCTION = _lock_function()


def _namespace(tmp_path, fcntl, *, handles=None, open_fn=open):
    return {
        "re": re,
        "os": os,
        "json": json,
        "fcntl": fcntl,
        "CENTRAL_DATA_DIR": tmp_path,
        "CENTRAL_PROCESS_LOCK_HANDLES": handles if handles is not None else {},
        "BASE_DIR": tmp_path,
        "data_hora_sp_str": lambda: "synthetic-time",
        "open": open_fn,
        "print": lambda *_args, **_kwargs: None,
    }


def _compile_lock(namespace):
    module = ast.Module(body=[copy.deepcopy(LOCK_FUNCTION)], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), str(SOURCE), "exec"), namespace)
    return namespace["acquire_runtime_file_lock"]


def test_missing_flock_fails_closed_without_creating_lock_file(tmp_path):
    handles = {}
    acquire = _compile_lock(_namespace(tmp_path, None, handles=handles))

    assert acquire("central_telegram_polling") is False
    assert handles == {}
    assert not (tmp_path / "central_telegram_polling.lock").exists()


def test_busy_lock_fails_closed_and_closes_candidate_handle(tmp_path):
    lock_file = tmp_path / "central_telegram_polling.lock"
    existing_metadata = '{"lock":"central_telegram_polling","pid":1234}'
    lock_file.write_text(existing_metadata, encoding="utf-8")

    class BusyFcntl:
        LOCK_EX = 1
        LOCK_NB = 2

        @staticmethod
        def flock(_fd, _flags):
            raise BlockingIOError("synthetic lock is held")

    handles = {}
    acquire = _compile_lock(_namespace(tmp_path, BusyFcntl, handles=handles))

    assert acquire("central_telegram_polling") is False
    assert handles == {}
    assert lock_file.read_text(encoding="utf-8") == existing_metadata


def test_lock_system_error_fails_closed_and_closes_candidate_handle(tmp_path):
    class ErrorFcntl:
        LOCK_EX = 1
        LOCK_NB = 2

        @staticmethod
        def flock(_fd, _flags):
            raise OSError("synthetic flock failure")

    handles = {}
    acquire = _compile_lock(_namespace(tmp_path, ErrorFcntl, handles=handles))

    assert acquire("central_telegram_polling") is False
    assert handles == {}


def test_lock_file_open_failure_fails_closed(tmp_path):
    class WorkingFcntl:
        LOCK_EX = 1
        LOCK_NB = 2

        @staticmethod
        def flock(_fd, _flags):
            return None

    def denied_open(*_args, **_kwargs):
        raise PermissionError("synthetic disk permission failure")

    handles = {}
    acquire = _compile_lock(
        _namespace(tmp_path, WorkingFcntl, handles=handles, open_fn=denied_open)
    )

    assert acquire("central_telegram_polling") is False
    assert handles == {}


def test_lock_metadata_write_failure_releases_lock_and_fails_closed(tmp_path):
    class WorkingFcntl:
        LOCK_EX = 1
        LOCK_NB = 2

        @staticmethod
        def flock(_fd, _flags):
            return None

    class FailingFile:
        closed = False

        def fileno(self):
            return 1

        def seek(self, _offset):
            return None

        def truncate(self):
            return None

        def write(self, _payload):
            raise OSError("synthetic lock metadata write failure")

        def close(self):
            self.closed = True

    lock_file = FailingFile()
    handles = {}
    acquire = _compile_lock(
        _namespace(tmp_path, WorkingFcntl, handles=handles, open_fn=lambda *_a, **_k: lock_file)
    )

    assert acquire("central_telegram_polling") is False
    assert lock_file.closed is True
    assert handles == {}


def test_duplicate_same_process_lock_request_is_denied(tmp_path):
    class WorkingFcntl:
        LOCK_EX = 1
        LOCK_NB = 2

        @staticmethod
        def flock(_fd, _flags):
            return None

    handles = {}
    acquire = _compile_lock(_namespace(tmp_path, WorkingFcntl, handles=handles))

    assert acquire("central_telegram_polling") is True
    held = handles["central_telegram_polling"]
    try:
        metadata = json.loads(
            (tmp_path / "central_telegram_polling.lock").read_text(encoding="utf-8")
        )
        assert metadata["lock"] == "central_telegram_polling"
        assert metadata["pid"] == os.getpid()
        assert acquire("central_telegram_polling") is False
        assert handles["central_telegram_polling"] is held
    finally:
        held.close()


def test_runtime_lock_names_are_unique_across_bot_and_shared_loops():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
    lock_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "acquire_runtime_file_lock"
    ]
    assert lock_calls

    literal_names = [
        node.args[0].value
        for node in lock_calls
        if node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    ]
    assert len(literal_names) == len(set(literal_names))

    bot_lock_calls = [
        node
        for node in lock_calls
        if node.args and isinstance(node.args[0], ast.JoinedStr)
    ]
    assert len(bot_lock_calls) == 1
    bot_lock_name = bot_lock_calls[0].args[0]
    assert isinstance(bot_lock_name.values[0], ast.Constant)
    assert bot_lock_name.values[0].value == "bot_telegram_"

    config_assignment = next(
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "BOT_CONFIGS"
            for target in node.targets
        )
    )
    assert isinstance(config_assignment.value, ast.Dict)
    bot_keys = [
        key.value
        for key in config_assignment.value.keys
        if isinstance(key, ast.Constant) and isinstance(key.value, str)
    ]
    normalized_bot_keys = [key.strip().lower() for key in bot_keys]
    assert len(bot_keys) == len(config_assignment.value.keys)
    assert len(normalized_bot_keys) == len(set(normalized_bot_keys))

    generated_bot_lock_names = {
        f"bot_telegram_{key}" for key in normalized_bot_keys
    }
    assert generated_bot_lock_names.isdisjoint(literal_names)
