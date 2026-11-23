"""Share live hardware reads and change notifications between subscribers."""
import sqlite3
import threading
import time


class Changes:
    def __init__(self):
        self.condition = threading.Condition()
        self.revision = 0
        self.topics = {}
        self.closed = False

    def publish(self, *topics):
        with self.condition:
            self.revision += 1
            self.topics.update(dict.fromkeys(topics, self.revision))
            self.condition.notify_all()

    def stream(self, cursor):
        first = True
        last = 0.0
        while True:
            with self.condition:
                if not first:
                    self.condition.wait_for(lambda: self.closed or self.revision != cursor, timeout=10)
                if self.closed:
                    return
                if not first:
                    # Coalesce bursts of log/packet notifications to one redraw per 125 ms.
                    self.condition.wait_for(lambda: self.closed, timeout=max(0, last + .125 - time.monotonic()))
                    if self.closed:
                        return
                changes = list(self.topics) if cursor > self.revision else [
                    topic for topic, revision in self.topics.items() if revision > cursor]
                cursor = self.revision
            last = time.monotonic()
            yield cursor, changes
            first = False

    def close(self):
        with self.condition:
            self.closed = True
            self.condition.notify_all()


class HardwareMonitor:
    """Run probes off the HTTP threads and share one result per refresh interval."""
    def __init__(self, hardware, events, ttl=3):
        self.hardware = hardware
        self.events = events
        self.ttl = ttl
        self.condition = threading.Condition()
        self.thread = None
        self.value = self.error = None
        self.pending = self.closed = False

    def start(self):
        with self.condition:
            if not self.thread and not self.closed:
                self.thread = threading.Thread(target=self.run, name='flight-status', daemon=True)
                self.thread.start()

    def snapshot(self):
        self.start()
        with self.condition:
            self.condition.wait_for(lambda: self.value is not None or self.error or self.closed)
            if self.error:
                raise ValueError(str(self.error))
            if self.closed:
                raise ValueError('Hardware monitor stopped')
            return self.value

    def invalidate(self):
        with self.condition:
            self.pending = True
            self.condition.notify_all()

    def run(self):
        stamps = {}
        while True:
            with self.condition:
                if self.closed:
                    return
                self.pending = False
            try:
                value = self.hardware.status()
                error = None
            except (OSError, ValueError, RuntimeError, sqlite3.OperationalError) as exc:
                value, error = None, exc
            with self.condition:
                changed = value != self.value or str(error) != str(self.error)
                self.value, self.error = value, error
                self.condition.notify_all()
            if changed:
                self.events.publish('hardware')
            paths = {'journey': self.hardware.journey.path, 'target': self.hardware.state.database}
            for topic, path in paths.items():
                try:
                    stamp = path.stat().st_mtime_ns
                    wal = path.with_name(path.name + '-wal')
                    try:
                        stamp = max(stamp, wal.stat().st_mtime_ns)
                    except FileNotFoundError:
                        pass
                except FileNotFoundError:
                    stamp = None
                if stamp != stamps.get(topic):
                    stamps[topic] = stamp
                    self.events.publish(topic)
            if value:
                signature = value['builds']['native']['fingerprint']
                if signature != stamps.get('workspace'):
                    stamps['workspace'] = signature
                    self.events.publish('workspace')
            with self.condition:
                self.condition.wait_for(lambda: self.closed or self.pending, timeout=self.ttl)

    def close(self):
        with self.condition:
            self.closed = True
            self.condition.notify_all()
        if self.thread:
            self.thread.join()
