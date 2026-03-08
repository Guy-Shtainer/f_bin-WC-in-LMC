The plan has been written to the output file. Here's a summary of what was planned:

## Task #40 Plan Summary

**Problem:** After adding a task in the To-Do page (`app/pages/10_todo.py`), all form fields retain their previous values, forcing the user to manually clear them.

**Root Cause:** Streamlit preserves widget values across `st.rerun()` via `st.session_state`. The widgets use `key=` params, so their state persists.

**Fix:** Insert 7 session state reset lines immediately after `save_todos(...)` in the button handler (line ~314):

```python
st.session_state['todo_new_title'] = ''
st.session_state['todo_new_desc'] = ''
st.session_state['todo_new_tags'] = ''
st.session_state['todo_new_added_by'] = 'Guy'
st.session_state['todo_new_suggested'] = 'Guy'
st.session_state['todo_new_urgent'] = False
st.session_state['todo_new_important'] = False
```

**Only 1 file changes:** `app/pages/10_todo.py` — a minimal, targeted edit with no risk of side effects on other page state (filters, inline edit forms, etc.).