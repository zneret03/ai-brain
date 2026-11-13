"""Every edge type of A4 appears on the fixture workspace, with the endpoints its row in the table names."""

from __future__ import annotations

import pytest

from ai_brain.model import EDGES


def _edges(g, etype):
    return [(s, d, p) for (t, s, d), p in g.edges.items() if t == etype]


@pytest.mark.parametrize("etype", EDGES)
def test_every_edge_type_is_built(built, etype):
    g, _, _ = built
    assert _edges(g, etype), f"no {etype} edge on the fixture"


def test_cross_engine_reference(built):
    g, _, _ = built
    cross = [(s, d) for s, d, p in _edges(g, "REFERENCES") if p.get("cross_engine")]
    assert any("eng-a" in s and d.endswith("#EngB::Helper") for s, d in cross)
    assert any(d.endswith("#Client") for s, d in cross)


def test_const_call_resolves_to_singleton_method(built):
    g, _, _ = built
    assert any(d.endswith("#EngB::Helper.call") for _, d, _ in _edges(g, "CALLS"))


def test_operation_line_is_the_query_keyword(built):
    g, _, _ = built
    op = g.nodes[g.iface_id("graphql_operation", "pilet/Things")][1]
    assert op["line"] == 2  # graphql(` is on line 1, `query Things` on line 2


def test_selects_and_invalidates(built):
    g, _, _ = built
    things = g.iface_id("graphql_operation", "pilet/Things")
    save = g.iface_id("graphql_operation", "pilet/SaveThing")
    assert (things, g.iface_id("graphql_field", "eng-a/Thing.name")) in {(s, d) for s, d, _ in _edges(g, "SELECTS")}
    assert (save, things) in {(s, d) for s, d, _ in _edges(g, "INVALIDATES")}


def test_self_referencing_foreign_key_is_kept(built):
    g, _, _ = built
    clients = g.iface_id("table", "public.clients")
    assert (clients, clients) in {(s, d) for s, d, _ in _edges(g, "FOREIGN_KEY")}


def test_note_sources_ok_moved_gone(built):
    g, _, _ = built
    statuses = {p["status"] for _, _, p in _edges(g, "CITES") if p.get("status")}
    assert {"ok", "moved"} <= statuses
    note = g.nodes[f"{g.project}:note:notes:projects/client.md"][1]
    assert note["gone"] == ["gone-repo:README.md"]


def test_external_api_named_by_host(built):
    g, _, _ = built
    assert any(d.endswith(":external_api:vendor") for _, d, _ in _edges(g, "CALLS_EXTERNAL"))


def test_engines_and_externals_are_discovered(built):
    _, meta, _ = built
    assert meta["engines"] == ["eng-a", "eng-b"]
    assert meta["externals"] == ["outside"]  # lib is a GIT source too, but it is cloned, so it is a repo


def test_library_is_read_at_its_lockfile_pin(built):
    _, meta, ctx = built
    pin = ctx.lock.split("revision: ")[1].split()[0]
    assert meta["indexed"]["lib"] == pin


def test_page_test_and_ticket(built):
    g, _, _ = built
    page = g.iface_id("pilet_page", "pilet:things")
    assert any(d == page for _, d, _ in _edges(g, "TESTS"))
    assert any(d.endswith(":ticket:PROJ-1") for _, d, _ in _edges(g, "TAGGED"))


def test_plan_sections_become_files_gaps_and_a_report(built):
    g, _, _ = built
    nid = f"{g.project}:note:orch:sprints/s2/plan/PROJ-2.md"
    plan = g.nodes[nid][1]
    assert (plan["ticket"], plan["sprint"], plan["parent"]) == ("PROJ-2", "s2", "PROJ-1")
    assert (plan["jira_type"], plan["jira_status"], plan["owner"]) == ("Story", "In Progress", "Dev One")
    assert plan["branches"] == ["pilet dev/proj-2-v1"]
    assert (plan["items_done"], plan["items_total"], plan["open_items"]) == (1, 2, ["A2 Save a thing (todo)"])
    assert (plan["gaps_total"], plan["gaps_open"]) == (2, ["F3 Save (gap)"])  # F1's only closer is done
    assert plan["planned_new"] == ["pilet/src/pages/ThingsList.tsx (add)"]
    assert (plan["tldr"], plan["summary"], plan["built"]) == (
        "What this is — the page lists things.",
        "The page now lists things.",
        True,
    )
    assert plan["prs"] == ["pilet#7"]
    planned = {d.rsplit(":", 1)[-1]: p for s, d, p in _edges(g, "PLANS") if s == nid}
    assert planned["src/pages/ThingsPage.tsx"] == {"line": 1, "change": "edit", "item": "A1", "count": 1, "side": "FE"}
    assert planned["src/graphql/mutations/save.ts"]["item"] == "A2"  # `TS <path>`: the repo tag is dropped
    assert [d.rsplit(":", 1)[-1] for s, d, _ in _edges(g, "CHANGED") if s == nid] == ["src/pages/ThingsPage.tsx"]


def test_reviews_and_harness_docs_cite_whole_paths(built):
    g, _, _ = built
    cites = {(s.split(":note:orch:")[-1], d.split(":", 1)[-1], p.get("line")) for s, d, p in _edges(g, "CITES")}
    assert ("sprints/s2/reviews/PROJ-2.md", "pilet:src/pages/ThingsPage.tsx", 1) in cites  # .tsx, not cut to .ts
    assert ("docs/GUIDE.md", "mono:apps/app/app/models/order.rb", 1) in cites
    assert g.nodes[f"{g.project}:note:orch:sprints/s2/reviews/PROJ-2.md"][1]["kind"] == "review"


def test_home_plan_supersedes_its_archive_copy_and_drafts_count(built):
    g, _, _ = built
    assert f"{g.project}:note:docs:sprints/s2/plan/PROJ-2.md" not in g.nodes
    assert f"{g.project}:note:docs:sprints/s1/plan/PROJ-1.md" in g.nodes
    draft = g.nodes[f"{g.project}:note:orch:sprints/s2/plan/PROJ-3.md"][1]  # gitignored, read from disk
    assert (draft["ticket"], draft["kind"]) == ("PROJ-3", "plan")


def test_ticket_commits_carry_their_authors(built):
    g, _, _ = built
    ticket = g.nodes[f"{g.project}:ticket:PROJ-1"][1]
    assert (ticket["authors"], ticket["commits"], ticket["repos"]) == (["t ×1"], 1, ["mono"])
