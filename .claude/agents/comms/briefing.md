# Briefing

**Round:** 4
**Task:** Four changes to the Bin-Sensitivity sub-tab, per the plan the user approved at `/Users/guyshtainer/.claude/plans/i-really-liked-the-moonlit-flamingo.md`. That plan is the authoritative spec — read it first. This briefing summarises the must-knows for the coder and the rigid decisions the user locked in.

## Assigned agents (in order)
- **coder** — implement all 4 changes end-to-end
- **qa** — verify 7 acceptance criteria + regression of Round-2/3 guarantees

## The 4 changes (per the approved plan)

### Change 1 — A&A paper-ready style for ALL 6 plots
Swap the dark `PLOTLY_THEME` path for `_academic_fig()` from [app/plots/theme.py:37-48](app/plots/theme.py#L37-L48). The wrapper currently used by bin-sensitivity plots is `_layout_update()` at [app/bc/bin_sensitivity_plots.py:63-67](app/bc/bin_sensitivity_plots.py#L63-L67) — re-point it at `_academic_fig()` so the swap happens once and every plot inherits white bg, Times New Roman serif, black mirrored axes, no gridlines.

**Color touch-ups needed on white bg** (already flagged in the plan):
- Plot #6 rug color: `palette['font_color']` is light grey (for dark bg) → switch to `#333333` on white.
- Plot #6 row canvas opacity: bump from `0.12` → `0.18` so the faint scheme-family background is still visible on white.
- `_BIN_SCHEME_COLORS` hexes are unchanged — they were chosen in Round 1 to pass WCAG on BOTH backgrounds.

### Change 2 — Plot #4 overlap fix + caption
In `_plot_marginal_posteriors` at [app/bc/bin_sensitivity_plots.py:382-448](app/bc/bin_sensitivity_plots.py#L382-L448):
- `vertical_spacing=0.15` → `vertical_spacing=0.22` in `make_subplots(...)`.
- Drop `subplot_titles=(...)` from the constructor. Instead, add explicit `fig.add_annotation(x=0.5, y=1.02, xref='paper', yref=f'y{i} domain', showarrow=False, ...)` for each panel title, so the titles sit above each row with no collision risk.
- Move "Dsilva best" annotation from `add_vline(annotation_text=...)` to a `fig.add_annotation(...)` below the panel top (e.g. `y=0.92, yref='y1 domain'`), not above where it overlaps the subplot title.

**Caption under plot #4** (via `st.caption` in [app/bc/bin_sensitivity.py](app/bc/bin_sensitivity.py) where plot #4 is rendered):

> *1-D marginal posteriors over f_bin (top) and π (bottom), one curve per bin scheme. Each curve is the posterior density marginalised over the other parameter, normalised to unit area. The gold dashed line marks the Dsilva-default best-fit cell. If curves from different schemes peak near the same value, the bin choice is not biasing the recovered binary fraction; if they peak at different locations the posterior is bin-sensitive. Multi-modal curves (two separate peaks in one scheme) usually indicate an ε-floor artifact — a near-empty bin dominated by the 1/N_sim floor. See `memory/likelihood_bin_sensitivity.md §4` for pitfall details.*

### Change 3 — Plot #5 scientific caption
Add a `st.caption(...)` under plot #5:

> *Grey = observed per-bin counts; red = simulated counts at the best-fit cell, rescaled so their total equals the observed sample size for visual comparability. A well-fitting model has obs and sim bars matching within each bin — which is an indicator of fit quality, not of bin-choice methodology. A separate question is whether the obs heights should be roughly equal **across** bins (quantile/equal-count binning). Quantile binning maximises statistical power per bin and avoids ε-floor artifacts, but its edges are data-driven, which mildly reduces interpretability. It is a legitimate choice, not cherry-picking; the recommended practice is to compare a physically-anchored scheme (the Dsilva default) against a quantile scheme and report the spread as a systematic uncertainty. To try a quantile scheme, add a row with edges at the 20/40/60/80 percentiles of your observed ΔRV distribution.*

### Change 4 — Mock-data toggle (new feature)
The biggest change. The plan locked: **simple 2-option radio** at top of controls. No "Both" option, no hidden validation button.

**UI flow** (edit [app/bc/bin_sensitivity.py](app/bc/bin_sensitivity.py) around source-selector at line ~206):
1. Radio: `[Real observations (default), Mock observations (known truth)]` — 2 options only.
2. If radio = "Real observations" → show the existing `.npz` selectbox (unchanged).
3. If radio = "Mock observations" → show the `.npz` selectbox (still required for grid parameters) **plus** 4 number_inputs in one row:
   - `True f_bin` default 0.46 (from [render_validation.py:93](app/bc/render_validation.py#L93))
   - `True π` default 0.0
   - `True σ_single` default 15.0
   - `True log P_max` default 5.0
   - One more: `Mock RNG seed` number_input, default 42, so the user can reproduce a specific mock draw.
4. No "Regenerate mock sample" button — the sample is regenerated each time the user clicks "Run comparison" with the current slider/seed values (simpler than a separate button).

**Wire-up on "Run comparison"** (when radio is "Mock observations"):
1. Load `.npz` ctx normally for grid parameters.
2. Call `generate_mock_observations(true_fbin=…, true_pi=…, true_sigma=…, true_logPmax=…, cadence_library=ctx['cadence_library'], rng=np.random.default_rng(seed))` from [validation.py:79-127](validation.py#L79-L127).
3. The returned `(25,)` array replaces `obs_delta_rv` in the scoring loop. The scorer's signature (`rescore_scheme(..., obs=...)`) is already compatible — no scorer signature change needed.
4. Build a `ground_truth` dict: `{'f_bin': true_fbin, 'pi': true_pi, 'sigma': true_sigma, 'logPmax': true_logPmax}` and persist it on each `SchemeResult` as an optional field (new field: `ground_truth: Optional[dict] = None`).

**Truth overlays** (plan §Decisions §3 — all four selected by user):
- **Plot #2 (best-fit scatter)**: when any result has `ground_truth`, add a single gold star `#DAA520` (`symbol='star'`, size=22, line color `#000000` for contrast) at `(π_true, f_bin_true)`. Annotation label `truth` to the right.
- **Plot #4 (marginal posteriors)**: when `ground_truth` is present, add a second vertical dashed line in `#2CA02C` (green) at `f_bin_true` on row 1 and `π_true` on row 2. Annotation label `truth` below each line (in the panel-domain).
- **Plot #6 (bin-edge map)**: when `ground_truth` is present, add a top-right `fig.add_annotation(text=f"Truth: f_bin={true_fbin:.2f}, π={true_pi:.2f}", xref='paper', yref='paper', x=0.98, y=0.98, xanchor='right', showarrow=False, font=dict(size=10))`. Reminds the user the rug shown IS the mock sample. No rug colour change.
- **Summary table**: in mock mode, add two additional columns immediately after `f_bin*` and `π*`: `Δf_bin = best_fbin - true_fbin` (signed, 3 decimals) and `Δπ = best_pi - true_pi` (signed, 3 decimals). Hide these two columns in real-obs mode.

## Files to modify (authoritative list)

| File | Changes |
|------|---------|
| [app/bc/bin_sensitivity_plots.py](app/bc/bin_sensitivity_plots.py) | `_layout_update` → `_academic_fig`; plot #6 rug color + canvas opacity tweak; plot #4 title spacing + manual annotations; truth markers on plots #2, #4, #6 (all gated on `ground_truth is not None`). |
| [app/bc/bin_sensitivity.py](app/bc/bin_sensitivity.py) | Source radio (2 options); 4 number_inputs for true params + 1 for seed (mock mode only); wiring to `generate_mock_observations`; captions under plots #4 and #5; 2 extra summary-table columns in mock mode. |
| [app/bc/bin_sensitivity_scorer.py](app/bc/bin_sensitivity_scorer.py) | Add `ground_truth: Optional[dict] = None` to `SchemeResult` dataclass (one field). Thread it through from the kick-off in bin_sensitivity.py. No change to `_run_all_schemes_bg`'s scoring loop. |

**Reused verbatim (imports only, no changes):**
- `_academic_fig` from [app/plots/theme.py](app/plots/theme.py)
- `generate_mock_observations` from [validation.py](validation.py)
- Slider default values from [app/bc/render_validation.py:93-105](app/bc/render_validation.py#L93-L105)

## Acceptance criteria (Round 4)

1. All 6 plots render on white bg, Times New Roman serif, black mirrored axes, no gridlines.
2. Plot #4 subplot titles no longer collide with traces; vertical_spacing = 0.22; manual annotations used.
3. Plot #4 has an `st.caption` reading exactly as specified in §Change 2.
4. Plot #5 has an `st.caption` reading exactly as specified in §Change 3.
5. Source radio has 2 options ("Real observations", "Mock observations (known truth)"). "Real observations" is default.
6. Selecting "Mock observations" reveals 4 true-param number_inputs + 1 seed input. Selecting back reverts to the real-obs UI.
7. In mock mode, clicking "Run comparison" generates a synthetic 25-star sample via `generate_mock_observations` and runs the comparison on it. Plots #2, #4, #6 show the truth markers. Summary table has the two extra `Δf_bin` and `Δπ` columns.
8. **Regression (from Round 2/3)**: `_logL_one_scheme` matches `wr_bias_simulation.multinomial_log_likelihood` exactly. Seed formula from `runners_cadence.py:82-92` unchanged. E048 full-forwarding of bin_cfg/period_model/cadence_weights/sigma_meas intact. Render bug fix from Round 3 (`st.rerun(scope='app')` in the progress poller on done/error) still in place.

## Hard rules (memory)
- Only coder writes code.
- Surgical edits; don't refactor `_render_results` or the scorer's re-simulation loop.
- No matplotlib; Plotly only.
- No hardcoded hex outside `_BIN_SCHEME_COLORS` + `_academic_fig`'s palette + the three approved additions in this briefing (`#333333` rug, `#2CA02C` truth green, `#000000` gold-star border).
- Run `/error-check` after edits (pyflakes + `scripts/test_render.py`).
- Do NOT commit. QA verifies first.

## Upstream comms
- Previous coder output: `.claude/agents/comms/coder.md` (Round 3 summary)
- Previous QA output: `.claude/agents/comms/qa.md` (Round 3 PASS)
- Approved plan: `/Users/guyshtainer/.claude/plans/i-really-liked-the-moonlit-flamingo.md`

---
*Round 4 — polish + mock-data feature. Plan approved by user; no re-design.*
