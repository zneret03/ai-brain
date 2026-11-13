---
description: Record a QA replication video for tickets that are ready for QA on the shared dev environment and post it to each ticket. Gated on the tracker's QA status (ai-brain/profile/TRACKER.md § QA gates); one scenario per acceptance criterion, each played as the persona the criterion names, on the one client the profile allows, with existing data, a visible cursor and captions, and your review before anything is posted. Never moves a ticket, edits a field, or saves data on the shared environment.
argument-hint: "<ticket-link|PROJ-123> [<ticket-link|PROJ-123> ...] [--no-post]"
disable-model-invocation: true
allowed-tools: Read, Write, Edit, Grep, Glob, AskUserQuestion, SendUserFile, Bash(git -C:*), Bash(ls:*), Bash(grep:*), Bash(date:*), Bash(ffprobe:*), mcp__claude_ai_Atlassian__getAccessibleAtlassianResources, mcp__claude_ai_Atlassian__atlassianUserInfo, mcp__claude_ai_Atlassian__getJiraIssue, mcp__claude_ai_Atlassian__searchJiraIssuesUsingJql
---

Record how to replicate each ticket's feature on the shared dev environment, check that it works on the way,
and leave QA a Jira comment with the steps and the video.

Tickets and flags: $ARGUMENTS

Run from the workspace root. Every path below is relative to it. The product facts this skill needs live in the
profile: the environment, the driver, the sign-in, the one client runs may use and the data recipes in
`ai-brain/profile/QA.md`; the QA gate, the fields and the posting setup in `ai-brain/profile/TRACKER.md`. Read
both before Step 0.

## What this does and does not do

- **Reads** Jira, the ticket's plan in `ai-brain/sprints/`, the repos, and the shared environment's database
  (read-only).
- **Drives** the shared environment in a real browser with the driver `ai-brain/profile/QA.md` § Driver names,
  acting for each criterion as a user who holds the persona that criterion names (QA.md § Sign-in), and
  records the run.
- **Signs in** to the shared environment with the user's own credentials from `~/.bashrc`. The user enters
  the 2FA code in the browser window, always.
- **Writes** one Jira comment per ticket through the Atlassian MCP connector. When `JIRA_EMAIL` and
  `JIRA_API_TOKEN` are set it also uploads the video files as attachments. Nothing else in Jira, and
  nothing at all without a yes in Step 8.
- **Never** transitions a ticket or edits a field: moving tickets is the user's job. Never presses a
  control that saves on the shared environment. Never runs against staging or production. Never uses a
  client other than the one `ai-brain/profile/QA.md` § Environment allows.

`allowed-tools` leaves out `addCommentToJiraIssue` on purpose, so every post asks the user first. It names none of
the profile's deploy or database commands either (QA.md § Environment, § Data lookups), so each of those asks
too, unless your local settings allow it.

## Inputs

| Give it | Effect |
| --- | --- |
| One or more Jira links or keys | Each parsed with `[A-Z][A-Z0-9]+-[0-9]+`. Handled one at a time, in the order given |
| `--no-post` | Record and review only. No Jira write |

No key found: stop and ask for one.

## Step 0 — prerequisites

Check each; when one is missing, stop and give the fix. `~/.bashrc` returns early in a non-interactive
shell, so sourcing it loads nothing. Every Bash call is a fresh shell, so load the credentials in the same
call as the command that uses them, with the loader line `ai-brain/profile/QA.md` § Sign-in gives. It has this
shape:

```bash
eval "$(grep -E '^export (JIRA_(EMAIL|API_TOKEN)|<the sign-in variables>)=' ~/.bashrc)"
```

Never print a credential, masked or not: check it with `[ -n "$VAR" ]` or `${#VAR}` only, and never put it
on a command line, in a file or in a log.

| Need | Check | Fix |
| --- | --- | --- |
| Sign-in to the shared environment | each variable QA.md § Sign-in names, with `[ -n "$VAR" ]` | Ask the user to add each to `~/.bashrc` as `export NAME='value'`: a literal value in single quotes, because the loader cannot resolve a `$VAR` reference and an unquoted special character breaks the line |
| The tool that tells what is deployed | the check QA.md § Environment gives | the fix it gives |
| Driver and its browser | the check QA.md § Driver gives | the fix it gives |
| ffmpeg with H.264 and GIF | `ffmpeg -hide_banner -encoders \| grep -E ' libx264 \| gif '` | `sudo apt install ffmpeg` |
| Jira token (optional) | `[ -n "$JIRA_EMAIL" ] && [ -n "$JIRA_API_TOKEN" ]` | the setup TRACKER.md § Writing to the tracker names. Without it the user attaches the video by hand |

Set `SKILL_DIR=ai-brain/.claude/skills/qa-demo`, and `QA` (the gitignored folder the run files go in) and `DEV`
(the environment's URL) from `ai-brain/profile/QA.md` § Environment.

## Step 1 — gate every ticket

`getJiraIssue` with `fields: [summary, status, issuetype, parent, assignee, <QA status field>, <criteria field>]`,
the two field ids from `ai-brain/profile/TRACKER.md` § QA gates (`getAccessibleAtlassianResources` gives the
cloud id).

A ticket goes ahead only when **both** hold, with the values TRACKER.md § QA gates gives:

- `status.name` is the gate status;
- the QA status field has the gate `value`.

Print `| Key | Title | Status | QA Status | Go |`. A ticket that fails the gate is reported with its real
values and left alone: never moved, never commented on. None go ahead: stop.

## Step 2 — what to show

Per ticket that goes ahead:

- **The criteria.** The criteria field on the ticket (TRACKER.md § QA gates). Then look for its plan:
  `ai-brain/bin/ai-brain ticket <KEY>` (its `plan` line), or `ai-brain/bin/plan-doc show <KEY>`;
  an older one may sit in the plans archive (`PLAN_DOC_ARCHIVE`). When a plan exists, its AC table
  (rows whose owner is this ticket), its Decisions and its Testing section's manual path define what
  "correct" means and the order to show it in.
- **One test case per criterion the browser can show**, as `AC1`, `AC2`… in the ticket's order, each with a
  one-line title. A criterion only a database, an API or a log can show goes in the comment as "not shown
  in the video", with the reason.
- **A persona per criterion**, from `ai-brain/profile/DEFINITIONS.md`. Take it from the criterion's own
  subject ("the employee", "a manager"); failing that, from the parent story's section on who uses it
  (TRACKER.md § Ticket family); failing that, ask in Step 5. Never invent a persona. A criterion that compares
  personas ("an employee sees X, a manager sees Y") gets one step per persona. Who plays each persona is in
  `ai-brain/profile/QA.md` § Sign-in.
- No criterion is showable (a backend-only ticket): skip the ticket and say why.

## Step 3 — is it deployed?

The video must show what QA will test, so the change has to be deployed. How to tell, for a frontend change and
for a backend change, is in `ai-brain/profile/QA.md` § Environment.

Not deployed: skip the ticket and say what is missing. Record the build (the tag or the release) for the comment.

## Step 4 — find the data, read-only

Existing data on the shared environment only. Never seed, never create a record, never press a control to make
a state.

- Every query runs read-only, through the runner `ai-brain/profile/QA.md` § Data lookups gives.
- **The client: only the one QA.md § Environment allows, always.** Check it with the query QA.md § Data
  lookups gives. Anything else: stop and tell the user; never fall back to another client.
- **State:** the rows each criterion needs, on that client. Read a table's columns before querying; QA.md
  § Data lookups names the schemas and the caveats.
- **One user per persona**, as the id QA.md § Data lookups says to use. How a persona maps to roles, and how a
  user reaches the client, are in QA.md § Data lookups. Read each join before trusting it. The user who owns
  the state and the persona who acts on it must line up: the manager must manage that employee.
- **Each user's name**, which QA searches for when acting as that persona, with the query in QA.md § Data
  lookups.

No fitting data or no user for a persona: skip the ticket and tell the user exactly which state or persona is
missing, so they can arrange it.

## Step 5 — confirm the run, once for all tickets

One `AskUserQuestion` before the shared environment is touched. It names, per ticket: the client, each
criterion with its persona and the user who plays it, the day or record shown, and the audited impersonation
reason `QA replication video <KEY> (<engineer's name>)`. Impersonation is audited and lives in the server
session, so this is the user's call. A no ends the run.

## Step 6 — sign in

From the folder `ai-brain/profile/QA.md` § Driver names:

- the session check QA.md § Sign-in gives, where exit 0 means signed in and 4 means the environment is
  unreachable (stop).
- Exit 3: with the Step 0 loader in the same call, run the headed sign-in QA.md § Sign-in gives. It runs
  `ai-brain/profile/qa/login.mjs`, which enters the email and password. Tell the user to enter the 2FA code
  in the window that opens, and to tick a captcha box if one appears. It waits up to five minutes.

A saved session lasts as long as QA.md § Sign-in says, so go straight from here to recording, and re-check
before each ticket.

## Step 7 — write, rehearse, record

**The steps file** is `$QA/<KEY>/demo-steps.mjs`: one scenario, so the ticket gets one continuous video. This is
its shape in the driver's format; QA.md § Driver has the two import paths as seen from the run folder.

```js
import { impersonate, stopImpersonating } from '<the impersonation helper, QA.md § Driver>';
import { caption, click, expectText, expectVisible, fill, hold, installCursor, pick, point } from '<this skill’s cursor.mjs, QA.md § Driver>';

const AS = { employee: 0, manager: 0 }; // Step 4: one user id per persona the criteria name
const REASON = 'QA replication video PROJ-123 (<engineer>)'; // the text approved in Step 5

export const testCases = [{ id: 'AC1', title: '<the criterion, in a line>' }];
export const scenarios = [
  {
    name: 'PROJ-123 replication',
    steps: [
      {
        name: 'as the employee',
        screenshot: false,
        run: async ({ page, context, note }) => {
          await installCursor(context); // before the first navigation
          await impersonate(page, { userId: AS.employee, reason: REASON, note });
        },
      },
      {
        name: 'AC1: <what the viewer sees>',
        tc: ['AC1'],
        run: async ({ page }) => {
          await page.goto('<the page>');
          await caption(page, 'AC1 · as the employee: <the criterion, in plain words>');
          await click(page, page.getByRole('button', { name: '<control>' }));
          await expectText(page.getByRole('combobox', { name: '<field>' }), '<expected>');
          await hold(page, 1500);
        },
      },
      {
        // impersonate() stops the previous impersonation first, so switching persona is one call.
        name: 'as the manager',
        screenshot: false,
        run: async ({ page, note }) => {
          await impersonate(page, { userId: AS.manager, reason: REASON, note });
        },
      },
      { name: 'stop impersonating', continueOnFailure: true, screenshot: false, run: ({ page }) => stopImpersonating(page) },
    ],
  },
];
```

Rules for the steps:

- **Reach the page the way QA does.** Navigate from the impersonated landing page through the app's own
  menus when they lead there. Otherwise use the entry points `ai-brain/profile/QA.md` § Environment lists, in
  its order. The comment says which one the video used.
- **Every criterion asserts.** `expectText` or `expectVisible` after each action, so a pass means the
  screen showed it. A caption leads each criterion and names its persona.
- **Each persona is checked.** After each impersonation, assert something only that persona sees: its
  landing page (QA.md § Sign-in says how to tell) or a control only it has. A user who lands as the wrong
  persona fails the step rather than recording the wrong view.
- **Nothing that saves.** No Submit, Save, Approve, Reject, Delete, Send, no autosaving field. A control that
  only stages a change in the browser is fine; QA.md § Driver names the known ones. When unsure whether a
  control saves, do not press it: put it in the comment as a step for QA instead.
- Selectors: the sources `ai-brain/profile/QA.md` § Driver names, the e2e suite's page objects first.

**Rehearse** without video until every step passes, at most three rounds, with the rehearsal command in
QA.md § Driver, into `$QA/<KEY>/rehearsal`. Read the run's `log.json` and the screenshots after each round. A
failure that looks like the product, not the script (the right control, the right data, the wrong result),
stops the ticket: report it to the user with the screenshot as a possible defect, and post nothing.

**Record** once the rehearsal is green, with the recording command in QA.md § Driver, into
`<run>` = `$QA/<KEY>/$(date +%F)-dev-demo`. Then make the media:

```bash
bash ai-brain/.claude/skills/qa-demo/media.sh <run>/media/*.webm <run>/<KEY>-qa-demo
```

The recorded run must pass too. If it fails, the video is not posted.

## Step 8 — review, then post

Send the user the GIF (`SendUserFile`, `display: render`) and the mp4 (`display: attach`), the run's
pass/fail per criterion from `log.json`, and the comment exactly as it will be posted. Then ask:
**Post** (Recommended) · **Re-record** · **Skip this ticket**. With `--no-post`, stop after showing.

On **Post**:

1. **With a token:** in one call with the Step 0 loader, run the `attach.mjs` line
   `ai-brain/profile/TRACKER.md` § QA gates gives; it sets the site and the gate, then runs
   `node $SKILL_DIR/attach.mjs <KEY> <run>/<KEY>-qa-demo.mp4 <run>/<KEY>-qa-demo.gif`. It re-checks the gate,
   uploads, reuses a file already attached under the same name, and prints each file's `mediaUuid`. Post the
   comment as ADF with a `mediaSingle` per file (below).
2. **Without a token:** post the comment as markdown, then open the folder for the user (on WSL,
   `explorer.exe "$(wslpath -w <run>)"`) and name the two files to drag onto the ticket.
3. `addCommentToJiraIssue`, one comment per ticket. An ADF post that the API refuses is retried once as
   markdown that names the attached files.
4. Save `{ commentId, attachments }` to `<run>/posted.json`. A later run on the same ticket updates that
   comment (`commentId`) instead of adding a second one.

## The comment

Written as the engineer, for QA. It follows the workspace rules for outward-facing text: plain sentences, no
em dashes, no emojis, and no mention of any assistant or tooling. Its words and tone follow
`ai-brain/docs/JIRA_COMMENTS.md`; the tables below are its shape, and `ai-brain/profile/QA.md` § Recording
gives the wording that names your environment, client, build and sign-in.

A level 3 heading, `How to replicate <KEY> on <the environment's name>`, then for each category below a level 4
heading and one table whose first row is the header. Categories and rows stay in this order.

| Category | Columns | What goes in it |
| --- | --- | --- |
| Recording | Item · Detail | Environment; Client, as QA.md § Recording writes it; Build, the tag or release Step 3 recorded and its PR; Recorded, the date and the engineer; Video, its file name and length, and that it follows the steps in order; Evidence, `The recording shows each step. QA confirms the outcome.` |
| Before you start | Item · Detail | Sign in; Data, the state QA needs and that it already exists; Act as a persona, how QA does it (QA.md § Recording); Between personas, what ends the session and what to do next (QA.md § Recording); Open the feature, where each persona lands; Saves data, which controls save, or that none do |
| Impersonate | Step · Persona · Search for this name · User id | One row per step: the persona, and the user's name and id from Step 4, as `Dana Lee` and `1234`. A persona played by the signed-in account reads `No one.` with the account to use instead, and `None` for the id |
| Steps by persona | # · Persona · Do · You should see · AC | One row per step, in the video's order. Do and You should see use the words on the screen |
| Acceptance criteria | AC · Criterion (from the ticket) · Step · Result in the recording | Every criterion, verbatim from the criteria field (TRACKER.md § QA gates). Result is `Passed`, `Failed`, `Partly shown.` with what was and was not, or `Not shown` |
| Not shown in the video | What · Why | Each criterion, or part of one, the browser could not show, with the reason, and how QA checks it when there is a way. A paragraph `None.` when everything was shown |
| Video | no table | A paragraph and a `mediaSingle` per uploaded file, the mp4 first |

Paths go in a `code` mark. Give every cell a `colwidth` so each table adds up to about 680 and fits the
comment. A two-column table as ADF:

```json
{ "type": "table", "attrs": { "isNumberColumnEnabled": false, "layout": "default" }, "content": [
  { "type": "tableRow", "content": [
    { "type": "tableHeader", "attrs": { "colwidth": [150] }, "content": [{ "type": "paragraph", "content": [{ "type": "text", "text": "Item" }] }] },
    { "type": "tableHeader", "attrs": { "colwidth": [530] }, "content": [{ "type": "paragraph", "content": [{ "type": "text", "text": "Detail" }] }] }] },
  { "type": "tableRow", "content": [
    { "type": "tableCell", "attrs": { "colwidth": [150] }, "content": [{ "type": "paragraph", "content": [{ "type": "text", "text": "Client" }] }] },
    { "type": "tableCell", "attrs": { "colwidth": [530] }, "content": [{ "type": "paragraph", "content": [{ "type": "text", "text": "Demo client (client 42)" }] }] }] }] }
```

A video goes in at the content width with its real width and height; without them Jira renders it small:

```json
{ "type": "mediaSingle", "attrs": { "layout": "center", "width": 100, "widthType": "percentage" },
  "content": [{ "type": "media", "attrs": { "type": "file", "id": "<mediaUuid>", "collection": "", "width": 1440, "height": 900 } }] }
```

A file whose `mediaUuid` came back null is named in a paragraph instead. Without a token, the same tables go
out as markdown pipe tables. A worked example, when your profile has one, is linked in QA.md § Recording.

## Rules

- The gate is Jira's state at the time of the run. Re-read it before posting, not only at Step 1.
- Existing data, only the client QA.md § Environment allows, nothing that saves. Stop impersonating at the end
  of every run, including failed ones (`continueOnFailure` on the last step).
- Every criterion is shown as the persona it names, never as whoever happens to be signed in.
- The environment's credentials come from `~/.bashrc` through the Step 0 loader and go only into the sign-in
  form. Never print, log or store them, and never let one reach a steps file, a screenshot, a recording or a
  comment. 2FA is the user's, in the headed window.
- No post without the Step 8 yes. One comment per ticket.
- Evidence is not verification: the comment reports what the recording showed, and QA confirms it.
- Run files stay under `$QA/<KEY>/`. Never commit them, and never attach the driver's saved session (QA.md
  § Driver says where it lives).

## Departures from the product's own browser-verification skill

When `ai-brain/profile/QA.md` § Driver names a verification skill and an evidence poster of the product's own,
this skill departs from them in two ways:

- **The comment goes through the Atlassian MCP connector, not the product's poster.** Such a poster posts a
  deterministic evidence report built from the run's log. A replication guide is written for QA from the
  acceptance criteria, which a poster has no way to produce. Uploads go through `attach.mjs`, which makes the
  same two REST calls (the attachment upload, then the media id from the content redirect) and refuses a
  ticket outside the gate.
- **Existing data only**, so the run never needs an exception for sacrificial data on the shared environment.
