"""Plain data objects for msdb backup history and database state."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

FULL, DIFF, LOG = "D", "I", "L"
TYPE_NAMES = {FULL: "full", DIFF: "differential", LOG: "log"}


@dataclass
class BackupSet:
    """One row of msdb.dbo.backupset, plus the device it was written to."""

    backup_set_id: int
    database: str
    type: str
    start: datetime
    finish: datetime
    first_lsn: int
    last_lsn: int
    checkpoint_lsn: int = 0
    database_backup_lsn: int = 0
    differential_base_lsn: Optional[int] = None
    is_copy_only: bool = False
    has_checksum: bool = False
    is_damaged: bool = False
    size_bytes: int = 0
    devices: list = field(default_factory=list)

    @property
    def type_name(self):
        return TYPE_NAMES.get(self.type, self.type)


@dataclass
class DatabaseInfo:
    """A row of sys.databases, reduced to what the checks need."""

    name: str
    recovery_model: str = "FULL"
    state: str = "ONLINE"
