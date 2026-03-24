"""Builders for small, hand-made backup histories used by the unit tests."""
import itertools
from datetime import datetime, timedelta

from backup_verify.model import BackupSet, DatabaseInfo

NOW = datetime(2023, 3, 1, 8, 0, 0)
_ids = itertools.count(1)
_lsn = itertools.count(1000, 100)


def backup(db, kind, hours_ago, minutes=1, first=None, last=None, **kw):
    """A backup that finished `hours_ago` hours before NOW.

    LSNs are unique and increasing unless given explicitly.
    """
    finish = NOW - timedelta(hours=hours_ago)
    if first is None:
        first = next(_lsn)
    if last is None:
        last = first + 50
    fields = dict(
        backup_set_id=next(_ids), database=db, type=kind,
        start=finish - timedelta(minutes=minutes), finish=finish,
        first_lsn=first, last_lsn=last, checkpoint_lsn=first + 10,
        has_checksum=True, devices=["D:\\bak\\%s_%s.bak" % (db, kind)],
    )
    fields.update(kw)
    return BackupSet(**fields)


def database(name, model="FULL", state="ONLINE"):
    return DatabaseInfo(name, model, state)


FIXTURE_CONFIG = {
    "defaults": {"full_max_age_hours": 26, "log_max_age_minutes": 90},
    "databases": {
        "Sales": {"diff_max_age_hours": 20},
        "Reporting": {"log_max_age_minutes": 180},
    },
}


def analyse_fixture(name, config=None, **kwargs):
    """Run the full pipeline against tests/fixtures/<name>.json."""
    from backup_verify.analysis import analyse
    from backup_verify.config import parse_config
    from backup_verify.queries import fetch_backups, fetch_databases

    from .fakes import connection_from_fixture

    conn = connection_from_fixture(name)
    dbs = fetch_databases(conn)
    backups = fetch_backups(conn, NOW)
    cfg = parse_config(config or FIXTURE_CONFIG)
    return analyse(dbs, backups, cfg, NOW, server="SQLPROD01", **kwargs)


def codes(result):
    return sorted((f.database, f.code) for f in result.findings)


def fixture_backups(name, database):
    """All backups of one database from tests/fixtures/<name>.json, oldest first."""
    from backup_verify.queries import attach_files, fetch_backups, fetch_files

    from .fakes import connection_from_fixture

    conn = connection_from_fixture(name)
    backups = fetch_backups(conn, NOW)
    attach_files(backups, fetch_files(conn, NOW))
    return sorted((b for b in backups if b.database == database), key=lambda b: b.start)


def fixture_databases(name):
    from backup_verify.queries import fetch_databases

    from .fakes import connection_from_fixture

    return fetch_databases(connection_from_fixture(name))
