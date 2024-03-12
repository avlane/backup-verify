import unittest

from backup_verify.queries import fetch_backups
from backup_verify.scripts import verify_statement

from .fakes import connection_from_fixture
from .helpers import NOW, fixture_backups


class StripedBackupTest(unittest.TestCase):
    def test_devices_of_one_backup_set_are_folded_together(self):
        backups = fetch_backups(connection_from_fixture("striped"), NOW)
        self.assertEqual(len(backups), 51)
        striped = [b for b in backups if len(b.devices) > 1]
        self.assertEqual(len(striped), 1)
        self.assertEqual(striped[0].database, "Reporting")
        self.assertEqual(len(striped[0].devices), 2)

    def test_device_order_is_kept(self):
        (striped,) = [b for b in fixture_backups("striped", "Reporting") if len(b.devices) > 1]
        self.assertTrue(striped.devices[0].endswith("_1.bak"))
        self.assertTrue(striped.devices[1].endswith("_2.bak"))

    def test_verify_statement_lists_every_stripe(self):
        (striped,) = [b for b in fixture_backups("striped", "Reporting") if len(b.devices) > 1]
        sql = verify_statement(striped)
        self.assertEqual(sql.count("DISK = "), 2)
        self.assertIn("_1.bak', DISK = N'", sql)
