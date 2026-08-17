# Linux 上跑通第一个 OpenHands GAIA 测试

本文说明如何在 Linux 服务器上使用本仓库、本地 GAIA 数据集和本地 vLLM 服务，运行第一个 GAIA Level 1 样本。

## 1. 获取代码

首次下载：

```bash
cd /home/l00948631
git clone https://github.com/fly-orange/agent-profile.git
cd agent-profile
```

如果代码仓已经存在：

```bash
cd /home/l00948631/agent-profile
git switch main
git pull origin main
```

## 2. 检查基础环境

需要安装 Git、Docker、curl 和 `uv`：

```bash
git --version
docker --version
docker info
curl --version
uv --version
```

如果没有安装 `uv`：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc
uv --version
```

如果当前用户无权运行 Docker：

```bash
sudo usermod -aG docker "$USER"
```

执行后退出 SSH 并重新登录，再运行：

```bash
docker info
```

## 3. 检查本地 GAIA 数据集

当前数据集路径为：

```text
/home/l00948631/.cache/modelscope/datasets/gaia-benchmark-GAIA
```

检查元数据文件：

```bash
find /home/l00948631/.cache/modelscope/datasets/gaia-benchmark-GAIA \
  -maxdepth 4 \( -name metadata.jsonl -o -name metadata.parquet \) -print
```

至少应当存在以下文件之一：

```text
/home/l00948631/.cache/modelscope/datasets/gaia-benchmark-GAIA/2023/validation/metadata.jsonl
/home/l00948631/.cache/modelscope/datasets/gaia-benchmark-GAIA/2023/validation/metadata.parquet
```

检查验证集中的附件：

```bash
ls -lah \
  /home/l00948631/.cache/modelscope/datasets/gaia-benchmark-GAIA/2023/validation \
  | head -20
```

如果 `metadata.jsonl` 位于更深一层，后续的 `dataset_path` 应指向直接包含 `2023` 目录的那一级。

预期目录结构如下：

```text
gaia-benchmark-GAIA/
└── 2023/
    ├── validation/
    │   ├── metadata.jsonl 或 metadata.parquet
    │   └── 题目附件
    └── test/
        ├── metadata.jsonl 或 metadata.parquet
        └── 题目附件
```

## 4. 创建运行配置

```bash
cd /home/l00948631/agent-profile
cp config.example.toml config.toml
cp .env.example .env
chmod +x scripts/oh-gaia.sh
```

编辑配置：

```bash
vim config.toml
```

首次测试建议使用一个样本和一个 worker：

```toml
[vllm]
# 控制进程访问 vLLM 时使用的地址。
health_url = "http://127.0.0.1:8000/v1"
# OpenHands Docker Workspace 访问宿主机 vLLM 时使用的地址。
base_url = "http://172.17.0.1:8000/v1"
model = "Qwen/Qwen3-32B"
api_key_env = "VLLM_API_KEY"
temperature = 0.0
max_output_tokens = 8192
timeout_seconds = 600

[gaia]
dataset_path = "/home/l00948631/.cache/modelscope/datasets/gaia-benchmark-GAIA"
level = "2023_level1"
split = "validation"
max_iterations = 30
num_workers = 1
limit = 1
critic = "pass"
workspace = "docker"
tool_preset = "default"
output_dir = "outputs/gaia"
note = "first-smoke-test"
enable_condenser = true

[upstream]
repository = "https://github.com/OpenHands/benchmarks.git"
revision = "main"
directory = ".upstream/openhands-benchmarks"
```

`model` 必须与 vLLM `/v1/models` 返回的模型 ID 完全一致。`base_url` 中的 Docker 网桥地址需要根据第 7 节的检查结果调整。

## 5. 配置环境变量

编辑 `.env`：

```bash
vim .env
```

填写：

```dotenv
VLLM_API_KEY=local-vllm
TAVILY_API_KEY=你的_Tavily_API_Key
```

使用本地 GAIA 数据集后不需要 `HF_TOKEN`。但是官方 OpenHands GAIA runner 使用 Tavily 执行联网搜索，因此仍然需要 `TAVILY_API_KEY`。

不要将包含真实密钥的 `.env` 提交到 Git。

## 6. 启动 vLLM

如果 vLLM 尚未启动，以 Qwen3 为例：

```bash
vllm serve Qwen/Qwen3-32B \
  --host 0.0.0.0 \
  --port 8000 \
  --served-model-name Qwen/Qwen3-32B \
  --enable-auto-tool-choice \
  --tool-call-parser hermes \
  --max-model-len 32768
```

工具调用解析器必须与实际模型匹配。其他模型可能需要不同的 `--tool-call-parser`。

在另一个终端检查 vLLM：

```bash
curl http://127.0.0.1:8000/v1/models
```

确认响应中存在配置使用的模型 ID，例如：

```json
{
  "data": [
    {
      "id": "Qwen/Qwen3-32B"
    }
  ]
}
```

## 7. 检查 Docker 到 vLLM 的网络

OpenHands Agent 在 Docker Workspace 中运行。容器里的 `127.0.0.1` 指向容器本身，不能用它访问宿主机上的 vLLM。

查询 Docker 默认网桥地址：

```bash
docker network inspect bridge \
  --format '{{(index .IPAM.Config 0).Gateway}}'
```

常见结果为：

```text
172.17.0.1
```

从临时容器测试 vLLM：

```bash
docker run --rm curlimages/curl:latest \
  http://172.17.0.1:8000/v1/models
```

如果 Docker 网桥地址不是 `172.17.0.1`，将测试命令和 `config.toml` 中的 `vllm.base_url` 改成实际地址：

```toml
base_url = "http://实际网桥地址:8000/v1"
```

宿主机健康检查地址仍然保持：

```toml
health_url = "http://127.0.0.1:8000/v1"
```

如果容器无法访问，请确认 vLLM 使用 `--host 0.0.0.0` 启动，并检查防火墙规则。

## 8. 安装 OpenHands benchmark

首次运行：

```bash
cd /home/l00948631/agent-profile
./scripts/oh-gaia.sh setup
```

该命令会：

- 克隆官方 `OpenHands/benchmarks`；
- 初始化 OpenHands SDK 子模块；
- 使用 `uv` 创建环境并安装依赖。

首次安装需要下载依赖，耗时会明显长于后续运行。

## 9. 执行环境检查

```bash
./scripts/oh-gaia.sh doctor
```

正常情况下会看到类似输出：

```text
vLLM OK: ['Qwen/Qwen3-32B']
Local GAIA dataset OK: /home/l00948631/.cache/modelscope/datasets/gaia-benchmark-GAIA
Environment checks passed.
```

如果检查失败，重点排查：

- Docker daemon 是否运行且当前用户有权限；
- vLLM 是否正在监听 `0.0.0.0:8000`；
- `config.toml` 中的模型名称是否与 `/v1/models` 一致；
- 本地数据集路径下是否存在对应 split 的 `metadata.jsonl`；
- `.env` 中是否设置了 `TAVILY_API_KEY`。

## 10. 运行第一个 GAIA 样本

```bash
./scripts/oh-gaia.sh smoke
```

`smoke` 默认只运行一个实例。第一次执行可能需要构建或拉取 OpenHands Workspace 镜像，因此启动时间可能较长。

查找结果文件：

```bash
find outputs/gaia -name output.jsonl -print
```

查看最新结果文件的最后一条记录：

```bash
find outputs/gaia -name output.jsonl -print0 \
  | xargs -0 ls -t \
  | head -1 \
  | xargs tail -1
```

生成简要报告：

```bash
./scripts/oh-gaia.sh summary
```

执行官方评分：

```bash
./scripts/oh-gaia.sh score
```

## 11. 扩展到多个样本和并发测试

第一个样本成功后，可编辑 `config.toml`：

```toml
[gaia]
limit = 10
num_workers = 1
note = "level1-10-workers1"
```

运行：

```bash
./scripts/oh-gaia.sh run
```

确认串行运行稳定后，再逐步提高并发：

```toml
[gaia]
limit = 20
num_workers = 2
note = "level1-20-workers2"
```

每个 worker 可能同时使用一个 OpenHands Workspace 容器、一个活跃的 vLLM 请求序列，以及浏览器、Python、ffmpeg 等工具进程。建议按照 `1 → 2 → 4 → 8` 的顺序逐步增加并发并记录资源指标。

## 12. 推荐的首次运行命令

```bash
cd /home/l00948631/agent-profile
./scripts/oh-gaia.sh setup
./scripts/oh-gaia.sh doctor
./scripts/oh-gaia.sh smoke
./scripts/oh-gaia.sh summary
```

## 13. 故障诊断信息

如果 `doctor` 或 `smoke` 失败，请保存完整错误日志，并收集以下输出：

```bash
find /home/l00948631/.cache/modelscope/datasets/gaia-benchmark-GAIA \
  -maxdepth 4 \( -name metadata.jsonl -o -name metadata.parquet \) -print

curl http://127.0.0.1:8000/v1/models

docker network inspect bridge \
  --format '{{(index .IPAM.Config 0).Gateway}}'
```

同时测试容器到 vLLM 的连通性：

```bash
VLLM_DOCKER_HOST=$(docker network inspect bridge \
  --format '{{(index .IPAM.Config 0).Gateway}}')

docker run --rm curlimages/curl:latest \
  "http://${VLLM_DOCKER_HOST}:8000/v1/models"
```
