"""Labels, edge types, ids and the in-memory graph every linker writes into (A4)."""

from __future__ import annotations

import re

LABELS = ("Project", "Repo", "Deployable", "Component", "File", "Symbol", "Interface", "Note", "Ticket", "Test")
KINDS = (
    "graphql_field graphql_type graphql_operation mount route kafka_topic table flag env_var gem npm_package "
    "schedule external_api pilet_page extension_slot privilege channel"
).split()
EDGES = (
    "CONTAINS OWNS DEFINES IMPORTS CALLS REFERENCES USES_FLAG READS_ENV INCLUDES EXPOSES RESOLVED_BY HANDLED_BY "
    "MOUNTED_AT GATED_BY AUTHORIZED_BY MAPS_TO ASSOCIATES FOREIGN_KEY PRODUCES CONSUMES SCHEDULED_BY STREAMS "
    "DECLARES SELECTS ROUTED_TO USES INVALIDATES UPDATES_CACHE REGISTERS RENDERS HOSTS GUARDED_BY CALLS_ROUTE "
    "SUBSCRIBES ENQUEUES CALLS_EXTERNAL DEPENDS_ON BUILT_FROM CITES TESTS TAGGED CHANGED TALKS_TO PLANS"
).split()

TEST_PATH = re.compile(
    r"(^|/)spec/.*_spec\.rb$|\.test\.[jt]sx?$|(^|/)__tests__/|(^|/)tests/.*\.spec\.ts$"
    r"|(^|/)(test_[^/]*|conftest)\.py$|_test\.(py|go|exs)$|(^|/)tests?/.*\.(py|rs|exs)$"
    r"|(^|/)src/test/.*\.(java|kt)$|(Test|Tests|IT)\.(java|kt)$"
)
SELF_LOOPS = {"FOREIGN_KEY", "ASSOCIATES"}  # a table keyed to itself (parent_id) is a real edge
_SPLIT = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+")


def tokens(*parts: str) -> str:
    """Lowercase words of camelCase, snake_case and kebab-case names, for the full-text search index."""
    words: list[str] = []
    for part in parts:
        for chunk in re.split(r"[^A-Za-z0-9]+", part or ""):
            words.extend(w.lower() for w in _SPLIT.findall(chunk))
    return " ".join(dict.fromkeys(words))


class Graph:
    def __init__(self, project: str):
        self.project = project
        self.nodes: dict[str, tuple[set[str], dict]] = {}
        self.edges: dict[tuple[str, str, str], dict] = {}

    # ids
    def file_id(self, repo: str, path: str) -> str:
        return f"{self.project}:{repo}:{path}"

    def sym_id(self, repo: str, path: str, qual: str) -> str:
        return f"{self.project}:{repo}:{path}#{qual}"

    def iface_id(self, kind: str, name: str) -> str:
        return f"{self.project}:{kind}:{name}"

    def comp_id(self, name: str) -> str:
        return f"{self.project}:component:{name}"

    def node(self, nid: str, label: str, /, **props) -> str:
        entry = self.nodes.get(nid)
        if entry is None:
            props.setdefault("project", self.project)
            self.nodes[nid] = ({label}, props)
        else:
            entry[0].add(label)
            for k, v in props.items():
                if v not in (None, "", [], {}) or k not in entry[1]:
                    entry[1][k] = v
        return nid

    def iface(self, kind: str, name: str, /, **props) -> str:
        nid = self.iface_id(kind, name)
        props.setdefault("name", name)
        props.setdefault("search", tokens(name))
        return self.node(nid, "Interface", kind=kind, **props)

    def label(self, nid: str) -> str | None:
        entry = self.nodes.get(nid)
        if entry is None:
            return None
        return min(entry[0], key=LABELS.index)

    def edge(self, etype: str, src: str, dst: str, /, **props) -> None:
        if (src == dst and etype not in SELF_LOOPS) or src not in self.nodes or dst not in self.nodes:
            return
        key = (etype, src, dst)
        cur = self.edges.get(key)
        if cur is None:
            props.setdefault("count", 1)
            self.edges[key] = props
        else:
            cur["count"] = cur.get("count", 1) + 1
            for k, v in props.items():
                if k not in cur and v is not None:
                    cur[k] = v
            if cur.get("inferred") and not props.get("inferred"):
                cur.pop("inferred", None)
