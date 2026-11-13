---
name: ai-brain
description: Use FIRST, before Grep, Glob or Read, for any question about the workspace's code that names a GraphQL field, type or operation, a hook, a resolver, a mutation, a Kafka topic, a route, a table, a job, a feature flag, a spec, or asks what a rename or change breaks, who consumes or calls something, where something is used, what already does X, or how the UI reaches the database. The ai-brain graph of every registered repo (apps, engines, micro-frontends, the shell, libraries, the e2e suite, notes, plans) answers in one command with file:line, instead of many greps.
allowed-tools: Bash(ai-brain/bin/ai-brain:*)
---

The brain is a graph of every repo registered for this workspace, read at `origin/<ref>`. Ask it with the CLI,
run from the workspace root. The output format, the exit codes and the trust rule are in
`ai-brain/docs/AI_BRAIN.md`.

Start a session with `ai-brain/bin/ai-brain fresh`. It prints one header line, starts Neo4j when it is down, and
starts a background re-index when a repo moved. Then use a verb:

| Verb | Use it for | Example |
| --- | --- | --- |
| `surface <words>` | Interfaces by name: GraphQL fields, types and operations, routes, topics, tables, flags, env vars, external APIs, frontend pages | `surface order queue` |
| `find <words>` | Code by what it does: symbol names and parameter names, every repo | `find format start end` |
| `impact <target>` | What reaches a field, operation, route, topic, table, symbol or file, with tests and notes | `impact Order.status` |
| `impact --diff <repo>...` | Consumers of what your branch changed that sit outside every listed diff. `<repo>` is the checkout as it stands; `<repo>@<ref>` a branch's commits wherever the checkout sits; `<repo>@<base>...<ref>` a stacked branch | `impact --diff monorepo@origin/you/proj-123-v1 web-app` |
| `consumers <target>` | Only the direct consumers | `consumers OrderQueue` |
| `trace <target>` | UI to operation to resolver to model to table; producer to topic to consumer | `trace Order.status` |
| `notes <file or words>` | Notes, plans, review rounds, `docs/` pages and `profile/` pages that cite a file, each ok, moved or gone | `notes src/helpers/dateFormat.ts` |
| `ticket <KEY>` | One ticket: its plan, files to touch, services, open gaps and items, branches and who holds them, commits and who made them, PRs, Dev report, related tickets | `ticket PROJ-123` |
| `sprint [<slug>\|all]` | A sprint's tickets with state, gaps and file counts, then files two plans both touch; `all` lists sprints | `sprint 2026-s1` |
| `gaps [<KEY>\|<slug>]` | Open gaps (a gap row whose closing items are not all done) and open action items | `gaps PROJ-123` |
| `history <repo/path>` | The tickets that planned, built, committed to or cited a file or directory, newest first | `history web-app/src/pages/Orders` |
| `who <repo/path>` | Who wrote a file (git authors and recent commits) and the tickets behind it | `who monorepo/gems/billing/app/policies` |
| `related <KEY>` | Tickets whose plans or commits share its files, the rarest shared files counting most | `related PROJ-123` |
| `status` | Graph size, engines, externals, schema skew; `status --skew` lists the skew | `status` |

Rules:

- Every line is a lead with a `path:line`. Open the file before you build on a lead.
- Never write Cypher. Use a verb. For a multi-step question, write a short script against `ai_brain.api`
  (`ai-brain/ai-brain/.venv/bin/python -c "from ai_brain import api; print(api.trace('X'))"`) and print only the
  final answer.
- Exit 3 or 4 prints `ai-brain: not run (<reason>)`. Say so, then fall back to grep.
