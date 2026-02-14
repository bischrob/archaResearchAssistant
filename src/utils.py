# import re
# import os
# from pathlib import Path
# from neo4j import GraphDatabase
# import subprocess
# import json
# import pandas as pd
# from sentence_transformers import SentenceTransformer
# import fitz 
# import warnings
# import numpy as np

# def run_query(query, driver, parameters=None):
#     with driver.session() as session:
#         result = session.run(query, parameters)
#         return [dict(record) for record in result]

# class PDFDocument:
#     def __init__(self, pdf_path, metadata, driver, model_name="BAAI/BGE-M3", add_citations = True):
#         """
#         Initialize the PDFDocument class.
#         :param pdf_path: Path to the PDF file.
#         :param model_name: Sentence Transformer model for embeddings.
#         """

#         self.pdf_path = pdf_path
#         self.text = self.extract_text()
#         self.paragraphs = self.chunk_text()
#         self.model = SentenceTransformer(model_name)
#         self.embeddings = self.generate_embeddings()
#         self.driver = driver
#         self.citekey = metadata["citekey"]
#         self.year = metadata["year"]
#         self.author = metadata["author"]
#         self.editor = metadata["editor"]
#         self.title = metadata["title"]
#         self.add_citations = add_citations
#         self.filtered_citations_count = 0
       
#         if not self.title or pd.isna(self.title) or str(self.title).strip() == "":
#             raise ValueError("title cannot be empty")
        
#     def generate_citekey(self, name, year, title):
#         """
#         Generates a citation key using the first author's last name, the year, and the first 5 characters of the title.
#         :param name: The first author's last name.
#         :param year: The year of publication.
#         :param title: The title of the document.
#         :return: A generated citation key (string).
#         """
#         # Extract first 5 characters of the title (lowercase, remove spaces)
#         short_title = title[:5].strip().lower() if title else ""

#         # Generate the citation key
#         citekey = f"{name}{year}-{short_title}"

#         # Ensure there are no trailing hyphens
#         citekey = citekey.strip("-")

#         return citekey
    
#     def load_citation_examples(self, filename):
#         """
#         Loads citation examples from a file, removing empty lines and stripping whitespace.
#         """
#         file_path = Path(filename)
#         if not file_path.exists():
#             print(f"⚠️ Warning: {filename} not found, skipping...")
#             return []

#         with open(file_path, "r", encoding="utf-8") as f:
#             return [line.strip() for line in f.readlines() if line.strip()]


#     def extract_text(self):
#         """Extracts text from a PDF file."""
#         doc = fitz.open(self.pdf_path)
#         return "\n".join(page.get_text() for page in doc)


#     def chunk_text(self):
#         """
#         Splits text into paragraphs based on:
#         - Empty lines.
#         - Lines shorter than 95% of the median line length.
#         """
#         lines = self.text.split("\n")  # Split into lines
#         lines_stripped = [line.strip() for line in lines if line.strip()]  # Remove empty lines
#         line_lengths = [len(line) for line in lines_stripped]

#         if not line_lengths:
#             return []  # If no valid lines, return an empty list

#         # ✅ Compute median and apply 95% threshold
#         med = np.median(line_lengths) * 0.95

#         paragraphs = []
#         temp_paragraph = []

#         for line in lines:
#             line = line.strip()

#             # ✅ Start a new paragraph if:
#             # - Line is empty
#             # - Line is shorter than 95% of the median
#             if not line or len(line) < med:
#                 if temp_paragraph:  # Avoid adding empty paragraphs
#                     paragraphs.append(" ".join(temp_paragraph))
#                     temp_paragraph = []
#             else:
#                 temp_paragraph.append(line)

#         # ✅ Add the last paragraph if it exists
#         if temp_paragraph:
#             paragraphs.append(" ".join(temp_paragraph))

#         return paragraphs


    
#     def generate_embeddings(self):
#         """Generates embeddings for each paragraph."""
#         return [self.model.encode(p).tolist() for p in self.paragraphs]
    
#     def detect_citations(self, threshold=0.5):
#         """
#         Identifies which paragraphs are likely citations by:
#         1. Filtering out anything similar to bad citations.
#         2. Keeping paragraphs where similarity to good citations is higher than similarity to bad citations.
#         """

#         # Load good & bad citation examples
#         good_examples = self.load_citation_examples("example_citations.txt")
#         bad_examples = self.load_citation_examples("bad_citations.txt")

#         # Encode examples
#         good_embeddings = self.model.encode(good_examples)
#         bad_embeddings = self.model.encode(bad_examples)

#         results = []

#         for i, para_embedding in enumerate(self.embeddings):
#             # Compute similarity with bad citations
#             bad_scores = np.dot(bad_embeddings, para_embedding) / (
#                 np.linalg.norm(bad_embeddings, axis=1) * np.linalg.norm(para_embedding)
#             ) if len(bad_embeddings) > 0 else [0]

#             # Compute similarity with good citations
#             good_scores = np.dot(good_embeddings, para_embedding) / (
#                 np.linalg.norm(good_embeddings, axis=1) * np.linalg.norm(para_embedding)
#             ) if len(good_embeddings) > 0 else [0]

#             max_good_score = max(good_scores)
#             max_bad_score = max(bad_scores)

#             # ✅ Keep only if similarity to good citations is higher than bad citations
#             is_citation = max_good_score > max_bad_score and max_good_score > threshold

#             results.append((self.paragraphs[i], is_citation))

#             if is_citation:
#                 print(f"✅ Paragraph {i+1} accepted as citation (Good Score: {max_good_score:.2f}, Bad Score: {max_bad_score:.2f}): {self.paragraphs[i][:50]}...")
#             else:
#                 print(f"❌ Paragraph {i+1} rejected (Good Score: {max_good_score:.2f}, Bad Score: {max_bad_score:.2f}): {self.paragraphs[i][:50]}...")

#         return results


    
#     def parse_citation_anystyle(self, citation_text):
#         """
#         Uses the Anystyle Docker container to parse a citation paragraph.
#         Ensures UTF-8 encoding and specifies an output file.
#         """
#         # Create a temporary input file

#         # Define file paths inside the shared Docker volume directory
#         temp_input_path = "tmp/tmp.txt"  # Ensure this directory is mounted to Anystyle
#         temp_output_path = "tmp/tmp_output.json"

#         # Write citation text to input file (overwrite mode)
#         with open(temp_input_path, "w", encoding="utf-8") as f:
#             f.write(citation_text)

#         # with open("example_citations.txt", "a", encoding="utf-8") as f:
#         #     f.write(f"\n{citation_text}\n")

#         # Run Anystyle with input and output file arguments
#         cmd = f"docker exec anystyle anystyle parse {temp_input_path} > {temp_output_path}"

#         try:
#             subprocess.run(cmd, shell=True, check=True)

#             # Read parsed output from the file
#             with open(temp_output_path, "r", encoding="utf-8") as f:
#                 parsed_data = json.load(f)

#             # Clean up temporary files
#             os.remove(temp_input_path)
#             os.remove(temp_output_path)

#             # Debugging Output
#             # print(f"📖 Parsed Citation Data: {parsed_data}")

#             return self.merge_citation_data(parsed_data)

#         except subprocess.CalledProcessError as e:
#             print(f"❌ Anystyle command failed: {e}")
#         except json.JSONDecodeError:
#             print("❌ Anystyle did not return valid JSON.")
#         except Exception as e:
#             print(f"❌ Error parsing citation with Anystyle: {e}")

#         # Ensure files are cleaned up even if an error occurs
#         finally:
#             if os.path.exists(temp_input_path):
#                 os.remove(temp_input_path)
#             if os.path.exists(temp_output_path):
#                 os.remove(temp_output_path)

#         return None
    
#     def merge_citation_data(self, parsed_data):
#         """
#         Merges fragmented citation data into a single structured dictionary.
#         """
#         citation = {
#             "title": "",
#             "year": None,
#             "author": [],
#             "editor": [],
#             "journal": "",
#             "volume": "",
#             "pages": "",
#             "doi": "",
#             "url": ""
#         }

#         for entry in parsed_data:
#             # Merge Titles
#             if "title" in entry:
#                 citation["title"] += " ".join(entry["title"]) + " "

#             # Merge Authors
#             if "author" in entry:
#                 citation["author"].extend(entry["author"])

#             # Merge Editors
#             if "editor" in entry:
#                 citation["editor"].extend(entry["editor"])

#             # Merge Date
#             if "date" in entry and isinstance(entry["date"], list) and entry["date"]:
#                 citation["year"] = entry["date"][0]  # Take first valid year

#             # Merge Journal Name
#             if "container-title" in entry:
#                 citation["journal"] += " ".join(entry["container-title"]) + " "

#             # Merge Volume
#             if "volume" in entry:
#                 citation["volume"] = entry["volume"][0] if isinstance(entry["volume"], list) else entry["volume"]

#             # Merge Pages
#             if "pages" in entry:
#                 citation["pages"] = entry["pages"][0] if isinstance(entry["pages"], list) else entry["pages"]

#             # Merge DOI
#             if "doi" in entry:
#                 citation["doi"] = entry["doi"][0] if isinstance(entry["doi"], list) else entry["doi"]

#             # Merge URL
#             if "url" in entry:
#                 citation["url"] = entry["url"][0] if isinstance(entry["url"], list) else entry["url"]

#         # Trim extra spaces
#         citation["title"] = citation["title"].strip()
#         citation["journal"] = citation["journal"].strip()

#         return citation



#     def upload_people(self, people_list, metadata, relationship):
#         """
#         Reusable function to upload authors and editors to Neo4j.
#         :param session: Neo4j session
#         :param people_list: List of people (authors or editors)
#         :param metadata: Document metadata dictionary
#         :param relationship: Relationship type ('AUTHOR' or 'EDITOR')
#         """
#         if isinstance(people_list, list) and people_list:
#             print(f"Uploading {relationship.lower()}s")
#             print(people_list)
#             people_df = pd.DataFrame(people_list)

#             # rename given to first and family to last
#             rename_map = {}
#             if "given" in people_df.columns:
#                 rename_map["given"] = "first"
#             if "family" in people_df.columns:
#                 rename_map["family"] = "last"

#             # ✅ Rename only existing columns
#             people_df.rename(columns=rename_map, inplace=True)

#             # ✅ Ensure necessary columns exist before applying .fillna()   
#             for col in ["formatted", "first", "last","initials"]:
#                 if col not in people_df.columns:
#                     people_df[col] = ""

#             people_df["formatted"] = people_df["formatted"].fillna("")
#             people_df["first"] = people_df["first"].fillna("")
#             people_df["last"] = people_df["last"].fillna("")
#             people_df["initials"] = people_df["initials"].fillna("")

#             # Update any empty or missing 'formatted' values
#             people_df["formatted"] = people_df.apply(
#                 lambda row: row["formatted"] if row["formatted"].strip() else (
#                     f"{row['first']} {row['last']}".strip()
#                     if row["first"] and row["last"]
#                     else f"{row['last']} {row['initials']}".strip()
#                     if row["last"]
#                     else f"Unknown {row['initials']}".strip()
#                     if row["initials"]
#                     else row['last']  # Fallback if all fields are empty
#                 ),
#                 axis=1
#             )

#             people_d = people_df.to_dict(orient="records")
#             with self.driver.session() as session:
#                 result = session.run(
#                     f"""
#                     UNWIND $people as people
#                     UNWIND $documents as documents
#                     MATCH (d:DOCUMENT {{citekey: documents.citekey}})
#                     MERGE (p:PERSON {{full: people.formatted}})
#                     SET p.first = people.first, p.last = people.last, p.initials = people.initials
#                     MERGE (d)<-[:{relationship}]-(p)
#                     RETURN COUNT(distinct p) AS count
#                     """,
#                     people=people_d,
#                     documents=[metadata]
#                 )
#                 count = result.single()["count"]
#                 print(f"Added {count} {relationship.lower()}(s) to document {metadata['citekey']}")
#         else:
#             print(f"No {relationship.lower()}s found.")

#     def upload_documents(self, documents, has_pdf = False):
#         with self.driver.session() as session:
#             # Store the document node
#             if has_pdf:
#                 label = ":PDF"
#             else:
#                 label = ""
#             result = session.run(
#                 f"""
#                 UNWIND $rows as row
#                 MERGE (d:DOCUMENT{label} {{citekey: row.citekey}})
#                 SET d.title = row.title, d.year = toInteger(row.year)
#                 RETURN d.title as title
#                 """,
#                 rows=documents
#             )
#             title = result.single()["title"]
#             print(f"Added '{title}' to Neo4j")
        
#     def upload_to_neo4j(self):
#         """
#         Uploads document, paragraphs, and citations to Neo4j.
#         """
#         if not self.citekey or pd.isna(self.citekey) or str(self.citekey).strip() == "":
#             warnings.warn("⚠️ 'citekey' is missing or blank. Generating a new citekey based on metadata.")

#             # Extract last name of the first author if available
#             last_name = ""
#             if "author" in self.author and isinstance(self.author , list) and self.author:
#                 last_name = self.author [0].get("last", "").strip()

#             self.citekey = self.generate_citekey(last_name, str(self.year), self.title)

#         self.upload_documents([{"citekey": self.citekey, "title": self.title, "year": self.year}], has_pdf=True)

#         self.upload_people(self.author,{"citekey": self.citekey}, "AUTHOR")
#         self.upload_people(self.editor,{"citekey": self.citekey}, "EDITOR")

#         # Detect citations
#         citation_results = self.detect_citations()

#         paragraphs_data = []
#         citations_data = []
#         citation_ids = set()  # Track citation paragraph numbers

#         for i, (paragraph, is_citation) in enumerate(citation_results):
#             paragraph_data = {
#                 "citekey": self.citekey,
#                 "text": paragraph,
#                 "paragraph_number": i + 1,
#                 "embedding": self.embeddings[i]
#             }
#             paragraphs_data.append(paragraph_data)

#             # ✅ FIX: Ensure citations are processed properly inside the loop
#             if is_citation:
#                 print(f"📖 Citation detected in paragraph {i+1}: {paragraph[:50]}...")
#                 citation_ids.add(i + 1)  # Mark paragraph as citation
                
#                 # ✅ FIX: Ensure Anystyle runs on every detected citation
#                 parsed_metadata = self.parse_citation_anystyle(paragraph)
#                 if parsed_metadata:
#                     # ✅ Extract first author's last name (family name)
#                     first_author_last = ""
#                     if isinstance(parsed_metadata.get("author", []), list) and parsed_metadata["author"]:
#                         first_author_last = parsed_metadata["author"][0].get("family", "").strip()

#                     # ✅ Extract year and title
#                     year = parsed_metadata.get("year", None)
#                     title = parsed_metadata.get("title", "").strip()  # Ensure title is stripped

#                     # ✅ Check if title is empty and filter out bad citations
#                     if not title or not first_author_last:
#                         print(f"❌ Skipping citation {i+1}: No title found.")
#                         self.filtered_citations_count += 1  # Track removed citations
#                         title = ""
#                     else:
#                         # ✅ Generate the citation key with extracted values
#                         citation_key = self.generate_citekey(first_author_last, year, title)
                        
#                         citation_data = {
#                             "citekey": citation_key,
#                             "text": paragraph,
#                             "paragraph_number": i + 1,
#                             "embedding": self.embeddings[i],
#                             "title": title,
#                             "year": year,
#                             "author": parsed_metadata.get("author", []),
#                             "editor": parsed_metadata.get("editor", []),
#                             "doi": parsed_metadata.get("doi", ""),
#                         }
#                         citations_data.append(citation_data)

#                 # ✅ Print how many citations were filtered
#                 if self.filtered_citations_count > 0:
#                     print(f"⚠️ {self.filtered_citations_count} citations were removed due to missing titles.")

#                 # ✅ Filter out citations where title is missing
#                 filtered_citations_data = [c for c in citations_data if c["title"].strip()]
#                 filtered_citation_count = len(citations_data) - len(filtered_citations_data)

#                 if filtered_citation_count > 0:
#                     print(f"⚠️ {filtered_citation_count} citations were removed due to missing titles.")

#                 # ✅ Update citation_ids after filtering
#                 filtered_citation_ids = {c["paragraph_number"] for c in filtered_citations_data}

#                 # Debugging: Confirm number of citations after filtering
#                 print(f"📖 Total Citations After Filtering: {len(filtered_citation_ids)}")
#                 print(f"📖 Citation Paragraph Numbers After Filtering: {list(filtered_citation_ids)}")

#                 # Store all paragraphs (both citations & non-citations)
#                 with self.driver.session() as session:
#                     session.run(
#                         """
#                         UNWIND $rows as row
#                         MATCH (d:DOCUMENT {citekey: row.citekey})
#                         MERGE (p:PARAGRAPH {text: row.text, paragraph_number: row.paragraph_number})
#                         MERGE (d)-[:HAS_PARAGRAPH]->(p)
#                         WITH p, row
#                         CALL db.create.setNodeVectorProperty(p, "embedding", row.embedding)
#                         """,
#                         rows=paragraphs_data
#                     )

#                     print(f"✅ Uploaded {len(paragraphs_data)} paragraphs.")

#                     # ✅ Label detected citations properly
#                     if filtered_citation_ids:
#                         session.run(
#                             """
#                             UNWIND $rows as row
#                             MATCH (p:PARAGRAPH {paragraph_number: row.paragraph_number})<-[:HAS_PARAGRAPH]-(d:DOCUMENT {citekey: row.citekey})
#                             SET p:CITATION
#                             """,
#                             rows=[{"citekey": self.citekey, "paragraph_number": num} for num in filtered_citation_ids]
#                         )
#                         print(f"✅ Labeled {len(filtered_citation_ids)} paragraphs as CITATIONs.")

#                     # ✅ Ensure citations are stored properly in Neo4j
#                     if filtered_citations_data:
#                         documents_to_upload = [
#                             {"citekey": c["citekey"], "title": c["title"], "year": c["year"]}
#                             for c in filtered_citations_data
#                         ]

#                         self.upload_documents(documents_to_upload) 

#                         session.run(
#                             """
#                             UNWIND $rows as row
#                             MATCH (d:DOCUMENT {citekey: row.citekey})
#                             MERGE (c:CITATION {text: row.text, paragraph_number: row.paragraph_number})
#                             MERGE (d)-[:HAS_CITATION]->(c)
#                             """,
#                             rows=filtered_citations_data
#                         )
#                         print(f"✅ Uploaded {len(filtered_citations_data)} structured citations.")

#                 # Upload authors and editors for detected citations
#                 for citation in citations_data:
#                     self.upload_people(citation["author"], {"citekey": citation["citekey"]}, "AUTHOR")
#                     self.upload_people(citation["editor"], {"citekey": citation["citekey"]}, "EDITOR")



# class DBcleanup:
#     def __init__(self, driver):
#         self.driver = driver

#     def remove_empty(self, type):
#         if isinstance(type, str):
#             type = [type]
#         if not isinstance(type,list):
#             raise ValueError("type must be a string or a list")
        
#         if "PERSON" in type:
#             result = run_query("match (p:PERSON {last: '', first: ''}) detach delete p return count(*) as count", self.driver)
#             count = result[0].get("count")
#             print(f"Deleted {count} empty people")
#         for t in type:
#             if t in ["keep","orcid","scholar"]:
#                 run_query("match (p:PERSON) where p.scopus = [''] set p.scopus = NULL return count(*) as count", self.driver)
#                 count = result[0].get("count")
#                 print(f"Deleted {count} empty {t} properties")

#     def find_dups(self, type):
#         if type == "PERSON":
#             print("Getting potential duplicate PERSON nodes")
#             query = """
#             MATCH (p:PERSON)
#             return elementId(p) as id, toUpper(p.full) as full, toUpper(p.last) as last, toUpper(p.first) as first, toUpper(p.initials) as initials
#             """
#             names = run_query(query, self.driver)

#             names = pd.DataFrame(names)

#             duplicate_rows = names[names.duplicated(subset=['last', 'first'], keep=False)]
#             return duplicate_rows
#         elif type == "DOCUMENT":
#             print("Getting potential duplicate DOCUMENT nodes")
#             query = """
#             MATCH (d:DOCUMENT)<-[:AUTHOR]-(p:PERSON)
#             return elementId(d) as id, toUpper(d.title) as title, d.year as year, toUpper(p.full) as author
#             """

#             citations = run_query(query, self.driver)

#             citations = pd.DataFrame(citations)

#             duplicate_rows = citations[citations.duplicated(subset=['title', 'year', 'author'], keep=False)]
#             return duplicate_rows
#         else:
#             raise Exception("type must be DOCUMENT or PERSON")

        
#     def merge_dups(self, df, type):
#         if len(df) > 0:
#             print(f"merging {len(df)} duplicate records")
#             if type == "DOCUMENT":
#                 df = df[["title","year","author"]]
#                 df = df.drop_duplicates()
#                 df = df.reset_index()
#                 query = """
#                 unwind $rows as row
#                 MATCH (d:DOCUMENT)<-[:AUTHOR]-(p:PERSON)
#                 where toUpper(d.title) = toUpper(row.title) and d.year = row.year and toUpper(p.full) = toUpper(row.author)
#                 WITH row.index as index, collect(d) as nodes
#                 WHERE SIZE(nodes) > 1
#                 CALL apoc.refactor.mergeNodes(nodes, { properties: "discard", mergeRels: true }) YIELD node
#                 RETURN count(distinct index) AS count
#                 """
#                 result = run_query(query, self.driver, parameters = {"rows": df.to_dict(orient = "records")})
#                 count = result[0].get("count")
#                 print(f"Merged {count} {type}s")
#             elif type == "PERSON":
#                 df = df[["last","first"]]
#                 df = df.drop_duplicates()
#                 df = df.reset_index()
#                 query = """
#                 unwind $rows as row
#                 MATCH (p:PERSON)
#                 where toUpper(p.last) = toUpper(row.last) and toUpper(p.first) = toUpper(row.first)
#                 WITH row.index as index, collect(p) as nodes
#                 WHERE SIZE(nodes) > 1
#                 CALL apoc.refactor.mergeNodes(nodes, { properties: "discard", mergeRels: true }) YIELD node
#                 RETURN count(distinct index) AS count
#                 """
#                 result = run_query(query, self.driver, parameters = {"rows": df.to_dict(orient = "records")})
#                 count = result[0].get("count")
#                 print(f"Merged {count} {type}s")
#             else: 
#                 raise ValueError("type must be DOCUMENT or PERSON")
#         else: 
#             print("Nothing to merge")


#     def update_metadata(self, df):
#         df = df.fillna("")
#         query = """
#         unwind $rows as row
#         match (p:PERSON {last: row.last, first: row.first, initials: row.initials})
#         set p.scholar = row.scholar, p.orcid = row.orcid, p.scopus = split(toString(row.scopus),"|"), p.keep = toInteger(row.keep)
#         return p.full, p.scholar
#         """
#         result = run_query(query, self.driver, parameters={"rows":df.to_dict(orient="records")})
#         print(result)

#     def merge_people_by_id(self, merge_id):
#         if merge_id not in ["scholar", "orcid", "scopus"]:
#             raise ValueError("merge_id must be one of ['scholar', 'orcid', 'scopus']")
        
#         if merge_id == "scopus":
#             query = """
#             MATCH (p:PERSON)
#             WHERE p.scopus IS NOT NULL
#             UNWIND p.scopus AS identifier  // Flatten list of scopus IDs
#             WITH identifier, COLLECT(p) AS nodes
#             WHERE SIZE(nodes) > 1  // Ensure there are duplicates to merge

#             // Identify the preferred node to keep (the one where keep = true)
#             WITH identifier, nodes, 
#                 [n IN nodes WHERE n.keep = true] AS preferred_nodes

#             // Pick the primary node: preferred if available, otherwise any arbitrary node
#             WITH identifier, 
#                 CASE WHEN SIZE(preferred_nodes) > 0 THEN preferred_nodes[0] ELSE nodes[0] END AS primary_node,
#                 nodes

#             CALL apoc.refactor.mergeNodes(nodes, { properties: "discard", mergeRels: true }) YIELD node

#             // Set the correct primary node explicitly
#             SET node += properties(primary_node)

#             // Remove the keep property from the merged node
#             REMOVE node.keep

#             RETURN count(distinct identifier) AS count
#             """
#             result = run_query(query, self.driver)
#             count = result[0].get("count")
#             print(f"Merged {count} {type}s")
#         else:
#             # Standard merging for scholar and orcid
#             query = f"""
#             MATCH (p:PERSON)
#             WHERE p.{merge_id} IS NOT NULL
#             WITH p.{merge_id} AS identifier, COLLECT(p) AS nodes
#             WHERE SIZE(nodes) > 1

#             // Identify the preferred node to keep (the one where keep = true)
#             WITH identifier, nodes, 
#                 [n IN nodes WHERE n.keep = true] AS preferred_nodes

#             // Pick the primary node: preferred if available, otherwise any arbitrary node
#             WITH identifier, 
#                 CASE WHEN SIZE(preferred_nodes) > 0 THEN preferred_nodes[0] ELSE nodes[0] END AS primary_node,
#                 nodes

#             CALL apoc.refactor.mergeNodes(nodes, {{ properties: "discard", mergeRels: true }}) YIELD node

#             // Set the correct primary node explicitly
#             SET node += properties(primary_node)

#             // Remove the keep property from the merged node
#             REMOVE node.keep

#             RETURN count(distinct identifier) AS count
#             """
#             result = run_query(query, self.driver)
#             count = result[0].get("count")
#             print(f"Merged {count} {type}s")
    
#         result = run_query(query, driver = self.driver)
#         print(result)
        
