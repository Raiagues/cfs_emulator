"""Resolve direct cFS UDP paths using the configured SSH and QEMU networks."""

import ipaddress
import json
import re
import socket

from sensors.qmp import connect


def _ipv4(value):
    try:
        address = ipaddress.IPv4Address(value)
    except ipaddress.AddressValueError:
        raise ValueError("The cFS ground link requires an IPv4 address.") from None
    if address.is_unspecified or address.is_loopback or address.is_multicast or int(address) == 0xFFFFFFFF:
        raise ValueError("The cFS ground link requires a reachable, non-loopback IPv4 address.")
    return str(address)


def _local_route(local, remote, port):
    local, remote = _ipv4(local), _ipv4(remote)
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.bind((local, 0))
            # UDP connect checks the route without sending a packet.
            probe.connect((remote, port))
    except OSError as error:
        raise ValueError(f"No local UDP route from {local} to {remote}: {error}. "
                         "Use a directly reachable board or a Linux Docker bridge.") from error
    return {"host": remote, "listen_host": local, "return_host": local}


def _ssh_addresses(hardware, target, connection=None):
    argv = hardware.ssh_argv(target, connection)
    argv.insert(1, "-4")
    code, output = hardware._capture(argv + ["printf '%s\\n' \"$SSH_CONNECTION\""], 15)
    if code:
        raise ValueError("Cannot discover the board's UDP route over SSH: " + output)
    for line in output.splitlines():
        fields = line.split()
        if len(fields) == 4 and fields[1].isdigit() and fields[3].isdigit():
            return _ipv4(fields[0]), _ipv4(fields[2])
    raise ValueError("SSH did not report a usable IPv4 connection for the ground link.")


def _forwarded(info, netdev, host, guest, port):
    block = None
    for line in info.splitlines():
        header = re.match(r"\s*Hub\s+-?\d+\s+\(([^)]+)\):", line)
        if header:
            block = header.group(1)
        if block != netdev:
            continue
        fields = line.split()
        if len(fields) < 6 or fields[0] != "UDP[HOST_FORWARD]":
            continue
        if fields[2] not in (host, "0.0.0.0") or fields[3] != str(port):
            continue
        if fields[4] != guest or fields[5] != str(port):
            raise ValueError("The QEMU command port already forwards to a different guest address or port.")
        return True
    return False


def _qemu_link(hardware, port):
    code, output = hardware._capture(["docker", "inspect", "pi4-cfs"], 10)
    try:
        container = json.loads(output)[0] if not code else None
    except (ValueError, IndexError, KeyError, TypeError):
        container = None
    if not container or not container.get("State", {}).get("Running"):
        raise ValueError("Start the QEMU board before connecting the ground station.")
    networks = container.get("NetworkSettings", {}).get("Networks", {})
    routes = []
    for network in networks.values():
        if not network.get("IPAddress") or not network.get("Gateway"):
            continue
        try:
            routes.append(_local_route(network["Gateway"], network["IPAddress"], port))
        except ValueError:
            continue
    if len(routes) != 1:
        raise ValueError("Direct QEMU telemetry requires one reachable Linux Docker bridge network; "
                         "the container's IPv4 address and gateway could not be resolved unambiguously.")
    route = routes[0]
    _, guest = _ssh_addresses(hardware, "qemu")
    with connect(hardware.root / "board/qmp.sock") as qmp:
        def monitor(command):
            return qmp.execute("human-monitor-command", {"command-line": command})

        info = monitor("info usernet")
        netdevs = re.findall(r"^\s*Hub\s+-?\d+\s+\(([^)]+)\):", info, re.M)
        if len(netdevs) != 1 or not re.fullmatch(r"[\w.-]+", netdevs[0]):
            raise ValueError("QEMU must expose one identifiable user-network interface for the ground link.")
        netdev = netdevs[0]
        if not _forwarded(info, netdev, route["host"], guest, port):
            response = monitor(f"hostfwd_add {netdev} udp:{route['host']}:{port}-{guest}:{port}")
            if not _forwarded(monitor("info usernet"), netdev, route["host"], guest, port):
                raise ValueError("QEMU could not expose the cFS command UDP port: " + str(response).strip())
    return route


def resolve_ground_link(hardware, target, catalog, connection=None):
    """Return command, local listener and telemetry return addresses; never encode packets."""
    ports = catalog.get("transport", {})
    for key in ("command_port", "telemetry_port"):
        if type(ports.get(key)) is not int or not 1 <= ports[key] <= 65535:
            raise ValueError("The compiled ground catalog has no valid UDP transport ports.")
    if target == "native":
        return {"host": "127.0.0.1", "listen_host": "127.0.0.1", "return_host": "127.0.0.1"}
    if target == "physical":
        local, remote = _ssh_addresses(hardware, target, connection)
        return _local_route(local, remote, ports["command_port"])
    if target == "qemu":
        return _qemu_link(hardware, ports["command_port"])
    raise ValueError("Invalid ground-station target.")
