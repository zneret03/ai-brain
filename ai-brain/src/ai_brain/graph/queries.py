"""Fixed, bounded, parameterized reads. The only Cypher the CLI runs (decision 1)."""

from __future__ import annotations

CONSUMER_EDGES = [
    "SELECTS",
    "USES",
    "CONSUMES",
    "USES_FLAG",
    "GATED_BY",
    "READS_ENV",
    "CALLS_ROUTE",
    "DEPENDS_ON",
    "RENDERS",
    "GUARDED_BY",
    "SUBSCRIBES",
    "MAPS_TO",
    "FOREIGN_KEY",
    "INVALIDATES",
    "CALLS_EXTERNAL",
    "TESTS",
    "UPDATES_CACHE",
]

SURFACE = """
CALL db.index.fulltext.queryNodes('interface_search', $q) YIELD node, score
WITH node AS n, score WHERE n.project = $p
WITH n, score ORDER BY score DESC, size(coalesce(n.display, n.name)) ASC LIMIT $lim
CALL (n) {
  OPTIONAL MATCH (n)-[:RESOLVED_BY|HANDLED_BY]->(impl)
  OPTIONAL MATCH (decl:File)-[:DECLARES]->(n)
  OPTIONAL MATCH (prod:Symbol)-[:PRODUCES|MAPS_TO|STREAMS|SCHEDULED_BY]->(n)
  RETURN coalesce(impl, decl, prod) AS at LIMIT 1
}
CALL (n) {
  OPTIONAL MATCH (c)-[r]->(n) WHERE type(r) IN $consumers
  RETURN count(DISTINCT c) AS consumers
}
RETURN n.kind AS kind, coalesce(n.display, n.name) AS name, n.owner AS owner, coalesce(at.repo, n.repo) AS repo,
       coalesce(at.path, n.path) AS path, coalesce(at.line, n.line) AS line, consumers
"""

FULLTEXT_COUNT = """
CALL db.index.fulltext.queryNodes($index, $q) YIELD node WITH node WHERE node.project = $p RETURN count(*) AS n
"""

FIND = """
CALL db.index.fulltext.queryNodes('symbol_search', $q) YIELD node, score
WITH node AS s, score WHERE s.project = $p
WITH s, score ORDER BY score DESC, size(s.name) ASC LIMIT $lim
CALL (s) {
  OPTIONAL MATCH (c)-[r:CALLS|REFERENCES|ENQUEUES|RENDERS|USES]->(s)
  RETURN count(DISTINCT c) AS callers
}
RETURN s.name AS name, s.kind AS kind, s.role AS role, s.repo AS repo, s.path AS path, s.line AS line, callers
"""

# Seeds by what the argument names: an interface, a symbol, or a file.
RESOLVE = """
CALL () {
  MATCH (n:Interface {project: $p}) WHERE n.display = $t OR n.name = $t OR n.name ENDS WITH ('.' + $t)
  RETURN n LIMIT 25
  UNION
  MATCH (n:Symbol {project: $p}) WHERE n.name = $t RETURN n LIMIT 25
  UNION
  MATCH (n:File {project: $p}) WHERE n.path = $t OR (n.repo + '/' + n.path) = $t
  RETURN n LIMIT 25
}
RETURN n.id AS id, labels(n) AS labels, n.kind AS kind
"""

RESOLVE_LOOSE = """
CALL () {
  MATCH (n:Symbol {project: $p}) WHERE n.short = $t RETURN n LIMIT 25
  UNION
  MATCH (n:File {project: $p}) WHERE n.path ENDS WITH ('/' + $t) RETURN n LIMIT 25
}
RETURN n.id AS id, labels(n) AS labels, n.kind AS kind
"""

# Everything a seed stands for: a file's symbols and declared operations, a class's methods, the interfaces the
# symbols implement.
EXPAND = """
MATCH (s) WHERE s.id IN $ids
OPTIONAL MATCH (s)-[:DEFINES*1..2]->(sym:Symbol)
WITH collect(DISTINCT s) + collect(DISTINCT sym) AS nodes
UNWIND nodes AS n
OPTIONAL MATCH (n)-[:DECLARES]->(op:Interface)
OPTIONAL MATCH (impl:Interface)-[:RESOLVED_BY|HANDLED_BY]->(n)
OPTIONAL MATCH (n)-[:PRODUCES|CONSUMES|MAPS_TO|STREAMS|SCHEDULED_BY]->(own:Interface)
WITH collect(DISTINCT n) AS nodes, collect(DISTINCT op) + collect(DISTINCT impl) + collect(DISTINCT own) AS ifaces
RETURN [x IN nodes | x.id] AS nodes, [x IN ifaces WHERE x IS NOT NULL | x.id] AS ifaces
"""

CONSUMERS = """
MATCH (i:Interface) WHERE i.id IN $ids
MATCH (c)-[r]->(i) WHERE type(r) IN $consumers AND NOT c.id IN $exclude
OPTIONAL MATCH (f:File)-[:DECLARES]->(c)
WITH i, r, c, f
OPTIONAL MATCH (u:Symbol)-[:USES]->(c) WHERE c:Interface AND c.kind = 'graphql_operation'
RETURN coalesce(i.display, i.name) AS iface, type(r) AS rel, coalesce(c.display, c.name) AS name,
       coalesce(c.repo, f.repo) AS repo, coalesce(c.path, f.path) AS path, coalesce(c.line, r.line) AS line,
       labels(c) AS labels, collect(DISTINCT [u.name, u.repo, u.path, u.line])[0..25] AS users,
       c.id AS cid, f.id AS fid, collect(DISTINCT u.id)[0..10] AS uids
ORDER BY rel, repo, path
"""

CALLERS = """
MATCH (s:Symbol) WHERE s.id IN $ids
MATCH (c)-[r:CALLS|REFERENCES|ENQUEUES]->(s) WHERE NOT c.id IN $exclude AND coalesce(c.path, '') <> s.path
RETURN s.name AS target, type(r) AS rel, c.name AS name, c.repo AS repo, c.path AS path, r.line AS line,
       r.inferred AS inferred, r.cross_engine AS cross
ORDER BY cross DESC, repo, path LIMIT 400
"""

TESTS = """
MATCH (x) WHERE x.id IN $ids
OPTIONAL MATCH (f:File)-[:DEFINES*1..2]->(x)
WITH collect(DISTINCT x) + collect(DISTINCT f) AS xs
UNWIND xs AS x
MATCH (t:Test)-[:TESTS]->(x)
RETURN DISTINCT t.repo AS repo, t.path AS path ORDER BY repo, path LIMIT 200
"""

NOTES = """
MATCH (x) WHERE x.id IN $ids
OPTIONAL MATCH (f:File)-[:DEFINES*1..2]->(x)
WITH collect(DISTINCT x) + collect(DISTINCT f) AS xs
UNWIND xs AS x
MATCH (n:Note)-[c:CITES]->(x)
RETURN DISTINCT n.kind AS kind, n.repo AS repo, n.path AS path, c.status AS status ORDER BY kind, path LIMIT 200
"""

NOTES_BY_WORDS = """
MATCH (n:Note {project: $p})
WHERE all(w IN $words WHERE toLower(coalesce(n.name, '') + ' ' + coalesce(n.title, '') + ' ' + n.path) CONTAINS w)
OPTIONAL MATCH (n)-[c:CITES]->(:File)
RETURN n.kind AS kind, n.repo AS repo, n.path AS path, n.status AS status, count(c) AS cites,
       coalesce(n.gone, []) AS gone ORDER BY kind, path LIMIT 200
"""

TRACE_FIELD = """
MATCH (start:Interface) WHERE start.id IN $ids
OPTIONAL MATCH (op:Interface {kind: 'graphql_operation'})-[:SELECTS]->(start)
WITH start, CASE WHEN start.kind = 'graphql_operation' THEN [start] ELSE collect(DISTINCT op) END AS ops
UNWIND ops AS op
OPTIONAL MATCH (u:Symbol)-[:USES]->(op)
OPTIONAL MATCH (f:File)-[:DECLARES]->(op)
OPTIONAL MATCH (op)-[:SELECTS]->(root:Interface)
  WHERE root.display STARTS WITH 'Query.' OR root.display STARTS WITH 'Mutation.'
OPTIONAL MATCH (root)-[:RESOLVED_BY]->(res:Symbol)
OPTIONAL MATCH (res)-[:DEFINES*0..1]->(:Symbol)-[:CALLS|REFERENCES*1..2]->(m:Symbol {role: 'model'})
OPTIONAL MATCH (m)-[:MAPS_TO]->(t:Interface)
RETURN op.display AS op, f.repo AS op_repo, f.path AS op_path, op.line AS op_line,
       collect(DISTINCT [u.name, u.repo, u.path, u.line])[0..4] AS users,
       collect(DISTINCT [root.display, res.name, res.repo, res.path, res.line])[0..4] AS roots,
       collect(DISTINCT [m.name, m.repo, m.path, m.line, t.name])[0..6] AS models
LIMIT 10
"""

TRACE_OTHER = """
MATCH (i:Interface) WHERE i.id IN $ids
OPTIONAL MATCH (a)-[r1]->(i) WHERE type(r1) IN ['PRODUCES', 'CALLS_ROUTE', 'USES_FLAG', 'REGISTERS', 'DECLARES']
OPTIONAL MATCH (i)-[r2]->(b) WHERE type(r2) IN ['HANDLED_BY', 'RESOLVED_BY', 'GATED_BY']
OPTIONAL MATCH (c)-[r3]->(i) WHERE type(r3) IN ['CONSUMES', 'MAPS_TO', 'SUBSCRIBES', 'TESTS', 'GUARDED_BY', 'RENDERS']
RETURN coalesce(i.display, i.name) AS iface, i.kind AS kind,
       collect(DISTINCT [type(r1), coalesce(a.name, a.display), a.repo, a.path,
                        coalesce(r1.line, a.line)])[0..10] AS ins,
       collect(DISTINCT [type(r2), coalesce(b.name, b.display), b.repo, b.path, b.line])[0..10] AS outs,
       collect(DISTINCT [type(r3), coalesce(c.name, c.display), c.repo, c.path,
                        coalesce(r3.line, c.line)])[0..10] AS tail
"""

DIFF_FILES = """
MATCH (f:File {project: $p}) WHERE (f.repo + '/' + f.path) IN $paths RETURN f.id AS id, f.repo AS repo, f.path AS path
"""

COUNTS = """
MATCH (n {project: $p}) RETURN labels(n) AS labels, count(*) AS n
"""

EDGE_COUNT = """
MATCH ({project: $p})-[r]->() RETURN count(r) AS n
"""

# Tickets, sprints and files over time: the Note props plans.py writes, and the Ticket props tickets.py writes.

TICKET_DOCS = """
MATCH (n:Note {project: $p}) WHERE n.ticket = $key OR n.parent = $key
RETURN n.id AS id, n.kind AS kind, n.repo AS repo, n.path AS path, n.ticket AS ticket, n.parent AS parent,
       n.title AS title, n.sprint AS sprint, n.jira_type AS jira_type, n.jira_status AS jira_status, n.owner AS owner,
       n.status AS status, n.updated AS updated, n.built AS built, n.tldr AS tldr, n.summary AS summary,
       n.items_total AS items_total, n.items_done AS items_done, coalesce(n.open_items, []) AS open_items,
       coalesce(n.gaps_open, []) AS gaps_open, coalesce(n.planned_new, []) AS planned_new,
       coalesce(n.branches, []) AS branches, coalesce(n.prs, []) AS prs
"""

TICKET_FILES = """
MATCH (n:Note)-[r:PLANS|CHANGED]->(f:File) WHERE n.id IN $ids
OPTIONAL MATCH (c:Component)-[:OWNS]->(f)
RETURN DISTINCT type(r) AS rel, f.repo AS repo, f.path AS path, r.line AS line, r.change AS change, r.item AS item,
       c.name AS unit, c.kind AS unit_kind
ORDER BY rel DESC, repo, path
"""

TICKET_COMMITS = """
MATCH (t:Ticket {project: $p, name: $key})
OPTIONAL MATCH (t)-[:CHANGED]->(f:File)
RETURN t.commits AS commits, coalesce(t.authors, []) AS authors, t.last AS last, coalesce(t.repos, []) AS repos,
       count(DISTINCT f) AS files
"""

# Shared files weighted by rarity: a file every ticket touches (a lockfile, the schema) says little.
RELATED = """
OPTIONAL MATCH (:Note {project: $p, ticket: $key})-[:PLANS|CHANGED]->(a:File)
WITH collect(DISTINCT a) AS mine
OPTIONAL MATCH (:Ticket {project: $p, name: $key})-[:CHANGED]->(b:File)
WITH mine, collect(DISTINCT b) AS committed
UNWIND mine + committed AS f
WITH DISTINCT f
CALL (f) {
  MATCH (x)-[:PLANS|CHANGED]->(f) WHERE x:Note OR x:Ticket
  RETURN count(DISTINCT coalesce(x.ticket, x.name)) AS df
}
MATCH (m)-[:PLANS|CHANGED]->(f)
WHERE (m:Note AND m.ticket IS NOT NULL AND m.ticket <> $key) OR (m:Ticket AND m.name <> $key)
WITH coalesce(m.ticket, m.name) AS ticket, f, df, max(m.sprint) AS sprint
WITH ticket, count(f) AS shared, sum(1.0 / df) AS score, collect(f.repo + '/' + f.path)[..2] AS sample,
     max(sprint) AS sprint
RETURN ticket, shared, score, sprint, sample ORDER BY score DESC, shared DESC, ticket DESC LIMIT $lim
"""

HISTORY = """
MATCH (f:File {project: $p})
WHERE ($repo IS NULL OR f.repo = $repo)
  AND (f.path = $path OR f.path STARTS WITH $prefix OR ($repo IS NULL AND f.path ENDS WITH $suffix))
WITH f LIMIT 2000
MATCH (n)-[r:PLANS|CHANGED|CITES]->(f) WHERE (n:Note AND (n.ticket IS NOT NULL OR n.kind = 'plan')) OR n:Ticket
WITH coalesce(n.ticket, n.name) AS ticket,
     collect(DISTINCT CASE WHEN n:Ticket THEN 'commits' WHEN type(r) = 'PLANS' THEN 'planned'
                           WHEN type(r) = 'CHANGED' THEN 'built' ELSE 'cited' END) AS how,
     collect(DISTINCT n.sprint) AS sprints, collect(DISTINCT CASE WHEN n:Note THEN n.repo + '/' + n.path END) AS docs,
     count(DISTINCT f) AS files, max(coalesce(n.last, n.updated)) AS last, collect(DISTINCT f.repo)[0] AS repo
RETURN ticket, how, sprints, docs, files, last, repo
"""

FILE_REPO = """
MATCH (f:File {project: $p})
WHERE ($repo IS NULL OR f.repo = $repo)
  AND (f.path = $path OR f.path STARTS WITH $prefix OR ($repo IS NULL AND f.path ENDS WITH $suffix))
RETURN f.repo AS repo, f.path AS path ORDER BY size(f.path) LIMIT 2
"""

SPRINTS = """
MATCH (n:Note {project: $p}) WHERE n.sprint IS NOT NULL AND n.kind = 'plan'
RETURN n.sprint AS sprint, count(*) AS plans, sum(CASE WHEN n.built THEN 1 ELSE 0 END) AS built,
       collect(DISTINCT n.repo) AS repos
"""

SPRINT = """
MATCH (n:Note {project: $p, sprint: $sprint}) WHERE n.kind IN ['plan', 'report', 'bug', 'review']
OPTIONAL MATCH (n)-[:PLANS]->(f:File)
RETURN n.kind AS kind, coalesce(n.ticket, n.name) AS ticket, n.title AS title, n.jira_status AS jira_status,
       n.status AS status, n.built AS built, n.items_done AS items_done, n.items_total AS items_total,
       size(coalesce(n.gaps_open, [])) AS gaps, count(DISTINCT f) AS files, n.repo AS repo, n.path AS path
"""

OVERLAP = """
MATCH (n:Note {project: $p, sprint: $sprint, kind: 'plan'})-[:PLANS]->(f:File)
WITH f, collect(DISTINCT coalesce(n.ticket, n.name)) AS tickets WHERE size(tickets) > 1
RETURN f.repo AS repo, f.path AS path, tickets ORDER BY size(tickets) DESC, repo, path LIMIT 50
"""

GAPS = """
MATCH (n:Note {project: $p}) WHERE n.kind = 'plan' AND (n.sprint = $sprint OR n.ticket = $key)
RETURN coalesce(n.ticket, n.name) AS ticket, coalesce(n.gaps_open, []) AS gaps, coalesce(n.open_items, []) AS items,
       n.repo AS repo, n.path AS path
"""
