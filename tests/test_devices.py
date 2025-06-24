import unittest

from backup_verify.scripts import verify_script, verify_statement, verify_statements

from .helpers import NOW, analyse_fixture, backup, codes, fixture_backups


class DeviceTypeTest(unittest.TestCase):
    def test_url_device(self):
        url_full = [b for b in fixture_backups("url", "Sales") if b.device_type == 9]
        self.assertEqual(len(url_full), 1)
        sql = verify_statement(url_full[0])
        self.assertTrue(sql.startswith("RESTORE VERIFYONLY FROM URL = N'https://examplestore.blob.core.windows.net/"))
        self.assertTrue(sql.endswith("WITH CHECKSUM;"))

    def test_disk_is_still_the_default(self):
        self.assertIn("FROM DISK = ", verify_statement(backup("Sales", "D", 1)))

    def test_tape_device(self):
        b = backup("Sales", "D", 1, device_type=5, devices=["\\\\.\\Tape0"])
        self.assertIn("FROM TAPE = N'", verify_statement(b))

    def test_virtual_device_backups_are_skipped_with_a_comment(self):
        full = backup("Sales", "D", 5, device_type=7)
        log = backup("Sales", "L", 1)
        self.assertEqual([b for b, _ in verify_statements([full, log])], [log])
        text = verify_script("Sales", [full, log], "SQLPROD01", NOW)
        self.assertIn("-- Skipped full backup", text)
        self.assertIn("virtual device", text)

    def test_fixture_with_a_url_backup_has_no_findings(self):
        self.assertEqual(codes(analyse_fixture("url")), [])
