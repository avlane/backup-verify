import unittest

from backup_verify.analysis import check_quality

from .helpers import analyse_fixture, backup, codes


class QualityTest(unittest.TestCase):
    def test_damaged_backup_in_chain(self):
        full = backup("Sales", "D", 5)
        log = backup("Sales", "L", 2, is_damaged=True)
        (finding,) = check_quality("Sales", [full, log])
        self.assertEqual(finding.code, "BACKUP_DAMAGED")
        self.assertEqual(finding.detail["backup_set_id"], log.backup_set_id)

    def test_damaged_backup_outside_the_chain_is_ignored(self):
        old = backup("Sales", "D", 50, is_damaged=True)
        new = backup("Sales", "D", 2)
        self.assertEqual(check_quality("Sales", [old, new]), [])

    def test_full_without_checksum_is_a_warning(self):
        (finding,) = check_quality("Sales", [backup("Sales", "D", 5, has_checksum=False)])
        self.assertEqual(finding.code, "NO_CHECKSUM")
        self.assertEqual(finding.severity, "warning")

    def test_no_backups_no_findings(self):
        self.assertEqual(check_quality("Sales", []), [])

    def test_fixture(self):
        self.assertEqual(codes(analyse_fixture("quality")),
                         [("Reporting", "NO_CHECKSUM"), ("Sales", "BACKUP_DAMAGED")])
