# Revisão local da evolução de XP e metas

Nenhuma consulta ou alteração remota foi executada nesta revisão. As conclusões
abaixo são sobre o código e PostgreSQL local descartável via PGlite; não atestam
o estado atual do Supabase.

## Problemas confirmados e correções

| Situação | Resultado da revisão |
| --- | --- |
| Várias edições seguidas de exclusão | O fluxo normal já calculava deltas corretamente. Agora o livro confirma o saldo antes de editar/excluir; uma divergência no cache não pode produzir um estorno silenciosamente incorreto. |
| Histórico legado | A exclusão usa o valor efetivamente lançado, não uma constante nem a fórmula nova. Sem original, não há estorno. Os lançamentos permanecem intactos. |
| Reutilização explícita de ID antigo sem UUID | Podia inserir uma atividade cujo prêmio original já existia. A validação agora também reconhece a identidade pelo ID legado e impede essa reutilização. |
| Conversão de meta legada com progresso 100, sem prêmio | O teste de transição anterior não premiava a conclusão comprovada na conversão. Agora a conversão calcula os registros e, se completar o objetivo, insere o bônus único independentemente do percentual legado. |
| Recálculo indiscriminado | Qualquer alteração de atividade atualizava todas as metas automáticas do usuário, incluindo metas futuras ou de outra modalidade. Uma meta inválida sem relação com a sessão podia abortar a operação. Agora somente mudanças na contribuição da sessão provocam recálculo. |
| Percentual com alvo muito pequeno | A conversão para integer ocorria antes do limite de 100. A expressão antiga estoura com 22.000 km / alvo 0,001; o limite agora é aplicado antes do cast. |
| Triggers e unicidade preexistentes | Não eram novamente conferidos nesta evolução. A migração passa a recusar triggers desconhecidos/desativados, proteção obrigatória ausente ou incompatível e índices únicos obrigatórios ausentes/inválidos/parciais. Não remove objetos desconhecidos. |

## Política de bônus e estorno

**Atividade:** original + revisões numeradas + estorno devem fechar em zero após
a exclusão. Exemplo testado: `+45 +5 +40 -75 +30 -45 = 0`. Uma atualização sem
alteração de XP não acrescenta revisão. Repetir a exclusão ou reenviar a mesma
identidade não cria recompensa. O livro exclui bônus de metas/conquistas/sequência
dessa soma. Divergência em atividade v2 aborta a operação inteira para revisão;
não há reparação automática do histórico nem exclusão parcialmente confirmada.

**Meta:** mantém-se a política histórica da versão anterior: +50 uma única vez
por `id_meta`. O prêmio registra um marco alcançado; não representa o saldo atual
de atividades. Editar/excluir atividades recalcula o progresso, mas não estorna
esse marco. Reconcluir, alterar o alvo, converter novamente uma meta já automática
ou excluir a meta não paga novamente nem remove o prêmio anterior. Conquistas e
primeira sequência de sete dias mantêm a mesma política histórica. Portanto, uma
meta pode ficar abaixo de 100% e ainda ter um prêmio histórico legítimo.

**Conversão:** preserva ID e recompensa anterior, substitui progresso/acumulado
enviados pelo cliente pelo cálculo real e exige critério válido. Abaixo de 100%,
não cria prêmio; em 100%, usa `ON CONFLICT (id_usuario,chave_evento) DO NOTHING`.
Não permite mudar usuário/ID nem voltar ao modo manual. Conversão inválida reverte
toda a operação. A migração não converte metas ou concede bônus retroativos em massa.

## Interação com o banco e permissões

O BEFORE da atividade mantém identidade, versão e cache sob controle. O AFTER
registra o prêmio/ajuste/estorno e `lifes_z_recalcular_metas` recalcula os objetivos
afetados. O BEFORE da meta determina os valores reais e seu AFTER registra o marco
único. Um erro numa meta efetivamente afetada reverte atividade e XP na mesma
transação. O bloqueio da linha do usuário continua serializando a contabilidade.

O recálculo compara a contribuição anterior/nova por métrica, modalidade e período.
Não atualiza metas por frequência legada, campos técnicos ou desvínculo da Agenda.
Alterar apenas duração não atualiza metas de sessões/km; alterar apenas distância
não atualiza metas de minutos/sessões. Mudar data/modalidade alcança ambos os grupos
de metas quando necessário. Operações em lote ainda podem visitar uma meta em mais
de um evento de linha; não foi introduzida uma reestruturação dos triggers por lote.

A constraint de XP continua aceitando valores não nulos de -5040 a 5040, exceto
zero. O estorno verifica esse limite e não tenta adicionar um segundo estorno
se encontrar histórico incompatível. Unicidade por usuário/evento continua exigida.
A FK de Agenda com `ON DELETE SET NULL` foi exercitada em teste. Constraints
adicionais do projeto remoto continuam precisando de inspeção no diagnóstico.

Nenhuma nova permissão de tabela, sequência ou RLS foi introduzida nesta revisão.
A função auxiliar `lifes_private.saldo_atividade(bigint,text)` é SECURITY INVOKER,
pertence a postgres e não concede EXECUTE a PUBLIC/anon/authenticated/service_role.
Os triggers SECURITY DEFINER continuam com schema qualificado e search_path fixo.
O gate continua rejeitando RPC SECURITY DEFINER desconhecida acessível, sem revogá-la.

## Testes locais

### Revisão específica de OLD/NEW no recálculo

A implementação anterior acessava OLD e NEW no VALUES compartilhado. **Não foi
reproduzido erro de registro indisponível** no PostgreSQL local: a suíte nova
`tests/sql_recalcular_metas.cjs` passou antes da alteração nos três tipos de data.
Mesmo assim, o acesso foi tornado explícito por TG_OP: INSERT copia somente NEW,
DELETE somente OLD e UPDATE copia ambos, após verificar mudanças relevantes.
O SQL compartilhado usa variáveis `public.atividades%ROWTYPE`, cujos campos têm
estrutura definida e ficam NULL quando não há contribuição daquele lado.

Após a alteração, passaram novamente:

- A suíte específica em DATE, TIMESTAMP WITHOUT TIME ZONE e TIMESTAMPTZ.
  Para minutos/km/sessões, verifica acumulados 30/3/1 após INSERT, 60/6/1 após
  UPDATE e 0/0/0 após DELETE, além dos percentuais calculados.
- Rollback explícito de cada uma das três operações, comparando metas, atividades
  e livro com o estado anterior; também rollback por erro de um trigger de teste
  executado depois do recálculo, para cada operação.
- `sql_evolucao.cjs` e `sql_evolucao.cjs --date`, incluindo as regressões de
  estorno, conversão, marcos históricos, recálculo seletivo, ACL e reaplicação.

Nenhuma regra de prêmio, estorno, permissão ou filtragem foi alterada nesta revisão
específica. Nenhum comando foi executado no Supabase remoto.

### Revisão anterior completa

Executados com sucesso:

- 101 testes Python (`.venv/Scripts/python.exe -m unittest discover -q`).
- `sql_evolucao.cjs`, incluindo `sql_evolucao_regressoes.cjs`, nos modos timestamp
  e `--date` (este último usa progresso NUMERIC e nome VARCHAR).
- `sql_semanas_8_9.cjs`, `sql_seguranca.cjs`, `sql_defaults_xp.cjs`,
  `sql_indice_conquistas.cjs` e `sql_storage_perfis.cjs`: cinco suítes adicionais.

As regressões abrangem múltiplos ajustes; edição idêntica; estorno legado de 20 e
50; legado sem prêmio; saldo adulterado com rollback; retries; conversão com/sem
prêmio anterior; tentativa de progresso/acumulado manual; regressão/reconclusão;
isolamento de usuário/modalidade/período; contagem de metas realmente atualizadas;
desvínculo da Agenda; overflow; permissões; triggers desconhecidos/desativados/
ausentes; índice único ausente; reaplicação sem reescrever o livro.

Os testes que desativam triggers ou alteram fixtures só fazem isso no PostgreSQL
descartável local. Não são procedimentos para executar no Supabase.

## Implantação e validação

Pré-requisitos: três migrações anteriores aplicadas nesta ordem:
`seguranca_backend.sql` → `semanas_8_9.sql` → `finalizacao_premium.sql`.
O Flask deve continuar usando sua credencial exclusiva de servidor. Esta revisão
não exige mudança adicional de `.env` além da configuração já descrita no guia da
evolução. Não reaplique as migrações antigas sobre a evolução.

Após autorização para implantação, confira o diagnóstico somente leitura,
`migrations/diagnostico_evolucao.sql`, e revise triggers/constraints adicionais.
Execute o arquivo completo `migrations/evolucao_perfil_metas_xp_niveis.sql` como
postgres, em manutenção. Se uma guarda falhar, revise a causa; não remova a guarda
nem apague objetos para contorná-la. A transação deve ser revertida integralmente.
O Storage permanece uma etapa separada, conforme o guia anterior.

Depois do commit:

1. Execute `migrations/validacao_evolucao.sql`: todas as contagens de divergências
   devem ser zero, inclusive a nova verificação de estornos históricos.
2. Em conta de teste, registre corrida 30 min/3 km (+45), edite para 25 min/5 km
   (+5), 60 min/6 km (+40), 10 min/1 km (-75) e 30 min/3 km (+30); exclua (-45).
   Confira a soma zero desta sessão separadamente dos bônus.
3. Complete uma meta, reduza sua contribuição para regredir e depois reconclua.
   Confira percentual atual correto e exatamente um lançamento de +50.
4. Converta metas legadas com/sem prêmio, inclusive uma já marcada 100. Confira
   cálculo real, mesmo ID e ausência de duplicação do bônus.
5. Exclua o agendamento de uma sessão concluída: a sessão e o XP devem permanecer.
6. Confira cronômetro, Agenda, edição/exclusão, histórico, conquistas e Dashboard
   no Flask real; observe erros HTTP/PostgREST e compare com o diagnóstico.

Os testes locais não validam configuração PostgREST, concorrência real, constraints
extras ou o estado de dados/permissões do Supabase. Esses pontos permanecem sujeitos
à validação da implantação real.
