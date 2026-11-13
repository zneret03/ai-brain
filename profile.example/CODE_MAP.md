> Example of `ai-brain/profile/CODE_MAP.md`: where things live per layer, the contract files, the reuse homes and the
> code conventions the builder and the QA lanes hold work to. Copy it to `ai-brain/profile/` and fill it in; the real
> one lives there, gitignored.

# CODE_MAP — where things live, per layer

Every path is relative to the workspace root. The skills and agents cite the sections below by name.

## File map

| Layer | Where |
| --- | --- |
| GraphQL types | `monorepo/gems/<engine>/app/graphql/<ns>/types/query_type.rb` (same for `mutation_type.rb`) |
| Tables and columns | `monorepo/gems/<engine>/db/structure.sql` |
| Resolvers | `monorepo/gems/<engine>/app/graphql/<ns>/resolvers/` |
| Policies | `monorepo/gems/<engine>/app/policies/` |
| Host app GraphQL | `monorepo/apps/shop/app/graphql/` |
| Frontend documents | `web-app/src/graphql/queries/`, `web-app/src/graphql/mutations/` |
| Hooks | `web-app/src/hooks/` |
| Generated types | `web-app/src/gql/` (generated, never hand-edited) |

- **`FE` means the backend is already there**: wire the existing operation with a document, the hook, the component
  and the tests.
- A duplicate document (the same query written twice) or a component duplicated into a second page instead of lifted
  to `src/components/` is a finding.

## Contract files

- `query_type.rb` and `mutation_type.rb` are the index: a field not registered there does not exist, however many
  resolver files mention it.
- The schema snapshot `web-app/src/graphql/schema/schema.graphql`: every field the UI needs, present or absent there.
  **An absent field is a backend gap candidate.**

The inventory commands:

```
grep -nE '^\s*field\s' monorepo/gems/orders/app/graphql/orders/types/query_type.rb
grep -nE '^\s*field\s' monorepo/gems/orders/app/graphql/orders/types/mutation_type.rb
grep -rn "<field name>" web-app/src/graphql/schema/schema.graphql
```

- A contract change goes engine first, then the frontend's codegen chain (`ai-brain/profile/REPOS.md`, "Codegen").
  Never hand-edit `src/gql/`.

## Reuse homes

| Repo | Shared places |
| --- | --- |
| `web-app` | `src/components/`, `src/hooks/`, `src/helpers/`, `src/graphql/fragments/`; tests: `src/__tests__/shared/` |
| `monorepo/gems/<engine>` | `app/services/<ns>/`, `app/policies/`, `app/models/concerns/<ns>/`; tests: `spec/support/`, `spec/factories/` |
| Shared by every engine | `shared-lib/lib/shared_lib/` |
| `e2e` | `pages/`, `fixtures/` |

- An extract stays inside the repo, engine or app that holds both callers; code two engines would share belongs in
  `shared-lib`, an open question in the plan.
- Where tests live: engine RSpec in `spec/graphql/`, `spec/policies/`, `spec/models/`; frontend Jest in
  `__tests__/<Feature>/unit/` and `__tests__/<Feature>/integration/`.

## Conventions

- **Cross-tree UI state** lives in an Apollo reactive var (`src/graphql/reactive/<feature>Var.ts`) with a companion
  hook, not `useState`.
- **Apollo is `HttpLink` only**: no subscriptions, so polling is the transport that exists.
- **Copy** lives in `src/helpers/copy.ts`; there are no locale files in the frontends.
- **Dev-only surfaces** stay behind `ENABLE_DEBUG_UI` and out of the production schema.
- **Spacing** is on the MUI scale (8px per unit); a value off the scale is said out loud.
- **Review standards**: `ai-brain/profile/REPOS.md` § Review standards.
