"""Shared seeded geometry helpers for scenario construction.

Goal positions are derived from the same deterministic rule everywhere
(spawn + a seeded horizontal offset), keeping the only independent variable
across runs the injected memory backend. Distinct-offset generation uses a
deterministic seed bump so a higher stress level never perturbs the locations
of a shallower level.
"""

from __future__ import annotations

import random

from ..core.models import Position


def seeded_offset(spawn: Position, rng: random.Random) -> Position:
    """Spawn plus a seeded horizontal offset in [8, 20] blocks with random signs."""

    dx = rng.choice((-1, 1)) * rng.randint(8, 20)
    dz = rng.choice((-1, 1)) * rng.randint(8, 20)
    return Position(x=spawn.x + dx, y=spawn.y, z=spawn.z + dz)


def _same_xy(a: Position, b: Position) -> bool:
    """Whether two positions coincide (same x/y/z triple)."""

    return (a.x, a.y, a.z) == (b.x, b.y, b.z)


def seeded_offset_distinct(
    spawn: Position, seed: int, others: list[Position]
) -> Position:
    """A seeded offset from `spawn` distinct from every position in `others`.

    The first candidate comes from `random.Random(seed)`; on a collision the
    seed is bumped deterministically (`seed + 10_000 * bump`), so the result
    is reproducible across processes.
    """

    candidate = seeded_offset(spawn, random.Random(seed))
    bump = 1
    while any(_same_xy(candidate, other) for other in others) and bump < 1000:
        candidate = seeded_offset(spawn, random.Random(seed + 10_000 * bump))
        bump += 1
    return candidate
