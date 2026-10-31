import contextlib
import io
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sensors.qmp import QMPError, connect
from sensors import runtime


@contextlib.contextmanager
def server(handler, greeting=None):
    errors = []
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "qmp.sock"
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(path))
        listener.listen(1)
        listener.settimeout(2)

        def run():
            try:
                connection, _ = listener.accept()
                with connection, connection.makefile("rwb") as stream:
                    def send(message):
                        stream.write((json.dumps(message) + "\n").encode())
                        stream.flush()

                    send({"QMP": {"version": {}}} if greeting is None else greeting)
                    if greeting is not None:
                        return
                    request = json.loads(stream.readline())
                    if request["execute"] != "qmp_capabilities":
                        raise AssertionError(request)
                    send({"return": {}, "id": request["id"]})
                    handler(stream, send)
            except BaseException as error:
                errors.append(error)

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        try:
            yield path
        finally:
            thread.join(3)
            listener.close()
            if thread.is_alive():
                raise AssertionError("Fake QMP server did not finish")
            if errors:
                raise errors[0]


class QMPTests(unittest.TestCase):
    def test_events_and_unrelated_replies_do_not_replace_command_result(self):
        def handler(stream, send):
            request = json.loads(stream.readline())
            self.assertEqual(request["execute"], "qom-get")
            self.assertEqual(request["arguments"]["property"], "temperature")
            send({"event": "RESET", "data": {}})
            send({"return": 999, "id": "another-request"})
            send({"return": 23500, "id": request["id"]})

        with server(handler) as path, connect(path) as qmp:
            self.assertEqual(qmp.execute("qom-get", {"property": "temperature"}), 23500)

    def test_error_is_reported_with_command_and_description(self):
        def handler(stream, send):
            request = json.loads(stream.readline())
            send({"error": {"class": "DeviceNotFound", "desc": "missing sensor"}, "id": request["id"]})

        with server(handler) as path, connect(path) as qmp:
            with self.assertRaisesRegex(QMPError, "qom-get: missing sensor"):
                qmp.execute("qom-get")

    def test_eof_during_command_is_reported(self):
        def handler(stream, _):
            stream.readline()

        with server(handler) as path, connect(path) as qmp:
            with self.assertRaisesRegex(QMPError, "closed before replying"):
                qmp.execute("qom-get")

    def test_command_has_timeout(self):
        def handler(stream, _):
            stream.readline()
            threading.Event().wait(0.15)

        with server(handler) as path, connect(path, timeout=0.05) as qmp:
            with self.assertRaisesRegex(QMPError, "timed out|Timed out"):
                qmp.execute("qom-get")

    def test_rejects_non_qmp_socket(self):
        with server(lambda *_: None, greeting={"hello": "world"}) as path:
            with self.assertRaisesRegex(QMPError, "QMP greeting"):
                connect(path)

    def test_context_manager_closes_connection(self):
        def handler(stream, _):
            self.assertEqual(stream.readline(), b"")

        with server(handler) as path:
            with connect(path) as qmp:
                self.assertIsNotNone(qmp.stream)
            self.assertIsNone(qmp.stream)
            self.assertEqual(qmp.socket.fileno(), -1)


class RuntimeCatalogTests(unittest.TestCase):
    def test_devices_lists_catalog_even_when_project_json_is_invalid(self):
        help_text = 'name "tmp105", bus i2c-bus\nname "virtio-net-pci", bus PCI\n'
        result = subprocess.CompletedProcess([], 0, stdout=help_text, stderr="")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "project").mkdir()
            (root / "project/config.json").write_text('{"devices": [')
            output = io.StringIO()
            with patch.object(sys, "argv", ["runtime.py", "--root", directory, "devices"]), \
                    patch.object(runtime.subprocess, "run", return_value=result) as query, \
                    contextlib.redirect_stdout(output):
                runtime.main()
            self.assertIn("Board: raspi4b | OS: raspios", output.getvalue())
            self.assertIn("tmp105", output.getvalue())
            self.assertNotIn("virtio-net-pci", output.getvalue())
            self.assertEqual(query.call_args.args[0],
                             ["qemu-system-aarch64", "-M", "raspi4b", "-device", "help"])

    def test_missing_installed_qemu_model_has_catalog_hint(self):
        config = {
            "schema_version": 1, "board": "raspi4b", "os": "raspios", "apps": [],
            "devices": [{"name": "Temperature", "id": "temp0", "model": "tmp105",
                         "bus": "i2c-bus.1", "address": 72, "values": {}}],
        }
        result = subprocess.CompletedProcess([], 0, stdout='name "usb-net", bus usb-bus\n', stderr="")
        with patch.object(runtime.subprocess, "run", return_value=result):
            with self.assertRaisesRegex(ValueError, r"Installed QEMU.*scripts/project\.sh devices"):
                runtime.qemu_arguments(config)


if __name__ == "__main__":
    unittest.main()
