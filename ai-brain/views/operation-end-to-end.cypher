// One operation from the UI to the table. First: :param operation => 'OrderQueue'
MATCH path = (:Symbol)-[:USES]->(op:Interface {kind: 'graphql_operation', display: $operation})
             -[:SELECTS]->(:Interface)-[:RESOLVED_BY]->(:Symbol)-[:DEFINES*0..1]->(:Symbol)
             -[:CALLS|REFERENCES*1..2]->(:Symbol {role: 'model'})-[:MAPS_TO]->(:Interface {kind: 'table'})
RETURN path
LIMIT 50
