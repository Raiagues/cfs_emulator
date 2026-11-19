// Activities and ordinary rail views can share a screen without starting the same task.
const screens = {
  boot: 'boot', event: 'ground', app: 'architecture', command: 'code',
  send: 'ground', sensor: 'simulation', test: 'simulation',
  architecture: 'architecture', bench: 'bench', code: 'code',
  ground: 'ground', simulation: 'simulation'
};

export function workspaceRoute(hash) {
  const key = hash.replace(/^#/, '');
  const id = Object.hasOwn(screens, key) ? key : 'architecture';
  return {id, view: screens[id]};
}

export function workspaceTarget(requested, execution) {
  const valid = ['native', 'qemu', 'physical'];
  return [requested, execution.target, execution.preferred_target].find(target => valid.includes(target));
}
