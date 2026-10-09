# Implantação do Lifes On

Revisão local de 08/10/2026. Nenhum comando foi executado no projeto Supabase.
As correções locais não certificam permissões, extensões e objetos desconhecidos
do banco real. Este roteiro complementa AUDITORIA_XP.md e atualiza a configuração
de chaves: o Flask agora aceita a chave atual `sb_secret_...` e o JWT legado
`service_role`. Não é necessário migrar o login para Supabase Auth nesta etapa.

## 1. Configuração exata do .env

No Supabase, abra **Settings → API Keys** do mesmo projeto da URL utilizada pelo
Lifes On. Copie uma chave **secret** para uso exclusivo do servidor. O Supabase
mapeia essa chave para o papel PostgreSQL `service_role`; os grants SQL continuam
válidos para ela. [Documentação oficial de chaves](https://supabase.com/docs/guides/getting-started/api-keys).

Antes de aplicar qualquer restrição de permissões, configure:

```dotenv
SUPABASE_URL=https://SEU-PROJETO.supabase.co
SUPABASE_SECRET_KEY=sb_secret_COLE_A_CHAVE_REAL_AQUI
LIFES_REQUIRE_SERVER_KEY=1
FLASK_SECRET_KEY=MANTENHA_O_VALOR_SECRETO_JA_EXISTENTE
```

Mantenha a URL e o valor real de FLASK_SECRET_KEY já existentes. Substitua apenas
a configuração da chave do Supabase e acrescente o modo estrito. O texto acima
contém marcadores, não valores para copiar literalmente. Nunca coloque a chave
em templates, JavaScript, Git ou logs.

Se preferir manter a chave **JWT legada service_role**, use isto **no lugar** de
SUPABASE_SECRET_KEY e deixe SUPABASE_SECRET_KEY ausente/comentada:

```dotenv
SUPABASE_SERVICE_ROLE_KEY=COLE_O_JWT_SERVICE_ROLE_REAL_AQUI
```

Não use a chave anon, publishable, senha do banco ou JWT secret de assinatura.
Escolha uma única variável de credencial para evitar confusão. Remova/comente
`SUPABASE_KEY` do .env do Lifes On após configurar a nova variável; se ela for
necessária a outro consumidor, a variável específica do servidor tem precedência.
A precedência exata é SECRET_KEY → SERVICE_ROLE_KEY → KEY. Uma chave específica
inválida causa falha; o código não tenta outra silenciosamente. O modo estrito
confere formato/role, não a assinatura nem a validade remota da credencial.

Reinicie o processo Flask após editar. Variáveis já definidas no terminal/serviço
têm precedência sobre .env (`load_dotenv` não as sobrescreve); atualize-as também
se existirem. O arquivo .env real não foi lido nem modificado nesta revisão.

## 2. Ordem de execução

1. Executar apenas `migrations/diagnostico_finalizacao.sql` e revisar o inventário
   completo no SQL Editor como postgres. Confirmar backup recuperável e os
   pré-requisitos: tabelas base, `semanas_6_7.sql` e `alertas_leitura.sql`.
   Se uma dessas migrações anteriores estiver pendente, revisá-la antes de aplicar;
   não executar `schema.sql` em banco existente.
2. Configurar o .env acima e colocar o aplicativo em manutenção. As etapas
   seguintes devem ser executadas integralmente, uma por vez, como postgres.
3. Aplicar `migrations/seguranca_backend.sql` após revisão/autorização das ACLs.
4. Aplicar `migrations/semanas_8_9.sql`.
5. Aplicar `migrations/finalizacao_premium.sql`.
6. Repetir o diagnóstico, reiniciar o Flask e validar os fluxos abaixo antes de
   liberar o uso. As etapas não são executadas automaticamente pelo aplicativo.

Manter manutenção até concluir todas as etapas. Uma falha reverte apenas a
transação do arquivo atual; etapas já confirmadas permanecem. Não ignorar erros
nem restaurar acesso anon para contorná-los.

## 3. O que foi conferido no script de segurança

- A verificação exige os grants positivos necessários ao Flask, além de negar
  privilégios excessivos: SELECT nas nove tabelas; INSERT em usuários e
  associações de conquista; INSERT/UPDATE/DELETE em atividades, metas, agenda e
  alertas. As sequências dessas inserções recebem USAGE/SELECT, sem UPDATE.
- O livro de XP permanece somente para leitura pelo serviço. Os triggers internos
  registram os eventos; o cliente não recebe INSERT/UPDATE/DELETE/TRUNCATE nele.
- Privilégios efetivos incluem PUBLIC, grants por coluna e herança. Uma herança
  desconhecida não é removida automaticamente, pois pode servir outro aplicativo.
  Se houver privilégio residual, o erro identifica papel, operação e objeto.
- O script restringe apenas as quatro funções trigger conhecidas do Lifes On,
  com assinatura sem argumentos. Não revoga funções por um prefixo genérico.
- A checagem SECURITY DEFINER trata funções de `public`; não confunde funções
  internas de `auth`, `storage` ou `extensions` com RPCs públicas. Uma função
  privilegiada acessível em public ainda bloqueia a migração, agora com assinatura,
  papel, proprietário e extensão identificados. Ser função de extensão não basta
  para declará-la segura; não há lista de exceções automática.
- Views e materialized views públicas legíveis por anon/authenticated continuam
  exigindo revisão. O erro informa nome, dono e opções. Nem `security_invoker=true`
  garante que funções chamadas pela view sejam seguras. O script não altera essas
  views e não pressupõe que uma view sem dependência direta seja inofensiva.
- Não há DML sobre os registros do usuário neste arquivo, alteração de policies
  ou RLS. A revogação de CREATE em public afeta outros consumidores do mesmo schema;
  revisar isso se o projeto não for exclusivo do Lifes On.

Se o gate apontar uma função/view desconhecida, revisar o objeto exato no diagnóstico
e decidir seus consumidores e grants antes de prosseguir. Não remover a verificação
para a implantação passar. Outras configurações de schemas expostos no PostgREST
continuam precisando de inspeção no projeto real.

O Flask usa sessões próprias e filtra por id_usuario; a chave do servidor pode
acessar todos os usuários. O controle de acesso por usuário permanece no backend.
Não há certificação de isolamento individual por RLS neste modelo.

## 4. Validação de funcionamento

Após as migrações, o operador pode executar o diagnóstico REST de leitura:

```powershell
.\.venv\Scripts\python.exe -m scripts.verificar_banco --detalhado
```

Ele usa a mesma seleção de chave do Flask e SELECT com limit=0, inclusive na tabela
de login. Não valida escrita. Não foi executado remotamente nesta revisão.

Com conta de teste autorizada, validar cadastro/login, Dashboard, atividade manual,
cronômetro, agenda, metas, conquistas, alertas e Dicas. Confirmar +20 por atividade,
+30 por conquista, +50 pela meta concluída e pelo primeiro marco de sete dias.
Repetir a mesma conclusão: uma atividade, nenhum XP duplicado e resposta original.
Excluir atividade: um único -20, sem apagar marcos históricos legítimos. Confirmar
persistência após recarga e isolamento entre duas contas; executar também o roteiro
de concorrência/API direta em AUDITORIA_XP.md. O diagnóstico SQL deve confirmar que
anon/authenticated não leem as tabelas e service_role não escreve diretamente no XP.

Testes locais abrangem SDK com transporte HTTP simulado para a chave atual,
configuração JWT legada, ACLs efetivas, grants faltantes, views, RPCs, herança,
upsert de conquistas/alertas, triggers de XP e integração Flask/cronômetro. Eles não
substituem o teste final no Supabase após uma implantação autorizada.
