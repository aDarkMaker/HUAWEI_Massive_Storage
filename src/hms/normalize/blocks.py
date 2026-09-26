"""Structural predicates and field helpers over MinerU content-list blocks."""

from __future__ import annotations

from pathlib import Path
from typing import Any

MULTIMODAL_TYPES = frozenset({"image", "table"})


def is_blank_block(item: dict[str, Any]) -> bool:
    """Detect a multimodal block that carries no usable payload.

    MinerU occasionally emits a ``table`` entry with an empty ``img_path``, no
    ``table_body`` and no caption; twelve blocks in the reference corpus have
    this shape. Such a block cannot be grounded: the vision model is handed
    nothing to look at, so whatever it writes describes content it never saw,
    and the resulting chunk is confident but unfounded at retrieval time.
    """
    if item.get("type") not in MULTIMODAL_TYPES:
        return False

    captions = (item.get("image_caption") or []) + (item.get("table_caption") or [])
    payloads = (item.get("img_path"), item.get("table_body"), *captions)
    return not any(str(value).strip() for value in payloads if value is not None)


def resolve_image_path(raw_path: str, images_dir: Path) -> Path:
    """Resolve an ``img_path`` reference to an absolute path.

    MinerU writes paths relative to a run directory that does not travel with
    the corpus, such as ``mineru-parsed/<doc>/auto/images/<hash>.jpg``, so only
    the file name is trustworthy. The result is always absolute, which is what
    keeps downstream consumers independent of their working directory. This is
    the opposite of the upstream fixer, which only rewrites references that
    already start with ``images/`` and is therefore a no-op on this corpus.
    """
    name = Path(raw_path.replace("\\", "/")).name
    return (Path(images_dir) / name).resolve()
