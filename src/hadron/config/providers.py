"""Provider configuration registry.

Defines available models, costs, and capabilities for each AI provider.
This configuration should eventually move to the database (§21).
"""

from __future__ import annotations

from typing import TypedDict


class ModelConfig(TypedDict):
    """Configuration for a specific AI model."""
    provider: str
    cost_input_1m: float  # Cost per 1M input tokens (USD)
    cost_output_1m: float # Cost per 1M output tokens (USD)
    context_window: int
    supports_vision: bool
    supports_tools: bool
    is_experimental: bool


class ProviderConfig(TypedDict):
    """Configuration for an AI provider."""
    name: str
    models: dict[str, ModelConfig]
    env_var_key: str


# Registry of supported providers and their models
PROVIDER_REGISTRY: dict[str, ProviderConfig] = {
    "anthropic": {
        "name": "Anthropic",
        "env_var_key": "HADRON_ANTHROPIC_API_KEY",
        "models": {
            "claude-3-5-sonnet-20240620": {
                "provider": "anthropic",
                "cost_input_1m": 3.00,
                "cost_output_1m": 15.00,
                "context_window": 200000,
                "supports_vision": True,
                "supports_tools": True,
                "is_experimental": False,
            },
            "claude-3-opus-20240229": {
                "provider": "anthropic",
                "cost_input_1m": 15.00,
                "cost_output_1m": 75.00,
                "context_window": 200000,
                "supports_vision": True,
                "supports_tools": True,
                "is_experimental": False,
            },
            "claude-3-haiku-20240307": {
                "provider": "anthropic",
                "cost_input_1m": 0.25,
                "cost_output_1m": 1.25,
                "context_window": 200000,
                "supports_vision": True,
                "supports_tools": True,
                "is_experimental": False,
            },
        },
    },
    "gemini": {
        "name": "Google Gemini",
        "env_var_key": "HADRON_GEMINI_API_KEY",
        "models": {
            "gemini-1.5-pro": {
                "provider": "gemini",
                "cost_input_1m": 1.25,  # <128k context
                "cost_output_1m": 5.00, # <128k context
                "context_window": 2000000,
                "supports_vision": True,
                "supports_tools": True,
                "is_experimental": False,
            },
            "gemini-1.5-flash": {
                "provider": "gemini",
                "cost_input_1m": 0.075,
                "cost_output_1m": 0.30,
                "context_window": 1000000,
                "supports_vision": True,
                "supports_tools": True,
                "is_experimental": False,
            },
            "gemini-2.0-flash": {
                "provider": "gemini",
                "cost_input_1m": 0.10,
                "cost_output_1m": 0.40,
                "context_window": 1000000,
                "supports_vision": True,
                "supports_tools": True,
                "is_experimental": True,
            },
             "gemini-3-pro-preview": {
                "provider": "gemini",
                "cost_input_1m": 1.25,
                "cost_output_1m": 10.00,
                "context_window": 2000000,
                "supports_vision": True,
                "supports_tools": True,
                "is_experimental": True,
            },
             "gemini-3-flash-preview": {
                "provider": "gemini",
                "cost_input_1m": 0.15,
                "cost_output_1m": 0.60,
                "context_window": 1000000,
                "supports_vision": True,
                "supports_tools": True,
                "is_experimental": True,
            },
        },
    },
}

def get_model_config(model_name: str) -> ModelConfig | None:
    """Retrieve configuration for a specific model name."""
    for provider in PROVIDER_REGISTRY.values():
        if model_name in provider["models"]:
            return provider["models"][model_name]
    return None

def get_provider_for_model(model_name: str) -> str | None:
    """Return the provider name (key) for a given model."""
    config = get_model_config(model_name)
    return config["provider"] if config else None

def list_available_models() -> list[dict]:
    """Return a flat list of all available models with metadata."""
    models = []
    for p_key, p_val in PROVIDER_REGISTRY.items():
        for m_key, m_val in p_val["models"].items():
            models.append({
                "id": m_key,
                "name": m_key,  # MVP: use ID as name
                "provider": p_val["name"],
                "provider_id": p_key,
                "context_window": m_val["context_window"],
                "is_experimental": m_val["is_experimental"],
            })
    return models
