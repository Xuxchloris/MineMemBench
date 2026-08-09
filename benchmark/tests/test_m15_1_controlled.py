from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import run_controlled_campaign as campaign  # noqa: E402

from minemembench import cli  # noqa: E402
from minemembench.core.models import HealthResponse  # noqa: E402
from minemembench.core.provenance import capture_source_provenance  # noqa: E402
from minemembench.scenarios.registry import available_scenarios, create_scenario  # noqa: E402


def _args(tmp_path: Path, scenario: str, params: dict):
    return campaign._build_parser().parse_args(
        [
            "--results-dir",
            str(tmp_path),
            "--scenario",
            scenario,
            "--seeds",
            "42,43,44",
            "--backends",
            "none,vector,mem0,letta",
            "--cell",
            json.dumps({"name": "m15-1", "params": params}),
        ]
    )


def test_m15_1_scenarios_are_registered_and_controlled_versioned() -> None:
    assert {"long_lived_memory", "failure_learning_multi"} <= set(
        available_scenarios()
    )
    lifetime = create_scenario("long_lived_memory")
    lifetime.apply_params({})
    assert cli.validate_controlled_policy(lifetime.name, lifetime.params) is None
    multi = create_scenario("failure_learning_multi")
    multi.apply_params({})
    assert cli.validate_controlled_policy(multi.name, multi.params) is None


def test_m15_1_fixture_selection_is_scenario_only() -> None:
    lifetime = create_scenario("long_lived_memory")
    lifetime.apply_params({})
    assert cli.controlled_fixture_spec(lifetime.name, lifetime.params) == (
        cli.CONTROLLED_LIFETIME_FIXTURE_SELECTOR,
        cli.CONTROLLED_LIFETIME_FIXTURE_IDENTITY,
    )
    multi = create_scenario("failure_learning_multi")
    multi.apply_params({})
    assert cli.controlled_fixture_spec(multi.name, multi.params) == (
        cli.CONTROLLED_HETEROGENEOUS_FAILURE_FIXTURE_SELECTOR,
        cli.CONTROLLED_HETEROGENEOUS_FAILURE_FIXTURE_IDENTITY,
    )
    visible_lifetime = cli.controlled_fixture_state(
        cli.CONTROLLED_LIFETIME_FIXTURE_SELECTOR
    )
    assert visible_lifetime == cli.canonical_fixture_state()
    visible_multi = cli.controlled_fixture_state(
        cli.CONTROLLED_HETEROGENEOUS_FAILURE_FIXTURE_SELECTOR
    )
    assert [entity.name for entity in visible_multi.nearby_entities] == [
        "zombie",
        "alpha_zombie",
        "alpha_creeper",
        "beta_skeleton",
        "beta_stray",
        "gamma_spider",
        "gamma_cave_spider",
    ]


@pytest.mark.asyncio
async def test_heterogeneous_fixture_gate_returns_registered_identity() -> None:
    class FixtureBot:
        async def get_state(self):
            return cli.controlled_fixture_state(
                cli.CONTROLLED_HETEROGENEOUS_FAILURE_FIXTURE_SELECTOR
            )

    health = HealthResponse(
        status="ok", mode="mock", connected=True, username="BenchBot", uptime_s=1
    )
    identity = await cli._assert_controlled_fixture(
        FixtureBot(),
        health,
        cli.CONTROLLED_HETEROGENEOUS_FAILURE_FIXTURE_SELECTOR,
    )
    assert identity == cli.CONTROLLED_HETEROGENEOUS_FAILURE_FIXTURE_IDENTITY


@pytest.mark.parametrize(
    "scenario,missing,explicit,selector",
    [
        (
            "long_lived_memory",
            {"lifetime_event_count": 8, "session_count": 2},
            {
                "lifetime_event_count": 8,
                "session_count": 2,
                "lifetime_semantics_version": "lifetime_v1",
            },
            cli.CONTROLLED_LIFETIME_FIXTURE_SELECTOR,
        ),
        (
            "failure_learning_multi",
            {"observed_failure_count": 2},
            {
                "observed_failure_count": 2,
                "failure_semantics_version": "observed_precondition_applicability_v4",
            },
            cli.CONTROLLED_HETEROGENEOUS_FAILURE_FIXTURE_SELECTOR,
        ),
    ],
)
def test_campaign_requires_explicit_m15_1_semantics_before_writes(
    tmp_path, scenario, missing, explicit, selector
) -> None:
    plan, error = campaign.prepare_campaign(_args(tmp_path, scenario, missing))
    assert plan is None
    assert error is not None and "explicitly request" in error
    assert list(tmp_path.iterdir()) == []

    plan, error = campaign.prepare_campaign(_args(tmp_path, scenario, explicit))
    assert error is None and plan is not None
    schedule = campaign.build_schedule(
        cells=plan["cells"],
        backends=plan["backends"],
        seeds=plan["seeds"],
        python="py",
        results_dir=tmp_path,
        scenario=scenario,
    )
    assert len(schedule) == 12
    assert {entry["fixture_selector"] for entry in schedule} == {selector}


def test_dashboard_static_assets_are_bound_into_source_provenance() -> None:
    provenance = capture_source_provenance()
    paths = {record.path for record in provenance.source_files}
    assert "benchmark/minemembench/dashboard/static/index.html" in paths
    assert "benchmark/minemembench/dashboard/static/app.css" in paths
    assert "benchmark/minemembench/dashboard/static/app.js" in paths


def test_dashboard_dependency_direction_is_consumer_only() -> None:
    package = Path(__file__).resolve().parents[1] / "minemembench"
    producer_roots = [
        package / "agent",
        package / "core",
        package / "memory",
        package / "scenarios",
        package / "events",
    ]
    offenders = []
    for root in producer_roots:
        for path in root.rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            if "import minemembench.dashboard" in source or "from ..dashboard" in source:
                offenders.append(path.relative_to(package).as_posix())
    assert offenders == []
