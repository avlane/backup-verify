"""A fake DB-API connection that answers queries from recorded rows."""
import json
import os

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.description = None
        self._rows = []

    def execute(self, sql, *params):
        self.conn.executed.append((sql, params))
        for marker, rows in self.conn.responses:
            if marker in sql:
                cols = list(rows[0]) if rows else []
                self.description = [(c, None, None, None, None, None, None) for c in cols]
                self._rows = [tuple(r[c] for c in cols) for r in rows]
                return self
        raise AssertionError("no fake response for: " + sql.strip()[:60])

    def fetchall(self):
        rows, self._rows = self._rows, []
        return rows

    def fetchone(self):
        return self._rows.pop(0) if self._rows else None

    def close(self):
        pass


class FakeConnection:
    def __init__(self, responses):
        self.responses = list(responses)
        self.executed = []
        self.closed = False
        self.timeout = None

    def cursor(self):
        return FakeCursor(self)

    def close(self):
        self.closed = True


def load_fixture(name):
    with open(os.path.join(FIXTURES, name + ".json"), encoding="utf-8") as fh:
        return json.load(fh)


def connection_from_fixture(name):
    doc = load_fixture(name)
    return FakeConnection([
        ("backupmediafamily", doc["backups"]),
        ("sys.databases", doc["databases"]),
        ("GETDATE()", [{"server_time": doc["server_time"], "server_name": doc["server_name"]}]),
        ("backupfile", doc.get("files", [])),
    ])
