# Evolução: perfil, metas automáticas, distância e níveis

Implementação local para revisão, em 09/10/2026. Nenhuma migração, alteração de
permissão, policy, bucket ou dado foi executada no Supabase. O `.env` real não foi
alterado. As três migrações já implantadas foram preservadas.

A verificação remota feita com `SELECT ... LIMIT 0` confirmou acesso às colunas
da versão anterior nas nove tabelas. A mesma sondagem com `--evolucao` retornou
`42703` nos quatro grupos que precisam de novas colunas: `usuarios`, `atividades`,
`metas` e `recompensas_xp`. Isso confirma a dependência da nova migração; não é
um diagnóstico de falha de conexão. Não foram consultados registros pessoais.
A leitura do OpenAPI real (HTTP 200, sem registros) também confirmou:
`usuarios.nome varchar(100)`, IDs bigint, `atividades.duracao integer`,
`atividades.data_registro date`, `metas.progresso numeric` e `metas.prazo date`.
A nova migração preserva esses tipos; DATE é tratado como dia de Brasília,
sem conversão que o desloque para a véspera. O default de DATE passa a usar
explicitamente Brasília; timestamp sem offset usa default UTC. A configuração
da serialização do Flask é conferida pelo diagnóstico CLI.
Essas leituras não provam ACLs completas, triggers, RLS ou persistência remota.
A consulta de metadados do bucket previsto retornou 404 pela API de Storage;
ele ainda não está disponível pela credencial atual. Nenhum arquivo foi listado,
enviado ou removido nessa verificação.

**Arquivos e comportamento entregues**

- `app.py`: perfil, foto autenticada, validação de distância, metas automáticas,
  recuperação de duplicidades, feedback correlacionado à transação e estornos.
- `perfil.py`: validação de nome, decodificação real da imagem, limite de tamanho,
  remoção de metadados e caminhos exclusivos do usuário.
- `evolucao.py`: números decimais, limites por modalidade, validação de metas e
  apresentação de quantidades em português.
- `recompensas.py`: cálculo inteiro de níveis progressivos, sem percorrer níveis.
- `modalidades.py` e `static/img/modalidades/caminhada.png`: Caminhada em todo o
  catálogo, com ilustração 3D própria. As imagens anteriores foram preservadas.
- Templates de perfil/avatar, Dashboard, atividades, cronômetro, metas,
  pontuação e navegação: novos controles integrados ao tema existente.
- `static/js/perfil.js`, `distancia.js`, `cronometro.js`, `interacoes.js` e
  `static/css/premium.css`: prévia, campos condicionais, distância pendente,
  mensagens de ajustes/subida/descida de nível e responsividade.
- `requirements.txt`: Pillow 12.3.0; `.env.example`: nome do bucket privado.
- `scripts/verificar_banco.py`: opção `--evolucao`, somente leitura.
- Novas migrações/diagnósticos e testes descritos abaixo. Testes de regressão
  anteriores foram atualizados para minutos completos e metas automáticas.

**Banco e permissões**

`migrations/evolucao_perfil_metas_xp_niveis.sql` acrescenta:

| Tabela | Novas colunas |
|---|---|
| usuarios | foto_path, perfil_versao |
| atividades | distancia_km, xp_versao, xp_atual, xp_revisao, xp_transacao |
| metas | metrica, modalidade, alvo, inicio, acumulado |
| recompensas_xp | transacao |

Há índices de apoio por usuário/data de atividade e por usuário em metas
automáticas. O CHECK antigo do livro passa a aceitar lançamentos inteiros não
nulos de -5040 a +5040, exceto zero. Isso comporta sessões, diferenças, estornos
e os bônus existentes. Não concede permissão de escrita no livro.

As funções internas validam o contexto do trigger, usam `search_path=pg_catalog`,
objetos qualificados e execução restrita. O banco impõe versão, XP, revisão e
transação da atividade, ignorando valores forjados nesses campos. O lock do usuário
serializa a contabilidade; atividade, ajuste/estorno e recálculo de metas ocorrem
na mesma transação. Falhas provocam rollback, sem confirmação parcial dessas operações.

O gate mantém verificações de ACL efetiva, herança, colunas, sequências, views e
RPCs SECURITY DEFINER desconhecidas. A única ampliação em `usuarios` é
`UPDATE(nome,foto_path,perfil_versao)` para `service_role`. Email, senha e ID não
ganham UPDATE. `anon`, `authenticated` e `PUBLIC` continuam sem acesso às tabelas
do aplicativo; `service_role` lê XP, mas não insere, edita, exclui ou trunca o livro.
Funções desconhecidas não são revogadas automaticamente: o gate aborta para revisão.

O Flask continua responsável por autenticar a sessão e filtrar o usuário. A chave
de servidor é privilegiada e fica exclusivamente no backend. Esta evolução não
migra a autenticação para Supabase Auth nem altera RLS das tabelas do aplicativo.

**Regras de XP e preservação histórica**

Para novas sessões:

`XP = minutos completos + floor(distância_km × taxa da modalidade)`.

| Modalidade | XP/km | Velocidade média máxima aceita |
|---|---:|---:|
| Corrida | 5 | 30 km/h |
| Caminhada | 3 | 12 km/h |
| Ciclismo | 2 | 80 km/h |
| Natação | 10 | 10 km/h |
| Musculação, Yoga, Artes Marciais, Outros | sem distância | — |

São limites de validação do aplicativo. Duração: 1–1440 minutos; distância
opcional, positiva, até 1000 km e no máximo três casas decimais. A velocidade
usa a duração inteira armazenada. Distância sem duração compatível é rejeitada,
nunca silenciosamente cortada. O teto matemático é 5040 XP por sessão (corrida
de 1440 minutos/720 km); bônus de metas/conquistas são lançamentos separados.

Exemplos: 30 min/3 km de corrida = 45 XP; 25 min/5 km = 50 XP;
40 min de Yoga = 40 XP; 60 min de Artes Marciais = 60 XP.
O cronômetro exige 60 segundos e usa `segundos // 60`: 179 segundos = 2 minutos.
Erros de distância ou rede mantêm a confirmação, UUID, duração e distância para
correção/reenvio, inclusive após recarregar. Datas futuras são recusadas.

Linhas anteriores recebem `xp_versao=1`, sem alterar lançamentos antigos.
Editar uma sessão legada não converte seu XP para a nova regra. Excluí-la estorna
o lançamento original, se existir; uma sessão antiga sem prêmio não recebe estorno.
Nas novas sessões (`xp_versao=2`), editar registra apenas a diferença em
`ajuste:atividade:<identidade>:<revisão>`; excluir estorna o saldo vigente da sessão.
Por exemplo: +45, ajuste +5, exclusão -50. Os três lançamentos permanecem.
O saldo é conferido no livro (original + revisões numeradas + estorno), excluindo
bônus. Divergência entre livro e `xp_atual` de uma sessão v2 aborta edição/exclusão
para revisão, sem reparar valores automaticamente. Reutilizar o ID de uma sessão
legada já premiada também não cria uma sessão nova sem recompensa correspondente.
UUID e vínculo com Agenda continuam impedindo repetir a sessão e seu prêmio.

Os bônus de +50 por meta, +30 por conquista e +50 pela primeira sequência de
sete dias continuam únicos e históricos. Reduzir progresso, editar ou excluir
atividades/metas não apaga esses marcos. A Agenda mantém o registro de conclusão
mesmo se a atividade for excluída, evitando reutilização do mesmo treino para XP.

`transacao` correlaciona os lançamentos realmente gerados pela operação;
`xp_transacao` permite reconhecer bônus de uma edição apenas de data, mesmo sem
diferença no XP da sessão. Não são números fornecidos pelo navegador. Conquistas
continuam sincronizadas pelo Flask após o commit: falhas são informadas e podem
ser recuperadas em **Conquistas → verificar pendentes**, sem repetir recompensas.

**Metas e níveis**

Metas novas usam minutos, quilômetros ou sessões. O PostgreSQL soma registros
válidos do usuário, da modalidade escolhida (ou todas compatíveis) e do período
inclusivo em `America/Sao_Paulo`. Timestamps legados sem offset continuam tratados
como UTC. Frequência legada não multiplica sessões. Distância ausente não soma
quilômetros, mas a atividade continua contando minutos/sessão.

O percentual é `min(100, floor(acumulado × 100 / alvo))`; sessões e minutos têm
alvo inteiro. Criar uma meta cujo período já contém atividades suficientes pode
concluí-la imediatamente. Edições/exclusões recalculam o acumulado. Se voltar a
menos de 100%, deixa de aparecer concluída, mas mantém o bônus histórico, sem
premiar outra vez ao recompletar. Não existe controle manual do percentual.

Metas legadas mantêm descrição, prazo e progresso. Editar apresenta conversão
explícita para um critério automático, preservando ID e eventual recompensa.
Nenhuma meta antiga é convertida em massa.
Na conversão, o percentual legado é ignorado: os registros reais determinam o
resultado. Se comprovarem 100%, o bônus é concedido apenas se a chave `meta:<id>`+ainda não existir, inclusive quando o percentual legado já era 100. Abaixo de
100%, nenhum bônus novo é criado. Não é permitido voltar ao modo manual.
Alterações de atividades recalculam somente metas cuja contribuição mudou,
considerando métrica, modalidade e período anterior/novo. Mudanças técnicas,
frequência legada ou desvínculo da Agenda não provocam recálculo sem necessidade.

A revisão SQL e seus cenários adicionais estão em
[REVISAO_EVOLUCAO_XP.md](REVISAO_EVOLUCAO_XP.md).

O nível 1 precisa de 100 XP; do nível L≥2 para o seguinte são `150 × (L−1)` XP.
O limiar acumulado de L≥2 é `100 + 75 × (L−2) × (L−1)`:
0 → L1, 100 → L2, 250 → L3, 550 → L4, 1000 → L5.
A implementação usa raiz quadrada inteira, sem teto artificial. Estornos reduzem
o total e podem diminuir o nível. Dashboard, Pontuação e Perfil usam esse mesmo cálculo.

**Fotos privadas e Storage**

O upload aceita JPEG/PNG/WebP estáticos, até 5 MiB e 16 milhões de pixels.
O servidor decodifica, verifica integridade, aplica orientação, reduz a imagem a
no máximo 512×512 e grava um PNG novo sem EXIF/metadados. GIF, SVG, arquivos
corrompidos e animações são recusados. O nome original do arquivo não vira caminho.

Objetos usam `<id_usuario>/<uuid>.png`. A rota `/perfil/foto` só lê o caminho do
usuário da sessão e devolve `private, no-store`; não aceita ID/caminho de terceiros.
Nome/foto usam uma versão otimista para impedir sobrescrita de outra aba.

`migrations/storage_perfis_privado.sql` é uma proposta separada: cria o bucket
**privado** `lifes-perfis`, com limite de 5 MiB e MIME `image/png`. Acrescenta uma
policy **restritiva** em `storage.objects` que bloqueia esse bucket para `anon` e
`authenticated`, inclusive diante de policies permissivas globais. Não altera
RLS nem policies existentes; exige RLS já ativo. Bucket/policy homônimos
incompatíveis provocam erro e rollback, sem substituição automática.

Storage e a tabela de perfil não compartilham uma transação. Depois de confirmar
o novo perfil, o servidor tenta remover a foto anterior. Falha nessa limpeza é
informada. Quando uma falha de rede torna o resultado do UPDATE incerto, o upload
não é apagado às cegas: pode ser a foto já confirmada. Um arquivo órfão privado pode
ficar pendente. Reconciliar esses casos comparando caminhos referenciados antes de
qualquer limpeza autorizada; não usar exclusão em massa nem apagar linhas de
`storage.objects` manualmente.

O fluxo segue as referências oficiais de [acesso ao Storage pelo servidor](https://supabase.com/docs/guides/storage/security/access-control)
e [download de buckets privados](https://supabase.com/docs/guides/storage/serving/downloads).
A ordem dos triggers considera a [ordem alfabética do PostgreSQL](https://www.postgresql.org/docs/current/trigger-definition.html).

**Ordem de implantação e `.env`**

1. Fazer backup e interromper gravações durante a troca. As três migrações
   anteriores já foram aplicadas, conforme informado. **Não reaplicá-las depois
   da evolução**: elas contêm funções/restrições antigas e não são um rollback.
2. Executar `migrations/diagnostico_evolucao.sql` (somente leitura) como postgres.
   Conferir também a estrutura anterior com `diagnostico_finalizacao.sql`,
   especialmente triggers/RPCs/views desconhecidos. Antes da evolução, as novas
   colunas aparecerão ausentes. Não contornar erros do gate removendo verificações.
3. Após revisão/autorização, aplicar o arquivo completo
   `migrations/evolucao_perfil_metas_xp_niveis.sql` como postgres.
4. Para fotos, após revisão/autorização específica da policy de Storage, aplicar
   `migrations/storage_perfis_privado.sql`. Sem essa etapa, não habilitar uploads.
   Não tornar o bucket público como solução para erro de acesso.
5. Atualizar dependências com `python -m pip install -r requirements.txt` e
   configurar o backend antes de reiniciá-lo. Manter URL e chave exclusiva de
   servidor existentes. Acrescentar/conferir estes valores para o banco real atual:

   ```dotenv
   SUPABASE_AVATAR_BUCKET=lifes-perfis
   LIFES_DATA_REGISTRO_TIPO=date
   ```

   `LIFES_DATA_REGISTRO_TIPO=date` é o padrão desta versão, correspondente ao
   banco real confirmado. Em instalação nova por `schema.sql`, usar `timestamptz`;
   para coluna timestamp sem offset, usar `timestamp` (UTC). Não converter tipos
   nem datas históricas para ajustar a configuração.
   Confirmar `LIFES_REQUIRE_SERVER_KEY=1`, `FLASK_SECRET_KEY` estável e uma opção de
   credencial: `SUPABASE_SECRET_KEY=sb_secret_...` **ou** o JWT em
   `SUPABASE_SERVICE_ROLE_KEY`. Não usar chave anon/publishable, não trocar a chave
   atual sem necessidade e não colocar credenciais em HTML/JS. O nome do bucket
   deve coincidir com o SQL de Storage; trocar só o `.env` não instala proteção.
6. Reiniciar o Flask com a nova versão, recarregar o navegador e rodar
   `python -m scripts.verificar_banco --evolucao`. As nove tabelas devem passar.
   Conferir `diagnostico_evolucao.sql` e `validacao_evolucao.sql`, ambos de leitura.
   Todas as contagens de divergências da validação devem ser zero.
7. Realizar o checklist abaixo em uma conta de teste e só então reabrir gravações.

Para instalação **nova**, a ordem é `schema.sql` (base com as três etapas antigas),
nova migração de evolução e proposta de Storage. Não usar `schema.sql` sobre o
banco existente. O SQL novo é reaplicável sem duplicar XP, mas deve ser executado
como arquivo completo, em sessão sem transação anterior abortada.

**Testes locais e limites da validação**

- 101 testes Python: login/CSRF, isolamento, perfil, foto válida/inválida,
  concorrência de perfil, falhas/limpeza parcial, decimais, metas, timer,
  recuperação de duplicidades, conquistas e limites de 9999 níveis, além de XP muito alto.
- `tests/sql_evolucao.cjs`: PostgreSQL descartável via PGlite; migração/reaplicação,
  legado, fórmulas, três métricas, período/fuso, correção/estorno, marco de sequência,
  transações, rollback após falha, ACL efetiva e RPC desconhecida preservada.
  Rodar também com `--date`: reproduz DATE, NUMERIC e varchar(100) do banco real;
  o modo padrão cobre timestamptz e timestamp legado.
- `tests/sql_storage_perfis.cjs`: bucket privado/policy restritiva, tipos text e
  varchar, reaplicação, bloqueio público sob policy permissiva preexistente e
  preservação de objetos. É uma simulação SQL das tabelas do Storage, não o serviço remoto.
- Regressões SQL: `sql_semanas_8_9.cjs`, `sql_seguranca.cjs`, `sql_defaults_xp.cjs`,
  `sql_indice_conquistas.cjs`.
- Chrome/Playwright: `browser_smoke`, `browser_semanas_8_9`, `browser_finalizacao`,
  `browser_evolucao`. Incluem 55 combinações de telas/larguras anteriores e 30 da
  evolução, foto/prévia/remoção, decimal, cache de confirmação, resposta perdida,
  erro HTTP, áudio e ausência de overflow em 320–1440 px. Usam banco/Storage
  simulados; a contabilidade SQL é verificada separadamente no PostgreSQL.

Comandos: `python -m unittest discover -q`,
`python -m tests.browser_evolucao` (e os outros módulos de navegador).
Para os `.cjs`, instalar `@electric-sql/pglite` em ambiente de testes e executar
`node tests/sql_evolucao.cjs` etc. Alternativamente apontar `PGLITE_MODULE` para a
instalação local do pacote. Nenhum desses testes deve receber conexão do Supabase.

Capturas locais: `artifacts/validacao/evolucao-*.png`. A ilustração Caminhada foi
gerada com a skill imagegen e copiada para o projeto: personagem feminina em
caminhada, roupa grafite/coral, renderização 3D e fundo transparente, usando
`corrida.png` apenas como referência de estilo. Não substitui arquivos anteriores.

**Checklist após implantação autorizada**

- Entrar/sair em duas contas; confirmar isolamento de perfil, fotos, atividades,
  metas e XP. Confirmar que o navegador não recebe a chave do servidor.
- Alterar nome, enviar JPEG/PNG/WebP, substituir/remover foto; conferir avatar em
  Perfil, sidebar e Dashboard. Recusar SVG, imagem corrompida e arquivo grande.
- Testar duas abas com o mesmo perfil: o formulário antigo deve pedir recarga.
  Confirmar bucket privado e acesso/listagem negados com anon/authenticated.
- Registrar 30 min/3 km de corrida: lançamento da sessão +45; outros bônus devem
  estar separados. Repetir UUID e treino da Agenda: nenhum prêmio adicional.
- Editar para 25 min/5 km: ajuste +5. Excluir: -50, mantendo +45 e +5 no histórico.
  Conferir comportamento de sessão antiga +20 e de sessão antiga sem XP.
- Criar metas por minutos/km/sessões e modalidades distintas; conferir período
  inclusivo, distância ausente, percentual e acumulado. Editar a data/duração/
  distância ou excluir uma atividade: recalcular. Conferir datas perto da meia-noite
  em Brasília, especialmente com a coluna DATE do banco atual. Recompletar não repete +50.
- Converter uma meta legada conscientemente; conferir que ID e prêmio anterior
  permanecem. Confirmar que slider/percentual enviado pelo cliente não controla progresso.
- Finalizar cronômetro com 179 segundos: dois minutos. Informar distância inválida,
  corrigir, recarregar e reenviar; não perder sessão nem duplicar atividade.
- Conferir 100/250/550/1000 XP como níveis 2/3/4/5 e redução de nível após estorno.
  Usar apenas atividades reais de teste; não inserir XP manualmente.
- Recuperar conquistas pendentes e conferir bônus único, histórico e Dashboard.
- Reexecutar a validação somente leitura. Validar requisições concorrentes em
  ambiente real de homologação antes de afirmar prontidão de produção.

Ainda dependem de autorização/validação real: aplicação dos dois SQLs de escrita,
configuração do bucket/policy, restart/implantação do backend e testes reais de
persistência/Storage/concorrência. Testes locais aprovados não equivalem a uma
implantação validada no Supabase.

**Relação completa dos arquivos desta etapa**

```text
.env.example
EVOLUCAO_PERFIL_METAS_XP.md
README.md
app.py
evolucao.py
migrations/diagnostico_evolucao.sql
migrations/evolucao_perfil_metas_xp_niveis.sql
migrations/storage_perfis_privado.sql
migrations/validacao_evolucao.sql
modalidades.py
perfil.py
recompensas.py
requirements.txt
scripts/verificar_banco.py
static/css/premium.css
static/img/modalidades/caminhada.png
static/js/cronometro.js
static/js/distancia.js
static/js/interacoes.js
static/js/perfil.js
templates/_avatar.html
templates/_cronometro.html
templates/atividade_form.html
templates/atividades.html
templates/base_dashboard.html
templates/dashboard.html
templates/meta_form.html
templates/metas.html
templates/perfil.html
templates/pontuacao.html
tests/browser_evolucao.py
tests/browser_finalizacao.py
tests/browser_semanas_8_9.py
tests/browser_smoke.py
tests/sql_evolucao.cjs
tests/sql_storage_perfis.cjs
tests/test_auditoria_xp.py
tests/test_evolucao.py
tests/test_finalizacao.py
tests/test_semanas_6_7.py
tests/test_semanas_8_9.py
```
