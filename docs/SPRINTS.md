# SPRINTS — where plans, reports, bugs and reviews live

`ai-brain/sprints/` is the source of truth for what you build. Every ticket's plan, its dev report, its hunt
reports, its open bugs, its review rounds and its evidence live there, one folder per sprint: `/plan` writes the
plan, `/dev` builds from it, appends its Dev report and keeps its screenshots and videos in the ticket's evidence
folder, `/bug-hunt` files its findings beside it, `/qa-demo` keeps its recordings there, `/branch-review` adds a round
per review, and the ai-brain indexes the documents, so the next session asks the brain instead of re-reading
(`ai-brain/bin/ai-brain ticket <KEY>`, `sprint`, `history <file>`, `notes <file>`, `gaps`).

Earlier plans may sit in a plans archive: a `plans` knowledge repo in the brain's `project.toml`, read from every
branch head, which `plan-doc import` copies from through `PLAN_DOC_ARCHIVE` (`ai-brain/profile/REPOS.md`, "The plans
archive").

## Layout

```
sprints/<sprint>/
├── plan/<KEY>.md                    the plan: parity, files to touch, action items, Dev report, Log
├── reports/<DD>-<slug>-bug-hunt.md  one /bug-hunt run
├── bugs/<slug>.md                   one finding still open
├── reviews/<KEY>.md                 /branch-review: one file per ticket, a dated round per run, never rewritten
└── evidence/<KEY>/                  /dev's screenshots, GIFs, mp4s and notes.md, its runs in runs/ (§ Evidence)
    ├── hunt/                        /bug-hunt's notes.md, bug-hunt.md and screenshots
    └── qa/                          /qa-demo's run files and recordings
```

The folder is the sprint's slug, made from the tracker's sprint name (`ai-brain/profile/TRACKER.md` § Current sprint
has the rule, e.g. `2026-s1`). The tracker says which sprint is current; `ai-brain sprint all` lists the folders.
Work with no ticket is `plan/chore-<slug>.md`.

## Local only

Nothing here is tracked: `sprints/` is gitignored, so each dev's plans, reports, bugs and reviews stay on that dev's
machine, never committed and never pushed. A fresh clone has no `sprints/` at all; it appears the first time `/plan`
writes a plan. No AI attribution in a doc. `ai-brain/bin/plan-doc` finds and makes the files:

| Step | Command |
| --- | --- |
| Find a ticket's plan | `plan-doc path <KEY>` |
| Print it | `plan-doc show <KEY>` |
| Get the file to edit; makes its sprint folder and `plan/` (or `reviews/`, `reports/`, `bugs/`) on first use | `plan-doc edit sprints/<slug>/plan/<KEY>.md` |
| Copy plans from the archive (`PLAN_DOC_ARCHIVE`) | `plan-doc import [--force] [<path>…]` |

`edit` prints the same file whatever branch ai-brain is on, since nothing under `sprints/` is tracked. The
commands make the evidence folders themselves (`mkdir -p`). The ai-brain reads every `.md` there from disk on each
`index`: after a plan changes, `ai-brain/bin/ai-brain index --background` lets `ai-brain ticket <KEY>` see it.

## Evidence

Each ticket's screenshots, GIFs, mp4s and run files sit beside its plan, in
`ai-brain/sprints/<sprint>/evidence/<KEY>/`: `<sprint>` is the plan's folder (`plan-doc path <KEY>` prints it), and
work with no ticket uses its chore slug. `/dev` writes to the folder itself, with its steps files and raw runs in
`runs/`; `/bug-hunt` writes to `hunt/` and `/qa-demo` to `qa/`.

- **Never committed, never pushed.** `sprints/` is gitignored and no branch anywhere carries the evidence, so
  screenshots of your product never reach this repo or any other. The e2e repo still holds the specs `/bug-hunt`
  promotes; only the artifacts live here. Check every frame for a real person's data before it leaves the machine.
- **In a PR body**, each image, GIF or mp4 is a placeholder `![alt](evidence:<file>)`, `<file>` relative to the
  evidence folder.
- **The upload.** After `gh pr create`, `ai-brain/bin/pr-images <owner>/<repo>#<number> <evidence folder>` opens the
  PR in a browser signed in to GitHub, uploads each file the body names through GitHub's own attachment box, and
  rewrites the body with the returned links; a video becomes GitHub's inline player. `--dry-run` lists what it
  would upload and changes nothing. When it fails, the placeholders stay: drag the listed files into the PR on
  GitHub.
- **Signing in, once per machine.** `ai-brain/bin/pr-images --login` opens a headed browser for you to sign in to
  GitHub, and saves the session under `ai-brain/evidence/.auth/`, which is gitignored. That session is a
  credential: never copy, commit or share it, and delete the folder to sign out.
- **The tooling** is `ai-brain/evidence/`, with Playwright pinned in its `package.json`. `ai-brain/bin/ai-brain-up`
  installs it when Node is there; by hand, `npm ci --prefix ai-brain/evidence` and
  `npx --prefix ai-brain/evidence playwright install chromium`.

## What the brain reads from a plan

| In the plan | Becomes |
| --- | --- |
| `# <KEY> — <title>` | the ticket and its title |
| `**Ticket:** [KEY](…) · Type · Status · Owner ·` | the tracker type, status and owner |
| `**Parent:** [KEY](…)` | the parent ticket |
| The header's `Repo` / `Branch` table | the branches |
| `## TLDR`, its first bullet | what the ticket is, in one line |
| `## Parity analysis`, Verdict `gap`, `blocked` or `unknown` | an open gap, until every action item that closes it is `done` |
| `## Files to touch`, the `File` column | what `/dev` will touch, with the change and the item |
| `## Action items`: `Repo + files`, `Closes`, `Status` | the files per item, and the done and open counts |
| `## Dev report`: `### Summary`, `### Files changed` | what was built, and the files it changed |
| A PR link anywhere | the PRs |

A review round is read the same way: its key comes from the file name, every `repo/path:line` it cites becomes a
`CITES` edge, and `ticket <KEY>`, `sprint` and `notes <file>` list it. That is how a finding reaches the next
`/plan`, `/dev` and `/branch-review` that touch the same file.

Write each path in full from the workspace root (`monorepo/gems/orders/app/…/x.rb:42`, `web-app/src/…/X.tsx`) so it
resolves to exactly one file. A file still to be added is listed with the change `add`; the brain keeps it as text
until it exists.

## The TLDR rule

Every plan opens with a TLDR that answers two questions, for someone who has never seen the ticket: **what is
this**, and **how do I test it**. Short sentences, plain English: no jargon, no class names, no paths, no code.
Say why it matters. The test line is for a person ("open the order and look at the top of the page"), not CI.
One to three sentences per half; everything precise goes in the sections below.

## Prose

Markdown, relative links, a `path:line` behind every claim about code, no code blocks of product code, and no AI
attribution anywhere. One exception: a review's findings carry short before/after samples (one to six lines),
because the sample is the finding.
