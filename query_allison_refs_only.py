from neo4j import GraphDatabase

driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', 'archaResearchAssistant'))
article_id = 'allison2008-AbajoRed-on-orangeEarlyPuebloICulturalDiversityInNorthernSanJuanRegion'
with driver.session() as s:
    rows = list(s.run(
        "MATCH (:Article {id: $article_id})-[:CITES_REFERENCE]->(r:Reference) RETURN r.id AS ref_id, r.title_guess AS title, r.raw_text AS raw_text ORDER BY r.id",
        article_id=article_id,
    ))
    print('count', len(rows))
    for row in rows:
        d = dict(row)
        print({'ref_id': d['ref_id'], 'title': d['title'], 'raw_text': (d['raw_text'] or '')[:300]})
driver.close()
