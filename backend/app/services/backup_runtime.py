"""API-owned backup worker; persisted work survives a process restart."""
import logging
from threading import Event, Thread

from app.services.backups import tick


class BackupRunner:
    def __init__(self):
        self.stopping = Event()
        self.thread = Thread(target=self.run, name='backup-worker', daemon=True)

    def start(self):
        self.thread.start()
        return self

    def run(self):
        while not self.stopping.is_set():
            try:
                tick()
            except Exception as exc:
                logging.getLogger('ntech').error('backup_worker_failure type=%s', type(exc).__name__)
            self.stopping.wait(15)

    def stop(self):
        self.stopping.set()
        self.thread.join()
