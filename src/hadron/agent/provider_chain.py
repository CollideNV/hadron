"""Provider chain — routes agent tasks to the right backend with failover.

Architecture reference: §9.3 (LLM Resilience & Failover).

Overview
--------
Every agent call goes through a ``ProviderChain``.  The chain:

1. Determines the correct backend based on the task's ``model`` field.
2. Tries the primary backend with retries.
3. On exhausted retries, falls through to the next backend in the
   configured **fallback** list (with model substitution).

The ``BackendRegistry`` holds instantiated backends keyed by provider
name (``"anthropic"``, ``"gemini"``, …).  It is populated once at
worker start-up and shared across all pipeline nodes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import AsyncIterator

from hadron.agent.base import (
    AgentBackend,
    AgentEvent,
    AgentResult,
    AgentTask,
    provider_for_model,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Fallback model mapping — when failing over from one provider to another,
# which model should be used as a substitute?
# ---------------------------------------------------------------------------

DEFAULT_FALLBACK_MODELS: dict[str, str] = {
    "anthropic": "claude-sonnet-4-20250514",
    "gemini": "gemini-3-pro-preview",
}


# ---------------------------------------------------------------------------
# Backend registry
# ---------------------------------------------------------------------------


class BackendRegistry:
    """Holds instantiated agent backends keyed by provider name.

    Usage::

        registry = BackendRegistry()
        registry.register(ClaudeAgentBackend(api_key="..."))
        registry.register(GeminiAgentBackend(api_key="..."))

        backend = registry.get("anthropic")
    """

    def __init__(self) -> None:
        self._backends: dict[str, AgentBackend] = {}

    def register(self, backend: AgentBackend) -> None:
        """Register a backend under its ``.name``."""
        self._backends[backend.name] = backend

    def get(self, provider: str) -> AgentBackend | None:
        """Return the backend for *provider*, or ``None``."""
        return self._backends.get(provider)

    def has(self, provider: str) -> bool:
        return provider in self._backends

    @property
    def providers(self) -> list[str]:
        return list(self._backends.keys())

    def __repr__(self) -> str:
        return f"BackendRegistry(providers={self.providers})"


# ---------------------------------------------------------------------------
# Provider chain
# ---------------------------------------------------------------------------


@dataclass
class ProviderChainConfig:
    """Configuration for the provider chain."""

    # Ordered list of provider names.  The first entry is the *primary*;
    # subsequent entries are fallbacks tried in order.
    chain: list[str] = field(default_factory=lambda: ["anthropic", "gemini"])

    # Maximum retries per provider before moving to the next one.
    max_retries_per_provider: int = 3

    # When falling over to a different provider, which model to use.
    fallback_models: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_FALLBACK_MODELS))


class ProviderChain:
    """Routes agent tasks to backends with automatic failover.

    The chain inspects ``task.model`` to determine the *natural* provider,
    then tries that provider first (if available).  If it fails after
    ``max_retries``, it walks the fallback list.

    This is the object that pipeline nodes interact with — they call
    ``chain.execute(task)`` exactly as they would a single backend.
    """

    def __init__(
        self,
        registry: BackendRegistry,
        config: ProviderChainConfig | None = None,
    ) -> None:
        self.registry = registry
        self.config = config or ProviderChainConfig()

    # --- public API (same shape as AgentBackend) --------------------------

    @property
    def name(self) -> str:
        return "provider_chain"

    async def execute(self, task: AgentTask) -> AgentResult:
        """Execute a task, trying providers in chain order."""
        providers = self._resolve_order(task.model)

        last_error: Exception | None = None
        for provider_name in providers:
            backend = self.registry.get(provider_name)
            if backend is None:
                continue

            # Possibly swap model if we're on a fallback provider
            effective_task = self._adapt_task(task, provider_name)

            try:
                result = await backend.execute(effective_task)
                return result
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Provider %s failed for role=%s model=%s: %s — trying next",
                    provider_name, task.role, effective_task.model, exc,
                )
                continue

        raise RuntimeError(
            f"All providers exhausted for role={task.role} model={task.model}. "
            f"Last error: {last_error}"
        )

    async def stream(self, task: AgentTask) -> AsyncIterator[AgentEvent]:
        """Stream from the first available provider."""
        providers = self._resolve_order(task.model)

        last_error: Exception | None = None
        for provider_name in providers:
            backend = self.registry.get(provider_name)
            if backend is None:
                continue

            effective_task = self._adapt_task(task, provider_name)

            try:
                async for event in backend.stream(effective_task):
                    yield event
                return  # success
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Provider %s stream failed for role=%s: %s — trying next",
                    provider_name, task.role, exc,
                )
                continue

        raise RuntimeError(
            f"All providers exhausted (stream) for role={task.role}. "
            f"Last error: {last_error}"
        )

    # --- internals --------------------------------------------------------

    def _resolve_order(self, model: str) -> list[str]:
        """Build the ordered list of providers to try.

        1. The *natural* provider for the model comes first.
        2. Then any remaining providers from ``self.config.chain`` that
           aren't the natural one, in their configured order.
        """
        natural = provider_for_model(model)
        seen: set[str] = set()
        order: list[str] = []

        # Natural provider first (if it's in the registry)
        if self.registry.has(natural):
            order.append(natural)
            seen.add(natural)

        # Then the configured chain order
        for p in self.config.chain:
            if p not in seen and self.registry.has(p):
                order.append(p)
                seen.add(p)

        return order

    def _adapt_task(self, task: AgentTask, target_provider: str) -> AgentTask:
        """Return a (possibly model-substituted) copy of *task*.

        If the task's model naturally belongs to ``target_provider``, use
        it as-is.  Otherwise swap in the fallback model for that provider.
        """
        natural = provider_for_model(task.model)
        if natural == target_provider:
            return task  # no substitution needed

        fallback_model = self.config.fallback_models.get(target_provider)
        if not fallback_model:
            return task  # no fallback model configured — try anyway

        logger.info(
            "Substituting model %s → %s for provider %s (role=%s)",
            task.model, fallback_model, target_provider, task.role,
        )
        # Shallow copy with replaced model
        return AgentTask(
            role=task.role,
            system_prompt=task.system_prompt,
            user_prompt=task.user_prompt,
            working_directory=task.working_directory,
            allowed_tools=task.allowed_tools,
            model=fallback_model,
            max_tokens=task.max_tokens,
            max_tool_rounds=task.max_tool_rounds,
            on_tool_call=task.on_tool_call,
            on_event=task.on_event,
            nudge_poll=task.nudge_poll,
        )
