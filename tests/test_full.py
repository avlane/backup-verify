import unittest

from backup_verify.analysis import analyse, CRITICAL, WARNING
from backup_verify.config import parse_config

from .helpers import NOW, backup, database


def run(backups, dbs=("Sales",), cfg=None):
    cfg = cfg or parse_config({"defaults": {"log_max_age_minutes": None}})
    return analyse([database(n) for n in dbs], backups, cfg, NOW)


class FullBackupCheckTest(unittest.TestCase):
    def test_recent_full_is_fine(self):
        result = run([backup("Sales", "D", 5)])
        self.assertEqual(result.findings, [])
        self.assertEqual(result.counts()["ok"], 1)

    def test_no_backups_at_all_is_critical(self):
        result = run([])
        self.assertEqual([f.code for f in result.findings], ["NO_FULL_BACKUP"])
        self.assertEqual(result.findings[0].severity, CRITICAL)

    def test_slightly_stale_full_is_a_warning(self):
        result = run([backup("Sales", "D", 30)])
        self.assertEqual(result.findings[0].code, "FULL_STALE")
        self.assertEqual(result.findings[0].severity, WARNING)

    def test_very_stale_full_is_critical(self):
        result = run([backup("Sales", "D", 60)])
        self.assertEqual(result.findings[0].severity, CRITICAL)

    def test_latest_full_wins(self):
        result = run([backup("Sales", "D", 100), backup("Sales", "D", 3)])
        self.assertEqual(result.findings, [])

    def test_threshold_comes_from_policy(self):
        cfg = parse_config({"defaults": {"log_max_age_minutes": None},
                            "databases": {"Archive": {"full_max_age_hours": 200}}})
        result = run([backup("Archive", "D", 100)], dbs=("Archive",), cfg=cfg)
        self.assertEqual(result.findings, [])

    def test_excluded_databases_are_skipped(self):
        result = run([], dbs=("tempdb", "Sales"))
        self.assertEqual(result.checked, ["Sales"])

    def test_backups_are_matched_case_insensitively(self):
        result = run([backup("SALES", "D", 2)])
        self.assertEqual(result.findings, [])
