# ai-brain

A cross-repo code graph for coding agents. ai-brain reads every repo in a workspace at `origin/<ref>`, links what
the code states (GraphQL fields and operations, routes, Kafka topics, tables, jobs, frontend pages, tests, plans
and notes) into Neo4j, and answers a question in a few lines of `repo/path:line` instead of a grep across every
repo. It ships a CLI, a Claude Code skill (`/ai-brain`) and an edit hook.

```
ai-brain/bin/ai-brain surface order queue                      # interfaces by name
ai-brain/bin/ai-brain find format start end                    # code by what it does
ai-brain/bin/ai-brain impact Order.status                      # what a change reaches, with its tests
ai-brain/bin/ai-brain trace Order.status                       # UI to operation to resolver to model to table
ai-brain/bin/ai-brain impact --diff monorepo web-app           # what your checkouts' changes reach outside them
ai-brain/bin/ai-brain impact --diff monorepo@origin/you/proj-123-v1   # a branch you have not checked out
ai-brain/bin/ai-brain ticket PROJ-123                          # plan, files to touch, open gaps, branches, PRs
ai-brain/bin/ai-brain history web-app/src/pages/Orders/Orders.tsx     # the tickets behind a file
```

Every line it prints is a lead with a `path:line`: open the file before you build on it.

## What it fits

It was built for workspaces shaped like this, and reads each part by its role:

- a Rails monorepo with its apps under `apps/<app>/` and engines under `gems/<engine>/`, serving GraphQL
  (graphql-ruby), REST routes, Kafka consumers and background jobs;
- React and TypeScript frontends: micro-frontends (Piral pilets) and the shell that hosts them, talking GraphQL
  (Apollo);
- shared libraries, and a Playwright end-to-end suite whose tests carry ticket tags like `@PROJ-123`;
- optionally, a notes repo, and plan documents for the tickets you work on.

It parses Ruby, TypeScript and JavaScript with tree-sitter. The Rails facts (routes, the GraphQL schema, models,
policies, jobs, mounts, Kafka consumers) come from booting the app with a script you supply. It draws an edge
only where the code states one, so a call through `send`, a callback or a prop has none. It does not read an issue
tracker, a database's rows or a running app.

## Requirements

- Linux; it is developed on Ubuntu under WSL2.
- git, Python 3.12 or newer, and curl.
- Docker Engine with the compose plugin. On Ubuntu or WSL2, `ai-brain/ai-brain/setup/install-docker.sh` installs it.
- For Rails facts: the app's Ruby through [mise](https://mise.jdx.dev) and its database running.
- Claude Code, for the `/ai-brain` skill and the hooks. The CLI works without it.

## Quick start

1. Put this checkout next to the repos it should read, in one workspace folder, and run everything from that
   folder:

   ```
   my-workspace/
   ├── ai-brain/      # git clone https://github.com/zneret03/ai-brain.git
   ├── monorepo/
   ├── web-app/
   └── shell/
   ```

2. Make a project for the workspace, and list its repos in the copy's `project.toml`:

   ```
   cp -r ai-brain/ai-brain/projects/_template ai-brain/ai-brain/projects/my-workspace
   ```

3. Start everything: `ai-brain/bin/ai-brain-up`. It checks Docker, creates the venv and `.env`, starts Neo4j,
   applies the schema, fetches, indexes every repo, links the `/ai-brain` skill into `my-workspace/.claude/`,
   and runs `doctor`. It is safe to re-run, and later runs index only what moved.
4. Ask it: `ai-brain/bin/ai-brain surface <words>`, or `/ai-brain` in a Claude Code session started at
   `my-workspace/`.
5. Once per machine, add the SessionStart hook in [docs/AI_BRAIN.md](docs/AI_BRAIN.md) (Keeping it current), so
   every session starts Neo4j when it is down and re-indexes in the background what moved.

`ai-brain/bin/help` lists every script, and each script and each verb takes `--help`.

## The verbs

| Verb | Answers |
| --- | --- |
| `surface <words>` | interfaces by name: GraphQL fields and operations, routes, topics, tables, flags, pages |
| `find <words>` | code by what it does: symbol and parameter names, in every repo |
| `impact <target>` | what reaches a field, operation, route, topic, table, symbol or file, with its tests |
| `impact --diff <repo>[@<ref>]...` | what the branches' changes reach outside them |
| `consumers <target>` | only the direct consumers of an interface |
| `trace <target>` | UI to operation to resolver to model to table; producer to topic to consumer |
| `notes <file or words>` | the notes and plans that cite a file or match words, each ok, moved or gone |
| `ticket <KEY>` | one ticket: plan, files to touch, services, open gaps, branches, commits, PRs, related |
| `sprint [<slug>\|all]` | a sprint's tickets with their state, then the files two of its plans both touch |
| `gaps [<KEY>\|<slug>]` | open gaps and open action items, for one ticket or one sprint |
| `history <repo/path>` | the tickets that planned, built, committed to or cited a file or directory |
| `who <repo/path>` | who wrote a file or directory, and the tickets behind it |
| `related <KEY>` | tickets that touched the same files, the rarest shared files counting most |
| `status` | graph size, coverage, engines, externals and schema skew |
| `fresh` | starts Neo4j if it is down; re-indexes in the background when a repo moved |
| `index` | rebuilds the graph: fetch, parse, link, and write only what changed (`--full` from empty) |
| `cards`, `schema`, `doctor` | re-render the hook's cards, apply Neo4j's constraints, check the setup |

## The project file

`ai-brain/ai-brain/projects/<name>/project.toml` describes one workspace. The template documents each key inline.

| Key | Means |
| --- | --- |
| `[project] name`, `root` | the project's name, and the workspace root: absolute, `~/…`, or relative to the ai-brain checkout (`".."` is its parent) |
| `[[repos]] name`, `role`, `ref` | a folder under `root`; its role, one of `monorepo`, `app`, `pilet`, `shell`, `library`, `e2e`; the branch read at `origin/<ref>` |
| `[[knowledge]] name`, `kind`, `ref` | a folder under `root` read as `notes`, `sprints` or `plans` (below) |
| `[externals] from` | a `Gemfile.lock`; its GIT sources that are not cloned here become externals, and a `library` repo is read at the tag it pins |
| `[rails] app`, `env` | a Rails app under `root`, booted with `bin/rails runner projects/<name>/extractors/rails_introspect.rb` for the facts, in that `RAILS_ENV`; you supply the script |
| `[extractors] pilet_routing` | a Python file in the project folder whose `router(ctx, repo)` returns a function from a frontend operation name to the engine that answers it |
| `[skip] dirs` | folders under `root` that are not repos, such as a worktree |
| `[tickets] prefix` | ticket keys look like `PROJ-123`, ticket branches like `you/proj-123-v1`; unset, commits and plan names link to no ticket |
| `[names] strip_prefix` | dropped from repo and engine names in output, e.g. `"acme-"` |
| `[names] apps` | a monorepo's `apps/<dir>` to a component name, e.g. `{ acme = "monolith" }` |
| `[http] own_hosts` | host or env-var words that are your own systems, so HTTP calls to them are not external APIs |
| `[[graphql.snapshots]] repo`, `path`, `engine` | a schema snapshot committed in a frontend repo, and the engine whose SDL it must match (`status --skew`) |

Several projects share one Neo4j, kept apart by a `project` property. Every verb takes `--project`, and defaults
to the project whose `root` holds the current directory.

## How it reads

- **Git objects at `origin/<ref>`, never the working tree.** `index` fetches first, so a checkout sitting on a
  ticket branch or holding local edits is read as its base branch. `impact --diff <repo>` is the one question
  about your checkout as it stands, committed, uncommitted and untracked.
- **`--pull` only fast-forwards.** A checkout on its base branch with no uncommitted tracked changes moves to
  `origin/<ref>`; anything else is fetched and left exactly as it is.
- **Only what moved is written.** One index runs at a time; later runs parse what changed and boot Rails again only
  when a path that carries facts changed (routes, GraphQL, models, policies, jobs, Kafka, `db/`, a lockfile).
- **A `sprints` repo's `sprints/` is the exception**: it is meant to be gitignored, each person's own, and is read
  from disk on every index.
- **Facts hold names and paths only**: never a table row, an `.env` value or a credential.

## Knowledge repos

All three kinds are optional.

- **`notes`**: Markdown notes whose YAML frontmatter names the code they describe. `notes <file>` then lists each
  note citing a file, with its source ok, moved or gone:

  ```yaml
  ---
  id: orders
  title: How orders are kept
  sources:
    - repo: your-org/monorepo
      ref: main
      paths:
        - apps/app/app/models/order.rb
  ---
  ```

- **`sprints`**: plan documents, one folder per sprint, read from disk, plus the repo's `docs/` pages at `main`.
  `ticket`, `sprint`, `gaps`, `history` and `related` answer from them:

  ```
  sprints/<sprint>/plan/<KEY>.md        a ticket's plan; chore-<slug>.md for work with no ticket
  sprints/<sprint>/reviews/<KEY>.md     review rounds
  sprints/<sprint>/reports/<name>.md    test reports
  sprints/<sprint>/bugs/<name>.md       bugs still open
  ```

  The sections it reads in a plan are listed in [docs/AI_BRAIN.md](docs/AI_BRAIN.md) (The plans it reads).
- **`plans`**: an archive of older plans, read from every branch head, newest first.

## Output, exit codes and trust

One header line names the commit each repo was read at, then at most 30 lines of a name and a `repo/path:line`.
Exit 0 means answered (or `none`), 3 not set up, 4 Neo4j unreachable; on 3 or 4 it prints
`ai-brain: not run (<reason>)`. A brain line is a lead, never a verdict: open its `path:line` before it becomes a
claim in a plan, a review or a pull request. The full contract is [docs/AI_BRAIN.md](docs/AI_BRAIN.md).

## Claude Code

- **The skill.** `ai-brain/bin/install.sh` links `.claude/skills/ai-brain/` into the workspace root's `.claude/`
  (`--copy`, `--status` and `--uninstall` too), and `ai-brain-up` runs it. A session started at the workspace root
  then asks the brain before it greps.
- **The hooks.** A SessionStart hook keeps it current, and a PostToolUse hook shows Claude a file's card after an
  edit to a file that crosses a boundary. Both are in [docs/AI_BRAIN.md](docs/AI_BRAIN.md).

## Seeing the graph

Neo4j Browser at http://localhost:7474, user `neo4j`, the password in `ai-brain/ai-brain/.env`. Saved views are in
`ai-brain/ai-brain/views/*.cypher`.

## Troubleshooting

| You see | Do |
| --- | --- |
| `ai-brain: not run (not set up: …)` | `ai-brain/bin/ai-brain-up` |
| `ai-brain: not run (Neo4j unreachable …)` | `ai-brain/bin/ai-brain-up`, or `ai-brain/bin/ai-brain fresh` |
| `The Docker daemon does not answer` | `sudo systemctl start docker`; on `permission denied`, add yourself to the `docker` group (see `install-docker.sh`) |
| `boot failed; keeping the previous facts` | read `ai-brain/ai-brain/var/log/boot.log`; start the app's database, or index with `--no-boot` |
| the header ends in `stale:` | the named repos moved since the index; `fresh` re-indexes them in the background |
| a background index seems stuck | `ai-brain/ai-brain/var/log/index.log` |
| the wrong project answers | pass `--project <name>`, or run from inside that project's `root` |
| the graph looks wrong after a Neo4j upgrade | stop the container, empty `ai-brain/ai-brain/var/neo4j/data/`, start it, then `ai-brain/bin/ai-brain index --full` |

`ai-brain/bin/ai-brain-up --status` runs `doctor` and changes nothing.

## Working on ai-brain

See [CLAUDE.md](CLAUDE.md): the venv, the tests and the change discipline.

## License

MIT. See [LICENSE](LICENSE).
