# File Hotspots

## Highest-change-risk files
- `webapp/main.py`
- `src/rag/neo4j_store.py`
- `src/rag/pipeline.py`
- `src/rag/retrieval.py`
- `webapp/static/app.js`

## Why these are hotspots
- They contain orchestration logic across many subsystems.
- Small changes can affect ingest, query, and UI behavior simultaneously.
- They are highly referenced by tests and runtime workflows.

## Suggested review order for incidents
1. `webapp/main.py` (request flow and error mapping)
2. `src/rag/pipeline.py` (selection and ingest execution)
3. `src/rag/neo4j_store.py` (query/write correctness)
4. `src/rag/retrieval.py` (ranking behavior)
5. `src/rag/llm_answer.py` (grounding and preprocessing)

## Useful companion notes
- [[60_Troubleshooting/01_symptom_to_cause_matrix]]
- [[50_Testing/02_current_test_status_2026-02-21]]
