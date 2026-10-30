import json
import socket


def execute(qmp, command, arguments=None):
    message = {"execute": command}

    if arguments is not None:
        message["arguments"] = arguments

    qmp.write((json.dumps(message) + "\n").encode())
    qmp.flush()

    response = json.loads(qmp.readline())

    if "error" in response:
        raise RuntimeError(response["error"])

    return response.get("return")


def connect(path):
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect(path)

    qmp = sock.makefile("rwb")
    qmp.readline()

    execute(qmp, "qmp_capabilities")

    return qmp


def set_property(qmp, path, name, value):
    arguments = {"path": path, "property": name, "value": value}
    execute(qmp, "qom-set", arguments)