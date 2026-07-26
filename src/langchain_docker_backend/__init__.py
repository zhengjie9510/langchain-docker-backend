"""langchain-docker-backend: Docker sandbox backend for AI agents.

Usage:
    ```python
    from langchain_docker_backend import DockerSandbox

    with DockerSandbox(image="ghcr.io/astral-sh/uv:python3.13-bookworm-slim") as sandbox:
        result = sandbox.execute("echo 'Hello!'")
        print(result.output)
    ```

Provider usage:
    ```python
    from langchain_docker_backend import DockerSandboxProvider

    # Register as a dcode sandbox provider via entry point.
    provider = DockerSandboxProvider()
    backend = provider.get_or_create()
    ```
"""

from importlib.metadata import version, PackageNotFoundError

from langchain_docker_backend.provider import DockerSandboxProvider
from langchain_docker_backend.sandbox import DockerImageNotFound, DockerSandbox

__all__ = ["DockerSandbox", "DockerImageNotFound", "DockerSandboxProvider"]

try:
    __version__ = version("langchain-docker-backend")
except PackageNotFoundError:
    __version__ = "0.0.0"
