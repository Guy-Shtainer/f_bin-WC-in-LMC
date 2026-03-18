---
name: feedback_test_renders
description: NEVER skip testing Streamlit render functions — they work fine in bare mode with mock data
type: feedback
---

NEVER skip Streamlit render/tab functions during error-checking. They work outside `streamlit run`.

**Why:** User caught that render functions were being skipped as "needs Streamlit runtime" during error-check. In reality, Streamlit widgets silently no-op in bare mode — the functions run fine and any real bug (missing import, wrong key, bad logic) will raise an Exception.

**How to apply:** During error-check Phase 3c, always test render functions (`render_tab_*`, `render_page_*`, `_render_*_tab`) by calling them with a mock `obs_data` dict containing the required numpy arrays and palette dict. Only a raised Exception counts as FAIL. Streamlit WARNING log lines are expected and harmless. Updated in: `.claude/commands/error-check.md`, `.claude/skills/error-checker.md`, `CLAUDE.md`.
