"""Standard-library, no-network checks for the independent root-head candidate."""

import socket
import unittest
from unittest.mock import patch


def _blocked_network(*_args, **_kwargs):
    raise AssertionError("NETWORK_FORBIDDEN_IN_C3_HEAD_TEST")


with patch.object(socket, "socket", side_effect=_blocked_network), patch.object(
    socket, "create_connection", side_effect=_blocked_network
):
    import trade_registry_c3_independent_root_head_read_offline_v1 as head_v1
    from trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_source_ports_contract_v2 import (
        startup_recovery_evidence_source_object_identity_sha256_v2,
    )


ROOT = "a" * 64
STORAGE = "b" * 64
KEY = "c" * 64
HEAD = "d" * 64
TABLE = "arn:aws:dynamodb:us-west-2:899845009758:table/c3-synthetic-head"


def item(**changes):
    values = {
        "schema_version": {"S": head_v1.ROOT_HEAD_SCHEMA_V1},
        "root_identity_sha256": {"S": ROOT},
        "storage_binding_sha256": {"S": STORAGE},
        "key_id_sha256": {"S": KEY},
        "key_epoch": {"N": "2"},
        "head_attestation_sha256": {"S": HEAD},
        "revoked": {"BOOL": False},
    }
    values.update(changes)
    return values


class FakeDynamoClient:
    _DEFAULT = object()

    def __init__(self, response=_DEFAULT, error=None):
        self.response = {"Item": item()} if response is self._DEFAULT else response
        self.error = error
        self.calls = []

    def get_item(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response


def reader(client, **changes):
    config = {
        "enabled": True,
        "scope_attestation": head_v1.INDEPENDENT_ROOT_HEAD_READ_SCOPE_V1,
        "table_arn": TABLE,
        "root_identity_sha256": ROOT,
        "expected_client_object_identity_sha256": (
            startup_recovery_evidence_source_object_identity_sha256_v2(client)
        ),
    }
    config.update(changes)
    return head_v1.IndependentRootHeadReaderV1(
        head_v1.IndependentRootHeadReadConfigV1(**config), client=client
    )


def check(candidate, **changes):
    fields = {
        "storage_binding_sha256": STORAGE,
        "key_id_sha256": KEY,
        "key_epoch": 2,
        "attestation_sha256": HEAD,
    }
    fields.update(changes)
    return candidate.check_head(**fields)


class IndependentRootHeadReadTests(unittest.TestCase):
    def setUp(self):
        self.socket_patch = patch.object(socket, "socket", side_effect=_blocked_network)
        self.connection_patch = patch.object(
            socket, "create_connection", side_effect=_blocked_network
        )
        self.socket_patch.start()
        self.connection_patch.start()
        self.addCleanup(self.connection_patch.stop)
        self.addCleanup(self.socket_patch.stop)

    def test_default_off_never_calls_client(self):
        client = FakeDynamoClient()
        candidate = head_v1.IndependentRootHeadReaderV1(client=client)
        result = check(candidate)
        self.assertFalse(result["head_matches"])
        self.assertFalse(result["admission_allowed"])
        self.assertFalse(result["production_ready"])
        self.assertEqual(client.calls, [])

    def test_matching_head_uses_exact_table_and_strong_read_but_never_admits(self):
        client = FakeDynamoClient()
        result = check(reader(client))
        self.assertTrue(result["head_matches"])
        self.assertEqual(result["reason"], "ROOT_HEAD_MATCHED_OFFLINE")
        self.assertFalse(result["admission_allowed"])
        self.assertFalse(result["production_ready"])
        self.assertFalse(result["live_allowed"])
        self.assertEqual(client.calls, [{
            "TableName": TABLE,
            "Key": {"root_identity_sha256": {"S": ROOT}},
            "ConsistentRead": True,
            "ReturnConsumedCapacity": "NONE",
        }])

    def test_stale_revoked_or_malformed_head_fails_closed(self):
        changes = [
            {"root_identity_sha256": {"S": "e" * 64}},
            {"storage_binding_sha256": {"S": "e" * 64}},
            {"key_id_sha256": {"S": "e" * 64}},
            {"key_epoch": {"N": "1"}},
            {"key_epoch": {"N": "02"}},
            {"head_attestation_sha256": {"S": "e" * 64}},
            {"revoked": {"BOOL": True}},
            {"revoked": {"S": "false"}},
            {"schema_version": {"S": "unknown"}},
            {"unexpected": {"S": "value"}},
        ]
        for changed_item in changes:
            with self.subTest(changed_item=changed_item):
                client = FakeDynamoClient(response={"Item": item(**changed_item)})
                result = check(reader(client))
                self.assertFalse(result["head_matches"])
                self.assertFalse(result["admission_allowed"])
                self.assertTrue(result["external_read_attempted"])

    def test_missing_or_ambiguous_response_fails_closed(self):
        for response in ({}, {"Item": {}}, {"Item": None}, None):
            with self.subTest(response=response):
                client = FakeDynamoClient(response=response)
                result = check(reader(client))
                self.assertFalse(result["head_matches"])
                self.assertFalse(result["admission_allowed"])

    def test_timeout_fails_closed_without_retry(self):
        client = FakeDynamoClient(error=TimeoutError("synthetic timeout"))
        result = check(reader(client))
        self.assertEqual(result["reason"], "ROOT_HEAD_READ_FAILED")
        self.assertFalse(result["head_matches"])
        self.assertFalse(result["admission_allowed"])
        self.assertEqual(len(client.calls), 1)

    def test_swapped_client_is_rejected_before_read(self):
        first = FakeDynamoClient()
        second = FakeDynamoClient()
        candidate = reader(first)
        candidate._client = second
        result = check(candidate)
        self.assertEqual(result["reason"], "ROOT_HEAD_READER_CLIENT_MISMATCH")
        self.assertEqual(first.calls, [])
        self.assertEqual(second.calls, [])

    def test_invalid_config_is_rejected_before_read(self):
        for change in (
            {"table_arn": "c3-synthetic-head"},
            {"root_identity_sha256": "not-a-hash"},
            {"scope_attestation": "wrong"},
        ):
            with self.subTest(change=change):
                client = FakeDynamoClient()
                result = check(reader(client, **change))
                self.assertFalse(result["head_matches"])
                self.assertEqual(client.calls, [])

    def test_invalid_request_is_rejected_before_read(self):
        for change in (
            {"storage_binding_sha256": "bad"},
            {"key_id_sha256": "bad"},
            {"key_epoch": True},
            {"key_epoch": 0},
            {"attestation_sha256": "bad"},
        ):
            with self.subTest(change=change):
                client = FakeDynamoClient()
                result = check(reader(client), **change)
                self.assertFalse(result["head_matches"])
                self.assertEqual(client.calls, [])


if __name__ == "__main__":
    unittest.main()
