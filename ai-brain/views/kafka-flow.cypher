// Producers and consumers of every Kafka topic.
MATCH path = (:Symbol)-[:PRODUCES]->(:Interface {kind: 'kafka_topic'})<-[:CONSUMES]-(:Symbol)
RETURN path
LIMIT 300
