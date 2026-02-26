"""Quick smoke test for the multi-provider agent integration."""
from hadron.agent.base import AgentBackend, AgentTask, provider_for_model
from hadron.agent.claude import ClaudeAgentBackend
from hadron.agent.gemini import GeminiAgentBackend
from hadron.agent.tools import TOOL_DEFINITIONS, execute_tool
from hadron.agent.provider_chain import BackendRegistry, ProviderChain, ProviderChainConfig
from hadron.models.config import BootstrapConfig
from hadron.config.defaults import get_config_snapshot

# Model routing
assert provider_for_model("claude-sonnet-4-20250514") == "anthropic"
assert provider_for_model("gemini-2.5-pro") == "gemini"
assert provider_for_model("gpt-4") == "openai"

# Config
cfg = BootstrapConfig()
assert hasattr(cfg, "gemini_api_key")

snap = get_config_snapshot()
assert "provider_chain" in snap["pipeline"]

# Registry
reg = BackendRegistry()
claude = ClaudeAgentBackend("test")
gemini = GeminiAgentBackend("test")
reg.register(claude)
reg.register(gemini)
assert reg.providers == ["anthropic", "gemini"]
assert claude.name == "anthropic"
assert gemini.name == "gemini"

# Provider chain
chain = ProviderChain(reg)
order = chain._resolve_order("claude-sonnet-4-20250514")
assert order[0] == "anthropic"
assert "gemini" in order

order2 = chain._resolve_order("gemini-2.5-pro")
assert order2[0] == "gemini"

# Worker import
from hadron.worker.main import run_worker  # noqa: F401

# Controller import
from hadron.controller.app import create_app  # noqa: F401

print("All smoke tests passed.")
