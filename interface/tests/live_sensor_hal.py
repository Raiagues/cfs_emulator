"""Check generated sensor HAL commands and collect distinct packets over UDP."""
import argparse
import json
from contextlib import redirect_stdout
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from interface.server import Studio


def wait_for(station, match, reason, timeout=60):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        snapshot = station.ground_snapshot()
        observed = match(snapshot)
        if observed:
            return observed
        time.sleep(0.2)
    raise RuntimeError(f"Timed out waiting for {reason}: {snapshot.get('error')}, {snapshot.get('subscription_errors')}")


def observe(studio, session, apps, expected_invalid, count):
    records = []
    contact = session["first_flight"]
    if not contact["telemetry"]:
        studio.ground_send({"command_id": contact["enable_command"],
                            "values": {"dest_IP": contact["return_host"]}})
    wait_for(studio, lambda state: state["received"], "first packet")
    for app in apps:
        descriptor = json.loads((ROOT / "project/apps" / (app + ".json")).read_text())
        def send(suffix, fields=None):
            return studio.ground_send({"command_id": app.upper() + "_" + suffix, "values": fields or {}})

        # PROCESS increments the command counter and writes to the flight syslog.
        # RESET sets a known baseline before we verify PROCESS using housekeeping.
        for suffix, signature, fields in (
                ("NOOP_CC", "NOOP command", {}),
                ("RESET_COUNTERS_CC", "RESET command", {}),
                ("PROCESS_CC", None, {}),
                ("DISPLAY_PARAM_CC", "ValU32=4312, ValI16=-27, ValStr=bench",
                 {"ValU32": 4312, "ValI16": -27, "ValStr": "bench"})):
            sent = send(suffix, fields)
            record = {"app": app, "command": sent["id"], "input": fields}
            if signature:
                def match(state):
                    return next((ev for ev in state["events"] if ev["received_at"] >= sent["sent_at"]
                                and ev["values"].get("PacketID.AppName") == app.upper()
                                and signature in ev["values"].get("Message", "")), None)
                event = wait_for(studio, match, signature)
                record.update(event=event["values"]["Message"], event_sequence=event["sequence"], at=event["received_at"])
            else:
                def hk_after(state):
                    return next((p for p in state["packets"] if p["mid"] == descriptor["hk_tlm_mid"]
                                 and p["received_at"] >= sent["sent_at"]
                                 and p["values"].get("CommandCounter") == 1
                                 and p["values"].get("CommandErrorCounter") == 0), None)
                packet = wait_for(studio, hk_after, "PROCESS housekeeping after RESET")
                record.update(housekeeping=packet["values"], sequence=packet["sequence"], at=packet["received_at"])
            records.append(record)

        for sensor in descriptor["sensors"]:
            mid = sensor["tlm_mid"]
            previous = -1
            after = sent["sent_at"]
            for _ in range(count):
                packet = wait_for(studio, lambda s: next((p for p in s["packets"]
                                  if p["mid"] == mid and p["received_at"] > after and p["sequence"] != previous), None), f"{app} MID {mid:#x}")
                values = packet["values"]
                if packet["errors"]:
                    raise RuntimeError(f"{app} decode: {packet['errors']}")
                fields = {k.split(".")[-1]: v for k, v in values.items()}
                if fields["Valid"] != int(app not in expected_invalid) or (fields["Status"] == 0) != bool(fields["Valid"]):
                    raise RuntimeError(f"{app}: {fields}")
                records.append({"app": app, "sensor": sensor["name"], "mid": mid, "sequence": packet["sequence"],
                                "at": packet["received_at"], "fields": values})
                previous = packet["sequence"]
                after = packet["received_at"]
    return records


def check(target, apps, expected_invalid, count):
    studio = Studio(ROOT)
    try:
        session = studio.ground_start({"target": target})
        records = observe(studio, session, apps, expected_invalid, count)
        return {"target": target, "build": studio.hardware.state.read("deployed.json")[target]["fingerprint"],
                "observations": records}
    finally:
        studio.ground.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=["physical", "qemu"], required=True)
    parser.add_argument("--expect-invalid", action="append", default=[], metavar="APP")
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("apps", nargs="+")
    args = parser.parse_args()
    if args.samples < 1 or not set(args.expect_invalid).issubset(args.apps):
        parser.error("Specify a positive sample count and select every expected-invalid app.")
    with redirect_stdout(sys.stderr):
        result = check(args.target, args.apps, args.expect_invalid, args.samples)
    print(json.dumps(result, indent=2))
