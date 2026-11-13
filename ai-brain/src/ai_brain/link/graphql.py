"""GraphQL: schemas, types, fields and resolvers from the boot (A7), and from the schema files of components the boot
does not cover (A12); operations, fragments, routing, SELECTS, USES and per-field skew from the documents (A8)."""

from __future__ import annotations

import importlib.util
import re
from collections import defaultdict

from graphql import (
    DocumentNode,
    FieldNode,
    FragmentDefinitionNode,
    FragmentSpreadNode,
    InterfaceTypeDefinitionNode,
    InterfaceTypeExtensionNode,
    ObjectTypeDefinitionNode,
    ObjectTypeExtensionNode,
    OperationDefinitionNode,
    TypeInfo,
    TypeInfoVisitor,
    TypeSystemDefinitionNode,
    TypeSystemExtensionNode,
    Visitor,
    build_schema,
    parse,
    print_ast,
    visit,
)

from ..model import tokens
from . import Ctx
from .code import primary_def


def link(ctx: Ctx) -> None:
    g = ctx.g
    owner_of: dict[str, str] = {}
    sdl_by_unit: dict[str, str] = {}
    for row in ctx.facts.get("schema", []):
        rel = ctx.rel(row.get("file"))
        unit = ctx.unit(*rel) if rel else None
        key = unit.name if unit else row["name"]
        owner_of[row["name"]] = key
        if (
            key not in sdl_by_unit
            or row["name"].endswith("::Schema")
            or ("::" not in row["name"] and row["name"].endswith("Schema"))  # an app's top-level <App>Schema
            or len(row["sdl"]) > len(sdl_by_unit[key])
        ):
            sdl_by_unit[key] = row["sdl"]
    ctx.graphql_docs = _documents(ctx)
    _schema_files(ctx, sdl_by_unit)
    ctx.graphql_sdl = sdl_by_unit
    for row in ctx.facts.get("field", []):
        key = owner_of.get(row["schema"], row["schema"])
        tname, fname = row["type"], row["field"]
        tid = g.iface("graphql_type", f"{key}/{tname}", display=tname, owner=key, search=tokens(tname))
        fid = g.iface(
            "graphql_field",
            f"{key}/{tname}.{fname}",
            display=f"{tname}.{fname}",
            owner=key,
            args=row.get("args") or [],
            search=tokens(tname, fname),
        )
        g.edge("DEFINES", tid, fid)
        if g.comp_id(key) in g.nodes:
            g.edge("EXPOSES", g.comp_id(key), fid)
        target = _resolver_symbol(ctx, row.get("resolver"))
        if target:
            g.edge("RESOLVED_BY", fid, target)
            role = "mutation" if tname == "Mutation" else "resolver"
            props = g.nodes[target][1]
            if not props.get("role"):
                props["role"] = role
    _operations(ctx)


SDL_FILES = (".graphql", ".graphqls", ".gql")
TYPES = (ObjectTypeDefinitionNode, ObjectTypeExtensionNode, InterfaceTypeDefinitionNode, InterfaceTypeExtensionNode)


def _documents(ctx: Ctx) -> dict[str, list[tuple[str, DocumentNode]]]:
    """Every .graphql document of the code repos, parsed: schema files and operation files alike."""
    docs: dict[str, list[tuple[str, DocumentNode]]] = defaultdict(list)
    for repo in ctx.parsed:
        for path in sorted(p for p in ctx.paths(repo) if p.endswith(SDL_FILES)):
            text = ctx.text(repo, path) or ""
            try:
                if text.strip():
                    docs[repo].append((path, parse(text)))
            except Exception as exc:  # a document graphql-core cannot parse is left out, with a note
                ctx.notes.append(f"graphql {repo}/{path}: {str(exc)[:100]}")
    return docs


def _schema_files(ctx: Ctx, sdl_by_unit: dict[str, str]) -> None:
    """The types and fields of each component's own schema files, declared at their lines. A component the boot
    already gave a schema keeps it: the running app is the authority, and its files are dumps of it."""
    g, booted, parts = ctx.g, set(sdl_by_unit), defaultdict(list)
    for repo, docs in ctx.graphql_docs.items():
        for path, doc in docs:
            unit = ctx.contract_unit(repo, path)
            sdl = [d for d in doc.definitions if isinstance(d, TypeSystemDefinitionNode | TypeSystemExtensionNode)]
            if unit is None or unit.name in booted or not sdl:
                continue
            key, fid_file = unit.name, g.file_id(repo, path)
            parts[key].append(print_ast(DocumentNode(definitions=tuple(sdl))))
            for d in (d for d in sdl if isinstance(d, TYPES)):
                tname = d.name.value
                tid = g.iface(
                    "graphql_type", f"{key}/{tname}", display=tname, owner=key, search=tokens(tname), line=_line(d.name)
                )
                g.edge("DECLARES", fid_file, tid, line=_line(d.name))
                for f in d.fields or []:
                    fname, line = f.name.value, _line(f.name)
                    fid = g.iface(
                        "graphql_field",
                        f"{key}/{tname}.{fname}",
                        display=f"{tname}.{fname}",
                        owner=key,
                        args=[a.name.value for a in f.arguments or []],
                        search=tokens(tname, fname),
                        line=line,
                    )
                    g.edge("DEFINES", tid, fid)
                    g.edge("DECLARES", fid_file, fid, line=line)
                    if g.comp_id(key) in g.nodes:
                        g.edge("EXPOSES", g.comp_id(key), fid)
    for key, texts in parts.items():
        sdl_by_unit[key] = "\n\n".join(texts)


def _line(node) -> int:
    return node.loc.start_token.line if node is not None and node.loc else 0


def _resolver_symbol(ctx: Ctx, impl: dict | None) -> str | None:
    if not impl:
        return None
    hit = ctx.symbol_at(impl)  # {file, symbol}: a resolver outside Rails
    if hit:
        return hit
    rel = ctx.rel(impl.get("file"))
    cls = impl.get("cls") or ""
    if rel and impl.get("method"):
        sid = ctx.sym.get((rel[0], rel[1], f"{cls}#{impl['method']}"))
        if sid:
            return sid
    if rel:
        sid = ctx.sym.get((rel[0], rel[1], cls))
        if sid:
            return sid
    return primary_def(ctx, cls)


def _load_router(ctx: Ctx):
    path = ctx.project.extractors.get("pilet_routing")
    if not path:  # with one schema in the workspace, every operation is its
        only = next(iter(ctx.graphql_sdl)) if len(ctx.graphql_sdl) == 1 else None
        return lambda repo: lambda op: only
    spec = importlib.util.spec_from_file_location("pilet_routing", ctx.project.dir / path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return lambda repo: mod.router(ctx, repo)


def _operations(ctx: Ctx) -> None:
    g = ctx.g
    routers = _load_router(ctx)
    routed = bool(ctx.project.extractors.get("pilet_routing"))
    schemas = {}
    for unit, sdl in ctx.graphql_sdl.items():
        try:
            schemas[unit] = build_schema(sdl, assume_valid=True)
        except Exception as exc:  # a schema graphql-core cannot build loses its SELECTS edges, not the index
            ctx.notes.append(f"schema {unit}: {str(exc)[:120]}")
    ctx.doc_ops = {}  # (repo, path, const) -> [operation ids]
    ctx.skew = []
    for repo, files_ in ctx.parsed.items():
        route = routers(repo)
        fragments: dict[str, FragmentDefinitionNode] = {}
        ops = []
        for path, f in files_.items():
            for const, text, line in f.get("gql", []):
                try:
                    doc = parse(text)
                except Exception:
                    continue
                for d in doc.definitions:
                    if isinstance(d, FragmentDefinitionNode):
                        fragments[d.name.value] = d
                    elif isinstance(d, OperationDefinitionNode) and d.name:
                        offset = d.loc.start_token.line - 1 if d.loc else 0
                        ops.append((path, const, line + offset, d))
        for path, doc in ctx.graphql_docs.get(repo, []):  # operation files, as codegen setups keep them
            for d in doc.definitions:
                if isinstance(d, FragmentDefinitionNode):
                    fragments[d.name.value] = d
                elif isinstance(d, OperationDefinitionNode) and d.name:
                    ops.append((path, "", _line(d), d))
        for path, const, line, op in ops:
            name = op.name.value
            unit = route(name)
            if unit is None and not routed:
                unit = _by_root_fields(schemas, op)
            oid = g.iface(
                "graphql_operation",
                f"{repo}/{name}",
                display=name,
                repo=repo,
                path=path,
                line=line,
                op_type=op.operation.value,
                routed_to=unit,
                search=tokens(name),
            )
            g.edge("DECLARES", g.file_id(repo, path), oid, line=line)
            ctx.doc_ops.setdefault((repo, path, const), []).append(oid)
            if unit and g.comp_id(unit) in g.nodes:
                g.edge("ROUTED_TO", oid, g.comp_id(unit))
            schema = schemas.get(unit)
            if schema is None:
                continue
            unknown = []
            for parent, field in _selected(schema, op, fragments):
                fid = g.iface_id("graphql_field", f"{unit}/{parent}.{field}") if parent else None
                if fid and fid in g.nodes:
                    g.edge("SELECTS", oid, fid)
                elif not field.startswith("__"):
                    unknown.append(f"{parent or '?'}.{field}")
            if unknown:
                g.nodes[oid][1]["unresolved"] = unknown[:20]
    _uses(ctx)
    _skew(ctx, schemas)


def _by_root_fields(schemas: dict, op: OperationDefinitionNode) -> str | None:
    """With no router and several schemas: the one schema whose root type has every field the operation starts at."""
    names = {s.name.value for s in op.selection_set.selections if isinstance(s, FieldNode)} - {"__typename"}
    hits = []
    for unit, schema in schemas.items():
        roots = {"query": schema.query_type, "mutation": schema.mutation_type, "subscription": schema.subscription_type}
        root = roots.get(op.operation.value)
        if names and root is not None and names <= set(root.fields):
            hits.append(unit)
    return hits[0] if len(hits) == 1 else None


def _selected(schema, op: OperationDefinitionNode, fragments: dict) -> list[tuple[str | None, str]]:
    needed, stack = {}, [op]
    while stack:
        node = stack.pop()
        for sub in _spreads(node):
            if sub in fragments and sub not in needed:
                needed[sub] = fragments[sub]
                stack.append(fragments[sub])
    doc = parse("\n".join(print_ast(d) for d in (op, *needed.values())))
    info = TypeInfo(schema)
    seen: list[tuple[str | None, str]] = []

    class Collect(Visitor):
        def enter_field(self, node: FieldNode, *_):
            parent = info.get_parent_type()
            seen.append((parent.name if parent else None, node.name.value))

    visit(doc, TypeInfoVisitor(info, Collect()))
    return list(dict.fromkeys(seen))


def _spreads(node) -> list[str]:
    out = []

    class Spreads(Visitor):
        def enter_fragment_spread(self, n: FragmentSpreadNode, *_):
            out.append(n.name.value)

    visit(node, Spreads())
    return out


def _uses(ctx: Ctx) -> None:
    g = ctx.g
    for repo, files_ in ctx.parsed.items():
        for path, f in files_.items():
            if f.get("lang") != "ts":
                continue
            imap = ctx.imports.get((repo, path), {})
            for owner, name, line in f.get("ident_refs", []):
                ops = ctx.doc_ops.get((repo, path, name))
                if ops is None and name in imap and imap[name][1]:
                    imported, target, _ = imap[name]
                    ops = ctx.doc_ops.get((repo, target, imported if imported not in ("default", "*") else name))
                if not ops:
                    continue
                src = ctx.owner_id(repo, path, owner)
                for oid in ops:
                    g.edge("USES", src, oid, line=line)
                    if g.label(src) == "Symbol" and not g.nodes[src][1].get("role"):
                        g.nodes[src][1]["role"] = "hook" if re.match(r"use[A-Z]", g.nodes[src][1]["short"]) else ""


def _skew(ctx: Ctx, schemas: dict) -> None:
    for (repo, path), unit in ctx.project.snapshots.items():
        engine = schemas.get(unit)
        text = ctx.text(repo, path) if repo in ctx.shas else None
        if engine is None or not text:
            continue
        try:
            snap = build_schema(text, assume_valid=True)
        except Exception:
            continue
        for tname, stype in snap.type_map.items():
            if tname.startswith("__") or not hasattr(stype, "fields"):
                continue
            etype = engine.type_map.get(tname)
            sfields = set(stype.fields)
            efields = set(getattr(etype, "fields", {}) or {})
            for fname in sorted(sfields - efields):
                ctx.skew.append((repo, path, unit, f"{tname}.{fname}", "in the snapshot, not served"))
            for fname in sorted(efields - sfields) if etype is not None else []:
                ctx.skew.append((repo, path, unit, f"{tname}.{fname}", "served, not in the snapshot"))
    ctx.skew_by_unit = defaultdict(int)
    for row in ctx.skew:
        ctx.skew_by_unit[row[2]] += 1
