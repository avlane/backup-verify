import io
import json
import os
import tempfile
import unittest

from backup_verify.cli import main

from .fakes import connection_from_fixture
from .helpers import FIXTURE_CONFIG


class FailOnTest(unittest.TestCase):
    def run_cli(self, *argv, fixture="stale", config=FIXTURE_CONFIG):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "policy.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(config, fh)
            return main(["--server", "SQLPROD01", "--config", path, *argv],
                        connect=lambda args: connection_from_fixture(fixture), stdout=io.StringIO())

    def test_default_fails_on_warnings(self):
        warn_only = dict(FIXTURE_CONFIG, databases={"Sales": {"full_max_age_hours": 6, "log_max_age_minutes": 90}})
        self.assertEqual(self.run_cli(fixture="healthy", config=warn_only), 1)

    def test_critical_threshold_ignores_warnings(self):
        warn_only = dict(FIXTURE_CONFIG, databases={"Sales": {"full_max_age_hours": 6, "log_max_age_minutes": 90}})
        self.assertEqual(self.run_cli("--fail-on", "critical", fixture="healthy", config=warn_only), 0)

    def test_critical_threshold_still_fails_on_critical(self):
        self.assertEqual(self.run_cli("--fail-on", "critical"), 2)

    def test_never_always_exits_zero(self):
        self.assertEqual(self.run_cli("--fail-on", "never"), 0)

    def test_errors_are_not_masked_by_never(self):
        code = main(["--server", "x", "--fail-on", "never"], connect=lambda a: 1 / 0, stdout=io.StringIO())
        self.assertEqual(code, 3)


class QuietTest(unittest.TestCase):
    def stdout_for(self, fixture, *argv):
        out = io.StringIO()
        main(["--server", "SQLPROD01", "--quiet", *argv],
             connect=lambda args: connection_from_fixture(fixture), stdout=out)
        return out.getvalue()

    def test_clean_run_prints_nothing(self):
        self.assertEqual(self.stdout_for("healthy", "--config", self.write_policy()), "")

    def test_findings_are_still_printed(self):
        self.assertIn("NO_FULL_BACKUP", self.stdout_for("stale", "--config", self.write_policy()))

    def write_policy(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = os.path.join(tmp.name, "policy.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(FIXTURE_CONFIG, fh)
        return path
