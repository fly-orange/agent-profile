from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Mapping, Sequence


def run(
    args: Sequence[str],
    *,
    cwd: Path | None = None,
    env: Mapping[str, str] | None = None,
    capture: bool = False,
) -> subprocess.CompletedProcess[str]:
    printable = subprocess.list2cmdline(list(args))
    print(f"+ {printable}", flush=True)
    return subprocess.run(
        list(args),
        cwd=cwd,
        env=dict(env) if env else None,
        check=True,
        text=True,
        capture_output=capture,
    )

