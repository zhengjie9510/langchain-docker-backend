"""Tests for the optional MCP adapter without a Docker daemon."""

import asyncio
import json
from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest


def test_mcp_tools():
    pytest.importorskip("mcp")
    from langchain_docker_backend.mcp import create_mcp_server

    @dataclass
    class Result:
        value: str

    sandbox = MagicMock()
    for name in ("ls", "read", "write", "edit", "glob", "grep", "execute"):
        getattr(sandbox, name).return_value = Result(name)

    async def check():
        server = create_mcp_server(sandbox)
        tools = {tool.name: tool for tool in await server.list_tools()}
        assert set(tools) == {"ls", "read", "write", "edit", "glob", "grep", "execute"}
        for tool in tools.values():
            assert tool.description
            assert all(
                "description" in prop
                for prop in tool.input_schema["properties"].values()
            )

        result = await server.call_tool("grep", {"pattern": "needle", "glob": "*.py"})
        assert json.loads(result.content[0].text) == {"value": "grep"}
        sandbox.grep.assert_called_once_with("needle", path=None, glob="*.py")

        await server.call_tool("glob", {"pattern": "**/*.py"})
        sandbox.glob.assert_called_once_with("**/*.py", path=".")

        await server.call_tool("execute", {"command": "echo hi", "timeout": 5})
        sandbox.execute.assert_called_once_with("echo hi", timeout=5)

    asyncio.run(check())
