// First-run links, free workspace views and browser history.
const screens = {
  boot: 'boot', event: 'ground', app: 'architecture', command: 'code', send: 'ground', sensor: 'simulation', test: 'simulation',
  architecture: 'architecture', bench: 'bench', code: 'code', ground: 'ground', simulation: 'simulation'
};
const workspace = path => /^\/studio\/?$/.test(path);

export function workspaceRoute(hash = location.hash) {
  const key = hash.replace(/^#/, '');
  const id = Object.hasOwn(screens, key) ? key : 'architecture';
  return {id, view: screens[id]};
}

export function workspaceTarget(requested, execution) {
  return [requested, execution.target, execution.preferred_target].find(target => ['native', 'qemu', 'physical'].includes(target));
}

export function requestedTarget(page = location) {
  return new URLSearchParams(page.search).get('target');
}

export function pageStep(page = location) {
  if (workspace(page.pathname)) return workspaceRoute(page.hash).id;
  return page.hash === '#board' ? 'board' : 'target';
}

export function stepUrl(step, page = location, target = null) {
  const query = target ? '?target=' + encodeURIComponent(target) : '';
  if (step === 'target') return '/' + query + '#target';
  if (step === 'board') return '/?target=physical#board';
  if (step === 'welcome') return '/welcome';
  return '/studio' + query + '#' + step;
}

// The bare entry URL resumes server evidence. Explicit setup links stay in setup.
export function landingRoute(page, snapshot, {welcomeSeen=false, sourcesReady=true}={}) {
  if(page.pathname!=='/'||page.hash||new URLSearchParams(page.search).has('target'))return null;
  if(snapshot?.target&&snapshot.current!=='target'&&sourcesReady) {
    if(snapshot.current&&snapshot.steps?.[snapshot.current]?.reachable)return snapshot.next_route||snapshot.steps[snapshot.current].route;
    if(snapshot.current===null)return stepUrl('ground',page,snapshot.target);
  }
  if(!welcomeSeen&&!snapshot?.steps?.target?.done)return stepUrl('welcome',page);
  return null;
}

export function navigate(url, replace = false) {
  if (replace) location.replace(url);
  else location.assign(url);
}

export function historyEntry() {
  return history.state || {};
}

export function recordRoute(route, extra = {}, replace = false) {
  const url = new URL(location.href);
  url.hash = route;
  if (url.href !== location.href) {
    if (replace) history.replaceState(extra, '', url);
    else history.pushState(extra, '', url);
  } else if (Object.keys(extra).length) {
    history.replaceState({...historyEntry(), ...extra}, '', url);
  }
  window.dispatchEvent(new Event('flight:navigate'));
}

export function displayTarget(target) {
  const url = new URL(location.href);
  if (target) url.searchParams.set('target', target);
  else url.searchParams.delete('target');
  history.replaceState(history.state, '', url);
}

export function redirectForStep(step, snapshot) {
  const status = snapshot.steps[step];
  if (!status || status.reachable) return null;
  return snapshot.steps[snapshot.current].route;
}

export function bindWorkspace(follow, handleError) {
  const open = () => Promise.resolve(follow()).catch(handleError);
  window.addEventListener('popstate', open);
  document.addEventListener('click', event => {
    const link = event.target.closest('a[href]');
    if (!link || event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey ||
        event.shiftKey || event.altKey || link.target || link.hasAttribute('download')) return;
    const url = new URL(link.href);
    if (url.origin !== location.origin || !workspace(url.pathname) || !url.hash || url.search !== location.search) return;
    event.preventDefault();
    recordRoute(workspaceRoute(url.hash).id);
    open();
  });
}

export function finishWelcome(target) {
  localStorage.setItem('fs-welcome', 'seen');
  navigate(stepUrl('target', location, target));
}

export function registerBrand(root = document) {
  for (const menu of root.querySelectorAll('[data-brand-menu]')) {
    for (const link of menu.querySelectorAll('[data-destination]')) {
      link.href = stepUrl(link.dataset.destination);
    }
    menu.addEventListener('keydown', event => {
      if (event.key === 'Escape') {
        menu.open = false;
        menu.querySelector('summary').focus();
      }
    });
  }
}

if (typeof document !== 'undefined') {
  registerBrand();
}
