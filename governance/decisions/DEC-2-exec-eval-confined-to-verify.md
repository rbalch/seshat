---
id: DEC-2
title: exec and eval are confined to src/seshat/verify.py, everywhere code lives
status: accepted
kind: negative
created: 2026-09-10
superseded_by: null
controls:
  - path: controls/fitness/exec_confinement.py
    type: fitness_fn
    enforcement: block
    pragma: supported
---

## Rule
A call to `exec` or `eval` may appear only in `src/seshat/verify.py`. No other
first-party Python file in this repo may call either — every `.py` file under the
repo root, excluding any path with a hidden (dot-prefixed) directory component,
excluding `node_modules/`, `dist/`, `build/`, and `__pycache__/` wherever they occur,
and excluding `tests/fixtures/`, which is committed probe-repo data, never linted or
rewritten. A symlinked directory is never followed, regardless of what it points to
or where it resolves; code reachable only through one is not scanned and is not
covered by this rule, and meeting one is reported informationally, not as a
violation.

## Context

**This supersedes [DEC-1](DEC-1-exec-eval-confined-to-verify.md).** DEC-1's Rule named
four directories by hand — `src/`, `controls/`, `governance/`, `tests/` — and
`scripts/` was never one of them. That is not a control bug to patch; the decision
itself did not cover `scripts/`, so no amount of editing
`controls/fitness/exec_confinement.py` alone could have closed the gap without making
the control enforce more than its own decision stated. `docs/ledger-findings.md` F-42
found this directly: `scripts/` held two files (`task-status.py`,
`task-symbols.py`, the latter in-flight in PR #11) with zero coverage, and a boundary
reviewer had to be asked "is this covered?" specifically, because "does this pass?"
gave no signal at all — the control was green throughout. F-42 logged one sighting; it
is promoted here on Ryan's explicit request rather than a third sighting, the same
seeding precedent DEC-0 and DEC-1 both used, because the gap is a structural one (a
hand-maintained directory list drifting silently) rather than a recurring behavior
that needs three independent occurrences to confirm.

**The fix is a derived scan set, not a longer hand-maintained list.** Appending
`'scripts'` to `SCAN_DIRS` repeats the exact failure mode that created the gap: the
next top-level directory holding first-party Python — the control stays silent about
its own absence from the list until someone thinks to check. The control instead walks
every `.py` file from the repo root and excludes only what is clearly not first-party
source: anything under a hidden directory (`.git/`, `.venv/`, `.claude/`, `.github/`,
`.devcontainer/`, `.ruff_cache/`, `.pytest_cache/`, `.mypy_cache/`, and any future
dot-directory, all in one exclusion by name shape rather than by listing each), the
small fixed set of dependency/build directory names that never hold source in any
language (`node_modules/`, `dist/`, `build/`, `__pycache__/`), and `tests/fixtures/`
specifically, which is real Python under version control but committed test data, not
project source — this repo's `pyproject.toml` excludes it from lint/format for the
same reason. Measured directly against the tree at the time of writing: this derives
to exactly `controls/`, `governance/`, `scripts/`, `src/`, and `tests/` (minus
`tests/fixtures/`) — the same five directories a person would list by hand today, but
arrived at by asking "is this source?" of every file, so a sixth directory added
tomorrow is scanned automatically instead of silently passing.

**DEC-1's Context contained a false claim about ruff, which this decision does not
carry forward.** DEC-1 asserted that ruff's `S102` ("no `exec` builtin") was active by
default and had been silently guarding the whole repo, with `src/seshat/verify.py`'s
`per-file-ignores` entry "buying T-05 its one legitimate call" out from under that
guard. This is false and was not verified before DEC-1 was written. `S102` is a
flake8-bandit (`S`) rule; this repo's `pyproject.toml` sets
`[tool.ruff.lint] extend-select = ["B", "I", "RUF", "UP"]`, which never includes `"S"`,
and ruff does not enable `S` by default outside an explicit select. Verified directly:
a file containing `x = eval("1")` passes `uv run ruff check` with no findings, in both
`src/seshat/` and `scripts/`. The `S102` per-file-ignore on `verify.py` is a no-op —
it lifts a guard that was never enforcing anything. The plain truth is simpler than
DEC-1's story: **nothing but this control, from the moment DEC-1 landed, has ever
guarded `exec`/`eval` in this repo.** The per-file-ignore stays in `pyproject.toml`
as documentation of intent (harmless, and removing it is a separate, unrelated
cleanup), but no rationale in this decision or its control depends on it doing
anything.

**Symlinked directories are not followed, and this was learned the expensive way.**
An earlier revision of this control tried to walk into a symlinked directory whose
target resolved inside the repo root, and fail if it resolved outside. A reviewer
planted a symlink with an ordinary name pointing at `.venv` (`src/venv_alias ->
.venv`); the name-based exclusion check only ever looked at the link's own name, so
it never recognised the target as excluded, and the control walked roughly a hundred
third-party files behind it, taking the run from 0.4s to 18s. The identical trick
reaches `.claude/worktrees/`, which holds full checkouts of this repo on other
branches — the one directory that must never be scanned by a control running inside
one of those checkouts. Two rounds went into guarding the descend-if-inside logic
before it was clear the guarding itself was the problem: each fix closed one hole
and the shape of the mechanism opened another. The rule this decision states now is
the one that ends that cycle — not "descend carefully," but "do not descend, and say
so when it matters." Code that only exists behind a symlinked directory is invisible
to this control; that is an accepted, stated limit of the rule, not a silent gap —
the distinction this whole decision exists to draw.

## Consequences

`controls/fitness/exec_confinement.py` walks the `ast` of every `.py` file reachable
from the repo root, skipping a file if any path component (relative to the repo root)
starts with `.`, if any path component is `node_modules`, `dist`, `build`, or
`__pycache__`, or if the file lies under `tests/fixtures/`. It looks for an `ast.Call`
whose function is a bare `ast.Name` with `id` in `{'exec', 'eval'}`. It goes **red**,
names the offending file and line, and exits non-zero if that call appears anywhere
but `src/seshat/verify.py`. It goes **green** on the tree as it stands, including
`verify.py`'s own `compile(tree, '<verifier>', 'exec')` — a string literal, not a call
to the `exec` builtin.

The walk never descends into a directory it finds via a symlink, whatever that
symlink's target. Meeting one inside an otherwise-scanned area prints
`INFO [DEC-2] <path>: symlinked directory, not scanned — see DEC-2.` to stdout; this
never changes the exit code by itself, only real violations and unreadable files do.
A file that cannot be decoded as UTF-8, or does not parse as Python, is reported as a
failure for that file and the scan continues to the rest of the tree.

`pyproject.toml` keeps its existing per-file-ignore for `S102` scoped to
`src/seshat/verify.py`; this decision does not change it and does not rely on it.

## Rejected alternatives

- **Add `'scripts'` to `SCAN_DIRS` and leave the rest of the control as-is.** Rejected.
  This is the fix that would need repeating for the next new source directory, and
  nothing would announce that it had been missed — the exact mechanism that produced
  F-42. A derived scan set only needs writing once.

- **Scan the whole tree and rely on `.gitignore` to define what is source.** Considered.
  `.gitignore` governs what git tracks, not what is first-party source about to be
  executed — an untracked scratch file with a fresh `eval()` in it, not yet
  `git add`ed, would slip past a scan gated on git's index or `git check-ignore`, and a
  control that only catches violations once they are staged is weaker than one that
  catches them the moment the file exists. Excluding by path shape (hidden directories,
  known build/dependency directory names) catches this case too, without the extra
  process dependency on `git`.

- **Descend into a symlinked directory whose target resolves inside the repo root,
  and fail the run if it resolves outside.** Tried, in an earlier revision of this
  decision's control, and rejected after it caused the exact failure it was meant to
  prevent: the in/out judgment only ever ran once the walk had already decided to
  look at the symlink, but the decision of *whether this directory is excluded at
  all* was a separate, name-based check that a symlink with a plain name skipped
  right past. Guarding the descent more carefully (checking the resolved target
  against the exclusion list too, not just the link's own name) was considered and
  rejected as a third layer on a mechanism that had already needed two — not
  descending removes the class of bug outright instead of extending it.

- **Fail the run when a symlinked directory is met, instead of an informational
  line.** Rejected. Not descending is a stated, accepted limit of this rule, not a
  violation of it — nothing under a symlinked directory was ever claimed to be
  covered. Failing a clean run over a legitimate symlink (a vendored submodule
  checkout, an editable install) would make the control cry wolf on structure that
  has nothing to do with `exec`/`eval`, which is the one failure mode this whole
  harness treats as worse than a coverage gap.

- **Amend DEC-1 in place rather than superseding it.** Rejected. DEC-1's Rule text is
  wrong as a statement of current policy, but it was the recorded, accepted policy at
  the time, and this repo's own governance harness (`check_governance.py`'s scoping
  note) treats history as a record, not something to overwrite. Superseding leaves
  DEC-1 legible as "what we believed and enforced, and when" and DEC-2 as "what we
  believe and enforce now," which a future reader of either file needs to be able to
  tell apart.
