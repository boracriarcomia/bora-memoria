'use strict';
// Spring motion is presentation only; never rewrites notes or their links.
const graphPositions=new Map();
let graphFrame=0,nodeDrag=null,skipGraphClick=false;
const graphAngle=0;
let graphInteractionUntil=0;
let graphTransformFrame=0;
function transformGraph(){
  graphInteractionUntil=performance.now()+900;
  if(graphTransformFrame)return;
  graphTransformFrame=requestAnimationFrame(()=>{
    graphTransformFrame=0;
    const group=$('map').querySelector(':scope > g');
    if(group)group.setAttribute('transform',`translate(${pan.x} ${pan.y}) translate(400 280) scale(${zoom}) translate(-400 -280)`);
  });
}
const reduceGraphMotion=matchMedia('(prefers-reduced-motion: reduce)');
let graphMode='light';
try{if(localStorage.getItem('bora.mapMode')==='animated')graphMode='animated';}catch{}
const graphAnimated=()=>graphMode==='animated'&&!reduceGraphMotion.matches;
let graphModeBeforeExpand='light';
// Resolve visual discs after fitting: fitting coordinates must not shrink their clearance.
function spaceGraphNodes(X,Y,R,W){
  const cell=72,N=X.length;
  for(let pass=0;pass<240;pass++){
    const grid=new Map();let overlap=0;
    for(let i=0;i<N;i++){
      const gx=Math.floor(X[i]/cell),gy=Math.floor(Y[i]/cell);
      for(let ox=-1;ox<=1;ox++)for(let oy=-1;oy<=1;oy++){
        for(const j of grid.get((gx+ox)+','+(gy+oy))||[]){
          let dx=X[i]-X[j],dy=Y[i]-Y[j],d=Math.hypot(dx,dy),minimum=R[i]+R[j]+4;
          if(d>=minimum)continue;
          if(d<.001){const a=(i+1)*2.39996;dx=Math.cos(a);dy=Math.sin(a);d=1;}
          const push=(minimum-d)*.54,wi=W[j]/(W[i]+W[j]),wj=1-wi;
          X[i]+=dx/d*push*wi;Y[i]+=dy/d*push*wi;
          X[j]-=dx/d*push*wj;Y[j]-=dy/d*push*wj;
          overlap=Math.max(overlap,minimum-d);
        }
      }
      X[i]=Math.max(28+R[i],Math.min(772-R[i],X[i]));
      Y[i]=Math.max(65+R[i],Math.min(525-R[i],Y[i]));
      const key=Math.floor(X[i]/cell)+','+Math.floor(Y[i]/cell);
      if(!grid.has(key))grid.set(key,[]);grid.get(key).push(i);
    }
    if(overlap<.15)break;
  }
}
// Visual categories never move files or rewrite their links.
const defaultMapCategories=[
  {id:'clients',title:'Gerenciamento de clientes',color:'#22b8a8',x:650,y:280},
  {id:'content',title:'Conteúdo',color:'#b18aff',x:210,y:150},
  {id:'projects',title:'Projetos e empresas',color:'#68aafa',x:465,y:235},
  {id:'guidance',title:'Orientações e marca',color:'#55b99b',x:645,y:420},
  {id:'logs',title:'Logs e evidências',color:'#e9a54e',x:130,y:380},
  {id:'history',title:'Início e histórico',color:'#a5a9b8',x:375,y:455},
  {id:'general',title:'Outras notas',color:'#e78fad',x:665,y:130}
];
let mapCategories=defaultMapCategories.slice();
function syncCentralFolders(){
  if(typeof syncContentColors==='function')syncContentColors();
  const central=[...new Set([...organizationData.folders.map(p=>p.split('/')[0]),...notes.filter(n=>n.id.includes('/')).map(n=>n.id.split('/')[0])])].sort((a,b)=>a.localeCompare(b,'pt-BR'));
  mapCategories=defaultMapCategories.filter(c=>c.id!=='clients').map(c=>central.includes(c.title)?{...c,title:c.title+' · sem pasta'}:c).concat(central.map((path,i)=>({id:'central-'+i,title:path,color:folderColor(path,neuralColor(path)),path,x:400,y:280})));
  const select=$('mapCategory'),previous=select.value;
  select.replaceChildren();
  const all=document.createElement('option');all.value='';all.textContent='Todas as categorias';select.append(all);
  for(const c of mapCategories){const option=document.createElement('option');option.value=c.id;option.textContent=c.title;select.append(option);}
  select.value=mapCategories.some(c=>c.id===previous)?previous:'';
}
function mapCategory(n){
  // Client records have their own cluster, including folders and descendants.
  const clientPath=(n.folderNode?n.path:n.id).normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
  const central=mapCategories.find(c=>c.path&&(clientPath===c.path.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase()||clientPath.startsWith(c.path.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase()+'/')));
  if(central)return central.id;
  if(!n.folderNode&&typeof organizationData!=='undefined'){
    const chosen=organizationData.notes[n.id]?.category;
    const explicit={content:'content',youtube:'content',instagram:'content',projects:'projects',guidance:'guidance',brand:'guidance',continuity:'history'};
    if(explicit[chosen])return explicit[chosen];
  }
  const path=(n.folderNode?n.path:n.id).normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
  const root=path.split('/')[0];
  if(/^(conteudo|blog|cursos)(\b|\/)/.test(root))return 'content';
  if(/^(chegou lead|clientes|projetos|empresas)(\b|\/)/.test(root))return 'projects';
  if(/^(identidade|referencias|orientacoes)(\b|\/)/.test(root))return 'guidance';
  if(/^(evidencias|logs)(\b|\/)/.test(root))return 'logs';
  if(/^(inicio|historico)(\b|\/)/.test(root))return 'history';
  if(/^(agents|cofre-e-perfis)\.md$/.test(root))return 'guidance';
  if(/^(checkpoint|retomada|continuidade|registro de execucao)\b/.test(root))return 'history';
  if(/^(orientacao|regras|manual|biblioteca da marca|padrao|guia)/.test(root))return 'guidance';
  if(/auditoria|validacao|conferencia|teste|relatorio/.test(root))return 'logs';
  if(/retomada|checkpoint|continuidade|andamento|instala|atualiza|revisao|memoria na bandeja/.test(root))return 'history';
  return 'general';
}
// Filters affect presentation only. Folder matching includes descendants, not similar prefixes.
function filterMapNotes(items,category,folder,hideHistory){
  return items.filter(n=>(!category||mapCategory(n)===category)&&
    (!folder||(folder==='@root'?!n.id.includes('/'):n.id.startsWith(folder+'/')))&&
    (!hideHistory||mapCategory(n)!=='history'));
}
function syncMapFolders(){
  const select=$('mapFolder'),previous=select.value;
  const paths=new Set();
  notes.forEach(n=>{const parts=n.id.split('/').slice(0,-1);for(let i=1;i<=parts.length;i++)paths.add(parts.slice(0,i).join('/'));});
  const values=['','@root',...[...paths].sort((a,b)=>a.localeCompare(b,'pt-BR'))];
  if(select.dataset.paths===JSON.stringify(values))return;
  select.replaceChildren(...values.map(value=>{const option=document.createElement('option');option.value=value;option.textContent=value==='@root'?'Notas sem pasta':value||'Todas as pastas';return option;}));
  select.value=values.includes(previous)?previous:'';select.dataset.paths=JSON.stringify(values);
}
renderGraph=function(){
  syncCentralFolders();
  const renderStarted=performance.now();
  if(typeof syncContentColors==='function')syncContentColors();
  cancelAnimationFrame(graphFrame);
  $('map')._disposeHover?.();
  const allEdges=edges(),selected=current?.id;
  let shown=notes;
  if(focus&&selected){const ids=new Set([selected]);allEdges.forEach(([a,b])=>{if(a===selected)ids.add(b);if(b===selected)ids.add(a);});shown=notes.filter(n=>ids.has(n.id));}
  syncMapFolders();
  shown=filterMapNotes(shown,$('mapCategory').value,$('mapFolder').value,$('mapHideHistory').checked);
  const shownCount=shown.length;
  $('mapScope').textContent=shownCount+' de '+notes.length+' notas carregadas';
  $('mapFilteredEmpty').hidden=!notes.length||shownCount>0;
  const folderSet=new Set();
  shown.forEach(n=>{const parts=n.id.split('/').slice(0,-1);for(let i=1;i<=parts.length;i++)folderSet.add(parts.slice(0,i).join('/'));});
  if(!$('mapCategory').value&&!$('mapFolder').value&&!focus)organizationData.folders.forEach(path=>folderSet.add(path));
  const folders=[...folderSet].sort();
  const folderNodes=folders.map(path=>({id:'folder:'+path,title:path.split('/').at(-1),folderNode:true,path,depth:path.split('/').length}));
  for(const f of folderNodes){const parent=f.path.split('/').slice(0,-1).join('/');if(parent)allEdges.push(['folder:'+parent,f.id]);}
  for(const n of shown){const parent=n.id.split('/').slice(0,-1).join('/');if(parent)allEdges.push(['folder:'+parent,n.id]);}
  shown=[...folderNodes,...shown];
  const topology=buildGraphCommunities(shown,allEdges,mapCategory,mapCategories);
  const layoutGroups=topology.groups;
  const visualGroups=topology.membership;
  const rootOf=n=>topology.membership.get(n.id);
  const roots=layoutGroups.map(c=>c.id);
  const graph=$('map');graph.replaceChildren();
  graph.dataset.highlightActive='false';
  graph.dataset.buildCount=String(Number(graph.dataset.buildCount||0)+1);
  const group=svg('g',{transform:`translate(${pan.x} ${pan.y}) translate(400 280) scale(${zoom}) translate(-400 -280)`});graph.append(group);
  const ids=new Set(shown.map(n=>n.id));
  const visible=allEdges.filter(([a,b])=>ids.has(a)&&ids.has(b));
  const peersByRoot=new Map(roots.map(root=>[root,shown.filter(n=>rootOf(n)===root)]));
  const centers=new Map(layoutGroups.map(c=>[c.id,{x:c.x,y:c.y}]));
  // Arrange communities by their real bridges, while reserving room for each nucleus.
  {
    const active=roots.filter(r=>r!=='isolated'),radius=r=>22+12*Math.sqrt(peersByRoot.get(r).length);
    const bridges=new Map();for(const [a,b]of visible){const x=rootOf(shown.find(n=>n.id===a)),y=rootOf(shown.find(n=>n.id===b));if(x===y)continue;const key=[x,y].sort().join('|');bridges.set(key,(bridges.get(key)||0)+1);}
    const ordered=[];const remaining=new Set(active);
    while(remaining.size){const next=[...remaining].sort((a,b)=>{const score=id=>ordered.reduce((sum,other)=>sum+(bridges.get([id,other].sort().join('|'))||0),0);return score(b)-score(a)||peersByRoot.get(b).length-peersByRoot.get(a).length||a.localeCompare(b);})[0];ordered.push(next);remaining.delete(next);}
    const orbit=Math.max(90,active.reduce((sum,r)=>sum+radius(r)*2+35,0)/(2*Math.PI));
    ordered.forEach((r,i)=>{const angle=i*2*Math.PI/Math.max(1,ordered.length);centers.set(r,{x:400+Math.cos(angle)*orbit,y:280+Math.sin(angle)*orbit});});
    for(let pass=0;pass<100;pass++){
      for(const [key,count]of bridges){const [a,b]=key.split('|'),x=centers.get(a),y=centers.get(b);const dx=y.x-x.x,dy=y.y-x.y,d=Math.hypot(dx,dy)||1,target=radius(a)+radius(b)+45,f=(d-target)*.006*Math.min(3,Math.sqrt(count));x.x+=dx/d*f;x.y+=dy/d*f;y.x-=dx/d*f;y.y-=dy/d*f;}
      for(let i=0;i<active.length;i++)for(let j=i+1;j<active.length;j++){const a=active[i],b=active[j],x=centers.get(a),y=centers.get(b),dx=y.x-x.x,dy=y.y-x.y,d=Math.hypot(dx,dy)||1,minimum=radius(a)+radius(b)+35;if(d<minimum){const f=(minimum-d)*.5;x.x-=dx/d*f;x.y-=dy/d*f;y.x+=dx/d*f;y.y+=dy/d*f;}}
    }
  }
  const localCounters=new Map();
  const placements=shown.map(n=>({side:roots.indexOf(rootOf(n))%2,index:0}));
  const hemisphereCounts=[1,1];
  // A sparse overview summarizes existing cross-category links, never invents them.
  const categoryLinks=new Map();
  const categoryById=new Map(shown.map(n=>[n.id,rootOf(n)]));
  for(const [a,b] of visible){
    const left=categoryById.get(a),right=categoryById.get(b);
    if(left===right)continue;
    const key=[left,right].sort().join('|');categoryLinks.set(key,(categoryLinks.get(key)||0)+1);
  }
  const components=new Map(roots.map(id=>[id,id]));
  const component=id=>{while(components.get(id)!==id)id=components.get(id);return id;};
  for(const [key,count] of [...categoryLinks].sort((a,b)=>b[1]-a[1]||a[0].localeCompare(b[0]))){
    const [left,right]=key.split('|'),ca=component(left),cb=component(right);
    if(ca===cb)continue;
    components.set(ca,cb);
    const a=centers.get(left),b=centers.get(right),dx=b.x-a.x,dy=b.y-a.y,d=Math.hypot(dx,dy)||1,gap=Math.min(90,d*.3);
    const x1=a.x+dx/d*gap,y1=a.y+dy/d*gap,x2=b.x-dx/d*gap,y2=b.y-dy/d*gap;
    const line=svg('path',{class:'map-category-link',fill:'none',d:`M ${x1} ${y1} Q ${(x1+x2)/2+14} ${(y1+y2)/2-14} ${x2} ${y2}`,'data-category-from':left,'data-category-to':right});
    const title=svg('title',{});title.textContent=count+' ligações entre estas categorias';line.append(title);group.append(line);
  }
  const defs=svg('defs',{});
  for(const c of layoutGroups){
    if(!roots.includes(c.id)||c.isolated||c.count<4)continue;
    const grad=svg('radialGradient',{id:'halo-'+c.id});
    grad.append(svg('stop',{offset:'0%','stop-color':c.color,'stop-opacity':.11}),svg('stop',{offset:'100%','stop-color':c.color,'stop-opacity':0}));
    defs.append(grad);
  }
  group.prepend(defs);
  let haloAnchor=defs;
  layoutGroups.forEach((c,i)=>{
    if(!roots.includes(c.id)||c.isolated||c.count<4)return;
    const halo=svg('circle',{class:'map-halo',cx:c.x,cy:c.y,r:Math.min(120,70+Math.sqrt(peersByRoot.get(c.id).length)*6),fill:`url(#halo-${c.id})`});
    halo.style.animationDelay=(-i*1.3)+'s';
    haloAnchor.after(halo);haloAnchor=halo;
  });
  for(const c of layoutGroups){
    if(!roots.includes(c.id)||c.isolated||c.count<4)continue;
    const heading=svg('text',{class:'map-category-label',x:c.x,y:c.y-102,'text-anchor':'middle','data-category':c.id});
    heading.textContent=c.title;
    heading.style.setProperty('--category-color',c.color);
    group.append(heading);
  }
  // Force layout computed once per render: folders become hubs with notes orbiting them. Visual only.

  const layoutStarted=performance.now();

  const layout=(()=>{

    const idx=new Map(shown.map((n,i)=>[n.id,i])),N=shown.length;

    const X=new Float32Array(N),Y=new Float32Array(N),W=new Float32Array(N),deg=new Array(N).fill(0),es=[];

    for(const [a,b] of visible){const i=idx.get(a),j=idx.get(b);if(i===undefined||j===undefined)continue;es.push([i,j,(a.startsWith('folder:')||b.startsWith('folder:'))?1:0]);deg[i]++;deg[j]++;}

    const initialCounts=new Map();const outerRadius=Math.max(180,...[...centers.values()].map(c=>Math.hypot(c.x-400,c.y-280)))+110;
    shown.forEach((n,i)=>{const key=rootOf(n),c=centers.get(key),local=initialCounts.get(key)||0;initialCounts.set(key,local+1);const ang=local*2.39996,r=key==='isolated'?outerRadius:12+Math.sqrt(local)*7;X[i]=c.x+Math.cos(ang)*r;Y[i]=c.y+Math.sin(ang)*r;W[i]=n.folderNode?(n.depth===1?3+Math.min(7,deg[i]*.18):1.6+Math.min(2.5,deg[i]*.07)):1;});

    const iterations=N>400?120:220;

    for(let it=0;it<iterations;it++){

      const alpha=1-it/iterations;

      for(let i=0;i<N;i++)for(let j=i+1;j<N;j++){

        let dx=X[i]-X[j],dy=Y[i]-Y[j],d2=dx*dx+dy*dy;if(d2>6400)continue;if(d2<25){dx=(i-j)%2?1:-1;dy=1;d2=25;}

        const d=Math.sqrt(d2),f=W[i]*W[j]*200/d2*(alpha+.15),fx=dx/d*f,fy=dy/d*f;

        X[i]+=fx/W[i];Y[i]+=fy/W[i];X[j]-=fx/W[j];Y[j]-=fy/W[j];

      }

      for(const [i,j,k] of es){

        const dx=X[j]-X[i],dy=Y[j]-Y[i],d=Math.hypot(dx,dy)||1;

        const cross=rootOf(shown[i])!==rootOf(shown[j]);

        const len=k?58+Math.sqrt(deg[i]+deg[j])*2:65;

        const f=(d-len)*(cross?.003:.1)*(alpha+.2),fx=dx/d*f,fy=dy/d*f;

        X[i]+=fx/W[i]*.6;Y[i]+=fy/W[i]*.6;X[j]-=fx/W[j]*.6;Y[j]-=fy/W[j]*.6;

      }

      shown.forEach((n,i)=>{if(rootOf(n)==='isolated')return;const c=centers.get(rootOf(n));X[i]+=(c.x-X[i])*.075*W[i]/3;Y[i]+=(c.y-Y[i])*.075*W[i]/3;});

    }

    // Fit the whole network inside the view instead of crushing groups against the edges.

    if(N){

      let x0=Infinity,x1=-Infinity,y0=Infinity,y1=-Infinity;

      for(let i=0;i<N;i++){x0=Math.min(x0,X[i]);x1=Math.max(x1,X[i]);y0=Math.min(y0,Y[i]);y1=Math.max(y1,Y[i]);}

      const s=Math.min(720/Math.max(1,x1-x0),440/Math.max(1,y1-y0),1.5),cx=(x0+x1)/2,cy=(y0+y1)/2;

      for(let i=0;i<N;i++){X[i]=400+(X[i]-cx)*s;Y[i]=298+(Y[i]-cy)*s;}

    }

    // Large folder hubs reserve room for their aura, label and gentle drift.

    const clearance=shown.map(n=>n.folderNode?(n.depth===1?29:11):6);

    spaceGraphNodes(X,Y,clearance,W);

    return {X,Y,deg,scale:1};

  })();

  graph.dataset.groupCount=String(roots.length);
  graph.dataset.layoutTime=(performance.now()-layoutStarted).toFixed(2);
  // Titles, halos and overview links follow the actual computed groups.
  const categoryBounds=new Map();
  for(const root of roots){
    const indexes=shown.map((n,i)=>rootOf(n)===root?i:-1).filter(i=>i>=0);
    const xs=indexes.map(i=>layout.X[i]),ys=indexes.map(i=>layout.Y[i]);
    categoryBounds.set(root,{x:(Math.min(...xs)+Math.max(...xs))/2,y:(Math.min(...ys)+Math.max(...ys))/2,top:Math.min(...ys),w:Math.max(...xs)-Math.min(...xs),h:Math.max(...ys)-Math.min(...ys)});
  }
  for(const label of group.querySelectorAll('.map-category-label')){
    const bound=categoryBounds.get(label.dataset.category);
    const hubs=shown.map((n,i)=>n.folderNode&&n.depth===1&&rootOf(n)===label.dataset.category?i:-1).filter(i=>i>=0);
    const hx=hubs.length?hubs.reduce((sum,i)=>sum+layout.X[i],0)/hubs.length:bound.x;
    const hy=Math.min(bound.top-23,hubs.length?Math.min(...hubs.map(i=>layout.Y[i]))-46:bound.top-23);
    label.setAttribute('x',bound.x);label.setAttribute('y',Math.max(22,bound.top-18));label.style.setProperty('--category-color',layoutGroups.find(c=>c.id===label.dataset.category).color);
  }
  for(const line of group.querySelectorAll('.map-category-link')){
    const a=categoryBounds.get(line.dataset.categoryFrom),b=categoryBounds.get(line.dataset.categoryTo);
    const dx=b.x-a.x,dy=b.y-a.y,d=Math.hypot(dx,dy)||1,gap=Math.min(85,d*.3);
    const x1=a.x+dx/d*gap,y1=a.y+dy/d*gap,x2=b.x-dx/d*gap,y2=b.y-dy/d*gap;
    line.setAttribute('d',`M ${x1} ${y1} Q ${(x1+x2)/2+14} ${(y1+y2)/2-14} ${x2} ${y2}`);
  }
  for(const halo of group.querySelectorAll('.map-halo')){

    const root=halo.getAttribute('fill').slice(10,-1),bound=categoryBounds.get(root);

    if(bound){halo.setAttribute('cx',bound.x);halo.setAttribute('cy',bound.y);halo.setAttribute('r',Math.max(45,Math.max(bound.w,bound.h)*.62+25));}

  }

  const points=shown.map((n,i)=>{
    if(!graphPositions.has(n.id)){const a=2*Math.PI*i/Math.max(shown.length,1)-Math.PI/2,r=shown.length===1?0:190;graphPositions.set(n.id,{x:400+Math.cos(a)*r,y:275+Math.sin(a)*r,vx:0,vy:0});}
    const p=graphPositions.get(n.id);p.id=n.id;
    const placement=placements[i];
    p.side=placement.side;
    const root=rootOf(n),localIndex=localCounters.get(root)||0;
    localCounters.set(root,localIndex+1);
    p.ax=layout.X[i];
    p.ay=layout.Y[i];
    p.phase=roots.indexOf(root)*1.7+localIndex*.19;
    if(p.neural!==7||p.layoutCount!==shown.length){p.x=p.ax;p.y=p.ay;p.vx=0;p.vy=0;p.z=0;p.neural=7;p.layoutCount=shown.length;}
    return p;
  });
  const lines=visible.map(([a,b])=>{const folder=a.startsWith('folder:')||b.startsWith('folder:');const principal=id=>id.startsWith('folder:')&&!id.slice(7).includes('/');const main=principal(a)&&principal(b);const cross=categoryById.get(a)!==categoryById.get(b);const line=svg('path',{class:(folder?'map-folder-link':'map-idea-link')+(main?' map-main-link':'')+(cross?' map-cross-link':''),fill:'none','data-from':a,'data-to':b});group.append(line);return {a:graphPositions.get(a),b:graphPositions.get(b),line,bend:folder&&!cross?.1:.24};});
  const adjacency=new Map(shown.map(n=>[n.id,new Set()]));
  for(const [a,b] of visible){adjacency.get(a).add(b);adjacency.get(b).add(a);}
  const nodes=shown.map(n=>{
    const category=layoutGroups.find(c=>c.id===rootOf(n));const p=graphPositions.get(n.id),g=svg('g',{class:'node',...(n.folderNode?{'data-folder':n.path}:{'data-note':n.id}),tabindex:0,role:'button','aria-label':'Abrir '+n.title});
    const contentPath=n.folderNode?n.path:n.id.split('/').slice(0,-1).join('/');
    const color=category.color;
    g.dataset.category=category.id;g.style.setProperty('--category-color',color);if(visualGroups.has(n.id))g.dataset.visualGroup=visualGroups.get(n.id);
    const fullTitle=svg('title',{});fullTitle.textContent=n.title;g.append(fullTitle);
    const degree=adjacency.get(n.id).size;
    const topHub=n.folderNode&&n.depth===1;
    const visualScale=Math.min(1,layout.scale);
    const nodeRadius=(topHub?Math.min(11,6+Math.sqrt(degree)*1.1):n.folderNode?Math.min(5.5,3.4+Math.sqrt(degree)*.5):Math.min(3.8,2.3+Math.sqrt(Math.max(0,degree))*.4)+(n.id===selected?1.5:0))*visualScale;
    if(topHub)g.append(svg('circle',{class:'map-hub-aura map-hub-breathe',r:nodeRadius*2.3,fill:color}));
    g.append(svg('circle',{class:topHub?'map-hub':n.folderNode?'map-hub map-subhub':'map-leaf',r:nodeRadius,fill:color}));
    const mainNote=n.id==='Inicio.md';
    const label=svg('text',{class:n.folderNode?'folder-label':'note-label',y:16,'text-anchor':'middle'});label.textContent=topHub?n.title:(n.title.length>18?n.title.slice(0,17)+'…':n.title);const radius=nodeRadius;label.setAttribute('y',radius+(n.folderNode?11:8));label.style.fontSize=((n.folderNode||mainNote?9.5:Math.min(7,4.5+radius*.45))*visualScale)+'px';label.style.fontWeight=n.folderNode?'500':'400';const labels=typeof organizationData==='undefined'?'all':(organizationData.labels||'all');if(labels==='none')label.classList.add('map-label-hidden');else if(labels==='main'&&!((n.folderNode&&n.depth===1)||mainNote))label.classList.add('map-label-secondary');if((topHub&&category.title===n.title)||(!n.folderNode&&n.title===n.id.split('/').at(-2)))label.classList.add('map-label-hidden');g.append(label); // Saved label preference, without changing project content.
    const highlight=()=>setWebFocus(n.id);
    g.addEventListener('focus',()=>{webPointer=null;highlight();});
    g.addEventListener('blur',()=>setWebFocus(null));
    g.addEventListener('pointerdown',e=>{if(e.button!==0)return;e.stopPropagation();webPointer={x:e.clientX,y:e.clientY};highlight();graph.classList.add('map-grabbing');nodeDrag={p,startX:e.clientX,startY:e.clientY,moved:false,activate:()=>{if(n.folderNode)openGraphFolder(n);else{openNote(n);selectPanel('note');}}};g.setPointerCapture(e.pointerId);});
    g.addEventListener('contextmenu',e=>{e.preventDefault();e.stopPropagation();revealGraphItem(n);});
    g.addEventListener('click',()=>{if(skipGraphClick){skipGraphClick=false;return;}if(n.folderNode){openGraphFolder(n);}else {openNote(n);selectPanel('note');}});
    g.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();if(n.folderNode){openGraphFolder(n);}else {openNote(n);selectPanel('note');}}});
    {
      const lens=svg('g',{class:'map-consultation-lens','aria-hidden':'true'});
      lens.append(svg('circle',{cx:17,cy:-19,r:6,fill:'#181421',stroke:'#ffd16a','stroke-width':1.6}),svg('path',{d:'M 21 -15 L 26 -10',stroke:'#ffd16a','stroke-width':2,'stroke-linecap':'round'}));
      g.append(lens);
    }
    group.append(g);return {p,g};
  });
  // Local web reveal follows real adjacency; no notes or edges are written.
  let webId=null,webFrame=0,webClear=0,webPointer=null;
  const webLayer=svg('g',{class:'map-web-layer','aria-hidden':'true'});group.append(webLayer);
  let webPaths=[];
  function setWebFocus(id){
    if(id===webId){updateWeb();return;}
    webId=id;graph.dataset.highlightActive=String(!!id);graph.dataset.webFocus=id||'';
    const chosen=id?lines.filter(l=>l.a.id===id||l.b.id===id).sort((a,b)=>Math.hypot(a.a.x-a.b.x,a.a.y-a.b.y)-Math.hypot(b.a.x-b.b.x,b.a.y-b.b.y)).slice(0,10):[];
    const connected=new Set(id?[id]:[]);chosen.forEach(l=>{connected.add(l.a.id);connected.add(l.b.id);});
    for(const {p,g} of nodes){g.classList.toggle('map-related',connected.has(p.id));g.classList.toggle('map-dimmed',!!id&&!connected.has(p.id));}
    const old=webLayer.querySelectorAll('.web-current');
    for(const line of old){line.classList.remove('web-current');line.classList.add('web-leaving');setTimeout(()=>line.remove(),650);}
    // Bound fading trails even when rapidly crossing many nodes.
    while(webLayer.children.length>30)webLayer.firstElementChild.remove();
    webPaths=chosen.map(l=>{
      const path=svg('path',{class:'map-web-thread web-current',fill:'none',pathLength:1});
      const reverse=l.b.id===id;path.style.setProperty('--edge',layoutGroups.find(c=>c.id===categoryById.get(id))?.color||'#55b99b');
      path.dataset.from=l.a.id;path.dataset.to=l.b.id;webLayer.append(path);return {l,path,reverse};
    });
    updateWeb();
  }
  function updateWeb(){
    // The hand is a temporary visual origin, never a saved note or connection.
    const matrix=webPointer?group.getScreenCTM():null;
    const hand=matrix?new DOMPoint(webPointer.x,webPointer.y).matrixTransform(matrix.inverse()):null;
    for(const {l,path,reverse} of webPaths){
      const node=reverse?l.b:l.a,b=reverse?l.a:l.b,a=hand?{sx:hand.x,sy:hand.y}:node;
      const dx=b.sx-a.sx,dy=b.sy-a.sy,bend=reverse?-l.bend:l.bend;
      path.dataset.origin=hand?'pointer':'node';
      path.setAttribute('d',`M ${a.sx} ${a.sy} Q ${(a.sx+b.sx)/2-dy*bend} ${(a.sy+b.sy)/2+dx*bend} ${b.sx} ${b.sy}`);
    }
  }
  function hoverAt(){
    webFrame=0;if(!webPointer||nodeDrag||drag)return;
    const matrix=group.getScreenCTM();if(!matrix)return;
    let nearest=null,distance=24;
    for(const {p} of nodes){const pos=new DOMPoint(p.sx,p.sy).matrixTransform(matrix),d=Math.hypot(pos.x-webPointer.x,pos.y-webPointer.y);const score=d-(p.id===webId?3:0);if(d<24&&score<distance){distance=score;nearest=p.id;}}
    setWebFocus(nearest);
  }
  function webMove(e){if(e.pointerType==='touch')return;clearTimeout(webClear);webPointer={x:e.clientX,y:e.clientY};if(nodeDrag){updateWeb();return;}if(!webFrame)webFrame=requestAnimationFrame(hoverAt);}
  function webLeave(){webPointer=null;cancelAnimationFrame(webFrame);webFrame=0;setWebFocus(null);}
  graph.addEventListener('pointermove',webMove);graph.addEventListener('pointerleave',webLeave);
  graph._clearWeb=()=>setWebFocus(null);
  graph._disposeHover=()=>{cancelAnimationFrame(webFrame);clearTimeout(webClear);graph.removeEventListener('pointermove',webMove);graph.removeEventListener('pointerleave',webLeave);};
  // Synapse effect: signals hop along real links and make notes fire. Purely visual.
  const nodeById=new Map(nodes.map(o=>[o.p.id,o]));
  for(const l of lines){const o=nodeById.get(l.line.dataset.to)||nodeById.get(l.line.dataset.from);if(o)l.line.style.setProperty('--edge',o.g.style.getPropertyValue('--category-color'));}
  const outgoing=new Map();
  for(const l of lines){for(const [from,to,rev] of [[l.a,l.b,false],[l.b,l.a,true]]){if(!outgoing.has(from.id))outgoing.set(from.id,[]);outgoing.get(from.id).push({l,rev});}}
  const pulseIds=[...outgoing.keys()];
  const pulses=[];
  const categorySeeds=roots.map(root=>pulseIds.find(id=>categoryById.get(id)===root)).filter(Boolean);
  const pulseCount=reduceGraphMotion.matches||!pulseIds.length?0:Math.min(26,Math.max(8,categorySeeds.length,Math.round(lines.length/12)));
  const curveControl=(a,b,bend=.18)=>{const dx=b.sx-a.sx,dy=b.sy-a.sy;return {x:(a.sx+b.sx)/2-dy*bend,y:(a.sy+b.sy)/2+dx*bend};};
  const bez=(a,c,b,t)=>{const u=1-t;return {x:u*u*a.sx+2*u*t*c.x+t*t*b.sx,y:u*u*a.sy+2*u*t*c.y+t*t*b.sy};};
  function pickRoute(from){const opts=outgoing.get(from);return opts[Math.floor(Math.random()*opts.length)];}
  function fire(id){
    const o=nodeById.get(id);if(!o)return;
    o.g.classList.add('fire');setTimeout(()=>o.g.classList.remove('fire'),600);
    const ring=svg('circle',{class:'map-ripple',cx:o.p.sx.toFixed(1),cy:o.p.sy.toFixed(1),r:4});
    ring.style.setProperty('--category-color',o.g.style.getPropertyValue('--category-color'));
    group.insertBefore(ring,group.querySelector('.node'));setTimeout(()=>ring.remove(),1100);
  }
  const catColor=id=>nodeById.get(id)?.g.style.getPropertyValue('--category-color')||'#fff';
  for(let i=0;i<pulseCount;i++){
    const start=categorySeeds[i]||pulseIds[Math.floor(Math.random()*pulseIds.length)],route=pickRoute(start);
    const dots=[2,1.5,1.1,.75].map((r,k)=>{const d=svg('circle',{class:k?'map-pulse map-pulse-tail':'map-pulse',r});d.style.opacity=String(1-k*.22);group.append(d);return d;});
    pulses.push({route,t:-Math.random()*1.5,speed:.006+Math.random()*.008,dots,from:start});
  }
  function stepPulses(elapsed){
    const k=Math.min(3,elapsed/32);
    for(const pl of pulses){
      pl.t+=pl.speed*k;
      const {l,rev}=pl.route,A=rev?l.b:l.a,B=rev?l.a:l.b;
      if(pl.t<0){pl.dots.forEach(d=>d.style.visibility='hidden');continue;}
      if(pl.t>=1){fire(B.id);pl.from=B.id;pl.route=pickRoute(B.id);pl.t=0;pl.speed=.006+Math.random()*.008;continue;}
      const c=curveControl(l.a,l.b,pl.route.l.bend),color=catColor(B.id);
      pl.dots.forEach((d,i)=>{const tt=Math.max(0,pl.t-i*.03),pos=bez(l.a,c,l.b,rev?1-tt:tt);d.style.visibility='visible';d.setAttribute('cx',pos.x.toFixed(1));d.setAttribute('cy',pos.y.toFixed(1));d.style.fill=i?color:'#fff';d.style.color=color;});
    }
  }
  let drawCount=0;
  const draw=()=>{
    graph.dataset.rotationAngle=graphAngle.toFixed(4);
    const cosine=Math.cos(graphAngle),sine=Math.sin(graphAngle);
    const now=performance.now(),drift=graphAnimated();
    for(const p of points){const x=p.x-400,z=p.z||0;p.depth=-x*sine+z*cosine;p.scale=700/(700-p.depth);const dx=drift&&nodeDrag?.p!==p?Math.sin(now*.0007+(p.phase||0)*2)*2.6:0,dy=drift&&nodeDrag?.p!==p?Math.cos(now*.0005+(p.phase||0)*3)*2.6:0;p.sx=400+(x*cosine+z*sine)*p.scale+dx;p.sy=275+(p.y-275)*p.scale+dy;}
    // Every frame: edges follow the drifting nodes without lagging behind.
    for(const {a,b,line,bend} of lines){const c=curveControl(a,b,bend);line.setAttribute('d',`M ${a.sx.toFixed(1)} ${a.sy.toFixed(1)} Q ${c.x.toFixed(1)} ${c.y.toFixed(1)} ${b.sx.toFixed(1)} ${b.sy.toFixed(1)}`);}
    for(const {p,g} of nodes)g.setAttribute('transform',`translate(${p.sx.toFixed(1)} ${p.sy.toFixed(1)}) scale(${p.scale.toFixed(3)})`);
    updateWeb();
  };
  let frames=0;
  let previousFrame=0;
  const frameTimes=[],workTimes=[];
  const highlightWork=[];
  function springStep(elapsed){
    if(reduceGraphMotion.matches)return;
    const dt=Math.min(1.8,Math.max(.3,elapsed/32));
    // Each edge transfers displacement, avoiding all-pairs repulsion.
    // No idle movement: category positions remain stable.
    for(const p of points){p.fx=(p.ax-p.x)*.018;p.fy=(p.ay-p.y)*.018;}
    for(const {a,b} of lines){
      const fx=((b.x-b.ax)-(a.x-a.ax))*.012,fy=((b.y-b.ay)-(a.y-a.ay))*.012;
      a.fx+=fx;a.fy+=fy;b.fx-=fx;b.fy-=fy;
    }
    for(const p of points){
      if(nodeDrag?.p===p)continue;
      p.vx=((p.vx||0)+p.fx*dt)*Math.pow(.88,dt);
      p.vy=((p.vy||0)+p.fy*dt)*Math.pow(.88,dt);
      p.x+=Math.max(-12,Math.min(12,p.vx))*dt;
      p.y+=Math.max(-12,Math.min(12,p.vy))*dt;
    }
  }
  function tick(){
    const started=performance.now();
    if(document.hidden||window.boraBackground)return;
    if(previousFrame&&started-previousFrame<32){graphFrame=requestAnimationFrame(tick);return;}
    const elapsed=previousFrame?Math.min(80,started-previousFrame):0;
    if(previousFrame)frameTimes.push(started-previousFrame);
    previousFrame=started;
    if(frameTimes.length>90)frameTimes.shift();
    springStep(elapsed||32);draw();
    const interacting=!!nodeDrag||started<graphInteractionUntil;
    if((graphAnimated()||interacting)&&!reduceGraphMotion.matches)stepPulses(elapsed||32);
    else for(const pulse of pulses)for(const dot of pulse.dots)dot.style.visibility='hidden';
    frames++;
    workTimes.push(performance.now()-started);if(workTimes.length>90)workTimes.shift();
    if(graph.dataset.highlightActive==='true'){
      highlightWork.push(performance.now()-started);if(highlightWork.length>90)highlightWork.shift();
      if(highlightWork.length>=30){graph.dataset.highlightWorkMean=(highlightWork.reduce((a,b)=>a+b,0)/highlightWork.length).toFixed(2);graph.dataset.highlightSamples=String(highlightWork.length);}
    }
    if(frames%60===0&&frameTimes.length){
      const sorted=[...frameTimes].sort((a,b)=>a-b);
      graph.dataset.frameMean=(frameTimes.reduce((a,b)=>a+b,0)/frameTimes.length).toFixed(2);
      graph.dataset.frameP95=sorted[Math.floor(sorted.length*.95)].toFixed(2);
      graph.dataset.workMean=(workTimes.reduce((a,b)=>a+b,0)/workTimes.length).toFixed(2);
    }
    const settling=points.some(p=>Math.abs(p.vx||0)+Math.abs(p.vy||0)>.03||Math.abs(p.x-p.ax)+Math.abs(p.y-p.ay)>.2);
    const running=!!nodeDrag||(!reduceGraphMotion.matches&&(graphAnimated()||settling||interacting));
    graph.dataset.renderState=running?'running':'idle';
    graphFrame=running?requestAnimationFrame(tick):0;
  }
  draw();graphFrame=requestAnimationFrame(tick);
  graph.dataset.renderTime=(performance.now()-renderStarted).toFixed(2);
  graph._wake=()=>{frames=0;previousFrame=0;cancelAnimationFrame(graphFrame);graph.dataset.renderState='running';graphFrame=requestAnimationFrame(tick);};
  $('connections').textContent=visible.length+' ligações · pastas e notas';$('mapempty').hidden=notes.length>0;$('focus').textContent=focus?'Conexões desta nota':'Todas as notas';
};
$('map').addEventListener('pointermove',e=>{
  if(!nodeDrag)return;
  if(!nodeDrag.moved&&Math.hypot(e.clientX-nodeDrag.startX,e.clientY-nodeDrag.startY)<=5)return;
  const rect=$('map').getBoundingClientRect(),scale=Math.min(rect.width/800,rect.height/560),left=rect.left+(rect.width-800*scale)/2,top=rect.top+(rect.height-560*scale)/2;
  const sx=((e.clientX-left)/scale-pan.x-400)/zoom,sy=((e.clientY-top)/scale-pan.y-280)/zoom+280;
  const p=nodeDrag.p,cx=sx/p.scale,depth=p.depth;
  p.x=Math.max(40,Math.min(760,400+cx*Math.cos(graphAngle)-depth*Math.sin(graphAngle)));
  p.z=cx*Math.sin(graphAngle)+depth*Math.cos(graphAngle);
  p.y=Math.max(40,Math.min(500,275+(sy-275)/p.scale));
  nodeDrag.p.vx=0;nodeDrag.p.vy=0;
  if(Math.hypot(e.clientX-nodeDrag.startX,e.clientY-nodeDrag.startY)>5)nodeDrag.moved=true;
  $('map')._wake?.();
});
function releaseGraphNode(event){if(!nodeDrag)return;const released=nodeDrag;skipGraphClick=true;nodeDrag=null;$('map')._clearWeb?.();$('map').classList.remove('map-grabbing');if(!released.moved&&event?.type!=='pointercancel')released.activate();$('map').dataset.highlightActive='false';graphInteractionUntil=performance.now()+1200;for(const item of $('map').querySelectorAll('.map-dimmed,.map-link-highlight,.map-related'))item.classList.remove('map-dimmed','map-link-highlight','map-related');$('map')._wake?.();setTimeout(()=>skipGraphClick=false,0);}
$('map').addEventListener('pointerup',releaseGraphNode);
$('map').addEventListener('pointercancel',releaseGraphNode);
reduceGraphMotion.addEventListener('change',()=>renderGraph());

// Zoom around the pointer, leaving page scrolling available outside the map.
$('map').addEventListener('wheel',e=>{
  e.preventDefault();
  const map=$('map'),matrix=map.getScreenCTM();
  if(!matrix)return;
  const point=new DOMPoint(e.clientX,e.clientY).matrixTransform(matrix.inverse());
  const delta=e.deltaY*(e.deltaMode===1?16:e.deltaMode===2?map.clientHeight:1);
  const next=Math.max(.4,Math.min(5,zoom*Math.exp(-delta*.0015)));
  const ratio=next/zoom;
  pan={x:point.x-400-(point.x-400-pan.x)*ratio,y:point.y-280-(point.y-280-pan.y)*ratio};
  zoom=next;
  transformGraph();
},{passive:false});

document.addEventListener('visibilitychange',()=>{if(!(document.hidden||window.boraBackground))$('map')._wake?.();else {cancelAnimationFrame(graphFrame);$('map').dataset.renderState='idle';}});

$('zoomin').onclick=()=>{zoom=Math.min(zoom*1.2,5);transformGraph();};
$('zoomout').onclick=()=>{zoom=Math.max(zoom/1.2,.4);transformGraph();};
$('resetmap').onclick=()=>{zoom=1;pan={x:0,y:0};transformGraph();};

for(const category of mapCategories){const option=document.createElement('option');option.value=category.id;option.textContent=category.title;$('mapCategory').append(option);}
function refreshMapFilters(){zoom=1;pan={x:0,y:0};renderGraph();}
for(const id of ['mapCategory','mapFolder','mapHideHistory'])$(id).addEventListener('change',refreshMapFilters);
$('mapClearFilters').onclick=()=>{$('mapCategory').value='';$('mapFolder').value='';$('mapHideHistory').checked=false;focus=false;refreshMapFilters();};

// Display modes affect presentation only, never notes or their saved links.
function syncGraphModeControls(){
  $('mapModeLight').setAttribute('aria-pressed',String(graphMode==='light'));
  $('mapModeAnimated').setAttribute('aria-pressed',String(graphMode==='animated'));
  const expanded=document.body.classList.contains('map-expanded');
  $('mapExpand').setAttribute('aria-pressed',String(expanded));
  $('mapExpandLabel').textContent=expanded?'Restaurar':'Expandir';
  $('mapExpand').setAttribute('title',expanded?'Restaurar painel (Esc)':'Expandir mapa com animações para gravar. Esc volta ao painel.');
  $('mapModeStatus').textContent=graphMode==='light'?'Economia de recursos':reduceGraphMotion.matches?'Movimento reduzido pelo sistema':'Animações contínuas';
}
function setGraphMode(mode,persist=true){
  graphMode=mode==='animated'?'animated':'light';
  if(persist)try{localStorage.setItem('bora.mapMode',graphMode);}catch{}
  syncGraphModeControls();$('map')._wake?.();
}
function setGraphExpanded(expanded){
  const active=document.body.classList.contains('map-expanded');
  if(expanded===active)return;
  if(expanded){graphModeBeforeExpand=graphMode;document.body.classList.add('map-expanded');setGraphMode('animated',false);}
  else{document.body.classList.remove('map-expanded');setGraphMode(graphModeBeforeExpand,false);$('mapExpand').focus();}
}
$('mapModeLight').onclick=()=>setGraphMode('light');
$('mapModeAnimated').onclick=()=>setGraphMode('animated');
$('mapExpand').onclick=()=>setGraphExpanded(!document.body.classList.contains('map-expanded'));
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&document.body.classList.contains('map-expanded')){e.preventDefault();setGraphExpanded(false);}});
reduceGraphMotion.addEventListener('change',syncGraphModeControls);
syncGraphModeControls();
