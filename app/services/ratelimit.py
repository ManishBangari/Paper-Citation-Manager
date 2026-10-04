"""Keeps our calls to arXiv at one every ARXIV_INTERVAL_SECONDS (arXiv asks for at most one per 3 seconds).

The slot is a Redis key that expires after the interval (SET NX PX is atomic), so the limit is shared by
every worker process. If Redis is down it falls back to a limiter inside this one process, so a single
server still behaves; only the cross-process sharing is lost.
"""
import threading
import time

from .. import cache

ARXIV_INTERVAL_SECONDS = 3.0
KEY = "arxiv:ratelimit"

_local_lock = threading.Lock()
_local_next = 0.0


class Busy(Exception):
    """No free slot became available within max_wait seconds."""


def wait_for_slot(max_wait: float) -> None:
    interval = ARXIV_INTERVAL_SECONDS
    if interval <= 0:
        return

    deadline = time.monotonic() + max_wait
    while True:
        got = cache.call(lambda r: r.set(KEY, "1", nx=True, px=int(interval * 1000)), default=cache.UNAVAILABLE)
        if got is cache.UNAVAILABLE:
            _wait_locally(interval, max(deadline - time.monotonic(), 0))
            return
        if got:
            return

        remaining_ms = cache.call(lambda r: r.pttl(KEY), default=cache.UNAVAILABLE)
        if remaining_ms is cache.UNAVAILABLE:
            continue        # Redis went away while we were waiting: the next loop takes the local path
        pause = max(remaining_ms, 0) / 1000 + 0.01
        if time.monotonic() + pause > deadline:
            raise Busy("no free arXiv slot")
        time.sleep(pause)


def _wait_locally(interval: float, max_wait: float) -> None:
    global _local_next
    with _local_lock:
        now = time.monotonic()
        slot = max(now, _local_next)       # threads reserve consecutive future slots
        if slot - now > max_wait:
            raise Busy("no free arXiv slot")
        _local_next = slot + interval
    if slot > now:
        time.sleep(slot - now)
