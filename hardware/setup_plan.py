"""Operator-facing groups and repairs for the actual probes in infrastructure."""
GROUPS = {
    "native": (("Compiler", "code"), ("Python", "terminal"), ("Source", "folder")),
    "qemu": (("Docker", "container"), ("Image", "cube"), ("SSH key", "key")),
    "physical": (("Host", "antenna"), ("User", "terminal"), ("Key", "key")),
}

ORDER = ("queue-limit", "native-tools", "dependencies", "clone-cfs", "settings", "emulator-image",
         "emulator-key", "board-key", "board-service")


def repair(target, label):
    if target == "native":
        group = {"NASA cFS source": "Source", "Python": "Python"}.get(label, "Compiler")
        action = "native-tools"
    elif target == "qemu":
        group = {"NASA cFS source": "Image", "Emulator image": "Image", "Emulator SSH identity": "SSH key",
                 "Local SSH port": "SSH key", "ssh": "SSH key", "scp": "SSH key"}.get(label, "Docker")
        action = "dependencies"
    else:
        group = {"ssh": "Key", "scp": "Key", "Board SSH identity": "Key", "Board login": "User",
                 "cFS service": "User"}.get(label, "Host")
        action = "dependencies"
    action = {"NASA cFS source": "clone-cfs", "Emulator image": "emulator-image", "Emulator SSH identity": "emulator-key",
              "Board network": "settings", "Local SSH port": "settings", "Board SSH identity": "board-key",
              "Board login": "board-key", "cFS service": "board-service", "POSIX message queues": "queue-limit"}.get(label, action)
    return {"action": action, "group": group, "priority": ORDER.index(action)}
