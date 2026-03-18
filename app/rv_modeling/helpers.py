"""rv_modeling/helpers.py — Constants and small layout helpers."""
from __future__ import annotations

import math
import numpy as np

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


BIN_METHODS = [
    "Auto (Freedman-Diaconis)", "Auto (Sturges)", "Auto (Scott)",
    "Auto (sqrt N)", "Auto (Plotly)", "Manual",
]


def auto_nbins(data, method: str = "freedman-diaconis") -> int | None:
    """Compute histogram bin count using *method*. Returns None for Plotly default."""
    n = len(data)
    if n < 2:
        return 10
    rng = float(np.ptp(data))
    if rng == 0:
        return 10
    method = method.lower()
    if "plotly" in method:
        return None
    if "sturges" in method:
        return int(math.ceil(math.log2(n))) + 1
    if "scott" in method:
        s = float(np.std(data, ddof=1))
        if s == 0:
            return 10
        h = 3.5 * s * n ** (-1 / 3)
        return max(1, int(math.ceil(rng / h)))
    if "sqrt" in method:
        return max(1, int(math.ceil(math.sqrt(n))))
    # default: Freedman-Diaconis
    q75, q25 = np.percentile(data, [75, 25])
    iqr = float(q75 - q25)
    if iqr == 0:
        return 10
    h = 2.0 * iqr * n ** (-1 / 3)
    return max(1, int(math.ceil(rng / h)))


def resolve_nbins(data, obs_data: dict) -> int | None:
    """Return nbins from obs_data bin_method / manual_bins."""
    method = obs_data.get("bin_method", "Auto (Freedman-Diaconis)")
    if method == "Manual":
        return obs_data.get("manual_bins", 50)
    return auto_nbins(data, method)


def _ann(pal: dict) -> dict:
    """Annotation styling respecting palette."""
    return dict(
        bgcolor=pal["annotation_bg"],
        bordercolor=pal["annotation_border"],
        font=dict(color=pal["annotation_font"], size=11),
        borderwidth=1,
    )
