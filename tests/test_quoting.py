import unittest

from backup_verify.scripts import (one_line, quote_literal, quote_name, restore_test_script,
                                   verify_script, verify_statement)

from .helpers import NOW, backup


class QuotingTest(unittest.TestCase):
    def test_closing_bracket_is_doubled(self):
        self.assertEqual(quote_name("odd]name"), "[odd]]name]")

    def test_single_quote_is_doubled(self):
        self.assertEqual(quote_literal("O'Brien"), "N'O''Brien'")

    def test_device_path_cannot_break_out_of_the_literal(self):
        b = backup("Sales", "D", 1, devices=["D:\\bak\\x'; DROP DATABASE Sales; --.bak"])
        self.assertEqual(verify_statement(b),
                         "RESTORE VERIFYONLY FROM DISK = N'D:\\bak\\x''; DROP DATABASE Sales; --.bak' WITH CHECKSUM;")

    def test_newline_in_a_database_name_stays_inside_the_comment(self):
        name = "Evil\nDROP DATABASE master"
        text = verify_script(name, [backup(name, "D", 1, devices=["D:\\bak\\x.bak"])], "SQLPROD01", NOW)
        for line in text.splitlines():
            self.assertFalse(line.startswith("DROP"), line)
        self.assertEqual(one_line("a\r\nb"), "a b")

    def test_test_restore_target_name_is_quoted(self):
        from backup_verify.model import BackupFile
        full = backup("O'Brien [Prod]", "D", 1)
        full.files = [BackupFile("O'Brien", "E:\\o.mdf", "D")]
        text = restore_test_script("O'Brien [Prod]", [full], "SQLPROD01", NOW)
        self.assertIn("RESTORE DATABASE [verify_O'Brien [Prod]]]", text)
        self.assertIn("MOVE N'O''Brien' TO", text)
        self.assertIn("DBCC CHECKDB (N'verify_O''Brien [Prod]')", text)
