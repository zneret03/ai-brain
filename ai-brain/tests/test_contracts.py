"""Contract files (A12): a component's GraphQL schema files and OpenAPI specs as interfaces, and their copies left out."""

from __future__ import annotations


def test_a_schema_file_declares_its_types_and_fields(poly_built):
    g, _, _ = poly_built
    field = g.iface_id("graphql_field", "exapp/Invoice.amount")
    assert g.nodes[field][1]["line"] == 6
    assert ("DECLARES", g.file_id("exapp", "priv/schema.graphql"), field) in g.edges
    assert ("EXPOSES", g.comp_id("exapp"), field) in g.edges


def test_copies_are_left_out(poly_built):
    g, _, _ = poly_built
    kinds = ("graphql_field", "graphql_type")
    owners = {props.get("owner") for _, (_, props) in g.nodes.items() if props.get("kind") in kinds}
    assert "web" not in owners  # a frontend's copy
    assert g.iface_id("graphql_type", "exapp/Fake") not in g.nodes  # a test's


def test_an_operation_file_routes_to_the_schema_with_its_root_fields(poly_built):
    g, _, _ = poly_built
    invoice = g.iface_id("graphql_operation", "web/Invoice")
    assert ("SELECTS", invoice, g.iface_id("graphql_field", "exapp/Invoice.amount")) in g.edges
    assert ("DECLARES", g.file_id("web", "src/invoice.graphql"), invoice) in g.edges
    assert g.nodes[g.iface_id("graphql_operation", "web/Order")][1]["routed_to"] == "pyapp"


def test_an_openapi_spec_declares_routes(poly_built):
    g, _, _ = poly_built
    get = g.iface_id("route", "GET /v1/orders/:id")
    assert (g.nodes[get][1]["owner"], g.nodes[get][1]["line"]) == ("goapp", 5)
    assert ("DECLARES", g.file_id("goapp", "api/openapi.yaml"), get) in g.edges
    assert g.edges[("HANDLED_BY", get, g.sym_id("goapp", "orders/orders.go", "Total"))]["inferred"] is True
    assert g.iface_id("route", "POST /v1/charges") in g.nodes
    assert ("CALLS_ROUTE", g.sym_id("web", "src/orders.ts", "loadOrder"), get) in g.edges
