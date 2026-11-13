"""Schema and writes. A write is the delta between the new graph and the last one written, in UNWIND batches,
so a second index with no changes writes nothing (A4, A6)."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import defaultdict

from ..config import VAR
from ..model import LABELS, Graph

BATCH = 5000
OPTIONAL = {"File": "Test", "Component": "Deployable"}  # second labels a node can gain or lose


def schema_apply(session) -> list[str]:
    statements = [
        f"CREATE CONSTRAINT {lab.lower()}_id IF NOT EXISTS FOR (n:{lab}) REQUIRE n.id IS UNIQUE"
        for lab in LABELS
        if lab not in ("Test", "Deployable")
    ]
    statements += [
        f"CREATE INDEX {lab.lower()}_project IF NOT EXISTS FOR (n:{lab}) ON (n.project)"
        for lab in ("File", "Symbol", "Interface", "Note", "Component")
    ]
    statements += [
        "CREATE INDEX symbol_short IF NOT EXISTS FOR (n:Symbol) ON (n.short)",
        "CREATE INDEX symbol_name IF NOT EXISTS FOR (n:Symbol) ON (n.name)",
        "CREATE INDEX interface_display IF NOT EXISTS FOR (n:Interface) ON (n.display)",
        "CREATE INDEX interface_name IF NOT EXISTS FOR (n:Interface) ON (n.name)",
        "CREATE INDEX file_path IF NOT EXISTS FOR (n:File) ON (n.path)",
        "CREATE FULLTEXT INDEX symbol_search IF NOT EXISTS FOR (n:Symbol) ON EACH [n.search]",
        "CREATE FULLTEXT INDEX interface_search IF NOT EXISTS FOR (n:Interface) ON EACH [n.search]",
    ]
    for s in statements:
        session.run(s).consume()
    return statements


def _clean(props: dict) -> dict:
    out = {}
    for k, v in props.items():
        if v is None or v == [] or isinstance(v, dict):
            continue
        if isinstance(v, list):
            v = [str(x) for x in v]
        out[k] = v
    return out


def _hash(obj) -> str:
    return hashlib.sha1(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]


def _state(project: str) -> sqlite3.Connection:
    path = VAR / "state" / f"{project}.sqlite"
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE IF NOT EXISTS nodes (id TEXT PRIMARY KEY, label TEXT, h TEXT)")
    db.execute(
        "CREATE TABLE IF NOT EXISTS edges (k TEXT PRIMARY KEY, t TEXT, s TEXT, d TEXT, sl TEXT, dl TEXT, h TEXT)"
    )
    return db


def reset_state(project: str) -> None:
    db = _state(project)
    db.execute("DELETE FROM nodes")
    db.execute("DELETE FROM edges")
    db.commit()
    db.close()


def wipe(session, project: str) -> None:
    session.run(
        "MATCH (n {project: $p}) CALL (n) { DETACH DELETE n } IN TRANSACTIONS OF 10000 ROWS", p=project
    ).consume()
    reset_state(project)


def write(driver, g: Graph, log=print) -> dict:
    """Apply the delta; returns counts of what was written."""
    db = _state(g.project)
    old_nodes = {i: (lab, h) for i, lab, h in db.execute("SELECT id, label, h FROM nodes")}
    old_edges = {k: (t, s, d, sl, dl, h) for k, t, s, d, sl, dl, h in db.execute("SELECT * FROM edges")}
    new_nodes, node_rows = {}, defaultdict(list)
    for nid, (labels, props) in g.nodes.items():
        primary = min(labels, key=LABELS.index)
        if primary == "Deployable":
            primary = "Component"
        extra = tuple(sorted(lab for lab in labels if lab != primary))
        clean = _clean(props)
        clean["id"] = nid
        h = _hash([extra, clean])
        new_nodes[nid] = (primary, h)
        if old_nodes.get(nid) != (primary, h):
            node_rows[(primary, extra)].append({"id": nid, "props": clean})
    new_edges, edge_rows = {}, defaultdict(list)
    labels_of = {nid: lab for nid, (lab, _) in new_nodes.items()}
    for (t, s, d), props in g.edges.items():
        clean = _clean(props)
        h = _hash(clean)
        k = f"{t}|{s}|{d}"
        sl, dl = labels_of[s], labels_of[d]
        new_edges[k] = (t, s, d, sl, dl, h)
        if old_edges.get(k, (None,) * 6)[5] != h:
            edge_rows[(t, sl, dl)].append({"s": s, "d": d, "props": clean})
    gone_edges = defaultdict(list)
    for k, (t, s, d, sl, dl, _) in old_edges.items():
        if k not in new_edges:
            gone_edges[(t, sl, dl)].append({"s": s, "d": d})
    gone_nodes = defaultdict(list)
    for nid, (lab, _) in old_nodes.items():
        if nid not in new_nodes:
            gone_nodes[lab].append(nid)
    counts = {
        "nodes_written": sum(map(len, node_rows.values())),
        "edges_written": sum(map(len, edge_rows.values())),
        "nodes_deleted": sum(map(len, gone_nodes.values())),
        "edges_deleted": sum(map(len, gone_edges.values())),
    }
    if not any(counts.values()):  # nothing moved: the stored state already matches
        db.close()
        return counts
    with driver.session() as session:
        for (t, sl, dl), rows in gone_edges.items():
            _batched(
                session, f"UNWIND $rows AS r MATCH (a:{sl} {{id: r.s}})-[e:{t}]->(b:{dl} {{id: r.d}}) DELETE e", rows
            )
        for lab, ids in gone_nodes.items():
            _batched(session, f"UNWIND $rows AS i MATCH (n:{lab} {{id: i}}) DETACH DELETE n", ids)
        for (primary, extra), rows in node_rows.items():
            q = f"UNWIND $rows AS r MERGE (n:{primary} {{id: r.id}}) SET n = r.props"
            opt = OPTIONAL.get(primary)
            if opt:
                q += f" SET n:{opt}" if opt in extra else f" REMOVE n:{opt}"
            _batched(session, q, rows)
        for (t, sl, dl), rows in edge_rows.items():
            _batched(
                session,
                f"UNWIND $rows AS r MATCH (a:{sl} {{id: r.s}}) MATCH (b:{dl} {{id: r.d}}) "
                f"MERGE (a)-[e:{t}]->(b) SET e = r.props",
                rows,
            )
    db.execute("DELETE FROM nodes")
    db.executemany("INSERT INTO nodes VALUES (?, ?, ?)", [(i, lab, h) for i, (lab, h) in new_nodes.items()])
    db.execute("DELETE FROM edges")
    db.executemany("INSERT INTO edges VALUES (?, ?, ?, ?, ?, ?, ?)", [(k, *v) for k, v in new_edges.items()])
    db.commit()
    db.close()
    return counts


def _batched(session, query: str, rows: list) -> None:
    for i in range(0, len(rows), BATCH):
        chunk = rows[i : i + BATCH]
        session.execute_write(lambda tx, c=chunk: tx.run(query, rows=c).consume())
