> Example of `ai-brain/profile/LESSONS.md`: your workspace's own rules, and what its tickets and reviews taught, with
> their evidence. Copy it to `ai-brain/profile/` and fill it in; the real one lives there, gitignored.

# LESSONS — this workspace's own rules, and what its tickets and reviews taught

The workspace's version of `ai-brain/docs/PRACTICES.md`: each rule with this workspace's sources, code, tickets and
PRs, plus the rules only this workspace has. Where the two differ, this file wins here.

Rules marked **Learned** come from your own records: the plans in `ai-brain/sprints/`, and the reviewer comments on
your recently merged PRs. How they are cited:

- `2026-s1/PROJ-123:40` is `ai-brain/sprints/2026-s1/plan/PROJ-123.md:40`.
- `monorepo#42` and `web-app#17` are PRs on those repos.
- `(3 · 2)` is 3 reviewer comments asking for it, on 2 PRs.

## KISS and DRY

- Learned (3 · 2): a bulk action calls its single twin's attributes method rather than a copy of it
  (`2026-s1/PROJ-123:40`, `monorepo#42`).

## System design

- Order data lives in the `orders` engine; the host app only mounts it.

## Data and queries

- Learned: an order's lines are filtered through `where(order: { … })`, never a `.merge` on `store_id`
  (`2026-s1/PROJ-124:12`).

## Caching

- The frontend's file map: the cached-query hook, the cache policy and the invalidations list, with their paths.

## GraphQL contract

- The error contract: the error class, its HTTP status and the error body's shape.

## Rails

- The service base class, its validation concern, and the mutation pattern, with the engine `CLAUDE.md` section that
  states it.

## React

- The copy module and the shared action-gate helper, with their paths.

## Tests

- Where persona rules are proven, and the spec that seeds the roles.

## Comments, docs and PR text

- The prose banlist the PR text follows.

## Learned on our tickets: the process

- Learned (2 · 2): product decisions go on the ticket before merge (`monorepo#42`, `web-app#17`).

### How a lesson gets here

A `/branch-review` round lists, under "Rules to add", each finding that states a rule neither page has. A person adds
it here with its evidence and count; a rule that holds in any codebase also goes into `ai-brain/docs/PRACTICES.md`.

## House style

The plan to model new plans on, if you have one: `ai-brain/sprints/2026-s1/plan/PROJ-123.md`.

## Planning

- Who the skills serve, and what that changes: e.g. "most tickets that read as full-stack are frontend-only, because
  the backend already exposes what the UI needs".
- Spec defects that recur: e.g. technical notes that cite the host app's conventions for frontend work.

## Known instances

Defects the QA lanes already know, so a new finding names them rather than rediscovering them:

- e.g. the Place order button renders before its gating query resolves and no-ops when clicked.

## Hunt scenarios

Your product's own hunt cases, for `/dev`'s browser check and the bug hunt:

- e.g. an empty cart, a first-time customer, an order placed just before midnight UTC, a phone-width window.
