"""Save/load persistence for Bin Sensitivity runs.

Layout on disk::

    bin_sensitivity_results/
        bin_sensitivity_<mock|real>_<YYMMDD-HHMM>.npz     # main: SchemeResult list + settings
        .partial_bin_sensitivity_<...>.npz                 # auto-saved, not yet confirmed
        mock_observations/
            bin_sensitivity_<...>_<YYMMDD-HHMM>/
                mock_stars.npz                             # pickled dict: stars + meta

Mirrors the descriptive-filename / list / metadata-scan pattern of ``app/bc/file_ops.py``
but lives in a dedicated ``bin_sensitivity_results/`` directory (sibling of ``results/``).

Main NPZ format (flat keys, via ``np.savez``):
    scheme_names          : array of str, shape (n_schemes,)
    scheme_families       : array of str
    scheme_edges          : object array of 1D float arrays (variable length)
    n_bins                : int array
    n_eff_bins            : int array
    best_fbin             : float array
    best_pi               : float array
    hdi68_fbin            : float array shape (n_schemes, 2)
    hdi68_pi              : float array shape (n_schemes, 2)
    logL_max              : float array
    aic                   : float array
    ks_D                  : float array
    ks_p                  : float array
    logL_map              : object array of 2D float arrays
    marginal_fbin         : object array of 1D float arrays
    marginal_pi           : object array of 1D float arrays
    sim_cdf_median        : object array of 1D float arrays
    sim_cdf_q16           : object array of 1D float arrays
    sim_cdf_q84           : object array of 1D float arrays
    cdf_x                 : object array of 1D float arrays
    n_obs_per_bin         : object array of 1D int arrays
    n_sim_per_bin         : object array of 1D int arrays
    status                : array of str
    status_reasons        : object array of tuples/lists of str
    ground_truth          : object array (dict or None per scheme)
    settings              : JSON string
    timestamp             : ISO-format str
    source_npz            : str
    mock_mode             : bool
    config_hash           : str
    format_version        : str  -- '1.0'

Mock NPZ format (pickled dict, via ``np.savez`` with ``allow_pickle``):
    stars = {0: {'rv': ndarray, 'mjd': ndarray, 'err': ndarray}, 1: ...}
    meta  = {'seed', 'n_stars', 'true_f_bin', 'true_pi', 'true_sigma',
             'true_logPmax', 'error_model', 'error_params', 'source_npz',
             'timestamp', 'delta_rv_sample'}
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
from dataclasses import fields
from datetime import datetime
from pathlib import Path

import numpy as np

_HERE = Path(__file__).resolve().parent
_APP = _HERE.parent              # .../Thesis-codes/app
_ROOT = _APP.parent              # repo root
# Streamlit adds the running script's dir to sys.path; for standalone
# (self-test / CLI) runs we also need `app/` so `from bc.xxx` resolves.
for _p in (str(_ROOT), str(_APP)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bc.bin_sensitivity_scorer import SchemeResult  # noqa: E402

# Project root resolved at import time — matches file_ops.py pattern
_THIS_FILE = Path(__file__).resolve()
PROJECT_ROOT = _THIS_FILE.parents[2]
RESULTS_DIR = PROJECT_ROOT / "bin_sensitivity_results"
MOCK_OBS_DIR = RESULTS_DIR / "mock_observations"

_FORMAT_VERSION = "1.0"


# ─────────────────────────────────────────────────────────────────────────────
# Directory / filename helpers
# ─────────────────────────────────────────────────────────────────────────────

def _ensure_dirs() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    MOCK_OBS_DIR.mkdir(parents=True, exist_ok=True)


def _now_stamp() -> str:
    return datetime.now().strftime("%y%m%d-%H%M")


def build_bs_filename(mock_mode: bool, timestamp: str | None = None) -> str:
    ts = timestamp or _now_stamp()
    tag = "mock" if mock_mode else "real"
    return f"bin_sensitivity_{tag}_{ts}.npz"


def partial_path_for(filename: str) -> Path:
    return RESULTS_DIR / f".partial_{filename}"


def final_path_for(filename: str) -> Path:
    return RESULTS_DIR / filename


def _permanent_stem(filename: str) -> str:
    """Return the non-partial stem (strip '.partial_' prefix and '.npz' ext)."""
    stem = Path(filename).stem  # strips '.npz'
    if stem.startswith(".partial_"):
        stem = stem[len(".partial_"):]
    return stem


def mock_obs_dir_for(filename: str) -> Path:
    """Return the subdir for mock observations matching ``filename``'s stem."""
    return MOCK_OBS_DIR / _permanent_stem(filename)


# ─────────────────────────────────────────────────────────────────────────────
# Object-array helpers (ragged numeric data)
# ─────────────────────────────────────────────────────────────────────────────

def _obj_array_from_list(items: list) -> np.ndarray:
    """Build a 1-D object ndarray from a list of possibly-ragged arrays.

    Passing ``dtype=object`` directly on a list of same-length arrays makes
    numpy return a 2-D array — we need a 1-D array so each entry stays a
    separate ndarray on load.
    """
    out = np.empty(len(items), dtype=object)
    for i, it in enumerate(items):
        out[i] = it
    return out


def _unwrap_scalar(v):
    """Unwrap 0-D object ndarrays back to their Python payload."""
    if isinstance(v, np.ndarray) and v.dtype == object and v.ndim == 0:
        return v.item()
    return v


# ─────────────────────────────────────────────────────────────────────────────
# Config hash — for embed into NPZ (settings sensitivity key)
# ─────────────────────────────────────────────────────────────────────────────

def _hash_settings(settings: dict, source_npz: str) -> str:
    payload = {
        "settings": settings,
        "source_npz": os.path.basename(str(source_npz)),
    }
    s = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


# ─────────────────────────────────────────────────────────────────────────────
# Save
# ─────────────────────────────────────────────────────────────────────────────

def save_bin_sensitivity_run(
    results: list[SchemeResult],
    settings: dict,
    mock_detail: dict | None,
    source_npz: str,
    filename: str,
    is_partial: bool,
) -> Path:
    """Serialize ``results`` + ``settings`` to an NPZ under ``bin_sensitivity_results/``.

    Parameters
    ----------
    results
        List of :class:`SchemeResult` objects (all 22 fields serialized).
    settings
        Free-form JSON-compatible dict (e.g. ``obs_delta_rv``, ``fbin_grid``,
        ``pi_grid``, ``source_npz``, etc.). Stored as a single JSON string.
    mock_detail
        Optional dict describing the synthetic sample — when not ``None``
        we also write ``mock_observations/<stem>/mock_stars.npz``.
    source_npz
        Path to the cadence .npz the scoring read from (echoed into the NPZ).
    filename
        Basename (no directory) — use :func:`build_bs_filename` to construct.
    is_partial
        If True, writes under the ``.partial_`` prefix so the UI can
        resume/promote later via :func:`promote_partial`.
    """
    _ensure_dirs()
    target = partial_path_for(filename) if is_partial else final_path_for(filename)

    # Collect every field from every SchemeResult into flat column arrays.
    n = len(results)

    scheme_names = np.array([r.scheme for r in results], dtype=object)
    scheme_families = np.array([r.family for r in results], dtype=object)
    scheme_edges = _obj_array_from_list([np.asarray(r.edges, dtype=float) for r in results])
    n_bins = np.array([int(r.n_bins) for r in results], dtype=int)
    n_eff_bins = np.array([int(r.n_eff_bins) for r in results], dtype=int)
    best_fbin = np.array([float(r.best_fbin) for r in results], dtype=float)
    best_pi = np.array([float(r.best_pi) for r in results], dtype=float)
    hdi68_fbin = np.array(
        [[float(r.hdi68_fbin[0]), float(r.hdi68_fbin[1])] for r in results],
        dtype=float,
    ) if n > 0 else np.zeros((0, 2), dtype=float)
    hdi68_pi = np.array(
        [[float(r.hdi68_pi[0]), float(r.hdi68_pi[1])] for r in results],
        dtype=float,
    ) if n > 0 else np.zeros((0, 2), dtype=float)
    logL_max = np.array([float(r.logL_max) for r in results], dtype=float)
    aic = np.array([float(r.aic) for r in results], dtype=float)
    ks_D = np.array([float(r.ks_D) for r in results], dtype=float)
    ks_p = np.array([float(r.ks_p) for r in results], dtype=float)

    logL_map = _obj_array_from_list([np.asarray(r.logL_map, dtype=float) for r in results])
    marginal_fbin = _obj_array_from_list(
        [np.asarray(r.marginal_fbin, dtype=float) for r in results]
    )
    marginal_pi = _obj_array_from_list(
        [np.asarray(r.marginal_pi, dtype=float) for r in results]
    )
    sim_cdf_median = _obj_array_from_list(
        [np.asarray(r.sim_cdf_median, dtype=float) for r in results]
    )
    sim_cdf_q16 = _obj_array_from_list(
        [np.asarray(r.sim_cdf_q16, dtype=float) for r in results]
    )
    sim_cdf_q84 = _obj_array_from_list(
        [np.asarray(r.sim_cdf_q84, dtype=float) for r in results]
    )
    cdf_x = _obj_array_from_list([np.asarray(r.cdf_x, dtype=float) for r in results])
    n_obs_per_bin = _obj_array_from_list(
        [np.asarray(r.n_obs_per_bin, dtype=int) for r in results]
    )
    n_sim_per_bin = _obj_array_from_list(
        [np.asarray(r.n_sim_per_bin, dtype=int) for r in results]
    )
    status = np.array([str(r.status) for r in results], dtype=object)
    status_reasons = _obj_array_from_list(
        [list(r.status_reasons) for r in results]
    )
    ground_truth = _obj_array_from_list(
        [(dict(r.ground_truth) if r.ground_truth is not None else None)
         for r in results]
    )

    settings_json = json.dumps(settings, default=str)
    timestamp_iso = datetime.now().isoformat()
    config_hash = _hash_settings(settings, source_npz)
    mock_mode = bool(mock_detail is not None)

    np.savez(
        target,
        scheme_names=scheme_names,
        scheme_families=scheme_families,
        scheme_edges=scheme_edges,
        n_bins=n_bins,
        n_eff_bins=n_eff_bins,
        best_fbin=best_fbin,
        best_pi=best_pi,
        hdi68_fbin=hdi68_fbin,
        hdi68_pi=hdi68_pi,
        logL_max=logL_max,
        aic=aic,
        ks_D=ks_D,
        ks_p=ks_p,
        logL_map=logL_map,
        marginal_fbin=marginal_fbin,
        marginal_pi=marginal_pi,
        sim_cdf_median=sim_cdf_median,
        sim_cdf_q16=sim_cdf_q16,
        sim_cdf_q84=sim_cdf_q84,
        cdf_x=cdf_x,
        n_obs_per_bin=n_obs_per_bin,
        n_sim_per_bin=n_sim_per_bin,
        status=status,
        status_reasons=status_reasons,
        ground_truth=ground_truth,
        settings=settings_json,
        timestamp=timestamp_iso,
        source_npz=str(source_npz),
        mock_mode=mock_mode,
        config_hash=config_hash,
        format_version=_FORMAT_VERSION,
    )

    # Also save mock observations (if supplied) under a sibling subdir.
    if mock_detail is not None:
        _save_mock_observations(filename, mock_detail, source_npz, timestamp_iso)

    return target


def _save_mock_observations(
    filename: str,
    mock_detail: dict,
    source_npz: str,
    timestamp_iso: str,
) -> Path:
    """Persist mock_detail to ``mock_observations/<stem>/mock_stars.npz``."""
    mock_dir = mock_obs_dir_for(filename)
    mock_dir.mkdir(parents=True, exist_ok=True)

    rvs = list(mock_detail.get("rvs_per_star", []))
    mjds = list(mock_detail.get("mjds_per_star", []))
    errs = list(mock_detail.get("errors_per_star", []))

    n_stars_detail = max(len(rvs), len(mjds), len(errs))

    stars: dict = {}
    for i in range(n_stars_detail):
        rv_i = np.asarray(rvs[i], dtype=float) if i < len(rvs) else np.array([], dtype=float)
        mjd_i = np.asarray(mjds[i], dtype=float) if i < len(mjds) else np.array([], dtype=float)
        err_i = np.asarray(errs[i], dtype=float) if i < len(errs) else np.array([], dtype=float)
        stars[i] = {"rv": rv_i, "mjd": mjd_i, "err": err_i}

    meta = {
        "seed": mock_detail.get("seed"),
        "n_stars": mock_detail.get("n_stars", n_stars_detail),
        "true_f_bin": mock_detail.get("true_f_bin"),
        "true_pi": mock_detail.get("true_pi"),
        "true_sigma": mock_detail.get("true_sigma"),
        "true_logPmax": mock_detail.get("true_logPmax"),
        "error_model": mock_detail.get("error_model"),
        "error_params": mock_detail.get("error_params"),
        "source_npz": str(source_npz),
        "timestamp": timestamp_iso,
        "delta_rv_sample": np.asarray(
            mock_detail.get("delta_rv_sample", []), dtype=float
        ),
    }

    np.savez(
        mock_dir / "mock_stars.npz",
        stars=stars,
        meta=meta,
    )
    return mock_dir / "mock_stars.npz"


# ─────────────────────────────────────────────────────────────────────────────
# Load
# ─────────────────────────────────────────────────────────────────────────────

def load_bin_sensitivity_run(
    path: str | Path,
) -> tuple[list[SchemeResult], dict, dict | None]:
    """Reverse of :func:`save_bin_sensitivity_run`.

    Returns ``(results, settings, mock_detail_or_None)`` where ``mock_detail``
    is the fully-rehydrated dict including ``stars={idx: {rv, mjd, err}, ...}``
    and ``meta`` (or ``None`` in real-observation mode).
    """
    p = Path(path)
    with np.load(p, allow_pickle=True) as d:
        n = int(len(d["scheme_names"]))

        scheme_names = [str(x) for x in d["scheme_names"]]
        scheme_families = [str(x) for x in d["scheme_families"]]
        scheme_edges = list(d["scheme_edges"])
        n_bins_arr = np.asarray(d["n_bins"], dtype=int)
        n_eff_arr = np.asarray(d["n_eff_bins"], dtype=int)
        best_fbin = np.asarray(d["best_fbin"], dtype=float)
        best_pi = np.asarray(d["best_pi"], dtype=float)
        hdi68_fbin = np.asarray(d["hdi68_fbin"], dtype=float)
        hdi68_pi = np.asarray(d["hdi68_pi"], dtype=float)
        logL_max = np.asarray(d["logL_max"], dtype=float)
        aic = np.asarray(d["aic"], dtype=float)
        ks_D = np.asarray(d["ks_D"], dtype=float)
        ks_p = np.asarray(d["ks_p"], dtype=float)
        logL_map = list(d["logL_map"])
        marginal_fbin = list(d["marginal_fbin"])
        marginal_pi = list(d["marginal_pi"])
        sim_cdf_median = list(d["sim_cdf_median"])
        sim_cdf_q16 = list(d["sim_cdf_q16"])
        sim_cdf_q84 = list(d["sim_cdf_q84"])
        cdf_x = list(d["cdf_x"])
        n_obs_per_bin = list(d["n_obs_per_bin"])
        n_sim_per_bin = list(d["n_sim_per_bin"])
        status = [str(x) for x in d["status"]]
        status_reasons = list(d["status_reasons"])
        ground_truth = list(d["ground_truth"])

        settings_json = str(_unwrap_scalar(d["settings"]))
        try:
            settings = json.loads(settings_json) if settings_json else {}
        except Exception:
            settings = {}
        mock_mode = bool(_unwrap_scalar(d["mock_mode"]))

    results: list[SchemeResult] = []
    for i in range(n):
        gt_i = _unwrap_scalar(ground_truth[i])
        if isinstance(gt_i, np.ndarray) and gt_i.size == 1:
            gt_i = gt_i.item()
        sr_i = status_reasons[i]
        if isinstance(sr_i, np.ndarray):
            sr_i = sr_i.tolist()
        results.append(SchemeResult(
            scheme=scheme_names[i],
            family=scheme_families[i],
            edges=np.asarray(scheme_edges[i], dtype=float),
            n_bins=int(n_bins_arr[i]),
            n_eff_bins=int(n_eff_arr[i]),
            best_fbin=float(best_fbin[i]),
            best_pi=float(best_pi[i]),
            hdi68_fbin=(float(hdi68_fbin[i, 0]), float(hdi68_fbin[i, 1])),
            hdi68_pi=(float(hdi68_pi[i, 0]), float(hdi68_pi[i, 1])),
            logL_max=float(logL_max[i]),
            aic=float(aic[i]),
            ks_D=float(ks_D[i]),
            ks_p=float(ks_p[i]),
            logL_map=np.asarray(logL_map[i], dtype=float),
            marginal_fbin=np.asarray(marginal_fbin[i], dtype=float),
            marginal_pi=np.asarray(marginal_pi[i], dtype=float),
            sim_cdf_median=np.asarray(sim_cdf_median[i], dtype=float),
            sim_cdf_q16=np.asarray(sim_cdf_q16[i], dtype=float),
            sim_cdf_q84=np.asarray(sim_cdf_q84[i], dtype=float),
            cdf_x=np.asarray(cdf_x[i], dtype=float),
            n_obs_per_bin=np.asarray(n_obs_per_bin[i], dtype=int),
            n_sim_per_bin=np.asarray(n_sim_per_bin[i], dtype=int),
            status=status[i],
            status_reasons=tuple(sr_i) if sr_i is not None else tuple(),
            ground_truth=(dict(gt_i) if isinstance(gt_i, dict) else None),
        ))

    mock_detail: dict | None = None
    if mock_mode:
        mock_dir = mock_obs_dir_for(p.name)
        mock_npz = mock_dir / "mock_stars.npz"
        if mock_npz.exists():
            with np.load(mock_npz, allow_pickle=True) as md:
                stars_raw = _unwrap_scalar(md["stars"])
                meta_raw = _unwrap_scalar(md["meta"])
            stars = {}
            if isinstance(stars_raw, dict):
                for k, v in stars_raw.items():
                    v = _unwrap_scalar(v)
                    if isinstance(v, dict):
                        stars[int(k)] = {
                            "rv": np.asarray(v.get("rv", []), dtype=float),
                            "mjd": np.asarray(v.get("mjd", []), dtype=float),
                            "err": np.asarray(v.get("err", []), dtype=float),
                        }
            meta = dict(meta_raw) if isinstance(meta_raw, dict) else {}
            mock_detail = {"stars": stars, "meta": meta}

    return results, settings, mock_detail


# ─────────────────────────────────────────────────────────────────────────────
# List / describe / delete / promote
# ─────────────────────────────────────────────────────────────────────────────

def list_bs_results() -> list[tuple[str, str]]:
    """Return ``[(display_label, full_path_str), ...]`` newest-first.

    Excludes the ``.partial_`` prefix (those are not yet confirmed).
    """
    _ensure_dirs()
    npzs = [p for p in RESULTS_DIR.glob("*.npz") if not p.name.startswith(".partial_")]
    npzs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    out = []
    for p in npzs:
        label = _describe_run(p)
        out.append((label, str(p)))
    return out


def list_bs_partials() -> list[tuple[str, str]]:
    """Return ``[(display_label, full_path_str), ...]`` of ``.partial_*.npz`` files, newest-first.

    Mirror of :func:`list_bs_results` for auto-saved (not-yet-promoted) runs.
    ``Path.glob`` on Unix does match names starting with a dot as long as the
    pattern explicitly starts with ``"."`` — which is why the pattern here is
    ``".partial_*.npz"`` (not ``"*.npz"``).
    """
    _ensure_dirs()
    npzs = [p for p in RESULTS_DIR.glob(".partial_*.npz")]
    npzs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    out = []
    for p in npzs:
        label = _describe_run(p)
        out.append((label, str(p)))
    return out


def _describe_run(path: Path) -> str:
    """Build a friendly display label by peeking at metadata."""
    try:
        with np.load(path, allow_pickle=True) as d:
            ts = str(_unwrap_scalar(d["timestamp"])) if "timestamp" in d.files else "??"
            mock = bool(_unwrap_scalar(d["mock_mode"])) if "mock_mode" in d.files else False
            n = int(len(d["scheme_names"])) if "scheme_names" in d.files else 0
        return f"{'MOCK' if mock else 'REAL'} | {n} schemes | {ts} | {path.name}"
    except Exception:
        return f"{path.name} (unreadable)"


def promote_partial(partial_path: str | Path) -> Path:
    """Rename ``.partial_foo.npz`` → ``foo.npz``.

    The mock_observations subdir already uses the permanent stem (see
    :func:`_permanent_stem`) so no directory rename is needed.
    """
    pp = Path(partial_path)
    if not pp.name.startswith(".partial_"):
        raise ValueError(f"Not a partial file: {pp.name}")
    final_name = pp.name[len(".partial_"):]
    final = RESULTS_DIR / final_name
    pp.rename(final)
    return final


def delete_bs_result(path: str | Path) -> None:
    """Delete the NPZ and its associated ``mock_observations/<stem>`` subdir."""
    p = Path(path)
    if p.exists():
        p.unlink()
    mock_dir = mock_obs_dir_for(p.name)
    if mock_dir.exists():
        shutil.rmtree(mock_dir)


# ─────────────────────────────────────────────────────────────────────────────
# Self-test
# ─────────────────────────────────────────────────────────────────────────────

def _fake_scheme_result(
    name: str, family: str, edges: np.ndarray, gt: dict | None
) -> SchemeResult:
    n_bins_total = int(max(edges.size - 1, 1))
    n_obs = np.array([3, 2, 5, 0], dtype=int)[:n_bins_total]
    n_sim = np.array([4, 3, 4, 1], dtype=int)[:n_bins_total]
    if n_obs.size < n_bins_total:
        pad = n_bins_total - n_obs.size
        n_obs = np.concatenate([n_obs, np.zeros(pad, dtype=int)])
        n_sim = np.concatenate([n_sim, np.zeros(pad, dtype=int)])
    return SchemeResult(
        scheme=name,
        family=family,
        edges=edges.astype(float),
        n_bins=n_bins_total,
        n_eff_bins=int(np.sum(n_obs > 0)),
        best_fbin=0.42,
        best_pi=-1.3,
        hdi68_fbin=(0.35, 0.50),
        hdi68_pi=(-2.0, -0.7),
        logL_max=-123.45,
        aic=256.9,
        ks_D=0.12,
        ks_p=0.87,
        logL_map=np.linspace(-200, -100, 12).reshape(3, 4).astype(float),
        marginal_fbin=np.array([0.1, 0.3, 0.4, 0.2], dtype=float),
        marginal_pi=np.array([0.25, 0.25, 0.25, 0.25], dtype=float),
        sim_cdf_median=np.linspace(0, 1, 8, dtype=float),
        sim_cdf_q16=np.linspace(0, 1, 8, dtype=float) * 0.9,
        sim_cdf_q84=np.linspace(0, 1, 8, dtype=float) * 1.1,
        cdf_x=np.linspace(0, 350, 8, dtype=float),
        n_obs_per_bin=n_obs,
        n_sim_per_bin=n_sim,
        status="OK",
        status_reasons=("P1", "P5") if name.endswith("2") else (),
        ground_truth=gt,
    )


def _assert_equal_scheme(r1: SchemeResult, r2: SchemeResult) -> None:
    for f in fields(SchemeResult):
        v1 = getattr(r1, f.name)
        v2 = getattr(r2, f.name)
        if isinstance(v1, np.ndarray):
            assert np.array_equal(v1, v2), f"field {f.name} mismatch"
        elif f.name == "ground_truth":
            assert v1 == v2, f"ground_truth mismatch: {v1} vs {v2}"
        elif f.name in ("hdi68_fbin", "hdi68_pi", "status_reasons"):
            assert tuple(v1) == tuple(v2), f"{f.name}: {v1} vs {v2}"
        else:
            assert v1 == v2, f"{f.name}: {v1} vs {v2}"


if __name__ == "__main__":
    print("── bin_sensitivity_storage self-test ──")
    _ensure_dirs()

    # 1) Build 3 fake SchemeResults; 2 with ground_truth, 1 without.
    r1 = _fake_scheme_result(
        "equal_width_10", "equal_width", np.linspace(0, 300, 11),
        gt={"f_bin": 0.5, "pi": -1.0, "sigma": 6.0, "logPmax": 3.5},
    )
    r2 = _fake_scheme_result(
        "equal_count_8_v2", "equal_count", np.array([0, 30, 50, 80, 120, 170, 230, 300.0]),
        gt={"f_bin": 0.4, "pi": -1.5, "sigma": 5.5, "logPmax": 3.0},
    )
    r3 = _fake_scheme_result(
        "manual_sparse", "manual", np.array([0, 50, 200.0]),
        gt=None,
    )
    fake_results = [r1, r2, r3]

    # 2) Save as partial, mock-mode.
    mock_detail = {
        "rvs_per_star": [np.array([1.0, 2.0, 3.0]), np.array([4.0, 5.0])],
        "mjds_per_star": [np.array([59000.0, 59010.0, 59020.0]), np.array([59500.0, 59510.0])],
        "errors_per_star": [np.array([1.0, 1.0, 1.0]), np.array([2.0, 2.0])],
        "seed": 42,
        "n_stars": 2,
        "true_f_bin": 0.5,
        "true_pi": -1.0,
        "true_sigma": 6.0,
        "true_logPmax": 3.5,
        "error_model": "fixed",
        "error_params": (),
        "delta_rv_sample": np.array([100.0, 200.0]),
    }
    filename = build_bs_filename(mock_mode=True)
    print(f"    filename: {filename}")
    partial = save_bin_sensitivity_run(
        fake_results,
        {"foo": 1, "fbin_grid": [0.0, 0.5, 1.0]},
        mock_detail=mock_detail,
        source_npz="test.npz",
        filename=filename,
        is_partial=True,
    )
    print(f"    saved partial -> {partial.relative_to(PROJECT_ROOT)}")
    assert partial.exists(), "partial file not written"
    assert partial.name.startswith(".partial_"), "partial prefix missing"

    # 3) Round-trip: load + field-by-field compare.
    results, settings, mock_back = load_bin_sensitivity_run(partial)
    assert len(results) == 3, "wrong number of results"
    for i, (r_in, r_out) in enumerate(zip(fake_results, results)):
        _assert_equal_scheme(r_in, r_out)
    assert settings == {"foo": 1, "fbin_grid": [0.0, 0.5, 1.0]}, f"settings mismatch: {settings}"
    assert mock_back is not None, "mock_detail should round-trip"
    assert set(mock_back["stars"].keys()) == {0, 1}, f"stars keys: {mock_back['stars'].keys()}"
    assert np.array_equal(mock_back["stars"][0]["rv"], np.array([1.0, 2.0, 3.0]))
    assert np.array_equal(mock_back["stars"][1]["mjd"], np.array([59500.0, 59510.0]))
    assert mock_back["meta"]["seed"] == 42
    assert mock_back["meta"]["true_f_bin"] == 0.5
    print("    round-trip: all 22 SchemeResult fields + settings + mock_detail match")

    # 4) promote_partial — file moves to permanent location.
    promoted = promote_partial(partial)
    assert promoted.exists(), "promoted file missing"
    assert not partial.exists(), "partial file still present"
    assert promoted.name == filename, f"promoted name wrong: {promoted.name}"
    print(f"    promoted -> {promoted.relative_to(PROJECT_ROOT)}")

    # 5) list_bs_results — should include promoted, exclude any partials.
    listed = list_bs_results()
    paths_listed = [p for (_, p) in listed]
    assert str(promoted) in paths_listed, "promoted file not in list"
    for (_, pth) in listed:
        assert not Path(pth).name.startswith(".partial_"), "partial leaked into list"
    print(f"    list_bs_results returned {len(listed)} entry/entries (newest first)")

    # 6) delete_bs_result — file + mock subdir gone.
    mock_dir = mock_obs_dir_for(promoted.name)
    assert mock_dir.exists(), "mock subdir should exist before delete"
    delete_bs_result(promoted)
    assert not promoted.exists(), "file not deleted"
    assert not mock_dir.exists(), "mock subdir not deleted"
    print("    delete_bs_result: main file + mock_observations/<stem>/ removed")

    # 6b) list_bs_partials — after the final delete + straggler-cleanup
    #     pass below, there should be no ``.partial_*.npz`` left.
    for leftover in RESULTS_DIR.glob(".partial_bin_sensitivity_mock_*"):
        try:
            leftover.unlink()
        except OSError:
            pass
    partials_after = list_bs_partials()
    assert partials_after == [], (
        f"list_bs_partials() should be empty after cleanup, got: "
        f"{[p for (_, p) in partials_after]}"
    )
    print("    list_bs_partials: returned [] after all partials removed")

    # 7) Cleanup any stragglers from prior runs (safety net).
    for leftover in RESULTS_DIR.glob(".partial_bin_sensitivity_mock_*"):
        try:
            leftover.unlink()
        except OSError:
            pass

    print("── self-test PASSED ──")
