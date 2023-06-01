import unittest

from backup_verify.analysis import check_log_chain

from .helpers import backup, analyse_fixture, codes


class LogChainTest(unittest.TestCase):
    def test_contiguous_chain_is_clean(self):
        logs = [backup("Sales", "L", 3, first=100, last=200),
                backup("Sales", "L", 2, first=200, last=300),
                backup("Sales", "L", 1, first=300, last=400)]
        self.assertEqual(check_log_chain("Sales", logs), [])

    def test_missing_log_backup_is_detected(self):
        logs = [backup("Sales", "L", 3, first=100, last=200),
                backup("Sales", "L", 1, first=300, last=400)]
        (finding,) = check_log_chain("Sales", logs)
        self.assertEqual(finding.code, "LOG_CHAIN_BROKEN")
        self.assertEqual(finding.detail["expected_first_lsn"], 200)
        self.assertEqual(finding.detail["actual_first_lsn"], 300)

    def test_input_order_does_not_matter(self):
        logs = [backup("Sales", "L", 1, first=200, last=300),
                backup("Sales", "L", 2, first=100, last=200)]
        self.assertEqual(check_log_chain("Sales", logs), [])

    def test_ignores_other_backup_types(self):
        mixed = [backup("Sales", "D", 3, first=10, last=20), backup("Sales", "I", 2, first=500, last=600)]
        self.assertEqual(check_log_chain("Sales", mixed), [])


class BrokenChainFixtureTest(unittest.TestCase):
    def test_gap_is_reported_for_sales_only(self):
        result = analyse_fixture("broken_chain")
        self.assertEqual(codes(result), [("Sales", "LOG_CHAIN_BROKEN")])
        finding = result.findings[0]
        self.assertEqual(finding.detail["gap_from"], "2023-03-01T03:01:00")
        self.assertEqual(finding.detail["gap_to"], "2023-03-01T05:00:00")
