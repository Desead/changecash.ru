import os
import tempfile
import atexit
from filelock import FileLock, Timeout
from apscheduler.schedulers.background import BackgroundScheduler
from django.core.cache import cache
from app_main.jobs.tasks import update_crypto_prices


LOCKFILE_PATH = os.path.join(tempfile.gettempdir(), "apscheduler.lock")
CACHE_KEY = "scheduler_is_running"
CACHE_TTL = 60 * 2  # 2 минуты

scheduler = BackgroundScheduler()
lock = FileLock(LOCKFILE_PATH, timeout=0.1)  # мгновенный отказ, если занят

def start_scheduler_with_lock():
    try:
        lock.acquire(timeout=0.1)
    except Timeout:
        print("[SCHEDULER] Lock file already in use, skipping startup.")
        return

    # доп. защита — по кэшу (если Django кэш работает)
    if cache.get(CACHE_KEY):
        print("[SCHEDULER] Skipping: already marked in cache")
        lock.release()
        return

    cache.set(CACHE_KEY, True, timeout=CACHE_TTL)

    scheduler.add_job(update_crypto_prices, "interval", minutes=1)
    scheduler.start()
    print("[SCHEDULER] Started successfully.")

    def on_exit():
        print("[SCHEDULER] Shutdown. Releasing lock and cache key.")
        cache.delete(CACHE_KEY)
        lock.release()
        scheduler.shutdown()

    atexit.register(on_exit)