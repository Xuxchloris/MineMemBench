"""Hermetic tests for TASK-024 producer-source provenance."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from minemembench.core.fairness import FairnessRecord
from minemembench.core.provenance import capture_source_provenance


def _tree(tmp_path: Path) -> tuple[tuple[str, ...], tuple[str, ...]]:
    (tmp_path / "src" / "nested").mkdir(parents=True)
    (tmp_path / "anchor.txt").write_text("anchor\n", encoding="utf-8")
    (tmp_path / "src" / "z.py").write_text("Z = 1\n", encoding="utf-8")
    (tmp_path / "src" / "nested" / "a.py").write_text(
        "A = 1\n", encoding="utf-8"
    )
    return ("src/**/*.py",), ("anchor.txt",)


def test_fingerprint_is_deterministic_sorted_and_git_unavailable(tmp_path) -> None:
    globs, required = _tree(tmp_path)

    first = capture_source_provenance(
        tmp_path, globs=globs, required_files=required
    )
    second = capture_source_provenance(
        tmp_path, globs=tuple(reversed(globs)), required_files=required
    )

    assert first.source_tree_fingerprint == second.source_tree_fingerprint
    assert [item.path for item in first.source_files] == [
        "anchor.txt",
        "src/nested/a.py",
        "src/z.py",
    ]
    assert first.source_file_count == 3
    assert first.git_available is False
    assert first.git_commit is None
    assert first.git_dirty is None
    assert first.git_status_fingerprint is None


def test_fingerprint_changes_for_one_byte_or_file_set_mutation(tmp_path) -> None:
    globs, required = _tree(tmp_path)
    before = capture_source_provenance(
        tmp_path, globs=globs, required_files=required
    )

    (tmp_path / "src" / "z.py").write_text("Z = 2\n", encoding="utf-8")
    content_changed = capture_source_provenance(
        tmp_path, globs=globs, required_files=required
    )
    assert content_changed.source_tree_fingerprint != before.source_tree_fingerprint

    (tmp_path / "src" / "new.py").write_text("NEW = True\n", encoding="utf-8")
    file_set_changed = capture_source_provenance(
        tmp_path, globs=globs, required_files=required
    )
    assert file_set_changed.source_tree_fingerprint != content_changed.source_tree_fingerprint
    assert file_set_changed.source_file_count == before.source_file_count + 1


def test_missing_anchor_and_forbidden_paths_fail_closed(tmp_path) -> None:
    with pytest.raises(FileNotFoundError, match="required provenance input"):
        capture_source_provenance(
            tmp_path, globs=(), required_files=("missing.txt",)
        )

    (tmp_path / ".env").write_text("SECRET=never-read\n", encoding="utf-8")
    with pytest.raises(ValueError, match="forbidden provenance path"):
        capture_source_provenance(
            tmp_path, globs=(), required_files=(".env",)
        )

    (tmp_path / "results").mkdir()
    (tmp_path / "results" / "evidence.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="allowlist glob reached forbidden"):
        capture_source_provenance(
            tmp_path,
            globs=("results/**/*.json",),
            required_files=(),
        )


def test_resolved_directory_alias_cannot_tunnel_into_forbidden_tree(
    tmp_path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "results").mkdir()
    (tmp_path / "anchor.txt").write_text("anchor", encoding="utf-8")
    (tmp_path / "results" / "hidden.py").write_text(
        "SECRET = 'runtime-data'\n", encoding="utf-8"
    )
    alias = tmp_path / "src" / "alias"
    if os.name == "nt":
        created = subprocess.run(
            [
                "cmd.exe",
                "/d",
                "/c",
                "mklink",
                "/J",
                str(alias),
                str(tmp_path / "results"),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if created.returncode != 0:
            pytest.skip(f"cannot create test junction: {created.stderr}")
    else:
        alias.symlink_to(tmp_path / "results", target_is_directory=True)

    with pytest.raises(ValueError, match="resolved provenance input reaches forbidden"):
        capture_source_provenance(
            tmp_path,
            globs=(),
            required_files=("anchor.txt", "src/alias/hidden.py"),
        )

def test_old_fairness_json_without_provenance_still_loads() -> None:
    legacy = FairnessRecord.model_validate(
        {
            "checked_at": datetime(2026, 1, 1, tzinfo=UTC).isoformat(),
            "minecraft_version": "unknown",
            "world_seed": None,
            "planner_model": "model",
            "temperature": 0.0,
            "system_prompt_hash": "a" * 64,
            "tool_set_hash": "b" * 64,
            "scenario": "delayed_recall",
        }
    )
    assert legacy.source_tree_fingerprint is None
    assert legacy.source_file_count is None
    assert legacy.git_available is None
    assert legacy.git_dirty is None


def test_current_repo_provenance_never_includes_forbidden_inputs() -> None:
    provenance = capture_source_provenance()
    paths = {item.path for item in provenance.source_files}
    assert "docs/protocol.md" in paths
    assert "scripts/run_controlled_campaign.py" in paths
    assert "scripts/verify_source_freeze.py" in paths
    assert "pyproject.toml" in paths
    assert ".env" not in paths
    assert not any("results" in Path(path).parts for path in paths)
    assert not any("__pycache__" in Path(path).parts for path in paths)
    assert provenance.source_file_count == len(provenance.source_files)
    assert len(provenance.source_tree_fingerprint) == 64


def test_provenance_serialization_is_json_safe(tmp_path) -> None:
    globs, required = _tree(tmp_path)
    provenance = capture_source_provenance(
        tmp_path, globs=globs, required_files=required
    )
    encoded = json.dumps(provenance.model_dump(mode="json"), sort_keys=True)
    decoded = json.loads(encoded)
    assert decoded["schema_version"] == "minemembench-source/v1"
    assert decoded["source_file_count"] == 3
