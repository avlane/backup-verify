import unittest

from backup_verify.connection import build_connection_string, connect


class ConnectionStringTest(unittest.TestCase):
    def test_defaults_use_driver_18_and_integrated_auth(self):
        cs = build_connection_string("SQLPROD01")
        self.assertIn("DRIVER={ODBC Driver 18 for SQL Server}", cs)
        self.assertIn("SERVER=SQLPROD01;", cs)
        self.assertIn("Encrypt=yes", cs)
        self.assertIn("Trusted_Connection=yes", cs)
        self.assertNotIn("TrustServerCertificate", cs)

    def test_trust_server_certificate_and_no_encrypt(self):
        cs = build_connection_string("SQLDR02", encrypt=False, trust_server_certificate=True)
        self.assertIn("Encrypt=no", cs)
        self.assertIn("TrustServerCertificate=yes", cs)

    def test_sql_login_values_are_braced(self):
        cs = build_connection_string("SQLPROD01", user="svc_backup", password="p}ss;word")
        self.assertIn("UID={svc_backup}", cs)
        self.assertIn("PWD={p}}ss;word}", cs)
        self.assertNotIn("Trusted_Connection", cs)

    def test_older_driver_can_be_selected(self):
        cs = build_connection_string("SQLPROD01", driver="ODBC Driver 17 for SQL Server")
        self.assertIn("DRIVER={ODBC Driver 17 for SQL Server}", cs)


class FakePyodbc:
    def __init__(self):
        self.calls = []

    def connect(self, cs, **kwargs):
        self.calls.append((cs, kwargs))
        return type("Conn", (), {"timeout": 30})()


class ConnectTest(unittest.TestCase):
    def test_connect_uses_autocommit_and_disables_query_timeout(self):
        fake = FakePyodbc()
        conn = connect("SQLPROD01", pyodbc_module=fake, trust_server_certificate=True)
        (cs, kwargs), = fake.calls
        self.assertIn("SERVER=SQLPROD01", cs)
        self.assertTrue(kwargs["autocommit"])
        self.assertEqual(kwargs["timeout"], 15)
        self.assertEqual(conn.timeout, 0)
