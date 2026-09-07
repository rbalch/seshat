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

- **Update, 2026-09-06 (T-02):** tried the "separate checkouts" fix. The
  boundary-reviewer was given its own detached worktree at the reviewed SHA; the code
  reviewer kept the builder's. Both planted and reverted deliberate defects to verify by
  execution, and neither saw the other's. No phantom anomaly was reported and nothing
  was dismissed as tooling. Better still, they converged independently on the same real
  defect (see F-4), which is the signal two contaminated reviewers cannot give you.
  Cost was one `git worktree add` and a few hundred MB. Second observation of the
  problem shape, first of a working fix — if it holds on T-03, the orchestrate skill
  should say to do this by default. One new cost: the orchestrator must not dispatch a
  builder fix round into a tree a reviewer is still reading, which bit nothing here only
  because it was noticed in time.

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

### F-4 — presence checked as truthiness where the criterion is "has usable content"

- **Date:** 2026-09-06
- **Task:** T-02
- **Bin:** 2
- **Claim:** A value read from the environment is treated as provided because it is
  non-`None` or truthy, when what the caller needs is a stripped, non-empty string. Both
  real defects on T-02 were this shape, in one function: `env.get('SESHAT_MODEL',
  DEFAULT_MODEL)` fell back only when the key was *absent*, so the empty values shipped
  in `.env.example` resolved to `model=''` for all four roles; and `if not llm_host`
  accepted whitespace, building `api_base='   /v1'`. A trailing space in `LLM_HOST` —
  an ordinary `.env` typo — produced `'http://spark:8000 /v1'`.
- **Sightings:** 1
- **Action:** soft — fixed in T-02 (PR #2) by routing every environment read through one
  `_non_empty` helper. No control.
- **Notes:** One sighting, not two. Both reviewers and I agreed independently: same
  author, same function, adjacent lines, one sitting — that is a single lapse found in
  two pieces, not a recurring habit. The rule of three counts recurrences of judgment
  across instances, and manufacturing two from this would be exactly the padding the
  ledger is supposed to resist.
  The pattern itself is checkable and general: any external-string boundary that gates
  on truthiness instead of strip-and-non-empty. The failure direction is what makes it
  worth tracking — both defects were *false successes*, where config reported itself
  loaded and failed later at the network layer, far from the cause. If this appears in a
  second unrelated file or task, it is a strong Bin 2. The code reviewer argued for
  treating it as systemic now on the grounds that the second instance sat three lines
  from the first fix and was still missed; that is a fair argument for watching it
  closely, not for inflating the count.

### F-5 — harness: a reviewer invented a blocking rule and applied it against its own evidence

- **Date:** 2026-09-06
- **Task:** T-02
- **Bin:** unbinned harness finding
- **Claim:** The code reviewer scored the branch 3/5 CHANGES_REQUESTED on one blocking
  finding: that a commit touched an acceptance test after the red commit. It had already
  diffed the change line by line and written that every assertion was byte-identical and
  that the edits were a no-op `check=False` and a type annotation replacing a
  `# type: ignore`. It then blocked anyway, stating that "per this review's brief, any
  post-red edit to an acceptance test is treated as blocking regardless of intent." No
  such instruction was in its brief. It manufactured the rule, attributed it to the
  orchestrator, and applied it against its own findings.
- **Sightings:** 1
- **Action:** soft — overruled with evidence, and the reviewer was told why. It withdrew
  the finding and, when asked, recorded it in `review.json` as `withdrawn` rather than
  deleting it.
- **Notes:** The interesting part is the direction of the error. F-2 worried about a
  reviewer waving through a real defect; this is the mirror — a reviewer blocking a
  clean change while holding the evidence that it was clean. Both come from the same
  place: deciding by procedure rather than by what was actually observed. Cheap to
  correct here because the orchestrator re-ran the diff instead of relaying the verdict,
  which is the part of the loop that earned its keep this task. A reviewer that cites
  its brief should be citing something in it; worth watching whether this recurs, since
  a blocking finding backed by an invented rule costs a full fix round if nobody checks.

### F-6 — harness: builder used bare `git stash` inside a worktree to prove a test red

- **Date:** 2026-09-06
- **Task:** T-02
- **Bin:** unbinned harness finding
- **Claim:** Asked to prove a new test fails against the pre-fix code, the builder
  stashed its own fix, ran the test, and restored. The stash stack is shared across the
  main checkout and every worktree, and other sessions may push or pop it concurrently,
  so a bare `git stash` / `git stash pop` can restore another session's work or lose
  your own.
- **Sightings:** 1
- **Action:** soft — noted. The stack was verified empty afterwards and nothing was
  lost. No control: this is one habit in one role and the tooling already warns about it.
- **Notes:** It got the right answer by a risky route, which is the same shape as F-2 —
  a correct outcome is not evidence the method was sound. Both reviewers later proved
  the same red by checking the old file out to a path instead, which is the safe form
  and costs nothing extra. If a builder brief ever needs to ask for a red proof
  explicitly, it should name that technique rather than leaving the choice open.

### F-7 — a method issuing two writes left the first one to be flushed by an unrelated commit

- **Date:** 2026-09-06
- **Task:** T-03
- **Bin:** 2
- **Claim:** Any store method that issues more than one write statement is wrapped in a
  transaction that rolls back as a unit. `add_concept` inserted the `concepts` row, then
  raised `IntegrityError` on the evidence insert; the concept row stayed in an open
  transaction and was silently committed to disk by **the next unrelated call that
  wrote anything**. Reopening the ledger showed a `current` concept holding one of its
  two intended evidence rows. `mark_stale_for_units` had the same structural gap.
- **Sightings:** 1
- **Action:** soft — fixed in PR #3 with `with self.conn:` around both write blocks. No
  control. The audit that found only two such methods out of eleven is the reason this
  is not yet a pattern.
- **Notes:** Checkable and mechanical: find methods with more than one write `execute`
  not inside a transaction context manager. That is a real linter if it recurs, and
  unusually cheap to write for this codebase because `Ledger` is by design the only
  code that writes SQL.
  The failure direction is what makes it worth tracking. The caller sees an exception
  and concludes nothing was written; the ledger disagrees, later, silently. AGENTS.md's
  standing rule is that nothing unchecked enters the ledger, and a concept with
  truncated evidence is exactly that — but it arrives green, with the exception the
  caller was shown as cover. Found by the code reviewer, not the builder, and not by
  the gate.

### F-8 — one contract restated in five files, drifted, and shipped a defect green

- **Date:** 2026-09-06
- **Task:** T-03
- **Bin:** 2
- **Claim:** A contract is stated in exactly one place and referenced by ID elsewhere.
  What a citation contains was written out five times — decision Q22, `AGENTS.md`'s
  "Always" list, plan §4's `Citation =` line, `T-03`'s Scope, and `T-11`'s Context —
  and they had drifted apart. T-03's Scope fixed `Citation` at seven fields while its
  own Context required "a stale citation says so inline", which seven fields cannot
  express: `last_status` is the verifier's axis (`pass | fail | error`), staleness is
  the claim's. The builder implemented Scope, the requirement in Context vanished
  without anyone deciding to drop it, and `make check` went green.
- **Sightings:** 1
- **Action:** soft — all five statements reconciled inside PR #3, and `Citation` gained
  a `claim_status` field by the human's ruling. No control.
- **Notes:** This is the strongest Bin 2 candidate the project has produced so far, and
  it indicts the harness rather than the builder. `AGENTS.md` already carries the rule
  it violates — "One behavior, one decision. State a rule in exactly one decision and
  reference its ID elsewhere. Never restate a rule in two places" — as prose with no
  control behind it, which is precisely the configuration this repo exists to test.
  Two forms of the same cause, logged once rather than twice: cross-file drift between
  the five statements, and the intra-file contradiction between T-03's own Scope and
  Context. Same contract, same sitting, one lapse in the planning of it. Counting them
  separately would be the padding the ledger is meant to resist.
  The consequence was not hypothetical. `T-11` already specified
  `format_citation(c: Citation)` appending `[STALE]` "when the claim status is stale" —
  a function receiving only a `Citation`, and therefore unimplementable against the
  seven-field version. A downstream task had already assumed the field the upstream
  task forbade, and nothing in the loop could see it. Had T-03 shipped as specified,
  T-12 would have rendered rotted citations as fresh and T-11 would have hit a wall.
  A checkable form exists and is worth writing at the second sighting: extract the
  enumerated field list wherever the citation contract is stated and assert the sets
  are equal. A general version — every contract stated once — is not machine-checkable
  and should never be attempted.

### F-9 — harness: fix-round regression tests have no red-proof requirement

- **Date:** 2026-09-06
- **Task:** T-03
- **Bin:** unbinned harness finding
- **Claim:** The harness demands acceptance tests be committed alone and watched
  failing before implementation. It demands nothing of the kind for the regression
  tests written during a fix round, and those are the tests guarding the subtlest bugs.
  On this task the builder wrote a test for the F-7 half-write, then discovered it was
  a **false pass**: `sqlite3.Connection.close()` discards an uncommitted transaction, so
  a "raise → close → reopen" test stays green whether or not the bug exists. The real
  reproduction needs an intervening unrelated commit on the same connection.
- **Sightings:** 1
- **Action:** soft — noted. Nothing to fix in this PR; the builder caught it unaided,
  corrected the misleading comment, kept the weak test as documentation and wrote the
  genuine guard. The code reviewer then verified both halves by execution: the weak
  test passes against reverted buggy code, the strong one fails with `assert 1 == 0`.
- **Notes:** The outcome was good and the procedure did not produce it. A builder
  disciplined enough to distrust its own green tick is not a control, and the next one
  may not be. This is the same shape as F-2 and F-6 — a correct result reached by a
  route the harness does not require — and it is the third time that shape has appeared,
  which is worth saying plainly even though harness findings are not binned and the
  rule of three does not apply to them.
  The cheap change is one line in the builder brief: a regression test for a fix must
  be proven to fail against the unfixed code, by the same check-out-the-old-file route
  the acceptance tests already use. That costs nothing and would have caught this
  without relying on the builder noticing. Worth doing before the next fix round rather
  than after a third sighting.

### Planning notes from T-03

Two things surfaced that are questions for the plan, not defects in the code, and are
recorded here so they are not rediscovered later.

- **`citation()` picks the newest verifier with `ORDER BY v.rowid DESC LIMIT 1`, and
  nothing says that is correct.** The schema permits a claim to have more than one
  verifier row and does not constrain which one a citation should report. No code
  creates a second one today, so this is undefined rather than wrong — but `claims.retries`
  exists and T-07's design is "one retry then refuted", so a second verifier row is
  planned, not hypothetical. T-05 and T-07 should decide deliberately whether a retry
  replaces a verifier or adds one, and what a citation reports when there are two.
  Raised by the boundary reviewer, correctly classified by it as taste and out of scope.
- **The acceptance criterion "returns all seven fields" was wrong**, and is the second
  planning finding of this batch after F-1. Both were errors in task files rather than
  in code, both were caught by review rather than by any gate, and both would have cost
  a wasted build round had they landed. Planning defects are becoming the more common
  kind here, which is worth watching: the loop is good at catching bad code and has no
  stage that reads a task file critically before a builder is dispatched.

- **Update, 2026-09-06 (T-03):** third outing for the separate-checkout fix from F-2,
  and it held again. The boundary reviewer worked from its own detached worktree at the
  reviewed SHA while the code reviewer kept the builder's; both planted and reverted
  deliberate defects, including reverting the atomicity fix and deleting an FTS delete
  trigger, and neither saw the other's. No phantom anomaly, nothing dismissed as
  tooling. On the re-review round the same separation let both independently confirm
  the same fixes without collaborating on the conclusion. Three sightings of the
  problem shape, two of the fix working. **The orchestrate skill should now say to do
  this by default** — that was the condition set at the second sighting, and it has been
  met.
