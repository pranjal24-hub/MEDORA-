

import os
import queue
import threading
import time
from collections import deque


WINDOW = float(os.environ.get("BATCH_WINDOW_MS", "20")) / 1000.0
TIMEOUT = 25.0
AGING_S = float(os.environ.get("AGING_SECONDS", "5"))  # itne sec wait pr priority bdhe
RANK = {"CRITICAL": 0, "MODERATE": 1, "LOW": 2}
_UP = {"LOW": "MODERATE", "MODERATE": "CRITICAL", "CRITICAL": "CRITICAL"}


def effective(severity, waited):
    """Wait time ke hisab se request ki priority bdhao."""
    for _ in range(int(waited // AGING_S) if AGING_S > 0 else 0):
        severity = _UP.get(severity, severity)
    return severity


class _Job:
    __slots__ = ("id", "label", "severity", "arrival", "fn", "done", "result", "exc")


    def __init__(self, jid, label, severity, fn):
        self.id, self.label, self.severity, self.fn = jid, label, severity, fn
        self.arrival = time.time()
        self.done = threading.Event()
        self.result = None
        self.exc = None


class Dispatcher:
    def __init__(self):
        self.q = queue.Queue()
        self._seq = 0
        self._lock = threading.Lock()
        self.batches = deque(maxlen=50)  # recent batches ka record
        threading.Thread(target=self._run, daemon=True, name="medora-dispatcher").start()


    def submit(self, severity, fn, label=None):
        with self._lock:
            self._seq += 1
            jid = self._seq

        job = _Job(jid, label if label is not None else jid, severity, fn)
        self.q.put(job)  # request queue me dalo

        if not job.done.wait(TIMEOUT):
            raise TimeoutError("Reservation dispatcher busy")

        if job.exc is not None:
            raise job.exc

        return job.result


    def _run(self):
        while True:
            batch = [self.q.get()]  # pehli request lo

            if WINDOW > 0:
                time.sleep(WINDOW)  # thodi der aur requests ka wait

            while True:
                try:
                    batch.append(self.q.get_nowait())
                except queue.Empty:
                    break

            now = time.time()

            # severity -> accident id -> arrival time
            batch.sort(key=lambda j: (
                RANK[effective(j.severity, now - j.arrival)],
                j.label,
                j.arrival
            ))

            self.batches.append({
                "size": len(batch),
                "order": [(j.label, j.severity) for j in batch]
            })

            for job in batch:
                try:
                    job.result = job.fn()
                except BaseException as e:
                    job.exc = e  # error caller ko bhejo
                finally:
                    job.done.set()  # request complete mark kro


dispatcher = Dispatcher()