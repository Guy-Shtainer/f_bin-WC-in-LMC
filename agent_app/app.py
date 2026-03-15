"""
agent_app/app.py — Agent Control Panel (Simplified)
────────────────────────────────────────────────────
Single-page webapp for selecting tasks and monitoring the ralph-loop agent.
Launch: conda run -n guyenv streamlit run agent_app/app.py
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent

import streamlit as st

st.set_page_config(
    page_title="Agent Control Panel",
    page_icon="🤖",
    layout="wide",
)

# Paths
TASK_FILE = _ROOT / ".claude" / "agent-task.json"
STATUS_FILE = _ROOT / ".claude" / "agent-status.json"
TODO_FILE = _ROOT / "TODO.md"

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _parse_todo_tasks():
    """Parse Open Tasks table from TODO.md. Returns list of dicts."""
    if not TODO_FILE.exists():
        return []
    text = TODO_FILE.read_text(encoding="utf-8")

    # Find Open Tasks table
    match = re.search(r"## Open Tasks\s*\n\|.*\n\|[-| ]+\n((?:\|.*\n)*)", text)
    if not match:
        return []

    tasks = []
    for line in match.group(1).strip().split("\n"):
        cols = [c.strip() for c in line.split("|")[1:-1]]  # skip leading/trailing |
        if len(cols) < 6:
            continue
        try:
            tid = int(cols[0])
        except (ValueError, IndexError):
            continue
        tasks.append({
            "id": tid,
            "title": cols[1],
            "description": cols[2][:120] + ("..." if len(cols[2]) > 120 else ""),
            "priority": cols[3] if len(cols) > 3 else "medium",
            "status": cols[5] if len(cols) > 5 else "open",
        })
    return tasks


def _read_status():
    """Read .claude/agent-status.json if it exists."""
    if not STATUS_FILE.exists():
        return None
    try:
        return json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _write_task_file(queue, freeform_text=None):
    """Write .claude/agent-task.json with the task queue."""
    data = {"queue": queue, "created_at": datetime.now().isoformat()}
    if freeform_text:
        data["freeform"] = freeform_text
    TASK_FILE.parent.mkdir(parents=True, exist_ok=True)
    TASK_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# Auto-refresh (every 3 seconds when agent is running)
# ─────────────────────────────────────────────────────────────────────────────
try:
    from streamlit_autorefresh import st_autorefresh
    status = _read_status()
    if status and status.get("phase") not in (None, "idle", "all_done"):
        st_autorefresh(interval=3000, limit=None, key="agent_refresh")
except ImportError:
    pass  # st_autorefresh not installed, manual refresh only

# ─────────────────────────────────────────────────────────────────────────────
# Header
# ─────────────────────────────────────────────────────────────────────────────
st.title("Agent Control Panel")

# ─────────────────────────────────────────────────────────────────────────────
# Section A: Live Status
# ─────────────────────────────────────────────────────────────────────────────
status = _read_status()

if status and status.get("phase") not in (None, "idle", "all_done"):
    phase = status.get("phase", "unknown")
    task_title = status.get("title", "Unknown task")
    task_id = status.get("task_id", "?")
    started = status.get("started_at", "")

    # Phase badge colors
    phase_colors = {
        "starting": "🟡", "explore": "🔍", "plan": "📋",
        "implement": "🔨", "quality_check": "✅", "commit": "💾",
        "failed": "❌",
    }
    badge = phase_colors.get(phase, "⚙️")

    # Elapsed time
    elapsed_str = ""
    if started:
        try:
            delta = datetime.now() - datetime.fromisoformat(started)
            mins = int(delta.total_seconds() // 60)
            elapsed_str = f" ({mins}m elapsed)"
        except ValueError:
            pass

    st.info(f"{badge} **{phase.upper()}** — Task #{task_id}: {task_title}{elapsed_str}")

    # Log entries
    log = status.get("log", [])
    if log:
        log_text = "\n".join(f"[{e.get('time', '')}] {e.get('msg', '')}" for e in log[-15:])
        st.code(log_text, language="text")

    # Error
    if status.get("error"):
        st.error(f"Error: {status['error']}")

    # Completed tasks count
    completed = status.get("completed_tasks", [])
    if completed:
        st.success(f"Completed {len(completed)} task(s) this session: {completed}")

    st.divider()

elif status and status.get("phase") == "all_done":
    completed = status.get("completed_tasks", [])
    st.success(f"All tasks complete! Finished {len(completed)} task(s): {completed}")
    st.divider()

# ─────────────────────────────────────────────────────────────────────────────
# Section B: Task Selection + Launch
# ─────────────────────────────────────────────────────────────────────────────
st.subheader("Launch Agent")

mode = st.radio(
    "Task source",
    ["Pick from TODO.md", "Free-form task"],
    horizontal=True,
    key="task_mode",
)

selected_ids = []
freeform_text = None

if mode == "Pick from TODO.md":
    tasks = _parse_todo_tasks()
    open_tasks = [t for t in tasks if t["status"] == "open"]

    if not open_tasks:
        st.warning("No open tasks in TODO.md.")
    else:
        # Priority sort
        prio_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        open_tasks.sort(key=lambda t: prio_order.get(t["priority"], 3))

        # Multiselect with formatted labels
        options = {t["id"]: f"#{t['id']} [{t['priority']}] {t['title']}" for t in open_tasks}
        selected_ids = st.multiselect(
            "Select tasks (ordered by priority)",
            options=list(options.keys()),
            format_func=lambda x: options[x],
            key="task_select",
        )

        if selected_ids:
            st.caption(f"{len(selected_ids)} task(s) selected")

else:
    freeform_text = st.text_area(
        "Task description",
        placeholder="Describe what the agent should do...",
        key="freeform_text",
    )

# Launch section
st.divider()
max_iter = st.number_input("Max iterations", min_value=1, max_value=200, value=20, key="max_iter")

c1, c2 = st.columns(2)

with c1:
    if st.button("Save Task Queue", type="primary", key="save_queue"):
        if mode == "Pick from TODO.md":
            if not selected_ids:
                st.error("Select at least one task.")
            else:
                _write_task_file(queue=selected_ids)
                st.success(f"Saved {len(selected_ids)} task(s) to queue. Now run the agent from terminal.")
        else:
            if not freeform_text or not freeform_text.strip():
                st.error("Enter a task description.")
            else:
                _write_task_file(queue=[], freeform_text=freeform_text.strip())
                st.success("Saved freeform task. Now run the agent from terminal.")

with c2:
    if st.button("Clear Queue", key="clear_queue"):
        if TASK_FILE.exists():
            TASK_FILE.unlink()
            st.info("Queue cleared.")

# Terminal command
st.markdown("### Run in Terminal")
st.code(f"bash scripts/launch-agent.sh {max_iter}", language="bash")
st.caption(
    "Or run directly: "
    f"`/ralph-loop \"/run-task\" --max-iterations {max_iter} --completion-promise ALL_DONE`"
)

# ─────────────────────────────────────────────────────────────────────────────
# Section C: History
# ─────────────────────────────────────────────────────────────────────────────
st.divider()
st.subheader("Recent Git History")

try:
    result = subprocess.run(
        ["git", "log", "--oneline", "-10"],
        capture_output=True, text=True, cwd=str(_ROOT), timeout=5,
    )
    if result.returncode == 0 and result.stdout.strip():
        st.code(result.stdout.strip(), language="text")
    else:
        st.info("No git history available.")
except (subprocess.SubprocessError, OSError):
    st.info("Could not read git history.")

# Rollback info
with st.expander("Rollback Instructions"):
    st.markdown("""
If something goes wrong, run in terminal:
```bash
git reset --hard pre-agent-rewrite && ln -sf ../Data Data
```
This restores everything to the state before the agent rewrite.
""")
