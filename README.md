# seshat

<img src="docs/images/seshat-logo.jpg" alt="Seshat" align="right" width="220">

Seshat surveys a codebase you did not write and produces a **ledger of verified claims**
about it. A claim is one falsifiable sentence — "`Executor.run` never spawns a
subprocess" — paired with executable Python that re-checks it against the code graph.
Claims that pass are rolled up into concepts with citations down to file and line;
claims that fail are kept too, because a model misreading code is data. Because every
claim carries its own check, a later run detects drift without rescanning the repo, and
`seshat ask` answers questions from the ledger with a citation on every sentence.

The name is the Egyptian goddess of measurement and record keeping, who stretched the
cord to survey a plot before anything was built on it.

Read [`docs/specs/docs/plan.md`](docs/specs/docs/plan.md) for the phase-one design,
[`decisions.md`](docs/specs/docs/decisions.md) for every settled question, and
[`nooa-research.md`](docs/specs/docs/nooa-research.md) for the background.

## Development

All work happens inside the devcontainer. `uv` manages dependencies and the Python
toolchain itself — the image ships no system Python.

### Container credentials

`~/.ssh` and `~/.config/gh` in the container are **external Docker volumes**, `dev-ssh`
and `dev-gh`, shared by every project on the machine rather than scoped to this one.

They are not bind mounts of your host dotfiles on purpose. A host ssh config is often a
symlink to a path that does not exist inside the container, and a bind mount would hand
the container every key you own rather than the one you meant to give it.

Run this on the host after the first `make build`:

```bash
make init KEY=~/.ssh/your-github-key
```

It creates both volumes, installs the key as `id_github`, proves it against GitHub, runs
`gh auth login` if needed, and builds the code graph. Every step is skipped if it is
already done, so re-running is safe and `KEY` is only read the first time. On a machine
that has already been set up, `make init` just confirms everything and indexes the new
repo.

Being external, the volumes survive `docker compose down -v`. The one wrinkle: a volume
is seeded from the image **only while it is empty**, so once credentials are in place,
changing the starter ssh config in `dev.Dockerfile` will not reach them. Edit the file
inside the container, or remove the volume and set it up again.

### Updating tools

Every CLI installs under `$HOME`, so updating one needs no rebuild and no sudo:

```bash
npm update -g @colbymchenry/codegraph
claude update
uv self update
```

Those updates live in the container layer, not a volume — a rebuild resets them to the
versions pinned in `dev.Dockerfile`.

### Commands

```bash
make check       # the single gate: controls → views --check → governance → tests
make views       # regenerate governance/views/RULES.md + registry.json
make governance  # integrity + drift check
make controls    # every controls/fitness/*.py, plus ruff and ty
make test        # pytest
```

## Running against the Spark

Every agent turn in this repo reads its model from `Settings` (`src/seshat/config.py`),
which requires `LLM_HOST` — the base URL of the vLLM server on the DGX Spark, e.g.
`http://spark.local:8000`. Nothing here ever reads a `.env` file itself; export it in
your shell.

Before pointing the worker or answer agents at the Spark, run the smoke script: it
drives a two-tool NOOA CodeAct agent (`add`, `lookup`) through `hosted_vllm/qwen3.8-27b`
twice — thinking on, then `--no-thinking` — and exits 0 only if both tools were called
both times.

```bash
LLM_HOST=http://<spark-host>:<port> uv run python scripts/smoke_codeact.py
LLM_HOST=... uv run python scripts/smoke_codeact.py --strategy pure-python  # PurePythonStrategy, for comparison
```

The integration test suite includes the smoke checks above plus the live
`VerifierAuthor.author` and `Worker.survey` checks (`tests/agents/test_verifier_author.py`,
`tests/agents/test_worker.py`):

```bash
LLM_HOST=http://<spark-host>:<port> uv run pytest tests/integration -m integration
```

Without `LLM_HOST` set, `uv run pytest tests/integration -q` collects the same tests and
skips every one — always exit 0, never a silent zero-tests-collected pass.

**A failing smoke is not a bug in this script.** It is the finding plan §8 exists to
produce: whether a 27B model on this hardware can reliably drive CodeAct's native
tool-calling loop, or whether the worker and answer agents belong on
`PurePythonStrategy` instead. Record the outcome in the spec's open questions and change
the strategy in config — never add a retry or a fallback here to make a flailing model
look like it passed.

## How work gets done

```
/planner                 plan with the agent → docs/specs/, tasks/<slug>/, docs/adr/ if earned
/orchestrate tasks/<slug>  each task: worktree → acceptance tests first → build → two reviews
                         → one squashed commit → PR to develop → findings triaged into the ledger
```

Branches: `main` and `develop`. Agents open PRs to `develop`, one per task. `develop` to
`main` is yours. The task file format is in `tasks/README.md`; the whole loop is in
`AGENTS.md`.

## Governance

This repo runs a ledger governance harness. Architectural rules live as decisions under
`governance/decisions/`, each backed by an executable control under `controls/`, and CI
fails on any drift between them.

- **Agents read `governance/views/RULES.md`** — generated, live rules only. Never read
  `governance/decisions/` for rules; it retains superseded records on purpose.
- **`AGENTS.md`** is the hand-written contract: architecture, working context, and how
  work gets done here.
- **`docs/governance-harness.md`** explains why the harness exists and how to tell
  whether it is earning its keep.
- **`docs/ledger-findings.md`** is the experiment log.

Change a rule by supersession, never by edit. See the `ledger-ops` skill.
