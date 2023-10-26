"""Work out which backups are needed to restore a database to its latest point."""
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


def restore_chain(backups):
    """Return [full, differential?, log, log, ...] for restoring to the most recent point.

    The list is empty when the history holds no usable full backup.
    """
    full = latest_full(backups)
    if full is None:
        return []
    chain = [full]
    start_lsn = full.last_lsn
    diffs = [b for b in usable(backups, DIFF)
             if b.differential_base_lsn == full.checkpoint_lsn and b.start >= full.start]
    if diffs:
        diff = max(diffs, key=lambda b: b.finish)
        chain.append(diff)
        start_lsn = diff.last_lsn
    logs = [b for b in usable(backups, LOG) if b.last_lsn > start_lsn]
    chain.extend(sorted(logs, key=lambda b: b.first_lsn))
    return chain
