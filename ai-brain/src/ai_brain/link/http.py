"""fetch calls to routes, and HTTP clients to the external APIs they call (A8, A9)."""

from __future__ import annotations

import re
from collections import defaultdict

from . import Ctx

LOCAL_HOSTS = ("localhost", "127.0.0.1", "example.com", "example.org", "test.host", "www.w3.org", "schemas.")
ENV_HINT = re.compile(r"(URL|HOST|ENDPOINT|BASE|API|DOMAIN)")
GENERIC = {"api", "client", "service", "adapter", "http", "base", "rest", "v1", "v2", "app", "www"}


def _segments(path: str) -> list[str]:
    return [s for s in path.split("?")[0].split("/") if s]


def link(ctx: Ctx) -> None:
    _fetch_routes(ctx)
    _external(ctx)


def _fetch_routes(ctx: Ctx) -> None:
    g = ctx.g
    table = []
    for rid, _verb, path, _unit in getattr(ctx, "routes", []):
        segs = _segments(path)
        table.append((rid, segs))
    for repo, files_ in ctx.parsed.items():
        for path, f in files_.items():
            for owner, template, line in f.get("fetch", []):
                segs = _segments(template.lstrip("{}") if template.startswith("{}") else template)
                if not segs or not segs[0] or segs[0] == "{}" and len(segs) == 1:
                    continue
                best, score = None, -1
                for rid, rsegs in table:
                    if len(rsegs) != len(segs):
                        continue
                    s = 0
                    for a, b in zip(segs, rsegs, strict=True):
                        if a == b:
                            s += 2
                        elif a == "{}" or b.startswith((":", "*")) or "{}" in a:
                            s += 0
                        else:
                            s = -1
                            break
                    if s > score:
                        best, score = rid, s
                if best and score > 0:
                    g.edge("CALLS_ROUTE", ctx.owner_id(repo, path, owner), best, line=line)


def _system(host: str) -> str:
    labels = host.lower().split(".")
    if len(labels) >= 3 and labels[-2] in ("co", "com"):
        return labels[-3]
    return labels[-2] if len(labels) >= 2 else labels[0]


def _external(ctx: Ctx) -> None:
    g = ctx.g
    for repo, files_ in ctx.parsed.items():
        for path, f in files_.items():
            if not f.get("http") or "/spec/" in "/" + path or path.startswith("spec/"):
                continue
            hosts = [h for _, h, _ in f.get("urls", []) if not any(x in h for x in LOCAL_HOSTS)]
            envs = [e for _, e, _ in f.get("env", []) if ENV_HINT.search(e)]
            by_class = defaultdict(list)
            for owner, _client, line in f["http"]:
                cls = re.split(r"[#.]", owner)[0] if owner else ""
                by_class[cls].append(line)
            for cls, lines in by_class.items():
                name = _name(ctx, repo, path, cls, hosts, envs)
                if not name:
                    continue
                xid = g.iface("external_api", name)
                src = ctx.sym.get((repo, path, cls)) or g.file_id(repo, path)
                g.edge("CALLS_EXTERNAL", src, xid, line=min(lines))


def _name(ctx: Ctx, repo: str, path: str, cls: str, hosts: list[str], envs: list[str]) -> str | None:
    """A host in the file, else an env var's first word, else the adapter engine's name; never a guess."""
    own = ctx.project.own_hosts  # your own systems are not external APIs
    for host in hosts:
        system = _system(host)
        if system not in own:
            return system
    for env in envs:
        first = env.split("_")[0].lower()
        if first not in GENERIC and first not in own:
            return first
    unit = ctx.unit(repo, path)
    if unit and unit.kind == "engine":
        return _unit_word(unit.name, ctx.project.strip_prefix)
    return None


def _unit_word(name: str, prefix: str) -> str | None:
    words = [w for w in name.removeprefix(prefix).split("-") if w not in ("service", "adapter")]
    return "-".join(words) or None
