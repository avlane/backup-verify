import json
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


class JsonReportTest(unittest.TestCase):
    def test_json_round_trips(self):
        doc = json.loads(render(analyse_fixture("stale"), "json"))
        self.assertEqual(doc["server"], "SQLPROD01")
        self.assertEqual(doc["server_time"], "2023-03-01T08:00:00")
        self.assertEqual(doc["summary"]["critical"], 2)
        first = doc["findings"][0]
        self.assertEqual(set(first), {"database", "code", "severity", "message", "detail"})
        self.assertEqual(first["severity"], "critical")

    def test_empty_findings(self):
        doc = json.loads(render(analyse_fixture("healthy"), "json"))
        self.assertEqual(doc["findings"], [])


class MarkdownReportTest(unittest.TestCase):
    def test_table_rows(self):
        text = render(analyse_fixture("stale"), "markdown")
        self.assertTrue(text.startswith("# Backup verification: SQLPROD01\n"))
        self.assertIn("| Severity | Database | Code | Detail |", text)
        self.assertIn("| critical | NewDb | `NO_FULL_BACKUP` | no full backup found in the history window |", text)
        self.assertIn("| warning | Sales | `FULL_STALE` |", text)

    def test_clean_report_has_no_table(self):
        text = render(analyse_fixture("healthy"), "markdown")
        self.assertIn("No problems found.", text)
        self.assertNotIn("| Severity", text)


class RestoreChainsInJsonTest(unittest.TestCase):
    def test_chains_are_listed_per_database(self):
        doc = json.loads(render(analyse_fixture("healthy"), "json"))
        chains = doc["restore_chains"]
        self.assertEqual(sorted(chains), ["Inventory", "Reporting", "Sales"])
        self.assertEqual([b["type"] for b in chains["Sales"]], ["full"] + ["log"] * 7)
        self.assertEqual(chains["Sales"][0]["finished"], "2023-03-01T01:06:00")
        self.assertTrue(chains["Sales"][0]["devices"][0].endswith(".bak"))

    def test_database_without_backups_has_an_empty_chain(self):
        doc = json.loads(render(analyse_fixture("stale"), "json"))
        self.assertEqual(doc["restore_chains"]["NewDb"], [])
