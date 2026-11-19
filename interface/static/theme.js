(() => {
  const storageKey = 'fs-theme';
  const icons = {
    dark: 'M12 3v2m0 14v2M3 12h2m14 0h2M5.6 5.6 7 7m10 10 1.4 1.4M5.6 18.4 7 17m10-10 1.4-1.4M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z',
    light: 'M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5Z'
  };

  function apply(theme) {
    const current = theme === 'light' ? 'light' : 'dark';
    document.documentElement.dataset.theme = current;
    const next = current === 'dark' ? 'light' : 'dark';
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', current === 'dark' ? '#13171c' : '#f1eadc');
    for (const button of document.querySelectorAll('[data-theme-toggle]')) {
      button.setAttribute('aria-label', 'Switch to ' + next + ' theme');
      button.title = 'Switch to ' + next + ' theme';
      button.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="' + icons[current] + '"/></svg>';
    }
  }
  let saved = 'dark';
  try { saved = localStorage.getItem(storageKey); } catch { /* Storage may be unavailable in a private session. */ }
  apply(saved);
  document.addEventListener('DOMContentLoaded', () => apply(document.documentElement.dataset.theme));
  document.addEventListener('click', event => {
    if (!event.target.closest('[data-theme-toggle]')) return;
    const theme = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    apply(theme);
    try { localStorage.setItem(storageKey, theme); } catch { /* The selection still applies to this page. */ }
  });
  window.addEventListener('storage', event => {
    if (event.key === storageKey || event.key === null) apply(event.newValue);
  });
})();
