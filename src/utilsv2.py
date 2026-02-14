import pandas as pd
from neo4j import GraphDatabase

# model_name="BAAI/BGE-M3"
# model = SentenceTransformer(model_name)
def run_query(query, driver, parameters=None):
    with driver.session() as session:
        result = session.run(query, parameters)
        return [dict(record) for record in result]
    
def upload_people(people_list, relationship, driver):
        """
        Reusable function to upload authors and editors to Neo4j.
        :param people_list: List of people (authors or editors)
        :param relationship: Relationship type ('AUTHOR' or 'EDITOR')
        """
        if isinstance(people_list, list) and people_list:
            print(f"Uploading {relationship.lower()}s")
            print(people_list)
            people_df = pd.DataFrame(people_list)

            # rename given to first and family to last
            rename_map = {}
            if "given" in people_df.columns:
                rename_map["given"] = "first"
            if "family" in people_df.columns:
                rename_map["family"] = "last"

            # ✅ Rename only existing columns
            people_df.rename(columns=rename_map, inplace=True)

            # ✅ Ensure necessary columns exist before applying .fillna()   
            for col in ["formatted", "first", "last","initials"]:
                if col not in people_df.columns:
                    people_df[col] = ""

            people_df["formatted"] = people_df["formatted"].fillna("")
            people_df["first"] = people_df["first"].fillna("")
            people_df["last"] = people_df["last"].fillna("")
            people_df["initials"] = people_df["initials"].fillna("")
            
            people_df = people_df.drop_duplicates(subset=['formatted'], keep='first')
            people_dict = people_df.to_dict(orient='records')
            query = f"""
            unwind $rows as row
            merge (p:PERSON {{formatted: row.formatted}})
            set p.initials= row.initials, p.first= row.first, p.last= row.last, ==
            return elementId(p) as id, p.formatted as formatted
            """
            result = run_query(query, driver, parameters = {"rows": people_dict})
            return pd.DataFrame(result)
