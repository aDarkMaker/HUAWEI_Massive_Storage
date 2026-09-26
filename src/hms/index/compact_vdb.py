#!/usr/bin/env python3
"""Strip the redundant vector payload from nano-vectordb store files.

LightRAG keeps every embedding twice. ``matrix`` holds the float32 values in
one base64 block, while each record also carries a ``vector`` field with the
same embedding re-encoded as ``base64(zlib(float16))``. ``NanoVectorDBStorage.
query`` drops that field before returning results, so it only inflates the JSON
on disk and slows every load.

Removing it shrinks the stores by around 30%: measured on the reference store,
`vdb_chunks.json` 38.6 MB -> 28.3 MB, `vdb_entities.json` 365.5 MB -> 254.3 MB
and `vdb_relationships.json` 655.1 MB -> 454.6 MB. Nothing else is touched: the
matrix, the record metadata and the record order are preserved, so files stay
loadable by the unmodified baseline.
"""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from hms import paths
from hms.logging_setup import setup_logging

VECTOR_FIELD = "vector"
VDB_GLOB = "vdb_*.json"


@dataclass(frozen=True)
class CompactionReport:
    """Outcome of compacting a single store file."""

    path: Path
    records: int
    dropped: int
    bytes_before: int
    bytes_after: int

    @property
    def saved_bytes(self) -> int:
        return self.bytes_before - self.bytes_after

    @property
    def saved_ratio(self) -> float:
        return self.saved_bytes / self.bytes_before if self.bytes_before else 0.0


def compact_file(path: Path, dry_run: bool = False) -> CompactionReport:
    """Drop every ``vector`` field from one store file."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = payload.get("data")
    if not isinstance(records, list):
        raise ValueError(f"unexpected layout in {path}: missing data list")

    dropped = 0
    for record in records:
        if isinstance(record, dict) and record.pop(VECTOR_FIELD, None) is not None:
            dropped += 1

    bytes_before = path.stat().st_size

    if dry_run:
        serialized = json.dumps(payload, ensure_ascii=False)
        bytes_after = len(serialized.encode("utf-8"))
    else:
        tmp_path = path.with_name(path.name + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False)
        os.replace(tmp_path, path)
        bytes_after = path.stat().st_size

    return CompactionReport(path, len(records), dropped, bytes_before, bytes_after)


def collect_targets(inputs: Sequence[Path]) -> list[Path]:
    """Expand directories into store files, defaulting to the index root."""
    roots = list(inputs) or [paths.INDEX_DIR]
    targets: list[Path] = []
    for root in roots:
        if root.is_dir():
            targets.extend(sorted(root.rglob(VDB_GLOB)))
        elif root.is_file():
            targets.append(root)
        else:
            raise FileNotFoundError(root)
    return targets


def format_bytes(value: int) -> str:
    size = float(value)
    for unit in ("B", "KB", "MB", "GB"):
        if abs(size) < 1024.0 or unit == "GB":
            return f"{size:.1f}{unit}"
        size /= 1024.0
    return f"{size:.1f}GB"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help=f"store files or directories (default: {paths.INDEX_DIR})",
    )
    parser.add_argument("--dry-run", action="store_true", help="measure without writing")
    args = parser.parse_args(argv)

    run_dir = paths.new_run_dir("compact")
    log = setup_logging("compact", run_dir)

    targets = collect_targets(args.paths)
    if not targets:
        log.error("no %s found", VDB_GLOB)
        return 1

    log.info("targets=%d dry_run=%s", len(targets), args.dry_run)

    reports: list[CompactionReport] = []
    for target in targets:
        report = compact_file(target, dry_run=args.dry_run)
        reports.append(report)
        log.info(
            "%-32s records=%d dropped=%d %s -> %s (-%.1f%%)",
            target.name,
            report.records,
            report.dropped,
            format_bytes(report.bytes_before),
            format_bytes(report.bytes_after),
            report.saved_ratio * 100.0,
        )

    before = sum(report.bytes_before for report in reports)
    after = sum(report.bytes_after for report in reports)
    log.info(
        "total %s -> %s (-%.1f%%), records=%d, dropped=%d",
        format_bytes(before),
        format_bytes(after),
        (1.0 - after / before) * 100.0 if before else 0.0,
        sum(report.records for report in reports),
        sum(report.dropped for report in reports),
    )

    summary = {
        "dry_run": args.dry_run,
        "files": [
            {
                "path": str(report.path),
                "records": report.records,
                "dropped": report.dropped,
                "bytes_before": report.bytes_before,
                "bytes_after": report.bytes_after,
                "saved_ratio": round(report.saved_ratio, 6),
            }
            for report in reports
        ],
        "bytes_before": before,
        "bytes_after": after,
    }
    summary_path = run_dir / "compact_report.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    log.info("report written to %s", summary_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
