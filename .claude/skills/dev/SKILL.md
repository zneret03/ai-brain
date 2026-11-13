---
description: Build a ticket from the plan /plan wrote. Works the plan's action items and parity rows on the ticket branches, reusing what other features already built instead of writing a second copy, runs each repo's gates, then checks the change on the local stack the way its users will — real accounts, real buttons, no seeders — as each persona the acceptance criteria name, hunting the edge and worst cases a user would hit. Captures before and after screenshots, an mp4 and a GIF, and on your yes commits, pushes and opens the PRs with the evidence on top. Starts from the ai-brain's brief of the ticket (plan, files to touch, services, open gaps, who built what) and ends by writing a Dev report into the plan in ai-brain/sprints. The product facts it needs (repos, entry points, test data, the evidence folder) come from ai-brain/profile/.
argument-hint: "<jira-link|PROJ-123> [--draft] [--no-pr]"
disable-model-invocation: true
effort: max
allowed-tools: Read, Write, Edit, Grep, Glob, AskUserQuestion, SendUserFile, Bash(ls:*), Bash(grep:*), Bash(date:*), Bash(ffprobe:*), Bash(ai-brain/bin/ai-brain:*), Bash(ai-brain/bin/plan-doc path:*), Bash(ai-brain/bin/plan-doc show:*), Bash(ai-brain/bin/plan-doc edit:*), mcp__claude_ai_Atlassian__getAccessibleAtlassianResources, mcp__claude_ai_Atlassian__getJiraIssue, mcp__claude_ai_Atlassian__searchJiraIssuesUsingJql
hooks:
  PostToolUse:
    - matcher: "Edit|Write"
      hooks:
        - type: command
          command: "${CLAUDE_PROJECT_DIR}/ai-brain/bin/ai-brain-hook"
          args: []
          timeout: 5
---

Build one planned ticket: work its plan, check it in a real browser as its users will, and open the
PRs with the evidence on top.

Ticket and flags: $ARGUMENTS

Run from the workspace root. Every path below is relative to it. The product facts this skill needs (the repos
and their gates, the entry points, the test data, the recording and evidence folders) live in the profile,
`ai-brain/profile/`; each step names the file and section it reads, and `ai-brain/profile.example/` shows the shape.

## What this does and does not do

- **Reads** the plan `/plan` wrote, `ai-brain/sprints/<sprint>/plan/<KEY>.md`, the source of truth for
  what is built. No plan, no build: stop and say to run `/plan <KEY>` first.
- **Writes** code only in the repos the plan's stack names, on the ticket branch `/plan` cut, and keeps
  the plan's action-item statuses, Decisions and Log current as items land, in the file
  `ai-brain/bin/plan-doc edit` prints.
- **Ends with a Dev report in the plan**, shipped or not: what was built and how it works now, every file
  changed, the PRs, and what is left. The next session, the reviewer and the brain read it there.
- **Checks** the change on the local stack with real accounts and real clicks, on a test client. It never
  seeds, never calls the engine's debug mutations, never sends a GraphQL request the UI would not send,
  and never writes to a database by hand. Waits are real.
- **Never** points a browser at a shared development, staging or production environment
  (`ai-brain/profile/QA.md` § Environment names them). That is `/qa-demo`'s job, and it saves nothing there.
- **Commits, pushes and opens PRs** only after a yes. Never merges, never force-pushes, never
  `--no-verify`. No AI attribution in any commit, PR or comment.
- **Reads the ticket and the code through the brain first.** `ai-brain ticket <KEY>` is the brief: the plan,
  the files to touch, the services, the open gaps, the branches and who holds them, the commits and who made
  them, the PRs, the related tickets. Every code fact a later step needs comes from
  `ai-brain/bin/ai-brain` before any grep: the surface, what already exists, who consumes a change,
  which specs pin it, who wrote a file. The file at each lead's `path:line` confirms it. Step 1's `fresh`
  starts Neo4j when it is down; the run ends by updating the brain (Final report).

`allowed-tools` leaves out git, gh, psql and every Jira write on purpose, so each of those asks first.

| Give it | Effect |
| --- | --- |
| Jira link or key | Required. Parsed with `[A-Z][A-Z0-9]+-[0-9]+` |
| `--draft` | PRs open as drafts |
| `--no-pr` | Push the branches, open nothing, report the compare URLs |

## Step 1 — load the plan and the branches

1. **Ask the brain for the ticket.** `ai-brain/bin/ai-brain ticket <KEY> --all` prints the plan's path,
   its TLDR, the items done, the branches in every repo with who holds them, the commits and who made them,
   the PRs, the services, the open gaps and items, every file to touch and every file a Dev report already
   changed, and the related tickets. Without the brain: `ai-brain/bin/plan-doc path <KEY>`. No plan
   in `ai-brain/sprints/`: stop, `/plan <KEY>` first; one only in the plans archive is imported by
   `/plan`.
2. **Read the plan whole**: `ai-brain/bin/plan-doc show <KEY>`. The header (stack, repos, branches),
   the AC table, every parity row, the Reuse inventory, **Files to touch** and **Services involved**, the
   action items, Delivery order, Testing, Decisions, Open questions, and a Dev report from an earlier run.
   These define what "done" means, and Files to touch is where the build starts: open those files rather than
   search for them. An open question that blocks an item is asked (`AskUserQuestion`) before that item, and
   the answer goes in Decisions, dated. Every edit to the plan goes in the file
   `plan-doc edit sprints/<slug>/plan/<KEY>.md` prints.
3. **Each repo the stack names** must be on the plan's branch, `<name>/<key>-v<n>`:
   - Already on it: keep it.
   - On its base and clean, with the branch existing: switch to it. Branch missing: cut it from
     `origin/<base>` and record it in the plan's `A0`.
   - Dirty, or parked on another ticket's branch: stop and ask. Never stash, commit or discard someone
     else's work, and never route around it with `git worktree add`.
4. **Has the base moved?** `git -C <repo> fetch origin <base>`, then compare with the SHA in the plan's
   Sources read: `git -C <repo> diff --stat <plan-sha>..origin/<base> -- <the paths the plan cites>`. A
   change in a cited path is re-read before building and logged in the plan.
5. **Re-check the stack.** Run `ai-brain/bin/ai-brain fresh`, then `ai-brain surface <words>` for the
   operations the plan relies on and the ones it adds. The operations it relies on still exist, and the ones it
   adds are still missing from the contract files (`ai-brain/profile/CODE_MAP.md` § Contract files: the query and
   mutation type files, each frontend's schema snapshot). A disagreement goes to the user before any code is
   written. On `ai-brain: not run (...)`, record the line and read those files only.
6. **What changed since the plan, and who built it.** For each file to touch,
   `ai-brain/bin/ai-brain history <repo/path>`: a ticket that planned or changed it after this plan was
   written is read before building, and a clash is a new parity row or an open question. `ai-brain related <KEY>`
   names the tickets sharing the most of these files, and `ai-brain who <repo/path>` the people who wrote a
   file the plan is unsure of: name them in the plan when the approach depends on them. `ai-brain notes
   <repo/path>` lists the notes, practices and earlier `/branch-review` rounds that cite each file: read a
   review's finding on a file before editing it, and do not write the shape it flagged. Gaps the plan missed
   still become new rows (Step 3).
7. Read each touched repo's own `CLAUDE.md` before editing it.

## Step 2 — the "before" evidence, before the first edit

Until its first code change, the ticket branch is its base, so the old behaviour is shot from the real app
now: run Step 5's mechanics for every scenario the "after" run will show, and save the frames as `before`.

- Branch already carries changes (a resumed run): ask. The choices are a `before` from
  `git archive origin/<base> | tar -x -C <scratchpad>/before-<repo>`, run from there, or no `before` with
  the reason in `notes.md` and the PR. Never stash to get one.
- A ticket no browser can show (a pure contract or job change) has no `before`; say so.

## Step 3 — build, item by item

Work the action items in the plan's Delivery order. Per item:

1. Mark it `in progress` in the plan.
2. Settle what the item can take from code that already exists ("Reuse before you write", below), and
   write each verdict in the plan's Reuse inventory.
3. Open the `path:line` its parity rows cite, then make the smallest change that closes them
   (`ai-brain/CLAUDE.md`, "Change discipline"), in the plainest code that does it (KISS:
   `ai-brain/docs/PRACTICES.md`, "KISS and DRY"). Follow the workspace `CLAUDE.md` rules: its frontend
   convention for any new read or write, the comment budget, one fact in one place.
4. Write the test the parity row names. A row without a test is not done.
5. Mark it `done` with the date.

Anything the plan did not foresee becomes a new parity row and action item, or an open question, written
in the plan before it is built. A Jira item in Phase 0 waits for the user's yes, and its comment is written by
`ai-brain/docs/JIRA_COMMENTS.md`.

A contract change goes engine first, then the frontend's codegen chain (`ai-brain/profile/REPOS.md`, "Codegen";
`ai-brain/profile/CODE_MAP.md` § Contract files).

### Reuse before you write

A second copy of something the repo already does is a defect here, however small: the copies drift, and
the next fix lands in only one. A frontend that already formats a date range three ways (`formatRange` and
`formatShortRange` in `src/helpers/dateFormat.ts`, `formatPeriodLabel` in `src/helpers/periods.ts`) does not
need a fourth, and this step exists to stop it.

1. **Start from the plan's Reuse inventory, then search past it.** `/plan` builds it from the GraphQL
   surface, so components, helpers and spec support are mostly missing from it.
2. **Search by what the code does, not by the name you would give it**: the domain words, the field it
   reads, the text the screen shows, the arguments it takes. Ask the brain first:
   `ai-brain/bin/ai-brain find <words>` matches symbol names and parameter names in every repo
   (`find format start end` lists all three formatters above), and `ai-brain trace <field>` lists the code that
   already reads a field. Open each lead before it becomes a verdict. Then search the whole repo, not only the
   feature's folder (in a monorepo, the engine or app the item touches), shared places first. Each repo's shared
   places and test helpers are in `ai-brain/profile/CODE_MAP.md` § Reuse homes; for a repo it does not list,
   read that repo's own `CLAUDE.md` for where shared code lives.

3. **Give each need one verdict**, with its `path:line`:

   | Verdict | When | Do |
   | --- | --- | --- |
   | Reuse as-is | It does the job and can be imported as it stands | Call it. No copy, and no wrapper that only renames it |
   | Extend | It does most of the job | Add what it lacks, with today's behaviour as the default, so every existing caller is unchanged |
   | Extract | It does the job but is locked inside another feature: not exported, or inline in a component | Move it to the shared place, into an existing file there before a new one. Point the old caller at it, then use it. A pure move: the old caller's specs pass unchanged |
   | Write new | Nothing does the job, or the look-alike would change for a different reason | Write it, and record what was searched and why the look-alike does not fit |

   The plan's Reuse inventory keeps its three lists, so an extract goes under *extend*, marked `extract`.
   "Write new" without a recorded search is not a verdict; the record names the brain search beside the grep,
   or the brain's `not run` line.
4. **Share what changes together, not what looks alike.** Two copies of one rule share one
   implementation; two blocks that only look the same stay apart. An option that names a property
   (`timeZone` on `formatTime`) is an extend. A flag or branch that names a caller
   (`isAdminPage`, `when :csv_export`) means they are different things: write new.
5. **Limits.**
   - An extend or extract the plan does not carry is a new action item, written before it is built.
     Change discipline's ~20-line stop applies to it like any other change.
   - An extract stays inside the repo, engine or app that holds both callers. Code two engines would
     share belongs in the shared library the app pins by tag (`ai-brain/profile/CODE_MAP.md` § Reuse homes
     names it): an open question in the plan, never part of this diff.
   - An older feature's bare `useQuery` or blanket `refetchQueries` is not a pattern to reuse. New code
     follows the workspace `CLAUDE.md` frontend convention even where its neighbours do not.

## Step 4 — gates

For every repo the diff touched, its gate commands (`ai-brain/profile/REPOS.md`, with any extra in
`ai-brain/profile/STACK.md` § Gates): the linter scoped to the diff, the specs scoped to the specs the diff
touches and the specs of every existing caller an extend or extract changed, and each frontend's lint,
type-check and test commands. The specs that pin a touched file are the `test` lines of
`ai-brain/bin/ai-brain impact <repo>/<path>`; they run too. Red sends you back to Step 3. Report each check
with its exact scope; a check that did not run is reported as not run.

## Step 5 — check it as the users will

**Ask first, every time this step is reached** (`AskUserQuestion`), which entry point to drive. The entry points
are in `ai-brain/profile/STACK.md` § Entry points: for each, its URL, how a user reaches the feature there, what
it needs turned on, and its start command. The question is a call of its own and holds those options and the test
client to use (below), nothing about the state of either side.

**The answer decides which questions may follow: only ones about the chosen entry point.** The other side is
set up without a question, as the table in `ai-brain/profile/STACK.md` § Entry points says (for each choice,
what may be asked about and what is done instead for the rest), and `notes.md` records what was done to it.

Either entry point may ask which personas play the criteria.

#### Frontends served from a local feed

When the host page loads its frontends (pilets) from a feed URL and the diff touches one, this run builds and
serves every frontend the page needs from one local feed; a backend-only change keeps the default feed. The build
command, the port and the variable that points the host at the feed are in `ai-brain/profile/STACK.md`
§ Frontend feed. In outline:

1. Build each frontend from its own checkout with a production build, every `.env` key blanked so nothing local
   is baked in. The `before` build comes from the untouched branch (Step 2), the `after` build from the branch.
2. Serve them, with each name and version from the frontend's `package.json`:
   `python3 -I ai-brain/.claude/skills/dev/pilet_feed.py <port> <name>@<version>=<dir> ...`.
3. Start the host with its feed variable pointing at `http://localhost:<port>/feed`, then confirm in the browser
   that each bundle came from that port.

Never a debug bundle (`pilet debug`): a debug build takes its GraphQL URL from its environment or `.env`, never
from the endpoint the host hands it (`ai-brain/profile/STACK.md` § Frontend feed names where).

### Preflight

- The chosen server answers. One that is down: ask whether to start it, with the command. The other side
  follows the profile's table. Never start one over the engineer's own session.
- **The page serves this branch.** For a frontend change, list the bundles the page loaded
  (`performance.getEntriesByType('resource')`) and confirm the frontend came from this checkout's server.
  `piral debug` moves to a random port without failing when its port is taken: read its log for
  `Running at` before trusting a port. For an engine change, a request must show the new behaviour; whether the
  local environment reloads engine code on its own is in `ai-brain/profile/STACK.md` § Preflight. When it does
  not, restart a server this run started. One the engineer runs is restarted on a yes when its entry point is
  the chosen one; otherwise the check is reported as not run, with the restart command.
- **Signed in.** Run the sign-in check in `ai-brain/profile/STACK.md` § Preflight against the base URL. Exit 0
  is signed in, 3 is not, 4 is unreachable. On 3, open a headed window with `--headed --save-state` and a steps
  file that opens `/` and waits until the URL leaves the sign-in pages (§ Preflight holds it): nothing here
  types a password.

### Data: test clients only

Everything shown runs on a test client: the one `ai-brain/profile/STACK.md` § Test data names, unless the user
names another. Its id can differ per database, so look it up each run, read-only, with the query there.

Never shoot a real client's people, and check every frame for one before it leaves the machine.

- **Personas**, one per criterion, from `ai-brain/profile/DEFINITIONS.md`: a real user on the test client who
  holds that persona. How a persona maps to roles and users, and how to impersonate one, are in
  `ai-brain/profile/STACK.md` § Test data. Read each table with `\d` before joining it, and stop impersonating
  at the end of every run.
- **State** comes from doing what the user does: create, submit, request a change, approve. Existing data on the
  test client is fine. A state that needs a real wait (a minimum gap the app enforces between two actions;
  § Test data names any) is waited for, with the time noted, and the wait is cut from the video. A state no
  click path can reach is shown by the tests instead, and the PR says which.
- **Each run makes its own records.** The after run repeats the steps from the start. It never re-shoots
  the before run's records, which the old code saved. `notes.md` lists what each run created.

### Scenarios

- **One per acceptance criterion** the browser can show, `AC1`, `AC2`… in the plan's order, played as the
  persona it names. Each asserts what the screen shows (`expectText`, `expectVisible`) after each action,
  and opens with a caption naming the criterion and the persona.
- **Then the hunt: what users will actually do.** At least these, where the screen has them:
  - Do it twice, fast: a double click on the action.
  - Refresh in the middle; press Back after it; act in two tabs at once.
  - The wrong persona opens the page's URL directly.
  - The empty, zero and first-time states: no record yet, an empty list, a brand-new user.
  - The boundaries the plan names: exactly on the limit, just past it.
  - The network drops while saving (`context.setOffline(true)`, then back on).
  - An evening action in a US timezone, which crosses midnight UTC.
  - A narrow phone-width window, for screens people use on phones.

  The product's own hunt cases are in `ai-brain/profile/LESSONS.md`. Each hunt scenario is reported **clean**
  or **broken**. Broken is a defect: back to Step 3 with a regression test in the repo that owns it, then
  re-drive it here. One outside the ticket goes in the plan's Deferred or Open questions with its screenshot,
  not into this diff.

### Recording

- Steps files and runs live in the gitignored run folder `ai-brain/profile/STACK.md` § Recording names. Write
  them as `/qa-demo` does: the driver's scenarios with `ai-brain/.claude/skills/qa-demo/cursor.mjs` for a
  visible cursor and captions (`installCursor` before the first navigation; `caption`, `click`, `fill`,
  `pick`, `hold`).
- **Rehearse** without video until every step passes, at most three rounds. A failure that is the product
  (the right control, the right data, the wrong result) is a finding, not a script fix.
- **Record** with the driver's video flag; the command is in § Recording. Record at 1440x900: a driver that sets
  `recordVideo` without a `size` lets Playwright scale the video to 800x500, too small to read a table, and
  § Recording says where the 1440x900 copy lives and how to make it.
- **Media**: `bash ai-brain/.claude/skills/qa-demo/media.sh <run>/media <run>/<KEY>-<before|after>`
  gives the mp4 and the GIF. It keeps frames that hold only the cursor, so trim waits and stop-impersonation
  fades with ffmpeg `trim` and `concat` first. Keep each GIF under about 30 seconds and 10 MB.
- **Screenshots**: one before and after pair per screen an owned criterion names, the same frame in both,
  named `<KEY>-<AC>-<before|after>-<slug>.png`.
- **Show the user** the GIF (`SendUserFile`, `display: render`), the key screenshots, and pass or fail per
  criterion and per hunt scenario from `log.json`, before anything is committed.

## Step 6 — the evidence folder

The ticket's evidence folder in the e2e repo (its path: `ai-brain/profile/E2E.md` § Evidence), on the ticket
branch in that repo, cut from its base. A dirty checkout, or one on another ticket's branch: ask. It holds the
screenshot pairs, the GIFs and mp4s, and `notes.md`:

| Section | What it says |
| --- | --- |
| Stack | The entry point and its URL, each repo's branch and short SHA, where each frontend bundle came from, and what the run did to the other side without asking |
| Data | The database and when it was restored, the test client by name and id, what each run created |
| Personas | Per criterion: the persona, the user id, how it was impersonated |
| Frames | Each file, what it shows, and which criterion or hunt scenario it belongs to |
| Hunt | Every scenario tried, clean or broken, with its frame |
| Not shown | Each criterion no click path reaches, and the test that covers it instead |

## Step 7 — self-review

Read each repo's whole diff against the plan's parity rows: every `gap` row and every owned criterion is
closed, nothing outside the plan rode along, and the comments fit the budget. Then read it once for KISS:
each new branch, option, parameter, wrapper, helper and file is needed by a parity row or a criterion, and
each line uses the plainest construct that works; anything else comes out. Search once more, by what
it does, for each function, component, hook and spec helper the diff adds (`ai-brain find` first): one the
repo already had sends that code back to Step 3. Then run
`ai-brain/bin/ai-brain impact --diff <every repo the diff touched>`: a consumer of a changed interface
that sits outside every diff is either the paired PR's job, named in the PR body, or a finding. A plan with Design rows:
compare each "after" screenshot with its Figma node (`get_screenshot`) by
`ai-brain/docs/DESIGN_PARITY.md`, and put each gap to the user as a defect to fix or a deviation to
record. Load the repo's own prose skill for the PR text, when it has one (`ai-brain/profile/REPOS.md` names it).

## Step 8 — confirm, then ship

One `AskUserQuestion`: per repo the branch, the commit subject, the file count, the base, and whether a PR
opens; the evidence branch. A no stops here; the Final report
still writes the Dev report.

1. **Commits**, one per repo, conventional prefix, imperative subject: the engine first, then the frontend,
   then the e2e evidence.
2. **Push the evidence branch first**, so the images resolve, then the code branches. A rejected push is
   reported, never forced.
3. **PRs**: `gh pr create -R <org>/<repo> --base <base> --head <branch> --title "<KEY> | <Title>"`, the org
   from `ai-brain/profile/REPOS.md` (add `--draft` on `--draft`; skip on `--no-pr`). Fill the repo's
   `pull_request_template.md`. The body:
   - `# Demo` first. A table per criterion with its before and after images, each the file's raw URL in the
     e2e repo on its branch (the pattern is in `ai-brain/profile/E2E.md` § Evidence), the GIF inline the same
     way, and the mp4 as a link. GitHub plays a video inline only when it is dragged into the description in
     the browser: say so to the user.
   - What changed and why, and the ticket and its parent. No plan link: the plan stays local in
     `ai-brain/sprints/`, which is gitignored.
   - The paired PR, and that the two merge together.
   - The Reuse inventory's verdicts with their `path:line`. Each extend and extract names the other
     feature whose files it changed.
   - The action items with their final status, the real gate results with their scopes, the hunt with
     each scenario's result, any parity deviation with its reason, and what is left open.
4. **The plan**: append the PRs (repo, number, URL, base, draft or not) to the Log, mark the PR items done,
   and write the Dev report (below), in place: `sprints/` is gitignored, so the plan is not committed or
   pushed.
5. **Jira** only on a separate yes: one comment on the ticket linking the PRs, written by
   `ai-brain/docs/JIRA_COMMENTS.md`: the link, where the demo is, and the order of release, with no plan
   link. No transition, no field edit.

## Dev report

Every run writes it, shipped or not: one section in the plan between Deferred and Log, replaced on each run,
so anyone who opens the plan understands what was built without reading the diff. The brain reads its
Summary and Files changed (`ai-brain/docs/SPRINTS.md`).

```
## Dev report

_Updated by /dev on YYYY-MM-DD, from <branch> at <short SHA> per repo._

### Summary

Three to six plain sentences, for someone who has not read the plan: what the ticket needed, what was built,
how it behaves now, and what is left. No paths.

### What was built

| Item | What it does now | Where | Verified by |
|---|---|---|---|

### Files changed

| File | Change | Item |
|---|---|---|

### Against the plan

Files to touch that were not touched, files touched that the plan did not name, and why.

### PRs

### Left open
```

- **What was built**: one row per action item this run worked, done or not, with the gate or the frame that
  proves it.
- **Files changed**: every file in each repo's diff against its base
  (`git -C <repo> diff --name-status origin/<base>...HEAD`), the full path from the workspace root, the change
  (`add`, `edit`, `delete`, `test`) and the item. Nothing summarised: this table is what `ai-brain history`
  answers with.
- **PRs**: repo, number, URL, base, draft or not, or "not opened" with the reason.
- **Left open**: each open gap and item, with who decides.

## Final report

First, whatever Step 8's answer was, the Dev report. Write it into the plan; there is nothing to commit, since
`sprints/` is gitignored. Then update the brain: `ai-brain/bin/ai-brain index --pull --background`. It fetches
every connected repo, fast-forwards each clean checkout that sits on its base branch, re-indexes, and logs which
checkouts it skipped (`ai-brain/ai-brain/var/log/index.log`). The plan reaches the brain at once, read
from disk; the code reaches it when the PRs merge.

One table per part: the branches and PRs per repo; each criterion with its result and frame; each hunt
scenario, clean or broken; each extend and extract, with the other feature it changed; the gates with
their scopes; what is still open. End with the PRs to review and the commands that review them:
`/branch-review <KEY>` and `/pr-review`, both the user's to run.

## Rules

- No plan, no build. The plan's action items and parity rows are the scope, and its ledger stays current.
- Reuse before you write. What another feature already does is reused, extended or extracted, never
  copied. "Write new" records what was searched.
- Keep it simple (KISS). The smallest change, in the plainest code that passes the parity row's test: no
  layer, option or abstraction that one caller does not need (`ai-brain/docs/PRACTICES.md`, "KISS
  and DRY").
- Brain lines are leads: open the `path:line` before a lead becomes a verdict (`ai-brain/docs/AI_BRAIN.md`).
- The plan in `ai-brain/sprints/` is the source of truth: the build starts from its Files to touch and
  Services involved, and every plan edit goes through `plan-doc`.
- Every run ends with a Dev report in the plan, then `ai-brain/bin/ai-brain index --pull --background`,
  shipped or not.
- Before shots come first, from the untouched branch.
- Real accounts, real clicks, a test client. No seeders, no debug mutations, no hand-written requests or
  database writes. Never a shared development, staging or production environment.
- Ask which entry point to drive (`ai-brain/profile/STACK.md` § Entry points) every time the check is reached,
  in a question of its own. After it, ask only about the chosen one; the other side follows the profile's table.
- A defect the hunt finds is fixed with a regression test and re-driven, or written into the plan.
- Never stash, never use a worktree, never switch a dirty checkout or one parked on another ticket.
- No commit, push, PR or Jira write without a yes. Never merge, never force-push, never `--no-verify`.
- Never report a check as passing unless it ran and passed.
- No AI attribution anywhere.
