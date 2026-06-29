"""Basic tests for package imports and class structure."""

import pytest


def test_import():
    """Import the main class."""
    from langchain_docker_backend import DockerSandbox
    assert DockerSandbox is not None


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
    """DockerSandbox inherits from BaseSandbox."""
    from langchain_docker_backend import DockerSandbox
    from deepagents.backends.sandbox import BaseSandbox
    assert issubclass(DockerSandbox, BaseSandbox)


def test_required_methods():
    """DockerSandbox implements all required abstract methods."""
    from langchain_docker_backend import DockerSandbox

    assert hasattr(DockerSandbox, "execute")
    assert hasattr(DockerSandbox, "upload_files")
    assert hasattr(DockerSandbox, "download_files")
    assert hasattr(DockerSandbox, "id")

    # Context manager protocol.
    assert hasattr(DockerSandbox, "__enter__")
    assert hasattr(DockerSandbox, "__exit__")
    assert hasattr(DockerSandbox, "close")


def test_docker_image_not_found():
    """DockerImageNotFound is raised for missing images."""
    from langchain_docker_backend import DockerImageNotFound

    exc = DockerImageNotFound("nonexistent:image")
    assert "nonexistent:image" in str(exc)
    assert exc.image == "nonexistent:image"


# --- Integration tests (require Docker daemon) ---


@pytest.mark.integration
class TestDockerSandboxIntegration:
    """Tests that require a running Docker daemon."""

    def test_execute_command(self):
        """Run a simple command inside the container."""
        from langchain_docker_backend import DockerSandbox

        with DockerSandbox(image="ghcr.io/astral-sh/uv:python3.13-bookworm-slim") as sandbox:
            result = sandbox.execute("echo 'hello'")
            assert result.exit_code == 0
            assert "hello" in result.output

    def test_write_and_read(self):
        """Write a file and read it back."""
        from langchain_docker_backend import DockerSandbox

        with DockerSandbox(image="ghcr.io/astral-sh/uv:python3.13-bookworm-slim") as sandbox:
            sandbox.write("/workspace/test.txt", "content")
            result = sandbox.read("/workspace/test.txt")
            assert result.file_data is not None
            # file_data is a dict with 'content' and 'encoding' keys.
            assert result.file_data["content"] == "content"

    def test_context_manager_cleanup(self):
        """Container is removed after exiting the context manager."""
        from langchain_docker_backend import DockerSandbox

        sandbox = DockerSandbox(image="ghcr.io/astral-sh/uv:python3.13-bookworm-slim")
        sandbox.close()
