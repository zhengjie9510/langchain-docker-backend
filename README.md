# langchain-docker-backend

[English](README.md) | [简体中文](README_CN.md)

A lightweight Docker sandbox for AI agents. Use it as a **LangChain / Deep Agents backend**, interact with it directly in Python, or expose sandbox tools through an **optional MCP server**.

Run commands and work with files inside Docker containers, using your preferred image and local or remote Docker daemon.

## Installation

Install the Docker sandbox backend:

```bash
pip install langchain-docker-backend
```

To also run an MCP server, install the optional extra:

```bash
pip install 'langchain-docker-backend[mcp]'
```

**Prerequisites:** Docker must be installed and running. Pull the default image before first use:

```bash
docker pull python:3.13-slim
```

`python:3.13-slim` is only the default. You can choose any suitable Docker image with `image=`, including a private or custom image.

## Usage

Choose the integration that fits your application:

- [MCP server](#mcp-server) — make sandbox operations available to MCP clients.
- [Deep Agents](#deep-agents) — use Docker as an agent backend.
- [LangChain](#langchain) — use the sandbox with `FilesystemMiddleware`.
- [Direct Python usage](#direct-python-usage) — call sandbox methods yourself.

### MCP server

The optional MCP adapter exposes seven tools backed by a `DockerSandbox`: `ls`, `read`, `write`, `edit`, `glob`, `grep`, and `execute`.

After installing the `[mcp]` extra, save the following as `mcp_server.py`:

```python
from langchain_docker_backend import DockerSandbox
from langchain_docker_backend.mcp import create_mcp_server


def main() -> None:
    with DockerSandbox() as sandbox:
        create_mcp_server(sandbox).run(transport="streamable-http")


if __name__ == "__main__":
    main()
```

Start it with:

```bash
python mcp_server.py
```

The default MCP endpoint is **`http://127.0.0.1:8000/mcp`**. Connect to it using an MCP client that supports Streamable HTTP. For example, Dify can use this endpoint if it is reachable from the Dify runtime. If the client runs on a different host or in another container, `127.0.0.1` will not refer to your MCP server; configure a reachable server address and the appropriate network access.

For configurable host and port options, see [`examples/mcp_server_example.py`](examples/mcp_server_example.py).

| MCP tool | What it does |
|---|---|
| `ls` | List files and directories |
| `read` | Read file contents (including paginated text) |
| `write` | Create or overwrite a text file |
| `edit` | Replace exact text in a file |
| `glob` | Find files by path pattern |
| `grep` | Search for literal text (not regular expressions) |
| `execute` | Run a shell command in the container |

**Access and isolation:** MCP clients can execute commands and modify files inside the sandbox. Do not expose this server to untrusted users without access controls. One server instance uses **one shared sandbox** across its clients; deploy separate instances or add isolation for multi-user workloads.

### Deep Agents

Use `DockerSandbox` as a backend for a Deep Agents agent. The example below uses Anthropic; install the corresponding model integration and configure its credentials first (or replace it with your model provider):

```bash
pip install langchain-anthropic
```

```python
from deepagents import create_deep_agent
from langchain_anthropic import ChatAnthropic
from langchain_docker_backend import DockerSandbox

with DockerSandbox() as sandbox:
    agent = create_deep_agent(
        model=ChatAnthropic(model="claude-sonnet-4-6"),
        system_prompt="You are a coding assistant with sandbox access.",
        backend=sandbox,
    )
    result = agent.invoke({
        "messages": [{"role": "user", "content": "Write and run a fizzbuzz script"}]
    })
    print(result)
```

### LangChain

Use `FilesystemMiddleware` to make sandbox operations available to a LangChain agent (using the same model-provider setup as above):

```python
from langchain.agents import create_agent
from langchain_anthropic import ChatAnthropic
from deepagents.middleware.filesystem import FilesystemMiddleware
from langchain_docker_backend import DockerSandbox

with DockerSandbox() as sandbox:
    agent = create_agent(
        model=ChatAnthropic(model="claude-sonnet-4-6"),
        middleware=[FilesystemMiddleware(backend=sandbox)],
    )
    result = agent.invoke({
        "messages": [{"role": "user", "content": "Write and run a fizzbuzz script"}]
    })
    print(result)
```

### Direct Python usage

Use sandbox operations without an agent:

```python
from langchain_docker_backend import DockerSandbox

with DockerSandbox(image="python:3.13-slim") as sandbox:
    result = sandbox.execute("python --version")
    print(result.output, result.exit_code)

    sandbox.write("/workspace/hello.txt", "Hello from Docker!\n")
    file = sandbox.read("/workspace/hello.txt")
    print(file.file_data["content"])

    for item in sandbox.ls("/workspace").entries:
        print(item["path"])

    sandbox.edit("/workspace/hello.txt", "Hello", "Hi")
    sandbox.upload_files([("data.bin", b"\x00\x01\x02")])
    downloaded = sandbox.download_files(["data.bin"])
    print(downloaded[0].content)
```

The default container is removed on `close()` or when leaving the `with` block. You can override this with `auto_remove=False` (the container is still stopped on close).

## Connecting to Docker

`DockerSandbox` connects using `docker.from_env()`. It honors standard Docker environment settings such as `DOCKER_HOST`, and can also accept explicit Docker client options through `docker_client_kwargs`.

### Local Docker

With a local Docker daemon, no special connection configuration is needed:

```python
sandbox = DockerSandbox()
```

On typical Linux systems the default connection uses `/var/run/docker.sock`; Docker Desktop and other platforms may use different endpoints.

### Running the application inside a container

You can mount the host's Docker socket into the application container:

```bash
docker run -v /var/run/docker.sock:/var/run/docker.sock your-image
```

`DockerSandbox()` can then talk to that daemon from inside the application container. **Mounting the Docker socket grants powerful access to the host Docker daemon**; only do this in a trusted environment.

Alternatively, run a separate Docker daemon with Docker-in-Docker (DinD), which typically requires privileged mode. For example, with the appropriate daemon already running and accessible:

```python
sandbox = DockerSandbox(
    docker_client_kwargs={"base_url": "unix:///var/run/docker.sock"}
)
```

### Remote Docker

For a remote Docker daemon secured with TLS, configure the standard Docker environment variables:

```bash
export DOCKER_HOST=tcp://your-docker-host:2376
export DOCKER_TLS_VERIFY=1
export DOCKER_CERT_PATH=/path/to/docker-certs
```

The certificate directory should contain the Docker client certificates (`ca.pem`, `cert.pem`, and `key.pem`). `DockerSandbox()` then uses these settings through `docker.from_env()`.

Alternatively, configure the Docker client explicitly:

```python
import docker.tls
from langchain_docker_backend import DockerSandbox

sandbox = DockerSandbox(
    docker_client_kwargs={
        "base_url": "tcp://your-docker-host:2376",
        "tls": docker.tls.TLSConfig(
            ca_cert="/path/to/ca.pem",
            client_cert=("/path/to/cert.pem", "/path/to/key.pem"),
            verify=True,
        ),
    }
)
```

Do **not** expose an unauthenticated Docker TCP API to untrusted networks.

## Network and resource configuration

You can choose container networking, DNS, GPUs, and other Docker container options:

```python
from langchain_docker_backend import DockerSandbox

with DockerSandbox(
    network_mode="bridge",     # also "host", "none", "container:<id>"
    dns=["1.1.1.1"],
    # gpus="all",              # optional; requires NVIDIA Container Toolkit
    container_kwargs={
        "mem_limit": "4g",
        "nano_cpus": 2_000_000_000,
        "shm_size": "2g",
    },
) as sandbox:
    print(sandbox.execute("python --version").output)
```

- **Network:** Docker's default `bridge` network generally permits outbound connections; use `network_mode="none"` for a container without network access. If network requests fail, check DNS and firewall settings.
- **GPU:** NVIDIA GPU access requires host-side NVIDIA Container Toolkit configuration. Other devices can be passed through via Docker container options when supported.
- **Isolation:** Host networking, device mounts, `privileged=True`, and Docker socket access can reduce isolation. Choose settings according to your threat model.

## Design

`DockerSandbox` implements Deep Agents' `BaseSandbox` interface, providing command execution and file operations, including synchronous and asynchronous methods. When used with Deep Agents or `FilesystemMiddleware`, agent-facing file and execution operations can be exposed as tools.

`upload_files()` and `download_files()` are intended for explicit application-side use rather than being exposed as agent tools by this package. The MCP adapter separately exposes the seven tools listed above; it does not expose binary upload/download tools.

## API reference

### `DockerSandbox` options

| Parameter | Default | Description |
|---|---|---|
| `image` | `python:3.13-slim` | Docker image to run |
| `container_name` | Generated | Container name |
| `volumes` | `{}` | Host-to-container volume mounts |
| `working_dir` | `/workspace` | Working directory inside the container |
| `auto_remove` | `True` | Remove the container when closing (it is stopped either way) |
| `execute_timeout` | `120` | Default command timeout in seconds |
| `max_output_bytes` | `512000` | Maximum command output bytes before truncation |
| `docker_client_kwargs` | `None` | Options passed to `docker.from_env()` |
| `network_mode` | `None` | Docker network mode (Docker default when omitted) |
| `dns` | `None` | Custom DNS servers |
| `gpus` | `None` | `"all"` or a positive GPU count |
| `container_kwargs` | `None` | Additional `containers.run()` options |

### Main methods

| Method | Description |
|---|---|
| `execute(command, *, timeout=None)` | Execute a command; returns an `ExecuteResponse` |
| `write(path, content)` | Create or overwrite a text file |
| `read(path)` | Read a file |
| `ls(path)` | List a directory |
| `edit(path, old_string, new_string, replace_all=False)` | Replace text |
| `glob(pattern, path=None)` | Find files by path pattern |
| `grep(pattern, path=None, glob=None)` | Search for literal text |
| `upload_files(files)` | Upload binary files as `(path, bytes)` pairs |
| `download_files(paths)` | Download files by path |
| `close()` | Stop the container, optionally remove it, and close the Docker client |

`ExecuteResponse` includes `output` (combined stdout/stderr), `exit_code`, and `truncated` (whether the output was shortened).
