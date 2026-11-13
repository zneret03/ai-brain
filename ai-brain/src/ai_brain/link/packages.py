"""Gems and npm packages at their locked versions; a cloned GIT gem is BUILT_FROM its repo at the tag (A9)."""

from __future__ import annotations

import json
import re

from ..config import git_pin
from . import Ctx

SPEC = re.compile(r"^    ([\w.-]+) \(([^)]+)\)$", re.M)


def link(ctx: Ctx) -> None:
    _gems(ctx)
    _npm(ctx)


def _gems(ctx: Ctx) -> None:
    g = ctx.g
    app = next((u for u in ctx.units if u.kind == "app"), None)
    if not ctx.lock or app is None:
        return
    comp = g.comp_id(app.name)
    for name, version in SPEC.findall(ctx.lock):
        gid = g.iface("gem", name, version=version)
        g.edge("DEPENDS_ON", comp, gid, version=version)
    for repo in ctx.project.repos:
        pin = git_pin(ctx.lock, repo.name)
        if pin:
            gid = g.iface_id("gem", repo.name)
            if gid in g.nodes:
                g.edge("BUILT_FROM", gid, f"{ctx.project.name}:repo:{repo.name}", revision=pin[0], tag=pin[1])


def _yarn_versions(text: str) -> dict[str, str]:
    out = {}
    for block in re.split(r"\n\n+", text or ""):
        lines = block.strip().splitlines()
        if not lines or lines[0].startswith("#"):
            continue
        m = re.search(r'^\s+version:?\s+"?([^"\s]+)"?', block, re.M)
        if not m:
            continue
        for spec in re.split(r",\s*", lines[0].rstrip(":")):
            spec = spec.strip().strip('"')
            name = spec.rsplit("@", 1)[0] if spec.count("@") > (1 if spec.startswith("@") else 0) else spec
            out.setdefault(name, m.group(1))
    return out


def _npm(ctx: Ctx) -> None:
    g = ctx.g
    for u in ctx.units:
        if not u.deployable:
            continue
        pkg_path, lock_path = f"{u.prefix}package.json", f"{u.prefix}yarn.lock"
        try:
            pkg = json.loads(ctx.text(u.repo, pkg_path) or "{}")
        except ValueError:
            continue
        locked = _yarn_versions(ctx.text(u.repo, lock_path) or "")
        comp = g.comp_id(u.name)
        if pkg.get("name"):
            g.nodes[comp][1]["package"] = pkg["name"]
        for section in ("dependencies", "devDependencies", "peerDependencies"):
            for name, rng in (pkg.get(section) or {}).items():
                version = locked.get(name, rng)
                nid = g.iface("npm_package", name, version=version)
                g.edge("DEPENDS_ON", comp, nid, version=version, range=rng, dev=(section != "dependencies") or None)
