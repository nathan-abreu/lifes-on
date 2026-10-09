# Auditoria conjunta de XP e segurança — 08/10/2026

Configuração atual e roteiro direto: [IMPLANTACAO_SEGURA.md](IMPLANTACAO_SEGURA.md).

**Correções locais verificadas; implantação ainda não liberada.** Nenhuma migração,
GRANT, REVOKE, policy ou alteração de RLS foi executada remotamente nesta auditoria.
O diagnóstico SQL foi testado apenas em PostgreSQL local. A configuração efetiva
do Supabase, seus objetos legados e o comportamento de concorrência real ainda
precisam da validação abaixo. Este documento substitui as orientações anteriores
de implantação/permissões em SEMANAS_8_9.md e FINALIZACAO_PREMIUM.md.

## Achados e correções

`pg_trigger_depth()` mede aninhamento, não identidade nem autorização. Um cliente
com escrita nas fontes podia fabricar atividades, concluir metas ou conceder
conquistas; proteger somente INSERT direto no livro não resolvia isso. Com RLS
desabilitado e grants para anon, também era possível consultar/alterar dados de
outros usuários fora do Flask. A chave anon não é um segredo de servidor.

O login atual usa sessão Flask e IDs próprios, sem Supabase Auth. Todos os pedidos
REST com a mesma chave representam o mesmo papel PostgreSQL; não existe um
`auth.uid()` distinto para cada sessão Flask. Acrescentar uma policy genérica não
criaria esse vínculo. A proteção compatível proposta é usar uma credencial apenas
no servidor e retirar dos papéis públicos o acesso às tabelas do aplicativo.
Essa conclusão decorre da arquitetura local e do funcionamento de
[chaves Supabase](https://supabase.com/docs/guides/getting-started/api-keys) e
[RLS](https://supabase.com/docs/guides/database/postgres/row-level-security).

| Arquivo | Alteração |
| --- | --- |
| `migrations/seguranca_backend.sql` | Nova etapa explícita de ACL, anterior às duas migrações; falha se restarem privilégios proibidos por herança/coluna, RPCs públicas SECURITY DEFINER acessíveis ou views públicas legíveis por anon/authenticated. |
| `migrations/semanas_8_9.sql` | Exige a etapa de segurança, valida unicidade efetiva, fixa proprietários/search_path/ACL de funções e restringe o livro a leitura pelo serviço. |
| `migrations/finalizacao_premium.sql` | Mesma verificação de segurança, contextos exatos de triggers, estorno único, marcos históricos e catálogo completo com unicidade de nome normalizado. |
| `app.py` | Recupera a atividade original antes e depois de INSERT suprimido; não presume que toda resposta vazia é duplicidade. |
| `banco.py`, `.env.example` | Credencial de servidor preferencial e modo estrito opcional `LIFES_REQUIRE_SERVER_KEY=1`, que rejeita configuração anon. O `.env` real não foi alterado. |
| `static/js/cronometro.js` | Distingue registro já existente, atividade excluída e agenda já concluída sem atividade disponível. |
| `migrations/semanas_6_7.sql`, `schema.sql` | Seed antigo compara nome normalizado; instalação nova sincronizada com as migrações corrigidas. |

### Permissões propostas

| Objeto | anon / authenticated | service_role usado pelo Flask |
| --- | --- | --- |
| `usuarios` | Nenhum acesso | SELECT, INSERT |
| `atividades`, `metas`, `agenda`, `alertas` | Nenhum acesso | SELECT, INSERT, UPDATE, DELETE |
| `usuario_conquista` | Nenhum acesso | SELECT, INSERT |
| `conquistas`, `dicas`, `recompensas_xp` | Nenhum acesso | SELECT |
| Sequências necessárias às inserções do Flask | Nenhum acesso | USAGE, SELECT; sem UPDATE |
| Sequência do livro e funções internas `lifes_*` | Nenhum acesso | Nenhum acesso |

São revogados também grants PUBLIC e por coluna nas tabelas listadas. O script
não remove automaticamente heranças desconhecidas: aborta e pede revisão técnica
da origem do privilégio. Revoga CREATE em `public` dos papéis API e PUBLIC; isso
exige revisar outros aplicativos que compartilhem o projeto/schema.

As funções internas SECURITY DEFINER pertencem explicitamente a `postgres`, usam
`search_path=pg_catalog`, referências qualificadas e conferem relação/operação do
trigger. Seu EXECUTE é revogado inclusive de PUBLIC e service_role; triggers já
instalados continuam funcionando. O guard do livro é SECURITY INVOKER: exige
`current_user=postgres`, relação correta, INSERT e contexto aninhado. A barreira
principal é a ACL; a profundidade é somente uma verificação adicional. Também há
bloqueio de UPDATE, DELETE e TRUNCATE do livro.

PostgreSQL executa SECURITY DEFINER com os privilégios do proprietário e preserva
ownership/ACL ao substituir funções; por isso a migração trata essas propriedades
explicitamente. BYPASSRLS não substitui permissões de tabela. Referências:
[CREATE FUNCTION](https://www.postgresql.org/docs/17/sql-createfunction.html) e
[privilégios PostgreSQL](https://www.postgresql.org/docs/17/ddl-priv.html).

### Idempotência e resposta HTTP

Cada busca usa `id_usuario` da sessão, primeiro por UUID e depois por agenda.
Se outra transação vencer após o SELECT inicial e o BEFORE INSERT retornar NULL,
o backend consulta novamente e devolve ID, modalidade, duração e data persistidos.
Um retry com dados diferentes não altera nem fabrica a resposta original. A
resposta usa `duplicado=true`, `situacao=existente` e nenhuma nova recompensa.

Se a atividade foi excluída, o lançamento original comprova a operação já
processada: `situacao=excluida`, campos da atividade nulos e nenhum novo INSERT/XP.
Uma agenda concluída sem atividade recuperável retorna `agenda_ja_concluida`.
O campo legado `registrado=true` significa operação processada; `situacao` informa
se a atividade ainda existe. Sem qualquer evidência persistida, INSERT vazio
produz 503, nunca um falso sucesso ou uma falsa duplicidade.

O livro usa chave de evento única por usuário; atividades também têm unicidade
por usuário/UUID e usuário/agenda. O lock no usuário serializa o processamento
dos eventos internos. Falha no XP reverte a atividade e a conclusão da agenda na
mesma transação. A sincronização Python de conquistas continua posterior; se
falhar, a atividade e seu XP básico permanecem válidos e a interface informa que
as conquistas precisam de sincronização explícita.

### Regra de estornos e histórico

| Evento | Prêmio | Após edição/exclusão |
| --- | --- | --- |
| Atividade nova | +20 | Edição não repete XP. Exclusão gera -20 uma única vez, somente se houver lançamento original +20; original preservado. |
| Primeira sequência de 7 dias | +50 | Marco histórico permanente, único por usuário; não estornado ao editar/excluir atividades. Edição de data pode alcançar o marco pela primeira vez. |
| Meta que passa de progresso menor que 100 para 100 | +50 | Único por ID; reabrir, concluir novamente ou excluir não apaga nem repete o prêmio. |
| Conquista desbloqueada | +30 | Único por usuário/ID; redução posterior dos indicadores não apaga prêmio nem desbloqueio. |

Não há XP retroativo automático para atividades/meta já existentes ao instalar
triggers; não se inventa um estorno para atividade antiga sem prêmio. A migração
não recalcula nem apaga o histórico. O total é a soma do livro, não uma função
apenas dos registros atuais. Concluir novamente um treino exige uma nova agenda
ou uma nova atividade independente; excluir sua atividade não reabre a agenda.

Se o diagnóstico encontrar lançamentos antigos forjados, duplicados ou incompatíveis,
eles precisam de análise administrativa baseada em evidências. Não há remoção
automática de premiações legítimas nem prova retroativa da autenticidade do legado.

### As 14 conquistas

| Nome canônico Python | Critério |
| --- | --- |
| Primeiro passo | 1 atividade |
| Em Movimento | 5 atividades |
| Foco Total | 10 atividades |
| Veterano | 30 atividades |
| Lenda do Treino | 100 atividades |
| Meta batida | 1 meta concluída |
| Caçador de Metas | 5 metas concluídas |
| Mestre dos Objetivos | 10 metas concluídas |
| Semana cheia | Melhor sequência de 7 dias |
| Constância de Aço | Melhor sequência de 14 dias |
| Imparável | Melhor sequência de 30 dias |
| Uma Hora de Superação | 60 minutos acumulados |
| Dez Horas de Evolução | 600 minutos acumulados |
| Centurião | 6.000 minutos acumulados |

O teste compara todos os nomes e descrições SQL com `REGRAS_CONQUISTAS`; os testes
de cálculo cobrem os limiares. Frequência não multiplica sessões/minutos. O cálculo
usa dias locais de São Paulo, aceita o timestamp legado sem offset como UTC e
ignora datas futuras. As conquistas são calculadas no Python confiável, não pelo
navegador; a função SQL de premiação não verifica cada critério de conquista.

O seed usa `lower(btrim(nome))` e conserva IDs, pontos e grafia existentes. Um índice
único impede duplicidade dos nomes canônicos por caixa/espaços. Se já houver dois
IDs com mesmo nome normalizado, a transação aborta sem mesclar ou excluir dados;
é necessário decidir o tratamento do legado e de suas associações. Catálogo
personalizado pode conter mais de 14 linhas: a migração não o remove.

## Diagnóstico somente leitura e pré-requisitos

Executar `migrations/diagnostico_finalizacao.sql` no SQL Editor como administrador,
sem executar as migrações. Todo o arquivo usa transação READ ONLY; o bloco DO faz
somente SELECT e emite contagens via NOTICE. Funciona sem as tabelas novas.
Preservar os resultados de cada bloco (o editor pode exibir apenas o último).
Definições de funções legadas podem conter segredos; revisar antes de compartilhar.

Conferir tabelas/proprietários, todos os tipos/defaults/NOT NULL/identidades,
constraints/FKs validadas, índices únicos válidos e imediatos, triggers ativos e
suas funções, RLS/policies, roles/heranças, ACLs efetivas por tabela/coluna/sequência,
EXECUTE de funções, views e privilégios padrão. O relatório inclui duplicidades
por UUID, agenda, conquista e evento, além de estornos sem origem e eventos fora
das regras conhecidas. Contagens incompatíveis exigem investigação, não DELETE.

Pré-requisitos específicos: PostgreSQL compatível com CREATE OR REPLACE TRIGGER;
papéis Supabase existentes e service_role com BYPASSRLS; execução como postgres;
base, `semanas_6_7.sql` e `alertas_leitura.sql` já compatíveis. IDs/FKs devem ser
compatíveis com bigint, UUID deve ser uuid; data_registro deve ser timestamp com
ou sem fuso, neste último caso representando UTC. Conferir também checks legados
de modalidade, frequência e XP: um CHECK adicional somente positivo impediria
estornos mesmo após substituir `recompensas_xp_xp_check`. Não o remover sem revisão.
IF NOT EXISTS não converte tipos legados nem corrige constraints personalizadas.

Revisar no painel a lista de schemas expostos pelo PostgREST: o verificador cobre
os objetos do aplicativo em public e lifes_private, não certifica RPCs/views em
outros schemas. Inspecionar triggers desconhecidos já anexados às tabelas.
Default grants não são modificados globalmente; novas tabelas/funções futuras
precisam de ACL explícita antes do commit. Administradores e funções confiáveis
com privilégios de proprietário permanecem parte da fronteira de confiança.

## Ordem segura de implantação futura

1. Obter e revisar o diagnóstico real, resolver incompatibilidades sem apagar
   dados e manter backup recuperável. Revisar impacto em outros consumidores.
2. Em manutenção, configurar no servidor `SUPABASE_SECRET_KEY` (ou JWT legado em `SUPABASE_SERVICE_ROLE_KEY`) e
   `LIFES_REQUIRE_SERVER_KEY=1`, mantendo a mesma URL e sessão Flask. Nunca enviar
   a credencial ao navegador, repositório ou logs. O modo estrito aceita
   a chave atual `sb_secret_...` e JWT legado service_role; o SDK instalado foi
   validado localmente com transporte HTTP simulado.
   A inspeção local de role evita erro de configuração, mas não valida assinatura;
   a autenticação real continua sendo feita pelo Supabase.
3. Após autorização específica de ACL, executar `seguranca_backend.sql` como
   postgres. **Flask ainda configurado com anon perderá acesso.** O script é
   transacional e não altera RLS/policies.
4. Executar `semanas_8_9.sql`, depois `finalizacao_premium.sql`. As duas exigem o
   verificador privado e voltam a conferir permissões ao final. Manter manutenção
   durante todas as etapas, inclusive reaplicações nessa ordem.
5. Repetir o diagnóstico e a validação abaixo antes de liberar tráfego.

Se uma etapa falhar, sua transação reverte; etapas anteriores já confirmadas
permanecem. Manter manutenção e corrigir a causa. Não restaurar grants públicos
amplos para fazer o Flask funcionar. `schema.sql` contém a mesma evolução para
instalação nova em Supabase; não executar sobre banco existente. Nenhuma etapa
deste roteiro foi executada remotamente nesta entrega.

## Validação após a migração

1. Conferir no diagnóstico: nenhum privilégio efetivo de anon/authenticated nas
   nove tabelas; service_role somente SELECT no livro, sem acesso à sua sequência,
   sem TRIGGER/TRUNCATE/CREATE; funções internas de postgres com path pg_catalog
   e EXECUTE negado à API; índices válidos, triggers ativos e zero duplicidades.
   Comparar RLS/policies com o inventário anterior: os scripts não devem alterá-los.
2. Pela API REST com anon, uma consulta às tabelas deve ser recusada, sem retornar
   dados pessoais. Conferir também RPCs/views/schemas expostos. Pela API de serviço,
   leituras devem funcionar e escrita direta no livro deve ser negada. Ensaiar
   tentativas de escrita em staging/conta de teste autorizada, nunca dados reais.
3. Pelo Flask, com conta de teste autorizada: cadastrar/entrar, listar páginas,
   registrar atividade manual e timer, concluir agenda, editar e excluir. Confirmar
   atividade +20 e eventual conquista +30 separadamente no livro.
4. Repetir o mesmo UUID em duas requisições simultâneas e com resposta perdida:
   uma atividade, um evento +20 e respostas apontando o mesmo registro. Repetir
   por agenda com UUID diferente. Excluir a agenda e repetir o UUID original;
   excluir a atividade e repetir: estado histórico, sem recriação de XP.
5. Excluir atividade premiada: um único -20. Repetir exclusão/retry: nenhum novo
   lançamento. Reabrir/concluir novamente meta: +50 único. Diminuir indicadores
   após desbloqueio: conservar marcos legítimos. Confirmar sequência com datas
   locais próximas à meia-noite e, se presente, timestamp legado UTC sem offset.
6. Usar duas contas Flask: ID/UUID/agenda de outra conta não permitem ler, editar,
   excluir ou concluir registros dela. Reabrir navegador/reiniciar Flask e
   confirmar persistência real, recálculo e feedback sem repetição.

O serviço pode acessar todos os usuários por definição; isso não é isolamento
RLS por usuário. Comprometimento da chave ou falha no backend continua sendo risco.
Uma evolução possível é Supabase Auth + mapeamento explícito dos IDs próprios para
auth.users + JWT individual e RLS; outra é conexão de servidor com papel dedicado
mais restrito. Ambas exigem projeto, testes e autorização próprios. Não habilitar
policies baseadas em auth.uid() sem migrar a identidade.

## Testes executados localmente

- `python -m unittest discover -q`: **75 testes aprovados**, incluindo 11 testes de auditoria e configuração
  contratos de retry, recuperação de original, isolamento por usuário, configuração
  de chave e equivalência do catálogo SQL/Python.
- `node tests/sql_semanas_8_9.cjs`: aprovado em PostgreSQL WASM (PGlite), cobrindo
  transação/rollback, repetição, sequência, edição, exclusão e XP histórico.
- `node tests/sql_seguranca.cjs`: aprovado; roles reais locais, ACL direta/coluna/
  herança, RPC insegura, índices incompatíveis, nomes duplicados, leitura/escrita
  anon bloqueadas, fluxo service_role e tentativa de injeção com trigger aninhado.
- `python -m tests.browser_semanas_8_9`: Chrome aprovado, incluindo duplo clique,
  resposta perdida, retry e feedback de XP.

As dependências/comandos PGlite estão no README. Fixtures SQL são descartáveis e
nunca se conectam ao Supabase. Corrida HTTP é simulada nos testes Python; PGlite
não certifica concorrência entre conexões PostgREST. Permanecem pendentes o
diagnóstico real e os testes autorizados de implantação. **Não considerar a
segurança e a consistência do XP em produção verificadas antes dessas evidências.**
