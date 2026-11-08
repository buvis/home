import {View} from 'gpui-kit';
import {InputState} from 'gpui-base';
import {focused,spaces,terminals,panes,theme,window,props,shared,setShared,exec,hc,readTextFile,run,layout,openOverlay,closeOverlay,nextCommand,notify} from 'herdr';
import {discover} from './discovery.js';
import {sourceKey,sourceIdentity,taskContext,taskKey,taskArgv,platformArgv,platformFromUname,collectArguments,migrateKeys} from './model.js';
import {contextFrom,launchArgs,reserveRun,resolveRecord,viewAction} from './runtime.js';
import {render,launcher,outputView} from './ui.js';
import {cacheKey,metadataContext,sessionServices} from './cache.js';

const PREFS='ciupaga.v1.preferences',RUNS='ciupaga.v1.runs',FORMS='ciupaga.v1.forms',CACHE='ciupaga.v2.metadata',CONSOLES='ciupaga.v2.consoles';
const uid=()=>Date.now().toString(36)+Math.random().toString(36).slice(2);

export default class Ciupaga extends View {
  init(initial,cx) {
    this.options=props()||initial||{};this.role=this.options.role||'popup';
    if(!shared('ciupaga.v2.keysMigrated')){for(const key of [PREFS,RUNS,FORMS])setShared(key,migrateKeys(shared(key)||{}));setShared('ciupaga.v2.keysMigrated',true);}
    this.context=null;this.sources=[];this.loading=false;this.message='';this.openMenu=null;this.detail=null;this.others=false;this.generation=0;this.inputs={};this.services=sessionServices();
    if(this.role==='output')this.context=this.options.context||this.currentContext();
    this.search=InputState.new({placeholder:'Find a task…'});
    this.search.on('change',(_e,cx)=>cx.notify());
    this.handle=cx.focus_handle();this.menuFocus=cx.focus_handle();
    if(this.role!=='button'&&this.role!=='output')this.activate(cx);
    cx.timer.every(1000,cx=>{this.reconcile(cx);if(this.role!=='button'&&this.role!=='output')this.activate(cx);});
    cx.spawn(async cx=>{for(;;){const command=await nextCommand();const name=typeof command==='string'?command:command.name;
      if(name==='focus')this.handle.focus();
      if(name==='open')this.openPopup();
      if(name==='refresh'&&this.role!=='button')this.reload(cx,true);
      if(name==='tab')this.present('tab',cx);
      if(name==='sidebar')this.present('sidebar',cx);
      if(name==='beside')this.present('right',cx);
      if(name==='below')this.present('down',cx);
      if(name==='sources')this.openMenu=this.openMenu==='sources'?null:'sources';
      if(name==='views')this.openMenu=this.openMenu==='presentation'?null:'presentation';
      const colon=name.indexOf(':');
      if(colon>0) {
        const action=name.slice(0,colon),value=name.slice(colon+1),task=this.source()?.tasks.find(t=>t.name===value);
        if(action==='source'&&this.sources.some(s=>s.file===value))this.selectSource(value,cx);
        if(task&&action==='run')this.start(task,cx);
        if(task&&action==='cancel')this.cancel(task,cx);
        if(task&&action==='star')this.toggleStar(task,cx);
        if(task&&action==='details')this.showDetail(task,cx);
        if(task&&action==='console')this.console(task,'tab',cx);
        if(task&&action==='console-right')this.console(task,'right',cx);
        if(task&&action==='console-up')this.console(task,'up',cx);
        if(task&&action==='console-down')this.console(task,'down',cx);
        if(task&&action==='hide-console')this.console(task,'hide',cx);
      }
      cx.notify();
    }});
  }
  close() {this.search.release();for(const input of Object.values(this.inputs))input.release();}
  currentContext(){return contextFrom(this.options,focused(),spaces());}
  activate(cx) {
    const context=this.currentContext();
    if(JSON.stringify(context)===JSON.stringify(this.requestContext))return;
    this.requestContext=context;
    this.context=context;this.sources=[];this.detail=null;this.loading=false;this.others=false;this.generation++;
    const cached=this.services.metadata.peek(cacheKey(context))||shared(CACHE)?.[cacheKey(context)];
    if(cached){this.services.metadata.seed(cacheKey(context),cached);this.applyMetadata(cached);}
    this.reload(cx);
  }
  async platform(context) {
    if(!context.machine)return window().platform;
    if(this.remotePlatform?.machine===context.machine)return this.remotePlatform.platform;
    let platform;
    try {const r=await exec('uname',['-s'],{on:context.machine});if(r.code!==0)throw new Error(r.stderr);platform=platformFromUname(r.stdout);}
    catch {const r=await exec('cmd.exe',['/d','/c','ver'],{on:context.machine});if(r.code!==0)throw new Error('Cannot determine the task machine platform');platform='windows';}
    this.remotePlatform={machine:context.machine,platform};return platform;
  }
  applyMetadata(value) {
    if(this.context?.folder!==value.context.folder){this.detail=null;this.others=false;}
    this.context=metadataContext(this.requestContext,value.context);this.sources=value.sources;this.platformName=value.platform;
    if(this.detail){const fresh=this.source()?.tasks.find(t=>t.name===this.detail.name);if(!fresh||JSON.stringify(fresh.parameters)!==JSON.stringify(this.detail.parameters))this.detail=null;else this.detail=fresh;}
  }
  reload(cx,force=false) {
    if(!this.context?.folder||this.loading)return;
    const request={...(this.requestContext||this.context)},key=cacheKey(request);
    const generation=++this.generation;this.loading=true;this.message='';
    cx.spawn(async cx=>{
      try {
        const value=await this.services.metadata.load(key,async(previous)=>{
        const now=Date.now();
        let context={...(previous&&!force?previous.context:request)};
        const platform=previous?.platform||await this.platform(context);
        const same=previous?.context.folder===context.folder;
        let sources=await discover(context,readTextFile,exec,platform,same?previous:null,{force,now});
        if(!sources.length) {
          if(!previous||force){
          try {
            const root=await exec('git',['rev-parse','--show-toplevel'],{cwd:context.folder,on:context.machine});
            const folder=root.stdout.trim();
            if(root.code===0&&folder&&folder.replace(/\\/g,'/')!==context.folder.replace(/\\/g,'/')) {
              const fallback={...context,folder};
              const found=await discover(fallback,readTextFile,exec,platform,previous?.context.folder===folder?previous:null,{force,now});
              if(found.length){sources=found;context=fallback;}
            }
          } catch {} // A folder without Git remains a valid task project.
          }
        }
        return {context,sources,platform,fingerprints:sources.fingerprints,packages:sources.packages};
        },Date.now(),force);
        if(shared(CACHE)?.[key]?.checkedAt!==value.checkedAt){const stored={...(shared(CACHE)||{}),[key]:{context:value.context,sources:value.sources,platform:value.platform,packages:value.packages,checkedAt:value.checkedAt}};const keys=Object.keys(stored).sort((a,b)=>stored[b].checkedAt-stored[a].checkedAt);setShared(CACHE,Object.fromEntries(keys.slice(0,12).map(k=>[k,stored[k]])));}
        if(generation!==this.generation)return;
        this.applyMetadata(value);
      } catch(error) {if(generation===this.generation)this.message=String(error.message||error);}
      if(generation===this.generation){this.loading=false;cx.notify();}
    });
  }
  prefs(){return shared(PREFS)||{};}
  contextKey(){return sourceKey(this.context||{},'');}
  source(){const file=this.prefs()[this.contextKey()]?.file;return this.sources.find(s=>s.file===file)||this.sources[0]||null;}
  sourcePrefs(){const s=this.source();return s?this.prefs()[sourceIdentity(this.context,s)]||{}:{};}
  patchPrefs(key,patch){setShared(PREFS,{...this.prefs(),[key]:{...this.prefs()[key],...patch}});}
  selectSource(file,cx){this.patchPrefs(this.contextKey(),{file});this.detail=null;this.openMenu=null;this.others=false;cx.notify();}
  toggleStar(task,cx){const stars=new Set(this.sourcePrefs().stars||[]);stars.has(task.name)?stars.delete(task.name):stars.add(task.name);this.patchPrefs(sourceIdentity(this.context,this.source()),{stars:[...stars]});cx.notify();}
  formKey(task){return taskKey(this.context,this.source(),task);}
  showDetail(task,cx) {
    if(this.detail?.name===task.name){this.detail=null;cx.notify();return;}
    for(const input of Object.values(this.inputs))input.release();this.inputs={};this.detail=task;
    if(!(this.sourcePrefs().stars||[]).includes(task.name))this.others=true;
    const key=this.formKey(task),saved=shared(FORMS)?.[key]||{};
    this.flags=Object.fromEntries(task.parameters.filter(p=>p.boolean).map(p=>[p.name,saved.flags?.[p.name]??(saved[p.name]==='true'?true:saved[p.name]==='false'?false:Boolean(p.defaultBoolean))]));
    for(const p of [...task.parameters,{name:'$extra'}]) {
      if(p.boolean)continue;
      const input=InputState.new({value:saved[p.name]||'',placeholder:p.hint|| (p.required?'Required':'Optional')});
      input.on('change',(_e,cx)=>{this.saveForm(key);cx.notify();});
      input.on('submit',(_e,cx)=>this.start(task,cx));this.inputs[p.name]=input;
    }
    cx.notify();
  }
  saveForm(key=this.detail&&this.formKey(this.detail)) {
    if(!key)return;
    const values=Object.fromEntries(Object.entries(this.inputs).map(([name,input])=>[name,input.value()]));
    setShared(FORMS,{...(shared(FORMS)||{}),[key]:{...values,flags:this.flags||{}}});
  }
  record(task,index) {
    const key=this.formKey(task);return resolveRecord(key,shared(RUNS)?.[key],index||terminals());
  }
  patchRun(key,id,patch) {const all=shared(RUNS)||{};if(all[key]?.id===id)setShared(RUNS,{...all,[key]:{...all[key],...patch}});}
  start(task,cx) {
    const current=this.record(task);
    if(['starting','running','cancelling'].includes(current.state))return;
    if(task.parameters.some(p=>p.required)&&this.detail?.name!==task.name){this.showDetail(task,cx);return;}
    const source={...this.source()},context=taskContext(this.context,source),key=this.formKey(task),id=uid();
    let argv;
    try {
      const saved=shared(FORMS)?.[key]||{};
      const args=collectArguments(task.parameters,{...saved,...(saved.flags||{})},saved.$extra||'');
      argv=platformArgv(taskArgv(source,task,args),this.platformName);
      const reserved=reserveRun(shared(RUNS)||{},key,id);reserved[key].machine=context.machine;
      setShared(RUNS,reserved);
    } catch(error) {this.message=String(error.message||error);cx.notify();return;}
    this.message='';cx.notify();
    cx.spawn(async cx=>{
      try {
        const result=await hc(launchArgs(context,key,id,argv));
        if(result.code!==0)throw new Error((result.stderr||result.stdout).trim()||'Could not start task');
        const started=JSON.parse(result.stdout),address=started.address||started.terminal?.address;
        this.patchRun(key,id,{phase:'launched',address});
        if(shared(RUNS)?.[key]?.cancel&&address)this.killOnce(id,address);
      } catch(error) {this.patchRun(key,id,{phase:'error',error:String(error.message||error)});}
      cx.notify();
    });
  }
  cancel(task,cx) {
    const record=this.record(task);
    if(record.entry)this.patchRun(record.key,record.entry.id,{cancel:true});
    if(record.terminal)this.killOnce(record.entry?.id||record.terminal.address,record.terminal.address);
    cx.notify();
  }
  killOnce(id,address){const now=Date.now(),last=this.services.cancellations.get(id);if(last!=null&&now-last<5000)return;this.services.cancellations.set(id,now);run('terminal.kill',{terminal:address});}
  reconcile(cx) {
    // Recovers starts even if their popup closed before hc's response arrived.
    const live=new Map(terminals().filter(t=>t.labels?.['ciupaga.run']).map(t=>[t.labels['ciupaga.run'],t]));
    for(const [key,entry] of Object.entries(shared(RUNS)||{})) {
      if(entry.final||entry.error)continue;
      const terminal=live.get(entry.id);
      if(terminal&&terminal.state!=='live'){this.patchRun(key,entry.id,{phase:'finished',final:terminal});continue;}
      if(terminal&&entry.cancel)this.killOnce(entry.id,terminal.address);
      if(terminal||this.services.checks.has(entry.id))continue;
      if(!entry.address&&Date.now()-entry.at<3000)continue;
      this.services.checks.add(entry.id);
      cx.spawn(async cx=>{
        try {
          let address=entry.address;
          if(!address) {
            const r=await exec('hc',['ls','--all','--json','--label',`ciupaga.run=${entry.id}`],{on:entry.machine});
            if(r.code!==0)throw new Error(r.stderr||'Cannot recover task');
            const candidate=JSON.parse(r.stdout).terminals?.[0];
            address=candidate?.address;
            if(address&&entry.machine&&!address.includes('/'))address=entry.machine+'/'+address;
            if(!address){if(Date.now()-entry.at>35000)this.patchRun(key,entry.id,{phase:'error',error:'Task did not appear in herdr-core. Refresh and try again.'});return;}
            this.patchRun(key,entry.id,{address,phase:'launched'});
          }
          const result=await hc(['get',address,'--json']);
          if(result.code!==0)throw new Error(result.stderr||'Task terminal is unavailable');
          const snapshot=JSON.parse(result.stdout);
          if(snapshot.labels?.['ciupaga.run']!==entry.id)throw new Error('Task terminal identity changed');
          if(snapshot.state!=='live')this.patchRun(key,entry.id,{phase:'finished',final:{...snapshot,address}});
          else if(entry.cancel)this.killOnce(entry.id,address);
        } catch(error) {this.patchRun(key,entry.id,{phase:'error',error:String(error.message||error)});}
        finally {this.services.checks.delete(entry.id);}
        cx.notify();
      });
    }
  }
  openPopup() {
    const bounds=this.buttonBounds;
    openOverlay({mod:'ciupaga',kind:'popup',width:520,height:520,props:{role:'popup',context:this.currentContext()},...(bounds?{at:{x:bounds.x,y:bounds.y+bounds.height+4}}:{})});
  }
  present(place,cx) {
    try {
      const action=viewAction(place,layout(),focused());
      if(action.name==='layout.show') {
        for(let i=0;i<action.path.length;i++) {
          const node=action.path[i];
          if(node.id&&node.hidden)run('layout.show',{id:node.id});
          if(node.id&&node.type==='stack'&&action.path[i+1]?.id)run('layout.select',{stack:node.id,child:action.path[i+1].id});
        }
        run(action.name,action.args);
      } else run(action.name,{...action.args,...(action.name==='tab.new'?{space:this.context.space}:{}),props:{role:place==='sidebar'?'sidebar':'pane',context:this.context}});
      if(this.options.overlay)closeOverlay(this.options.overlay);
    } catch(error) {this.message=String(error.message||error);cx.notify();}
  }
  console(task,place,cx) {
    const record=this.record(task),terminal=record.terminal;
    if(!terminal)return;
    this.openMenu=null;
    const existing=this.consolePane(terminal.address);
    if(place==='hide'){if(existing?.terminal===terminal.address)run('terminal.park',{terminal:terminal.address});else if(existing)run('pane.close',{pane:existing.pane});return;}
    if(existing){run('tab.select',{id:existing.tab});run('pane.focus',{pane:existing.pane});this.dismiss();return;}
    const origin=focused();
    if(place!=='tab'&&!origin?.pane){this.message='Focus a terminal pane before opening a split';cx.notify();return;}
    if(terminal.state!=='live'){this.openOutput(task,terminal,place,cx);return;}
    if(this.services.opening.has(terminal.address))return;
    this.services.opening.add(terminal.address);
    run('terminal.keep',{terminal:terminal.address,place:place==='up'?'down':place});
    cx.spawn(async cx=>{
      try {for(let i=0;i<50;i++) {
        const pane=panes().find(p=>p.terminal===terminal.address);
        if(pane){
          if(place==='tab')run('tab.rename',{id:pane.tab,name:task.name});
          run('tab.select',{id:pane.tab});run('pane.focus',{pane:pane.pane});
          if(place==='up')run('pane.swap',{direction:'up'});
          this.dismiss();return;
        }
        await cx.sleep(100);
      }
      this.message='The console did not open. Try again.';cx.notify();
      } finally {this.services.opening.delete(terminal.address);}
    });
  }
  consolePane(address){const all=panes(),direct=all.find(p=>p.terminal===address),viewer=shared(CONSOLES)?.[address];return direct||all.find(p=>p.pane===viewer?.pane&&p.terminal===viewer?.terminal)||null;}
  openOutput(task,terminal,place,cx) {
    if(this.services.opening.has(terminal.address))return;
    const origin=focused(),before=new Set(panes().map(p=>p.pane)),name=`Ciupaga ${uid()}`;
    const target=this.context?.machine?terminal.address.split('/').at(-1):terminal.address;
    const argv=['hc','read',target,'--lines','10000'];
    if(place==='tab')run('tab.new',{space:this.context?.space,folder:terminal.cwd||this.context?.folder,name,argv});
    else if(origin?.pane)run('pane.split',{argv,pane:origin.pane,direction:place==='right'?'right':'down'});
    else {notify({title:'Ciupaga',body:'Focus a terminal pane before opening a split'});return;}
    this.services.opening.add(terminal.address);
    cx.spawn(async cx=>{
      try {for(let attempt=0;attempt<50;attempt++) {
        const tab=place==='tab'?spaces().flatMap(s=>s.tabs).find(t=>t.name===name):null;
        const candidate=panes().find(p=>!before.has(p.pane)&&p.terminal&&(place==='tab'?p.tab===tab?.id:p.tab===origin.tab&&JSON.stringify(terminals().find(t=>t.address===p.terminal)?.argv||[]).includes(target)));
        if(candidate){
          setShared(CONSOLES,{...(shared(CONSOLES)||{}),[terminal.address]:{pane:candidate.pane,terminal:candidate.terminal}});
          if(place==='tab')run('tab.rename',{id:candidate.tab,name:task.name});
          run('tab.select',{id:candidate.tab});run('pane.focus',{pane:candidate.pane});
          if(place==='up')run('pane.swap',{direction:'up'});
          this.dismiss();return;
        }
        await cx.sleep(100);
      }this.message='The console did not open. Try again.';cx.notify();
      } finally {this.services.opening.delete(terminal.address);}
    });
  }
  dismiss(){if(this.options.overlay)closeOverlay(this.options.overlay);}
  menuHandle(){return this.menuFocus;}
  render(cx) {
    if(this.role==='button')return launcher(this,cx);
    if(this.role==='output')return outputView(this,cx);
    return render(this,cx);
  }
}
