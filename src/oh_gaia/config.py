from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class VLLMConfig:
    health_url: str
    base_url: str
    model: str
    api_key_env: str = "VLLM_API_KEY"
    temperature: float = 0.0
    max_output_tokens: int = 8192
    timeout_seconds: int = 600

    @property
    def api_key(self) -> str:
        return os.getenv(self.api_key_env, "local-vllm")


@dataclass(frozen=True)
class GaiaConfig:
    dataset_path: str = ""
    level: str = "2023_level1"
    split: str = "validation"
    max_iterations: int = 30
    num_workers: int = 1
    limit: int = 3
    critic: str = "pass"
    workspace: str = "docker"
    tool_preset: str = "default"
    output_dir: str = "outputs/gaia"
    note: str = "local-vllm"
    enable_condenser: bool = True
    select_file: str = ""


@dataclass(frozen=True)
class UpstreamConfig:
    repository: str = "https://github.com/OpenHands/benchmarks.git"
    revision: str = "main"
    directory: str = ".upstream/openhands-benchmarks"


@dataclass(frozen=True)
class AppConfig:
    root: Path
    vllm: VLLMConfig
    gaia: GaiaConfig
    upstream: UpstreamConfig

    @property
    def upstream_dir(self) -> Path:
        return (self.root / self.upstream.directory).resolve()

    @property
    def output_dir(self) -> Path:
        return (self.root / self.gaia.output_dir).resolve()

    @property
    def select_file(self) -> Path | None:
        if not self.gaia.select_file:
            return None
        path = Path(self.gaia.select_file).expanduser()
        return path.resolve() if path.is_absolute() else (self.root / path).resolve()

    @property
    def llm_config_path(self) -> Path:
        return self.root / ".generated" / "vllm.json"

    @property
    def dataset_path(self) -> Path | None:
        if not self.gaia.dataset_path:
            return None
        path = Path(self.gaia.dataset_path).expanduser()
        return path.resolve() if path.is_absolute() else (self.root / path).resolve()


def _construct(cls: type[Any], values: dict[str, Any]) -> Any:
    try:
        return cls(**values)
    except TypeError as exc:
        raise ValueError(f"Invalid configuration for [{cls.__name__}]: {exc}") from exc


def load_config(path: Path) -> AppConfig:
    path = path.resolve()
    with path.open("rb") as handle:
        raw = tomllib.load(handle)
    missing = [section for section in ("vllm", "gaia", "upstream") if section not in raw]
    if missing:
        raise ValueError(f"Missing configuration sections: {', '.join(missing)}")
    config = AppConfig(
        root=path.parent,
        vllm=_construct(VLLMConfig, raw["vllm"]),
        gaia=_construct(GaiaConfig, raw["gaia"]),
        upstream=_construct(UpstreamConfig, raw["upstream"]),
    )
    if config.gaia.workspace not in {"docker", "remote"}:
        raise ValueError("gaia.workspace must be 'docker' or 'remote'")
    if config.gaia.num_workers < 1 or config.gaia.max_iterations < 1:
        raise ValueError("num_workers and max_iterations must be positive")
    if config.select_file and not config.select_file.is_file():
        raise ValueError(f"GAIA select file not found: {config.select_file}")
    return config
