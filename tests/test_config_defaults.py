from rag.config import Settings


def test_default_neo4j_password_matches_repo_compose_default(monkeypatch):
    monkeypatch.delenv("NEO4J_PASSWORD", raising=False)
    settings = Settings()
    assert settings.neo4j_password == "archaResearchAssistant"
