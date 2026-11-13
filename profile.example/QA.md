> Example of `ai-brain/profile/QA.md`: the shared environment `/qa-demo` records on, how to sign in, how to find
> data, the comment's recording table and the QA driver. Copy it to `ai-brain/profile/` and fill it in; the real one
> lives there, gitignored.

# QA — the shared environment `/qa-demo` records on

Every path is relative to the workspace root. `/qa-demo` cites the sections below by name.

## Environment

- `DEV=https://dev.example.com`; the environment's name, used in the comment's heading, is `dev`.
- Each ticket's run files go in `<qa>` = `ai-brain/sprints/<sprint>/evidence/<KEY>/qa/` (gitignored with the rest of
  `sprints/`); the driver runs from `monorepo/apps/shop`, so from there `<qa>` is
  `../../../ai-brain/sprints/<sprint>/evidence/<KEY>/qa`.
- **Never** a client other than **Demo client** (`client_id` 42). Never staging or production. Never a control that
  saves.
- `/dev` never points a browser at this environment; that is `/qa-demo`'s job.
- **Is it deployed?** A frontend change: its merge commit is in a released tag. A backend change: the deployed
  release contains the merge commit (`git merge-base --is-ancestor <merge-sha> <deployed-sha>`).
- **Reach the page the way QA does**: through the app's own menus first.

## Sign-in

- The credentials come from `~/.bashrc` (`export QA_EMAIL='…'`, `export QA_PASSWORD='…'`); a loader `eval`s those
  lines in the same call as the command that needs them.
- `ai-brain/profile/qa/login.mjs` enters them (a starting point: `ai-brain/profile.example/qa/login.mjs`); the user
  enters any 2FA code in the browser window, always.
- A saved session lasts about 30 minutes; re-check before each ticket.

| Persona | Who plays it |
| --- | --- |
| Customer | a user with an account on the Demo client and no admin role |
| Store admin | a holder of the `store_admin` role on the Demo client |

## Data lookups

Existing data only, every query read-only:

```
psql "$DEV_DATABASE_URL" -c "SET default_transaction_read_only = on; <SELECT ...>;"
```

- **Client: Demo client, always.** `SELECT id, name FROM clients WHERE id = 42` must return `Demo client`.
- **One user per persona**, and each user's name, which QA searches for.

## Recording

The comment: a level 3 heading, `How to replicate <KEY> on dev`, then for each category a level 4 heading and one
table.

| Category | Columns | What goes in it |
| --- | --- | --- |
| Recording | Item · Detail | Environment; Client, `Demo client (client 42)`; Build; Recorded; Video; Evidence |
| Before you start | Item · Detail | Sign in; Data; Act as a persona; Open the page; Saves data |
| Impersonate | Step · Persona · Name · User id | One row per step, as `Dana Lee` and `1234` |
| Acceptance criteria | AC · Criterion · Step · Result | Every criterion, verbatim from the ticket |

## Driver

- The QA driver: `monorepo/apps/shop/qa/drive.mjs` (install: `cd monorepo/apps/shop && yarn install`).
- The session check: `node qa/check-auth.mjs $DEV` (exit 0 signed in, 3 signed out, 4 unreachable).
- The steps file imports `ai-brain/.claude/skills/qa-demo/cursor.mjs` for the cursor and captions; as seen from `<qa>`
  that is `../../../../../.claude/skills/qa-demo/cursor.mjs`.
- **Rehearse** without video until every step passes, then **record** with `--video`, then make the media with
  `ai-brain/.claude/skills/qa-demo/media.sh`.
- Run files stay under `<qa>` (`ai-brain/sprints/<sprint>/evidence/<KEY>/qa/`) and are never committed. The sign-in
  run's scratch and the saved session stay with the driver: they belong to no ticket.
