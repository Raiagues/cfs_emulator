// A deployment decision comes from the same hardware snapshot shown by the CLI.
export function deploymentControls(state) {
  const plan = state.hardware?.launch?.[state.target];
  const job = (state.jobs||[]).findLast(item=>item.target===state.target && ['run','first-boot','boot','build','stop','shutdown','probe'].includes(item.action));
  const working = job?.status==='running' && !job.operation_complete;
  const toolbar = plan && document.querySelector('.top-actions [data-job="'+CSS.escape(plan.action)+'"]:not([hidden])');
  const button = toolbar?.getClientRects().length ? toolbar : null;
  return {plan, button, working, failure: job?.status==='failed' ? job.error : ''};
}
