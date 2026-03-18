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
