# langchain-docker-backend

Docker sandbox backend for AI agents — execute code safely in isolated containers.

## Installation

```bash
pip install langchain-docker-backend
```

**Prerequisites:** Docker must be installed and running. The default image below works out of the box — pull it before first use:

```bash
docker pull ghcr.io/astral-sh/uv:python3.13-bookworm-slim
```

> **💡 Any Docker image works.** `ghcr.io/astral-sh/uv:python3.13-bookworm-slim` is just the default. You can use any image — `python:3.13-slim`, `ubuntu:22.04`, `node:20`, or your own custom image. Pass it via `image=` to match your runtime needs.

## Usage

### deepagents

Plug `DockerSandbox` into a deep agent — the agent gets a full set of sandbox tools and runs code in an isolated container:

```python
from deepagents import create_deep_agent
from langchain_anthropic import ChatAnthropic
from langchain_docker_backend import DockerSandbox

sandbox = DockerSandbox()

try:
    agent = create_deep_agent(
        model=ChatAnthropic(model="claude-sonnet-4-6"),
        system_prompt="You are a coding assistant with sandbox access.",
        backend=sandbox,
    )
    result = agent.invoke({
        "messages": [{"role": "user", "content": "Write and run a fizzbuzz script"}]
    })
    print(result)
finally:
    sandbox.close()
```

### LangChain

With LangChain, wire it through `FilesystemMiddleware`:

```python
from langchain.agents import create_agent
from langchain_anthropic import ChatAnthropic
from deepagents.middleware.filesystem import FilesystemMiddleware
from langchain_docker_backend import DockerSandbox

sandbox = DockerSandbox()

try:
    agent = create_agent(
        model=ChatAnthropic(model="claude-sonnet-4-6"),
        middleware=[FilesystemMiddleware(backend=sandbox)],
    )
    result = agent.invoke({
        "messages": [{"role": "user", "content": "Write a fizzbuzz script and run it"}]
    })
finally:
    sandbox.close()
```

### Direct Usage

Beyond agent use, you can interact with the sandbox directly — execute commands, read and write files, list directories, edit file content.

Pick any image to suit your stack:
```python
sandbox = DockerSandbox(image="python:3.13-slim")      # bare Python
sandbox = DockerSandbox(image="node:20")                # Node.js
sandbox = DockerSandbox(image="ubuntu:22.04")           # Ubuntu
sandbox = DockerSandbox()                               # default (uv + Python 3.13)
```

```python
from langchain_docker_backend import DockerSandbox

sandbox = DockerSandbox()

try:
    # Execute commands
    result = sandbox.execute("echo 'Hello from Docker!'")
    print(result.output)      # Hello from Docker!
    print(result.exit_code)   # 0

    # Write a file
    sandbox.write("/workspace/test.txt", "Hello, World!")

    # Read it back
    file = sandbox.read("/workspace/test.txt")
    print(file.file_data["content"])  # Hello, World!

    # List a directory
    ls = sandbox.ls("/workspace")
    for entry in ls.entries:
        print(entry["path"], entry.get("is_dir", False))

    # Find and replace
    sandbox.edit("/workspace/test.txt", "Hello", "你好")

    # Upload / download binary files
    sandbox.upload_files([("data.bin", b"\x00\x01\x02")])
    files = sandbox.download_files(["data.bin"])
    print(files[0].content)  # b'\x00\x01\x02'

    # Commands time out
    result = sandbox.execute("sleep 10", timeout=2)
    print(result.exit_code)   # 124
finally:
    sandbox.close()
```

## Design

`DockerSandbox` implements `BaseSandbox`, which defines a full set of sandbox operations — synchronous and asynchronous — including `execute`, file reads and writes, directory listing, glob, grep, and more.

When plugged into `FilesystemMiddleware` or `create_deep_agent(backend=...)`, most operations are exposed as tools that the **agent model decides** when to invoke: the model autonomously chooses to `ls` a directory, `read_file`, `write_file`, `execute` a command, etc.

The exception is `upload_files` and `download_files`. These remain **developer-only** — the developer controls what data enters the sandbox and what results to extract, not the model.

## API Reference

### `DockerSandbox`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `image` | `str` | `ghcr.io/astral-sh/uv:python3.13-bookworm-slim` | Any Docker image (public, private, or custom) |
| `container_name` | `str \| None` | auto-generated | Container name |
| `volumes` | `dict` | `{}` | Volume mounts |
| `working_dir` | `str` | `/workspace` | Working directory inside container |
| `auto_remove` | `bool` | `True` | Remove container on close |
| `execute_timeout` | `int` | `120` | Default timeout in seconds |
| `max_output_bytes` | `int` | `512000` | Max output bytes before truncation |

### Key Methods

| Method | Description |
|--------|-------------|
| `execute(command, *, timeout)` | Run a shell command |
| `write(path, content)` | Write a text file |
| `read(path)` | Read a text file |
| `ls(path)` | List directory contents |
| `edit(path, find, replace)` | Find and replace in a file |
| `upload_files(files)` | Upload binary files (tar-based) |
| `download_files(paths)` | Download binary files (tar-based) |
| `close()` | Stop and optionally remove container |

### `ExecuteResponse`

| Field | Type | Description |
|-------|------|-------------|
| `output` | `str` | Combined stdout + stderr |
| `exit_code` | `int` | Command exit code |
| `truncated` | `bool` | Whether output was truncated |
