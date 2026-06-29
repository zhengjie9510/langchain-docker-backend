"""Use DockerSandbox with deepagents.

Prerequisites:
    docker pull ghcr.io/astral-sh/uv:python3.13-bookworm-slim
    pip install langchain-docker-backend langchain-anthropic

Usage:
    ANTHROPIC_AUTH_TOKEN=... ANTHROPIC_BASE_URL=... python deepagents_example.py
"""

import os

from deepagents import create_deep_agent
from langchain_anthropic import ChatAnthropic

from langchain_docker_backend import DockerSandbox

sandbox = DockerSandbox()

agent = create_deep_agent(
    model=ChatAnthropic(
        model="mimo-v2.5-pro",
        base_url=os.environ.get("ANTHROPIC_BASE_URL"),
        api_key=os.environ.get("ANTHROPIC_AUTH_TOKEN"),
    ),
    system_prompt="You are a Python coding assistant with sandbox access.",
    backend=sandbox,
)

try:
    result = agent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": "Create a small Python package and run pytest",
                }
            ]
        }
    )
    print(result)
finally:
    sandbox.close()
