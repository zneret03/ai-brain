"""Reading any language (A1-A7): which reader takes a file, what the generic reader keeps, and the edges the polyglot
workspace gets from it."""

from __future__ import annotations

import pytest

from ai_brain.extract import corpus, languages, skeleton


def _edges(g, etype):
    """(source, target, props) with the project prefix dropped: repo:path or repo:path#qual."""
    return [(s.split(":", 1)[1], d.split(":", 1)[1], p) for (t, s, d), p in g.edges.items() if t == etype]


def _pairs(g, etype):
    return {(s, d) for s, d, _ in _edges(g, etype)}


@pytest.fixture
def settings():
    yield languages.configure
    languages.configure()


def test_walkers_keep_their_suffixes_and_the_rest_is_detected():
    for path, lang in {
        "a.rb": "ruby",
        "a.ts": "typescript",
        "a.tsx": "tsx",
        "a.js": "tsx",
        "a.mjs": "tsx",
        "a.py": "python",
        "lib/a.ex": "elixir",
        "test/a_test.exs": "elixir",
        "src/a.rs": "rust",
        "a.go": "go",
        "A.java": "java",
        "A.kt": "kotlin",
    }.items():
        assert languages.language_for(path) == lang, path
    for path in ("a.cjs", "Rakefile", "x.rake", "a.json", "a.yml", "README.md", "app.properties", "a.sh"):
        assert languages.language_for(path) is None, path


def test_include_and_exclude(settings):
    settings(exclude=["go"])
    assert languages.language_for("a.go") is None
    assert languages.language_for("a.py") == "python"
    settings(include=["python"])
    assert languages.language_for("a.rs") is None
    assert languages.language_for("a.py") == "python"
    assert languages.language_for("a.rb") == "ruby"  # the walkers always read


def test_a_failing_grammar_is_left_out_with_a_note(settings, monkeypatch):
    def broken(lang):
        raise RuntimeError(f"no grammar for {lang}")

    settings()
    monkeypatch.setattr(languages.pack, "get_language", broken)
    languages.ensure({"go"})
    assert languages.language_for("a.go") is None
    assert languages.notes() == ["language go not read: RuntimeError: no grammar for go"]


def test_parse_cache_keys_generic_files_by_language_and_query():
    assert corpus._key("a.rb", "abc") == "abc"
    assert corpus._key("a.py", "abc") == f"abc:python:{languages.digest('python')}"


def test_python_reader_rows():
    out = skeleton.parse(
        "shop/billing.py",
        b"from .models import Order as O, Line\nimport shop.models as m\n\n"
        b"def charge(order_id, *, rate=1):\n    return O(order_id).total(rate) + m.helper()\n",
    )
    assert out["lang"] == "python"
    assert out["symbols"] == [["charge", "function", 4, ["order_id", "rate"], ""]]
    assert out["imports"] == [
        ["O", "Order", ".models", 1],
        ["Line", "Line", ".models", 1],
        ["m", "*", "shop.models", 2],
    ]
    assert ["charge", "O", "", 5] in out["calls"]
    assert ["charge", "total", "?", 5] in out["calls"]  # the receiver is an expression
    assert ["charge", "helper", "m", 5] in out["calls"]


@pytest.mark.parametrize(
    "lang, text, rows",
    [
        ("rust", "use crate::a::{b, c::d as e};", [("b", "b", "crate::a"), ("e", "d", "crate::a::c")]),
        ("rust", "pub use self::x::*;", [("*", "*", "self::x")]),
        ("go", 'b "example.com/shop/billing"', [("b", "*", "example.com/shop/billing")]),
        ("go", '"github.com/x/yaml/v3"', [("yaml", "*", "github.com/x/yaml/v3")]),
        ("elixir", "alias Shop.{A, B}", [("A", "*", "Shop.A"), ("B", "*", "Shop.B")]),
        ("elixir", "alias Shop.C, as: D", [("D", "*", "Shop.C")]),
        ("java", "import static a.c.U.m;", [("m", "m", "a.c.U")]),
        ("kotlin", "import a.e.F as G", [("G", "F", "a.e")]),
    ],
)
def test_import_statements(lang, text, rows):
    assert languages.IMPORTS[lang][2](text) == rows


def test_symbols_nest(poly_built):
    g, _, _ = poly_built
    syms = {nid.split(":", 1)[1]: props for nid, (labels, props) in g.nodes.items() if "Symbol" in labels}
    assert syms["pyapp:shop/models.py#Order.total"]["kind"] == "method"
    assert syms["pyapp:shop/models.py#Order.total"]["params"] == ["self", "rate"]
    assert syms["exapp:lib/shop/orders.ex#Shop.Orders"]["kind"] == "module"
    assert syms["exapp:lib/shop/orders.ex#Shop.Orders.helper"]["kind"] == "function"
    assert syms["rsapp:src/order.rs#Order.total"]["kind"] == "method"  # nested under its impl
    assert syms["jvapp:src/main/java/shop/orders/OrderService.java#OrderService.fee"]["kind"] == "method"
    assert ("pyapp:shop/models.py#Order", "pyapp:shop/models.py#Order.total") in _pairs(g, "DEFINES")


def test_imports_resolve_to_files(poly_built):
    g, _, _ = poly_built
    imports = _pairs(g, "IMPORTS")
    for edge in [
        ("pyapp:shop/billing.py", "pyapp:shop/models.py"),
        ("pyapp:tests/test_billing.py", "pyapp:shop/billing.py"),
        ("exapp:lib/shop/orders.ex", "exapp:lib/shop/billing.ex"),
        ("rsapp:src/order.rs", "rsapp:src/billing.rs"),
        ("rsapp:tests/order.rs", "rsapp:src/order.rs"),
        ("goapp:orders/orders.go", "goapp:billing/billing.go"),
        ("jvapp:src/main/java/shop/orders/OrderService.java", "jvapp:src/main/java/shop/billing/Billing.java"),
    ]:
        assert edge in imports, edge


def test_calls_resolve(poly_built):
    g, _, _ = poly_built
    calls = _pairs(g, "CALLS")
    for edge in [
        ("pyapp:shop/models.py#Order.total", "pyapp:shop/models.py#Order.subtotal"),
        ("pyapp:shop/billing.py#charge", "pyapp:shop/models.py#Order"),
        ("pyapp:tests/test_billing.py#test_charge", "pyapp:shop/billing.py#charge"),
        ("exapp:lib/shop/orders.ex#Shop.Orders.total", "exapp:lib/shop/billing.ex#Shop.Billing.charge"),
        ("exapp:lib/shop/orders.ex#Shop.Orders.total", "exapp:lib/shop/orders.ex#Shop.Orders.helper"),
        ("exapp:test/shop/orders_test.exs#Shop.OrdersTest", "exapp:lib/shop/orders.ex#Shop.Orders.total"),
        ("rsapp:src/order.rs#Order.total", "rsapp:src/billing.rs#charge"),
        ("rsapp:src/order.rs#Order.total", "rsapp:src/order.rs#Order.fee"),
        ("goapp:orders/orders.go#Total", "goapp:billing/billing.go#Charge"),
        ("goapp:orders/orders.go#Total", "goapp:orders/orders.go#fee"),
        (
            "jvapp:src/main/java/shop/orders/OrderService.java#OrderService.total",
            "jvapp:src/main/java/shop/billing/Billing.java#Billing.charge",
        ),
        (
            "jvapp:src/main/java/shop/orders/OrderService.java#OrderService.total",
            "jvapp:src/main/java/shop/orders/OrderService.java#OrderService.fee",
        ),
    ]:
        assert edge in calls, edge
    assert not any(s.endswith("#fee") and s.startswith("goapp:") for s, _ in calls)  # os.Getenv is outside the repo


def test_a_variable_receiver_links_only_inferred(poly_built):
    g, _, _ = poly_built
    hit = [p for s, d, p in _edges(g, "CALLS") if s == "pyapp:shop/billing.py#charge" and d.endswith("#Order.total")]
    assert hit and hit[0].get("inferred") is True


def test_cross_component_call_and_talks_label(poly_built):
    g, _, _ = poly_built
    cross = [
        p
        for s, d, p in _edges(g, "CALLS")
        if s == "pymono:apps/api/api/handlers.py#handle" and d == "pymono:apps/worker/worker/jobs.py#enqueue_job"
    ]
    assert cross and cross[0].get("cross_engine") is True
    talks = {(s, d): p for s, d, p in _edges(g, "TALKS_TO")}
    assert talks[("component:api", "component:worker")]["via"] == ["python"]


def test_tests_linked(poly_built):
    g, _, _ = poly_built
    tests = _pairs(g, "TESTS")
    for edge in [
        ("pyapp:tests/test_billing.py", "pyapp:shop/billing.py"),
        ("exapp:test/shop/orders_test.exs", "exapp:lib/shop/orders.ex"),
        ("rsapp:tests/order.rs", "rsapp:src/order.rs"),
        ("goapp:orders/orders_test.go", "goapp:orders/orders.go"),
        ("jvapp:src/test/java/shop/orders/OrderServiceTest.java", "jvapp:src/main/java/shop/orders/OrderService.java"),
    ]:
        assert edge in tests, edge
    assert "Test" in g.nodes[g.file_id("goapp", "orders/orders_test.go")][0]


def test_env_reads_and_ticket_tags(poly_built):
    g, _, _ = poly_built
    env = _pairs(g, "READS_ENV")
    for edge in [
        ("pyapp:shop/models.py", "env_var:SHOP_API_URL"),
        ("exapp:lib/shop/orders.ex#Shop.Orders.total", "env_var:SHOP_KEY"),
        ("rsapp:src/order.rs#Order.fee", "env_var:FEE"),
        ("goapp:orders/orders.go#fee", "env_var:FEE"),
        ("jvapp:src/main/java/shop/orders/OrderService.java#OrderService.fee", "env_var:FEE"),
    ]:
        assert edge in env, edge
    assert ("pyapp:tests/test_billing.py", "ticket:PROJ-7") in _pairs(g, "TAGGED")


def test_a_project_query_adds_a_language(poly_built):
    g, meta, _ = poly_built
    assert ("pyapp:scripts/deploy.sh#deploy", "pyapp:scripts/deploy.sh#build") in _pairs(g, "CALLS")
    assert meta["languages"]["bash"] == 1
    assert meta["coverage"] == 100.0
