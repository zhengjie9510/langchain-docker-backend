"""Docker sandbox provider for Deep Agents Code.

Wraps the existing ``DockerSandbox`` backend so it can be used as a pluggable
sandbox for ``dcode --sandbox docker``.

Usage::

    # Install the package and run:
    dcode --sandbox docker

    # Reuse an existing container:
    dcode --sandbox docker --sandbox-id abc123

    # With a setup script:
    dcode --sandbox docker --sandbox-setup ./setup.sh

"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, NoReturn

from deepagents_code.integrations.sandbox_provider import (
    SandboxInstallHint,
    SandboxNotFoundError,
    SandboxProvider,
    SandboxProviderMetadata,
)

from langchain_docker_backend.sandbox import DockerSandbox, _DEFAULT_WORKING_DIR

if TYPE_CHECKING:
    from deepagents.backends.protocol import SandboxBackendProtocol

logger = logging.getLogger(__name__)

def _raise_unsupported_kwargs(kwargs: dict[str, Any]) -> NoReturn:
    names = ", ".join(sorted(kwargs))
    msg = f"Received unsupported arguments: {names}"
    raise TypeError(msg)


class DockerSandboxProvider(SandboxProvider):
    """Manage Docker containers as sandboxes for Deep Agents Code.

    This provider delegates all Docker SDK interactions to
    :class:`~langchain_docker_backend.sandbox.DockerSandbox`.  Its
    responsibility is limited to environment-variable resolution and
    factory methods.
    """

    _metadata = SandboxProviderMetadata(
        name="docker",
        working_dir=_DEFAULT_WORKING_DIR,
        install=SandboxInstallHint(kind="package", name="langchain-docker-backend"),
        supports_sandbox_id=True,
        supports_snapshot_name=False,
    )

    @property
    def metadata(self) -> SandboxProviderMetadata:
        """Return metadata used by Deep Agents Code provider discovery."""
        return self._metadata

    def get_or_create(
        self,
        *,
        sandbox_id: str | None = None,
        **kwargs: Any,
    ) -> SandboxBackendProtocol:
        """Get or create a Docker container sandbox.

        All container lifecycle is delegated to
        :class:`~langchain_docker_backend.sandbox.DockerSandbox`.

        Args:
            sandbox_id: Existing container ID, or ``None`` to create one.
            image: Docker image name.
            container_name: Container name.  Auto-generated when ``None``.
            volumes: Volume mounts, e.g.
                ``{"/host": {"bind": "/container", "mode": "rw"}}``.
            working_dir: Working directory inside the container.
            auto_remove: Remove the container on ``close()``.
            execute_timeout: Default timeout in seconds for ``execute()``.
            max_output_bytes: Maximum output bytes before truncation.
            docker_client_kwargs: Extra keyword arguments for ``docker.from_env()``.
            environment: Environment variables to set inside the container.

        Returns:
            A ``DockerSandbox`` instance.

        Raises:
            SandboxNotFoundError: If ``sandbox_id`` does not exist or is exited.
            ValueError: If credentials or settings are invalid.
        """

        if sandbox_id is not None:
            # Reattach to existing container via DockerSandbox.from_id
            try:
                docker_client_kwargs = kwargs.pop("docker_client_kwargs", None)
                working_dir = kwargs.pop("working_dir", None)
                execute_timeout = kwargs.pop("execute_timeout", None)
                return DockerSandbox.from_id(
                    sandbox_id,
                    docker_client_kwargs=docker_client_kwargs,
                    working_dir=working_dir,
                    execute_timeout=execute_timeout,
                )
            except DockerSandbox.NotFound:
                raise SandboxNotFoundError(sandbox_id) from None

        # Delegate creation to DockerSandbox, passing only explicitly set arguments
        # so sandbox.py defaults apply for unset parameters.
        allowed = {"image", "container_name", "volumes", "working_dir", "auto_remove", "execute_timeout", "max_output_bytes", "docker_client_kwargs", "environment"}
        create_kwargs = {k: kwargs.pop(k) for k in allowed if k in kwargs}

        if kwargs:
            _raise_unsupported_kwargs(kwargs)

        return DockerSandbox(**create_kwargs)

    def delete(self, *, sandbox_id: str, **kwargs: Any) -> None:
        """Stop and remove a Docker container.

        Args:
            sandbox_id: Container ID to stop and remove.
            **kwargs: Unsupported provider options.

        Raises:
            SandboxNotFoundError: If ``sandbox_id`` does not exist.
        """
        if kwargs:
            _raise_unsupported_kwargs(kwargs)

        try:
            DockerSandbox.stop(sandbox_id)
        except DockerSandbox.NotFound:
            raise SandboxNotFoundError(sandbox_id) from None
