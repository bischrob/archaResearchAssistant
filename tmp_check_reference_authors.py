from neo4j import GraphDatabase

driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', 'archaResearchAssistant'))
article_id = 'pryce2024-APartialPrehistoryOfSouthwestSilkRoad-ArchaeometallurgicalNetworksAlongSub-himalayanCorridor'
with driver.session() as s:
    row = s.run(
        """
        MATCH (:Article {id: $article_id})-[:CITES_REFERENCE]->(r:Reference)
        OPTIONAL MATCH (r)<-[:WROTE]-(p:Author)
        RETURN count(DISTINCT r) AS refs_with_nodes,
               count(p) AS ref_author_edges,
               sum(CASE WHEN r.bibtex IS NOT NULL AND r.bibtex <> '' THEN 1 ELSE 0 END) AS refs_with_bibtex
        """,
        article_id=article_id,
    ).single()
    print(dict(row))
    rows = s.run(
        """
        MATCH (:Article {id: $article_id})-[:CITES_REFERENCE]->(r:Reference)
        OPTIONAL MATCH (p:Author)-[w:WROTE]->(r)
        RETURN r.id AS ref_id,
               r.title_guess AS title,
               r.authors AS authors,
               substring(r.bibtex, 0, 160) AS bibtex_prefix,
               [x IN collect(CASE WHEN p IS NULL THEN NULL ELSE {author: p.name, position: w.position} END) WHERE x IS NOT NULL][0..5] AS wrote_sample
        LIMIT 3
        """,
        article_id=article_id,
    )
    for row in rows:
        print(dict(row))
driver.close()
