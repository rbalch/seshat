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
