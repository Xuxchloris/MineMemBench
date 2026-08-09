"""Hermetic tests for TASK-025 read-only source-freeze preflight."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import verify_source_freeze as verifier  # noqa: E402

from minemembench.core.provenance import (  # noqa: E402
    SourceFileDigest,
    SourceProvenance,
    capture_source_provenance,
    source_freeze_error,
)


def _provenance(*, available: bool = True, dirty: bool | None = False) -> SourceProvenance:
    return SourceProvenance(
        source_tree_fingerprint="a" * 64,
        source_file_count=1,
        source_files=(
            SourceFileDigest(path="source.py", size=1, sha256="d" * 64),
        ),
        git_available=available,
        git_commit="b" * 40 if available else None,
        git_dirty=dirty if available else None,
        git_status_fingerprint="c" * 64 if available else None,
    )


def test_shared_source_freeze_validator_distinguishes_failures() -> None:
    clean = _provenance()
    assert source_freeze_error(clean, require_clean=True) is None
    assert "source fingerprint mismatch" in source_freeze_error(
        clean, expected_source_fingerprint="e" * 64
    )
    assert "git commit mismatch" in source_freeze_error(
        clean, expected_git_commit="f" * 40
    )
    assert source_freeze_error(_provenance(dirty=True), require_clean=True) == (
        "the git worktree is dirty"
    )
    assert source_freeze_error(_provenance(available=False), require_clean=True) == (
        "git provenance is unavailable"
    )


def test_verifier_disables_bytecode_cache_writes() -> None:
    assert verifier.sys.dont_write_bytecode is True


def test_diagnostic_cli_reports_dirty_without_writing(
    tmp_path, monkeypatch, capsys
) -> None:
    dirty = _provenance(dirty=True)
    monkeypatch.setattr(verifier, "capture_source_provenance", lambda root: dirty)
    monkeypatch.chdir(tmp_path)

    assert verifier.main([]) == 0
    captured = capsys.readouterr()
    report = json.loads(captured.out.split("source freeze preflight: PASS")[0])
    assert report["clean"] is False
    assert report["status"] == "pass"
    assert list(tmp_path.iterdir()) == []


def test_require_clean_cli_rejects_dirty_and_unavailable(
    tmp_path, monkeypatch, capsys
) -> None:
    monkeypatch.chdir(tmp_path)
    for provenance, reason in (
        (_provenance(dirty=True), "worktree is dirty"),
        (_provenance(available=False), "git provenance is unavailable"),
    ):
        monkeypatch.setattr(
            verifier, "capture_source_provenance", lambda root, p=provenance: p
        )
        assert verifier.main(["--require-clean"]) == 2
        captured = capsys.readouterr()
        assert reason in captured.err
    assert list(tmp_path.iterdir()) == []


def test_expected_identities_pass_or_fail_without_writing(
    tmp_path, monkeypatch, capsys
) -> None:
    clean = _provenance()
    monkeypatch.setattr(verifier, "capture_source_provenance", lambda root: clean)
    monkeypatch.chdir(tmp_path)
    accepted = [
        "--require-clean",
        "--expected-source-fingerprint",
        "a" * 64,
        "--expected-git-commit",
        "b" * 40,
    ]
    assert verifier.main(accepted) == 0
    assert '"status": "pass"' in capsys.readouterr().out

    rejected = [
        "--expected-source-fingerprint",
        "e" * 64,
    ]
    assert verifier.main(rejected) == 2
    assert "source fingerprint mismatch" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("value", ["short", "g" * 64, "a" * 63])
def test_invalid_expected_fingerprint_is_rejected(value) -> None:
    with pytest.raises(SystemExit) as exc_info:
        verifier.main(["--expected-source-fingerprint", value])
    assert exc_info.value.code == 2


def test_verifier_is_part_of_current_source_fingerprint() -> None:
    provenance = capture_source_provenance()
    paths = {item.path for item in provenance.source_files}
    assert "scripts/verify_source_freeze.py" in paths
