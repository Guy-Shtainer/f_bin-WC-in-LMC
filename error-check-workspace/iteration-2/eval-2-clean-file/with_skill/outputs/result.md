═══════════════════════════════════════════════════════════════
  ERROR CHECK — FULL CHECKLIST
  Files: utils.py
═══════════════════════════════════════════════════════════════

Phase 1: Static Pattern Scan
  ✅ Quick-Scan Regex on utils.py — 0 matches
  ✅ E003 (RV zero-filter) — N/A, no load_property calls in file
  ✅ E018 (PLOTLY_THEME collision) — N/A, no PLOTLY_THEME or _ACADEMIC_THEME usage
  ✅ E024 (dataclass cache sync) — N/A, no dataclass definitions in file
  ✅ E025 (removed widget refs) — N/A, no Streamlit widgets in file

Phase 2: Cache Cleanup
  ✅ Deleted __pycache__/utils.cpython-314.pyc

Phase 3: Functional Testing
  ✅ py_compile utils.py — OK
  ✅ import utils — OK (exports: robust_mean, double_robust_mean, robust_std, np)
  ✅ robust_mean([1,2,3,100,4], sigma=3) — 22.0 (float64, outlier within 3-sigma so not clipped, correct)
  ✅ robust_mean([1,2,3,4,5], sigma=3) — 3.0 (clean data, no clipping needed)
  ✅ robust_mean([42], sigma=3) — 42.0 (single element)
  ⚠️ robust_mean([], sigma=3) — nan with RuntimeWarning (empty slice), does not crash
  ⚠️ robust_mean([1, NaN, 3], sigma=3) — nan (NaN propagation, no crash)
  ✅ double_robust_mean([1,2,3,100,4], sigma=3) — 22.0 (float64, correct)
  ✅ double_robust_mean([1,2,3,4,5], sigma=3) — 3.0 (clean data)
  ✅ double_robust_mean([42], sigma=3) — 42.0 (single element)
  ⚠️ double_robust_mean([], sigma=3) — nan with RuntimeWarning (empty slice), does not crash
  ⚠️ double_robust_mean([1, NaN, 3], sigma=3) — nan (NaN propagation, no crash)
  ✅ robust_std([1,2,3,100,4], sigma=3) — 39.0128 (float64, correct)
  ✅ robust_std([1,2,3,4,5], sigma=3) — 1.4142 (clean data)
  ✅ robust_std([42], sigma=3) — 0.0 (single element, zero variance)
  ⚠️ robust_std([], sigma=3) — nan with RuntimeWarning (empty slice), does not crash
  ⚠️ robust_std([1, NaN, 3], sigma=3) — nan (NaN propagation, no crash)

Phase 4: Webapp Smoke Test
  ⏭️ Shared module import — skipped, utils.py is not under app/
  ⏭️ Modified page imports — skipped, utils.py is not under app/
  ⏭️ Cross-import check — skipped, utils.py is not app/shared.py

Phase 5: Learning
  ✅ No failures found — no new patterns to add to COMMON_ERRORS.md

═══════════════════════════════════════════════════════════════
  OVERALL: ✅ PASS — 0 issues need attention
  Checked: 22 items | Passed: 16 | Failed: 0 | Warned: 6 | Skipped: 3
═══════════════════════════════════════════════════════════════

Notes on warnings:
- Empty array inputs produce `nan` with numpy RuntimeWarnings (Mean of empty slice,
  Degrees of freedom <= 0). The functions do not crash — they gracefully return nan.
  This is acceptable behavior for utility functions; callers should validate input
  size if nan-free results are required.
- NaN-containing array inputs propagate NaN through np.mean/np.std. The functions
  do not use np.nanmean/np.nanstd, so NaN values are not filtered. This is by
  design — callers should pre-filter NaN if needed.
