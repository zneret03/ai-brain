"""Pundit policies, and the resolvers and controllers they authorize (A7). Pilet privileges are frontend.py."""

from __future__ import annotations

import re
from collections import defaultdict

from . import Ctx
from .code import primary_def

AUTH_CALLS = {"authorize", "authorize!", "policy_scope", "authorized?", "policy"}


def link(ctx: Ctx) -> None:
    g = ctx.g
    policies = set()
    for (_repo, path, qual), sid in ctx.sym.items():
        props = g.nodes[sid][1]
        if props.get("kind") == "class" and (re.search(r"(^|/)app/policies/", path) or qual.endswith("Policy")):
            props["role"] = props.get("role") or "policy"
            policies.add(sid)
    class_of = {}
    for (repo, path, qual), sid in ctx.sym.items():
        if "#" in qual or "." in qual:
            cls = re.split(r"[#.]", qual)[0]
            class_of[sid] = ctx.sym.get((repo, path, cls))
    refs = defaultdict(set)
    for t, s, d in g.edges:
        if t == "REFERENCES":
            refs[class_of.get(s) or s].add(d)
    callers = set()
    for repo, files_ in ctx.parsed.items():
        for path, f in files_.items():
            if f.get("lang") != "ruby":
                continue
            for owner, _, _, meth, kind, _ in f.get("calls", []):
                if kind == "self" and meth in AUTH_CALLS:
                    sid = ctx.sym.get((repo, path, owner))
                    callers.add(class_of.get(sid) or sid)
    roles = ("resolver", "mutation", "controller")
    for cls, targets in refs.items():
        if not cls or cls not in g.nodes or g.nodes[cls][1].get("role") not in roles:
            continue
        explicit = [t for t in targets if t in policies]
        for p in explicit:
            g.edge("AUTHORIZED_BY", cls, p)
        if not explicit and cls in callers:
            for t in targets:
                if g.nodes[t][1].get("role") == "model":
                    pol = primary_def(ctx, g.nodes[t][1]["name"] + "Policy")
                    if pol:
                        g.edge("AUTHORIZED_BY", cls, pol, inferred=True)
