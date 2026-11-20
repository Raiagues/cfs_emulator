"""Resolve operator command names against the active mission's compiler catalog."""
import re


def command_for(commands, app, name):
    if not isinstance(app, str) or not isinstance(name, str):
        raise ValueError("Choose an application and command")
    name = name.upper().removesuffix('_CC')
    if app == 'to_lab' and name == 'ENABLE_OUTPUT':
        name = 'OUTPUT_ENABLE'
    matches = [item for item in commands if item['app'] == app and
               (item['id'].removesuffix('_CC') == name or item['id'].removesuffix('_CC').endswith('_' + name))]
    if len(matches) != 1:
        raise ValueError(f"Choose a command in the active {app} catalog")
    return matches[0]


def noop_event(packet, app):
    values = packet['values']
    return (not packet['errors'] and values.get('PacketID.AppName', '').casefold() == app.casefold()
            and re.search(r'\bno[ -]?op\b', str(values.get('Message', '')), re.I))
