"""Answer the queries from a JSON history file instead of a live server.

The file is a single JSON object with the keys server_name, server_time,
databases, backups and (optionally) files. Each list holds one object per row
and uses the column names of the queries in queries.py. sql/export_history.sql
produces such a file on the server.
"""
import json
from datetime import datetime


class HistoryFileError(ValueError):
    """The history file is missing, unreadable or does not have the expected shape."""


_REQUIRED = ("server_name", "server_time", "databases", "backups")
_TABLES = (("backupmediafamily", "backups"), ("backupfile", "files"), ("sys.databases", "databases"))


class _Cursor:
    def __init__(self, conn):
        self.conn = conn
        self.description = None
        self._rows = []

    def execute(self, sql, *params):
        self.conn.executed.append((sql, params))
        doc = self.conn.doc
        if "GETDATE()" in sql:
            rows = [{"server_time": doc["server_time"], "server_name": doc["server_name"]}]
        else:
            for marker, key in _TABLES:
                if marker in sql:
                    rows = list(doc.get(key, []))
                    break
            else:
                raise HistoryFileError("the history file cannot answer: " + sql.strip()[:60])
            if key == "backups" and params and self.conn.filter_since:
                rows = [r for r in rows if datetime.fromisoformat(r["backup_start_date"]) >= params[0]]
        columns = list(rows[0]) if rows else []
        self.description = [(c, None, None, None, None, None, None) for c in columns]
        self._rows = [tuple(r[c] for c in columns) for r in rows]
        return self

    def fetchall(self):
        rows, self._rows = self._rows, []
        return rows

    def close(self):
        pass


class FileConnection:
    """Just enough of a DB-API connection for the read-only queries."""

    def __init__(self, doc):
        missing = [key for key in _REQUIRED if key not in doc]
        if missing:
            raise HistoryFileError("history file is missing: " + ", ".join(missing))
        self.doc = doc
        self.executed = []
        self.filter_since = True  # apply the `since` parameter to the backup rows

    def cursor(self):
        return _Cursor(self)

    def close(self):
        pass


def open_history_file(path):
    try:
        with open(path, encoding="utf-8-sig") as fh:
            doc = json.load(fh)
    except OSError as exc:
        raise HistoryFileError("cannot read %s: %s" % (path, exc)) from exc
    except json.JSONDecodeError as exc:
        raise HistoryFileError("%s is not valid JSON: %s" % (path, exc)) from exc
    if not isinstance(doc, dict):
        raise HistoryFileError("%s: the top level must be an object" % path)
    return FileConnection(doc)
