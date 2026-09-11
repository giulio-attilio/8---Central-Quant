"""Explicit Linux-only lab export and isolated test launcher; no runtime imports."""

import ast
import hashlib
import json
import os
from pathlib import Path
import pwd
import shutil
import subprocess
import sys
import uuid


TESTS = [
    "tests/test_c3_persistent_independent_authority_process_v1.py",
    "tests/test_c3_maintenance_ledger_process_probe.py",
    "tests/test_c3_maintenance_independent_consumption_v1.py",
    "tests/test_trade_registry_c3_maintenance_authority_startup_v1.py",
    "tests/test_trade_registry_c3_maintenance_activation_offline_v1.py",
]
EXTRA = [
    "tests/helpers/c3_independent_authority_child.py",
    "tests/helpers/c3_maintenance_ledger_child.py",
    "tests/helpers/c3_linux_lab.py",
    "trade_registry_c3_maintenance_activation_offline_v1.py",
    "trade_registry_c3_maintenance_authorization_v1.py",
    "trade_registry_closed_identity_conflict_repair_runtime_seam_v1.py",
]


def source_closure(source):
    pending, files = list(TESTS + EXTRA), {"main.py"}  # main is AST data, never import it.
    while pending:
        rel = pending.pop()
        if rel in files:
            continue
        path = source / rel
        if path.is_symlink() or not path.resolve().is_relative_to(source) or path.suffix != ".py":
            raise RuntimeError("unsafe export source")
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        files.add(rel)
        if len(files) > 300:
            raise RuntimeError("source closure unexpectedly broad")
        names = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.append(node.module)
            elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                  and node.func.attr == "import_module" and node.args
                  and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
                names.append(node.args[0].value)
        for name in names:
            if not all(part.isidentifier() for part in name.split(".")):
                raise RuntimeError("invalid module in export")
            for candidate in (name.replace(".", "/") + ".py", "tests/" + name + ".py"):
                if (source / candidate).is_file() and candidate not in files:
                    pending.append(candidate)
    return sorted(files)


def validate_lab(value):
    lab = Path(value).resolve(strict=True)
    if lab.parent != Path("/var/tmp") or not lab.name.startswith("cq-c3-lab-"):
        raise RuntimeError("expected dedicated Linux temporary lab directory")
    return lab


def export(source, lab):
    source = Path(source).resolve(strict=True)
    lab = validate_lab(lab)
    if any(lab.iterdir()):
        raise RuntimeError("export requires an empty fresh lab")
    files = source_closure(source)
    account = pwd.getpwnam("cq-c3-lab")
    target = lab / "src"
    target.mkdir()
    manifest = {}
    for rel in files:
        original = source / rel
        if original.is_symlink() or not original.resolve().is_relative_to(source):
            raise RuntimeError("source path changed")
        destination = target / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, destination)
        manifest[rel] = hashlib.sha256(destination.read_bytes()).hexdigest()
    # No environment file, data registry, git directory or operational log exported.
    (lab / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2))
    (lab / "scratch").mkdir()
    os.chmod(lab, 0o755)
    os.chown(lab / "scratch", account.pw_uid, account.pw_gid)
    print(json.dumps({"exported_python_files": len(files), "lab": str(lab),
                      "main_is_ast_data_only": True}), flush=True)


def launch(lab, *, extra_args=(), entrypoint="/work/tests/helpers/c3_linux_lab.py", timeout=300):
    lab = validate_lab(lab)
    manifest = json.loads((lab / "manifest.json").read_text())
    for rel, digest in manifest.items():
        path = lab / "src" / rel
        if not path.resolve().is_relative_to(lab / "src") or path.is_symlink():
            raise RuntimeError("invalid exported file")
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise RuntimeError("exported source changed")
    netns = os.readlink("/proc/self/ns/net")
    command = ["/usr/sbin/runuser", "--user", "cq-c3-lab", "--", "/usr/bin/bwrap",
               "--unshare-all", "--unshare-user", "--unshare-net", "--disable-userns", "--new-session",
               "--die-with-parent", "--cap-drop", "ALL", "--clearenv",
               "--ro-bind", "/usr", "/usr", "--symlink", "usr/bin", "/bin",
               "--symlink", "usr/sbin", "/sbin", "--symlink", "usr/lib", "/lib",
               "--symlink", "usr/lib64", "/lib64", "--proc", "/proc", "--dev", "/dev",
               "--tmpfs", "/tmp", "--dir", "/etc",
               "--ro-bind", str(lab / "src"), "/work",
               "--bind", str(lab / "scratch"), "/scratch", "--chdir", "/work",
               "--setenv", "PATH", "/usr/bin:/bin",
               "--setenv", "PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1",
               "--setenv", "PYTHONDONTWRITEBYTECODE", "1",
               "--setenv", "LC_ALL", "C.UTF-8",
               *extra_args, "/usr/bin/python3", "-B", entrypoint, "inside", netns]
    raise SystemExit(subprocess.call(command, timeout=timeout))


def verify_isolation(parent_netns):
    # These checks precede ANY import of repository modules or pytest plugins.
    assert sys.platform == "linux" and os.getuid() != 0
    assert os.readlink("/proc/self/ns/net") != parent_netns
    assert len(Path("/proc/net/route").read_text().splitlines()) == 1
    assert not any(Path(p).exists() for p in ("/mnt", "/home", "/root", "/run", "/etc/shadow"))
    assert "WSL_INTEROP" not in os.environ
    assert os.statvfs("/work").f_flag & os.ST_RDONLY
    status = Path("/proc/self/status").read_text()
    assert "CapEff:\t0000000000000000" in status and "NoNewPrivs:\t1" in status
    mounts = Path("/proc/self/mountinfo").read_text().splitlines()
    assert any(" /scratch " in line and " - ext4 " in line for line in mounts)
    print(json.dumps({"isolation_verified": True, "network_routes": 0,
                      "windows_mounts_visible": False, "uid": os.getuid(),
                      "scratch_filesystem": "ext4", "source_read_only": True}), flush=True)


def inside(parent_netns):
    verify_isolation(parent_netns)
    sys.path.insert(0, "/work")
    import pytest
    run_id = uuid.uuid4().hex
    raise SystemExit(pytest.main(["-q", "-rs", "--runxfail", "-p", "no:cacheprovider",
        "--basetemp=/scratch/pytest-" + run_id, "--junitxml=/scratch/results-" + run_id + ".xml", *TESTS]))


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "export" and len(sys.argv) == 4:
        export(sys.argv[2], sys.argv[3])
    elif mode == "launch" and len(sys.argv) == 3:
        launch(sys.argv[2])
    elif mode == "inside" and len(sys.argv) == 3:
        inside(sys.argv[2])
    else:
        raise SystemExit("explicit export, launch or inside mode required")
