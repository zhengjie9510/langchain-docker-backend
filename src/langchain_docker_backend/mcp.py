"""Expose an existing DockerSandbox as an MCP tool server."""

from dataclasses import asdict
from typing import Annotated

from mcp.server import MCPServer
from pydantic import Field

from langchain_docker_backend.sandbox import DockerSandbox


def create_mcp_server(sandbox: DockerSandbox) -> MCPServer:
    """Register sandbox operations on an MCP server.

    The caller owns the sandbox and must close it after the server stops.
    Install the optional ``mcp`` dependency before importing this module.
    """
    server = MCPServer("docker-sandbox")

    @server.tool()
    def ls(
        path: Annotated[
            str,
            Field(description="Directory to list."),
        ],
    ) -> dict:
        """List files and directories with metadata.

        Use this to explore a directory before choosing files to read or edit.
        """
        return asdict(sandbox.ls(path))

    @server.tool()
    def read(
        path: Annotated[
            str,
            Field(description="File to read."),
        ],
        offset: Annotated[int, Field(description="Zero-based starting line for text files.")] = 0,
        limit: Annotated[
            int,
            Field(description="Maximum text lines to return; use fewer for large files."),
        ] = 2000,
    ) -> dict:
        """Read a file.

        Text reads support line-based pagination. Binary content is returned
        base64-encoded without pagination.
        """
        return asdict(sandbox.read(path, offset=offset, limit=limit))

    @server.tool()
    def write(
        path: Annotated[
            str,
            Field(description="Path for the new file."),
        ],
        content: Annotated[str, Field(description="UTF-8 text to write to the new file.")],
    ) -> dict:
        """Create a new text file.

        Returns an error if the file already exists; use edit to change it.
        """
        return asdict(sandbox.write(path, content))

    @server.tool()
    def edit(
        path: Annotated[
            str,
            Field(description="File to edit."),
        ],
        old_string: Annotated[
            str, Field(description="Exact text to find, including its whitespace.")
        ],
        new_string: Annotated[
            str, Field(description="Replacement text, different from old_string.")
        ],
        replace_all: Annotated[
            bool,
            Field(description="Replace all occurrences; otherwise the text must be unique."),
        ] = False,
    ) -> dict:
        """Replace exact text in an existing file.

        Read the file first so the search text and whitespace match.
        """
        return asdict(sandbox.edit(path, old_string, new_string, replace_all))

    @server.tool()
    def glob(
        pattern: Annotated[str, Field(description="File path glob, such as '**/*.py' or '*.txt'.")],
        path: Annotated[
            str,
            Field(description="Base directory; defaults to the sandbox working directory."),
        ] = ".",
    ) -> dict:
        """Find files by path pattern.

        Use this when you know a filename or extension. '*' matches characters;
        '**' matches directories.
        """
        return asdict(sandbox.glob(pattern, path=path))

    @server.tool()
    def grep(
        pattern: Annotated[
            str, Field(description="Literal text to find; regular expressions are unsupported.")
        ],
        path: Annotated[
            str | None,
            Field(description="File or directory to search; defaults to the working directory."),
        ] = None,
        glob: Annotated[
            str | None, Field(description="Optional filename filter, such as '*.py'.")
        ] = None,
    ) -> dict:
        """Search file contents for literal text.

        Returns matching files and lines. Regex characters are ordinary text.
        """
        return asdict(sandbox.grep(pattern, path=path, glob=glob))

    @server.tool()
    def execute(
        command: Annotated[
            str, Field(description="Shell command to run inside the sandbox container.")
        ],
        timeout: Annotated[
            int | None, Field(description="Optional seconds; overrides the sandbox default.")
        ] = None,
    ) -> dict:
        """Run a shell command in the sandbox working directory.

        Returns combined stdout/stderr, exit code, and an output truncation flag.
        """
        return asdict(sandbox.execute(command, timeout=timeout))

    return server
