"""CLI scenario-loop contract tests (TASK-002): the paired seed schedule and
the post-run completed-episode reset audit, exercised through
`_run_scenario_async` with hermetic fakes (no network, no real LLM API).
"""

from __future__ import annotations

import argparse
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from minemembench import cli
from minemembench.core.models import (
    BotMode,
    EventType,
    ExperienceEvent,
    HealthResponse,
    Position,
)
from minemembench.memory.base import MemoryBackend, MemoryItem, MemoryQuery, MemoryStats

from .conftest import FakeBotClient, SmartFakeLLM, make_settings


class FakeBridge(FakeBotClient):
    """FakeBotClient plus the BotClient surface the CLI loop uses."""

    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url

    async def __aenter__(self) -> FakeBridge:
        return self

    async def __aexit__(self, *exc: Any) -> bool:
        return False

    async def health(self) -> HealthResponse:
        return HealthResponse(
            status="ok",
            mode=BotMode.MOCK,
            connected=True,
            username="BenchBot",
            uptime_s=1.0,
        )

    async def iter_events(self) -> AsyncIterator[Any]:
        return
        yield  # pragma: no cover — an empty raw event stream


class RecordingBackend(MemoryBackend):
    """Scoped in-memory backend recording its reset calls and latency counters."""

    def __init__(self, *, fail_reset: bool = False) -> None:
        self._items: list[MemoryItem] = []
        self.reset_calls: list[str] = []
        self._fail_reset = fail_reset

    async def add(self, event: ExperienceEvent) -> None:
        self._items.append(
            MemoryItem(
                item_id=event.event_id,
                event=event,
                score=None,
                created_at=datetime(2026, 8, 7, 12, 0, 0, tzinfo=UTC),
            )
        )

    async def retrieve(self, query: MemoryQuery) -> list[MemoryItem]:
        return [
            item for item in self._items if item.event.episode_id == query.episode_id
        ][: query.limit]

    async def update(self, event: ExperienceEvent) -> None:
        pass

    async def reset(self, episode_id: str) -> None:
        self.reset_calls.append(episode_id)
        if self._fail_reset:
            raise RuntimeError("reset exploded")
        self._items = [
            item for item in self._items if item.event.episode_id != episode_id
        ]

    async def stats(self) -> MemoryStats:
        return MemoryStats(backend="recording", item_count=len(self._items))


def _run_args(*, runs: int, seed: int, memory: str = "recording") -> argparse.Namespace:
    return cli._build_parser().parse_args(
        [
            "run",
            "--scenario",
            "delayed_recall",
            "--memory",
            memory,
            "--runs",
            str(runs),
            "--seed",
            str(seed),
        ]
    )


@pytest.fixture()
def harness(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Patch the CLI's external boundaries; return the recording state."""

    backends: list[RecordingBackend] = []
    state: dict[str, Any] = {"fail_reset": False}

    def factory(name: str, settings: Any) -> RecordingBackend:
        backend = RecordingBackend(fail_reset=state["fail_reset"])
        backends.append(backend)
        return backend

    monkeypatch.setattr(cli, "BotClient", FakeBridge)
    monkeypatch.setattr(cli, "create_memory_backend", factory)
    monkeypatch.setattr(
        cli, "OpenAICompatibleProvider", lambda settings: SmartFakeLLM()
    )
    settings = make_settings(results_dir=str(tmp_path / "results"))
    return {
        "backends": backends,
        "state": state,
        "settings": settings,
        "results_dir": tmp_path / "results",
    }


async def test_paired_seed_schedule_42_43_44(harness) -> None:
    args = _run_args(runs=3, seed=42)
    results = await cli._run_scenario_async(args, harness["settings"], {})

    assert [result.seed for result in results] == [42, 43, 44]
    assert [result.fairness.run_seed for result in results] == [42, 43, 44]
    for result in results:
        assert result.fairness is not None
        assert result.fairness.valid is True


async def test_seed_schedule_is_identical_across_backends(harness) -> None:
    """The same base seed + run count yields the same seed schedule no matter
    which backend name the factory is asked for (paired design)."""

    first = await cli._run_scenario_async(
        _run_args(runs=3, seed=42, memory="backend-a"), harness["settings"], {}
    )
    second = await cli._run_scenario_async(
        _run_args(runs=3, seed=42, memory="backend-b"), harness["settings"], {}
    )
    assert [r.seed for r in first] == [r.seed for r in second] == [42, 43, 44]


async def test_fresh_backend_and_completed_episode_reset_per_run(harness) -> None:
    args = _run_args(runs=3, seed=42)
    results = await cli._run_scenario_async(args, harness["settings"], {})

    backends = harness["backends"]
    # One fresh backend instance per run: counters/scope never accumulate.
    assert len(backends) == 3
    assert len({id(backend) for backend in backends}) == 3

    for result, backend in zip(results, backends):
        # reset() was called on the episode that ACTUALLY ran, and the
        # post-reset probes found both the old scope and a fresh scope empty.
        assert backend.reset_calls[0] == result.episode_id
        fairness = result.fairness
        assert fairness is not None
        assert fairness.reset_episode == result.episode_id
        assert fairness.reset_performed is True
        assert fairness.post_reset_items == 0
        assert fairness.fresh_scope_items == 0
        # No cross-run contamination: each backend only ever held its own
        # episode's items, and they are gone after the audit.
        assert backend._items == []


async def test_invalid_cleanup_still_produces_an_auditable_result(harness) -> None:
    harness["state"]["fail_reset"] = True
    args = _run_args(runs=2, seed=42)
    results = await cli._run_scenario_async(args, harness["settings"], {})

    assert len(results) == 2  # the runs are not dropped
    for result in results:
        fairness = result.fairness
        assert fairness is not None
        assert fairness.valid is False
        assert fairness.reset_performed is False
        assert fairness.reset_error is not None
        assert "reset exploded" in fairness.reset_error
        assert fairness.invalid_reason is not None

    # The run logs are still written for audit, marked invalid.
    written = sorted(harness["results_dir"].glob("scenario_*.json"))
    assert len(written) == 2
    for path in written:
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["fairness"]["valid"] is False
        assert payload["fairness"]["invalid_reason"]
