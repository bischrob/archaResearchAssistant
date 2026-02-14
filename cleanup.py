from src import *
from neo4j import GraphDatabase
import pandas as pd
import re
import unicodedata

driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "archaResearchAssistant"))

cleanup = DBcleanup(driver)

dups = cleanup.find_dups("DOCUMENT")
cleanup.merge_dups(dups, "DOCUMENT")
dups = cleanup.find_dups("PERSON")
cleanup.merge_dups(dups, "PERSON")
authors = pd.read_excel("authors.xlsx")
cleanup.update_metadata(authors)
cleanup.merge_people_by_id("scholar")
cleanup.merge_people_by_id("orcid")
cleanup.merge_people_by_id("scopus")
cleanup.remove_empty(["PERSON","keep","orcid","scholar"])

# to do -- export documents and people to spreadsheets and mark as valid or not then delete invalid and use results to train a machine learning model to better identify valid citation paragraphs

query = """
MATCH (t:PARAGRAPH)<-[:HAS_CITATION]-(d:DOCUMENT)<-[r]-(p:PERSON)
with collect(elementId(t)) as ts, d, r, p
WITH d, type(r) + ": " + p.full AS author_entry, ts
WHERE NOT "PDF" in labels(d)
// Group authors per document into a single line
WITH d, COLLECT(author_entry) AS authors, apoc.text.join(ts,"; ") as paragraphs
RETURN elementId(d) AS id, 
       paragraphs,
       d.citekey AS citekey, 
       d.title AS title, 
       d.year AS year, 
       REDUCE(s = "", a IN authors | s + CASE WHEN s = "" THEN a ELSE "; " + a END) AS authors_list
ORDER BY d.title
"""

results = run_query(query, driver)

results = pd.DataFrame(results)

def clean_string(value):
    if isinstance(value, str):
        # Normalize Unicode (fixes encoding issues)
        value = unicodedata.normalize("NFKD", value)
        # Remove all non-printable and control characters
        value = re.sub(r'[\x00-\x1F\x7F-\x9F]', '', value)
        # Remove non-ASCII characters (keep only standard English characters)
        value = re.sub(r'[^\x20-\x7E]', '', value)
        value = re.sub('[^a-zA-Z0-9:-; ]',' ',value)
    return value

results = results.astype(str).map(clean_string)

prior = pd.read_excel("documents2.xlsx")

results_new = pd.merge(prior[["id","Valid"]], results, how = "right", on = "id")
results_new.to_excel("documents.xlsx", index=False)
