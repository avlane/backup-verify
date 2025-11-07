"""Command line interface for backup-verify."""
import argparse
import os
import sys
from datetime import datetime, timedelta

from . import __version__
from .analysis import CRITICAL, Finding, analyse
from .chain import group_by_database
from .config import Config, ConfigError, load_config
from .connection import DEFAULT_DRIVER
from .execute import run_verify
from .offline import HistoryFileError, open_history_file
from .queries import attach_files, fetch_backups, fetch_databases, fetch_files, fetch_server_time
from .report import render
from .scripts import DEFAULT_RESTORE_DIR, DEFAULT_RESTORE_PREFIX, write_scripts

EXIT_OK, EXIT_WARNING, EXIT_CRITICAL, EXIT_ERROR = 0, 1, 2, 3
DEFAULT_LOOKBACK_DAYS = 35


class _Parser(argparse.ArgumentParser):
    """argparse exits with 2 on usage errors; that code is reserved for critical findings."""

    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(EXIT_ERROR, "%s: error: %s\n" % (self.prog, message))


class _Failure(Exception):
    """An error that ends the run with EXIT_ERROR."""


def _timestamp(text):
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        raise argparse.ArgumentTypeError("not a date and time: %r (use e.g. 2025-04-30T14:30:00)" % text) from None


def _positive_days(text):
    try:
        days = int(text)
    except ValueError:
        days = 0
    if days < 1:
        raise argparse.ArgumentTypeError("must be a whole number of days, at least 1")
    return days


def build_parser():
    p = _Parser(
        prog="backup-verify",
        description="Check msdb backup history against RPO targets and report broken or stale backup chains.",
        epilog="Exit codes: 0 clean, 1 warnings, 2 critical findings, 3 usage/config/connection error.",
    )
    p.add_argument("--version", action="version", version="%(prog)s " + __version__)
    p.add_argument("--server", help="instance to check, e.g. SQLPROD01 or SQLPROD01,1433")
    p.add_argument("--history-file", metavar="FILE",
                   help="read an exported JSON history (see sql/export_history.sql) instead of connecting")
    p.add_argument("--config", help="policy file (RPO targets per database)")
    p.add_argument("--since-days", type=_positive_days, default=DEFAULT_LOOKBACK_DAYS, metavar="N",
                   help="how many days of msdb history to read (default: %(default)s); it must be longer "
                        "than your longest full backup interval")
    p.add_argument("-d", "--database", action="append", default=[], metavar="NAME",
                   help="only check this database (repeatable)")
    p.add_argument("--format", choices=("text", "json", "markdown"), default="text",
                   help="report format (default: text)")
    p.add_argument("-o", "--output", help="write the report to this file instead of stdout")
    p.add_argument("--fail-on", choices=("warning", "critical", "never"), default="warning",
                   help="lowest severity that gives a non-zero exit code (default: %(default)s)")
    p.add_argument("-q", "--quiet", action="store_true",
                   help="print nothing to stdout when there are no findings (for cron and SQL Agent jobs)")
    p.add_argument("--scripts-dir", metavar="DIR",
                   help="write RESTORE VERIFYONLY and test-restore scripts for review into DIR (nothing is run)")
    p.add_argument("--restore-dir",
                   help="folder for the files of a test restore (default: restore_test_dir from the "
                        "policy file, else %s)" % DEFAULT_RESTORE_DIR)
    p.add_argument("--restore-prefix",
                   help="name prefix of the test-restore database (default: restore_test_prefix from "
                        "the policy file, else %s)" % DEFAULT_RESTORE_PREFIX)
    p.add_argument("--stopat", type=_timestamp, metavar="TIME",
                   help="make the test-restore scripts a point-in-time restore to this server-local time")
    p.add_argument("--execute", action="store_true",
                   help="run RESTORE VERIFYONLY for the latest restore chain of every database on the server "
                        "(read-only but I/O heavy; without this flag nothing is ever run)")
    p.add_argument("--user", help="SQL login; the password is read from BACKUP_VERIFY_PASSWORD")
    p.add_argument("--driver", default=DEFAULT_DRIVER, help="ODBC driver name (default: %(default)s)")
    p.add_argument("--no-encrypt", action="store_true", help="connect without encryption")
    p.add_argument("--trust-server-certificate", action="store_true",
                   help="accept the server certificate without validating it")
    return p


def default_connect(args):
    from .connection import connect

    return connect(
        args.server,
        driver=args.driver,
        user=args.user,
        password=os.environ.get("BACKUP_VERIFY_PASSWORD"),
        encrypt=not args.no_encrypt,
        trust_server_certificate=args.trust_server_certificate,
    )


def exit_code(analysis, fail_on="warning"):
    """Map findings to an exit code; `fail_on` sets the lowest severity that counts."""
    counts = analysis.counts()
    if counts["critical"] and fail_on != "never":
        return EXIT_CRITICAL
    if counts["warning"] and fail_on == "warning":
        return EXIT_WARNING
    return EXIT_OK


def _error(message):
    print("backup-verify: %s" % message, file=sys.stderr)
    return EXIT_ERROR


def _select(databases, names):
    if not names:
        return databases
    wanted = {name.lower() for name in names}
    missing = wanted - {d.name.lower() for d in databases}
    if missing:
        raise _Failure("database not found: %s" % ", ".join(sorted(missing)))
    return [d for d in databases if d.name.lower() in wanted]


def _verify(conn, analysis, backups):
    """Run RESTORE VERIFYONLY and return a finding for every failure."""
    grouped = group_by_database(backups)
    findings = []
    for name in analysis.checked:
        for result in run_verify(conn, name, grouped.get(name.lower(), [])):
            print("backup-verify: %s: verify %s backup %d: %s" % (
                name, result.type_name, result.backup_set_id, "ok" if result.ok else "FAILED"),
                file=sys.stderr)
            if not result.ok:
                findings.append(Finding(
                    name, "VERIFY_FAILED", CRITICAL,
                    "RESTORE VERIFYONLY failed for %s backup %d: %s" % (
                        result.type_name, result.backup_set_id, result.error),
                    {"backup_set_id": result.backup_set_id}))
    return findings


def _run(args, config, conn, stdout):
    try:
        now, server_name = fetch_server_time(conn)
        databases = fetch_databases(conn)
        since = now - timedelta(days=args.since_days)
        backups = fetch_backups(conn, since)
        attach_files(backups, fetch_files(conn, since))
    except Exception as exc:
        raise _Failure("query failed: %s" % exc) from exc
    databases = _select(databases, args.database)
    analysis = analyse(databases, backups, config, now, server=server_name or args.server)
    if args.execute:
        analysis.add(_verify(conn, analysis, backups))
    if args.scripts_dir:
        try:
            restore_dir = args.restore_dir or config.restore_dir or DEFAULT_RESTORE_DIR
            restore_prefix = args.restore_prefix
            if restore_prefix is None:
                restore_prefix = config.restore_prefix or DEFAULT_RESTORE_PREFIX
            paths = write_scripts(args.scripts_dir, analysis.checked, backups, analysis.server,
                                  analysis.now, restore_dir, restore_prefix, args.stopat)
        except ValueError as exc:
            raise _Failure(exc) from exc
        print("backup-verify: wrote %d script(s) to %s" % (len(paths), args.scripts_dir), file=sys.stderr)
    text = render(analysis, args.format)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(text)
    elif analysis.findings or not args.quiet:
        stdout.write(text)
    return exit_code(analysis, args.fail_on)


def main(argv=None, connect=None, stdout=None):
    stdout = stdout or sys.stdout
    parser = build_parser()
    args = parser.parse_args(argv)
    if bool(args.server) == bool(args.history_file):
        parser.error("give exactly one of --server and --history-file")
    if args.history_file and args.execute:
        parser.error("--execute needs a live connection (--server)")
    try:
        config = load_config(args.config) if args.config else Config()
    except ConfigError as exc:
        return _error(exc)
    try:
        if args.history_file:
            conn = open_history_file(args.history_file)
        else:
            conn = (connect or default_connect)(args)
    except HistoryFileError as exc:
        return _error(exc)
    except Exception as exc:  # driver errors are not importable without the driver
        return _error("cannot connect to %s: %s" % (args.server, exc))
    try:
        return _run(args, config, conn, stdout)
    except _Failure as exc:
        return _error(exc)
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
