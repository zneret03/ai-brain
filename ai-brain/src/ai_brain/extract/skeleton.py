"""tree-sitter skeleton of one file: symbols with parameters, imports, calls, constant refs, flags, env reads
and the other syntactic facts the linkers join on (A6). Pure function of (path, bytes), so results cache by blob."""

from __future__ import annotations

import re
import sys

import tree_sitter as ts
from tree_sitter_language_pack import get_language, get_parser

from . import languages

VERSION = 4  # bump to invalidate the parse cache

sys.setrecursionlimit(20000)
_PARSERS: dict = {}
URL_RE = re.compile(r"https?://([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)")
TAG_RE = re.compile(r"@([A-Z][A-Z0-9]*-\d+)")  # a ticket tag, e.g. @PROJ-123
HTTP_CLIENTS = ("Faraday", "HTTParty", "Net::HTTP", "RestClient")
ENQUEUE = {"perform_later", "perform_async", "perform_in", "perform_at"}
REGISTER = {"registerPage", "registerExtension", "registerMenu", "registerTile", "registerModal"}
KEYS = (
    "symbols imports exports_from calls refs flags env http urls gql registrations fetch slots cable enqueues "
    "describe tags gotos ident_refs consts privilege_checks topic_assign register_as"
).split()


def parse(path: str, data: bytes) -> dict | None:
    lang = languages.language_for(path)
    if lang is None:
        return None
    parser = _PARSERS.get(lang) or _PARSERS.setdefault(lang, get_parser(lang))
    tree = parser.parse(data)
    out: dict = {k: [] for k in KEYS}
    out["lang"] = lang if lang not in languages.OWN else "ruby" if lang == "ruby" else "ts"
    out["error"] = bool(tree.root_node.has_error)
    if lang == "ruby":
        _Ruby(data, out).walk(tree.root_node, (), "", "", False)
    elif lang in languages.OWN:
        _TS(data, out, path).run(tree.root_node)
    else:
        _Generic(data, out, lang).run(tree.root_node)
    for key in ("refs", "ident_refs", "calls", "flags", "env", "urls"):
        out[key] = _dedupe(out[key])
    return out


TOP_LEVEL = ("program", "export_statement", "lexical_declaration", "variable_declaration")


def _same(a, b) -> bool:
    return a is not None and b is not None and a.start_byte == b.start_byte and a.end_byte == b.end_byte


def _dedupe(rows: list) -> list:
    seen, keep = set(), []
    for row in rows:
        key = tuple(map(str, row[:-1]))
        if key not in seen:
            seen.add(key)
            keep.append(row)
    return keep


class _Base:
    def __init__(self, src: bytes, out: dict):
        self.src = src
        self.out = out

    def text(self, node) -> str:
        return self.src[node.start_byte : node.end_byte].decode("utf-8", "replace")

    @staticmethod
    def line(node) -> int:
        return node.start_point[0] + 1


class _Ruby(_Base):
    """nesting is Module.nesting as written, innermost first; owner is the enclosing method or class."""

    def walk(self, n, nesting: tuple, cls: str, owner: str, singleton: bool) -> None:
        t = n.type
        if t in ("class", "module"):
            name = n.child_by_field_name("name")
            if name is None:
                return
            written = self.text(name)
            if written.startswith("::"):
                cpath = written[2:]
            else:
                cpath = f"{nesting[0]}::{written}" if nesting else written
            sup = n.child_by_field_name("superclass")
            sup_text = ""
            if sup is not None:
                for c in sup.children:
                    if c.type in ("constant", "scope_resolution"):
                        sup_text = self.text(c)
                        self.out["refs"].append([owner or cls, sup_text, list(nesting), self.line(c)])
            self.out["symbols"].append([cpath, t, self.line(n), [], sup_text])
            inner = (cpath, *nesting)
            for c in n.children:
                if not (_same(c, name) or _same(c, sup)):
                    self.walk(c, inner, cpath, cpath, False)
            return
        if t == "singleton_class":
            for c in n.children:
                self.walk(c, nesting, cls, owner, True)
            return
        if t in ("method", "singleton_method"):
            name = n.child_by_field_name("name")
            mname = self.text(name) if name is not None else "?"
            sep = "." if (t == "singleton_method" or singleton) else "#"
            qual = f"{cls or 'main'}{sep}{mname}"
            self.out["symbols"].append([qual, "method", self.line(n), self._params(n), ""])
            obj = n.child_by_field_name("object")
            for c in n.children:
                if not (_same(c, name) or _same(c, obj)) and c.type != "method_parameters":
                    self.walk(c, nesting, cls, qual, singleton)
            return
        if t == "call":
            self._call(n, nesting, cls, owner)
        elif t == "element_reference":
            obj = n.children[0] if n.children else None
            if obj is not None and self.text(obj) == "ENV":
                s = self._first_string(n)
                if s:
                    self.out["env"].append([owner, s, self.line(n)])
        elif t == "assignment":
            left, right = n.child_by_field_name("left"), n.child_by_field_name("right")
            if left is not None and right is not None:
                if left.type == "constant":
                    cpath = f"{cls}::{self.text(left)}" if cls else self.text(left)
                    if right.type == "string":
                        self.out["consts"].append([cpath, "str", self._string_value(right), self.line(n)])
                    else:
                        self.out["consts"].append([cpath, "value", "", self.line(n)])
                elif (
                    left.type == "call"
                    and self.text(left) in ("self.topic_name",)
                    and right.type in ("constant", "scope_resolution")
                ):
                    self.out["topic_assign"].append([cls, self.text(right), list(nesting), self.line(n)])
        elif t in ("constant", "scope_resolution"):
            path = self.text(n)
            if t == "constant" or re.fullmatch(r"(::)?[A-Z]\w*(::[A-Z]\w*)*", path):
                self.out["refs"].append([owner or cls, path, list(nesting), self.line(n)])
                return
        elif t == "string_content":
            m = URL_RE.search(self.text(n))
            if m:
                self.out["urls"].append([owner or cls, m.group(1), self.line(n)])
            return
        for c in n.children:
            self.walk(c, nesting, cls, owner, singleton)

    def _call(self, n, nesting, cls, owner) -> None:
        recv, meth = n.child_by_field_name("receiver"), n.child_by_field_name("method")
        m = self.text(meth) if meth is not None else ""
        line = self.line(n)
        if recv is None or recv.type == "self":
            if m == "register_as":
                topic = self._kwarg(n, "topic")
                if topic:
                    self.out["register_as"].append([cls, topic[0], topic[1], list(nesting), line])
            elif m == "describe" and recv is None:
                self._describe(n, nesting)
            if m:
                self.out["calls"].append([owner, "", list(nesting), m, "self", line])
            return
        rtext = self.text(recv)
        base = recv
        while base.type == "call" and base.child_by_field_name("receiver") is not None:
            base = base.child_by_field_name("receiver")
        if recv.type in ("constant", "scope_resolution"):
            if rtext == "Flipper" and m == "enabled?":
                sym = self._first_symbol(n)
                if sym:
                    self.out["flags"].append([owner, sym, line])
            elif rtext == "ENV" and m in ("fetch", "key?", "[]"):
                s = self._first_string(n)
                if s:
                    self.out["env"].append([owner, s, line])
            elif rtext == "RSpec" and m == "describe":
                self._describe(n, nesting)
            if rtext.lstrip(":").startswith(HTTP_CLIENTS):
                self.out["http"].append([owner or cls, rtext.lstrip(":"), line])
            if m in ENQUEUE:
                self.out["enqueues"].append([owner, rtext, list(nesting), m, line])
            self.out["calls"].append([owner, rtext, list(nesting), m, "const", line])
        elif m in ENQUEUE and base.type in ("constant", "scope_resolution"):
            self.out["enqueues"].append([owner, self.text(base), list(nesting), m, line])
        else:
            self.out["calls"].append([owner, "", list(nesting), m, "var", line])

    def _describe(self, n, nesting) -> None:
        args = n.child_by_field_name("arguments")
        if args is not None:
            for c in args.children:
                if c.type in ("constant", "scope_resolution"):
                    self.out["describe"].append([self.text(c), list(nesting), self.line(c)])
                    return

    def _params(self, n) -> list[str]:
        params = n.child_by_field_name("parameters")
        names = []
        if params is not None:
            for c in params.children:
                if c.type == "identifier":
                    names.append(self.text(c))
                else:
                    nm = c.child_by_field_name("name")
                    if nm is not None:
                        names.append(self.text(nm))
        return names

    def _first_symbol(self, n) -> str | None:
        args = n.child_by_field_name("arguments")
        for c in args.children if args is not None else []:
            if c.type == "simple_symbol":
                return self.text(c).lstrip(":")
            if c.type == "string":
                return self._string_value(c)
        return None

    def _first_string(self, n) -> str | None:
        for c in n.children:
            if c.type == "string":
                return self._string_value(c)
            if c.type == "argument_list":
                for a in c.children:
                    if a.type == "string":
                        return self._string_value(a)
                return None
        return None

    def _string_value(self, n) -> str:
        return "".join(self.text(c) for c in n.children if c.type == "string_content")

    def _kwarg(self, n, key: str) -> tuple[str, str] | None:
        args = n.child_by_field_name("arguments")
        for c in args.children if args is not None else []:
            if c.type == "pair":
                k = c.child_by_field_name("key")
                v = c.child_by_field_name("value")
                if k is not None and v is not None and self.text(k).rstrip(":").lstrip(":") == key:
                    if v.type == "string":
                        return self._string_value(v), "str"
                    if v.type in ("constant", "scope_resolution"):
                        return self.text(v), "const"
        return None


class _TS(_Base):
    def __init__(self, src: bytes, out: dict, path: str):
        super().__init__(src, out)
        self.tsx = path.endswith((".tsx", ".jsx"))
        self.locals: set[str] = set()

    def run(self, root) -> None:
        for c in root.children:
            node = c.child_by_field_name("declaration") if c.type == "export_statement" else None
            if c.type == "import_statement":
                self._import(c)
            elif node is not None:
                self._collect_local(node)
            else:
                self._collect_local(c)
        self.walk(root, "", "", True)

    def _collect_local(self, n) -> None:
        if n.type in ("lexical_declaration", "variable_declaration"):
            for d in n.children:
                if d.type == "variable_declarator":
                    nm = d.child_by_field_name("name")
                    if nm is not None and nm.type == "identifier":
                        self.locals.add(self.text(nm))

    def _import(self, n) -> None:
        src = n.child_by_field_name("source")
        if src is None:
            return
        module = self._string_value(src)
        line = self.line(n)
        for clause in n.children:
            if clause.type != "import_clause":
                continue
            for c in clause.children:
                if c.type == "identifier":
                    self._add_import(self.text(c), "default", module, line)
                elif c.type == "namespace_import":
                    ids = [x for x in c.children if x.type == "identifier"]
                    if ids:
                        self._add_import(self.text(ids[0]), "*", module, line)
                elif c.type == "named_imports":
                    for spec in c.children:
                        if spec.type == "import_specifier":
                            name = spec.child_by_field_name("name")
                            alias = spec.child_by_field_name("alias")
                            if name is not None:
                                local = self.text(alias if alias is not None else name)
                                self._add_import(local, self.text(name), module, line)

    def _add_import(self, local: str, imported: str, module: str, line: int) -> None:
        self.out["imports"].append([local, imported, module, line])
        self.locals.add(local)

    def walk(self, n, owner: str, decl: str, top: bool) -> None:
        t = n.type
        if t == "import_statement":
            return
        if t == "export_statement":
            src = n.child_by_field_name("source")
            if src is not None:
                module = self._string_value(src)
                names = [
                    self.text(s.child_by_field_name("name"))
                    for c in n.children
                    if c.type == "export_clause"
                    for s in c.children
                    if s.type == "export_specifier" and s.child_by_field_name("name")
                ]
                for name in names or ["*"]:
                    self.out["exports_from"].append([name, module, self.line(n)])
                return
        if t in ("function_declaration", "generator_function_declaration") and top:
            name = n.child_by_field_name("name")
            if name is not None:
                qual = self.text(name)
                self._symbol(qual, "function", n, n.child_by_field_name("parameters"))
                for c in n.children:
                    self.walk(c, qual, "", False)
                return
        if t == "class_declaration" and top:
            name = n.child_by_field_name("name")
            qual = self.text(name) if name is not None else "?"
            self.out["symbols"].append([qual, "class", self.line(n), [], ""])
            body = n.child_by_field_name("body")
            for c in body.children if body is not None else []:
                if c.type == "method_definition":
                    mn = c.child_by_field_name("name")
                    mq = f"{qual}.{self.text(mn)}" if mn is not None else qual
                    self._symbol(mq, "method", c, c.child_by_field_name("parameters"))
                    for cc in c.children:
                        self.walk(cc, mq, "", False)
                else:
                    self.walk(c, qual, "", False)
            return
        if t == "variable_declarator":
            name, value = n.child_by_field_name("name"), n.child_by_field_name("value")
            if name is not None and name.type == "identifier" and value is not None:
                nm = self.text(name)
                inner = value
                while (
                    inner.type
                    in ("as_expression", "satisfies_expression", "parenthesized_expression", "non_null_expression")
                    and inner.children
                ):
                    inner = inner.children[0] if inner.type != "parenthesized_expression" else inner.children[1]
                fn = self._function_value(inner)
                if top and fn is not None:
                    self._symbol(nm, "function", n, fn.child_by_field_name("parameters"))
                    self.walk(value, nm, nm, False)
                    return
                if top:
                    self._const(nm, inner)
                self.walk(value, owner, nm, False)
                return
        if t == "call_expression":
            self._call(n, owner, decl)
        elif t in ("jsx_self_closing_element", "jsx_opening_element"):
            nm = n.child_by_field_name("name")
            if nm is not None and self.text(nm) == "ExtensionSlot":
                for a in n.children:
                    if a.type == "jsx_attribute" and a.children and self.text(a.children[0]) == "name":
                        val = a.children[-1]
                        if val.type == "string":
                            self.out["slots"].append([owner, "str:" + self._string_value(val), self.line(n)])
                        else:
                            ids = [x for x in val.children if x.type == "identifier"]
                            if ids:
                                self.out["slots"].append([owner, "id:" + self.text(ids[0]), self.line(n)])
        elif t == "member_expression":
            txt = self.text(n)
            if txt.startswith("process.env."):
                self.out["env"].append([owner, txt.split(".")[2], self.line(n)])
                return
        elif t == "identifier":
            nm = self.text(n)
            if nm in self.locals:
                self.out["ident_refs"].append([owner, nm, self.line(n)])
            return
        elif t == "string_fragment":
            txt = self.text(n)
            m = URL_RE.search(txt)
            if m:
                self.out["urls"].append([owner, m.group(1), self.line(n)])
            for tag in TAG_RE.findall(txt) if txt.startswith("@") else []:
                self.out["tags"].append([tag, self.line(n)])
            return
        for c in n.children:
            self.walk(c, owner, decl, top and t in TOP_LEVEL)

    def _function_value(self, v):
        if v.type in ("arrow_function", "function_expression", "function"):
            return v
        if v.type == "call_expression":  # memo(() => ...), forwardRef(...), styled wrappers
            args = v.child_by_field_name("arguments")
            for a in args.children if args is not None else []:
                if a.type in ("arrow_function", "function_expression", "function"):
                    return a
        return None

    def _symbol(self, qual: str, kind: str, n, params) -> None:
        role = ""
        base = qual.split(".")[-1]
        if re.match(r"use[A-Z0-9]", base):
            role = "hook"
        elif self.tsx and base[:1].isupper() and kind == "function":
            role = "component"
        self.out["symbols"].append([qual, kind, self.line(n), self._params(params), role])

    def _params(self, params) -> list[str]:
        names: list[str] = []
        if params is None:
            return names

        def collect(node):
            if node.type in ("identifier", "shorthand_property_identifier_pattern"):
                names.append(self.text(node))
            elif node.type == "pair_pattern":
                k = node.child_by_field_name("key")
                if k is not None:
                    names.append(self.text(k))
            else:
                for c in node.children:
                    if c.type not in ("type_annotation",):
                        collect(c)

        for p in params.children:
            if p.type in ("required_parameter", "optional_parameter"):
                pat = p.child_by_field_name("pattern")
                if pat is not None:
                    collect(pat)
            elif p.type == "identifier":
                names.append(self.text(p))
        return names

    def _const(self, name: str, v) -> None:
        line = self.line(v)
        if v.type == "string":
            self.out["consts"].append([name, "str", self._string_value(v), line])
        elif v.type == "template_string" and not any(c.type == "template_substitution" for c in v.children):
            self.out["consts"].append([name, "str", self._template(v), line])
        elif v.type == "array":
            items = []
            for c in v.children:
                if c.type == "string":
                    items.append(self._string_value(c))
                elif c.type == "spread_element":
                    ids = [x for x in c.children if x.type == "identifier"]
                    if ids:
                        items.append("..." + self.text(ids[0]))
            self.out["consts"].append([name, "array", items, line])
        elif v.type == "object":
            obj = {}
            for c in v.children:
                if c.type == "pair":
                    k, val = c.child_by_field_name("key"), c.child_by_field_name("value")
                    if k is not None and val is not None and val.type == "string":
                        obj[self.text(k).strip("'\"")] = self._string_value(val)
            if obj:
                self.out["consts"].append([name, "object", obj, line])
        elif v.type == "call_expression":  # new Set([...]) is a new_expression; handled below
            pass
        elif v.type == "new_expression":
            arr = [c for c in v.children if c.type == "arguments"]
            for a in arr[0].children if arr else []:
                if a.type == "array":
                    self._const(name, a)

    def _call(self, n, owner: str, decl: str) -> None:
        fn, args = n.child_by_field_name("function"), n.child_by_field_name("arguments")
        line = self.line(n)
        if fn is None:
            return
        first = None
        if args is not None:
            real = [a for a in args.children if a.type not in ("(", ")", ",")]
            first = real[0] if real else None
            if args.type == "template_string":
                first = args
        if fn.type == "identifier":
            name = self.text(fn)
            if name in ("graphql", "gql") and first is not None and first.type == "template_string":
                self.out["gql"].append([decl, self._template(first), self.line(first)])
            elif name == "fetch" and first is not None:
                self.out["fetch"].append([owner, self._path_arg(first), line])
            elif name == "hasPrivilege" and first is not None:
                self.out["privilege_checks"].append([owner, self.text(first), line])
            self.out["calls"].append([owner, name, "id", line])
        elif fn.type == "member_expression":
            obj, prop = fn.child_by_field_name("object"), fn.child_by_field_name("property")
            if obj is None or prop is None:
                return
            otext, ptext = self.text(obj), self.text(prop)
            if ptext in REGISTER:
                second = None
                if args is not None:
                    real = [a for a in args.children if a.type not in ("(", ")", ",")]
                    second = real[1] if len(real) > 1 else None
                self.out["registrations"].append(
                    [
                        ptext,
                        self._reg_arg(first),
                        self.text(second) if second is not None and second.type == "identifier" else "",
                        line,
                    ]
                )
            elif ptext == "hasPrivilege" and first is not None:
                self.out["privilege_checks"].append([owner, self.text(first), line])
            elif ptext == "create" and otext.endswith("subscriptions") and first is not None:
                chan = self._channel_arg(first)
                if chan:
                    self.out["cable"].append([owner, chan, line])
            elif ptext == "goto" and first is not None:
                self.out["gotos"].append([self._path_arg(first), line])
            self.out["calls"].append([owner, f"{otext}.{ptext}", "member", line])

    def _reg_arg(self, a) -> str:
        if a is None:
            return ""
        if a.type == "string":
            return "str:" + self._string_value(a)
        if a.type == "identifier":
            return "id:" + self.text(a)
        if a.type == "call_expression":
            fn, args = a.child_by_field_name("function"), a.child_by_field_name("arguments")
            inner = [x for x in (args.children if args is not None else []) if x.type == "string"]
            if fn is not None and inner:
                return f"call:{self.text(fn)}:{self._string_value(inner[0])}"
        if a.type == "object":
            return "object"
        return "expr"

    def _channel_arg(self, a) -> str | None:
        if a.type == "string":
            return self._string_value(a)
        if a.type == "object":
            for c in a.children:
                if c.type == "pair":
                    k, v = c.child_by_field_name("key"), c.child_by_field_name("value")
                    if (
                        k is not None
                        and v is not None
                        and self.text(k).strip("'\"") == "channel"
                        and v.type == "string"
                    ):
                        return self._string_value(v)
        return None

    def _path_arg(self, a) -> str:
        if a.type == "string":
            return self._string_value(a)
        if a.type == "template_string":
            return "".join(
                "{}" if c.type == "template_substitution" else self.text(c) for c in a.children if c.type not in ("`",)
            )
        return "{}"

    def _template(self, n) -> str:
        return "".join(self.text(c) for c in n.children if c.type == "string_fragment")

    def _string_value(self, n) -> str:
        return "".join(self.text(c) for c in n.children if c.type in ("string_fragment", "escape_sequence"))


class _Generic(_Base):
    """Any language with a tags query (A2). Definitions nest by their byte ranges, and an `impl` block nests its
    methods under its type; a call or a type reference keeps the receiver written before its name."""

    SIMPLE = re.compile(r"[A-Za-z_$@][\w$]*(?:(?:\.|::|->)[A-Za-z_$][\w$]*)*")
    CLASSY = {"class", "interface", "struct", "trait", "object", "implementation"}
    _QUERIES: dict = {}

    def __init__(self, src: bytes, out: dict, lang: str):
        super().__init__(src, out)
        self.lang = lang

    def run(self, root) -> None:
        events = self._tags(root) + self._scan(root) + self._env()
        events.sort(key=lambda e: (e[0], -e[1]))
        stack: list[tuple[int, str, str]] = []  # (end byte, qual, kind) of the definitions open at this byte
        for start, end, what, *rest in events:
            while stack and stack[-1][0] <= start:
                stack.pop()
            owner = stack[-1][1] if stack else ""
            if what == "def":
                name, kind, line, node = rest
                if kind == "function" and stack and stack[-1][2] in self.CLASSY:
                    kind = "method"
                qual = f"{owner}.{name}" if owner else name
                self.out["symbols"].append([qual, kind, line, self._params(node), ""])
                stack.append((end, qual, kind))
            elif what == "impl":
                stack.append((end, f"{owner}.{rest[0]}" if owner else rest[0], "implementation"))
            elif what == "tags":
                self.out["tags"].append(rest)
            else:
                self.out[what].append([owner, *rest])

    def _tags(self, root) -> list[tuple]:
        text = languages.tags_query(self.lang)
        query = self._QUERIES.get(text) or self._QUERIES.setdefault(text, ts.Query(get_language(self.lang), text))
        defs: dict[tuple[int, int], list] = {}
        refs = []
        for _, caps in ts.QueryCursor(query).matches(root):
            names = caps.get("name")
            if not names:
                continue
            nm = names[0]
            for tag, nodes in caps.items():
                if tag.startswith("definition."):
                    kind, key = tag[11:], (nm.start_byte, nm.end_byte)
                    if key not in defs:
                        n = nodes[0]
                        defs[key] = [n.start_byte, n.end_byte, "def", self.text(nm), kind, self.line(n), n]
                    elif kind == "method":  # one function captured as both, as Rust's query does
                        defs[key][4] = kind
                elif tag.startswith("reference."):
                    refs.append((tag[10:], nodes[0], nm))
        events = [tuple(d) for d in defs.values()]
        skip = languages.NOT_CALLS.get(self.lang, frozenset())
        attribute = languages.ATTRIBUTES.get(self.lang)
        for kind, node, nm in refs:
            if (nm.start_byte, nm.end_byte) in defs:  # a definition's own name, such as an Elixir function head
                continue
            name = self.text(nm)
            if kind == "implementation":
                typ = node.child_by_field_name("type")
                while typ is not None and typ.child_by_field_name("type") is not None:  # impl<T> Order<T>
                    typ = typ.child_by_field_name("type")
                events.append((node.start_byte, node.end_byte, "impl", self.text(typ) if typ is not None else name))
            if kind == "call":
                if name not in skip and not (attribute and self._inside(node, *attribute)):
                    events.append(
                        (nm.start_byte, nm.start_byte, "calls", name, self._receiver(nm, node), self.line(nm))
                    )
            elif kind in ("class", "type", "module", "interface", "implementation"):
                events.append((nm.start_byte, nm.start_byte, "refs", name, self._receiver(nm, node), self.line(nm)))
        return events

    def _inside(self, node, typ: str, token: bytes) -> bool:
        cur = node.parent
        while cur is not None:
            if cur.type == typ and self.src.startswith(token, cur.start_byte):
                return True
            cur = cur.parent
        return False

    def _receiver(self, nm, ref) -> str:
        """What is written before the name inside the expression that holds it: `bc` in `bc.charge(o)`."""
        cur = nm
        for _ in range(3):
            par = cur.parent
            if par is None:
                return ""
            before = None
            for c in par.named_children:
                if c.start_byte >= cur.start_byte:
                    break
                before = c
            if before is not None:
                txt = self.text(before)
                return txt if len(txt) <= 120 and self.SIMPLE.fullmatch(txt) else "?"
            if par.id == ref.id or par.named_child_count > 1:  # climb only through a wrapper, as Kotlin's suffix
                return ""
            cur = par
        return ""

    def _params(self, node) -> list[str]:
        params = node.child_by_field_name("parameters")
        if params is None:
            params = next((c for c in node.named_children if "parameter" in c.type), None)
        names = []
        for c in params.named_children if params is not None else []:
            n = c if "identifier" in c.type else c.child_by_field_name("name") or c.child_by_field_name("pattern")
            if n is None:
                n = next((x for x in c.named_children if "identifier" in x.type), None)
            if n is not None and "identifier" in n.type:
                names.append(self.text(n))
        return names

    def _scan(self, root) -> list[tuple]:
        """Import statements, and ticket tags in strings, in one walk of the tree."""
        types, heads, parse_import = languages.IMPORTS.get(self.lang, ((), None, None))
        events = []
        cur = root.walk()
        while True:
            node = cur.node
            t = node.type
            if t in types and (heads is None or self.src.startswith(heads, node.start_byte)):
                for row in parse_import(self.text(node)):
                    self.out["imports"].append([*row, self.line(node)])
            elif ("string" in t or t == "quoted_content") and not any("string" in c.type for c in node.named_children):
                txt = self.text(node).strip("\"'`")
                if txt.startswith("@"):
                    events += [
                        (node.start_byte, node.start_byte, "tags", tag, self.line(node)) for tag in TAG_RE.findall(txt)
                    ]
            if cur.goto_first_child():
                continue
            while not cur.goto_next_sibling():
                if not cur.goto_parent():
                    return events

    def _env(self) -> list[tuple]:
        pat = languages.ENV.get(self.lang)
        events = []
        for m in pat.finditer(self.src) if pat is not None else []:
            events.append((m.start(), m.start(), "env", m.group(1).decode(), self.src.count(b"\n", 0, m.start()) + 1))
        return events
