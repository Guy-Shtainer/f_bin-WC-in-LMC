# FEATURES.md — Bias Correction Page Feature Catalog

> **Purpose:** Regression checklist for the bias correction page (`app/pages/05_bias_correction.py` + `app/bc/`).
> After any code change, verify affected features still work. Each feature has an ID, description,
> implementing files, and a verification method.

---

## Module Map (20 files, ~10,500 lines)

| File | Lines | Role |
|------|-------|------|
| `app/pages/05_bias_correction.py` | 125 | Page entrypoint, tab creation, canvas controls |
| `app/bc/__init__.py` | 5 | Re-exports 6 tab renderers |
| `app/bc/dsilva.py` | 796 | Dsilva (power-law) tab |
| `app/bc/langer.py` | 791 | Langer 2020 tab |
| `app/bc/cadence.py` | 854 | Cadence-aware Dsilva + Langer tabs |
| `app/bc/extras.py` | 1237 | RV Errors tab + Compare tab + error model selector |
| `app/bc/params.py` | 595 | Orbital parameter UI + scan controls + likelihood bin config |
| `app/bc/helpers.py` | 445 | Constants, ETA formatting, heatmap helpers, CDF sanity check, methodology |
| `app/bc/file_ops.py` | 593 | Result/partial file I/O, metadata scanning, descriptive filenames |
| `app/bc/polling.py` | 198 | Live polling fragment (@st.fragment) for running jobs |
| `app/bc/runners.py` | 4 | Re-exports background runners |
| `app/bc/runners_dsilva.py` | 420 | Dsilva multiprocessing grid runner |
| `app/bc/runners_langer.py` | 409 | Langer multiprocessing grid runner |
| `app/bc/runners_cadence.py` | 619 | Cadence-aware unified runner (both models) |
| `app/bc/analysis.py` | 1210 | Scoring summary table, per-method expanders, CDF comparison, Model Explorer |
| `app/bc/subtabs.py` | 330 | Method radio selector, simulation overview orchestrator |
| `app/bc/sim_plots.py` | 432 | Period distribution, gap analysis, orbital histograms |
| `app/bc/scoring_detail.py` | 650 | Per-method heatmaps, grid exclusion, parabolic fits, 3D surfaces |
| `app/bc/corner_plots.py` | 253 | Corner plots (pairwise 2D projections) |
| `app/bc/likelihood_viz.py` | 328 | Likelihood CDF overlay, per-bin table, explainer |
| `app/bc/fitting.py` | 262 | Neighborhood-fit interpolation (1D/2D/3D parabolic) |
| `wr_bias_simulation.py` | ~2800 | Simulation engine (shared, not in app/bc/) |

---

## 1. Tab Structure & Navigation

| ID | Feature | Files | Verify |
|----|---------|-------|--------|
| F-001 | **6 default tabs**: Dsilva, Langer, Cadence (Dsilva), Cadence (Langer), RV Errors, Compare — rendered via `st.tabs()` with per-tab renderers from `bc.__init__` | `05_bias_correction.py`, `__init__.py` | All 6 tabs render without error; clicking each shows correct content |
| F-002 | **Tab prefix isolation**: each tab gets a unique prefix (`bc`, `lg`, `cad`, `cal`, `rve`, `cmp`) used to namespace all session_state keys — prevents cross-tab interference | `05_bias_correction.py`, all tab files | Change f_bin in Dsilva tab → Langer tab's f_bin unchanged |
| F-003 | **Canvas size controls**: expander at page top with height (200–2000px, default 520) and width (0=auto, up to 3000px) number_inputs — applied to all heatmaps/charts via `bc_canvas_height`/`bc_canvas_width` session keys | `05_bias_correction.py` | Changing height resizes all heatmaps on every tab |
| F-004 | **Dynamic tab add/remove**: st.popover "+ Add tab" with type selector (radio: Cadence Dsilva/Langer, RV Errors, Compare) + optional name text_input; "Remove last" button appears when ≥5 tabs. Tabs persist in `st.session_state['bc_tabs']` list of dicts | `05_bias_correction.py` | Add a tab → new tab appears; remove → last tab disappears |

---

## 2. Grid Parameter Selection

| ID | Feature | Files | Verify |
|----|---------|-------|--------|
| F-010 | **f_bin range**: 3-column compact layout with number_inputs for min (0.0–1.0), max (0.0–1.0), steps (2–200). Each input has on_change callback that auto-saves to `user_settings.json` via `sm.save()` | `dsilva.py`, `langer.py`, `cadence.py` | Values persist after page navigation; linspace(min,max,steps) used in grid |
| F-011 | **pi range** (Dsilva / Cadence-Dsilva only): 3-column number_inputs for min, max, steps of the power-law exponent π. Hidden in Langer/Cadence-Langer tabs | `dsilva.py`, `cadence.py` | Only visible in Dsilva-type tabs; controls `pi_grid` dimension |
| F-012 | **sigma_single** (Langer / Cadence): intrinsic single-star RV scatter [km/s]. Either a single number_input (no scan) or range via F-040 scan toggle | `langer.py`, `cadence.py` | Value feeds into SimulationConfig.sigma_single |
| F-013 | **N stars per grid point**: number_input (100–100,000 for standard tabs, 100–50,000 for cadence). Controls simulation statistical quality — higher N = smoother CDFs but slower | all 4 model tabs | Value saved to settings; used as sim_cfg.n_stars |
| F-014 | **sigma_measure**: measurement uncertainty [km/s], default ~1.622. Rendered via error model selector (F-015). Added as Gaussian noise to every simulated RV epoch | all 4 model tabs | Default visible; changing it affects all simulations |
| F-015 | **Error model selector**: 7 distribution types (Fixed, Normal, Log-normal, Gamma, Weibull, Exponential, Flat) in dual-column layout — separate selector for singles and binaries. Each type shows distribution-specific parameter inputs (loc, scale, shape). Live caption shows "Distribution mean = X km/s (per-epoch draws)". Returns dict with type, sigma_measure, and params per population | `extras.py` (`_render_error_model_selector`) | Select "Log-normal" → shape/loc/scale inputs appear; "Fixed" → single σ slider |
| F-016 | **Workers count**: number_input (1 to `os.cpu_count()-1`, default=max). Controls multiprocessing Pool size for grid computation | all 4 model tabs | Value capped at available cores; used in Pool(n_proc) |
| F-017 | **View mode toggle**: horizontal radio ("K-S p-value" / "K-S D-statistic"). Switches which scoring array is displayed in the primary heatmap | all 4 model tabs | Toggle changes heatmap colorbar title and data source |
| F-018 | **N sets for CvM/Likelihood**: number_input (100–50,000, default 1000). Controls how many Monte Carlo repetitions are used for CvM variance estimation and empirical p-value computation | all 4 model tabs | Higher N = more stable p-values but slower |

---

## 3. Orbital Parameters — Dsilva

| ID | Feature | Files | Verify |
|----|---------|-------|--------|
| F-020 | **Period range** (logP_min, logP_max): two number_inputs in compact 2-column layout. Controls log₁₀(P/days) bounds for power-law sampling. Saved to `grid_dsilva.orbital.logP_min/max` in settings | `params.py` (`_render_orbital_params_dsilva`) | Values persist; used in BinaryParameterConfig |
| F-021 | **Eccentricity model**: selectbox ("flat" / "zero"). "flat" shows e_max slider (0.0–0.99); "zero" hides it (e=0 for all systems, appropriate for post-RLOF). Wrapped in "Orbital parameters (Kepler)" expander (collapsed by default) | `params.py` | Select "zero" → e_max slider disappears |
| F-022 | **Primary mass M1**: selectbox ("fixed" / "uniform"). "fixed" → single M₁ number_input [M☉]; "uniform" → M₁_min and M₁_max number_inputs | `params.py` | Select "uniform" → two inputs appear instead of one |
| F-023 | **Mass ratio q (Dsilva)**: selectbox ("flat" / "langer"). "flat" → q_min/q_max inputs only; "langer" → additionally shows μ and σ for clipped Gaussian. q = M₂/M₁ by default | `params.py` | "langer" shows 4 inputs (min, max, mu, sigma); "flat" shows 2 |

---

## 4. Orbital Parameters — Langer

| ID | Feature | Files | Verify |
|----|---------|-------|--------|
| F-030 | **Two-component period distribution**: Case A (short-P, narrow) + Case B (long-P, broad) rendered side-by-side in 2-column layout. Each component has independent distribution type and parameters | `params.py` (`_render_orbital_params_langer`) | Both columns render independently; caption explains "two-component mixture in log₁₀(P/days)" |
| F-031 | **5 distribution types per component**: selectbox with Gaussian, Log-normal, Reflected log-normal, Empirical (Langer Fig. 6), Flat. Selecting Gaussian/Log-normal/Reflected shows μ (mode or mean) and σ inputs; Empirical/Flat hide parameter inputs entirely | `params.py` | Select "Empirical" → μ/σ inputs disappear; "Gaussian" → they reappear |
| F-032 | **Component weight slider**: st.slider for weight_A (0.0–1.0, step 0.01, default 0.2). Label shows "weight_B = 1 − weight_A". Controls Case A fraction in mixture | `params.py` | Sliding to 0.0 → pure Case B; to 1.0 → pure Case A |
| F-033 | **Case A/B/Both quick-set buttons**: 3 st.button in a row — "Case A only" (weight_A=1.0), "Case B only" (weight_A=0.0), "Both (Langer)" (weight_A=0.3). Clicking auto-updates weight slider | `params.py` | Click "Case B only" → slider jumps to 0.0 |
| F-034 | **q distribution (Langer)**: selectbox with 5 types (Flat, Gaussian, Log-normal, Reflected log-normal, Empirical from Langer Fig. 4). Empirical uses digitized histogram (`LANGER_Q_BIN_EDGES`/`LANGER_Q_WEIGHTS`), hides q_min/q_max. Others show q range + distribution params | `params.py` | "Empirical" hides range inputs; caption: "Sampling from digitized Langer+2020 Fig. 4" |
| F-035 | **q_flipped toggle**: st.checkbox "q flipped (M₂ = M₁/q)". When checked, mass ratio definition is inverted — M₂ = M₁/q instead of M₂ = q×M₁. Saved to BinaryParameterConfig.q_flipped | `params.py` | Check → changes mass calculation in simulation; persists to settings |
| F-036 | **Period range (Langer)**: logP_min/logP_max number_inputs, separate from Dsilva orbital params. Stored under `grid_langer.langer_period_params.logP_min/max` | `params.py` | Values independent from Dsilva tab's period range |
| F-037 | **Primary mass M1 (Langer)**: fixed/uniform selector + value/range inputs. Same logic as F-022 but stored under langer settings key | `params.py` | Same UI as Dsilva but writes to different settings section |

---

## 5. Scan Controls

| ID | Feature | Files | Verify |
|----|---------|-------|--------|
| F-040 | **sigma_single scan toggle** (Cadence tabs): st.checkbox "Scan σ_single over a range". Disabled → single σ_single number_input; Enabled → 3-column layout with σ_min, σ_max, σ_steps number_inputs. Returns `np.linspace(min, max, steps)` or `[single_value]` | `params.py` (`_render_cadence_sigma_scan`) | Toggle on → 3 inputs appear; off → single input |
| F-041 | **logP_max scan toggle** (Dsilva & Langer tabs): st.checkbox "Scan logP_max over a range". Adds extra grid dimension when enabled. 3-column layout with logPmax_min, logPmax_max, logPmax_steps | `params.py` (`_render_logPmax_scan`) | Toggle on → grid becomes 3D/4D; off → uses single logP_max from orbital params |
| F-042 | **Adaptive bins toggle** (Cadence tabs, recommended): st.checkbox "Use adaptive bins". When on, uses observed ΔRV values as CDF evaluation bin edges — eliminates bin-width parameter entirely. Recommended for cadence-aware simulations because bin edges match actual data points | `params.py` (`_render_cadence_adaptive_bins`) | Toggle on → bin width/max inputs disappear; caption says "(recommended)" |
| F-043 | **Manual bin width + max ΔRV**: two number_inputs visible only when adaptive bins (F-042) is OFF. Controls fixed bin edges: `np.arange(0, max, width)` | `params.py` | Only visible when adaptive toggle is off |
| F-044 | **Likelihood bin config**: st.radio ("Threshold-based" / "Manual"). Threshold → single slider (ΔRV threshold, 1–200 km/s, default 45.5) auto-generates bins `[0, threshold, 250, 650, ∞]`. Manual → st.text_input for comma-separated bin edges | `params.py` (`_render_likelihood_bin_config`) | Switch to "Manual" → text input appears; "Threshold" → slider appears |
| F-045 | **Grid range exclusion UI**: per-axis range sliders (st.slider with min/max) to exclude grid points from analysis. If axis has <5 values, falls back to st.multiselect. Separate sigma exclusion multiselect (if n_sig > 1). Info box shows "Excluding N / M grid points". Excluded points set to NaN on heatmaps (white) | `scoring_detail.py:74-162` | Narrow range → excluded region turns white on heatmap; info box updates count |
| F-046 | **Exclusion mask persistence**: 2D boolean mask (`{prefix}_exc_mask_2d`) + 1D projections (`_exc_x_mask_1d`, `_exc_y_mask_1d`) + value sets (`_exc_x_val_set`, `_exc_y_val_set`) stored in session_state. Survives Streamlit re-renders and tab navigation | `scoring_detail.py:307-312` | Set exclusion → navigate away → return → exclusion still applied |

---

## 6. Run / Cancel / Save Controls

| ID | Feature | Files | Verify |
|----|---------|-------|--------|
| F-050 | **Run button** ("▶️ Run [Model] Grid"): st.button (type="primary"). Disabled while a job is running. On click: builds full config dict from all UI params, launches `threading.Thread(daemon=True)` calling `_run_{model}_bg()`, stores job dict in `{p}_job` session_state | `dsilva.py`, `langer.py`, `cadence.py` + runners | Button grays out during run; background thread starts |
| F-051 | **Cancel button** ("⏹ Cancel"): appears only while job running. Sets `job['cancel'] = True`, `cancel_mode = 'discard'`. Background thread checks flag and exits loop | same + `polling.py` | Click → progress stops; status shows "Cancelled" |
| F-052 | **Cancel & Save button** ("💾 Cancel & Save"): appears alongside Cancel. Sets `cancel_mode = 'save'` — background thread writes partial checkpoint .npz before exiting. Partial file includes `progress_pct`, `rows_done`, `total_rows` alongside scoring arrays (NaN for incomplete cells) | same + `file_ops.py` | Click → partial file appears in results/ with `_partial_` tag |
| F-053 | **Manual Save button** ("💾 Save result"): visible only when result exists in session_state. Calls `_build_descriptive_filename()` to generate filename encoding all params. Saves to `results/{filename}.npz`. Clears metadata cache so load table refreshes | `file_ops.py` | Click → toast notification shows filename; file appears in load table |
| F-054 | **Descriptive filename generation**: encodes model type, f_bin range×steps, pi/sigma range×steps, N_stars, sigma value(s), logP range, and DDMMYY-HHMM timestamp. Langer filenames include case tag (_caseA/_caseB/_wA{val}) | `file_ops.py` (`_build_descriptive_filename`) | Filename matches pattern: `cadence_dsilva_fb0.01-1.00x99_pi-3.0-3.0x100_N1000_sig3.0-13.0x50_logP0.15-4.00_170326-1828.npz` |
| F-055 | **Toast/success notifications on save**: st.success() or st.toast() shown after successful save operations (result save, partial checkpoint save). Brief confirmation with filename | `cadence.py`, `file_ops.py` | Save → green success message appears briefly |

---

## 7. Load Saved Results

| ID | Feature | Files | Verify |
|----|---------|-------|--------|
| F-060 | **Results directory scan**: `_list_saved_results()` finds all .npz files in `results/` matching model type (excludes `_partial_` files). Sorted by modification time (newest first) | `file_ops.py` | New save appears at top of list |
| F-061 | **Metadata table**: st.dataframe with columns extracted from .npz headers — File, Model, Date, f_bin range, pi/sigma range, N_stars, N_sets, scoring method, period model, Best p-value, Best f_bin. Renders without loading full arrays | `file_ops.py` (`_scan_result_metadata`) | All columns populated; date format readable |
| F-062 | **Single-row selection to load**: `on_select` callback on dataframe. Clicking a row loads the full .npz into `st.session_state['{p}_result']` dict via `cached_load_grid_result()`. Result immediately displayed in heatmap + analysis sections | `dsilva.py`, `langer.py`, `cadence.py` | Click row → heatmap + scoring tabs populate |
| F-063 | **Delete button** ("🗑️ Delete"): removes selected .npz file from disk, clears metadata cache, clears session result if it was the loaded file | `file_ops.py` | Click → file gone from disk and table |
| F-064 | **Cached metadata scanning**: `@st.cache_data(ttl=30)` on `_scan_result_metadata()` and `_scan_partial_metadata()`. Avoids re-reading .npz headers on every Streamlit rerun. Cache manually cleared on save/delete operations | `file_ops.py` | Table loads fast on repeated visits; refreshes after save |
| F-065 | **Config hash reuse detection**: `_find_reusable_fbin()` / `_find_reusable_fbin_langer()` checks if any cached result matches current pi/sigma grids AND orbital params (including q_flipped, langer_period_params). If match found, offers to load instead of re-running | `file_ops.py` | Set identical params to saved result → prompt to reuse |

---

## 8. Partial Results / Checkpoints

| ID | Feature | Files | Verify |
|----|---------|-------|--------|
| F-070 | **Partial result table**: st.expander "Partial results (N found)" with st.dataframe. Columns: % Complete, Cells done, Date, f_bin range, pi/sigma range, logP grid, N_stars, Best p, Filename. Shows all `_partial_` .npz files | `file_ops.py` (`_render_partial_table`, `_scan_partial_metadata`) | Partial files listed after Cancel & Save |
| F-071 | **Resume from partial**: clicking a partial row sets `{p}_resume_from` path. On next Run, background thread loads partial .npz and prefills completed grid cells (non-NaN entries). Computation skips already-done cells, starting from checkpoint % | `runners_cadence.py`, `runners_dsilva.py`, `runners_langer.py` | Resume 50% partial → progress starts at ~50%; final result includes all cells |
| F-072 | **Auto-resume flag**: `{p}_auto_resume` session_state boolean, set when user clicks resume in partial table. Triggers Run automatically on next page render without clicking Run button | tab files | Click resume in partial table → run starts automatically |
| F-073 | **Partial file naming**: `_build_partial_filename()` generates `{model}_partial_{fb_range}_{pi_range}_N{n}_{sig_range}_{timestamp}.npz`. The `_partial_` tag distinguishes from complete results | `file_ops.py` | Partial files clearly distinguishable in directory listing |
| F-074 | **Partial .npz contents**: stores `progress_pct` (float 0–1), `rows_done` (int), `total_rows` (int) alongside all scoring arrays (ks_p, ks_D, etc.) with NaN for incomplete cells. Also stores full config for resume validation | `runners_*.py`, `file_ops.py` | Loading partial → correct % shown; NaN cells identifiable |

---

## 9. Progress Bar & Live Updates

| ID | Feature | Files | Verify |
|----|---------|-------|--------|
| F-080 | **Progress bar**: `st.progress(pct, text=...)` showing "X/Y cells (Z%) — ETA HH:MM:SS". Updates every 3 seconds via polling fragment. Percentage tracks completed grid cells / total grid cells | `polling.py`, runners | Bar fills 0→100% during run; text shows meaningful counts |
| F-081 | **ETA formatting**: `_fmt_eta()` formats elapsed/remaining time as "HH:MM:SS" for <24h, "Xd HH:MM:SS" for longer runs. Based on elapsed time × (remaining/completed) ratio | `helpers.py` (`_fmt_eta`) | ETA decreases as run progresses; format switches at 24h boundary |
| F-082 | **Status text**: shows current computation slice — "σ=X.XX km/s, logPmax=Y.YY" (if scanning), plus "cells done/total" count. Updated by background thread into `job['progress_text']` | `polling.py`, runners | Text shows correct sigma/logPmax value for current slice |
| F-083 | **@st.fragment(run_every=3) polling**: `_render_running_fragment()` decorated with `@st.fragment(run_every=3)` — rerenders only this UI section every 3 seconds, not the entire page. Non-blocking: main UI stays responsive | `polling.py` | Progress updates without full page reload; widgets remain interactive |
| F-084 | **Live 2×2 heatmap grid**: during run, shows 4 heatmaps side-by-side (K-S p-value, K-S weighted, CvM p-value, Likelihood) that progressively fill in as grid cells complete. Uses `job['live_heatmaps']` dict updated by background thread | `polling.py` (`_render_heatmap_row`) | Heatmaps partially filled during run; fully complete at end |
| F-085 | **Live 1D sigma profile**: line chart of max p-value vs σ_single. Only shown if sigma is scanned (n_sig > 1). Updates after each sigma slice completes. Uses `_make_max_pval_fig()` from helpers | `polling.py`, `helpers.py` | Chart grows one point per sigma slice during run |
| F-086 | **Live 1D logPmax profile**: line chart of max p-value vs logP_max. Only shown if logPmax is scanned. Updates per logPmax slice | `polling.py`, `helpers.py` | Same progressive update pattern as sigma profile |
| F-087 | **Final heatmaps persisted**: after job completes, live heatmaps and 1D profiles are copied from `job` dict to `{p}_final_live_heatmaps` / `{p}_final_live_sigma_1d` session_state keys. Job dict is then cleaned up, but final renders survive | `polling.py` | Job finishes → heatmaps still visible after cleanup; navigate away and back → still there |
| F-088 | **1 Hz update throttling**: background thread limits live heatmap writes to once per second (not after every task). Prevents I/O bottleneck from flooding session_state with large arrays | `runners_cadence.py` | No visible lag during run despite frequent task completion |

---

## 10. Result Display — Heatmaps

| ID | Feature | Files | Verify |
|----|---------|-------|--------|
| F-090 | **2D heatmap** (f_bin × π or f_bin × σ) per scoring method. Uses `make_heatmap_fig()` from shared.py with PLOTLY_THEME. Interactive: hover shows exact values, zoom/pan enabled | `analysis.py`, `scoring_detail.py`, `shared.py` | Heatmap renders with correct axis labels and data range |
| F-091 | **Best-fit gold star marker**: scatter point at global maximum, color #DAA520 (darker gold for readability on white/colored backgrounds), star symbol, size 12 | `analysis.py`, `scoring_detail.py` | Gold star visible at correct grid cell |
| F-092 | **Colorbar**: method-specific titles via `_METHOD_COLORBAR_OVERRIDE` dict — e.g., "K-S p-value", "CvM empirical p", "Normalized Likelihood". Color scales vary by method | `helpers.py` | Each method tab shows appropriate colorbar title |
| F-093 | **Sigma browse slider**: st.select_slider shown when n_sig > 1. Discrete values from sigma_grid with `format_func=lambda v: f'{v:.2f}'`. Changing slice updates the displayed 2D heatmap | `cadence.py`, `dsilva.py` | Slider shows sigma values; heatmap changes on selection |
| F-094 | **logPmax browse slider**: st.select_slider when n_logPmax > 1. Format: `f'{v:.2f}'`. Selects which logPmax slice to display | `cadence.py`, `dsilva.py` | Slider values match logPmax_grid; heatmap updates |
| F-095 | **4D outer grid** (Dsilva with both scans): when both sigma and logPmax are scanned, displays σ × logPmax grid of 2D heatmaps. Each cell shows f_bin × π heatmap for that (σ, logPmax) combination | `dsilva.py` | Both scans on → matrix of small heatmaps visible |
| F-096 | **Canvas size applied globally**: height/width from F-003 passed to all `st.plotly_chart()` calls via session_state keys | `05_bias_correction.py` | Change canvas height → all charts on all tabs resize |
| F-097 | **Three heatmaps per scoring method** (in detail view): (a) **Raw statistic** — all grid points, colorbar shows S-score or -logL; (b) **Score-masked** — only plausible points (CvM: p∈[0.05, 0.95]; Likelihood: L ≥ 5% of max), implausible = white/NaN; (c) **Normalized score** — CvM empirical p-value or normalized likelihood [0,1]. Each heatmap stacked vertically with captions | `scoring_detail.py:188-260` | All 3 heatmaps show different views of same data; masked version has white regions |
| F-098 | **3D surface plot with camera presets**: interactive Plotly 3D paraboloid surface (50×50 grid, Viridis_r colorscale, opacity 0.7) + grid data points (size 3 markers) + gold star at minimum (size 8). Camera radio: Default (eye 1.5,1.5,1.2), Top-down (0,0,2.5), Front (1.5,0,0.5), Side (0,1.5,0.5). Height 500px | `scoring_detail.py:337-430` | Camera radio switches viewpoint; surface + points + star visible |
| F-099 | **3D quadratic fit + 3 projection surfaces**: when sigma or logPmax scan has >1 value, fits 10-coefficient 3D quadratic surface. Renders 3 cross-section projections (f_bin×y at best z, f_bin×z at best y, y×z at best f_bin), each 50×50 with paraboloid + grid points + gold star | `scoring_detail.py:437+`, `fitting.py` | 3 projection plots visible; success box shows "3D minimum: f_bin=X, y=Y, z=Z, S=W" |

---

## 11. Scoring Methods & Summary Table

| ID | Feature | Files | Verify |
|----|---------|-------|--------|
| F-100 | **4 scoring methods computed per run**: K-S standard (two-sample on binned CDF), K-S weighted (variance-weighted max deviation), CvM (Cramér–von Mises with inverse-variance weighting), Likelihood (binned multinomial log-likelihood normalized to [0,1]). All 4 computed in single simulation pass | `wr_bias_simulation.py`, all runners | Result dict contains ks_p, ks_D, weighted_p, weighted_D, cvm_p, cvm_D, cvm_S_raw, logL_raw, likelihood |
| F-101 | **Summary table**: st.dataframe with columns — Method, Best f_bin, 68% HDI f_bin (mode ⁺ᵘᵖ₋ₗₒ), Best [π or σ], 68% HDI [π or σ], Best σ_single (if multi-sigma), Score (best value), Agreement. One row per method. Handles 2D/3D/4D grid modes | `analysis.py` (`_render_method_summary_section`) | Table has 4 rows; HDI bounds make sense; best values match heatmap stars |
| F-102 | **68% HDI computation**: `compute_hdi68()` uses binary search for horizontal line height enclosing 68% area under 1D posterior curve. Linear interpolation for smooth bounds. Returns (mode, lower_bound, upper_bound) | `wr_bias_simulation.py` (`compute_hdi68`) | HDI interval contains mode; width reasonable for grid resolution |
| F-103 | **Radio button method selector**: st.radio (horizontal) with 4 options (K-S Standard, K-S Weighted, CvM, Likelihood). Switching changes which method's detail analysis is displayed below | `subtabs.py` (`render_model_subtabs`) | Click each radio → different heatmap/analysis appears |
| F-104 | **Agreement check**: for each method, checks if its best-fit f_bin falls within every OTHER method's 68% HDI. Shown as "Yes"/"No" in Agreement column of summary table | `analysis.py` | If all methods agree, all show "Yes"; outlier method shows "No" |
| F-105 | **Score vs sigma profile** (per-method): in each method's expander, line chart showing best score (max p-value or min S-score) at each sigma value. Uses `_make_max_pval_fig()` or `_make_min_score_fig()` from helpers. Only shown when n_sig > 1 | `analysis.py` | Line chart with n_sig points; peak/minimum identifiable |
| F-106 | **Score vs logPmax profile** (per-method): same as F-105 but for logPmax axis. Only shown when n_logPmax > 1 | `analysis.py` | Line chart with n_logPmax points |
| F-107 | **Per-method summary table**: within each method expander, compact table with rows for each parameter — columns: Parameter, Best (grid), Mode ± HDI68, Interpolated (if parabolic fit available). Shows f_bin, x_axis, sigma (if multi), logPmax (if multi), Score | `analysis.py` | Table inside expander; interpolated column populated after fit |

---

## 12. CDF Comparison

| ID | Feature | Files | Verify |
|----|---------|-------|--------|
| F-110 | **4-trace CDF comparison plot**: observed ΔRV as solid black step function (width 2.5). For each of 3 scoring methods' best-fit point, **re-simulates 100 times** (seeds 42–141, N_stars = observed count) → computes median binned CDF (dashed line, method color) + 16th–84th percentile band (semi-transparent fill). Method colors from `SCORING_METHODS` constant | `analysis.py` (`_render_all_methods_cdf`) | 4 traces visible; observed clearly distinguished; shading shows spread |
| F-111 | **Confidence bands**: 16th–84th percentile envelope from 100 CDF realizations per method. Semi-transparent fill (opacity ~0.2) in method-specific color. Shows simulation variability at each bin edge | `analysis.py` | Shading width varies — wider at bins with fewer observed stars |
| F-112 | **CDF sanity check** (cadence tabs only): st.expander showing 5 random CDF draws vs observed at best-fit point. Each draw rendered as semi-transparent line. Verifies that observed CDF falls within typical simulation spread | `helpers.py` (`_render_cdf_sanity_check`) | 5 thin lines + 1 thick observed line; observed should be "among" the simulated |
| F-113 | **Legend & shadow toggling**: st.checkbox to show/hide CDF confidence bands and legend. Toggling updates plot without recomputation — purely visual control | `analysis.py` | Uncheck → shading disappears; legend toggles on/off |
| F-114 | **Model Explorer**: interactive exploration of parameter space with live feedback. Sliders for f_bin [0,1], x_val [grid range], σ_single [grid range] (if multi-sigma), logPmax [grid range] (if present). Updates in real-time: CDF plot (observed + simulated median ± 68% band), ΔRV histogram, detection fraction metric, and per-method score value. Uses `_me_cdf_band()` (cached, N_sets=50) | `analysis.py` (`_render_model_explorer`) | Move f_bin slider → CDF and histogram update; detection % changes |
| F-115 | **Detection fraction metric** (in Model Explorer): displays "Detected: X / Y (Z%)" where detection applies the full binary criterion: ΔRV > 45.5 km/s AND ΔRV − 4σ > 0. Shows how many simulated binaries would be classified as detected at the current parameter point | `analysis.py` | At f_bin=1.0 → high detection %; at f_bin=0.1 → fewer detections |

---

## 13. Per-Method Detail Analysis

| ID | Feature | Files | Verify |
|----|---------|-------|--------|
| F-120 | **Per-method heatmap** (in method expander): 2D slice at best sigma/logPmax with best-fit gold star. If multi-sigma AND multi-logPmax, shows additional cross-section heatmaps (f_bin × logPmax max over σ; σ × logPmax max over f_bin) | `scoring_detail.py`, `analysis.py` | Heatmap matches summary table's best-fit for that method |
| F-121 | **1D marginal slices**: line charts slicing through best-fit along each parameter axis. Grid points as markers, score values on y-axis. For 2D: 2 columns (x-slice, y-slice); for 3D: 3 columns (x, y, z slices) | `scoring_detail.py`, `fitting.py` | Slices pass through best-fit point; peak/minimum visible |
| F-122 | **68% HDI shaded regions on 1D slices**: blue semi-transparent rectangles between HDI lower and upper bounds on each 1D slice plot | `scoring_detail.py` | Shaded region contains the mode/peak |
| F-123 | **Parabolic fit overlay on 1D slices**: green curve from quadratic fit + green star at interpolated minimum/maximum. Different from gold grid-based star. Shows where refined best-fit falls between grid points | `fitting.py` (`_parabolic_min_1d`, `_render_cvm_1d_plot`) | Green curve smooth; green star between grid points |
| F-124 | **Corner plots**: NxN grid where diagonal = 1D posteriors with 68% HDI blue shading + red dashed mode line; off-diagonal = 2D marginalized heatmaps with 68% and 95% contour lines (white/gray) + gold star at best-fit. Layout: 2×2 (sigma + f_bin) or 3×3 (sigma + logPmax + f_bin). Requires ≥2 parameters | `corner_plots.py` (`_render_corner_plot`) | NxN grid renders; contour lines at 2 levels; posteriors show HDI shading |
| F-125 | **Re-simulation at interpolated best-fit**: in method expander, N_sets number_input (100–50,000, step 100) + "Re-simulate" st.button. Runs full simulation at parabolic-fit-interpolated (f_bin, x_val, sigma). Displays CDF with error band + observed overlay + metric card with score at interpolated point | `analysis.py` (`_render_resim_interp`) | Click Re-simulate → CDF appears with title "Re-sim: f_bin=X, x_label=Y" |
| F-126 | **2D quadratic surface fitting**: `_parabolic_min_2d()` fits 6-coefficient quadratic to grid neighborhood. Returns refined (x, y) coordinates + fitted value. Gold star on masked heatmap shows refined position | `fitting.py` | Success box: "Parabolic minimum: x = X.XXX, y = Y.YYY, S = Z.ZZZ" |
| F-127 | **Fit mode selector**: st.radio (horizontal) with 3 modes — "Height-based" (include points where S < S_min × factor, with 2D + per-axis factor sliders), "Range-based" (include points within ±fraction of grid range), "Neighborhood" (±N neighbors on each axis, max = grid_size/2). Each mode shows different sub-controls | `scoring_detail.py` | Switch mode → different parameter inputs appear; fit region changes |

---

## 14. Likelihood-Specific Features

| ID | Feature | Files | Verify |
|----|---------|-------|--------|
| F-130 | **CDF with likelihood bins overlaid**: st.checkbox "Show likelihood bins on CDF" in likelihood_viz.py. When checked, vertical dashed lines at bin edges appear on CDF plot. Separate "Show bin edges on CDF" checkbox in analysis.py model explorer | `likelihood_viz.py:130`, `analysis.py:1128` | Check → vertical lines appear at bin boundaries |
| F-131 | **Per-bin breakdown table**: st.dataframe with columns — Bin label (e.g., "0–45.5"), n_obs (observed count), n_sim (simulated count), p_i (sim fraction), ln(p_i), n_i·ln(p_i) (contribution to log-likelihood). Bottom row shows total ln L | `likelihood_viz.py` (`render_likelihood_stats_table`) | Sum of contributions = total ln L; zero-count bins handled |
| F-132 | **Methodology explainer**: st.expander "How is the likelihood calculated?" with 3 sections — (1) Raw log-likelihood formula with LaTeX: ln L = Σ nᵢ ln(pᵢ); (2) Normalization to [0,1] by dividing by max; (3) Why many points cluster near 1.0. Uses worked example with actual observed ΔRV bin counts | `likelihood_viz.py` (`render_likelihood_explanation`) | LaTeX renders; worked example uses real numbers |
| F-133 | **Threshold-based auto bin generation**: `dsilva_likelihood_bins(threshold)` returns `[0, threshold, 250, 650, ∞]`. Default threshold = 45.5 km/s (binary detection limit). Creates 4 bins matching Dsilva+2023 convention | `wr_bias_simulation.py`, `params.py` | Default bins = [0, 45.5, 250, 650, inf] |
| F-134 | **Likelihood normalization to [0,1]**: after computing log-likelihood for all grid points, divides by global max across entire grid (including all sigma/logPmax slices). Enables cross-slice comparison where "1.0 = best fit found anywhere" | `wr_bias_simulation.py`, runners | Max normalized likelihood = 1.0; other values ≤ 1.0 |
| F-135 | **Scoring version field**: .npz files contain `scoring_version=2` for forward-compatibility. Allows future changes to scoring methods without breaking old result loading | runners | Key exists in saved .npz; can be checked before loading |

---

## 15. Analysis Plots (Simulation Tab)

| ID | Feature | Files | Verify |
|----|---------|-------|--------|
| F-140 | **Period distribution histogram**: shows log₁₀(P/days) distribution of simulated binaries at best-fit. **3 view modes** via st.radio: "Detected / Missed" (tomato red vs amber), "Case A / B" (steel blue vs amber, Langer only), "All (Det/Mis + A/B)" (all overlaid). **Normalization toggle**: "Probability density" (area=1) or "Probability" (fraction per bin). Vertical dashed lines at logP_min/logP_max bounds. Caption: missed systems concentrated at long periods | `sim_plots.py` (`render_period_distribution`) | Radio changes coloring; normalization toggles y-axis scale; vertical lines at bounds |
| F-141 | **Gap analysis plot** (binary fraction vs ΔRV threshold): X = threshold (0 to 1.05×max_ΔRV), Y = fraction of stars above threshold. **Elements**: blue curve (observed f_bin(T)), red dashed horizontal (intrinsic f_bin target), amber dashed vertical (45.5 km/s threshold), **filled areas** (amber = missed binaries below threshold, blue = single-star false positives above), **diamond marker** at observed point, **arrow annotation** showing gap between intrinsic and observed f_bin, **gap statistics box** ("Gap: X% — N missed / M binaries") | `sim_plots.py` (`render_binary_fraction_vs_threshold`) | All visual elements present; gap annotation shows correct numbers |
| F-142 | **Orbital histograms**: **9 parameter panels** (log₁₀P, e, q, K₁, M₁, M₂, i°, ω°, T₀ rad) in grid layout, 30 bins each. **5 view modes** via st.radio: "Compare detected vs missed" (red+amber), "Detected only", "Missed only", "All binaries (combined)", "Case A vs Case B" (Langer). Colors: red (detected), amber (missed), green (all). Legend with count in parentheses. Safety: empty arrays handled via `_safe_mask()` | `sim_plots.py` (`render_orbital_histograms`) | 9 panels visible; radio changes coloring; empty populations don't crash |
| F-143 | **Gap simulation caching**: 10,000-star simulation at best-fit point, cached via `{p}_gap_fingerprint` key. Only recomputed when best-fit parameters change (fingerprint = hash of f_bin, x_val, sigma, logPmax). Result stored in `{p}_gap_sim` session_state | `cadence.py`, `analysis.py` | Same best-fit → no recomputation; different best-fit → new simulation |
| F-144 | **Period histogram normalization toggle**: within F-140's view, radio for "Probability density" (area under curve = 1) vs "Probability" (fraction per bin, matches Langer+2020 Fig. 6 convention). Only available when Case A/B decomposition is shown | `sim_plots.py` | Toggle changes y-axis label and bar heights |

---

## 16. Interpolation & Fitting

| ID | Feature | Files | Verify |
|----|---------|-------|--------|
| F-150 | **1D parabolic fit**: `_parabolic_min_1d()` fits quadratic y = ax² + bx + c to selected grid points. 3 modes: "height" (points where S < S_min × factor), "range" (±fraction of axis range), "neighborhood" (±N neighbors). Returns interpolated minimum x_opt, y_opt, and fit coefficients | `fitting.py` | Mode changes which points are included; green star on plot shows x_opt |
| F-151 | **2D quadratic surface fit**: `_parabolic_min_2d()` fits 6-coefficient surface z = a₀ + a₁x + a₂y + a₃x² + a₄xy + a₅y². Respects exclusion mask. Returns refined (x_opt, y_opt, z_opt), coefficients, and fit bounds | `fitting.py` | Gold star on masked heatmap at (x_opt, y_opt); success message |
| F-152 | **3D quadratic surface fit**: `_parabolic_min_3d()` fits 10-coefficient surface. `_eval_3d_quadratic()` evaluates fit at arbitrary coordinates. Used when sigma/logPmax add a third dimension | `fitting.py` | 3 cross-section projections rendered; success box shows 3D minimum |
| F-153 | **Interpolated best-fit display**: after parabolic fit, shows refined coordinates alongside grid-based values in per-method summary table (F-107). If fit succeeded, "Interpolated" column shows sub-grid-resolution estimates | `analysis.py` | Interpolated values differ slightly from grid values (not snapped to grid) |

---

## 17. Compare Tab

| ID | Feature | Files | Verify |
|----|---------|-------|--------|
| F-160 | **Multi-select results table**: st.dataframe with `on_select` allowing multiple row selection. Requires minimum 2 results to proceed. Shows all saved .npz files (both Dsilva and Langer). Warning if >6 selected: "plots may be crowded" | `extras.py` (`_render_compare_tab`) | Select 2+ rows → comparison UI appears; <2 → message "Select 2 or more" |
| F-161 | **View mode toggle**: st.radio ("Side-by-side" / "Overlay"). Side-by-side: each result's heatmap in separate column (up to 3 columns). Overlay: single plot combining multiple results | `extras.py` | Toggle changes layout between grid and single plot |
| F-162 | **Overlay heatmap** (2 results, same model/shape): result 1 as filled heatmap (blue, opacity 0.6) + result 2 as contour lines (dotted, dark). Shows where two results agree/disagree spatially | `extras.py` | Both results visible on single plot; contours overlay on filled heatmap |
| F-163 | **Parameter overlay**: best-fit points from each result plotted on same heatmap with different marker colors and shapes. Color/dash rotation via `_CMP_COLORS` (10 colors) and `_CMP_DASHES` (5 dash patterns) | `extras.py` | Multiple star markers visible at different positions |
| F-164 | **Best-fit comparison table**: rows = selected results, columns = Result label, Model type, Best f_bin, f_bin HDI (mode ⁺ᵘᵖ₋ₗₒ), Best π/σ, π/σ HDI, p-value, S_raw (CvM), p(resim). Likelihood posteriors in separate section with pre-computed HDI | `extras.py` | Table aligns results for easy numerical comparison |
| F-165 | **Run parameters expander**: per result, collapsible expander showing full configuration — model type, timestamp, N stars, σ_measure, f_bin range × count, π range × count, σ_single range, logP range, e_model, q_model, M₁ spec, Langer period params (dist_A/B, μ, σ, weight_A). Formatted via `_format_run_params()` | `extras.py` | Expand → all config visible; parameters match saved .npz metadata |
| F-166 | **Parameter differences table**: extracts all settings keys across selected results, displays as table. Rows where values differ between results highlighted with orange background. Identical rows shown normally | `extras.py` | Differing parameters immediately visible via orange highlighting |
| F-167 | **1D posterior overlay**: f_bin posteriors from all selected results overlaid on single plot — each as line (color/dash) + HDI shading + dashed mode line. X-axis posteriors grouped by model type: π posteriors (Dsilva results) on left, σ posteriors (Langer results) on right | `extras.py` | Multiple posterior curves visible; HDI regions overlap/diverge |
| F-168 | **Likelihood posteriors** (Dsilva+2023 method): separate section using multinomial likelihood heatmap. Computes 1D f_bin + x-axis posteriors with HDI shadows. Only shown if likelihood data present in results | `extras.py` | Additional posterior section appears below K-S posteriors |
| F-169 | **Observed ΔRV CDF comparison**: solid black line (observed) + dashed colored lines (simulated CDF from best-fit of each result). For cadence results: includes median CDF with confidence band | `extras.py` | All CDF traces visible; observed stands out as solid black |

---

## 18. RV Errors Tab

| ID | Feature | Files | Verify |
|----|---------|-------|--------|
| F-170 | **Binary/single classification**: stars split into binary and single populations using ΔRV threshold (adjustable st.slider, 0–200 km/s, default 45.5) + 4σ significance criterion (ΔRV − 4σ > 0). Both criteria must be met for binary classification. Star filter radio: All / Clean only / Contaminated only | `extras.py` (`_render_rv_errors_tab`) | Changing threshold re-classifies stars; count of singles/binaries updates |
| F-171 | **Distribution fitting (per population)**: separate fitting UI for single and binary RV error distributions in 2-column layout. Each column has: distribution selector, parameter inputs, histogram + PDF overlay, AIC/BIC display, data summary (mean, median, std) | `extras.py` | Left column = singles, right column = binaries; each has independent controls |
| F-172 | **6 distribution models**: selectbox with Normal (μ, σ), Log-normal (s, loc, scale), Gamma (a, loc, scale), Weibull (c, loc, scale), Exponential (loc, scale), Flat/Uniform (loc, scale). Each type shows appropriate parameter inputs (0–4 columns). Positive-only distributions (lognorm, gamma, Weibull, expon) clamp x_lo to 0.001 | `extras.py` | Select each distribution → correct parameter inputs appear |
| F-173 | **Auto-fit (MLE)**: "Auto-fit" st.button per population. Fits selected distribution via scipy maximum likelihood estimation, stores fitted params in session_state. "📝 Record fit" button manually logs current params to fit history | `extras.py` | Click Auto-fit → params update to MLE values; PDF overlay updates |
| F-174 | **AIC/BIC/log-L scoring**: displayed below each fit — `"{dist} — AIC: X.X · BIC: X.X · log L: X.X"`. Lower AIC/BIC = better model (penalizes complexity). Higher log L = better fit | `extras.py` | Scores update after fitting; AIC < BIC for simple models |
| F-175 | **Q-Q plots**: quantile-quantile plot comparing theoretical quantiles from fitted distribution vs sample quantiles. Includes y=x reference line (red dashed). Theoretical quantiles via `ppf(np.linspace(0.5/n, 1-0.5/n, n), *params)`. Shows departure from distributional assumption | `extras.py` | Points close to y=x line = good fit; systematic deviation = poor fit |
| F-176 | **Fit history table**: session_state-cached log of all recorded fits. Columns: #, Distribution, Params, AIC, BIC, log L. "🗑️ Clear history" button resets the log | `extras.py` | Multiple fits accumulate; clear removes all |
| F-177 | **Auto-fit all distributions**: "🔍 Run Auto-Fit" button fits all 6 distributions via MLE, displays ranked table (sorted by AIC). For the best-fit model: shows histogram + Q-Q plot side by side | `extras.py` | Click → table of 6 models appears; best model highlighted |
| F-178 | **Combined population overlay**: histogram of single vs binary error distributions overlaid (different colors). Two-sample K-S test comparing the populations: displays D statistic, p-value, and significance interpretation at α = 0.05 level | `extras.py` | Both histograms visible on same axes; K-S result displayed below |
| F-179 | **Current error model reference**: collapsible st.expander "📋 Current Simulation Error Model" showing: fixed σ_measure, σ_single, combined σ_total = √(σ_measure² + σ_single²). Suggests per-epoch error draws from fitted distributions as future enhancement | `extras.py` | Expand → current model parameters visible |

---

## 19. Methodology Explainers

| ID | Feature | Files | Verify |
|----|---------|-------|--------|
| F-180 | **Per-tab methodology expander**: st.expander "📖 How this bias correction works" with scientific explanation tailored to each tab's model (Dsilva power-law, Langer 2020 OB+BH, cadence-aware variants). Contains LaTeX + markdown prose | `helpers.py` (`_render_methodology_expander`) | Expander content differs between Dsilva and Langer tabs |
| F-181 | **Inline LaTeX equations**: K₁ semi-amplitude formula, Kepler equation, true anomaly, RV curve, K-S test formula, binary detection criterion (ΔRV > 45.5 AND ΔRV − 4σ > 0). Rendered via Streamlit markdown | `helpers.py`, `subtabs.py` | LaTeX renders correctly; no broken math symbols |
| F-182 | **Per-scoring-method equations**: K-S two-sample D = max|F₁-F₂|, weighted D = max(|F₁-F₂|/σ), CvM S = Σ(F₁-F₂)²/σ², Likelihood ln L = Σ nᵢ ln(pᵢ). Each shown in context of the active scoring method tab | `subtabs.py` (`render_methodology_equations`) | Formulas match scoring method descriptions; LaTeX renders |
| F-183 | **Scoring explanation expander** (RV Errors tab): "ℹ️ What do the scores mean?" — explains AIC (2k − 2·ln L, penalizes params), BIC (k·ln n − 2·ln L, stronger penalty), log L (higher = better, no penalty) | `extras.py` | Expand → clear explanation of all 3 scoring metrics |

---

## 20. Settings Persistence & History

| ID | Feature | Files | Verify |
|----|---------|-------|--------|
| F-190 | **Widget values auto-saved to settings.json**: every parameter input has `on_change` callback calling `sm.save([section, key], value)`. Sections: `cadence_dsilva`, `cadence_langer`, `dsilva`, `langer`, `likelihood_config`. Closing/reopening app restores all parameter values | all tab files, `params.py` | Set f_bin_min=0.2 → close app → reopen → f_bin_min still 0.2 |
| F-191 | **Config hash for result matching**: `_stable_cfg_hash()` computes SHA256 of settings dict (sorted keys, JSON serialized). Stored in .npz as `config_hash`. Used by reuse detection (F-065) to match current settings to saved results | `helpers.py`, `file_ops.py` | Same settings → same hash; any param change → different hash |
| F-192 | **Run history logging**: `_append_run_history()` writes entry to `settings/run_history.json` on each grid run. Entry includes timestamp, model type, all parameters, and result summary | `file_ops.py` | JSON file grows after each run; entries have timestamps |
| F-193 | **Reuse detection**: `_find_reusable_fbin()` (Dsilva) and `_find_reusable_fbin_langer()` compare current settings to all saved .npz files. Checks: pi/sigma grids match, orbital params match (including q_flipped, langer_period_params, q_mu/sigma). Returns matching indices if found | `file_ops.py` | Configure identical params → "Reuse existing result?" prompt |

---

## 21. Background Execution Architecture

| ID | Feature | Files | Verify |
|----|---------|-------|--------|
| F-200 | **Daemon thread launch**: `threading.Thread(daemon=True, target=_run_{model}_bg, args=(job, params))`. Daemon=True ensures thread dies when app process exits. Job dict is shared mutable state between main thread and worker | `runners_dsilva.py`, `runners_langer.py`, `runners_cadence.py` | Run → thread starts; close browser → thread auto-terminates |
| F-201 | **Multiprocessing Pool with global initializer**: `mp.Pool(n_proc, initializer=_init_worker, initargs=(...))` stores shared read-only data (obs_delta_rv, bin_edges, cadence_library, error model params) in worker-global dict `_WORKER_GLOBALS`. Avoids pickling large arrays per task | `wr_bias_simulation.py`, runners | Workers access shared data; no per-task serialization overhead |
| F-202 | **Job state machine**: dict with keys `{status, error, result, cancel, cancel_mode, progress_pct, progress_text, live_heatmaps, live_sigma_1d, live_logPmax_1d, partial_saved}`. States: idle → running → {done, cancelled, error}. Error state captures full traceback string | all runners, `polling.py` | Status transitions correctly; error shows readable traceback |
| F-203 | **Concurrent tab execution**: each tab has independent job dict (`{p}_job`). Running a grid in one tab does not block other tabs. Can view results in Langer while Dsilva runs. No inter-tab locks (Python GIL handles dict access) | `05_bias_correction.py`, all tabs | Start Dsilva run → switch to Langer → Langer results still interactive |

---

## 22. Simulation Engine (wr_bias_simulation.py)

| ID | Feature | Files | Verify |
|----|---------|-------|--------|
| F-210 | **Power-law period sampling**: `sample_logP_powerlaw(pi, size, logP_min, logP_max, rng)` — draws logP from p(logP) ∝ (logP)^π. Special-cases π = −1 (CDF = ln(x/a)/ln(b/a)). Returns shape (size,) array | `wr_bias_simulation.py` | Histogram of samples matches expected power-law shape |
| F-211 | **Langer 2020 two-component period**: `sample_logP_langer2020()` — Case A + Case B mixture. Draws component assignment via weight_A, then samples from component-specific distribution. Optional `return_components=True` returns (logP, case_A_mask boolean) for decomposition plots | `wr_bias_simulation.py` | Bimodal histogram; weight_A=1.0 → only Case A peak |
| F-212 | **5 parametric distribution types**: flat (uniform), gaussian, lognormal (mode-based: μ_ln = ln(mode) + σ²), reflected_lognormal (mirrors around mode: 2×mode − sample), empirical (digitized histogram via `_sample_empirical(bin_edges, weights, size, rng)`). Used for both logP and q distributions | `wr_bias_simulation.py` | Each type produces expected shape; empirical matches Langer Fig. 4/6 |
| F-213 | **Kepler orbit solver**: `solve_kepler(M, e)` — Newton-Raphson iteration for E − e sin(E) = M. Tolerance 1e-10 rad, max 50 iterations. Vectorized over arrays. Initial guess E₀ = M | `wr_bias_simulation.py` | Converges for e ∈ [0, 0.99]; matches scipy reference |
| F-214 | **K1 semi-amplitude**: `compute_K1(P_days, e, M1, M2, i_rad)` — K₁ = [(2πG/P)^(1/3)] × (M₂ sin i) / [(M₁+M₂)^(2/3) √(1−e²)]. SI units internally (G=6.67430e-11, M_SUN=1.98847e30, DAY_S=86400). Vectorized | `wr_bias_simulation.py` | Output in km/s; typical WR binaries: K₁ ~ 10–200 km/s |
| F-215 | **Cadence-aware simulation**: `simulate_delta_rv_cadence_aware()` — each simulated system gets a REAL star's observation times (MJD sequence from cadence_library). N_sets repetitions, each with n_stars = len(cadence_library). System i always gets cadence i (deterministic assignment). Returns median/lo/hi CDF + per-bin variance + all ΔRV arrays | `wr_bias_simulation.py` | N_sets × n_stars ΔRV values generated; CDF envelope reflects cadence variability |
| F-216 | **7 error model types**: `_draw_measurement_noise(model_type, params, sigma_fallback, size, rng)` — fixed (Gaussian with σ), normal, lognormal, gamma, weibull, exponential, uniform. Each draws from scipy.stats distribution, applies random sign (symmetric). Falls back to fixed σ if model unrecognized | `wr_bias_simulation.py` | Each model produces noise with correct distribution shape |
| F-217 | **K-S two-sample tests**: standard `ks_two_sample()` (continuous, fallback Kolmogorov series p-value) and `ks_two_sample_binned()` (discrete bin edges: D = max|CDF_sim(bᵢ) − CDF_obs(bᵢ)|). Both return (D, p_value) | `wr_bias_simulation.py` | Standard matches scipy.stats.ks_2samp; binned works on discrete edges |
| F-218 | **Variance-weighted K-S D**: `ks_weighted_D(sim_median_cdf, obs_cdf, sim_cdf_var)` — D = max(|F_obs − F_sim| / σᵢ). Weights bins by inverse variance: low-variance bins (stable across repetitions) count more. Returns scalar D | `wr_bias_simulation.py` | Higher D when CDF diverges at low-variance bins |
| F-219 | **CvM weighted score**: `cvm_weighted_score()` — S = Σ (F_obs − F_sim)² / σ²ᵢ using all bins (not just max like K-S). Empirical p-value: recomputes S for each of N_sets individual CDF realizations vs median, fraction with S ≥ S_obs. Returns (S_obs, p_value, S_raw_unweighted) | `wr_bias_simulation.py` | Empirical p-value ∈ [0,1]; S_raw comparable across models |
| F-220 | **Multinomial log-likelihood**: `multinomial_log_likelihood(obs_drv, sim_drv_pooled, bin_edges)` — ln L = Σ nᵢ ln(pᵢ) where nᵢ = observed bin count, pᵢ = simulated bin fraction. Epsilon-clamped to avoid ln(0). Returns scalar ≤ 0 | `wr_bias_simulation.py` | Returns negative number; more negative = worse fit |
| F-221 | **Adaptive bin edges**: `adaptive_bin_edges(obs_drv, min_gap=1.0)` — auto-generates ~20–22 bin edges from sorted observed ΔRV values. Groups adjacent values within min_gap km/s (replaces with mean). Ensures first edge ≤ min(data) and last edge ≥ max(data) | `wr_bias_simulation.py` | ~20 edges for 25 stars; first edge ≈ 0, last ≥ max observed ΔRV |
| F-222 | **68% HDI computation**: `compute_hdi68(x_vals, posterior_1d)` — binary search for horizontal line height that encloses 68% of area under posterior curve. Linear interpolation for smooth bounds. Returns (mode_val, lower_bound, upper_bound) | `wr_bias_simulation.py` | mode within [lower, upper]; interval width reasonable |

---

## 23. Data Flow & Visualization Patterns

| ID | Feature | Files | Verify |
|----|---------|-------|--------|
| F-230 | **Log₁₀ scale toggle**: st.checkbox per scoring method detail view. Applies `np.log10(np.where(S > 0, S, np.nan))` to CvM S-scores and Likelihood values. Invalid values (≤0) masked as NaN to prevent log errors | `scoring_detail.py:60-72` | Toggle on → colorbar/axis shows log values; toggle off → linear |
| F-231 | **Custom hover templates**: all Plotly figures use `hovertemplate` with `<extra></extra>` to suppress default trace name box. Format: `'{x_label}=%{x:.2f}<br>score=%{y:.4f}'`. Applied to heatmaps, line charts, CDF plots | all plot modules | Hover shows clean formatted values; no secondary trace name box |
| F-232 | **PLOTLY_THEME consistency**: all plots use `fig.update_layout(**{**PLOTLY_THEME, ...})` from `shared.py`. Method-specific overrides via dict merge (not keyword args, to avoid E018 TypeError). Gold markers always #DAA520 | all plot modules, `helpers.py` | Consistent font, background, axis styling across all charts |
| F-233 | **st.empty() placeholder slots**: scoring_detail and polling use `st.empty()` to create re-renderable plot slots. Allows updating a plot in-place (e.g., adding gold star after parabolic fit) without creating duplicate charts | `scoring_detail.py`, `polling.py` | Plot updates in same location; no duplicates |
| F-234 | **Implicit validation**: all arrays checked with `np.isfinite()` before operations. Epsilon clamping for log operations: `np.maximum(x, eps)`. Empty arrays handled gracefully via early returns. Session state keys checked with `is not None` and `len() > 0` guards | all modules | No crashes on empty results, NaN-heavy arrays, or missing session keys |

---

## Quick Regression Test Checklist

After any change to `app/bc/` or `wr_bias_simulation.py`:

1. **Import check**: `conda run -n guyenv python error-check-workspace/test_bc_imports.py`
2. **Syntax check**: `conda run -n guyenv python -m py_compile <changed_file>`
3. **App loads**: `conda run -n guyenv streamlit run app/app.py` — navigate to Bias Correction page
4. **All 6 tabs render**: click each tab, verify no errors
5. **Parameter widgets**: change f_bin min/max, pi range, sigma range — verify persistence after navigation
6. **Load a saved result**: select from table → verify heatmap + analysis + summary table render
7. **Run a small grid**: f_bin 2 steps, pi 2 steps, N=100 → verify progress bar, ETA, live heatmaps, completion
8. **Cancel & Save**: start run, click Cancel & Save → verify partial file appears in partial table
9. **Resume partial**: click resume on partial → verify it starts from checkpoint %
10. **Save result**: click Save → verify toast + file in results/ + load table refresh
11. **Scoring methods**: click each radio (K-S, Weighted, CvM, Likelihood) → verify heatmap + analysis changes
12. **Grid exclusion**: narrow range in scoring detail → verify white regions on heatmap
13. **Model Explorer**: move f_bin slider → verify CDF + histogram + detection % update live
14. **Corner plots**: verify NxN layout with HDI shading and contour lines
15. **Compare tab**: load 2 results → verify side-by-side heatmaps + posteriors + differences table
16. **RV Errors tab**: adjust threshold slider → verify re-classification; run Auto-fit → verify AIC/BIC table
17. **3D surface**: if multi-sigma, verify 3D paraboloid renders with camera presets
