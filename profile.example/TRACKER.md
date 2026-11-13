> Example of `ai-brain/profile/TRACKER.md`: how the skills read and write your issue tracker. Copy it to
> `ai-brain/profile/` and fill it in; the real one lives there, gitignored.

# TRACKER — the issue tracker: site, board, sprints, tickets, QA gates, writing

The skills cite the sections below by name.

## Site and board

- **Site:** Jira Cloud at `https://jira.example.com`, through the Atlassian tools
  (`getAccessibleAtlassianResources` gives the cloud id).
- **Board:** `42` only.
- **Ticket keys** look like `PROJ-123`. A ticket comes as a link (`…/browse/PROJ-123`, `…?selectedIssue=PROJ-123`) or
  a key. A key can also come from a branch name: `you/proj-123-v1` → `PROJ-123`.

## Current sprint

`--sprint` wins. Otherwise take it from the tracker, never from a table, which lags:

1. The ticket's sprint field — the sprint whose state is `active`.
2. None active: `sprint in openSprints() AND assignee = currentUser()`.

The sprint's name maps to its folder: `Sprint 2026-S1` → `2026-s1`. Record the slug **and** the numeric sprint id.
Work with no ticket is `plan/chore-<slug>.md`.

- `sprint = NN` in JQL matches the **id**, not the name.

## Ticket family

- The ticket handed to a skill is usually a **subtask** of a story. Read every field: the content may live in custom
  fields (Acceptance Criteria, Technical Notes) rather than the description.
- One inventory row per criterion: `<source key>/AC<n>` (e.g. `PROJ-120/AC2`).
- The family: `parent = <PARENT> ORDER BY key`.
- Who owns parents: e.g. "stories stay with the product manager; only subtasks go to developers".

## QA gates

`/qa-demo` goes ahead only when **both** hold:

- the ticket's status is `Ready for QA`;
- the field `customfield_10000` (QA Status) is `To test`.

The criteria are `customfield_10001`. The upload line, with the sign-in loader in the same call:

```bash
JIRA_BASE_URL=https://jira.example.com QA_GATE_STATUS='Ready for QA' QA_GATE_FIELD=customfield_10000 QA_GATE_VALUE='To test' node $SKILL_DIR/attach.mjs <KEY> <run>/<KEY>-qa-demo.mp4 <run>/<KEY>-qa-demo.gif
```

## Writing to the tracker

- Who reads the tickets: e.g. "the product owner reads every story, so comments are plain prose".
- Descriptions are ADF, comments are markdown. The plan stays local: no plan link in a description.
- A Jira token for uploads (`JIRA_EMAIL`, `JIRA_API_TOKEN`) is optional; without it the user attaches the video by
  hand.
