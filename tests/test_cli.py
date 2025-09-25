import io
import json
import os
import tempfile
import unittest
from datetime import datetime

from backup_verify.cli import main

from .fakes import FakeConnection, connection_from_fixture
from .helpers import FIXTURE_CONFIG


class CliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.config = os.path.join(self.tmp.name, "policy.json")
        with open(self.config, "w", encoding="utf-8") as fh:
            json.dump(FIXTURE_CONFIG, fh)

    def run_cli(self, *argv, fixture="healthy", **kwargs):
        out = io.StringIO()
        code = main(["--server", "SQLPROD01", "--config", self.config, *argv],
                    connect=lambda args: connection_from_fixture(fixture),
                    stdout=out, **kwargs)
        return code, out.getvalue()

    def test_clean_run_exits_zero(self):
        code, out = self.run_cli()
        self.assertEqual(code, 0)
        self.assertIn("No problems found.", out)

    def test_critical_findings_exit_two(self):
        code, out = self.run_cli(fixture="stale")
        self.assertEqual(code, 2)
        self.assertIn("NO_FULL_BACKUP", out)

    def test_warnings_only_exit_one(self):
        cfg = dict(FIXTURE_CONFIG, databases={"Sales": {"full_max_age_hours": 6, "log_max_age_minutes": 90}})
        with open(self.config, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh)
        code, out = self.run_cli()
        self.assertEqual(code, 1)
        self.assertIn("FULL_STALE", out)

    def test_json_output_to_file(self):
        target = os.path.join(self.tmp.name, "report.json")
        code, out = self.run_cli("--format", "json", "--output", target)
        self.assertEqual(code, 0)
        self.assertEqual(out, "")
        with open(target, encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["summary"]["databases"], 3)

    def test_database_filter(self):
        code, out = self.run_cli("--database", "sales", fixture="stale")
        self.assertIn("1 database(s) checked", out)
        self.assertNotIn("NewDb", out)

    def test_unknown_database_is_an_error(self):
        code, out = self.run_cli("--database", "Nope")
        self.assertEqual(code, 3)

    def test_bad_config_is_an_error(self):
        with open(self.config, "w", encoding="utf-8") as fh:
            fh.write("[]")
        code, out = self.run_cli()
        self.assertEqual(code, 3)

    def test_connection_failure_is_an_error(self):
        def boom(args):
            raise OSError("login timeout")

        code = main(["--server", "SQLDR02"], connect=boom, stdout=io.StringIO())
        self.assertEqual(code, 3)

    def test_query_failure_is_an_error(self):
        code = main(["--server", "SQLDR02"], connect=lambda args: FakeConnection([]),
                    stdout=io.StringIO())
        self.assertEqual(code, 3)

    def test_usage_errors_do_not_collide_with_finding_exit_codes(self):
        with self.assertRaises(SystemExit) as ctx:
            main([])
        self.assertEqual(ctx.exception.code, 3)

    def test_help_exits_zero(self):
        with self.assertRaises(SystemExit) as ctx:
            main(["--help"])
        self.assertEqual(ctx.exception.code, 0)

    def test_history_window_is_measured_from_the_server_clock(self):
        conns = []

        def connect(args):
            conns.append(connection_from_fixture("healthy"))
            return conns[0]

        main(["--server", "SQLPROD01"], connect=connect, stdout=io.StringIO())
        params = [p for sql, p in conns[0].executed if "backupmediafamily" in sql]
        self.assertEqual(params, [(datetime(2023, 1, 25, 8, 0, 0),)])
