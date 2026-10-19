'use strict';
let activityData={events:[],revision:''},activityFilter='all',activityBusy=false;
const activityLabels={note_imported:'Nota importada do Obsidian',note_saved:'Nota salva',note_removed:'Nota movida para lixeira',note_restored:'Nota restaurada',external_created:'Nota externa adicionada',external_changed:'Alteração externa',external_removed:'Nota removida externamente',task_changed:'Tarefa atualizada'};
function selectPanel(name){
  for(const panel of ['activity','note','guidance','insights']){
    $(panel+'Panel').hidden=panel!==name;
    $(panel+'Tab').setAttribute('aria-selected',String(panel===name));
  }
  if(name==='guidance')renderGuidance();
  if(name==='insights'&&typeof refreshInsights==='function')refreshInsights(true);
}
function renderGuidance(){
  const out=$('guidanceList');out.replaceChildren();
  const items=notes.filter(n=>classification(n).category==='guidance');
  const usage=$('guidanceUsage');usage.replaceChildren();
  for(const run of taskData.execution||[])for(const ref of run.guidance||[]){const b=element('button',run.agent+' · Usando orientação: '+ref.title,'guidance-in-use');b.onclick=()=>{const n=notes.find(n=>n.id===ref.id);if(n)openNote(n);};usage.append(b);}
  for(const n of items){const b=element('button',undefined,'activity-task');b.append(element('strong',n.title),element('small',n.id));b.onclick=async()=>{await openNote(n);if(current?.id===n.id&&!dirty)showReading(true);};out.append(b);}
  if(!items.length)out.append(element('p','Nenhuma orientação encontrada. Classifique uma nota em Organizar → Assunto → Orientações.'));
}
$('guidanceTab').onclick=()=>selectPanel('guidance');
$('guidanceState').onclick=()=>$('projectState').click();
$('activityTab').onclick=()=>{selectPanel('activity');refreshActivities();};
$('noteTab').onclick=()=>selectPanel('note');
const panelTabs=['activityTab','noteTab','guidanceTab','insightsTab'];
for(const id of panelTabs)$(id).addEventListener('keydown',e=>{if(e.key==='ArrowLeft'||e.key==='ArrowRight'){e.preventDefault();const step=e.key==='ArrowRight'?1:-1,target=panelTabs[(panelTabs.indexOf(id)+step+panelTabs.length)%panelTabs.length];$(target).focus();$(target).click();}});
const openFromActivity=openNote;
openNote=async function(n){await openFromActivity(n);if(n===null||current?.id===n.id)selectPanel('note');};
function editActivity(item){
  const c=modal('Observação da atividade',[]),label=element('label','Observação'),input=element('textarea');
  input.id='activityObservation';input.value=item.observation||'';input.maxLength=2000;label.htmlFor=input.id;
  const markLabel=element('label'),mark=element('input');mark.type='checkbox';mark.checked=item.important;markLabel.append(mark,document.createTextNode(' Importante'));
  const error=element('p');error.setAttribute('role','alert');const b=element('button','Salvar observação','primary');
  b.onclick=async()=>{b.disabled=true;try{activityData=await api('activities',{revision:activityData.revision,id:item.id,observation:input.value,important:mark.checked});$('dialog').close();renderActivities();}catch(e){error.textContent=e.message;}finally{b.disabled=false;}};
  c.append(element('p',item.title),label,input,markLabel,error,b);
}
function renderActivities(){
  renderAIConsole();
  if(!$('guidancePanel').hidden)renderGuidance();
  const out=$('activityFeed');out.replaceChildren();
  $('activityCount').textContent=taskData.tasks.filter(t=>t.state==='done').length+' concluídas';
  const taskArea=$('activeTasks');taskArea.replaceChildren();
  const order={doing:0,pending:1,awaiting_review:2,blocked:3,done:4,cancelled:5,superseded:6};
  const rank={urgent:0,high:1,normal:2,low:3};
  const terminalRank=t=>({done:1,cancelled:2,superseded:3}[t.state]||0);
  const sorted=[...taskData.tasks].sort((a,b)=>terminalRank(a)-terminalRank(b)||(rank[a.priority||'normal']-rank[b.priority||'normal'])||order[a.state]-order[b.state]);
  const monitoredTasks=new Set((taskData.execution||[]).map(run=>run.task));
  let previousGroup='';
  for(const t of sorted){
    const group=({done:'Concluídas',cancelled:'Canceladas · histórico',superseded:'Substituídas · histórico'}[t.state]||'Prioridade '+priorityLabels[t.priority||'normal']);
    if(group!==previousGroup){taskArea.append(element('h3',group,'activity-priority-heading'));previousGroup=group;}
    const b=element('button',undefined,'activity-task'+(t.state==='done'?' completed':'')+(t.state==='cancelled'?' cancelled':'')+(t.state==='superseded'?' superseded':''));
    b.append(element('strong',t.title));
    const badges=element('div',undefined,'task-meta');badges.append(element('span',terminalRank(t)?taskStateLabel(t):monitoredTasks.has(t.id)?'Em execução':taskBlocked(t)?'Aguardando dependência':taskStateLabel(t),'activity-tag'));if(!['cancelled','superseded'].includes(t.state))badges.append(element('span',priorityLabels[t.priority||'normal'],'activity-tag'));b.append(badges);
    const last=[...(taskData.history||[])].reverse().find(h=>h.task===t.id);if(last)b.append(element('small',new Date(last.at).toLocaleString('pt-BR')));if(t.owner)b.append(element('small','Responsável: '+t.owner));if(t.evidence)b.append(element('span',t.evidence,'task-evidence'));b.onclick=()=>editTask(t);taskArea.append(b);
  }
  if(!sorted.length)taskArea.append(element('p','Nenhuma tarefa cadastrada.'));
  const guidanceEvents=(taskData.history||[]).filter(e=>e.kind==='guidance_consulted').map(e=>({...e,source:'app',evidence:'Consultada por '+e.agent}));
  for(const item of [...activityData.events,...guidanceEvents].sort((a,b)=>new Date(b.at)-new Date(a.at)).filter(e=>e.kind!=='task_changed').filter(e=>activityFilter!=='important'||e.important).slice(0,50)){
    const row=element('article',undefined,'activity-card'+(item.state==='done'?' completed':''));
    const top=element('div',undefined,'activity-card-top');top.append(element('small',item.source==='external'?'Alteração externa':activityLabels[item.kind]||'Atualização'),element('time',new Date(item.at).toLocaleString('pt-BR')));row.append(top,element('strong',item.title));
    if(item.state)row.append(element('span',taskLabels[item.state]||item.state,'activity-tag'));
    if(item.important)row.append(element('span','Importante','activity-tag important'));
    if(item.observation)row.append(element('p',item.observation));
    if(item.evidence)row.append(element('p',item.evidence,'activity-evidence'));
    const actions=element('div',undefined,'activity-actions');
    if(item.id){const observe=element('button','Observação');observe.setAttribute('aria-label','Observação: '+item.title);observe.onclick=()=>editActivity(item);actions.append(observe);}
    const note=notes.find(n=>n.id===item.note);if(note){const b=element('button','Abrir nota');b.onclick=()=>openNote(note);actions.append(b);}
    const task=taskData.tasks.find(t=>t.id===item.task);if(task){const b=element('button','Editar tarefa');b.onclick=()=>editTask(task);actions.append(b);}
    row.append(actions);out.append(row);
  }
  if(!out.children.length)out.append(element('p',activityFilter==='important'?'Nenhuma atividade marcada como importante.':'As próximas alterações aparecerão aqui.'));
}
async function refreshActivities(){
  if(activityBusy)return;activityBusy=true;
  try{await loadTasks();activityData=await api('activities');renderActivities();if(typeof refreshInsights==='function'&&!$('insightsPanel').hidden)refreshInsights();$('activityUpdate').textContent='Atualizado '+new Date().toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit'});}
  catch(e){$('activityUpdate').textContent='Falha ao atualizar';notice(e.message);}finally{activityBusy=false;}
}
$('activityFilter').onchange=()=>{activityFilter=$('activityFilter').value;renderActivities();};
$('refreshActivity').onclick=refreshActivities;
$('allTasks').onclick=async()=>{try{await loadTasks();showTasks();}catch(e){notice(e.message);}};
const newActivityButton=element('button','+ Nova atividade','primary');
newActivityButton.id='newActivity';
newActivityButton.onclick=async()=>{try{await loadTasks();editTask(null);}catch(e){notice(e.message);}};
$('allTasks').before(newActivityButton);
const originalWriteTasks=writeTasks;
writeTasks=async function(tasks,revision){await originalWriteTasks(tasks,revision);await refreshActivities();};
const activityTimer=setInterval(()=>{if(!window.boraBackground&&!document.hidden)refreshActivities();},4000);
document.addEventListener('visibilitychange',()=>{if(!window.boraBackground&&!document.hidden)refreshActivities();});
window.addEventListener('focus',()=>{if(!window.boraBackground&&!document.hidden)refreshActivities();});
selectPanel('activity');refreshActivities();

function renderAIConsole(){
  const out=$('aiConsoleLines');out.replaceChildren();
  const runs=taskData.execution||[],lines=[];
  for(const run of window.boraConsultationRuns||[])lines.push({state:run.active?'CONSULTANDO':'CONSULTOU',agent:run.agent,text:[...run.notes,...(run.folders||[])].join(', '),active:run.active});
  const activeCount=runs.length+(window.boraConsultationRuns||[]).filter(r=>r.active).length;
  $('aiConsoleState').textContent=activeCount?activeCount+' em execução':'Sem execução';

  for(const run of runs){
    const task=taskData.tasks.find(t=>t.id===run.task);if(!task)continue;
    lines.push({state:'EXEC',agent:run.agent,text:task.title,active:true});
    for(const ref of run.guidance||[])lines.push({state:'ORIENTAÇÃO',agent:run.agent,text:'Usando orientação: '+ref.title,at:ref.at,note:ref.id});
  }
  const labels={claimed:'INÍCIO',guidance_consulted:'ORIENTAÇÃO',released:'PAUSA',verified:'OK',contribution:'OK',note_consulted:'CONSULTA',note_written:'ALTEROU',action_failed:'FALHA',action_started:'AÇÃO'};
  const finishedActions=new Set((taskData.history||[]).filter(e=>['note_consulted','note_written','action_failed'].includes(e.kind)).map(e=>e.operation_id));
  for(const event of [...(taskData.history||[])].reverse()){
    if(!labels[event.kind]||!event.agent)continue;
    if(event.kind==='action_started'&&(finishedActions.has(event.operation_id)||Date.now()-new Date(event.at).getTime()>30000))continue;
    if(event.kind==='guidance_consulted'&&lines.some(l=>l.note===event.note&&l.agent===event.agent))continue;
    lines.push({state:event.kind==='action_started'?(event.operation==='read'?'CONSULTANDO':'ALTERANDO'):labels[event.kind],agent:event.agent,text:event.title+(event.kind==='action_failed'?' · operação não concluída':''),at:event.at,active:event.kind==='action_started'});
  }
  const latest=lines[0];
  $('aiConsoleLatest').textContent=latest ? (lines.some(l=>l.active)?'Agora: ':'Última ação: ')+latest.agent+' · '+latest.text : 'Aguardando ações registradas.';
  for(const line of lines.slice(0,20)){
    const row=element('div',undefined,'console-line'+(line.active?' console-active':''));row.setAttribute('role','listitem');
    const state=element('span','['+line.state+']','console-state');
    const text=element('span',line.agent+' · '+line.text,'console-description');
    if(line.active){
      const motion=element('span',undefined,'agent-working-dots console-execution-motion');motion.setAttribute('aria-hidden','true');
      for(let i=0;i<3;i++)motion.append(element('span'));
      state.append(motion);
    }
    row.append(state,text);
    if(line.at)row.append(element('time',new Date(line.at).toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit'})));
    out.append(row);
  }
  if(!out.children.length)out.append(element('p','Aguardando ações registradas.'));
}

