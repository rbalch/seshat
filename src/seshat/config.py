"""Model and runtime configuration.

One place that says which model string, API base and thinking setting each of the
four model roles uses. Every agent task reads its model from here and nowhere else.

`Settings.load` reads the environment mapping the caller passes in; it never reads a
`.env` file itself (the caller sets the environment).
"""

from __future__ import annotations

import dataclasses
import os
import typing
from collections.abc import Mapping
from types import MappingProxyType
from typing import Literal

Role = Literal['worker', 'verifier_author', 'reflection', 'answer']

ROLES: tuple[Role, ...] = typing.get_args(Role)

DEFAULT_MODEL = 'hosted_vllm/qwen3.8-27b'

_ROLE_ENV_VARS: dict[Role, str] = {
    'worker': 'SESHAT_MODEL_WORKER',
    'verifier_author': 'SESHAT_MODEL_VERIFIER_AUTHOR',
    'reflection': 'SESHAT_MODEL_REFLECTION',
    'answer': 'SESHAT_MODEL_ANSWER',
}


def _non_empty(value: str | None) -> str | None:
    """`value` stripped, or None when it is absent, empty or whitespace-only."""
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


class ConfigError(Exception):
    """Raised when required configuration is missing or invalid."""


@dataclasses.dataclass(frozen=True)
class RoleConfig:
    """The model, API base and thinking setting for one model role."""

    model: str
    api_base: str
    thinking: bool


@dataclasses.dataclass(frozen=True)
class Settings:
    """Resolved configuration for every model role.

    Construct via `Settings.load`, not directly.
    """

    _roles: Mapping[Role, RoleConfig]

    @classmethod
    def load(cls, env: Mapping[str, str] | None = None) -> Settings:
        """Read settings from `env` (defaults to `os.environ` when None).

        Required: `LLM_HOST`. Raises `ConfigError` naming the variable when missing.
        An optional variable that is absent, empty or whitespace-only is treated as
        unset and falls back to its default.
        """
        if env is None:
            env = os.environ

        llm_host = _non_empty(env.get('LLM_HOST'))
        if llm_host is None:
            raise ConfigError('Missing required environment variable: LLM_HOST')

        api_base = f'{llm_host}/v1'
        default_model = _non_empty(env.get('SESHAT_MODEL')) or DEFAULT_MODEL

        roles: dict[Role, RoleConfig] = {}
        for role in ROLES:
            model = _non_empty(env.get(_ROLE_ENV_VARS[role])) or default_model
            roles[role] = RoleConfig(model=model, api_base=api_base, thinking=True)

        return cls(_roles=MappingProxyType(roles))

    def role(self, name: Role) -> RoleConfig:
        """The resolved config for one role."""
        return self._roles[name]

    def llm_kwargs(self, role: Role) -> dict:
        """Kwargs to hand NOOA's LLM constructor for `role`.

        `api_base` and `extra_body` pass through to LiteLLM unchanged; never wrap or
        rename them.
        """
        role_config = self.role(role)
        kwargs: dict = {
            'model': role_config.model,
            'api_base': role_config.api_base,
        }
        if not role_config.thinking:
            kwargs['extra_body'] = {'chat_template_kwargs': {'enable_thinking': False}}
        return kwargs

    def with_thinking(self, thinking: bool) -> Settings:
        """A copy of these settings with thinking set for every role."""
        roles = {name: dataclasses.replace(role_config, thinking=thinking) for name, role_config in self._roles.items()}
        return dataclasses.replace(self, _roles=MappingProxyType(roles))
