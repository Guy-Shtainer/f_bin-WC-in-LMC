## Status: READY
## Layout Spec: Mock Inspector — standalone pipeline comparison webapp

---

## Structure

Single-page Streamlit app (`mock_inspector_app/app.py`).
No sidebar — all controls live in the main area, top-to-bottom:

```
┌────────────────────────────────────────────────────────────────────────┐
│  st.title("Mock Pipeline Inspector")                                   │
│  st.caption("Side-by-side comparison: Mock Data vs Model Explorer…")  │
├────────────────────────────────────────────────────────────────────────┤
│  CONTROL REGION  (st.container, full width)                            │
│                                                                        │
│  Row A  [σ_single] [σ_meas] [f_bin] [π (logP exp)] [True logP_max]   │
│  Row B  [error_model selectbox ──────────] [N_iter] [seed_base]       │
│                                                                        │
│                           [  Run ▶  ]  (right-aligned)                │
│  st.divider()                                                          │
├────────────────────────────────────────────────────────────────────────┤
│  COMPARISON REGION  st.columns([1, 1])                                 │
│                                                                        │
│  ┌── Mock Data (bc.validation) ──┐  ┌── Model Explorer (render_lk_exp)┐│
│  │ st.markdown("**Mock Data**")  │  │ st.markdown("**Model Explorer**")││
│  │                               │  │                                  ││
│  │  ΔRV CDF (h=300)              │  │  ΔRV CDF (h=300)                ││
│  │  st.caption(...)              │  │  st.caption(...)                 ││
│  │                               │  │                                  ││
│  │  Binary frac vs thresh(h=280) │  │  Binary frac vs thresh (h=280)  ││
│  │  st.caption(...)              │  │  st.caption(...)                 ││
│  │                               │  │                                  ││
│  │  logP histogram  (h=220)      │  │  logP histogram   (h=220)       ││
│  │  e histogram     (h=220)      │  │  e histogram      (h=220)       ││
│  │  q histogram     (h=220)      │  │  q histogram      (h=220)       ││
│  │  cos i histogram (h=220)      │  │  cos i histogram  (h=220)       ││
│  │  ω histogram     (h=220)      │  │  ω histogram      (h=220)       ││
│  │  phase histogram (h=220)      │  │  phase histogram  (h=220)       ││
│  │                               │  │                                  ││
│  │  st.dataframe(summary stats)  │  │  st.dataframe(summary stats)    ││
│  └───────────────────────────────┘  └──────────────────────────────────┘│
└────────────────────────────────────────────────────────────────────────┘
```

---

## Control Placement

All controls live in the main area. No sidebar (single-page standalone app;
no global/page-local split is needed). No expanders — all controls visible
inline by default (project rule: feedback_no_collapsing_controls.md).

### Row A — five number_inputs in st.columns([1, 1, 1, 1, 1])

| Label | Key | Default | Step | Affects |
|-------|-----|---------|------|---------|
| σ_single (km/s) | insp_sigma_single | 15.0 | 0.1 | both |
| σ_meas (km/s) | insp_sigma_meas | 5.0 | 0.1 | both |
| f_bin | insp_f_bin | 0.46 | 0.01 | both |
| π (logP exponent) | insp_pi | 0.0 | 0.1 | both |
| True logP_max | insp_logPmax | 5.0 | 0.5 | both |

No min/max constraints on any number_input (project rule).
Defaults sourced from render_validation.py:93-105 (same as Validation tab).

### Row B — three controls in st.columns([2, 1, 1])

| Label | Type | Key | Default | Affects |
|-------|------|-----|---------|---------|
| Error model | selectbox | insp_error_model | "gaussian" | both |
| N_iterations | number_input | insp_n_iter | 500 | both |
| Seed base | number_input | insp_seed_base | 42 | both |

Error model options: ["gaussian", "asymmetric", "none"].
number_input step = 50 for N_iterations; step = 1 for seed_base.

### Run button

Right-aligned via spacer:
```
_, _, btn_col = st.columns([4, 1, 1])
```
Button in btn_col: `st.button("Run ▶", type="primary", key="insp_run",
use_container_width=True)`.

Clicking Run checks if `params_hash` changed since last run:
- unchanged → display cached session_state results immediately (no recompute)
- changed → run both pipelines, show st.progress() during computation

### Persistence rule

Every control must have an `on_change` callback calling
`sm.save(["inspector", key])` where `sm` is a SettingsManager reading/writing
`mock_inspector_app/settings.json`. Defaults are read from saved config at
startup; fall back to the defaults in the table above if key is absent.

---

## Two-Column Comparison Region

```python
left_col, right_col = st.columns([1, 1])
```

Each column renders independently. The coder builds one helper function
`render_column(col, results, pipeline_label, color)` called twice — once for
each pipeline — with different `results` and `color` arguments.

### Progress feedback (shown during computation only)

```python
prog = st.progress(0.0, text="Initializing Mock Data pipeline...")
# after mock_data completes:
prog.progress(0.5, text="Running Model Explorer pipeline...")
# after model_explorer completes:
prog.progress(1.0, text="Done.")
```

Both pipelines run sequentially in the main thread (not background threads)
because they are fast Monte-Carlo functions; blocking the UI briefly is
acceptable. If either pipeline takes >10 s, the coder may add a threading
layer, but that is an implementation decision outside this spec.

---

## Plot Details

All figures use `_academic_fig()` from `app/plots/theme.py` for white
background, Times New Roman serif, black mirrored axes, no gridlines.
Every plot rendered with `st.plotly_chart(fig, use_container_width=True)`.
Eight separate `st.plotly_chart` calls per column (not `make_subplots`) —
see Rationale for why.

### Plot 1 — ΔRV CDF (height=300)

- X axis: "ΔRV (km/s)"; Y axis: "Cumulative fraction"
- Observed empirical step-ECDF: color `#2E2E2E`, solid, width 2 px
- Simulated 16–84 percentile band: `#4A90D9` fill, opacity 0.25;
  `legendgroup="sim"` on both fill trace and its median line so toggling
  the legend entry hides both (CDF legend-toggle rule from plot_preferences.md)
- Simulated median: `#4A90D9` solid, width 1.5 px
- Mock Data column color: `#4A90D9` (steel blue)
- Model Explorer column color: `#E25A53` (tomato red) — use the column's
  assigned color for the simulated traces; the observed step is always `#2E2E2E`
- st.caption below: "Pooled empirical ECDF across 25 stars (black step) vs
  simulated 16–84 percentile band from N_iterations Monte-Carlo draws. Smooth
  pooled CDF uses bc.helpers.smooth_pooled_cdf."

### Plot 2 — Binary fraction vs threshold (height=280)

- X axis: "ΔRV threshold (km/s)", range [0, 150]; Y axis: "Detected binary fraction"
- One curve per column, column's assigned color
- Vertical dashed line at x=45.5 in `#2E2E2E`, annotated "threshold"
- st.caption: "Fraction of 25 stars classified as binary as a function of ΔRV
  threshold. Vertical dashed line at the project binary-detection threshold (45.5 km/s)."

### Plots 3–8 — Orbital parameter histograms (height=220 each)

Order within each column: logP, e, q, cos i, ω, phase.
Bar color = column's assigned color (blue for Mock Data, red for Model Explorer).
30 bins. No gap between bars (`bargap=0`).
Full physical x-range for each parameter (logP: auto from data; e: [0,1];
q: [0,1]; cos i: [0,1]; ω: [0, 360] degrees; phase: [0,1]).

st.caption below each histogram (verbatim text for coder):
- logP: "Orbital period distribution (log days). Power-law exponent π controls the slope."
- e: "Orbital eccentricity (0 = circular). Drawn from the configured distribution."
- q: "Mass ratio M2/M1 (0–1). Assumed uniform unless overridden."
- cos i: "Cosine of orbital inclination. Uniform in cos i implies random 3-D orientation."
- ω: "Argument of periastron (degrees, 0–360). Drawn uniformly."
- phase: "Orbital phase at first observation epoch (0–1). Drawn uniformly."

Font sizes (project rule, 2026-04-23):
- Axis titles: 14 pt minimum
- Tick labels: 12 pt minimum
- Legend text: 12 pt minimum
- In-plot annotations: 12 pt minimum

### Summary stats table (bottom of each column)

`st.dataframe` with `hide_index=True`. Six rows (one per orbital parameter),
three stat columns: mean, median, std. Column header: "Parameter | Mean | Median | Std".
White background, no metric cards.

---

## Styling Rules

- A&A journal style on every plot: white background, black text, Times New Roman
  serif, black mirrored axes, no gridlines, outside ticks. Use `_academic_fig()`
  from `app/plots/theme.py`.
- WCAG 4.5:1 contrast: all text `#2E2E2E` or darker on white.
- Ban list (no exceptions on white-background plots): `'white'`, `'#FFFFFF'`
  as trace colors; `'gold'`, `'#FFD700'`; any grey ≤ `#555555` for primary
  data. (Source: plot_preferences.md 2026-04-23 ban list.)
- Approved column-accent colors: Mock Data `#4A90D9`; Model Explorer `#E25A53`.
  These pass WCAG 4.5:1 on white background.
- Page config: `st.set_page_config(layout="wide", page_title="Mock Inspector")`.
- No emojis in any interface text, labels, captions, or button labels.

---

## Cache + Run State

Results live in `st.session_state` keyed by `(params_hash, pipeline_id)`:
- `st.session_state[("mock_data", params_hash)]` → dict with arrays
- `st.session_state[("model_explorer", params_hash)]` → dict with arrays

`params_hash = hashlib.md5(json.dumps(params, sort_keys=True).encode()).hexdigest()`
where `params` is a plain dict of all 8 control values.

On "Run ▶":
1. Compute new hash.
2. If both keys exist in session_state → skip recomputation, display immediately.
3. If either key is missing → run that pipeline, store result under new hash.
4. Prune stale session_state keys: keep only the two most recent hashes to
   avoid unbounded growth.

No `@st.cache_data` on run functions — the user controls reproducibility via
seed_base; session_state with a hash key is sufficient and avoids Streamlit's
function-signature hash issues with numpy arrays.

---

## Standalone Webapp Scaffolding

```
mock_inspector_app/
    __init__.py         # empty — marks package for sibling imports
    app.py              # st.set_page_config + top-level render entry point
    inspector.py        # pure rendering helpers: build_cdf_fig, build_hist_fig,
                        #   build_binary_frac_fig, build_summary_table.
                        #   Accepts numpy arrays; returns Plotly figures.
                        #   No Streamlit imports.
    runner.py           # thin wrappers around bc.validation and
                        #   bc.render_lk_explorer that call the Monte-Carlo
                        #   and return plain dicts of numpy arrays.
                        #   No Streamlit imports.
    settings.py         # minimal SettingsManager: load/save settings.json
    settings.json       # persisted control defaults (add to .gitignore)
```

Launch command:
```
streamlit run mock_inspector_app/app.py --server.port 8503
```

Sibling import path setup at top of `app.py` (same pattern as `app/bc/*.py`):
```python
import os, sys
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)            # project root
_APP  = os.path.join(_ROOT, "app")        # app/ directory
for _p in [_ROOT, _APP]:
    if _p not in sys.path:
        sys.path.insert(0, _p)
# Enables:
#   from bc import validation, helpers, render_lk_explorer
#   from shared import cached_load_cadence, PLOTLY_THEME
#   from plots.theme import _academic_fig
```

`runner.py` imports from `bc.validation` and `bc.render_lk_explorer`.
`inspector.py` imports from `plots.theme` only. Neither file imports Streamlit.
`app.py` owns all Streamlit calls and passes results to `inspector.py` helpers.

---

## Acceptance Criteria (QA checks against these)

- [ ] `streamlit run mock_inspector_app/app.py --server.port 8503` starts
      without any ImportError or AttributeError.
- [ ] All 8 controls (σ_single, σ_meas, f_bin, π, logP_max, error_model,
      N_iterations, seed_base) are visible inline; none hidden inside st.expander.
- [ ] Each number_input has no `min_value` or `max_value` argument; step values
      match the table in this spec.
- [ ] "Run ▶" button triggers both pipelines and shows st.progress() during computation.
- [ ] Two equal-width columns render side by side, each containing 8 plots
      in the specified order: CDF, binary-frac curve, logP, e, q, cos i, ω, phase.
- [ ] All plots use white background (A&A style). No dark background on any chart.
- [ ] CDF observed step trace color is `#2E2E2E`. Not any variant of white.
- [ ] CDF simulated band and its median line share the same `legendgroup`;
      toggling via the Plotly legend hides both traces simultaneously.
- [ ] Mock Data column histograms use `#4A90D9`; Model Explorer histograms use `#E25A53`.
- [ ] All axis title font sizes are ≥ 14 pt; tick labels ≥ 12 pt.
- [ ] `grep -nE "'white'|'#FFFFFF'|'gold'|'#FFD700'|showgrid=True"` returns
      zero hits in mock_inspector_app/inspector.py and mock_inspector_app/runner.py.
- [ ] Summary stats dataframe appears below each column's histograms with
      `hide_index=True`, six rows (one per parameter), three stat columns.
- [ ] Every control has an `on_change` callback that calls sm.save([...]);
      defaults are read from settings.json at startup.
- [ ] Re-clicking "Run ▶" with unchanged controls skips recomputation and
      displays results from session_state immediately (no progress bar shown).
- [ ] st.caption appears immediately below every plot (all 8 per column).
- [ ] Page uses `layout="wide"`.
- [ ] ω histograms display x-axis range [0, 360] in degrees, not radians.

---

## Rationale

**Eight separate figures per column vs make_subplots.**
The col=/row= scoping bug (diagnosed 2026-04-23, documented in plot_preferences.md)
causes inconsistent axis styling when `update_xaxes`/`update_yaxes` is called
with only `row=` or only `col=`. With 8 rows in a single subplot grid the risk
of a style inconsistency escaping QA is high. Eight independent `st.plotly_chart`
calls with `use_container_width=True` are immune to this bug and match the
pattern used in existing pages.

**Equal [1,1] columns.**
The two pipelines are being compared as equals. Asymmetric widths would imply
one is the reference and the other is secondary, which is not the case here.

**Distinct histogram colors per column.**
With 16 plots on screen simultaneously, the user's eye easily loses track of
which column it is reading. Persistent color coding (blue-left / red-right)
removes the need to re-read column headers for orientation.

**ω in degrees (0–360), not radians.**
Degrees are immediately readable by an astronomer. Radian values (0–2π) require
mental conversion and offer no scientific advantage for a distribution check.

**No sidebar.**
This is a standalone, single-purpose comparison tool. There are no global
settings to persist across pages. Putting controls in the main area keeps the
full horizontal width available for the two-column comparison.

**runner.py separate from inspector.py.**
`inspector.py` is pure: arrays in, Plotly figures out. `runner.py` is the
Monte-Carlo adapter. This split makes both unit-testable without a running
Streamlit server, and makes it trivial to add a third pipeline in the future
by adding one function to `runner.py` and one column to `app.py`.
