# langchain-docker-backend

[English](README.md) | [简体中文](README_CN.md)

面向 AI Agent 的轻量级 Docker 沙箱。既可以作为 **LangChain / Deep Agents 的 Backend**，也可以在 Python 中直接使用，或通过**可选的 MCP 服务**对外提供沙箱工具。

在 Docker 容器中执行命令和操作文件，支持自定义镜像，以及连接本地或远程 Docker 服务。

## 安装

安装 Docker 沙箱后端：

```bash
pip install langchain-docker-backend
```

如需使用 MCP 服务，安装可选依赖：

```bash
pip install 'langchain-docker-backend[mcp]'
```

**前置条件：** 需要安装并启动 Docker。首次使用前，拉取默认镜像：

```bash
docker pull python:3.13-slim
```

`python:3.13-slim` 只是默认镜像。通过 `image=` 参数可以指定其他镜像，包括私有镜像或自定义镜像。

## 使用方式

根据应用场景选择接入方式：

- [MCP 服务](#mcp-服务)：通过 MCP 客户端使用沙箱工具。
- [Deep Agents](#deep-agents)：作为 Agent 的 Docker Backend。
- [LangChain](#langchain)：通过 `FilesystemMiddleware` 接入。
- [直接使用 Python](#直接使用-python)：直接调用沙箱方法。

### MCP 服务

可选 MCP 适配层提供七个基于 `DockerSandbox` 的工具：`ls`、`read`、`write`、`edit`、`glob`、`grep` 和 `execute`。

安装 `[mcp]` 可选依赖后，将以下代码保存为 `mcp_server.py`：

```python
from langchain_docker_backend import DockerSandbox
from langchain_docker_backend.mcp import create_mcp_server


def main() -> None:
    with DockerSandbox() as sandbox:
        create_mcp_server(sandbox).run(transport="streamable-http")


if __name__ == "__main__":
    main()
```

启动服务：

```bash
python mcp_server.py
```

默认 MCP 地址为 **`http://127.0.0.1:8000/mcp`**，可通过支持 Streamable HTTP 的 MCP 客户端连接。例如 Dify 可以连接该地址，但前提是 Dify 所在运行环境能够访问 MCP 服务。如果客户端位于其他主机或容器中，它的 `127.0.0.1` 并不是 MCP 服务所在的主机，需要配置实际可访问的服务地址和网络。

若需要自定义监听地址和端口，参见 [`examples/mcp_server_example.py`](examples/mcp_server_example.py)。

| MCP 工具 | 功能 |
|---|---|
| `ls` | 列出文件及目录 |
| `read` | 读取文件，支持文本分页 |
| `write` | 创建或覆盖文本文件 |
| `edit` | 精确替换文件内容 |
| `glob` | 根据路径模式查找文件 |
| `grep` | 按字面文本搜索，不支持正则表达式 |
| `execute` | 在容器中执行 Shell 命令 |

**访问控制与隔离：** MCP 客户端可以在沙箱中执行命令和修改文件。没有合适的访问控制时，不要将服务暴露给不可信用户。**一个服务实例使用一个共享沙箱**，多个客户端会访问同一个环境；多用户部署应分别创建实例或增加隔离机制。

### Deep Agents

将 `DockerSandbox` 作为 Deep Agents 的 Backend。下面示例使用 Anthropic；请先安装模型集成包并配置好凭据，也可以换成其他模型提供商：

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
        system_prompt="你是一个有沙箱访问权限的编程助手。",
        backend=sandbox,
    )
    result = agent.invoke({
        "messages": [{"role": "user", "content": "写一个 fizzbuzz 脚本并运行"}]
    })
    print(result)
```

### LangChain

通过 `FilesystemMiddleware` 将沙箱接入 LangChain Agent（模型依赖与配置同上）：

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
        "messages": [{"role": "user", "content": "写一个 fizzbuzz 脚本并运行"}]
    })
    print(result)
```

### 直接使用 Python

不依赖 Agent，也可以直接操作沙箱：

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

默认情况下，调用 `close()` 或退出 `with` 代码块时会删除容器。设置 `auto_remove=False` 可以保留容器，但关闭时仍会停止它。

## Docker 连接方式

`DockerSandbox` 通过 `docker.from_env()` 连接 Docker，支持读取 `DOCKER_HOST` 等标准环境变量，也可以使用 `docker_client_kwargs` 指定 Docker 客户端参数。

### 本地 Docker

本地 Docker daemon 已运行时，无需额外连接配置：

```python
sandbox = DockerSandbox()
```

在常见 Linux 环境中，默认连接使用 `/var/run/docker.sock`；Docker Desktop 等平台可能使用不同的连接地址。

### 在容器内部运行应用

可以将宿主机 Docker Socket 挂载到应用容器中：

```bash
docker run -v /var/run/docker.sock:/var/run/docker.sock your-image
```

此时容器内的 `DockerSandbox()` 可以连接宿主机 Docker daemon。**挂载 Docker Socket 意味着容器拥有对宿主机 Docker 服务的强大控制能力**，只应在可信环境中使用。

另一种方式是 Docker-in-Docker（DinD），它通过独立 Docker daemon 工作，通常需要特权模式。假设该 daemon 已启动且可以访问，连接方式例如：

```python
sandbox = DockerSandbox(
    docker_client_kwargs={"base_url": "unix:///var/run/docker.sock"}
)
```

### 远程 Docker

连接启用 TLS 的远程 Docker daemon，可以使用标准 Docker 环境变量：

```bash
export DOCKER_HOST=tcp://your-docker-host:2376
export DOCKER_TLS_VERIFY=1
export DOCKER_CERT_PATH=/path/to/docker-certs
```

证书目录应包含 Docker 客户端证书（`ca.pem`、`cert.pem`、`key.pem`）。`DockerSandbox()` 会通过 `docker.from_env()` 读取这些配置。

也可以在代码中显式指定 Docker 客户端 TLS 配置：

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

**不要将未认证的 Docker TCP API 暴露到不可信网络。**

## 网络与资源配置

创建容器时可以指定网络模式、DNS、GPU 及其他 Docker 资源选项：

```python
from langchain_docker_backend import DockerSandbox

with DockerSandbox(
    network_mode="bridge",     # 也可以为 "host"、"none"、"container:<id>"
    dns=["1.1.1.1"],
    # gpus="all",              # 可选，需要安装 NVIDIA Container Toolkit
    container_kwargs={
        "mem_limit": "4g",
        "nano_cpus": 2_000_000_000,
        "shm_size": "2g",
    },
) as sandbox:
    print(sandbox.execute("python --version").output)
```

- **网络：** Docker 默认的 `bridge` 网络通常允许容器访问外网；使用 `network_mode="none"` 可以关闭容器网络访问。遇到网络错误，优先排查 DNS 和防火墙设置。
- **GPU：** NVIDIA GPU 需要宿主机正确安装和配置 NVIDIA Container Toolkit。其他设备在 Docker 支持的情况下可通过容器参数透传。
- **隔离：** 宿主机网络、设备挂载、`privileged=True` 和 Docker Socket 访问都会降低隔离强度，应根据威胁模型选择合适配置。

## 设计说明

`DockerSandbox` 实现了 Deep Agents 的 `BaseSandbox` 接口，提供命令执行、文件操作及相应的同步和异步方法。通过 Deep Agents 或 `FilesystemMiddleware` 接入时，面向 Agent 的文件与执行操作可以暴露为工具。

`upload_files()` 和 `download_files()` 主要供应用代码显式调用，而非由本项目直接暴露为 Agent 工具。MCP 适配层单独暴露上文列出的七个工具，不包含二进制文件上传与下载工具。

## API 参考

### `DockerSandbox` 参数

| 参数 | 默认值 | 说明 |
|---|---|---|
| `image` | `python:3.13-slim` | Docker 镜像 |
| `container_name` | 自动生成 | 容器名称 |
| `volumes` | `{}` | 宿主机与容器的目录挂载 |
| `working_dir` | `/workspace` | 容器内工作目录 |
| `auto_remove` | `True` | 关闭时删除容器（无论是否删除均会停止容器） |
| `execute_timeout` | `120` | 默认命令超时时间（秒） |
| `max_output_bytes` | `512000` | 命令输出字节上限 |
| `docker_client_kwargs` | `None` | 传给 `docker.from_env()` 的额外参数 |
| `network_mode` | `None` | 容器网络模式（省略时使用 Docker 默认值） |
| `dns` | `None` | 自定义 DNS 服务器 |
| `gpus` | `None` | `"all"` 或正整数 GPU 数量 |
| `container_kwargs` | `None` | 传给 `containers.run()` 的额外参数 |

### 主要方法

| 方法 | 说明 |
|---|---|
| `execute(command, *, timeout=None)` | 执行命令，返回 `ExecuteResponse` |
| `write(path, content)` | 创建或覆盖文本文件 |
| `read(path)` | 读取文件 |
| `ls(path)` | 列出目录 |
| `edit(path, old_string, new_string, replace_all=False)` | 替换文本 |
| `glob(pattern, path=None)` | 根据路径模式查找文件 |
| `grep(pattern, path=None, glob=None)` | 按字面文本搜索 |
| `upload_files(files)` | 上传 `(path, bytes)` 形式的二进制文件 |
| `download_files(paths)` | 按路径下载文件 |
| `close()` | 停止容器、按配置删除容器并关闭 Docker 客户端 |

`ExecuteResponse` 包含 `output`（合并的 stdout/stderr）、`exit_code` 和 `truncated`（是否发生输出截断）。
