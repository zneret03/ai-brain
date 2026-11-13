# DESIGN PARITY — building and checking against Figma

When a ticket carries a Figma link, the design is part of the contract, and "it renders" is not the bar.
This file is the shared definition of what gets extracted, what gets checked, and what counts as a
defect — so `/plan`, `/dev` and the PR's reviewer are measuring the same thing.

No Figma link on a ticket means no design check. Do not invent one from a screenshot.

## The node inventory — `/plan`'s output

The plan doc carries a table of **every node the ticket needs**, not just the top-level frame. A missing
node is the most common design defect here, and it is only findable if the plan enumerated it.

| Column | Content |
|---|---|
| Node id | The Figma node id (`1234:5678`), exactly as the tool returns it |
| Name | The layer/component name in the file |
| Kind | `screen` · `component` · `variant` · `state` · `icon` · `token` |
| Maps to | The frontend file it lands in, or `new` |
| Spacing | The padding, gap and margin values the node specifies |
| Typography / colour | The token names, not raw values, where the file uses variables |
| Notes | Interaction, responsive behaviour, empty/error/loading variants |

Get them with the Figma tools rather than by eye:

- `get_metadata` — the node tree for the file or a frame. **Start here**: it is how you find nodes the
  ticket never mentioned.
- `get_design_context` — the design spec for a node: layout, spacing, typography, fills.
- `get_variable_defs` — the design-system variables in play. Token names are what the code should carry.
- `get_screenshot` — the visual reference to attach to the plan and to compare against.
- `get_code_connect_map` — an existing Figma-node → component mapping, if the file has one. Reuse beats
  re-deriving.

**Every variant and every state is a node.** Default, hover, focus, disabled, empty, loading, error,
and the responsive breakpoints the file defines. A plan that lists the happy-path frame and nothing else
will pass a check that only looks at the happy-path frame, and the ticket will come back from review.

## What the design check looks at

Against the node inventory, in this order:

1. **Coverage** — is every node in the plan actually built? A node with no implementation is a
   `MAJOR`; a **state** that cannot be reached at all (no empty branch, no error branch) is a `MAJOR`.
2. **Spacing** — padding, gap, margin. This is where the defects are. Compare the Figma value to the
   value in the code, and name both.
3. **Typography** — size, weight, line-height, and whether the code uses the theme's token rather than a
   literal.
4. **Colour** — token name match. A raw hex where the theme carries the token is a defect even when the
   pixel value is identical, because the next theme change silently breaks it.
5. **Hierarchy and order** — layout direction, alignment, element order, what wraps and what truncates.
6. **Iconography** — the right icon, the right size, the right accessible name.
7. **Responsive** — the breakpoints the file specifies, if it specifies any.

### Tolerances — so a check does not fail a build over a rounding artefact

- **Spacing: exact.** On a spacing scale (MUI's is 8px) a Figma 12px gap is `1.5`, not "about 1". If the
  design value is not on the scale, say so in the finding and name the value used.
- **Font size, line-height, radius: exact**, or a named token that resolves to the design value.
- **Colour: the token must match by name.** Where the design has no variable, the hex must match exactly.
- **Rendered screenshots: ±1px** on measurements read off an image, and only when there is no code value
  to read instead. Prefer the code value — it is exact, and a screenshot measurement is not.
- **Anything the design file itself leaves ambiguous is an open question in the plan**, not a finding
  against the code.

### What is not a design defect

- A deviation the plan **declared**, with a reason. Those are parity entries, already accepted.
- Anti-aliasing, font rendering, or a difference visible only under a browser zoom the design never
  specified.
- A platform affordance the design omitted — a focus ring, a scrollbar, a native control's own padding.
  The accessible version wins; note the deviation instead of removing the ring.
- Copy differences. Those belong to the frontend review and to the frontend's copy module
  (`ai-brain/profile/GRAPHQL_SURFACES.md` names it).

## Every design parity row names its test

A design claim with no way to re-check it decays the moment someone else edits the component. Per row:

- **Spacing, typography, colour, token usage** → the code value, cited `file:line`. That is the durable
  check: a reviewer or a later QA round reads the same line.
- **Node/state coverage** → a frontend integration test that renders the state and asserts on what the user
  sees, where the frontend keeps them (`ai-brain/profile/CODE_MAP.md` § Reuse homes).
- **The visual record** → a named e2e screenshot, filed in the ticket's evidence folder
  (`ai-brain/sprints/<sprint>/evidence/<KEY>/`, `ai-brain/docs/SPRINTS.md` § Evidence) next to the Figma
  reference image.

Do not ask for a pixel-snapshot test unless the workspace has a visual-regression harness
(`ai-brain/profile/E2E.md` § Suite says whether it does); adding one is its own ticket.

## The correction cycle

`/dev` compares each "after" screenshot with its Figma node before the PR, and a gap goes round like any
other finding:

```
/dev finds a gap
   │
   ▼
the engineer re-reads the Figma node, decides: defect, or accepted deviation?
   │           │
   │ defect    └─ deviation → recorded in the plan's parity table, with the reason. Closed.
   ▼
plan updated — the parity row and a new action item, both numbered
   │
   ▼
/dev fixes exactly that
   │
   ▼
/dev re-shoots and re-checks → repeat until it matches
```

**The engineer adjudicates, in the plan.** A build that decides on its own that a 4px difference is fine has removed
the only check on the design contract. A finding is either fixed or written into the plan as a deviation
with a reason — never dropped silently.
