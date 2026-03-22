---
name: error-pattern-lessons
description: Lessons from analyzing 187 commits of working history — patterns that cause consecutive errors and wasted time. Apply these before every fix attempt.
type: feedback
---

## Top 3 Time Wasters (from real data)

### 1. Fixing symptoms without checking data (Task #72 — 4x same mistake)
All 4 attempts fixed display code without reading the source data first.
**Why:** Assumed the data format matched expectations. Never verified.
**How to apply:** Before ANY fix, read the raw data/state first. Print it. Don't guess what's in a variable — look at it. "DATA BEFORE DISPLAY" is not just a rule, it's the #1 time-saver.

### 2. Exploring dead-end approaches sequentially (KS weighting — 3 failed attempts)
Three normalization approaches all failed because they explored the same direction without stepping back.
**Why:** Each attempt was a small tweak on the previous one, not a fundamentally different approach.
**How to apply:** After 2 failed attempts at the same problem, STOP. Ask: "Am I varying the same knob, or trying a genuinely different approach?" If same knob → step back, reconsider methodology, or ask the user.

### 3. Incomplete fixes that cascade (exclusion masks → 5 NaN guards)
First fix addressed the symptom (shape mismatch) but left downstream code vulnerable to the now-possible NaN arrays.
**Why:** Fixed the crash site without tracing all downstream consumers of the changed data.
**How to apply:** After fixing a bug, grep for every consumer of the changed function/variable. Ask: "If this value is now NaN/None/empty/different-shape, what breaks downstream?" Fix those too in the same commit.

## Quantified Impact
- 53% of working time goes to error correction (should be <30%)
- 12.3% of all commits are cascading fixes (should be <5%)
- 9 cascade chains detected in 2 weeks
- COMMON_ERRORS.md grows at 2.1 errors/day — error-check skill should slow this

## Pre-Fix Checklist (apply before every bug fix)
1. Read the raw data/state — don't assume
2. Is this the same approach I already tried? If yes, try something different
3. After the fix: grep all downstream consumers — what else could break?
4. Run `/error-check` on modified files before committing

## Pre-Edit Checklist (apply before every code change — learned 2026-03-18)
1. **Before adding a function call**: grep for the function definition — is it imported? Are all variables it uses in scope?
2. **Before adding a parameter to a function**: grep ALL callers of that function — update every one
3. **Before claiming a pattern fix is complete**: grep ALL instances of the pattern across the entire codebase
4. **When user says "remove X from the page"**: trace the rendering code path to identify the EXACT lines. Don't assume which file/function renders it.
5. **Confidence gate**: if understanding of user's request < 90%, STOP and ask. Signs of low confidence: "I think they mean...", "probably...", "I assume...". One clarifying question saves 4 wrong attempts.
6. **If user repeats a request**: that means I misunderstood the first time. ASK what they mean rather than trying the same approach again.
## DO NOT TOUCH WORKING CODE — 5 Mandatory Blocks (learned 2026-03-22)

**Why:** Cadence resume fix — rewrote task filter, array init, removed guards in
runners_cadence.py when the entire fix was 10 lines in cadence.py. Broke features
that were working. User explicitly set these rules.

### Block 1: ROOT CAUSE FIRST
Before editing ANY file, identify the single root cause and write it down.
No edits until I can state: "The bug is at file:line because X."
**How to apply:** State the root cause in my response before touching code.

### Block 2: ONE FILE ONLY
If the bug is in one file, edit only that file. Touching a second file requires
explicit justification to the user first.
**How to apply:** If I'm about to open a second file for editing, STOP and ask.

### Block 3: REVERT TEST
After making a fix, mentally check: "If I revert every OTHER change I made,
does the fix still work?" If not, I'm editing unnecessary code.
**How to apply:** Before committing, list all changes. For each non-root-cause
change, ask: "Is the fix broken without this?" If no → revert it.

### Block 4: ASK BEFORE REFACTORING
If I see code I think is "wrong" or "improvable" near the bug, I must NOT
touch it. If I really think it matters, mention it and let the user decide.
**How to apply:** Never edit code that isn't the root cause. Mention concerns
in text, don't act on them.

### Block 5: FLAG WORKING CODE
Use `# ── WORKING · {feature} ──` comment flags above functions or code segments
that implement a working feature. These flags mean: DO NOT MODIFY this code
unless the user explicitly asks to change THIS feature.
**How to apply:** When I encounter or verify working code during investigation,
add the flag. When I see the flag during a fix, skip that code entirely.
