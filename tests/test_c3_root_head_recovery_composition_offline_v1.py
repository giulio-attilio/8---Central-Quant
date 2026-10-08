import sys
import unittest
from pathlib import Path
import tempfile
import socket
import subprocess

def _block(*args, **kwargs):
    raise RuntimeError("Network/Subprocess blocked")

socket.socket = _block
subprocess.Popen = _block

project_root = r"c:\Users\giuli\OneDrive\Documentos\GitHub\8---Central-Quant\.worktrees\c3_final_release_promote_20260910"
sys.path.insert(0, project_root)

import trade_registry_c3_independent_root_head_read_offline_v1 as root_head_read
import trade_registry_c3_root_head_recovery_composition_offline_v1 as recovery_comp
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_persistent_authority_boundary_harness_v2 as boundary_harness
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_source_ports_contract_v2 as ports_v2
import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as hash_v2

class MockDynamoDBClient:
    def __init__(self, item_to_return=None):
        self._item = item_to_return
        self.called = False
    def get_item(self, **kwargs):
        self.called = True
        if self._item is None:
            raise RuntimeError("DynamoDB item not found")
        return {"Item": self._item}

class TestRootHeadRecovery(unittest.TestCase):
    def test_offline_recovery_composition(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            # 1. Build Synthetic Boundary Context
            boundary_ctx = boundary_harness.build_authenticated_persistent_authority_boundary_context_v2(temp_dir)
            boundary = boundary_ctx["boundary"]
            attestation = boundary_ctx["attestation"]
            
            # 2. Setup mock DynamoDB
            root_identity = attestation["root_identity_sha256"]
            storage_binding = attestation["storage_binding_sha256"]
            key_id = attestation["key_id_sha256"]
            head_attest = attestation["attestation_sha256"]
            key_epoch = attestation["key_epoch"]
            
            valid_item = {
                "schema_version": {"S": root_head_read.ROOT_HEAD_SCHEMA_V1},
                "root_identity_sha256": {"S": root_identity},
                "storage_binding_sha256": {"S": storage_binding},
                "key_id_sha256": {"S": key_id},
                "key_epoch": {"N": str(key_epoch)},
                "head_attestation_sha256": {"S": head_attest},
                "revoked": {"BOOL": False},
            }
            mock_dynamo = MockDynamoDBClient(valid_item)
            
            # 3. Setup IndependentRootHeadReaderV1
            dynamo_sha = ports_v2.startup_recovery_evidence_source_object_identity_sha256_v2(mock_dynamo)
            reader_config = root_head_read.IndependentRootHeadReadConfigV1(
                enabled=True,
                scope_attestation=root_head_read.INDEPENDENT_ROOT_HEAD_READ_SCOPE_V1,
                table_arn="arn:aws:dynamodb:us-east-1:123456789012:table/MyTable",
                root_identity_sha256=root_identity,
                expected_client_object_identity_sha256=dynamo_sha
            )
            reader = root_head_read.IndependentRootHeadReaderV1(reader_config, client=mock_dynamo)
            
            # 4. Create Recovery Composition
            boundary_sha = ports_v2.startup_recovery_evidence_source_object_identity_sha256_v2(boundary)
            reader_sha = ports_v2.startup_recovery_evidence_source_object_identity_sha256_v2(reader)
            
            comp_config = recovery_comp.OfflineRootHeadRecoveryConfigV1(
                enabled=True,
                scope_attestation=recovery_comp.OFFLINE_ROOT_HEAD_RECOVERY_SCOPE_V1,
                expected_boundary_object_identity_sha256=boundary_sha,
                expected_head_reader_object_identity_sha256=reader_sha
            )
            
            composition = recovery_comp.OfflineRootHeadRecoveryCompositionV1(
                config=comp_config,
                boundary=boundary,
                head_reader=reader
            )
            
            # 5. Execute Check
            permit = {
                "maintenance_epoch": hash_v2.stable_sha256_v2({"maintenance_epoch": "authenticated-boundary"}),
                "state": "QUIESCED",
                "lock_namespace_sha256": hash_v2.stable_sha256_v2({"lock_namespace": "authenticated-boundary"}),
                "registered_writer_count": 19,
                "inflight_mutations": 0,
                "shared_lock_acquired": True,
            }
            
            result = composition.check(
                maintenance_permit=permit,
                root_authority_attestation=attestation
            )
            
            self.assertTrue(result.get("offline_evidence_consistent"))
            self.assertTrue(result.get("synthetic_recovery_checked"))
            self.assertTrue(result.get("head_external_read_attempted"))
            self.assertTrue(mock_dynamo.called)

if __name__ == '__main__':
    unittest.main()
