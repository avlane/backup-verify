import unittest

from .helpers import analyse_fixture, codes


class FixtureAnalysisTest(unittest.TestCase):
    def test_healthy_server_has_no_findings(self):
        result = analyse_fixture("healthy")
        self.assertEqual(codes(result), [])
        self.assertEqual(result.counts(), {"databases": 3, "critical": 0, "warning": 0, "ok": 3})

    def test_stale_server(self):
        result = analyse_fixture("stale")
        self.assertEqual(codes(result), [
            ("NewDb", "NO_FULL_BACKUP"),
            ("NewDb", "NO_LOG_BACKUP"),
            ("Sales", "FULL_STALE"),
            ("Sales", "LOG_STALE"),
        ])
        counts = result.counts()
        self.assertEqual((counts["critical"], counts["warning"], counts["ok"]), (2, 0, 2))

    def test_simple_recovery_database_needs_no_log_backups(self):
        result = analyse_fixture("healthy")
        self.assertNotIn(("Inventory", "NO_LOG_BACKUP"), codes(result))

    def test_findings_are_sorted_worst_first(self):
        result = analyse_fixture("stale")
        severities = [f.severity for f in result.findings]
        self.assertEqual(severities, sorted(severities, key=["critical", "warning", "info"].index))


class DatabaseStateTest(unittest.TestCase):
    def test_offline_databases_are_skipped_not_failed(self):
        from backup_verify.analysis import analyse
        from backup_verify.config import Config

        from .helpers import NOW, database

        result = analyse([database("Old", state="OFFLINE")], [], Config(), NOW)
        self.assertEqual(result.checked, [])
        self.assertEqual([f.code for f in result.findings], ["SKIPPED_STATE"])
        self.assertEqual(result.counts()["critical"], 0)
