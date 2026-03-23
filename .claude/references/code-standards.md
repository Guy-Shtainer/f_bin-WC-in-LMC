# Code Standards & Quality Rules

## Testing (mandatory after every edit)
1. For `app/bc/` changes: `conda run -n guyenv python error-check-workspace/test_bc_imports.py`
2. Then: `conda run -n guyenv python -m py_compile path/to/file.py`
3. Test Streamlit render functions directly — they work in bare mode with mock `obs_data` dict
4. `py_compile` alone is NOT sufficient — always run real functional tests first

## Pre-Fix Checklist (before every bug fix)
1. Read the raw data/state — don't assume
2. Is this the same approach I already tried? If yes → try something different
3. State root cause: "The bug is at file:line because X" — no edits until identified
4. After fix: grep ALL downstream consumers — what else could break?
5. Run `/error-check` on modified files before committing

## 5 Mandatory Blocks (bug fixes)
1. **ROOT CAUSE FIRST** — identify before editing. State it explicitly
2. **ONE FILE ONLY** — touching a second file requires user justification
3. **REVERT TEST** — would fix still work if I revert every OTHER change?
4. **ASK BEFORE REFACTORING** — don't touch "improvable" code near the bug
5. **FLAG WORKING CODE** — `# ── WORKING · {feature} ──` marks untouchable code

## File Size & Structure
- Max ~800 lines per `.py` file. If approaching 700+ → split before adding
- Pages: `pages/NN_name.py` (≤30 lines) → imports from `app/{name}/page.py`
- Check `wc -l` before adding code to existing files

## Workflow After Code Changes
After ANY code edit, automatically:
1. Run `/error-check` on modified files
2. If clean → offer to `/git` commit
3. If errors → fix and re-check (max 2 rounds, then ask user)

## Other Rules
- Check `COMMON_ERRORS.md` patterns before and after editing any `.py` file
- After fixing ANY runtime error → add to `COMMON_ERRORS.md` with ID, grep pattern, fix
- Backup before editing app pages: `cp app/pages/{file} Backups/{file}.bak`
- Commit each logical change separately
- After every push → update `GIT_LOG.md`
- TODO tasks: set to `to-test` on completion — NEVER `done`
- Progress bars (`st.progress()`) for any computation >5 seconds
- Use `/compact` after completing each major task within a session
- Use `/clear` when switching between unrelated work areas
