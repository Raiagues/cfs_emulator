"""Small synchronous QMP client used by the emulator's sensor tools."""

import json
import socket
import time


class QMPError(RuntimeError):
    pass


class QMPClient:
    def __init__(self, path, timeout=5.0):
        self.timeout = timeout
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.stream = None
        self.request_id = 0
        try:
            self.socket.settimeout(timeout)
            self.socket.connect(str(path))
            self.stream = self.socket.makefile("rwb")
            greeting = self._receive(time.monotonic() + timeout)
            if "QMP" not in greeting:
                raise QMPError("The socket did not return a QMP greeting")
            self.execute("qmp_capabilities")
        except BaseException:
            self.close()
            raise

    def _receive(self, deadline):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise QMPError("Timed out waiting for QMP")
        self.socket.settimeout(remaining)
        try:
            line = self.stream.readline(1024 * 1024 + 1)
        except OSError as error:
            raise QMPError(f"Cannot read QMP response: {error}") from error
        if not line:
            raise QMPError("QMP connection closed before replying")
        if len(line) > 1024 * 1024:
            raise QMPError("QMP response exceeded 1 MiB")
        try:
            message = json.loads(line)
        except (ValueError, UnicodeError) as error:
            raise QMPError("QMP returned invalid JSON") from error
        if not isinstance(message, dict):
            raise QMPError("QMP returned a message that is not an object")
        return message

    def execute(self, command, arguments=None):
        self.request_id += 1
        message = {"execute": command, "id": self.request_id}
        if arguments is not None:
            message["arguments"] = arguments
        deadline = time.monotonic() + self.timeout
        try:
            self.socket.settimeout(self.timeout)
            self.stream.write((json.dumps(message) + "\n").encode())
            self.stream.flush()
        except OSError as error:
            raise QMPError(f"Cannot send QMP command: {error}") from error
        while True:
            response = self._receive(deadline)
            if "event" in response or response.get("id") != self.request_id:
                continue
            if "error" in response:
                error = response["error"]
                raise QMPError(f"{command}: {error.get('desc', str(error))}")
            if "return" not in response:
                raise QMPError(f"QMP returned no result for {command}")
            return response["return"]

    def close(self):
        if self.stream is not None:
            self.stream.close()
            self.stream = None
        self.socket.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def connect(path, timeout=5.0):
    return QMPClient(path, timeout)


def execute(qmp, command, arguments=None):
    return qmp.execute(command, arguments)


def set_property(qmp, path, name, value):
    return execute(qmp, "qom-set", {"path": path, "property": name, "value": value})
