import unittest

from backup_verify.analysis import analyse, CRITICAL, WARNING
from backup_verify.config import parse_config

from .helpers import NOW, backup, database


def run(backups, **policy):
    cfg = parse_config({"defaults": policy})
    return analyse([database("Sales")], backups, cfg, NOW)


class DiffCheckTest(unittest.TestCase):
    def test_not_checked_unless_configured(self):
        result = run([backup("Sales", "D", 5)], log_max_age_minutes=None)
        self.assertEqual(result.findings, [])

    def test_stale_differential(self):
        result = run([backup("Sales", "D", 20), backup("Sales", "I", 14)],
                     diff_max_age_hours=12, log_max_age_minutes=None)
        self.assertEqual([f.code for f in result.findings], ["DIFF_STALE"])

    def test_recent_full_satisfies_differential_target(self):
        result = run([backup("Sales", "D", 2)], diff_max_age_hours=12,
                     log_max_age_minutes=None)
        self.assertEqual(result.findings, [])


class LogCheckTest(unittest.TestCase):
    def test_recent_log_is_fine(self):
        result = run([backup("Sales", "D", 5), backup("Sales", "L", 0.25)],
                     log_max_age_minutes=30)
        self.assertEqual(result.findings, [])

    def test_missing_log_backups(self):
        result = run([backup("Sales", "D", 5)], log_max_age_minutes=30)
        self.assertEqual(result.findings[0].code, "NO_LOG_BACKUP")
        self.assertEqual(result.findings[0].severity, CRITICAL)

    def test_stale_log_warning_then_critical(self):
        warn = run([backup("Sales", "D", 5), backup("Sales", "L", 0.75)],
                   log_max_age_minutes=30)
        self.assertEqual(warn.findings[0].code, "LOG_STALE")
        self.assertEqual(warn.findings[0].severity, WARNING)
        crit = run([backup("Sales", "D", 5), backup("Sales", "L", 2)],
                   log_max_age_minutes=30)
        self.assertEqual(crit.findings[0].severity, CRITICAL)
