/* Conectores de IA: status real lido do computador, somente leitura. */
(() => {
  const button = element('button', 'Conectores de IA');
  button.id = 'connectorsButton';
  $('guide').before(button);
  const date = value => { if (!value) return 'sem registro'; const d = new Date(value); return isNaN(d) ? value : d.toLocaleString('pt-BR', {dateStyle: 'short', timeStyle: 'short'}); };
  const badge = (ok, yes, no, warn) => element('span', ok ? yes : no, 'connector-badge ' + (ok ? 'ok' : (warn ? 'warn' : 'bad')));
  function row(label, value) { const r = element('div', undefined, 'connector-row'); r.append(element('span', label, 'connector-label'), element('span', value, 'connector-value')); return r; }
  function card(item) {
    const c = element('section', undefined, 'connector-card');
    const head = element('header');
    head.append(element('strong', item.client + (item.profile ? ' · perfil ' + item.profile : '')));
    if (!item.configured) head.append(badge(false, '', 'Bora não configurado', true));
    else if (!item.command_exists) head.append(badge(false, '', 'Executável não encontrado'));
    else if (!item.uses_this_vault) head.append(badge(false, '', 'Usa outro cofre', true));
    else if (item.enabled === false) head.append(badge(false, '', 'Desativado', true));
    else head.append(badge(true, 'Configurado', ''));
    c.append(head);
    if (item.configured) {
      c.append(row('Programa', item.command_name || '—'));
      c.append(row('Cofre', item.uses_this_vault ? 'este cofre' : (item.workspace || 'não informado')));
      c.append(row('Acesso', item.access === 'somente leitura' ? 'Somente leitura' : 'Leitura e escrita de notas e tarefas'));
    }
    if ('last_activity' in item) c.append(row('Última ação registrada', date(item.last_activity)));
    c.append(row('Configuração', item.config_file));
    if (item.identification) c.append(element('p', item.identification, 'connector-note'));
    if (item.cache_warning) c.append(element('p', item.cache_warning, 'connector-note'));
    if (item.error) c.append(element('p', item.error, 'connector-note'));
    return c;
  }

  function telegramCard(initial) {
    const c = element('section', undefined, 'connector-card');
    const head = element('header'); head.append(element('strong', 'Telegram')); c.append(head);
    const body = element('div'); c.append(body);
    const msg = element('p', '', 'connector-note'); msg.setAttribute('role', 'status');
    async function act(payload) {
      msg.textContent = '';
      try { render(await api('telegram', payload)); } catch (e) { msg.textContent = e.message; }
    }
    function render(t) {
      body.replaceChildren();
      head.querySelector('.connector-badge')?.remove();
      head.append(t.linked ? badge(true, 'Vinculado', '') : (t.configured ? badge(false, '', 'Aguardando vínculo', true) : badge(false, '', 'Não configurado', true)));
      if (t.configured) {
        body.append(row('Bot', t.bot ? '@' + t.bot : '—'), row('Token', t.token));
        if (t.linked) body.append(row('Chat autorizado', t.chat));
        body.append(row('Modo', t.mode === 'capture' ? 'Captura de notas' : 'Conversa com a Central IA'));
        body.append(element('p', 'Converse normalmente, com ou sem ?. Use /nota para guardar um texto e /conversar para voltar ao chat.', 'connector-note'));
        if (t.last_delivery?.at) body.append(row('Última resposta enviada', date(t.last_delivery.at)));
        body.append(row('Recebimento', t.running ? 'ativo (só com o Bora aberto)' : 'parado'));
        if (t.last_activity) body.append(row('Última mensagem', date(t.last_activity)));
        if (t.last_error) body.append(element('p', t.last_error, 'connector-note'));
        if (!t.linked) {
          if (t.code) {
            body.append(row('Código', t.code + ' (expira em ' + Math.ceil(t.code_expires_in / 60) + ' min)'));
            body.append(element('p', 'No Telegram, abra o bot' + (t.bot ? ' @' + t.bot : '') + ' e envie: /vincular ' + t.code, 'connector-note'));
            if (t.link) { const a = element('a', t.link); a.href = t.link; a.target = '_blank'; a.rel = 'noopener noreferrer'; body.append(a); }
          }
          const gen = element('button', t.code ? 'Gerar novo código' : 'Gerar código de vínculo'); gen.onclick = () => act({action: 'code'}); body.append(gen);
        }
        const off = element('button', 'Desconectar'); off.onclick = () => { if (confirm('Desconectar o Telegram e apagar o token deste computador?')) act({action: 'disconnect'}); }; body.append(off);
      } else {
        body.append(element('p', 'Crie um bot no @BotFather, copie o token e cole aqui. O token fica só neste computador, fora do cofre.', 'connector-note'));
        const input = element('input'); input.type = 'password'; input.autocomplete = 'off'; input.placeholder = 'Token do BotFather'; input.setAttribute('aria-label', 'Token do BotFather');
        const save = element('button', 'Salvar token'); save.onclick = () => { const v = input.value; input.value = ''; act({action: 'token', token: v}); };
        body.append(input, save);
      }
      body.append(element('p', t.limits, 'connector-note'), msg);
    }
    render(initial);
    return c;
  }
  async function show() {
    const c = modal('Conectores de IA', ['Clientes de IA que usam este cofre pelo programa local do Bora (MCP). Esta tela só lê as configurações; não altera nada e não mostra chaves ou senhas.']);
    c.classList.add('connectors-panel');
    $('dialog').classList.add('connectors-dialog');
    $('dialog').addEventListener('close', () => { c.classList.remove('connectors-panel'); $('dialog').classList.remove('connectors-dialog'); }, {once: true});
    const status = element('p', 'Conferindo…'); status.setAttribute('role', 'status'); c.append(status);
    let state;
    try { state = await api('connectors'); }
    catch (e) { status.textContent = 'Não foi possível conferir os conectores: ' + e.message; return; }
    status.remove();
    const v = state.vault, b = state.bridge;
    const summary = element('section', undefined, 'connector-card connector-summary');
    const sh = element('header'); sh.append(element('strong', 'Cofre e programa de conexão')); summary.append(sh);
    summary.append(row('Cofre', (v.accessible ? 'acessível' : 'inacessível') + (v.writable ? '' : ', sem permissão de escrita') + ' · ' + v.notes + ' de ' + v.note_limit + ' notas'));
    summary.append(row('Pasta do cofre', v.path));
    summary.append(row('Programa', b.exists ? b.name + ' · ' + b.size_mb + ' MB · ' + date(b.modified) : b.name + ' não encontrado nesta instalação' + (b.installation ? ' (' + b.installation + ')' : '')));
    if (b.exists) summary.append(row('Identificação (SHA-256)', b.sha256 + '…'));
    summary.append(element('p', 'Apesar do nome "Consultas", este programa permite ler e também gravar notas e tarefas. Cada cliente o inicia por conta própria; fechar o Bora não desconecta as IAs.', 'connector-note'));
    c.append(summary);
    if (!state.clients.length) c.append(element('p', 'Nenhuma configuração de cliente encontrada neste perfil do Windows.'));
    for (const item of state.clients) c.append(card(item));
    try { c.append(telegramCard(await api('telegram'))); } catch (e) { c.append(element('p', 'Telegram indisponível: ' + e.message, 'connector-note')); }
    const limits = element('section', undefined, 'connector-card');
    const lh = element('header'); lh.append(element('strong', 'O que uma IA conectada pode fazer')); limits.append(lh);
    limits.append(row('Ler', 'contexto do projeto, notas, tarefas, histórico e orientações'));
    limits.append(row('Gravar', 'criar e atualizar notas (a versão anterior fica guardada), criar e atualizar tarefas pendentes, assumir tarefas, registrar evidências e bloqueios, exportar cópia do cofre'));
    limits.append(row('Não pode', state.limits.not_available.join('; ')));
    limits.append(element('p', '"Configurado" significa que a configuração existe e aponta para o programa; o Bora não confirma se o cliente está aberto agora. A última ação vem do registro do próprio Bora. O nome do cliente é declarado por ele, não é uma autenticação.', 'connector-note'));
    c.append(limits);
    c.append(element('small', 'Conferido em ' + date(state.checked_at), 'connector-note'));
  }
  button.onclick = show;
})();
