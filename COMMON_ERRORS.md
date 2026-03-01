# Common Errors & Known Pitfalls

This file documents recurring bugs and deprecated patterns found in this project.
**Claude checks these patterns automatically before and after writing code.**

## Quick-Scan Regex

Combined grep pattern for all known bad patterns (copy-paste ready):

```bash
grep -rn -E 'np\.trapz\b|\.bool_\b.*is (True|False)|\.int_\b|\.float_\b|\.complex_\b|\.object_\b|\.str_\b' --include='*.py' .
```

---

## Numpy Deprecations (numpy 2.x)

### E001 — `np.trapz` removed in numpy 2.0

| | |
|---|---|
| **Bad** | `np.trapz(y, x)` |
| **Fix** | `np.trapezoid(y, x)` |
| **Grep** | `np\.trapz\b` |
| **Why** | `numpy.trapz` was deprecated in 1.25 and removed in 2.0. Renamed to `numpy.trapezoid`. |
| **Found in** | `wr_bias_simulation.py`, `app/pages/05_bias_correction.py`, `CCF.py`, `CCF-old.py` |

### E002 — `numpy.bool_` identity comparison

| | |
|---|---|
| **Bad** | `if result is True:` (where `result` is `numpy.bool_`) |
| **Fix** | `if bool(result):` or `if result:` |
| **Grep** | `\.bool_\b.*is (True\|False)` |
| **Why** | `numpy.bool_(True) is True` evaluates to `False` because they are different objects. Always cast with `bool()` before using `is` comparisons. |
| **Found in** | Various files comparing numpy array element results |

---

## Data Handling

### E003 — Missing zero-filter on RV arrays

| | |
|---|---|
| **Bad** | Using raw RV arrays directly from `.npz` property files |
| **Fix** | `rv = rv[rv != 0]` before any analysis |
| **Grep** | *(not greppable — requires manual attention)* |
| **Why** | Missing/unavailable epochs are stored as `0.0` in the RV property arrays. Using them without filtering corrupts ΔRV calculations. |
| **Found in** | `pipeline/load_observations.py`, any code loading `full_RV` properties |

---

## Streamlit

### E004 — Duplicate widget keys in `st.empty()` slots

| | |
|---|---|
| **Bad** | Calling `slot.plotly_chart(..., key='same_key')` twice in one script run |
| **Fix** | Guard with `if not run_btn:` or use different keys for live vs display rendering |
| **Grep** | *(not greppable — requires manual attention)* |
| **Why** | Streamlit raises `StreamlitDuplicateElementKey` when two widgets in the same run share a key. `st.empty()` slots reused during live updates and post-run display can trigger this. |
| **Found in** | `app/pages/05_bias_correction.py` (heatmap slot) |

---

## Adding New Errors

When you encounter a new recurring error, add it here with:
1. An **ID** (E005, E006, ...) and descriptive title
2. The **bad** and **fix** code patterns
3. A **grep regex** if the pattern is machine-detectable
4. **Why** it happens
5. **Where** it was found
6. Update the **Quick-Scan Regex** at the top if a new greppable pattern was added
