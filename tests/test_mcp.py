"""End-to-end tests for the MCP adapter over Streamable HTTP.

These tests use a real `DockerSandbox` and connect through the actual MCP
client transport, matching how HTTP clients such as Dify consume the server.

Requires a running Docker daemon.  Run with::

    uv run pytest tests/test_mcp.py -v
"""

import asyncio
import json
import socket
import threading
import time

import pytest

from langchain_docker_backend import DockerSandbox
from langchain_docker_backend.mcp import create_mcp_server

pytestmark = pytest.mark.integration

TOOL_NAMES = {"ls", "read", "write", "edit", "glob", "grep", "execute"}


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_for_port(port: int, timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.1)
    raise TimeoutError(f"MCP server did not start on port {port}")


@pytest.fixture(scope="module")
def endpoint():
    """Serve a Docker-backed MCP server over Streamable HTTP on localhost."""
    pytest.importorskip("mcp")
    import anyio
    import uvicorn

    port = _free_port()
    with DockerSandbox(working_dir="/workspace") as sandbox:
        server = create_mcp_server(sandbox)
        app = server.streamable_http_app(streamable_http_path="/mcp", host="127.0.0.1")
        uv_server = uvicorn.Server(
            uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
        )
        thread = threading.Thread(target=anyio.run, args=(uv_server.serve,), daemon=True)
        thread.start()
        try:
            _wait_for_port(port)
            yield f"http://127.0.0.1:{port}/mcp"
        finally:
            uv_server.should_exit = True
            thread.join(timeout=10)


def _json(result) -> dict:
    """Decode the JSON text returned by a tool call."""
    assert not result.is_error, result
    assert result.content, result
    return json.loads(result.content[0].text)


async def _exercise(url: str) -> None:
    from mcp import Client

    async with Client(url) as client:
        tools = {tool.name: tool for tool in (await client.list_tools()).tools}
        assert set(tools) == TOOL_NAMES
        for name, tool in tools.items():
            assert tool.description, f"{name} has no description"
            for prop, schema in tool.input_schema["properties"].items():
                assert schema.get("description"), f"{name}.{prop} has no description"

        written = _json(
            await client.call_tool(
                "write", {"path": "notes.txt", "content": "alpha\nneedle here\n"}
            )
        )
        assert written["error"] is None
        assert written["path"].endswith("notes.txt")

        overwritten = _json(
            await client.call_tool(
                "write", {"path": "notes.txt", "content": "alpha\nneedle here\n"}
            )
        )
        assert overwritten["error"] is None

        read = _json(await client.call_tool("read", {"path": "notes.txt"}))
        assert read["error"] is None
        assert read["file_data"]["content"].rstrip("\n") == "alpha\nneedle here"
        assert read["file_data"]["encoding"] == "utf-8"

        edited = _json(
            await client.call_tool(
                "edit",
                {
                    "path": "notes.txt",
                    "old_string": "needle",
                    "new_string": "thread",
                },
            )
        )
        assert edited["error"] is None
        assert edited["occurrences"] == 1

        grep = _json(
            await client.call_tool("grep", {"pattern": "thread", "glob": "*.txt"})
        )
        assert grep["error"] is None
        assert len(grep["matches"]) == 1
        assert grep["matches"][0]["path"].endswith("notes.txt")
        assert grep["matches"][0]["line"] == 2
        assert "thread" in grep["matches"][0]["text"]

        globbed = _json(await client.call_tool("glob", {"pattern": "*.txt"}))
        assert globbed["error"] is None
        assert len(globbed["matches"]) == 1
        assert globbed["matches"][0]["path"] == "/workspace/notes.txt"

        listing = _json(await client.call_tool("ls", {"path": "."}))
        assert listing["error"] is None
        assert any(
            entry["path"].endswith("notes.txt") and not entry["is_dir"]
            for entry in listing["entries"]
        )

        executed = _json(
            await client.call_tool("execute", {"command": "printf 'ok'"})
        )
        assert executed["exit_code"] == 0
        assert executed["output"] == "ok"
        assert executed["truncated"] is False

        missing = _json(await client.call_tool("read", {"path": "missing.txt"}))
        assert missing["error"] is not None


def test_streamable_http_end_to_end(endpoint):
    """Every MCP tool round-trips through a real sandbox over HTTP."""
    asyncio.run(_exercise(endpoint))
