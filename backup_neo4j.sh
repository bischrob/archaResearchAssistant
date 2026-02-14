docker compose stop neo4j

docker compose run --rm neo4j-admin neo4j-admin database dump neo4j --to-path=/var/lib/neo4j/import

# To restore (optional)
# docker compose run --rm neo4j-admin neo4j-admin database load neo4j --from-path=/var/lib/neo4j/import --force

docker compose start neo4j