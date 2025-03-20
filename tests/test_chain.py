import unittest

from backup_verify.analysis import check_log_chain

from .helpers import analyse_fixture, backup, codes


def with_full(*logs, full_last=100):
    return [backup("Sales", "D", 10, first=50, last=full_last), *logs]


class LogChainTest(unittest.TestCase):
    def test_contiguous_chain_is_clean(self):
        logs = [backup("Sales", "L", 3, first=100, last=200),
                backup("Sales", "L", 2, first=200, last=300),
                backup("Sales", "L", 1, first=300, last=400)]
        self.assertEqual(check_log_chain("Sales", with_full(*logs)), [])

    def test_missing_log_backup_is_detected(self):
        logs = [backup("Sales", "L", 3, first=100, last=200),
                backup("Sales", "L", 1, first=300, last=400)]
        (finding,) = check_log_chain("Sales", with_full(*logs))
        self.assertEqual(finding.code, "LOG_CHAIN_BROKEN")
        self.assertEqual(finding.detail["expected_first_lsn"], 200)
        self.assertEqual(finding.detail["actual_first_lsn"], 300)

    def test_input_order_does_not_matter(self):
        logs = [backup("Sales", "L", 1, first=200, last=300),
                backup("Sales", "L", 2, first=100, last=200)]
        self.assertEqual(check_log_chain("Sales", with_full(*logs)), [])

    def test_a_log_backup_may_overlap_the_end_of_the_full(self):
        log = backup("Sales", "L", 2, first=60, last=160)
        self.assertEqual(check_log_chain("Sales", with_full(log)), [])

    def test_first_log_must_cover_the_end_of_the_full(self):
        log = backup("Sales", "L", 2, first=150, last=250)
        (finding,) = check_log_chain("Sales", with_full(log))
        self.assertEqual(finding.code, "LOG_CHAIN_NOT_ANCHORED")
        self.assertEqual(finding.detail["full_last_lsn"], 100)

    def test_gaps_before_the_latest_full_are_ignored(self):
        old = [backup("Sales", "L", 30, first=100, last=200), backup("Sales", "L", 28, first=500, last=600)]
        new_full = backup("Sales", "D", 10, first=900, last=1000)
        new_log = backup("Sales", "L", 5, first=950, last=1100)
        self.assertEqual(check_log_chain("Sales", [*old, new_full, new_log]), [])

    def test_no_full_no_chain_check(self):
        self.assertEqual(check_log_chain("Sales", [backup("Sales", "L", 3, first=1, last=2)]), [])

    def test_no_logs_is_not_a_chain_problem(self):
        self.assertEqual(check_log_chain("Sales", with_full()), [])

    def test_ignores_differentials(self):
        mixed = with_full(backup("Sales", "I", 2, first=500, last=600))
        self.assertEqual(check_log_chain("Sales", mixed), [])


class ChainFixtureTest(unittest.TestCase):
    def test_gap_after_the_latest_full_is_reported_for_sales_only(self):
        result = analyse_fixture("broken_chain")
        self.assertEqual(codes(result), [("Sales", "LOG_CHAIN_BROKEN")])
        finding = result.findings[0]
        self.assertEqual(finding.detail["gap_from"], "2023-03-01T03:01:00")
        self.assertEqual(finding.detail["gap_to"], "2023-03-01T05:00:00")

    def test_old_gap_before_the_latest_full_is_not_reported(self):
        self.assertEqual(codes(analyse_fixture("old_gap")), [])
