# OpenHands + GAIA + 本地 vLLM

这是一个薄而完整的运行仓：它不复制或修改 GAIA Agent，而是固定并调用官方
`OpenHands/benchmarks`，同时提供本地 vLLM 配置、环境检查、Docker Workspace、
并发执行、断点续跑、官方评分和简洁报告。

## 架构

```text
GAIA runner → OpenHands Agent → 本地 vLLM（OpenAI-compatible）
                    ├→ Tavily MCP / fetch
                    └→ 每题独立 Docker Workspace（Terminal/File/Browser）
```

默认不需要 Kubernetes。官方 runner 会为每个任务创建隔离的本地 Docker
Workspace。大规模运行时可把 `gaia.workspace` 改为 `remote`，并配置 OpenHands
Runtime API。

## 前置条件

- Linux 或 WSL2（推荐）；Windows 需要 Docker Desktop 和可用的 Linux 容器。
- Python 3.11+ 用于本包装器；官方 benchmark 由 `uv` 安装 Python 3.12 环境。
- `git`、`uv >= 0.8.13`、Docker。
- 已启动的 vLLM OpenAI-compatible server。
- GAIA Hugging Face 数据集访问权限及 `HF_TOKEN`。
- `TAVILY_API_KEY`（官方 GAIA runner 默认使用 Tavily MCP）。

推荐的 vLLM 启动方式：

```bash
vllm serve Qwen/Qwen3-32B \
  --host 0.0.0.0 --port 8000 \
  --served-model-name Qwen/Qwen3-32B \
  --enable-auto-tool-choice \
  --tool-call-parser hermes \
  --max-model-len 32768
```

`--tool-call-parser` 必须与你的模型模板匹配，例如 Qwen 系列常用 `hermes`；请以
当前 vLLM/model 文档为准。

## 快速开始

Linux 服务器首次部署和单样本跑通流程请参阅：
[Linux 上跑通第一个 OpenHands GAIA 测试](docs/FIRST_GAIA_RUN_ZH.md)。

```bash
cd openhands-gaia-vllm
cp config.example.toml config.toml
cp .env.example .env
# 编辑 config.toml 和 .env

./scripts/oh-gaia.sh setup
./scripts/oh-gaia.sh doctor
./scripts/oh-gaia.sh smoke
./scripts/oh-gaia.sh run
./scripts/oh-gaia.sh score
./scripts/oh-gaia.sh summary
```

PowerShell：

```powershell
Copy-Item config.example.toml config.toml
Copy-Item .env.example .env
.\scripts\oh-gaia.ps1 setup
.\scripts\oh-gaia.ps1 doctor
.\scripts\oh-gaia.ps1 smoke
```

也可直接使用：

```bash
uv run oh-gaia --config config.toml run --limit 10
```

## 网络配置：最容易踩坑的地方

包装器运行在宿主机，因此 `vllm.health_url` 通常是：

```toml
health_url = "http://127.0.0.1:8000/v1"
```

OpenHands Agent Server 位于 Docker 容器。容器中的 `127.0.0.1` 是容器本身，
因此 `vllm.base_url` 必须是容器可访问的地址：

```toml
base_url = "http://host.docker.internal:8000/v1"
```

Docker Desktop 通常直接支持该域名。Linux 若无法解析，可使用宿主机网桥 IP，或在
Docker daemon/运行配置中增加 `host.docker.internal:host-gateway`。同时确保 vLLM
监听 `0.0.0.0`，并仅在可信网络中开放端口。

## 配置建议

### 使用本地 GAIA 数据集

如果数据已经下载到本机，可在 `config.toml` 中设置数据集根目录：

```toml
[gaia]
dataset_path = "/home/l00948631/.cache/modelscope/datasets/gaia-benchmark-GAIA"
```

该目录必须包含 `2023/validation/metadata.jsonl` 或 `metadata.parquet`（运行 test
split 时，`2023/test/` 下也应包含其中一种格式）及对应附件。设置后 runner 会直接读取本地数据并跳过
Hugging Face 的 `load_dataset` 和 `snapshot_download`，因此不再需要 `HF_TOKEN`。

可先检查目录：

```bash
find /home/l00948631/.cache/modelscope/datasets/gaia-benchmark-GAIA \
  -maxdepth 3 -name metadata.jsonl -print
```

- 首次先运行 Level 1、`limit = 1`、`num_workers = 1`。
- 确认工具调用正确后逐步提高到 2、4、8 workers。
- `max_iterations = 30` 是合理起点；复杂任务可提高，但成本明显增加。
- 论文实验应把 `[upstream].revision` 改为实际 commit SHA，并记录 vLLM、模型和
  容器镜像版本。
- 多模态 GAIA 题目要求 vLLM 模型支持图片输入；纯文本模型无法公平完成这些题目。

重复执行同一命令和输出目录时，官方 runner 会自动跳过已完成实例，实现断点续跑。

## 输出

官方结果位于 `outputs/gaia/**/output.jsonl`，包含：

- 任务 ID、答案和 ground truth
- 正确性分数
- 完整 Agent 轨迹
- LLM/工具调用指标
- 错误信息

`summary` 会把最近一次运行汇总到 `reports/latest.json`。

## 测试

```bash
uv run --with pytest pytest
```

## 安全

GAIA 会让 Agent 执行模型生成的命令并访问互联网。不要把 Docker socket、宿主机
敏感目录或生产凭据挂进 Workspace。应使用单独测试机或受控网络运行大规模评测。
