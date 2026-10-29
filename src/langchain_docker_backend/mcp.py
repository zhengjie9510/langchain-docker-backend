"""Expose a DockerSandbox through MCP."""

from dataclasses import asdict
from typing import Annotated

from mcp.server import MCPServer
from pydantic import Field

from langchain_docker_backend.sandbox import DockerSandbox


def create_mcp_server(sandbox: DockerSandbox) -> MCPServer:
    """Register tools for a sandbox. The caller is responsible for closing it."""
    server = MCPServer("docker-sandbox")

    @server.tool()
    def ls(path: Annotated[str, Field(description="Directory to list.")]) -> dict:
        """List files and directories with metadata to locate files to read or edit."""
        return asdict(sandbox.ls(path))

    @server.tool()
    def read(
        path: Annotated[str, Field(description="File to read.")],
        offset: Annotated[int, Field(description="First text line, starting at zero.")] = 0,
        limit: Annotated[int, Field(description="Maximum number of text lines.")] = 2000,
    ) -> dict:
        """Read a file. Text supports pagination; binary content is base64 encoded."""
        return asdict(sandbox.read(path, offset=offset, limit=limit))

    @server.tool()
    def write(
        path: Annotated[str, Field(description="Path for the new file.")],
        content: Annotated[str, Field(description="UTF-8 text to write.")],
    ) -> dict:
        """Create a text file. Returns an error if the file already exists."""
        return asdict(sandbox.write(path, content))

    @server.tool()
    def edit(
        path: Annotated[str, Field(description="File to edit.")],
        old_string: Annotated[str, Field(description="Exact text to find.")],
        new_string: Annotated[str, Field(description="Replacement text.")],
        replace_all: Annotated[
            bool, Field(description="Replace every match; otherwise the match must be unique.")
        ] = False,
    ) -> dict:
        """Replace exact text in an existing file. Read the file before editing."""
        return asdict(sandbox.edit(path, old_string, new_string, replace_all))

    @server.tool()
    def glob(
        pattern: Annotated[str, Field(description="Path pattern, such as '**/*.py'.")],
        path: Annotated[
            str, Field(description="Base directory; defaults to the working directory.")
        ] = ".",
    ) -> dict:
        """Find files by path pattern. Use '*' for characters and '**' for directories."""
        return asdict(sandbox.glob(pattern, path=path))

    @server.tool()
    def grep(
        pattern: Annotated[str, Field(description="Literal text to find, not a regex.")],
        path: Annotated[
            str | None, Field(description="File or directory; defaults to the working directory.")
        ] = None,
        glob: Annotated[str | None, Field(description="Filename filter, such as '*.py'.")] = None,
    ) -> dict:
        """Search file contents for literal text and return matching lines."""
        return asdict(sandbox.grep(pattern, path=path, glob=glob))

    @server.tool()
    def execute(
        command: Annotated[str, Field(description="Shell command to run in the sandbox.")],
        timeout: Annotated[
            int | None, Field(description="Timeout in seconds; overrides the sandbox default.")
        ] = None,
    ) -> dict:
        """Run a command and return its output, exit code, and truncation flag."""
        return asdict(sandbox.execute(command, timeout=timeout))

    return server
