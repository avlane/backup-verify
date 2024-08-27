import io
import json
import os
import tempfile
import unittest

from backup_verify.cli import main
from backup_verify.offline import HistoryFileError, open_history_file
from backup_verify.queries import fetch_backups, fetch_databases, fetch_server_time

from .fakes import FIXTURES
from .helpers import FIXTURE_CONFIG, NOW

HEALTHY = os.path.join(FIXTURES, "healthy.json")


class HistoryFileTest(unittest.TestCase):
    def test_queries_are_answered_from_the_file(self):
        conn = open_history_file(HEALTHY)
        self.assertEqual(fetch_server_time(conn)[1], "SQLPROD01")
        self.assertEqual(len(fetch_databases(conn)), 3)
        self.assertEqual(len(fetch_backups(conn, NOW.replace(year=2000))), 51)

    def test_since_filters_old_backups(self):
        conn = open_history_file(HEALTHY)
        recent = fetch_backups(conn, NOW.replace(day=1, hour=0))
        self.assertTrue(0 < len(recent) < 51)
        self.assertTrue(all(b.start >= NOW.replace(day=1, hour=0) for b in recent))

    def test_missing_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "h.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump({"server_name": "X"}, fh)
            with self.assertRaises(HistoryFileError):
                open_history_file(path)

    def test_unreadable_files(self):
        with self.assertRaises(HistoryFileError):
            open_history_file("/nonexistent/history.json")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "h.json")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("[1, 2")
            with self.assertRaises(HistoryFileError):
                open_history_file(path)


class HistoryFileCliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.policy = os.path.join(self.tmp.name, "policy.json")
        with open(self.policy, "w", encoding="utf-8") as fh:
            json.dump(FIXTURE_CONFIG, fh)

    def run_cli(self, *argv):
        out = io.StringIO()
        code = main([*argv, "--config", self.policy], stdout=out)
        return code, out.getvalue()

    def test_history_file_replaces_the_server(self):
        code, out = self.run_cli("--history-file", HEALTHY)
        self.assertEqual(code, 0)
        self.assertIn("backup-verify report for SQLPROD01", out)

    def test_findings_from_a_history_file(self):
        code, out = self.run_cli("--history-file", os.path.join(FIXTURES, "stale.json"))
        self.assertEqual(code, 2)

    def test_server_or_file_but_not_both_or_neither(self):
        for argv in ([], ["--server", "A", "--history-file", HEALTHY]):
            with self.assertRaises(SystemExit) as ctx:
                self.run_cli(*argv)
            self.assertEqual(ctx.exception.code, 3)

    def test_execute_needs_a_live_server(self):
        with self.assertRaises(SystemExit) as ctx:
            self.run_cli("--history-file", HEALTHY, "--execute")
        self.assertEqual(ctx.exception.code, 3)

    def test_bad_file_is_an_error(self):
        code, out = self.run_cli("--history-file", "/nonexistent/h.json")
        self.assertEqual(code, 3)
