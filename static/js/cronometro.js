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
    const pendencia = chave + '-pendente';
    function limparPendencia() {try {sessionStorage.removeItem(pendencia);} catch (_) {}}
    let chaveRegistro = null;
    let acumulado = 0, inicio = null, intervalo = null, segundos = 0, tipo = '', treinoId = null, enviando = false;

    function estado(id) {
        ['timerFormulario', 'timerRodando', 'timerConfirmacao', 'timerConcluido'].forEach(nome => {
            el(nome).hidden = nome !== id;
        });
    }
    function avisar(texto) { window.LifesUI?.som('erro'); erro.textContent = texto; erro.hidden = false; }
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
        limparPendencia();
        estado('timerFormulario'); selecao.focus();
    }
    function mostrarSucesso(dados) {
        limparPendencia();
        if (dados.recompensa) {
            window.LifesUI?.som('treino', true);
            setTimeout(() => window.LifesUI?.recompensar(dados.recompensa), 400);
        }
        el('timerMensagem').textContent = 'Atividade concluída! ' + (dados.titulo_treino || dados.tipo_exercicio) + ' • ' + dados.duracao + (dados.duracao === 1 ? ' minuto' : ' minutos');
        if (dados.duplicado) el('timerMensagem').textContent = 'Treino já registrado; nenhum XP adicional.';
        if (dados.situacao === 'excluida') el('timerMensagem').textContent = 'Esta operação já foi processada e a atividade foi excluída. Nenhum registro ou XP adicional foi criado.';
        if (dados.situacao === 'agenda_ja_concluida') el('timerMensagem').textContent = 'Este treino já foi concluído. A atividade não está mais disponível; nenhum novo registro foi criado.';
        const lista = el('timerConquistas'); lista.replaceChildren();
        (dados.novas_conquistas || []).forEach(conquista => {
            const item = document.createElement('p');
            item.className = 'timer-conquista';
            item.textContent = '🏆 Conquista desbloqueada: ' + conquista.nome + ' — ' + conquista.descricao;
            lista.appendChild(item);
        });
        if(dados.conquistas_atualizadas === false && !dados.duplicado) {
            const aviso=document.createElement('p');
            aviso.textContent='Atividade e XP básico salvos. Confira conquistas pendentes na página Conquistas.';
            lista.appendChild(aviso);
        }
        estado('timerConcluido'); el('timerConcluido').focus();
    }
    function atualizarDistancia() {
        const campo=el('timerDistancia');campo.disabled=!['Corrida','Caminhada','Ciclismo','Natação'].includes(el('timerModalidade').value);
        campo.closest('[data-distancia]').hidden=campo.disabled;if(campo.disabled)campo.value='';
    }
    el('timerModalidade').addEventListener('change',atualizarDistancia);
    atualizarDistancia();
    function iniciarTreino() {
        if (!selecao || !selecao.value || el('timerFormulario').hidden) return;
        raiz.closest('details').open = true;
        treinoId = Number(selecao.value);
        chaveRegistro = crypto.randomUUID();
        tipo = selecao.selectedOptions[0].dataset.titulo; acumulado = 0; erro.hidden = true;
        el('timerModalidade').value = selecao.selectedOptions[0].dataset.modalidade || '';
        el('timerDistancia').value='';atualizarDistancia();el('timerTipoAtual').textContent = tipo; continuar(); el('timerBotaoPausar').focus();
    }
    if (selecao) {
        selecao.addEventListener('change', () => { el('timerBotaoIniciar').disabled = !selecao.value; });
        el('timerBotaoIniciar').addEventListener('click', iniciarTreino);
    }
    document.addEventListener('click', evento => {
            const botao = evento.target.closest('[data-iniciar-treino]');
            if (!botao) return;
            if (!selecao || el('timerFormulario').hidden) {
                raiz.scrollIntoView();
                return;
            }
            selecao.value = botao.dataset.iniciarTreino;
            el('timerBotaoIniciar').disabled = !selecao.value;
            iniciarTreino();
    });
    el('timerBotaoPausar').addEventListener('click', () => { inicio === null ? continuar() : pausar(); });
    el('timerBotaoConcluir').addEventListener('click', () => {
        pausar(); segundos = Math.floor(acumulado / 1000);
        if (segundos < 60) { avisar('Atividade muito curta: mínimo 60 segundos. Continue ou cancele.'); return; }
        if (segundos > 86400) { avisar('A sessão deve ter no máximo 24 horas. Cancele e registre a duração pela página de atividades.'); return; }
        erro.hidden = true; salvar.disabled = false;
        el('timerResumo').textContent = tipo + ' • ' + formatar(segundos) + ' • ' + Math.floor(segundos / 60) + ' min';
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
        try {sessionStorage.setItem(pendencia,JSON.stringify({chaveRegistro,treinoId,segundos,tipo,modalidade:el('timerModalidade').value,distancia:el('timerDistancia').value}));} catch (_) {}
        try {
            const resposta = await fetch(raiz.dataset.url, {
                method: 'POST', credentials: 'same-origin',
                headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': raiz.dataset.csrf },
                body: JSON.stringify({ chave_registro: chaveRegistro, id_agenda: treinoId, tipo_exercicio: el('timerModalidade').value, segundos_decorridos: segundos, distancia_km: el('timerDistancia').disabled ? null : el('timerDistancia').value })
            });
            const dados = resposta.headers.get('content-type')?.includes('application/json')
                ? await resposta.json().catch(() => ({erro: 'O servidor enviou uma resposta inválida. Confira se o treino foi salvo antes de confirmar novamente.'}))
                : {erro: 'Não foi possível confirmar a resposta. Confira sua sessão e tente novamente.'};
            if (!resposta.ok || !dados.registrado) {
                // Falhas de servidor podem ocorrer depois do INSERT: conferir antes de reenviar.
                el('timerConfirmacao').querySelectorAll('button').forEach(b => { b.disabled = false; });
                avisar(dados.erro || 'Não foi possível registrar. Atualize a página e confira sua sessão.');
                return;
            }
            // Celebra na página já desbloqueada para áudio, e relê os indicadores reais.
            mostrarSucesso(dados);
            try {
                const pagina = await fetch(window.location.href, {credentials:'same-origin'});
                if (!pagina.ok) throw new Error('resumo indisponível');
                const documento = new DOMParser().parseFromString(await pagina.text(), 'text/html');
                ['.jornada-resumo','.proximo-treino','.meta-dashboard','.metricas-grid','.atividades','#alertas'].forEach(seletor => {
                    const atual=document.querySelector(seletor), novo=documento.querySelector(seletor);
                    if(atual && novo) atual.replaceWith(novo);
                });
                const serie=documento.getElementById('dadosProgresso');
                const blocoGrafico=document.querySelector('.grafico');
                if(blocoGrafico) {
                    blocoGrafico.querySelectorAll(':scope > .mini__apoio:not(#graficoErro)').forEach(p=>p.remove());
                    documento.querySelectorAll('.grafico > .mini__apoio:not(#graficoErro)').forEach(p=>blocoGrafico.querySelector('.grafico-container').before(p.cloneNode(true)));
                    const tabela=blocoGrafico.querySelector('.grafico-tabela'), novaTabela=documento.querySelector('.grafico-tabela');
                    if(tabela && novaTabela)tabela.replaceWith(novaTabela);
                    if(serie)document.getElementById('dadosProgresso').textContent=serie.textContent;
                }
                if(serie && window.Chart) {
                    const grafico=Chart.getChart('graficoProgresso');
                    if(grafico) {const d=JSON.parse(serie.textContent);grafico.data.labels=d.labels;grafico.data.datasets[0].data=d.minutos;grafico.update();}
                }
                const sino=document.querySelector('.sino'), novoSino=documento.querySelector('.sino');
                if(sino && novoSino) sino.replaceWith(novoSino);
                const novaSelecao=documento.getElementById('timerAtividade');
                if(selecao && novaSelecao)selecao.replaceChildren(...novaSelecao.childNodes);
                else {const opcao=selecao?.querySelector('option[value="'+treinoId+'"]');if(opcao)opcao.remove();}
                if(selecao) {selecao.value='';el('timerBotaoIniciar').disabled=true;}
            } catch (_) {
                avisar('Atividade salva. Não foi possível atualizar o resumo; recarregue a página para consultar os indicadores.');
            }
        } catch (_) {
            el('timerConfirmacao').querySelectorAll('button').forEach(b => { b.disabled = false; });
            avisar('Conexão interrompida. Tente confirmar novamente: a mesma chave impede duplicação.');
        } finally {
            enviando = false; salvar.textContent = 'Confirmar e salvar';
        }
    });
    try {
        const salvo=JSON.parse(sessionStorage.getItem(pendencia));
        if(salvo && typeof salvo.chaveRegistro==='string' && Number.isInteger(salvo.segundos)) {
            raiz.closest('details').open = true;
            chaveRegistro=salvo.chaveRegistro;treinoId=salvo.treinoId;segundos=salvo.segundos;tipo=salvo.tipo;
            acumulado=segundos*1000;
            el('timerModalidade').value=salvo.modalidade;el('timerDistancia').value=salvo.distancia || '';atualizarDistancia();
            el('timerResumo').textContent=tipo+' • '+formatar(segundos);
            estado('timerConfirmacao');
            erro.textContent='Há uma confirmação pendente. Tente confirmar novamente para conferir se o treino foi salvo.';
            erro.hidden=false;
        }
    } catch (_) {}
    const iniciarId = new URLSearchParams(window.location.search).get('iniciar');
    if (iniciarId && selecao) {
        selecao.value = iniciarId;
        el('timerBotaoIniciar').disabled = !selecao.value;
        iniciarTreino();
        history.replaceState(null, '', window.location.pathname + '#cronometro');
    }
    try {
        const feedback = sessionStorage.getItem(chave);
        sessionStorage.removeItem(chave);
        if (feedback) mostrarSucesso(JSON.parse(feedback));
    } catch (_) { /* A atividade permanece salva mesmo sem armazenamento local. */ }
})();
