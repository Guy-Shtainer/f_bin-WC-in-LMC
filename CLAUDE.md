# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.
For detailed architecture, plot styles, and learnings, see `.claude/references/`.

## Project Overview

Spectroscopic analysis pipeline for Wolf-Rayet (WR) stars in the LMC. Goal: measure radial velocities (RVs) from multi-epoch spectroscopy, classify binary/single stars, and constrain the binary fraction with Monte-Carlo bias correction.

**Instruments:** VLT/X-SHOOTER (UVB/VIS/NIR bands), NRES
**Stars:** 25 WR stars listed in `specs.py`
**Key algorithm:** Cross-Correlation Function (CCF) via Zucker & Mazeh (1994) / Zucker et al. (2003)

## Project Structure

- `pipeline/` — standalone CLI scripts (each starts with `sys.path.insert(0, parent_dir)`)
- `app/` — Streamlit web app (`streamlit run app/app.py`)
- `settings/` — `user_settings.json` (master), `run_history.json`, `states/`, `presets/`
- `results/` — saved grid outputs (.npz) with embedded `config_hash`
- `plots/` — saved publication figures
- `../output/` — **NEVER CHANGE THIS PATH** — existing CCF plot output one level above project root
- `.claude/references/` — detailed architecture, plot style, code standards, learnings

**Architecture details:** See `.claude/references/architecture.md`

## Running the Analysis

```bash
conda run -n guyenv streamlit run app/app.py          # primary workflow
conda run -n guyenv python pipeline/dsilva_grid.py     # CLI pipeline
conda run -n guyenv python ccf_tasks.py                # legacy
```

## Performance Preferences

- **Multiprocessing:** Always use `os.cpu_count() - 1` cores
- **Speed over memory:** Pre-allocation, vectorization, lookup tables, in-memory caching freely

## Webapp Conventions (app/)

- Sidebar "Save state" button on every page → `settings/states/{timestamp}_{name}.json`
- `.npz` result files store `config_hash` — check for matching hash before rerunning
- `@st.cache_data` with no expiry. Manual "Clear cache" in Settings only
- Plotly for all interactive charts (not matplotlib)
- Import convention for `app/pages/`: `from shared import ...` (NOT `from app.shared import ...`)

## Key Conventions

- **Git:** Always commit to `main`. `agent/*` branches = unconfirmed. Check `git branch` before committing
- **Data symlink:** `Data/` → `../Data`. Git ops destroy it. Fix: `ln -s ../Data Data`
- **Binary detection:** (1) ΔRV > 45.5 km/s AND (2) ΔRV − 4σ > 0. Line: `C IV 5808-5812`. Result: 13/28 ≈ 46%
- **MJD source:** `fit.header['MJD-OBS']` — NOT in RV property dict
- **numpy.bool_:** Always cast with `bool()` before `is True` checks
- **Wavelengths:** FITS files in nm. Display in Å: `wave_nm * 10.0`. NRES already in Å

## Do Not Touch Working Code

When fixing a bug, follow ALL five blocks. No exceptions.

1. **ROOT CAUSE FIRST** — State: "The bug is at file:line because X." No edits until identified.
2. **ONE FILE ONLY** — Touching a second file requires explicit user justification.
3. **REVERT TEST** — "If I revert every OTHER change, does the fix still work?"
4. **ASK BEFORE REFACTORING** — Don't touch "improvable" code near the bug.
5. **FLAG WORKING CODE** — Use `# WORKING — do not change this code` above verified working segments. NEVER modify flagged code unless user explicitly asks.

See `.claude/references/learnings.md` for the full pre-fix checklist.

## Code Quality Rules

- **File size:** Max ~800 lines. Pre-plan splits using thin-wrapper pattern
- **Testing:** integration test → py_compile → render test. See `.claude/references/code-standards.md`
- **Common errors:** Check `COMMON_ERRORS.md` before/after edits. Add new errors immediately after fixing
- **Commits:** Each logical change separately. After push → update `GIT_LOG.md`
- **Backups:** `cp app/pages/{file} Backups/{file}.bak` before editing pages
- **TODO:** Set status to `to-test` on completion — NEVER `done`
- **Progress bars:** `st.progress()` for any computation >5 seconds
- **Documentation:** Update `DOCUMENTATION.md` at session end (scientific prose, not changelog)

## Context Management

- Use `/compact` after completing each major task within a session
- Use `/clear` when switching between unrelated work areas
- After ANY code edit: run `/error-check` → if clean, offer to `/git` commit

## Graph Style

See `.claude/references/plot-style.md` for full style guide.
Key rule: Use `PLOTLY_THEME` from `app/shared.py` — never hardcode plot colors.
After ANY plot feedback → update `memory/plot_preferences.md`.
