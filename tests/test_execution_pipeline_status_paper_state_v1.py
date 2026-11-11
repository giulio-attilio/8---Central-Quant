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


if __name__ == "__main__":
    unittest.main()
