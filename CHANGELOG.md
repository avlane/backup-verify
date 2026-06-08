# Changelog

## 0.5.0 - 2026-06-10

* Restore chains are listed in the JSON report
* Recently created databases are informational; no log findings without a full backup
* Markdown tables escape pipes and newlines
* Test-restore folder and prefix can be set in the policy file; `--since-days`
  (default 35 days) replaces the fixed 14 day window
* README rewritten, with the full list of findings and options

## 0.4.0 - 2025-08-13

* Wildcards in database sections and in `exclude`
* Log chain check looks only at the chain a restore from the latest full backup would
  use; old gaps no longer raise `LOG_CHAIN_BROKEN`, and `LOG_CHAIN_NOT_ANCHORED` is new
* `--stopat` turns the test-restore scripts into a point-in-time restore rehearsal
* URL and tape backup devices; virtual-device backups are skipped with a comment
* `--execute` only runs statements that match the exact RESTORE VERIFYONLY shape

## 0.3.0 - 2024-06-19

* `--execute` runs RESTORE VERIFYONLY for the latest chain of each database
* `--history-file` checks an exported JSON history without a connection
* `--fail-on` and `--quiet`
* Checks for differential base mismatches, damaged backups and full backups without checksums
* Markdown report, test-restore scripts, quoting of names in generated scripts

## 0.2.0 - 2023-11-14

* Policy files can be TOML; Python 3.11 or newer is required
* Backup ages are measured against the server clock

## 0.1.0 - 2023-02-08

* First version: full, differential and log age checks, log chain gaps, text and JSON reports
