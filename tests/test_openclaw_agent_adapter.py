from __future__ import annotations

import importlib.util
import json
from pathlib import Path


MODULE_PATH = Path("/home/rjbischo/researchAssistant/scripts/openclaw_agent_adapter.py")
spec = importlib.util.spec_from_file_location("openclaw_agent_adapter", MODULE_PATH)
openclaw_agent_adapter = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(openclaw_agent_adapter)


def test_parse_node_major_handles_version_prefix() -> None:
    assert openclaw_agent_adapter._parse_node_major("v24.13.1") == 24
    assert openclaw_agent_adapter._parse_node_major("22.12.0") == 22
    assert openclaw_agent_adapter._parse_node_major("") is None


def test_build_openclaw_command_prefers_modern_node(monkeypatch, tmp_path) -> None:
    openclaw_bin = tmp_path / "openclaw"
    openclaw_bin.write_text("#!/bin/sh\n")
    node_modules = tmp_path / "node_modules" / "openclaw"
    node_modules.mkdir(parents=True)
    script_path = node_modules / "openclaw.mjs"
    script_path.write_text("console.log('ok')\n")

    monkeypatch.setattr(openclaw_agent_adapter, "_resolve_openclaw_bin", lambda: str(openclaw_bin))
    monkeypatch.setattr(openclaw_agent_adapter, "_resolve_node_bin", lambda min_major=22: "/opt/node-v24/bin/node")

    command = openclaw_agent_adapter._build_openclaw_command()

    assert command == ["/opt/node-v24/bin/node", str(script_path)]


def test_build_openclaw_command_falls_back_to_openclaw_shim(monkeypatch, tmp_path) -> None:
    openclaw_bin = tmp_path / "openclaw"
    openclaw_bin.write_text("#!/bin/sh\n")

    monkeypatch.setattr(openclaw_agent_adapter, "_resolve_openclaw_bin", lambda: str(openclaw_bin))
    monkeypatch.setattr(openclaw_agent_adapter, "_resolve_node_bin", lambda min_major=22: None)

    command = openclaw_agent_adapter._build_openclaw_command()

    assert command == [str(openclaw_bin)]


def test_grounded_answer_prefers_bounded_openai_fallback(monkeypatch) -> None:
    monkeypatch.delenv("OPENCLAW_GROUNDED_ANSWER_MODE", raising=False)
    monkeypatch.setattr(openclaw_agent_adapter, "_invoke_openclaw_agent_once", lambda **kwargs: (_ for _ in ()).throw(AssertionError("should not call openclaw")))
    monkeypatch.setattr(
        openclaw_agent_adapter,
        "_invoke_openai_responses",
        lambda **kwargs: json.dumps({
            "answer": "Bounded answer [C1]",
            "relevant_citation_ids": ["C1"],
            "excluded_citation_ids": [],
            "relevance_summary": "Used 1 of 1 retrieved results after relevance filtering.",
            "synthesis_status": "succeeded",
        }),
    )

    text = openclaw_agent_adapter._run_task(
        "grounded_answer",
        {"question": "What projectile points are found in Arizona?", "fallback": {"context": "[C1] Example evidence"}},
    )

    payload = json.loads(text)
    assert payload["answer"] == "Bounded answer [C1]"
    assert payload["relevant_citation_ids"] == ["C1"]


def test_grounded_answer_can_try_openclaw_then_fallback(monkeypatch) -> None:
    monkeypatch.setenv("OPENCLAW_GROUNDED_ANSWER_MODE", "prefer-agent")
    monkeypatch.setattr(openclaw_agent_adapter, "_invoke_openclaw_agent_once", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("timed out")))
    monkeypatch.setattr(
        openclaw_agent_adapter,
        "_invoke_openai_responses",
        lambda **kwargs: json.dumps({
            "answer": "Recovered answer [C2]",
            "relevant_citation_ids": ["C2"],
            "excluded_citation_ids": ["C1"],
            "relevance_summary": "Used 1 of 2 retrieved results after relevance filtering.",
            "synthesis_status": "succeeded",
        }),
    )

    text = openclaw_agent_adapter._run_task(
        "grounded_answer",
        {"question": "Q", "fallback": {"context": "[C1] Noise\n[C2] Evidence"}},
    )

    payload = json.loads(text)
    assert payload["answer"] == "Recovered answer [C2]"
    assert payload["excluded_citation_ids"] == ["C1"]


def test_grounded_answer_reports_both_failures(monkeypatch) -> None:
    monkeypatch.setenv("OPENCLAW_GROUNDED_ANSWER_MODE", "prefer-agent")
    monkeypatch.setattr(openclaw_agent_adapter, "_invoke_openclaw_agent_once", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("timed out")))
    monkeypatch.setattr(openclaw_agent_adapter, "_invoke_openai_responses", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("quota")))

    try:
        openclaw_agent_adapter._run_task(
            "grounded_answer",
            {"question": "Q", "fallback": {"context": "[C1] Evidence"}},
        )
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("expected RuntimeError")

    assert "openclaw: timed out" in message
    assert "openai_fallback: quota" in message
