> Example of `ai-brain/profile/MICROSERVICES.md`: your platform's services, what each owns, and how they talk. Copy it
> to `ai-brain/profile/` and fill it in; the real one lives there, gitignored.

# MICROSERVICES — the platform on one page

Condensed from the architecture page (link it here), **checked against the repos on a date you write down**. Read the
page itself when a claim here matters; this file exists so an agent gets the bird's-eye view without a network call.

## The mental model

```
ORDERS   = the input     what the customer asked for
CATALOG  = the config    what this store sells, and how
BILLING  = the rules     what the order costs: prices, taxes, discounts
SHIPPING = the release   it goes out once, and you cannot unsend it
```

| Core service | Owns | The question it answers |
|---|---|---|
| `orders` | `orders`, `order_lines`, `carts` | What did the customer ask for, and was it confirmed? |
| `catalog` | `products`, `variants`, `store_settings` | What is this store set up to sell? |
| `billing` | `invoices`, `tax_rules`, `discounts` | What must the customer pay, and why? |
| `shipping` | `shipments`, `labels` | Did it go out, exactly once? |

The host app (`monorepo/apps/shop`) is **not** one of them: it owns login, the page shell and the identity feed.

## Which service lights up, by activity

| Activity | Frequency | Services |
|---|---|---|
| Browsing products | Constant | `catalog` only |
| Placing an order | Many times a day | `orders` + one price read from `billing` |
| Shipping an order | Once per order | `shipping`, then `orders` |

## The platform rules

1. **Facts travel on events.** Name the topics each service publishes, and the local read copies (projections) each
   keeps.
2. **Questions travel on GraphQL.** One endpoint per service.

**No cross-service table reads. No foreign key into another service's tables.**

## Where the split falls, and why it holds

- **catalog vs billing** — say what belongs on each side, and the rule that decides a case in between.

## Deployment state

Whether each service runs mounted in the host app or standalone today, and the cutover order if one is planned.

## What is not a service

The host app, the micro-frontends, the shell, shared gems and infrastructure repos.

## Routing a ticket to a service — the questions to ask

1. Does it record or read **what the customer asked for**? → `orders`.
2. Does it decide **what something costs**? → `billing`.
3. Is it a **store setting**? → `catalog`.
4. Does it **send the parcel**? → `shipping`.
5. Is it **login, the shell, or the identity feed**? → the host app.
6. Does it render UI? → the matching micro-frontend, **not** the host app's own UI.

## Related docs

Links to the architecture, migration and guardrail pages.

## Transports

What each side can use to talk: HTTP only, WebSockets, a push channel; what is not available without new
infrastructure.

## Routing defects

- A decision placed in the wrong service is a design defect to raise in planning, and a finding in review: prices in
  shipping, stock rules in billing, customer settings in catalog. Route it against § Routing a ticket to a service.
- Before putting code in a service, confirm that service owns the decision.

## Which service owns what

- The surface spans several services and two frontends; nobody holds it in their head, and a duplicated query is a
  defect. Check the other services' query and mutation types before accepting a new field.
