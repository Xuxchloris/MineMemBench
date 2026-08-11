"""Deterministic producer-source provenance for benchmark evidence.

The fingerprint deliberately covers code, tests, dependency manifests,
container definitions, the public configuration schema and the wire contract.
It never traverses runtime data: ``.env``, results, stores, caches, build
output, Minecraft worlds and dependency directories are outside the explicit
allowlist.

This is provenance, not a substitute for a clean reviewed git commit.  Git
metadata is recorded independently so a dirty or unavailable repository can
never be mistaken for an immutable revision.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

SOURCE_PROVENANCE_SCHEMA = "minemembench-source/v1"

# Runtime, verification and reproducibility inputs.  Keeping the allowlist
# explicit prevents a broad filesystem walk from ever reading .env, results,
# stores, server worlds, caches or user-owned data.
SOURCE_GLOBS: tuple[str, ...] = (
    "benchmark/minemembench/**/*.py",
    "benchmark/minemembench/dashboard/static/*",
    "benchmark/tests/**/*.py",
    "benchmark/tests/fixtures/**/*.json",
    "minecraft/src/**/*.ts",
    "minecraft/test/**/*.ts",
)
SOURCE_FILES: tuple[str, ...] = (
    ".env.example",
    "docker-compose.yml",
    "docker-compose.letta.yml",
    "pyproject.toml",
    "minecraft/Dockerfile",
    "minecraft/package.json",
    "minecraft/package-lock.json",
    "minecraft/tsconfig.json",
    "docs/protocol.md",
    "scripts/analyze_formal_m15.py",
    "scripts/run_controlled_campaign.py",
    "scripts/run_formal_m15_v1.py",
    "scripts/verify_source_freeze.py",
    "scripts/verify_letta_live.py",
)

_FORBIDDEN_PARTS = frozenset(
    {
        ".git",
        ".venv",
        "__pycache__",
        "dist",
        "node_modules",
        "results",
        "server",
        "stores",
    }
)


class SourceFileDigest(BaseModel):
    """One allowlisted file bound into the source-tree fingerprint."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str
    size: int
    sha256: str


class SourceProvenance(BaseModel):
    """Complete deterministic source identity plus read-only git state."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = SOURCE_PROVENANCE_SCHEMA
    digest_algorithm: str = "sha256"
    source_tree_fingerprint: str
    source_file_count: int = Field(ge=1)
    source_files: tuple[SourceFileDigest, ...]
    git_available: bool
    git_commit: str | None = None
    git_dirty: bool | None = None
    git_status_fingerprint: str | None = None

    @model_validator(mode="after")
    def validate_internal_consistency(self) -> SourceProvenance:
        if self.source_file_count != len(self.source_files):
            raise ValueError(
                "source_file_count must equal the number of source_files"
            )
        git_values = (
            self.git_commit,
            self.git_dirty,
            self.git_status_fingerprint,
        )
        if self.git_available and any(value is None for value in git_values):
            raise ValueError("available git provenance must carry all git fields")
        if not self.git_available and any(value is not None for value in git_values):
            raise ValueError("unavailable git provenance cannot carry git fields")
        return self


def repository_root() -> Path:
    """Return the repository root for this installed/editable source tree."""

    return Path(__file__).resolve().parents[3]


def _is_forbidden(relative: Path) -> bool:
    parts = set(relative.parts)
    return bool(parts & _FORBIDDEN_PARTS) or relative.name == ".env"


def _discover_source_paths(
    root: Path,
    *,
    globs: tuple[str, ...],
    required_files: tuple[str, ...],
) -> list[Path]:
    root = root.resolve()
    paths: set[Path] = set()

    for relative_text in required_files:
        relative = Path(relative_text)
        if _is_forbidden(relative):
            raise ValueError(f"forbidden provenance path: {relative.as_posix()}")
        path = root / relative
        if not path.is_file():
            raise FileNotFoundError(
                f"required provenance input is missing: {relative.as_posix()}"
            )
        paths.add(path)

    for pattern in globs:
        for path in root.glob(pattern):
            if not path.is_file():
                continue
            relative = path.relative_to(root)
            if _is_forbidden(relative):
                raise ValueError(
                    f"allowlist glob reached forbidden path: {relative.as_posix()}"
                )
            paths.add(path)

    if not paths:
        raise ValueError("source provenance allowlist resolved to no files")

    ordered = sorted(paths, key=lambda path: path.relative_to(root).as_posix())
    for path in ordered:
        if path.is_symlink():
            relative = path.relative_to(root).as_posix()
            raise ValueError(f"symlink provenance input is not allowed: {relative}")
        resolved = path.resolve()
        try:
            resolved_relative = resolved.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"provenance input escapes repository: {path}") from exc
        # Windows directory junctions are not reported by Path.is_symlink().
        # Re-check the real target so an allowlisted alias cannot tunnel into
        # results/stores/server worlds or another forbidden in-repo tree.
        if _is_forbidden(resolved_relative):
            raise ValueError(
                "resolved provenance input reaches forbidden path: "
                f"{resolved_relative.as_posix()}"
            )
    return ordered


def _git_provenance(root: Path) -> tuple[bool, str | None, bool | None, str | None]:
    """Read git identity without mutating the repository."""

    def run(*args: str) -> subprocess.CompletedProcess[str] | None:
        try:
            return subprocess.run(
                ["git", "-C", str(root), *args],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except OSError:
            return None

    head = run("rev-parse", "HEAD")
    if head is None or head.returncode != 0:
        return False, None, None, None

    status = run("status", "--porcelain=v1", "--untracked-files=all")
    if status is None or status.returncode != 0:
        # A commit without an auditable worktree state must not be represented
        # as clean or fully available.
        return False, None, None, None

    commit = head.stdout.strip()
    normalized_status = status.stdout.replace("\r\n", "\n").replace("\r", "\n")
    status_fingerprint = hashlib.sha256(
        normalized_status.encode("utf-8")
    ).hexdigest()
    return True, commit, bool(normalized_status.strip()), status_fingerprint


def capture_source_provenance(
    root: Path | None = None,
    *,
    globs: tuple[str, ...] = SOURCE_GLOBS,
    required_files: tuple[str, ...] = SOURCE_FILES,
) -> SourceProvenance:
    """Fingerprint the allowlisted source tree and read current git state.

    ``globs`` and ``required_files`` are injectable solely so hermetic tests can
    exercise ordering, mutation and exclusion behavior in a temporary tree.
    Production callers use the module constants.
    """

    root = (root or repository_root()).resolve()
    paths = _discover_source_paths(
        root,
        globs=globs,
        required_files=required_files,
    )
    records: list[SourceFileDigest] = []
    for path in paths:
        content = path.read_bytes()
        records.append(
            SourceFileDigest(
                path=path.relative_to(root).as_posix(),
                size=len(content),
                sha256=hashlib.sha256(content).hexdigest(),
            )
        )

    identity_payload = {
        "schema_version": SOURCE_PROVENANCE_SCHEMA,
        "files": [record.model_dump(mode="json") for record in records],
    }
    encoded = json.dumps(
        identity_payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    fingerprint = hashlib.sha256(encoded).hexdigest()
    git_available, git_commit, git_dirty, git_status_fingerprint = _git_provenance(
        root
    )
    return SourceProvenance(
        source_tree_fingerprint=fingerprint,
        source_file_count=len(records),
        source_files=tuple(records),
        git_available=git_available,
        git_commit=git_commit,
        git_dirty=git_dirty,
        git_status_fingerprint=git_status_fingerprint,
    )


def source_freeze_error(
    provenance: SourceProvenance,
    *,
    require_clean: bool = False,
    expected_source_fingerprint: str | None = None,
    expected_git_commit: str | None = None,
) -> str | None:
    """Return the first source-freeze failure, or ``None`` when accepted.

    This pure validator is shared by the campaign runner and the standalone
    read-only preflight command. It never captures provenance or mutates git;
    callers decide whether a clean tree and/or exact expected identities are
    required for their context.
    """

    if (
        expected_source_fingerprint is not None
        and provenance.source_tree_fingerprint != expected_source_fingerprint
    ):
        return (
            "source fingerprint mismatch: expected "
            f"{expected_source_fingerprint}, got "
            f"{provenance.source_tree_fingerprint}"
        )

    if (require_clean or expected_git_commit is not None) and not provenance.git_available:
        return "git provenance is unavailable"

    if require_clean and provenance.git_dirty is not False:
        return "the git worktree is dirty"

    if expected_git_commit is not None and provenance.git_commit != expected_git_commit:
        return (
            f"git commit mismatch: expected {expected_git_commit}, "
            f"got {provenance.git_commit}"
        )

    return None
