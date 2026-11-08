// Session coordinator: shared promises coalesce copies without retaining their cx.
import {sourceKey} from './model.js';
export const cacheKey=context=>sourceKey(context,'');
export const metadataContext=(request,resolved)=>({...resolved,space:request?.space});
export class MetadataCache {
  constructor(limit=12){this.entries=new Map();this.limit=limit;}
  peek(key){return this.entries.get(key)?.value||null;}
  seed(key,value){if(!this.peek(key)){this.entries.set(key,{value});this.trim();}}
  trim(){for(const [key,entry] of this.entries){if(this.entries.size<=this.limit)return;if(!entry.promise)this.entries.delete(key);}}
  load(key,loader,now=Date.now(),force=false) {
    let entry=this.entries.get(key);
    if(entry){this.entries.delete(key);this.entries.set(key,entry);}
    if(entry?.promise)return entry.promise;
    if(!force&&entry?.value)return Promise.resolve(entry.value);
    if(!entry){entry={};this.entries.set(key,entry);}
    const previous=entry.value;
    entry.promise=loader(previous,force).then(result=>{entry.value={...result,checkedAt:now};return entry.value;}).finally(()=>{entry.promise=null;this.trim();});
    return entry.promise;
  }
}
export function sessionServices(){
  const key=Symbol.for('ciupaga.services.v3');
  return globalThis[key]??= {metadata:new MetadataCache(),checks:new Set(),cancellations:new Map(),opening:new Set()};
}
