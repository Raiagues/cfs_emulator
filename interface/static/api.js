// All Studio mutations use the same session token and Origin policy.
let session;
async function token() {
  session ??= request('session').then(response => response.json()).then(data => data.token).catch(error => {
    session = null;
    throw error;
  });
  return session;
}

export async function request(path, body, options = {}, renew = true) {
  const init = {cache:'no-store', ...options, headers:{...options.headers}};
  if (body !== undefined) {
    init.method = 'POST';
    Object.assign(init.headers, {'Content-Type':'application/json', 'X-Studio-Token':await token()});
    init.body = JSON.stringify(body);
  }
  let response;
  try {
    response = await fetch('/api/' + path, init);
  } catch (error) {
    if (error.name === 'AbortError') throw error;
    window.dispatchEvent(new CustomEvent('flight:connection', {detail:false}));
    throw Error(body === undefined ? 'Server disconnected' : 'Connection interrupted. Check the terminal before retrying.');
  }
  window.dispatchEvent(new CustomEvent('flight:connection', {detail:true}));
  if (response.status === 403 && body !== undefined && renew) {
    session = null;
    return request(path, body, options, false);
  }
  if (!response.ok) {
    const details = await response.json();
    throw Error(details.error || response.statusText);
  }
  return response;
}

export async function api(path, body, options) {
  return (await request(path, body, options)).json();
}

export function readJourney(target, board = false, options) {
  const params = new URLSearchParams();
  if (board) params.set('view', 'board');
  else if (target) params.set('target', target);
  return api('journey?' + params, undefined, options);
}
