# CLAUDE.md — ai-brain

Two things live here, and no product code. The **ai-brain** is a cross-repo code graph for a workspace of git
repos that sit side by side. It parses every registered repo at `origin/<ref>`, links what the code states
(GraphQL fields and operations, routes, Kafka topics, tables, jobs, pages, tests, plans and notes) into Neo4j,
and answers a coding agent's question in a few lines of `repo/path:line` before it greps. The **harness** is
the skills, agents and command that plan, build, review, hunt and demo a ticket across those repos, asking the
brain first. The facts about your workspace (its repos, stack, tracker, QA environment, e2e suite and the lessons
its tickets taught) live in `profile/`, gitignored; `profile.example/` shows the shape. The brain's contract,
what it answers, its output and exit codes, is `docs/AI_BRAIN.md`; setting up a workspace is `README.md`.

A ticket goes through three steps, each started by the engineer: `/plan` writes the plan, `/dev` builds it,
`/branch-review` reviews what was built. A ticket is often a sub-ticket of a parent feature, and the parent is
where the shape is (`profile/TRACKER.md` § Ticket family).

## The flow

```
/plan PROJ-123 ── reads the ticket, its parent and every sibling; maps the files with the
  │               ai-brain and has backend and frontend agents verify the map; asks what the reading
  │               could not settle; cuts the ticket branches; writes sprints/<sprint>/plan/PROJ-123.md
  │               (parity + a test per row, files to touch, services, numbered action items, a demo
  │               item), kept on this machine: sprints/ is gitignored. No code.
  │
/dev PROJ-123 ─── no plan, no build. Works on the ticket branches /plan cut:
  │   Before ── shoots the old behaviour on the untouched branch, real clicks on a test client
  │   Build ─── the action items in delivery order, each with the test its parity row names
  │   Gate ──── scoped rubocop / rspec / lint / type-check / jest per touched repo
  │   Check ─── asks which entry point to check on (profile/STACK.md § Entry points). Real
  │             accounts, real buttons, no seeders; one scenario per AC as its persona, then the hunt
  │             for the edge and worst cases users hit. A broken scenario goes back to Build with a
  │             regression test.
  │   Evidence ─ screenshots, mp4 and GIF in the e2e repo's evidence folder (profile/E2E.md § Evidence)
  │   Ship ──── behind one yes: commits, pushes, paired PRs opening with # Demo, the plan's Log
  │
/branch-review PROJ-123 ── the ai-brain first; stops with an error when it does not answer. No code written:
      Read ──── the family's AC, the plan and its Decisions, every branch the ticket has, without a switch
      Reach ─── impact --diff <repo>@<tip>, then impact, trace, find, history, notes per file and interface
      Check ─── scoped rubocop / eslint / type-check / react-doctor; specs only where the tip is checked out
      Lanes ─── qa-backend (Rails) and qa-frontend (React) in parallel, on each repo's own rules
      Verdict ─ Request changes for what breaks or misses an AC; Suggestions (KISS, DRY, approach) never block
      Record ── sprints/<sprint>/reviews/PROJ-123.md, which the brain reads; GitHub only on a yes
```

`/pr-review` is **not** part of this. It stays a manual step the user runs on the finished PR.

`/bug-hunt` runs `developer`, and `/branch-review` runs `qa-backend` and `qa-frontend` as its two lanes.
No command runs `project-manager`, `qa-design` or `qa-e2e`; they stay in `.claude/agents/` for an ad-hoc run.

## The second loop — `/bug-hunt`

```
Scope ── read the diff across every repo; derive the routes a browser can reach, the
  │      personas that reach them, the operations to fault, and the scenario families
  │      worth running. What no browser can show is recorded as unreachable, not hunted.
  │
  ├─► Hunt ── Playwright hunters, ONE AT A TIME, one per scenario family. They probe,
  │     │      promote what pins real behaviour into a tagged spec, and report the clean
  │     │      scenarios as well as the breaks. They do not fix.
  │   Fix ── the developer patches the confirmed findings; one writer per repo, and a
  │     │    regression test in the repo that owns the defect, not only in Playwright.
  │   Gate ── scoped rubocop / rspec / lint / type-check / jest on the repos it touched.
  │     │     A red gate sends the round straight back to the developer — no browser pass
  │     │     over a tree that does not compile.
  │ Verify ── a hunter RE-DRIVES every patch in the browser, and hunts the patch itself
  │     │     for the states it may have hidden. A fix nobody re-drove stays a claim.
  └─────┘ rounds until nothing fixable is left, or --rounds runs out (default 3)
          │
Evidence ── the e2e repo's evidence folder (profile/E2E.md § Evidence) with notes.md,
            bug-hunt.md and the named screenshots — written on EVERY exit path, then
            checked on disk by a second agent.
```

It starts where `/dev` stops: the feature is built and its specs are green, and the question is what
breaks when someone uses it. Three things separate it from `/dev`'s browser check:

- **It hunts with seeded, repeatable Playwright runs, and it fixes in a loop.** `/dev` clicks through by
  hand on real data; here hunters seed, the developer patches, and a hunter re-drives every patch.
- **The browser runs alone.** The suite runs one worker against one shared database whose seeds clear and
  recreate (`profile/E2E.md` § Suite). Every browser stage in `bug-hunt.js` is a serial `for` loop for that
  reason — **never** `parallel()`. Two hunters at once seed over each other and report each other's wreckage
  as defects.
- **The evidence folder is the deliverable**, findings or not. A hunt that found nothing still has to show
  which states it drove, or it cannot be told apart from a hunt that stopped early. The workflow's last
  phase checks the folder on disk rather than trusting the agent that wrote it — the same reflex as
  `/dev`'s "no plan, no build".

The write-ups sit beside the ticket's plan in `sprints/<sprint>/`: the hunt goes to `reports/`, and a finding
left open gets a live entry in `bugs/`. A finding this run fixed does not get a bug file — `bugs/` is a
list of what is broken now, not an archive.

## Layout

```
.claude/skills/       plan/          — /plan: a ticket link → questions → the plan doc + ticket branches, no code.
                                       A skill, not a command file, so it replaces the built-in /plan
                      dev/           — /dev: the plan → build the action items → gates → a real-click check on
                                       the local stack → before/after evidence → paired PRs on a yes
                      branch-review/ — /branch-review: a ticket's branches → the brain (an error without it) →
                                       AC + plan → reach, checks, Rails and React lanes → findings by reason
                                       with samples → a review round in sprints/<sprint>/reviews/, GitHub on a yes
                      qa-demo/       — /qa-demo: tickets at the QA gate (profile/TRACKER.md § QA gates) → a
                                       replication video on the shared environment with a visible cursor →
                                       one tracker comment per ticket. cursor.mjs, media.sh, attach.mjs
                      ai-brain/      — /ai-brain: the brain's verbs for ad-hoc cross-repo questions
.claude/agents/       project-manager · developer · qa-backend · qa-frontend · qa-design · qa-e2e
.claude/commands/     bug-hunt.md    — the /bug-hunt command, owns git and the write-ups
.claude/workflows/    bug-hunt.js    — the hunt/fix/verify loop
ai-brain/                     the brain's Python package and everything it needs
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
bin/plan-doc                  finds and shows the docs in sprints/, makes a sprint's folders on first use, imports an archive
bin/install.sh                links the .claude/ entries into the workspace root's .claude/
bin/help                      lists every script here and what it is for; each script takes --help
docs/AI_BRAIN.md              the brain's contract: what it answers, output, exit codes, the trust rule, set up
docs/PLANNING.md              the planning contract: stack scoping, parity + tests, action items, the visualization
docs/PRACTICES.md             the house rules for planning, writing and reviewing code — KISS and DRY, system
                              design, data and queries, caching, the contract, Rails, React, tests; the brain indexes it
docs/DESIGN_PARITY.md         the Figma contract: nodes, spacing, tokens, tolerances, the fix cycle
docs/JIRA_COMMENTS.md         how every tracker comment is written: plain words, short headings, a kind tone
docs/SPRINTS.md               the sprints/ layout, and what the brain reads from each section
profile.example/              the shape of a workspace profile, with neutral examples; copy it to profile/
profile/                      gitignored, yours: REPOS, MICROSERVICES, DEFINITIONS, GRAPHQL_SURFACES, CODE_MAP,
                              STACK, TRACKER, E2E, QA and LESSONS — the facts the skills and agents read
sprints/                      gitignored, made by the first /plan: every plan, Dev report, hunt report, bug and
                              review round, one folder per sprint
```

## Install

The harness resolves skills and agents from the **session's** `.claude/`, and the work spans repos, so
sessions run from the workspace root:

```
ai-brain/bin/install.sh          # per-entry symlinks into the workspace root's .claude/
ai-brain/bin/install.sh --status
ai-brain/bin/install.sh --copy   # if symlinked agents are not picked up
```

Symlinks mean an edit here takes effect immediately. With `--copy`, re-run after every edit. The script
never overwrites a file it did not create. Then copy `profile.example/` to `profile/` and fill each page
(`profile.example/README.md`); a skill that needs a page you have not filled says which one.

## Working on this repo

- **Every path in the skills, agents, command and docs is relative to the workspace root**, not to this
  repo: `ai-brain/bin/plan-doc`, `ai-brain/profile/STACK.md`. The agents run with the workspace root as their
  working directory. This file's own paths are relative to the repo.
- **This repo holds no product code.** Every plan, Dev report, hunt report, open bug and review round lives in
  `sprints/`, gitignored and each dev's own (`docs/SPRINTS.md`), and the brain indexes them, with the pages in
  `docs/` once they merge and the `profile/` pages from disk.
- **Python lives only in `ai-brain/.venv`**, which `bin/ai-brain-bootstrap` creates. Never `sudo pip` or
  `pip install --user`.
- **Before a commit that touches `ai-brain/`**, from the `ai-brain/` folder: `.venv/bin/pytest` and
  `.venv/bin/ruff check`. This repo has no CI, so these two are the gate.
- **Reads go through git objects at `origin/<ref>`, never the working tree** (`extract/files.py`). The two
  exceptions are a `sprints` knowledge repo's `sprints/` and `profile/`, both gitignored by design and read from
  disk (`link/plans.py`). Keep it that way: an index of uncommitted edits would answer for code nobody pushed.
- **Facts hold names and paths only**: never a table row, an `.env` value or a credential.
- **A project's own conventions belong in its `project.toml`**, not in the code: ticket prefix, own hosts,
  name prefixes, schema snapshots. A linker reads them from `ctx.project`.
- **One fact, one place.** A rule belongs in exactly one `docs/` page, a fact about the workspace in exactly
  one `profile/` page, and the skills and agents link to it. Do not restate a profile fact inside a skill or
  an agent. The brain's contract lives in `docs/AI_BRAIN.md`, setup in `README.md`; the CLI help links to them.
- **The profile is grounded in named sources.** Each page says where it was condensed from, a wiki page or the
  repos themselves. When you revise one, re-read the source rather than editing from memory, and say what you
  checked it against.
- **Skill, agent and help text is a contract.** A model reads it and follows it literally. Prefer a named file
  path over a description, an example over an adjective, and a failure mode over a principle.
- Keep the workflow script free of `Date.now()`, `Math.random()` and argless `new Date()` — they throw in a
  workflow, because they would break resume.

## Change discipline

Binds `/dev` on every item, and the `developer` agent `/bug-hunt` runs. The failure mode is not doing too
little. It is a simple change arriving as a new concern, a wrapper and four hundred lines of prose. It is KISS
and DRY applied to this harness; `docs/PRACTICES.md`, "KISS and DRY", has the signals with examples, and
`/plan`, `/dev` and `/branch-review` all hold work to it.

- Make the smallest change that satisfies the request. Do not refactor, rename, reformat or "improve" code you
  were not asked to touch.
- Do not create a file unless it is needed. Prefer editing an existing one.
- Do not add an abstraction (an interface, a base class, a factory, a wrapper, a generic helper) for a single
  use. Inline first.
- Do not write a second copy of what the repo already does. Reuse or extend it, or extract it so both callers
  share one copy: the second real call site is the trigger, not the third. This is the one exception to the
  first rule: the extract may move code you were not asked to touch. Code that only looks alike, and would
  change for different reasons, stays apart. The search and the verdicts: `.claude/skills/dev/SKILL.md`,
  "Reuse before you write".
- Do not add error handling, fallbacks, retries or guards unless the input is untrusted or the request asks
  for it. No `try`/`except` or `rescue` around code that cannot raise.
- Do not add caching, memoization or batching without a stated performance need.
- Match the surrounding code's style, naming and patterns. Do not introduce a new pattern.
- If a change seems to need more than about 20 lines or a new file, stop and propose the plan first. In
  `/dev` that means a new action item or an open question in the plan, asked before it is built, not building
  it and explaining afterwards.
- Comment only the non-obvious: a decision and why the obvious alternative was rejected, a constraint the code
  cannot state, a trap for the next reader. One or two lines inline, one to four for a doc block; a workspace's
  own `CLAUDE.md` may set a tighter budget.

## Branching — every modified repo, no exceptions

**A repo that was modified gets its own branch, and a shared branch is never a push target.** Not `main`, not
`staging`, not `development`, not `develop` — in any repo of the workspace, the e2e repo included.

`sprints/` in this repo never commits: it is gitignored, so plans, Dev reports, hunt reports and bug files stay
on each dev's machine and never reach a branch (`docs/SPRINTS.md`). Everything else, in this repo or any other,
follows the rule above.

- One branch name across every repo a ticket touches: `{name}/{key}-v{n}`, e.g. `you/proj-123-v1`. The same
  name in each repo is what makes the paired change readable a sprint later.
- Which repos get a PR on the branch, and which only get the branch pushed with its compare URL reported (by
  default the e2e repo, with no direct commit to `main` either): `profile/REPOS.md` § Branches and commits.
- `git push origin main` is not a command `/dev` runs. If any step is about to write to a shared branch, the
  branch step was skipped — stop rather than pushing.

The rule is about review surface, not ceremony: a change that lands straight on a shared branch has no diff
anybody was asked to read.

## Two things `/dev` deliberately does not do

- **It does not commit, push or open a PR without a yes.** One confirmation covers the commits, the pushes,
  the PRs and the plan's Log.
- **It does not seed.** Its check uses real accounts and real clicks on a test client (`profile/STACK.md`
  § Test data), so it shows what a user would see. Seeded, repeatable runs and tagged Playwright specs belong to
  `/bug-hunt` and the e2e suite (`profile/E2E.md` § Suite). Exploratory probes there go in `tests/probes/`,
  which logs rather than asserts.

## The browser check is mandatory

A change nobody clicked through in a real browser is not verified, however green the unit suites are. `/dev`
runs its check on every ticket a browser can show. A stack that will not start is reported as not run, with the
command that fixes it: never a failure blamed on the code, and never a pass inferred from a suite that did not
run.

## Every check hunts, it does not only confirm

Confirming the criteria finds what is wrong on the page; constructing the scenarios users will hit finds what
is wrong in the model. `/dev` plays each criterion as its persona, then the hunt: double clicks, refreshes, two
tabs, the wrong persona at a URL, empty and zero states, boundaries, a dropped network. It reports the
scenarios that came back **clean** as well as the ones that broke, and a broken one is fixed with a regression
test and re-driven, or written into the plan.

Local, untracked instructions for your own setup can sit in `CLAUDE.local.md`.
