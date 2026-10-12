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
renderGraph=function(){
  cancelAnimationFrame(graphFrame);
  const allEdges=edges(),selected=current?.id;
  let shown=notes;
  if(focus&&selected){const ids=new Set([selected]);allEdges.forEach(([a,b])=>{if(a===selected)ids.add(b);if(b===selected)ids.add(a);});shown=notes.filter(n=>ids.has(n.id));}
  const folderSet=new Set();
  shown.forEach(n=>{const parts=n.id.split('/').slice(0,-1);for(let i=1;i<=parts.length;i++)folderSet.add(parts.slice(0,i).join('/'));});
  const folders=[...folderSet].sort();
  const folderNodes=folders.map(path=>({id:'folder:'+path,title:path.split('/').at(-1),folderNode:true,path,depth:path.split('/').length}));
  for(const f of folderNodes){const parent=f.path.split('/').slice(0,-1).join('/');if(parent)allEdges.push(['folder:'+parent,f.id]);}
  for(const n of shown){const parent=n.id.split('/').slice(0,-1).join('/');if(parent)allEdges.push(['folder:'+parent,n.id]);}
  shown=[...folderNodes,...shown];
  const loose=shown.filter(n=>!n.folderNode&&!n.id.includes('/'));
  const looseIds=new Set(loose.map(n=>n.id)),neighbors=new Map(loose.map(n=>[n.id,new Set()]));
  for(const [a,b] of allEdges)if(looseIds.has(a)&&looseIds.has(b)){neighbors.get(a).add(b);neighbors.get(b).add(a);}
  const visualGroups=new Map(),remaining=new Set(looseIds);
  const seeds=[...looseIds].sort((a,b)=>neighbors.get(b).size-neighbors.get(a).size||a.localeCompare(b));
  for(const seed of seeds){
    if(!remaining.has(seed))continue;
    const queue=[seed],key='ideias:'+seed;let members=0;
    for(let head=0;head<queue.length&&members<18;head++){
      const id=queue[head];if(!remaining.delete(id))continue;
      visualGroups.set(id,key);members++;
      for(const neighbor of neighbors.get(id))if(remaining.has(neighbor))queue.push(neighbor);
    }
  }
  const groupSizes=new Map();for(const key of visualGroups.values())groupSizes.set(key,(groupSizes.get(key)||0)+1);
  for(const id of looseIds){
    if(!neighbors.get(id).size){visualGroups.set(id,'sem-ligacoes');continue;}
    const key=visualGroups.get(id);if(groupSizes.get(key)>3)continue;
    const candidates=[...neighbors.get(id)].map(other=>visualGroups.get(other)).filter(other=>other!==key&&groupSizes.get(other)>3);
    if(candidates.length){const target=candidates.sort((a,b)=>groupSizes.get(b)-groupSizes.get(a)||a.localeCompare(b))[0];visualGroups.set(id,target);}
  }
  const rootOf=n=>n.folderNode?n.path:(n.id.includes('/')?n.id.split('/').slice(0,-1).join('/'):visualGroups.get(n.id)||'Geral');
  const roots=[...new Set(shown.map(rootOf))];
  const graph=$('map');graph.replaceChildren();
  graph.dataset.highlightActive='false';
  graph.dataset.buildCount=String(Number(graph.dataset.buildCount||0)+1);
  const group=svg('g',{transform:`translate(${pan.x} ${pan.y}) translate(400 280) scale(${zoom}) translate(-400 -280)`});graph.append(group);
  const ids=new Set(shown.map(n=>n.id));
  const visible=allEdges.filter(([a,b])=>ids.has(a)&&ids.has(b));
  const hemisphereCounts=[0,0];
  const peersByRoot=new Map();
  for(const n of shown){const root=rootOf(n);if(!peersByRoot.has(root))peersByRoot.set(root,[]);peersByRoot.get(root).push(n);}
  const rootCounters=new Map();
  const centers=new Map(roots.map((root,i)=>{const angle=i*2.399963,r=roots.length===1?0:Math.sqrt((i+.5)/roots.length);return [root,{x:400+Math.cos(angle)*245*r,y:275+Math.sin(angle)*175*r}];}));
  const localCounters=new Map();
  for(const root of [...roots].sort((a,b)=>a.split('/').length-b.split('/').length)){
    const parent=root.split('/').slice(0,-1).join('/');
    if(centers.has(parent)){const base=centers.get(parent),angle=roots.indexOf(root)*2.39996;centers.set(root,{x:base.x+Math.cos(angle)*65,y:base.y+Math.sin(angle)*65});}
  }
  const rootById=new Map(shown.map(n=>[n.id,rootOf(n)]));
  // Move only cluster centers toward real cross-folder connections at build time.
  const groupNeighbors=new Map(roots.map(root=>[root,new Set()]));
  for(const [a,b] of visible){const ra=rootById.get(a),rb=rootById.get(b);if(ra!==rb){groupNeighbors.get(ra).add(rb);groupNeighbors.get(rb).add(ra);}}
  const originalCenters=new Map([...centers].map(([root,p])=>[root,{...p}]));
  for(const [root,linked] of groupNeighbors){
    if(!linked.size)continue;
    const p=originalCenters.get(root),near=[...linked].map(id=>originalCenters.get(id));
    centers.set(root,{x:p.x*.94+near.reduce((sum,n)=>sum+n.x,0)/near.length*.06,y:p.y*.94+near.reduce((sum,n)=>sum+n.y,0)/near.length*.06});
  }
  // Separate cluster envelopes once, not every animation frame.
  const envelope=root=>Math.min(80,25+Math.sqrt(peersByRoot.get(root).length)*12);
  for(let pass=0;pass<24;pass++)for(let i=0;i<roots.length;i++)for(let j=i+1;j<roots.length;j++){
    const a=centers.get(roots[i]),b=centers.get(roots[j]);let dx=b.x-a.x,dy=b.y-a.y,d=Math.hypot(dx,dy);
    if(d<.01){dx=Math.cos(i*2.399);dy=Math.sin(i*2.399);d=1;}
    const gap=envelope(roots[i])+envelope(roots[j])+24;
    if(d<gap){const shift=(gap-d)*.25;a.x-=dx/d*shift;a.y-=dy/d*shift;b.x+=dx/d*shift;b.y+=dy/d*shift;}
    for(const p of [a,b]){p.x=Math.max(90,Math.min(710,p.x));p.y=Math.max(85,Math.min(475,p.y));}
  }
  const placements=shown.map(n=>{
    const root=rootOf(n);
    const peers=peersByRoot.get(root),index=rootCounters.get(root)||0,sector=roots.indexOf(root);
    rootCounters.set(root,index+1);
    const side=peers.length>shown.length*.45?index%2:sector%2;
    return {side,index:hemisphereCounts[side]++};
  });
  const points=shown.map((n,i)=>{
    if(!graphPositions.has(n.id)){const a=2*Math.PI*i/Math.max(shown.length,1)-Math.PI/2,r=shown.length===1?0:190;graphPositions.set(n.id,{x:400+Math.cos(a)*r,y:275+Math.sin(a)*r,vx:0,vy:0});}
    const p=graphPositions.get(n.id);p.id=n.id;
    const placement=placements[i],a=placement.index*2.399963229728653;
    const r=Math.sqrt((placement.index+.5)/Math.max(1,hemisphereCounts[placement.side]));
    p.side=placement.side;
    const root=rootOf(n),center=centers.get(root),localIndex=localCounters.get(root)||0;
    localCounters.set(root,localIndex+1);
    const localAngle=localIndex*2.399963229728653,localRadius=Math.sqrt((localIndex+.5)/Math.max(1,peersByRoot.get(root).length))*(roots.length===1?185:Math.min(80,25+Math.sqrt(peersByRoot.get(root).length)*12));
    p.ax=center.x+Math.cos(localAngle)*localRadius;
    p.ay=center.y+Math.sin(localAngle)*localRadius;
    p.phase=roots.indexOf(root)*1.7+localIndex*.19;
    if(p.neural!==5||p.layoutCount!==shown.length){p.x=p.ax;p.y=p.ay;p.z=0;p.neural=5;p.layoutCount=shown.length;}
    return p;
  });
  if(points.length>1){
    const xs=points.map(p=>p.ax),ys=points.map(p=>p.ay),minX=Math.min(...xs),maxX=Math.max(...xs),minY=Math.min(...ys),maxY=Math.max(...ys);
    const factor=Math.min(1.7,680/Math.max(1,maxX-minX),440/Math.max(1,maxY-minY)),cx=(minX+maxX)/2,cy=(minY+maxY)/2;
    for(const p of points){p.ax=400+(p.ax-cx)*factor;p.ay=275+(p.ay-cy)*factor;p.x=p.ax;p.y=p.ay;p.vx=0;p.vy=0;}
  }
  const lines=visible.map(([a,b])=>{const folder=a.startsWith('folder:')||b.startsWith('folder:');const line=svg('path',{class:folder?'map-folder-link':'map-idea-link',fill:'none','data-from':a,'data-to':b});group.append(line);return {a:graphPositions.get(a),b:graphPositions.get(b),line};});
  const adjacency=new Map(shown.map(n=>[n.id,new Set()]));
  for(const [a,b] of visible){adjacency.get(a).add(b);adjacency.get(b).add(a);}
  const nodes=shown.map(n=>{
    const p=graphPositions.get(n.id),g=svg('g',{class:'node',...(n.folderNode?{'data-folder':n.path}:{'data-note':n.id}),tabindex:0,role:'button','aria-label':'Abrir '+n.title});
    if(visualGroups.has(n.id))g.dataset.visualGroup=visualGroups.get(n.id);
    const fullTitle=svg('title',{});fullTitle.textContent=n.title;g.append(fullTitle);
    const degree=adjacency.get(n.id).size;
    g.append(svg('circle',{r:n.folderNode?Math.max(3.5,7.5-(n.depth-1)*2):Math.min(4,1.6+Math.sqrt(Math.max(0,degree))*.35)+(n.id===selected?1:0),fill:n.id===selected?'#6525de':'#ac8adf',stroke:'#b4c9ed','stroke-width':.45}));
    const mainNote=visualGroups.get(n.id)==='ideias:'+n.id;
    const label=svg('text',{class:n.folderNode?'folder-label':'note-label',y:16,'text-anchor':'middle'});label.textContent=n.title.length>18?n.title.slice(0,17)+'…':n.title;const radius=Number(g.querySelector('circle').getAttribute('r'));label.setAttribute('y',radius+8);label.style.fontSize=(n.folderNode||mainNote?9:Math.min(7,4.5+radius*.45))+'px';label.style.fontWeight='400';const labels=typeof organizationData==='undefined'?'all':(organizationData.labels||'all');if(labels==='all'||(labels==='main'&&((n.folderNode&&n.depth===1)||mainNote)))g.append(label); // Saved label preference, without changing project content.
    const highlight=()=>{
      graph.dataset.highlightActive='true';
      cancelAnimationFrame(graphFrame);
      const connected=new Set([n.id,...adjacency.get(n.id)]);
      for(const item of group.querySelectorAll('.node')){
        const id=item.dataset.note||'folder:'+item.dataset.folder;
        item.classList.toggle('map-dimmed',!connected.has(id));
      }
      for(const {line} of lines){
        const active=line.dataset.from===n.id||line.dataset.to===n.id;
        line.classList.toggle('map-link-highlight',active);
        line.classList.toggle('map-dimmed',!active);
      }
    };
    const clear=()=>{graph.dataset.highlightActive='false';for(const item of group.querySelectorAll('.map-dimmed,.map-link-highlight'))item.classList.remove('map-dimmed','map-link-highlight');graph._wake?.();};
    g.addEventListener('pointerenter',highlight);g.addEventListener('pointerleave',()=>{if(!nodeDrag)clear();});
    g.addEventListener('focus',highlight);g.addEventListener('blur',clear);
    g.addEventListener('pointerdown',e=>{if(e.button!==0)return;e.stopPropagation();highlight();nodeDrag={p,startX:e.clientX,startY:e.clientY,moved:false,activate:()=>{if(n.folderNode)openGraphFolder(n);else{openNote(n);selectPanel('note');}}};g.setPointerCapture(e.pointerId);});
    g.addEventListener('contextmenu',e=>{e.preventDefault();e.stopPropagation();revealGraphItem(n);});
    g.addEventListener('click',()=>{if(skipGraphClick){skipGraphClick=false;return;}if(n.folderNode){openGraphFolder(n);}else {openNote(n);selectPanel('note');}});
    g.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();if(n.folderNode){openGraphFolder(n);}else {openNote(n);selectPanel('note');}}});
    group.append(g);return {p,g};
  });
  let drawCount=0;
  const draw=()=>{
    graph.dataset.rotationAngle=graphAngle.toFixed(4);
    const cosine=Math.cos(graphAngle),sine=Math.sin(graphAngle);
    for(const p of points){const x=p.x-400,z=p.z||0;p.depth=-x*sine+z*cosine;p.scale=700/(700-p.depth);p.sx=400+(x*cosine+z*sine)*p.scale;p.sy=275+(p.y-275)*p.scale;}
    // Slow rotation needs fewer edge updates than pointer interactions.
    if(drawCount++%2===0||nodeDrag||reduceGraphMotion.matches)
      for(const {a,b,line} of lines){const bend=Math.min(35,Math.abs(b.sx-a.sx)*.12)*(a.side?1:-1);line.setAttribute('d',`M ${a.sx.toFixed(1)} ${a.sy.toFixed(1)} Q ${((a.sx+b.sx)/2+bend).toFixed(1)} ${((a.sy+b.sy)/2-12).toFixed(1)} ${b.sx.toFixed(1)} ${b.sy.toFixed(1)}`);}
    for(const {p,g} of nodes)g.setAttribute('transform',`translate(${p.sx.toFixed(1)} ${p.sy.toFixed(1)}) scale(${p.scale.toFixed(3)})`);
  };
  let frames=0;
  let previousFrame=0;
  const frameTimes=[],workTimes=[];
  const highlightWork=[];
  function springStep(elapsed){
    if(reduceGraphMotion.matches)return;
    const dt=Math.min(1.8,Math.max(.3,elapsed/32));
    // Each edge transfers displacement, avoiding all-pairs repulsion.
    const wave=performance.now()*.0007;
    for(const p of points){p.fx=(p.ax+Math.sin(wave+p.phase)*4-p.x)*.018;p.fy=(p.ay+Math.cos(wave*.8+p.phase)*5-p.y)*.018;}
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
    springStep(elapsed||32);draw();frames++;
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
    if(nodeDrag||(!reduceGraphMotion.matches&&(settling||graph.dataset.highlightActive!=='true')))graphFrame=requestAnimationFrame(tick);
  }
  draw();graphFrame=requestAnimationFrame(tick);
  graph._wake=()=>{frames=0;cancelAnimationFrame(graphFrame);graphFrame=requestAnimationFrame(tick);};
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
function releaseGraphNode(){if(!nodeDrag)return;const released=nodeDrag;skipGraphClick=true;nodeDrag=null;if(!released.moved)released.activate();$('map').dataset.highlightActive='false';graphInteractionUntil=performance.now()+1200;for(const item of $('map').querySelectorAll('.map-dimmed,.map-link-highlight'))item.classList.remove('map-dimmed','map-link-highlight');$('map')._wake?.();setTimeout(()=>skipGraphClick=false,0);}
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

document.addEventListener('visibilitychange',()=>{if(!(document.hidden||window.boraBackground))$('map')._wake?.();else cancelAnimationFrame(graphFrame);});

$('zoomin').onclick=()=>{zoom=Math.min(zoom*1.2,5);transformGraph();};
$('zoomout').onclick=()=>{zoom=Math.max(zoom/1.2,.4);transformGraph();};
$('resetmap').onclick=()=>{zoom=1;pan={x:0,y:0};transformGraph();};
