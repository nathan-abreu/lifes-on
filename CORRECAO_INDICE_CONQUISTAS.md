# Correção do índice de conquistas — 09/10/2026

Nenhuma alteração ou consulta remota foi executada nesta revisão. Nenhuma
conquista ou índice existente foi removido pelo SQL corrigido.

## Causa reproduzida

A comparação literal `pg_get_expr(indexprs, indrelid) = 'lower(btrim(nome))'`
rejeita um índice correto quando o tipo de nome exige cast para text. O teste
reproduziu o ERROR P0001 com nome varchar(120) e char(120), seguido de rollback
da migração inteira: índice ausente e dados/NOT NULL anteriores preservados.
Isso explica o comportamento relatado, mas o tipo real de nome não foi consultado
remotamente nesta revisão.

## Trecho alterado

Somente o bloco entre `lock table public.conquistas in share row exclusive mode;`
e `-- Seed completo dos 14 critérios` em migrations/finalizacao_premium.sql foi
alterado. A cópia desse SQL em schema.sql foi sincronizada.

1. CREATE UNIQUE INDEX usa explicitamente pg_catalog.lower e pg_catalog.btrim.
2. O bloco DO cria uma tabela temporária **vazia**, com LIKE public.conquistas,
   preservando os tipos/collations na definição, e um índice de referência.
   Não copia dados, não cria um segundo índice sobre a tabela real e não remove
   o índice real. Os objetos temporários novos são descartados no commit.
3. PostgreSQL analisa a expressão esperada usando esses tipos. A validação compara
   as expressões reconstruídas de ambos os índices no mesmo search_path controlado,
   em vez de compará-las com uma string SQL fixa. Não apaga casts por regex nem
   aceita uma função apenas por ter o nome lower/btrim.
4. Confere tabela correta, índice único, válido, pronto, ativo e imediato, uma
   chave de expressão, ausência de predicado parcial/exclusão, mesmo método de
   acesso, collation e classe de operadores. INCLUDE e ordenação DESC são aceitos
   quando não alteram a semântica da chave única. Uma expressão diferente falha.
5. Restaura o search_path anterior. Em caso de erro, a transação reverte também a
   referência temporária, mantendo dados e índices preexistentes.

Esta é uma comparação com uma referência analisada pelo próprio servidor e com
metadados de índice. Não tenta provar equivalência matemática entre expressões
arbitrárias. As propriedades verificadas estão documentadas em
[pg_index](https://www.postgresql.org/docs/current/catalog-pg-index.html).

## Posso executar o arquivo completo novamente?

**Sim, pode executar novamente a versão corrigida inteira de
finalizacao_premium.sql**, como postgres e em manutenção, desde que
seguranca_backend.sql e semanas_8_9.sql tenham sido concluídas com sucesso.
Não é necessário apagar/criar manualmente o índice nem repetir as etapas anteriores
se já foram confirmadas. Se a sessão SQL ainda estiver em estado de transação
abortada (25P02), executar ROLLBACK antes ou abrir uma nova sessão.

Executar de BEGIN a COMMIT, não apenas a seleção do bloco. O rollback anterior
pode ter revertido todas as outras alterações do arquivo, inclusive frequência,
modalidade, funções e estornos. Após o sucesso, repetir o diagnóstico de leitura
e a validação funcional documentada em ESTABILIZACAO_INTEGRACAO.md.

Se existir um índice realmente incompatível, o arquivo continuará abortando e o
preservará para revisão. Se houver nomes duplicados normalizados, CREATE UNIQUE
INDEX também continuará falhando sem remover conquistas. Outras constraints,
permissões ou objetos remotos ainda podem exigir revisão; esta correção não é
uma garantia sobre a configuração remota inteira.

## Testes SQL locais

`node tests/sql_indice_conquistas.cjs` reproduz o erro antigo e valida:

- Migração completa e reaplicação com nome text, varchar(120) e char(120).
- Cast explícito para text, funções qualificadas, INCLUDE e DESC equivalentes.
- Rejeição de índice não único, parcial, em outra coluna/tabela, com duas chaves,
  sem btrim, com collation/opclass diferente ou função homônima incompatível.
- Rejeição com indisvalid, indisready, indislive ou indimmediate desativados.
- Preservação dos IDs/dados existentes e do OID dos índices existentes, inclusive
  quando a validação falha; bloqueio real de nome duplicado por caixa/espaços.
- Limpeza automática da referência temporária após commit e reaplicação.

As manipulações de índice/catálogo usadas para montar casos inválidos existem
somente no banco WASM descartável dos testes, não na migração. As suítes
sql_defaults_xp.cjs, sql_seguranca.cjs e sql_semanas_8_9.cjs verificam também a
integração com permissões, recompensas, estornos e idempotência.
