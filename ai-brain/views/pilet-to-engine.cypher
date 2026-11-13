// Which pilet operation hits which engine field. Open in Neo4j Browser; double-click a node to expand it.
MATCH (p:Repo {role: 'pilet'})-[:CONTAINS]->(:File)-[:DECLARES]->(op:Interface {kind: 'graphql_operation'})
      -[:SELECTS]->(f:Interface {kind: 'graphql_field'})<-[:EXPOSES]-(e:Component)
RETURN p, op, f, e
LIMIT 300
