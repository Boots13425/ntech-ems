# Backup and recovery

The utility uses PostgreSQL custom-format dumps, Fernet encryption, SHA-256 checksums, authenticated decryption, and `pg_restore --list` archive validation. Credentials are passed through subprocess environments, never arguments. Client tools must be compatible with PostgreSQL's server version.

Set a separate `BACKUP_ENCRYPTION_KEY` in the ignored backend environment. Generate independently using `Fernet.generate_key()` as described in `.env.example`. Preserve database credentials, MFA encryption key, and backup key securely outside database archives.

From `backend`:

```powershell
.\.venv\Scripts\python.exe -m app.backup backup
.\.venv\Scripts\python.exe -m app.backup verify --file ..\backups\YOUR_BACKUP.dump.enc
```

Encrypted archives/checksums default to Git-ignored repository-root `backups/`. Restrict Windows directory ACLs; the utility sets restrictive POSIX modes on Linux. Temporary plaintext is isolated and removed when the command exits. Initial encryption runs in memory and suits small databases; larger deployments should adopt streaming backups and point-in-time recovery.

## Restore drill

Provision a separate empty PostgreSQL database. Supply `RESTORE_DATABASE_URL` securely through the environment, then:

```powershell
.\.venv\Scripts\python.exe -m app.backup restore --file ..\backups\YOUR_BACKUP.dump.enc --confirm-database EXACT_TARGET_DATABASE_NAME
```

Restore rejects the source database and targets containing public tables. It never drops existing tables. Compare revisions/counts, run health/authentication checks against the restored target, and inspect critical records before switching traffic.

`python scripts/check_restore.py`, using the backend virtual environment, creates `ntech_ems_restore_test` through local administrator access, restores a new backup, compares all model-table counts and revision, and retains it for inspection. A second run preserves the existing recovery database and requires a fresh target.

## Operational status

Manual encrypted backups and restore utilities are available. Scheduling, offsite copies, automated retention, alerts, and production recovery objectives are not configured. Before production, agree on acceptable data loss/recovery time, schedule backups, preserve keys separately, monitor failures, and exercise restoration regularly.
