"""Validate and analyze MineMemBench M15 Controlled Formal V1 evidence."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from minemembench.evaluation.formal_m15 import (
    FORMAL_RESULTS_RELATIVE,
    FormalIntegrityError,
    analyze_formal,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--results-dir",
        default=str(REPO_ROOT / FORMAL_RESULTS_RELATIVE),
        help="Exact Formal V1 results directory; calibration directories are never scanned.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        outputs = analyze_formal(Path(args.results_dir))
    except FormalIntegrityError as exc:
        print(f"formal analysis: FAIL: {exc}", file=sys.stderr)
        return 2
    print("formal analysis: PASS")
    for name, path in outputs.items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
