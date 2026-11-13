# profile — your workspace's facts, for the skills

The skills, agents and commands in `ai-brain/.claude/` describe the workflow. The facts of your workspace live in
`ai-brain/profile/`, which is gitignored: your repos, ports, tracker, test data, conventions and lessons. This folder
shows the shape of each file, filled with a made-up shop (a `monorepo` with `orders`, `billing`, `catalog` and
`shipping` engines, the `web-app` and `admin-app` micro-frontends, a `shell`, a `shared-lib` and an `e2e` suite).

## Set it up

From the workspace root:

1. Copy the examples: `cp -r ai-brain/profile.example ai-brain/profile`.
2. Fill each file with your workspace's facts. Keep the `##` headings: the skills cite them by name, for example
   `ai-brain/profile/STACK.md` § Entry points.
3. Re-index: `ai-brain/bin/ai-brain index --background`. The brain reads `profile/*.md` from disk, so a skill's
   `ai-brain notes` query finds them.

A file you leave out makes the skill that reads it ask, or stop with what it needed.

## The files

| File | Holds | Read by |
| --- | --- | --- |
| `REPOS.md` | repos and roles, base branches, gate commands, codegen, branch and PR rules, review targets and standards, knowledge repos, the plans archive, reference docs | every skill, the agents, `docs/PLANNING.md` |
| `MICROSERVICES.md` | the services, what each owns, how they talk, routing defects | `/plan`, `project-manager`, `developer`, `qa-backend`, the bug-hunt workflow |
| `DEFINITIONS.md` | personas, statuses, domain terms, the rules the QA lanes check | `/plan`, `/dev`, `/qa-demo`, `project-manager`, `developer`, `qa-backend`, `qa-frontend` |
| `GRAPHQL_SURFACES.md` | where every query and mutation lives, and the inventory commands | `project-manager`, `developer`, `qa-backend`, `qa-frontend`, `docs/PLANNING.md` |
| `CODE_MAP.md` | per-layer paths, contract files, reuse homes, code conventions | `/plan`, `/dev`, `/branch-review`, `/bug-hunt`, the agents |
| `STACK.md` | entry points, the frontend feed, preflight, test data, gates, recording | `/dev`, `/bug-hunt`, `qa-e2e` |
| `TRACKER.md` | site and board, current sprint, ticket family, QA gates, writing to the tracker | `/plan`, `/branch-review`, `/qa-demo`, `/bug-hunt`, `project-manager` |
| `E2E.md` | the e2e suite, and where its screenshots are copied from into the evidence folder | `/plan`, `/dev`, `/bug-hunt`, `developer`, `qa-design`, `qa-e2e` |
| `QA.md` | the shared environment, sign-in, data lookups, the recording table, the QA driver | `/qa-demo`, `/dev` |
| `LESSONS.md` | your own rules, and what your tickets and reviews taught | `/plan`, `/dev`, `/branch-review`, `project-manager`, `qa-e2e`, `qa-frontend` |
| `qa/login.mjs` | the sign-in steps the QA driver runs | `/qa-demo` |
