"""Unit tests for the Docker sandbox provider."""

from __future__ import annotations

from importlib.metadata import entry_points
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast
from unittest.mock import ANY, MagicMock, patch

import docker
import pytest
from deepagents_code.integrations.sandbox_provider import SandboxNotFoundError

from langchain_docker_backend.provider import DockerSandboxProvider
from langchain_docker_backend.sandbox import DockerSandbox

if TYPE_CHECKING:
    from collections.abc import Callable


def _make_container(
    name: str = "langchain-docker-abc123",
    status: str = "running",
    container_id: str = "test-container-123",
) -> MagicMock:
    """Create a mock Docker container."""
    container = MagicMock()
    container.id = container_id
    container.short_id = container_id
    container.name = name
    container.attrs = {"Config": {"Image": "ghcr.io/astral-sh/uv:python3.13-bookworm-slim"}}
    container.status = status
    container.stop = MagicMock()
    container.remove = MagicMock()
    container.reload = MagicMock()
    return container


def _make_mock_client(container: MagicMock) -> MagicMock:
    """Create a mock Docker client."""
    client = MagicMock()
    client.containers = MagicMock()
    client.containers.run.return_value = container
    client.containers.get.return_value = container
    return client


def test_provider_metadata_does_not_require_docker() -> None:
    """Provider metadata should be accessible without Docker running."""
    provider = DockerSandboxProvider()
    metadata = provider.metadata

    assert metadata.name == "docker"
    assert metadata.working_dir == "/workspace"
    assert metadata.supports_sandbox_id is True
    assert metadata.supports_snapshot_name is False
    assert metadata.install is not None
    assert metadata.install.kind == "package"
    assert metadata.install.name == "langchain-docker-backend"


def test_entry_point_loads_provider() -> None:
    """Entry point should correctly load the provider class."""
    entries = list(entry_points(group="deepagents_code.sandbox_providers"))
    entry = next((item for item in entries if item.name == "docker"), None)
    assert entry is not None, "docker entry point not found"
    assert entry.value == "langchain_docker_backend.provider:DockerSandboxProvider"
    assert entry.load() is DockerSandboxProvider


def test_provider_metadata_from_entry_point() -> None:
    """Metadata loaded through entry point should be correct."""
    entries = list(entry_points(group="deepagents_code.sandbox_providers"))
    entry = next(item for item in entries if item.name == "docker")
    provider_class = entry.load()
    provider = provider_class()

    assert provider.metadata.name == "docker"
    assert provider.metadata.working_dir == "/workspace"


def test_provider_creates_container_with_defaults() -> None:
    """Provider should create a container with correct defaults."""
    mock_container = _make_container()
    mock_client = _make_mock_client(mock_container)

    with patch("docker.from_env", return_value=mock_client):
        provider = DockerSandboxProvider()
        backend = provider.get_or_create()

        assert isinstance(backend, DockerSandbox)

    mock_client.containers.run.assert_called_once_with(
        image="ghcr.io/astral-sh/uv:python3.13-bookworm-slim",
        name=ANY,  # auto-generated
        command="tail -f /dev/null",
        detach=True,
        stdin_open=True,
        tty=False,
        working_dir="/workspace",
        volumes={},
    )


def test_provider_connects_existing_container() -> None:
    """Provider should connect to an existing container by ID."""
    mock_container = _make_container("test-container-123", "running", "test-container-123")
    mock_client = _make_mock_client(mock_container)

    with patch("docker.from_env", return_value=mock_client):
        provider = DockerSandboxProvider()
        backend = provider.get_or_create(sandbox_id="test-container-123")

        assert isinstance(backend, DockerSandbox)
        assert backend.id == "test-container-123"

    mock_client.containers.get.assert_called_once_with("test-container-123")
    mock_container.reload.assert_called_once()


def test_provider_raises_for_nonexistent_container() -> None:
    """Provider should raise SandboxNotFoundError for non-existent container."""
    mock_container = _make_container()
    mock_client = _make_mock_client(mock_container)
    mock_client.containers.get.side_effect = docker.errors.NotFound("Container not found")

    with patch("docker.from_env", return_value=mock_client):
        provider = DockerSandboxProvider()
        with pytest.raises(SandboxNotFoundError):
            provider.get_or_create(sandbox_id="nonexistent")


def test_provider_rejects_unsupported_kwargs() -> None:
    """Provider should reject unsupported keyword arguments."""
    provider = DockerSandboxProvider()
    with pytest.raises(TypeError, match="Received unsupported arguments: unsupported"):
        provider.get_or_create(unsupported="value")


def test_provider_rejects_unsupported_delete_kwargs() -> None:
    """Provider should reject unsupported keyword arguments in delete."""
    provider = DockerSandboxProvider()
    with pytest.raises(TypeError, match="Received unsupported arguments: force"):
        provider.delete(sandbox_id="test", force=True)


def test_provider_delete_stops_and_removes_container() -> None:
    """Provider delete should stop and remove the container."""
    mock_container = _make_container()
    mock_client = _make_mock_client(mock_container)

    with patch("docker.from_env", return_value=mock_client):
        provider = DockerSandboxProvider()
        provider.delete(sandbox_id="test-container-123")

    mock_container.stop.assert_called_once_with(timeout=5)
    mock_container.remove.assert_called_once_with(force=True)


def test_provider_delete_raises_for_nonexistent_container() -> None:
    """Provider delete should raise SandboxNotFoundError for non-existent container."""
    mock_container = _make_container()
    mock_client = _make_mock_client(mock_container)
    mock_client.containers.get.side_effect = docker.errors.NotFound("Container not found")

    with patch("docker.from_env", return_value=mock_client):
        provider = DockerSandboxProvider()
        with pytest.raises(SandboxNotFoundError):
            provider.delete(sandbox_id="nonexistent")


def test_provider_exits_container_raises_sandbox_not_found() -> None:
    """Provider should raise SandboxNotFoundError when reattaching to exited container."""
    mock_container = _make_container("test-container-123", "exited", "test-container-123")
    mock_client = _make_mock_client(mock_container)

    with patch("docker.from_env", return_value=mock_client):
        provider = DockerSandboxProvider()
        with pytest.raises(SandboxNotFoundError):
            provider.get_or_create(sandbox_id="test-container-123")


def test_provider_creates_container_with_volumes() -> None:
    """Provider should pass volumes to container creation."""
    mock_container = _make_container()
    mock_client = _make_mock_client(mock_container)

    volumes = {"/host/path": {"bind": "/container/path", "mode": "rw"}}
    with patch("docker.from_env", return_value=mock_client):
        provider = DockerSandboxProvider()
        provider.get_or_create(volumes=volumes)

    call_kwargs = mock_client.containers.run.call_args[1]
    assert call_kwargs["volumes"] == volumes


def test_provider_creates_container_with_environment() -> None:
    """Provider should pass environment to container creation."""
    mock_container = _make_container()
    mock_client = _make_mock_client(mock_container)

    environment = {"KEY1": "value1", "KEY2": "value2"}
    with patch("docker.from_env", return_value=mock_client):
        provider = DockerSandboxProvider()
        provider.get_or_create(environment=environment)

    call_kwargs = mock_client.containers.run.call_args[1]
    assert call_kwargs["environment"] == environment


def test_provider_creates_container_with_image() -> None:
    """Provider should pass image to container creation."""
    mock_container = _make_container()
    mock_client = _make_mock_client(mock_container)

    with patch("docker.from_env", return_value=mock_client):
        provider = DockerSandboxProvider()
        provider.get_or_create(image="custom-image:latest")

    call_kwargs = mock_client.containers.run.call_args[1]
    assert call_kwargs["image"] == "custom-image:latest"


def test_provider_creates_container_with_working_dir() -> None:
    """Provider should pass working_dir to container creation."""
    mock_container = _make_container()
    mock_client = _make_mock_client(mock_container)

    with patch("docker.from_env", return_value=mock_client):
        provider = DockerSandboxProvider()
        provider.get_or_create(working_dir="/custom/workspace")

    call_kwargs = mock_client.containers.run.call_args[1]
    assert call_kwargs["working_dir"] == "/custom/workspace"


def test_provider_handles_execute_timeout() -> None:
    """Provider should accept execute_timeout without raising an error."""
    mock_container = _make_container()
    mock_client = _make_mock_client(mock_container)

    with patch("docker.from_env", return_value=mock_client):
        provider = DockerSandboxProvider()
        backend = provider.get_or_create(execute_timeout=300)

        assert isinstance(backend, DockerSandbox)
        # The execute_timeout is stored internally on the sandbox backend.
        assert backend._default_timeout == 300


def test_provider_handles_docker_client_kwargs() -> None:
    """Provider should accept docker_client_kwargs without raising an error."""
    mock_container = _make_container()
    mock_client = _make_mock_client(mock_container)

    with patch("docker.from_env", return_value=mock_client) as mock_from_env:
        provider = DockerSandboxProvider()
        provider.get_or_create(docker_client_kwargs={"version": "auto"})

    mock_from_env.assert_called_with(version="auto")


def test_provider_reuses_container_with_kwargs() -> None:
    """Provider should pass kwargs when reattaching to an existing container."""
    mock_container = _make_container("test-container-123", "running", "test-container-123")
    mock_client = _make_mock_client(mock_container)

    with patch("docker.from_env", return_value=mock_client):
        provider = DockerSandboxProvider()
        backend = provider.get_or_create(
            sandbox_id="test-container-123",
            working_dir="/custom",
            execute_timeout=600,
        )

        assert isinstance(backend, DockerSandbox)
        assert backend._default_timeout == 600


def test_provider_passes_container_name() -> None:
    """Provider should pass container_name to DockerSandbox creation."""
    mock_container = _make_container()
    mock_client = _make_mock_client(mock_container)

    with patch("docker.from_env", return_value=mock_client):
        provider = DockerSandboxProvider()
        provider.get_or_create(container_name="my-custom-sandbox")

    call_kwargs = mock_client.containers.run.call_args[1]
    assert call_kwargs["name"] == "my-custom-sandbox"


def test_provider_passes_auto_remove() -> None:
    """Provider should pass auto_remove to DockerSandbox creation."""
    mock_container = _make_container()
    mock_client = _make_mock_client(mock_container)

    with patch("docker.from_env", return_value=mock_client):
        provider = DockerSandboxProvider()
        backend = provider.get_or_create(auto_remove=False)

        assert isinstance(backend, DockerSandbox)
        assert backend._auto_remove is False


def test_provider_passes_max_output_bytes() -> None:
    """Provider should pass max_output_bytes to DockerSandbox creation."""
    mock_container = _make_container()
    mock_client = _make_mock_client(mock_container)

    with patch("docker.from_env", return_value=mock_client):
        provider = DockerSandboxProvider()
        backend = provider.get_or_create(max_output_bytes=1024 * 1024)

        assert isinstance(backend, DockerSandbox)
        assert backend._max_output_bytes == 1024 * 1024


def test_provider_passes_docker_client_kwargs_on_reconnect() -> None:
    """Provider should propagate docker_client_kwargs when reconnecting to a container."""
    mock_container = _make_container("test-container-123", "running", "test-container-123")
    mock_client = _make_mock_client(mock_container)

    with patch("docker.from_env", return_value=mock_client) as mock_from_env:
        provider = DockerSandboxProvider()
        provider.get_or_create(
            sandbox_id="test-container-123",
            docker_client_kwargs={"version": "1.41"},
        )

    # docker.from_env should be called with the client kwargs for reconnection
    from_env_calls = [c for c in mock_from_env.call_args_list if c[1] == {"version": "1.41"}]
    assert len(from_env_calls) >= 1
