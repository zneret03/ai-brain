"""Against the local Neo4j, under its own project name: schema, delta writes, the read verbs, impact --diff."""

from __future__ import annotations

import subprocess

import pytest

from ai_brain import api
from ai_brain.graph import ingest
from ai_brain.graph.driver import Unreachable, connect

pytestmark = pytest.mark.neo4j


@pytest.fixture(scope="module")
def db(built):
    try:
        driver = connect()
    except Unreachable:
        pytest.skip("Neo4j is not running (docker compose up -d)")
    g, _, _ = built
    with driver.session() as s:
        ingest.schema_apply(s)
        ingest.wipe(s, g.project)
    first = ingest.write(driver, g)
    second = ingest.write(driver, g)
    yield driver, g, first, second
    with driver.session() as s:
        ingest.wipe(s, g.project)
    driver.close()


def test_second_write_writes_nothing(db):
    _, g, first, second = db
    assert first["nodes_written"] == len(g.nodes) and first["edges_written"] == len(g.edges)
    assert second == {"nodes_written": 0, "edges_written": 0, "nodes_deleted": 0, "edges_deleted": 0}


def test_schema_apply_twice_changes_nothing(db):
    driver = db[0]
    with driver.session() as s:
        before = sorted(s.run("SHOW CONSTRAINTS YIELD name RETURN collect(name) AS n").single()["n"])
        ingest.schema_apply(s)
        after = sorted(s.run("SHOW CONSTRAINTS YIELD name RETURN collect(name) AS n").single()["n"])
    assert before == after
    assert {"file_id", "symbol_id", "interface_id"} <= set(after)


def test_read_verbs(db):
    assert "formatted" not in api.find(["write", "thing"], project="fixture")
    assert "writeThing" in api.find(["write", "thing"], project="fixture")
    assert "Thing.name" in api.surface(["thing", "name"], project="fixture")
    out = api.impact("Thing.name", project="fixture")
    assert "Things" in out and "useThings" in out
    assert "useThings.test.ts" in out  # the spec that pins the hook is listed under tests


def test_impact_diff_finds_consumers_outside_the_diff(db, workspace):
    repo = workspace / "mono"
    resolver = repo / "gems/eng-a/app/graphql/eng_a/resolvers/thing.rb"
    original = resolver.read_text()
    subprocess.run(["git", "-C", str(repo), "switch", "-q", "-c", "feature"], check=True)
    try:
        resolver.write_text(original.replace("find(1)", "find(2)"))
        out = api.impact(diff=["mono"], project="fixture")
    finally:
        resolver.write_text(original)
        subprocess.run(["git", "-C", str(repo), "switch", "-q", "main"], check=True)
    assert "mono: 1 files since its merge base" in out
    assert "Query.thing ← Things" in out and "(not in the diff)" in out


def test_impact_diff_reads_a_branch_the_checkout_is_not_on(db, workspace):
    repo = workspace / "mono"
    git = ["git", "-C", str(repo)]
    resolver = repo / "gems/eng-a/app/graphql/eng_a/resolvers/thing.rb"
    original = resolver.read_text()
    subprocess.run([*git, "switch", "-q", "-c", "review-me"], check=True)
    try:
        resolver.write_text(original.replace("find(1)", "find(2)"))
        subprocess.run([*git, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "find 2"], check=True)
    finally:
        subprocess.run([*git, "switch", "-q", "main"], check=True)
    try:
        out = api.impact(diff=["mono@review-me"], project="fixture")
        stacked = api.impact(diff=["mono@main...review-me"], project="fixture")
        here = api.impact(diff=["mono"], project="fixture")
        with pytest.raises(SystemExit, match="mono@no-such-branch"):
            api.impact(diff=["mono@no-such-branch"], project="fixture")
    finally:
        subprocess.run([*git, "branch", "-q", "-D", "review-me"], check=True)
    assert "mono@review-me: 1 files since its merge base" in out
    assert "Query.thing ← Things" in out and "(not in the diff)" in out
    assert "mono@main...review-me: 1 files since its merge base" in stacked
    assert "mono: 0 files since its merge base" in here  # the checkout is back on main, clean


def test_harness_docs_and_reviews_are_notes(db):
    assert "doc    orch/docs/GUIDE.md (ok)" in api.notes(["apps/app/app/models/order.rb"], project="fixture")
    review = "orch/sprints/s2/reviews/PROJ-2.md"
    assert f"review {review} (ok)" in api.notes(["pilet/src/pages/ThingsPage.tsx"], project="fixture")
    assert f"review        {review}" in api.sprint(project="fixture")
    assert f"review        {review}" in api.ticket("PROJ-2", project="fixture")


def test_ticket_brief(db, workspace):
    pilet = workspace / "pilet"
    subprocess.run(["git", "-C", str(pilet), "branch", "dev/proj-2-v1"], check=True)
    try:
        out = api.ticket("proj-2", project="fixture")
    finally:
        subprocess.run(["git", "-C", str(pilet), "branch", "-D", "dev/proj-2-v1"], check=True, capture_output=True)
    for line in (
        "plan          orch/sprints/s2/plan/PROJ-2.md  · s2 · Story · In Progress · Dev One",
        "what          What this is — the page lists things.",
        "built         The page now lists things.",
        "items         1 of 2 done",
        "branch        pilet dev/proj-2-v1 · t ·",
        "pr            pilet#7",
        "service       pilet (pilet) · 2 files",
        "gap           F3 Save (gap)",
        "open          A2 Save a thing (todo)",
        "touch         pilet/src/pages/ThingsPage.tsx:1  · edit · A1",
        "changed       pilet/src/pages/ThingsPage.tsx  · edit · A1",
        "new           pilet/src/pages/ThingsList.tsx (add)",
        "related       PROJ-4  1 shared · s2 · pilet/src/pages/ThingsPage.tsx",
    ):
        assert line in out, line
    parent = api.ticket("PROJ-1", project="fixture")
    assert "child         PROJ-2  · s2 · orch/sprints/s2/plan/PROJ-2.md" in parent
    assert "commits       1 on mono · t ×1" in parent


def test_sprint_gaps_history_who_related(db):
    out = api.sprint(project="fixture")
    assert "sprint        s2 · 3 plans" in out
    assert "PROJ-2        In Progress · built · 1/2 items · 1 open gaps · 2 files" in out
    assert "PROJ-3" in out  # the untracked draft, read because the checkout is on main
    overlap = next(ln for ln in out.splitlines() if ln.startswith("overlap"))
    assert "pilet/src/pages/ThingsPage.tsx" in overlap and "PROJ-2" in overlap and "PROJ-4" in overlap
    assert "s1" in api.sprint("all", project="fixture")
    gaps = api.gaps("PROJ-2", project="fixture")
    assert "PROJ-2        gap   F3 Save (gap)" in gaps and "PROJ-2        open  A2 Save a thing (todo)" in gaps
    history = api.history("pilet/src/pages/ThingsPage.tsx", project="fixture")
    assert "PROJ-2        built, planned · s2 · 1 files" in history
    assert "PROJ-4        planned · s2" in history
    who = api.who("src/hooks/useThings.ts", project="fixture")  # no repo given: found by its path
    assert "author        t · 1 commits" in who and "ticket        PROJ-1  cited" in who
    assert "PROJ-4        1 shared · score 0.50 · s2" in api.related("PROJ-2", project="fixture")
