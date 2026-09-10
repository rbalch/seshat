#!/usr/bin/env python3
"""Print the live status of every task in a plan directory.

Status is derived, not stored: a task is ``done`` when a PR titled ``T-NN: ...``
has merged, ``in_review`` when one is open, ``blocked`` when a dependency is not
done, and ``ready`` otherwise. Usage::

    make tasks PLAN=tasks/<plan-slug>   # or: uv run python scripts/task-status.py tasks/<plan-slug>
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

FRONT = re.compile(r'^---\n(.*?)\n---', re.DOTALL)


def frontmatter(path: Path) -> dict[str, str]:
    m = FRONT.match(path.read_text())
    if not m:
        raise SystemExit(f'{path}: no frontmatter')
    out: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ':' in line and not line.startswith(' '):
            k, v = line.split(':', 1)
            out[k.strip()] = v.split('#', 1)[0].strip()
    return out


def deps(raw: str) -> list[str]:
    return [d.strip() for d in raw.strip('[]').split(',') if d.strip()]


def pr_index() -> dict[str, dict]:
    """Map task id -> PR record. Merged beats open beats closed if a task has several."""
    raw = subprocess.run(
        ['gh', 'pr', 'list', '--state', 'all', '--limit', '200', '--json', 'number,title,state,url'],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    rank = {'MERGED': 2, 'OPEN': 1, 'CLOSED': 0}
    index: dict[str, dict] = {}
    for pr in json.loads(raw):
        m = re.match(r'([A-Z]+-\d+):', pr['title'])
        if not m:
            continue
        tid = m.group(1)
        if tid not in index or rank[pr['state']] > rank[index[tid]['state']]:
            index[tid] = pr
    return index


def main(plan_dir: str) -> None:
    # Ids are plan-qualified by prefix (T-NN for seshat-phase-one, CT-NN for
    # critic-tooling, ...) because PR titles carry the id alone and nothing else
    # says which plan a PR belongs to.
    files = [p for p in sorted(Path(plan_dir).glob('*.md')) if p.name != 'README.md']
    tasks = [frontmatter(p) for p in files]
    prs = pr_index()
    status: dict[str, str] = {}
    for t in tasks:  # sorted by id, deps always point backwards
        pr = prs.get(t['id'])
        if pr and pr['state'] == 'MERGED':
            status[t['id']] = 'done'
        elif pr and pr['state'] == 'OPEN':
            status[t['id']] = 'in_review'
        elif all(status.get(d) == 'done' for d in deps(t['depends_on'])):
            status[t['id']] = 'ready'
        else:
            status[t['id']] = 'blocked'

    icon = {'done': '✅', 'in_review': '👀', 'ready': '🟢', 'blocked': '⛔'}
    width = max(len(t['title']) for t in tasks)
    for t in tasks:
        s = status[t['id']]
        pr = prs.get(t['id'])
        tail = f'PR #{pr["number"]}' if pr else ''
        if s == 'blocked':
            waiting = [d for d in deps(t['depends_on']) if status.get(d) != 'done']
            tail = f'waits on {", ".join(waiting)}'
        print(f'{icon[s]} {t["id"]}  {s:<10} {t["title"]:<{width}}  {tail}')

    counts = {s: sum(1 for v in status.values() if v == s) for s in icon}
    print('\n' + '  '.join(f'{k}={v}' for k, v in counts.items() if v))
    ready = [t['id'] for t in tasks if status[t['id']] == 'ready']
    if ready:
        print(f'next: {", ".join(ready)}')


if __name__ == '__main__':
    if len(sys.argv) > 1:
        main(sys.argv[1])
    else:
        plans = [p for p in Path('tasks').iterdir() if p.is_dir()]
        if len(plans) != 1:
            raise SystemExit(f'pass a plan dir; found {[str(p) for p in plans]}')
        main(str(plans[0]))
