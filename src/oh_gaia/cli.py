from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import load_config
from .runner import doctor, load_dotenv, run_gaia, score, setup_upstream, summarize, write_llm_config


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Run OpenHands GAIA against local vLLM")
    root.add_argument("--config", type=Path, default=Path("config.toml"))
    sub = root.add_subparsers(dest="command", required=True)
    sub.add_parser("setup", help="Clone and install official OpenHands benchmarks")
    sub.add_parser("doctor", help="Check Docker, vLLM, and required credentials")
    sub.add_parser("config", help="Generate and print the OpenHands LLM config")
    smoke = sub.add_parser("smoke", help="Run one GAIA task")
    smoke.add_argument("--limit", type=int, default=1)
    run_cmd = sub.add_parser("run", help="Run/resume the configured evaluation")
    run_cmd.add_argument("--limit", type=int)
    score_cmd = sub.add_parser("score", help="Run official scoring for an output file")
    score_cmd.add_argument("--output", type=Path)
    summary_cmd = sub.add_parser("summary", help="Create a compact JSON summary")
    summary_cmd.add_argument("--output", type=Path)
    return root


def main() -> None:
    args = parser().parse_args()
    try:
        config = load_config(args.config)
        load_dotenv(config.root / ".env")
        if args.command == "setup":
            setup_upstream(config)
        elif args.command == "doctor":
            doctor(config)
        elif args.command == "config":
            print(write_llm_config(config).read_text(encoding="utf-8"))
        elif args.command == "smoke":
            run_gaia(config, limit=args.limit)
        elif args.command == "run":
            run_gaia(config, limit=args.limit)
        elif args.command == "score":
            score(config, args.output)
        elif args.command == "summary":
            summarize(config, args.output)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()

