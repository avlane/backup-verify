import unittest

from backup_verify.analysis import analyse
from backup_verify.config import parse_config

from .helpers import NOW, analyse_fixture, codes


class NewDatabaseTest(unittest.TestCase):
    def test_a_database_created_an_hour_ago_is_informational(self):
        result = analyse_fixture("newdb")
        self.assertEqual(codes(result), [("NewDb", "NEW_DATABASE")])
        self.assertEqual(result.counts()["critical"], 0)
        self.assertEqual(result.counts()["ok"], 4)

    def test_it_becomes_critical_once_the_first_full_is_overdue(self):
        from datetime import timedelta

        from .helpers import fixture_databases

        dbs = fixture_databases("newdb")
        new = [d for d in dbs if d.name == "NewDb"]
        new[0].created = NOW - timedelta(hours=30)
        result = analyse(new, [], parse_config({}), NOW)
        self.assertEqual([f.code for f in result.findings], ["NO_FULL_BACKUP"])

    def test_no_log_backup_finding_without_a_full_backup(self):
        result = analyse_fixture("stale")
        self.assertEqual([f.code for f in result.findings if f.database == "NewDb"], ["NO_FULL_BACKUP"])
