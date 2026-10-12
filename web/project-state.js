'use strict';
$('projectState').onclick=async()=>{
  try{
    const data=await api('project-state'),state=data.state;
    const c=modal('Estado e padrões do projeto',['Este resumo vigente é separado do histórico. Alterações de regras nesta interface sinalizam tarefas que precisam de revisão.']);
    const objective=taskField(c,'Objetivo atual',state.objective||'',true);
    const scope=taskField(c,'Escopo autorizado',state.authorized_scope||'',true);
    const advanced=element('details'),summary=element('summary','Versões, decisões e padrões');advanced.append(summary);c.append(advanced);
    const versions=taskField(advanced,'Versões (JSON)',JSON.stringify(state.versions||{},null,2),true);
    const decisions=taskField(advanced,'Decisões vigentes e substituídas (JSON)',JSON.stringify(state.decisions||[],null,2),true);
    const rules=taskField(advanced,'Regras, origens e escopos (JSON)',JSON.stringify(state.rules||[],null,2),true);
    c.append(element('p','Regras são orientações e limites da ponte; não garantem que qualquer IA ou programa externo siga o padrão. Não guarde senhas nesta configuração.'));
    const error=element('p'),save=element('button','Salvar estado vigente','primary');
    save.onclick=async()=>{try{await api('project-state',{revision:data.revision,state:{version:1,objective:objective.value,authorized_scope:scope.value,versions:JSON.parse(versions.value),decisions:JSON.parse(decisions.value),rules:JSON.parse(rules.value)}});$('dialog').close();notice('Estado vigente salvo.');}catch(e){error.textContent=e.message;}};
    c.append(error,save);
  }catch(e){notice(e.message);}
};
