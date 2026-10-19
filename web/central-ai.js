'use strict';
let centralData={messages:[]},centralBusy=false,centralDraft='',centralPending='';
let centralRequestId=null;
let centralRecording=null,centralVoiceBusy=false,centralSpeaking=null;
function centralText(node,text){
  // DOM-only Markdown. Model output can never inject HTML, scripts or requests.
  const inline=(parent,value)=>{for(const part of value.split(/(\*\*[^*]+\*\*|`[^`]+`|\*[^*\n]+\*)/g)){if(part.startsWith('**'))parent.append(element('strong',part.slice(2,-2)));else if(part.startsWith('`'))parent.append(element('code',part.slice(1,-1)));else if(part.startsWith('*'))parent.append(element('em',part.slice(1,-1)));else parent.append(document.createTextNode(part));}};
  let list=null,code=null;
  for(const line of text.split('\n')){
    if(line.trim().startsWith('```')){list=null;if(code)code=null;else{code=element('code');const pre=element('pre');pre.append(code);node.append(pre);}continue;}
    if(code){code.append(document.createTextNode(line+'\n'));continue;}
    if(!line.trim()){list=null;continue;}
    if(/^\s*([-*_])\1{2,}\s*$/.test(line)){node.append(element('hr'));list=null;continue;}
    const heading=line.match(/^#{1,6}\s+(.*)$/),item=line.match(/^\s*(?:[-*]|\d+[.)])\s+(.*)$/);
    if(item){const kind=/^\s*\d/.test(line)?'ol':'ul';if(!list||list.tagName.toLowerCase()!==kind){list=element(kind);node.append(list);}const li=element('li');inline(li,item[1]);list.append(li);}
    else{list=null;const p=element(heading?'h3':'p');inline(p,heading?heading[1]:line);node.append(p);}
  }
}
function centralSpeak(text,button){
  if(!('speechSynthesis' in window))return;
  const same=centralSpeaking===button;speechSynthesis.cancel();if(centralSpeaking)centralSpeaking.textContent='Ouvir resposta';centralSpeaking=null;if(same)return;
  const voices=speechSynthesis.getVoices().filter(v=>/^pt[-_]BR/i.test(v.lang)&&v.localService);
  if(!voices.length){$('centralStatus').textContent='Nenhuma voz local em português disponível. Instale uma voz do Windows nas configurações de idioma.';return;}
  const utterance=new SpeechSynthesisUtterance(text.replace(/[#*`]/g,''));utterance.lang='pt-BR';utterance.voice=voices[0];centralSpeaking=button;button.textContent='Parar áudio';
  utterance.onend=utterance.onerror=()=>{button.textContent='Ouvir resposta';if(centralSpeaking===button)centralSpeaking=null;};speechSynthesis.speak(utterance);
}
function centralRender(){
  const out=$('centralMessages');out.replaceChildren();
  if(centralData.memory_only){out.append(element('p',centralData.ownership_message));$('centralStatus').textContent=centralData.ownership_message;}
  if(!centralData.messages.length&&!centralPending){const welcome=element('div',undefined,'central-welcome');welcome.append(element('div','✦','central-orb'),element('h3','Olá, Neidson. O que vamos pensar juntos?'),element('p','Tire uma dúvida, conte uma ideia ou converse sobre seus projetos. Eu uso o Bora para acompanhar o contexto.'));out.append(welcome);}
  const messages=[...centralData.messages];if(centralPending)messages.push({role:'user',content:centralPending});
  for(const m of messages){const card=element('article',undefined,'central-message '+m.role),body=element('div',undefined,'central-message-body');card.append(element('strong',m.role==='user'?'Você':'✦ Central IA'));if(m.role==='user')body.textContent=m.content;else centralText(body,m.content);card.append(body);
    if(m.role==='assistant'&&'speechSynthesis' in window){const b=element('button','Ouvir resposta','central-listen');b.onclick=()=>centralSpeak(m.content,b);card.append(b);}
    if(m.sources?.length){const details=element('details'),summary=element('summary',m.sources.length+' notas usadas');details.append(summary);for(const s of m.sources){const b=element('button',s.title);b.onclick=async()=>{const n=notes.find(n=>n.id===s.id);if(n){centralToggle(false);await openNote(n);}};details.append(b);}card.append(details);}out.append(card);
  }
  out.setAttribute('aria-busy',String(centralBusy));
  if(centralBusy){const thinking=element('div',undefined,'central-thinking');thinking.setAttribute('role','status');const dots=element('span',undefined,'central-dots');dots.setAttribute('aria-hidden','true');for(let i=0;i<3;i++)dots.append(element('i'));thinking.append(dots,element('span','A Central está preparando sua resposta…'));out.append(thinking);}
  out.scrollTop=out.scrollHeight;
}
async function centralToggle(open){
  $('centralPanel').hidden=!open;document.querySelector('.workspace').hidden=open;document.body.classList.toggle('central-active',open);$('centralOpen').setAttribute('aria-pressed',String(open));
  if(!open){if(centralRecording)await centralEndRecording(true);if('speechSynthesis' in window)speechSynthesis.cancel();return;}
  $('centralInput').value=centralDraft;
  const selected=new Set([...$('centralNotes').selectedOptions].map(o=>o.value));$('centralNotes').replaceChildren();for(const n of notes){const o=element('option',n.title);o.value=n.id;o.selected=selected.has(n.id);$('centralNotes').append(o);}
  try{centralData=await api('central-ia');centralRender();if(!centralData.available)$('centralStatus').textContent='Conecte o Antigravity para conversar.';if(!centralData.voice?.available){$('centralMic').disabled=true;$('centralMic').title='Modelo local de voz não instalado neste computador.';}}catch(e){$('centralStatus').textContent=e.message;}if(!centralBusy)$('centralInput').focus();
}
function centralControls(){const locked=centralBusy||centralVoiceBusy||!!centralRecording;$('centralSend').disabled=locked;$('centralInput').disabled=centralBusy||centralVoiceBusy;$('centralMic').disabled=centralBusy||centralVoiceBusy||!centralData.voice?.available;for(const id of ['centralBrief','centralNext','centralSave','centralTask'])$(id).disabled=locked;}
async function centralSend(text){
  if(centralBusy||centralVoiceBusy||centralRecording||!text.trim())return;
  const chosen=[...$('centralNotes').selectedOptions].map(o=>o.value);if(chosen.length>20){$('centralStatus').textContent='Selecione no máximo 20 notas.';return;}
  centralRequestId=centralRequestId||crypto.randomUUID();centralBusy=true;centralPending=text;centralDraft=text;centralControls();centralRender();$('centralStatus').textContent='Consultando o Bora e preparando a resposta…';
  try{const voice=centralData.voice;centralData=await api('central-ia',{message:text,notes:chosen,request_id:centralRequestId});centralData.voice=voice;$('centralInput').value='';centralDraft='';centralRequestId=null;$('centralStatus').textContent='Enter envia · Shift + Enter faz uma nova linha.';}
  catch(e){$('centralInput').value=centralDraft;$('centralStatus').textContent=e.message+' Sua mensagem foi preservada para tentar novamente.';}
  finally{centralBusy=false;centralPending='';centralControls();centralRender();$('centralInput').focus();}
}
function centralWav(chunks,rate){
  let length=chunks.reduce((n,c)=>n+c.length,0),samples=new Float32Array(length),position=0;for(const chunk of chunks){samples.set(chunk,position);position+=chunk.length;}
  const count=Math.floor(length*16000/rate),buffer=new ArrayBuffer(44+count*2),view=new DataView(buffer),write=(offset,text)=>{for(let i=0;i<text.length;i++)view.setUint8(offset+i,text.charCodeAt(i));};
  write(0,'RIFF');view.setUint32(4,36+count*2,true);write(8,'WAVE');write(12,'fmt ');view.setUint32(16,16,true);view.setUint16(20,1,true);view.setUint16(22,1,true);view.setUint32(24,16000,true);view.setUint32(28,32000,true);view.setUint16(32,2,true);view.setUint16(34,16,true);write(36,'data');view.setUint32(40,count*2,true);
  // Average input samples over each output interval to limit downsampling aliasing.
  for(let i=0;i<count;i++){const start=Math.floor(i*rate/16000),end=Math.max(start+1,Math.floor((i+1)*rate/16000));let sum=0;for(let j=start;j<end&&j<length;j++)sum+=samples[j];const value=Math.max(-1,Math.min(1,sum/(end-start)));view.setInt16(44+i*2,value<0?value*32768:value*32767,true);}
  const bytes=new Uint8Array(buffer);let binary='';for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode(...bytes.subarray(i,i+8192));return btoa(binary);
}
async function centralEndRecording(discard=false){
  const rec=centralRecording;if(!rec)return;centralRecording=null;clearTimeout(rec.timer);clearInterval(rec.clock);rec.processor.onaudioprocess=null;rec.processor.disconnect();rec.source.disconnect();rec.stream.getTracks().forEach(track=>track.stop());await rec.context.close();$('centralMic').textContent='◉ Ditar';$('centralMic').setAttribute('aria-pressed','false');$('centralMicCancel').hidden=true;
  if(discard){centralControls();$('centralStatus').textContent='Áudio descartado. Sua mensagem foi preservada.';return;}
  centralVoiceBusy=true;centralControls();$('centralStatus').textContent='Transcrevendo neste computador…';
  try{const result=await api('central-voice',{audio:centralWav(rec.chunks,rec.rate)}),before=$('centralInput').value,combined=(before?before.trimEnd()+'\n':'')+result.text;if(combined.length>8000){$('centralStatus').textContent='A transcrição excede o limite da mensagem. Envie ou reduza o rascunho antes de ditar novamente.';}else{$('centralInput').value=combined;centralDraft=combined;$('centralStatus').textContent='Transcrição pronta. Revise nomes e pontuação e clique em Enviar.';}}
  catch(e){$('centralStatus').textContent=e.message;}
  finally{centralVoiceBusy=false;centralControls();$('centralInput').focus();}
}
async function centralStartRecording(){
  if(centralRecording){await centralEndRecording();return;}if(centralBusy||centralVoiceBusy)return;
  if(!navigator.mediaDevices?.getUserMedia||!(window.AudioContext||window.webkitAudioContext)){$('centralStatus').textContent='Microfone indisponível neste ambiente. Você também pode ditar com Windows + H no campo de mensagem.';return;}
  centralVoiceBusy=true;centralControls();let stream,context;
  try{stream=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true,noiseSuppression:true}});context=new (window.AudioContext||window.webkitAudioContext)();await context.resume();const source=context.createMediaStreamSource(stream),processor=context.createScriptProcessor(4096,1,1),chunks=[];const rec={stream,context,source,processor,chunks,rate:context.sampleRate};processor.onaudioprocess=e=>{if(centralRecording===rec)chunks.push(new Float32Array(e.inputBuffer.getChannelData(0)));};source.connect(processor);processor.connect(context.destination);centralRecording=rec;rec.timer=setTimeout(()=>centralEndRecording(),60000);const started=Date.now();rec.clock=setInterval(()=>{$('centralMic').textContent='■ Concluir · '+Math.floor((Date.now()-started)/1000)+' s';},1000);$('centralMic').textContent='■ Concluir ditado';$('centralMic').setAttribute('aria-pressed','true');$('centralMicCancel').hidden=false;$('centralStatus').textContent='Ouvindo por até 60 segundos. Clique em Concluir para transcrever. Nada será enviado automaticamente.';}
  catch(e){stream?.getTracks().forEach(track=>track.stop());if(context)await context.close();$('centralStatus').textContent=e.name==='NotAllowedError'?'Permita o microfone para ditar. Como alternativa, use Windows + H no campo de mensagem.':'Não consegui abrir o microfone. Confira o dispositivo nas configurações de som.';}
  finally{centralVoiceBusy=false;centralControls();}
}
$('centralInput').addEventListener('input',()=>{centralDraft=$('centralInput').value;centralRequestId=null;});
$('centralInput').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();centralSend($('centralInput').value);}});
$('centralOpen').onclick=()=>centralToggle(true);$('centralClose').onclick=()=>centralToggle(false);
$('centralContextToggle').onclick=()=>{const open=$('centralContext').hidden;$('centralContext').hidden=!open;$('centralContextToggle').setAttribute('aria-expanded',String(open));$('centralPanel').classList.toggle('with-context',open);};
$('centralMic').onclick=centralStartRecording;$('centralMicCancel').onclick=()=>centralEndRecording(true);
document.addEventListener('visibilitychange',()=>{if((document.hidden||window.boraBackground)&&centralRecording)centralEndRecording(true);});
window.addEventListener('pagehide',()=>{if(centralRecording)centralRecording.stream.getTracks().forEach(t=>t.stop());if('speechSynthesis' in window)speechSynthesis.cancel();});
$('centralForm').onsubmit=e=>{e.preventDefault();centralSend($('centralInput').value);};
$('centralBrief').onclick=()=>centralSend('Prepare meu resumo do dia: o que consta como feito, o que está em andamento, bloqueios e próximos passos. Distinga registro histórico de verificação atual.');
$('centralNext').onclick=()=>centralSend('Com base nas prioridades e dependências registradas, quais são os três próximos passos? Explique o motivo e indique o que falta decidir.');
$('centralSave').onclick=async()=>{if(centralBusy||!centralData.messages.length)return;try{const body=centralData.messages.map(m=>'## '+(m.role==='user'?'Você':'Central IA')+'\n\n'+m.content).join('\n\n');await api('save',{title:'Central IA — conversa '+new Date().toLocaleString('pt-BR'),body});notice('Conversa salva como nota.');await refresh();}catch(e){notice(e.message);}};
$('centralTask').onclick=async()=>{if(centralBusy)return;try{await loadTasks();editTask(null);const user=[...centralData.messages].reverse().find(m=>m.role==='user');if(user){const title=$('task-Ttulodatarefa');if(title)title.value=user.content.slice(0,160);}}catch(e){notice(e.message);}};
