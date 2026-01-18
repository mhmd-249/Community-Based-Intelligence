"""
LLM configuration for Claude models.

Defines model settings for each agent type with appropriate
temperature, token limits, and timeouts.
"""

from dataclasses import dataclass
from typing import Literal

AgentType = Literal["reporter", "surveillance", "analyst"]


@dataclass(frozen=True, slots=True)
class LLMConfig:
    """Configuration for a Claude model."""

    model: str
    max_tokens: int
    temperature: float
    timeout: float


# Model identifiers
HAIKU_MODEL = "claude-3-5-haiku-20241022"
SONNET_MODEL = "claude-3-5-sonnet-20241022"


# Agent-specific configurations
REPORTER_CONFIG = LLMConfig(
    model=HAIKU_MODEL,
    max_tokens=500,
    temperature=0.3,  # Low for consistency
    timeout=30.0,
)

SURVEILLANCE_CONFIG = LLMConfig(
    model=SONNET_MODEL,
    max_tokens=2000,
    temperature=0.1,  # Very low for classification
    timeout=60.0,
)

ANALYST_CONFIG = LLMConfig(
    model=SONNET_MODEL,
    max_tokens=4000,
    temperature=0.1,
    timeout=120.0,
)


def get_llm_config(agent_type: AgentType) -> LLMConfig:
    """
    Get LLM configuration for an agent type.

    Args:
        agent_type: The type of agent (reporter, surveillance, analyst).

    Returns:
        LLMConfig with model settings for the agent.

    Raises:
        ValueError: If agent_type is not recognized.
    """
    configs: dict[AgentType, LLMConfig] = {
        "reporter": REPORTER_CONFIG,
        "surveillance": SURVEILLANCE_CONFIG,
        "analyst": ANALYST_CONFIG,
    }

    if agent_type not in configs:
        raise ValueError(f"Unknown agent type: {agent_type}")

    return configs[agent_type]
