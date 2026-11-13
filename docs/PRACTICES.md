# PRACTICES — how we plan, write and review code here

What every change is held to. `/plan` and `/dev` apply it while they plan and build; `/branch-review` and its two lanes
check it, and each review finding names the rule it rests on. Every rule here is one line. Where a rule has a source,
the source has the reasoning and the whole rule, and wins where this page is shorter: a repo's own `CLAUDE.md` and its
rules folder first, then the workspace's own rules and lessons (`ai-brain/profile/LESSONS.md`), then this page, then
the code around the change, which is never a precedent on its own.

This page holds the rules that hold in any codebase. The workspace's version of each rule, with its own code, tickets
and PRs as evidence, and the rules only that workspace has, live in `ai-brain/profile/LESSONS.md`.

Every path is relative to the workspace root, and code is cited in full, so the ai-brain links a page to the files it
names: `ai-brain/bin/ai-brain notes <file>` lists the rule that covers a file.

## KISS and DRY

**KISS: the simplest shape that fully meets the criteria, and nothing for a need no ticket names.** Make it as simple
as possible, but not simpler; build the first case concretely and extract when the second real one arrives. Each of
these is a finding when a diff shows it:

- A layer, wrapper, base class, option, flag, setting or seam that one caller uses: inline it
  (`ai-brain/CLAUDE.md`, "Change discipline").
- Caching, batching or memoization with no stated performance need; error handling for input that cannot be wrong
  ("Change discipline").
- Code nothing reads: a prop only its own tests pass, a fallback that cannot apply, state whose readers sit in another
  PR.
- A flag or branch that names a caller (`isOrdersPage`, `when :invoice_export`): two things sharing one name, which
  stay apart (`ai-brain/.claude/skills/dev/SKILL.md`, "Reuse before you write").
- A view model whose mapper is identity: use the codegen type.
- State that an effect copies from props or other state: compute it in render.
- A service `call` longer than a short outline of named steps, or a filter in Ruby that SQL can do.

```ruby
# before: the policy, the refusal and the action in one branchy method
def call
  if OrderPolicy.new(pundit_context, @order).approve?
    @order.status == 'submitted' ? @order.update!(status: 'approved') : service.fail!({ code: :invalid_status })
  end
end

# after: refusals first, in validate!, and the action alone
def validate!
  authorize!(@order, :approve?)
  service.fail!({ code: :invalid_status }) unless @order.status == 'submitted'
end

def call
  @order.update!(status: 'approved')
  service.data = @order
end
```

```tsx
// before: derived state copied by an effect
const [total, setTotal] = useState(0);
useEffect(() => setTotal(rows.reduce((sum, row) => sum + row.amount, 0)), [rows]);

// after: computed in render
const total = rows.reduce((sum, row) => sum + row.amount, 0);
```

**DRY: one rule, one implementation; share what changes together, not what looks alike.**

- Search by what the code does before writing: `ai-brain find <words>`, then the shared places, then one verdict per
  need: reuse, extend, extract or write new (`ai-brain/.claude/skills/dev/SKILL.md`, "Reuse before you write").
- One implementation of a rule that several paths apply (single and bulk, list and detail, every menu), called from
  each path. A bulk action follows its single twin: the same policy, the same guard, and the bulk write calls the
  single service's attributes method.
- Use the helper, hook or query that already does the job.
- Before adding a bridge method or helper, search the base branch and the open sibling branches: parallel work
  otherwise leaves two copies side by side.
- A change to one copy of a duplicated query, predicate or mapping updates its siblings in the same diff.
- Read each fact from its one source (the backend's SDL, the tenant's setting, the repo's `.nvmrc`), never from a copy
  or a hard-coded value.

```tsx
// before: another date-range formatter
const label = `${toShortDate(order.startDate)} - ${toShortDate(order.endDate)}`;
// after: the one the frontend already has, web-app/src/helpers/dateFormat.ts
const label = formatDateRange(order.startDate, order.endDate);
```

## System design

- **Data lives in the service that owns it.** A host-app change that adds another service's table, model, GraphQL
  type, mutation or business logic is in the wrong place.
- **Route each decision to its service** (`ai-brain/profile/MICROSERVICES.md`).
- **Events for facts, queries for questions, and no read across another service's schema.** Data another service owns
  comes only through its published interface or a bridge, never a direct read of its tables.
- An id that belongs to another service is a plain column with no foreign key into it.
- **Additive and backward-compatible.** A flag gates routing only; schema, consumers and migrations go live with the
  code.
- **Ship the pair together**: a backend contract change with its frontend consumer, an engine change in the same
  monorepo PR as its host app, and a dependency change with the host app's relock. The backend side deploys before the
  frontend release that selects it, and a field removal waits until no frontend document selects it, because a
  document that selects a missing field fails whole. A PR whose pair cannot ship yet is held with `DO NOT MERGE` or as
  a draft, plus an "is blocked by" link on the ticket.
- **Mounted is how it ships.** What a host app configures for an engine it mounts (an audit class, recurring jobs,
  mapped privileges) is proven by a host-app spec or run, because the engine's suite boots alone.
- **Gate every server path that reaches an action**, sibling mutations and direct API calls included, not only the
  screen's.
- **Bound a persona's screen on its own read** (a self-scoped field, a filter argument), never by narrowing a
  tenant-wide read that other screens share.
- **A persona is what its grants say.** Read its grants where they are seeded, and make the backend policy and the
  frontend guard agree for it; a role's label is not its grants.
- **Expose the server's answer** (a `viewerCan…` field, the stored value, a flag on the row) instead of copying a
  privilege rule into the frontend; where the frontend must gate, it mirrors the backend's policy exactly.
- **A projection is only as fresh as its publisher**: ask the owner, through its interface, for a state its publisher
  never re-sends.
- **Never fail or fall back silently**: rescue the error you mean by name, in a small block; warn when a fallback is
  taken; alert once on a failure in an unattended job.

## Data and queries

- **Index** every column a new `WHERE`, `JOIN` or `ORDER BY` uses, checked in the schema file; never `pluck` to filter.
- **Keep a request's query count flat**: `includes` or batching at write time; per-row GraphQL loads through a
  dataloader source; per-batch facts read once, outside the row loop; nil results memoized too; query-count specs that
  reach the fallback.

  ```ruby
  # before: when the guard fails nothing is stored, so every call looks again
  @latest_payment = candidate if settled?(candidate)
  # after: the nil answer is stored too
  @latest_payment = (candidate if settled?(candidate))
  ```

- **Every list paginates, and expensive work goes to a job**, never the request.
- **Filters go into SQL** (`where`, `find_by`), never `relation.select { }`.
- **Count what the screen claims**: `count(distinct)` where rows and values differ, and a tenant-wide count that does
  not move when the caller pages (`ai-brain/.claude/agents/qa-backend.md`, "The bug hunt"). A count the UI shows equals
  the items the viewer can open.
- **Tenancy through the model scopes** (`for_tenant`, `by_account`), pinned by a foreign-tenant example on every lookup
  path.
- **Filter children through their parent's keys with the named scopes or `where(parent: { … })`**, never a `.merge` on
  the same column, which silently replaces the condition; create children through the one path that ensures their
  parents.
- **Order on the association** when rows have a natural order, and the GraphQL list keeps that order.
- **Migrations**: made by the generator, versioned to the UTC second, reversible, under `strong_migrations`; the
  schema cache regenerated; a column removed in two releases. Once pushed, add a migration rather than edit one.
- **A load-bearing invariant lives in the database**: `normalizes` does not cover raw SQL or old rows, and `insert_all`
  skips validations, so back it with a `CHECK` or `citext`, NULL-safe.
- **A search predicate that is dropped fails open.** Check that every filter reaches the SQL (a predicate the model
  does not allow, or a matcher an adapter ignores on some column types, is dropped without an error), and pin it with
  a spec that would return extra rows.
- **Quantities are `numeric`, money is `BigDecimal`, never a float.**
- **Choose "today" on purpose**: UTC `Date.current` or the tenant's zone, decided per rule, with an evening case in a
  zone behind UTC pinned, and time-sensitive specs that pass at any hour and in any zone.
- **A read that generates rows can write**: cap what it generates, and make its answer independent of the order the
  dates are read.
- **Races**: lock the row and re-read it inside the write whenever a second writer can race the check, taking locks in
  one fixed order.
- **Refuse before the first write; fire side effects after commit, once per batch.**
- **A fix that changes stored rows ships with its repair**, through the service that keeps the invariants (dry run,
  apply, rerun), run on every environment, with what it means for production rows stated.
- **Stamp who did it at write time**; do not resolve names later through a projection of users.

## Caching

- **The frontend's caching convention binds every read and write** (the workspace's `CLAUDE.md`, and its file map in
  `ai-brain/profile/LESSONS.md`, "Caching"):
  - reads through the shared cached-query hook, never a bare `useQuery` or a fetch policy picked by hand;
  - a `keyFields` for every type whose identity is not `id`;
  - a mutation writes what its payload proves in its `update`, and names what it cannot in the one invalidations list
    that a shared helper re-reads; no new `refetchQueries` list;
  - variables validated beside each document: a bad read is skipped and logged, a bad write throws;
  - a bulk payload checked against what was requested.
- **Re-read on the sibling reads' triggers** (focus, reconnect, poll, the invalidation list), and test a cache bust
  against an entry still inside its TTL.
- **A new or view-only field goes in a slim page-local document**, not in a heavy shared read: one field the backend
  lacks blanks every screen that shares the document.
- **A bulk outcome comes from the payload and the mode**: all-or-nothing wrote nothing on any failure.
- **A failed re-read after a write that landed is not a failed write.**
- **Server-side caching needs a stated requirement**, and a cache that can fail open is fixed or made a tracked
  precondition.

```ts
// before: a blanket refetch after every action
const [reject] = useMutation(REJECT_ORDER_MUTATION, { refetchQueries: [ORDER_BY_ID, ORDER_QUEUE] });

// after: write what the payload proves, invalidate what it cannot
const [reject] = useMutation(REJECT_ORDER_MUTATION, {
  update(cache, { data }) {
    const order = data?.rejectOrder;
    if (!order) return;
    writeOrderStatuses(cache, [order.id], OrderStatus.Rejected);
    ORDER_STATUS_INVALIDATES.forEach((operationName) => invalidateOperation(operationName));
  },
});
```

## GraphQL contract

- **The schema's root types are the index** (`query_type.rb` and `mutation_type.rb` in graphql-ruby): a field not
  registered there does not exist (`ai-brain/.claude/skills/plan/SKILL.md`, Step 3b).
- **A service's GraphQL belongs to that service.**
- **A mutation is a thin adapter over a service and returns the entity, `null: false`**; a failure raises the API's
  one error type and renders its one error shape, with no payload `errors` field. The workspace's error contract:
  `ai-brain/profile/LESSONS.md`, "GraphQL contract".
- **A refusal's data rides as extra keys in that error shape.** A refusal gets its own code when an existing code's
  frontend copy would read wrong for the new action.
- **An SDL change refreshes, in the same PR, every committed copy of the schema** (the frontend's snapshot, a federated
  SDL, a supergraph fixture), dumped from the backend head, never by hand; then codegen and the type-check, and nothing
  generated is edited (`ai-brain/profile/REPOS.md`, "Codegen").
- **A description states the rule its resolver applies** (the null cases, the discarded rows), changed in the same
  commit as the behaviour, because the frontend copies it into its schema.
- **Nullability is a promise**: a nullable field read as present breaks its consumer, and a non-null field needs a
  value on the error path (`ai-brain/.claude/agents/qa-backend.md`, "GraphQL contract").
- **No dev-only field outside its debug flag** (the same).
- **snake_case in Ruby, camelCase in TypeScript, converted at the boundary.**

## Rails

- **The service shape**: one service base class with its validation concern, an inline `params do` block, business
  refusals and authorization in `validate!`, the action in `call`, and a mutation of about five lines. Return objects,
  raise errors, no CRUD-only services. The workspace's exact shape: `ai-brain/profile/LESSONS.md`, "Rails".
- **Every refusal in `validate!`, before any write**: a `call` that runs without a transaction leaves rows behind
  after a late refusal.
- **Authorize with the action's predicate**: `authorize!(record, :create?)`, never a broader one that skips a
  per-tenant gate. Authorization runs before any state refusal, so a caller without reach learns nothing. An
  admin-only action is gated on its privilege, never on a role check every manager passes.
- **In a host app's GraphQL**: `authorize!(record, :show?)` before a record is returned, `index?` and `policy_scope` on
  a collection, and tenant scope from the record, never from the request's current tenant.
- **A `my*` resolver serves the viewer only**, and an id argument never widens it.
- **Three layers, three questions**: the policy says who may, ActiveRecord keeps persistence invariants, the
  validation layer checks input shape and business rules.
- **Shared refusals live in one guard**, called from every writer it covers; every guard still lets an owner finish
  what they started.
- **A behaviour that widens a write sits behind an opt-in that defaults to today's**, and any unclear flag value takes
  the safe path.
- **Every state keeps a way forward**, and the checks of a step a transition skips still run.
- **Jobs** are idempotent, take ids, and rescue, record and re-raise; the settings a job resolves come through a
  user-less entry point, never a policy scope.
- **A system actor is shown through one display helper**, at the API, in GraphQL and in exports alike.
- **A rake task to run after deploy** gets a "Post-deploy command" section in the PR and its run lines on the ticket.
- **Rename a method when a change alters what it answers.**
- **Style is the directory's `.rubocop.yml`**, run scoped to the diff (`ai-brain/profile/REPOS.md`, "Gate commands per
  repo"): `# frozen_string_literal: true`, single quotes, hash shorthand.

## React

- **The frontend repo's `CLAUDE.md` is the standard**: named React imports; explicit types for `useState`, `useRef`,
  `useReducer` and every hook's return; the repo's convention for cross-tree state; mutations inside category hooks;
  helper placement; path aliases; no import across page folders; codegen types over hand-written mirrors. Never
  `React.FC`.
- **Keep a read's states apart**: loading, error and a settled null are three states; pass the error itself, typed,
  and send every read screen through the shared outage copy.

  ```tsx
  // before: a missing answer reads as shipped
  const shipped = order?.shipped ?? true;
  // after: only a read still in flight counts as unknown
  const shipped = order?.shipped ?? orderLoading;
  ```

- **A gated control shows only after its gating read delivered once**, and a failed gating read means no gate, never
  no list.
- **Gate an action through one shared gate helper** on the field the backend refuses on, at every entry point: the
  detail menu, the action bar, the row menu and the bulk menu.
- **Effects**: complete and stable dependencies, a cleanup for every timer, subscription and listener, and no state an
  effect only derives.
- **Rendering**: stable keys, never the index on a list that filters or reorders, and stable references into memoized
  children.
- **Colours through the theme** (`theme.vars?.palette ?? theme.palette`, `theme.applyStyles('dark', …)`), never a hex
  or a raw palette step; dark mode is checked where the host renders it.
- **Guard inputs that would quietly widen an operation**: dedupe id lists, and check that URL params belong to the
  route's record.
- **Accessibility is a defect, not polish**: real buttons, accessible names, labelled inputs, live regions for async
  status (`ai-brain/.claude/agents/qa-frontend.md`, "Accessibility").
- **Copy lives in the frontend's copy module** (`ai-brain/profile/GRAPHQL_SURFACES.md` names it).
- **react-doctor is clean on the changed scope.**

## Tests

- **Every parity row names its test** (`ai-brain/docs/PLANNING.md`, "Every parity row names a test").
- **Prove each new test catches its bug**: break the code it guards, or run it on the base, and watch it fail; rewrite
  a test that stays green, such as a vacuous `[] == []` or a boundary tested at 9 and 11 but not 10.
- **Assert the effect the criterion names, not a proxy**: the data changed and not only the status, the values and not
  only the query count, a negative case beside the positive one.
- **RSpec**: real records from factories, not doubles; the unhappy paths are required (unauthorized, wrong role, not
  found, another tenant, another user, empty, a contract failure); the shared matchers; one happy path through the
  schema's `execute`. A policy is tested allowed and denied (`qa-backend.md`).
- **Drive the real path**: no `allow_any_instance_of`, the flag enabled rather than the routing under test stubbed,
  stubs constrained with `.with(…)`, and the error shape the server really returns.
- **Persona rules are proven on the seeded roles in a host-app spec** whenever a development bridge or mock grants
  every privilege in the engine's own suite.
- **Spec speed**: `instance_double`, then `build_stubbed`, `build`, `create`, and `let_it_be` for shared setup. A spec
  creates only the records it needs, and its name says what it asserts now.
- **Jest**: render through the app's provider helper, never mock Apollo hooks, assert on what the user sees, query by
  role, no empty `waitFor`, and every suite passes alone in any shard. A suite that failed under the full run's load is
  rerun alone before it is called a regression.
- **Cache tests render against the app-shaped cache**, every mock carries a `__typename`, mocks of one normalized
  record agree across documents, and a missing mock is the strongest "made no request" assertion.

## Comments, docs and PR text

- **The comment budget**: one or two lines inline, one to four for a doc block; reasoning, history and ticket ids go
  to the plan or the PR.
- **Fix every comment, doc block and doc that the change makes untrue**, outside the diff too. Counts, versions and
  other files' line numbers go stale: leave them out.
- **The PR description becomes the squash commit**: every claim and count true at the head, the command beside each
  test number, and the known gaps, costs and deploy notes written down.
- **Review and PR prose is plain**: no emojis, a spaced hyphen for a dash, no "worth" constructions.

## The process

- **Read a ticket's state from its branches and PRs**, not from its tracker status.
- **Every gap a PR leaves out gets a filed, linked ticket**; "no card yet" tracks nothing.
- **Product decisions, sign-offs and release gates go on the ticket before merge**, not only in the PR.
- **Build what the criteria say**; when a PR does more or less, the ticket is amended or the work moves to its own
  ticket before merge.
- **Merge only on green CI at the head**: re-run cancelled shards, confirm a stacked PR's suites, and re-trigger rather
  than re-run jobs on a stale merge ref.
- **Agree the order with any open PR that edits the same lines or adds the same helper.**
- **Post the run the ticket asks for** (the e2e report, the smoke test) before merge. The end-to-end test itself is the
  developer's choice: a review never requires one or blocks without it.
- **Carry a superseded plan's kept decisions into its rewrite**, and say so when a plan reverses an earlier Decision.
- **Capture or correct the note that a merged change makes stale**, in the workspace's notes repo.
- **How reviewers here review**: they say what blocks and what does not; they limit a later round to the fix, while a
  defect the fix introduces still counts; they post the criteria as a table with `file:line` evidence; they do not
  repeat a finding another reviewer already raised. `/branch-review` does the same.

### How a rule gets here

A `/branch-review` round lists, under "Rules to add", each finding that states a rule neither this page nor
`ai-brain/profile/LESSONS.md` has, or repeats one an earlier review made. A rule that holds in any codebase comes here
through a PR on this repo, in the topic it belongs to; the workspace's version, with its evidence and its count, goes
to `ai-brain/profile/LESSONS.md`. A rule leaves when its reason stops being true.
