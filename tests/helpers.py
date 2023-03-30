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
