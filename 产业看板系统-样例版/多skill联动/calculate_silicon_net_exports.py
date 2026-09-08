# -*- coding: utf-8 -*-
"""Backward-compatible wrapper around the generic net-export calculator."""

from __future__ import annotations

import sys
from pathlib import Path

from calculate_net_exports import calculate_net_exports


if __name__ == "__main__":
    paths = [Path(arg) for arg in sys.argv[1:] if not arg.startswith("-")]
    if not paths:
        print("Usage: python calculate_silicon_net_exports.py <file.xlsx>")
        sys.exit(1)
    for path in paths:
        calculate_net_exports(path)
