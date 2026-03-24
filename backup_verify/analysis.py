"""Compare backup history with the policy and produce findings."""
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from .chain import latest_full, restore_chain, usable
from .model import FULL, DIFF, LOG


class Severity(StrEnum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"

    @property
    def rank(self):
        """0 is the worst, so sorting by rank puts critical findings first."""
        return list(Severity).index(self)


CRITICAL, WARNING, INFO = Severity.CRITICAL, Severity.WARNING, Severity.INFO


@dataclass
class Finding:
    database: str
    code: str
    severity: str
    message: str
    detail: dict = field(default_factory=dict)

    def __post_init__(self):
        self.severity = Severity(self.severity)


@dataclass
class Analysis:
    server: str
    now: datetime
    checked: list
    findings: list
    chains: dict = field(default_factory=dict)  # database name -> restore chain

    def worst_by_database(self):
        worst = {}
        for f in self.findings:
            if f.severity == INFO:
                continue
            current = worst.get(f.database)
            if current is None or f.severity.rank < current.rank:
                worst[f.database] = f.severity
        return worst

    def add(self, findings):
        """Add findings (for example from --execute) and keep the list sorted."""
        self.findings.extend(findings)
        self.findings.sort(key=_sort_key)

    def counts(self):
        worst = self.worst_by_database()
        crit = sum(1 for s in worst.values() if s == CRITICAL)
        warn = sum(1 for s in worst.values() if s == WARNING)
        return {
            "databases": len(self.checked),
            "critical": crit,
            "warning": warn,
            "ok": len(self.checked) - len(worst),
        }


def _sort_key(finding):
    return (finding.severity.rank, finding.database.lower(), finding.code)


def hours_between(later, earlier):
    return (later - earlier).total_seconds() / 3600.0


def latest(backups, kind):
    chosen = usable(backups, kind)
    return max(chosen, key=lambda b: b.finish) if chosen else None


def check_full(db, backups, policy, now, created=None):
    full = latest(backups, FULL)
    if full is None:
        if created is not None and hours_between(now, created) < policy.full_max_age_hours:
            return [Finding(db, "NEW_DATABASE", INFO,
                            "created %.1f h ago; the first full backup is not due yet" % hours_between(now, created),
                            {"created": created.isoformat()})]
        copies = [b for b in backups if b.type == FULL and b.is_copy_only]
        note = " (only copy-only full backups exist, and those do not count)" if copies else ""
        return [Finding(db, "NO_FULL_BACKUP", CRITICAL,
                        "no full backup found in the history window" + note)]
    age = hours_between(now, full.finish)
    limit = policy.full_max_age_hours
    if age > limit:
        severity = CRITICAL if age > 2 * limit else WARNING
        return [Finding(db, "FULL_STALE", severity,
                        "last full backup finished %.1f h ago (limit %g h)" % (age, limit),
                        {"finished": full.finish.isoformat(), "age_hours": round(age, 1)})]
    return []


def check_diff(db, backups, policy, now):
    limit = policy.diff_max_age_hours
    if limit is None:
        return []
    marks = [b.finish for b in backups if b.type in (FULL, DIFF) and not b.is_copy_only]
    if not marks:
        return []  # reported as NO_FULL_BACKUP already
    age = hours_between(now, max(marks))
    if age > limit:
        return [Finding(db, "DIFF_STALE", WARNING,
                        "no differential or full backup for %.1f h (limit %g h)" % (age, limit),
                        {"age_hours": round(age, 1)})]
    return []


def check_log(db, backups, policy, now):
    limit = policy.log_max_age_minutes
    if limit is None:
        return []
    log = latest(backups, LOG)
    if log is None:
        return [Finding(db, "NO_LOG_BACKUP", CRITICAL,
                        "no log backup found in the history window")]
    age = (now - log.finish).total_seconds() / 60.0
    if age > limit:
        severity = CRITICAL if age > 2 * limit else WARNING
        return [Finding(db, "LOG_STALE", severity,
                        "last log backup finished %.0f min ago (limit %g min)" % (age, limit),
                        {"finished": log.finish.isoformat(), "age_minutes": round(age)})]
    return []


def check_log_chain(db, backups):
    """Check the log chain that a restore from the latest full backup would follow.

    Gaps that are older than the latest full backup are ignored. A full backup does
    not restart the log chain, but nobody restores from before it, and a broken chain
    that was repaired with a new full backup is not worth a critical finding forever.
    """
    full = latest_full(backups)
    if full is None:
        return []
    logs = sorted((b for b in usable(backups, LOG) if b.last_lsn >= full.last_lsn),
                  key=lambda b: b.first_lsn)
    findings = []
    if logs and logs[0].first_lsn > full.last_lsn:
        findings.append(Finding(
            db, "LOG_CHAIN_NOT_ANCHORED", CRITICAL,
            "the first log backup after the latest full backup (%d) starts at LSN %d, after the "
            "end of the full backup (LSN %d); restoring past the full backup is not possible" % (
                logs[0].backup_set_id, logs[0].first_lsn, full.last_lsn),
            {"full_backup_set_id": full.backup_set_id, "full_last_lsn": full.last_lsn,
             "first_log_backup_set_id": logs[0].backup_set_id, "first_log_first_lsn": logs[0].first_lsn}))
    for prev, cur in zip(logs, logs[1:]):
        if cur.first_lsn != prev.last_lsn:
            findings.append(Finding(
                db, "LOG_CHAIN_BROKEN", CRITICAL,
                "log chain broken between backup %d (%s) and %d (%s): expected first LSN %d, found %d" % (
                    prev.backup_set_id, prev.finish.strftime("%Y-%m-%d %H:%M"),
                    cur.backup_set_id, cur.start.strftime("%Y-%m-%d %H:%M"),
                    prev.last_lsn, cur.first_lsn),
                {"after_backup_set_id": prev.backup_set_id,
                 "before_backup_set_id": cur.backup_set_id,
                 "expected_first_lsn": prev.last_lsn,
                 "actual_first_lsn": cur.first_lsn,
                 "gap_from": prev.finish.isoformat(),
                 "gap_to": cur.start.isoformat()}))
    return findings


def check_diff_base(db, backups):
    """The newest differential taken after the latest full must be based on that full."""
    full = latest_full(backups)
    if full is None:
        return []
    diffs = [b for b in usable(backups, DIFF) if b.start >= full.start]
    if not diffs:
        return []
    diff = max(diffs, key=lambda b: b.finish)
    if diff.differential_base_lsn != full.checkpoint_lsn:
        return [Finding(
            db, "DIFF_BASE_MISMATCH", CRITICAL,
            "differential backup %d is not based on the latest full backup %d; "
            "a full backup that is missing from the msdb history was probably taken in between" % (
                diff.backup_set_id, full.backup_set_id),
            {"differential_backup_set_id": diff.backup_set_id,
             "full_backup_set_id": full.backup_set_id,
             "differential_base_lsn": diff.differential_base_lsn,
             "full_checkpoint_lsn": full.checkpoint_lsn})]
    return []


def check_quality(db, backups):
    """Flag damaged backups in the restore chain and a full backup without checksums."""
    chain = restore_chain(backups)
    findings = []
    for b in chain:
        if b.is_damaged:
            findings.append(Finding(
                db, "BACKUP_DAMAGED", CRITICAL,
                "%s backup %d is flagged as damaged in msdb" % (b.type_name, b.backup_set_id),
                {"backup_set_id": b.backup_set_id}))
    if chain and not chain[0].has_checksum:
        findings.append(Finding(
            db, "NO_CHECKSUM", WARNING,
            "full backup %d was taken without CHECKSUM, so page checksums were not verified "
            "when it was written" % chain[0].backup_set_id,
            {"backup_set_id": chain[0].backup_set_id}))
    return findings


def analyse(databases, backups, config, now, server=""):
    by_db = {}
    for b in backups:
        by_db.setdefault(b.database.lower(), []).append(b)
    checked, findings, chains = [], [], {}
    for info in databases:
        if config.is_excluded(info.name):
            continue
        if info.state != "ONLINE":
            findings.append(Finding(info.name, "SKIPPED_STATE", INFO,
                                    "database is %s, not checked" % info.state))
            continue
        checked.append(info.name)
        mine = sorted(by_db.get(info.name.lower(), []), key=lambda b: b.start)
        policy = config.policy_for(info.name)
        chains[info.name] = restore_chain(mine)
        findings += check_full(info.name, mine, policy, now, info.created)
        findings += check_diff(info.name, mine, policy, now)
        findings += check_diff_base(info.name, mine)
        findings += check_quality(info.name, mine)
        # log backups are impossible before the first full backup, so NO_FULL_BACKUP says it all
        if info.recovery_model != "SIMPLE" and latest_full(mine) is not None:
            findings += check_log(info.name, mine, policy, now)
            findings += check_log_chain(info.name, mine)
    findings.sort(key=_sort_key)
    return Analysis(server, now, checked, findings, chains)
