"""TODO.md parsing and writing — extracted from overnight_agent.py."""
from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
_TODO_PATH = _ROOT / 'TODO.md'

QUADRANT_FILTERS = {
    'eliminate': lambda t: not t.get('urgent') and not t.get('important'),
    'delegate': lambda t: t.get('urgent') and not t.get('important'),
    'schedule': lambda t: not t.get('urgent') and t.get('important'),
    'do_first': lambda t: t.get('urgent') and t.get('important'),
}
QUADRANT_ORDER = ['eliminate', 'delegate', 'schedule']


def _parse_bool(val: str) -> bool:
    return val.strip().lower() in ('y', 'yes', 'true', '1')


def _bool_str(val: bool) -> str:
    return 'Y' if val else 'N'


def _parse_table_rows(lines: list[str]) -> list[list[str]]:
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
    """Parse TODO.md into (open_tasks, done_tasks) lists of dicts."""
    if not _TODO_PATH.exists():
        return [], []
    content = _TODO_PATH.read_text(encoding='utf-8')
    open_tasks, done_tasks = [], []

    sections = re.split(r'^## ', content, flags=re.MULTILINE)
    for section in sections:
        if section.startswith('Open Tasks'):
            rows = _parse_table_rows(section.split('\n'))
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
                        'urgent': _parse_bool(cells[9]) if len(cells) > 9 else False,
                        'important': _parse_bool(cells[10]) if len(cells) > 10 else False,
                    })
        elif section.startswith('Done'):
            rows = _parse_table_rows(section.split('\n'))
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
                    })
                elif len(cells) >= 3:
                    done_tasks.append({
                        'id': int(cells[0]) if cells[0].isdigit() else 0,
                        'title': cells[1],
                        'date_done': cells[2],
                    })
    return open_tasks, done_tasks


def save_todos(open_tasks: list[dict], done_tasks: list[dict]) -> None:
    """Write tasks back to TODO.md in markdown table format."""
    priority_order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
    open_tasks.sort(key=lambda t: priority_order.get(t.get('priority', 'low'), 3))

    lines = ['# Project To-Do List\n', '\n## Open Tasks\n']
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
    _TODO_PATH.write_text('\n'.join(lines), encoding='utf-8')


def update_task_status(task_id: int, new_status: str) -> None:
    """Update a single task's status in TODO.md."""
    open_tasks, done_tasks = load_todos()
    for t in open_tasks:
        if t['id'] == task_id:
            t['status'] = new_status
            break
    save_todos(open_tasks, done_tasks)


def select_tasks(quadrant: str, include_critical: bool = False,
                 task_ids: list[int] | None = None) -> list[dict]:
    """Select tasks from TODO.md by quadrant or explicit IDs."""
    open_tasks, _ = load_todos()

    if task_ids:
        id_set = set(task_ids)
        actionable = {'open', 'in-progress'}
        selected = [t for t in open_tasks if t['id'] in id_set
                    and t.get('status', 'open') in actionable]
        id_order = {tid: i for i, tid in enumerate(task_ids)}
        selected.sort(key=lambda t: id_order.get(t['id'], 999))
        return selected

    open_only = [t for t in open_tasks if t.get('status', 'open') == 'open']

    if quadrant == 'all':
        order = list(QUADRANT_ORDER)
        if include_critical:
            order.append('do_first')
        candidates = []
        for q in order:
            filt = QUADRANT_FILTERS[q]
            group = [t for t in open_only if filt(t)]
            priority_order = {'low': 0, 'medium': 1, 'high': 2, 'critical': 3}
            group.sort(key=lambda t: priority_order.get(t.get('priority', 'low'), 0))
            candidates.extend(group)
        return candidates

    filt = QUADRANT_FILTERS.get(quadrant, QUADRANT_FILTERS['eliminate'])
    candidates = [t for t in open_only if filt(t)]
    priority_order = {'low': 0, 'medium': 1, 'high': 2, 'critical': 3}
    candidates.sort(key=lambda t: priority_order.get(t.get('priority', 'low'), 0))
    return candidates
