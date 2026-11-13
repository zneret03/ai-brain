> Example of `ai-brain/profile/E2E.md`: the end-to-end suite and where each ticket's evidence lives. Copy it to
> `ai-brain/profile/` and fill it in; the real one lives there, gitignored.

# E2E — the Playwright suite and the evidence folder

Every path is relative to the workspace root. The skills and agents cite the sections below by name.

## Suite

**The existing suite: `e2e`.** Never write a throwaway spec somewhere else, never install a second Playwright, and
read `e2e/CLAUDE.md` before touching anything.

`/bug-hunt`'s workflow args: `e2eRepo` is `e2e`; `evidenceDir` is `ai-brain/sprints/<sprint>/evidence/<KEY>/hunt`
(§ Evidence); `repos` is the list in `ai-brain/profile/REPOS.md` § Repos the hunt reads.

**What a spec looks like.**

- `tests/customer/` or `tests/admin/` — the directory encodes the role.
- Import `test` / `expect` from `../../fixtures/roles`.
- Tag it `{ tag: ['@ticket', '@PROJ-123'] }` on the top-level `describe`.
- Seed, then open the page, then assert. `await shot(page, '<name>')` at the moments that evidence the criteria.

```
cd e2e
yarn test --grep @PROJ-123          # this ticket only
yarn typecheck
```

**The browser runs alone**: `workers: 1`, one shared database whose seeds clear and recreate, one frontend on
`:5011`. Hunters run one at a time.

**Seeding** goes through `fixtures/seed.ts`. **Probes** live in `tests/probes/`; they log, never assert, and one that
pins real behaviour is promoted into `tests/<role>/` with the ticket tag.

**Traps that have produced false findings here**: e.g. a wall of `ERR_CONNECTION_REFUSED` is a dead dev server, not a
wall of defects; restart it and re-run before reading anything into a large failure count.

## Evidence

**Evidence lives beside the plan, not in the e2e repo**: `ai-brain/sprints/<sprint>/evidence/<KEY>/`, gitignored
with the rest of `sprints/` and never pushed (`ai-brain/docs/SPRINTS.md` § Evidence). `/dev` writes the screenshot
pairs, the GIFs and mp4s, and `notes.md` (which stack, which data, which persona) there; `/bug-hunt` writes `hunt/`;
`/qa-demo` writes `qa/`.

- `/bug-hunt` writes `hunt/` on every run, with `notes.md` and `bug-hunt.md` in it.
- The hunt report goes to `ai-brain/sprints/<sprint>/reports/<DD>-<slug>-bug-hunt.md`.
- The e2e suite writes its own screenshots to `e2e/test-results/`; a screenshot worth keeping is copied from there
  into the ticket's evidence folder, named after the criterion it evidences (`AC-3-empty-state.png`).
- A PR's `# Demo` images are written `![alt](evidence:<file>)`; after `gh pr create`, `ai-brain/bin/pr-images` uploads
  them and swaps in GitHub's links.
