"""Use DockerSandbox with langchain agent via FilesystemMiddleware.

FilesystemMiddleware provides built-in filesystem tools (ls, read_file,
write_file, edit_file, glob, grep) and an execute tool when the backend
implements SandboxBackendProtocol.

Prerequisites:
    docker pull ghcr.io/astral-sh/uv:python3.13-bookworm-slim
    pip install langchain-docker-backend langchain-anthropic

Usage:
    ANTHROPIC_AUTH_TOKEN=... ANTHROPIC_BASE_URL=... python langchain_example.py
"""

import os

from langchain.agents import create_agent
from langchain_anthropic import ChatAnthropic
from deepagents.middleware.filesystem import FilesystemMiddleware

from langchain_docker_backend import DockerSandbox

sandbox = DockerSandbox()

agent = create_agent(
    model=ChatAnthropic(
        model="mimo-v2.5-pro",
        base_url=os.environ.get("ANTHROPIC_BASE_URL"),
        api_key=os.environ.get("ANTHROPIC_AUTH_TOKEN"),
    ),
    system_prompt="You are a Python coding assistant with sandbox access.",
    middleware=[FilesystemMiddleware(backend=sandbox)],
)

try:
    result = agent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": "Write a Python fizzbuzz script and run it",
                }
            ]
        }
    )
    print(result)
finally:
    sandbox.close()
