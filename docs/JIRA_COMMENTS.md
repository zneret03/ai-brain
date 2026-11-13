# Jira comments

How every comment a skill here posts on a ticket is written: `/plan`'s Phase 0 notes once `/dev` posts them,
`/dev`'s questions and its pull request link, `/qa-demo`'s replication notes, and any note to another developer.
Most readers are not engineers: product owners and QA read every Story (who reads what, here:
`ai-brain/profile/TRACKER.md` § Writing to the tracker).

## Words

- Say what a person or the system does, in the words on the screen: "the system submits the order", not
  `AutoSubmitDue` or `status: submitted`. No class, method, field, file or path names. A note to another developer may
  name one file when that file is the point of the note.
- No link to the plan in `ai-brain/sprints/`. Link the pull request, and say the demo is at the top of it.
- Kind, not forceful. Open with "Hi" and an @mention of the person asked, thank them, say so when nothing is blocked,
  and ask rather than tell: "Would you like the system to…?", not "Please confirm" or "This needs".
- The rules for outward-facing text still bind: the workspace's plain-prose banlist when it has one
  (`ai-brain/profile/TRACKER.md` § Writing to the tracker), no em dashes, no emojis, and no mention of any assistant
  or tooling.

## Shape

Short level 3 headings, in this order, leaving out any with nothing under it:

| Heading | What goes under it |
| --- | --- |
| What we built (or What changed) | Two to four bullets, each one thing a person can now do or see |
| Questions for you | A numbered list. Each item is the question as one plain sentence, then a short paragraph: why it comes up, and how it works until someone answers |
| Good to know | Bullets the reader should know but need not act on |
| Order of release | For a pull request: what goes in before it, with it or after it, and why, in one sentence each |

End with a short thank-you. A pull request comment is one opening sentence with the link and where the demo is, then
Order of release.

## Posting

- Post as ADF, so the @mention notifies: a `mention` node with the person's `accountId` (`lookupJiraAccountId`),
  headings as `heading` nodes, and questions as an `orderedList` whose items each hold two `paragraph` nodes.
- Show the user the exact text and post only on a yes. To fix a posted comment, edit it (`commentId`) rather than add
  a second one.

`/qa-demo` keeps its own tables for QA (`.claude/skills/qa-demo/SKILL.md`, "The comment"); its words and tone follow
this file.

## Example

A question for product:

> Hi @Sam Lee, thank you for writing up part 2. A few questions came up where your view as product owner would
> really help. None of this is blocking: until we hear from you, the system works the way each question describes.
>
> ### What we built
>
> - When a store turns on auto-confirm, the system confirms each customer's order for them on the day and at the
>   time the admin picked.
>
> ### Questions for you
>
> 1. Should a reopened order be confirmed again automatically?
>
>    If a manager rejects an order and an admin reopens it, it goes back to being a draft. For now the system leaves
>    it alone. Would you like the system to confirm it again at a later time instead?
>
> ### Good to know
>
> - When an order can't be sent in at its moment, the system tries again every 15 minutes.
>
> Thanks so much, Sam!
