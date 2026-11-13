"""The one Neo4j connection. An unreachable database is exit 4, so /plan and /dev take their grep path."""

from __future__ import annotations

from neo4j import GraphDatabase
from neo4j.exceptions import AuthError, ServiceUnavailable

from ..config import load_env

URI = "bolt://127.0.0.1:7687"


class Unreachable(Exception):
    pass


def connect():
    env = load_env()
    if not env.get("NEO4J_PASSWORD"):
        raise Unreachable("no NEO4J_PASSWORD in ai-brain/.env")
    driver = GraphDatabase.driver(
        URI, auth=("neo4j", env["NEO4J_PASSWORD"]), connection_timeout=2, max_transaction_retry_time=5
    )
    try:
        driver.verify_connectivity()
    except (ServiceUnavailable, AuthError, OSError) as exc:
        driver.close()
        raise Unreachable(f"Neo4j unreachable at 127.0.0.1:7687: {type(exc).__name__}") from exc
    return driver
