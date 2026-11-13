// Deployables, engines and external APIs, one edge per pair; t.detail says how they talk.
MATCH (a)-[t:TALKS_TO]->(b)
RETURN a, t, b
