// A modal owns the next action until it closes. Completed screens yield to the step bar.
export function guide(control) {
  const bar = document.querySelector('#flight-guide');
  const dialog = document.querySelector('dialog[open]');
  if (dialog && !dialog.contains(control)) control = null;
  const forward = bar?.querySelector('.flight-next:not([hidden])');
  if (forward && !dialog) control = forward;
  for (const el of document.querySelectorAll('.fs-coach')) {
    if (el !== control) el.classList.remove('fs-coach');
  }
  if (control && !control.disabled && !control.hidden) control.classList.add('fs-coach');
}
