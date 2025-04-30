import io
import os
import tempfile
import unittest
from datetime import datetime

from backup_verify.chain import restore_chain
from backup_verify.cli import main
from backup_verify.scripts import restore_test_script

from .fakes import connection_from_fixture
from .helpers import NOW, backup, fixture_backups


class PointInTimeChainTest(unittest.TestCase):
    def test_chain_stops_at_the_log_backup_that_contains_the_time(self):
        backups = fixture_backups("healthy", "Sales")
        chain = restore_chain(backups, datetime(2023, 3, 1, 4, 30))
        self.assertEqual(chain[0].start, datetime(2023, 3, 1, 1, 0))
        self.assertEqual([b.type for b in chain], ["D"] + ["L"] * 5)
        self.assertEqual(chain[-1].start, datetime(2023, 3, 1, 5, 0))

    def test_an_earlier_full_is_used_when_the_latest_finished_after_the_time(self):
        backups = fixture_backups("healthy", "Sales")
        chain = restore_chain(backups, datetime(2023, 2, 28, 20, 0))
        self.assertEqual(chain[0].start, datetime(2023, 2, 28, 1, 0))
        self.assertEqual(chain[1].type, "I")

    def test_time_before_every_full_gives_no_chain(self):
        self.assertEqual(restore_chain(fixture_backups("healthy", "Sales"), datetime(2023, 1, 1)), [])

    def test_without_stopat_nothing_changes(self):
        self.assertEqual(len(restore_chain(fixture_backups("healthy", "Sales"))), 8)


class StopAtScriptTest(unittest.TestCase):
    def test_stopat_on_the_last_log_restore_only(self):
        text = restore_test_script("Sales", fixture_backups("healthy", "Sales"), "SQLPROD01", NOW,
                                   stopat=datetime(2023, 3, 1, 4, 30))
        self.assertEqual(text.count("STOPAT = "), 1)
        lines = [l for l in text.splitlines() if l.startswith("RESTORE LOG")]
        self.assertEqual(len(lines), 5)
        self.assertIn("STOPAT = N'2023-03-01T04:30:00'", lines[-1])
        self.assertTrue(all("STOPAT" not in l for l in lines[:-1]))

    def test_stopat_before_any_full(self):
        text = restore_test_script("Sales", fixture_backups("healthy", "Sales"), "SQLPROD01", NOW,
                                   stopat=datetime(2022, 1, 1))
        self.assertIn("finished before STOPAT", text)

    def test_stopat_without_a_log_backup_is_explained(self):
        full = backup("Sales", "D", 5)
        from backup_verify.model import BackupFile
        full.files = [BackupFile("Sales", "E:\\Sales.mdf", "D")]
        text = restore_test_script("Sales", [full], "SQLPROD01", NOW, stopat=NOW)
        self.assertIn("No log backup reaches STOPAT", text)


class StopAtCliTest(unittest.TestCase):
    def test_option_reaches_the_script(self):
        with tempfile.TemporaryDirectory() as tmp:
            main(["--server", "SQLPROD01", "--scripts-dir", tmp, "--stopat", "2023-03-01T04:30:00"],
                 connect=lambda args: connection_from_fixture("healthy"), stdout=io.StringIO())
            with open(os.path.join(tmp, "Sales.test-restore.sql"), encoding="utf-8") as fh:
                self.assertIn("STOPAT = N'2023-03-01T04:30:00'", fh.read())

    def test_bad_timestamp_is_a_usage_error(self):
        with self.assertRaises(SystemExit) as ctx:
            main(["--server", "SQLPROD01", "--stopat", "yesterday"], stdout=io.StringIO())
        self.assertEqual(ctx.exception.code, 3)
