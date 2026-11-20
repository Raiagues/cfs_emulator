"""Resolve direct cFS UDP paths using the configured SSH and QEMU networks."""

import ipaddress
import json
from pathlib import Path
import socket

from hardware.emulator_ssh import container_id
from hardware.infrastructure import emulator_config
from project.defaults import network, loopback


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
                         "Use a directly reachable board.") from error
    return {"host": remote, "listen_host": local, "return_host": local}


def _ssh_addresses(hardware, target, connection=None):
    argv = hardware.agent_command(target, connection, "connection")
    argv.insert(1, "-4")
    code, output = hardware._capture(argv, 15, input=Path(__file__).with_name("remote_agent.py").read_text())
    if code:
        raise ValueError("Cannot discover the board's UDP route over SSH: " + output)
    fields = json.loads(output)
    if isinstance(fields, list) and len(fields) == 4 and fields[1].isdigit() and fields[3].isdigit():
        return _ipv4(fields[0]), _ipv4(fields[2])
    raise ValueError("SSH did not report a usable IPv4 connection for the ground link.")


def _qemu_link(hardware, port):
    net = network(hardware.root)
    ident = container_id(hardware.root, emulator_config(hardware.root)["ssh_port"])
    code, output = hardware._capture(["docker", "port", ident, f"{port}/udp"], 10)
    address, separator, forwarded = output.strip().rpartition(":")
    if code or not separator or address != loopback() or not forwarded.isdigit():
        raise ValueError(f"Restart the emulator to publish this build's CI_LAB port {port}")
    return {"host": loopback(), "listen_host": loopback(), "return_host": net.guest_host,
            "command_port": int(forwarded), "receiver_container": ident}


def resolve_ground_link(hardware, target, catalog, connection=None):
    """Return command, local listener and telemetry return addresses."""
    ports = catalog.get("transport", {})
    for key in ("command_port", "telemetry_port"):
        if type(ports.get(key)) is not int or not 1 <= ports[key] <= 65535:
            raise ValueError("The compiled ground catalog has no valid UDP transport ports.")
    if target == "native":
        return dict.fromkeys(("host", "listen_host", "return_host"), loopback())
    if target == "physical":
        local, remote = _ssh_addresses(hardware, target, connection)
        return _local_route(local, remote, ports["command_port"])
    if target == "qemu":
        return _qemu_link(hardware, ports["command_port"])
    raise ValueError("Invalid ground-station target.")
