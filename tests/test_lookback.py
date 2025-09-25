import io
import unittest
from datetime import datetime

from backup_verify.cli import DEFAULT_LOOKBACK_DAYS, main

from .fakes import connection_from_fixture


class LookbackTest(unittest.TestCase):
    def since_for(self, *argv):
        conns = []

        def connect(args):
            conns.append(connection_from_fixture("healthy"))
            return conns[0]

        main(["--server", "SQLPROD01", *argv], connect=connect, stdout=io.StringIO())
        (params,) = [p for sql, p in conns[0].executed if "backupmediafamily" in sql]
        return params[0]

    def test_default_covers_a_monthly_full(self):
        self.assertEqual(DEFAULT_LOOKBACK_DAYS, 35)
        self.assertEqual(self.since_for(), datetime(2023, 1, 25, 8, 0, 0))

    def test_since_days(self):
        self.assertEqual(self.since_for("--since-days", "7"), datetime(2023, 2, 22, 8, 0, 0))

    def test_bad_values_are_usage_errors(self):
        for value in ("0", "-3", "week"):
            with self.assertRaises(SystemExit) as ctx:
                main(["--server", "SQLPROD01", "--since-days", value], stdout=io.StringIO())
            self.assertEqual(ctx.exception.code, 3)
