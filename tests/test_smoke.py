import json
import os
import subprocess
import sys
import tempfile
import unittest

import backup_verify

from .helpers import FIXTURE_CONFIG

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run(*argv):
    return subprocess.run([sys.executable, "-B", "-m", "backup_verify", *argv], cwd=ROOT,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)


class ModuleEntryPointTest(unittest.TestCase):
    def test_help(self):
        result = run("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("Exit codes:", result.stdout)

    def test_version(self):
        result = run("--version")
        self.assertEqual(result.returncode, 0)
        self.assertIn(backup_verify.__version__, result.stdout)

    def test_usage_error_exit_code(self):
        self.assertEqual(run("--no-such-option").returncode, 3)

    def test_history_file_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            policy = os.path.join(tmp, "policy.json")
            with open(policy, "w", encoding="utf-8") as fh:
                json.dump(FIXTURE_CONFIG, fh)
            fixture = os.path.join(ROOT, "tests", "fixtures", "stale.json")
            result = run("--history-file", fixture, "--config", policy, "--format", "json")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(json.loads(result.stdout)["summary"]["critical"], 2)
