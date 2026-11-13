"""Kafka topics: names from the Topics constants at the locked utilities tag, producers from topic_name,
consumers from the booted ConsumerRegistry (A7, A9)."""

from __future__ import annotations

from . import Ctx
from .code import primary_def, resolve_const


def link(ctx: Ctx) -> None:
    g = ctx.g
    values: dict[str, str] = {}
    for files_ in ctx.parsed.values():
        for f in files_.values():
            if f.get("lang") == "ruby":
                for cpath, kind, value, _ in f.get("consts", []):
                    if kind == "str":
                        values[cpath] = value
    topics_by_short = {cp.rsplit("::", 1)[-1]: v for cp, v in values.items() if "::Kafka::Topics::" in cp}
    produced: set[str] = set()
    for repo, files_ in ctx.parsed.items():
        for path, f in files_.items():
            for cls, const, nesting, line in f.get("topic_assign", []):
                cpath = resolve_const(ctx, const, nesting) or const.lstrip(":")
                name = values.get(cpath) or topics_by_short.get(const.rsplit("::", 1)[-1])
                sid = ctx.sym.get((repo, path, cls))
                if name and sid:
                    g.nodes[sid][1]["role"] = "producer"
                    g.edge("PRODUCES", sid, g.iface("kafka_topic", name), line=line)
                    produced.add(name)
    consumed = set()
    rows = ctx.facts.get("consumer", [])
    for row in rows:
        rel = ctx.rel(row.get("file"))
        sid = (ctx.sym.get((rel[0], rel[1], row["consumer"])) if rel else None) or primary_def(ctx, row["consumer"])
        if sid:
            g.nodes[sid][1]["role"] = "consumer"
            g.edge("CONSUMES", sid, g.iface("kafka_topic", row["topic"]), group=row.get("group"))
            consumed.add(row["topic"])
    if not rows:  # no boot: fall back to the register_as calls as written
        for repo, files_ in ctx.parsed.items():
            for path, f in files_.items():
                for cls, value, kind, nesting, line in f.get("register_as", []):
                    name = (
                        value
                        if kind == "str"
                        else values.get(f"{cls}::{value}") or values.get(resolve_const(ctx, value, nesting) or "")
                    )
                    sid = ctx.sym.get((repo, path, cls))
                    if name and sid:
                        g.edge("CONSUMES", sid, g.iface("kafka_topic", name), line=line)
                        consumed.add(name)
    for name in consumed - produced:
        tid = g.iface_id("kafka_topic", name)
        if name.endswith((".retry", "-retry", ".dlq", "-dlq")) or "retry" in name.split(".")[-1]:
            g.nodes[tid][1]["producer"] = "retry or dlq of a consumer"
        else:
            g.nodes[tid][1]["producer"] = "producer not found"
