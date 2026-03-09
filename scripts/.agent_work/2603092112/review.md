# Review (Round 2): Revised Plan for Rebuild Plots Page (06_plots.py)

## Previous Issues — Were They Corrected?

### 1. E023 Violation (`_settings_hash` underscore prefix) — FIXED
The revised plan now uses `settings_hash: str` (no underscore) in the `cached_load_drv_analysis()` signature (Step 1, line 149). Additionally, a prominent "CRITICAL E023 NOTE" was added at line 156 explicitly warning against underscore prefixes. **Fully addressed.**

### 2. Use `apply_theme()` throughout — FIXED
The revised plan now consistently uses `apply_theme()` as the canonical pattern everywhere:
- Step 2 has a dedicated "CRITICAL THEME PATTERN" section (lines 214-219)
- Step 3 shows `apply_theme(fig, title=dict(text='...'), height=380)` in every plot
- A full "apply_theme() Usage Reference" section was added (lines 485-519) with do/don't examples
- The imports in Step 2 now include `apply_theme` (line 175)
**Fully addressed.**

### 3. Missing StarClass plot types — FIXED
The revised plan now includes:
- **Raw spectra viewer** with 5 toggles: Normalize, Rest frame, Log scale, Show continuum, Show RV emission lines (Step 2, items 2a-2e, lines 184-191)
- **Error spectra viewer** in an expander (Step 2, item 3, lines 192-195)
- **2D spectral image** via `go.Heatmap` with ValMin/ValMax sliders (Step 2, item 4, lines 197-201)
- **Extreme RV comparison** overlay (Step 2, item 6, line 210)
**Fully addressed.**

### 4. Missing notebook plots — FIXED
- **Epoch flux consistency scatter** (Cell 9/10) — added as Step 2 item 5 (lines 203-208)
- **Per-order NRES view** (Cells 29-30) — added in Step 9 item 2 (lines 317-326) with toggle for blaze correction, order selector, and WR17 special case
- **Blaze function visualization** (Cell 30) — added as Step 9 item 3 (lines 328-330)
**Fully addressed.**

### 5. NRESClass empty placeholder methods — FIXED
Step 7 now has an explicit NOTE (lines 290-291): "NRESClass.plot_spectra() and NRESClass.plot_spectra_errors() are empty placeholder methods (pass). These will NOT be ported." Also echoed in Risk 8 (line 395).
**Fully addressed.**

### 6. `apply_theme` added to imports — FIXED
Step 2 import block (lines 169-176) now includes `apply_theme` in the `from shared import (...)` statement.
**Fully addressed.**

### 7. `get_stitched_spectra3()` emphasis — FIXED
Step 7 item 4 (lines 301-302) explicitly states: "ALWAYS use NRESClass.get_stitched_spectra3() — this is the production version with low-blaze filtering. Never use get_stitched_spectra() (v1) or get_stitched_spectra2() (v2)."
**Fully addressed.**

---

## Were Correct Parts Preserved?

- Two-tab structure (X-Shooter / NRES) — preserved
- Sub-tab organization — preserved and enhanced
- Data access patterns reference section — preserved and correct
- Risk analysis — preserved and expanded (now 9 risks, up from 8)
- Verification checklist — preserved and expanded (now 27 items)
- TODO items (#21, #26, #27, #28) — preserved
- Backup step — preserved
- CCF Outputs and Grid Results sub-tabs — preserved

**All correct parts preserved.**

---

## What's Correct

1. **All 6 previous corrections applied**: Every issue from Round 1 was addressed with no shortcuts.

2. **Risk 9 is a valuable addition**: The plan correctly identifies that `preview_snr_stitch_cleaned_normalized()` is called in the notebook (cell 20) but does NOT exist in `StarClass.py` — confirmed by grep. The mitigation (skip it, use normalized flux comparison instead) is appropriate.

3. **apply_theme() reference section is excellent**: Lines 485-519 provide clear usage examples and explicit "NEVER do this" anti-patterns. This will prevent E018 errors during implementation.

4. **Data access patterns are accurate**: Verified against actual codebase:
   - `star.load_2D_observation(epoch, band)` → confirmed exists at StarClass.py:777
   - `star.load_observation(epoch, band)` → `data['WAVE'][0]`, `data['FLUX'][0]`, `data['ERR'][0]` — correct
   - NRES `get_stitched_spectra3()` returns `(wave, flux, snr)` — confirmed at NRESClass.py:2066
   - `cached_load_observed_delta_rvs(settings_hash)` uses non-underscore parameter — confirmed at shared.py:374

5. **Comprehensive sub-tab coverage**: The plan covers 5 X-Shooter sub-tabs and 3 NRES sub-tabs, mapping every significant notebook cell and class method to a specific location.

6. **Correct handling of wavelength units (#26)**: Step 10 correctly identifies that X-Shooter raw FITS data is in nm (needs ×10 for Å) while normalized properties and NRES data are already in Å.

7. **NRES WR17 special case documented**: Step 9 item 2 notes the reversed sky/object pairing for WR17 epochs 2 & 3 — this is a real gotcha that would cause wrong data if ignored.

---

## What Needs Fixing

### MINOR — `apply_theme` with nested dict keys may still collide

The plan shows:
```python
apply_theme(fig, title=dict(text='My Title'), height=480)
```

Since `PLOTLY_THEME` contains `title=dict(font=dict(...))` and `apply_theme` does `{**PLOTLY_THEME, **overrides}`, passing `title=dict(text='My Title')` as an override will **replace** the entire title dict (including the font styling from the theme). The title text will render but lose the themed font size/family/color.

The correct pattern should be:
```python
apply_theme(fig, title=dict(text='My Title', font=dict(size=15, family='serif', color=palette_title_color)))
```
Or, more practically, just pass `text` and let the theme's title font persist by merging:
```python
apply_theme(fig, title={**PLOTLY_THEME['title'], 'text': 'My Title'}, height=480)
```

**However**, this is a minor cosmetic issue — the title font will just fall back to the base `font` setting in `PLOTLY_THEME`, which is close enough. This can be fixed incrementally. Not a blocker.

### MINOR — File size estimate may be optimistic

The plan estimates 800-1200 lines. With 8 sub-tabs, each having multiple plot types with toggles, data loading, error handling, and `st.expander` wrappers, 1200-1500 lines is more realistic. Risk 5 acknowledges this but the mitigation ("limit initial scope") conflicts with the user's explicit request to cover all plots. The implementer should be prepared for a longer file and consider breaking helper functions into a separate module if it exceeds ~1200 lines.

---

## Corrections Required

None critical. The two minor notes above are cosmetic/planning awareness items, not blocking issues.

---

## New Issues Introduced?

No new issues were introduced in this revision. The plan is strictly better than the first version — it adds coverage without removing any previously correct content.

---

## Verdict

The revised plan comprehensively addresses all 6 issues raised in Round 1. The E023 fix eliminates a silent data corruption risk. The `apply_theme()` adoption removes the E018 hazard. All missing StarClass/NRESClass plot types and notebook cells are now covered with correct data access patterns. The verification checklist is thorough. The only remaining notes are minor cosmetic/sizing considerations that don't affect correctness.

**APPROVED**
