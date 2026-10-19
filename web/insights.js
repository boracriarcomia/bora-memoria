'use strict';
let insightData=null,insightBusy=false,insightQueued=null,insightKey='',insightFolder='';
const localDay=d=>`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
function completionDays(data){return data.completions.map(e=>({task:e.task,day:localDay(new Date(e.at))}));}
function insightCard(title){const card=element('section',undefined,'insight-card');card.append(element('h3',title));return card;}
async function refreshInsights(force=false){
  if($('insightsPanel').hidden)return;
  // A request in flight may predate a goal save; run once more after it instead of dropping this one.
  if(insightBusy){insightQueued=insightQueued||force;return;}
  const folder=$('folderpath').textContent,key=JSON.stringify([folder,taskData.revision,signature,(taskData.execution||[]).map(r=>[r.task,r.agent]),localDay(new Date()),organizationData?.revision,$('insightPeriod').value]);
  if(!force&&key===insightKey)return;
  insightBusy=true;$('insightStatus').textContent='Atualizando indicadores…';
  try{
    const data=await api('insights');
    if(folder!==$('folderpath').textContent){insightKey='';return;}
    insightData=data;insightFolder=folder;insightKey=key;renderInsights();
    $('insightStatus').textContent='Notas carregadas · tarefas do cofre · '+new Date(data.updated_at).toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit'});
  }catch(e){insightKey='';$('insightContent').replaceChildren();$('insightStatus').textContent='Indicadores indisponíveis. '+e.message;}
  finally{insightBusy=false;if(insightQueued!==null){const again=insightQueued;insightQueued=null;refreshInsights(again);}}
}
function renderInsights(){
  if(!insightData)return;
  const out=$('insightContent');out.replaceChildren();
  const unique=new Map();for(const [a,b] of edges())unique.set(JSON.stringify([a,b].sort()),[a,b]);
  const tasks=taskData.tasks,running=tasks.filter(t=>t.state==='doing'),active=new Set((taskData.execution||[]).map(r=>r.task));
  const summary=element('div',undefined,'insight-numbers');
  for(const [number,label] of [[notes.length,'Notas'],[unique.size,'Conexões'],[running.length,'Andamento']]){const cell=element('div');cell.append(element('strong',String(number)),element('small',label));summary.append(cell);}out.append(summary);
  out.append(element('small','Até 500 notas carregadas; conexões únicas entre notas, sem ligações de pastas. Filtros do mapa não alteram estes totais.','insight-caption'));
  const stateCard=insightCard('Atividades por estado');
  for(const [state,label] of Object.entries(taskLabels)){
    const count=tasks.filter(t=>t.state===state).length;if(!count)continue;
    const button=element('button',undefined,'insight-state');button.append(element('span',label),element('strong',String(count)));
    const bar=element('progress');bar.max=tasks.length||1;bar.value=count;bar.setAttribute('aria-label',`${label}: ${count} de ${tasks.length}`);button.append(bar);
    button.onclick=()=>{const c=modal(label,[]);for(const t of tasks.filter(t=>t.state===state)){const b=element('button',t.title);b.onclick=()=>editTask(t);c.append(b);}};stateCard.append(button);
  }
  if(!tasks.length)stateCard.append(element('p','Nenhuma tarefa cadastrada.'));out.append(stateCard);
  const days=Number($('insightPeriod').value),dates=[];
  for(let i=days-1;i>=0;i--){const d=new Date();d.setDate(d.getDate()-i);dates.push(localDay(d));}
  const completions=completionDays(insightData),counts=dates.map(day=>completions.filter(e=>e.day===day).length),total=counts.reduce((a,b)=>a+b,0);
  const history=insightCard(`Conclusões · ${days} dias`);history.append(element('strong',`${total} tarefas concluídas no período`));
  const chart=svg('svg',{viewBox:'0 0 280 80',role:'img','aria-label':dates.map((d,i)=>`${d}: ${counts[i]}`).join('; '),class:'insight-chart'});
  const max=Math.max(1,...counts),width=270/days;
  counts.forEach((count,i)=>{const rect=svg('rect',{x:5+i*width,y:68-count/max*58,width:Math.max(2,width-3),height:count?count/max*58:1,rx:2,fill:'currentColor'});const title=svg('title',{});title.textContent=dates[i]+': '+count;rect.append(title);chart.append(rect);});history.append(chart);
  history.append(element('small',`${dates[0]} a ${dates.at(-1)} · horário local. Última conclusão registrada de cada tarefa ainda concluída; reabertas não entram.`));
  if(insightData.undated_done||insightData.invalid_dates)history.append(element('p',`${insightData.undated_done} concluídas sem data confiável. Histórico com datas inválidas: ${insightData.invalid_dates}.`));
  out.append(history);
  const goalCard=insightCard('Meta de conclusões'),goal=insightData.goal;
  if(goal){const value=completions.filter(e=>e.day>=goal.start&&e.day<=goal.end).length;goalCard.append(element('strong',`${value} / ${goal.target}`));const bar=element('progress');bar.max=goal.target;bar.value=Math.min(value,goal.target);bar.setAttribute('aria-label',`${value} de ${goal.target} conclusões`);goalCard.append(bar,element('small',`${goal.start} a ${goal.end} · cofre completo`));}
  else goalCard.append(element('p','Sem meta definida.'));
  const define=element('button',goal?'Editar meta':'Definir meta');define.onclick=editInsightGoal;goalCard.append(define);out.append(goalCard);
  const category=element('details',undefined,'insight-card');category.append(element('summary','Mapa de conexões por categoria'));
  const byId=new Map(notes.map(n=>[n.id,mapCategory(n)])),matrix=new Map();
  for(const [a,b] of unique.values()){const key=[byId.get(a),byId.get(b)].sort().join('|');matrix.set(key,(matrix.get(key)||0)+1);}
  const heat=element('div',undefined,'insight-heat');heat.setAttribute('role','group');heat.setAttribute('aria-label','Conexões por categoria');
  for(const a of mapCategories){const row=element('div',undefined,'insight-heat-row');const label=element('button',a.title);label.onclick=()=>{$('mapCategory').value=a.id;refreshMapFilters();};row.append(label);for(const b of mapCategories){const count=matrix.get([a.id,b.id].sort().join('|'))||0;const cell=element('span',String(count));cell.title=`${a.title} ↔ ${b.title}: ${count}`;cell.style.background=count?'color-mix(in srgb, var(--purple) '+Math.min(35,8+count*3)+'%, var(--paper))':'var(--bg)';row.append(cell);}heat.append(row);}category.append(element('small','Colunas na mesma ordem das linhas. Relações entre categorias aparecem simetricamente. Clique no nome para filtrar o mapa.'),heat);
  const clear=element('button','Limpar filtros do mapa');clear.onclick=()=>$('mapClearFilters').click();category.append(clear);out.append(category);
  const ongoing=insightCard('Em andamento');
  for(const t of running.slice(0,3)){const b=element('button',undefined,'insight-task');b.append(element('strong',t.title),element('small',(active.has(t.id)?'Execução ativa':'Sem execução ativa')+' · '+(t.owner||'Sem responsável')));b.onclick=()=>editTask(t);ongoing.append(b);}
  if(!running.length)ongoing.append(element('p','Nenhuma tarefa em andamento.'));
  const all=element('button','Ver todas as atividades');all.onclick=()=>selectPanel('activity');ongoing.append(all);out.append(ongoing);
  const results=element('details',undefined,'insight-card');results.append(element('summary','Resultados registrados'));
  const completed=tasks.filter(t=>t.state==='done'&&t.evidence).slice(-3).reverse();
  for(const t of completed){const b=element('button',t.title,'insight-task');b.onclick=()=>{const c=modal(t.title,[t.evidence]);};results.append(b);}
  if(!completed.length)results.append(element('p','Nenhuma evidência de conclusão disponível.'));out.append(results);
  const usage=element('details',undefined,'insight-card');usage.append(element('summary','Uso e desempenho'));
  const events=activityData.events||[];usage.append(element('p',`${events.length} eventos no histórico recente disponível. Não representa horas de uso nem produtividade.`));
  const graph=$('map');usage.append(element('p',`Última construção do mapa: ${graph.dataset.renderTime||'—'} ms. Trabalho médio por quadro: ${graph.dataset.workMean||'—'} ms.`),element('small','Medições locais da renderização; atualizadas ao reabrir os indicadores. Não medem memória ou desempenho do computador.'));out.append(usage);
}
function editInsightGoal(){
  const revision=insightData.revision,folder=insightFolder,g=insightData.goal,today=localDay(new Date());
  const c=modal('Meta de conclusões',['Conta tarefas ainda concluídas cuja última conclusão registrada está no período. A meta fica salva neste cofre.']);
  const inputs={};for(const [key,label,type,value] of [['target','Quantidade','number',g?.target||10],['start','Início','date',g?.start||today],['end','Fim','date',g?.end||today]]){const l=element('label',label),input=element('input');input.id='goal-'+key;l.htmlFor=input.id;input.type=type;input.value=value;if(key==='target'){input.min=1;input.max=100000;input.step=1;}inputs[key]=input;c.append(l,input);}
  const error=element('p');error.setAttribute('role','alert');const save=element('button','Salvar meta','primary');
  const submit=async goal=>{save.disabled=true;try{if(folder!==$('folderpath').textContent)throw Error('O cofre mudou. Reabra a meta.');await api('insights',{revision,goal});$('dialog').close();await refreshInsights(true);}catch(e){error.textContent=e.message;}finally{save.disabled=false;}};
  save.onclick=()=>submit({target:Number(inputs.target.value),start:inputs.start.value,end:inputs.end.value});c.append(error,save);
  if(g){const remove=element('button','Remover meta');remove.onclick=()=>submit(null);c.append(remove);}
}
$('insightsTab').onclick=()=>selectPanel('insights');
$('insightPeriod').onchange=()=>refreshInsights(true);
const beforeInsightRefresh=refresh;
refresh=async function(){const result=await beforeInsightRefresh();if(!$('insightsPanel').hidden)refreshInsights();return result;};

