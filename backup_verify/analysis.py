"""Compare backup history with the policy and produce findings."""
from dataclasses import dataclass, field
from datetime import datetime

from .model import FULL, DIFF, LOG

CRITICAL = "critical"
WARNING = "warning"
INFO = "info"
SEVERITY_ORDER = {CRITICAL: 0, WARNING: 1, INFO: 2}


@dataclass
class Finding:
    database: str
    code: str
    severity: str
    message: str
    detail: dict = field(default_factory=dict)


@dataclass
class Analysis:
    server: str
    now: datetime
    checked: list
    findings: list

    def worst_by_database(self):
        worst = {}
        for f in self.findings:
            if f.severity == INFO:
                continue
            current = worst.get(f.database)
            if current is None or SEVERITY_ORDER[f.severity] < SEVERITY_ORDER[current]:
                worst[f.database] = f.severity
        return worst

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


def hours_between(later, earlier):
    return (later - earlier).total_seconds() / 3600.0


def latest(backups, kind):
    chosen = [b for b in backups if b.type == kind]
    return max(chosen, key=lambda b: b.finish) if chosen else None


def check_full(db, backups, policy, now):
    full = latest(backups, FULL)
    if full is None:
        return [Finding(db, "NO_FULL_BACKUP", CRITICAL,
                        "no full backup found in the history window")]
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
    marks = [b.finish for b in backups if b.type in (FULL, DIFF)]
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
    """Each log backup must start at the LSN where the previous one ended."""
    logs = sorted((b for b in backups if b.type == LOG), key=lambda b: b.start)
    findings = []
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


def analyse(databases, backups, config, now, server=""):
    by_db = {}
    for b in backups:
        by_db.setdefault(b.database.lower(), []).append(b)
    checked, findings = [], []
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
        findings += check_full(info.name, mine, policy, now)
        findings += check_diff(info.name, mine, policy, now)
        if info.recovery_model != "SIMPLE":
            findings += check_log(info.name, mine, policy, now)
            findings += check_log_chain(info.name, mine)
    findings.sort(key=lambda f: (SEVERITY_ORDER[f.severity], f.database.lower(), f.code))
    return Analysis(server, now, checked, findings)
