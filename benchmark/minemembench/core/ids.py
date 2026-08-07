"""Small id helpers used across the benchmark.

Run ids identify a single benchmark run and are used to build results file
names; event ids uniquely identify ExperienceEvent records so the memory
layer can deduplicate them. Both are raw uuid4 hex strings (no dashes).
"""

from __future__ import annotations

from uuid import uuid4


def new_run_id() -> str:
    """Return a fresh run id (uuid4 hex, 32 chars, no dashes)."""
    return uuid4().hex


def new_event_id() -> str:
    """Return a fresh event id (uuid4 hex, 32 chars, no dashes)."""
    return uuid4().hex
