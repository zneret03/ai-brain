"""Mounts and routes from the booted router, with the flags their constraints check (A7)."""

from __future__ import annotations

from . import Ctx
from .code import primary_def


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
