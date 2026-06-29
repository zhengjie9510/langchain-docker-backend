"""langchain-docker-backend: Docker sandbox backend for AI agents.

Usage:
    ```python
    from langchain_docker_backend import DockerSandbox

    with DockerSandbox(image="ghcr.io/astral-sh/uv:python3.13-bookworm-slim") as sandbox:
        result = sandbox.execute("echo 'Hello!'")
        print(result.output)
    ```
"""

from importlib.metadata import version, PackageNotFoundError

from langchain_docker_backend.sandbox import DockerImageNotFound, DockerSandbox

__all__ = ["DockerSandbox", "DockerImageNotFound"]

try:
    __version__ = version("langchain-docker-backend")
except PackageNotFoundError:
    __version__ = "0.0.0"
