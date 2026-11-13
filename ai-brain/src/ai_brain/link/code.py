"""Repos, components, files and symbols; Ruby constants resolved by nesting; TS imports; calls, flags, env (A6)."""

from __future__ import annotations

import json
import posixpath
import re
from collections import Counter, defaultdict

from ..model import tokens
from . import Ctx

# Method names too common to infer a call target from the name alone (decision 14).
STOP = set(
    "call new save save! update update! destroy create create! find find_by where each map select reject first last "
    "count size present? blank? to_s to_h to_a to_json as_json valid? perform run process execute build initialize "
    "send presence merge fetch key? include? any? empty? none? sum join split strip downcase upcase id name value "
    "reload exists? pluck order limit includes joins group then tap freeze dup render redirect_to head params "
    "permit require authorize log info warn error debug start stop reset clear delete remove add push pop items".split()
)


def link(ctx: Ctx) -> None:
    g, p = ctx.g, ctx.project
    g.node(p.name, "Project", name=p.name)
    for repo in p.repos + p.knowledge:
        if repo.name in ctx.shas:
            rid = g.node(
                f"{p.name}:repo:{repo.name}",
                "Repo",
                name=repo.name,
                role=repo.role,
                ref=repo.ref,
                sha=ctx.shas[repo.name],
            )
            g.edge("CONTAINS", p.name, rid)
    for u in ctx.units:
        cid = g.node(
            g.comp_id(u.name),
            "Component",
            name=u.name,
            kind=u.kind,
            repo=u.repo,
            prefix=u.prefix,
            search=tokens(u.name),
        )
        if u.deployable:
            g.node(cid, "Deployable")
    for u in ctx.units:
        if u.kind == "engine":
            app = next((a for a in ctx.units if a.repo == u.repo and a.kind == "app"), None)
            if app:
                g.edge("INCLUDES", g.comp_id(app.name), g.comp_id(u.name))
    _files_and_symbols(ctx)
    _ruby(ctx)
    _ts(ctx)
    _flags_env(ctx)


BINARY = re.compile(r"\.(png|jpe?g|gif|ico|svg|webp|pdf|woff2?|ttf|eot|mp4|webm|mov|zip|gz|lock|map|snap)$", re.I)


def _files_and_symbols(ctx: Ctx) -> None:
    g = ctx.g
    from ..extract.files import SKIP_PARTS

    for repo, listing in ctx.listing.items():  # every tracked file is a node, so notes can cite config and docs
        if repo not in ctx.parsed:
            continue
        for path, _, _ in listing:
            if (
                path not in ctx.parsed[repo]
                and not BINARY.search(path)
                and not any(s in "/" + path for s in SKIP_PARTS)
            ):
                unit = ctx.unit(repo, path)
                fid = g.node(
                    g.file_id(repo, path),
                    "File",
                    name=path.rsplit("/", 1)[-1],
                    repo=repo,
                    path=path,
                    unit=unit.name if unit else None,
                )
                g.edge("CONTAINS", f"{ctx.project.name}:repo:{repo}", fid)
                if unit:
                    g.edge("OWNS", g.comp_id(unit.name), fid)
    for repo, files_ in ctx.parsed.items():
        rid = f"{ctx.project.name}:repo:{repo}"
        for path, f in files_.items():
            unit = ctx.unit(repo, path)
            fid = g.node(
                g.file_id(repo, path),
                "File",
                name=path.rsplit("/", 1)[-1],
                repo=repo,
                path=path,
                lang=f.get("lang"),
                parse_error=bool(f.get("error")),
                unit=unit.name if unit else None,
            )
            g.edge("CONTAINS", rid, fid)
            if unit:
                g.edge("OWNS", g.comp_id(unit.name), fid)
            for qual, kind, line, params, hint in f.get("symbols", []):
                sid = g.sym_id(repo, path, qual)
                short = re.split(r"[#.]|::", qual)[-1]
                g.node(
                    sid,
                    "Symbol",
                    name=qual,
                    short=short,
                    kind=kind,
                    line=line,
                    repo=repo,
                    path=path,
                    params=params,
                    superclass=hint if f.get("lang") == "ruby" else "",
                    role=hint if f.get("lang") == "ts" else "",
                    unit=unit.name if unit else None,
                    search=tokens(short, *params),
                )
                ctx.sym[(repo, path, qual)] = sid
                parent = _parent(qual, f.get("lang"))
                psid = ctx.sym.get((repo, path, parent)) if parent else None
                g.edge("DEFINES", psid or fid, sid, line=line)
                if f.get("lang") == "ruby" and kind in ("class", "module"):
                    ctx.ruby_defs[qual].append((repo, path, sid))
                    ctx.known_cpaths.add(qual)
            if f.get("lang") == "ruby":
                for cpath, *_ in f.get("consts", []):
                    owner = cpath.rsplit("::", 1)[0] if "::" in cpath else ""
                    sid = ctx.sym.get((repo, path, owner))
                    if sid and cpath not in ctx.ruby_defs:
                        ctx.const_owner.setdefault(cpath, []).append(sid)
                        ctx.known_cpaths.add(cpath)


def _parent(qual: str, lang: str | None) -> str | None:
    if lang == "ruby":
        for sep in ("#", "."):
            if sep in qual:
                return qual.rsplit(sep, 1)[0]
        return None
    return qual.rsplit(".", 1)[0] if "." in qual else None


# ---------------------------------------------------------------- Ruby


def underscore(cpath: str) -> str:
    return "/".join(
        re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", "_", s).lower() for s in cpath.split("::")
    )


def primary_def(ctx: Ctx, cpath: str) -> str | None:
    """The definition that owns a constant: its conventional file, then Zeitwerk's, then the shortest path.
    A value constant (TLM_FLAG = ...) resolves to the class or module that assigns it."""
    defs = ctx.ruby_defs.get(cpath)
    if not defs:
        owners = ctx.const_owner.get(cpath)
        return owners[0] if owners else None
    conv = "/" + underscore(cpath) + ".rb"
    for _repo, path, sid in defs:
        if ("/" + path).endswith(conv) and "/spec/" not in "/" + path:
            return sid
    zw = ctx.zeitwerk_file.get(cpath) if hasattr(ctx, "zeitwerk_file") else None
    if zw:
        for repo, path, sid in defs:
            if (repo, path) == zw:
                return sid
    return sorted(defs, key=lambda d: ("/spec/" in "/" + d[1], len(d[1]), d[1]))[0][2]


# Ruby core, stdlib and framework namespaces. The monolith reopens several in config/initializers/ (Date, Time,
# String...); a reference to one is a reference to Ruby or a gem, never to the file that patches it.
EXTERNAL_ROOTS = set(
    "Object BasicObject Module Class Kernel Comparable Enumerable String Symbol Integer Float Numeric Rational "
    "Complex Array Hash Range Regexp Proc Method NilClass TrueClass FalseClass Struct Set Date DateTime Time "
    "BigDecimal Exception StandardError RuntimeError ArgumentError NameError NoMethodError TypeError KeyError "
    "IOError Errno File Dir IO Process Thread Mutex Queue Math Random Marshal Encoding ObjectSpace Signal GC "
    "JSON YAML Psych CSV URI Net OpenSSL Digest Base64 SecureRandom Logger Pathname Tempfile StringIO Shellwords "
    "Timeout Benchmark ERB OpenStruct Forwardable Singleton Observable Comparable Zlib Socket "
    "ActiveRecord ActiveSupport ActiveModel ActiveJob ActionController ActionDispatch ActionView ActionMailer "
    "ActionCable ActiveStorage ActionText ActionMailbox Rails Rack Arel Zeitwerk Bundler Gem GraphQL Sidekiq "
    "Karafka WaterDrop Rdkafka Pundit Flipper Faraday HTTParty RestClient RSpec Devise Warden Redis PG Concurrent "
    "Nokogiri Aws Google Sentry FactoryBot Faker Prawn Money Geocoder Paper PaperTrail Audited Kaminari".split()
)


def local_def(ctx: Ctx, cpath: str, unit: str) -> str | None:
    """A constant several units define for themselves (a spec helper, a shared mixin) resolves to the caller's own."""
    for sid in [d[2] for d in ctx.ruby_defs.get(cpath, [])] + ctx.const_owner.get(cpath, []):
        if ctx.g.nodes[sid][1].get("unit") == unit:
            return sid
    return primary_def(ctx, cpath)


def resolve_const(ctx: Ctx, name: str, nesting: list[str]) -> str | None:
    """The constant path Ruby would resolve `name` to from this lexical nesting, if it is defined in the workspace."""
    cpath = _resolve(ctx, name, nesting)
    return None if cpath is None or cpath.split("::")[0] in EXTERNAL_ROOTS else cpath


def _resolve(ctx: Ctx, name: str, nesting: list[str]) -> str | None:
    known = ctx.known_cpaths
    if name.startswith("::"):
        full = name[2:]
        return full if full in known else None
    first, _, rest = name.partition("::")
    base = None
    for scope in nesting:
        cand = f"{scope}::{first}"
        if cand in known:
            base = cand
            break
    if base is None and first in known:
        base = first
    if base is None:
        return None
    full = f"{base}::{rest}" if rest else base
    return full if full in known else None


def _ruby(ctx: Ctx) -> None:
    g = ctx.g
    ctx.zeitwerk_file = {}
    for row in ctx.facts.get("cpath", []):
        rel = ctx.rel(row.get("file"))
        if rel and rel[1].endswith(".rb"):
            ctx.zeitwerk_file[row["cpath"]] = rel
            ctx.known_cpaths.add(row["cpath"])
    # unique method names per unit, for inferred calls on a receiver of unknown class
    method_names: dict[str, Counter] = defaultdict(Counter)
    method_ids: dict[tuple[str, str], str] = {}
    for (repo, path, qual), sid in ctx.sym.items():
        if "#" in qual or "." in qual:
            node = g.nodes[sid][1]
            if node.get("kind") == "method" and path.endswith(".rb"):
                unit = node.get("unit") or repo
                short = node["short"]
                method_names[unit][short] += 1
                method_ids[(unit, short)] = sid
    for repo, files_ in ctx.parsed.items():
        for path, f in files_.items():
            if f.get("lang") != "ruby":
                continue
            unit = ctx.unit(repo, path)
            uname = unit.name if unit else repo
            for owner, name, nesting, line in f.get("refs", []):
                cpath = resolve_const(ctx, name, nesting)
                target = local_def(ctx, cpath, uname) if cpath else None
                if target:
                    src = ctx.owner_id(repo, path, owner)
                    tunit = g.nodes[target][1].get("unit")
                    g.edge("REFERENCES", src, target, line=line, cross_engine=(tunit != uname) or None)
            for owner, rtext, nesting, meth, kind, line in f.get("calls", []):
                src = ctx.owner_id(repo, path, owner)
                target = None
                inferred = None
                if kind == "const":
                    cpath = resolve_const(ctx, rtext, nesting)
                    if cpath:
                        target = _method_of(ctx, cpath, meth, singleton=True)
                elif kind == "self" and owner:
                    cls = owner.split("#")[0] if "#" in owner else owner.rsplit(".", 1)[0] if "." in owner else owner
                    singleton = "#" not in owner and "." in owner
                    target = _method_of(ctx, cls, meth, singleton=singleton)
                elif kind == "var" and meth and meth not in STOP and method_names[uname].get(meth) == 1:
                    target = method_ids.get((uname, meth))
                    inferred = True
                if target and target != src:
                    tunit = g.nodes[target][1].get("unit")
                    g.edge("CALLS", src, target, line=line, inferred=inferred, cross_engine=(tunit != uname) or None)


def _method_of(ctx: Ctx, cpath: str, meth: str, singleton: bool) -> str | None:
    for repo, path, _ in ctx.ruby_defs.get(cpath, []):
        for qual in (f"{cpath}.{meth}", f"{cpath}#{meth}") if singleton else (f"{cpath}#{meth}", f"{cpath}.{meth}"):
            sid = ctx.sym.get((repo, path, qual))
            if sid:
                return sid
    return None


# ---------------------------------------------------------------- TypeScript

EXTS = ("", ".ts", ".tsx", ".js", ".jsx", ".mjs", "/index.ts", "/index.tsx", "/index.js")


def _tsconfigs(ctx: Ctx, repo: str) -> list[tuple[str, str, list[tuple[str, str]]]]:
    """(dir, baseUrl dir, [(alias pattern, target pattern)]) for each tsconfig.json in the repo."""
    out = []
    for path in sorted(ctx.paths(repo)):
        if not path.endswith("tsconfig.json") or "node_modules/" in path:
            continue
        raw = ctx.text(repo, path) or ""
        raw = re.sub(r"(?<!:)//.*", "", raw)
        raw = re.sub(r"/\*.*?\*/", "", raw, flags=re.S)
        raw = re.sub(r",(\s*[}\]])", r"\1", raw)
        try:
            co = json.loads(raw).get("compilerOptions", {})
        except ValueError:
            continue
        base_dir = posixpath.dirname(path)
        base = posixpath.normpath(posixpath.join(base_dir, co.get("baseUrl", "."))) if co.get("baseUrl") else base_dir
        aliases = [(k, (v or [""])[0]) for k, v in (co.get("paths") or {}).items()]
        out.append((base_dir, base, aliases))
    return out


def resolve_module(ctx: Ctx, repo: str, importer: str, module: str, configs, paths: set[str]) -> str | None:
    cands = []
    if module.startswith("."):
        cands.append(posixpath.normpath(posixpath.join(posixpath.dirname(importer), module)))
    else:
        cfg = max(
            (c for c in configs if importer.startswith(c[0] + "/") or c[0] in ("", ".")),
            key=lambda c: len(c[0]),
            default=None,
        )
        if cfg:
            base_dir, base, aliases = cfg
            for alias, target in sorted(aliases, key=lambda a: -len(a[0])):
                if alias.endswith("/*") and module.startswith(alias[:-1]):
                    cands.append(posixpath.normpath(posixpath.join(base, target[:-1] + module[len(alias) - 1 :])))
                elif alias == module:
                    cands.append(posixpath.normpath(posixpath.join(base, target)))
            if base != base_dir or any(a for a in aliases):
                cands.append(posixpath.normpath(posixpath.join(base, module)))
    for cand in cands:
        if cand.startswith(".."):
            continue
        for ext in EXTS:
            if cand + ext in paths:
                return cand + ext
    return None


def _ts(ctx: Ctx) -> None:
    g = ctx.g
    for repo, files_ in ctx.parsed.items():
        ts_files = {p: f for p, f in files_.items() if f.get("lang") == "ts"}
        if not ts_files:
            continue
        configs = _tsconfigs(ctx, repo)
        paths = set(files_)
        for path, f in ts_files.items():
            names = {}
            for qual, _kind, *_ in f.get("symbols", []):
                if "." not in qual:
                    names[qual] = ctx.sym[(repo, path, qual)]
            for name, *_ in f.get("consts", []):
                names.setdefault(name, g.file_id(repo, path))
            for qual, *_ in f.get("gql", []):
                if qual:
                    names.setdefault(qual, g.file_id(repo, path))
            ctx.exports[(repo, path)] = names
        for path, f in ts_files.items():
            imap = {}
            for local, imported, module, line in f.get("imports", []):
                target = resolve_module(ctx, repo, path, module, configs, paths)
                if target:
                    imap[local] = (imported, target, module)
                    g.edge("IMPORTS", g.file_id(repo, path), g.file_id(repo, target), line=line)
                else:
                    imap[local] = (imported, "", module)
            ctx.imports[(repo, path)] = imap
        for path, f in ts_files.items():
            local_names = ctx.exports.get((repo, path), {})
            imap = ctx.imports[(repo, path)]
            for owner, callee, kind, line in f.get("calls", []):
                src = ctx.owner_id(repo, path, owner)
                target = None
                if kind == "id":
                    if callee in imap:
                        target = find_export(ctx, repo, imap[callee], callee)
                    elif callee in local_names and local_names[callee] != g.file_id(repo, path):
                        target = local_names[callee]
                elif kind == "member":
                    obj, _, prop = callee.rpartition(".")
                    if obj in imap and imap[obj][0] == "*":
                        target = find_export(ctx, repo, (prop, imap[obj][1], imap[obj][2]), prop)
                if target and target != src and g.label(target) == "Symbol":
                    g.edge("CALLS", src, target, line=line)


def find_export(ctx: Ctx, repo: str, spec: tuple[str, str, str], local: str, depth: int = 0) -> str | None:
    """The symbol (or file) an import names, following `export ... from` up to three hops."""
    imported, target, _ = spec
    if not target or depth > 3:
        return None
    names = ctx.exports.get((repo, target), {})
    want = local if imported == "default" else imported
    if want in names:
        return names[want]
    if imported == "default":
        funcs = [v for v in names.values() if ctx.g.label(v) == "Symbol"]
        if len(funcs) == 1:
            return funcs[0]
    f = ctx.parsed.get(repo, {}).get(target, {})
    for name, module, _ in f.get("exports_from", []):
        if name in (want, "*"):
            configs = _tsconfigs_cached(ctx, repo)
            nxt = resolve_module(ctx, repo, target, module, configs, set(ctx.parsed[repo]))
            hit = find_export(ctx, repo, (want, nxt or "", module), local, depth + 1)
            if hit:
                return hit
    return ctx.g.file_id(repo, target) if names or f else None


_CFG_CACHE: dict = {}


def _tsconfigs_cached(ctx: Ctx, repo: str):
    key = (id(ctx), repo)
    if key not in _CFG_CACHE:
        _CFG_CACHE[key] = _tsconfigs(ctx, repo)
    return _CFG_CACHE[key]


# ---------------------------------------------------------------- flags and env


def _flags_env(ctx: Ctx) -> None:
    g = ctx.g
    for repo, files_ in ctx.parsed.items():
        for path, f in files_.items():
            for owner, name, line in f.get("flags", []):
                fid = g.iface("flag", name)
                g.edge("USES_FLAG", ctx.owner_id(repo, path, owner), fid, line=line)
            for owner, name, line in f.get("env", []):
                if re.fullmatch(r"[A-Z][A-Z0-9_]+", name or ""):
                    eid = g.iface("env_var", name)
                    g.edge("READS_ENV", ctx.owner_id(repo, path, owner), eid, line=line)
