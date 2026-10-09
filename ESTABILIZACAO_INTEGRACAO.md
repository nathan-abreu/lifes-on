# Estabilização da integração — 08/10/2026

**Ainda não liberado como funcional no Supabase real.** Foram feitas consultas
remotas de leitura, correções locais e testes. Nenhuma migração, escrita, exclusão,
GRANT, REVOKE ou alteração de RLS foi executada remotamente. O design e o .env real
foram preservados. As três migrações não foram alteradas nesta revisão.

## Diagnóstico por erro

| Relato | Evidência e causa | Situação |
| --- | --- | --- |
| Login: “Não foi possível carregar os dados” | Essa frase era o título genérico para qualquer APIError/HTTPError, inclusive falha posterior no Dashboard. A consulta às colunas de usuários funcionou; GET /login retornou 200. Não havia log persistido do erro relatado disponível no projeto. | **Causa original não confirmada.** Um login válido seguido de erro no Dashboard é uma hipótese, coberta por teste separado. Não foi usado e-mail/senha real para autenticação. |
| Agenda: “Treino não salvo” | `agenda.modalidade` e `agenda.realizado_em` retornaram 42703. O payload de salvar inclui modalidade, inclusive NULL. O formulário fazia SELECT * e afirmava conferir as colunas novas sem realmente fazê-lo. | **Incompatibilidade confirmada.** O GET de Novo treino agora verifica as colunas e retorna 503 explicativo. Nenhum INSERT remoto foi tentado; o código exato da tentativa original de INSERT não foi capturado. |
| Recuperar conquistas | O POST exige o livro de XP antes de sincronizar. O livro retornou PGRST205. As colunas de conquistas e usuario_conquista foram acessíveis. | **Bloqueio confirmado antes da gravação.** Permissão de INSERT, índices e triggers dessas tabelas ainda dependem da auditoria SQL real. |
| XP/histórico indisponível | A API não encontra `recompensas_xp` no schema/cache exposto (PGRST205). | **Indisponibilidade confirmada.** REST não distingue sozinho ausência física, schema exposto ou cache desatualizado; não se presume que apenas recarregar cache resolverá. |
| Excluir atividade | A rota chama exigir_xp antes de DELETE. O mesmo PGRST205 impede iniciar a exclusão. | **Bloqueio confirmado.** É necessário preservar essa proteção para não perder o estorno. DELETE remoto não foi executado. |
| Yoga e Ciclismo com ícones | Não havia yoga.png/webp nem ciclismo.png/webp; o catálogo acionava corretamente o fallback. | **Causa confirmada e corrigida localmente.** Duas ilustrações transparentes foram adicionadas ao catálogo existente. |

Não há evidência de indisponibilidade geral de conexão neste diagnóstico. A chave
selecionada é do tipo `sb_secret_...`; LIFES_REQUIRE_SERVER_KEY está ativo e
FLASK_SECRET_KEY está presente. A única variável de credencial preenchida no .env
é SUPABASE_SECRET_KEY. Não havia sobrescrita dessas variáveis no processo de
diagnóstico antes de carregar o arquivo. Nenhum valor secreto foi impresso.
Isso descreve o processo testado, não certifica outro terminal ou servidor já aberto.

## Banco remoto: resultado das leituras

`python -m scripts.verificar_banco --detalhado` retornou código 1 por estrutura
incompleta, usando SELECT com limit=0. Colunas acessíveis: usuários, alertas,
metas, catálogo de conquistas e associação de conquistas. Ausências detectadas:

| Objeto | Resultado PostgREST | Migração que o introduz |
| --- | --- | --- |
| atividades.chave_registro, atividades.id_agenda | 42703 | semanas_8_9.sql |
| agenda.realizado_em | 42703 | semanas_8_9.sql |
| agenda.modalidade | 42703 | finalizacao_premium.sql |
| dicas.categoria, dicas.fonte | 42703 | semanas_8_9.sql |
| recompensas_xp | PGRST205 | semanas_8_9.sql |

Leitura adicional apenas dos campos usados em cálculos verificou 9 atividades,
6 metas e 2 treinos: nenhum formato incompatível de duração, data, modalidade,
progresso, prazo ou horário foi encontrado nos campos conferidos. Não foram
exibidos registros, nomes, e-mails, hashes, IDs de usuários ou valores pessoais.
Essa verificação não prova a validade de todas as regras ou de registros futuros.

Para reproduzir HTTP sem alterar o banco, o cliente Flask recebeu um adaptador
que força limit=0 em todas as leituras e bloqueia qualquer mutação antes do envio.
A sessão era exclusivamente local, com usuário inexistente; não foi um login real.

| Requisição nesse ambiente restrito | Resposta |
| --- | --- |
| GET /login | 200 |
| POST /login sem registros retornados | 302 para /login, sem autenticação |
| GET /dashboard, /agenda, /conquistas, /pontuacao, /atividades | 200; XP indisponível explicitamente onde aplicável |
| GET /agenda/novo | 503, coluna ausente 42703 |
| POST /atividades/excluir/1 | 503, leitura de XP PGRST205; DELETE não iniciado |
| POST /conquistas/sincronizar | 503, leitura de XP PGRST205; upsert não iniciado |

Os avisos P0001 de alertas durante esse ensaio vieram do bloqueador local de escrita,
não do Supabase. O Dashboard tenta sincronizar alertas em sua execução normal;
nenhuma dessas sincronizações foi enviada remotamente pelo diagnóstico.

Os logs novos identificam endpoint, método HTTP, categoria, código e tipo da
exceção, sem mensagem SQL, URL, cabeçalhos ou conteúdo do formulário. Exemplo:
`rota=atividade_excluir metodo=POST categoria=estrutura codigo=PGRST205 tipo=APIError`.
Para fechar o relato de login, ainda é preciso identificar se a falha ocorreu no
POST /login ou no GET /dashboard e capturar esse código no processo usado pelo navegador.

## Correções locais

- `erros_banco.py`: distingue estrutura, credencial/permissão, consistência,
  timeout e comunicação; gera mensagens públicas sem repassar detalhes sensíveis.
- `app.py`: exigir_xp preserva a exceção original, em vez de transformar qualquer
  falha em PGRST205. O modo de leitura retorna indisponibilidade sem inventar 0 XP.
- Login com falha de banco mantém o formulário e o e-mail, sem devolver a senha
  nem criar sessão autenticada. Falha posterior no Dashboard não é tratada como
  senha incorreta ou novo login malsucedido.
- Novo treino confere explicitamente as colunas que precisa usar. Na falha de
  salvamento, mantém título, data, horário, modalidade e descrição; resposta vazia
  não é anunciada como sucesso. Timeout não comprova que uma gravação não ocorreu.
- Recuperação explícita de conquistas não diz “Seu registro foi salvo” quando
  nenhuma atividade foi salva. Falha de sincronização retorna 503; sucesso só é
  anunciado depois de concluir as consultas e operações necessárias.
- Exclusão continua condicionada ao livro de XP. Se nenhum registro for retornado
  pelo DELETE, informa “não encontrada ou já excluída”, sem anunciar exclusão real.
- `_xp.html` mostra a categoria relevante, sem afirmar que toda falha é conexão.
- `cronometro.js` distingue JSON inválido de conexão interrompida e mantém a
  confirmação pendente/UUID. Nenhum erro é convertido em sucesso ou recompensa.
- Novos assets `static/img/modalidades/yoga.png` e `ciclismo.png`, 1254×1254,
  transparência confirmada e servidos pelo Flask. O catálogo existente seleciona
  esses arquivos automaticamente; layout, CSS, paleta e demais artes preservados.

## Operações que dependem das migrações

| Operação | Dependência necessária |
| --- | --- |
| Cadastro/login e leitura dos dados legados | Tabelas base e grants de servidor. Não dependem diretamente da tabela XP. Credencial deve estar pronta antes de seguranca_backend.sql. |
| Salvar/editar treino no formulário atual | Agenda das semanas 6/7 e modalidade da finalização; realizado_em das semanas 8/9 é conferido no formulário novo. |
| Confirmar cronômetro e vincular agenda | UUID/id_agenda, índices únicos, livro e triggers das semanas 8/9; frequência NULL/modalidades da finalização. |
| Registrar/editar atividade manual | Mesmas dependências de XP/identidade e validador final; edição não repete XP básico. |
| Excluir atividade com consistência de XP | Livro acessível, CHECK aceitando -20 e trigger lifes_estornar_atividade da finalização. Apenas criar a tabela não basta. |
| Exibir XP e histórico | Livro acessível com SELECT do servidor; cálculo usa lançamentos reais. |
| Recuperar/desbloquear conquistas | Livro, associação única e trigger de recompensa; catálogo final completo de 14 critérios. |
| Concluir meta e registrar recompensa | Livro e trigger de transição de progresso. |
| Integrar todos os indicadores do Dashboard | Conjunto completo das três migrações, catálogo e alertas_leitura.sql. Leitura parcial não significa integração completa. |
| Categorias/fontes das Dicas | Colunas das semanas 8/9. |
| Ilustrações Yoga/Ciclismo | Arquivos locais; não dependem do Supabase. |

Atividades legadas não recebem +20 retroativo automaticamente ao instalar o livro.
Sua exclusão só estorna se existir o lançamento original +20. Uma atividade nova
recebe +20 uma vez; exclusão acrescenta um único -20. Marcos históricos de metas,
conquistas e primeira sequência são preservados. Recuperação explícita concede
somente conquistas elegíveis ainda não registradas; não inventa XP de atividades
passadas. Falha posterior da sincronização não desfaz uma atividade já confirmada.

## Ordem e checklist para validação futura

Primeiro executar/revisar `diagnostico_finalizacao.sql` no SQL Editor como postgres.
REST não permite certificar todos os tipos, constraints, índices, triggers,
proprietários e ACLs reais. Confirmar base, semanas_6_7 e alertas_leitura. Depois,
com credencial do servidor configurada, manutenção e autorização:
`seguranca_backend.sql` → `semanas_8_9.sql` → `finalizacao_premium.sql`.
O roteiro de .env está em IMPLANTACAO_SEGURA.md; a configuração atual conferida
já seleciona secret e modo estrito. Não executar schema.sql no banco existente.

- [ ] Repetir o diagnóstico de leitura: nenhuma coluna necessária indisponível.
- [ ] Conferir grants, RLS, índices únicos e triggers reais, incluindo o estorno;
  manter anon/authenticated sem acesso às tabelas e servidor sem escrita no livro.
- [ ] Reiniciar o processo Flask usado no navegador. Entrar com conta de teste
  autorizada e distinguir POST /login (302) de GET /dashboard (200).
- [ ] Criar um treino de teste futuro com modalidade; recarregar, editar e conferir.
- [ ] Confirmar esse treino no cronômetro; conferir uma atividade e +20 reais.
  Repetir UUID/agenda em duas abas: nenhuma duplicação de atividade ou XP.
- [ ] Simular resposta perdida; confirmar novamente e receber o registro original.
- [ ] Registrar e editar uma atividade de teste; manter seu XP básico único.
- [ ] Excluir somente a atividade criada para o teste: um único -20; repetir
  exclusão sem novo estorno. Não usar registros pessoais existentes nesse ensaio.
- [ ] Sincronizar conquistas elegíveis; conferir +30 por obtenção nova e nenhuma
  recompensa extra em nova sincronização. Conferir catálogo das 14 conquistas.
- [ ] Concluir uma meta de teste: +50 único; reabrir e concluir sem duplicar.
- [ ] Conferir Dashboard, Pontuação e alertas após recarga/reinício, em duas contas,
  sem vazamento de registros entre usuários. Conferir Yoga/Ciclismo no formulário.
- [ ] Registrar status/código de qualquer falha; não compartilhar .env, senha,
  tokens, headers Authorization/apikey ou mensagens SQL com dados pessoais.

## Testes locais e limites

`python -m unittest discover -q`: **86 aprovados**, incluindo 11 novos testes de
estabilização. Cobrem login, separação da falha de Dashboard, Agenda com coluna
ausente, preservação de formulário, resposta vazia, bloqueio de DELETE sem XP,
erro original preservado, recuperação de conquistas, mensagens e assets.

`node tests/sql_seguranca.cjs` e `node tests/sql_semanas_8_9.cjs`: aprovados em
PostgreSQL WASM local; ACLs, triggers, estornos, histórico, idempotência e rollback.

`python -m tests.browser_finalizacao`: aprovado no Chrome com banco simulado,
55 combinações de página/largura, integração Agenda→cronômetro, 503, JSON inválido,
recarga e retry após resposta perdida. Nenhum teste local constitui validação de
escrita ou autenticação real no Supabase. A implantação permanece pendente.

## Ilustrações: origem e prompts finais

Criadas com a skill imagegen e ferramenta integrada, usando corrida.png somente
como referência de estilo. Os originais gerados foram preservados fora do projeto;
os arquivos de uso estão em static/img/modalidades. Não foi usado fallback CLI.

Yoga:
> Create a NEW standalone Yoga illustration for Lifes On sports dashboard, save the final generated asset locally. Reference image is STYLE REFERENCE ONLY: premium detailed stylized 3D athletic character with warm cinematic studio highlights, charcoal athletic outfit and restrained coral-red accents, transparent background. New subject: adult woman practicing yoga, whole body in balanced seated lotus pose on a small charcoal mat, calm expression, both hands on knees, natural anatomy and fingers. Center composition with generous transparent margins. Fully transparent PNG alpha, no background, no lettering, no logo, no UI. Do not include runner or change reference asset. Production asset target yoga.png.

Ciclismo:
> Create a NEW standalone Ciclismo illustration for Lifes On sports dashboard. Reference image is STYLE REFERENCE ONLY: premium detailed stylized 3D athletic character with warm cinematic studio highlights, charcoal athletic outfit and restrained coral-red accents, transparent background. New subject: adult male cyclist wearing a safety helmet, fitted charcoal and coral cycling clothes and shoes, riding a modern charcoal road bicycle, whole character AND complete bicycle visible, dynamic three-quarter angle, natural anatomy. Center composition with generous transparent margins for a small sports card. Fully transparent PNG alpha, no backdrop, no lettering, no logo, no UI. Do not include the runner. Production asset target ciclismo.png.
