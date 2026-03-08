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
from datetime import date, datetime

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


def load_todos() -> tuple[list[dict], list[dict], list[dict]]:
    """Load TODO.md → (open_tasks, done_tasks, deleted_tasks)."""
    if not os.path.exists(TODO_PATH):
        return [], [], []

    with open(TODO_PATH, 'r', encoding='utf-8') as f:
        content = f.read()

    open_tasks = []
    done_tasks = []
    deleted_tasks = []

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
                        'notes': cells[11] if len(cells) > 11 else '',
                    }
                    open_tasks.append(task)
        elif section.startswith('Done'):
            lines = section.split('\n')
            rows = _parse_table_rows(lines)
            for cells in rows[1:] if len(rows) > 1 else []:
                if len(cells) >= 12:
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
                        'notes': cells[12] if len(cells) > 12 else '',
                    })
                elif len(cells) >= 3:
                    done_tasks.append({
                        'id': int(cells[0]) if cells[0].isdigit() else 0,
                        'title': cells[1],
                        'date_done': cells[2],
                    })
        elif section.startswith('Deleted'):
            lines = section.split('\n')
            rows = _parse_table_rows(lines)
            for cells in rows[1:] if len(rows) > 1 else []:
                if len(cells) >= 4:
                    deleted_tasks.append({
                        'id': int(cells[0]) if cells[0].isdigit() else 0,
                        'title': cells[1],
                        'date_deleted': cells[2],
                        'notes': cells[3] if len(cells) > 3 else '',
                    })

    return open_tasks, done_tasks, deleted_tasks


def save_todos(open_tasks: list[dict], done_tasks: list[dict],
               deleted_tasks: list[dict] | None = None) -> None:
    """Write open_tasks + done_tasks + deleted_tasks back to TODO.md."""
    if deleted_tasks is None:
        deleted_tasks = []

    lines = ['# Project To-Do List\n']
    lines.append('\n## Open Tasks\n')
    lines.append(
        '| ID | Title | Description | Priority | Tags | Status '
        '| Added by | Suggested by | Date added | Urgent | Important | Notes |'
    )
    lines.append(
        '|----|-------|-------------|----------|------|--------'
        '|----------|-------------|------------|--------|-----------|-------|'
    )
    for t in open_tasks:
        lines.append(
            f"| {t['id']} | {t['title']} | {t.get('description', '')} "
            f"| {t.get('priority', 'medium')} | {t.get('tags', '')} "
            f"| {t.get('status', 'open')} | {t.get('added_by', '')} "
            f"| {t.get('suggested_by', '')} | {t.get('date_added', '')} "
            f"| {_bool_str(t.get('urgent', False))} "
            f"| {_bool_str(t.get('important', False))} "
            f"| {t.get('notes', '')} |"
        )

    lines.append('\n## Done\n')
    lines.append(
        '| ID | Title | Description | Priority | Tags | Status '
        '| Added by | Suggested by | Date added | Urgent | Important '
        '| Date done | Notes |'
    )
    lines.append(
        '|----|-------|-------------|----------|------|--------'
        '|----------|-------------|------------|--------|-----------|'
        '-----------|-------|'
    )
    for t in done_tasks:
        lines.append(
            f"| {t['id']} | {t['title']} | {t.get('description', '')} "
            f"| {t.get('priority', 'medium')} | {t.get('tags', '')} "
            f"| done | {t.get('added_by', '')} "
            f"| {t.get('suggested_by', '')} | {t.get('date_added', '')} "
            f"| {_bool_str(t.get('urgent', False))} "
            f"| {_bool_str(t.get('important', False))} "
            f"| {t.get('date_done', '')} "
            f"| {t.get('notes', '')} |"
        )

    if deleted_tasks:
        lines.append('\n## Deleted\n')
        lines.append('| ID | Title | Date deleted | Notes |')
        lines.append('|----|-------|-------------|-------|')
        for t in deleted_tasks:
            lines.append(
                f"| {t['id']} | {t['title']} "
                f"| {t.get('date_deleted', '')} "
                f"| {t.get('notes', '')} |"
            )

    lines.append('')
    with open(TODO_PATH, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))


def _all_tags_by_frequency(open_tasks: list[dict], done_tasks: list[dict]) -> list[str]:
    """Return all unique tags sorted by frequency (most common first)."""
    from collections import Counter
    counter: Counter = Counter()
    for t in open_tasks + done_tasks:
        for tag in t.get('tags', '').split(','):
            tag = tag.strip()
            if tag:
                counter[tag] += 1
    return [tag for tag, _ in counter.most_common()]


def _next_id(open_tasks: list[dict], done_tasks: list[dict],
             deleted_tasks: list[dict] | None = None) -> int:
    all_ids = ([t['id'] for t in open_tasks] + [t['id'] for t in done_tasks]
               + [t['id'] for t in (deleted_tasks or [])])
    return max(all_ids, default=0) + 1


# ── Page content ─────────────────────────────────────────────────────────────
st.markdown('# 📝 To-Do List')

open_tasks, done_tasks, deleted_tasks = load_todos()

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
            st.markdown(
                f'<div style="background:{color}22;border:1px solid {color};'
                f'border-radius:8px;padding:10px;min-height:60px">'
                f'<b style="color:{color}">{title}</b> '
                f'<span style="color:#888;font-size:0.8em">({label})</span>'
                f'</div>',
                unsafe_allow_html=True)
            if tasks_q:
                for tq in tasks_q:
                    pri_e = PRIORITY_EMOJIS.get(tq.get('priority', 'medium'), '⚪')
                    if st.button(f'{pri_e} {tq["title"]}',
                                 key=f'eis_btn_{tq["id"]}',
                                 help=f'Jump to edit #{tq["id"]}',
                                 use_container_width=True):
                        st.session_state[f'todo_editing_{tq["id"]}'] = True
                        st.rerun()
            else:
                st.caption('No tasks')

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
# Form version counter — incrementing creates fresh widget keys to clear fields
_fv = st.session_state.get('todo_form_ver', 0)

with st.expander('➕ Add new task', expanded=False):
    _cols = st.columns([3, 1])
    new_title = _cols[0].text_area('Title', key=f'todo_new_title_v{_fv}',
                                    placeholder='Short task name', height=68)
    new_added_by = _cols[1].selectbox('Added by', ['Guy', 'Claude', 'Tomer'],
                                      key=f'todo_new_added_by_v{_fv}')

    _existing_tags = _all_tags_by_frequency(open_tasks, done_tasks)
    _cols2 = st.columns([3, 2, 1])
    new_desc = _cols2[0].text_area('Description', key=f'todo_new_desc_v{_fv}',
                                    placeholder='What needs to be done', height=68)
    _selected_tags = _cols2[1].multiselect(
        'Tags', _existing_tags, key=f'todo_new_tags_multi_v{_fv}',
        placeholder='Select existing tags...')
    _extra_tags = _cols2[1].text_input(
        'New tags', key=f'todo_new_tags_v{_fv}',
        placeholder='Add new tags (comma-separated)')
    # Merge selected + extra
    _all_new_tags = list(_selected_tags)
    for _t in _extra_tags.split(','):
        _t = _t.strip()
        if _t and _t not in _all_new_tags:
            _all_new_tags.append(_t)
    new_tags = ', '.join(_all_new_tags)
    new_suggested = _cols2[2].selectbox('Suggested by',
                                        ['Guy', 'Tomer', 'Claude'],
                                        key=f'todo_new_suggested_v{_fv}')

    _cols3 = st.columns([1, 1, 2])
    new_urgent = _cols3[0].checkbox('Urgent', key=f'todo_new_urgent_v{_fv}')
    new_important = _cols3[1].checkbox('Important', key=f'todo_new_important_v{_fv}')

    if _cols3[2].button('Add task', key='todo_add_btn', type='primary'):
        title_clean = new_title.strip().replace('\n', ' ')
        if title_clean:
            new_task = {
                'id': _next_id(open_tasks, done_tasks, deleted_tasks),
                'title': title_clean,
                'description': new_desc.strip().replace('\n', ' '),
                'priority': _derive_priority(new_urgent, new_important),
                'tags': new_tags.strip(),
                'status': 'open',
                'added_by': new_added_by,
                'suggested_by': new_suggested,
                'date_added': datetime.now().isoformat(timespec='seconds'),
                'urgent': new_urgent,
                'important': new_important,
            }
            open_tasks.append(new_task)
            save_todos(open_tasks, done_tasks, deleted_tasks)
            st.success(f'Added: {title_clean}')
            # Increment form version to get fresh empty widgets
            st.session_state['todo_form_ver'] = _fv + 1
            st.rerun()
        else:
            st.warning('Enter a title first.')

# ── Filters ──────────────────────────────────────────────────────────────────
if open_tasks:
    _filter_cols = st.columns([1, 1, 1, 1, 1, 1])
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
    filter_status = _filter_cols[3].selectbox(
        'Status', ['All', 'Open', 'To Test', 'In Progress'],
        key='todo_filter_status')
    sort_by = _filter_cols[4].selectbox(
        'Sort by', ['Priority', 'Date added', 'ID', 'Urgent first'],
        key='todo_sort_by')
    filter_quadrant = _filter_cols[5].selectbox(
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

    # Status filter
    if filter_status == 'Open':
        filtered = [t for t in filtered if t.get('status', 'open') == 'open']
    elif filter_status == 'To Test':
        filtered = [t for t in filtered if t.get('status', 'open') == 'to-test']
    elif filter_status == 'In Progress':
        filtered = [t for t in filtered
                     if t.get('status', 'open') == 'in-progress']

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
_tasks_to_delete = []
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

    _edit_width = 1.0 if _task_status == 'to-test' else 0.4
    (col_check, col_id, col_pri, col_title, col_flags,
     col_tags, col_date, col_by, col_del, col_edit) = st.columns(
        [0.3, 0.4, 0.5, 3, 1, 1.5, 1.0, 0.8, 0.3, _edit_width])

    with col_check:
        if st.checkbox('', key=f'todo_done_{task["id"]}',
                        label_visibility='collapsed'):
            _tasks_to_complete.append(task)
    with col_id:
        st.markdown(
            f'<span style="color:#888;font-size:0.85em;font-weight:600">'
            f'#{task["id"]}</span>',
            unsafe_allow_html=True)
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
    with col_date:
        _da = task.get('date_added', '')
        if _da:
            st.caption(_da[:10], help=_da)
    with col_by:
        st.caption(task.get('suggested_by', ''))
    with col_del:
        if st.button('🗑️', key=f'del_btn_{task["id"]}',
                     help=f'Delete #{task["id"]}'):
            _tasks_to_delete.append(task)
    with col_edit:
        _edit_key = f'todo_editing_{task["id"]}'
        if _task_status == 'to-test':
            _bc1, _bc2, _bc3 = st.columns(3)
            if _bc1.button('✅', key=f'confirm_btn_{task["id"]}',
                           help=f'Confirm #{task["id"]} works'):
                _tasks_to_complete.append(task)
            if _bc2.button('❌', key=f'decline_btn_{task["id"]}',
                           help=f'Decline #{task["id"]}'):
                st.session_state[f'todo_declining_{task["id"]}'] = True
                st.rerun()
            if _bc3.button('✏️', key=f'edit_btn2_{task["id"]}',
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

        _ec7, _ec7b, _ec8, _ec9, _ec10, _ec11 = st.columns(
            [2, 2, 1, 1, 0.7, 0.7])
        # Parse current tags for default selection
        _cur_tag_list = [t.strip() for t in tags_str.split(',') if t.strip()]
        _edit_existing = _all_tags_by_frequency(open_tasks, done_tasks)
        _edit_sel_tags = _ec7.multiselect(
            'Tags', _edit_existing,
            default=[t for t in _cur_tag_list if t in _edit_existing],
            key=f'edit_tags_multi_{task["id"]}',
            placeholder='Select tags...')
        _edit_extra = _ec7b.text_input(
            'New tags', key=f'edit_tags_{task["id"]}',
            value=', '.join(t for t in _cur_tag_list if t not in _edit_existing),
            placeholder='New tags...')
        _edit_all = list(_edit_sel_tags)
        for _et in _edit_extra.split(','):
            _et = _et.strip()
            if _et and _et not in _edit_all:
                _edit_all.append(_et)
        edit_tags = ', '.join(_edit_all)
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
            # Track modification timestamp in notes
            _mod_ts = datetime.now().isoformat(timespec='seconds')
            _existing_notes = task.get('notes', '')
            _mod_note = f'[Modified {_mod_ts}]'
            task['notes'] = (f'{_existing_notes}; {_mod_note}'
                             if _existing_notes else _mod_note)
            save_todos(open_tasks, done_tasks, deleted_tasks)
            st.session_state[f'todo_editing_{task["id"]}'] = False
            st.success(f'Updated #{task["id"]}')
            st.rerun()

        if _ec11.button('Cancel', key=f'edit_cancel_{task["id"]}'):
            st.session_state[f'todo_editing_{task["id"]}'] = False
            st.rerun()

    # ── Decline feedback form (toggled by ❌ button) ─────────────────────
    if st.session_state.get(f'todo_declining_{task["id"]}', False):
        st.warning(f'Declining task #{task["id"]}: **{task["title"]}**')
        _decline_reason = st.text_area(
            'What went wrong / what needs to change?',
            key=f'decline_reason_{task["id"]}',
            placeholder='Describe why this task is being declined...',
            height=100,
        )
        _dc_col1, _dc_col2 = st.columns([1, 1])
        if _dc_col1.button('Submit decline', key=f'decline_submit_{task["id"]}',
                           type='primary'):
            _decline_ts = datetime.now().isoformat(timespec='seconds')
            _reason_text = _decline_reason.strip() or 'No reason given'
            _decline_note = f'[DECLINED {_decline_ts}] {_reason_text}'
            _prev_notes = task.get('notes', '')
            task['notes'] = (f'{_prev_notes}; {_decline_note}'
                             if _prev_notes else _decline_note)
            task['status'] = 'open'
            # Add 'declined' tag if not already present
            _cur_tags = task.get('tags', '')
            if 'declined' not in _cur_tags:
                task['tags'] = f'{_cur_tags}, declined' if _cur_tags else 'declined'
            save_todos(open_tasks, done_tasks, deleted_tasks)
            st.session_state.pop(f'todo_declining_{task["id"]}', None)
            st.success(f'Task #{task["id"]} declined and returned to open.')
            st.rerun()
        if _dc_col2.button('Cancel', key=f'decline_cancel_{task["id"]}'):
            st.session_state.pop(f'todo_declining_{task["id"]}', None)
            st.rerun()

# Handle completions
if _tasks_to_complete:
    for task in _tasks_to_complete:
        open_tasks = [t for t in open_tasks if t['id'] != task['id']]
        done_entry = dict(task)
        done_entry['date_done'] = datetime.now().isoformat(timespec='seconds')
        done_entry['status'] = 'done'
        done_tasks.insert(0, done_entry)
    save_todos(open_tasks, done_tasks, deleted_tasks)
    st.rerun()

# Handle deletions
if _tasks_to_delete:
    for task in _tasks_to_delete:
        open_tasks = [t for t in open_tasks if t['id'] != task['id']]
        deleted_tasks.append({
            'id': task['id'],
            'title': task['title'],
            'date_deleted': datetime.now().isoformat(timespec='seconds'),
            'notes': task.get('notes', ''),
        })
    save_todos(open_tasks, done_tasks, deleted_tasks)
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
            save_todos(open_tasks, done_tasks, deleted_tasks)
            st.rerun()

# ── Deleted tasks ─────────────────────────────────────────────────────────────
if deleted_tasks:
    with st.expander(f'Deleted ({len(deleted_tasks)})', expanded=False):
        _del_restore = []
        _del_permanent = []
        for task in deleted_tasks:
            _dl1, _dl2, _dl3 = st.columns([6, 0.4, 0.4])
            with _dl1:
                st.markdown(
                    f'<span style="color:#666;text-decoration:line-through">'
                    f'#{task["id"]} — {task["title"]}</span>'
                    f'&nbsp;&nbsp;<span style="color:#555;font-size:0.8em">'
                    f'{task.get("date_deleted", "")}</span>',
                    unsafe_allow_html=True,
                )
            with _dl2:
                if st.button('↩️', key=f'undelete_btn_{task["id"]}',
                             help=f'Restore #{task["id"]} to open'):
                    _del_restore.append(task)
            with _dl3:
                if st.button('🗑️', key=f'permdel_btn_{task["id"]}',
                             help=f'Permanently delete #{task["id"]}'):
                    _del_permanent.append(task)
        if _del_restore:
            for task in _del_restore:
                deleted_tasks = [t for t in deleted_tasks
                                 if t['id'] != task['id']]
                open_tasks.append({
                    'id': task['id'],
                    'title': task['title'],
                    'description': '',
                    'priority': 'medium',
                    'tags': '',
                    'status': 'open',
                    'added_by': '',
                    'suggested_by': '',
                    'date_added': task.get('date_deleted', ''),
                    'urgent': False,
                    'important': False,
                    'notes': task.get('notes', ''),
                })
            save_todos(open_tasks, done_tasks, deleted_tasks)
            st.rerun()
        if _del_permanent:
            for task in _del_permanent:
                deleted_tasks = [t for t in deleted_tasks
                                 if t['id'] != task['id']]
            save_todos(open_tasks, done_tasks, deleted_tasks)
            st.rerun()

st.caption(
    f'{n_open} open tasks ({n_critical} critical, {n_high} high). '
    f'Check the box to mark as done. Click the pencil to edit, '
    f'or the checkmark to confirm tested features.'
)
