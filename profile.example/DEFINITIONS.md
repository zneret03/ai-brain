> Example of `ai-brain/profile/DEFINITIONS.md`: your product's vocabulary, the personas, statuses and classifications a
> plan must not invent. Copy it to `ai-brain/profile/` and fill it in; the real one lives there, gitignored.

# DEFINITIONS — personas, statuses, classifications

Condensed from the product's definitions page (link it here, with its last-modified date). When a ticket says "the
manager can…" or "once confirmed…", the meaning is here — and a plan that invents its own statuses or roles is wrong
before it is written.

## Personas

| Persona | Scope | Can do |
|---|---|---|
| **Customer** | Own orders only | Place, change and cancel own orders; see own invoices |
| **Store manager** | Their store's orders | Confirm or reject orders; issue refunds up to a limit |
| **Store admin** | Whole store. Super user. | Override every decision; configure the store |
| **Support — view only** | All stores, read-only | View everything above |

Say where authorization lives (policy code in the owning service, never the token alone).

## Order statuses

| Customer label | Staff label | Meaning | Next action |
|---|---|---|---|
| DRAFT | DRAFT | Started, not yet placed | The customer places it |
| PLACED | **PENDING** | Placed, awaiting review | Staff confirm or reject it |
| CONFIRMED | CONFIRMED | Accepted, ready to ship | None |
| SHIPPED | SHIPPED | Handed to the carrier | Terminal. **Read-only.** |

Write down the traps: a status that carries two labels by audience, or one that coexists with another rather than
replacing it.

## Fulfilment statuses (per shipment)

| Status | Meaning | Included order statuses |
|---|---|---|
| IN PROGRESS | Being picked and packed | CONFIRMED |
| SENT | Label printed and handed over | SHIPPED |

## Customer classifications

| Classification | What it changes | What the product must handle |
|---|---|---|
| Retail | Prices with tax | Tax per region |
| Wholesale | Net prices, credit terms | Invoices on terms, credit limits |

## Rules the product must express

The rules a rules engine or a configuration must be able to state, with the cases that make them conditional.

## Rules the QA lanes check

**Authorization**

- A `customer_id` or `account_id` taken from arguments and trusted instead of derived from the authenticated
  identity. Blocker.
- Horizontal access: one customer reaching another's orders.
- A policy that grants a persona more than this page says it has.

**Statuses and data**

- An enum that restates a status set inconsistently with this page.
- Money in a float where the schema uses decimal.
- A date compared or stored without its intended zone, or a UTC value rendered as local.

**The bug hunt** — the absent value (a null the type permits), boundaries (a period edge, a non-UTC timezone, a value
at the top of its range), tenancy (the same read as another customer), role (each persona the screen allows).

**Severity** — `BLOCKER`: authorization bypass, cross-tenant data leak, data loss, a wrong amount of money. `MAJOR`: a
real bug, a missing guard on a non-sensitive path, a broken contract with the frontend.
