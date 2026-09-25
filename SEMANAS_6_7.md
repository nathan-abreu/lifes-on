# Lifes On — final da Semana 7

## Alertas com leitura persistida

A melhoria posterior de leitura reutiliza a tabela alertas real. Veja
[ALERTAS_LEITURA.md](ALERTAS_LEITURA.md) para regras, testes e limitações.
É necessário aplicar manualmente `migrations/alertas_leitura.sql`, que acrescenta
chave_evento e índice único sem alterar permissões. A migração das semanas 6/7
anteriormente aplicada não inclui essa atualização. O histórico guarda lido/não
lido; o sino conta somente não lidos. Nenhuma mudança no cronômetro ou regras dos
outros módulos foi feita nesta melhoria.

## Última melhoria: Dashboard e cronômetro

O usuário confirmou que a migração foi aplicada no Supabase real e que o treino
aparece na Agenda e no Dashboard. As pendências da auditoria abaixo são o registro
histórico anterior a essa confirmação. Esta melhoria não altera SQL, tabelas,
permissões, chaves ou rotas da Agenda.

- Dashboard organizado conforme o wireframe da página 19: métricas no topo,
  resumo semanal com dados reais, próximo treino/meta/conquistas à direita,
  cronômetro compacto e atividades recentes com Hoje/Ontem/data.
- O cronômetro lista somente treinos da Agenda do usuário, de hoje em diante,
  ordenados por horário (inclui horários de hoje já passados). Exibe título,
  Hoje/Amanhã/data e horário. O card Próximo treino inicia diretamente.
- Sem treinos, oferece Agendar treino e Registrar atividade realizada. O registro
  manual permanece independente. O cronômetro conta para cima em HH:MM:SS,
  permite pausa, continuação, cancelamento e confirmação antes de salvar.
- A Agenda não possui modalidade; a confirmação pede o tipo de exercício realizado
  entre os tipos existentes, sem interpretar o título livre. O backend consulta
  id_agenda com id_usuario da sessão antes de gravar e rejeita IDs alheios/excluídos.
- Planejamento não entra nas métricas. Só a confirmação salva na mesma tabela
  atividades. Não exclui nem marca a Agenda, que não tem campo de conclusão.
  Não cria vínculo persistente novo ou altera o banco. Os botões bloqueiam duplo
  clique na mesma realização; iniciar outra sessão continua permitido. Não há
  garantia de deduplicação entre abas/requisições independentes sem chave no banco.
- Usa performance.now() para medir tempo decorrido, sem somar pausas ou depender
  da quantidade de execuções de setInterval. Fechar/recarregar abandona o tempo.
- POST /atividades/concluir_timer continua gravando em atividades, com usuário
  da sessão, CSRF, frequência 1 e data UTC. Aceita segundos inteiros de 30 a 86400;
  minutos são arredondados para o inteiro mais próximo, meio minuto para cima.
- Após salvar, o Dashboard recarrega os dados do backend. Progresso lê a mesma
  atividade. Metas textuais mantêm a atualização manual existente.
- A sincronização existente de conquistas retorna os nomes efetivamente inseridos
  no upsert. O feedback usa esses registros, sem anúncio de conquista antiga ou
  botão de desbloqueio. A confirmação sobrevive a um reload usando sessionStorage
  por usuário, removido na leitura; se indisponível, aparece antes do reload.
- Envio bloqueia botões para evitar cliques repetidos. Falha de rede/servidor com
  resultado incerto pede conferir atividades antes de reenviar; não faz retry
  automático. Não foi criada infraestrutura de idempotência no banco.
- Testes locais: 37 testes automatizados; navegador Chrome com banco em memória
  cobre pausa, continuação, confirmação, cancelamento, feedback, gráficos,
  isolamento, Agenda/Metas/Alertas e telas menores. Não houve gravação remota
  nesta melhoria. Os dados de teste ficam exclusivamente nos testes.
- Nenhum sistema de XP, pontuação, níveis, ranking, dicas ou recurso futuro foi
  implementado. Não há migração ou configuração manual nova.


## Referência principal

Foi lido o PDF **Lifes On - Documentação Geral.pdf**, de 28 páginas, fornecido em
D:/Usuario/Documents. Foram inspecionados também os diagramas e wireframes:
RF 4/5/7/9/10 nas páginas 9–11, regra de agendamento na página 13, modelo de dados
nas páginas 16–17, Dashboard nas páginas 19–20 e Progresso nas páginas 23–24.

O PDF descreve o produto completo. Esta entrega segue o recorte solicitado:
cadastro/login, dashboard, atividades, metas, progresso, alertas, agenda e conquistas.
Flask e o login existente foram preservados, mesmo que o capítulo de tecnologias
do PDF mencione Node/Express. Não houve recriação do projeto.

## Diferenças encontradas e correções

| Primeira implementação | Segunda revisão |
| --- | --- |
| Consulta a treinos_agendados, ausente no banco | Reutiliza agenda, prevista no PDF e confirmada no Supabase |
| Data e hora em colunas separadas | Usa agenda.horario (timestamp local) e lembrete como descrição |
| Título sem correspondente na tabela real | Migração acrescenta somente agenda.titulo |
| SDK Python falhava na validação TLS | Certificados confiáveis do sistema, mantendo verificação TLS |
| Treinos passados aceitos | Backend rejeita data/horário passado na criação e edição |
| Conquistas calculadas, sem histórico | Obtenções persistidas em usuario_conquista |
| Tabelas de conquistas consideradas inexistentes | Reutiliza conquistas e usuario_conquista reais |
| Somente gráfico semanal | Gráfico mensal por semanas e minutos por modalidade |
| XP adicionado ao Dashboard | Novos cálculos e exibições de XP removidos |
| Card mostrava apenas média das metas | Mostra meta pendente de menor prazo, percentual e prazo |
| Sem obtenção recente no Dashboard | Quantidade persistida e conquista recente com data |
| Agenda dependia de outros módulos | CRUD e listagem consultam somente agenda |
| Falha de gravação genérica | Valores preservados e mensagem de estrutura/acesso/conexão |

A remoção local do elemento timerCurta continua preservada. O timer, as rotas e os
formulários existentes foram mantidos. Os antigos atalhos de Dicas, Pontuação e
Configurações foram preservados em comentário de template, fora do menu renderizado.

## Por que a Agenda não funcionava — diagnóstico real de 24/09/2026

Nesta segunda etapa voltou a ser possível consultar o Supabase:

- treinos_agendados: **404 / PGRST205**, tabela não encontrada.
- agenda: existe com id_agenda, id_usuario, horario e lembrete.
- horario: timestamp sem fuso; não há coluna separada data/data_hora.
- agenda.titulo: ausente, **42703**.
- conquistas e usuario_conquista: existentes com os campos previstos no PDF.
- data_obtencao: tipo date.
- Catálogo existente: Primeiro passo, Semana cheia e Meta batida.
- A configuração atual utiliza chave com papel anon.

O endpoint inicial de metadados retornou 401; consultas diretas às tabelas funcionaram.
O SDK Python apresentou CERTIFICATE_VERIFY_FAILED. A mesma consulta passou com
ssl.create_default_context(), que inclui os certificados confiáveis do sistema.
**Não foi desabilitada a validação de certificado ou hostname.**

As causas confirmadas foram **tabela incorreta no código** e **confiança TLS no
cliente Python**. Depois dessas correções, resta atualizar a coluna de título.
Não era apenas um problema de formulário ou CSRF.

| Origem | Destino no banco |
| --- | --- |
| Formulário titulo | agenda.titulo |
| Formulário descricao | agenda.lembrete |
| Formulário data + horario | agenda.horario, data/hora local de Brasília |
| Usuário da sessão | agenda.id_usuario |
| ID usado na URL | agenda.id_agenda |

Após o ajuste TLS, o cliente real confirmou as colunas de atividades, metas,
conquistas e associação. As rotas /agenda e /agenda/novo, em GET com sessão técnica
sem usuário real, retornaram 503 com mensagem de migração pendente.

**Não executei DDL, INSERT, UPDATE ou DELETE no banco remoto.** Não há validação
remota de persistência ou das permissões finais. A migração revisada não foi aplicada.

## SQL ainda necessário no Supabase

1. **Não execute ainda a migração:** faltam conferir permissões de escrita,
   policies, defaults e constraints reais. A versão anterior com REVOKE quebraria
   a chave anon atualmente utilizada; esse bloco foi removido.
2. No projeto apontado por SUPABASE_URL, abra **SQL Editor → New query** e execute
   [migrations/auditoria_somente_leitura.sql](migrations/auditoria_somente_leitura.sql).
   O diagnóstico não altera dados. Confira cada resultado; se o editor mostrar
   somente o último, execute as consultas separadamente.
3. Confira permissões e policies para CRUD de agenda e SELECT/INSERT de
   usuario_conquista, defaults dos IDs, constraints e ausência de pares duplicados.
   Privilégios de tabela sozinhos não garantem acesso quando há RLS.
4. Depois dessa conferência, a atualização está integralmente em
   [migrations/semanas_6_7.sql](migrations/semanas_6_7.sql). Não use a cópia antiga
   com REVOKE. Preserve a chave atual; não há exigência de service_role.
5. Após aplicar a atualização, reinicie o Flask e teste gravação pela aplicação.

O script usa transação e IF NOT EXISTS. No banco real consultado, ele:

- Reutiliza agenda, conquistas e usuario_conquista.
- Adiciona agenda.titulo, preservando horario e lembrete.
- Acrescenta Em Movimento, Foco Total e Veterano ao catálogo.
- Mantém nomes, descrições e pontos dos registros já existentes.
- Cria índice único em (id_usuario, id_conquista) e índices de consulta.
- Preserva permissões, RLS, policies e sequências existentes.
- Não cria tabelas: as seis tabelas necessárias existem no banco real.
- Solicita atualização do cache de schema do PostgREST.

Não cria treinos_agendados, não apaga tabelas e não destrói registros. O título
padrão “Treino agendado” apenas identifica eventuais registros antigos sem título;
não cria dados fictícios. Pontos das novas conquistas são zero, sem lógica de XP.

Se houver duplicações antigas em usuario_conquista em outro ambiente, a criação
do índice único abortará a transação para revisão, sem apagar essas duplicações.
Se a primeira migração tiver criado treinos_agendados em outro ambiente, essa tabela
não será apagada/importada automaticamente; revise seus dados antes de usar esse
ambiente. No projeto remoto consultado, ela foi confirmada ausente.

[Schema completo](schema.sql) contém o mesmo bloco da migração para banco novo.
Atividades e metas continuam declaradas porque faltavam no schema original, embora
já fossem usadas pelo aplicativo. Tabelas existentes não são recriadas.

## Credenciais e auditoria final

O código anterior usava SUPABASE_KEY. A configuração atual contém uma chave de
papel anon, sem SUPABASE_SERVICE_ROLE_KEY. app.py e o diagnóstico priorizam a
variável opcional SUPABASE_SERVICE_ROLE_KEY quando preenchida; caso contrário,
usam SUPABASE_KEY. banco.py apenas recebe a chave e cria o cliente com TLS validado.
Não alterei .env nem a chave real.

**Service Role não é necessária para esta entrega.** A versão anterior da migração
passava a exigi-la ao revogar anon, authenticated e PUBLIC. Foram removidos todos
os comandos de GRANT, REVOKE e ENABLE ROW LEVEL SECURITY e os grants em sequências.
Preservar as permissões evita essa regressão de acesso, mas não garante que as
permissões de escrita dos módulos novos já estejam corretas.

O login usa sessão Flask, não Supabase Auth. Consultas anon compartilham a mesma
identidade no banco. Os filtros do Flask protegem as rotas, mas não garantem
isolamento por usuário no acesso direto à API do Supabase. Preservar a arquitetura
não corrige essa limitação anterior. Uma revisão de autenticação/RLS deve ser
tratada separadamente; não foram criadas policies nem ampliados privilégios.

Não há cliente Supabase no JavaScript ou chave enviada aos templates. .env está
ignorado pelo Git e não é rastreado no estado atual. A variável de servidor
continua opcional, sem exigência de trocar a chave existente.

A auditoria remota somente de leitura confirmou bigint nas dez colunas de IDs
(PK/FK) das seis tabelas por validação de tipos no PostgREST. Isso não confirma as
definições completas de constraints, defaults, índices ou policies. agenda.titulo
permanece ausente. Não houve escrita remota. O SQL de auditoria consulta esses
metadados no SQL Editor e conta duplicações sem expor registros pessoais.

A migração é repetível em execução sequencial, desde que o schema corresponda ao
esperado: IF NOT EXISTS não corrige coluna/índice preexistente incompatível.
Duplicações na associação fazem a transação falhar sem apagar dados. O seed usa
WHERE NOT EXISTS por nome; não execute cópias da migração simultaneamente.

Todas as rotas internas exigem autenticação; os POSTs mantêm CSRF. O usuário não
define id_usuario pelo formulário. Edições/exclusões filtram também pelo dono.

## Conquistas e persistência

Os nomes já existentes foram mantidos. Primeiro passo, Semana cheia e Meta batida
equivalem, respectivamente, a Primeiros Passos, Consistência e Conquistador sugeridos:

| Nome | Condição automática |
| --- | --- |
| Primeiro passo | Uma atividade registrada |
| Em Movimento | Cinco atividades registradas |
| Foco Total | Dez atividades registradas |
| Veterano | Trinta atividades registradas |
| Semana cheia | Melhor sequência de sete dias consecutivos |
| Meta batida | Uma meta com progresso igual a 100% |

As regras estão centralizadas em progresso.py. A função sincronizar_conquistas()
no Flask faz a associação:

1. Após salvar atividade manual, timer, edição de atividade ou atualização de meta,
   consulta os dados reais do usuário e verifica os requisitos.
2. Insere somente novas obtenções, com id_usuario, id_conquista e data_obtencao.
3. Usa upsert com ignore_duplicates e conflito na chave composta, apoiado por índice
   único. Uma corrida entre requisições não substitui a primeira data.
4. Lê o histórico persistido para exibir estado e data no card e no Dashboard.

Visitas ao Dashboard, Progresso, Alertas e Conquistas também reconciliam registros
anteriores. Para dados antigos, salva-se a **data de detecção**: não se inventa a
data histórica exata em que o requisito foi cumprido.

Uma conquista obtida permanece após excluir atividades ou reduzir metas. A barra
permanece completa. Bloqueadas mostram progresso atual e aparência discreta.
Não há botão de desbloquear. Nomes sem regra desta etapa no catálogo não recebem
regras presumidas de funcionalidades futuras.

Se o registro principal for salvo e a associação falhar, a aplicação informa o
sucesso do registro e a pendência das conquistas. A próxima consulta tenta novamente
sem duplicar a atividade. Essas chamadas REST não são uma única transação.

O campo pontos existe somente por compatibilidade do modelo. Não é somado nem usado
para desbloquear conquistas, gerar XP, nível, ranking ou recompensas.

## Progresso, Agenda, Alertas e Dashboard

- **Progresso:** minutos/atividades do mês, sequência atual e recorde; linha semanal;
  barras de atividades por semana do mês; minutos de todo o histórico por modalidade.
  Os gráficos possuem tabelas acessíveis e mensagem quando a CDN não carrega.
- **Períodos:** semanas de segunda a domingo, recortadas pelos limites do mês.
  Um mês pode ter quatro a seis intervalos. Datas usam São Paulo/Brasília.
- **Atividades:** cada registro representa uma sessão realizada. Frequência declarada
  não multiplica totais. UTC sem offset legado continua interpretado como UTC.
  Registros futuros não contam como atividade realizada.
- **Metas:** 100% representa conclusão. Percentuais vêm da tela existente; objetivos
  em texto livre não são interpretados automaticamente.
- **Agenda:** CRUD próprio, ordem por data/hora, próximos sete dias destacados,
  anteriores separados e proibição de passado no backend, também na edição.
  Treinos anteriores podem ser excluídos ou remarcados. Agendamento não é atividade.
- **Alertas:** treinos futuros de hoje/amanhã têm prioridade; metas pendentes,
  vencidas ou a até três dias do prazo; inatividade a partir de três dias e convite
  ao primeiro registro. Falha da Agenda não aparece como “tudo em dia”.
- **Dashboard:** métricas, gráfico semanal, cinco atividades recentes, próximo treino,
  meta atual, quantidade de conquistas e obtenção recente. Até três alertas com
  acesso à lista completa. O timer recarrega o resumo após salvar.

Os alertas são internos e calculados ao visitar a página. Não foram implementados
push, e-mail, SMS ou tarefas em segundo plano.

## Rotas e configuração

As rotas da primeira etapa foram mantidas: /progresso, /alertas, /conquistas,
/agenda, /agenda/novo, /agenda/editar/<int:id_treino> e
/agenda/excluir/<int:id_treino>. O parâmetro id_treino identifica agenda.id_agenda.

Execute na raiz do repositório:

    .venv\Scripts\python.exe -m pip install -r requirements.txt
    .venv\Scripts\python.exe -m scripts.verificar_banco
    .venv\Scripts\python.exe app.py

O diagnóstico testa colunas com limit=0: não lê registros nem imprime chaves.
Após configuração/migração, todas as tabelas devem indicar colunas acessíveis.
Isso não substitui testar gravação. Esta revisão não adicionou dependências de
execução; tzdata foi acrescentado na primeira etapa.

## Testes e limitações

| Categoria | Resultado e alcance |
| --- | --- |
| Automatizados locais | 33 testes aprovados com banco em memória: regressão, vazios, sequência, mensal, isolamento, CSRF, CRUD, passado, persistência, datas e duplicação |
| Interface | Chrome desktop e 390 px: login, formulários, agenda, alertas, dois gráficos, conquistas, timer manual/automático e fallback de CDN |
| Estáticos | Compilação Python, sintaxe JavaScript, revisão do diff; SQL analisado pelo parser PostgreSQL e conferido contra schema.sql |
| Supabase real | SELECTs/estrutura e correção TLS confirmados; falta agenda.titulo; nenhuma gravação ou migração executada |

Concorrência foi simulada localmente; não foi testada em PostgreSQL real. As
permissões, RLS, defaults e índices reais precisam ser conferidos antes de
aplicar o SQL; a persistência deve ser testada depois pela aplicação. A aplicação normal não usa mocks.

Comandos:

    .venv\Scripts\python.exe -m unittest discover -v
    .venv\Scripts\python.exe -m compileall -q app.py banco.py progresso.py tests scripts
    node --check static/js/progresso.js

Verificação opcional de interface com Chrome instalado e banco em memória:

    .venv\Scripts\python.exe -m pip install playwright
    .venv\Scripts\python.exe -m tests.browser_smoke

## Como testar no Supabase após executar a migração

1. Rode o diagnóstico. Entre com uma conta própria; abra Agenda e salve um treino
   para amanhã com título e descrição.
2. No Table Editor, confira agenda: usuário correto, horario completo, titulo e
   lembrete. Confira também a Agenda, o próximo treino no Dashboard e o Alerta.
3. Edite título e horário. Confira a persistência e os três locais da interface.
4. Exclua. Confira a remoção na tabela, na Agenda, no Dashboard e nos Alertas.
5. Cadastre dois horários futuros em ordem invertida; confira a ordenação.
   Ontem e um horário passado hoje devem ser rejeitados.
6. Registre uma atividade e confira usuario_conquista imediatamente. Reabrir as
   telas não deve mudar quantidade/data. Excluir a atividade não remove a obtenção.
7. Atualize uma meta para 100%: Meta batida deve ser registrada. Use prazos próximos
   para conferir alertas. Verifique gráficos semanal/mensal e modalidades.
8. Entre numa segunda conta: dados e obtenções da primeira não aparecem. Abrir
   diretamente a edição de um treino alheio deve retornar 404.

## Arquivos desta revisão

Modificados sobre a primeira etapa:

- app.py, progresso.py, schema.sql, migrations/semanas_6_7.sql, SEMANAS_6_7.md.
- static/js/progresso.js e static/css/style.css.
- templates/dashboard.html, base_dashboard.html, _painel_progresso.html,
  _alertas.html, progresso.html, conquistas.html, agenda.html, treino_form.html
  e indisponivel.html.
- tests/test_semanas_6_7.py e tests/browser_smoke.py.

Criados nesta segunda etapa:

- banco.py: cliente compartilhado com certificados confiáveis do sistema.
- scripts/verificar_banco.py: diagnóstico remoto somente de leitura.
- migrations/auditoria_somente_leitura.sql: auditoria de metadados e permissões.
- templates/_metricas.html e templates/_grafico_semanal.html: componentes extraídos
  da primeira etapa para reutilização entre Dashboard e Progresso.

Outros arquivos ainda modificados no Git pertencem à primeira etapa, inclusive
tokens CSRF nos formulários, requirements.txt e .env.example.

## Revisão final de escopo

Não foram desenvolvidos Dicas/Recomendações, pontuação/XP, níveis, ranking,
recompensas, funcionalidades sociais ou notificações externas. Foram removidos
a soma de XP e os elementos dinâmicos de XP adicionados na primeira etapa.

Conforme a instrução de preservar código antigo, a prévia local de XP já existente
em atividade_form.html e o conteúdo promocional antigo da landing page não foram
reimplementados nem ampliados. Esses trechos herdados não constituem pontuação
persistida e não alimentam Dashboard, Progresso ou Conquistas. Nenhuma tela nova
exibe XP ou nível.

Referências técnicas complementares:
[upsert](https://supabase.com/docs/reference/python/upsert),
[RLS](https://supabase.com/docs/guides/database/postgres/row-level-security),
[chaves do Supabase](https://supabase.com/docs/guides/getting-started/api-keys).
