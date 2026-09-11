# Seshat

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

## Using Seshat

### Install

Seshat is a Python 3.13 package with one console script, `seshat`. It needs two things
on `PATH`: `uv` and `codegraph` (`npm install -g @colbymchenry/codegraph`), which builds
the code graph every scan reads.

Inside the devcontainer both are already there, so:

```bash
uv sync                     # installs the package and its deps into .venv
uv run seshat --help
```

Outside the container, from a clone of this repo:

```bash
uv tool install .           # puts `seshat` on your PATH
# or, for a checkout you are editing:
uv sync && source .venv/bin/activate
```

Every command that calls a model also needs `LLM_HOST` (see
[Running against the Spark](#running-against-the-spark)). The read-only commands need
nothing but the ledger.

### Scan a repo

```bash
LLM_HOST=http://spark.local:8000 seshat scan /path/to/repo
```

Prefixing the variable each time gets old. Export it once per shell, or keep a `.env`
and load it yourself — Seshat never reads a `.env` file on its own:

```bash
export LLM_HOST=http://spark.local:8000      # once per shell
# or
echo 'LLM_HOST=http://spark.local:8000' > .env
set -a; source .env; set +a                  # then plain `seshat scan ...` works
```

`.env` files are gitignored here already.

One scan does, in order: index the target with `codegraph init` (or `codegraph sync` if
it is already indexed); open the ledger; seed the target's `README.md` and `docs/**/*.md`
into working memory as *hypotheses*; enumerate every class, function, method and module
as a **unit** and diff them against the last run; rerun the verifiers for anything that
moved; then hand units to worker agents until a budget runs out. Each worker proposes
claims about its unit, has a Python verifier written for each one, and runs it. After
the pool drains, a reflection pass groups confirmed claims into concepts.

Progress prints one line per unit:

```
[3/40] orders.OrderRepository.get +4 -1 tokens=18211 elapsed=41.2s
```

and the final line names the run and how it ended. `stopped_complete` means the queue
drained; `stopped_budget` means a limit was hit first. Both exit 0. `failed` exits 1.

Flags, all optional:

| flag | default | meaning |
|---|---|---|
| `--units N` | 5 | stop after N units |
| `--minutes M` | 10 | stop after M minutes |
| `--tokens T` | 200000 | stop after T tokens |
| `--workers W` | 1 | concurrent workers |
| `--full` | off | rerun every verifier, not just the ones touching changed units |
| `--no-thinking` | off | disable model thinking |
| `--model NAME` | env | override the model for this run |

The defaults are deliberately small. Scans are incremental, so re-running the same
command grows the ledger; raise `--units` once you trust the output.

### Read the ledger

None of these touch a model. All take the repo path first.

```bash
seshat status  REPO                      # the last run: status, budgets, counts
seshat units   REPO [--changed]          # every unit, with confirmed/refuted/stale counts
seshat claims  REPO orders.OrderRepository.get   # one unit's claims, with ids and citations
seshat concept REPO "connection pooling"         # a concept by id or search, with its evidence
seshat drift   REPO                      # stale claims and concepts, grouped by unit
```

A claim line reads `[confirmed] <id> <text>  — <unit> <file>:<start>-<end> @<sha> [pass]`.
`[STALE]` on the end means the code moved under it, or its verifier last failed. `drift`
says "No drift." when the ledger is current.

### Ask questions

```bash
LLM_HOST=... seshat ask REPO -q "What talks to the database?"
LLM_HOST=... seshat ask REPO               # prompt loop; `exit` or Ctrl-D to leave
```

The answer agent reads only the ledger, never the source. Every sentence must cite a
claim id; a sentence citing nothing, or an id the ledger does not know, is stripped
before printing rather than shown as fact. An answer that loses every citation collapses
to "Nothing in the ledger answers that."

### What it writes

Everything Seshat produces lands **inside the target repo**, in two directories:

| path | what | keep? |
|---|---|---|
| `.seshat/ledger.db` | SQLite: runs, units, claims, verifiers, concepts, citations | yes — this is the product; it never decays |
| `.seshat/memory.db` | working memory: seeded docs, hypotheses, dead ends | disposable; decays on its own |
| `.codegraph/` | the tree-sitter code graph | build output; `codegraph sync` refreshes it |

The first scan appends `.seshat/` to the target's `.gitignore`. `.codegraph/` is
codegraph's own concern. Nothing is written outside the target, and nothing is written
to this repo when you scan another one.

Delete `.seshat/` to start over. Delete `.codegraph/` and the next scan re-indexes from
scratch.

### Configuration

All by environment variable. Nothing reads a `.env` file.

| variable | required | default |
|---|---|---|
| `LLM_HOST` | for `scan` and `ask` | — |
| `SESHAT_MODEL` | no | `hosted_vllm/qwen3.8-27b` |
| `SESHAT_MODEL_WORKER` | no | `SESHAT_MODEL` |
| `SESHAT_MODEL_VERIFIER_AUTHOR` | no | `SESHAT_MODEL` |
| `SESHAT_MODEL_REFLECTION` | no | `SESHAT_MODEL` |
| `SESHAT_MODEL_ANSWER` | no | `SESHAT_MODEL` |

`LLM_HOST` is the base URL of an OpenAI-compatible server; Seshat appends `/v1`.

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
