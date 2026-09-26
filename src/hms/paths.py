"""Central path resolution.

Every entry point resolves locations through this module so that no script
depends on the current working directory. ``HMS_ROOT`` overrides the detected
repository root, which keeps the code usable from a container or a tmpfs mount.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

ROOT = Path(os.environ.get("HMS_ROOT") or Path(__file__).resolve().parents[2]).resolve()

DATA_DIR = ROOT / "data"
RAW_PDF_DIR = DATA_DIR / "raw" / "pdfs"
PARSED_DIR = DATA_DIR / "parsed"
PARSED_NORM_DIR = DATA_DIR / "parsed_norm"

INDEX_DIR = ROOT / "index"
RUNS_DIR = ROOT / "runs"

ASSETS_DIR = ROOT / "assets"
CONFIGS_DIR = ROOT / "configs"
THIRD_PARTY_DIR = ROOT / "third_party"
RAG_ANYTHING_DIR = THIRD_PARTY_DIR / "RAG-Anything"

QUERIES_FILE = ASSETS_DIR / "queries_30.json"


def ensure_dir(path: Path) -> Path:
    """Create ``path`` when missing and return it."""
    Path(path).mkdir(parents=True, exist_ok=True)
    return Path(path)


def new_run_dir(step: str) -> Path:
    """Create a timestamped run directory namespaced by pipeline step."""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return ensure_dir(RUNS_DIR / f"{stamp}_{step}")


def latest_run_dir(step: str | None = None) -> Path:
    """Return the most recent run directory, optionally filtered by step."""
    pattern = f"*_{step}" if step else "*"
    candidates = sorted(p for p in RUNS_DIR.glob(pattern) if p.is_dir())
    if not candidates:
        raise FileNotFoundError(f"no run directory under {RUNS_DIR} matching {pattern}")
    return candidates[-1]
