"""
helpers/model_io.py — Thin wrapper for model spectrum file I/O.
Lazy-imports plot.read_file() to avoid loading the 22k-line plot.py eagerly.
"""
from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

MODELS_DIR = os.path.join(_ROOT, 'Data', 'Models_for_Guy')


def list_model_files() -> list[str]:
    """Return sorted list of available model spectrum files."""
    if not os.path.isdir(MODELS_DIR):
        return []
    return sorted(
        f for f in os.listdir(MODELS_DIR)
        if os.path.isfile(os.path.join(MODELS_DIR, f)) and not f.startswith('.')
    )
