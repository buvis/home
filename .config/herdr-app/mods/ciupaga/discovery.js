import {joinPath,parseMake,parseJust,parseTask,parseMise,packageTasks,packageManager,jsonTasks,platformArgv} from './model.js';

export const candidates=[
  ['justfile','just'],['Justfile','just'],['.justfile','just'],
  ['GNUmakefile','make'],['makefile','make'],['Makefile','make'],
  ['Taskfile.yml','task'],['Taskfile.yaml','task'],['taskfile.yml','task'],['taskfile.yaml','task'],['Taskfile.dist.yml','task'],['Taskfile.dist.yaml','task'],
  ['mise.toml','mise'],['.mise.toml','mise'],['.config/mise.toml','mise'],
  ['package.json','package'],['composer.json','composer'],['deno.json','deno']
];
const excludedPackages=new Set(['node_modules','vendor','bower_components','bin','obj','dist','build','target','coverage']);
async function nestedPackages(context,execute,previous,{force,now}) {
  if(!force&&previous)return previous;
  try {
    const result=await execute('git',['ls-files','--cached','--others','--exclude-standard','-z','--',':(glob)*/package.json'],{cwd:context.folder,on:context.machine});
    const paths=result.code===0?result.stdout.split('\0').filter(path=>/^[^/\\]+\/package\.json$/.test(path)&&!path.startsWith('.')&&!excludedPackages.has(path.split('/')[0].toLowerCase())):[];
    return {paths:[...new Set(paths)].sort(),at:now};
  } catch {return {paths:[],at:now};} // Git is optional for task files in the current folder.
}
export async function discover(context,read,execute,platform,previous=null,{force=false,now=Date.now()}={}) {
  const sources=[],seen=new Set();
  const unique=candidates.filter(([file])=>{const key=platform==='windows'?file.toLowerCase():file;if(seen.has(key))return false;seen.add(key);return true;});seen.clear();
  const fingerprints=new Map(),work=[];
  async function append(entries) {
  const files=await Promise.all(entries.map(async([file,kind])=>({file,kind,text:await read(joinPath(context.folder,file),{on:context.machine})})));
  const physical=[];
  for(const {file,kind,text} of files) {
    if(text==null)continue;
    // Probe identity rather than guessing APFS case sensitivity from the OS.
    const alias=physical.find(other=>other.toLowerCase()===file.toLowerCase());
    if(alias&&platform!=='windows') {
      try {
        const same=await execute('sh',['-c','test "$1" -ef "$2"','ciupaga',alias,file],{cwd:context.folder,on:context.machine});
        if(same.code===0)continue;
      } catch {} // Keep both files if identity cannot be determined.
    }
    physical.push(file);
    const id=platform==='windows'?file.toLowerCase():file;
    // Windows aliases point to the same physical file. Mise layers are one effective config.
    if(seen.has(id)||(kind==='mise'&&sources.some(s=>s.kind==='mise')))continue;
    seen.add(id);
    const old=previous?.fingerprints?.get(file),oldSource=previous?.sources?.find(s=>s.file===file);
    fingerprints.set(file,{text,at:old?.at??now});
    if(!force&&old?.text===text&&oldSource){sources.push(oldSource);continue;}
    fingerprints.set(file,{text,at:now});
    const source={file,kind,tasks:[],error:null,note:''};
    if(kind==='package'&&file!=='package.json'){source.folder=joinPath(context.folder,file.slice(0,file.lastIndexOf('/')));source.identityFile='package.json';}
    sources.push(source);
    work.push((async()=>{
    try {
      if(kind==='make') {
        source.tasks=parseMake(text);
        source.note='Explicit targets only; included files, variables and generated targets are not expanded.';
      } else if(kind==='package') {
        const data=JSON.parse(text),locks=[];
        if(!data.packageManager)await Promise.all(['pnpm-lock.yaml','yarn.lock','bun.lock'].map(async lock=>{try{if(await read(joinPath(source.folder||context.folder,lock),{on:context.machine})!=null)locks.push(lock);}catch(error){if(/large|size|limit/i.test(String(error)))locks.push(lock);else throw error;}}));
        source.manager=packageManager(data,locks);source.tasks=packageTasks(data);
      } else if(kind==='composer'||kind==='deno') source.tasks=jsonTasks(JSON.parse(text),kind);
      else {
        const argv=kind==='just'?['just','--justfile',file,'--dump','--dump-format','json']:
          kind==='task'?['task','--taskfile',file,'--list-all','--json']:['mise','tasks','ls','--local','--json'];
        const options={cwd:context.folder,on:context.machine};
        let result;
        try {result=await execute(argv[0],argv.slice(1),options);}
        catch(error) {
          // Native runners do not need a PowerShell startup. Fall back only for
          // a Windows launcher/shim failure, never rerun a timed-out enumeration.
          if(platform!=='windows'||!/os error (?:2|193)\b|ENOENT|not a valid Win32|cannot start|program.*not found/i.test(String(error)))throw error;
          const [command,...args]=platformArgv(argv,platform);result=await execute(command,args,options);
        }
        if(result.code!==0)throw new Error((result.stderr||result.stdout).trim()||`${argv[0]} exited ${result.code}`);
        const data=JSON.parse(result.stdout);
        source.tasks=kind==='just'?parseJust(data):kind==='task'?parseTask(data):parseMise(data);
        if(kind==='mise')source.note='Mise merges project configuration layers and file tasks; this is the effective local task list.';
      }
    } catch(error) {source.error=String(error.message||error);}
    })());
  }
  }
  // Package lookup overlaps native runner enumeration rather than delaying it.
  let packages;
  await Promise.all([
    append(unique),
    nestedPackages(context,execute,previous?.packages,{force,now}).then(async result=>{packages=result;await append(result.paths.map(file=>[file,'package']));})
  ]);
  await Promise.all(work);
  const order=new Map(unique.map(([file],index)=>[file,index]));
  sources.sort((a,b)=>(order.get(a.file)??unique.length)-(order.get(b.file)??unique.length)||a.file.localeCompare(b.file));
  // Kept in memory only; never serialize project source text into shared state.
  Object.defineProperty(sources,'fingerprints',{value:fingerprints});
  Object.defineProperty(sources,'packages',{value:packages});
  return sources;
}
