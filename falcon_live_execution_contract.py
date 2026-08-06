"""Neutral contract for Falcon's single LIVE execution path.

This module intentionally has no operational imports, I/O, or side effects.
Both the Falcon producer and Central's redundant bridge consume this one
canonical marker so a missing or incompatible contract fails closed.
"""

FALCON_SINGLE_LIVE_EXECUTION_PATH_VERSION = (
    "2026-08-03-FALCON-SINGLE-LIVE-EXECUTION-PATH-V1"
)
