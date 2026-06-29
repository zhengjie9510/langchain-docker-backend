# langchain-docker-backend

AI Agent 的 Docker 沙箱后端 — 在隔离容器中安全执行代码。

## 安装

```bash
pip install langchain-docker-backend
```

**前置条件：** 确保本机已安装并运行 Docker。以下默认镜像开箱即用，首次使用前拉取：

```bash
docker pull ghcr.io/astral-sh/uv:python3.13-bookworm-slim
```

> **💡 任意 Docker 镜像均可使用。** `ghcr.io/astral-sh/uv:python3.13-bookworm-slim` 只是默认值。你可以用任何镜像 —— `python:3.13-slim`、`ubuntu:22.04`、`node:20`，或者你自己的定制镜像。通过 `image=` 参数传入即可，自由匹配你的运行时需求。

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

### deepagents

将 `DockerSandbox` 接入 deep agent，agent 即获得全套沙箱工具，在隔离容器中执行代码：

```python
from deepagents import create_deep_agent
from langchain_anthropic import ChatAnthropic
from langchain_docker_backend import DockerSandbox

sandbox = DockerSandbox()

try:
    agent = create_deep_agent(
        model=ChatAnthropic(model="claude-sonnet-4-6"),
        system_prompt="你是一个有沙箱访问权限的编程助手。",
        backend=sandbox,
    )
    result = agent.invoke({
        "messages": [{"role": "user", "content": "写一个 fizzbuzz 脚本并运行"}]
    })
    print(result)
finally:
    sandbox.close()
```

### LangChain

在 LangChain 中通过 `FilesystemMiddleware` 接入：

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
        "messages": [{"role": "user", "content": "写一个 fizzbuzz 脚本并运行"}]
    })
finally:
    sandbox.close()
```

### 基础用法

除了配合 agent 使用，也可以直接操作沙箱 — 执行命令、读写文件、列目录、编辑内容。

自由选择镜像以匹配你的技术栈：
```python
sandbox = DockerSandbox(image="python:3.13-slim")      # 纯净 Python
sandbox = DockerSandbox(image="node:20")                # Node.js
sandbox = DockerSandbox(image="ubuntu:22.04")           # Ubuntu
sandbox = DockerSandbox()                               # 默认（uv + Python 3.13）
```

```python
from langchain_docker_backend import DockerSandbox

sandbox = DockerSandbox()

try:
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
finally:
    sandbox.close()
```

## 设计说明

`DockerSandbox` 实现了 `BaseSandbox`，后者定义了一整套沙箱操作（同步 + 异步），包括 `execute`、文件读写、目录列表、glob、grep 等。

当接入 `FilesystemMiddleware` 或 `create_deep_agent(backend=...)` 后，大部分操作会暴露为工具，由 **Agent 模型自主决定**何时调用：模型自行判断需要 `ls` 列目录、`read_file` 读文件、`write_file` 写文件、`execute` 执行命令等。

例外是 `upload_files` 和 `download_files`，它们**不暴露给模型**，必须由**开发者在代码中显式调用** — 什么数据进入沙箱、什么结果需要提取，由开发者控制，而非模型自行决定。

## API 参考

### `DockerSandbox`

| 参数 | 类型 | 默认值 | 说明 |
|-----------|------|---------|------|
| `image` | `str` | `ghcr.io/astral-sh/uv:python3.13-bookworm-slim` | 任意 Docker 镜像（公开、私有或定制） |
| `container_name` | `str \| None` | 自动生成 | 容器名称 |
| `volumes` | `dict` | `{}` | 目录挂载 |
| `working_dir` | `str` | `/workspace` | 容器内工作目录 |
| `auto_remove` | `bool` | `True` | 关闭时是否删除容器 |
| `execute_timeout` | `int` | `120` | 默认超时时间（秒） |
| `max_output_bytes` | `int` | `512000` | 输出截断上限（字节） |
| `docker_client_kwargs` | `dict \| None` | `None` | `docker.from_env()` 的额外参数（如 `base_url`、`tls`） |

### 主要方法

| 方法 | 说明 |
|--------|------|
| `execute(command, *, timeout)` | 执行 Shell 命令 |
| `write(path, content)` | 写入文本文件 |
| `read(path)` | 读取文本文件 |
| `ls(path)` | 列出目录内容 |
| `edit(path, find, replace)` | 查找替换文件内容 |
| `upload_files(files)` | 上传二进制文件（tar 方式） |
| `download_files(paths)` | 下载二进制文件（tar 方式） |
| `close()` | 停止并可选删除容器 |

### `ExecuteResponse`

| 字段 | 类型 | 说明 |
|-------|------|------|
| `output` | `str` | 合并的 stdout + stderr |
| `exit_code` | `int` | 命令退出码 |
| `truncated` | `bool` | 输出是否被截断 |
