"""Graph validation, safe execution, persistence, and real workflow outputs."""
import copy
import io
import json
import time
import zipfile
from app.engine import Engine, csv_safe, format_name, regex_field, validate
from app.service import starter_workflow
from localdesk.safety import InputError, digest
from tests.support import AppCase, Context, ROOT

class WorkflowTests(AppCase):
    def flow(self):return starter_workflow()
    def run_demo(self,dry=True,**extra):return self.finish('run',{'id':'invoice-register','workspace':str(ROOT/'examples'),'dry_run':dry,**extra})
    def test_starter_has_valid_topological_order(self):
        nodes,parents=validate(self.flow());self.assertEqual(nodes[0]['type'],'scan');self.assertEqual(nodes[-1]['type'],'csv')
    def test_cycle_is_rejected(self):
        f=self.flow();f['edges'].append({'from':'table','to':'read'})
        with self.assertRaises(InputError):validate(f)
    def test_duplicate_id_is_rejected(self):
        f=self.flow();f['nodes'][1]['id']='input'
        with self.assertRaises(InputError):validate(f)
    def test_unknown_node_is_rejected(self):
        f=self.flow();f['nodes'][1]['type']='shell'
        with self.assertRaises(InputError):validate(f)
    def test_missing_edge_target_is_rejected(self):
        f=self.flow();f['edges'].append({'from':'input','to':'missing'})
        with self.assertRaises(InputError):validate(f)
    def test_unconnected_transform_is_rejected(self):
        f=self.flow();f['edges']=[]
        with self.assertRaises(InputError):validate(f)
    def test_too_many_nodes_are_rejected(self):
        f=self.flow();f['nodes']=f['nodes']*10
        with self.assertRaises(InputError):validate(f)
    def test_dry_run_writes_no_outputs(self):
        before=list(self.app.exports.iterdir());r=self.run_demo()
        self.assertEqual(r['record_count'],3);self.assertEqual(r['artifacts'],[])
        self.assertEqual(list(self.app.exports.iterdir()),before);self.assertEqual(len(r['planned_files']),4)
    def test_real_run_outputs_and_source_hashes(self):
        sources=list((ROOT/'examples').glob('invoice-*.txt'));before={p:digest(p) for p in sources}
        r=self.run_demo(False);self.assertEqual(len(r['artifacts']),5)
        for p,h in before.items():self.assertEqual(digest(p),h)
        csv=next(a for a in r['artifacts'] if a['name'].endswith('.csv'))
        text=self.output(csv).decode('utf-8-sig');self.assertIn('INV-1001',text);self.assertEqual(len(text.splitlines()),4)
    def test_debug_run_stops_at_selected_step(self):
        r=self.run_demo(stop_after='read');self.assertEqual(len(r['steps']),2);self.assertEqual(r['planned_files'],[])
    def test_missing_workspace_is_rejected(self):
        with self.assertRaises(InputError):self.app.post('run',{})
    def test_save_and_restore_revision(self):
        f=self.flow();f['name']='Changed name';r=self.app.post('save',{'workflow':f});self.assertEqual(r['version'],2)
        self.app.post('restore',{'id':f['id'],'revision':1});self.assertEqual(self.app.load(f['id'])['name'],'Invoice register')
        self.assertEqual(self.app.load(f['id'])['version'],3)
    def test_exported_definition_can_be_imported(self):
        r=self.app.post('export',{'id':'invoice-register'});f=json.loads(self.output(r));f['id']='imported-copy'
        self.app.post('save',{'workflow':f});self.assertEqual(self.app.load('imported-copy')['name'],'Invoice register')
    def test_extraction_returns_capture_group(self):self.assertEqual(regex_field(r'ID: (\d+)','ID: 1234'),'1234')
    def test_no_regex_match_is_empty(self):self.assertEqual(regex_field('missing','test'),'')
    def test_invalid_regex_is_rejected(self):
        with self.assertRaises(InputError):regex_field('[','text')
    def test_regex_timeout_stops_catastrophic_pattern(self):
        started=time.monotonic()
        with self.assertRaises(InputError):regex_field('(a+)+$','a'*15998+'!')
        self.assertLess(time.monotonic()-started,5)
    def test_template_cannot_create_a_folder(self):
        with self.assertRaises(InputError):format_name('../${name}',{'name':'x.txt'})
        with self.assertRaises(InputError):format_name('${missing}',{})
    def test_formula_like_csv_cells_are_escaped(self):
        for value in ['=1+2','+SUM(A1)','@cmd','-2']:
            self.assertTrue(csv_safe(value).startswith("'"))
    def test_engine_detects_source_changes(self):
        p=self.file();engine=Engine(self.workspace,None,Context(),self.app.data)
        rows,_=engine.step({'type':'scan','config':{}},[]);p.write_text('changed')
        with self.assertRaises(InputError):engine.source(rows[0])
    def test_filter_condition_merge_and_note(self):
        engine=Engine(self.workspace,None,Context(),self.app.data)
        rows=[{'source':'one','name':'a.txt','ext':'.txt','value':'yes'},{'source':'two','name':'b.csv','ext':'.csv','value':''}]
        out,_=engine.step({'type':'filter','config':{'extension':'.txt'}},rows);self.assertEqual(len(out),1)
        out,_=engine.step({'type':'condition','config':{'field':'value','operator':'empty'}},rows);self.assertEqual(out[0]['source'],'two')
        out,_=engine.step({'type':'merge'},rows+rows);self.assertEqual(len(out),2)
        out,note=engine.step({'type':'note','config':{'message':'Checked'}},rows);self.assertEqual(note,'Checked')
    def test_collision_names_are_unique_case_insensitive(self):
        engine=Engine(self.workspace,None,Context(),self.app.data)
        self.assertEqual(engine.reserve('A.txt'),'A.txt');self.assertEqual(engine.reserve('a.txt'),'a-2.txt')
    def test_zip_backup_contains_source_content(self):
        self.file('a.txt','first');self.file('b.txt','second')
        r=self.finish('run',{'id':'folder-backup','workspace':str(self.workspace),'dry_run':False})
        raw=self.output(next(a for a in r['artifacts'] if a['name'].endswith('.zip')))
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:self.assertEqual(archive.read('a.txt'),b'first')
    def test_trigger_is_off_on_startup(self):self.assertFalse(self.app.state()['trigger']['enabled'])
    def test_trigger_rejects_unsafe_interval(self):
        with self.assertRaises(InputError):self.app.post('trigger/start',{'workspace':str(self.workspace),'seconds':1})
