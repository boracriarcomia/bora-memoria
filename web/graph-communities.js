/* Presentation only: communities use existing edges, never write note links. */
function buildGraphCommunities(items,edges,categoryOf,categories){
 const byId=new Map(items.map(n=>[n.id,n])),adj=new Map(items.map(n=>[n.id,new Map()]));
 const seen=new Set();
 for(const [a,b]of edges){if(a===b||!byId.has(a)||!byId.has(b))continue;const key=[a,b].sort().join('\u0000');if(seen.has(key))continue;seen.add(key);const w=a.startsWith('folder:')||b.startsWith('folder:')?.8:3;adj.get(a).set(b,w);adj.get(b).set(a,w);}
 const degree=new Map([...adj].map(([id,ns])=>[id,[...ns.values()].reduce((a,b)=>a+b,0)])),total=[...degree.values()].reduce((a,b)=>a+b,0)||1;
 const labels=new Map(items.map(n=>[n.id,n.id])),volume=new Map(degree),order=items.map(n=>n.id).sort((a,b)=>degree.get(b)-degree.get(a)||a.localeCompare(b));
 for(let pass=0;pass<18;pass++){let changes=0;for(const id of order){const k=degree.get(id);if(!k)continue;const old=labels.get(id),weights=new Map();for(const [other,w]of adj.get(id)){const label=labels.get(other);weights.set(label,(weights.get(label)||0)+w);}
  volume.set(old,volume.get(old)-k);const score=label=>(weights.get(label)||0)-1.12*k*(volume.get(label)||0)/total;
  let best=old,bestScore=score(old);for(const label of [...weights.keys()].sort()){const value=score(label);if(value>bestScore+1e-8){best=label;bestScore=value;}}
  labels.set(id,best);volume.set(best,(volume.get(best)||0)+k);if(best!==old)changes++;
 }if(!changes)break;}
 // Merge whole communities as well: local moves alone fragment long chains.
 for(let pass=0;pass<items.length;pass++){
  const between=new Map();for(const [id,neighbors]of adj)for(const [other,w]of neighbors){if(id>=other)continue;const a=labels.get(id),b=labels.get(other);if(a===b)continue;const key=[a,b].sort().join('\u0000');between.set(key,(between.get(key)||0)+w);}
  let best=null,gain=1e-8;for(const [key,w]of between){const [a,b]=key.split('\u0000'),value=w-1.12*(volume.get(a)||0)*(volume.get(b)||0)/total;if(value>gain){gain=value;best=[a,b];}}
  if(!best)break;const [a,b]=best;for(const [id,label]of labels)if(label===b)labels.set(id,a);volume.set(a,(volume.get(a)||0)+(volume.get(b)||0));volume.set(b,0);
 }
 const buckets=new Map();for(const n of items){const label=degree.get(n.id)?labels.get(n.id):'__isolated__';if(!buckets.has(label))buckets.set(label,[]);buckets.get(label).push(n);}
 const entries=[...buckets].sort((a,b)=>b[1].length-a[1].length||a[0].localeCompare(b[0])),membership=new Map(),groups=[];
 entries.forEach(([label,members],i)=>{const isolated=label==='__isolated__',id=isolated?'isolated':'community-'+i;const counts=new Map();for(const n of members){const key=categoryOf(n);counts.set(key,(counts.get(key)||0)+1);membership.set(n.id,id);}
  const top=[...counts].sort((a,b)=>b[1]-a[1]||a[0].localeCompare(b[0]))[0]?.[0],category=categories.find(c=>c.id===top)||{title:'Ideias',color:'#b6bdc9'};
  const hub=members.slice().sort((a,b)=>degree.get(b.id)-degree.get(a.id)||a.id.localeCompare(b.id))[0];
  let title=category.path?category.title:top==='general'?(hub?.title||'Ideias'):category.title,color=category.color;
  const corpus=members.map(n=>n.title||n.id).join(' ').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
  if(!category.path&&top==='general'){if(/\bskills?\b/.test(corpus)){title='Skills';color='#b18aff';}else if(/pesquisa|radar|fontes/.test(corpus)){title='Pesquisa';color='#52c9ee';}else if(/historico|checkpoint|retomada/.test(corpus)){title='Histórico';color='#a5a9b8';}}
  groups.push({id,title:isolated?'Sem ligações':title,color:isolated?'#8d96a6':color,x:400,y:280,isolated,count:members.length});
 });
 return{membership,groups,degree};
}
