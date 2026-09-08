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
- **Sightings:** 1
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
