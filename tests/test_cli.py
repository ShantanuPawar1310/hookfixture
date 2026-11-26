import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CliTests(unittest.TestCase):
    def run_cli(self, *args):
        env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
        return subprocess.run([sys.executable, "-m", "hookfixture", *map(str, args)],
                              env=env, capture_output=True, text=True)

    def test_build_and_verify_as_separate_processes(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "scenario"
            result = self.run_cli("build", ROOT / "examples/invoice-events.json", "--out", output,
                                  "--copies", "3", "--order", "shuffle", "--seed", "42")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["duplicates"], 4)
            result = self.run_cli("verify", output / "manifest.json")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), {"valid": True, "deliveries": 6, "duplicates": 4, "unique_events": 2})

    def test_errors_have_nonzero_exit_and_no_traceback(self):
        result = self.run_cli("verify", "/missing/hookfixture/manifest.json")
        self.assertEqual(result.returncode, 2)
        self.assertIn("hookfixture:", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_version(self):
        result = self.run_cli("--version")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "hookfixture 0.1.0")
