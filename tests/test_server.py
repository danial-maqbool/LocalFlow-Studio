import json
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from localflow.server import Handler

class ServerTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.httpd=ThreadingHTTPServer(('127.0.0.1',0),Handler);cls.thread=threading.Thread(target=cls.httpd.serve_forever,daemon=True);cls.thread.start();cls.base=f'http://127.0.0.1:{cls.httpd.server_port}'
 @classmethod
 def tearDownClass(cls): cls.httpd.shutdown();cls.thread.join()
 def test_status(self):
  with urllib.request.urlopen(self.base+'/api/status') as r:data=json.load(r)
  self.assertTrue(data['ok']);self.assertTrue(data['local'])
 def test_home(self):
  with urllib.request.urlopen(self.base+'/') as r:html=r.read().decode()
  self.assertIn('LocalFlow Studio',html)

if __name__=='__main__': unittest.main()
