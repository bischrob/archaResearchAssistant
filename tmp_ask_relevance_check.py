from src.rag.llm_answer import ask_openclaw_grounded

rows = [
    {
        "chunk_id": "rel1",
        "chunk_text": "Binford argues that archaeology should function as anthropology and focus on explanation.",
        "article_title": "Archaeology as Anthropology",
        "article_year": 1962,
        "authors": ["Lewis Binford"],
    },
    {
        "chunk_id": "noise1",
        "chunk_text": "Marine chemistry measurements of salinity and isotope variation in the North Atlantic.",
        "article_title": "Ocean Salinity Study",
        "article_year": 2021,
        "authors": ["A. Ocean"],
    },
]

print(ask_openclaw_grounded("What did Binford argue about archaeology?", rows))
