export function runState(t) {
  if(!t)return 'idle';
  if(t.state==='live')return 'running';
  if(t.reason==='killed')return 'cancelled';
  if(t.exit_code==null)return 'finished';
  return t.exit_code===0?'succeeded':'failed';
}
export function latestRun(terminals,key) {
  let latest=null;for(const terminal of terminals)if(canonicalTaskKey(terminal.labels?.['ciupaga.task'])===key&&(!latest||(terminal.created_ms||0)>(latest.created_ms||0)))latest=terminal;
  return latest;
}
export function terminalIndex(terminals){const result=new Map();for(const t of terminals){const key=canonicalTaskKey(t.labels?.['ciupaga.task']),old=result.get(key);if(key&&(!old||(t.created_ms||0)>(old.created_ms||0)))result.set(key,t);}return result;}
export function launchArgs(context,key,id,argv) {
  return ['run','--json','--bg','--no-parent','--no-notify','--cwd',context.folder,
    ...(context.machine?['--on',context.machine]:[]),'--label',`ciupaga.task=${key}`,'--label',`ciupaga.run=${id}`,'--',...argv];
}
export function contextFrom(props,focus,spaces) {
  if(props.context?.folder)return props.context;
  const space=spaces.find(s=>s.id===focus?.space)||spaces.find(s=>s.active);
  return {folder:focus?.cwd||space?.folder||'',machine:space?.machine||null,space:space?.id||focus?.space};
}
export function findNode(tree,id) {
  if(!tree)return null;
  if(tree.id===id)return tree;
  for(const child of tree.children||[]) {const match=findNode(child,id);if(match)return match;}
  return null;
}
export function viewAction(place,tree,focus) {
  if(place==='tab')return {name:'tab.new',args:{mod:'ciupaga',name:'Ciupaga'}};
  const sidebar=place==='sidebar'&&sidebarPath(tree);
  if(sidebar)return {name:'layout.show',args:{id:sidebar.at(-1).id},path:sidebar};
  if(!focus?.pane)throw new Error('Focus a terminal pane before opening a split');
  return {name:'pane.split',args:{pane:focus.pane,direction:place==='down'?'down':'right',mod:'ciupaga'}};
}
export function sidebarPath(tree,path=[]) {
  if(!tree)return null;
  const next=[...path,tree];
  if(tree.content?.mod==='ciupaga'&&(tree.content.props?.role||'sidebar')==='sidebar'&&tree.id)return next;
  for(const child of tree.children||[]){const match=sidebarPath(child,next);if(match)return match;}
  return null;
}
export const statusText=(state,t)=>({idle:'Ready',starting:'Starting…',cancelling:'Cancelling…',running:'Running',succeeded:'Succeeded',failed:`Failed · exit ${t?.exit_code??'?'}`,cancelled:'Cancelled',finished:'Finished · exit code unavailable',error:'Could not start'})[state]||state;

// One owner reserves before awaiting hc, so other copies cannot double launch.
export function reserveRun(records,key,id,now=Date.now()) {
  const existing=records[key];
  if(existing?.phase==='starting'&&now-existing.at<35000)throw new Error('This task is already starting');
  return {...records,[key]:{id,at:now,phase:'starting',cancel:false}};
}
export function resolveRecord(key,entry,terminals,now=Date.now()) {
  const terminal=(terminals instanceof Map?terminals.get(key):latestRun(terminals,key))||entry?.final||null;
  if(entry?.phase==='starting'&&terminal?.labels?.['ciupaga.run']!==entry.id&&now-entry.at<35000)
    return {key,entry,terminal:null,state:entry.cancel?'cancelling':'starting'};
  const same=entry&&terminal?.labels?.['ciupaga.run']===entry.id;
  if(same||(!entry&&terminal))return {key,entry,terminal,state:same&&entry.cancel&&terminal.state==='live'?'cancelling':runState(terminal)};
  if(entry?.error)return {key,entry,terminal:null,state:'error'};
  return {key,entry,terminal:null,state:'idle'};
}
import {canonicalTaskKey} from './model.js';
