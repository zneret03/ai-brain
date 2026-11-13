"""Mounts and routes from the booted router, with the flags their constraints check (A7); routes from each
component's OpenAPI and Swagger files (A12)."""

from __future__ import annotations

import re
from collections import defaultdict
from urllib.parse import urlparse

import yaml

from . import Ctx
from .code import primary_def

SPEC = re.compile(r"(^|/)(?:(?:openapi|swagger)(?:[._-][^/]*)?|[^/]+\.(?:openapi|swagger))\.(?:ya?ml|json)$", re.I)
METHODS = ("get", "put", "post", "delete", "patch", "options", "head", "trace")


def camelize(path: str) -> str:
    return "::".join("".join(w.capitalize() for w in seg.split("_")) for seg in path.split("/"))


def link(ctx: Ctx) -> None:
    g = ctx.g
    engine_unit: dict[str, str] = {}
    for row in ctx.facts.get("mount", []):
        rel = ctx.rel(row.get("root") + "/x") if row.get("root") else None
        unit = ctx.unit(*rel) if rel else None
        mid = g.iface(
            "mount",
            row["path"],
            engine=row.get("engine"),
            owner=unit.name if unit else None,
            src=[x["src"] for x in row.get("gates", [])],
        )
        if unit:
            engine_unit[row.get("engine")] = unit.name
            g.edge("MOUNTED_AT", g.comp_id(unit.name), mid)
        for gate in row.get("gates", []):
            for flag in gate.get("flags", []):
                g.edge("GATED_BY", mid, g.iface("flag", flag), src=gate["src"])
    ctx.routes = []
    for row in ctx.facts.get("route", []):
        verb = row.get("verb") or "ANY"
        handler = ctx.symbol_at(row.get("handler"))
        unit = (
            engine_unit.get(row.get("engine"))
            or (g.nodes[handler][1].get("unit") if handler else None)
            or next((u.name for u in ctx.units if u.kind == "app"), None)
        )
        rid = g.iface(
            "route",
            f"{verb} {row['path']}",
            verb=verb,
            path=row["path"],
            owner=unit,
            controller=row.get("controller"),
            action=row.get("action"),
        )
        ctx.routes.append((rid, verb, row["path"], unit))
        target = handler or _handler(ctx, row.get("controller"), row.get("action"))
        if target:
            g.edge("HANDLED_BY", rid, target)
            props = g.nodes[target][1]
            if props.get("kind") == "class" and not props.get("role"):
                props["role"] = "controller"
        for gate in row.get("gates", []):
            for flag in gate.get("flags", []):
                g.edge("GATED_BY", rid, g.iface("flag", flag), src=gate["src"])
    _openapi(ctx)


def _openapi(ctx: Ctx) -> None:
    """Each path and method of a component's OpenAPI or Swagger file: a route declared at its line and owned by the
    component, handled by the one definition there named as its operationId, inferred."""
    g, named = ctx.g, {}
    for repo in ctx.parsed:
        for path in sorted(p for p in ctx.paths(repo) if SPEC.search(p)):
            unit = ctx.contract_unit(repo, path)
            text = (ctx.text(repo, path) or "") if unit else ""
            try:
                spec = yaml.safe_load(text) if text.strip() else None
            except yaml.YAMLError as exc:  # a spec that does not parse is left out, with a note
                ctx.notes.append(f"openapi {repo}/{path}: {str(exc)[:100]}")
                continue
            if not isinstance(spec, dict) or not {"openapi", "swagger"} & spec.keys():
                continue
            if unit.name not in named:
                named[unit.name] = _named(ctx, unit.name)
            base, lines = _base_path(spec), text.splitlines()
            for route, ops in (spec.get("paths") or {}).items():
                line = _key_line(lines, str(route))
                for method, op in ops.items() if isinstance(ops, dict) else []:
                    if method.lower() not in METHODS:
                        continue
                    verb, op = method.upper(), op if isinstance(op, dict) else {}
                    full = "/" + "/".join(x.strip("/") for x in (base, str(route)) if x.strip("/"))
                    rpath = re.sub(r"\{([^}/]+)\}", r":\1", full)  # /orders/{id} as the routers write it: /orders/:id
                    rid = g.iface(
                        "route",
                        f"{verb} {rpath}",
                        verb=verb,
                        path=rpath,
                        owner=unit.name,
                        operation_id=op.get("operationId"),
                        line=line,
                    )
                    g.edge("DECLARES", g.file_id(repo, path), rid, line=line)
                    ctx.routes.append((rid, verb, rpath, unit.name))
                    ids = named[unit.name].get(str(op.get("operationId") or ""), [])
                    if len(ids) == 1:
                        g.edge("HANDLED_BY", rid, ids[0], inferred=True)


def _named(ctx: Ctx, unit: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = defaultdict(list)
    for nid, (labels, props) in ctx.g.nodes.items():
        if "Symbol" in labels and props.get("unit") == unit:
            out[props["short"]].append(nid)
    return out


def _base_path(spec: dict) -> str:
    """The path every route sits under: Swagger's basePath, or the path of OpenAPI's first server URL."""
    if spec.get("basePath"):
        return str(spec["basePath"])
    servers = spec.get("servers") or []
    url = (
        str(servers[0].get("url") or "")
        if isinstance(servers, list) and servers and isinstance(servers[0], dict)
        else ""
    )
    return url if url.startswith("/") else urlparse(url).path


def _key_line(lines: list[str], key: str) -> int:
    pattern = re.compile(rf"^\s*[\"']?{re.escape(key)}[\"']?\s*:")
    return next((i + 1 for i, text in enumerate(lines) if pattern.match(text)), 0)


def _handler(ctx: Ctx, controller: str | None, action: str | None) -> str | None:
    if not controller:
        return None
    cpath = camelize(controller) + "Controller"
    cls = primary_def(ctx, cpath)
    if cls is None:
        return None
    if action:
        for repo, path, _ in ctx.ruby_defs.get(cpath, []):
            sid = ctx.sym.get((repo, path, f"{cpath}#{action}"))
            if sid:
                ctx.g.nodes[cls][1]["role"] = "controller"
                return sid
    return cls
