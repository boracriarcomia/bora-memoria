window.boraConsultationRuns=[];
let consultationBusy=false;
function updateConsultationMarkers(){
 document.querySelectorAll('.map-consultation-active').forEach(n=>n.classList.remove('map-consultation-active'));
 for(const run of window.boraConsultationRuns){
  for(const folder of run.folders||[]){
   const node=[...document.querySelectorAll('#map [data-folder]')].find(n=>n.dataset.folder===folder);
   if(node)node.classList.add('map-consultation-active');
  }
  for(const name of run.notes||[]){
   const nodes=[...document.querySelectorAll('#map [data-note],#map [data-folder]')];
   const exact=nodes.find(n=>n.dataset.note===name);
   const folder=name.includes('/')?name.slice(0,name.lastIndexOf('/')):'';
   const parent=nodes.filter(n=>n.dataset.folder&&(folder===n.dataset.folder||folder.startsWith(n.dataset.folder+'/'))).sort((a,b)=>b.dataset.folder.length-a.dataset.folder.length)[0];
   const target=exact||parent;
   if(target){target.classList.add('map-consultation-active');target.setAttribute('aria-description',run.agent+(run.active?' consultando: ':' consultou: ')+name);}
  }
 }
 if(typeof renderAIConsole==='function')renderAIConsole();
}
async function refreshConsultations(){
 if(consultationBusy||window.boraBackground||document.hidden)return;
 consultationBusy=true;
 try{const state=await api('consultations');window.boraConsultationRuns=state.runs||[];}
 catch(e){window.boraConsultationRuns=[];}
 finally{consultationBusy=false;updateConsultationMarkers();}
}
setInterval(refreshConsultations,1200);
document.addEventListener('visibilitychange',()=>{document.documentElement.classList.toggle('bora-background',!!window.boraBackground||document.hidden);refreshConsultations();});
refreshConsultations();
