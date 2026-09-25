/* Cronômetro local: pausas não contam; somente a confirmação grava uma atividade. */
(function () {
    'use strict';
    const raiz = document.getElementById('cronometro');
    if (!raiz) return;
    const el = id => document.getElementById(id);
    const selecao = el('timerAtividade');
    const erro = el('timerErro');
    const salvar = el('timerBotaoSalvar');
    const chave = 'lifes-on-atividade-' + raiz.dataset.usuario;
    let acumulado = 0, inicio = null, intervalo = null, segundos = 0, tipo = '', treinoId = null, enviando = false;

    function estado(id) {
        ['timerFormulario', 'timerRodando', 'timerConfirmacao', 'timerConcluido'].forEach(nome => {
            el(nome).hidden = nome !== id;
        });
    }
    function avisar(texto) { erro.textContent = texto; erro.hidden = false; }
    function tempo() { return acumulado + (inicio === null ? 0 : performance.now() - inicio); }
    function formatar(total) {
        return [Math.floor(total / 3600), Math.floor(total / 60) % 60, total % 60]
            .map(n => String(n).padStart(2, '0')).join(':');
    }
    function atualizar() {
        el('timerRelogio').textContent = formatar(Math.floor(tempo() / 1000));
    }
    function pausar() {
        acumulado = tempo(); inicio = null;
        clearInterval(intervalo); intervalo = null; atualizar();
        el('timerBotaoPausar').textContent = 'Continuar';
        el('timerEstado').textContent = 'Pausado';
    }
    function continuar() {
        inicio = performance.now();
        intervalo = setInterval(atualizar, 250);
        el('timerBotaoPausar').textContent = 'Pausar';
        el('timerEstado').textContent = 'Em andamento';
        estado('timerRodando'); atualizar();
    }
    function cancelar() {
        if (enviando) return;
        if (!window.confirm('Cancelar esta atividade sem salvar?')) return;
        pausar(); acumulado = 0; erro.hidden = true;
        estado('timerFormulario'); selecao.focus();
    }
    function mostrarSucesso(dados) {
        el('timerMensagem').textContent = 'Atividade concluída! ' + (dados.titulo_treino || dados.tipo_exercicio) + ' • ' + dados.duracao + (dados.duracao === 1 ? ' minuto' : ' minutos');
        const lista = el('timerConquistas'); lista.replaceChildren();
        (dados.novas_conquistas || []).forEach(conquista => {
            const item = document.createElement('p');
            item.className = 'timer-conquista';
            item.textContent = '🏆 Conquista desbloqueada: ' + conquista.nome + ' — ' + conquista.descricao;
            lista.appendChild(item);
        });
        estado('timerConcluido'); el('timerConcluido').focus();
    }
    function iniciarTreino() {
        if (!selecao || !selecao.value || el('timerFormulario').hidden) return;
        treinoId = Number(selecao.value);
        tipo = selecao.selectedOptions[0].dataset.titulo; acumulado = 0; erro.hidden = true;
        el('timerModalidade').value = '';
        el('timerTipoAtual').textContent = tipo; continuar(); el('timerBotaoPausar').focus();
    }
    if (selecao) {
        selecao.addEventListener('change', () => { el('timerBotaoIniciar').disabled = !selecao.value; });
        el('timerBotaoIniciar').addEventListener('click', iniciarTreino);
    }
    document.querySelectorAll('[data-iniciar-treino]').forEach(botao => {
        botao.addEventListener('click', () => {
            if (!selecao || el('timerFormulario').hidden) {
                raiz.scrollIntoView();
                return;
            }
            selecao.value = botao.dataset.iniciarTreino;
            el('timerBotaoIniciar').disabled = !selecao.value;
            iniciarTreino();
        });
    });
    el('timerBotaoPausar').addEventListener('click', () => { inicio === null ? continuar() : pausar(); });
    el('timerBotaoConcluir').addEventListener('click', () => {
        pausar(); segundos = Math.floor(acumulado / 1000);
        if (segundos < 30) { avisar('Atividade muito curta: mínimo 30 segundos. Continue ou cancele.'); return; }
        if (segundos > 86400) { avisar('A sessão deve ter no máximo 24 horas. Cancele e registre a duração pela página de atividades.'); return; }
        erro.hidden = true; salvar.disabled = false;
        el('timerResumo').textContent = tipo + ' • ' + formatar(segundos) + ' • ' + Math.max(1, Math.floor((segundos + 30) / 60)) + ' min';
        estado('timerConfirmacao'); el('timerConfirmacao').focus();
    });
    el('timerBotaoVoltar').addEventListener('click', () => { erro.hidden = true; continuar(); });
    raiz.querySelectorAll('[data-cancelar]').forEach(botao => botao.addEventListener('click', cancelar));
    el('timerBotaoNovo').addEventListener('click', () => { acumulado = 0; estado('timerFormulario'); if (selecao) selecao.focus(); });
    salvar.addEventListener('click', async () => {
        if (enviando || salvar.disabled) return;
        if (!el('timerModalidade').value) { avisar('Selecione o tipo de exercício realizado.'); el('timerModalidade').focus(); return; }
        enviando = true; erro.hidden = true;
        el('timerConfirmacao').querySelectorAll('button').forEach(b => { b.disabled = true; });
        salvar.textContent = 'Salvando…';
        try {
            const resposta = await fetch(raiz.dataset.url, {
                method: 'POST', credentials: 'same-origin',
                headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': raiz.dataset.csrf },
                body: JSON.stringify({ id_agenda: treinoId, tipo_exercicio: el('timerModalidade').value, segundos_decorridos: segundos })
            });
            const dados = await resposta.json();
            if (!resposta.ok || !dados.registrado) {
                // Falhas de servidor podem ocorrer depois do INSERT: conferir antes de reenviar.
                if (resposta.status >= 500) throw new Error('resultado incerto');
                el('timerConfirmacao').querySelectorAll('button').forEach(b => { b.disabled = false; });
                avisar(dados.erro || 'Não foi possível registrar. Atualize a página e confira sua sessão.');
                return;
            }
            // O resumo é relido do Flask/Supabase; não incrementamos gráficos artificialmente.
            try {
                sessionStorage.setItem(chave, JSON.stringify(dados));
                window.location.reload();
            } catch (_) {
                mostrarSucesso(dados);
                setTimeout(() => window.location.reload(), 3500);
            }
        } catch (_) {
            avisar('Não foi possível confirmar o salvamento. Atualize a página e confira suas atividades antes de registrar novamente.');
        } finally {
            enviando = false; salvar.textContent = 'Confirmar e salvar';
        }
    });
    try {
        const feedback = sessionStorage.getItem(chave);
        sessionStorage.removeItem(chave);
        if (feedback) mostrarSucesso(JSON.parse(feedback));
    } catch (_) { /* A atividade permanece salva mesmo sem armazenamento local. */ }
})();
