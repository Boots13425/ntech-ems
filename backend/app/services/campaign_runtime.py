"""Own the worker's lifecycle without requiring a separate development terminal."""
import logging
from threading import Event, Thread

logger = logging.getLogger('ntech')


class CampaignRunner:
    def __init__(self, tick, interval=15):
        self.tick = tick
        self.interval = interval
        self.stopping = Event()
        self.wakeup = Event()
        self.thread = Thread(target=self.run, name='campaign-worker', daemon=True)

    def start(self):
        self.thread.start()
        logger.info('campaign_worker_started')
        return self

    def run(self):
        while not self.stopping.is_set():
            self.wakeup.clear()
            try:
                self.tick()
            except Exception as exc:
                logger.error('campaign_worker_failure type=%s', type(exc).__name__)
            if not self.stopping.is_set():
                self.wakeup.wait(self.interval)

    def stop(self):
        self.stopping.set()
        self.wakeup.set()
        self.thread.join()
        logger.info('campaign_worker_stopped')


runner = None


def start_worker():
    global runner
    from app.campaign_worker import tick
    runner = CampaignRunner(tick).start()
    return runner


def wake_worker():
    if runner and runner.thread.is_alive():
        runner.wakeup.set()
