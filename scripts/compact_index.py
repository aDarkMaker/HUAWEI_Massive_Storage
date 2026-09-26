#!/usr/bin/env python3
"""Entry point for stripping redundant vector payloads from the index stores."""

from __future__ import annotations

from hms.index.compact_vdb import main

if __name__ == "__main__":
    raise SystemExit(main())
