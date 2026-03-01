---
name: documentation
description: Maintain the scientific documentation for thesis writing. This skill triggers at the end of each working session, when the user says "done", "let's stop", "wrap up", "save progress", "document this", "update docs", or similar. Also triggers after significant results are obtained, after meetings with Tomer (the supervisor), or when important scientific decisions are made. Always update DOCUMENTATION.md with a dated work log entry before ending a session.
---

# Documentation for Paper Writing

`DOCUMENTATION.md` at the project root is the primary reference for writing the
Masters thesis. It has two parts:

- **Sections 1–6:** Scientific methodology (sample, RV measurement, classification,
  bias correction, key numbers, references). Update these when methodology changes.
- **Section 7: Work Log:** Dated daily entries summarizing each session's work.

## When to Update

1. **End of every working session** — append a new entry to Section 7
2. **After obtaining significant results** — record key numbers immediately
3. **After meetings with Tomer** — document feedback, decisions, and new directions
4. **When methodology changes** — update the relevant section (1–6)

## Work Log Entry Format

Each entry in Section 7 follows this structure:

```markdown
### YYYY-MM-DD — Short descriptive title

**Meeting with Tomer (Nth):** (if applicable)
- Summary of feedback and requests...

**What was done:**
- Scientific work, code changes, analyses performed...
- Be specific: name the methods, files, and techniques used.

**Key results:**
- Any new measurements, best-fit values, thresholds, fractions...
- Include numbers with uncertainties when available.

**Decisions:**
- Why approach X was chosen over Y...
- Parameter choices and their justification.

**Open questions:**
- Things to revisit, verify, or discuss with Tomer...
```

## Writing Style

- Use **scientific language** — this will be adapted into thesis prose.
- Be **specific**: "Implemented Dsilva-style marginalization with HDI68 credible
  intervals" not "added error bars".
- Include **key numbers** every time — f_bin, π, σ, thresholds, sample sizes.
- Record **why** decisions were made, not just what was done.
- Keep entries **concise but complete** — 10–30 lines per session is typical.

## Important

- Never delete or overwrite previous entries — the log is append-only.
- Update the "Last updated" date at the bottom of the file.
- If a methodology section (1–6) needs updating, do that in addition to the
  work log entry, not instead of it.
