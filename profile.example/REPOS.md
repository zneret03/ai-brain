> Example of `ai-brain/profile/REPOS.md`: the repos in your workspace, their roles, ports, base branches, gates and
> branch rules. Copy it to `ai-brain/profile/` and fill it in; the real one lives there, gitignored.

# REPOS — the workspace, per repo

**Every path in this file is relative to the workspace root.** The harness is always run from the workspace root,
never from inside a single repo — a ticket crosses BE and FE and each step has to read both.

## The map

| Repo | Role | Stack | Port | Base branch |
|---|---|---|---|---|
| `monorepo` | The host app under `apps/shop/` and its engines under `gems/<engine>/` (`orders`, `billing`, `catalog`, `shipping`) | Rails 7.1, GraphQL, Kafka | 3000 | `main` |
| `web-app` | Micro-frontend (pilet) for the orders engine | Piral pilet, React, Apollo, MUI, TS | — | `main` |
| `admin-app` | Micro-frontend for the catalog engine | Piral pilet, React, Apollo, TS | — | `main` |
| `shell` | The micro-frontend host | Node, Piral | 1234 | `main` |
| `shared-lib` | Ruby code every engine shares, pinned by tag | Ruby gem | — | `main` |
| `e2e` | E2E suite, driven by `/bug-hunt`; `/dev` keeps each ticket's demo evidence in `artifacts/tickets/<KEY>/` | Playwright + TS | drives 3000 + a pilet on 5011 | ticket branch, no PR |
| `ai-brain` | The harness and the brain; `sprints/` and `profile/` are gitignored | — | — | branch + PR |

## Not cloned

A repo named in a doc but not cloned here is absent: never plan a file path into a repo that is not on disk, say it
is absent instead. List them, e.g.:

- `mobile-app` is not cloned. A mobile need is `unknown`, said plainly.

## Stack

- Rails 7.1 engines with `graphql-ruby` and Pundit under `monorepo/gems/`, plus the host app under `apps/shop/`.
- Piral micro-frontends in React + Apollo + MUI + TypeScript strict (`web-app`, `admin-app`), hosted by `shell`.
- **The `CLAUDE.md` of every repo you touch** carries the real conventions, the test standards and the traps.

## Stack to repos

**Repos:** each code repo the stack puts in scope: `BE` → `monorepo`; `FE` → `web-app` (or `admin-app` for catalog
screens); `FE+BE` → both.

## Base branches

```
git -C <repo> symbolic-ref --short refs/remotes/origin/HEAD
```

`git -C <repo> fetch origin` first for the repos with changes. Name any repo whose `origin/HEAD` disagrees with where
work actually merges, and confirm against the ticket's plan doc and the repo's own `CLAUDE.md` before cutting a
branch. Say which base you chose.

## Gate commands per repo

Run only the lanes for repos the round actually touched. Never report a check you did not watch run.

| Repo | Lint | Types | Tests |
|---|---|---|---|
| `monorepo` | `bundle exec rubocop` **scoped to the diff** | `yarn build` | `bundle exec rspec` (scope it: `gems/orders/spec/`, or `<file>:<line>`) |
| `web-app` | `yarn lint` | `yarn type-check` | `yarn test` |
| `admin-app` | `yarn lint` | `yarn type-check` | `yarn test` |
| `shell` | `yarn lint` | `yarn typecheck` | `yarn test` |
| `e2e` | — | `yarn typecheck` | `yarn test`, or one ticket: `yarn test --grep @PROJ-123` |

### Scope rubocop to the diff, the same way rspec is scoped

A repo with a large pre-existing rubocop baseline is red before anyone writes a line, so a gate that runs it bare can
never go green. Scope it:

```bash
files=$(git status --porcelain | awk '{print $NF}' | grep '\.rb$')
[ -n "$files" ] && bundle exec rubocop $files
```

Report the scope in the evidence. The gate asks "did this diff introduce an offence", not "is the repo clean".

## Gates

The gate the developer runs before returning, and the one the `/bug-hunt` loop runs centrally, per repo:

- `monorepo`: rubocop scoped to the `.rb` files the diff touches, then rspec scoped to the specs the diff touches.
  Record the scope: a scoped green run reported as "the suite passed" is a false gate.
- `web-app`, `admin-app`: `yarn lint`, `yarn type-check`, `yarn test`.
- `shell`: `yarn lint`, `yarn typecheck`, `yarn test`.
- `e2e`: `yarn typecheck` only; the suite belongs to the hunters.
- `ai-brain`: no gate; its `sprints/` write-up is docs.

## Codegen

The FE step people forget. The frontend's types come from a dumped schema, not from the live service:

```
cd web-app
yarn schema:dump     # pull the backend's current SDL into schema.graphql
yarn codegen         # regenerate src/gql/ from schema.graphql + src/graphql/**
yarn type-check
```

A new or changed backend field is invisible to the FE until `schema:dump` runs. Never hand-edit `src/gql/`.

## Branch and PR conventions

- **Every repo a ticket modifies: feature branch, always.** `you/proj-123-v1` — `{name}/{ticket-key}-v{n}`, bumping
  `v{n}` for a follow-up branch on the same ticket. The same branch name in each repo the ticket touches.
- PR title: `{TICKET KEY} | {Title}`.
- Commit prefixes: `feat`, `fix`, `chore`, `refactor`, `test`, `docs`.
- **Paired PRs ship together.** A BE GraphQL change without its FE consumer (or the reverse) breaks the frontend at
  runtime. Open both, and say in each that it is half of a pair.

### PRs

- `gh pr create -R acme/<repo> --base <base> --head <branch> --title "<KEY> | <Title>"`. Fill the repo's
  `pull_request_template.md`.
- The GitHub owner is `acme`: every `gh` call uses `-R acme/<repo>`.
- The prose skill the PR text follows, if a repo has one.

### No shared branch is a push target

Not `main`, `staging`, `development` or `develop`, in any repo here. Every repo is branch + PR, except the e2e repo,
which gets its branch pushed and its compare URL reported.

### No AI attribution anywhere in this workspace

Say here whether commits and PRs may carry a `Co-Authored-By` or "Generated with" trailer.

## Branches and commits

What `/bug-hunt` does with its fixes: every repo the fixes touched gets `{name}/{ticket-key}-bughunt-v1`, checked
against local and remote first; one commit per repo, conventional prefix, imperative subject of 50 characters or
fewer (`fix(PROJ-123): render the empty queue instead of a blank table`); the owning service first, then the
frontend, then the e2e repo. The e2e repo pushes its branch and takes no PR.

## Delivery order

What merges before what, across repos: an engine change ships with the host app in the same `monorepo` PR; a BE
contract change ships with its frontend consumer.

## Review targets

The repos `/branch-review` reads: `monorepo` (engines in `monorepo/gems/<engine>/`, the host app in
`monorepo/apps/shop/`), `web-app`, `admin-app`, `shell` and `e2e`, all under the `acme` owner on GitHub. It reads
every code repo and writes none.

## Review standards

| Check | Lane | Command | In an export |
| --- | --- | --- | --- |
| rubocop | Rails | `bundle exec rubocop --format json <the diff's .rb files>`, from the engine's directory | the same, from the export's directory |
| type-check | React | the repo's type command in § Gate commands per repo | the same |

The standards each lane applies, by path: the `CLAUDE.md` of each engine or app the diff touches, the repo's
`.claude/rules/*.md` that match a changed file, and `ai-brain/docs/PRACTICES.md`. Review prose follows the repo's
prose rule, if it has one.

## Repos the hunt reads

```
for d in monorepo web-app admin-app shell e2e ai-brain; do
  printf '%-20s %-30s %s\n' "$d" "$(git -C "$d" rev-parse --abbrev-ref HEAD)" "$(git -C "$d" status --porcelain | wc -l) changed"
done
```

## Running the stack locally

```
cd monorepo && bin/dev               # the host app :3000
cd shell && yarn dev                 # the shell :1234
```

The entry points `/dev` drives: `ai-brain/profile/STACK.md`.

## Knowledge repos

The notes and plans the brain reads besides `ai-brain/sprints/`: a notes repo (`kind = "notes"` in project.toml), a
plans archive (`kind = "plans"`), and the grep fallback when the brain does not answer:
`grep -rln "<KEY>" ai-brain/sprints`.

## The plans archive

Where plans written before this harness live, if anywhere, and the path `PLAN_DOC_ARCHIVE` points at.

## Reference docs

The architecture, data-model and diagram-template docs a plan reads, with their paths, and which of them lag the
code.
