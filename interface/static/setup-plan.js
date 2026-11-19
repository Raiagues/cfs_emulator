export const groupsByTarget = {
  native:[['Compiler','code'],['Python','terminal'],['Source','folder']],
  qemu:[['Docker','container'],['Image','cube'],['Toolchain','cpu']],
  physical:[['Network','antenna'],['SSH key','key'],['Service','power']]
};
export function groupFor(mode,label) {
  if (mode === 'native') return label === 'NASA cFS source' ? 'Source' : label.includes('Python') ? 'Python' : 'Compiler';
  if (mode === 'qemu') {
    if (/docker/i.test(label)) return 'Docker';
    return /Emulator|Local SSH/.test(label) ? 'Image' : 'Toolchain';
  }
  if (label === 'Board network') return 'Network';
  return /SSH identity|Board login|^ssh$|^scp$/.test(label) ? 'SSH key' : 'Service';
}
export function repairFor(mode,item) {
  if (item.label === 'NASA cFS source') return 'clone-cfs';
  if (item.label === 'Board network' || item.label === 'Local SSH port') return 'settings';
  if (item.label === 'Board login' || item.label === 'Board SSH identity') return 'board-key';
  if (item.label === 'cFS service') return 'board-service';
  if (item.label.startsWith('Emulator')) return 'emulator-image';
  return mode === 'native' ? 'native-tools' : 'dependencies';
}

// Host tools and sources precede image builds, key authorization and board deployment.
const repairOrder = ['native-tools','dependencies','clone-cfs','settings','emulator-image','board-key','board-service'];

export function nextRepair(target, rows, selectedGroup) {
  const failed = rows.filter(row => row.status === 'failed');
  for (const action of repairOrder) {
    const row = failed.find(item => repairFor(target,item) === action &&
      (!selectedGroup || groupFor(target,item.label) === selectedGroup));
    if (row) return {action, group:groupFor(target,row.label), label:row.label};
  }
  return null;
}
