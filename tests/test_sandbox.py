"""Tests for langchain_docker_backend package."""

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
