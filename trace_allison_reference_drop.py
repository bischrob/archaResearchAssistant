import sys
from pathlib import Path

sys.path.insert(0, ".")

from neo4j import GraphDatabase
from src.rag.anystyle_refs import extract_citations_with_anystyle_docker, parse_reference_strings_with_anystyle_docker

PDF = Path("/mnt/storage/main/home_server/researchAssistant/ingest_inputs/zotero/storage/EVQUW6ZD/allison2008-AbajoRed-on-orangeEarlyPuebloICulturalDiversityInNorthernSanJuanRegion.pdf")
ARTICLE_ID = "allison2008-AbajoRed-on-orangeEarlyPuebloICulturalDiversityInNorthernSanJuanRegion"
MANUAL_REFS = [
    "Hegmon, Michelle, James R. Allison, Hector Neff, and Michael Glascock. 1997. Production of San Juan Red Ware in the Northern Southwest: Insights into Regional Interaction in Early Puebloan Prehistory. American Antiquity 62(3):449-463.",
    "Washburn, Dorothy. 2006. Abajo Ceramics: A Non-Local Design System amidst the Anasazi. In Southwestern Interludes: Papers in Honor of Charlotte J. And Theodore R. Frisbie, edited by Regge N. Wiseman, Thomas C. O’Laughlin, and Cordelia T. Snow, pp. 193-202. Papers of the Archaeological Society of New Mexico No. 32. Albuquerque.",
]

print("=== Anystyle find on whole PDF ===")
found = extract_citations_with_anystyle_docker(PDF)
print("count", len(found))
for i, c in enumerate(found, start=1):
    print(f"FOUND {i}: title={c.title_guess!r} year={c.year!r} authors={c.authors!r}")
    print(f"RAW {i}: {c.raw_text[:500]}")

print("=== Anystyle parse on manual clean references ===")
parsed = parse_reference_strings_with_anystyle_docker(MANUAL_REFS, article_id="manual-allison-test")
print("count", len(parsed))
for i, c in enumerate(parsed, start=1):
    print(f"PARSED {i}: title={c.title_guess!r} year={c.year!r} authors={c.authors!r}")
    print(f"RAW {i}: {c.raw_text[:500]}")

print("=== Reference nodes currently attached in Neo4j ===")
driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "archaResearchAssistant"))
with driver.session() as s:
    rows = list(s.run(
        "MATCH (:Article {id: $article_id})-[:CITES_REFERENCE]->(r:Reference) RETURN r.id AS ref_id, r.title_guess AS title, r.raw_text AS raw_text ORDER BY r.id",
        article_id=ARTICLE_ID,
    ))
    print("count", len(rows))
    for row in rows:
        d = dict(row)
        print(f"NODE {d['ref_id']}: title={d['title']!r}")
        print(f"NODE RAW: {(d['raw_text'] or '')[:500]}")
driver.close()
