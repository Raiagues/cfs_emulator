"""Exercise a running Flight Studio and confirm the NASA sample app answers over UDP."""
import argparse
import json
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def check(port, target, timeout=40):
    base = f"http://127.0.0.1:{port}"
    token = json.load(urlopen(base + "/api/session", timeout=10))["token"]

    def api(path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        request = Request(base + "/api/" + path, data,
                          {"Content-Type": "application/json", "X-Studio-Token": token})
        try:
            with urlopen(request, timeout=120) as response:
                return json.load(response)
        except HTTPError as error:
            raise RuntimeError(error.read().decode()) from error

    before = api("ground")
    if before["connected"] and before.get("target") != target:
        raise RuntimeError("A different target owns the Ground Station session.")
    opened = not before["connected"]
    session = api("ground/start", {"target": target}) if opened else before
    try:
        contact = session["first_flight"]
        if not contact["automatic"] and not contact["telemetry"]:
            api("ground/send", {"target": target, "command_id": contact["enable_command"],
                                "values": {"dest_IP": contact["return_host"]}})
        # Wait for the downlink before sending. A successful send alone is not an acknowledgement.
        deadline = time.monotonic() + timeout
        while not api("ground")["receiving"]:
            if time.monotonic() >= deadline:
                raise RuntimeError("No telemetry arrived from cFS.")
            time.sleep(0.2)
        command = api("ground/send", {"target": target, "command_id": "SAMPLE_APP_NOOP_CC", "values": {}})
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status = api("ground")
            for event in status["events"]:
                values = event["values"]
                if (event["received_at"] >= command["sent_at"] and
                    values.get("PacketID.AppName") == "SAMPLE_APP" and
                    "NOOP" in str(values.get("Message", "")).upper()):
                    return {"target": target, "command": command["id"], "bytes": command["bytes"],
                            "telemetry_packets": status["received"], "event": values["Message"]}
            time.sleep(0.2)
        raise RuntimeError("No SAMPLE_APP NOOP event arrived over the downlink.")
    finally:
        if opened:
            api("ground/stop", {})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--target", choices=("native", "qemu", "physical"), default="native")
    options = parser.parse_args()
    print(json.dumps(check(options.port, options.target), indent=2))
