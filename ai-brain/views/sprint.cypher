// One sprint's plans and every file they plan to touch; a file with two plans on it is a merge to watch.
// :param sprint => '2026-s1'
MATCH (n:Note {sprint: $sprint, kind: 'plan'})-[r:PLANS]->(f:File)
RETURN n, r, f
