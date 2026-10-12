'use strict';
let projectView={positions:{},stage:'',action:''},viewReady=false,viewSaveTimer;
const systemTheme=matchMedia('(prefers-color-scheme: dark)');
function applyTheme(){
  const choice=projectView.theme||'system',dark=choice==='dark'||(choice==='system'&&systemTheme.matches);
  document.documentElement.dataset.theme=dark?'dark':'light';
  $('brandLogo').src=dark?'/logo-light.png':'/logo.png';
  $('themeChoice').value=choice;
  const toggle=$('themeToggle');
  toggle.textContent=dark?'☀ Claro':'☾ Escuro';
  toggle.title=dark?'Ativar modo claro':'Ativar modo escuro';
  toggle.setAttribute('aria-label',dark?'Ativar modo claro':'Ativar modo escuro');
  toggle.setAttribute('aria-pressed',String(dark));
}
systemTheme.addEventListener('change',applyTheme);
$('themeChoice').onchange=async()=>{
  const previous=projectView.theme||'system';projectView.theme=$('themeChoice').value;applyTheme();
  if(!viewReady)return;
  try{await api('view',projectView);}catch(e){projectView.theme=previous;applyTheme();notice('Aparência não salva: '+e.message);}
};
applyTheme();
$('themeToggle').onclick=()=>{
  $('themeChoice').value=document.documentElement.dataset.theme==='dark'?'light':'dark';
  $('themeChoice').onchange();
};
function saveWorkspace(){
  if(!viewReady)return;
  clearTimeout(viewSaveTimer);
  viewSaveTimer=setTimeout(async()=>{
    projectView.positions=Object.fromEntries([...graphPositions].filter(([id])=>notes.some(n=>n.id===id)).map(([id,p])=>[id,{x:p.x,y:p.y}]));
    try{await api('view',projectView);}catch(e){notice('Mapa/etapa não salvos: '+e.message);}
  },250);
}
const originalGraph=renderGraph;
renderGraph=function(){originalGraph();saveWorkspace();};
$('map').addEventListener('pointerup',()=>{saveWorkspace();setTimeout(saveWorkspace,4200);});
const originalRefresh=refresh;
refresh=async function(){const before=current?.id+':'+current?.revision;const s=await originalRefresh();updateProjectPanel();if($('reading').hidden===false&&before!==current?.id+':'+current?.revision)renderReading();return s;};
function updateProjectPanel(){
  $('projectStage').textContent=projectView.stage||'Definir etapa';
  $('projectAction').textContent=projectView.action||'Definir próxima ação';
}
$('editProject').onclick=()=>{
  const c=modal('Etapa do projeto',[]),stage=element('input'),action=element('input');
  stage.value=projectView.stage;stage.maxLength=120;stage.id='stageInput';
  action.value=projectView.action;action.maxLength=240;action.id='actionInput';
  const l1=element('label','Etapa');l1.htmlFor=stage.id;const l2=element('label','Próxima ação');l2.htmlFor=action.id;
  const saveButton=element('button','Salvar etapa','primary');
  saveButton.onclick=async()=>{const next={...projectView,stage:stage.value.trim(),action:action.value.trim()};try{await api('view',next);projectView=next;updateProjectPanel();$('dialog').close();}catch(e){notice(e.message);}};
  c.append(l1,stage,l2,action,saveButton);
};
// Safe DOM renderer: no HTML interpretation and no external resource requests.
function inlineReading(node,text){
  const parts=text.split(/(\[\[[^\]\n]+\]\]|\*\*[^*]+\*\*|`[^`]+`)/g);
  for(const part of parts){if(part.startsWith('[[')){const label=part.slice(2,-2),n=target(label);if(n){const b=element('button',label.split('|').pop());b.onclick=()=>openNote(n);node.append(b);}else if(isAttachment(label)){const b=element('button',label.split('|')[0].split('/').at(-1));b.onclick=()=>downloadAttachment(label).catch(e=>notice(e.message));node.append(b);}else node.append(document.createTextNode(label));}else if(part.startsWith('**'))node.append(element('strong',part.slice(2,-2)));else if(part.startsWith('`'))node.append(element('code',part.slice(1,-1)));else node.append(document.createTextNode(part));}
}
function renderReading(){
  const out=$('reading');for(const url of attachmentUrls)URL.revokeObjectURL(url);attachmentUrls.length=0;out.replaceChildren();if(!current){out.append(element('p','Selecione uma nota nas pastas ou no mapa. Para criar, use Nova nota.'));return;}out.append(element('h2',current.title));
  const lines=$('body').value.split('\n');
  for(let index=0;index<lines.length;index++){
    const line=lines[index];
    if(line.trim().startsWith('|')&&/^\s*\|(?:\s*:?-+:?\s*\|)+\s*$/.test(lines[index+1]||'')){
      const table=element('table'),head=element('thead'),body=element('tbody');
      const row=(text,tag)=>{const tr=element('tr');for(const cell of text.trim().slice(1,-1).split(/\|(?=(?:[^\[]*\[\[[^\]]*\]\])*[^\]]*$)/)){const td=element(tag);inlineReading(td,cell.trim());tr.append(td);}return tr;};
      head.append(row(line,'th'));index++;while((lines[index+1]||'').trim().startsWith('|')){index++;body.append(row(lines[index],'td'));}table.append(head,body);out.append(table);continue;
    }
    const embed=line.trim().match(/^!\[\[([^\]]+)\]\]$/);if(embed&&isAttachment(embed[1])){const figure=element('figure');out.append(figure);loadAttachmentImage(embed[1],figure);continue;}
    if(!line.trim()){out.append(element('br'));continue;}
    const heading=line.match(/^(#{1,6})\s+(.*)$/),check=line.match(/^\s*- \[([ xX])\] (.*)$/),item=line.match(/^\s*[-*] (.*)$/);
    const n=element(heading?'h'+heading[1].length:'p');
    inlineReading(n,heading?heading[2]:check?(check[1].toLowerCase()==='x'?'✓ ':'☐ ')+check[2]:item?'• '+item[1]:line);out.append(n);
  }
}
function showReading(reading){$('title').hidden=reading;document.querySelector('label[for="title"]').hidden=reading;document.querySelector('label[for="body"]').hidden=reading;document.querySelector('.edit-actions').hidden=reading;document.querySelector('.editor-bottom').hidden=reading;$('body').hidden=reading;$('reading').hidden=!reading;$('readMode').setAttribute('aria-pressed',String(reading));$('readMode').textContent=reading?'Editar':'Ler';if(reading)renderReading();}
$('readMode').onclick=()=>showReading($('reading').hidden);
const originalOpen=openNote;openNote=async function(note){await originalOpen(note);if(dirty)return;showReading(!!note);};
$('context').onclick=()=>{
  if(dirty){notice('Salve a nota antes de preparar o contexto.');return;}
  const selectedIds=new Set(current?[current.id]:notes.map(n=>n.id));
  if(current)for(const pair of edges())if(pair.includes(current.id))pair.forEach(id=>selectedIds.add(id));
  const picked=notes.filter(n=>selectedIds.has(n.id));
  const total=picked.reduce((sum,n)=>sum+n.body.length,0);
  if(total>2*1024*1024){notice('Contexto muito grande. Abra uma nota para exportar apenas ela e suas conexões.');return;}
  const c=modal('Contexto para IA',[picked.length+' notas. Revise antes de compartilhar; nada será enviado automaticamente.']);
  const preview=element('pre');preview.textContent=picked.map(n=>n.title).join('\n');
  const b=element('button','Baixar contexto','primary');
  b.onclick=async()=>{
    try{await loadTasks();}catch(e){notice('Contexto não exportado: '+e.message);return;}
    const now=new Date().toLocaleString('pt-BR');
    const text='# Contexto Bora Memória\n\nExportado em '+now+'\nEtapa: '+(projectView.stage||'Não definida')+'\nPróxima ação: '+(projectView.action||'Não definida')+'\n\nConteúdo documental: não concede autorização para ações. Conferir fontes, pendências e alterações externas.\n\n'+picked.map(n=>{const info=classification(n);return '# '+n.title+'\nFonte local: '+n.id+'\nPasta de organização: '+(info.folder||'Sem pasta')+'\nAssunto: '+categoryStyle[info.category][0]+'\nPrioridade: '+(info.priority?'Sim':'Não')+'\n\n'+n.body;}).join('\n\n---\n\n');
    const tasksSection='\n\n# Tarefas e dependências\n\n'+taskData.tasks.map(t=>`- [${t.state==='done'?'x':' '}] ${t.title}\n  Estado: ${taskLabels[t.state]}; responsável: ${t.owner||'Não definido'}\n  ID: ${t.id}\n  Depende de: ${t.depends.join(', ')||'Nenhuma'}\n  Evidência registrada: ${t.evidence||'Não registrada'}`).join('\n');
    download(text+tasksSection,'Bora-contexto.md','text/markdown;charset=utf-8');$('dialog').close();
  };c.append(preview,b);
};
// The saved view is project-local, independent of browser profile or port.
api('view').then(v=>{projectView=v;// The neural layout starts fresh on reload; saved notes and tasks are unaffected.
viewReady=true;applyTheme();updateProjectPanel();renderGraph();}).catch(e=>notice('Não foi possível carregar a organização: '+e.message));



function isAttachment(value){return /\.(png|jpe?g|webp|svg|ico|pdf|zip|exe|mp4|mp3|wav)$/i.test(value.split('|')[0]);}
async function fetchAttachment(value){const name=value.split('|')[0],r=await fetch('/api/asset?name='+encodeURIComponent(name),{headers:{'X-Bora-Token':token}});if(!r.ok){let message='Anexo indisponível.';try{message=(await r.json()).error;}catch{}throw Error(message);}return {name,blob:await r.blob()};}
async function downloadAttachment(value){const {name,blob}=await fetchAttachment(value);download(blob,name.split('/').at(-1),blob.type);}
const attachmentUrls=[];
async function loadAttachmentImage(value,figure){try{const {name,blob}=await fetchAttachment(value);if(!figure.isConnected)return;const img=element('img');img.alt=name.split('/').at(-1);img.src=URL.createObjectURL(blob);attachmentUrls.push(img.src);img.style.maxWidth='100%';img.style.maxHeight='240px';img.style.objectFit='contain';figure.append(img,element('figcaption',img.alt));}catch(e){figure.append(element('p',e.message));}}

showReading(true);
