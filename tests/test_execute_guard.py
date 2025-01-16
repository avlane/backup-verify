import unittest
from unittest import mock

from backup_verify.execute import is_verify_only, run_verify
from backup_verify.scripts import verify_statements

from .fakes import connection_from_fixture
from .helpers import backup, fixture_backups


class GuardTest(unittest.TestCase):
    def test_generated_statements_pass(self):
        for name in ("Sales", "Reporting", "Inventory"):
            for _, sql in verify_statements(fixture_backups("healthy", name)):
                self.assertTrue(is_verify_only(sql), sql)

    def test_striped_and_odd_paths_pass(self):
        b = backup("Sales", "D", 1, devices=["D:\\a'b.bak", "D:\\c.bak"])
        for _, sql in verify_statements([b]):
            self.assertTrue(is_verify_only(sql), sql)

    def test_anything_else_is_rejected(self):
        for sql in (
            "RESTORE VERIFYONLY FROM DISK = N'a'; DROP DATABASE x;",
            "RESTORE VERIFYONLY FROM DISK = N'a' WITH CHECKSUM; SELECT 1;",
            "RESTORE DATABASE x FROM DISK = N'a';",
            "DROP DATABASE x;",
            "RESTORE VERIFYONLY FROM DISK = N'a' WITH REPLACE;",
            "",
        ):
            self.assertFalse(is_verify_only(sql), sql)

    def test_run_verify_refuses_to_execute_a_tampered_statement(self):
        conn = connection_from_fixture("healthy")
        b = backup("Sales", "D", 1)
        evil = "RESTORE VERIFYONLY FROM DISK = N'a'; DROP DATABASE Sales;"
        with mock.patch("backup_verify.execute.verify_statements", return_value=[(b, evil)]):
            (result,) = run_verify(conn, "Sales", [b])
        self.assertFalse(result.ok)
        self.assertIn("refused", result.error)
        self.assertEqual(conn.executed, [])
