import io
import os
import tempfile
import unittest

from backup_verify.cli import main
from backup_verify.scripts import safe_filename

from .fakes import connection_from_fixture


class ScriptsDirTest(unittest.TestCase):
    def run_cli(self, directory, fixture="healthy"):
        conns = []

        def connect(args):
            conns.append(connection_from_fixture(fixture))
            return conns[0]

        code = main(["--server", "SQLPROD01", "--scripts-dir", directory],
                    connect=connect, stdout=io.StringIO())
        return code, conns[0]

    def test_one_script_per_database_with_a_chain(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "scripts")
            self.run_cli(target)
            self.assertEqual(sorted(os.listdir(target)), [
                "Inventory.test-restore.sql", "Inventory.verify.sql",
                "Reporting.test-restore.sql", "Reporting.verify.sql",
                "Sales.test-restore.sql", "Sales.verify.sql"])
            with open(os.path.join(target, "Sales.verify.sql"), encoding="utf-8") as fh:
                text = fh.read()
            self.assertEqual(text.count("RESTORE VERIFYONLY FROM"), 8)

    def test_nothing_is_executed_against_the_server(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, conn = self.run_cli(tmp)
        self.assertTrue(conn.executed)
        for sql, params in conn.executed:
            self.assertTrue(sql.lstrip().upper().startswith("SELECT"), sql)

    def test_databases_without_a_full_backup_get_no_script(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.run_cli(tmp, fixture="stale")
            self.assertNotIn("NewDb.verify.sql", os.listdir(tmp))

    def test_safe_filename(self):
        self.assertEqual(safe_filename("my db/x:y"), "my_db_x_y")
        self.assertEqual(safe_filename("Sales_2023.v1"), "Sales_2023.v1")


class TestRestoreScriptsTest(unittest.TestCase):
    def test_restore_scripts_are_written_next_to_verify_scripts(self):
        with tempfile.TemporaryDirectory() as tmp:
            main(["--server", "SQLPROD01", "--scripts-dir", tmp, "--restore-dir", "R:\\T"],
                 connect=lambda args: connection_from_fixture("healthy"), stdout=io.StringIO())
            self.assertIn("Sales.test-restore.sql", os.listdir(tmp))
            with open(os.path.join(tmp, "Sales.test-restore.sql"), encoding="utf-8") as fh:
                self.assertIn("R:\\T\\verify_Sales_1.mdf", fh.read())

    def test_empty_prefix_is_a_usage_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            code = main(["--server", "SQLPROD01", "--scripts-dir", tmp, "--restore-prefix", ""],
                        connect=lambda args: connection_from_fixture("healthy"), stdout=io.StringIO())
        self.assertEqual(code, 3)
