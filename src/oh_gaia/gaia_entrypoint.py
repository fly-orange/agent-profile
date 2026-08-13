"""Launch the official OpenHands GAIA runner with optional local data loading."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any


def _install_local_dataset_adapter(module: Any, dataset_root: Path) -> None:
    """Replace only the official runner's dataset/download bindings."""
    from datasets import Dataset

    def load_local_dataset(_name: str, level: str) -> dict[str, Any]:
        result: dict[str, Any] = {}
        wanted_level = None
        if level != "2023_all":
            try:
                wanted_level = int(level.rsplit("level", 1)[1])
            except (IndexError, ValueError) as exc:
                raise ValueError(f"Unsupported GAIA level: {level}") from exc

        for split in ("validation", "test"):
            metadata = dataset_root / "2023" / split / "metadata.jsonl"
            if not metadata.is_file():
                continue
            frame = module.pd.read_json(metadata, lines=True)
            if wanted_level is not None:
                level_values = frame["Level"].astype(str).str.extract(r"(\d+)", expand=False)
                frame = frame[level_values == str(wanted_level)]
            result[split] = Dataset.from_pandas(frame, preserve_index=False)
        if not result:
            raise FileNotFoundError(
                f"No metadata.jsonl found below {dataset_root / '2023'}"
            )
        return result

    module.DATASET_CACHE_DIR = dataset_root
    module.load_dataset = load_local_dataset
    module.huggingface_hub.snapshot_download = lambda *args, **kwargs: str(dataset_root)


def main() -> None:
    # The wrapper is outside the upstream checkout while the process cwd is the
    # checkout root. Make that relationship explicit for Python script mode.
    sys.path.insert(0, str(Path.cwd()))
    from benchmarks.gaia import run_infer

    local_path = os.getenv("OH_GAIA_DATASET_PATH")
    if local_path:
        _install_local_dataset_adapter(run_infer, Path(local_path).expanduser().resolve())
    run_infer.main()


if __name__ == "__main__":
    main()
