> Diagnóstico real e checklist atualizado: [ESTABILIZACAO_INTEGRACAO.md](ESTABILIZACAO_INTEGRACAO.md).

# Checklist — finalização Lifes On

Situação em 08/10/2026. `[x]` significa validado localmente; a persistência remota
continua bloqueada por migrações pendentes. Relatório: [FINALIZACAO_PREMIUM.md](FINALIZACAO_PREMIUM.md).

## Antes da apresentação real

- [ ] Revisar diagnóstico `migrations/diagnostico_finalizacao.sql` (somente leitura).
- [ ] Revisar [AUDITORIA_XP.md](AUDITORIA_XP.md), configurar chave service_role apenas no servidor e ativar modo estrito.
- [ ] Em manutenção, autorizar ACLs e aplicar `seguranca_backend.sql`, `semanas_8_9.sql`, depois `finalizacao_premium.sql`.
- [ ] Validar negação de acesso anon/authenticated, ausência de escrita direta no livro e retries concorrentes reais com conta de teste autorizada.
- [ ] Conferir constraints, triggers, índices, permissões e RLS sem ampliá-los automaticamente.
- [ ] Rodar `python -m scripts.verificar_banco --detalhado`; todas as colunas devem estar acessíveis.
- [ ] Autorizar conta de teste e validar criação, recarga e persistência reais.
- [ ] Completar os cenários abaixo no Supabase, incluindo duas contas e duas abas.
- [ ] Adicionar Yoga e Ciclismo; as outras cinco artes estão integradas.
- [ ] Ouvir os sons no equipamento da apresentação e conferir volume.

## Cenários locais verificados

- [x] Cadastro/login, sessão, CSRF, isolamento nas rotas Flask.
- [x] Agenda: criar/editar/excluir, modalidade opcional e treino mais próximo.
- [x] Iniciar pela Agenda e Dashboard; pausar, retomar, finalizar e confirmar.
- [x] Treino curto não salva; confirmação grava uma única sessão.
- [x] Duplo clique/retry e resposta perdida não duplicam atividade/XP.
- [x] Recarregar após falha mantém UUID e confirmação pendente na mesma aba.
- [x] 503 exibe erro amigável sem SQL; nenhum prêmio antes do sucesso.
- [x] Atividade, XP básico e realização da Agenda fazem rollback juntos no PostgreSQL local.
- [x] Manual sem frequência, data de realização, rejeição de futuro e Artes Marciais.
- [x] Edição mantém frequência legada; histórico identifica registros antigos.
- [x] Progresso, gráficos/tabelas e sequência usam sessões e datas reais.
- [x] Meta concluída uma vez; reabrir/reconcluir não duplica recompensa.
- [x] Níveis derivados do livro; exclusão de atividade estorna 20 XP uma única vez.
- [x] Conquistas históricas permanecem; recuperação explícita é idempotente.
- [x] Nenhum XP por visitar páginas ou agendar treino.
- [x] 14 critérios de conquistas, símbolos, raridade, progresso e data.
- [x] Alertas individuais/coletivos, contador e estado lido persistidos no banco simulado.
- [x] Dicas: busca, filtro, detalhe, vazio, fontes e erro de conexão.
- [x] Imagens WebP, transparência, fallback por ausência/falha e PNGs preservados.
- [x] Sidebar na ordem solicitada; áudio no cabeçalho.
- [x] Controle/volume persistidos, síntese original, fila de recompensas e movimento reduzido.
- [x] 11 páginas/formulários em 1440, 1024, 768, 390 e 320 px sem rolagem horizontal.
- [x] Dashboard, formulário e conquistas inspecionados em capturas desktop/mobile.

## Evidências reproduzíveis

- 64 testes Python com banco simulado: `python -m unittest -q`.
- Chrome: `tests.browser_smoke`, `tests.browser_semanas_8_9`, `tests.browser_finalizacao`.
- PostgreSQL WASM local: `node tests/sql_semanas_8_9.cjs` e `node tests/sql_seguranca.cjs` (PGLITE_MODULE configurado).
- Capturas: `artifacts/validacao/` (ignoradas pelo Git, dados de teste).
- Remoto: somente SELECT limit=0, com colunas/livro ainda indisponíveis.

Não marcar a apresentação como pronta no Supabase antes de validar salvamento e XP
no ambiente real. Testes Flask não certificam isolamento pela API direta/RLS.
