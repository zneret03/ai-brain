# PLANNING — the contract every ticket passes through before code

**Nothing gets built here without a plan doc in `ai-brain/sprints/`.** Not "a plan in the
conversation" — a markdown file with a parity analysis, the files to touch and numbered action items.
`/plan` writes it, `/dev` refuses to start without it and ends by writing its Dev report into it, and the
ai-brain indexes it, so the next session asks `ai-brain ticket <KEY>` instead of re-reading.

Every path is relative to the workspace root. The workspace's own facts (its repos, services, personas,
statuses, tracker and sprint naming) live in `ai-brain/profile/`; this file names the page and section to read.

## Where the plan lives

```
ai-brain/sprints/<sprint-slug>/plan/<KEY>.md      the plan, then its Dev report
ai-brain/sprints/<sprint-slug>/plan/<KEY>.html    its visualization (optional)
ai-brain/sprints/<sprint-slug>/reports/, bugs/    /bug-hunt's write-ups
```

- **The sprint slug comes from the tracker's current sprint**, the ticket's active sprint; how the slug is made
  and how to find the sprint: `ai-brain/profile/TRACKER.md` § Current sprint. Never hardcode a sprint, and never
  infer it from a folder listing — closed sprints have folders too.
- **The plan file is named after the ticket we are building.** For a sub-ticket that means the
  sub-ticket key. A plan named after the parent that covers the whole family is also valid — `/dev`
  accepts either, as long as the doc names the ticket in scope and covers its parent.
- Tickets that do not exist in the tracker yet use `NEW-<slug>.md`.

> **The archive.** Earlier plans may live in a plans archive: a `plans` knowledge repo in the brain's
> `project.toml`, which `plan-doc` reads through `PLAN_DOC_ARCHIVE` (`ai-brain/profile/REPOS.md`, "The plans
> archive"), some in an older `tickets/<KEY>/README.md` layout. If a ticket's only doc is there, `/plan` imports it
> (`ai-brain/bin/plan-doc import <path>`) and extends it rather than writing a second one.

`sprints/` is gitignored in `ai-brain`: the plan and its visualization are written there, on the
dev's own machine, through `ai-brain/bin/plan-doc` (`ai-brain/docs/SPRINTS.md`). They are
never committed, not in a code repo and not in `ai-brain`.

## If the plan already exists

`/plan` checks first, and the answer decides what it does:

| Found | What happens |
|---|---|
| Plan doc exists, and carries a parent view, a parity analysis and numbered action items | **Reuse it.** Re-verify its claims against the repos at their current SHAs, record what has changed since it was written, and go to development. Do not rewrite a sound plan. |
| Plan doc exists but is thin — no parity, no action items, or written against the wrong repo | **Refresh it in place.** Add the missing sections. Mark superseded analysis `⊘ DESCOPED` or `superseded` rather than deleting it; the record of what was believed is worth keeping. |
| No plan doc | **Write it.** Full planning pass, from the templates below. |

Refreshing beats rewriting. These docs are read by humans across sprints and their build logs are
evidence.

## Scoping the stack — FE, BE, or both

**The planner decides what the ticket actually covers. The subtask title is a hint.** Plenty of tickets that
read as full-stack are frontend-only, because the backend already exposes what the UI needs.

So before a single backend action item gets written, check the surface —
`ai-brain/profile/GRAPHQL_SURFACES.md` has the commands — and land on one of:

| Verdict | When | What the plan says |
|---|---|---|
| **`FE`** | The query and mutation exist and carry the fields the UI needs | Wire the existing operation: document → hook → component → tests. **Zero backend action items.** Name the operations and their `file:line` in the stack reason |
| **`FE`** + a codegen item | The field exists in the backend but not in the frontend's schema snapshot | One item for the schema dump and codegen (`ai-brain/profile/REPOS.md`, "Codegen"). Say which branch the field is on — a field only on an unmerged branch is a dependency, not a capability |
| **`FE+BE`** | An operation is missing a field, filter or argument | The backend item is scoped to that addition and nothing more |
| **`FE+BE`** / **`BE`** | Nothing covers it | Say what is being added, and what you searched to be sure nothing existing serves it |

A sibling subtask that owns the BE half changes the answer: merged makes this ticket `FE` with a dependency
recorded; unmerged makes it `FE` with a blocked item.

**Inventing backend work that already shipped is the most expensive planning mistake available here** — it
costs a build round, a review, and a PR that has to be closed. `/dev` re-checks the stack against the
surface before its first edit, and a disagreement goes back to the user *before* anyone writes code.

## What the planner must read before writing anything

1. The tracker's sub-ticket **and its parent** — description, acceptance criteria, technical-notes custom
   fields, status, assignee, sprint field, and **every sibling subtask**. A subtask read alone gives a
   keyhole view of a feature; the parent is where the shape is.
1. `ai-brain/profile/GRAPHQL_SURFACES.md`, and then the surface itself — before writing any backend
   action item. See the stack table above.
1. `ai-brain/docs/DESIGN_PARITY.md` and the Figma file, when the ticket has a design link.
2. `ai-brain/profile/MICROSERVICES.md` — which service owns this, and whether the ticket routes
   itself correctly.
3. `ai-brain/profile/DEFINITIONS.md` — personas, statuses, classifications. Never invent a status or a role.
4. The workspace's reference docs for the affected services and the data model
   (`ai-brain/profile/REPOS.md`, "Reference docs"). They are **snapshots that lag the code** — verify anything
   load-bearing against the schema file (`db/structure.sql` or `db/schema.rb`) and the service's code.
5. Prior plans for the same family, including closed sprints: `ai-brain ticket <PARENT>` and
   `ai-brain history <file>` list them from `ai-brain/sprints/` and the archive. A blocked parent
   usually already has one.
6. The code itself, at a named SHA per repo. A parity claim without a `file:line` is an opinion.

## The plan document

Model it on the workspace's house-style plan (`ai-brain/profile/LESSONS.md`, "House style"), when it names one;
`/plan`'s Step 6 lists the sections it writes, including **Files to touch** and **Services involved**, which the brain
reads (`ai-brain/docs/SPRINTS.md`). Required sections, in order:

1. **Header block** — ticket link + type + status + assignee; **parent feature** link and status;
   related tickets and their link type; **every sibling subtask** with owner and status; sprint name
   **and numeric id**; the repos in scope; and `Verified against:` — one line per repo with the branch
   and short SHA you read, and the date.
2. **TLDR** — required, plain English, no jargon, no file paths. Two halves: *what this is* (1–3
   sentences, including why it matters) and *how to test this* (1–3 sentences a human can follow).
   This is "The TLDR rule" in `ai-brain/docs/SPRINTS.md`, and it is not optional.
3. **How to read this doc** — one paragraph pointing at the sections that matter, plus a
   "if you have five minutes" line.
4. **Verdict up front** — numbered findings, each tagged: ✅ fine · 🟡 caveat · 🔴 spec or tracking
   defect · ⛔ blocked. State plainly whether the ticket is buildable this sprint, and what the critical
   path actually is (it is often review and merge, not engineering).
5. **What the ticket asks for** — the feature in one page, BE and FE, plus the invariants it rests on.
6. **Bird's-eye view** — the parent feature's full scope, where this sub-ticket sits inside it, what the
   siblings deliver, and the dependency chain with each link's real status.
7. **Parity analysis** — see below.
8. **Stack** — `FE` / `BE` / `FE+BE`, with the operations and `file:line` that decided it. See
   "Scoping the stack" above.
9. **Figma node inventory** — when the ticket has a design: every node, variant and state, with the file
   it maps to and its spacing, typography and colour tokens. Format in `DESIGN_PARITY.md`. This table is
   what the design QA lane checks against, so a node left out is a node nobody checks.
10. **The BE ↔ FE contract** — the SDL, the FE document, the field → UI mapping. Both sides are built
   and reviewed against this, not against the subtask charters. Skip it on an `FE` ticket, and say the
   contract is unchanged.
11. **Reuse inventory (DRY & KISS)** — each item takes the simplest shape that meets its rows; a heavier
   shape is a Decision that names the simpler one it beat (`ai-brain/docs/PRACTICES.md`, "KISS and
   DRY"). Then three lists: *reuse as-is*, *extend*, *write new*, from
   `ai-brain/profile/GRAPHQL_SURFACES.md`. Every entry names `file:line`.
12. **Action items** — see below.
13. **Delivery order** — what must merge before what, across repos.
14. **Testing** — the backend specs, the frontend tests, the e2e spec, and the manual/QA path. Name the files.
   Every parity row's test appears here.
15. **Open questions & decisions** — what needs a human, each with the decision it blocks.
16. **Build log** — appended per round as work lands, newest last. Never rewrite an old entry. Mid-round
   plan corrections (a stack change, an adjudicated design finding) land here too, dated.

## Parity analysis — the heart of it

**Parity here means: what the ticket assumes, versus what the repos actually contain today.** It is not
a pixel comparison. Tickets routinely assume UI, events, transports and endpoints that do not exist, and
every one of those is a round burned in development if it surfaces there instead of here.

One subsection per dimension, lettered `3A`, `3B`, `3C`…, each with:

| Field | Content |
|---|---|
| Dimension | What is being compared — "the event contract", "which frontend is this", "the 3-step accordion" |
| Side | `BE` · `FE` · `design` · `cross` |
| The ticket assumes | Quoted from the ticket or its AC |
| The repo today | What is actually there, with `repo/path/file.rb:41` and the branch/SHA you read |
| Verdict | `match` · `gap` · `blocked` · `unknown` |
| Consequence | What breaks, or what has to change, and which action item covers it |
| **Test** | **Required.** The spec that pins this row — see below |

### Every parity row names a test

Testing is not a phase that follows the work here; it is what keeps a parity claim true after the branch
merges. A row with no test is an incomplete row, and `/dev` treats the criterion behind it as unverified.

- **BE row** → the RSpec file and which path it covers. A policy row names **both** the allowed and the
  denied example.
- **FE row** → the frontend test file: a pure-helper unit test, or an integration test through the app's
  provider helper asserting on what the user sees across loading, error and success.
- **Design row** → the code value cited `file:line` (exact and re-checkable), plus the named e2e screenshot
  that records it visually.
- **Cross row** (a BE ↔ FE contract) → both sides: the backend spec and the frontend test that consumes it.
- **Cannot be pinned** → say why, in the row, and raise it as an open question. "Checked by hand" is an
  answer only when it names who checks it and when.

Dimensions worth checking on almost every ticket:

- **Which frontend?** A micro-frontend or the host app's own UI (`ai-brain/profile/MICROSERVICES.md` says which
  owns what). Technical notes that cite one frontend's conventions for work that lives in another are a 🔴 spec
  defect, and the fix is a ticket correction, not a code path.
- **Which service?** Route it against `ai-brain/profile/MICROSERVICES.md`. A decision placed in the wrong service is a
  design defect to raise in planning.
- **Does the surface it decorates exist?** A ticket that says "inside the accordion delivered by
  PROJ-120" fails if what shipped was a tab set.
- **Does the data exist?** Table, column, GraphQL field, projection. Check the schema file.
- **Does the producer exist?** An event with no emitter anywhere is ⛔, not 🟡.
- **Does the transport exist?** A push channel (WebSockets, ActionCable) or a stream the ticket assumes may not
  exist on that side; check before planning on it (`ai-brain/profile/MICROSERVICES.md`, "Transports").
- **Tracker status vs code.** A ticket marked Released that shipped nothing is a tracking defect that will
  otherwise be discovered as a "missing dependency" mid-build.
- **The existing test surface this disturbs.** Which specs change meaning.
- **Statuses and personas** against `ai-brain/profile/DEFINITIONS.md`.
- **The design**, when there is a Figma link: does every node in the file have a home in the code, and
  does every state the design draws exist? Full rubric in `ai-brain/docs/DESIGN_PARITY.md`; the
  node inventory is a required section of the plan.

## Action items

Numbered `AI-1`, `AI-2`, … grouped into phases, opening with a **status ledger** table so someone
picking the doc up mid-sprint can start there. Each item carries:

- **What** — one imperative sentence.
- **Repo + files** — where it lands. `unknown` is an answer; a wrong path is not.
- **Depends on** — other AI ids, or an external ticket with its status.
- **Verifies by** — the spec, command or manual step that proves it done.
- **Status** — `todo` · `in progress` · `done` · `blocked` · `descoped`.

Phase 0 is always **spec corrections** — tracker edits, wrong conventions, mis-tracked tickets. Those are
done before anyone writes code, because they change what "correct" means.

An action item that is blocked on someone else's ticket says so, names the ticket and its status, and
does not get quietly built around.

## The visualization

**Optional.** Nothing in `/plan` → `/dev` requires one. When a plan carries one, it is an HTML file
beside the plan markdown, illustrating the **bird's-eye view**: the parent feature, its
subtasks, the dependency chain with statuses, and the BE → FE data path for this ticket.

Non-negotiable rules:

- **Start from the workspace's diagram template** when it has one (`ai-brain/profile/REPOS.md`, "Reference
  docs"). Never copy a neighbouring diagram.
- **Minimalist black and white, always light.** No colour, no `prefers-color-scheme`, no `data-theme` —
  these get projected and printed, so they must not follow the viewer's OS theme.
- No CDN, no external fonts, no scripts.
- The markdown stays authoritative; the HTML illustrates it. Never HTML-only for prose.

Statuses in the diagram use the same tags as the verdict (✅ 🟡 🔴 ⛔) rendered as text, not colour —
colour must never be the only carrier of meaning.

## The tracker

- The site, board, project key, sprint query and who owns which ticket type: `ai-brain/profile/TRACKER.md`.
- With Jira, `sprint = NN` in JQL matches the sprint's **id**, not its name, and silently returns empty when
  given the number from a name — query by the numeric id, or by the full quoted name.
- With Jira, descriptions written through `createJiraIssue` / `editJiraIssue` use **ADF, not markdown** —
  markdown often renders empty. Comments in markdown are fine.
- The ticket's spec lives in `ai-brain/sprints/` and stays on the dev's machine; the tracker's description is a
  short summary, with no plan link.
- Parent stories and features stay with their product owners; only subtasks are assigned to developers
  (`ai-brain/profile/TRACKER.md` § Ticket family).
- **Drafting is text-only.** "Create X" while drafting means write the content for review. `/plan` and
  `/dev` write plan files in `ai-brain/sprints/`; neither edits a ticket without the user's yes
  in that run.
