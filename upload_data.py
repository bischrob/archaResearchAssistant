# from src import *
from neo4j import GraphDatabase
import pandas as pd
from pathlib import Path
import os

from tomlkit import key

driver = GraphDatabase.driver(
    os.getenv("NEO4J_URI", "bolt://localhost:7687"),
    auth=(os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD", "archaResearchAssistant")),
)

def run_query(query, driver, parameters=None):
    with driver.session() as session:
        result = session.run(query, parameters)
        return [dict(record) for record in result]
    

# print("testing")

# test = run_query("match (n) return count(*) as n", driver)
# test

paperpile = pd.read_json("paperpile.json")
paperpile.columns.tolist()

cols = ["_id","author", "editor", "published", "citekey", "title","attachments"]
cols = [col for col in cols if col in paperpile.columns]

paperpile_metadata = paperpile[cols].copy()
paperpile_metadata["year"] = paperpile_metadata["published"].apply(lambda x: int(x["year"]) if isinstance(x, dict) and "year" in x else None)
paperpile_metadata["filename"] = paperpile_metadata["attachments"].apply(
    lambda x: [item["filename"] for item in x if isinstance(item, dict) and "filename" in item] if isinstance(x, list) else []
)
paperpile_metadata["file_id"] = paperpile_metadata["attachments"].apply(
    lambda x: [item["_id"] for item in x if isinstance(item, dict) and "_id" in item] if isinstance(x, list) else []
)
paperpile_metadata = paperpile_metadata.explode("filename", ignore_index=True)
paperpile_metadata.drop(columns=["published","attachments"], inplace=True)
paperpile_metadata = paperpile_metadata.reset_index()

authors = paperpile_metadata[["index","author"]].copy()
df_exploded = authors.explode('author').reset_index(drop=True)
df = pd.json_normalize(df_exploded['author'])
authors = pd.concat([df_exploded.drop(columns=['author']), df], axis=1)
editors = paperpile_metadata[["index","editor"]].copy()
df_exploded = editors.explode('editor').reset_index(drop=True)
df = pd.json_normalize(df_exploded['editor'])
editors = pd.concat([df_exploded.drop(columns=['editor']), df], axis=1)
document = paperpile_metadata[["index","title","year","citekey","_id"]].copy()
document["title"] = (document['title']
                     .str.replace(r'[{}\n\t]', '', regex=True)
                     .str.upper())
# convert all to string
document = document.astype('str')
document['year'] = document['year'].apply(lambda x: str(x) if pd.notna(x) else "")
# convert all None values to ""
document = document.replace('None', '')

query = """
unwind $rows as row
merge (d:DOCUMENT {_id: row._id})
set d._id = row._id, d.title = row.title, d.year = row.year, d.citekey = row.citekey
with d set d.year = toInteger(d.year)
return d._id as _id, d.title as title, d.year as year, d.citekey as citekey
"""

document_result = run_query(query, driver, parameters = {"rows": document.to_dict(orient = "records")})

document_result = pd.DataFrame(document_result)
document_result = document_result.astype('str')
ids = pd.merge(document_result, document[['citekey','_id',"index"]], how = "left", on = ["citekey","_id"])

authors = authors.astype("str")
authors = authors.map(lambda x: str(x) if pd.notna(x) else None)
authors = authors.replace('nan', None)
authors['type'] = "author"

editors = editors.astype("str")
editors = editors.map(lambda x: str(x) if pd.notna(x) else None)
editors = editors.replace('nan', None)
editors['type'] = 'editor'

people = pd.concat([authors, editors], axis = 0)
people = people.drop_duplicates()
people = pd.merge(people, ids, how = "left", on = "index")
people.rename(columns={"_id":"document_id"},inplace = True)
people.loc[people['formatted'].isna(), 'formatted'] = people.loc[people['formatted'].isna(), 'collective']
people = people[~people["formatted"].isnull()]
people_f = people.drop_duplicates(subset=['formatted'], keep='first')

people_dict = people_f.drop(columns=["type"], inplace=False)
people_dict = people_dict.drop_duplicates()
people_dict = people_dict.map(lambda x: str(x) if pd.notna(x) else "")
people_dict = people_dict.to_dict(orient='records')
len(people_dict)

query = """
unwind $rows as row
merge (p:PERSON {formatted: row.formatted})
set p.initials= row.initials, p.first= row.first, p.last= row.last, p.jr= row.jr, p.collective= row.collective, p.level= row.level, p.bak= row.bak, p.orcid= row.orcid
return elementId(p) as id, p.formatted as formatted
"""

result = run_query(query, driver, parameters = {"rows": people_dict})
result = pd.DataFrame(result)
result = pd.merge(result, people, how = "left", on = "formatted")

author_rel = result[result["type"]=="author"].copy()
editor_rel = result[result["type"]=="editor"].copy()

author_rel[author_rel["id"].isnull()]
editor_rel[editor_rel["id"].isnull()]

query = """
unwind $rows as row
match (d:DOCUMENT) 
where d._id = row.document_id
match (p:PERSON)
where elementId(p) = row.id
with p,d
merge (p)-[:AUTHOR]->(d)
return count(*) as count
"""

result = run_query(query, driver, parameters = {"rows": author_rel.to_dict(orient = "records")})
print(result)

query = """
unwind $rows as row
match (d:DOCUMENT) 
where d._id = row.document_id
match (p:PERSON)
where elementId(p) = row.id
with p,d
merge (p)-[:EDITOR]->(d)
return count(*) as count
"""

result = run_query(query, driver, parameters = {"rows": editor_rel.to_dict(orient = "records")})
print(result)

# clean up
keys = run_query("match (p:PERSON) unwind keys(p) as key return distinct key", driver)
keys = [val for d in keys for val in d.values()]
for key in keys:
    query = f"match (p:PERSON) where p.{key} = '' set p.{key} = null return '{key}' as key, count(p) as count"
    
    run_query(query, driver)
        
run_query("match (p:PERSON) where p.formatted is null detach delete p", driver)

existing_documents = run_query("match (d:DOCUMENT) return d._id as id, d.citekey as citekey", driver)
existing_documents = pd.DataFrame(existing_documents)

paperpile = pd.read_json("paperpile.json")
len(paperpile)
paperpile = paperpile[paperpile['citekey'].isin(existing_documents['citekey'])]
len(paperpile)

# combine authors
author_list = pd.read_excel("authors.xlsx")
cols_to_check = ['scholar', 'orcid', 'scopus']
# Create the new column
author_list['primary_id'] = author_list[cols_to_check].bfill(axis=1).iloc[:, 0]
author_list = author_list.groupby('primary_id').agg(list).reset_index()
for i, row in author_list.iterrows():
    print(f"Processing row {i+1} of {len(author_list)}")
    
    # 1. Convert the single row (Series) to a DataFrame and Transpose it
    # 2. Explode the columns as a DataFrame
    # 3. Now to_dict(orient='records') will work perfectly
    df_row = pd.DataFrame([row]) 
    exploded_df = df_row.explode('first').explode('last')
    
    rows_data = exploded_df.to_dict(orient='records')

    query = """
    UNWIND $rows as row
    MATCH (p:PERSON)
    WHERE p.first = row.first AND p.last = row.last
    RETURN DISTINCT elementId(p) as id, p.formatted as formatted, p.first as first, p.last as last
    """
    
    result = run_query(query, driver, parameters={"rows": rows_data})
    
    if len(result) > 1:
        # Keep the first PERSON node and merge others into it
        primary_id = result[0]['id']
        for person in result[1:]:
            duplicate_id = person['id']
            merge_query = """
            MATCH (p1:PERSON), (p2:PERSON)
            WHERE elementId(p1) = $primary_id AND elementId(p2) = $duplicate_id
            // Merge relationships from p2 to p1
            CALL apoc.refactor.mergeNodes([p1, p2]) YIELD node
            RETURN node
            """
            run_query(merge_query, driver, parameters={"primary_id": primary_id, "duplicate_id": duplicate_id})
        print(f"Merged {len(result)-1} duplicate PERSON nodes into {primary_id}")

# # _id to pdfs
# from PyPDF2 import PdfReader, PdfWriter
# from pathlib import Path

# for i in range(0, len(paperpile)):
#     try:

#         print(f"{i} of {len(paperpile_metadata)}")
#         document = paperpile_metadata.loc[i]
#         pdf = document["filename"]
#         print(pdf)
#         src = Path("pdfs") / pdf
#         pdf_uuid =  document["_id"]
#         reader = PdfReader(src)
#         writer = PdfWriter()
#         for page in reader.pages:
#             writer.add_page(page)

#         # Add metadata including UUID
#         metadata = reader.metadata or {}
#         metadata.update({"/UUID": pdf_uuid})
#         writer.add_metadata(metadata)

#         # Save PDF with metadata
#         with open(src, "wb") as f:
#             writer.write(f)

#     except Exception as e:
#         print(f"Error: {e}")

# from src.make_chunks_no_refs import *

# # === Run on All PDFs in Parallel ===
# pdf_root = "pdfs"

# pdf_files = list(find_all_pdfs(pdf_root))
# json_files = list(find_all_jsons("jsons"))
# # # Extract just the base filenames (without extension or directory)
# # pdf_basenames = {os.path.splitext(os.path.basename(f))[0] for f in pdf_files}
# # json_basenames = {os.path.splitext(os.path.basename(f))[0] for f in json_files}

# # # Files that exist as PDFs but not as JSONs
# # missing_json_basenames = pdf_basenames - json_basenames

# # # Get the full paths of these PDFs for processing
# # todo = [f for f in pdf_files if os.path.splitext(os.path.basename(f))[0] in missing_json_basenames]
# # todo
# # print(f"Number of PDFs to process: {len(todo)}")
# # create_chunks(todo, parallel=True, num_workers = 4)

# pdf_files = list(find_all_pdfs(pdf_root))
# json_files = list(find_all_jsons("jsons"))
# # Extract just the base filenames (without extension or directory)
# pdf_basenames = [os.path.splitext(os.path.basename(f))[0] for f in pdf_files]
# json_basenames = [os.path.splitext(os.path.basename(f))[0] for f in json_files]
# pdf_df = pd.DataFrame()
# pdf_df["pdf_path"] = pdf_files
# pdf_df['basenames'] = pdf_basenames
# pdfs = paperpile_metadata[["_id","filename","file_id"]].copy()
# pdfs = pdfs[~pdfs["filename"].isna()]
# pdfs['basenames'] = pdfs['filename'].apply(lambda f: os.path.splitext(os.path.basename(f))[0])
# pdfs = pd.merge(pdfs,pdf_df, how = "left", on = "basenames")
# pdfs = pdfs.drop(columns = ["filename"])
# pdfs = pdfs.explode('file_id').reset_index(drop=True)
# pdfs = pdfs.drop_duplicates()
# json_df = pd.DataFrame()
# json_df["json_path"] = json_files
# json_df["basenames"] = json_basenames
# pdfs = pd.merge(pdfs,json_df, how = "left", on = "basenames")

# # pdfs.to_pickle("pdfs.pkl")

# # json_chunks = []

# # for json_chunk in pdfs["json_path"].values:
# #     if json_chunk and not pd.isna(json_chunk):
# #         print(json_chunk)
# #         data = pd.read_json(json_chunk)
# #         data['json_path'] = json_chunk
# #         json_chunks.append(data)

# # chunks_df = pd.concat(json_chunks)

# # save chunks_df as pickle
# chunks_df = chunks_df.reset_index(drop=True)

# pdfs
# chunks_df.columns
# upload = pdfs[["_id","json_path","file_id"]]
# upload = pd.merge(upload,chunks_df, how="left",on="json_path")

# import pickle
# with open("upload.pkl", "wb") as f:
#     pickle.dump(upload, f)
