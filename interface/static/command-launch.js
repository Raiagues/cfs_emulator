// The compiled catalog and the process on the selected target must describe the same build.
export function commandLaunchStep(state, intent, busy = null) {
 const target = intent.target;
 const hardware = state.hardware;
 const build = state.workspace?.builds?.[target];
 if (!hardware || !build) return {label:'Checking target'};
 if (busy) {
  const labels = {stop:'Stopping cFS',build:'Building cFS',run:'Starting cFS',boot:'Starting emulator',probe:'Checking board'};
  return {label:labels[busy.action] || 'Operation running'};
 }
 const running = hardware.execution.running_targets || [];
 if (hardware.execution.conflict) return {label:'Multiple cFS instances', action:'check'};
 if (running.some(other => other !== target)) return {label:'View active flight', action:'active'};
 const deployed = hardware.deployed?.[target];
 const current = build.exists && build.current;
 if (running.includes(target) && (!current || !deployed || deployed.stopped_at || deployed.fingerprint !== build.fingerprint)) {
  return {label:'Stop previous build', action:'stop'};
 }
 if (!current) return {label:'Build cFS', action:'build'};
 if (!running.includes(target)) {
  if (target === 'qemu' && !hardware.qemu.linux_ready) {
   if (!hardware.docker.available || !hardware.qemu.ssh_configured || hardware.qemu.image_ready === false) return {label:'Emulator setup', action:'setup'};
   return {label:'Start emulator', action:'boot'};
  }
  if (target === 'physical' && !hardware.physical.last_probe?.connected) return {label:'Board setup', action:'setup'};
  if (!hardware.execution.can_start) return {label:'Check target', action:'check'};
  return {label:'Start cFS', action:'run'};
 }
 if (state.catalogLoading) return {label:'Reading catalog'};
 if (state.catalogTarget !== target || state.catalog?.build_fingerprint !== build.fingerprint) return {label:'Load command', action:'catalog'};
 if (!state.catalog.commands.some(cmd => cmd.app === intent.app && cmd.id === intent.id)) return {label:'Inspect command', action:'source'};
 return null;
}
