"""Authenticate local browsers independently of the POST anti-forgery token."""
import hmac
from http.cookies import CookieError, SimpleCookie
import ipaddress
import os
from pathlib import Path
import sys


def loopback_listener(connection):
    return all(ipaddress.ip_address(address[0]).is_loopback
               for address in (connection.getsockname(), connection.getpeername()))


def _linux_address(endpoint, ipv6):
    host, port = endpoint[:2]
    addr = ipaddress.ip_address(host)
    if ipv6 and addr.version == 4:
        addr = ipaddress.IPv6Address('::ffff:' + host)
    packed = addr.packed
    words = (int.from_bytes(packed[i:i + 4], sys.byteorder) for i in range(0, len(packed), 4))
    return ''.join(f'{word:08X}' for word in words) + f':{port:04X}'


def local_account(connection):
    if not sys.platform.startswith('linux') or not loopback_listener(connection):
        return False
    peer, local = connection.getpeername(), connection.getsockname()
    # Look up the *client* side of this established connection. The reversed
    # row is the Studio's own socket and would authorize every local account.
    for table in ('tcp', 'tcp6'):
        endpoints = [_linux_address(endpoint, table == 'tcp6') for endpoint in (peer, local)]
        try:
            rows = (Path('/proc/net') / table).read_text().splitlines()[1:]
        except (FileNotFoundError, PermissionError):
            continue
        for row in rows:
            fields = row.split()
            if fields[1:3] == endpoints and fields[3] == '01':
                return int(fields[7]) == os.getuid()
    return False


def authenticated(request):
    cookie = SimpleCookie()
    try:
        cookie.load(request.headers.get('Cookie', ''))
    except CookieError:
        return False
    entry = cookie.get('flight_session')
    secret = getattr(request.server.studio, 'browser_session', None)
    if entry and isinstance(secret, str) and hmac.compare_digest(entry.value.encode(), secret.encode()):
        return True
    return local_account(request.connection)
