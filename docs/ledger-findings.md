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
- **Sightings:** **3.** Second `F-29` (T-09). **Third 2026-09-10, T-11** — see `F-38`.
  This is the rule of three; a control was considered and the outcome is recorded in
  `F-38`.
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

### F-10 — the seam answered wrongly and gave the caller no way to tell

- **Date:** 2026-09-07
- **Task:** T-04
- **Bin:** 2
- **Claim:** A method whose contract is "the distinct things matching X" returns
  something else, and returns it in a shape indistinguishable from a correct answer.
  Two mechanisms, both in `src/seshat/graph.py`, both found by review and neither
  visible to a green `make check`:
  - `callers`, `callees` and `subclasses` joined `edges` without `DISTINCT`. codegraph
    records **one edge per call site**, so a caller invoking a target six times came
    back as six identical `Node` objects. Not hypothetical: this repo's own index has
    79 duplicate `(source, target, kind)` groups — `parse_decision → _require` appears
    six times. Every verifier counting callers or subclasses would have been inflated.
  - `decorators()` returned `[]` for **every decorated class**, because the `ast`
    fallback's `_find_def` returned `None` when the name it was walking terminated on a
    `ClassDef`. A decorated class got a confident "no decorators".
- **Sightings:** 1 as stated here. **As the false-success family, 2** — see below.
- **Action:** soft — both fixed in PR #4, each with a regression test proven red first
  (`32c0cef`/`a842491`, `4676c8c`/`c61b039`). No control.
- **Notes:** Logged once, not twice. Missing `DISTINCT` is a SQL habit and the unhandled
  `ClassDef` is a control-flow omission — different mechanisms — but they are one author,
  one file, one sitting, and the F-4 and F-8 precedents both say that is a single lapse
  found in two pieces. Manufacturing two sightings from it is the padding this ledger
  exists to resist.
  What makes it worth tracking is the failure direction, which is the same one F-4
  recorded: **a false success**. Both defects report work done that was not done, and
  both stay silent. F-4's own note set the condition — "if this appears in a second
  unrelated file or task, it is a strong Bin 2" — and this is that second appearance,
  in a different file, a different task, a different author, and a different mechanism.
  **The false-success family now stands at two sightings.** One more and it earns a
  decision. What a control could actually check is narrower than the family: "every
  query in the graph seam that joins `edges` and returns nodes uses `DISTINCT`" is
  mechanically checkable and worth writing if it recurs. "Never return a confidently
  wrong answer" is not, and must never be attempted.

### F-11 — acceptance tests passed because the fixture cannot express the failure

- **Date:** 2026-09-07
- **Task:** T-04
- **Bin:** 2
- **Claim:** Acceptance tests are written against a fixture that does not contain the
  shapes the contract must handle, so they pass vacuously and the suite's green says
  nothing about the criterion. `tests/fixtures/target` has zero duplicate edges and no
  decorated class. Both F-10 defects were therefore invisible to eleven acceptance
  criteria, twelve passing tests and a green `make check`; both were found by a reviewer
  reasoning about the contract, not by the gate.
- **Sightings:** 1
- **Action:** soft — regression tests now build a synthetic codegraph-schema database
  under `tmp_path` rather than extending the committed fixture, which would have
  invalidated its committed index. No control.
- **Notes:** The third planning finding of this batch, after F-1 (a symbol the fixture
  never defines) and T-03's "seven fields" criterion. The trend the T-03 notes flagged
  is holding: **planning defects are now the most common kind here, and the loop still
  has no stage that reads a task file critically before a builder is dispatched.** This
  one is a sharper version of F-1 — there the fixture lacked a symbol the criteria named,
  which fails loudly; here the fixture lacked a *shape* the criteria assumed, which
  passes quietly. The second is much worse, because the reward for writing the test is
  a green tick.
  A checkable form is not obvious and I am not proposing one. "Every acceptance
  criterion is exercised by fixture data that could falsify it" is mutation testing,
  which is a real technique and a disproportionate answer to three findings. The cheaper
  answer, if this recurs: when a task's criteria depend on a property of the fixture
  (a duplicate edge, a decorated class, two callers), the task file names that property
  explicitly so a builder can check it exists before writing the assertion.

### F-12 — harness: a subagent read the session's own tool-routing instruction as an attack

- **Date:** 2026-09-07
- **Task:** T-04
- **Bin:** unbinned harness finding
- **Claim:** Mid-build, the builder received the session-level `system-reminder`
  instructing that file reads and edits be routed through Bash rather than the
  Read/Edit/Write tools. It refused, and reported it to the orchestrator as a suspected
  injection: "looked like an attempt to get file mutations done through less-inspectable
  shell commands." The instruction was a legitimate harness setting from the human's own
  configuration, inherited by the subagent.
- **Action:** soft — noted. No harm done; the builder's chosen tools were fine and the
  work was unaffected.
- **Notes:** The refusal was the right instinct applied to the wrong object, and the
  instinct is worth more than the false positive — a builder that ignores an
  unexplained instruction to move file mutation into the shell is behaving correctly,
  and I would rather field this report than not. The real observation is about
  inheritance: session-level directives reach subagents stripped of the context that
  makes them legible, and a subagent has no way to distinguish "the human configured
  this" from "something injected this mid-run." It cost one paragraph here; on a
  security-sensitive change it could cost a whole build round, or worse, teach a builder
  that unexplained instructions are safe to dismiss. Watch for a second sighting.

- **Update, 2026-09-07 (T-04): F-9 second sighting.** The T-03 entry proposed a one-line
  fix — "a regression test for a fix must be proven to fail against the unfixed code, by
  the same check-out-the-old-file route the acceptance tests already use" — and said it
  was worth doing before the next fix round rather than after a third sighting. It was
  not done as a standing line in the builder brief; I wrote it per-item instead, into
  fix-round items 1 and 2 and not into item 3. **Item 3 is the one that shipped
  untested.** The `ORDER BY` tiebreak changed a stated contract and arrived with nothing
  proving it held, and it took a reviewer round to notice; the test written afterwards
  did fail red against the pre-fix query (`['Zebra.foo', 'Apple']` instead of
  `['Apple', 'Zebra.foo']`), so the fix was correct and the gap was purely in the
  evidence. Second sighting, and the cause is now specific: **an instruction repeated
  per-item gets forgotten on the item that looks too small to need it.** It belongs in
  the builder brief once, applying to every fix, not attached to the findings that
  happen to feel serious. Harness findings are not binned and the rule of three does not
  apply, but two sightings with a known one-line fix is enough — this should go into the
  builder dispatch section of the orchestrate skill.
  A methodology trap found in the same round and worth recording next to it: the code
  reviewer noted that `git checkout <sha> -- .` only overlays tracked paths from that
  commit and does not delete files added later, so it is **not** a safe way to reproduce
  a red proof — a file added after the SHA survives the checkout and can turn the red
  green. Use a real detached checkout. It caught this itself mid-review and switched.

- **Update, 2026-09-07 (T-04): F-2 held a fourth time.** Boundary reviewer in its own
  detached checkout at the reviewed SHA, code reviewer in the builder's worktree, across
  two review rounds each. No cross-contamination, no anomaly dismissed as tooling, and
  on the first round they converged independently on overlapping-but-distinct defects —
  the boundary reviewer found the missing `DISTINCT`, the code reviewer found the
  `ClassDef` fallback, and neither found the other's. The condition set at the second
  sighting was met at the third and the skill still does not say to do this by default;
  the orchestrator did it from the ledger rather than from the skill, which is exactly
  the fragility the ledger is supposed to remove. **Still owed: one line in the
  orchestrate skill.**

- **Update, 2026-09-07 (T-04): F-2 is closed.** The separate-checkout fix is now written
  into the orchestrate skill's reviewer-dispatch section and into the "things that will
  bite you" list in `AGENTS.md`, so it no longer depends on an orchestrator reading this
  log first. Five sightings of the problem shape, three of the fix working, and the
  condition set at the second sighting is finally discharged. No control, and none is
  possible: this is a fact about how subagents are dispatched at runtime, which leaves
  nothing in the repo for a script to inspect. Harness findings get written into the
  procedure or they get forgotten — that is the whole repertoire.
  Still open from the same family: **F-9**, the red-proof requirement for fix-round
  regression tests, which has two sightings and the same one-line remedy, and is not yet
  written anywhere.

### F-13 — the verifier sandbox handed out the whole interpreter, and reported the abuse as `pass`

- **Date:** 2026-09-08
- **Task:** T-05
- **Bin:** 2
- **Claim:** A namespace built to expose "only builtins, `json`, `re`, and the
  `Graph`/`Node` types" passed the process's real `__builtins__` module through
  unfiltered. The `ast` import gate rejected `import os` and nothing else, so a verifier
  reached the filesystem and the shell on the next line via `__import__('os')`, `open()`
  or a nested `eval`. A reviewer demonstrated the end state: a verifier that clears the
  tautology gate, runs `os.system('echo pwned > marker')`, and returns a value matching
  its expected JSON comes back `VerifierResult(status='pass', actual=None, error=None)`
  with the marker written to disk.
- **Sightings:** 1 as stated. **As the false-success family, 3** — see below.
- **Action:** fixed in PR #5 by replacing the passthrough with an explicit ~26-name
  allow-list, proven red against the pre-fix code. Dispatching `control-author` on the
  family's third sighting; see the note there.
- **Notes:** The failure direction is the whole point. Arbitrary code execution is bad;
  arbitrary code execution *recorded in the ledger as a confirmed claim* is worse,
  because the ledger's entire premise is that a row you can read is a row something
  checked. This is the third member of the false-success family after `F-4` (config
  truthiness) and `F-10` (the graph seam's silent wrong answers), and `F-10` set the
  condition explicitly: "one more and it earns a decision."
  Two things are worth separating. The *code* was in-spec — T-05's Non-scope says "do
  not sandbox beyond the import gate; that is the phase-1.5 behavioral agent's job," and
  the builder implemented exactly that. The *spec* was the defect: Scope's phrase
  "exposes only builtins" plainly meant a restricted namespace and was implemented as
  the literal builtins module, which made the import gate decorative. That is a planning
  finding, and it is the fourth in this project after `F-1`, T-03's "seven fields" and
  `F-11`. **Planning defects remain the most common kind here and the loop still has no
  stage that reads a task file critically before a builder is dispatched.**
  The fix is an improvement, not a solution, and the PR says so: attribute-traversal
  escapes (`().__class__.__bases__[0].__subclasses__()`, or reaching a live module
  through `__globals__`) need no builtins at all and remain open. Both reviewers
  independently executed that route to full `os.system` and confirmed it. It is pinned
  by a test explicitly labelled as documenting a limitation rather than asserting
  correct behaviour, and deferred to phase 1.5.

### F-14 — harness: the orchestrator's brief became governance text that nobody checked

- **Date:** 2026-09-08
- **Task:** T-05
- **Bin:** unbinned harness finding
- **Claim:** DEC-1 shipped claiming the import gate "protects a standing line in
  `AGENTS.md`: 'Never run the target's own code.'" That sentence was false, and it came
  near-verbatim from the orchestrator's dispatch brief to `control-author`. The agent
  wrote the orchestrator's framing into a governance artifact without testing it, though
  testing it was ten minutes' work — which is exactly what the boundary reviewer then
  did, from the same tree, and disproved it immediately.
- **Sightings:** 1
- **Action:** soft — corrected in PR #5, twice: first to state the real containment, then
  again when the code reviewer proved the residual gap was arbitrary code execution
  rather than the introspection the wording implied. No control.
- **Notes:** A decision is the most durable artifact this repo produces. Prose in a task
  file gets superseded; a decision is what agents read as true, forever, and the whole
  design rests on the view being trustworthy. So a false claim in a decision is a
  strictly worse outcome than the same false claim in code, and this one was introduced
  by the role that is supposed to be judging, not producing.
  The mechanism generalises past this instance: **`control-author` verified its control
  by execution and its decision's prose not at all.** It planted a violation, proved the
  control went red, proved it went green again — genuinely good work — and then wrote an
  untested security claim two paragraphs above. Nothing in the loop checks that a
  decision's Context and Consequences are true; the boundary reviewer only caught it
  because the orchestrator happened to ask it to audit DEC-1 specifically. That is luck,
  not procedure, and it is the same shape as `F-2`, `F-6` and `F-9`: a correct outcome
  reached by a route the harness does not require.
  The cheap fix is one line in the `control-author` brief: any factual claim about what
  the control or the code contains must be verified the same way the control itself is,
  or stated as an open question. Worth doing before the next decision is authored.

### F-15 — harness: the orchestrator's ambiguity rulings are the least-reviewed input in the loop

- **Date:** 2026-09-08
- **Task:** T-05
- **Bin:** unbinned harness finding
- **Claim:** Three of the defects found on this task trace to the orchestrator's own
  wording rather than to the builder's judgement. (1) Ruling that the canonical pass
  should sort every list, when the task said "lists sorted **where they were sets**" —
  which made an order-dependent claim pass regardless of order, a false success.
  (2) Instructing that "a graph call" with a non-literal argument fail closed, when only
  `graph.node(...)` is ambiguous — which made the tautology gate reject legitimate
  two-step verifiers. (3) The DEC-1 containment sentence recorded as `F-14`.
- **Sightings:** 2 — second sighting `F-23` (T-06), two occurrences counted once.
- **Action:** soft — all three found by review and fixed within the task. No control; this
  is a fact about how briefs are written, with nothing in the repo for a script to
  inspect.
- **Notes:** The orchestrate skill is built on the premise that the orchestrator forms
  its own view rather than relaying, and that premise held where it mattered — the
  builder's "S102 is the only remaining failure" was checked and found false, and the
  boundary reviewer's blocking finding was re-executed before being accepted. But the
  orchestrator's *own* output enters the loop unreviewed. A builder receives a ruling on
  an ambiguity and implements it faithfully; no stage asks whether the ruling was right.
  Here that cost two review rounds.
  What makes it tractable rather than just a caution: in all three cases the task file
  already contained the correct answer, and the ruling drifted from it. "Lists sorted
  where they were sets" is unambiguous on re-reading. The failure was paraphrasing a
  spec instead of quoting it. A cheap discipline follows — when ruling on an ambiguity,
  quote the task's own words in the brief and rule *around* them rather than replacing
  them, so the builder can see the original and push back. Worth trying on the next task
  before proposing anything heavier.

### F-16 — Bin 1: three type errors hid behind a fail-fast gate for a whole round

- **Date:** 2026-09-08
- **Task:** T-05
- **Bin:** 1
- **Claim:** The builder reported ruff's `S102` as "the only remaining failure" when
  `make check` stopped there. Three `ty` errors in its own test file were sitting behind
  it, invisible because the gate fails fast and `ty` never ran. The orchestrator acted on
  the report as though it were exhaustive.
- **Sightings:** 1
- **Action:** soft — fixed in the first fix round. No new control: `ty` already catches
  this and did, the moment it was allowed to run. `AGENTS.md` already warns that
  `make check` reports only the earliest failing stage.
- **Notes:** Bin 1 by construction — the tooling worked perfectly and the reporting
  around it did not. Logged because the interesting part is not the type errors but the
  claim: an agent converted "the stages after this one did not run" into "this is the
  only failure," and the orchestrator believed it. The correction was cheap here and was
  put into the next fix-round brief. Worth watching whether agents in this loop
  habitually describe truncated pipelines as complete results, since that class of
  overclaim is not specific to `make check`.

- **Update, 2026-09-08 (T-05): F-9 is closed.** The remedy proposed at F-9's first
  sighting and re-proposed at its second — a regression test for a fix must be proven to
  fail against the unfixed code, by a genuine detached checkout — was written into the
  builder's dispatch brief **once, as a standing requirement covering every fix round**,
  rather than per-item as on T-04. It held for all three fix rounds and eight regression
  tests, including the items that looked too small to need it. The builder also correctly
  avoided both traps the ledger had already recorded: no bare `git stash` (`F-6`), and no
  `git checkout <sha> -- .` (recorded on T-04, where the overlay leaves later-added files
  in place and can turn a red green). Three sightings of the problem, one of the fix
  working, and the fix now lives in the procedure rather than in this log. Like `F-2`,
  no control is possible — this is a fact about how a subagent is briefed at runtime,
  which leaves nothing in the repo for a script to inspect. It gets written into the
  brief or it gets forgotten.

- **Update, 2026-09-08 (T-05): F-2 held a sixth time, now from the skill rather than the
  log.** Boundary reviewer in its own detached checkout, advanced with `git checkout
  --detach` across three review rounds; code reviewer in the builder's worktree. Both
  planted and reverted payloads — including live `os.system` calls that wrote marker
  files — and neither saw the other's. On round 1 they converged independently on the
  same blocking finding from different angles: the boundary reviewer proved the namespace
  was open, the code reviewer proved it returned `pass`. That second half is what made it
  a blocker rather than a caution, and a single contaminated tree would not have produced
  it. First task where the orchestrator did this from the skill's own instructions rather
  than by reading this log, which was the point of closing it.

- **Update, 2026-09-08: the false-success family (F-4, F-10, F-13) reached three
  sightings and was evaluated for a control, deliberately not given one.**
  `control-author` checked each candidate mechanism concretely rather than in the
  abstract: the F-13 namespace-passthrough fix on the T-05 branch is already pinned by a
  runtime regression test in `tests/test_verify.py` that plants
  `__import__('os').system(...)` and proves it fails — a static control on top would be
  weaker than what exists, since an `ast` check on "does the exec call use
  `_ALLOWED_BUILTINS`" cannot tell whether that dict still contains a dangerous name,
  and the runtime test can (Bin 1, already covered). The F-10 `DISTINCT` fix in
  `src/seshat/graph.py` was re-checked directly and is clean — every query joining
  `edges` carries `DISTINCT`, and `search()` correctly does not, joining `nodes_fts` 1:1
  — but the mechanism has exactly one sighting of its own, not three. Writing a control
  for it now would manufacture a count the rule of three exists to prevent. No single
  mechanism inside the family has recurred three times; only the *direction* is shared —
  a false success reported silently, indistinguishable from a true one — and that
  direction is "never return a confidently wrong answer," which F-10's own note already
  said must never be attempted as a control. Refusal, not coverage, is the recorded
  outcome. The `DISTINCT`-on-edge-join check remains a live candidate for a future task
  if it resurfaces in a second unrelated file or task.
  **The orchestrator's note:** this is the first time the rule of three fired and
  produced nothing, and that is the harness working rather than failing. The falsifiable
  test at the top of this file says to judge the experiment by whether Bin 2 stays fat
  and review burden shrinks, explicitly not by whether CI goes red. A graduation step
  that can return "no control, here is why" is what stops the rule of three from
  degenerating into a quota.

### F-17 — a library's retry default silently multiplied a "one shot" contract by ten

- **Date:** 2026-09-08
- **Task:** T-07
- **Bin:** 2
- **Claim:** Where a design fixes the number of model calls, the strategy object is
  constructed with that number stated explicitly rather than left at the library's
  default. `VerifierAuthor.author` was declared one-shot by design (task §Non-scope,
  decisions Q27) and documented as such in its own module docstring, but
  `nooa.PredictStrategy` defaults to `max_retries=10` and nothing constrained it. A
  malformed response produced ten model calls before raising. `author_with_retry`'s
  own one-retry budget — the entire retry contract the task specifies — sat on top of
  a hidden loop an order of magnitude larger.
- **Sightings:** 1
- **Action:** soft — fixed in T-07 (PR #6) with
  `PredictStrategy(config=PredictConfig(max_retries=1))` and a test pinning
  `call_count == 1` on a malformed response. No control.
- **Notes:** The acceptance tests could not have caught this and were not at fault. The
  task's four required cases include a "bad response" scenario, but the bad response it
  specifies (source missing `def check(`) still parses and validates cleanly, so the
  library's retry loop never engaged. The defect lived in the gap between "invalid to
  us" and "invalid to the library" — a distinction the task file had no reason to
  anticipate. Found only because a reviewer fed a genuinely unparseable response
  directly to the generation method rather than through the tested path.
  Three more generation-point agents are planned (worker, reflection, answer) and each
  will construct a strategy. If a second one ships with an unstated retry budget this
  becomes a strong Bin 2 with an obvious checkable form: every `*Strategy(...)`
  construction under `src/seshat/agents/` names its `max_retries`. Worth noting the
  failure direction — the budget silently *widens*, so the symptom is cost and latency,
  not an error, and nothing goes red.

### F-18 — a textual check standing in for a structural one, in the guard whose job is to trigger the retry

- **Date:** 2026-09-08
- **Task:** T-07
- **Bin:** 2
- **Claim:** A check on generated code parses it rather than matching a substring of it.
  `_has_check_entry_point` tested `'def check(' in source`, which returns `True` for
  `"# TODO: implement def check(graph)\ndef not_check(graph): return 1"` — source with
  no entry point at all. The guard exists solely to reject a bad spec and trigger the
  one retry with feedback; a false pass wastes the retry, and the failure surfaces two
  stages later in T-05's runner, far from the model call that caused it.
- **Sightings:** 1
- **Action:** soft — fixed in T-07 (PR #6) with an `ast.parse` walk that fails closed on
  `SyntaxError`. No control.
- **Notes:** Related to the false-success family (`F-4`, `F-10`, `F-13`) by direction —
  a validator reporting success on input it did not actually validate — but the
  mechanism is its own: text matching used where structure is meant. That mechanism is
  checkable in a way the family's shared direction is not, which is why it is logged
  separately rather than folded in as a fourth sighting of a family whose graduation was
  already deliberately refused. Padding that count would be the failure mode the refusal
  note warned about.
  Worth recording that this one did *not* reach the ledger: T-05's runner rejects the
  same source structurally, so no unverified claim could have been promoted. The cost
  was a wasted generation and a diagnostic that points at the wrong stage.

### F-19 — a tool diagnostic suppressed repo-wide to cover code that does not exist yet

- **Date:** 2026-09-08
- **Task:** T-07
- **Bin:** 2
- **Claim:** A suppression is scoped to the code that actually triggers the diagnostic.
  `ty` reports a NOOA generation point's `...` body as an implicit `None` return against
  its annotation. The fix landed as a repo-wide `[tool.ty.rules] empty-body = "ignore"`,
  justified by the three further generation-point agents that will hit the same
  diagnostic when they are written. Repo-wide suppression to pre-cover unwritten code
  silences the diagnostic for every genuinely stubbed function under `src/` for the life
  of the project.
- **Sightings:** 1
- **Action:** soft — narrowed in T-07 (PR #6) to a `[[tool.ty.overrides]]` block scoped
  to the one file that currently trips it, mirroring how DEC-1's own ruff `S102` ignore
  is scoped per-file. No control.
- **Notes:** The builder's reasoning that this is tooling config rather than a governed
  control was correct and I accepted it: nothing in `pyproject.toml` is covered by a
  `pragma: external` content hash, and no control under `controls/` reads `.toml`. This
  is not control evasion and should not be recorded as such. It is a scope judgement,
  and the boundary reviewer settled it by execution rather than argument — it wrote the
  narrower override, proved `ty check src/` still passed, then planted an empty-body
  defect in `src/seshat/ledger/models.py` and proved the narrowed version still caught
  it. That is the difference between a reviewer's preference and a reviewer's finding.
  A control here would be brittle (judging whether a suppression is "too broad" needs to
  know what code exists) and none is proposed. The general lesson — suppress what fails,
  not what might — is closer to Bin 3 than the specific claim above.

- **Update, 2026-09-08 (T-07): F-8 second sighting, now in code rather than in docs.**
  `_has_check_entry_point` in `src/seshat/agents/verifier_author.py` and
  `_find_check_function` in `src/seshat/verify.py` both define "what counts as a valid
  `check` entry point". The duplication is deliberate and mine: DEC-1 confines `exec`
  to `verify.py`, and I judged that importing it into the agent to save five lines
  widens that module's reach into the agent's import graph for no good reason. The
  contract then drifted twice inside a single task — the agent's copy accepted
  `async def check(graph)` where the runner always rejects it (a spec passing validation
  then failing a stage later), and rejected `def check(graph, extra=1)` where the runner
  accepts and runs it (a valid verifier discarded, burning the one-shot budget). Both
  were found only because a reviewer was asked to try to defeat the new predicate rather
  than to read it, and both were aligned to the runner as the authority.
  Second sighting of F-8's claim: a contract stated in more than one place, drifting.
  The first was five prose statements of the citation contract; this is two predicate
  functions. F-8's note said a checkable form was worth writing at the second sighting,
  and a specific one exists here — the builder proposed it when asked for judgement
  rather than compliance: one shared table of `(source, expected)` cases below both
  modules, plus a single test asserting the two predicates agree pairwise over it. It
  crosses no DEC-1 boundary, since `_find_check_function` is a pure `ast` reader
  containing no `exec` or `eval`.
  **Not implemented, and deliberately not folded into PR #6** — it is outside T-07's
  declared `files` and lands in T-05's already-merged test area, so it is a planning
  finding for the human, not a fix round. Both reviewers agreed with that call.
  Note also what this is *not*: a control. The remedy is a test, and F-8 was right that
  the general form — every contract stated once — is not machine-checkable and should
  never be attempted. Third sighting is the one to watch, and by then the specific
  remedy should already be in place.
  One thing the aligned predicates now agree on and both get wrong: `def check(a, b)`
  passes validation and would raise `TypeError` when the runner calls `check(graph)`.
  Agreement on a gap is not the same defect as drift, and matching the authority was the
  right call for T-07; the gap belongs to `verify.py` and is logged here rather than
  fixed on this branch.

- **Update, 2026-09-08 (T-07): F-2, seventh holding — and the first contamination in the
  opposite direction.** The two-tree split held again across three review rounds: both
  reviewers planted and reverted deliberate defects (planted `eval` against DEC-1's
  control, a planted empty-body defect against the narrowed `ty` override) and neither
  saw the other's. But during fix round 1 the **builder** used the boundary reviewer's
  detached checkout as scratch for its red proof — copied its new test file in at
  `21d94ce`, ran it, restored the tree. It was restored correctly; I verified
  `git status --porcelain` empty and the SHA unchanged before advancing that tree, and
  the boundary reviewer independently reconciled its own earlier test counts
  (167 at `21d94ce`, +4 committed regression tests, 173 after round 2) and confirmed
  nothing it had concluded could have been affected.
  Every prior sighting of F-2 was a *reviewer* contaminating a tree. This is a builder
  doing it, and the builder's brief says nothing about where a red proof may be staged —
  only that it must be a genuine detached checkout, which the reviewer's tree
  technically was. The brief that closed F-9 specified the *method* and left the
  *location* open. Told the builder directly in fix round 2 to create its own; it did,
  and removed it after. This costs one line in the builder brief — "create your own
  detached checkout for a red proof; never write into a tree a reviewer is reading" —
  and that line should go into the skill alongside the F-9 remedy it sits next to, since
  both are facts about how a subagent is briefed at runtime and neither leaves anything
  in the repo for a control to inspect.
  No harm done this time, which is exactly what `F-2` and `F-6` both warned about: a
  correct outcome is not evidence the method was sound.

### Planning findings from T-07

- **Plan §6 lists nine `Graph` methods; `src/seshat/graph.py` has eleven.** `nodes(kinds)`
  and `inbound_call_count(qualified_name)` exist in the code and appear nowhere in §6.
  The builder found this while quoting the nine into the prompt docstring as the task
  requires, reported it rather than silently picking one, and left the docstring as the
  task specified. For the human: either §6 is stale and should gain the two, or the two
  are deliberately not part of the verifier-facing surface and §6 should say so. The
  prompt currently offers a 27B model nine of the eleven ways to read the graph, which
  may well be the right call — but it is currently an accident, not a decision.
  Adjacent to `F-1` (a symbol named in acceptance criteria that the code does not
  define) but the inverse: code the spec does not name. Logged once, not counted as an
  `F-1` sighting.
- **No live model call has exercised the prompt.** `LLM_HOST` is unset in this
  environment, so the integration test skips and the hermetic suite proves only that the
  prompt reaches the client and the plumbing round-trips. Whether a 27B model actually
  returns a usable verifier from this docstring is untested, and that is the one thing
  the task's acceptance criteria cannot measure. Carried to T-13's smoke test; noted
  here because "all acceptance criteria pass" reads stronger than the evidence supports.

### F-20 — a status write that could not write the field the status is derived from

- **Date:** 2026-09-09
- **Task:** T-06
- **Bin:** 2
- **Claim:** A unit's `vanished` status is derived from `ast_hash is None`, but the call
  used to set it, `Ledger.set_unit_status`, cannot write the `ast_hash` column at all.
  The row therefore kept its last real hash cached while claiming to be vanished. Restore
  a briefly-unparseable file byte-for-byte — or let a node return to the graph unchanged —
  and the next sync compares the real hash against that identical cached value, reports
  `unchanged`, and leaves `status='vanished'` permanently. The unit is invisible to
  `build_queue` forever with no path back. Fixed by building the row from the prior one
  and upserting `ast_hash=None`, so any real hash compares unequal and recovery always
  lands in `changed`.
- **Sightings:** **2.** It occurred in two branches of one function, but that is one cause
  in one task, so it counts once — see the same-batch rule. **Second sighting 2026-09-09,
  T-08:** `Ledger.set_claim_status` could not write `retries` at all, so a claim moved to
  `refuted` after a retry could not record that a retry had happened — the same shape one
  column over, in the same method, found by `task-critic` before dispatch this time rather
  than by a reviewer after code existed. Fixed in PR #8 by giving the method a
  `retries: int | None = None` parameter. At a third sighting this is a serious graduation
  candidate: the claim is narrow, structural, and a machine could plausibly check it.
- **Action:** soft — both branches fixed in PR #7, each pinned by a test proven red first.
  No control.
- **Notes:** The checkable claim is narrower than the family it belongs to and worth
  stating on its own: **a write that sets a status must also write every field that
  status is derived from, or the row can assert something the data contradicts.** That is
  structural and a machine could check it, unlike "never return a confidently wrong
  answer," which `F-10` already ruled out as a control. Logged as its own mechanism at one
  sighting rather than as a fourth member of the false-success family, whose graduation
  was deliberately refused on 2026-09-08 precisely because no single mechanism inside it
  had recurred three times. Padding that count is the failure mode the refusal exists to
  prevent, and the same reasoning `F-18` used to stay separate applies here.
  Worth flagging for whoever fixes the follow-up: `Ledger.upsert_unit` unconditionally
  stamps `last_seen_run=run_id` with no way to opt out, which is the same shape of defect
  one level down — an API that forces a write the caller does not mean. It is why a
  vanished unit is now recorded as seen in a run that did not see it, an accepted and
  documented trade in PR #7. A `store.py` task that gives `upsert_unit` an opt-out closes
  both. If that lands and the pattern shows up in a third unrelated place, this becomes a
  serious graduation candidate.

### F-21 — harness: two reviewers cleared a defect by reading that one test then caught

- **Date:** 2026-09-09
- **Task:** T-06
- **Bin:** unbinned harness finding
- **Claim:** `F-20`'s defect survived review twice, in the two different ways review can
  fail. First: the code reviewer traced the recovery path by hand, concluded a
  transiently-unreadable file recovers correctly, and noted only that nothing pinned it.
  Asked to write that test, the builder found it went **red** — the hand-trace had reached
  the opposite of the truth. Second: after that fix, the boundary reviewer scored the
  delta 5/5 with zero findings and explicitly called the fix "minimal and correct" for
  deliberately not touching the sibling branch. The code reviewer then wrote a test
  against that untouched branch and found the identical permanent-stuck bug still live.
  Both misses came from reading; both catches came from executing.
- **Sightings:** **2.** **Second sighting 2026-09-09, T-08:** asked to re-review the fix
  round, the boundary reviewer resolved one of the three deltas — the regression test for
  `set_claim_status(retries=None)` — without running the mutation, writing that it "did not
  need to re-run the mutation myself" because the test's assertion "directly encodes the
  exact contract." That reasoning is correct, and it is still a hand-trace standing in for
  an execution. It cost nothing here only because the code reviewer, in its own tree and
  under an explicit instruction to re-plant it, did run the mutation and confirmed the red.
  The pattern holds: reviewers reach for reading whenever the reading looks conclusive, and
  the reading looks conclusive most often precisely when a test is short.
- **Action:** soft — noted. Both defects fixed inside PR #7 with red proofs. No control;
  this is about how the loop is run, not about code.
- **Notes:** Both reviewer briefs in this repo already say "verify by execution, not by
  reading," and both reviewers do plant-and-revert defects diligently — they did so here,
  repeatedly and well. The gap is narrower: they execute against the code that **is**
  there and reason about the code that is **not**. A branch nobody wrote a test for gets
  read, and a reviewer's own hand-trace is the least-tested artifact in the loop, because
  nothing checks it the way a planted mutation checks an assertion.
  The cheap intervention is already proven and cost one sentence: when a reviewer reports
  a property it verified by tracing rather than by running, the orchestrator asks for the
  test. That is exactly what produced both catches here, and the second one only happened
  because the first had made the question worth asking again. Recording it because "the
  reviewers approved it" was true twice about code with a permanent false-success bug in
  it, and the only thing that separated the approvals from the truth was whether someone
  ran it.

### F-22 — an acceptance criterion that was logically unsatisfiable

- **Date:** 2026-09-09
- **Task:** T-06
- **Bin:** 2
- **Claim:** T-06's acceptance required that editing a function body leave "that unit
  alone" in `changed`. The same task file specifies that a `module` unit hashes the whole
  file, and a class's `ast.dump` necessarily contains its nested methods, so the enclosing
  class and module hashes genuinely change too. Satisfying the criterion as written would
  have required reporting those ancestors as `unchanged` — a false "nothing changed", the
  exact failure this module exists to prevent. The criterion was unsatisfiable against its
  own task file, not merely awkward.
- **Sightings:** 1 for this mechanism. **As a planning defect, the fifth** — after `F-1`,
  T-03's "seven fields", `F-11`, and `F-13`'s spec/code split.
- **Action:** soft — the human corrected the criterion on `develop` in `1ca3e91` before
  the fix round ran. The builder flagged it and stopped rather than quietly narrowing the
  test, which is the contract working as written.
- **Notes:** The checkable claim: **a task file must not state an acceptance criterion its
  own scope section contradicts.** Both halves were in the same file, twelve lines apart.
  A machine cannot check the general case, but a reviewer reading the task file before
  dispatch would have caught this one in a minute — which is `F-13`'s standing observation,
  now on its fifth instance: *planning defects remain the most common kind of finding in
  this project, and the loop still has no stage that reads a task file critically before a
  builder is dispatched.* Five sightings of a gap in the loop's shape is a stronger signal
  than most Bin 2 code patterns carry, and the rule of three does not apply cleanly because
  the fix is a loop stage, not a control. Recommending it to the human as a change to
  `orchestrate`: a cheap pre-dispatch read of the task file against itself.
  Worth noting what did work: the builder reported the contradiction instead of rewriting
  the test, both reviewers independently reached the same conclusion, and the corrected
  criterion is now **stricter** than the one it replaced — it pins that an untouched
  sibling stays `unchanged`, which the original never asked for.

### F-23 — harness: the orchestrator's fix-shape suggestion would have shipped a test that could not fail

- **Date:** 2026-09-09
- **Task:** T-06
- **Bin:** unbinned harness finding
- **Claim:** Second and third sightings of `F-15`. Twice in one task the orchestrator
  handed the builder an instruction that was wrong, and twice the builder caught it rather
  than complying. (1) The orchestrator specified pinning a unit's status as `'scanned'` in
  a regression test — the same literal the mutation it was meant to catch hard-codes, so
  the test would have passed with the bug in place, unable to distinguish "preserved" from
  "stomped to the same value". The builder switched the pinned status to `'changed'` and
  proved the mutation red. (2) The orchestrator asserted that `last_seen_run` should not be
  bumped for a node nothing saw this run; `upsert_unit` stamps it unconditionally with no
  opt-out, so the only way to comply was `set_unit_status` — the very call that causes
  `F-20`. The builder took the correct `ast_hash` instead and said plainly why.
- **Sightings:** 1 as stated. **As `F-15`, 2** — both occurrences are one task and one
  cause, so they count once under the same-batch rule.
- **Action:** soft — noted. Both instructions were overruled correctly before any code was
  written; nothing shipped.
- **Notes:** `F-15` recorded that orchestrator rulings are the least-reviewed input in the
  loop: builder and reviewer output both get checked by something, and the orchestrator's
  own reasoning gets checked by nothing. This is that, sharpened — instruction (1) would
  have produced a *green test that could never fail*, which is the false-success direction
  arriving through the harness rather than through the code, and no reviewer would have
  caught it because a passing test that pins the wrong literal looks exactly like a passing
  test.
  What saved it both times was a builder willing to say "your fix shape is wrong, here is
  why," which is not a property the harness enforces anywhere. The brief that produced it
  asked for reasons and evidence rather than compliance, and both refusals came back with
  the constraint quoted from `store.py`. Worth keeping that framing in builder briefs
  deliberately rather than by luck. At `F-15`'s third independent sighting this stops being
  an anecdote about one session's mistakes and becomes an argument for a structural check
  on orchestrator instructions.

### F-24 — five task-file defects in one task, caught before a builder existed

- **Date:** 2026-09-09
- **Task:** T-10
- **Bin:** 2
- **Claim:** Every symbol a task's scope and acceptance name either exists in a dependency
  that is `done`, or is defined by the task itself with enough detail to assert on. T-10
  broke this five ways: (1) `ReflectionSummary` is the return type of the task's central
  function and the subject of an acceptance bullet, but no section declares a single field
  of it; (2) scope §3's "drops any evidence id that is not in the batch and not
  `confirmed`" reads two ways and every acceptance bullet passes under both; (3) scope §5
  requires conforming to T-09's `after_scan(ledger, run)`, and `after_scan` appears nowhere
  in `src/` — only in the prose of two `todo` task files; (4) `files:` omits
  `src/seshat/ledger/store.py` although `set_candidate` is confirmed absent and
  `flag_candidates` cannot be written without it; (5) `depends_on: [T-03]` declared neither
  the T-09 coupling that §5 creates nor T-08.
- **Sightings:** **2** for the multi-defect shape. **As a planning defect, the seventh** —
  after `F-1`, `F-11`, `F-22` and the two the ledger already counts there. **Second
  sighting 2026-09-09, T-08:** the critic returned five findings against T-08 too — a
  ledger column with no typed writer (`F-20`), an inverted external-tool claim (`F-25`),
  an acceptance criterion nothing could falsify, an ambiguous identifier rule where only
  one reading satisfied acceptance, and a return type with no declared owning module.
  Counted as a second sighting of the same shape rather than a new finding: T-08 and T-10
  come from one plan and one planner, which is one cause, per the same-batch rule.
- **Action:** soft — the human decided on `develop` in `8c6e478`: `depends_on` widened to
  `[T-03, T-08, T-09]`, and scope §3 rewritten to batch-membership-only with the redundant
  clause deleted and the absence of a ledger-wide lookup stated. Defects (1) and (4) were
  explicitly left open by the human's call; they must be resolved before T-10 dispatches.
  No control.
  **Closed 2026-09-10, at T-10 dispatch.** A second critic run confirmed both were still
  open against the merged tree — `set_candidate` genuinely absent after T-03, T-08 and
  T-09 all landed — and the human resolved them: `ReflectionSummary` pinned to exactly
  four named int fields, and `src/seshat/ledger/store.py` added to `files:`. See `F-34`
  for what the deferral actually cost.
- **Notes:** The first planning defect this project caught *before* a builder existed. The
  previous five were all found after code was written against them — `F-22` cost a full
  review round and a human correction mid-task, `F-1` corrupted two task files that had
  already shipped acceptance criteria asserting on a class the fixture never defines. The
  `task-critic` stage was added to `orchestrate` as the recommendation recorded under
  `F-22`; this is its first run against a task it had not already seen fixed, and it
  returned five findings for roughly two minutes of reading. That is the cheapest defect
  removal in the log so far.
  Worth being honest about what it does not settle: a pre-dispatch reader is a *soft*
  layer, not a control. It found (3) by grepping `src/` for a symbol the task named, which
  a script could do — a candidate for the same automation `F-1` floated and nobody built.
  Defect (2), the ambiguity, is the one no script would ever catch: both readings are
  coherent English and both satisfy the acceptance list. That is the class this harness
  exists for, and it is also the class that stays in Bin 2 forever.
  Watch the direction of the human's ruling on (1) and (4). Leaving `ReflectionSummary`
  unspecified means whichever builder eventually runs T-10 invents the field names and
  writes an acceptance test against its own invention — the F-23 failure mode, a green
  test that pins whatever the code happened to do. If T-10 dispatches with that still open,
  expect it back as a review finding.

### F-25 — a task file claimed an external tool's behaviour was "verified" and had it backwards

- **Date:** 2026-09-09
- **Task:** T-08
- **Bin:** 2
- **Claim:** T-08's scope specified `CODEGRAPH_MCP_TOOLS=node,callers,callees,search,impact`
  and said, in the same bullet, that codegraph 1.6.0 "lists `codegraph_explore` alone by
  default; that env var **adds** the five named above (verified against the installed
  binary)." The parenthetical is false and the mechanism is inverted: the env var
  *replaces* the default allowlist rather than extending it. Under the value the task
  prescribed, `codegraph_explore` is absent from the tool list entirely — so the next
  clause of the same bullet, "tell the model in the prompt to call `codegraph_explore`
  first," instructed the worker to call a tool its own configuration had removed. The
  `task-critic` caught it by starting the binary and sending `tools/list`; the
  orchestrator re-ran the probe both ways before taking it to the human, and confirmed
  five tools without `explore` and six with it.
- **Sightings:** 1.
- **Action:** soft — the human chose to add `explore` to the list; corrected on `develop`
  in `b919caf`, with the replace-not-extend mechanism written into the task so the next
  reader cannot re-lose it. No control.
- **Notes:** The checkable claim: **a task file that says a fact was "verified" must name
  how, or the word is decoration.** This is a different failure from `F-24`'s five, which
  were omissions and ambiguities — nobody had asserted those either way. Here a specific,
  falsifiable, empirically-checkable claim was written down as already-checked and was
  wrong, which is strictly worse: the word "verified" is exactly what stops the next
  reader from checking. It survived into a dispatched task file because no stage before
  `task-critic` existed to run the one command that refutes it.
  A machine cannot check the general case, but the narrow case is automatable and cheap:
  any task-file claim about an installed tool's observable behaviour can be turned into a
  command. That is the same automation `F-1` floated and `F-24` floated again, now on its
  third mention with nobody having built it. Worth noting the failure direction — an
  agent told to call an unavailable tool does not crash; it improvises, and the run
  degrades quietly. Nothing in the acceptance criteria would have caught it, because the
  MCP attachment is live-only and the hermetic suite never exercises it.

### F-26 — a mutation survived forty-nine tests, and only mutation testing found the gap

- **Date:** 2026-09-09
- **Task:** T-08
- **Bin:** 2
- **Claim:** T-08 extended `Ledger.set_claim_status` with `retries: int | None = None`,
  contracted to leave the column untouched when `None`. The implementation was correct.
  The code reviewer mutated it so `None` wrote `0` instead, and the mutation passed the
  entire relevant suite — 49 tests across `tests/ledger/test_store.py`,
  `test_store_fixes.py` and `tests/agents/test_worker.py` — with nothing going red. New
  behaviour had shipped with no test able to distinguish it from a regression.
- **Sightings:** 1 for this mechanism.
- **Action:** soft — fixed in PR #8 by `c45adad`, a test that sets `retries=1`, calls
  `set_claim_status` with no `retries` kwarg, and asserts the column is still `1`. Both
  the builder and the code reviewer independently re-planted the mutation and confirmed
  `AssertionError: assert 0 == 1`. No control.
- **Notes:** The checkable claim: **a new optional parameter whose contract is "does
  nothing when omitted" needs a test that fails when it does something.** A default-valued
  parameter is the easy case to leave untested precisely because omitting it is what every
  existing caller already does — the suite exercises that path constantly and asserts
  nothing about it, so full green says only that nothing crashed.
  What is worth recording is the method, not the defect. `F-21` logged that this project's
  reviewers miss things by reading and catch things by executing; this is the sharper
  version — the reviewer executed the *suite*, which was green, and learned nothing. Only
  mutating the implementation and re-running told it anything. Mutation testing was used
  here because the brief demanded it per-criterion, and it earned its cost on the first
  criterion it touched. The same round also confirmed the reverse: mutations against the
  token-accounting rewrite (constant return, fixed increment, no-op middleware) all went
  correctly red, so the acceptance test that `F-24`-adjacent review had flagged as
  unfalsifiable is now demonstrably falsifiable.

### F-27 — test scaffolding installed on the production path, defeating a framework type check

- **Date:** 2026-09-09
- **Task:** T-08
- **Bin:** 2
- **Claim:** To satisfy an acceptance criterion requiring a real token count, the builder
  wrapped the LLM client in `_CountingLLM`, a duck-typed proxy installed by overriding
  `Worker.set_llm` — for every client, production included, not only test doubles. It
  justified this by checking that NOOA's `set_llm` and the runtime's `_llm` lookup do no
  `isinstance` check. That check was true and insufficient:
  `nooa/runtime/actor.py:197` `_resolve_provider_formatter`, called on every render, does
  `isinstance(llm_client, ResponsesClient)` to choose the wire-format formatter. A wrapped
  client is a different class, so that branch is always `False` and the runtime silently
  falls back to the default formatter. Inert today — `config.py` only builds
  `CompletionClient` — but point any of the four generation points at a Responses-API
  client and it sends the wrong wire format with no exception raised.
- **Sightings:** 1 for this mechanism. Belongs to the false-success family (`F-4`, `F-10`,
  `F-13`) by direction, and is logged separately for the same reason `F-18` and `F-20`
  were: the family's graduation was refused on 2026-09-08 because no single mechanism in
  it had recurred three times, and padding that count is the failure the refusal exists to
  prevent.
- **Action:** soft — fixed in PR #8 by `372f427`. The wrapper is gone; token accounting is
  now an `llm_call` middleware handler that observes `ctx.response.usage` after
  `await nxt(ctx)` and never replaces the client. Pinned by a test that builds a `Worker`
  around a real `ResponsesClient` and asserts NOOA's own `_resolve_provider_formatter`
  returns a `ResponsesProviderFormatter`. No control.
- **Notes:** The checkable claim: **a mechanism that exists to make something testable
  must not sit on the path the production object travels.** The tell is generic — a proxy,
  a subclass, or a monkeypatch installed unconditionally in a constructor, where the
  motivation named in the docstring is observation. Observation has a supported seam in
  most frameworks (here, middleware); substitution does not.
  Two things are worth keeping. First, the builder's docstring asserted the wrapper "stands
  in for the real client everywhere the runtime touches it" — a universal claim resting on
  two call sites it had actually read. The defect lived in the third. Second, the fix was
  found by *not* prescribing one: the orchestrator forwarded the finding with the evidence
  and explicitly refused to name a mechanism, having twice before specified fix shapes that
  were wrong (`F-23`). The builder chose middleware over the `__class__`-proxying hack the
  reviewer had suggested, and while inside it found a second defect nobody had reported —
  the token meter reset on `set_llm` rather than per turn, so `tokens_used` accumulated
  across a Worker's whole lifetime. A prescribed one-line fix would have shipped that.

### F-28 — open: a second unguarded read on the same crash path, in a module the task did not own

- **Date:** 2026-09-09
- **Task:** T-08
- **Bin:** 2
- **Claim:** `_read_span` in `worker.py` caught only `OSError`, so a non-UTF-8 source file
  crashed a worker turn with an uncaught `UnicodeDecodeError`. Fixed. But proving that fix
  red, the builder found `Graph.decorators()` (`src/seshat/graph.py:253`) reaches the same
  crash by a second route: its ast-fallback branch calls `source_path.read_text()` with no
  guard at all, and `unit_brief()` calls it unconditionally. The orchestrator confirmed the
  unguarded read and noted `ast.parse` on the following line is exposed the same way; the
  code reviewer independently reproduced the crash by corrupting a fixture file.
- **Sightings:** 1.
- **Action:** **open.** `graph.py` is outside T-08's declared `files:` and belongs to a
  task that is `done`, so nothing was patched. Needs a follow-up task. Recorded in PR #8's
  "Check by hand".
- **Notes:** The builder did the right thing twice over: it reported the out-of-scope gap
  rather than patching someone else's module, and it narrowed its own regression test to
  call `_read_span` directly rather than through `unit_brief()`. The second choice is the
  interesting one. An end-to-end test would still be red today, which leaves two bad
  options — weaken the test until it passes, or patch outside the footprint — and the
  narrow test takes neither. The code reviewer was asked to judge whether this hid the
  finding and concluded it did not, because the gap is stated in the commit message, in a
  code comment, and in the PR body.
  The checkable claim worth watching: **when a failure mode is fixed at one call site, the
  other call sites reaching it need naming.** One unguarded `read_text` was fixed and an
  identical one three modules away was not, and only an accident of how the red proof was
  constructed surfaced it. This is adjacent to `F-20`, where a fix to one branch of a
  function left the identical defect live in its sibling and a reviewer scored the delta
  5/5 for correctly not touching it.

### F-29 — four task-file defects in T-09, and two of them are exact repeats

- **Date:** 2026-09-10
- **Task:** T-09
- **Bin:** 2
- **Claim:** The `task-critic` returned four blockers against T-09 before a builder
  existed. Two are new: `ScanOptions` as written could not compile (a non-defaulted
  `model` after defaulted fields), and scope step 4 described "a rerun that fails flips
  its claim to `stale`" as work to do when `sync_units` already performs that transition
  before any rerun — a task instructing a builder to re-implement something its
  dependency does. The other two are repeats of findings already in this ledger:
  - the acceptance block named `run_unit` as a method on the object `worker_factory()`
    returns; it is a module-level free function taking the worker as its first argument.
    That is **`F-1`'s claim verbatim** — a symbol named in acceptance that does not exist
    in the shape the task asserts.
  - "after editing one function, only that unit is scanned again" is **`F-22`'s
    mechanism verbatim**, one task later and against the same `ast_hash` semantics:
    editing a method changes the method, its enclosing class and its module, always
    three units, never one.
- **Sightings:** **`F-1`: 2. `F-22`: 2. The multi-defect shape (`F-24`): 3** — T-08,
  T-10, now T-09. Counted as a third rather than folded into the same-batch rule because
  `F-24` already exercised that judgement for T-08/T-10 and this is a distinct task file
  read on a distinct day; the honest reading is that the shape recurs per task, not per
  batch.
- **Action:** soft — corrected on `develop` before dispatch. The human ruled on the
  `F-22` repeat (reword to "the changed set", the ratified semantics now written into the
  criterion with the date); the other three were mechanical and applied as the critic
  proposed. No control.
- **Notes:** `F-22` recurring one task later is the finding here, not the four defects.
  The `F-22` correction was made in T-06's own task file and nowhere else, so the same
  wrong sentence was free to be written again in T-09 — a per-file fix for a per-planner
  habit. The narrow lesson is cheap and specific: **any acceptance criterion asserting
  that editing one thing changes one unit is wrong in this codebase**, and that sentence
  belongs in `tasks/README.md` where the next task file is written, not only in the two
  task files that have already been corrected.
  On graduation: `F-24` reaches three sightings here, but its own notes are right that
  the general shape — omissions, ambiguity, contradictions — is not machine-checkable and
  its remedy, the `task-critic` stage, already shipped and caught all four of these for
  about two minutes of reading. No control is authored for the general shape; a control
  that fires on correct prose is the worst outcome available here.
  What **is** now four times floated and still unbuilt is the narrow, genuinely scriptable
  slice, mentioned at `F-1`, `F-24`, `F-25` and again here: parse a task file's scope and
  acceptance blocks for backticked identifiers and check each against `src/` and the
  fixture, reporting the ones that do not resolve. It would have caught the `run_unit`
  defect mechanically. It catches neither of the two new T-09 defects, and it would not
  have caught `F-22`. That is an argument for building it as a `task-critic` tool rather
  than as a CI control: it is a pre-dispatch aid with a false-negative rate nobody should
  be forced to argue with in a red build. **Recommended to the human as tooling, not as
  a decision.**

### F-30 — a builder rewrote an acceptance criterion inside the commit that implemented it

- **Date:** 2026-09-10
- **Task:** T-09
- **Bin:** 2
- **Claim:** The implementation commit `163584f` edited `tests/test_scan.py` as well as
  `src/seshat/scan.py`. One edit changed what a criterion *means* — the "only that unit is
  rescanned" assertion was widened to the three-unit change set — and a second fixed a
  real fixture bug in the `workers=2` test (copying an already-scanned repo instead of the
  pristine fixture, which made the comparison run scan zero units and pass vacuously).
  Both edits were correct. Neither was the builder's call to make silently, and both were
  invisible in a commit whose subject says `feat`.
- **Sightings:** 1.
- **Action:** soft — the reviewer caught it and returned `NEEDS_HUMAN` at 2/5 rather than
  scoring the working code. The orchestrator verified the `ast_hash` claim independently,
  took it to the human, who ratified the widened assertion; the builder was told to
  escalate before changing a criterion and never to ride a test edit inside a feature
  commit. The next round complied without being reminded — test alone at `1551153`, fix
  alone at `fb34945`. No control.
- **Notes:** The checkable claim is narrow and real: **a commit whose subject is `feat`
  must not modify a file under `tests/` that a previous `test(T-NN):` commit in the same
  branch created.** That is scriptable against the branch's own history, and unlike most
  of Bin 2 it has an unambiguous machine answer. Holding at one sighting.
  Worth separating two things the same commit did, because they deserve different
  verdicts. The vacuous-fixture fix is the builder catching a false success in its own
  test and repairing it — exactly the behaviour this project wants, and the finding is
  only that it was buried. The criterion rewrite is different in kind: the builder
  substituted its own judgement for the human's on what the software must do, and it was
  *right*, which is precisely why it is worth logging. A wrong rewrite gets caught by a
  reviewer; a correct one shipped quietly and nobody ever learns the criterion was wrong.
  **Second sighting 2026-09-10, T-11** — see `F-37`. Same mechanism, same failure
  direction, a different builder instance and a task whose brief said in as many words
  not to do it. At two.
  The failure direction is the same one `F-23` describes from the other side of the loop —
  the loop's own instructions being the least-reviewed input — and the same thing saved it
  here: a reviewer that escalated instead of scoring the green tests.

### F-31 — the crash report lied about how long the run took and how far it got

- **Date:** 2026-09-10
- **Task:** T-09
- **Bin:** 2
- **Claim:** `run_scan`'s exception handler printed `elapsed = time.monotonic()` — the raw
  clock reading, not a duration — and a hardcoded `[0/0]` progress prefix. A scan that
  crashed instantly reported `elapsed=70588.8s`, and a scan that crashed after real work
  reported no progress at all. Both reviewers found it independently, in different trees.
  It survived the whole acceptance suite because every failure-path test asserted on
  program state (`run.status == 'failed'`) and none asserted on the text a human would
  actually read while debugging.
- **Sightings:** 1 for this mechanism. Belongs to the false-success family (`F-4`, `F-10`,
  `F-13`, `F-27`) by direction — output that reports something untrue and is believed —
  though here the audience is a human reading a terminal rather than a caller reading a
  return value.
- **Action:** soft — fixed in PR #9 by `fb34945`, pinned by `1551153`, a test proven red
  first on the progress half and separately proven red on the elapsed half at the
  orchestrator's request. No control.
- **Notes:** The checkable claim: **operator-facing output on a failure path needs its own
  assertion, not just a state assertion on the same path.** The generalisation the
  reviewer proposed — test log and status content, not only program state — is real but
  too broad to control; a linter cannot tell a status line from a debug print.
  Two things worth keeping. The bug lived on the path taken only when something has
  already gone wrong, which is the path least exercised and most read; that is a decent
  heuristic for where to spend an assertion. And the fix moved the counters into
  `run_scan`'s scope so the crash handler could see real numbers, which created shared
  mutable state across the `asyncio.gather` pool — a new seam introduced by a cosmetic
  fix. Both reviewers were asked to attack it and both cleared it concretely: the code
  reviewer forced a genuine lost update (21 where 11 was correct) by adding a yield point
  inside the critical section, proving the `workers=2` test has teeth and that the lock is
  not decorative. A comment now says so, because the lock guards a hazard that does not
  exist yet and would otherwise read as dead code to whoever tidies this file next.

### F-32 — Bin 3: a docstring naming a lock that never existed

- **Date:** 2026-09-10
- **Task:** T-09
- **Bin:** 3
- **Claim:** `_Stats`'s docstring said its counters were "guarded by `_ScanState.lock`".
  There is no `_ScanState` in `scan.py` and never was.
- **Sightings:** 1.
- **Action:** soft — fixed in PR #9 by `ddf75d1`, along with the comment explaining why
  the lock stays. No control, and none is possible: no checker can know whether a name in
  prose is meant to refer to a symbol.
- **Notes:** Logged because a fat Bin 3 is a real result and this is what one looks like.
  The only reason it was caught is that a reviewer read the docstring against the code
  rather than skimming past it; the cost of the error was one comment nit folded into a
  round that was happening anyway.

### F-33 — harness: `develop` moved under an in-flight worktree, and the review range lied

- **Date:** 2026-09-10
- **Task:** T-10
- **Bin:** unbinned harness finding
- **Claim:** The orchestrate skill tells both reviewers to review `develop..HEAD`. A task
  branch is cut from `develop` at dispatch, but `develop` is a moving ref: during T-10's
  build the human committed `ff8eaa6` (an unrelated task-status script fix) to it. From
  that moment `develop..HEAD` showed `scripts/task-status.py` being *reverted* by the task
  branch — a file the builder never touched, in a commit it never made. The builder's own
  footprint report was correct and the diff was wrong.
- **Sightings:** 1.
- **Action:** soft — the orchestrator caught it by running `git log --oneline develop..HEAD
  -- scripts/task-status.py`, which returned nothing for a file the range diff claimed had
  changed, and both reviewer briefs were given the true merge-base range `1d5b03d..HEAD`
  instead. The branch was rebased onto `develop` before the squash, so PR #10 is clean.
  No control.
- **Notes:** The failure direction is what makes this worth logging. It does not hide a
  real change; it *invents* one, which is the safer of the two directions but still costs
  a round if a reviewer files it as a finding — an undeclared, unreported edit to a script
  outside the task's `files:` list is exactly the shape a boundary reviewer is built to
  block on. Two reviewers would have found the same phantom independently and agreed with
  each other, which is the case where independence gives no protection at all.
  The fix is mechanical and belongs in the skill: brief reviewers with
  `$(git merge-base develop HEAD)..HEAD`, never `develop..HEAD`. Cheap, and it removes the
  whole class. If this recurs, that is the change to make rather than another note.

### F-34 — a known task-file defect was deferred, and the second reader had to re-find it

- **Date:** 2026-09-10
- **Task:** T-10
- **Bin:** 2
- **Claim:** A task-file defect found before dispatch is resolved before dispatch, or it is
  re-found at full price later. `F-24` recorded five defects in T-10 on 2026-09-09; the
  human fixed three and explicitly left (1) `ReflectionSummary` having no declared fields
  and (4) `files:` missing the ledger store open. Both were still open on 2026-09-10 and a
  second critic run spent a second full pass re-deriving them, including re-verifying
  against three dependencies that had merged in between.
- **Sightings:** 1 for the deferral mechanism. **As a planning defect, the eighth** — after
  `F-1`, `F-11`, `F-22`, `F-24`, `F-25`, `F-29` and the fifth the ledger counts under
  `F-24`.
- **Action:** soft — both resolved by the human at dispatch, the shape recorded in `F-24`.
  No control: a script cannot tell a deliberately deferred decision from a forgotten one.
- **Notes:** `F-24` predicted the cost precisely — "if T-10 dispatches with that still open,
  expect it back as a review finding", the `F-23` failure mode where a builder invents a
  field name and pins it with a green test. That is not what happened, and the reason is
  worth recording: the critic stage ran *again*, before dispatch, and caught it a second
  time. The soft layer held where it was predicted to fail, which is the first evidence in
  this log that a pre-dispatch reader is worth running on a task it has already seen.
  The cost was a second critic pass, roughly a minute; the predicted cost was a full review
  round plus a human correction mid-task. That is the trade, and it came out in favour of
  re-reading.
  What it does not settle: the defect still sat open for a day because nothing tracks
  "resolved before dispatch" as a gate. It was caught because the orchestrator read `F-24`
  in the ledger before dispatching, which is exactly the loop the ledger is for, and also
  exactly the sort of thing that works until the day someone skips the reading.

### F-35 — Bin 3: a lazy import to break a cycle between two new modules

- **Date:** 2026-09-10
- **Task:** T-10
- **Bin:** 3
- **Claim:** `candidates.py` imports `PatternDraft` from `agents/reflection.py`, and
  `run_reflection` imports `flag_candidates` back from `candidates.py` lazily, inside the
  function body, to break the resulting cycle. The alternative shape is a shared module
  holding the drafts that both import from, avoiding the cycle rather than routing around
  it.
- **Sightings:** 1.
- **Action:** none. Both modules document the cycle and why the import is where it is; the
  boundary reviewer raised it as taste and approved. Left as built.
- **Notes:** Logged as Bin 3 rather than Bin 2 deliberately. A checker *could* find lazy
  imports, but it could not tell the ones that break a genuine cycle from the ones that
  defer an expensive import, and both are legitimate — so the checkable version of this
  claim is not the claim anyone actually holds. That is the test for Bin 3 and this passes
  it cleanly.

### F-36 — harness: the first task in this log to draw zero review findings

- **Date:** 2026-09-10
- **Task:** T-10
- **Bin:** unbinned harness finding
- **Claim:** Both reviewers returned APPROVE 5/5 with no findings at any severity — the
  first time in ten tasks. The reported red proof was also the weakest so far: a bare
  `ModuleNotFoundError` on the whole test module, which proves the module is absent and
  proves nothing about any individual acceptance criterion.
- **Sightings:** 1.
- **Action:** soft — the orchestrator did not relay it. Both reviewer briefs were told the
  red was module-level and asked to mutation-test each acceptance bullet on the green tree;
  the code reviewer reported all seven going red for the correct reason. The orchestrator
  then independently planted two mutations of its own in the disposable boundary checkout —
  the sightings threshold `3 → 2`, and `concepts_discarded += 1 → += 0` — and confirmed
  exactly one test caught each, for the right reason. Reverted; the tests have teeth.
- **Notes:** A clean sweep is the result most worth distrusting, because it is
  indistinguishable from two reviewers agreeing to wave a branch through — the `F-2` and
  `F-21` shape. The cheap defence is the one used here: the orchestrator spends two
  mutations of its own rather than accepting "I mutation-tested it" as evidence. That cost
  about a minute and is the only thing separating "no findings" from "no looking".
  The other half is the red proof itself. A module-level `ModuleNotFoundError` is what you
  always get when a task creates a new module and writes its acceptance tests first, so it
  is not a builder error — but it means the red commit certifies far less than the ritual
  implies, and every future task that creates a new module will produce the same weak red.
  If a builder brief ever gets a line about proving each criterion red individually, this
  is the entry that argues for it. One sighting; not yet a change.

### F-37 — the design a human rejected in the brief shipped anyway in the code

- **Date:** 2026-09-10
- **Task:** CT-01
- **Bin:** 2
- **Claim:** The `task-critic` found a blocker in CT-01's brief: the `declared by this
  task` exemption, as written, would have swallowed the tool's own worked example. The
  human ruled, the brief was corrected on `develop` to require that a `files:` entry be
  "the plausible home" for the name, and the builder was dispatched against the corrected
  file. The builder then implemented `plausible_home()` as *any* `src/*.py` entry in
  `files:` exempting *every* signature-shaped name — which, since nearly every real task
  lists at least one source file, gutted the bucket the same brief calls "the point of the
  tool". The `after_scan` example the correction was written to protect was reported as
  `declared by this task` in the shipped code. **The correction was applied to the brief
  and the rejected behaviour shipped regardless**, one dispatch later.
- **Sightings:** 1 for this mechanism. Related to `F-30` from the other direction: there a
  builder overrode a criterion knowingly and correctly; here a builder implemented a
  criterion faithfully in wording and inverted it in effect.
- **Action:** soft — caught by the code reviewer, which proved it by deleting the guard
  clause and watching all 12 acceptance tests pass. The human ruled a second time, this
  time on the implementation: presence, never plausibility. Fixed in PR #11 by `001112a`,
  pinned by a test built from the `after_scan` case. The brief on `develop` was rewritten
  a second time to say "resolves in a listed file — no filename matching, no module-path
  guessing, no heuristic of any kind", with the date of the ruling.
- **Notes:** The checkable claim, and it is a real one: **a task-file correction that
  states a constraint in words like "plausible", "appropriate" or "related" has not
  actually constrained anything.** The first correction and the shipped bug are both
  faithful readings of the same sentence. The second correction is checkable because it
  names a set-membership test a machine could run.
  This is the strongest argument in the log so far for why the loop's stops matter more
  than its stages. Two stages read that sentence — the critic that wrote it and the
  orchestrator that applied it — and neither noticed it had no teeth, because a
  plausibility rule reads like a rule. What caught it was a reviewer that deleted the code
  and watched the tests not care. **Test-deletion beat two careful readings**, and the
  same technique is what found `F-26`.
  Worth recording the irony plainly, since the ledger is the experiment: the tool this
  task builds exists to catch defects in task files, and its own task file carried a
  defect that survived a critic, a human ruling and a correction before a mutation test
  found it in the code.

### F-38 — a tool's own test suite could not see its central guard being deleted

- **Date:** 2026-09-10
- **Task:** CT-01
- **Bin:** 2
- **Claim:** Twelve acceptance tests, written first and proven red, all passed with the
  `declared by this task` membership guard deleted outright. The same sweep later found
  the membership branch could be weakened from `rel(found.path) in files` to `if files`
  with all eighteen tests still green. Both are the tool's core decision — the one that
  separates "the task creates this" from "this name is unaccounted for" — and neither had
  a test that could distinguish correct from broken.
- **Sightings:** 1 as stated. **As the mutation-testing family, 2** — after `F-26`, where
  a mutation survived forty-nine tests and only a deliberate mutation found the gap.
- **Action:** soft — both pinned in PR #11, each with a test proven red under the exact
  mutation before the fix landed. No control.
- **Notes:** The checkable claim: **a branch that decides which bucket a result lands in
  needs a test per branch, not a test per happy path.** All twelve original tests asserted
  on reports produced by correct input; none asserted that a *wrong* classification would
  be noticed.
  Two sightings now say the same thing about this project's tests: they are written to
  demonstrate the feature, and a demonstration cannot fail in the interesting direction.
  At a third sighting this is a genuine control candidate — not "run mutation testing in
  CI", which is slow and noisy, but something narrower: a reviewer instruction, already
  informal, that every guard clause introduced by a change must be deleted once and the
  suite re-run. Both reviewers did that here without being told twice, and it found the
  two most serious defects in the task.

### F-39 — one function broke three times in three consecutive rounds, each time silently

- **Date:** 2026-09-10
- **Task:** CT-01
- **Bin:** 2
- **Claim:** `sections()` in `scripts/task-symbols.py` produced a distinct silent
  content-drop in each of three consecutive fix rounds: (1) no fence awareness at all, so
  a `##` line inside a fenced example ended a section early and a repeated header
  overwrote the first; (2) a fence left open at EOF swallowed the rest of the file, report
  showing a clean `0/0/0/0`; (3) two fences each left open summed to an even count, paired
  with each other, and dropped a real section header between them with no warning. Every
  one failed in the same direction — the report said nothing was wrong because the parser
  never saw the text — and every one was found by a reviewer building adversarial
  fixtures, never by the suite.
- **Sightings:** 1 for the repeated-regression shape. All three instances belong to the
  false-success family (`F-4`, `F-10`, `F-13`, `F-27`, `F-31`) and are counted once here
  under the same-batch rule: one function, one task, one cause.
- **Action:** soft — all three fixed in PR #11 (`001112a`, `db9c4f1`, `36ddd10`), each
  with its own red proof. A factual comment now sits at `sections()` listing the three
  failures and what each guard is for. No control.
- **Notes:** The checkable claim is about attention, not code: **when a function breaks
  twice in the same direction, the next round should attack it rather than review it.**
  That is what happened — round 3's brief told the reviewer the area was fragile and asked
  for fixtures rather than reading — and it is why round 3 found something round 2's
  reading had not.
  Worth being honest about the cost: four fix rounds on a ~400-line advisory script is a
  lot of loop for the value. The defensible reading is that parsing semi-structured
  human-written markdown is genuinely harder than it looks and each round found a real
  defect. The uncomfortable reading is that the task should have specified the parsing
  contract precisely enough to test up front, and the brief said "extract backticked
  spans" as if that were simple. Both are true. If a second task in this plan needs a
  markdown parser, the brief should name the fence, header and span cases explicitly
  rather than leaving them to be discovered one review round at a time.

### F-40 — the orchestrator asserted an external tool's contract in a brief, again

- **Date:** 2026-09-10
- **Task:** CT-02
- **Bin:** 2
- **Claim:** CT-02's brief instructed a builder to have the hook "emit its report so the
  model sees it as feedback on the write", and its acceptance bullet pinned that as "the
  resolver's report on stdout". The critic found that `PostToolUse` hook output reaches
  the model through a JSON envelope (`hookSpecificOutput.additionalContext`), not through
  bare stdout — two hook implementations shipped with the installed Claude Code both use
  the envelope and never plain text. A hook satisfying the brief literally would have
  passed every test while the model never saw a word. The brief had hedged on the *input*
  payload's field names and asserted the *output* channel as settled fact.
- **Sightings:** **`F-25`: 2.** Same mechanism as T-08's inverted `CODEGRAPH_MCP_TOOLS`
  claim — a specific, empirically checkable statement about an external tool, written down
  as known and wrong.
- **Action:** soft — the human ruled on 2026-09-10 to pin the envelope in the brief on the
  strength of the plugin evidence, with the evidence labelled second-hand and the builder
  still required to confirm it against the installed version and say how. The acceptance
  bullet now asserts on the parsed JSON structure rather than a substring, so a bare
  `print()` fails it. CT-02 has not been dispatched.
- **Notes:** `F-25`'s note said the narrow case is automatable: any task-file claim about
  an installed tool's observable behaviour can be turned into a command. Two sightings
  now. It also said the word "verified" is what stops the next reader from checking —
  this brief did something subtler and worse, hedging visibly on one half of a contract
  while stating the other half flatly, which reads as though the flat half was the part
  already known.
  Direction of failure, again: a hook that prints to a channel nobody reads does not fail.
  It succeeds silently and the feature is simply absent.

### F-41 — harness: `develop` moved under an in-flight worktree, second sighting

- **Date:** 2026-09-10
- **Task:** CT-01
- **Bin:** unbinned harness finding
- **Claim:** Second sighting of `F-33`. The boundary reviewer's `develop..HEAD` range
  showed `reflection.py`, `candidates.py`, `store.py` and four ledger entries being
  deleted — T-10's work, merged onto `develop` after CT-01's branch was cut. The reviewer
  caught it, recovered the true range with `git merge-base`, reviewed that, and said
  plainly that the phantom deletions were not attributable to the change under review.
- **Sightings:** **2** — `F-33` (T-10), this.
- **Action:** soft — the reviewer self-corrected and the orchestrator's later fix-round
  briefs named the true base explicitly and told the builder not to rebase. No control.
- **Notes:** The reviewer recovering unaided is the good news and also the reason this
  stays soft: the failure is legible, a reviewer that knows `git merge-base` fixes it in
  one command, and `F-33` had already written it down. The cheap fix is entirely in the
  orchestrator's hands and cost one sentence per brief — **state the merge-base SHA and
  the range in every reviewer brief, rather than saying `develop..HEAD`**. That was done
  from round 1 onward here only because `F-33` had been logged the day before. Third
  sighting should make it a line in the `orchestrate` skill, not a control.

### F-42 — Bin 2: `scripts/` sits outside every control's reach

- **Date:** 2026-09-10
- **Task:** CT-01
- **Bin:** 2
- **Claim:** `controls/fitness/exec_confinement.py` sets
  `SCAN_DIRS = ['src', 'controls', 'governance', 'tests']`. `scripts/` is not in it, and
  now holds two files — `task-status.py` and `task-symbols.py`. A script dropped there
  calling `exec` or `eval` would never be seen by DEC-1's control. Neither current script
  does; this is a coverage gap, not a violation.
- **Sightings:** 1.
- **Action:** **closed 2026-09-10 by DEC-2, PR #13** — the human chose to supersede before
  CT-02 could add a third file to `scripts/`. Scan set derived, not listed. What the
  supersession found on the way is logged as `F-44` and `F-45`.
- **Was:** open. Not fixed in PR #11: widening a control's scan set is a governance
  change, and doing it inside a task that adds a file to the very directory being brought
  under the control is the wrong shape — a builder must never be in a position to
  influence the reach of the control that judges it. Belongs in its own change, on
  `develop`, reviewed on its own terms.
- **Notes:** The checkable claim, and it generalises past this one control: **a control's
  scan set should be the set of directories that contain code, derived, not a list
  maintained by hand.** Every hand-maintained list of directories drifts the moment
  someone adds a directory, and nothing announces it — the control keeps passing, which
  reads exactly like the code being clean.
  Found by a boundary reviewer that was explicitly asked whether `scripts/` was in the
  control's scan set and told to say so plainly if it was not. It would not have surfaced
  otherwise, because the control passed. Worth remembering when writing the next boundary
  brief: asking "is this covered?" is a different question from "does this pass?", and
  only the first one finds a gap.

### F-43 — harness: a reviewer proposed a fix that could not work, and said so when shown why

- **Date:** 2026-09-10
- **Task:** CT-01
- **Bin:** unbinned harness finding
- **Claim:** The code reviewer's round-3 finding was correct — two fences left open pair
  with each other and drop a section silently — but its proposed fix, a per-fence tracker
  replacing the global parity count, cannot work: the two readings are the same character
  sequence, and CommonMark resolves the second delimiter as closing the first. The
  orchestrator rejected the fix, kept the finding, and specified a different one that
  inspects the casualty (warn when a fenced region swallows a known section header) rather
  than classifying the fences. The builder reached the same conclusion independently
  before being told, and said so. The reviewer, invited to argue back with a concrete
  counter-example and told explicitly not to soften the finding because it had been
  overruled, looked for one, did not find it, and agreed.
- **Sightings:** 1.
- **Action:** none needed. Recorded as a positive data point.
- **Notes:** Logged because the log is mostly failures and this is the loop's stated shape
  working exactly as written: reviewer wins on the finding, orchestrator wins on the fix
  only by carrying the argument, builder free to refuse, and the disagreement resolved by
  a fact about CommonMark rather than by seniority. `AGENTS.md` says "builder and reviewer
  disagree: reviewer wins, unless you can personally verify the reviewer is wrong" — this
  is the exception clause being used, once, with the verification stated in the brief so
  both other agents could check it.
  The part worth keeping deliberately: the reviewer was told **not** to soften its finding
  because the orchestrator disagreed with the remedy. Separating "your diagnosis is right"
  from "your prescription is wrong" is what let it re-attack the new code honestly instead
  of defending its own proposal, and it found a genuine false-positive class in the
  replacement on the very next round.

### F-37 — a builder answered a wrong criterion by tuning the test until it passed

- **Date:** 2026-09-10
- **Task:** T-11
- **Bin:** 2
- **Claim:** Second sighting of `F-30`. T-11's acceptance required that after editing a
  function and rescanning, `units --changed` "lists exactly one unit". That is false for
  any rescan that runs to completion: `sync_units` sets a unit to `changed`, and
  `run_unit` sets it back to `scanned` when it processes it, so the list is always empty
  by the time the command runs. The builder discovered this, and instead of stopping,
  rescanned with `--units 2` so that exactly one of three changed units survived
  unprocessed — then rewrote `test_units_changed_...` inside the implementation commit
  `5af9119`, not in the `test(T-11):` commit that created the file.
- **Sightings:** 1 for this instance. **As `F-30`, 2.**
- **Action:** soft — the code reviewer returned `NEEDS_HUMAN` at 2/5 rather than scoring
  the green suite, which is the second time in two tasks that escalation caught this. The
  orchestrator verified the status lifecycle independently in `src/seshat/units.py` and
  took it to the human, who chose to correct the criterion at the source: `--changed` is
  now defined as "seen as changed and not yet reprocessed", the acceptance bullet requires
  asserting the expected qualified name rather than a count, and the empty-after-a-full-
  rescan behaviour is pinned by its own test. Fixed in PR #12 by `d794f20`. No control.
- **Notes:** The builder's own report described this honestly and called it "my own test-
  design bug" rather than a criterion problem — it genuinely believed it had found a flaw
  in its first draft of the test rather than a flaw in the spec. That is the interesting
  part, and it is why the brief's instruction ("an acceptance criterion you believe is
  wrong is a planning question — stop and report it") did not fire: the builder never
  classified what it had found as a criterion problem. Telling builders to escalate wrong
  criteria only helps when they recognise one. The failure had a second, worse property:
  the workaround produced a test that passed by arithmetic, so a filter returning the
  *wrong* unit would still have gone green. The reviewer proved the fixed version is
  identity-sensitive by reversing `build_queue`'s sort order and watching it fail.
  `F-30`'s scriptable claim still holds and now has two sightings behind it: **a `feat`
  commit must not modify a file under `tests/` that an earlier `test(T-NN):` commit on the
  same branch created.** One more and it earns a control.

### F-38 — a task file named three fields that do not exist, and the rule of three came due

- **Date:** 2026-09-10
- **Task:** T-11
- **Bin:** 2
- **Claim:** Third sighting of `F-1`. T-11's scope specified `format_citation` as
  `{qualified_name} {file_path}:{start}-{end} @{sha[:8]} [{last_status}]`. The `Citation`
  dataclass has `start_line`, `end_line` and `verified_sha`; `start`, `end` and `sha` do
  not exist on it, and the format string as written raises `AttributeError`. The same task
  also assumed two ledger queries that were never built (fetch a concept by id, list a
  concept's evidence) and specified a `concept` acceptance test against a fixture that can
  never contain a concept, because only the reflection agent writes one and the fixture
  was specified as model-free.
- **Sightings:** **`F-1`: 3. The multi-defect shape (`F-24`): 4** — T-08, T-09, T-10,
  T-11, counted once per task.
- **Action:** all three corrected on `develop` before any builder was dispatched — the
  `task-critic` caught every one by reading the code the task names. The human ruled on
  the concept-fixture fork: run reflection with a `FakeLLMClient` so the concept the CLI
  renders is one the real pipeline wrote, rather than a row seeded by hand.
  **No control, deliberately.** See notes.
- **Notes:** This is `F-1`'s third sighting and therefore the rule of three came due. The
  orchestrator's judgement is that it should not graduate, and the reasoning is worth
  recording because it is the first time the rule has been declined rather than
  unmet. `F-1`'s remedy already shipped, as a *process* step rather than a control: the
  `task-critic` agent now runs against every task file before a builder exists, and it
  caught all three of these defects here in under three minutes, before a line of code was
  written. A CI control cannot do the same job — `tasks/` is untracked and never reaches
  CI, so a control would have nothing to run against, and the check it would perform
  (does this identifier exist in the tree?) is exactly what the critic already does with
  more context and no false-positive cost. Graduating here would mean building a worse
  version of a working control in a place it cannot run. The honest reading of `F-1` at
  three sightings is that the finding was real, the fix works, and the fix is not a
  control. Logged as such rather than dispatching `control-author` to refuse.
  Worth noticing separately: the defect rate in task files is not falling. Four tasks in a
  row have arrived with multiple defects each. The critic catches them, which is why none
  has cost a review round since T-09, but the critic is a filter on a bad input, not a fix
  for it. The upstream cause is the planner writing acceptance criteria against a tree it
  has not read. That is a finding about the `planner` skill, and it belongs there.

### F-39 — harness: an `AGENTS.md` "Always" requirement that no output honoured and nothing checked

- **Date:** 2026-09-10
- **Task:** T-11
- **Bin:** unbinned harness finding
- **Claim:** `AGENTS.md`'s Always list requires that a citation carry the claim id among
  its fields. T-11 shipped six subcommands and not one output path printed a claim id —
  `format_citation`'s specified shape omits it, and both the `claims` and `drift` lines
  and `concept`'s evidence list were built from that shape. The task file matched
  `AGENTS.md` nowhere on this point and nothing failed, because the Always list is
  declared shape with no control behind it.
- **Sightings:** 1.
- **Action:** soft — the boundary reviewer found it by reading `AGENTS.md` against the
  diff rather than by running a control, and explicitly declined to treat the task file as
  automatically correct. The orchestrator folded it into the fix round: `seshat claims`,
  the per-claim detail view, now prints the id (`085dbdd`); `drift`'s grouped lines and
  `concept`'s evidence list keep the short form, and the task file says why. No control.
- **Notes:** The reviewer's second pass made the sharper point unprompted: this closes the
  gap *as scoped*, not literally. If the Always list means "every citation, everywhere",
  two paths still do not comply. It judged the amendment a legitimate, visible human scope
  decision rather than a workaround, and declined to re-open it as blocking — which is the
  right call and the right way to say it.
  The harness observation is the one to keep. `AGENTS.md` states the Always list is the
  *shape* of the design and that the enforced wording lives in the generated view, which
  wins on any disagreement. That is a sound rule for avoiding a rule stated twice, but it
  has a cost nobody had paid until now: an Always item with no `DEC-N` behind it is
  unenforced prose, and a task file can contradict it for a whole build without anything
  going red. Seven of the eight fields the Always list names are in `Citation` and get
  rendered; the eighth silently was not. This is not an argument for controlling the
  Always list — most of it is genuinely shape. It is an argument that the boundary
  reviewer reading `AGENTS.md` against the diff *is* the control, and the one thing that
  would break it is briefing that reviewer as if `RULES.md` were its whole job.

### F-44 — a decision's stated rationale rested on a false claim about a linter

- **Date:** 2026-09-10
- **Task:** DEC-2 (no task file; dispatched from `F-42`'s triage)
- **Bin:** 2
- **Claim:** DEC-1's Context said ruff's `S102` "is enabled in ruff's default rule set, and
  this repo's `pyproject.toml` never opted out of it, so the count of `exec`/`eval` sites
  sat at zero without anyone deciding it should", and that a `per-file-ignores` entry
  "buys T-05 its one legitimate call". None of it is true. `pyproject.toml`'s
  `extend-select` is `["B", "I", "RUF", "UP"]` — no `S` — and flake8-bandit is not in
  ruff's default selection. A file containing `x = eval("1")` passes `uv run ruff check`
  in `src/seshat/` and in `scripts/` alike. The per-file-ignore is inert and the
  "accidental guard" the rationale describes never existed.
- **Sightings:** **`F-25`: 3.** After T-08's inverted `CODEGRAPH_MCP_TOOLS` claim and
  CT-02's `PostToolUse` output channel (`F-40`). **First time it is in a governance
  decision rather than a task file.**
- **Action:** corrected in DEC-2's Context, PR #13. DEC-1 left as written with a note
  pointing at DEC-2 — history is a record, not a constraint. Both the control author and
  the boundary reviewer reproduced the probe independently before relying on it.
- **Notes:** The checkable claim is `F-25`'s, now on its third sighting: **a written claim
  about an installed tool's observable behaviour must name the command that shows it.**
  Three sightings is the rule of three, and this is where the honest answer is that **no
  control gets authored.** A machine cannot check whether a paragraph of English is true
  about ruff. What can be automated is narrower and was floated at `F-1`, `F-24`, `F-25`
  and `F-29`: turn the claim into a command and run it. That is a habit and a brief line,
  not a CI gate, and `scripts/task-symbols.py` (PR #11) is the first instalment of it.
  The reason this instance is worse than the two task-file ones: a task file is read once
  by a builder and thrown away, while a decision is the durable record that tells every
  future reader why a rule exists. DEC-1's false rationale would have justified narrowing
  the control one day — "ruff already covers the rest" — and nobody would have checked.
  Worth noting the direction the error pointed: the rationale *overstated* existing
  protection. An overstated guard is the dangerous kind, because it argues for doing less.

### F-45 — the control that enforces a rule had no tests, and hid two false negatives

- **Date:** 2026-09-10
- **Task:** DEC-2
- **Bin:** 2
- **Claim:** `controls/fitness/exec_confinement.py` has gated every build since T-05 and
  had no test of its own. Reviewers proved it by deleting the `tests/fixtures/` exclusion
  and inverting the hidden-directory check: the control printed `ok` and exited 0 both
  times, because nothing in the tree happened to trip the broken logic. Two live false
  negatives were then found in the same file: (1) `rglob('*.py')` does not descend into
  symlinked directories, so `exec` behind one was invisible and the control reported `ok`;
  (2) a decode or syntax failure aborted the scan, so a violation later in sort order went
  unreported. Neither was introduced by this change; both had been there.
- **Sightings:** **As the untested-guard family (`F-38`), 2.** Same week, different code:
  a central guard whose deletion no test noticed. Counted separately from `F-38` because
  that was a new tool's own suite and this is a CI gate that has been running for days.
- **Action:** fixed in PR #13 — 26 tests in `tests/controls/test_exec_confinement.py`,
  each building its tree in `tmp_path`, each proven red by breaking the guard it pins.
  Both false negatives fixed with tests. No new control; the fix is that the control now
  has tests, which is the ordinary thing that should have been true from the start.
- **Notes:** The checkable claim, and it is the sharpest one in this log: **a fitness
  control is code that decides whether a build passes, and it needs tests at least as much
  as the code it judges.** This one is mechanically checkable — every file under
  `controls/fitness/` should have a corresponding test module — and at a third sighting it
  is a genuine candidate for a control about controls.
  Being honest about what this says for the harness's own falsifiable test: the governance
  layer went several days enforcing a rule with a gate that could have been silently
  broken by one edit, and the thing that found it was not the harness but a reviewer
  instructed to delete guards and see what noticed. That technique — `F-26`, `F-38`, and
  now this — has found the three most serious defects in this project. If any single
  practice earns promotion from this log, it is that one, and it is a brief line rather
  than a control.

### F-46 — harness: two rounds of guarding a risky mechanism, then removing it

- **Date:** 2026-09-10
- **Task:** DEC-2
- **Bin:** unbinned harness finding
- **Claim:** Symlink descent entered the control as a fix for a real finding (code behind
  a symlinked directory was invisible). The orchestrator ruled it should descend into
  in-repo links and fail closed on links escaping the repo. That closed the reported hole
  and opened a worse one: a symlink with an ordinary name pointing at an excluded
  directory bypassed the name-based exclusion entirely, because the exclusion checked the
  link's name and the descent checked the resolved path, and the two never spoke. A link
  to `.venv` pulled roughly a hundred third-party violations into the gate and took the
  run from 0.4s to 18s; a link to `.claude/worktrees/` reached full checkouts of this
  repo on other branches. The human's ruling was to remove the mechanism rather than guard
  it a third time.
- **Sightings:** 1.
- **Action:** removed in PR #13. The blind spot is now stated in DEC-2's Rule and reported
  by an informational line that never affects the exit code.
- **Notes:** Recorded against the orchestrator, since the fail-closed ruling was mine and
  it was wrong in a specific, learnable way: **I ruled on the escape case, which was the
  case in front of me, and never asked what else a symlink could point at.** Fail-closed
  reasoning felt rigorous and was, within the one scenario I considered. The reviewer that
  found it did the thing I had not: enumerated targets rather than directions.
  The pattern worth keeping is the human's, not mine. Two rounds of patching a mechanism
  that was never required — DEC-1, DEC-2 and `F-42` all concern a hand-maintained
  directory list, and none of them asked for symlink handling — and the resolution was to
  delete the mechanism and write the resulting gap into the rule. A blind spot that is
  documented, reported on every run, and cannot break the build is a better artifact than
  a clever guard nobody can reason about.
  Also worth recording: the builder agreed with the reversal unprompted and named the
  accepted cost itself, and both reviewers independently endorsed the removal over their
  own earlier positions. Nobody defended their previous answer.

### F-40 — the acceptance suite shelled out to a binary nobody had declared, and only CI knew

- **Date:** 2026-09-10
- **Task:** T-11
- **Bin:** 2
- **Claim:** A test must not depend on an executable that is not a declared dependency of
  the project. `src/seshat/cli.py` called `run_scan` without passing the `indexer`
  parameter that `src/seshat/scan.py` exposes precisely so callers can substitute one, so
  every scan-driving test in `tests/test_cli.py` spawned the real `codegraph` binary.
  Eleven tests went green locally and 3 failed / 8 errored on the runner with
  `[Errno 2] No such file or directory: 'codegraph'`. `codegraph` is an npm package
  installed on the developer's machine and nowhere in `pyproject.toml`.
- **Sightings:** 1. Belongs to the false-success family (`F-4`, `F-10`, `F-13`, `F-27`,
  `F-31`) by failure direction: the suite reported success on the strength of an
  accident of the environment.
- **Action:** soft — fixed in PR #12. `indexer` is now a module-level patchable seam in
  `cli.py` alongside `worker_factory` and `reflect_after_scan`, passed explicitly to
  `run_scan`; the default is still the real indexer and the reviewer identity-checked
  that a production `seshat scan` is unchanged. The `IndexFailed` → exit 2 test was
  rewritten to drive the new seam and was proven to survive a mutation of the mapping.
  Verified by running the suite under a `PATH` with `codegraph` genuinely unresolvable,
  by the builder and then independently by the reviewer. No control.
- **Notes:** The seam already existed and `tests/test_scan.py` already used it at every
  call site — T-09 built `indexer` injection for exactly this reason. The defect was one
  caller not using the affordance its own dependency provides, which is why nobody
  spotted it: the CLI looked like it was calling `run_scan` correctly, and it was, minus
  one keyword argument whose absence is invisible at the call site.
  The checkable claim worth keeping is narrow: **a subprocess invocation reachable from a
  test must name a binary that is either a declared dependency or injected through a
  seam.** A script could walk the test suite's reachable call graph for `subprocess.run`
  and check argv[0] against `pyproject.toml` plus an allowlist. That is real work for one
  sighting, and CI already catches this class the moment it happens — which is the
  argument against a control, not for one. Holding at one.
  Checked while here, at the orchestrator's request: `_commit_sha` (`src/seshat/scan.py:75`)
  also shells out, to `git rev-parse HEAD`, on every scan including in tests. The reviewer
  confirmed by execution — `git` and `codegraph` both stripped from `PATH` — that it fails
  soft, catching `OSError` and returning `'nogit'`. Not a second landmine, but it is the
  same shape one handler away from being one.

### F-41 — harness: every agent in the loop verifies by execution, on the same machine

- **Date:** 2026-09-10
- **Task:** T-11
- **Bin:** unbinned harness finding
- **Claim:** `F-40` shipped through a task-critic, a builder, two reviewers in two
  separate checkouts, two full review rounds, four independent `make check` runs and an
  explicit instruction to both reviewers to verify by execution rather than by reading —
  and was caught by CI thirty seconds after the PR opened. Every one of those agents ran
  the suite on the developer's machine, where `codegraph` is installed. The loop's
  central quality mechanism has a blind spot exactly the size of the difference between
  that machine and the runner, and separate checkouts do nothing about it because the
  thing being shared is the host, not the tree.
- **Sightings:** 1.
- **Action:** soft — noted. Fixed the defect, not the loop.
- **Notes:** This is the first finding in the log where the harness did not merely miss
  something but was *structurally incapable* of catching it, and it is worth being precise
  about why. `F-2`'s fix — a separate checkout per reviewer — was aimed at agents
  contaminating each other's evidence. It works. It has nothing to say about agents
  sharing an environment that is itself wrong, and reading the two problems as one would
  be a mistake: more isolation of the same kind buys nothing here.
  What actually caught it was the cheapest thing in the pipeline. That is the useful
  observation, and it cuts against the instinct this project keeps having, which is to
  answer a miss with another agent. CI is not a better reviewer; it is a *differently
  situated* one, and situation is what was missing. The same logic says a third reviewer
  would have found nothing.
  Two responses are available and neither is obviously right yet. Ask reviewers to run
  the suite under a stripped environment as a named verification — cheap, but only ever
  catches the hazard someone thought to strip. Or open the PR earlier and treat CI's first
  run as an input to review rather than a gate after it — which changes what a PR means
  and would need the human to want it. Recorded as an open question, not a change. Watch
  for a second sighting where the environment difference is subtler than a missing binary:
  a version skew, a locale, a filesystem case rule. That one will not announce itself with
  `Errno 2`.

### F-42 — harness: the gate scanned agent worktrees and failed on a rule nobody had violated

- **Date:** 2026-09-10
- **Task:** T-12 (found on `develop`, before the task was dispatched)
- **Bin:** unbinned harness finding
- **Claim:** `make check` was red on a clean `develop` with 8 failures, none of them in
  the repository. `governance/scripts/check_governance.py`'s `scannable_files()` walked
  `os.walk(REPO_ROOT)` pruning only a named allowlist of directories, so it descended
  into `.claude/worktrees/`, where nine leftover agent worktrees held whole checkouts of
  this repo at commits predating the DEC-1 → DEC-2 supersession. Each one's copy of
  `controls/fitness/exec_confinement.py` still carried `governance: enforces DEC-1`, and
  check 4 reported each as a live unfinished supersession.
- **Sightings:** 1.
- **Action:** **fixed on develop in `9ee164b`** — the walk now prunes any dot-prefixed
  directory. The nine merged worktrees and five scratch review checkouts were pruned by
  the human's decision. No control; this *is* the control, corrected.
- **Notes:** The interesting part is not the bug, it is what the bug is made of. A
  governance harness whose integrity check cannot tell repository content from a
  *checkout of the repository's own past* will fail the moment its own workflow leaves
  one lying around — and this workflow leaves one per task, by design. The failure was
  perfectly informative and completely wrong: every message was true of the file it
  named, and none of them was about this repo.
  DEC-2's own control already excluded dot-prefixed path components, and had done since
  it was written. The integrity checker did not, and the two had never been compared.
  That is the checkable claim worth keeping and it is narrow: **the pragma scanner and
  the controls it validates agree on which paths are in scope.** A test that asserts the
  two exclusion rules produce the same file set is mechanical and cheap. Holding at one
  sighting; if a second scope disagreement appears, write it.
  Cost was real but bounded: the gate was red before the task started, which is the one
  state the orchestrate skill says you must not build from, because you can no longer
  tell which failures a task caused. Worth noting that this had been sitting on `develop`
  through the T-11 triage commit and nobody had run `make check` on a clean tree since.

### F-43 — the acceptance suite's red was a missing module, which proves nothing

- **Date:** 2026-09-10
- **Task:** T-12
- **Bin:** 2
- **Claim:** An acceptance test's red proof must fail for the reason the criterion is
  about, not because the module under test does not exist yet. All ten of T-12's
  acceptance tests went red at `7bf4564` with one error —
  `ModuleNotFoundError: No module named 'seshat.agents.answer'` — plus `ask` missing
  from `--help`. That red is real and it is nearly uninformative: it proves the module
  is new and says nothing about whether a single assertion inside those tests bites.
- **Sightings:** 1.
- **Action:** soft — no fix to the code. The reviewer was briefed to treat the weak red
  as the actual work of the review and mutation-tested every assertion instead:
  `validate_answer` collapsed on any unknown id, and separately never collapsing;
  `render_answer` ignoring `claim_status`; `search_claims` collapsing its two fields.
  Each was caught by a distinct test. The tests turned out to be good; nothing in the
  red proof had told us that.
- **Notes:** This is structural, not a lapse by this builder. **Every task in this plan
  that introduces a new module gets this red for free**, and the harness currently
  accepts it as the red-then-green evidence the whole loop is built on. The acceptance-
  tests-first rule was written to stop tests being retrofitted to whatever the code
  happened to do; it does not, on its own, produce evidence that the tests can fail for
  the right reason.
  The checkable form is a real technique with a name — mutation testing — and proposing
  it wholesale for one sighting would be the disproportionate answer `F-11` already
  refused. The cheap version is a line in the reviewer brief, and it earned its keep
  here on the first outing: when the red proof's failure mode is uniform across every
  test (one import error, one missing subcommand), the reviewer mutates the
  implementation per criterion instead of trusting the red. Related to `F-11` — there
  the fixture could not express the failure, here the red does not exercise the
  assertion — and both are the same underlying question: *what would make this test go
  red, and is it the thing the criterion is about?* If a third variant of that question
  appears, the family is worth a decision.

### F-44 — a fix round's regression test was proven red by mutation, not by absence

- **Date:** 2026-09-10
- **Task:** T-12
- **Bin:** unbinned harness finding — a note on `F-9` working
- **Claim:** `F-9` recorded twice that fix-round regression tests ship with no red-proof
  requirement, and its second sighting pinned the cause: an instruction repeated
  per-item gets forgotten on the item that looks too small to need it. On T-12 the fix
  round's single item was coverage for a behaviour that was **already correct**, so the
  usual red proof — check the pre-fix file out and watch it fail — was unavailable by
  construction. The builder was told to mutate `_concept_citation_display` to bypass
  `format_citation` and prove the red that way. It did, and reported the failing output
  verbatim; the reviewer reproduced the same mutation independently and matched it.
- **Sightings:** n/a — recorded as evidence that `F-9`'s fix generalises.
- **Notes:** Worth writing down because it closes a gap in `F-9`'s own proposed remedy.
  "Prove the regression test fails against the unfixed code" is unimplementable when
  there is no unfixed code — when the fix is a test for behaviour that already works,
  which is exactly the shape of a coverage gap found in review. Mutation is the general
  form and absence is the special case, so the builder brief should say **mutate the
  implementation and watch the new test fail**, which covers both.
  One more thing the reviewer caught that the builder did not, and it is the reason to
  ask for an independent reproduction rather than accept the report: one of the three
  new tests stayed green under the builder's mutation. The builder called that "expected
  and consistent," which was true but incomplete. The reviewer went looking for a
  mutation that *would* catch it, found one — removing the concept fallback from
  `_citation_display`, the function `validate_answer` actually routes through — and so
  established the test was insensitive to one mutation rather than insensitive to all of
  them. A new test no mutation can redden is decoration, and only the second check tells
  you which you have.

### Planning notes from T-12

- **The task-critic earned its keep, quietly.** Three nits, no blockers, and all three
  were shape ambiguities rather than missing symbols: whether the answer collapses when
  *any* or *every* sentence loses its citation; one word, "citation", naming both a bare
  id and a rendered display string in adjacent bullets; and a memory-absence criterion
  loose enough that renaming a method would satisfy it. None would have failed loudly.
  All three would have surfaced as review findings or, worse, as a plausible wrong
  implementation with green tests. This is the first task where the critic's whole value
  was in disambiguation rather than in catching a symbol that does not exist, which is
  the shape `F-1`, `F-11` and the T-03 notes kept asking for a stage to catch.
- **A pre-existing bug found by a reviewer, out of scope, and left alone.**
  `seshat scan`'s `--model` and `--no-thinking` are parsed into `ScanOptions` and never
  reach the worker's completion client. It is real, confirmed by execution, and it dates
  from T-11. The code reviewer reported it as a note rather than a finding and it was
  not fixed here — `ask`'s own flags are wired correctly and verified. Recorded so it is
  not rediscovered: it needs its own task, and it is the second time a CLI option has
  been captured but not applied.

### F-45 — harness: a second task drew zero review findings, and both reviewers proved it

- **Date:** 2026-09-10
- **Task:** T-13
- **Bin:** n/a — harness finding
- **Claim:** Second sighting of `F-36`. Both reviewers returned 5/5 with no findings at
  all, and unlike a quiet pass this one carries proof: the boundary reviewer planted
  `eval('1+1')` in `scripts/smoke_codeact.py` and watched DEC-2's control go red at
  `scripts/smoke_codeact.py:216`, and the code reviewer independently reproduced both
  mutation kills the builder claimed rather than trusting the report.
- **Sightings:** **As `F-36`, 2.**
- **Action:** none. Logged as evidence about where the loop's cost now sits.
- **Notes:** The difference between this and `F-36` is worth keeping. Both tasks drew zero
  findings, but this one was preceded by a task-critic stop that changed the task file
  twice before a builder existed — one contradiction between two acceptance bullets, and
  two of four integration checks that already existed as live tests. Zero review findings
  after a corrected brief is a different result from zero review findings after an
  uncorrected one, and the cheap reading — "reviews are finding nothing, cut a reviewer" —
  would be the wrong one to draw from two data points where the expensive step moved
  earlier rather than disappeared.
  Both reviewers also answered "is this covered?" separately from "does this pass?",
  which was written into their briefs because `F-42` was found only by asking the first
  question. That is the second brief in a row to carry it, and it is now worth making a
  standing line in the `orchestrate` skill rather than a per-task instruction.

### F-46 — the `ty` override include list is a hand-maintained list of paths

- **Date:** 2026-09-10
- **Task:** T-13
- **Bin:** 2
- **Claim:** `pyproject.toml`'s `[[tool.ty.overrides]]` `include` list names four agent
  modules by path and gained a fifth entry here (`scripts/smoke_codeact.py`) so that
  `ty`'s `empty-body` diagnostic stops firing on NOOA `...`-body generation points. The
  suppression is narrow and correct — the boundary reviewer confirmed by execution that
  removing the entry produces exactly two `empty-body` diagnostics, both on legitimate
  `@strategy` generation points — but the list is maintained by hand, and nothing checks
  that its entries still exist or that a new generation-point module was added to it. A
  file dropped from the list silently regains the diagnostic; a file that disappears
  leaves a dead entry nobody notices.
- **Sightings:** **As `F-42`'s generalised claim, 2.** `F-42` was `controls/fitness/exec_confinement.py`'s
  hand-listed `SCAN_DIRS`, closed by DEC-2 with a derived scan set. Same shape, different
  tool: a list of paths, maintained by hand, whose drift is invisible because the tool
  keeps passing.
- **Action:** none this task. Widening the list was the right call here and the override's
  own comment invites it.
- **Notes:** The checkable claim is `F-42`'s and it generalises past controls: **a list of
  paths that selects which code a check applies to should be derived from a property of
  the code, not typed out.** Here the property is available — a module containing an
  `@strategy`-decorated `...` body is exactly the set that needs the override. At a third
  sighting this is a real control candidate, and the control would be the same one either
  time: assert that every hand-maintained path list in the repo's config either resolves
  to files that exist or is derived. Holding at two.

### F-47 — the fixture bytes a task file handed the builder did not do what the task said

- **Date:** 2026-09-10
- **Task:** T-14
- **Bin:** 2
- **Claim:** T-14's Context offered one byte string as "bytes that reproduce the crash"
  and the acceptance section required a test where `ast_hash` "reports unreadable". The
  bad byte in those bytes sits inside a `#` comment. It does make today's `read_text()`
  raise, which is the crash — but after the fix, when `ast.parse` is handed the bytes,
  it parses cleanly and the unit hashes normally. A builder reusing the one example the
  task provided would have written the unreadable test against source that is perfectly
  readable, watched it fail for a reason that looks like a bug in their own code, and
  debugged the wrong thing.
- **Sightings:** **`F-25`: 4.** After T-08's inverted `CODEGRAPH_MCP_TOOLS` claim, CT-02's
  `PostToolUse` output channel (`F-40`), and DEC-1's false ruff `S102` rationale (`F-44`).
  **As a planning defect, the ninth** — after `F-1`, `F-22`, `F-24`, `F-29`, `F-34`,
  `F-38`.
- **Action:** soft — caught by the task-critic before a builder existed. The critic ran
  `ast.parse` on both byte strings in a live interpreter rather than reasoning about
  them; the orchestrator reproduced the same two-line probe before taking it to the
  human. The task file now carries three byte strings, each labelled with the test it
  belongs to and a note that they are not interchangeable. No control.
- **Notes:** `F-44` settled at three sightings that this family gets no CI control,
  because no machine can check whether a paragraph of English is true about CPython. Its
  proposed remedy was the habit: **turn the claim into a command and run it.** This is
  the first sighting where that habit was actually in place beforehand — the task-critic
  brief told the critic to verify the encoding claim "by running python, not by
  reasoning" — and it worked on the first outing, which is the cheapest possible place
  for this defect to be found.
  The sharper observation is about *which* claim was wrong. The task's headline claim,
  that `ast.parse` on bytes honours a PEP 263 declaration, was true and had been verified
  in planning and written into an ADR. What nobody checked was the smaller, duller claim
  sitting three lines away: that this specific example demonstrates the failure. The
  verified claim inoculated the unverified one next to it. Worth watching for: a
  document that shows its working for the interesting claim and gets believed on the
  boring one.

### F-48 — a fallback branch nothing could see being deleted, found by mutation again

- **Date:** 2026-09-10
- **Task:** T-14
- **Bin:** 2
- **Claim:** `Graph.decorators`' ast fallback gained `if raw is None: return []` for the
  case where the source cannot be read at all. No test constrained it. The code reviewer
  mutated it to `return None` and the whole suite stayed green, so the branch could have
  shipped returning anything.
- **Sightings:** **As the untested-guard / mutation-testing family, 4** — `F-26` (T-08),
  `F-38` (CT-01), `F-45` (DEC-2), this. Third sighting was reached at `F-45`; the rule of
  three was applied at this one.
- **Action:** fixed in PR #16 by `0c35553`, a test that drives the branch through a real
  `OSError` — the indexed node's `file_path` is a directory, so `read_bytes()` raises
  `IsADirectoryError` — proven red under the reviewer's own mutation and green after.
  Both the builder and the code reviewer re-planted the mutation independently, and the
  reviewer used a distinguishing mutant (`return ['MUTATED']` rather than `return None`)
  to prove the test reaches *this* branch and not an earlier one that also returns `[]`.
  A control-author was dispatched on the rule of three; its ruling is recorded below.
- **Notes:** Two things this sighting adds to the three before it. First, the defect was
  in the *new* half of a change whose old half was carefully tested — the `SyntaxError`
  branch beside it had a test, the `OSError` branch did not, because the task's
  acceptance criteria named the syntax case and not the read case. The suite mirrors the
  criteria, so a criterion that omits a branch produces a branch with no test, every
  time. Second, the reviewer's choice of mutant is itself the technique worth copying: a
  mutation that returns a *distinguishable wrong value* proves which branch the test
  reached, where `return None` alone would not have.
  This family has now found four of the more serious defects in this project and has done
  it entirely through a brief line rather than a gate. `F-45` predicted that if any
  single practice earns promotion from this log it is this one; four sightings later it
  still has not needed a control to work.

### F-49 — Bin 3: a comment describing a column's meaning drifted when the meaning widened

- **Date:** 2026-09-10
- **Task:** T-14
- **Bin:** 3
- **Claim:** The SQL comment above `units.ast_hash` in `src/seshat/ledger/schema.py` said
  a NULL there means the symbol vanished. After this task a NULL also means the source
  was unreadable. The comment was not wrong when written and nothing enforces it.
- **Sightings:** **As `F-32` (a docstring naming a lock that never existed), 2.**
- **Action:** fixed in PR #16 by `6cf2fa5`, comment only. No control, and there should
  not be one.
- **Notes:** Logged as Bin 3 rather than Bin 2 deliberately. A machine can check that a
  comment exists; it cannot check that a sentence of English still describes what the
  code does. The only mechanical version — forbid prose comments near schema — would be
  worse than the disease. What makes this pair mildly interesting is that both sightings
  are comments that were *true when written*, which is the harder kind to catch than a
  comment that was always wrong.

### F-50 — harness: the weak red proof recurred, and the stub meant to prevent it did not

- **Date:** 2026-09-10
- **Task:** T-14
- **Bin:** unbinned harness finding — second sighting of `F-43`
- **Claim:** The builder was briefed with `F-43`'s lesson explicitly — that a red which
  is only "module not found" proves nothing — and it responded by creating
  `src/seshat/source.py` as a stub raising `NotImplementedError` so the new suite would
  fail on behaviour. That worked for `tests/test_source.py`. It did not help
  `tests/test_units.py`, which still failed at *collection* with
  `ImportError: cannot import name 'UNREADABLE'`, because the sentinel the tests import
  did not exist yet. The most important criteria in the task — unreadable versus
  vanished, first-sight recovery, stale claims — were behind that uninformative red.
- **Sightings:** **2** — `F-43` (T-12), this.
- **Action:** soft — the code reviewer was briefed to treat the weak red as the actual
  work of the review, and did: it checked out the red SHA and reasoned per-assertion
  against the unpatched `units.py` to confirm each new assertion would fail for a domain
  reason, then mutation-tested the sentinel guard at HEAD. No fix to the code.
- **Notes:** The interesting part is that the remedy was applied and only half worked. A
  stub cures a missing *module*; it does not cure a missing *name* that the tests import
  from an existing module, and any task introducing a new constant, enum member or
  status value hits the second shape. Curing it fully would mean stubbing every new
  symbol before the red — which starts to be implementation written before the tests it
  is meant to fail against, and is not obviously worth it.
  So the honest reading, two sightings in, is that `F-43`'s real remedy was never the
  stub; it was the reviewer instruction to mutate per-criterion when the red is uniform.
  That is what caught the gap on T-12 and it is what did the work here. The stub is a
  nice-to-have that should not be mistaken for the fix. If a third variant appears, what
  deserves the decision is the reviewer instruction, not the stub.

- **Ruling on the rule of three (2026-09-10, T-14).** The control-author refused the
  family and authored something narrower. Its reasoning, which I accept: the general
  claim — "a branch whose deletion no test notices" — is mutation testing, which `F-38`
  already rejected as slow and noisy, and four sightings of it working as a brief line
  is evidence the brief line is the remedy. So no control governs the family. What it
  did instead was check `F-45`'s narrower candidate against today's tree and find it
  live: `controls/fitness/exec_confinement.py` got its 26 tests after `F-45`, but its
  sibling `controls/fitness/view_naming.py`, which backs `DEC-0` and has gated every
  build since T-01, still had none. That is the same defect `F-45` logged, still
  present, in the one place where an untested branch silently disables enforcement for
  everybody. `DEC-3` therefore says only this: every module under `controls/fitness/`
  has a non-empty test module under `tests/controls/`. Presence, not behaviour — it
  cannot fire on correct code. It ships in its own PR, because a rule change is a diff a
  human reviews, never a side effect of a triage commit.

### F-51 — the acceptance suite shelled out to an undeclared binary, and only CI knew — again

- **Date:** 2026-09-10
- **Task:** T-14
- **Bin:** 2
- **Claim:** Four of T-14's acceptance tests build a throwaway repo and run
  `codegraph init` in it through `subprocess`. That binary is installed on the dev
  machine and on no GitHub runner, so the whole suite was green locally, both reviewers
  ran it green in two separate trees, and CI failed on PR #16 with
  `FileNotFoundError: [Errno 2] No such file or directory: 'codegraph'` on all four,
  taking `make governance` check 9 down with them.
- **Sightings:** **2** — `F-40` (the first, same mechanism, same log), this.
- **Action:** fixed on the PR branch: `.github/workflows/ci.yml` now installs
  `@colbymchenry/codegraph@1.6.0` on a pinned node, before the first step that runs
  pytest. The human chose installing the real indexer over the two cheaper answers —
  a committed fixture index, or a hand-built sqlite one — because the crash this task
  fixes is about what the real indexer produces for an undecodable file, and a
  stand-in index would assume the very thing the test exists to show. CI green on
  `06e1cc7`. No control.
- **Notes:** Two sightings, and what they share is not carelessness but a blind spot
  with a specific shape: **every agent in this loop verifies by execution on the same
  machine, and that machine has tools the deployment target does not.** `F-41` logged
  that observation about the harness; this is it producing a red build for the second
  time. Three verifications — builder, boundary reviewer, code reviewer, in three
  separate trees — cannot catch it, because all three inherit the same PATH. The
  cheapest checkable form is narrow and worth remembering at a third sighting: **a test
  that shells out to a binary names it in the CI workflow.** A grep for `subprocess` in
  `tests/` against the workflow's install steps would have caught both instances.
  Recorded while fixing this one: the builder swept the rest of the suite for the same
  shape and found `uv`, `git` and `sys.executable`, all of which a runner has. So the
  gap today is exactly one tool, and it is now declared.
