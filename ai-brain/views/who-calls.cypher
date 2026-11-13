// The callers of a function or method. First: :param name => 'formatPeriodRange'
MATCH (s:Symbol)<-[c:CALLS]-(caller:Symbol)<-[:DEFINES*1..2]-(f:File)
WHERE s.short = $name OR s.name = $name
RETURN s, c, caller, f
LIMIT 200
