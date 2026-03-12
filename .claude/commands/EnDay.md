End-of-day documentation, paper update, and commit workflow.

Run this command at the end of each working session to ensure all work is properly documented, errors are catalogued, the paper is updated, and changes are committed with a working-version tag.

## Steps

1. **Read today's daily conversation log:**
   - Check if `daily_logs/{YYYY-MM-DD}.md` exists in the project root (where `{YYYY-MM-DD}` is today's date).
   - If it exists, read the full file. This contains structured summaries from each conversation today (written by the `/EndConv` command). Use these as primary context — they capture discussions, decisions, and work that may not appear in git history.
   - If it does not exist, note that no conversation logs were saved today and rely on git history alone.

2. **Inventory today's work:**
   - Run `git log --since="today" --oneline` and `git diff --stat` to see all commits and uncommitted changes from today.
   - Read `.claude/command_history.log` for additional context on what was done.
   - **Cross-reference with daily log:** The conversation log may mention work, decisions, or discussions not reflected in commits. Merge both sources into a complete picture.
   - Identify: new features, bug fixes, refactors, research findings, simulation runs.

3. **Audit TODO.md:**
   - Read `TODO.md` and the git log from Step 2, plus the daily conversation log from Step 1.
   - **Cross-reference commits with tasks:** For each commit/change today, find the matching task in TODO.md. If the task still shows `open` but was clearly worked on, update its status to `to-test`.
   - **Scan conversation log for missing tasks:** The daily log may mention work or discussions that have no corresponding TODO.md entry. Add new entries with proper attribution, full datetime, and status (`to-test` if completed, `open` if not yet started).
   - **Report changes:** List every TODO.md update (status changes and new entries) so the user can review before proceeding.

4. **Document errors in COMMON_ERRORS.md:**
   - Review all bugs fixed today (from git log messages, code diffs, and conversation context).
   - For each bug, check if it already has an entry in `COMMON_ERRORS.md`.
   - If not documented, add a new entry following the existing format:
     - ID (next available E0xx), descriptive title
     - Bad / Fix code patterns
     - Grep regex (if machine-detectable)
     - Why it happens
     - Where it was found
   - Update the Quick-Scan Regex at the top if a new greppable pattern was added.

5. **Update DOCUMENTATION.md Section 7 (Work Log):**
   - Check if today's date already has an entry. If so, expand it; if not, create a new one.
   - Entry format (scientific prose for thesis reference):
     - **What was done:** List features, fixes, and research with enough detail for paper writing.
     - **Key results:** Numbers, best-fit values, fractions, statistical findings.
     - **Methodology notes for paper:** Any method details that should go in the thesis.
     - **Decisions:** Design choices and their rationale.
     - **Bugs found and fixed:** Brief list with COMMON_ERRORS.md IDs.
     - **Open questions:** Unresolved scientific or technical questions.
   - Update the "Last updated" date at the bottom of the file.

6. **Update the paper (paper/sections/*.tex):**
   - Review today's work for scientific content that belongs in the paper.
   - Check TODO markers in paper sections — fill in any that can now be addressed.
   - Common updates: bias correction results, new methodology descriptions, table data.
   - Update macros in `paper/main.tex` if key numbers changed (e.g., `\fbincorr`, `\pibestfit`).
   - Follow A&A journal conventions and match the style of existing sections.

7. **Commit changes (one logical change per commit):**
   - Commit documentation updates: `COMMON_ERRORS.md`, `DOCUMENTATION.md`
   - Commit paper updates: `paper/sections/*.tex`, `paper/main.tex`
   - Commit any remaining code changes (group by feature/fix)
   - Follow the project's commit message conventions from `CLAUDE.md`.

8. **Tag as working version:**
   - Create an annotated git tag: `git tag -a v{YYMMDD}-working -m "Working version: {brief summary of day's work}"`
   - This gives a named rollback point the user can return to.

9. **Update GIT_LOG.md:**
   - Add entries for all new commits with hash, summary, and brief description.

## Important Notes

- Always check `git branch` first — commit to `main` only.
- After any git operation, verify `Data/` symlink: `ls -la Data`.
- Run `conda run -n guyenv python -m py_compile` on any modified `.py` files.
- Set completed TODO.md tasks to `to-test`, never `done`.
- Cross-reference all today's work against TODO.md — no completed task should remain `open`.
- Use scientific language in DOCUMENTATION.md — it's thesis reference material.
