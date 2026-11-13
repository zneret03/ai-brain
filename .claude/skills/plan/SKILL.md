---
description: Plan a ticket from its Jira link — asks the ai-brain first for what is already planned and built, reads the ticket, its parent and every subtask (the AC of all of them), maps the files involved with the ai-brain, has backend and frontend agents verify that map in parallel (each asking the brain before it searches), asks clarifying questions, decides FE / BE / FE+BE (including the backend a frontend ticket needs to close its gaps), cuts the ticket branch, and writes the parity + action-item plan, with the files to touch and the services involved, to ai-brain/sprints/<sprint>/plan/<KEY>.md, gitignored and local. The workspace's own facts come from ai-brain/profile/. Returns the plan as categorized tables. Writes no code.
argument-hint: "<jira-link|PROJ-123> [--figma <url>] [--more-context <text|@path|url>] [--sprint <slug>]"
disable-model-invocation: true
effort: max
allowed-tools: Bash(git -C:*), Bash(git status:*), Bash(git config:*), Bash(ls:*), Bash(mkdir:*), Bash(grep:*), Bash(date:*), Bash(ai-brain/bin/ai-brain:*), Bash(ai-brain/bin/plan-doc path:*), Bash(ai-brain/bin/plan-doc show:*), Bash(ai-brain/bin/plan-doc edit:*), Read, Write, Edit, Grep, Glob, Agent, AskUserQuestion, mcp__claude_ai_Atlassian__getAccessibleAtlassianResources, mcp__claude_ai_Atlassian__atlassianUserInfo, mcp__claude_ai_Atlassian__getJiraIssue, mcp__claude_ai_Atlassian__searchJiraIssuesUsingJql, mcp__claude_ai_Atlassian__getJiraIssueRemoteIssueLinks, mcp__claude_ai_Atlassian__getConfluencePage, mcp__claude_ai_Atlassian__fetch, mcp__claude_ai_Figma__get_metadata, mcp__claude_ai_Figma__get_screenshot, mcp__claude_ai_Figma__get_variable_defs
---

Plan one ticket: understand it, map the files it involves with the brain, check that map against both
halves of the stack, ask what the reading could not settle, and leave a parity + action-item plan in
`ai-brain/sprints/`, the source of truth for what is built. `/dev` starts from it knowing which files to
touch, which services are involved and which gaps to close.

Ticket and flags: $ARGUMENTS

Run this from the workspace root. Every path below is relative to it. The workspace's own facts (its repos, code
layout, services, personas, tracker and e2e suite) live in `ai-brain/profile/`, and each step names the file and
section it reads. When a file it names is missing, say which one, and that `ai-brain/profile.example/` shows its
shape.

## What this command does and does not do

- **Writes** `ai-brain/sprints/<sprint>/plan/<KEY>.md`, in the file `ai-brain/bin/plan-doc edit`
  prints. `sprints/` is gitignored, so the plan stays on this machine, never committed
  (`ai-brain/docs/SPRINTS.md`). Nothing else.
- **Asks the brain first, every time.** The brain's brief of the ticket opens Step 1, before Jira, and the map
  of files, services and earlier tickets comes from `ai-brain/bin/ai-brain` queries (Step 3). The survey
  agents start from that map and ask the brain for what it misses; they search the code only for what the brain
  cannot answer or does not hold.
- **Cuts** the ticket branch in each code repo the stack verdict puts in scope. The plan needs no branch.
- **Never** writes code, edits a Jira issue, commits or pushes.
- **Runs at maximum effort.** The frontmatter sets `effort: max` while it runs, and every subagent it
  launches is started with `effort: "max"`. Only a `CLAUDE_CODE_EFFORT_LEVEL` environment variable or
  an org effort cap outranks that.
- **It is a skill, not a command file, on purpose.** Claude Code ships a built-in `/plan` (enter plan
  mode); a project skill of the same name replaces it in a local terminal session, a command file is
  not documented to. Plan mode stays on Shift+Tab. `disable-model-invocation` keeps the word "plan" in
  a prompt from starting it.
- **No visualization.** Nothing downstream requires one: `/dev` works from the markdown alone, and
  `PLANNING.md` makes the `.html` optional.

`ai-brain/docs/PLANNING.md` is the planning contract — stack scoping, the parity dimensions,
the test every parity row owes. This command follows it, with the departures listed at the end.

## Inputs

| Give it | When | Effect if missing |
| --- | --- | --- |
| Jira link or key | always | Nothing to plan. Accepts `…/browse/PROJ-123`, `…?selectedIssue=PROJ-123`, or `PROJ-123`; the project key and the link forms are in `ai-brain/profile/TRACKER.md` § Site and board |
| `--figma <url>` | the ticket has a design | No design parity rows and no node inventory; the plan says so. Repeatable |
| `--more-context <text\|@path\|url>` | context lives in neither Jira nor the code | Authoritative about intent, never about code: a claim still needs a `path:line`. Repeatable |
| `--sprint <slug>` | the ticket is not in the current sprint | Resolved from Jira (Step 2); the slug form is in `TRACKER.md` § Current sprint |

Parse the key with `[A-Z][A-Z0-9]+-[0-9]+` off the link. No key found: stop and ask for it.

---

## Step 1 — ask the brain, then read the ticket family

**The brain comes first, before Jira.** From the workspace root:

```
ai-brain/bin/ai-brain fresh                  # one header line; keep it for Sources read
ai-brain/bin/ai-brain ticket <KEY>           # an earlier plan, report or bug, its branches, commits and PRs
ai-brain/bin/ai-brain ticket <PARENT>        # the parent's plan, and every sibling plan under it (child lines)
ai-brain/bin/ai-brain notes <domain words>   # notes and earlier plans, each ok, moved or gone
```

`ticket <KEY>` prints a `parent` line when the key was planned before; otherwise take the parent from Jira below
and run `ticket <PARENT>` then. The words for `notes` come from the ticket's title.

What the brain returns sets how much of the rest is new work. A plan for the key makes this a re-plan (Step 2):
read Jira for what changed against that plan's AC inventory instead of rebuilding it. Sibling plans under the
parent already hold most of the family's files, decisions and gaps, so build on them. The brain holds no Jira,
Figma, database rows or running app: the AC still come from the family below, and whatever else the brain lacks
is read from its own source, as far as this ticket needs it.

`ticket` reads `ai-brain/sprints/` and, when the project registers one, the plans archive of earlier sprints
(`ai-brain/profile/REPOS.md` § Knowledge repos). Notes are summaries at a pinned SHA: verify against code. When the
brain prints `ai-brain: not run (...)` (exit 3 or 4), keep that line for Sources read and grep instead: the greps
over `ai-brain/sprints`, the plans archive and the notes index are in `REPOS.md` § Knowledge repos.

Then the ticket family, via the Atlassian tools (`getAccessibleAtlassianResources` gives the cloud id):

- **The ticket**: every field, with field names expanded. The description can be empty while the content lives in
  custom fields; `ai-brain/profile/TRACKER.md` § Ticket family names them. Read those before concluding the ticket
  is unspecified.
- **Its parent**, in full. A subtask read alone is a keyhole view; the parent is where the shape is.
- **Every sibling**: `parent = <PARENT> ORDER BY key` — key, title, owner, status, and whether its
  charter overlaps this one.
- **Issue links** with their link type and real status (a "relates" is not a parent), and the remote
  links (`getJiraIssueRemoteIssueLinks`) — Figma and Confluence links usually sit there. Read any
  Confluence page the ticket names as its spec.

**Acceptance criteria — always from the parent and every subtask.** Whichever level the link points
at, collect the AC of the whole family, never of the ticket alone:

- The **parent** and **every subtask** under it: the siblings above, plus the ticket itself. When the
  link is the parent, its subtasks are `parent = <KEY> ORDER BY key`.
- Every place AC live: the description (often a checklist), and the fields `TRACKER.md` § Ticket family lists.
- One inventory row per criterion: `<source key>/AC<n>` (e.g. `PROJ-101/AC2`), the source field, the
  text verbatim, and the owner: this ticket, a sibling's key, or nobody.

Then read the inventory for gaps. A parent AC no subtask owns is a Spec & tracking parity row. A subtask
AC that narrows or contradicts the parent's is a Step 4 question. No AC anywhere in the family is a 🔴
verdict finding; never invent criteria to fill the hole.

## Step 2 — resolve the sprint and any existing plan

**Sprint.** `--sprint` wins. Otherwise take it from Jira, never from a table, which lags:

1. The ticket's sprint field — the sprint whose state is `active`.
2. None active: the fallback query in `ai-brain/profile/TRACKER.md` § Current sprint, and note in the plan header
   that Jira still lists the ticket in its old sprint.

The sprint's name maps to its folder slug by the rule in `TRACKER.md` § Current sprint. Record the slug **and** the
numeric sprint id. A new sprint is only a new folder, made in Step 6; `ai-brain sprint <slug>` is its dashboard.

**Existing plan.** From the Step 1 `ticket` lines (`plan`, `also`, `child`):

| Found | Do |
| --- | --- |
| `ai-brain/sprints/<slug>/plan/<KEY>.md` | **Re-plan in place.** Keep Decisions, Log and any Dev report; mark superseded rows `superseded` rather than deleting them |
| A plan for the key only in the plans archive | Import it first, `ai-brain/bin/plan-doc import <its sprints/… path>` (it asks; the archive is `PLAN_DOC_ARCHIVE`), then re-plan in place |
| A doc for the key in an earlier sprint, or under `tickets/` | Read it, then ask in Step 4: move it into this sprint, or extend it where it is |
| A plan under the **parent** key covering the family | Read it; this plan links to it instead of restating the bird's-eye view |
| Nothing | Write a new one |

## Step 3 — map the files with the brain, then verify the map in parallel

### 3a. The file map, from the brain

Before any agent reads a file, ask the brain where the ticket lands. For each concept the AC name (an operation,
a field, a page, a table, a topic, a job), from the workspace root:

| Ask | For | Gives |
| --- | --- | --- |
| `ai-brain surface <words>` | each concept | the interfaces by name, where each is implemented, how many consumers |
| `ai-brain find <words>` | each behaviour the AC describe | the code that already does it, by symbol and parameter names |
| `ai-brain trace <field>` | each field the UI shows | frontend page → document → resolver → table |
| `ai-brain impact <interface or repo/path>` | each interface the ticket changes | its consumers and the specs that pin it |
| `ai-brain history <repo/path>` | each file the map lands on | the earlier tickets that planned or changed it; their plans are prior art, their Decisions bind |
| `ai-brain notes <repo/path>` | each file the map lands on | the notes, the practices and the earlier `/branch-review` rounds that cite it; a review's finding on that file is a shape the plan does not repeat |
| `ai-brain related <PARENT>` | the family | the tickets that touched the same files, rarest files first |

Write the answers as the **file map**: `| File (repo/path:line) | In scope because | Lead (the brain line) |
Change: edit, extend, add or test |`, then the services those files belong to (the `service` lines of
`ai-brain ticket` once the plan is indexed, or the engine or pilet each path sits under). It becomes the plan's
**Files to touch** and **Services involved** (Step 6). A file to be added is a row too, `add`, with the folder it
goes in. The trust rule (`ai-brain/docs/AI_BRAIN.md`): a brain line is a lead until its `path:line` is
opened. On `ai-brain: not run (...)`, keep the line for Sources read and say "no map" to both agents.

### 3b. Backend and frontend agents verify the map

Launch two agents **in one message** so they run together: `subagent_type: "general-purpose"`,
`effort: "max"`. Both are **read-only** — say so in the prompt: no edits, no git writes. Give each the
key, the whole AC inventory from Step 1 and the custom-field text verbatim, the siblings, every
`--more-context` item, and its half of the file map under the heading "File map (<the brain's header line>)",
with this rule: **open each mapped `path:line` first and judge it; drop and note a row the file does not bear
out; add only what the map misses, and say how you found it.** The map is where the agent starts, not a substitute
for reading: the brain holds edges, never behaviour. **For what the map misses, the agent asks the brain before
it searches:** it runs `ai-brain/bin/ai-brain` from the workspace root (`find`, `surface`, `trace`, `impact`,
`consumers`, `history`; one example per verb in `ai-brain/.claude/skills/ai-brain/SKILL.md`) before any
Grep, Glob or shell search, and searches only where the brain answers `none` or `ai-brain: not run`, or for what
it does not hold: behaviour inside a method, copy, Jira, Figma, database rows, a running app. Each returns tables
in which **every row carries a `path:line`** and the AC ids it bears on, the file map with each row kept, dropped
or added (an added row says whether its lead came from the brain or a search), the number of brain queries and
of searches it ran, and the branch and short SHA of each repo it read
(`git -C <repo> rev-parse --abbrev-ref HEAD` and `--short HEAD`).

Where the docs and the disk name different paths, the real layout is in `ai-brain/profile/CODE_MAP.md`
§ File map. Give that section to both agents.

**Backend agent** — what the engines and the app hold today for what the ticket needs:

- Route the ticket to its engine with `ai-brain/profile/MICROSERVICES.md`. A need routed to an engine that does
  not own it is a routing defect (the ones this workspace sees: `MICROSERVICES.md` § Routing defects), reported
  as a finding.
- The contract index is the truth (`ai-brain/profile/CODE_MAP.md` § Contract files): a field not registered there
  does not exist, however many resolver files mention it. Per need: the operation, its arguments, filters and
  fields.
- Authorization per persona — the policy, with the allowed and the denied path. Personas and statuses
  from `ai-brain/profile/DEFINITIONS.md`; never invent one.
- The data: table and column in the schema file `CODE_MAP.md` § File map names. The producer of any event the
  ticket assumes (an event nobody emits is blocked, not a caveat), and the transport each side really has
  (`CODE_MAP.md` § File map).
- The app side, where the ticket crosses into it (its GraphQL folder: `CODE_MAP.md` § File map).
- The RSpec files that pin today's behaviour and would change meaning.
- Verdict per need: `exists` · `exists, missing <field/arg/filter>` · `missing` · `blocked` · `unknown`.

**Frontend agent** — what the frontend repo the ticket lands in holds today (`ai-brain/profile/REPOS.md`):

- The page, route, guard, component and copy the ticket decorates — and whether it really lives in that frontend.
  A spec that cites another app's conventions for frontend work is a spec defect, not a code path.
- The documents, the hooks and the privileges, where `CODE_MAP.md` § File map puts them in a frontend.
- The schema snapshot (`CODE_MAP.md` § Contract files): every field the UI needs, present or absent there.
  **An absent field is a backend gap candidate** — list each one by name.
- The states the feature can enter — loading, empty, error, denied, zero — and which exist today.
- Where new reads and writes must follow a frontend convention the workspace states (`CODE_MAP.md` § File map
  names it and its files). Name the files; do not restate the rules.
- The Jest suites that pin today's behaviour, and any e2e spec on the surface (the suite:
  `ai-brain/profile/E2E.md` § Suite).
- A repo the workspace does not clone (`REPOS.md`) has no code to read: a need there is `unknown`, said plainly.

With `--figma`: inventory the nodes yourself while the agents run — `get_metadata` for the tree,
`get_variable_defs` for tokens, `get_screenshot` for the reference — in the table format of
`ai-brain/docs/DESIGN_PARITY.md`. Every variant and state is its own row.

**Verify before you trust.** Open the `path:line` behind every row that decides the stack or blocks the
ticket. An agent's claim is a lead; the file is the evidence.

## Step 4 — decide the stack, then ask

**The stack** follows the "Scoping the stack" table in `PLANNING.md`, decided from the surveys, never
from the ticket's title or its `(FE)` / `(BE)` prefix. One addition this command owns:

> **A frontend ticket with a backend gap is `FE+BE`.** When the UI needs a field, argument, filter or
> operation the surface lacks, the plan adds **backend gap-fill** items scoped to exactly that
> addition — named, with what was searched to prove it is missing. Nothing more rides along.

A sibling that owns the backend half changes the answer: merged makes this `FE` with a recorded
dependency; unmerged makes it `FE` with a blocked item. Inventing engine work that already shipped is
the most expensive planning mistake available here.

**Then ask, with `AskUserQuestion`.** Always one round, at most two. Up to four questions per round,
two to four options each, the recommended option first and marked `(Recommended)`.

- **Q1 is always the understanding check**: the scope in one sentence plus the stack verdict — "Is this
  the ticket?" — with options for as-stated, narrower, and wider.
- The rest come only from what the reading surfaced. Typical triggers:
  - AC that are ambiguous or compound, a subtask AC that narrows or contradicts the parent's, or a
    parent AC no subtask owns.
  - The ticket assumes UI, data, an event or a transport that does not exist: gap-fill it here,
    descope it, or block on another ticket.
  - A sibling whose charter overlaps this one.
  - A persona or role whose behaviour the ticket does not state.
  - A design is mentioned but no Figma link was given or found.
  - A plan or ticket branch already exists from an earlier run: continue it, or start a new version.
- Every question cites its evidence — the Jira field or the `path:line` — in its own text.
- Never ask what Jira or the code already answers. That is reading left undone.

Record every answer in the plan's **Decisions**, dated; free-text answers verbatim. A question the user
skips goes to **Open questions** with the default the plan proceeds on.

## Step 5 — cut the ticket branch

**Name:** `<name>/<key>-v<n>`, lowercase — e.g. `you/proj-123-v1` — the convention in
`ai-brain/CLAUDE.md` under "Branching", one name across every repo.

- `<name>`: the local part of `git config user.email`. Unset: the local part of the Atlassian account
  email (`atlassianUserInfo`). Still nothing: ask.
- `<n>`: `1`, unless a branch for this ticket exists locally (`git -C <repo> branch --list '<name>/<key>-v*'`)
  or on origin (`git -C <repo> ls-remote --heads origin '<name>/<key>-v*'`). Then follow the Step 4
  answer: switch to it, or take the highest `v` plus one.

**Repos:** each code repo the stack puts in scope, by `ai-brain/profile/REPOS.md` § Stack to repos (`BE`, `FE`,
`FE+BE`). The code branches stay empty and local; they exist so `/dev` and the developer start on the
ticket's branch. The plan itself goes to `ai-brain/sprints/`, which is gitignored, so it needs no
branch, and the plans archive gets none.

Per repo:

```
git -C <repo> status --porcelain                                # must print nothing
git -C <repo> rev-parse --abbrev-ref HEAD                       # base branch, or this ticket's branch
git -C <repo> symbolic-ref --short refs/remotes/origin/HEAD     # origin/<base>
git -C <repo> fetch origin <base>
git -C <repo> switch --no-track -c <branch> origin/<base>
```

- Already on this ticket's branch: keep it, and say so.
- **Dirty tree, or parked on another ticket's branch: do not switch, stash, commit or discard.** Skip
  that repo and report why.
- Never write on `main`, `development`, `staging` or `develop`. Nothing is pushed here.
- **No worktrees.** The branch is checked out in the repo's own checkout, where the dev servers, the
  editor and `/dev` look (workspace `CLAUDE.md`). A repo that cannot be switched is skipped
  and reported, never worked around with `git worktree add`.

Record each repo's branch, base and base SHA — they go in action item `A0`.

## Step 6 — write the plan

`ai-brain/sprints/<slug>/plan/<KEY>.md`. Get the file to write with
`ai-brain/bin/plan-doc edit sprints/<slug>/plan/<KEY>.md`: it prints the same file whatever branch
`ai-brain` is on, and makes the sprint's `plan/` folder the first time.

The house style is plain prose, short sentences, a `path:line` behind every claim. When
`ai-brain/profile/LESSONS.md` § House style names a plan to model, read it first. Sections in this order; `/dev`
reads them by these headings and works the ledger as written, and the brain reads the ones
`ai-brain/docs/SPRINTS.md` lists ("What the brain reads from a plan"):

1. **Header block** — ticket link, type, status, owner; sprint name and numeric id; parent; stack;
   repos; branch per repo.
2. **TLDR** — what this is and how to test it, for someone who has never seen the ticket. The rule is
   in `ai-brain/docs/SPRINTS.md`, "The TLDR rule". No jargon, no paths.
3. **Verdict** — numbered findings tagged ✅ fine · 🟡 caveat · 🔴 spec or tracking defect · ⛔ blocked.
   Say whether it is buildable this sprint, and what the critical path really is.
4. **What the ticket asks for** — the feature in a page, then **Scope**: In and Out, each Out with its
   reason or owning ticket.
5. **Acceptance criteria** — the Step 1 inventory, parent and every subtask:

   | AC | Source field | Criterion (verbatim) | Owner | Covered by |
   |---|---|---|---|---|

   *Covered by* names the parity rows and action items for every AC this ticket owns, the sibling for
   one it does not, and `none — gap` for a parent AC nobody owns.
6. **Bird's-eye view** — the parent's whole scope, a siblings table (key · title · owner · status ·
   overlap), and the dependency chain with each link's real status.
7. **Sources read** — `| Repo | Ref | SHA |`, plus the Jira and Confluence pages and the notes, and under
   the table the brain's header line from Step 1, or its `ai-brain: not run (<reason>)` line.
8. **Stack** — the verdict, the operations and `path:line` that decided it, and when there is any, the
   backend gap-fill table:

   | # | Frontend need | Missing on the surface (searched where) | Backend addition, scoped | Engine |
   |---|---|---|---|---|

9. **Parity analysis** — categorized, one subsection each, in this order. An empty category keeps its
   heading and the line "None.":

   | Category | Row ids | Holds |
   |---|---|---|
   | Backend | `B1`, `B2`… | operations, fields, policies, data, producers, engine specs |
   | Frontend | `F1`… | pages, guards, documents, hooks, states, copy, cache convention, Jest |
   | Contract | `C1`… | the BE ↔ FE seam: SDL field ↔ document ↔ UI, the schema snapshot |
   | Design | `D1`… | only with a Figma link; the node inventory follows the table |
   | Spec & tracking | `S1`… | Jira vs code: wrong frontend named, status vs what shipped, AC gaps |

   Every table has the same columns:

   | # | Area | Exists on `<base>` | Should (ticket) | Verdict | Gap → action | Test |
   |---|---|---|---|---|---|---|

   Verdict is `match`, `gap`, `blocked` or `unknown` — `unknown` beats a guess. **Every row names its
   test**, per "Every parity row names a test" in `PLANNING.md`; a row that cannot be pinned says why.
10. **Reuse inventory** — reuse as-is · extend · write new, each entry with `path:line`.
11. **Files to touch** — the Step 3 file map as the agents left it, one row per file:

    | File | Change | Items | Why |
    |---|---|---|---|

    *File* is the full path from the workspace root, with a line where one matters
    (`monorepo/gems/orders/app/…/x.rb:42`, `web-app/src/…/X.tsx`), so the
    brain resolves it to exactly one file. *Change* is `edit`, `extend`, `extract`, `add`, `delete` or `test`;
    a file still to be written is `add`. *Items* names the action items that touch it. This table is what `/dev`
    starts from, and what `ai-brain ticket`, `history` and `related` answer with.
12. **Services involved** — `| Service | Kind | Side | What changes |`: each engine, the monolith app, each
    pilet or the shell the files above sit in, with the one-line change in each.
13. **Action items** — the ledger:

    | # | Phase | Side | Action | Repo + files | Closes | Depends on | Verifies by | Status |
    |---|---|---|---|---|---|---|---|---|

    *Repo + files* uses the same full paths as Files to touch. `A0` is the branch, `done`. Phase 0 is spec
    corrections — Jira edits, wrong conventions — before
    any code. An item that posts a Jira comment drafts it by `ai-brain/docs/JIRA_COMMENTS.md`. Then backend, frontend, tests and e2e, PR. **Every `gap` row and every AC this ticket
    owns is closed by at least one item; each item names the rows and AC ids it closes.** Status: `todo` · `in progress` · `done` ·
    `blocked` · `descoped`. Blocked names the ticket and its status.

    **A demo item always precedes the PR item.** `/dev` carries it out: before-and-after screenshots of
    every screen an owned AC names, in each mode or width the AC names, plus an mp4 and a GIF. All come
    from a real browser on the local stack, with real accounts on a test client, clicking what the
    persona would click: no seeders. "Before" is shot on the ticket branch before its first code change;
    a branch that already has changes takes it from `git archive origin/<base>` in the scratchpad, never
    a worktree. Write the item as the click path each AC needs, and name any AC no click path can reach
    (a rule that blocks the state, a picker with no seconds), with the test that covers it instead.
    They go in the ticket's evidence folder beside this plan, `ai-brain/sprints/<sprint>/evidence/<KEY>/`
    (gitignored; `ai-brain/docs/SPRINTS.md` § Evidence), with a `notes.md` saying where each came from: which
    local stack, which data, which persona and how it was granted. The PR item depends on it: every PR body
    opens with `# Demo`, the before/after pairs uploaded into it by `ai-brain/bin/pr-images`.
14. **Delivery order** — what merges before what, across repos, by the pairing rules in
    `ai-brain/profile/REPOS.md` § Delivery order. A BE contract change ships with its frontend consumer.
15. **Testing** — the RSpec, Jest and Playwright files, and the manual path a human follows.
16. **Decisions** — the Step 4 answers and the calls the plan made, each with the rejected option. Where two
    shapes meet the AC, the simpler one is planned and the heavier one is recorded here with why it lost.
17. **Open questions** — `- [ ] Q1. …`, each with who decides, what it blocks, and the default.
18. **Deferred** — out of scope, with the reason.
19. **Log** — `- YYYY-MM-DD: Planned. Branch <branch> cut from <base> at <sha>; not pushed.` Append on
    re-plan; never rewrite an entry.

`/dev` adds a **Dev report** between Deferred and Log; a re-plan keeps it. Prose follows
`ai-brain/docs/SPRINTS.md`: relative links, no code blocks of product code, no AI attribution
anywhere.

## Step 7 — return the plan

**First, print the finished plan doc in full** — `ai-brain/bin/plan-doc show <KEY>`, exactly as written,
every section, nothing summarised or elided. The user reviews the real document, not a digest of it.

Then the read-out, as categorized tables:

1. **Ticket** — key, title, type, parent, sprint (slug + id), doc path, and per repo: branch, base,
   or why it was skipped.
2. **Stack** — `| Verdict | Why | Evidence (path:line) |`, then the backend gap-fill table if any.
3. **Acceptance criteria** — `| AC | Owner | Covered by |`, parent and every subtask.
4. **Parity**, one table per category — `| # | Area | Verdict | Gap → action |` — each headed with its
   count by verdict.
5. **Files to touch** and **Services involved**, as in the plan.
6. **Action items**, grouped by phase — `| # | Side | Action | Status |`.
7. **Open questions** — one line each, with its default.
8. **Brain and files** — the brain queries run, by verb, in the main session and in each agent; the files
   opened; and each search made where the brain had no answer, with what it was for.

Then re-index so the brain serves the plan to `/dev`:
`ai-brain/bin/ai-brain index --background`, then `ai-brain ticket <KEY>` shows its `plan`, `touch`,
`service` and `gap` lines. The plan is not committed: `sprints/` is gitignored, so it stays on this machine
(`ai-brain/docs/SPRINTS.md`). Code-repo branches are never committed to or pushed by this command.

If the user's answer, or a review comment, changes the plan, edit the doc and print it in full again.

End with the next step: `/dev <KEY>`, which builds from this plan.

## Departures from `PLANNING.md`

- **Sprint from Jira, not a table** — because a table lags.
- **The workspace's real paths**, per `ai-brain/profile/CODE_MAP.md` § File map.
- **No visualization**, and the house style `ai-brain/profile/LESSONS.md` § House style names, when it names one.

## Rules

- No code, no Jira edits, no commit or push.
- The plan lives in `ai-brain/sprints/`, gitignored and local, written through `plan-doc`. It is the source of
  truth `/dev` builds from: its Files to touch, Services involved and open gaps are what `/dev` starts with.
- The brain comes first: its brief opens Step 1, the Step 3 file map is built from its queries, and the agents
  ask it before they search. Then they open and judge every row.
- AC come from the parent and every subtask, every time. The ticket alone is a keyhole.
- The stack comes from the surface, never the title. No backend item without proof the surface lacks it.
- Keep it simple (KISS). Plan the simplest shape that meets the AC: reuse or extend before adding, and no new
  file, layer, option, flag or abstraction that no AC needs. Each action item is one change a reviewer can read
  in one sitting. The signals and examples: `ai-brain/docs/PRACTICES.md`, "KISS and DRY".
- Every parity row: a `path:line` and a test. `unknown` over a guess.
- Brain lines are leads: open the `path:line` before a lead becomes a row.
- Every plan has a demo item before its PR item, and every PR opens with `# Demo`.
- Never switch a dirty repo, or one parked on another ticket's branch.
- Questions are grounded in evidence and answered in the doc. Nothing the user said lives only in chat.
