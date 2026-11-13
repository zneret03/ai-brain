# CLAUDE.md — ai-brain

ai-brain is a cross-repo code graph for a workspace of git repos that sit side by side. It parses every
registered repo at `origin/<ref>`, links what the code states (GraphQL fields and operations, routes, Kafka
topics, tables, jobs, pages, tests, plans and notes) into Neo4j, and answers a coding agent's question in a few
lines of `repo/path:line` before it greps. The contract, what it answers, its output and exit codes, is
`docs/AI_BRAIN.md`; setting it up for a workspace is `README.md`.

## Layout

```
ai-brain/                     the Python package and everything it needs
  src/ai_brain/               the CLI (cli.py), the queries (api.py), the indexer, the parsers (extract/),
                              the linkers (link/), the Neo4j driver and Cypher (graph/), the edit hook (hook.py)
  projects/_template/         the project.toml to copy for a workspace; projects/<name>/ holds one per workspace
  views/                      saved Cypher views for Neo4j Browser
  tests/                      pytest; the fixtures build throwaway git repos
  compose.yaml                Neo4j in Docker
  setup/install-docker.sh     Docker Engine on Ubuntu or WSL2
bin/ai-brain                  the CLI
bin/ai-brain-up               sets up, starts and updates everything; safe to re-run
bin/ai-brain-bootstrap        the venv, .env and var/
bin/ai-brain-hook             the PostToolUse hook that shows a file's card after an edit
bin/install.sh                links .claude/ entries into the workspace root's .claude/
bin/help                      lists every script here and what it is for
.claude/skills/ai-brain/      the /ai-brain skill
docs/AI_BRAIN.md              the contract
```

## Working on this repo

- **Python lives only in `ai-brain/.venv`**, which `bin/ai-brain-bootstrap` creates. Never `sudo pip` or
  `pip install --user`.
- **Before a commit that touches `ai-brain/`**, from the `ai-brain/` folder: `.venv/bin/pytest` and
  `.venv/bin/ruff check`. This repo has no CI, so these two are the gate.
- **Reads go through git objects at `origin/<ref>`, never the working tree** (`extract/files.py`). The one
  exception is a `sprints` knowledge repo's `sprints/`, which is gitignored by design and read from disk
  (`link/plans.py`). Keep it that way: an index of uncommitted edits would answer for code nobody pushed.
- **Facts hold names and paths only**: never a table row, an `.env` value or a credential.
- **A project's own conventions belong in its `project.toml`**, not in the code: ticket prefix, own hosts,
  name prefixes, schema snapshots. A linker reads them from `ctx.project`.
- **One fact, one place.** The contract lives in `docs/AI_BRAIN.md`, setup in `README.md`; the skill and the
  CLI help link to them rather than restate them.
- **Skill and help text is a contract.** A model reads it and follows it literally. Prefer a named file path
  over a description, an example over an adjective, and a failure mode over a principle.

## Change discipline

The failure mode is not doing too little. It is a simple change arriving as a new concern, a wrapper and four
hundred lines of prose.

- Make the smallest change that satisfies the request. Do not refactor, rename, reformat or "improve" code you
  were not asked to touch.
- Do not create a file unless it is needed. Prefer editing an existing one.
- Do not add an abstraction (an interface, a base class, a factory, a wrapper, a generic helper) for a single
  use. Inline first.
- Do not write a second copy of what the repo already does. Reuse or extend it, or extract it so both callers
  share one copy: the second real call site is the trigger, not the third. Code that only looks alike, and
  would change for different reasons, stays apart.
- Do not add error handling, fallbacks, retries or guards unless the input is untrusted or the request asks
  for it. No `try`/`except` around code that cannot raise.
- Do not add caching, memoization or batching without a stated performance need.
- Match the surrounding code's style, naming and patterns.
- If a change seems to need more than about 20 lines or a new file, stop and propose the plan first.
- Comment only the non-obvious: a decision and why the obvious alternative was rejected, a constraint the code
  cannot state, a trap for the next reader. One or two lines inline, one to four for a doc block.

Local, untracked instructions for your own setup can sit in `CLAUDE.local.md`.
