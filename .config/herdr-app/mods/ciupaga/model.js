// Pure data and command construction; no Herdr or platform globals.
export const joinPath=(root,file)=>`${root.replace(/[\\/]+$/,'')}/${file}`;
export function sourceKey(context,file) {
  const folder=String(context.folder||''),windows=/^[a-z]:[\\/]/i.test(folder)||folder.startsWith('\\\\');
  let normalized=folder.replace(/\\/g,'/');
  if(normalized.length>1&&!/^[a-z]:\/$/i.test(normalized))normalized=normalized.replace(/\/$/,'');
  if(windows)normalized=normalized.toLowerCase();
  return JSON.stringify([context.machine||null,normalized,windows?file.toLowerCase():file]);
}
export function canonicalTaskKey(key) {
  if(typeof key!=='string')return key;
  const separator=key.indexOf('\n'),prefix=separator<0?key:key.slice(0,separator);
  try {const [machine,folder,file]=JSON.parse(prefix);if(typeof folder!=='string'||typeof file!=='string')return key;return sourceKey({machine,folder},file)+(separator<0?'':key.slice(separator));}catch{return key;}
}
export function migrateKeys(store={}) {
  const result={};
  for(const [oldKey,value] of Object.entries(store)) {
    const key=canonicalTaskKey(oldKey),previous=result[key];
    if(previous?.at!=null&&value?.at!=null&&previous.at>value.at)continue;
    result[key]=previous?.stars&&value?.stars?{...previous,...value,stars:[...new Set([...previous.stars,...value.stars])]}:value;
  }
  return result;
}
export const taskContext=(context,source)=>({...context,folder:source.folder||context.folder});
export const sourceIdentity=(context,source)=>sourceKey(taskContext(context,source),source.identityFile||source.file);
export const taskKey=(context,source,task)=>sourceIdentity(context,source)+'\n'+task.name;

// Arguments are literal tokens, never a shell program. Backslashes stay literal
// (also in Windows paths); matching quotes group tokens, doubled quotes escape.
export function parseArguments(text='') {
  const result=[]; let token='',quote=null,started=false;
  for(let i=0;i<text.length;i++) {
    const c=text[i];
    if(quote) {
      if(c===quote) { if(text[i+1]===quote){token+=c;i++;}else quote=null; }
      else token+=c;
    } else if(c==='"'||c==="'") {quote=c;started=true;}
    else if(/\s/.test(c)) {if(started){result.push(token);token='';started=false;}}
    else {token+=c;started=true;}
  }
  if(quote)throw new Error('Unclosed quote in arguments');
  if(started)result.push(token);
  return result;
}

const sorted=tasks=>tasks.sort((a,b)=>a.name.localeCompare(b.name));
const task=(name,description='',parameters=[])=>({name,description,parameters});
function justChoices(pattern) {
  const literal=typeof pattern==='string'?pattern:Array.isArray(pattern)&&pattern.length===1&&typeof pattern[0]==='string'?pattern[0]:null;
  return literal&&/^[\w./-]+(?:\|[\w./-]+)+$/.test(literal)?literal.split('|'):null;
}
export function parseMake(text) {
  const found=new Map(); let comment='';
  for(const line of text.replace(/\\\r?\n/g,' ').split(/\r?\n/)) {
    if(/^\s*#/.test(line)){comment=line.replace(/^\s*#+\s*/,'');continue;}
    if(/^\t/.test(line))continue;
    const match=/^([^\s#:=][^:=]*?)\s*:(?![=])(?:[^#]*?)(?:##\s*(.*))?$/.exec(line);
    if(match) {
      const names=match[1].trim().split(/\s+/);
      if(names[0]==='.PHONY')for(const name of line.split(':').slice(1).join(':').split('#')[0].trim().split(/\s+/)) {
        if(/^[\w][\w./-]*$/.test(name)&&!found.has(name))found.set(name,task(name));
      }
      for(const name of names)if(/^[\w][\w./-]*$/.test(name))found.set(name,task(name,match[2]||comment));
    }
    comment='';
  }
  return sorted([...found.values()]);
}
export function parseJust(data,prefix='') {
  const tasks=[];
  for(const [key,r] of Object.entries(data.recipes||{})) {
    if(r.private||key.startsWith('_'))continue;
    tasks.push(task(prefix+key,r.doc||'',(r.parameters||[]).map(p=>({
      name:p.name,required:p.default==null&&p.kind!=='star',
      boolean:(Boolean(p.long||p.short)&&p.value!=null)||(!p.long&&!p.short&&['true','false'].includes(p.default)),
      defaultBoolean:!p.long&&!p.short&&p.default==='true',defaultValue:typeof p.default==='string'?p.default:undefined,
      option:p.long?`--${p.long}`:p.short?`-${p.short}`:null,
      choices:justChoices(p.pattern),
      variadic:p.kind==='star'||p.kind==='plus',
      hint:p.help||(p.default==null?'':typeof p.default==='string'?`Default: ${p.default}`:'Default defined in justfile')
    }))));
  }
  for(const [name,module] of Object.entries(data.modules||{}))if(module&&typeof module==='object')tasks.push(...parseJust(module,prefix+name+'::'));
  return sorted(tasks);
}
export function parseTask(data) {
  if(!Array.isArray(data.tasks))throw new Error('Unsupported Task JSON: expected tasks array');
  return sorted(data.tasks.filter(t=>!t.internal).map(t=>task(t.name||t.task,t.desc||t.summary||'')));
}
export function parseMise(data) {
  if(!Array.isArray(data))throw new Error('Unsupported Mise JSON: expected tasks array');
  return sorted(data.filter(t=>!t.hide).map(t=>({...task(t.name,t.description||''),source:t.source})));
}
export function packageTasks(data) {
  return sorted(Object.entries(data.scripts||{}).filter(([,v])=>typeof v==='string').map(([name,value])=>task(name,value)));
}
export function jsonTasks(data,kind) {
  return sorted(Object.entries(data[kind==='deno'?'tasks':'scripts']||{}).map(([name,value])=>task(name,typeof value==='string'?value:JSON.stringify(value))));
}
export function packageManager(data,locks=[]) {
  const declared=data.packageManager?.split('@')[0];
  if(['npm','pnpm','yarn','bun'].includes(declared))return declared;
  if(locks.includes('pnpm-lock.yaml'))return 'pnpm';
  if(locks.includes('yarn.lock'))return 'yarn';
  if(locks.includes('bun.lock')||locks.includes('bun.lockb'))return 'bun';
  return 'npm';
}
export function taskArgv(source,t,args=[]) {
  if(!t.name||t.name.startsWith('-'))throw new Error('Task names beginning with - are unsupported');
  switch(source.kind) {
    case 'just': return ['just','--justfile',source.file,'--',t.name,...args];
    case 'make': return ['make','-f',source.file,'--',t.name,...args];
    case 'task': return ['task','--taskfile',source.file,t.name,...(args.length?['--',...args]:[])];
    case 'mise': return ['mise','run',t.name,...args];
    case 'package': return [source.manager||'npm','run',t.name,...(args.length&&(!source.manager||source.manager==='npm')?['--']:[]),...args];
    case 'composer': return ['composer','run-script',t.name,...(args.length?['--',...args]:[])];
    case 'deno': return ['deno','task','--config',source.file,t.name,...args];
    default: throw new Error(`Unsupported runner: ${source.kind}`);
  }
}
export function platformArgv(argv,platform) {
  if(platform!=='windows')return argv;
  if(argv.some(value=>/[\0\r\n]/.test(value)))throw new Error('Windows task arguments cannot contain NUL or line breaks');
  const quote=s=>"'"+String(s).replace(/'/g,"''")+"'";
  // Build the native CRT command line ourselves: Windows PowerShell 5's
  // native argument binder otherwise strips embedded quotes and empty values.
  const native=s=>'"'+String(s).replace(/(\\*)"/g,'$1$1\\"').replace(/(\\+)$/,'$1$1')+'"';
  // Batch shims forward %* through a second cmd parsing pass.
  const batch=s=>native(s).replace(/[ !%^&()<>|"]/g,'^$&').replace(/[ !%^&()<>|"]/g,'^$&');
  const args=argv.slice(1);
  return ['powershell.exe','-NoLogo','-NoProfile','-NonInteractive','-Command',
    `$ErrorActionPreference='Stop'; $program=(Get-Command ${quote(argv[0])} -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source; $info=New-Object System.Diagnostics.ProcessStartInfo; $info.UseShellExecute=$false; if ($program -match '\\.(cmd|bat)$') { $info.FileName=$env:ComSpec; $info.Arguments='/d /v:off /s /c ""'+$program+${quote('" '+args.map(batch).join(' ')+'"')} } else { $info.FileName=$program; $info.Arguments=${quote(args.map(native).join(' '))} }; $process=[System.Diagnostics.Process]::Start($info); $process.WaitForExit(); exit $process.ExitCode`];
}
export function platformFromUname(value) {
  if(/mingw|msys|cygwin/i.test(value))return 'windows';
  if(/darwin/i.test(value))return 'macos';
  if(/linux/i.test(value))return 'linux';
  throw new Error(`Unrecognized remote platform: ${value.trim()}`);
}
export function groupTasks(tasks,stars=[]) {
  const selected=new Set(stars),primary=tasks.filter(t=>selected.has(t.name));
  return primary.length?{primary,others:tasks.filter(t=>!selected.has(t.name))}:{primary:tasks,others:[]};
}
export function collectArguments(parameters,values,extra='') {
  const args=[],pending=[];
  const positional=tokens=>{if(pending.some(v=>v===undefined))throw new Error('Fill earlier positional parameters before later ones');args.push(...pending,...tokens);pending.length=0;};
  for(const p of parameters) {
    const value=values[p.name]??'';
    if(p.boolean){
      const checked=typeof value==='boolean'?value:value==='true'?true:value==='false'?false:Boolean(p.defaultBoolean);
      if(p.option){if(checked)args.push(p.option);else if(p.required)throw new Error(`Enable ${p.name}`);}
      else {const literal=String(checked);if(literal===p.defaultValue)pending.push(literal);else positional([literal]);}
      continue;
    }
    if(value==='') {
      if(p.required)throw new Error(`Enter ${p.name}`);
      if(!p.option)pending.push(p.defaultValue);continue;
    }
    const tokens=p.variadic?parseArguments(value):[value];
    if(p.option)for(const token of tokens)args.push(p.option,token);
    else positional(tokens);
  }
  return [...args,...parseArguments(extra)];
}
