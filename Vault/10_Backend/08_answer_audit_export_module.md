# Backend Module: Answer Audit and Export

## Source files
- `src/rag/answer_audit.py`
- `src/rag/report_export.py`

## Responsibility
Estimate grounding risk from citation overlap and produce export artifacts.

## Audit behavior
- Splits answer into sentences.
- Computes token overlap between each sentence and concatenated cited chunk text.
- Sentences with zero overlap counted as unsupported.
- Risk score combines unsupported ratio plus no-citation penalty.
- Labels: `low`, `medium`, `high`.

## Export behavior
- Markdown report includes question/model/risk and used citations.
- CSV export includes citation metadata row set.
- PDF export shells out to `pandoc` and tries engines in order:
  - default, `wkhtmltopdf`, `weasyprint`, `xelatex`, `pdflatex`.

## Failure modes
- Audit is lexical; can mark paraphrased support as unsupported.
- PDF export fails if pandoc or engines unavailable.

## Extension points
- Replace lexical audit with entailment/similarity model.
- Add JSON export for machine pipelines.
- Add report signing/checksum for reproducibility.

## Related
- [[20_WebAPI/05_query_and_ask_api]]
- [[60_Troubleshooting/01_symptom_to_cause_matrix]]
