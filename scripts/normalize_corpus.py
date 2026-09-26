#!/usr/bin/env python3
"""Rewrite MinerU content lists with normalized math and absolute image paths.

Reads ``<src>/<doc>/auto/<doc>_content_list.json`` and writes a mirrored tree
under ``<dst>``. Two changes are applied:

* math spans in the ``text`` field of ``text`` and ``equation`` items are
  normalized so numerals and units survive tokenization;
* ``img_path`` is rewritten to an absolute path inside the source tree, which
  removes the working-directory dependency of the reference pipeline.

Images are never copied. The rewritten paths point back into ``<src>``.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from hms import paths
from hms.logging_setup import setup_logging
from hms.normalize import normalize_text

CONTENT_LIST_GLOB = "*_content_list.json"
NORMALIZED_TYPES = frozenset({"text", "equation"})
PROGRESS_EVERY = 10


def resolve_image(raw: str, src_images: Path) -> Path:
    """Point an image reference at the source tree regardless of its origin.

    MinerU writes image paths relative to a run directory that no longer
    exists, so only the file name is trustworthy.
    """
    name = Path(raw.replace("\\", "/")).name
    return (src_images / name).resolve()


def normalize_document(
    src_file: Path,
    src_root: Path,
    dst_root: Path,
    stats: Counter[str],
    missing_images: set[str],
    dry_run: bool = False,
) -> int:
    """Normalize one content list and return its item count."""
    payload: list[Any] = json.loads(src_file.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise TypeError(f"expected a list in {src_file}")

    relative_parent = src_file.parent.relative_to(src_root)
    src_images = src_root / relative_parent / "images"

    for item in payload:
        if not isinstance(item, dict):
            continue

        if item.get("type") in NORMALIZED_TYPES and isinstance(item.get("text"), str):
            before = item["text"]
            after = normalize_text(before, stats)
            if after != before:
                item["text"] = after
                stats["items_touched"] += 1

        raw_path = item.get("img_path")
        if isinstance(raw_path, str) and raw_path:
            resolved = resolve_image(raw_path, src_images)
            if not resolved.exists():
                missing_images.add(resolved.name)
            item["img_path"] = str(resolved)

    if not dry_run:
        out_file = dst_root / src_file.relative_to(src_root)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    return len(payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--src", type=Path, default=paths.PARSED_DIR)
    parser.add_argument("--dst", type=Path, default=paths.PARSED_NORM_DIR)
    parser.add_argument("--limit", type=int, default=0, help="process at most N documents")
    parser.add_argument("--dry-run", action="store_true", help="report without writing")
    args = parser.parse_args(argv)

    run_dir = paths.new_run_dir("normalize")
    log = setup_logging("normalize", run_dir)

    src = args.src.resolve()
    dst = args.dst.resolve()
    if not src.is_dir():
        log.error("source tree not found: %s", src)
        return 1

    files = sorted(src.rglob(CONTENT_LIST_GLOB))
    if args.limit > 0:
        files = files[: args.limit]
    if not files:
        log.error("no %s found under %s", CONTENT_LIST_GLOB, src)
        return 1

    log.info("src=%s", src)
    log.info("dst=%s", dst)
    log.info("documents=%d dry_run=%s", len(files), args.dry_run)

    stats: Counter[str] = Counter()
    missing_images: set[str] = set()
    total_items = 0

    for index, path in enumerate(files, start=1):
        total_items += normalize_document(
            path, src, dst, stats, missing_images, dry_run=args.dry_run
        )
        if index % PROGRESS_EVERY == 0 or index == len(files):
            log.info("progress %d/%d documents, %d items", index, len(files), total_items)

    report = {
        "documents": len(files),
        "items": total_items,
        "items_touched": stats.pop("items_touched", 0),
        "rules": dict(sorted(stats.items())),
        "missing_images": len(missing_images),
        "src": str(src),
        "dst": str(dst),
        "dry_run": args.dry_run,
    }
    report_path = run_dir / "normalize_stats.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    log.info("items=%d touched=%d", report["items"], report["items_touched"])
    for name, count in report["rules"].items():
        log.info("  rule %-24s %d", name, count)
    if missing_images:
        sample = ", ".join(sorted(missing_images)[:5])
        log.warning("missing images: %d (e.g. %s)", len(missing_images), sample)
    log.info("stats written to %s", report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
