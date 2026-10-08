# Checklist final — apresentação do Lifes On

Validado localmente em 08/10/2026. `[x]` significa verificado localmente;
`[ ]` significa pendente no Supabase real ou na apresentação.

## Preparação do ambiente real

- [ ] Autorizar/revisar e aplicar `migrations/semanas_8_9.sql`.
- [ ] Executar diagnóstico de estrutura e conferir permissões/RLS vigentes.
- [ ] Autorizar conta/dados de teste para validar gravações remotas sem afetar usuários.
- [ ] Conferir `.env` apenas no servidor; nunca mostrar chaves na apresentação.
- [ ] Reiniciar Flask e repetir os fluxos abaixo no banco real.

## Roteiro para a professora

- [x] Usuário sem atividades: métricas zero, sem dados inventados, nível 1 e estados vazios.
- [x] Criar treino: aparece na Agenda e Dashboard sem atividade ou XP.
- [x] Cronômetro: iniciar, pausar, continuar, finalizar e confirmar modalidade.
- [x] Cancelar sessão não registra atividade; sessão curta pede continuar.
- [x] Confirmar atualiza atividade, minutos, gráfico, sequência e XP.
- [x] Agenda mantém treino como realizado e remove-o do próximo treino/cronômetro.
- [x] Registro manual usa os mesmos dados e recompensas; frequência não multiplica minutos.
- [x] Dashboard e Progresso mostram minutos coerentes; gráficos mensal/modalidades usam registros reais.
- [x] Criar/editar/excluir meta; conclusão única e meta reaberta não repete XP.
- [x] Ganho exato de XP, conquista persistida, nível 2 e barra coerente.
- [x] Conquistas permanecem após recarregar ou excluir atividade.
- [x] Alertas: leitura individual/coletiva e contador persistidos; sem duplicação.
- [x] Dicas: categorias, busca, filtros, detalhe, fontes e nenhum resultado.
- [x] Duplo clique e retry com mesma chave não duplicam registros.
- [x] Resposta perdida após salvamento: retry do cronômetro reconhece treino já concluído.
- [x] Falha na recompensa SQL reverte atividade e conclusão da Agenda juntas.
- [x] Falha de conexão mostra mensagem; ausência da migração é informada.
- [x] Acesso de outro usuário às rotas de registros é rejeitado ou não encontra registros.
- [x] CSRF obrigatório; XP e usuário enviados pelo frontend não determinam a recompensa/dono.
- [x] Sons desligados/ligados, volume salvo, síntese no Chrome e uso sem áudio.
- [x] Movimento reduzido respeitado em CSS e gráficos.
- [x] Viewports de 390 e 320 px sem overflow horizontal nos fluxos verificados.
- [x] Capturas de Dashboard e Dicas inspecionadas em desktop e celular.

## Confirmação ainda necessária

- [ ] Repetir registro manual, cronômetro, meta e conquista no Supabase com conta autorizada.
- [ ] Recarregar e conferir persistência remota de XP, realização da Agenda e alertas.
- [ ] Testar duas abas/requisições concorrentes reais e isolamento com duas contas reais.
- [ ] Auditar acesso direto pela API Supabase; teste das rotas Flask não certifica RLS.
- [ ] Conferir som/volume nos equipamentos da sala e navegador utilizado na apresentação.
- [ ] Fazer revisão humana final do conteúdo educativo e dos textos.

## Evidências

- `python -m unittest -q`: 54 testes locais.
- `python -m tests.browser_smoke`: regressão no Chrome com banco simulado.
- `python -m tests.browser_semanas_8_9`: novos fluxos no Chrome com banco simulado.
- `node tests/sql_semanas_8_9.cjs`: PostgreSQL WASM real local, triggers e rollback.
- Capturas em `artifacts/validacao/`.
- Diagnóstico remoto: exclusivamente SELECT limit=0; novas colunas/livro ainda ausentes.

Não marcar a apresentação como validada no banco real antes de completar os itens pendentes.
