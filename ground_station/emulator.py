"""Receive actual TO_LAB packets from QEMU's slirp host, including on Docker Desktop."""
import selectors
import struct
import subprocess
import threading


class EmulatorReceiver:
    def __init__(self, container, port, accept, failed):
        self.container, self.port = container, port
        self.accept, self.failed = accept, failed
        self.process = self.worker = None
        self.stopping = threading.Event()

    def start(self):
        self.process = subprocess.Popen(['docker', 'exec', '-i', self.container, 'python3', '-u',
                                        '-m', 'sensors.udp_receiver', str(self.port)],
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(self.process.stdout, selectors.EVENT_READ)
                if not selector.select(timeout=10):
                    raise ValueError('Timed out opening the emulator UDP receiver')
            if self.process.stdout.read(2) != b'\0\0':
                raise ValueError(self.process.stderr.read().decode(errors='replace').strip() or 'Emulator receiver exited')
            self.worker = threading.Thread(target=self.receive, name='QEMU telemetry', daemon=True)
            self.worker.start()
        except BaseException:
            self.stop()
            raise

    def receive(self):
        try:
            stream = self.process.stdout
            while not self.stopping.is_set():
                header = stream.read(2)
                if len(header) != 2:
                    raise ValueError('Emulator telemetry receiver closed')
                size, = struct.unpack('!H', header)
                packet = stream.read(size)
                if len(packet) != size:
                    raise ValueError('Incomplete emulator telemetry datagram')
                self.accept(packet)
        except (OSError, ValueError) as error:
            if not self.stopping.is_set():
                self.failed(str(error))

    def connected(self):
        return bool(self.worker and self.worker.is_alive() and not self.stopping.is_set())

    def stop(self):
        self.stopping.set()
        if self.process:
            self.process.stdin.close()
            try:
                self.process.wait(5)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                self.process.wait()
            if self.worker:
                self.worker.join()
            self.process.stdout.close()
            self.process.stderr.close()
