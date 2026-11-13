"""Tables, columns and foreign keys from the schema files at origin/<ref>, not the database; models and their
associations from the boot (A7)."""

from __future__ import annotations

import re

from . import Ctx
from .code import primary_def

CREATE_RB = re.compile(r'^\s*create_table\s+"([\w.]+)"(.*?)^\s*end\b', re.M | re.S)
COLUMN_RB = re.compile(r'^\s*t\.\w+\s+"(\w+)"', re.M)
FK_RB = re.compile(r'^\s*add_foreign_key\s+"([\w.]+)",\s*"([\w.]+)"(?:.*?column:\s*"(\w+)")?', re.M)
CREATE_SQL = re.compile(r"^CREATE TABLE ([\w.]+) \((.*?)^\);", re.M | re.S)
FK_SQL = re.compile(
    r"^ALTER TABLE (?:ONLY )?([\w.]+)\s+ADD CONSTRAINT \w+ FOREIGN KEY \(([\w, ]+)\) REFERENCES ([\w.]+)\(", re.M
)


def _qualify(name: str, schema: str) -> str:
    return name if "." in name else f"{schema}.{name}"


def link(ctx: Ctx) -> None:
    owner_of: dict[str, str] = {}
    for repo in ctx.parsed:
        paths = sorted(ctx.paths(repo))
        for path in paths:
            if path.endswith("db/schema.rb"):
                _schema_rb(ctx, repo, path, ctx.unit(repo, path), owner_of)
        for path in paths:
            if path.endswith("db/structure.sql") and "/spec/" not in "/" + path:
                _structure_sql(ctx, repo, path, ctx.unit(repo, path), owner_of)
    ctx.table_owner = owner_of
    _models(ctx)


def _table(ctx: Ctx, name: str, unit, repo: str, path: str, columns: list[str], owner_of: dict) -> str:
    schema = name.split(".")[0]
    own = unit.name if unit else None
    if name in owner_of:  # the first file that defines a table owns it; schema.rb is read first
        return ctx.g.iface_id("table", name)
    owner_of[name] = own
    return ctx.g.iface("table", name, schema=schema, owner=own, columns=columns, repo=repo, path=path)


def _schema_rb(ctx: Ctx, repo, path, unit, owner_of) -> None:
    text = ctx.text(repo, path) or ""
    for name, body in CREATE_RB.findall(text):
        _table(ctx, _qualify(name, "public"), unit, repo, path, COLUMN_RB.findall(body), owner_of)
    for src, dst, col in FK_RB.findall(text):
        a, b = _qualify(src, "public"), _qualify(dst, "public")
        _fk(ctx, a, b, col or f"{dst.split('.')[-1].rstrip('s')}_id", path)


def _structure_sql(ctx: Ctx, repo, path, unit, owner_of) -> None:
    # An engine's structure.sql also carries a standalone copy of public: only its own schemas count.
    text = ctx.text(repo, path) or ""
    for name, body in CREATE_SQL.findall(text):
        if _qualify(name, "public").startswith("public."):
            continue
        cols = [
            m.group(1) for m in re.finditer(r'^\s+"?(\w+)"?\s+\w', body, re.M) if m.group(1).upper() != "CONSTRAINT"
        ]
        _table(ctx, _qualify(name, "public"), unit, repo, path, cols, owner_of)
    for src, cols, dst in FK_SQL.findall(text):
        if not _qualify(src, "public").startswith("public."):
            _fk(ctx, _qualify(src, "public"), _qualify(dst, "public"), cols.strip(), path)


def _fk(ctx: Ctx, a: str, b: str, column: str, path: str) -> None:
    g = ctx.g
    for name in (a, b):
        if g.iface_id("table", name) not in g.nodes:
            g.iface("table", name, schema=name.split(".")[0])
    cross = a.split(".")[0] != b.split(".")[0]
    g.edge(
        "FOREIGN_KEY",
        g.iface_id("table", a),
        g.iface_id("table", b),
        column=column,
        file=path,
        cross_schema=cross or None,
    )


def _models(ctx: Ctx) -> None:
    g = ctx.g
    models = {}
    for row in ctx.facts.get("model", []):
        rel = ctx.rel(row.get("file"))
        sid = (ctx.sym.get((rel[0], rel[1], row["class"])) if rel else None) or primary_def(ctx, row["class"])
        if not sid:
            continue
        models[row["class"]] = sid
        g.nodes[sid][1]["role"] = "model"
        table = row.get("table") or ""
        unit = g.nodes[sid][1].get("unit")
        cands = [table] if "." in table else [f"{s}.{table}" for s in _schemas_for(ctx, unit)] + [f"public.{table}"]
        for cand in cands:
            tid = g.iface_id("table", cand)
            if tid in g.nodes:
                g.edge("MAPS_TO", sid, tid)
                break
    for row in ctx.facts.get("model", []):
        src = models.get(row["class"])
        for a in row.get("assocs", []) or []:
            target = models.get((a.get("class_name") or "").lstrip(":"))
            if src and target:
                g.edge("ASSOCIATES", src, target, macro=a.get("macro"), name=a.get("name"))


def _schemas_for(ctx: Ctx, unit: str | None) -> list[str]:
    return sorted(
        {t.split(".")[0] for t, own in ctx.table_owner.items() if own == unit and not t.startswith("public.")}
    )
