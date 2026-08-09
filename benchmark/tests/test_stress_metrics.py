"""M15B stress metric-math tests: the pure metric functions of the stress
scenarios, exercised with hand-crafted MemoryItems (no network, no LLM)."""

from __future__ import annotations

from datetime import UTC, datetime

from minemembench.core.models import EventType, ExperienceEvent, Position
from minemembench.memory.base import MemoryItem
from minemembench.scenarios.delayed_recall import compute_recall_metrics
from minemembench.scenarios.world_update import compute_update_metrics

NOW = datetime(2026, 8, 7, 12, 0, 0, tzinfo=UTC)


def _item(
    event_id: str,
    subject: str,
    *,
    x: float | None = None,
    y: float | None = None,
    z: float | None = None,
    **extra,
) -> MemoryItem:
    context: dict = {"subject": subject}
    if x is not None:
        context.update({"x": x, "y": y, "z": z})
    context.update(extra)
    return MemoryItem(
        item_id=event_id,
        event=ExperienceEvent(
            event_id=event_id,
            episode_id="ep",
            timestamp=NOW,
            actor="test",
            event_type=EventType.WORLD_FACT_UPDATED,
            context=context,
        ),
        score=None,
        created_at=NOW,
    )


# --- delayed_recall metric math (id-based ground truth) ----------------------


def test_recall_metrics_with_correct_fact_present() -> None:
    items = [
        _item("correct", "target_chest", x=10.0, y=64.0, z=20.0),
        _item("wrong", "target_chest", x=30.0, y=64.0, z=40.0),
        _item("other", "blue_chest", x=5.0, y=64.0, z=9.0),
        _item("noise", "world", fact="rain"),
    ]
    metrics = compute_recall_metrics(items, "correct", {"wrong"})
    assert metrics["fact_retrieval_rank"] == 1
    assert metrics["recall_accuracy"] == 1
    assert metrics["wrong_fact_rate"] == 0.25  # 1 wrong / 4 retrieved
    assert metrics["retrieval_precision"] == 0.5  # 2 about target / 4 retrieved


def test_recall_metrics_work_with_text_shaped_events() -> None:
    """Ids drive the metrics even when a backend reconstructs only a
    text-shaped event (no structured context) — e.g. a passage without an
    event payload. Ground truth never parses backend-specific context."""

    def text_item(event_id: str, text: str) -> MemoryItem:
        return MemoryItem(
            item_id=event_id,
            event=ExperienceEvent(
                event_id=event_id,
                episode_id="ep",
                timestamp=NOW,
                actor="letta",
                event_type=EventType.WORLD_FACT_UPDATED,
                context={"text": text},
            ),
            score=None,
            created_at=NOW,
        )

    items = [
        text_item("noise", "world fact rain"),
        text_item("correct", "target chest at 10 64 20"),
        text_item("wrong", "target chest at 30 64 40"),
    ]
    metrics = compute_recall_metrics(items, "correct", {"wrong"})
    assert metrics["fact_retrieval_rank"] == 2
    assert metrics["recall_accuracy"] == 1
    assert metrics["wrong_fact_rate"] == round(1 / 3, 4)
    assert metrics["retrieval_precision"] == round(2 / 3, 4)


def test_recall_metrics_without_correct_fact() -> None:
    items = [
        _item("wrong", "target_chest", x=30.0, y=64.0, z=40.0),
        _item("noise", "world", fact="rain"),
    ]
    metrics = compute_recall_metrics(items, "correct", {"wrong"})
    assert metrics["recall_accuracy"] == 0
    assert metrics["wrong_fact_rate"] == 0.5
    assert metrics["retrieval_precision"] == 0.5


def test_recall_metrics_rank_skips_irrelevant_items() -> None:
    items = [
        _item("noise", "world", fact="rain"),
        _item("correct", "target_chest", x=10.0, y=64.0, z=20.0),
    ]
    metrics = compute_recall_metrics(items, "correct", set())
    assert metrics["fact_retrieval_rank"] == 2
    assert metrics["recall_accuracy"] == 1


def test_recall_metrics_rank_is_the_correct_fact_not_a_wrong_lookalike() -> None:
    """A wrong lookalike at rank 1 must not pull the reported rank forward:
    the rank belongs to the correct fact alone."""

    items = [
        _item("wrong", "target_chest", x=30.0, y=64.0, z=40.0),
        _item("correct", "target_chest", x=10.0, y=64.0, z=20.0),
    ]
    metrics = compute_recall_metrics(items, "correct", {"wrong"})
    assert metrics["fact_retrieval_rank"] == 2
    assert metrics["recall_accuracy"] == 1
    assert metrics["wrong_fact_rate"] == 0.5
    assert metrics["retrieval_precision"] == 1.0


def test_recall_metrics_wrong_only_is_rank_na_and_measured_miss() -> None:
    """Wrong lookalikes present but the correct fact absent: rank is N/A and
    recall is a measured 0 — the backend surfaced only wrong facts."""

    items = [
        _item("wrong", "target_chest", x=30.0, y=64.0, z=40.0),
        _item("noise", "world", fact="rain"),
    ]
    metrics = compute_recall_metrics(items, "correct", {"wrong"})
    assert metrics["fact_retrieval_rank"] is None
    assert metrics["recall_accuracy"] == 0
    assert metrics["wrong_fact_rate"] == 0.5
    assert metrics["retrieval_precision"] == 0.5


def test_recall_metrics_empty_retrieval_is_a_measured_miss() -> None:
    metrics = compute_recall_metrics([], "correct", {"wrong"})
    assert metrics == {
        "fact_retrieval_rank": None,
        "recall_accuracy": 0,  # empty retrieval is a measured miss, not N/A
        "wrong_fact_rate": None,  # undefined without retrieved items -> N/A
        "retrieval_precision": None,
    }


# --- world_update metric math -----------------------------------------------


def test_update_metrics_stale_top_ranked() -> None:
    current = Position(x=40.0, y=64.0, z=40.0)
    stale = [Position(x=10.0, y=64.0, z=20.0)]
    items = [
        _item("a", "supply_cache", x=10.0, y=64.0, z=20.0),
        _item("b", "supply_cache", x=40.0, y=64.0, z=40.0),
        _item("noise", "world", fact="rain"),
    ]
    metrics = compute_update_metrics(items, current, stale)
    assert metrics["current_fact_accuracy"] == 0  # top item is stale A
    assert metrics["stale_memory_rate"] == 0.5  # 1 stale / 2 cache facts
    assert metrics["obsolete_fact_retrieval_rate"] == round(1 / 3, 4)


def test_update_metrics_current_top_ranked() -> None:
    current = Position(x=40.0, y=64.0, z=40.0)
    stale = [Position(x=10.0, y=64.0, z=20.0)]
    items = [
        _item("b", "supply_cache", x=40.0, y=64.0, z=40.0),
        _item("a", "supply_cache", x=10.0, y=64.0, z=20.0),
    ]
    metrics = compute_update_metrics(items, current, stale)
    assert metrics["current_fact_accuracy"] == 1
    assert metrics["stale_memory_rate"] == 0.5
    assert metrics["obsolete_fact_retrieval_rate"] == 0.5


def test_update_metrics_deep_chain_intermediate_is_stale() -> None:
    current = Position(x=40.0, y=64.0, z=40.0)
    stale = [Position(x=10.0, y=64.0, z=20.0), Position(x=25.0, y=64.0, z=30.0)]
    items = [
        _item("c", "supply_cache", x=25.0, y=64.0, z=30.0),
        _item("d", "supply_cache", x=40.0, y=64.0, z=40.0),
    ]
    metrics = compute_update_metrics(items, current, stale)
    assert metrics["current_fact_accuracy"] == 0  # intermediate C is still stale
    assert metrics["stale_memory_rate"] == 0.5


def test_update_metrics_no_cache_facts_retrieved() -> None:
    current = Position(x=40.0, y=64.0, z=40.0)
    stale = [Position(x=10.0, y=64.0, z=20.0)]
    items = [_item("noise", "world", fact="rain")]
    metrics = compute_update_metrics(items, current, stale)
    assert metrics["current_fact_accuracy"] is None
    assert metrics["stale_memory_rate"] is None
    assert metrics["obsolete_fact_retrieval_rate"] == 0.0


def test_update_metrics_empty_retrieval_is_none() -> None:
    metrics = compute_update_metrics([], Position(x=1.0, y=64.0, z=1.0), [])
    assert metrics == {
        "current_fact_accuracy": None,
        "stale_memory_rate": None,
        "obsolete_fact_retrieval_rate": None,
    }
