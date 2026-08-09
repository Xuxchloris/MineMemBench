"""Read-only preflight for a MineMemBench producer-source freeze."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# A freeze preflight must not make even gitignored bytecode-cache writes.
# This is set before importing any project module.
sys.dont_write_bytecode = True

from minemembench.core.provenance import (
    SourceProvenance,
    capture_source_provenance,
    source_freeze_error,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_GIT_COMMIT_RE = re.compile(r"^(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})$")


def _sha256(value: str) -> str:
    normalized = value.lower()
    if not _SHA256_RE.fullmatch(normalized):
        raise argparse.ArgumentTypeError("expected a 64-character SHA-256 hex digest")
    return normalized


def _git_commit(value: str) -> str:
    normalized = value.lower()
    if not _GIT_COMMIT_RE.fullmatch(normalized):
        raise argparse.ArgumentTypeError(
            "expected a 40- or 64-character hexadecimal git commit"
        )
    return normalized


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--require-clean",
        action="store_true",
        help="Fail unless git is available and the complete worktree is clean.",
    )
    parser.add_argument(
        "--expected-source-fingerprint",
        type=_sha256,
        help="Fail unless the producer-source SHA-256 fingerprint matches.",
    )
    parser.add_argument(
        "--expected-git-commit",
        type=_git_commit,
        help="Fail unless read-only git provenance reports this exact commit.",
    )
    return parser


def _compact_report(
    provenance: SourceProvenance,
    *,
    expected_source_fingerprint: str | None,
    expected_git_commit: str | None,
    error: str | None,
) -> dict[str, object]:
    return {
        "schema_version": provenance.schema_version,
        "source_tree_fingerprint": provenance.source_tree_fingerprint,
        "source_file_count": provenance.source_file_count,
        "git_available": provenance.git_available,
        "git_commit": provenance.git_commit,
        "git_dirty": provenance.git_dirty,
        "git_status_fingerprint": provenance.git_status_fingerprint,
        "clean": provenance.git_available and provenance.git_dirty is False,
        "expected_source_fingerprint": expected_source_fingerprint,
        "source_fingerprint_matches": (
            None
            if expected_source_fingerprint is None
            else provenance.source_tree_fingerprint == expected_source_fingerprint
        ),
        "expected_git_commit": expected_git_commit,
        "git_commit_matches": (
            None
            if expected_git_commit is None
            else provenance.git_commit == expected_git_commit
        ),
        "status": "pass" if error is None else "fail",
    }


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        provenance = capture_source_provenance(REPO_ROOT)
    except (OSError, ValueError) as exc:
        print(f"source freeze preflight: FAIL: cannot capture provenance: {exc}", file=sys.stderr)
        return 2

    error = source_freeze_error(
        provenance,
        require_clean=args.require_clean,
        expected_source_fingerprint=args.expected_source_fingerprint,
        expected_git_commit=args.expected_git_commit,
    )
    report = _compact_report(
        provenance,
        expected_source_fingerprint=args.expected_source_fingerprint,
        expected_git_commit=args.expected_git_commit,
        error=error,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    if error is not None:
        print(f"source freeze preflight: FAIL: {error}", file=sys.stderr)
        return 2
    print("source freeze preflight: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
