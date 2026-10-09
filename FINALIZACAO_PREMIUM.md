# Lifes On — revisão final das Semanas 8 e 9

**Auditoria posterior:** [AUDITORIA_XP.md](AUDITORIA_XP.md) contém a proteção de XP,
credencial de servidor, ordem de implantação e resultados atuais dos testes.

Implementação local em 08/10/2026. **Ainda não liberado para apresentação com o
Supabase real:** o salvamento integrado depende das migrações abaixo, que não
foram executadas remotamente. Este relatório substitui as regras antigas de
frequência, exclusão de atividades, reconciliação por GET e interface.

## 1. Auditoria e causas dos erros

Foram revisados os módulos Flask, cliente Supabase, cálculos, recompensas, alertas,
templates, JavaScript, CSS, schema, migrações, documentação e testes existentes.
A base inicial passou em 54 testes Python. Não foram alterados `.env`, credenciais,
autenticação, permissões remotas, RLS ou dependências de execução. A auditoria
posterior propõe restrições locais de ACL, ainda não aplicadas remotamente.

Diagnóstico real: `python -m scripts.verificar_banco --detalhado`, exclusivamente
SELECT com `limit=0`, sem consultar dados pessoais ou executar SQL de migração.

| Objeto esperado | Resultado remoto |
| --- | --- |
| `atividades.chave_registro`, `atividades.id_agenda` | Não disponíveis, código 42703 |
| `agenda.realizado_em`, `agenda.modalidade` | Não disponíveis, código 42703 |
| `dicas.categoria`, `dicas.fonte` | Não disponíveis, código 42703 |
| `recompensas_xp` | Não encontrada/exposta no cache de esquema PostgREST, PGRST205 |
| Alertas, Metas, Conquistas, Associação | Colunas consultadas acessíveis |

**Cronômetro:** `registrar_atividade` exige a leitura do livro de XP antes de gravar.
Essa leitura falha no ambiente atual, resultando em 503. O JavaScript antigo
transformava qualquer 5xx em exceção de conexão e escondia a resposta explicativa.
Além disso, sessão expirada e CSRF inválido podiam devolver HTML, quebrando
`response.json()`. Não é uma falha resolvível apenas trocando a mensagem.

**XP indisponível:** o livro esperado não está acessível na API configurada. As
colunas ausentes também correspondem à migração das Semanas 8/9 pendente.
O diagnóstico REST não permite concluir quais GRANTs, policies, constraints ou
triggers existem; `diagnostico_finalizacao.sql` permite inspecioná-los no SQL Editor.
Não foi presumido que trocar a chave ou desativar RLS resolveria o problema.

Outros problemas: frequência confundia sessões com planejamento; Artes Marciais
não estava no catálogo/validador SQL; imagens existentes não eram usadas; exclusão
mantinha os 20 XP da atividade; abrir páginas podia materializar conquistas e XP;
feedback de erro era técnico; a atualização do cronômetro deixava partes do resumo
e a tabela acessível do gráfico desatualizadas.

## 2. Correções e integração

- Respostas JSON para erros HTTP do cronômetro; 401 para sessão ausente com CSRF
  ainda válido, 400 para CSRF inválido, 503 para falha de banco. Nenhum detalhe de
  SQL/credenciais na interface; logs registram classe/código, sem payloads pessoais.
- JavaScript diferencia resposta HTTP de conexão realmente interrompida. Mantém
  UUID e confirmação pendente em `sessionStorage`, inclusive após reload. Cancela
  a pendência somente ao confirmar sucesso ou ao cancelar explicitamente.
- Atividade, 20 XP e realização da Agenda continuam na mesma transação SQL.
  Índices únicos e serialização por usuário protegem reenvio/duplo clique. O livro
  conserva o UUID mesmo após exclusão, impedindo recriação pelo mesmo pedido.
- Mesmo serviço de registro para manual e cronômetro; mesma fonte de dados para
  Progresso, gráficos, sequência, Dashboard e conquistas.
- Manual: modalidade, duração e data local de realização. Datas futuras/inválidas
  são rejeitadas; datas sem horário são persistidas à meia-noite de Brasília em UTC.
  A API aceita formulários antigos sem data, usando o dia atual para compatibilidade.
- Frequência foi retirada do formulário. Novas sessões gravam **NULL**, nunca uma
  frequência semanal inventada. Valores antigos são preservados, inclusive na edição,
  e identificados como históricos. Cada linha continua sendo uma sessão.
- Agenda tem modalidade opcional, sem adivinhar pelo título. Iniciar leva ao timer
  e pré-seleciona a modalidade para confirmação. Planejamento não gera XP.
- Edição de atividade preserva seu prêmio básico; novos marcos reais podem ser
  desbloqueados. Exclusão acrescenta estorno de 20 XP, se havia recompensa original.
- Metas mantêm progresso declarado pelo usuário. Nenhuma atividade incrementa uma
  meta textual automaticamente.
- Alertas mantêm persistência, contador, estados lido/não lido e ações individuais
  e coletivas. Dicas mantêm catálogo, busca, filtros, detalhe e fontes existentes.

Conquistas são sincronizadas após salvar atividade/edição/meta, ou por POST explícito
em **Conferir conquistas pendentes**. Abrir páginas não concede XP. Esse botão
recupera obtenções após falha parcial ou expansão do catálogo; o prêmio corresponde
ao marco comprovado no histórico, nunca ao clique. Sem livro de XP acessível, essas
mutações não prosseguem. Nomes duplicados com diferenças de caixa/espaços são
normalizados, priorizando associações já obtidas; nenhum ID legado é apagado.

## 3. Banco: arquivos para revisão e autorização

Para o banco existente, conferir primeiro `migrations/diagnostico_finalizacao.sql`
(somente leitura). Depois, **somente mediante autorização**, aplicar nesta ordem:

1. Configurar a credencial de servidor em manutenção e autorizar/aplicar
   `migrations/seguranca_backend.sql`; ver os pré-requisitos em AUDITORIA_XP.md.
2. `migrations/semanas_8_9.sql`: evolução já pendente; livro de XP, UUID, vínculo e
   conclusão da Agenda, triggers atômicos, proteção do livro e metadados de Dicas.
3. `migrations/finalizacao_premium.sql`: frequência anulável, modalidade da Agenda,
   Artes Marciais no validador, validação de edição, estorno, sequência após edição
   da data e catálogo completo das 14 conquistas, sem duplicar nomes normalizados.

Pré-requisitos anteriores: `semanas_6_7.sql` e `alertas_leitura.sql`. As colunas
dessas etapas foram acessíveis no diagnóstico, mas seus índices/permissões ainda
precisam da auditoria SQL. A finalização aceita timestamp legado UTC sem offset no
cálculo de sequência, consistente com Python. Não converte a coluna nem reescreve datas.

As migrações são transacionais e repetíveis em ordem. Não apagam registros nem
alteram policies/RLS. As versões auditadas alteram GRANT/REVOKE das tabelas e
funções internas conforme AUDITORIA_XP.md; exigem aprovação dessa restrição. O novo CHECK permite o lançamento `-20`;
o original permanece imutável. Se houver constraints personalizadas incompatíveis,
a transação deve falhar para revisão, sem contorná-las silenciosamente.

`schema.sql` inclui a evolução completa **somente para instalação nova**. Não usar
o schema completo como atualização do banco real. Nenhum SQL remoto foi executado.

## 4. Imagens e identidade visual

Não foram encontradas as pastas `imgs/` e `static/imgs` com os seis arquivos citados.
Havia cinco PNGs não rastreados já em `static/img/modalidades/`: Corrida, Musculação,
Natação, Outros e `artesmarciais.png`. Todos foram preservados. O último recebeu
uma cópia no nome canônico `artemarcial.png`.

`modalidades.py` centraliza os sete tipos, os caminhos e os fallbacks. O macro
`_modalidade.html` usa `url_for`, dimensões explícitas, `object-fit: contain`, lazy
loading fora do destaque e fallback para arquivo ausente ou falha de carregamento.

| Modalidade | WebP utilizado | Tamanho |
| --- | --- | ---: |
| Corrida | `corrida.webp` | 84.610 bytes |
| Musculação | `musculacao.webp` | 42.998 bytes |
| Natação | `natacao.webp` | 55.310 bytes |
| Artes Marciais | `artemarcial.webp` | 45.914 bytes |
| Outros | `outros.webp` | 55.638 bytes |

Total: 2.049.883 bytes de PNGs para 284.470 bytes de WebP (~86% menor). Conversão
local, qualidade 92%, lado máximo 800 px, transparência preservada, sem geração de
novas ilustrações. O utilitário `scripts/otimizar_modalidades.py` usa o Chrome já
disponível para testes. Não introduz Pillow ou dependências no aplicativo.

**Pendentes: `yoga.png` e `ciclismo.png`.** Enquanto ausentes, usam ícones discretos
do próprio tipo, sem reutilizar a arte de outra modalidade. Adicioná-los à pasta
canônica habilita o mapeamento; executar o utilitário gera os WebPs opcionais.

O Dashboard apresenta XP/nível, duas medalhas recentes e sequência; próximo treino
com imagem correspondente, data e ação; gráfico semanal e meta atual. Não há ranking
nem métricas inventadas. O cronômetro fica em seção recolhível. Cores: navy/grafite
na estrutura, esmeralda nas ações, azul no gráfico e âmbar na chama.

Sidebar: **Dashboard → Agenda → Progresso → Metas → Registrar Atividade → Pontuação
→ Conquistas → Dicas → Alertas**. Configurações sai da navegação. O cabeçalho oferece
controle de áudio; a rota antiga de preferências permanece compatível.

`premium.css` harmoniza todos os módulos, formulários, estados, foco e tamanhos de
tela. O histórico usa imagens pequenas; o formulário tem seletor ilustrado. Medalhas
são SVGs originais com tênis, halter, alvo, escudo, chama, coroa, troféu e cronômetro;
são apresentadas como medalhas vetoriais, sem alegação de arte 3D gerada.

## 5. Regras de XP e níveis

| Evento confirmado | XP | Regra |
| --- | ---: | --- |
| Nova sessão válida | +20 | Uma vez por UUID; não proporcional à duração |
| Excluir sessão premiada | -20 | Estorno único; mantém a recompensa original no livro |
| Primeira conclusão de uma meta | +50 | Uma vez por ID da meta |
| Conquista desbloqueada | +30 | Uma vez por associação persistida |
| Primeiro marco de sete dias consecutivos | +50 | Uma vez por usuário |

Nível: `1 + total // 100`; barra: `total % 100`; faltam `100 - total % 100`.
Backend soma lançamentos persistidos, incluindo estornos. O navegador não escolhe
XP, nível, usuário ou critério de conquista.

**Política de edição/exclusão:** XP de sessão é sustentado pela existência da sessão;
editar duração/modalidade não muda o valor fixo, excluir estorna. Metas, conquistas
e sequência representam **marcos históricos**, portanto suas recompensas permanecem
após redução/exclusão dos dados, sem novo prêmio por reabertura/reconclusão.
A pontuação distingue experiência histórica de contagem atual; Progresso sempre
reflete o histórico atual de atividades. A política está exposta em Pontuação.

Não há backfill de XP básico para atividades antigas sem lançamento, nem estorno
sem recompensa original. Conquistas realmente elegíveis podem ser recuperadas pela
ação explícita. Agendar/abrir páginas nunca concede XP. O livro continua protegido
contra INSERT/UPDATE/DELETE/TRUNCATE arbitrários.

## 6. Catálogo de conquistas

Preservadas: Primeiro passo, Em Movimento, Foco Total, Veterano, Semana cheia e Meta
batida. Acrescentadas: Lenda do Treino (100 sessões), Constância de Aço (14 dias),
Imparável (30 dias), Caçador de Metas (5 metas), Mestre dos Objetivos (10 metas), Uma
Hora de Superação (60 min), Dez Horas de Evolução (600 min) e Centurião (6.000 min).

Total: 14 critérios. Raridades Comum/Rara/Épica/Lendária e símbolos ficam centralizados
em `progresso.py`; tabelas `conquistas` e `usuario_conquista` são reutilizadas. A página
mostra bloqueadas, obtidas, progresso, condição, raridade e data persistida.

## 7. Sons e microinterações

Gerenciador único em `interacoes.js`: notas originais em intervalos musicais, tons
mais graves, clique de 55 ms e ganho reduzido, recompensas com envelope de 270 ms,
ataque suave e decaimento exponencial. Limita sobreposição; desligar interrompe
osciladores ativos e limpa sons pendentes. Não toca confirmação ao enviar formulário.

Preferência desligada por padrão, persistida por usuário/navegador. Respeita gesto
para desbloquear AudioContext. Áudio opcional, mensagens acessíveis e fila única de
recompensas confirmadas. Progresso e botões têm transições discretas; movimento
reduzido é respeitado. A qualidade subjetiva do som precisa de escuta no equipamento
da apresentação; testes automatizados verificam síntese/controle, não preferência musical.

## 8. Verificação e limites

- Python: 64 testes locais, banco simulado. Cadastro/login, CSRF, isolamento, CRUD,
  datas, Artes Marciais, critérios, níveis, duplicidade, estorno, erros e recuperação.
- Chrome `browser_smoke`: regressão de login, Agenda, timer/pausas, gráficos,
  conquistas, alertas, mobile e falha de CDN.
- Chrome `browser_semanas_8_9`: Dicas, XP confirmado, áudio, movimento reduzido,
  duplo clique, resposta perdida e visualização mobile.
- Chrome `browser_finalizacao`: 11 páginas em 1440/1024/768/390/320 px (55 combinações),
  imagens/fallback, sidebar, data, Artes Marciais, Agenda → timer, erro 503 e UUID
  preservado após reload e resposta perdida. Capturas em `artifacts/validacao/`.
- PostgreSQL WASM local/PGlite: schema e migrações repetidas, triggers, estorno,
  validações, associação de usuário, XP único, livro protegido e rollback. Não simula
  permissões/policies do Supabase nem prova concorrência entre conexões remotas.
- Remoto: somente o diagnóstico SELECT descrito no início. **Nenhuma escrita,
  migração, persistência nova ou isolamento direto da API remota foi validado.**

O login herdado usa Flask, não Supabase Auth; isolamento nas rotas não certifica RLS
na API direta. O treino em andamento ainda não sobrevive a reload; apenas a
confirmação já enviada é recuperável. Fechar a aba encerra seu `sessionStorage`.
CDNs de fontes/ícones/gráficos permanecem; gráficos oferecem tabela alternativa.

## 9. Arquivos alterados

Backend: `app.py`, `progresso.py`, novo `modalidades.py`; cálculos de nível em
`recompensas.py` preservados. Banco: `schema.sql`, novos `finalizacao_premium.sql`
e `diagnostico_finalizacao.sql`. Utilitários: `verificar_banco.py` e novo
`otimizar_modalidades.py`. Interface: `base_dashboard`, `dashboard`, `atividade_form`,
`atividades`, `agenda`, `treino_form`, `conquistas`, `pontuacao`, `progresso`, `dicas`,
`indisponivel`, `_cronometro`, `_xp`, novos `_modalidade` e `_medalha`; `premium.css`,
`cronometro.js`, `interacoes.js`, `progresso.js` e imagens em `static/img/modalidades`.
Testes: suítes anteriores atualizadas, novos `test_finalizacao.py` e
`browser_finalizacao.py`, SQL local ampliado. Documentação: este relatório, README,
checklist e indicação de versão histórica em `SEMANAS_8_9.md`.

## 10. Executar e validar

```powershell
.\.venv\Scripts\python.exe -m unittest -q
.\.venv\Scripts\python.exe -m tests.browser_smoke
.\.venv\Scripts\python.exe -m tests.browser_semanas_8_9
.\.venv\Scripts\python.exe -m tests.browser_finalizacao
$env:PGLITE_MODULE = "$env:TEMP\lifes-on-sql-validation\node_modules\@electric-sql\pglite"
node tests/sql_semanas_8_9.cjs
.\.venv\Scripts\python.exe -m scripts.verificar_banco --detalhado
.\.venv\Scripts\python.exe -m flask --app app run
```

PGlite é ferramenta de teste instalada fora do repositório; instruções de instalação
estão no README. O diagnóstico retorna código 1 enquanto houver colunas/livro
indisponíveis. Não é falha a esconder nem indicação de teste de escrita realizado.

Pendências para liberação: diagnóstico real e aprovação/aplicação da etapa de
segurança e das duas migrações, conforme AUDITORIA_XP.md; validação de ACL efetiva; gravação com conta de teste autorizada, recarga e duas
contas/abas reais; imagens Yoga e Ciclismo; escuta e conferência humana. Não declarar
o projeto finalizado no ambiente real enquanto cronômetro/XP estiverem bloqueados.
