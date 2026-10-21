"""Tests for langchain_docker_backend package."""

from unittest.mock import MagicMock

import docker
import pytest


# -- Package metadata --------------------------------------------------------


def test_version():
    """Version string is available."""
    import langchain_docker_backend

    assert hasattr(langchain_docker_backend, "__version__")
    assert isinstance(langchain_docker_backend.__version__, str)


def test_all_exports():
    """__all__ exposes the public API."""
    import langchain_docker_backend

    assert "DockerSandbox" in langchain_docker_backend.__all__
    assert "DockerImageNotFound" in langchain_docker_backend.__all__


def test_class_inheritance():
    """DockerSandbox inherits from BaseSandbox (ABC — guarantees abstract methods)."""
    from langchain_docker_backend import DockerSandbox
    from deepagents.backends.sandbox import BaseSandbox

    assert issubclass(DockerSandbox, BaseSandbox)


def test_docker_image_not_found():
    """DockerImageNotFound carries the image name in message and attribute."""
    from langchain_docker_backend import DockerImageNotFound

    exc = DockerImageNotFound("nonexistent:image")
    assert "nonexistent:image" in str(exc)
    assert exc.image == "nonexistent:image"


# -- Container configuration (mocked Docker client) --------------------------


@pytest.fixture
def mock_client(monkeypatch):
    """Replace ``docker.from_env`` with a mock client."""
    client = MagicMock()
    client.containers.run.return_value.exec_run.return_value = (0, b"")
    monkeypatch.setattr(docker, "from_env", lambda **kwargs: client)
    return client


def _run_kwargs(client):
    return client.containers.run.call_args.kwargs


def test_default_run_kwargs_unchanged(mock_client):
    """Without new options, no network/dns/device kwargs are passed."""
    from langchain_docker_backend import DockerSandbox

    DockerSandbox()
    kwargs = _run_kwargs(mock_client)
    assert kwargs["detach"] is True
    assert kwargs["command"] == "tail -f /dev/null"
    for key in ("network_mode", "dns", "device_requests"):
        assert key not in kwargs


def test_network_mode_and_dns_forwarded(mock_client):
    """network_mode and dns reach containers.run()."""
    from langchain_docker_backend import DockerSandbox

    DockerSandbox(network_mode="host", dns=["1.1.1.1", "8.8.8.8"])
    kwargs = _run_kwargs(mock_client)
    assert kwargs["network_mode"] == "host"
    assert kwargs["dns"] == ["1.1.1.1", "8.8.8.8"]


@pytest.mark.parametrize(("gpus", "count"), [("all", -1), (2, 2)])
def test_gpus_device_request(mock_client, gpus, count):
    """gpus is translated into a GPU DeviceRequest."""
    from langchain_docker_backend import DockerSandbox

    DockerSandbox(gpus=gpus)
    (request,) = _run_kwargs(mock_client)["device_requests"]
    assert request["Count"] == count
    assert request["Capabilities"] == [["gpu"]]


def test_gpus_merged_with_user_device_requests(mock_client):
    """gpus is appended to device_requests given in container_kwargs."""
    from langchain_docker_backend import DockerSandbox

    user_request = docker.types.DeviceRequest(driver="custom", count=1)
    DockerSandbox(gpus="all", container_kwargs={"device_requests": [user_request]})
    requests = _run_kwargs(mock_client)["device_requests"]
    assert len(requests) == 2
    assert requests[0] is user_request
    assert requests[1]["Capabilities"] == [["gpu"]]


def test_container_kwargs_forwarded(mock_client):
    """container_kwargs are passed through to containers.run()."""
    from langchain_docker_backend import DockerSandbox

    DockerSandbox(
        container_kwargs={"mem_limit": "1g", "devices": ["/dev/null:/dev/null"]}
    )
    kwargs = _run_kwargs(mock_client)
    assert kwargs["mem_limit"] == "1g"
    assert kwargs["devices"] == ["/dev/null:/dev/null"]


@pytest.mark.parametrize(
    "options",
    [
        {"container_kwargs": {"image": "other"}},
        {"container_kwargs": {"auto_remove": True}},
        {"network_mode": "host", "container_kwargs": {"network_mode": "bridge"}},
        {"dns": ["1.1.1.1"], "container_kwargs": {"dns": ["8.8.8.8"]}},
        {"gpus": 0},
        {"gpus": "some"},
        {"gpus": True},
    ],
)
def test_invalid_container_options(mock_client, options):
    """Invalid options raise ValueError before any container is created."""
    from langchain_docker_backend import DockerSandbox

    with pytest.raises(ValueError):
        DockerSandbox(**options)
    mock_client.containers.run.assert_not_called()


# -- Integration tests (require Docker daemon) -------------------------------


@pytest.mark.integration
class TestDockerSandboxIntegration:
    """End-to-end tests that require a running Docker daemon."""

    def test_full_workflow(self):
        """Execute, write, read, ls, edit, and timeout in one container."""
        from langchain_docker_backend import DockerSandbox

        with DockerSandbox(image="ghcr.io/astral-sh/uv:python3.13-bookworm-slim") as sandbox:
            # 1. Basic command execution
            result = sandbox.execute("echo 'Hello from Docker!'")
            assert result.exit_code == 0
            assert "Hello from Docker!" in result.output

            # 2. Python execution
            result = sandbox.execute(
                "python -c 'import sys; print(f\"Python {sys.version}\")'"
            )
            assert result.exit_code == 0
            assert "Python" in result.output

            # 3. Write file
            write_result = sandbox.write("/workspace/test.txt", "Hello, World!")
            assert write_result.error is None

            # 4. Read file
            read_result = sandbox.read("/workspace/test.txt")
            assert read_result.file_data is not None
            assert "Hello, World!" in read_result.file_data["content"]

            # 5. List directory
            ls_result = sandbox.ls("/workspace")
            assert ls_result.entries is not None
            paths = [e["path"] for e in ls_result.entries]
            assert any(p.endswith("/test.txt") for p in paths)

            # 6. Edit file (find and replace)
            edit_result = sandbox.edit("/workspace/test.txt", "Hello", "你好")
            assert edit_result.occurrences > 0
            read_result = sandbox.read("/workspace/test.txt")
            assert "你好" in read_result.file_data["content"]

            # 7. Timeout
            result = sandbox.execute("sleep 10", timeout=2)
            assert "timed out" in result.output.lower()
            assert result.exit_code == 124

    def test_upload_and_download_files(self):
        """upload_files writes bytes, download_files reads them back."""
        from langchain_docker_backend import DockerSandbox

        with DockerSandbox(image="ghcr.io/astral-sh/uv:python3.13-bookworm-slim") as sandbox:
            # Upload multiple files
            files = [
                ("/workspace/a.txt", b"alpha"),
                ("/workspace/b.txt", b"beta"),
            ]
            upload_results = sandbox.upload_files(files)
            assert len(upload_results) == 2
            for r in upload_results:
                assert r.error is None

            # Download them back
            download_results = sandbox.download_files(["/workspace/a.txt", "/workspace/b.txt"])
            assert len(download_results) == 2
            contents = {r.path: r.content for r in download_results}
            assert contents["/workspace/a.txt"] == b"alpha"
            assert contents["/workspace/b.txt"] == b"beta"

    def test_download_nonexistent_file(self):
        """download_files returns error for missing files."""
        from langchain_docker_backend import DockerSandbox

        with DockerSandbox(image="ghcr.io/astral-sh/uv:python3.13-bookworm-slim") as sandbox:
            results = sandbox.download_files(["/workspace/nope.txt"])
            assert len(results) == 1
            assert results[0].content is None
            assert results[0].error == "file_not_found"

    def test_network_mode_none(self):
        """network_mode='none' leaves only the loopback interface."""
        from langchain_docker_backend import DockerSandbox

        with DockerSandbox(
            image="ghcr.io/astral-sh/uv:python3.13-bookworm-slim",
            network_mode="none",
        ) as sandbox:
            result = sandbox.execute("ls /sys/class/net")
            assert result.exit_code == 0
            assert result.output.split() == ["lo"]

    def test_custom_dns(self):
        """dns servers are written to the container's resolv.conf."""
        from langchain_docker_backend import DockerSandbox

        with DockerSandbox(
            image="ghcr.io/astral-sh/uv:python3.13-bookworm-slim",
            dns=["1.1.1.1"],
        ) as sandbox:
            result = sandbox.execute("cat /etc/resolv.conf")
            assert "1.1.1.1" in result.output

    def test_container_kwargs_mem_limit(self):
        """container_kwargs are applied to the container's host config."""
        from langchain_docker_backend import DockerSandbox

        with DockerSandbox(
            image="ghcr.io/astral-sh/uv:python3.13-bookworm-slim",
            container_kwargs={"mem_limit": "256m"},
        ) as sandbox:
            sandbox._container.reload()
            assert sandbox._container.attrs["HostConfig"]["Memory"] == 256 * 1024 * 1024
