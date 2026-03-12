# Plan: Fix and Improve 06_plots.py (Visualization Gallery)

## Summary of Issues Found
After thorough exploration of the 1456-line Plots page, I identified **15 issues** across 5 categories.

## Round 1: Critical Bugs (3 issues)
1. **`is_clean_bool` logic inverted** (line 297): `is_clean_bool = not has_cleaned` means `True` = "has NO cleaned data". But line 301 shows `'✓' if is_clean_bool else 'X'`, meaning stars WITHOUT cleaned data get a checkmark. Caption says "Clean = ✓ means no contamination" which is semantically backwards. Fix: rename to `has_no_cleaning` or invert the logic.
2. **`rv_err if rv_err else 0`** (line 1283): If rv_err is exactly `0.0` (valid), this evaluates falsy → returns 0. Should be `rv_err if rv_err is not None else 0`.
3. **`_load_ccf_settings()` reads `st.session_state` inside `@st.cache_data`** (line 274): `cached_load_drv_analysis` calls `_load_ccf_settings()` which reads `st.session_state`. Streamlit warns against this. Fix: refactor to use `@st.cache_data` for ccf_settings loading instead.

## Round 2: Performance (2 issues)
4. **Binary fraction vs threshold loop not cached** (lines 742-759): 396 threshold values × 25 stars × 11 lines = ~109K iterations, runs on every page render. Fix: Extract to cached function.
5. **`_get_epochs()` not cached** (line 261): Called repeatedly per star without `@st.cache_data`. Fix: Add `@st.cache_data` decorator.

## Round 3: Dead Code Cleanup (4 issues)
6. Remove `_load_normalized_spec` (lines 148-159) — never called, superseded by `_load_spectrum`
7. Remove `_get_star_config` (lines 143-145) — defined, never called
8. Remove `_wilson_score_interval` (lines 251-258) — defined, never called
9. Remove unused imports: `apply_theme`, `get_palette` from shared import

## Round 4: UX and Polish (4 issues)
10. **Missing caption on confidence grading chart** (line 849): `_show(fig_grade)` has no caption parameter
11. **Corner plot hardcodes theme** (lines 983-989): Manually replicates _ACADEMIC_THEME values instead of using the dict
12. **NRES_STARS hardcoded** (line 46): Should discover NRES stars from ObservationManager or specs
13. **Hardcoded annotation color `#333333`** (lines 123, 660): Fine for white bg but not reusable

## Round 5: Final Quality Pass
14. Verify all charts have captions
15. Add explanatory comments for the 4σ significance test
16. Self-test the entire execution flow

## Pre-Implementation Validation
- **First load**: User sees the X-Shooter Spectra tab with normalized spectra auto-loaded for the first star. All tabs auto-populate. ✓
- **Cached functions**: Uses `cached_load_observed_delta_rvs`, `cached_load_drv_analysis`, `cached_load_grid_result` from shared ✓
- **PLOTLY_THEME**: Page uses `_ACADEMIC_THEME` with `_academic_fig(**overrides)` pattern — correct dict-merge, no E018 risk ✓
- **Structural template**: Standard boilerplate (sys.path, inject_theme, render_sidebar) ✓

## Files Modified
- `app/pages/06_plots.py` (primary target)
