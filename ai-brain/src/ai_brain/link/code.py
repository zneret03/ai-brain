"""Repos, components, files and symbols; Ruby constants resolved by nesting; TS imports; calls, flags, env (A6)."""

from __future__ import annotations

import json
import posixpath
import re
from collections import Counter, defaultdict

from ..extract import languages
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
    _generic(ctx)
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


# ---------------------------------------------------------------- every other language (A3)

# Names too common to infer a call target from the name alone, in any language, compared lowercased: Go's err.Error()
# and t.Error() are not the repo's own Error method. The Ruby list is part of it.
COMMON = STOP | set(
    "get set put post call new init run main start stop open close read write send map filter reduce each apply "
    "update create save load find fetch print println printf len str int list dict append extend format join split "
    "strip push pop add remove clear copy keys values items log info warn error debug assert raise super to_string "
    "from into unwrap expect clone iter collect is_empty ok err some none test string less swap equals hashcode "
    "tostring compareto hash next size length flush fatal fatalf errorf logf sprintf".split()
)
SELF = {"self", "this", "cls", "Self", "$this"}
TYPES = {"class", "module", "interface", "struct", "trait", "enum", "type", "object", "union", "protocol", "record"}
JVM = (".java", ".kt", ".kts")


def _generic(ctx: Ctx) -> None:
    for repo, files_ in ctx.parsed.items():
        own = {p: f for p, f in files_.items() if f.get("lang") not in ("ruby", "ts", "?", None)}
        if own:
            _Langs(ctx, repo, own).link()


class _Langs:
    """One repo's files in the other languages: the files each import names, and the definition a name reaches. A
    name with no import or local definition links only when the component defines it once, marked inferred."""

    def __init__(self, ctx: Ctx, repo: str, own: dict[str, dict]):
        self.ctx, self.repo, self.own = ctx, repo, own
        self.short: dict[str, dict[str, list[str]]] = defaultdict(dict)  # path -> short name -> symbol ids
        self.in_unit: dict[str, dict[str, list[str]]] = defaultdict(dict)  # component -> short name -> ids
        self.modules: dict[str, list[tuple[str, str]]] = defaultdict(list)  # module name -> (path, id)
        self.py: dict[str, list[tuple[str, str]]] = defaultdict(list)  # "a/b" -> (a/b.py or a/b/__init__.py, prefix)
        self.jvm: dict[str, list[str]] = defaultdict(list)  # "a/b/C" -> a/b/C.java
        self.by_dir: dict[str, list[str]] = defaultdict(list)
        for path, f in own.items():
            self.by_dir[posixpath.dirname(path)].append(path)
            for qual, kind, *_ in f.get("symbols", []):
                sid = ctx.sym[(repo, path, qual)]
                for index in (self.short[path], self.in_unit[self._unit(path) or ""]):
                    ids = index.setdefault(qual.rsplit(".", 1)[-1], [])
                    if sid not in ids:
                        ids.append(sid)
                if kind == "module":
                    self.modules[qual].append((path, sid))
            stem, ext = posixpath.splitext(path)
            parts = stem.split("/")
            if ext == ".py":
                parts = parts[:-1] if parts[-1] == "__init__" else parts
                for i in range(len(parts)):
                    self.py["/".join(parts[i:])].append((path, "/".join(parts[:i])))
            elif ext in JVM:
                for i in range(len(parts)):
                    self.jvm["/".join(parts[i:])].append(path)
        self.gomods, self.crates = self._manifests()

    def _unit(self, path: str) -> str | None:
        unit = self.ctx.unit(self.repo, path)
        return unit.name if unit else None

    def _manifests(self) -> tuple[list[tuple[str, str]], list[tuple[str, str, str]]]:
        """(module path, folder) from each go.mod; (folder, src folder, crate name) from each Cargo.toml."""
        from ..extract.files import SKIP_PARTS

        langs = {f.get("lang") for f in self.own.values()}
        gomods, crates = [], []
        for path in sorted(self.ctx.paths(self.repo)):
            name, folder = path.rsplit("/", 1)[-1], posixpath.dirname(path)
            if any(s in "/" + path for s in SKIP_PARTS):
                continue
            if name == "go.mod" and "go" in langs:
                m = re.search(r"^module\s+(\S+)", self.ctx.text(self.repo, path) or "", re.M)
                if m:
                    gomods.append((m.group(1), folder))
            elif name == "Cargo.toml" and "rust" in langs:
                text = self.ctx.text(self.repo, path) or ""
                m = re.search(r'^\[package\][^\[]*?^name\s*=\s*"([^"]+)"', text, re.M | re.S)
                src = "/".join(x for x in (folder, "src") if x)
                crates.append((folder, src, m.group(1).replace("-", "_") if m else ""))
        return sorted(gomods, key=lambda m: -len(m[0])), sorted(crates, key=lambda c: -len(c[0]))

    def link(self) -> None:
        ctx, g, repo = self.ctx, self.ctx.g, self.repo
        for path, f in self.own.items():
            uname, lang = self._unit(path), f["lang"]
            imap: dict[str, list[tuple[str, str, list[str]]]] = {}
            for local, imported, module, line in f.get("imports", []):
                targets = self.resolve(lang, path, module, imported)
                for target in targets:
                    g.edge("IMPORTS", g.file_id(repo, path), g.file_id(repo, target), line=line)
                imap.setdefault(local, []).append((imported, module, targets))
            ctx.imports[(repo, path)] = {
                local: (rows[0][0], next((t for *_, ts_ in rows for t in ts_), ""), rows[0][1])
                for local, rows in imap.items()
            }
            for owner, name, recv, line in f.get("calls", []):
                self._edge("CALLS", path, uname, owner, self.call(lang, path, uname, owner, name, recv, imap), line)
            for owner, name, recv, line in f.get("refs", []):
                self._edge("REFERENCES", path, uname, owner, self.ref(lang, path, uname, name, recv, imap), line)

    def _edge(self, etype: str, path: str, uname: str | None, owner: str, hit, line: int) -> None:
        if not hit:
            return
        target, inferred = hit
        src = self.ctx.owner_id(self.repo, path, owner)
        if target != src:
            tunit = self.ctx.g.nodes[target][1].get("unit")
            self.ctx.g.edge(etype, src, target, line=line, inferred=inferred, cross_engine=(tunit != uname) or None)

    # ------------------------------------------------ imports: the files a statement names, [] when from outside

    def resolve(self, lang: str, importer: str, module: str, imported: str) -> list[str]:
        if lang == "python":
            return self._python(importer, module, imported)
        if lang == "go":
            return self._go(module)
        if lang == "rust":
            return self._rust(importer, module, imported)
        if lang == "elixir":
            return self._best([p for p, _ in self.modules.get(module, [])], importer)
        if lang in ("java", "kotlin"):
            return self._jvm(importer, module, imported)
        return []

    def _best(self, cands: list[str], importer: str) -> list[str]:
        """The candidate in the importer's component, then the shortest path."""
        unit = self._unit(importer)
        return [min(dict.fromkeys(cands), key=lambda p: (self._unit(p) != unit, len(p), p))] if cands else []

    def _python(self, importer: str, module: str, imported: str) -> list[str]:
        sub = imported not in ("*", "")
        if module.startswith("."):
            dots = len(module) - len(module.lstrip("."))
            base = posixpath.dirname(importer)
            for _ in range(dots - 1):
                base = posixpath.dirname(base)
            rest = [x for x in module[dots:].split(".") if x]
            stem = "/".join([x for x in (base,) if x] + rest)
            cands = []
            if sub:
                s = "/".join(x for x in (stem, imported) if x)
                cands += [f"{s}.py", f"{s}/__init__.py"]
            if rest:
                cands.append(f"{stem}.py")
            cands.append("/".join(x for x in (stem, "__init__.py") if x))
            return [c for c in cands if c in self.own][:1]
        key = module.replace(".", "/")
        for k in ([f"{key}/{imported}"] if sub else []) + [key]:
            # a match must start at an import root: `import json` is not utils/json.py inside package utils
            hits = [p for p, prefix in self.py.get(k, []) if not prefix or f"{prefix}/__init__.py" not in self.own]
            if hits:
                return self._best(hits, importer)
        return []

    def _go(self, module: str) -> list[str]:
        for mod, folder in self.gomods:
            if module == mod or module.startswith(mod + "/"):
                pkg = "/".join(x for x in (folder, module[len(mod) :].strip("/")) if x)
                return sorted(p for p in self.by_dir.get(pkg, []) if p.endswith(".go") and not p.endswith("_test.go"))
        return []

    def _rust(self, importer: str, module: str, imported: str) -> list[str]:
        crate = next((c for c in self.crates if not c[0] or importer.startswith(c[0] + "/")), None)
        parts = [x for x in module.split("::") if x]
        if not parts and imported not in ("*", ""):  # use billing; use a::{self}
            parts, imported = [imported], "*"
        if crate is None or not parts:
            return []
        root = crate[1]
        if parts[0] == "crate":
            base, parts = root, parts[1:]
        elif parts[0] in ("self", "super"):
            base = self._rs_dir(importer)
            while parts and parts[0] in ("self", "super"):
                if parts.pop(0) == "super":
                    base = posixpath.dirname(base)
        else:
            other = next((c[1] for c in self.crates if c[2] == parts[0]), None)
            if other is None:
                return []  # std, or a crate from outside this repo
            root, base, parts = other, other, parts[1:]
        for seq in ([parts + [imported]] if imported not in ("*", "") else []) + [parts]:
            hit = self._rs_file(base, seq, root)
            if hit:
                return [hit]
        return []

    @staticmethod
    def _rs_dir(path: str) -> str:
        """The folder holding a module's children: src for src/lib.rs, src/a for src/a.rs and src/a/mod.rs."""
        return posixpath.dirname(path) if path.rsplit("/", 1)[-1] in ("lib.rs", "main.rs", "mod.rs") else path[:-3]

    def _rs_file(self, base: str, seq: list[str], root: str) -> str | None:
        if seq:
            stem = "/".join([base, *seq])
            cands = [f"{stem}.rs", f"{stem}/mod.rs"]
        else:
            cands = [f"{base}/lib.rs", f"{base}/main.rs"] if base == root else [f"{base}.rs", f"{base}/mod.rs"]
        return next((c for c in cands if c in self.own), None)

    def _jvm(self, importer: str, module: str, imported: str) -> list[str]:
        folder = module.replace(".", "/")
        if imported in ("*", ""):
            return sorted(
                p for d, ps in self.by_dir.items() if ("/" + d).endswith("/" + folder) for p in ps if p.endswith(JVM)
            )
        hit = self._best(self.jvm.get(f"{folder}/{imported}" if folder else imported, []), importer)
        return hit or (self._best(self.jvm.get(folder, []), importer) if folder else [])  # import static a.B.m

    # ------------------------------------------------ names: (symbol id, inferred) or None

    def call(self, lang: str, path: str, uname: str | None, owner: str, name: str, recv: str, imap: dict):
        cls = owner.rsplit(".", 1)[0] if "." in owner else ""
        if recv in SELF:
            return self._local(path, name, cls or owner)
        calls_scope, types_scope = languages.SCOPE.get(lang, ("component", "component"))
        guess = None if lang in languages.DYNAMIC else self._infer(uname, name)
        if recv == "?":
            return guess
        if recv:
            rows = imap.get(recv) or imap.get(re.split(r"\.|::", recv, maxsplit=1)[0])
            if rows is not None:  # an imported receiver resolves in its files or stays unlinked, never guessed
                for imported, module, targets in rows:
                    quals = [f"{imported}.{name}"] if imported != "*" else []
                    hit = self._in(targets, name, quals + [f"{module}.{name}"])
                    if hit:
                        return hit
                return None
            if recv in self.modules:
                return self._in([p for p, _ in self.modules[recv]], name, [f"{recv}.{name}"])
            if recv[:1].isupper():
                files, inferred = self._type_files(path, uname, recv, types_scope)
                hit = self._in(files, name, [f"{recv}.{name}"])
                return (hit[0], inferred) if hit else None
            return guess
        rows = imap.get(name)
        if rows is not None:
            for imported, _module, targets in rows:
                want = name if imported == "*" else imported
                hit = self._in(targets, want, [want])
                if hit:
                    return hit
            return None
        hit = self._local(path, name, cls)
        if hit:
            return hit
        for _imported, module, targets in imap.get("*", []):  # only the imported module's own top-level names
            quals = [f"{module}.{name}"] + ([] if module in self.modules else [name])  # an Elixir defimpl's is not
            hit = self._in(targets, name, quals, loose=False)
            if hit:
                return hit
        if calls_scope == "folder":
            ids = [sid for p in self.by_dir.get(posixpath.dirname(path), []) for sid in self.short[p].get(name, [])]
            return (ids[0], None) if len(ids) == 1 else None
        return None if calls_scope == "file" else guess

    def ref(self, lang: str, path: str, uname: str | None, name: str, recv: str, imap: dict):
        if recv and recv in imap:  # pkg.Type
            return self._types([t for *_, targets in imap[recv] for t in targets], name)
        if name in self.modules:  # a module named in full
            return self.modules[name][0][1], None
        rows = imap.get(name)
        if rows is not None:
            for imported, module, targets in rows:
                full = module if imported == "*" else imported
                hit = self._types(targets, re.split(r"\.|::", full)[-1], full)
                if hit:
                    return hit
            return None
        files, inferred = self._type_files(path, uname, name, languages.SCOPE.get(lang, ("", "component"))[1])
        hit = self._types(files, name)
        return (hit[0], inferred) if hit else None

    def _local(self, path: str, name: str, cls: str = ""):
        """A definition in this file: the one in `cls`, then a top-level one, then any of that name."""
        for qual in ([f"{cls}.{name}"] if cls else []) + [name]:
            sid = self.ctx.sym.get((self.repo, path, qual))
            if sid:
                return sid, None
        ids = self.short.get(path, {}).get(name)
        return (ids[0], None) if ids else None

    def _in(self, paths: list[str], name: str, quals=(), loose: bool = True):
        """A definition in these files: one of `quals` first, then, when loose, any definition of that name."""
        for qual in quals:
            for p in paths:
                sid = self.ctx.sym.get((self.repo, p, qual))
                if sid:
                    return sid, None
        for p in paths if loose else []:
            ids = self.short.get(p, {}).get(name)
            if ids:
                return ids[0], None
        return None

    def _types(self, paths: list[str], name: str, full: str = ""):
        for p in paths:
            sid = self.ctx.sym.get((self.repo, p, full)) if full else None
            if sid and self._kind(sid) in TYPES:
                return sid, None
            for sid in self.short.get(p, {}).get(name, []):
                if self._kind(sid) in TYPES:
                    return sid, None
        return None

    def _type_files(self, path: str, uname: str | None, cls: str, scope: str) -> tuple[list[str], bool | None]:
        """The files defining a class or module named `cls`: this file, then as far as the language's scope reaches,
        its folder (a Java package) and the one file in the component that does, inferred."""
        if self._types([path], cls):
            return [path], None
        if scope == "file":
            return [], None
        same = [p for p in self.by_dir.get(posixpath.dirname(path), []) if self._types([p], cls)]
        if same or scope == "folder":
            return same[:1], None
        ids = [sid for sid in self.in_unit[uname or ""].get(cls, []) if self._kind(sid) in TYPES]
        return ([self.ctx.g.nodes[ids[0]][1]["path"]], True) if len(ids) == 1 else ([], None)

    def _infer(self, uname: str | None, name: str):
        ids = self.in_unit[uname or ""].get(name, [])
        return (ids[0], True) if len(ids) == 1 and len(name) > 2 and name.lower() not in COMMON else None

    def _kind(self, sid: str) -> str | None:
        return self.ctx.g.nodes[sid][1].get("kind")


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
