"""Benchmark scenarios (M7): reproducible, seeded episodes with distinct
phases (setup -> experience -> interference -> test -> evaluate)."""

from __future__ import annotations

from .base import PhaseRecord, Scenario, ScenarioContext, ScenarioResult
from .registry import (
    ScenarioRegistryError,
    available_scenarios,
    create_scenario,
)

__all__ = [
    "PhaseRecord",
    "Scenario",
    "ScenarioContext",
    "ScenarioResult",
    "ScenarioRegistryError",
    "available_scenarios",
    "create_scenario",
]
