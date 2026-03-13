# Reference LoRA Gold Dataset

## Purpose
- Stores article-level gold reference outputs for LoRA supervision.

## Data File
- `data/reference_lora_gold_articles.json`

## Current Records
- `aikens1971-1971-Adovasio-SomeCommentsOnTheRelationshipOfGreatBasinTextilesToTextilesFromTheSouthwest`
- `allison2008-HumanEcologyAndSocialTheoryInUtahArchaeology`

## Notes
- Format is one JSON document with `records[]`.
- Each record stores `expected_references` in CSL-like JSON from user-provided gold labels.
