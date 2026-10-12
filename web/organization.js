'use strict';
let organizationData={folders:[],notes:{},revision:''},activeFolder='',priorityOnly=false;
const expandedFolders=new Set();
async function openGraphFolder(item){
  if(!await mayLeave())return;
  await revealGraphItem(item);
  const box=modal(item.title,['Arquivos e subpastas desta pasta.']);
  const knownFolders=new Set(organizationData.folders);
  for(const note of notes){const parts=classification(note).folder.split('/');for(let i=1;i<=parts.length;i++)knownFolders.add(parts.slice(0,i).join('/'));}
  const directFolders=[...knownFolders].filter(path=>path.startsWith(item.path+'/')&&!path.slice(item.path.length+1).includes('/'));
  for(const path of directFolders){const b=element('button','▸ '+path.split('/').at(-1));b.onclick=()=>{$('dialog').close();openGraphFolder({folderNode:true,path,title:path.split('/').at(-1)});};box.append(b);}
  const files=notes.filter(note=>classification(note).folder===item.path);
  for(const note of files){const b=element('button',note.title);b.onclick=async()=>{$('dialog').close();await openNote(note);selectPanel('note');showReading(true);};box.append(b);}
  if(!files.length&&!directFolders.length)box.append(element('p','Esta pasta ainda não contém notas.'));
}
async function revealGraphItem(item){
  if(!item.folderNode){await openNote(item);if(current?.id!==item.id||dirty)return;}
  const folder=item.folderNode?item.path:classification(item).folder;
  activeFolder=folder;$('search').value='';priorityOnly=false;
  folder.split('/').filter(Boolean).forEach((_,i,parts)=>expandedFolders.add(parts.slice(0,i+1).join('/')));
  drawNoteTree();
  const selector=item.folderNode?'[data-folder-path]':'[data-note-id]';
  const target=[...$('notes').querySelectorAll(selector)].find(node=>item.folderNode?node.dataset.folderPath===folder:node.dataset.noteId===item.id);
  target?.scrollIntoView({block:'nearest'});target?.focus({preventScroll:true});
}
const categoryStyle={guidance:['Orientações','#187e65'],general:['Geral','#8b70b8'],community:['Comunidade','#6d28d9'],continuity:['Continuidade','#475569'],youtube:['YouTube','#c93845'],instagram:['Instagram','#b73591'],brand:['Marca','#bd5b32'],content:['Conteúdo','#187e65'],projects:['Projetos','#286da5']};
function classification(n){return organizationData.notes[n.id]||{folder:n.id.includes('/')?n.id.slice(0,n.id.lastIndexOf('/')):'',category:'general',priority:false};}
function drawNoteTree(){
  const q=$('search').value.toLocaleLowerCase(),out=$('notes');out.replaceChildren();
  const matches=notes.filter(n=>(n.title+' '+n.body).toLocaleLowerCase().includes(q)&&(!priorityOnly||classification(n).priority));
  $('count').textContent=matches.length;$('mapLabels').value=organizationData.labels||'all';
  const root={children:new Map(),notes:[],path:''};
  function folderNode(path){let node=root,prefix='';for(const part of path.split('/').filter(Boolean)){prefix=prefix?prefix+'/'+part:part;if(!node.children.has(part))node.children.set(part,{children:new Map(),notes:[],path:prefix});node=node.children.get(part);}return node;}
  for(const folder of organizationData.folders)folderNode(folder);
  for(const n of matches)folderNode(classification(n).folder).notes.push(n);
  function count(node){return node.notes.length+[...node.children.values()].reduce((sum,n)=>sum+count(n),0);}
  function noteButton(n,parent){const info=classification(n),b=element('button',undefined,n.id===current?.id?'active':'');b.dataset.noteId=n.id;b.setAttribute('aria-label',n.title+(info.priority?' · Prioridade':''));const dot=element('i');dot.style.backgroundColor=folderColor(info.folder,categoryStyle[info.category][1]);dot.setAttribute('aria-hidden','true');b.append(dot,document.createTextNode(n.title));if(info.priority)b.append(element('span','★','priority-mark'));b.onclick=()=>{activeFolder=info.folder;openNote(n);};parent.append(b);}
  function branch(node,parent){
    for(const[label,child]of [...node.children].sort((a,b)=>a[0].localeCompare(b[0],'pt-BR'))){
      const total=count(child);if((q||priorityOnly)&&!total)continue;
      const detail=element('details',undefined,'note-folder'),summary=element('summary');summary.dataset.folderPath=child.path;summary.style.borderLeft='3px solid '+folderColor(child.path,'#8b70b8');summary.append(element('span',label),element('small',String(total)));detail.append(summary);detail.open=q?true:expandedFolders.has(child.path);
      summary.onclick=()=>{activeFolder=child.path;if(detail.open)expandedFolders.delete(child.path);else expandedFolders.add(child.path);};
      const children=element('div',undefined,'folder-children');branch(child,children);for(const n of child.notes)noteButton(n,children);detail.append(children);parent.append(detail);
    }
  }
  branch(root,out);for(const n of root.notes)noteButton(n,out);
  if(!matches.length&&(q||priorityOnly||!organizationData.folders.length))out.append(element('p','Nenhuma nota encontrada.'));
  $('priorities').setAttribute('aria-pressed',String(priorityOnly));
}
renderList=drawNoteTree;$('search').oninput=drawNoteTree;
$('priorities').onclick=()=>{priorityOnly=!priorityOnly;drawNoteTree();};
$('collapseFolders').onclick=()=>{expandedFolders.clear();drawNoteTree();};
async function saveOrganization(next){organizationData=await api('organization',{...next,revision:organizationData.revision});drawNoteTree();renderGraph();}
function newFolder(){
  const c=modal('Nova pasta',[]),label=element('label','Nome da pasta'),input=element('input');input.id='newFolderName';label.htmlFor=input.id;input.maxLength=240;input.placeholder='Comunidade/Cursos';input.value=activeFolder?activeFolder+'/':'';
  const error=element('p');error.setAttribute('role','alert');const b=element('button','Criar pasta','primary');
  b.onclick=async()=>{b.disabled=true;try{const name=input.value.trim();if(!name)throw Error('Informe o nome da pasta.');await saveOrganization({...organizationData,folders:[...new Set([...organizationData.folders,name])]});activeFolder=name;name.split('/').forEach((_,i)=>expandedFolders.add(name.split('/').slice(0,i+1).join('/')));drawNoteTree();$('dialog').close();}catch(e){error.textContent=e.message;}finally{b.disabled=false;}};c.append(label,input,error,b);
}
$('newFolder').onclick=newFolder;
function organizeNote(){
  if(!current){notice('Abra uma nota para organizar.');return;}
  const n=current,info=classification(n),c=modal('Organizar nota',[]);
  const folder=element('select');folder.id='noteFolder';const folderLabel=element('label','Pasta');folderLabel.htmlFor=folder.id;
  const none=element('option','Sem pasta');none.value='';folder.append(none);for(const name of organizationData.folders){const o=element('option',name);o.value=name;folder.append(o);}folder.value=info.folder;
  const category=element('select');category.id='noteCategory';const categoryLabel=element('label','Assunto');categoryLabel.htmlFor=category.id;
  for(const[key,[label]]of Object.entries(categoryStyle)){const o=element('option',label);o.value=key;category.append(o);}category.value=info.category;
  const mark=element('input');mark.type='checkbox';mark.checked=info.priority;const markLabel=element('label');markLabel.append(mark,document.createTextNode(' Prioridade'));
  const error=element('p');error.setAttribute('role','alert');const b=element('button','Salvar organização','primary');b.onclick=async()=>{b.disabled=true;try{if(dirty)throw Error('Salve as alterações da nota antes de organizar.');let moved=n;if(folder.value!==n.id.split('/').slice(0,-1).join('/')){moved=await api('move',{id:n.id,revision:n.revision,folder:folder.value});current=moved;await refresh();await reloadOrganization();}await saveOrganization({...organizationData,notes:{...organizationData.notes,[moved.id]:{folder:folder.value,category:category.value,priority:mark.checked}}});activeFolder=folder.value;$('dialog').close();}catch(e){error.textContent=e.message;}finally{b.disabled=false;}};
  c.append(element('p',n.title),folderLabel,folder,categoryLabel,category,markLabel,error,b);
}
$('organizeNote').onclick=organizeNote;
const beforeOrganizationGraph=renderGraph;
renderGraph=function(){beforeOrganizationGraph();for(const node of $('map').querySelectorAll('[data-note]')){const info=organizationData.notes[node.dataset.note]||{category:'general',priority:false};node.querySelector('circle').setAttribute('fill',folderColor(info.folder||node.dataset.note.split('/').slice(0,-1).join('/'),neuralColor(info.folder||node.dataset.note.split('/').slice(0,-1).join('/')||node.dataset.visualGroup||'Geral')));if(info.priority){node.querySelector('circle').setAttribute('stroke','#e0a923');node.querySelector('circle').setAttribute('stroke-width','1.2');}const title=svg('title',{});title.textContent=node.getAttribute('aria-label')+' · '+categoryStyle[info.category][0]+(info.priority?' · Prioridade':'');}};
const beforeOrganizationSave=save;
save=async function(){const creating=!current,folder=activeFolder;await beforeOrganizationSave();if(creating&&current&&!dirty&&folder&&!organizationData.notes[current.id]){try{await saveOrganization({...organizationData,notes:{...organizationData.notes,[current.id]:{folder,category:'general',priority:false}}});}catch(e){notice('Nota salva; organização pendente: '+e.message);}}};
$('save').onclick=save;
async function reloadOrganization(){organizationData=await api('organization');drawNoteTree();renderGraph();}
let orgRefreshBusy=false;
let orgRefreshFailures=0;
async function refreshOrganization(){
  if(window.boraBackground||document.hidden||orgRefreshBusy)return;
  orgRefreshBusy=true;
  try{
    const next=await api('organization');
    if(next.revision!==organizationData.revision){organizationData=next;drawNoteTree();renderGraph();}
    orgRefreshFailures=0;clearNotice('organization-connection');
  }catch(error){
    orgRefreshFailures++;
    if(!error.connection&&orgRefreshFailures===1)notice('Organização não atualizada: '+error.message,'organization-connection');
    else if(error.connection&&orgRefreshFailures===2)notice('Sem conexão com a organização das notas. Tentando reconectar automaticamente.','organization-connection');
  }finally{orgRefreshBusy=false;}
}
setInterval(refreshOrganization,4000);
const folderOperation=$('folder').onclick;
$('folder').onclick=async()=>{await folderOperation();activeFolder='';expandedFolders.clear();await reloadOrganization();};
reloadOrganization().catch(e=>notice('Organização não carregada: '+e.message));

function folderColor(folder,fallback){let path=folder;const colors=organizationData.colors||{};while(path){if(colors[path])return colors[path];path=path.split('/').slice(0,-1).join('/');}return colors['*']||fallback;}
$('folderColors').onclick=()=>{
 const c=modal('Cores das pastas',[]),select=element('select');select.id='colorFolder';
 const label=element('label','Pasta');label.htmlFor=select.id;
 for(const name of ['*',...organizationData.folders]){const o=element('option',name==='*'?'Todas as pastas':name);o.value=name;select.append(o);}
 const color=element('input');color.type='color';color.id='folderColorValue';const cl=element('label','Cor');cl.htmlFor=color.id;
 const update=()=>{color.value=folderColor(select.value,'#6d28d9');};select.onchange=update;update();
 const error=element('p');error.setAttribute('role','alert');
 const saveColor=element('button','Aplicar cor','primary'),reset=element('button','Restaurar padrão');
 saveColor.onclick=async()=>{try{const colors=select.value==='*'?{'*':color.value}:{...(organizationData.colors||{}),[select.value]:color.value};await saveOrganization({...organizationData,colors});$('dialog').close();}catch(e){error.textContent=e.message;}};
 reset.onclick=async()=>{try{const colors={...(organizationData.colors||{})};if(select.value==='*'){await saveOrganization({...organizationData,colors:{}});}else{delete colors[select.value];await saveOrganization({...organizationData,colors});}$('dialog').close();}catch(e){error.textContent=e.message;}};
 c.append(label,select,cl,color,element('p','Subpastas herdam a cor da pasta. Uma cor própria tem prioridade.'),error,saveColor,reset);
};

const beforeFolderColorsGraph=renderGraph;renderGraph=function(){beforeFolderColorsGraph();for(const node of $('map').querySelectorAll('[data-folder]'))node.querySelector('circle').setAttribute('fill',folderColor(node.dataset.folder,neuralColor(node.dataset.folder)));};

function neuralColor(path){const root=path.split('/')[0]||'Geral',palette=['#52c9ee','#b89aff','#efac63','#df7ee8','#7bb6ff','#f0809a','#72d9bc'];let hash=0;for(const c of root)hash=(hash*31+c.charCodeAt(0))>>>0;return palette[hash%palette.length];}

function drawMemoryCalendar(){const now=new Date(),year=now.getFullYear(),month=now.getMonth(),first=new Date(year,month,1).getDay(),days=new Date(year,month+1,0).getDate(),box=$('memoryCalendar');box.replaceChildren(element('strong',now.toLocaleDateString('pt-BR',{month:'long',year:'numeric'})));const grid=element('div',undefined,'calendar-grid');for(const label of ['D','S','T','Q','Q','S','S'])grid.append(element('small',label));for(let i=0;i<first;i++)grid.append(element('span',''));for(let d=1;d<=days;d++){const day=element('span',String(d),d===now.getDate()?'today':'');if(d===now.getDate())day.setAttribute('aria-label','Hoje, '+now.toLocaleDateString('pt-BR'));grid.append(day);}box.append(grid);}
drawMemoryCalendar();

$('mapLabels').onchange=async()=>{const choice=$('mapLabels').value;try{await saveOrganization({...organizationData,labels:choice});}catch(e){$('mapLabels').value=organizationData.labels||'all';notice('Preferência não salva: '+e.message);}};
