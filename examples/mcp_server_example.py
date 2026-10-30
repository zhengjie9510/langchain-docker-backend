"""Run one Docker sandbox as an MCP server for HTTP clients such as Dify.

Prerequisites:
    docker pull python:3.13-slim

Usage:
    python mcp_server_example.py --host 127.0.0.1 --port 8000
"""

import argparse

from langchain_docker_backend import DockerSandbox
from langchain_docker_backend.mcp import create_mcp_server


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    with DockerSandbox(working_dir="/workspace") as sandbox:
        create_mcp_server(sandbox).run(
            transport="streamable-http",
            host=args.host,
            port=args.port,
        )


if __name__ == "__main__":
    main()
