"""Command line interface for backup-verify."""
import argparse
import os
import sys
from datetime import timedelta

from . import __version__
from .analysis import analyse
from .config import Config, ConfigError, load_config
from .connection import DEFAULT_DRIVER
from .queries import fetch_backups, fetch_databases, fetch_server_time
from .report import render
from .scripts import write_scripts

EXIT_OK, EXIT_WARNING, EXIT_CRITICAL, EXIT_ERROR = 0, 1, 2, 3
DEFAULT_LOOKBACK_DAYS = 14


class _Parser(argparse.ArgumentParser):
    """argparse exits with 2 on usage errors; that code is reserved for critical findings."""

    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(EXIT_ERROR, "%s: error: %s\n" % (self.prog, message))


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
    p.add_argument("--format", choices=("text", "json", "markdown"), default="text", help="report format (default: text)")
    p.add_argument("-o", "--output", help="write the report to this file instead of stdout")
    p.add_argument("--scripts-dir", metavar="DIR",
                   help="write RESTORE VERIFYONLY scripts for review into DIR (nothing is run)")
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


def exit_code(analysis):
    counts = analysis.counts()
    if counts["critical"]:
        return EXIT_CRITICAL
    if counts["warning"]:
        return EXIT_WARNING
    return EXIT_OK


def _error(message):
    print("backup-verify: %s" % message, file=sys.stderr)
    return EXIT_ERROR


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
        now, server_name = fetch_server_time(conn)
        databases = fetch_databases(conn)
        backups = fetch_backups(conn, now - timedelta(days=DEFAULT_LOOKBACK_DAYS))
    except Exception as exc:
        return _error("query failed: %s" % exc)
    finally:
        conn.close()
    if args.database:
        wanted = {name.lower() for name in args.database}
        missing = wanted - {d.name.lower() for d in databases}
        if missing:
            return _error("database not found: %s" % ", ".join(sorted(missing)))
        databases = [d for d in databases if d.name.lower() in wanted]
    analysis = analyse(databases, backups, config, now, server=server_name or args.server)
    if args.scripts_dir:
        paths = write_scripts(args.scripts_dir, analysis.checked, backups, analysis.server, analysis.now)
        print("backup-verify: wrote %d verify script(s) to %s" % (len(paths), args.scripts_dir), file=sys.stderr)
    text = render(analysis, args.format)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(text)
    else:
        stdout.write(text)
    return exit_code(analysis)


if __name__ == "__main__":
    sys.exit(main())
