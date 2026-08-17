import os
import tempfile
import unittest
from pathlib import Path

from oh_gaia.config import load_config
from oh_gaia.runner import (
    build_infer_command,
    summarize,
    validate_local_dataset,
    write_llm_config,
)


CONFIG = """
[vllm]
health_url = "http://127.0.0.1:8000/v1"
base_url = "http://host.docker.internal:8000/v1"
model = "local-model"

[gaia]
dataset_path = ""
level = "2023_level1"
split = "validation"
max_iterations = 20
num_workers = 2
limit = 3
critic = "pass"
workspace = "docker"
tool_preset = "default"
output_dir = "outputs/gaia"
note = "test"
enable_condenser = true

[upstream]
repository = "https://example.invalid/benchmarks.git"
revision = "deadbeef"
directory = ".upstream/benchmarks"
"""


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "config.toml").write_text(CONFIG, encoding="utf-8")
        self.config = load_config(self.root / "config.toml")

    def tearDown(self):
        self.tmp.cleanup()

    def test_generated_config_uses_openai_provider(self):
        os.environ["VLLM_API_KEY"] = "secret"
        payload = write_llm_config(self.config).read_text(encoding="utf-8")
        self.assertIn('"model": "openai/local-model"', payload)
        self.assertIn('"api_key": "secret"', payload)

    def test_command_contains_core_options(self):
        command = build_infer_command(self.config, limit=1)
        self.assertTrue(command[3].endswith("gaia_entrypoint.py"))
        self.assertEqual(command[command.index("--n-limit") + 1], "1")
        self.assertEqual(command[command.index("--num-workers") + 1], "2")

    def test_local_dataset_path_is_resolved(self):
        text = CONFIG.replace('dataset_path = ""', 'dataset_path = "data/GAIA"')
        (self.root / "config.toml").write_text(text, encoding="utf-8")
        config = load_config(self.root / "config.toml")
        self.assertEqual(config.dataset_path, (self.root / "data" / "GAIA").resolve())

    def test_local_parquet_metadata_is_accepted(self):
        text = CONFIG.replace('dataset_path = ""', 'dataset_path = "data/GAIA"')
        (self.root / "config.toml").write_text(text, encoding="utf-8")
        metadata = self.root / "data" / "GAIA" / "2023" / "validation" / "metadata.parquet"
        metadata.parent.mkdir(parents=True)
        metadata.touch()
        validate_local_dataset(load_config(self.root / "config.toml"))

    def test_summary(self):
        out = self.config.output_dir / "run" / "output.jsonl"
        out.parent.mkdir(parents=True)
        out.write_text(
            '{"test_result":{"score":true},"error":null}\n'
            '{"test_result":{"score":false},"error":"boom"}\n',
            encoding="utf-8",
        )
        report = summarize(self.config, out)
        self.assertEqual(report["completed"], 2)
        self.assertEqual(report["passed"], 1)
        self.assertEqual(report["accuracy"], 0.5)


if __name__ == "__main__":
    unittest.main()
