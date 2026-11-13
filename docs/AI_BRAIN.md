# AI BRAIN — the contract

A Neo4j graph of every repo registered for a workspace, read at `origin/<ref>`. It answers in a few lines what
would otherwise take a grep across every repo: who consumes a GraphQL field, which frontend operation reaches which
backend engine, what already does what a ticket needs, what a branch's diff reaches. The code is in
`ai-brain/ai-brain/`, the entry points in `ai-brain/bin/ai-brain*`, the skill in `ai-brain/.claude/skills/ai-brain/`.

Every path is relative to the workspace root: the folder that holds this checkout and the repos it indexes.
`ai-brain <verb>` means `ai-brain/bin/ai-brain <verb>`.

## What it answers, and what it does not

It holds the repos listed in `ai-brain/ai-brain/projects/<name>/project.toml`, each with a role:

| Role | What it reads |
| --- | --- |
| `monorepo` | apps under `apps/<dir>/` and engines under `gems/<engine>/` (any folder with a `.gemspec`), discovered rather than listed |
| `app` | one application repo |
| `pilet` | one micro-frontend repo |
| `shell` | the frontend host that loads the micro-frontends |
| `library` | a shared library, read at the tag the monorepo's `Gemfile.lock` pins when `[externals] from` names that lockfile |
| `e2e` | an end-to-end suite; `@PROJ-123` tags in its tests link specs to tickets |

And knowledge repos, each with a kind: `notes` (notes whose frontmatter `sources[]` name code), `sprints` (the
plans, reports, bugs and review rounds in its `sprints/`, read from disk, plus its `docs/` pages at `main` and
its `profile/*.md` pages from disk), and
`plans` (an archive of older plans, read from every branch head). A plan's Files to touch become `PLANS` edges,
its Dev report's Files changed `CHANGED` edges, and its parity and action-item tables its open gaps and items.
Every `repo/path:line` that a plan, a review, a `docs/` page or a `profile/` page cites becomes a `CITES` edge, so
`notes <file>` lists the notes, past reviews and profile pages that name a file. With `[tickets] prefix` set, git adds who committed each
ticket's work. The edge types are listed in `ai-brain/ai-brain/src/ai_brain/model/__init__.py`, `EDGES`.

It draws an edge only where the code states one. A Ruby call on a receiver of unknown class gets an edge only
when the method name is defined once in that engine, marked `(inferred)`, and so does a call in any other language
whose name was neither imported nor defined in its file. `send`, callbacks, `delegate`,
`method_missing`, and functions passed through props or context have no edge. The languages it parses, and what it
reads in each, are in `ai-brain/docs/LANGUAGES.md`.

## The verbs

`ai-brain --help` lists every verb with what it answers, and `ai-brain <verb> --help` its options. The table
with one example per verb is in `ai-brain/.claude/skills/ai-brain/SKILL.md`. In short: `surface` and `find`
search interfaces and code by words; `impact`, `consumers`, `trace` and `notes` start from a field, operation,
route, topic, table, symbol or file; `impact --diff <repo>...` starts from a branch: `<repo>` is the checkout
as it stands, committed, uncommitted and untracked, `<repo>@<ref>` a branch's commits wherever the checkout sits,
and `<repo>@<base>...<ref>` a branch stacked on another; `ticket`, `sprint`, `gaps`, `history`, `who` and
`related` answer what was planned, built and left open, and who built it; `fresh`, `status` and `doctor` report
the index; `index`, `schema` and `cards` maintain it.

## Output and exit codes

One header line, then plain lines of a name and a `repo/path:line`, at most 30, then
`+N more: <command> --all` when cut. The header names the commit each repo was read at, the commit the Rails
facts came from (`facts@`), coverage, the index age, and the repos that moved since (`stale:`).

| Exit | Prints | Means |
| --- | --- | --- |
| 0 | the answer, or `none` | answered |
| 3 | `ai-brain: not run (not set up: …)` | no venv, or never indexed |
| 4 | `ai-brain: not run (Neo4j unreachable …)` | Neo4j does not answer; `fresh` and `index` start it first, the query verbs do not |

On 3 or 4, a skill or agent copies the `not run` line into its record and takes the grep path it has without the
brain. A step that must not run blind, such as a review of what a change reaches, stops with the error instead.

## The trust rule

A brain line is a lead, never a verdict. Open its `path:line` before it becomes a claim in a plan, a review or a
pull request. A stale brain still answers and its header says so; the lead is still checked at the file.

## The project file

`ai-brain/ai-brain/projects/<name>/project.toml` lists one workspace's repos and knowledge repos, and the
conventions the code reads from it rather than hardcodes: `[tickets] prefix`, `[names] strip_prefix` and `apps`,
`[http] own_hosts` and `[[graphql.snapshots]]`. Every key is in `ai-brain/README.md` (The project file), and the
template documents each one inline. Projects share one Neo4j, kept apart by a `project` property. Every verb
takes `--project`, and defaults to the project whose `root` holds the current directory.

## The plans it reads

A `sprints` knowledge repo keeps one folder per sprint. Everything under `sprints/` is meant to be gitignored,
each person's own, and the brain reads it from disk on every index:

```
sprints/<sprint>/plan/<KEY>.md        a ticket's plan; chore-<slug>.md for work with no ticket
sprints/<sprint>/reviews/<KEY>.md     review rounds
sprints/<sprint>/reports/<name>.md    test or hunt reports
sprints/<sprint>/bugs/<name>.md       bugs still open
```

From a plan it reads:

- the header: `**Ticket:** [PROJ-123](<link>) · <type> · <status> · <owner> ·` and `**Parent:** [PROJ-100](<link>)`;
- `## TLDR`, its first paragraph;
- `## Parity analysis`: rows whose first cell is an id such as `F1` or `B2`, and a verdict. A verdict of gap,
  blocked, unknown, partial or missing is a gap, open until every action item that closes it is done;
- `## Files to touch`: rows that start with a backticked `repo/path` or `repo/path:line`;
- `## Action items`: rows that start `| A1 |`, done when the status starts with done, descoped, merged or shipped;
- `## Dev report`, which marks the plan built, with `### Summary` and `### Files changed`;
- pull requests, as `github.com/<owner>/<repo>/pull/<n>` or `<repo>#<n>` for a registered repo.

The same repo's `profile/*.md` pages, the workspace's facts the skills read (`profile.example/` shows them), are
gitignored too. Every index reads them from disk as doc notes, alongside `sprints/` (`link/plans.py`,
`_home_docs`), so a profile page that cites a file shows up in `notes <file>`.

## Facts from any stack

Some facts only the running app knows: its routes, its GraphQL schema, its models and tables, its jobs and its Kafka
consumers. A facts command writes them as JSON lines, one object per line with its type in `t`, and every index reads
`ai-brain/ai-brain/projects/<name>/facts/*.jsonl`. `[rails]` is the built-in command: it boots the app with
`bin/rails runner extractors/rails_introspect.rb`. Any other stack names its own in `project.toml`:

```toml
[[facts]]
name = "api"                                                     # writes facts/api.jsonl
app = "shop/services/api"                                        # the folder it runs in, under the workspace root
command = ["python", "{project}/extractors/facts.py", "{out}"]  # {out}: the file to write; {project}, {root}
paths = ['urls\.py$', 'models\.py$']                             # changed paths that run it again; unset: any under app
env = { DJANGO_SETTINGS_MODULE = "api.settings" }
```

A command runs on `index --full`, on the first index, and when its repo's HEAD moved a path it reads; `--no-boot`
skips it. One that fails keeps its last facts and writes its output to `ai-brain/ai-brain/var/log/facts-<name>.log`
(`boot.log` for Rails). `status` names the commit each command last ran at.

| `t` | Fields | Becomes |
| --- | --- | --- |
| `route` | `verb`, `path`, `handler` | a `route` interface, HANDLED_BY the handler, owned by the handler's component |
| `schema` | `name`, `file`, `sdl` | the GraphQL schema of the component that holds `file`; frontend operations are matched against it |
| `field` | `schema`, `type`, `field`, `args`, `resolver` | a `graphql_field` interface, RESOLVED_BY the resolver |
| `table` | `name`, `schema` (default `public`), `file`, `columns` | a `table` interface, unless a `db/structure.sql` or `db/schema.rb` defines it first |
| `model` | `class`, `file`, `table`, `assocs` (each `macro`, `name`, `class_name`) | the model: MAPS_TO its table, ASSOCIATES the models it names |
| `consumer` | `consumer`, `file`, `topic`, `group` | CONSUMES the `kafka_topic` |
| `job` | `class`, `file` | a definition marked as a job |
| `schedule` | `job`, `cron`, `source` | a `schedule` interface; the job is SCHEDULED_BY it |
| `meta` | `errors` | the lines `status` lists under `facts` |

`file` is an absolute path inside the workspace root. `handler` and `resolver` are `{"file": …, "symbol": …}`.
`class`, `consumer` and `symbol` name a definition the way the brain names it: `Order.total` in most languages,
`Billing::Invoice` and `Billing::Invoice#total` in Ruby. The Rails boot names handlers with `controller` and `action`
and resolvers with `cls` and `method` instead, and writes three rows only Rails has: `mount` (an engine's mount and its
gates), `channel` (an Action Cable channel) and `cpath` (Zeitwerk's constant map). With no
`[extractors] pilet_routing`, a frontend operation is matched against the workspace's one GraphQL schema, or with
several, against the one whose root type has every field the operation starts at. A component with no facts command
can declare its schema and routes in files instead: `ai-brain/docs/LANGUAGES.md`, Contract files.

## Using it from a skill or an agent

- Start with `ai-brain fresh`: one header line. It starts Neo4j when it is down and re-indexes in the background
  when a repo's `origin/<ref>` moved. It does not fetch, so a skill never waits on the network.
- Ask a verb before Grep, Glob or Read; open what it points to; grep for what it answered `none`.
- After writing a plan, run `ai-brain index --background`, so the next `ticket <KEY>` sees it.
- At the end of a build, run `ai-brain index --pull --background`, so the next session reads what this one built.
- How the harness uses it: `/plan` starts with `fresh`, `ticket` and `notes`, maps the files with the brain, and
  ends with `index --background`. `/dev` reads `ticket <KEY>`, asks `find`, `impact` and `history` before it
  writes, checks `impact --diff` in its self-review before it ships, and ends with
  `index --pull --background`. `/branch-review`
  starts from `impact --diff <repo>@<tip>` and stops with the error when the brain does not answer: it never
  reviews blind. `/bug-hunt` and `/qa-demo` read the ticket with `ticket <KEY>`.
- The edit hook, `ai-brain/bin/ai-brain-hook`, shows Claude a file's card once per session after an edit to a
  file that crosses a boundary. Register it in a skill's frontmatter or in `.claude/settings.json`:

  ```json
  "hooks": {
    "PostToolUse": [{ "matcher": "Edit|Write", "hooks": [{ "type": "command",
      "command": "\"${CLAUDE_PROJECT_DIR}/ai-brain/bin/ai-brain-hook\"" }] }]
  }
  ```

## Set up and start

1. Once per machine, Docker Engine: on Ubuntu or WSL2, `bash ai-brain/ai-brain/setup/install-docker.sh` installs
   it (it asks for sudo).
2. Then one command does the rest, and is safe to re-run: `ai-brain/bin/ai-brain-up`. It pulls this checkout on a
   clean `main` and starts again on the new copy, checks Docker, creates the venv and `.env` when they are
   missing and reinstalls the packages when `requirements.lock` changed, starts Neo4j on the image
   `compose.yaml` names and waits for it, applies the schema, fetches, pulls and indexes (everything on the
   first run, what changed after), links the `/ai-brain` skill, and runs `doctor`. A Rails boot inside the index
   needs that app's database up; without it the last facts stay.
3. Once per machine, add the session hook from Keeping it current, so it stays up and current after that.

| Flag | Does |
| --- | --- |
| `--full`, `--no-boot`, `--no-fetch`, `--project NAME` | passed to `index` |
| `--no-pull` | fetch, but leave every checkout where it is |
| `--status` | `doctor` only, changes nothing |
| `--down` | stops Neo4j; the graph stays on disk |

Neo4j runs in Docker; the CLI, the hook and the Rails boot stay on the host, because the boot needs the host's
Ruby, the app's credentials and its database, and the hook has 100 ms. After a reboot nothing is needed: the
Docker service is enabled and the container restarts itself.

## Seeing the graph yourself

Neo4j Browser at http://localhost:7474, user `neo4j`, the password in `ai-brain/ai-brain/.env`. The saved views
are in `ai-brain/ai-brain/views/*.cypher`; set a parameter first where a view asks for one
(`:param operation => 'OrderQueue'`). `ai-brain/ai-brain/projects/<name>/cards/architecture.md`, which every
index writes, is the same picture as a Mermaid diagram, readable without Neo4j.

## Keeping it current

Three things keep it up and current without anyone running `ai-brain-up`:

- **Every session.** A SessionStart hook in the workspace root's `.claude/settings.local.json` runs
  `fresh --quiet`. It prints nothing and returns in under a second; in the background it starts Neo4j when it is
  down, fetches, pulls and re-indexes what moved. The file is personal and in no repo, so each machine adds the
  hook once:

  ```json
  "hooks": {
    "SessionStart": [{ "hooks": [{ "type": "command", "timeout": 15,
      "command": "\"${CLAUDE_PROJECT_DIR}/ai-brain/bin/ai-brain\" fresh --quiet >/dev/null 2>&1 || true" }] }]
  }
  ```

  It fires only for sessions started at the workspace root, which is where that file is read from.
- **Every skill** that starts with `fresh`.
- **Every build** that ends with `index --pull --background`.

None of the three installs anything: when a pull of this checkout changes `requirements.lock` or the Neo4j image
in `compose.yaml`, run `ai-brain-up` to take it.

`--pull` (which `fresh --quiet` and `ai-brain-up` pass) fast-forwards a checkout to `origin/<ref>` only when it is
on that base branch with no uncommitted tracked changes. A checkout on a ticket branch, with local edits, or
diverged is fetched and left exactly as it is, and the log says which:
`pull <repo>: skipped: on you/proj-123-v1, not main`. One index runs at a time (`var/index.lock`); the background
runs log to `ai-brain/ai-brain/var/log/index.log`.

`index` fetches first and boots Rails again only when a path that carries facts changed (routes, GraphQL, models,
policies, jobs, channels, Kafka, `db/`, a `Gemfile.lock`). After a Neo4j image bump or a model change, empty
`ai-brain/ai-brain/var/neo4j/data/` with the container stopped, start it, and run `index --full`: the graph is
derived, so nothing is backed up. Facts hold names and paths only, never a table row, an `.env` value or a
credential.

## Working on the brain

Python lives only in `ai-brain/ai-brain/.venv`. Cypher lives in `ai-brain/ai-brain/src/ai_brain/graph/` (the
CLI's reads) and `ai-brain/ai-brain/views/` (for people). Before a commit, from `ai-brain/ai-brain/`:
`.venv/bin/pytest` and `.venv/bin/ruff check`.
