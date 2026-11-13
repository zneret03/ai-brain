---
description: Review a ticket's branches, or one PR, before it merges. Asks the ai-brain first and stops with an error when it cannot answer (no grep fallback), reads the acceptance criteria of the whole Jira ticket family and the plan in ai-brain/sprints, diffs every branch the ticket has in every code repo without switching a checkout, finds what the change reaches outside the diff, runs the repo's own checks (scoped rubocop, eslint, type-check, react-doctor), and reviews the Rails half and the React half in parallel against each repo's CLAUDE.md, rules and ai-brain/docs/PRACTICES.md. The workspace's own facts come from ai-brain/profile/. Returns findings grouped by reason, each with its file and line, the change to make and sample syntax. A breaking change or an unmet acceptance criterion makes the verdict Request changes; KISS, DRY and best-approach findings are Suggestions that never block. Writes the round to ai-brain/sprints/<sprint>/reviews/<KEY>.md, where the brain reads it, and posts to GitHub only on a yes.
argument-hint: "<PROJ-123 | jira-link | PR url | <repo>#<n>> [--repo <name>] [--no-post]"
disable-model-invocation: true
effort: max
allowed-tools: Read, Grep, Glob, Agent, AskUserQuestion, Bash(ai-brain/bin/ai-brain:*), Bash(ai-brain/bin/plan-doc path:*), Bash(ai-brain/bin/plan-doc show:*), Bash(ai-brain/bin/plan-doc edit:*), Bash(git -C:*), Bash(gh pr view:*), Bash(gh pr list:*), Bash(gh pr diff:*), Bash(gh pr checks:*), Bash(ls:*), Bash(grep:*), Bash(date:*), mcp__claude_ai_Atlassian__getAccessibleAtlassianResources, mcp__claude_ai_Atlassian__getJiraIssue, mcp__claude_ai_Atlassian__searchJiraIssuesUsingJql
---

Review one ticket's work the way the team should: from what the ai-brain knows about every file it touches,
against what the ticket asked for and the rules each repo wrote down, and say plainly what must change before merge
and what would only make it simpler.

Ticket or PR, and flags: $ARGUMENTS

Run from the workspace root. Every path below is relative to it. `<scratch>` is this session's scratchpad. The
workspace's own facts (its repos and GitHub owner, code layout, review standards and tracker) live in
`ai-brain/profile/`, and each step names the file and section it reads.

## What this does and does not do

- **Reads every code repo, writes none.** No edit, `git add`, commit, push, switch, stash or worktree in any code
  repo (the monorepo, a frontend, the shell or the e2e suite): the checkout may hold someone else's work. It writes
  only the review record (Step 9, through `plan-doc`), files under `<scratch>/branch-review/<KEY>/`, and, after a
  yes, the GitHub review (Step 10).
- **The brain first, and the brain always.** Every code fact comes from `ai-brain/bin/ai-brain` before any
  Grep, Glob or Read, and every lead is opened at its `path:line` before it becomes a finding. When the brain does
  not answer, the review stops with an error (Step 1). This departs from the workspace rule, where `not run` means
  "grep instead": a review that cannot see what the change reaches is not a review.
- **Acceptance criteria from the whole family**, the parent and every subtask, as `/plan` reads them.
- **Two severities.** **Request changes** for what breaks: a breaking change, an unmet acceptance criterion, a bug,
  a security or data defect. **Suggestion** for what works but could be simpler or better: KISS, DRY, the best
  approach for a line, a repo convention. A Suggestion never blocks.
- **Never approves, never merges, never posts without a yes.** No AI attribution in the record or on GitHub.
- **Runs at maximum effort.** The frontmatter sets `effort: max`, and both lane agents start with `effort: "max"`.

`allowed-tools` leaves out `gh api` (posting), the lint and test runners, and every Jira write, so each asks first.

| Give it | Effect |
| --- | --- |
| `PROJ-123` or its Jira link | Every branch the ticket has, in every repo. The key is `[A-Z][A-Z0-9]+-[0-9]+` |
| A PR URL, or `<repo>#<n>` | That PR only; the key comes from its title, else its branch name |
| `--repo <name>` | With a key: only that repo's branch |
| `--no-post` | Print and record; never offer to post |

## Step 1 — the brain, or nothing

```
ai-brain/bin/ai-brain fresh
```

`fresh` starts Neo4j when it is down. When it, or **any later brain call in any step or lane**, exits 3 or 4 or
prints a line starting `ai-brain: not run`, stop the whole review and print only:

> branch-review stopped: the ai-brain did not answer: `<that line>`. Start it with `ai-brain/bin/ai-brain-up`,
> then run `/branch-review` again.

No grep fallback, no partial review, no record, no post. A verb that answers `none` is an answer, not a failure.

Then the ticket's brief, and keep its header line for the record:

```
ai-brain/bin/ai-brain ticket <KEY> --all
```

It gives the plan, the files to touch, the open gaps, every branch for the key in every repo with who holds it, the
PRs, the earlier `review` rounds and the related tickets.

## Step 2 — the targets

The repos to review, their layout and their GitHub owner are in `ai-brain/profile/REPOS.md` § Review targets.
Below, `<owner>/<repo>` is that owner and repo.

Per repo with a branch for the key (the `branch` lines; the highest `-v<n>` per repo; `--repo` narrows it), or the one
PR given:

1. **The PR**: `gh pr list -R <owner>/<repo> --head <branch> --state all --json number,url,title,author,baseRefName,headRefOid,isDraft,state`,
   or `gh pr view <n> -R <owner>/<repo> --json number,url,title,author,headRefName,headRefOid,baseRefName,isDraft,state`
   for a PR input.
2. **The base**: the PR's `baseRefName`; with no PR, `git -C <repo> symbolic-ref --short refs/remotes/origin/HEAD`.
   A base that is another ticket's branch makes this a stacked review; the diff is against that branch.
3. **The tip**: `git -C <repo> fetch origin <base> <branch>` (it moves only the remote refs), then `origin/<branch>`.
   With no PR and a local branch ahead of origin, the local branch, and the review says the work is unpushed.
4. **The diff**: `git -C <repo> merge-base origin/<base> <tip>` is the merge base; save
   `git -C <repo> diff <merge-base> <tip>` to `<scratch>/branch-review/<KEY>/<repo>.patch` and read it whole, once.
   Keep its `--stat` and `--name-status`.
5. **Uncommitted work** in a checkout that sits on this branch is listed under "Not reviewed", never read as part
   of the branch.
6. **What reviewers already said**: the PR's body (`gh pr view <n> -R <owner>/<repo> --json body`) and its review
   threads (`gh api repos/<owner>/<repo>/pulls/<n>/comments --paginate --jq '.[] | {user: .user.login, path,
   line, body}'`). A finding another reviewer already raised goes under "Already raised" with its link, not again
   as a finding.

No branch and no PR anywhere: stop, there is nothing to review.

**The lanes come from the file list**, never from the ticket's `(BE)` or `(FE)` prefix:

| Lane | Files |
| --- | --- |
| Rails | `*.rb`, `*.rake`, `*.erb`, `*.slim`, `*.jbuilder`, anything under `db/`, `Gemfile`, `Gemfile.lock`, `*.gemspec` |
| React | `*.ts`, `*.tsx`, `*.js`, `*.jsx`, `*.mjs` |
| Both read | `*.graphql`, and a frontend's GraphQL documents (where `ai-brain/profile/CODE_MAP.md` § File map puts them): the contract between the two |

A diff with no file in either lane (docs, config) gets the acceptance-criteria and plan checks only.

## Step 3 — the ticket, and what done means

Through the Atlassian tools (`getAccessibleAtlassianResources` gives the cloud id), build the acceptance-criteria
inventory exactly as `ai-brain/.claude/skills/plan/SKILL.md`, Step 1 does: the ticket, its parent and every
subtask (`parent = <PARENT> ORDER BY key`), from the description and the fields `ai-brain/profile/TRACKER.md`
§ Ticket family lists, one row per criterion as `<source key>/AC<n>`.

Then the plan: `ai-brain/bin/plan-doc show <KEY>`. Its AC table names each criterion's owner, its Files to
touch say what the build should change, and its **Decisions bind the review**: a shape the plan chose and recorded is
not a finding unless it breaks something.

- The criteria this ticket owns are judged in Step 7. The others are listed with their owner, not judged.
- **An end-to-end test is the developer's choice** (`ai-brain/profile/LESSONS.md`, "Learned on our tickets: the
  process"). A ticket line asking for one is not a criterion: list it as "not judged: the developer's choice", and
  never make a missing spec or run a finding. A spec the branch does add is reviewed like any other test.
- No plan: say so, and review against Jira alone.
- No criteria anywhere in the family: one blocking finding under Acceptance criteria, "the ticket family has no
  acceptance criteria". Never invent criteria.
- A PR with no ticket key: no criteria to judge; say so in the verdict.

## Step 4 — what the change reaches

Ask the brain about every file and every interface the diff touches. Keep each query, its words and its lead for the
record.

| Ask | For | Feeds |
| --- | --- | --- |
| `ai-brain impact --diff <repo>@<tip> [<repo>@<tip>...]` | every repo in the review, in one call. Stacked: `<repo>@origin/<base>...<tip>` | **Breaking change**: a consumer, outside every diff, of an interface the diff changed |
| `ai-brain impact <repo>/<path>` | each changed file | its consumers, and the specs that pin it (Step 5 runs them) |
| `ai-brain trace <Type.field>`, `ai-brain consumers <name>` | each GraphQL field, type or operation, route, Kafka topic, table or flag the diff adds, removes, renames, or changes the type, arguments or nullability of | **Contract** |
| `ai-brain find <words of what it does>` | each function, method, class, hook, component and spec helper the diff adds | **DRY**: the repo already has it |
| `ai-brain history <repo>/<path>` | each changed file | the tickets whose plans and Decisions bind it |
| `ai-brain notes <repo>/<path>` | each changed file | the notes, the practices (`ai-brain/docs/`) and the earlier reviews that cite it |
| `ai-brain related <KEY>` | the ticket | prior art |

- **Open every lead** at its `path:line` before it becomes a finding (`ai-brain/docs/AI_BRAIN.md`, "The trust
  rule"). A lead the file does not bear out is dropped, and the record counts the drops.
- **A consumer outside the diff breaks** when it still selects a removed or renamed field, sends an argument the
  diff removed or made required, reads a field as present that the diff made nullable, calls a method with its old
  signature, parses an event payload the diff reshaped, or reads a column a migration drops or renames. A consumer in
  the paired PR is the pair's job: check that the pair handles it, and name the PR.
- **An earlier review** (`review` lines from `notes`) that flagged the same shape on the same file is repeated with
  that review named: the lesson did not stick.
- **Plan parity**: the diff's files against the plan's Files to touch. A planned file not touched feeds the
  criteria check; a touched file not planned is a scope Suggestion unless it breaks something.

## Step 5 — checks, where the branch's files are

**Where.** The checkout, when `git -C <repo> rev-parse HEAD` is the tip and `git -C <repo> status --porcelain` prints
nothing. Otherwise an export, the house way to run code at another ref (workspace `CLAUDE.md`):
`mkdir -p <dir> && git -C <repo> archive <tip> | tar -x -C <dir>`, with `<dir>` =
`<scratch>/branch-review/<KEY>/<repo>`. In an export of a Node project, link `node_modules` from the checkout
(`ln -s "$PWD/<repo>/node_modules" <dir>/node_modules`) and run the codegen `ai-brain/profile/CODE_MAP.md`
§ Contract files names first when the generated types are gitignored. Never a switch, a stash or a worktree.

The commands, their scope and the directory each runs from, per repo, are in `ai-brain/profile/REPOS.md`
(§ Gate commands per repo, § Review standards):

| Check | Lane | Command, from the project directory | In an export |
| --- | --- | --- | --- |
| CI | both | `gh pr checks <n> -R <owner>/<repo>` | the same |
| rubocop | Rails | `bundle exec rubocop --format json <the diff's .rb files>`, scoped as `REPOS.md` says, from the app's or the engine's directory with that directory's Ruby (`mise exec ruby@$(cat .ruby-version) --` when the shell's differs) | the same, from the export's directory |
| eslint | React | `node_modules/.bin/eslint <the diff's .ts/.tsx files>` | the same |
| type-check | React | the repo's type command in `REPOS.md` | the same |
| react-doctor | React | as the frontend repo's own review recipe says (`REPOS.md` § Review standards): `npx -y react-doctor@latest --json --scope changed --base origin/<base> --no-telemetry --yes`, then its three filters (the repo's false-positives list, the rule's validation prompt, reading the code) | `--scope full`; keep only the diagnostics on lines the diff adds |
| specs | both | the `test` lines of Step 4's `impact <file>` plus the specs in the diff: `bundle exec rspec <files>`, `node_modules/.bin/jest <files>` | not run: the PR's CI stands in, and the review says so |

- A check that did not run is **not run**, with its reason. Never report a pass you did not watch.
- A syntax error, a type error, an eslint error or a failing spec that the diff causes is a **breaking change**. A
  check that is red on the base too is noted as pre-existing, not charged to the diff; say which base you checked.
- A react-doctor diagnostic that survives the three filters is a lane finding like any other, in the lane's words.

## Step 6 — the lanes, in parallel

Launch one agent per lane the diff has, **in one message**, each with `effort: "max"`:

- **Rails lane**: `subagent_type: "qa-backend"`.
- **React lane**: `subagent_type: "qa-frontend"`.

Each prompt opens with the line `Branch review — read-only.` (the agent's "Branch review" section keys on it), then:

1. **The target**, per repo: the repo, the base, the merge-base SHA, the tip SHA, the patch path, the lane's file
   list, and where the files are on disk (the checkout, or the export path).
2. **The Step 5 results** for its lane, verbatim, with their scopes.
3. **The Step 4 leads** for its files, under the heading `Brain leads (<the brain's header line>)`.
4. **What done means**: the acceptance criteria this ticket owns, verbatim with their ids, and the plan's parity rows
   and Decisions that touch its files.
5. **The standards to apply**, only those that match its files, by path: for each lane, the list in
   `ai-brain/profile/REPOS.md` § Review standards (the `CLAUDE.md` of each project a file sits in, the repo's rules
   files whose `paths:` glob matches a changed file, the review skills the repo ships for schema changes, fixes,
   tests and accessibility, the directory's lint config, the frontend review lenses and conventions), then
   `ai-brain/docs/PRACTICES.md`.
6. **The rule for the brain**: ask `ai-brain/bin/ai-brain` (from the workspace root) before any Grep, Glob or shell
   search, and return the `ai-brain: not run` line as the whole answer if it does not answer.
7. **The return**: the table of the agent's "Branch review" section, the scenarios that came back clean, and the
   brain queries it ran.

A lane that returns `ai-brain: not run` stops the review (Step 1).

## Step 7 — judge, then write the findings

1. **Verify every lane finding** at its `path:line` against the patch. Drop what the code does not bear out, and count
   the drops. A lane's claim is a lead; the file is the evidence.
2. **Add the review's own**: each owned criterion judged **met**, **partly met**, **not met** or **needs the browser**,
   with the `path:line` and the test that prove it; the breaking changes from Step 4; the plan parity; DRY from `find`;
   KISS from reading the diff whole.
3. **One finding per root cause.** Findings that share a cause merge into one that lists every site.
4. **The severity**:
   - **Request changes**: a breaking change (Step 4 or Step 5); an owned criterion **not met** or **partly met**; a
     lane BLOCKER or MAJOR (an authorization gap, data from another client, wrong hours or money, data loss, stale
     UI after a write, a broken BE ↔ FE contract); a contract change whose paired PR is missing.
   - **Suggestion**: everything that works but could be better: KISS, DRY, the best approach for a line, a repo
     convention the diff drifts from, naming, a lane MINOR or NIT, a test that could prove more.
5. **The reason**, one category per finding, in this order:

   | Category | It is about |
   | --- | --- |
   | Breaking change | what stops working, inside or outside the diff |
   | Acceptance criteria | an owned criterion not met or partly met |
   | Correctness | a bug in the new code |
   | Security and access | policies, tenancy, identity, secrets |
   | Data and queries | migrations, indexes, N+1, counts, time zones, money |
   | Caching | the Apollo cache, invalidation, freshness |
   | Contract | the BE ↔ FE seam: SDL, schema snapshot, codegen, nullability, error codes |
   | Tests | a behaviour with no test, a test that proves nothing |
   | Comments and docs | a comment, field description or doc the change made untrue; the comment budget |
   | KISS | a simpler shape does the same job |
   | DRY | the repo already has it |
   | Repo standard | a rule in the repo's `CLAUDE.md`, its rules files or `ai-brain/docs/PRACTICES.md` |
   | Syntax and approach | a clearer or safer way to write the same line |
   | Process | the PR body untrue at the head, a gap with no ticket, an unheld pair, a missing post-deploy section or relock |

6. **Every finding has six parts**: the category, the place, why, the change, a sample and the source. The shape,
   on an invented line:

   ````
   #### 3. DRY - `web-app/src/pages/Orders/components/DateRangeCell.tsx:41`

   Why: another formatter for a date range; the next date fix lands in only one of them.
   Change: call `formatDateRange` from `web-app/src/helpers/dateFormat.ts:127` instead.
   Sample:
   ```tsx
   // before
   const label = `${toShortDate(order.placedAt)} - ${toShortDate(order.dueAt)}`;
   // after
   const label = formatDateRange(order.placedAt, order.dueAt);
   ```
   Source: `ai-brain find format date range`; ai-brain/docs/PRACTICES.md, "KISS and DRY".
   ````

   - **The place** is the full path from the workspace root with a line, so the brain links the record to the file.
   - **The sample** is short and real: the before quotes the diff (one to four lines), the after uses the repo's own
     helpers and names (one to six lines). A finding about a missing thing shows where it goes.
   - **The source** is what the finding rests on: the rule (file and section), the brain line, the check output, or
     the criterion id.

## Step 8 — the review

Print it in this order:

1. **Ticket**: key, title, sprint; per repo the branch, the base, the tip and the PR; the brain's header line.
2. **Verdict**: `Request changes: <n> blocking, <m> suggestions`, or `Comment: nothing blocks, <m> suggestions`, or
   `No findings`.
3. **Acceptance criteria**: `| AC | Criterion | Verdict | Evidence |`, every owned criterion, then the others with their
   owner.
4. **Request changes**, grouped by category in the Step 7 order.
5. **Suggestions**, grouped the same way.
6. **Reached outside the diff**: `| Consumer (path:line) | Reaches | Breaks, safe, or the paired PR's |`.
7. **Checks**: `| Check | Repo | Scope | Result |`, not run included.
8. **Plan parity**: files planned and not touched, files touched and not planned.
9. **Already raised**: what other reviewers flagged that this review agrees with, each with its link.
10. **Brain**: `| Verb | Words | Lead |`, the leads dropped, and the lanes' queries.
11. **Not reviewed**: uncommitted work, files outside every lane, branches not taken.

## Step 9 — the record the brain reads

`ai-brain/sprints/<slug>/reviews/<KEY>.md` (a PR with no key: `chore-<repo>-<n>.md`). The slug is the plan's
sprint from the `ticket` line, else the ticket's active sprint in Jira, else the fallback query in
`ai-brain/profile/TRACKER.md` § Current sprint, named as `/plan` Step 2 names it. Write in the file
`ai-brain/bin/plan-doc edit sprints/<slug>/reviews/<KEY>.md` prints; it makes the sprint's `reviews/`
folder the first time.

- A new file starts with `# <KEY> — branch review` and one line with the ticket link and the plan's path.
- Each run appends `## Round <n> — YYYY-MM-DD`, with the tips it reviewed and the Step 8 sections. Never rewrite an
  earlier round. From round 2, the round opens with the last round's findings, each **fixed**, **still open** or
  **withdrawn**. Request changes still come from the whole diff, but new Suggestions only from lines changed since
  the last round's tip (`git -C <repo> diff <last tip> <tip>`); a defect a fix introduces still counts.
- Every finding names its file in full from the workspace root, so `ai-brain notes <file>` lists this review for the
  next `/plan`, `/dev` and `/branch-review` that touch it. That is how the brain learns from a review.
- **Rules to add.** A finding that states a rule `ai-brain/docs/PRACTICES.md` lacks, or repeats one an earlier
  review made on another ticket, goes under `### Rules to add to PRACTICES.md` with its evidence. A person folds them
  into the doc through a `ai-brain` PR; `docs/` does not commit straight to `main`.
- Then `ai-brain/bin/ai-brain index --background`. The record is not committed: `sprints/` is gitignored,
  so it stays on this machine.

Prose follows `ai-brain/docs/SPRINTS.md`; the samples are the one kind of code a sprints doc carries.

## Step 10 — post, only on a yes

Skip it with `--no-post`, or when no PR exists, and say so. Otherwise one `AskUserQuestion`, with per PR the event and
the number of inline comments:

- **Post the reviews (Recommended)**
- **Don't post**

On a post, per PR:

- **Event**: `REQUEST_CHANGES` when that PR's repo has a blocking finding or an owned criterion is not met, otherwise
  `COMMENT`. Never `APPROVE`. GitHub refuses `REQUEST_CHANGES` from the PR's own author: when `gh api user --jq .login`
  is the PR's author, post `COMMENT` with the body opening `Request changes`.
- **Body**: the verdict, the criteria table, the findings of that repo that have no line in the PR's diff, and the
  counts.
- **Inline comments**: each finding whose line falls inside a hunk of `gh pr diff <n> -R <owner>/<repo>`, at its
  repo-relative `path` and `line`, `side: RIGHT`, with the finding's parts as its body.
- **Prose** follows the repo's rule for review text (`ai-brain/profile/REPOS.md` § Review standards names it): no
  emojis, a spaced hyphen for a dash, plain verbs, no AI attribution.
- **Send** with `gh api repos/<owner>/<repo>/pulls/<n>/reviews --method POST --input <scratch>/branch-review/<KEY>/<repo>-review.json`,
  the file being `{ "commit_id": "<tip SHA>", "event": "...", "body": "...", "comments": [{ "path": "...", "line": N,
  "side": "RIGHT", "body": "..." }] }`. Read it back (`gh api repos/<owner>/<repo>/pulls/<n>/reviews --jq '.[-1] |
  {state, html_url}'`) and add the link to the round.

## Final report

The Step 8 review, then the record's path, each posted review's link or "not posted", and the workspace
summary: the brain queries by verb, every file read, the checks with their scopes, and what is still open.

## Rules

- No brain, no review. An `ai-brain: not run` anywhere stops it with the error and `ai-brain/bin/ai-brain-up`.
- Read-only on every code repo. No switch, stash, worktree, `git add`, edit, commit or push there.
- The lanes come from the diff's files, never from a ticket prefix.
- A lead is not a finding until its `path:line` is opened. A check is not a pass until it ran and passed.
- Request changes only for what breaks or what an owned criterion misses. KISS, DRY and the best approach are
  Suggestions, and a Suggestion never blocks. A missing end-to-end test is neither: it is the developer's choice.
- Every finding: category, place, why, change, sample, source.
- The plan's Decisions bind the review; the criteria come from the whole family.
- One record per ticket, a round per run, never rewritten, written through `plan-doc` and kept local.
- Never approve, never merge, never post or push without a yes. No AI attribution anywhere.
