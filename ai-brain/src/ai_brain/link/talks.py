"""TALKS_TO: one edge per pair of components (or a component and an external API), derived from the detail (A11)."""

from __future__ import annotations

from collections import Counter, defaultdict

from . import Ctx


def link(ctx: Ctx) -> None:
    g = ctx.g
    unit_of = {}
    for nid, (labels, props) in g.nodes.items():
        if "Symbol" in labels or "File" in labels:
            if props.get("unit"):
                unit_of[nid] = g.comp_id(props["unit"])
        elif "Interface" in labels and props.get("kind") in ("graphql_operation",):
            u = ctx.unit(props["repo"], props["path"])
            if u:
                unit_of[nid] = g.comp_id(u.name)
        elif "Interface" in labels and props.get("kind") == "route" and props.get("owner"):
            unit_of[nid] = g.comp_id(props["owner"])
        elif "Interface" in labels and props.get("kind") == "table" and props.get("owner"):
            unit_of[nid] = g.comp_id(props["owner"])
    pairs: dict[tuple[str, str], Counter] = defaultdict(Counter)

    def add(a, b, via):
        if a and b and a != b and a in g.nodes and b in g.nodes:
            pairs[(a, b)][via] += 1

    producers, consumers = defaultdict(set), defaultdict(set)
    for (t, s, d), props in g.edges.items():
        if t == "ROUTED_TO":
            add(unit_of.get(s), d, "graphql")
        elif t in ("REFERENCES", "CALLS") and props.get("cross_engine"):
            add(unit_of.get(s), unit_of.get(d), "ruby")
        elif t == "ENQUEUES":
            add(unit_of.get(s), unit_of.get(d), "job")
        elif t == "CALLS_ROUTE":
            add(unit_of.get(s), unit_of.get(d), "http")
        elif t == "CALLS_EXTERNAL":
            add(unit_of.get(s), d, "external")
        elif t == "HOSTS":
            add(s, d, "hosts")
        elif t == "FOREIGN_KEY" and props.get("cross_schema"):
            add(unit_of.get(s), unit_of.get(d), "fk")
        elif t == "PRODUCES":
            producers[d].add(unit_of.get(s))
        elif t == "CONSUMES":
            consumers[d].add(unit_of.get(s))
        elif t == "BUILT_FROM":
            pass
    for topic, prods in sorted(producers.items()):
        for a in sorted(x for x in prods if x):
            for b in sorted(x for x in consumers.get(topic, ()) if x):
                add(a, b, "kafka")
    packages = {
        props.get("package"): nid
        for nid, (labels, props) in g.nodes.items()
        if "Component" in labels and props.get("package")
    }
    repo_comp = {
        props.get("repo"): nid
        for nid, (labels, props) in g.nodes.items()
        if "Component" in labels and props.get("kind") == "library"
    }
    for t, s, d in g.edges:
        if t == "DEPENDS_ON":
            dprops = g.nodes[d][1]
            if dprops.get("kind") == "npm_package" and dprops["name"] in packages:
                add(s, packages[dprops["name"]], "npm")
            elif dprops.get("kind") == "gem":
                lib = repo_comp.get(dprops["name"])
                if lib:
                    add(s, lib, "gem")
    for (a, b), vias in pairs.items():
        g.edge(
            "TALKS_TO",
            a,
            b,
            via=sorted(vias),
            detail=[f"{k}:{v}" for k, v in sorted(vias.items(), key=lambda kv: (-kv[1], kv[0]))],
            count=sum(vias.values()),
        )
