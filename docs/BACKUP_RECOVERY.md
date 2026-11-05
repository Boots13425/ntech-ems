# Backup and recovery

The utility uses PostgreSQL custom-format dumps, Fernet encryption, SHA-256 checksums, authenticated decryption, and `pg_restore --list` archive validation. Credentials are passed through subprocess environments, never arguments. Client tools must be compatible with PostgreSQL's server version.

Set a separate `BACKUP_ENCRYPTION_KEY` in the ignored backend environment. Generate independently using `Fernet.generate_key()` as described in `.env.example`. Preserve database credentials, `MFA_ENCRYPTION_KEY`, the effective `SMTP_ENCRYPTION_KEY` (if set), and the backup key securely outside database archives. Never rotate these keys without retaining the originals needed to decrypt older backups and stored credentials.

## Backup section

Sign in as CEO and open **Administration → Backup** (also linked from Settings). The page follows the existing workspace layout and provides **Back up now**, the next scheduled time, recent results, and authenticated downloads of encrypted archives and checksums. Download both files into the same folder. Only fully authenticated CEO sessions can list, request, or download backups; manual requests also require CSRF protection. Requests, results, interruptions, and downloads are audited without secret values.

The API starts an independent backup worker automatically. It checks every 15 seconds, even when no browser is open. Backups run **every Monday at 12:00 noon Africa/Douala (11:00 UTC)**. The first start initializes the next Monday slot. After initialization, a missed schedule triggers one catch-up backup on restart, not one per missed week. Manual backups do not change the Monday schedule. A failed scheduled attempt is recorded; use **Back up now** to retry after fixing the problem. The next regular attempt remains the following Monday.

Jobs are stored in PostgreSQL. Database locks serialize requests and prevent multiple API processes from running backups concurrently. Queued jobs survive restarts; a job interrupted while running becomes failed when a worker resumes. A separate worker thread keeps normal API requests responsive. Each PostgreSQL subprocess has a 30-minute timeout. The page shows configuration issues and an unavailable idle worker.

The eight most recent successfully verified module backups are retained; older registered files are removed after a successful backup, with periodic cleanup retries. Failed attempts never evict a successful backup. History remains in the database, with the latest 50 attempts shown. Standalone command-line backups are not tracked or deleted by this retention policy. Keep an off-device copy: local backups cannot protect against loss of the server or disk.

## Enable or update

1. Preserve `backend/.env` and all existing keys. Existing local setup already generates a separate backup key. Install matching PostgreSQL `pg_dump` and `pg_restore` tools and make them available on the API service account's PATH.
2. Optionally set `BACKUP_DIRECTORY` to an **absolute** private filesystem path. The default is repository-root `backups/`. Keep it outside any web/static directory and restrict Windows ACLs to the service account and recovery administrators. Allow room for the encrypted archives plus temporary dumps. All API processes must use the same host/storage and backup key.
3. From `backend`, run `.venv\Scripts\alembic.exe upgrade head` (migration `0007_backups`). From `frontend`, run `npm.cmd run build`.
4. Restart the existing application launcher/service. For this local workspace the command is `npm.cmd start -- --port 5200 --api-port 8100` from the repository root. `BACKUP_WORKER_ENABLED` defaults to `true`; keep it enabled on the active server.
5. Open Backup as CEO, create the first backup, download both files, and perform a restore drill. Keep the machine awake and the API running for scheduled work. No Windows Task Scheduler entry is required while the API is running.

From `backend`:

```powershell
.\.venv\Scripts\python.exe -m app.backup backup
.\.venv\Scripts\python.exe -m app.backup verify --file ..\backups\YOUR_BACKUP.dump.enc
```

Encrypted archives/checksums default to Git-ignored repository-root `backups/`. Restrict Windows directory ACLs; the utility sets restrictive POSIX modes on Linux. Temporary plaintext is isolated inside the private backup directory and removed on normal completion or handled failure. A hard process kill/power failure can leave a `.ntech-*` temporary directory; a recovery administrator should inspect and remove abandoned temporary data when no backup is running. Archives are published only after checksum, authenticated decryption, and archive-structure checks pass. Encryption runs in memory and suits small databases; larger deployments should adopt streaming backups and point-in-time recovery.

These are application database snapshots, not disk images: they include business records, accounts, configuration stored in the database, and audit/history tables. Source code, runtime environment files, encryption keys, operating system configuration, and PostgreSQL cluster roles are not included. Preserve the application release and recovery configuration separately. Restore tools must match the archive's PostgreSQL version. Archive validation is not a substitute for a restore drill.

## Restore drill

Provision a separate empty PostgreSQL database. Supply `RESTORE_DATABASE_URL` securely through the environment, then:

```powershell
.\.venv\Scripts\python.exe -m app.backup restore --file ..\backups\YOUR_BACKUP.dump.enc --confirm-database EXACT_TARGET_DATABASE_NAME
```

Restore rejects the source database and targets containing public tables. It never drops existing tables. Compare revisions/counts, run health/authentication checks against the restored target, and inspect critical records before switching traffic.

`python scripts/check_restore.py`, using the backend virtual environment, creates `ntech_ems_restore_test` through local administrator access, restores a new backup, compares all model-table counts and revision, and retains it for inspection. A second run preserves the existing recovery database and requires a fresh target.

For another drill, pass `--target-database ntech_ems_YYYYMMDD_restore_test` with a fresh name. Supply administrator authentication through a protected libpq password file or the `ADMIN_DATABASE_URL` environment variable; do not paste credentials into command arguments or chat. Run the count comparison while application writes are paused so changes made after the snapshot do not produce false differences.

## Operational status

Monday scheduling, manual UI backups, local retention, status history, and guarded restore utilities are implemented. Offsite replication and external failure alerts are not configured; inspect Backup history and server logs. Before production, agree on acceptable data loss/recovery time, arrange offsite copies, preserve keys separately, and exercise restoration regularly. A weekly schedule can lose up to a week of changes; use manual backups before important changes.

Implementation uses PostgreSQL's [custom-format dump and restore support](https://www.postgresql.org/docs/current/app-pgdump.html) for consistent database snapshots while the app is in use.

## Verification

From `backend`, run `.venv\Scripts\python.exe -m pytest tests/test_backups.py -q`. After a frontend build, run `.venv\Scripts\python.exe scripts/check_e2e.py --backups`. Run these sequentially: both use/reset the guarded test database. The browser suite uses a temporary backup directory and an ephemeral test key, covers login/MFA, manual backup, downloaded checksum, desktop/mobile layout, and staff denial; it never backs up the application database.
