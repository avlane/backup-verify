import unittest

from backup_verify.analysis import analyse
from backup_verify.chain import restore_chain
from backup_verify.config import parse_config

from .helpers import NOW, analyse_fixture, backup, codes, database, fixture_backups


class CopyOnlyTest(unittest.TestCase):
    def test_copy_only_full_does_not_satisfy_the_full_target(self):
        result = analyse_fixture("copy_only")
        self.assertEqual(codes(result), [("Sales", "FULL_STALE")])

    def test_only_copy_only_fulls_means_no_full(self):
        cfg = parse_config({"defaults": {"log_max_age_minutes": None}})
        result = analyse([database("Sales")], [backup("Sales", "D", 1, is_copy_only=True)], cfg, NOW)
        (finding,) = result.findings
        self.assertEqual(finding.code, "NO_FULL_BACKUP")
        self.assertIn("copy-only", finding.message)

    def test_copy_only_log_backup_does_not_break_the_chain(self):
        # a copy-only log backup starts at the same LSN as the next regular one
        result = analyse_fixture("copy_only")
        self.assertNotIn("LOG_CHAIN_BROKEN", [f.code for f in result.findings])

    def test_restore_chain_skips_copy_only_backups(self):
        chain = restore_chain(fixture_backups("copy_only", "Sales"))
        self.assertFalse(any(b.is_copy_only for b in chain))
        self.assertEqual(chain[0].start.isoformat(), "2023-02-28T01:00:00")
