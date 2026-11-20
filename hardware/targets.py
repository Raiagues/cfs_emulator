"""Read the operator's last explicit target selection."""
import json
from pathlib import Path

from journey import TARGETS


def selected_target(root, *, required=False):
    try:
        selected = json.loads((Path(root) / "hardware/.runtime/target.json").read_text())["target"]
    except FileNotFoundError:
        if required:
            raise ValueError("Choose an execution target or pass --target.") from None
        return None
    if selected not in TARGETS:
        raise ValueError("Invalid saved execution target")
    return selected
