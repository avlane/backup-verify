import unittest

from backup_verify.analysis import check_diff_base

from .helpers import analyse_fixture, backup, codes


class DiffBaseTest(unittest.TestCase):
    def test_matching_base_is_fine(self):
        full = backup("Sales", "D", 10, checkpoint_lsn=500)
        diff = backup("Sales", "I", 4, differential_base_lsn=500)
        self.assertEqual(check_diff_base("Sales", [full, diff]), [])

    def test_mismatching_base_is_critical(self):
        full = backup("Sales", "D", 10, checkpoint_lsn=500)
        diff = backup("Sales", "I", 4, differential_base_lsn=400)
        (finding,) = check_diff_base("Sales", [full, diff])
        self.assertEqual(finding.code, "DIFF_BASE_MISMATCH")
        self.assertEqual(finding.detail["full_checkpoint_lsn"], 500)

    def test_differentials_older_than_the_full_are_not_checked(self):
        diff = backup("Sales", "I", 20, differential_base_lsn=1)
        full = backup("Sales", "D", 10, checkpoint_lsn=500)
        self.assertEqual(check_diff_base("Sales", [diff, full]), [])

    def test_no_differentials_no_finding(self):
        self.assertEqual(check_diff_base("Sales", [backup("Sales", "D", 3)]), [])

    def test_fixture(self):
        self.assertEqual(codes(analyse_fixture("diffbase")), [("Sales", "DIFF_BASE_MISMATCH")])
        self.assertEqual(codes(analyse_fixture("healthy")), [])
