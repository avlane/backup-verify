import unittest
from datetime import datetime

from backup_verify.queries import fetch_backups, fetch_databases

from .fakes import connection_from_fixture


class FetchBackupsTest(unittest.TestCase):
    def setUp(self):
        self.conn = connection_from_fixture("healthy")
        self.since = datetime(2023, 2, 27)
        self.backups = fetch_backups(self.conn, self.since)

    def test_every_row_is_mapped(self):
        self.assertEqual(len(self.backups), 51)

    def test_since_is_passed_as_parameter(self):
        sql, params = self.conn.executed[0]
        self.assertIn("backup_start_date >= ?", sql)
        self.assertEqual(params, (self.since,))

    def test_types_and_dates(self):
        first = self.backups[0]
        self.assertEqual(first.type, "D")
        self.assertEqual(first.start, datetime(2023, 2, 28, 1, 0))
        self.assertGreater(first.finish, first.start)

    def test_lsns_are_integers(self):
        for b in self.backups:
            self.assertIsInstance(b.first_lsn, int)
            self.assertIsInstance(b.last_lsn, int)
            self.assertLessEqual(b.first_lsn, b.last_lsn)

    def test_differential_has_base_lsn(self):
        diffs = [b for b in self.backups if b.type == "I"]
        self.assertEqual(len(diffs), 1)
        self.assertIsNotNone(diffs[0].differential_base_lsn)


class FetchDatabasesTest(unittest.TestCase):
    def test_recovery_models(self):
        dbs = fetch_databases(connection_from_fixture("healthy"))
        self.assertEqual([d.name for d in dbs], ["Sales", "Reporting", "Inventory"])
        self.assertEqual(dbs[2].recovery_model, "SIMPLE")
        self.assertEqual(dbs[0].state, "ONLINE")
