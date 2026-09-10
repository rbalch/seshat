"""Acceptance tests for T-13: the Spark smoke checks (plan §8/§12).

Both tests below are marked `integration` and skipped when `LLM_HOST` is unset — see
`tasks/seshat-phase-one/T-13-spark-smoke.md`'s Acceptance section, bullets 1-2. The
live `VerifierAuthor.author` and `Worker.survey` checks already exist as
`integration`-marked tests (`tests/agents/test_verifier_author.py`,
`tests/agents/test_worker.py`); this module does not repeat them and `-m integration`
runs all four together.

Each test's failure message names which of the two checks it is, per the task's
Acceptance bullet 2 ("a failure whose message names which of the two checks failed"),
so a human running this on the Spark gets a report they can act on without reading the
traceback.

`test_no_thinking_reaches_the_wire_as_chat_template_kwargs` does not need the real
Spark to be meaningful: it points a `CompletionClient` at a local recording HTTP stub
this module starts and tears down itself, and inspects the literal JSON body litellm
sent over the wire -- a different claim than `tests/test_config.py:70`'s unit test,
which only checks `Settings.llm_kwargs` *constructs* the right dict, never that
anything downstream *sends* it. It stays gated behind `LLM_HOST` for consistency with
every other integration test in this suite (skip on presence, not on the value), which
also means it is runnable ahead of real Spark access by exporting any non-empty
`LLM_HOST`.

`test_smoke_agent_calls_both_tools_in_both_modes` has no such workaround: it drives
`scripts/smoke_codeact.py` against the real, ambient `LLM_HOST`, and whether a 27B
model reliably drives two-tool CodeAct is exactly the open question plan §8 raises. A
failure here is a finding about the model/strategy, not a bug in this test -- see the
task's Context and the module docstring of `scripts/smoke_codeact.py`.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import ClassVar

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = ROOT / 'scripts' / 'smoke_codeact.py'

pytestmark = pytest.mark.integration

skip_without_llm_host = pytest.mark.skipif(
    not os.getenv('LLM_HOST'), reason='needs a live LLM_HOST'
)


# -- test 1: the live two-tool CodeAct smoke, against the real ambient LLM_HOST -----


@skip_without_llm_host
def test_smoke_agent_calls_both_tools_in_both_modes() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, (
        'CHECK 1/2 FAILED (smoke agent tool-calls): '
        f'scripts/smoke_codeact.py exited {result.returncode}, expected 0. '
        f'stdout:\n{result.stdout}\nstderr:\n{result.stderr}'
    )
    for mode in ('thinking', 'no-thinking'):
        line = next((l for l in result.stdout.splitlines() if f'[{mode}]' in l), None)
        assert line is not None, (
            f'CHECK 1/2 FAILED (smoke agent tool-calls): no [{mode}] line in stdout:\n'
            f'{result.stdout}'
        )
        assert 'add_called=True' in line and 'lookup_called=True' in line, (
            f'CHECK 1/2 FAILED (smoke agent tool-calls): [{mode}] run did not call '
            f'both tools -- {line!r}. A failure here means the model, not the test, is '
            "flailing at CodeAct on this unit -- report it, don't retry it "
            '(task non-scope: no retries/fallbacks that hide a flailing model).'
        )


# -- test 2: no-thinking really reaches the wire, via a local recording stub --------


class _RecordingHandler(BaseHTTPRequestHandler):
    """Records every POSTed JSON body onto `captured` (set by the server factory)."""

    captured: ClassVar[list[dict]] = []

    def log_message(self, *_args: object) -> None:  # silence default stderr logging
        pass

    def do_POST(self) -> None:
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length)
        self.captured.append(json.loads(body))
        response = {
            'id': 'cmpl-smoke-stub',
            'object': 'chat.completion',
            'created': 0,
            'model': 'hosted_vllm/qwen3.8-27b',
            'choices': [
                {
                    'index': 0,
                    'message': {'role': 'assistant', 'content': 'stub-reply'},
                    'finish_reason': 'stop',
                }
            ],
            'usage': {'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2},
        }
        data = json.dumps(response).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)


@pytest.fixture
def recording_stub():
    captured: list[dict] = []
    handler = type('_Handler', (_RecordingHandler,), {'captured': captured})
    server = HTTPServer(('127.0.0.1', 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}/v1', captured
    finally:
        server.shutdown()
        thread.join(timeout=5)


@skip_without_llm_host
def test_no_thinking_reaches_the_wire_as_chat_template_kwargs(recording_stub) -> None:
    from nooa.unifiedllm import CompletionClient

    from seshat.config import Settings

    api_base, captured = recording_stub
    settings = Settings.load({'LLM_HOST': 'http://unused.invalid'}).with_thinking(False)
    kwargs = settings.llm_kwargs('worker')
    kwargs['api_base'] = api_base  # point at the local stub, not the real host

    client = CompletionClient(**kwargs)

    async def _call() -> None:
        await client.acall(messages=[{'role': 'user', 'content': 'ping'}])

    asyncio.run(_call())

    assert captured, (
        'CHECK 2/2 FAILED (no-thinking wire body): the local recording stub never '
        'received a request -- CompletionClient.acall did not reach the wire.'
    )
    body = captured[0]
    template_kwargs = body.get('chat_template_kwargs')
    assert template_kwargs is not None, (
        'CHECK 2/2 FAILED (no-thinking wire body): the request body had no '
        f'"chat_template_kwargs" key at all. Full body: {body!r}'
    )
    assert template_kwargs.get('enable_thinking') is False, (
        'CHECK 2/2 FAILED (no-thinking wire body): '
        f'chat_template_kwargs.enable_thinking was {template_kwargs.get("enable_thinking")!r}, '
        'expected False. --no-thinking is not reaching the model.'
    )
