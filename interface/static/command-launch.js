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
 const plan = hardware.launch?.[target];
 if (plan === undefined) return {label:'Checking target'};
 if (plan) return plan;
 if (state.catalogLoading) return {label:'Reading catalog'};
 if (state.catalogTarget !== target || state.catalog?.build_fingerprint !== build.fingerprint) return {label:'Load command', action:'catalog'};
 if (!state.catalog.commands.some(cmd => cmd.app === intent.app && cmd.id === intent.id)) return {label:'Inspect command', action:'source'};
 return null;
}
