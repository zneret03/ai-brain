"""Cards: one per component (40 lines at most), interfaces.tsv, files.tsv (the hook's input) and architecture.md,
a Mermaid picture of TALKS_TO in at most 80 lines (A11)."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import Path

from ..model import TEST_PATH, Graph

CARD_LINES, HOOK_LINES, ARCH_LINES = 40, 10, 80
CONSUMES = {
    "SELECTS",
    "USES",
    "CONSUMES",
    "CALLS_ROUTE",
    "MAPS_TO",
    "USES_FLAG",
    "GATED_BY",
    "SUBSCRIBES",
    "GUARDED_BY",
    "RENDERS",
    "INVALIDATES",
}


class View:
    def __init__(self, g: Graph):
        self.g = g
        self.out, self.into = defaultdict(list), defaultdict(list)
        for (t, s, d), props in g.edges.items():
            self.out[s].append((t, d, props))
            self.into[d].append((t, s, props))

    def p(self, nid: str) -> dict:
        return self.g.nodes[nid][1]

    def where(self, nid: str, line: int | None = None) -> str:
        pr = self.p(nid)
        if pr.get("path"):
            return f"{pr.get('repo')}/{pr['path']}" + (f":{line or pr.get('line')}" if (line or pr.get("line")) else "")
        return ""

    def name(self, nid: str) -> str:
        pr = self.p(nid)
        return pr.get("display") or pr.get("name") or nid.rsplit(":", 1)[-1]

    def unit(self, nid: str) -> str | None:
        pr = self.p(nid)
        if pr.get("unit"):
            return pr["unit"]
        for t, s, _ in self.into.get(nid, []):
            if t == "DECLARES":
                return self.p(s).get("unit")
        return pr.get("owner")


def render(g: Graph, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.md"):
        old.unlink()
    v = View(g)
    n_cards = _components(v, out_dir)
    n_ifaces = _interfaces(v, out_dir)
    n_files = _files(v, out_dir)
    arch = _architecture(v, out_dir)
    return {"cards": n_cards, "interfaces": n_ifaces, "files": n_files, "architecture_lines": arch}


def _components(v: View, out_dir: Path) -> int:
    g, count = v.g, 0
    for cid, (labels, cp) in g.nodes.items():
        if "Component" not in labels:
            continue
        name = cp["name"]
        lines = [
            f"# {name}",
            f"{cp.get('kind')} in {cp.get('repo')}/{cp.get('prefix') or ''}"
            + (" · deployable" if "Deployable" in labels else "")
            + (f" · host {cp['host']}" if cp.get("host") else ""),
        ]
        outs = Counter(t for t, _, _ in v.out[cid])
        mounts = [v.name(d) + _gates(v, d) for t, d, _ in v.out[cid] if t == "MOUNTED_AT"]
        if mounts:
            lines.append("mounted at " + ", ".join(mounts))
        fields = [d for t, d, _ in v.out[cid] if t == "EXPOSES"]
        if fields:
            consumers = Counter()
            for f in fields:
                for t, s, _ in v.into[f]:
                    if t == "SELECTS":
                        consumers[v.p(s).get("repo")] += 1
            lines.append(
                f"graphql: {len(fields)} fields; selected by "
                + (", ".join(f"{r} ({n})" for r, n in consumers.most_common(4)) or "no operation")
            )
        sym_ids = [d for t, d, _ in v.out[cid] if t == "OWNS"]
        roles = Counter()
        produced, consumed, externals, cross = Counter(), Counter(), Counter(), Counter()
        tests = 0
        for f in sym_ids:
            if "Test" in g.nodes[f][0]:
                tests += 1
            for t, sid, _ in v.out[f]:
                if t != "DEFINES":
                    continue
                for sym in [sid] + [d for tt, d, _ in v.out[sid] if tt == "DEFINES"]:
                    role = v.p(sym).get("role")
                    if role:
                        roles[role] += 1
                    for tt, d, pr in v.out[sym]:
                        if tt == "PRODUCES":
                            produced[v.name(d)] += 1
                        elif tt == "CONSUMES":
                            consumed[v.name(d)] += 1
                        elif tt == "CALLS_EXTERNAL":
                            externals[v.name(d)] += 1
                        elif tt in ("REFERENCES", "CALLS") and pr.get("cross_engine"):
                            cross[v.p(d).get("unit")] += 1
        if roles:
            lines.append("roles: " + ", ".join(f"{r} {n}" for r, n in roles.most_common(8)))
        if produced:
            lines.append("produces: " + ", ".join(t for t, _ in produced.most_common(6)) + _more(produced, 6))
        if consumed:
            lines.append("consumes: " + ", ".join(t for t, _ in consumed.most_common(6)) + _more(consumed, 6))
        if externals:
            lines.append("external APIs: " + ", ".join(externals))
        if cross:
            lines.append("calls into: " + ", ".join(f"{u} ({n})" for u, n in cross.most_common(6)))
        talks = [(d, pr) for t, d, pr in v.out[cid] if t == "TALKS_TO"]
        heard = [(s, pr) for t, s, pr in v.into[cid] if t == "TALKS_TO"]
        if talks:
            lines.append(
                "talks to: "
                + "; ".join(
                    f"{v.name(d)} [{' '.join(pr['detail'])}]"
                    for d, pr in sorted(talks, key=lambda x: -x[1]["count"])[:6]
                )
            )
        if heard:
            lines.append(
                "heard from: "
                + "; ".join(
                    f"{v.name(s)} [{' '.join(pr['detail'])}]"
                    for s, pr in sorted(heard, key=lambda x: -x[1]["count"])[:6]
                )
            )
        owned_tables = [n for n, (lab, pr) in g.nodes.items() if pr.get("kind") == "table" and pr.get("owner") == name]
        if owned_tables:
            lines.append(
                f"tables: {len(owned_tables)} in " + ", ".join(sorted({v.p(t).get("schema") for t in owned_tables}))
            )
        lines.append(f"files {len(sym_ids)} · specs {tests} · " + ", ".join(f"{k} {n}" for k, n in outs.most_common(3)))
        (out_dir / f"{name}.md").write_text("\n".join(lines[:CARD_LINES]) + "\n")
        count += 1
    return count


def _gates(v: View, mid: str) -> str:
    flags = [v.name(d) for t, d, _ in v.out[mid] if t == "GATED_BY"]
    return f" (flag {', '.join(flags)})" if flags else ""


def _more(counter: Counter, n: int) -> str:
    return f" +{len(counter) - n} more" if len(counter) > n else ""


def _consumers(v: View, iface: str) -> list[tuple[str, str]]:
    return [(t, s) for t, s, _ in v.into[iface] if t in CONSUMES]


def _interfaces(v: View, out_dir: Path) -> int:
    rows = ["kind\tname\towner\tat\tconsumers"]
    for nid, (labels, pr) in v.g.nodes.items():
        if "Interface" not in labels:
            continue
        at = ""
        for t, d, _ in v.out[nid]:
            if t in ("RESOLVED_BY", "HANDLED_BY"):
                at = v.where(d)
                break
        if not at:
            for t, s, _ in v.into[nid]:
                if t in ("DECLARES", "PRODUCES", "MAPS_TO", "STREAMS"):
                    at = v.where(s)
                    break
        rows.append(
            "\t".join(
                [
                    pr["kind"],
                    v.name(nid),
                    str(pr.get("owner") or ""),
                    at or pr.get("path", "") or "",
                    str(len(_consumers(v, nid))),
                ]
            )
        )
    (out_dir / "interfaces.tsv").write_text("\n".join(rows) + "\n")
    return len(rows) - 1


def _files(v: View, out_dir: Path) -> int:
    """Per file with a cross-boundary link, the card the hook prints: at most 10 lines."""
    rows = []
    for fid, (labels, fp) in v.g.nodes.items():
        if "File" not in labels or "Test" in labels:
            continue
        unit = fp.get("unit")
        syms = [d for t, d, _ in v.out[fid] if t == "DEFINES"]
        syms += [d for s in list(syms) for t, d, _ in v.out[s] if t == "DEFINES"]
        lines = []
        ifaces = [(t, d) for t, d, _ in v.out[fid] if t == "DECLARES"]
        for s in syms:
            ifaces += [(t, src) for t, src, _ in v.into[s] if t in ("RESOLVED_BY", "HANDLED_BY")]
            ifaces += [(t, d) for t, d, _ in v.out[s] if t in ("PRODUCES", "CONSUMES", "MAPS_TO", "STREAMS")]
        for t, iface in dict.fromkeys(ifaces):
            pr = v.p(iface)
            if t == "DECLARES":
                routed = pr.get("routed_to")
                if not routed or routed == unit:
                    continue
                fields = [d for tt, d, _ in v.out[iface] if tt == "SELECTS"]
                lines.append(
                    f"- {pr.get('op_type', 'operation')} {v.name(iface)} → {routed}: selects {len(fields)} "
                    "fields" + (f", {len(pr['unresolved'])} not in its schema" if pr.get("unresolved") else "")
                )
                for f in fields:
                    if v.name(f).startswith(("Query.", "Mutation.")):
                        for tt, r, _ in v.out[f]:
                            if tt == "RESOLVED_BY":
                                lines.append(f"    {v.name(f)} resolved by {v.name(r)}  {v.where(r)}")
                users = [s for tt, s, _ in v.into[iface] if tt == "USES" and not _is_test(v, s)]
                if users:
                    lines.append(
                        f"    used by {v.name(users[0])}  {v.where(users[0])}"
                        + (f" and {len(users) - 1} more" if len(users) > 1 else "")
                    )
                continue
            cons = [
                (ct, c)
                for ct, c in _consumers(v, iface)
                if (v.unit(c) != unit or v.p(c).get("repo") != fp["repo"]) and not _is_test(v, c)
            ]
            if not cons:
                continue
            repos = Counter(v.p(c).get("repo") or v.p(c).get("owner") for _, c in cons)
            lines.append(
                f"- {pr['kind']} {v.name(iface)}: {len(cons)} consumers outside {unit} ("
                + ", ".join(f"{r} {n}" for r, n in repos.most_common(3))
                + ")"
            )
            for ct, c in cons[:2]:
                if v.where(c):
                    lines.append(f"    {ct.lower()} {v.name(c)}  {v.where(c)}")
        callers = Counter()
        for s in syms:
            for t, c, pr in v.into[s]:
                if t in ("CALLS", "REFERENCES") and pr.get("cross_engine"):
                    callers[v.p(c).get("unit")] += 1
        if callers:
            lines.append("- called from other engines: " + ", ".join(f"{u} ({n})" for u, n in callers.most_common(4)))
        if not lines:
            continue
        tests = {s for x in [fid, *syms] for t, s, _ in v.into[x] if t == "TESTS"}
        if tests:
            lines.append(f"- pinned by {len(tests)} specs, e.g. {v.where(sorted(tests)[0])}")
        card = [f"ai-brain: {fp['repo']}/{fp['path']} crosses a boundary:"] + lines
        if len(card) > HOOK_LINES:
            card = card[: HOOK_LINES - 1] + [f"  … ai-brain impact {fp['repo']}/{fp['path']}"]
        rows.append(f"{fp['repo']}/{fp['path']}\t" + "\\n".join(c.replace("\t", " ") for c in card))
    (out_dir / "files.tsv").write_text("\n".join(rows) + "\n")
    return len(rows)


def _is_test(v: View, nid: str) -> bool:
    path = v.p(nid).get("path") or ""
    return bool(TEST_PATH.search(path))


def _mid(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", name)


def _architecture(v: View, out_dir: Path) -> int:
    g = v.g
    edges = [(s, d, pr) for (t, s, d), pr in g.edges.items() if t == "TALKS_TO"]
    every = {n for n, (labels, pr) in g.nodes.items() if "Component" in labels or pr.get("kind") == "external_api"}
    nodes = sorted(every | {x for s, d, _ in edges for x in (s, d)}, key=lambda n: v.name(n))
    lines = ["# Architecture (generated by ai-brain from TALKS_TO; do not edit)", "", "```mermaid", "flowchart LR"]
    groups = defaultdict(list)
    for n in nodes:
        pr = v.p(n)
        group = "external" if pr.get("kind") == "external_api" else "engines" if pr.get("kind") == "engine" else "apps"
        groups[group].append(n)
    for group, members in groups.items():
        lines.append(f"  subgraph {group}")
        lines.append("    " + "; ".join(f"{_mid(v.name(n))}[{v.name(n)}]" for n in members))
        lines.append("  end")
    budget = ARCH_LINES - len(lines) - 3
    ranked = sorted(edges, key=lambda e: -e[2]["count"])
    shown = ranked[:budget]
    for s, d, pr in shown:
        lines.append(f"  {_mid(v.name(s))} -->|{' '.join(pr['detail'][:3])}| {_mid(v.name(d))}")
    lines.append("```")
    if len(ranked) > len(shown):
        lines.append(
            f"{len(ranked) - len(shown)} smaller edges left out; `ai-brain` view architecture.cypher shows all."
        )
    (out_dir / "architecture.md").write_text("\n".join(lines) + "\n")
    return len(lines)
