"""
pages/10_todo.py — Project To-Do List

Interactive task manager that reads/writes TODO.md at the project root.
Supports adding, completing, filtering, and sorting tasks.
"""
from __future__ import annotations

import os
import sys
import re
from datetime import date

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import streamlit as st
from shared import inject_theme, render_sidebar

st.set_page_config(
    page_title='To-Do — WR Binary',
    page_icon='📝',
    layout='wide',
)
inject_theme()
render_sidebar('To-Do')

TODO_PATH = os.path.join(_ROOT, 'TODO.md')

# ── Priority config ──────────────────────────────────────────────────────────
PRIORITY_ORDER = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
PRIORITY_COLORS = {
    'critical': '#E25A53',
    'high': '#F5A623',
    'medium': '#4A90D9',
    'low': '#8C8C8C',
}
PRIORITY_EMOJIS = {
    'critical': '🔴',
    'high': '🟠',
    'medium': '🔵',
    'low': '⚪',
}


# ── Parse / write TODO.md ────────────────────────────────────────────────────
def _parse_table_rows(lines: list[str]) -> list[dict]:
    """Parse markdown table rows (skip header + separator)."""
    rows = []
    for line in lines:
        line = line.strip()
        if not line.startswith('|') or line.startswith('|--') or line.startswith('| --'):
            continue
        cells = [c.strip() for c in line.split('|')[1:-1]]
        if cells and all(c == '' or set(c) <= {'-', ' '} for c in cells):
            continue  # separator row
        rows.append(cells)
    return rows


def load_todos() -> tuple[list[dict], list[dict]]:
    """Load TODO.md → (open_tasks, done_tasks)."""
    if not os.path.exists(TODO_PATH):
        return [], []

    with open(TODO_PATH, 'r', encoding='utf-8') as f:
        content = f.read()

    open_tasks = []
    done_tasks = []

    # Split by sections
    sections = re.split(r'^## ', content, flags=re.MULTILINE)
    for section in sections:
        if section.startswith('Open Tasks'):
            lines = section.split('\n')
            rows = _parse_table_rows(lines)
            # Skip header row
            for cells in rows[1:] if len(rows) > 1 else []:
                if len(cells) >= 9:
                    open_tasks.append({
                        'id': int(cells[0]) if cells[0].isdigit() else 0,
                        'title': cells[1],
                        'description': cells[2],
                        'priority': cells[3].lower().strip(),
                        'tags': cells[4],
                        'status': cells[5].lower().strip(),
                        'added_by': cells[6],
                        'suggested_by': cells[7],
                        'date_added': cells[8],
                    })
        elif section.startswith('Done'):
            lines = section.split('\n')
            rows = _parse_table_rows(lines)
            for cells in rows[1:] if len(rows) > 1 else []:
                if len(cells) >= 3:
                    done_tasks.append({
                        'id': int(cells[0]) if cells[0].isdigit() else 0,
                        'title': cells[1],
                        'date_done': cells[2],
                    })

    return open_tasks, done_tasks


def save_todos(open_tasks: list[dict], done_tasks: list[dict]) -> None:
    """Write open_tasks + done_tasks back to TODO.md."""
    # Sort open by priority
    open_tasks.sort(key=lambda t: PRIORITY_ORDER.get(t.get('priority', 'low'), 3))

    lines = ['# Project To-Do List\n']
    lines.append('\n## Open Tasks\n')
    lines.append('| ID | Title | Description | Priority | Tags | Status | Added by | Suggested by | Date added |')
    lines.append('|----|-------|-------------|----------|------|--------|----------|-------------|------------|')
    for t in open_tasks:
        lines.append(
            f"| {t['id']} | {t['title']} | {t.get('description', '')} "
            f"| {t.get('priority', 'medium')} | {t.get('tags', '')} "
            f"| {t.get('status', 'open')} | {t.get('added_by', '')} "
            f"| {t.get('suggested_by', '')} | {t.get('date_added', '')} |"
        )

    lines.append('\n## Done\n')
    lines.append('| ID | Title | Date done |')
    lines.append('|----|-------|-----------|')
    for t in done_tasks:
        lines.append(f"| {t['id']} | {t['title']} | {t.get('date_done', '')} |")

    lines.append('')
    with open(TODO_PATH, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))


def _next_id(open_tasks: list[dict], done_tasks: list[dict]) -> int:
    """Get next available ID."""
    all_ids = [t['id'] for t in open_tasks] + [t['id'] for t in done_tasks]
    return max(all_ids, default=0) + 1


# ── Page content ─────────────────────────────────────────────────────────────
st.markdown('# 📝 To-Do List')

open_tasks, done_tasks = load_todos()

# ── Sidebar summary ─────────────────────────────────────────────────────────
n_open = len(open_tasks)
n_critical = sum(1 for t in open_tasks if t.get('priority') == 'critical')
n_high = sum(1 for t in open_tasks if t.get('priority') == 'high')

# ── Add new task ─────────────────────────────────────────────────────────────
with st.expander('➕ Add new task', expanded=False):
    _cols = st.columns([3, 1, 1])
    new_title = _cols[0].text_input('Title', key='todo_new_title',
                                     placeholder='Short task name')
    new_priority = _cols[1].selectbox('Priority', ['high', 'critical', 'medium', 'low'],
                                      key='todo_new_priority')
    new_added_by = _cols[2].selectbox('Added by', ['Guy', 'Claude', 'Tomer'],
                                      key='todo_new_added_by')

    _cols2 = st.columns([3, 1, 1])
    new_desc = _cols2[0].text_input('Description', key='todo_new_desc',
                                     placeholder='One sentence — what needs to be done')
    new_tags = _cols2[1].text_input('Tags', key='todo_new_tags',
                                    placeholder='e.g. bias-correction, webapp')
    new_suggested = _cols2[2].selectbox('Suggested by', ['Guy', 'Tomer', 'Claude'],
                                        key='todo_new_suggested')

    if st.button('Add task', key='todo_add_btn', type='primary'):
        if new_title.strip():
            new_task = {
                'id': _next_id(open_tasks, done_tasks),
                'title': new_title.strip(),
                'description': new_desc.strip(),
                'priority': new_priority,
                'tags': new_tags.strip(),
                'status': 'open',
                'added_by': new_added_by,
                'suggested_by': new_suggested,
                'date_added': date.today().isoformat(),
            }
            open_tasks.append(new_task)
            save_todos(open_tasks, done_tasks)
            st.success(f'Added: {new_title.strip()}')
            st.rerun()
        else:
            st.warning('Enter a title first.')

# ── Filters ──────────────────────────────────────────────────────────────────
if open_tasks:
    _filter_cols = st.columns([1, 1, 1, 2])
    all_priorities = sorted(set(t.get('priority', 'medium') for t in open_tasks),
                            key=lambda p: PRIORITY_ORDER.get(p, 3))
    all_tags = sorted(set(
        tag.strip()
        for t in open_tasks
        for tag in t.get('tags', '').split(',')
        if tag.strip()
    ))
    all_authors = sorted(set(t.get('added_by', '') for t in open_tasks if t.get('added_by')))

    filter_priority = _filter_cols[0].multiselect('Filter priority', all_priorities,
                                                   default=all_priorities, key='todo_filter_pri')
    filter_tags = _filter_cols[1].multiselect('Filter tags', all_tags,
                                              default=all_tags, key='todo_filter_tags')
    filter_author = _filter_cols[2].multiselect('Filter author', all_authors,
                                                default=all_authors, key='todo_filter_author')
    sort_by = _filter_cols[3].selectbox('Sort by', ['Priority', 'Date added', 'ID'],
                                        key='todo_sort_by')

    # Apply filters
    filtered = [
        t for t in open_tasks
        if t.get('priority', 'medium') in filter_priority
        and t.get('added_by', '') in filter_author
        and (not all_tags or any(
            tag.strip() in filter_tags
            for tag in t.get('tags', '').split(',')
            if tag.strip()
        ) or not t.get('tags', '').strip())
    ]

    # Apply sort
    if sort_by == 'Priority':
        filtered.sort(key=lambda t: PRIORITY_ORDER.get(t.get('priority', 'low'), 3))
    elif sort_by == 'Date added':
        filtered.sort(key=lambda t: t.get('date_added', ''), reverse=True)
    else:
        filtered.sort(key=lambda t: t.get('id', 0))
else:
    filtered = []

# ── Open tasks display ───────────────────────────────────────────────────────
st.markdown(f'### Open Tasks ({len(filtered)})')

if not filtered:
    st.info('No open tasks. Use the form above to add one.')

_tasks_to_complete = []

for task in filtered:
    pri = task.get('priority', 'medium')
    pri_color = PRIORITY_COLORS.get(pri, '#8C8C8C')
    pri_emoji = PRIORITY_EMOJIS.get(pri, '⚪')
    tags_str = task.get('tags', '')
    desc = task.get('description', '')

    col_check, col_pri, col_title, col_tags, col_by, col_date = st.columns(
        [0.3, 0.5, 3, 1.5, 1, 1])

    with col_check:
        if st.checkbox('', key=f'todo_done_{task["id"]}', label_visibility='collapsed'):
            _tasks_to_complete.append(task)
    with col_pri:
        st.markdown(
            f'<span style="color:{pri_color};font-weight:600">{pri_emoji} {pri}</span>',
            unsafe_allow_html=True)
    with col_title:
        title_md = f'**{task["title"]}**'
        if desc:
            title_md += f'  \n<span style="color:#888;font-size:0.85em">{desc}</span>'
        st.markdown(title_md, unsafe_allow_html=True)
    with col_tags:
        if tags_str:
            badges = ''.join(
                f'<span style="background:#1a4a80;color:#9ec5fe;padding:2px 8px;'
                f'border-radius:10px;font-size:0.75em;margin-right:4px">{t.strip()}</span>'
                for t in tags_str.split(',') if t.strip()
            )
            st.markdown(badges, unsafe_allow_html=True)
    with col_by:
        st.caption(f'{task.get("suggested_by", "")}')
    with col_date:
        st.caption(task.get('date_added', ''))

# Handle completions
if _tasks_to_complete:
    for task in _tasks_to_complete:
        open_tasks = [t for t in open_tasks if t['id'] != task['id']]
        done_tasks.insert(0, {
            'id': task['id'],
            'title': task['title'],
            'date_done': date.today().isoformat(),
        })
    save_todos(open_tasks, done_tasks)
    st.rerun()

# ── Done tasks ───────────────────────────────────────────────────────────────
if done_tasks:
    with st.expander(f'Completed ({len(done_tasks)})', expanded=False):
        for task in done_tasks:
            st.markdown(
                f'<span style="color:#666;text-decoration:line-through">'
                f'#{task["id"]} — {task["title"]}</span>'
                f'&nbsp;&nbsp;<span style="color:#555;font-size:0.8em">'
                f'{task.get("date_done", "")}</span>',
                unsafe_allow_html=True,
            )

st.caption(
    f'{n_open} open tasks ({n_critical} critical, {n_high} high). '
    f'Check the box to mark a task as done.'
)
