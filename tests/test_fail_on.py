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
