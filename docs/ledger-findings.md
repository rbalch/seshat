# Ledger findings

The experiment log. Every dislike of agent output gets sorted into a bin and recorded
here, whether or not it becomes a control. An unlogged finding is a lost data point.

- **Bin 1** — already covered by a linter or type-checker. The harness adds nothing.
- **Bin 2** — a concrete, checkable, systemic pattern. **This is the value.**
- **Bin 3** — genuine subjective taste. No control will ever catch it.

Rule of three: a Bin 2 finding stays in the soft layer (a note, a nudge, a one-off
correction) until its **third** sighting. Only then does it earn a decision and a
CI-enforced control.

**The falsifiable test:** if Bin 2 stays fat and review burden measurably shrinks, the
harness earns its keep. If nearly everything lands in Bin 1 or Bin 3, this is
complicated linters plus a wiki and we should say so and drop it. Do not judge it by
"does CI go red."

See the `finding-triage` skill for the procedure and the entry template.

Findings about the **harness itself** — something it got wrong, friction that felt like
ceremony, a control that fired on correct code — are worth logging here too. Mark them
as harness findings and leave them unbinned; the bins sort dislikes of *agent output*,
and forcing a harness observation into one loses what makes it interesting.

---

## Findings

### F-1 — planner named a symbol the fixture never defines

- **Date:** 2026-09-06
- **Task:** T-01 (found while reviewing its output, but the fault is in T-04 and T-05)
- **Bin:** 2
- **Claim:** Every symbol named in a task's acceptance criteria exists in the fixture or
  code that task depends on. T-04 and T-05 both asserted on `subclasses('Order')`; the
  fixture defines `SpecialOrder(OrderRepository)` and no `Order` class at all.
- **Sightings:** 1
- **Action:** soft — task files corrected on develop in 6956b65, no control
- **Notes:** Checkable in principle: a script could parse the acceptance blocks for
  quoted identifiers and grep the fixture for them. Worth doing only if this recurs,
  since the cost of the error was one orchestrator inspection and a two-line sed.
  Caught before T-04 was dispatched; had it landed, a builder would have written a test
  against a class that does not exist and burned a review round proving it.

### F-2 — harness: two reviewers sharing one worktree contaminated each other

- **Date:** 2026-09-06
- **Task:** T-01
- **Bin:** unbinned harness finding
- **Claim:** The orchestrate skill dispatches boundary-reviewer and reviewer into the
  same builder worktree. Both were told to verify by execution rather than by reading,
  and both did so by planting a deliberate defect and reverting it. Run concurrently,
  each saw the other's plant. The code reviewer reported a transient stray function in
  `demo/errors.py` and a momentarily detached HEAD, correctly guessed it was not a real
  defect, and dismissed it.
- **Sightings:** 1
- **Action:** soft — noted. The orchestrator verified the worktree was clean before
  squashing, and it was.
- **Notes:** The dismissal happened to be right, which is the worrying part. A reviewer
  that learns to attribute anomalies to its own tooling is a reviewer that will one day
  wave through a real one. Two cheap fixes exist: run the reviewers in sequence, or give
  each its own checkout of the branch. Sequential costs wall-clock on every task;
  separate checkouts cost disk. Neither is obviously right yet, so this is a note, not a
  change. Watch for a second sighting where the dismissal is wrong.

<!--
### F-1 — <one-line description>
- **Date:** YYYY-MM-DD
- **Bin:** 2
- **Claim:** <the dislike, stated so a machine could check it>
- **Sightings:** 1
- **Action:** soft — noted, no control yet
- **Notes:** <anything surprising about the harness itself>
-->

### F-3 — orchestrator staged with `git add -A` and swept in unreviewed changes

- **Date:** 2026-09-06
- **Task:** T-01
- **Bin:** 2
- **Claim:** A commit stages named paths. `git add -A` in a repo that hosts agent
  worktrees and a human's work-in-progress stages both. The T-01 triage commit picked up
  `.claude/worktrees/agent-a7e1dd28cc50b605c` as a gitlink to an embedded repository,
  and an unrelated `dev.Dockerfile` edit belonging to the human, then pushed both to
  develop under the message "triage and status".
- **Sightings:** 1
- **Action:** soft — backed out in 172075d, `.claude/worktrees/` added to `.gitignore`.
  No control: this is one habit in one role, and a control that inspected commit
  contents for "things that look unrelated" would be guesswork.
- **Notes:** The gitignore entry removes half the failure for good, which is the better
  fix. The other half, sweeping up a human's uncommitted work, remains available on
  every future task and only discipline prevents it. The orchestrate skill tells the
  orchestrator to commit status and triage together but never says how to stage. Worth a
  line in the skill if this recurs.
