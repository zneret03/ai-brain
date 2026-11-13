"""Other stacks (A10, A11): facts from a command any app can supply, and monorepo components found from manifests."""

from __future__ import annotations

from pathlib import Path

from ai_brain import config, indexer


def _project(tmp_path: Path, **kw) -> config.Project:
    base = dict(name="t", root=tmp_path, dir=tmp_path / "p", repos=[], knowledge=[], skip=[], externals_from=None)
    return config.Project(**{**base, "rails_app": None, "rails_env": "development", **kw})


def test_a_facts_command_runs_and_its_rows_link(poly_built):
    g, meta, _ = poly_built
    assert meta["facts"]["shop"]
    charge = g.sym_id("pyapp", "shop/billing.py", "charge")
    order = g.sym_id("pyapp", "shop/models.py", "Order")
    route = g.iface_id("route", "POST /charges")
    assert ("HANDLED_BY", route, charge) in g.edges
    assert g.nodes[route][1]["owner"] == "pyapp"
    total = g.iface_id("graphql_field", "pyapp/Order.total")
    assert ("RESOLVED_BY", total, g.sym_id("pyapp", "shop/models.py", "Order.total")) in g.edges
    assert ("MAPS_TO", order, g.iface_id("table", "public.orders")) in g.edges
    assert ("CONSUMES", charge, g.iface_id("kafka_topic", "orders.created")) in g.edges


def test_a_typescript_operation_reaches_the_python_resolver(poly_built):
    g, _, _ = poly_built
    op = g.iface_id("graphql_operation", "web/Order")
    assert ("SELECTS", op, g.iface_id("graphql_field", "pyapp/Order.total")) in g.edges  # the only schema answers it


def test_facts_run_again_only_when_their_app_moves(poly_built):
    _, _, ctx = poly_built
    spec = next(s for s in indexer.facts_specs(ctx.project) if s["name"] == "shop")
    assert not indexer.needs_run(ctx.project, spec, "changed")
    assert indexer.needs_run(ctx.project, spec, "full")


def test_a_failing_facts_command_keeps_the_previous_facts(tmp_path, monkeypatch):
    monkeypatch.setattr(indexer, "VAR", tmp_path / "var")
    p = _project(
        tmp_path,
        facts=[
            {"name": "bad", "app": ".", "command": ["false"]},
            {"name": "gone", "app": ".", "command": [str(tmp_path / "no-such-command")]},
        ],
    )
    (p.dir / "facts").mkdir(parents=True)
    (p.dir / "facts" / "bad.jsonl").write_text('{"t": "route", "path": "/kept"}\n')
    logged = []
    assert indexer.boot(p, logged.append) is False
    assert indexer.load_facts(p)[0]["route"] == [{"t": "route", "path": "/kept"}]
    assert (tmp_path / "var" / "log" / "facts-gone.log").read_text().startswith("FileNotFoundError")
    assert logged[-1] == "facts gone failed; keeping the previous facts (var/log/facts-gone.log)"


def test_the_rails_boot_is_the_built_in_facts_command(tmp_path):
    p = _project(tmp_path, rails_app="mono/apps/app", rails_env="personal")
    spec = indexer.facts_specs(p)[0]
    assert (spec["name"], spec["app"], spec["env"]) == ("rails", "mono/apps/app", {"RAILS_ENV": "personal"})
    cmd = indexer._command(p, spec, tmp_path / "out.jsonl")
    assert cmd[:4] == ["mise", "exec", "ruby@ruby", "--"] and cmd[4:7] == [
        "bin/rails",
        "runner",
        str(p.dir / "extractors" / "rails_introspect.rb"),
    ]


def test_monorepo_components_from_manifests(tmp_path):
    p = _project(
        tmp_path, repos=[config.Repo("mono", "monorepo", "main", tmp_path / "mono")], roots={"pilets": "pilet"}
    )
    ls = {
        "mono": [
            "apps/web/x.py",
            "gems/eng/eng.gemspec",
            "packages/core/package.json",
            "packages/core/src/a.ts",
            "services/api/go.mod",
            "libs/notes/README.md",
            "crates/core/Cargo.toml",
            "pilets/ts/package.json",
            "tools/x/package.json",
        ]
    }
    got = {u.prefix: (u.name, u.kind, u.deployable) for u in config.units(p, ls)}
    assert got == {
        "apps/web/": ("web", "app", True),
        "gems/eng/": ("eng", "engine", False),
        "packages/core/": ("core", "package", False),
        "crates/core/": ("crates-core", "package", False),
        "services/api/": ("api", "service", True),
        "pilets/ts/": ("ts", "pilet", True),
    }
