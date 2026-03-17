"""rv_modeling/helpers.py — Constants and small layout helpers."""
from __future__ import annotations

from shared import PLOTLY_THEME

# ── Constants ────────────────────────────────────────────────────────────
NSIGMA_DETECT: float = 4.0
T_MAX: int = 301
COLOR_GAUSS = "#9B59B6"


def _theme_parts() -> tuple:
    """Return (xaxis_base, yaxis_base, legend_base) from PLOTLY_THEME."""
    return (
        PLOTLY_THEME.get("xaxis", {}),
        PLOTLY_THEME.get("yaxis", {}),
        PLOTLY_THEME.get("legend", {}),
    )


def _ann(pal: dict) -> dict:
    """Annotation styling respecting palette."""
    return dict(
        bgcolor=pal["annotation_bg"],
        bordercolor=pal["annotation_border"],
        font=dict(color=pal["annotation_font"], size=11),
        borderwidth=1,
    )
