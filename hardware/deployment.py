"""Next operator action to run the current mission on a target."""


def next_action(hardware, target):
    execution = hardware['execution']
    running = execution['running_targets']
    build = hardware['builds'][target]
    deployed = hardware['deployed'].get(target) or {}
    current = build['exists'] and build['current']
    if execution.get('conflict'):
        return {'action': 'check', 'label': 'Check running instances'}
    if any(other != target for other in running):
        return {'action': 'active', 'label': 'View active flight', 'target': execution.get('target') or running[0]}
    if target in running:
        if current and not deployed.get('stopped_at') and deployed.get('fingerprint') == build['fingerprint']:
            return None
        return {'action': 'stop', 'label': 'Stop cFS'}
    if not current:
        return {'action': 'build', 'label': 'Build cFS'}
    if target == 'qemu' and not hardware['qemu'].get('linux_ready'):
        qemu = hardware['qemu']
        if not hardware['docker']['available'] or not qemu['ssh_configured'] or qemu.get('image_ready') is False:
            return {'action': 'setup', 'label': 'Set up emulator'}
        return {'action': 'boot', 'label': 'Start emulator'}
    if target == 'physical' and not (hardware['physical'].get('last_probe') or {}).get('connected'):
        return {'action': 'setup', 'label': 'Set up board'}
    if not execution['can_start']:
        return {'action': 'check', 'label': 'Check target'}
    return {'action': 'run', 'label': 'Run cFS'}
