"""SQL used to read backup history from msdb, and the row mapping."""
from datetime import datetime

from .model import BackupSet, DatabaseInfo

BACKUP_SQL = """
SELECT bs.backup_set_id, bs.database_name, bs.type,
       bs.backup_start_date, bs.backup_finish_date,
       bs.first_lsn, bs.last_lsn, bs.checkpoint_lsn,
       bs.database_backup_lsn, bs.differential_base_lsn,
       bs.is_copy_only, bs.has_backup_checksums, bs.is_damaged,
       bs.backup_size, bs.compressed_backup_size,
       bmf.physical_device_name, bmf.device_type
FROM msdb.dbo.backupset AS bs
JOIN msdb.dbo.backupmediafamily AS bmf ON bmf.media_set_id = bs.media_set_id
WHERE bs.backup_start_date >= ?
  AND bs.type IN ('D', 'I', 'L')
ORDER BY bs.database_name, bs.backup_start_date, bs.backup_set_id;
"""

DATABASE_SQL = """
SELECT name, recovery_model_desc, state_desc
FROM sys.databases
WHERE database_id <> 2
  AND source_database_id IS NULL
ORDER BY name;
"""


def rows_as_dicts(cursor):
    """Turn a DB-API cursor result into a list of dicts keyed by lower-case column name."""
    names = [col[0].lower() for col in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def _dt(value):
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    return value


def _opt_int(value):
    return None if value is None else int(value)


def backup_from_row(row):
    return BackupSet(
        backup_set_id=int(row["backup_set_id"]),
        database=row["database_name"],
        type=row["type"],
        start=_dt(row["backup_start_date"]),
        finish=_dt(row["backup_finish_date"]),
        first_lsn=int(row["first_lsn"]),
        last_lsn=int(row["last_lsn"]),
        checkpoint_lsn=int(row["checkpoint_lsn"] or 0),
        database_backup_lsn=int(row["database_backup_lsn"] or 0),
        differential_base_lsn=_opt_int(row["differential_base_lsn"]),
        is_copy_only=bool(row["is_copy_only"]),
        has_checksum=bool(row["has_backup_checksums"]),
        is_damaged=bool(row["is_damaged"]),
        size_bytes=int(row["backup_size"] or 0),
        devices=[row["physical_device_name"]],
    )


def fetch_backups(conn, since):
    """Return BackupSet objects for backups that started on or after `since`."""
    cur = conn.cursor()
    try:
        cur.execute(BACKUP_SQL, since)
        return [backup_from_row(row) for row in rows_as_dicts(cur)]
    finally:
        cur.close()


def fetch_databases(conn):
    cur = conn.cursor()
    try:
        cur.execute(DATABASE_SQL)
        return [
            DatabaseInfo(row["name"], row["recovery_model_desc"], row["state_desc"])
            for row in rows_as_dicts(cur)
        ]
    finally:
        cur.close()
