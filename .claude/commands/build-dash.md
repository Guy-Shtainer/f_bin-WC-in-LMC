---
description: "Implement the next batch of Dash features from FEATURES.md"
argument-hint: "[batch_num | 'next' | 'status']"
---

# Autonomous Dash Feature Builder

You are implementing features for the Plotly Dash webapp in `bias_app/`.
Follow each phase precisely. Write status to `.claude/dash-builder-status.json` at every phase.

## Batch Grouping Table

Features are grouped into batches matching FEATURES.md sections. Execute in this order.

### Quick wins — wire existing factories
```
BATCH 1  — Part 6: σ 1D slices (missing per method)           — 4 items  — detail_plots_cb.py
BATCH 2  — Part 6: Score profiles (score vs σ, score vs logP)  — 2 items  — NEW: per-method profile callbacks
BATCH 3  — Part 6: Extra 2D heatmaps (fbin×logP, σ×logP)      — 2 items  — method_figures.py + callbacks
BATCH 4  — Part 6: Best-fit metrics (HDI, slice vs global)     — 3 items  — scoring_cb.py + scoring_tabs.py
BATCH 5  — Part 6: Per-method summary table + corner auto-axes — 2 items  — analysis callbacks
BATCH 6  — Part 5: Method summary HDI + agreement column       — 4 items  — scoring_cb.py
BATCH 7  — Part 5: Sim tab toggles (Case A/B, density, pop)   — 5 items  — scoring_tabs.py + sim_plots_cb.py
BATCH 8  — Part 5: Methodology equations (LaTeX expanders)     — 2 items  — scoring_tabs.py
BATCH 9  — Helper plot builders (min score, CDF sanity)        — 2 items  — figures.py / detail_figures.py
```

### Medium complexity — new UI + callbacks
```
BATCH 10 — Part 7: Scoring detail — log toggle + exclusion     — 3 items  — NEW scoring_detail_cb.py
BATCH 11 — Part 7: Scoring detail — masked heatmaps            — 3 items  — detail_figures.py + scoring_detail_cb.py
BATCH 12 — Part 7: Parabolic fitting + 3D surface              — 4 items  — NEW surface_figures.py + fitting callbacks
BATCH 13 — Part 7: 1D fit slices + re-simulation CDF           — 3 items  — surface_figures.py + callbacks
BATCH 14 — Part 7: Likelihood-specific (CDF+bins, table, LaTeX)— 4 items  — NEW likelihood_cb.py
BATCH 15 — Part 3: Run controls (view mode, N sets, bin config)— 3 items  — param_panels.py + callbacks
BATCH 16 — Part 3: Cancel & Save + partial results             — 4 items  — persistence_cb.py + simulation callbacks
BATCH 17 — Part 3: Result management (delete, descriptive fn)  — 4 items  — result_browser_cb.py
BATCH 18 — Part 2: Error model selector + params               — 3 items  — param_panels.py + simulation callbacks
BATCH 19 — Part 2: Langer extras (dist type, q flip)           — 2 items  — param_panels.py + ui_callbacks.py
```

### Pages with new modules
```
BATCH 20 — Part 8: Compare tab extensions                      — 5 items  — comparison.py
BATCH 21 — Part 9: RV Errors — threshold + filter + histogram  — 5 items  — rv_errors.py + NEW rv_errors_cb.py
BATCH 22 — Part 9: RV Errors — auto-fit + history + Q-Q        — 6 items  — rv_errors_cb.py + rv_error_figures.py
BATCH 23 — Part 1: Page-level (canvas, tabs, toasts, captions) — 5 items  — app.py + pages
```

### High complexity — architectural changes
```
BATCH 24 — Part 4: Live polling infrastructure (dcc.Interval)  — 4 items  — NEW live_polling_cb.py
BATCH 25 — Part 4: Live heatmaps (4 methods, 2×2 grid)        — 4 items  — live_polling_cb.py + live_figures.py
BATCH 26 — Part 4: Live profiles + cancel modes                — 4 items  — live_polling_cb.py
BATCH 27 — Part 10: Infrastructure (notifications, new instance)— 3 items  — app.py + misc
```

## Phase 0: Select Batch

Read `bias_app/FEATURES.md`. Count how many `[ ]` items remain in each batch group.

If `$ARGUMENTS` is a number → select that batch.
If `$ARGUMENTS` is `status` → print a progress report (checked/total per batch) and STOP.
If `$ARGUMENTS` is `next` or empty → select the first batch with unchecked items.

If ALL batches are complete, print "ALL FEATURES COMPLETE" and STOP.

Write initial status:
```json
{
  "batch": <number>,
  "batch_name": "<name>",
  "phase": "starting",
  "cycle": 0,
  "started_at": "<ISO timestamp>",
  "features_target": ["<list of feature descriptions>"],
  "log": [{"time": "<HH:MM:SS>", "msg": "Starting batch N"}]
}
```

## Phase 1 — Cycle 1: Explore & Implement

Update status: `"phase": "cycle_1", "cycle": 1`

### 1a. Explore

Read ALL of these files to understand existing Dash patterns:
- `bias_app/FEATURES.md` — exact requirements for each feature in this batch
- `bias_app/config.py` — themes, scoring methods, color constants
- `bias_app/components/figures.py` — simulation tab figure factories (FOLLOW THIS PATTERN)
- `bias_app/components/detail_figures.py` — D-stat/slice figure factories
- `bias_app/components/method_figures.py` — per-method figure factories
- `bias_app/components/scoring_tabs.py` — layout components (Graph/Store targets)
- `bias_app/components/param_panels.py` — parameter input panels
- `bias_app/callbacks/detail_plots_cb.py` — callback registration pattern
- `bias_app/callbacks/scoring_cb.py` — scoring callback pattern
- `bias_app/callbacks/sim_plots_cb.py` — simulation plot callbacks
- `COMMON_ERRORS.md` — known pitfalls (scan for relevant ones)
- `.claude/skills/developing-with-dash/SKILL.md` — Dash/DMC reference

Read the Streamlit source to understand WHAT each plot does (logic/data):
- `app/bc/analysis.py` — method summary, CDF comparison, heatmaps, best-fit, corner calls
- `app/bc/sim_plots.py` — period dist, binary fraction vs threshold, orbital histograms
- `app/bc/scoring_detail.py` — CvM/Likelihood detail: log toggle, exclusion, masked heatmaps, parabolic fit
- `app/bc/fitting.py` — parabolic fitting logic (height/range/neighborhood modes)
- `app/bc/likelihood_viz.py` — likelihood CDF with bins, per-bin table, explanation
- `app/bc/corner_plots.py` — corner plot rendering (N×N, HDI, contours)
- `app/bc/polling.py` — live polling fragment (job dict, heatmap updates, progress)
- `app/bc/helpers.py` — color helpers, methodology expanders, 1D chart builders
- `app/bc/extras.py` — RV errors tab, compare tab
- `app/bc/file_ops.py` — result loading, metadata, partial results

Read the FULL content of files you will modify, not just the headers.
The Streamlit code shows the LOGIC — translate it to Dash callbacks + figure factories.

### 1b. Implement

For each feature in this batch:
1. Identify which file(s) need editing
2. Follow the EXACT pattern of existing code in those files:
   - Figure factories: accept `theme: dict`, return `go.Figure`
   - Callbacks: use closure-capture pattern from `detail_plots_cb.py`
   - Layout: add `dcc.Graph(id='{prefix}-{method}-{feature}')` in `scoring_tabs.py`
3. Use colors from `config.py` (COLOR_GOLD, METHOD_COLORS, etc.) — NEVER hardcode
4. Use themes from `config.py` (`get_plotly_theme()`) — NEVER hardcode

After EACH file edit, immediately run:
```bash
conda run -n guyenv python -m py_compile <file>
```
Fix any syntax errors before moving to the next file.

### 1c. Test (Cycle 1)

After all features are implemented, run these tests:

**Test 1 — py_compile all modified files:**
```bash
for f in <list of modified files>; do
  conda run -n guyenv python -m py_compile "$f"
done
```

**Test 2 — Import test each modified module:**
```bash
conda run -n guyenv python -c "
import sys, os
sys.path.insert(0, 'bias_app')
sys.path.insert(0, '.')
# Import each modified module
import config
from components.detail_figures import make_d_heatmap_fig, make_1d_slice_fig
# ... add imports for all modified modules
print('All imports OK')
"
```

**Test 3 — Smoke test new figure factories (with synthetic data):**
```bash
conda run -n guyenv python -c "
import sys; sys.path.insert(0, 'bias_app'); sys.path.insert(0, '.')
import numpy as np
from config import get_plotly_theme
theme = get_plotly_theme('dark')
# Call each new/modified figure factory with dummy data
# Example: fig = make_d_heatmap_fig(np.random.rand(5,5), np.linspace(0.1,0.9,5), np.linspace(-3,3,5), 'K-S', '#4A90D9', theme)
# assert len(fig.data) > 0
print('Figure factories OK')
"
```

**Test 4 — COMMON_ERRORS scan:**
Read `COMMON_ERRORS.md`, extract all regex patterns, grep each modified file.

**Test 5 — Full app import:**
```bash
conda run -n guyenv python -c "
import sys; sys.path.insert(0, 'bias_app'); sys.path.insert(0, '.')
from dash import _dash_renderer
_dash_renderer._set_react_version('18.2.0')
from app import app
print(f'App loaded: {len(app.callback_map)} callbacks')
"
```

Fix any failures found. Max 2 retries per file. If a specific feature is unfixable,
revert that feature's changes with `git checkout -- <file>` and log it.

## Phase 2 — Cycle 2: Review & Improve

Update status: `"phase": "cycle_2", "cycle": 2`

### 2a. Re-read

Re-read EVERY file you modified in Cycle 1 — the FULL file, not just your changes.

### 2b. Review checklist

For each modified file, verify:
- [ ] Follows the EXACT same code pattern as existing functions in the same file
- [ ] All figure factories accept `theme: dict` parameter
- [ ] No hardcoded colors (uses `config.py` constants or `theme`)
- [ ] Callback IDs use the correct `{prefix}-{method}-{id}` pattern
- [ ] Layout components (`dcc.Graph`, `dcc.Store`) exist for every callback Output
- [ ] No unused imports
- [ ] Docstrings match the style of existing functions
- [ ] Any new array operations handle edge cases (empty arrays, NaN values)

### 2c. Fix

Fix/rewrite anything that fails the review checklist.
Do NOT skip items — each checklist point matters.

### 2d. Re-test

Re-run ALL 5 tests from Phase 1 (1c). Fix any new failures.

## Phase 3 — Cycle 3: Final Hardening

Update status: `"phase": "cycle_3", "cycle": 3`

### 3a. Final read

Re-read every modified file one last time.

### 3b. Cross-checks

Run these additional checks:

**Check 1 — No duplicate callback Output IDs:**
```bash
conda run -n guyenv python -c "
import sys; sys.path.insert(0, 'bias_app'); sys.path.insert(0, '.')
from dash import _dash_renderer
_dash_renderer._set_react_version('18.2.0')
from app import app
outputs = []
for cb_id, cb_info in app.callback_map.items():
    outputs.append(cb_id)
dupes = [o for o in outputs if outputs.count(o) > 1]
if dupes:
    print(f'DUPLICATE OUTPUTS: {set(dupes)}')
    raise SystemExit(1)
print(f'No duplicate outputs ({len(outputs)} callbacks)')
"
```

**Check 2 — File size limit:**
```bash
for f in <list of modified files>; do
  lines=$(wc -l < "$f")
  if [ "$lines" -gt 800 ]; then
    echo "WARNING: $f has $lines lines (limit 800)"
  fi
done
```
If any file exceeds 800 lines, split it before committing.

**Check 3 — Re-run full test suite (Tests 1-5 from Phase 1)**

### 3c. Fix any remaining issues

This is the last chance. If something is still broken after 2 fix attempts,
revert ONLY that feature's changes and log the failure.

## Phase 4: Commit

Update status: `"phase": "commit"`

1. Verify Data symlink: `ls -la Data` — if missing: `ln -s ../Data Data`
2. `git add` ONLY the specific files you modified in `bias_app/`
3. Commit with descriptive message:
   ```
   Dash batch N: <batch name>

   Implemented:
   - Feature description 1
   - Feature description 2
   ...

   3-cycle quality verification passed.

   Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
   ```
4. Update `bias_app/FEATURES.md`: change `[ ]` → `[x]` for completed features
5. `git add bias_app/FEATURES.md` and commit separately:
   ```
   Update FEATURES.md: batch N complete (X/70 total)
   ```

## Phase 5: Report & Exit

Update status with completion:
```json
{
  "batch": <number>,
  "phase": "complete",
  "cycle": 3,
  "features_completed": ["<list>"],
  "features_skipped": ["<list of any that failed>"],
  "files_modified": ["<list>"],
  "commit_hash": "<hash>",
  "completed_at": "<ISO timestamp>"
}
```

Print a summary: batch name, features completed, features skipped, time elapsed.

## Error Recovery

If at ANY point something goes catastrophically wrong:
1. `git checkout -- bias_app/` to revert all uncommitted changes
2. Verify Data symlink: `ls -la Data` → if broken: `ln -s ../Data Data`
3. Update status with error details
4. Print the error summary so the launcher script can log it

## Critical Rules

- **NEVER modify files outside `bias_app/`** (except FEATURES.md marking and git operations)
- **NEVER break existing features** — if unsure, read more code first
- **Always follow existing patterns** — look at how existing functions work before writing new ones
- **Theme parameter is mandatory** — every figure factory must accept and use `theme: dict`
- **Colors from config.py only** — COLOR_GOLD, COLOR_BINARY, COLOR_SINGLE, METHOD_COLORS
- **800-line limit** — if a file would exceed it, split into a new module first
- **Read the Dash skill** (`.claude/skills/developing-with-dash/SKILL.md`) for DMC patterns
- **React 18 required** — any app import test must call `_dash_renderer._set_react_version("18.2.0")`
