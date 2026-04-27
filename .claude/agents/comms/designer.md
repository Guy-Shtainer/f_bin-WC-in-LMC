## Status: READY

## Layout Spec: Bin Sensitivity sub-tab (app/bc/)

---

## Structure

The new sub-tab is a **standalone tab** registered as type `'bin_sensitivity'` in
`05_bias_correction.py`'s `bc_tabs` session-state list. It lives between "Cadence (Langer)"
and "RV Errors" in the default tab list — immediately after the two simulation tabs so the user
sees it right after running a grid, and before the diagnostic/utility tabs.

Default entry in `bc_tabs` init block (add at index 2, shifting RV Errors and Compare):

```
{'type': 'bin_sensitivity', 'name': 'Bin Sensitivity', 'prefix': 'bsn'},
```

"Bin Sensitivity" is 13 characters — well under the 20-char Streamlit tab render limit.

Tab registration in `05_bias_correction.py`:
- Import: `from bc.bin_sensitivity import _render_bin_sensitivity_tab`
- Dispatch: `elif _ti['type'] == 'bin_sensitivity': _render_bin_sensitivity_tab(_ti['prefix'], settings, sm)`

Tab registration in `app/bc/__init__.py`:
- Add: `from bc.bin_sensitivity import _render_bin_sensitivity_tab`

The tab's content divides into three vertical sections rendered top-to-bottom:
1. Controls section — source selector + scheme controls (always visible, no expanders)
2. Progress section — progress bar + status text (only shown when running)
3. Results section — summary table + sub-tabs for plots + export button

---

## Control Placement

All controls in this section MUST be visible inline without any st.expander. This follows
feedback_no_collapsing_controls.md: controls are never hidden; everything defaults ON.

### Row 1 — Source selector (full width)

```
st.markdown("#### Source")
col_src_a, col_src_b = st.columns([0.35, 0.65])
```

- col_src_a: st.radio("Simulation source", ["Reuse existing .npz", "Run fresh simulation"],
  horizontal=True, key=f'{p}_bsn_source')
  - Default: "Reuse existing .npz"
- col_src_b (shown only when "Reuse existing .npz" is selected):
  st.selectbox("Result file", options=<list of cadence_*.npz sorted by mtime desc>,
  key=f'{p}_bsn_npz_path')
  - List built by scanning results/ for cadence_*.npz files, sorted newest-first.
  - Display: filename only (not full path). Tooltip shows full path via help= parameter.
  - When "Run fresh simulation" is selected, col_src_b is hidden (use if branch, not expander).

### Row 2 — Scheme family multi-select (full width)

```
st.markdown("#### Bin schemes to compare")
```

Use st.multiselect with all families listed. Default ON for all except "custom".

```python
scheme_families = st.multiselect(
    "Active schemes",
    options=["dsilva_default", "equal_width", "log_spaced", "quantile",
             "anchored", "freedman_diaconis", "custom"],
    default=["dsilva_default", "equal_width", "log_spaced", "quantile",
             "anchored", "freedman_diaconis"],
    key=f'{p}_bsn_schemes',
)
```

### Row 3 — Parametric scheme controls (4 columns, no expanders)

```
col_nbin1, col_nbin2, col_nbin3, col_nbin4 = st.columns([0.22, 0.22, 0.22, 0.34])
```

- col_nbin1: st.number_input("n_bins (equal-width)", value=10, step=1, key=f'{p}_bsn_n_ew')
  - Applies to "equal_width". No min/max constraint per feedback_no_hard_limits.
- col_nbin2: st.number_input("n_bins (log-spaced)", value=10, step=1, key=f'{p}_bsn_n_ls')
  - Applies to "log_spaced".
- col_nbin3: st.number_input("n_bins (quantile)", value=5, step=1, key=f'{p}_bsn_n_qt')
  - Applies to "quantile".
- col_nbin4: st.number_input("n_anchors (anchored)", value=5, step=1, key=f'{p}_bsn_n_an')
  - Applies to "anchored". Controls how many intermediate anchor points are placed between
    the threshold and max_obs.

No min/max constraints on any number_input per feedback_no_hard_limits.md.

### Row 4 — Threshold and max-delta-RV controls (3 columns)

```
col_thr, col_max, col_fd = st.columns([0.3, 0.3, 0.4])
```

- col_thr: st.number_input("Detection threshold (km/s)", value=45.5, step=0.5,
  format="%.1f", key=f'{p}_bsn_threshold')
  - Used as anchor edge for dsilva-style and anchored schemes.
- col_max: st.number_input("Max delta-RV (km/s, 0=auto)", value=0.0, step=10.0,
  format="%.1f", key=f'{p}_bsn_max_drv')
  - When value is 0.0 (default), the renderer auto-fills from max(obs_delta_rv) at run time.
  - Non-zero value overrides auto-fill. No min/max constraint.
- col_fd: st.caption("Freedman-Diaconis edges are computed automatically from the observed
  distribution. No parameters needed.")
  - Informational only; no widget.

### Row 5 — Custom edges (only when "custom" is in active schemes)

```python
if "custom" in scheme_families:
    custom_edges_str = st.text_input(
        "Custom bin edges (comma-separated km/s, e.g. 0,45.5,100,250,650)",
        value="0,45.5,100,250,650",
        key=f'{p}_bsn_custom_edges',
    )
    st.caption("Parsed as np.array(sorted(floats)). First value should be 0; last may be 'inf'.")
```

### Row 6 — Run button (right-aligned)

```python
_, col_run = st.columns([0.75, 0.25])
with col_run:
    run_clicked = st.button("Run comparison", type="primary",
                            key=f'{p}_bsn_run', use_container_width=True)
```

---

## Progress Feedback

Shown only while the comparison is running (use a boolean in session state,
e.g. f'{p}_bsn_running').

```python
if st.session_state.get(f'{p}_bsn_running'):
    bsn_prog = st.progress(0.0, text="Initializing...")
    bsn_status = st.empty()
```

- bsn_prog.progress(fraction, text=f"Re-scoring scheme {i}/{total}: {scheme_label}")
  — fraction in [0, 1].
- After the first scheme completes, show ETA:
  bsn_status.markdown(f"ETA: ~{eta_seconds:.0f}s remaining")
- On completion: bsn_prog.progress(1.0, text="Complete.") then st.rerun() to enter results view.

The progress callback is a plain Python callable (not Streamlit-specific) so it can be passed to
the backend scorer without tying it to Streamlit's thread. The coder should buffer progress
updates in st.session_state and read them in a @st.fragment(run_every=1) poller rather than
calling Streamlit from a background thread directly.

---

## Result Presentation

Results are shown only when st.session_state.get(f'{p}_bsn_result') is not None.

### Summary table (top of results)

Full-width st.dataframe with the following columns:

| Column | Description |
|---|---|
| scheme | Scheme name string (e.g., "dsilva_default", "equal_width_10") |
| n_bins | Integer count of bins (edges - 1) |
| f_bin* | Best-fit f_bin at grid maximum |
| f_bin_HDI68 | HDI 68% width for f_bin (dimensionless, 0-1 range) |
| pi* | Best-fit pi at grid maximum |
| pi_HDI68 | HDI 68% width for pi |
| logL_max | Raw log-likelihood at best cell (shown as-is, not negated; label "logL" per feedback_logL_convention.md) |
| KS_at_best | K-S statistic between obs CDF and sim median CDF at best-fit cell |
| n_empty_bins | Count of bins with zero observed counts |

The row corresponding to "dsilva_default" is displayed first (sort so dsilva_default is always
row 0, then alphabetical for remaining schemes). This ensures the reference row is always
visually prominent without requiring Pandas Styler complexity.

Below the table: st.caption("logL shown as raw value; higher (less negative) is better.")

A st.radio immediately below the table lets the user select a single scheme to inspect in the
plots below:

```python
selected_scheme = st.radio(
    "Inspect scheme in plots",
    options=[r['scheme'] for r in result_rows],
    horizontal=True,
    key=f'{p}_bsn_selected_scheme',
)
```

### Plots (middle of results)

Use st.tabs(["Sensitivity", "CDF Overlay", "Posterior Shapes", "Bin Diagnostics"]) —
four sub-tabs, one plot per sub-tab. Each sub-tab contains a single @st.fragment render.

Tab 1 — "Sensitivity": HDI-width vs. scheme/n_bins sensitivity chart.
Shows f_bin_HDI68 and pi_HDI68 as separate markers/lines across all active schemes on the X-axis
(categorical). Two marker shapes (circle for f_bin, diamond for pi) on a single Y-axis labeled
"HDI 68% width". Fragment key: f'{p}_bsn_plot_sens'.
Caption: "Smaller HDI width = tighter posterior. Compare across schemes to assess sensitivity."

Tab 2 — "CDF Overlay": Observed delta-RV empirical CDF (step line, dark) overlaid with the
simulated median CDF for the scheme selected in the radio button above (step line, colored).
Bin edges for the selected scheme drawn as vertical dashed lines annotated with edge values.
Fragment key: f'{p}_bsn_plot_cdf'.
Caption: "Vertical dashed lines show bin edges for the selected scheme. Observe how CDF is partitioned."

Tab 3 — "Posterior Shapes": Two 2D heatmaps side by side (st.columns([0.5, 0.5])) —
left: normalized likelihood surface (f_bin vs pi) for the currently selected scheme;
right: dsilva_default surface for comparison. Use make_heatmap_fig from shared.py for consistency.
Fragment key: f'{p}_bsn_plot_post'.
Caption: "Left: selected scheme likelihood surface. Right: dsilva_default reference. Compare peak location and breadth."

Tab 4 — "Bin Diagnostics": Grouped bar chart (side by side, not stacked) showing observed count
and simulated expected count per bin for the selected scheme at the best-fit grid cell.
Color: observed = dark (first palette color), expected = lighter variant. Bins with zero observed
count get a red annotation "empty". Fragment key: f'{p}_bsn_plot_diag'.
Caption: "Empty bins (n_obs=0) contribute 0 to logL regardless of simulated density and are wasted degrees of freedom."

Each plot gets a st.caption immediately below it describing axes and interpretation.

### Export button (bottom of results)

```python
col_exp, _ = st.columns([0.25, 0.75])
with col_exp:
    if st.button("Export results", key=f'{p}_bsn_export'):
        # write results/bin_sensitivity_YYMMDD-HHMM.csv and .json
        ...
```

On click: write results/bin_sensitivity_{timestamp}.csv (one row per scheme, all table columns)
and results/bin_sensitivity_{timestamp}.json (full result dict including bin edges per scheme).
Show st.success(f"Exported to results/bin_sensitivity_{timestamp}.csv / .json").

---

## Styling Rules

All plots use PLOTLY_THEME from app/shared.py — never hardcode colors.
White background, serif font, black axes, no gridlines per feedback_matplotlib_style.md.
WCAG AA contrast for all text labels and annotations per feedback_aa_journal_style.md.
Scheme color palette: use get_palette() cycling through the returned list, one color per scheme.
The dsilva_default scheme always uses index 0 of the palette (consistent with existing charts).

Axis labels:
- Delta-RV axis label: "Delta-RV (km/s)"
- f_bin axis: "f<sub>bin</sub>" (HTML subscript via Plotly)
- logL axis: "logL" (no negation, no dash, no "-logL")
- HDI width axis: "HDI 68% width"

No emojis anywhere in the tab (interface text, captions, labels, or button labels).

---

## File Plan for the Coder

Four new files (all under app/bc/):

| File | Purpose | Target lines |
|---|---|---|
| app/bc/bin_sensitivity.py | Tab renderer: controls, progress, results layout, export | max 380 lines |
| app/bc/bin_schemes.py | Scheme library: pure functions returning np.ndarray of edges | max 200 lines |
| app/bc/bin_sensitivity_plots.py | Plot builders: one function per plot (4 total) | max 300 lines |
| app/bc/bin_sensitivity_scorer.py | Re-scoring engine: takes npz + edge arrays, returns result rows; houses @st.cache_data decorators | max 250 lines |

Rationale for 4 files (not 3 as the briefing proposed): the re-scoring logic is substantial and
import-sensitive enough that mixing it with layout code would push bin_sensitivity.py above 400
lines and complicate the @st.cache_data key design. Splitting scorer from renderer keeps each file
to its single responsibility and under 400 lines, consistent with feedback_file_size.md.

Files NOT modified in Round 2:
- app/bc/subtabs.py — the new tab lives at the page level, not inside render_model_subtabs().
- Any render_lk*.py, render_shared*.py, runners_cadence*.py — no changes.
- wr_bias_simulation.py — read-only from the scorer.

Files modified in Round 2:
- app/bc/__init__.py — add one import line.
- app/pages/05_bias_correction.py — add default tab entry, one elif dispatch, one radio option,
  one _type_map entry.

---

## State Persistence

On every render, the following bin-sensitivity-specific keys should be persistable via the
sidebar "Save state" button to settings/states/{timestamp}_bin_sensitivity.json:

```python
{
    "source": st.session_state.get(f'{p}_bsn_source'),
    "npz_path": st.session_state.get(f'{p}_bsn_npz_path'),
    "schemes": st.session_state.get(f'{p}_bsn_schemes'),
    "n_ew": st.session_state.get(f'{p}_bsn_n_ew'),
    "n_ls": st.session_state.get(f'{p}_bsn_n_ls'),
    "n_qt": st.session_state.get(f'{p}_bsn_n_qt'),
    "n_an": st.session_state.get(f'{p}_bsn_n_an'),
    "threshold": st.session_state.get(f'{p}_bsn_threshold'),
    "max_drv": st.session_state.get(f'{p}_bsn_max_drv'),
    "custom_edges": st.session_state.get(f'{p}_bsn_custom_edges'),
    "last_result_path": <path of last .csv export, if any>,
}
```

Save via sm.save(['bin_sensitivity', p], {...}) if sm supports nested paths, or write directly
to settings/states/ via file_ops helpers — whichever pattern the coder finds in existing tabs.

---

## Fragments and Caching

Caching (@st.cache_data): key on (npz_path, scheme_key, scheme_params_tuple) where
scheme_params_tuple is a hashable tuple of sorted edge floats.
Cache lives in bin_sensitivity_scorer.py. Each scheme's re-score is independently cached so
toggling one scheme ON/OFF only recomputes that scheme, not the entire batch.

Fragments (@st.fragment): each of the four plot functions in bin_sensitivity_plots.py is
decorated with @st.fragment. Fragment keys use the f'{p}_bsn_plot_{name}' pattern.
The summary table and export button are NOT fragments (fast and stateless).

Important implementation note for the coder: the scorer must use the SAME seeds as the original
grid run. Grid seeds are a pure function of cell index (i_sig, i_fb, i_pi) as verified in
runners_cadence.py:82-92 and are stable across resume. The scorer can reconstruct seeds
deterministically. If the original simulated pools are not stored in the .npz (they are not today
— only logL_raw is), the scorer must re-simulate at each grid cell using
simulate_delta_rv_cadence_aware with the same seed formula. The briefing flags this as the key
design decision for Round 2 — the layout does not depend on which path is chosen, but the coder
must preserve result-dict completeness (learnings.md: "Result-dict completeness contract").
The scorer must pass the FULL bin_cfg, period_model, cadence_weights, sigma_meas from the .npz
result dict to every re-simulation helper — never reconstruct BinaryParameterConfig from scratch
(learnings.md: "A re-simulated plot MUST use the SAME bin_cfg / period_model / cadence_weights").

---

## Acceptance Criteria (QA checks against these)

- [ ] Tab loads without error when no .npz file is selected (or results directory is empty);
      shows informational st.info() rather than a traceback.
- [ ] "Run comparison" with default schemes (dsilva_default, equal_width, log_spaced) completes
      on any small .npz in results/ without error; the summary table appears with all rows
      populated (no NaN, no None, no "--" in numeric columns).
- [ ] All table columns are populated with real computed values: f_bin*, f_bin_HDI68, pi*,
      pi_HDI68, logL_max, KS_at_best, n_empty_bins. Spot-check: dsilva_default row logL_max
      must match the logL shown in the Cadence (Dsilva) tab for the same .npz.
- [ ] All four plot sub-tabs render without error; axis labels match the spec (delta-RV in km/s,
      logL not negated, f_bin with HTML subscript where Plotly is used).
- [ ] Toggling a scheme off in the multi-select (without clicking Run again) removes its row
      from the displayed table; other scheme rows do not trigger a cache miss (no re-computation).
- [ ] Export button writes both results/bin_sensitivity_*.csv and results/bin_sensitivity_*.json
      and the st.success message appears with the file paths.
- [ ] "custom" edges text input is hidden when "custom" is not in the active schemes multi-select,
      and appears immediately when "custom" is added to the selection.
- [ ] No controls are hidden inside st.expander widgets; all scheme controls are visible inline.
- [ ] dsilva_default row appears first in the summary table.

---

## Rationale

Placing "Bin Sensitivity" at position 2 (after the two cadence simulation tabs) gives the user
immediate access after running a grid. The primary workflow is: run grid in Cadence Dsilva ->
switch to Bin Sensitivity -> load the just-completed .npz -> compare schemes. Placing it last
would require scrolling past utility tabs.

The three-section layout (controls, progress, results) matches the existing Cadence tabs pattern
for visual consistency. All controls inline (no expanders) is a hard rule from user feedback.
Four result plots in sub-tabs avoids CSS hacks and gives each plot full container width for
legibility of fine-grained bin-edge annotations.

Separating scorer and plot builders into their own files keeps bin_sensitivity.py under 400 lines
and makes future changes surgical: a new scheme family means editing only bin_schemes.py and
adding one row to the scorer loop, with zero risk of touching the plot or layout code.
