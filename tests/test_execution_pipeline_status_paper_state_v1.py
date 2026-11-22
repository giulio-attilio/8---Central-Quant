import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import execution_pipeline_status as pipeline


class ExecutionPipelinePaperStateTest(unittest.TestCase):
    def _healthy_components(self):
        return (
            mock.patch.object(pipeline, "execution_engine_health", return_value={"ok": True, "real_execution_enabled": False}),
            mock.patch.object(pipeline, "paper_lifecycle_health", return_value={"ok": True}),
            mock.patch.object(pipeline, "outcome_evaluator_health", return_value={"ok": True}),
            mock.patch.object(pipeline, "adaptive_weights_health", return_value={"ok": True}),
            mock.patch.object(pipeline, "get_adaptive_weights", return_value={"weights": {}}),
        )

    def test_enabled_paper_with_missing_state_is_not_pipeline_ready(self):
        patches = self._healthy_components()
        with patches[0], patches[1], patches[2], patches[3], patches[4], mock.patch.object(
            pipeline,
            "paper_integrated_health",
            return_value={
                "ok": True,
                "paper_execution_enabled": True,
                "state_files_present": False,
                "state_files_valid": False,
                "state_files_status": "PAPER_STATE_FILES_MISSING",
                "open_positions": None,
                "closed_positions": None,
                "pending_outcome": None,
                "total_positions": None,
            },
        ):
            result = pipeline.build_execution_pipeline_status()

        self.assertEqual(result["status"], "ERRO")
        self.assertFalse(result["pipeline"]["components"]["paper_executor"]["ok"])
        self.assertIsNone(result["positions"]["open"])
        self.assertIn(
            "Estado persistente PAPER ausente ou inválido; execução PAPER não está pronta.",
            result["alerts"],
        )

    def test_valid_empty_paper_state_is_distinguished_from_missing_state(self):
        patches = self._healthy_components()
        with patches[0], patches[1], patches[2], patches[3], patches[4], mock.patch.object(
            pipeline,
            "paper_integrated_health",
            return_value={
                "ok": True,
                "paper_execution_enabled": True,
                "state_files_present": True,
                "state_files_valid": True,
                "state_files_status": "PAPER_STATE_FILES_PRESENT",
                "open_positions": 0,
                "closed_positions": 0,
                "pending_outcome": 0,
                "total_positions": 0,
            },
        ):
            result = pipeline.build_execution_pipeline_status()

        self.assertTrue(result["pipeline"]["components"]["paper_executor"]["ok"])
        self.assertEqual(result["positions"]["open"], 0)
        self.assertEqual(result["positions"]["state_files_status"], "PAPER_STATE_FILES_PRESENT")

    def test_outcome_summary_does_not_turn_unverified_mount_into_zero_trades(self):
        with mock.patch.object(pipeline, "paper_data_mount_verified", return_value=False):
            result = pipeline._outcome_summary()

        self.assertEqual(result["status"], "PAPER_DATA_MOUNT_NOT_VERIFIED")
        self.assertIsNone(result["trades"])
        self.assertIsNone(result["wins"])

    def test_outcome_summary_uses_guarded_presence_check(self):
        with mock.patch.object(pipeline, "paper_data_mount_verified", return_value=True), mock.patch.object(
            pipeline, "paper_file_exists", return_value=False
        ) as guarded_exists:
            result = pipeline._outcome_summary()

        guarded_exists.assert_called_once_with(pipeline.OUTCOME_STATS_FILE)
        self.assertEqual(result["status"], "OUTCOME_STATS_MISSING")
        self.assertIsNone(result["trades"])

    def test_outcome_summary_fails_closed_on_presence_guard_error(self):
        with mock.patch.object(pipeline, "paper_data_mount_verified", return_value=True), mock.patch.object(
            pipeline, "paper_file_exists", side_effect=OSError("symlink rejected")
        ):
            result = pipeline._outcome_summary()

        self.assertEqual(result["status"], "PAPER_DATA_MOUNT_NOT_VERIFIED")
        self.assertIsNone(result["exists"])
        self.assertIsNone(result["trades"])

    def test_adaptive_summary_does_not_follow_unverified_presence_path(self):
        patches = self._healthy_components()
        with patches[0], patches[1], patches[2], patches[3], mock.patch.object(
            pipeline, "get_adaptive_weights", return_value={"ok": True, "weights": {}}
        ), mock.patch.object(
            pipeline, "paper_file_exists", side_effect=OSError("symlink rejected")
        ) as guarded_exists:
            result = pipeline._adaptive_summary()

        guarded_exists.assert_called_once_with(pipeline.ADAPTIVE_WEIGHTS_FILE)
        self.assertIsNone(result["exists"])


if __name__ == "__main__":
    unittest.main()
