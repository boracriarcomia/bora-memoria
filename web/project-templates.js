'use strict';
const templatesButton=element('button','Modelos: marca e correções');
$('guide').after(templatesButton);
templatesButton.onclick=()=>{
  const content=modal('Modelos do projeto',['Crie apenas os documentos que ainda faltam. Preencha os padrões aprovados da sua empresa.']);
  const templates=[['Manual da marca','## Identidade\nNome e propósito da marca.\n\n## Cores aprovadas\nNome, código e aplicação.\n\n## Fontes aprovadas\nNome, pesos e arquivos/licenças.\n\n## Logos e imagens\nArquivos oficiais, fundos e restrições.\n\n## Componentes\nBotões, espaçamentos, exemplos aprovados.\n\n## Convenções de código\nTecnologias e critérios de revisão.\n\n## Aprovação\nResponsável e data. Não tratar propostas como padrões aprovados.'],['Erros e correções','## Registro\nPara cada problema: sintoma, contexto, causa confirmada, correção, teste de regressão e referência à tarefa.\n\n## Pendências\nSepare hipóteses de causas confirmadas.\n\n## Aprendizado\nPadrões a preservar para evitar recorrência. Relacionar a [[Manual da marca]] quando aplicável.']];
  for(const[title,body]of templates){const button=element('button','Criar '+title);button.onclick=async()=>{try{await refresh();if(notes.some(n=>n.title===title)){notice('Este documento já existe. Abra-o nas notas.');return;}const saved=await api('save',{title,body});$('dialog').close();await refresh();openNote(saved);}catch(error){notice(error.message);}};content.append(button);}
};
