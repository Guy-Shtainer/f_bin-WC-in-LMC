---
name: error-checker
description: Automatically check for known bugs and deprecated patterns before and after writing code. This skill triggers whenever you are about to write, edit, or modify any Python file (.py), or when you are testing, compiling, or reviewing code. Also triggers when the user says "check for errors", "scan for bugs", "verify code", or similar. Always run the error scan BEFORE writing code (to avoid introducing known-bad patterns) and AFTER writing code (to catch anything that slipped through).
---

# Error Checker

## When This Triggers

1. **Before writing/editing any `.py` file** — scan your planned changes mentally
2. **After writing/editing any `.py` file** — run the automated grep scan
3. **During the `py_compile` verification phase** — run the scan as an additional check
4. **When the user asks to check for errors**

## Workflow

### Step 1: Load Known Patterns

Read `COMMON_ERRORS.md` at the project root. Extract the **Quick-Scan Regex**
from the top of the file — this is a single grep command with all known bad patterns.

### Step 2: Pre-Write Check

Before writing code, mentally review your planned changes against the known errors:
- Am I using `np.trapz`? → Use `np.trapezoid` instead (E001)
- Am I comparing `numpy.bool_` with `is True`? → Use `bool()` cast (E002)
- Am I loading RV arrays? → Remember to filter zeros (E003)
- Am I using `st.empty()` with keys? → Avoid duplicate keys in same run (E004)

### Step 3: Post-Write Scan

After editing files, run the Quick-Scan Regex against the modified files:

```bash
grep -rn -E 'np\.trapz\b|\.bool_\b.*is (True|False)' --include='*.py' <modified_files>
```

Replace `<modified_files>` with the actual paths of files you just edited.

### Step 4: Handle Matches

If any matches are found:
1. **Fix them immediately** — do not proceed to committing
2. Re-run the scan to confirm zero matches
3. Only then continue with `py_compile` and commits

### Step 5: During Testing

When running `py_compile` as part of the standard verification:
1. Run `py_compile` first
2. Then run the Quick-Scan Regex on the same files
3. Both must pass before the file is considered ready

## Adding New Errors

When you encounter a new error that could recur:
1. Add it to `COMMON_ERRORS.md` with ID, pattern, fix, grep regex, and explanation
2. Update the Quick-Scan Regex at the top of that file
3. The next time this skill triggers, it will automatically include the new pattern

## Important

- The source of truth is `COMMON_ERRORS.md` — always read it fresh
- Non-greppable errors (E003, E004) require manual attention during code review
- Greppable errors should be caught automatically every time
