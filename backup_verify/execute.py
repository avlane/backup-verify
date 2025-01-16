"""Run RESTORE VERIFYONLY statements against a server. Only used with --execute."""
import re
from dataclasses import dataclass

from .scripts import verify_statements


# The exact shape of the statements scripts.verify_statement() generates.
_VERIFY_ONLY = re.compile(
    r"RESTORE VERIFYONLY FROM (?:(?:DISK|URL|TAPE) = N'(?:[^']|'')*'(?:, )?)+(?: WITH CHECKSUM)?;")


def is_verify_only(sql):
    """True only for a single plain RESTORE VERIFYONLY statement."""
    return _VERIFY_ONLY.fullmatch(sql) is not None


@dataclass
class VerifyResult:
    database: str
    backup_set_id: int
    type_name: str
    ok: bool
    error: str = ""


def run_verify(conn, database, backups):
    """Run RESTORE VERIFYONLY for every backup in the database's restore chain.

    A failure is recorded and the remaining backups are still verified.
    """
    results = []
    for backup, sql in verify_statements(backups):
        if not is_verify_only(sql):
            # --execute must never run anything but RESTORE VERIFYONLY, whatever ends up in `sql`
            results.append(VerifyResult(database, backup.backup_set_id, backup.type_name, False,
                                        "refused to run a statement that is not a plain RESTORE VERIFYONLY"))
            continue
        cur = conn.cursor()
        try:
            cur.execute(sql)
            # Non-fatal errors only surface once the result sets have been consumed.
            while cur.nextset():
                pass
            ok, error = True, ""
        except Exception as exc:  # driver errors cannot be named without importing the driver
            ok, error = False, str(exc)
        finally:
            cur.close()
        results.append(VerifyResult(database, backup.backup_set_id, backup.type_name, ok, error))
    return results
