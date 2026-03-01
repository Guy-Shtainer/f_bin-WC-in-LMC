"""
pages/10_todo.py — Project To-Do List

Interactive task manager that reads/writes TODO.md at the project root.
Features: Eisenhower matrix, inline editing, priority/tag filtering,
urgent/important fields, checkbox completion.
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

# Eisenhower quadrant colors
_Q_COLORS = {
    'urgent_important':     ('#E25A53', 'Do First'),
    'not_urgent_important': ('#4A90D9', 'Schedule'),
    'urgent_not_important': ('#F5A623', 'Delegate'),
    'not_urgent_not_important': ('#8C8C8C', 'Eliminate'),
}


# ── Parse / write TODO.md ────────────────────────────────────────────────────
def _parse_bool(val: str) -> bool:
    return val.strip().lower() in ('y', 'yes', 'true', '1')


def _bool_str(val: bool) -> str:
    return 'Y' if val else 'N'


def _derive_priority(urgent: bool, important: bool) -> str:
    """Map Eisenhower quadrant to priority level."""
    if urgent and important:
        return 'critical'
    if important:
        return 'high'
    if urgent:
        return 'medium'
    return 'low'


def _parse_table_rows(lines: list[str]) -> list[list[str]]:
    """Parse markdown table rows (skip header + separator)."""
    rows = []
    for line in lines:
        line = line.strip()
        if not line.startswith('|') or line.startswith('|--') or line.startswith('| --'):
            continue
        cells = [c.strip() for c in line.split('|')[1:-1]]
        if cells and all(c == '' or set(c) <= {'-', ' '} for c in cells):
            continue
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

    sections = re.split(r'^## ', content, flags=re.MULTILINE)
    for section in sections:
        if section.startswith('Open Tasks'):
            lines = section.split('\n')
            rows = _parse_table_rows(lines)
            for cells in rows[1:] if len(rows) > 1 else []:
                if len(cells) >= 9:
                    task = {
                        'id': int(cells[0]) if cells[0].isdigit() else 0,
                        'title': cells[1],
                        'description': cells[2],
                        'priority': cells[3].lower().strip(),
                        'tags': cells[4],
                        'status': cells[5].lower().strip(),
                        'added_by': cells[6],
                        'suggested_by': cells[7],
                        'date_added': cells[8],
                        'urgent': _parse_bool(cells[9]) if len(cells) > 9 else False,
                        'important': _parse_bool(cells[10]) if len(cells) > 10 else False,
                    }
                    open_tasks.append(task)
        elif section.startswith('Done'):
            lines = section.split('\n')
            rows = _parse_table_rows(lines)
            for cells in rows[1:] if len(rows) > 1 else []:
                if len(cells) >= 12:
                    # Full metadata format (12 columns)
                    done_tasks.append({
                        'id': int(cells[0]) if cells[0].isdigit() else 0,
                        'title': cells[1],
                        'description': cells[2],
                        'priority': cells[3].lower().strip(),
                        'tags': cells[4],
                        'added_by': cells[6],
                        'suggested_by': cells[7],
                        'date_added': cells[8],
                        'urgent': _parse_bool(cells[9]),
                        'important': _parse_bool(cells[10]),
                        'date_done': cells[11],
                    })
                elif len(cells) >= 3:
                    # Legacy 3-column format (backwards compatible)
                    done_tasks.append({
                        'id': int(cells[0]) if cells[0].isdigit() else 0,
                        'title': cells[1],
                        'date_done': cells[2],
                    })

    return open_tasks, done_tasks


def save_todos(open_tasks: list[dict], done_tasks: list[dict]) -> None:
    """Write open_tasks + done_tasks back to TODO.md."""
    open_tasks.sort(key=lambda t: PRIORITY_ORDER.get(t.get('priority', 'low'), 3))

    lines = ['# Project To-Do List\n']
    lines.append('\n## Open Tasks\n')
    lines.append(
        '| ID | Title | Description | Priority | Tags | Status '
        '| Added by | Suggested by | Date added | Urgent | Important |'
    )
    lines.append(
        '|----|-------|-------------|----------|------|--------'
        '|----------|-------------|------------|--------|-----------|'
    )
    for t in open_tasks:
        lines.append(
            f"| {t['id']} | {t['title']} | {t.get('description', '')} "
            f"| {t.get('priority', 'medium')} | {t.get('tags', '')} "
            f"| {t.get('status', 'open')} | {t.get('added_by', '')} "
            f"| {t.get('suggested_by', '')} | {t.get('date_added', '')} "
            f"| {_bool_str(t.get('urgent', False))} "
            f"| {_bool_str(t.get('important', False))} |"
        )

    lines.append('\n## Done\n')
    lines.append(
        '| ID | Title | Description | Priority | Tags | Status '
        '| Added by | Suggested by | Date added | Urgent | Important | Date done |'
    )
    lines.append(
        '|----|-------|-------------|----------|------|--------'
        '|----------|-------------|------------|--------|-----------|-----------|'
    )
    for t in done_tasks:
        lines.append(
            f"| {t['id']} | {t['title']} | {t.get('description', '')} "
            f"| {t.get('priority', 'medium')} | {t.get('tags', '')} "
            f"| done | {t.get('added_by', '')} "
            f"| {t.get('suggested_by', '')} | {t.get('date_added', '')} "
            f"| {_bool_str(t.get('urgent', False))} "
            f"| {_bool_str(t.get('important', False))} "
            f"| {t.get('date_done', '')} |"
        )

    lines.append('')
    with open(TODO_PATH, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))


def _next_id(open_tasks: list[dict], done_tasks: list[dict]) -> int:
    all_ids = [t['id'] for t in open_tasks] + [t['id'] for t in done_tasks]
    return max(all_ids, default=0) + 1


# ── Page content ─────────────────────────────────────────────────────────────
st.markdown('# 📝 To-Do List')

open_tasks, done_tasks = load_todos()

n_open = len(open_tasks)
n_critical = sum(1 for t in open_tasks if t.get('priority') == 'critical')
n_high = sum(1 for t in open_tasks if t.get('priority') == 'high')

# ── Eisenhower Matrix ────────────────────────────────────────────────────────
if open_tasks:
    with st.expander('📊 Eisenhower Matrix', expanded=True):
        q_ui = [t for t in open_tasks if t.get('urgent') and t.get('important')]
        q_ni = [t for t in open_tasks if not t.get('urgent') and t.get('important')]
        q_un = [t for t in open_tasks if t.get('urgent') and not t.get('important')]
        q_nn = [t for t in open_tasks if not t.get('urgent') and not t.get('important')]

        def _render_quadrant(title, color, label, tasks_q):
            parts = [
                f'<div style="background:{color}22;border:1px solid {color};'
                f'border-radius:8px;padding:10px;min-height:100px">',
                f'<b style="color:{color}">{title}</b> '
                f'<span style="color:#888;font-size:0.8em">({label})</span><br>',
            ]
            if tasks_q:
                for tq in tasks_q:
                    pri_e = PRIORITY_EMOJIS.get(tq.get('priority', 'medium'), '⚪')
                    parts.append(
                        f'<span style="font-size:0.85em">{pri_e} {tq["title"]}'
                        f'</span><br>'
                    )
            else:
                parts.append(
                    '<span style="color:#666;font-size:0.8em;font-style:italic">'
                    'No tasks</span>'
                )
            parts.append('</div>')
            st.markdown(''.join(parts), unsafe_allow_html=True)

        # Header row
        _h1, _h2 = st.columns(2)
        _h1.markdown(
            '<div style="text-align:center;font-weight:600;color:#9ec5fe">'
            'Important</div>', unsafe_allow_html=True)
        _h2.markdown(
            '<div style="text-align:center;font-weight:600;color:#888">'
            'Not Important</div>', unsafe_allow_html=True)

        # Row 1: Urgent
        c1, c2 = st.columns(2)
        with c1:
            _render_quadrant('Urgent + Important', '#E25A53', 'Do First', q_ui)
        with c2:
            _render_quadrant('Urgent + Not Important', '#F5A623', 'Delegate', q_un)

        # Row 2: Not Urgent
        c3, c4 = st.columns(2)
        with c3:
            _render_quadrant('Not Urgent + Important', '#4A90D9', 'Schedule', q_ni)
        with c4:
            _render_quadrant('Not Urgent + Not Important', '#8C8C8C', 'Eliminate', q_nn)

        st.caption(
            f'**{len(q_ui)}** do first, '
            f'**{len(q_ni)}** schedule, '
            f'**{len(q_un)}** delegate, '
            f'**{len(q_nn)}** eliminate'
        )

# ── Add new task ─────────────────────────────────────────────────────────────
with st.expander('➕ Add new task', expanded=False):
    _cols = st.columns([3, 1])
    new_title = _cols[0].text_area('Title', key='todo_new_title',
                                    placeholder='Short task name', height=68)
    new_added_by = _cols[1].selectbox('Added by', ['Guy', 'Claude', 'Tomer'],
                                      key='todo_new_added_by')

    _cols2 = st.columns([3, 1, 1])
    new_desc = _cols2[0].text_area('Description', key='todo_new_desc',
                                    placeholder='What needs to be done', height=68)
    new_tags = _cols2[1].text_input('Tags', key='todo_new_tags',
                                    placeholder='e.g. bias-correction')
    new_suggested = _cols2[2].selectbox('Suggested by',
                                        ['Guy', 'Tomer', 'Claude'],
                                        key='todo_new_suggested')

    _cols3 = st.columns([1, 1, 2])
    new_urgent = _cols3[0].checkbox('Urgent', key='todo_new_urgent')
    new_important = _cols3[1].checkbox('Important', key='todo_new_important')

    if _cols3[2].button('Add task', key='todo_add_btn', type='primary'):
        title_clean = new_title.strip().replace('\n', ' ')
        if title_clean:
            new_task = {
                'id': _next_id(open_tasks, done_tasks),
                'title': title_clean,
                'description': new_desc.strip().replace('\n', ' '),
                'priority': _derive_priority(new_urgent, new_important),
                'tags': new_tags.strip(),
                'status': 'open',
                'added_by': new_added_by,
                'suggested_by': new_suggested,
                'date_added': date.today().isoformat(),
                'urgent': new_urgent,
                'important': new_important,
            }
            open_tasks.append(new_task)
            save_todos(open_tasks, done_tasks)
            st.success(f'Added: {title_clean}')
            st.rerun()
        else:
            st.warning('Enter a title first.')

# ── Filters ──────────────────────────────────────────────────────────────────
if open_tasks:
    _filter_cols = st.columns([1, 1, 1, 1, 1])
    all_priorities = sorted(
        set(t.get('priority', 'medium') for t in open_tasks),
        key=lambda p: PRIORITY_ORDER.get(p, 3),
    )
    all_tags = sorted(set(
        tag.strip()
        for t in open_tasks
        for tag in t.get('tags', '').split(',')
        if tag.strip()
    ))
    all_authors = sorted(
        set(t.get('added_by', '') for t in open_tasks if t.get('added_by'))
    )

    filter_priority = _filter_cols[0].multiselect(
        'Priority', all_priorities, default=all_priorities, key='todo_filter_pri')
    filter_tags = _filter_cols[1].multiselect(
        'Tags', all_tags, default=all_tags, key='todo_filter_tags')
    filter_author = _filter_cols[2].multiselect(
        'Author', all_authors, default=all_authors, key='todo_filter_author')
    sort_by = _filter_cols[3].selectbox(
        'Sort by', ['Priority', 'Date added', 'ID', 'Urgent first'],
        key='todo_sort_by')
    filter_quadrant = _filter_cols[4].selectbox(
        'Quadrant', ['All', 'Urgent + Important', 'Important',
                      'Urgent', 'Neither'],
        key='todo_filter_quadrant')

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

    # Quadrant filter
    if filter_quadrant == 'Urgent + Important':
        filtered = [t for t in filtered if t.get('urgent') and t.get('important')]
    elif filter_quadrant == 'Important':
        filtered = [t for t in filtered if t.get('important')]
    elif filter_quadrant == 'Urgent':
        filtered = [t for t in filtered if t.get('urgent')]
    elif filter_quadrant == 'Neither':
        filtered = [t for t in filtered
                     if not t.get('urgent') and not t.get('important')]

    # Apply sort
    if sort_by == 'Priority':
        filtered.sort(key=lambda t: PRIORITY_ORDER.get(t.get('priority', 'low'), 3))
    elif sort_by == 'Date added':
        filtered.sort(key=lambda t: t.get('date_added', ''), reverse=True)
    elif sort_by == 'Urgent first':
        filtered.sort(key=lambda t: (
            0 if t.get('urgent') and t.get('important') else
            1 if t.get('urgent') else
            2 if t.get('important') else 3
        ))
    else:
        filtered.sort(key=lambda t: t.get('id', 0))
else:
    filtered = []

# ── Open tasks display ───────────────────────────────────────────────────────
st.markdown(f'### Open Tasks ({len(filtered)})')

if not filtered:
    st.info('No open tasks. Use the form above to add one.')

_tasks_to_complete = []
_tasks_modified = False

for task in filtered:
    pri = task.get('priority', 'medium')
    pri_color = PRIORITY_COLORS.get(pri, '#8C8C8C')
    pri_emoji = PRIORITY_EMOJIS.get(pri, '⚪')
    tags_str = task.get('tags', '')
    desc = task.get('description', '')
    is_urgent = task.get('urgent', False)
    is_important = task.get('important', False)

    # Urgency/importance indicators
    _task_status = task.get('status', 'open')
    flags = ''
    if _task_status == 'to-test':
        flags = '<span style="color:#2ECC71;font-size:0.75em;font-weight:600">🧪 TO TEST</span>'
    elif is_urgent and is_important:
        flags = '<span style="color:#E25A53;font-size:0.75em">🔥 DO FIRST</span>'
    elif is_urgent:
        flags = '<span style="color:#F5A623;font-size:0.75em">⚡ URGENT</span>'
    elif is_important:
        flags = '<span style="color:#4A90D9;font-size:0.75em">📌 IMPORTANT</span>'

    _edit_width = 0.7 if _task_status == 'to-test' else 0.4
    col_check, col_pri, col_title, col_flags, col_tags, col_by, col_edit = st.columns(
        [0.3, 0.5, 3, 1, 1.5, 0.8, _edit_width])

    with col_check:
        if st.checkbox('', key=f'todo_done_{task["id"]}',
                        label_visibility='collapsed'):
            _tasks_to_complete.append(task)
    with col_pri:
        st.markdown(
            f'<span style="color:{pri_color};font-weight:600">'
            f'{pri_emoji} {pri}</span>',
            unsafe_allow_html=True)
    with col_title:
        title_md = f'**{task["title"]}**'
        if desc:
            title_md += (f'  \n<span style="color:#888;font-size:0.85em">'
                         f'{desc}</span>')
        st.markdown(title_md, unsafe_allow_html=True)
    with col_flags:
        if flags:
            st.markdown(flags, unsafe_allow_html=True)
    with col_tags:
        if tags_str:
            badges = ''.join(
                f'<span style="background:#1a4a80;color:#9ec5fe;padding:2px 8px;'
                f'border-radius:10px;font-size:0.75em;margin-right:4px">'
                f'{t.strip()}</span>'
                for t in tags_str.split(',') if t.strip()
            )
            st.markdown(badges, unsafe_allow_html=True)
    with col_by:
        st.caption(task.get('suggested_by', ''))
    with col_edit:
        _edit_key = f'todo_editing_{task["id"]}'
        if _task_status == 'to-test':
            _bc1, _bc2 = st.columns(2)
            if _bc1.button('✅', key=f'confirm_btn_{task["id"]}',
                           help=f'Confirm #{task["id"]} works'):
                _tasks_to_complete.append(task)
            if _bc2.button('✏️', key=f'edit_btn2_{task["id"]}',
                           help=f'Edit task #{task["id"]}'):
                st.session_state[_edit_key] = not st.session_state.get(
                    _edit_key, False)
                st.rerun()
        else:
            if st.button('✏️', key=f'edit_btn_{task["id"]}',
                         help=f'Edit task #{task["id"]}'):
                st.session_state[_edit_key] = not st.session_state.get(
                    _edit_key, False)
                st.rerun()

    # ── Inline edit form (toggled by pencil button) ──────────────────────
    if st.session_state.get(f'todo_editing_{task["id"]}', False):
        _ec1, _ec2 = st.columns([3, 1])
        edit_title = _ec1.text_area(
            'Title', value=task['title'],
            key=f'edit_title_{task["id"]}', height=68)
        _status_opts = ['open', 'in-progress', 'to-test']
        _cur_status = task.get('status', 'open')
        edit_status = _ec2.selectbox(
            'Status', _status_opts,
            index=_status_opts.index(_cur_status)
            if _cur_status in _status_opts else 0,
            key=f'edit_status_{task["id"]}')

        _ec4, _ec5, _ec6 = st.columns([3, 1, 1])
        edit_desc = _ec4.text_area(
            'Description', value=desc,
            key=f'edit_desc_{task["id"]}', height=68)
        edit_added = _ec5.selectbox(
            'Added by', ['Guy', 'Claude', 'Tomer'],
            index=['Guy', 'Claude', 'Tomer'].index(
                task.get('added_by', 'Guy'))
            if task.get('added_by', 'Guy') in ['Guy', 'Claude', 'Tomer'] else 0,
            key=f'edit_added_{task["id"]}')
        edit_suggested = _ec6.selectbox(
            'Suggested by', ['Guy', 'Tomer', 'Claude'],
            index=['Guy', 'Tomer', 'Claude'].index(
                task.get('suggested_by', 'Guy'))
            if task.get('suggested_by', 'Guy') in ['Guy', 'Tomer', 'Claude'] else 0,
            key=f'edit_suggested_{task["id"]}')

        _ec7, _ec8, _ec9, _ec10, _ec11 = st.columns([2, 1, 1, 0.7, 0.7])
        edit_tags = _ec7.text_input(
            'Tags', value=tags_str,
            key=f'edit_tags_{task["id"]}')
        edit_urgent = _ec8.checkbox(
            'Urgent', value=is_urgent,
            key=f'edit_urgent_{task["id"]}')
        edit_important = _ec9.checkbox(
            'Important', value=is_important,
            key=f'edit_important_{task["id"]}')

        if _ec10.button('Save', key=f'edit_save_{task["id"]}',
                         type='primary'):
            task['title'] = edit_title.strip().replace('\n', ' ')
            task['description'] = edit_desc.strip().replace('\n', ' ')
            task['priority'] = _derive_priority(edit_urgent, edit_important)
            task['status'] = edit_status
            task['tags'] = edit_tags.strip()
            task['added_by'] = edit_added
            task['suggested_by'] = edit_suggested
            task['urgent'] = edit_urgent
            task['important'] = edit_important
            save_todos(open_tasks, done_tasks)
            st.session_state[f'todo_editing_{task["id"]}'] = False
            st.success(f'Updated #{task["id"]}')
            st.rerun()

        if _ec11.button('Cancel', key=f'edit_cancel_{task["id"]}'):
            st.session_state[f'todo_editing_{task["id"]}'] = False
            st.rerun()

# Handle completions
if _tasks_to_complete:
    for task in _tasks_to_complete:
        open_tasks = [t for t in open_tasks if t['id'] != task['id']]
        done_entry = dict(task)
        done_entry['date_done'] = date.today().isoformat()
        done_entry['status'] = 'done'
        done_tasks.insert(0, done_entry)
    save_todos(open_tasks, done_tasks)
    st.rerun()

# ── Done tasks ───────────────────────────────────────────────────────────────
if done_tasks:
    with st.expander(f'Completed ({len(done_tasks)})', expanded=False):
        _tasks_to_restore = []
        for task in done_tasks:
            _dc1, _dc2 = st.columns([6, 0.5])
            with _dc1:
                st.markdown(
                    f'<span style="color:#666;text-decoration:line-through">'
                    f'#{task["id"]} — {task["title"]}</span>'
                    f'&nbsp;&nbsp;<span style="color:#555;font-size:0.8em">'
                    f'{task.get("date_done", "")}</span>',
                    unsafe_allow_html=True,
                )
            with _dc2:
                if st.button('↩️', key=f'restore_btn_{task["id"]}',
                             help=f'Restore #{task["id"]} to open'):
                    _tasks_to_restore.append(task)
        if _tasks_to_restore:
            for task in _tasks_to_restore:
                done_tasks = [t for t in done_tasks if t['id'] != task['id']]
                restored = dict(task)
                restored.pop('date_done', None)
                restored['status'] = 'open'
                open_tasks.append(restored)
            save_todos(open_tasks, done_tasks)
            st.rerun()

st.caption(
    f'{n_open} open tasks ({n_critical} critical, {n_high} high). '
    f'Check the box to mark as done. Click the pencil to edit, '
    f'or the checkmark to confirm tested features.'
)
