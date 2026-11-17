from __future__ import annotations

import builtins
import json
import errno
import os
from pathlib import Path
from types import SimpleNamespace
import pytest

import executive_policy_learning
import paper_state_storage


def test_render_rejects_paper_paths_outside_persistent_root(monkeypatch, tmp_path):
    data_root = tmp_path / "data"
    ephemeral = tmp_path / "ephemeral" / "positions.json"
    monkeypatch.setenv("RENDER", "true")

    assert paper_state_storage.paper_data_mount_verified(
        ephemeral,
        platform_name="posix",
        data_root=data_root,
    ) is False


def test_non_render_local_paths_remain_available_for_offline_tests(
    monkeypatch, tmp_path
):
    data_root = tmp_path / "data"
    local_state = tmp_path / "local-test" / "positions.json"
    monkeypatch.delenv("RENDER", raising=False)

    assert paper_state_storage.paper_data_mount_verified(
        local_state,
        platform_name="posix",
        data_root=data_root,
    ) is True


def test_policy_outcome_log_reader_refuses_unverified_paper_path(
    monkeypatch, tmp_path
):
    paper_log = tmp_path / "paper_lifecycle_log.jsonl"
    paper_log.write_text('{"event":"test"}\n', encoding="utf-8")
    opened = []

    def reject_mount(_path):
        return False

    def record_open(*args, **kwargs):
        opened.append(args[0] if args else None)
        raise AssertionError("unverified PAPER log was opened")

    monkeypatch.setattr(
        executive_policy_learning,
        "paper_data_mount_verified",
        reject_mount,
    )
    monkeypatch.setattr(builtins, "open", record_open)

    assert executive_policy_learning._read_jsonl_tail_items(paper_log) == []
    assert opened == []


def test_policy_outcome_index_distinguishes_empty_missing_and_failed_reads(
    monkeypatch, tmp_path
):
    empty_log = tmp_path / "empty.jsonl"
    empty_log.write_text("", encoding="utf-8")
    denied_log = tmp_path / "denied.jsonl"
    denied_log.write_text('{"event":"present-but-unreadable"}\n', encoding="utf-8")
    missing_log = tmp_path / "missing.jsonl"
    real_open = paper_state_storage.open_paper_binary

    def guarded_open(path, *args, **kwargs):
        if Path(path) == denied_log:
            raise PermissionError("synthetic read denial")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(
        executive_policy_learning,
        "_policy_outcome_candidate_paths",
        lambda: [empty_log, denied_log, missing_log],
    )
    monkeypatch.setattr(
        executive_policy_learning,
        "paper_data_mount_verified",
        lambda _path: True,
    )
    monkeypatch.setattr(
        executive_policy_learning,
        "open_paper_binary",
        guarded_open,
    )

    report = executive_policy_learning._load_policy_outcome_index()
    sources = report["sources"]

    assert [(source["read_status"], source["exists"], source["events"]) for source in sources] == [
        ("READ_OK", True, 0),
        ("READ_FAILED", True, 0),
        ("MISSING", False, 0),
    ]


def test_policy_learning_state_writer_fails_closed_when_path_is_unverified(
    monkeypatch, tmp_path
):
    target = tmp_path / "policy-state.json"

    monkeypatch.setattr(
        paper_state_storage,
        "paper_data_mount_verified",
        lambda _path, **_kwargs: False,
    )

    try:
        executive_policy_learning._write_json(target, {"safe": True})
    except OSError as exc:
        assert str(exc) == "PAPER_DATA_MOUNT_NOT_VERIFIED_OR_WRITE_FAILED"
    else:
        raise AssertionError("unverified state write was accepted")

    assert not target.exists()


@pytest.mark.skipif(os.name == "nt", reason="requires POSIX dir_fd/O_NOFOLLOW")
def test_descriptor_open_rejects_real_root_nested_and_relative_symlinks(tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "paper").mkdir()
    (outside / "ledger.json").write_text('{"outside":true}', encoding="utf-8")

    safe = root / "paper" / "ledger.json"
    safe.write_text('{"inside":true}', encoding="utf-8")
    fd = paper_state_storage._open_fd_under_root(
        safe,
        root,
        os.O_RDONLY,
        require_mount=False,
    )
    try:
        assert os.read(fd, 100) == b'{"inside":true}'
    finally:
        os.close(fd)

    (root / "nested-link").symlink_to(outside, target_is_directory=True)
    (root / "relative-link").symlink_to(Path("../outside"), target_is_directory=True)
    for target in (
        root / "nested-link" / "ledger.json",
        root / "relative-link" / "ledger.json",
    ):
        with pytest.raises(OSError):
            paper_state_storage._open_fd_under_root(
                target,
                root,
                os.O_RDONLY,
                require_mount=False,
            )

    root_alias = tmp_path / "data-alias"
    root_alias.symlink_to(root, target_is_directory=True)
    with pytest.raises(OSError):
        paper_state_storage._open_fd_under_root(
            root_alias / "paper" / "ledger.json",
            root_alias,
            os.O_RDONLY,
            require_mount=False,
        )

    file_link = root / "paper" / "file-link.json"
    file_link.symlink_to(outside / "ledger.json")
    with pytest.raises(OSError):
        paper_state_storage._open_fd_under_root(
            file_link,
            root,
            os.O_RDONLY,
            require_mount=False,
        )


@pytest.mark.skipif(os.name == "nt", reason="requires POSIX symlink semantics")
def test_mount_guard_rejects_data_root_symlink_and_missing_target_under_nested_symlink(
    tmp_path,
):
    persistent_target = tmp_path / "persistent-target"
    persistent_target.mkdir()
    data_root_link = tmp_path / "data-root-link"
    data_root_link.symlink_to(persistent_target, target_is_directory=True)

    assert paper_state_storage.paper_data_mount_verified(
        data_root_link / "paper" / "ledger.json",
        platform_name="posix",
        data_root=data_root_link,
    ) is False

    root = tmp_path / "data"
    outside = tmp_path / "ephemeral"
    root.mkdir()
    outside.mkdir()
    (root / "paper-link").symlink_to(outside, target_is_directory=True)
    missing_target = root / "paper-link" / "ledger-does-not-exist.json"

    # The target's absence must not hide the escaping intermediate symlink.
    assert not missing_target.exists()
    assert paper_state_storage.paper_data_mount_verified(
        missing_target,
        platform_name="posix",
        data_root=root,
    ) is False


@pytest.mark.skipif(os.name == "nt", reason="requires POSIX dir_fd/O_NOFOLLOW")
def test_open_parent_descriptor_stays_anchored_if_path_is_replaced(tmp_path):
    root = tmp_path / "data"
    parent = root / "paper"
    outside = tmp_path / "outside"
    parent.mkdir(parents=True)
    outside.mkdir()
    target = parent / "ledger.json"

    parent_fd, name, root_fd, _device, _mount_id = (
        paper_state_storage._open_parent_under_root(
            target,
            root,
            require_mount=False,
        )
    )
    moved_parent = root / "paper-moved"
    try:
        parent.rename(moved_parent)
        parent.symlink_to(outside, target_is_directory=True)
        fd = os.open(
            name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=parent_fd,
        )
        os.write(fd, b"anchored")
        os.close(fd)
        assert (moved_parent / "ledger.json").read_bytes() == b"anchored"
        assert not (outside / "ledger.json").exists()
    finally:
        os.close(parent_fd)
        os.close(root_fd)


@pytest.mark.skipif(os.name == "nt", reason="requires POSIX dir_fd/O_NOFOLLOW")
def test_descriptor_walk_rejects_nested_mount_id_even_on_same_device(
    monkeypatch, tmp_path
):
    root = tmp_path / "data"
    nested = root / "paper"
    nested.mkdir(parents=True)
    target = nested / "positions.json"
    calls = 0

    def different_mount_ids(_fd):
        nonlocal calls
        calls += 1
        return 11 if calls == 1 else 12

    monkeypatch.setattr(paper_state_storage, "_mount_id_for_fd", different_mount_ids)
    with pytest.raises(OSError, match="PAPER_NESTED_MOUNT_REJECTED"):
        paper_state_storage._open_parent_under_root(
            target,
            root,
            require_mount=False,
        )


@pytest.mark.skipif(os.name == "nt", reason="requires POSIX dir_fd/O_NOFOLLOW")
def test_production_mount_rejects_same_device_bind_mount(
    monkeypatch, tmp_path
):
    root = tmp_path / "data"
    root.mkdir()
    target = root / "positions.json"
    mount_ids = iter((11, 12))
    original_fstat = os.fstat
    fstat_calls = 0
    root_device = []

    def same_device_fstat(fd):
        nonlocal fstat_calls
        fstat_calls += 1
        result = original_fstat(fd)
        if fstat_calls == 1:
            root_device.append(result.st_dev)
        elif fstat_calls == 2:
            return SimpleNamespace(st_dev=root_device[0])
        return result

    monkeypatch.setattr(
        paper_state_storage,
        "paper_data_mount_verified",
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(paper_state_storage.os, "fstat", same_device_fstat)
    monkeypatch.setattr(
        paper_state_storage,
        "_mount_id_for_fd",
        lambda _fd: next(mount_ids),
    )

    # Force the / descriptor to report the data root's st_dev while assigning
    # a different mount ID, modeling a same-device bind mount of ephemeral data.
    with pytest.raises(OSError, match="PAPER_DATA_MOUNT_NOT_VERIFIED"):
        paper_state_storage._open_parent_under_root(
            target,
            root,
            require_mount=True,
        )


@pytest.mark.skipif(os.name == "nt", reason="requires POSIX dir_fd/O_NOFOLLOW")
def test_atomic_replace_uses_same_verified_directory_and_does_not_follow_target_symlink(
    tmp_path,
):
    root = tmp_path / "data"
    parent = root / "paper"
    outside = tmp_path / "outside"
    parent.mkdir(parents=True)
    outside.mkdir()
    external_target = outside / "ledger.json"
    external_target.write_text('{"outside":true}', encoding="utf-8")
    link = parent / "positions.json"
    link.symlink_to(external_target)

    assert paper_state_storage._write_json_atomically_under_data(
        link,
        {"safe": True},
        data_root=root,
        require_mount=False,
    )
    assert json.loads(link.read_text(encoding="utf-8")) == {"safe": True}
    assert json.loads(external_target.read_text(encoding="utf-8")) == {"outside": True}
    assert sorted(p.name for p in parent.iterdir()) == ["positions.json"]


def test_paper_atomic_bytes_write_calls_hook_after_fsync_and_replaces_atomically(tmp_path):
    target = tmp_path / "registry_v2.json"
    target.write_bytes(b"old")
    stages = []

    paper_state_storage.write_paper_bytes_atomically(
        target,
        b"new",
        after_temp_fsync=lambda: stages.append("after_fsync"),
    )

    assert stages == ["after_fsync"]
    assert target.read_bytes() == b"new"
    assert list(tmp_path.iterdir()) == [target]


def test_paper_atomic_bytes_write_preserves_previous_target_on_fault(tmp_path):
    target = tmp_path / "registry_v2.json"
    target.write_bytes(b"old")

    def fail_after_fsync():
        raise RuntimeError("injected crash")

    with pytest.raises(RuntimeError, match="injected crash"):
        paper_state_storage.write_paper_bytes_atomically(
            target,
            b"new",
            after_temp_fsync=fail_after_fsync,
        )

    assert target.read_bytes() == b"old"
    assert list(tmp_path.iterdir()) == [target]


def test_safe_binary_modes_support_wal_lock_and_truncate(tmp_path):
    path = tmp_path / "registry_v2.lock"
    with paper_state_storage.open_paper_binary(path, "a+b") as handle:
        handle.write(b"0")
        handle.flush()
    with paper_state_storage.open_paper_binary(path, "r+b") as handle:
        handle.seek(0)
        handle.truncate()
        handle.write(b"1")
    assert path.read_bytes() == b"1"


def test_paper_file_exists_reports_missing_then_present(tmp_path):
    path = tmp_path / "registry_v2.json"
    assert paper_state_storage.paper_file_exists(path) is False
    path.write_text("{}", encoding="utf-8")
    assert paper_state_storage.paper_file_exists(path) is True


@pytest.mark.skipif(os.name == "nt", reason="requires POSIX dir_fd/O_NOFOLLOW")
def test_v2_wal_helpers_anchor_temp_root_and_replace_symlink_without_following(
    tmp_path,
):
    root = tmp_path / "data"
    parent = root / "paper"
    outside = tmp_path / "outside"
    parent.mkdir(parents=True)
    outside.mkdir()
    target = parent / "registry_v2.json"
    external_target = outside / "keep.json"
    external_target.write_bytes(b"external")
    target.symlink_to(external_target)

    paper_state_storage.write_paper_bytes_atomically(
        target,
        b"persistent-state",
        data_root=root,
        require_mount=False,
    )
    paper_state_storage.fsync_paper_directory(
        parent,
        data_root=root,
        require_mount=False,
    )

    assert target.read_bytes() == b"persistent-state"
    assert not target.is_symlink()
    assert external_target.read_bytes() == b"external"
    assert paper_state_storage.paper_file_exists(
        target,
        data_root=root,
        require_mount=False,
    )


@pytest.mark.skipif(os.name == "nt", reason="requires POSIX dir_fd/O_NOFOLLOW")
def test_v2_wal_binary_open_rejects_symlink_and_supports_locked_mutation(tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    target = root / "registry_v2.lock"
    outside = tmp_path / "outside.lock"
    outside.write_bytes(b"external")
    target.symlink_to(outside)

    with pytest.raises(OSError) as open_error:
        paper_state_storage.open_paper_binary(
            target,
            "a+b",
            data_root=root,
            require_mount=False,
        )
    assert open_error.value.errno == errno.ELOOP
    with pytest.raises(OSError, match="PAPER_SYMLINK_REJECTED"):
        paper_state_storage.paper_file_exists(
            target,
            data_root=root,
            require_mount=False,
        )
    assert outside.read_bytes() == b"external"

    target.unlink()
    with paper_state_storage.open_paper_binary(
        target,
        "a+b",
        data_root=root,
        require_mount=False,
    ) as handle:
        handle.write(b"0")
        handle.flush()
    with paper_state_storage.open_paper_binary(
        target,
        "r+b",
        data_root=root,
        require_mount=False,
    ) as handle:
        handle.seek(0)
        handle.truncate()
        handle.write(b"1")
    assert target.read_bytes() == b"1"
