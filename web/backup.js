/* Direct Drive API; connecting never uploads a vault. */
(() => {
  let timer;
  $('backupCenter').onclick = async () => {
    const c = modal('Backup local e Google Drive', [
      'Crie versões completas com notas, anexos, tarefas e configurações. O backup local é preservado mesmo se o envio ao Drive falhar.',
      'Conecte sua própria conta Google. No primeiro envio, o Bora cria a pasta Bora Memória no seu Drive. Conectar a conta não envia notas.'
    ]);
    c.classList.add('backup-panel');
    $('dialog').addEventListener('close', () => { c.classList.remove('backup-panel'); clearTimeout(timer); }, {once:true});
    const local = element('p'), drive = element('p'), auth = element('p'), automatic = element('p'), status = element('div'), controls = element('div');
    status.setAttribute('role','status'); auth.setAttribute('role','status');
    c.append(local,drive,auth,automatic,status,controls);
    const buttons=[];
    function button(label,action,disabled) {
      const b=element('button',label); buttons.push({b,disabled}); controls.append(b);
      b.onclick=async () => {
        buttons.forEach(x=>x.b.disabled=true);
        try { await action(); await refresh(); }
        catch(e) { status.textContent=e.message; await refresh(false).catch(()=>{}); }
      };
    }
    async function refresh(replaceStatus=true) {
      const state=await api('backup-state'), connection=state.drive;
      local.textContent='Destino local: '+state.settings.local;
      drive.textContent='Google Drive: '+(connection.connected?'Conta autorizada neste perfil Windows.':connection.authorizing?'Aguardando autorização no navegador.':connection.configured?'Configuração disponível; conta desconectada.':'Configuração OAuth Desktop pendente.');
      auth.textContent=connection.message||'';
      automatic.textContent='Backup automático: '+(state.automatic.enabled?'ativado. ':'desativado. ')+state.automatic.message;
      if(replaceStatus) {
        status.replaceChildren(element('p',state.status.message));
        if(state.status.local_path) status.append(element('p','ZIP local: '+state.status.local_path));
        if(state.status.remote_sync==='verified') status.append(element('p','Tamanho e checksum conferidos na API do Drive.'));
      }
      buttons.forEach(x=>x.b.disabled=state.busy||!!(x.disabled&&x.disabled(connection)));
      clearTimeout(timer);
      if($('dialog').open&&c.contains(status)) timer=setTimeout(()=>refresh().catch(e=>status.textContent=e.message),state.busy||connection.authorizing?1000:10000);
    }
    button('Escolher destino local',()=>api('backup-destination',{kind:'local'}));
    button('Importar configuração OAuth Desktop',()=>api('drive-config',{}),d=>d.connected||d.authorizing);
    button('Conectar minha conta Google',()=>api('drive-connect',{}),d=>!d.configured||d.connected||d.authorizing);
    button('Cancelar autorização',()=>api('drive-cancel',{}),d=>!d.authorizing);
    button('Desconectar conta',()=>api('drive-disconnect',{}),d=>!d.configured||d.authorizing);
    const run=async remote=>{
      if(dirty) throw Error('Salve a nota aberta antes de iniciar o backup.');
      await api('backup-run',{remote});
    };
    button('Criar somente backup local',()=>run(false));
    button('Criar backup local e enviar ao Drive',()=>run(true),d=>!d.connected);
    button('Ativar backup automático no Drive',()=>api('backup-automatic',{enabled:true}),d=>!d.connected);
    button('Desativar backup automático',()=>api('backup-automatic',{enabled:false}));
    c.append(element('p','O automático envia versões das alterações salvas após dois minutos, com limite de quinze minutos durante edição contínua. Funciona enquanto o Bora estiver aberto ou na bandeja; Sair ou desligar o computador interrompe o agendamento. Ao reabrir, mudanças pendentes são detectadas.'));
    c.append(element('p','Para restaurar: baixe o ZIP do Drive quando necessário, extraia em uma pasta vazia e abra a pasta cofre. Preserve a base atual até conferir a recuperação. Este ZIP completo não usa Restaurar backup de notas.'));
    try { await refresh(); } catch(e) { status.textContent=e.message; }
    c.scrollTop=0;
  };
})();
