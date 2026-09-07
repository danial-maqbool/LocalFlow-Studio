import json
import tempfile
import unittest
from pathlib import Path
from localflow.engine import WorkflowEngine, WorkflowError, validate

WF={"steps":[
 {"id":"scan","type":"scan","config":{}},
 {"id":"txt","type":"filter","config":{"pattern":"*.txt"}},
 {"id":"read","type":"read","config":{}},
 {"id":"id","type":"extract","config":{"field":"invoice_id","pattern":"Invoice ID:\\s*(INV-[0-9]+)"}},
 {"id":"name","type":"rename","config":{"template":"${invoice_id}.txt"}},
 {"id":"copy","type":"copy","config":{}},
 {"id":"csv","type":"csv","config":{"name":"register.csv","fields":["invoice_id","name"]}}
]}

class EngineTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.inbox=self.root/'in';self.out=self.root/'out';self.inbox.mkdir()
  (self.inbox/'a.txt').write_text('Invoice ID: INV-001\nTotal: 10')
  (self.inbox/'b.txt').write_text('Invoice ID: INV-002\nTotal: 20')
 def tearDown(self): self.tmp.cleanup()
 def test_validate(self): self.assertEqual(len(validate(WF)),7)
 def test_preview_writes_nothing(self):
  result=WorkflowEngine(self.inbox,None).run(WF,preview=True);self.assertEqual(len(result.records),2);self.assertFalse(self.out.exists())
 def test_run_creates_copies_and_csv(self):
  result=WorkflowEngine(self.inbox,self.out).run(WF);self.assertEqual(set(result.outputs),{'INV-001.txt','INV-002.txt','register.csv'})
 def test_source_is_not_modified(self):
  before=(self.inbox/'a.txt').read_bytes();WorkflowEngine(self.inbox,self.out).run(WF);self.assertEqual(before,(self.inbox/'a.txt').read_bytes())
 def test_rejects_path_in_output_name(self):
  bad=json.loads(json.dumps(WF));bad['steps'][4]['config']['template']='../${invoice_id}.txt'
  with self.assertRaises(WorkflowError): WorkflowEngine(self.inbox,self.out).run(bad)
 def test_requires_scan_first(self):
  with self.assertRaises(WorkflowError): validate({'steps':[{'id':'x','type':'read','config':{}}]})

if __name__=='__main__': unittest.main()
