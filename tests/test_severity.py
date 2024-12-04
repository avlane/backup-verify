import json
import unittest

from backup_verify.analysis import CRITICAL, INFO, WARNING, Severity
from backup_verify.report import render

from .helpers import analyse_fixture


class SeverityTest(unittest.TestCase):
    def test_ranking(self):
        self.assertLess(CRITICAL.rank, WARNING.rank)
        self.assertLess(WARNING.rank, INFO.rank)

    def test_behaves_like_a_string(self):
        self.assertEqual(Severity.CRITICAL, "critical")
        self.assertEqual(CRITICAL.upper(), "CRITICAL")

    def test_json_report_still_uses_plain_strings(self):
        doc = json.loads(render(analyse_fixture("stale"), "json"))
        self.assertEqual({f["severity"] for f in doc["findings"]}, {"critical", "warning"})
