---
name: testable-code
description: Guide the coder agent to write testable Python code. This skill should be used when reviewing code architecture for testability, suggesting refactors that make code easier to verify, teaching separation of concerns, or when the QA agent struggles to test a function because of tight coupling. Triggers include untestable, hard to test, refactor for testing, dependency injection, separation of concerns.
---

# Testable Code

Guide the coder to write code that the QA agent can effectively test. Testable code is code where logic can be verified independently of UI, file I/O, and external state.

## Core Principle: Separate Logic from Side Effects

```python
# UNTESTABLE: Logic mixed with Streamlit UI
def render_classification_page():
    star = st.selectbox("Star", specs.star_names)
    obs = ObservationManager(data_dir='Data/')
    star_obj = obs.load_star_instance(star)
    rvs = load_rvs(star_obj)  # file I/O
    is_binary = check_binary(rvs)  # logic
    st.write(f"Binary: {is_binary}")  # UI

# TESTABLE: Logic extracted into pure function
def classify_star(rv_array, rv_err_array, threshold=45.5, sigma_factor=4.0):
    """Pure function: arrays in, boolean out. No I/O, no UI."""
    if len(rv_array) < 2:
        return False
    idx_min, idx_max = np.argmin(rv_array), np.argmax(rv_array)
    delta = abs(rv_array[idx_max] - rv_array[idx_min])
    sigma = np.sqrt(rv_err_array[idx_min]**2 + rv_err_array[idx_max]**2)
    return bool(delta > threshold and (delta - sigma_factor * sigma) > 0)

# UI layer just calls the pure function
def render_classification_page():
    star = st.selectbox("Star", specs.star_names)
    rvs, errs = load_rvs_for_star(star)  # thin I/O wrapper
    is_binary = classify_star(rvs, errs)  # testable!
    st.write(f"Binary: {is_binary}")
```

## Testability Patterns

### 1. Pure Functions
Functions that take inputs and return outputs with no side effects.
- **No** file reads/writes inside the function
- **No** Streamlit widgets (`st.write`, `st.selectbox`)
- **No** global state modification
- **Yes** to numpy arrays, dicts, numbers as inputs/outputs

### 2. Thin Wrappers for I/O
Keep I/O in thin, simple functions that just load/save:
```python
def load_star_rvs(star_name, line='C IV 5808-5812'):
    """Thin I/O wrapper — loads data, returns arrays."""
    obs = ObservationManager(data_dir='Data/', backup_dir='Backups/')
    star = obs.load_star_instance(star_name, to_print=False)
    rvs, errs = [], []
    for ep in star.get_all_epoch_numbers():
        rv_prop = star.load_property('RVs', ep, 'COMBINED')
        if rv_prop and line in rv_prop:
            entry = rv_prop[line].item()
            if entry['full_RV'] != 0:
                rvs.append(entry['full_RV'])
                errs.append(entry['full_RV_err'])
    return np.array(rvs), np.array(errs)
```

### 3. Configuration as Parameters
Don't hardcode thresholds or settings inside functions:
```python
# HARD TO TEST: Hardcoded values
def is_significant(delta_rv):
    return delta_rv > 45.5  # Where does 45.5 come from?

# TESTABLE: Parameters with defaults
def is_significant(delta_rv, threshold=45.5):
    return delta_rv > threshold
```

### 4. Return Values, Not Side Effects
```python
# UNTESTABLE: Modifies external state
def process_star(star, results_dict):
    results_dict[star.name] = compute(star)  # side effect

# TESTABLE: Returns result
def process_star(star):
    return compute(star)  # caller decides what to do with it
```

## What to Tell the Coder

When code is hard to test, communicate via `comms/qa.md`:

```
## Testability Issue
**Function:** `render_bias_grid()` in `app/bc/cadence.py:142`
**Problem:** Computation logic is mixed with Streamlit UI calls. Cannot test
the grid computation without running Streamlit.
**Suggestion:** Extract `compute_bias_grid(fbin_range, pi_range, config)` as a
pure function that returns the grid array. The render function calls it and
displays the result.
**Benefit:** QA can test grid computation with known inputs and verify outputs
without launching the webapp.
```

## Testability Checklist

For every function the coder writes, check:
- [ ] Can I call this function from a plain Python script (no Streamlit)?
- [ ] Does it return a value I can assert against?
- [ ] Are all parameters explicit (no hidden globals)?
- [ ] Can I test edge cases by varying inputs?
- [ ] Is file I/O separated from computation?

## Test Fixtures for This Project

When testing, use these known-good values:
- Star names: `specs.star_names` (list of 25 WC stars)
- Primary line: `'C IV 5808-5812'`
- Binary threshold: 45.5 km/s
- Sigma factor: 4.0
- Expected binary fraction: ~46% (13/28)
- RV range: typically -200 to +200 km/s for WR stars
