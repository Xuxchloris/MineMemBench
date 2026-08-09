"""Controlled Mode helpers: deterministic event identity for campaign runs.

In Controlled Mode a scenario's generated events must be semantically
identical across backends for a given `(seed, effective params)`: only the
isolation `episode_id` may differ. These helpers derive stable event ids and
logical timestamps from `(seed, params, phase, ordinal)` instead of
uuid4/wall-clock, so retrieval cannot respond to coordinate/timestamp/id
noise between backends (A-RESEARCH-REVIEW-004).
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any

#: Logical clock origin for Controlled Mode events (no wall-clock meaning).
CONTROLLED_EPOCH = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)

#: Phase slots for the logical clock; keeps event order monotone by phase.
_PHASE_ORDER = {"experience": 0, "interference": 1, "test": 2}


def controlled_event_identity(
    *, seed: int, params: dict[str, Any], phase: str, ordinal: int
) -> tuple[str, datetime]:
    """Stable (event_id, logical timestamp) for one generated event.

    The id is a SHA-256 over the event's semantic coordinates — seed,
    effective params, phase, and per-phase ordinal — so two campaign runs with
    the same `(seed, params)` generate identical ids and timestamps regardless
    of backend. `phase` must be one of `_PHASE_ORDER`.
    """

    key = json.dumps(
        {"seed": seed, "params": params, "phase": phase, "ordinal": ordinal},
        sort_keys=True,
    )
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    event_id = f"ctrl-{digest[:24]}"
    timestamp = CONTROLLED_EPOCH + timedelta(
        seconds=_PHASE_ORDER[phase] * 100_000 + ordinal
    )
    return event_id, timestamp
