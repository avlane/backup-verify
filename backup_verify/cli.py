"""Command line interface for backup-verify."""
import argparse
import os
import sys
from datetime import timedelta

from . import __version__
from .analysis import CRITICAL, Finding, analyse
from .chain import group_by_database
from .config import Config, ConfigError, load_config
from .connection import DEFAULT_DRIVER
from .execute import run_verify
from .queries import attach_files, fetch_backups, fetch_databases, fetch_files, fetch_server_time
from .report import render
from .scripts import DEFAULT_RESTORE_DIR, DEFAULT_RESTORE_PREFIX, write_scripts

EXIT_OK, EXIT_WARNING, EXIT_CRITICAL, EXIT_ERROR = 0, 1, 2, 3
DEFAULT_LOOKBACK_DAYS = 14


class _Parser(argparse.ArgumentParser):
    """argparse exits with 2 on usage errors; that code is reserved for critical findings."""

    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(EXIT_ERROR, "%s: error: %s\n" % (self.prog, message))


class _Failure(Exception):
    """An error that ends the run with EXIT_ERROR."""


def build_parser():
    p = _Parser(
        prog="backup-verify",
        description="Check msdb backup history against RPO targets and report broken or stale backup chains.",
        epilog="Exit codes: 0 clean, 1 warnings, 2 critical findings, 3 usage/config/connection error.",
    )
    p.add_argument("--version", action="version", version="%(prog)s " + __version__)
    p.add_argument("--server", required=True, help="instance to check, e.g. SQLPROD01 or SQLPROD01,1433")
    p.add_argument("--config", help="policy file (RPO targets per database)")
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
    p.add_argument("--restore-dir", default=DEFAULT_RESTORE_DIR,
                   help="folder for the files of a test restore (default: %(default)s)")
    p.add_argument("--restore-prefix", default=DEFAULT_RESTORE_PREFIX,
                   help="name prefix of the test-restore database (default: %(default)s)")
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
        since = now - timedelta(days=DEFAULT_LOOKBACK_DAYS)
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
            paths = write_scripts(args.scripts_dir, analysis.checked, backups, analysis.server,
                                  analysis.now, args.restore_dir, args.restore_prefix)
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
    args = build_parser().parse_args(argv)
    try:
        config = load_config(args.config) if args.config else Config()
    except ConfigError as exc:
        return _error(exc)
    try:
        conn = (connect or default_connect)(args)
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
