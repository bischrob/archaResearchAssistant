# Glossary

## Article
A paper-level node in Neo4j representing one PDF/document.

## Chunk
A fixed-size overlapping text segment extracted from article main body.

## Token
A normalized term mentioned in a chunk with frequency count.

## Reference
A citation/reference entry parsed from an article references section.

## CITES
Relationship from one `Article` to another inferred by reference-title match or fallback heuristics.

## RAG
Retrieval-augmented generation; answer is generated from retrieved context blocks.

## Citation block (`[C#]`)
Identifier assigned to each retrieved chunk when constructing LLM context.

## Ingest modes
- `batch`: first N readable eligible PDFs.
- `all`: all eligible PDFs in API-driven batches.
- `custom`: explicit PDF path list.
- `test3`: alias of `batch`.
