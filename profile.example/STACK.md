> Example of `ai-brain/profile/STACK.md`: how `/dev`, the e2e lane and `/bug-hunt` bring the app up and reach it.
> Copy it to `ai-brain/profile/` and fill it in; the real one lives there, gitignored.

# STACK — running and reaching the app locally

Every path is relative to the workspace root. The skills and agents cite the sections below by name.

## Entry points

`/dev` asks which stack to drive, every time its browser check is reached:

- **The host app, `http://localhost:3000`.** Real sign-in; personas impersonated from `/admin/users`. Needs the feature
  flag `NEW_CHECKOUT` on. The page loads micro-frontends from a feed URL; a frontend change only shows when that feed
  serves this checkout's build (§ Frontend feed).
- **The shell, `http://localhost:1234`.** `cd shell && yarn dev`, with
  `ORDERS_GRAPHQL_URL=http://localhost:3000/orders/graphql` so the data comes from the host app.

| Chosen | May ask about | Never asks about; does this instead |
| --- | --- | --- |
| Host app | The host app: starting it, pending migrations | Any frontend: when the diff touches one, the run builds and serves it (§ Frontend feed) |
| Shell | The shell: starting it | The host app, which only serves the data: one that answers `/health` is used as it is; one that is down is started in the background and stopped at the end |

**The e2e stack.** The suite needs the host app on `:3000` with `ENABLE_DEBUG_UI=true`; Playwright boots its own
frontend on `:5011`.

```
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:3000/health
cd monorepo && ENABLE_DEBUG_UI=true bin/rails s -p 3000   # if it does not answer 200
```

## Frontend feed

1. Build each frontend from its own checkout with a production `pilet build`, every `.env` key blanked.
2. Serve them: `python3 -I ai-brain/.claude/skills/dev/pilet_feed.py 5099 @acme/web-app@1.0.0=<dir> ...`.
3. Start the host app with `PILET_FEED_URL='http://localhost:5099/feed'`, then confirm in the browser that each bundle
   came from `:5099`.

## Preflight

- **The page serves this branch.** For an engine change, a request must show the new behaviour; restart a server
  this run started when it does not.
- **Signed in.** `node <driver dir>/check-auth.mjs <baseURL>`: exit 0 signed in, 3 not, 4 unreachable. On 3, a headed
  window waits for the engineer to sign in by hand: nothing types a password.

## Test data

Everything shown runs on a test client: **Demo client** unless the user names another. Look its id up each run,
read-only. One real user per persona (`ai-brain/profile/DEFINITIONS.md`), impersonated and stopped at the end of every
run. State comes from doing what the user does: add to cart, place the order, cancel it.

## Gates

For every repo the diff touched, the gate commands in `ai-brain/profile/REPOS.md` (§ Gate commands per repo).

## Recording

- Steps files and runs live in `monorepo/tmp/tickets/dev/<KEY>/` (gitignored), written for the QA driver with
  `ai-brain/.claude/skills/qa-demo/cursor.mjs` for a visible cursor and captions.
- **Record**: `node <driver> <baseURL> <run dir> <steps> --video`, at `1440x900` so a table stays readable.
