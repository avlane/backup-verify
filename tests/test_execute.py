import io
import unittest

from backup_verify.cli import main
from backup_verify.execute import run_verify

from .fakes import connection_from_fixture
from .helpers import fixture_backups


def restores(conn):
    return [sql for sql, params in conn.executed if sql.lstrip().startswith("RESTORE")]


class RunVerifyTest(unittest.TestCase):
    def test_every_backup_in_the_chain_is_verified(self):
        conn = connection_from_fixture("healthy")
        results = run_verify(conn, "Reporting", fixture_backups("healthy", "Reporting"))
        self.assertEqual([r.type_name for r in results], ["full", "log", "log", "log"])
        self.assertTrue(all(r.ok for r in results))
        self.assertEqual(len(restores(conn)), 4)

    def test_a_failure_is_recorded_and_the_rest_still_run(self):
        conn = connection_from_fixture("healthy")
        conn.failures.append(("Reporting_LOG_20230301_020000", "Msg 3241: media family is damaged"))
        results = run_verify(conn, "Reporting", fixture_backups("healthy", "Reporting"))
        self.assertEqual([r.ok for r in results], [True, False, True, True])
        self.assertIn("3241", results[1].error)
        self.assertEqual(len(restores(conn)), 4)


class ExecuteFlagTest(unittest.TestCase):
    def run_cli(self, *argv, failures=()):
        conns = []

        def connect(args):
            conn = connection_from_fixture("healthy")
            conn.failures.extend(failures)
            conns.append(conn)
            return conn

        out = io.StringIO()
        code = main(["--server", "SQLPROD01", *argv], connect=connect, stdout=out)
        return code, out.getvalue(), conns[0]

    def test_nothing_runs_without_the_flag(self):
        code, out, conn = self.run_cli()
        self.assertEqual(restores(conn), [])

    def test_execute_verifies_every_database(self):
        code, out, conn = self.run_cli("--execute")
        self.assertEqual(len(restores(conn)), 13)
        self.assertTrue(all(sql.startswith("RESTORE VERIFYONLY") for sql in restores(conn)))

    def test_failed_verify_is_a_critical_finding(self):
        code, out, conn = self.run_cli("--execute", failures=[("Sales_FULL_20230301", "Msg 3241")])
        self.assertEqual(code, 2)
        self.assertIn("[CRITICAL] Sales: VERIFY_FAILED", out)
        self.assertIn("Msg 3241", out)
        self.assertEqual(len(restores(conn)), 13)
