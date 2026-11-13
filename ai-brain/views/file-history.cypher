// The tickets behind a file: plans that touched it, dev reports that changed it, commits that named a ticket.
// :param path => 'src/pages/Orders/Orders.tsx'
MATCH (f:File) WHERE f.path ENDS WITH $path
MATCH (n)-[r:PLANS|CHANGED]->(f) WHERE n:Note OR n:Ticket
RETURN n, r, f
