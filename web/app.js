import {$,$$,E,api,get,post,icon,button,badge,stats,pageHead,empty,listen,toast,modal,ask,
        showJSON,runJob,download,artifactsHTML,bindArtifacts,pickPath,jobsHTML,bindJobs,mount,when} from './common.js';
const info=await get('info');
let state,workflow,selected='input',workspace=info.example_path,lastRun=null,dirty=false,view='builder';
const defaults={ocr:{language:'eng'},tables:{strategy:'lines'},semantic:{query:'customer invoice payment',minimum_score:0.15,model_path:''},summary:{sentences:3},desktop:{actions:[{type:'wait',seconds:2}]},scan:{pattern:'*'},filter:{pattern:'*',extension:'.txt'},read:{},extract:{field:'value',pattern:'Amount:\\s*([0-9.]+)'},condition:{field:'value',operator:'not_empty',value:''},name:{template:'${stem}${ext}'},copy:{},csv:{filename:'records.csv',fields:['name','size','sha256']},json:{filename:'records.json'},archive:{filename:'archive.zip'},merge:{},note:{message:'Step complete.'}};
const nodeIcons={scan:'folder',filter:'settings',read:'file',extract:'search',condition:'check',name:'file',copy:'copy',csv:'grid',json:'file',archive:'folder',merge:'flow',note:'bookmark'};
const guide=`<p>Start with the Invoice register workflow. It uses the included synthetic invoices.</p><ol class="list-note"><li>Select a workspace folder.</li><li>Select Preview plan. No output files are written.</li><li>Check the step results and proposed file names.</li><li>Select Create outputs. The app writes new copies under its private data folder.</li></ol><p class="muted small">Use the right panel to edit a selected node. Save a definition to keep a revision. File nodes create new copies. Confirmed desktop input can change the focused application and its files.</p>`;

async function refresh(){state=await get('state');}
function syncInputs(){if($('#workflow-name'))workflow.name=$('#workflow-name').value;if($('#workspace-path'))workspace=$('#workspace-path').value;}
function activeNode(){return workflow.nodes.find(n=>n.id===selected);}
function applyProperties(render=true){
  const node=activeNode();
  if(node&&$('#node-label')){
    const config=JSON.parse($('#node-config').value);
    if(!config||typeof config!=='object'||Array.isArray(config))throw new Error('Node settings must be a JSON object.');
    node.label=$('#node-label').value;node.config=config;
    const parents=$$('[data-parent]:checked').map(x=>x.dataset.parent);
    workflow.edges=workflow.edges.filter(e=>e.to!==node.id);
    parents.forEach(id=>workflow.edges.push({from:id,to:node.id}));dirty=true;
  }
  if(render)renderCanvas();
}
async function saveWorkflow(){syncInputs();applyProperties(false);workflow=await post('save',{workflow});dirty=false;await refresh();toast('Workflow definition saved.');return workflow;}

function canvasHTML(){
  const width=Math.max(800,...workflow.nodes.map(n=>(Number(n.x)||30)+240));
  const height=Math.max(385,...workflow.nodes.map(n=>(Number(n.y)||40)+115));
  let edges='';
  for(const edge of workflow.edges){
    const a=workflow.nodes.find(n=>n.id===edge.from),b=workflow.nodes.find(n=>n.id===edge.to);if(!a||!b)continue;
    const ax=Number(a.x)||30,ay=Number(a.y)||40,bx=Number(b.x)||30,by=Number(b.y)||40;
    let path;
    if(Math.abs(by-ay)>100&&Math.abs(bx-ax)<60){const sx=ax+102,sy=ay+84,tx=bx+102,ty=by;path=`M${sx} ${sy} C${sx} ${sy+40},${tx} ${ty-40},${tx} ${ty}`;}
    else{const right=bx>ax;const sx=ax+(right?205:0),sy=ay+42,tx=bx+(right?0:205),ty=by+42;const d=right?40:-40;path=`M${sx} ${sy} C${sx+d} ${sy},${tx-d} ${ty},${tx} ${ty}`;}
    edges+=`<path class="edge" d="${path}" marker-end="url(#flow-arrow)"/>`;
  }
  return `<div class="flow-canvas" style="width:${width}px;height:${height}px"><svg class="flow-connections" viewBox="0 0 ${width} ${height}"><defs><marker id="flow-arrow" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto"><path d="M0 0 6 3 0 6" fill="#9cacc2"/></marker></defs>${edges}</svg>${workflow.nodes.map((n,index)=>{const result=lastRun?.steps?.find(s=>s.id===n.id);return `<button class="flow-node ${selected===n.id?'selected':''}" data-node="${E(n.id)}" style="left:${Number(n.x)||30}px;top:${Number(n.y)||40}px" aria-label="Edit ${E(n.label||n.type)}"><span class="node-type">${icon(nodeIcons[n.type]||'flow')}<span>STEP ${String(index+1).padStart(2,'0')}</span></span><strong>${E(n.label||state.node_types[n.type]?.label||n.type)}</strong>${result?`<span class="node-result">${E(result.records)} records checked</span>`:''}</button>`;}).join('')}</div>`;
}
function renderCanvas(){
  $('#canvas-scroll').innerHTML=canvasHTML();
  $$('.flow-node').forEach(node=>{
    let drag=null,moved=false;
    node.addEventListener('pointerdown',e=>{
      if(e.button!==0)return;
      selected=node.dataset.node;$$('.flow-node').forEach(n=>n.classList.toggle('selected',n===node));renderProperties();
      const data=activeNode();drag={sx:e.clientX,sy:e.clientY,x:Number(data.x)||30,y:Number(data.y)||40};moved=false;
      node.setPointerCapture(e.pointerId);
    });
    node.addEventListener('pointermove',e=>{
      if(!drag)return;const dx=e.clientX-drag.sx,dy=e.clientY-drag.sy;if(Math.abs(dx)+Math.abs(dy)>4)moved=true;
      if(moved){const data=activeNode();data.x=Math.max(8,Math.min(1800,drag.x+dx));data.y=Math.max(8,Math.min(1000,drag.y+dy));node.style.left=data.x+'px';node.style.top=data.y+'px';dirty=true;}
    });
    node.addEventListener('pointerup',()=>{drag=null;if(moved)renderCanvas();});
    node.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();selected=node.dataset.node;renderCanvas();renderProperties();}});
  });
  if($('#definition-status'))$('#definition-status').textContent=dirty?'Unsaved changes':`Saved revision ${workflow.version||1}`;
}
function renderProperties(){
  const node=activeNode();
  const box=$('#properties-content');if(!box)return;
  if(!node){box.innerHTML=empty('Select a step','Select a block on the canvas to edit it.','flow');return;}
  box.innerHTML=`<div class="node-description">${E(state.node_types[node.type]?.detail||'Workflow step')}</div><label class="field">Step name<input id="node-label" value="${E(node.label||node.type)}"></label><label class="field">Settings as JSON<textarea id="node-config" rows="6" spellcheck="false">${E(JSON.stringify(node.config||{},null,2))}</textarea></label>${node.type!=='scan'?`<div class="field">Input steps<div style="max-height:115px;overflow:auto;margin-top:6px">${workflow.nodes.filter(n=>n.id!==node.id).map(n=>`<label class="check-label tiny"><input type="checkbox" data-parent="${E(n.id)}" ${workflow.edges.some(e=>e.from===n.id&&e.to===node.id)?'checked':''}>${E(n.label||n.id)}</label>`).join('')}</div></div>`:''}<div class="section-actions">${button('apply-node','Apply settings','check','primary')}${button('remove-node','Remove','trash','ghost')}</div><p class="muted tiny" style="margin-top:14px">Connect only earlier inputs. The engine rejects cycles and missing connections.</p>`;
  listen('#apply-node','click',()=>{syncInputs();applyProperties();toast('Step settings applied. Save the workflow to keep them.');});
  listen('#remove-node','click',()=>{syncInputs();workflow.nodes=workflow.nodes.filter(n=>n.id!==selected);workflow.edges=workflow.edges.filter(e=>e.from!==selected&&e.to!==selected);selected=workflow.nodes[0]?.id;dirty=true;renderCanvas();renderProperties();});
}

async function renderBuilder(){
  if(!workflow){workflow=await get('workflow');selected=workflow.nodes[0]?.id;}
  const options=[...state.workflows];if(!options.some(w=>w.id===workflow.id))options.push({id:workflow.id,name:workflow.name});
  $('#view').innerHTML=pageHead('LOCAL FILE AUTOMATION','Make file work repeatable.','Build a file workflow, preview each step, and write new outputs without changing your source files.',`${button('new-flow','New workflow','plus')}${button('save-flow','Save definition','check','primary')}`)
  +stats([['Saved workflows',state.stats.workflows,'Independent JSON definitions','flow'],['Completed runs',state.stats.finished,'Stored with step-by-step reports','check'],['Execution mode','Local','No cloud services or API keys','shield']])
  +`<div class="panel"><div class="panel-body" style="padding:16px 20px"><div class="input-row"><select id="workflow-select" aria-label="Select workflow">${options.map(w=>`<option value="${E(w.id)}" ${w.id===workflow.id?'selected':''}>${E(w.name)}</option>`).join('')}</select><input id="workflow-name" aria-label="Workflow name" value="${E(workflow.name)}"><span class="count-label" id="definition-status">Saved revision ${workflow.version||1}</span>${button('import-flow','Import','upload','ghost')}${button('export-flow','Export','download','ghost')}<input id="workflow-import-file" type="file" accept=".json" hidden></div><div class="input-row" style="margin-top:12px"><span class="small muted">Workspace</span><input id="workspace-path" aria-label="Workflow workspace path" value="${E(workspace)}">${button('browse-workspace','Choose folder','folder')}${button('demo-workspace','Use demo','','ghost')}</div></div></div>`
  +`<div class="workflow-grid"><div><div class="panel"><div class="panel-head"><div><h2>Workflow canvas</h2><p>Select a step to edit it. Drag steps to arrange them.</p></div>${badge(workflow.nodes.length+' steps','accent')}</div><div class="node-palette">${Object.entries(state.node_types).map(([kind,s])=>`<button class="palette-item" data-add-node="${E(kind)}" title="${E(s.detail)}">${icon('plus')}${E(s.label)}</button>`).join('')}</div><div id="canvas-scroll" class="canvas-scroll"></div><div class="run-actions">${button('preview-run','Preview plan','play','secondary')}${button('real-run','Create outputs','play','primary')}${button('step-run','Run to selected','arrow','ghost')}<span class="run-note">File nodes create copies. Desktop actions can change other apps.</span></div></div><div id="run-results"></div></div><aside class="panel properties"><div class="panel-head"><h2>Step settings</h2>${icon('settings')}</div><div class="panel-body" id="properties-content"></div></aside></div>`;
  renderCanvas();renderProperties();renderResults();
  listen('#save-flow','click',async()=>{await saveWorkflow();await renderBuilder();});
  listen('#workflow-select','change',async e=>{workspace=$('#workspace-path').value;workflow=await get('workflow',{id:e.target.value});selected=workflow.nodes[0]?.id;dirty=false;lastRun=null;await renderBuilder();});
  listen('#new-flow','click',async()=>{workspace=$('#workspace-path').value;workflow={id:'workflow-'+Date.now(),name:'Untitled workflow',version:0,nodes:[{id:'input',type:'scan',label:'Read workspace',x:45,y:70,config:{pattern:'*'}}],edges:[]};selected='input';lastRun=null;dirty=true;await renderBuilder();});
  listen('#browse-workspace','click',async()=>{const path=await pickPath(workspace);if(path){workspace=path;$('#workspace-path').value=path;}});
  listen('#demo-workspace','click',()=>{workspace=info.example_path;$('#workspace-path').value=workspace;toast('The included demo folder is selected.');});
  listen('#import-flow','click',()=>$('#workflow-import-file').click());
  listen('#workflow-import-file','change',async e=>{const file=e.target.files[0];if(!file)return;if(file.size>100000)throw new Error('A workflow definition must be smaller than 100 KB.');workflow=await post('save',{workflow:JSON.parse(await file.text())});selected=workflow.nodes[0]?.id;lastRun=null;await refresh();await renderBuilder();toast('Workflow imported and validated.');});
  listen('#export-flow','click',async()=>{await saveWorkflow();await download(await post('export',{id:workflow.id}));});
  listen('[data-add-node]','click',(_,node)=>{syncInputs();applyProperties(false);const type=node.dataset.addNode;const ident=type+'-'+Date.now().toString(36);const previous=selected;workflow.nodes.push({id:ident,type,label:state.node_types[type].label,x:60+(workflow.nodes.length%3)*250,y:420+Math.floor(workflow.nodes.length/3)*130,config:structuredClone(defaults[type])});if(type!=='scan'&&previous)workflow.edges.push({from:previous,to:ident});selected=ident;dirty=true;renderCanvas();renderProperties();$('#canvas-scroll').scrollTop=1000;});
  async function run(dry,stop){syncInputs();applyProperties(false);let desktop_token='';if(!dry&&workflow.nodes.some(n=>n.type==='desktop')){if(!state.desktop_allowed)throw new Error('Restart with --allow-desktop to permit confirmed desktop actions.');const actions=workflow.nodes.filter(n=>n.type==='desktop').map(n=>n.config.actions);if(!window.confirm('Review these actions. They can type into the wrong window. Move the mouse to a screen corner to stop. Actions start after 3 seconds.\n\n'+JSON.stringify(actions,null,2)))return;desktop_token=(await post('desktop/arm',{workflow,workspace,confirmed:true})).desktop_token;}lastRun=await runJob('run',{workflow,workspace,dry_run:dry,stop_after:stop||null,desktop_token});await refresh();if(view==='builder'){await renderBuilder();}toast(dry?'Preview complete. No output files were written.':'New output files are ready.');}
  listen('#preview-run','click',()=>run(true));listen('#real-run','click',()=>run(false));listen('#step-run','click',()=>run(true,selected));
}
function renderResults(){
  const box=$('#run-results');if(!box)return;
  if(!lastRun){box.innerHTML=`<div class="notice info">${icon('shield')}<span>Start with Preview plan. Inspect the proposed outputs before you create files.</span></div>`;return;}
  box.innerHTML=`<div class="panel"><div class="panel-head"><div><h2>${lastRun.dry_run?'Preview results':'Run results'}</h2><p>${lastRun.dry_run?'No output files were written.':'Output copies and a run manifest are ready.'}</p></div>${badge(lastRun.record_count+' records','good')}</div><div class="table-wrap"><table><thead><tr><th>Step</th><th>Records</th><th>Time</th><th>Result</th></tr></thead><tbody>${lastRun.steps.map(s=>`<tr><td>${E(s.label)}</td><td>${s.records}</td><td>${s.seconds.toFixed(3)} s</td><td>${E(s.note)}</td></tr>`).join('')}</tbody></table></div>${lastRun.artifacts?.length?`<div class="panel-body">${artifactsHTML(lastRun.artifacts)}</div>`:`<div class="panel-body small muted">Planned files: ${E(lastRun.planned_files.join(', ')||'No output step reached.')}</div>`}</div>`;
  bindArtifacts(lastRun.artifacts||[],box);
}
async function renderTriggers(){
  $('#view').innerHTML=pageHead('AUTOMATIC RUNS','Run only when you choose.','Folder watches run in the local worker. A user service can start the worker at login.')+`<div class="notice">${icon('alert')}<span>Triggers create output files. An enabled trigger resumes after an encrypted-vault restart. Select Stop trigger to disable it. The current trigger uses a snapshot of the saved workflow.</span></div><div class="split"><div class="panel"><div class="panel-head"><h2>Trigger settings</h2>${badge(state.trigger.enabled?'Running':'Off',state.trigger.enabled?'good':'')}</div><div class="panel-body"><label class="field">Saved workflow<select id="trigger-workflow">${state.workflows.map(w=>`<option value="${E(w.id)}">${E(w.name)}</option>`).join('')}</select></label><label class="field">Workspace folder<input id="trigger-path" value="${E(workspace)}"></label><div class="two-cols"><label class="field">Trigger type<select id="trigger-mode"><option value="watch">When folder metadata changes</option><option value="schedule">At a fixed interval</option></select></label><label class="field">Interval in seconds<input type="number" id="trigger-seconds" min="15" max="86400" value="30"></label></div><div class="section-actions">${button('start-trigger','Start trigger','play','primary')}${button('stop-trigger','Stop trigger','pause')}</div></div></div><div class="panel"><div class="panel-head"><h2>Current state</h2></div><div class="panel-body"><div class="key-values"><span>Enabled</span><strong>${state.trigger.enabled?'Yes':'No'}</strong><span>Mode</span><strong>${E(state.trigger.mode)}</strong><span>Last error</span><strong>${E(state.trigger.last_error||'None')}</strong></div><p class="muted small">Keep outputs outside the watched input folder. The app excludes its own private data folder from scans.</p></div></div></div>`;
  listen('#start-trigger','click',async()=>{await post('trigger/start',{id:$('#trigger-workflow').value,workspace:$('#trigger-path').value,mode:$('#trigger-mode').value,seconds:Number($('#trigger-seconds').value)});await refresh();await renderTriggers();toast('Trigger started. The browser tab can close while the local worker stays running.');});
  listen('#stop-trigger','click',async()=>{await post('trigger/stop');await refresh();await renderTriggers();toast('Trigger stopped.');});
}
async function route(tab){view=tab;await refresh();
  if(tab==='builder')return renderBuilder();
  if(tab==='runs'){$('#view').innerHTML=pageHead('EXECUTION HISTORY','See what each run did.','Completed, cancelled, and interrupted jobs stay visible in the local database.')+`<div class="panel">${jobsHTML(state.jobs)}</div>`;bindJobs();return;}
  if(tab==='triggers')return renderTriggers();
  $('#view').innerHTML=pageHead('WORKFLOW GUIDE','Small steps. Explicit outputs.','A workflow is a saved graph of file-processing steps.')+`<div class="panel"><div class="panel-body">${guide}</div></div><div class="panel"><div class="panel-head"><h2>Available step types</h2></div><table><thead><tr><th>Step</th><th>Purpose</th></tr></thead><tbody>${Object.values(state.node_types).map(n=>`<tr><td>${E(n.label)}</td><td>${E(n.detail)}</td></tr>`).join('')}</tbody></table></div><div class="notice">${icon('alert')}<span>OCR, PDF tables, semantic ranking, and summaries run locally. Desktop actions need explicit permission and confirmation. Interrupted runs are not replayed automatically.</span></div>`;
}
mount(info,[['builder','Workflow builder','flow'],['runs','Run history','clock'],['triggers','Triggers','refresh'],['guide','Step guide','help']],route,guide);
