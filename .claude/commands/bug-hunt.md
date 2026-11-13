---
description: Bug-hunt the feature currently in the working trees with Playwright — serial browser hunters over the surfaces the diff reaches, the developer fixes what they find, a hunter re-drives every fix, and the ticket's evidence folder in the e2e repo (ai-brain/profile/E2E.md § Evidence) is written whether or not anything broke
argument-hint: "[PROJ-123] [--scope <text>] [--families <a,b>] [--rounds N] [--fix-minor] [--no-fix] [--more-context <text|@path|url>] [--no-report] [--dry-run]"
allowed-tools: Bash(git status:*), Bash(git fetch:*), Bash(git switch:*), Bash(git checkout:*), Bash(git add:*), Bash(git commit:*), Bash(git push:*), Bash(git log:*), Bash(git diff:*), Bash(git rev-parse:*), Bash(git symbolic-ref:*), Bash(git show-ref:*), Bash(git ls-remote:*), Bash(git branch:*), Bash(git status), Bash(gh pr:*), Bash(gh repo:*), Bash(gh auth:*), Bash(curl:*), Bash(date:*), Bash(ls:*), Bash(cp:*), Bash(mkdir:*), Read, Write, Edit, Grep, Glob, Workflow, Skill, AskUserQuestion
---

Hunt bugs in the feature that is already implemented in these trees, fix what the hunt finds, and leave
the evidence behind.

Ticket and flags: $ARGUMENTS

Run this from the workspace root, never from inside a single repo. The feature under test usually spans a
backend service and a frontend, and the hunt has to read both.

The workspace's facts — repos, ports, flags, the e2e suite, the tracker — live in `ai-brain/profile/`:
`REPOS.md`, `STACK.md`, `E2E.md` and `TRACKER.md`. This command names the section each step reads.

## What this is, and how it differs from `/dev`

`/dev` builds a ticket against its plan and checks it by hand in a real browser, on real data.
**This command starts after that.** The feature exists, its own specs are
green, and the question is no longer "does it meet the criteria" but "what breaks when someone uses it".

Three things make it its own command:

- **It hunts with seeded, repeatable runs, and it fixes in a loop.** Here the loop hunts, patches, gates and then
  **re-drives every patch in the browser**. A fix nobody re-drove is a claim, and this command does not
  report claims as fixes.
- **The browser runs alone.** The suite's Playwright config runs one worker, not fully parallel, over one
  shared backend database whose seeds clear and recreate, and one frontend dev server
  (`ai-brain/profile/E2E.md` § Suite). Hunters therefore run **one at a time** — serially, by design, not
  for lack of ambition. Two agents driving browsers at once seed over each other and report each other's
  wreckage as defects. Never raise `--workers`, and never parallelise the hunt.
- **The evidence folder is the deliverable.** The ticket's evidence folder in the e2e repo
  (`E2E.md` § Evidence) is written on **every** run — a hunt that found nothing still has to show which
  states it drove, or it cannot be told apart from a hunt that stopped early. A run that ends with no
  folder has failed, whatever it says about the code.

## What it needs from the user

**Nothing, on a good day.** Point it at a workspace where a feature has just been built and it resolves
the rest. Everything below is optional.

| Give it | When | Why it matters |
| --- | --- | --- |
| `PROJ-123` | the branch does not carry the key, or several repos disagree | It names the evidence folder. Resolved from the branch names otherwise; `NEW-<slug>` is accepted for a feature with no ticket |
| `--scope "<text>"` | the diff is wider than what you want hunted | Narrows the surfaces. "Only the submit button's gate" spends the browser budget there instead of across a whole page |
| `--more-context "<text>"` (or `@path`, or a URL) | intent is in neither the ticket nor the code | Read by the scope pass, every hunter, the developer and the verify pass. A deliberate behaviour nobody wrote down is otherwise reported as a defect |
| `--families a,b` | you know where the risk is | Runs only those scenario families. Each family is one browser pass, so this is the flag that trades coverage for time |
| `--no-fix` | you want the report before any edit | Hunts and reports, patches nothing. The evidence folder is still written |
| `--fix-minor` | copy and cosmetics count this time | Without it, `MINOR`/`NIT` findings are recorded and not patched, so the loop cannot spend its rounds on nits |

## Flags

Parse these off `$ARGUMENTS`; what remains is the ticket key, if one was given.

- `--scope <text>` — narrow the hunt in your own words. Passed as `scope`.
- `--families <a,b,c>` — subset of the scenario families the scope pass planned. Names come from that
  plan: `zero-one-many`, `absent-value`, `failure-isolation`, `identity-and-scope`, `order-and-timing`,
  `boundaries`. A name the scope pass did not plan is reported and ignored, not invented.
- `--rounds N` — maximum rounds. Default 3. Each round is browser time. What a round *is* depends on
  `--no-fix`:
  - **fixing (default)** — hunt, fix, gate, verify. Raise it when a run converged on a red gate rather
    than on a clean verify.
  - **`--no-fix`** — there is no fix stage, so rounds buy **depth**: the hunters go again with everything
    already found in their prompt as "do not re-report these, hunt past them", and the loop stops when a
    round turns up nothing new (dry) or the budget runs out. A run that spends its last round still
    finding defects says so — there is more there.
- `--fix-minor` — patch `MINOR` as well as `BLOCKER` and `MAJOR`. `NIT` is never patched by the loop.
- `--no-fix` — hunt and report only. Passed as `noFix`.
- `--more-context <text|@path|url>` — repeatable, mixed forms fine. Passed as `moreContext`.
- `--no-report` — do not write the hunt report or bug files in `ai-brain/sprints/<sprint>/`. The
  e2e evidence folder is still written; that one has no off switch.
- `--dry-run` — run the hunt and the fixes, report, and stop before any commit or push. The patches stay
  in the trees so you can read the diff.

## Roles

The loop reuses this project's agents, from `ai-brain/.claude/agents/`:

| Agent | Writes | Job here |
| --- | --- | --- |
| `general-purpose` | no | The scope pass: reads the diff and says which routes, personas and operations a browser can reach. Also the gate, and the on-disk evidence check |
| `qa-e2e` | e2e repo only | The hunters, the verify pass, and the evidence write-up. **Still never fixes** — a defect is a finding with a `file:line` and a scenario |
| `developer` | code repos | Patches the confirmed findings. One writer per repo, repos handled one at a time |

If the workflow stops with `agent type 'qa-e2e' not found`, the registry has not picked up the files:
run `ai-brain/bin/install.sh` and start a new session.

---

## Step 1 — preflight

1. **Today's date**, once, for every artefact this run writes:

   ```
   date +%Y-%m-%d
   ```

   The workflow cannot read the clock — `Date.now()` and `new Date()` throw in a workflow script because
   they would break resume — so this value is passed in as `today`. Everything dated in the evidence
   folder and the report uses it.

2. **What is in the trees, and on which branch.** This is the feature under test, so read it before
   deciding anything. The repos are the ones `ai-brain/profile/REPOS.md` lists, plus the e2e repo and
   `ai-brain`:

   ```
   for d in <the repos in ai-brain/profile/REPOS.md> <the e2e repo> ai-brain; do
     printf '%-34s %-30s %s\n' "$d" \
       "$(git -C "$d" rev-parse --abbrev-ref HEAD)" \
       "$(git -C "$d" status --porcelain | wc -l) changed"
   done
   ```

   **A dirty tree is not a blocker here — it is the subject.** Uncommitted work
   is the normal input to this command. What does block:
   - **Nothing to hunt.** Every repo clean and on its base branch means there is no feature in these
     trees. Stop and say so rather than hunting `main`.
   - **A dirty e2e repo that is not this hunt's own work.** The hunters write specs, probes and
     artefacts there. Show what is uncommitted and ask before writing over it.

3. **Resolve the ticket key.** In order: the argument, then the branch names (`you/proj-123-v1` →
   `PROJ-123`; the key's prefix is in `ai-brain/profile/TRACKER.md` § Site and board), then ask. If two
   repos carry different keys, stop and ask — the evidence folder can only be named once, and guessing
   files a hunt under the wrong ticket.

4. **The stack must be up**, because every hunter needs it. `ai-brain/profile/STACK.md` § Entry points and
   `E2E.md` § Suite name what the suite needs: the service, its port, its health check, the flag it must
   run with, and the command that starts it.

   ```
   curl -s -o /dev/null -w '%{http_code}\n' <the health URL E2E.md § Suite names>
   <the start command it names>   # if it does not answer 200
   ```

   The flag `E2E.md` § Suite names is not optional: the suite's setup preflight fails fast without it, and
   the seeds it needs are gated on it. Playwright boots its own frontend dev server and reuses it if it is
   already up; the dev server `E2E.md` § Suite says is never reused stays untouched. Bring the backend up
   yourself — a hunt that cannot reach the app returns nothing, and an unrunnable stack reported as a
   clean run is the worst outcome this command has.

5. `git -C <repo> fetch origin` for the repos with changes, and read each real base branch with
   `git -C <repo> symbolic-ref --short refs/remotes/origin/HEAD`. `ai-brain/profile/REPOS.md` § Base
   branches names the traps — a repo whose `origin/HEAD` is not where the sprint's work went. Say which
   base you chose.

6. `gh auth status` — note the account. Only needed if the run ends in a push.

7. Find the plan doc if there is one — `ai-brain/bin/ai-brain ticket <KEY>` (its `plan` line, and its
   files to touch and open gaps, which tell the hunters where to look), or `ai-brain/bin/plan-doc path
   <KEY>`; an older one may sit in the plans archive (`PLAN_DOC_ARCHIVE`, `REPOS.md` § Reference docs).
   The hunt does not need it, but the evidence notes link it, and a hunter that knows the intended
   behaviour files better findings. The plan's sprint is where the write-up goes (Step 4); with no plan,
   the current sprint from the tracker (`TRACKER.md` § Current sprint).

## Step 2 — run the hunt

```
Workflow({
  name: "bug-hunt",
  args: {
    ticket: "PROJ-123",
    today: "<YYYY-MM-DD from Step 1>",
    e2eRepo: "<the e2e repo, from ai-brain/profile/E2E.md § Suite>",
    repos: ["<every repo from Step 1.2>"],
    evidenceDir: "<the ticket's evidence folder, from E2E.md § Evidence>",
    scope: "<--scope text, if given>",
    families: ["zero-one-many", "..."],
    maxRounds: <N>,
    fixMinor: <bool>,
    noFix: <bool>,
    moreContext: ["<a note about intent>", "<path or url to read>"],
    notes: "<what preflight found: branches, bases, what had to be started>"
  }
})
```

It runs in the background and returns `{ ticket, today, converged, aborted, rounds, fixPolicy, scope,
families, scenariosDriven, scenariosClean, scenariosBlocked, findings, fixed, open, notFixedReasons,
evidence, evidenceCheck, evidenceDir, history }`.

While it runs, do nothing else — it is driving a browser and a database you would collide with.

When it returns:

- **`aborted` set** — report it verbatim. An abort here is one of two things: the stack could not be
  driven (nothing was verified — do not read a clean result into it), or defects were found and none
  could be patched (read `notFixedReasons`; that is a decision for a human). Still do Step 3.
- **`converged` false** — the loop ran out of rounds with findings still open. Report them, and say
  whether the blocker was a red gate or a verify that kept failing. Still do Step 3.
- **`converged` true with `findings` empty** — the hunt held. That is a result, and the scenario list in
  the evidence folder is what makes it one. Say how many scenarios were driven and how many were
  `blocked` — a converged run that could only drive two scenarios is a thin result and should read as one.
- **`open` non-empty** — those are the defects nobody fixed. They go in the report and, if they outlive
  this run, in `ai-brain/sprints/<sprint>/bugs/`.

## Step 3 — the evidence folder is the invariant

`evidenceDir` is the ticket's evidence folder in the e2e repo (`E2E.md` § Evidence), and it must exist
with `notes.md` and `bug-hunt.md` in it. Read `evidenceCheck`, which checked the disk rather than taking
the writer's word:

```
ls -la <evidenceDir>
```

- **Folder or a file missing** — say so plainly and write the missing piece yourself from the workflow's
  return value: the scenario list, the findings, what was fixed, what is open, what could not be reached.
  Do not report the run as recorded when it is not.
- **Screenshots missing** — the hunters capture into `test-results/`, which Playwright clears on the next
  run. If `evidence.missing` names images, copy what still exists and list what is gone. A `notes.md`
  whose screenshot table points at files that are not there is worse than a table with fewer rows.
- **Never rename a screenshot to look like something it does not show.**

The folder is the point of the run, so this step happens on every exit path — converged, unconverged or
aborted.

## Step 4 — the write-up, beside the plan in `ai-brain/sprints/<sprint>/`

Skip on `--no-report`. The write-up sits with the ticket's plan, so `ai-brain ticket <KEY>` lists it and the next
session finds it there (`ai-brain/docs/SPRINTS.md`). Get each file to write with
`ai-brain/bin/plan-doc edit <sprints/… path>`; it makes the sprint's `reports/` or `bugs/` folder the
first time.

1. **The hunt report** — `sprints/<sprint>/reports/<DD>-<slug>-bug-hunt.md`, with front-matter `title`, `date`,
   `kind: bug-hunt`, `ticket: <KEY>` and `verdict`. Mirror the report model `E2E.md` § Evidence names: a
   verdict paragraph, an "In plain words" section a non-engineer can read, the scope and environment table
   with repos, branches and SHAs, then the findings. The report is the evidence; it is point-in-time and it
   is never edited later to match what the code became.
2. **A bug file per finding still open** — `sprints/<sprint>/bugs/<kebab-slug>.md` with front-matter
   `ticket: <KEY>`, `status: open`, `reported: <today>`, a severity and the repos, linking back to the report.
   That folder is a live list: every file in it is believed broken right now. A finding this run **fixed**
   does not get a bug file — the report already records it, and `bugs/` is not an archive.
3. **The plan doc** — if the feature has one, append to its Log: the hunt date, what was found, what was
   fixed, what is open. Append; never rewrite an earlier entry.

The write-up is not committed or pushed: `sprints/` is gitignored, so it stays on this machine, like every plan.

## Step 5 — branches and commits

**Every repo the fixes touched gets a branch, and a shared branch is never a push target** — not `main`,
`staging`, `development` or `develop`, in any repo here, including the e2e repo. The write-up needs no
branch: `ai-brain/sprints/` is gitignored and never committed. The branch and commit rules of this
workspace are in `ai-brain/profile/REPOS.md` § Branches and commits.

- A repo **already on this ticket's branch** keeps it: these fixes belong with the feature they fix, in
  the same PR a reviewer is already reading.
- A repo on its **base branch** that the hunt patched gets `{name}/{key}-bughunt-v1`, checked against
  local and remote first:

  ```
  git -C <repo> show-ref --verify --quiet refs/heads/you/proj-123-bughunt-v1
  git -C <repo> ls-remote --exit-code --heads origin you/proj-123-bughunt-v1
  ```

  A remote-only branch is the trap: without the second check the push either fast-forwards into someone
  else's branch or is rejected after the commits exist.

One commit per repo, conventional prefix, imperative subject ≤50 characters:

```
fix(PROJ-123): render the empty list instead of a blank table
```

The body names the finding it closes, the scenario that found it, and the paired repo when there is one.
Order: the owning service first, then the frontend (with any regenerated dumped schema and generated types,
`ai-brain/profile/CODE_MAP.md` § Contract files), then the e2e repo (the specs, the probes and the evidence
folder).

**Attribution follows `REPOS.md` § Branches and commits** — what a commit may and may not carry about who
wrote it, in every repo here.

Let each repo's pre-push hook run (`REPOS.md` § Gates names them). If one fails, the loop's gate missed
something — report and stop rather than pushing with `--no-verify`.

## Step 6 — push, only after a confirmation

**Stop here on `--dry-run`.** Otherwise use `AskUserQuestion` to show, per repo: the branch, the commit
subject, the file count, the base, and whether a PR exists on that branch already. Get a yes.

```
git -C <repo> push -u origin <branch>
```

- **A PR already open on the branch** — the push updates it. Do not open a second one. Comment on it
  instead when the fixes need explaining, and say in the comment which findings they close.
- **No PR and the repo is a code repo** — report the compare URL. Open a PR only if the user asks; these
  are fixes to a feature whose PR strategy the user already chose.
- The e2e repo pushes its branch and follows its own PR rule in `REPOS.md` § Branches and commits (by
  default, no PR). Report its compare URL.
- A rejected push (`non-fast-forward`) is a report, not a problem to overwrite. No force-push, no rebase
  without asking. **Nothing merges here** — no `gh pr merge`, whatever the verify pass said.

## Step 7 — the tracker

Ask first. If yes: a comment on the ticket saying what was hunted, what was found, what was fixed and what
is still open, linking the report and the evidence folder, in the format `ai-brain/profile/TRACKER.md`
§ Writing to the tracker gives and the style of `ai-brain/docs/JIRA_COMMENTS.md`. Do not transition the
ticket, and do not edit its description — if a description must change, it follows the description format
in `TRACKER.md` § Writing to the tracker.

---

## Final report

- **Ticket and date** — key, and the `today` every artefact is stamped with.
- **What was under test** — repo, branch and one line on what changed, per repo.
- **Coverage** — families run, scenarios driven, how many came back clean, how many were `blocked` and
  why. A number of scenarios means nothing without the blocked count next to it.
- **Findings** — one line each: severity, `repo/file:line`, what was observed, and `fixed` /
  `still open` / `not patched (reason)`.
- **Fixes** — what changed per repo, the regression tests added, and **how each one was re-driven in the
  browser**. A fix with no verify line is reported as unverified.
- **Gate** — the real results with their scopes. `not run` stays `not run`.
- **Could not reach** — what the diff changed that no browser could show, from `scope.unreachable`. This
  is the honest limit of the run and it belongs in the report, not in a footnote.
- **Evidence** — the folder path, its files, and anything missing from it.
- **Write-ups** — the report path, any bug files, the plan-doc entry.
- **Branches and PRs** — per repo, and which existing PR the fixes landed on.
- **Next** — what a human still has to decide: the open findings, the product questions, the seeders that
  do not exist yet.

## Rules

- **One browser at a time.** Hunters are serial because the suite shares one database and one frontend
  dev server. Never raise `--workers`, never run two hunters at once, never run the gate's suites during a
  browser pass.
- **The hunters do not fix, and the developer does not hunt.** The lane that found a defect is the lane
  that re-drives it; the repo that owns the defect is where it is fixed.
- **No fix is fixed on a claim.** A patch is verified in the browser, on the scenario that found it, or
  it is reported as unverified.
- **Fix the cause.** A guard that hides the symptom on the one surface a hunter happened to use is not a
  fix, and the verify pass is told to look for exactly that.
- **A regression test lands in the owning repo**, not only in Playwright: RSpec for a backend fix, Jest
  for a frontend fix. A browser-only proof leaves nothing behind for CI.
- **The evidence folder is written on every run**, findings or not, converged or not. A run with no folder
  has failed.
- **Log the clean scenarios.** "I drove these fourteen states and the feature held" is the result; a
  findings-only report cannot be told from a hunt that stopped early.
- **A stack that will not start is `NOT_RUN`, never a clean run and never a defect in the code.** Bring
  it up first; report the obstacle and the command that clears it if you cannot.
- **Restart the suite's frontend dev server before trusting a cluster of failures.** It degrades after
  repeated seeding and route interception, and a wall of `ERR_CONNECTION_REFUSED` is a dead server, not a
  wall of defects.
- **Probes and specs are kept, not deleted.** A probe that pins real behaviour is promoted into the suite's
  role folder with the ticket tag; the rest stay in the probe folder, which logs rather than asserts
  (`E2E.md` § Suite).
- **Scope discipline.** The loop patches findings. A defect noticed outside them is reported, not
  quietly fixed — nothing hunted it and nothing will verify it.
- **No shared branch is ever a push target**, and the push waits for a confirmation every time. Approval
  for one hunt is not approval for the next.
- **Never merge**, and never run `/pr-review` from here. That stays the user's, after they read the diff.
- **Attribution** in commits and PRs follows `REPOS.md` § Branches and commits, everywhere in this workspace.
