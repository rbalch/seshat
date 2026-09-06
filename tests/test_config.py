"""Acceptance tests for T-02: role config.

Covers the acceptance criteria in tasks/seshat-phase-one/T-02-package-skeleton.md:

- missing `LLM_HOST` raises `ConfigError` whose message contains `LLM_HOST`.
- default model for every role is `hosted_vllm/qwen3.8-27b` and `api_base` is
  `<LLM_HOST>/v1`.
- `SESHAT_MODEL_ANSWER=x` changes only the answer role.
- `llm_kwargs` omits `extra_body` when thinking is on and includes the exact
  `chat_template_kwargs` dict when off.
"""

from __future__ import annotations

import typing

import pytest

from seshat.config import ConfigError, Settings

DEFAULT_MODEL = 'hosted_vllm/qwen3.8-27b'
ALL_ROLES = ('worker', 'verifier_author', 'reflection', 'answer')


def test_missing_llm_host_raises_config_error() -> None:
    with pytest.raises(ConfigError) as exc_info:
        Settings.load(env={})
    assert 'LLM_HOST' in str(exc_info.value)


def test_whitespace_only_llm_host_raises_config_error() -> None:
    with pytest.raises(ConfigError) as exc_info:
        Settings.load(env={'LLM_HOST': ' \t\n'})
    assert 'LLM_HOST' in str(exc_info.value)


def test_llm_host_with_surrounding_whitespace_produces_clean_api_base() -> None:
    settings = Settings.load(env={'LLM_HOST': 'http://spark:8000 '})
    assert settings.role('worker').api_base == 'http://spark:8000/v1'


def test_default_model_and_api_base_for_every_role() -> None:
    settings = Settings.load(env={'LLM_HOST': 'http://spark:8000'})
    for role in ALL_ROLES:
        role_config = settings.role(role)
        assert role_config.model == DEFAULT_MODEL
        assert role_config.api_base == 'http://spark:8000/v1'


def test_answer_override_changes_only_answer_role() -> None:
    settings = Settings.load(
        env={
            'LLM_HOST': 'http://spark:8000',
            'SESHAT_MODEL_ANSWER': 'x',
        }
    )
    assert settings.role('answer').model == 'x'
    for role in ('worker', 'verifier_author', 'reflection'):
        assert settings.role(role).model == DEFAULT_MODEL


def test_llm_kwargs_omits_extra_body_when_thinking_on() -> None:
    settings = Settings.load(env={'LLM_HOST': 'http://spark:8000'})
    kwargs = settings.llm_kwargs('worker')
    assert kwargs['model'] == DEFAULT_MODEL
    assert kwargs['api_base'] == 'http://spark:8000/v1'
    assert 'extra_body' not in kwargs


def test_llm_kwargs_includes_chat_template_kwargs_when_thinking_off() -> None:
    settings = Settings.load(env={'LLM_HOST': 'http://spark:8000'}).with_thinking(False)
    kwargs = settings.llm_kwargs('worker')
    assert kwargs['extra_body'] == {'chat_template_kwargs': {'enable_thinking': False}}


def test_empty_optional_vars_fall_back_to_default_model() -> None:
    env = {
        'LLM_HOST': 'http://spark:8000',
        'SESHAT_MODEL': '',
        'SESHAT_MODEL_WORKER': '',
        'SESHAT_MODEL_VERIFIER_AUTHOR': '',
        'SESHAT_MODEL_REFLECTION': '',
        'SESHAT_MODEL_ANSWER': '',
    }
    settings = Settings.load(env)
    for role in ALL_ROLES:
        assert settings.role(role).model == DEFAULT_MODEL
    assert settings.llm_kwargs('worker') == {
        'model': DEFAULT_MODEL,
        'api_base': 'http://spark:8000/v1',
    }


def test_load_defaults_to_os_environ(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('LLM_HOST', 'http://spark:8000')
    settings = Settings.load()
    assert settings.role('worker').model == DEFAULT_MODEL
    assert settings.role('worker').api_base == 'http://spark:8000/v1'


def test_with_thinking_does_not_mutate_original() -> None:
    original = Settings.load(env={'LLM_HOST': 'http://spark:8000'})
    off = original.with_thinking(False)
    assert off.role('worker').thinking is False
    assert original.role('worker').thinking is True


def test_settings_roles_mapping_is_read_only() -> None:
    settings = Settings.load(env={'LLM_HOST': 'http://spark:8000'})
    roles = typing.cast(dict, settings._roles)
    with pytest.raises(TypeError):
        roles['worker'] = 'CLOBBERED'
