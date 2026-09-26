#!/usr/bin/env python3
"""Recompute the competition score with an explicit penalty breakdown.

The graded formula is::

    accuracy_score = 100 * accuracy
    search_penalty = A * min((search_time - baseline_search_time) / baseline_search_time, 1)
    build_penalty  = B * min((build_time  - baseline_build_time)  / baseline_build_time,  1)
    final_score    = accuracy_score - search_penalty - build_penalty

Both penalties saturate at their coefficient, so the build penalty can never
cost more than ``B`` points however slow the build gets. Accuracy must clear the
80% preliminary gate to score at all and the 85% final gate to advance.

The reference implementation is reproduced verbatim, including the fact that
beating the baseline yields a negative penalty rather than being clamped at
zero.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from hms import paths
from hms.logging_setup import setup_logging

DEFAULT_COEFFICIENT_A = 1.0
DEFAULT_COEFFICIENT_B = 5.0
PRELIMINARY_ACCURACY_GATE = 0.80
FINAL_ACCURACY_GATE = 0.85

SUMMARY_FILENAME = "rag_answers_judged_summary.json"
TIMINGS_FILENAME = "timings.json"


@dataclass(frozen=True)
class ScoreBreakdown:
    """Score decomposition for one evaluation run."""

    accuracy: float
    accuracy_score: float
    search_penalty: float
    build_penalty: float
    final_score: float
    actual_search_time: float
    baseline_search_time: float
    actual_build_time: float
    baseline_build_time: float
    coefficient_a: float
    coefficient_b: float
    clears_preliminary_gate: bool
    clears_final_gate: bool


def penalty(actual: float, baseline: float, coefficient: float) -> float:
    """Scaled and saturated relative overrun, matching the grader."""
    if baseline <= 0:
        return 0.0
    return coefficient * min((actual - baseline) / baseline, 1.0)


def compute_score(
    accuracy: float,
    actual_search_time: float,
    actual_build_time: float,
    baseline_search_time: float,
    baseline_build_time: float,
    coefficient_a: float = DEFAULT_COEFFICIENT_A,
    coefficient_b: float = DEFAULT_COEFFICIENT_B,
) -> ScoreBreakdown:
    """Produce the full score decomposition."""
    accuracy_score = accuracy * 100.0
    search_penalty = penalty(actual_search_time, baseline_search_time, coefficient_a)
    build_penalty = penalty(actual_build_time, baseline_build_time, coefficient_b)

    return ScoreBreakdown(
        accuracy=accuracy,
        accuracy_score=round(accuracy_score, 4),
        search_penalty=round(search_penalty, 4),
        build_penalty=round(build_penalty, 4),
        final_score=round(accuracy_score - search_penalty - build_penalty, 4),
        actual_search_time=round(actual_search_time, 2),
        baseline_search_time=round(baseline_search_time, 2),
        actual_build_time=round(actual_build_time, 2),
        baseline_build_time=round(baseline_build_time, 2),
        coefficient_a=coefficient_a,
        coefficient_b=coefficient_b,
        clears_preliminary_gate=accuracy >= PRELIMINARY_ACCURACY_GATE,
        clears_final_gate=accuracy >= FINAL_ACCURACY_GATE,
    )


def load_accuracy(summary_path: Path) -> float:
    """Read overall accuracy from a judger summary file."""
    payload = json.loads(Path(summary_path).read_text(encoding="utf-8"))
    if isinstance(payload.get("overall"), dict) and "accuracy" in payload["overall"]:
        return float(payload["overall"]["accuracy"])
    if "accuracy" in payload:
        return float(payload["accuracy"])
    raise ValueError(f"no accuracy field in {summary_path}")


def load_timings(timings_path: Path) -> tuple[float, float]:
    """Read ``(build_time, search_time)`` from a timings file."""
    payload = json.loads(Path(timings_path).read_text(encoding="utf-8"))
    missing = [key for key in ("build_time", "search_time") if key not in payload]
    if missing:
        raise ValueError(f"missing {missing} in {timings_path}")
    return float(payload["build_time"]), float(payload["search_time"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--run-dir",
        type=Path,
        default=None,
        help="directory holding the judger summary and timings files",
    )
    parser.add_argument("--summary", type=Path, default=None)
    parser.add_argument("--timings", type=Path, default=None)
    parser.add_argument("--baseline-search-time", type=float, default=None)
    parser.add_argument("--baseline-build-time", type=float, default=None)
    parser.add_argument("--coefficient-a", type=float, default=DEFAULT_COEFFICIENT_A)
    parser.add_argument("--coefficient-b", type=float, default=DEFAULT_COEFFICIENT_B)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    if args.run_dir is not None:
        run_dir = args.run_dir
        run_dir.mkdir(parents=True, exist_ok=True)
    else:
        try:
            run_dir = paths.latest_run_dir()
        except FileNotFoundError:
            run_dir = paths.new_run_dir("score")

    log = setup_logging("score", run_dir)

    summary_path = args.summary or run_dir / SUMMARY_FILENAME
    timings_path = args.timings or run_dir / TIMINGS_FILENAME

    try:
        accuracy = load_accuracy(summary_path)
        build_time, search_time = load_timings(timings_path)
    except (FileNotFoundError, ValueError) as error:
        log.error("%s", error)
        return 1

    if args.baseline_search_time is None or args.baseline_build_time is None:
        log.error("baseline search and build times are required")
        return 2

    breakdown = compute_score(
        accuracy=accuracy,
        actual_search_time=search_time,
        actual_build_time=build_time,
        baseline_search_time=args.baseline_search_time,
        baseline_build_time=args.baseline_build_time,
        coefficient_a=args.coefficient_a,
        coefficient_b=args.coefficient_b,
    )

    log.info("accuracy          %.4f", breakdown.accuracy)
    log.info("accuracy score    %+.4f", breakdown.accuracy_score)
    log.info(
        "search penalty    %+.4f  (%.2fs vs %.2fs)",
        breakdown.search_penalty,
        breakdown.actual_search_time,
        breakdown.baseline_search_time,
    )
    log.info(
        "build penalty     %+.4f  (%.2fs vs %.2fs)",
        breakdown.build_penalty,
        breakdown.actual_build_time,
        breakdown.baseline_build_time,
    )
    log.info("final score       %+.4f", breakdown.final_score)
    log.info(
        "preliminary gate  %s (>= %.0f%%)",
        "PASS" if breakdown.clears_preliminary_gate else "FAIL",
        PRELIMINARY_ACCURACY_GATE * 100,
    )
    log.info(
        "final gate        %s (>= %.0f%%)",
        "PASS" if breakdown.clears_final_gate else "FAIL",
        FINAL_ACCURACY_GATE * 100,
    )

    out_path = args.out or run_dir / "score.json"
    out_path.write_text(
        json.dumps(asdict(breakdown), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    log.info("score written to %s", out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
