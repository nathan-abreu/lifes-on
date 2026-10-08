# Lifes On — entrega das Semanas 8 e 9

Implementação local em 08/10/2026. Flask, Supabase e os módulos anteriores foram
preservados. A liberação no banco remoto **ainda depende da autorização e aplicação
da migração**. Não apresentar a persistência remota como validada.

## Semana 8 — Dicas (Pablo e Vinícius)

`GET /dicas` lê o catálogo do Supabase com paginação, pesquisa por título/conteúdo
sem distinguir maiúsculas e filtro por categoria. `GET /dicas/<id>` mostra a leitura
completa e a fonte. Cards, detalhes, estado vazio, erro de conexão, navegação e telas
menores usam a identidade comum. HTML é escapado; fontes externas só podem apontar
para HTTPS nos domínios editoriais da OMS/CDC.

A migração publica cinco dicas de atividade física, recuperação, sono, hidratação e
hábitos saudáveis, preserva o catálogo anterior e corrige a afirmação absoluta sobre
aquecimento do seed antigo. Conteúdo educativo geral, sem prescrição individual.
Não há IA ou recomendações personalizadas nesta versão.

Fontes conferidas em 08/10/2026:
- [OMS — atividade física](https://www.who.int/news-room/fact-sheets/detail/physical-activity)
- [CDC — sono](https://www.cdc.gov/sleep/about/)
- [CDC — água](https://www.cdc.gov/healthy-weight-growth/water-healthy-drinks/)
- [CDC — atividade física](https://www.cdc.gov/physical-activity-basics/about/index.html)

## Semana 9 — XP (Nathan e Pablo)

| Evento efetivamente salvo | XP | Identidade da recompensa |
| --- | ---: | --- |
| Nova atividade válida | 20 | atividade:UUID do registro |
| Meta passa de menos de 100 para 100% | 50 | meta:ID |
| Nova associação de conquista | 30 | conquista:ID |
| Primeira sequência histórica de sete dias | 50 | sequencia:primeiros-7 |

Nível = `1 + XP_total // 100`. Progresso = `XP_total % 100`. Faltam
`100 - progresso` pontos. Exemplos: 0 XP → nível 1; 99 → nível 1, 99%;
100 → nível 2, 0%; 250 → nível 3, 50%.

O total é a soma do livro `recompensas_xp`. Nunca recebe XP do navegador. Os triggers
PostgreSQL concedem os valores fixos na transação do evento. O campo legado
`conquistas.pontos` é preservado e não é usado como segunda fonte de pontuação.
Índice único `(id_usuario, chave_evento)` protege cada recompensa; triggers no livro
impedem inserção arbitrária, alteração, exclusão e TRUNCATE diretos.

Editar/excluir atividade não concede nem remove o XP já conquistado. Reenviar o
mesmo UUID após exclusão continua sem prêmio ou registro novo. Meta reaberta e
concluída novamente mantém seu único prêmio. Conquista mantém a obtenção persistida.
Não há XP por agenda, visitas, seleção de opções ou cliques. Metas textuais continuam
com conclusão declarada pelo usuário; não é possível verificar fisicamente o treino
ou a veracidade da declaração usando os dados deste aplicativo.

Não há backfill de XP de atividades/metas/conquistas já persistidas. Conquistas
pendentes que atendem condições reais são reconciliadas pelo fluxo existente; uma
associação realmente nova após a migração gera 30 XP, inclusive quando recuperada
em uma consulta posterior. Abrir a página sem um evento pendente não gera prêmio.

## Como os dados percorrem os módulos

1. Agenda cria planejamento em `agenda`; não altera métricas ou XP.
2. Cronômetro local conta tempo ativo com `performance.now()`, sem contar pausas.
3. Ao confirmar, Flask valida sessão, CSRF, modalidade, duração, UUID e dono da Agenda.
4. `registrar_atividade` grava na mesma tabela `atividades` do registro manual.
5. O banco serializa por usuário, verifica duplicidade, grava +20 XP e marca
   `agenda.realizado_em`, tudo na mesma transação. Agenda preserva o histórico.
6. O backend calcula conquistas a partir de registros reais e persiste em
   `usuario_conquista` usando conflito único. Inserção gera +30 XP na sua transação.
7. Dashboard relê minutos, atividades, sequência, metas, conquistas, alertas e XP.
   Após o cronômetro, busca o HTML atualizado do backend e substitui os indicadores;
   atualiza o gráfico com a série retornada, sem inventar incrementos.
8. Progresso usa o mesmo `calcular_progresso`: dias locais de Brasília, semanas de
   segunda a domingo, mês recortado pelo calendário e minutos por modalidade.
   Frequência semanal não multiplica sessões. Datas futuras não entram nos gráficos.

Uma Agenda pode ser concluída apenas uma vez; `realizado_em` e o índice do vínculo
protegem inclusive requisições com UUIDs distintos. Exclusão da Agenda mantém a
atividade (`ON DELETE SET NULL`). Exclusão da atividade não reabre o treino.
Treinos realizados saem do próximo treino e do seletor do cronômetro e recebem selo
na Agenda. Metas não são incrementadas por atividades sem relação verificável.

Alertas preservam `nao_lido`, `lido`, `chave_evento`, contador, leitura individual e
leitura coletiva. Histórico e deduplicação continuam em `alertas`.

## Falhas parciais e repetição

Atividade, XP básico e marcação da Agenda são atômicos: falha na recompensa reverte
os três. Conquistas são uma etapa separada; falha informa que a atividade foi salva
e a sincronização posterior recupera obtenções pendentes sem duplicá-las.

O formulário manual mantém valores e UUID ao receber falha de conexão/estrutura.
O cronômetro mantém o UUID ao repetir uma confirmação cuja resposta foi perdida.
A interface bloqueia duplo clique; a proteção definitiva fica no banco. Feedback
compara recompensas reais e filtra os eventos da operação para não celebrar o XP de
outra aba. Uma resposta perdida pode impedir a celebração, mas não a persistência.
Se a leitura de XP falhar após salvar, não se inventa valor e o histórico continua
consultável depois. Se o resumo não puder ser atualizado, pede recarregar a página.

## Sons e animações

`static/js/interacoes.js` centraliza tons originais sintetizados com Web Audio:
clique, navegação, seleção, confirmação, treino, XP, conquista, nível e erro suave.
Sem arquivos ou personagens de terceiros. Notas curtas, ganho máximo baixo,
intervalo mínimo entre cliques e agendamento sequencial impedem sobreposição.

Áudio vem desligado. Configurações permitem ligar/desligar, volume e exemplo;
`localStorage` salva por usuário neste navegador. Falha do armazenamento não impede
o uso. AudioContext só é retomado após gesto de ponteiro/teclado. Após redirecionar,
o navegador pode exigir novo gesto para tocar; a notificação textual sempre aparece.
Preferências não são sincronizadas entre aparelhos. Uma avaliação subjetiva do timbre
e do volume nos alto-falantes da apresentação ainda deve ser feita pelo usuário.

XP, conquistas e níveis entram numa fila de notificações acessível, sem modais.
Valores são confirmados pelo backend. Barra e nível são relidos do banco. Botões
respondem à pressão, opções mostram seleção, envio mostra salvamento e cards têm
hover discreto. `prefers-reduced-motion` desativa movimentos e animações de gráficos;
todas as tarefas podem ser realizadas sem áudio. Há foco visível e link para pular
para o conteúdo.

## Banco e instalação

Tabelas: `usuarios`, `atividades`, `agenda`, `metas`, `conquistas`,
`usuario_conquista`, `alertas`, `dicas`, `recompensas_xp`.

Banco existente: revisar e autorizar `migrations/semanas_8_9.sql`; requer as migrações
anteriores. Banco novo: `schema.sql` contém também essa evolução. **Não execute
schema.sql para atualizar um banco existente.** A migração é transacional/repetível,
adiciona colunas, índices, livro, funções, triggers e conteúdo editorial. Não apaga
registros, muda chaves, GRANT/REVOKE, policies ou RLS.

O papel usado pelo Flask precisa ler `recompensas_xp` e continuar gravando as tabelas
existentes. Os triggers internos SECURITY DEFINER usam search_path fixo; nenhuma
função RPC recebe usuário/XP informado pelo cliente. Privilégios/defaults/RLS do
ambiente real precisam ser conferidos: a migração preserva a configuração vigente.
O login existente usa sessões Flask, e não Supabase Auth. Isolamento foi testado nas
rotas Flask; exposição direta pela API do Supabase depende das policies existentes
e **não foi certificada**. Não publicar como produção multiusuário sem essa revisão.
Nenhuma política ou credencial foi modificada nesta entrega.

PowerShell:
```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
# Configurar .env local com SUPABASE_URL, SUPABASE_KEY e FLASK_SECRET_KEY.
# Não incluir .env em commits. Preservar a chave autorizada do projeto.
.\.venv\Scripts\python.exe -m flask --app app run
```
Use o servidor local para a apresentação. `app.py` mantém o modo de desenvolvimento
anterior; não é configuração de produção. Não há implantação automática nesta tarefa.

## Verificações e evidências

```powershell
.\.venv\Scripts\python.exe -m unittest -q
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
# Chrome instalado:
.\.venv\Scripts\python.exe -m tests.browser_smoke
.\.venv\Scripts\python.exe -m tests.browser_semanas_8_9
# Diagnóstico remoto exclusivamente SELECT limit=0, sem ler registros:
.\.venv\Scripts\python.exe -m scripts.verificar_banco
```

Teste SQL local: Node e `@electric-sql/pglite` (PostgreSQL WASM). Instalar fora do
projeto e informar o caminho do módulo:
```powershell
npm install --prefix "$env:TEMP\lifes-on-sql-validation" @electric-sql/pglite --no-audit --no-fund
$env:PGLITE_MODULE = "$env:TEMP\lifes-on-sql-validation\node_modules\@electric-sql\pglite"
node tests/sql_semanas_8_9.cjs
```
Se Node não reconhecer certificados corporativos, usar `NODE_OPTIONS=--use-system-ca`
com uma versão que o suporte; nunca desativar validação TLS.

Resultados locais: 54 testes Python, Chrome de regressão e Chrome semanas 8/9.
SQL real local verifica migração repetida, recompensas únicas, metas reabertas,
conquista repetida, sequência, edição/exclusão, vínculo de usuário, livro protegido
e rollback após falha do trigger. Esse PostgreSQL local não reproduz policies do
Supabase nem certifica concorrência entre conexões remotas independentes.
Chrome usa exclusivamente banco em memória; nunca dados fictícios no aplicativo real.
Capturas novas em `artifacts/validacao/` (ignoradas pelo Git).

Remoto em 08/10/2026: somente SELECT limit=0. Alertas, metas, conquistas e associação
acessíveis. Atividades, Agenda e Dicas ainda sem as novas colunas (42703), livro de
XP ausente (PGRST205). Não houve DDL, INSERT, UPDATE ou DELETE remotos. Nenhuma
persistência nova, privilégio de escrita ou RLS foi testado no Supabase.

## Limitações e pendências

- Aplicar a migração autorizada e validar escrita/persistência usando conta de teste
  autorizada; depois executar o checklist da professora no ambiente real.
- Conferir permissões/RLS sem alterá-las silenciosamente. A chave atual e a política
  de login herdada não foram substituídas. Acesso direto à API exige auditoria própria.
- Conquistas podem precisar de recuperação após falha; XP básico não se perde.
- O cronômetro não sobrevive a fechamento/reload durante treino; registro manual
  permite registrar o que foi feito fora do aplicativo. Isto preserva o fluxo anterior.
- Sem notificações push, IA, ranking, sincronização de preferências entre aparelhos
  ou verificação física de atividades. Sequência recebe bônus uma vez, sem exigir
  exercício diário ou ignorar necessidade de descanso.
- Gráficos, fonte e ícones usam CDNs; há tabelas/números alternativos se o gráfico
  falhar. Não foi realizado teste de carga, auditoria completa de autenticação,
  navegador Safari real ou concorrência remota. Mobile foi Chrome com viewport.

## Arquivos da entrega

Backend: `app.py`, `progresso.py`, novo `recompensas.py`.
Banco: `schema.sql`, nova `migrations/semanas_8_9.sql`, `scripts/verificar_banco.py`.
Interface: `base_dashboard.html`, `dashboard.html`, `agenda.html`,
`atividade_form.html`, novos `_xp.html`, `dicas.html`, `dica_detalhe.html`,
`pontuacao.html`, `configuracoes.html`; `style.css`, `cronometro.js`, `progresso.js`,
novo `interacoes.js`.
Validação: testes de regressão atualizados, novos `test_semanas_8_9.py`,
`browser_semanas_8_9.py`, `sql_semanas_8_9.cjs`, `requirements-dev.txt`.
Documentação: este arquivo, `CHECKLIST_APRESENTACAO.md`, `README.md`, `.gitignore`.
