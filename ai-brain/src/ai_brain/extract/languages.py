"""Which reader parses a file (A1): the Ruby and TypeScript walkers by suffix; any other file in the language the pack
detects from its name, when there is a tags query for it, bundled or in projects/<name>/queries/<language>/tags.scm.
Plus the rows the generic reader takes per language: import statements, env reads, and forms that are not calls."""

from __future__ import annotations

import hashlib
import re
from functools import cache

import tree_sitter as ts
import tree_sitter_language_pack as pack

VERSION = 1  # bump to re-read every file the generic reader read
WALKED = ((".rb", "ruby"), (".ts", "typescript"), (".tsx", "tsx"), (".jsx", "tsx"), (".js", "tsx"), (".mjs", "tsx"))
OWN = {"ruby", "typescript", "tsx", "javascript"}  # the walkers' grammars: a .rake or .cjs file stays unread, as before
DATA = {"properties", "udev"}  # config formats that happen to have a tags query

_include: frozenset[str] | None = None
_exclude: frozenset[str] = frozenset(DATA)
_queries: dict[str, str] = {}
_broken: dict[str, str] = {}
_ready: set[str] = set()


def configure(include=(), exclude=(), queries=None, broken=None) -> None:
    """This process's settings; the parse pool's workers start with the same, from current()."""
    global _include, _exclude, _queries, _broken
    _include = frozenset(include) or None
    _exclude = frozenset(exclude) | (DATA - frozenset(include))
    _queries = dict(queries or {})
    _broken = dict(broken or {})
    _ready.clear()


def current() -> tuple:
    return tuple(sorted(_include or ())), tuple(sorted(_exclude)), dict(_queries), dict(_broken)


def project_settings(project) -> tuple:
    """(include, exclude, queries) from the project's [languages] and its queries/<language>/tags.scm files."""
    qdir = project.dir / "queries"
    queries = {f.parent.name: f.read_text() for f in sorted(qdir.glob("*/tags.scm"))} if qdir.is_dir() else {}
    return tuple(project.languages.get("include", [])), tuple(project.languages.get("exclude", [])), queries


@cache
def _detect(name: str) -> str | None:
    return pack.detect_language_from_path(name)


@cache
def _bundled(lang: str) -> str:
    return pack.get_tags_query(lang) or ""


def tags_query(lang: str) -> str:
    return _queries.get(lang) or _bundled(lang)


def language_for(path: str) -> str | None:
    """The grammar that reads this path, or None when nothing does."""
    for suffix, lang in WALKED:
        if path.endswith(suffix):
            return lang
    lang = _detect(path.rsplit("/", 1)[-1])
    if lang is None or lang in OWN or lang in _exclude or lang in _broken:
        return None
    if _include is not None and lang not in _include:
        return None
    return lang if tags_query(lang) else None


@cache
def _digest(text: str) -> str:
    return hashlib.sha1(f"{VERSION}\n{text}".encode()).hexdigest()[:10]


def digest(lang: str) -> str:
    """Changes when the reader or the language's query changes, so the parse cache reads the file again."""
    return _digest(tags_query(lang))


def ensure(langs) -> None:
    """Load each language's grammar, downloading it the first time, and compile its query, once per run. A language
    that fails is left unread for this run, and notes() says why."""
    for lang in sorted({x for x in langs if x} - _ready - OWN - set(_broken)):
        try:
            ts.Query(pack.get_language(lang), tags_query(lang))
            _ready.add(lang)
        except Exception as exc:  # offline on the first download, or a query this grammar rejects
            _broken[lang] = f"{type(exc).__name__}: {str(exc)[:100]}"


def notes() -> list[str]:
    return [f"language {lang} not read: {why}" for lang, why in sorted(_broken.items())]


# ---------------------------------------------------------------- import statements: (local, imported, module)


def _python(text: str) -> list[tuple[str, str, str]]:
    t = " ".join(re.sub(r"#[^\n]*", "", text).replace("(", " ").replace(")", " ").replace("\\", " ").split())
    m = re.match(r"from (\.*[\w.]*) import (.+)$", t)
    if m:
        rows = []
        for part in m.group(2).split(","):
            name, _, alias = (x.strip() for x in part.partition(" as "))
            if name:
                rows.append(("*", "*", m.group(1)) if name == "*" else (alias or name, name, m.group(1)))
        return rows
    m = re.match(r"import (.+)$", t)
    if not m:
        return []
    parts = ((x.strip() for x in p.partition(" as ")) for p in m.group(1).split(","))
    return [(alias or name, "*", name) for name, _, alias in parts if name]


def _go(text: str) -> list[tuple[str, str, str]]:
    m = re.match(r'\s*([\w.]+)?\s*"([^"]+)"', text)
    if not m or m.group(1) == "_":
        return []
    alias, path = m.groups()
    if alias == ".":
        return [("*", "*", path)]
    name = path.rsplit("/", 1)[-1]
    if re.fullmatch(r"v\d+", name) and "/" in path:  # example.com/x/v2 is package x
        name = path.rsplit("/", 2)[-2]
    return [(alias or re.sub(r"\.v\d+$", "", name).replace("-", "_"), "*", path)]


def _rust(text: str) -> list[tuple[str, str, str]]:
    m = re.match(r"(?:pub(?:\([^)]*\))?\s+)?use\s+(.+?);?\s*$", " ".join(re.sub(r"//[^\n]*", "", text).split()))
    return _rust_tree(m.group(1), "") if m else []


def _rust_tree(spec: str, prefix: str) -> list[tuple[str, str, str]]:
    spec = spec.strip()
    if spec.endswith("}") and "{" in spec:
        head, _, inner = spec.partition("{")
        base = prefix + head.strip().rstrip(":")
        return [row for part in _split(inner[:-1]) for row in _rust_tree(part, base + "::" if base else "")]
    path, _, alias = (prefix + spec).partition(" as ")
    path = path.strip().removesuffix("::self")
    if path.endswith("::*"):
        return [("*", "*", path[:-3])]
    module, _, name = path.rpartition("::")
    return [(alias.strip() or name, name, module)] if name else []


def _split(inner: str) -> list[str]:
    """The comma-separated parts of a use list, at brace depth 0."""
    parts, depth, cur = [], 0, ""
    for ch in inner:
        if ch == "," and depth == 0:
            parts.append(cur)
            cur = ""
            continue
        depth += {"{": 1, "}": -1}.get(ch, 0)
        cur += ch
    return [p for p in parts + [cur] if p.strip()]


def _elixir(text: str) -> list[tuple[str, str, str]]:
    t = " ".join(text.split())
    m = re.match(r"(alias|import|require|use) ([A-Z][\w.]*?)(?:\.\{([^}]*)\})?(?:,\s*as:\s*([A-Z]\w*))?(?=[\s,]|$)", t)
    if not m:
        return []
    kind, base, group, alias = m.groups()
    mods = [f"{base}.{g.strip()}" for g in group.split(",") if g.strip()] if group else [base]
    if kind in ("import", "use"):
        return [("*", "*", mod) for mod in mods]
    if kind == "require":
        return [(mod, "*", mod) for mod in mods]
    return [(alias if alias and len(mods) == 1 else mod.rsplit(".", 1)[-1], "*", mod) for mod in mods]


def _jvm(text: str) -> list[tuple[str, str, str]]:
    t = " ".join(text.split())
    m = re.match(r"import\s+(?:static\s+)?([\w.`]+?)(\.\*)?(?:\s+as\s+(\w+))?\s*;?\s*$", t)
    if not m:
        return []
    path, star, alias = m.groups()
    path = path.replace("`", "")
    if star:
        return [("*", "*", path)]
    module, _, name = path.rpartition(".")
    return [(alias or name, name, module)]


# language -> (node types that hold an import, the first word such a node starts with or None, its parser)
IMPORTS = {
    "python": (("import_statement", "import_from_statement"), None, _python),
    "go": (("import_spec",), None, _go),
    "rust": (("use_declaration",), None, _rust),
    "java": (("import_declaration",), None, _jvm),
    "kotlin": (("import_header",), None, _jvm),
    "elixir": (("call",), (b"alias", b"import", b"require", b"use"), _elixir),
}
ENV = {
    "python": re.compile(rb"""os\.(?:environ\.get\(|environ\[|getenv\()\s*["'](\w+)"""),
    "go": re.compile(rb'os\.(?:Getenv|LookupEnv)\(\s*"(\w+)"'),
    "rust": re.compile(rb'(?:env::var(?:_os)?\(|(?:option_)?env!\()\s*"(\w+)"'),
    "elixir": re.compile(rb'System\.(?:get_env|fetch_env!?)\(\s*"(\w+)"'),
    "java": re.compile(rb'System\.getenv\(\s*"(\w+)"'),
    "kotlin": re.compile(rb'System\.getenv\(\s*"(\w+)"'),
}
NOT_CALLS = {
    "elixir": frozenset(
        "def defp defmacro defmacrop defmodule defstruct defprotocol defimpl defdelegate defguard defguardp "
        "defexception defoverridable alias import require use type typep opaque spec callback macrocallback".split()
    )
}
# Where a call or a type name that was neither imported nor defined in its own file can resolve: "file" (an import or
# a local definition is the only way in), "folder" (a Go or Kotlin package, a Java class's package). A language not
# listed resolves it anywhere in the component, marked inferred.
SCOPE = {
    "python": ("file", "file"),
    "elixir": ("file", "file"),
    "java": ("file", "folder"),
    "kotlin": ("folder", "folder"),
    "go": ("folder", "folder"),
}
DYNAMIC = {"elixir"}  # a lowercase receiver is a map field (conn.host) or a module held in a variable: never inferred
ATTRIBUTES = {"elixir": ("unary_operator", b"@")}  # a call written inside @spec or @callback names, it does not call
