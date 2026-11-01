// Bundled app purposes are summarized from their local cFS/apps/*/README.md.
// Custom apps use observed source capabilities, never their name or README prose.
const bundledPurposes = Object.freeze({
  cf: 'File transfer',
  ci_lab: 'Command reception',
  cs: 'Checksums',
  ds: 'Data storage',
  fm: 'File management',
  hk: 'Housekeeping',
  hs: 'Health monitoring',
  lc: 'Limit checking',
  md: 'Memory sampling',
  sc: 'Stored commands',
  sch_lab: 'Scheduling',
  to_lab: 'Telemetry output',
  sample_app: 'Example app',
  sbn: 'Software bus network',
});

export function appLabel(app) {
  const documented = bundledPurposes[app?.name];
  if (typeof documented === 'string') return documented;

  const nodes = app?.behavior?.nodes || [];
  const capabilities = new Set(nodes.flatMap(node => node.capabilities || []));
  const roles = new Set(nodes.map(node => node.role));
  const telemetry = nodes.some(node => node.role === 'publish' && node.title === 'Publish telemetry') ||
    (app?.behavior?.details?.telemetry || []).some(packet => packet.publishers?.length);

  if (capabilities.has('sensors')) return telemetry ? 'Sensor telemetry' : 'Sensor I/O';
  if (capabilities.has('network_receive') && capabilities.has('network_send')) return 'Network I/O';
  if (capabilities.has('network_receive')) return 'Network reception';
  if (capabilities.has('network_send')) return 'Network output';
  if (capabilities.has('checksums')) return 'Checksum calculation';
  if (capabilities.has('monitoring')) return 'Execution monitoring';
  if (capabilities.has('packet_assembly')) return 'Packet assembly';
  if (capabilities.has('files')) return 'File processing';
  if (capabilities.has('evaluation')) return 'Data evaluation';
  if (telemetry) return 'Telemetry publishing';
  if (roles.has('commands')) return 'Command handling';
  if (roles.has('publish')) return 'Message publishing';
  return 'Flight app';
}
