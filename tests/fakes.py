"""Test doubles for the DB-API connection."""
import json
import os

from backup_verify.offline import FileConnection

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.description = None
        self._rows = []

    def execute(self, sql, *params):
        self.conn.executed.append((sql, params))
        for marker, message in self.conn.failures:
            if marker in sql:
                raise RuntimeError(message)
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

    def nextset(self):
        return False

    def close(self):
        pass


class FakeConnection:
    """Answers each query from canned rows; `failures` makes matching statements raise."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.executed = []
        self.closed = False
        self.timeout = None
        self.failures = []  # (substring of the SQL, error message)

    def cursor(self):
        return FakeCursor(self)

    def close(self):
        self.closed = True


class FixtureConnection(FileConnection):
    """A history-file connection that also accepts RESTORE statements and injected failures."""

    def __init__(self, doc):
        super().__init__(doc)
        self.filter_since = False  # fixtures are small; tests pick any `since`
        self.failures = []
        self.timeout = None

    def cursor(self):
        return _FixtureCursor(self)


class _FixtureCursor:
    def __init__(self, conn):
        self.conn = conn
        self._inner = FileConnection.cursor(conn)

    @property
    def description(self):
        return self._inner.description

    def execute(self, sql, *params):
        if sql.lstrip().startswith("RESTORE"):
            self.conn.executed.append((sql, params))
            for marker, message in self.conn.failures:
                if marker in sql:
                    raise RuntimeError(message)
            return self
        for marker, message in self.conn.failures:
            if marker in sql:
                raise RuntimeError(message)
        self._inner.execute(sql, *params)
        return self

    def fetchall(self):
        return self._inner.fetchall()

    def nextset(self):
        return False

    def close(self):
        pass


def load_fixture(name):
    with open(os.path.join(FIXTURES, name + ".json"), encoding="utf-8") as fh:
        return json.load(fh)


def connection_from_fixture(name):
    return FixtureConnection(load_fixture(name))
