-- Export the msdb backup history as one JSON document for
--   backup-verify --history-file history.json
--
-- Run it on the SQL Server and keep the output unwrapped, for example:
--   sqlcmd -S SQLPROD01 -E -h -1 -y 0 -i export_history.sql -o history.json
-- (SSMS splits long JSON over several rows; use sqlcmd, or "Results to File".)
--
-- Read-only. Change the number of days if you keep less or more history.

SET NOCOUNT ON;

DECLARE @since datetime = DATEADD(DAY, -35, GETDATE());

SELECT
    @@SERVERNAME AS server_name,
    CONVERT(varchar(19), GETDATE(), 126) AS server_time,
    (
        SELECT d.name, d.recovery_model_desc, d.state_desc
        FROM sys.databases AS d
        WHERE d.database_id <> 2
          AND d.source_database_id IS NULL
        ORDER BY d.name
        FOR JSON PATH
    ) AS [databases],
    (
        SELECT bs.backup_set_id, bs.database_name, bs.type,
               bs.backup_start_date, bs.backup_finish_date,
               bs.first_lsn, bs.last_lsn, bs.checkpoint_lsn,
               bs.database_backup_lsn, bs.differential_base_lsn,
               bs.is_copy_only, bs.has_backup_checksums, bs.is_damaged,
               bs.backup_size, bs.compressed_backup_size,
               bmf.physical_device_name, bmf.device_type
        FROM msdb.dbo.backupset AS bs
        JOIN msdb.dbo.backupmediafamily AS bmf ON bmf.media_set_id = bs.media_set_id
        WHERE bs.backup_start_date >= @since
          AND bs.type IN ('D', 'I', 'L')
        ORDER BY bs.database_name, bs.backup_start_date, bs.backup_set_id, bmf.family_sequence_number
        FOR JSON PATH
    ) AS backups,
    (
        SELECT bf.backup_set_id, bf.logical_name, bf.physical_name, bf.file_type
        FROM msdb.dbo.backupfile AS bf
        JOIN msdb.dbo.backupset AS bs ON bs.backup_set_id = bf.backup_set_id
        WHERE bs.backup_start_date >= @since
          AND bs.type IN ('D', 'I')
          AND bf.file_type IN ('D', 'L')
        ORDER BY bf.backup_set_id, bf.file_number
        FOR JSON PATH
    ) AS files
FOR JSON PATH, WITHOUT_ARRAY_WRAPPER;
