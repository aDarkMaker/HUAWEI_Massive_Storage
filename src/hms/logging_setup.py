"""Structured logging for pipeline steps.

Each step writes to stdout and to ``<run_dir>/<step>.log`` so a failed run can
be inspected after the terminal is gone. Handlers are attached to the root
logger, which also captures third-party records such as LightRAG's.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

FORMAT = "%(asctime)s %(levelname)-8s %(name)s:%(lineno)d %(message)s"
DATE_FORMAT = "%Y-%m-%dT%H:%M:%S%z"
MAX_BYTES = 10 * 1024 * 1024
BACKUP_COUNT = 3


def setup_logging(step: str, run_dir: Path, level: int = logging.INFO) -> logging.Logger:
    """Route logging to stdout and a rotating per-step file."""
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(level)
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()

    formatter = logging.Formatter(FORMAT, datefmt=DATE_FORMAT)

    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    root.addHandler(stream)

    file_handler = RotatingFileHandler(
        run_dir / f"{step}.log",
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    return logging.getLogger(step)
