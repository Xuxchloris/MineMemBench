"""Name -> factory registry for benchmark scenarios (M7).

New scenarios subclass `Scenario` and register a factory here; they become
selectable via `--scenario`. The scenario harness never branches on scenario
names beyond this registry.
"""

from __future__ import annotations

from .base import Scenario
from .delayed_recall import DelayedRecallScenario
from .failure_learning import FailureLearningScenario
from .world_update import WorldUpdateScenario


class ScenarioRegistryError(Exception):
    """Raised when an unknown scenario name is requested."""


_SCENARIOS: dict[str, type[Scenario]] = {
    DelayedRecallScenario.name: DelayedRecallScenario,
    WorldUpdateScenario.name: WorldUpdateScenario,
    FailureLearningScenario.name: FailureLearningScenario,
}


def available_scenarios() -> list[str]:
    """Names of all registered scenarios, sorted."""

    return sorted(_SCENARIOS)


def create_scenario(name: str) -> Scenario:
    """Instantiate the scenario registered under `name`."""

    try:
        cls = _SCENARIOS[name]
    except KeyError:
        available = ", ".join(available_scenarios())
        raise ScenarioRegistryError(
            f"unknown scenario {name!r}. Available now: {available}."
        ) from None
    return cls()
