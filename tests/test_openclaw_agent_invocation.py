from __future__ import annotations

import json
import os
import sys

from src.rag import openclaw_agent
from src.rag.config import Settings


def test_prepare_command_wraps_python_scripts() -> None:
    prepared = openclaw_agent._prepare_command('/home/rjbischo/researchAssistant/scripts/openclaw_agent_adapter.py --flag value')
    assert prepared[0] == sys.executable
    assert prepared[1:] == [
        '/home/rjbischo/researchAssistant/scripts/openclaw_agent_adapter.py',
        '--flag',
        'value',
    ]


def test_prepare_command_leaves_non_python_command_unchanged() -> None:
    prepared = openclaw_agent._prepare_command('openclaw agent --message hello')
    assert prepared == ['openclaw', 'agent', '--message', 'hello']


def test_invoke_openclaw_agent_runs_python_script_via_interpreter(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_run(command, **kwargs):
        captured['command'] = command
        captured['env'] = kwargs['env']
        captured['input'] = kwargs['input']

        class _Proc:
            returncode = 0
            stdout = json.dumps({'directive': 'authors: none | years: none | title_terms: none | content_terms: test'})
            stderr = ''

        return _Proc()

    monkeypatch.setattr(openclaw_agent.subprocess, 'run', _fake_run)
    settings = Settings(openclaw_agent_command='/home/rjbischo/researchAssistant/scripts/openclaw_agent_adapter.py')

    result = openclaw_agent.invoke_openclaw_agent('query_preprocess', {'question': 'test'}, settings=settings)

    assert result == {'directive': 'authors: none | years: none | title_terms: none | content_terms: test'}
    assert captured['command'][0] == sys.executable
    assert captured['command'][1] == '/home/rjbischo/researchAssistant/scripts/openclaw_agent_adapter.py'
    assert captured['env']['OPENCLAW_AGENT_TASK'] == 'query_preprocess'
    assert json.loads(captured['input']) == {'question': 'test'}


def test_adapter_script_is_checked_in_with_lf_only() -> None:
    path = '/home/rjbischo/researchAssistant/scripts/openclaw_agent_adapter.py'
    with open(path, 'rb') as fh:
        data = fh.read()
    assert b'\r\n' not in data
    assert data.startswith(b'#!/usr/bin/env python3\n')
