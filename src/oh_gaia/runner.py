from __future__ import annotations

import json
import os
import shutil
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .config import AppConfig
from .process import run


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def require_command(name: str) -> None:
    if shutil.which(name) is None:
        raise RuntimeError(f"Required command not found: {name}")


def setup_upstream(config: AppConfig) -> None:
    require_command("git")
    require_command("uv")
    target = config.upstream_dir
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        run(["git", "clone", "--recurse-submodules", config.upstream.repository, str(target)])
    run(["git", "fetch", "--tags", "origin"], cwd=target)
    run(["git", "checkout", config.upstream.revision], cwd=target)
    run(["git", "submodule", "update", "--init", "--recursive"], cwd=target)
    run(["uv", "sync", "--dev"], cwd=target)


def write_llm_config(config: AppConfig) -> Path:
    path = config.llm_config_path
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "model": f"openai/{config.vllm.model}",
        "base_url": config.vllm.base_url.rstrip("/"),
        "api_key": config.vllm.api_key,
        "temperature": config.vllm.temperature,
        "max_output_tokens": config.vllm.max_output_tokens,
        "timeout": config.vllm.timeout_seconds,
        "num_retries": 3,
        "drop_params": True,
        "modify_params": True,
        "native_tool_calling": True,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def check_vllm(config: AppConfig) -> dict[str, Any]:
    url = f"{config.vllm.health_url.rstrip('/')}/models"
    request = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {config.vllm.api_key}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.load(response)
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"Cannot reach vLLM at {url}: {exc}") from exc
    models = [item.get("id") for item in payload.get("data", [])]
    if config.vllm.model not in models:
        print(f"WARNING: configured model {config.vllm.model!r} not in /models: {models}")
    return payload


def doctor(config: AppConfig) -> None:
    for command in ("git", "uv", "docker"):
        require_command(command)
    run(["docker", "info"], capture=True)
    payload = check_vllm(config)
    print(f"vLLM OK: {[item.get('id') for item in payload.get('data', [])]}")
    if config.dataset_path:
        validate_local_dataset(config)
        print(f"Local GAIA dataset OK: {config.dataset_path}")
    elif not os.getenv("HF_TOKEN"):
        print("WARNING: HF_TOKEN is missing; GAIA download may fail.")
    if not os.getenv("TAVILY_API_KEY"):
        print("WARNING: TAVILY_API_KEY is missing; official GAIA runner will fail.")
    print("Environment checks passed.")


def validate_local_dataset(config: AppConfig) -> None:
    root = config.dataset_path
    if root is None:
        return
    split_dir = root / "2023" / config.gaia.split
    candidates = (split_dir / "metadata.jsonl", split_dir / "metadata.parquet")
    if not any(path.is_file() for path in candidates):
        raise RuntimeError(
            f"Local GAIA metadata not found below: {split_dir}. "
            "Expected metadata.jsonl or metadata.parquet."
        )


def build_infer_command(config: AppConfig, *, limit: int | None = None) -> list[str]:
    gaia = config.gaia
    llm_path = write_llm_config(config)
    command = [
        "uv", "run", "python", str((config.root / "src" / "oh_gaia" / "gaia_entrypoint.py").resolve()),
        str(llm_path), "--level", gaia.level, "--split", gaia.split,
        "--max-iterations", str(gaia.max_iterations), "--critic", gaia.critic,
        "--output-dir", str(config.output_dir), "--num-workers", str(gaia.num_workers),
        "--workspace", gaia.workspace, "--tool-preset", gaia.tool_preset,
        "--note", gaia.note,
    ]
    effective_limit = gaia.limit if limit is None else limit
    if effective_limit > 0:
        command.extend(["--n-limit", str(effective_limit)])
    command.append("--enable-condenser" if gaia.enable_condenser else "--disable-condenser")
    return command


def run_gaia(config: AppConfig, *, limit: int | None = None) -> None:
    if not config.upstream_dir.exists():
        raise RuntimeError("Upstream repository is missing. Run: oh-gaia setup")
    write_llm_config(config)
    env = os.environ.copy()
    env.setdefault("RICH_LOGGING", "1")
    env.setdefault("HF_TOKEN", os.getenv("HF_TOKEN", ""))
    if config.dataset_path:
        validate_local_dataset(config)
        env["OH_GAIA_DATASET_PATH"] = str(config.dataset_path)
    run(build_infer_command(config, limit=limit), cwd=config.upstream_dir, env=env)


def find_outputs(config: AppConfig) -> list[Path]:
    if not config.output_dir.exists():
        return []
    return sorted(config.output_dir.rglob("output.jsonl"), key=lambda p: p.stat().st_mtime)


def score(config: AppConfig, output: Path | None = None) -> None:
    candidates = find_outputs(config)
    selected = output.resolve() if output else (candidates[-1] if candidates else None)
    if selected is None or not selected.exists():
        raise RuntimeError("No output.jsonl found. Run an evaluation first or pass --output.")
    run(
        ["uv", "run", "python", "-m", "benchmarks.gaia.get_score", "--file", str(selected)],
        cwd=config.upstream_dir,
    )


def summarize(config: AppConfig, output: Path | None = None) -> dict[str, Any]:
    candidates = find_outputs(config)
    selected = output.resolve() if output else (candidates[-1] if candidates else None)
    if selected is None or not selected.exists():
        raise RuntimeError("No output.jsonl found.")
    rows = []
    for line_no, line in enumerate(selected.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid JSONL at {selected}:{line_no}: {exc}") from exc
    passed = sum(bool(row.get("test_result", {}).get("score")) for row in rows)
    errors = sum(bool(row.get("error")) for row in rows)
    report = {
        "file": str(selected),
        "completed": len(rows),
        "passed": passed,
        "failed": len(rows) - passed,
        "errors": errors,
        "accuracy": passed / len(rows) if rows else 0.0,
    }
    report_dir = config.root / "reports"
    report_dir.mkdir(exist_ok=True)
    (report_dir / "latest.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return report
