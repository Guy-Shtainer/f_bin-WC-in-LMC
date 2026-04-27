# Plan — Validation Run Persistence (mock_results/)

**Owner:** coder agent
**Date:** 2026-04-23
**Scope:** Single-Point Recovery validation flow only (batch sweep deferred)
**Design confirmed by user** — see AskUserQuestion answers at top of conversation on 2026-04-23.

## Goal
Every validation run auto-saves its full result + mock observations to disk so Guy can reload prior validation runs and re-render the Recovery Diagnostics panels instantly. Mirror the existing `results/` save/load UX exactly.

## On-disk layout

```
<repo_root>/
├── results/                                       (existing, untouched)
│   └── cadence_{dsilva|langer}_*.npz
├── mock_results/                                  (NEW)
│   ├── validation_{dsilva|langer}_*.npz           ← grid result (mirror of results/ payload)
│   ├── validation_{dsilva|langer}_partial_*.npz   ← 120s autosave checkpoint
│   └── mock_observations/                         (NEW subdir)
│       └── validation_{dsilva|langer}_<stem>/     ← subdir named after result basename (no .npz)
│           └── mock_stars.npz                     ← pickled-dict keyed by star index
```

### Filename schema
Same convention as normal runs (use `_build_descriptive_filename` as a template) but:
- Prefix `validation_` instead of `cadence_`
- Model still `dsilva` / `langer`
- Encode the **truth** params (`_fbT{val}_piT{val}_sigT{val}_logPT{val}_seed{val}`) alongside the grid range (so two runs with same truth but different recovery grids have different names)
- Same timestamp format: `%d%m%y-%H%M`

Example: `validation_dsilva_fbT0.46_piT0.00_sigT15.0_logPT4.00_seed42_fb0.0-1.0x49_pi-3.0-3.0x50_N500_sig3.0-13.0x50_230426-1530.npz`

### Top-level `.npz` payload
**Everything the regular cadence run saves** (see full key list in save-pipeline mapping) **PLUS**:
- `is_validation = True`
- `true_fbin`, `true_pi`, `true_sigma`, `true_logPmax`, `seed` (truth params)
- `mock_delta_rv` (the mock observations ΔRV array — already in cadence result when `is_validation=True`)
- `mock_stars_subdir` — relative path to the mock_observations subdir (for cross-reference)

### `mock_stars.npz` payload
Pickled dict, keyed by integer star index (per user's explicit spec). Saved with `allow_pickle=True`:

```python
stars = {
    0: {
        'rvs':    np.array([...], dtype=float),   # per-epoch RVs [km/s]
        'times':  np.array([...], dtype=float),   # per-epoch MJDs [days]
        'errs':   np.array([...], dtype=float),   # per-epoch sigma [km/s] — sigma_meas broadcast to match rvs
        'is_binary': bool,                        # ground truth
    },
    1: {...},
    ...
    N-1: {...},
}
np.savez(path, stars=np.array(stars, dtype=object), allow_pickle=True)
```

- Star index = position in `cadence_library` (integer 0..N-1), **NOT** a WR name. Mock stars don't correspond to real WRs.
- `errs` array has the same length as `rvs`. In the current mock generator `sigma_meas` is a scalar, so broadcast: `errs = np.full_like(rvs, sigma_meas)`. Keep it per-RV to allow future heteroscedastic mocks.

---

## Implementation stages

### Stage 1 — New IO module `app/bc/validation_io.py`

Create from scratch. Public API:

```python
def build_validation_filename(
    model: str, truth: dict, grid_ranges: dict, partial: bool = False
) -> str: ...

def validation_result_path(filename: str) -> Path:
    """<repo_root>/mock_results/<filename>"""

def mock_observations_dir(result_filename: str) -> Path:
    """<repo_root>/mock_results/mock_observations/<stem>/"""

def save_validation_result(
    result: dict, mock_detail: dict, truth: dict, *, partial: bool = False
) -> tuple[str, str]:
    """Save (a) result .npz → mock_results/, (b) mock_stars.npz → subdir.
    Returns (result_path, mock_stars_path).
    For partial=True, only the result .npz is updated (mock_stars is stable, so
    write it once on the first partial save and skip on subsequent partials)."""

def list_validation_results(model: str) -> list[tuple[str, str]]:
    """Glob mock_results/validation_{model}_*.npz, exclude _partial_,
    return [(display_name, full_path)] sorted newest-first."""

def list_validation_partials(model: str) -> list[tuple[str, str]]:
    """Mirror for _partial_ files."""

def load_validation_result(path: str) -> tuple[dict, dict | None]:
    """Load result .npz + sibling mock_stars.npz. Returns (result_dict, mock_detail_or_None).
    mock_detail is None if the mock_stars file is missing."""

def scan_validation_metadata(paths: list[str]) -> pd.DataFrame:
    """Mirror of _scan_result_metadata but for validation files. Columns:
    Date, truth_f_bin, truth_pi, truth_sigma, truth_logPmax, seed,
    f_bin range, pi range, sigma range, logP range, N_stars, N_sets,
    sigma_meas, period_model, best_fbin, best_pi, best_sigma, Runtime,
    File name, _path. Cached @30s TTL via st.cache_data."""
```

Reuse helpers from `app/bc/file_ops.py` where possible (timestamp formatter, grid-range encoder). Do NOT duplicate; import and wrap.

### Stage 2 — Wire auto-save into the run

In [app/bc/runners_cadence.py](app/bc/runners_cadence.py), the background runner `_run_cadence_bg()`:
- Currently checks `params.get('skip_save')` — respect this flag but add a new branch: when `params.get('is_validation')` is True AND `skip_save` is False → route saves to `validation_io` instead of the normal `results/` path.
- Partial checkpoint (`_save_partial_cadence`) also needs the same branching. Add `params['save_backend']` = `'results'` (default) | `'mock_results'` to select.

In [app/bc/render_validation.py](app/bc/render_validation.py), where `skip_save=True` is set (line ~668 in the mapping), change to `skip_save=False, save_backend='mock_results'` and pass `truth` + `mock_detail` to the runner so the saver has everything it needs.

**Threading note**: the runner runs in a background thread (`threading.Thread`). `validation_io.save_validation_result` must be thread-safe (file I/O in a bg thread is fine; just no `st.*` calls inside). The partial save thread already writes safely — mirror that pattern.

### Stage 3 — UI dropdown in render_validation.py

At the top of the Single-Point Recovery tab (above the truth-params sliders), add a result-file table + Load/Delete buttons mirroring the Cadence Dsilva tab's pattern (see `app/bc/cadence.py` around line 1052 for reference — how the dataframe `on_select='rerun'` hook drives load/delete).

Schema:
- Table columns: Date, truth_f_bin, truth_pi, truth_sigma, truth_logPmax, seed, grid ranges, period_model, best_fbin, Runtime, File name
- Single-row selection reveals **Load** / **Delete** buttons
- **Load**: calls `load_validation_result` → pushes result dict to `st.session_state[f'{p}_result']`, pushes mock_detail to `st.session_state[f'{p}_val_mock_detail']`, pushes truth to `st.session_state[f'{p}_val_mock_params']`, then `st.rerun()`. The Recovery Diagnostics section below will re-render from these session_state keys exactly as if a fresh run just completed (per "Re-render stored panels only").
- **Delete**: remove .npz + mock_observations/<stem>/ subdir + confirm dialog

Also show a small "Resume partial" row for partial .npz files, with a Resume button (matches the existing partial-resume pattern in cadence.py).

### Stage 4 — Plot display while loading

After loading a saved validation run, the user scrolls down and sees the exact same Recovery Diagnostics section. No conditional rendering — the data source (session_state) is identical whether it came from a fresh run or disk. This is already how the Cadence tab works — no new code needed if session_state wiring in Stage 3 is correct.

---

## Constraints

- **Do NOT** touch the existing `results/` save/load path. Validation is a new parallel lane.
- **Do NOT** refactor `file_ops.py` — import from it.
- **Do NOT** skip the mock_stars file even when it's redundant with `mock_delta_rv` — the user explicitly asked for per-star RV / time / error arrays to be persisted.
- **File size cap**: `render_validation.py` is already 1324 lines (above the 800 soft cap per CLAUDE.md). Prefer putting new helpers in `validation_io.py`. If `render_validation.py` grows past 1500, split the Recovery Diagnostics section into its own module — but only if unavoidable this sprint.
- **No markdown/docs** written by the coder. This plan is the spec.
- **Surgical edits** to existing files. WORKING-flagged code is untouched unless absolutely necessary.

## Test plan

1. `conda run -n guyenv python -m pyflakes app/bc/validation_io.py app/bc/runners_cadence.py app/bc/render_validation.py`
2. `conda run -n guyenv python scripts/test_render.py`
3. Manual: launch app → Bias Correction → Validation → Single-Point Recovery → set truth → Run → verify `mock_results/` has (a) `validation_dsilva_*.npz` final and (b) `mock_observations/<stem>/mock_stars.npz` with a pickled dict of 25 (or cadence-library-length) star entries.
4. Manual: pick the saved row in the new table → Load → Recovery Diagnostics panels re-render with identical content.
5. Manual: run a long validation, kill it mid-run → confirm `validation_dsilva_partial_*.npz` exists and is loadable via Resume.

## Commit plan

Do NOT commit. After all stages ship + tests pass, hand back to orchestrator. Orchestrator will hand to QA for visual check, then Guy for sign-off, then `/git`.
