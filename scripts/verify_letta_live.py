"""M15A live verification: drive the real LettaBackend against a running server.

This is an OPT-IN script, never a pytest test. It touches the network only to
reach the configured Letta server, so the pytest suite stays fully offline. It
starts/stops nothing.

Usage:
    .venv/Scripts/python scripts/verify_letta_live.py
    .venv/Scripts/python scripts/verify_letta_live.py --require-live

Flow:
  1. Read config from the repo .env via `Settings` (LETTA_BASE_URL, ...).
  2. If the Letta server is unreachable, print a clear SKIP message and exit 0
     (offline machines and the pytest suite are unaffected). With
     `--require-live` (strict acceptance mode, used by QA) an unavailable
     server exits NON-ZERO instead: acceptance cannot silently skip.
  3. Otherwise run three checks through the MemoryBackend interface with a real
     (non-injected) LettaBackend:
       A. add() an ExperienceEvent stating the target chest is at location A,
          then retrieve() and assert the server round-trips the EXACT event —
          event_id, event_type, actor, target, context, and outcome all equal
          to what was written (the passage-tag payload, no process-local
          side channel).
       B. update() the same event to say the chest moved to location B, then
          retrieve() and assert the result is the exact NEW event and no
          retrieved item still carries the stale location-A outcome.
       C. reset() the episode, then retrieve() and assert the old episode's
          memory cannot pollute a fresh episode.
  Each check prints PASS/FAIL; the script exits non-zero if any check fails.

Every run uses fresh, unique episode ids and performs best-effort cleanup, so
it can be re-run safely against a long-lived server.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import uuid
from datetime import UTC, datetime

import httpx

from minemembench.core.config import Settings
from minemembench.core.models import EventType, ExperienceEvent, Position
from minemembench.memory.base import MemoryItem, MemoryQuery
from minemembench.memory.letta_adapter import LettaBackend

#: How long to wait for a health probe / backend call before giving up.
_TIMEOUT_S = 10.0

_failures: list[str] = []


def _exclude_loopback_proxies() -> None:
    """Keep both the health client and Letta SDK on the local Docker route."""

    existing = os.environ.get("NO_PROXY") or os.environ.get("no_proxy") or ""
    entries = [entry.strip() for entry in existing.split(",") if entry.strip()]
    for loopback in ("localhost", "127.0.0.1"):
        if loopback not in entries:
            entries.append(loopback)
    value = ",".join(entries)
    os.environ["NO_PROXY"] = value
    os.environ["no_proxy"] = value


def _mark(label: str, ok: bool, detail: str = "") -> None:
    """Print PASS/FAIL for one check and record failures."""
    status = "PASS" if ok else "FAIL"
    suffix = f"  {detail}" if detail else ""
    print(f"{status}  {label}{suffix}")
    if not ok:
        _failures.append(label)


async def _server_available(base_url: str) -> str | None:
    """Return the server version if reachable, else None."""
    url = base_url.rstrip("/") + "/v1/health/"
    try:
        # A system proxy must never intercept this loopback-only acceptance
        # probe (the benchmark's planner provider follows the same rule).
        async with httpx.AsyncClient(timeout=_TIMEOUT_S, trust_env=False) as client:
            response = await client.get(url)
        if response.status_code == 200:
            data = response.json()
            return str(data.get("version", "unknown"))
    except (httpx.HTTPError, ValueError):
        return None
    return None


def _event(event_id: str, episode_id: str, outcome: str) -> ExperienceEvent:
    """A WORLD_FACT_UPDATED event: the target chest's current location.

    Carries a non-null `location` so the live round-trip check exercises every
    field of the model, not only the scalar ones.
    """
    return ExperienceEvent(
        event_id=event_id,
        episode_id=episode_id,
        timestamp=datetime(2026, 8, 8, 12, 0, 0, tzinfo=UTC),
        actor="agent",
        target="chest",
        event_type=EventType.WORLD_FACT_UPDATED,
        location=Position(x=10.0, y=64.0, z=20.0),
        context={"target": "chest"},
        outcome=outcome,
    )


def _first_with_item_id(items: list[MemoryItem], event_id: str) -> MemoryItem | None:
    """The first retrieved memory carrying `event_id`, or None."""
    for item in items:
        if item.item_id == event_id:
            return item
    return None


def _event_identity_mismatches(
    expected: ExperienceEvent, actual: ExperienceEvent
) -> list[str]:
    """Field-by-field differences between the written and reconstructed event.

    The semantic round-trip must be exact for the COMPLETE ExperienceEvent —
    every model field, including `timestamp`, `location`, and `raw_events` —
    so no information loss in any field can hide behind a partial comparison.
    """
    mismatches: list[str] = []
    for field in type(expected).model_fields:
        expected_value = getattr(expected, field)
        actual_value = getattr(actual, field)
        if expected_value != actual_value:
            mismatches.append(f"{field}: {actual_value!r} != {expected_value!r}")
    return mismatches


async def check_a(backend: LettaBackend, episode_id: str) -> None:
    """add() a fact, then retrieve() the EXACT same event back from the server."""
    event = _event("verify-a", episode_id, "the target chest is at location A (10, 64, 20)")
    await backend.add(event)
    items = await backend.retrieve(
        MemoryQuery(query_text="where is the target chest", episode_id=episode_id)
    )
    if not items:
        _mark("A: add then retrieve round-trips the exact event", False,
              "retrieval returned nothing")
        return
    best = _first_with_item_id(items, event.event_id)
    if best is None:
        detail = "returned items: " + ", ".join(i.item_id for i in items)
        _mark("A: add then retrieve round-trips the exact event", False, detail)
        return
    mismatches = _event_identity_mismatches(event, best.event)
    _mark(
        "A: add then retrieve round-trips the exact event",
        not mismatches,
        "; ".join(mismatches) if mismatches else "complete ExperienceEvent equal",
    )


async def check_b(backend: LettaBackend, episode_id: str) -> None:
    """update() a fact, then assert retrieval returns the exact NEW event.

    Belief update: check_a has already stored this event (event_id `verify-a`,
    location A). update() must replace that passage in place, never append, so
    retrieval afterwards reflects location B and no longer location A.
    """
    new = _event("verify-a", episode_id, "the target chest is at location B (40, 64, 80)")
    await backend.update(new)

    items = await backend.retrieve(
        MemoryQuery(query_text="where is the target chest", episode_id=episode_id)
    )
    best = _first_with_item_id(items, new.event_id)
    if best is None:
        _mark("B: update round-trips the exact new event", False,
              "event not found after update")
        return
    mismatches = _event_identity_mismatches(new, best.event)
    stale = [i.item_id for i in items if i.event.outcome and "location A" in i.event.outcome]
    ok = not mismatches and not stale
    detail = "; ".join(mismatches) if mismatches else "complete ExperienceEvent equal"
    detail += f"; stale location-A items: {stale or 'none'}"
    _mark("B: update round-trips the exact new event", ok, detail)


async def check_c(backend: LettaBackend, episode_id: str, fresh_episode_id: str) -> None:
    """reset() an episode, then assert no leakage into a fresh episode."""
    await backend.add(_event("verify-c", episode_id, "the target chest is at location A (10, 64, 20)"))
    await backend.reset(episode_id)

    old_episode = await backend.retrieve(
        MemoryQuery(query_text="where is the target chest", episode_id=episode_id)
    )
    fresh_episode = await backend.retrieve(
        MemoryQuery(query_text="where is the target chest", episode_id=fresh_episode_id)
    )
    ok = not old_episode and not fresh_episode
    detail = (
        f"reset episode retrieval: {len(old_episode)} item(s), "
        f"fresh episode retrieval: {len(fresh_episode)} item(s)"
    )
    _mark("C: reset isolates the old episode from a fresh one", ok, detail)


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--require-live",
        action="store_true",
        help=(
            "Strict acceptance mode: exit non-zero when the Letta server is "
            "unavailable instead of skipping. QA/acceptance runs must use this."
        ),
    )
    args = parser.parse_args(argv)

    _exclude_loopback_proxies()

    settings = Settings()
    base_url = settings.letta_base_url

    version = await _server_available(base_url)
    if version is None:
        print(
            f"SKIP: letta server not reachable at {base_url!r} "
            f"(offline or not started) - nothing to verify"
        )
        if args.require_live:
            print("FAIL: --require-live set; an unavailable server cannot pass")
            return 2
        return 0
    print(f"letta server: {base_url} version={version}")

    # Fresh episode ids per run so stale state from earlier runs can never
    # satisfy the checks.
    episode_id = f"verify-{uuid.uuid4().hex}"
    fresh_episode_id = f"verify-fresh-{uuid.uuid4().hex}"

    backend = LettaBackend(settings=settings)
    try:
        await check_a(backend, episode_id)
        await check_b(backend, episode_id)
        await check_c(backend, episode_id, fresh_episode_id)
    finally:
        # Best-effort cleanup: never leave test agents behind on the server.
        for target in (episode_id, fresh_episode_id):
            try:
                await backend.reset(target)
            except Exception:  # noqa: BLE001 - cleanup must not fail the script
                pass

    if _failures:
        print(f"FAIL: {len(_failures)} check(s) failed")
        return 1
    print("PASS: M15A live verification")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
