"""Tests for the core id helpers."""

from __future__ import annotations

import string

from minemembench.core.ids import new_event_id, new_run_id


def test_run_id_shape() -> None:
    run_id = new_run_id()
    assert set(run_id) <= set(string.hexdigits)
    assert run_id == run_id.lower()
    assert len(run_id) == 32


def test_event_id_shape() -> None:
    event_id = new_event_id()
    assert set(event_id) <= set(string.hexdigits)
    assert event_id == event_id.lower()
    assert len(event_id) == 32


def test_run_ids_are_unique_across_calls() -> None:
    ids = {new_run_id() for _ in range(100)}
    assert len(ids) == 100


def test_event_ids_are_unique_across_calls() -> None:
    ids = {new_event_id() for _ in range(100)}
    assert len(ids) == 100
