import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import trade_registry_closed_identity_conflict_repair_runtime_production_startup_port_binding_adapter_contract_v1 as ports_v1
from c3_runtime_dependency_assembly_offline_v1 import SyntheticAssemblyDependenciesV1, assemble_c3_dependencies_offline_v1

class MockLock:
    def acquire(self): pass
    def __enter__(self): return self
    def __exit__(self, exc_type, exc_val, exc_tb): pass

class MockStore:
    def read(self): pass
    def write(self, data): pass

class MockProvider:
    def read_current_root_authority_v2(self): pass

class MockVerifier:
    def verify_root_authority_signature_v2(self): pass

class MockRevocation:
    def root_authority_key_revoked_v2(self): pass

class MockRecovery:
    def recover_multistore_v2(self): pass

def dummy_callback(*args, **kwargs):
    pass

def main():
    ports = ports_v1.RuntimeProductionStartupPortsV1(
        atomic_lock=MockLock(),
        trading_controls=dummy_callback,
        startup_state=dummy_callback,
        seam_binding_evidence=dummy_callback,
        maintenance_completion_evidence=dummy_callback,
        production_evidence_verifier=dummy_callback,
        startup_callback=dummy_callback,
        synthetic_only=True,
        runtime_integrated=False,
        authority_root_sha256=None
    )

    deps = SyntheticAssemblyDependenciesV1(
        ports=ports,
        lock_backend=MockLock(),
        lease_store=MockStore(),
        clock=dummy_callback,
        nonce_source=dummy_callback,
        root_state_provider=MockProvider(),
        root_authority_verifier=MockVerifier(),
        root_revocation_source=MockRevocation(),
        multistore_recovery=MockRecovery(),
        startup_bridge=dummy_callback,
        synthetic_only=True
    )

    assembly = assemble_c3_dependencies_offline_v1(deps)
    snapshot = assembly.snapshot()
    
    print("--- ETAPA 4: DORMANT OFFLINE ASSEMBLY SNAPSHOT ---")
    import json
    print(json.dumps(snapshot, indent=2))
    
    assert snapshot["ok"] is True, "Assembly snapshot failed!"
    assert snapshot["status"] == "C3_OFFLINE_ASSEMBLY_BOUND_DORMANT"
    print("\nSUCCESS: All components successfully bound offline in dormant state.")

if __name__ == "__main__":
    main()

