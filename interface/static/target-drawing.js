// Shared silhouettes identify the selected execution target in Setup and First boot.
const drawings = {
  native: `<svg width="240" height="170" viewBox="0 0 240 170" fill="none" aria-hidden="true">
  <rect x="30" y="12" width="180" height="116" rx="6" stroke-width="2" fill="var(--fs-bg)" stroke="var(--fs-muted)"></rect>
  <rect x="40" y="22" width="160" height="96" rx="2" fill="var(--fs-surface)"></rect>
  <circle cx="48" cy="30" r="2" fill="var(--fs-line)"></circle><circle cx="55" cy="30" r="2" fill="var(--fs-line)"></circle><circle cx="62" cy="30" r="2" fill="var(--fs-line)"></circle>
  <rect x="48" y="42" width="44" height="5" rx="1" fill="var(--fs-code)"></rect><rect x="96" y="42" width="60" height="5" rx="1" fill="var(--fs-blue)"></rect>
  <rect x="56" y="54" width="30" height="5" rx="1" fill="var(--fs-line)"></rect><rect x="90" y="54" width="70" height="5" rx="1" fill="var(--fs-success)"></rect>
  <rect x="56" y="66" width="52" height="5" rx="1" fill="var(--fs-accent)"></rect><rect x="112" y="66" width="34" height="5" rx="1" fill="var(--fs-line)"></rect>
  <rect x="56" y="78" width="80" height="5" rx="1" fill="var(--fs-line)"></rect>
  <rect x="48" y="90" width="20" height="5" rx="1" fill="var(--fs-code)"></rect><rect x="72" y="90" width="40" height="5" rx="1" fill="var(--fs-blue)"></rect>
  <rect x="48" y="104" width="6" height="8" fill="var(--fs-accent)"></rect>
  <path d="M106 128h28l6 22h-40z" fill="var(--fs-line)"></path>
  <rect x="84" y="148" width="72" height="7" rx="3.5" fill="var(--fs-line)"></rect>
        </svg>`,
  qemu: `<svg width="240" height="170" viewBox="0 0 240 170" fill="none" aria-hidden="true">
  <path d="M12 26V12h14M214 12h14v14M228 144v14h-14M26 158H12v-14" stroke-width="1.5" stroke="var(--fs-accent)"></path>
  <g stroke-width="1.2" stroke="var(--fs-success)">
    <rect x="26" y="26" width="180" height="118" rx="8" stroke-dasharray="5 4" fill="color-mix(in srgb, var(--fs-success) 6%, transparent)"></rect>
    <circle cx="38" cy="38" r="4"></circle><circle cx="38" cy="132" r="4"></circle><circle cx="146" cy="38" r="4"></circle><circle cx="146" cy="132" r="4"></circle>
    <rect x="48" y="31" width="104" height="13"></rect>
    <rect x="94" y="72" width="40" height="40" rx="2"></rect>
    <rect x="142" y="80" width="20" height="24"></rect>
    <rect x="182" y="38" width="32" height="24"></rect>
    <rect x="182" y="70" width="32" height="24"></rect>
    <rect x="182" y="102" width="32" height="30"></rect>
    <rect x="44" y="136" width="16" height="12"></rect><rect x="68" y="138" width="12" height="10"></rect><rect x="88" y="138" width="12" height="10"></rect>
    <rect x="58" y="62" width="16" height="16"></rect>
  </g>
  <path d="M52 37.5H148" stroke-width="4" stroke-dasharray="2 2.6" opacity="0.7" stroke="var(--fs-success)"></path>
  <path d="M100 92h28M100 84h28M100 100h18" stroke-width="1" opacity="0.5" stroke="var(--fs-success)"></path>
        </svg>`,
  physical: `<svg width="240" height="170" viewBox="0 0 240 170" fill="none" aria-hidden="true">
  <path d="M196 14a18 18 0 0124 0M201 20a10 10 0 0114 0" stroke-width="1.8" stroke-linecap="round" stroke="var(--fs-accent)"></path><circle cx="208" cy="26" r="2" fill="var(--fs-accent)"></circle>
  <rect x="22" y="30" width="180" height="118" rx="8" fill="color-mix(in srgb, var(--fs-success) 55%, var(--fs-shade))" stroke="color-mix(in srgb, var(--fs-success) 75%, var(--fs-shade))"></rect>
  <circle cx="34" cy="42" r="4" fill="var(--fs-bg)" stroke="var(--fs-accent)"></circle><circle cx="34" cy="136" r="4" fill="var(--fs-bg)" stroke="var(--fs-accent)"></circle><circle cx="142" cy="42" r="4" fill="var(--fs-bg)" stroke="var(--fs-accent)"></circle><circle cx="142" cy="136" r="4" fill="var(--fs-bg)" stroke="var(--fs-accent)"></circle>
  <rect x="44" y="35" width="104" height="13" fill="color-mix(in srgb, var(--fs-success) 30%, var(--fs-shade))"></rect>
  <path d="M48 39H146M48 44.5H146" stroke-width="3" stroke-dasharray="2 2.6" stroke="var(--fs-accent)"></path>
  <rect x="90" y="76" width="40" height="40" rx="2" fill="var(--fs-muted)"></rect>
  <rect x="94" y="80" width="32" height="32" rx="1" fill="var(--fs-muted)"></rect>
  <rect x="138" y="84" width="20" height="24" fill="color-mix(in srgb, var(--fs-success) 30%, var(--fs-shade))"></rect>
  <rect x="54" y="66" width="16" height="16" fill="color-mix(in srgb, var(--fs-success) 30%, var(--fs-shade))"></rect>
  <rect x="46" y="94" width="6" height="4" fill="var(--fs-accent)"></rect><rect x="58" y="94" width="6" height="4" fill="var(--fs-accent)"></rect><rect x="46" y="104" width="6" height="4" fill="var(--fs-accent)"></rect><rect x="160" y="60" width="6" height="4" fill="var(--fs-accent)"></rect><rect x="160" y="120" width="6" height="4" fill="var(--fs-accent)"></rect>
  <rect x="178" y="42" width="34" height="24" fill="var(--fs-text)"></rect><rect x="178" y="42" width="34" height="5" fill="var(--fs-blue)"></rect>
  <rect x="178" y="74" width="34" height="24" fill="var(--fs-text)"></rect><rect x="178" y="74" width="34" height="5" fill="var(--fs-blue)"></rect>
  <rect x="178" y="106" width="34" height="30" fill="var(--fs-muted)"></rect>
  <rect x="40" y="140" width="16" height="12" rx="2" fill="var(--fs-text)"></rect><rect x="64" y="142" width="12" height="10" fill="var(--fs-text)"></rect><rect x="84" y="142" width="12" height="10" fill="var(--fs-text)"></rect><rect x="108" y="142" width="10" height="10" rx="5" fill="var(--fs-bg)"></rect>
  <circle cx="36" cy="120" r="2.5" fill="var(--fs-danger)"></circle><circle cx="36" cy="128" r="2.5" fill="var(--fs-success)"></circle>
        </svg>`,
};

export function targetDrawing(target) {
  return drawings[target] || '';
}
