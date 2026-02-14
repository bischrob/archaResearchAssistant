# Research Assistant RAG (Neo4j)

This project now includes a clean, local pipeline to:

- Ingest PDF articles into Neo4j
- Chunk and tokenize article text
- Store chunk embeddings for semantic retrieval
- Extract references and link article-to-article citations
- Retrieve context with author + citation neighborhood

## 1) Start Neo4j

```bash
docker compose up -d neo4j
```

Default connection values (can be overridden by env vars):

- `NEO4J_URI=bolt://localhost:7687`
- `NEO4J_USER=neo4j`
- `NEO4J_PASSWORD=archaResearchAssistant`

## 2) Build graph from 3 PDFs

By default this uses the first 3 files in `pdf2epub/input`.

```bash
python scripts/build_graph.py --wipe
```

Or provide explicit test PDFs:

```bash
python scripts/build_graph.py --wipe \
  --pdf pdf2epub/input/aikens1961-PrehistoryOfCentralNorthernUtah.pdf \
  --pdf pdf2epub/input/aikens1964-UintaBasinPrehistory.pdf \
  --pdf pdf2epub/input/aikens1965-PreliminaryReportOnExcavationsAtInjunCreekSite,Warren,Utah.pdf
```

## 3) Query with contextual retrieval

```bash
python scripts/query_graph.py "fremont culture chronology"
```

Returned results include:

- matched chunk text
- article and author
- outgoing and incoming citation context

