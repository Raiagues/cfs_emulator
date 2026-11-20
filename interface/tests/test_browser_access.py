import http.client
from http.server import ThreadingHTTPServer
import threading
import unittest
from unittest.mock import Mock, patch

from interface.server import Handler


class BrowserAccessTest(unittest.TestCase):
    def test_launch_cookie_separates_access_from_csrf(self):
        server = self.enterContext(ThreadingHTTPServer(('127.0.0.1', 0), Handler))
        server.studio = Mock(token='csrf', launch_key='launch', browser_session='browser')
        worker = threading.Thread(target=server.serve_forever)
        worker.start()
        self.addCleanup(worker.join)
        self.addCleanup(server.shutdown)
        with patch('interface.access.local_account', return_value=False):
            def request(path, cookie=None):
                client = http.client.HTTPConnection(*server.server_address, timeout=5)
                try:
                    client.request('GET', path, headers={'Cookie': cookie} if cookie else {})
                    response = client.getresponse()
                    return response.status, response.getheader('Set-Cookie'), response.read()
                finally:
                    client.close()

            self.assertEqual(request('/api/session')[0], 403)
            self.assertEqual(request('/?t=wrong')[0], 403)
            status, cookie, _ = request('/?t=launch')
            self.assertEqual(status, 303)
            self.assertIn('HttpOnly; SameSite=Strict', cookie)
            self.assertEqual(request('/api/session', cookie.split(';')[0]), (200, None, b'{"token": "csrf"}'))
