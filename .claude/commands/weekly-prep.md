Prepare a structured meeting prep document for the biweekly meeting with thesis advisor Tomer. Gathers work done, results, open questions, and task status from all project data sources, then writes a scannable meeting prep to `daily_logs/weekly_prep_YYYY-MM-DD.md`.

If `$ARGUMENTS` contains a date (e.g., `/weekly-prep 2026-03-10`), use that as the start of the time range instead of auto-detecting.

## Step 1: Determine the time range

Search `DOCUMENTATION.md` Section 7 (Work Log) for the most recent entry matching the pattern `Meeting \d+ with Tomer`. Extract that date as `LAST_MEETING` and the meeting number as `N`.

- If `$ARGUMENTS` contains a date, use that as `LAST_MEETING` instead.
- If neither is found, fall back to 14 days ago.

The time range is: `LAST_MEETING` through today.

Print: "Preparing meeting prep for work since Meeting N (LAST_MEETING)."

## Step 2: Gather data from all sources

Read ALL of the following. Do not skip any source — each contains unique information.

**2a. Daily conversation logs:**
Read every file in `daily_logs/` with dates in the time range. These contain per-conversation structured summaries (topics, work done, decisions, open questions). This is the richest source of what actually happened day-to-day.

**2b. Git history:**
Run `git log --since="LAST_MEETING" --oneline --no-merges` to get all commits in the range. Also read `GIT_LOG.md` for the human-readable summaries grouped by date.

**2c. TODO.md:**
Read `TODO.md` in full. Extract:
- Tasks where `Suggested by` is `Tomer` — these are Tomer's requests; report their current status.
- Tasks that changed status (from `open` to `to-test` or `done`) within the time range (use `Date added` and any `[Modified ...]` annotations in Notes to judge timing).
- Critical/high priority tasks still `open` — potential discussion items.
- Also check for tasks where `Added by` is `Claude` but `Suggested by` is `Tomer` — these are tasks Claude created from Tomer's verbal requests during meetings.

**2d. DOCUMENTATION.md Section 7:**
Read Section 7 (Work Log) entries within the time range. These contain scientific prose — methodology details, key numbers, decisions with rationale. Extract anything Tomer should know about.

**2e. Run history:**
Read `settings/run_history.json`. Filter runs with timestamps in the time range. Note: which models were run (dsilva/langer/cadence_dsilva/cadence_langer), grid sizes, elapsed times, any new result files produced.

**2f. Results directory:**
Run `ls -lt results/*.npz` and identify files created within the time range (filename date stamps are YYMMDD-HHMM, e.g., `260315-1834` = 2026-03-15 18:34). Note the model type, parameter ranges, and grid sizes encoded in filenames.

**2g. Overleaf journal notes:**
Use the MCP Overleaf server to list and read files from the `journal_notes` project (project ID: `66bb2b0d21ca798da019ce76`). Look for any entries or notes added since LAST_MEETING. This contains thesis communication notes and may reference meeting action items or paper feedback.

If the MCP server is unavailable (connection error, timeout), skip this section and note: "Overleaf journal notes unavailable — check manually before the meeting."

**2h. Memory files:**
Read session memory files from the project memory directory:
`/Users/guyshtainer/.claude/projects/-Users-guyshtainer-Library-CloudStorage-OneDrive-Tel-AvivUniversity-----------Thesis-Thesis-codes/memory/`
Read any `session_*.md` files with dates in the time range. These contain architectural decisions, bug details, and context that daily logs may summarize too briefly.

## Step 3: Synthesize the meeting prep document

Organize all gathered information into the template below. **Group by theme, not by date.** Write in a conversational, scannable style — short paragraphs, bullet points, bold key numbers. This should read like talking points, not a data dump.

```
# Meeting Prep — Meeting {N+1} with Tomer
**Date:** {today}
**Period covered:** {LAST_MEETING} to {today}
**Previous meeting:** Meeting {N} on {LAST_MEETING}

---

## 1. Progress Summary

Group completed work by theme. Example themes:
- Bias correction methodology
- Simulation infrastructure
- Webapp / visualization
- Data analysis / RV measurements
- Paper writing

For each theme, 2-4 bullet points summarizing what was done and why it matters.
Highlight anything that addresses a request from the previous meeting with a checkmark.

## 2. Key Results

New quantitative findings since the last meeting:
- Best-fit parameter values (f_bin, pi, sigma_single) from new simulation runs
- K-S / CvM scores and p-values
- Changes to binary classification
- Model comparisons (Dsilva vs Langer, cadence vs non-cadence)

Include specific numbers. If no new results, say so explicitly.

## 3. Methodology Changes

Changes to the simulation or analysis approach that Tomer should review:
- New scoring methods, period/mass-ratio distributions
- Cadence-aware modifications, error propagation changes

For each: what changed, why, and whether it invalidates previous results.

## 4. Tasks from Tomer — Status Update

| Task ID | Title | Status | Notes |
|---------|-------|--------|-------|
(All TODO.md tasks where "Suggested by" contains "Tomer")

Flag any that are blocked or need his input.

## 5. Open Questions for Tomer

Numbered list of scientific or methodological questions needing his guidance.
Pull from "Open questions" in daily logs, DOCUMENTATION.md, and any decision
points where the direction is unclear.

## 6. Blockers & Challenges

Anything stuck, broken, or taking longer than expected.
If nothing is blocked, write "No current blockers."

## 7. Proposed Next Steps

What to work on after this meeting, in suggested priority order.
Pull from high-priority open tasks in TODO.md. Frame as prioritization questions:
- "Should I focus on X or Y next?"
- "Is Z important enough to implement before the paper draft?"

## 8. Paper Progress

- Sections written or updated on Overleaf
- DOCUMENTATION.md updates that feed into paper sections
- Figures generated for the paper
- Estimated paper completion status (if assessable from available data)
```

## Step 4: Save the document

Write the completed prep document to:
`daily_logs/weekly_prep_{YYYY-MM-DD}.md`
where `YYYY-MM-DD` is today's date.

## Step 5: Present a summary

After saving, print to the terminal:
- The time range covered and meeting number
- Number of commits, tasks completed, and simulation runs in the period
- **Top 3 discussion points** for the meeting (the most important items Tomer should hear)
- The file path where the full prep was saved

End with: "Review the full prep at `daily_logs/weekly_prep_{date}.md` before your meeting. Edit it to add anything I missed or remove things you don't want to discuss."

## Important Notes

- This command is READ-ONLY except for creating the prep document. Do NOT modify TODO.md, DOCUMENTATION.md, or any source files.
- The Overleaf MCP server is read-only. If unavailable, skip gracefully.
- For results/ filenames, date encoding is YYMMDD (e.g., 260315 = 2026-03-15).
- Filter run_history.json by timestamp — it can contain hundreds of entries.
- Memory session files live in the Claude project memory directory, not the project root.
