"""Exercise only reviewed main.py fragments; never import the application."""

import ast
import os
import socket
import ssl  # Load before replacing socket.socket.
import subprocess
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


def forbidden(*_args, **_kwargs):
    raise AssertionError("C3_PROVIDER_NETWORK_OR_PROCESS_CALL_FORBIDDEN")


with patch.object(socket, "socket", side_effect=forbidden), patch.object(
    socket, "getaddrinfo", side_effect=forbidden
), patch.object(subprocess, "Popen", side_effect=forbidden):
    import trade_registry_c3_independent_root_head_read_offline_v1 as reader_v1
    import trade_registry_c3_root_head_recovery_composition_offline_v1 as probe_v1
    import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_persistent_authority_boundary_v2 as boundary_v2


READER = "C3_CLOSED_REPAIR_ROOT_HEAD_READER_OFFLINE_V1"
PROBE = "C3_CLOSED_REPAIR_ROOT_HEAD_RECOVERY_OFFLINE_V1"
BOUNDARY = "C3_CLOSED_REPAIR_AUTHENTICATED_PERSISTENT_AUTHORITY_BOUNDARY_V2"


class DormantRootHeadStartupIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tree = ast.parse(
            (Path(__file__).resolve().parents[1] / "main.py").read_text(
                encoding="utf-8"
            )
        )
        for owner, name in (
            (socket, "socket"), (socket, "create_connection"),
            (socket, "getaddrinfo"), (subprocess, "Popen"),
            (os, "system"), (os, "popen"),
        ):
            active = patch.object(owner, name, side_effect=forbidden)
            active.start()
            self.addCleanup(active.stop)

    def _assembly(self):
        boundary = boundary_v2.AuthenticatedPersistentAuthorityBoundaryV2()
        namespace = {
            BOUNDARY: boundary,
            "c3_independent_root_head_read_offline_v1": reader_v1,
            "c3_root_head_recovery_composition_offline_v1": probe_v1,
        }
        selected = [
            node for node in self.tree.body
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id in (READER, PROBE)
                    for target in node.targets)
        ]
        self.assertEqual(len(selected), 2)
        exec(compile(ast.Module(body=selected, type_ignores=[]), "<c3-dormant-assembly>", "exec"), namespace)
        return boundary, namespace

    def _recover(self, namespace, boundary):
        class Interlocks:
            _bound_startup_recovery = boundary

            def coordination_status(self):
                return {"enabled": False}

            def run_startup_recovery_v1(self):
                forbidden()

        namespace["c3_runtime_seam_v1"] = SimpleNamespace(
            C3ClosedRepairRuntimeInterlockBindingV1=Interlocks
        )
        node = next(
            node for node in self.tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "_recover_c3_closed_repair_registry_v1"
        )
        exec(compile(ast.Module(body=[node], type_ignores=[]), "<c3-dormant-recovery>", "exec"), namespace)
        return namespace[node.name], Interlocks()

    def test_main_binds_default_off_probe_before_startup_without_io(self):
        positions = {}
        for index, node in enumerate(self.tree.body):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        positions[target.id] = index
        self.assertLess(positions[BOUNDARY], positions[READER])
        self.assertLess(positions[READER], positions[PROBE])
        self.assertLess(positions[PROBE], positions["C3_CLOSED_REPAIR_STARTUP_RECOVERY_V1"])
        boundary, namespace = self._assembly()
        probe = namespace[PROBE]
        self.assertIs(probe._boundary, boundary)
        self.assertIs(probe._head_reader, namespace[READER])
        self.assertIs(probe._config.enabled, False)
        self.assertIs(namespace[READER]._config.enabled, False)
        namespace[READER]._client = SimpleNamespace(get_item=forbidden)
        recover, interlocks = self._recover(namespace, boundary)
        result = recover(interlocks=interlocks)
        self.assertEqual(result["status"], "C3_DORMANT_STARTUP_RECOVERY_DEFERRED_DEFAULT_OFF")
        self.assertFalse(result["readiness_allowed"])
        self.assertFalse(result["network_accessed"])

    def test_probe_drift_blocks_before_any_provider_call(self):
        boundary, namespace = self._assembly()
        recover, interlocks = self._recover(namespace, boundary)
        probe = namespace[PROBE]
        for change in ("probe_enabled", "reader_enabled", "boundary_swapped"):
            with self.subTest(change=change):
                original_config = probe._config
                original_reader_config = probe._head_reader._config
                original_boundary = probe._boundary
                try:
                    if change == "probe_enabled":
                        probe._config = replace(original_config, enabled=True)
                    elif change == "reader_enabled":
                        probe._head_reader._config = replace(original_reader_config, enabled=True)
                    else:
                        probe._boundary = boundary_v2.AuthenticatedPersistentAuthorityBoundaryV2()
                    with patch.object(probe, "check", side_effect=forbidden):
                        result = recover(interlocks=interlocks)
                    self.assertEqual(result["status"], "C3_STARTUP_RECOVERY_BLOCKED")
                    self.assertFalse(result["readiness_allowed"])
                finally:
                    probe._config = original_config
                    probe._head_reader._config = original_reader_config
                    probe._boundary = original_boundary

    def test_probe_exception_fails_closed(self):
        boundary, namespace = self._assembly()
        recover, interlocks = self._recover(namespace, boundary)
        with patch.object(namespace[PROBE], "check", side_effect=RuntimeError("test")):
            result = recover(interlocks=interlocks)
        self.assertEqual(result["reason"], "ROOT_HEAD_RECOVERY_DORMANT_PROBE_INVALID")
        self.assertFalse(result["readiness_allowed"])


if __name__ == "__main__":
    unittest.main()
