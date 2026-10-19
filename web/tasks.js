'use strict';
let taskData={tasks:[],history:[],revision:''};
const taskLabels={pending:'A fazer',doing:'Em andamento',blocked:'Bloqueada pelo proprietário',done:'Concluída',awaiting_review:'Aguardando revisão',cancelled:'Cancelada',superseded:'Substituída'};
const priorityLabels={urgent:'Urgente',high:'Alta',normal:'Média',low:'Baixa'};
function taskStateLabel(t){return t.state==='doing'&&!(taskData.execution||[]).some(r=>r.task===t.id)?'Reserva expirada':taskLabels[t.state];}
function taskBlocked(t){return t.depends.some(id=>taskData.tasks.find(x=>x.id===id)?.state!=='done');}
function updateProgress(){
  const total=taskData.tasks.length,done=taskData.tasks.filter(t=>t.state==='done').length;
  $('taskSummary').textContent=total?`${done}/${total} concluídas`:'Organizar tarefas';
  $('taskProgress').max=total||1;$('taskProgress').value=done;
  $('taskProgress').setAttribute('aria-label',`${done} de ${total} tarefas concluídas`);
}
async function loadTasks(){taskData=await api('tasks');updateProgress();}
async function writeTasks(tasks,revision=taskData.revision){taskData=await api('tasks',{revision,tasks});updateProgress();}
function taskField(c,label,value='',multiline=false){const id='task-'+label.replace(/\W/g,'');const l=element('label',label),input=element(multiline?'textarea':'input');input.id=id;l.htmlFor=id;input.value=value;c.append(l,input);return input;}
function editTask(task){
  const editRevision=taskData.revision,editTasks=taskData.tasks.map(t=>({...t,depends:[...t.depends]}));
  const c=modal(task?'Editar tarefa':'Nova tarefa',[]);
  const title=taskField(c,'Título da tarefa',task?.title||''),owner=taskField(c,'Responsável',task?.owner||'');title.maxLength=160;owner.maxLength=120;
  const l=element('label','Estado'),state=element('select');state.id='task-state';l.htmlFor=state.id;
  for(const[value,text]of Object.entries(taskLabels)){const o=element('option',text);o.value=value;state.append(o);}state.value=task?.state||'pending';c.append(l,state);
  const pl=element('label','Prioridade'),priority=element('select');priority.id='task-priority';pl.htmlFor=priority.id;
  for(const[value,text]of Object.entries(priorityLabels)){const o=element('option',text);o.value=value;priority.append(o);}priority.value=task?.priority||'normal';c.append(pl,priority);
  const acceptance=taskField(c,'Critério de conclusão',task?.acceptance||'',true);acceptance.maxLength=2000;
  const contract=taskData.governance?.[task?.id];
  const kindLabel=element('label','Tipo de entrega'),kind=element('select');
  for(const [value,text] of [['execution','Execução com verificação do resultado'],['document','Documento com conferência de integridade']]){const o=element('option',text);o.value=value;kind.append(o);}kind.value=contract?.kind==='document'?'document':'execution';c.append(kindLabel,kind);
  const resources=taskField(c,'Arquivos ou áreas afetadas (uma por linha)',contract?.resources?.join('\n')||'',true);
  const evidence=taskField(c,'Evidência de conclusão',task?.evidence||'',true);evidence.maxLength=2000;
  const noteLabel=element('label','Nota relacionada'),note=element('select');note.id='task-note';noteLabel.htmlFor=note.id;
  const empty=element('option','Nenhuma');empty.value='';note.append(empty);
  for(const n of notes){const o=element('option',n.title);o.value=n.id;note.append(o);}note.value=task?.note||'';c.append(noteLabel,note);
  c.append(element('h3','Depende de outras tarefas'),element('p','Marque somente as tarefas necessárias antes desta. Estas caixas não indicam conclusão.'));
  const checks=[];
  for(const t of taskData.tasks.filter(t=>t.id!==task?.id)){const label=element('label'),box=element('input');box.type='checkbox';box.checked=task?.depends?.includes(t.id)||false;label.append(box,document.createTextNode(' '+t.title));c.append(label);checks.push([t.id,box]);}
  const error=element('p');error.setAttribute('role','alert');const saveButton=element('button','Salvar tarefa','primary');
  saveButton.onclick=async()=>{saveButton.disabled=true;try{
    if(state.value==='blocked'&&!evidence.value.trim())throw Error('Informe o motivo do bloqueio pelo proprietário no campo de evidência.');
    if(task?.state==='blocked'&&state.value!=='blocked'&&!confirm('Desbloquear esta tarefa? A retomada está autorizada pelo proprietário.'))return;
    const changed={id:task?.id||'t_'+crypto.randomUUID().replaceAll('-',''),title:title.value,owner:owner.value,state:state.value,evidence:evidence.value,note:note.value,priority:priority.value,acceptance:acceptance.value,depends:checks.filter(([,box])=>box.checked).map(([id])=>id)};
    const next=task?editTasks.map(t=>t.id===task.id?changed:t):[...editTasks,changed];
    const needsPlan=!task||contract?.kind==='legacy'||task.acceptance!==changed.acceptance||contract?.kind!==kind.value||JSON.stringify(contract?.resources||[])!==JSON.stringify(resources.value.split('\n').map(x=>x.trim()).filter(Boolean));
    if(needsPlan){if(changed.state!=='pending')throw Error('Ao definir critérios, deixe a tarefa A fazer; registre evidências antes de concluir.');await api('task-plan',{task:changed,revision:editRevision,kind:kind.value,resources:resources.value.split('\n').map(x=>x.trim()).filter(Boolean)});await loadTasks();}
    else await writeTasks(next,editRevision);await refreshActivities();showTasks();
  }catch(e){error.textContent=e.message;}finally{saveButton.disabled=false;}};c.append(error,saveButton);
}
function showTasks(){
  const c=modal('Etapas e tarefas',[]);
  const tools=element('div'),add=element('button','Nova tarefa','primary'),reload=element('button','Recarregar tarefas'),history=element('button','Histórico');
  add.onclick=()=>editTask(null);reload.onclick=async()=>{try{await loadTasks();showTasks();}catch(e){notice(e.message);}};
  history.onclick=()=>{const h=modal('Histórico de tarefas',['As 200 alterações mais recentes. O histórico completo permanece no banco local.']);for(const item of [...taskData.history].reverse()){h.append(element('p',`${new Date(item.at).toLocaleString('pt-BR')} · ${item.title} · ${taskLabels[item.state]||item.state}`));if(item.evidence)h.append(element('p',item.evidence));}};
  tools.append(add,reload,history);c.append(tools);
  for(const run of taskData.execution||[])c.append(element('p',`${run.agent} está trabalhando nesta tarefa. Outras IAs podem colaborar com coordenação.`));
  if(!taskData.tasks.length)c.append(element('p','Crie a primeira tarefa. Conclusões precisam de evidência registrada.'));
  for(const t of [...taskData.tasks].sort((a,b)=>Object.keys(priorityLabels).indexOf(a.priority||'normal')-Object.keys(priorityLabels).indexOf(b.priority||'normal'))){
    const row=element('div',undefined,'task-row'+(t.state==='done'?' completed':'')+(t.state==='cancelled'?' cancelled':'')+(t.state==='superseded'?' superseded':'')),head=element('div');
    head.append(element('strong',t.title),element('small',taskBlocked(t)?'Aguardando dependência':taskStateLabel(t)));
    if(t.owner)head.append(element('small',t.owner));row.append(head);
    head.append(element('small',priorityLabels[t.priority||'normal']));
    if(t.acceptance)row.append(element('p',t.acceptance));
    const contract=taskData.governance?.[t.id];
    if(contract?.kind==='legacy')row.append(element('p','Tarefa antiga: critérios estruturados ainda precisam de revisão.'));
    if(t.state==='doing'&&!(taskData.execution||[]).some(r=>r.task===t.id))row.append(element('p','Reserva expirada; não há execução ativa confirmada.'));
    if(contract&&contract.kind!=='legacy'){
      for(const criterion of contract.criteria){const item=element('div');item.append(element('p',criterion.description+' · '+criterion.type));
        for(const check of contract.checks.filter(x=>x.criterion===criterion.id))item.append(element('p',(check.passed?'Evidência registrada':'Verificação falhou')+' · '+check.agent));
        const review=element('button','Registrar evidência');review.onclick=()=>{
          const panel=modal('Conferir evidência',['Informe um arquivo dentro do cofre. Uma revisão manual é uma decisão explícita feita nesta interface; um hash só confere integridade.']);
          const artifact=taskField(panel,'Arquivo'),hash=taskField(panel,'SHA-256'),report=taskField(panel,'Relatório de teste (quando necessário)'),reportHash=taskField(panel,'SHA-256 do relatório');
          const save=element('button','Confirmar evidência','primary');save.onclick=async()=>{try{await api('task-evidence',{task_id:t.id,criterion_id:criterion.id,artifact:artifact.value,sha256:hash.value,report:report.value||null,report_sha256:reportHash.value||null,passed:true});await loadTasks();showTasks();}catch(e){notice(e.message);}};panel.append(save);
        };item.append(review);row.append(item);}
    }
    const edit=element('button','Editar '+t.title);edit.onclick=()=>editTask(t);row.append(edit);
    if(t.note){const n=notes.find(n=>n.id===t.note);if(n){const b=element('button','Abrir nota');b.onclick=()=>{$('dialog').close();openNote(n);};row.append(b);}}
    if(t.evidence)row.append(element('p',t.evidence));
    if(t.depends.length)row.append(element('p','Depende de: '+t.depends.map(id=>taskData.tasks.find(x=>x.id===id)?.title||id).join(', ')));
    c.append(row);
  }
}
$('tasksButton').onclick=async()=>{try{await loadTasks();showTasks();}catch(e){notice(e.message);}};
loadTasks().catch(e=>notice('Não foi possível carregar tarefas: '+e.message));
