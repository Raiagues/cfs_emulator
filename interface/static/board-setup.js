// The Board sheet previews the physical target. Only its explicit action changes equipment.
export function boardProgress(selected, hardware, jobs, journey) {
  if (selected !== 'physical') return {action:'use',label:'Use this board'};
  const receipt=journey?.steps?.board;
  if (receipt?.observed_at && receipt.ref?.run) return {label:'OPERATIONAL',complete:true};
  if (!hardware) return {label:'Checking board'};
  const plan=hardware.launch.physical;
  const running=jobs.findLast(j=>['stop','build','run','probe'].includes(j.action) && j.status==='running' && !j.operation_complete);
  if(running) return {label:{stop:'Stopping cFS…',build:'Building cFS…',run:'Starting cFS…',probe:'Checking connection…'}[running.action]};
  if(plan?.action==='active') return {action:'stop',target:plan.target,label:'Stop cFS · '+({native:'Native',qemu:'Emulator',physical:'Board'})[plan.target]};
  if(plan?.action==='setup' || plan?.action==='check')return {action:'check',label:'Check connection'};
  return plan || {label:'Waiting for OPERATIONAL'};
}
