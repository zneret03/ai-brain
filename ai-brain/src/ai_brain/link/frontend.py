"""Pilet wiring: pages, extensions, menus, host slots, hosts, privileges, cache wiring, ActionCable (A8)."""

from __future__ import annotations

import json
import re

from . import Ctx
from .code import find_export

CACHE_DIR = "src/graphql/cacheUpdates/"
TYPENAME = re.compile(r"__typename['\"]?\s*:\s*['\"](\w+)['\"]|typename\s*:\s*['\"](\w+)['\"]")


def link(ctx: Ctx) -> None:
    _registrations(ctx)
    _hosts(ctx)
    _privileges(ctx)
    _invalidations(ctx)
    _cache_updates(ctx)
    _cable(ctx)


def _const_value(ctx: Ctx, repo: str, path: str, name: str):
    """A top-level const's value, in this file or the file it is imported from."""
    for cname, kind, value, _ in ctx.parsed[repo][path].get("consts", []):
        if cname == name:
            return kind, value
    spec = ctx.imports.get((repo, path), {}).get(name)
    if spec and spec[1]:
        target = spec[1]
        want = spec[0] if spec[0] not in ("default", "*") else name
        for cname, kind, value, _ in ctx.parsed[repo].get(target, {}).get("consts", []):
            if cname == want:
                return kind, value
        hit = find_export(ctx, repo, spec, name)
        if hit and hit.startswith(ctx.g.file_id(repo, "")):
            tpath = hit[len(ctx.g.file_id(repo, "")) :].split("#")[0]
            for cname, kind, value, _ in ctx.parsed[repo].get(tpath, {}).get("consts", []):
                if cname == want:
                    return kind, value
    return None, None


def _slot_name(ctx: Ctx, repo: str, path: str, arg: str) -> str | None:
    if arg.startswith("str:"):
        return arg[4:]
    if arg.startswith("id:"):
        kind, value = _const_value(ctx, repo, path, arg[3:])
        return value if kind == "str" else None
    return None


def _registrations(ctx: Ctx) -> None:
    g = ctx.g
    for repo, files_ in ctx.parsed.items():
        for path, f in files_.items():
            unit = ctx.unit(repo, path)
            if not unit or "/__tests__/" in "/" + path or re.search(r"\.test\.[jt]sx?$", path):
                continue
            for kind, arg, component, line in f.get("registrations", []):
                comp = g.comp_id(unit.name)
                if kind == "registerPage":
                    page = (
                        arg.split(":", 2)[2] if arg.startswith("call:") else arg[4:] if arg.startswith("str:") else None
                    )
                    if page is None:
                        continue
                    pid = g.iface(
                        "pilet_page",
                        f"{repo}:{page}",
                        display=page,
                        repo=repo,
                        path=path,
                        line=line,
                        component=component,
                    )
                    g.edge("REGISTERS", comp, pid, line=line)
                    target = ctx.sym.get((repo, path, component))
                    if target is None and component:
                        spec = ctx.imports.get((repo, path), {}).get(component)
                        target = find_export(ctx, repo, spec, component) if spec else None
                    if target and g.label(target) == "Symbol":
                        g.nodes[target][1]["role"] = "page"
                        g.edge("RENDERS", pid, target)
                elif kind in ("registerExtension", "registerTile", "registerModal"):
                    name = _slot_name(ctx, repo, path, arg)
                    if name:
                        g.edge("REGISTERS", comp, g.iface("extension_slot", name), line=line, file=path)
                elif kind == "registerMenu":
                    g.edge("REGISTERS", comp, g.iface("extension_slot", "menu"), line=line, file=path)
            for owner, arg, line in f.get("slots", []):
                if "/__tests__/" in "/" + path or re.search(r"\.test\.[jt]sx?$", path):
                    continue
                name = _slot_name(ctx, repo, path, arg)
                if name:
                    g.edge("RENDERS", ctx.owner_id(repo, path, owner), g.iface("extension_slot", name), line=line)


def _package(ctx: Ctx, repo: str, path: str = "package.json") -> dict:
    try:
        return json.loads(ctx.text(repo, path) or "{}")
    except ValueError:
        return {}


def _hosts(ctx: Ctx) -> None:
    g = ctx.g
    shells = {}
    for u in ctx.units:
        if u.kind == "shell":
            name = _package(ctx, u.repo).get("name")
            if name:
                shells[name] = u.name
    app = next((u for u in ctx.units if u.kind == "app"), None)
    embed = app is not None and any(
        p.startswith(f"{app.prefix}app/javascript/piral-embed/") for p in ctx.paths(app.repo)
    )
    for u in ctx.units:
        if u.kind != "pilet":
            continue
        host = (_package(ctx, u.repo).get("piral") or {}).get("name")
        comp = g.comp_id(u.name)
        g.nodes[comp][1]["host"] = host or "unknown"
        if host in shells:
            g.edge("HOSTS", g.comp_id(shells[host]), comp, via="package.json piral.name")
            if embed:
                g.edge("HOSTS", g.comp_id(app.name), comp, via="app/javascript/piral-embed")


def _privileges(ctx: Ctx) -> None:
    g = ctx.g
    for repo, files_ in ctx.parsed.items():
        for path, f in files_.items():
            for owner, expr, line in f.get("privilege_checks", []):
                obj, _, key = expr.partition(".")
                if not key:
                    continue
                kind, value = _const_value(ctx, repo, path, obj)
                if kind != "object" or key not in value:
                    continue
                pid = g.iface("privilege", value[key], key=key)
                g.edge("GUARDED_BY", ctx.owner_id(repo, path, owner), pid, line=line)
                cls = ctx.ruby_defs.get(value[key])
                if cls:
                    g.edge("REFERENCES", pid, cls[0][2])


def _mutations_used(ctx: Ctx, src: str) -> list[str]:
    g = ctx.g
    return [dst for (t, s, dst) in ctx.uses_index.get(src, []) if g.nodes[dst][1].get("op_type") == "mutation"]


def _index_uses(ctx: Ctx) -> None:
    ctx.uses_index = {}
    for t, s, d in ctx.g.edges:
        if t == "USES":
            ctx.uses_index.setdefault(s, []).append((t, s, d))


def _invalidations(ctx: Ctx) -> None:
    g = ctx.g
    _index_uses(ctx)
    for repo, files_ in ctx.parsed.items():
        consts = {}
        for path, f in files_.items():
            if path.startswith(CACHE_DIR) or "/cacheUpdates/" in path:
                for name, kind, value, _ in f.get("consts", []):
                    if kind == "array" and name.endswith("_INVALIDATES"):
                        consts[(path, name)] = value

        def expand(path, name, depth=0, consts=consts):
            out = []
            for item in consts.get((path, name), []):
                if item.startswith("...") and depth < 5:
                    out.extend(expand(path, item[3:], depth + 1, consts))
                else:
                    out.append(item)
            return out

        if not consts:
            continue
        for path, f in files_.items():
            imap = ctx.imports.get((repo, path), {})
            file_mutations = None
            for owner, name, line in f.get("ident_refs", []):
                spec = imap.get(name)
                key = (spec[1], spec[0]) if spec and spec[1] else (path, name)
                if key not in consts:
                    continue
                src = ctx.owner_id(repo, path, owner)
                muts = _mutations_used(ctx, src)
                if not muts:
                    if file_mutations is None:
                        file_mutations = [
                            d
                            for s in {ctx.owner_id(repo, path, o) for o, *_ in f.get("ident_refs", [])}
                            for d in _mutations_used(ctx, s)
                        ]
                    muts = file_mutations
                for op_name in expand(*key):
                    oid = g.iface_id("graphql_operation", f"{repo}/{op_name}")
                    for mut in muts:
                        g.edge("INVALIDATES", mut, oid, via=key[1], line=line)


def _cache_updates(ctx: Ctx) -> None:
    g = ctx.g
    for repo, files_ in ctx.parsed.items():
        helpers = {}
        for path in files_:
            if "/cacheUpdates/" in "/" + path and not path.endswith("invalidations.ts") and ".test." not in path:
                text = ctx.text(repo, path) or ""
                types = {a or b for a, b in TYPENAME.findall(text)}
                if types:
                    helpers[path] = types
        if not helpers:
            continue
        for (t, s, d), _ in list(g.edges.items()):
            if t != "CALLS" or not d.startswith(g.file_id(repo, "")):
                continue
            tpath = d[len(g.file_id(repo, "")) :].split("#")[0]
            if tpath not in helpers:
                continue
            for mut in _mutations_used(ctx, s):
                unit = g.nodes[mut][1].get("routed_to")
                for tname in sorted(helpers[tpath]):
                    tid = g.iface_id("graphql_type", f"{unit}/{tname}")
                    g.edge("UPDATES_CACHE", mut, tid, via=tpath)


def _cable(ctx: Ctx) -> None:
    g = ctx.g
    for row in ctx.facts.get("channel", []):
        rel = ctx.rel(row.get("file"))
        cid = g.iface("channel", row["class"])
        sid = ctx.sym.get((rel[0], rel[1], row["class"])) if rel else None
        if sid:
            g.nodes[sid][1]["role"] = "channel"
            g.edge("STREAMS", sid, cid)
    for repo, files_ in ctx.parsed.items():
        for path, f in files_.items():
            for owner, channel, line in f.get("cable", []):
                g.edge("SUBSCRIBES", ctx.owner_id(repo, path, owner), g.iface("channel", channel), line=line)
