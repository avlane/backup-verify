# backup-verify

A command line tool for DBAs that reads the backup history SQL Server keeps in
`msdb`, compares it with the recovery point targets you set, and tells you which
databases have missing or stale backups or a broken backup chain. It also writes
RESTORE VERIFYONLY and test-restore scripts for you to review and run.

It only reads from the server. Nothing is restored, verified or changed unless you
run the generated scripts yourself or pass `--execute`, which runs RESTORE
VERIFYONLY statements and nothing else.

## What it checks

For every online database that is not excluded:

* the newest full backup is younger than `full_max_age_hours`
* the newest differential (or full) is younger than `diff_max_age_hours`, if set
* the newest log backup is younger than `log_max_age_minutes` (databases in the
  SIMPLE recovery model are not expected to have log backups)
* the log backups since the latest full backup form an unbroken LSN chain, and the
  first of them covers the end of the full backup
* the newest differential is based on the latest full backup
* nothing in the restore chain is flagged damaged, and the full backup was taken
  with CHECKSUM
* copy-only backups are ignored: they do not count towards the targets and do not
  take part in the restore chain
* a database created less than one full-backup interval ago is reported as
  informational instead of missing its first full backup

## Install

```
pip install .
pip install ".[sqlserver]"      # adds pyodbc, needed to talk to a server
```

It needs Python 3.11 or newer and the Microsoft ODBC driver for SQL Server (version
18 by default; use `--driver "ODBC Driver 17 for SQL Server"` for 17). Driver 18
encrypts the connection by default; if the server has a self-signed certificate, add
`--trust-server-certificate`.

## Usage

```
backup-verify --server SQLPROD01 --config examples/backup-verify.toml
backup-verify --server SQLPROD01,1433 --config policy.toml --format json -o report.json
backup-verify --server SQLPROD01 --config policy.toml --format markdown -o report.md
backup-verify --server SQLPROD01 -d Sales -d Reporting
backup-verify --server SQLPROD01 --scripts-dir out/
backup-verify --server SQLPROD01 --scripts-dir out/ --stopat 2025-04-30T14:30:00
backup-verify --server SQLPROD01 --config policy.toml --execute
backup-verify --history-file history.json --config policy.toml
backup-verify --help
```

With integrated authentication the account running the tool needs `SELECT` on
`msdb.dbo.backupset`, `backupmediafamily` and `backupfile`, and `VIEW ANY DATABASE`
(`--execute` additionally needs permission to run RESTORE VERIFYONLY). For a SQL
login pass `--user NAME` and set the `BACKUP_VERIFY_PASSWORD` environment variable.

| option | meaning |
| --- | --- |
| `--server NAME` | instance to check, for example `SQLPROD01` or `SQLPROD01,1433` |
| `--history-file FILE` | read an exported JSON history instead of connecting |
| `--config FILE` | policy file, TOML or JSON |
| `-d`, `--database NAME` | only check this database (repeatable) |
| `--since-days N` | days of msdb history to read (default 35); keep it longer than your longest full backup interval |
| `--format` | `text` (default), `json` or `markdown` |
| `-o`, `--output FILE` | write the report to a file |
| `-q`, `--quiet` | print nothing on stdout when there are no findings |
| `--fail-on` | `warning` (default), `critical` or `never`: lowest severity with a non-zero exit code |
| `--scripts-dir DIR` | write `NAME.verify.sql` and `NAME.test-restore.sql` for review |
| `--restore-dir`, `--restore-prefix` | where and under which name test restores go |
| `--stopat TIME` | make the test-restore scripts a point-in-time restore (server time) |
| `--execute` | run RESTORE VERIFYONLY for the latest chain of every checked database |
| `--user`, `--driver`, `--no-encrypt`, `--trust-server-certificate` | connection options |

### Example output

```
backup-verify report for SQLPROD01
server time: 2023-03-01 08:00:00
4 database(s) checked: 2 ok, 0 with warnings, 2 critical

[CRITICAL] NewDb: NO_FULL_BACKUP - no full backup found in the history window
[CRITICAL] Sales: LOG_STALE - last log backup finished 1079 min ago (limit 90 min)
[WARNING] Sales: FULL_STALE - last full backup finished 30.9 h ago (limit 26 h)
```

That is the `stale` fixture from `tests/fixtures`, which is why the date is in 2023.

## Policy file

See `examples/backup-verify.toml`. JSON files work too:

```json
{
  "defaults": {"full_max_age_hours": 26, "log_max_age_minutes": 30},
  "databases": {"Sales": {"diff_max_age_hours": 14}, "Stage_*": {"log_max_age_minutes": null}},
  "exclude": ["tempdb", "ReportServer*"],
  "restore_test_dir": "D:\\RestoreTest"
}
```

Full and differential targets are in hours, log targets in minutes. `null` (JSON) or
`false` (TOML) switches a check off. Database sections may use wildcards; an exact
name wins over a pattern and the first matching pattern wins. Ages are measured
against the server's clock, because msdb stores local server time.

## Findings

| code | severity | meaning |
| --- | --- | --- |
| `NO_FULL_BACKUP` | critical | no usable full backup in the history window |
| `FULL_STALE` | warning, critical beyond twice the limit | newest full backup is older than the target |
| `DIFF_STALE` | warning | no differential or full backup within the differential target |
| `NO_LOG_BACKUP`, `LOG_STALE` | critical, warning | missing or old log backups |
| `LOG_CHAIN_BROKEN` | critical | a log backup does not start where the previous one ended |
| `LOG_CHAIN_NOT_ANCHORED` | critical | the first log backup after the full does not cover the end of the full |
| `DIFF_BASE_MISMATCH` | critical | the newest differential is not based on the latest full backup |
| `BACKUP_DAMAGED` | critical | a backup in the restore chain is flagged damaged |
| `NO_CHECKSUM` | warning | the full backup was taken without CHECKSUM |
| `VERIFY_FAILED` | critical | RESTORE VERIFYONLY failed under `--execute` |
| `NEW_DATABASE`, `SKIPPED_STATE` | info | recently created, or not online; not checked |

## Generated scripts

`--scripts-dir DIR` writes, for every checked database that has a usable full backup:

* `NAME.verify.sql`: one RESTORE VERIFYONLY per backup in the restore chain (latest
  full, matching differential, log backups since). `WITH CHECKSUM` is only added
  for backups that were written with checksums. Backups on virtual devices
  (third-party tools) are skipped with a comment.
* `NAME.test-restore.sql`: restores the chain as `verify_NAME` with every file moved
  under `--restore-dir`, runs `DBCC CHECKDB`, and leaves a commented-out `DROP DATABASE`.
  It never targets the source database and fails if the copy already exists.

Names and paths are quoted, so database names with brackets or quotes are safe.
Review the files, then run them in SSMS or sqlcmd.

## Exit codes

| code | meaning |
| --- | --- |
| 0 | no warnings or critical findings (or `--fail-on never`) |
| 1 | warnings only |
| 2 | at least one critical finding |
| 3 | usage, configuration, connection or query error |

## Working from an exported history

On a server where you cannot install Python, run `sql/export_history.sql` with
sqlcmd, copy the JSON file to a workstation and use `--history-file`:

```
sqlcmd -S SQLPROD01 -E -h -1 -y 0 -i sql/export_history.sql -o history.json
backup-verify --history-file history.json --config policy.toml
```

`--execute` needs a live connection and is refused with `--history-file`.

## Running it on a schedule

`examples/nightly.ps1` is a starting point for a Windows scheduled task or a SQL
Agent step. It writes the JSON report and the review scripts to a dated location and
returns the exit code of `backup-verify --fail-on critical`. With `--quiet` and
`--fail-on never` the tool prints only when something is wrong and never fails the
job, which suits a mail-on-output setup.

## Tests

The tests (`python3 -m unittest discover`) need neither pyodbc nor a server. They cover:

* the analysis rules, the restore-chain selection, the report formats and the
  script generation, with hand-built backup histories and with the fixtures in
  `tests/fixtures/`
* the command line: options, exit codes, `--scripts-dir`, `--execute` (against a
  fake connection that records the statements), `--history-file`, and the
  `python -m backup_verify` entry point
* result-row mapping in `queries.py`, using a fake cursor that returns recorded rows
* connection-string building, and `connect()` with an injected fake `pyodbc`

## Limitations

* msdb only knows about backups taken on that instance. On an availability group
  with backups on a secondary, run the check against each replica.
* If msdb history has been cleaned up (`sp_delete_backuphistory`) there may be
  nothing to compare, which looks like a missing backup.
* Backups made by third-party tools are only visible if they write to msdb.
* Filestream and in-memory OLTP containers are not handled in the test-restore script.
* RESTORE VERIFYONLY does not prove that the data can be restored. Run the
  test-restore scripts as well.

## Development

```
python3 -m unittest discover
```

See `CHANGELOG.md` for the version history.
