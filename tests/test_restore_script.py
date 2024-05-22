import unittest

from backup_verify.scripts import move_clauses, restore_test_script

from .helpers import NOW, backup, fixture_backups


class RestoreTestScriptTest(unittest.TestCase):
    def setUp(self):
        self.text = restore_test_script("Sales", fixture_backups("healthy", "Sales"),
                                        "SQLPROD01", NOW, restore_dir="E:\\RestoreTest")

    def test_restores_under_a_different_name(self):
        self.assertIn("RESTORE DATABASE [verify_Sales]", self.text)
        self.assertNotIn("RESTORE DATABASE [Sales]", self.text)
        self.assertNotIn("RESTORE LOG [Sales]", self.text)

    def test_files_are_moved(self):
        self.assertIn("MOVE N'Sales' TO N'E:\\RestoreTest\\verify_Sales_1.mdf'", self.text)
        self.assertIn("MOVE N'Sales_log' TO N'E:\\RestoreTest\\verify_Sales_2.ldf'", self.text)

    def test_every_step_but_the_last_is_norecovery(self):
        self.assertEqual(self.text.count("RESTORE LOG [verify_Sales]"), 7)
        self.assertEqual(self.text.count("WITH NORECOVERY;"), 7)
        self.assertEqual(self.text.count("RESTORE DATABASE [verify_Sales] WITH RECOVERY;"), 1)
        self.assertLess(self.text.index("WITH NORECOVERY;"), self.text.index("WITH RECOVERY;"))

    def test_checkdb_and_commented_out_drop(self):
        self.assertIn("DBCC CHECKDB (N'verify_Sales')", self.text)
        drops = [line for line in self.text.splitlines() if "DROP DATABASE" in line]
        self.assertEqual(len(drops), 1)
        self.assertTrue(drops[0].startswith("--"))

    def test_empty_prefix_is_refused(self):
        with self.assertRaises(ValueError):
            restore_test_script("Sales", fixture_backups("healthy", "Sales"), "SQLPROD01", NOW, prefix="")

    def test_missing_file_list_is_explained(self):
        text = restore_test_script("Sales", [backup("Sales", "D", 2)], "SQLPROD01", NOW)
        self.assertIn("no file list", text)
        self.assertNotIn("RESTORE DATABASE", text)

    def test_differential_is_restored_between_full_and_logs(self):
        full = backup("Sales", "D", 10, first=100, last=150, checkpoint_lsn=120)
        diff = backup("Sales", "I", 6, first=300, last=350, differential_base_lsn=120)
        log = backup("Sales", "L", 2, first=350, last=400)
        from backup_verify.model import BackupFile
        full.files = [BackupFile("Sales", "E:\\Data\\Sales.mdf", "D")]
        text = restore_test_script("Sales", [full, diff, log], "SQLPROD01", NOW)
        self.assertLess(text.index("differential backup"), text.index("RESTORE LOG"))
        self.assertIn("RESTORE DATABASE [verify_Sales] FROM DISK", text)

    def test_second_data_file_is_ndf(self):
        from backup_verify.model import BackupFile
        full = backup("Sales", "D", 1)
        full.files = [BackupFile("a", "x", "D"), BackupFile("b", "y", "D"), BackupFile("a_log", "z", "L")]
        clauses = move_clauses(full, "verify_Sales", "E:\\RT\\")
        self.assertTrue(clauses[0].endswith("verify_Sales_1.mdf'"))
        self.assertTrue(clauses[1].endswith("verify_Sales_2.ndf'"))
        self.assertTrue(clauses[2].endswith("verify_Sales_3.ldf'"))
        self.assertIn("E:\\RT\\verify_Sales_1", clauses[0])
