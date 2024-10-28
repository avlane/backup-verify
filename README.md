# backup-verify

A small command line tool for DBAs that reads the backup history SQL Server keeps
in `msdb`, compares it with the recovery point targets you set, and tells you which
databases have missing or stale backups or a broken backup chain. It can also
write RESTORE VERIFYONLY and test-restore scripts for you to review and run.

It only reads from the server. Nothing is restored, verified or changed unless you
run the generated scripts yourself.

## What it checks

For every online database that is not excluded:

* the newest full backup is younger than `full_max_age_hours`
* the newest differential (or full) is younger than `diff_max_age_hours`, if set
* the newest log backup is younger than `log_max_age_minutes` (databases in the
  SIMPLE recovery model are not expected to have log backups)
* the log backups form an unbroken LSN chain (`first_lsn` of each backup equals
  `last_lsn` of the previous one)
* copy-only backups are ignored: they do not reset the differential base and
  do not count towards the full backup target

## Install

```
pip install .
pip install ".[sqlserver]"      # adds pyodbc, needed to talk to a server
```

It needs Python 3.11 or newer and the Microsoft ODBC driver for SQL Server
(version 18 by default; use `--driver "ODBC Driver 17 for SQL Server"` for 17).
Driver 18 encrypts the connection by default. If the server has a self-signed
certificate, add `--trust-server-certificate`.

## Usage

```
backup-verify --server SQLPROD01 --config examples/backup-verify.toml
backup-verify --server SQLPROD01,1433 --config policy.toml --format json -o report.json
backup-verify --server SQLPROD01 --config policy.toml --format markdown -o report.md
backup-verify --server SQLPROD01 -d Sales -d Reporting
backup-verify --server SQLPROD01 --scripts-dir out/
backup-verify --help
```

With integrated authentication the account running the tool needs `SELECT` on
`msdb.dbo.backupset`, `backupmediafamily` and `backupfile`, and `VIEW ANY DATABASE`.
For a SQL login pass `--user NAME` and set `BACKUP_VERIFY_PASSWORD`.

### Example output

```
backup-verify report for SQLPROD01
server time: 2023-03-01 08:00:00
4 database(s) checked: 2 ok, 0 with warnings, 2 critical

[CRITICAL] NewDb: NO_FULL_BACKUP - no full backup found in the history window
[CRITICAL] NewDb: NO_LOG_BACKUP - no log backup found in the history window
[CRITICAL] Sales: LOG_STALE - last log backup finished 1079 min ago (limit 90 min)
[WARNING] Sales: FULL_STALE - last full backup finished 30.9 h ago (limit 26 h)
```

(That is the `stale` fixture from `tests/fixtures`, which is why the date is in 2023.)

## Policy file

See `examples/backup-verify.toml`. JSON files work too:

```json
{
  "defaults": {"full_max_age_hours": 26, "log_max_age_minutes": 30},
  "databases": {"Sales": {"diff_max_age_hours": 14}},
  "exclude": ["tempdb"]
}
```

## Generated scripts

`--scripts-dir DIR` writes, for every checked database that has a usable full
backup, `NAME.verify.sql` with one RESTORE VERIFYONLY per backup in the restore
chain (latest full, matching differential, log backups since). Review the file and
run it in SSMS or sqlcmd.

## Exit codes

| code | meaning |
| --- | --- |
| 0 | no warnings or critical findings |
| 1 | warnings only |
| 2 | at least one critical finding |
| 3 | usage, configuration, connection or query error |

## Development

```
python3 -m unittest discover
```

## Working from an exported history

On a server where you cannot install Python, run `sql/export_history.sql` with
sqlcmd, copy the JSON file to a workstation and use `--history-file`:

```
sqlcmd -S SQLPROD01 -E -h -1 -y 0 -i sql/export_history.sql -o history.json
backup-verify --history-file history.json --config policy.toml
```

`--execute` needs a live connection and is refused with `--history-file`.

## Tests

The tests (`python3 -m unittest discover`) need neither pyodbc nor a server. They cover:

* the analysis rules, the restore-chain selection, the report formats and the
  script generation, with hand-built backup histories and with the fixtures in
  `tests/fixtures/`
* the command line: options, exit codes, `--scripts-dir`, `--execute` (against a
  fake connection that records the statements), `--history-file`
* result-row mapping in `queries.py`, using a fake cursor that returns recorded rows
* connection-string building, and `connect()` with an injected fake `pyodbc`

## Limitations

* msdb only knows about backups taken on that instance. On an availability group
  with backups on a secondary, run the check against each replica.
* If msdb history has been cleaned up (`sp_delete_backuphistory`) there may be
  nothing to compare, which looks like a missing backup.
* Backups made by third-party tools are only visible if they write to msdb.
* Filestream and in-memory OLTP containers are not handled in the test-restore script.
