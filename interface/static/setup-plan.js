// Both interfaces use the group, repair and prerequisite priority returned by the probes.
export function nextRepair(rows, repairs, group) {
  let next;
  for (const row of rows) {
    const plan = repairs[row.label];
    if (row.status !== 'failed' || !plan || group && plan.group !== group) continue;
    if (!next || plan.priority < next.priority) next = {...plan, label: row.label};
  }
  return next || null;
}
