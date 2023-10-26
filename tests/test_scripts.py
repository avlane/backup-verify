import unittest

from backup_verify.chain import restore_chain
from backup_verify.scripts import verify_script, verify_statement, verify_statements

from .helpers import NOW, backup, fixture_backups


class RestoreChainTest(unittest.TestCase):
    def test_full_then_logs_in_lsn_order(self):
        chain = restore_chain(fixture_backups("healthy", "Sales"))
        self.assertEqual([b.type for b in chain], ["D"] + ["L"] * 7)
        self.assertEqual(chain[0].start.isoformat(), "2023-03-01T01:00:00")
        firsts = [b.first_lsn for b in chain[1:]]
        self.assertEqual(firsts, sorted(firsts))

    def test_differential_is_used_when_it_matches_the_full(self):
        full = backup("Sales", "D", 10, first=100, last=150, checkpoint_lsn=120)
        diff = backup("Sales", "I", 6, first=300, last=350, differential_base_lsn=120)
        old_log = backup("Sales", "L", 5, first=150, last=250)
        new_log = backup("Sales", "L", 2, first=350, last=400)
        chain = restore_chain([old_log, new_log, diff, full])
        self.assertEqual([b.type for b in chain], ["D", "I", "L"])
        self.assertIs(chain[-1], new_log)

    def test_differential_for_another_base_is_ignored(self):
        full = backup("Sales", "D", 10, first=100, last=150, checkpoint_lsn=120)
        diff = backup("Sales", "I", 6, first=300, last=350, differential_base_lsn=999)
        self.assertEqual(restore_chain([full, diff]), [full])

    def test_no_full_no_chain(self):
        self.assertEqual(restore_chain([backup("Sales", "L", 1)]), [])


class VerifyScriptTest(unittest.TestCase):
    def test_statement_uses_checksum_only_when_the_backup_has_one(self):
        with_sum = backup("Sales", "D", 1, devices=["D:\\bak\\a.bak"])
        without = backup("Sales", "D", 1, devices=["D:\\bak\\b.bak"], has_checksum=False)
        self.assertEqual(verify_statement(with_sum),
                         "RESTORE VERIFYONLY FROM DISK = N'D:\\bak\\a.bak' WITH CHECKSUM;")
        self.assertEqual(verify_statement(without),
                         "RESTORE VERIFYONLY FROM DISK = N'D:\\bak\\b.bak';")

    def test_one_statement_per_backup_in_the_chain(self):
        statements = verify_statements(fixture_backups("healthy", "Reporting"))
        self.assertEqual(len(statements), 4)
        self.assertTrue(all(sql.startswith("RESTORE VERIFYONLY") for _, sql in statements))

    def test_script_has_header_and_database_name(self):
        text = verify_script("Sales", fixture_backups("healthy", "Sales"), "SQLPROD01", NOW)
        self.assertIn("REVIEW BEFORE RUNNING", text)
        self.assertIn("-- Database: [Sales]", text)
        self.assertEqual(text.count("RESTORE VERIFYONLY FROM"), 8)
        self.assertNotIn("DROP", text)

    def test_script_for_database_without_backups(self):
        text = verify_script("NewDb", [], "SQLPROD01", NOW)
        self.assertIn("nothing to verify", text)
        self.assertNotIn("RESTORE", text.replace("RESTORE VERIFYONLY reads", ""))
