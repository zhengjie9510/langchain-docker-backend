"""Run one Docker sandbox as an MCP server for HTTP clients such as Dify."""

from langchain_docker_backend import DockerSandbox
from langchain_docker_backend.mcp import create_mcp_server


def main() -> None:
    with DockerSandbox(working_dir="/workspace") as sandbox:
        create_mcp_server(sandbox).run(transport="streamable-http")


if __name__ == "__main__":
    main()
