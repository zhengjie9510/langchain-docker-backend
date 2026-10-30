# langchain-docker-backend

AI Agent 的 Docker 沙箱后端 — 在隔离容器中安全执行代码。

## 安装

```bash
pip install langchain-docker-backend
```

**前置条件：** 确保本机已安装并运行 Docker。以下默认镜像开箱即用，首次使用前拉取：

```bash
docker pull python:3.13-slim
```

> **💡 任意 Docker 镜像均可使用。** `python:3.13-slim` 只是默认值。你可以用任何镜像 —— `ghcr.io/astral-sh/uv:python3.13-bookworm-slim`、`ubuntu:22.04`、`node:20`，或者你自己的定制镜像。通过 `image=` 参数传入即可，自由匹配你的运行时需求。

## Docker 连接方式

`DockerSandbox` 通过 `docker.from_env()` 连接 Docker。默认读取 `DOCKER_HOST` 环境变量，未设置时回退到本地 Unix Socket（`/var/run/docker.sock`）。

### 宿主机 Docker（默认）

最常见的方式 — 代码运行在宿主机上，连接本地 Docker daemon，无需额外配置：

```python
sandbox = DockerSandbox()  # 连接 /var/run/docker.sock
```

### Docker-in-Docker

当代码本身运行在容器内部时，有两种方式：

**方式一 — Socket 挂载（Docker outside of Docker）**

将宿主机的 Docker Socket 挂载进容器，共享宿主机的 Docker daemon，更简单轻量：

```bash
docker run -v /var/run/docker.sock:/var/run/docker.sock your-image
```

```python
# 容器内使用方式完全相同
sandbox = DockerSandbox()
```

> **注意：** 这会让容器获得宿主机 Docker daemon 的访问权限，请确保安全影响在可接受范围内。

**方式二 — 真正的 Docker-in-Docker（DinD）**

使用 `docker:dind` 镜像，在容器内部运行独立的 Docker daemon，与宿主机完全隔离，但需要 `--privileged`：

```bash
docker run --privileged docker:dind
```

```python
# 在 DinD 容器内，连接内部 daemon
sandbox = DockerSandbox(
    docker_client_kwargs={"base_url": "unix:///var/run/docker.sock"}
)
```

> **注意：** `--privileged` 会赋予容器扩展的 Linux 能力。除非需要内外 Docker daemon 完全隔离，否则优先使用 Socket 挂载方式。

### 远程 Docker

通过 TCP 连接另一台机器上的 Docker daemon。

**方式一：环境变量**（推荐）

```bash
export DOCKER_HOST=tcp://192.168.1.100:2375
```

```python
sandbox = DockerSandbox()  # 自动读取 DOCKER_HOST
```

**方式二：通过 `docker_client_kwargs` 显式指定**

```python
sandbox = DockerSandbox(
    docker_client_kwargs={"base_url": "tcp://192.168.1.100:2375"}
)
```

**启用 TLS：**

```python
import docker.tls

sandbox = DockerSandbox(
    docker_client_kwargs={
        "base_url": "tcp://192.168.1.100:2376",
        "tls": docker.tls.TLSConfig(
            ca_cert="/path/to/ca.pem",
            client_cert=("/path/to/cert.pem", "/path/to/key.pem"),
        ),
    }
)
```

## 使用教程

### 作为 MCP 服务使用

安装可选依赖后，可以在自己的脚本中配置沙箱，并一次性暴露 `ls`、`read`、`write`、`edit`、`glob`、`grep` 和 `execute` 工具：

```bash
pip install 'langchain-docker-backend[mcp]'
```

```python
from langchain_docker_backend import DockerSandbox
from langchain_docker_backend.mcp import create_mcp_server


def main():
    with DockerSandbox(working_dir="/workspace/project") as sandbox:
        create_mcp_server(sandbox).run(transport="streamable-http")


if __name__ == "__main__":
    main()
```

默认 MCP 地址为 `http://127.0.0.1:8000/mcp`。Dify 需要能够从其运行环境访问该地址；若运行在不同容器或主机上，需配置可达的监听地址和网络连接。一个服务实例使用一个沙箱，所有调用共享其中的文件；多用户场景需要另行做隔离。`grep` 的 `pattern` 是字面字符串，不是正则表达式。示例脚本见 [`examples/mcp_server_example.py`](examples/mcp_server_example.py)。

### deepagents

将 `DockerSandbox` 接入 deep agent，agent 即获得全套沙箱工具，在隔离容器中执行代码：

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

在 LangChain 中通过 `FilesystemMiddleware` 接入：

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
```

### 基础用法

除了配合 agent 使用，也可以直接操作沙箱 — 执行命令、读写文件、列目录、编辑内容。

自由选择镜像以匹配你的技术栈：
```python
sandbox = DockerSandbox()                               # 默认（Python 3.13）
sandbox = DockerSandbox(image="node:20")                # Node.js
sandbox = DockerSandbox(image="ubuntu:22.04")           # Ubuntu
```

```python
from langchain_docker_backend import DockerSandbox

with DockerSandbox() as sandbox:
    # 执行命令
    result = sandbox.execute("echo 'Hello from Docker!'")
    print(result.output)      # Hello from Docker!
    print(result.exit_code)   # 0

    # 写入文件
    sandbox.write("/workspace/test.txt", "Hello, World!")

    # 读取文件
    file = sandbox.read("/workspace/test.txt")
    print(file.file_data["content"])  # Hello, World!

    # 列出目录
    ls = sandbox.ls("/workspace")
    for entry in ls.entries:
        print(entry["path"], entry.get("is_dir", False))

    # 查找替换
    sandbox.edit("/workspace/test.txt", "Hello", "你好")

    # 上传 / 下载二进制文件
    sandbox.upload_files([("data.bin", b"\x00\x01\x02")])
    files = sandbox.download_files(["data.bin"])
    print(files[0].content)  # b'\x00\x01\x02'

    # 命令超时
    result = sandbox.execute("sleep 10", timeout=2)
    print(result.exit_code)   # 124
```

### 网络与硬件配置

网络、DNS、GPU 及资源限制在创建容器时生效：

```python
from langchain_docker_backend import DockerSandbox

with DockerSandbox(
    network_mode="host",          # "bridge"（Docker 默认）、"host"、"none"、"container:<id>"
    dns=["1.1.1.1", "8.8.8.8"],   # 自定义 DNS 服务器
    gpus="all",                   # "all" 或 GPU 数量
    container_kwargs={            # docker-py containers.run() 的其他任意参数
        "mem_limit": "4g",
        "nano_cpus": 2_000_000_000,               # 2 个 CPU
        "shm_size": "2g",
        "devices": ["/dev/accel0:/dev/accel0"],   # 透传宿主机设备
    },
) as sandbox:
    sandbox.execute("pip install requests")
```

- **沙箱内无法联网？** 使用 Docker 默认 `bridge` 网络的容器本身即可访问外网。若安装依赖或发起网络请求失败，通常是 DNS 问题（例如宿主机使用 `127.0.0.53`，而所在网络屏蔽了 Docker 回退使用的 `8.8.8.8`）——优先设置 `dns=[...]` 为当前网络可访问的 DNS，再考虑 `network_mode="host"`。
- **GPU** 需要宿主机安装 [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)。其他加速器（NPU、TPU 等）可通过 `container_kwargs={"devices": [...]}` 或 `{"device_requests": [...]}` 暴露。
- **隔离性：** `network_mode="host"`、宿主机 `devices` 以及 `container_kwargs={"privileged": True}` 都会削弱沙箱隔离。需要完全离线的 Agent 请使用 `network_mode="none"`。

## 设计说明

`DockerSandbox` 实现了 `BaseSandbox`，后者定义了一整套沙箱操作（同步 + 异步），包括 `execute`、文件读写、目录列表、glob、grep 等。

当接入 `FilesystemMiddleware` 或 `create_deep_agent(backend=...)` 后，大部分操作会暴露为工具，由 **Agent 模型自主决定**何时调用：模型自行判断需要 `ls` 列目录、`read_file` 读文件、`write_file` 写文件、`execute` 执行命令等。

例外是 `upload_files` 和 `download_files`，它们**不暴露给模型**，必须由**开发者在代码中显式调用** — 什么数据进入沙箱、什么结果需要提取，由开发者控制，而非模型自行决定。

## API 参考

### `DockerSandbox`

| 参数 | 类型 | 默认值 | 说明 |
|-----------|------|---------|------|
| `image` | `str` | `python:3.13-slim` | 任意 Docker 镜像（公开、私有或定制） |
| `container_name` | `str \| None` | 自动生成 | 容器名称 |
| `volumes` | `dict` | `{}` | 目录挂载 |
| `working_dir` | `str` | `/workspace` | 容器内工作目录 |
| `auto_remove` | `bool` | `True` | 关闭时是否删除容器 |
| `execute_timeout` | `int` | `120` | 默认超时时间（秒） |
| `max_output_bytes` | `int` | `512000` | 输出截断上限（字节） |
| `docker_client_kwargs` | `dict \| None` | `None` | `docker.from_env()` 的额外参数（如 `base_url`、`tls`） |
| `network_mode` | `str \| None` | `None`（Docker 默认 `bridge`） | 容器网络模式：`"bridge"`、`"host"`、`"none"`、`"container:<id>"` |
| `dns` | `list[str] \| None` | `None` | 自定义 DNS 服务器 |
| `gpus` | `int \| str \| None` | `None` | 暴露给容器的 GPU：`"all"` 或正整数（需 NVIDIA Container Toolkit） |
| `container_kwargs` | `dict \| None` | `None` | `client.containers.run()` 的额外参数（如 `mem_limit`、`nano_cpus`、`devices`、`shm_size`） |

### 主要方法

| 方法 | 说明 |
|--------|------|
| `execute(command, *, timeout)` | 执行 Shell 命令 |
| `write(path, content)` | 创建文本文件；已存在则报错 |
| `read(path)` | 读取文件 |
| `ls(path)` | 列出目录内容 |
| `edit(path, old_string, new_string)` | 精确替换文件内容 |
| `glob(pattern, path)` | 按路径模式查找文件 |
| `grep(pattern, path, glob)` | 按字面文本检索文件内容 |
| `upload_files(files)` | 上传二进制文件（tar 方式） |
| `download_files(paths)` | 下载二进制文件（tar 方式） |
| `close()` | 停止并可选删除容器 |

### `ExecuteResponse`

| 字段 | 类型 | 说明 |
|-------|------|------|
| `output` | `str` | 合并的 stdout + stderr |
| `exit_code` | `int` | 命令退出码 |
| `truncated` | `bool` | 输出是否被截断 |
