"""Read the operator's last explicit target selection."""
from hardware.state import RuntimeState


def selected_target(root, *, required=False):
    choice = RuntimeState(root).selection()
    if choice is None and required:
        raise ValueError("Choose an execution target or pass --target.")
    return choice.target if choice else None
