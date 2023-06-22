import unittest

from backup_verify.report import render, render_text

from .helpers import analyse_fixture


class TextReportTest(unittest.TestCase):
    def test_clean_report(self):
        text = render_text(analyse_fixture("healthy"))
        self.assertIn("backup-verify report for SQLPROD01", text)
        self.assertIn("server time: 2023-03-01 08:00:00", text)
        self.assertIn("3 database(s) checked: 3 ok, 0 with warnings, 0 critical", text)
        self.assertIn("No problems found.", text)

    def test_findings_listed_with_severity(self):
        text = render_text(analyse_fixture("stale"))
        self.assertIn("[CRITICAL] NewDb: NO_FULL_BACKUP", text)
        self.assertIn("[WARNING] Sales: FULL_STALE - last full backup finished 30.9 h ago (limit 26 h)", text)

    def test_unknown_format(self):
        with self.assertRaises(ValueError):
            render(analyse_fixture("healthy"), "xml")
