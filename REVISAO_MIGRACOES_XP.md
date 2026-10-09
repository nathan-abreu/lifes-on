# Integração das migrações de XP — 09/10/2026

Revisão e testes exclusivamente locais. Nenhum comando remoto foi executado.
Dados e permissões do Supabase real não foram alterados nem certificados nesta etapa.

## Criação do livro após a etapa de segurança

`seguranca_backend.sql` aceita a ausência de recompensas_xp, pois sua criação
pertence a semanas_8_9.sql. Não é seguro supor que as restrições aplicadas às tabelas
já existentes serão automaticamente aplicadas à tabela futura.

A segunda migração já revogava grants de tabela/sequência e EXECUTE das funções
conhecidas antes do commit. A revisão acrescenta limpeza explícita imediatamente
após CREATE TABLE IF NOT EXISTS: revoga privilégios da tabela, de todas as colunas
e das sequências vinculadas, para PUBLIC, anon, authenticated e service_role;
concede somente SELECT da tabela à service_role. O gate ao final confirma os
privilégios efetivos, inclusive os herdados. O fechamento anterior foi mantido
como verificação adicional. Nenhum dado é alterado por essa limpeza de ACL.

Default privileges afetam objetos futuros criados pelo papel executor. Não há
default privilege específico de coluna; grants por coluna podem vir de operações
posteriores ou automações DDL. São tratados separadamente porque revogar o grant
da tabela não basta. Os defaults globais/do schema não são modificados pelo plano.
Referências: [ALTER DEFAULT PRIVILEGES](https://www.postgresql.org/docs/current/sql-alterdefaultprivileges.html)
e [REVOKE](https://www.postgresql.org/docs/current/sql-revoke.html).

Tudo ocorre na mesma transação. Não há commit intermediário expondo a tabela
recém-criada com os grants iniciais. Se uma herança desconhecida conservar acesso,
a transação aborta; não remove automaticamente esse papel nem suas permissões.
O gate agora enumera os privilégios de tabela reconhecidos pela versão PostgreSQL,
incluindo MAINTAIN quando disponível, sem exigir esse nome em versões antigas.

## Resultado esperado após as três etapas

| Papel/objeto | Permissão |
| --- | --- |
| PUBLIC, anon, authenticated sobre livro/colunas/sequência | Nenhuma |
| service_role sobre recompensas_xp | SELECT, sem escrita direta, TRUNCATE ou TRIGGER |
| service_role sobre sequência do livro | Nenhuma |
| PUBLIC e papéis API sobre funções internas conhecidas | EXECUTE revogado |
| Triggers internos | SECURITY DEFINER de postgres, path pg_catalog, referências qualificadas e contexto validado |

O guard do livro é SECURITY INVOKER e exige o papel efetivo postgres, INSERT e
contexto de trigger. Profundidade não concede autorização por si só. A escrita
ocorre dentro das funções internas, mantendo atividade/recompensa e exclusão/
estorno na mesma transação. O cliente Flask lê o histórico sem poder inseri-lo
diretamente. Um serviço comprometido ainda pode manipular fontes que possui
permissão para gravar: a chave de servidor e o backend são partes confiáveis do
modelo; isso não é isolamento por usuário via RLS.

## Funções SECURITY DEFINER preexistentes

O gate continua conservador: função privilegiada em public executável por um
papel API bloqueia a transação e identifica assinatura, papel, proprietário e
extensão. Não há revogação automática de função desconhecida, nem exceção baseada
apenas em pertencer a uma extensão. As únicas revogações automáticas são das
assinaturas internas conhecidas do Lifes On. Funções em auth/storage/extensions
não são examinadas como RPCs de public; outros schemas expostos exigem revisão.
Views públicas legíveis também exigem análise. Um bloqueio pode atingir uma função
legítima: é necessário revisar seu uso e acesso, não ignorar o erro para prosseguir.

## Ordem e pré-requisitos

1. Revisar diagnostico_finalizacao.sql, somente leitura, e manter backup recuperável.
   Confirmar tabelas base, semanas_6_7.sql e alertas_leitura.sql; tipos, constraints,
   índices, triggers, proprietários e schemas expostos compatíveis.
2. Configurar Flask com SUPABASE_SECRET_KEY (`sb_secret_...`) ou JWT service_role
   em SUPABASE_SERVICE_ROLE_KEY e LIFES_REQUIRE_SERVER_KEY=1. Preservar URL e chave
   de sessão Flask. Reiniciar o processo; nunca enviar essa credencial ao navegador.
3. Em manutenção, como postgres, aplicar seguranca_backend.sql integralmente.
4. Aplicar semanas_8_9.sql integralmente.
5. Aplicar finalizacao_premium.sql integralmente e repetir o diagnóstico.
6. Validar com conta de teste autorizada antes de liberar uso: leitura de XP,
   atividade +20, exclusão -20 única, conquista +30, meta +50, retries sem duplicação
   e rejeição de escrita direta no livro. Seguir o checklist de ESTABILIZACAO_INTEGRACAO.md.

Requer papéis Supabase anon/authenticated/service_role existentes, service_role
com BYPASSRLS e privilégios de execução administrativa como postgres. Nenhum papel
é criado no SQL de produção, nenhuma policy/RLS é alterada. Não usar schema.sql
para atualizar banco existente. Manter manutenção se qualquer etapa falhar;
transações anteriores já confirmadas permanecem, a etapa com erro é revertida.

## Testes executados

- `node tests/sql_defaults_xp.cjs`: banco local sem livro na primeira etapa,
  defaults permissivos para tabelas/sequências/funções, grants de coluna simulados
  por fixture DDL, herança residual com rollback, PUBLIC verificado por papel sem
  grants próprios, RPC desconhecida preservada, SELECT do serviço, +20/-20 pelos
  triggers, escrita direta recusada e reaplicação sem mudar histórico/defaults.
- `node tests/sql_seguranca.cjs`: ACLs, herança, colunas, funções, views, permissões
  necessárias ao Flask, ataque por trigger aninhado e rollback.
- `node tests/sql_semanas_8_9.cjs`: recompensas, estornos, idempotência, sequência,
  fuso legado e atomicidade dos eventos.

As três suítes passaram em PostgreSQL WASM local. A suíte nova usa roles, grants
e triggers reais nesse banco descartável; não usa o Supabase. Isso verifica as
migrações no cenário controlado, não os objetos desconhecidos do projeto remoto.
schema.sql foi sincronizado com as versões revisadas.
