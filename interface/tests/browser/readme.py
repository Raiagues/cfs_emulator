"""Verify the terminal examples after the clean-login browser has released cFS."""
import os
import pty
import selectors
import time
from pathlib import Path
import subprocess
import sys
import tempfile
from urllib.request import urlopen


def command(args, cwd=None, expected=None):
    result = subprocess.run(args, cwd=cwd, text=True, stdout=subprocess.PIPE, check=True)
    last = result.stdout.strip().splitlines()
    last = last[-1] if last else ''
    if expected and expected not in last:
        raise ValueError(f"{args}: expected {expected} in {last}")
    print(f"{' '.join(args)} → {last[:180]}", flush=True)
    return result.stdout


def cli(*args, expected=None):
    return command(["./start", "--no-ui", *args], expected=expected)


def serve(argv, file, expected):
    with subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True) as server:
        try:
            # The Studio prints its address after listen().
            first = server.stdout.readline()
            if not first or server.poll() is not None:
                raise RuntimeError(first)
            with urlopen(file, timeout=15) as response:
                assert expected in response.read(), file
            print(f"{' '.join(argv)} → {file} HTTP 200", flush=True)
        finally:
            server.terminate()
            server.wait()


def standalone():
    with tempfile.TemporaryDirectory(dir=Path.home()) as directory:
        command(["git", "clone", "https://github.com/nasa/cFS.git"], directory)
        repo = Path(directory) / "cFS"
        command(["git", "checkout", "a4d305dc06fb7d468f5b45214d9f730b97d4bd77"], repo)
        command(["git", "submodule", "update", "--init", "--recursive"], repo)
        command(["make", "native_std.prep"], repo)
        command(["make", "native_std.install"], repo)
        sender = repo / "tools/cFS-GroundSystem/Subsystems/cmdUtil"
        command(["make"], sender)
        master, slave = pty.openpty()
        with os.fdopen(master, "rb", buffering=0) as stream, os.fdopen(slave, "wb") as console:
            with subprocess.Popen(["./core-cpu1"], cwd=repo / "build-native_std/exe/cpu1", stdout=console,
                                  stderr=subprocess.STDOUT) as cpu, selectors.DefaultSelector() as events:
                console.close()
                events.register(stream, selectors.EVENT_READ)

                def observe(message):
                    deadline = time.monotonic() + 120
                    seen = b""
                    while message.encode() not in seen:
                        if not events.select(max(0, deadline - time.monotonic())) or cpu.poll() is not None:
                            raise RuntimeError(f"Missing {message}: {seen[-2000:].decode(errors='replace')}")
                        seen += stream.read(65536)
                    print(message, flush=True)

                try:
                    observe("CFE_ES_Main entering OPERATIONAL state")
                    command(["./cmdUtil", "--host=127.0.0.1", "--port=1234", "--pktid=0x1882", "--cmdcode=0"], sender)
                    observe("SAMPLE: NOOP command")
                finally:
                    cpu.terminate()
                    cpu.wait()



def main():
    serve(["./start", "--ui", "--port", "8766"], "http://127.0.0.1:8766/welcome", b"welcome-scenes")
    cli("source", "install", expected="NASA cFS ready")
    cli("target", "native", expected="native")
    cli("setup", "--target", "native")
    cli("setup", "--target", "native", "--check", expected="Checks passed")
    cli("build", "--target", "native")
    try:
        cli("run", "--target", "native")
        cli("status", "--target", "native", expected="OPERATIONAL")
        cli("ground", "connect")
        cli("ground", "send", "to_lab", "ENABLE_OUTPUT", "--arg", "dest_IP=127.0.0.1")
        cli("ground", "send", "sample_app", "NOOP", expected="CommandCounter 0 → 1")
        cli("ground", "listen", "--count", "1")
        cli("ground", "test", "--all-noop")
    finally:
        cli("stop", "--target", "native")
    cli("app", "new", "demo_app")
    cli("library", "new", "filters")
    for stage in ("Code", "Struct", "Prototype", "Dispatch", "Events"):
        cli("project", "command-step", "demo_app", "--target", "native", "--confirm", stage)
    cli("project", "command-step", "demo_app", "--target", "native", "--line", "DEMO_APP_Data.Rate_Hz = Rate_Hz;")
    cli("project", "link-hal", "demo_app", "temp", "--device", "temp")
    cli("build", "--target", "native")
    try:
        cli("run", "--target", "native")
        cli("ground", "connect")
        cli("ground", "send", "to_lab", "ENABLE_OUTPUT", "--arg", "dest_IP=127.0.0.1")
        cli("ground", "send", "demo_app", "SET_RATE", "--arg", "Rate_Hz=17", expected="Rate set to 17 Hz")
        cli("simulate", "temp", "--target", "native", "--steps", "8")
        cli("simulate-preview", "--model", "tmp105")
        cli("simulate-preview", "--device", "temp", "--scenario", "orbit")
        cli("journey", "--target", "native")
        cli("ground", "stop")
    finally:
        cli("stop", "--target", "native")
    cli("app", "delete", "demo_app")
    cli("library", "delete", "filters")
    for group in ((), ("project",), ("signals",), ("ground",), ("setup",)):
        cli(*group, "--help")
    standalone()


if __name__ == "__main__":
    sys.path.insert(0, str(Path.cwd()))
    main()
