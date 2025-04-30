"""Work out which backups are needed to restore a database."""
from .model import FULL, DIFF, LOG


def group_by_database(backups):
    grouped = {}
    for b in backups:
        grouped.setdefault(b.database.lower(), []).append(b)
    return grouped


def usable(backups, kind):
    """Backups of one type that take part in the restore chain (copy-only ones do not)."""
    return [b for b in backups if b.type == kind and not b.is_copy_only]


def latest_full(backups):
    fulls = usable(backups, FULL)
    return max(fulls, key=lambda b: b.finish) if fulls else None


def restore_chain(backups, stopat=None):
    """Return [full, differential?, log, log, ...] needed to restore a database.

    Without `stopat` the chain ends at the newest log backup. With `stopat` (a
    datetime in server time) it is the chain for a point-in-time restore: the newest
    full backup that finished before that moment, a matching differential that also
    finished before it, and log backups up to and including the first one that
    finished at or after it, because that one contains the target time.

    The list is empty when the history holds no suitable full backup.
    """
    fulls = usable(backups, FULL)
    if stopat is not None:
        fulls = [b for b in fulls if b.finish <= stopat]
    if not fulls:
        return []
    full = max(fulls, key=lambda b: b.finish)
    chain = [full]
    start_lsn = full.last_lsn
    diffs = [b for b in usable(backups, DIFF)
             if b.differential_base_lsn == full.checkpoint_lsn and b.start >= full.start
             and (stopat is None or b.finish <= stopat)]
    if diffs:
        diff = max(diffs, key=lambda b: b.finish)
        chain.append(diff)
        start_lsn = diff.last_lsn
    logs = sorted((b for b in usable(backups, LOG) if b.last_lsn > start_lsn), key=lambda b: b.first_lsn)
    for log in logs:
        chain.append(log)
        if stopat is not None and log.finish >= stopat:
            break
    return chain
