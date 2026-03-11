---
name: project-debug
description: Proactive debugging and bug-prevention skill for this Python/Streamlit scientific project. Triggers BEFORE writing any code to enforce a pre-flight checklist, and when debugging runtime errors, tracebacks, broken UI, or unexpected behavior. Also triggers when the user reports a bug, says "it's broken", "not working", "error", "fix this", shares a traceback, or when Claude is about to make changes to Streamlit pages, simulation code, or data processing logic. This skill complements error-checker (which scans for known patterns) by enforcing a structured debugging methodology that prevents bugs from being introduced in the first place.
---

# Project Debug — Proactive Bug Prevention

This skill reduces bugs by enforcing a structured pre-flight checklist before writing code and a systematic debugging methodology when issues arise. It is specific to this WR binary analysis project (Python, Streamlit, numpy, multiprocessing).

## Pre-Flight Checklist (BEFORE writing/editing code)

Run through this mental checklist before making any change. Each item addresses a class of bugs that has occurred in this project.

### 1. Environment & Imports
- Am I testing with `conda run -n guyenv python ...`? (base Python lacks numpy, astropy, etc.)
- Am I importing from the right path? (`from shared import ...` in `app/pages/`, NOT `from app.shared import ...`)
- If adding a new import, does the module actually exist in guyenv? Quick check: `conda run -n guyenv python -c "import <module>"`

### 2. Streamlit Specifics
- **Widget keys**: Will any widget key be duplicated in a single run? (E004) Especially in `st.empty()` slots reused for live updates AND final display.
- **Cache keys**: Am I using `@st.cache_data` with underscore-prefixed params? Those are EXCLUDED from the cache key (E023). `_star_name` means all stars get the same cached result.
- **Session state**: Am I reading `st.session_state[key]` before the widget that creates it has run? Use `.get(key, default)` pattern.
- **Multiprocessing in pages**: Functions passed to `multiprocessing.Pool.map()` must be in a separate importable module, not defined in `app/pages/*.py` (E022). Streamlit pages run as `__main__`.
- **Page navigation**: `st.page_link()` paths are relative to the entrypoint directory, not CWD (E012).
- **Concurrent UI**: Long computations must use background threads + polling (daemon thread + `@st.fragment(run_every=3)`), never block the main thread.

### 3. Numpy & Data
- **numpy.bool_**: Never use `is True` / `is False` on numpy results. Cast with `bool()` first (E002).
- **numpy truth-value**: Never `if arr:` on a numpy array. Use `arr.size > 0` or `len(arr) > 0`.
- **Zero-filter**: RV arrays from `.npz` files contain `0.0` for missing epochs. Filter: `rv = rv[rv != 0]` (E003).
- **np.trapz**: Removed in numpy 2.0. Use `np.trapezoid()` (E001).

### 4. Plotly Theme
- **PLOTLY_THEME collision**: Never use `title=`, `legend=`, `xaxis=`, `yaxis=`, `font=` as kwargs alongside `**PLOTLY_THEME`. Use dict literal: `fig.update_layout(**{**PLOTLY_THEME, 'title': ...})` (E018).

### 5. Variable Lifecycle
- Before REMOVING any variable/widget, grep for ALL references to it in the file. Fix every downstream use (E025).
- Before ADDING a field to a config dataclass, audit ALL cache/reuse/hash functions that compare configs (E024).
- In dict/list comprehensions, don't reuse a variable name that shadows a function parameter (E021).

### 6. Git & Data Safety
- After ANY git operation, verify `Data/` symlink: `ls -la Data` → should show `Data -> ../Data`. Restore: `ln -s ../Data Data` (E019).
- Always commit to `main`. Check `git branch` first. If on an agent branch, switch to main.

## Debugging Methodology (WHEN a bug occurs)

Follow this structured approach. Do NOT guess-and-fix repeatedly.

### Step 1: Read the actual error
- Read the FULL traceback, not just the last line
- Identify the exact file and line number
- Note the exception type (TypeError, KeyError, NameError, etc.)

### Step 2: Read the data BEFORE the code
- When UI shows wrong values: READ THE RAW DATA FIRST. Don't assume data format matches expectations. (Lesson learned: wasted 4 attempts fixing display code when the data had no time components)
- Load the actual `.npz` file or session_state value in question
- Print/log the shape, dtype, and sample values

### Step 3: Reproduce minimally
- Can the bug be triggered with `conda run -n guyenv python -c "..."` ?
- For Streamlit: Does it happen on page load, on button click, or only with specific data?
- For multiprocessing: Does it happen with `Pool(1)` (serial)?

### Step 4: Check known patterns
- Read `COMMON_ERRORS.md` — is this a known pitfall?
- Run the Quick-Scan Regex on the affected file
- Check the Skills Auto-Trigger Guide in MEMORY.md — is there a domain-specific skill that should handle this?

### Step 5: Fix with verification
- Make the minimal fix
- Run `conda run -n guyenv python -m py_compile <file>` — must produce zero output
- Run the Quick-Scan Regex on the modified file
- If Streamlit: verify the page loads without errors

### Step 6: Prevent recurrence
- If this is a new class of bug, add it to `COMMON_ERRORS.md` with ID, pattern, grep regex, fix, and explanation
- Update the Quick-Scan Regex if the pattern is greppable

## Streamlit-Specific Debug Patterns

### "Widget key already exists" error
- Two widgets with the same `key=` in one run
- Fix: Use unique keys, or guard with `if` to avoid rendering both

### Page shows stale/wrong data
1. Check `st.session_state` — is the key set correctly?
2. Check `@st.cache_data` — is an underscore param hiding differences?
3. Check if `st.rerun()` is needed after state change

### Multiprocessing crashes silently
- Move worker functions to separate `.py` file (E022)
- Check if worker function accesses Streamlit state (it can't — different process)
- Test with `Pool(1)` first to get readable tracebacks

### Plot not updating / showing old data
- Check if `st.empty()` slot is being reused correctly
- Check for key conflicts between live-update and final display
- Verify `fig` object is newly created, not mutated from cached version

## Quick Reference: Most Common Bug Types in This Project

| Rank | Bug Type | Prevention |
|------|----------|------------|
| 1 | Variable undefined after refactor | Grep for ALL uses before removing any definition |
| 2 | Cache returning wrong data | No `_` prefix on differentiating params; audit cache checks when adding config fields |
| 3 | PLOTLY_THEME kwargs collision | Always use `{**PLOTLY_THEME, ...}` dict literal |
| 4 | numpy type mismatches | Always `bool()` cast; never `if arr:` |
| 5 | Missing zero-filter on RVs | Always `rv[rv != 0]` before analysis |
| 6 | Multiprocessing pickle errors | Worker functions in separate module |
| 7 | Wrong conda env | Always `conda run -n guyenv` |
