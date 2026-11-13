// One ticket: its plan, the files it plans to touch and changed, and the engine or pilet owning each.
// :param key => 'PROJ-123'
MATCH (n:Note {ticket: $key})-[r:PLANS|CHANGED]->(f:File)
OPTIONAL MATCH (c:Component)-[o:OWNS]->(f)
RETURN n, r, f, c, o
