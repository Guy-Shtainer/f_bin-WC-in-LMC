---
name: live-testing
description: Test Python code by running it and validating output. This skill should be used when verifying code changes work correctly, checking Streamlit pages render without errors, validating data accuracy against expected values, parsing tracebacks to explain root causes, or running integration tests against real data. Triggers include test, verify, check, validate, run, error, traceback, broken, crash.
---

# Live Testing

Test code by actually running it. Validate output. Parse errors and explain them clearly to the coder agent.

## Testing Workflow

### Phase 1: Static Check
```bash
# Syntax validation
conda run -n guyenv python -m py_compile <file.py>

# Import check (catches missing modules, circular imports)
conda run -n guyenv python -c "import <module>"

# Pyflakes (unused imports, undefined names)
conda run -n guyenv python -m pyflakes <file.py>
```

### Phase 2: Render Test (Streamlit)
```bash
# Run the project's render test with real data
conda run -n guyenv python scripts/test_render.py
```
This test imports key modules and verifies they can process actual star data without crashing.

### Phase 3: Live Validation
Run specific functions with real data and check outputs:

```python
# Example: Verify RV loading returns expected structure
from ObservationClass import ObservationManager
import specs

obs = ObservationManager(data_dir='Data/', backup_dir='Backups/')
star = obs.load_star_instance('BAT99-14', to_print=False)
rv_data = star.load_property('RVs', 1, 'COMBINED')

# Validate structure
assert rv_data is not None, "RV data missing for epoch 1"
assert 'C IV 5808-5812' in rv_data, "Primary line missing from RVs"
entry = rv_data['C IV 5808-5812'].item()
assert 'full_RV' in entry, "full_RV key missing"
assert isinstance(entry['full_RV'], (int, float)), f"RV is {type(entry['full_RV'])}, expected number"
```

### Phase 4: Data Accuracy Validation
**CRITICAL: No false data.** Verify computed values make physical sense:

```python
# RV values should be in reasonable range for WR stars
assert -500 < rv < 500, f"RV={rv} km/s is unreasonable for WR star"

# ΔRV should be positive
assert delta_rv >= 0, f"ΔRV={delta_rv} is negative"

# Binary fraction should be between 0 and 1
assert 0 <= f_bin <= 1, f"f_bin={f_bin} is out of range"

# Check array shapes match expectations
assert grid.shape == (n_fbin, n_pi), f"Grid shape {grid.shape} != expected ({n_fbin}, {n_pi})"
```

## Error Analysis

### Parsing Tracebacks
When a traceback occurs, extract and communicate:

1. **Error type:** `TypeError`, `ValueError`, `KeyError`, etc.
2. **Location:** File, line number, function name
3. **Root cause:** The actual mistake (not the symptom)
4. **Fix strategy:** Minimal change to resolve

### Communication Format (for coder agent)
Write to `comms/qa.md`:
```
## Bug Report
**Error:** [error type] at [file:line]
**Root cause:** [1 sentence explaining WHY it fails]
**Fix:** [specific, minimal change — e.g., "Cast numpy.bool_ with bool() at line 42"]
**Verify:** [how to confirm the fix works]
```

### Common Error Patterns in This Project

| Error | Root Cause | Fix |
|-------|-----------|-----|
| `TypeError: 'numpy.bool_' is not JSON serializable` | numpy.bool_ used where Python bool expected | `bool(value)` |
| `AttributeError: 'DataFrame' has no attribute 'applymap'` | pandas removed applymap | Use `.map()` |
| `TypeError: trapz() missing` | numpy removed np.trapz | Use `np.trapezoid()` |
| `FileNotFoundError: Data/...` | Data symlink broken by git | `ln -s ../Data Data` |
| `KeyError: 'MJD-OBS'` | Looking in wrong dict (RV vs FITS header) | Use `fit.header['MJD-OBS']` |
| `ValueError: zero-size array` | RV array not zero-filtered | Filter `rv[rv != 0]` first |

## Integration Testing Pattern

For testing a full pipeline step:
```python
# 1. Load real data
star = obs.load_star_instance(star_name, to_print=False)

# 2. Run the function under test
result = function_under_test(star, params)

# 3. Validate output type and shape
assert isinstance(result, expected_type)

# 4. Validate output values are physically reasonable
assert result_in_expected_range(result)

# 5. Validate against known reference (if available)
if reference_value is not None:
    assert abs(result - reference_value) < tolerance
```

## What Makes a Good Test Report

- **Specific:** "line 42 raises TypeError" not "something is wrong"
- **Actionable:** Include the exact fix, not just the problem
- **Minimal:** One fix per issue, smallest possible change
- **Verifiable:** Include how to confirm the fix works
