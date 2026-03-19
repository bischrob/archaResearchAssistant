# Research Assistant Documentation Vault

Last reviewed: 2026-03-19

## Purpose
This vault is a full project review for `/home/rjbischo/researchAssistant`, optimized for:
- fast troubleshooting
- safe feature extension
- quick onboarding for humans and LLM agents

## How to use this vault
1. Start with [[00_Project/01_project_overview]].
2. For agent execution workflow, use [[00_Project/12_llm_agent_playbook]].
3. Jump to architecture notes in `Vault/10_Backend/` and API notes in `Vault/20_WebAPI/`.
4. Use [[60_Troubleshooting/01_symptom_to_cause_matrix]] for operational failures.
5. Use `Vault/70_Feature_Playbooks/` before adding new features.

## Sections
- Project context: `Vault/00_Project/`
- Backend modules: `Vault/10_Backend/`
- Web API surface: `Vault/20_WebAPI/`
- Frontend behavior: `Vault/30_Frontend/`
- Scripts and services: `Vault/40_Scripts/`
- Tests and quality: `Vault/50_Testing/`
- Troubleshooting and risks: `Vault/60_Troubleshooting/`
- Feature playbooks: `Vault/70_Feature_Playbooks/`
- Appendix and hotspots: `Vault/99_Appendix/`

## Note Index
- [[00_Project/01_project_overview]]
- [[00_Project/02_repository_map]]
- [[00_Project/03_runtime_and_config]]
- [[00_Project/04_data_and_storage]]
- [[00_Project/05_startup_runbook]]
- [[00_Project/06_ancillary_content]]
- [[00_Project/12_llm_agent_playbook]]
- [[00_Project/13_reusability_todo_2026-03-19]]
- [[10_Backend/01_settings_and_config_module]]
- [[10_Backend/02_metadata_matching_module]]
- [[10_Backend/03_pdf_processing_module]]
- [[10_Backend/04_ingest_pipeline_module]]
- [[10_Backend/05_graph_store_module]]
- [[10_Backend/06_retrieval_module]]
- [[10_Backend/07_llm_grounding_module]]
- [[10_Backend/08_answer_audit_export_module]]
- [[20_WebAPI/01_api_surface]]
- [[20_WebAPI/02_job_manager]]
- [[20_WebAPI/03_sync_api]]
- [[20_WebAPI/04_ingest_api]]
- [[20_WebAPI/05_query_and_ask_api]]
- [[20_WebAPI/06_diagnostics_api]]
- [[20_WebAPI/08_api_reference]]
- [[20_WebAPI/09_citation_lookup_quickstart]]
- [[30_Frontend/01_ui_structure]]
- [[30_Frontend/02_ui_client_logic]]
- [[40_Scripts/01_cli_scripts]]
- [[40_Scripts/02_shell_scripts]]
- [[40_Scripts/03_docker_services]]
- [[50_Testing/01_test_overview]]
- [[50_Testing/02_current_test_status_2026-02-21]]
- [[60_Troubleshooting/01_symptom_to_cause_matrix]]
- [[60_Troubleshooting/02_known_risks_and_debt]]
- [[60_Troubleshooting/03_performance_notes]]
- [[70_Feature_Playbooks/01_add_api_endpoint]]
- [[70_Feature_Playbooks/02_add_retrieval_signal]]
- [[70_Feature_Playbooks/03_add_ingest_metadata_field]]
- [[70_Feature_Playbooks/04_add_ui_workflow]]
- [[99_Appendix/01_glossary]]
- [[99_Appendix/02_file_hotspots]]

## Canonical source files
- Backend: `src/rag/`
- API: `webapp/main.py`
- Frontend: `webapp/static/index.html`, `webapp/static/app.js`, `webapp/static/styles.css`
- CLI scripts: `scripts/*.py`
- Ops scripts: `start.sh`, `scripts/*.sh`, `docker-compose.yml`
- Tests: `tests/*.py`
