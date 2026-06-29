"""Docker sandbox backend.

[`DockerSandbox`][langchain_docker_backend.sandbox.DockerSandbox] implements
[`BaseSandbox`][deepagents.backends.sandbox.BaseSandbox] using Docker SDK for
Python.  All file operations and command execution run inside an isolated
container.

Usage:
    ```python
    from langchain_docker_backend import DockerSandbox

    with DockerSandbox(image="ghcr.io/astral-sh/uv:python3.13-bookworm-slim") as sandbox:
        result = sandbox.execute("echo 'Hello!'")
        print(result.output)
    ```
"""

from __future__ import annotations

import io
import logging
import tarfile
import threading
import uuid
from typing import Any

import docker
from docker.models.containers import Container

from deepagents.backends.protocol import (
    ExecuteResponse,
    FileDownloadResponse,
    FileUploadResponse,
)
from deepagents.backends.sandbox import BaseSandbox

logger = logging.getLogger(__name__)

_DEFAULT_IMAGE = "ghcr.io/astral-sh/uv:python3.13-bookworm-slim"
_DEFAULT_WORKING_DIR = "/workspace"
_DEFAULT_EXECUTE_TIMEOUT = 120  # seconds
_DEFAULT_MAX_OUTPUT_BYTES = 500 * 1024  # 500 KiB


class DockerSandbox(BaseSandbox):
    """Docker container sandbox.

    Manages the full container lifecycle via Docker SDK.  All `execute()`,
    `upload_files()`, and `download_files()` calls run inside the container.

    Subclasses of `BaseSandbox` must implement `execute()`, `upload_files()`,
    `download_files()`, and the `id` property — this class provides all four.

    Args:
        image: Docker image name.
        container_name: Container name.  Auto-generated when ``None``.
        volumes: Volume mounts, e.g.
            ``{"/host": {"bind": "/container", "mode": "rw"}}``.
        working_dir: Working directory inside the container.
        auto_remove: Remove the container on ``close()``.
        execute_timeout: Default timeout in seconds for ``execute()``.
        max_output_bytes: Maximum output bytes before truncation.
        docker_client_kwargs: Extra keyword arguments for ``docker.from_env()``.
    """

    def __init__(
        self,
        image: str = _DEFAULT_IMAGE,
        container_name: str | None = None,
        volumes: dict[str, dict[str, str]] | None = None,
        working_dir: str = _DEFAULT_WORKING_DIR,
        auto_remove: bool = True,
        execute_timeout: int = _DEFAULT_EXECUTE_TIMEOUT,
        max_output_bytes: int = _DEFAULT_MAX_OUTPUT_BYTES,
        docker_client_kwargs: dict[str, Any] | None = None,
    ) -> None:
        self._image = image
        self._container_name = container_name or f"sandbox-{uuid.uuid4().hex[:12]}"
        self._volumes = volumes or {}
        self._working_dir = working_dir
        self._auto_remove = auto_remove
        self._default_timeout = execute_timeout
        self._max_output_bytes = max_output_bytes

        client_kwargs = docker_client_kwargs or {}
        self._client = docker.from_env(**client_kwargs)

        # Verify the image is available locally before creating the container.
        self._check_image()

        self._container = self._create_container()
        self.execute(f"mkdir -p {working_dir}")

        logger.info(
            "DockerSandbox initialized: container=%s, image=%s",
            self._container.short_id,
            image,
        )

    def _check_image(self) -> None:
        """Check that the Docker image exists locally.

        Raises:
            DockerImageNotFound: If the image is not available locally.
        """
        try:
            self._client.images.get(self._image)
        except docker.errors.ImageNotFound:
            raise DockerImageNotFound(self._image) from None

    def _create_container(self) -> Container:
        """Create and start the container."""
        return self._client.containers.run(
            image=self._image,
            name=self._container_name,
            command="tail -f /dev/null",
            working_dir=self._working_dir,
            volumes=self._volumes,
            detach=True,
            stdin_open=True,
            tty=False,
        )

    @property
    def id(self) -> str:
        """Container short ID."""
        return self._container.short_id

    def execute(
        self,
        command: str,
        *,
        timeout: int | None = None,
    ) -> ExecuteResponse:
        """Execute a shell command in the container.

        Args:
            command: Shell command to execute.
            timeout: Timeout in seconds.  Uses the default when ``None``.

        Returns:
            `ExecuteResponse` with combined output, exit code, and truncation
            flag.
        """
        if not command or not isinstance(command, str):
            return ExecuteResponse(
                output="Error: Command must be a non-empty string.",
                exit_code=1,
                truncated=False,
            )

        effective_timeout = timeout if timeout is not None else self._default_timeout

        result_holder: dict[str, Any] = {}
        execution_done = threading.Event()

        def run_command() -> None:
            try:
                exit_code, output = self._container.exec_run(
                    cmd=["sh", "-c", command],
                    stdout=True,
                    stderr=True,
                    demux=False,
                    workdir=self._working_dir,
                )
                result_holder["exit_code"] = exit_code
                result_holder["output"] = (
                    output.decode("utf-8", errors="replace") if output else ""
                )
            except Exception as e:
                result_holder["exit_code"] = 1
                result_holder["output"] = (
                    f"Error executing command: {type(e).__name__}: {e}"
                )
            finally:
                execution_done.set()

        thread = threading.Thread(target=run_command, daemon=True)
        thread.start()

        if not execution_done.wait(timeout=effective_timeout):
            return ExecuteResponse(
                output=(
                    f"Error: Command timed out after {effective_timeout} seconds."
                ),
                exit_code=124,
                truncated=False,
            )

        output = result_holder.get("output", "")
        exit_code = result_holder.get("exit_code", 1)

        # Truncate by bytes, not characters, to respect max_output_bytes.
        truncated = False
        encoded = output.encode("utf-8")
        if len(encoded) > self._max_output_bytes:
            output = encoded[: self._max_output_bytes].decode(
                "utf-8", errors="ignore"
            )
            output += f"\n\n... Output truncated at {self._max_output_bytes} bytes."
            truncated = True

        return ExecuteResponse(
            output=output,
            exit_code=exit_code,
            truncated=truncated,
        )

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        """Upload files to the container via tar archive.

        Args:
            files: List of ``(path, content)`` tuples.

        Returns:
            List of `FileUploadResponse`, one per file.
        """
        responses: list[FileUploadResponse] = []

        for file_path, content in files:
            try:
                if not file_path.startswith("/"):
                    file_path = f"{self._working_dir}/{file_path}"

                dir_path = file_path.rsplit("/", 1)[0] if "/" in file_path else "/"

                # Build a single-file tar archive.
                tar_stream = io.BytesIO()
                with tarfile.open(fileobj=tar_stream, mode="w") as tar:
                    info = tarfile.TarInfo(name=file_path.lstrip("/"))
                    info.size = len(content)
                    tar.addfile(info, io.BytesIO(content))

                tar_stream.seek(0)

                self.execute(f"mkdir -p {dir_path}")
                self._container.put_archive("/", tar_stream)

                responses.append(FileUploadResponse(path=file_path, error=None))
                logger.debug("Uploaded file: %s (%d bytes)", file_path, len(content))

            except Exception as e:
                error_msg = f"Failed to upload {file_path}: {type(e).__name__}: {e}"
                logger.error(error_msg)
                responses.append(FileUploadResponse(path=file_path, error=error_msg))

        return responses

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        """Download files from the container via tar archive.

        Args:
            paths: List of file paths to download.

        Returns:
            List of `FileDownloadResponse`, one per file.
        """
        responses: list[FileDownloadResponse] = []

        for file_path in paths:
            try:
                if not file_path.startswith("/"):
                    file_path = f"{self._working_dir}/{file_path}"

                tar_stream, _stat = self._container.get_archive(file_path)

                tar_data = io.BytesIO()
                for chunk in tar_stream:
                    tar_data.write(chunk)
                tar_data.seek(0)

                with tarfile.open(fileobj=tar_data, mode="r") as tar:
                    members = tar.getmembers()
                    if not members:
                        responses.append(
                            FileDownloadResponse(
                                path=file_path,
                                content=None,
                                error="file_not_found",
                            )
                        )
                        continue

                    f = tar.extractfile(members[0])
                    if f is None:
                        responses.append(
                            FileDownloadResponse(
                                path=file_path,
                                content=None,
                                error="file_not_found",
                            )
                        )
                        continue

                    content = f.read()
                    responses.append(
                        FileDownloadResponse(
                            path=file_path, content=content, error=None
                        )
                    )
                    logger.debug(
                        "Downloaded file: %s (%d bytes)", file_path, len(content)
                    )

            except docker.errors.NotFound:
                responses.append(
                    FileDownloadResponse(
                        path=file_path, content=None, error="file_not_found"
                    )
                )
            except Exception as e:
                error_msg = (
                    f"Failed to download {file_path}: {type(e).__name__}: {e}"
                )
                logger.error(error_msg)
                responses.append(
                    FileDownloadResponse(
                        path=file_path, content=None, error=error_msg
                    )
                )

        return responses

    def close(self) -> None:
        """Stop and optionally remove the container."""
        try:
            self._container.stop(timeout=5)
            if self._auto_remove:
                self._container.remove(force=True)
                logger.info("Container %s removed", self._container.short_id)
            else:
                logger.info("Container %s stopped", self._container.short_id)
        except Exception as e:
            logger.warning("Error closing container: %s", e)
        finally:
            self._client.close()

    def __enter__(self) -> DockerSandbox:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()


class DockerImageNotFound(Exception):
    """Raised when the requested Docker image is not available locally.

    Pull the image before creating the sandbox::

        docker pull ghcr.io/astral-sh/uv:python3.13-bookworm-slim
    """

    def __init__(self, image: str) -> None:
        self.image = image
        super().__init__(
            f"Docker image '{image}' not found locally. "
            f"Pull it first: docker pull {image}"
        )
